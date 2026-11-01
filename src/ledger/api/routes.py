"""HTTP routes for records, imports and reports."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ledger.models import Record
from ledger.queue.producer import enqueue
from ledger.reports import projections
from ledger.store import Store
from ledger.validation import validate_record

bp = Blueprint("ledger", __name__)


def _store() -> Store:
    return current_app.extensions["ledger_store"]


def _body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    return payload


def _records_from(entries: list) -> list[Record]:
    return [Record.from_dict(entry) for entry in entries]


@bp.post("/records")
def create_record():
    try:
        record = Record.from_dict(_body())
    except ValueError as exc:
        return jsonify({"error": "invalid_record", "detail": str(exc)}), 400

    store = _store()
    errors = validate_record(record, store)
    if "duplicate email" in errors:
        return jsonify({"error": "duplicate_email"}), 409
    if errors:
        return jsonify({"error": "invalid_record", "errors": errors}), 400

    record_id = store.insert(record)
    return jsonify({"id": record_id}), 201, {"Location": f"/records/{record_id}"}


@bp.post("/import")
def create_import():
    try:
        payload = _body()
    except ValueError as exc:
        return jsonify({"error": "invalid_batch", "detail": str(exc)}), 400

    entries = payload.get("records")
    if not isinstance(entries, list):
        return jsonify({"error": "invalid_batch", "detail": "records must be a list"}), 400

    try:
        records = _records_from(entries)
    except ValueError as exc:
        return jsonify({"error": "invalid_batch", "detail": str(exc)}), 400

    return jsonify({"enqueued": enqueue(_store(), records)}), 202


@bp.get("/records/<int:record_id>")
def get_record(record_id: int):
    stored = _store().get(record_id)
    if stored is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(stored.to_dict()), 200


@bp.get("/reports/totals")
def report_totals():
    return jsonify(projections.totals(_store())), 200


@bp.app_errorhandler(404)
def _missing_route(_error):
    return jsonify({"error": "not_found"}), 404


@bp.app_errorhandler(405)
def _wrong_method(_error):
    return jsonify({"error": "method_not_allowed"}), 405
