"""
app.py
━━━━━
AirGuard AI – Flask Application Entry Point

This is the main server file. It:
  • Creates the Flask app.
  • Defines all REST API endpoints.
  • Serves the dashboard HTML.
  • Handles errors gracefully.

Run with:  python app.py
"""

import os
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables from .env file FIRST — before any other imports
load_dotenv()

# ── Import agents and services ────────────────────────────────────────────────
# These are imported lazily inside functions to avoid startup errors if
# optional packages (scikit-learn, ibm-watsonx-ai) aren't installed yet.
from agents import coordinator_agent
from services import aqi_service
from rag import knowledge_base

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "airguard-dev-secret")

# Allow cross-origin requests from the frontend (useful during development)
CORS(app)


# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("index.html")


# ─────────────────────────────────────────────────────────────────────────────
# API routes — all return JSON
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/aqi", methods=["GET"])
def api_aqi():
    """
    Phase 1 endpoint — fetch AQI data only (no AI).

    GET /api/aqi?city=Delhi
    Returns: { city, aqi, pm25, pm10, category, ... }
    """
    city = request.args.get("city", "Delhi").strip()
    if not city:
        return jsonify({"error": "city parameter is required"}), 400

    try:
        raw = aqi_service.fetch_aqi(city)
        return jsonify(raw)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/full-report", methods=["GET", "POST"])
