from datetime import date, datetime
from decimal import Decimal
import json
import redis
import mysql.connector
from typing import Optional

# 1. Redis Connection
r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
CACHE_TTL = 300  # 5 minutes

# 2. MySQL Connection Config
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "MySql_11111",
    "database": "event_ticketing_db",
    "port": 3306
}

def fetch_event_from_mysql(event_id: int) -> Optional[dict]:
    """Authoritative source of record query for the EVENTS table."""
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor(dictionary=True)
    try:
        query = """
            SELECT event_id, title, venue_id, category_id, start_datetime, end_datetime, status, created_at, updated_at, created_by
            FROM EVENTS
            WHERE event_id = %s
        """
        cursor.execute(query, (event_id,))
        row = cursor.fetchone()
        
        if not row:
            return None

        # Convert date/time objects to ISO string for JSON serialization
        for key, val in row.items():
            if isinstance(val, (datetime, date)):
                row[key] = val.isoformat()
            elif isinstance(val, Decimal):
                row[key] = float(val)

        return row
    finally:
        cursor.close()
        connection.close()

def get_event_with_cache(event_id: int) -> Optional[dict]:

    cache_key = f"event:cache:{event_id}"
    
    # --- Step 1: Check Redis ---
    cached_data = r.get(cache_key)
    if cached_data:
        data = json.loads(cached_data)
        data["_cache_status"] = "HIT"
        record_event_view(event_id)
        return data

    # --- Step 2: Cache MISS -> Fallback to MySQL ---
    event_data = fetch_event_from_mysql(event_id)
    if not event_data:
        return None  # Event doesn't exist in MySQL, exit w/o recording view
    
    # --- Step 3: Populate Redis with TTL ---
    r.setex(cache_key, CACHE_TTL, json.dumps(event_data))
    
    event_data["_cache_status"] = "MISS"
    record_event_view(event_id)
    return event_data

TRENDING_KEY = "events:trending"

def record_event_view(event_id: int) -> float:
    """
    Increments the view score for an event by 1.0.
    Member key format matches the assignment example: 'event:<id>'
    Returns the updated score.
    """
    member = f"event:{event_id}"
    new_score = r.zincrby(TRENDING_KEY, 1.0, member)
    return float(new_score)


def get_top_trending_events(limit: int = 10) -> list[dict]:
    """
    Retrieves the top N trending events ordered by score descending.
    Returns a list of dictionaries with event_id and its score/views.
    """
    # zrevrange returns elements ordered from highest to lowest score
    # limit=10 retrieves indices 0 through 9
    raw_results = r.zrevrange(TRENDING_KEY, 0, limit - 1, withscores=True)
    
    trending_list = []
    for member, score in raw_results:
        # member is formatted as 'event:105' -> extract 105
        event_id = int(member.split(":")[1])
        trending_list.append({
            "event_id": event_id,
            "score": int(score)
        })
        
    return trending_list


def get_event_score(event_id: int) -> Optional[float]:
    """Optional helper: check the current popularity score of an event."""
    score = r.zscore(TRENDING_KEY, f"event:{event_id}")
    return float(score) if score is not None else 0.0

#def main():
#    test_event_id = 101  # Example event ID to test
#    result = get_event_with_cache(test_event_id)
#    
#    if result:
#        print(f"Event Data for ID {test_event_id}:")
#        print(json.dumps(result, indent=4))
#    else:
#        print(f"No event found for ID {test_event_id}.")
#        print("\n--- Testing Trending Events (Sorted Set) ---")
#    
#    # Simulate views
#    record_event_view(105)
#    record_event_view(105)
#    record_event_view(201)
#    record_event_view(310)
#    record_event_view(105)  # Event 105 now has 3 views
#    record_event_view(201)  # Event 201 now has 2 views
#    
#    # Retrieve top trending
#    top_events = get_top_trending_events(limit=10)
#    print("Top Trending Events:")
#    for rank, item in enumerate(top_events, start=1):
#        print(f"Rank {rank}: Event ID {item['event_id']} -> Score: {item['score']}")

#main()