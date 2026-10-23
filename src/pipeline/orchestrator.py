"""Orchestrateur — pipeline unique Corse (Haute-Corse + Corse-du-Sud fusionnés)."""
import uuid
from typing import Dict, Any, Optional
from config import settings
from src.utils.logger import get_logger
from src.utils.email_notifier import notify_error
from src.db.mongo_client import ensure_indexes
from src.pipeline.stage0_normalization import run_stage_0
from src.pipeline.stage1_micro import run_stage_1
from src.pipeline.stage2_meso import run_stage_2
from src.pipeline.stage3_bilan import run_stage_3
from src.pipeline.stage4_finale import run_stage_4


def run_pipeline_territoire(
    departement: str,
    mois: str,
    run_id: Optional[str] = None,
    force_update: bool = False,
    stage: str = "all",
) -> Dict[str, Any]:
    """Exécute les stages demandés pour le territoire unifié Corse."""
    logger = get_logger()
    results: Dict[str, Any] = {}

    stages = {
        "0": lambda: run_stage_0(mois, departement, run_id, force_update),
        "1": lambda: run_stage_1(mois, departement, run_id, force_update),
        "2": lambda: run_stage_2(mois, departement, run_id, force_update),
        "3": lambda: run_stage_3(mois, departement, run_id, force_update),
        "4": lambda: run_stage_4(mois, departement, run_id, force_update),
    }

    if stage == "all":
        ordered = ["0", "1", "2", "3", "4"]
    elif stage not in stages:
        raise ValueError(
            f"Stage inconnu : '{stage}'. Attendus : {list(stages.keys())} ou 'all'."
        )
    else:
        ordered = [stage]

    for s in ordered:
        logger.info(f"--- {departement} / stage {s} ---")
        try:
            results[s] = stages[s]()
        except Exception as exc:
            # Erreur bloquante sur un stage - notifie l'admin puis relance
            logger.error(
                f"Erreur bloquante stage {s} ({departement}): {exc}",
                exc_info=True,
            )
            try:
                notify_error(
                    exc,
                    context=f"stage {s} / {departement}",
                    mois=mois,
                    stage=s,
                    run_id=run_id,
                )
            except Exception:
                pass
            raise

        # Un stage 1/2/3 incomplet bloque la suite : pas de finale sur données partielles
        res = results[s]
        if s in ("1", "2", "3") and (res.get("erreurs", 0) > 0 or res.get("error")):
            reste = ordered[ordered.index(s) + 1:]
            if reste:
                logger.error(
                    f"[{departement}] Stage {s} incomplet ({res.get('erreurs', 0)} erreur(s)) "
                    f"- arrêt avant le stage {reste[0]} pour ne pas produire une synthèse "
                    f"sur des données partielles."
                )
                break

    return results


def run_region(
    mois: Optional[str] = None,
    run_id: Optional[str] = None,
    force_update: bool = False,
    stage: str = "all",
) -> Dict[str, Any]:
    """
    Pipeline unique : un seul territoire « Corse » (sources Haute-Corse + Corse-du-Sud).
    La finale (stage 4) est écrite directement dans region_synthesis.
    """
    logger = get_logger()
    mois = settings.resolve_mois(mois)
    
    run_id = run_id or str(uuid.uuid4())[:8]
    ensure_indexes()

    region_name = getattr(settings, "REGION_NAME", "Corse")
    territoire = "Corse"

    logger.info("=" * 60)
    logger.info(f"PIPELINE UNIQUE {region_name.upper()} - mois {mois} - run {run_id}")
    logger.info("Sources fusionnées : Haute-Corse + Corse-du-Sud - 1 pipeline")
    logger.info(f"Finale - collection {settings.MONGO_REGION_SYNTHESIS}")
    logger.info("=" * 60)

    all_results: Dict[str, Any] = {
        "run_id": run_id,
        "mois": mois,
        "region": region_name,
        "territoires": {},
    }

    logger.info(f"[{territoire}] Lancement pipeline unique")
    all_results["territoires"][territoire] = run_pipeline_territoire(
        departement=territoire,
        mois=mois,
        run_id=run_id,
        force_update=force_update,
        stage=stage,
    )

    logger.info("=" * 60)
    logger.info(f"PIPELINE TERMINÉ - résultat dans {settings.MONGO_REGION_SYNTHESIS}")
    logger.info("=" * 60)
    return all_results



def run_pipeline(
    stage: str = "all",
    force_update: bool = False,
    mois: Optional[str] = None,
    departement: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Point d'entrée principal.

    - Si departement est fourni : traite ce territoire (doit être « Corse »).
    - Sinon : lance le pipeline unique Corse.
    """
    mois = settings.resolve_mois(mois)
    
    if departement:
        
        if departement not in settings.TERRITOIRES:
            raise ValueError(
                f"Territoire inconnu : {departement}. "
                f"Connus : {list(settings.TERRITOIRES.keys())}"
            )
        run_id = str(uuid.uuid4())[:8]
        ensure_indexes()
        return {
            "run_id": run_id,
            "mois": mois,
            "territoires": {
                departement: run_pipeline_territoire(
                    departement=departement,
                    mois=mois,
                    run_id=run_id,
                    force_update=force_update,
                    stage=stage,
                )
            },
        }

    return run_region(
        mois=mois,
        force_update=force_update,
        stage=stage,
    )