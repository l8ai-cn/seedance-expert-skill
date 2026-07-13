from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_metadata(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid metadata file: {path}") from error
    if not isinstance(document, dict):
        raise ValueError("metadata must contain a JSON object")
    return document


def create_metadata(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_temporary(path, document)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_metadata(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_temporary(path, document)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_temporary(path: Path, document: dict) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".part",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return temporary
