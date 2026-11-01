"""Shared helpers: time, money, JSON payloads and retries.

A deliberately broad module. The pieces here are small on their own; they are
kept together so callers have one place to look for the plumbing.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

from ledger.models import Record

T = TypeVar("T")
K = TypeVar("K")

PATH_CHUNK = 500


def utcnow() -> datetime:
    """Aware UTC timestamp. Stores take an injected clock in tests."""
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC string with second precision."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp."""
    return datetime.fromisoformat(value)


def parse_date(value: str) -> date:
    """Parse a ``YYYY-MM-DD`` date."""
    return date.fromisoformat(value)


def month_key(day: date) -> str:
    """The ``YYYY-MM`` bucket a date belongs to."""
    return f"{day.year:04d}-{day.month:02d}"


def start_of_month(day: date) -> date:
    """The first day of the month ``day`` falls in."""
    return day.replace(day=1)


def end_of_month(day: date) -> date:
    """The last day of the month ``day`` falls in."""
    _, last = calendar.monthrange(day.year, day.month)
    return day.replace(day=last)


def format_money(cents: int, currency: str = "") -> str:
    """Render integer cents as a decimal string, optionally with a currency."""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    text = f"{sign}{whole}.{part:02d}"
    return f"{text} {currency}".strip()


def parse_money(value: str) -> int:
    """Turn a decimal amount such as ``"12.34"`` into integer cents."""
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    return int((amount * 100).to_integral_value())


def sum_cents(values: Iterable[int]) -> int:
    """Add a stream of integer cents."""
    return sum(int(value) for value in values)


def is_blank(value: Any) -> bool:
    """True for non-strings and for strings that are empty or whitespace."""
    return not isinstance(value, str) or not value.strip()


def stable_dumps(payload: Any) -> str:
    """Canonical JSON: sorted keys, no incidental whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def encode(record: Record) -> str:
    """Serialise a record for the outbox."""
    return stable_dumps(record.to_dict())


def decode(payload: str) -> Record:
    """Rebuild a record from an outbox payload."""
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return Record.from_dict(data)


def fingerprint(record: Record) -> str:
    """A stable digest of a record's content."""
    return hashlib.sha256(encode(record).encode("utf-8")).hexdigest()


def dedupe(items: Iterable[T], key: Callable[[T], Any] | None = None) -> list[T]:
    """Drop repeats while keeping the original order."""
    seen: set[Any] = set()
    kept: list[T] = []
    for item in items:
        marker = key(item) if key is not None else item
        if marker in seen:
            continue
        seen.add(marker)
        kept.append(item)
    return kept


def chunked(values: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield consecutive slices of at most ``size`` items."""
    if size < 1:
        raise ValueError("size must be at least 1")
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def group_by(items: Iterable[T], key: Callable[[T], Any]) -> dict[Any, list[T]]:
    """Bucket items by a key, preserving their order within each bucket."""
    grouped: dict[Any, list[T]] = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return grouped


def count_by(items: Iterable[T], key: Callable[[T], Any]) -> dict[Any, int]:
    """Count items per key."""
    return {marker: len(bucket) for marker, bucket in group_by(items, key).items()}


def sum_by(
    items: Iterable[T],
    key: Callable[[T], Any],
    amount: Callable[[T], int],
) -> dict[Any, int]:
    """Sum an integer field per key."""
    totals: dict[Any, int] = {}
    for item in items:
        marker = key(item)
        totals[marker] = totals.get(marker, 0) + int(amount(item))
    return totals


def read_json(path: Path) -> Any:
    """Read and decode a JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    """Write JSON atomically, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def write() -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    retry(write, attempts=3, delay=0.01, exceptions=(OSError,))
    return path


def retry(
    func: Callable[[], T],
    attempts: int = 3,
    delay: float = 0.01,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``func`` until it stops raising one of ``exceptions``."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return func()
        except exceptions as exc:
            last = exc
            if attempt + 1 < attempts:
                sleep(delay)
    assert last is not None
    raise last


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for command line use."""
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
