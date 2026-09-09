"""
agents/community_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━
Phase 2 – Community Action Agent

Responsibility:
  • Suggest concrete pollution-reduction actions that residents and communities
    can take based on AQI levels and dominant pollutants.
  • Optionally generate a customised AI action plan via IBM watsonx.ai.

Actions are organized into categories so the frontend can display them
in grouped cards.
"""

from __future__ import annotations
from services import ibm_watsonx_service


# ── Static action libraries ───────────────────────────────────────────────────
# Actions are tagged by the minimum AQI level they apply to.
# "always" actions are shown regardless of AQI.
COMMUNITY_ACTIONS = [
    # ── Mobility ──────────────────────────────────────────────────────────────
    {
        "category": "🚲 Sustainable Mobility",
        "min_aqi": 0,
        "action": "Use public transport, cycle, or walk instead of driving private cars.",
        "impact": "Reduces road-transport NOx and PM2.5 by up to 40% per trip.",
    },
    {
        "category": "🚲 Sustainable Mobility",
        "min_aqi": 100,
        "action": "Avoid unnecessary car trips on high-pollution days — consider carpooling or remote work.",
        "impact": "Cuts rush-hour traffic emissions significantly.",
    },
    {
        "category": "🚲 Sustainable Mobility",
        "min_aqi": 0,
        "action": "Switch to an electric vehicle (EV) or hybrid for your next car purchase.",
        "impact": "Zero tailpipe emissions; reduces urban PM2.5 and NOx long-term.",
    },

    # ── Home & Workplace ───────────────────────────────────────────────────────
    {
        "category": "🏠 Home & Workplace",
        "min_aqi": 0,
        "action": "Switch to energy-efficient LED lighting and appliances to reduce power-plant emissions.",
        "impact": "Reduces electricity demand and associated coal/gas plant pollution.",
    },
    {
        "category": "🏠 Home & Workplace",
        "min_aqi": 100,
        "action": "Avoid burning wood, waste, or biomass indoors or outdoors.",
        "impact": "Burning is a major PM2.5 source in residential areas.",
    },
    {
        "category": "🏠 Home & Workplace",
        "min_aqi": 150,
        "action": "Place indoor air-purifying plants (snake plant, peace lily) around your home.",
        "impact": "Can reduce indoor VOC levels by 10–20%.",
    },

    # ── Green Spaces ───────────────────────────────────────────────────────────
    {
        "category": "🌳 Green Spaces",
        "min_aqi": 0,
        "action": "Plant trees or join a community tree-planting drive in your neighbourhood.",
        "impact": "A single mature tree absorbs ~22 kg of CO₂ per year and filters particulates.",
    },
    {
        "category": "🌳 Green Spaces",
        "min_aqi": 0,
        "action": "Advocate for more parks and green corridors in your city's development plan.",
        "impact": "Green buffers reduce street-level pollution by 15–50%.",
    },

    # ── Industry & Policy ─────────────────────────────────────────────────────
    {
        "category": "📢 Advocacy & Policy",
        "min_aqi": 100,
        "action": "Report illegal burning or industrial smoke to your local environmental authority.",
        "impact": "Direct enforcement action reduces point-source pollution.",
    },
    {
        "category": "📢 Advocacy & Policy",
        "min_aqi": 0,
        "action": "Support clean-energy policies and renewable energy adoption in your community.",
        "impact": "Transitioning to renewables is the single largest long-term AQI improver.",
    },
    {
        "category": "📢 Advocacy & Policy",
        "min_aqi": 150,
        "action": "Encourage your school or workplace to implement a vehicle-free zone or air-quality policy.",
        "impact": "Reduces local hotspot pollution by up to 30%.",
    },

    # ── Personal Health Actions ────────────────────────────────────────────────
    {
        "category": "💪 Personal Health",
        "min_aqi": 100,
        "action": "Share AQI data with family, friends and neighbours — awareness is the first step.",
        "impact": "Community awareness leads to collective behaviour change.",
    },
    {
        "category": "💪 Personal Health",
        "min_aqi": 150,
        "action": "Donate or lend spare air purifiers to vulnerable households (elderly, children).",
        "impact": "High-risk populations benefit most from clean indoor air.",
    },
]


def _filter_actions(aqi: int) -> list[dict]:
    """Return only actions relevant to the current AQI level."""
    relevant = [a for a in COMMUNITY_ACTIONS if a["min_aqi"] <= aqi]

    # Group by category for cleaner frontend display
    categories: dict[str, list] = {}
    for action in relevant:
        cat = action["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "action": action["action"],
            "impact": action["impact"],
        })

    return [{"category": cat, "actions": acts} for cat, acts in categories.items()]


def _ai_action_plan(aqi_context: dict) -> str | None:
    """
    Ask IBM watsonx.ai for a custom community action message for this city/AQI.
    Returns None if AI is unavailable.
    """
    prompt = (
        f"You are a community environmental advisor. "
        f"AQI in {aqi_context['city']} is {aqi_context['aqi']} "
        f"({aqi_context['category_level']}).\n"
        "Write one paragraph (3-4 sentences) of motivating community-action advice "
        "for residents. Be specific, positive, and actionable."
    )
    return ibm_watsonx_service.generate_text(prompt, max_tokens=150, temperature=0.6)


# ── Main agent function ────────────────────────────────────────────────────────
def run(aqi_context: dict) -> dict:
    """
    Community Action Agent entry point.

    Input:  aqi_context — from aqi_data_agent.run()

    Output: dict with:
              grouped_actions : list of {category, actions[]}
              ai_message      : AI-generated motivational paragraph (or None)
              action_count    : total number of actions returned
    """
    aqi = aqi_context["aqi"]
    grouped = _filter_actions(aqi)
    ai_message = _ai_action_plan(aqi_context)

    return {
        "grouped_actions": grouped,
        "ai_message": ai_message,
        "action_count": sum(len(g["actions"]) for g in grouped),
    }
