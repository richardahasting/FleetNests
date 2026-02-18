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

CENTRAL = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ["SECRET_KEY"]

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
            # Attach Central Time offset so FullCalendar is unambiguous regardless
            # of the viewer's browser timezone.
            start_ct = row["start_time"].replace(tzinfo=CENTRAL) if row["start_time"] else None
            end_ct   = row["end_time"].replace(tzinfo=CENTRAL)   if row["end_time"]   else None
            events.append({
                "title": row["full_name"],
                "start": start_ct.isoformat() if start_ct else row["date"].isoformat(),
                "end":   end_ct.isoformat()   if end_ct   else None,
                "color": "#0d6efd" if mine else "#6c757d",
                "textColor": "#ffffff",
                "url": url_for("reserve_detail", res_date=row["date"].isoformat()),
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
            try:
                start_dt = datetime.fromisoformat(f"{res_date}T{start_str}")
                end_dt   = datetime.fromisoformat(f"{res_date}T{end_str}")
            except ValueError:
                flash("Invalid time format.", "danger")
                return render_template("reserve.html", day=day, existing=existing, today=date.today())

            error = models.validate_reservation(user["id"], start_dt, end_dt)
            if error:
                flash(error, "danger")
            else:
                models.make_reservation(user["id"], start_dt, end_dt)
                flash(f"Reserved {day.strftime('%B %d')} "
                      f"{start_dt.strftime('%-I:%M %p')}–{end_dt.strftime('%-I:%M %p')} CT!", "success")
                return redirect(url_for("calendar"))

        return render_template("reserve.html", day=day, existing=existing, today=date.today())

    @app.route("/cancel/<int:res_id>", methods=["POST"])
    @auth.login_required
    def cancel_reservation(res_id: int):
        user = auth.current_user()
        res = models.get_reservation_by_id(res_id)
        ok = models.cancel_reservation(res_id, user["id"], is_admin=user["is_admin"])
        if ok and res:
            day = res["date"].strftime("%B %d, %Y")
            flash(f"Reservation for {day} cancelled.", "success")
        else:
            flash("Could not cancel that reservation.", "danger")
        return redirect(url_for("calendar"))

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

            if not username or not full_name or not password:
                flash("Username, full name, and password are required.", "danger")
            else:
                pw_hash = auth.hash_password(password)
                try:
                    models.create_user(username, full_name, email, pw_hash, is_admin)
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
                flash(f"Password reset for {user['username']}.", "success")
                return redirect(url_for("admin_users"))

        return render_template("admin/reset_pw.html", user=user)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5210)
