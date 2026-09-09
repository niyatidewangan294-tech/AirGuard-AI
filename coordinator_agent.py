"""
agents/coordinator_agent.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 3 – AI Coordinator Agent (upgraded)

Orchestrates all specialist agents in sequence, records a per-step trace
(timing, status, output snippet) and assembles the Final Daily Action Plan.

Pipeline:
  ① AQI Data Agent          — interprets raw numbers → AQI context
  ② Health Advisory Agent   — IBM watsonx.ai personalised recs
  ③ Forecasting Agent       — 24-hour prediction + warnings
  ④ Community Action Agent  — pollution-reduction actions
  ⑤ Coordinator             — merges all → Final Daily Action Plan

Phase 3 additions:
  • agent_trace   : list of {agent, status, duration_ms, output_snippet}
  • pipeline_status: "ok" | "partial" | "error"
  • final_plan    : structured dict (not just a string) with sections
  • Langflow multi-agent graph support via run_flow()
  • User profile personalisation passed through the whole chain
"""

from __future__ import annotations
import time
import traceback

from agents import aqi_data_agent, health_advisory_agent, forecasting_agent, community_agent
from services import aqi_service, ibm_watsonx_service, langflow_service


# ─────────────────────────────────────────────────────────────────────────────
# Agent-trace helpers
# ─────────────────────────────────────────────────────────────────────────────

def _trace_step(name: str, emoji: str, description: str) -> dict:
    """Create a new trace entry for one agent step."""
    return {
        "agent":       name,
        "emoji":       emoji,
        "description": description,
        "status":      "running",   # running | ok | error
        "duration_ms": 0,
        "output_snippet": "",
    }


def _finish_step(step: dict, t0: float, snippet: str) -> None:
    """Mark a step complete, record its elapsed time and output snippet."""
    step["status"]         = "ok"
    step["duration_ms"]    = round((time.time() - t0) * 1000)
    step["output_snippet"] = snippet[:120]   # truncate to keep JSON small


def _error_step(step: dict, t0: float, exc: Exception) -> None:
    """Mark a step as errored."""
    step["status"]         = "error"
    step["duration_ms"]    = round((time.time() - t0) * 1000)
    step["output_snippet"] = str(exc)[:120]


# ─────────────────────────────────────────────────────────────────────────────
# Final Daily Plan composer
# ─────────────────────────────────────────────────────────────────────────────

