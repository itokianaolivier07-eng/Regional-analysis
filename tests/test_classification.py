"""Tests du classifieur d'articles (src/preprocessing/classification.py)."""
import pytest
from src.preprocessing.classification import classer_domaine

ENV, SEC, TRA = "Environnement & Sécheresse", "Securité & Propreté", "Transports & Mobilité"


@pytest.mark.parametrize("titre,attendu", [
    ("Un important feu à Calenzana, une cinquantaine d'hectares parcourus par les flammes", ENV),
    ("Incendie à Cagnanu : une centaine d’hectares parcourus", ENV),
    ("Vigilance orange canicule prolongée en Corse", ENV),
    ("Un homme de 61 ans tué à Foce, la JIRS se saisit de l'enquête", SEC),
    ("Violences sexuelles sur mineurs : 104 procédures recensées par le parquet d'Ajaccio", SEC),
    ("Un bar d'Ajaccio entièrement détruit par un incendie criminel", SEC),
    ("Une personne en urgence absolue après un choc frontal sur la RT 10 à Ventiseri", TRA),
    ("Un homme grièvement blessé dans un accident de la route à Porto-Vecchio", TRA),
])
def test_faits_cles_classes_dans_le_bon_domaine(titre, attendu):
    assert classer_domaine(titre, "") == attendu


@pytest.mark.parametrize("titre", [
    "Une paillote détruite par un incendie à Sorbo-Ocagnano, deux personnes blessées",
    "Calvi : la terrasse du restaurant Chez Tao prend feu",
    "Les Rencontres de Calenzana, 26 ans à faire vibrer la musique classique",
    "Football - SC Bastia",
])
def test_cas_ambigus_ou_hors_sujet_restent_non_classes(titre):
    assert classer_domaine(titre, "") is None


def test_un_incendie_de_vegetation_n_est_jamais_classe_en_securite():
    assert classer_domaine("Incendie en Balagne : 64 hectares parcourus", "maquis, flammes") != SEC
