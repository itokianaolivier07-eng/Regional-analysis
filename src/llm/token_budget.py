"""
Suivi simple et persistant de consommation estimée de tokens (par jour).
Méthode d'estimation grossière: 1 token ≈ 4 caractères (approximatif).
Le compteur est stocké dans CHECKPOINT_DIR/token_budget.json sous la forme
{ "YYYY-MM-DD": int }
"""
import os
import json
from datetime import date

from config import settings


BUDGET_FILE = os.path.join(settings.CHECKPOINT_DIR, "token_budget.json")


def _ensure_dir():
    os.makedirs(settings.CHECKPOINT_DIR, exist_ok=True)


def _load_all():
    _ensure_dir()
    if not os.path.exists(BUDGET_FILE):
        return {}
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_all(data: dict):
    _ensure_dir()
    with open(BUDGET_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _today_key() -> str:
    return date.today().isoformat()


class BudgetExceeded(Exception):
    """Levée lorsque le budget token journalier est dépassé."""
    pass


def get_consumed_today() -> int:
    data = _load_all()
    return int(data.get(_today_key(), 0))


def add_consumed(n: int):
    data = _load_all()
    key = _today_key()
    data[key] = int(data.get(key, 0)) + int(n)
    _save_all(data)


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def estimate_tokens_for_messages(messages: list) -> int:
    # join roles and contents
    if not messages:
        return 0
    parts = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        parts.append(f"{role}: {content}")
    joined = "\n".join(parts)
    return estimate_tokens_from_text(joined)
