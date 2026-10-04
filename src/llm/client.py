"""
Wrapper LLM avec basculement automatique (failover) multi-fournisseurs.

Supporte :
- Mode 'auto' : essaie le premier fournisseur disponible dans LLM_PROVIDER_ORDER
  (par défaut: google -> openrouter). En cas d'erreur de quota (429/402/exhaution),
  bascule automatiquement sur le fournisseur suivant sans interrompre le traitement.
- Mode direct ('google' ou 'openrouter').

Chaque fournisseur fait lui-même tourner ses propres clés API en interne
(voir google_client.py / openrouter_client.py) avant de remonter une
GoogleQuotaError/OpenRouterQuotaError ici — ce module ne gère que le
basculement entre fournisseurs, pas entre clés d'un même fournisseur.

Sans LiteLLM : clients natifs google_client / openrouter_client.
"""
from __future__ import annotations

from typing import List, Tuple

from config import settings
from src.llm import google_client, openrouter_client, token_budget
from src.llm.exceptions import LLMError, GoogleQuotaError, OpenRouterQuotaError
from src.llm.rate_limiter import GLOBAL_RATE_LIMITER
from src.llm.response_parser import parse_json_response
from src.utils.logger import get_logger

logger = get_logger()

# Fournisseur actuellement actif (index dans le pipeline)
_CURRENT_PROVIDER_INDEX = 0


def _get_provider_pipeline() -> List[Tuple[str, callable]]:
    """Retourne la liste ordonnée des fournisseurs à essayer."""
    pipeline: List[Tuple[str, callable]] = []
    order = (
        settings.LLM_PROVIDER_ORDER
        if settings.LLM_PROVIDER == "auto"
        else [settings.LLM_PROVIDER]
    )

    for p in order:
        p_clean = p.strip().lower()
        if p_clean in ("google", "google_aistudio", "aistudio"):
            if settings.GOOGLE_AI_API_KEYS:
                pipeline.append(("google", google_client.call_llm))
        elif p_clean == "openrouter":
            if settings.OPENROUTER_API_KEYS:
                pipeline.append(("openrouter", openrouter_client.call_llm))

    if not pipeline:
        # Fallback si mal configuré mais qu'une clé existe
        if settings.GOOGLE_AI_API_KEYS:
            pipeline.append(("google", google_client.call_llm))
        if settings.OPENROUTER_API_KEYS:
            pipeline.append(("openrouter", openrouter_client.call_llm))

    return pipeline


def _check_budget(prompt_tokens: int) -> None:
    limit = settings.LLM_TOKEN_BUDGET_DAILY
    if limit <= 0:
        return
    consumed = token_budget.get_consumed_today()
    reserved = prompt_tokens + settings.LLM_MAX_TOKENS_OUTPUT
    if consumed + reserved > limit:
        raise token_budget.BudgetExceeded(
            f"Budget journalier insuffisant: {limit - consumed} tokens restants, "
            f"environ {reserved} nécessaires."
        )


def _record_usage(prompt_tokens: int, response: str) -> None:
    token_budget.add_consumed(
        prompt_tokens + token_budget.estimate_tokens_from_text(response)
    )


def call_llm(messages: list) -> str:
    global _CURRENT_PROVIDER_INDEX

    pipeline = _get_provider_pipeline()
    if not pipeline:
        raise LLMError(
            "Aucun provider disponible. Renseignez GOOGLE_AI_API_KEY(_2) ou OPENROUTER_API_KEY(_2)."
        )

    prompt_tokens = token_budget.estimate_tokens_for_messages(messages)
    _check_budget(prompt_tokens)

    try:
        GLOBAL_RATE_LIMITER.acquire()
    except Exception:
        pass

    num_providers = len(pipeline)
    last_exc = None

    for i in range(num_providers):
        idx = (_CURRENT_PROVIDER_INDEX + i) % num_providers
        provider_name, call_fn = pipeline[idx]

        try:
            raw = call_fn(messages)

            if idx != _CURRENT_PROVIDER_INDEX:
                logger.info(
                    f"[FAILOVER] Fournisseur actif basculé vers: {provider_name.upper()}"
                )
                _CURRENT_PROVIDER_INDEX = idx

            _record_usage(prompt_tokens, raw)
            return raw

        except (GoogleQuotaError, OpenRouterQuotaError) as quota_err:
            logger.warning(
                f"[FAILOVER] Quota/Limite atteinte sur '{provider_name.upper()}': {quota_err}. "
                f"Tentative de basculement vers un autre fournisseur..."
            )
            last_exc = quota_err
            continue
        except Exception as exc:
            if settings.LLM_PROVIDER == "auto" and num_providers > 1:
                logger.warning(
                    f"[FAILOVER] Erreur sur '{provider_name.upper()}': {exc}. "
                    f"Tentative de basculement vers fournisseur de secours..."
                )
                last_exc = exc
                continue
            raise LLMError(f"[{provider_name}] {exc}") from exc

    raise LLMError(f"Tous les fournisseurs LLM ont échoué. Dernière erreur: {last_exc}")


def call_llm_simple(system: str, user: str) -> str:
    return call_llm(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )


def call_llm_json_avec_retry(
    system: str, user: str, max_retries: int | None = None
) -> dict:
    retries = settings.LLM_MAX_RETRIES if max_retries is None else max_retries
    last_raw = ""
    for attempt in range(retries + 1):
        last_raw = call_llm_simple(system, user)
        data = parse_json_response(last_raw)
        if data:
            return data
        logger.warning(f"Réponse LLM non-JSON, tentative {attempt + 1}/{retries + 1}")
    raise ValueError(
        f"Réponse LLM non parseable après {retries + 1} tentative(s): {last_raw[:200]!r}"
    )

