"""
services/langflow_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wraps an IBM Langflow (or open-source Langflow) REST endpoint.

IBM Langflow lets you visually build multi-agent pipelines and expose them
as HTTP endpoints. This service calls those endpoints with a JSON payload
and returns the pipeline's output.

Setup (Phase 2+):
  1. Deploy Langflow (IBM or open-source).
  2. Build your AQI pipeline in the Langflow UI.
  3. Set LANGFLOW_BASE_URL, LANGFLOW_FLOW_ID, LANGFLOW_API_KEY in .env.
  4. This service will automatically be used by the coordinator agent.

If Langflow is not configured, calls return None and the system falls back
to the direct watsonx.ai call.

Docs: https://docs.langflow.org/
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

LANGFLOW_BASE_URL = os.getenv("LANGFLOW_BASE_URL", "")
LANGFLOW_FLOW_ID  = os.getenv("LANGFLOW_FLOW_ID", "")
LANGFLOW_API_KEY  = os.getenv("LANGFLOW_API_KEY", "")


def is_configured() -> bool:
    """Return True if Langflow credentials are present."""
    return bool(LANGFLOW_BASE_URL and LANGFLOW_FLOW_ID)


def run_flow(input_data: dict, tweaks: dict | None = None) -> dict | None:
    """
    Call a Langflow flow endpoint with `input_data` as the input payload.

    Parameters
    ----------
    input_data : Dict sent as the flow's input (e.g. {"city": "Delhi", "aqi": 178, ...})
    tweaks     : Optional per-component parameter overrides (Langflow feature).

    Returns the flow's output dict, or None on failure / not configured.
    """
    if not is_configured():
        return None

    url = f"{LANGFLOW_BASE_URL}/api/v1/run/{LANGFLOW_FLOW_ID}"

    headers = {"Content-Type": "application/json"}
    if LANGFLOW_API_KEY:
        headers["Authorization"] = f"Bearer {LANGFLOW_API_KEY}"

    payload = {
        "input_value": input_data,
        "input_type": "json",
        "output_type": "json",
    }
    if tweaks:
        payload["tweaks"] = tweaks

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        # Langflow wraps the output in outputs[0].outputs[0].results.message.data.text
        # We try the deep path first, then fall back to returning the whole response.
        try:
            return data["outputs"][0]["outputs"][0]["results"]
        except (KeyError, IndexError):
            return data
    except Exception as exc:
        print(f"[Langflow] Flow call error: {exc}")
        return None


def run_chat(message: str, session_id: str = "default") -> str | None:
    """
    Send a chat message to a Langflow chat flow and return the reply string.
    Used by the AI Chat Assistant widget on the dashboard.
    """
    if not is_configured():
        return None

    url = f"{LANGFLOW_BASE_URL}/api/v1/run/{LANGFLOW_FLOW_ID}"

    headers = {"Content-Type": "application/json"}
    if LANGFLOW_API_KEY:
        headers["Authorization"] = f"Bearer {LANGFLOW_API_KEY}"

    payload = {
        "input_value": message,
        "input_type": "chat",
        "output_type": "chat",
        "session_id": session_id,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["outputs"][0]["outputs"][0]["results"]["message"]["data"]["text"]
        except (KeyError, IndexError):
            return str(data)
    except Exception as exc:
        print(f"[Langflow] Chat error: {exc}")
        return None
