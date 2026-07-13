#!/usr/bin/env python3
"""Dependency-free validation and bundle checks for V7-08 auxiliary contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


TAKE_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/take-review-v2.schema.json"
PROMPT_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/prompt-spec-v2.schema.json"
RUN_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/generation-run-v2.schema.json"
PROJECT_SCHEMA = "https://github.com/Emily2040/seedance-2.0/schemas/project-state-v2.schema.json"
SCHEMA_FILES = {
    TAKE_SCHEMA: "take-review-v2.schema.json",
    PROMPT_SCHEMA: "prompt-spec-v2.schema.json",
    RUN_SCHEMA: "generation-run-v2.schema.json",
}
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_FILES = 64
MAX_DEPTH = 64
MAX_NODES = 100_000
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

TAKE_FIELDS = {
    "decision_status", "source_status", "verdict", "media_kind", "accepted_media_sha256",
    "observed_start_snapshot_sha256", "observed_end_snapshot_sha256", "endpoint_states",
    "completed_beat_ids", "incomplete_beat_ids", "unexpected_completed_beat_ids",
    "continuity_break_ids", "accepted_deviation_ids", "observation_confidence",
    "requires_user_confirmation",
}
PROMPT_FIELDS = {
    "status", "project_id", "clip_id", "state_revision", "canon_revision",
    "semantic_state_sha256", "sequence_relation", "opening_source", "parent_clip_id",
    "observed_source_snapshot_sha256", "accepted_source_media_sha256", "source_take_id",
    "source_take_review_sha256", "source_accepted_deviation_ids", "completed_beat_ids", "reserved_future_beat_ids",
    "carry_forward_motion_bindings",
    "planning_status", "reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256",
}
RUN_FIELDS = {
    "run_id", "project_id", "clip_id", "state_revision", "canon_revision",
    "semantic_state_sha256", "project_state_sha256", "prompt_spec_id",
    "prompt_spec_sha256", "execution_status", "result_status", "is_synthetic_fixture",
    "block_reason",
}
FORBIDDEN_EXECUTION_FIELDS = {
    "prompt", "natural_language_prompt", "prompt_render_sha256", "render_sha256", "result_sha256",
    "provider", "provider_handle", "surface_binding", "compiler_sha256",
    "compiler_toolchain_sha256", "submission_id", "output_url",
}
ACCEPT_VERDICTS = {"accept", "accept_with_deviation"}
ACCEPTED_STATUSES = {"accepted", "accepted_with_deviation"}
UNCERTAIN_ENDPOINTS = {"incomplete", "unknown"}
FRAME_UNPROVABLE_ENDPOINTS = {
    "completed_with_motion", "dissipated_or_resolved", "frame_exit", "cyclic_phase_boundary",
    "open_handoff", "incomplete", "unknown",
}
ACCEPTED_OPENINGS = {"accepted_parent_video", "accepted_parent_final_frame"}
DESCRIBED_OPENINGS = {"user_description", "legacy_description"}
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


class InputFailure(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputFailure("AUX004_DUPLICATE_KEY", "duplicate object keys are forbidden")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise InputFailure("AUX005_NONFINITE_NUMBER", "non-finite JSON numbers are forbidden")


def _resource_check(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise InputFailure("AUX006_RESOURCE_LIMIT", "document structure exceeds the bounded resource limit")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def parse_document(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_INPUT_BYTES:
        raise InputFailure("AUX001_INPUT_TOO_LARGE", "input exceeds the bounded byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputFailure("AUX002_INVALID_UTF8", "input must be valid UTF-8") from exc
    if text.startswith("\ufeff"):
        raise InputFailure("AUX003_BOM_FORBIDDEN", "UTF-8 BOM is forbidden")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except InputFailure:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError, OverflowError) as exc:
        raise InputFailure("AUX007_INVALID_JSON", "input must be bounded strict JSON") from exc
    if not isinstance(value, dict):
        raise InputFailure("AUX008_ROOT_NOT_OBJECT", "document root must be an object")
    _resource_check(value)
    return value


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _error(errors: set[str], code: str, message: str) -> None:
    errors.add(f"{code}: {message}")


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _schema_type(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }.get(expected, False)


def _resolve_ref(root: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        return None
    current: Any = root
    for encoded in reference[2:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _schema_valid(value: Any, schema: Any, root: dict[str, Any]) -> bool:
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, dict):
        return False
    reference = schema.get("$ref")
    if reference is not None:
        target = _resolve_ref(root, reference) if isinstance(reference, str) else None
        if target is None or not _schema_valid(value, target, root):
            return False
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _schema_type(value, expected_type):
        return False
    if isinstance(expected_type, list) and not any(isinstance(item, str) and _schema_type(value, item) for item in expected_type):
        return False
    if "const" in schema and not _json_equal(value, schema["const"]):
        return False
    if "enum" in schema and (not isinstance(schema["enum"], list) or not any(_json_equal(value, item) for item in schema["enum"])):
        return False
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            return False
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            return False
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            return False
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            return False
        if isinstance(schema.get("exclusiveMinimum"), (int, float)) and value <= schema["exclusiveMinimum"]:
            return False
        if isinstance(schema.get("exclusiveMaximum"), (int, float)) and value >= schema["exclusiveMaximum"]:
            return False
    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list) and any(not isinstance(key, str) or key not in value for key in required):
            return False
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return False
        for key, child_schema in properties.items():
            if key in value and not _schema_valid(value[key], child_schema, root):
                return False
        extras = set(value) - set(properties)
        additional = schema.get("additionalProperties", True)
        if additional is False and extras:
            return False
        if isinstance(additional, dict) and any(not _schema_valid(value[key], additional, root) for key in extras):
            return False
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            return False
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            return False
        if schema.get("uniqueItems") is True:
            fingerprints = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value]
            if len(fingerprints) != len(set(fingerprints)):
                return False
        if "items" in schema and any(not _schema_valid(item, schema["items"], root) for item in value):
            return False
        if "contains" in schema and not any(_schema_valid(item, schema["contains"], root) for item in value):
            return False
    if "not" in schema and _schema_valid(value, schema["not"], root):
        return False
    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and sum(_schema_valid(value, item, root) for item in one_of) != 1:
        return False
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and any(not _schema_valid(value, item, root) for item in all_of):
        return False
    condition = schema.get("if")
    if isinstance(condition, dict):
        selected = schema.get("then") if _schema_valid(value, condition, root) else schema.get("else")
        if selected is not None and not _schema_valid(value, selected, root):
            return False
    return True


def _contract_schema(schema_uri: str) -> dict[str, Any] | None:
    if schema_uri in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[schema_uri]
    filename = SCHEMA_FILES.get(schema_uri)
    if filename is None:
        return None
    try:
        schema = parse_document((SCHEMA_ROOT / filename).read_bytes())
    except (OSError, InputFailure):
        return None
    _SCHEMA_CACHE[schema_uri] = schema
    return schema


def schema_contract_valid(document: dict[str, Any]) -> bool:
    schema_uri = document.get("$schema")
    if not isinstance(schema_uri, str):
        return False
    schema = _contract_schema(schema_uri)
    return schema is not None and _schema_valid(document, schema, schema)


def _semantic_shape(document: dict[str, Any], required: set[str], errors: set[str]) -> bool:
    if not required.issubset(document):
        _error(errors, "AUX010_SEMANTIC_FIELDS", "required semantic fields are missing")
        return False
    return True


def _array(document: dict[str, Any], key: str, errors: set[str]) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        _error(errors, "AUX011_SEMANTIC_TYPE", "a semantic array field has the wrong type")
        return []
    return value


def validate_take_review(document: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not _semantic_shape(document, TAKE_FIELDS, errors):
        return sorted(errors)
    scalar_fields = ("decision_status", "source_status", "verdict", "media_kind", "observation_confidence")
    if any(not isinstance(document.get(key), str) for key in scalar_fields) or not isinstance(document.get("requires_user_confirmation"), bool):
        _error(errors, "AUX011_SEMANTIC_TYPE", "a semantic scalar field has the wrong type")
        return sorted(errors)
    beat_arrays = {
        key: _array(document, key, errors)
        for key in ("completed_beat_ids", "incomplete_beat_ids", "unexpected_completed_beat_ids")
    }
    if any(not all(isinstance(item, str) for item in value) for value in beat_arrays.values()):
        _error(errors, "AUX011_SEMANTIC_TYPE", "a semantic array item has the wrong type")
    beat_sets = [set(value) for value in beat_arrays.values() if all(isinstance(item, str) for item in value)]
    if len(beat_sets) == 3 and any(beat_sets[left] & beat_sets[right] for left in range(3) for right in range(left + 1, 3)):
        _error(errors, "AUX100_BEAT_SET_OVERLAP", "completed, incomplete, and unexpected beat sets must be disjoint")
    endpoints = _array(document, "endpoint_states", errors)
    endpoint_ids: set[str] = set()
    endpoint_owners: set[tuple[str, str]] = set()
    endpoint_modes: set[str] = set()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            _error(errors, "AUX011_SEMANTIC_TYPE", "an endpoint state has the wrong type")
            continue
        endpoint_id = endpoint.get("endpoint_id")
        owner = (endpoint.get("owner_kind"), endpoint.get("owner_id"))
        mode = endpoint.get("completion_mode")
        if not isinstance(endpoint_id, str) or not all(isinstance(item, str) for item in owner) or not isinstance(mode, str):
            _error(errors, "AUX011_SEMANTIC_TYPE", "an endpoint semantic field has the wrong type")
            continue
        if endpoint_id in endpoint_ids:
            _error(errors, "AUX101_ENDPOINT_ID_DUPLICATE", "endpoint identifiers must be unique")
        endpoint_ids.add(endpoint_id)
        if owner in endpoint_owners:
            _error(errors, "AUX102_ENDPOINT_OWNER_DUPLICATE", "endpoint owners must be unique")
        endpoint_owners.add(owner)
        endpoint_modes.add(mode)

    decision = document.get("decision_status")
    source_status = document.get("source_status")
    verdict = document.get("verdict")
    media_kind = document.get("media_kind")
    digest = document.get("accepted_media_sha256")
    confirmation = document.get("requires_user_confirmation")
    if media_kind == "video" and not (_sha(document.get("observed_start_snapshot_sha256")) and _sha(document.get("observed_end_snapshot_sha256"))):
        _error(errors, "AUX116_VIDEO_OBSERVATION", "video evidence requires observed start and end snapshots")
    if media_kind == "final_frame" and (document.get("observed_start_snapshot_sha256") is not None or not _sha(document.get("observed_end_snapshot_sha256"))):
        _error(errors, "AUX117_FRAME_OBSERVATION", "final-frame evidence has only an observed end snapshot")
    if media_kind in {"user_description", "legacy_description"} and (
        document.get("observed_start_snapshot_sha256") is not None or document.get("observed_end_snapshot_sha256") is not None
    ):
        _error(errors, "AUX118_DESCRIPTION_OBSERVATION", "descriptions cannot claim observed snapshots")
    if decision == "pending_confirmation":
        if source_status != "reviewed" or confirmation is not True or digest is not None:
            _error(errors, "AUX103_PENDING_RELATION", "pending decisions must remain reviewed, unaccepted, and confirmation-gated")
    elif decision == "final":
        if confirmation is not False:
            _error(errors, "AUX104_FINAL_CONFIRMATION", "final decisions cannot require confirmation")
        expected = {"accept": "accepted", "accept_with_deviation": "accepted_with_deviation", "repair": "repair", "reject": "rejected"}.get(verdict)
        if expected is None or source_status != expected:
            _error(errors, "AUX105_FINAL_STATUS", "final verdict and source status are inconsistent")
        if verdict in ACCEPT_VERDICTS:
            if media_kind not in {"video", "final_frame"} or not _sha(digest):
                _error(errors, "AUX106_ACCEPTED_MEDIA", "final acceptance requires accepted video or frame evidence")
        elif digest is not None:
            _error(errors, "AUX107_UNACCEPTED_DIGEST", "repair and reject decisions cannot carry an accepted-media digest")
        if verdict in ACCEPT_VERDICTS:
            unresolved = ("incomplete_beat_ids", "unexpected_completed_beat_ids", "continuity_break_ids")
            if document.get("observation_confidence") not in {"low", "medium", "high"}:
                _error(errors, "AUX108_ACCEPT_CONFIDENCE", "final acceptance requires known observation confidence")
            if any(_array(document, key, errors) for key in unresolved):
                _error(errors, "AUX109_ACCEPT_NOT_RESOLVED", "final acceptance cannot retain unresolved completion or continuity facts")
        if verdict == "accept" and _array(document, "accepted_deviation_ids", errors):
            _error(errors, "AUX110_DEVIATION_MISLABELED", "ordinary acceptance cannot carry named deviations")
        if verdict == "accept_with_deviation" and not _array(document, "accepted_deviation_ids", errors):
            _error(errors, "AUX111_DEVIATION_UNNAMED", "accept-with-deviation requires at least one named disposition")
    else:
        _error(errors, "AUX112_DECISION_STATUS", "decision status is invalid")
    if source_status in ACCEPTED_STATUSES and (decision != "final" or endpoint_modes & UNCERTAIN_ENDPOINTS):
        _error(errors, "AUX113_TERMINAL_UNCERTAINTY", "terminal accepted status cannot carry unresolved endpoint uncertainty")
    if verdict in ACCEPT_VERDICTS and endpoint_modes & UNCERTAIN_ENDPOINTS and decision != "pending_confirmation":
        _error(errors, "AUX114_ACCEPT_REQUIRES_CONFIRMATION", "uncertain accepted endpoints require a pending confirmation decision")
    if decision == "final" and media_kind in {"user_description", "legacy_description"} and verdict in ACCEPT_VERDICTS:
        _error(errors, "AUX115_DESCRIPTION_ACCEPTED", "descriptions cannot become finally accepted media")
    if decision == "final" and media_kind == "final_frame" and endpoint_modes & FRAME_UNPROVABLE_ENDPOINTS:
        _error(errors, "AUX119_FRAME_TEMPORAL_CLAIM", "a final frame cannot finally establish a temporal endpoint mode")
    return sorted(errors)


def validate_prompt_spec(document: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not _semantic_shape(document, PROMPT_FIELDS, errors):
        return sorted(errors)
    scalar_fields = ("status", "sequence_relation", "opening_source", "planning_status")
    if any(not isinstance(document.get(key), str) for key in scalar_fields):
        _error(errors, "AUX011_SEMANTIC_TYPE", "a semantic scalar field has the wrong type")
        return sorted(errors)
    if set(document) & FORBIDDEN_EXECUTION_FIELDS:
        _error(errors, "AUX200_FORBIDDEN_PROMPT_FIELD", "prompt, render, provider, surface, and compiler fields are forbidden")
    if document.get("status") != "compile_required":
        _error(errors, "AUX201_COMPILE_STATUS", "v2 prompt specifications must remain compile-required")
    completed = _array(document, "completed_beat_ids", errors)
    reserved = _array(document, "reserved_future_beat_ids", errors)
    if not all(isinstance(item, str) for item in completed + reserved):
        _error(errors, "AUX011_SEMANTIC_TYPE", "a semantic array item has the wrong type")
    elif set(completed) & set(reserved):
        _error(errors, "AUX202_PROMPT_BEAT_OVERLAP", "completed and reserved beat sets must be disjoint")
    carry_bindings = _array(document, "carry_forward_motion_bindings", errors)
    parent_motion_ids: set[str] = set()
    opening_motion_ids: set[str] = set()
    sort_keys: list[tuple[str, str, str]] = []
    for binding in carry_bindings:
        if not isinstance(binding, dict):
            _error(errors, "AUX011_SEMANTIC_TYPE", "a carry-forward binding has the wrong type")
            continue
        fields = ("endpoint_id", "owner_kind", "owner_id", "parent_motion_id", "opening_motion_id")
        if any(not isinstance(binding.get(field), str) for field in fields):
            _error(errors, "AUX011_SEMANTIC_TYPE", "a carry-forward binding field has the wrong type")
            continue
        if binding["parent_motion_id"] in parent_motion_ids:
            _error(errors, "AUX210_PARENT_MOTION_DUPLICATE", "a parent motion can appear in only one carry binding")
        if binding["opening_motion_id"] in opening_motion_ids:
            _error(errors, "AUX211_OPENING_MOTION_DUPLICATE", "an opening motion can receive only one carried motion")
        parent_motion_ids.add(binding["parent_motion_id"])
        opening_motion_ids.add(binding["opening_motion_id"])
        sort_keys.append((binding["endpoint_id"], binding["parent_motion_id"], binding["opening_motion_id"]))
    if sort_keys != sorted(sort_keys):
        _error(errors, "AUX212_CARRY_BINDINGS_UNSORTED", "carry-forward bindings must use canonical endpoint and motion order")
    relation = document.get("sequence_relation")
    opening = document.get("opening_source")
    source_fields = (
        document.get("observed_source_snapshot_sha256"), document.get("accepted_source_media_sha256"),
        document.get("parent_clip_id"), document.get("source_take_id"), document.get("source_take_review_sha256"),
    )
    source_deviations = _array(document, "source_accepted_deviation_ids", errors)
    if opening in ACCEPTED_OPENINGS:
        if not (_sha(source_fields[0]) and _sha(source_fields[1]) and isinstance(source_fields[2], str) and isinstance(source_fields[3], str) and _sha(source_fields[4])):
            _error(errors, "AUX203_ACCEPTED_SOURCE_PROVENANCE", "accepted-parent openings require complete observed take provenance")
    elif opening in {"planned_start"} | DESCRIBED_OPENINGS:
        if any(value is not None for value in source_fields):
            _error(errors, "AUX204_NONPARENT_PROVENANCE", "non-parent openings cannot carry accepted take provenance")
        if carry_bindings:
            _error(errors, "AUX213_NONPARENT_CARRY", "non-parent openings cannot claim carried motion bindings")
        if source_deviations:
            _error(errors, "AUX214_NONPARENT_DEVIATION", "non-parent openings cannot claim accepted source deviations")
    else:
        _error(errors, "AUX205_OPENING_SOURCE", "opening source is invalid")
    if relation in {"standalone", "sequence_first_clip"}:
        allowed = {"planned_start"} | DESCRIBED_OPENINGS
    elif relation in {"seamless_continuation", "bridge_between_known_states", "reanchor_after_drift"}:
        allowed = ACCEPTED_OPENINGS
    elif relation == "repair_tail":
        allowed = {"accepted_parent_video"}
    elif relation == "intentional_next_shot":
        allowed = {"planned_start"} | ACCEPTED_OPENINGS
    else:
        allowed = set()
    if opening not in allowed:
        _error(errors, "AUX206_RELATION_OPENING", "sequence relation and opening source are inconsistent")
    planning = document.get("planning_status")
    planning_hashes = tuple(document.get(key) for key in ("reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256"))
    if planning != "planning_required":
        _error(errors, "AUX208_PLANNED_ARTIFACTS_UNVERIFIED", "V7-08 cannot accept planned artifacts without a strict artifact bundle")
    if any(value is not None for value in planning_hashes):
        _error(errors, "AUX207_UNPLANNED_HASH", "planning-required state cannot carry planning artifact hashes")
    return sorted(errors)


def validate_generation_run(document: dict[str, Any]) -> list[str]:
    errors: set[str] = set()
    if not _semantic_shape(document, RUN_FIELDS, errors):
        return sorted(errors)
    if set(document) & FORBIDDEN_EXECUTION_FIELDS:
        _error(errors, "AUX300_FORBIDDEN_RUN_FIELD", "run receipts cannot contain prompt, result, provider, or compiler claims")
    execution_status = document.get("execution_status")
    if not isinstance(execution_status, str) or execution_status not in {"compile_required", "blocked"} or document.get("result_status") != "not_run_fixture":
        _error(errors, "AUX301_RUN_NOT_BLOCKED", "v2 generation runs must remain unexecuted fixtures")
    if document.get("is_synthetic_fixture") is not True:
        _error(errors, "AUX302_RUN_NOT_SYNTHETIC", "v2 generation runs must identify synthetic fixture status")
    coherent_pairs = {
        ("compile_required", "v2_compiler_not_available"),
        ("blocked", "planning_required"),
        ("blocked", "migration_review_required"),
    }
    pair = (document.get("execution_status"), document.get("block_reason"))
    if not all(isinstance(item, str) for item in pair) or pair not in coherent_pairs:
        _error(errors, "AUX303_RUN_REASON_PAIR", "execution status and block reason are internally inconsistent")
    return sorted(errors)


def validate_document(document: dict[str, Any]) -> list[str]:
    schema = document.get("$schema")
    if not isinstance(schema, str) or schema not in SCHEMA_FILES:
        return ["AUX009_SCHEMA_UNKNOWN: exact v2 auxiliary schema dispatch is required"]
    errors: set[str] = set()
    if not schema_contract_valid(document):
        _error(errors, "AUX020_SCHEMA_CONTRACT", "document does not satisfy its complete packaged schema contract")
    semantic = {
        TAKE_SCHEMA: validate_take_review,
        PROMPT_SCHEMA: validate_prompt_spec,
        RUN_SCHEMA: validate_generation_run,
    }[schema](document)
    errors.update(semantic)
    return sorted(errors)


def _validate_project(document: dict[str, Any]) -> bool:
    try:
        try:
            from scripts import project_state_v2_check as state
        except ImportError:
            import project_state_v2_check as state  # type: ignore[no-redef]
        state.validate_project_state(document)
        return True
    except Exception:
        return False


def _verify_carry_projection(
    prompt: dict[str, Any], parent: dict[str, Any], current: dict[str, Any], errors: set[str]
) -> None:
    observed_end = parent.get("observed_end_snapshot")
    if not isinstance(observed_end, dict):
        _error(errors, "AUX425_PARENT_OBSERVED_END_REQUIRED", "carry projection requires an accepted parent observed end")
        return
    carry_endpoints: dict[tuple[Any, Any], dict[str, Any]] = {}
    for endpoint in observed_end.get("endpoint_states", []):
        if isinstance(endpoint, dict) and endpoint.get("carry_forward") is True:
            carry_endpoints[(endpoint.get("owner_kind"), endpoint.get("owner_id"))] = endpoint
    parent_vectors = {
        vector.get("motion_id"): vector
        for vector in observed_end.get("motion_handoff", {}).get("vectors", [])
        if isinstance(vector, dict)
        and vector.get("continuity") == "open"
        and (vector.get("owner_kind"), vector.get("owner_id")) in carry_endpoints
    }
    opening_vectors = {
        vector.get("motion_id"): vector
        for vector in current.get("planned_start_snapshot", {}).get("motion_handoff", {}).get("vectors", [])
        if isinstance(vector, dict) and vector.get("continuity") == "open"
    }
    endpoint_vector_owners = {
        (vector.get("owner_kind"), vector.get("owner_id")) for vector in parent_vectors.values()
    }
    if set(carry_endpoints) - endpoint_vector_owners:
        _error(errors, "AUX426_CARRY_ENDPOINT_WITHOUT_MOTION", "each carried endpoint requires at least one parent open motion")
    bindings = prompt.get("carry_forward_motion_bindings")
    if not isinstance(bindings, list):
        _error(errors, "AUX427_CARRY_BINDING_INVALID", "carry projection must be a binding array")
        return
    bound_parent: set[Any] = set()
    bound_opening: set[Any] = set()
    signature_fields = ("owner_kind", "owner_id", "domain", "coordinate_frame", "direction", "speed_trend")
    for binding in bindings:
        if not isinstance(binding, dict):
            _error(errors, "AUX427_CARRY_BINDING_INVALID", "carry projection contains an invalid binding")
            continue
        owner = (binding.get("owner_kind"), binding.get("owner_id"))
        endpoint = carry_endpoints.get(owner)
        parent_vector = parent_vectors.get(binding.get("parent_motion_id"))
        opening_vector = opening_vectors.get(binding.get("opening_motion_id"))
        if endpoint is None or endpoint.get("endpoint_id") != binding.get("endpoint_id"):
            _error(errors, "AUX428_CARRY_ENDPOINT_BINDING", "carry binding does not identify an exact carried endpoint")
        if parent_vector is None or any(parent_vector.get(field) != binding.get(field) for field in ("owner_kind", "owner_id")):
            _error(errors, "AUX429_PARENT_MOTION_BINDING", "carry binding does not identify an exact parent open motion")
        if opening_vector is None or any(opening_vector.get(field) != binding.get(field) for field in ("owner_kind", "owner_id")):
            _error(errors, "AUX430_OPENING_MOTION_BINDING", "carry binding does not identify an exact child opening motion")
        if parent_vector is not None and opening_vector is not None and any(
            parent_vector.get(field) != opening_vector.get(field) for field in signature_fields
        ):
            _error(errors, "AUX431_CARRY_SIGNATURE_MISMATCH", "parent and opening motion signatures do not match")
        parent_motion_id = binding.get("parent_motion_id")
        opening_motion_id = binding.get("opening_motion_id")
        if parent_motion_id in bound_parent or opening_motion_id in bound_opening:
            _error(errors, "AUX432_CARRY_NOT_ONE_TO_ONE", "carry motion projection must be globally one-to-one")
        bound_parent.add(parent_motion_id)
        bound_opening.add(opening_motion_id)
    if bound_parent != set(parent_vectors):
        _error(errors, "AUX433_CARRY_COVERAGE", "carry projection omits or adds parent carried motions")


def verify_bundle(documents: list[dict[str, Any]]) -> list[str]:
    errors: set[str] = set()
    groups: dict[Any, list[dict[str, Any]]] = {}
    for document in documents:
        schema = document.get("$schema")
        groups.setdefault(schema if isinstance(schema, str) else None, []).append(document)
    if len(groups.get(PROJECT_SCHEMA, [])) != 1 or len(groups.get(PROMPT_SCHEMA, [])) != 1 or len(groups.get(RUN_SCHEMA, [])) != 1:
        return ["AUX400_BUNDLE_MEMBERS: bundle requires exactly one project state, prompt specification, and generation run"]
    if set(groups) - {PROJECT_SCHEMA, TAKE_SCHEMA, PROMPT_SCHEMA, RUN_SCHEMA}:
        return ["AUX401_BUNDLE_SCHEMA: bundle contains an unsupported schema"]
    project = groups[PROJECT_SCHEMA][0]
    prompt = groups[PROMPT_SCHEMA][0]
    run = groups[RUN_SCHEMA][0]
    reviews = groups.get(TAKE_SCHEMA, [])
    if not _validate_project(project):
        _error(errors, "AUX402_PROJECT_INVALID", "bundle project state failed its dependency-free validator")
        return sorted(errors)
    for document in [*reviews, prompt, run]:
        if validate_document(document):
            _error(errors, "AUX403_AUX_MEMBER_INVALID", "bundle contains an invalid auxiliary contract")
    if errors:
        return sorted(errors)

    identity_fields = ("project_id", "state_revision", "canon_revision", "semantic_state_sha256")
    if any(prompt.get(key) != project.get(key) or run.get(key) != project.get(key) for key in identity_fields):
        _error(errors, "AUX404_PROJECT_BINDING", "project identity, revisions, or semantic hash do not match")
    if run.get("clip_id") != prompt.get("clip_id") or run.get("prompt_spec_id") != prompt.get("prompt_spec_id"):
        _error(errors, "AUX405_PROMPT_ID_BINDING", "generation run does not identify the exact prompt specification")
    if run.get("project_state_sha256") != canonical_sha256(project) or run.get("prompt_spec_sha256") != canonical_sha256(prompt):
        _error(errors, "AUX406_ARTIFACT_HASH_BINDING", "generation run artifact hashes do not match canonical bundle members")

    clips = project.get("semantic_state", {}).get("clips", [])
    clip_by_id = {clip.get("clip_id"): clip for clip in clips if isinstance(clip, dict)}
    if prompt.get("clip_id") != project.get("semantic_state", {}).get("current_clip_id"):
        _error(errors, "AUX407_CURRENT_CLIP_BINDING", "prompt and run must target the project's exact current clip")
    current = clip_by_id.get(prompt.get("clip_id"))
    if not isinstance(current, dict):
        _error(errors, "AUX407_CURRENT_CLIP_BINDING", "prompt clip is absent from project state")
        return sorted(errors)
    if current.get("status") != "planned" or current.get("execution_readiness") not in {"migration_review", "planning_required"}:
        _error(errors, "AUX408_TARGET_NOT_PLANNABLE", "current target clip must remain planned and pre-compile")
    if prompt.get("sequence_relation") != current.get("sequence_relation") or prompt.get("parent_clip_id") != current.get("parent_clip_id"):
        _error(errors, "AUX409_CLIP_RELATION_BINDING", "prompt relation or parent does not match project state")
    if prompt.get("planned_start_snapshot_sha256") != current.get("planned_start_snapshot", {}).get("snapshot_sha256"):
        _error(errors, "AUX410_PLANNED_SNAPSHOT_BINDING", "prompt planned start snapshot does not match project state")
    if prompt.get("planned_end_snapshot_sha256") != current.get("planned_end_snapshot", {}).get("snapshot_sha256"):
        _error(errors, "AUX410_PLANNED_SNAPSHOT_BINDING", "prompt planned end snapshot does not match project state")
    planning_link = current.get("planning_link", {})
    if planning_link.get("status") == "planned":
        _error(errors, "AUX422_PLANNED_ARTIFACT_BUNDLE_REQUIRED", "V7-08 fails closed when exact planning artifacts are not bundled")
    if prompt.get("planning_status") != planning_link.get("status"):
        _error(errors, "AUX434_PLANNING_BINDING", "prompt planning status does not match project state")
    for field in ("reference_manifest_sha256", "scene_ir_sha256", "planning_report_sha256"):
        if prompt.get(field) != planning_link.get(field):
            _error(errors, "AUX434_PLANNING_BINDING", "prompt planning artifacts do not match project state")
    if prompt.get("reference_binding_ids") != planning_link.get("binding_ids"):
        _error(errors, "AUX434_PLANNING_BINDING", "prompt reference bindings do not match project state")
    expected_run_pair: tuple[str, str] | None = None
    readiness = current.get("execution_readiness")
    if current.get("compile_required") is not True:
        _error(errors, "AUX440_RUN_STATE_BINDING", "generation receipt requires an explicit compile-required project clip")
    elif planning_link.get("status") == "planning_required" and prompt.get("planning_status") == "planning_required":
        if readiness == "migration_review":
            expected_run_pair = ("blocked", "migration_review_required")
        elif readiness == "planning_required":
            expected_run_pair = ("blocked", "planning_required")
    elif planning_link.get("status") == "planned" and prompt.get("planning_status") == "planned" and readiness == "compile_required":
        expected_run_pair = ("compile_required", "v2_compiler_not_available")
    if expected_run_pair is None:
        _error(errors, "AUX440_RUN_STATE_BINDING", "project and prompt planning state do not define a valid generation receipt")
    elif (run.get("execution_status"), run.get("block_reason")) != expected_run_pair:
        _error(errors, "AUX441_RUN_REASON_BINDING", "generation execution status and block reason do not match project readiness")
    expected_endpoint_hash = canonical_sha256(current.get("planned_end_snapshot", {}).get("endpoint_states", []))
    expected_motion_hash = canonical_sha256(current.get("planned_start_snapshot", {}).get("motion_handoff", {}))
    if prompt.get("endpoint_states_sha256") != expected_endpoint_hash or prompt.get("motion_snapshot_sha256") != expected_motion_hash:
        _error(errors, "AUX423_STATE_PROJECTION_BINDING", "prompt endpoint or motion projection hash does not match project state")
    expected_rules = [rule.get("rule_id") for rule in current.get("continuity_rules", []) if isinstance(rule, dict)]
    if (
        prompt.get("completed_beat_ids") != current.get("already_happened")
        or prompt.get("reserved_future_beat_ids") != current.get("reserved_for_later")
        or prompt.get("continuity_rule_ids") != expected_rules
    ):
        _error(errors, "AUX424_STATE_SET_BINDING", "prompt state sets do not match the selected project clip")

    opening = prompt.get("opening_source")
    if opening in ACCEPTED_OPENINGS:
        matches = [review for review in reviews if review.get("take_id") == prompt.get("source_take_id")]
        if len(matches) != 1:
            _error(errors, "AUX411_SOURCE_REVIEW_REQUIRED", "accepted-parent opening requires exactly one matching take review")
            return sorted(errors)
        review = matches[0]
        expected_kind = "video" if opening == "accepted_parent_video" else "final_frame"
        expected_source_kind = "accepted_video" if opening == "accepted_parent_video" else "accepted_final_frame"
        if canonical_sha256(review) != prompt.get("source_take_review_sha256"):
            _error(errors, "AUX412_REVIEW_HASH_BINDING", "source take review canonical hash does not match")
        if review.get("project_id") != prompt.get("project_id") or review.get("clip_id") != prompt.get("parent_clip_id"):
            _error(errors, "AUX413_REVIEW_ID_BINDING", "source take project or parent clip does not match")
        if review.get("decision_status") != "final" or review.get("source_status") not in ACCEPTED_STATUSES or review.get("verdict") not in ACCEPT_VERDICTS:
            _error(errors, "AUX414_REVIEW_NOT_ACCEPTED", "source take review is not terminally accepted")
        if review.get("media_kind") != expected_kind or review.get("accepted_media_sha256") != prompt.get("accepted_source_media_sha256"):
            _error(errors, "AUX415_REVIEW_MEDIA_BINDING", "source media kind or digest does not match")
        if review.get("observed_end_snapshot_sha256") != prompt.get("observed_source_snapshot_sha256"):
            _error(errors, "AUX416_REVIEW_SNAPSHOT_BINDING", "source observed end snapshot does not match")
        parent = clip_by_id.get(prompt.get("parent_clip_id"))
        observed = parent.get("observed_end_snapshot") if isinstance(parent, dict) else None
        source = observed.get("source", {}) if isinstance(observed, dict) else {}
        if not isinstance(parent, dict) or parent.get("status") not in ACCEPTED_STATUSES or parent.get("status") != review.get("source_status"):
            _error(errors, "AUX417_PARENT_NOT_ACCEPTED", "project parent clip is not accepted")
        elif (
            source.get("kind") != expected_source_kind
            or source.get("take_id") != review.get("take_id")
            or source.get("media_sha256") != review.get("accepted_media_sha256")
            or observed.get("snapshot_sha256") != review.get("observed_end_snapshot_sha256")
        ):
            _error(errors, "AUX418_PARENT_REVIEW_BINDING", "project parent observation does not match the source take review")
        if isinstance(parent, dict) and isinstance(observed, dict):
            observed_start = parent.get("observed_start_snapshot")
            if expected_kind == "video":
                start_source = observed_start.get("source", {}) if isinstance(observed_start, dict) else {}
                if (
                    not isinstance(observed_start, dict)
                    or observed_start.get("snapshot_sha256") != review.get("observed_start_snapshot_sha256")
                    or start_source.get("kind") != "accepted_video"
                    or start_source.get("take_id") != review.get("take_id")
                    or start_source.get("media_sha256") != review.get("accepted_media_sha256")
                ):
                    _error(errors, "AUX435_REVIEW_START_BINDING", "video review start does not match an actual project observed start")
            elif observed_start is not None or review.get("observed_start_snapshot_sha256") is not None:
                _error(errors, "AUX435_REVIEW_START_BINDING", "final-frame review cannot claim a project observed start")
            if canonical_json(review.get("endpoint_states")) != canonical_json(observed.get("endpoint_states")):
                _error(errors, "AUX436_REVIEW_ENDPOINT_BINDING", "review endpoint states do not match project observed end canon")
            beat_by_id = {
                beat.get("beat_id"): beat
                for beat in project.get("semantic_state", {}).get("beats", [])
                if isinstance(beat, dict)
            }
            local_beats = parent.get("this_clip_only", [])
            expected_completed = {
                beat_id for beat_id in local_beats if beat_by_id.get(beat_id, {}).get("status") == "completed"
            }
            expected_incomplete = {
                beat_id for beat_id in local_beats if beat_by_id.get(beat_id, {}).get("status") in {"planned", "current"}
            }
            review_completed = set(review.get("completed_beat_ids", []))
            review_incomplete = set(review.get("incomplete_beat_ids", []))
            if review_completed != expected_completed or review_incomplete != expected_incomplete:
                _error(errors, "AUX437_REVIEW_BEAT_BINDING", "review completed and incomplete beat sets do not match project canon")
            if review.get("unexpected_completed_beat_ids") or review.get("continuity_break_ids"):
                _error(errors, "AUX438_REVIEW_UNREPRESENTED_FACT", "review facts absent from project canon cannot enter an accepted-parent bundle")
            project_deviations = parent.get("accepted_deviation_ids")
            review_deviations = review.get("accepted_deviation_ids")
            prompt_deviations = prompt.get("source_accepted_deviation_ids")
            if project_deviations != review_deviations or review_deviations != prompt_deviations:
                _error(errors, "AUX439_REVIEW_DISPOSITION_BINDING", "accepted deviation IDs must match project, review, and prompt exactly")
            if parent.get("status") == "accepted" and project_deviations:
                _error(errors, "AUX442_ACCEPTED_DEVIATION_STATUS", "ordinary accepted parent cannot carry accepted deviations")
            if parent.get("status") == "accepted_with_deviation" and not project_deviations:
                _error(errors, "AUX442_ACCEPTED_DEVIATION_STATUS", "accepted-with-deviation parent requires named accepted deviations")
            _verify_carry_projection(prompt, parent, current, errors)
    elif reviews:
        _error(errors, "AUX419_UNUSED_REVIEW", "non-parent bundle cannot carry unrelated take reviews")
    return sorted(errors)


def _self_test_documents() -> list[dict[str, Any]]:
    sha = "a" * 64
    take = {
        "$schema": TAKE_SCHEMA, "schema_version": 2, "project_id": "self_test", "clip_id": "clip_01",
        "take_id": "take_01", "decision_status": "final", "source_status": "accepted", "verdict": "accept",
        "media_kind": "video", "accepted_media_sha256": sha, "observed_start_snapshot_sha256": "b" * 64,
        "observed_end_snapshot_sha256": "c" * 64,
        "endpoint_states": [{"endpoint_id": "end", "owner_kind": "shot", "owner_id": "shot", "completion_mode": "held_static", "carry_forward": False, "description": "The shot is locally complete."}],
        "completed_beat_ids": ["beat"], "incomplete_beat_ids": [], "unexpected_completed_beat_ids": [],
        "continuity_break_ids": [], "accepted_deviation_ids": [], "observation_confidence": "high",
        "uncertainties": [], "requires_user_confirmation": False,
    }
    prompt = {
        "$schema": PROMPT_SCHEMA, "schema_version": 2, "status": "compile_required", "prompt_spec_id": "self_test.spec_01",
        "project_id": "self_test", "clip_id": "clip_01", "state_revision": 1, "canon_revision": 1,
        "semantic_state_sha256": sha, "sequence_relation": "standalone", "opening_source": "planned_start",
        "parent_clip_id": None, "planned_start_snapshot_sha256": sha, "planned_end_snapshot_sha256": sha,
        "observed_source_snapshot_sha256": None, "accepted_source_media_sha256": None, "source_take_id": None,
        "source_take_review_sha256": None, "source_accepted_deviation_ids": [],
        "endpoint_states_sha256": sha, "carry_forward_motion_bindings": [],
        "completed_beat_ids": [], "reserved_future_beat_ids": [], "continuity_rule_ids": [], "motion_snapshot_sha256": sha,
        "reference_binding_ids": [], "planning_status": "planning_required", "reference_manifest_sha256": None,
        "scene_ir_sha256": None, "planning_report_sha256": None,
    }
    run = {
        "$schema": RUN_SCHEMA, "schema_version": 2, "run_id": "self_test.run_01", "project_id": "self_test",
        "clip_id": "clip_01", "state_revision": 1, "canon_revision": 1, "semantic_state_sha256": sha,
        "project_state_sha256": sha, "prompt_spec_id": "self_test.spec_01", "prompt_spec_sha256": sha,
        "execution_status": "compile_required", "result_status": "not_run_fixture", "is_synthetic_fixture": True,
        "block_reason": "v2_compiler_not_available",
    }
    return [take, prompt, run]


def self_test() -> list[str]:
    take, prompt, run = _self_test_documents()
    failures: list[str] = []
    for document in (take, prompt, run):
        if validate_document(document):
            failures.append("valid auxiliary contract failed")
    invalid = json.loads(json.dumps(run))
    invalid["provider"] = "forbidden"
    if not validate_document(invalid):
        failures.append("schema-invalid generation run passed")
    overlap = json.loads(json.dumps(take))
    overlap["incomplete_beat_ids"] = ["beat"]
    if not any(error.startswith("AUX100_") for error in validate_document(overlap)):
        failures.append("beat overlap passed")
    try:
        parse_document(b'{"value":1,"value":2}')
        failures.append("duplicate key passed")
    except InputFailure as exc:
        if exc.code != "AUX004_DUPLICATE_KEY":
            failures.append("duplicate-key diagnostic changed")
    return failures


def _read(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    try:
        with Path(path).open("rb") as handle:
            return handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise InputFailure("AUX012_READ_ERROR", "input could not be read") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="JSON files; omit or use - for stdin")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--bundle", action="store_true", help="verify cross-artifact bindings")
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        if failures:
            for failure in failures:
                print(f"ERROR AUX900_SELF_TEST: {failure}")
            return 1
        print("v2 auxiliary self-test passed.")
        return 0
    paths = args.paths or ["-"]
    if len(paths) > MAX_FILES or paths.count("-") > 1:
        print("ERROR AUX013_INPUT_COUNT: input count exceeds the bounded limit")
        return 1
    documents: list[dict[str, Any]] = []
    failed = False
    for index, path in enumerate(paths, 1):
        try:
            document = parse_document(_read(path))
            documents.append(document)
            errors = [] if args.bundle and document.get("$schema") == PROJECT_SCHEMA else validate_document(document)
        except InputFailure as exc:
            errors = [f"{exc.code}: {exc.message}"]
        for error in errors:
            print(f"ERROR document {index} {error}")
        failed = failed or bool(errors)
    if args.bundle and not failed:
        bundle_errors = verify_bundle(documents)
        for error in bundle_errors:
            print(f"ERROR bundle {error}")
        failed = bool(bundle_errors)
    if failed:
        return 1
    mode = "bundle" if args.bundle else "document"
    print(f"v2 auxiliary {mode} check passed: {len(paths)} document(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
