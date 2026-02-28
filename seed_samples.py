#!/usr/bin/env python3
"""
Seed script for FleetNests sample sites.

Sample 1 — Summit Ridge Flying Club (Flagstaff, AZ)
  • Piper M600 (2023)    — tail N623MX
  • Cirrus SR22T (2021)  — tail N421CR
  • 10 members

Sample 2 — Clearwater Boat Club (Lake Geneva, WI)
  • Catalina 275 Sport (2017)   — hull CYWL2791D717
  • Bennington 24 SSBXP (2024)  — hull BNNA5240D424
  • MasterCraft X22 (2026)      — hull MCFT2260D626
  • 14 members
"""

import os, random, sys, json
from datetime import date, datetime, timedelta
import psycopg2
import psycopg2.extras
import bcrypt

# ── connection helpers ────────────────────────────────────────────────────────

def conn1():
    return psycopg2.connect(
        "postgresql://fn_sample1_user:S4mpl3One!2026@127.0.0.1:5432/fn_sample1",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

def conn2():
    return psycopg2.connect(
        "postgresql://fn_sample2_user:S4mpl3Two!2026@127.0.0.1:5432/fn_sample2",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

def hashpw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

# ── utility ───────────────────────────────────────────────────────────────────

TODAY = date.today()
START = TODAY - timedelta(days=365)   # 12 months back
END   = TODAY + timedelta(days=61)    # ~2 months forward

rng = random.Random(42)   # reproducible

def rand_date(start=START, end=END):
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))

def past_date(days_ago_min, days_ago_max):
    return TODAY - timedelta(days=rng.randint(days_ago_min, days_ago_max))

def future_date(days_min, days_max):
    return TODAY + timedelta(days=rng.randint(days_min, days_max))

def rand_time(h_min=7, h_max=18):
    return f"{rng.randint(h_min, h_max):02d}:{rng.choice(['00','15','30','45'])}:00"

def rand_choice(lst):
    return rng.choice(lst)

# ── sample 1: Summit Ridge Flying Club ───────────────────────────────────────

MEMBERS_S1 = [
    # (username, full_name, email, is_admin)
    ("jwilson",   "James Wilson",      "jwilson@summitridgeflying.com",    True),
    ("sarah_m",   "Sarah Martinez",    "smartinez@summitridgeflying.com",  False),
    ("dpatel",    "Dev Patel",         "dpatel@summitridgeflying.com",     False),
    ("lchen",     "Linda Chen",        "lchen@summitridgeflying.com",      False),
    ("bkowalski", "Brian Kowalski",    "bkowalski@summitridgeflying.com",  False),
    ("emorgan",   "Emma Morgan",       "emorgan@summitridgeflying.com",    False),
    ("tgriffin",  "Tom Griffin",       "tgriffin@summitridgeflying.com",   False),
    ("anakamura", "Akira Nakamura",    "anakamura@summitridgeflying.com",  False),
    ("cjohnson",  "Carol Johnson",     "cjohnson@summitridgeflying.com",   False),
    ("rfoster",   "Rob Foster",        "rfoster@summitridgeflying.com",    False),
]

VEHICLES_S1 = [
    {
        "name": "Piper M600",
        "vehicle_type": "plane",
        "tail_number": "N623MX",
        "registration_number": "N623MX",
        "hull_id": "4698109",
        "current_hours": 1247.3,   # 3-yr-old Piper M600, active club use
    },
    {
        "name": "Cirrus SR22T",
        "vehicle_type": "plane",
        "tail_number": "N421CR",
        "registration_number": "N421CR",
        "hull_id": "2208056",
        "current_hours": 843.7,    # 5-yr-old SR22T
    },
]

DESTINATIONS_S1 = [
    "KPHX Phoenix Sky Harbor", "KLAS Las Vegas Harry Reid",
    "KLAX Los Angeles Intl", "KSAN San Diego Intl", "KDEN Denver Intl",
    "KSFO San Francisco Intl", "KSLC Salt Lake City", "KABQ Albuquerque",
    "KTUS Tucson Intl", "KPRC Prescott", "KSEZ Sedona", "KGCN Grand Canyon",
    "KOAK Oakland Intl", "KBUR Burbank", "KSMF Sacramento",
]

CONDITIONS = ["Excellent", "Good", "Good", "Good", "Good – minor cleaning needed"]
FUEL_TYPES_PLANE = ["100LL", "Jet-A"]

