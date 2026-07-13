from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals" / "evals.json"

V708_CASE_IDS = {
    "physics_claim_architecture_refusal",
    "mirror_lag_observable_risk",
    "contact_visible_consequence_not_force_proof",
    "stylized_reverse_gravity_declared_rule",
    "subject_settled_ambient_continues",
    "held_dynamic_endpoint",
    "camera_subject_motion_ownership",
    "seamless_open_motion_handoff",
    "intentional_cut_axis_reset",
    "endpoint_full_chain_observability",
    "same_seed_not_determinism_proof",
    "repeat_failure_not_causal_proof",
}


def load_cases() -> dict[str, dict]:
    value = json.loads(EVALS.read_text(encoding="utf-8"))
    return {case["id"]: case for case in value["cases"]}


def oracle_text(case: dict) -> str:
    return " ".join(
        [
            case["expected_output"],
            *case["assertions"],
            case["failure_mode"],
        ]
    ).casefold()


class PhysicsMotionFailureCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()

    def test_twelve_failure_focused_cases_are_present_and_closed(self) -> None:
        self.assertEqual(V708_CASE_IDS - set(self.cases), set())
        self.assertEqual(len(V708_CASE_IDS), 12)
        for case_id in sorted(V708_CASE_IDS):
            case = self.cases[case_id]
            with self.subTest(case_id=case_id):
                self.assertEqual(
                    set(case),
                    {
                        "id",
                        "prompt",
                        "expected_output",
                        "assertions",
                        "failure_mode",
                        "skills_expected_to_activate",
                    },
                )
                self.assertGreaterEqual(len(case["assertions"]), 4)
                self.assertTrue(case["skills_expected_to_activate"])

    def test_public_suites_remain_non_release_eligible(self) -> None:
        development = json.loads(
            (ROOT / "evals" / "suites" / "development.json").read_text(encoding="utf-8")
        )
        live = json.loads(
            (ROOT / "evals" / "suites" / "live.json").read_text(encoding="utf-8")
        )
        self.assertEqual(development["expected_case_count"], len(self.cases))
        self.assertFalse(development["release_eligible"])
        self.assertFalse(live["release_eligible"])
        self.assertEqual(development["kind"], "development")
        self.assertEqual(live["kind"], "live")

    def test_settled_subject_does_not_freeze_unrelated_ambient_motion(self) -> None:
        text = oracle_text(self.cases["subject_settled_ambient_continues"])
        for required in (
            "cyclist is stationary",
            "rain and foliage motion active",
            "separate environment ownership",
            "does not treat settled endpoint as global frame stillness",
        ):
            self.assertIn(required, text)

    def test_held_dynamic_endpoint_is_not_rewritten_as_zero_motion(self) -> None:
        text = oracle_text(self.cases["held_dynamic_endpoint"])
        self.assertIn("held dynamic endpoint", text)
        self.assertIn("ongoing rotation", text)
        self.assertIn("does not rewrite the fan endpoint as stopped", text)
        self.assertIn("dynamic but complete and reviewable", text)

    def test_camera_and_subject_motion_have_separate_owners(self) -> None:
        text = oracle_text(self.cases["camera_subject_motion_ownership"])
        self.assertIn("stationary status to the runner", text)
        self.assertIn("continuing push-in only to the camera", text)
        self.assertIn("does not describe the runner as still moving", text)

    def test_intentional_change_is_dimension_scoped_not_a_global_waiver(self) -> None:
        text = oracle_text(self.cases["intentional_cut_axis_reset"])
        self.assertIn("only the camera-side and screen-axis reset", text)
        self.assertIn("preserves identity, wardrobe, location, and prop ownership", text)
        self.assertIn("does not treat the word intentional as permission", text)

    def test_same_seed_and_repeated_failure_are_not_causal_proof(self) -> None:
        seed_text = oracle_text(self.cases["same_seed_not_determinism_proof"])
        repeat_text = oracle_text(self.cases["repeat_failure_not_causal_proof"])
        self.assertIn("does not call the comparison deterministic", seed_text)
        self.assertIn("checks seed support on the exact model, surface, and operation", seed_text)
        self.assertIn("does not say that three failures prove", repeat_text)
        self.assertIn("without claiming causal certainty", repeat_text)

    def test_declared_stylized_world_rule_is_preserved(self) -> None:
        text = oracle_text(self.cases["stylized_reverse_gravity_declared_rule"])
        self.assertIn("keeps the user-declared upward direction", text)
        self.assertIn("instead of silently restoring ordinary gravity", text)
        self.assertIn("does not claim the model has learned or simulated", text)

    def test_endpoint_review_covers_the_full_observable_chain(self) -> None:
        text = oracle_text(self.cases["endpoint_full_chain_observability"])
        for phase in (
            "before-state",
            "decisive event",
            "visible response",
            "follow-through",
            "endpoint",
        ):
            self.assertIn(phase, text)
        self.assertIn("endpoint-only review cannot establish", text)

    def test_existing_hidden_assumptions_and_hard_chain_threshold_are_removed(self) -> None:
        novel = oracle_text(self.cases["novel_case_mechanism_reasoning"])
        contact = oracle_text(self.cases["physical_contact_has_consequence_chain"])
        chain = oracle_text(self.cases["scene_layer_caps_extension_chain"])
        reanchor = oracle_text(self.cases["local_reference_reanchor"])
        self.assertNotIn("training-distribution rarity", novel)
        self.assertNotIn("trajectory conflict", novel)
        self.assertNotIn("ties the consequence to mass and force", contact)
        self.assertNotIn("max_chain_depth", chain)
        self.assertNotIn("default 2", chain)
        self.assertNotIn("extension_depth 2 raises continuity risk", reanchor)
        self.assertIn("observed coat and face deviation", reanchor)

    def test_sequence_eval_check_is_deterministic_across_ten_hash_seeds(self) -> None:
        outputs: list[tuple[int, bytes, bytes]] = []
        for seed in ("0", "1", "2", "3", "7", "11", "42", "101", "708", "999"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            process = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "sequence_eval_check.py")],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
            outputs.append((process.returncode, process.stdout, process.stderr))
        self.assertTrue(all(output == outputs[0] for output in outputs))
        self.assertEqual(outputs[0][0], 0, outputs[0][1].decode("utf-8"))
        self.assertEqual(outputs[0][2], b"")


if __name__ == "__main__":
    unittest.main()
