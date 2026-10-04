"""Tests de l'arbitrage du domaine critique (src/pipeline/arbitrage.py)."""
import pytest
from src.pipeline import arbitrage as A

ENV, SEC, LOG = "Environnement & Sécheresse", "Securité & Propreté", "Logement & Pouvoir d'Achat"


def l3(domaine, gravite, nb_sources=5):
    return {
        "domaine_critique": domaine, "gravite": gravite,
        "analyses_sources": [f"L1-{i}" for i in range(nb_sources)],
        "problematique": "p", "preuve": "preuve", "chiffres_cles": ["a", "b", "c", "d"],
    }


def indicateurs(theme, volumes):
    return {"theme_dominant": theme, "repartition_themes": volumes}


def test_egalite_parfaite_departagee_par_les_sources_pas_par_la_liste():
    # SEC est avant ENV dans settings.DOMAINES : l'ordre de la liste ne doit pas gagner
    docs = [l3(SEC, "critique", nb_sources=14), l3(ENV, "critique", nb_sources=30)]
    r = A.choisir_domaine(docs, None)
    assert r["domaine"] == ENV
    assert r["arbitrage_serre"] is True
    assert r["co_critiques"] == [SEC]


def test_theme_dominant_sans_ecart_reel_ne_donne_aucun_bonus():
    docs = [l3(SEC, "critique"), l3(ENV, "critique", nb_sources=30)]
    ind = indicateurs(SEC, {SEC: 206772, LOG: 206236, ENV: 204381})  # écart 0,26 %
    r = A.choisir_domaine(docs, ind)
    assert r["scores"][SEC]["bonus_theme_dominant"] == 0.0
    assert r["domaine"] == ENV


def test_theme_dominant_reel_donne_un_petit_bonus():
    docs = [l3(SEC, "eleve"), l3(LOG, "eleve")]
    ind = indicateurs(LOG, {LOG: 300, SEC: 200})  # écart 33 %
    r = A.choisir_domaine(docs, ind)
    assert r["scores"][LOG]["bonus_theme_dominant"] == A.BONUS_THEME_DOMINANT
    assert r["domaine"] == LOG


def test_le_bonus_ne_renverse_jamais_un_niveau_de_gravite():
    docs = [l3(ENV, "critique"), l3(LOG, "grave")]
    ind = indicateurs(LOG, {LOG: 1000, ENV: 100})  # thème écrasant
    assert A.choisir_domaine(docs, ind)["domaine"] == ENV


def test_bonus_inferieur_a_l_ecart_entre_deux_gravites():
    ecart = A.POIDS_GRAVITE["critique"] - A.POIDS_GRAVITE["grave"]
    assert A.BONUS_THEME_DOMINANT < ecart + 0.5 * ecart


def test_pas_de_co_critique_quand_l_ecart_est_net():
    docs = [l3(ENV, "critique"), l3(LOG, "modere")]
    r = A.choisir_domaine(docs, None)
    assert r["arbitrage_serre"] is False and r["co_critiques"] == []


def test_contexte_des_autres_domaines_inclut_la_preuve_des_co_critiques():
    docs = [l3(ENV, "critique", 30), l3(SEC, "critique", 14), l3(LOG, "modere")]
    r = A.choisir_domaine(docs, None)
    autres = A.resume_autres_domaines(docs, r["domaine"], r["co_critiques"])
    par_dom = {a["domaine"]: a for a in autres}
    assert par_dom[SEC]["co_critique"] is True and "preuve" in par_dom[SEC]
    assert len(par_dom[SEC]["chiffres_cles"]) == 3
    assert "preuve" not in par_dom[LOG]


def test_aucun_bilan_valide_leve_une_erreur():
    with pytest.raises(ValueError):
        A.choisir_domaine([{"domaine_critique": "inconnu", "gravite": "critique"}])
