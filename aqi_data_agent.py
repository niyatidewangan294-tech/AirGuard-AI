"""
agents/aqi_data_agent.py
━━━━━━━━━━━━━━━━━━━━━━━
Phase 1 – AQI Data Agent

Responsibility:
  • Receives raw AQI data from the AQI service.
  • Interprets and enriches it (adds human-readable summaries, risk flags,
    dominant pollutant, confidence score).
  • Builds a structured "context packet" that every downstream agent
    (health, forecasting, community) can consume.

Think of this agent as the "translator" that turns numbers into meaning.
"""

from __future__ import annotations


# ── Dominant-pollutant logic ───────────────────────────────────────────────────
# Each pollutant has a "threshold" above which it is considered elevated.
# The one furthest above its threshold is flagged as dominant.
POLLUTANT_THRESHOLDS = {
    "pm25": 35.0,   # µg/m³  — US-EPA 24-hr standard
    "pm10": 50.0,   # µg/m³
    "no2":  40.0,   # µg/m³  — WHO annual mean
    "o3":   60.0,   # µg/m³
    "so2":  20.0,   # µg/m³  — WHO 24-hr mean
    "co":   4.0,    # mg/m³
}

POLLUTANT_NAMES = {
    "pm25": "PM2.5 (fine particles)",
    "pm10": "PM10 (coarse particles)",
    "no2":  "Nitrogen Dioxide (NO₂)",
    "o3":   "Ozone (O₃)",
    "so2":  "Sulfur Dioxide (SO₂)",
    "co":   "Carbon Monoxide (CO)",
}

# Short health facts shown per pollutant on the dashboard
POLLUTANT_HEALTH_NOTES = {
    "pm25": "Fine particles penetrate deep into the lungs and bloodstream.",
    "pm10": "Coarse particles irritate the nose, throat and lungs.",
    "no2":  "Inflames the airways; worsens asthma and respiratory disease.",
    "o3":   "Triggers chest pain, coughing, and throat irritation.",
    "so2":  "Can cause breathing problems and aggravate asthma.",
    "co":   "Reduces oxygen delivery to organs; dangerous in enclosed spaces.",
}


def _find_dominant_pollutant(aqi_data: dict) -> dict | None:
    """Return the pollutant that most exceeds its threshold, or None if all OK."""
    worst_key = None
    worst_ratio = 0.0

    for key, threshold in POLLUTANT_THRESHOLDS.items():
        value = float(aqi_data.get(key, 0) or 0)
        if threshold > 0:
            ratio = value / threshold
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst_key = key

    if worst_key and worst_ratio > 1.0:
        return {
            "key": worst_key,
            "name": POLLUTANT_NAMES[worst_key],
            "value": aqi_data.get(worst_key),
            "threshold": POLLUTANT_THRESHOLDS[worst_key],
            "ratio": round(worst_ratio, 2),
            "health_note": POLLUTANT_HEALTH_NOTES[worst_key],
        }
    return None


def _assess_vulnerable_groups(category_level: str) -> list[str]:
    """Return a list of groups who face heightened risk at this AQI level."""
    level = category_level.lower()

    always_at_risk = ["Children under 14", "Adults over 65"]

    if "good" in level:
        return []
    if "moderate" in level:
        return always_at_risk + ["People with asthma or allergies"]
    if "sensitive" in level:
        return always_at_risk + ["Asthma / COPD patients", "Pregnant women", "People exercising outdoors"]
    # Unhealthy and above — everyone
    return always_at_risk + [
        "Asthma / COPD patients",
        "Pregnant women",
        "Heart disease patients",
        "Everyone exercising outdoors",
    ]


def _outdoor_activity_advice(category_level: str) -> str:
    """Single-sentence outdoor activity guidance."""
    level = category_level.lower()
    if "good" in level:
        return "Great day for outdoor activities!"
    if "moderate" in level:
        return "Outdoor activities are fine. Sensitive individuals may want to limit extended exertion."
    if "sensitive" in level:
        return "Sensitive groups should reduce prolonged outdoor exertion."
    if "unhealthy" in level and "very" not in level:
        return "Everyone should limit prolonged outdoor exertion. Take breaks indoors."
    if "very" in level:
        return "Avoid prolonged outdoor activities. Wear a mask (N95) if going outside."
    return "Stay indoors. Outdoor activities are hazardous today."


# ── Main agent function ────────────────────────────────────────────────────────
def run(aqi_data: dict) -> dict:
    """
    AQI Data Agent entry point.

    Input:  raw AQI dict from aqi_service.fetch_aqi()
    Output: enriched context packet consumed by all downstream agents.

    The returned dict is called the "AQI context" throughout the codebase.
    """
    aqi = int(aqi_data.get("aqi", 0))
    category = aqi_data.get("category", {})
    category_level = category.get("level", "Unknown")

    dominant = _find_dominant_pollutant(aqi_data)
    vulnerable = _assess_vulnerable_groups(category_level)
    activity_advice = _outdoor_activity_advice(category_level)

    # Build a plain-English summary that we later include in AI prompts
    summary_lines = [
        f"City: {aqi_data.get('city', 'Unknown')}",
        f"AQI: {aqi} — {category_level}",
        f"PM2.5: {aqi_data.get('pm25', 0)} µg/m³ | PM10: {aqi_data.get('pm10', 0)} µg/m³",
    ]
    if dominant:
        summary_lines.append(
            f"Dominant pollutant: {dominant['name']} "
            f"({dominant['value']} — {dominant['ratio']}× its safe threshold)"
        )
    if vulnerable:
        summary_lines.append(f"Groups at risk: {', '.join(vulnerable)}")
    summary_lines.append(f"Outdoor advice: {activity_advice}")

    return {
        # Pass through original data unchanged so agents can access raw values
        "raw": aqi_data,

        # Enriched fields
        "aqi": aqi,
        "city": aqi_data.get("city", "Unknown"),
        "category": category,
        "category_level": category_level,
        "pm25": aqi_data.get("pm25", 0),
        "pm10": aqi_data.get("pm10", 0),
        "no2": aqi_data.get("no2", 0),
        "o3": aqi_data.get("o3", 0),
        "co": aqi_data.get("co", 0),
        "so2": aqi_data.get("so2", 0),
        "dominant_pollutant": dominant,
        "vulnerable_groups": vulnerable,
        "outdoor_activity_advice": activity_advice,
        "plain_summary": "\n".join(summary_lines),
        "data_source": aqi_data.get("source", "unknown"),
    }
