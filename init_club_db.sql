-- ClubReserve — Club Database Schema
-- Replaces init_db.sql for multi-tenant use.
-- Run once per club after creating the club database:
--   psql -U club_{shortname}_user -d club-{shortname} -f init_club_db.sql

-- -------------------------------------------------------------------------
-- Vehicles (first-class: boats OR planes)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vehicles (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(100) NOT NULL,
    vehicle_type        VARCHAR(10) NOT NULL DEFAULT 'boat' CHECK (vehicle_type IN ('boat', 'plane')),
    hull_id             VARCHAR(50),            -- HIN for boats
    registration_number VARCHAR(50),            -- N-number for planes (FAA)
    tail_number         VARCHAR(20),            -- display tail number (planes)
    current_hours       NUMERIC(10,1),          -- tracked Hobbs/tach hours
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Users
-- -------------------------------------------------------------------------

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

-- -------------------------------------------------------------------------
-- Reservations (vehicle-scoped)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reservations (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    vehicle_id  INTEGER REFERENCES vehicles(id),
    date        DATE NOT NULL,
    start_time  TIMESTAMP NOT NULL,
    end_time    TIMESTAMP NOT NULL,
    status      VARCHAR(20) DEFAULT 'active',   -- active | cancelled | pending_approval
    notes       VARCHAR(300),
    created_at  TIMESTAMP DEFAULT NOW(),
    cancelled_at TIMESTAMP
);

-- -------------------------------------------------------------------------
-- Messages
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    title           VARCHAR(200) NOT NULL,
    body            TEXT NOT NULL,
    is_announcement BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Blackout dates (vehicle-scoped or club-wide)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS blackout_dates (
    id          SERIAL PRIMARY KEY,
    vehicle_id  INTEGER REFERENCES vehicles(id), -- NULL = all vehicles
    start_time  TIMESTAMP NOT NULL,
    end_time    TIMESTAMP NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Incident reports (vehicle-scoped)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS incident_reports (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    vehicle_id  INTEGER REFERENCES vehicles(id),
    res_id      INTEGER REFERENCES reservations(id),
    report_date DATE NOT NULL,
    severity    VARCHAR(20) NOT NULL DEFAULT 'minor',
    description TEXT NOT NULL,
    resolved    BOOLEAN DEFAULT FALSE,
    resolved_by INTEGER REFERENCES users(id),
    resolved_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Fuel log (vehicle-scoped)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fuel_log (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id),
    vehicle_id       INTEGER REFERENCES vehicles(id),
    res_id           INTEGER REFERENCES reservations(id),
    log_date         DATE NOT NULL,
    gallons          NUMERIC(6,2) NOT NULL,
    price_per_gallon NUMERIC(6,3),
    total_cost       NUMERIC(8,2),
    notes            VARCHAR(300),
    created_at       TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Trip logs — renamed motor_hours_* → primary_hours_* for plane/boat parity
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trip_logs (
    id                  SERIAL PRIMARY KEY,
    res_id              INTEGER REFERENCES reservations(id) UNIQUE,
    vehicle_id          INTEGER REFERENCES vehicles(id),
    user_id             INTEGER REFERENCES users(id),
    checkout_time       TIMESTAMP NOT NULL,
    primary_hours_out   NUMERIC(8,1),          -- motor hours (boat) or Hobbs/tach (plane)
    fuel_level_out      VARCHAR(20),           -- boat only: empty|quarter|half|three_quarters|full
    condition_out       TEXT,
    checklist_items     JSONB,                 -- array of checked item indices
    checkin_time        TIMESTAMP,
    primary_hours_in    NUMERIC(8,1),
    fuel_added_gallons  NUMERIC(6,2),
    fuel_added_cost     NUMERIC(8,2),
    condition_in        TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Waitlist (vehicle-scoped)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS waitlist (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id),
    vehicle_id   INTEGER REFERENCES vehicles(id),
    desired_date DATE NOT NULL,
    notes        VARCHAR(300),
    notified     BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, vehicle_id, desired_date)
);

-- -------------------------------------------------------------------------
-- Club settings (key-value store)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS club_settings (
    key        VARCHAR(100) PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Audit log (per-club)
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    action      VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id   INTEGER,
    detail      JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Message photos
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS message_photos (
    id           SERIAL PRIMARY KEY,
    message_id   INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    photo_data   BYTEA NOT NULL,
    content_type VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
    filename     VARCHAR(200),
    uploaded_at  TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Feedback submissions
-- -------------------------------------------------------------------------

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

-- -------------------------------------------------------------------------
-- Statements
-- -------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS statements (
    id           SERIAL PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    filename     VARCHAR(200),
    file_data    BYTEA NOT NULL,
    file_size    INTEGER,
    uploaded_by  INTEGER REFERENCES users(id),
    uploaded_at  TIMESTAMP DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Indexes
-- -------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_res_date       ON reservations(date);
CREATE INDEX IF NOT EXISTS idx_res_user       ON reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_res_vehicle    ON reservations(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_res_status     ON reservations(status);
CREATE INDEX IF NOT EXISTS idx_blackout_start ON blackout_dates(start_time);
CREATE INDEX IF NOT EXISTS idx_triplog_res    ON trip_logs(res_id);
CREATE INDEX IF NOT EXISTS idx_triplog_user   ON trip_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_triplog_vehicle ON trip_logs(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_msgphoto_msg   ON message_photos(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user  ON feedback_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_time     ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_fuel_vehicle   ON fuel_log(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_incident_vehicle ON incident_reports(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_vehicle ON waitlist(vehicle_id);

-- -------------------------------------------------------------------------
-- Grant (placeholder — actual user name injected by provisioning script)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {db_user};
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {db_user};
-- -------------------------------------------------------------------------

-- -------------------------------------------------------------------------
-- Default admin account (change password immediately after first login)
-- -------------------------------------------------------------------------
INSERT INTO users (username, full_name, email, password_hash, is_admin)
VALUES (
    'admin',
    'Club Administrator',
    '',
    '$2b$12$01bbF/OdljvkfJ7nRT6amux/bmlPs/jho4JWjRANfppro9OErhKmu',  -- 'changeme'
    TRUE
)
ON CONFLICT (username) DO NOTHING;
