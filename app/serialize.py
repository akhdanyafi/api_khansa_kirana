from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def normalize_row(row: dict[str, Any], *, bool_fields: set[str] | None = None) -> dict[str, Any]:
    bool_fields = bool_fields or set()
    out: dict[str, Any] = {}

    for key, value in row.items():
        if key in bool_fields and value is not None:
            out[key] = bool(value)
            continue

        if isinstance(value, datetime):
            out[key] = _to_iso(value)
            continue

        if isinstance(value, Decimal):
            out[key] = float(value)
            continue

        out[key] = value

    return out


def normalize_rows(rows: list[dict[str, Any]], *, bool_fields: set[str] | None = None) -> list[dict[str, Any]]:
    return [normalize_row(r, bool_fields=bool_fields) for r in rows]
