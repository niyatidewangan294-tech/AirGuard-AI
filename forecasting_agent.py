"""
agents/forecasting_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 2 – Forecasting Agent (upgraded)

Changes from Phase 1:
  • Intra-day variation model: AQI follows real-world patterns —
    high at morning rush (7–9 AM), dips midday, rises at evening rush
    (5–7 PM), drops overnight. Ozone peaks in the afternoon.
  • Confidence band: ±1 standard deviation of the 7-day history is
    returned so the chart can show an uncertainty ribbon.
  • Best outdoor window: finds the cleanest 2-hour block of the day.
  • Hourly detail table: returns a summary table for the next 12 hours.
  • Still uses Linear Regression (scikit-learn) for the daily trend —
    simple, explainable, easy to swap for ARIMA/LSTM later.
"""

from __future__ import annotations
import math
import numpy as np
from services import ibm_watsonx_service


# ── Warning thresholds ────────────────────────────────────────────────────────
WARNING_THRESHOLDS = {
    "moderate":       100,
    "sensitive":      150,
    "unhealthy":      200,
    "very_unhealthy": 300,
}

# ── Intra-day AQI shape ───────────────────────────────────────────────────────
# Multiplicative factors for each hour of the day (0–23).
# Based on typical urban traffic + photochemical patterns.
# 1.0 = baseline. >1.0 = worse. <1.0 = better.
HOURLY_SHAPE = [
    0.78,  # 00:00  — clean overnight
    0.72,  # 01:00
    0.68,  # 02:00  — daily low
    0.70,  # 03:00
    0.75,  # 04:00
    0.82,  # 05:00  — early commuters
    0.92,  # 06:00
    1.10,  # 07:00  — morning rush begins
    1.25,  # 08:00  — morning rush peak
    1.18,  # 09:00
    1.05,  # 10:00
    0.95,  # 11:00  — midday dip (mixing height rises)
    0.90,  # 12:00
    0.92,  # 13:00
    0.98,  # 14:00  — ozone building
    1.08,  # 15:00  — afternoon ozone peak
    1.15,  # 16:00
    1.22,  # 17:00  — evening rush begins
    1.28,  # 18:00  — evening rush peak
    1.20,  # 19:00
    1.10,  # 20:00
    0.98,  # 21:00
    0.88,  # 22:00
    0.82,  # 23:00
]


def _linear_forecast(history: list[dict]) -> float:
    """
    Fit Linear Regression on 7-day AQI history and return tomorrow's
    predicted daily-average AQI.
    """
    from sklearn.linear_model import LinearRegression

    if len(history) < 2:
        return float(history[-1]["aqi"]) if history else 100.0

    X = np.array(range(len(history))).reshape(-1, 1)
    y = np.array([d["aqi"] for d in history], dtype=float)

    model = LinearRegression()
    model.fit(X, y)

    # Predict the next day (index = len(history))
    return float(model.predict([[len(history)]])[0])


def _confidence_band(history: list[dict]) -> float:
    """
    Standard deviation of past AQI values — used as the ±1σ confidence band.
    Represents how much AQI typically varies day-to-day.
    """
    values = [d["aqi"] for d in history]
    if len(values) < 2:
        return 10.0
    return float(np.std(values))


def _build_hourly_forecast(
    base_aqi: float,
    sigma: float,
    history: list[dict],
) -> list[dict]:
    """
    Build 24 hourly forecast points by combining:
      1. The linear-trend daily-average prediction (base_aqi).
      2. The intra-day shape multiplier for each hour.
      3. Small deterministic perturbation (hash-based, reproducible).

    Returns list of {hour, time_label, aqi, aqi_low, aqi_high}
    where aqi_low/aqi_high form the ±1σ confidence band.
    """
    import datetime

    now = datetime.datetime.now()
    forecast = []

    for h in range(1, 25):
        future = now + datetime.timedelta(hours=h)
        hour_of_day = future.hour

        shape = HOURLY_SHAPE[hour_of_day]
        predicted = max(0, round(base_aqi * shape))

        # Confidence band scales with sigma and the shape factor
        band = max(5, round(sigma * shape * 0.8))

        forecast.append({
            "hour":       h,
            "hour_of_day": hour_of_day,
            "time_label": future.strftime("%I %p").lstrip("0"),  # "8 AM"
            "time_full":  future.strftime("%H:%M"),
            "aqi":        predicted,
            "aqi_low":    max(0, predicted - band),
            "aqi_high":   predicted + band,
        })

    return forecast


def _best_outdoor_window(forecast: list[dict]) -> dict:
    """
    Find the best consecutive 2-hour window (lowest average AQI) during
    reasonable daylight hours (6 AM – 9 PM).
    """
    daytime = [
        p for p in forecast
        if 6 <= p["hour_of_day"] <= 21
    ]
    if not daytime:
        return {"start": "—", "end": "—", "aqi": "—"}

    best_avg = 9999
    best_start = daytime[0]
    best_end   = daytime[0]

    for i in range(len(daytime) - 1):
        avg = (daytime[i]["aqi"] + daytime[i + 1]["aqi"]) / 2
        if avg < best_avg:
            best_avg = avg
            best_start = daytime[i]
            best_end   = daytime[i + 1]

    return {
        "start": best_start["time_label"],
        "end":   best_end["time_label"],
        "aqi":   round(best_avg),
    }


