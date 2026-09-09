"""
services/ibm_watsonx_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wraps the IBM watsonx.ai text-generation API.

How it works:
  1. Authenticates using your IBM Cloud API key to get a bearer token.
  2. Calls the watsonx.ai /text/generation endpoint with a prompt.
  3. Returns the model's response as a plain string.

If no IBM credentials are configured, _every_ call returns None so that
the calling agent can switch to its rule-based fallback automatically.

Docs: https://cloud.ibm.com/apidocs/watsonx-ai
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

IBM_API_KEY      = os.getenv("IBM_API_KEY", "")
IBM_PROJECT_ID   = os.getenv("IBM_PROJECT_ID", "")
IBM_WATSONX_URL  = os.getenv("IBM_WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
IBM_MODEL_ID     = os.getenv("IBM_MODEL_ID", "ibm/granite-13b-chat-v2")

# IBM IAM token endpoint
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"

# Cached token to avoid re-authenticating on every call
_token_cache: dict = {"token": None, "expires_at": 0}


def _get_iam_token() -> str | None:
    """
    Fetch (or return a cached) IBM IAM bearer token.
    Tokens are valid for ~1 hour; we refresh 5 minutes before expiry.
    Returns None if no IBM_API_KEY is set.
    """
    if not IBM_API_KEY:
        return None

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    try:
        resp = requests.post(
            IAM_TOKEN_URL,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": IBM_API_KEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        token_data = resp.json()
        _token_cache["token"] = token_data["access_token"]
        # expires_in is in seconds; subtract 5 min safety margin
        _token_cache["expires_at"] = now + token_data.get("expires_in", 3600) - 300
        return _token_cache["token"]
    except Exception as exc:
        print(f"[IBMwatsonx] IAM token error: {exc}")
        return None


def generate_text(prompt: str, max_tokens: int = 500, temperature: float = 0.7) -> str | None:
    """
    Send `prompt` to the configured IBM watsonx.ai model and return the
    generated text, or None if the call fails / credentials are absent.

    Parameters
    ----------
    prompt      : The full prompt string to send to the model.
    max_tokens  : Maximum tokens in the response (controls length).
    temperature : Creativity level. 0 = deterministic, 1 = most creative.
    """
    if not IBM_API_KEY or not IBM_PROJECT_ID:
        return None   # caller will use rule-based fallback

    token = _get_iam_token()
    if not token:
        return None

    url = f"{IBM_WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"

    payload = {
        "model_id": IBM_MODEL_ID,
        "input": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "decoding_method": "sample",
            "stop_sequences": ["<|end|>"],
        },
        "project_id": IBM_PROJECT_ID,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        # The generated text is nested inside results[0].generated_text
        return result["results"][0]["generated_text"].strip()
    except Exception as exc:
        print(f"[IBMwatsonx] Generation error: {exc}")
        return None
