from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.seedance_metadata import create_metadata
from scripts.seedance_request import GenerationRequest, approval_fingerprint
from scripts.seedance_task import generate, resume


TEST_MODEL = "doubao-seedance-2-0-260128"


class RecordingClient:
    def __init__(self, *, create_error: Exception | None = None) -> None:
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        self.create_error = create_error
        self.created = 0
        self.queried = 0

    def create_task(self, _request: GenerationRequest) -> str:
        self.created += 1
        if self.create_error:
            raise self.create_error
        return "task-created"

    def get_task(self, _task_id: str) -> dict:
        self.queried += 1
        return {"status": "running"}

    def download(self, _url: str, _output: Path) -> None:
        raise AssertionError("download is not expected")


class DeterministicHTTPError(RuntimeError):
    status_code = 404


class TaskRecoveryTests(unittest.TestCase):
    def test_initial_metadata_creation_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "result.json"
            create_metadata(metadata, {"status": "creating"})

            with self.assertRaises(FileExistsError):
                create_metadata(metadata, {"status": "other"})

            self.assertEqual(
                {"status": "creating"},
                json.loads(metadata.read_text(encoding="utf-8")),
            )

    def test_existing_metadata_blocks_duplicate_task_creation(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")
            metadata.write_text(
                json.dumps(
                    {
                        "provider": "volcengine-ark",
                        "task_id": "task-existing",
                        "status": "running",
                        "request_fingerprint": approval_fingerprint(request),
                        "request": request.metadata(),
                        "output_file": str(output),
                    }
                ),
                encoding="utf-8",
            )
            client = RecordingClient()

            with self.assertRaisesRegex(FileExistsError, "--resume"):
                generate(client, request, output, poll_interval=0, max_wait=0)

            self.assertEqual(0, client.created)

    def test_ambiguous_create_failure_is_persisted_and_blocks_retry(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")
            client = RecordingClient(create_error=TimeoutError("response timed out"))

            with self.assertRaisesRegex(TimeoutError, "response timed out"):
                generate(client, request, output)

            saved = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual("creation_unknown", saved["status"])
            self.assertEqual(approval_fingerprint(request), saved["request_fingerprint"])
            self.assertNotIn("task_id", saved)

            with self.assertRaisesRegex(FileExistsError, "creation outcome is unknown"):
                generate(RecordingClient(), request, output)

    def test_client_rejection_is_not_marked_as_creation_unknown(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")
            client = RecordingClient(create_error=DeterministicHTTPError("model not open"))

            with self.assertRaisesRegex(DeterministicHTTPError, "model not open"):
                generate(client, request, output)

            saved = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual("creation_rejected", saved["status"])
            self.assertEqual("model not open", saved["error"])

    def test_resume_rejects_tampered_request_fingerprint_without_network(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            metadata = output.with_suffix(".json")
            metadata.write_text(
                json.dumps(
                    {
                        "provider": "volcengine-ark",
                        "task_id": "task-existing",
                        "status": "running",
                        "request_fingerprint": "0" * 64,
                        "request": request.metadata(),
                        "output_file": str(output),
                    }
                ),
                encoding="utf-8",
            )
            client = RecordingClient()

            with self.assertRaisesRegex(ValueError, "fingerprint"):
                resume(client, metadata, poll_interval=0, max_wait=0)

            self.assertEqual(0, client.queried)

    def test_resume_rejects_output_metadata_path_collision(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "result.json"
            metadata.write_text(
                json.dumps(
                    {
                        "provider": "volcengine-ark",
                        "task_id": "task-existing",
                        "status": "running",
                        "request_fingerprint": approval_fingerprint(request),
                        "request": request.metadata(),
                        "output_file": str(metadata),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "metadata"):
                resume(RecordingClient(), metadata)

    def test_resume_requires_metadata_to_remain_adjacent_to_output(self) -> None:
        request = GenerationRequest("A lamp turns on.", TEST_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.mp4"
            metadata = root / "moved.json"
            metadata.write_text(
                json.dumps(
                    {
                        "provider": "volcengine-ark",
                        "api_base_url": "https://ark.cn-beijing.volces.com/api/v3",
                        "task_id": "task-existing",
                        "status": "running",
                        "request_fingerprint": approval_fingerprint(request),
                        "request": request.metadata(),
                        "output_file": str(output),
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "adjacent"):
                resume(RecordingClient(), metadata, poll_interval=0, max_wait=0)


if __name__ == "__main__":
    unittest.main()
