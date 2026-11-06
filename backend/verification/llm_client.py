import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PLACEHOLDER_KEYS = {
    "",
    "your_gemini_api_key_here",
    "your_openrouter_api_key_here",
    "your_api_key_here",
    "changeme",
    "none",
    "null",
}

_TOKEN_REDACT_PATTERN = re.compile(
    r"(sk-or-v1-[A-Za-z0-9_-]+|sk-or-[A-Za-z0-9_-]+|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._-]+)"
)


class LLMAPIError(RuntimeError):
    """Raised when an LLM API call fails and strict_llm mode is enabled."""


# Process-wide counters so callers (e.g. the API job runner) can report how many
# LLM calls succeeded vs. fell back to the deterministic local evaluator.
LLM_STATS: Dict[str, Any] = {"calls": 0, "succeeded": 0, "fallbacks": 0, "last_error": None}


def _record_fallback(reason: str) -> None:
    LLM_STATS["fallbacks"] += 1
    LLM_STATS["last_error"] = reason


def snapshot_llm_stats() -> Dict[str, Any]:
    return dict(LLM_STATS)


def redact_secrets(message: Any) -> str:
    """Strips any API keys or bearer tokens from log or exception messages."""
    text = str(message)
    for env_var in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        secret = os.getenv(env_var, "").strip()
        if secret and len(secret) >= 6 and secret.lower() not in _PLACEHOLDER_KEYS:
            text = text.replace(secret, "[REDACTED]")
    text = _TOKEN_REDACT_PATTERN.sub("[REDACTED]", text)
    return text


def _get_valid_key(env_name: str) -> Optional[str]:
    val = os.getenv(env_name, "").strip()
    if not val or val.lower() in _PLACEHOLDER_KEYS:
        return None
    return val


def repair_json(text: str) -> Dict[str, Any]:
    """Parses LLM output into JSON, stripping markdown code fences and repairing minor truncation."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Expected top-level JSON object.")
    except json.JSONDecodeError:
        last_brace = cleaned.rfind("}")
        if last_brace != -1:
            repaired = cleaned[: last_brace + 1]
            if not repaired.endswith("]}"):
                if not repaired.endswith("]"):
                    repaired += "]"
                repaired += "}"
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        raise


def call_llm_json(
    prompt: str,
    max_tokens: int = 600,
    strict_llm: bool = False,
    timeout_sec: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Calls OpenRouter or Google Gemini to obtain a structured JSON response.

    - Never exposes API keys in logs or exceptions.
    - If strict_llm=True, raises LLMAPIError on missing credentials or API/parse failures.
    - If strict_llm=False, logs a clear redacted warning and returns None so caller can use deterministic fallback.
    """
    load_dotenv()
    LLM_STATS["calls"] += 1
    openrouter_key = _get_valid_key("OPENROUTER_API_KEY")
    gemini_key = _get_valid_key("GEMINI_API_KEY")

    if not openrouter_key and not gemini_key:
        msg = "No valid OPENROUTER_API_KEY or GEMINI_API_KEY configured."
        if strict_llm:
            raise LLMAPIError(msg)
        _record_fallback(msg)
        logger.warning(f"{msg} Using deterministic local fallback.")
        return None

    # 1. OpenRouter path
    if openrouter_key and openrouter_key.startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "google/gemini-2.5-flash",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        last_err = "Unknown OpenRouter error"
        for attempt in range(2):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
            except Exception as exc:
                last_err = f"OpenRouter request error: {redact_secrets(exc)}"
                break

            if res.status_code == 200:
                try:
                    data = res.json()
                    response_text = data["choices"][0]["message"]["content"].strip()
                    time.sleep(0.2)
                    parsed_json = repair_json(response_text)
                    LLM_STATS["succeeded"] += 1
                    return parsed_json
                except Exception as exc:
                    last_err = f"OpenRouter response parse failure: {redact_secrets(exc)}"
                    break

            if res.status_code in (429, 503) and attempt == 0:
                wait_sec = min(5, int(res.headers.get("Retry-After", 2)))
                time.sleep(wait_sec)
                continue

            last_err = f"OpenRouter HTTP {res.status_code}"
            break

        if strict_llm:
            raise LLMAPIError(last_err)
        _record_fallback(last_err)
        logger.warning(f"{last_err}. Using deterministic local fallback.")
        return None

    # 2. Google Gemini SDK path
    try:
        from google import genai
    except ImportError as exc:
        msg = f"google-genai package is not installed: {redact_secrets(exc)}"
        if strict_llm:
            raise LLMAPIError(msg) from exc
        _record_fallback(msg)
        logger.warning(f"{msg}. Using deterministic local fallback.")
        return None

    try:
        client = genai.Client(api_key=gemini_key)
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            response_text = (getattr(response, "text", None) or "").strip()
        else:
            interaction = client.interactions.create(
                model="gemini-2.5-flash",
                input=prompt,
            )
            response_text = (getattr(interaction, "output_text", None) or "").strip()

        if not response_text:
            raise ValueError("Empty response received from Gemini API.")

        parsed_json = repair_json(response_text)
        LLM_STATS["succeeded"] += 1
        return parsed_json
    except Exception as exc:
        safe_err = f"Gemini API call failed: {redact_secrets(exc)}"
        if strict_llm:
            raise LLMAPIError(safe_err) from None
        _record_fallback(safe_err)
        logger.warning(f"{safe_err}. Using deterministic local fallback.")
        return None
