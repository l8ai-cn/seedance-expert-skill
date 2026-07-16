from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path

from scripts.seedance_url_policy import validate_https_url


CHUNK_SIZE = 1024 * 1024
ALLOWED_VIDEO_TYPES = {"application/octet-stream"}


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str] | None = None) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_https_url(
                newurl,
                label="download redirect URL",
                allowed_hosts=self.allowed_hosts,
            )
        except ValueError as error:
            raise RuntimeError(str(error)) from error
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_video(
    opener: urllib.request.OpenerDirector,
    url: str,
    output: Path,
    *,
    timeout: float,
    max_bytes: int,
    allowed_hosts: set[str] | None = None,
) -> None:
    source_url = validate_https_url(url, label="download URL", allowed_hosts=allowed_hosts)
    request = urllib.request.Request(source_url, method="GET")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else source_url
            try:
                validate_https_url(
                    final_url,
                    label="download redirect URL",
                    allowed_hosts=allowed_hosts,
                )
            except ValueError as error:
                raise RuntimeError(str(error)) from error
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if not content_type:
                raise RuntimeError("video download is missing Content-Type")
            if not content_type.startswith("video/") and content_type not in ALLOWED_VIDEO_TYPES:
                raise RuntimeError(f"video download returned {content_type}")
            _validate_content_length(response.headers.get("Content-Length"), max_bytes)
            temporary, total = _stream_to_temporary(response, output, max_bytes)
            if total == 0:
                raise RuntimeError("video download was empty")
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_content_length(value: str | None, max_bytes: int) -> None:
    if not value:
        return
    try:
        content_length = int(value)
    except ValueError as error:
        raise RuntimeError("video download returned an invalid Content-Length") from error
    if content_length <= 0:
        raise RuntimeError("video download was empty")
    if content_length > max_bytes:
        raise RuntimeError("video download exceeded size limit")


def _stream_to_temporary(response, output: Path, max_bytes: int) -> tuple[Path, int]:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            total = 0
            while chunk := response.read(CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError("video download exceeded size limit")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary, total
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
