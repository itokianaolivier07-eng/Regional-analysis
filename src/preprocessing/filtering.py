"""Normalisation, filtrage et indicateurs Python."""
from typing import List, Dict, Any, Tuple
from datetime import datetime
import hashlib
import re
from config import settings
from src.preprocessing.classification import classer_domaine


def _extract_date_str(value) -> str:
    if value is None: return ""
    if isinstance(value, datetime): return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, dict):
        value = value.get("$date", "")
        return value.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(value, datetime) else str(value)
    if isinstance(value, (int, float)):
        try: return datetime.utcfromtimestamp(value / 1000).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception: return str(value)
    return str(value)


def _mongo_id(doc) -> str:
    value = doc.get("document_id") or doc.get("url_hash") or doc.get("id")
    if value: return str(value)
    oid = doc.get("_id")
    if isinstance(oid, dict): return str(oid.get("$oid", ""))
    return str(oid) if oid is not None else ""


def normaliser_document(doc: dict) -> dict:
    historique = "source_category" not in doc
    date_value = doc.get("date_publication") if historique else doc.get("publication_date")
    title = doc.get("titre") if historique else doc.get("title")
    raw_text = (doc.get("texte_complet") or doc.get("texte")) if historique else doc.get("raw_text")
    category = doc.get("categorie") if historique else doc.get("source_category")
    detected = doc.get("departement_detecte") or []
    if not isinstance(detected, list): detected = [detected] if detected else []
    department = doc.get("department") or next((x for x in detected if x and x != "Région Corse"), None)
    metadata = dict(doc.get("metadata") or {})
    for key in ("topic_category", "business_creations", "business_insolvencies", "value", "price_per_m2", "housing_tension_index"):
        if key in doc and key not in metadata: metadata[key] = doc[key]
    return {
        "document_id": _mongo_id(doc), "title": title, "raw_text": raw_text or "",
        "source_category": category or "news", "publication_date": _extract_date_str(date_value),
        "department": department, "region": doc.get("region") or "Corse", "metadata": metadata,
        "url": doc.get("url"), "municipality": doc.get("municipality"),
        "territoire": doc.get("territoire") or department, "source_name": doc.get("source_name"),
    }


def filtrer_par_mois(docs: List[Dict], mois_cible: str) -> List[Dict]:
    return [d for d in docs if not mois_cible or str(d.get("publication_date", "")).startswith(mois_cible)]


def _normalize_text_for_dedup(text: str) -> str:
    """Normalise un texte pour détecter les near-duplicates (templates social_media)."""
    if not text:
        return ""
    # Retirer les volumes numériques ("Nombre de signalements ... : 374")
    text = re.sub(r"\b\d+\b", "#", text)
    # Minuscules + espaces normalisés
    text = re.sub(r"\s+", " ", text.lower().strip())
    return text


def _social_media_dedup_key(doc: Dict) -> str:
    """Clé de déduplication spécifique aux baromètres social_media."""
    meta = doc.get("metadata") or {}
    topic = meta.get("topic_category") or doc.get("theme_pre_tague") or ""
    dept = doc.get("department") or doc.get("territoire") or ""
    date = str(doc.get("publication_date") or "")[:10]
    text_norm = _normalize_text_for_dedup(doc.get("raw_text") or "")
    # Hash court du texte normalisé pour coller les templates identiques
    text_hash = hashlib.md5(text_norm.encode("utf-8")).hexdigest()[:12]
    return f"sm|{dept}|{topic}|{date}|{text_hash}"


def _generic_dedup_key(doc: Dict) -> str:
    """Clé de déduplication pour news / autres (document_id prioritaire)."""
    doc_id = doc.get("document_id")
    if doc_id:
        return f"id|{doc_id}"
    text_norm = _normalize_text_for_dedup(doc.get("raw_text") or "")
    text_hash = hashlib.md5(text_norm.encode("utf-8")).hexdigest()[:16]
    return f"txt|{text_hash}"


_RE_VOLUME_24H = re.compile(r"Nombre de signalements enregistrés au cours des 24h\s*:\s*[\d.,]+\.?")


