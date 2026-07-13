#!/usr/bin/env python3
"""Validate and lower the V7-09 AV contracts to a prompt program.

This module is an offline candidate-preview compiler stage.  It deliberately
does not activate a provider, derive provider tokens, translate utterances, or
read media.  Diagnostics are stable and never echo caller-controlled values.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from . import render_surface_bindings as bindings
    from . import scene_ir_v2_check as av_check
    from . import semantic_lint as v1_lint
except ImportError:  # pragma: no cover - CLI path
    import render_surface_bindings as bindings
    import scene_ir_v2_check as av_check
    import semantic_lint as v1_lint


ROOT = Path(__file__).resolve().parents[1]
REQUEST_URI = "https://github.com/Emily2040/seedance-2.0/schemas/prompt-compile-request-v2.schema.json"
SCENE_URI = "https://github.com/Emily2040/seedance-2.0/schemas/scene-ir-v2.schema.json"
POLICY_URI = "https://github.com/Emily2040/seedance-2.0/schemas/surface-av-policy.schema.json"
CATALOG_URI = "https://github.com/Emily2040/seedance-2.0/schemas/prompt-realization-catalog-v2.schema.json"
PROGRAM_URI = "https://github.com/Emily2040/seedance-2.0/schemas/prompt-program-v2.schema.json"
BINDING_SET_URI = "https://github.com/Emily2040/seedance-2.0/schemas/surface-binding-set-v2.schema.json"

REQUEST_KEYS = {"$schema", "schema_version", "scene_ir", "surface_av_policy", "surface_binding_set", "realization_catalog"}
SCENE_KEYS = {"$schema", "schema_version", "state_binding", "take_structure", "timing_policy", "entities", "materials", "speakers", "shots", "transitions", "audio_events", "subtitle_policy", "requested_invariants", "known_fragilities", "acceptance_tests", "post_fallbacks"}
POLICY_KEYS = {"$schema", "schema_version", "policy_id", "policy_kind", "attestation", "status", "runtime_enabled", "preview_only", "profile_id", "operation", "model_profile_id", "model_variant", "region", "provider_locale", "surface_profile_sha256", "model_profile_sha256", "prompt_locales", "multi_shot", "audio", "exact_timing", "evidence_pins"}
CATALOG_KEYS = {"$schema", "schema_version", "scene_ir_sha256", "attestation", "entries"}
ATTESTATION_KEYS = {"method", "linguistic_equivalence", "locales"}
ENTRY_KEYS = {"semantic_key", "source_sha256", "en", "zh_hans"}
MULTI_KEYS = {"status", "grammar", "max_shots", "transition_types"}
AUDIO_POLICY_KEYS = {"status", "semantic_functions", "voice_modes", "voice_reference_status"}
EXACT_KEYS = {"status", "range_unit", "evidence_claim_ids"}
PIN_KEYS = {"claim_id", "claim_sha256", "expires_at"}
POLICY_ATTESTATION_KEYS = {"method", "verification_record_sha256"}
BINDING_SET_KEYS = {"$schema", "schema_version", "policy_id", "surface_av_policy_sha256", "profile_id", "operation", "bindings"}

SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")
CLAIM_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
LANGUAGE_TAG = re.compile(r"^[a-z]{2,8}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SEMANTIC_FUNCTIONS = {"dialogue", "voiceover", "sound_effect", "ambience", "music", "rhythm", "silence"}
VOICE_MODES = {"generic_synthetic", "authorized_reference", "post_dub"}
TRANSITION_TYPES = {"hard_cut", "match_cut", "dissolve", "fade"}
GRAMMARS = {"none", "ascii_numbered_shot_labels", "localized_numbered_shot_labels", "ordered_paragraphs"}
TIMING_POLICIES = {"ordered_phases", "relative_beats", "surface_exact_ranges"}
MAX_INPUT_BYTES = 64 * 1024 * 1024


class SemanticLintV2Error(bindings.BindingError):
    """Stable, non-echoing V7-09 contract failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise SemanticLintV2Error(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("V2_TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("V2_OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(value: object, pointer: str, *, minimum: int = 0, maximum: int = 1024) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("V2_ARRAY_BOUNDS_INVALID", pointer)
    return value


def _id(value: object, pointer: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        _fail("V2_IDENTIFIER_INVALID", pointer)
    return value


def _sha(value: object, pointer: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        _fail("V2_HASH_INVALID", pointer)
    return value


def _integer(value: object, pointer: str, *, minimum: int = 0, maximum: int = 10000) -> int:
    if not bindings._is_int(value) or not minimum <= value <= maximum:
        _fail("V2_INTEGER_INVALID", pointer)
    return value


def _enum(value: object, allowed: set[str], pointer: str, code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(code, pointer)
    return value


def _unique_strings(value: object, pointer: str, *, maximum: int = 256) -> list[str]:
    rows = _array(value, pointer, maximum=maximum)
    if any(not isinstance(item, str) for item in rows) or len(rows) != len(set(rows)):
        _fail("V2_SET_INVALID", pointer)
    return rows


def _safe_source_text(value: object, pointer: str, *, exact: bool = False) -> str:
    limit = 2000 if exact else 1000
    if not isinstance(value, str) or not value or len(value) > limit:
        _fail("V2_TEXT_INVALID", pointer)
    if unicodedata.normalize("NFC", value) != value:
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    if exact:
        try:
            bindings._guard_default_ignorables(value, pointer, "PRM013_UNICODE_UNSAFE")
            bindings._check_scalar_text(value, pointer)
            bindings._validate_visible_text(value, pointer)
            v1_lint._guard_payload(value, pointer)
        except bindings.BindingError as exc:
            raise SemanticLintV2Error(exc.code, exc.pointer) from None
        checked = value
    else:
        try:
        # Reuse the locked V7-07 payload guards.  Source mode permits terminal
        # punctuation but still rejects provider tokens, meta-instructions,
        # secrets, locators, default-ignorables, and unevidenced time ranges.
            checked = v1_lint._safe_text(value, pointer, source=True)
        except bindings.BindingError as exc:
            raise SemanticLintV2Error(exc.code, exc.pointer) from None
    if exact and any(character in checked for character in "\"\r\n\t"):
        _fail("AUDIO013_UTTERANCE_DELIMITER_UNSAFE", pointer)
    return checked


def _canonical_sha(value: object) -> str:
    return bindings.sha256_bytes(bindings.canonical_json(value))


def _validate_policy(value: object, *, allow_unattested_fixture: bool, today: date) -> dict[str, Any]:
    policy = _object(value, POLICY_KEYS, "/surface_av_policy")
    if policy["$schema"] != POLICY_URI or policy["schema_version"] != 1:
        _fail("AVP001_POLICY_CONTRACT_INVALID", "/surface_av_policy")
    _id(policy["policy_id"], "/surface_av_policy/policy_id")
    policy_kind = _enum(policy["policy_kind"], {"evidence_pinned", "unattested_fixture"}, "/surface_av_policy/policy_kind", "AVP001_POLICY_CONTRACT_INVALID")
    attestation = _object(policy["attestation"], POLICY_ATTESTATION_KEYS, "/surface_av_policy/attestation")
    if policy_kind == "unattested_fixture":
        if not allow_unattested_fixture or attestation != {"method": "unattested_fixture", "verification_record_sha256": None}:
            _fail("AVP006_POLICY_NOT_INSTALLED", "/surface_av_policy/attestation")
    elif attestation.get("method") != "evidence_registry":
        _fail("AVP006_POLICY_NOT_INSTALLED", "/surface_av_policy/attestation")
    else:
        _sha(attestation.get("verification_record_sha256"), "/surface_av_policy/attestation/verification_record_sha256")
    if policy["status"] != "candidate" or policy["runtime_enabled"] is not False or policy["preview_only"] is not True:
        _fail("AVP002_CANDIDATE_PREVIEW_REQUIRED", "/surface_av_policy")
    for field in ("profile_id", "operation", "model_profile_id", "model_variant", "region", "provider_locale"):
        if not isinstance(policy[field], str) or not policy[field] or len(policy[field]) > 100:
            _fail("AVP001_POLICY_CONTRACT_INVALID", f"/surface_av_policy/{field}")
    _sha(policy["surface_profile_sha256"], "/surface_av_policy/surface_profile_sha256")
    _sha(policy["model_profile_sha256"], "/surface_av_policy/model_profile_sha256")
    if policy["prompt_locales"] != ["en", "zh-Hans"]:
        _fail("AVP003_PROMPT_LOCALE_SET_INVALID", "/surface_av_policy/prompt_locales")

    multi = _object(policy["multi_shot"], MULTI_KEYS, "/surface_av_policy/multi_shot")
    multi_status = _enum(multi["status"], {"supported", "unsupported", "unknown"}, "/surface_av_policy/multi_shot/status", "MS007_SURFACE_GRAMMAR_UNRESOLVED")
    grammar = _enum(multi["grammar"], GRAMMARS, "/surface_av_policy/multi_shot/grammar", "MS007_SURFACE_GRAMMAR_UNRESOLVED")
    transition_types = _unique_strings(multi["transition_types"], "/surface_av_policy/multi_shot/transition_types", maximum=4)
    if any(item not in TRANSITION_TYPES for item in transition_types):
        _fail("MS002_TRANSITION_SET_INVALID", "/surface_av_policy/multi_shot/transition_types")
    if multi_status == "supported":
        if grammar == "none" or not bindings._is_int(multi["max_shots"]) or multi["max_shots"] < 2 or not transition_types:
            _fail("MS007_SURFACE_GRAMMAR_UNRESOLVED", "/surface_av_policy/multi_shot")
    elif grammar != "none" or multi["max_shots"] is not None or transition_types:
        _fail("MS007_SURFACE_GRAMMAR_UNRESOLVED", "/surface_av_policy/multi_shot")

    audio = _object(policy["audio"], AUDIO_POLICY_KEYS, "/surface_av_policy/audio")
    audio_status = _enum(audio["status"], {"supported", "unsupported", "unknown"}, "/surface_av_policy/audio/status", "AUDIO014_SURFACE_AUDIO_UNRESOLVED")
    functions = _unique_strings(audio["semantic_functions"], "/surface_av_policy/audio/semantic_functions", maximum=7)
    voice_modes = _unique_strings(audio["voice_modes"], "/surface_av_policy/audio/voice_modes", maximum=3)
    if any(item not in SEMANTIC_FUNCTIONS for item in functions) or any(item not in VOICE_MODES for item in voice_modes):
        _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", "/surface_av_policy/audio")
    voice_status = _enum(audio["voice_reference_status"], {"supported", "unsupported", "unknown"}, "/surface_av_policy/audio/voice_reference_status", "AUDIO014_SURFACE_AUDIO_UNRESOLVED")
    if audio_status == "supported":
        if not functions:
            _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", "/surface_av_policy/audio")
    elif functions or voice_modes or voice_status == "supported":
        _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", "/surface_av_policy/audio")
    if ("authorized_reference" in voice_modes) != (voice_status == "supported"):
        _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", "/surface_av_policy/audio")

    exact = _object(policy["exact_timing"], EXACT_KEYS, "/surface_av_policy/exact_timing")
    exact_status = _enum(exact["status"], {"supported", "unsupported", "unknown"}, "/surface_av_policy/exact_timing/status", "PRM008_TIME_RANGE_UNEVIDENCED")
    exact_claims = _unique_strings(exact["evidence_claim_ids"], "/surface_av_policy/exact_timing/evidence_claim_ids", maximum=32)
    if any(not CLAIM_ID.fullmatch(item) for item in exact_claims):
        _fail("AVP004_EVIDENCE_PIN_INVALID", "/surface_av_policy/exact_timing/evidence_claim_ids")
    pins = _array(policy["evidence_pins"], "/surface_av_policy/evidence_pins", minimum=1, maximum=64)
    pin_ids: set[str] = set()
    for index, raw in enumerate(pins):
        pointer = f"/surface_av_policy/evidence_pins/{index}"
        pin = _object(raw, PIN_KEYS, pointer)
        claim_id = pin["claim_id"]
        if not isinstance(claim_id, str) or not CLAIM_ID.fullmatch(claim_id) or claim_id in pin_ids:
            _fail("AVP004_EVIDENCE_PIN_INVALID", f"{pointer}/claim_id")
        pin_ids.add(claim_id)
        _sha(pin["claim_sha256"], f"{pointer}/claim_sha256")
        if not isinstance(pin["expires_at"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pin["expires_at"]):
            _fail("AVP004_EVIDENCE_PIN_INVALID", f"{pointer}/expires_at")
        try:
            expires = date.fromisoformat(pin["expires_at"])
        except ValueError:
            _fail("AVP004_EVIDENCE_PIN_INVALID", f"{pointer}/expires_at")
        if today >= expires:
            _fail("PROFILE_EVIDENCE_EXPIRED", f"{pointer}/expires_at")
    if exact_status == "supported":
        if exact["range_unit"] != "seconds" or not exact_claims or not set(exact_claims) <= pin_ids:
            _fail("PRM008_TIME_RANGE_UNEVIDENCED", "/surface_av_policy/exact_timing")
    elif exact["range_unit"] is not None or exact_claims:
        _fail("PRM008_TIME_RANGE_UNEVIDENCED", "/surface_av_policy/exact_timing")
    if policy_kind == "evidence_pinned":
        try:
            registry = bindings.load_registry(ROOT)
            surface = registry.surfaces[policy["profile_id"]]
            model = registry.models[policy["model_profile_id"]]
        except (KeyError, bindings.BindingError):
            _fail("AVP006_POLICY_NOT_INSTALLED", "/surface_av_policy")
        if surface.sha256 != policy["surface_profile_sha256"] or model.sha256 != policy["model_profile_sha256"] or surface.data["model_profile_id"] != policy["model_profile_id"]:
            _fail("AVP005_POLICY_BINDING_MISMATCH", "/surface_av_policy")
        operation = next((item for item in surface.data["operations"] if item["operation"] == policy["operation"]), None)
        if operation is None:
            _fail("AVP005_POLICY_BINDING_MISMATCH", "/surface_av_policy/operation")
        installed_pins = {item["claim_id"]: item for item in [*model.data["evidence_pins"], *operation["evidence_pins"]]}
        for index, pin in enumerate(policy["evidence_pins"]):
            installed = installed_pins.get(pin["claim_id"])
            if installed is None or installed != pin:
                _fail("AVP004_EVIDENCE_PIN_INVALID", f"/surface_av_policy/evidence_pins/{index}")
    return policy


def _validate_binding_set(value: object, policy: dict[str, Any]) -> dict[str, Any]:
    binding_set = _object(value, BINDING_SET_KEYS, "/surface_binding_set")
    if binding_set["$schema"] != BINDING_SET_URI or binding_set["schema_version"] != 2:
        _fail("BINDINGS_INVALID", "/surface_binding_set")
    if (
        binding_set["policy_id"] != policy["policy_id"]
        or binding_set["surface_av_policy_sha256"] != _canonical_sha(policy)
        or binding_set["profile_id"] != policy["profile_id"]
        or binding_set["operation"] != policy["operation"]
    ):
        _fail("AVP005_POLICY_BINDING_MISMATCH", "/surface_binding_set")
    rows = _array(binding_set["bindings"], "/surface_binding_set/bindings", maximum=64)
    seen: set[str] = set()
    for index, row in enumerate(rows):
        pointer = f"/surface_binding_set/bindings/{index}"
        if not isinstance(row, dict) or set(row) != {"binding_id", "media_type"}:
            _fail("BINDINGS_INVALID", pointer)
        binding_id = _id(row.get("binding_id"), f"{pointer}/binding_id")
        if binding_id in seen:
            _fail("BINDING_ID_DUPLICATE", f"{pointer}/binding_id")
        seen.add(binding_id)
        _enum(row.get("media_type"), {"audio", "image", "video"}, f"{pointer}/media_type", "BINDING_MEDIA_UNSUPPORTED")
    return binding_set


def _validate_scene(value: object, policy: dict[str, Any], binding_set: dict[str, Any]) -> dict[str, Any]:
    scene = _object(value, SCENE_KEYS, "/scene_ir")
    if scene["$schema"] != SCENE_URI or scene["schema_version"] != 2:
        _fail("SCENE_IR_V2_CONTRACT_INVALID", "/scene_ir")
    take_structure = _enum(scene["take_structure"], {"single_continuous_take", "edited_multi_shot"}, "/scene_ir/take_structure", "MS001_STRUCTURE_AMBIGUOUS")
    timing_policy = _enum(scene["timing_policy"], TIMING_POLICIES, "/scene_ir/timing_policy", "PRM008_TIME_RANGE_UNEVIDENCED")
    if timing_policy == "surface_exact_ranges" and policy["exact_timing"]["status"] != "supported":
        _fail("PRM008_TIME_RANGE_UNEVIDENCED", "/scene_ir/timing_policy")
    state_binding = scene["state_binding"]
    if not isinstance(state_binding, dict):
        _fail("SCENE_IR_V2_CONTRACT_INVALID", "/scene_ir/state_binding")
    completed = set(_unique_strings(state_binding.get("completed_beat_ids"), "/scene_ir/state_binding/completed_beat_ids"))
    current = set(_unique_strings(state_binding.get("current_beat_ids"), "/scene_ir/state_binding/current_beat_ids"))
    reserved = set(_unique_strings(state_binding.get("reserved_future_beat_ids"), "/scene_ir/state_binding/reserved_future_beat_ids"))
    if not current or completed & current or completed & reserved or current & reserved:
        _fail("MS006_FUTURE_BEAT_LEAKAGE", "/scene_ir/state_binding")

    entities = _array(scene["entities"], "/scene_ir/entities", minimum=1, maximum=128)
    entity_ids: set[str] = set()
    for index, entity in enumerate(entities):
        pointer = f"/scene_ir/entities/{index}"
        if not isinstance(entity, dict) or "entity_id" not in entity or "label" not in entity:
            _fail("SCENE_IR_V2_CONTRACT_INVALID", pointer)
        entity_id = _id(entity["entity_id"], f"{pointer}/entity_id")
        if entity_id in entity_ids:
            _fail("ENTITY_ID_DUPLICATE", f"{pointer}/entity_id")
        entity_ids.add(entity_id)
        _safe_source_text(entity["label"], f"{pointer}/label")

    speakers = _array(scene["speakers"], "/scene_ir/speakers", maximum=128)
    speaker_by_id: dict[str, dict[str, Any]] = {}
    binding_by_id = {item["binding_id"]: item for item in binding_set["bindings"]}
    for index, speaker in enumerate(speakers):
        pointer = f"/scene_ir/speakers/{index}"
        if not isinstance(speaker, dict) or set(speaker) != {"speaker_id", "entity_id", "role", "display_name", "voice"}:
            _fail("SCENE_IR_V2_CONTRACT_INVALID", pointer)
        speaker_id = _id(speaker["speaker_id"], f"{pointer}/speaker_id")
        if speaker_id in speaker_by_id:
            _fail("AUDIO003_SPEAKER_UNRESOLVED", f"{pointer}/speaker_id")
        if speaker["entity_id"] is not None and speaker["entity_id"] not in entity_ids:
            _fail("AUDIO003_SPEAKER_UNRESOLVED", f"{pointer}/entity_id")
        if speaker["role"] != "narrator" and speaker["entity_id"] is None:
            _fail("AUDIO003_SPEAKER_UNRESOLVED", f"{pointer}/entity_id")
        _safe_source_text(speaker["display_name"], f"{pointer}/display_name")
        voice = speaker["voice"]
        if not isinstance(voice, dict):
            _fail("SCENE_IR_V2_CONTRACT_INVALID", f"{pointer}/voice")
        mode = _enum(voice.get("mode"), VOICE_MODES, f"{pointer}/voice/mode", "AUDIO014_SURFACE_AUDIO_UNRESOLVED")
        if mode not in policy["audio"]["voice_modes"]:
            _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", f"{pointer}/voice/mode")
        asset_id = voice.get("asset_id")
        if mode == "authorized_reference":
            voice_binding = binding_by_id.get(asset_id) if isinstance(asset_id, str) else None
            if (
                voice.get("authorization_status") != "user_attested_authorized"
                or voice.get("authority_target_id") != speaker["entity_id"]
                or voice_binding is None
                or voice_binding.get("media_type") != "audio"
                or "structured_role" in voice_binding
            ):
                _fail("REF010_VOICE_NOT_AUTHORIZED", f"{pointer}/voice")
            _sha(voice.get("attestation_sha256"), f"{pointer}/voice/attestation_sha256")
        elif asset_id is not None:
            _fail("AUDIO009_DUB_VARIANT_REQUIRED" if mode == "post_dub" else "AUDIO014_SURFACE_AUDIO_UNRESOLVED", f"{pointer}/voice/asset_id")
        speaker_by_id[speaker_id] = speaker

    used_binding_ids = {
        speaker["voice"]["asset_id"]
        for speaker in speakers
        if speaker["voice"]["mode"] == "authorized_reference"
    }
    if used_binding_ids != set(binding_by_id):
        _fail("BINDING_UNUSED", "/surface_binding_set/bindings")

    shots = _array(scene["shots"], "/scene_ir/shots", minimum=1, maximum=64)
    shot_by_id: dict[str, dict[str, Any]] = {}
    event_ids: set[str] = set()
    for shot_offset, shot in enumerate(shots):
        pointer = f"/scene_ir/shots/{shot_offset}"
        if not isinstance(shot, dict) or "shot_id" not in shot or "shot_index" not in shot or "events" not in shot or "camera" not in shot:
            _fail("SCENE_IR_V2_CONTRACT_INVALID", pointer)
        shot_id = _id(shot["shot_id"], f"{pointer}/shot_id")
        if shot_id in shot_by_id or shot["shot_index"] != shot_offset + 1 or not bindings._is_int(shot["shot_index"]):
            _fail("EVT003_SHOT_ORDER_INVALID", f"{pointer}/shot_index")
        shot_by_id[shot_id] = shot
        events = _array(shot["events"], f"{pointer}/events", minimum=1, maximum=64)
        local: list[str] = []
        for event_offset, event in enumerate(events):
            event_pointer = f"{pointer}/events/{event_offset}"
            if not isinstance(event, dict) or "event_id" not in event or "event_index" not in event or "visible_state_change" not in event:
                _fail("SCENE_IR_V2_CONTRACT_INVALID", event_pointer)
            event_id = _id(event["event_id"], f"{event_pointer}/event_id")
            if event_id in event_ids or event["event_index"] != event_offset + 1 or not bindings._is_int(event["event_index"]):
                _fail("EVT003_EVENT_ORDER_INVALID", f"{event_pointer}/event_index")
            event_ids.add(event_id)
            local.append(event_id)
            _safe_source_text(event["visible_state_change"], f"{event_pointer}/visible_state_change")
        if shot.get("opening_event_id") != local[0] or shot.get("endpoint_event_id") != local[-1]:
            _fail("MS005_ENDPOINT_OPENING_MISMATCH", pointer)
        camera = shot["camera"]
        move = camera if isinstance(camera, dict) else None
        if not isinstance(move, dict):
            _fail("SCENE_IR_V2_CONTRACT_INVALID", f"{pointer}/camera")
        for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing"):
            if field not in move:
                _fail("SCENE_IR_V2_CONTRACT_INVALID", f"{pointer}/camera/primary_move")
            _safe_source_text(move[field], f"{pointer}/camera/{field}")

    transitions = _array(scene["transitions"], "/scene_ir/transitions", maximum=63)
    authored_beats: set[str] = set()
    for shot in shots:
        for event in shot["events"]:
            authored_beats.update(event.get("beat_ids", []))
    if take_structure == "single_continuous_take":
        if len(shots) != 1 or transitions:
            _fail("MS003_CONTINUOUS_TAKE_HAS_CUT", "/scene_ir")
    else:
        multi = policy["multi_shot"]
        if multi["status"] != "supported" or len(shots) < 2 or len(shots) > multi["max_shots"]:
            _fail("MS007_SURFACE_GRAMMAR_UNRESOLVED", "/scene_ir/shots")
        if len(transitions) != len(shots) - 1:
            _fail("MS002_TRANSITION_SET_INVALID", "/scene_ir/transitions")
    transition_ids: set[str] = set()
    for offset, transition in enumerate(transitions):
        pointer = f"/scene_ir/transitions/{offset}"
        if not isinstance(transition, dict):
            _fail("MS002_TRANSITION_SET_INVALID", pointer)
        transition_id = _id(transition.get("transition_id"), f"{pointer}/transition_id")
        if transition_id in transition_ids or transition.get("transition_index") != offset + 1 or not bindings._is_int(transition.get("transition_index")):
            _fail("MS002_TRANSITION_SET_INVALID", pointer)
        transition_ids.add(transition_id)
        if transition.get("from_shot_id") != shots[offset]["shot_id"] or transition.get("to_shot_id") != shots[offset + 1]["shot_id"]:
            _fail("MS002_TRANSITION_SET_INVALID", pointer)
        if transition.get("from_event_id") != shots[offset]["endpoint_event_id"] or transition.get("to_event_id") != shots[offset + 1]["opening_event_id"]:
            _fail("MS005_ENDPOINT_OPENING_MISMATCH", pointer)
        if transition.get("transition_type") not in policy["multi_shot"]["transition_types"]:
            _fail("MS002_TRANSITION_SET_INVALID", f"{pointer}/transition_type")
        authored_beats.update(transition.get("beat_ids", []))

    audio_events = _array(scene["audio_events"], "/scene_ir/audio_events", maximum=128)
    audio_ids: set[str] = set()
    speech_turns: list[int] = []
    for offset, audio in enumerate(audio_events):
        pointer = f"/scene_ir/audio_events/{offset}"
        if not isinstance(audio, dict):
            _fail("SCENE_IR_V2_CONTRACT_INVALID", pointer)
        audio_id = _id(audio.get("audio_event_id"), f"{pointer}/audio_event_id")
        if audio_id in audio_ids or audio.get("audio_event_index") != offset + 1 or not bindings._is_int(audio.get("audio_event_index")):
            _fail("AUDIO_EVENT_ID_DUPLICATE", pointer)
        audio_ids.add(audio_id)
        function = _enum(audio.get("semantic_function"), SEMANTIC_FUNCTIONS, f"{pointer}/semantic_function", "AUDIO001_SEMANTIC_FUNCTION_INVALID")
        if policy["audio"]["status"] != "supported" or function not in policy["audio"]["semantic_functions"]:
            _fail("AUDIO014_SURFACE_AUDIO_UNRESOLVED", f"{pointer}/semantic_function")
        shot_ids = _unique_strings(audio.get("shot_ids"), f"{pointer}/shot_ids", maximum=64)
        if not shot_ids or any(item not in shot_by_id for item in shot_ids):
            _fail("AUDIO_EVENT_LINK_INVALID", f"{pointer}/shot_ids")
        _safe_source_text(audio.get("description"), f"{pointer}/description")
        authored_beats.update(audio.get("beat_ids", []))
        timing = audio.get("timing")
        if not isinstance(timing, dict) or "mode" not in timing:
            _fail("AUDIO001_TEMPORAL_RELATIONSHIP_INVALID", f"{pointer}/timing")
        mode = timing["mode"]
        compatible_modes = {
            "ordered_phases": {"visual_event_window", "continuous_shot", "continuous_sequence"},
            "relative_beats": {"relative_beat"},
            "surface_exact_ranges": {"surface_exact_range"},
        }[timing_policy]
        if mode not in compatible_modes:
            _fail("AUDIO001_TEMPORAL_RELATIONSHIP_INVALID", f"{pointer}/timing/mode")
        has_exact = timing.get("start_seconds") is not None or timing.get("end_seconds") is not None or bool(timing.get("evidence_claim_ids"))
        if has_exact and (timing_policy != "surface_exact_ranges" or policy["exact_timing"]["status"] != "supported"):
            _fail("PRM008_TIME_RANGE_UNEVIDENCED", f"{pointer}/timing")
        if timing_policy == "surface_exact_ranges":
            claims = timing.get("evidence_claim_ids")
            if not isinstance(claims, list) or not set(claims) <= set(policy["exact_timing"]["evidence_claim_ids"]):
                _fail("PRM008_TIME_RANGE_UNEVIDENCED", f"{pointer}/timing/evidence_claim_ids")
        speech = audio.get("speech")
        if function in {"dialogue", "voiceover"}:
            if not isinstance(speech, dict):
                _fail("AUDIO002_EXACT_UTTERANCE_REQUIRED", f"{pointer}/speech")
            speaker_id = speech.get("speaker_id")
            if speaker_id not in speaker_by_id:
                _fail("AUDIO003_SPEAKER_UNRESOLVED", f"{pointer}/speech/speaker_id")
            language = speech.get("spoken_language")
            if not isinstance(language, str) or not LANGUAGE_TAG.fullmatch(language):
                _fail("AUDIO005_SPOKEN_LANGUAGE_INVALID", f"{pointer}/speech/spoken_language")
            utterance = _safe_source_text(speech.get("utterance"), f"{pointer}/speech/utterance", exact=True)
            if speech.get("utterance_sha256") != bindings.sha256_bytes(utterance.encode("utf-8")):
                _fail("AUDIO006_UTTERANCE_HASH_MISMATCH", f"{pointer}/speech/utterance_sha256")
            turn = _integer(speech.get("turn_index"), f"{pointer}/speech/turn_index", minimum=1, maximum=128)
            speech_turns.append(turn)
        elif speech is not None:
            _fail("AUDIO002_EXACT_UTTERANCE_REQUIRED", f"{pointer}/speech")
    if speech_turns != list(range(1, len(speech_turns) + 1)):
        _fail("AUDIO015_TURN_ORDER_INVALID", "/scene_ir/audio_events")
    if authored_beats != current or authored_beats & (completed | reserved):
        _fail("MS006_FUTURE_BEAT_LEAKAGE", "/scene_ir")

    subtitle = scene["subtitle_policy"]
    if not isinstance(subtitle, dict) or subtitle.get("mode") not in {"none", "post_subtitles", "post_sdh_captions", "post_forced_narrative"}:
        _fail("AUDIO008_SUBTITLE_POLICY_REQUIRED", "/scene_ir/subtitle_policy")
    if subtitle.get("picture_policy") not in {"clean_picture", "not_applicable"}:
        _fail("AUDIO008_SUBTITLE_POLICY_REQUIRED", "/scene_ir/subtitle_policy/picture_policy")
    for collection, id_key in (("known_fragilities", "fragility_id"), ("acceptance_tests", "acceptance_id"), ("post_fallbacks", "fallback_id")):
        seen: set[str] = set()
        for index, item in enumerate(_array(scene[collection], f"/scene_ir/{collection}", maximum=256)):
            if not isinstance(item, dict) or id_key not in item:
                _fail("SCENE_IR_V2_CONTRACT_INVALID", f"/scene_ir/{collection}/{index}")
            item_id = _id(item[id_key], f"/scene_ir/{collection}/{index}/{id_key}")
            if item_id in seen:
                _fail("V2_IDENTIFIER_DUPLICATE", f"/scene_ir/{collection}/{index}/{id_key}")
            seen.add(item_id)
            text_key = "action" if collection == "post_fallbacks" else "description" if collection == "known_fragilities" else "observable"
            _safe_source_text(item[text_key], f"/scene_ir/{collection}/{index}/{text_key}")
    return scene


def _expected_catalog(scene: dict[str, Any]) -> list[tuple[str, str, set[str] | None, str]]:
    rows: list[tuple[str, str, set[str] | None, str]] = []
    for entity in scene["entities"]:
        rows.append((f"entity.{entity['entity_id']}.label", entity["label"], None, "entity_label"))
    for speaker in scene["speakers"]:
        rows.append((f"speaker.{speaker['speaker_id']}.display_name", speaker["display_name"], None, "entity_label"))
    for shot in scene["shots"]:
        for event in shot["events"]:
            owners = set(event.get("actor_ids", [])) | set(event.get("target_ids", []))
            rows.append((f"event.{event['event_id']}.visible_state_change", event["visible_state_change"], owners, "event"))
        move = shot["camera"]
        for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing"):
            rows.append((f"shot.{shot['shot_id']}.camera.{field}", move[field], None, "camera"))
    for audio in scene["audio_events"]:
        rows.append((f"audio.{audio['audio_event_id']}.description", audio["description"], set(audio.get("source_entity_ids", [])), "audio"))
        speech = audio.get("speech")
        if speech is not None:
            rows.append((f"audio.{audio['audio_event_id']}.delivery_intent", speech["delivery_intent"], None, "audio"))
    for invariant in scene["requested_invariants"]:
        rows.append((f"invariant.{invariant['invariant_id']}.description", invariant["description"], set(invariant.get("entity_ids", [])), "invariant"))
    return rows


def _validate_catalog(scene: dict[str, Any], value: object, *, allow_unattested_fixture: bool) -> tuple[dict[str, dict[str, str]], str]:
    catalog = _object(value, CATALOG_KEYS, "/realization_catalog")
    if catalog["$schema"] != CATALOG_URI or catalog["schema_version"] != 2:
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog")
    scene_sha = _canonical_sha(scene)
    if catalog["scene_ir_sha256"] != scene_sha:
        _fail("AUDIO006_UTTERANCE_HASH_MISMATCH", "/realization_catalog/scene_ir_sha256")
    attestation = _object(catalog["attestation"], ATTESTATION_KEYS, "/realization_catalog/attestation")
    if attestation["locales"] != ["en", "zh-Hans"]:
        _fail("LANG003_LOCALIZATION_SET_MISMATCH", "/realization_catalog/attestation/locales")
    if attestation["method"] == "unattested_fixture":
        if not allow_unattested_fixture or attestation["linguistic_equivalence"] != "not_attested":
            _fail("CATALOG_FORMS_HUMAN_ATTESTATION_DECLARED", "/realization_catalog/attestation")
    elif attestation["method"] not in {"user_attested", "reviewer_attested"} or attestation["linguistic_equivalence"] != "human_asserted":
        _fail("CATALOG_FORMS_HUMAN_ATTESTATION_DECLARED", "/realization_catalog/attestation")
    expected = _expected_catalog(scene)
    entries = _array(catalog["entries"], "/realization_catalog/entries", minimum=1, maximum=1024)
    if len(entries) != len(expected):
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/entries")
    known_entities = {item["entity_id"] for item in scene["entities"]}
    result: dict[str, dict[str, str]] = {}
    speaker_labels: dict[str, set[str]] = {"en": set(), "zh_hans": set()}
    for index, (raw, wanted) in enumerate(zip(entries, expected)):
        pointer = f"/realization_catalog/entries/{index}"
        entry = _object(raw, ENTRY_KEYS, pointer)
        key, source, required_entities, category = wanted
        if entry["semantic_key"] != key or key in result:
            _fail("PRM025_LOCALE_CATALOG_INVALID", f"{pointer}/semantic_key")
        if entry["source_sha256"] != bindings.sha256_bytes(source.encode("utf-8")):
            _fail("PRM025_LOCALE_CATALOG_INVALID", f"{pointer}/source_sha256")
        checked: dict[str, str] = {}
        for locale, field in (("en", "en"), ("zh-Hans", "zh_hans")):
            try:
                text = v1_lint._safe_text(entry[field], f"{pointer}/{field}")
                tokens = set(v1_lint._entity_tokens(text, f"{pointer}/{field}", known_entities))
                if required_entities is not None and tokens != required_entities:
                    _fail("PRM004_ENTITY_AMBIGUOUS", f"{pointer}/{field}")
                v1_lint._validate_entry_language(text, locale=locale, category=category, pointer=f"{pointer}/{field}")
            except bindings.BindingError as exc:
                raise SemanticLintV2Error(exc.code, exc.pointer) from None
            if key.startswith("speaker.") and key.endswith(".display_name"):
                comparison = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
                if comparison in speaker_labels[field]:
                    _fail("AUDIO016_SPEAKER_LABEL_COLLISION", f"{pointer}/{field}")
                speaker_labels[field].add(comparison)
            checked[field] = text
        result[key] = checked
    return result, _canonical_sha(catalog)


def validate_request(value: object, *, allow_unattested_fixture: bool = False, today: date | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, str]], str]:
    request = _object(value, REQUEST_KEYS, "/")
    if request["$schema"] != REQUEST_URI or request["schema_version"] != 2:
        _fail("COMPILE002_REQUEST_CONTRACT_INVALID", "/")
    effective_today = datetime.now(timezone.utc).date() if today is None else today
    try:
        # This is the authoritative AV validator.  The checks below are only
        # compiler-specific binding/catalog constraints layered on its result.
        authoritative_policy = av_check.validate_surface_av_policy(
            request["surface_av_policy"],
            today=effective_today,
            allow_unattested_fixture=allow_unattested_fixture,
        )
        authoritative_scene = av_check.validate_scene_ir(
            request["scene_ir"],
            policy=authoritative_policy,
            allow_unattested_policy=allow_unattested_fixture,
            today=effective_today,
        )
    except av_check.AVContractError as exc:
        raise SemanticLintV2Error(exc.code, exc.pointer) from None
    policy = _validate_policy(authoritative_policy, allow_unattested_fixture=allow_unattested_fixture, today=effective_today)
    binding_set = _validate_binding_set(request["surface_binding_set"], policy)
    scene = _validate_scene(authoritative_scene, policy, binding_set)
    catalog, catalog_sha = _validate_catalog(scene, request["realization_catalog"], allow_unattested_fixture=allow_unattested_fixture)
    return scene, policy, binding_set, catalog, catalog_sha


def _unit(unit_id: str, kind: str, emission: str, *, source_ids: list[str], shot_ids: list[str] | None = None, semantic_key: str | None = None, content_sha256: str | None = None, speaker_id: str | None = None, spoken_language: str | None = None, turn_index: int | None = None) -> dict[str, Any]:
    return {"unit_id": unit_id, "kind": kind, "emission": emission, "source_ids": source_ids, "shot_ids": [] if shot_ids is None else shot_ids, "semantic_key": semantic_key, "content_sha256": content_sha256, "speaker_id": speaker_id, "spoken_language": spoken_language, "turn_index": turn_index}


def build_prompt_program(scene: dict[str, Any], policy: dict[str, Any], binding_set: dict[str, Any], catalog_sha: str) -> dict[str, Any]:
    units: list[dict[str, Any]] = [
        _unit("state.binding", "state", "request_carried", source_ids=[scene["state_binding"]["project_id"], scene["state_binding"]["clip_id"]], content_sha256=_canonical_sha(scene["state_binding"])),
        _unit("take.structure", "take", "prompt", source_ids=[]),
    ]
    transitions_by_from = {item["from_shot_id"]: item for item in scene["transitions"]}
    for shot in scene["shots"]:
        shot_id = shot["shot_id"]
        units.append(_unit(f"shot.{shot_id}", "shot", "prompt", source_ids=[shot_id], shot_ids=[shot_id]))
        for event in shot["events"]:
            event_id = event["event_id"]
            units.append(_unit(f"event.{event_id}", "event", "prompt", source_ids=[event_id], shot_ids=[shot_id], semantic_key=f"event.{event_id}.visible_state_change"))
        for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing"):
            units.append(_unit(f"camera.{shot_id}.{field}", "camera", "prompt", source_ids=[shot_id], shot_ids=[shot_id], semantic_key=f"shot.{shot_id}.camera.{field}"))
        transition = transitions_by_from.get(shot_id)
        if transition is not None:
            units.append(_unit(f"transition.{transition['transition_id']}", "transition", "prompt", source_ids=[transition["transition_id"], transition["from_event_id"], transition["to_event_id"]], shot_ids=[transition["from_shot_id"], transition["to_shot_id"]]))
    speaker_by_id = {item["speaker_id"]: item for item in scene["speakers"]}
    for audio in scene["audio_events"]:
        audio_id = audio["audio_event_id"]
        speech = audio["speech"]
        emission = "prompt"
        if speech is not None and speaker_by_id[speech["speaker_id"]]["voice"]["mode"] == "post_dub":
            emission = "post_only"
        units.append(_unit(f"audio.{audio_id}", "audio", emission, source_ids=[audio_id], shot_ids=list(audio["shot_ids"]), semantic_key=f"audio.{audio_id}.description"))
        timing = audio["timing"]
        timing_source_ids = [audio_id]
        timing_source_ids.extend(
            timing[field]
            for field in ("start_event_id", "end_event_id", "cue_event_id")
            if timing.get(field) is not None
        )
        units.append(_unit(
            f"audio_timing.{audio_id}",
            "audio_timing",
            emission,
            source_ids=timing_source_ids,
            shot_ids=list(audio["shot_ids"]),
            content_sha256=_canonical_sha(timing),
        ))
        if speech is not None:
            units.append(_unit(
                f"speech_delivery.{audio_id}",
                "speech_delivery",
                emission,
                source_ids=[audio_id, speech["speaker_id"]],
                shot_ids=list(audio["shot_ids"]),
                semantic_key=f"audio.{audio_id}.delivery_intent",
                speaker_id=speech["speaker_id"],
            ))
            units.append(_unit(
                f"speech_overlap.{audio_id}",
                "speech_overlap",
                emission,
                source_ids=[audio_id, speech["speaker_id"]],
                shot_ids=list(audio["shot_ids"]),
                content_sha256=_canonical_sha(speech["overlap_policy"]),
                speaker_id=speech["speaker_id"],
            ))
            units.append(_unit(
                f"speech_lip_sync.{audio_id}",
                "speech_lip_sync",
                emission,
                source_ids=[audio_id, speech["speaker_id"]],
                shot_ids=list(audio["shot_ids"]),
                content_sha256=_canonical_sha(speech["lip_sync"]),
                speaker_id=speech["speaker_id"],
            ))
            units.append(_unit(f"speech.{audio_id}", "exact_speech", emission, source_ids=[audio_id, speech["speaker_id"]], shot_ids=list(audio["shot_ids"]), content_sha256=speech["utterance_sha256"], speaker_id=speech["speaker_id"], spoken_language=speech["spoken_language"], turn_index=speech["turn_index"]))
    for invariant in scene["requested_invariants"]:
        invariant_id = invariant["invariant_id"]
        units.append(_unit(f"invariant.{invariant_id}", "invariant", "prompt", source_ids=[invariant_id], semantic_key=f"invariant.{invariant_id}.description"))
    if scene["subtitle_policy"]["mode"] != "none":
        units.append(_unit("subtitle.post", "subtitle", "post_only", source_ids=["subtitle_policy"]))
    for fragility in scene["known_fragilities"]:
        units.append(_unit(f"review.fragility.{fragility['fragility_id']}", "review", "review_only", source_ids=[fragility["fragility_id"]], content_sha256=_canonical_sha(fragility)))
    for acceptance in scene["acceptance_tests"]:
        units.append(_unit(f"review.acceptance.{acceptance['acceptance_id']}", "review", "review_only", source_ids=[acceptance["acceptance_id"]], content_sha256=_canonical_sha(acceptance)))
    for fallback in scene["post_fallbacks"]:
        units.append(_unit(f"post.fallback.{fallback['fallback_id']}", "post_fallback", "post_only", source_ids=[fallback["fallback_id"]], content_sha256=_canonical_sha(fallback)))
    for speaker in scene["speakers"]:
        voice = speaker["voice"]
        if voice["mode"] == "authorized_reference":
            units.append(_unit(
                f"voice_binding.{speaker['speaker_id']}",
                "voice_binding",
                "request_carried",
                source_ids=[speaker["speaker_id"], voice["authority_target_id"], voice["asset_id"]],
                content_sha256=_canonical_sha(voice),
                speaker_id=speaker["speaker_id"],
            ))
    for binding in binding_set["bindings"]:
        units.append(_unit(f"binding.{binding['binding_id']}", "binding", "request_carried", source_ids=[binding["binding_id"]], content_sha256=_canonical_sha(binding)))
    unit_ids = [item["unit_id"] for item in units]
    if len(unit_ids) != len(set(unit_ids)):
        _fail("PRM014_PROGRAM_HASH_MISMATCH", "/prompt_program/units")
    speech_events = [item for item in scene["audio_events"] if item["speech"] is not None]
    return {
        "$schema": PROGRAM_URI,
        "schema_version": 2,
        "status": "unattested_fixture_preview" if policy["policy_kind"] == "unattested_fixture" else "candidate_preview",
        "state_binding": scene["state_binding"],
        "state_binding_sha256": _canonical_sha(scene["state_binding"]),
        "scene_ir_sha256": _canonical_sha(scene),
        "surface_av_policy_sha256": _canonical_sha(policy),
        "surface_binding_set_sha256": _canonical_sha(binding_set),
        "realization_catalog_sha256": catalog_sha,
        "policy_provenance": {
            "policy_id": policy["policy_id"],
            "policy_kind": policy["policy_kind"],
            "profile_id": policy["profile_id"],
            "operation": policy["operation"],
            "model_profile_id": policy["model_profile_id"],
            "model_variant": policy["model_variant"],
            "region": policy["region"],
            "provider_locale": policy["provider_locale"],
            "surface_profile_sha256": policy["surface_profile_sha256"],
            "model_profile_sha256": policy["model_profile_sha256"],
        },
        "take_structure": scene["take_structure"],
        "timing_policy": scene["timing_policy"],
        "ordering": {
            "transition_ids": [item["transition_id"] for item in scene["transitions"]],
            "audio_event_ids": [item["audio_event_id"] for item in scene["audio_events"]],
            "speech_event_ids": [item["audio_event_id"] for item in speech_events],
            "speech_turn_indices": [item["speech"]["turn_index"] for item in speech_events],
        },
        "units": units,
    }


def compile_program(value: object, *, allow_unattested_fixture: bool = False, today: date | None = None) -> dict[str, Any]:
    scene, policy, binding_set, _catalog, catalog_sha = validate_request(value, allow_unattested_fixture=allow_unattested_fixture, today=today)
    return build_prompt_program(scene, policy, binding_set, catalog_sha)


def _self_test() -> None:
    try:
        bindings.parse_json_bytes(b'{"x":1,"x":2}')
    except bindings.BindingError as exc:
        if exc.code != "JSON_DUPLICATE_KEY":
            _fail("SELF_TEST_FAILED")
    else:
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V7-09 candidate AV prompt program from strict JSON.")
    parser.add_argument("request", nargs="?", default="-", help="JSON request path, or - for stdin")
    parser.add_argument("--preview-candidate", action="store_true")
    parser.add_argument("--allow-unattested-fixture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("semantic lint v2 self-test passed")
            return 0
        if not args.preview_candidate:
            _fail("CANDIDATE_PREVIEW_ONLY")
        raw = bindings._read_request(args.request)
        if len(raw) > MAX_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        program = compile_program(bindings.parse_json_bytes(raw), allow_unattested_fixture=args.allow_unattested_fixture)
        payload = bindings.canonical_json(program)
    except bindings.BindingError as exc:
        print(f"semantic-lint-v2 error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
