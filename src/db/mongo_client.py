"""Accès MongoDB. Les collections sont entièrement déterminées par .env."""
from pymongo import MongoClient
from pymongo.collection import Collection
from config import settings

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        try:
            _client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
            _client.admin.command("ping")
        except ValueError as exc:
            raise ValueError(f"MONGO_URI invalide: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"MongoDB inaccessible: {exc}") from exc
    return _client


def get_db():
    return get_client()[settings.MONGO_DB_NAME]


def get_collection(name: str) -> Collection:
    if not name:
        raise ValueError("Nom de collection Mongo vide.")
    return get_db()[name]


def _territory_config(departement: str) -> dict:
    try:
        return settings.TERRITOIRES[departement]
    except KeyError as exc:
        raise ValueError(f"Territoire inconnu: {departement}") from exc


def get_pipeline_collection(departement: str) -> Collection:
    # Pipeline unique Corse → toujours pipeline_stage_C
    _territory_config(departement)  # valide le territoire
    return get_collection(settings.MONGO_PIPELINE_STAGES_C)


def get_final_collection(departement: str) -> Collection:
    # Finale = region_synthesis
    _territory_config(departement)
    return get_collection(settings.MONGO_REGION_SYNTHESIS)

def get_region_final_collection() -> Collection:
    return get_collection(settings.MONGO_REGION_SYNTHESIS)

def ensure_indexes() -> None:
    for departement in settings.TERRITOIRES:
        pipeline = get_pipeline_collection(departement)
        pipeline.create_index([("mois", 1), ("stage", 1), ("lot_id", 1)])
        pipeline.create_index([("mois", 1), ("stage", 1), ("document_id", 1)])
        get_final_collection(departement).create_index(
            [("region", 1), ("mois", 1)], unique=True
        )
    get_region_final_collection().create_index(
        [("region", 1), ("mois", 1)], unique=True
    )