def _to_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _apply_social_stats(doc: Dict, volumes: List[float]) -> None:
    """Résume les relevés horaires d'un même baromètre (même jour, même thème).

    Chaque relevé est déjà un compteur glissant « signalements sur 24 h » : les
    additionner compterait chaque signalement ~24 fois. On garde donc la MOYENNE
    de la journée (+ min / pic / nb de relevés) et on réécrit le texte pour que le
    chiffre vu par le LLM soit celui des métadonnées (et non le 1er relevé du jour).
    """
    if not volumes:
        return
    n = len(volumes)
    moyenne = sum(volumes) / n
    meta = doc.setdefault("metadata", {})
    meta["complaint_volume"] = round(moyenne, 1)
    meta["complaint_volume_min"] = min(volumes)
    meta["complaint_volume_max"] = max(volumes)
    meta["nb_releves"] = n
    if n == 1:
        return  # un seul relevé : le texte d'origine est déjà exact
    # Le pic/min horaire n'est PAS mis dans le texte : ces relevés fluctuent trop
    # (31 → 418 dans la même journée) et le LLM les citerait comme des « pics ».
    resume = (
        f"Signalements sur 24h, moyenne de la journée ({n} relevés) : {moyenne:.0f}."
    )
    texte = doc.get("raw_text") or ""
    doc["raw_text"] = (
        _RE_VOLUME_24H.sub(resume, texte) if _RE_VOLUME_24H.search(texte)
        else f"{texte} {resume}".strip()
    )


def deduplicate_documents(docs: List[Dict]) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Déduplique les documents avant calcul d'indicateurs et sauvegarde L0.

    - social_media : regroupe par (département, thème, jour, hash du texte normalisé).
      Conserve UN document par clé et résume les complaint_volume (moyenne, min,
      pic, nb de relevés) : ce sont des compteurs glissants 24 h, on ne les somme pas.
    - autres catégories : dédup stricte par document_id (ou hash texte).

    Retourne (liste_dédupliquée, stats).
    """
    if not docs:
        return [], {"input": 0, "output": 0, "removed": 0, "social_aggregated": 0}

    seen: Dict[str, Dict] = {}
    social_volumes: Dict[str, List[float]] = {}
    social_aggregated = 0

    for doc in docs:
        category = doc.get("source_category") or ""
        if category == "social_media":
            key = _social_media_dedup_key(doc)
            vol = _to_float((doc.get("metadata") or {}).get("complaint_volume"))
            if key in seen:
                if vol is not None:
                    social_volumes[key].append(vol)
                social_aggregated += 1
                continue
            # Première occurrence : on clone pour ne pas muter l'original
            clone = dict(doc)
            clone["metadata"] = dict(doc.get("metadata") or {})
            seen[key] = clone
            social_volumes[key] = [vol] if vol is not None else []
        else:
            key = _generic_dedup_key(doc)
            if key not in seen:
                seen[key] = doc

    for key, volumes in social_volumes.items():
        _apply_social_stats(seen[key], volumes)

    result = list(seen.values())
    stats = {
        "input": len(docs),
        "output": len(result),
        "removed": len(docs) - len(result),
        "social_aggregated": social_aggregated,
    }
    return result, stats


def separer_llm_python(docs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    return ([d for d in docs if d.get("source_category") in settings.CATEGORIES_LLM_DEPARTEMENT],
            [d for d in docs if d.get("source_category") in settings.CATEGORIES_PYTHON_DEPARTEMENT])


def get_source_weight(category: str) -> float:
    """Retourne le poids de fiabilité d'une catégorie de source."""
    return float(settings.SOURCE_WEIGHTS.get(category, settings.DEFAULT_SOURCE_WEIGHT))


def build_compact_object(doc: Dict) -> Dict[str, Any]:
    category = doc.get("source_category") or "news"
    return {
        "document_id": doc.get("document_id"),
        "titre": doc.get("title"),
        "texte": doc.get("raw_text"),
        "categorie": category,
        "theme_pre_tague": (doc.get("metadata") or {}).get("topic_category"),
        # Domaine déduit par Python pour les articles sans thème (voir classification.py).
        # Champ séparé de theme_pre_tague : il sert uniquement à former des lots
        # homogènes, il n'entre pas dans le calcul du thème dominant.
        "theme_infere": (
            None if (doc.get("metadata") or {}).get("topic_category")
            else classer_domaine(doc.get("title") or "", doc.get("raw_text") or "")
        ),
        "date": str(doc.get("publication_date", ""))[:10],
        "publication_date": doc.get("publication_date"),
        "url": doc.get("url"),
        "municipality": doc.get("municipality"),
        "department": doc.get("department"),
        "territoire": doc.get("territoire"),
        "region": doc.get("region"),
        "source_name": doc.get("source_name"),
        "metadata": doc.get("metadata") or {},
        # Faille n°2 : poids exposé pour les stages LLM et l'arbitrage
        "poids_source": get_source_weight(category),
    }


