"""
services/aqi_service.py
━━━━━━━━━━━━━━━━━━━━━━
Fetches live AQI data from the AQICN World Air Quality Index API.
Falls back to realistic sample data when the API key is missing or the
request fails — so the dashboard always has something to show.

API docs: https://aqicn.org/api/
"""

import os
import time
import random
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
AQICN_API_KEY = os.getenv("AQICN_API_KEY", "")
AQICN_BASE_URL = "https://api.waqi.info"

# Simple in-memory cache so we don't hammer the API on every dashboard refresh
_cache: dict = {}
CACHE_TTL = int(os.getenv("AQI_CACHE_TTL", "300"))  # seconds


# ── AQI category helpers ───────────────────────────────────────────────────────
def get_aqi_category(aqi: int) -> dict:
    """
    Map a numeric AQI value to its WHO / US-EPA category, colour, and
    a short description of the health risk.

    Returns a dict with: level, color, emoji, description
    """
    if aqi <= 50:
        return {
            "level": "Good",
            "color": "#00e400",
            "text_color": "#005a00",
            "emoji": "😊",
            "description": "Air quality is satisfactory. No health risk.",
        }
    elif aqi <= 100:
        return {
            "level": "Moderate",
            "color": "#ffff00",
            "text_color": "#7a7a00",
            "emoji": "😐",
            "description": "Acceptable air quality. Sensitive individuals may notice minor effects.",
        }
    elif aqi <= 150:
        return {
            "level": "Unhealthy for Sensitive Groups",
            "color": "#ff7e00",
            "text_color": "#7a3c00",
            "emoji": "😷",
            "description": "Sensitive groups (children, elderly, asthma) may experience health effects.",
        }
    elif aqi <= 200:
        return {
            "level": "Unhealthy",
            "color": "#ff0000",
            "text_color": "#7a0000",
            "emoji": "🤢",
            "description": "Everyone may begin to experience health effects.",
        }
    elif aqi <= 300:
        return {
            "level": "Very Unhealthy",
            "color": "#8f3f97",
            "text_color": "#4a1a50",
            "emoji": "🤮",
            "description": "Health alert: serious health effects for everyone.",
        }
    else:
        return {
            "level": "Hazardous",
            "color": "#7e0023",
            "text_color": "#3a0010",
            "emoji": "☠️",
            "description": "Emergency health warning. Entire population is at risk.",
        }


# ── Sample / fallback data ────────────────────────────────────────────────────
SAMPLE_CITIES = {
    "Delhi": {"aqi": 178, "pm25": 89.4, "pm10": 142.1, "no2": 48.2, "o3": 22.1, "co": 1.2, "so2": 12.5},
    "Mumbai": {"aqi": 112, "pm25": 42.7, "pm10": 78.3, "no2": 31.1, "o3": 18.4, "co": 0.8, "so2": 7.2},
    "London": {"aqi": 48, "pm25": 11.2, "pm10": 19.8, "no2": 22.0, "o3": 35.6, "co": 0.4, "so2": 2.1},
    "Beijing": {"aqi": 156, "pm25": 72.3, "pm10": 118.5, "no2": 55.4, "o3": 15.2, "co": 1.6, "so2": 18.9},
    "New York": {"aqi": 62, "pm25": 18.5, "pm10": 28.4, "no2": 29.3, "o3": 42.1, "co": 0.5, "so2": 3.4},
    "Tokyo": {"aqi": 55, "pm25": 15.1, "pm10": 24.2, "no2": 20.8, "o3": 38.7, "co": 0.3, "so2": 2.8},
    "Los Angeles": {"aqi": 95, "pm25": 28.6, "pm10": 44.1, "no2": 38.2, "o3": 67.4, "co": 0.7, "so2": 4.1},
    "Shanghai": {"aqi": 134, "pm25": 58.2, "pm10": 95.7, "no2": 47.8, "o3": 20.3, "co": 1.3, "so2": 15.6},
}


