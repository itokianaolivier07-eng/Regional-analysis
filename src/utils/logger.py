"""Logger pour le pipeline département."""
import logging
import sys
from datetime import datetime
from config import settings


def get_logger(name: str = "departement_pipeline") -> logging.Logger:
    logger = logging.getLogger(name)

    # Ne configurer les handlers qu'une seule fois par logger
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Fichier
    try:
        settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
        fh = logging.FileHandler(
            settings.LOGS_DIR / f"run_{stamp}.log",
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass

    logger.propagate = False
    return logger
