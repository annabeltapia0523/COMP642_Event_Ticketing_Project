#MySQL data-access layer for the Event Ticketing API (Part A).


from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

VALID_PAYMENT_METHODS = frozenset({"credit_card", "debit_card", "paypal", "apple_pay"})

#Raised when a ticket purchase cannot be completed (nothing is saved).
class PurchaseError(Exception):
    

#One line of a purchase request: which ticket type and how many.
@dataclass(frozen=True)
class OrderLine:
    

    ticket_type_id: int
    quantity: int

#Convert Decimal/datetime values so the dict can go to JSON or Redis.
def _to_json_safe(row: dict[str, Any]) -> dict[str, Any]:
   
    safe: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            safe[key] = float(value)
        elif isinstance(value, (datetime, date)):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe

 #All SQL the application needs, in one place (class libary)
class MySQLRepository:
   

    def __init__(self, pool: MySQLConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def from_env(cls) -> "MySQLRepository":
        #Build a connection pool from environment variables / .env file.
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass  # plain environment variables still work

        pool = MySQLConnectionPool(
            pool_name="ticketing_pool",
            pool_size=int(os.getenv("MYSQL_POOL_SIZE", "5")),
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "ticket_app"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "event_ticketing_db"),
            autocommit=True,  # reads commit instantly; purchases open a transaction
        )
        return cls(pool)

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        #Borrow a connection from the pool and always give it back.
        conn = self._pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            try:
                yield cursor
            finally:
                cursor.close()
        finally:
            conn.close()  # returns the connection to the pool

    def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(sql, params)
            return [_to_json_safe(row) for row in cur.fetchall()]

    def _fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self._fetch_all(sql, params)
        return rows[0] if rows else None


    # Events  (GET /events, GET /events/{id})
    def list_events(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            "SELECT * FROM v_event_summary ORDER BY start_datetime"
        )

    def get_event_summary(self, event_id: int) -> dict[str, Any] | None:
        #MySQL half of GET /events/{id}: event, venue, price, availability.
        event = self._fetch_one(
            "SELECT * FROM v_event_summary WHERE event_id = %s", (event_id,)
        )
        if event is None:
            return None
        event["ticket_types"] = self._fetch_all(
            """
            SELECT ticket_type_id, name, price, quantity_available
            FROM ticket_types
            WHERE event_id = %s
            ORDER BY price
            """,
            (event_id,),
        )
        return event

    # Users  (POST /users, GET /users/{id}/orders)
    def create_user(
        self,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        phone: str | None = None,
    ) -> int:
        #nsert a customer. Duplicate email raises mysql.connector.IntegrityError.
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, first_name, last_name, phone)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (email, password_hash, first_name, last_name, phone),
            )
            return cur.lastrowid

    def user_exists(self, user_id: int) -> bool:
        #Used by the MongoDB team before saving a review for user_id.
        return self._fetch_one("SELECT 1 AS ok FROM users WHERE user_id = %s", (user_id,)) is not None

    def get_user_orders(self, user_id: int) -> list[dict[str, Any]]:
        #Query 2 as an API call: every ticket line a user bought.
        return self._fetch_all(
            """
            SELECT o.order_id, o.order_datetime, o.status, e.event_id,
                   e.title AS event, t.name AS ticket_type,
                   oi.quantity, oi.unit_price,
                   oi.quantity * oi.unit_price AS line_total
            FROM orders AS o
            JOIN order_items  AS oi ON oi.order_id      = o.order_id
            JOIN ticket_types AS t  ON t.ticket_type_id = oi.ticket_type_id
            JOIN events       AS e  ON e.event_id       = t.event_id
            WHERE o.user_id = %s
            ORDER BY o.order_datetime DESC, o.order_id DESC
            """,
            (user_id,),
        )

    # Orders  (POST /orders)  -> ACID transaction
    def purchase_tickets(
        self, user_id: int, lines: list[OrderLine], payment_method: str
    ) -> dict[str, Any]:
        #Create order + items + inventory update + payment, all or nothing.
        #Returns {"order_id", "total_amount", "event_ids"} on success.
        #Raises PurchaseError (and saves nothing) on any failure.
        #The caller should delete the Redis cache for each returned event_id,because ticket availability just changed.
        
        self._validate_purchase(lines, payment_method)
        # Lock rows in a fixed order -> two buyers can never deadlock each other
        ordered = sorted(lines, key=lambda line: line.ticket_type_id)

        conn = self._pool.get_connection()
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            priced = [self._lock_and_check(cur, line) for line in ordered]
            total = sum(price * line.quantity for line, price, _ in priced)

            cur.execute(
                "INSERT INTO orders (user_id, status, total_amount) VALUES (%s, 'pending', %s)",
                (user_id, total),
            )
            order_id = cur.lastrowid

            for line, price, _ in priced:
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, ticket_type_id, quantity, unit_price)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, line.ticket_type_id, line.quantity, price),
                )
                cur.execute(
                    """
                    UPDATE ticket_types
                    SET quantity_available = quantity_available - %s
                    WHERE ticket_type_id = %s
                    """,
                    (line.quantity, line.ticket_type_id),
                )

            cur.execute(
                """
                INSERT INTO payments (order_id, amount, method, status, transaction_ref)
                VALUES (%s, %s, %s, 'completed', %s)
                """,
                (order_id, total, payment_method, f"TXN-{uuid.uuid4().hex[:32]}"),
            )
            cur.execute("UPDATE orders SET status = 'paid' WHERE order_id = %s", (order_id,))
            conn.commit()
            return {
                "order_id": order_id,
                "total_amount": float(total),
                "event_ids": sorted({event_id for _, _, event_id in priced}),
            }
        except PurchaseError:
            conn.rollback()
            raise
        except mysql.connector.Error as exc:
            conn.rollback()
            raise PurchaseError(f"Purchase failed and was rolled back: {exc.msg}") from exc
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def _validate_purchase(lines: list[OrderLine], payment_method: str) -> None:
        if not lines:
            raise PurchaseError("An order needs at least one ticket line")
        if any(line.quantity < 1 for line in lines):
            raise PurchaseError("Quantity must be at least 1")
        if len({line.ticket_type_id for line in lines}) != len(lines):
            raise PurchaseError("Each ticket type may appear only once per order")
        if payment_method not in VALID_PAYMENT_METHODS:
            raise PurchaseError(f"Unsupported payment method: {payment_method}")

    @staticmethod
    def _lock_and_check(cur: Any, line: OrderLine) -> tuple[OrderLine, Decimal, int]:
        #SELECT ... FOR UPDATE: lock the ticket row, then check stock.
        cur.execute(
            """
            SELECT t.price, t.quantity_available, t.event_id, e.status
            FROM ticket_types AS t
            JOIN events AS e ON e.event_id = t.event_id
            WHERE t.ticket_type_id = %s
            FOR UPDATE
            """,
            (line.ticket_type_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise PurchaseError(f"Ticket type {line.ticket_type_id} does not exist")
        if row["status"] != "scheduled":
            raise PurchaseError(f"Event {row['event_id']} is not open for sales")
        if row["quantity_available"] < line.quantity:
            raise PurchaseError(
                f"Only {row['quantity_available']} tickets left for type {line.ticket_type_id}"
            )
        return line, row["price"], row["event_id"]


    # Admin analytics (the 8 required queries, reusable by the API)
    def revenue_by_event(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT e.event_id, e.title,
                   COALESCE(SUM(CASE WHEN o.status = 'paid'
                                     THEN oi.quantity * oi.unit_price END), 0) AS revenue
            FROM events AS e
            LEFT JOIN ticket_types AS t  ON t.event_id        = e.event_id
            LEFT JOIN order_items  AS oi ON oi.ticket_type_id = t.ticket_type_id
            LEFT JOIN orders       AS o  ON o.order_id        = oi.order_id
            GROUP BY e.event_id, e.title
            ORDER BY revenue DESC
            """
        )

    def monthly_revenue(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT DATE_FORMAT(o.order_datetime, '%Y-%m') AS sales_month,
                   SUM(oi.quantity) AS tickets_sold,
                   SUM(oi.quantity * oi.unit_price) AS revenue
            FROM orders AS o
            JOIN order_items AS oi ON oi.order_id = o.order_id
            WHERE o.status = 'paid'
            GROUP BY sales_month
            ORDER BY sales_month
            """
        )


if __name__ == "__main__":
    # Smoke test:  python -m app.mysql_repository
    repo = MySQLRepository.from_env()
    print("Event 101:", repo.get_event_summary(101))
    print("Orders of user 204:", len(repo.get_user_orders(204)), "lines")
    try:
        repo.purchase_tickets(209, [OrderLine(ticket_type_id=1, quantity=99999)], "paypal")
    except PurchaseError as err:
        print("Expected failure ->", err)
