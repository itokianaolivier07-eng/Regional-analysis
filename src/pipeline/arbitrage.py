"""Arbitrage déterministe du domaine critique (stage 4).

Python choisit le domaine à partir des bilans L3 (gravité) + des indicateurs
(theme_dominant pondéré). Le LLM ne fait ensuite que rédiger sur ce domaine :
le choix est reproductible et explicable (les scores sont enregistrés dans meta).

Faille n°4 : le score ne dépend plus uniquement du nombre de L3 (qui peut être
artificiellement multiplié) et intègre le signal des indicateurs.
"""
from typing import Any, Dict, List, Optional
from config import settings

# Poids par niveau de gravité. À ajuster ici, nulle part ailleurs.
POIDS_GRAVITE = {
    "critique": 3.0,
    "grave": 2.5,
    "eleve": 2.0,
    "modere": 1.0,
    "faible": 0.5,
}
ORDRE_GRAVITE = ["faible", "modere", "eleve", "grave", "critique"]

# Sous cet écart relatif entre le 1er et le 2e domaine, l'arbitrage est « serré ».
ECART_SERRE = 0.15

# Bonus accordé au theme_dominant des indicateurs (Faille n°4).
# Il doit rester STRICTEMENT inférieur à l'écart de score entre deux niveaux de
# gravité voisins (0.75 : critique→grave ou grave→élevé, pour un seul bilan),
# sinon le volume de signalements pourrait changer le niveau de gravité.
BONUS_THEME_DOMINANT = 0.5

# Le bonus n'est accordé que si le theme_dominant domine réellement : écart
# relatif minimal entre le 1er et le 2e thème dans repartition_themes.
# En dessous, les volumes sont du bruit (ex. août 2026 : 0,26 %) → pas de bonus.
SEUIL_ECART_THEME = 0.10


def ecart_theme_dominant(indicateurs: Optional[Dict[str, Any]]) -> float:
    """Écart relatif entre le 1er et le 2e thème (volumes pondérés). 0.0 si inconnu."""
    repartition = (indicateurs or {}).get("repartition_themes") or {}
    volumes = sorted((v for v in repartition.values() if isinstance(v, (int, float))), reverse=True)
    if len(volumes) < 2 or volumes[0] <= 0:
        return 0.0
    return round((volumes[0] - volumes[1]) / volumes[0], 4)


def _domaine(doc: Dict[str, Any]) -> str:
    dom = doc.get("domaine_critique")
    dom = dom.strip() if isinstance(dom, str) else ""
    return dom if dom in settings.DOMAINES else ""


def _poids(doc: Dict[str, Any]) -> float:
    return POIDS_GRAVITE.get(doc.get("gravite"), POIDS_GRAVITE["modere"])


def _gravite_max(docs: List[Dict[str, Any]]) -> str:
    connues = [d.get("gravite") for d in docs if d.get("gravite") in ORDRE_GRAVITE]
    return max(connues, key=ORDRE_GRAVITE.index) if connues else "modere"


