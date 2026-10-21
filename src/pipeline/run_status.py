"""Statut d'un run à partir des résultats des stages."""
from typing import Any, Dict, List, Tuple


def compute_statut(stage_results: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Retourne (statut, problèmes) ; statut = 'complete' ou 'partial'."""
    problemes: List[str] = []
    for stage, res in sorted((stage_results or {}).items()):
        if not isinstance(res, dict):
            continue
        erreurs = res.get("erreurs", 0)
        if erreurs or res.get("error"):
            detail = res.get("error") or f"{erreurs} erreur(s)"
            problemes.append(f"stage {stage}: {detail}")
    return ("partial" if problemes else "complete"), problemes

def compute_statut_run(results: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Statut de l'ensemble du run (tous les territoires)."""
    problemes: List[str] = []
    for territoire, stage_results in ((results or {}).get("territoires") or {}).items():
        if not isinstance(stage_results, dict):
            continue
        _, p = compute_statut(stage_results)
        problemes += [f"{territoire} / {x}" for x in p]
    return ("partial" if problemes else "complete"), problemes

_RESUME_KEYS = ("lots_total", "succes", "skipped", "erreurs", "duree_secondes", "error")


def resume_stages(results: Dict[str, Any]) -> Dict[str, Any]:
    """Résumé compact des stages (sans les gros objets comme les indicateurs)."""
    out: Dict[str, Any] = {}
    for territoire, stage_results in ((results or {}).get("territoires") or {}).items():
        if not isinstance(stage_results, dict):
            continue
        for stage, res in stage_results.items():
            if isinstance(res, dict):
                out[f"{territoire}/{stage}"] = {k: res[k] for k in _RESUME_KEYS if k in res}
    return out