def _compose_final_plan(
    aqi_ctx: dict,
    health: dict,
    forecast: dict,
    community: dict,
) -> dict:
    """
    Compose a structured Final Daily Action Plan from all agent outputs.

    Returns a dict with clearly labelled sections — beginner-friendly to read.

    ① Tries IBM Langflow multi-agent endpoint first.
    ② Falls back to IBM watsonx.ai with a rich prompt.
    ③ Falls back to a well-structured template.
    """

    # ── ① Langflow ──
    lf_payload = {
        "city":             aqi_ctx["city"],
        "aqi":              aqi_ctx["aqi"],
        "category":         aqi_ctx["category_level"],
        "recommendations":  health["recommendations"][:3],
        "forecast_summary": forecast["summary"],
        "best_window":      f"{forecast['best_window']['start']} – {forecast['best_window']['end']}",
        "community_tip":    (
            community["grouped_actions"][0]["actions"][0]["action"]
            if community["grouped_actions"] else ""
        ),
        "warnings_count":   len(forecast["warnings"]),
    }
    lf = langflow_service.run_flow(lf_payload)
    if lf and lf.get("final_plan"):
        fp = lf["final_plan"]
        if isinstance(fp, str):
            # Langflow returned a plain string — wrap it
            return {
                "headline":       fp[:160],
                "morning_action": health["recommendations"][0] if health["recommendations"] else "",
                "best_outdoor":   f"{forecast['best_window']['start']} – {forecast['best_window']['end']} (AQI {forecast['best_window']['aqi']})",
                "ai_tip":         health["recommendations"][1] if len(health["recommendations"]) > 1 else "",
                "community_act":  (community["grouped_actions"][0]["actions"][0]["action"] if community["grouped_actions"] else ""),
                "evening_action": health["recommendations"][2] if len(health["recommendations"]) > 2 else "",
                "source":         "langflow",
            }
        return fp

    # ── ② watsonx.ai ──
    top_recs = "\n".join(f"- {r}" for r in health["recommendations"][:3])
    bw = forecast["best_window"]
    warn_text = (
        f"{len(forecast['warnings'])} forecast warning(s): "
        + "; ".join(w['message'] for w in forecast['warnings'][:2])
        if forecast["warnings"] else "No forecast warnings."
    )

    prompt = (
        f"You are AirGuard AI — a friendly, expert air quality advisor.\n\n"
        f"Today's data for {aqi_ctx['city']}:\n"
        f"- AQI: {aqi_ctx['aqi']} ({aqi_ctx['category_level']})\n"
        f"- PM2.5: {aqi_ctx['pm25']} µg/m³  |  PM10: {aqi_ctx['pm10']} µg/m³\n"
        f"- {warn_text}\n"
        f"- Best outdoor window: {bw['start']} – {bw['end']} (forecast AQI {bw['aqi']})\n"
        f"- Top health tips:\n{top_recs}\n\n"
        "Write a Daily Action Plan with exactly these 4 labelled sections:\n"
        "MORNING: (one sentence — what to do when you wake up)\n"
        "OUTDOOR: (one sentence — best time and how to go out safely)\n"
        "HEALTH: (one sentence — key health protection tip)\n"
        "EVENING: (one sentence — evening and indoor actions)\n"
        "Keep each section to one sentence. Be warm, positive, specific."
    )

    ai_text = ibm_watsonx_service.generate_text(prompt, max_tokens=280, temperature=0.55)

    if ai_text:
        # Parse the 4 labelled sections
        sections = {"morning": "", "outdoor": "", "health": "", "evening": ""}
        for line in ai_text.strip().splitlines():
            l = line.strip()
            for key in sections:
                if l.upper().startswith(key.upper() + ":"):
                    sections[key] = l.split(":", 1)[1].strip()
        return {
            "headline":       f"Your daily air quality plan for {aqi_ctx['city']} — AQI {aqi_ctx['aqi']} ({aqi_ctx['category_level']})",
            "morning_action": sections["morning"] or health["recommendations"][0],
            "best_outdoor":   f"{bw['start']} – {bw['end']} (AQI {bw['aqi']})",
            "ai_tip":         sections["health"] or (health["recommendations"][1] if len(health["recommendations"]) > 1 else ""),
            "community_act":  (community["grouped_actions"][0]["actions"][0]["action"] if community["grouped_actions"] else ""),
            "evening_action": sections["evening"] or (health["recommendations"][2] if len(health["recommendations"]) > 2 else ""),
            "source":         "watsonx",
        }

    # ── ③ Template fallback ──
    return {
        "headline": (
            f"Today in {aqi_ctx['city']}: AQI {aqi_ctx['aqi']} ({aqi_ctx['category_level']}). "
            f"{aqi_ctx['outdoor_activity_advice']}"
        ),
        "morning_action": health["recommendations"][0] if health["recommendations"] else "Check today's AQI before heading out.",
        "best_outdoor":   f"{bw['start']} – {bw['end']} (AQI {bw['aqi']})",
        "ai_tip":         health["recommendations"][1] if len(health["recommendations"]) > 1 else "",
        "community_act":  (community["grouped_actions"][0]["actions"][0]["action"] if community["grouped_actions"] else ""),
        "evening_action": health["recommendations"][-1] if health["recommendations"] else "",
        "source":         "template",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run(city: str, user_profile: dict | None = None) -> dict:
    """
    Full 5-stage multi-agent pipeline.

    Input:
      city         — city name string
      user_profile — optional {"age_group": "adult"|"child"|"elderly",
                               "conditions": ["asthma", "heart disease", ...]}

    Output: complete report dict for the dashboard including Phase 3 fields:
      agent_trace     : list of per-agent {agent, emoji, status, duration_ms, output_snippet}
      pipeline_status : "ok" | "partial" | "error"
      final_plan      : structured dict with headline, morning, outdoor, health, evening sections
      user_profile    : echo back the profile used
    """
    pipeline_start = time.time()
    trace: list[dict] = []
    pipeline_status = "ok"

    # ─── Stage 1: AQI Data Agent ──────────────────────────────────────────────
    step1 = _trace_step("AQI Data Agent", "🌫️", "Fetching & interpreting live AQI data")
    trace.append(step1)
    t0 = time.time()
    try:
        raw_aqi = aqi_service.fetch_aqi(city)
        aqi_ctx = aqi_data_agent.run(raw_aqi)
        snippet = f"AQI={aqi_ctx['aqi']} ({aqi_ctx['category_level']}) | PM2.5={aqi_ctx['pm25']} | source={aqi_ctx['data_source']}"
        _finish_step(step1, t0, snippet)
    except Exception as exc:
        _error_step(step1, t0, exc)
        pipeline_status = "error"
        # Cannot continue without AQI data — return minimal error report
        return {
            "city": city, "error": str(exc),
            "agent_trace": trace,
            "pipeline_status": "error",
        }

    # ─── Stage 2: Health Advisory Agent ──────────────────────────────────────
    step2 = _trace_step("Health Advisory Agent", "🏥", "Generating personalised health recommendations via IBM watsonx.ai")
    trace.append(step2)
    t0 = time.time()
    try:
        health_out = health_advisory_agent.run(aqi_ctx, user_profile)
        snippet = f"{len(health_out['recommendations'])} recs | AI={health_out['ai_generated']} | {health_out['model_used']}"
        _finish_step(step2, t0, snippet)
    except Exception as exc:
        _error_step(step2, t0, exc)
        health_out = {"recommendations": [], "ai_generated": False, "model_used": "error"}
        pipeline_status = "partial"

    # ─── Stage 3: Forecasting Agent ───────────────────────────────────────────
    step3 = _trace_step("Forecasting Agent", "📈", "Running 24-hour AQI prediction (Linear Regression + intra-day model)")
    trace.append(step3)
    t0 = time.time()
    try:
        history = aqi_service.fetch_historical_aqi(city, days=7)
        forecast_out = forecasting_agent.run(aqi_ctx, history)
        bw = forecast_out["best_window"]
        snippet = f"Peak={max(p['aqi'] for p in forecast_out['forecast'])} | Best window {bw['start']}-{bw['end']} | {len(forecast_out['warnings'])} warning(s)"
        _finish_step(step3, t0, snippet)
    except Exception as exc:
        _error_step(step3, t0, exc)
        history = []
        forecast_out = {
            "forecast": [], "warnings": [], "summary": "Forecast unavailable.",
            "best_window": {"start": "—", "end": "—", "aqi": "—"},
            "chart_labels": [], "chart_data": [], "chart_low": [], "chart_high": [],
            "hourly_table": [], "sigma": 0,
        }
        pipeline_status = "partial"

    # ─── Stage 4: Community Action Agent ─────────────────────────────────────
    step4 = _trace_step("Community Action Agent", "🤝", "Selecting pollution-reduction actions for residents")
    trace.append(step4)
    t0 = time.time()
    try:
        community_out = community_agent.run(aqi_ctx)
        snippet = f"{community_out['action_count']} actions across {len(community_out['grouped_actions'])} categories"
        _finish_step(step4, t0, snippet)
    except Exception as exc:
        _error_step(step4, t0, exc)
        community_out = {"grouped_actions": [], "ai_message": None, "action_count": 0}
        pipeline_status = "partial"

    # ─── Stage 5: AI Coordinator ──────────────────────────────────────────────
    step5 = _trace_step("AI Coordinator", "🤖", "Assembling Final Daily Action Plan from all agent outputs")
    trace.append(step5)
    t0 = time.time()
    try:
        final_plan = _compose_final_plan(aqi_ctx, health_out, forecast_out, community_out)
        snippet = f"Plan ready | source={final_plan.get('source','?')} | langflow={langflow_service.is_configured()}"
        _finish_step(step5, t0, snippet)
    except Exception as exc:
        _error_step(step5, t0, exc)
        final_plan = {
            "headline": f"AQI {aqi_ctx['aqi']} in {aqi_ctx['city']} today.",
            "morning_action": "", "best_outdoor": "", "ai_tip": "",
            "community_act": "", "evening_action": "", "source": "error",
        }
        pipeline_status = "partial"

    elapsed = round(time.time() - pipeline_start, 2)

    return {
        # ── Core AQI ──
        "city":               aqi_ctx["city"],
        "aqi":                aqi_ctx["aqi"],
        "pm25":               aqi_ctx["pm25"],
        "pm10":               aqi_ctx["pm10"],
        "no2":                aqi_ctx["no2"],
        "o3":                 aqi_ctx["o3"],
        "co":                 aqi_ctx["co"],
        "so2":                aqi_ctx["so2"],
        "category":           aqi_ctx["category"],
        "category_level":     aqi_ctx["category_level"],
        "dominant_pollutant": aqi_ctx["dominant_pollutant"],
        "vulnerable_groups":  aqi_ctx["vulnerable_groups"],
        "outdoor_advice":     aqi_ctx["outdoor_activity_advice"],
        "data_source":        aqi_ctx["data_source"],

        # ── Health Advisory ──
        "recommendations":  health_out["recommendations"],
        "ai_generated":     health_out["ai_generated"],
        "model_used":       health_out["model_used"],

        # ── Forecast ──
        "forecast":         forecast_out["forecast"],
        "warnings":         forecast_out["warnings"],
        "forecast_summary": forecast_out["summary"],
        "best_window":      forecast_out["best_window"],
        "chart_labels":     forecast_out["chart_labels"],
        "chart_data":       forecast_out["chart_data"],
        "chart_low":        forecast_out["chart_low"],
        "chart_high":       forecast_out["chart_high"],
        "hourly_table":     forecast_out["hourly_table"],
        "sigma":            forecast_out["sigma"],

        # ── History ──
        "history":          history,
        "history_labels":   [d["date"]  for d in history],
        "history_data":     [d["aqi"]   for d in history],
        "history_pm25":     [d["pm25"]  for d in history],

        # ── Community ──
        "community_actions":  community_out["grouped_actions"],
        "community_message":  community_out["ai_message"],

        # ── Phase 3: Final Plan + Trace ──
        "final_plan":       final_plan,
        "daily_plan":       final_plan["headline"],   # backward compat for Phase 1 UI
        "agent_trace":      trace,
        "pipeline_status":  pipeline_status,
        "user_profile":     user_profile or {},

        # ── Meta ──
        "pipeline_time_s":  elapsed,
        "langflow_active":  langflow_service.is_configured(),
    }
