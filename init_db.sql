-- Bentley Boat Club — Database Schema
-- Run once after creating the database:
--   psql -U bentley_user -d bentley_boat -f init_db.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(100),
    password_hash VARCHAR(255) NOT NULL,
    is_admin      BOOLEAN DEFAULT FALSE,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reservations (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id),
    date         DATE NOT NULL,          -- calendar date of start_time (for consecutive-day checks)
    start_time   TIMESTAMP NOT NULL,
    end_time     TIMESTAMP NOT NULL,
    status       VARCHAR(20) DEFAULT 'active',  -- active | cancelled
    created_at   TIMESTAMP DEFAULT NOW(),
    cancelled_at TIMESTAMP
    -- No UNIQUE(date): multiple non-overlapping slots per day are allowed.
    -- Overlap enforcement is done at the application layer.
);

CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    title           VARCHAR(200) NOT NULL,
    body            TEXT NOT NULL,
    is_announcement BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_res_date   ON reservations(date);
CREATE INDEX IF NOT EXISTS idx_res_user   ON reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_res_status ON reservations(status);

-- First admin account: username=admin, password=changeme
-- CHANGE THIS PASSWORD immediately after first login via Admin > Reset Password
INSERT INTO users (username, full_name, email, password_hash, is_admin)
VALUES (
    'admin',
    'Club Administrator',
    '',
    '$2b$12$01bbF/OdljvkfJ7nRT6amux/bmlPs/jho4JWjRANfppro9OErhKmu',  -- 'changeme'
    TRUE
)
ON CONFLICT (username) DO NOTHING;
