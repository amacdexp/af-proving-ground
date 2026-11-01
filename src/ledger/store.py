"""SQLite access: records, line items, the outbox and the totals projection."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from ledger import config
from ledger.models import (
    STATUSES,
    STATUS_OPEN,
    LineItem,
    Record,
    StoredRecord,
)
from ledger.reports import projections
from ledger.utils import PATH_CHUNK, chunked, to_iso, utcnow

DB_FILENAME = "ledger.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    supplier TEXT NOT NULL,
    email TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    issued_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS line_items (
    id INTEGER PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS totals (
    currency TEXT PRIMARY KEY,
    amount_cents INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

FILTER_COLUMNS = ("supplier", "email", "status", "currency")
ORDER_COLUMNS = ("id", "issued_on", "amount_cents", "supplier")


def default_path() -> Path:
    """The sqlite file used when no explicit path is given."""
    return config.data_dir() / DB_FILENAME


@dataclass(frozen=True)
class OutboxRow:
    id: int
    payload: str
    state: str
    attempts: int
    created_at: str


class Store:
    """Thin sqlite wrapper. One connection per operation, opened and closed."""

    def __init__(self, path: str | Path, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self._clock = clock or utcnow

    def now(self) -> datetime:
        return self._clock()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @classmethod
    def open_default(cls) -> "Store":
        store = cls(default_path())
        store.init_db()
        return store

    # -- records ---------------------------------------------------------

    def insert(self, rec: Record) -> int:
        created = to_iso(self.now())
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO records"
                " (supplier, email, amount_cents, currency, issued_on, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.supplier,
                    rec.email,
                    rec.amount_cents,
                    rec.currency,
                    rec.issued_on.isoformat(),
                    STATUS_OPEN,
                    created,
                ),
            )
            record_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO line_items (record_id, description, amount_cents) VALUES (?, ?, ?)",
                [(record_id, item.description, item.amount_cents) for item in rec.items],
            )
            projections.apply(
                conn,
                {
                    "kind": "insert",
                    "record_id": record_id,
                    "currency": rec.currency,
                    "amount_cents": rec.amount_cents,
                    "status": STATUS_OPEN,
                    "at": created,
                },
            )
        return record_id

    def insert_many(self, records: Sequence[Record]) -> list[int]:
        """Insert several records; returns their ids in order."""
        return [self.insert(record) for record in records]

    def get(self, record_id: int) -> StoredRecord | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                return None
            return self._stored_from_row(row, self._items(conn, record_id))

    def find_by_email(self, email: str) -> list[Record]:
        with self.connection() as conn:
            ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM records WHERE email = ? ORDER BY id", (email,)
                )
            ]
            return [stored.record for stored in self._load_many(conn, ids)]

    def find_by_supplier(self, supplier: str) -> list[StoredRecord]:
        return self.search(supplier=supplier)

    def find_by_ids(self, record_ids: Sequence[int]) -> list[StoredRecord]:
        """Load the given ids, skipping any that do not exist."""
        with self.connection() as conn:
            return self._load_many(conn, list(record_ids))

    def records(self, limit: int | None = None) -> list[StoredRecord]:
        return self.search(limit=limit)

    def search(
        self,
        *,
        supplier: str | None = None,
        email: str | None = None,
        status: str | None = None,
        currency: str | None = None,
        issued_from: date | None = None,
        issued_to: date | None = None,
        limit: int | None = None,
        offset: int = 0,
        order_by: str = "id",
        descending: bool = False,
    ) -> list[StoredRecord]:
        """Filter records by exact field values and an optional date span.

        ``order_by`` is one of the columns in ``ORDER_COLUMNS``; ties fall back
        to ``id`` so paging is stable.
        """
        if order_by not in ORDER_COLUMNS:
            raise ValueError(f"cannot order by: {order_by!r}")
        filters = {
            "supplier": supplier,
            "email": email,
            "status": status,
            "currency": currency,
        }
        clauses: list[str] = []
        params: list[Any] = []
        for column in FILTER_COLUMNS:
            value = filters[column]
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if issued_from is not None:
            clauses.append("issued_on >= ?")
            params.append(issued_from.isoformat())
        if issued_to is not None:
            clauses.append("issued_on <= ?")
            params.append(issued_to.isoformat())

        sql = "SELECT id FROM records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        direction = "DESC" if descending else "ASC"
        if order_by == "id":
            sql += f" ORDER BY id {direction}"
        else:
            sql += f" ORDER BY {order_by} {direction}, id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        elif offset:
            sql += " LIMIT -1"
        if offset:
            sql += " OFFSET ?"
            params.append(offset)

        with self.connection() as conn:
            ids = [int(row["id"]) for row in conn.execute(sql, params)]
            return self._load_many(conn, ids)

    def count(self, status: str | None = None) -> int:
        with self.connection() as conn:
            if status is None:
                row = conn.execute("SELECT COUNT(*) AS total FROM records").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS total FROM records WHERE status = ?", (status,)
                ).fetchone()
            return int(row["total"])

    def status_counts(self) -> dict[str, int]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS total FROM records GROUP BY status ORDER BY status"
            ).fetchall()
        return {row["status"]: int(row["total"]) for row in rows}

    def currency_counts(self) -> dict[str, int]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT currency, COUNT(*) AS total FROM records GROUP BY currency ORDER BY currency"
            ).fetchall()
        return {row["currency"]: int(row["total"]) for row in rows}

    def stats(self) -> dict[str, Any]:
        """Counts used by the export summary."""
        return {
            "records": self.count(),
            "statuses": self.status_counts(),
            "currencies": self.currency_counts(),
            "pending_outbox": self.pending_outbox(),
        }

    def update_status(self, record_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status!r}")
        changed = to_iso(self.now())
        with self.connection() as conn:
            row = conn.execute(
                "SELECT status, currency, amount_cents FROM records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            previous = row["status"]
            conn.execute("UPDATE records SET status = ? WHERE id = ?", (status, record_id))
            projections.apply(
                conn,
                {
                    "kind": "update",
                    "record_id": record_id,
                    "currency": row["currency"],
                    "amount_cents": int(row["amount_cents"]),
                    "old_status": previous,
                    "new_status": status,
                    "at": changed,
                },
            )

    def delete(self, record_id: int) -> None:
        removed = to_iso(self.now())
        with self.connection() as conn:
            row = conn.execute(
                "SELECT currency, amount_cents, status FROM records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
            projections.apply(
                conn,
                {
                    "kind": "delete",
                    "record_id": record_id,
                    "currency": row["currency"],
                    "amount_cents": int(row["amount_cents"]),
                    "status": row["status"],
                    "at": removed,
                },
            )

    def delete_many(self, record_ids: Sequence[int]) -> int:
        """Delete several records; returns how many were removed."""
        removed = 0
        for record_id in record_ids:
            self.delete(record_id)
            removed += 1
        return removed

    # -- outbox ----------------------------------------------------------

    def enqueue_row(self, payload: str) -> int:
        created = to_iso(self.now())
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO outbox (payload, state, attempts, created_at)"
                " VALUES (?, 'pending', 0, ?)",
                (payload, created),
            )
            return int(cursor.lastrowid)

    def claim_outbox(self, limit: int) -> list[OutboxRow]:
        with self.connection() as conn:
            ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM outbox WHERE state = 'pending' ORDER BY id LIMIT ?", (limit,)
                )
            ]
            claimed: list[OutboxRow] = []
            for row_id in ids:
                conn.execute(
                    "UPDATE outbox SET state = 'claimed', attempts = attempts + 1 WHERE id = ?",
                    (row_id,),
                )
                row = conn.execute("SELECT * FROM outbox WHERE id = ?", (row_id,)).fetchone()
                claimed.append(_outbox_row(row))
            return claimed

    def mark_done(self, row_id: int) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE outbox SET state = 'done' WHERE id = ?", (row_id,))

    def mark_failed(self, row_id: int) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE outbox SET state = 'failed' WHERE id = ?", (row_id,))

    def requeue(self, row_id: int) -> None:
        """Put a row back in the pending queue."""
        with self.connection() as conn:
            conn.execute("UPDATE outbox SET state = 'pending' WHERE id = ?", (row_id,))

    def outbox_row(self, row_id: int) -> OutboxRow | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM outbox WHERE id = ?", (row_id,)).fetchone()
            return None if row is None else _outbox_row(row)

    def outbox_rows(self, state: str | None = None) -> list[OutboxRow]:
        sql = "SELECT * FROM outbox"
        params: tuple[str, ...] = ()
        if state is not None:
            sql += " WHERE state = ?"
            params = (state,)
        sql += " ORDER BY id"
        with self.connection() as conn:
            return [_outbox_row(row) for row in conn.execute(sql, params)]

    def pending_outbox(self) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM outbox WHERE state = 'pending'"
            ).fetchone()
            return int(row["total"])

    # -- internals -------------------------------------------------------

    def _items(self, conn: sqlite3.Connection, record_id: int) -> tuple[LineItem, ...]:
        rows = conn.execute(
            "SELECT description, amount_cents FROM line_items WHERE record_id = ? ORDER BY id",
            (record_id,),
        )
        return tuple(
            LineItem(description=row["description"], amount_cents=int(row["amount_cents"]))
            for row in rows
        )

    def _load_many(
        self, conn: sqlite3.Connection, ids: Sequence[int]
    ) -> list[StoredRecord]:
        wanted = list(dict.fromkeys(ids))
        if not wanted:
            return []

        found: dict[int, StoredRecord] = {}
        for chunk in chunked(wanted, PATH_CHUNK):
            placeholders = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT * FROM records WHERE id IN ({placeholders})", tuple(chunk)
            ).fetchall()
            by_id = {int(row["id"]): row for row in rows}

            items: dict[int, list[LineItem]] = {record_id: [] for record_id in chunk}
            for row in conn.execute(
                f"SELECT record_id, description, amount_cents FROM line_items"
                f" WHERE record_id IN ({placeholders}) ORDER BY id",
                tuple(chunk),
            ):
                items[int(row["record_id"])].append(
                    LineItem(
                        description=row["description"],
                        amount_cents=int(row["amount_cents"]),
                    )
                )

            for record_id in chunk:
                row = by_id.get(record_id)
                if row is not None:
                    found[record_id] = self._stored_from_row(row, tuple(items[record_id]))

        return [found[record_id] for record_id in wanted if record_id in found]

    def _stored_from_row(
        self, row: sqlite3.Row, items: tuple[LineItem, ...]
    ) -> StoredRecord:
        record = Record(
            supplier=row["supplier"],
            email=row["email"],
            amount_cents=int(row["amount_cents"]),
            currency=row["currency"],
            issued_on=date.fromisoformat(row["issued_on"]),
            items=items,
        )
        return StoredRecord(
            id=int(row["id"]),
            record=record,
            status=row["status"],
            created_at=row["created_at"],
        )


def _outbox_row(row: sqlite3.Row) -> OutboxRow:
    return OutboxRow(
        id=int(row["id"]),
        payload=row["payload"],
        state=row["state"],
        attempts=int(row["attempts"]),
        created_at=row["created_at"],
    )
