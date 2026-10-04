"""
Point d'entrée — Pipeline d'analyse territoriale unique Corse

Les sources Haute-Corse et Corse-du-Sud sont fusionnées en un seul pipeline.
La synthèse finale est écrite dans la collection region_synthesis.

Utilisation :
    python main.py --stage all
    python main.py --stage all --mois 2026-08
    python main.py --stage all --departement "Corse"
    python main.py --stage 0 --mois 2026-08
    python main.py --stage all --force-update
"""
import argparse
import sys
from config import settings
from src.pipeline.orchestrator import run_pipeline
from src.utils.logger import get_logger


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pipeline d'analyse territoriale — Corse (pipeline unique)"
    )
    parser.add_argument(
        "--stage",
        type=str,
        default="all",
        choices=["0", "1", "2", "3", "4", "region", "all"],
        help="Étage à exécuter (0=normalisation … 4=finale régionale, all)",
    )
    parser.add_argument(
        "--mois",
        type=str,
        default=None,
        help="Mois cible (ex: 2026-08). Sinon utilise MOIS_CIBLE du .env",
    )
    parser.add_argument(
        "--departement",
        type=str,
        default=None,
        help='Territoire (ex: "Corse"). Les anciens noms Haute-Corse / Corse-du-Sud '
             "sont redirigés vers le pipeline unique Corse.",
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force le retraitement de tous les documents",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger = get_logger()

    if args.force_update:
        logger.warning("MODE FORCE-UPDATE ACTIVÉ")

    try:
        settings.validate()
        run_pipeline(
            stage=args.stage,
            force_update=args.force_update,
            mois=args.mois,
            departement=args.departement,
        )
    except KeyboardInterrupt:
        logger.warning("Arrêt manuel (Ctrl+C)")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Erreur non gérée : {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