ANNOUNCEMENTS_S1 = [
    ("Annual Safety Meeting – March 15", "Reminder: our annual safety and IFR currency meeting is March 15 at 7 PM in the FBO lounge. Attendance is strongly encouraged for all club members. CFI guest speaker will cover approaches in IMC."),
    ("M600 Annual Inspection Complete", "The Piper M600 (N623MX) has completed its annual inspection and is back in service. All squawks resolved. Avionics database updated to current cycle."),
    ("New Online Scheduling System", "We've upgraded to FleetNests for scheduling. Your login credentials were sent by email. Please update your recurring reservations by end of month."),
    ("Fuel Price Update – Effective April 1", "100LL is now $6.85/gal and Jet-A is $5.70/gal at our FBO. Prices are reviewed monthly. Thank you for your patience with recent increases."),
    ("SR22T Maintenance Window – May 3-5", "The Cirrus SR22T (N421CR) will be unavailable May 3–5 for scheduled alternator replacement and pitot-static recertification. Please plan accordingly."),
    ("Summer Flying Season Reminder", "As temperatures rise, please review density altitude procedures. Flagstaff's 7,014 ft elevation makes summer DA calculations critical. See the pinned document in Files."),
    ("Congrats to Dev – Instrument Rating!", "The club congratulates Dev Patel on earning his Instrument Rating last weekend! First approach to minimums in actual IMC – impressive work, Dev!"),
    ("Holiday Schedule", "The club office and FBO will be closed December 24-25. Aircraft reservations remain available via the app. Emergency contact: James Wilson 928-555-0147."),
]

MESSAGES_S1 = [
    ("Question about M600 autopilot", "Has anyone had issues with the AFCS disconnecting during cruise climb above FL250? Got a subtle lateral oscillation yesterday. Logged it in the squawk book but wanted to check if others have noticed."),
    ("SR22T – great trip to Sedona", "Just back from a perfect day trip to Sedona in the SR22T. Visibility was unlimited, winds calm. Traffic pattern was busy with helicopters but otherwise textbook. Highly recommend the Tuesday morning slot if you want the ramp to yourself."),
    ("Currency check reminder", "Quick reminder – if you haven't flown the M600 in 90 days you'll need a currency flight with our club CFI before solo reservations. Check your logbook!"),
    ("IFR flight plan tip", "For those filing to PHX, I've been using the LINND3 arrival and it's been really smooth. Tower has been assigning runway 26 lately so plan for that."),
    ("Hangar space question", "Anyone know if there's a waiting list for the covered tiedowns? Looking to move my personal aircraft here as well."),
]


# ── sample 2: Clearwater Boat Club ───────────────────────────────────────────

MEMBERS_S2 = [
    ("rbennett",   "Rachel Bennett",    "rbennett@clearwaterboatclub.com",    True),
    ("mthompson",  "Mike Thompson",     "mthompson@clearwaterboatclub.com",   False),
    ("janderson",  "Julie Anderson",    "janderson@clearwaterboatclub.com",   False),
    ("cdavis",     "Chris Davis",       "cdavis@clearwaterboatclub.com",      False),
    ("lmiller",    "Lauren Miller",     "lmiller@clearwaterboatclub.com",     False),
    ("swilliams",  "Steve Williams",    "swilliams@clearwaterboatclub.com",   False),
    ("klee",       "Karen Lee",         "klee@clearwaterboatclub.com",        False),
    ("gjackson",   "Greg Jackson",      "gjackson@clearwaterboatclub.com",    False),
    ("aharris",    "Amy Harris",        "aharris@clearwaterboatclub.com",     False),
    ("bmartin",    "Bob Martin",        "bmartin@clearwaterboatclub.com",     False),
    ("ngarcia",    "Nina Garcia",       "ngarcia@clearwaterboatclub.com",     False),
    ("dwatson",    "Dan Watson",        "dwatson@clearwaterboatclub.com",     False),
    ("pwhite",     "Paula White",       "pwhite@clearwaterboatclub.com",      False),
    ("tcook",      "Tom Cook",          "tcook@clearwaterboatclub.com",       False),
]

