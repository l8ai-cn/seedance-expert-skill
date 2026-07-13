from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts import av_take_review_check as review


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "validation" / "fixtures"
CHECKER = ROOT / "scripts" / "av_take_review_check.py"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bundle() -> dict:
    return {
        "take_review_v2": fixture("take-review-v2.valid.json"),
        "scene_ir_v2": fixture("scene-ir-v2.valid.json"),
        "av_take_review": fixture("av-take-review-v1.valid.json"),
    }


def rehash(value: dict) -> None:
    value["av_take_review"]["take_review_v2_sha256"] = review.canonical_sha256(value["take_review_v2"])
    value["av_take_review"]["scene_ir_v2_sha256"] = review.canonical_sha256(value["scene_ir_v2"])


class AVTakeReviewTests(unittest.TestCase):
    def assert_code(self, value: dict, code: str) -> None:
        self.assertTrue(any(error.startswith(code + ":") for error in review.validate_bundle(value)), review.validate_bundle(value))

    def test_valid_fixture_cli_and_dependency_free_self_test(self) -> None:
        value = bundle()
        self.assertEqual(review.validate_bundle(value), [])
        result = subprocess.run(
            [sys.executable, "-S", "-B", str(CHECKER)],
            cwd=ROOT,
            input=review.canonical_json(value),
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(
            subprocess.run(
                [sys.executable, "-S", "-B", str(CHECKER), "--self-test"],
                cwd=ROOT,
                capture_output=True,
                check=False,
            ).returncode,
            0,
        )

    def test_tampered_canonical_hashes_fail(self) -> None:
        for field in ("take_review_v2_sha256", "scene_ir_v2_sha256"):
            with self.subTest(field=field):
                value = bundle()
                value["av_take_review"][field] = "0" * 64
                self.assert_code(value, "AVR100_HASH_BINDING")

    def test_project_clip_take_media_and_base_verdict_match_exactly(self) -> None:
        for field, replacement in (("project_id", "other_project"), ("clip_id", "other_clip"), ("take_id", "other_take")):
            with self.subTest(field=field):
                value = bundle()
                value["av_take_review"][field] = replacement
                self.assert_code(value, "AVR101_ID_BINDING")

        verdict = bundle()
        verdict["av_take_review"]["base_verdict"] = "accept_with_deviation"
        self.assert_code(verdict, "AVR102_BASE_BINDING")

        media = bundle()
        av = media["av_take_review"]
        av["media_kind"] = "final_frame"
        for result in av["speech_results"]:
            result.update(utterance_status="unknown", speaker_status="unknown", spoken_language_status="unknown", lip_sync_status="unknown", timing_status="unknown")
        for result in av["audio_results"]:
            result["result"] = "unknown"
        for result in av["transition_results"]:
            result["result"] = "unknown"
        av["av_verdict"] = "pending"
        av["requires_user_confirmation"] = True
        self.assert_code(media, "AVR102_BASE_BINDING")

    def test_speech_nonspeech_and_transition_coverage_is_exact(self) -> None:
        cases = [
            lambda av: av["required_audio_event_ids"].pop(),
            lambda av: av["required_audio_event_ids"].append("extra_audio"),
            lambda av: av["speech_results"].pop(),
            lambda av: av["speech_results"].append(copy.deepcopy(av["speech_results"][0])),
            lambda av: av["audio_results"].pop(),
            lambda av: av["audio_results"].append(copy.deepcopy(av["audio_results"][0])),
        ]
        for mutate in cases:
            value = bundle()
            mutate(value["av_take_review"])
            self.assert_code(value, "AVR104_AUDIO_COVERAGE")

        for mutate in (
            lambda av: av["required_transition_ids"].pop(),
            lambda av: av["transition_results"].pop(),
            lambda av: av["transition_results"].append(copy.deepcopy(av["transition_results"][0])),
        ):
            value = bundle()
            mutate(value["av_take_review"])
            self.assert_code(value, "AVR105_TRANSITION_COVERAGE")

    def test_expected_utterance_hash_is_bound_to_exact_scene_bytes(self) -> None:
        value = bundle()
        value["av_take_review"]["speech_results"][0]["expected_utterance_sha256"] = "0" * 64
        self.assert_code(value, "AVR108_EXPECTED_UTTERANCE_BINDING")

        scene_tamper = bundle()
        speech = next(event["speech"] for event in scene_tamper["scene_ir_v2"]["audio_events"] if event["speech"] is not None)
        speech["utterance"] += "!"
        rehash(scene_tamper)
        errors = review.validate_bundle(scene_tamper)
        self.assertTrue(
            any(error.startswith(("AVR012_SCENE_INVALID:", "AVR107_SCENE_UTTERANCE_HASH:")) for error in errors),
            errors,
        )

    def test_required_lip_sync_cannot_be_reviewed_as_not_required(self) -> None:
        value = bundle()
        value["av_take_review"]["speech_results"][0]["lip_sync_status"] = "not_required"
        self.assert_code(value, "AVR113_LIP_SYNC_BINDING")

    def test_base_pending_cannot_be_false_pass(self) -> None:
        value = bundle()
        base = value["take_review_v2"]
        base["decision_status"] = "pending_confirmation"
        base["source_status"] = "reviewed"
        base["accepted_media_sha256"] = None
        base["requires_user_confirmation"] = True
        rehash(value)
        self.assert_code(value, "AVR110_VERDICT_DERIVATION")
        self.assert_code(value, "AVR112_FALSE_PASS")

    def test_final_frame_cannot_prove_transition_or_av_pass(self) -> None:
        value = bundle()
        base = value["take_review_v2"]
        base["media_kind"] = "final_frame"
        base["observed_start_snapshot_sha256"] = None
        for endpoint in base["endpoint_states"]:
            endpoint["completion_mode"] = "held_static"
        av = value["av_take_review"]
        av["media_kind"] = "final_frame"
        for result in av["speech_results"]:
            result.update(
                utterance_status="unknown",
                speaker_status="unknown",
                spoken_language_status="unknown",
                lip_sync_status="unknown",
                timing_status="unknown",
            )
        for result in av["audio_results"]:
            result["result"] = "unknown"
        for result in av["transition_results"]:
            result["result"] = "pass"
        av["unexpected_in_picture_text"] = "absent"
        av["av_verdict"] = "pending"
        av["requires_user_confirmation"] = True
        rehash(value)
        self.assert_code(value, "AVR109_FINAL_FRAME_OVERCLAIM")

    def test_unexpected_picture_text_forces_fail(self) -> None:
        accepted_failure = bundle()
        av = accepted_failure["av_take_review"]
        av["unexpected_in_picture_text"] = "present"
        av["av_verdict"] = "fail"
        av["requires_user_confirmation"] = False
        self.assertEqual(review.validate_bundle(accepted_failure), [])

        false_pass = bundle()
        false_pass["av_take_review"]["unexpected_in_picture_text"] = "present"
        errors = review.validate_bundle(false_pass)
        self.assertTrue(
            any(error.startswith(("AVR013_REVIEW_INVALID:", "AVR110_VERDICT_DERIVATION:")) for error in errors),
            errors,
        )

    def test_unknown_required_result_forces_pending(self) -> None:
        value = bundle()
        av = value["av_take_review"]
        av["audio_results"][0]["result"] = "unknown"
        av["av_verdict"] = "pending"
        av["requires_user_confirmation"] = True
        self.assertEqual(review.validate_bundle(value), [])

    def test_failure_precedes_unknown_in_verdict_derivation(self) -> None:
        value = bundle()
        av = value["av_take_review"]
        av["speech_results"][0]["speaker_status"] = "fail"
        av["audio_results"][0]["result"] = "unknown"
        av["av_verdict"] = "fail"
        av["requires_user_confirmation"] = False
        self.assertEqual(review.validate_bundle(value), [])

    def test_strict_json_resource_and_duplicate_limits(self) -> None:
        cases = [
            (b'{}\xef\xbb\xbf', "AVR007_INVALID_JSON"),
            (b'\xef\xbb\xbf{}', "AVR003_BOM_FORBIDDEN"),
            (b'\xff', "AVR002_INVALID_UTF8"),
            (b'{"x":1,"x":2}', "AVR004_DUPLICATE_KEY"),
            (b'{"x":NaN}', "AVR005_NONFINITE_NUMBER"),
            (b'{"x":1e999}', "AVR005_NONFINITE_NUMBER"),
        ]
        for raw, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(review.InputFailure) as caught:
                    review.parse_document(raw)
                self.assertEqual(caught.exception.code, code)

        too_deep = ("[" * (review.MAX_DEPTH + 1) + "0" + "]" * (review.MAX_DEPTH + 1)).encode()
        with self.assertRaises(review.InputFailure) as caught:
            review.parse_document(b'{"value":' + too_deep + b"}")
        self.assertEqual(caught.exception.code, "AVR006_RESOURCE_LIMIT")
        with self.assertRaises(review.InputFailure) as caught:
            review.parse_document(b" " * (review.MAX_INPUT_BYTES + 1))
        self.assertEqual(caught.exception.code, "AVR001_INPUT_TOO_LARGE")

    def test_cli_errors_are_deterministic_and_do_not_echo_input(self) -> None:
        value = bundle()
        value["av_take_review"]["base_verdict"] = {"secret": "must-not-echo"}
        raw = review.canonical_json(value)
        outputs: list[bytes] = []
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-S", "-B", str(CHECKER)],
                cwd=ROOT,
                input=raw,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertNotIn(b"must-not-echo", result.stderr)
            outputs.append(result.stderr)
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
