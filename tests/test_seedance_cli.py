from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "seedance_generate.py"
CLI_NETWORK_FIXTURE = ROOT / "tests" / "fixtures" / "cli_network"


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    process_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


class SeedanceCliTests(unittest.TestCase):
    def test_help_runs_as_a_direct_script(self) -> None:
        result = run_cli("--help")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--check-credentials", result.stdout)
        self.assertIn("--print-approval", result.stdout)
        self.assertIn("--resume", result.stdout)
        self.assertNotIn("--allow-api-host", result.stdout)

    def test_print_approval_accepts_repeated_references_and_lints_real_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "Image2 becomes the last frame while Video1 guides movement and Audio1 guides voice.",
                "--output",
                str(Path(directory) / "result.mp4"),
                "--image-url",
                "reference_image=https://assets.example/one.png",
                "--image-url",
                "last_frame=https://assets.example/two.png",
                "--video-url",
                "reference_video=https://assets.example/motion.mp4",
                "--audio-url",
                "reference_audio=https://assets.example/voice.mp3",
                "--print-approval",
                env={"SEEDANCE_MODEL": "doubao-seedance-2-0-260128"},
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout.strip(), r"^[0-9a-f]{64}$")

    def test_execution_requires_the_exact_fingerprint_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                "A lamp turns on.",
                "--output",
                str(Path(directory) / "result.mp4"),
                "--approval",
                "0" * 64,
                env={
                    "SEEDANCE_API_KEY": "dummy",
                    "SEEDANCE_MODEL": "doubao-seedance-2-0-260128",
                },
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("approval fingerprint does not match", result.stderr)

    def test_invalid_billable_parameters_fail_before_approval(self) -> None:
        result = run_cli(
            "A lamp turns on.",
            "--output",
            "result.mp4",
            "--duration",
            "16",
            "--print-approval",
            env={"SEEDANCE_MODEL": "doubao-seedance-2-0-260128"},
        )

        self.assertEqual(2, result.returncode)
        self.assertTrue(re.search(r"duration.*4.*15", result.stderr, re.DOTALL))

    def test_reference_and_api_urls_fail_closed_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "result.mp4")
            reference = run_cli(
                "A lamp turns on.",
                "--output",
                output,
                "--image-url",
                "file:///etc/hosts",
                "--print-approval",
                env={"SEEDANCE_MODEL": "doubao-seedance-2-0-260128"},
            )
            api = run_cli(
                "A lamp turns on.",
                "--output",
                output,
                "--print-approval",
                env={
                    "SEEDANCE_MODEL": "doubao-seedance-2-0-260128",
                    "SEEDANCE_BASE_URL": "https://evil.example/api/v3",
                },
            )

        self.assertEqual(2, reference.returncode)
        self.assertIn("must use HTTPS", reference.stderr)
        self.assertEqual(2, api.returncode)
        self.assertIn("not allowed", api.stderr)

    def test_approval_changes_when_the_api_endpoint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = (
                "A lamp turns on.",
                "--output",
                str(Path(directory) / "result.mp4"),
                "--print-approval",
            )
            first = run_cli(
                *args,
                env={
                    "SEEDANCE_MODEL": "doubao-seedance-2-0-260128",
                    "SEEDANCE_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
                },
            )
            second = run_cli(
                *args,
                env={
                    "SEEDANCE_MODEL": "doubao-seedance-2-0-260128",
                    "SEEDANCE_BASE_URL": "https://ark.cn-beijing.volces.com/api/v4",
                },
            )

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertNotEqual(first.stdout.strip(), second.stdout.strip())

    def test_sub2api_seedance_cli_creates_polls_and_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.mp4"
            trace = root / "trace.jsonl"
            env = {
                "PYTHONPATH": str(CLI_NETWORK_FIXTURE),
                "PYTHONDONTWRITEBYTECODE": "1",
                "SEEDANCE_API_KEY": "test-key",
                "SEEDANCE_MODEL": "doubao-seedance-2-0-260128",
                "SEEDANCE_BASE_URL": "https://token.aiedulab.cn/api/v3",
                "SEEDANCE_TEST_TRACE": str(trace),
            }
            approval = run_cli(
                "A lamp turns on.",
                "--output",
                str(output),
                "--print-approval",
                env=env,
            )
            result = run_cli(
                "A lamp turns on.",
                "--output",
                str(output),
                "--approval",
                approval.stdout.strip(),
                "--poll-interval",
                "0.01",
                env=env,
            )

            self.assertEqual(0, approval.returncode, approval.stderr)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(b"sub2api-video", output.read_bytes())
            metadata = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual("succeeded", metadata["status"])
            requests = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                ["POST", "GET", "GET"],
                [request["method"] for request in requests],
            )
            self.assertEqual(
                "https://token.aiedulab.cn/api/v3/contents/generations/tasks",
                requests[0]["url"],
            )


if __name__ == "__main__":
    unittest.main()
