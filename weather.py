"""
NWS weather alert checker for Canyon Lake, TX.

Canyon Lake is in Comal County — NWS forecast zone TXZ206.
Uses the NWS API (no API key required).
"""

import urllib.request
import urllib.error
import json
import logging

log = logging.getLogger(__name__)

NWS_ZONE    = "TXZ206"   # Comal County / Canyon Lake forecast zone
NWS_COUNTY  = "TXC091"   # Comal County FIPS zone (catches county-level alerts)
ALERTS_URL  = "https://api.weather.gov/alerts/active?zone={zone}"

# Alert event types that warrant notifying members
ALERT_EVENTS = {
    # Severe / life safety
    "Tornado Warning",
    "Tornado Watch",
    "Severe Thunderstorm Warning",
    "Severe Thunderstorm Watch",
    "Flash Flood Warning",
    "Flash Flood Watch",
    "Flood Warning",
    "Flood Watch",
    # Wind / boating hazards
    "Wind Advisory",
    "High Wind Warning",
    "High Wind Watch",
    "Small Craft Advisory",
    "Small Craft Advisory for Hazardous Seas",
    # Extreme heat (safety on water)
    "Excessive Heat Warning",
    "Excessive Heat Watch",
    "Heat Advisory",
    # Fog / visibility
    "Dense Fog Advisory",
}


def get_active_alerts() -> list[dict]:
    """Return active NWS alerts for Canyon Lake zone. Returns [] on error."""
    alerts = []
    for zone in (NWS_ZONE, NWS_COUNTY):
        url = ALERTS_URL.format(zone=zone)
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BentleyBoatClub/1.0 admin@bentleyboatclub.com"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                event = props.get("event", "")
                if event in ALERT_EVENTS:
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
            log.error("NWS API error for zone %s: %s", zone, exc)

    # Deduplicate by event name
    seen = set()
    unique = []
    for a in alerts:
        if a["event"] not in seen:
            seen.add(a["event"])
            unique.append(a)
    return unique


def format_alert_summary(alerts: list[dict]) -> str:
    """Return a plain-text summary of active alerts."""
    if not alerts:
        return "No active weather alerts for Canyon Lake."
    lines = []
    for a in alerts:
        lines.append(f"⚠ {a['event']} ({a['severity']})")
        lines.append(f"  {a['headline']}")
        if a["instruction"]:
            lines.append(f"  {a['instruction'].splitlines()[0]}")
        lines.append("")
    return "\n".join(lines).strip()
