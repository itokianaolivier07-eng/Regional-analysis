"""
Client minimal pour Google AI Studio (endpoint configurable).

Expose call_llm(messages) et lève LLMError ou GoogleQuotaError en cas d'échec.
Fait tourner plusieurs clés API (settings.GOOGLE_AI_API_KEYS) : si une clé
répond 429/quota, on passe à la suivante avant d'abandonner.
"""
import time
import random
import requests

from config import settings
from src.llm.exceptions import LLMError, GoogleQuotaError
from src.utils.logger import get_logger


_SESSION = requests.Session()
_key_index = 0


def call_llm(messages: list) -> str:
    """Retourne le texte brut de la réponse. Fait tourner les clés sur 429/quota."""
    global _key_index
    keys = [k.strip().strip('"').strip("'") for k in settings.GOOGLE_AI_API_KEYS if k.strip()]
    if not keys:
        raise GoogleQuotaError("Aucune clé Google AI Studio configurée")

    last_quota_err = None
    for i in range(len(keys)):
        idx = (_key_index + i) % len(keys)
        api_key = keys[idx]
        try:
            result = _call_with_key(messages, api_key)
            if idx != _key_index:
                get_logger().info(f"[FAILOVER] Google: bascule vers clé #{idx + 1}")
                _key_index = idx
            return result
        except GoogleQuotaError as exc:
            last_quota_err = exc
            continue

    raise last_quota_err or GoogleQuotaError("Toutes les clés Google AI Studio sont épuisées")


def _call_with_key(messages: list, api_key: str) -> str:
    """Retourne le texte brut de la réponse via l'endpoint v1beta/models/{model}:generateContent."""
    headers = {"Content-Type": "application/json"}
    if api_key.startswith("ya29.") or api_key.startswith("ya29_"):
        headers["Authorization"] = f"Bearer {api_key}"

    # Construire le prompt textuel à partir des messages
    prompt_parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            prompt_parts.append(f"INSTRUCTIONS:\n{content}")
        else:
            prompt_parts.append(f"{content}")
    prompt = "\n\n".join(prompt_parts)

    base = settings.GOOGLE_AI_BASE_URL.rstrip("/")
    primary_model = settings.GOOGLE_AI_MODEL or "gemini-3.5-flash-lite"
    model_candidates = [primary_model]
    for m in ("gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"):
        if m not in model_candidates:
            model_candidates.append(m)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": settings.LLM_MAX_TOKENS_OUTPUT,
            "responseMimeType": "application/json",
        },
    }

    def _extract_text(data: dict) -> str:
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            for path in (
                ("candidates", 0, "output"),
                ("candidates", 0, "text"),
                ("output",),
                ("choices", 0, "message", "content"),
            ):
                try:
                    val = data
                    for key in path:
                        val = val[key]
                    if isinstance(val, str):
                        return val
                    if isinstance(val, dict) and "content" in val:
                        return val["content"]
                except Exception:
                    continue
        raise KeyError("No text candidate found in Google AI response")

    last_error = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        for model in model_candidates:
            call_url = f"{base}/v1beta/models/{model}:generateContent"
            if api_key and not headers.get("Authorization"):
                sep = "&" if "?" in call_url else "?"
                call_url = f"{call_url}{sep}key={api_key}"

            try:
                resp = _SESSION.post(
                    call_url,
                    headers=headers,
                    json=payload,
                    timeout=settings.LLM_TIMEOUT_SECONDES,
                )
                if resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
                    err_msg = f"HTTP {resp.status_code}: {resp.text[:250]}"
                    if "quota" in resp.text.lower() or "resource_exhausted" in resp.text.lower():
                        raise GoogleQuotaError(err_msg)
                    last_error = LLMError(err_msg)
                    backoff = min(4, 0.5 * (2 ** attempt))
                    time.sleep(backoff + random.uniform(0, 0.5))
                    continue

                if resp.status_code in (400, 404):
                    last_error = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    continue

                if resp.status_code >= 500:
                    last_error = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(min(2, 0.25 * (2 ** attempt)))
                    continue

                resp.raise_for_status()
                data = resp.json()
                return _extract_text(data)
            except GoogleQuotaError:
                raise
            except (requests.RequestException, KeyError, IndexError) as exc:
                last_error = LLMError(str(exc))
                time.sleep(min(1, 0.1 * (2 ** attempt)))
                continue

    if last_error and (
        "429" in str(last_error)
        or "quota" in str(last_error).lower()
        or "resource_exhausted" in str(last_error).lower()
    ):
        raise GoogleQuotaError(str(last_error))
    raise last_error or LLMError("Échec de l'appel Google AI Studio")