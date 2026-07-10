from __future__ import annotations

import base64
import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_harness.core import (  # noqa: E402
    EVAL_SUITE_SCHEMA_URI,
    HarnessError,
    RunBundle,
    RuntimeResources,
    SEQUENCE_DIMENSIONS,
    aggregate,
    canonical_json,
    execute_case,
    load_suite,
    parse_judgment,
    recover_incomplete,
    sha256_bytes,
    verify_bundle,
)
from eval_harness.providers import MAX_RESPONSE_BYTES, ProviderError, anthropic_completion  # noqa: E402
from eval_run import executed_harness_sources  # noqa: E402


def completion_result(system: str, user: str, model: str, max_tokens: int, text: str, stop_reason: str = "end_turn") -> dict:
    request = canonical_json({"system": system, "user": user, "model": model, "max_tokens": max_tokens})
    response = canonical_json({"model": model, "text": text, "stop_reason": stop_reason})
    return {
        "request_bytes": request,
        "response_bytes": response,
        "text": text,
        "requested_model": model,
        "returned_model": model,
        "request_id": "request-test",
        "job_id": "job-test",
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "duration_ms": 1,
        "provider": "fixture",
        "api_version": "fixture-v1",
        "endpoint": "fixture://completion",
        "http_status": 200,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "settings": {"max_tokens": max_tokens},
    }


class QueueCompletion:
    def __init__(self, outputs: list[tuple[str, str]]):
        self.outputs = list(outputs)

    def __call__(self, system: str, user: str, model: str, max_tokens: int) -> dict:
        text, stop_reason = self.outputs.pop(0)
        return completion_result(system, user, model, max_tokens, text, stop_reason)


class CollidingCompletion(QueueCompletion):
    def __call__(self, system: str, user: str, model: str, max_tokens: int) -> dict:
        result = super().__call__(system, user, model, max_tokens)
        result["returned_model"] = "same-effective-model"
        return result


class FakeResponse:
    def __init__(self, data: bytes, status: int = 200):
        self.data = data
        self.status = status
        self.headers: dict[str, str] = {"request-id": "request-fake"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int) -> bytes:
        return self.data[:amount]


class IncompleteResponse(FakeResponse):
    def read(self, amount: int) -> bytes:
        raise http.client.IncompleteRead(b"partial-response", amount)


def minimal_bundle_records(run_id: str) -> tuple[dict, dict, dict]:
    case = {
        "case_id": "case-1",
        "attempt_index": 1,
        "status": "infrastructure_error",
        "passed": False,
        "sequence": False,
        "critical": False,
        "assets": [],
        "input_sha256": "a" * 64,
        "oracle_sha256": "b" * 64,
        "error": {"stage": "router", "type": "HarnessError", "message": "fixture failure"},
    }
    case_hash = sha256_bytes(canonical_json(case))
    summary = {
        "status": "incomplete",
        "passed": False,
        "release_pass": False,
        "release_eligible": False,
        "case_count": 1,
        "expected_case_count": 1,
        "failed_case_ids": ["case-1"],
        "legacy_average": None,
        "sequence_average": None,
        "thresholds_passed": True,
    }
    run = {
        "schema_version": 2,
        "run_id": run_id,
        "harness_version": "2.0.0",
        "network_used": True,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:00:01Z",
        "suite": {
            "suite_id": "fixture-suite",
            "kind": "development",
            "manifest_sha256": "1" * 64,
            "case_pack_sha256": "2" * 64,
            "complete_selection": True,
            "release_eligible": False,
        },
        "repository": {"commit_sha": "3" * 40, "tree_sha": "4" * 40, "clean": True, "status_sha256": "5" * 64},
        "models": {"responder": "responder-a", "judge": "judge-b", "distinct": True},
        "environment": {"python_version": "3.12.0", "python_implementation": "CPython", "platform": "fixture"},
        "attempt_index": 1,
        "cases": [{"ordinal": 1, "case_record_sha256": case_hash, "status": "infrastructure_error", "passed": False}],
        "summary": summary,
        "rubric": {"path": "references/eval-rubric.md", "sha256": sha256_bytes(b"rubric")},
        "runtime_tree_sha256": "7" * 64,
        "harness_sources": [{"path": "executed:fixture.py", "size": 1, "sha256": "8" * 64}],
        "configuration_sha256": "9" * 64,
        "egress_acknowledged": True,
        "release_gate_operational": False,
    }
    public = {
        "schema_version": 2,
        "run_id": run_id,
        "suite_kind": "development",
        "case_count": 1,
        "status": "incomplete",
        "passed": False,
        "release_pass": False,
        "failed_case_count": 1,
        "commit_sha": "3" * 40,
        "runtime_tree_sha256": "7" * 64,
    }
    return case, run, public


