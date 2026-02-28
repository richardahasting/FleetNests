# ClubReserve

A multi-tenant reservation platform for boat and flying clubs. One Flask application
serves any number of clubs, each with full isolation — separate PostgreSQL database,
subdomain routing, and configurable vehicle type (boat or plane).

---

## Features

- **Reservation calendar** — FullCalendar UI with overlap enforcement, blackout dates, and pending-approval workflow
- **Vehicle types** — Boat mode (fuel level buttons, NWS marine weather, Motor Hours) and Plane mode (FAA METAR weather, Hobbs Hours, fuel quantity required on return)
- **Trip check-out / check-in** — Pre-departure captain's checklist, departure/return time, engine hours, fuel logging
- **Waitlist** — Auto-notification when a cancelled slot opens
- **Weather alerts** — NWS API integration (boat: zone/county alerts; plane: METAR), daily 6 AM cron
- **Trip reminders** — Daily 6 PM email cron for upcoming reservations
- **Fuel log & statistics** — Per-trip fuel records, aggregated reporting
- **Incident / damage reports** — Structured reports with admin review
- **Message board** — Posts with photo attachments
- **Family accounts** — Two logins sharing one reservation slot
- **iCal feed** — Personal token-based calendar subscription
- **AI-routed member feedback** — Routes feedback to GitHub issues (bugs) or email (other)
- **Monthly PDF statements** — Upload and per-member access control
- **Audit log** — Tracks all admin actions
- **Admin dashboard** — User management, blackouts, approvals, CSV export, trip logs
- **Super-admin panel** — Club provisioning, activation/deactivation across all tenants

---

## Architecture

### Two-Database Tier

| Service | Port | Database | Purpose |
|---------|------|----------|---------|
| `db-master` | 5433 | `clubreserve_master` | Club registry, super-admins, vehicle templates |
| `db-clubs` | 5434 | `club-<shortname>` (one per club) | All per-club data |

### Per-Request Club Resolution

`club_resolver.py` runs as a Flask `before_request` hook:

1. Extracts the subdomain from the incoming request (`bentley.clubreserve.com` → `bentley`)
2. Looks up the club in `clubreserve_master`
3. Stores the club record and its DSN on Flask `g`

`CLUB_SHORT_NAME` env var bypasses subdomain lookup for local dev.

`/superadmin` paths skip club resolution entirely and authenticate against the master database.

### Per-Request DSN Switching

`db.py` reads `g.club_dsn` on every query, so each request talks to the correct club's
PostgreSQL database. Falls back to `DATABASE_URL` for single-club / legacy mode.

### Vehicle Types

All vehicle-type behaviour lives in `vehicle_types.py`. The `build_checkout_context()`
function returns the correct constants (fuel level buttons, weather source, hours label,
contact phone label, checklist items) for the current club's vehicle type.

---

## Quick Start (Docker)

```bash
git clone https://github.com/richardahasting/bentley-boat.git ClubReserve
cd ClubReserve
cp .env.example .env        # fill in all values before proceeding
docker compose up -d
```

On first start:
- `db-master` auto-runs `init_master_db.sql` — creates the master schema and seeds a default super-admin
- `db-clubs` starts empty; clubs are provisioned at runtime via the super-admin panel

> **⚠️ Security**: Change all `changeme-*` passwords in `.env` and the default super-admin
> credentials before any real deployment.

### Provision Your First Club

1. Log in at `/superadmin` (default credentials set in `init_master_db.sql`)
2. Create a new club — choose short name (used for subdomain and DB name) and vehicle type
3. Add `DB_PASS_CLUB_<SHORTNAME>_USER=<password>` to `.env` and restart `web`
4. Navigate to `<shortname>.yourdomain.com` and log in as the club admin

### Local Dev (Single Club)

```bash
# Skip subdomain routing — always use the "bentley" club
CLUB_SHORT_NAME=bentley python app.py
```

---

## Environment Variables

### Database

| Variable | Required | Description |
|----------|----------|-------------|
| `MASTER_DATABASE_URL` | **Yes** | DSN for `clubreserve_master` (club registry) |
| `MASTER_DB_PASSWORD` | Docker | Password for master DB (used in compose) |
| `PG_HOST` | **Yes** | Host of the clubs PostgreSQL instance |
| `PG_PORT` | No (5434) | Port of the clubs PostgreSQL instance |
| `PG_SUPERUSER` | **Yes** | Superuser on clubs DB (used to create new club DBs) |
| `PG_SUPERUSER_PASSWORD` | **Yes** | Password for `PG_SUPERUSER` |
| `DB_PASS_CLUB_<UPPER>_USER` | Per club | Password for each club's DB user |
| `CLUB_SHORT_NAME` | Dev only | Bypass subdomain routing; always use this club |
| `DATABASE_URL` | Legacy | Single-club fallback if master DB not configured |

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | **Yes** | — | Flask session secret |
| `APP_PREFIX` | No | `/` | URL prefix when mounted under a path |
| `SESSION_COOKIE_SECURE` | No | `true` | Set `false` for local HTTP dev |

