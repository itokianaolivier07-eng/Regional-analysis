import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_int(name: str, default: int) -> int:
    value = get_env(name, str(default))
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} doit être un entier, reçu: {value!r}") from exc


def get_float(name: str, default: float) -> float:
    value = get_env(name, str(default))
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} doit être un nombre, reçu: {value!r}") from exc


# MongoDB
MONGO_URI = get_env("MONGO_URI", "mongodb://127.0.0.1:27017/")
MONGO_DB_NAME = get_env("MONGO_DB_NAME", "region_france")

# Sources fixes (les deux départements)
MONGO_SOURCE_CORSE_A = get_env("MONGO_SOURCE_CORSE_A", "Haute-Corse")
MONGO_SOURCE_CORSE_B = get_env("MONGO_SOURCE_CORSE_B", "Corse-du-Sud")

# Collections de sortie — pipeline unique Corse + finale régionale
MONGO_PIPELINE_STAGES_C = get_env("MONGO_PIPELINE_STAGES_C", "pipeline_stage_C")
MONGO_REGION_SYNTHESIS = get_env("MONGO_REGION_SYNTHESIS", "region_synthesis")

# Domaines imposés pour le batching LLM
DOMAINES = [
    "Logement & Pouvoir d'Achat",
    "Securité & Propreté",
    "Environnement & Sécheresse",
    "Transports & Mobilité",
    "Pénurie Médicale & Santé",
]

# Mapping unique : un seul territoire « Corse » qui lit les deux sources
TERRITOIRES = {
    "Corse": {
        "source_collection": MONGO_SOURCE_CORSE_A,  # fallback
        "sources": [MONGO_SOURCE_CORSE_A, MONGO_SOURCE_CORSE_B],
        "key": "C",
    },
}
REGION_NAME = "Corse"

# Catégories réellement envoyées au LLM / traitées par Python.
# government_pub (communiqués) passent maintenant par le LLM.
CATEGORIES_LLM_DEPARTEMENT = {"social_media", "news", "government_pub"}
CATEGORIES_PYTHON_DEPARTEMENT = {"business_registry", "official_stats", "housing", "job_offers"}

# Pondération des sources (Faille n°2)
# Utilisée par compute_theme_dominant et exposée dans les objets L0.
# news et government_pub pèsent nettement plus que les templates social_media.
SOURCE_WEIGHTS = {
    "news": 10.0,
    "government_pub": 5.0,
    "social_media": 1.0,
    # catégories Python (au cas où on les compterait un jour)
    "official_stats": 8.0,
    "business_registry": 3.0,
    "housing": 3.0,
    "job_offers": 1.0,
}
DEFAULT_SOURCE_WEIGHT = 1.0

# Filtre mensuel
MOIS_CIBLE = get_env("MOIS_CIBLE", "")

def _collect_keys(*names: str) -> list:
    keys = []
    for name in names:
        val = get_env(name)
        if val:
            keys.append(val)
    return keys

OPENROUTER_API_KEYS = _collect_keys("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2")
OPENROUTER_MODEL = get_env("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
OPENROUTER_BASE_URL = get_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

GOOGLE_AI_API_KEYS = _collect_keys("GOOGLE_AI_API_KEY", "GOOGLE_AI_API_KEY_2")
GOOGLE_AI_MODEL = get_env("GOOGLE_AI_MODEL", "gemini-3.5-flash-lite")
GOOGLE_AI_BASE_URL = get_env("GOOGLE_AI_BASE_URL", "https://generativelanguage.googleapis.com")

LLM_PROVIDER = get_env("LLM_PROVIDER", "auto").lower()
LLM_PROVIDER_ORDER = [
    item.strip().lower()
    for item in get_env("LLM_PROVIDER_ORDER", "google,openrouter").split(",")
    if item.strip()
]


# Performance
BATCH_SIZE = get_int("BATCH_SIZE", 8)
PAUSE_SECONDES = get_float("PAUSE_SECONDES", 2)
MAX_WORKERS = get_int("MAX_WORKERS", 1)
MAX_DOCS_PER_RUN = get_int("MAX_DOCS_PER_RUN", 0)
MAX_LOTS_L3_PAR_DOMAINE = get_int("MAX_LOTS_L3_PAR_DOMAINE", 2)

RAW_TEXT_MAX_CHARS = get_int("RAW_TEXT_MAX_CHARS", 800)
RAW_TEXT_MAX_CHARS_BY_CATEGORY = {
    "news": get_int("RAW_TEXT_MAX_CHARS_NEWS", 1200),
    "government_pub": get_int("RAW_TEXT_MAX_CHARS_GOV", 1000),
    "social_media": get_int("RAW_TEXT_MAX_CHARS_SOCIAL", 400),
}
LLM_MAX_TOKENS_OUTPUT = get_int("LLM_MAX_TOKENS_OUTPUT", 4500)
LLM_TIMEOUT_SECONDES = get_int("LLM_TIMEOUT_SECONDES", 45)
LLM_MAX_RETRIES = get_int("LLM_MAX_RETRIES", 3)
LLM_REQUESTS_PER_MINUTE = get_int("LLM_REQUESTS_PER_MINUTE", 20)
LLM_TOKEN_BUDGET_DAILY = get_int("LLM_TOKEN_BUDGET_DAILY", 0)

LOGS_DIR = BASE_DIR / "logs"
CHECKPOINT_DIR = BASE_DIR / ".checkpoint"

VALID_LLM_PROVIDERS = {"google", "openrouter"}


def _check_ascii(name: str, value: str) -> None:
    """Ces valeurs finissent dans des headers HTTP (requests), qui
    n'acceptent que de l'ASCII. Un caractère accentué copié-collé par
    erreur (ex: dans une clé API) fait planter avec un traceback
    illisible (UnicodeEncodeError). On le détecte ici, tôt, avec un
    message clair."""
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"{name} contient un caractère non-ASCII à la position {exc.start} "
            f"({value[exc.start:exc.start+1]!r}). Vérifiez le .env pour un "
            f"caractère accentué ou une apostrophe typographique collée par erreur."
        ) from exc


