"""Shared fixtures: isolated settings, a fixed clock and a seeded store."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ledger.models import LineItem, Record
from ledger.store import Store

SETTINGS_TEMPLATE = """\
[storage]
data_dir = "data"

[validation]
strict = false

[queue]
batch = 25
"""

FIXED_NOW = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch, settings_file, tmp_path):
    """Keep every test's settings and storage inside its own tmp directory."""
    monkeypatch.setenv("LEDGER_SETTINGS", str(settings_file))
    monkeypatch.setenv("LEDGER_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def clock():
    return lambda: FIXED_NOW


@pytest.fixture
def store(tmp_path, clock):
    seeded = Store(str(tmp_path / "ledger.sqlite"), clock=clock)
    seeded.init_db()
    return seeded


@pytest.fixture
def make_record():
    def build(**overrides):
        fields = {
            "supplier": "Acme Ltd",
            "email": "billing@acme.example",
            "amount_cents": 1250,
            "currency": "GBP",
            "issued_on": date(2026, 1, 1),
            "items": (LineItem("consulting", 1250),),
        }
        fields.update(overrides)
        return Record(**fields)

    return build


@pytest.fixture
def client(store):
    from ledger.api.app import create_app

    return create_app(store).test_client()
