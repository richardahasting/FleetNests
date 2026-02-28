"""
Email notifications for ClubReserve.
Uses local Postfix (localhost:25) — no SMTP auth needed on same server.
Activate by setting EMAIL_ENABLED=true in .env.

All notify_* functions are vehicle-type aware via _get_club_context().
"""
import os
import smtplib
from email.mime.text import MIMEText

EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST     = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "25"))


def _get_club_context() -> dict:
    """
    Build email context from current Flask request's club (g.club).
    Falls back to env vars for dev / single-club use.
    """
    try:
        from flask import g
        club = getattr(g, "club", None)
        if club:
            vehicle_type = club.get("vehicle_type", "boat")
            club_name    = club.get("name", "Club")
            app_url      = os.environ.get("APP_URL", "https://clubreserve.com")
            email_from   = os.environ.get("EMAIL_FROM",
                                          f"noreply@{club.get('subdomain', 'club')}.clubreserve.com")
            return {
                "club_name":     club_name,
                "vehicle_type":  vehicle_type,
                "vehicle_noun":  "boat" if vehicle_type == "boat" else "aircraft",
                "checklist_name": "Captain's Checklist" if vehicle_type == "boat" else "Pre-Flight Checklist",
                "vehicle_label":  "boat" if vehicle_type == "boat" else "aircraft",
                "app_url":       app_url,
                "email_from":    email_from,
                "signature":     f"— {club_name}",
            }
    except RuntimeError:
        pass

    # Fallback (no request context)
    return {
        "club_name":      "Club",
        "vehicle_type":   "boat",
        "vehicle_noun":   "boat",
        "checklist_name": "Captain's Checklist",
        "vehicle_label":  "boat",
        "app_url":        os.environ.get("APP_URL", "https://clubreserve.com"),
        "email_from":     os.environ.get("EMAIL_FROM", "noreply@clubreserve.com"),
        "signature":      "— ClubReserve",
    }


def send_email(to_addr: str, subject: str, body_text: str) -> bool:
    """Send a plain-text email via local Postfix. Returns True on success."""
    if not EMAIL_ENABLED or not to_addr:
        return False
    ctx = _get_club_context()
    try:
        msg = MIMEText(body_text, "plain")
        msg["Subject"] = subject
        msg["From"]    = ctx["email_from"]
        msg["To"]      = to_addr
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as smtp:
            smtp.sendmail(ctx["email_from"], [to_addr], msg.as_string())
        return True
    except Exception:
        return False