def _build_sample_response(city: str) -> dict:
    """Generate a realistic sample AQI response for demo / offline mode."""
    # Use a known city if available, else generate plausible random values
    if city in SAMPLE_CITIES:
        d = SAMPLE_CITIES[city]
    else:
        aqi = random.randint(40, 160)
        d = {
            "aqi": aqi,
            "pm25": round(aqi * 0.45 + random.uniform(-5, 5), 1),
            "pm10": round(aqi * 0.75 + random.uniform(-10, 10), 1),
            "no2": round(random.uniform(10, 60), 1),
            "o3": round(random.uniform(10, 70), 1),
            "co": round(random.uniform(0.2, 2.0), 1),
            "so2": round(random.uniform(1, 20), 1),
        }

    category = get_aqi_category(d["aqi"])
    return {
        "city": city,
        "aqi": d["aqi"],
        "pm25": d["pm25"],
        "pm10": d["pm10"],
        "no2": d["no2"],
        "o3": d["o3"],
        "co": d["co"],
        "so2": d["so2"],
        "category": category,
        "source": "sample",          # flag so the UI can show a disclaimer
        "timestamp": time.time(),
    }


# ── Live API fetch ────────────────────────────────────────────────────────────
def fetch_aqi(city: str) -> dict:
    """
    Main entry point. Returns a normalised AQI dict for the given city.

    Steps:
    1. Check in-memory cache (avoids repeated API calls within CACHE_TTL).
    2. Try the AQICN live API if a key is configured.
    3. Fall back to sample data if the API is unavailable or key is missing.
    """
    city_key = city.strip().lower()

    # ── Step 1: cache check ──
    cached = _cache.get(city_key)
    if cached and (time.time() - cached["timestamp"]) < CACHE_TTL:
        return cached

    # ── Step 2: live API ──
    if AQICN_API_KEY:
        try:
            result = _fetch_from_aqicn(city)
            _cache[city_key] = result   # store in cache
            return result
        except Exception as exc:
            print(f"[AQIService] Live fetch failed for '{city}': {exc} — using sample data")

    # ── Step 3: fallback ──
    result = _build_sample_response(city.title())
    _cache[city_key] = result
    return result


def _fetch_from_aqicn(city: str) -> dict:
    """
    Call the AQICN /feed/ endpoint and normalise the response into our
    standard format.

    Raises an exception if the API returns an error or the request times out.
    """
    url = f"{AQICN_BASE_URL}/feed/{city}/?token={AQICN_API_KEY}"
    resp = requests.get(url, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "ok":
        raise ValueError(f"AQICN API error: {data.get('data', 'unknown error')}")

    raw = data["data"]

    # Helper: safely extract a pollutant value buried in iaqi sub-dict
    def _pollutant(key: str) -> float:
        try:
            return float(raw["iaqi"][key]["v"])
        except (KeyError, TypeError, ValueError):
            return 0.0

    aqi_value = int(raw.get("aqi", 0))
    category = get_aqi_category(aqi_value)

    return {
        "city": raw.get("city", {}).get("name", city),
        "aqi": aqi_value,
        "pm25": _pollutant("pm25"),
        "pm10": _pollutant("pm10"),
        "no2": _pollutant("no2"),
        "o3": _pollutant("o3"),
        "co": _pollutant("co"),
        "so2": _pollutant("so2"),
        "category": category,
        "source": "live",
        "timestamp": time.time(),
    }


# ── Historical / simulated trend data (Phase 2) ───────────────────────────────
def fetch_historical_aqi(city: str, days: int = 7) -> list:
    """
    Return a list of daily AQI readings for the past `days` days.

    In Phase 2 this is simulated. You can replace it with a real historical
    API (e.g. OpenAQ, AQICN historical endpoint) without changing the agents.

    Returns: list of dicts with keys: date (ISO string), aqi, pm25, pm10
    """
    import datetime

    base = _build_sample_response(city)
    base_aqi = base["aqi"]
    history = []

    for i in range(days, 0, -1):
        day = datetime.date.today() - datetime.timedelta(days=i)
        # Add realistic-looking variation around the base value
        variation = random.uniform(-20, 20)
        daily_aqi = max(5, int(base_aqi + variation))
        history.append({
            "date": day.isoformat(),
            "aqi": daily_aqi,
            "pm25": round(daily_aqi * 0.45 + random.uniform(-3, 3), 1),
            "pm10": round(daily_aqi * 0.75 + random.uniform(-5, 5), 1),
        })

    return history
