from __future__ import annotations

import io
import json
import os
import urllib.request
from pathlib import Path


class Response:
    def __init__(self, body: bytes, url: str, content_type: str = "application/json") -> None:
        self._body = io.BytesIO(body)
        self._url = url
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url


class Opener:
    def open(self, request: urllib.request.Request, timeout: float):
        url = request.full_url
        _record(request.get_method(), url, timeout)
        if request.get_method() == "POST" and url.endswith("/contents/generations/tasks"):
            return Response(b'{"id":"task-sub2api-e2e"}', url)
        if url.endswith("/contents/generations/tasks/task-sub2api-e2e"):
            body = (
                b'{"id":"task-sub2api-e2e","status":"succeeded","content":'
                b'{"video_url":"https://a.lovart.ai/artifacts/agent/video.mp4"}}'
            )
            return Response(body, url)
        if url == "https://a.lovart.ai/artifacts/agent/video.mp4":
            return Response(b"sub2api-video", url, "video/mp4")
        raise AssertionError(f"unexpected request: {request.get_method()} {url}")


def _record(method: str, url: str, timeout: float) -> None:
    trace = Path(os.environ["SEEDANCE_TEST_TRACE"])
    with trace.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"method": method, "url": url, "timeout": timeout}) + "\n")


urllib.request.build_opener = lambda *_handlers: Opener()
