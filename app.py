"""
Bentley Boat Club Reservation System — Flask application.
Portable: deploy at hastingtx.org/boat or on its own domain by changing APP_PREFIX.
"""

import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, abort, g
)
from werkzeug.middleware.proxy_fix import ProxyFix

from zoneinfo import ZoneInfo

import auth
import models
import email_notify

CENTRAL = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ["SECRET_KEY"]
    app.config["APPROVAL_REQUIRED"] = os.environ.get("APPROVAL_REQUIRED", "false").lower() == "true"

    # Sub-path portability: set APPLICATION_ROOT for correct url_for() prefixing
    prefix = os.environ.get("APP_PREFIX", "/")
    app.config["APPLICATION_ROOT"] = prefix
    app.config["PREFERRED_URL_SCHEME"] = "https"

    # Trust the reverse proxy (nginx) for host/scheme/prefix headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Make current_user available in all templates
    @app.context_processor
    def inject_user():
        return {"current_user": auth.current_user()}

    # Custom 403 page
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app: Flask):

    # -- Root redirect ---------------------------------------------------

    @app.route("/")
    def index():
        return redirect(url_for("calendar"))

    # -- Auth ------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if auth.current_user():
            return redirect(url_for("calendar"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = auth.authenticate(username, password)
            if user:
                auth.login_user(user)
                return redirect(url_for("calendar"))
            flash("Invalid username or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        auth.logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    # -- Calendar --------------------------------------------------------

    @app.route("/calendar")
    @auth.login_required
    def calendar():
        return render_template("calendar.html")

    @app.route("/api/reservations")
    @auth.login_required
    def api_reservations():
        """JSON feed for FullCalendar. Returns timed events for the requested range."""
        try:
            start = date.fromisoformat(request.args["start"][:10])
            end   = date.fromisoformat(request.args["end"][:10])
        except (KeyError, ValueError):
            return jsonify([])

        rows = models.get_reservations_range(start, end)
        user = auth.current_user()
        events = []
        for row in rows:
            mine = (row["user_id"] == user["id"])
            is_pending = (row["status"] == "pending_approval")
            color = "#ffc107" if is_pending else ("#0d6efd" if mine else "#6c757d")
            text_color = "#000000" if is_pending else "#ffffff"
            # Attach Central Time offset so FullCalendar is unambiguous regardless
            # of the viewer's browser timezone.
            start_ct = row["start_time"].replace(tzinfo=CENTRAL) if row["start_time"] else None
            end_ct   = row["end_time"].replace(tzinfo=CENTRAL)   if row["end_time"]   else None
            events.append({
                "title": row["full_name"],
                "start": start_ct.isoformat() if start_ct else row["date"].isoformat(),
                "end":   end_ct.isoformat()   if end_ct   else None,
                "color": color,
                "textColor": text_color,
                "url": url_for("reserve_detail", res_date=row["date"].isoformat()),
            })

        # Add blackout dates as non-clickable red blocks
        blackouts = models.get_blackouts_range(start, end)
        for b in blackouts:
            events.append({
                "title": f"\U0001f6ab {b['reason']}",
                "start": b["start_time"].replace(tzinfo=CENTRAL).isoformat(),
                "end":   b["end_time"].replace(tzinfo=CENTRAL).isoformat(),
                "color": "#dc3545",
                "textColor": "#ffffff",
                "display": "block",
            })

        return jsonify(events)

    # -- Reserve / Cancel ------------------------------------------------

    @app.route("/reserve/<res_date>", methods=["GET", "POST"])
    @auth.login_required
    def reserve_detail(res_date: str):
        try:
            day = date.fromisoformat(res_date)
        except ValueError:
            abort(404)

        user = auth.current_user()
        existing = models.get_reservations_for_date(day)

        if request.method == "POST":
            start_str = request.form.get("start_time", "").strip()
            end_str   = request.form.get("end_time", "").strip()
            notes     = request.form.get("notes", "").strip()[:300]
            try:
                start_dt = datetime.fromisoformat(f"{res_date}T{start_str}")
                end_dt   = datetime.fromisoformat(f"{res_date}T{end_str}")
            except ValueError:
                flash("Invalid time format.", "danger")
                user_res_ids = {r["user_id"] for r in existing}
                on_waitlist  = models.is_on_waitlist(user["id"], day)
                return render_template("reserve.html", day=day, existing=existing, today=date.today(),
                                       user_has_res=user["id"] in user_res_ids,
                                       on_waitlist=on_waitlist)

            error = models.validate_reservation(user["id"], start_dt, end_dt)
            if error:
                flash(error, "danger")
            else:
                approval = app.config.get("APPROVAL_REQUIRED", False)
                status_after = "pending_approval" if approval else "active"
                result = models.make_reservation(user["id"], start_dt, end_dt, notes=notes,
                                                 status=status_after)
                models.log_action(user["id"], "reservation_created", "reservation",
                                  result["id"] if result else None,
                                  {"date": res_date, "start": start_str, "end": end_str})
                if approval:
                    flash(f"Reservation request submitted for {day.strftime('%B %d')} — awaiting admin approval.", "info")
                    admins = [u for u in models.get_all_active_users() if u["is_admin"]]
                    email_notify.notify_approval_needed(admins, user,
                        {"date": day, "start_time": start_dt, "end_time": end_dt})
                else:
                    flash(f"Reserved {day.strftime('%B %d')} "
                          f"{start_dt.strftime('%-I:%M %p')}–{end_dt.strftime('%-I:%M %p')} CT!", "success")
                    email_notify.notify_reservation_confirmed(user,
                        {"date": day, "start_time": start_dt, "end_time": end_dt})
                return redirect(url_for("calendar"))

        user_res_ids = {r["user_id"] for r in existing}
        on_waitlist  = models.is_on_waitlist(user["id"], day)
        return render_template("reserve.html", day=day, existing=existing, today=date.today(),
                               user_has_res=user["id"] in user_res_ids,
                               on_waitlist=on_waitlist)

    @app.route("/cancel/<int:res_id>", methods=["POST"])
    @auth.login_required
    def cancel_reservation(res_id: int):
        user = auth.current_user()
        res = models.get_reservation_by_id(res_id)
        ok = models.cancel_reservation(res_id, user["id"], is_admin=user["is_admin"])
        if ok and res:
            day = res["date"].strftime("%B %d, %Y")
            flash(f"Reservation for {day} cancelled.", "success")
            models.log_action(user["id"], "reservation_cancelled", "reservation", res_id)
            # Notify the reservation owner if admin cancelled on their behalf
            if user["is_admin"] and res["user_id"] != user["id"]:
                owner = models.get_user_by_id(res["user_id"])
                if owner:
                    email_notify.notify_reservation_cancelled(owner, res)
            elif not user["is_admin"]:
                email_notify.notify_reservation_cancelled(user, res)
            # Notify waitlisted members that this slot is open
            models.notify_and_clear_waitlist(res["date"])
        else:
            flash("Could not cancel that reservation.", "danger")
        # Redirect back to referring page (my-reservations or calendar)
        referrer = request.referrer or ""
        if "my-reservations" in referrer:
            return redirect(url_for("my_reservations"))
        return redirect(url_for("calendar"))

    # -- My Reservations -------------------------------------------------

    @app.route("/my-reservations")
    @auth.login_required
    def my_reservations():
        user = auth.current_user()
        data = models.get_user_reservations(user["id"])
        waitlist = models.get_user_waitlist(user["id"])
        ical_token = models.get_or_create_ical_token(user["id"])
        tlogs = models.get_trip_logs_for_user(user["id"])
        trip_logs_map = {tlog["res_id"]: tlog for tlog in tlogs}
        return render_template("my_reservations.html",
                               upcoming=data["upcoming"],
                               past=data["past"],
                               waitlist=waitlist,
                               ical_token=ical_token,
                               trip_logs_map=trip_logs_map,
                               today=date.today())

    # -- Stats -----------------------------------------------------------

    @app.route("/stats")
    @auth.login_required
    def stats():
        rows = models.get_usage_stats()
        return render_template("stats.html", rows=rows)

    # -- Messages --------------------------------------------------------

    @app.route("/messages")
    @auth.login_required
    def messages():
        msgs = models.get_messages()
        return render_template("messages.html", messages=msgs)

    @app.route("/messages/new", methods=["GET", "POST"])
    @auth.login_required
    def new_message():
        user = auth.current_user()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            body  = request.form.get("body", "").strip()
            is_ann = bool(request.form.get("is_announcement")) and user["is_admin"]
            if not title or not body:
                flash("Title and body are required.", "danger")
            else:
                models.create_message(user["id"], title, body, is_ann)
                flash("Message posted.", "success")
                return redirect(url_for("messages"))
        return render_template("message_form.html")

    @app.route("/messages/<int:msg_id>/delete", methods=["POST"])
    @auth.login_required
    def delete_message(msg_id: int):
        user = auth.current_user()
        ok = models.delete_message(msg_id, user["id"], is_admin=user["is_admin"])
        if ok:
            flash("Message deleted.", "success")
        else:
            flash("You cannot delete that message.", "danger")
        return redirect(url_for("messages"))

    # -- Admin -----------------------------------------------------------

    @app.route("/admin/users")
    @auth.admin_required
    def admin_users():
        users = models.get_all_active_users()
        return render_template("admin/users.html", users=users)

    @app.route("/admin/users/new", methods=["GET", "POST"])
    @auth.admin_required
    def admin_new_user():
        if request.method == "POST":
            username  = request.form.get("username", "").strip().lower()
            full_name = request.form.get("full_name", "").strip()
            email     = request.form.get("email", "").strip()
            password  = request.form.get("password", "")
            is_admin  = bool(request.form.get("is_admin"))
            max_consec = int(request.form.get("max_consecutive_days", 3))
            max_pend   = int(request.form.get("max_pending", 7))

            if not username or not full_name or not password:
                flash("Username, full name, and password are required.", "danger")
            else:
                pw_hash = auth.hash_password(password)
                try:
                    models.create_user(username, full_name, email, pw_hash, is_admin,
                                       max_consecutive_days=max_consec, max_pending=max_pend)
                    models.log_action(auth.current_user()["id"], "user_created", "user", None, {"username": username})
                    flash(f"User {username} created.", "success")
                    return redirect(url_for("admin_users"))
                except Exception as e:
                    if "unique" in str(e).lower():
                        flash("That username is already taken.", "danger")
                    else:
                        flash("Error creating user.", "danger")

        return render_template("admin/users.html",
                               users=models.get_all_active_users(),
                               show_form=True)

    @app.route("/admin/users/<int:user_id>/deactivate", methods=["POST"])
    @auth.admin_required
    def admin_deactivate_user(user_id: int):
        me = auth.current_user()
        if user_id == me["id"]:
            flash("You cannot deactivate your own account.", "danger")
        else:
            models.deactivate_user(user_id)
            models.log_action(auth.current_user()["id"], "user_deactivated", "user", user_id)
            flash("User deactivated.", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:user_id>/reset-password", methods=["GET", "POST"])
    @auth.admin_required
    def admin_reset_password(user_id: int):
        user = models.get_user_by_id(user_id)
        if not user:
            abort(404)

        if request.method == "POST":
            new_pw = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            if not new_pw or len(new_pw) < 8:
                flash("Password must be at least 8 characters.", "danger")
            elif new_pw != confirm:
                flash("Passwords do not match.", "danger")
            else:
                models.update_password(user_id, auth.hash_password(new_pw))
                models.log_action(auth.current_user()["id"], "password_reset", "user", user_id)
                flash(f"Password reset for {user['username']}.", "success")
                return redirect(url_for("admin_users"))

        return render_template("admin/reset_pw.html", user=user)

    @app.route("/admin/blackouts")
    @auth.admin_required
    def admin_blackouts():
        blackouts = models.get_all_blackouts()
        return render_template("admin/blackouts.html", blackouts=blackouts)

    @app.route("/admin/blackouts/new", methods=["GET", "POST"])
    @auth.admin_required
    def admin_new_blackout():
        if request.method == "POST":
            date_str  = request.form.get("date", "").strip()
            start_str = request.form.get("start_time", "").strip()
            end_str   = request.form.get("end_time", "").strip()
            reason    = request.form.get("reason", "").strip()
            all_day   = bool(request.form.get("all_day"))
            if not date_str or not reason:
                flash("Date and reason are required.", "danger")
            else:
                try:
                    if all_day:
                        start_dt = datetime.fromisoformat(f"{date_str}T00:00:00")
                        end_dt   = datetime.fromisoformat(f"{date_str}T23:59:59")
                    else:
                        start_dt = datetime.fromisoformat(f"{date_str}T{start_str}")
                        end_dt   = datetime.fromisoformat(f"{date_str}T{end_str}")
                    if end_dt <= start_dt:
                        flash("End time must be after start time.", "danger")
                    else:
                        user = auth.current_user()
                        models.create_blackout(start_dt, end_dt, reason, user["id"])
                        flash("Blackout date added.", "success")
                        return redirect(url_for("admin_blackouts"))
                except ValueError:
                    flash("Invalid date or time.", "danger")
        return render_template("admin/blackouts.html", blackouts=models.get_all_blackouts(), show_form=True)

    @app.route("/admin/blackouts/<int:blackout_id>/delete", methods=["POST"])
    @auth.admin_required
    def admin_delete_blackout(blackout_id: int):
        models.delete_blackout(blackout_id)
        flash("Blackout removed.", "success")
        return redirect(url_for("admin_blackouts"))

    @app.route("/admin/export-csv")
    @auth.admin_required
    def admin_export_csv():
        import csv, io
        rows = models.get_usage_stats()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Member", "Past", "Upcoming", "Total", "Cancelled"])
        for r in rows:
            writer.writerow([r["full_name"], r["past"], r["upcoming"], r["total"], r["cancelled"]])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=reservations.csv"},
        )


    @app.route("/admin/audit-log")
    @auth.admin_required
    def admin_audit_log():
        from datetime import timedelta
        days = int(request.args.get("days", 30))
        after = models.now_ct() - timedelta(days=days)
        entries = models.get_audit_log(limit=500, after_date=after)
        return render_template("admin/audit_log.html", entries=entries, days=days)

    @app.route("/admin/approvals")
    @auth.admin_required
    def admin_approvals():
        pending = models.get_pending_approval()
        return render_template("admin/approvals.html", pending=pending)

    @app.route("/admin/approvals/<int:res_id>/approve", methods=["POST"])
    @auth.admin_required
    def admin_approve(res_id: int):
        models.approve_reservation(res_id)
        flash("Reservation approved.", "success")
        return redirect(url_for("admin_approvals"))

    @app.route("/admin/approvals/<int:res_id>/deny", methods=["POST"])
    @auth.admin_required
    def admin_deny(res_id: int):
        res = models.get_reservation_by_id(res_id)
        models.deny_reservation(res_id)
        flash("Reservation denied.", "success")
        if res:
            owner = models.get_user_by_id(res["user_id"])
            if owner:
                email_notify.notify_reservation_cancelled(owner, res)
        return redirect(url_for("admin_approvals"))

    # -- Incident / Damage Reports ----------------------------------------

    @app.route("/incidents/new", methods=["GET", "POST"])
    @auth.login_required
    def new_incident():
        user = auth.current_user()
        # Allow linking to a specific past reservation
        res_id = request.args.get("res_id", type=int)
        res = models.get_reservation_by_id(res_id) if res_id else None

        if request.method == "POST":
            res_id_form = request.form.get("res_id", type=int)
            severity    = request.form.get("severity", "minor")
            description = request.form.get("description", "").strip()
            report_date = request.form.get("report_date", "").strip()

            if not description or not report_date:
                flash("Description and date are required.", "danger")
            else:
                try:
                    rdate = date.fromisoformat(report_date)
                    models.create_incident(user["id"], res_id_form, rdate, severity, description)
                    models.log_action(user["id"], "incident_reported", "reservation", res_id_form,
                                      {"severity": severity})
                    flash("Incident report submitted. Thank you.", "success")
                    return redirect(url_for("my_reservations"))
                except ValueError:
                    flash("Invalid date.", "danger")

        return render_template("incident_form.html", res=res,
                               today=date.today().isoformat())

    @app.route("/admin/incidents")
    @auth.admin_required
    def admin_incidents():
        incidents = models.get_all_incidents()
        return render_template("admin/incidents.html", incidents=incidents)

    @app.route("/admin/incidents/<int:inc_id>/resolve", methods=["POST"])
    @auth.admin_required
    def admin_resolve_incident(inc_id: int):
        user = auth.current_user()
        models.resolve_incident(inc_id, user["id"])
        flash("Incident marked as resolved.", "success")
        return redirect(url_for("admin_incidents"))

    # -- Fuel Log ---------------------------------------------------------

    @app.route("/fuel/new", methods=["GET", "POST"])
    @auth.login_required
    def new_fuel_entry():
        user = auth.current_user()
        res_id = request.args.get("res_id", type=int)
        res = models.get_reservation_by_id(res_id) if res_id else None

        if request.method == "POST":
            res_id_form     = request.form.get("res_id", type=int)
            log_date        = request.form.get("log_date", "").strip()
            gallons_str     = request.form.get("gallons", "").strip()
            price_str       = request.form.get("price_per_gallon", "").strip()
            total_str       = request.form.get("total_cost", "").strip()
            notes           = request.form.get("notes", "").strip()[:300]

            try:
                ldate   = date.fromisoformat(log_date)
                gallons = float(gallons_str)
                price   = float(price_str) if price_str else None
                total   = float(total_str) if total_str else (
                    round(gallons * price, 2) if price else None
                )
                if gallons <= 0:
                    raise ValueError("gallons must be positive")
                models.create_fuel_entry(user["id"], res_id_form, ldate, gallons,
                                         price, total, notes)
                flash(f"Fuel entry logged: {gallons} gal on {ldate.strftime('%B %d, %Y')}.", "success")
                return redirect(url_for("my_reservations"))
            except ValueError as ex:
                flash(f"Invalid input: {ex}", "danger")

        return render_template("fuel_form.html", res=res,
                               today=date.today().isoformat())

    @app.route("/admin/fuel")
    @auth.admin_required
    def admin_fuel():
        entries = models.get_all_fuel_entries()
        stats   = models.get_fuel_stats()
        return render_template("admin/fuel.html", entries=entries, stats=stats)

    # -- Waitlist ---------------------------------------------------------

    @app.route("/waitlist/<res_date>/join", methods=["POST"])
    @auth.login_required
    def waitlist_join(res_date: str):
        user = auth.current_user()
        try:
            day = date.fromisoformat(res_date)
        except ValueError:
            abort(404)
        notes = request.form.get("notes", "").strip()[:300]
        models.add_to_waitlist(user["id"], day, notes)
        flash(f"You're on the waitlist for {day.strftime('%B %d')}. "
              "We'll email you if a spot opens.", "info")
        return redirect(url_for("reserve_detail", res_date=res_date))

    @app.route("/waitlist/<res_date>/leave", methods=["POST"])
    @auth.login_required
    def waitlist_leave(res_date: str):
        user = auth.current_user()
        try:
            day = date.fromisoformat(res_date)
        except ValueError:
            abort(404)
        models.remove_from_waitlist(user["id"], day)
        flash("Removed from waitlist.", "info")
        return redirect(url_for("reserve_detail", res_date=res_date))

    # -- iCal feed (no login — token is the auth) -------------------------

    @app.route("/ical/<token>.ics")
    def ical_feed(token: str):
        from flask import Response
        user = models.get_user_by_ical_token(token)
        if not user:
            abort(404)
        reservations = models.get_user_ical_reservations(user["id"])

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Bentley Boat Club//Reservation System//EN",
            "X-WR-CALNAME:My Boat Reservations",
            "X-WR-TIMEZONE:America/Chicago",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        for r in reservations:
            # Format datetimes as YYYYMMDDTHHMMSS (floating / local time)
            def fmt(dt):
                return dt.strftime("%Y%m%dT%H%M%S")
            uid = f"res-{r['id']}@bentleyboatclub"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART;TZID=America/Chicago:{fmt(r['start_time'])}",
                f"DTEND;TZID=America/Chicago:{fmt(r['end_time'])}",
                f"SUMMARY:Boat Reservation",
                f"DESCRIPTION:{(r.get('notes') or '').replace(chr(10), ' ')}",
                f"CREATED:{fmt(r['created_at'])}",
                "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")

        ics_content = "\r\n".join(lines) + "\r\n"
        return Response(
            ics_content,
            mimetype="text/calendar",
            headers={"Content-Disposition": f"attachment; filename=boat-reservations.ics"},
        )

    @app.route("/ical-token")
    @auth.login_required
    def ical_token_page():
        user = auth.current_user()
        token = models.get_or_create_ical_token(user["id"])
        return render_template("ical_token.html", token=token)

    # -- Trip Log (Checkout / Check-in) -----------------------------------

    @app.route("/trips/<int:res_id>/checkout", methods=["GET", "POST"])
    @auth.login_required
    def trip_checkout(res_id: int):
        user = auth.current_user()
        res = models.get_reservation_by_id(res_id)
        if not res:
            abort(404)
        if not user["is_admin"] and res["user_id"] != user["id"]:
            abort(403)
        if res["date"] != date.today():
            flash("Check-out is only available on the day of your reservation.", "warning")
            return redirect(url_for("my_reservations"))
        trip_log = models.get_trip_log(res_id)
        if trip_log:
            flash("Check-out already recorded for this reservation.", "info")
            return redirect(url_for("my_reservations"))

        if request.method == "POST":
            time_str    = request.form.get("checkout_time", "").strip()
            hours_str   = request.form.get("motor_hours_out", "").strip()
            fuel_level  = request.form.get("fuel_level_out", "").strip()
            condition   = request.form.get("condition_out", "").strip()[:500]
            checklist   = [int(x) for x in request.form.getlist("checklist") if x.isdigit()]
            try:
                checkout_dt = datetime.fromisoformat(f"{res['date'].isoformat()}T{time_str}")
                hours_out   = float(hours_str) if hours_str else None
                models.create_checkout(res_id, user["id"], checkout_dt,
                                       hours_out, fuel_level or None, condition, checklist)
                models.log_action(user["id"], "trip_checkout", "reservation", res_id,
                                  {"fuel_level": fuel_level, "checklist_count": len(checklist)})
                flash("Check-out recorded. Have a great trip!", "success")
                return redirect(url_for("my_reservations"))
            except (ValueError, KeyError) as ex:
                flash(f"Invalid input: {ex}", "danger")

        now_time = datetime.now(CENTRAL).strftime("%H:%M")
        return render_template("checkout.html", res=res, trip_log=None,
                               CAPTAIN_CHECKLIST=models.CAPTAIN_CHECKLIST,
                               CHECKLIST_CATEGORIES=models.CHECKLIST_CATEGORIES,
                               FUEL_LEVELS=models.FUEL_LEVELS,
                               now_time=now_time)

    @app.route("/trips/<int:res_id>/checkin", methods=["GET", "POST"])
    @auth.login_required
    def trip_checkin(res_id: int):
        user = auth.current_user()
        res = models.get_reservation_by_id(res_id)
        if not res:
            abort(404)
        trip_log = models.get_trip_log(res_id)
        if not trip_log:
            flash("No check-out found for this reservation.", "warning")
            return redirect(url_for("my_reservations"))
        if not user["is_admin"] and trip_log["user_id"] != user["id"]:
            abort(403)

        if request.method == "POST":
            time_str      = request.form.get("checkin_time", "").strip()
            hours_str     = request.form.get("motor_hours_in", "").strip()
            gallons_str   = request.form.get("fuel_added_gallons", "").strip()
            cost_str      = request.form.get("fuel_added_cost", "").strip()
            condition     = request.form.get("condition_in", "").strip()[:500]
            try:
                checkin_dt  = datetime.fromisoformat(f"{res['date'].isoformat()}T{time_str}")
                hours_in    = float(hours_str) if hours_str else None
                gallons     = float(gallons_str) if gallons_str else None
                cost        = float(cost_str) if cost_str else None
                models.update_checkin(res_id, checkin_dt, hours_in, gallons, cost, condition)
                if gallons and gallons > 0:
                    models.create_fuel_entry(user["id"], res_id, res["date"],
                                             gallons, None, cost,
                                             "Auto-logged from trip check-in")
                models.log_action(user["id"], "trip_checkin", "reservation", res_id,
                                  {"hours_in": hours_in, "fuel_gallons": gallons})
                flash("Check-in complete. Welcome back!", "success")
                return redirect(url_for("my_reservations"))
            except (ValueError, KeyError) as ex:
                flash(f"Invalid input: {ex}", "danger")

        now_time = datetime.now(CENTRAL).strftime("%H:%M")
        return render_template("checkin.html", res=res, trip_log=trip_log,
                               FUEL_LEVELS=models.FUEL_LEVELS,
                               now_time=now_time)

    @app.route("/admin/trip-logs")
    @auth.admin_required
    def admin_trip_logs():
        logs = models.get_all_trip_logs()
        return render_template("admin/trip_logs.html", logs=logs)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5210)
