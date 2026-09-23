
-- File 02: The 8 required SQL queries + 2  admin queries

USE event_ticketing_db;

-- Query 1: Find all events at a particular venue.Joins 3 tables: events + venues + event_categories

SET @venue_name = 'Pacific Convention Center';

SELECT
    v.name            AS venue,
    e.event_id,
    e.title,
    c.name            AS category,
    e.start_datetime,
    e.status
FROM events AS e
JOIN venues           AS v ON v.venue_id    = e.venue_id
JOIN event_categories AS c ON c.category_id = e.category_id
WHERE v.name = @venue_name
ORDER BY e.start_datetime;


-- Query 2: Find all tickets purchased by a particular user. Joins 5 tables: users + orders + order_items + ticket_types + events

SET @user_id = 204;

SELECT
    u.user_id,
    CONCAT(u.first_name, ' ', u.last_name) AS customer,
    o.order_id,
    o.order_datetime,
    e.title                                AS event,
    t.name                                 AS ticket_type,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price            AS line_total
FROM users AS u
JOIN orders       AS o  ON o.user_id         = u.user_id
JOIN order_items  AS oi ON oi.order_id       = o.order_id
JOIN ticket_types AS t  ON t.ticket_type_id  = oi.ticket_type_id
JOIN events       AS e  ON e.event_id        = t.event_id
WHERE u.user_id = @user_id
  AND o.status  = 'paid'
ORDER BY o.order_datetime, o.order_id;


-- Query 3: Calculate total tickets sold for each event. LEFT JOIN keeps events with zero sales in the list.

SELECT
    e.event_id,
    e.title,
    COALESCE(SUM(CASE WHEN o.status = 'paid' THEN oi.quantity END), 0)
        AS tickets_sold
FROM events AS e
LEFT JOIN ticket_types AS t  ON t.event_id        = e.event_id
LEFT JOIN order_items  AS oi ON oi.ticket_type_id = t.ticket_type_id
LEFT JOIN orders       AS o  ON o.order_id        = oi.order_id
GROUP BY e.event_id, e.title
ORDER BY tickets_sold DESC;


-- Query 4: Determine remaining ticket inventory for an event. Shows live inventory AND re-computes it from sales as an audit check  (the two numbers must match -> proves the data is consistent).

SET @event_id = 101;

SELECT
    e.title,
    t.name                                      AS ticket_type,
    t.price,
    t.quantity_total,
    t.quantity_total - t.quantity_available     AS sold,
    t.quantity_available                        AS remaining,
    t.quantity_total - COALESCE((
        SELECT SUM(oi.quantity)
        FROM order_items AS oi
        JOIN orders      AS o ON o.order_id = oi.order_id
        WHERE oi.ticket_type_id = t.ticket_type_id
          AND o.status = 'paid'
    ), 0)                                       AS remaining_audit
FROM ticket_types AS t
JOIN events AS e ON e.event_id = t.event_id
WHERE t.event_id = @event_id
ORDER BY t.price;


-- Query 5: Calculate total revenue for each event.

SELECT
    e.event_id,
    e.title,
    COALESCE(SUM(CASE WHEN o.status = 'paid'
                      THEN oi.quantity * oi.unit_price END), 0) AS revenue
FROM events AS e
LEFT JOIN ticket_types AS t  ON t.event_id        = e.event_id
LEFT JOIN order_items  AS oi ON oi.ticket_type_id = t.ticket_type_id
LEFT JOIN orders       AS o  ON o.order_id        = oi.order_id
GROUP BY e.event_id, e.title
ORDER BY revenue DESC;


-- Query 6: Identify the customers who have purchased the most tickets. RANK() keeps ties fair (two users with same count share a rank).

SELECT
    RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS rank_no,
    u.user_id,
    CONCAT(u.first_name, ' ', u.last_name)       AS customer,
    COUNT(DISTINCT o.order_id)                   AS orders_placed,
    SUM(oi.quantity)                             AS tickets_bought,
    SUM(oi.quantity * oi.unit_price)             AS amount_spent
FROM users AS u
JOIN orders      AS o  ON o.user_id   = u.user_id
JOIN order_items AS oi ON oi.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY u.user_id, customer
ORDER BY tickets_bought DESC, amount_spent DESC
LIMIT 5;


-- Query 7: Find events whose sales exceed a specified threshold. HAVING filters AFTER grouping (WHERE cannot see SUM()).

SET @revenue_threshold = 5000.00;

SELECT
    e.event_id,
    e.title,
    SUM(oi.quantity)                 AS tickets_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM events AS e
JOIN ticket_types AS t  ON t.event_id        = e.event_id
JOIN order_items  AS oi ON oi.ticket_type_id = t.ticket_type_id
JOIN orders       AS o  ON o.order_id        = oi.order_id
WHERE o.status = 'paid'
GROUP BY e.event_id, e.title
HAVING revenue > @revenue_threshold
ORDER BY revenue DESC;


-- Query 8: Calculate monthly ticket revenue.

SELECT
    DATE_FORMAT(o.order_datetime, '%Y-%m')  AS sales_month,
    COUNT(DISTINCT o.order_id)              AS paid_orders,
    SUM(oi.quantity)                        AS tickets_sold,
    SUM(oi.quantity * oi.unit_price)        AS revenue
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
WHERE o.status = 'paid'
GROUP BY sales_month
ORDER BY sales_month;

-- queries (admin features from the scenario)

-- Sell-through % per ticket type (monitor inventory / low stock)
SELECT
    e.title,
    t.name                                              AS ticket_type,
    t.quantity_total,
    t.quantity_available,
    ROUND(100 * (t.quantity_total - t.quantity_available)
          / t.quantity_total, 1)                        AS pct_sold
FROM ticket_types AS t
JOIN events AS e ON e.event_id = t.event_id
ORDER BY pct_sold DESC
LIMIT 10;

-- Revenue by event category (analyze event activity)
SELECT
    c.name                            AS category,
    COUNT(DISTINCT e.event_id)        AS events,
    SUM(oi.quantity)                  AS tickets_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM event_categories AS c
JOIN events       AS e  ON e.category_id     = c.category_id
JOIN ticket_types AS t  ON t.event_id        = e.event_id
JOIN order_items  AS oi ON oi.ticket_type_id = t.ticket_type_id
JOIN orders       AS o  ON o.order_id        = oi.order_id
WHERE o.status = 'paid'
GROUP BY c.name
ORDER BY revenue DESC;

-- The view the API calls for GET /events/{id}
SELECT * FROM v_event_summary WHERE event_id = 101;

-- Prove the indexes are used (EXPLAIN shows key = ix_...)
EXPLAIN
SELECT order_id, order_datetime, total_amount
FROM orders
WHERE user_id = 204
ORDER BY order_datetime DESC;