def rebind_bundle(path: Path) -> None:
    artifacts = []
    for item in sorted(file for file in path.rglob("*") if file.is_file() and file.name not in {"manifest.json", "COMPLETE.json"}):
        data = item.read_bytes()
        artifacts.append({"path": item.relative_to(path).as_posix(), "size": len(data), "sha256": sha256_bytes(data)})
    manifest = canonical_json({"schema_version": 2, "run_id": path.name, "artifacts": artifacts})
    (path / "manifest.json").write_bytes(manifest)
    (path / "COMPLETE.json").write_bytes(canonical_json({"schema_version": 2, "manifest_sha256": sha256_bytes(manifest)}))


def legacy_case() -> dict:
    return {
        "id": "blind_case",
        "prompt": "Write one concise Seedance prompt.",
        "expected_output": "ORACLE_OUTPUT_SENTINEL",
        "assertions": ["ORACLE_ASSERTION_SENTINEL"],
        "failure_mode": "ORACLE_FAILURE_SENTINEL",
        "skills_expected_to_activate": ["seedance-prompt"],
    }


def judgment(case: dict, *, passed: bool = True, score: int = 3) -> str:
    return json.dumps({
        "assertion_scores": [{"assertion": item, "met": True} for item in case["assertions"]],
        "dimension_scores": [],
        "overall_score": score,
        "pass": passed,
        "notes": "fixture judgment",
    })


def sequence_judgment(case: dict, *, passed: bool = True, score: int = 4, dimension_score: int = 3) -> str:
    return json.dumps({
        "assertion_scores": [{"assertion": item, "met": True} for item in case["assertions"]],
        "dimension_scores": [{"dimension": name, "score": dimension_score} for name in SEQUENCE_DIMENSIONS],
        "overall_score": score,
        "pass": passed,
        "notes": "fixture sequence judgment",
    })


class EvalHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resources = RuntimeResources(ROOT)
        cls.development = load_suite(ROOT, ROOT / "evals" / "suites" / "development.json")

    def test_offline_self_test_is_network_free_and_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/eval_run.py", "--self-test"], cwd=ROOT,
            text=True, capture_output=True, check=False,
            env={**os.environ, "ANTHROPIC_API_KEY": "must-not-be-used"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("zero network calls", result.stdout)

    def test_provenance_hashes_executing_harness_including_package_init(self) -> None:
        records = executed_harness_sources()
        self.assertEqual([record["path"] for record in records], sorted(record["path"] for record in records))
        self.assertIn("executed:eval_harness/__init__.py", [record["path"] for record in records])
        by_path = {record["path"]: record for record in records}
        actual = (ROOT / "scripts" / "eval_harness" / "__init__.py").read_bytes()
        self.assertEqual(by_path["executed:eval_harness/__init__.py"]["sha256"], sha256_bytes(actual))

    def test_responder_requests_exclude_oracle_and_preserve_raw_records(self) -> None:
        case = legacy_case()
        completion = QueueCompletion([
            (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
            ("candidate response", "end_turn"),
            (judgment(case), "end_turn"),
        ])
        record = execute_case(ROOT, self.resources, case, "rubric", "responder-a", "judge-b", completion, 1)
        self.assertTrue(record["passed"], record)
        for stage in ("router", "responder"):
            request = base64.b64decode(record[stage]["request_base64"])
            self.assertNotIn(b"ORACLE_ASSERTION_SENTINEL", request)
            self.assertNotIn(b"ORACLE_OUTPUT_SENTINEL", request)
            self.assertNotIn(b"ORACLE_FAILURE_SENTINEL", request)
        judge_request = base64.b64decode(record["judge"]["request_base64"])
        self.assertIn(b"ORACLE_ASSERTION_SENTINEL", judge_request)
        self.assertEqual(record["attempt_index"], 1)
        self.assertEqual(record["router"]["seed"]["support_status"], "not_supported_by_adapter")
        self.assertEqual(record["responder"]["cost"]["status"], "unknown")

    def test_complete_resources_are_loaded_without_truncation(self) -> None:
        system, records = self.resources.selected_system(["seedance-interview"])
        complete = (ROOT / "skills" / "seedance-interview" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(complete, system)
        self.assertNotIn("...[truncated]", system)
        self.assertTrue(any(record["path"] == "skills/seedance-interview/SKILL.md" and record["size"] > 12000 for record in records))
        for language in ("en", "es", "ja", "ko", "ru", "zh"):
            with self.subTest(language=language):
                _system, language_records = self.resources.selected_system([f"seedance-vocab-{language}"])
                self.assertIn(f"references/vocab/{language}.md", [record["path"] for record in language_records])
        _system, antislop_records = self.resources.selected_system(["seedance-antislop"])
        antislop_paths = [record["path"] for record in antislop_records]
        self.assertIn("references/vocab/en.md", antislop_paths)
        self.assertIn("references/vocab/zh.md", antislop_paths)

    def test_runtime_bytes_are_snapshotted_after_lock_verification(self) -> None:
        manifest = json.loads((ROOT / "runtime" / "seedance-20.manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "candidate"
            for relative in ["runtime/seedance-20.manifest.json", *manifest["files"]]:
                source = ROOT / relative
                destination = checkout / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            resources = RuntimeResources(checkout)
            locked_tree = resources.tree_sha256
            original_root = resources.text("SKILL.md")
            (checkout / "SKILL.md").write_text("MUTATED_AFTER_LOCK\n", encoding="utf-8")
            router_system, _records = resources.router_system()
            self.assertEqual(resources.tree_sha256, locked_tree)
            self.assertIn(original_root, router_system)
            self.assertNotIn("MUTATED_AFTER_LOCK", router_system)

    def test_root_only_route_and_effective_reference_closure_are_accounted(self) -> None:
        root_case = {**legacy_case(), "skills_expected_to_activate": ["seedance-20"]}
        root_completion = QueueCompletion([
            (json.dumps({"skills": [], "references": []}), "end_turn"),
            ("root response", "end_turn"),
            (judgment(root_case), "end_turn"),
        ])
        root_record = execute_case(ROOT, self.resources, root_case, "rubric", "responder-a", "judge-b", root_completion, 1)
        self.assertTrue(root_record["passed"], root_record)
        self.assertEqual(root_record["selected_route"], [])
        self.assertEqual(root_record["actual_route"], ["seedance-20"])
        self.assertEqual([item["path"] for item in root_record["responder_resources"]], ["SKILL.md"])

        pipeline_case = {**legacy_case(), "skills_expected_to_activate": ["seedance-pipeline"]}
        pipeline_completion = QueueCompletion([
            (json.dumps({"skills": ["seedance-pipeline"], "references": []}), "end_turn"),
            ("pipeline response", "end_turn"),
            (judgment(pipeline_case), "end_turn"),
        ])
        pipeline_record = execute_case(
            ROOT, self.resources, pipeline_case, "rubric", "responder-a", "judge-b", pipeline_completion, 1
        )
        self.assertIn("api-status", pipeline_record["actual_references"])
        self.assertIn("references/api-status.md", [item["path"] for item in pipeline_record["responder_resources"]])
        self.assertNotIn("skills/seedance-prompt/SKILL.md", [item["path"] for item in pipeline_record["responder_resources"]])

        over_routed = QueueCompletion([
            (json.dumps({"skills": ["seedance-prompt", "seedance-camera"], "references": []}), "end_turn"),
            ("over-routed response", "end_turn"),
            (judgment(legacy_case()), "end_turn"),
        ])
        over_routed_record = execute_case(
            ROOT, self.resources, legacy_case(), "rubric", "responder-a", "judge-b", over_routed, 1
        )
        self.assertFalse(over_routed_record["route_match"])
        self.assertFalse(over_routed_record["passed"])

    def test_state_fixture_reaches_responder_and_judge_but_oracle_only_reaches_judge(self) -> None:
        case = {
            **legacy_case(),
            "state_fixture": "examples/sequence-airport-arrival/project-state.json",
        }
        completion = QueueCompletion([
            (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
            ("candidate response", "end_turn"),
            (judgment(case), "end_turn"),
        ])
        record = execute_case(ROOT, self.resources, case, "rubric", "responder-a", "judge-b", completion, 1)
        responder_request = base64.b64decode(record["responder"]["request_base64"])
        judge_request = base64.b64decode(record["judge"]["request_base64"])
        fixture_sentinel = b"two steps from the open rear door"
        self.assertIn(fixture_sentinel, responder_request)
        self.assertIn(fixture_sentinel, judge_request)
        self.assertNotIn(b"ORACLE_ASSERTION_SENTINEL", responder_request)
        self.assertIn(b"ORACLE_ASSERTION_SENTINEL", judge_request)

    def test_pass_false_and_truncated_response_override_high_score(self) -> None:
        case = legacy_case()
        for model_pass, stop_reason in ((False, "end_turn"), (True, "max_tokens")):
            with self.subTest(model_pass=model_pass, stop_reason=stop_reason):
                completion = QueueCompletion([
                    (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
                    ("candidate", stop_reason),
                    (judgment(case, passed=model_pass, score=3), "end_turn"),
                ])
                record = execute_case(ROOT, self.resources, case, "rubric", "r", "j", completion, 1)
                self.assertFalse(record["passed"], record)

    def test_unknown_terminal_reasons_and_effective_model_collision_fail_closed(self) -> None:
        case = legacy_case()
        for outputs in (
            [(json.dumps({"skills": ["seedance-prompt"], "references": []}), None)],
            [
                (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
                ("candidate", "end_turn"),
                (judgment(case), "mystery"),
            ],
        ):
            with self.subTest(outputs=outputs):
                record = execute_case(ROOT, self.resources, case, "rubric", "responder-a", "judge-b", QueueCompletion(outputs), 1)
                self.assertEqual(record["status"], "infrastructure_error")
        colliding = CollidingCompletion([
            (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
            ("candidate", "end_turn"),
            (judgment(case), "end_turn"),
        ])
        record = execute_case(ROOT, self.resources, case, "rubric", "responder-a", "judge-b", colliding, 1)
        self.assertIn("same effective", record["error"]["message"])

    def test_empty_aggregate_and_unknown_ids_fail(self) -> None:
        summary = aggregate([], self.development)
        self.assertFalse(summary["passed"])
        self.assertFalse(summary["release_pass"])
        with self.assertRaisesRegex(HarnessError, "unknown case ids"):
            load_suite(ROOT, ROOT / "evals" / "suites" / "development.json", ["definitely_missing"])

    def test_live_suite_prohibits_partial_selection(self) -> None:
        with self.assertRaisesRegex(HarnessError, "prohibit"):
            load_suite(ROOT, ROOT / "evals" / "suites" / "live.json", ["direct_prompt_t2v"])

    def test_fixture_rejects_absolute_parent_and_symlink_paths(self) -> None:
        for value in ("/etc/hosts", "../outside.json", "examples\\state.json", ".git/config"):
            case = {**legacy_case(), "state_fixture": value}
            record = execute_case(ROOT, self.resources, case, "rubric", "r", "j", QueueCompletion([]), 1)
            self.assertEqual(record["status"], "infrastructure_error")
            self.assertTrue(
                "path" in record["error"]["message"] or "allowlist" in record["error"]["message"],
                record,
            )
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            target = directory / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = directory / "link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            case = {**legacy_case(), "state_fixture": "link.json"}
            record = execute_case(
                ROOT, self.resources, case, "rubric", "r", "j", QueueCompletion([]), 1,
                external_input_root=directory,
            )
            self.assertIn("link/reparse", record["error"]["message"])

    def test_heldout_suite_must_be_external_and_public_suites_are_not_release_eligible(self) -> None:
        self.assertFalse(self.development["release_eligible"])
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary)
            cases = outside / "cases.json"
            cases.write_text(json.dumps({"cases": [legacy_case()]}), encoding="utf-8")
            manifest = outside / "heldout.json"
            manifest.write_text(json.dumps({
                "$schema": EVAL_SUITE_SCHEMA_URI,
                "schema_version": 2,
                "suite_id": "heldout-test",
                "kind": "held_out",
                "case_file": "cases.json",
                "expected_case_count": 1,
                "release_eligible": True,
                "description": "sealed test suite",
            }), encoding="utf-8")
            suite = load_suite(ROOT, manifest)
            self.assertTrue(suite["declared_release_eligible"])
            self.assertFalse(suite["release_eligible"])

    def test_suite_manifest_allows_outer_alias_but_rejects_manifest_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(temporary)
            real = outer / "real"
            real.mkdir()
            (real / "cases.json").write_text(json.dumps({"cases": [legacy_case()]}), encoding="utf-8")
            manifest = real / "heldout.json"
            manifest.write_text(json.dumps({
                "$schema": EVAL_SUITE_SCHEMA_URI,
                "schema_version": 2,
                "suite_id": "heldout-alias",
                "kind": "held_out",
                "case_file": "cases.json",
                "expected_case_count": 1,
                "release_eligible": True,
                "description": "sealed alias fixture",
            }), encoding="utf-8")
            alias = outer / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            suite = load_suite(ROOT, alias / "heldout.json")
            self.assertEqual(suite["manifest"]["suite_id"], "heldout-alias")
            manifest_link = real / "linked.json"
            manifest_link.symlink_to(manifest)
            with self.assertRaisesRegex(HarnessError, "itself must not be"):
                load_suite(ROOT, manifest_link)

    def test_suite_resources_reject_typos_and_missing_inputs_before_network(self) -> None:
        suite = {"manifest": {"kind": "development"}, "input_root": ROOT, "cases": []}
        suite["cases"] = [{**legacy_case(), "skills_expected_to_activate": ["seedance-promtp"]}]
        with self.assertRaisesRegex(HarnessError, "unknown skills"):
            self.resources.validate_suite_resources(suite)
        suite["cases"] = [{**legacy_case(), "state_fixture": "examples/missing.json"}]
        with self.assertRaisesRegex(HarnessError, "allowlist"):
            self.resources.validate_suite_resources(suite)

    def test_judgment_rejects_malformed_types_ranges_and_missing_assertions(self) -> None:
        case = legacy_case()
        invalid = [
            {"assertion_scores": [], "dimension_scores": [], "overall_score": 3, "pass": True, "notes": ""},
            {"assertion_scores": [{"assertion": case["assertions"][0], "met": True}], "dimension_scores": [], "overall_score": 99, "pass": True, "notes": ""},
            {"assertion_scores": [{"assertion": case["assertions"][0], "met": True}], "dimension_scores": [], "overall_score": 3, "pass": "false", "notes": ""},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(HarnessError):
                parse_judgment(json.dumps(value), case)

    def test_network_run_requires_ack_models_and_distinct_judge_before_credentials(self) -> None:
        base = [sys.executable, "scripts/eval_run.py", "--run"]
        first = subprocess.run(base, cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(first.returncode, 2)
        self.assertIn("acknowledge", first.stdout)
        second = subprocess.run(
            base + ["--acknowledge-network-egress", "--responder-model", "same", "--judge-model", "same", "--output-root", "eval-runs"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(second.returncode, 2)
        self.assertIn("distinct", second.stdout)
        self.assertFalse((ROOT / "eval-runs").exists())

    def test_public_cli_refuses_external_heldout_execution_before_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "private"
            command = [
                sys.executable, "scripts/eval_run.py", "--run", "--acknowledge-network-egress",
                "--responder-model", "responder-a", "--judge-model", "judge-b",
                "--output-root", str(output), "--suite-file", "/does/not/need/to/exist.json",
            ]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("external/held-out execution is disabled", result.stdout)
            self.assertFalse(output.exists())

    def test_bundle_is_no_overwrite_manifested_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-test")
            reserved_inode = bundle.final.stat().st_ino
            self.assertTrue((bundle.final / "RESERVATION.json").is_file())
            with self.assertRaises(FileExistsError):
                bundle.final.mkdir()
            case, run, public = minimal_bundle_records("run-test")
            bundle.write_json("cases/0001.json", case)
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)
            if reserved_inode:
                self.assertEqual(final.stat().st_ino, reserved_inode)
            record = verify_bundle(final)
            self.assertFalse(record["summary"]["passed"])
            with self.assertRaisesRegex(HarnessError, "valid completed"):
                recover_incomplete(final)
            self.assertIsNone(bundle.abort())
            with self.assertRaisesRegex(HarnessError, "already exists"):
                RunBundle(output, "run-test")
            (final / "cases" / "0001.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(HarnessError, "integrity mismatch"):
                verify_bundle(final)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits unavailable")
    def test_existing_broad_output_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "broad"
            output.mkdir(mode=0o755)
            output.chmod(0o755)
            with self.assertRaisesRegex(HarnessError, "0700"):
                RunBundle(output, "run-private")

    def test_semantic_forgery_duplicate_manifest_and_special_entries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-forgery")
            case, run, public = minimal_bundle_records("run-forgery")
            bundle.write_json("cases/0001.json", case)
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)

            forged_run = json.loads((final / "run.json").read_text(encoding="utf-8"))
            forged_public = json.loads((final / "public-summary.json").read_text(encoding="utf-8"))
            forged_run["summary"]["release_pass"] = True
            forged_public["release_pass"] = True
            (final / "run.json").write_bytes(canonical_json(forged_run))
            (final / "public-summary.json").write_bytes(canonical_json(forged_public))
            rebind_bundle(final)
            with self.assertRaisesRegex(HarnessError, "release_pass"):
                verify_bundle(final)

        for mutation, message in (("wrong_run_id", "run_id"), ("duplicate_artifact", "duplicate")):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "runs"
                bundle = RunBundle(output, "run-manifest")
                case, run, public = minimal_bundle_records("run-manifest")
                bundle.write_json("cases/0001.json", case)
                bundle.write_json("public-summary.json", public)
                final = bundle.finish(run)
                manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
                if mutation == "wrong_run_id":
                    manifest["run_id"] = "different-run"
                else:
                    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
                manifest_bytes = canonical_json(manifest)
                (final / "manifest.json").write_bytes(manifest_bytes)
                (final / "COMPLETE.json").write_bytes(canonical_json({
                    "schema_version": 2, "manifest_sha256": sha256_bytes(manifest_bytes),
                }))
                with self.assertRaisesRegex(HarnessError, message):
                    verify_bundle(final)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-summary-mismatch")
            case, run, public = minimal_bundle_records("run-summary-mismatch")
            bundle.write_json("cases/0001.json", case)
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)
            public["passed"] = True
            (final / "public-summary.json").write_bytes(canonical_json(public))
            rebind_bundle(final)
            with self.assertRaisesRegex(HarnessError, "public summary passed"):
                verify_bundle(final)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-forged-case")
            _case, run, public = minimal_bundle_records("run-forged-case")
            forged_case = {
                "case_id": "case-1", "attempt_index": 1, "status": "completed", "passed": True,
                "sequence": False, "score": 3,
                "responder": {"requested_model": "responder-a", "returned_model": "effective-a"},
                "judge": {"requested_model": "judge-b", "returned_model": "effective-b"},
            }
            bundle.write_json("cases/0001.json", forged_case)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(forged_case)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": True, "failed_case_ids": [],
                "legacy_average": 3.0,
            })
            public.update({"status": "completed", "passed": True, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            with self.assertRaisesRegex(HarnessError, "completed case fields"):
                bundle.finish(run)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-completed-case")
            case_definition = legacy_case()
            completion = QueueCompletion([
                (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
                ("candidate response", "end_turn"),
                (judgment(case_definition), "end_turn"),
            ])
            completed_case = execute_case(
                ROOT, self.resources, case_definition, "rubric", "responder-a", "judge-b", completion, 1
            )
            _case, run, public = minimal_bundle_records("run-completed-case")
            bundle.write_json("cases/0001.json", completed_case)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(completed_case)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": True, "failed_case_ids": [],
                "legacy_average": 3.0,
            })
            public.update({"status": "completed", "passed": True, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)
            self.assertTrue(verify_bundle(final)["summary"]["passed"])
            tampered = json.loads(canonical_json(completed_case))
            tampered["responder_resources"] = [
                item for item in tampered["responder_resources"]
                if item["path"] != "skills/seedance-prompt/SKILL.md"
            ]
            (final / "cases" / "0001.json").write_bytes(canonical_json(tampered))
            run["cases"][0]["case_record_sha256"] = sha256_bytes(canonical_json(tampered))
            (final / "run.json").write_bytes(canonical_json(run))
            rebind_bundle(final)
            with self.assertRaisesRegex(HarnessError, "resource records do not match raw request"):
                verify_bundle(final)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-raw-semantic-forgery")
            case_definition = legacy_case()
            original_judgment = judgment(case_definition, passed=False, score=3)
            completion = QueueCompletion([
                (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
                ("candidate response", "end_turn"),
                (original_judgment, "end_turn"),
            ])
            forged = execute_case(
                ROOT, self.resources, case_definition, "rubric", "responder-a", "judge-b", completion, 1
            )
            forged_judgment = json.loads(judgment(case_definition, passed=True, score=3))
            forged["judge"]["text"] = json.dumps(forged_judgment)
            forged["judgment"] = forged_judgment
            forged["model_pass"] = True
            forged["passed"] = True
            _case, run, public = minimal_bundle_records("run-raw-semantic-forgery")
            bundle.write_json("cases/0001.json", forged)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(forged)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": True, "failed_case_ids": [], "legacy_average": 3.0,
            })
            public.update({"status": "completed", "passed": True, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            with self.assertRaisesRegex(HarnessError, "extracted fields do not match raw fixture response"):
                bundle.finish(run)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-unrelated-judge")
            case_definition = legacy_case()
            completion = QueueCompletion([
                (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
                ("candidate response", "end_turn"),
                (judgment(case_definition), "end_turn"),
            ])
            unrelated = execute_case(
                ROOT, self.resources, case_definition, "rubric", "responder-a", "judge-b", completion, 1
            )
            unrelated_request = canonical_json({
                "system": "not an evaluator",
                "user": "judge an unrelated candidate",
                "model": "judge-b",
                "max_tokens": 1400,
            })
            unrelated["judge"]["request_base64"] = base64.b64encode(unrelated_request).decode("ascii")
            unrelated["judge"]["request_sha256"] = sha256_bytes(unrelated_request)
            _case, run, public = minimal_bundle_records("run-unrelated-judge")
            bundle.write_json("cases/0001.json", unrelated)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(unrelated)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": True, "failed_case_ids": [], "legacy_average": 3.0,
            })
            public.update({"status": "completed", "passed": True, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            with self.assertRaisesRegex(HarnessError, "judge system"):
                bundle.finish(run)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-critical-downgrade")
            critical_case = next(case for case in self.development["cases"] if case.get("critical") is True)
            completion = QueueCompletion([
                (json.dumps({"skills": ["seedance-sequence"], "references": []}), "end_turn"),
                ("candidate sequence response", "end_turn"),
                (sequence_judgment(critical_case, score=3, dimension_score=3), "end_turn"),
            ])
            downgraded = execute_case(
                ROOT, self.resources, critical_case, "rubric", "responder-a", "judge-b", completion, 1
            )
            self.assertFalse(downgraded["passed"])
            downgraded["critical"] = False
            downgraded["passed"] = True
            _case, run, public = minimal_bundle_records("run-critical-downgrade")
            bundle.write_json("cases/0001.json", downgraded)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(downgraded)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": False, "failed_case_ids": [], "legacy_average": None,
                "sequence_average": 3.0, "thresholds_passed": False,
            })
            public.update({"status": "completed", "passed": False, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            with self.assertRaisesRegex(HarnessError, "flags do not match judge oracle"):
                bundle.finish(run)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-special")
            case, run, public = minimal_bundle_records("run-special")
            bundle.write_json("cases/0001.json", case)
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)
            link = final / "linked-directory"
            try:
                link.symlink_to(final / "cases", target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable")
            with self.assertRaisesRegex(HarnessError, "link/reparse"):
                verify_bundle(final)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO files unavailable")
    def test_bundle_rejects_fifo_and_socket_entries(self) -> None:
        for kind in ("fifo", "socket"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "runs"
                bundle = RunBundle(output, f"run-{kind}")
                case, run, public = minimal_bundle_records(f"run-{kind}")
                bundle.write_json("cases/0001.json", case)
                bundle.write_json("public-summary.json", public)
                final = bundle.finish(run)
                special = final / kind
                sock = None
                if kind == "fifo":
                    os.mkfifo(special)
                else:
                    if not hasattr(socket, "AF_UNIX"):
                        self.skipTest("Unix sockets unavailable")
                    try:
                        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        sock.bind(str(special))
                    except OSError:
                        if sock is not None:
                            sock.close()
                        continue
                try:
                    with self.assertRaisesRegex(HarnessError, "special file"):
                        verify_bundle(final)
                finally:
                    if sock is not None:
                        sock.close()

    def test_bundle_rejects_hard_linked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            bundle = RunBundle(output, "run-hardlink")
            case, run, public = minimal_bundle_records("run-hardlink")
            bundle.write_json("cases/0001.json", case)
            bundle.write_json("public-summary.json", public)
            final = bundle.finish(run)
            try:
                os.link(final / "run.json", final / "linked-run.json")
            except OSError:
                self.skipTest("hard links unavailable")
            with self.assertRaisesRegex(HarnessError, "hard-linked"):
                verify_bundle(final)

    def test_incomplete_recovery_is_idempotent_and_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = RunBundle(Path(temporary) / "runs", "crashed-run")
            bundle.write_json("checkpoints/0001-router.json", {"raw": "retained"})
            recovered = bundle.abort()
            self.assertIsNotNone(recovered)
            assert recovered is not None
            marker = json.loads((recovered / "INCOMPLETE.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["status"], "incomplete")
            self.assertFalse(marker["passed"])
            self.assertFalse(marker["release_pass"])
            self.assertEqual(recover_incomplete(recovered), recovered)
            self.assertTrue((recovered / "checkpoints" / "0001-router.json").is_file())

    def test_each_completed_stage_is_checkpointed_before_later_failure(self) -> None:
        case = legacy_case()
        snapshots: list[tuple[str, bytes]] = []
        completion = QueueCompletion([
            (json.dumps({"skills": ["seedance-prompt"], "references": []}), "end_turn"),
            ("candidate response", "end_turn"),
        ])
        record = execute_case(
            ROOT, self.resources, case, "rubric", "responder-a", "judge-b", completion, 1,
            checkpoint=lambda stage, partial: snapshots.append((stage, canonical_json(partial))),
        )
        self.assertEqual([stage for stage, _snapshot in snapshots], ["router", "responder", "error"])
        self.assertIn(b'"router"', snapshots[1][1])
        self.assertIn(b'"responder"', snapshots[1][1])
        self.assertEqual(record["error"]["stage"], "judge")

    def test_provider_failures_retain_bounded_metadata_and_never_serialize_auth_header(self) -> None:
        completion = anthropic_completion("SECRET_API_KEY")
        http_error = urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages", 429, "rate limited", {"request-id": "request-429"}, io.BytesIO(b'{"error":"limited"}')
        )
        headerless_http_error = urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages", 500, "server error", None, io.BytesIO(b'{"error":"server"}')
        )
        scenarios = [
            (http_error, True, False),
            (headerless_http_error, True, False),
            (TimeoutError("timeout"), False, False),
            (IncompleteResponse(b""), False, False),
            (FakeResponse(b"{" + b"x" * MAX_RESPONSE_BYTES), False, True),
            (FakeResponse(b'{"model":"a","model":"b"}'), True, False),
        ]
        for returned, response_complete, truncated in scenarios:
            with self.subTest(returned=type(returned).__name__), mock.patch(
                "eval_harness.providers.urllib.request.urlopen", side_effect=returned if isinstance(returned, BaseException) else None,
                return_value=None if isinstance(returned, BaseException) else returned,
            ):
                with self.assertRaises(ProviderError) as caught:
                    completion("system", "user", "model-a", 10)
                error = caught.exception
                self.assertEqual(error.requested_model, "model-a")
                self.assertEqual(error.response_complete, response_complete)
                self.assertEqual(error.truncated, truncated)
                self.assertEqual(error.response_byte_limit, MAX_RESPONSE_BYTES)
                self.assertNotIn(b"SECRET_API_KEY", error.request_bytes)

        checkpoints: list[tuple[str, dict]] = []
        with mock.patch("eval_harness.providers.urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            record = execute_case(
                ROOT, self.resources, legacy_case(), "rubric", "model-a", "model-b", completion, 1,
                checkpoint=lambda stage, partial: checkpoints.append((stage, json.loads(canonical_json(partial)))),
            )
        failure = record["provider_error_raw"]
        self.assertEqual(record["error"]["stage"], "router")
        self.assertEqual(failure["provider"], "anthropic")
        self.assertEqual(failure["endpoint"], "https://api.anthropic.com/v1/messages")
        self.assertFalse(failure["response_complete"])
        self.assertEqual(checkpoints[-1][0], "error")
        with tempfile.TemporaryDirectory() as temporary:
            bundle = RunBundle(Path(temporary) / "runs", "run-provider-failure")
            _case, run, public = minimal_bundle_records("run-provider-failure")
            bundle.write_json("cases/0001.json", record)
            run["models"] = {"responder": "model-a", "judge": "model-b", "distinct": True}
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(record)),
                "status": "infrastructure_error", "passed": False,
            }]
            run["summary"]["failed_case_ids"] = ["blind_case"]
            bundle.write_json("public-summary.json", public)
            self.assertFalse(verify_bundle(bundle.finish(run))["summary"]["passed"])

    def test_anthropic_success_raw_bytes_bind_every_scored_field(self) -> None:
        case = legacy_case()

        def response(model: str, job_id: str, text: str) -> FakeResponse:
            return FakeResponse(canonical_json({
                "id": job_id,
                "model": model,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }))

        responses = [
            response("effective-responder", "job-router", json.dumps({"skills": ["seedance-prompt"], "references": []})),
            response("effective-responder", "job-responder", "candidate response"),
            response("effective-judge", "job-judge", judgment(case)),
        ]
        with mock.patch("eval_harness.providers.urllib.request.urlopen", side_effect=responses):
            record = execute_case(
                ROOT, self.resources, case, "rubric", "responder-a", "judge-b",
                anthropic_completion("SECRET_API_KEY"), 1,
            )
        self.assertTrue(record["passed"], record)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = RunBundle(Path(temporary) / "runs", "run-anthropic")
            _case, run, public = minimal_bundle_records("run-anthropic")
            bundle.write_json("cases/0001.json", record)
            run["cases"] = [{
                "ordinal": 1, "case_record_sha256": sha256_bytes(canonical_json(record)),
                "status": "completed", "passed": True,
            }]
            run["summary"].update({
                "status": "completed", "passed": True, "failed_case_ids": [], "legacy_average": 3.0,
            })
            public.update({"status": "completed", "passed": True, "failed_case_count": 0})
            bundle.write_json("public-summary.json", public)
            self.assertTrue(verify_bundle(bundle.finish(run))["summary"]["passed"])

    def test_canonical_json_is_order_stable_and_rejects_nonfinite(self) -> None:
        self.assertEqual(canonical_json({"b": 2, "a": "中文"}), canonical_json({"a": "中文", "b": 2}))
        with self.assertRaises(HarnessError):
            canonical_json({"value": float("nan")})

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_suite_schema_executes_against_committed_manifests(self) -> None:
        schema = json.loads((ROOT / "evals" / "eval-suite-v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for name in ("development", "live"):
            instance = json.loads((ROOT / "evals" / "suites" / f"{name}.json").read_text(encoding="utf-8"))
            with self.subTest(name=name):
                self.assertEqual(list(validator.iter_errors(instance)), [])


if __name__ == "__main__":
    unittest.main()
