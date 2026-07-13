from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import render_surface_bindings as bindings
import semantic_lint_v2 as lint


def fixture() -> dict:
    return json.loads((ROOT / "validation/fixtures/prompt-compile-request-v2.valid.json").read_text(encoding="utf-8"))


def rebind_scene(request: dict) -> None:
    request["realization_catalog"]["scene_ir_sha256"] = lint._canonical_sha(request["scene_ir"])


def rebind_policy(request: dict) -> None:
    request["surface_binding_set"]["surface_av_policy_sha256"] = lint._canonical_sha(request["surface_av_policy"])


class SemanticLintV2Tests(unittest.TestCase):
    def assert_error(self, request: dict, code: str, *, today: date | None = None) -> None:
        with self.assertRaises(bindings.BindingError) as caught:
            lint.compile_program(request, allow_unattested_fixture=True, today=today)
        self.assertEqual(caught.exception.code, code)

    def test_unattested_policy_is_default_closed_and_opt_in_is_labeled(self) -> None:
        with self.assertRaises(bindings.BindingError) as caught:
            lint.compile_program(fixture())
        self.assertEqual(caught.exception.code, "AVP004_UNATTESTED_POLICY_FORBIDDEN")
        program = lint.compile_program(fixture(), allow_unattested_fixture=True)
        self.assertEqual(program["status"], "unattested_fixture_preview")
        self.assertEqual(program["policy_provenance"]["policy_kind"], "unattested_fixture")

    def test_program_binds_state_order_policy_and_all_emission_classes(self) -> None:
        program = lint.compile_program(fixture(), allow_unattested_fixture=True)
        self.assertEqual(program["state_binding_sha256"], lint._canonical_sha(program["state_binding"]))
        self.assertEqual(program["ordering"]["transition_ids"], ["cut_01_02"])
        self.assertEqual(program["ordering"]["speech_turn_indices"], [1])
        emissions = {unit["emission"] for unit in program["units"]}
        self.assertEqual(emissions, {"prompt", "post_only", "review_only", "request_carried"})
        speech = next(item for item in program["units"] if item["kind"] == "exact_speech")
        self.assertIsNone(speech["semantic_key"])

    def test_utterance_hash_unicode_and_provider_injection_fail(self) -> None:
        wrong_hash = fixture()
        wrong_hash["scene_ir"]["audio_events"][0]["speech"]["utterance"] = "I found this."
        rebind_scene(wrong_hash)
        self.assert_error(wrong_hash, "AV077_UTTERANCE_HASH_MISMATCH")

        nfd = fixture()
        speech = nfd["scene_ir"]["audio_events"][0]["speech"]
        speech["utterance"] = "Cafe\u0301"
        speech["utterance_sha256"] = bindings.sha256_bytes(speech["utterance"].encode("utf-8"))
        rebind_scene(nfd)
        self.assert_error(nfd, "AV033_UTTERANCE_UNSAFE_UNICODE")

        token = fixture()
        speech = token["scene_ir"]["audio_events"][0]["speech"]
        speech["utterance"] = "Use @Audio1."
        speech["utterance_sha256"] = bindings.sha256_bytes(speech["utterance"].encode("utf-8"))
        rebind_scene(token)
        self.assert_error(token, "AV032_UTTERANCE_TOKEN_FORBIDDEN")

    def test_speaker_turn_transition_and_future_beat_mutations_fail(self) -> None:
        speaker = fixture()
        speaker["scene_ir"]["audio_events"][0]["speech"]["speaker_id"] = "missing"
        rebind_scene(speaker)
        self.assert_error(speaker, "AV074_SPEECH_SPEAKER_UNKNOWN")

        turn = fixture()
        turn["scene_ir"]["audio_events"][0]["speech"]["turn_index"] = 2
        rebind_scene(turn)
        self.assert_error(turn, "AV084_SPEECH_TURNS_NONCONTIGUOUS")

        transition = fixture()
        transition["scene_ir"]["transitions"][0]["from_shot_id"] = "shot_02"
        rebind_scene(transition)
        self.assert_error(transition, "AV055_TRANSITION_NOT_ADJACENT")

        future = fixture()
        future["scene_ir"]["shots"][0]["events"][0]["beat_ids"] = ["beat_after"]
        rebind_scene(future)
        self.assert_error(future, "AV029_EVENT_BEAT_OUT_OF_SCOPE")

    def test_policy_binding_exact_timing_and_expiry_fail_closed(self) -> None:
        mismatch = fixture()
        mismatch["surface_binding_set"]["profile_id"] = "other.surface"
        self.assert_error(mismatch, "AVP005_POLICY_BINDING_MISMATCH")

        timing = fixture()
        timing["scene_ir"]["timing_policy"] = "surface_exact_ranges"
        for audio in timing["scene_ir"]["audio_events"]:
            audio["timing"].update({"mode": "surface_exact_range", "start_event_id": None, "end_event_id": None, "cue_event_id": None, "beat_label": None, "start_seconds": 0, "end_seconds": 1, "evidence_claim_ids": ["fixture.av.preview"]})
        rebind_scene(timing)
        self.assert_error(timing, "AV088_EXACT_TIMING_UNSUPPORTED")

        self.assert_error(fixture(), "AVP015_EVIDENCE_EXPIRED", today=date(2099, 12, 31))

    def test_authorized_voice_requires_the_speaker_target_and_an_audio_binding(self) -> None:
        unused = fixture()
        unused["surface_binding_set"]["bindings"].append({
            "binding_id": "unused_picture",
            "media_type": "image",
        })
        self.assert_error(unused, "BINDING_UNUSED")

        request = fixture()
        request["surface_av_policy"]["audio"]["voice_modes"].append("authorized_reference")
        request["surface_av_policy"]["audio"]["voice_reference_status"] = "supported"
        rebind_policy(request)
        request["scene_ir"]["speakers"][0]["voice"] = {
            "mode": "authorized_reference",
            "authority_target_id": "detective",
            "asset_id": "picture_ref",
            "authorization_status": "user_attested_authorized",
            "attestation_sha256": "1" * 64,
        }
        rebind_scene(request)
        self.assert_error(request, "REF010_VOICE_NOT_AUTHORIZED")

        request["surface_binding_set"]["bindings"].append({
            "binding_id": "voice_ref",
            "media_type": "audio",
        })
        request["scene_ir"]["speakers"][0]["voice"]["asset_id"] = "voice_ref"
        rebind_scene(request)
        program = lint.compile_program(request, allow_unattested_fixture=True)
        self.assertEqual(program["status"], "unattested_fixture_preview")

    def test_catalog_order_source_hash_and_exact_speech_exclusion(self) -> None:
        request = fixture()
        request["realization_catalog"]["entries"][0]["source_sha256"] = "0" * 64
        self.assert_error(request, "PRM025_LOCALE_CATALOG_INVALID")
        keys = [row["semantic_key"] for row in fixture()["realization_catalog"]["entries"]]
        self.assertFalse(any("utterance" in key for key in keys))
        self.assertIn("audio.detective_line.delivery_intent", keys)

    def test_localized_speaker_labels_cannot_collapse_distinct_speakers(self) -> None:
        request = fixture()
        request["scene_ir"]["speakers"].append({
            "speaker_id": "woman_voice",
            "entity_id": "woman",
            "role": "onscreen_character",
            "display_name": "Woman",
            "voice": {
                "mode": "generic_synthetic",
                "authority_target_id": None,
                "asset_id": None,
                "authorization_status": "not_applicable",
                "attestation_sha256": None,
            },
        })
        entries = request["realization_catalog"]["entries"]
        insert_at = next(
            index + 1
            for index, entry in enumerate(entries)
            if entry["semantic_key"] == "speaker.detective_voice.display_name"
        )
        entries.insert(insert_at, {
            "semantic_key": "speaker.woman_voice.display_name",
            "source_sha256": bindings.sha256_bytes(b"Woman"),
            "en": "detective",
            "zh_hans": "侦探",
        })
        rebind_scene(request)
        self.assert_error(request, "AUDIO016_SPEAKER_LABEL_COLLISION")

    def test_cli_is_deterministic_non_echoing_and_default_closed(self) -> None:
        raw = json.dumps(fixture(), ensure_ascii=False).encode("utf-8")
        script = ROOT / "scripts/semantic_lint_v2.py"
        completed = subprocess.run([sys.executable, "-B", str(script), "--preview-candidate"], cwd=ROOT, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(completed.returncode, 1)
        self.assertIn(b"AVP004_UNATTESTED_POLICY_FORBIDDEN", completed.stderr)
        hostile = fixture()
        hostile["private-sentinel"] = "sk-private-sentinel-value"
        completed = subprocess.run([sys.executable, "-B", str(script), "--preview-candidate", "--allow-unattested-fixture"], cwd=ROOT, input=json.dumps(hostile).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertNotIn(b"private-sentinel", completed.stderr)
        self.assertNotIn(b"sk-private", completed.stderr)
        self.assertNotIn(b"Traceback", completed.stderr)

        expected = None
        for seed in (0, 1, 2, 3, 7, 11, 42, 101, 709, 999):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            completed = subprocess.run([sys.executable, "-B", str(script), "--preview-candidate", "--allow-unattested-fixture"], cwd=ROOT, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            expected = completed.stdout if expected is None else expected
            self.assertEqual(completed.stdout, expected)


if __name__ == "__main__":
    unittest.main()
