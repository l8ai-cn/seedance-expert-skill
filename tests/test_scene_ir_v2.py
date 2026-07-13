from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scripts import scene_ir_v2_check as av


ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "validation" / "fixtures" / "scene-ir-v2.valid.json"
POLICY_PATH = ROOT / "validation" / "fixtures" / "surface-av-policy.valid.json"
TODAY = date(2026, 7, 13)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SceneIRV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = load(SCENE_PATH)
        self.policy = load(POLICY_PATH)

    def assertCode(self, code: str, callback) -> av.AVContractError:
        with self.assertRaises(av.AVContractError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def validate(self, scene: dict | None = None, policy: dict | None = None) -> dict:
        return av.validate_scene_ir(
            scene or self.scene,
            policy=policy,
            allow_unattested_policy=policy is not None,
            today=TODAY,
        )

    def test_valid_multishot_dialogue_scene(self) -> None:
        self.assertIs(self.validate(), self.scene)
        self.assertIs(self.validate(policy=self.policy), self.scene)

    def test_unattested_policy_requires_explicit_fixture_opt_in(self) -> None:
        self.assertCode(
            "AVP004_UNATTESTED_POLICY_FORBIDDEN",
            lambda: av.validate_surface_av_policy(self.policy, today=TODAY),
        )
        checked = av.validate_surface_av_policy(
            self.policy,
            today=TODAY,
            allow_unattested_fixture=True,
            expected_surface_profile_sha256="d" * 64,
            expected_model_profile_sha256="e" * 64,
        )
        self.assertIs(checked, self.policy)

    def test_caller_cannot_self_authorize_evidence_policy(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["policy_kind"] = "evidence_pinned"
        policy["attestation"] = {
            "method": "evidence_registry",
            "verification_record_sha256": "1" * 64,
        }
        self.assertCode(
            "AVP005_POLICY_UNTRUSTED",
            lambda: av.validate_surface_av_policy(policy, today=TODAY),
        )

    def test_trusted_policy_binding_covers_the_complete_canonical_record(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["policy_kind"] = "evidence_pinned"
        policy["attestation"] = {
            "method": "evidence_registry",
            "verification_record_sha256": "1" * 64,
        }
        policy_sha256 = __import__("hashlib").sha256(av.canonical_json(policy)).hexdigest()
        with mock.patch.dict(av.TRUSTED_POLICY_BINDINGS, {policy["policy_id"]: policy_sha256}):
            self.assertIs(av.validate_surface_av_policy(policy, today=TODAY), policy)
            tampered = copy.deepcopy(policy)
            tampered["region"] = "GB"
            self.assertCode(
                "AVP005_POLICY_UNTRUSTED",
                lambda: av.validate_surface_av_policy(tampered, today=TODAY),
            )

    def test_evidence_expiry_is_exclusive(self) -> None:
        expires = date.fromisoformat(self.policy["evidence_pins"][0]["expires_at"])
        self.assertCode(
            "AVP015_EVIDENCE_EXPIRED",
            lambda: av.validate_surface_av_policy(
                self.policy,
                today=expires,
                allow_unattested_fixture=True,
            ),
        )

    def test_supported_policy_cannot_hide_unknown_region_or_provider_locale(self) -> None:
        for field in ("region", "provider_locale"):
            with self.subTest(field=field):
                policy = copy.deepcopy(self.policy)
                policy[field] = "unknown"
                self.assertCode(
                    "AVP028_SURFACE_SCOPE_UNKNOWN",
                    lambda policy=policy: av.validate_surface_av_policy(
                        policy,
                        today=TODAY,
                        allow_unattested_fixture=True,
                    ),
                )

    def test_policy_profile_hashes_are_exactly_bound(self) -> None:
        self.assertCode(
            "AVP010_SURFACE_PROFILE_HASH_MISMATCH",
            lambda: av.validate_surface_av_policy(
                self.policy,
                today=TODAY,
                allow_unattested_fixture=True,
                expected_surface_profile_sha256="0" * 64,
            ),
        )

    def test_state_beat_sets_are_disjoint_and_current_beats_are_complete(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["state_binding"]["reserved_future_beat_ids"].append("beat_line")
        self.assertCode("AV003_STATE_BEAT_OVERLAP", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["state_binding"]["current_beat_ids"].append("beat_uncovered")
        self.assertCode("AV099_CURRENT_BEAT_COVERAGE", lambda: self.validate(scene))

    def test_event_audio_and_transition_cannot_leak_future_beats(self) -> None:
        mutations = (
            ("event", lambda scene: scene["shots"][0]["events"][0]["beat_ids"].__setitem__(0, "beat_after"), "AV029_EVENT_BEAT_OUT_OF_SCOPE"),
            ("audio", lambda scene: scene["audio_events"][0]["beat_ids"].__setitem__(0, "beat_after"), "AV067_AUDIO_BEAT_OUT_OF_SCOPE"),
            ("transition", lambda scene: scene["transitions"][0]["beat_ids"].__setitem__(0, "beat_after"), "AV058_TRANSITION_BEAT_OUT_OF_SCOPE"),
        )
        for label, mutate, code in mutations:
            with self.subTest(label=label):
                scene = copy.deepcopy(self.scene)
                mutate(scene)
                self.assertCode(code, lambda scene=scene: self.validate(scene))

    def test_take_structure_and_transition_chain_fail_closed(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["take_structure"] = "single_continuous_take"
        self.assertCode("AV020_CONTINUOUS_TAKE_SHOT_COUNT", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["transitions"] = []
        self.assertCode("AV052_TRANSITION_CHAIN_INCOMPLETE", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["transitions"][0]["transition_type"] = "continuous_move"
        self.assertCode("AV056_TRANSITION_TYPE_INVALID", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["transitions"][0]["to_event_id"] = "shot_02_end"
        self.assertCode("AV057_TRANSITION_BOUNDARY_INVALID", lambda: self.validate(scene))

    def test_cross_shot_audio_requires_contiguous_scope_and_every_bridge(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["audio_events"][1]["shot_ids"] = ["shot_02", "shot_01"]
        self.assertCode("AV066_AUDIO_SHOT_SCOPE_NONCONTIGUOUS", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["transitions"][0]["audio_bridge_event_ids"] = []
        self.assertCode("AV086_AUDIO_BRIDGE_COVERAGE", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["transitions"][0]["audio_bridge_event_ids"] = ["detective_line"]
        self.assertCode("AV085_AUDIO_BRIDGE_INVALID", lambda: self.validate(scene))

    def test_speech_turns_are_contiguous(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["audio_events"][0]["speech"]["turn_index"] = 2
        self.assertCode("AV084_SPEECH_TURNS_NONCONTIGUOUS", lambda: self.validate(scene))

    def test_utterance_hash_uses_exact_raw_utf8_bytes(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["audio_events"][0]["speech"]["utterance"] = "I found it!"
        self.assertCode("AV077_UTTERANCE_HASH_MISMATCH", lambda: self.validate(scene))

    def test_utterance_rejects_provider_tokens_and_unsafe_unicode(self) -> None:
        for utterance, code in (
            ("Say @Image1 now", "AV032_UTTERANCE_TOKEN_FORBIDDEN"),
            ("Say @ Image: 1 now", "AV032_UTTERANCE_TOKEN_FORBIDDEN"),
            ("说 @图片1", "AV032_UTTERANCE_TOKEN_FORBIDDEN"),
            ("Say <audio:2> now", "AV032_UTTERANCE_TOKEN_FORBIDDEN"),
            ("safe\u202Eunsafe", "AV033_UTTERANCE_UNSAFE_UNICODE"),
            ("safe\u200Bunsafe", "AV033_UTTERANCE_UNSAFE_UNICODE"),
            ("line one\nline two", "AV031_UTTERANCE_INVALID"),
        ):
            with self.subTest(code=code):
                scene = copy.deepcopy(self.scene)
                scene["audio_events"][0]["speech"]["utterance"] = utterance
                self.assertCode(code, lambda scene=scene: self.validate(scene))

    def test_spoken_language_is_bcp47_subset_not_prompt_locale(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["audio_events"][0]["speech"]["spoken_language"] = "cmn-Hans-CN"
        utterance = "我找到了。"
        scene["audio_events"][0]["speech"]["utterance"] = utterance
        scene["audio_events"][0]["speech"]["utterance_sha256"] = __import__("hashlib").sha256(utterance.encode("utf-8")).hexdigest()
        self.validate(scene)

        scene["audio_events"][0]["speech"]["spoken_language"] = "ZH_hans"
        self.assertCode("AV030_LANGUAGE_TAG_INVALID", lambda: self.validate(scene))

    def test_exact_resolved_speaker_and_dialogue_scope(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["audio_events"][0]["source_entity_ids"] = ["woman"]
        self.assertCode("AV076_SPEECH_SOURCE_MISMATCH", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["audio_events"][0]["shot_ids"] = ["shot_01", "shot_02"]
        self.assertCode("AV075_DIALOGUE_SPEAKER_OR_SCOPE_INVALID", lambda: self.validate(scene))

    def test_voice_reference_is_authorization_gated(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["speakers"][0]["voice"] = {
            "mode": "authorized_reference",
            "authority_target_id": "detective",
            "asset_id": "voice_ref",
            "authorization_status": "unknown",
            "attestation_sha256": None,
        }
        self.assertCode("AV017_VOICE_REFERENCE_UNAUTHORIZED", lambda: self.validate(scene))

        scene = copy.deepcopy(self.scene)
        scene["speakers"][0]["voice"] = {
            "mode": "authorized_reference",
            "authority_target_id": "woman",
            "asset_id": "voice_ref",
            "authorization_status": "user_attested_authorized",
            "attestation_sha256": "1" * 64,
        }
        self.assertCode("AV017_VOICE_REFERENCE_UNAUTHORIZED", lambda: self.validate(scene))

    def test_post_dub_requires_post_only_lip_sync(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["speakers"][0]["voice"] = {
            "mode": "post_dub",
            "authority_target_id": None,
            "asset_id": None,
            "authorization_status": "unknown",
            "attestation_sha256": None,
        }
        scene["audio_events"][0]["speech"]["lip_sync"] = "not_required"
        self.assertCode("AV082_POST_DUB_EMISSION_INVALID", lambda: self.validate(scene))

    def test_generated_in_picture_subtitles_have_no_legal_mode(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["subtitle_policy"]["mode"] = "generated_in_picture"
        self.assertCode("AV090_SUBTITLE_MODE_INVALID", lambda: self.validate(scene))

    def test_exact_ranges_require_a_supported_evidence_bound_policy(self) -> None:
        scene = copy.deepcopy(self.scene)
        scene["timing_policy"] = "surface_exact_ranges"
        for index, audio in enumerate(scene["audio_events"], start=1):
            audio["timing"] = {
                "mode": "surface_exact_range",
                "start_event_id": None,
                "end_event_id": None,
                "cue_event_id": None,
                "beat_label": None,
                "start_seconds": float(index - 1),
                "end_seconds": float(index),
                "evidence_claim_ids": ["fixture.av.preview"],
            }
        self.assertCode("AV087_EXACT_TIMING_POLICY_REQUIRED", lambda: self.validate(scene))
        self.assertCode(
            "AV088_EXACT_TIMING_UNSUPPORTED",
            lambda: self.validate(scene, self.policy),
        )

    def test_every_endpoint_audio_event_and_transition_requires_acceptance(self) -> None:
        for field, value in (
            ("event_ids", ["shot_01_end"]),
            ("audio_event_ids", ["detective_line"]),
            ("transition_ids", []),
        ):
            with self.subTest(field=field):
                scene = copy.deepcopy(self.scene)
                scene["acceptance_tests"][0][field] = value
                self.assertCode("AV106_ACCEPTANCE_COVERAGE_INCOMPLETE", lambda scene=scene: self.validate(scene))

    def test_cli_diagnostics_do_not_echo_attacker_values(self) -> None:
        scene = copy.deepcopy(self.scene)
        marker = "DO_NOT_ECHO_ATTACKER_VALUE"
        scene["audio_events"][0]["speech"]["utterance"] = f"@Image7 {marker}"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scene.json"
            path.write_text(json.dumps(scene), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-S", "-B", str(ROOT / "scripts" / "scene_ir_v2_check.py"), str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AV032_UTTERANCE_TOKEN_FORBIDDEN", result.stderr)
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_parser_bounds_duplicates_and_nonfinite_numbers(self) -> None:
        self.assertCode("AV210_JSON_DUPLICATE_KEY", lambda: av.parse_json_bytes(b'{"x":1,"x":2}'))
        self.assertCode("AV213_JSON_NUMBER_INVALID", lambda: av.parse_json_bytes(b'{"x":NaN}'))
        self.assertCode("AV211_JSON_TOO_LARGE", lambda: av.parse_json_bytes(b" " * (av.MAX_INPUT_BYTES + 1)))

    def test_self_test_is_stable_in_ten_fresh_processes(self) -> None:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for seed in ("0", "1", "2", "3", "7", "11", "42", "101", "709", "999"):
            env["PYTHONHASHSEED"] = seed
            result = subprocess.run(
                [sys.executable, "-S", "-B", str(ROOT / "scripts" / "scene_ir_v2_check.py"), "--self-test"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
