"""Producer and consumer behaviour on the happy path."""

from __future__ import annotations

from ledger.models import LineItem
from ledger.queue import consumer, producer
from ledger.utils import decode


def test_enqueue_writes_one_row_per_distinct_record(store, make_record):
    assert producer.enqueue(store, [make_record(), make_record(email="b@acme.example")]) == 2
    assert store.pending_outbox() == 2


def test_enqueue_of_an_empty_batch_writes_nothing(store):
    assert producer.enqueue(store, []) == 0
    assert store.pending_outbox() == 0


def test_drain_persists_the_queued_records(store, make_record):
    producer.enqueue(store, [make_record(), make_record(email="b@acme.example")])
    assert consumer.drain(store, 10) == 2
    assert len(store.find_by_email("billing@acme.example")) == 1
    assert len(store.find_by_email("b@acme.example")) == 1


def test_drain_marks_rows_done(store, make_record):
    producer.enqueue(store, [make_record()])
    consumer.drain(store, 10)
    assert store.pending_outbox() == 0
    with store.connection() as conn:
        states = [row["state"] for row in conn.execute("SELECT state FROM outbox")]
    assert states == ["done"]


def test_drain_respects_its_limit(store, make_record):
    producer.enqueue(
        store,
        [
            make_record(email="a@acme.example"),
            make_record(email="b@acme.example"),
            make_record(email="c@acme.example"),
        ],
    )
    assert consumer.drain(store, 2) == 2
    assert store.pending_outbox() == 1
    assert store.count() == 2


def test_drain_on_an_empty_outbox_is_a_no_op(store):
    assert consumer.drain(store, 10) == 0
    assert store.count() == 0


def test_drain_restores_line_items(store, make_record):
    producer.enqueue(
        store,
        [make_record(items=(LineItem("consulting", 1000), LineItem("travel", 250)))],
    )
    consumer.drain(store, 10)
    stored = store.find_by_email("billing@acme.example")[0]
    assert stored.items == (LineItem("consulting", 1000), LineItem("travel", 250))


def test_the_outbox_payload_is_a_full_record(store, make_record):
    record = make_record(items=(LineItem("consulting", 1250),))
    producer.enqueue(store, [record])
    row = store.outbox_rows("pending")[0]
    assert decode(row.payload) == record
    assert row.attempts == 0
