#!/bin/bash
# Lance le pipeline pour le mois précédent (stage en argument, "all" par défaut)
cd "$(dirname "$0")" || exit 1

STAGE="${1:-all}"
MOIS="${2:-$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)}"

# Verrou : un seul run à la fois (le verrou se libère à la fin du script)
exec 9>/tmp/analysis_regional.lock
if ! flock -n 9; then
    echo "=== $(date '+%F %T') | un run est déjà en cours - abandon ==="
    exit 1
fi

echo "=== $(date '+%F %T') | stage ${STAGE} | mois ${MOIS} ==="
docker compose run --rm -T pipeline python main.py --stage "${STAGE}" --mois "${MOIS}"
