"""Totals projection and snapshot output."""

from __future__ import annotations

import json
from datetime import date

import pytest

from ledger.config import load
from ledger.queue import consumer, producer
from ledger.reports import projections
from ledger.sync import exporter


def test_totals_start_empty(store):
    assert projections.totals(store) == {}


def test_totals_accumulate_per_currency(store, make_record):
    store.insert(make_record(amount_cents=1250))
    store.insert(make_record(amount_cents=750))
    store.insert(make_record(amount_cents=900, currency="USD", email="us@acme.example"))
    assert projections.totals(store) == {"GBP": 2000, "USD": 900}


def test_totals_count_a_record_once_regardless_of_items(store, make_record):
    store.insert(make_record(amount_cents=1250, items=()))
    assert projections.totals(store) == {"GBP": 1250}


def test_totals_follow_the_consumer(store, make_record):
    producer.enqueue(store, [make_record(amount_cents=500)])
    consumer.drain(store, 10)
    assert projections.totals(store) == {"GBP": 500}


def test_write_totals_creates_the_snapshot(store, make_record):
    store.insert(make_record(amount_cents=1250))
    path = projections.write_totals(store)
    assert path == load().data_dir / "totals.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "generated_at": "2026-01-01T09:00:00+00:00",
        "totals": {"GBP": 1250},
    }


def test_write_totals_accepts_an_alternate_name(store):
    path = projections.write_totals(store, name="daily.json")
    assert path.name == "daily.json"
    assert path.parent == load().data_dir
    assert json.loads(path.read_text(encoding="utf-8"))["totals"] == {}


def test_read_totals_round_trips_a_snapshot(store, make_record):
    store.insert(make_record(amount_cents=1250))
    path = projections.write_totals(store)
    assert projections.read_totals(path) == {"GBP": 1250}


def test_summary_reports_counts_and_currencies(store, make_record):
    store.insert(make_record(amount_cents=1250))
    store.insert(make_record(amount_cents=900, currency="USD", email="us@acme.example"))
    assert projections.summary(store) == {
        "record_count": 2,
        "suppliers": ["Acme Ltd"],
        "currencies": ["GBP", "USD"],
        "totals": {"GBP": 1250, "USD": 900},
    }


def test_rebuild_recomputes_the_projection_from_records(store, make_record):
    record_id = store.insert(make_record(amount_cents=1250))
    store.insert(make_record(amount_cents=900, currency="USD", email="us@acme.example"))
    store.update_status(record_id, "void")

    rebuilt = projections.rebuild(store)
    assert rebuilt == {"USD": 900}
    assert projections.totals(store) == {"USD": 900}


def test_monthly_groups_by_issue_month(store, make_record):
    store.insert(
        make_record(amount_cents=1000, issued_on=date(2026, 1, 5), email="a@acme.example")
    )
    store.insert(
        make_record(amount_cents=500, issued_on=date(2026, 1, 20), email="b@acme.example")
    )
    store.insert(
        make_record(
            amount_cents=900,
            currency="USD",
            issued_on=date(2026, 2, 1),
            email="c@acme.example",
        )
    )
    assert projections.monthly(store) == {
        "2026-01": {"GBP": 1500},
        "2026-02": {"USD": 900},
    }


def test_monthly_ignores_voided_records(store, make_record):
    record_id = store.insert(make_record(amount_cents=1000, issued_on=date(2026, 1, 5)))
    store.update_status(record_id, "void")
    assert projections.monthly(store) == {}


def test_totals_by_status_and_outstanding(store, make_record):
    voided = store.insert(make_record(amount_cents=1000, email="a@acme.example"))
    store.insert(make_record(amount_cents=500, email="b@acme.example"))
    store.insert(make_record(amount_cents=700, email="c@acme.example"))
    store.update_status(voided, "void")

    assert projections.totals_by_status(store) == {
        "open": {"GBP": 1200},
        "void": {"GBP": 1000},
    }
    assert projections.outstanding(store) == {"GBP": 1200}


def test_export_snapshot_summarises_records(store, make_record):
    store.insert(make_record(amount_cents=1250, issued_on=date(2026, 1, 5)))
    snapshot = exporter.snapshot(store)
    assert snapshot["generated_at"] == "2026-01-01T09:00:00+00:00"
    assert snapshot["summary"] == {
        "record_count": 1,
        "total_cents": 1250,
        "by_month": {"2026-01": {"GBP": 1250}},
        "by_status": {"open": 1},
        "by_currency": {"GBP": 1},
        "by_supplier": {"Acme Ltd": {"GBP": 1250}},
        "aging": {"0-30 days": {"GBP": 1250}},
    }
    assert snapshot["records"][0]["email"] == "billing@acme.example"
    assert snapshot["records"][0]["status"] == "open"


def test_supplier_totals_group_by_supplier_and_currency(store, make_record):
    store.insert(make_record(amount_cents=1000, supplier="Acme Ltd"))
    store.insert(
        make_record(
            amount_cents=400,
            supplier="Other Co",
            email="other@acme.example",
        )
    )
    store.insert(
        make_record(
            amount_cents=500,
            supplier="Acme Ltd",
            currency="USD",
            email="us@acme.example",
        )
    )
    assert projections.supplier_totals(store) == {
        "Acme Ltd": {"GBP": 1000, "USD": 500},
        "Other Co": {"GBP": 400},
    }


def test_supplier_totals_skip_voided_records(store, make_record):
    record_id = store.insert(make_record(amount_cents=1000, supplier="Acme Ltd"))
    store.update_status(record_id, "void")
    assert projections.supplier_totals(store) == {}


def test_aging_buckets_open_records_by_age(store, make_record):
    store.insert(make_record(amount_cents=1000, issued_on=date(2025, 12, 20),
                             email="a@acme.example"))  # 12 days old
    store.insert(make_record(amount_cents=500, issued_on=date(2025, 12, 2),
                             email="b@acme.example"))  # 30 days old
    store.insert(make_record(amount_cents=700, issued_on=date(2025, 12, 1),
                             email="c@acme.example"))  # 31 days old
    store.insert(make_record(amount_cents=300, issued_on=date(2025, 11, 1),
                             email="d@acme.example"))  # 61 days old
    store.insert(make_record(amount_cents=900, issued_on=date(2025, 9, 1),
                             email="e@acme.example"))  # 122 days old

    assert projections.aging(store) == {
        "0-30 days": {"GBP": 1500},
        "31-60 days": {"GBP": 700},
        "61-90 days": {"GBP": 300},
        "91+ days": {"GBP": 900},
    }


def test_aging_only_counts_open_records(store, make_record):
    paid = store.insert(make_record(issued_on=date(2025, 12, 20)))
    store.update_status(paid, "paid")
    assert projections.aging(store) == {}


def test_aging_accepts_custom_buckets(store, make_record):
    store.insert(make_record(issued_on=date(2025, 12, 20)))
    assert projections.aging(store, buckets=(7, 14)) == {
        "8-14 days": {"GBP": 1250},
    }


def test_aging_rejects_bad_buckets(store):
    with pytest.raises(ValueError):
        projections.aging(store, buckets=())
    with pytest.raises(ValueError):
        projections.aging(store, buckets=(0, 30))
