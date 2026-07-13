from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from scripts import project_state_v2_check as state


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "validation" / "fixtures"


def fixture() -> dict:
    value = json.loads((FIXTURES / "project-state-v2.valid.json").read_text(encoding="utf-8"))
    for clip in value["semantic_state"]["clips"]:
        clip.setdefault("accepted_deviation_ids", [])
        clip["planning_link"].setdefault("resolved_binding_proofs", [])
    rehash_project(value)
    return value


def rehash_project(value: dict) -> None:
    value["semantic_state_sha256"] = state.sha256_object(
        {
            "project_id": value["project_id"],
            "state_revision": value["state_revision"],
            "canon_revision": value["canon_revision"],
            "semantic_state": value["semantic_state"],
        }
    )


def rehash_snapshot(snapshot: dict) -> None:
    snapshot["snapshot_sha256"] = state.sha256_object({key: item for key, item in snapshot.items() if key != "snapshot_sha256"})


def accepted_video_continuation() -> dict:
    value = fixture()
    value["project_mode"] = "sequence_project"
    parent = value["semantic_state"]["clips"][0]
    parent["status"] = "accepted"
    parent["sequence_relation"] = "sequence_first_clip"
    value["semantic_state"]["beats"][0]["status"] = "completed"
    observed = copy.deepcopy(parent["planned_end_snapshot"])
    observed["snapshot_id"] = "clip_01.observed_end_state"
    observed["basis"] = "observed"
    observed["source"] = {"kind": "accepted_video", "take_id": "take_01", "media_sha256": "1" * 64}
    observed["motion_handoff"] = {
        "basis": "observed",
        "vectors": [{
            "motion_id": "watch.slide", "owner_kind": "product", "owner_id": "watch", "domain": "subject",
            "coordinate_frame": "world", "description": "The watch continues sliding right.", "phase": "continuing",
            "direction": "right", "speed": "slow", "speed_trend": "constant", "continuity": "open",
            "observability": "observed_in_video", "source_kind": "accepted_video", "confidence": "high", "uncertainty": None,
        }],
    }
    observed["endpoint_states"] = [{"endpoint_id": "watch.endpoint", "owner_kind": "product", "owner_id": "watch", "completion_mode": "open_handoff", "carry_forward": True, "description": "The local beat ends while the watch continues sliding."}]
    observed["requires_confirmation"] = False
    observed["uncertainties"] = []
    rehash_snapshot(observed)
    parent["observed_end_snapshot"] = observed

    child = copy.deepcopy(parent)
    child.update({"clip_id": "clip_02", "parent_clip_id": "clip_01", "sequence_index": 2, "status": "planned", "sequence_relation": "seamless_continuation", "extension_depth": 1, "already_happened": ["beat_hold"], "this_clip_only": [], "observed_end_snapshot": None, "observed_start_snapshot": None})
    start = copy.deepcopy(observed)
    start["snapshot_id"] = "clip_02.planned_start_state"
    start["basis"] = "planned"
    start["source"] = {"kind": "project_plan", "take_id": None, "media_sha256": None}
    start["endpoint_states"] = []
    start["motion_handoff"]["basis"] = "planned"
    start["motion_handoff"]["vectors"][0]["observability"] = "planned"
    start["motion_handoff"]["vectors"][0]["source_kind"] = "project_plan"
    rehash_snapshot(start)
    child["planned_start_snapshot"] = start
    child["continuity_rules"] = [{"rule_id": "lock.watch", "atom_id": "watch.identity", "policy": "locked", "from_value_sha256": observed["state_atoms"][0]["value_sha256"], "to_value_sha256": start["state_atoms"][0]["value_sha256"], "scope": "next_clip", "reason": "Preserve the same watch identity."}]
    child["planning_link"]["binding_ids"] = ["product_ref"]
    value["semantic_state"]["clips"].append(child)
    value["semantic_state"]["scenes"][0]["assigned_clip_ids"].append("clip_02")
    value["semantic_state"]["current_clip_id"] = "clip_02"
    rehash_project(value)
    return value


