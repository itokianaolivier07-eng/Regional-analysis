"""Écriture des stages et de la synthèse finale régionale."""
from typing import Optional
from config import settings
from src.db.audit import build_upsert
from src.db.mongo_client import get_pipeline_collection, get_final_collection


def _save_stage_doc(doc: dict, stage: str, mois: str, departement: str) -> bool:
    if not doc:
        return False
    doc = dict(doc)
    doc.pop("_id", None)
    doc.update({"stage": stage, "mois": mois, "departement": departement})
    coll = get_pipeline_collection(departement)
    if stage == "L0":
        key = {"mois": mois, "stage": stage, "document_id": doc.get("document_id")}
    else:
        key = {"mois": mois, "stage": stage, "lot_id": doc.get("lot_id")}
    coll.update_one(key, build_upsert(doc), upsert=True)
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
    get_pipeline_collection(departement).update_one(
        {"mois": mois, "stage": "indicateurs"}, build_upsert(doc), upsert=True
    )
    return True


def save_synthese_finale(doc: dict, mois: str, departement: str) -> bool:
    """Écrit la synthèse finale (collection MONGO_REGION_SYNTHESIS)."""    
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
        "territoires_sources": list(settings.TERRITOIRES[region]["sources"]),
    })
    get_final_collection(departement).update_one(
        {"region": region, "mois": mois}, build_upsert(doc), upsert=True
    )
    return True

def purge_lots_obsoletes(stage: str, mois: str, departement: str, lot_ids_a_garder) -> int:
    """Supprime les lots d'un stage qui ne correspondent plus à aucun lot courant."""
    garder = list(lot_ids_a_garder)
    if not garder:
        return 0  # par sécurité : jamais de suppression totale
    res = get_pipeline_collection(departement).delete_many(
        {"mois": mois, "stage": stage, "lot_id": {"$nin": garder}}
    )
    return res.deleted_count

def nettoyer_lots_obsoletes(stage: str, mois: str, departement: str, batches, erreurs: int, logger) -> int:
    """Supprime les lots périmés d'un stage, seulement si aucun lot n'a échoué."""
    if erreurs:
        return 0
    n = purge_lots_obsoletes(stage, mois, departement, [b["lot_id"] for b in batches])
    if n:
        logger.info(f"  Lots {stage} obsolètes supprimés : {n}")
    return n