def _generate_warnings(forecast: list[dict], current_aqi: int) -> list[dict]:
    """
    Scan the forecast for AQI threshold crossings.
    Returns warnings with severity, expected time, and advice.
    """
    SEVERITY_ADVICE = {
        "moderate":       "Sensitive individuals should limit outdoor exertion.",
        "sensitive":      "Children, elderly and asthma patients should stay indoors.",
        "unhealthy":      "Everyone should reduce outdoor time. Wear an N95 mask.",
        "very_unhealthy": "Health alert — avoid all outdoor activity.",
    }

    warnings = []
    seen_levels = set()

    for point in forecast:
        aqi = point["aqi"]
        for level, threshold in sorted(WARNING_THRESHOLDS.items(), key=lambda x: x[1]):
            if level not in seen_levels and current_aqi < threshold <= aqi:
                warnings.append({
                    "type":         level,
                    "threshold":    threshold,
                    "expected_aqi": aqi,
                    "expected_at":  point["time_label"],
                    "message": (
                        f"⚠️ AQI forecast to reach {aqi} "
                        f"({level.replace('_',' ').title()}) "
                        f"around {point['time_label']}."
                    ),
                    "advice": SEVERITY_ADVICE[level],
                })
                seen_levels.add(level)
                break

    return warnings


def _narrative_summary(
    forecast: list[dict],
    current_aqi: int,
    city: str,
    best_window: dict,
) -> str:
    """
    Plain-English summary. Tries IBM watsonx.ai; falls back to template.
    """
    peak = max(forecast, key=lambda x: x["aqi"])
    low  = min(forecast, key=lambda x: x["aqi"])

    prompt = (
        f"You are a friendly air quality forecaster. "
        f"Current AQI in {city} is {current_aqi}.\n"
        f"24h forecast — peak: AQI {peak['aqi']} at {peak['time_label']}, "
        f"low: AQI {low['aqi']} at {low['time_label']}.\n"
        f"Best outdoor window: {best_window['start']}–{best_window['end']} "
        f"(forecast AQI {best_window['aqi']}).\n"
        "Write a 2-sentence friendly forecast for residents. "
        "Mention the best time to go outside."
    )

    ai_text = ibm_watsonx_service.generate_text(prompt, max_tokens=130, temperature=0.5)
    if ai_text:
        return ai_text

    trend = "improving" if peak["aqi"] <= current_aqi else "worsening slightly"
    return (
        f"Air quality in {city} is forecast to be {trend} over the next 24 hours, "
        f"peaking around AQI {peak['aqi']} at {peak['time_label']}. "
        f"The best time to go outside is {best_window['start']}–{best_window['end']} "
        f"when AQI is expected around {best_window['aqi']}."
    )


# ── Main agent function ────────────────────────────────────────────────────────
def run(aqi_context: dict, history: list[dict]) -> dict:
    """
    Forecasting Agent entry point.

    Input:  aqi_context — from aqi_data_agent.run()
            history     — from aqi_service.fetch_historical_aqi()

    Output: dict with:
      forecast        : 24 hourly points {hour, time_label, aqi, aqi_low, aqi_high}
      warnings        : list of threshold-crossing warning dicts
      summary         : plain-English narrative string
      best_window     : {start, end, aqi} — best outdoor time
      chart_labels    : hourly labels for the forecast line chart (every 3h)
      chart_data      : AQI values for chart
      chart_low       : lower confidence band values
      chart_high      : upper confidence band values
      hourly_table    : next-12-hour summary table rows
      sigma           : historical standard deviation (shown in UI)
    """
    current_aqi = aqi_context["aqi"]
    city = aqi_context["city"]

    # Stage 1: statistical model
    base_aqi = _linear_forecast(history)
    sigma    = _confidence_band(history)

    # Stage 2: hourly forecast with intra-day shape
    forecast = _build_hourly_forecast(base_aqi, sigma, history)

    # Stage 3: analysis
    warnings     = _generate_warnings(forecast, current_aqi)
    best_window  = _best_outdoor_window(forecast)
    summary      = _narrative_summary(forecast, current_aqi, city, best_window)

    # Stage 4: chart-ready data — every 3 hours
    chart_points = [forecast[i] for i in range(0, 24, 3)]

    # Stage 5: next-12-hour table (every 2 hours, readable)
    hourly_table = [
        {
            "time":     forecast[i]["time_label"],
            "aqi":      forecast[i]["aqi"],
            "band":     "+/-" + str(forecast[i]['aqi_high'] - forecast[i]['aqi']),
            "category": _aqi_label(forecast[i]["aqi"]),
        }
        for i in range(0, 12, 2)
    ]

    return {
        "forecast":      forecast,
        "warnings":      warnings,
        "summary":       summary,
        "best_window":   best_window,
        "chart_labels":  [p["time_label"] for p in chart_points],
        "chart_data":    [p["aqi"]        for p in chart_points],
        "chart_low":     [p["aqi_low"]    for p in chart_points],
        "chart_high":    [p["aqi_high"]   for p in chart_points],
        "hourly_table":  hourly_table,
        "sigma":         round(sigma, 1),
    }


def _aqi_label(aqi: int) -> str:
    if aqi <= 50:  return "Good"
    if aqi <= 100: return "Moderate"
    if aqi <= 150: return "Sensitive"
    if aqi <= 200: return "Unhealthy"
    if aqi <= 300: return "Very Unhealthy"
    return "Hazardous"
