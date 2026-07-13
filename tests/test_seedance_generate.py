from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import scripts.seedance_generate as generation


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str = "application/json",
        url: str | None = None,
    ) -> None:
        self.body = body
        self.offset = 0
        self.headers = {"Content-Type": content_type}
        self.url = url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        if self.url is None:
            raise AssertionError("FakeOpener must set the response URL")
        return self.url


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if response.url is None:
            response.url = request.full_url
        return response


def require(name: str):
    value = getattr(generation, name, None)
    if value is None:
        raise AssertionError(f"scripts.seedance_generate must expose {name}")
    return value


class SeedanceRequestTests(unittest.TestCase):
    def test_serializes_all_official_reference_content_types_and_roles(self) -> None:
        reference = require("ReferenceInput")
        request = generation.GenerationRequest(
            prompt="Use Image2, Video1, and Audio1.",
            model="doubao-seedance-2-0-260128",
            references=(
                reference("image_url", "https://assets.example/one.png", "first_frame"),
                reference("image_url", "https://assets.example/two.png", "reference_image"),
                reference("video_url", "https://assets.example/motion.mp4", "reference_video"),
                reference("audio_url", "https://assets.example/voice.mp3", "reference_audio"),
            ),
        )

        self.assertEqual(
            [
                {"type": "text", "text": request.prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://assets.example/one.png"},
                    "role": "first_frame",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://assets.example/two.png"},
                    "role": "reference_image",
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "https://assets.example/motion.mp4"},
                    "role": "reference_video",
                },
                {
                    "type": "audio_url",
                    "audio_url": {"url": "https://assets.example/voice.mp3"},
                    "role": "reference_audio",
                },
            ],
            request.content(),
        )

    def test_validates_duration_ratio_resolution_and_reference_roles(self) -> None:
        validate = require("validate_generation_request")
        reference = require("ReferenceInput")

        for duration in (3, 16):
            with self.assertRaisesRegex(ValueError, "duration"):
                validate(generation.GenerationRequest("prompt", "model", duration=duration))
        with self.assertRaisesRegex(ValueError, "ratio"):
            validate(generation.GenerationRequest("prompt", "model", ratio="2:1"))
        with self.assertRaisesRegex(ValueError, "resolution"):
            validate(generation.GenerationRequest("prompt", "model", resolution="2k"))
        with self.assertRaisesRegex(ValueError, "role"):
            validate(
                generation.GenerationRequest(
                    "prompt",
                    "model",
                    references=(reference("video_url", "https://assets.example/a.mp4", "first_frame"),),
                )
            )

    def test_approval_fingerprint_binds_prompt_model_parameters_and_references(self) -> None:
        fingerprint = require("approval_fingerprint")
        reference = require("ReferenceInput")
        base = generation.GenerationRequest(
            "A lamp turns on.",
            "doubao-seedance-2-0-260128",
            references=(reference("image_url", "https://assets.example/lamp.png", "reference_image"),),
        )

        approved = fingerprint(base)

        self.assertRegex(approved, r"^[0-9a-f]{64}$")
        self.assertNotEqual(approved, fingerprint(generation.GenerationRequest("A lamp turns off.", base.model)))
        self.assertNotEqual(approved, fingerprint(generation.GenerationRequest(base.prompt, "other-model")))
        self.assertNotEqual(
            approved,
            fingerprint(
                generation.GenerationRequest(
                    base.prompt,
                    base.model,
                    references=(reference("image_url", "https://assets.example/other.png", "reference_image"),),
                )
            ),
        )
        self.assertEqual(approved, hashlib.sha256(base.approval_document()).hexdigest())


