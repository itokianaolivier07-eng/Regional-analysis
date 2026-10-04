"""Propagation déterministe de la traçabilité entre les stages (format compact)."""
from itertools import zip_longest
from typing import Any, Dict, List
from src.schema.schemas import ENRICHED_LIST_FIELDS

# Limites pour les prompts LLM
_PROMPT_LIMITS = {
    "document_ids": 40,
    "analyses_sources": 30,
    "chiffres_cles": 10,
}

# Limites strictes pour les sorties finales (L4 / région)
_FINAL_LIMITS = {
    "document_ids": 10,
    "analyses_sources": 15,
    "chiffres_cles": 5,
    "priorites": 3,
    "convergences": 5,
    "divergences": 5,
}


def _round_robin(listes: List[List[Any]]) -> List[Any]:
    """Prend un élément par liste à tour de rôle (évite que la 1re liste occupe tout)."""
    resultat, vus = [], set()
    for rang in zip_longest(*listes):
        for valeur in rang:
            if valeur and str(valeur) not in vus:
                resultat.append(valeur)
                vus.add(str(valeur))
    return resultat


def select_enriched(doc: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Extrait les champs de traçabilité d'un document pour le prompt LLM."""
    result = {}
    for field in ENRICHED_LIST_FIELDS:
        value = doc.get(field) or []
        if not isinstance(value, list):
            value = [value]
        result[field] = value[: _PROMPT_LIMITS.get(field, 20)]
    # Propager le lot_id comme analyse source
    if doc.get("lot_id"):
        result.setdefault("analyses_sources", [])
        if doc["lot_id"] not in result["analyses_sources"]:
            result["analyses_sources"] = [doc["lot_id"]] + result.get("analyses_sources", [])
            result["analyses_sources"] = result["analyses_sources"][
                : _PROMPT_LIMITS.get("analyses_sources", 30)
            ]
    return result


def merge_enriched(
    llm_output: Dict[str, Any],
    source_documents: List[Dict[str, Any]],
    *,
    final: bool = False,
) -> Dict[str, Any]:
    """Fusionne la traçabilité depuis les documents sources.

    - analyses_sources : lot_id des analyses du niveau précédent
    - document_ids : échantillon limité
    - chiffres_cles : plafonnés
    Si final=True (L4 / région), plafonds stricts.
    """
    limits = _FINAL_LIMITS if final else _PROMPT_LIMITS

    # --- analyses_sources ---
    # En mode final : uniquement les lot_id des documents réellement utilisés
    # (on ignore ce que le LLM a écrit, il peut se tromper d'identifiants).
    current_as = [] if final else (llm_output.get("analyses_sources") or [])
    if not isinstance(current_as, list):
        current_as = [current_as] if current_as else []
    seen_as = set(str(x) for x in current_as if x)

    for doc in source_documents:
        lid = doc.get("lot_id")
        if lid and str(lid) not in seen_as:
            current_as.append(lid)
            seen_as.add(str(lid))
        if final:
            continue
        for a in doc.get("analyses_sources") or []:
            if a and str(a) not in seen_as:
                current_as.append(a)
                seen_as.add(str(a))

    llm_output["analyses_sources"] = current_as[: limits.get("analyses_sources", 20)]

    # --- document_ids ---
    # Répartis entre tous les documents sources (un par source à tour de rôle),
    # pour que l'échantillon final ne vienne pas d'un seul bilan.
    # En mode final, les ids écrits par le LLM sont ignorés.
    current_docs = [] if final else (llm_output.get("document_ids") or [])
    if not isinstance(current_docs, list):
        current_docs = [current_docs] if current_docs else []

    listes = []
    for doc in source_documents:
        ids = list(doc.get("document_ids") or [])
        if doc.get("document_id"):
            ids.append(doc["document_id"])
        listes.append(ids)
    seen_docs = set(str(x) for x in current_docs if x)
    for did in _round_robin(listes):
        if str(did) not in seen_docs:
            current_docs.append(did)
            seen_docs.add(str(did))

    llm_output["document_ids"] = current_docs[: limits.get("document_ids", 20)]

    # --- chiffres_cles ---
    current_ch = llm_output.get("chiffres_cles") or []
    if not isinstance(current_ch, list):
        current_ch = [current_ch] if current_ch else []
    seen_ch = set(repr(x) for x in current_ch)

    for doc in source_documents:
        for c in doc.get("chiffres_cles") or []:
            key = repr(c)
            if key not in seen_ch:
                current_ch.append(c)
                seen_ch.add(key)

    llm_output["chiffres_cles"] = current_ch[: limits.get("chiffres_cles", 8)]

    # --- priorites / convergences / divergences (L4 / REGION) ---
    for field in ("priorites", "convergences", "divergences"):
        val = llm_output.get(field)
        if isinstance(val, list) and field in limits:
            llm_output[field] = val[: limits[field]]

    return llm_output