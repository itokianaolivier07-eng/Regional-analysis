"""Stage 2 — Méso-synthèses L2 (format compact)."""
import time
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from config import settings
from src.utils.logger import get_logger
from src.db.source_reader import read_l1, read_l2
from src.db.target_writer import save_meso_synthese
from src.llm.client import call_llm_json_avec_retry
from src.llm.token_budget import BudgetExceeded
from src.llm.prompts.loader import load_prompts
from src.batching.batcher import create_batches_by_domaine, domaine_synthese
from src.schema.schemas import validate_and_fill
from src.pipeline.aggregation import select_enriched, merge_enriched
from src.pipeline.parallel import run_batches, ThreadSafeCounters

SYSTEM_PROMPT, USER_TEMPLATE = load_prompts("DEPARTEMENT_L2")


def run_stage_2(
    mois: str,
    departement: str,
    run_id: Optional[str] = None,
    force_update: bool = False,
) -> Dict[str, Any]:
    logger = get_logger()
    start = time.time()
    logger.info(f"[STAGE 2] {departement} — méso-synthèses mois {mois}")

    docs_l1 = read_l1(mois, departement)
    logger.info(f"  Micro-synthèses L1 : {len(docs_l1)}")
    if not docs_l1:
        return {
            "stage": "2",
            "mois": mois,
            "departement": departement,
            "error": "Aucun document L1",
            "succes": 0,
            "skipped": 0,
            "erreurs": 0,
        }

    batches = create_batches_by_domaine(docs_l1, domaine_synthese, settings.BATCH_SIZE, "L2")
    for i, b in enumerate(batches, 1):
        b["lot_id"] = f"L2-{departement}-{mois}-{i:04d}"

    by_dom = {}
    for b in batches:
        by_dom[b["domaine"]] = by_dom.get(b["domaine"], 0) + 1
    logger.info(f"  Nombre de lots méso : {len(batches)} — par domaine : {by_dom}")

    existing_ids = set()
    if not force_update:
        existing_ids = {
            d.get("lot_id") for d in read_l2(mois, departement) if d.get("lot_id")
        }
        logger.info(f"  Lots L2 déjà présents : {len(existing_ids)}")

    counters = ThreadSafeCounters("succes", "skipped", "erreurs")
    total_lots = len(batches)
    budget_exceeded_event = threading.Event()

    def _process(batch: Dict[str, Any]) -> None:
        lot_id = batch["lot_id"]

        if not force_update and lot_id in existing_ids:
            counters.increment("skipped")
            idx = batch.get("index", 0)
            logger.info(f"  Lot {lot_id} ({idx}/{total_lots}) déjà traité — skip")
            return

        if budget_exceeded_event.is_set():
            counters.increment("erreurs")
            return

        source_docs = batch["documents"]
        syntheses = [
            {
                "lot_id": d.get("lot_id"),
                "domaine_critique": d.get("domaine_critique"),
                "gravite": d.get("gravite"),
                "problematique": d.get("problematique"),
                "cause": d.get("cause"),
                "preuve": d.get("preuve"),
                "consequence": d.get("consequence"),
                "solution": d.get("solution"),
                "chiffres_cles": d.get("chiffres_cles"),
                "resume": d.get("resume"),
                **select_enriched(d),
            }
            for d in source_docs
        ]

        user_prompt = USER_TEMPLATE.format(
            mois=mois,
            territoire=departement,
            lot_id=lot_id,
            domaine=batch.get("domaine", "non_classe"),
            syntheses_json=json.dumps(syntheses, ensure_ascii=False, indent=2),
        )

        try:
            logger.info(
                f"  Lot {lot_id} ({batch.get('index', 0)}/{total_lots}) — appel LLM…"
            )
            data = call_llm_json_avec_retry(SYSTEM_PROMPT, user_prompt)
            data = validate_and_fill(data, "L2")
            if batch.get("domaine") and batch["domaine"] != "non_classe":
                data["domaine_critique"] = batch["domaine"]
            data["lot_id"] = lot_id
            data["run_id"] = run_id
            data["mois"] = mois
            data["source_territoire"] = departement
            data["region"] = "Corse"
            data["meta"] = {
                "run_id": run_id,
                "lot_numero": batch["index"],
                "mois": mois,
                "source_territoire": departement,
                "nb_analyses_l1": len(syntheses),
                "date_analyse": datetime.now(timezone.utc).date().isoformat(),
            }
            data = merge_enriched(data, source_docs)
            save_meso_synthese(data, mois=mois, departement=departement)
            counters.increment("succes")
            existing_ids.add(lot_id)
            idx = batch.get("index", 0)
            logger.info(f"  Lot {lot_id} ({idx}/{total_lots}) OK")
        except BudgetExceeded as e:
            logger.error(f"  Budget de tokens journalier dépassé, arrêt du stage 2 : {e}")
            budget_exceeded_event.set()
            counters.increment("erreurs")
        except Exception as e:
            counters.increment("erreurs")
            logger.warning(f"  Erreur lot {lot_id}: {e}")

        if settings.MAX_WORKERS <= 1:
            time.sleep(settings.PAUSE_SECONDES)

    run_batches(batches, _process, max_workers=settings.MAX_WORKERS)

    stats = counters.snapshot()
    duree = round(time.time() - start, 2)
    logger.info(
        f"  Stage 2 terminé : {stats['succes']}/{len(batches)} lots "
        f"(dont {stats['skipped']} skip, {stats['erreurs']} erreurs) ({duree}s)"
    )
    return {
        "stage": "2",
        "mois": mois,
        "departement": departement,
        "run_id": run_id,
        "lots_total": len(batches),
        "succes": stats["succes"],
        "skipped": stats["skipped"],
        "erreurs": stats["erreurs"],
        "duree_secondes": duree,
    }