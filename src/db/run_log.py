"""Historique des runs : une ligne par exécution du pipeline."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings
from src.db.mongo_client import get_collection
from src.pipeline.run_status import resume_stages


def save_run(
    *,
    run_id: str,
    mois: str,
    stage: str,
    force_update: bool,
    statut: str,
    problemes: List[str],
    duree_secondes: float,
    results: Optional[Dict[str, Any]] = None,
) -> None:
    """Enregistre (ou met à jour) la ligne d'un run. Ne doit jamais casser le pipeline."""
    doc = {
        "run_id": run_id,
        "mois": mois,
        "stage": stage,
        "force_update": force_update,
        "statut": statut,  # complete | partial | failed
        "problemes": problemes,
        "duree_secondes": round(duree_secondes, 2),
        "stages": resume_stages(results),
        "date_fin": datetime.now(timezone.utc),
    }
    get_collection(settings.MONGO_RUNS).update_one(
        {"run_id": run_id}, {"$set": doc}, upsert=True
    )