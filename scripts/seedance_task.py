from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from scripts.seedance_ark_client import ArkSeedanceClient
from scripts.seedance_metadata import create_metadata, read_metadata, write_metadata
from scripts.seedance_request import (
    GenerationRequest,
    approval_fingerprint,
    approval_fingerprint_for_payload,
    validate_generation_request,
)


TERMINAL_FAILURES = {"failed", "cancelled", "expired"}
ACTIVE_STATUSES = {"queued", "running"}
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


def generate(
    client: ArkSeedanceClient,
    request: GenerationRequest,
    output: Path,
    *,
    poll_interval: float = 10,
    max_wait: float = 1800,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    validate_generation_request(request)
    _validate_timing(poll_interval, max_wait)
    output = output.resolve()
    metadata = metadata_path_for(output)
    if metadata.exists():
        _raise_existing_metadata(metadata)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    document = {
        "provider": "volcengine-ark",
        "api_base_url": client.base_url,
        "status": "creating",
        "request_fingerprint": approval_fingerprint(request, client.base_url),
        "request": request.metadata(),
        "output_file": str(output),
    }
    create_metadata(metadata, document)
    try:
        task_id = client.create_task(request)
        _validate_task_id(task_id)
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        if status_code == 404:
            document["status"] = "endpoint_unavailable"
            document["error"] = str(error)
        elif isinstance(status_code, int) and 400 <= status_code < 500:
            document["status"] = "creation_rejected"
            document["error"] = str(error)
        else:
            document["status"] = "creation_unknown"
        write_metadata(metadata, document)
        raise
    document["task_id"] = task_id
    document["status"] = "created"
    write_metadata(metadata, document)
    return _poll(client, metadata, document, poll_interval, max_wait, sleeper)


def resume(
    client: ArkSeedanceClient,
    metadata: Path,
    *,
    poll_interval: float = 10,
    max_wait: float = 1800,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    _validate_timing(poll_interval, max_wait)
    document = read_metadata(metadata)
    if document.get("provider") != "volcengine-ark":
        raise ValueError("resume metadata has an unsupported provider")
    if not document.get("task_id"):
        raise ValueError("resume metadata is missing task_id")
    _validate_task_id(document["task_id"])
    output_file = document.get("output_file")
    if not isinstance(output_file, str) or not output_file:
        raise ValueError("resume metadata is missing output_file")
    output = Path(output_file)
    expected_metadata = metadata_path_for(output).resolve()
    if output.resolve() == metadata.resolve():
        raise ValueError("output and metadata paths must be different")
    if expected_metadata != metadata.resolve():
        raise ValueError("resume metadata must remain adjacent to its output file")
    _validate_fingerprint(document, client.base_url)
    return _poll(client, metadata, document, poll_interval, max_wait, sleeper)


def metadata_path_for(output: Path) -> Path:
    if output.suffix.lower() == ".json":
        raise ValueError("output must be a video path and must not conflict with JSON metadata")
    return output.with_suffix(".json")


def _raise_existing_metadata(metadata: Path) -> None:
    document = read_metadata(metadata)
    if document.get("task_id"):
        raise FileExistsError(f"task metadata already exists; use --resume {metadata}")
    if document.get("status") in {"creating", "creation_unknown"}:
        raise FileExistsError(
            f"task creation outcome is unknown; inspect the provider before removing {metadata}"
        )
    raise FileExistsError(f"metadata already exists: {metadata}")


def _validate_fingerprint(document: dict, client_base_url: str) -> None:
    payload = document.get("request")
    stored = document.get("request_fingerprint")
    base_url = document.get("api_base_url")
    if not isinstance(payload, dict) or not isinstance(stored, str) or not isinstance(base_url, str):
        raise ValueError("resume metadata is missing request fingerprint data")
    if base_url != client_base_url:
        raise ValueError("resume API base URL does not match the current client")
    if approval_fingerprint_for_payload(payload, base_url) != stored:
        raise ValueError("resume metadata request fingerprint does not match")


def _validate_task_id(task_id: object) -> None:
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("resume metadata contains an invalid task_id")


def _validate_timing(poll_interval: float, max_wait: float) -> None:
    if poll_interval < 0:
        raise ValueError("poll_interval must not be negative")
    if max_wait < 0:
        raise ValueError("max_wait must not be negative")


def _poll(
    client: ArkSeedanceClient,
    metadata: Path,
    document: dict,
    poll_interval: float,
    max_wait: float,
    sleeper: Callable[[float], None],
) -> Path:
    task_id = str(document["task_id"])
    started = time.monotonic()
    while True:
        result = client.get_task(task_id)
        status = result.get("status")
        document["status"] = status
        document["result"] = _result_summary(result)
        write_metadata(metadata, document)
        if status == "succeeded":
            video_url = _video_url(result, task_id)
            client.download(video_url, Path(document["output_file"]))
            return metadata
        if status in TERMINAL_FAILURES:
            raise _provider_failure(task_id, status, result.get("error"))
        if status not in ACTIVE_STATUSES:
            raise RuntimeError(f"Ark task {task_id} returned unknown status: {status!r}")
        if time.monotonic() - started >= max_wait:
            raise TimeoutError(f"Ark task {task_id} did not finish within {max_wait} seconds")
        sleeper(poll_interval)


def _video_url(result: dict, task_id: str) -> str:
    content = result.get("content")
    video_url = content.get("video_url") if isinstance(content, dict) else None
    if not isinstance(video_url, str) or not video_url:
        raise RuntimeError(f"Ark task {task_id} succeeded without content.video_url")
    return video_url


def _provider_failure(task_id: str, status: object, error: object) -> RuntimeError:
    if isinstance(error, dict):
        code = error.get("code", "unknown")
        message = error.get("message", status)
    else:
        code, message = "unknown", error or status
    return RuntimeError(f"Ark task {task_id} failed: {code}: {message}")


def _result_summary(result: dict) -> dict:
    return {
        key: result.get(key)
        for key in (
            "model",
            "duration",
            "ratio",
            "resolution",
            "seed",
            "created_at",
            "updated_at",
        )
    }
