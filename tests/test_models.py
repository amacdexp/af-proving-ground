"""Dataclass behaviour and JSON marshalling."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from ledger.models import ImportBatch, LineItem, Record, StoredRecord


def test_line_item_is_frozen():
    item = LineItem("paper", 500)
    with pytest.raises(FrozenInstanceError):
        item.amount_cents = 600


def test_line_item_round_trips_through_a_dict():
    item = LineItem("paper", 500)
    assert LineItem.from_dict(item.to_dict()) == item


def test_record_to_dict_uses_iso_dates_and_plain_lists(make_record):
    record = make_record()
    data = record.to_dict()
    assert data["issued_on"] == "2026-01-01"
    assert data["items"] == [{"description": "consulting", "amount_cents": 1250}]


def test_record_round_trips_through_a_dict(make_record):
    record = make_record()
    assert Record.from_dict(record.to_dict()) == record


def test_record_from_dict_needs_every_field():
    with pytest.raises(ValueError):
        Record.from_dict({"email": "billing@acme.example"})


def test_record_from_dict_rejects_a_bad_date():
    with pytest.raises(ValueError):
        Record.from_dict(
            {
                "supplier": "Acme Ltd",
                "email": "billing@acme.example",
                "amount_cents": 1250,
                "currency": "GBP",
                "issued_on": "01/01/2026",
            }
        )


def test_record_from_dict_rejects_non_list_items():
    with pytest.raises(ValueError):
        Record.from_dict(
            {
                "supplier": "Acme Ltd",
                "email": "billing@acme.example",
                "amount_cents": 1250,
                "currency": "GBP",
                "issued_on": "2026-01-01",
                "items": "consulting",
            }
        )


def test_record_with_items_returns_a_new_record(make_record):
    record = make_record(items=())
    extended = record.with_items(LineItem("travel", 250))
    assert record.items == ()
    assert extended.items == (LineItem("travel", 250),)
    assert extended.amount_cents == record.amount_cents


def test_import_batch_summarises_its_records(make_record):
    batch = ImportBatch.of(
        "Acme Ltd",
        [make_record(amount_cents=1000), make_record(amount_cents=250, currency="USD")],
    )
    assert batch.supplier == "Acme Ltd"
    assert batch.total_cents == 1250
    assert batch.currencies() == ("GBP", "USD")


def test_stored_record_merges_row_metadata(make_record):
    stored = StoredRecord(
        id=7,
        record=make_record(),
        status="open",
        created_at="2026-01-01T09:00:00+00:00",
    )
    data = stored.to_dict()
    assert data["id"] == 7
    assert data["status"] == "open"
    assert data["created_at"] == "2026-01-01T09:00:00+00:00"
    assert data["supplier"] == "Acme Ltd"


def test_record_summary_omits_the_items(make_record):
    summary = make_record(items=(LineItem("a", 250), LineItem("b", 1000))).summary()
    assert summary["item_count"] == 2
    assert "items" not in summary
    assert summary["issued_on"] == "2026-01-01"


def test_record_turns_a_list_of_items_into_a_tuple(make_record):
    record = make_record(items=[LineItem("consulting", 1250)])
    assert isinstance(record.items, tuple)
    assert record.items == (LineItem("consulting", 1250),)


def test_import_batch_round_trips_through_a_dict(make_record):
    batch = ImportBatch.of("Acme Ltd", [make_record(amount_cents=1000)])
    assert ImportBatch.from_dict(batch.to_dict()) == batch
    assert batch.total_by_currency() == {"GBP": 1000}
    assert len(batch) == 1
    assert not batch.is_empty


def test_stored_record_reports_its_status(make_record):
    stored = StoredRecord(
        id=1,
        record=make_record(),
        status="void",
        created_at="2026-01-01T09:00:00+00:00",
    )
    assert stored.is_void is True
    assert stored.is_open is False


def test_record_from_dict_rejects_a_non_object():
    with pytest.raises(ValueError):
        Record.from_dict(["not", "a", "record"])


def test_record_from_dict_rejects_a_bad_item():
    payload = {
        "supplier": "Acme Ltd",
        "email": "billing@acme.example",
        "amount_cents": 1250,
        "currency": "GBP",
        "issued_on": "2026-01-01",
        "items": [{"description": "consulting", "amount_cents": "1250"}],
    }
    with pytest.raises(ValueError):
        Record.from_dict(payload)


def test_line_item_from_dict_needs_both_fields():
    with pytest.raises(ValueError):
        LineItem.from_dict({"description": "consulting"})
    with pytest.raises(ValueError):
        LineItem.from_dict({"amount_cents": 500})


def test_an_empty_import_batch_is_empty():
    batch = ImportBatch(supplier="Acme Ltd")
    assert batch.is_empty
    assert len(batch) == 0
    assert batch.total_cents == 0
    assert batch.currencies() == ()
    assert batch.total_by_currency() == {}


def test_import_batch_from_dict_needs_a_supplier(make_record):
    with pytest.raises(ValueError):
        ImportBatch.from_dict({"records": [make_record().to_dict()]})


def test_stored_record_open_flag(make_record):
    stored = StoredRecord(
        id=1,
        record=make_record(),
        status="open",
        created_at="2026-01-01T09:00:00+00:00",
    )
    assert stored.is_open is True
    assert stored.is_void is False