def score_domaines(
    docs_l3: List[Dict[str, Any]],
    indicateurs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Score par domaine (Faille n°4) :
    - base = gravité_max (poids) + 0.5 * moyenne des poids des bilans
      → un domaine avec 1 bilan « critique » n'est pas écrasé par 5 bilans « élevé »
    - bonus si le domaine == theme_dominant des indicateurs
    """
    groupes: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs_l3:
        dom = _domaine(d)
        if dom:
            groupes.setdefault(dom, []).append(d)

    theme_dom = ""
    if indicateurs and ecart_theme_dominant(indicateurs) >= SEUIL_ECART_THEME:
        theme_dom = (indicateurs.get("theme_dominant") or "").strip()

    result = {}
    for dom, docs in groupes.items():
        poids_list = [_poids(d) for d in docs]
        grav_max = _gravite_max(docs)
        base = POIDS_GRAVITE.get(grav_max, 1.0)
        moyenne = sum(poids_list) / len(poids_list) if poids_list else 0.0
        # Score normalisé : gravité max pèse fort, le volume de bilans pèse peu
        score = base + 0.5 * moyenne
        bonus = 0.0
        if theme_dom and dom == theme_dom:
            bonus = BONUS_THEME_DOMINANT
            score += bonus
        result[dom] = {
            "score": round(score, 2),
            "nb_bilans": len(docs),
            "gravite_max": grav_max,
            "bonus_theme_dominant": bonus,
            "score_base": round(base + 0.5 * moyenne, 2),
            # Largeur de la preuve : sert uniquement à départager une égalité parfaite
            "nb_sources": sum(len(d.get("analyses_sources") or []) for d in docs),
        }
    return result


def choisir_domaine(
    docs_l3: List[Dict[str, Any]],
    indicateurs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retourne le domaine gagnant + les scores + l'écart avec le 2e.

    Départage : score, puis gravité_max, puis nombre de bilans, puis largeur de la
    preuve (nb de L1/L2 sources), puis ordre DOMAINES en tout dernier recours
    (toujours le même résultat pour les mêmes données). L'ordre de la liste ne
    doit jamais décider seul entre deux domaines de même gravité.
    """
    scores = score_domaines(docs_l3, indicateurs)
    if not scores:
        raise ValueError("Aucun bilan L3 avec un domaine_critique valide")

    def cle(dom: str):
        s = scores[dom]
        grav_idx = (
            ORDRE_GRAVITE.index(s["gravite_max"])
            if s["gravite_max"] in ORDRE_GRAVITE
            else -1
        )
        return (
            -s["score"], -grav_idx, -s["nb_bilans"], -s["nb_sources"],
            settings.DOMAINES.index(dom),
        )

    classement = sorted(scores, key=cle)
    premier = classement[0]
    if len(classement) > 1:
        s1, s2 = scores[premier]["score"], scores[classement[1]]["score"]
        ecart = round((s1 - s2) / s1, 3) if s1 else 0.0
    else:
        s1, ecart = scores[premier]["score"], 1.0
    # Domaines « co-critiques » : à moins de ECART_SERRE du gagnant. Ils doivent
    # apparaître dans la synthèse finale, pas seulement être cités en contexte.
    co_critiques = [
        dom for dom in classement[1:]
        if s1 and (s1 - scores[dom]["score"]) / s1 < ECART_SERRE
    ]
    return {
        "domaine": premier,
        "scores": scores,
        "classement": classement,
        "ecart_relatif": ecart,
        "arbitrage_serre": ecart < ECART_SERRE,
        "co_critiques": co_critiques,
        "gravite": scores[premier]["gravite_max"],
        "theme_dominant_indicateurs": (indicateurs or {}).get("theme_dominant"),
        "ecart_theme_dominant": ecart_theme_dominant(indicateurs),
    }


def bilans_du_domaine(docs_l3: List[Dict[str, Any]], domaine: str) -> List[Dict[str, Any]]:
    return [d for d in docs_l3 if _domaine(d) == domaine]


def resume_autres_domaines(
    docs_l3: List[Dict[str, Any]],
    domaine: str,
    co_critiques: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Contexte des domaines non retenus (pour le verdict).

    Les domaines co-critiques (arbitrage serré) portent aussi leur fait décisif et
    leurs chiffres clés, pour que le verdict puisse les citer sans rien inventer.
    """
    co_critiques = co_critiques or []
    scores = score_domaines(docs_l3)
    resume = []
    for dom, info in sorted(scores.items(), key=lambda kv: -kv[1]["score"]):
        if dom == domaine:
            continue
        docs = bilans_du_domaine(docs_l3, dom)
        pire = max(docs, key=_poids)
        ligne = {
            "domaine": dom,
            "gravite_max": info["gravite_max"],
            "nb_bilans": info["nb_bilans"],
            "co_critique": dom in co_critiques,
            "problematique": (pire.get("problematique") or "")[:200],
        }
        if dom in co_critiques:
            ligne["preuve"] = (pire.get("preuve") or "")[:300]
            ligne["chiffres_cles"] = list(pire.get("chiffres_cles") or [])[:3]
        resume.append(ligne)
    return resume
