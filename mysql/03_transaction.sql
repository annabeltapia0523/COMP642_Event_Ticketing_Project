
-- File 03: Ticket purchase TRANSACTION (ACID demo)

-- Purchase = 5 steps that must succeed or fail TOGETHER:
--   1. Create order            (orders)
--   2. Create order item       (order_items)
--   3. Update ticket inventory (ticket_types.quantity_available)
--   4. Create payment          (payments)
--   5. Mark order paid  ->  COMMIT
-- If ANY step fails -> ROLLBACK (database goes back to the start state).

-- SELECT ... FOR UPDATE locks the ticket row, so two buyers cannot both buy "the last ticket" at the same time (no overselling).


USE event_ticketing_db;

DROP PROCEDURE IF EXISTS sp_purchase_tickets;
DROP PROCEDURE IF EXISTS sp_try_purchase;

DELIMITER //

CREATE PROCEDURE sp_purchase_tickets(
    IN  p_user_id         INT UNSIGNED,
    IN  p_ticket_type_id  INT UNSIGNED,
    IN  p_quantity        SMALLINT UNSIGNED,
    IN  p_payment_method  VARCHAR(20),
    OUT p_order_id        INT UNSIGNED
)
BEGIN
    DECLARE v_price         DECIMAL(10, 2);
    DECLARE v_available     INT UNSIGNED;
    DECLARE v_event_status  VARCHAR(20);
    DECLARE v_total         DECIMAL(10, 2);

    -- Safety net: any SQL error -> undo everything, then re-raise the error.
    -- SQLWARNING is included on purpose: in strict mode a bad ENUM value
    -- raises SQLSTATE 01000 (warning class), and with money we treat
    -- every warning as a failure.
    DECLARE EXIT HANDLER FOR SQLEXCEPTION, SQLWARNING
    BEGIN
        ROLLBACK;
        SET p_order_id = NULL;
        RESIGNAL;
    END;

    IF p_quantity IS NULL OR p_quantity = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Quantity must be at least 1';
    END IF;

    START TRANSACTION;

    -- Read price + stock AND lock this ticket row until COMMIT/ROLLBACK
    SELECT t.price, t.quantity_available, e.status
      INTO v_price, v_available, v_event_status
      FROM ticket_types AS t
      JOIN events       AS e ON e.event_id = t.event_id
     WHERE t.ticket_type_id = p_ticket_type_id
       FOR UPDATE;

    IF v_price IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ticket type does not exist';
    END IF;
    IF v_event_status <> 'scheduled' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Event is not open for sales';
    END IF;
    IF v_available < p_quantity THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Not enough tickets available';
    END IF;

    SET v_total = v_price * p_quantity;

    -- Step 1: create order (pending until payment succeeds)
    INSERT INTO orders (user_id, status, total_amount)
    VALUES (p_user_id, 'pending', v_total);
    SET p_order_id = LAST_INSERT_ID();

    -- Step 2: create order item (price copied at purchase time)
    INSERT INTO order_items (order_id, ticket_type_id, quantity, unit_price)
    VALUES (p_order_id, p_ticket_type_id, p_quantity, v_price);

    -- Step 3: update inventory
    UPDATE ticket_types
       SET quantity_available = quantity_available - p_quantity
     WHERE ticket_type_id = p_ticket_type_id;

    -- Step 4: create payment (an invalid method fails HERE -> rollback)
    INSERT INTO payments (order_id, amount, method, status, transaction_ref)
    VALUES (p_order_id, v_total, p_payment_method, 'completed',
            CONCAT('TXN-', REPLACE(UUID(), '-', '')));

    -- Step 5: mark order paid and make it permanent
    UPDATE orders SET status = 'paid' WHERE order_id = p_order_id;

    COMMIT;
END //

-- TEST wrapper: calls the purchase and REPORTS the outcome instead ofstopping the script, so the whole file runs top to bottom.
CREATE PROCEDURE sp_try_purchase(
    IN p_label           VARCHAR(60),
    IN p_user_id         INT UNSIGNED,
    IN p_ticket_type_id  INT UNSIGNED,
    IN p_quantity        SMALLINT UNSIGNED,
    IN p_payment_method  VARCHAR(20)
)
BEGIN
    DECLARE v_error     TEXT DEFAULT NULL;
    DECLARE v_order_id  INT UNSIGNED DEFAULT NULL;
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION, SQLWARNING
        GET DIAGNOSTICS CONDITION 1 v_error = MESSAGE_TEXT;

    CALL sp_purchase_tickets(p_user_id, p_ticket_type_id, p_quantity,
                             p_payment_method, v_order_id);

    SELECT p_label                                        AS test_case,
           IF(v_error IS NULL, 'COMMIT', 'ROLLBACK')      AS outcome,
           v_order_id                                     AS new_order_id,
           COALESCE(v_error, 'All 5 steps succeeded')     AS message;
END //

DELIMITER ;

-- =====================================================================
-- TESTING  (ticket_type_id 1 = "Early Bird" for event 101)

-- A. BEFORE snapshot
SELECT 'BEFORE' AS moment,
       (SELECT quantity_available FROM ticket_types WHERE ticket_type_id = 1) AS early_bird_left,
       (SELECT COUNT(*) FROM orders)      AS orders,
       (SELECT COUNT(*) FROM order_items) AS order_items,
       (SELECT COUNT(*) FROM payments)    AS payments;

-- B. SUCCESS: user 204 buys 2 Early Bird tickets
CALL sp_try_purchase('1. Valid purchase', 204, 1, 2, 'credit_card');

-- C. FAIL early: asks for more tickets than exist (nothing written yet)
CALL sp_try_purchase('2. Oversell attempt', 209, 1, 5000, 'paypal');

-- D. FAIL late: order + item + inventory already written, then the payment insert fails (bad method). ROLLBACK must undo steps 1-3.
CALL sp_try_purchase('3. Payment fails at step 4', 211, 1, 3, 'bitcoin');

-- E. FAIL: user does not exist (foreign key violation)
CALL sp_try_purchase('4. Unknown user', 99999, 1, 1, 'credit_card');

-- F. AFTER snapshot: only test 1 changed the data (early_bird_left -2, orders +1, order_items +1, payments +1)
SELECT 'AFTER' AS moment,
       (SELECT quantity_available FROM ticket_types WHERE ticket_type_id = 1) AS early_bird_left,
       (SELECT COUNT(*) FROM orders)      AS orders,
       (SELECT COUNT(*) FROM order_items) AS order_items,
       (SELECT COUNT(*) FROM payments)    AS payments;

-- G. The committed order, end to end
SELECT o.order_id, o.user_id, o.status, o.total_amount,
       oi.ticket_type_id, oi.quantity, oi.unit_price,
       p.method, p.status AS payment_status, p.transaction_ref
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN payments    AS p  ON p.order_id  = o.order_id
ORDER BY o.order_id DESC
LIMIT 1;
