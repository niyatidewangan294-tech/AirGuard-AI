"""
agents/health_advisory_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1 + 2 – Health Advisory Agent

Responsibility:
  • Build a structured prompt from the AQI context produced by aqi_data_agent.
  • Send it to IBM watsonx.ai (via ibm_watsonx_service) or Langflow.
  • Parse the AI response into a structured list of recommendations.
  • Fall back to a rule-based engine if AI is unavailable.

The rule-based fallback is intentionally comprehensive so the dashboard
is fully functional even without IBM credentials.
"""

from __future__ import annotations
from services import ibm_watsonx_service, langflow_service


# ── Prompt template ───────────────────────────────────────────────────────────
PROMPT_TEMPLATE = """\
You are AirGuard, a friendly and expert air quality health advisor.

Current air quality data:
{plain_summary}

Based on this data, provide exactly 5 personalized health recommendations.
Format your response as a numbered list (1. ... 2. ... etc.).
Each recommendation should be one or two sentences, practical, and actionable.
Focus on: protecting health, masks, indoor air quality, exercise, and diet.
Keep the language simple and friendly for a general audience.

Recommendations:
"""


def _rule_based_recommendations(aqi_context: dict) -> list[str]:
    """
    Rule-based health recommendations — no AI required.
    Used as fallback when IBM credentials are not configured.
    """
    aqi = aqi_context["aqi"]
    level = aqi_context["category_level"].lower()
    dominant = aqi_context.get("dominant_pollutant")

    # Base recommendations by AQI level
    if aqi <= 50:
        recs = [
            "🌿 Air quality is excellent! Enjoy outdoor activities freely.",
            "🏃 Great day for jogging, cycling or any outdoor exercise.",
            "🪟 Open windows to ventilate your home with fresh air.",
            "💧 Stay well-hydrated throughout the day.",
            "🌳 Consider planting trees or indoor plants to support clean air.",
        ]
    elif aqi <= 100:
        recs = [
            "😊 Air quality is acceptable. Most people can go outdoors normally.",
            "🏃 Active individuals may notice mild effects during intense exercise — take short breaks.",
            "🤧 If you have allergies or asthma, keep your inhaler or antihistamines nearby.",
            "💧 Drink plenty of water to help your lungs stay moist and clear.",
            "🪟 Ventilate your home in the morning when pollution is usually lower.",
        ]
    elif aqi <= 150:
        recs = [
            "😷 Sensitive groups (children, elderly, asthma patients) should limit outdoor time.",
            "🏠 Keep windows closed during peak pollution hours (typically 6–10 AM and 4–8 PM).",
            "🌿 Use an indoor air purifier if available, especially in bedrooms.",
            "🏃 Reduce the intensity and duration of outdoor workouts today.",
            "💊 If you have a respiratory condition, follow your doctor's action plan.",
        ]
    elif aqi <= 200:
        recs = [
            "😷 Wear an N95 or KN95 mask if you need to go outside.",
            "🏠 Stay indoors as much as possible and keep windows and doors closed.",
            "🌬️ Run an air purifier with a HEPA filter indoors.",
            "🚫 Avoid outdoor exercise — do light yoga or stretching indoors instead.",
            "🥗 Eat antioxidant-rich foods (berries, spinach, nuts) to support your immune system.",
        ]
    elif aqi <= 300:
        recs = [
            "⚠️ Health alert! Minimize all outdoor activity — stay indoors.",
            "😷 If going outside is essential, wear an N95 mask and limit exposure to under 30 minutes.",
            "🏠 Seal gaps around doors and windows; use air purifiers on high setting.",
            "🚗 When travelling, keep car windows closed and use recirculated air mode.",
            "🩺 Anyone with heart or lung disease should contact their doctor if symptoms worsen.",
        ]
    else:
        recs = [
            "🚨 Hazardous air quality — stay indoors and keep all windows shut.",
            "😷 If you must go out, use an N95/N99 respirator and limit exposure to minutes.",
            "🏥 People with pre-existing conditions should call their doctor for guidance.",
            "🌬️ Run air purifiers continuously; replace filters frequently.",
            "📱 Follow local emergency health advisories and be ready to evacuate if instructed.",
        ]

    # Add a pollutant-specific tip if a dominant pollutant was identified
    if dominant:
        key = dominant["key"]
        tips = {
            "pm25": "🔬 PM2.5 levels are high — a high-quality N95 mask is most effective against fine particles.",
            "pm10": "🌪️ Coarse particle levels are elevated — rinse your nose and eyes after being outdoors.",
            "no2":  "🚗 NO₂ is high, often from traffic — avoid busy roads and rush-hour commutes.",
            "o3":   "☀️ Ozone is elevated in the afternoon — plan outdoor activities before noon.",
            "so2":  "🏭 SO₂ levels are high, often from industry — stay away from industrial areas.",
            "co":   "🔥 CO is elevated — check home gas appliances and ensure good ventilation.",
        }
        if key in tips:
            # Replace the last generic tip with this specific one
            recs[-1] = tips[key]

    return recs


