"""Lecture des sources et des sorties intermédiaires."""
from typing import Optional, List, Dict, Any
from src.db.mongo_client import (
    get_pipeline_collection,
    get_final_collection,
    get_collection,
)
from config import settings


def read_all_sources(departement: str) -> List[Dict[str, Any]]:
    """Lit toutes les collections sources définies pour le territoire."""
    cfg = settings.TERRITOIRES[departement]
    docs = []
    for nom in cfg.get("sources") or [cfg["source_collection"]]:
        docs += list(get_collection(nom).find({}).sort("_id", 1))
    return docs


def read_stage(mois: str, stage: str, departement: str) -> List[Dict[str, Any]]:
    return list(
        get_pipeline_collection(departement)
        .find({"mois": mois, "stage": stage})
        .sort("_id", 1)
    )


def read_l0(mois: str, departement: str):
    return read_stage(mois, "L0", departement)


def read_l1(mois: str, departement: str):
    return read_stage(mois, "L1", departement)


def read_l2(mois: str, departement: str):
    return read_stage(mois, "L2", departement)


def read_l3(mois: str, departement: str):
    return read_stage(mois, "L3", departement)


def read_indicateurs(mois: str, departement: str) -> Dict[str, Any]:
    return (
        get_pipeline_collection(departement).find_one(
            {"mois": mois, "stage": "indicateurs"}
        )
        or {}
    )


def read_finale(mois: str, departement: str) -> Optional[Dict[str, Any]]:
    """Lit la synthèse finale dans region_synthesis."""
    return get_final_collection(departement).find_one(
        {"region": settings.REGION_NAME, "mois": mois}
    )