#!/usr/bin/env python3
"""
Weather alert check — run daily via cron.

Checks NWS alerts for Canyon Lake and emails any member with a reservation
in the next 48 hours if hazardous conditions are active.

Cron entry (runs at 6 AM daily):
  0 6 * * * /usr/bin/python3 /home/richard/projects/fleetnests/weather_check.py >> /var/log/bentley-weather.log 2>&1
"""

import os
import sys
import logging
from datetime import date, timedelta

# Bootstrap — find the app directory
APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

from dotenv import load_dotenv
load_dotenv()

import db
import models
import weather
import email_notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def main():
    log.info("Weather check starting")

    alerts = weather.get_active_alerts()
    if not alerts:
        log.info("No active weather alerts for Canyon Lake — nothing to do")
        return

    log.info("Active alerts: %s", [a["event"] for a in alerts])

    # Check reservations for today and the next 48 hours
    today = date.today()
    end   = today + timedelta(days=2)
    reservations = models.get_reservations_range(today, end)

    if not reservations:
        log.info("No upcoming reservations in the next 48 hours")
        return

    log.info("Found %d reservation(s) to notify", len(reservations))

    # Fetch user emails and notify each member once (deduplicate by user_id)
    notified = set()
    for res in reservations:
        user_id = res["user_id"]
        if user_id in notified:
            continue
        notified.add(user_id)

        user = models.get_user_by_id(user_id)
        if not user or not user.get("email"):
            log.warning("No email for user_id %s — skipping", user_id)
            continue

        ok = email_notify.notify_weather_alert(user, res["date"], alerts)
        if ok:
            log.info("Notified %s (%s) for reservation on %s",
                     user["full_name"], user["email"], res["date"])
        else:
            log.error("Failed to notify %s (%s)",
                      user["full_name"], user.get("email"))

    log.info("Weather check complete — %d member(s) notified", len(notified))


if __name__ == "__main__":
    main()
