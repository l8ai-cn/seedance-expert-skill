from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # dependency-free portability lane
    Draft202012Validator = FormatChecker = None  # type: ignore[assignment,misc]

from scripts import evaluation_program_check as checker


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "evals" / "evaluation-program-v1.json"
CHECKER = ROOT / "scripts" / "evaluation_program_check.py"


def load_json(path: Path) -> dict[str, object]:
    value = checker.strict_load_json(path)
    assert isinstance(value, dict)
    return value


class EvaluationProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.program = load_json(PROGRAM)
        cls.benchmark_path = ROOT / "validation" / "fixtures" / "benchmark-manifest-v1.valid.json"
        cls.benchmark_snapshot = checker.strict_load_snapshot(cls.benchmark_path)
        cls.benchmark = cls.benchmark_snapshot.value
        cls.annotation = load_json(ROOT / "validation" / "fixtures" / "atomic-output-annotation-v1.valid.json")
        cls.benchmark_sha256 = cls.benchmark_snapshot.sha256

    def test_checked_in_program_is_closed_and_non_release(self) -> None:
        self.assertEqual(checker.validate_program(copy.deepcopy(self.program), ROOT), [])
        self.assertIs(self.program["release_gate"], False)
        self.assertIs(self.program["quality_claims_allowed"], False)
        self.assertEqual(self.program["network_policy"], "forbidden")
        self.assertEqual(
            self.program["public_corpora"],
            {
                "development_release_eligible": False,
                "live_canary_release_eligible": False,
                "held_out_execution": "blocked_without_protected_runner",
            },
        )

    def test_all_declared_program_mutations_fail_closed(self) -> None:
        detected, total, failures = checker.run_program_mutations(copy.deepcopy(self.program), ROOT)
        self.assertEqual(failures, [])
        self.assertEqual((detected, total), (len(checker.PROGRAM_MUTATIONS), len(checker.PROGRAM_MUTATIONS)))
        self.assertGreaterEqual(detected / total, 0.9)

    def test_benchmark_and_atomic_annotation_are_exactly_cross_bound(self) -> None:
        self.assertEqual(checker.validate_benchmark_manifest(copy.deepcopy(self.benchmark), ROOT), [])
        self.assertEqual(
            checker.validate_atomic_annotation(
                copy.deepcopy(self.annotation),
                self.benchmark_snapshot,
            ),
            [],
        )
        self.assertEqual(self.annotation["benchmark_manifest_sha256"], self.benchmark_sha256)
        annotation_schema = ROOT / "schemas" / "atomic-output-annotation-v1.schema.json"
        self.assertEqual(
            self.benchmark["protocol"]["annotation_schema_sha256"],
            checker._raw_sha256(annotation_schema),
        )

    def test_all_declared_output_review_mutations_fail_closed(self) -> None:
        detected, total, failures = checker.run_output_review_mutations(
            copy.deepcopy(self.annotation),
            self.benchmark_snapshot,
        )
        self.assertEqual(failures, [])
        self.assertEqual((detected, total), (len(checker.OUTPUT_REVIEW_MUTATIONS), len(checker.OUTPUT_REVIEW_MUTATIONS)))
        self.assertGreaterEqual(detected / total, 0.9)

    def test_complete_double_review_is_failure_first_order_invariant_and_non_release(self) -> None:
        annotations = checker.synthetic_annotation_matrix(
            copy.deepcopy(self.annotation),
            self.benchmark_snapshot,
        )
        report, errors = checker.aggregate_output_reviews(self.benchmark_snapshot, annotations)
        self.assertEqual(errors, [])
        self.assertEqual(report["condition_verdict"], "pass")
        self.assertEqual(report["attempt_count"], 10)
        self.assertEqual(report["retained_attempt_count"], 10)
        self.assertEqual(report["resolved_review_cell_count"], 220)
        self.assertEqual(report["observable_catalog_item_count"], 22)
        self.assertEqual(report["observable_dimension_count"], 22)
        self.assertEqual(report["benchmark_manifest_sha256"], self.benchmark_sha256)
        self.assertEqual(sum(report["confidence_counts"].values()), 220)
        self.assertIs(report["release_pass"], False)
        self.assertIs(report["quality_claims_allowed"], False)

        reordered, reordered_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot,
            list(reversed(annotations)),
        )
        self.assertEqual(reordered_errors, [])
        self.assertEqual(reordered, report)

        failed = copy.deepcopy(annotations)
        failed[0]["status"] = "fail"
        failed[1]["status"] = "fail"
        failure_report, failure_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot,
            failed,
        )
        self.assertEqual(failure_errors, [])
        self.assertEqual(failure_report["condition_verdict"], "fail")
        self.assertEqual(failure_report["status_counts"]["fail"], 1)

    def test_missing_disputed_or_unknown_reviews_never_pass(self) -> None:
        annotations = checker.synthetic_annotation_matrix(self.annotation, self.benchmark_snapshot)

        missing_report, missing_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot,
            annotations[:-1],
        )
        self.assertTrue(missing_errors)
        self.assertEqual(missing_report["condition_verdict"], "incomplete")

        disputed = copy.deepcopy(annotations)
        disputed[0]["status"] = "fail"
        disputed[0]["confidence"] = "high"
        disputed_report, disputed_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot,
            disputed,
        )
        self.assertIn("aggregate.missing_adjudication", disputed_errors)
        self.assertEqual(disputed_report["condition_verdict"], "incomplete")

        unknown = copy.deepcopy(annotations)
        for index in (0, 1):
            unknown[index]["status"] = "unknown"
            unknown[index]["confidence"] = "unknown"
            unknown[index]["evidence_locus"] = {"kind": "unavailable"}
        unknown_report, unknown_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot,
            unknown,
        )
        self.assertEqual(unknown_errors, [])
        self.assertEqual(unknown_report["condition_verdict"], "incomplete")
        self.assertEqual(unknown_report["status_counts"]["unknown"], 1)

    def test_repeated_observable_dimensions_are_reviewed_as_distinct_cells(self) -> None:
        manifest = copy.deepcopy(self.benchmark)
        manifest["condition"]["observable_catalog"].append({
            "observable_id": "dialogue_exactness.line_02",
            "observable_dimension": "dialogue_exactness",
            "rubric_item_sha256": "f" * 64,
        })
        snapshot = checker.snapshot_from_value(manifest)
        self.assertEqual(checker.validate_benchmark_manifest(manifest), [])
        annotations = checker.synthetic_annotation_matrix(self.annotation, snapshot)
        report, errors = checker.aggregate_output_reviews(snapshot, annotations)
        self.assertEqual(errors, [])
        self.assertEqual(report["observable_catalog_item_count"], 23)
        self.assertEqual(report["observable_dimension_count"], 22)
        self.assertEqual(report["resolved_review_cell_count"], 230)
        dialogue_ids = {
            annotation["observable_id"]
            for annotation in annotations
            if annotation["observable_dimension"] == "dialogue_exactness"
        }
        self.assertEqual(dialogue_ids, {"dialogue_exactness", "dialogue_exactness.line_02"})

    def test_duplicate_review_cells_are_excluded_order_invariantly(self) -> None:
        annotations = checker.synthetic_annotation_matrix(self.annotation, self.benchmark_snapshot)
        duplicate = copy.deepcopy(annotations[0])
        duplicate["annotation_id"] = "ann_duplicate_cell"
        duplicate["status"] = "fail"
        rows = [*annotations, duplicate]
        report, errors = checker.aggregate_output_reviews(self.benchmark_snapshot, rows)
        reversed_report, reversed_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot, list(reversed(rows))
        )
        self.assertIn("aggregate.duplicate_review_cell", errors)
        self.assertEqual(errors, reversed_errors)
        self.assertEqual(report, reversed_report)
        self.assertEqual(report["condition_verdict"], "incomplete")

    def test_request_hashes_may_repeat_but_comparability_fields_may_not_drift(self) -> None:
        repeated = copy.deepcopy(self.benchmark)
        repeated["attempts"][1]["request_sha256"] = repeated["attempts"][0]["request_sha256"]
        self.assertEqual(checker.validate_benchmark_manifest(repeated), [])

        drifted = copy.deepcopy(repeated)
        drifted["attempts"][1]["request_template_sha256"] = "f" * 64
        self.assertIn(
            "benchmark.attempts.2.request_template_sha256_mismatch",
            checker.validate_benchmark_manifest(drifted),
        )

    def test_static_derived_final_frame_can_localize_identity_or_composition_failure(self) -> None:
        attempt = self.benchmark["attempts"][0]
        for dimension in ("identity_adherence", "composition_adherence"):
            with self.subTest(dimension=dimension):
                catalog_item = next(
                    item
                    for item in self.benchmark["condition"]["observable_catalog"]
                    if item["observable_dimension"] == dimension
                )
                annotation = copy.deepcopy(self.annotation)
                annotation.update({
                    "observable_id": catalog_item["observable_id"],
                    "observable_dimension": dimension,
                    "rubric_item_sha256": catalog_item["rubric_item_sha256"],
                    "status": "fail",
                    "evidence_asset_kind": "derived_final_frame",
                    "evidence_asset_sha256": "10467e3558cff078bb98ac3363164bc1d4dce469ab4d5660503f55fd0d082361",
                    "evidence_parent_output_sha256": attempt["output_media_sha256"],
                    "derivation_record_sha256": "e136aa019a233120a713b40be72eaf97599ff393720344c27eba34647b5f4bbd",
                    "evidence_locus": {"kind": "single_frame", "frame_index": attempt["frame_count"] - 1},
                })
                self.assertEqual(checker.validate_atomic_annotation(annotation, self.benchmark_snapshot), [])

    def test_loci_audio_and_whole_output_rules_are_bounded(self) -> None:
        attempt = self.benchmark["attempts"][0]
        one_frame_manifest = copy.deepcopy(self.benchmark)
        one_frame_manifest["attempts"][0]["frame_count"] = 1
        self.assertIn(
            "benchmark.attempts.1.frame_count",
            checker.validate_benchmark_manifest(one_frame_manifest),
        )
        one_frame_snapshot = checker.snapshot_from_value(one_frame_manifest)
        one_frame_annotation = copy.deepcopy(self.annotation)
        one_frame_annotation["benchmark_manifest_sha256"] = one_frame_snapshot.sha256
        self.assertIn(
            "annotation.temporal_requires_multiframe_video",
            checker.validate_atomic_annotation(one_frame_annotation, one_frame_snapshot),
        )

        out_of_time = copy.deepcopy(self.annotation)
        out_of_time["evidence_locus"] = {
            "kind": "video_time_range",
            "start_ms": 0,
            "end_ms": attempt["duration_ms"] + 1,
        }
        self.assertIn(
            "annotation.evidence_locus.time_range_bounds",
            checker.validate_atomic_annotation(out_of_time, self.benchmark_snapshot),
        )

        one_frame = copy.deepcopy(self.annotation)
        one_frame["evidence_locus"] = {"kind": "video_frame_range", "start_frame": 4, "end_frame": 4}
        self.assertIn(
            "annotation.evidence_locus.temporal_frame_span",
            checker.validate_atomic_annotation(one_frame, self.benchmark_snapshot),
        )

        out_of_frames = copy.deepcopy(self.annotation)
        out_of_frames["evidence_locus"] = {
            "kind": "video_frame_range",
            "start_frame": 0,
            "end_frame": attempt["frame_count"],
        }
        self.assertIn(
            "annotation.evidence_locus.frame_range_bounds",
            checker.validate_atomic_annotation(out_of_frames, self.benchmark_snapshot),
        )

        no_audio_manifest = copy.deepcopy(self.benchmark)
        no_audio_manifest["attempts"][0]["audio_present"] = False
        no_audio_snapshot = checker.snapshot_from_value(no_audio_manifest)
        no_audio = copy.deepcopy(self.annotation)
        no_audio["benchmark_manifest_sha256"] = no_audio_snapshot.sha256
        self.assertIn(
            "annotation.audio_observable_requires_audio",
            checker.validate_atomic_annotation(no_audio, no_audio_snapshot),
        )

        for dimension, status, expected_error in (
            ("operation_correctness", "pass", "annotation.global_pass_requires_whole_video"),
            ("unexpected_text_logo", "pass", "annotation.global_pass_requires_whole_video"),
            ("overall_usable_take", "fail", "annotation.usability_requires_whole_video"),
        ):
            with self.subTest(dimension=dimension):
                item = next(
                    entry
                    for entry in self.benchmark["condition"]["observable_catalog"]
                    if entry["observable_dimension"] == dimension
                )
                partial = copy.deepcopy(self.annotation)
                partial.update({
                    "observable_id": item["observable_id"],
                    "observable_dimension": dimension,
                    "rubric_item_sha256": item["rubric_item_sha256"],
                    "status": status,
                    "evidence_locus": {"kind": "video_time_range", "start_ms": 0, "end_ms": 1000},
                })
                self.assertIn(expected_error, checker.validate_atomic_annotation(partial, self.benchmark_snapshot))

    def test_adjudication_failed_generation_and_low_confidence_are_visible(self) -> None:
        annotations = checker.synthetic_annotation_matrix(self.annotation, self.benchmark_snapshot)
        disputed = copy.deepcopy(annotations)
        disputed[0]["status"] = "fail"
        adjudicator = copy.deepcopy(disputed[0])
        adjudicator["annotation_id"] = "ann_01_001_adjudicator"
        adjudicator["reviewer"] = {
            **copy.deepcopy(self.benchmark["reviewers"]["adjudicator"]),
            "reviewed_on": self.benchmark["evaluated_on"],
            "review_method": "human_observation",
        }
        adjudicator["status"] = "pass"
        disputed.append(adjudicator)
        adjudicated_report, adjudicated_errors = checker.aggregate_output_reviews(
            self.benchmark_snapshot, disputed
        )
        self.assertEqual(adjudicated_errors, [])
        self.assertEqual(adjudicated_report["disagreement_count"], 1)
        self.assertEqual(adjudicated_report["condition_verdict"], "pass")

        low = copy.deepcopy(annotations)
        low[0]["confidence"] = "low"
        low_report, low_errors = checker.aggregate_output_reviews(self.benchmark_snapshot, low)
        self.assertEqual(low_errors, [])
        self.assertEqual(low_report["confidence_counts"]["low"], 1)

        failed_manifest = copy.deepcopy(self.benchmark)
        failed_manifest["is_synthetic_fixture"] = False
        for attempt_row in failed_manifest["attempts"]:
            attempt_row["attempt_status"] = "returned"
        failed_attempt = failed_manifest["attempts"][-1]
        failed_attempt["attempt_status"] = "failed"
        for field in (
            "output_id",
            "output_media_sha256",
            "media_kind",
            "media_metadata_sha256",
            "duration_ms",
            "frame_count",
            "audio_present",
        ):
            failed_attempt[field] = None
        failed_attempt["failure_record_sha256"] = "f" * 64
        failed_snapshot = checker.snapshot_from_value(failed_manifest)
        failed_template = copy.deepcopy(self.annotation)
        failed_template["is_synthetic_fixture"] = False
        failed_annotations = checker.synthetic_annotation_matrix(failed_template, failed_snapshot)
        failed_report, failed_errors = checker.aggregate_output_reviews(failed_snapshot, failed_annotations)
        self.assertEqual(failed_errors, [])
        self.assertEqual(failed_report["failed_generation_attempt_count"], 1)
        self.assertEqual(failed_report["condition_verdict"], "fail")

    def test_wrong_json_types_return_controlled_errors(self) -> None:
        benchmark_cases = []
        for path, value in (
            (("operation", "operation_kind"), []),
            (("attempts", 0, "attempt_status"), {}),
            (("attempts", 0, "media_kind"), []),
        ):
            candidate = copy.deepcopy(self.benchmark)
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            benchmark_cases.append(candidate)
        for candidate in benchmark_cases:
            self.assertTrue(checker.validate_benchmark_manifest(candidate))

        for field, value in (
            ("observable_dimension", []),
            ("status", {}),
            ("confidence", []),
        ):
            candidate = copy.deepcopy(self.annotation)
            candidate[field] = value
            self.assertTrue(checker.validate_atomic_annotation(candidate, self.benchmark_snapshot))
        reviewer = copy.deepcopy(self.annotation)
        reviewer["reviewer"]["role"] = []
        self.assertTrue(checker.validate_atomic_annotation(reviewer, self.benchmark_snapshot))
        self.assertEqual(
            checker.validate_atomic_annotation(self.annotation, self.benchmark),
            ["annotation.manifest_snapshot"],
        )

    def test_external_review_cli_emits_redacted_provenance_report(self) -> None:
        annotations = checker.synthetic_annotation_matrix(self.annotation, self.benchmark_snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            annotation_path = Path(temporary) / "annotations.json"
            annotation_path.write_text(json.dumps(annotations, sort_keys=True), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(CHECKER),
                    "--review-benchmark",
                    str(self.benchmark_path),
                    "--review-annotations",
                    str(annotation_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["validation_errors"], [])
        self.assertEqual(report["benchmark_manifest_sha256"], self.benchmark_sha256)
        self.assertEqual(report["condition_verdict"], "pass")
        self.assertIs(report["release_pass"], False)
        self.assertNotIn(str(self.benchmark_path), result.stdout)

    def test_external_review_cli_rejects_symlink_inputs(self) -> None:
        annotations = checker.synthetic_annotation_matrix(self.annotation, self.benchmark_snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            annotation_path = root / "annotations.json"
            annotation_path.write_text(json.dumps(annotations, sort_keys=True), encoding="utf-8")
            benchmark_link = root / "benchmark-link.json"
            annotations_link = root / "annotations-link.json"
            try:
                benchmark_link.symlink_to(self.benchmark_path)
                annotations_link.symlink_to(annotation_path)
            except OSError:
                self.skipTest("symlinks are not available")
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(CHECKER),
                    "--review-benchmark",
                    str(benchmark_link),
                    "--review-annotations",
                    str(annotations_link),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["condition_verdict"], "incomplete")
        self.assertIs(report["release_pass"], False)

    def test_external_review_cli_preserves_known_failure_with_review_errors(self) -> None:
        manifest = copy.deepcopy(self.benchmark)
        manifest["is_synthetic_fixture"] = False
        for attempt in manifest["attempts"]:
            attempt["attempt_status"] = "returned"
        failed_attempt = manifest["attempts"][-1]
        failed_attempt["attempt_status"] = "failed"
        for field in (
            "output_id",
            "output_media_sha256",
            "media_kind",
            "media_metadata_sha256",
            "duration_ms",
            "frame_count",
            "audio_present",
        ):
            failed_attempt[field] = None
        failed_attempt["failure_record_sha256"] = "f" * 64
        snapshot = checker.snapshot_from_value(manifest)
        template = copy.deepcopy(self.annotation)
        template["is_synthetic_fixture"] = False
        annotations = checker.synthetic_annotation_matrix(template, snapshot)[:-1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            benchmark_path = root / "benchmark.json"
            annotations_path = root / "annotations.json"
            benchmark_path.write_bytes(snapshot.raw)
            annotations_path.write_text(json.dumps(annotations, sort_keys=True), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    str(CHECKER),
                    "--review-benchmark",
                    str(benchmark_path),
                    "--review-annotations",
                    str(annotations_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["condition_verdict"], "fail")
        self.assertIn("aggregate.missing_primary_or_secondary", report["validation_errors"])

    def test_oracles_are_bound_to_exact_test_or_case_ids(self) -> None:
        for relation in self.program["metamorphic_relations"]:  # type: ignore[index]
            self.assertIsNotNone(checker._safe_repo_file(ROOT, relation["oracle_path"]))
        candidate = copy.deepcopy(self.program)
        candidate["metamorphic_relations"][0]["oracle_ids"] = ["test_nonexistent_oracle"]
        errors = checker.validate_program(candidate, ROOT)
        self.assertIn("metamorphic.surface_swap_preserves_semantics.oracle_ids", errors)
        self.assertIn("metamorphic.surface_swap_preserves_semantics.oracle_unbound", errors)

    def test_plan_supplied_paths_are_never_executed_or_allowed_to_escape(self) -> None:
        self.assertIsNone(checker._safe_repo_file(ROOT, "../outside"))
        self.assertIsNone(checker._safe_repo_file(ROOT, "/tmp/outside"))
        self.assertIsNone(checker._safe_repo_file(ROOT, "scripts\\evaluation_program_check.py"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            try:
                (root / "tests" / "link.py").symlink_to(CHECKER)
            except OSError:
                self.skipTest("symlinks are not available")
            self.assertIsNone(checker._safe_repo_file(root, "tests/link.py"))

            source = root / "tests" / "source.py"
            source.write_text("pass\n", encoding="utf-8")
            hardlink = root / "tests" / "hardlink.py"
            try:
                os.link(source, hardlink)
            except OSError:
                self.skipTest("hard links are not available")
            self.assertIsNone(checker._safe_repo_file(root, "tests/source.py"))
            self.assertIsNone(checker._safe_repo_file(root, "tests/hardlink.py"))

    def test_strict_json_rejects_duplicates_nonfinite_bom_and_oversize(self) -> None:
        payloads = (
            b'{"a":1,"a":2}',
            b'{"a":NaN}',
            b'{"a":1e999}',
            b"\xef\xbb\xbf{}",
            b"[" * (checker.MAX_JSON_DEPTH + 2) + b"0" + b"]" * (checker.MAX_JSON_DEPTH + 2),
            b" " * (checker.MAX_JSON_BYTES + 1),
        )
        for index, payload in enumerate(payloads):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "value.json"
                path.write_bytes(payload)
                with self.assertRaises((ValueError, UnicodeError)):
                    checker.strict_load_json(path)

    def test_stable_snapshot_handles_distinct_path_and_descriptor_stat_views(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "value.json"
            path.write_text("{}\n", encoding="utf-8")
            real_lstat = Path.lstat

            def stat_view(metadata: os.stat_result, **overrides: int) -> SimpleNamespace:
                fields = {
                    "st_mode": metadata.st_mode,
                    "st_nlink": metadata.st_nlink,
                    "st_dev": metadata.st_dev,
                    "st_ino": metadata.st_ino,
                    "st_size": metadata.st_size,
                    "st_mtime_ns": metadata.st_mtime_ns,
                    "st_ctime_ns": metadata.st_ctime_ns,
                    "st_file_attributes": getattr(metadata, "st_file_attributes", 0),
                }
                fields.update(overrides)
                return SimpleNamespace(**fields)

            def windows_lstat(candidate: Path) -> SimpleNamespace | os.stat_result:
                metadata = real_lstat(candidate)
                if candidate == path:
                    return stat_view(metadata, st_mode=metadata.st_mode ^ stat.S_IWUSR)
                return metadata

            with mock.patch.object(Path, "lstat", windows_lstat):
                self.assertEqual(checker.strict_load_json(path), {})

            calls = 0

            def changing_lstat(candidate: Path) -> SimpleNamespace | os.stat_result:
                nonlocal calls
                metadata = real_lstat(candidate)
                if candidate != path:
                    return metadata
                calls += 1
                return stat_view(metadata, st_size=metadata.st_size + int(calls > 1))

            with mock.patch.object(Path, "lstat", changing_lstat), self.assertRaisesRegex(
                ValueError, "file changed during read"
            ):
                checker.strict_load_json(path)

    def test_manifest_snapshot_cannot_detach_value_or_digest_from_raw_bytes(self) -> None:
        with self.assertRaises(TypeError):
            class ForgedSnapshot(checker.JsonSnapshot):
                @property
                def value(self) -> object:
                    return {"benchmark_id": "forged_benchmark"}

                @property
                def sha256(self) -> str:
                    return "f" * 64

        snapshot = checker.strict_load_snapshot(self.benchmark_path)
        original_digest = snapshot.sha256
        detached_value = snapshot.value
        detached_value["benchmark_id"] = "forged_benchmark"
        self.assertEqual(snapshot.value["benchmark_id"], self.benchmark["benchmark_id"])
        self.assertEqual(snapshot.sha256, original_digest)
        for field, value in (
            ("raw", b"{}"),
            ("value", {}),
            ("sha256", "f" * 64),
            ("_JsonSnapshot__raw", b"{}"),
        ):
            with self.subTest(field=field), self.assertRaises(AttributeError):
                setattr(snapshot, field, value)
        annotations = checker.synthetic_annotation_matrix(self.annotation, snapshot)
        report, errors = checker.aggregate_output_reviews(snapshot, annotations)
        self.assertEqual(errors, [])
        self.assertEqual(report["benchmark_id"], self.benchmark["benchmark_id"])
        self.assertEqual(report["benchmark_manifest_sha256"], original_digest)

    def test_cli_summary_is_canonical_and_deterministic_across_hash_seeds(self) -> None:
        outputs: list[str] = []
        for seed in ("0", "1", "8675309"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = seed
            result = subprocess.run(
                [sys.executable, "-S", "-B", str(CHECKER), "--self-test", "--json"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(len(set(outputs)), 1)
        report = json.loads(outputs[0])
        self.assertEqual(report["network_calls"], 0)
        self.assertIs(report["release_gate"], False)
        self.assertIs(report["quality_claims_allowed"], False)
        self.assertEqual(report["program_mutations"]["detection_rate"], 1.0)
        self.assertEqual(report["output_review_mutations"]["detection_rate"], 1.0)
        self.assertEqual(report["aggregation_probes_passed"], 4)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_program_schema_accepts_fixture_and_rejects_release_mutations(self) -> None:
        schema = load_json(ROOT / "schemas" / "evaluation-program-v1.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual(list(validator.iter_errors(self.program)), [])
        for field, value in (
            ("network_policy", "allowed"),
            ("release_gate", True),
            ("quality_claims_allowed", True),
            ("status", "release"),
        ):
            with self.subTest(field=field):
                candidate = copy.deepcopy(self.program)
                candidate[field] = value
                self.assertTrue(list(validator.iter_errors(candidate)))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_output_contract_schemas_accept_only_closed_fixtures(self) -> None:
        for schema_name, fixture in (
            ("benchmark-manifest-v1.schema.json", self.benchmark),
            ("atomic-output-annotation-v1.schema.json", self.annotation),
        ):
            with self.subTest(schema=schema_name):
                schema = load_json(ROOT / "schemas" / schema_name)
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema, format_checker=FormatChecker())
                self.assertEqual(list(validator.iter_errors(fixture)), [])

        annotation_schema = load_json(ROOT / "schemas" / "atomic-output-annotation-v1.schema.json")
        annotation_validator = Draft202012Validator(annotation_schema, format_checker=FormatChecker())
        still = copy.deepcopy(self.annotation)
        still.update({
            "evidence_asset_kind": "derived_final_frame",
            "evidence_asset_sha256": "10467e3558cff078bb98ac3363164bc1d4dce469ab4d5660503f55fd0d082361",
            "derivation_record_sha256": "e136aa019a233120a713b40be72eaf97599ff393720344c27eba34647b5f4bbd",
            "evidence_locus": {"kind": "single_frame", "frame_index": 119},
        })
        for status in ("pass", "fail"):
            with self.subTest(status=status):
                still["status"] = status
                self.assertTrue(list(annotation_validator.iter_errors(still)))


if __name__ == "__main__":
    unittest.main()
