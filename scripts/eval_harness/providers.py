from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from typing import Any

from .core import HarnessError, canonical_json, parse_json_bytes, utc_now


API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderError(HarnessError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        request_bytes: bytes = b"",
        response_bytes: bytes = b"",
        requested_model: str,
        settings: dict[str, Any],
        request_id: str | None = None,
        job_id: str | None = None,
        duration_ms: int,
        started_at: str,
        finished_at: str,
        response_complete: bool,
        truncated: bool,
    ):
        super().__init__(message)
        self.status = status
        self.request_bytes = request_bytes
        self.response_bytes = response_bytes
        self.provider = "anthropic"
        self.api_version = API_VERSION
        self.endpoint = API_URL
        self.requested_model = requested_model
        self.settings = settings
        self.request_id = request_id
        self.job_id = job_id
        self.duration_ms = duration_ms
        self.started_at = started_at
        self.finished_at = finished_at
        self.response_complete = response_complete
        self.truncated = truncated
        self.response_byte_limit = MAX_RESPONSE_BYTES


def anthropic_completion(api_key: str):
    def complete(system: str, user: str, model: str, max_tokens: int) -> dict[str, Any]:
        settings = {"max_tokens": max_tokens}
        payload = {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]}
        request_bytes = canonical_json(payload)
        request = urllib.request.Request(API_URL, data=request_bytes, method="POST")
        request.add_header("x-api-key", api_key)
        request.add_header("anthropic-version", API_VERSION)
        request.add_header("content-type", "application/json")
        started_at = utc_now()
        started = time.monotonic_ns()
        request_id = None
        http_status = None
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                request_id = response.headers.get("request-id") or response.headers.get("anthropic-request-id")
                http_status = getattr(response, "status", 200)
                response_bytes = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            body_read_failed = False
            try:
                response_bytes = exc.read(MAX_RESPONSE_BYTES + 1)
            except Exception:
                response_bytes = b""
                body_read_failed = True
            duration_ms = (time.monotonic_ns() - started) // 1_000_000
            truncated = len(response_bytes) > MAX_RESPONSE_BYTES
            headers = exc.headers or {}
            raise ProviderError(
                f"provider HTTP error {exc.code}" + ("; error body could not be read" if body_read_failed else ""),
                status=exc.code,
                request_bytes=request_bytes, response_bytes=response_bytes,
                requested_model=model, settings=settings,
                request_id=headers.get("request-id") or headers.get("anthropic-request-id"),
                duration_ms=duration_ms, started_at=started_at, finished_at=utc_now(),
                response_complete=not truncated and not body_read_failed, truncated=truncated,
            ) from exc
        except http.client.IncompleteRead as exc:
            response_bytes = exc.partial if isinstance(exc.partial, bytes) else b""
            duration_ms = (time.monotonic_ns() - started) // 1_000_000
            truncated = len(response_bytes) > MAX_RESPONSE_BYTES
            raise ProviderError(
                "provider response ended before the declared body was complete",
                status=http_status, request_bytes=request_bytes, response_bytes=response_bytes,
                requested_model=model, settings=settings, request_id=request_id,
                duration_ms=duration_ms, started_at=started_at, finished_at=utc_now(),
                response_complete=False, truncated=truncated,
            ) from exc
        except http.client.HTTPException as exc:
            duration_ms = (time.monotonic_ns() - started) // 1_000_000
            raise ProviderError(
                "provider HTTP protocol error", status=http_status, request_bytes=request_bytes,
                requested_model=model, settings=settings, request_id=request_id, duration_ms=duration_ms,
                started_at=started_at, finished_at=utc_now(), response_complete=False, truncated=False,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            duration_ms = (time.monotonic_ns() - started) // 1_000_000
            raise ProviderError(
                "provider transport error", request_bytes=request_bytes,
                requested_model=model, settings=settings, duration_ms=duration_ms,
                started_at=started_at, finished_at=utc_now(), response_complete=False, truncated=False,
            ) from exc
        duration_ms = (time.monotonic_ns() - started) // 1_000_000
        if len(response_bytes) > MAX_RESPONSE_BYTES:
            raise ProviderError(
                "provider response exceeds the configured byte limit",
                request_bytes=request_bytes, response_bytes=response_bytes,
                status=http_status, requested_model=model, settings=settings, request_id=request_id,
                duration_ms=duration_ms, started_at=started_at, finished_at=utc_now(),
                response_complete=False, truncated=True,
            )
        try:
            body = parse_json_bytes(response_bytes, "provider response")
        except HarnessError as exc:
            raise ProviderError(
                f"provider returned invalid JSON: {exc}",
                request_bytes=request_bytes, response_bytes=response_bytes,
                status=http_status, requested_model=model, settings=settings, request_id=request_id,
                duration_ms=duration_ms, started_at=started_at, finished_at=utc_now(),
                response_complete=True, truncated=False,
            ) from exc
        if not isinstance(body, dict):
            raise ProviderError(
                "provider response must be an object",
                request_bytes=request_bytes, response_bytes=response_bytes,
                status=http_status, requested_model=model, settings=settings, request_id=request_id,
                duration_ms=duration_ms, started_at=started_at, finished_at=utc_now(),
                response_complete=True, truncated=False,
            )
        text = "".join(
            block.get("text", "") for block in body.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )
        return {
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "text": text,
            "requested_model": model,
            "returned_model": body.get("model"),
            "request_id": request_id or body.get("id"),
            "job_id": body.get("id"),
            "stop_reason": body.get("stop_reason"),
            "usage": body.get("usage"),
            "duration_ms": duration_ms,
            "provider": "anthropic",
            "api_version": API_VERSION,
            "endpoint": API_URL,
            "http_status": http_status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "settings": settings,
        }

    return complete
