"""Core types: line items, records, import batches and stored rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

STATUS_OPEN = "open"
STATUS_PAID = "paid"
STATUS_VOID = "void"
STATUSES = (STATUS_OPEN, STATUS_PAID, STATUS_VOID)


def _field(data: dict[str, Any], name: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError("record must be a JSON object")
    if name not in data:
        raise ValueError(f"missing field: {name}")
    return data[name]


def _text(data: dict[str, Any], name: str) -> str:
    value = _field(data, name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _integer(data: dict[str, Any], name: str) -> int:
    value = _field(data, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _iso_date(data: dict[str, Any], name: str) -> date:
    value = _text(data, name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD): {value!r}") from exc


@dataclass(frozen=True)
class LineItem:
    """One line on an invoice."""

    description: str
    amount_cents: int

    def to_dict(self) -> dict[str, Any]:
        return {"description": self.description, "amount_cents": self.amount_cents}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineItem":
        return cls(
            description=_text(data, "description"),
            amount_cents=_integer(data, "amount_cents"),
        )


@dataclass(frozen=True)
class Record:
    """One invoice, as it arrives from a supplier."""

    supplier: str
    email: str
    amount_cents: int
    currency: str
    issued_on: date
    items: tuple[LineItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplier": self.supplier,
            "email": self.email,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "issued_on": self.issued_on.isoformat(),
            "items": [item.to_dict() for item in self.items],
        }

    def summary(self) -> dict[str, Any]:
        """The fields a list view needs, without the line items."""
        return {
            "supplier": self.supplier,
            "email": self.email,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "issued_on": self.issued_on.isoformat(),
            "item_count": len(self.items),
        }

    def with_items(self, *items: LineItem) -> "Record":
        """A copy of this record with further line items appended."""
        return Record(
            supplier=self.supplier,
            email=self.email,
            amount_cents=self.amount_cents,
            currency=self.currency,
            issued_on=self.issued_on,
            items=self.items + tuple(items),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        if not isinstance(data, dict):
            raise ValueError("record must be a JSON object")
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ValueError("items must be a list")
        return cls(
            supplier=_text(data, "supplier"),
            email=_text(data, "email"),
            amount_cents=_integer(data, "amount_cents"),
            currency=_text(data, "currency"),
            issued_on=_iso_date(data, "issued_on"),
            items=tuple(LineItem.from_dict(entry) for entry in raw_items),
        )


@dataclass(frozen=True)
class ImportBatch:
    """A group of records arriving from one supplier."""

    supplier: str
    records: tuple[Record, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            object.__setattr__(self, "records", tuple(self.records))

    def __len__(self) -> int:
        return len(self.records)

    @property
    def is_empty(self) -> bool:
        return not self.records

    @property
    def total_cents(self) -> int:
        return sum(record.amount_cents for record in self.records)

    def currencies(self) -> tuple[str, ...]:
        return tuple(sorted({record.currency for record in self.records}))

    def total_by_currency(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for record in self.records:
            totals[record.currency] = totals.get(record.currency, 0) + record.amount_cents
        return totals

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplier": self.supplier,
            "records": [record.to_dict() for record in self.records],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImportBatch":
        if not isinstance(data, dict):
            raise ValueError("batch must be a JSON object")
        entries = data.get("records", [])
        if not isinstance(entries, list):
            raise ValueError("records must be a list")
        return cls(
            supplier=_text(data, "supplier"),
            records=tuple(Record.from_dict(entry) for entry in entries),
        )

    @classmethod
    def of(cls, supplier: str, records: Iterable[Record]) -> "ImportBatch":
        return cls(supplier=supplier, records=tuple(records))


@dataclass(frozen=True)
class StoredRecord:
    """A record as persisted, with its row id, status and timestamp."""

    id: int
    record: Record
    status: str
    created_at: str

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_OPEN

    @property
    def is_void(self) -> bool:
        return self.status == STATUS_VOID

    def to_dict(self) -> dict[str, Any]:
        data = self.record.to_dict()
        data.update({"id": self.id, "status": self.status, "created_at": self.created_at})
        return data
