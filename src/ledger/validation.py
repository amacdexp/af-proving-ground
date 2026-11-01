"""Record validation and the duplicate rule."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

from ledger.config import load
from ledger.models import Record
from ledger.utils import is_blank

if TYPE_CHECKING:
    from ledger.store import Store

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def normalise_email(value: str) -> str:
    """Canonical form used when comparing addresses."""
    return value.strip().lower()


def validate_fields(rec: Record) -> list[str]:
    """Check the record on its own, without looking at what is stored."""
    errors: list[str] = []

    if is_blank(rec.supplier):
        errors.append("supplier is required")
    if is_blank(rec.email) or not EMAIL_RE.match(rec.email.strip()):
        errors.append("email is invalid")
    if isinstance(rec.amount_cents, bool) or not isinstance(rec.amount_cents, int):
        errors.append("amount_cents must be an integer")
    elif rec.amount_cents <= 0:
        errors.append("amount_cents must be positive")
    if not isinstance(rec.currency, str) or not CURRENCY_RE.match(rec.currency):
        errors.append("currency must be a three-letter code")
    if not isinstance(rec.issued_on, date):
        errors.append("issued_on must be a date")

    for index, item in enumerate(rec.items, start=1):
        if is_blank(item.description):
            errors.append(f"line item {index} needs a description")
        if isinstance(item.amount_cents, bool) or not isinstance(item.amount_cents, int):
            errors.append(f"line item {index} amount must be an integer")
        elif item.amount_cents < 0:
            errors.append(f"line item {index} amount must be zero or more")

    return errors


def validate_record(rec: Record, store: "Store", strict: bool | None = None) -> list[str]:
    """Return the problems with ``rec``; an empty list means it is acceptable.

    ``strict`` controls duplicate checking. ``None`` means "use the settings
    file"; an explicit boolean overrides it for this call.
    """
    errors = validate_fields(rec)

    check_duplicates = strict if strict is not None else load().validation.strict
    if check_duplicates and store.find_by_email(normalise_email(rec.email)):
        errors.append("duplicate email")

    return errors


def validate_batch(
    records: list[Record],
    store: "Store",
    strict: bool | None = None,
) -> list[tuple[int, list[str]]]:
    """Validate several records; returns ``(index, errors)`` for the bad ones."""
    findings: list[tuple[int, list[str]]] = []
    for index, record in enumerate(records):
        errors = validate_record(record, store, strict)
        if errors:
            findings.append((index, errors))
    return findings
