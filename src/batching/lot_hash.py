"""Empreinte stable d'un lot : dépend du contenu, pas de la position."""
import hashlib


def prompt_version(*prompts: str) -> str:
    """Empreinte des prompts : si tu les modifies, les lots sont recalculés."""
    return hashlib.sha1("\n".join(prompts).encode("utf-8")).hexdigest()[:8]


def compute_lot_hash(documents: list, domaine: str, extra: str = "") -> str:
    parts = [domaine, extra]
    for d in sorted(documents, key=lambda x: str(x.get("document_id") or "")):
        texte = str(d.get("texte") or "")
        h = hashlib.sha1(texte.encode("utf-8")).hexdigest()[:12]
        parts.append(f"{d.get('document_id')}|{h}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]

def compute_synthese_hash(syntheses: list, domaine: str, extra: str = "") -> str:
    """Empreinte d'un lot de synthèses (L1 -> L2, L2 -> L3) : dépend de leur contenu."""
    parts = [domaine, extra]
    for d in sorted(syntheses, key=lambda x: str(x.get("lot_id") or "")):
        contenu = "|".join(
            str(d.get(k) or "")
            for k in ("problematique", "cause", "preuve", "consequence", "solution", "resume", "gravite")
        )
        h = hashlib.sha1(contenu.encode("utf-8")).hexdigest()[:12]
        parts.append(f"{d.get('lot_id')}|{h}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]

def assign_synthese_lot_ids(batches: list, stage: str, departement: str, mois: str, config: str) -> None:
    """Donne à chaque lot de synthèses (L2, L3) un nom calculé sur son contenu."""
    for batch in batches:
        h = compute_synthese_hash(batch["documents"], batch.get("domaine", ""), config)
        batch["lot_id"] = f"{stage}-{departement}-{mois}-{h}"