def _parse_ai_response(text: str) -> list[str]:
    """
    Parse a numbered-list AI response into a clean Python list.
    Handles formats like "1. ...", "1) ...", "• ...", etc.
    """
    lines = text.strip().split("\n")
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip leading number + punctuation: "1.", "1)", "1 -"
        import re
        cleaned = re.sub(r"^[\d]+[.)]\s*", "", line)
        cleaned = re.sub(r"^[-•*]\s*", "", cleaned)
        if cleaned and len(cleaned) > 10:   # ignore very short fragments
            result.append(cleaned)

    # If parsing produced fewer than 3 items, return the raw text as one item
    if len(result) < 3:
        return [text.strip()]
    return result[:6]   # cap at 6 recommendations


# ── Main agent function ────────────────────────────────────────────────────────
def run(aqi_context: dict, user_profile: dict | None = None) -> dict:
    """
    Health Advisory Agent entry point.

    Input:  aqi_context  — output of aqi_data_agent.run()
            user_profile — optional dict: {"age_group": "adult", "conditions": [...]}

    Output: dict with keys:
              recommendations  : list of strings
              ai_generated     : bool (True if IBM AI was used)
              model_used       : str
    """
    # ── Try Langflow first (Phase 2+ when configured) ──
    langflow_result = langflow_service.run_flow({
        "plain_summary": aqi_context["plain_summary"],
        "city": aqi_context["city"],
        "aqi": aqi_context["aqi"],
        "category": aqi_context["category_level"],
    })
    if langflow_result and langflow_result.get("recommendations"):
        recs = langflow_result["recommendations"]
        if isinstance(recs, str):
            recs = _parse_ai_response(recs)
        return {
            "recommendations": recs,
            "ai_generated": True,
            "model_used": "IBM Langflow",
        }

    # ── Build prompt and call IBM watsonx.ai ──
    prompt = PROMPT_TEMPLATE.format(plain_summary=aqi_context["plain_summary"])

    # Add user-profile context if provided
    if user_profile:
        age = user_profile.get("age_group", "")
        conditions = ", ".join(user_profile.get("conditions", [])) or "none"
        prompt += f"\nUser profile — Age group: {age}. Medical conditions: {conditions}."

    ai_text = ibm_watsonx_service.generate_text(prompt, max_tokens=400)

    if ai_text:
        return {
            "recommendations": _parse_ai_response(ai_text),
            "ai_generated": True,
            "model_used": f"IBM watsonx.ai ({ibm_watsonx_service.IBM_MODEL_ID})",
        }

    # ── Rule-based fallback ──
    return {
        "recommendations": _rule_based_recommendations(aqi_context),
        "ai_generated": False,
        "model_used": "Rule-based engine (IBM credentials not configured)",
    }
