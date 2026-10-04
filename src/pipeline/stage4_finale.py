"""Stage 4 — Arbitrage final : le domaine est choisi par Python, le LLM rédige."""
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.utils.logger import get_logger
from src.db.source_reader import read_l3, read_indicateurs, read_finale
from src.db.target_writer import save_synthese_finale
from src.llm.client import call_llm_json_avec_retry
from src.schema.schemas import validate_and_fill
from src.pipeline.aggregation import select_enriched, merge_enriched
from src.pipeline.arbitrage import (
    choisir_domaine,
    bilans_du_domaine,
    resume_autres_domaines,
)
from src.llm.prompts.loader import load_prompts

SYSTEM_PROMPT, USER_TEMPLATE = load_prompts("DEPARTEMENT_L4")


def run_stage_4(
    mois: str,
    departement: str,
    run_id: Optional[str] = None,
    force_update: bool = False,
) -> Dict[str, Any]:
    logger = get_logger()
    start = time.time()
    logger.info(f"[STAGE 4] {departement} - arbitrage final / synthèse régionale mois {mois}")

    if not force_update:
        existing = read_finale(mois, departement)
        if existing:
            logger.info("  Synthèse finale déjà présente - skip")
            return {
                "stage": "4",
                "mois": mois,
                "departement": departement,
                "succes": 1,
                "skipped": 1,
                "erreurs": 0,
                "duree_secondes": 0,
            }

    docs_l3 = read_l3(mois, departement)
    logger.info(f"  Bilans L3 : {len(docs_l3)}")
    if not docs_l3:
        return {
            "stage": "4",
            "mois": mois,
            "departement": departement,
            "error": "Aucun document L3",
            "succes": 0,
            "skipped": 0,
            "erreurs": 0,
        }

    # Faille n°4 : les indicateurs (theme_dominant pondéré) participent à l'arbitrage
    indicateurs = read_indicateurs(mois, departement)

    try:
        choix = choisir_domaine(docs_l3, indicateurs=indicateurs)
    except ValueError as e:
        logger.error(f"  Arbitrage impossible : {e}")
        return {
            "stage": "4",
            "mois": mois,
            "departement": departement,
            "error": str(e),
            "succes": 0,
            "skipped": 0,
            "erreurs": 1,
        }
    domaine = choix["domaine"]
    docs_domaine = bilans_du_domaine(docs_l3, domaine)
    autres = resume_autres_domaines(docs_l3, domaine, choix.get("co_critiques"))
    logger.info(
        f"  Domaine retenu : {domaine} "
        f"(scores={ {k: v['score'] for k, v in choix['scores'].items()} }, "
        f"écart={choix['ecart_relatif']}, serré={choix['arbitrage_serre']}, "
        f"theme_dom_ind={choix.get('theme_dominant_indicateurs')})"
    )

    _skip = {
        "_id", "mois", "departement", "stage", "run_id",
        "created_at", "updated_at", "version", "update_count",
    }

    # Faille n°3 : indicateurs autorisés par domaine (évite le mélange
    # ex. "Infirmier Diplômé d'État" dans une synthèse Environnement).
    _INDICATEURS_PAR_DOMAINE = {
        "Environnement & Sécheresse": {
            "theme_dominant", "volume_signalements", "repartition_themes",
            "repartition_themes_brut",
        },
        "Securité & Propreté": {
            "theme_dominant", "volume_signalements", "repartition_themes",
            "repartition_themes_brut",
        },
        "Transports & Mobilité": {
            "theme_dominant", "volume_signalements", "repartition_themes",
            "repartition_themes_brut",
        },
        "Logement & Pouvoir d'Achat": {
            "theme_dominant", "volume_signalements", "repartition_themes",
            "repartition_themes_brut", "prix_m2_moyen", "indice_tension_locative",
        },
        "Pénurie Médicale & Santé": {
            "theme_dominant", "volume_signalements", "repartition_themes",
            "repartition_themes_brut", "emploi_par_metier", "taux_chomage",
        },
    }
    # Indicateurs transversaux toujours utiles quel que soit le domaine
    _INDICATEURS_TRANSVERSAUX = {
        "theme_dominant", "volume_signalements", "repartition_themes",
        "repartition_themes_brut", "taux_chomage",
        "total_creations_entreprises", "total_insolvabilites",
        "solde_net_entreprises", "nb_jours_observes_business",
    }

    def _jsonable(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: _jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_jsonable(v) for v in value]
        return value

    allowed = _INDICATEURS_PAR_DOMAINE.get(domaine, set()) | _INDICATEURS_TRANSVERSAUX
    indicateurs_propres = {
        k: _jsonable(v)
        for k, v in indicateurs.items()
        if k not in _skip and k in allowed
    }
    # NE PAS remettre un second indicateurs_propres = {...} sans filtre

    bilans = [
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
        for d in docs_domaine
    ]
    bilans = _jsonable(bilans)

    user_prompt = USER_TEMPLATE.format(
        mois=mois,
        territoire=departement,
        domaine=domaine,
        bilans_json=json.dumps(bilans, ensure_ascii=False, indent=2, default=str),
        autres_domaines_json=json.dumps(autres, ensure_ascii=False, indent=2),
        arbitrage_json=json.dumps(
            {
                "arbitrage_serre": choix["arbitrage_serre"],
                "ecart_relatif": choix["ecart_relatif"],
                "co_critiques": choix.get("co_critiques", []),
            },
            ensure_ascii=False,
        ),
        indicateurs_json=json.dumps(
            indicateurs_propres, ensure_ascii=False, indent=2, default=str
        ),
    )

    succes, skipped, erreurs = 0, 0, 0

    try:
        data = call_llm_json_avec_retry(SYSTEM_PROMPT, user_prompt)
        data = validate_and_fill(data, "L4")
        data["domaine_critique"] = domaine
        data["gravite"] = choix["gravite"]
        data["statut_urgence"] = choix["gravite"]
        data["run_id"] = run_id
        data["mois"] = mois
        data["source_territoire"] = departement
        data["region"] = "Corse"
        data["meta"] = {
            "run_id": run_id,
            "mois": mois,
            "source_territoire": departement,
            "nb_bilans_l3": len(docs_l3),
            "nb_bilans_domaine": len(docs_domaine),
            "arbitrage": {
                "domaine": domaine,
                "scores": choix["scores"],
                "classement": choix.get("classement"),
                "ecart_relatif": choix["ecart_relatif"],
                "arbitrage_serre": choix["arbitrage_serre"],
                "theme_dominant_indicateurs": choix.get("theme_dominant_indicateurs"),
                "ecart_theme_dominant": choix.get("ecart_theme_dominant"),
                "co_critiques": choix.get("co_critiques", []),
            },
            "date_analyse": datetime.now(timezone.utc).date().isoformat(),
        }
        data = merge_enriched(data, docs_domaine, final=True)
        save_synthese_finale(data, mois=mois, departement=departement)
        succes = 1
        logger.info(f"  Synthèse finale - region_synthesis OK ({departement})")
    except Exception as e:
        erreurs = 1
        logger.error(f"  Erreur synthèse finale {departement}: {e}")

    duree = round(time.time() - start, 2)
    logger.info(
        f"  Stage 4 terminé : succes={succes} erreurs={erreurs} ({duree}s)"
    )
    return {
        "stage": "4",
        "mois": mois,
        "departement": departement,
        "run_id": run_id,
        "succes": succes,
        "skipped": skipped,
        "erreurs": erreurs,
        "duree_secondes": duree,
    }