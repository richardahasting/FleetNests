# FleetNests — System Documentation

Complete technical reference for the FleetNests multi-tenant reservation platform.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Database Schema Reference](#2-database-schema-reference)
3. [Route Reference](#3-route-reference)
4. [Module Reference](#4-module-reference)
5. [Club Settings Reference](#5-club-settings-reference)
6. [Per-Club Theming & Branding](#6-per-club-theming--branding)
7. [Maintenance Tracking](#7-maintenance-tracking)
8. [Vehicle Types (Boat vs Plane)](#8-vehicle-types-boat-vs-plane)
9. [Authentication & Authorization](#9-authentication--authorization)
10. [Email Notifications](#10-email-notifications)
11. [Weather Integration](#11-weather-integration)
12. [AI Feedback Routing](#12-ai-feedback-routing)
13. [Deployment Reference](#13-deployment-reference)
14. [Demo Sites (sample1 / sample2)](#14-demo-sites-sample1--sample2)

---

## 1. Architecture Overview

### Request Lifecycle

```
Browser → Nginx → Gunicorn → Flask
                              ├── club_resolver.before_request()
                              │     ├── Extract short_name (subdomain or X-Club-Short-Name header)
                              │     ├── Fetch club row from fleetnests_master
                              │     └── Set g.club, g.vehicle_type, g.club_dsn
                              ├── context_processor inject_context()
                              │     ├── auth.current_user()
                              │     ├── models.get_all_club_settings()
                              │     └── models.get_branding()  (boolean flags only, no binary)
                              └── Route handler
                                    ├── db.execute() / db.fetchone()  (uses g.club_dsn)
                                    └── render_template()
```

### Multi-Tenancy

- Each club gets its own PostgreSQL database (`fn_<shortname>`) with its own user.
- The master database (`fleetnests_master`) stores the club registry only.
- `db.py` switches DSN on every query by reading `flask.g.club_dsn`.
- Templates receive `club`, `branding`, `club_settings`, and `current_user` via the context processor — no per-route injection needed.

### URL Structure

In production each club is a subdomain: `bentley.fleetnests.com`.

For path-mounted deployments (e.g., `fleetnests.com/sample1`), Nginx sets
`X-Forwarded-Prefix: /sample1` and `X-Club-Short-Name: sample1`. ProxyFix + club_resolver
handle this transparently; `url_for()` generates correctly prefixed URLs.

---

## 2. Database Schema Reference

### Master DB (`fleetnests_master`)

#### `clubs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `short_name` | VARCHAR(50) UNIQUE | Subdomain / DB name fragment |
| `name` | VARCHAR(100) | Display name |
| `vehicle_type` | VARCHAR(10) | `'boat'` or `'plane'` |
| `dsn_template` | TEXT | Connection string (populated by provisioning) |
| `is_active` | BOOLEAN | Inactive clubs return 403 |
| `contact_email` | VARCHAR(100) | Used in email footers |
| `timezone` | VARCHAR(50) | e.g. `America/Chicago` |

#### `super_admins`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | |
| `username` | VARCHAR(50) UNIQUE | Login name |
| `password_hash` | VARCHAR(255) | bcrypt |
| `is_active` | BOOLEAN | |

#### `vehicle_templates`

Default checklist items seeded per vehicle type (used during club provisioning).

---

### Per-Club DB (`fn_<shortname>`)

#### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `username` | VARCHAR(50) UNIQUE | |
| `full_name` | VARCHAR(100) | |
| `display_name` | VARCHAR(100) | Public name shown on calendar (default: "The X family") |
| `email` | VARCHAR(100) | Primary login email |
| `email2` | VARCHAR(100) | Family sub-account email |
| `password_hash` | VARCHAR(255) | bcrypt for primary |
| `password_hash2` | VARCHAR(255) | bcrypt for family sub-account |
| `is_admin` | BOOLEAN | Club admin flag |
| `is_active` | BOOLEAN | |
| `max_consecutive_days` | INTEGER | Default 3 |
| `max_pending` | INTEGER | Max active+pending reservations |
| `family_account_id` | INTEGER FK → users | Sub-account points to primary |
| `ical_token` | VARCHAR(64) UNIQUE | Personal iCal feed auth |
| `phone` | VARCHAR(20) | |
| `pending_email` / `email_verify_token` | | Email-change verification |
| `avatar` / `avatar_content_type` | BYTEA | Profile photo |
| `password_reset_token` / `password_reset_expires` | | Password reset flow |
| `can_manage_statements` | BOOLEAN | Allows statement uploads without full admin |

#### `vehicles`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `name` | VARCHAR(100) | Display name |
| `vehicle_type` | VARCHAR(10) | `'boat'` or `'plane'` |
| `hull_id` | VARCHAR(50) | HIN (boats) |
| `registration_number` | VARCHAR(50) | N-number (planes) |
| `tail_number` | VARCHAR(20) | Display tail number |
| `current_hours` | NUMERIC(10,1) | Hobbs / tach hours (updated from trip logs) |
| `is_active` | BOOLEAN | |

#### `reservations`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` | INTEGER FK → users | |
| `vehicle_id` | INTEGER FK → vehicles | |
| `date` | DATE | Calendar date |
| `start_time` | TIMESTAMP | Naive (stored in club timezone) |
| `end_time` | TIMESTAMP | |
| `status` | VARCHAR(20) | `active` \| `cancelled` \| `pending_approval` |
| `notes` | VARCHAR(300) | Optional member note |
| `cancelled_at` | TIMESTAMP | |

#### `blackout_dates`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `vehicle_id` | INTEGER FK | NULL = affects all vehicles |
| `start_time` | TIMESTAMP | |
| `end_time` | TIMESTAMP | |
| `reason` | VARCHAR(200) | Shown on calendar |
| `created_by` | INTEGER FK → users | |

#### `trip_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `res_id` | INTEGER FK UNIQUE → reservations | |
| `vehicle_id` / `user_id` | INTEGER FK | |
| `checkout_time` | TIMESTAMP | |
| `primary_hours_out` | NUMERIC(8,1) | Hobbs/tach at departure |
| `fuel_level_out` | VARCHAR(20) | Boat: `empty` \| `quarter` \| `half` \| `three_quarters` \| `full` |
| `condition_out` | TEXT | Pre-departure notes |
| `checklist_items` | JSONB | Array of checked item indices |
| `checkin_time` | TIMESTAMP | |
| `primary_hours_in` | NUMERIC(8,1) | Hobbs/tach at return |
| `fuel_added_gallons` | NUMERIC(6,2) | |
| `fuel_added_cost` | NUMERIC(8,2) | |
| `condition_in` | TEXT | Post-trip notes |

#### `fuel_log`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` / `vehicle_id` / `res_id` | FK | |
| `log_date` | DATE | |
| `gallons` | NUMERIC(6,2) | |
| `price_per_gallon` / `total_cost` | NUMERIC | |
| `notes` | VARCHAR(300) | |

#### `maintenance_records`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `vehicle_id` | INTEGER FK → vehicles | |
| `performed_by` | VARCHAR(100) | Mechanic / shop name |
| `performed_at` | DATE | Date of service |
| `category` | VARCHAR(50) | `general` \| `engine` \| `hull` \| `electrical` \| `safety` \| `annual_inspection` \| `avionics` \| `fuel_system` \| `cooling` \| `rigging` \| `propeller` \| `airframe` \| `other` |
| `description` | TEXT | What was done |
| `hours_at_service` | NUMERIC(8,1) | Hobbs/tach reading at time of service |
| `cost` | NUMERIC(10,2) | |
| `notes` | TEXT | Additional notes |
| `created_by` | INTEGER FK → users | Admin who logged the record |
| `created_at` | TIMESTAMP | |

#### `maintenance_schedules`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `vehicle_id` | INTEGER FK → vehicles | |
| `task_name` | VARCHAR(100) | e.g. "Annual Inspection" |
| `category` | VARCHAR(50) | Same as maintenance_records |
| `description` | TEXT | |
| `interval_months` | INTEGER | Calendar recurrence (NULL = hours-only) |
| `interval_hours` | NUMERIC(8,1) | Hours recurrence (NULL = calendar-only) |
| `last_performed_at` | DATE | Updated when marked done |
| `last_performed_hours` | NUMERIC(8,1) | Updated when marked done |
| `next_due_date` | DATE | Computed from last_performed_at + interval_months |
| `next_due_hours` | NUMERIC(8,1) | Computed from last_performed_hours + interval_hours |
| `priority` | VARCHAR(10) | `low` \| `normal` \| `high` |
| `is_active` | BOOLEAN | Soft-delete |
| `created_at` | TIMESTAMP | |

**Overdue logic**: A schedule is overdue when `next_due_date <= today` OR (`vehicle.current_hours >= next_due_hours` when both are set).

#### `club_settings`

Key/value store. See [Club Settings Reference](#5-club-settings-reference).

#### `club_branding`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | Always exactly one row |
| `primary_color` | VARCHAR(7) | Hex color, default `#0A2342` |
| `accent_color` | VARCHAR(7) | Hex color, default `#C9A84C` |
| `logo_data` | BYTEA | Club logo image |
| `logo_content_type` | VARCHAR(50) | MIME type |
| `hero_data` | BYTEA | Hero banner image |
| `hero_content_type` | VARCHAR(50) | |

**Note**: `get_branding()` returns only boolean flags (`has_logo`, `has_hero`) — never binary data — to avoid loading 100KB+ on every request. Binary data is fetched only by the image-serving routes.

#### `club_photos` / `vehicle_photos` / `message_photos`

Standard photo tables with `BYTEA photo_data`, `content_type`, `uploaded_at`.

#### `waitlist`

Unique per `(user_id, vehicle_id, desired_date)`. Notified entries are flagged `notified=TRUE` but not deleted.

#### `incident_reports`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` / `vehicle_id` / `res_id` | FK | |
| `report_date` | DATE | |
| `severity` | VARCHAR(20) | `minor` \| `moderate` \| `major` |
| `description` | TEXT | |
| `resolved` | BOOLEAN | |
| `resolved_by` / `resolved_at` | | |

#### `audit_log`

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `user_id` | FK → users | |
| `action` | VARCHAR(100) | Snake-case verb, e.g. `reservation_created` |
| `target_type` | VARCHAR(50) | e.g. `vehicle`, `reservation` |
| `target_id` | INTEGER | |
| `detail` | JSONB | Arbitrary context |
| `created_at` | TIMESTAMP | |

---

## 3. Route Reference

### Public / Auth

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET/POST | `/login` | `login` | Login page (demo clubs: email-only) |
| GET | `/logout` | `logout` | Clear session |
| GET/POST | `/forgot-password` | `forgot_password` | Request reset link |
| GET/POST | `/set-password/<token>` | `set_password` | Set password via reset token |
| GET | `/verify-email/<token>` | `verify_email` | Confirm pending email change |

### Member-Facing

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/` | `index` | Redirects to `/calendar` |
| GET | `/calendar` | `calendar` | FullCalendar reservation view |
| GET | `/api/reservations` | `api_reservations` | JSON event feed for FullCalendar |
| GET/POST | `/reserve/<date>` | `reserve_detail` | View/create reservations for a date |
| POST | `/reserve/<date>/cancel/<res_id>` | `cancel_reservation` | Cancel a reservation |
| GET | `/my-reservations` | `my_reservations` | Member's upcoming reservations |
| GET | `/stats` | `stats` | Club usage statistics |
| GET | `/messages` | `messages` | Message board |
| GET/POST | `/messages/new` | `new_message` | Post a message |
| GET | `/messages/<id>` | `view_message` | Read a message |
| GET | `/messages/photo/<id>` | `message_photo` | Serve message photo |
| GET | `/fleet-status` | `fleet_status` | Maintenance schedule & service history |
| GET | `/gallery` | `gallery` | Club photo gallery |
| GET | `/club-photo/<id>` | `club_photo` | Serve gallery photo |
| GET | `/vehicle-photo/<id>` | `vehicle_photo` | Serve vehicle photo |
| GET | `/club-logo` | `club_logo` | Serve club logo (fallback: badge.svg) |
| GET | `/club-hero` | `club_hero` | Serve hero banner (404 if none) |
| GET | `/rules` | `rules_page` | Club rules and checklist reference |
| GET | `/checklist` | `checklist_page` | Departure checklist reference |
| GET | `/statements` | `statements` | Member PDF statements |
| GET | `/statements/<id>/download` | `download_statement` | Download a statement |
| GET | `/help` | `help_page` | Help documentation |
| GET | `/profile` | `profile` | Member profile (GET + POST for all sub-actions) |
| GET | `/profile/photo/<user_id>` | `profile_photo` | Serve member avatar |
| GET | `/ical/<token>.ics` | `ical_feed` | Personal iCal calendar feed |
| GET | `/ical-token` | `ical_token_page` | View / regenerate iCal token |
| POST | `/feedback` | `submit_feedback` | AI-routed member feedback |
| GET/POST | `/incidents/new` | `new_incident` | File an incident report |
| GET/POST | `/fuel/new` | `new_fuel_entry` | Log a fuel purchase |
| GET/POST | `/trips/<res_id>/checkout` | `trip_checkout` | Pre-departure check-out |
| GET/POST | `/trips/<res_id>/checkin` | `trip_checkin` | Post-trip check-in |
| POST | `/waitlist/<date>/join` | `waitlist_join` | Join the waitlist |
| POST | `/waitlist/<date>/leave` | `waitlist_leave` | Leave the waitlist |

### Admin

All `/admin/*` routes require `is_admin = TRUE` on the session user.

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| GET | `/admin/users` | `admin_users` | Member list |
| POST | `/admin/users/new` | `admin_new_user` | Create member account |
| POST | `/admin/users/<id>/deactivate` | `admin_deactivate_user` | Deactivate member |
| POST | `/admin/users/<id>/reset-pw` | `admin_reset_password` | Send password reset email |
| GET/POST | `/admin/users/<id>/edit` | `admin_edit_user` | Edit display name / family link |
| GET | `/admin/blackouts` | `admin_blackouts` | Manage blackout dates |
| POST | `/admin/blackouts/new` | `admin_blackout_new` | Create blackout |
| POST | `/admin/blackouts/<id>/delete` | `admin_blackout_delete` | Delete blackout |
| GET | `/admin/approvals` | `admin_approvals` | Pending reservations queue |
| POST | `/admin/approvals/<id>/approve` | `admin_approve` | Approve reservation |
| POST | `/admin/approvals/<id>/deny` | `admin_deny` | Deny reservation |
| GET | `/admin/incidents` | `admin_incidents` | All incident reports |
| POST | `/admin/incidents/<id>/resolve` | `admin_resolve_incident` | Mark incident resolved |
| GET | `/admin/fuel` | `admin_fuel` | Fuel log and stats |
| GET | `/admin/trip-logs` | `admin_trip_logs` | Trip check-out/check-in logs |
| GET | `/admin/audit-log` | `admin_audit_log` | Audit log (last 30 days default) |
| GET | `/admin/feedback` | `admin_feedback` | Member feedback submissions |
| GET | `/admin/maintenance` | `admin_maintenance` | Maintenance records & schedules |
| POST | `/admin/maintenance/records/new` | `admin_maintenance_record_new` | Log service record |
| POST | `/admin/maintenance/records/<id>/delete` | `admin_maintenance_record_delete` | Delete record |
| POST | `/admin/maintenance/schedules/new` | `admin_maintenance_schedule_new` | Add scheduled task |
| POST | `/admin/maintenance/schedules/<id>/done` | `admin_maintenance_schedule_done` | Mark task done, advance due date |
| POST | `/admin/maintenance/schedules/<id>/delete` | `admin_maintenance_schedule_delete` | Delete schedule |
| GET/POST | `/admin/settings` | `admin_settings` | Club settings, branding, photos |
| POST | `/admin/branding` | `admin_branding` | Update colors / logo / hero |
| POST | `/admin/photos/upload` | `admin_photo_upload` | Upload gallery photo |
| POST | `/admin/photos/<id>/delete` | `admin_photo_delete` | Delete gallery photo |
| POST | `/admin/vehicle-photos/upload` | `admin_vehicle_photo_upload` | Upload vehicle photo |
| POST | `/admin/vehicle-photos/<id>/set-primary` | `admin_vehicle_photo_set_primary` | Set primary vehicle photo |
| POST | `/admin/vehicle-photos/<id>/delete` | `admin_vehicle_photo_delete` | Delete vehicle photo |
| GET/POST | `/admin/statements` | `admin_statements` | PDF statement management |
| GET | `/admin/export-csv` | `admin_export_csv` | Download reservations as CSV |

### Super-Admin

All `/superadmin/*` routes authenticate against `fleetnests_master.super_admins`.

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/superadmin/login` | Super-admin login |
| GET | `/superadmin/logout` | Clear super-admin session |
| GET | `/superadmin/` | Club list dashboard |
| GET/POST | `/superadmin/clubs/new` | Provision a new club |
| POST | `/superadmin/clubs/<id>/activate` | Activate club |
| POST | `/superadmin/clubs/<id>/deactivate` | Deactivate club |

---

## 4. Module Reference

### `app.py`

Flask application factory (`create_app()`). Contains:
- `register_routes(app)` — all club-facing routes
- `register_superadmin_routes(app)` — super-admin routes
- Context processor `inject_context()` — provides `current_user`, `club`, `branding`, `club_settings`, vehicle-type booleans to every template

### `models.py`

All per-club database query functions. Key sections:

| Section | Key functions |
|---------|---------------|
| Users | `get_user_by_id`, `create_user`, `update_password`, `get_effective_user_id` |
| Reservations | `create_reservation`, `validate_reservation`, `cancel_reservation`, `get_reservations_range` |
| Vehicles | `get_all_vehicles`, `get_default_vehicle_id` |
| Maintenance | `get_maintenance_records`, `create_maintenance_record`, `get_maintenance_schedules`, `create_maintenance_schedule`, `mark_schedule_done`, `get_overdue_schedules` |
| Trip logs | `create_checkout`, `update_checkin`, `get_trip_log`, `get_all_trip_logs` |
| Fuel | `create_fuel_entry`, `get_all_fuel_entries`, `get_fuel_stats` |
| Branding | `get_branding` (flags only), `get_branding_logo`, `get_branding_hero`, `update_branding_colors`, `update_branding_logo`, `update_branding_hero` |
| Photos | `get_club_photos`, `add_club_photo`, `delete_club_photo`, `get_vehicle_photos`, `add_vehicle_photo`, `set_primary_vehicle_photo` |
| Settings | `get_all_club_settings`, `update_club_setting` |
| Audit | `log_action` |

**`validate_reservation(user_id, start_dt, end_dt, vehicle_id, exclude_res_id=None)`**

Returns an error string or `None` (success). Checks:
1. Duration within `[min_res_hours, max_res_hours]`
2. Start time is in the future
3. Not more than `max_advance_days` ahead
4. Per-user consecutive day limit
5. Per-user pending reservation limit
6. No overlap with existing active/pending reservations or blackouts (uses `SHARE ROW EXCLUSIVE` table lock for atomicity)
7. Per-user max concurrent vehicles (if `max_concurrent_vehicles` setting is set)

### `auth.py`

Session-based auth. Key decorators:
- `@auth.login_required` — redirects to `/login` if not authenticated
- `@auth.admin_required` — returns 403 if `current_user.is_admin` is False
- `@auth.statements_manager_required` — admin OR `can_manage_statements`
- `@auth.superadmin_required` — checks super-admin session key

### `db.py`

```python
db.execute(sql, params=None, fetch=True)  # returns list of dicts
db.fetchone(sql, params=None)             # returns dict or None
db.insert(sql, params)                    # returns the RETURNING row
```

All functions pick the DSN from `flask.g.club_dsn` (set by `club_resolver`).

### `club_resolver.py`

`init_app(app)` registers a `before_request` hook that:
1. Skips super-admin routes
2. Reads `X-Club-Short-Name` header OR extracts subdomain from `Host`
3. Fetches the club from master DB
4. Sets `g.club`, `g.vehicle_type`, `g.club_dsn`
5. Returns 404 for unknown clubs, 403 for inactive clubs

### `vehicle_types.py`

`build_checkout_context(vtype, settings)` returns a dict with:
- `VEHICLE_NOUN` — `'Boat'` or `'Plane'`
- `HOURS_LABEL` — e.g. `'Motor Hours'` or `'Hobbs Hours'`
- `CHECKLIST_ITEMS` — list of checklist item strings
- `fuel_*` flags, weather source constants, contact label

### `email_notify.py`

Sends all transactional email. Reads SMTP config from environment. Key functions:
- `notify_reservation_created(user, res)`
- `notify_reservation_cancelled(user, res)`
- `notify_waitlist_available(user, date)`
- `notify_weather_alert(club, alert_text)`
- `notify_trip_reminder(user, res)`
- `notify_password_reset(user, token)`
- `notify_demo_lead(email, club_name, short_name, ip)`

### `master_db.py` / `master_models.py`

`provision_club(name, short_name, vtype, contact_email, timezone)`:
1. Creates PostgreSQL user and database
2. Runs `init_club_db.sql` in the new database
3. Seeds the default admin account
4. Inserts the club into `fleetnests_master.clubs`

---

## 5. Club Settings Reference

Stored in `club_settings` as key/value pairs. Managed via `/admin/settings`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `min_res_hours` | float | `2.0` | Minimum reservation duration (hours) |
| `max_res_hours` | float | `6.0` | Maximum reservation duration (hours) |
| `max_advance_days` | int | `60` | How far ahead members can book |
| `max_future_reservations` | int | `7` | Max active+pending per member |
| `max_concurrent_vehicles` | int | `0` (unlimited) | Max vehicles reserved simultaneously per member |
| `approval_required` | bool | `false` | New reservations require admin approval |
| `has_hours_meter` | bool | `true` | Show engine hours on check-out/in |
| `has_fuel_level_enum` | bool | `true` | Show fuel level buttons (boat only) |
| `fuel_required_on_return` | bool | `false` | Require fuel quantity on check-in |
| `hours_label` | string | type-based | Override the hours label (e.g. `"Tach Hours"`) |
| `marina_phone` | string | — | Boat: marina contact phone |
| `fbo_phone` | string | — | Plane: FBO contact phone |
| `weather_zone` | string | — | NWS zone code for marine alerts |
| `nws_county` | string | — | NWS county code for alerts |
| `aviation_station` | string | — | METAR station ICAO (plane) |
| `member_rules_json` | JSON array | `[]` | Club rules list displayed on `/rules` |

---

## 6. Per-Club Theming & Branding

### CSS Variables

`base.html` injects club colors as CSS custom properties on every page:

```css
:root {
  --club-primary:       #0A2342;   /* from club_branding.primary_color */
  --club-primary-dark:  color-mix(in srgb, #0A2342 70%, #000);
  --club-primary-mid:   color-mix(in srgb, #0A2342 85%, #fff);
  --club-primary-light: color-mix(in srgb, #0A2342 75%, #fff);
  --club-accent:        #C9A84C;
  --club-accent-dark:   color-mix(in srgb, #C9A84C 80%, #000);
  --club-accent-light:  color-mix(in srgb, #C9A84C 70%, #fff);
}
```

`style.css` uses these variables throughout (`.bg-club-blue`, `.text-club-blue`, `.btn-club-blue`, etc.).

### Logo

- Stored as BYTEA in `club_branding.logo_data`
- Served at `/club-logo` (falls back to `static/images/badge.svg` if none uploaded)
- Shown in navbar (34px) and in the hero banner overlay (72px)
- Admin: Settings → Branding

### Hero Banner

- Stored as BYTEA in `club_branding.hero_data`
- Served at `/club-hero`
- Shown full-width at the top of the calendar page with gradient overlay
- Admin: Settings → Branding

### Branding Context

`get_branding()` returns:
```python
{
  "primary_color": "#0A2342",
  "accent_color": "#C9A84C",
  "has_logo": True,      # boolean only — no binary data
  "has_hero": False,
  "logo_content_type": "image/png",
  "hero_content_type": None,
}
```

Templates use `{% if branding.has_hero %}` — never `branding.hero_data`.

---

## 7. Maintenance Tracking

### Overview

Two complementary tables track fleet maintenance:

- **`maintenance_records`** — historical log of completed service work
- **`maintenance_schedules`** — recurring tasks with due-date and hours tracking

### Overdue Detection

`get_overdue_schedules()` returns schedules where:
- `next_due_date <= today`, OR
- `vehicle.current_hours >= next_due_hours` (when both are set)

The fleet status page shows a warning banner when any overdue items exist.

### Marking a Task Done

`mark_schedule_done(schedule_id, done_date, done_hours)`:
1. Reads the schedule's `interval_months` and `interval_hours`
2. Computes `next_due_date = done_date + relativedelta(months=interval_months)`
3. Computes `next_due_hours = done_hours + interval_hours`
4. Updates `last_performed_at`, `last_performed_hours`, `next_due_date`, `next_due_hours`

### Member View (`/fleet-status`)

Shows all active schedules with color-coded status badges:
- `Overdue` (red) — past due by date or hours
- `Due Soon` (yellow) — due within 30 days
- `OK` (green)

Also shows per-vehicle accordion with last 20 service records.

### Admin View (`/admin/maintenance`)

Full management interface:
- **Log Service** modal — add a `maintenance_record`
- **Add Schedule** modal — create a `maintenance_schedule`
- **Mark Done** modal — record completion date/hours and auto-advance next due
- Delete buttons for both records and schedules

---

## 8. Vehicle Types (Boat vs Plane)

Vehicle type is set at the club level and cannot be changed without re-provisioning.

| Feature | Boat | Plane |
|---------|------|-------|
| Hours label | Motor Hours | Hobbs Hours |
| Fuel level entry | Dropdown (empty → full) | Quantity in gallons |
| Fuel required on return | Optional | Configurable |
| Weather | NWS zone/county marine | METAR (aviation station) |
| Contact label | Marina phone | FBO phone |
| Registration field | HIN | N-number / tail |

All vehicle-type decisions are isolated in `vehicle_types.py`. Templates use the context variables `is_boat`, `is_plane` for conditional rendering.

---

## 9. Authentication & Authorization

### Member Auth Flow

1. POST `/login` with `username` + `password`
2. `auth.authenticate()` bcrypt-verifies against `users.password_hash` (or `password_hash2` for family sub-accounts)
3. On success: `auth.login_user(user, club_short_name=...)` stores user dict in `session['user']`
4. All protected routes use `@auth.login_required`

### Admin Auth

Same session; admin routes additionally check `current_user['is_admin'] == True`.

### Super-Admin Auth

Completely separate session key (`session['super_admin']`). Authenticates against `fleetnests_master.super_admins`. Super-admins can also access club-specific data via the normal club routes if they're logged in as a club member.

### Demo Club Auth

Clubs named `sample1` or `sample2` use email-only login (no password). The app logs the visitor's email in the master DB as a lead and logs them in as the pre-seeded demo admin user.

### Password Reset

1. POST `/forgot-password` with `login` (username or email)
2. `create_password_token()` generates a 32-char URL-safe token stored in `users.password_reset_token` (1-hour expiry)
3. Token is emailed; user clicks link to `/set-password/<token>`
4. `consume_password_token()` validates and clears the token, user sets new password

---

## 10. Email Notifications

### Configuration

```
EMAIL_ENABLED=true
EMAIL_FROM=noreply@yourclub.com
SMTP_HOST=localhost
SMTP_PORT=25
APP_URL=https://yourclub.fleetnests.com
```

### Events That Send Email

| Trigger | Recipients |
|---------|-----------|
| Reservation created | Member |
| Reservation cancelled | Member |
| Reservation approved/denied | Member |
| Waitlist slot available | Waitlisted member |
| Weather alert | All members with email |
| Trip reminder (6 PM cron) | Members with reservations tomorrow |
| Password reset | Requester |
| Email change verification | New email address |
| Demo lead signup | Admin (`FEEDBACK_EMAIL`) |

---

## 11. Weather Integration

### Boat Clubs (NWS)

`weather.py` fetches from `https://api.weather.gov/alerts/active`:
- Filter by `zone` (`club_settings.weather_zone`) and `county` (`club_settings.nws_county`)
- Returns `Effective`, `Expires`, `Event`, `Headline`, `Description` for each alert

### Flying Clubs (METAR)

`weather.py` fetches from `https://aviationweather.gov/api/data/metar`:
- Filter by `station` (`club_settings.aviation_station`)
- Returns decoded METAR including flight rules category (VFR/MVFR/IFR/LIFR)

### Cron

`weather_check.py` runs at 6 AM daily, fetches alerts for all active clubs, and calls `email_notify.notify_weather_alert()` for each club that has alerts.

---

## 12. AI Feedback Routing

### Flow

1. Member submits text + optional attachment at `/feedback`
2. `feedback.process_feedback()` calls the Anthropic API (Claude) with the text
3. Claude classifies as `github_issue` (bug/feature) or `email` (other)
4. For `github_issue`: creates a GitHub issue via REST API
5. For `email`: sends to `FEEDBACK_EMAIL`
6. Result stored in `feedback_submissions`

### Configuration

```
ANTHROPIC_API_KEY=...
GITHUB_TOKEN=ghp_...       # Issues: Read+Write scope
GITHUB_REPO=owner/repo
FEEDBACK_EMAIL=admin@club.com
```

If `ANTHROPIC_API_KEY` is not set, all feedback falls back to email.

---

## 13. Deployment Reference

### Systemd Service

```ini
[Unit]
Description=FleetNests Reservation Platform
After=network.target

[Service]
User=richard
WorkingDirectory=/home/richard/projects/fleetnests
EnvironmentFile=/home/richard/projects/fleetnests/.env
ExecStart=/usr/bin/gunicorn --config gunicorn.conf.py app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx (Path-Mounted, Multi-Club)

```nginx
location /sample1/ {
    proxy_pass         http://127.0.0.1:5210/;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Forwarded-Prefix /sample1;
    proxy_set_header   X-Club-Short-Name sample1;
}
```

### Adding a New Club (Bare Metal)

1. Create PostgreSQL user and database manually (or use the super-admin panel)
2. Run `init_club_db.sql` against the new database
3. Add `DB_PASS_FN_<SHORTNAME>_USER=<pw>` to `.env`
4. Add the club record to `fleetnests_master.clubs`
5. Add Nginx location block for the new subdomain/path
6. Restart the service

### Live DB Migration (Adding Tables to Existing Clubs)

```bash
python3 - << 'EOF'
import psycopg2
sql = "CREATE TABLE IF NOT EXISTS ..."
for db_name, user, pw in [...]:
    conn = psycopg2.connect(host='127.0.0.1', dbname=db_name, user=user, password=pw)
    conn.autocommit = True
    conn.cursor().execute(sql)
    print(f'{db_name}: OK')
    conn.close()
EOF
```

---

## 14. Demo Sites (sample1 / sample2)

- Accessible at `https://fleetnests.com/sample1` and `/sample2`
- Use email-only login (no passwords)
- Visitor emails are logged as leads in the master DB
- Data resets nightly via `reset_samples.sh` (cron at midnight)
- Demo banner shown to all visitors
- Both clubs are fully functional: different vehicle types, logos, colors, and sample data

`seed_samples.py` populates:
- Vehicles with realistic names
- Members with sample reservations
- Club branding (logo from local file path)
- Club settings

---

*Last updated: 2026-02-28*
