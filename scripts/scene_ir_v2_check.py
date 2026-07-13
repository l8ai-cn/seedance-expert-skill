#!/usr/bin/env python3
"""Validate the candidate V7-09 state-bound AV scene contract.

The checker is dependency-free, bounded, fail-closed, and non-echoing. It
validates authored semantics and provenance; it does not claim that a provider
will follow the plan or that generated audio/video is correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCENE_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/scene-ir-v2.schema.json"
POLICY_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/surface-av-policy.schema.json"
MAX_INPUT_BYTES = 16 * 1024 * 1024
SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
CLAIM_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
LANGUAGE_TAG = re.compile(
    r"^[a-z]{2,8}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?"
    r"(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*$"
)
PROVIDER_TOKEN = re.compile(
    r"(?:@\s*(?:image|video|audio|图片|视频|音频)\s*[-_#:：]?\s*[0-9]+"
    r"|<\s*(?:image|video|audio)\s*[-_#:：]?\s*[0-9]+\s*>)",
    re.IGNORECASE,
)
LOCATOR_LIKE = re.compile(r"(?:https?://|file://)", re.IGNORECASE)
BIDI_CONTROLS = {
    *range(0x202A, 0x202F),
    *range(0x2066, 0x206A),
    0x061C,
    0x200E,
    0x200F,
}

# Evidence-pinned policies become trusted only through an explicit reviewed
# code change binding policy ID to the canonical SHA-256 of the complete
# immutable policy record. Binding selected provenance fields is insufficient:
# capability grammar, scope, timing, and evidence pins must move together.
# V7-09 intentionally ships no activated or trusted feature policy.
TRUSTED_POLICY_BINDINGS: dict[str, str] = {}

ROOT_KEYS = {
    "$schema", "schema_version", "state_binding", "take_structure", "timing_policy",
    "entities", "materials", "speakers", "shots", "transitions", "audio_events",
    "subtitle_policy", "requested_invariants", "known_fragilities", "acceptance_tests",
    "post_fallbacks",
}
STATE_KEYS = {
    "project_id", "clip_id", "state_revision", "canon_revision", "semantic_state_sha256",
    "planned_start_snapshot_sha256", "planned_end_snapshot_sha256", "completed_beat_ids",
    "current_beat_ids", "reserved_future_beat_ids",
}
ENTITY_KEYS = {"entity_id", "label", "kind", "stable_features"}
MATERIAL_KEYS = {"material_id", "entity_id", "kind", "response_properties"}
SPEAKER_KEYS = {"speaker_id", "entity_id", "role", "display_name", "voice"}
VOICE_KEYS = {"mode", "authority_target_id", "asset_id", "authorization_status", "attestation_sha256"}
SHOT_KEYS = {"shot_id", "shot_index", "opening_event_id", "endpoint_event_id", "events", "camera"}
EVENT_KEYS = {
    "event_id", "event_index", "phase", "actor_ids", "target_ids", "depends_on",
    "visible_state_change", "beat_ids", "interaction_kind", "material_ids",
}
CAMERA_KEYS = {
    "move_kind", "start_framing", "path", "speed", "subject_relationship",
    "endpoint_framing", "observed_event_ids", "occlusion_risks", "mitigations",
}
TRANSITION_KEYS = {
    "transition_id", "transition_index", "from_shot_id", "to_shot_id", "transition_type",
    "from_event_id", "to_event_id", "beat_ids", "preserved_invariant_ids",
    "allowed_change_event_ids", "audio_bridge_event_ids",
}
AUDIO_KEYS = {
    "audio_event_id", "audio_event_index", "semantic_function", "shot_ids", "beat_ids",
    "source_entity_ids", "timing", "description", "speech",
}
TIMING_KEYS = {
    "mode", "start_event_id", "end_event_id", "cue_event_id", "beat_label",
    "start_seconds", "end_seconds", "evidence_claim_ids",
}
SPEECH_KEYS = {
    "speaker_id", "spoken_language", "utterance", "utterance_sha256", "turn_index",
    "overlap_policy", "lip_sync", "delivery_intent",
}
SUBTITLE_KEYS = {"mode", "target_language_tags", "picture_policy"}
INVARIANT_KEYS = {"invariant_id", "entity_ids", "description"}
FRAGILITY_KEYS = {"fragility_id", "event_ids", "audio_event_ids", "transition_ids", "description"}
ACCEPTANCE_KEYS = {"acceptance_id", "event_ids", "audio_event_ids", "transition_ids", "observable", "pass_condition"}
FALLBACK_KEYS = {"fallback_id", "trigger_acceptance_ids", "action"}
POLICY_KEYS = {
    "$schema", "schema_version", "policy_id", "policy_kind", "attestation", "status",
    "runtime_enabled", "preview_only", "profile_id", "operation", "model_profile_id",
    "model_variant", "region", "provider_locale", "surface_profile_sha256",
    "model_profile_sha256", "prompt_locales", "multi_shot", "audio", "exact_timing",
    "evidence_pins",
}
ATTESTATION_KEYS = {"method", "verification_record_sha256"}
MULTI_KEYS = {"status", "grammar", "max_shots", "transition_types"}
POLICY_AUDIO_KEYS = {"status", "semantic_functions", "voice_modes", "voice_reference_status"}
EXACT_KEYS = {"status", "range_unit", "evidence_claim_ids"}
PIN_KEYS = {"claim_id", "claim_sha256", "expires_at"}

ENTITY_KINDS = {"character", "product", "object", "environment", "effect", "text"}
MATERIAL_KINDS = {"rigid", "elastic", "fabric", "liquid", "granular", "organic", "smoke", "fire", "other"}
SPEAKER_ROLES = {"onscreen_character", "offscreen_character", "narrator"}
VOICE_MODES = {"generic_synthetic", "authorized_reference", "post_dub"}
AUTH_STATUSES = {"not_applicable", "user_attested_authorized", "unknown", "not_authorized"}
PHASES = {"opening_state", "action", "interaction_or_state_change", "response", "follow_through", "endpoint"}
INTERACTIONS = {"none", "contact", "material_change", "non_material_state_change"}
CAMERA_MOVES = {"locked", "push_in", "pull_out", "pan", "tilt", "tracking", "orbit", "crane", "dolly", "handheld"}
TRANSITION_TYPES = {"hard_cut", "match_cut", "dissolve", "fade"}
AUDIO_FUNCTIONS = {"dialogue", "voiceover", "sound_effect", "ambience", "music", "rhythm", "silence"}
TIMING_MODES = {"visual_event_window", "continuous_shot", "continuous_sequence", "relative_beat", "surface_exact_range"}
SUPPORT_STATUSES = {"supported", "unsupported", "unknown"}


class AVContractError(ValueError):
    """Stable, non-echoing AV contract failure."""

    def __init__(self, code: str, pointer: str = "/") -> None:
        super().__init__(code)
        self.code = code
        self.pointer = pointer


def _fail(code: str, pointer: str = "/") -> None:
    raise AVContractError(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("AV200_TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("AV201_OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(value: object, pointer: str, *, minimum: int = 0, maximum: int = 256) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("AV202_ARRAY_BOUNDS_INVALID", pointer)
    return value


def _id(value: object, pointer: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        _fail("AV203_IDENTIFIER_INVALID", pointer)
    return value


def _sha(value: object, pointer: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        _fail("AV204_SHA256_INVALID", pointer)
    return value


def _nullable_id(value: object, pointer: str) -> str | None:
    return None if value is None else _id(value, pointer)


def _nullable_sha(value: object, pointer: str) -> str | None:
    return None if value is None else _sha(value, pointer)


def _enum(value: object, allowed: set[str], pointer: str, code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(code, pointer)
    return value


def _text(value: object, pointer: str, *, maximum: int = 2_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("AV205_TEXT_INVALID", pointer)
    if LOCATOR_LIKE.search(value):
        _fail("AV206_TEXT_LOCATOR_FORBIDDEN", pointer)
    for character in value:
        number = ord(character)
        if number < 32 or number == 127 or number in BIDI_CONTROLS or unicodedata.category(character) == "Cf":
            _fail("AV207_TEXT_UNSAFE_UNICODE", pointer)
    return value


def _unique_ids(
    value: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 256,
) -> list[str]:
    raw = _array(value, pointer, minimum=minimum, maximum=maximum)
    checked = [_id(item, f"{pointer}/{index}") for index, item in enumerate(raw)]
    if len(checked) != len(set(checked)):
        _fail("AV208_IDENTIFIER_DUPLICATE", pointer)
    return checked


def _unique_text(value: object, pointer: str, *, minimum: int = 0, maximum: int = 16) -> list[str]:
    raw = _array(value, pointer, minimum=minimum, maximum=maximum)
    checked = [_text(item, f"{pointer}/{index}") for index, item in enumerate(raw)]
    if len(checked) != len(set(checked)):
        _fail("AV209_TEXT_DUPLICATE", pointer)
    return checked


def _language(value: object, pointer: str) -> str:
    if not isinstance(value, str) or len(value) > 63 or LANGUAGE_TAG.fullmatch(value) is None:
        _fail("AV030_LANGUAGE_TAG_INVALID", pointer)
    return value


def _safe_utterance(value: object, pointer: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2_000 or value != value.strip():
        _fail("AV031_UTTERANCE_INVALID", pointer)
    if unicodedata.normalize("NFC", value) != value:
        _fail("AV033_UTTERANCE_UNSAFE_UNICODE", pointer)
    if "\n" in value or "\r" in value:
        _fail("AV031_UTTERANCE_INVALID", pointer)
    if PROVIDER_TOKEN.search(value) or LOCATOR_LIKE.search(value):
        _fail("AV032_UTTERANCE_TOKEN_FORBIDDEN", pointer)
    for character in value:
        number = ord(character)
        if number < 32 or number == 127 or number in BIDI_CONTROLS or unicodedata.category(character) == "Cf":
            _fail("AV033_UTTERANCE_UNSAFE_UNICODE", pointer)
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)


def _parse_date(value: object, pointer: str) -> date:
    if not isinstance(value, str):
        _fail("AVP020_EVIDENCE_DATE_INVALID", pointer)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("AVP020_EVIDENCE_DATE_INVALID", pointer)
    if parsed.isoformat() != value:
        _fail("AVP020_EVIDENCE_DATE_INVALID", pointer)
    return parsed


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("AV210_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def parse_json_bytes(raw: bytes) -> object:
    if len(raw) > MAX_INPUT_BYTES:
        _fail("AV211_JSON_TOO_LARGE")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("AV212_JSON_UTF8_INVALID")
    try:
        return json.loads(
            text,
            object_pairs_hook=_json_pairs,
            parse_constant=lambda _value: _fail("AV213_JSON_NUMBER_INVALID"),
        )
    except AVContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        _fail("AV214_JSON_INVALID")


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read(path: str) -> bytes:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        try:
            with Path(path).open("rb") as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
        except OSError:
            _fail("AV215_INPUT_READ_FAILED")
    if len(raw) > MAX_INPUT_BYTES:
        _fail("AV211_JSON_TOO_LARGE")
    return raw


def validate_surface_av_policy(
    value: object,
    *,
    today: date | None = None,
    allow_unattested_fixture: bool = False,
    expected_surface_profile_sha256: str | None = None,
    expected_model_profile_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate a candidate policy without converting it into authority."""

    policy = _object(value, POLICY_KEYS, "/surface_av_policy")
    if policy["$schema"] != POLICY_SCHEMA_URI or not _is_int(policy["schema_version"]) or policy["schema_version"] != 1:
        _fail("AVP001_POLICY_CONTRACT_INVALID", "/surface_av_policy")
    policy_id = _id(policy["policy_id"], "/surface_av_policy/policy_id")
    kind = _enum(
        policy["policy_kind"],
        {"evidence_pinned", "unattested_fixture"},
        "/surface_av_policy/policy_kind",
        "AVP002_POLICY_KIND_INVALID",
    )
    attestation = _object(policy["attestation"], ATTESTATION_KEYS, "/surface_av_policy/attestation")
    verification = _nullable_sha(
        attestation["verification_record_sha256"],
        "/surface_av_policy/attestation/verification_record_sha256",
    )
    if kind == "unattested_fixture":
        if attestation["method"] != "unattested_fixture" or verification is not None:
            _fail("AVP003_POLICY_ATTESTATION_INVALID", "/surface_av_policy/attestation")
        if not allow_unattested_fixture:
            _fail("AVP004_UNATTESTED_POLICY_FORBIDDEN", "/surface_av_policy/policy_kind")
    else:
        if attestation["method"] != "evidence_registry" or verification is None:
            _fail("AVP003_POLICY_ATTESTATION_INVALID", "/surface_av_policy/attestation")
        trusted = TRUSTED_POLICY_BINDINGS.get(policy_id)
        supplied_policy_sha256 = hashlib.sha256(canonical_json(policy)).hexdigest()
        if trusted is None or supplied_policy_sha256 != trusted:
            _fail("AVP005_POLICY_UNTRUSTED", "/surface_av_policy/policy_id")

    if policy["status"] != "candidate" or policy["runtime_enabled"] is not False or policy["preview_only"] is not True:
        _fail("AVP006_CANDIDATE_BOUNDARY_INVALID", "/surface_av_policy/status")
    for field in ("profile_id", "model_profile_id", "model_variant"):
        _id(policy[field], f"/surface_av_policy/{field}")
    _enum(
        policy["operation"],
        {"reference_generation", "first_last_frame"},
        "/surface_av_policy/operation",
        "AVP007_OPERATION_INVALID",
    )
    region = policy["region"]
    if not isinstance(region, str) or (region not in {"global", "unknown"} and re.fullmatch(r"[A-Z]{2}", region) is None):
        _fail("AVP008_REGION_INVALID", "/surface_av_policy/region")
    provider_locale = _enum(
        policy["provider_locale"], {"global", "cn", "unknown"},
        "/surface_av_policy/provider_locale", "AVP009_PROVIDER_LOCALE_INVALID",
    )
    surface_hash = _sha(policy["surface_profile_sha256"], "/surface_av_policy/surface_profile_sha256")
    model_hash = _sha(policy["model_profile_sha256"], "/surface_av_policy/model_profile_sha256")
    if expected_surface_profile_sha256 is not None and surface_hash != expected_surface_profile_sha256:
        _fail("AVP010_SURFACE_PROFILE_HASH_MISMATCH", "/surface_av_policy/surface_profile_sha256")
    if expected_model_profile_sha256 is not None and model_hash != expected_model_profile_sha256:
        _fail("AVP011_MODEL_PROFILE_HASH_MISMATCH", "/surface_av_policy/model_profile_sha256")
    if policy["prompt_locales"] != ["en", "zh-Hans"]:
        _fail("AVP012_PROMPT_LOCALES_INVALID", "/surface_av_policy/prompt_locales")

    pins = _array(policy["evidence_pins"], "/surface_av_policy/evidence_pins", minimum=1, maximum=32)
    pin_ids: set[str] = set()
    effective_today = today or datetime.now(timezone.utc).date()
    for index, raw in enumerate(pins):
        pointer = f"/surface_av_policy/evidence_pins/{index}"
        pin = _object(raw, PIN_KEYS, pointer)
        claim = pin["claim_id"]
        if not isinstance(claim, str) or len(claim) > 100 or CLAIM_ID.fullmatch(claim) is None:
            _fail("AVP013_EVIDENCE_CLAIM_INVALID", f"{pointer}/claim_id")
        if claim in pin_ids:
            _fail("AVP014_EVIDENCE_CLAIM_DUPLICATE", f"{pointer}/claim_id")
        pin_ids.add(claim)
        _sha(pin["claim_sha256"], f"{pointer}/claim_sha256")
        if effective_today >= _parse_date(pin["expires_at"], f"{pointer}/expires_at"):
            _fail("AVP015_EVIDENCE_EXPIRED", f"{pointer}/expires_at")

    multi = _object(policy["multi_shot"], MULTI_KEYS, "/surface_av_policy/multi_shot")
    multi_status = _enum(multi["status"], SUPPORT_STATUSES, "/surface_av_policy/multi_shot/status", "AVP016_SUPPORT_STATUS_INVALID")
    grammar = _enum(
        multi["grammar"],
        {"none", "ascii_numbered_shot_labels", "localized_numbered_shot_labels", "ordered_paragraphs"},
        "/surface_av_policy/multi_shot/grammar", "AVP017_MULTI_GRAMMAR_INVALID",
    )
    transitions = _array(multi["transition_types"], "/surface_av_policy/multi_shot/transition_types", maximum=4)
    if any(not isinstance(item, str) or item not in TRANSITION_TYPES for item in transitions) or len(transitions) != len(set(transitions)):
        _fail("AVP018_TRANSITION_TYPES_INVALID", "/surface_av_policy/multi_shot/transition_types")
    if multi_status == "supported":
        if grammar == "none" or not _is_int(multi["max_shots"]) or not 2 <= multi["max_shots"] <= 32 or not transitions:
            _fail("AVP019_MULTI_SUPPORT_INCOHERENT", "/surface_av_policy/multi_shot")
    elif grammar != "none" or multi["max_shots"] is not None or transitions:
        _fail("AVP019_MULTI_SUPPORT_INCOHERENT", "/surface_av_policy/multi_shot")

    audio = _object(policy["audio"], POLICY_AUDIO_KEYS, "/surface_av_policy/audio")
    audio_status = _enum(audio["status"], SUPPORT_STATUSES, "/surface_av_policy/audio/status", "AVP016_SUPPORT_STATUS_INVALID")
    functions = _array(audio["semantic_functions"], "/surface_av_policy/audio/semantic_functions", maximum=7)
    modes = _array(audio["voice_modes"], "/surface_av_policy/audio/voice_modes", maximum=3)
    voice_ref = _enum(
        audio["voice_reference_status"], SUPPORT_STATUSES,
        "/surface_av_policy/audio/voice_reference_status", "AVP016_SUPPORT_STATUS_INVALID",
    )
    if any(not isinstance(item, str) or item not in AUDIO_FUNCTIONS for item in functions) or len(functions) != len(set(functions)):
        _fail("AVP021_AUDIO_FUNCTIONS_INVALID", "/surface_av_policy/audio/semantic_functions")
    if any(not isinstance(item, str) or item not in VOICE_MODES for item in modes) or len(modes) != len(set(modes)):
        _fail("AVP022_VOICE_MODES_INVALID", "/surface_av_policy/audio/voice_modes")
    if audio_status == "supported":
        if not functions:
            _fail("AVP023_AUDIO_SUPPORT_INCOHERENT", "/surface_av_policy/audio")
    elif functions or modes or voice_ref == "supported":
        _fail("AVP023_AUDIO_SUPPORT_INCOHERENT", "/surface_av_policy/audio")
    if (voice_ref == "supported") != ("authorized_reference" in modes):
        _fail("AVP024_VOICE_REFERENCE_INCOHERENT", "/surface_av_policy/audio")

    exact = _object(policy["exact_timing"], EXACT_KEYS, "/surface_av_policy/exact_timing")
    exact_status = _enum(exact["status"], SUPPORT_STATUSES, "/surface_av_policy/exact_timing/status", "AVP016_SUPPORT_STATUS_INVALID")
    exact_claims = _array(exact["evidence_claim_ids"], "/surface_av_policy/exact_timing/evidence_claim_ids", maximum=32)
    if any(not isinstance(item, str) or CLAIM_ID.fullmatch(item) is None for item in exact_claims) or len(exact_claims) != len(set(exact_claims)):
        _fail("AVP025_EXACT_EVIDENCE_INVALID", "/surface_av_policy/exact_timing/evidence_claim_ids")
    if set(exact_claims) - pin_ids:
        _fail("AVP026_EXACT_EVIDENCE_NOT_PINNED", "/surface_av_policy/exact_timing/evidence_claim_ids")
    if exact_status == "supported":
        if exact["range_unit"] != "seconds" or not exact_claims:
            _fail("AVP027_EXACT_SUPPORT_INCOHERENT", "/surface_av_policy/exact_timing")
    elif exact["range_unit"] is not None or exact_claims:
        _fail("AVP027_EXACT_SUPPORT_INCOHERENT", "/surface_av_policy/exact_timing")

    if any(status == "supported" for status in (multi_status, audio_status, exact_status)) and (
        region == "unknown" or provider_locale == "unknown"
    ):
        _fail("AVP028_SURFACE_SCOPE_UNKNOWN", "/surface_av_policy")
    return policy