VEHICLES_S2 = [
    {
        "name": "Catalina 275 Sport",
        "vehicle_type": "boat",
        "hull_id": "CYWL2791D717",
        "registration_number": "WI4821TM",
        "tail_number": None,
        "current_hours": 412.0,   # 2017 sailboat, steady use
    },
    {
        "name": "Bennington 24 SSBXP",
        "vehicle_type": "boat",
        "hull_id": "BNNA5240D424",
        "registration_number": "WI7734TM",
        "tail_number": None,
        "current_hours": 87.5,    # 2024 pontoon, newer
    },
    {
        "name": "MasterCraft X22",
        "vehicle_type": "boat",
        "hull_id": "MCFT2260D626",
        "registration_number": "WI0091TM",
        "tail_number": None,
        "current_hours": 23.2,    # 2026 wakeboard boat, brand new
    },
]

DESTINATIONS_S2 = [
    "Fontana Bay", "Big Foot Beach", "Williams Bay Marina", "Delavan Lake",
    "Trinke Lagoon", "Black Point", "The Narrows", "Geneva Bay Sandbar",
    "Riviera Docks", "Sailboat race buoy field",
]

CONDITIONS_BOAT = ["Excellent", "Good", "Good", "Good", "Good – needs rinse"]

ANNOUNCEMENTS_S2 = [
    ("Spring Commissioning Weekend – April 26-27", "All hands on deck! Club workday to launch the boats and prep the docks. Lunch provided. Please sign up for a 2-hour shift on the club website so we can coordinate volunteers."),
    ("New MasterCraft X22 in the Fleet!", "We're thrilled to welcome our 2026 MasterCraft X22 'Whitecap' to the Clearwater fleet. The X22 is our premium wakeboard/surf boat with 440-hp Ilmor engine and Gen2 surf system. Orientation sessions are required before first reservation — sign up in the app."),
    ("Catalina Mast Work Complete", "The Catalina 275 Sport mast has been unstepped and restepped following forestay replacement and VHF antenna cable repair. She's back in service and ready for the season."),
    ("Lake Geneva Water Level Advisory", "WDNR reports lake level is currently 2 inches above normal. No navigation concerns but be mindful of shallows near the north beach at Fontana Bay."),
    ("Labor Day Regatta – Sept 1", "The annual Labor Day Regatta is on! All sailboat owners and Catalina reservations that day will participate. Non-racers welcome as spectator boats. Contact Rachel to register your crew."),
    ("Winter Storage Deposits Due Nov 1", "Winter storage deposits are due November 1. Please submit your $250 deposit to hold your slip for next season. Contact the club office for payment options."),
    ("Boat Safety Course – Offered June 7", "Wisconsin DNR-approved boating safety course offered June 7 at the Lake Geneva Public Library. Required for operators born after 1989. All new members encouraged to attend."),
    ("Pontoon Capacity Reminder", "The Bennington 24 SSBXP is rated for 11 persons maximum. This includes crew. Please respect this limit — it is federal law and club policy. Overloading will result in suspension of reservation privileges."),
]

MESSAGES_S2 = [
    ("Wakeboard orientation spots available", "Two spots left for Saturday's MasterCraft X22 orientation. First time operators must attend before reserving the X22. Reply here or sign up in the app."),
    ("Catalina tip – Sunday afternoon slot", "FYI the Sunday afternoon Catalina slot is magic right now. SW breeze, 10-14 kts, perfect close reach across the lake. Highly recommend if you haven't gotten out yet this season."),
    ("Bennington – great for the 4th", "Took the pontoon out for the fireworks cruise last night with 9 people and it was perfect. Anchored just north of the Riviera. Best view on the lake. Already reserved it for next year!"),
    ("X22 surf system question", "Can anyone walk me through switching between goofy and regular surf wave? I read the manual but the app on the touchscreen is different from what the manual shows."),
    ("Fuel reminder at Fontana Bay", "Heads up – the fuel dock at Fontana Bay closed early on Saturday (ran out of premium unleaded). Suggest fueling at Riviera if you're planning a longer trip."),
    ("Fall sailing conditions", "Getting some great fall sailing in. Yesterday had steady 15 kts and 60°F. Catalina handled beautifully on a beam reach to Williams Bay and back. Don't put her away too soon!"),
]


# ── generic seed function ─────────────────────────────────────────────────────

