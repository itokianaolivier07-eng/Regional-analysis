"""Orchestrateur — pipeline unique Corse (Haute-Corse + Corse-du-Sud fusionnés)."""
import uuid
from typing import Dict, Any, Optional
from config import settings
from src.utils.logger import get_logger
from src.db.mongo_client import ensure_indexes
from src.db.source_reader import read_finale
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
    elif stage == "region":
        # Avec le pipeline unique, la finale L4 EST déjà la synthèse régionale
        # (écrite dans region_synthesis). On relance juste le stage 4.
        ordered = ["4"]
    elif stage not in stages:
        raise ValueError(
            f"Stage inconnu : '{stage}'. Attendus : {list(stages.keys())}, 'all' ou 'region'."
        )
    else:
        ordered = [stage]

    for s in ordered:
        logger.info(f"--- {departement} / stage {s} ---")
        results[s] = stages[s]()

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
    mois = mois or settings.MOIS_CIBLE
    if not mois:
        raise ValueError("MOIS_CIBLE non défini (arg --mois ou .env).")

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

    if stage == "all" and not force_update and read_finale(mois, territoire):
        logger.info(f"[{territoire}] Déjà traité (synthèse finale existante) - skip")
        all_results["territoires"][territoire] = {"skipped": True}
    else:
        logger.info(f"[{territoire}] Lancement pipeline unique")
        all_results["territoires"][territoire] = run_pipeline_territoire(
            departement=territoire,
            mois=mois,
            run_id=run_id,
            force_update=force_update,
            stage=stage,
        )

    logger.info("=" * 60)
    logger.info("PIPELINE TERMINÉ - résultat dans region_synthesis")
    logger.info("=" * 60)
    return all_results


# Alias rétro-compatible
run_region_corse = run_region


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
    mois = mois or settings.MOIS_CIBLE
    if not mois:
        raise ValueError("MOIS_CIBLE non défini.")

    if departement:
        # Accepte les anciens noms → redirige vers Corse
        if departement in ("Haute-Corse", "Corse-du-Sud"):
            get_logger = __import__("src.utils.logger", fromlist=["get_logger"]).get_logger
            get_logger().warning(
                f"Territoire '{departement}' fusionné dans le pipeline unique « Corse »."
            )
            departement = "Corse"
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

    return run_region_corse(
        mois=mois,
        force_update=force_update,
        stage=stage,
    )
