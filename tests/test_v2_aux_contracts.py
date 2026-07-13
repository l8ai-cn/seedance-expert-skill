from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from scripts import project_state_v2_check as state_v2
from scripts import v2_aux_check as aux
from tests.test_project_state_v2 import accepted_video_continuation


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "v2_aux_check.py"
SHA = "a" * 64


def load_json(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def run_checker(document: dict[str, object], seed: int = 0) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = str(seed)
    return subprocess.run(
        [sys.executable, "-S", "-B", str(CHECKER)],
        cwd=ROOT,
        input=json.dumps(document, sort_keys=True),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def canonical_sha256(value: object) -> str:
    return aux.canonical_sha256(value)


class ContractCase(unittest.TestCase):
    schema_path: str
    fixture_path: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_json(cls.schema_path)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())
        cls.fixture = load_json(cls.fixture_path)

    def assert_valid(self, instance: dict[str, object]) -> None:
        errors = sorted(
            self.validator.iter_errors(instance),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        self.assertEqual(errors, [])

    def assert_invalid(self, instance: dict[str, object]) -> None:
        self.assertTrue(list(self.validator.iter_errors(instance)), instance)


class TakeReviewV2ContractTests(ContractCase):
    schema_path = "schemas/take-review-v2.schema.json"
    fixture_path = "validation/fixtures/take-review-v2.valid.json"

    def test_positive_fixture(self) -> None:
        self.assert_valid(copy.deepcopy(self.fixture))

    def test_final_accept_requires_matching_terminal_status_media_and_digest(self) -> None:
        for field, value in (
            ("source_status", "reviewed"),
            ("accepted_media_sha256", None),
            ("media_kind", "user_description"),
            ("media_kind", "legacy_description"),
            ("requires_user_confirmation", True),
        ):
            with self.subTest(field=field, value=value):
                instance = copy.deepcopy(self.fixture)
                instance[field] = value
                self.assert_invalid(instance)

    def test_pending_confirmation_is_nonterminal_and_unaccepted(self) -> None:
        pending = copy.deepcopy(self.fixture)
        pending.update({
            "decision_status": "pending_confirmation",
            "source_status": "reviewed",
            "accepted_media_sha256": None,
            "requires_user_confirmation": True,
        })
        pending["endpoint_states"][0]["completion_mode"] = "unknown"
        self.assert_valid(pending)

        for field, value in (
            ("source_status", "accepted"),
            ("accepted_media_sha256", SHA),
            ("requires_user_confirmation", False),
        ):
            with self.subTest(field=field):
                contradiction = copy.deepcopy(pending)
                contradiction[field] = value
                self.assert_invalid(contradiction)

    def test_unknown_or_incomplete_endpoint_cannot_be_terminally_accepted(self) -> None:
        for completion_mode in ("unknown", "incomplete"):
            with self.subTest(completion_mode=completion_mode):
                instance = copy.deepcopy(self.fixture)
                instance["endpoint_states"][0]["completion_mode"] = completion_mode
                self.assert_invalid(instance)

    def test_ordinary_final_accept_requires_clean_named_sets_and_known_confidence(self) -> None:
        for field, value in (
            ("observation_confidence", "unknown"),
            ("incomplete_beat_ids", ["beat_incomplete"]),
            ("unexpected_completed_beat_ids", ["beat_unexpected"]),
            ("continuity_break_ids", ["break_01"]),
            ("accepted_deviation_ids", ["deviation_01"]),
        ):
            with self.subTest(field=field):
                instance = copy.deepcopy(self.fixture)
                instance[field] = value
                self.assert_invalid(instance)

    def test_accept_with_deviation_is_explicitly_named(self) -> None:
        accepted = copy.deepcopy(self.fixture)
        accepted.update({
            "verdict": "accept_with_deviation",
            "source_status": "accepted_with_deviation",
            "accepted_deviation_ids": ["deviation_01"],
        })
        self.assert_valid(accepted)
        accepted["accepted_deviation_ids"] = []
        self.assert_invalid(accepted)

    def test_accept_with_deviation_cannot_leave_unresolved_facts(self) -> None:
        base = copy.deepcopy(self.fixture)
        base.update({
            "verdict": "accept_with_deviation",
            "source_status": "accepted_with_deviation",
            "accepted_deviation_ids": ["disposition_01"],
        })
        for field, value in (
            ("observation_confidence", "unknown"),
            ("incomplete_beat_ids", ["beat_incomplete"]),
            ("unexpected_completed_beat_ids", ["beat_unexpected"]),
            ("continuity_break_ids", ["break_01"]),
        ):
            with self.subTest(field=field):
                unresolved = copy.deepcopy(base)
                unresolved[field] = value
                self.assert_invalid(unresolved)

        pending = copy.deepcopy(base)
        pending.update({
            "decision_status": "pending_confirmation",
            "source_status": "reviewed",
            "accepted_media_sha256": None,
            "observation_confidence": "unknown",
            "incomplete_beat_ids": ["beat_incomplete"],
            "requires_user_confirmation": True,
        })
        self.assert_valid(pending)

    def test_repair_and_reject_are_coherent_and_do_not_accept_media(self) -> None:
        for verdict, status in (("repair", "repair"), ("reject", "rejected")):
            with self.subTest(verdict=verdict):
                coherent = copy.deepcopy(self.fixture)
                coherent.update({
                    "verdict": verdict,
                    "source_status": status,
                    "accepted_media_sha256": None,
                })
                self.assert_valid(coherent)
                coherent["accepted_media_sha256"] = SHA
                self.assert_invalid(coherent)

    def test_final_frame_cannot_establish_temporal_endpoint_modes(self) -> None:
        temporal = (
            "completed_with_motion",
            "dissipated_or_resolved",
            "frame_exit",
            "cyclic_phase_boundary",
            "open_handoff",
            "incomplete",
            "unknown",
        )
        for mode in temporal:
            with self.subTest(mode=mode):
                instance = copy.deepcopy(self.fixture)
                instance["media_kind"] = "final_frame"
                instance["observed_start_snapshot_sha256"] = None
                instance["endpoint_states"][0]["completion_mode"] = mode
                self.assert_invalid(instance)

        static = copy.deepcopy(self.fixture)
        static["media_kind"] = "final_frame"
        static["observed_start_snapshot_sha256"] = None
        static["endpoint_states"][0]["completion_mode"] = "held_static"
        self.assert_valid(static)

        pending = copy.deepcopy(static)
        pending.update({
            "decision_status": "pending_confirmation",
            "source_status": "reviewed",
            "accepted_media_sha256": None,
            "observation_confidence": "unknown",
            "requires_user_confirmation": True,
        })
        pending["endpoint_states"][0]["completion_mode"] = "frame_exit"
        self.assert_valid(pending)

    def test_media_kind_controls_observation_provenance_exactly(self) -> None:
        video = copy.deepcopy(self.fixture)
        video["observed_start_snapshot_sha256"] = None
        self.assert_invalid(video)

        frame = copy.deepcopy(self.fixture)
        frame["media_kind"] = "final_frame"
        frame["endpoint_states"][0]["completion_mode"] = "held_static"
        self.assert_invalid(frame)
        frame["observed_start_snapshot_sha256"] = None
        self.assert_valid(frame)

    def test_descriptions_can_be_reviewed_but_not_finally_accepted(self) -> None:
        for media_kind in ("user_description", "legacy_description"):
            with self.subTest(media_kind=media_kind):
                rejected = copy.deepcopy(self.fixture)
                rejected.update({
                    "media_kind": media_kind,
                    "verdict": "reject",
                    "source_status": "rejected",
                    "accepted_media_sha256": None,
                    "observed_start_snapshot_sha256": None,
                    "observed_end_snapshot_sha256": None,
                })
                self.assert_valid(rejected)
                rejected.update({
                    "verdict": "accept",
                    "source_status": "accepted",
                    "accepted_media_sha256": SHA,
                })
                self.assert_invalid(rejected)


class PromptSpecV2ContractTests(ContractCase):
    schema_path = "schemas/prompt-spec-v2.schema.json"
    fixture_path = "validation/fixtures/prompt-spec-v2.valid.json"

    def test_positive_fixture(self) -> None:
        self.assert_valid(copy.deepcopy(self.fixture))

    def accepted_parent(self, opening: str = "accepted_parent_video") -> dict[str, object]:
        instance = copy.deepcopy(self.fixture)
        instance.update({
            "sequence_relation": "seamless_continuation",
            "opening_source": opening,
            "parent_clip_id": "clip_parent_01",
            "observed_source_snapshot_sha256": SHA,
            "accepted_source_media_sha256": "b" * 64,
            "source_take_id": "take_parent_01",
            "source_take_review_sha256": "c" * 64,
        })
        return instance

    def test_planned_and_described_openings_forbid_all_accepted_source_provenance(self) -> None:
        provenance = (
            ("observed_source_snapshot_sha256", SHA),
            ("accepted_source_media_sha256", SHA),
            ("source_take_id", "take_parent_01"),
            ("source_take_review_sha256", SHA),
        )
        for opening in ("planned_start", "user_description", "legacy_description"):
            for field, value in provenance:
                with self.subTest(opening=opening, field=field):
                    instance = copy.deepcopy(self.fixture)
                    instance["opening_source"] = opening
                    instance[field] = value
                    self.assert_invalid(instance)

    def test_accepted_parent_requires_all_provenance_fields(self) -> None:
        fields = (
            "observed_source_snapshot_sha256",
            "accepted_source_media_sha256",
            "parent_clip_id",
            "source_take_id",
            "source_take_review_sha256",
        )
        for opening in ("accepted_parent_video", "accepted_parent_final_frame"):
            valid = self.accepted_parent(opening)
            self.assert_valid(valid)
            for field in fields:
                with self.subTest(opening=opening, missing=field):
                    invalid = copy.deepcopy(valid)
                    invalid[field] = None
                    self.assert_invalid(invalid)

        with_deviation = self.accepted_parent()
        with_deviation["source_accepted_deviation_ids"] = ["deviation_01"]
        self.assert_valid(with_deviation)

    def test_nonparent_openings_forbid_source_deviation_projection(self) -> None:
        for opening in ("planned_start", "user_description", "legacy_description"):
            with self.subTest(opening=opening):
                instance = copy.deepcopy(self.fixture)
                instance["opening_source"] = opening
                instance["source_accepted_deviation_ids"] = ["deviation_01"]
                self.assert_invalid(instance)
                self.assertTrue(any("AUX214_NONPARENT_DEVIATION" in error for error in aux.validate_document(instance)))

    def test_sequence_relation_and_opening_source_are_coherent(self) -> None:
        cases = (
            ("standalone", "accepted_parent_video"),
            ("sequence_first_clip", "accepted_parent_final_frame"),
            ("seamless_continuation", "planned_start"),
            ("bridge_between_known_states", "legacy_description"),
            ("repair_tail", "accepted_parent_final_frame"),
            ("reanchor_after_drift", "planned_start"),
            ("intentional_next_shot", "user_description"),
        )
        for relation, opening in cases:
            with self.subTest(relation=relation, opening=opening):
                instance = self.accepted_parent(opening) if opening.startswith("accepted_parent") else copy.deepcopy(self.fixture)
                instance.update({"sequence_relation": relation, "opening_source": opening})
                self.assert_invalid(instance)

        repair = self.accepted_parent("accepted_parent_video")
        repair["sequence_relation"] = "repair_tail"
        self.assert_valid(repair)

    def test_v7_08_fails_closed_without_exact_planning_artifacts(self) -> None:
        planning_hashes = ("reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256")
        for field in planning_hashes:
            with self.subTest(status="planning_required", field=field):
                instance = copy.deepcopy(self.fixture)
                instance[field] = SHA
                self.assert_invalid(instance)

        planned = copy.deepcopy(self.fixture)
        planned.update({
            "planning_status": "planned",
            "reference_manifest_sha256": SHA,
            "scene_ir_sha256": "b" * 64,
            "planning_report_sha256": "c" * 64,
        })
        self.assert_invalid(planned)
        self.assertTrue(any("AUX208_PLANNED_ARTIFACTS_UNVERIFIED" in error for error in aux.validate_document(planned)))

    def test_status_and_nonsemantic_fields_are_closed(self) -> None:
        instance = copy.deepcopy(self.fixture)
        instance["status"] = "compiled"
        self.assert_invalid(instance)
        for field in ("prompt", "prompt_render_sha256", "provider", "provider_handle"):
            with self.subTest(field=field):
                instance = copy.deepcopy(self.fixture)
                instance[field] = "must-not-enter-v2-state"
                self.assert_invalid(instance)


class GenerationRunV2ContractTests(ContractCase):
    schema_path = "schemas/generation-run-v2.schema.json"
    fixture_path = "validation/fixtures/generation-run-v2.valid.json"

    def test_positive_fixture_and_dependency_free_dispatch(self) -> None:
        instance = copy.deepcopy(self.fixture)
        self.assert_valid(instance)
        result = run_checker(instance)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_project_and_prompt_bindings_are_required(self) -> None:
        for field in ("project_state_sha256", "prompt_spec_id", "prompt_spec_sha256"):
            with self.subTest(field=field):
                instance = copy.deepcopy(self.fixture)
                instance.pop(field)
                self.assert_invalid(instance)
                self.assertTrue(aux.validate_document(instance))

    def test_execution_provider_and_result_claims_are_closed(self) -> None:
        for field, value in (
            ("execution_status", "submitted"),
            ("result_status", "succeeded"),
            ("is_synthetic_fixture", False),
            ("provider", "unverified-provider"),
            ("output_url", "https://invalid.example/output"),
            ("prompt", "must-not-exist"),
        ):
            with self.subTest(field=field):
                instance = copy.deepcopy(self.fixture)
                instance[field] = value
                self.assert_invalid(instance)
                self.assertTrue(aux.validate_document(instance))

    def test_execution_status_and_block_reason_cross_product_is_coherent(self) -> None:
        allowed = {
            ("compile_required", "v2_compiler_not_available"),
            ("blocked", "planning_required"),
            ("blocked", "migration_review_required"),
        }
        for execution_status in ("compile_required", "blocked"):
            for block_reason in ("v2_compiler_not_available", "planning_required", "migration_review_required"):
                with self.subTest(execution_status=execution_status, block_reason=block_reason):
                    instance = copy.deepcopy(self.fixture)
                    instance.update({"execution_status": execution_status, "block_reason": block_reason})
                    if (execution_status, block_reason) in allowed:
                        self.assert_valid(instance)
                        self.assertEqual(aux.validate_document(instance), [])
                    else:
                        self.assert_invalid(instance)
                        self.assertTrue(any("AUX303_RUN_REASON_PAIR" in error for error in aux.validate_document(instance)))


class V2AuxSchemaStructureTests(unittest.TestCase):
    def test_every_conditional_has_explicit_discriminators(self) -> None:
        for schema_path in (
            "schemas/take-review-v2.schema.json",
            "schemas/prompt-spec-v2.schema.json",
            "schemas/generation-run-v2.schema.json",
        ):
            schema = load_json(schema_path)
            stack: list[object] = [schema]
            found = 0
            while stack:
                current = stack.pop()
                if isinstance(current, dict):
                    if "if" in current:
                        found += 1
                        self.assertIsInstance(current["if"], dict)
                        self.assertTrue(current["if"].get("required"), schema_path)
                    stack.extend(current.values())
                elif isinstance(current, list):
                    stack.extend(current)
            if schema_path != "schemas/generation-run-v2.schema.json":
                self.assertGreater(found, 0)

    def test_strict_schema_check_is_deterministic(self) -> None:
        mappings = [
            {"schema": "schemas/take-review-v2.schema.json", "instances": ["validation/fixtures/take-review-v2.valid.json"]},
            {"schema": "schemas/prompt-spec-v2.schema.json", "instances": ["validation/fixtures/prompt-spec-v2.valid.json"]},
            {"schema": "schemas/generation-run-v2.schema.json", "instances": ["validation/fixtures/generation-run-v2.valid.json"]},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            isolated_root = Path(temporary)
            for relative in (
                "schemas/take-review-v2.schema.json",
                "schemas/prompt-spec-v2.schema.json",
                "validation/fixtures/take-review-v2.valid.json",
                "validation/fixtures/prompt-spec-v2.valid.json",
                "schemas/generation-run-v2.schema.json",
                "validation/fixtures/generation-run-v2.valid.json",
            ):
                destination = isolated_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
            manifest = isolated_root / "validation" / "schema-instances.json"
            manifest.write_text(json.dumps({"schema_version": 1, "mappings": mappings}), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts" / "schema_check.py"), str(isolated_root), "--strict"]
            results = [subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False) for _ in range(2)]
        self.assertEqual(results[0].returncode, 0, results[0].stdout + results[0].stderr)
        self.assertEqual(
            (results[0].returncode, results[0].stdout, results[0].stderr),
            (results[1].returncode, results[1].stdout, results[1].stderr),
        )


class V2AuxSchemaCheckerParityTests(unittest.TestCase):
    def test_schema_invalid_mutation_corpus_never_passes_dependency_free_checker(self) -> None:
        contracts = (
            ("schemas/take-review-v2.schema.json", "validation/fixtures/take-review-v2.valid.json"),
            ("schemas/prompt-spec-v2.schema.json", "validation/fixtures/prompt-spec-v2.valid.json"),
            ("schemas/generation-run-v2.schema.json", "validation/fixtures/generation-run-v2.valid.json"),
        )
        wrong_values: tuple[object, ...] = (None, {}, [], "", True, -1)
        checked = 0
        for schema_path, fixture_path in contracts:
            schema = load_json(schema_path)
            fixture = load_json(fixture_path)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            candidates: list[dict[str, object]] = []
            for field in fixture:
                missing = copy.deepcopy(fixture)
                missing.pop(field)
                candidates.append(missing)
                for wrong in wrong_values:
                    mutated = copy.deepcopy(fixture)
                    mutated[field] = copy.deepcopy(wrong)
                    candidates.append(mutated)
            extra = copy.deepcopy(fixture)
            extra["schema_parity_unknown"] = True
            candidates.append(extra)
            if fixture_path.endswith("take-review-v2.valid.json"):
                nested_extra = copy.deepcopy(fixture)
                nested_extra["endpoint_states"][0]["unknown"] = True
                candidates.append(nested_extra)
                too_many = copy.deepcopy(fixture)
                too_many["uncertainties"] = ["bounded"] * 129
                candidates.append(too_many)
            for candidate in candidates:
                if not list(validator.iter_errors(candidate)):
                    continue
                checked += 1
                errors = aux.validate_document(candidate)
                with self.subTest(schema=schema_path, ordinal=checked):
                    self.assertTrue(errors, candidate)
                    if candidate.get("$schema") == fixture.get("$schema"):
                        self.assertTrue(any(error.startswith("AUX020_SCHEMA_CONTRACT") for error in errors), errors)
        self.assertGreaterEqual(checked, 300)

    def test_nested_bounds_patterns_and_conditionals_have_checker_parity(self) -> None:
        take_schema = load_json("schemas/take-review-v2.schema.json")
        prompt_schema = load_json("schemas/prompt-spec-v2.schema.json")
        take = load_json("validation/fixtures/take-review-v2.valid.json")
        prompt = load_json("validation/fixtures/prompt-spec-v2.valid.json")
        cases: list[tuple[dict[str, object], dict[str, object]]] = []

        for field in ("endpoint_id", "owner_kind", "owner_id", "completion_mode", "carry_forward", "description"):
            mutated = copy.deepcopy(take)
            mutated["endpoint_states"][0].pop(field)
            cases.append((take_schema, mutated))
        for field, value in (
            ("endpoint_id", "UPPERCASE"),
            ("owner_kind", "invalid_owner"),
            ("completion_mode", "invalid_mode"),
            ("description", ""),
            ("description", "x" * 2001),
        ):
            mutated = copy.deepcopy(take)
            mutated["endpoint_states"][0][field] = value
            cases.append((take_schema, mutated))
        endpoint_extra = copy.deepcopy(take)
        endpoint_extra["endpoint_states"][0]["extra"] = True
        cases.append((take_schema, endpoint_extra))
        duplicate_ids = copy.deepcopy(take)
        duplicate_ids["completed_beat_ids"] = ["beat_hold", "beat_hold"]
        cases.append((take_schema, duplicate_ids))
        too_many_endpoints = copy.deepcopy(take)
        too_many_endpoints["endpoint_states"] = [copy.deepcopy(take["endpoint_states"][0]) for _ in range(513)]
        cases.append((take_schema, too_many_endpoints))
        frame_overclaim = copy.deepcopy(take)
        frame_overclaim["media_kind"] = "final_frame"
        cases.append((take_schema, frame_overclaim))

        accepted_parent = copy.deepcopy(prompt)
        accepted_parent.update({
            "sequence_relation": "seamless_continuation",
            "opening_source": "accepted_parent_video",
            "parent_clip_id": "clip_parent",
            "observed_source_snapshot_sha256": SHA,
            "accepted_source_media_sha256": "b" * 64,
            "source_take_id": "take_parent",
            "source_take_review_sha256": "c" * 64,
        })
        for field in (
            "parent_clip_id", "observed_source_snapshot_sha256", "accepted_source_media_sha256",
            "source_take_id", "source_take_review_sha256",
        ):
            mutated = copy.deepcopy(accepted_parent)
            mutated[field] = None
            cases.append((prompt_schema, mutated))
        relation_mismatch = copy.deepcopy(prompt)
        relation_mismatch["sequence_relation"] = "repair_tail"
        cases.append((prompt_schema, relation_mismatch))
        partial_planning = copy.deepcopy(prompt)
        partial_planning["planning_status"] = "planned"
        partial_planning["reference_manifest_sha256"] = SHA
        cases.append((prompt_schema, partial_planning))

        for index, (schema, candidate) in enumerate(cases):
            with self.subTest(index=index):
                self.assertTrue(list(Draft202012Validator(schema).iter_errors(candidate)))
                errors = aux.validate_document(candidate)
                self.assertTrue(any(error.startswith("AUX020_SCHEMA_CONTRACT") for error in errors), errors)

    def test_positive_fixtures_pass_both_schema_and_dependency_free_contract_layer(self) -> None:
        for schema_path, fixture_path in (
            ("schemas/take-review-v2.schema.json", "validation/fixtures/take-review-v2.valid.json"),
            ("schemas/prompt-spec-v2.schema.json", "validation/fixtures/prompt-spec-v2.valid.json"),
            ("schemas/generation-run-v2.schema.json", "validation/fixtures/generation-run-v2.valid.json"),
        ):
            schema = load_json(schema_path)
            fixture = load_json(fixture_path)
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(fixture)), [])
            self.assertTrue(aux.schema_contract_valid(fixture), schema_path)
            self.assertEqual(aux.validate_document(fixture), [], schema_path)


class V2AuxCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.take = load_json("validation/fixtures/take-review-v2.valid.json")
        self.prompt = load_json("validation/fixtures/prompt-spec-v2.valid.json")
        self.run = load_json("validation/fixtures/generation-run-v2.valid.json")

    def assert_checker_code(self, document: dict[str, object], code: str) -> None:
        result = run_checker(document)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(code, result.stdout)

    def test_positive_fixtures_pass_dependency_free_stdin_dispatch(self) -> None:
        for document in (self.take, self.prompt, self.run):
            result = run_checker(document)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")

    def test_cross_set_beat_overlap_is_rejected(self) -> None:
        self.take["incomplete_beat_ids"] = list(self.take["completed_beat_ids"])
        self.assert_checker_code(self.take, "AUX100_BEAT_SET_OVERLAP")

    def test_duplicate_endpoint_ids_and_owners_are_rejected(self) -> None:
        duplicate_id = copy.deepcopy(self.take)
        second = copy.deepcopy(duplicate_id["endpoint_states"][0])
        second.update({"owner_kind": "camera", "owner_id": "camera"})
        duplicate_id["endpoint_states"].append(second)
        self.assert_checker_code(duplicate_id, "AUX101_ENDPOINT_ID_DUPLICATE")

        duplicate_owner = copy.deepcopy(self.take)
        second = copy.deepcopy(duplicate_owner["endpoint_states"][0])
        second["endpoint_id"] = "watch.endpoint.second"
        duplicate_owner["endpoint_states"].append(second)
        self.assert_checker_code(duplicate_owner, "AUX102_ENDPOINT_OWNER_DUPLICATE")

    def test_checker_rejects_semantic_contradictions_without_jsonschema(self) -> None:
        pending = copy.deepcopy(self.take)
        pending["decision_status"] = "pending_confirmation"
        self.assert_checker_code(pending, "AUX103_PENDING_RELATION")

        frame = copy.deepcopy(self.take)
        frame["media_kind"] = "final_frame"
        frame["endpoint_states"][0]["completion_mode"] = "open_handoff"
        self.assert_checker_code(frame, "AUX119_FRAME_TEMPORAL_CLAIM")

        false_parent = copy.deepcopy(self.prompt)
        false_parent["sequence_relation"] = "seamless_continuation"
        false_parent["opening_source"] = "accepted_parent_video"
        self.assert_checker_code(false_parent, "AUX203_ACCEPTED_SOURCE_PROVENANCE")

    def test_exact_schema_dispatch_and_diagnostics_do_not_echo_input(self) -> None:
        secret = "do-not-echo-sensitive-value"
        unknown = {"$schema": "https://invalid.example/" + secret, "payload": secret}
        result = run_checker(unknown)
        self.assertEqual(result.returncode, 1)
        self.assertIn("AUX009_SCHEMA_UNKNOWN", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_checker_output_is_deterministic(self) -> None:
        broken = copy.deepcopy(self.take)
        broken["requires_user_confirmation"] = True
        first = run_checker(broken, seed=1)
        second = run_checker(broken, seed=9)
        self.assertEqual((first.returncode, first.stdout, first.stderr), (second.returncode, second.stdout, second.stderr))

    def test_self_test_passes_ten_fresh_process_hash_seeds(self) -> None:
        outputs: list[tuple[int, str, str]] = []
        for seed in range(10):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = str(seed)
            result = subprocess.run(
                [sys.executable, "-S", "-B", str(CHECKER), "--self-test"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            outputs.append((result.returncode, result.stdout, result.stderr))
        self.assertTrue(all(output[0] == 0 for output in outputs), outputs)
        self.assertTrue(all(output == outputs[0] for output in outputs), outputs)

    def test_parser_is_bounded_and_non_echoing(self) -> None:
        secret = "parser-secret"
        result = subprocess.run(
            [sys.executable, "-S", "-B", str(CHECKER)],
            cwd=ROOT,
            input='{"payload":"' + secret + '","payload":"duplicate"}',
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("AUX004_DUPLICATE_KEY", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_structurally_wrong_semantic_values_fail_without_traceback(self) -> None:
        for document, field in ((copy.deepcopy(self.take), "decision_status"), (copy.deepcopy(self.prompt), "opening_source")):
            with self.subTest(field=field):
                document[field] = {"unhashable": ["value"]}
                result = run_checker(document)
                self.assertEqual(result.returncode, 1)
                self.assertIn("AUX011_SEMANTIC_TYPE", result.stdout)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_byte_and_depth_resource_limits_fail_closed(self) -> None:
        oversized = subprocess.run(
            [sys.executable, "-S", "-B", str(CHECKER)],
            cwd=ROOT,
            input=b" " * (2 * 1024 * 1024 + 1),
            capture_output=True,
            check=False,
        )
        self.assertEqual(oversized.returncode, 1)
        self.assertIn(b"AUX001_INPUT_TOO_LARGE", oversized.stdout)

        nested: object = None
        for _ in range(70):
            nested = [nested]
        nested = {"$schema": "invalid", "nested": nested}
        result = subprocess.run(
            [sys.executable, "-S", "-B", str(CHECKER)],
            cwd=ROOT,
            input=json.dumps(nested),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("AUX006_RESOURCE_LIMIT", result.stdout)


class V2AuxBundleTests(unittest.TestCase):
    def refresh_bundle_hashes(self, documents: list[dict[str, object]]) -> None:
        project = documents[0]
        prompt = documents[-2]
        run = documents[-1]
        project["semantic_state_sha256"] = state_v2.sha256_object({
            "project_id": project["project_id"],
            "state_revision": project["state_revision"],
            "canon_revision": project["canon_revision"],
            "semantic_state": project["semantic_state"],
        })
        prompt["semantic_state_sha256"] = project["semantic_state_sha256"]
        run.update({
            "semantic_state_sha256": project["semantic_state_sha256"],
            "project_state_sha256": canonical_sha256(project),
            "prompt_spec_sha256": canonical_sha256(prompt),
        })

    def standalone_bundle(self) -> list[dict[str, object]]:
        project = load_json("validation/fixtures/project-state-v2.valid.json")
        prompt = load_json("validation/fixtures/prompt-spec-v2.valid.json")
        run = load_json("validation/fixtures/generation-run-v2.valid.json")
        self.assertEqual(run["project_state_sha256"], canonical_sha256(project))
        self.assertEqual(run["prompt_spec_sha256"], canonical_sha256(prompt))
        return [project, prompt, run]

    def accepted_parent_bundle(self) -> list[dict[str, object]]:
        project = accepted_video_continuation()
        project["project_mode"] = "sequence_project"
        project["semantic_state"]["clips"][0]["sequence_relation"] = "sequence_first_clip"
        parent = project["semantic_state"]["clips"][0]
        child = project["semantic_state"]["clips"][1]
        child["status"] = "planned"
        observed = parent["observed_end_snapshot"]
        observed_start = copy.deepcopy(parent["planned_start_snapshot"])
        observed_start.update({
            "snapshot_id": "clip_01.observed_start_state",
            "basis": "observed",
            "source": copy.deepcopy(observed["source"]),
        })
        observed_start["motion_handoff"]["basis"] = "observed"
        observed_start["snapshot_sha256"] = state_v2.sha256_object({
            key: value for key, value in observed_start.items() if key != "snapshot_sha256"
        })
        parent["observed_start_snapshot"] = observed_start
        project["semantic_state"]["beats"][0]["status"] = "completed"
        project["semantic_state_sha256"] = state_v2.sha256_object({
            "project_id": project["project_id"],
            "state_revision": project["state_revision"],
            "canon_revision": project["canon_revision"],
            "semantic_state": project["semantic_state"],
        })

        review = load_json("validation/fixtures/take-review-v2.valid.json")
        review.update({
            "project_id": project["project_id"],
            "clip_id": parent["clip_id"],
            "take_id": observed["source"]["take_id"],
            "media_kind": "video",
            "accepted_media_sha256": observed["source"]["media_sha256"],
            "observed_start_snapshot_sha256": observed_start["snapshot_sha256"],
            "observed_end_snapshot_sha256": observed["snapshot_sha256"],
            "endpoint_states": copy.deepcopy(observed["endpoint_states"]),
            "completed_beat_ids": ["beat_hold"],
        })

        prompt = load_json("validation/fixtures/prompt-spec-v2.valid.json")
        prompt.update({
            "prompt_spec_id": "migration_watch.clip_02.spec_01",
            "clip_id": child["clip_id"],
            "semantic_state_sha256": project["semantic_state_sha256"],
            "sequence_relation": child["sequence_relation"],
            "opening_source": "accepted_parent_video",
            "parent_clip_id": parent["clip_id"],
            "planned_start_snapshot_sha256": child["planned_start_snapshot"]["snapshot_sha256"],
            "planned_end_snapshot_sha256": child["planned_end_snapshot"]["snapshot_sha256"],
            "observed_source_snapshot_sha256": observed["snapshot_sha256"],
            "accepted_source_media_sha256": observed["source"]["media_sha256"],
            "source_take_id": review["take_id"],
            "source_take_review_sha256": canonical_sha256(review),
            "endpoint_states_sha256": canonical_sha256(child["planned_end_snapshot"]["endpoint_states"]),
            "carry_forward_motion_bindings": [{
                "endpoint_id": observed["endpoint_states"][0]["endpoint_id"],
                "owner_kind": observed["endpoint_states"][0]["owner_kind"],
                "owner_id": observed["endpoint_states"][0]["owner_id"],
                "parent_motion_id": observed["motion_handoff"]["vectors"][0]["motion_id"],
                "opening_motion_id": child["planned_start_snapshot"]["motion_handoff"]["vectors"][0]["motion_id"],
            }],
            "completed_beat_ids": copy.deepcopy(child["already_happened"]),
            "reserved_future_beat_ids": copy.deepcopy(child["reserved_for_later"]),
            "continuity_rule_ids": [rule["rule_id"] for rule in child["continuity_rules"]],
            "motion_snapshot_sha256": canonical_sha256(child["planned_start_snapshot"]["motion_handoff"]),
            "reference_binding_ids": copy.deepcopy(child["planning_link"]["binding_ids"]),
            "planning_status": child["planning_link"]["status"],
            "reference_manifest_sha256": child["planning_link"]["reference_manifest_sha256"],
            "scene_ir_sha256": child["planning_link"]["scene_ir_sha256"],
            "planning_report_sha256": child["planning_link"]["planning_report_sha256"],
        })

        run = load_json("validation/fixtures/generation-run-v2.valid.json")
        run.update({
            "run_id": "fixture_migration_watch_clip_02",
            "clip_id": child["clip_id"],
            "semantic_state_sha256": project["semantic_state_sha256"],
            "project_state_sha256": canonical_sha256(project),
            "prompt_spec_id": prompt["prompt_spec_id"],
            "prompt_spec_sha256": canonical_sha256(prompt),
        })
        return [project, review, prompt, run]

    def test_standalone_and_accepted_parent_bundles_pass(self) -> None:
        for documents in (self.standalone_bundle(), self.accepted_parent_bundle()):
            with self.subTest(members=len(documents)):
                self.assertEqual(aux.verify_bundle(documents), [])
                with tempfile.TemporaryDirectory() as temporary:
                    paths = []
                    for index, document in enumerate(documents):
                        path = Path(temporary) / f"member-{index}.json"
                        path.write_bytes(aux.canonical_json(document))
                        paths.append(str(path))
                    result = subprocess.run(
                        [sys.executable, "-S", "-B", str(CHECKER), "--bundle", *paths],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generation_run_binds_exact_project_and_prompt_artifacts(self) -> None:
        for field, code in (("project_state_sha256", "AUX406"), ("prompt_spec_sha256", "AUX406"), ("prompt_spec_id", "AUX405")):
            with self.subTest(field=field):
                documents = self.standalone_bundle()
                documents[-1][field] = "wrong_id" if field == "prompt_spec_id" else SHA
                self.assertTrue(any(code in error for error in aux.verify_bundle(documents)))

    def test_generation_run_pair_is_derived_from_exact_project_readiness(self) -> None:
        for execution_status in ("compile_required", "blocked"):
            for block_reason in ("v2_compiler_not_available", "planning_required", "migration_review_required"):
                with self.subTest(execution_status=execution_status, block_reason=block_reason):
                    documents = self.standalone_bundle()
                    documents[-1].update({"execution_status": execution_status, "block_reason": block_reason})
                    errors = aux.verify_bundle(documents)
                    if (execution_status, block_reason) == ("blocked", "planning_required"):
                        self.assertEqual(errors, [])
                    else:
                        self.assertTrue(errors)

        migration = self.standalone_bundle()
        project, _prompt, run = migration
        project["semantic_state"]["clips"][0]["execution_readiness"] = "migration_review"
        run.update({"execution_status": "blocked", "block_reason": "migration_review_required"})
        self.refresh_bundle_hashes(migration)
        self.assertEqual(aux.verify_bundle(migration), [])

    def test_accepted_parent_review_bindings_fail_closed_independently(self) -> None:
        mutations = (
            (lambda docs: docs[2].__setitem__("source_take_review_sha256", SHA), "AUX412"),
            (lambda docs: docs[1].__setitem__("project_id", "other_project"), "AUX413"),
            (lambda docs: docs[1].__setitem__("clip_id", "other_clip"), "AUX413"),
            (lambda docs: docs[2].__setitem__("source_take_id", "other_take"), "AUX411"),
            (lambda docs: docs[2].__setitem__("opening_source", "accepted_parent_final_frame"), "AUX415"),
            (lambda docs: docs[2].__setitem__("accepted_source_media_sha256", SHA), "AUX415"),
            (lambda docs: docs[2].__setitem__("observed_source_snapshot_sha256", SHA), "AUX416"),
        )
        for mutate, code in mutations:
            with self.subTest(code=code):
                documents = self.accepted_parent_bundle()
                mutate(documents)
                errors = aux.verify_bundle(documents)
                self.assertTrue(any(code in error for error in errors), errors)

    def test_bundle_rejects_missing_or_unrelated_members(self) -> None:
        incomplete = self.standalone_bundle()[:-1]
        self.assertTrue(any("AUX400" in error for error in aux.verify_bundle(incomplete)))
        unrelated = self.standalone_bundle()
        unrelated.insert(1, load_json("validation/fixtures/take-review-v2.valid.json"))
        self.assertTrue(any("AUX419" in error for error in aux.verify_bundle(unrelated)))

    def test_h8_compound_same_owner_motion_is_exactly_one_to_one(self) -> None:
        documents = self.accepted_parent_bundle()
        project, review, prompt, run = documents
        parent = project["semantic_state"]["clips"][0]
        child = project["semantic_state"]["clips"][1]
        parent_vector = copy.deepcopy(parent["observed_end_snapshot"]["motion_handoff"]["vectors"][0])
        parent_vector.update({"motion_id": "watch.slide.secondary", "domain": "material"})
        opening_vector = copy.deepcopy(child["planned_start_snapshot"]["motion_handoff"]["vectors"][0])
        opening_vector.update({"motion_id": "watch.slide.secondary", "domain": "material"})
        parent["observed_end_snapshot"]["motion_handoff"]["vectors"].append(parent_vector)
        child["planned_start_snapshot"]["motion_handoff"]["vectors"].append(opening_vector)
        for snapshot in (parent["observed_end_snapshot"], child["planned_start_snapshot"]):
            snapshot["snapshot_sha256"] = state_v2.sha256_object({
                key: value for key, value in snapshot.items() if key != "snapshot_sha256"
            })
        review["observed_end_snapshot_sha256"] = parent["observed_end_snapshot"]["snapshot_sha256"]
        prompt.update({
            "observed_source_snapshot_sha256": review["observed_end_snapshot_sha256"],
            "source_take_review_sha256": canonical_sha256(review),
            "planned_start_snapshot_sha256": child["planned_start_snapshot"]["snapshot_sha256"],
            "motion_snapshot_sha256": canonical_sha256(child["planned_start_snapshot"]["motion_handoff"]),
        })
        prompt["carry_forward_motion_bindings"].append({
            "endpoint_id": parent["observed_end_snapshot"]["endpoint_states"][0]["endpoint_id"],
            "owner_kind": parent_vector["owner_kind"],
            "owner_id": parent_vector["owner_id"],
            "parent_motion_id": parent_vector["motion_id"],
            "opening_motion_id": opening_vector["motion_id"],
        })
        self.refresh_bundle_hashes(documents)
        run["prompt_spec_sha256"] = canonical_sha256(prompt)
        self.assertEqual(state_v2.validate_project_state(project), project)
        self.assertEqual(aux.verify_bundle(documents), [])

        omitted = copy.deepcopy(documents)
        omitted[-2]["carry_forward_motion_bindings"].pop()
        omitted[-1]["prompt_spec_sha256"] = canonical_sha256(omitted[-2])
        self.assertTrue(any("AUX433_CARRY_COVERAGE" in error for error in aux.verify_bundle(omitted)))

        many_to_one = copy.deepcopy(documents)
        many_to_one[-2]["carry_forward_motion_bindings"][1]["opening_motion_id"] = many_to_one[-2]["carry_forward_motion_bindings"][0]["opening_motion_id"]
        many_to_one[-1]["prompt_spec_sha256"] = canonical_sha256(many_to_one[-2])
        self.assertTrue(aux.verify_bundle(many_to_one))
        self.assertTrue(any("AUX211_OPENING_MOTION_DUPLICATE" in error for error in aux.validate_document(many_to_one[-2])))

        extra = copy.deepcopy(documents)
        extra[-2]["carry_forward_motion_bindings"].append({
            "endpoint_id": "watch.endpoint",
            "owner_kind": "product",
            "owner_id": "watch",
            "parent_motion_id": "watch.slide.extra",
            "opening_motion_id": "watch.slide.opening_extra",
        })
        extra[-2]["carry_forward_motion_bindings"].sort(
            key=lambda binding: (binding["endpoint_id"], binding["parent_motion_id"], binding["opening_motion_id"])
        )
        extra[-1]["prompt_spec_sha256"] = canonical_sha256(extra[-2])
        self.assertTrue(any("AUX429_PARENT_MOTION_BINDING" in error for error in aux.verify_bundle(extra)))

    def test_h8_does_not_derive_carry_from_child_planned_start_endpoints(self) -> None:
        documents = self.accepted_parent_bundle()
        project, _review, prompt, _run = documents
        parent = project["semantic_state"]["clips"][0]
        child = project["semantic_state"]["clips"][1]
        child["planned_start_snapshot"]["endpoint_states"] = [{
            "endpoint_id": "misleading.planned.endpoint",
            "owner_kind": "camera",
            "owner_id": "planned_camera",
            "completion_mode": "held_static",
            "carry_forward": False,
            "description": "A planned endpoint must not drive accepted-parent carry projection.",
        }]
        errors: set[str] = set()
        aux._verify_carry_projection(prompt, parent, child, errors)
        self.assertEqual(errors, set())

    def test_h9_rejects_noncurrent_or_nonplannable_target(self) -> None:
        documents = self.accepted_parent_bundle()
        project, _review, prompt, run = documents
        parent = project["semantic_state"]["clips"][0]
        prompt.update({
            "clip_id": parent["clip_id"],
            "sequence_relation": parent["sequence_relation"],
            "opening_source": "planned_start",
            "parent_clip_id": None,
            "planned_start_snapshot_sha256": parent["planned_start_snapshot"]["snapshot_sha256"],
            "planned_end_snapshot_sha256": parent["planned_end_snapshot"]["snapshot_sha256"],
            "observed_source_snapshot_sha256": None,
            "accepted_source_media_sha256": None,
            "source_take_id": None,
            "source_take_review_sha256": None,
            "carry_forward_motion_bindings": [],
            "endpoint_states_sha256": canonical_sha256(parent["planned_end_snapshot"]["endpoint_states"]),
            "motion_snapshot_sha256": canonical_sha256(parent["planned_start_snapshot"]["motion_handoff"]),
            "completed_beat_ids": copy.deepcopy(parent["already_happened"]),
            "reserved_future_beat_ids": copy.deepcopy(parent["reserved_for_later"]),
            "continuity_rule_ids": [rule["rule_id"] for rule in parent["continuity_rules"]],
        })
        run.update({"clip_id": parent["clip_id"], "prompt_spec_sha256": canonical_sha256(prompt)})
        errors = aux.verify_bundle([project, prompt, run])
        self.assertTrue(any("AUX407_CURRENT_CLIP_BINDING" in error for error in errors), errors)
        self.assertTrue(any("AUX408_TARGET_NOT_PLANNABLE" in error for error in errors), errors)

    def test_planned_project_link_fails_closed_without_artifact_bundle(self) -> None:
        documents = self.standalone_bundle()
        project, prompt, run = documents
        current = project["semantic_state"]["clips"][0]
        current["planning_link"].update({
            "status": "planned",
            "reference_manifest_sha256": SHA,
            "scene_ir_sha256": "b" * 64,
            "planning_report_sha256": "c" * 64,
            "resolved_binding_proofs": [{"binding_id": "product_ref", "media_sha256": SHA}],
        })
        project["semantic_state"]["reference_assets"][0].update({"status": "available", "media_sha256": SHA})
        current["execution_readiness"] = "compile_required"
        self.refresh_bundle_hashes(documents)
        run["prompt_spec_sha256"] = canonical_sha256(prompt)
        errors = aux.verify_bundle(documents)
        self.assertTrue(any("AUX422_PLANNED_ARTIFACT_BUNDLE_REQUIRED" in error for error in errors), errors)

    def test_review_observation_endpoints_and_beats_match_project_canon(self) -> None:
        endpoint_mismatch = self.accepted_parent_bundle()
        review = endpoint_mismatch[1]
        prompt = endpoint_mismatch[2]
        run = endpoint_mismatch[3]
        review["endpoint_states"][0].update({
            "completion_mode": "held_static",
            "carry_forward": False,
            "description": "A self-asserted endpoint must not replace project canon.",
        })
        prompt["source_take_review_sha256"] = canonical_sha256(review)
        run["prompt_spec_sha256"] = canonical_sha256(prompt)
        self.assertTrue(any("AUX436_REVIEW_ENDPOINT_BINDING" in error for error in aux.verify_bundle(endpoint_mismatch)))

        start_mismatch = self.accepted_parent_bundle()
        review = start_mismatch[1]
        prompt = start_mismatch[2]
        run = start_mismatch[3]
        review["observed_start_snapshot_sha256"] = start_mismatch[0]["semantic_state"]["clips"][0]["planned_start_snapshot"]["snapshot_sha256"]
        prompt["source_take_review_sha256"] = canonical_sha256(review)
        run["prompt_spec_sha256"] = canonical_sha256(prompt)
        self.assertTrue(any("AUX435_REVIEW_START_BINDING" in error for error in aux.verify_bundle(start_mismatch)))

        beat_mismatch = self.accepted_parent_bundle()
        review = beat_mismatch[1]
        prompt = beat_mismatch[2]
        run = beat_mismatch[3]
        review["completed_beat_ids"] = []
        prompt["source_take_review_sha256"] = canonical_sha256(review)
        run["prompt_spec_sha256"] = canonical_sha256(prompt)
        self.assertTrue(any("AUX437_REVIEW_BEAT_BINDING" in error for error in aux.verify_bundle(beat_mismatch)))

    def test_accepted_deviation_status_verdict_source_and_projection_cross_product(self) -> None:
        deviation = ["deviation_01"]
        accepted_count = 0
        rejected_count = 0
        for parent_status in ("accepted", "accepted_with_deviation"):
            for parent_has_ids in (False, True):
                for verdict in ("accept", "accept_with_deviation"):
                    for source_status in ("accepted", "accepted_with_deviation"):
                        for review_has_ids in (False, True):
                            for prompt_has_ids in (False, True):
                                documents = self.accepted_parent_bundle()
                                project, review, prompt, run = documents
                                parent = project["semantic_state"]["clips"][0]
                                parent.update({
                                    "status": parent_status,
                                    "accepted_deviation_ids": copy.deepcopy(deviation if parent_has_ids else []),
                                })
                                review.update({
                                    "verdict": verdict,
                                    "source_status": source_status,
                                    "accepted_deviation_ids": copy.deepcopy(deviation if review_has_ids else []),
                                })
                                prompt.update({
                                    "source_accepted_deviation_ids": copy.deepcopy(deviation if prompt_has_ids else []),
                                    "source_take_review_sha256": canonical_sha256(review),
                                })
                                self.refresh_bundle_hashes(documents)
                                run["prompt_spec_sha256"] = canonical_sha256(prompt)
                                should_pass = (
                                    parent_status == source_status
                                    and ((parent_status == "accepted" and verdict == "accept" and not parent_has_ids and not review_has_ids and not prompt_has_ids)
                                         or (parent_status == "accepted_with_deviation" and verdict == "accept_with_deviation" and parent_has_ids and review_has_ids and prompt_has_ids))
                                )
                                errors = aux.verify_bundle(documents)
                                with self.subTest(
                                    parent_status=parent_status,
                                    parent_has_ids=parent_has_ids,
                                    verdict=verdict,
                                    source_status=source_status,
                                    review_has_ids=review_has_ids,
                                    prompt_has_ids=prompt_has_ids,
                                ):
                                    if should_pass:
                                        accepted_count += 1
                                        self.assertEqual(errors, [])
                                    else:
                                        rejected_count += 1
                                        self.assertTrue(errors)
        self.assertEqual(accepted_count, 2)
        self.assertEqual(rejected_count, 62)


if __name__ == "__main__":
    unittest.main()
