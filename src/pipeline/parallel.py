"""
Exécution parallèle bornée pour les lots des stages 1/2/3 (appels LLM).

Avant ce correctif, `settings.MAX_WORKERS` était défini et documenté (README,
.env) mais n'était utilisé nulle part : tous les stages traitaient leurs lots
strictement en séquence (`for batch in batches: ...`). Ce module fournit un
point d'exécution unique, thread-safe, respectant MAX_WORKERS.

Le rate-limiter (`src/llm/rate_limiter.py`) et le budget de tokens
(`src/llm/token_budget.py`) restent des ressources partagées globales :
augmenter MAX_WORKERS accélère le débit de traitement mais n'augmente PAS le
quota journalier réel des providers — il sera juste atteint plus tôt.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List


def run_batches(
    batches: List[Dict[str, Any]],
    process_fn: Callable[[Dict[str, Any]], None],
    max_workers: int,
) -> None:
    """
    Exécute `process_fn(batch)` pour chaque lot de `batches`.

    - max_workers <= 1 : exécution séquentielle (comportement historique,
      inchangé — c'est le défaut).
    - max_workers > 1  : ThreadPoolExecutor borné à max_workers threads.

    `process_fn` DOIT gérer ses propres exceptions "métier" (erreurs LLM,
    JSON invalide, etc.) en interne pour ne pas interrompre le traitement
    des autres lots — exactement comme le faisait la boucle séquentielle
    d'origine (try/except par lot). Toute exception qui s'échappe malgré
    tout de `process_fn` est relancée ici pour rester visible (pas
    d'échec silencieux).
    """
    if not batches:
        return

    if max_workers is None or max_workers <= 1:
        for batch in batches:
            process_fn(batch)
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_fn, batch): batch for batch in batches}
        for future in as_completed(futures):
            future.result()


class ThreadSafeCounters:
    """Petit compteur multi-clés protégé par un lock, pour les stats
    (succes/skipped/erreurs) accumulées par plusieurs threads en parallèle."""

    def __init__(self, *keys: str):
        self._lock = threading.Lock()
        self._values = {k: 0 for k in keys}

    def increment(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._values[key] = self._values.get(key, 0) + n

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._values)
