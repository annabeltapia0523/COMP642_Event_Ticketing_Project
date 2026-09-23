-- =====================================================================
-- COMP 642 Course Project - Event Ticketing Platform
-- File 04: Least-privilege login for the Python/FastAPI app
-- Run as root ONCE. The app never uses root.
-- Change the password here AND in your local .env (never commit .env).
-- =====================================================================

CREATE USER IF NOT EXISTS 'ticket_app'@'%' IDENTIFIED BY 'ChangeMe_642!';

-- Only data read/write + calling the purchase procedure. No DROP/ALTER.
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE
    ON event_ticketing_db.* TO 'ticket_app'@'%';

FLUSH PRIVILEGES;

SHOW GRANTS FOR 'ticket_app'@'%';
