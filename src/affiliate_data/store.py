"""Writes scraped rows: insert new ones, refresh existing ones (by platform + site id)."""

import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Conversion, Product, TrendingVideo


def _jsonable(raw: Any) -> Any:
    """Raw site records go into JSONB; round-trip them so odd types (Decimal) cannot break the insert."""
    return json.loads(json.dumps(raw, default=str))


def _upsert(db: Session, model: Any, platform: str, rows: list[dict[str, Any]], key: list[str]) -> int:
    if not rows:
        return 0
    values = [{**row, "platform": platform, "raw": _jsonable(row.get("raw"))} for row in rows]
    columns = set().union(*(v.keys() for v in values))
    # Rows from different parsers carry different fields; fill the gaps so one statement fits all.
    values = [{c: v.get(c) for c in columns} for v in values]
    statement = insert(model).values(values)
    # Keep what we already know when a fresher row lacks a field (e.g. a search row has no commission).
    updates = {
        c: func.coalesce(statement.excluded[c], getattr(model, c)) for c in columns if c not in (*key, "platform")
    }
    updates["updated_at"] = func.now()
    db.execute(statement.on_conflict_do_update(index_elements=["platform", *key], set_=updates))
    db.commit()
    return len(values)


def save_products(db: Session, platform: str, rows: list[dict[str, Any]]) -> int:
    return _upsert(db, Product, platform, rows, ["external_id"])


def save_videos(db: Session, platform: str, rows: list[dict[str, Any]]) -> int:
    return _upsert(db, TrendingVideo, platform, rows, ["external_id"])


def save_conversions(db: Session, platform: str, rows: list[dict[str, Any]]) -> int:
    return _upsert(db, Conversion, platform, rows, ["order_id", "item_id"])
