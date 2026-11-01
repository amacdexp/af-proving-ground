"""Command line: backfill, drain and report."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ledger import __version__
from ledger import store as store_module
from ledger.config import load
from ledger.models import Record
from ledger.queue import consumer
from ledger.reports import projections
from ledger.sync import exporter
from ledger.utils import read_json, setup_logging
from ledger.validation import validate_record

log = logging.getLogger(__name__)


def _open_store() -> store_module.Store:
    return store_module.Store.open_default()


def backfill(store: store_module.Store, path: Path, dry_run: bool = False) -> tuple[int, int]:
    """Replay a historical batch file. Returns ``(inserted, skipped)``."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("batch file must hold a JSON object")
    entries = payload.get("records")
    if not isinstance(entries, list):
        raise ValueError("batch file needs a 'records' list")

    inserted = 0
    skipped = 0
    for entry in entries:
        record = Record.from_dict(entry)
        errors = validate_record(record, store, strict=True)
        if errors:
            print(f"skip {record.email}: {'; '.join(errors)}")
            skipped += 1
            continue
        if dry_run:
            print(f"would insert {record.email}")
        else:
            store.insert(record)
        inserted += 1

    label = "dry-run " if dry_run else ""
    print(f"{label}inserted={inserted} skipped={skipped}")
    return inserted, skipped


def drain(store: store_module.Store, limit: int | None = None) -> int:
    """Process queued imports. Returns the number of rows attempted."""
    batch = limit if limit is not None else load().queue.batch
    processed = consumer.drain(store, batch)
    print(f"processed={processed}")
    return processed


def report(store: store_module.Store) -> dict[str, int]:
    """Print totals, then write the totals and export snapshots."""
    data = projections.totals(store)
    counted = projections.summary(store)
    print(json.dumps(data, sort_keys=True))
    print(
        f"records={counted['record_count']} currencies={len(counted['currencies'])}"
        f" suppliers={len(counted['suppliers'])}"
    )
    totals_path = projections.write_totals(store)
    export_path = exporter.export(store)
    print(f"totals={totals_path}")
    print(f"export={export_path}")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledger.cli",
        description="Ledger maintenance commands",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log at debug level")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    back = sub.add_parser("backfill", help="replay a historical batch file")
    back.add_argument("--file", required=True, help="JSON batch file")
    back.add_argument("--dry-run", action="store_true", help="validate without inserting")

    drain_cmd = sub.add_parser("drain", help="process queued imports")
    drain_cmd.add_argument("--limit", type=int, default=None, help="maximum rows to process")

    sub.add_parser("report", help="print totals and write snapshots")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verbose:
        setup_logging(logging.DEBUG)

    if args.command == "backfill":
        try:
            backfill(_open_store(), Path(args.file), dry_run=args.dry_run)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "drain":
        drain(_open_store(), args.limit)
        return 0

    if args.command == "report":
        report(_open_store())
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
