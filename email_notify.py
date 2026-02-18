"""
Email notifications for Bentley Boat Club.
Uses local Postfix (localhost:25) — no SMTP auth needed on same server.
Activate by setting EMAIL_ENABLED=true in .env.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_FROM    = os.environ.get("EMAIL_FROM", "noreply@hastingtx.org")
SMTP_HOST     = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "25"))
APP_URL       = os.environ.get("APP_URL", "https://hastingtx.org/boat")


def send_email(to_addr: str, subject: str, body_text: str) -> bool:
    """Send a plain-text email via local Postfix. Returns True on success."""
    if not EMAIL_ENABLED or not to_addr:
        return False
    try:
        msg = MIMEText(body_text, "plain")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = to_addr
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as smtp:
            smtp.sendmail(EMAIL_FROM, [to_addr], msg.as_string())
        return True
    except Exception:
        return False


def notify_reservation_confirmed(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    d = res["date"].strftime("%A, %B %d, %Y")
    s = res["start_time"].strftime("%-I:%M %p") if res.get("start_time") else ""
    e = res["end_time"].strftime("%-I:%M %p")   if res.get("end_time")   else ""
    return send_email(
        user["email"],
        f"Boat Reservation Confirmed — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your boat reservation is confirmed:\n\n"
        f"  Date: {d}\n"
        f"  Time: {s} – {e} CT\n\n"
        f"Manage your trips at: {APP_URL}\n\n"
        f"— Bentley Boat Club",
    )


def notify_reservation_cancelled(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    d = res["date"].strftime("%A, %B %d, %Y")
    return send_email(
        user["email"],
        f"Boat Reservation Cancelled — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your reservation for {d} has been cancelled.\n\n"
        f"Book again at: {APP_URL}\n\n"
        f"— Bentley Boat Club",
    )


def notify_reservation_approved(user: dict, res: dict) -> bool:
    if not user.get("email"):
        return False
    d = res["date"].strftime("%A, %B %d, %Y")
    s = res["start_time"].strftime("%-I:%M %p") if res.get("start_time") else ""
    e = res["end_time"].strftime("%-I:%M %p")   if res.get("end_time")   else ""
    return send_email(
        user["email"],
        f"Boat Reservation Approved — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Your reservation request has been approved!\n\n"
        f"  Date: {d}\n"
        f"  Time: {s} – {e} CT\n\n"
        f"View it at: {APP_URL}\n\n"
        f"— Bentley Boat Club",
    )


def notify_approval_needed(admins: list, user: dict, res: dict):
    """Email all admins that a reservation needs approval."""
    d = res["date"].strftime("%A, %B %d, %Y")
    for admin in admins:
        if admin.get("email"):
            send_email(
                admin["email"],
                f"Approval Needed — {user['full_name']}",
                f"A reservation request is waiting for approval:\n\n"
                f"  Member: {user['full_name']} ({user['username']})\n"
                f"  Date:   {d}\n\n"
                f"Review at: {APP_URL}/admin/approvals\n\n"
                f"— Bentley Boat Club",
            )


def notify_email_verify(user: dict, new_email: str, token: str) -> bool:
    """Send email verification link to the NEW address the member wants to switch to."""
    return send_email(
        new_email,
        "Verify your new email — Bentley Boat Club",
        f"Hi {user['full_name']},\n\n"
        f"You requested to change your Bentley Boat Club email address to this one.\n\n"
        f"Click the link below to confirm (expires in 24 hours):\n\n"
        f"  {APP_URL}/verify-email/{token}\n\n"
        f"If you did not request this, ignore this email. Your current address is unchanged.\n\n"
        f"— Bentley Boat Club",
    )


def notify_waitlist_available(user: dict, desired_date) -> bool:
    """Notify a waitlisted member that their desired date is now open."""
    if not user.get("email"):
        return False
    d = desired_date.strftime("%A, %B %d, %Y")
    return send_email(
        user["email"],
        f"Boat Available — {d}",
        f"Hi {user['full_name']},\n\n"
        f"Good news! The boat is now available on {d}.\n\n"
        f"Book now (before someone else does):\n"
        f"{APP_URL}/reserve/{desired_date}\n\n"
        f"— Bentley Boat Club",
    )
