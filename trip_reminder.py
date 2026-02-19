#!/usr/bin/env python3
"""
Pre-trip reminder — run daily via cron at 6 PM.

Emails any member with a reservation tomorrow so they can review
the Captain's Checklist and prepare for their trip.

Cron entry (runs at 6 PM daily):
  0 18 * * * /usr/bin/python3 /home/richard/projects/bentley-boat/trip_reminder.py >> /var/log/bentley-trip-reminder.log 2>&1
"""

import os
import logging
from datetime import date, timedelta

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

from dotenv import load_dotenv
load_dotenv()

import models
import email_notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def main():
    log.info("Trip reminder check starting")

    tomorrow = date.today() + timedelta(days=1)
    reservations = models.get_reservations_range(tomorrow, tomorrow)

    if not reservations:
        log.info("No reservations tomorrow — nothing to do")
        return

    log.info("Found %d reservation(s) for %s", len(reservations), tomorrow)

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

        ok = email_notify.notify_trip_reminder(user, res)
        if ok:
            log.info("Reminded %s (%s) for reservation on %s",
                     user["full_name"], user["email"], res["date"])
        else:
            log.error("Failed to remind %s (%s)",
                      user["full_name"], user.get("email"))

    log.info("Trip reminder complete — %d member(s) notified", len(notified))


if __name__ == "__main__":
    main()
