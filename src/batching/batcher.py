"""Création de lots pour les stages L1 → L3 (Python pur, pas de LLM)."""
import math
from collections import defaultdict
from typing import List, Dict, Any, Callable
from config import settings


def create_batches(
    documents: List[Dict[str, Any]],
    batch_size: int = None,
    stage: str = "L1",
) -> List[Dict[str, Any]]:
    """
    Découpe une liste de documents en lots de taille batch_size.
    Retourne une liste de dicts {lot_id, documents, size}.
    """
    batch_size = batch_size or settings.BATCH_SIZE
    if not documents:
        return []

    n = len(documents)
    n_batches = math.ceil(n / batch_size)
    batches = []

    for i in range(n_batches):
        start = i * batch_size
        end = min(start + batch_size, n)
        lot_docs = documents[start:end]
        lot_id = f"{stage}_{i+1:03d}"
        batches.append({
            "lot_id": lot_id,
            "stage": stage,
            "documents": lot_docs,
            "size": len(lot_docs),
            "index": i + 1,
            "total_lots": n_batches,
            "domaine": "non_classe",
        })
    return batches


def domaine_l0(doc: Dict[str, Any]) -> str:
    """Domaine d'un document L0 (theme_pre_tague ou metadata.topic_category)."""
    t = doc.get("theme_pre_tague") or (doc.get("metadata") or {}).get("topic_category")
    if isinstance(t, str) and t.strip() in settings.DOMAINES:
        return t.strip()
    # Articles sans thème : domaine déduit par Python (lots homogènes par domaine)
    t = doc.get("theme_infere")
    if isinstance(t, str) and t.strip() in settings.DOMAINES:
        return t.strip()
    return "non_classe"


def domaine_synthese(doc: Dict[str, Any]) -> str:
    """Domaine d'une synthèse L1/L2 (champ domaine_critique)."""
    t = doc.get("domaine_critique")
    if isinstance(t, str) and t.strip() in settings.DOMAINES:
        return t.strip()
    return "non_classe"


def create_batches_by_domaine(
    documents: List[Dict[str, Any]],
    key_fn: Callable[[Dict[str, Any]], str],
    batch_size: int = None,
    stage: str = "L1",
    max_lots_per_domaine: int = None,
) -> List[Dict[str, Any]]:
    """
    Regroupe les documents par domaine puis découpe chaque groupe en lots.
    Chaque lot porte un champ « domaine » (domaine imposé ou « non_classe »).

    max_lots_per_domaine (Faille n°7) : si défini, plafonne le nombre de lots
    par domaine (utile en L3 pour éviter la multiplication artificielle).
    On conserve les lots les plus denses (plus de documents).
    """
    batch_size = batch_size or settings.BATCH_SIZE
    groupes: Dict[str, List] = defaultdict(list)
    for d in documents:
        groupes[key_fn(d)].append(d)

    batches: List[Dict[str, Any]] = []
    # non_classe en dernier
    for domaine in sorted(groupes, key=lambda k: (k == "non_classe", k)):
        lots_domaine = create_batches(groupes[domaine], batch_size, stage)
        for lot in lots_domaine:
            lot["domaine"] = domaine
        # Faille n°7 : plafonner le nombre de lots par domaine
        if max_lots_per_domaine and max_lots_per_domaine > 0:
            lots_domaine = sorted(
                lots_domaine, key=lambda l: -l["size"]
            )[:max_lots_per_domaine]
        batches.extend(lots_domaine)

    for i, lot in enumerate(batches, 1):
        lot["index"] = i
        lot["total_lots"] = len(batches)
    return batches