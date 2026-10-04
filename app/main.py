"""
FastAPI integration layer - COMP 642 Online Event and Ticketing Service.

This file does NOT talk to any database directly. It calls the repository
classes written by each database teammate:

    app/mysql_repository.py   -> MySQL   (system of record: users, events,
                                          tickets, orders, payments)
    app/mongodb_repository.py -> MongoDB (flexible event_content documents)
    app/redis_repository.py   -> Redis   (event cache + trending sorted set)

Run from the project root (needed so MYSQL_SSL_CA=mysql/ca.pem is found):
    uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs
"""

import json
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, Optional

import bcrypt
import mysql.connector
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints
from redis.exceptions import RedisError

from app.mongodb_repository import EventContentError, MongoDBRepository
from app.mysql_repository import MySQLRepository, OrderLine, PurchaseError
from app.redis_repository import RedisRepository, RedisRepositoryError

# Errors any of the three databases can raise. A route that catches these
# answers "503 Service Unavailable" instead of crashing with a 500.
DATABASE_ERRORS = (
    mysql.connector.Error,   # MySQL
    EventContentError,       # MongoDB teammate's error type
    RedisError,              # Redis driver
    RedisRepositoryError,    # Redis teammate's error type
)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: connect to all three databases ONCE and keep the objects on
    # app.state so every request reuses them. Each teammate's from_env()
    # reads its own settings from .env.
    app.state.mysql = MySQLRepository.from_env()   # MySQL connection pool
    app.state.mongo = MongoDBRepository.from_env() # MongoDB client (pings Atlas)
    app.state.redis = RedisRepository.from_env()   # Redis client (pings Redis)

    yield  # the API runs and serves requests here

    # SHUTDOWN: close the connections cleanly when uvicorn stops.
    app.state.mongo.close()
    app.state.redis.close()


app = FastAPI(
    title="COMP 642 Event Ticketing API",
    description=(
        "Python integration layer connecting MySQL (transactions), "
        "MongoDB (flexible event content) and Redis (cache + trending)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# GET /health - proves Python can reach all three databases
# ---------------------------------------------------------------------------
# Plain "def" (not "async def"): the teammates' database drivers are
# synchronous, so FastAPI runs this function in a worker thread and a slow
# database call never blocks other requests.
@app.get("/health", tags=["System"])
def health(request: Request):
    state = request.app.state
    checks = {}

    # MySQL: read the SQL teammate's v_event_summary view.
    try:
        events = state.mysql.list_events()
        checks["mysql"] = {"status": "ok", "events": len(events)}
    except Exception as exc:
        checks["mysql"] = {"status": "error", "detail": str(exc)[:200]}

    # MongoDB: read the event_content collection.
    try:
        documents = state.mongo.list_event_content()
        checks["mongodb"] = {"status": "ok", "event_documents": len(documents)}
    except Exception as exc:
        checks["mongodb"] = {"status": "error", "detail": str(exc)[:200]}

    # Redis: read the events:trending sorted set.
    try:
        trending = state.redis.get_top_trending_events(limit=10)
        checks["redis"] = {"status": "ok", "trending_events": len(trending)}
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": str(exc)[:200]}

    all_ok = all(check["status"] == "ok" for check in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "databases": checks},
    )


# ---------------------------------------------------------------------------
# GET /events/{event_id} - the operation that uses ALL THREE databases
# ---------------------------------------------------------------------------
def cache_key(event_id: int) -> str:
    # Same key format the Redis teammate uses in redis_repository.py.
    return f"event:cache:{event_id}"


def load_event_from_databases(state: Any, event_id: int) -> Optional[dict[str, Any]]:
    """Read one event from the two persistent databases and combine them.

    MySQL   -> structured facts: event, venue, price range, live ticket types
    MongoDB -> flexible content: description, speakers, schedule, tags, reviews...
    Both are joined on the same integer ID (event_id in MySQL = eventId in MongoDB).
    """
    summary = state.mysql.get_event_summary(event_id)      # MySQL (v_event_summary + ticket_types)
    if summary is None:
        return None                                        # MySQL is the source of truth: no row = no event
    ticket_types = summary.pop("ticket_types")
    content = state.mongo.get_event_content(event_id)      # MongoDB (event_content), may be None

    return {
        "event_id": event_id,
        "event": summary,             # from MySQL
        "ticket_types": ticket_types, # from MySQL
        "content": content,           # from MongoDB
    }


@app.get("/events/{event_id}", tags=["Events"])
def get_event(event_id: int, request: Request, use_cache: bool = True):
    """Event details combined from MySQL + MongoDB, cached in Redis.

    use_cache=true  (default): Redis HIT -> return cached copy.
                               Redis MISS -> read MySQL + MongoDB, combine,
                               store in Redis with a TTL, return.
                               Every view adds +1 to the trending score.
    use_cache=false: skip Redis completely (the "without Redis" side of the
                     performance experiment).
    """
    state = request.app.state
    started = time.perf_counter()

    try:
        # ---- Without Redis: always go to MySQL + MongoDB ------------------
        if not use_cache:
            data = load_event_from_databases(state, event_id)
            if data is None:
                raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
            data["cache"] = {"status": "BYPASS"}
            data["response_time_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return data

        # ---- With Redis: cache-aside ---------------------------------------
        redis_repo = state.redis
        key = cache_key(event_id)

        cached = redis_repo._redis.get(key)                 # 1. check Redis
        data = json.loads(cached) if cached else None
        if data is not None and "event" not in data:
            # Entry written by redis_repository.py's own smoke test (MySQL row
            # only, not our combined format) -> treat it as a MISS.
            data = None

        if data is not None:                                # HIT: no MySQL/MongoDB call at all
            cache_status = "HIT"
        else:
            data = load_event_from_databases(state, event_id)   # 2. MISS: MySQL + MongoDB
            if data is None:
                raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
            redis_repo._redis.set(key, json.dumps(data), ex=redis_repo.cache_ttl)  # 3. store with TTL
            cache_status = "MISS"

        trending_score = redis_repo.record_event_view(event_id)    # 4. +1 trending (teammate method)

        data["cache"] = {
            "status": cache_status,
            "key": key,
            "ttl_seconds": redis_repo.cache_ttl,
            "ttl_remaining_seconds": redis_repo._redis.ttl(key),
        }
        data["popularity"] = {"trending_score": int(trending_score)}
        data["response_time_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return data                                                  # 5. return

    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")

# ---------------------------------------------------------------------------
# GET /trending - Top 10 trending events from Redis
# ---------------------------------------------------------------------------
@app.get("/trending", tags=["Events"])
def get_trending(request: Request, limit: int = 10):
    """Return the most-viewed events using the Redis trending sorted set."""
    state = request.app.state

    try:
        trending = state.redis.get_top_trending_events(limit=limit)

        return {
            "count": len(trending),
            "limit": limit,
            "events": trending,
        }

    except (RedisError, RedisRepositoryError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Redis error: {str(exc)[:200]}"
        )


# ---------------------------------------------------------------------------
# Request models (FastAPI validates every request body against these and
# answers 422 automatically if a field is missing or has the wrong type)
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=72)   # bcrypt uses at most 72 bytes
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=20)

    model_config = {"json_schema_extra": {"examples": [{
        "email": "new.student@mail.example",
        "password": "StrongPass123",
        "first_name": "Angela",
        "last_name": "Johnson",
        "phone": "818-555-0300",
    }]}}


class OrderItem(BaseModel):
    ticket_type_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=65535)   # order_items.quantity is SMALLINT UNSIGNED