def validate() -> None:
    for _name, _values in (("GOOGLE_AI_API_KEY", GOOGLE_AI_API_KEYS), ("OPENROUTER_API_KEY", OPENROUTER_API_KEYS)):
        for _i, _key in enumerate(_values):
            _check_ascii(f"{_name}[{_i}]", _key)
    _check_ascii("GOOGLE_AI_MODEL", GOOGLE_AI_MODEL)
    _check_ascii("OPENROUTER_MODEL", OPENROUTER_MODEL)

    if not MONGO_URI:
        raise RuntimeError("MONGO_URI est vide.")
    if not MONGO_DB_NAME:
        raise RuntimeError("MONGO_DB_NAME est vide.")
    if not MONGO_SOURCE_CORSE_A or not MONGO_SOURCE_CORSE_B:
        raise RuntimeError("Les deux collections source A et B sont obligatoires.")
    if not MONGO_PIPELINE_STAGES_C:
        raise RuntimeError("MONGO_PIPELINE_STAGES_C est obligatoire.")
    if not MONGO_REGION_SYNTHESIS:
        raise RuntimeError("MONGO_REGION_SYNTHESIS est obligatoire.")
    if not MOIS_CIBLE:
        raise RuntimeError("MOIS_CIBLE est obligatoire.")
    if len(MOIS_CIBLE) != 7 or MOIS_CIBLE[4] != "-":
        raise RuntimeError(f"MOIS_CIBLE doit être au format YYYY-MM, reçu: {MOIS_CIBLE!r}")
    if BATCH_SIZE <= 0:
        raise RuntimeError("BATCH_SIZE doit être > 0.")
    if PAUSE_SECONDES < 0:
        raise RuntimeError("PAUSE_SECONDES doit être >= 0.")
    if MAX_WORKERS <= 0:
        raise RuntimeError("MAX_WORKERS doit être > 0.")
    if MAX_DOCS_PER_RUN < 0:
        raise RuntimeError("MAX_DOCS_PER_RUN doit être >= 0.")
    if RAW_TEXT_MAX_CHARS < 0:
        raise RuntimeError("RAW_TEXT_MAX_CHARS doit être >= 0.")
    if LLM_MAX_TOKENS_OUTPUT <= 0:
        raise RuntimeError("LLM_MAX_TOKENS_OUTPUT doit être > 0.")
    if LLM_TIMEOUT_SECONDES <= 0:
        raise RuntimeError("LLM_TIMEOUT_SECONDES doit être > 0.")
    if LLM_MAX_RETRIES < 0:
        raise RuntimeError("LLM_MAX_RETRIES doit être >= 0.")
    if LLM_REQUESTS_PER_MINUTE <= 0:
        raise RuntimeError("LLM_REQUESTS_PER_MINUTE doit être > 0.")
    if LLM_TOKEN_BUDGET_DAILY < 0:
        raise RuntimeError("LLM_TOKEN_BUDGET_DAILY doit être >= 0.")

    if LLM_PROVIDER not in {"auto"} | VALID_LLM_PROVIDERS:
        raise RuntimeError(
            f"LLM_PROVIDER inconnu: {LLM_PROVIDER!r}. "
            f"Valeurs: auto, google, openrouter."
        )
    if not LLM_PROVIDER_ORDER:
        raise RuntimeError("LLM_PROVIDER_ORDER est vide.")
    unknown = [p for p in LLM_PROVIDER_ORDER if p not in VALID_LLM_PROVIDERS]
    if unknown:
        raise RuntimeError(f"Provider(s) inconnu(s): {unknown}")
    if LLM_PROVIDER != "auto" and LLM_PROVIDER not in LLM_PROVIDER_ORDER:
        raise RuntimeError(
            f"LLM_PROVIDER={LLM_PROVIDER!r} n'est pas présent dans LLM_PROVIDER_ORDER."
        )

    keys = {
        "google": bool(GOOGLE_AI_API_KEYS),
        "openrouter": bool(OPENROUTER_API_KEYS),
    }
    if LLM_PROVIDER != "auto" and not keys[LLM_PROVIDER]:
        raise RuntimeError(f"Clé API manquante pour {LLM_PROVIDER}.")
    if LLM_PROVIDER == "auto" and not any(keys[p] for p in LLM_PROVIDER_ORDER):
        raise RuntimeError(
            "Aucune clé API disponible. Renseignez GOOGLE_AI_API_KEY "
            "ou OPENROUTER_API_KEY."
        )