def api_full_report():
    """
    Phase 1–3 endpoint — runs the complete multi-agent pipeline.

    GET  /api/full-report?city=Delhi
    POST /api/full-report  body: { "city": "Delhi", "user_profile": {...} }

    Returns the full report dict from coordinator_agent.run().
    """
    # Accept both GET query param and POST JSON body
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        city = body.get("city", "Delhi").strip()
        user_profile = body.get("user_profile")   # optional
    else:
        city = request.args.get("city", "Delhi").strip()
        user_profile = None

    if not city:
        return jsonify({"error": "city parameter is required"}), 400

    try:
        report = coordinator_agent.run(city, user_profile=user_profile)
        return jsonify(report)
    except Exception as exc:
        app.logger.exception("Pipeline error for city '%s'", city)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    """
    Phase 2 endpoint — historical AQI data for the trend chart.

    GET /api/history?city=Delhi&days=7
    Returns: list of { date, aqi, pm25, pm10 }
    """
    city = request.args.get("city", "Delhi").strip()
    days = int(request.args.get("days", "7"))
    days = max(1, min(days, 30))   # clamp to reasonable range

    try:
        history = aqi_service.fetch_historical_aqi(city, days=days)
        return jsonify(history)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Phase 3 endpoint — AI Chat Assistant with conversation history.

    POST /api/chat
    Body: {
      "message":      "Is it safe to jog today?",
      "city":         "Delhi",
      "aqi":          178,
      "history":      [{"role":"user","content":"..."},{"role":"assistant","content":"..."}],
      "context":      {"category":"Unhealthy","daily_plan":"...","recommendations":[...]},
      "user_profile": {"age_group":"adult","conditions":["asthma"]}
    }

    Routes through:
      1. Langflow chat flow (if configured).
      2. RAG retrieval + IBM watsonx.ai with full context injection.
      3. Rule-based RAG chunk fallback.

    Returns: { "reply": "...", "source": "..." }
    """
    from services.ibm_watsonx_service import generate_text

    body         = request.get_json(silent=True) or {}
    message      = body.get("message", "").strip()
    city         = body.get("city", "")
    aqi_val      = body.get("aqi")
    history      = body.get("history", [])          # conversation turns
    ctx          = body.get("context", {})           # current report snapshot
    user_profile = body.get("user_profile", {})

    if not message:
        return jsonify({"error": "message is required"}), 400

    # Build RAG context
    aqi_ctx = None
    if city and aqi_val is not None:
        aqi_ctx = {
            "city": city,
            "aqi": aqi_val,
            "category_level": aqi_service.get_aqi_category(int(aqi_val)).get("level", ""),
        }

    try:
        # ── 1. Langflow chat ──
        from services.langflow_service import run_chat
        langflow_reply = run_chat(message)
        if langflow_reply:
            return jsonify({"reply": langflow_reply, "source": "langflow"})

        # ── 2. RAG retrieval ──
        sources = knowledge_base.retrieve(message, top_k=2)
        guideline_text = "\n\n".join(sources) if sources else ""

        # ── 3. Build a rich prompt for watsonx.ai ──
        profile_text = ""
        if user_profile:
            age  = user_profile.get("age_group", "")
            cond = ", ".join(user_profile.get("conditions", []))
            if age or cond:
                profile_text = f"\nUser profile — Age group: {age}. Conditions: {cond or 'none'}."

        aqi_snapshot = ""
        if city and aqi_val is not None:
            cat = aqi_ctx["category_level"] if aqi_ctx else ""
            dp  = ctx.get("daily_plan", "")
            rec = "\n".join(f"- {r}" for r in ctx.get("recommendations", []))
            aqi_snapshot = (
                f"\nCurrent conditions: {city} AQI={aqi_val} ({cat}).\n"
                f"Daily plan: {dp}\n"
                f"Recommendations:\n{rec}"
            )

        # Build conversation history text (last 4 turns)
        history_text = ""
        for turn in history[-4:]:
            role = "User" if turn.get("role") == "user" else "AirGuard"
            history_text += f"{role}: {turn.get('content','')}\n"

        prompt = (
            "You are AirGuard AI, a friendly air quality health assistant.\n"
            + (f"\nRelevant health guidelines:\n{guideline_text}\n" if guideline_text else "")
            + aqi_snapshot
            + profile_text
            + (f"\nConversation so far:\n{history_text}" if history_text else "")
            + f"\nUser: {message}\n"
            "AirGuard (2-3 sentences, friendly and specific):"
        )

        ai_reply = generate_text(prompt, max_tokens=250, temperature=0.5)
        if ai_reply:
            return jsonify({"reply": ai_reply, "source": "rag+watsonx"})

        # ── 4. RAG chunk fallback ──
        if sources:
            return jsonify({"reply": sources[0], "source": "rag-fallback"})

        return jsonify({
            "reply": (
                "Based on current guidelines, please monitor air quality carefully today. "
                "Check the dashboard for personalised recommendations."
            ),
            "source": "fallback",
        })

    except Exception as exc:
        app.logger.exception("Chat error")
        return jsonify({
            "reply": "I couldn't process that right now. Please check the dashboard for current conditions.",
            "source": "error",
        })


@app.route("/api/rag", methods=["POST"])
def api_rag():
    """
    Phase 2 endpoint — RAG Health Advisory.

    POST /api/rag
    Body: { "question": "Is it safe to run outside?", "city": "Delhi", "aqi": 178 }

    Retrieves relevant WHO/EPA guideline chunks, then calls IBM watsonx.ai
    (or falls back to the best-matching chunk) to answer the question.

    Returns: { "answer": "...", "sources": [...], "chunk_count": N }
    """
    body     = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()
    city     = body.get("city", "")
    aqi_val  = body.get("aqi")

    if not question:
        return jsonify({"error": "question is required"}), 400

    aqi_ctx = None
    if city and aqi_val is not None:
        aqi_ctx = {
            "city": city,
            "aqi": aqi_val,
            "category_level": aqi_service.get_aqi_category(int(aqi_val)).get("level", ""),
        }

    try:
        # Retrieve matching guideline chunks (for "sources" display)
        sources = knowledge_base.retrieve(question, top_k=2)
        # Generate grounded answer
        answer  = knowledge_base.answer_health_question(question, aqi_ctx)
        return jsonify({
            "answer":       answer,
            "sources":      sources,
            "chunk_count":  len(knowledge_base._CHUNKS),
        })
    except Exception as exc:
        app.logger.exception("RAG error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/agent-status", methods=["GET"])
def api_agent_status():
    """
    Phase 3 endpoint — returns the live configuration status of every
    service in the pipeline. The dashboard uses this to show which agents
    are backed by real AI vs rule-based fallback.

    GET /api/agent-status
    Returns: {
      services: { aqicn, watsonx, langflow, rag },
      agents:   [ { name, emoji, powered_by, status } ]
    }
    """
    from services.ibm_watsonx_service import IBM_API_KEY, IBM_PROJECT_ID
    from services.langflow_service import is_configured as langflow_ok

    aqicn_ok   = bool(os.getenv("AQICN_API_KEY"))
    watsonx_ok = bool(IBM_API_KEY and IBM_PROJECT_ID)
    langflow_c = langflow_ok()
    rag_ok     = len(knowledge_base._CHUNKS) > 0

    agents = [
        {
            "name":       "AQI Data Agent",
            "emoji":      "\U0001f32b\ufe0f",
            "powered_by": "AQICN Live API" if aqicn_ok else "Sample data (no AQICN key)",
            "status":     "live" if aqicn_ok else "sample",
            "description": "Fetches and interprets air quality data",
        },
        {
            "name":       "Health Advisory Agent",
            "emoji":      "\U0001f3e5",
            "powered_by": (
                "IBM Langflow" if langflow_c else
                ("IBM watsonx.ai" if watsonx_ok else "Rule-based engine")
            ),
            "status":     "ai" if (watsonx_ok or langflow_c) else "fallback",
            "description": "Generates personalised health recommendations",
        },
        {
            "name":       "Forecasting Agent",
            "emoji":      "\U0001f4c8",
            "powered_by": "Linear Regression + IBM watsonx.ai narrative",
            "status":     "ai" if watsonx_ok else "model",
            "description": "Predicts 24-hour AQI with confidence band",
        },
        {
            "name":       "Community Action Agent",
            "emoji":      "\U0001f91d",
            "powered_by": "IBM watsonx.ai" if watsonx_ok else "Rule-based library",
            "status":     "ai" if watsonx_ok else "fallback",
            "description": "Suggests community pollution-reduction actions",
        },
        {
            "name":       "AI Coordinator",
            "emoji":      "\U0001f916",
            "powered_by": (
                "IBM Langflow multi-agent graph" if langflow_c else
                ("IBM watsonx.ai" if watsonx_ok else "Template engine")
            ),
            "status":     "ai" if (watsonx_ok or langflow_c) else "fallback",
            "description": "Orchestrates all agents and builds the Final Daily Plan",
        },
    ]

    return jsonify({
        "services": {
            "aqicn":    {"configured": aqicn_ok,    "label": "AQICN AQI API"},
            "watsonx":  {"configured": watsonx_ok,  "label": "IBM watsonx.ai"},
            "langflow": {"configured": langflow_c,  "label": "IBM Langflow"},
            "rag":      {"configured": rag_ok,       "label": f"RAG ({len(knowledge_base._CHUNKS)} chunks)"},
        },
        "agents": agents,
    })


@app.route("/api/health", methods=["GET"])
def api_health():
    """Simple health-check endpoint — useful for deployment monitoring."""
    from services.ibm_watsonx_service import IBM_API_KEY, IBM_PROJECT_ID
    from services.langflow_service import is_configured as langflow_ok

    return jsonify({
        "status": "ok",
        "ibm_watsonx_configured": bool(IBM_API_KEY and IBM_PROJECT_ID),
        "langflow_configured": langflow_ok(),
        "aqicn_configured": bool(os.getenv("AQICN_API_KEY")),
        "rag_chunks_loaded": len(knowledge_base._CHUNKS),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "internal server error"}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AirGuard AI Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    debug = os.getenv("FLASK_DEBUG", "true").lower() in ("true", "1", "yes")

    print("\n" + "="*55)
    print("  AirGuard AI starting on http://localhost:%d" % args.port)
    print("="*55 + "\n")

    app.run(host=args.host, port=args.port, debug=debug)
