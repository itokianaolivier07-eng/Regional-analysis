"""Stage 1 — micro-synthèses L1 (format compact)."""
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from config import settings
from src.utils.logger import get_logger
from src.db.source_reader import read_l0, read_l1
from src.db.target_writer import save_micro_synthese
from src.llm.client import call_llm_json_avec_retry
from src.llm.token_budget import BudgetExceeded
from src.llm.prompts.loader import load_prompts
from src.batching.batcher import create_batches_by_domaine, domaine_l0
from src.schema.schemas import validate_and_fill
from src.pipeline.parallel import run_batches, ThreadSafeCounters



SYSTEM_PROMPT, USER_TEMPLATE = load_prompts("DEPARTEMENT_L1")

def _source_ref(d: dict) -> dict:
    return {
        k: d.get(k)
        for k in (
            "document_id", "titre", "url", "municipality",
            "department", "territoire", "region", "source_name", "publication_date",
        )
        if d.get(k) is not None
    }


def _merge_list(current, values):
    result = list(current) if isinstance(current, list) else ([] if not current else [current])
    seen = {str(v) for v in result}
    for value in values:
        if value is None:
            continue
        key = str(value)
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def run_stage_1(
    mois: str,
    departement: str,
    run_id: Optional[str] = None,
    force_update: bool = False,
) -> Dict[str, Any]:
    logger = get_logger()
    start = time.time()
    docs_l0 = read_l0(mois, departement)
    logger.info(f"[STAGE 1] {departement} — {len(docs_l0)} documents L0")
    if not docs_l0:
        return {
            "stage": "1",
            "mois": mois,
            "departement": departement,
            "error": "Aucun document L0",
            "succes": 0,
            "skipped": 0,
            "erreurs": 0,
        }

    batches = create_batches_by_domaine(docs_l0, domaine_l0, settings.BATCH_SIZE, "L1")
    for i, batch in enumerate(batches, 1):
        batch["lot_id"] = f"L1-{departement}-{mois}-{i:04d}"
    by_dom = {}
    for b in batches:
        by_dom[b["domaine"]] = by_dom.get(b["domaine"], 0) + 1
    logger.info(
        f"  Nombre de lots micro : {len(batches)} (batch_size={settings.BATCH_SIZE}) "
        f"— par domaine : {by_dom}"
    )

    existing_ids = set()
    if not force_update:
        existing_ids = {d.get("lot_id") for d in read_l1(mois, departement) if d.get("lot_id")}
        if existing_ids:
            logger.info(f"  Lots L1 déjà présents : {len(existing_ids)}")

    counters = ThreadSafeCounters("succes", "skipped", "erreurs")
    total_lots = len(batches)

    def process(batch):
        lot_id = batch["lot_id"]
        idx = batch.get("index", 0)
        if lot_id in existing_ids and not force_update:
            counters.increment("skipped")
            logger.info(f"  Lot {lot_id} ({idx}/{total_lots}) déjà traité — skip")
            return
        try:
            logger.info(f"  Lot {lot_id} ({idx}/{total_lots}) — appel LLM…")
            signaux = []
            source_refs = []
            for d in batch["documents"]:
                doc_id = str(d.get("document_id") or "")
                # Faille n°6 : troncature différenciée par catégorie
                cat = d.get("categorie") or ""
                max_chars = settings.RAW_TEXT_MAX_CHARS_BY_CATEGORY.get(
                    cat, settings.RAW_TEXT_MAX_CHARS
                )
                raw = str(d.get("texte") or "")
                texte = raw[:max_chars] if max_chars else raw
                signaux.append({
                    "id": doc_id,
                    "titre": d.get("titre"),
                    "texte": texte,
                    "categorie": cat,
                    "theme_pre_tague": d.get("theme_pre_tague"),
                    "date": d.get("date"),
                    "poids_source": d.get("poids_source", 1.0),
                })
                source_refs.append(_source_ref(d))
            
            prompt = USER_TEMPLATE.format(
                mois=mois,
                territoire=departement,
                lot_id=lot_id,
                domaine=batch.get("domaine", "non_classe"),
                signaux_json=json.dumps(signaux, ensure_ascii=False, indent=2),
            )
            data = validate_and_fill(
                call_llm_json_avec_retry(SYSTEM_PROMPT, prompt), "L1"
            )
            if batch.get("domaine") and batch["domaine"] != "non_classe":
                data["domaine_critique"] = batch["domaine"]
            data.update({
                "lot_id": lot_id,
                "run_id": run_id,
                "mois": mois,
                "source_territoire": departement,
                "region": "Corse",
            })
            data["document_ids"] = _merge_list(
                data.get("document_ids"),
                [x.get("document_id") for x in source_refs if x.get("document_id")],
            )
            data["meta"] = {
                **(data.get("meta") or {}),
                "run_id": run_id,
                "lot_numero": batch["index"],
                "mois": mois,
                "source_territoire": departement,
                "nb_documents": len(source_refs),
                "lot_taille": len(source_refs),
                "date_analyse": datetime.now(timezone.utc).date().isoformat(),
            }
            save_micro_synthese(data, mois, departement)
            counters.increment("succes")
            logger.info(f"  Lot {lot_id} ({idx}/{total_lots}) OK")
        except BudgetExceeded:
            counters.increment("erreurs")
            logger.error(f"Budget token atteint au lot {lot_id}")
        except Exception as exc:
            counters.increment("erreurs")
            logger.error(f"Erreur lot {lot_id}: {exc}")
        if settings.MAX_WORKERS <= 1 and settings.PAUSE_SECONDES:
            time.sleep(settings.PAUSE_SECONDES)

    run_batches(batches, process, settings.MAX_WORKERS)
    stats = counters.snapshot()
    duration = round(time.time() - start, 2)
    logger.info(
        f"[STAGE 1] {departement} terminé: {stats['succes']}/{len(batches)} lots, "
        f"{stats['erreurs']} erreur(s), {duration}s"
    )
    return {
        "stage": "1",
        "mois": mois,
        "departement": departement,
        "run_id": run_id,
        "lots_total": len(batches),
        **stats,
        "duree_secondes": duration,
    }