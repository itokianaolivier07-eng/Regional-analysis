"""Stage 0 — Normalisation + indicateurs Python (multi-territoires)."""
import time
from typing import Dict, Any, Optional
from config import settings
from src.utils.logger import get_logger
from src.db.source_reader import read_all_sources
from src.db.target_writer import save_normalized, save_indicateurs
from src.db.mongo_client import get_pipeline_collection
from src.preprocessing.filtering import (
    normaliser_document,
    filtrer_par_mois,
    deduplicate_documents,
    separer_llm_python,
    build_compact_object,
    compute_indicateurs_python,
    compute_theme_dominant,
)


def run_stage_0(
    mois: str,
    departement: str,
    run_id: Optional[str] = None,
    force_update: bool = False,
) -> Dict[str, Any]:
    logger = get_logger()
    start = time.time()
    logger.info(f"[STAGE 0] {departement} — mois {mois}")

    if departement not in settings.TERRITOIRES:
        raise ValueError(
            f"Territoire inconnu : {departement}. "
            f"Connus : {list(settings.TERRITOIRES.keys())}"
        )

    cfg = settings.TERRITOIRES[departement]
    source_names = cfg.get("sources") or [cfg["source_collection"]]
    sources_brutes = read_all_sources(departement)
    sources_normalisees = [normaliser_document(d) for d in sources_brutes]
    logger.info(f"  Sources lues : {len(sources_brutes)} (collections: {source_names})")

    if not sources_brutes:
        logger.warning(
            f"  Aucune source trouvée dans les collections Mongo {source_names} "
            f"(base '{settings.MONGO_DB_NAME}'). Vérifiez MONGO_SOURCE_CORSE_A/B "
            f"dans .env : le nom de collection est sensible à la casse."
        )

    docs_mois = filtrer_par_mois(sources_normalisees, mois)
    logger.info(f"  Documents du mois {mois} : {len(docs_mois)}")

    if sources_brutes and not docs_mois:
        logger.warning(
            f"  {len(sources_brutes)} source(s) lue(s) mais aucune ne correspond "
            f"au mois '{mois}'. Vérifiez le format de MOIS_CIBLE (attendu: YYYY-MM) "
            f"et les dates de publication_date des documents."
        )

    # --- Faille n°1 : déduplication des near-duplicates (templates social_media) ---
    docs_mois, dedup_stats = deduplicate_documents(docs_mois)
    logger.info(
        f"  Déduplication : {dedup_stats['input']} → {dedup_stats['output']} "
        f"(retirés={dedup_stats['removed']}, social agrégés={dedup_stats['social_aggregated']})"
    )

    if settings.MAX_DOCS_PER_RUN and settings.MAX_DOCS_PER_RUN > 0:
        docs_mois = docs_mois[: settings.MAX_DOCS_PER_RUN]
        logger.info(f"  Limité à MAX_DOCS_PER_RUN={settings.MAX_DOCS_PER_RUN}")

    docs_llm, docs_python = separer_llm_python(docs_mois)
    logger.info(f"  -> LLM : {len(docs_llm)} | Python pur : {len(docs_python)}")

    indicateurs = compute_indicateurs_python(docs_python)
    indicateurs.update(compute_theme_dominant(docs_llm))
    save_indicateurs(indicateurs, mois=mois, departement=departement, run_id=run_id)

    coll = get_pipeline_collection(departement)
    succes, skipped, erreurs = 0, 0, 0

    for doc in docs_llm:
        doc_id = doc.get("document_id")
        if not force_update and doc_id:
            existing = coll.find_one({
                "departement": departement,
                "mois": mois,
                "stage": "L0",
                "document_id": doc_id,
            })
            if existing:
                skipped += 1
                continue
        try:
            compact = build_compact_object(doc)
            compact["document_id"] = doc_id
            compact["run_id"] = run_id
            save_normalized(compact, mois=mois, departement=departement)
            succes += 1
        except Exception as e:
            erreurs += 1
            logger.warning(f"  Erreur normalisation {doc_id}: {e}")

    duree = round(time.time() - start, 2)
    logger.info(
        f"  Stage 0 terminé : {succes} normalisées "
        f"(dont {skipped} skip, {erreurs} erreurs) ({duree}s)"
    )
    return {
        "stage": "0",
        "mois": mois,
        "departement": departement,
        "run_id": run_id,
        "docs_llm": len(docs_llm),
        "docs_python": len(docs_python),
        "succes": succes,
        "skipped": skipped,
        "erreurs": erreurs,
        "dedup_stats": dedup_stats,
        "indicateurs": indicateurs,
        "duree_secondes": duree,
    }