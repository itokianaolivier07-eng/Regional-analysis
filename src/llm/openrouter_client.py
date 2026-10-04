"""
Client minimal pour OpenRouter (API compatible OpenAI).

Expose call_llm(messages) et lève OpenRouterError / OpenRouterQuotaError.
Fait tourner plusieurs clés API (settings.OPENROUTER_API_KEYS) : si une clé
répond 402/429/quota, on passe à la suivante avant d'abandonner.
"""
import time
import random
import requests

from config import settings
from src.llm.exceptions import OpenRouterError, OpenRouterQuotaError
from src.utils.logger import get_logger


_SESSION = requests.Session()
_key_index = 0


def call_llm(messages: list) -> str:
    """Retourne le texte brut de la réponse. Fait tourner les clés sur 402/429/quota."""
    global _key_index
    keys = [k.strip().strip('"').strip("'") for k in settings.OPENROUTER_API_KEYS if k.strip()]
    if not keys:
        raise OpenRouterQuotaError("Aucune clé OpenRouter configurée")

    last_quota_err = None
    for i in range(len(keys)):
        idx = (_key_index + i) % len(keys)
        api_key = keys[idx]
        try:
            result = _call_with_key(messages, api_key)
            if idx != _key_index:
                get_logger().info(f"[FAILOVER] OpenRouter: bascule vers clé #{idx + 1}")
                _key_index = idx
            return result
        except OpenRouterQuotaError as exc:
            last_quota_err = exc
            continue

    raise last_quota_err or OpenRouterQuotaError("Toutes les clés OpenRouter sont épuisées")


def _call_with_key(messages: list, api_key: str) -> str:
    """Retourne le texte brut de la réponse (JSON), ou lève OpenRouterError/OpenRouterQuotaError."""
    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "PipelineTerritorialCorse",
    }
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": settings.LLM_MAX_TOKENS_OUTPUT,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    last_error = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            resp = _SESSION.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.LLM_TIMEOUT_SECONDES,
            )
            if resp.status_code in (402, 429):
                err_msg = f"HTTP {resp.status_code}: {resp.text[:250]}"
                if (
                    resp.status_code == 402
                    or "quota" in resp.text.lower()
                    or "credits" in resp.text.lower()
                ):
                    raise OpenRouterQuotaError(err_msg)
                last_error = OpenRouterError(err_msg)
                backoff = min(6, 1.0 * (2 ** attempt))
                time.sleep(backoff + random.uniform(0, 0.5))
                continue
            if resp.status_code >= 500:
                last_error = OpenRouterError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(min(4, 0.5 * (2 ** attempt)))
                continue

            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except OpenRouterQuotaError:
            raise
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_error = OpenRouterError(str(exc))
            time.sleep(min(2, 0.25 * (2 ** attempt)))

    if last_error and ("429" in str(last_error) or "quota" in str(last_error).lower()):
        raise OpenRouterQuotaError(str(last_error))
    raise last_error or OpenRouterError("Échec inconnu de l'appel OpenRouter")