def compute_theme_dominant(docs_llm: List[Dict]) -> Dict[str, Any]:
    """
    Thème dominant avec pondération des sources (Faille n°2).

    - social_media : complaint_volume * poids_source (défaut 1.0)
    - news / government_pub : 1 * poids_source (10 / 5) si un thème est identifiable
    - Les volumes bruts restent disponibles dans repartition_themes_brut
    """
    volumes_pondérés: Dict[str, float] = {}
    volumes_bruts: Dict[str, float] = {}

    for d in docs_llm:
        category = d.get("source_category") or ""
        meta = d.get("metadata") or {}
        topic = meta.get("topic_category") or d.get("theme_pre_tague")
        if not topic:
            continue

        weight = get_source_weight(category)

        if category == "social_media":
            vol = meta.get("complaint_volume")
            try:
                vol = float(vol) if vol is not None else 1.0
            except (TypeError, ValueError):
                vol = 1.0
        else:
            # news, government_pub, etc. : chaque document compte comme 1 signal
            vol = 1.0

        volumes_bruts[topic] = volumes_bruts.get(topic, 0.0) + vol
        volumes_pondérés[topic] = volumes_pondérés.get(topic, 0.0) + (vol * weight)

    if not volumes_pondérés:
        return {}

    theme = max(volumes_pondérés, key=volumes_pondérés.get)
    return {
        "theme_dominant": theme,
        "volume_signalements": volumes_pondérés[theme],
        "repartition_themes": {
            k: round(v, 1) for k, v in sorted(volumes_pondérés.items(), key=lambda x: -x[1])
        },
        "repartition_themes_brut": {
            k: round(v, 1) for k, v in sorted(volumes_bruts.items(), key=lambda x: -x[1])
        },
    }

def compute_indicateurs_python(docs_python: List[Dict]) -> Dict[str, Any]:
    business = [d for d in docs_python if d.get("source_category") == "business_registry"]
    stats = [d for d in docs_python if d.get("source_category") == "official_stats"]
    housing = [d for d in docs_python if d.get("source_category") == "housing"]
    jobs = [d for d in docs_python if d.get("source_category") == "job_offers"]  # NOUVEAU

    creations = sum((d.get("metadata") or {}).get("business_creations", 0) or 0 for d in business)
    insolv = sum((d.get("metadata") or {}).get("business_insolvencies", 0) or 0 for d in business)
    result = {"total_creations_entreprises": creations, "total_insolvabilites": insolv,
              "solde_net_entreprises": creations - insolv, "nb_jours_observes_business": len(business)}
    if stats: result["taux_chomage"] = (stats[-1].get("metadata") or {}).get("value")
    if housing:
        meta = housing[-1].get("metadata") or {}
        result["prix_m2_moyen"] = meta.get("price_per_m2")
        result["indice_tension_locative"] = meta.get("housing_tension_index")

    # NOUVEAU : agrégation par métier, triée du plus tendu au moins tendu
    if jobs:
        par_metier = {}
        for d in jobs:
            meta = d.get("metadata") or {}
            profession = meta.get("profession")
            volume = meta.get("job_volume")
            if profession is None or volume is None:
                continue
            par_metier.setdefault(profession, []).append(
                (d.get("publication_date"), volume)
            )
        emploi_par_metier = {}
        for profession, releves in par_metier.items():
            valeurs = [v for _, v in releves]
            releves_tries = sorted(releves, key=lambda r: r[0] or "")
            emploi_par_metier[profession] = {
                "moyenne": round(sum(valeurs) / len(valeurs), 1),
                "min": min(valeurs),
                "max": max(valeurs),
                "derniere_valeur": releves_tries[-1][1],
                "derniere_date": releves_tries[-1][0],
                "nb_releves": len(valeurs),
            }
        result["emploi_par_metier"] = emploi_par_metier

    return result
