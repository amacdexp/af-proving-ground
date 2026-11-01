"""Totals projection maintenance and snapshot output."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ledger.config import load
from ledger.models import STATUS_OPEN, STATUS_PAID
from ledger.utils import month_key, read_json, to_iso, write_json

if TYPE_CHECKING:
    from ledger.store import Store

DEFAULT_NAME = "totals.json"
COUNTED_STATUSES = (STATUS_OPEN, STATUS_PAID)
AGING_BUCKETS = (30, 60, 90)


def apply(conn: sqlite3.Connection, change: dict[str, Any]) -> None:
    """Apply one change to the totals table."""
    kind = change.get("kind")
    if kind == "insert":
        _increase(conn, change["currency"], int(change["amount_cents"]), change["at"])
        return
    if kind in ("update", "delete"):
        return
    raise ValueError(f"unknown change kind: {kind!r}")


def _increase(conn: sqlite3.Connection, currency: str, amount_cents: int, at: str) -> None:
    row = conn.execute(
        "SELECT amount_cents FROM totals WHERE currency = ?", (currency,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO totals (currency, amount_cents, updated_at) VALUES (?, ?, ?)",
            (currency, amount_cents, at),
        )
    else:
        conn.execute(
            "UPDATE totals SET amount_cents = amount_cents + ?, updated_at = ? WHERE currency = ?",
            (amount_cents, at, currency),
        )


def totals(store: "Store") -> dict[str, int]:
    """Per-currency totals, read from the projection table."""
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT currency, amount_cents FROM totals ORDER BY currency"
        ).fetchall()
    return {row["currency"]: int(row["amount_cents"]) for row in rows}


def summary(store: "Store") -> dict[str, Any]:
    """Totals plus the record counts they were derived from."""
    data = totals(store)
    with store.connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM records").fetchone()
        suppliers = [
            entry["supplier"]
            for entry in conn.execute(
                "SELECT DISTINCT supplier FROM records ORDER BY supplier"
            )
        ]
    return {
        "record_count": int(row["total"]),
        "suppliers": suppliers,
        "currencies": sorted(data),
        "totals": data,
    }


def rebuild(store: "Store") -> dict[str, int]:
    """Recompute the projection from the record table."""
    at = to_iso(store.now())
    with store.connection() as conn:
        conn.execute("DELETE FROM totals")
        rows = conn.execute(
            "SELECT currency, SUM(amount_cents) AS total FROM records"
            " WHERE status IN (?, ?) GROUP BY currency ORDER BY currency",
            COUNTED_STATUSES,
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO totals (currency, amount_cents, updated_at) VALUES (?, ?, ?)",
                (row["currency"], int(row["total"]), at),
            )
    return totals(store)


def write_totals(store: "Store", name: str = DEFAULT_NAME) -> Path:
    """Write the current totals to a JSON snapshot and return its path."""
    target = load().data_dir / name
    payload = {"generated_at": to_iso(store.now()), "totals": totals(store)}
    return write_json(target, payload)


def read_totals(path: Path) -> dict[str, int]:
    """Read a totals snapshot back into a plain dict."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("totals snapshot must be a JSON object")
    totals_data = payload.get("totals", {})
    if not isinstance(totals_data, dict):
        raise ValueError("totals snapshot has no totals object")
    return {str(currency): int(cents) for currency, cents in totals_data.items()}


def monthly(store: "Store") -> dict[str, dict[str, int]]:
    """Per-month, per-currency totals for the records that count."""
    buckets: dict[str, dict[str, int]] = {}
    for stored in store.records():
        if stored.status not in COUNTED_STATUSES:
            continue
        record = stored.record
        month = buckets.setdefault(month_key(record.issued_on), {})
        month[record.currency] = month.get(record.currency, 0) + record.amount_cents
    return dict(sorted(buckets.items()))


def totals_by_status(store: "Store") -> dict[str, dict[str, int]]:
    """Per-status, per-currency totals straight from the record table."""
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT status, currency, SUM(amount_cents) AS total FROM records"
            " GROUP BY status, currency ORDER BY status, currency"
        ).fetchall()
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        grouped.setdefault(row["status"], {})[row["currency"]] = int(row["total"])
    return grouped


def outstanding(store: "Store") -> dict[str, int]:
    """Per-currency totals for records still open."""
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT currency, SUM(amount_cents) AS total FROM records"
            " WHERE status = ? GROUP BY currency ORDER BY currency",
            (STATUS_OPEN,),
        ).fetchall()
    return {row["currency"]: int(row["total"]) for row in rows}


def supplier_totals(store: "Store") -> dict[str, dict[str, int]]:
    """Per-supplier, per-currency totals for the records that count."""
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT supplier, currency, SUM(amount_cents) AS total FROM records"
            " WHERE status IN (?, ?) GROUP BY supplier, currency"
            " ORDER BY supplier, currency",
            COUNTED_STATUSES,
        ).fetchall()
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        grouped.setdefault(row["supplier"], {})[row["currency"]] = int(row["total"])
    return grouped


def _aging_labels(buckets: tuple[int, ...]) -> list[str]:
    labels: list[str] = []
    lower = 0
    for upper in buckets:
        labels.append(f"{lower}-{upper} days")
        lower = upper + 1
    labels.append(f"{lower}+ days")
    return labels


def aging(
    store: "Store", buckets: tuple[int, ...] = AGING_BUCKETS
) -> dict[str, dict[str, int]]:
    """Per-bucket, per-currency totals for records still open.

    Buckets are day counts measured from the store clock; the labels run from
    ``0-<first>`` up to ``<last+1>+``. Empty buckets are left out.
    """
    if not buckets or any(bucket <= 0 for bucket in buckets):
        raise ValueError("buckets must be positive day counts")

    ordered = tuple(sorted(buckets))
    labels = _aging_labels(ordered)
    as_of = store.now().date()
    grouped: dict[str, dict[str, int]] = {}
    for stored in store.search(status=STATUS_OPEN):
        age = max(0, (as_of - stored.record.issued_on).days)
        label = labels[-1]
        for index, limit in enumerate(ordered):
            if age <= limit:
                label = labels[index]
                break
        bucket = grouped.setdefault(label, {})
        currency = stored.record.currency
        bucket[currency] = bucket.get(currency, 0) + stored.record.amount_cents
    return {label: grouped[label] for label in labels if label in grouped}
