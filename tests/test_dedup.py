"""Tests de la déduplication du stage 0 (src/preprocessing/filtering.py)."""
from src.preprocessing.filtering import deduplicate_documents, compute_theme_dominant


def releve(heure, volume, theme="Securité & Propreté", dept="Haute-Corse"):
    return {
        "document_id": f"id-{theme}-{dept}-{heure}", "source_category": "social_media",
        "department": dept, "publication_date": f"2026-08-17T{heure:02d}:30:00",
        "raw_text": (
            f"Baromètre - Département {dept}. Sujet prédominant: {theme}. "
            f"Nombre de signalements enregistrés au cours des 24h: {volume}."
        ),
        "metadata": {"topic_category": theme, "complaint_volume": volume},
    }


def test_les_releves_horaires_ne_sont_pas_additionnes():
    docs = [releve(0, 100), releve(1, 200), releve(2, 300)]
    out, stats = deduplicate_documents(docs)
    assert len(out) == 1 and stats["removed"] == 2
    meta = out[0]["metadata"]
    assert meta["complaint_volume"] == 200.0          # moyenne, pas 600
    assert meta["nb_releves"] == 3
    assert meta["complaint_volume_max"] == 300 and meta["complaint_volume_min"] == 100


def test_le_texte_envoye_au_llm_est_coherent_avec_les_metadonnees():
    out, _ = deduplicate_documents([releve(0, 100), releve(1, 200), releve(2, 300)])
    texte = out[0]["raw_text"]
    assert "moyenne de la journée (3 relevés) : 200" in texte
    assert "au cours des 24h: 100" not in texte       # plus le chiffre du 1er relevé
    assert "pic" not in texte                          # le pic horaire n'est pas exposé


def test_un_releve_unique_garde_son_texte_d_origine():
    d = releve(5, 321)
    out, _ = deduplicate_documents([d])
    assert out[0]["raw_text"] == d["raw_text"]
    assert out[0]["metadata"]["complaint_volume"] == 321.0


def test_themes_et_departements_differents_ne_sont_pas_regroupes():
    docs = [releve(0, 10), releve(0, 20, theme="Transports & Mobilité"), releve(0, 30, dept="Corse-du-Sud")]
    out, stats = deduplicate_documents(docs)
    assert len(out) == 3 and stats["removed"] == 0


def test_jours_differents_ne_sont_pas_regroupes():
    autre_jour = releve(0, 50)
    autre_jour["publication_date"] = "2026-08-18T00:30:00"
    out, _ = deduplicate_documents([releve(0, 10), autre_jour])
    assert len(out) == 2


def test_doublon_d_article_retire_par_document_id():
    a = {"document_id": "x", "source_category": "news", "raw_text": "t", "metadata": {}}
    out, stats = deduplicate_documents([a, dict(a)])
    assert len(out) == 1 and stats["removed"] == 1


def test_theme_dominant_ne_depend_plus_du_nombre_de_releves():
    # Même niveau moyen (200), mais un thème a 3 relevés et l'autre 1 seul :
    # avant la correction (somme) le premier gagnait ×3 ; maintenant c'est à égalité.
    docs = [releve(h, 200) for h in range(3)] + [releve(0, 200, theme="Transports & Mobilité")]
    out, _ = deduplicate_documents(docs)
    rep = compute_theme_dominant(out)["repartition_themes"]
    assert rep["Securité & Propreté"] == rep["Transports & Mobilité"] == 200.0