def _ancestors(event_id: str, dependencies: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    pending = list(dependencies[event_id])
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(dependencies[current])
    return found


def validate_scene_ir(
    value: object,
    *,
    policy: dict[str, Any] | None = None,
    allow_unattested_policy: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Validate a V2 scene, optionally against an exact AV surface policy."""

    scene = _object(value, ROOT_KEYS, "/scene_ir")
    if scene["$schema"] != SCENE_SCHEMA_URI or not _is_int(scene["schema_version"]) or scene["schema_version"] != 2:
        _fail("AV001_SCENE_CONTRACT_INVALID", "/scene_ir")
    checked_policy = None
    if policy is not None:
        checked_policy = validate_surface_av_policy(
            policy,
            today=today,
            allow_unattested_fixture=allow_unattested_policy,
        )

    state = _object(scene["state_binding"], STATE_KEYS, "/scene_ir/state_binding")
    _id(state["project_id"], "/scene_ir/state_binding/project_id")
    _id(state["clip_id"], "/scene_ir/state_binding/clip_id")
    for field in ("state_revision", "canon_revision"):
        if not _is_int(state[field]) or state[field] < 1:
            _fail("AV002_STATE_REVISION_INVALID", f"/scene_ir/state_binding/{field}")
    for field in ("semantic_state_sha256", "planned_start_snapshot_sha256", "planned_end_snapshot_sha256"):
        _sha(state[field], f"/scene_ir/state_binding/{field}")
    completed = set(_unique_ids(state["completed_beat_ids"], "/scene_ir/state_binding/completed_beat_ids", maximum=4096))
    current_list = _unique_ids(state["current_beat_ids"], "/scene_ir/state_binding/current_beat_ids", minimum=1, maximum=4096)
    current = set(current_list)
    reserved = set(_unique_ids(state["reserved_future_beat_ids"], "/scene_ir/state_binding/reserved_future_beat_ids", maximum=4096))
    if completed & current or completed & reserved or current & reserved:
        _fail("AV003_STATE_BEAT_OVERLAP", "/scene_ir/state_binding")

    take_structure = _enum(
        scene["take_structure"], {"single_continuous_take", "edited_multi_shot"},
        "/scene_ir/take_structure", "AV004_TAKE_STRUCTURE_INVALID",
    )
    timing_policy = _enum(
        scene["timing_policy"], {"ordered_phases", "relative_beats", "surface_exact_ranges"},
        "/scene_ir/timing_policy", "AV005_TIMING_POLICY_INVALID",
    )

    entity_ids: set[str] = set()
    entity_kind: dict[str, str] = {}
    for index, raw in enumerate(_array(scene["entities"], "/scene_ir/entities", minimum=1, maximum=128)):
        pointer = f"/scene_ir/entities/{index}"
        entity = _object(raw, ENTITY_KEYS, pointer)
        entity_id = _id(entity["entity_id"], f"{pointer}/entity_id")
        if entity_id in entity_ids:
            _fail("AV006_ENTITY_DUPLICATE", f"{pointer}/entity_id")
        entity_ids.add(entity_id)
        entity_kind[entity_id] = _enum(entity["kind"], ENTITY_KINDS, f"{pointer}/kind", "AV007_ENTITY_KIND_INVALID")
        _text(entity["label"], f"{pointer}/label")
        _unique_text(entity["stable_features"], f"{pointer}/stable_features", minimum=1)

    material_ids: set[str] = set()
    material_owner: dict[str, str] = {}
    for index, raw in enumerate(_array(scene["materials"], "/scene_ir/materials", maximum=128)):
        pointer = f"/scene_ir/materials/{index}"
        material = _object(raw, MATERIAL_KEYS, pointer)
        material_id = _id(material["material_id"], f"{pointer}/material_id")
        if material_id in material_ids:
            _fail("AV008_MATERIAL_DUPLICATE", f"{pointer}/material_id")
        material_ids.add(material_id)
        owner = _id(material["entity_id"], f"{pointer}/entity_id")
        if owner not in entity_ids:
            _fail("AV009_MATERIAL_ENTITY_UNKNOWN", f"{pointer}/entity_id")
        material_owner[material_id] = owner
        _enum(material["kind"], MATERIAL_KINDS, f"{pointer}/kind", "AV010_MATERIAL_KIND_INVALID")
        _unique_text(material["response_properties"], f"{pointer}/response_properties", minimum=1)

    speaker_ids: set[str] = set()
    speakers: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(scene["speakers"], "/scene_ir/speakers", maximum=32)):
        pointer = f"/scene_ir/speakers/{index}"
        speaker = _object(raw, SPEAKER_KEYS, pointer)
        speaker_id = _id(speaker["speaker_id"], f"{pointer}/speaker_id")
        if speaker_id in speaker_ids:
            _fail("AV011_SPEAKER_DUPLICATE", f"{pointer}/speaker_id")
        speaker_ids.add(speaker_id)
        entity_id = _nullable_id(speaker["entity_id"], f"{pointer}/entity_id")
        role = _enum(speaker["role"], SPEAKER_ROLES, f"{pointer}/role", "AV012_SPEAKER_ROLE_INVALID")
        if role != "narrator" and (entity_id is None or entity_kind.get(entity_id) != "character"):
            _fail("AV013_SPEAKER_ENTITY_INVALID", f"{pointer}/entity_id")
        if entity_id is not None and entity_id not in entity_ids:
            _fail("AV013_SPEAKER_ENTITY_INVALID", f"{pointer}/entity_id")
        _text(speaker["display_name"], f"{pointer}/display_name")
        voice = _object(speaker["voice"], VOICE_KEYS, f"{pointer}/voice")
        mode = _enum(voice["mode"], VOICE_MODES, f"{pointer}/voice/mode", "AV014_VOICE_MODE_INVALID")
        target = _nullable_id(voice["authority_target_id"], f"{pointer}/voice/authority_target_id")
        asset = _nullable_id(voice["asset_id"], f"{pointer}/voice/asset_id")
        auth = _enum(voice["authorization_status"], AUTH_STATUSES, f"{pointer}/voice/authorization_status", "AV015_VOICE_AUTH_INVALID")
        attestation = _nullable_sha(voice["attestation_sha256"], f"{pointer}/voice/attestation_sha256")
        if mode == "generic_synthetic" and (target is not None or asset is not None or auth != "not_applicable" or attestation is not None):
            _fail("AV016_GENERIC_VOICE_BINDING_FORBIDDEN", f"{pointer}/voice")
        if mode == "authorized_reference" and (
            entity_id is None
            or target != entity_id
            or asset is None
            or auth != "user_attested_authorized"
            or attestation is None
        ):
            _fail("AV017_VOICE_REFERENCE_UNAUTHORIZED", f"{pointer}/voice")
        if mode == "post_dub" and (target is not None or asset is not None or attestation is not None):
            _fail("AV018_POST_DUB_BINDING_FORBIDDEN", f"{pointer}/voice")
        speakers[speaker_id] = {"entity_id": entity_id, "role": role, "voice": voice}

    shots = _array(scene["shots"], "/scene_ir/shots", minimum=1, maximum=32)
    if take_structure == "single_continuous_take" and len(shots) != 1:
        _fail("AV020_CONTINUOUS_TAKE_SHOT_COUNT", "/scene_ir/shots")
    if take_structure == "edited_multi_shot" and len(shots) < 2:
        _fail("AV021_EDITED_TAKE_SHOT_COUNT", "/scene_ir/shots")
    shot_ids: list[str] = []
    shot_index: dict[str, int] = {}
    shot_open: dict[str, str] = {}
    shot_end: dict[str, str] = {}
    event_ids: set[str] = set()
    event_shot: dict[str, str] = {}
    event_order: dict[str, int] = {}
    authored_beats: set[str] = set()
    ordinal = 0
    for shot_offset, raw in enumerate(shots):
        pointer = f"/scene_ir/shots/{shot_offset}"
        shot = _object(raw, SHOT_KEYS, pointer)
        shot_id = _id(shot["shot_id"], f"{pointer}/shot_id")
        if shot_id in shot_index:
            _fail("AV022_SHOT_DUPLICATE", f"{pointer}/shot_id")
        if not _is_int(shot["shot_index"]) or shot["shot_index"] != shot_offset + 1:
            _fail("AV023_SHOT_ORDER_INVALID", f"{pointer}/shot_index")
        shot_ids.append(shot_id)
        shot_index[shot_id] = shot_offset
        events = _array(shot["events"], f"{pointer}/events", minimum=2, maximum=64)
        local_ids: list[str] = []
        local_events: dict[str, dict[str, Any]] = {}
        dependencies: dict[str, list[str]] = {}
        for event_offset, raw_event in enumerate(events):
            event_pointer = f"{pointer}/events/{event_offset}"
            event = _object(raw_event, EVENT_KEYS, event_pointer)
            event_id = _id(event["event_id"], f"{event_pointer}/event_id")
            if event_id in event_ids:
                _fail("AV024_EVENT_DUPLICATE", f"{event_pointer}/event_id")
            if not _is_int(event["event_index"]) or event["event_index"] != event_offset + 1:
                _fail("AV025_EVENT_ORDER_INVALID", f"{event_pointer}/event_index")
            _enum(event["phase"], PHASES, f"{event_pointer}/phase", "AV026_EVENT_PHASE_INVALID")
            actors = _unique_ids(event["actor_ids"], f"{event_pointer}/actor_ids", maximum=16)
            targets = _unique_ids(event["target_ids"], f"{event_pointer}/target_ids", maximum=16)
            if not actors and not targets:
                _fail("AV027_EVENT_PARTICIPANT_REQUIRED", event_pointer)
            if any(item not in entity_ids for item in [*actors, *targets]):
                _fail("AV028_EVENT_ENTITY_UNKNOWN", event_pointer)
            dependency_ids = _unique_ids(event["depends_on"], f"{event_pointer}/depends_on", maximum=16)
            _text(event["visible_state_change"], f"{event_pointer}/visible_state_change")
            beats = _unique_ids(event["beat_ids"], f"{event_pointer}/beat_ids", minimum=1, maximum=64)
            if any(beat not in current for beat in beats):
                _fail("AV029_EVENT_BEAT_OUT_OF_SCOPE", f"{event_pointer}/beat_ids")
            authored_beats.update(beats)
            interaction = _enum(event["interaction_kind"], INTERACTIONS, f"{event_pointer}/interaction_kind", "AV034_INTERACTION_INVALID")
            materials = _unique_ids(event["material_ids"], f"{event_pointer}/material_ids", maximum=16)
            if any(item not in material_ids for item in materials):
                _fail("AV035_EVENT_MATERIAL_UNKNOWN", f"{event_pointer}/material_ids")
            participants = set(actors) | set(targets)
            if any(material_owner[item] not in participants for item in materials):
                _fail("AV036_MATERIAL_OWNER_NOT_PARTICIPANT", f"{event_pointer}/material_ids")
            if interaction in {"contact", "material_change"} and not materials:
                _fail("AV037_MATERIAL_RESPONSE_REQUIRED", f"{event_pointer}/material_ids")
            if interaction in {"none", "non_material_state_change"} and materials:
                _fail("AV038_MATERIAL_WITHOUT_INTERACTION", f"{event_pointer}/material_ids")
            event_ids.add(event_id)
            local_ids.append(event_id)
            local_events[event_id] = event
            dependencies[event_id] = dependency_ids
            event_shot[event_id] = shot_id
            event_order[event_id] = ordinal
            ordinal += 1

        opening = _id(shot["opening_event_id"], f"{pointer}/opening_event_id")
        endpoint = _id(shot["endpoint_event_id"], f"{pointer}/endpoint_event_id")
        if opening != local_ids[0] or local_events[opening]["phase"] != "opening_state" or dependencies[opening]:
            _fail("AV039_OPENING_EVENT_INVALID", f"{pointer}/opening_event_id")
        if endpoint != local_ids[-1] or local_events[endpoint]["phase"] != "endpoint":
            _fail("AV040_ENDPOINT_EVENT_INVALID", f"{pointer}/endpoint_event_id")
        for event_offset, event_id in enumerate(local_ids):
            for dependency in dependencies[event_id]:
                if dependency not in local_events:
                    _fail("AV041_CROSS_SHOT_EVENT_DEPENDENCY", f"{pointer}/events/{event_offset}/depends_on")
                if local_ids.index(dependency) >= event_offset:
                    _fail("AV042_EVENT_DEPENDENCY_ORDER", f"{pointer}/events/{event_offset}/depends_on")
            if event_id != opening and opening not in _ancestors(event_id, dependencies):
                _fail("AV043_EVENT_NOT_OPENING_REACHABLE", f"{pointer}/events/{event_offset}")
        endpoint_ancestors = _ancestors(endpoint, dependencies)
        if any(event_id not in endpoint_ancestors for event_id in local_ids[:-1]):
            _fail("AV044_ENDPOINT_NOT_FULLY_REACHABLE", f"{pointer}/endpoint_event_id")
        camera = _object(shot["camera"], CAMERA_KEYS, f"{pointer}/camera")
        move = _enum(camera["move_kind"], CAMERA_MOVES, f"{pointer}/camera/move_kind", "AV045_CAMERA_MOVE_INVALID")
        for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing"):
            _text(camera[field], f"{pointer}/camera/{field}")
        if move == "locked" and camera["speed"].strip().casefold() != "static":
            _fail("AV046_LOCKED_CAMERA_SPEED", f"{pointer}/camera/speed")
        observed = _unique_ids(camera["observed_event_ids"], f"{pointer}/camera/observed_event_ids", minimum=2, maximum=64)
        if any(item not in local_events for item in observed) or opening not in observed or endpoint not in observed:
            _fail("AV047_CAMERA_OBSERVABILITY_INVALID", f"{pointer}/camera/observed_event_ids")
        risks = _unique_text(camera["occlusion_risks"], f"{pointer}/camera/occlusion_risks")
        mitigations = _unique_text(camera["mitigations"], f"{pointer}/camera/mitigations")
        if risks and not mitigations:
            _fail("AV048_OCCLUSION_UNMITIGATED", f"{pointer}/camera/mitigations")
        shot_open[shot_id] = opening
        shot_end[shot_id] = endpoint

    invariant_ids: set[str] = set()
    for index, raw in enumerate(_array(scene["requested_invariants"], "/scene_ir/requested_invariants", maximum=128)):
        pointer = f"/scene_ir/requested_invariants/{index}"
        invariant = _object(raw, INVARIANT_KEYS, pointer)
        invariant_id = _id(invariant["invariant_id"], f"{pointer}/invariant_id")
        if invariant_id in invariant_ids:
            _fail("AV049_INVARIANT_DUPLICATE", f"{pointer}/invariant_id")
        invariant_ids.add(invariant_id)
        owners = _unique_ids(invariant["entity_ids"], f"{pointer}/entity_ids", minimum=1, maximum=16)
        if any(item not in entity_ids for item in owners):
            _fail("AV050_INVARIANT_ENTITY_UNKNOWN", f"{pointer}/entity_ids")
        _text(invariant["description"], f"{pointer}/description")

    transitions = _array(scene["transitions"], "/scene_ir/transitions", maximum=31)
    if take_structure == "single_continuous_take" and transitions:
        _fail("AV051_CONTINUOUS_TAKE_TRANSITION_FORBIDDEN", "/scene_ir/transitions")
    if take_structure == "edited_multi_shot" and len(transitions) != len(shots) - 1:
        _fail("AV052_TRANSITION_CHAIN_INCOMPLETE", "/scene_ir/transitions")
    transition_ids: set[str] = set()
    transition_by_id: dict[str, dict[str, Any]] = {}
    bridged_audio: dict[str, set[str]] = {}
    for index, raw in enumerate(transitions):
        pointer = f"/scene_ir/transitions/{index}"
        transition = _object(raw, TRANSITION_KEYS, pointer)
        transition_id = _id(transition["transition_id"], f"{pointer}/transition_id")
        if transition_id in transition_ids:
            _fail("AV053_TRANSITION_DUPLICATE", f"{pointer}/transition_id")
        transition_ids.add(transition_id)
        if not _is_int(transition["transition_index"]) or transition["transition_index"] != index + 1:
            _fail("AV054_TRANSITION_ORDER_INVALID", f"{pointer}/transition_index")
        if transition["from_shot_id"] != shot_ids[index] or transition["to_shot_id"] != shot_ids[index + 1]:
            _fail("AV055_TRANSITION_NOT_ADJACENT", pointer)
        transition_type = _enum(transition["transition_type"], TRANSITION_TYPES, f"{pointer}/transition_type", "AV056_TRANSITION_TYPE_INVALID")
        if transition["from_event_id"] != shot_end[shot_ids[index]] or transition["to_event_id"] != shot_open[shot_ids[index + 1]]:
            _fail("AV057_TRANSITION_BOUNDARY_INVALID", pointer)
        beats = _unique_ids(transition["beat_ids"], f"{pointer}/beat_ids", minimum=1, maximum=64)
        if any(beat not in current for beat in beats):
            _fail("AV058_TRANSITION_BEAT_OUT_OF_SCOPE", f"{pointer}/beat_ids")
        authored_beats.update(beats)
        preserved = _unique_ids(transition["preserved_invariant_ids"], f"{pointer}/preserved_invariant_ids", maximum=128)
        if any(item not in invariant_ids for item in preserved):
            _fail("AV059_TRANSITION_INVARIANT_UNKNOWN", f"{pointer}/preserved_invariant_ids")
        if transition_type == "match_cut" and not preserved:
            _fail("AV060_MATCH_CUT_INVARIANT_REQUIRED", f"{pointer}/preserved_invariant_ids")
        changes = _unique_ids(transition["allowed_change_event_ids"], f"{pointer}/allowed_change_event_ids", maximum=128)
        allowed_boundary_events = {
            event_id for event_id, owner in event_shot.items()
            if owner in {shot_ids[index], shot_ids[index + 1]}
        }
        if any(item not in allowed_boundary_events for item in changes):
            _fail("AV061_TRANSITION_CHANGE_EVENT_INVALID", f"{pointer}/allowed_change_event_ids")
        bridges = _unique_ids(transition["audio_bridge_event_ids"], f"{pointer}/audio_bridge_event_ids", maximum=128)
        bridged_audio[transition_id] = set(bridges)
        transition_by_id[transition_id] = transition

    audio_ids: set[str] = set()
    audio_by_id: dict[str, dict[str, Any]] = {}
    speech_turns: list[int] = []
    speech_ids: set[str] = set()
    exact_claims_used: set[str] = set()
    for index, raw in enumerate(_array(scene["audio_events"], "/scene_ir/audio_events", maximum=128)):
        pointer = f"/scene_ir/audio_events/{index}"
        audio = _object(raw, AUDIO_KEYS, pointer)
        audio_id = _id(audio["audio_event_id"], f"{pointer}/audio_event_id")
        if audio_id in audio_ids:
            _fail("AV062_AUDIO_DUPLICATE", f"{pointer}/audio_event_id")
        audio_ids.add(audio_id)
        if not _is_int(audio["audio_event_index"]) or audio["audio_event_index"] != index + 1:
            _fail("AV063_AUDIO_ORDER_INVALID", f"{pointer}/audio_event_index")
        function = _enum(audio["semantic_function"], AUDIO_FUNCTIONS, f"{pointer}/semantic_function", "AV064_AUDIO_FUNCTION_INVALID")
        scope = _unique_ids(audio["shot_ids"], f"{pointer}/shot_ids", minimum=1, maximum=32)
        if any(item not in shot_index for item in scope):
            _fail("AV065_AUDIO_SHOT_UNKNOWN", f"{pointer}/shot_ids")
        indexes = [shot_index[item] for item in scope]
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            _fail("AV066_AUDIO_SHOT_SCOPE_NONCONTIGUOUS", f"{pointer}/shot_ids")
        beats = _unique_ids(audio["beat_ids"], f"{pointer}/beat_ids", minimum=1, maximum=64)
        if any(beat not in current for beat in beats):
            _fail("AV067_AUDIO_BEAT_OUT_OF_SCOPE", f"{pointer}/beat_ids")
        authored_beats.update(beats)
        sources = _unique_ids(audio["source_entity_ids"], f"{pointer}/source_entity_ids", maximum=16)
        if any(item not in entity_ids for item in sources):
            _fail("AV068_AUDIO_SOURCE_UNKNOWN", f"{pointer}/source_entity_ids")
        _text(audio["description"], f"{pointer}/description")
        timing = _object(audio["timing"], TIMING_KEYS, f"{pointer}/timing")
        timing_mode = _enum(timing["mode"], TIMING_MODES, f"{pointer}/timing/mode", "AV069_AUDIO_TIMING_MODE_INVALID")
        start = _nullable_id(timing["start_event_id"], f"{pointer}/timing/start_event_id")
        end = _nullable_id(timing["end_event_id"], f"{pointer}/timing/end_event_id")
        cue = _nullable_id(timing["cue_event_id"], f"{pointer}/timing/cue_event_id")
        beat_label = timing["beat_label"]
        if beat_label is not None:
            _text(beat_label, f"{pointer}/timing/beat_label", maximum=200)
        evidence = _array(timing["evidence_claim_ids"], f"{pointer}/timing/evidence_claim_ids", maximum=32)
        if any(not isinstance(item, str) or CLAIM_ID.fullmatch(item) is None for item in evidence) or len(evidence) != len(set(evidence)):
            _fail("AV070_AUDIO_TIMING_EVIDENCE_INVALID", f"{pointer}/timing/evidence_claim_ids")
        scope_set = set(scope)
        if timing_mode == "visual_event_window":
            if start is None or end is None or cue is not None or beat_label is not None or timing["start_seconds"] is not None or timing["end_seconds"] is not None or evidence:
                _fail("AV071_AUDIO_TIMING_FIELDS_INVALID", f"{pointer}/timing")
            if start not in event_ids or end not in event_ids or event_shot[start] not in scope_set or event_shot[end] not in scope_set or event_order[start] > event_order[end]:
                _fail("AV072_AUDIO_EVENT_WINDOW_INVALID", f"{pointer}/timing")
        elif timing_mode == "continuous_shot":
            if len(scope) != 1 or any(value is not None for value in (start, end, cue, beat_label, timing["start_seconds"], timing["end_seconds"])) or evidence:
                _fail("AV071_AUDIO_TIMING_FIELDS_INVALID", f"{pointer}/timing")
        elif timing_mode == "continuous_sequence":
            if len(scope) < 2 or any(value is not None for value in (start, end, cue, beat_label, timing["start_seconds"], timing["end_seconds"])) or evidence:
                _fail("AV071_AUDIO_TIMING_FIELDS_INVALID", f"{pointer}/timing")
        elif timing_mode == "relative_beat":
            if cue is None or cue not in event_ids or event_shot[cue] not in scope_set or beat_label is None or any(value is not None for value in (start, end, timing["start_seconds"], timing["end_seconds"])) or evidence:
                _fail("AV071_AUDIO_TIMING_FIELDS_INVALID", f"{pointer}/timing")
        else:
            start_seconds = timing["start_seconds"]
            end_seconds = timing["end_seconds"]
            if any(value is not None for value in (start, end, cue, beat_label)) or not _is_number(start_seconds) or not _is_number(end_seconds) or not 0 <= start_seconds < end_seconds <= 60 or not evidence:
                _fail("AV071_AUDIO_TIMING_FIELDS_INVALID", f"{pointer}/timing")
            exact_claims_used.update(evidence)
        if timing_policy == "ordered_phases" and timing_mode in {"relative_beat", "surface_exact_range"}:
            _fail("AV073_TIMING_POLICY_MISMATCH", f"{pointer}/timing/mode")
        if timing_policy == "relative_beats" and timing_mode == "surface_exact_range":
            _fail("AV073_TIMING_POLICY_MISMATCH", f"{pointer}/timing/mode")
        if timing_policy == "surface_exact_ranges" and timing_mode != "surface_exact_range":
            _fail("AV073_TIMING_POLICY_MISMATCH", f"{pointer}/timing/mode")

        speech = audio["speech"]
        if function in {"dialogue", "voiceover"}:
            speech = _object(speech, SPEECH_KEYS, f"{pointer}/speech")
            speaker_id = _id(speech["speaker_id"], f"{pointer}/speech/speaker_id")
            if speaker_id not in speakers:
                _fail("AV074_SPEECH_SPEAKER_UNKNOWN", f"{pointer}/speech/speaker_id")
            speaker = speakers[speaker_id]
            if function == "dialogue" and (speaker["role"] == "narrator" or len(scope) != 1):
                _fail("AV075_DIALOGUE_SPEAKER_OR_SCOPE_INVALID", f"{pointer}/speech")
            expected_sources = [] if speaker["entity_id"] is None else [speaker["entity_id"]]
            if sources != expected_sources:
                _fail("AV076_SPEECH_SOURCE_MISMATCH", f"{pointer}/source_entity_ids")
            _language(speech["spoken_language"], f"{pointer}/speech/spoken_language")
            utterance = _safe_utterance(speech["utterance"], f"{pointer}/speech/utterance")
            supplied_hash = _sha(speech["utterance_sha256"], f"{pointer}/speech/utterance_sha256")
            if hashlib.sha256(utterance.encode("utf-8")).hexdigest() != supplied_hash:
                _fail("AV077_UTTERANCE_HASH_MISMATCH", f"{pointer}/speech/utterance_sha256")
            if not _is_int(speech["turn_index"]) or not 1 <= speech["turn_index"] <= 128:
                _fail("AV078_SPEECH_TURN_INVALID", f"{pointer}/speech/turn_index")
            speech_turns.append(speech["turn_index"])
            _enum(speech["overlap_policy"], {"no_overlap", "overlap_allowed"}, f"{pointer}/speech/overlap_policy", "AV079_OVERLAP_POLICY_INVALID")
            lip_sync = _enum(speech["lip_sync"], {"required", "not_required", "post_only"}, f"{pointer}/speech/lip_sync", "AV080_LIP_SYNC_INVALID")
            voice_mode = speaker["voice"]["mode"]
            if lip_sync == "required" and (function != "dialogue" or speaker["role"] != "onscreen_character" or voice_mode == "post_dub"):
                _fail("AV081_LIP_SYNC_REQUIREMENT_INVALID", f"{pointer}/speech/lip_sync")
            if (voice_mode == "post_dub") != (lip_sync == "post_only"):
                _fail("AV082_POST_DUB_EMISSION_INVALID", f"{pointer}/speech/lip_sync")
            _text(speech["delivery_intent"], f"{pointer}/speech/delivery_intent")
            speech_ids.add(audio_id)
        elif speech is not None:
            _fail("AV083_NONSPEECH_HAS_SPEECH", f"{pointer}/speech")
        audio_by_id[audio_id] = audio

    if speech_turns != list(range(1, len(speech_turns) + 1)):
        _fail("AV084_SPEECH_TURNS_NONCONTIGUOUS", "/scene_ir/audio_events")
    for transition_id, bridges in bridged_audio.items():
        transition = transition_by_id[transition_id]
        left = transition["from_shot_id"]
        right = transition["to_shot_id"]
        for audio_id in bridges:
            audio = audio_by_id.get(audio_id)
            if audio is None or left not in audio["shot_ids"] or right not in audio["shot_ids"]:
                _fail("AV085_AUDIO_BRIDGE_INVALID", "/scene_ir/transitions")
    for audio_id, audio in audio_by_id.items():
        scope = audio["shot_ids"]
        if len(scope) > 1:
            for left_index in range(shot_index[scope[0]], shot_index[scope[-1]]):
                transition_id = transitions[left_index]["transition_id"]
                if audio_id not in bridged_audio[transition_id]:
                    _fail("AV086_AUDIO_BRIDGE_COVERAGE", "/scene_ir/transitions")

    if timing_policy == "surface_exact_ranges":
        if checked_policy is None:
            _fail("AV087_EXACT_TIMING_POLICY_REQUIRED", "/scene_ir/timing_policy")
        exact = checked_policy["exact_timing"]
        if exact["status"] != "supported" or exact["range_unit"] != "seconds":
            _fail("AV088_EXACT_TIMING_UNSUPPORTED", "/surface_av_policy/exact_timing")
        if not exact_claims_used or exact_claims_used - set(exact["evidence_claim_ids"]):
            _fail("AV089_EXACT_TIMING_EVIDENCE_MISMATCH", "/scene_ir/audio_events")

    subtitle = _object(scene["subtitle_policy"], SUBTITLE_KEYS, "/scene_ir/subtitle_policy")
    subtitle_mode = _enum(
        subtitle["mode"], {"none", "post_subtitles", "post_sdh_captions", "post_forced_narrative"},
        "/scene_ir/subtitle_policy/mode", "AV090_SUBTITLE_MODE_INVALID",
    )
    languages = _array(subtitle["target_language_tags"], "/scene_ir/subtitle_policy/target_language_tags", maximum=16)
    if len(languages) != len(set(languages)):
        _fail("AV091_SUBTITLE_LANGUAGE_DUPLICATE", "/scene_ir/subtitle_policy/target_language_tags")
    for index, item in enumerate(languages):
        _language(item, f"/scene_ir/subtitle_policy/target_language_tags/{index}")
    if subtitle_mode == "none":
        if languages or subtitle["picture_policy"] != "not_applicable":
            _fail("AV092_SUBTITLE_POLICY_INCOHERENT", "/scene_ir/subtitle_policy")
    elif not languages or subtitle["picture_policy"] != "clean_picture":
        _fail("AV092_SUBTITLE_POLICY_INCOHERENT", "/scene_ir/subtitle_policy")

    if checked_policy is not None:
        multi = checked_policy["multi_shot"]
        if take_structure == "edited_multi_shot":
            if multi["status"] != "supported" or len(shots) > multi["max_shots"]:
                _fail("AV093_MULTI_SHOT_UNSUPPORTED", "/surface_av_policy/multi_shot")
            if any(item["transition_type"] not in multi["transition_types"] for item in transitions):
                _fail("AV094_TRANSITION_UNSUPPORTED", "/scene_ir/transitions")
        policy_audio = checked_policy["audio"]
        if audio_ids:
            if policy_audio["status"] != "supported":
                _fail("AV095_AUDIO_UNSUPPORTED", "/surface_av_policy/audio")
            if any(item["semantic_function"] not in policy_audio["semantic_functions"] for item in audio_by_id.values()):
                _fail("AV096_AUDIO_FUNCTION_UNSUPPORTED", "/scene_ir/audio_events")
            used_modes = {speakers[item["speech"]["speaker_id"]]["voice"]["mode"] for item in audio_by_id.values() if item["speech"] is not None}
            if used_modes - set(policy_audio["voice_modes"]):
                _fail("AV097_VOICE_MODE_UNSUPPORTED", "/scene_ir/speakers")
            if "authorized_reference" in used_modes and policy_audio["voice_reference_status"] != "supported":
                _fail("AV098_VOICE_REFERENCE_UNSUPPORTED", "/surface_av_policy/audio/voice_reference_status")

    if authored_beats != current:
        _fail("AV099_CURRENT_BEAT_COVERAGE", "/scene_ir/state_binding/current_beat_ids")

    fragility_ids: set[str] = set()
    for index, raw in enumerate(_array(scene["known_fragilities"], "/scene_ir/known_fragilities", maximum=128)):
        pointer = f"/scene_ir/known_fragilities/{index}"
        fragility = _object(raw, FRAGILITY_KEYS, pointer)
        fragility_id = _id(fragility["fragility_id"], f"{pointer}/fragility_id")
        if fragility_id in fragility_ids:
            _fail("AV100_FRAGILITY_DUPLICATE", f"{pointer}/fragility_id")
        fragility_ids.add(fragility_id)
        links = {
            "event_ids": event_ids,
            "audio_event_ids": audio_ids,
            "transition_ids": transition_ids,
        }
        total = 0
        for field, known in links.items():
            values = _unique_ids(fragility[field], f"{pointer}/{field}", maximum=256)
            total += len(values)
            if any(item not in known for item in values):
                _fail("AV101_FRAGILITY_LINK_UNKNOWN", f"{pointer}/{field}")
        if total == 0:
            _fail("AV102_FRAGILITY_LINK_REQUIRED", pointer)
        _text(fragility["description"], f"{pointer}/description")

    acceptance_ids: set[str] = set()
    covered_events: set[str] = set()
    covered_audio: set[str] = set()
    covered_transitions: set[str] = set()
    for index, raw in enumerate(_array(scene["acceptance_tests"], "/scene_ir/acceptance_tests", minimum=1, maximum=256)):
        pointer = f"/scene_ir/acceptance_tests/{index}"
        acceptance = _object(raw, ACCEPTANCE_KEYS, pointer)
        acceptance_id = _id(acceptance["acceptance_id"], f"{pointer}/acceptance_id")
        if acceptance_id in acceptance_ids:
            _fail("AV103_ACCEPTANCE_DUPLICATE", f"{pointer}/acceptance_id")
        acceptance_ids.add(acceptance_id)
        total = 0
        for field, known, covered in (
            ("event_ids", event_ids, covered_events),
            ("audio_event_ids", audio_ids, covered_audio),
            ("transition_ids", transition_ids, covered_transitions),
        ):
            values = _unique_ids(acceptance[field], f"{pointer}/{field}", maximum=256)
            total += len(values)
            if any(item not in known for item in values):
                _fail("AV104_ACCEPTANCE_LINK_UNKNOWN", f"{pointer}/{field}")
            covered.update(values)
        if total == 0:
            _fail("AV105_ACCEPTANCE_LINK_REQUIRED", pointer)
        _text(acceptance["observable"], f"{pointer}/observable")
        _text(acceptance["pass_condition"], f"{pointer}/pass_condition")
    if set(shot_end.values()) - covered_events or audio_ids - covered_audio or transition_ids - covered_transitions:
        _fail("AV106_ACCEPTANCE_COVERAGE_INCOMPLETE", "/scene_ir/acceptance_tests")

    fallback_ids: set[str] = set()
    for index, raw in enumerate(_array(scene["post_fallbacks"], "/scene_ir/post_fallbacks", maximum=128)):
        pointer = f"/scene_ir/post_fallbacks/{index}"
        fallback = _object(raw, FALLBACK_KEYS, pointer)
        fallback_id = _id(fallback["fallback_id"], f"{pointer}/fallback_id")
        if fallback_id in fallback_ids:
            _fail("AV107_FALLBACK_DUPLICATE", f"{pointer}/fallback_id")
        fallback_ids.add(fallback_id)
        triggers = _unique_ids(fallback["trigger_acceptance_ids"], f"{pointer}/trigger_acceptance_ids", minimum=1, maximum=256)
        if any(item not in acceptance_ids for item in triggers):
            _fail("AV108_FALLBACK_TRIGGER_UNKNOWN", f"{pointer}/trigger_acceptance_ids")
        _text(fallback["action"], f"{pointer}/action")
    return scene


def _self_test() -> None:
    try:
        parse_json_bytes(b'{"x":1,"x":2}')
    except AVContractError as exc:
        if exc.code != "AV210_JSON_DUPLICATE_KEY":
            _fail("AV900_SELF_TEST_FAILED")
    else:
        _fail("AV900_SELF_TEST_FAILED")
    if hashlib.sha256(_safe_utterance("I found it.", "/self_test").encode("utf-8")).hexdigest() != "7a3610a72b4915d3cd7c0932053fd81430c57b5bfb30c02b6f887bd8d4cf3b73":
        _fail("AV900_SELF_TEST_FAILED")
    try:
        _safe_utterance("safe\u202Eunsafe", "/self_test")
    except AVContractError as exc:
        if exc.code != "AV033_UTTERANCE_UNSAFE_UNICODE":
            _fail("AV900_SELF_TEST_FAILED")
    else:
        _fail("AV900_SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a candidate V7-09 AV scene contract.")
    parser.add_argument("scene", nargs="?", default="-", help="scene JSON path, or - for stdin")
    parser.add_argument("--policy", help="exact candidate surface AV policy JSON path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("scene IR v2 AV self-test passed")
            return 0
        scene = parse_json_bytes(_read(args.scene))
        policy = parse_json_bytes(_read(args.policy)) if args.policy else None
        checked = validate_scene_ir(scene, policy=policy)
        payload = canonical_json({
            "schema_version": 2,
            "status": "valid_candidate",
            "scene_ir_sha256": hashlib.sha256(canonical_json(checked)).hexdigest(),
            "policy_bound": policy is not None,
        })
    except AVContractError as exc:
        print(f"scene-ir-v2 error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