class OrderCreate(BaseModel):
    user_id: int = Field(gt=0)
    items: list[OrderItem] = Field(min_length=1)
    # Same four values as the payments.method ENUM in the MySQL schema.
    payment_method: Literal["credit_card", "debit_card", "paypal", "apple_pay"]

    model_config = {"json_schema_extra": {"examples": [{
        "user_id": 204,
        "items": [{"ticket_type_id": 1, "quantity": 2}],
        "payment_method": "credit_card",
    }]}}


class ReviewCreate(BaseModel):
    user_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

    model_config = {"json_schema_extra": {"examples": [{
        "user_id": 204,
        "rating": 5,
        "comment": "Great speakers and well organized",
    }]}}


def clear_event_cache(state: Any, event_ids: list[int]) -> list[int]:
    """Delete the cached GET /events/{id} response for each event (teammate's
    invalidate_event_cache). Called AFTER data changed in MySQL or MongoDB,
    so the next read is a MISS and returns fresh data.

    Never raises: the database change already succeeded, so a Redis problem
    must not turn it into an error (the user could retry and buy twice).
    The cache TTL is the backstop if a delete fails.
    """
    cleared = []
    for event_id in event_ids:
        try:
            state.redis.invalidate_event_cache(event_id)
            cleared.append(event_id)
        except DATABASE_ERRORS:
            pass
    return cleared


# ---------------------------------------------------------------------------
# GET /events - browse all events (MySQL)
# ---------------------------------------------------------------------------
@app.get("/events", tags=["Events"])
def list_events(request: Request):
    """All events from the SQL teammate's v_event_summary view, soonest first."""
    try:
        events = request.app.state.mysql.list_events()
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")
    return {"count": len(events), "events": events}