def notify_reservation_confirmed(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = res["date"].strftime("%A, %B %d, %Y")
    s = res["start_time"].strftime("%-I:%M %p") if res.get("start_time") else ""
    e = res["end_time"].strftime("%-I:%M %p")   if res.get("end_time")   else ""
    return send_email(
        user["email"],
        f"{ctx['vehicle_noun'].title()} Reservation Confirmed — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your {ctx['vehicle_noun']} reservation is confirmed:\n\n"
        f"  Date: {d}\n"
        f"  Time: {s} – {e} CT\n\n"
        f"Before you head out, review the {ctx['checklist_name']}:\n"
        f"  {ctx['app_url']}/checklist\n\n"
        f"Manage your trips at: {ctx['app_url']}\n\n"
        f"{ctx['signature']}",
    )


def notify_reservation_cancelled(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = res["date"].strftime("%A, %B %d, %Y")
    return send_email(
        user["email"],
        f"{ctx['vehicle_noun'].title()} Reservation Cancelled — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your reservation for {d} has been cancelled.\n\n"
        f"Book again at: {ctx['app_url']}\n\n"
        f"{ctx['signature']}",
    )


def notify_reservation_approved(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = res["date"].strftime("%A, %B %d, %Y")
    s = res["start_time"].strftime("%-I:%M %p") if res.get("start_time") else ""
    e = res["end_time"].strftime("%-I:%M %p")   if res.get("end_time")   else ""
    return send_email(
        user["email"],
        f"{ctx['vehicle_noun'].title()} Reservation Approved — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your reservation request has been approved!\n\n"
        f"  Date: {d}\n"
        f"  Time: {s} – {e} CT\n\n"
        f"Before you head out, review the {ctx['checklist_name']}:\n"
        f"  {ctx['app_url']}/checklist\n\n"
        f"View it at: {ctx['app_url']}\n\n"
        f"{ctx['signature']}",
    )


def notify_approval_needed(admins: list, user: dict, res: dict):
    """Email all admins that a reservation needs approval."""
    ctx = _get_club_context()
    d = res["date"].strftime("%A, %B %d, %Y")
    for admin in admins:
        if admin.get("email"):
            send_email(
                admin["email"],
                f"Approval Needed — {user['full_name']}",
                f"A reservation request is waiting for approval:\n\n"
                f"  Member: {user['full_name']} ({user['username']})\n"
                f"  Date:   {d}\n\n"
                f"Review at: {ctx['app_url']}/admin/approvals\n\n"
                f"{ctx['signature']}",
            )


def notify_email_verify(user: dict, new_email: str, token: str) -> bool:
    ctx = _get_club_context()
    return send_email(
        new_email,
        f"Verify your new email — {ctx['club_name']}",
        f"Hi {user['full_name']},\n\n"
        f"You requested to change your {ctx['club_name']} email address to this one.\n\n"
        f"Click the link below to confirm (expires in 24 hours):\n\n"
        f"  {ctx['app_url']}/verify-email/{token}\n\n"
        f"If you did not request this, ignore this email. Your current address is unchanged.\n\n"
        f"{ctx['signature']}",
    )


def notify_welcome(user: dict, token: str) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    return send_email(
        user["email"],
        f"Welcome to {ctx['club_name']} — set your password",
        f"Hi {user['full_name']},\n\n"
        f"Your {ctx['club_name']} account has been created.\n\n"
        f"Click the link below to set your password and get started (expires in 72 hours):\n\n"
        f"  {ctx['app_url']}/set-password/{token}\n\n"
        f"If you have any questions, contact your club administrator.\n\n"
        f"{ctx['signature']}",
    )


def notify_password_reset(user: dict, token: str) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    return send_email(
        user["email"],
        f"Reset your {ctx['club_name']} password",
        f"Hi {user['full_name']},\n\n"
        f"We received a request to reset your password.\n\n"
        f"Click the link below to choose a new password (expires in 72 hours):\n\n"
        f"  {ctx['app_url']}/set-password/{token}\n\n"
        f"If you did not request this, you can safely ignore this email — your password has not changed.\n\n"
        f"{ctx['signature']}",
    )


def notify_weather_alert(user: dict, res_date, alerts: list) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = res_date.strftime("%A, %B %d, %Y")
    alert_lines = []
    for a in alerts:
        alert_lines.append(f"  ⚠ {a['event']} ({a['severity']})")
        alert_lines.append(f"     {a['headline']}")
        if a.get("instruction"):
            alert_lines.append(f"     {a['instruction'].splitlines()[0]}")
    alert_text = "\n".join(alert_lines)
    return send_email(
        user["email"],
        f"⚠ Weather Alert — Your {ctx['vehicle_noun'].title()} Reservation on {d}",
        f"Hi {user['full_name']},\n\n"
        f"There are active alerts for your area on the date of your reservation ({d}):\n\n"
        f"{alert_text}\n\n"
        f"Please review the conditions and decide whether to keep or cancel your reservation.\n\n"
        f"  Manage your trips: {ctx['app_url']}/reservations\n\n"
        f"Stay safe.\n\n"
        f"{ctx['signature']}",
    )


def notify_trip_reminder(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = res["date"].strftime("%A, %B %d, %Y")
    s = res["start_time"].strftime("%-I:%M %p") if res.get("start_time") else ""
    e = res["end_time"].strftime("%-I:%M %p")   if res.get("end_time")   else ""
    return send_email(
        user["email"],
        f"Reminder — {ctx['vehicle_noun'].title()} Reservation Tomorrow ({d})",
        f"Hi {user['full_name']},\n\n"
        f"Just a reminder that you have a {ctx['vehicle_noun']} reservation tomorrow:\n\n"
        f"  Date: {d}\n"
        f"  Time: {s} – {e} CT\n\n"
        f"Before you head out, review the {ctx['checklist_name']}:\n"
        f"  {ctx['app_url']}/checklist\n\n"
        f"On the day of your trip, use the Check Out button on your reservations\n"
        f"page to complete the pre-departure checklist:\n"
        f"  {ctx['app_url']}/my-reservations\n\n"
        f"Stay safe and have a great trip!\n\n"
        f"{ctx['signature']}",
    )


def notify_waitlist_available(user: dict, desired_date) -> bool:
    if not user.get("email"):
        return False
    ctx = _get_club_context()
    d = desired_date.strftime("%A, %B %d, %Y")
    return send_email(
        user["email"],
        f"{ctx['vehicle_noun'].title()} Available — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Good news! The {ctx['vehicle_noun']} is now available on {d}.\n\n"
        f"Book now (before someone else does):\n"
        f"{ctx['app_url']}/reserve/{desired_date}\n\n"
        f"{ctx['signature']}",
    )
