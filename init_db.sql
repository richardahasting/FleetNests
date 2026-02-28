-- FleetNests — Database Schema
-- Run once after creating the database:
--   psql -U bentley_user -d bentley_boat -f init_db.sql

CREATE TABLE IF NOT EXISTS users (
    id                     SERIAL PRIMARY KEY,
    username               VARCHAR(50) UNIQUE NOT NULL,
    full_name              VARCHAR(100) NOT NULL,
    email                  VARCHAR(100),
    password_hash          VARCHAR(255) NOT NULL,
    is_admin               BOOLEAN DEFAULT FALSE,
    is_active              BOOLEAN DEFAULT TRUE,
    max_consecutive_days   INTEGER DEFAULT 3,
    max_pending            INTEGER DEFAULT 7,
    ical_token             VARCHAR(64) UNIQUE,
    phone                  VARCHAR(20),
    pending_email          VARCHAR(100),
    email_verify_token     VARCHAR(64) UNIQUE,
    email_verify_expires   TIMESTAMP,
    avatar                 BYTEA,
    avatar_content_type    VARCHAR(50),
    password_reset_token   VARCHAR(64) UNIQUE,
    password_reset_expires TIMESTAMP,
    display_name           VARCHAR(100),
    family_account_id      INTEGER REFERENCES users(id),
    email2                 VARCHAR(100),
    password_hash2         VARCHAR(255),
    can_manage_statements  BOOLEAN DEFAULT FALSE,
    created_at             TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reservations (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id),
    date         DATE NOT NULL,          -- calendar date of start_time (for consecutive-day checks)
    start_time   TIMESTAMP NOT NULL,
    end_time     TIMESTAMP NOT NULL,
    status       VARCHAR(20) DEFAULT 'active',  -- active | cancelled
    notes        VARCHAR(300),
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

CREATE TABLE IF NOT EXISTS blackout_dates (
    id          SERIAL PRIMARY KEY,
    start_time  TIMESTAMP NOT NULL,
    end_time    TIMESTAMP NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incident_reports (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    res_id      INTEGER REFERENCES reservations(id),
    report_date DATE NOT NULL,
    severity    VARCHAR(20) NOT NULL DEFAULT 'minor',
    description TEXT NOT NULL,
    resolved    BOOLEAN DEFAULT FALSE,
    resolved_by INTEGER REFERENCES users(id),
    resolved_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fuel_log (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id),
    res_id           INTEGER REFERENCES reservations(id),
    log_date         DATE NOT NULL,
    gallons          NUMERIC(6,2) NOT NULL,
    price_per_gallon NUMERIC(6,3),
    total_cost       NUMERIC(8,2),
    notes            VARCHAR(300),
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trip_logs (
    id                  SERIAL PRIMARY KEY,
    res_id              INTEGER REFERENCES reservations(id) UNIQUE,
    user_id             INTEGER REFERENCES users(id),
    checkout_time       TIMESTAMP NOT NULL,
    motor_hours_out     NUMERIC(8,1),
    fuel_level_out      VARCHAR(20),   -- empty|quarter|half|three_quarters|full
    condition_out       TEXT,
    checklist_items     JSONB,         -- array of checked item indices, e.g. [0,1,3,5]
    checkin_time        TIMESTAMP,
    motor_hours_in      NUMERIC(8,1),
    fuel_added_gallons  NUMERIC(6,2),
    fuel_added_cost     NUMERIC(8,2),
    condition_in        TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS waitlist (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id),
    desired_date DATE NOT NULL,
    notes        VARCHAR(300),
    notified     BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, desired_date)
);

CREATE INDEX IF NOT EXISTS idx_res_date       ON reservations(date);
CREATE INDEX IF NOT EXISTS idx_res_user       ON reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_res_status     ON reservations(status);
CREATE INDEX IF NOT EXISTS idx_blackout_start ON blackout_dates(start_time);
CREATE INDEX IF NOT EXISTS idx_triplog_res    ON trip_logs(res_id);
CREATE INDEX IF NOT EXISTS idx_triplog_user   ON trip_logs(user_id);

CREATE TABLE IF NOT EXISTS message_photos (
    id           SERIAL PRIMARY KEY,
    message_id   INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    photo_data   BYTEA NOT NULL,
    content_type VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
    filename     VARCHAR(200),
    uploaded_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_msgphoto_msg ON message_photos(message_id);

CREATE TABLE IF NOT EXISTS feedback_submissions (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id),
    submitted_at     TIMESTAMP DEFAULT NOW(),
    text             TEXT NOT NULL,
    attachment_path  VARCHAR(300),
    attachment_name  VARCHAR(200),
    attachment_type  VARCHAR(100),
    routed_to        VARCHAR(30),
    github_issue_url VARCHAR(300)
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback_submissions(user_id);

-- Grant app user access to all tables and sequences
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bentley_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bentley_user;

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