class ProjectStateV2Tests(unittest.TestCase):
    def assert_state_error(self, value: dict, code: str) -> None:
        with self.assertRaises(state.StateV2Error) as caught:
            state.validate_project_state(value)
        self.assertEqual(caught.exception.code, code)

    def test_valid_fixture_and_dependency_free_cli(self) -> None:
        value = fixture()
        self.assertEqual(state.validate_project_state(value), value)
        result = subprocess.run(
            [sys.executable, "-S", "-B", "scripts/project_state_v2_check.py"],
            cwd=ROOT,
            input=state.canonical_json(value),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        malformed = fixture()
        malformed["semantic_state"]["clips"][0]["planned_start_snapshot"]["source"]["kind"] = {"secret": "must-not-echo"}
        rehash_snapshot(malformed["semantic_state"]["clips"][0]["planned_start_snapshot"])
        rehash_project(malformed)
        result = subprocess.run(
            [sys.executable, "-S", "-B", "scripts/project_state_v2_check.py"],
            cwd=ROOT,
            input=state.canonical_json(malformed),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertNotIn(b"must-not-echo", result.stderr)

    def test_self_parent_and_beat_cycle_fail(self) -> None:
        self_parent = fixture()
        clip = self_parent["semantic_state"]["clips"][0]
        clip["parent_clip_id"] = clip["clip_id"]
        clip["sequence_relation"] = "intentional_next_shot"
        rehash_project(self_parent)
        self.assert_state_error(self_parent, "STATE046_PARENT_INVALID")

        beat_cycle = fixture()
        beat_cycle["semantic_state"]["beats"][0]["dependencies"] = ["beat_hold"]
        rehash_project(beat_cycle)
        self.assert_state_error(beat_cycle, "STATE032_BEAT_CYCLE")

    def test_intentional_word_cannot_bypass_locked_change(self) -> None:
        base = fixture()["semantic_state"]["clips"][0]["planned_start_snapshot"]
        parent_snapshot = copy.deepcopy(base)
        child_snapshot = copy.deepcopy(base)
        child_snapshot["state_atoms"][0]["value"] = "different watch"
        child_snapshot["state_atoms"][0]["value_sha256"] = state.sha256_text("different watch")
        parent = {"observed_end_snapshot": parent_snapshot}
        child = {
            "planned_start_snapshot": child_snapshot,
            "continuity_rules": [
                {
                    "rule_id": "lock.watch",
                    "atom_id": "watch.identity",
                    "policy": "locked",
                    "from_value_sha256": parent_snapshot["state_atoms"][0]["value_sha256"],
                    "to_value_sha256": child_snapshot["state_atoms"][0]["value_sha256"],
                    "scope": "next_clip",
                    "reason": "intentional change",
                }
            ],
        }
        with self.assertRaises(state.StateV2Error) as caught:
            state._validate_continuity(parent, child, "/child")
        self.assertEqual(caught.exception.code, "STATE022_LOCKED_ATOM_CHANGED")

    def test_missing_atom_never_passes_a_lock(self) -> None:
        base = fixture()["semantic_state"]["clips"][0]["planned_start_snapshot"]
        parent = {"observed_end_snapshot": copy.deepcopy(base)}
        child_snapshot = copy.deepcopy(base)
        child_snapshot["state_atoms"] = []
        child = {"planned_start_snapshot": child_snapshot, "continuity_rules": []}
        with self.assertRaises(state.StateV2Error) as caught:
            state._validate_continuity(parent, child, "/child")
        self.assertEqual(caught.exception.code, "STATE019_CONTINUITY_RULE_COVERAGE_INCOMPLETE")

    def test_final_frame_cannot_claim_direction_or_speed(self) -> None:
        motion = {
            "basis": "observed",
            "vectors": [
                {
                    "motion_id": "hand.motion",
                    "owner_kind": "character",
                    "owner_id": "performer",
                    "domain": "subject",
                    "coordinate_frame": "screen",
                    "description": "The hand may still be moving.",
                    "phase": "continuing",
                    "direction": None,
                    "speed": None,
                    "speed_trend": "unknown",
                    "continuity": "unknown",
                    "observability": "inferred_from_frame",
                    "source_kind": "accepted_final_frame",
                    "confidence": "low",
                    "uncertainty": "A still cannot establish phase.",
                }
            ],
        }
        with self.assertRaises(state.StateV2Error) as caught:
            state._validate_motion(motion, "observed", "/motion", snapshot_source_kind="accepted_final_frame")
        self.assertEqual(caught.exception.code, "STATE008_FRAME_MOTION_OVERCLAIM")

    def test_observed_motion_can_mix_explicit_vector_sources(self) -> None:
        motion = {
            "basis": "observed",
            "vectors": [
                {"motion_id": "subject.move", "owner_kind": "character", "owner_id": "performer", "domain": "subject", "coordinate_frame": "world", "description": "The performer continues right.", "phase": "continuing", "direction": "right", "speed": "slow", "speed_trend": "constant", "continuity": "open", "observability": "observed_in_video", "source_kind": "accepted_video", "confidence": "high", "uncertainty": None},
                {"motion_id": "camera.move", "owner_kind": "camera", "owner_id": "camera_main", "domain": "camera", "coordinate_frame": "subject", "description": "The operator reports a continuing track.", "phase": "continuing", "direction": "right", "speed": "matched", "speed_trend": "constant", "continuity": "open", "observability": "user_attested", "source_kind": "user_description", "confidence": "medium", "uncertainty": "No camera telemetry is available."},
            ],
        }
        state._validate_motion(motion, "observed", "/motion", snapshot_source_kind="accepted_video")

    def test_endpoint_modes_cover_static_resolved_and_moving_completion(self) -> None:
        expected = {
            "held_static", "dissipated_or_resolved", "completed_with_motion",
            "frame_exit", "cyclic_phase_boundary", "open_handoff", "incomplete", "unknown",
        }
        self.assertEqual(state.COMPLETION_MODES, expected)

    def test_owner_endpoint_controls_carry_forward(self) -> None:
        value = fixture()
        endpoint = value["semantic_state"]["clips"][0]["planned_end_snapshot"]["endpoint_states"][0]
        endpoint["carry_forward"] = True
        snapshot = value["semantic_state"]["clips"][0]["planned_end_snapshot"]
        snapshot["snapshot_sha256"] = state.sha256_object({key: item for key, item in snapshot.items() if key != "snapshot_sha256"})
        rehash_project(value)
        self.assert_state_error(value, "STATE057_ENDPOINT_CARRY_FORWARD_INVALID")

        open_endpoint = fixture()
        snapshot = open_endpoint["semantic_state"]["clips"][0]["planned_end_snapshot"]
        snapshot["endpoint_states"][0]["completion_mode"] = "open_handoff"
        snapshot["endpoint_states"][0]["carry_forward"] = True
        snapshot["snapshot_sha256"] = state.sha256_object({key: item for key, item in snapshot.items() if key != "snapshot_sha256"})
        rehash_project(open_endpoint)
        self.assert_state_error(open_endpoint, "STATE060_MOTION_HANDOFF_ENDPOINT_MISMATCH")

    def test_reanchor_is_optional_and_exact_timing_requires_evidence_or_block(self) -> None:
        selected = fixture()
        selected["semantic_state"]["reanchor_policy"] = {"status": "selected", "trigger_extension_depth": 7, "reason": "Re-anchor when project review finds accumulated drift."}
        rehash_project(selected)
        self.assertEqual(state.validate_project_state(selected), selected)

        exact = fixture()
        exact["semantic_state"]["timing_policy"] = {"mode": "surface_exact_ranges", "status": "selected", "evidence_claim_ids": [], "evidence_expires_at": None, "block_reason": None}
        rehash_project(exact)
        self.assert_state_error(exact, "STATE066_EXACT_TIMING_EVIDENCE_REQUIRED")

        blocked = fixture()
        blocked["semantic_state"]["timing_policy"] = {"mode": "surface_exact_ranges", "status": "blocked", "evidence_claim_ids": [], "evidence_expires_at": None, "block_reason": "No current surface-scoped evidence."}
        rehash_project(blocked)
        self.assertEqual(state.validate_project_state(blocked), blocked)

        fabricated = fixture()
        fabricated["semantic_state"]["timing_policy"] = {"mode": "surface_exact_ranges", "status": "blocked", "evidence_claim_ids": ["fake.claim"], "evidence_expires_at": "2099-01-01", "block_reason": "Blocked."}
        rehash_project(fabricated)
        self.assert_state_error(fabricated, "STATE065_TIMING_POLICY_INVALID")

    def test_authority_stays_unresolved_and_compile_required_is_explicit(self) -> None:
        value = fixture()
        self.assertTrue(value["semantic_state"]["clips"][0]["compile_required"])
        asset = value["semantic_state"]["reference_assets"][0]
        self.assertEqual(asset["authority_status"], "unresolved")
        self.assertEqual(asset["status"], "pending")
        self.assertNotIn("binding_policy", asset)
        asset["authority_status"] = "selected"
        rehash_project(value)
        self.assert_state_error(value, "STATE061_BINDING_POLICY_INVALID")

    def test_v2_prompt_and_run_fixtures_make_no_false_compiler_claim(self) -> None:
        prompt_spec = json.loads((FIXTURES / "prompt-spec-v2.valid.json").read_text(encoding="utf-8"))
        generation_run = json.loads((FIXTURES / "generation-run-v2.valid.json").read_text(encoding="utf-8"))
        self.assertEqual(prompt_spec["status"], "compile_required")
        self.assertEqual(generation_run["execution_status"], "blocked")
        forbidden = {"prompt", "natural_language_prompt", "prompt_render_sha256", "compiler_sha256", "compiler_toolchain_sha256"}
        self.assertTrue(forbidden.isdisjoint(prompt_spec))
        self.assertTrue(forbidden.isdisjoint(generation_run))

    def test_project_mode_parent_relation_and_readiness_cannot_bypass_contracts(self) -> None:
        wrong_mode = accepted_video_continuation()
        wrong_mode["project_mode"] = "standalone_clip"
        rehash_project(wrong_mode)
        self.assert_state_error(wrong_mode, "STATE024_PROJECT_MODE_INVALID")

        disguised_child = accepted_video_continuation()
        child = disguised_child["semantic_state"]["clips"][1]
        child["sequence_relation"] = "standalone"
        child["planned_start_snapshot"]["motion_handoff"]["vectors"] = []
        rehash_snapshot(child["planned_start_snapshot"])
        rehash_project(disguised_child)
        self.assert_state_error(disguised_child, "STATE045_PARENT_RELATION_INVALID")

        false_ready = fixture()
        false_ready["semantic_state"]["clips"][0]["execution_readiness"] = "ready"
        rehash_project(false_ready)
        self.assert_state_error(false_ready, "STATE043_EXECUTION_READINESS_INVALID")

        ambiguous_status = fixture()
        ambiguous_status["semantic_state"]["clips"][0]["status"] = "ready"
        rehash_project(ambiguous_status)
        self.assert_state_error(ambiguous_status, "STATE035_CLIP_STATUS_INVALID")

        premature_compile = fixture()
        premature_compile["semantic_state"]["clips"][0]["execution_readiness"] = "compile_required"
        rehash_project(premature_compile)
        self.assert_state_error(premature_compile, "STATE043_EXECUTION_READINESS_INVALID")

    def test_planned_reference_proofs_are_live_exact_and_schema_bound(self) -> None:
        schema = json.loads((ROOT / "schemas" / "project-state-v2.schema.json").read_text(encoding="utf-8"))
        schema_validator = Draft202012Validator(schema, format_checker=FormatChecker())

        def candidate(planning_status: str, reference_status: str) -> dict:
            value = fixture()
            reference = value["semantic_state"]["reference_assets"][0]
            reference["status"] = reference_status
            reference["media_sha256"] = "a" * 64 if reference_status == "available" else None
            planning = value["semantic_state"]["clips"][0]["planning_link"]
            planning["status"] = planning_status
            if planning_status == "planned":
                planning.update({
                    "resolved_binding_proofs": [{"binding_id": "product_ref", "media_sha256": "a" * 64}],
                    "reference_manifest_sha256": "b" * 64,
                    "scene_ir_sha256": "c" * 64,
                    "planning_report_sha256": "d" * 64,
                })
                value["semantic_state"]["clips"][0]["execution_readiness"] = "compile_required"
            rehash_project(value)
            return value

        for planning_status, reference_status, should_pass in (
            ("planning_required", "pending", True),
            ("planning_required", "available", True),
            ("planning_required", "retired", False),
            ("planned", "pending", False),
            ("planned", "available", True),
            ("planned", "retired", False),
        ):
            with self.subTest(planning_status=planning_status, reference_status=reference_status):
                value = candidate(planning_status, reference_status)
                if should_pass:
                    self.assertEqual(state.validate_project_state(value), value)
                else:
                    with self.assertRaises(state.StateV2Error):
                        state.validate_project_state(value)

        planned_available = candidate("planned", "available")
        self.assertEqual(list(schema_validator.iter_errors(planned_available)), [])
        planned_pending = candidate("planned", "pending")
        self.assertTrue(list(schema_validator.iter_errors(planned_pending)))

        proof_mutations = [
            lambda planning: planning.update(resolved_binding_proofs=[]),
            lambda planning: planning["resolved_binding_proofs"][0].update(media_sha256="e" * 64),
            lambda planning: planning["resolved_binding_proofs"].append({"binding_id": "extra_ref", "media_sha256": "a" * 64}),
            lambda planning: planning["resolved_binding_proofs"].append({"binding_id": "product_ref", "media_sha256": "e" * 64}),
        ]
        for index, mutation in enumerate(proof_mutations):
            with self.subTest(proof_mutation=index):
                value = candidate("planned", "available")
                mutation(value["semantic_state"]["clips"][0]["planning_link"])
                rehash_project(value)
                self.assert_state_error(value, "STATE042_PLANNING_LINK_PARTIAL" if index != 1 else "STATE083_PLANNED_REFERENCE_UNRESOLVED")

        missing_projection = candidate("planned", "available")
        missing_projection["semantic_state"]["clips"][0]["planning_link"].pop("resolved_binding_proofs")
        rehash_project(missing_projection)
        self.assertTrue(list(schema_validator.iter_errors(missing_projection)))
        with self.assertRaises(state.StateV2Error):
            state.validate_project_state(missing_projection)

    def test_accepted_observation_claims_require_bound_media_and_confirmation(self) -> None:
        motion = {
            "basis": "observed",
            "vectors": [{
                "motion_id": "watch.slide", "owner_kind": "product", "owner_id": "watch", "domain": "subject",
                "coordinate_frame": "world", "description": "The watch continues right.", "phase": "continuing",
                "direction": "right", "speed": "slow", "speed_trend": "constant", "continuity": "open",
                "observability": "observed_in_video", "source_kind": "accepted_video", "confidence": "high", "uncertainty": None,
            }],
        }
        with self.assertRaises(state.StateV2Error) as caught:
            state._validate_motion(motion, "observed", "/motion", snapshot_source_kind="legacy_state_description")
        self.assertEqual(caught.exception.code, "STATE004_MOTION_SOURCE_INVALID")

        unconfirmed = accepted_video_continuation()
        unconfirmed["semantic_state"]["clips"] = unconfirmed["semantic_state"]["clips"][:1]
        unconfirmed["semantic_state"]["scenes"][0]["assigned_clip_ids"] = ["clip_01"]
        unconfirmed["semantic_state"]["current_clip_id"] = "clip_01"
        unconfirmed["project_mode"] = "standalone_clip"
        clip = unconfirmed["semantic_state"]["clips"][0]
        clip["sequence_relation"] = "standalone"
        observed = clip["observed_end_snapshot"]
        observed["source"] = {"kind": "legacy_state_description", "take_id": None, "media_sha256": None}
        observed["motion_handoff"]["vectors"][0].update(source_kind="legacy_state_description", observability="unknown")
        observed["requires_confirmation"] = False
        rehash_snapshot(observed)
        rehash_project(unconfirmed)
        self.assert_state_error(unconfirmed, "STATE010_SNAPSHOT_SOURCE_INVALID")

        observed["requires_confirmation"] = True
        rehash_snapshot(observed)
        rehash_project(unconfirmed)
        self.assert_state_error(unconfirmed, "STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED")

    def test_accepted_observation_pair_and_final_frame_endpoint_are_fail_closed(self) -> None:
        value = accepted_video_continuation()
        parent = value["semantic_state"]["clips"][0]
        observed_start = copy.deepcopy(parent["observed_end_snapshot"])
        observed_start["snapshot_id"] = "clip_01.observed_start_state"
        observed_start["endpoint_states"] = []
        rehash_snapshot(observed_start)
        parent["observed_start_snapshot"] = observed_start
        rehash_project(value)
        self.assertEqual(state.validate_project_state(value), value)

        observed_start["source"]["take_id"] = "take_other"
        rehash_snapshot(observed_start)
        rehash_project(value)
        self.assert_state_error(value, "STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED")

        frame = accepted_video_continuation()
        frame["semantic_state"]["clips"] = frame["semantic_state"]["clips"][:1]
        frame["semantic_state"]["scenes"][0]["assigned_clip_ids"] = ["clip_01"]
        frame["semantic_state"]["current_clip_id"] = "clip_01"
        frame["project_mode"] = "standalone_clip"
        clip = frame["semantic_state"]["clips"][0]
        clip["sequence_relation"] = "standalone"
        observed_end = clip["observed_end_snapshot"]
        observed_end["source"]["kind"] = "accepted_final_frame"
        observed_end["motion_handoff"]["vectors"] = []
        observed_end["endpoint_states"][0].update(completion_mode="held_static", carry_forward=False)
        rehash_snapshot(observed_end)
        rehash_project(frame)
        self.assertEqual(state.validate_project_state(frame), frame)

        for completion_mode in ("completed_with_motion", "dissipated_or_resolved", "frame_exit", "cyclic_phase_boundary", "open_handoff", "incomplete", "unknown"):
            observed_end["endpoint_states"][0]["completion_mode"] = completion_mode
            if completion_mode == "open_handoff":
                observed_end["endpoint_states"][0]["carry_forward"] = True
                observed_end["motion_handoff"]["vectors"] = [{
                    "motion_id": "watch.open", "owner_kind": "product", "owner_id": "watch", "domain": "subject",
                    "coordinate_frame": "world", "description": "The watch may continue.", "phase": "continuing",
                    "direction": None, "speed": None, "speed_trend": "unknown", "continuity": "open",
                    "observability": "inferred_from_frame", "source_kind": "accepted_final_frame", "confidence": "low", "uncertainty": "Still-frame ambiguity.",
                }]
            else:
                observed_end["endpoint_states"][0]["carry_forward"] = False
                observed_end["motion_handoff"]["vectors"] = []
            rehash_snapshot(observed_end)
            rehash_project(frame)
            self.assert_state_error(frame, "STATE008_FRAME_MOTION_OVERCLAIM")

        incomplete_deviation = accepted_video_continuation()
        parent = incomplete_deviation["semantic_state"]["clips"][0]
        parent["status"] = "accepted_with_deviation"
        parent["accepted_deviation_ids"] = ["deviation_watch"]
        parent["observed_end_snapshot"]["endpoint_states"][0].update(completion_mode="incomplete", carry_forward=False)
        rehash_snapshot(parent["observed_end_snapshot"])
        rehash_project(incomplete_deviation)
        self.assert_state_error(incomplete_deviation, "STATE041_ACCEPTED_COMPLETION_UNKNOWN")

    def test_take_identity_completed_motion_and_deviation_projection_are_exact(self) -> None:
        conflicting_take = accepted_video_continuation()
        child = conflicting_take["semantic_state"]["clips"][1]
        child["status"] = "accepted"
        child_end = copy.deepcopy(conflicting_take["semantic_state"]["clips"][0]["observed_end_snapshot"])
        child_end["snapshot_id"] = "clip_02.observed_end_state"
        child_end["source"]["media_sha256"] = "2" * 64
        rehash_snapshot(child_end)
        child["observed_end_snapshot"] = child_end
        rehash_project(conflicting_take)
        self.assert_state_error(conflicting_take, "STATE078_TAKE_IDENTITY_CONFLICT")

        conflicting_asset = accepted_video_continuation()
        asset = conflicting_asset["semantic_state"]["reference_assets"][0]
        asset.update(source_kind="accepted_take", source_take_id="take_01", media_sha256="2" * 64, status="available")
        rehash_project(conflicting_asset)
        self.assert_state_error(conflicting_asset, "STATE078_TAKE_IDENTITY_CONFLICT")

        no_motion = fixture()
        snapshot = no_motion["semantic_state"]["clips"][0]["planned_end_snapshot"]
        snapshot["endpoint_states"][0]["completion_mode"] = "completed_with_motion"
        snapshot["motion_handoff"]["vectors"] = []
        rehash_snapshot(snapshot)
        rehash_project(no_motion)
        self.assert_state_error(no_motion, "STATE079_COMPLETED_MOTION_EVIDENCE_REQUIRED")

        deviation = accepted_video_continuation()
        deviation["semantic_state"]["clips"][0]["status"] = "accepted_with_deviation"
        deviation["semantic_state"]["clips"][0]["accepted_deviation_ids"] = ["deviation_watch"]
        rehash_project(deviation)
        self.assertEqual(state.validate_project_state(deviation), deviation)

        deviation["semantic_state"]["clips"][0]["accepted_deviation_ids"] = []
        rehash_project(deviation)
        self.assert_state_error(deviation, "STATE080_ACCEPTED_DEVIATION_PROJECTION_INVALID")

    def test_reference_topology_and_motion_carry_are_lossless(self) -> None:
        retired_anchor = fixture()
        retired_anchor["semantic_state"]["reference_assets"].append({
            "binding_id": "retired_anchor", "media_type": "image", "source_kind": "user_asset",
            "source_take_id": None, "media_sha256": None, "description": "Retired anchor.",
            "status": "retired", "authority_status": "unresolved",
        })
        retired_anchor["semantic_state"]["scenes"][0]["anchor_binding_ids"].append("retired_anchor")
        rehash_project(retired_anchor)
        self.assert_state_error(retired_anchor, "STATE030_REFERENCE_UNKNOWN")

        dropped_binding = accepted_video_continuation()
        child = dropped_binding["semantic_state"]["clips"][1]
        child["planned_start_snapshot"]["binding_ids"] = []
        child["planning_link"]["binding_ids"] = []
        rehash_snapshot(child["planned_start_snapshot"])
        rehash_project(dropped_binding)
        self.assert_state_error(dropped_binding, "STATE076_REFERENCE_BINDING_DROPPED")

        mismatched_planning = fixture()
        mismatched_planning["semantic_state"]["clips"][0]["planning_link"]["binding_ids"] = []
        rehash_project(mismatched_planning)
        self.assert_state_error(mismatched_planning, "STATE042_PLANNING_LINK_PARTIAL")

        many_to_one = accepted_video_continuation()
        observed = many_to_one["semantic_state"]["clips"][0]["observed_end_snapshot"]
        second = copy.deepcopy(observed["motion_handoff"]["vectors"][0])
        second["motion_id"] = "watch.slide.secondary"
        second["description"] = "A second distinct sliding component remains open."
        observed["motion_handoff"]["vectors"].append(second)
        rehash_snapshot(observed)
        rehash_project(many_to_one)
        self.assert_state_error(many_to_one, "STATE071_CARRY_FORWARD_DROPPED")

    def test_reanchor_parent_and_beat_assignment_scopes_are_coherent(self) -> None:
        reanchor = accepted_video_continuation()
        child = reanchor["semantic_state"]["clips"][1]
        child["sequence_relation"] = "reanchor_after_drift"
        child["extension_depth"] = 0
        rehash_project(reanchor)
        self.assertEqual(state.validate_project_state(reanchor), reanchor)

        reanchor["semantic_state"]["clips"][0]["status"] = "planned"
        rehash_project(reanchor)
        self.assert_state_error(reanchor, "STATE049_PARENT_NOT_ACCEPTED")

        wrong_assignment = fixture()
        wrong_assignment["semantic_state"]["beats"][0]["assigned_clip_id"] = None
        rehash_project(wrong_assignment)
        self.assert_state_error(wrong_assignment, "STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH")

        cross_scope = accepted_video_continuation()
        cross_scope["semantic_state"]["clips"][1]["already_happened"] = []
        cross_scope["semantic_state"]["clips"][1]["this_clip_only"] = ["beat_hold"]
        rehash_project(cross_scope)
        self.assert_state_error(cross_scope, "STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH")

        planned_past = accepted_video_continuation()
        planned_past["semantic_state"]["beats"][0]["status"] = "planned"
        rehash_project(planned_past)
        self.assert_state_error(planned_past, "STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH")

        unresolved_dependency = fixture()
        unresolved_dependency["semantic_state"]["beats"].append({
            "beat_id": "beat_future", "description": "A later unresolved beat.", "status": "planned",
            "assigned_clip_id": "clip_01", "dependencies": [],
        })
        unresolved_dependency["semantic_state"]["beats"][0]["dependencies"] = ["beat_future"]
        unresolved_dependency["semantic_state"]["clips"][0]["this_clip_only"] = ["beat_hold", "beat_future"]
        rehash_project(unresolved_dependency)
        self.assert_state_error(unresolved_dependency, "STATE081_BEAT_DEPENDENCY_LIFECYCLE_INVALID")

        inactive_scene = fixture()
        inactive_scene["semantic_state"]["scenes"][0]["status"] = "completed"
        rehash_project(inactive_scene)
        self.assert_state_error(inactive_scene, "STATE082_SCENE_LIFECYCLE_INVALID")

        duplicate_current_scene = fixture()
        duplicate_current_scene["semantic_state"]["scenes"].append({
            "scene_id": "scene_02", "scene_index": 2, "anchor_binding_ids": ["product_ref"],
            "assigned_clip_ids": [], "status": "current",
        })
        rehash_project(duplicate_current_scene)
        self.assert_state_error(duplicate_current_scene, "STATE082_SCENE_LIFECYCLE_INVALID")

    def test_story_and_world_cannot_hide_execution_claims(self) -> None:
        provider_key = fixture()
        provider_key["semantic_state"]["world_bible"]["provider_id"] = "opaque"
        rehash_project(provider_key)
        self.assert_state_error(provider_key, "STATE001_SURFACE_FIELD_FORBIDDEN")

        provider_value = fixture()
        provider_value["semantic_state"]["story"]["logline"] = "Submit through the Seedance API endpoint."
        rehash_project(provider_value)
        self.assert_state_error(provider_value, "STATE001_SURFACE_FIELD_FORBIDDEN")

        hidden_felt_intent = fixture()
        hidden_felt_intent["semantic_state"]["clips"][0]["felt_intent"] = "The compiler submission is ready."
        rehash_project(hidden_felt_intent)
        self.assert_state_error(hidden_felt_intent, "STATE001_SURFACE_FIELD_FORBIDDEN")

        chinese_claim = fixture()
        chinese_claim["semantic_state"]["world_bible"]["模型版本"] = "字节跳动 Seedance"
        rehash_project(chinese_claim)
        self.assert_state_error(chinese_claim, "STATE001_SURFACE_FIELD_FORBIDDEN")

        for key in ("binding_policy", "render_sha256", "prompt_render_sha256", "bindingPolicy", "promptRenderHash", "renderer_sha256"):
            with self.subTest(key=key):
                hidden_authority = fixture()
                hidden_authority["semantic_state"]["world_bible"][key] = "opaque"
                rehash_project(hidden_authority)
                self.assert_state_error(hidden_authority, "STATE001_SURFACE_FIELD_FORBIDDEN")

        legitimate_prose = fixture()
        legitimate_prose["semantic_state"]["story"]["logline"] = "A compiler submits a short story to a magazine."
        rehash_project(legitimate_prose)
        self.assertEqual(state.validate_project_state(legitimate_prose), legitimate_prose)

    def test_adjacent_schema_string_bounds_are_enforced_dependency_free(self) -> None:
        long_block = fixture()
        long_block["semantic_state"]["timing_policy"] = {
            "mode": "surface_exact_ranges", "status": "blocked", "evidence_claim_ids": [],
            "evidence_expires_at": None, "block_reason": "x" * 2001,
        }
        rehash_project(long_block)
        self.assert_state_error(long_block, "STATE065_TIMING_POLICY_INVALID")

        long_source_version = fixture()
        long_source_version["migration_provenance"]["source_schema_version"] = "v" * 33
        self.assert_state_error(long_source_version, "STATE055_MIGRATION_PROVENANCE_INVALID")

        wrong_source_version_type = fixture()
        wrong_source_version_type["migration_provenance"]["source_schema_version"] = 2
        self.assert_state_error(wrong_source_version_type, "STATE055_MIGRATION_PROVENANCE_INVALID")

    def test_accepted_video_open_motion_must_carry_exactly_into_child(self) -> None:
        value = accepted_video_continuation()
        self.assertEqual(state.validate_project_state(value), value)
        payload = state.canonical_json(value)
        for seed in range(10):
            result = subprocess.run(
                [sys.executable, "-S", "-B", "scripts/project_state_v2_check.py"], cwd=ROOT,
                input=payload, capture_output=True, env={**__import__("os").environ, "PYTHONHASHSEED": str(seed)}, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        dropped = accepted_video_continuation()
        child_start = dropped["semantic_state"]["clips"][1]["planned_start_snapshot"]
        child_start["motion_handoff"]["vectors"] = []
        rehash_snapshot(child_start)
        rehash_project(dropped)
        self.assert_state_error(dropped, "STATE071_CARRY_FORWARD_DROPPED")

        wrong_depth = accepted_video_continuation()
        wrong_depth["semantic_state"]["clips"][1]["extension_depth"] = 2
        rehash_project(wrong_depth)
        self.assert_state_error(wrong_depth, "STATE075_EXTENSION_DEPTH_DISCONTINUITY")

        changed_owner = accepted_video_continuation()
        child_atom = changed_owner["semantic_state"]["clips"][1]["planned_start_snapshot"]["state_atoms"][0]
        child_atom["owner_id"] = "other_watch"
        rehash_snapshot(changed_owner["semantic_state"]["clips"][1]["planned_start_snapshot"])
        rehash_project(changed_owner)
        self.assert_state_error(changed_owner, "STATE070_CONTINUITY_ATOM_IDENTITY_CHANGED")

    def test_local_completion_can_keep_open_motion_without_carry(self) -> None:
        value = accepted_video_continuation()
        parent_endpoint = value["semantic_state"]["clips"][0]["observed_end_snapshot"]["endpoint_states"][0]
        parent_endpoint["completion_mode"] = "completed_with_motion"
        parent_endpoint["carry_forward"] = False
        rehash_snapshot(value["semantic_state"]["clips"][0]["observed_end_snapshot"])
        child_start = value["semantic_state"]["clips"][1]["planned_start_snapshot"]
        child_start["motion_handoff"]["vectors"] = []
        rehash_snapshot(child_start)
        rehash_project(value)
        self.assertEqual(state.validate_project_state(value), value)

    def test_root_rules_budgets_dates_endpoint_ids_and_reference_liveness_are_checked(self) -> None:
        bad_rule = fixture()
        bad_rule["semantic_state"]["clips"][0]["continuity_rules"] = [{"rule_id": "bad"}]
        rehash_project(bad_rule)
        self.assert_state_error(bad_rule, "OBJECT_FIELDS_INVALID")

        bad_budget = fixture()
        bad_budget["semantic_state"]["clip_budget_sec"] = True
        rehash_project(bad_budget)
        self.assert_state_error(bad_budget, "STATE072_BUDGET_INVALID")

        unknown_current = fixture()
        unknown_current["semantic_state"]["current_clip_id"] = "clip_missing"
        rehash_project(unknown_current)
        self.assert_state_error(unknown_current, "STATE054_CURRENT_CLIP_UNKNOWN")

        bad_date = fixture()
        bad_date["updated_at"] = "2026-02-31"
        self.assert_state_error(bad_date, "STATE056_DATE_INVALID")

        compact_date = fixture()
        compact_date["updated_at"] = "20260713"
        self.assert_state_error(compact_date, "STATE056_DATE_INVALID")

        non_boolean_endpoint = fixture()
        snapshot = non_boolean_endpoint["semantic_state"]["clips"][0]["planned_end_snapshot"]
        snapshot["endpoint_states"][0]["carry_forward"] = None
        rehash_snapshot(snapshot)
        rehash_project(non_boolean_endpoint)
        self.assert_state_error(non_boolean_endpoint, "TYPE_BOOLEAN_REQUIRED")

        numeric_confirmation = fixture()
        snapshot = numeric_confirmation["semantic_state"]["clips"][0]["planned_start_snapshot"]
        snapshot["requires_confirmation"] = 1
        rehash_snapshot(snapshot)
        rehash_project(numeric_confirmation)
        self.assert_state_error(numeric_confirmation, "TYPE_BOOLEAN_REQUIRED")

        duplicate_endpoint = fixture()
        snapshot = duplicate_endpoint["semantic_state"]["clips"][0]["planned_end_snapshot"]
        snapshot["endpoint_states"].append(copy.deepcopy(snapshot["endpoint_states"][0]))
        rehash_snapshot(snapshot)
        rehash_project(duplicate_endpoint)
        self.assert_state_error(duplicate_endpoint, "STATE002_IDENTIFIER_DUPLICATE")

        retired = fixture()
        retired["semantic_state"]["reference_assets"][0]["status"] = "retired"
        rehash_project(retired)
        self.assert_state_error(retired, "STATE030_REFERENCE_UNKNOWN")

        bad_asset = fixture()
        bad_asset["semantic_state"]["reference_assets"][0]["status"] = "available"
        rehash_project(bad_asset)
        self.assert_state_error(bad_asset, "STATE069_REFERENCE_PROVENANCE_REQUIRED")

    def test_unhashable_enum_values_fail_with_typed_contract_errors(self) -> None:
        mutations = [
            lambda value: value.update(project_mode=[]),
            lambda value: value["semantic_state"]["timing_policy"].update(mode={}),
            lambda value: value["semantic_state"]["reference_assets"][0].update(source_kind=[]),
            lambda value: value["semantic_state"]["scenes"][0].update(status={}),
            lambda value: value["semantic_state"]["beats"][0].update(status=[]),
            lambda value: value["semantic_state"]["clips"][0].update(sequence_relation={}),
            lambda value: value["semantic_state"]["clips"][0]["planned_end_snapshot"]["motion_handoff"]["vectors"][0].update(source_kind=[]),
            lambda value: value["semantic_state"]["clips"][0]["planned_end_snapshot"]["endpoint_states"][0].update(completion_mode={}),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                candidate = fixture()
                mutation(candidate)
                for clip in candidate["semantic_state"]["clips"]:
                    for field in ("planned_start_snapshot", "planned_end_snapshot", "observed_start_snapshot", "observed_end_snapshot"):
                        if clip[field] is not None:
                            rehash_snapshot(clip[field])
                rehash_project(candidate)
                with self.assertRaises(state.StateV2Error):
                    state.validate_project_state(candidate)

    def test_all_three_beat_scope_overlaps_fail(self) -> None:
        value = fixture()
        clip = value["semantic_state"]["clips"][0]
        clip["already_happened"] = ["beat_hold"]
        clip["this_clip_only"] = []
        clip["reserved_for_later"] = ["beat_hold"]
        rehash_project(value)
        self.assert_state_error(value, "STATE038_BEAT_SCOPE_OVERLAP")

    def test_deep_beat_graph_is_iterative_and_bounded(self) -> None:
        value = fixture()
        beats = []
        for index in range(1500):
            beat_id = f"beat_{index}"
            beats.append({"beat_id": beat_id, "description": f"Beat {index}.", "status": "planned", "assigned_clip_id": "clip_01", "dependencies": [f"beat_{index - 1}"] if index else []})
        value["semantic_state"]["beats"] = beats
        clip = value["semantic_state"]["clips"][0]
        clip["already_happened"] = []
        clip["this_clip_only"] = [f"beat_{index}" for index in range(1500)]
        clip["reserved_for_later"] = []
        rehash_project(value)
        self.assertEqual(state.validate_project_state(value), value)

        value["semantic_state"]["beats"][0]["dependencies"] = ["beat_1499"]
        rehash_project(value)
        self.assert_state_error(value, "STATE032_BEAT_CYCLE")

    def test_no_arbitrary_extension_depth_ceiling(self) -> None:
        value = fixture()
        value["semantic_state"]["clips"][0]["extension_depth"] = 1000
        rehash_project(value)
        self.assertEqual(state.validate_project_state(value), value)

    def test_surface_fields_are_forbidden_even_when_hash_is_recomputed(self) -> None:
        value = fixture()
        value["semantic_state"]["world_bible"]["tag"] = "opaque"
        rehash_project(value)
        self.assert_state_error(value, "STATE001_SURFACE_FIELD_FORBIDDEN")

    def test_semantic_hash_and_snapshot_hash_are_enforced(self) -> None:
        semantic = fixture()
        semantic["semantic_state"]["story"]["tone"] = "changed"
        self.assert_state_error(semantic, "STATE026_SEMANTIC_STATE_HASH_MISMATCH")

        snapshot = fixture()
        snapshot["semantic_state"]["clips"][0]["planned_start_snapshot"]["requires_confirmation"] = True
        rehash_project(snapshot)
        self.assert_state_error(snapshot, "STATE016_SNAPSHOT_HASH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
