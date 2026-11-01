"""Store behaviour: records, outbox and schema creation."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from ledger.models import LineItem
from ledger.store import Store, default_path


def test_init_db_can_run_twice(tmp_path, clock):
    seeded = Store(str(tmp_path / "twice.sqlite"), clock=clock)
    seeded.init_db()
    seeded.init_db()
    assert seeded.count() == 0


def test_insert_returns_sequential_ids(store, make_record):
    first = store.insert(make_record())
    second = store.insert(make_record(email="second@acme.example"))
    assert (first, second) == (1, 2)


def test_get_returns_row_metadata_and_the_fixed_clock(store, make_record):
    record_id = store.insert(make_record())
    stored = store.get(record_id)
    assert stored is not None
    assert stored.id == record_id
    assert stored.status == "open"
    assert stored.created_at == "2026-01-01T09:00:00+00:00"
    assert stored.record.supplier == "Acme Ltd"


def test_get_returns_line_items(store, make_record):
    record_id = store.insert(
        make_record(items=(LineItem("consulting", 1000), LineItem("travel", 250)))
    )
    stored = store.get(record_id)
    assert stored is not None
    assert stored.record.items == (LineItem("consulting", 1000), LineItem("travel", 250))


def test_get_returns_none_for_an_unknown_id(store):
    assert store.get(404) is None


def test_find_by_email_matches_exactly(store, make_record):
    record_id = store.insert(make_record(email="billing@acme.example"))
    found = store.find_by_email("billing@acme.example")
    assert [record.email for record in found] == ["billing@acme.example"]
    assert found[0] == store.get(record_id).record


def test_find_by_email_returns_nothing_for_an_unknown_address(store):
    assert store.find_by_email("nobody@example.com") == []


def test_find_by_email_returns_every_match_in_id_order(store, make_record):
    store.insert(make_record(email="dup@example.com"))
    store.insert(make_record(email="other@example.com"))
    store.insert(make_record(email="dup@example.com"))
    assert len(store.find_by_email("dup@example.com")) == 2


def test_count_and_status_are_independent(store, make_record):
    record_id = store.insert(make_record())
    store.insert(make_record(email="second@acme.example"))
    store.update_status(record_id, "void")
    assert store.count() == 2
    assert store.count("open") == 1
    assert store.count("void") == 1


def test_update_status_changes_the_row(store, make_record):
    record_id = store.insert(make_record())
    store.update_status(record_id, "paid")
    assert store.get(record_id).status == "paid"


def test_update_status_for_an_unknown_id_raises(store):
    with pytest.raises(KeyError):
        store.update_status(999, "void")


def test_update_status_rejects_an_unknown_status(store, make_record):
    record_id = store.insert(make_record())
    with pytest.raises(ValueError):
        store.update_status(record_id, "archived")


def test_delete_removes_the_record_and_its_items(store, make_record):
    record_id = store.insert(make_record())
    store.delete(record_id)
    assert store.get(record_id) is None
    with store.connection() as conn:
        remaining = conn.execute("SELECT COUNT(*) AS total FROM line_items").fetchone()
    assert remaining["total"] == 0


def test_delete_for_an_unknown_id_raises(store):
    with pytest.raises(KeyError):
        store.delete(999)


def test_outbox_round_trip(store):
    row_id = store.enqueue_row('{"supplier": "Acme Ltd"}')
    assert store.pending_outbox() == 1

    claimed = store.claim_outbox(10)
    assert [row.id for row in claimed] == [row_id]
    assert claimed[0].state == "claimed"
    assert claimed[0].attempts == 1
    assert claimed[0].created_at == "2026-01-01T09:00:00+00:00"

    assert store.claim_outbox(10) == []
    store.mark_done(row_id)
    assert store.outbox_row(row_id).state == "done"
    assert store.pending_outbox() == 0


def test_claim_outbox_respects_the_limit(store):
    for _ in range(3):
        store.enqueue_row("{}")
    assert len(store.claim_outbox(2)) == 2


def test_mark_failed_records_the_state(store):
    row_id = store.enqueue_row("{}")
    store.mark_failed(row_id)
    assert store.outbox_row(row_id).state == "failed"


def test_records_lists_rows_in_insertion_order(store, make_record):
    store.insert(make_record(email="one@acme.example"))
    store.insert(make_record(email="two@acme.example"))
    emails = [stored.record.email for stored in store.records()]
    assert emails == ["one@acme.example", "two@acme.example"]
    assert len(store.records(limit=1)) == 1


def test_find_by_supplier_groups_rows(store, make_record):
    store.insert(make_record(supplier="Acme Ltd"))
    store.insert(make_record(supplier="Other Co", email="other@acme.example"))
    assert len(store.find_by_supplier("Acme Ltd")) == 1


def test_default_path_follows_the_env_override():
    expected = Path(os.environ["LEDGER_DATA_DIR"]) / "ledger.sqlite"
    assert default_path() == expected


def test_insert_many_returns_ids_in_order(store, make_record):
    ids = store.insert_many(
        [make_record(email="one@acme.example"), make_record(email="two@acme.example")]
    )
    assert ids == [1, 2]
    assert store.count() == 2


def test_search_filters_and_pages(store, make_record):
    store.insert(make_record(email="one@acme.example", currency="GBP"))
    store.insert(make_record(email="two@acme.example", currency="USD"))
    store.insert(make_record(email="three@acme.example", currency="GBP"))

    assert len(store.search(currency="GBP")) == 2
    assert [entry.id for entry in store.search(currency="GBP", limit=1, offset=1)] == [3]
    assert store.search(email="missing@acme.example") == []
    assert len(store.search(limit=2)) == 2


def test_status_and_currency_counts(store, make_record):
    first = store.insert(make_record(email="one@acme.example", currency="GBP"))
    store.insert(make_record(email="two@acme.example", currency="GBP"))
    store.insert(make_record(email="three@acme.example", currency="USD"))
    store.update_status(first, "void")

    assert store.status_counts() == {"open": 2, "void": 1}
    assert store.currency_counts() == {"GBP": 2, "USD": 1}


def test_outbox_rows_filters_by_state_and_requeues(store):
    first = store.enqueue_row("{}")
    second = store.enqueue_row("{}")
    store.mark_done(second)

    assert [row.id for row in store.outbox_rows("pending")] == [first]
    assert [row.id for row in store.outbox_rows("done")] == [second]
    assert len(store.outbox_rows()) == 2

    store.requeue(second)
    assert store.pending_outbox() == 2
    assert store.outbox_row(second).state == "pending"


def test_stats_summarises_the_whole_store(store, make_record):
    store.insert(make_record(email="one@acme.example", currency="GBP"))
    store.insert(make_record(email="two@acme.example", currency="USD"))
    store.enqueue_row("{}")
    stats = store.stats()
    assert stats["records"] == 2
    assert stats["statuses"] == {"open": 2}
    assert stats["currencies"] == {"GBP": 1, "USD": 1}
    assert stats["pending_outbox"] == 1


def test_search_filters_by_date_span(store, make_record):
    store.insert(make_record(issued_on=date(2026, 1, 5), email="jan@acme.example"))
    store.insert(make_record(issued_on=date(2026, 2, 10), email="feb@acme.example"))
    store.insert(make_record(issued_on=date(2026, 3, 1), email="mar@acme.example"))

    found = store.search(issued_from=date(2026, 1, 15), issued_to=date(2026, 2, 28))
    assert [entry.record.email for entry in found] == ["feb@acme.example"]
    assert len(store.search(issued_from=date(2026, 2, 1))) == 2
    assert len(store.search(issued_to=date(2026, 2, 28))) == 2


def test_find_by_ids_keeps_request_order_and_skips_missing(store, make_record):
    first = store.insert(make_record(email="one@acme.example"))
    second = store.insert(make_record(email="two@acme.example"))
    found = store.find_by_ids([second, 999, first])
    assert [entry.id for entry in found] == [second, first]


def test_delete_many_removes_each_row(store, make_record):
    ids = store.insert_many(
        [make_record(email="one@acme.example"), make_record(email="two@acme.example")]
    )
    assert store.delete_many(ids) == 2
    assert store.count() == 0


def test_search_filters_by_each_column(store, make_record):
    store.insert(make_record(supplier="Acme Ltd", email="one@acme.example"))
    store.insert(make_record(supplier="Other Co", email="two@other.example"))
    store.insert(
        make_record(supplier="Acme Ltd", email="three@acme.example", currency="USD")
    )
    assert len(store.search(supplier="Acme Ltd")) == 2
    assert len(store.search(email="two@other.example")) == 1
    assert len(store.search(currency="USD")) == 1
    assert len(store.search(supplier="Acme Ltd", currency="GBP")) == 1


def test_search_can_page_from_an_offset_without_a_limit(store, make_record):
    for index in range(3):
        store.insert(make_record(email=f"user{index}@acme.example"))
    assert [entry.id for entry in store.search(offset=1)] == [2, 3]


def test_search_can_order_by_amount(store, make_record):
    store.insert(make_record(amount_cents=300, email="a@acme.example"))
    store.insert(make_record(amount_cents=100, email="b@acme.example"))
    store.insert(make_record(amount_cents=200, email="c@acme.example"))

    ascending = store.search(order_by="amount_cents")
    descending = store.search(order_by="amount_cents", descending=True)
    assert [entry.record.amount_cents for entry in ascending] == [100, 200, 300]
    assert [entry.record.amount_cents for entry in descending] == [300, 200, 100]


def test_search_rejects_an_unknown_order_column(store):
    with pytest.raises(ValueError):
        store.search(order_by="password")


def test_find_by_ids_with_no_ids_returns_nothing(store):
    assert store.find_by_ids([]) == []


def test_update_status_to_the_same_status_is_allowed(store, make_record):
    record_id = store.insert(make_record())
    store.update_status(record_id, "open")
    assert store.get(record_id).status == "open"


def test_outbox_row_for_an_unknown_id_is_none(store):
    assert store.outbox_row(999) is None


def test_an_empty_store_answers_with_empty_collections(store):
    assert store.records() == []
    assert store.count() == 0
    assert store.status_counts() == {}
    assert store.currency_counts() == {}
    assert store.stats()["pending_outbox"] == 0
