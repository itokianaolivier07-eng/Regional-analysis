"""API en lecture seule pour l'interface (historique des analyses)."""
import secrets
from typing import Optional
from starlette.responses import PlainTextResponse
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from config import settings
from src.db.mongo_client import get_collection
from src.pipeline.arbitrage import ORDRE_GRAVITE

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500

_cle_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_cle(cle: Optional[str] = Security(_cle_header)) -> None:
    attendue = settings.API_KEY
    if not attendue:  # pas de clé configurée : mode local, pas de contrôle
        return
    if not cle or not secrets.compare_digest(cle, attendue):
        raise HTTPException(401, "Clé d'API invalide.")

app = FastAPI(
    title="Analyse régionale - API",
    dependencies=[Depends(verifier_cle)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


async def health(request):
    return PlainTextResponse("ok")


app.add_route("/health", health, include_in_schema=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

def _hist():
    return get_collection(settings.MONGO_HISTORY)


def _propre(doc: dict) -> dict:
    """Prépare un document Mongo pour le JSON."""
    doc = dict(doc)
    for champ in ("_id", "empreinte", "run_id", "region"):
        doc.pop(champ, None)
    h = doc.get("horodatage")
    if h is not None:
        doc["horodatage"] = h.isoformat() + ("Z" if h.tzinfo is None else "")
    return doc


def _mois(mois: Optional[str]) -> str:
    """Mois demandé, sinon celui de la dernière analyse enregistrée."""
    if mois:
        return mois
    dernier = _hist().find_one({}, sort=[("horodatage", -1)])
    if not dernier:
        raise HTTPException(404, "Aucune analyse enregistrée.")
    return dernier["mois"]


@app.get("/finale")
def finale(mois: Optional[str] = None):
    """Dernière synthèse finale : le résultat mis en avant."""
    mois = _mois(mois)
    doc = _hist().find_one({"kind": "finale", "mois": mois}, sort=[("horodatage", -1)])
    if not doc:
        raise HTTPException(404, f"Pas de synthèse finale pour {mois}.")
    return _propre(doc)

@app.get("/finale/historique")
def finale_historique(mois: Optional[str] = None, limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)):
    """Toutes les synthèses finales, de la plus récente à la plus ancienne."""
    mois = _mois(mois)
    lignes = _hist().find({"kind": "finale", "mois": mois}).sort("horodatage", -1).limit(limit)
    return {"mois": mois, "historique": [_propre(d) for d in lignes]}


def _iso(h):
    return h.isoformat() + ("Z" if h.tzinfo is None else "") if h else None


@app.get("/stats")
def stats(mois: Optional[str] = None):
    """Chiffres du tableau de bord : documents, dédoublonnage, lots par stage."""
    mois = _mois(mois)
    pipe = get_collection(settings.MONGO_PIPELINE_STAGES_C)
    final = get_collection(settings.MONGO_REGION_SYNTHESIS)

    st = pipe.find_one({"mois": mois, "stage": "stats"}, {"_id": 0}) or {}
    docs = {k: st.get(k) for k in (
        "sources_lues", "documents_periode", "apres_dedoublonnage",
        "retires", "social_agreges", "docs_llm", "docs_python")}

    lots = {s: pipe.count_documents({"mois": mois, "stage": s}) for s in ("L1", "L2", "L3")}
    lots["L4"] = final.count_documents({"mois": mois})

    par_categorie = {
        g["_id"] or "autre": g["n"]
        for g in pipe.aggregate([
            {"$match": {"mois": mois, "stage": "L0"}},
            {"$group": {"_id": "$categorie", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ])
    }

    f = final.find_one({"mois": mois}, {"meta.arbitrage.scores": 1, "_id": 0}) or {}
    scores = ((f.get("meta") or {}).get("arbitrage") or {}).get("scores") or {}
    sources_par_rubrique = {k: v.get("nb_sources") for k, v in scores.items()}

    run = get_collection(settings.MONGO_RUNS).find_one(
        {}, sort=[("date_fin", -1)],
        projection={"_id": 0, "statut": 1, "stage": 1, "duree_secondes": 1, "date_fin": 1},
    ) or {}
    if run:
        run["date_fin"] = _iso(run.get("date_fin"))

    return {
        "mois": mois,
        "documents": docs,
        "lots": lots,
        "par_categorie": par_categorie,
        "sources_par_rubrique": sources_par_rubrique,
        "dernier_run": run,
    }


@app.get("/rubriques")
def rubriques(mois: Optional[str] = None, limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)):
    """Les 5 rubriques : version actuelle (dernière version de chaque lot)."""
    mois = _mois(mois)
    lignes = _hist().find({"kind": "rubrique", "mois": mois}).sort("horodatage", -1).limit(limit)

    derniere_par_lot = {}
    for d in lignes:  # triées de la plus récente à la plus ancienne
        derniere_par_lot.setdefault(d.get("lot_id"), d)

    resultat = []
    for domaine in settings.DOMAINES:
        lots = [d for d in derniere_par_lot.values() if d.get("domaine_critique") == domaine]
        if not lots:
            continue
        resultat.append({
            "domaine": domaine,
            "gravite": max((d.get("gravite") for d in lots if d.get("gravite") in ORDRE_GRAVITE),
                           key=ORDRE_GRAVITE.index, default="modere"),
            "derniere_analyse": _propre(max(lots, key=lambda d: d["horodatage"]))["horodatage"],
            "analyses": [_propre(d) for d in lots],
        })
    return {"mois": mois, "rubriques": resultat}


@app.get("/rubriques/{domaine}/historique")
def historique(domaine: str, mois: Optional[str] = None, limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)):
    """Toutes les versions d'une rubrique, de la plus récente à la plus ancienne."""
    if domaine not in settings.DOMAINES:
        raise HTTPException(404, "Rubrique inconnue.")
    mois = _mois(mois)
    lignes = _hist().find(
        {"kind": "rubrique", "mois": mois, "domaine_critique": domaine}
    ).sort("horodatage", -1).limit(limit)
    return {"domaine": domaine, "mois": mois, "historique": [_propre(d) for d in lignes]}
