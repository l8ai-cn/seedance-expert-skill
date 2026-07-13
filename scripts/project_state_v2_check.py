#!/usr/bin/env python3
"""Validate the bounded, surface-independent Seedance project-state-v2 contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any


SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/project-state-v2.schema.json"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_JSON_DEPTH = 48
MAX_JSON_NODES = 250_000
SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_KEYS = {
    "binding_policy",
    "tag",
    "role",
    "source_clip_tag",
    "reference_tags",
    "reference_roles",
    "prompt_visible_handle",
    "natural_language_prompt",
    "prompt",
    "prompt_render_sha256",
    "render_sha256",
    "surface",
}
HIDDEN_EXECUTION_KEYS = {
    "api_endpoint",
    "binding_authority",
    "binding_policy",
    "binding_profile",
    "compiler",
    "compiler_sha256",
    "compiler_toolchain",
    "compiler_toolchain_sha256",
    "compiler_version",
    "model_id",
    "model_version",
    "provider",
    "provider_id",
    "provider_profile",
    "prompt_render_hash",
    "prompt_render_sha256",
    "render_digest",
    "render_hash",
    "render_id",
    "render_sha256",
    "render_status",
    "renderer_sha256",
    "submission",
    "submission_id",
    "submission_status",
    "surface_id",
    "surface_policy",
}
HIDDEN_EXECUTION_KEY_PREFIXES = ("binding_", "compiler_", "execution_", "prompt_render_", "provider_", "renderer_", "submission_", "surface_")
HIDDEN_EXECUTION_KEY_COMPACT = {
    "bindingauthority", "bindingpolicy", "bindingprofile", "compilersha256", "compilertoolchainsha256",
    "executionprovider", "promptrenderdigest", "promptrenderhash", "promptrendersha256", "providerid",
    "providerprofile", "renderdigest", "renderhash", "renderid", "rendersha256", "renderstatus",
    "renderersha256", "submissionid", "submissionstatus", "surfaceid", "surfacepolicy",
}
HIDDEN_EXECUTION_KEY_TOKENS = ("提供商", "供应商", "供應商", "编译器", "編譯器", "提交状态", "提交狀態", "模型版本", "模型id", "平台接口")
PROVIDER_HANDLE = re.compile(r"@\s*(?:image|video|audio)\s*\d+|\[(?:image|video|audio)\s*\d+\]|(?:图片|圖片|图像|圖像|视频|視頻|音频|音頻)\s*\d+", re.IGNORECASE)
HIDDEN_EXECUTION_VALUE = re.compile(
    r"(?:\bprovider(?:[ _-]?(?:id|profile|policy|selected))\b|\bcompiler(?:[ _-]?(?:toolchain|version|sha256|output|submission))\b|\bsubmission(?:[ _-]?(?:status|id|endpoint|payload))\b|"
    r"\bapi[ _-]?endpoint\b|\bmodel[ _-]?(?:id|version)\b|\bseedance(?:[ _-]?\d+(?:\.\d+)*)?\b|"
    r"\bseedream\b|\bjimeng\b|\bbytedance\b|即梦|即夢|字节跳动|字節跳動|(?:提供商|供应商|供應商)(?:标识|標識|配置|id)|(?:编译器|編譯器)(?:版本|摘要|输出|輸出)|提交(?:状态|狀態|标识|標識|接口)|模型版本|模型\s*id|平台接口)",
    re.IGNORECASE,
)
ACCEPTED = {"accepted", "accepted_with_deviation"}
CONTINUATION_RELATIONS = {"seamless_continuation", "bridge_between_known_states", "repair_tail"}
OWNER_KINDS = {"character", "product", "object", "environment", "camera", "lighting", "audio", "shot"}
MOTION_DOMAINS = {"subject", "camera", "prop", "environment", "cloth_hair", "vehicle", "material", "audio"}
MOTION_PHASES = {"stationary", "starting", "continuing", "accelerating", "decelerating", "settling", "complete", "unknown"}
MOTION_CONTINUITY = {"open", "settled", "unknown"}
OBSERVABILITY = {"observed_in_video", "inferred_from_frame", "user_attested", "planned", "unknown"}
MOTION_SOURCES = {"project_plan", "accepted_video", "accepted_final_frame", "user_description", "legacy_state_description"}
COORDINATE_FRAMES = {"screen", "camera", "subject", "world", "unknown"}
SPEED_TRENDS = {"accelerating", "decelerating", "constant", "stopping", "unknown"}
COMPLETION_MODES = {
    "held_static",
    "dissipated_or_resolved",
    "completed_with_motion",
    "frame_exit",
    "cyclic_phase_boundary",
    "open_handoff",
    "incomplete",
    "unknown",
}


class StateV2Error(RuntimeError):
    def __init__(self, code: str, pointer: str = "/") -> None:
        super().__init__(code)
        self.code = code
        self.pointer = pointer


def fail(code: str, pointer: str = "/") -> None:
    raise StateV2Error(code, pointer)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _nonfinite(_value: str) -> None:
    fail("JSON_NONFINITE_NUMBER")


def _parse_int(value: str) -> int:
    if len(value) > 128:
        fail("JSON_NUMBER_OUT_OF_RANGE")
    parsed = int(value)
    if not -(2**53 - 1) <= parsed <= 2**53 - 1:
        fail("JSON_NUMBER_OUT_OF_RANGE")
    return parsed


def _parse_float(value: str) -> float:
    if len(value) > 128:
        fail("JSON_NUMBER_OUT_OF_RANGE")
    parsed = float(value)
    if not math.isfinite(parsed):
        fail("JSON_NONFINITE_NUMBER")
    return parsed


def _walk_json(value: object) -> None:
    stack: list[tuple[object, int, str]] = [(value, 0, "/")]
    nodes = 0
    while stack:
        current, depth, pointer = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            fail("JSON_TOO_MANY_NODES")
        if depth > MAX_JSON_DEPTH:
            fail("JSON_TOO_DEEP")
        if isinstance(current, dict):
            for key, child in current.items():
                _visible_text(key, pointer)
                stack.append((child, depth + 1, f"{pointer}/{_escape(key)}"))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                stack.append((child, depth + 1, f"{pointer}/{index}"))
        elif isinstance(current, str):
            _visible_text(current, pointer)


def _visible_text(value: str, pointer: str) -> None:
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            fail("UNICODE_SURROGATE_FORBIDDEN", pointer)
        if (codepoint < 0x20 and codepoint not in {0x09, 0x0A, 0x0D}) or 0x7F <= codepoint <= 0x9F:
            fail("TEXT_CONTROL_FORBIDDEN", pointer)
        if unicodedata.category(character) == "Cf":
            fail("UNICODE_FORMAT_CONTROL_FORBIDDEN", pointer)


def parse_json_bytes(raw: bytes, *, max_bytes: int = MAX_INPUT_BYTES) -> Any:
    if len(raw) > max_bytes:
        fail("JSON_TOO_LARGE")
    if raw.startswith(b"\xef\xbb\xbf"):
        fail("JSON_BOM_FORBIDDEN")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("JSON_UTF8_REQUIRED")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_nonfinite,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
    except StateV2Error:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError):
        fail("JSON_INVALID")
    _walk_json(value)
    return value


def canonical_json(value: object) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        fail("OUTPUT_NOT_CANONICAL")


def sha256_object(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _object(value: object, required: set[str], pointer: str, optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("TYPE_OBJECT_REQUIRED", pointer)
    allowed = required | (optional or set())
    if set(value) != allowed:
        fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(value: object, pointer: str, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        fail("ARRAY_BOUNDS_INVALID", pointer)
    return value


def _id(value: object, pointer: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        fail("IDENTIFIER_INVALID", pointer)
    return value


def _id_array(value: object, pointer: str, maximum: int) -> list[str]:
    values = _array(value, pointer, maximum)
    checked = [_id(item, f"{pointer}/{index}") for index, item in enumerate(values)]
    if len(checked) != len(set(checked)):
        fail("STATE002_IDENTIFIER_DUPLICATE", pointer)
    return checked


def _sha(value: object, pointer: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        fail("SHA256_INVALID", pointer)
    return value


def _text(value: object, pointer: str, maximum: int = 20_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail("TEXT_INVALID", pointer)
    normalized = unicodedata.normalize("NFKC", value).casefold()
    if PROVIDER_HANDLE.search(normalized) or HIDDEN_EXECUTION_VALUE.search(normalized):
        fail("STATE001_SURFACE_FIELD_FORBIDDEN", pointer)
    return value


def _no_legacy_keys(value: object) -> None:
    stack: list[tuple[object, str]] = [(value, "/semantic_state")]
    while stack:
        current, pointer = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_pointer = f"{pointer}/{_escape(key)}"
                if key in FORBIDDEN_KEYS:
                    fail("STATE001_SURFACE_FIELD_FORBIDDEN", child_pointer)
                stack.append((child, child_pointer))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                stack.append((child, f"{pointer}/{index}"))


def _no_hidden_execution_claims(value: object, pointer: str) -> None:
    stack: list[tuple[object, str]] = [(value, pointer)]
    while stack:
        current, current_pointer = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_pointer = f"{current_pointer}/{_escape(key)}"
                normalized_text = unicodedata.normalize("NFKC", key).casefold()
                normalized_key = re.sub(r"[^a-z0-9]+", "_", normalized_text).strip("_")
                compact_key = re.sub(r"[^a-z0-9]+", "", normalized_text)
                if normalized_key in HIDDEN_EXECUTION_KEYS or normalized_key.startswith(HIDDEN_EXECUTION_KEY_PREFIXES) or compact_key in HIDDEN_EXECUTION_KEY_COMPACT or any(token in normalized_text for token in HIDDEN_EXECUTION_KEY_TOKENS):
                    fail("STATE001_SURFACE_FIELD_FORBIDDEN", child_pointer)
                stack.append((child, child_pointer))
        elif isinstance(current, list):
            for index, child in enumerate(current):
                stack.append((child, f"{current_pointer}/{index}"))
        elif isinstance(current, str):
            normalized = unicodedata.normalize("NFKC", current).casefold()
            if PROVIDER_HANDLE.search(normalized) or HIDDEN_EXECUTION_VALUE.search(normalized):
                fail("STATE001_SURFACE_FIELD_FORBIDDEN", current_pointer)


def _unique_ids(items: list[Any], key: str, pointer: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail("TYPE_OBJECT_REQUIRED", f"{pointer}/{index}")
        item_id = _id(item.get(key), f"{pointer}/{index}/{key}")
        if item_id in result:
            fail("STATE002_IDENTIFIER_DUPLICATE", f"{pointer}/{index}/{key}")
        result[item_id] = item
    return result


def _validate_motion(value: object, basis: str, pointer: str, *, snapshot_source_kind: str | None = None) -> None:
    data = _object(value, {"basis", "vectors"}, pointer)
    if data["basis"] != basis:
        fail("STATE003_MOTION_BASIS_MISMATCH", f"{pointer}/basis")
    vectors = _array(data["vectors"], f"{pointer}/vectors", 128)
    ids: set[str] = set()
    for index, vector_value in enumerate(vectors):
        vp = f"{pointer}/vectors/{index}"
        vector = _object(
            vector_value,
            {"motion_id", "owner_kind", "owner_id", "domain", "coordinate_frame", "description", "phase", "direction", "speed", "speed_trend", "continuity", "observability", "source_kind", "confidence", "uncertainty"},
            vp,
        )
        motion_id = _id(vector["motion_id"], f"{vp}/motion_id")
        if motion_id in ids:
            fail("STATE002_IDENTIFIER_DUPLICATE", f"{vp}/motion_id")
        ids.add(motion_id)
        if not isinstance(vector["owner_kind"], str) or vector["owner_kind"] not in OWNER_KINDS:
            fail("STATE005_OWNER_KIND_INVALID", f"{vp}/owner_kind")
        _id(vector["owner_id"], f"{vp}/owner_id")
        if not all(isinstance(vector[field], str) for field in ("domain", "phase", "continuity")) or vector["domain"] not in MOTION_DOMAINS or vector["phase"] not in MOTION_PHASES or vector["continuity"] not in MOTION_CONTINUITY:
            fail("STATE006_MOTION_ENUM_INVALID", vp)
        if not all(isinstance(vector[field], str) for field in ("coordinate_frame", "speed_trend", "source_kind")) or vector["coordinate_frame"] not in COORDINATE_FRAMES or vector["speed_trend"] not in SPEED_TRENDS or vector["source_kind"] not in MOTION_SOURCES:
            fail("STATE006_MOTION_ENUM_INVALID", vp)
        _text(vector["description"], f"{vp}/description", 2_000)
        for field in ("direction", "speed"):
            if vector[field] is not None:
                _text(vector[field], f"{vp}/{field}", 500)
        if vector["uncertainty"] is not None:
            _text(vector["uncertainty"], f"{vp}/uncertainty", 2_000)
        if not isinstance(vector["observability"], str) or not isinstance(vector["confidence"], str) or vector["observability"] not in OBSERVABILITY or vector["confidence"] not in {"low", "medium", "high", "unknown"}:
            fail("STATE006_MOTION_ENUM_INVALID", vp)
        if basis == "planned" and (vector["observability"] != "planned" or vector["source_kind"] != "project_plan"):
            fail("STATE007_PLANNED_MOTION_OBSERVABILITY_INVALID", f"{vp}/observability")
        if basis == "observed" and vector["source_kind"] == "project_plan":
            fail("STATE004_MOTION_SOURCE_INVALID", f"{vp}/source_kind")
        expected_observability = {
            "accepted_video": "observed_in_video",
            "accepted_final_frame": "inferred_from_frame",
            "user_description": "user_attested",
            "legacy_state_description": "unknown",
        }.get(vector["source_kind"])
        if basis == "observed" and expected_observability != vector["observability"]:
            fail("STATE004_MOTION_SOURCE_INVALID", f"{vp}/observability")
        if basis == "observed" and vector["source_kind"] in {"accepted_video", "accepted_final_frame"} and vector["source_kind"] != snapshot_source_kind:
            fail("STATE004_MOTION_SOURCE_INVALID", f"{vp}/source_kind")
        if vector["source_kind"] == "accepted_final_frame" and (
            vector["direction"] is not None
            or vector["speed"] is not None
            or vector["observability"] == "observed_in_video"
            or vector["phase"] in {"starting", "continuing", "accelerating", "decelerating", "settling"}
            or vector["continuity"] == "open"
        ):
            fail("STATE008_FRAME_MOTION_OVERCLAIM", vp)
        if vector["continuity"] == "open" and vector["phase"] not in {"starting", "continuing", "accelerating", "decelerating", "settling"}:
            fail("STATE068_MOTION_PHASE_CONTINUITY_INVALID", vp)
        if vector["continuity"] == "settled" and vector["phase"] not in {"stationary", "complete"}:
            fail("STATE068_MOTION_PHASE_CONTINUITY_INVALID", vp)


def _validate_snapshot(value: object, basis: str, pointer: str, *, nullable: bool = False) -> dict[str, Any] | None:
    if value is None and nullable:
        return None
    data = _object(
        value,
        {"snapshot_id", "basis", "source", "binding_ids", "state_atoms", "motion_handoff", "endpoint_states", "uncertainties", "requires_confirmation", "snapshot_sha256"},
        pointer,
    )
    _id(data["snapshot_id"], f"{pointer}/snapshot_id")
    if data["basis"] != basis:
        fail("STATE009_SNAPSHOT_BASIS_MISMATCH", f"{pointer}/basis")
    source = _object(data["source"], {"kind", "take_id", "media_sha256"}, f"{pointer}/source")
    if not isinstance(source["kind"], str):
        fail("STATE010_SNAPSHOT_SOURCE_INVALID", f"{pointer}/source/kind")
    planned_source = source["kind"] == "project_plan" and source["take_id"] is None and source["media_sha256"] is None
    observed_source = source["kind"] in {"accepted_video", "accepted_final_frame", "user_description", "legacy_state_description"}
    if (basis == "planned" and not planned_source) or (basis == "observed" and not observed_source):
        fail("STATE010_SNAPSHOT_SOURCE_INVALID", f"{pointer}/source")
    if source["take_id"] is not None:
        _id(source["take_id"], f"{pointer}/source/take_id")
    _sha(source["media_sha256"], f"{pointer}/source/media_sha256", nullable=True)
    if source["kind"] in {"accepted_video", "accepted_final_frame"} and (source["take_id"] is None or source["media_sha256"] is None):
        fail("STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED", f"{pointer}/source")
    if source["kind"] in {"user_description", "legacy_state_description"} and (source["take_id"] is not None or source["media_sha256"] is not None):
        fail("STATE010_SNAPSHOT_SOURCE_INVALID", f"{pointer}/source")
    binding_ids = _id_array(data["binding_ids"], f"{pointer}/binding_ids", 64)
    atoms = _array(data["state_atoms"], f"{pointer}/state_atoms", 512)
    atom_ids: set[str] = set()
    previous = ""
    for index, atom_value in enumerate(atoms):
        ap = f"{pointer}/state_atoms/{index}"
        atom = _object(atom_value, {"atom_id", "owner_kind", "owner_id", "dimension", "value", "value_sha256", "confidence"}, ap)
        atom_id = _id(atom["atom_id"], f"{ap}/atom_id")
        if atom_id in atom_ids:
            fail("STATE002_IDENTIFIER_DUPLICATE", f"{ap}/atom_id")
        if previous and atom_id <= previous:
            fail("STATE012_STATE_ATOMS_UNSORTED", f"{ap}/atom_id")
        atom_ids.add(atom_id)
        previous = atom_id
        if not isinstance(atom["owner_kind"], str) or atom["owner_kind"] not in OWNER_KINDS:
            fail("STATE005_OWNER_KIND_INVALID", f"{ap}/owner_kind")
        _id(atom["owner_id"], f"{ap}/owner_id")
        _id(atom["dimension"], f"{ap}/dimension")
        text = _text(atom["value"], f"{ap}/value")
        if atom["value_sha256"] != sha256_text(text):
            fail("STATE013_VALUE_HASH_MISMATCH", f"{ap}/value_sha256")
        if not isinstance(atom["confidence"], str) or atom["confidence"] not in {"low", "medium", "high", "unknown"}:
            fail("STATE014_CONFIDENCE_INVALID", f"{ap}/confidence")
    _validate_motion(data["motion_handoff"], basis, f"{pointer}/motion_handoff", snapshot_source_kind=source["kind"])
    endpoint_states = _array(data["endpoint_states"], f"{pointer}/endpoint_states", 512)
    endpoint_owners: set[tuple[str, str]] = set()
    endpoint_ids: set[str] = set()
    for index, endpoint_value in enumerate(endpoint_states):
        ep = f"{pointer}/endpoint_states/{index}"
        endpoint = _object(endpoint_value, {"endpoint_id", "owner_kind", "owner_id", "completion_mode", "carry_forward", "description"}, ep)
        endpoint_id = _id(endpoint["endpoint_id"], f"{ep}/endpoint_id")
        if endpoint_id in endpoint_ids:
            fail("STATE002_IDENTIFIER_DUPLICATE", f"{ep}/endpoint_id")
        endpoint_ids.add(endpoint_id)
        if not isinstance(endpoint["owner_kind"], str) or endpoint["owner_kind"] not in OWNER_KINDS:
            fail("STATE005_OWNER_KIND_INVALID", f"{ep}/owner_kind")
        owner = (endpoint["owner_kind"], _id(endpoint["owner_id"], f"{ep}/owner_id"))
        if owner in endpoint_owners:
            fail("STATE002_IDENTIFIER_DUPLICATE", ep)
        endpoint_owners.add(owner)
        if not isinstance(endpoint["completion_mode"], str) or endpoint["completion_mode"] not in COMPLETION_MODES:
            fail("STATE015_COMPLETION_MODE_INVALID", f"{ep}/completion_mode")
        if not isinstance(endpoint["carry_forward"], bool):
            fail("TYPE_BOOLEAN_REQUIRED", f"{ep}/carry_forward")
        if endpoint["completion_mode"] == "open_handoff" and endpoint["carry_forward"] is not True:
            fail("STATE057_ENDPOINT_CARRY_FORWARD_INVALID", f"{ep}/carry_forward")
        if endpoint["carry_forward"] and endpoint["completion_mode"] not in {"open_handoff", "completed_with_motion", "frame_exit", "cyclic_phase_boundary"}:
            fail("STATE057_ENDPOINT_CARRY_FORWARD_INVALID", f"{ep}/carry_forward")
        _text(endpoint["description"], f"{ep}/description", 2_000)
    owners = {(atom["owner_kind"], atom["owner_id"]) for atom in atoms}
    owners.update(
        (vector["owner_kind"], vector["owner_id"])
        for vector in data["motion_handoff"]["vectors"]
    )
    is_start = "start_snapshot" in pointer
    if is_start and source["kind"] == "accepted_final_frame":
        fail("STATE008_FRAME_MOTION_OVERCLAIM", f"{pointer}/source")
    if is_start and endpoint_states:
        fail("STATE058_START_ENDPOINT_FORBIDDEN", f"{pointer}/endpoint_states")
    if not is_start and endpoint_owners != owners:
        fail("STATE059_ENDPOINT_OWNER_COVERAGE_INCOMPLETE", f"{pointer}/endpoint_states")
    endpoint_by_owner = {
        (item["owner_kind"], item["owner_id"]): item for item in endpoint_states
    }
    if source["kind"] == "accepted_final_frame" and any(
        endpoint["completion_mode"] != "held_static" for endpoint in endpoint_states
    ):
        fail("STATE008_FRAME_MOTION_OVERCLAIM", f"{pointer}/endpoint_states")
    open_vector_owners = {
        (vector["owner_kind"], vector["owner_id"])
        for vector in data["motion_handoff"]["vectors"]
        if vector["continuity"] == "open"
    }
    for owner, endpoint in endpoint_by_owner.items():
        if endpoint["carry_forward"] and owner not in open_vector_owners:
            fail("STATE060_MOTION_HANDOFF_ENDPOINT_MISMATCH", f"{pointer}/endpoint_states")
        if endpoint["completion_mode"] == "completed_with_motion" and not any(
            (vector["owner_kind"], vector["owner_id"]) == owner
            and vector["phase"] in {"starting", "continuing", "accelerating", "decelerating", "settling"}
            for vector in data["motion_handoff"]["vectors"]
        ):
            fail("STATE079_COMPLETED_MOTION_EVIDENCE_REQUIRED", f"{pointer}/endpoint_states")
    for vector in data["motion_handoff"]["vectors"]:
        endpoint = endpoint_by_owner.get((vector["owner_kind"], vector["owner_id"]))
        if endpoint is not None and vector["continuity"] == "open" and endpoint["completion_mode"] in {"held_static", "dissipated_or_resolved"}:
            fail("STATE060_MOTION_HANDOFF_ENDPOINT_MISMATCH", f"{pointer}/endpoint_states")
    if not isinstance(data["requires_confirmation"], bool):
        fail("TYPE_BOOLEAN_REQUIRED", f"{pointer}/requires_confirmation")
    if basis == "observed" and source["kind"] in {"user_description", "legacy_state_description"} and data["requires_confirmation"] is not True:
        fail("STATE010_SNAPSHOT_SOURCE_INVALID", f"{pointer}/requires_confirmation")
    for index, uncertainty in enumerate(_array(data["uncertainties"], f"{pointer}/uncertainties", 128)):
        _text(uncertainty, f"{pointer}/uncertainties/{index}", 2_000)
    hash_input = {key: child for key, child in data.items() if key != "snapshot_sha256"}
    if data["snapshot_sha256"] != sha256_object(hash_input):
        fail("STATE016_SNAPSHOT_HASH_MISMATCH", f"{pointer}/snapshot_sha256")
    return data


def _atoms(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {atom["atom_id"]: atom for atom in snapshot["state_atoms"]}


def _validate_continuity_rules(rules: object, pointer: str) -> dict[str, dict[str, Any]]:
    rules = _array(rules, pointer, 512)
    rule_by_atom: dict[str, dict[str, Any]] = {}
    rule_ids: set[str] = set()
    for index, rule_value in enumerate(rules):
        rp = f"{pointer}/{index}"
        rule = _object(rule_value, {"rule_id", "atom_id", "policy", "from_value_sha256", "to_value_sha256", "scope", "reason"}, rp)
        rule_id = _id(rule["rule_id"], f"{rp}/rule_id")
        atom_id = _id(rule["atom_id"], f"{rp}/atom_id")
        if rule_id in rule_ids or atom_id in rule_by_atom:
            fail("STATE002_IDENTIFIER_DUPLICATE", rp)
        rule_ids.add(rule_id)
        rule_by_atom[atom_id] = rule
        if rule["policy"] not in {"locked", "allowed_change"} or rule["scope"] not in {"next_clip", "scene", "project"}:
            fail("STATE018_CONTINUITY_RULE_INVALID", rp)
        _sha(rule["from_value_sha256"], f"{rp}/from_value_sha256")
        _sha(rule["to_value_sha256"], f"{rp}/to_value_sha256")
        _text(rule["reason"], f"{rp}/reason", 2_000)
    return rule_by_atom


def _validate_continuity(parent: dict[str, Any], child: dict[str, Any], pointer: str) -> None:
    parent_snapshot = parent["observed_end_snapshot"]
    child_snapshot = child["planned_start_snapshot"]
    if parent_snapshot is None:
        fail("STATE017_PARENT_OBSERVED_ENDPOINT_REQUIRED", pointer)
    parent_atoms = _atoms(parent_snapshot)
    child_atoms = _atoms(child_snapshot)
    if not set(parent_snapshot["binding_ids"]).issubset(child_snapshot["binding_ids"]):
        fail("STATE076_REFERENCE_BINDING_DROPPED", f"{pointer}/planned_start_snapshot/binding_ids")
    required_atom_ids = set(parent_atoms) | set(child_atoms)
    rule_by_atom = _validate_continuity_rules(child["continuity_rules"], f"{pointer}/continuity_rules")
    if set(rule_by_atom) != required_atom_ids:
        fail("STATE019_CONTINUITY_RULE_COVERAGE_INCOMPLETE", f"{pointer}/continuity_rules")
    for atom_id in sorted(required_atom_ids):
        if atom_id not in parent_atoms or atom_id not in child_atoms:
            fail("STATE020_CONTINUITY_ATOM_MISSING", f"{pointer}/continuity_rules")
        before = parent_atoms[atom_id]["value_sha256"]
        after = child_atoms[atom_id]["value_sha256"]
        for field in ("owner_kind", "owner_id", "dimension"):
            if parent_atoms[atom_id][field] != child_atoms[atom_id][field]:
                fail("STATE070_CONTINUITY_ATOM_IDENTITY_CHANGED", f"{pointer}/continuity_rules")
        rule = rule_by_atom[atom_id]
        if rule["from_value_sha256"] != before or rule["to_value_sha256"] != after:
            fail("STATE021_CONTINUITY_HASH_MISMATCH", f"{pointer}/continuity_rules")
        if rule["policy"] == "locked" and before != after:
            fail("STATE022_LOCKED_ATOM_CHANGED", f"{pointer}/continuity_rules")


def _validate_motion_carry(parent: dict[str, Any], child: dict[str, Any], pointer: str) -> None:
    parent_snapshot = parent["observed_end_snapshot"]
    if parent_snapshot is None:
        fail("STATE017_PARENT_OBSERVED_ENDPOINT_REQUIRED", pointer)
    carry_owners = {
        (endpoint["owner_kind"], endpoint["owner_id"])
        for endpoint in parent_snapshot["endpoint_states"]
        if endpoint["carry_forward"]
    }
    parent_vectors = [
        vector for vector in parent_snapshot["motion_handoff"]["vectors"]
        if vector["continuity"] == "open" and (vector["owner_kind"], vector["owner_id"]) in carry_owners
    ]
    child_vectors = child["planned_start_snapshot"]["motion_handoff"]["vectors"]
    remaining: dict[tuple[object, ...], int] = {}
    for child_vector in child_vectors:
        if child_vector["continuity"] != "open":
            continue
        signature = tuple(
            child_vector[field]
            for field in ("owner_kind", "owner_id", "domain", "coordinate_frame", "direction", "speed_trend")
        )
        remaining[signature] = remaining.get(signature, 0) + 1
    for parent_vector in parent_vectors:
        signature = tuple(
            parent_vector[field]
            for field in ("owner_kind", "owner_id", "domain", "coordinate_frame", "direction", "speed_trend")
        )
        if remaining.get(signature, 0) < 1:
            fail("STATE071_CARRY_FORWARD_DROPPED", f"{pointer}/planned_start_snapshot/motion_handoff")
        remaining[signature] -= 1


def validate_project_state(value: object) -> dict[str, Any]:
    data = _object(
        value,
        {"$schema", "schema_version", "project_id", "project_mode", "state_revision", "canon_revision", "semantic_state", "semantic_state_sha256", "migration_provenance", "updated_at"},
        "/",
    )
    if data["$schema"] != SCHEMA_URI or data["schema_version"] != 2 or isinstance(data["schema_version"], bool):
        fail("STATE023_CONTRACT_INVALID", "/schema_version")
    project_id = _id(data["project_id"], "/project_id")
    if not isinstance(data["project_mode"], str) or data["project_mode"] not in {"standalone_clip", "sequence_project"}:
        fail("STATE024_PROJECT_MODE_INVALID", "/project_mode")
    for field in ("state_revision", "canon_revision"):
        if not isinstance(data[field], int) or isinstance(data[field], bool) or data[field] < 1:
            fail("STATE025_REVISION_INVALID", f"/{field}")
    semantic = _object(
        data["semantic_state"],
        {"clip_budget_sec", "prompt_budget", "story", "world_bible", "reanchor_policy", "timing_policy", "reference_assets", "scenes", "beats", "clips", "current_clip_id"},
        "/semantic_state",
    )
    _no_legacy_keys(semantic)
    _id(semantic["current_clip_id"], "/semantic_state/current_clip_id")
    clip_budget = semantic["clip_budget_sec"]
    if clip_budget is not None and (not isinstance(clip_budget, (int, float)) or isinstance(clip_budget, bool) or not math.isfinite(clip_budget) or clip_budget <= 0):
        fail("STATE072_BUDGET_INVALID", "/semantic_state/clip_budget_sec")
    prompt_budget = semantic["prompt_budget"]
    if prompt_budget is not None and (not isinstance(prompt_budget, int) or isinstance(prompt_budget, bool) or prompt_budget < 1):
        fail("STATE072_BUDGET_INVALID", "/semantic_state/prompt_budget")
    if not isinstance(semantic["story"], dict) or not isinstance(semantic["world_bible"], dict):
        fail("STATE073_SEMANTIC_OBJECT_INVALID", "/semantic_state")
    _no_hidden_execution_claims(semantic["story"], "/semantic_state/story")
    _no_hidden_execution_claims(semantic["world_bible"], "/semantic_state/world_bible")
    reanchor = _object(semantic["reanchor_policy"], {"status", "trigger_extension_depth", "reason"}, "/semantic_state/reanchor_policy")
    if reanchor["status"] == "not_selected":
        if reanchor["trigger_extension_depth"] is not None or reanchor["reason"] is not None:
            fail("STATE064_REANCHOR_POLICY_INVALID", "/semantic_state/reanchor_policy")
    elif reanchor["status"] == "selected":
        if not isinstance(reanchor["trigger_extension_depth"], int) or isinstance(reanchor["trigger_extension_depth"], bool) or reanchor["trigger_extension_depth"] < 1:
            fail("STATE064_REANCHOR_POLICY_INVALID", "/semantic_state/reanchor_policy/trigger_extension_depth")
        _text(reanchor["reason"], "/semantic_state/reanchor_policy/reason", 2_000)
    else:
        fail("STATE064_REANCHOR_POLICY_INVALID", "/semantic_state/reanchor_policy/status")
    timing = _object(semantic["timing_policy"], {"mode", "status", "evidence_claim_ids", "evidence_expires_at", "block_reason"}, "/semantic_state/timing_policy")
    if not isinstance(timing["mode"], str) or not isinstance(timing["status"], str) or timing["mode"] not in {"ordered_phases", "relative_beats", "surface_exact_ranges"} or timing["status"] not in {"selected", "blocked"}:
        fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy")
    claims = _array(timing["evidence_claim_ids"], "/semantic_state/timing_policy/evidence_claim_ids", 32)
    if any(not isinstance(item, str) or re.fullmatch(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$", item) is None for item in claims):
        fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy/evidence_claim_ids")
    if len(claims) != len(set(claims)):
        fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy/evidence_claim_ids")
    if timing["mode"] == "surface_exact_ranges":
        if timing["status"] != "blocked":
            fail("STATE066_EXACT_TIMING_EVIDENCE_REQUIRED", "/semantic_state/timing_policy")
        if not isinstance(timing["block_reason"], str) or not timing["block_reason"].strip():
            fail("STATE067_EXACT_TIMING_BLOCK_REASON_REQUIRED", "/semantic_state/timing_policy/block_reason")
        if len(timing["block_reason"]) > 2_000:
            fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy/block_reason")
        if claims or timing["evidence_expires_at"] is not None:
            fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy")
    elif timing["status"] != "selected" or claims or timing["evidence_expires_at"] is not None or timing["block_reason"] is not None:
        fail("STATE065_TIMING_POLICY_INVALID", "/semantic_state/timing_policy")
    state_hash_input = {"project_id": project_id, "state_revision": data["state_revision"], "canon_revision": data["canon_revision"], "semantic_state": semantic}
    if data["semantic_state_sha256"] != sha256_object(state_hash_input):
        fail("STATE026_SEMANTIC_STATE_HASH_MISMATCH", "/semantic_state_sha256")
    references = _array(semantic["reference_assets"], "/semantic_state/reference_assets", 64)
    reference_by_id = _unique_ids(references, "binding_id", "/semantic_state/reference_assets")
    for index, reference in enumerate(references):
        pointer = f"/semantic_state/reference_assets/{index}"
        _object(reference, {"binding_id", "media_type", "source_kind", "source_take_id", "media_sha256", "description", "status", "authority_status"}, pointer)
        if not isinstance(reference["media_type"], str) or not isinstance(reference["source_kind"], str) or reference["media_type"] not in {"image", "video", "audio"} or reference["source_kind"] not in {"user_asset", "accepted_take", "extracted_frame"}:
            fail("STATE027_REFERENCE_CONTRACT_INVALID", pointer)
        if reference["source_take_id"] is not None:
            _id(reference["source_take_id"], f"{pointer}/source_take_id")
        _sha(reference["media_sha256"], f"{pointer}/media_sha256", nullable=True)
        _text(reference["description"], f"{pointer}/description", 2_000)
        if not isinstance(reference["status"], str) or reference["status"] not in {"available", "pending", "retired"}:
            fail("STATE027_REFERENCE_CONTRACT_INVALID", pointer)
        if reference["authority_status"] != "unresolved":
            fail("STATE061_BINDING_POLICY_INVALID", f"{pointer}/authority_status")
        if reference["source_kind"] in {"accepted_take", "extracted_frame"} and (reference["source_take_id"] is None or reference["media_sha256"] is None):
            fail("STATE069_REFERENCE_PROVENANCE_REQUIRED", pointer)
        if reference["source_kind"] == "user_asset" and reference["source_take_id"] is not None:
            fail("STATE069_REFERENCE_PROVENANCE_REQUIRED", pointer)
        if reference["status"] == "available" and reference["media_sha256"] is None:
            fail("STATE069_REFERENCE_PROVENANCE_REQUIRED", f"{pointer}/status")
    scenes = _array(semantic["scenes"], "/semantic_state/scenes", 256)
    scene_by_id = _unique_ids(scenes, "scene_id", "/semantic_state/scenes")
    scene_indexes: set[int] = set()
    for index, scene in enumerate(scenes):
        pointer = f"/semantic_state/scenes/{index}"
        _object(scene, {"scene_id", "scene_index", "anchor_binding_ids", "assigned_clip_ids", "status"}, pointer)
        scene_index = scene["scene_index"]
        if not isinstance(scene_index, int) or isinstance(scene_index, bool) or scene_index < 1 or scene_index in scene_indexes:
            fail("STATE028_SCENE_INDEX_INVALID", f"{pointer}/scene_index")
        scene_indexes.add(scene_index)
        if not isinstance(scene["status"], str) or scene["status"] not in {"planned", "current", "completed", "omitted", "replaced"}:
            fail("STATE029_SCENE_STATUS_INVALID", f"{pointer}/status")
        for field in ("anchor_binding_ids", "assigned_clip_ids"):
            _id_array(scene[field], f"{pointer}/{field}", 64 if field == "anchor_binding_ids" else 1024)
        if any(item not in reference_by_id or reference_by_id[item]["status"] == "retired" for item in scene["anchor_binding_ids"]):
            fail("STATE030_REFERENCE_UNKNOWN", f"{pointer}/anchor_binding_ids")
    beats = _array(semantic["beats"], "/semantic_state/beats", 4096)
    beat_by_id = _unique_ids(beats, "beat_id", "/semantic_state/beats")
    for index, beat in enumerate(beats):
        pointer = f"/semantic_state/beats/{index}"
        _object(beat, {"beat_id", "description", "status", "assigned_clip_id", "dependencies"}, pointer)
        _text(beat["description"], f"{pointer}/description", 2_000)
        if not isinstance(beat["status"], str) or beat["status"] not in {"planned", "current", "completed", "omitted", "replaced"}:
            fail("STATE031_BEAT_STATUS_INVALID", f"{pointer}/status")
        if beat["assigned_clip_id"] is not None:
            _id(beat["assigned_clip_id"], f"{pointer}/assigned_clip_id")
        dependencies = _id_array(beat["dependencies"], f"{pointer}/dependencies", 256)
        for dep_index, dependency in enumerate(dependencies):
            if dependency == beat["beat_id"]:
                fail("STATE032_BEAT_CYCLE", f"{pointer}/dependencies/{dep_index}")
    clips = _array(semantic["clips"], "/semantic_state/clips", 1024)
    clip_by_id = _unique_ids(clips, "clip_id", "/semantic_state/clips")
    if semantic["current_clip_id"] not in clip_by_id:
        fail("STATE054_CURRENT_CLIP_UNKNOWN", "/semantic_state/current_clip_id")
    clip_indexes: set[int] = set()
    for index, clip in enumerate(clips):
        pointer = f"/semantic_state/clips/{index}"
        _object(
            clip,
            {"clip_id", "parent_clip_id", "scene_id", "sequence_index", "status", "accepted_deviation_ids", "sequence_relation", "felt_intent", "already_happened", "this_clip_only", "reserved_for_later", "planned_start_snapshot", "planned_end_snapshot", "observed_start_snapshot", "observed_end_snapshot", "continuity_rules", "planning_link", "execution_readiness", "compile_required", "extension_depth"},
            pointer,
        )
        if clip["parent_clip_id"] is not None:
            _id(clip["parent_clip_id"], f"{pointer}/parent_clip_id")
        clip_scene_id = _id(clip["scene_id"], f"{pointer}/scene_id")
        if clip_scene_id not in scene_by_id:
            fail("STATE033_SCENE_UNKNOWN", f"{pointer}/scene_id")
        sequence_index = clip["sequence_index"]
        if not isinstance(sequence_index, int) or isinstance(sequence_index, bool) or sequence_index < 1 or sequence_index in clip_indexes:
            fail("STATE034_CLIP_SEQUENCE_INVALID", f"{pointer}/sequence_index")
        clip_indexes.add(sequence_index)
        if not isinstance(clip["status"], str) or clip["status"] not in {"planned", "generated", "reviewed", "accepted", "accepted_with_deviation", "repair", "rejected"}:
            fail("STATE035_CLIP_STATUS_INVALID", f"{pointer}/status")
        accepted_deviation_ids = _id_array(clip["accepted_deviation_ids"], f"{pointer}/accepted_deviation_ids", 512)
        if (clip["status"] == "accepted_with_deviation" and not accepted_deviation_ids) or (clip["status"] != "accepted_with_deviation" and accepted_deviation_ids):
            fail("STATE080_ACCEPTED_DEVIATION_PROJECTION_INVALID", f"{pointer}/accepted_deviation_ids")
        if not isinstance(clip["sequence_relation"], str) or clip["sequence_relation"] not in {"standalone", "sequence_first_clip", "seamless_continuation", "intentional_next_shot", "bridge_between_known_states", "repair_tail", "reanchor_after_drift"}:
            fail("STATE036_SEQUENCE_RELATION_INVALID", f"{pointer}/sequence_relation")
        _text(clip["felt_intent"], f"{pointer}/felt_intent", 2_000)
        for field in ("already_happened", "this_clip_only", "reserved_for_later"):
            values = _id_array(clip[field], f"{pointer}/{field}", 4096)
            for item_index, item in enumerate(values):
                if item not in beat_by_id:
                    fail("STATE037_BEAT_UNKNOWN", f"{pointer}/{field}/{item_index}")
        if set(clip["already_happened"]) & set(clip["this_clip_only"]) or set(clip["this_clip_only"]) & set(clip["reserved_for_later"]):
            fail("STATE038_BEAT_SCOPE_OVERLAP", pointer)
        if set(clip["already_happened"]) & set(clip["reserved_for_later"]):
            fail("STATE038_BEAT_SCOPE_OVERLAP", pointer)
        _validate_snapshot(clip["planned_start_snapshot"], "planned", f"{pointer}/planned_start_snapshot")
        _validate_snapshot(clip["planned_end_snapshot"], "planned", f"{pointer}/planned_end_snapshot")
        _validate_snapshot(clip["observed_start_snapshot"], "observed", f"{pointer}/observed_start_snapshot", nullable=True)
        observed_end = _validate_snapshot(clip["observed_end_snapshot"], "observed", f"{pointer}/observed_end_snapshot", nullable=True)
        if clip["status"] in ACCEPTED and observed_end is None:
            fail("STATE039_ACCEPTED_ENDPOINT_REQUIRED", f"{pointer}/observed_end_snapshot")
        if clip["status"] == "rejected" and observed_end is not None:
            fail("STATE040_REJECTED_CANON_FORBIDDEN", f"{pointer}/observed_end_snapshot")
        if clip["status"] in ACCEPTED and observed_end is not None:
            if not observed_end["endpoint_states"]:
                fail("STATE074_ACCEPTED_ENDPOINT_COVERAGE_REQUIRED", f"{pointer}/observed_end_snapshot/endpoint_states")
            modes = {item["completion_mode"] for item in observed_end["endpoint_states"]}
            if "unknown" in modes or "incomplete" in modes:
                fail("STATE041_ACCEPTED_COMPLETION_UNKNOWN", f"{pointer}/observed_end_snapshot/endpoint_states")
            if observed_end["source"]["kind"] not in {"accepted_video", "accepted_final_frame"} or observed_end["requires_confirmation"] is not False:
                fail("STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED", f"{pointer}/observed_end_snapshot/source")
            if observed_end["source"]["kind"] == "accepted_final_frame" and any(item["completion_mode"] != "held_static" for item in observed_end["endpoint_states"]):
                fail("STATE008_FRAME_MOTION_OVERCLAIM", f"{pointer}/observed_end_snapshot/endpoint_states")
            observed_start = clip["observed_start_snapshot"]
            if observed_start is not None:
                if observed_start["source"]["kind"] != "accepted_video" or observed_start["requires_confirmation"] is not False:
                    fail("STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED", f"{pointer}/observed_start_snapshot/source")
                if observed_start["source"] != observed_end["source"]:
                    fail("STATE011_ACCEPTED_MEDIA_PROVENANCE_REQUIRED", f"{pointer}/observed_start_snapshot/source")
        _validate_continuity_rules(clip["continuity_rules"], f"{pointer}/continuity_rules")
        for snapshot_field in ("planned_start_snapshot", "planned_end_snapshot", "observed_start_snapshot", "observed_end_snapshot"):
            snapshot = clip[snapshot_field]
            if snapshot is None:
                continue
            for binding_index, binding_id in enumerate(snapshot["binding_ids"]):
                reference = reference_by_id.get(binding_id)
                if reference is None or reference["status"] == "retired":
                    fail("STATE030_REFERENCE_UNKNOWN", f"{pointer}/{snapshot_field}/binding_ids/{binding_index}")
        planning = _object(clip["planning_link"], {"status", "binding_ids", "resolved_binding_proofs", "reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256"}, f"{pointer}/planning_link")
        planning_binding_ids = _id_array(planning["binding_ids"], f"{pointer}/planning_link/binding_ids", 64)
        for binding_index, binding_id in enumerate(planning_binding_ids):
            if binding_id not in reference_by_id or reference_by_id[binding_id]["status"] == "retired":
                fail("STATE030_REFERENCE_UNKNOWN", f"{pointer}/planning_link/binding_ids/{binding_index}")
        if set(planning_binding_ids) != set(clip["planned_start_snapshot"]["binding_ids"]):
            fail("STATE042_PLANNING_LINK_PARTIAL", f"{pointer}/planning_link/binding_ids")
        proofs = _array(planning["resolved_binding_proofs"], f"{pointer}/planning_link/resolved_binding_proofs", 64)
        proof_by_binding: dict[str, str] = {}
        for proof_index, proof_value in enumerate(proofs):
            proof_pointer = f"{pointer}/planning_link/resolved_binding_proofs/{proof_index}"
            proof = _object(proof_value, {"binding_id", "media_sha256"}, proof_pointer)
            proof_binding_id = _id(proof["binding_id"], f"{proof_pointer}/binding_id")
            _sha(proof["media_sha256"], f"{proof_pointer}/media_sha256")
            if proof_binding_id in proof_by_binding:
                fail("STATE042_PLANNING_LINK_PARTIAL", f"{proof_pointer}/binding_id")
            proof_by_binding[proof_binding_id] = proof["media_sha256"]
        hashes = [planning[field] for field in ("reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256")]
        if planning["status"] == "planning_required":
            if any(item is not None for item in hashes) or proofs:
                fail("STATE042_PLANNING_LINK_PARTIAL", f"{pointer}/planning_link")
        elif planning["status"] == "planned":
            for field in ("reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256"):
                _sha(planning[field], f"{pointer}/planning_link/{field}")
            if set(proof_by_binding) != set(planning_binding_ids):
                fail("STATE042_PLANNING_LINK_PARTIAL", f"{pointer}/planning_link/resolved_binding_proofs")
            for binding_id in planning_binding_ids:
                reference = reference_by_id[binding_id]
                if reference["status"] != "available" or reference["media_sha256"] is None or proof_by_binding[binding_id] != reference["media_sha256"]:
                    fail("STATE083_PLANNED_REFERENCE_UNRESOLVED", f"{pointer}/planning_link/resolved_binding_proofs")
            if any(reference["status"] != "available" or reference["media_sha256"] is None for reference in references):
                fail("STATE083_PLANNED_REFERENCE_UNRESOLVED", f"{pointer}/planning_link")
        else:
            fail("STATE042_PLANNING_LINK_PARTIAL", f"{pointer}/planning_link/status")
        if not isinstance(clip["execution_readiness"], str) or clip["execution_readiness"] not in {"migration_review", "planning_required", "compile_required", "blocked"}:
            fail("STATE043_EXECUTION_READINESS_INVALID", f"{pointer}/execution_readiness")
        if planning["status"] == "planning_required" and clip["execution_readiness"] == "compile_required":
            fail("STATE043_EXECUTION_READINESS_INVALID", f"{pointer}/execution_readiness")
        if planning["status"] == "planned" and clip["execution_readiness"] == "planning_required":
            fail("STATE043_EXECUTION_READINESS_INVALID", f"{pointer}/execution_readiness")
        if clip["compile_required"] is not True:
            fail("STATE063_COMPILE_REQUIRED", f"{pointer}/compile_required")
        if not isinstance(clip["extension_depth"], int) or isinstance(clip["extension_depth"], bool) or clip["extension_depth"] < 0:
            fail("STATE044_EXTENSION_DEPTH_INVALID", f"{pointer}/extension_depth")
    take_identities: dict[str, tuple[str, str | None]] = {}

    def register_take(take_id: str, media_sha256: str, source_kind: str | None, pointer: str) -> None:
        existing = take_identities.get(take_id)
        if existing is not None and (existing[0] != media_sha256 or existing[1] is not None and source_kind is not None and existing[1] != source_kind):
            fail("STATE078_TAKE_IDENTITY_CONFLICT", pointer)
        take_identities[take_id] = (media_sha256, source_kind if source_kind is not None else existing[1] if existing is not None else None)

    for index, reference in enumerate(references):
        if reference["source_kind"] == "accepted_take":
            register_take(reference["source_take_id"], reference["media_sha256"], None, f"/semantic_state/reference_assets/{index}")
    for clip_index, clip in enumerate(clips):
        for snapshot_field in ("observed_start_snapshot", "observed_end_snapshot"):
            snapshot = clip[snapshot_field]
            if snapshot is None or snapshot["source"]["kind"] not in {"accepted_video", "accepted_final_frame"}:
                continue
            source = snapshot["source"]
            register_take(source["take_id"], source["media_sha256"], source["kind"], f"/semantic_state/clips/{clip_index}/{snapshot_field}/source")
    for clip_id, clip in clip_by_id.items():
        parent_id = clip["parent_clip_id"]
        pointer = f"/semantic_state/clips/{clips.index(clip)}"
        if parent_id is None:
            if clip["sequence_relation"] not in {"standalone", "sequence_first_clip"}:
                fail("STATE045_PARENT_RELATION_INVALID", f"{pointer}/sequence_relation")
            continue
        if parent_id == clip_id or parent_id not in clip_by_id:
            fail("STATE046_PARENT_INVALID", f"{pointer}/parent_clip_id")
        if clip["sequence_relation"] in {"standalone", "sequence_first_clip"}:
            fail("STATE045_PARENT_RELATION_INVALID", f"{pointer}/sequence_relation")
        parent = clip_by_id[parent_id]
        if parent["sequence_index"] >= clip["sequence_index"]:
            fail("STATE047_PARENT_ORDER_INVALID", f"{pointer}/parent_clip_id")
        if clip["sequence_relation"] in CONTINUATION_RELATIONS:
            if parent["scene_id"] != clip["scene_id"]:
                fail("STATE048_CROSS_SCENE_CONTINUATION", f"{pointer}/scene_id")
            if parent["status"] not in ACCEPTED:
                fail("STATE049_PARENT_NOT_ACCEPTED", f"{pointer}/parent_clip_id")
            parent_source = parent["observed_end_snapshot"]["source"]
            if parent_source["media_sha256"] is None:
                fail("STATE050_ACCEPTED_MEDIA_DIGEST_REQUIRED", f"{pointer}/parent_clip_id")
            if clip["extension_depth"] != parent["extension_depth"] + 1:
                fail("STATE075_EXTENSION_DEPTH_DISCONTINUITY", f"{pointer}/extension_depth")
            _validate_continuity(parent, clip, pointer)
            _validate_motion_carry(parent, clip, pointer)
        if clip["sequence_relation"] == "reanchor_after_drift":
            if parent["status"] not in ACCEPTED or parent["observed_end_snapshot"] is None:
                fail("STATE049_PARENT_NOT_ACCEPTED", f"{pointer}/parent_clip_id")
            parent_source = parent["observed_end_snapshot"]["source"]
            if parent_source["kind"] not in {"accepted_video", "accepted_final_frame"} or parent_source["media_sha256"] is None or parent_source["take_id"] is None:
                fail("STATE050_ACCEPTED_MEDIA_DIGEST_REQUIRED", f"{pointer}/parent_clip_id")
        if clip["sequence_relation"] in {"intentional_next_shot", "reanchor_after_drift"} and clip["extension_depth"] != 0:
            fail("STATE051_REANCHOR_DEPTH_INVALID", f"{pointer}/extension_depth")
    roots = [clip for clip in clips if clip["parent_clip_id"] is None]
    if data["project_mode"] == "standalone_clip":
        if len(clips) != 1 or len(roots) != 1 or roots[0]["sequence_relation"] != "standalone":
            fail("STATE024_PROJECT_MODE_INVALID", "/project_mode")
    elif len(roots) != 1 or roots[0]["sequence_relation"] != "sequence_first_clip" or any(clip["sequence_relation"] == "standalone" for clip in clips):
        fail("STATE024_PROJECT_MODE_INVALID", "/project_mode")
    # Explicit graph walk catches cycles even if sequence-order validation changes later.
    for clip_id in clip_by_id:
        seen: set[str] = set()
        cursor: str | None = clip_id
        while cursor is not None:
            if cursor in seen:
                fail("STATE052_CLIP_CYCLE", "/semantic_state/clips")
            seen.add(cursor)
            cursor = clip_by_id.get(cursor, {}).get("parent_clip_id")
    indegree = {beat_id: 0 for beat_id in beat_by_id}
    dependents = {beat_id: [] for beat_id in beat_by_id}
    for beat_id, beat in beat_by_id.items():
        for dependency in beat["dependencies"]:
            if dependency not in beat_by_id:
                fail("STATE037_BEAT_UNKNOWN", "/semantic_state/beats")
            indegree[beat_id] += 1
            dependents[dependency].append(beat_id)
    ready = [beat_id for beat_id, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ready:
        beat_id = ready.pop()
        visited_count += 1
        for dependent in dependents[beat_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if visited_count != len(beat_by_id):
        fail("STATE032_BEAT_CYCLE", "/semantic_state/beats")
    owners: dict[str, str] = {}
    for scene_id, scene in scene_by_id.items():
        for clip_id in scene["assigned_clip_ids"]:
            if clip_id not in clip_by_id or clip_id in owners:
                fail("STATE053_SCENE_ASSIGNMENT_INVALID", "/semantic_state/scenes")
            owners[clip_id] = scene_id
    for clip_id, clip in clip_by_id.items():
        if owners.get(clip_id) != clip["scene_id"]:
            fail("STATE053_SCENE_ASSIGNMENT_INVALID", "/semantic_state/scenes")
    for beat in beats:
        if beat["assigned_clip_id"] is not None and beat["assigned_clip_id"] not in clip_by_id:
            fail("STATE037_BEAT_UNKNOWN", "/semantic_state/beats")
    clip_index_by_id = {clip_id: clip["sequence_index"] for clip_id, clip in clip_by_id.items()}
    current_sequence_index = clip_index_by_id[semantic["current_clip_id"]]
    for beat in beats:
        assigned_clip_id = beat["assigned_clip_id"]
        if beat["status"] == "current" and assigned_clip_id != semantic["current_clip_id"]:
            fail("STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH", "/semantic_state/beats")
        if beat["status"] == "completed" and (assigned_clip_id is None or clip_index_by_id[assigned_clip_id] > current_sequence_index):
            fail("STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH", "/semantic_state/beats")
        if beat["status"] == "planned" and assigned_clip_id is not None and clip_index_by_id[assigned_clip_id] < current_sequence_index:
            fail("STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH", "/semantic_state/beats")
        for dependency_id in beat["dependencies"]:
            dependency = beat_by_id[dependency_id]
            if beat["status"] in {"current", "completed"} and dependency["status"] not in {"completed", "omitted", "replaced"}:
                fail("STATE081_BEAT_DEPENDENCY_LIFECYCLE_INVALID", "/semantic_state/beats")
            if assigned_clip_id is not None and dependency["assigned_clip_id"] is not None and clip_index_by_id[dependency["assigned_clip_id"]] > clip_index_by_id[assigned_clip_id]:
                fail("STATE081_BEAT_DEPENDENCY_LIFECYCLE_INVALID", "/semantic_state/beats")
        for clip in clips:
            memberships = {
                "already_happened": beat["beat_id"] in clip["already_happened"],
                "this_clip_only": beat["beat_id"] in clip["this_clip_only"],
                "reserved_for_later": beat["beat_id"] in clip["reserved_for_later"],
            }
            expected = None
            if assigned_clip_id is not None:
                assigned_index = clip_index_by_id[assigned_clip_id]
                if clip["sequence_index"] < assigned_index:
                    expected = "reserved_for_later"
                elif clip["sequence_index"] == assigned_index:
                    expected = "this_clip_only"
                else:
                    expected = "already_happened"
            if any(value != (name == expected) for name, value in memberships.items()):
                fail("STATE077_BEAT_ASSIGNMENT_SCOPE_MISMATCH", f"/semantic_state/clips/{clips.index(clip)}")
    current_scene_id = clip_by_id[semantic["current_clip_id"]]["scene_id"]
    current_scene_ids = [scene_id for scene_id, scene in scene_by_id.items() if scene["status"] == "current"]
    if current_scene_ids != [current_scene_id]:
        fail("STATE082_SCENE_LIFECYCLE_INVALID", "/semantic_state/scenes")
    for scene in scenes:
        if scene["status"] not in {"completed", "omitted", "replaced"}:
            continue
        assigned = set(scene["assigned_clip_ids"])
        if any(clip_by_id[clip_id]["status"] not in ACCEPTED | {"rejected"} for clip_id in assigned):
            fail("STATE082_SCENE_LIFECYCLE_INVALID", "/semantic_state/scenes")
        if any(beat["assigned_clip_id"] in assigned and beat["status"] in {"planned", "current"} for beat in beats):
            fail("STATE082_SCENE_LIFECYCLE_INVALID", "/semantic_state/scenes")
    provenance = _object(data["migration_provenance"], {"status", "source_schema_version", "source_raw_sha256", "source_canonical_sha256", "migration_map_sha256", "migration_tool_sha256"}, "/migration_provenance")
    if provenance["status"] == "native":
        if any(provenance[field] is not None for field in ("source_schema_version", "source_raw_sha256", "source_canonical_sha256", "migration_map_sha256", "migration_tool_sha256")):
            fail("STATE055_MIGRATION_PROVENANCE_INVALID", "/migration_provenance")
    elif provenance["status"] == "migrated":
        if not isinstance(provenance["source_schema_version"], str) or not provenance["source_schema_version"] or len(provenance["source_schema_version"]) > 32:
            fail("STATE055_MIGRATION_PROVENANCE_INVALID", "/migration_provenance/source_schema_version")
        for field in ("source_raw_sha256", "source_canonical_sha256", "migration_map_sha256", "migration_tool_sha256"):
            _sha(provenance[field], f"/migration_provenance/{field}")
    else:
        fail("STATE055_MIGRATION_PROVENANCE_INVALID", "/migration_provenance/status")
    if not isinstance(data["updated_at"], str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["updated_at"]) is None:
        fail("STATE056_DATE_INVALID", "/updated_at")
    try:
        date.fromisoformat(data["updated_at"])
    except ValueError:
        fail("STATE056_DATE_INVALID", "/updated_at")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one project-state-v2 JSON document from stdin.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            if sha256_object({"b": 2, "a": 1}) != hashlib.sha256(b'{"a":1,"b":2}\n').hexdigest():
                fail("SELF_TEST_FAILED")
            print("project state v2 self-test passed")
            return 0
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            fail("JSON_TOO_LARGE")
        validate_project_state(parse_json_bytes(raw))
    except StateV2Error as exc:
        print(f"project-state-v2 error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        print("project-state-v2 error: STATE023_CONTRACT_INVALID at /", file=sys.stderr)
        return 1
    print("project state v2 valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
