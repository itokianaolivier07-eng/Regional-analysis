"""Schémas de sortie compacts du pipeline.

Principe :
- Chaque niveau tranche un domaine_critique cohérent avec les données.
- Champs utiles : problematique, cause, preuve, consequence, solution.
- Traçabilité par analyses_sources (IDs des analyses du niveau précédent),
  pas par dump de tous les documents bruts.
- Les champs techniques (run_id, stage, created_at…) sont ajoutés par Python.
"""
from typing import Any


def _coerce(value: Any, default: Any) -> Any:
    if isinstance(value, type(default)):
        return value
    if isinstance(default, list):
        if value in (None, ""):
            return []
        return value if isinstance(value, list) else [value]
    if isinstance(default, dict):
        if value in (None, ""):
            return {}
        return value if isinstance(value, dict) else default
    if isinstance(default, str):
        if value is None:
            return default
        return "; ".join(map(str, value)) if isinstance(value, list) else str(value)
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def _fill(data: dict, schema: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    return {
        key: _coerce(data[key], default) if key in data and data[key] is not None else default
        for key, default in schema.items()
    }


# L1 — Micro-synthèse (1 analyse d'un lot de documents sources)
SCHEMA_L1 = {
    "lot_id": "",
    "type": "synthese_l1",
    "mois": "",
    "source_territoire": "",
    "region": "Corse",

    "domaine_critique": "",
    "gravite": "modere",

    "problematique": "",
    "cause": "",
    "preuve": "",
    "consequence": "",
    "solution": "",

    "chiffres_cles": [],
    "resume": "",

    "document_ids": [],
    "meta": {},
}


# L2 — Méso-synthèse (consolidation d'analyses L1)
SCHEMA_L2 = {
    "lot_id": "",
    "type": "synthese_l2",
    "mois": "",
    "source_territoire": "",
    "region": "Corse",

    "domaine_critique": "",
    "gravite": "modere",

    "problematique": "",
    "cause": "",
    "preuve": "",
    "consequence": "",
    "solution": "",

    "chiffres_cles": [],
    "resume": "",

    "analyses_sources": [],
    "document_ids": [],
    "meta": {},
}


# L3 — Bilan transversal
SCHEMA_L3 = {
    "lot_id": "",
    "type": "synthese_l3",
    "mois": "",
    "source_territoire": "",
    "region": "Corse",

    "domaine_critique": "",
    "gravite": "modere",

    "problematique": "",
    "cause": "",
    "preuve": "",
    "consequence": "",
    "solution": "",

    "chiffres_cles": [],
    "resume": "",

    "analyses_sources": [],
    "meta": {},
}


# L4 — Arbitrage final département
SCHEMA_L4 = {
    "type": "synthese_finale_departement",
    "mois": "",
    "source_territoire": "",
    "region": "Corse",

    "domaine_critique": "",
    "statut_urgence": "modere",
    "gravite": "modere",

    "problematique": "",
    "cause": "",
    "preuve": "",
    "consequence": "",
    "solution": "",

    "verdict": "",
    "priorites": [],
    "chiffres_cles": [],

    "analyses_sources": [],
    "meta": {},
}


# REGION — Arbitrage régional
SCHEMA_REGION = {
    "type": "synthese_finale_region",
    "mois": "",
    "region": "Corse",
    "territoires_sources": [],

    "domaine_critique": "",
    "statut_urgence": "modere",
    "gravite": "modere",

    "problematique": "",
    "cause": "",
    "preuve": "",
    "consequence": "",
    "solution": "",

    "verdict": "",
    "priorites": [],
    "convergences": [],
    "divergences": [],
    "chiffres_cles": [],

    "analyses_sources": [],
    "meta": {},
}


_SCHEMAS = {
    "L1": SCHEMA_L1,
    "L2": SCHEMA_L2,
    "L3": SCHEMA_L3,
    "L4": SCHEMA_L4,
    "REGION": SCHEMA_REGION,
}

ENRICHED_LIST_FIELDS = [
    "document_ids",
    "analyses_sources",
    "chiffres_cles",
]


def validate_and_fill(data: dict, stage: str) -> dict:
    if stage not in _SCHEMAS:
        raise ValueError(f"Stage inconnu: {stage}")
    return _fill(data, _SCHEMAS[stage])