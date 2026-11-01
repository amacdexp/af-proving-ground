"""JSON snapshot writer for the record table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ledger.config import load
from ledger.reports import projections
from ledger.store import Store
from ledger.utils import sum_cents, to_iso, write_json

DEFAULT_NAME = "export.json"


def snapshot(store: Store) -> dict[str, Any]:
    """The JSON document written by an export."""
    stored = store.records()
    return {
        "generated_at": to_iso(store.now()),
        "summary": {
            "record_count": len(stored),
            "total_cents": sum_cents(entry.record.amount_cents for entry in stored),
            "by_month": projections.monthly(store),
            "by_status": store.status_counts(),
            "by_currency": store.currency_counts(),
            "by_supplier": projections.supplier_totals(store),
            "aging": projections.aging(store),
        },
        "records": [entry.to_dict() for entry in stored],
    }


def export(store: Store, name: str = DEFAULT_NAME) -> Path:
    """Write every stored record to a JSON snapshot and return its path."""
    target = load().data_dir / name
    return write_json(target, snapshot(store))
