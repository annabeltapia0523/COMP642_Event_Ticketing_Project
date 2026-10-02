from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import os
from typing import Any, Optional

import mysql.connector
from mysql.connector import Error as MySQLError
import redis
from redis.exceptions import RedisError


class RedisRepositoryError(Exception):
    """Custom exception matching the project's repository error pattern."""
    pass


class RedisRepository:
    def __init__(
        self,
        redis_client: redis.Redis,
        mysql_config: dict[str, Any],
        cache_ttl: int = 300,
        trending_key: str = "events:trending",
    ) -> None:
        self._redis = redis_client
        self._mysql_config = mysql_config
        self.cache_ttl = cache_ttl
        self.trending_key = trending_key

    @classmethod
    def from_env(cls) -> "RedisRepository":
        """Factory method to instantiate the repository using environment variables."""
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass

        # Redis Connection Parameters
        redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        cache_ttl = int(os.getenv("CACHE_TTL", "300"))
        trending_key = os.getenv("REDIS_TRENDING_KEY", "events:trending")

        # MySQL Connection Parameters
        mysql_config = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "user": os.getenv("MYSQL_USER", "ticket_app"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "event_ticketing_db"),
            "port": int(os.getenv("MYSQL_PORT", "3306")),
        }

        try:
            client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                socket_timeout=5,
            )
            # Ping test to fail fast on invalid Redis config
            client.ping()

            return cls(
                redis_client=client,
                mysql_config=mysql_config,
                cache_ttl=cache_ttl,
                trending_key=trending_key,
            )
        except RedisError as exc:
            raise RedisRepositoryError(
                f"Redis connection failed: {exc}"
            ) from exc

    def close(self) -> None:
        """Close the active Redis connection pool."""
        self._redis.close()

    # -------------------------------------------------------------
    # Authoritative MySQL Reader
    # -------------------------------------------------------------
    def fetch_event_from_mysql(self, event_id: int) -> Optional[dict[str, Any]]:
        """Authoritative query for the EVENTS table in MySQL."""
        try:
            connection = mysql.connector.connect(**self._mysql_config)
            cursor = connection.cursor(dictionary=True)
            try:
                query = """
                    SELECT event_id, title, venue_id, category_id, 
                           start_datetime, end_datetime, status, 
                           created_at, updated_at, created_by
                    FROM EVENTS
                    WHERE event_id = %s
                """
                cursor.execute(query, (int(event_id),))
                row = cursor.fetchone()

                if not row:
                    return None

                # Convert date/time and Decimal types for JSON serialization
                for key, val in row.items():
                    if isinstance(val, (datetime, date)):
                        row[key] = val.isoformat()
                    elif isinstance(val, Decimal):
                        row[key] = float(val)

                return row
            finally:
                cursor.close()
                connection.close()
        except MySQLError as exc:
            raise RedisRepositoryError(
                f"MySQL query failed for event {event_id}: {exc}"
            ) from exc

    # -------------------------------------------------------------
    # Use Case 1: Event Cache (Read-Through Cache Pattern)
    # -------------------------------------------------------------
    def get_event_with_cache(self, event_id: int) -> Optional[dict[str, Any]]:
        """
        Retrieves event details. Checks Redis first; falls back to MySQL on miss,
        populates cache with TTL, and tracks view for trending.
        """
        cache_key = f"event:cache:{event_id}"

        try:
            # 1. Check Redis Cache
            cached_data = self._redis.get(cache_key)
            if cached_data:
                data = json.loads(cached_data)
                data["_cache_status"] = "HIT"
                self.record_event_view(event_id)
                return data

            # 2. Cache MISS -> Fallback to MySQL
            event_data = self.fetch_event_from_mysql(event_id)
            if not event_data:
                return None  # Do not record views for nonexistent events

            # 3. Populate Redis with TTL
            self._redis.setex(cache_key, self.cache_ttl, json.dumps(event_data))

            event_data["_cache_status"] = "MISS"
            self.record_event_view(event_id)
            return event_data

        except RedisError as exc:
            raise RedisRepositoryError(
                f"Redis cache operation failed for event {event_id}: {exc}"
            ) from exc

    def invalidate_event_cache(self, event_id: int) -> bool:
        """Evicts an event key from cache when admin updates or cancels an event."""
        try:
            return bool(self._redis.delete(f"event:cache:{event_id}"))
        except RedisError as exc:
            raise RedisRepositoryError(
                f"Failed to invalidate cache for event {event_id}: {exc}"
            ) from exc

    # -------------------------------------------------------------
    # Use Case 2: Trending Events (Sorted Set)
    # -------------------------------------------------------------
    def record_event_view(self, event_id: int) -> float:
        """Increments the view score for an event by 1.0."""
        try:
            member = f"event:{event_id}"
            new_score = self._redis.zincrby(self.trending_key, 1.0, member)
            return float(new_score)
        except RedisError as exc:
            raise RedisRepositoryError(
                f"Failed to record view for event {event_id}: {exc}"
            ) from exc

    def get_top_trending_events(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieves top N trending events ordered by score descending."""
        try:
            raw_results = self._redis.zrevrange(
                self.trending_key, 0, limit - 1, withscores=True
            )
            trending_list = []
            for member, score in raw_results:
                event_id = int(member.split(":")[1])
                trending_list.append({
                    "event_id": event_id,
                    "score": int(score)
                })
            return trending_list
        except RedisError as exc:
            raise RedisRepositoryError(
                f"Failed to retrieve trending events: {exc}"
            ) from exc

    def get_event_score(self, event_id: int) -> float:
        """Returns the current trending score for a specific event."""
        try:
            score = self._redis.zscore(self.trending_key, f"event:{event_id}")
            return float(score) if score is not None else 0.0
        except RedisError as exc:
            raise RedisRepositoryError(
                f"Failed to get score for event {event_id}: {exc}"
            ) from exc


if __name__ == "__main__":
    repo = RedisRepository.from_env()

    try:
        test_id = 101
        print(f"\n--- Testing Cache for Event {test_id} ---")
        first_call = repo.get_event_with_cache(test_id)
        print("First call (should be MISS):", first_call.get("_cache_status") if first_call else "Not found")

        second_call = repo.get_event_with_cache(test_id)
        print("Second call (should be HIT):", second_call.get("_cache_status") if second_call else "Not found")

        print("\n--- Testing Top Trending Events ---")
        for item in repo.get_top_trending_events(5):
            print(f"Event ID {item['event_id']} -> Score: {item['score']}")

    finally:
        repo.close()