# ---------------------------------------------------------------------------
# GET /events/{event_id}/content - flexible event document only (MongoDB)
# ---------------------------------------------------------------------------
@app.get("/events/{event_id}/content", tags=["Events"])
def get_event_content(event_id: int, request: Request):
    """The MongoDB event_content document (description, speakers, reviews...)."""
    try:
        content = request.app.state.mongo.get_event_content(event_id)
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")
    if content is None:
        raise HTTPException(status_code=404, detail=f"No MongoDB content for event {event_id}")
    return content


# ---------------------------------------------------------------------------
# POST /users - create a customer account (MySQL)
# ---------------------------------------------------------------------------
@app.post("/users", status_code=201, tags=["Users"])
def create_user(body: UserCreate, request: Request):
    """Create a customer. The password is stored only as a bcrypt hash,
    matching users.password_hash CHAR(60) in the schema."""
    if len(body.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password is longer than 72 bytes")
    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    try:
        user_id = request.app.state.mysql.create_user(
            email=body.email.lower(),
            password_hash=password_hash,
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
        )
    except mysql.connector.IntegrityError:
        # UNIQUE constraint uq_users_email
        raise HTTPException(status_code=409, detail=f"Email {body.email} is already registered")
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")

    # Never send the password or its hash back.
    return {
        "user_id": user_id,
        "email": body.email.lower(),
        "first_name": body.first_name,
        "last_name": body.last_name,
        "role": "customer",
    }


# ---------------------------------------------------------------------------
# GET /users/{user_id}/orders - a user's previous purchases (MySQL)
# ---------------------------------------------------------------------------
@app.get("/users/{user_id}/orders", tags=["Users"])
def get_user_orders(user_id: int, request: Request):
    """Every ticket line the user bought, newest order first (5-table join)."""
    mysql_repo = request.app.state.mysql
    try:
        if not mysql_repo.user_exists(user_id):
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        lines = mysql_repo.get_user_orders(user_id)
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")
    return {"user_id": user_id, "count": len(lines), "order_items": lines}


# ---------------------------------------------------------------------------
# POST /orders - buy tickets (MySQL transaction) + clear Redis cache
# ---------------------------------------------------------------------------
@app.post("/orders", status_code=201, tags=["Orders"])
def create_order(body: OrderCreate, request: Request):
    """Purchase tickets using the SQL teammate's purchase_tickets() transaction:
    lock ticket rows -> order -> order_items -> inventory -> payment -> COMMIT.
    Any failure inside it is rolled back, so nothing is saved."""
    state = request.app.state

    ticket_ids = [item.ticket_type_id for item in body.items]
    if len(set(ticket_ids)) != len(ticket_ids):
        raise HTTPException(
            status_code=400,
            detail="Each ticket type may appear only once per order (combine the quantities)",
        )

    try:
        if not state.mysql.user_exists(body.user_id):
            raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")
        result = state.mysql.purchase_tickets(
            body.user_id,
            [OrderLine(ticket_type_id=i.ticket_type_id, quantity=i.quantity) for i in body.items],
            body.payment_method,
        )
    except PurchaseError as exc:
        # Not enough tickets, event not on sale, unknown ticket type... -> ROLLBACK
        raise HTTPException(status_code=409, detail=f"Purchase rejected and rolled back: {exc}")
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")

    # COMMITTED. Ticket availability changed, so drop the cached event pages.
    cleared = clear_event_cache(state, result["event_ids"])

    return {
        "status": "paid",
        "order_id": result["order_id"],
        "total_amount": result["total_amount"],
        "event_ids": result["event_ids"],
        "cache_cleared_for_events": cleared,
    }


# ---------------------------------------------------------------------------
# POST /events/{event_id}/reviews - MySQL checks the user, MongoDB stores it
# ---------------------------------------------------------------------------
@app.post("/events/{event_id}/reviews", status_code=201, tags=["Reviews"])
def add_review(event_id: int, body: ReviewCreate, request: Request):
    """MySQL is the authority on who users are; the review itself is flexible
    content, so it is pushed into the MongoDB event_content document."""
    state = request.app.state
    try:
        if not state.mysql.user_exists(body.user_id):                     # MySQL
            raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")
        if state.mongo.get_event_content(event_id) is None:               # MongoDB
            raise HTTPException(status_code=404, detail=f"No MongoDB content for event {event_id}")
        updated = state.mongo.add_review(event_id, body.user_id, body.rating, body.comment)
    except DATABASE_ERRORS as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {str(exc)[:200]}")

    # The cached GET /events/{id} response includes reviews -> clear it.
    cleared = clear_event_cache(state, [event_id])

    return {
        "event_id": event_id,
        "review": {"userId": body.user_id, "rating": body.rating, "comment": body.comment},
        "review_count": len(updated.get("reviews", [])),
        "cache_cleared": event_id in cleared,
    }
