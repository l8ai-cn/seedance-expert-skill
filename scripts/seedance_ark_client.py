from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.seedance_download import HttpsOnlyRedirectHandler, download_video
from scripts.seedance_request import GenerationRequest, validate_ark_seedance_model
from scripts.seedance_url_policy import DEFAULT_API_HOST, validate_api_base_url


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class ArkSeedanceClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        allowed_api_hosts: set[str] | None = None,
        api_opener: urllib.request.OpenerDirector | None = None,
        download_opener: urllib.request.OpenerDirector | None = None,
        timeout: float = 60,
        max_download_bytes: int = 1024 * 1024 * 1024,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SEEDANCE_API_KEY is required")
        self.api_key = api_key.strip()
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_download_bytes <= 0:
            raise ValueError("max_download_bytes must be positive")
        self.allowed_api_hosts = {DEFAULT_API_HOST, *(allowed_api_hosts or set())}
        self.base_url = validate_api_base_url(base_url, self.allowed_api_hosts)
        self.api_opener = api_opener or urllib.request.build_opener(RejectRedirects())
        self.download_opener = download_opener or urllib.request.build_opener(
            HttpsOnlyRedirectHandler()
        )
        self.timeout = timeout
        self.max_download_bytes = max_download_bytes

    def create_task(self, request: GenerationRequest) -> str:
        result = self._json_request(
            f"{self.base_url}/contents/generations/tasks",
            method="POST",
            payload=request.payload(),
        )
        task_id = result.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("Ark create response is missing task id")
        return task_id

    def check_credentials(self, model: str) -> None:
        query = urllib.parse.urlencode({
            "page_size": 1,
            "filter.model": validate_ark_seedance_model(model),
        })
        self._json_request(f"{self.base_url}/contents/generations/tasks?{query}")

    def get_task(self, task_id: str) -> dict:
        return self._json_request(f"{self.base_url}/contents/generations/tasks/{task_id}")

    def download(self, url: str, output: Path) -> None:
        download_video(
            self.download_opener,
            url,
            output,
            timeout=self.timeout,
            max_bytes=self.max_download_bytes,
        )

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
    ) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with self._open_api(request, "Ark request") as response:
            _reject_redirect(response, url)
            try:
                decoded = json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RuntimeError("Ark returned invalid JSON") from error
        if not isinstance(decoded, dict):
            raise RuntimeError("Ark returned a non-object response")
        return decoded

    def _open_api(self, request: urllib.request.Request, label: str):
        try:
            return self.api_opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise RuntimeError(f"{label} redirect was rejected") from error
            detail = error.read(65536).decode("utf-8", errors="replace")
            raise RuntimeError(f"{label} failed with HTTP {error.code}: {detail}") from error


def _reject_redirect(response, requested_url: str) -> None:
    final_url = response.geturl() if hasattr(response, "geturl") else requested_url
    if final_url != requested_url:
        raise RuntimeError("redirect was rejected")
