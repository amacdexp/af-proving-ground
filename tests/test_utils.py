"""Helpers for time, money, collections, JSON files and retries."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ledger import utils
from ledger.models import LineItem


def test_utcnow_is_timezone_aware():
    assert utils.utcnow().tzinfo is not None


def test_to_iso_formats_seconds_in_utc():
    moment = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    assert utils.to_iso(moment) == "2026-01-01T09:00:00+00:00"


def test_to_iso_treats_naive_times_as_utc():
    assert utils.to_iso(datetime(2026, 1, 1, 9, 0)) == "2026-01-01T09:00:00+00:00"


def test_from_iso_round_trips():
    moment = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    assert utils.from_iso(utils.to_iso(moment)) == moment


def test_parse_date_reads_iso_dates():
    assert utils.parse_date("2026-02-03") == date(2026, 2, 3)


def test_month_boundaries():
    day = date(2024, 2, 15)
    assert utils.month_key(day) == "2024-02"
    assert utils.start_of_month(day) == date(2024, 2, 1)
    assert utils.end_of_month(day) == date(2024, 2, 29)


def test_format_money_renders_cents():
    assert utils.format_money(1234) == "12.34"
    assert utils.format_money(-5) == "-0.05"
    assert utils.format_money(1000, "GBP") == "10.00 GBP"


def test_parse_money_reads_decimal_strings():
    assert utils.parse_money("12.34") == 1234
    assert utils.parse_money("-0.05") == -5


def test_parse_money_rejects_nonsense():
    with pytest.raises(ValueError):
        utils.parse_money("twelve")


def test_sum_cents_adds_integers():
    assert utils.sum_cents([1, 2, 3]) == 6
    assert utils.sum_cents([]) == 0


def test_is_blank_handles_whitespace_and_non_strings():
    assert utils.is_blank("  ") is True
    assert utils.is_blank("") is True
    assert utils.is_blank(None) is True
    assert utils.is_blank("x") is False


def test_stable_dumps_sorts_keys_without_spaces():
    assert utils.stable_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_dedupe_keeps_the_first_of_each_key():
    assert utils.dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert utils.dedupe(["aa", "ab", "ba"], key=lambda value: value[0]) == ["aa", "ba"]


def test_chunked_slices_a_sequence():
    assert list(utils.chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(utils.chunked([], 3)) == []
    with pytest.raises(ValueError):
        list(utils.chunked([1], 0))


def test_grouping_helpers():
    words = ["apple", "avocado", "banana", "cherry"]
    assert utils.group_by(words, key=lambda word: word[0]) == {
        "a": ["apple", "avocado"],
        "b": ["banana"],
        "c": ["cherry"],
    }
    assert utils.count_by(words, key=lambda word: word[0]) == {"a": 2, "b": 1, "c": 1}
    assert utils.sum_by(words, key=lambda word: word[0], amount=len) == {
        "a": 12,
        "b": 6,
        "c": 6,
    }


def test_json_round_trip_creates_parent_directories(tmp_path):
    path = tmp_path / "deep" / "payload.json"
    utils.write_json(path, {"b": 1, "a": [1, 2]})
    assert utils.read_json(path) == {"b": 1, "a": [1, 2]}
    assert not (tmp_path / "deep" / "payload.json.tmp").exists()


def test_encode_decode_and_fingerprint_agree(make_record):
    record = make_record(items=(LineItem("consulting", 1250),))
    assert utils.decode(utils.encode(record)) == record
    assert utils.fingerprint(record) == utils.fingerprint(
        make_record(items=(LineItem("consulting", 1250),))
    )
    assert utils.fingerprint(record) != utils.fingerprint(make_record(amount_cents=1))


def test_decode_rejects_a_non_object_payload():
    with pytest.raises(ValueError):
        utils.decode("[1, 2]")


def test_retry_recovers_after_transient_failures():
    attempts = {"count": 0}
    sleeps: list[float] = []

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("not yet")
        return "ok"

    assert utils.retry(flaky, attempts=3, sleep=sleeps.append) == "ok"
    assert attempts["count"] == 3
    assert sleeps == [0.01, 0.01]


def test_retry_raises_the_last_error():
    def always():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        utils.retry(always, attempts=2, sleep=lambda delay: None)


def test_retry_needs_at_least_one_attempt():
    with pytest.raises(ValueError):
        utils.retry(lambda: 1, attempts=0)


def test_format_money_handles_zero():
    assert utils.format_money(0) == "0.00"
    assert utils.format_money(0, "GBP") == "0.00 GBP"


def test_retry_does_not_catch_unlisted_exceptions():
    calls = {"count": 0}

    def wrong_error():
        calls["count"] += 1
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        utils.retry(wrong_error, attempts=3, exceptions=(OSError,))
    assert calls["count"] == 1


def test_write_json_replaces_an_existing_file(tmp_path):
    path = tmp_path / "value.json"
    utils.write_json(path, {"value": 1})
    utils.write_json(path, {"value": 2})
    assert utils.read_json(path) == {"value": 2}


def test_read_json_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        utils.read_json(tmp_path / "absent.json")
