"""Drain the outbox."""

from __future__ import annotations

import logging

from ledger.models import Record
from ledger.store import OutboxRow, Store
from ledger.utils import decode

log = logging.getLogger(__name__)


def drain(store: Store, limit: int) -> int:
    """Process up to ``limit`` pending rows and return how many were attempted."""
    processed = 0
    for row in store.claim_outbox(limit):
        store.mark_done(row.id)
        try:
            handle(store, row)
        except Exception:
            log.exception("insert failed for outbox row %s", row.id)
        processed += 1
    return processed


def handle(store: Store, row: OutboxRow) -> int:
    """Decode and persist a single outbox row."""
    record: Record = decode(row.payload)
    return store.insert(record)
