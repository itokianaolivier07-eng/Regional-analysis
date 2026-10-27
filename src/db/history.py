"""Historique des analyses : une ligne ajoutée seulement si le résultat a changé."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from config import settings
from src.db.mongo_client import get_collection
from src.utils.logger import get_logger

_CHAMPS = (
    "domaine_critique", "gravite", "statut_urgence",
    "problematique", "cause", "preuve", "consequence", "solution",
    "verdict", "priorites", "chiffres_cles", "resume",
)


def _empreinte(contenu: dict) -> str:
    """Hash stable du contenu : même résultat -> même empreinte."""
    brut = json.dumps(contenu, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:16]


def append_history(doc: dict, *, kind: str, mois: str, run_id: Optional[str] = None) -> bool:
    """Ajoute une ligne si le résultat diffère du dernier enregistré.

    Retourne True si une ligne a été ajoutée. Ne casse jamais le pipeline.
    """
    try:
        contenu = {k: doc[k] for k in _CHAMPS if k in doc}
        empreinte = _empreinte(contenu)

        coll = get_collection(settings.MONGO_HISTORY)
        cle = {"region": settings.REGION_NAME, "kind": kind, "mois": mois}
        if kind == "rubrique":
            cle["domaine_critique"] = contenu.get("domaine_critique")
            cle["lot_id"] = doc.get("lot_id")
        
        dernier = coll.find_one(cle, sort=[("horodatage", -1)])
        if dernier and dernier.get("empreinte") == empreinte:
            return False  # résultat identique : rien à ajouter

        coll.insert_one({
            **contenu,
            **cle,
            "empreinte": empreinte,
            "run_id": run_id or doc.get("run_id"),
            "horodatage": datetime.now(timezone.utc),
        })
        return True
    except Exception as exc:
        get_logger().warning(f"Historique non enregistré: {exc}")
        return False