def seed_club(get_conn, members, vehicles, destinations, conditions,
              announcements, messages, primary_color, accent_color):

    db = get_conn()
    cur = db.cursor()

    # ── clear existing data ──────────────────────────────────────────────────
    for tbl in ["fuel_log", "trip_logs", "reservations", "vehicles",
                "messages", "users", "club_branding", "club_photos", "vehicle_photos"]:
        cur.execute(f"DELETE FROM {tbl}")
    db.commit()

    # ── users ────────────────────────────────────────────────────────────────
    user_ids = []
    pw = hashpw("FleetNests2026!")
    for username, full_name, email, is_admin in members:
        cur.execute("""
            INSERT INTO users (username, full_name, email, password_hash, is_admin, is_active,
                               display_name, max_consecutive_days, max_pending)
            VALUES (%s,%s,%s,%s,%s,true,%s,7,3) RETURNING id
        """, (username, full_name, email, pw, is_admin, full_name.split()[0]))
        user_ids.append(cur.fetchone()["id"])
    db.commit()
    print(f"  {len(user_ids)} users created")

    # ── vehicles ─────────────────────────────────────────────────────────────
    vehicle_ids = []
    vehicle_hours = []
    for v in vehicles:
        cur.execute("""
            INSERT INTO vehicles (name, vehicle_type, hull_id, registration_number,
                                  tail_number, current_hours, is_active)
            VALUES (%s,%s,%s,%s,%s,%s,true) RETURNING id
        """, (v["name"], v["vehicle_type"], v["hull_id"],
              v["registration_number"], v["tail_number"], v["current_hours"]))
        vehicle_ids.append(cur.fetchone()["id"])
        vehicle_hours.append(float(v["current_hours"]))
    db.commit()
    print(f"  {len(vehicle_ids)} vehicles created")

    # ── reservations, trip logs, fuel logs ───────────────────────────────────
    # Build a calendar of reservations spanning START → END
    # Each day, randomly assign 0–2 reservations across vehicles
    res_count = 0
    trip_count = 0
    fuel_count = 0

    # We'll track "hours accrued" per vehicle as we go backwards
    # (since current_hours is "now", older reservations used fewer hours)
    hours_at_now = list(vehicle_hours)

    # Generate reservation slots
    current = START
    while current <= END:
        for vi, vid in enumerate(vehicle_ids):
            # ~35% chance of a reservation each day per vehicle
            if rng.random() > 0.35:
                current = current + timedelta(days=1) if vi == len(vehicle_ids)-1 else current
                continue

            uid = rng.choice(user_ids)

            # Duration: 2–8 hours for planes, half-day or full day for boats
            if vehicles[vi]["vehicle_type"] == "plane":
                duration_h = rng.choice([2, 3, 3, 4, 4, 5, 6, 8])
            else:
                duration_h = rng.choice([3, 4, 4, 5, 6, 8, 8])

            start_h = rng.randint(7, 16)
            start_dt = datetime(current.year, current.month, current.day,
                                start_h, rng.choice([0, 0, 30]), 0)
            end_dt = start_dt + timedelta(hours=duration_h)

            is_past = current < TODAY
            status = "active" if is_past else rng.choice(["active", "active", "active", "pending_approval"])
            if current < TODAY - timedelta(days=1):
                status = "active"   # all historical = active

            cur.execute("""
                INSERT INTO reservations
                  (user_id, vehicle_id, date, start_time, end_time, status, notes, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (uid, vid, current, start_dt, end_dt, status,
                  rng.choice([""] * 3 + [f"Trip to {rng.choice(destinations)}"]),
                  start_dt - timedelta(days=rng.randint(1, 14))))
            res_id = cur.fetchone()["id"]
            res_count += 1

            # Trip log for completed past reservations
            if is_past and status == "active" and rng.random() < 0.85:
                hours_used = round(duration_h * rng.uniform(0.9, 1.1), 1)
                hours_out = round(hours_at_now[vi] - hours_used, 1)
                hours_in  = round(hours_at_now[vi], 1)
                hours_at_now[vi] = max(0.0, hours_at_now[vi] - hours_used)

                fuel_gallons = round(hours_used * rng.uniform(8, 20) if vehicles[vi]["vehicle_type"] == "plane"
                                     else hours_used * rng.uniform(4, 12), 1)
                fuel_cost = round(fuel_gallons * (6.85 if vehicles[vi]["vehicle_type"] == "plane" else 3.95), 2)

                cur.execute("""
                    INSERT INTO trip_logs
                      (res_id, vehicle_id, user_id, checkout_time, primary_hours_out,
                       fuel_level_out, condition_out, checklist_items,
                       checkin_time, primary_hours_in, fuel_added_gallons,
                       fuel_added_cost, condition_in, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (res_id, vid, uid,
                      start_dt, hours_out,
                      rng.choice(["Full","3/4","1/2","1/4"]),
                      rng.choice(conditions),
                      '{}',
                      end_dt, hours_in,
                      fuel_gallons, fuel_cost,
                      rng.choice(conditions),
                      end_dt + timedelta(minutes=15)))
                trip_count += 1

                # Fuel log entry (~60% of trip logs)
                if rng.random() < 0.60:
                    ppg = round(rng.uniform(6.50, 7.20) if vehicles[vi]["vehicle_type"] == "plane"
                                else rng.uniform(3.75, 4.15), 2)
                    gal = round(fuel_gallons * rng.uniform(0.4, 0.9), 1)
                    cur.execute("""
                        INSERT INTO fuel_log
                          (user_id, vehicle_id, res_id, log_date, gallons,
                           price_per_gallon, total_cost, notes, created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (uid, vid, res_id, current, gal, ppg,
                          round(gal * ppg, 2),
                          rng.choice(["", "", f"Fueled at {rng.choice(destinations).split()[0]}"]),
                          end_dt + timedelta(minutes=30)))
                    fuel_count += 1

        current += timedelta(days=1)

    db.commit()
    print(f"  {res_count} reservations, {trip_count} trip logs, {fuel_count} fuel log entries")

    # ── announcements ────────────────────────────────────────────────────────
    admin_uid = user_ids[0]
    ann_dates = sorted([past_date(10, 365) for _ in announcements], reverse=True)
    for i, (title, body) in enumerate(announcements):
        ann_dt = datetime.combine(ann_dates[i], datetime.min.time()) + timedelta(hours=9)
        cur.execute("""
            INSERT INTO messages (user_id, title, body, is_announcement, created_at, updated_at)
            VALUES (%s,%s,%s,true,%s,%s)
        """, (admin_uid, title, body, ann_dt, ann_dt))

    # ── member messages ──────────────────────────────────────────────────────
    msg_dates = sorted([past_date(1, 90) for _ in messages], reverse=True)
    for i, (title, body) in enumerate(messages):
        uid = rng.choice(user_ids)
        msg_dt = datetime.combine(msg_dates[i], datetime.min.time()) + timedelta(hours=rng.randint(8,20))
        cur.execute("""
            INSERT INTO messages (user_id, title, body, is_announcement, created_at, updated_at)
            VALUES (%s,%s,%s,false,%s,%s)
        """, (uid, title, body, msg_dt, msg_dt))

    db.commit()
    print(f"  {len(announcements)} announcements + {len(messages)} messages")

    # ── club branding ────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO club_branding (primary_color, accent_color)
        VALUES (%s,%s)
        ON CONFLICT DO NOTHING
    """, (primary_color, accent_color))
    db.commit()

    cur.close()
    db.close()


# ── club settings (rules, checklist, contact info) ───────────────────────────

def upsert_setting(cur, key, value):
    cur.execute("""
        INSERT INTO club_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, value))

RULES_S1 = [
    "Membership in Summit Ridge Flying Club is open to certificated pilots in good standing. All members must maintain at least a Private Pilot certificate (ASEL) and a valid medical.",
    "<strong>Complete the Pre-Flight Checklist before every flight</strong> — no exceptions, regardless of experience level or familiarity with the aircraft.",
    "Log all Hobbs time accurately in the aircraft logbook and in FleetNests. Any discrepancy must be reported to a club officer before leaving the ramp.",
    "Return with at least <strong>1 hour VFR fuel reserve / 45 min IFR fuel reserve</strong>. Top off at destination when practical. Both aircraft use 100LL only.",
    "All squawks, write-ups, and maintenance concerns must be entered in the aircraft maintenance log before leaving the aircraft. If the aircraft is unairworthy, ground it and notify the Safety Officer immediately.",
    "Members must be current per FAR 61.56 (BFR) and 61.57 (recency of experience). Notify the club immediately if any currency or certificate lapses — you may not fly club aircraft until restored.",
    "High-altitude and mountain flying: Flagstaff sits at 7,014 ft MSL. All members must review density altitude procedures and complete the club's Mountain Flying endorsement before flying the M600 above FL250.",
    "The Pilot-in-Command is solely responsible for the safe operation of the aircraft, all persons aboard, and compliance with all applicable FARs. Non-pilot passengers may accompany members after signing the club liability waiver.",
    "Aircraft must be returned clean and ready for the next member. Wipe down surfaces after dusty or wet flights. Leave the cockpit as you found it.",
    "Monthly dues of $425 (M600) or $280 (SR22T) are due on the 1st. Members more than 30 days past due may not reserve aircraft until the account is current. Contact Treasurer James Wilson with billing questions.",
    "Any incident, accident, or ATC enforcement action must be reported to the club Safety Officer within 24 hours. Cooperation with any NTSB or FAA investigation is mandatory.",
    "The club Safety Officer has final authority on all airworthiness and safety matters. Any member may ground an aircraft they believe to be unsafe — no questions asked.",
]

CHECKLIST_S1 = {
    "items": [
        "AROW documents confirmed in aircraft: Airworthiness certificate, Registration, Operating handbook (POH/AFM), Weight & balance.",
        "Fuel: Visually verify quantity in both tanks. Verify 100LL. Sump fuel from all drain points — check for water or contamination.",
        "Oil: Check level (M600: 12–14 qt; SR22T: 7–8 qt). Inspect for leaks. Secure oil cap.",
        "Exterior walk-around: Flight controls, static ports, pitot tube (remove cover), antennas, landing gear/tires, lights, prop for nicks or cracks.",
        "Oxygen (M600 only): Check O₂ quantity if planning flight above 12,500 MSL. Connect masks and verify flow.",
        "Avionics: Verify database currency. Set altimeter — Flagstaff field elevation 7,014 ft MSL.",
        "Engine start per POH/AFM. Monitor oil pressure (green arc within 30 sec).",
        "ATIS received. Clearance obtained if IFR. Transponder set and confirmed with tower.",
        "Taxi check: Controls free and correct, flight instruments alive, brakes checked.",
        "Run-up: Magnetos checked, prop cycle, all engine instruments in green.",
        "Before takeoff briefing: Abort point, emergency return plan, passengers briefed on exits and safety equipment.",
        "Post-landing: Taxi clear of runway, complete after-landing checklist, transponder to GND/STBY.",
        "Shutdown: Log Hobbs time before shutdown. Complete engine shutdown per POH. Secure aircraft: control lock, master off, chocks, tie-downs.",
        "Squawk book: Record any discrepancies before leaving. If any system is inoperative, placard it per MEL/POH.",
    ],
    "categories": [],
    "disclaimer": "Aviation involves inherent risks. The Pilot-in-Command accepts full responsibility for the safe operation of the aircraft and compliance with all applicable FARs. Summit Ridge Flying Club, its officers, and members shall not be liable for any injury, death, or property damage arising from the use of club aircraft.",
}

RULES_S2 = [
    "Membership is open to individuals 18 or older. All operators must hold a valid Wisconsin Boating Safety Certificate (required by DNR for anyone born after 1989) before operating any club vessel.",
    "<strong>Complete the Captain's Checklist before every departure</strong> — no exceptions. A thorough pre-departure check prevents the majority of on-water incidents.",
    "Life jackets: Ensure an appropriately-sized USCG-approved PFD is available and accessible for every person aboard before leaving the dock. Children under 13 must wear their PFD at all times underway.",
    "Return all vessels with a <strong>full fuel tank</strong>. Fuel up at Riviera Marina or Fontana Bay before returning to the slip. Log gallons added in FleetNests.",
    "Vessel capacity: The Bennington 24 SSBXP is rated for <strong>11 persons maximum</strong>. The Catalina 275 Sport: 6 persons. The MasterCraft X22: 15 persons (surf config: 6 recommended). Never exceed posted capacity.",
    "MasterCraft X22 orientation required: No member may operate the X22 without completing the club's ballast and surf-system orientation session with a certified instructor. Sign up in FleetNests.",
    "Speed limits: Observe Wisconsin's <strong>no-wake within 100 ft of shore</strong> and all posted limits. Lake Geneva enforces a 35 MPH limit in open water. Wakeboarding is permitted in designated areas only.",
    "Weather: If NOAA issues a Small Craft Advisory or Thunderstorm Watch for Lake Geneva, return to dock immediately. Monitor VHF Ch. 16. Do not depart if lightning is visible within 10 miles.",
    "Damage: Any collision, grounding, equipment failure, or injury must be reported to Club Manager Rachel Bennett within 2 hours. Document with photos. Members are responsible for damages caused during their reservation.",
    "Cleanliness: Rinse the vessel with fresh water after every use. Remove all personal items and trash. Leave the cockpit, cabin, and head (Catalina) clean for the next member.",
    "Monthly dues are due on the 1st. Members more than 30 days past due may not make reservations until the account is current. Contact Rachel Bennett with billing questions.",
    "The Club Manager has final authority on all safety, maintenance, and conduct matters. Any member may remove a vessel from service if they believe it is unsafe — notify the club immediately.",
]

CHECKLIST_S2 = {
    "items": [
        "Life jackets: Count PFDs — one per person. Children's PFDs are in the forward compartment (Catalina) or under port seat (Bennington, X22).",
        "Fuel: Check level gauge. Plan to return full. Catalina: diesel at Riviera. Bennington/X22: premium unleaded at Fontana Bay or Riviera.",
        "Engine: Check oil level (X22: before every trip). Inspect raw water strainer (Catalina). Check bilge — pump out if any standing water.",
        "Safety equipment: Fire extinguisher (port side). Flares (check expiry date). Throwable cushion. First-aid kit.",
        "Electronics: VHF radio on and tested on Ch. 16. Navigation lights functional (required after sunset). GPS on.",
        "Lines and fenders: All dock lines and fenders stowed or aboard. Shore power cord removed (Catalina) and stowed.",
        "Blower: Run engine blower minimum 4 minutes before starting gas engines (Bennington, X22). Check for fuel smell before proceeding.",
        "Engine start: Normal start per vessel manual. Confirm water flow from exhaust (cooling). Idle warm-up 3–5 minutes.",
        "Cast off: Walk the dock — confirm no lines, fenders, or obstacles fouling the hull or prop.",
        "Underway check: Throttle, steering, bilge pump switch, all instruments normal. No-wake until clear of marina channel.",
        "X22 ballast (if surfing): Enable Surf System. Activate ballast fill per goofy/regular selection. Follow club guidelines on max ballast for Lake Geneva.",
        "Return: No-wake approaching slip. Flush engine with fresh water if applicable. Log trip and fuel in FleetNests. Fuel up before returning if under ½ tank.",
        "Secure: Lines bow and stern. Shore power connected (Catalina). Bimini up (Bennington). Cover snapped. Log any squawks in FleetNests before leaving.",
    ],
    "categories": [],
    "disclaimer": "Boating involves inherent risks. The Captain and all passengers accept responsibility for any damage, injury, or claims arising from use of Clearwater Boat Club vessels, and agree to indemnify and hold the club, its officers, and members harmless. The club shall not be liable for any physical, financial, or other damages.",
}


def seed_settings(get_conn, rules, checklist, phone_key, phone_val, extra_settings=None):
    db = get_conn()
    cur = db.cursor()
    upsert_setting(cur, "member_rules_json", json.dumps(rules))
    upsert_setting(cur, "checklist_json", json.dumps(checklist))
    upsert_setting(cur, phone_key, phone_val)
    for k, v in (extra_settings or {}).items():
        upsert_setting(cur, k, v)
    db.commit()
    cur.close()
    db.close()


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Seeding Sample 1 — Summit Ridge Flying Club …")
    seed_club(
        conn1, MEMBERS_S1, VEHICLES_S1, DESTINATIONS_S1, CONDITIONS,
        ANNOUNCEMENTS_S1, MESSAGES_S1,
        primary_color="#1A3A5C",   # deep aviation blue
        accent_color="#D4AF37",    # gold
    )
    seed_settings(conn1, RULES_S1, CHECKLIST_S1,
                  phone_key="fbo_phone", phone_val="928-213-2900",
                  extra_settings={"aviation_station": "KFLG"})

    print("\nSeeding Sample 2 — Clearwater Boat Club …")
    seed_club(
        conn2, MEMBERS_S2, VEHICLES_S2, DESTINATIONS_S2, CONDITIONS_BOAT,
        ANNOUNCEMENTS_S2, MESSAGES_S2,
        primary_color="#005F6B",   # teal/lake green
        accent_color="#F4A261",    # warm coral/orange
    )
    seed_settings(conn2, RULES_S2, CHECKLIST_S2,
                  phone_key="marina_phone", phone_val="262-248-6200",
                  extra_settings={"weather_zone": "WIZ064", "nws_county": "WIC127"})

    print("\nDone.")
