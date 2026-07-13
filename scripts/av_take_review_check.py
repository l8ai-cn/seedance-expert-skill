#!/usr/bin/env python3
"""Dependency-free AV take-review companion and strict bundle validator."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable


TAKE_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/take-review-v2.schema.json"
SCENE_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/scene-ir-v2.schema.json"
AV_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/av-take-review-v1.schema.json"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 100_000
BUNDLE_KEYS = {"take_review_v2", "scene_ir_v2", "av_take_review"}
SPEECH_FUNCTIONS = {"dialogue", "voiceover"}
ACCEPTED_BASE = {
    ("final", "accepted", "accept"),
    ("final", "accepted_with_deviation", "accept_with_deviation"),
}


class InputFailure(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputFailure("AVR004_DUPLICATE_KEY", "duplicate object keys are forbidden")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise InputFailure("AVR005_NONFINITE_NUMBER", "non-finite JSON numbers are forbidden")


def _resource_check(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise InputFailure("AVR006_RESOURCE_LIMIT", "document structure exceeds the bounded resource limit")
        if isinstance(current, float) and not math.isfinite(current):
            raise InputFailure("AVR005_NONFINITE_NUMBER", "non-finite JSON numbers are forbidden")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def parse_document(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_INPUT_BYTES:
        raise InputFailure("AVR001_INPUT_TOO_LARGE", "input exceeds the bounded byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputFailure("AVR002_INVALID_UTF8", "input must be valid UTF-8") from exc
    if text.startswith("\ufeff"):
        raise InputFailure("AVR003_BOM_FORBIDDEN", "UTF-8 BOM is forbidden")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except InputFailure:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError) as exc:
        raise InputFailure("AVR007_INVALID_JSON", "input must be bounded strict JSON") from exc
    if not isinstance(value, dict):
        raise InputFailure("AVR008_ROOT_NOT_OBJECT", "document root must be an object")
    _resource_check(value)
    return value


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def utterance_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _error(errors: set[str], code: str, message: str) -> None:
    errors.add(f"{code}: {message}")


def _aux_module() -> Any:
    try:
        from scripts import v2_aux_check as aux
    except ImportError:
        import v2_aux_check as aux  # type: ignore[no-redef]
    return aux


def _schema_valid(document: dict[str, Any], filename: str) -> bool:
    try:
        schema = parse_document((SCHEMA_ROOT / filename).read_bytes())
        aux = _aux_module()
        return bool(aux._schema_valid(document, schema, schema))
    except (OSError, InputFailure, ImportError, AttributeError):
        return False


def _validate_base(document: dict[str, Any]) -> bool:
    try:
        aux = _aux_module()
        return document.get("$schema") == TAKE_SCHEMA and not aux.validate_document(document)
    except Exception:
        return False


def _call_scene_validator(document: dict[str, Any]) -> bool | None:
    try:
        try:
            from scripts import scene_ir_v2_check as checker
        except ImportError:
            import scene_ir_v2_check as checker  # type: ignore[no-redef]
    except ImportError:
        return None
    candidates: tuple[str, ...] = ("validate_scene_ir_v2", "validate_scene_ir", "validate_document", "validate")
    for name in candidates:
        candidate: Callable[[dict[str, Any]], Any] | None = getattr(checker, name, None)
        if candidate is None:
            continue
        try:
            result = candidate(document)
        except Exception:
            return False
        return not isinstance(result, list) or not result
    return False


def _fallback_scene_shape(document: dict[str, Any]) -> bool:
    """Bounded extraction fallback for installations without the dedicated checker."""
    if document.get("$schema") != SCENE_SCHEMA or document.get("schema_version") != 2:
        return False
    state = document.get("state_binding")
    audio_events = document.get("audio_events")
    transitions = document.get("transitions")
    if not isinstance(state, dict) or not all(isinstance(state.get(key), str) for key in ("project_id", "clip_id")):
        return False
    if not isinstance(audio_events, list) or not isinstance(transitions, list):
        return False
    for event in audio_events:
        if not isinstance(event, dict) or not isinstance(event.get("audio_event_id"), str):
            return False
        function = event.get("semantic_function")
        speech = event.get("speech")
        if function in SPEECH_FUNCTIONS:
            if not isinstance(speech, dict):
                return False
            utterance = speech.get("utterance")
            if not isinstance(utterance, str) or speech.get("utterance_sha256") != utterance_sha256(utterance):
                return False
        elif speech is not None:
            return False
    return all(isinstance(item, dict) and isinstance(item.get("transition_id"), str) for item in transitions)


def _validate_scene(document: dict[str, Any]) -> bool:
    dependency_result = _call_scene_validator(document)
    if dependency_result is not None:
        return dependency_result
    if (SCHEMA_ROOT / "scene-ir-v2.schema.json").exists() and not _schema_valid(document, "scene-ir-v2.schema.json"):
        return False
    return _fallback_scene_shape(document)


def _ordered_ids(items: Any, key: str) -> list[str] | None:
    if not isinstance(items, list):
        return None
    values: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            return None
        values.append(item[key])
    return values


def _scene_contract(scene: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]] | None:
    state = scene.get("state_binding")
    audio = scene.get("audio_events")
    transitions = scene.get("transitions")
    if not isinstance(state, dict) or not isinstance(audio, list) or not isinstance(transitions, list):
        return None
    if not all(isinstance(item, dict) for item in audio + transitions):
        return None
    return state, audio, transitions


def _has_failure(av: dict[str, Any], base_state: str) -> bool:
    if base_state == "fail" or av.get("unexpected_in_picture_text") == "present":
        return True
    for result in av.get("speech_results", []):
        if result.get("utterance_status") in {"mismatch", "unheard"}:
            return True
        if any(result.get(key) == "fail" for key in ("speaker_status", "spoken_language_status", "lip_sync_status", "timing_status")):
            return True
    if any(result.get("result") == "fail" for result in av.get("audio_results", [])):
        return True
    return any(result.get("result") == "fail" for result in av.get("transition_results", []))


def _has_unknown(av: dict[str, Any], base_state: str) -> bool:
    if base_state == "pending" or av.get("unexpected_in_picture_text") == "unknown":
        return True
    for result in av.get("speech_results", []):
        if result.get("utterance_status") == "unknown":
            return True
        if any(result.get(key) == "unknown" for key in ("speaker_status", "spoken_language_status", "lip_sync_status", "timing_status")):
            return True
    if any(result.get("result") == "unknown" for result in av.get("audio_results", [])):
        return True
    return any(result.get("result") == "unknown" for result in av.get("transition_results", []))


def _base_state(base: dict[str, Any]) -> str:
    key = (base.get("decision_status"), base.get("source_status"), base.get("verdict"))
    if key in ACCEPTED_BASE:
        return "accepted"
    if base.get("decision_status") == "pending_confirmation":
        return "pending"
    return "fail"


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if set(bundle) != BUNDLE_KEYS:
        return ["AVR009_BUNDLE_MEMBERS: bundle requires exactly take_review_v2, scene_ir_v2, and av_take_review"]
    if any(not isinstance(bundle.get(key), dict) for key in BUNDLE_KEYS):
        return ["AVR010_BUNDLE_MEMBER_TYPE: every bundle member must be an object"]
    base = bundle["take_review_v2"]
    scene = bundle["scene_ir_v2"]
    av = bundle["av_take_review"]

    if not _validate_base(base):
        _error(errors, "AVR011_BASE_INVALID", "take-review-v2 failed its packaged dependency-free validator")
    if not _validate_scene(scene):
        _error(errors, "AVR012_SCENE_INVALID", "scene-ir-v2 failed its packaged dependency-free validator")
    if av.get("$schema") != AV_SCHEMA or not _schema_valid(av, "av-take-review-v1.schema.json"):
        _error(errors, "AVR013_REVIEW_INVALID", "AV take review does not satisfy its complete packaged schema contract")
    if errors:
        return sorted(errors)

    contract = _scene_contract(scene)
    if contract is None:
        return ["AVR012_SCENE_INVALID: scene-ir-v2 failed its packaged dependency-free validator"]
    state, audio_events, transitions = contract

    if av.get("take_review_v2_sha256") != canonical_sha256(base) or av.get("scene_ir_v2_sha256") != canonical_sha256(scene):
        _error(errors, "AVR100_HASH_BINDING", "canonical artifact hash binding does not match the bundle members")
    if (
        av.get("project_id") != base.get("project_id")
        or av.get("project_id") != state.get("project_id")
        or av.get("clip_id") != base.get("clip_id")
        or av.get("clip_id") != state.get("clip_id")
        or av.get("take_id") != base.get("take_id")
    ):
        _error(errors, "AVR101_ID_BINDING", "project, clip, or take identity does not match exactly")
    if av.get("media_kind") != base.get("media_kind") or av.get("base_verdict") != base.get("verdict"):
        _error(errors, "AVR102_BASE_BINDING", "media kind or base verdict does not match exactly")

    audio_ids = _ordered_ids(audio_events, "audio_event_id")
    transition_ids = _ordered_ids(transitions, "transition_id")
    speech_events = [event for event in audio_events if event.get("semantic_function") in SPEECH_FUNCTIONS]
    nonspeech_events = [event for event in audio_events if event.get("semantic_function") not in SPEECH_FUNCTIONS]
    speech_ids = _ordered_ids(speech_events, "audio_event_id")
    nonspeech_ids = _ordered_ids(nonspeech_events, "audio_event_id")
    result_speech_ids = _ordered_ids(av.get("speech_results"), "audio_event_id")
    result_audio_ids = _ordered_ids(av.get("audio_results"), "audio_event_id")
    result_transition_ids = _ordered_ids(av.get("transition_results"), "transition_id")
    if None in (audio_ids, transition_ids, speech_ids, nonspeech_ids, result_speech_ids, result_audio_ids, result_transition_ids):
        _error(errors, "AVR103_COVERAGE_SHAPE", "audio or transition coverage has an invalid identifier shape")
    else:
        if av.get("required_audio_event_ids") != audio_ids or result_speech_ids != speech_ids or result_audio_ids != nonspeech_ids:
            _error(errors, "AVR104_AUDIO_COVERAGE", "speech and nonspeech results must exactly cover scene audio events in canonical order")
        if av.get("required_transition_ids") != transition_ids or result_transition_ids != transition_ids:
            _error(errors, "AVR105_TRANSITION_COVERAGE", "transition results must exactly cover scene transitions in canonical order")

    expected_hashes: dict[str, str] = {}
    expected_lip_sync: dict[str, str] = {}
    for event in speech_events:
        speech = event.get("speech")
        if not isinstance(speech, dict) or not isinstance(speech.get("utterance"), str):
            _error(errors, "AVR106_SCENE_SPEECH", "a required speech event lacks an exact utterance contract")
            continue
        expected = utterance_sha256(speech["utterance"])
        if speech.get("utterance_sha256") != expected:
            _error(errors, "AVR107_SCENE_UTTERANCE_HASH", "scene utterance hash does not match exact UTF-8 speech bytes")
        expected_hashes[event["audio_event_id"]] = expected
        lip_sync = speech.get("lip_sync")
        if lip_sync not in {"required", "not_required", "post_only"}:
            _error(errors, "AVR106_SCENE_SPEECH", "a required speech event lacks a valid lip-sync contract")
        else:
            expected_lip_sync[event["audio_event_id"]] = lip_sync
    for result in av.get("speech_results", []):
        if isinstance(result, dict) and expected_hashes.get(result.get("audio_event_id")) != result.get("expected_utterance_sha256"):
            _error(errors, "AVR108_EXPECTED_UTTERANCE_BINDING", "review expected-utterance hash does not match the scene contract")

    if av.get("media_kind") == "video":
        for result in av.get("speech_results", []):
            if not isinstance(result, dict):
                continue
            required = expected_lip_sync.get(result.get("audio_event_id"))
            observed = result.get("lip_sync_status")
            if (required == "required" and observed == "not_required") or (
                required in {"not_required", "post_only"} and observed != "not_required"
            ):
                _error(errors, "AVR113_LIP_SYNC_BINDING", "review lip-sync status contradicts the scene speech contract")

    media_kind = av.get("media_kind")
    if media_kind == "final_frame":
        speech_overclaim = any(
            isinstance(result, dict)
            and (
                result.get("utterance_status") != "unknown"
                or any(result.get(key) != "unknown" for key in ("speaker_status", "spoken_language_status", "lip_sync_status", "timing_status"))
            )
            for result in av.get("speech_results", [])
        )
        other_overclaim = any(result.get("result") != "unknown" for result in av.get("audio_results", []) if isinstance(result, dict))
        transition_overclaim = any(result.get("result") != "unknown" for result in av.get("transition_results", []) if isinstance(result, dict))
        if speech_overclaim or other_overclaim or transition_overclaim or av.get("av_verdict") == "pass":
            _error(errors, "AVR109_FINAL_FRAME_OVERCLAIM", "a final frame cannot establish any audiovisual or transition result")

    base_state = _base_state(base)
    failure = _has_failure(av, base_state)
    unknown = _has_unknown(av, base_state) or media_kind == "final_frame"
    expected_verdict = "fail" if failure else "pending" if unknown else "pass"
    if av.get("av_verdict") != expected_verdict:
        _error(errors, "AVR110_VERDICT_DERIVATION", "AV verdict does not match failure-first and unknown-second derivation")
    expected_confirmation = expected_verdict == "pending"
    if av.get("requires_user_confirmation") is not expected_confirmation:
        _error(errors, "AVR111_CONFIRMATION_DERIVATION", "user-confirmation state does not match the derived AV verdict")
    if av.get("av_verdict") == "pass" and (media_kind != "video" or base_state != "accepted"):
        _error(errors, "AVR112_FALSE_PASS", "AV pass requires reviewed video and a terminally accepted base take")
    return sorted(errors)


def _self_test_bundle() -> dict[str, Any]:
    utterance = "Hold steady."
    base = {
        "$schema": TAKE_SCHEMA,
        "schema_version": 2,
        "project_id": "self_test",
        "clip_id": "clip_01",
        "take_id": "take_01",
        "decision_status": "final",
        "source_status": "accepted",
        "verdict": "accept",
        "media_kind": "video",
        "accepted_media_sha256": "a" * 64,
        "observed_start_snapshot_sha256": "b" * 64,
        "observed_end_snapshot_sha256": "c" * 64,
        "endpoint_states": [{"endpoint_id": "end", "owner_kind": "shot", "owner_id": "shot_01", "completion_mode": "held_static", "carry_forward": False, "description": "The shot is complete."}],
        "completed_beat_ids": ["beat_01"],
        "incomplete_beat_ids": [],
        "unexpected_completed_beat_ids": [],
        "continuity_break_ids": [],
        "accepted_deviation_ids": [],
        "observation_confidence": "high",
        "uncertainties": [],
        "requires_user_confirmation": False,
    }
    event_base = {
        "actor_ids": ["performer"],
        "target_ids": ["room"],
        "interaction_kind": "none",
        "material_ids": [],
    }
    timing_base = {
        "cue_event_id": None,
        "beat_label": None,
        "start_seconds": None,
        "end_seconds": None,
        "evidence_claim_ids": [],
    }
    scene = {
        "$schema": SCENE_SCHEMA,
        "schema_version": 2,
        "state_binding": {
            "project_id": "self_test",
            "clip_id": "clip_01",
            "state_revision": 1,
            "canon_revision": 1,
            "semantic_state_sha256": "d" * 64,
            "planned_start_snapshot_sha256": "e" * 64,
            "planned_end_snapshot_sha256": "f" * 64,
            "completed_beat_ids": ["beat_before"],
            "current_beat_ids": ["beat_line", "beat_reaction"],
            "reserved_future_beat_ids": ["beat_after"],
        },
        "take_structure": "edited_multi_shot",
        "timing_policy": "ordered_phases",
        "entities": [
            {"entity_id": "performer", "label": "performer", "kind": "character", "stable_features": ["same performer"]},
            {"entity_id": "room", "label": "quiet room", "kind": "environment", "stable_features": ["same room"]},
        ],
        "materials": [],
        "speakers": [{
            "speaker_id": "speaker_01",
            "entity_id": "performer",
            "role": "onscreen_character",
            "display_name": "Performer",
            "voice": {"mode": "generic_synthetic", "authority_target_id": None, "asset_id": None, "authorization_status": "not_applicable", "attestation_sha256": None},
        }],
        "shots": [
            {
                "shot_id": "shot_01",
                "shot_index": 1,
                "opening_event_id": "shot_01.open",
                "endpoint_event_id": "shot_01.end",
                "events": [
                    {**event_base, "event_id": "shot_01.open", "event_index": 1, "phase": "opening_state", "depends_on": [], "visible_state_change": "The performer faces the camera.", "beat_ids": ["beat_line"]},
                    {**event_base, "event_id": "shot_01.end", "event_index": 2, "phase": "endpoint", "depends_on": ["shot_01.open"], "visible_state_change": "The performer finishes the line and holds.", "beat_ids": ["beat_line"]},
                ],
                "camera": {"move_kind": "locked", "start_framing": "Medium close-up.", "path": "No movement.", "speed": "static", "subject_relationship": "The face remains visible.", "endpoint_framing": "Medium close-up hold.", "observed_event_ids": ["shot_01.open", "shot_01.end"], "occlusion_risks": [], "mitigations": []},
            },
            {
                "shot_id": "shot_02",
                "shot_index": 2,
                "opening_event_id": "shot_02.open",
                "endpoint_event_id": "shot_02.end",
                "events": [
                    {**event_base, "event_id": "shot_02.open", "event_index": 1, "phase": "opening_state", "depends_on": [], "visible_state_change": "The second view opens on the same performer.", "beat_ids": ["beat_reaction"]},
                    {**event_base, "event_id": "shot_02.end", "event_index": 2, "phase": "endpoint", "depends_on": ["shot_02.open"], "visible_state_change": "The performer remains still at the endpoint.", "beat_ids": ["beat_reaction"]},
                ],
                "camera": {"move_kind": "locked", "start_framing": "Medium side view.", "path": "No movement.", "speed": "static", "subject_relationship": "The performer remains readable.", "endpoint_framing": "Medium side-view hold.", "observed_event_ids": ["shot_02.open", "shot_02.end"], "occlusion_risks": [], "mitigations": []},
            },
        ],
        "transitions": [{"transition_id": "cut_01", "transition_index": 1, "from_shot_id": "shot_01", "to_shot_id": "shot_02", "transition_type": "hard_cut", "from_event_id": "shot_01.end", "to_event_id": "shot_02.open", "beat_ids": ["beat_reaction"], "preserved_invariant_ids": ["performer.same"], "allowed_change_event_ids": ["shot_02.open", "shot_02.end"], "audio_bridge_event_ids": ["room_01"]}],
        "audio_events": [
            {
                "audio_event_id": "line_01", "audio_event_index": 1, "semantic_function": "dialogue", "shot_ids": ["shot_01"], "beat_ids": ["beat_line"], "source_entity_ids": ["performer"],
                "timing": {**timing_base, "mode": "visual_event_window", "start_event_id": "shot_01.open", "end_event_id": "shot_01.end"},
                "description": "The performer says the exact line.",
                "speech": {"speaker_id": "speaker_01", "spoken_language": "en", "utterance": utterance, "utterance_sha256": utterance_sha256(utterance), "turn_index": 1, "overlap_policy": "no_overlap", "lip_sync": "required", "delivery_intent": "Calm and clear."},
            },
            {
                "audio_event_id": "room_01", "audio_event_index": 2, "semantic_function": "ambience", "shot_ids": ["shot_01", "shot_02"], "beat_ids": ["beat_line", "beat_reaction"], "source_entity_ids": ["room"],
                "timing": {**timing_base, "mode": "continuous_sequence", "start_event_id": None, "end_event_id": None},
                "description": "Quiet room tone continues across the cut.", "speech": None,
            },
        ],
        "subtitle_policy": {"mode": "none", "target_language_tags": [], "picture_policy": "not_applicable"},
        "requested_invariants": [{"invariant_id": "performer.same", "entity_ids": ["performer"], "description": "The performer remains the same across the cut."}],
        "known_fragilities": [{"fragility_id": "av.review", "event_ids": ["shot_01.end", "shot_02.open"], "audio_event_ids": ["line_01", "room_01"], "transition_ids": ["cut_01"], "description": "Review speech, ambience, and the cut separately."}],
        "acceptance_tests": [{"acceptance_id": "av.complete", "event_ids": ["shot_01.end", "shot_02.end"], "audio_event_ids": ["line_01", "room_01"], "transition_ids": ["cut_01"], "observable": "Both endpoints, all required audio, and the cut can be reviewed.", "pass_condition": "The exact line, room tone, and hard cut each pass review."}],
        "post_fallbacks": [{"fallback_id": "post.audio", "trigger_acceptance_ids": ["av.complete"], "action": "Route failed speech or audio to authorized post-production."}],
    }
    av = {
        "$schema": AV_SCHEMA,
        "schema_version": 1,
        "project_id": "self_test",
        "clip_id": "clip_01",
        "take_id": "take_01",
        "take_review_v2_sha256": canonical_sha256(base),
        "scene_ir_v2_sha256": canonical_sha256(scene),
        "media_kind": "video",
        "base_verdict": "accept",
        "required_audio_event_ids": ["line_01", "room_01"],
        "required_transition_ids": ["cut_01"],
        "speech_results": [{"audio_event_id": "line_01", "expected_utterance_sha256": utterance_sha256(utterance), "utterance_status": "exact", "speaker_status": "pass", "spoken_language_status": "pass", "lip_sync_status": "pass", "timing_status": "pass"}],
        "audio_results": [{"audio_event_id": "room_01", "result": "pass"}],
        "transition_results": [{"transition_id": "cut_01", "result": "pass"}],
        "unexpected_in_picture_text": "absent",
        "av_verdict": "pass",
        "requires_user_confirmation": False,
    }
    return {"take_review_v2": base, "scene_ir_v2": scene, "av_take_review": av}


def self_test() -> list[str]:
    failures: list[str] = []
    bundle = _self_test_bundle()
    if validate_bundle(bundle):
        failures.append("valid AV bundle failed")
    duplicate = b'{"take_review_v2":{},"take_review_v2":{},"scene_ir_v2":{},"av_take_review":{}}'
    try:
        parse_document(duplicate)
        failures.append("duplicate key passed")
    except InputFailure as exc:
        if exc.code != "AVR004_DUPLICATE_KEY":
            failures.append("duplicate-key diagnostic changed")
    tampered = json.loads(json.dumps(bundle))
    tampered["av_take_review"]["take_review_v2_sha256"] = "0" * 64
    if not any(error.startswith("AVR100_") for error in validate_bundle(tampered)):
        failures.append("tampered hash passed")
    return failures


def _read(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    try:
        with Path(path).open("rb") as handle:
            return handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise InputFailure("AVR014_READ_ERROR", "input could not be read") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="strict bundle JSON; omit or use - for stdin")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        if failures:
            for failure in failures:
                print(f"ERROR AVR900_SELF_TEST: {failure}")
            return 1
        print("AV take-review self-test passed.")
        return 0
    try:
        bundle = parse_document(_read(args.path))
        errors = validate_bundle(bundle)
    except InputFailure as exc:
        errors = [f"{exc.code}: {exc.message}"]
    for error in errors:
        print(f"ERROR bundle {error}", file=sys.stderr)
    if errors:
        return 1
    print("AV take-review bundle check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
