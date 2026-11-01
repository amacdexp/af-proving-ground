"""Settings loading and the storage directory override."""

from __future__ import annotations

import pytest

from ledger import config


def test_load_reads_the_discovered_file(settings_file):
    settings = config.load()
    assert settings.path == settings_file
    assert settings.storage.data_dir == settings_file.parent / "data"
    assert settings.validation.strict is False
    assert settings.queue.batch == 25


def test_load_accepts_an_explicit_path(tmp_path):
    path = tmp_path / "custom.toml"
    path.write_text(
        '[storage]\ndata_dir = "store"\n[validation]\nstrict = true\n[queue]\nbatch = 7\n',
        encoding="utf-8",
    )
    settings = config.load(path)
    assert settings.storage.data_dir == tmp_path / "store"
    assert settings.validation.strict is True
    assert settings.queue.batch == 7


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.load(tmp_path / "absent.toml")


def test_load_keeps_an_absolute_data_dir(tmp_path):
    path = tmp_path / "absolute.toml"
    path.write_text(f"[storage]\ndata_dir = \"{tmp_path / 'abs'}\"\n", encoding="utf-8")
    assert config.load(path).storage.data_dir == tmp_path / "abs"


def test_data_dir_honours_the_env_override(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    monkeypatch.setenv("LEDGER_DATA_DIR", str(target))
    assert config.data_dir() == target


def test_data_dir_falls_back_to_the_settings_file(monkeypatch):
    monkeypatch.delenv("LEDGER_DATA_DIR")
    assert config.data_dir() == config.load().storage.data_dir


def test_settings_path_follows_the_env(monkeypatch, settings_file):
    assert config.settings_path() == settings_file
    monkeypatch.delenv("LEDGER_SETTINGS")
    assert config.settings_path() == config.ROOT / "settings.toml"


def test_settings_as_dict_is_json_friendly(settings_file):
    data = config.load().as_dict()
    assert data == {
        "storage": {"data_dir": str(settings_file.parent / "data")},
        "validation": {"strict": False},
        "queue": {"batch": 25},
        "path": str(settings_file),
    }


def test_load_fills_defaults_for_missing_sections(tmp_path):
    path = tmp_path / "sparse.toml"
    path.write_text('[storage]\ndata_dir = "store"\n', encoding="utf-8")
    settings = config.load(path)
    assert settings.data_dir == tmp_path / "store"
    assert settings.validation.strict is False
    assert settings.queue.batch == 25
