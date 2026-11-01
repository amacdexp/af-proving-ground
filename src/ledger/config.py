"""Settings loader.

Settings live in ``settings.toml`` at the repository root. Two environment
variables change where things come from at run time:

``LEDGER_SETTINGS``
    path to an alternative settings file; relative ``data_dir`` values are
    resolved against the directory holding that file.

``LEDGER_DATA_DIR``
    overrides the storage directory, whatever the settings file says.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = "settings.toml"
ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Storage:
    data_dir: Path


@dataclass(frozen=True)
class Validation:
    strict: bool


@dataclass(frozen=True)
class Queue:
    batch: int


@dataclass(frozen=True)
class Settings:
    storage: Storage
    validation: Validation
    queue: Queue
    path: Path

    @property
    def data_dir(self) -> Path:
        """The configured storage directory, resolved against the settings file."""
        return self.storage.data_dir

    def as_dict(self) -> dict[str, Any]:
        """A plain JSON-friendly view, useful in logs and diagnostics."""
        return {
            "storage": {"data_dir": str(self.storage.data_dir)},
            "validation": {"strict": self.validation.strict},
            "queue": {"batch": self.queue.batch},
            "path": str(self.path),
        }


def settings_path() -> Path:
    override = os.environ.get("LEDGER_SETTINGS")
    if override:
        return Path(override).expanduser()
    return ROOT / DEFAULT_SETTINGS


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path)


def load(path: str | Path | None = None) -> Settings:
    """Read a settings file. With no argument, use the discovered one."""
    source = Path(path) if path is not None else settings_path()
    with open(source, "rb") as handle:
        raw = tomllib.load(handle)

    storage = raw.get("storage", {})
    validation = raw.get("validation", {})
    queue = raw.get("queue", {})

    return Settings(
        storage=Storage(data_dir=_resolve(source.parent, storage.get("data_dir", "data"))),
        validation=Validation(strict=bool(validation.get("strict", False))),
        queue=Queue(batch=int(queue.get("batch", 25))),
        path=source,
    )


def data_dir() -> Path:
    """The directory the application writes to."""
    override = os.environ.get("LEDGER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return load().storage.data_dir
