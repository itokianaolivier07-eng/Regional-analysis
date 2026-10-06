"""Classification déterministe (Python) des articles sans thème pré-étiqueté.

Pourquoi : les articles de presse (news / government_pub) n'ont pas de
`topic_category`. Ils étaient regroupés en lots « non_classe » dans l'ordre des
dates, puis le LLM devait donner UN SEUL domaine par lot. Des faits de nature
différente survenus le même jour (ex. un incendie et un homicide) tombaient dans
le même lot et héritaient du même domaine → le même fait pouvait être compté dans
deux domaines et fausser l'arbitrage.

Ici chaque article est rattaché à UN domaine avant le découpage en lots, avec
des règles lisibles. En cas de doute (score faible ou ex æquo) on renvoie None :
l'article reste « non_classe » et c'est le LLM qui tranche, comme avant.

Les mots-clés sont à ajuster ICI et nulle part ailleurs.
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple


# Domaines (mêmes libellés que config.settings.DOMAINES)
LOG = "Logement & Pouvoir d'Achat"
SEC = "Securité & Propreté"
ENV = "Environnement & Sécheresse"
TRA = "Transports & Mobilité"
SAN = "Pénurie Médicale & Santé"


# (motif, poids). Un motif est cherché en début de mot, sans accents ni casse.
MOTS_CLES: Dict[str, List[Tuple[str, int]]] = {
    ENV: [
        # Feux de végétation / canicule / sécheresse
        ("incendie", 2), ("feu de", 2), ("feux de", 2), ("megafeux", 3),
        ("depart de feu", 3), ("feu se declare", 3), ("flammes", 2),
        ("hectares", 3), ("maquis", 3), ("evacuent", 1),
        ("canicule", 3), ("secheresse", 3), ("vegetation", 2),
        ("sapeurs-pompiers", 1), ("pompiers", 1),
        ("restriction d'eau", 3), ("eau potable", 2), ("penurie d'eau", 3),
        ("ressource en eau", 2), ("niveau d'eau", 2), ("stocks d'eau", 2),
        ("alerte secheresse", 3),
        ("pollution", 2), ("biodiversite", 2), ("erosion", 2),
        ("vigilance", 1), ("temperatures", 1), ("coupure d'electricite", 1),
        # Intempéries / crues / orages (manquants dans les données réelles)
        ("intemperies", 3), ("intemperie", 3), ("crues", 3), ("crue", 3),
        ("inondations", 3), ("inondation", 3), ("foudre", 2), ("orage", 2),
        ("coulees", 2), ("coulées", 2), ("risque incendie", 3),
    ],
    SEC: [
        ("homicide", 3), ("tue par balle", 3), ("meurtre", 3), ("assassinat", 3),
        ("blesse par balle", 3), ("armes", 2), ("munitions", 2),
        ("stupefiants", 3), ("cocaine", 3), ("cannabis", 3), ("drogue", 2),
        ("deal", 2), ("interpelle", 2), ("interpellation", 2),
        ("garde a vue", 2), ("mis en examen", 3), ("perquisition", 2),
        ("agression", 2), ("agresse", 2), ("violences", 2), ("cambriolage", 2),
        ("braquage", 3), ("banditisme", 3), ("jirs", 3), ("parquet", 1),
        ("explosifs", 3), ("dynamite", 3), ("delinquance", 2),
        ("incivilites", 2), ("dechets", 2), ("proprete", 2),
        ("enquete ouverte", 1), ("refus d'obtemperer", 2),
        ("incendie volontaire", 4), ("incendie criminel", 4),
        ("piste criminelle", 4), ("criminelle", 2), ("criminel", 2),
        ("police", 1), ("gendarmerie", 1),
    ],
    TRA: [
        ("accident de la circulation", 4), ("choc frontal", 4), ("collision", 3),
        ("accident de la route", 4), ("routier", 2), ("trafic", 2),
        ("circulation", 2), ("automobiliste", 2), ("motard", 2),
        ("ter ", 2), ("train", 2), ("bus ", 2), ("ferry", 3),
        ("traversee", 2), ("aeroport", 3), ("vol retarde", 3),
        ("vols annules", 3), ("greve", 2),  # grèves aériennes / transports
        ("navette", 2), ("rt 10", 2), ("rn 193", 2), ("autocar", 2),
        ("transports", 2), ("mobilite", 2),
        # Accidents type "chute de X mètres"
        ("chute de", 2), ("fait une chute", 3),
    ],
    SAN: [
        ("hopital", 3), ("urgences", 3), ("medecin", 2), ("soignants", 2),
        ("infirmier", 2), ("sante", 2), ("patients", 2), ("chu ", 3),
        ("desert medical", 4), ("samu", 2), ("agence regionale de sante", 3),
        ("epidemie", 3), ("vaccin", 3), ("maternite", 2), ("pharmacie", 2),
        ("noyade", 2),  # souvent traité comme fait divers santé / secours
    ],
    LOG: [
        ("loyer", 3), ("logement", 3), ("immobilier", 2), ("pouvoir d'achat", 4),
        ("factures", 2), ("inflation", 3), ("carburant", 2),
        ("aide alimentaire", 3), ("precarite", 3), ("restos du coeur", 3),
        ("hlm", 3), ("locataires", 2), ("saisonniers", 1),
        ("cout de la vie", 3), ("prix des", 1),
    ],
}


# Un feu de bâtiment / de matériel n'est pas un feu de végétation : malus ENV
# si l'un de ces mots est dans le titre.
MALUS_BATIMENT = 5
MOTS_BATIMENT = (
    "paillote", "restaurant", "terrasse", "cuisine", "engin de chantier",
    "transformateur", "appartement", "creche", "voiture", "vehicule", "magasin",
    "batiment agricole", "hangar",
)


SEUIL_SCORE = 3        # score minimal du domaine gagnant
SEUIL_MARGE = 2        # avance minimale sur le 2e domaine


def _norm(texte: str) -> str:
    t = unicodedata.normalize("NFD", texte or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t.lower().replace("’", "'")) + " "


def scores_domaines(titre: str, texte: str) -> Dict[str, int]:
    """Score par domaine : le titre compte double, chaque motif compte une fois."""
    t_titre, t_corps = _norm(titre), _norm(texte)
    scores: Dict[str, int] = {}
    for domaine, motifs in MOTS_CLES.items():
        total = 0
        for motif, poids in motifs:
            rx = r"\b" + re.escape(motif)
            if re.search(rx, t_titre):
                total += 2 * poids
            elif re.search(rx, t_corps):
                total += poids
        if domaine == ENV and any(m in t_titre for m in MOTS_BATIMENT):
            total -= MALUS_BATIMENT
        if total > 0:
            scores[domaine] = total
    return scores


def classer_domaine(titre: str, texte: str) -> Optional[str]:
    """Domaine le plus probable, ou None si le doute est trop grand."""
    scores = scores_domaines(titre, texte)
    if not scores:
        return None
    classement = sorted(scores.items(), key=lambda kv: -kv[1])
    premier, s1 = classement[0]
    s2 = classement[1][1] if len(classement) > 1 else 0
    if s1 >= SEUIL_SCORE and (s1 - s2) >= SEUIL_MARGE:
        return premier
    return None