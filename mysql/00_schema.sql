
DROP DATABASE IF EXISTS event_ticketing_db;
CREATE DATABASE event_ticketing_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE event_ticketing_db;


-- 1. users : customers and administrators

CREATE TABLE users (
    user_id        INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    email          VARCHAR(255)  NOT NULL,
    password_hash  CHAR(60)      NOT NULL,          -- bcrypt hash, never plain text
    first_name     VARCHAR(50)   NOT NULL,
    last_name      VARCHAR(50)   NOT NULL,
    phone          VARCHAR(20)   NULL,
    role           ENUM('customer', 'admin') NOT NULL DEFAULT 'customer',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_users        PRIMARY KEY (user_id),
    CONSTRAINT uq_users_email  UNIQUE (email)
) ENGINE = InnoDB;


-- 2. venues : physical places where events happen

CREATE TABLE venues (
    venue_id       INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    name           VARCHAR(120)  NOT NULL,
    address        VARCHAR(200)  NOT NULL,
    city           VARCHAR(80)   NOT NULL,
    state          CHAR(2)       NOT NULL,
    capacity       INT UNSIGNED  NOT NULL,

    CONSTRAINT pk_venues            PRIMARY KEY (venue_id),
    CONSTRAINT uq_venues_name_city  UNIQUE (name, city),
    CONSTRAINT ck_venues_capacity   CHECK (capacity > 0)
) ENGINE = InnoDB;


-- 3. event_categories : lookup table (Concert, Conference, ...)  Names match MongoDB event_content.eventType exactly.

CREATE TABLE event_categories (
    category_id    TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name           VARCHAR(50)      NOT NULL,

    CONSTRAINT pk_event_categories       PRIMARY KEY (category_id),
    CONSTRAINT uq_event_categories_name  UNIQUE (name)
) ENGINE = InnoDB;


-- 4. events : one row per event (core, structured facts only)  Venue 1 --< Events,  Category 1 --< Events,  Admin 1 --< Events

