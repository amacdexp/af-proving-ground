"""HTTP contract: records, imports and totals."""

from __future__ import annotations

import os
from pathlib import Path

from ledger.api.app import create_app


def test_post_records_returns_201_and_a_readable_row(client, make_record):
    response = client.post("/records", json=make_record().to_dict())
    assert response.status_code == 201
    record_id = response.get_json()["id"]
    assert response.headers["Location"] == f"/records/{record_id}"

    fetched = client.get(f"/records/{record_id}")
    assert fetched.status_code == 200
    body = fetched.get_json()
    assert body["id"] == record_id
    assert body["supplier"] == "Acme Ltd"
    assert body["status"] == "open"
    assert body["created_at"] == "2026-01-01T09:00:00+00:00"
    assert body["items"] == [{"description": "consulting", "amount_cents": 1250}]


def test_get_an_unknown_record_is_a_404(client):
    response = client.get("/records/999")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not_found"}


def test_post_records_rejects_a_non_object_body(client):
    response = client.post("/records", json=["not", "a", "record"])
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_record"


def test_post_records_rejects_a_missing_field(client):
    body = {"supplier": "Acme Ltd"}
    response = client.post("/records", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_record"


def test_post_records_rejects_a_bad_date(client, make_record):
    body = make_record().to_dict()
    body["issued_on"] = "01/01/2026"
    response = client.post("/records", json=body)
    assert response.status_code == 400


def test_post_import_enqueues_the_batch(client, make_record):
    body = {
        "records": [
            make_record().to_dict(),
            make_record(email="second@acme.example").to_dict(),
        ]
    }
    response = client.post("/import", json=body)
    assert response.status_code == 202
    assert response.get_json() == {"enqueued": 2}


def test_post_import_rejects_a_bad_batch(client, make_record):
    body = make_record().to_dict()
    response = client.post("/import", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_batch"


def test_totals_are_empty_at_the_start(client):
    response = client.get("/reports/totals")
    assert response.status_code == 200
    assert response.get_json() == {}


def test_totals_group_by_currency(client, make_record):
    client.post("/records", json=make_record(amount_cents=1250).to_dict())
    client.post(
        "/records",
        json=make_record(amount_cents=250, currency="USD", email="us@acme.example").to_dict(),
    )
    client.post(
        "/records",
        json=make_record(amount_cents=750, currency="USD", email="us2@acme.example").to_dict(),
    )
    assert client.get("/reports/totals").get_json() == {"GBP": 1250, "USD": 1000}


def test_create_app_opens_the_default_database():
    app = create_app()
    store = app.extensions["ledger_store"]
    expected = Path(os.environ["LEDGER_DATA_DIR"]) / "ledger.sqlite"
    assert store.path == expected
    response = app.test_client().get("/reports/totals")
    assert response.status_code == 200


def test_an_unknown_route_answers_with_json(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not_found"}


def test_a_wrong_method_answers_with_json(client):
    response = client.get("/records")
    assert response.status_code == 405
    assert response.get_json() == {"error": "method_not_allowed"}


def test_post_records_reports_field_errors(client, make_record):
    body = make_record(supplier="", amount_cents=-1).to_dict()
    response = client.post("/records", json=body)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "invalid_record"
    assert "supplier is required" in payload["errors"]
    assert "amount_cents must be positive" in payload["errors"]


def test_post_records_needs_a_json_object(client):
    response = client.post("/records", data="not json", content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_record"


def test_post_import_needs_a_records_list(client):
    response = client.post("/import", json={"records": {}})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_batch"


def test_post_import_rejects_a_bad_entry(client, make_record):
    bad = make_record().to_dict()
    bad["issued_on"] = "not-a-date"
    response = client.post("/import", json={"records": [bad]})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_batch"