class ArkClientSecurityTests(unittest.TestCase):
    def test_api_base_requires_https_and_an_allowed_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            generation.ArkSeedanceClient("secret", "http://ark.cn-beijing.volces.com/api/v3")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            generation.ArkSeedanceClient("secret", "https://evil.example/api/v3")

        client = generation.ArkSeedanceClient(
            "secret",
            "https://private-ark.example/api/v3",
            allowed_api_hosts={"private-ark.example"},
        )
        self.assertEqual("https://private-ark.example/api/v3", client.base_url)

    def test_api_redirect_is_rejected_before_bearer_can_reach_another_host(self) -> None:
        opener = FakeOpener(
            [FakeResponse(b"{}", url="https://evil.example/contents/generations/tasks")]
        )
        client = generation.ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            api_opener=opener,
        )

        with self.assertRaisesRegex(RuntimeError, "redirect"):
            client.get_task("task-1")

    def test_download_rejects_non_https_empty_and_oversized_content_atomically(self) -> None:
        client = generation.ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            download_opener=FakeOpener([]),
            max_download_bytes=4,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            output.write_bytes(b"old")

            with self.assertRaisesRegex(ValueError, "HTTPS"):
                client.download("file:///etc/hosts", output)

            client.download_opener = FakeOpener(
                [FakeResponse(b"", content_type="video/mp4", url="https://files.example/a.mp4")]
            )
            with self.assertRaisesRegex(RuntimeError, "empty"):
                client.download("https://files.example/a.mp4", output)
            self.assertEqual(b"old", output.read_bytes())

            client.download_opener = FakeOpener(
                [FakeResponse(b"12345", content_type="video/mp4", url="https://files.example/a.mp4")]
            )
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                client.download("https://files.example/a.mp4", output)
            self.assertEqual(b"old", output.read_bytes())
            self.assertEqual([], list(output.parent.glob("*.part")))


class TaskLifecycleTests(unittest.TestCase):
    def test_task_id_is_persisted_before_polling_and_survives_timeout(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(b'{"id":"task-3"}'),
                FakeResponse(b'{"id":"task-3","status":"running"}'),
            ]
        )
        client = generation.ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            api_opener=opener,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")

            with self.assertRaisesRegex(TimeoutError, "task-3"):
                generation.generate(
                    client,
                    generation.GenerationRequest("A curtain moves.", "model"),
                    output,
                    poll_interval=0,
                    max_wait=0,
                    sleeper=lambda _seconds: None,
                )

            saved = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual("task-3", saved["task_id"])
            self.assertEqual("running", saved["status"])

    def test_resume_queries_and_downloads_without_creating_a_task(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(
                    b'{"id":"task-4","status":"succeeded","content":'
                    b'{"video_url":"https://files.example/video.mp4"}}'
                ),
                FakeResponse(
                    b"video",
                    content_type="video/mp4",
                    url="https://files.example/video.mp4",
                ),
            ]
        )
        client = generation.ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            api_opener=opener,
            download_opener=opener,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")
            request = generation.GenerationRequest("A lamp turns on.", "model")
            metadata.write_text(
                json.dumps(
                    {
                        "provider": "volcengine-ark",
                        "task_id": "task-4",
                        "status": "running",
                        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
                        "request_fingerprint": generation.approval_fingerprint(request),
                        "request": request.payload(),
                        "output_file": str(output),
                    }
                ),
                encoding="utf-8",
            )

            resumed = require("resume")
            self.assertEqual(
                metadata,
                resumed(client, metadata, poll_interval=0, sleeper=lambda _seconds: None),
            )
            self.assertTrue(output.exists())
            self.assertTrue(all(item[0].get_method() == "GET" for item in opener.requests))

    def test_output_json_is_rejected_before_any_task_is_created(self) -> None:
        opener = FakeOpener([])
        client = generation.ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            api_opener=opener,
        )

        with self.assertRaisesRegex(ValueError, "JSON"):
            generation.generate(
                client,
                generation.GenerationRequest("A lamp turns on.", "model"),
                Path("result.json"),
            )
        self.assertEqual([], opener.requests)


if __name__ == "__main__":
    unittest.main()
