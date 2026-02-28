"""
Weather alert checker for ClubReserve.

Supports two modes based on vehicle type:
  boat  → NWS zone/county alerts (existing logic, parameterized)
  plane → FAA METAR-based IFR/LIFR detection via aviationweather.gov API

Public API:
  get_active_alerts(vehicle_type, settings) → list[dict]
  format_alert_summary(alerts, vehicle_type) → str
"""

import urllib.request
import urllib.error
import json
import logging

log = logging.getLogger(__name__)

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone={zone}"
METAR_URL = "https://aviationweather.gov/api/data/metar?ids={station}&format=json"

USER_AGENT = "ClubReserve/1.0 admin@clubreserve.com"


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def get_active_alerts(vehicle_type: str = "boat", settings: dict = None) -> list[dict]:
    """
    Return a list of active alerts for this club's vehicle type.
    settings should be the dict from models.get_all_club_settings().
    """
    settings = settings or {}
    if vehicle_type == "plane":
        station = settings.get("aviation_station", "KSAT")
        return _get_aviation_alerts(station)
    else:
        zone   = settings.get("weather_zone", "TXZ206")
        county = settings.get("nws_county", "TXC091")
        return _get_nws_marine_alerts(zone, county)


def format_alert_summary(alerts: list[dict], vehicle_type: str = "boat") -> str:
    """Return a plain-text summary of active alerts."""
    if not alerts:
        if vehicle_type == "plane":
            return "No active aviation alerts. VFR conditions expected."
        return "No active weather alerts for your area."
    lines = []
    for a in alerts:
        lines.append(f"⚠ {a['event']} ({a['severity']})")
        lines.append(f"  {a['headline']}")
        if a.get("instruction"):
            lines.append(f"  {a['instruction'].splitlines()[0]}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# NWS marine / boat alerts
# ---------------------------------------------------------------------------

# Alert event types relevant to boating
_BOAT_ALERT_EVENTS = {
    "Tornado Warning", "Tornado Watch",
    "Severe Thunderstorm Warning", "Severe Thunderstorm Watch",
    "Flash Flood Warning", "Flash Flood Watch",
    "Flood Warning", "Flood Watch",
    "Wind Advisory", "High Wind Warning", "High Wind Watch",
    "Small Craft Advisory", "Small Craft Advisory for Hazardous Seas",
    "Excessive Heat Warning", "Excessive Heat Watch", "Heat Advisory",
    "Dense Fog Advisory",
}


def _get_nws_marine_alerts(zone: str, county: str) -> list[dict]:
    """Return active NWS alerts for the given zone and county. Returns [] on error."""
    alerts = []
    for nws_zone in (zone, county):
        url = NWS_ALERTS_URL.format(zone=nws_zone)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                event = props.get("event", "")
                if event in _BOAT_ALERT_EVENTS:
                    alerts.append({
                        "event":       event,
                        "headline":    props.get("headline", event),
                        "description": props.get("description", ""),
                        "severity":    props.get("severity", "Unknown"),
                        "certainty":   props.get("certainty", "Unknown"),
                        "onset":       props.get("onset", ""),
                        "expires":     props.get("expires", ""),
                        "instruction": props.get("instruction") or "",
                    })
        except Exception as exc:
            log.error("NWS API error for zone %s: %s", nws_zone, exc)

    # Deduplicate by event name
    seen = set()
    unique = []
    for a in alerts:
        if a["event"] not in seen:
            seen.add(a["event"])
            unique.append(a)
    return unique


# ---------------------------------------------------------------------------
# Aviation / plane alerts
# ---------------------------------------------------------------------------

def _get_aviation_alerts(station: str) -> list[dict]:
    """
    Check METAR at station and return IFR/LIFR conditions as alert-shaped dicts.
    Also checks NWS for severe weather at the station.
    Returns [] on API error.
    """
    alerts = []
    url = METAR_URL.format(station=station.upper())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        if not data:
            return []

        metar = data[0] if isinstance(data, list) else data
        flight_category = metar.get("flightCategory", "").upper()
        raw_metar = metar.get("rawOb", "")
        wind_speed = metar.get("wspd", 0) or 0
        wind_gust  = metar.get("wgst", 0) or 0
        visibility = metar.get("visib", 99) or 99
        ceil_ft    = metar.get("cldBas1", 9999) or 9999

        if flight_category in ("IFR", "LIFR"):
            severity = "Extreme" if flight_category == "LIFR" else "Severe"
            alerts.append({
                "event":       f"{flight_category} Conditions",
                "headline":    f"{flight_category} at {station.upper()} — ceiling {ceil_ft} ft, visibility {visibility} SM",
                "description": f"Raw METAR: {raw_metar}",
                "severity":    severity,
                "certainty":   "Observed",
                "onset":       "",
                "expires":     "",
                "instruction": "Flight operations may be restricted. Check NOTAMs and consult CFI.",
            })

        if wind_speed >= 25 or wind_gust >= 35:
            alerts.append({
                "event":       "High Wind Advisory (Aviation)",
                "headline":    f"Winds {wind_speed} kt gusting {wind_gust} kt at {station.upper()}",
                "description": f"Raw METAR: {raw_metar}",
                "severity":    "Moderate",
                "certainty":   "Observed",
                "onset":       "",
                "expires":     "",
                "instruction": "Evaluate crosswind component for your aircraft.",
            })

    except Exception as exc:
        log.error("METAR API error for station %s: %s", station, exc)

    return alerts