CREATE TABLE events (
    event_id        INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    venue_id        INT UNSIGNED     NOT NULL,
    category_id     TINYINT UNSIGNED NOT NULL,
    created_by      INT UNSIGNED     NOT NULL,       -- admin who created it
    title           VARCHAR(150)     NOT NULL,
    start_datetime  DATETIME         NOT NULL,
    end_datetime    DATETIME         NOT NULL,
    status          ENUM('scheduled', 'cancelled', 'completed')
                                     NOT NULL DEFAULT 'scheduled',
    created_at      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT pk_events PRIMARY KEY (event_id),
    -- a venue cannot host two events that start at the same moment
    CONSTRAINT uq_events_venue_start UNIQUE (venue_id, start_datetime),
    CONSTRAINT ck_events_time_order  CHECK (end_datetime > start_datetime),
    CONSTRAINT fk_events_venue
        FOREIGN KEY (venue_id)    REFERENCES venues (venue_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_events_category
        FOREIGN KEY (category_id) REFERENCES event_categories (category_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_events_created_by
        FOREIGN KEY (created_by)  REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE INDEX ix_events_start_datetime ON events (start_datetime);
CREATE INDEX ix_events_category       ON events (category_id);


-- 5. ticket_types : price tiers per event (General, VIP, Student, ...)  quantity_available is the LIVE inventory the transaction updates.

CREATE TABLE ticket_types (
    ticket_type_id      INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    event_id            INT UNSIGNED   NOT NULL,
    name                VARCHAR(50)    NOT NULL,
    price               DECIMAL(10, 2) NOT NULL,
    quantity_total      INT UNSIGNED   NOT NULL,
    quantity_available  INT UNSIGNED   NOT NULL,

    CONSTRAINT pk_ticket_types             PRIMARY KEY (ticket_type_id),
    CONSTRAINT uq_ticket_types_event_name  UNIQUE (event_id, name),
    CONSTRAINT ck_ticket_types_price       CHECK (price >= 0),
    CONSTRAINT ck_ticket_types_inventory
        CHECK (quantity_available <= quantity_total),
    CONSTRAINT fk_ticket_types_event
        FOREIGN KEY (event_id) REFERENCES events (event_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;


-- 6. orders : one checkout by one user.  User 1 --< Orders

CREATE TABLE orders (
    order_id        INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    user_id         INT UNSIGNED   NOT NULL,
    order_datetime  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status          ENUM('pending', 'paid', 'cancelled', 'refunded')
                                   NOT NULL DEFAULT 'pending',
    total_amount    DECIMAL(10, 2) NOT NULL DEFAULT 0.00,

    CONSTRAINT pk_orders        PRIMARY KEY (order_id),
    CONSTRAINT ck_orders_total  CHECK (total_amount >= 0),
    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

-- "orders of user X, newest first" and "revenue by month"
CREATE INDEX ix_orders_user_datetime   ON orders (user_id, order_datetime);
CREATE INDEX ix_orders_status_datetime ON orders (status, order_datetime);


-- 7. order_items : BRIDGE table -> MANY-TO-MANY between orders and ticket_types (one order holds many ticket types, one ticket type appears in many orders).unit_price is copied at purchase time so later price changes never rewrite history.

CREATE TABLE order_items (
    order_item_id   INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    order_id        INT UNSIGNED      NOT NULL,
    ticket_type_id  INT UNSIGNED      NOT NULL,
    quantity        SMALLINT UNSIGNED NOT NULL,
    unit_price      DECIMAL(10, 2)    NOT NULL,

    CONSTRAINT pk_order_items            PRIMARY KEY (order_item_id),
    CONSTRAINT uq_order_items_order_type UNIQUE (order_id, ticket_type_id),
    CONSTRAINT ck_order_items_quantity   CHECK (quantity > 0),
    CONSTRAINT ck_order_items_price      CHECK (unit_price >= 0),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)       REFERENCES orders (order_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_order_items_ticket_type
        FOREIGN KEY (ticket_type_id) REFERENCES ticket_types (ticket_type_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE INDEX ix_order_items_ticket_type ON order_items (ticket_type_id);


-- 8. payments : one payment per order (1 : 1, enforced by UNIQUE)

CREATE TABLE payments (
    payment_id       INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    order_id         INT UNSIGNED   NOT NULL,
    amount           DECIMAL(10, 2) NOT NULL,
    method           ENUM('credit_card', 'debit_card', 'paypal', 'apple_pay')
                                    NOT NULL,
    status           ENUM('pending', 'completed', 'failed', 'refunded')
                                    NOT NULL DEFAULT 'pending',
    transaction_ref  VARCHAR(40)    NOT NULL,       -- id from payment gateway
    paid_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_payments           PRIMARY KEY (payment_id),
    CONSTRAINT uq_payments_order     UNIQUE (order_id),
    CONSTRAINT uq_payments_txn_ref   UNIQUE (transaction_ref),
    CONSTRAINT ck_payments_amount    CHECK (amount >= 0),
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

CREATE INDEX ix_payments_status_paid_at ON payments (status, paid_at);


-- 9. View used by the API for GET /events/{id} (the "MySQL half" of the cross-database response)


CREATE VIEW v_event_summary AS
SELECT
    e.event_id,
    e.title,
    c.name                       AS category,
    e.start_datetime,
    e.end_datetime,
    e.status,
    v.venue_id,
    v.name                       AS venue_name,
    v.city                       AS venue_city,
    v.state                      AS venue_state,
    MIN(t.price)                 AS price_from,
    MAX(t.price)                 AS price_to,
    CAST(SUM(t.quantity_total)     AS UNSIGNED) AS tickets_total,
    CAST(SUM(t.quantity_available) AS UNSIGNED) AS tickets_available
FROM events AS e
JOIN venues           AS v ON v.venue_id    = e.venue_id
JOIN event_categories AS c ON c.category_id = e.category_id
LEFT JOIN ticket_types AS t ON t.event_id   = e.event_id
GROUP BY
    e.event_id, e.title, c.name, e.start_datetime, e.end_datetime,
    e.status, v.venue_id, v.name, v.city, v.state;
-- Quick check
SHOW TABLES;
