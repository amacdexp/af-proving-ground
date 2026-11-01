"""Put imports on the durable outbox."""

from __future__ import annotations

from ledger.models import Record
from ledger.store import Store
from ledger.utils import dedupe, encode, fingerprint


def enqueue(store: Store, records: list[Record]) -> int:
    """Write one outbox row per distinct record in the batch.

    Returns the number of rows written, which can be smaller than the number
    of records when a payload repeats the same invoice.
    """
    written = 0
    for record in dedupe(records, key=fingerprint):
        store.enqueue_row(encode(record))
        written += 1
    return written
