"""CLI happy paths for backfill, drain and report."""

from __future__ import annotations

import json

import pytest

from ledger import cli
from ledger.config import load
from ledger.models import Record
from ledger.queue import producer
from ledger.store import Store


def write_batch(path, records):
    payload = {"records": [record.to_dict() for record in records]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_backfill_inserts_every_record(tmp_path, make_record, capsys):
    path = write_batch(
        tmp_path / "batch.json",
        [make_record(), make_record(email="second@acme.example")],
    )
    store = Store.open_default()
    inserted, skipped = cli.backfill(store, path)
    assert (inserted, skipped) == (2, 0)
    assert store.count() == 2
    assert "inserted=2 skipped=0" in capsys.readouterr().out


def test_backfill_skips_invalid_records(tmp_path, make_record, capsys):
    path = write_batch(
        tmp_path / "batch.json",
        [make_record(), make_record(supplier="", email="broken@acme.example")],
    )
    store = Store.open_default()
    inserted, skipped = cli.backfill(store, path)
    assert (inserted, skipped) == (1, 1)
    assert "skip broken@acme.example" in capsys.readouterr().out


def test_backfill_reports_a_missing_file(tmp_path, capsys):
    assert cli.main(["backfill", "--file", str(tmp_path / "absent.json")]) == 1
    assert "error:" in capsys.readouterr().err


def test_backfill_reports_a_bad_batch_file(tmp_path, capsys):
    path = tmp_path / "batch.json"
    path.write_text('{"records": "nope"}', encoding="utf-8")
    assert cli.main(["backfill", "--file", str(path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_backfill_dry_run_writes_nothing(tmp_path, make_record, capsys):
    path = write_batch(tmp_path / "batch.json", [make_record()])
    assert cli.main(["backfill", "--file", str(path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would insert billing@acme.example" in out
    assert "dry-run inserted=1 skipped=0" in out
    assert Store.open_default().count() == 0


def test_drain_processes_queued_rows(make_record, capsys):
    store = Store.open_default()
    producer.enqueue(store, [make_record(), make_record(email="second@acme.example")])
    assert cli.main(["drain", "--limit", "10"]) == 0
    assert "processed=2" in capsys.readouterr().out
    assert Store.open_default().count() == 2


def test_drain_uses_the_configured_batch(make_record, capsys):
    store = Store.open_default()
    producer.enqueue(store, [make_record()])
    assert cli.main(["drain"]) == 0
    assert "processed=1" in capsys.readouterr().out


def test_report_prints_totals_and_writes_snapshots(make_record, capsys):
    store = Store.open_default()
    store.insert(make_record(currency="GBP", amount_cents=1250))
    store.insert(make_record(currency="USD", amount_cents=900, email="us@acme.example"))

    assert cli.main(["report"]) == 0
    out = capsys.readouterr().out
    assert '{"GBP": 1250, "USD": 900}' in out
    assert "records=2 currencies=2 suppliers=1" in out

    data_dir = load().data_dir
    totals_path = data_dir / "totals.json"
    export_path = data_dir / "export.json"
    assert totals_path.is_file()
    assert export_path.is_file()

    totals = json.loads(totals_path.read_text(encoding="utf-8"))
    assert totals["totals"] == {"GBP": 1250, "USD": 900}
    export = json.loads(export_path.read_text(encoding="utf-8"))
    assert len(export["records"]) == 2


def test_report_on_an_empty_ledger_writes_empty_totals(capsys):
    assert cli.main(["report"]) == 0
    out = capsys.readouterr().out
    assert "{}" in out
    assert "records=0 currencies=0 suppliers=0" in out
    totals = json.loads((load().data_dir / "totals.json").read_text(encoding="utf-8"))
    assert totals["totals"] == {}


def test_backfill_reads_records_as_models(tmp_path, make_record):
    path = write_batch(tmp_path / "batch.json", [make_record()])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert Record.from_dict(payload["records"][0]) == make_record()


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.main([])


def test_version_prints_and_exits_zero(capsys):
    from ledger import __version__

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
