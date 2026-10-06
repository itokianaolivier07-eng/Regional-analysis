"""Tests du classifieur d'articles (src/preprocessing/classification.py)."""
import pytest
from src.preprocessing.classification import classer_domaine

ENV = "Environnement & Sécheresse"
SEC = "Securité & Propreté"
TRA = "Transports & Mobilité"
SAN = "Pénurie Médicale & Santé"
LOG = "Logement & Pouvoir d'Achat"


# ---------------------------------------------------------------------------
# Cas positifs : classification attendue
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("titre,attendu", [
    # ENV – feux / canicule / sécheresse
    ("Un important feu à Calenzana, une cinquantaine d'hectares parcourus par les flammes", ENV),
    ("Incendie à Cagnanu : une centaine d’hectares parcourus", ENV),
    ("Vigilance orange canicule prolongée en Corse", ENV),
    ("En Haute-Corse, l'alerte sécheresse est maintenue", ENV),
    ("Venaco : un incendie se déclare au pont de Noceta, 5 hectares de maquis brûlés", ENV),
    # ENV – intempéries / crues (nouveaux)
    ("Évacuation de la vallée de l'Asco, coulées noires dans la Restonica... Le point sur les intempéries", ENV),
    ("Face au risque de crues, la préfecture interdit l'accès à des cours d'eau en Corse-du-Sud", ENV),
    # SEC
    ("Un homme de 61 ans tué à Foce, la JIRS se saisit de l'enquête", SEC),
    ("Violences sexuelles sur mineurs : 104 procédures recensées par le parquet d'Ajaccio", SEC),
    ("Un bar d'Ajaccio entièrement détruit par un incendie criminel", SEC),
    ("Quatre personnes en garde à vue après la découverte de dynamite et de plusieurs kilos de drogue à Bastia", SEC),
    ("\"C'est dégueulasse...\". La paillote le Week-end à Ajaccio détruite dans un incendie, la piste criminelle privilégiée", SEC),
    # TRA
    ("Une personne en urgence absolue après un choc frontal sur la RT 10 à Ventiseri", TRA),
    ("Un homme grièvement blessé dans un accident de la route à Porto-Vecchio", TRA),
    ("Six blessés dans un choc frontal entre deux voitures à Valle-di-Rostino", TRA),
    ("Speloncato : une voiture fait une chute de 80 mètres", TRA),
    ("Grève chez Easyjet : une centaine de vols annulés en France, lesquels sont concernés en Corse ?", TRA),
])
def test_faits_cles_classes_dans_le_bon_domaine(titre, attendu):
    assert classer_domaine(titre, "") == attendu


# ---------------------------------------------------------------------------
# Cas ambigus / hors sujet → None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("titre", [
    "Une paillote détruite par un incendie à Sorbo-Ocagnano, deux personnes blessées",
    "Calvi : la terrasse du restaurant Chez Tao prend feu",
    "Les Rencontres de Calenzana, 26 ans à faire vibrer la musique classique",
    "Football - SC Bastia",
    "VIDÉO. GFCA - Dernière ligne droite avant la reprise en National 2",
    "Une médaille d'argent en relais au championnat d'Europe pour le jeune nageur ajaccien Sauveur Cristofini",
    "Vidéo. En immersion au cœur du festival Jazz in Aiacciu",
    "VIDÉO. #Municipales2026 : À Bastia, neuf élus de l'opposition soutiennent le recours",
    "Neuf conseillers municipaux de l'opposition rejoignent le recours administratif contre l'élection de Gilles Simeoni à Bastia",
    "Pétanque : jouer aux boules en langue corse",
    "\"La saison s’inscrirait en deçà de 2025\" : pourquoi le bilan de l'activité touristique est déjà défavorable en Corse",
])
def test_cas_ambigus_ou_hors_sujet_restent_non_classes(titre):
    assert classer_domaine(titre, "") is None


# ---------------------------------------------------------------------------
# Règles de non-confusion
# ---------------------------------------------------------------------------

def test_un_incendie_de_vegetation_n_est_jamais_classe_en_securite():
    assert classer_domaine("Incendie en Balagne : 64 hectares parcourus", "maquis, flammes") != SEC


def test_incendie_criminel_va_en_securite_pas_en_environnement():
    assert classer_domaine(
        "La paillote le Week-end à Ajaccio détruite dans un incendie, la piste criminelle privilégiée",
        "La piste criminelle est privilégiée."
    ) == SEC


def test_feu_de_paillote_sans_piste_criminelle_reste_non_classe():
    # Malus bâtiment → score ENV trop bas → None
    assert classer_domaine(
        "Une paillote détruite par un incendie à Ajaccio",
        "Les dégâts sont très importants."
    ) is None