"""Unified LLM client for market-monitor.

Uses Moonshot API (Kimi K2.6) for all LLM calls.
Falls back to Z.AI (GLM) if Moonshot is unavailable.
"""

import json
import os
import urllib.request
from typing import Optional


MOONSHOT_API_URL = "https://api.moonshot.ai/v1/chat/completions"
ZAI_API_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"

# Kimi K2.6 with thinking=off returns reliable content without reasoning tokens.
# moonshot-v1-8k is deprecated/unavailable — do not use.
DEFAULT_MODEL = "kimi-k2-6"
FALLBACK_MODEL = "glm-5-turbo"


def _call_api(
    url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 500,
    timeout: int = 60,
) -> str:
    """Make an OpenAI-compatible chat completion API call."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning_content", "")


def chat(
    messages: list[dict],
    max_tokens: int = 500,
    api_key: Optional[str] = None,
    fallback: bool = True,
) -> str:
    """Call the LLM API. Tries Moonshot (Kimi) first, then Z.AI fallback.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}
        max_tokens: Maximum tokens to generate
        api_key: Optional API key override
        fallback: Whether to try Z.AI if Moonshot fails

    Returns:
        Generated text content

    Raises:
        ValueError: If no API keys are configured
        urllib.error.HTTPError: If API call fails and fallback is disabled or also fails
    """
    # Try Moonshot first
    moonshot_key = api_key or os.environ.get("MOONSHOT_API_KEY")
    if moonshot_key:
        try:
            return _call_api(
                MOONSHOT_API_URL,
                moonshot_key,
                DEFAULT_MODEL,
                messages,
                max_tokens,
                timeout=60,
            )
        except Exception as e:
            print(f"[LLM] Moonshot error: {e}")
            if not fallback:
                raise

    # Fallback to Z.AI
    zai_key = os.environ.get("ZAI_API_KEY")
    if zai_key:
        try:
            return _call_api(
                ZAI_API_URL,
                zai_key,
                FALLBACK_MODEL,
                messages,
                max_tokens,
                timeout=60,
            )
        except Exception as e:
            print(f"[LLM] Z.AI fallback error: {e}")
            raise

    raise ValueError("No LLM API key configured (MOONSHOT_API_KEY or ZAI_API_KEY)")


def check_moonshot() -> tuple[bool, str]:
    """Check Moonshot API key validity.

    Returns:
        (is_ok, message) tuple
    """
    key = os.environ.get("MOONSHOT_API_KEY")
    if not key:
        return False, "MOONSHOT_API_KEY not set"

    try:
        req = urllib.request.Request(
            "https://api.moonshot.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["id"] for m in data.get("data", [])]
            if DEFAULT_MODEL in models or "kimi-k2.6" in models:
                return True, "Key valid"
            return True, f"Key valid ({len(models)} models)"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "API key invalid or expired"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:100]
