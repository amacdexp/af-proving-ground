"""Validation primitives and the duplicate rule."""

from __future__ import annotations

from datetime import date

from ledger.models import LineItem
from ledger.validation import normalise_email, validate_batch, validate_fields, validate_record


def test_normalise_email_trims_and_lowercases():
    assert normalise_email("  Billing@Acme.Example \n") == "billing@acme.example"


def test_a_good_record_has_no_errors(store, make_record):
    assert validate_record(make_record(), store) == []


def test_a_blank_supplier_is_rejected(store, make_record):
    assert "supplier is required" in validate_record(make_record(supplier="  "), store)


def test_a_malformed_email_is_rejected(store, make_record):
    assert "email is invalid" in validate_record(make_record(email="not-an-email"), store)


def test_a_non_positive_amount_is_rejected(store, make_record):
    assert "amount_cents must be positive" in validate_record(make_record(amount_cents=0), store)


def test_a_currency_must_be_three_capitals(store, make_record):
    assert (
        "currency must be a three-letter code"
        in validate_record(make_record(currency="gbp"), store)
    )


def test_line_item_descriptions_are_required(store, make_record):
    errors = validate_record(make_record(items=(LineItem("", 100),)), store)
    assert "line item 1 needs a description" in errors


def test_line_item_amounts_cannot_be_negative(store, make_record):
    errors = validate_record(make_record(items=(LineItem("credit", -1),)), store)
    assert "line item 1 amount must be zero or more" in errors


def test_several_problems_are_collected(store, make_record):
    errors = validate_record(make_record(supplier="", currency="x", amount_cents=-5), store)
    assert len(errors) == 3


def test_strict_mode_finds_an_existing_address(store, make_record):
    store.insert(make_record(email="billing@acme.example"))
    duplicate = make_record(amount_cents=999)
    assert validate_record(duplicate, store, strict=True) == ["duplicate email"]


def test_strict_mode_accepts_an_unseen_address(store, make_record):
    assert validate_record(make_record(email="new@acme.example"), store, strict=True) == []


def test_an_issued_date_must_be_a_date(store, make_record):
    record = make_record()
    object.__setattr__(record, "issued_on", "2026-01-01")
    assert "issued_on must be a date" in validate_record(record, store)


def test_fields_can_be_checked_without_a_store(make_record):
    assert validate_fields(make_record()) == []
    assert validate_fields(make_record(supplier="")) == ["supplier is required"]


def test_validate_batch_reports_only_the_bad_positions(store, make_record):
    records = [
        make_record(),
        make_record(email="broken", issued_on=date(2026, 1, 2)),
        make_record(email="third@acme.example", issued_on=date(2026, 1, 3)),
    ]
    findings = validate_batch(records, store)
    assert [index for index, _ in findings] == [1]
    assert findings[0][1] == ["email is invalid"]


def test_validate_batch_can_report_several_bad_positions(store, make_record):
    records = [
        make_record(email="broken", issued_on=date(2026, 1, 2)),
        make_record(),
        make_record(supplier="", email="third@acme.example"),
    ]
    findings = validate_batch(records, store)
    assert [index for index, _ in findings] == [0, 2]


def test_duplicate_check_normalises_the_address(store, make_record):
    store.insert(make_record(email="billing@acme.example"))
    duplicate = make_record(email=" BILLING@Acme.Example ")
    assert validate_record(duplicate, store, strict=True) == ["duplicate email"]


def test_an_amount_must_be_an_integer(store, make_record):
    record = make_record()
    object.__setattr__(record, "amount_cents", "1250")
    assert "amount_cents must be an integer" in validate_record(record, store)


def test_a_currency_must_be_a_string(store, make_record):
    record = make_record()
    object.__setattr__(record, "currency", 826)
    assert "currency must be a three-letter code" in validate_record(record, store)


def test_a_line_item_amount_must_be_an_integer(store, make_record):
    errors = validate_record(make_record(items=(LineItem("consulting", "1250"),)), store)
    assert "line item 1 amount must be an integer" in errors
