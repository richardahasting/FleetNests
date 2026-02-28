"""
Vehicle-type constants and context builders for FleetNests.

All the constants that were hardcoded in models.py (CAPTAIN_CHECKLIST,
FUEL_LEVELS, MARINA_PHONE, etc.) now live here and are parameterized
by vehicle_type ('boat' | 'plane').

Templates receive these via app.py's context_processor.
"""

import json
import logging
import master_db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fuel levels — boats use an enum, planes track gallons added (no level enum)
# ---------------------------------------------------------------------------

FUEL_LEVELS_BOAT = {
    "empty":          ("Empty", "danger"),
    "quarter":        ("¼",     "warning"),
    "half":           ("½",     "warning"),
    "three_quarters": ("¾",     "success"),
    "full":           ("Full",  "success"),
}

FUEL_LEVELS_PLANE = {}   # planes don't use a fuel-level enum at checkout


def get_fuel_levels(vehicle_type: str) -> dict:
    return FUEL_LEVELS_BOAT if vehicle_type == "boat" else FUEL_LEVELS_PLANE


# ---------------------------------------------------------------------------
# Weather alert event sets
# ---------------------------------------------------------------------------

ALERT_EVENTS_BOAT = {
    "Tornado Warning", "Tornado Watch",
    "Severe Thunderstorm Warning", "Severe Thunderstorm Watch",
    "Flash Flood Warning", "Flash Flood Watch",
    "Flood Warning", "Flood Watch",
    "Wind Advisory", "High Wind Warning", "High Wind Watch",
    "Small Craft Advisory", "Small Craft Advisory for Hazardous Seas",
    "Excessive Heat Warning", "Excessive Heat Watch", "Heat Advisory",
    "Dense Fog Advisory",
}

ALERT_EVENTS_PLANE = {
    "Tornado Warning", "Tornado Watch",
    "Severe Thunderstorm Warning", "Severe Thunderstorm Watch",
    "Wind Advisory", "High Wind Warning", "High Wind Watch",
    "Dense Fog Advisory",
    "Airmet Sierra",   # IFR conditions
    "Airmet Tango",    # Turbulence
    "Airmet Zulu",     # Icing
    "Sigmet",
    "Special Marine Warning",
}


def get_alert_events(vehicle_type: str) -> set:
    return ALERT_EVENTS_BOAT if vehicle_type == "boat" else ALERT_EVENTS_PLANE


# ---------------------------------------------------------------------------
# UI labels that differ between vehicle types
# ---------------------------------------------------------------------------

def get_hours_label(vehicle_type: str) -> str:
    """Label for the hours meter field (motor hours vs Hobbs hours)."""
    return "Motor Hours" if vehicle_type == "boat" else "Hobbs Hours"


def get_vehicle_noun(vehicle_type: str) -> str:
    """Singular noun: 'boat' or 'aircraft'."""
    return "boat" if vehicle_type == "boat" else "aircraft"


def get_checklist_name(vehicle_type: str) -> str:
    return "Captain's Checklist" if vehicle_type == "boat" else "Pre-Flight Checklist"


def get_contact_phone_label(vehicle_type: str) -> str:
    return "Marina Phone" if vehicle_type == "boat" else "FBO Phone"


def get_contact_phone_key(vehicle_type: str) -> str:
    """club_settings key for the contact phone number."""
    return "marina_phone" if vehicle_type == "boat" else "fbo_phone"


# ---------------------------------------------------------------------------
# Checklist — loaded from club_settings or master template
# ---------------------------------------------------------------------------

def get_club_checklist(vehicle_type: str, settings: dict) -> tuple[list, list, str]:
    """
    Return (checklist_items, categories, disclaimer).

    Priority:
      1. club_settings['checklist_json'] (club-specific override stored as JSON)
      2. Master DB default template for vehicle_type
      3. Hardcoded fallback (empty list)
    """
    raw = settings.get("checklist_json")
    if raw:
        try:
            data = json.loads(raw)
            return (
                data.get("items", []),
                data.get("categories", []),
                data.get("disclaimer", ""),
            )
        except (json.JSONDecodeError, TypeError):
            log.warning("Invalid checklist_json in club_settings — falling back to master template")

    # Fall back to master template
    try:
        tmpl = master_db.get_default_template(vehicle_type)
        if tmpl:
            items = tmpl["checklist_items"]
            cats  = tmpl["categories"]
            # psycopg2 may return these as dicts already (JSONB) or as strings
            if isinstance(items, str):
                items = json.loads(items)
            if isinstance(cats, str):
                cats = json.loads(cats)
            # Normalize categories to (label, indices) tuples for template compatibility
            cat_tuples = [(c["label"], c["indices"]) for c in cats]
            return items, cat_tuples, tmpl.get("disclaimer") or ""
    except Exception as exc:
        log.error("Could not load master template for %s: %s", vehicle_type, exc)

    return [], [], ""


# ---------------------------------------------------------------------------
# Per-club feature flag helper
# ---------------------------------------------------------------------------

def _setting_bool(settings: dict, key: str, default: bool) -> bool:
    """Read a boolean club_setting, falling back to a type-based default."""
    val = settings.get(key)
    return default if val is None else val.lower() == "true"


# ---------------------------------------------------------------------------
# Full checkout context builder
# ---------------------------------------------------------------------------

def build_checkout_context(vehicle_type: str, settings: dict) -> dict:
    """
    Build the complete context dict injected into checkout.html and checkin.html.
    Feature flags are resolved from club_settings first, then fall back to
    type-based defaults so any club can override the vehicle-type behaviour.
    """
    items, categories, disclaimer = get_club_checklist(vehicle_type, settings)
    phone_key = get_contact_phone_key(vehicle_type)

    has_hours  = _setting_bool(settings, "has_hours_meter",        vehicle_type == "plane")
    hours_lbl  = settings.get("hours_label") or get_hours_label(vehicle_type)
    fuel_enum  = _setting_bool(settings, "has_fuel_level_enum",    vehicle_type == "boat")
    fuel_req   = _setting_bool(settings, "fuel_required_on_return", vehicle_type == "plane")

    return {
        "CHECKLIST_ITEMS":         items,
        "CHECKLIST_CATEGORIES":    categories,
        "DISCLAIMER":              disclaimer,
        "FUEL_LEVELS":             get_fuel_levels(vehicle_type),
        "HOURS_LABEL":             hours_lbl,
        "CONTACT_PHONE_LABEL":     get_contact_phone_label(vehicle_type),
        "CONTACT_PHONE":           settings.get(phone_key, ""),
        "CHECKLIST_NAME":          get_checklist_name(vehicle_type),
        "show_fuel_level":         fuel_enum,
        "show_hours_meter":        has_hours,
        "fuel_required_on_return": fuel_req,
        "vehicle_noun":            get_vehicle_noun(vehicle_type),
    }


# ---------------------------------------------------------------------------
# Weather zone parameters
# ---------------------------------------------------------------------------

def get_weather_zone_params(vehicle_type: str, settings: dict) -> dict:
    """
    Return parameters for weather.get_active_alerts().
      boat  → {'zone': ..., 'county': ...}  (NWS zones)
      plane → {'station': ...}              (ICAO station for METAR)
    """
    if vehicle_type == "boat":
        return {
            "zone":   settings.get("weather_zone", "TXZ206"),
            "county": settings.get("nws_county", "TXC091"),
        }
    else:
        return {
            "station": settings.get("aviation_station", "KSAT"),
        }
