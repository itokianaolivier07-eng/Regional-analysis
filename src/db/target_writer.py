"""Écriture des stages et de la synthèse finale régionale."""
from datetime import datetime, timezone
from typing import Optional
from config import settings
from src.db.mongo_client import get_pipeline_collection, get_final_collection


def _add_audit(doc: dict) -> dict:
    now = datetime.now(timezone.utc)
    doc.setdefault("created_at", now)
    doc["updated_at"] = now
    doc["date_execution"] = now
    doc["version"] = int(doc.get("version", 0)) + 1
    return doc


def _save_stage_doc(doc: dict, stage: str, mois: str, departement: str) -> bool:
    if not doc:
        return False
    doc = dict(doc)
    doc.pop("_id", None)
    doc.update({"stage": stage, "mois": mois, "departement": departement})
    _add_audit(doc)
    coll = get_pipeline_collection(departement)
    if stage == "L0":
        key = {"mois": mois, "stage": stage, "document_id": doc.get("document_id")}
    else:
        key = {"mois": mois, "stage": stage, "lot_id": doc.get("lot_id")}
    coll.update_one(key, {"$set": doc}, upsert=True)
    return True


def save_normalized(doc, mois, departement):
    return _save_stage_doc(doc, "L0", mois, departement)


def save_micro_synthese(doc, mois, departement):
    return _save_stage_doc(doc, "L1", mois, departement)


def save_meso_synthese(doc, mois, departement):
    return _save_stage_doc(doc, "L2", mois, departement)


def save_bilan_transversal(doc, mois, departement):
    return _save_stage_doc(doc, "L3", mois, departement)


def save_indicateurs(
    indicateurs: dict, mois: str, departement: str, run_id: Optional[str] = None
) -> bool:
    doc = {
        **indicateurs,
        "mois": mois,
        "departement": departement,
        "stage": "indicateurs",
        "run_id": run_id,
    }
    _add_audit(doc)
    get_pipeline_collection(departement).update_one(
        {"mois": mois, "stage": "indicateurs"}, {"$set": doc}, upsert=True
    )
    return True


def save_synthese_finale(doc: dict, mois: str, departement: str) -> bool:
    """Écrit la synthèse finale dans region_synthesis."""
    if not doc:
        return False
    doc = dict(doc)
    doc.pop("_id", None)
    region = settings.REGION_NAME
    doc.update({
        "mois": mois,
        "mois_cible": mois,
        "region": region,
        "source_territoire": departement,
        "departement": departement,
        "type": "synthese_finale_region",
        "stage": "L4",
        "territoires_sources": ["Haute-Corse", "Corse-du-Sud"],
    })
    _add_audit(doc)
    get_final_collection(departement).update_one(
        {"region": region, "mois": mois}, {"$set": doc}, upsert=True
    )
    return True