### Email

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_ENABLED` | No | `false` | Enable outbound email |
| `EMAIL_FROM` | No | `noreply@myclub.com` | Sender address |
| `SMTP_HOST` | No | `localhost` | Mail server |
| `SMTP_PORT` | No | `25` | Mail server port |
| `SMTP_USER` | No | — | SMTP username (if auth required) |
| `SMTP_PASS` | No | — | SMTP password |
| `APP_URL` | No | — | Base URL embedded in email links |

### Integrations

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables AI feedback routing |
| `GITHUB_TOKEN` | No | PAT for filing bug-report issues (Issues: Read+Write) |
| `GITHUB_REPO` | No | Target repo for bug reports (`owner/repo`) |
| `FEEDBACK_EMAIL` | No | Destination for non-bug feedback |

---

## Project Structure

```
ClubReserve/
├── app.py              # Flask routes and view logic (1,244 lines)
├── models.py           # Per-club DB query layer / business logic (1,018 lines)
├── auth.py             # Session auth, login_required, superadmin_required (170 lines)
├── db.py               # Per-request DSN-switching PostgreSQL wrapper (105 lines)
├── club_resolver.py    # before_request hook: subdomain → club record + DSN (132 lines)
├── master_db.py        # Master DB query layer (clubs registry, super-admins) (166 lines)
├── master_models.py    # provision_club() workflow (200 lines)
├── vehicle_types.py    # Boat / plane constants and checkout context builder (184 lines)
├── email_notify.py     # Email notification helpers (256 lines)
├── weather.py          # NWS / METAR alert fetching (170 lines)
├── weather_check.py    # Daily weather alert cron script
├── trip_reminder.py    # Evening reservation reminder cron script
├── feedback.py         # AI-routed member feedback
├── init_master_db.sql  # Master DB schema (clubs, super_admins, vehicle_templates)
├── init_club_db.sql    # Per-club DB schema (replaces legacy init_db.sql)
├── gunicorn.conf.py    # Server config (bind :5210, 2 workers)
├── docker-compose.yml  # db-master + db-clubs + web services
├── Dockerfile          # Python 3.12-slim image
├── requirements.txt    # Python dependencies
├── templates/          # Jinja2 templates
│   ├── superadmin/     # Super-admin panel templates (separate base, no club branding)
│   └── admin/          # Club-admin templates
└── static/             # CSS, JS, uploaded photos
```

---

## Database Schema

### Master DB (`clubreserve_master`)

| Table | Purpose |
|-------|---------|
| `clubs` | Club registry: short name, display name, vehicle type, DSN template, active flag |
| `super_admins` | Platform-level admin accounts (bcrypt) |
| `vehicle_templates` | Default checklist items per vehicle type |

### Per-Club DB (`club-<shortname>`)

| Table | Purpose |
|-------|---------|
| `users` | Member accounts, roles, family links, per-member limits |
| `vehicles` | Club vehicles (boat or plane) |
| `reservations` | All booking records — `active`, `cancelled`, `pending_approval` |
| `blackout_dates` | Admin-defined ranges that block reservations (per-vehicle or global) |
| `trip_logs` | Check-out / check-in records with checklist data, engine hours, fuel |
| `fuel_log` | Per-trip fuel records |
| `waitlist` | Queue entries with auto-notify on cancellation |
| `incident_reports` | Damage / incident reports |
| `messages` | Message board posts |
| `message_photos` | Photo attachments |
| `feedback_submissions` | Member feedback before AI routing |
| `statements` | Monthly PDF statement uploads with per-member visibility |
| `audit_log` | Admin action history |
| `club_settings` | Key/value store for per-club configuration |
| `ical_tokens` | Personal tokens for iCal feed subscriptions |

---

## Key Business Rules

- Reservations: 2–6 hours, 30-minute intervals, up to 60 days ahead
- No overlap with existing bookings (`active` or `pending_approval`) or blackout dates
- Per-member limits: consecutive days and total pending reservations (configurable)
- Family accounts: two login credentials sharing one reservation slot
- Overlap check is enforced at the database level (table lock + atomic insert) to prevent race conditions
- A day is "fully booked" only when no 2-hour gap remains; partial bookings show remaining availability

---

## Cron Jobs

```cron
# Weather alerts — 6 AM daily
0  6 * * *  /usr/bin/python3 /path/to/weather_check.py  >> /var/log/clubreserve-weather.log 2>&1

# Trip reminders — 6 PM daily
0 18 * * *  /usr/bin/python3 /path/to/trip_reminder.py  >> /var/log/clubreserve-reminder.log 2>&1
```

Both scripts load `.env` via `python-dotenv` and connect directly to PostgreSQL.

---

## Bare-Metal / Systemd Deployment

```bash
pip install -r requirements.txt
cp .env.example .env && vim .env

# Initialize master DB (clubs registry, super-admin)
psql "$MASTER_DATABASE_URL" -f init_master_db.sql

# Run directly
gunicorn --config gunicorn.conf.py app:app
```

Nginx should proxy to `http://127.0.0.1:5210`. For multi-tenant subdomain routing,
configure a wildcard DNS record (`*.clubreserve.com → server IP`) and a wildcard
`server_name` in Nginx.
