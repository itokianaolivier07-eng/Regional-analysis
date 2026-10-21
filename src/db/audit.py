"""Champs d'audit des documents écrits en base."""
from datetime import datetime, timezone
from typing import Optional

_RESERVED = ("_id", "created_at", "version")


def build_upsert(doc: dict, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    fields = {k: v for k, v in doc.items() if k not in _RESERVED}
    fields["updated_at"] = now
    fields["date_execution"] = now
    return {
        "$set": fields,
        "$setOnInsert": {"created_at": now},
        "$inc": {"version": 1},
    }