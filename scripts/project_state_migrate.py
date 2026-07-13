#!/usr/bin/env python3
"""Inspect, migrate, and verify legacy v6.6 project state without writing files."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

try:
    from . import project_state_v2_check as state_v2
except ImportError:  # pragma: no cover - exercised by CLI tests
    import project_state_v2_check as state_v2


MAP_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/project-state-v2-migration-map.schema.json"
REPORT_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/project-state-v2-migration-report.schema.json"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_MAP_BYTES = 8 * 1024 * 1024


def _toolchain_sha256() -> str:
    digest = hashlib.sha256()
    for label, path in (
        (b"project_state_migrate.py", Path(__file__).resolve()),
        (b"project_state_v2_check.py", Path(state_v2.__file__).resolve()),
    ):
        payload = path.read_bytes()
        digest.update(len(label).to_bytes(4, "big"))
        digest.update(label)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


TOOL_SHA256 = _toolchain_sha256()
SNAPSHOT_FIELDS = (
    "planned_start_state",
    "planned_end_state",
    "observed_start_state",
    "observed_end_state",
)
PROVIDER_TOKEN = re.compile(r"@\s*(?:image|video|audio)\s*\d+|\[(?:image|video|audio)\s*\d+\]|(?:图片|圖片|图像|圖像|视频|視頻|音频|音頻)\s*\d+", re.IGNORECASE)
MISSING_VALUE = {"presence": "missing"}


class MigrationError(state_v2.StateV2Error):
    pass


def fail(code: str, pointer: str = "/") -> None:
    raise MigrationError(code, pointer)


def safe_read(path_text: str, maximum: int) -> bytes:
    path = Path(path_text).absolute()
    try:
        before = path.lstat()
    except OSError:
        fail("MIG023_FILE_UNSAFE")
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
        fail("MIG023_FILE_UNSAFE")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        fail("MIG023_FILE_UNSAFE")
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns, opened.st_nlink)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or identity[:2] != (before.st_dev, before.st_ino):
            fail("MIG023_FILE_UNSAFE")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                fail("MIG024_RESOURCE_LIMIT")
        raw = b"".join(chunks)
        final = os.fstat(descriptor)
        final_identity = (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns, final.st_nlink)
        if identity != final_identity or len(raw) != opened.st_size:
            fail("MIG022_SOURCE_CHANGED_DURING_READ")
        return raw
    except MigrationError:
        raise
    except OSError:
        fail("MIG023_FILE_UNSAFE")
    finally:
        os.close(descriptor)


def parse(raw: bytes, maximum: int) -> Any:
    try:
        return state_v2.parse_json_bytes(raw, max_bytes=maximum)
    except state_v2.StateV2Error as exc:
        raise MigrationError(exc.code, exc.pointer) from exc


def canonical_hash(value: object) -> str:
    return state_v2.sha256_object(value)


def text_hash(value: str) -> str:
    return state_v2.sha256_text(value)


def raw_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def legacy_value_hash(value: object) -> str:
    return canonical_hash(value)


def _terminal_occurrences(value: object, pointer: str, maximum: int) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    stack: list[tuple[object, str]] = [(value, pointer)]
    while stack:
        current, current_pointer = stack.pop()
        if isinstance(current, (dict, list, str, int, float, bool)) or current is None:
            occurrences.append({"pointer": current_pointer, "value_sha256": legacy_value_hash(current), "mapped": False})
        else:
            fail("MIG002_SOURCE_CONTRACT_INVALID", current_pointer)
        if len(occurrences) > maximum:
            fail("MIG024_RESOURCE_LIMIT", pointer)
        if isinstance(current, dict):
            if current:
                for key in sorted(current, reverse=True):
                    stack.append((current[key], f"{current_pointer}/{key.replace('~', '~0').replace('/', '~1')}"))
        elif isinstance(current, list):
            if current:
                for index in reversed(range(len(current))):
                    stack.append((current[index], f"{current_pointer}/{index}"))
    return occurrences


def pointer_get(value: object, pointer: str) -> object:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/state_atom_mappings/source_pointer")
    current = value
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            fail("MIG011_STATE_ATOM_UNMAPPED", pointer)
    return current


def _v1_string(value: object, pointer: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or nonempty and not value:
        fail("MIG002_SOURCE_CONTRACT_INVALID", pointer)
    return value


def _v1_integer(value: object, pointer: str, minimum: int, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or maximum is not None and value > maximum:
        fail("MIG002_SOURCE_CONTRACT_INVALID", pointer)
    return value


def _v1_number(value: object, pointer: str, *, nullable: bool = False) -> float | int | None:
    if value is None and nullable:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        fail("MIG002_SOURCE_CONTRACT_INVALID", pointer)
    return value


def _v1_string_array(value: object, pointer: str, *, unique: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        fail("MIG002_SOURCE_CONTRACT_INVALID", pointer)
    if unique and len(value) != len(set(value)):
        fail("MIG002_SOURCE_CONTRACT_INVALID", pointer)
    return value


def source_contract(source: object) -> dict[str, Any]:
    if not isinstance(source, dict):
        fail("MIG002_SOURCE_CONTRACT_INVALID")
    if source.get("schema_version") != "6.6.0":
        fail("MIG001_SOURCE_VERSION_UNSUPPORTED", "/schema_version")
    required = {
        "schema_version", "state_revision", "project_id", "project_mode", "surface",
        "clip_budget_sec", "prompt_budget", "story", "world_bible", "reference_registry",
        "scenes", "beats", "clips", "take_history", "current_clip_id", "canon_revision", "updated_at",
    }
    if set(source) != required:
        fail("MIG002_SOURCE_CONTRACT_INVALID")
    _v1_integer(source["state_revision"], "/state_revision", 1)
    _v1_string(source["project_id"], "/project_id", nonempty=True)
    if not isinstance(source["project_mode"], str) or source["project_mode"] not in {"standalone_clip", "sequence_project"}:
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/project_mode")
    if not isinstance(source["surface"], dict):
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/surface")
    _v1_number(source["clip_budget_sec"], "/clip_budget_sec", nullable=True)
    if source["prompt_budget"] is not None:
        _v1_integer(source["prompt_budget"], "/prompt_budget", 1)
    _v1_integer(source["canon_revision"], "/canon_revision", 1)
    _v1_string(source["current_clip_id"], "/current_clip_id", nonempty=True)
    _v1_string(source["updated_at"], "/updated_at", nonempty=True)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["updated_at"]) is None:
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/updated_at")
    try:
        date.fromisoformat(source["updated_at"])
    except ValueError:
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/updated_at")
    if not isinstance(source["reference_registry"], list):
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/reference_registry")
    if len(source["reference_registry"]) > 64:
        fail("MIG024_RESOURCE_LIMIT", "/reference_registry")
    if not isinstance(source["clips"], list):
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/clips")
    if len(source["clips"]) > 1024:
        fail("MIG024_RESOURCE_LIMIT", "/clips")
    if not isinstance(source["take_history"], list):
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/take_history")
    if len(source["take_history"]) > 4096:
        fail("MIG024_RESOURCE_LIMIT", "/take_history")
    if not isinstance(source["story"], dict) or not isinstance(source["world_bible"], dict):
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/story")
    story_keys = {"logline", "story_promise", "objective", "initial_condition", "final_outcome", "target_duration_sec", "tone", "medium"}
    if set(source["story"]) != story_keys:
        fail("MIG002_SOURCE_CONTRACT_INVALID", "/story")
    for field in story_keys - {"target_duration_sec"}:
        _v1_string(source["story"][field], f"/story/{field}")
    _v1_number(source["story"]["target_duration_sec"], "/story/target_duration_sec", nullable=True)
    if not isinstance(source["scenes"], list) or not isinstance(source["beats"], list):
        fail("MIG002_SOURCE_CONTRACT_INVALID")
    if len(source["scenes"]) > 256 or len(source["beats"]) > 4096:
        fail("MIG024_RESOURCE_LIMIT", "/")
    scene_keys = {"scene_id", "scene_index", "narrative_function", "arc_position", "location", "time_of_day", "anchor_source", "max_chain_depth", "audio_plan", "assigned_clip_ids", "transition_out", "status"}
    beat_keys = {"beat_id", "description", "narrative_function", "status", "assigned_clip_id", "dependencies"}
    clip_keys = {"clip_id", "parent_clip_id", "scene_id", "sequence_index", "prompt_version", "generation_mode", "status", "narrative_job", "felt_intent", "already_happened", "this_clip_only", "reserved_for_later", "planned_start_state", "planned_end_state", "observed_start_state", "observed_end_state", "continuity_locks", "allowed_changes", "continuity_breaks", "accepted_deviations", "transition_in", "transition_out", "open_motion_vectors", "handoff_requirements", "extension_depth"}
    for index, reference in enumerate(source["reference_registry"]):
        if not isinstance(reference, dict) or set(reference) != {"tag", "role", "preserve_exact_tag"} or not isinstance(reference["tag"], str) or not reference["tag"] or not isinstance(reference["role"], str) or not reference["role"] or reference["preserve_exact_tag"] is not True:
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/reference_registry/{index}")
    for index, scene in enumerate(source["scenes"]):
        if not isinstance(scene, dict) or set(scene) != scene_keys or not isinstance(scene["anchor_source"], list) or not isinstance(scene["assigned_clip_ids"], list):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/scenes/{index}")
        _v1_string(scene["scene_id"], f"/scenes/{index}/scene_id", nonempty=True)
        _v1_integer(scene["scene_index"], f"/scenes/{index}/scene_index", 1)
        for field in ("narrative_function", "location", "time_of_day", "audio_plan", "transition_out"):
            _v1_string(scene[field], f"/scenes/{index}/{field}")
        if not isinstance(scene["arc_position"], str) or not isinstance(scene["status"], str) or scene["arc_position"] not in {"open", "rising", "turn", "climax", "release"} or scene["status"] not in {"planned", "current", "completed", "omitted", "replaced"}:
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/scenes/{index}")
        _v1_integer(scene["max_chain_depth"], f"/scenes/{index}/max_chain_depth", 0, 3)
        _v1_string_array(scene["anchor_source"], f"/scenes/{index}/anchor_source")
        _v1_string_array(scene["assigned_clip_ids"], f"/scenes/{index}/assigned_clip_ids")
    for index, beat in enumerate(source["beats"]):
        if not isinstance(beat, dict) or set(beat) != beat_keys or not isinstance(beat["dependencies"], list):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/beats/{index}")
        _v1_string(beat["beat_id"], f"/beats/{index}/beat_id", nonempty=True)
        _v1_string(beat["description"], f"/beats/{index}/description")
        _v1_string(beat["narrative_function"], f"/beats/{index}/narrative_function")
        if not isinstance(beat["status"], str) or beat["status"] not in {"planned", "current", "completed", "omitted", "replaced"} or beat["assigned_clip_id"] is not None and not isinstance(beat["assigned_clip_id"], str):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/beats/{index}")
        _v1_string_array(beat["dependencies"], f"/beats/{index}/dependencies")
    for index, clip in enumerate(source["clips"]):
        if not isinstance(clip, dict) or not clip_keys.issubset(clip) or not set(clip).issubset(clip_keys | {"source_clip_tag"}):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}")
        if "source_clip_tag" in clip and clip["source_clip_tag"] is not None and not isinstance(clip["source_clip_tag"], str):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}/source_clip_tag")
        if any(not isinstance(clip[field], str) or not clip[field] for field in ("clip_id", "scene_id", "felt_intent")) or (clip["parent_clip_id"] is not None and not isinstance(clip["parent_clip_id"], str)):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}")
        _v1_integer(clip["sequence_index"], f"/clips/{index}/sequence_index", 1)
        _v1_integer(clip["extension_depth"], f"/clips/{index}/extension_depth", 0)
        for field in ("prompt_version", "generation_mode", "narrative_job", "transition_in", "transition_out"):
            _v1_string(clip[field], f"/clips/{index}/{field}")
        if not isinstance(clip["status"], str) or clip["status"] not in {"planned", "ready", "generated", "reviewed", "accepted", "accepted_with_deviation", "repair", "rejected"}:
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}/status")
        for field in ("already_happened", "this_clip_only", "reserved_for_later"):
            _v1_string_array(clip[field], f"/clips/{index}/{field}")
        for field in ("continuity_locks", "allowed_changes", "continuity_breaks", "accepted_deviations", "open_motion_vectors", "handoff_requirements"):
            _v1_string_array(clip[field], f"/clips/{index}/{field}", unique=True)
        for field in ("planned_start_state", "planned_end_state"):
            if not isinstance(clip[field], dict):
                fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}/{field}")
        for field in ("observed_start_state", "observed_end_state"):
            if clip[field] is not None and not isinstance(clip[field], dict):
                fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{index}/{field}")
    return source


def _leaf_occurrences(source: dict[str, Any]) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []

    def record(pointer: str, value: object) -> None:
        occurrences.append({"pointer": pointer, "value_sha256": legacy_value_hash(value), "mapped": False})
        if len(occurrences) > 4096:
            fail("MIG024_RESOURCE_LIMIT", "/clips")

    for clip_index, clip in enumerate(source["clips"]):
        if not isinstance(clip, dict):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{clip_index}")
        for field in SNAPSHOT_FIELDS:
            state = clip.get(field)
            if state is None:
                continue
            if not isinstance(state, dict):
                fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{clip_index}/{field}")
            stack: list[tuple[object, str]] = [(state, f"/clips/{clip_index}/{field}")]
            state_pointer = f"/clips/{clip_index}/{field}"
            while stack:
                current, pointer = stack.pop()
                if isinstance(current, dict):
                    if not current:
                        record(pointer, current)
                        continue
                    for key in sorted(current, reverse=True):
                        if pointer == state_pointer and key == "reference_tags":
                            tags = current[key]
                            if not isinstance(tags, list) or len(tags) > 64 or any(not isinstance(tag, str) for tag in tags) or len(tags) != len(set(tags)):
                                fail("MIG002_SOURCE_CONTRACT_INVALID", f"{pointer}/reference_tags")
                            continue
                        stack.append((current[key], f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"))
                elif isinstance(current, list):
                    if not current:
                        record(pointer, current)
                        continue
                    for index in reversed(range(len(current))):
                        stack.append((current[index], f"{pointer}/{index}"))
                elif isinstance(current, (str, int, float, bool)) or current is None:
                    record(pointer, current)
                else:
                    fail("MIG011_STATE_ATOM_UNMAPPED", pointer)
    return occurrences


def _legacy_field_occurrences(source: dict[str, Any]) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for field in sorted(source):
        occurrences.extend(_terminal_occurrences(source[field], f"/{field}", 16384 - len(occurrences)))
        if len(occurrences) > 16384:
            fail("MIG024_RESOURCE_LIMIT", f"/{field}")
    for index, clip in enumerate(source["clips"]):
        if "source_clip_tag" not in clip:
            occurrences.append({"pointer": f"/clips/{index}/source_clip_tag", "value_sha256": legacy_value_hash(MISSING_VALUE), "mapped": False})
            if len(occurrences) > 16384:
                fail("MIG024_RESOURCE_LIMIT", "/clips")
    return occurrences


def inspect_source(source: dict[str, Any], source_raw_sha256: str) -> dict[str, Any]:
    id_occurrences = [{"pointer": "/project_id", "value_sha256": legacy_value_hash(source["project_id"]), "mapped": False}]
    id_occurrences.extend({"pointer": f"/scenes/{index}/scene_id", "value_sha256": legacy_value_hash(scene["scene_id"]), "mapped": False} for index, scene in enumerate(source["scenes"]))
    id_occurrences.extend({"pointer": f"/beats/{index}/beat_id", "value_sha256": legacy_value_hash(beat["beat_id"]), "mapped": False} for index, beat in enumerate(source["beats"]))
    id_occurrences.extend({"pointer": f"/clips/{index}/clip_id", "value_sha256": legacy_value_hash(clip["clip_id"]), "mapped": False} for index, clip in enumerate(source["clips"]))
    reference_occurrences: list[dict[str, Any]] = []
    for index, reference in enumerate(source["reference_registry"]):
        if not isinstance(reference, dict) or set(reference) != {"tag", "role", "preserve_exact_tag"}:
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/reference_registry/{index}")
        if not isinstance(reference["tag"], str) or not isinstance(reference["role"], str):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/reference_registry/{index}")
        reference_occurrences.append(
            {
                "legacy_registry_index": index,
                "tag_sha256": text_hash(reference["tag"]),
                "role_sha256": text_hash(reference["role"]),
                "mapped": False,
            }
        )
    motion_occurrences: list[dict[str, Any]] = []
    for clip_index, clip in enumerate(source["clips"]):
        motions = clip.get("open_motion_vectors", [])
        if not isinstance(motions, list):
            fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{clip_index}/open_motion_vectors")
        for motion_index, motion in enumerate(motions):
            if not isinstance(motion, str):
                fail("MIG002_SOURCE_CONTRACT_INVALID", f"/clips/{clip_index}/open_motion_vectors/{motion_index}")
            motion_occurrences.append(
                {
                    "clip_id_sha256": text_hash(str(clip.get("clip_id", "invalid"))),
                    "legacy_index": motion_index,
                    "value_sha256": legacy_value_hash(motion),
                    "mapped": False,
                }
            )
            if len(motion_occurrences) > 4096:
                fail("MIG024_RESOURCE_LIMIT", "/clips")
    state_leaves = _leaf_occurrences(source)
    legacy_fields = _legacy_field_occurrences(source)
    diagnostics = []
    if reference_occurrences:
        diagnostics.append({"code": "MIG005_REFERENCE_UNMAPPED", "pointer": "/reference_registry"})
    if id_occurrences:
        diagnostics.append({"code": "MIG027_ID_MAPPING_REQUIRED", "pointer": "/"})
    if state_leaves:
        diagnostics.append({"code": "MIG011_STATE_ATOM_UNMAPPED", "pointer": "/clips"})
    if motion_occurrences:
        diagnostics.append({"code": "MIG012_MOTION_BASIS_UNRESOLVED", "pointer": "/clips"})
    if legacy_fields:
        diagnostics.append({"code": "MIG025_LEGACY_DISPOSITION_REQUIRED", "pointer": "/"})
    return {
        "$schema": REPORT_SCHEMA_URI,
        "schema_version": 1,
        "status": "blocked" if diagnostics else "ready",
        "source_raw_sha256": source_raw_sha256,
        "source_project_state_sha256": canonical_hash(source),
        "reference_occurrences": reference_occurrences,
        "id_occurrences": id_occurrences,
        "state_leaf_occurrences": state_leaves,
        "motion_occurrences": motion_occurrences,
        "legacy_field_occurrences": legacy_fields,
        "diagnostics": diagnostics,
    }


def validate_map(value: object, source: dict[str, Any], source_raw_sha256: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "$schema", "schema_version", "source_raw_sha256", "source_project_state_sha256", "reference_mappings",
        "id_mappings", "state_atom_mappings", "motion_mappings", "clip_mappings", "legacy_dispositions", "reanchor_policy", "timing_policy",
    }:
        fail("MIG003_MAPPING_CONTRACT_INVALID")
    if value["$schema"] != MAP_SCHEMA_URI or value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/schema_version")
    if value["source_project_state_sha256"] != canonical_hash(source):
        fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", "/source_project_state_sha256")
    if value["source_raw_sha256"] != source_raw_sha256:
        fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", "/source_raw_sha256")
    for field, maximum in (("reference_mappings", 64), ("id_mappings", 5377), ("state_atom_mappings", 4096), ("motion_mappings", 4096), ("clip_mappings", 1024), ("legacy_dispositions", 16384)):
        if not isinstance(value[field], list) or len(value[field]) > maximum:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"/{field}")
    _validate_map_policies(value)
    _mapped_references(source, value)
    _id_mapping_index(source, value)
    _state_mapping_index(source, value)
    _motion_mapping_index(source, value)
    _clip_mapping_index(source, value)
    _validate_legacy_dispositions(source, value)
    for index, clip in enumerate(source["clips"]):
        if clip.get("source_clip_tag") is not None:
            fail("MIG010_SOURCE_CLIP_UNMAPPED", f"/clips/{index}/source_clip_tag")
    return value


def _validate_map_policies(mapping: dict[str, Any]) -> None:
    reanchor = mapping["reanchor_policy"]
    if not isinstance(reanchor, dict) or set(reanchor) != {"status", "trigger_extension_depth", "reason"}:
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/reanchor_policy")
    if reanchor["status"] == "not_selected":
        if reanchor["trigger_extension_depth"] is not None or reanchor["reason"] is not None:
            fail("MIG003_MAPPING_CONTRACT_INVALID", "/reanchor_policy")
    elif reanchor["status"] == "selected":
        if not isinstance(reanchor["trigger_extension_depth"], int) or isinstance(reanchor["trigger_extension_depth"], bool) or reanchor["trigger_extension_depth"] < 1 or not isinstance(reanchor["reason"], str) or not reanchor["reason"].strip() or len(reanchor["reason"]) > 2000:
            fail("MIG003_MAPPING_CONTRACT_INVALID", "/reanchor_policy")
    else:
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/reanchor_policy/status")
    timing = mapping["timing_policy"]
    if not isinstance(timing, dict) or set(timing) != {"mode", "status", "evidence_claim_ids", "evidence_expires_at", "block_reason"}:
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/timing_policy")
    if not isinstance(timing["mode"], str) or not isinstance(timing["status"], str) or timing["mode"] not in {"ordered_phases", "relative_beats", "surface_exact_ranges"} or not isinstance(timing["evidence_claim_ids"], list) or len(timing["evidence_claim_ids"]) > 32 or any(not isinstance(item, str) for item in timing["evidence_claim_ids"]) or len(timing["evidence_claim_ids"]) != len(set(timing["evidence_claim_ids"])):
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/timing_policy")
    if timing["mode"] == "surface_exact_ranges":
        if timing["status"] != "blocked" or timing["evidence_claim_ids"] or timing["evidence_expires_at"] is not None or not isinstance(timing["block_reason"], str) or not timing["block_reason"].strip() or len(timing["block_reason"]) > 2000:
            fail("MIG003_MAPPING_CONTRACT_INVALID", "/timing_policy")
    elif timing["status"] != "selected" or timing["evidence_claim_ids"] or timing["evidence_expires_at"] is not None or timing["block_reason"] is not None:
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/timing_policy")


def _id_mapping_index(source: dict[str, Any], mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    definitions: dict[str, dict[str, str]] = {
        "project": {"/project_id": source["project_id"]},
        "scene": {f"/scenes/{index}/scene_id": scene["scene_id"] for index, scene in enumerate(source["scenes"])},
        "beat": {f"/beats/{index}/beat_id": beat["beat_id"] for index, beat in enumerate(source["beats"])},
        "clip": {f"/clips/{index}/clip_id": clip["clip_id"] for index, clip in enumerate(source["clips"])},
    }
    result: dict[str, dict[str, str]] = {kind: {} for kind in definitions}
    seen_pointers: set[str] = set()
    target_ids: dict[str, set[str]] = {kind: set() for kind in definitions}
    expected_pointers = {pointer for records in definitions.values() for pointer in records}
    for index, record in enumerate(mapping["id_mappings"]):
        pointer = f"/id_mappings/{index}"
        if not isinstance(record, dict) or set(record) != {"entity_kind", "source_pointer", "source_value_sha256", "target_id"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        kind = record["entity_kind"]
        source_pointer = record["source_pointer"]
        if not isinstance(kind, str) or not isinstance(source_pointer, str) or len(source_pointer) > 1000 or kind not in definitions or source_pointer not in definitions[kind] or source_pointer in seen_pointers:
            fail("MIG027_ID_MAPPING_REQUIRED", pointer)
        source_id = definitions[kind][source_pointer]
        if record["source_value_sha256"] != legacy_value_hash(source_id):
            fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", pointer)
        target_id = record["target_id"]
        if not isinstance(target_id, str) or state_v2.SAFE_ID.fullmatch(target_id) is None or target_id in target_ids[kind]:
            fail("MIG028_ID_MAPPING_AMBIGUOUS", f"{pointer}/target_id")
        if source_id in result[kind]:
            fail("MIG028_ID_MAPPING_AMBIGUOUS", pointer)
        result[kind][source_id] = target_id
        target_ids[kind].add(target_id)
        seen_pointers.add(source_pointer)
    if seen_pointers != expected_pointers:
        fail("MIG027_ID_MAPPING_REQUIRED", "/id_mappings")
    return result


def _mapped_references(source: dict[str, Any], mapping: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records = mapping["reference_mappings"]
    by_index: dict[int, dict[str, Any]] = {}
    binding_ids: set[str] = set()
    tag_to_binding: dict[str, str] = {}
    for index, record in enumerate(records):
        pointer = f"/reference_mappings/{index}"
        expected = {"legacy_registry_index", "tag_sha256", "role_sha256", "binding_id", "media_type", "source_kind", "source_take_id", "media_sha256", "description"}
        if not isinstance(record, dict) or set(record) != expected:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        legacy_index = record["legacy_registry_index"]
        if not isinstance(legacy_index, int) or isinstance(legacy_index, bool) or legacy_index in by_index or not 0 <= legacy_index < len(source["reference_registry"]):
            fail("MIG006_REFERENCE_AMBIGUOUS", f"{pointer}/legacy_registry_index")
        reference = source["reference_registry"][legacy_index]
        if record["tag_sha256"] != text_hash(reference["tag"]) or record["role_sha256"] != text_hash(reference["role"]):
            fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", pointer)
        binding_id = record["binding_id"]
        if not isinstance(binding_id, str) or state_v2.SAFE_ID.fullmatch(binding_id) is None or binding_id in binding_ids:
            fail("MIG009_BINDING_ID_COLLISION", f"{pointer}/binding_id")
        if not isinstance(record["media_type"], str) or not isinstance(record["source_kind"], str) or record["media_type"] not in {"image", "video", "audio"} or record["source_kind"] not in {"user_asset", "accepted_take", "extracted_frame"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        if not isinstance(record["description"], str) or not record["description"].strip() or len(record["description"]) > 2000:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/description")
        if reference["tag"] in tag_to_binding and tag_to_binding[reference["tag"]] != binding_id:
            fail("MIG006_REFERENCE_AMBIGUOUS", pointer)
        tag_to_binding[reference["tag"]] = binding_id
        if record["source_take_id"] is not None and (not isinstance(record["source_take_id"], str) or state_v2.SAFE_ID.fullmatch(record["source_take_id"]) is None):
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/source_take_id")
        if record["media_sha256"] is not None and (not isinstance(record["media_sha256"], str) or state_v2.SHA256.fullmatch(record["media_sha256"]) is None):
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/media_sha256")
        if record["source_kind"] in {"accepted_take", "extracted_frame"} and (record["source_take_id"] is None or record["media_sha256"] is None):
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        if record["source_kind"] == "user_asset" and record["source_take_id"] is not None:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        binding_ids.add(binding_id)
        by_index[legacy_index] = record
    if set(by_index) != set(range(len(source["reference_registry"]))):
        fail("MIG005_REFERENCE_UNMAPPED", "/reference_mappings")
    assets = [
        {
            "binding_id": by_index[index]["binding_id"],
            "media_type": by_index[index]["media_type"],
            "source_kind": by_index[index]["source_kind"],
            "source_take_id": by_index[index]["source_take_id"],
            "media_sha256": by_index[index]["media_sha256"],
            "description": by_index[index]["description"],
            "status": "available" if by_index[index]["media_sha256"] is not None else "pending",
            "authority_status": "unresolved",
        }
        for index in sorted(by_index)
    ]
    return assets, tag_to_binding


def _state_mapping_index(source: dict[str, Any], mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected_pointers = {item["pointer"] for item in _leaf_occurrences(source)}
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(mapping["state_atom_mappings"]):
        pointer = f"/state_atom_mappings/{index}"
        expected = {"source_pointer", "source_value_sha256", "replacement_value", "atom_id", "owner_kind", "owner_id", "dimension", "confidence"}
        if not isinstance(record, dict) or set(record) != expected:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        source_pointer = record["source_pointer"]
        if not isinstance(source_pointer, str) or len(source_pointer) > 1000:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/source_pointer")
        if source_pointer in result:
            fail("MIG006_REFERENCE_AMBIGUOUS", f"{pointer}/source_pointer")
        raw_value = pointer_get(source, source_pointer)
        value = str(raw_value)
        if record["source_value_sha256"] != legacy_value_hash(raw_value):
            fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", pointer)
        replacement = record["replacement_value"]
        if not isinstance(replacement, str) or not replacement.strip() or len(replacement) > 20000:
            fail("MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED", f"{pointer}/replacement_value")
        comparison = unicodedata.normalize("NFKC", replacement).casefold()
        normalized_tags = [unicodedata.normalize("NFKC", reference["tag"]).casefold() for reference in source["reference_registry"]]
        if PROVIDER_TOKEN.search(comparison) or any(tag and tag in comparison for tag in normalized_tags):
            fail("MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED", f"{pointer}/replacement_value")
        for field in ("atom_id", "owner_id", "dimension"):
            if not isinstance(record[field], str) or state_v2.SAFE_ID.fullmatch(record[field]) is None:
                fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/{field}")
        if not isinstance(record["owner_kind"], str) or not isinstance(record["confidence"], str) or record["owner_kind"] not in state_v2.OWNER_KINDS or record["confidence"] not in {"low", "medium", "high", "unknown"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        result[source_pointer] = record
    if set(result) != expected_pointers:
        fail("MIG011_STATE_ATOM_UNMAPPED", "/state_atom_mappings")
    return result


def _motion_mapping_index(source: dict[str, Any], mapping: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    expected: set[tuple[str, int]] = set()
    clips_by_id = {clip["clip_id"]: clip for clip in source["clips"]}
    for clip in source["clips"]:
        expected.update((clip["clip_id"], index) for index in range(len(clip.get("open_motion_vectors", []))))
        if len(expected) > 4096:
            fail("MIG024_RESOURCE_LIMIT", "/clips")
    result: dict[tuple[str, int], dict[str, Any]] = {}
    fields = {"clip_id", "legacy_index", "value_sha256", "destination_snapshot", "basis", "motion_id", "owner_kind", "owner_id", "domain", "coordinate_frame", "description", "phase", "direction", "speed", "speed_trend", "continuity", "observability", "source_kind", "confidence", "uncertainty"}
    for index, record in enumerate(mapping["motion_mappings"]):
        pointer = f"/motion_mappings/{index}"
        if not isinstance(record, dict) or set(record) != fields:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        if not isinstance(record["clip_id"], str) or not record["clip_id"] or len(record["clip_id"]) > 20000 or not isinstance(record["legacy_index"], int) or isinstance(record["legacy_index"], bool):
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        key = (record["clip_id"], record["legacy_index"])
        if key in result or key not in expected:
            fail("MIG012_MOTION_BASIS_UNRESOLVED", pointer)
        value = clips_by_id[key[0]]["open_motion_vectors"][key[1]]
        if record["value_sha256"] != legacy_value_hash(value):
            fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", pointer)
        destination = record["destination_snapshot"]
        if destination not in SNAPSHOT_FIELDS or clips_by_id[key[0]].get(destination) is None:
            fail("MIG012_MOTION_BASIS_UNRESOLVED", f"{pointer}/destination_snapshot")
        expected_basis = "planned" if destination.startswith("planned_") else "observed"
        if record["basis"] != expected_basis:
            fail("MIG012_MOTION_BASIS_UNRESOLVED", f"{pointer}/basis")
        vector = {field_name: record[field_name] for field_name in ("motion_id", "owner_kind", "owner_id", "domain", "coordinate_frame", "description", "phase", "direction", "speed", "speed_trend", "continuity", "observability", "source_kind", "confidence", "uncertainty")}
        try:
            state_v2._validate_motion({"basis": record["basis"], "vectors": [vector]}, record["basis"], pointer, snapshot_source_kind=record["source_kind"])
        except state_v2.StateV2Error:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        result[key] = record
    if set(result) != expected:
        fail("MIG012_MOTION_BASIS_UNRESOLVED", "/motion_mappings")
    return result


def _clip_mapping_index(source: dict[str, Any], mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    clip_ids = {clip["clip_id"] for clip in source["clips"]}
    result: dict[str, dict[str, Any]] = {}
    clips_by_id = {clip["clip_id"]: clip for clip in source["clips"]}
    expected = {"clip_id", "target_status", "sequence_relation", "planned_endpoint_states", "observed_endpoint_states", "execution_readiness", "continuity_rules"}
    for index, record in enumerate(mapping["clip_mappings"]):
        pointer = f"/clip_mappings/{index}"
        if not isinstance(record, dict) or set(record) != expected or not isinstance(record.get("clip_id"), str) or not record["clip_id"] or len(record["clip_id"]) > 20000 or record["clip_id"] not in clip_ids or record["clip_id"] in result:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        source_status = clips_by_id[record["clip_id"]]["status"]
        if not isinstance(record["target_status"], str) or record["target_status"] not in {"planned", "generated", "reviewed", "accepted", "accepted_with_deviation", "repair", "rejected"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/target_status")
        expected_status = "planned" if source_status == "ready" else "reviewed" if source_status in {"accepted", "accepted_with_deviation"} else source_status
        if record["target_status"] != expected_status:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/target_status")
        for field in ("planned_endpoint_states", "observed_endpoint_states"):
            if not isinstance(record[field], list) or len(record[field]) > 512:
                fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/{field}")
            endpoint_ids: set[str] = set()
            endpoint_owners: set[tuple[str, str]] = set()
            for endpoint_index, endpoint in enumerate(record[field]):
                endpoint_pointer = f"{pointer}/{field}/{endpoint_index}"
                if not isinstance(endpoint, dict) or set(endpoint) != {"endpoint_id", "owner_kind", "owner_id", "completion_mode", "carry_forward", "description"}:
                    fail("MIG003_MAPPING_CONTRACT_INVALID", endpoint_pointer)
                if not isinstance(endpoint["endpoint_id"], str) or state_v2.SAFE_ID.fullmatch(endpoint["endpoint_id"]) is None or endpoint["endpoint_id"] in endpoint_ids or not isinstance(endpoint["owner_kind"], str) or endpoint["owner_kind"] not in state_v2.OWNER_KINDS or not isinstance(endpoint["owner_id"], str) or state_v2.SAFE_ID.fullmatch(endpoint["owner_id"]) is None or (endpoint["owner_kind"], endpoint["owner_id"]) in endpoint_owners or not isinstance(endpoint["completion_mode"], str) or endpoint["completion_mode"] not in state_v2.COMPLETION_MODES or not isinstance(endpoint["carry_forward"], bool) or not isinstance(endpoint["description"], str) or not endpoint["description"].strip() or len(endpoint["description"]) > 2000:
                    fail("MIG003_MAPPING_CONTRACT_INVALID", endpoint_pointer)
                endpoint_ids.add(endpoint["endpoint_id"])
                endpoint_owners.add((endpoint["owner_kind"], endpoint["owner_id"]))
        if not isinstance(record["execution_readiness"], str) or record["execution_readiness"] not in {"migration_review", "planning_required", "blocked"}:
            fail("MIG018_COMPILER_PROVENANCE_INCOMPLETE", pointer)
        if not isinstance(record["sequence_relation"], str) or record["sequence_relation"] not in {"standalone", "sequence_first_clip", "seamless_continuation", "intentional_next_shot", "bridge_between_known_states", "repair_tail", "reanchor_after_drift"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/sequence_relation")
        if not isinstance(record["continuity_rules"], list) or len(record["continuity_rules"]) > 512:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/continuity_rules")
        try:
            state_v2._validate_continuity_rules(record["continuity_rules"], f"{pointer}/continuity_rules")
        except state_v2.StateV2Error:
            fail("MIG003_MAPPING_CONTRACT_INVALID", f"{pointer}/continuity_rules")
        result[record["clip_id"]] = record
    if set(result) != clip_ids:
        fail("MIG003_MAPPING_CONTRACT_INVALID", "/clip_mappings")
    return result


def _authorized_disposition_targets(source: dict[str, Any], source_pointer: str) -> set[str]:
    top_level = {
        "/schema_version": "/migration_provenance/source_schema_version",
        "/state_revision": "/state_revision",
        "/project_id": "/project_id",
        "/project_mode": "/project_mode",
        "/clip_budget_sec": "/semantic_state/clip_budget_sec",
        "/prompt_budget": "/semantic_state/prompt_budget",
        "/current_clip_id": "/semantic_state/current_clip_id",
        "/canon_revision": "/canon_revision",
        "/updated_at": "/updated_at",
    }
    if source_pointer in top_level:
        return {top_level[source_pointer]}
    if source_pointer == "/story" or source_pointer.startswith("/story/") or source_pointer == "/world_bible" or source_pointer.startswith("/world_bible/"):
        return {f"/semantic_state{source_pointer}"}
    match = re.fullmatch(r"/reference_registry/(\d+)/tag", source_pointer)
    if match is not None and int(match.group(1)) < len(source["reference_registry"]):
        return {f"/semantic_state/reference_assets/{int(match.group(1))}/binding_id"}
    match = re.fullmatch(r"/scenes/(\d+)/(scene_id|scene_index|anchor_source|assigned_clip_ids|status)(/\d+)?", source_pointer)
    if match is not None and int(match.group(1)) < len(source["scenes"]):
        field = {"anchor_source": "anchor_binding_ids"}.get(match.group(2), match.group(2))
        return {f"/semantic_state/scenes/{int(match.group(1))}/{field}{match.group(3) or ''}"}
    match = re.fullmatch(r"/scenes/(\d+)/location", source_pointer)
    if match is not None and int(match.group(1)) < len(source["scenes"]):
        return {"/semantic_state/world_bible/location"}
    match = re.fullmatch(r"/beats/(\d+)/narrative_function", source_pointer)
    if match is not None and int(match.group(1)) < len(source["beats"]):
        return {f"/semantic_state/beats/{int(match.group(1))}/description"}
    match = re.fullmatch(r"/beats/(\d+)/(beat_id|description|status|assigned_clip_id|dependencies)(/\d+)?", source_pointer)
    if match is not None and int(match.group(1)) < len(source["beats"]):
        return {f"/semantic_state/beats/{int(match.group(1))}/{match.group(2)}{match.group(3) or ''}"}
    match = re.fullmatch(r"/clips/(\d+)/narrative_job", source_pointer)
    if match is not None and int(match.group(1)) < len(source["clips"]):
        clip = source["clips"][int(match.group(1))]
        return {
            f"/semantic_state/beats/{index}/description"
            for index, beat in enumerate(source["beats"])
            if beat["assigned_clip_id"] == clip["clip_id"]
        }
    match = re.fullmatch(r"/clips/(\d+)/status", source_pointer)
    if match is not None and int(match.group(1)) < len(source["clips"]):
        return {f"/semantic_state/clips/{int(match.group(1))}/status"}
    match = re.fullmatch(r"/clips/(\d+)/(clip_id|parent_clip_id|scene_id|sequence_index|felt_intent|already_happened|this_clip_only|reserved_for_later|extension_depth)(/\d+)?", source_pointer)
    if match is not None and int(match.group(1)) < len(source["clips"]):
        return {f"/semantic_state/clips/{int(match.group(1))}/{match.group(2)}{match.group(3) or ''}"}
    match = re.fullmatch(r"/clips/(\d+)/transition_in", source_pointer)
    if match is not None and int(match.group(1)) < len(source["clips"]):
        return {f"/semantic_state/clips/{int(match.group(1))}/sequence_relation"}
    return set()


def _validate_legacy_dispositions(source: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    expected = {item["pointer"]: item["value_sha256"] for item in _legacy_field_occurrences(source)}
    seen: set[str] = set()
    for index, record in enumerate(mapping["legacy_dispositions"]):
        pointer = f"/legacy_dispositions/{index}"
        if not isinstance(record, dict) or set(record) != {"source_pointer", "source_value_sha256", "disposition", "reason", "target_pointer", "target_value_sha256"}:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        source_pointer = record["source_pointer"]
        if not isinstance(source_pointer, str) or not source_pointer or len(source_pointer) > 1000 or source_pointer in seen or source_pointer not in expected or record["source_value_sha256"] != expected[source_pointer]:
            fail("MIG004_MAPPING_SOURCE_HASH_MISMATCH", pointer)
        if not isinstance(record["disposition"], str) or record["disposition"] not in {"mapped", "retired_with_reason", "blocked"} or not isinstance(record["reason"], str) or not record["reason"].strip() or len(record["reason"]) > 2000:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        authorized_targets = _authorized_disposition_targets(source, source_pointer)
        carried_semantic = bool(authorized_targets)
        retired_history = source_pointer == "/take_history" or source_pointer.startswith("/take_history/") or re.fullmatch(r"/clips/\d+/source_clip_tag", source_pointer) is not None
        if carried_semantic and record["disposition"] != "mapped":
            fail("MIG026_DISPOSITION_TARGET_MISMATCH", f"{pointer}/disposition")
        if retired_history and record["disposition"] != "retired_with_reason":
            fail("MIG026_DISPOSITION_TARGET_MISMATCH", f"{pointer}/disposition")
        if record["disposition"] == "mapped":
            if not isinstance(record["target_pointer"], str) or not record["target_pointer"].startswith("/") or len(record["target_pointer"]) > 1000 or not isinstance(record["target_value_sha256"], str) or state_v2.SHA256.fullmatch(record["target_value_sha256"]) is None:
                fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
            if record["target_pointer"] not in authorized_targets:
                fail("MIG026_DISPOSITION_TARGET_MISMATCH", f"{pointer}/target_pointer")
        elif record["target_pointer"] is not None or record["target_value_sha256"] is not None:
            fail("MIG003_MAPPING_CONTRACT_INVALID", pointer)
        if record["disposition"] == "blocked":
            fail("MIG025_LEGACY_DISPOSITION_REQUIRED", source_pointer)
        seen.add(source_pointer)
    if seen != set(expected):
        fail("MIG025_LEGACY_DISPOSITION_REQUIRED", "/legacy_dispositions")
    return mapping["legacy_dispositions"]


def _reject_provider_values(value: object, legacy_tags: list[str]) -> None:
    normalized_tags = [unicodedata.normalize("NFKC", tag).casefold() for tag in legacy_tags]
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str):
            comparison = unicodedata.normalize("NFKC", current).casefold()
            if PROVIDER_TOKEN.search(comparison) or any(tag and tag in comparison for tag in normalized_tags):
                fail("MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED", "/semantic_state")


def _snapshot(
    source: dict[str, Any], clip_index: int, clip: dict[str, Any], field: str,
    state_mappings: dict[str, dict[str, Any]], motion_mappings: dict[tuple[str, int], dict[str, Any]],
    tag_to_binding: dict[str, str], endpoint_states: list[dict[str, Any]], target_clip_id: str,
) -> dict[str, Any] | None:
    legacy = clip.get(field)
    if legacy is None:
        return None
    basis = "planned" if field.startswith("planned_") else "observed"
    prefix = f"/clips/{clip_index}/{field}"
    atom_records = [record for pointer, record in state_mappings.items() if pointer == prefix or pointer.startswith(prefix + "/")]
    atoms = []
    atom_ids: set[str] = set()
    for record in sorted(atom_records, key=lambda item: item["atom_id"]):
        if record["atom_id"] in atom_ids:
            fail("MIG009_BINDING_ID_COLLISION", prefix)
        atom_ids.add(record["atom_id"])
        value = record["replacement_value"]
        atoms.append(
            {
                "atom_id": record["atom_id"], "owner_kind": record["owner_kind"], "owner_id": record["owner_id"],
                "dimension": record["dimension"], "value": value, "value_sha256": text_hash(value), "confidence": record["confidence"],
            }
        )
    reference_tags = legacy.get("reference_tags", [])
    if not isinstance(reference_tags, list):
        fail("MIG002_SOURCE_CONTRACT_INVALID", f"{prefix}/reference_tags")
    binding_ids = []
    for index, tag in enumerate(reference_tags):
        if tag not in tag_to_binding:
            fail("MIG005_REFERENCE_UNMAPPED", f"{prefix}/reference_tags/{index}")
        binding_id = tag_to_binding[tag]
        if binding_id not in binding_ids:
            binding_ids.append(binding_id)
    vectors = []
    for key in sorted(motion_mappings):
        if key[0] != clip["clip_id"]:
            continue
        record = motion_mappings[key]
        if record["destination_snapshot"] != field:
            continue
        vectors.append({field_name: record[field_name] for field_name in ("motion_id", "owner_kind", "owner_id", "domain", "coordinate_frame", "description", "phase", "direction", "speed", "speed_trend", "continuity", "observability", "source_kind", "confidence", "uncertainty")})
    source_record = (
        {"kind": "project_plan", "take_id": None, "media_sha256": None}
        if basis == "planned"
        else {"kind": "legacy_state_description", "take_id": None, "media_sha256": None}
    )
    snapshot = {
        "snapshot_id": f"{target_clip_id}.{field}",
        "basis": basis,
        "source": source_record,
        "binding_ids": binding_ids,
        "state_atoms": atoms,
        "motion_handoff": {"basis": basis, "vectors": vectors},
        "endpoint_states": endpoint_states,
        "uncertainties": ["Migrated from legacy free-form state; confirm against accepted media."] if basis == "observed" else [],
        "requires_confirmation": basis == "observed",
    }
    snapshot["snapshot_sha256"] = canonical_hash(snapshot)
    return snapshot


def migrate(source: dict[str, Any], mapping: dict[str, Any], source_raw_sha256: str) -> dict[str, Any]:
    assets, tag_to_binding = _mapped_references(source, mapping)
    id_mappings = _id_mapping_index(source, mapping)
    state_mappings = _state_mapping_index(source, mapping)
    motion_mappings = _motion_mapping_index(source, mapping)
    clip_mappings = _clip_mapping_index(source, mapping)
    dispositions = _validate_legacy_dispositions(source, mapping)

    def rewrite_id(kind: str, value: str | None, pointer: str) -> str | None:
        if value is None:
            return None
        rewritten = id_mappings[kind].get(value)
        if rewritten is None:
            fail("MIG027_ID_MAPPING_REQUIRED", pointer)
        return rewritten

    project_id = rewrite_id("project", source["project_id"], "/project_id")
    scenes = []
    for index, scene in enumerate(source["scenes"]):
        anchors = []
        for anchor_index, tag in enumerate(scene.get("anchor_source", [])):
            if tag not in tag_to_binding:
                fail("MIG005_REFERENCE_UNMAPPED", f"/scenes/{index}/anchor_source/{anchor_index}")
            anchors.append(tag_to_binding[tag])
        scenes.append(
            {"scene_id": rewrite_id("scene", scene["scene_id"], f"/scenes/{index}/scene_id"), "scene_index": scene["scene_index"], "anchor_binding_ids": anchors, "assigned_clip_ids": [rewrite_id("clip", clip_id, f"/scenes/{index}/assigned_clip_ids") for clip_id in scene["assigned_clip_ids"]], "status": scene["status"]}
        )
    clips = []
    for clip_index, legacy in enumerate(source["clips"]):
        clip_map = clip_mappings[legacy["clip_id"]]
        target_clip_id = rewrite_id("clip", legacy["clip_id"], f"/clips/{clip_index}/clip_id")
        if "source_clip_tag" in legacy and legacy["source_clip_tag"] is not None:
            fail("MIG010_SOURCE_CLIP_UNMAPPED", f"/clips/{clip_index}/source_clip_tag")
        planned_start = _snapshot(source, clip_index, legacy, "planned_start_state", state_mappings, motion_mappings, tag_to_binding, [], target_clip_id)
        planned_end = _snapshot(source, clip_index, legacy, "planned_end_state", state_mappings, motion_mappings, tag_to_binding, clip_map["planned_endpoint_states"], target_clip_id)
        observed_start = _snapshot(source, clip_index, legacy, "observed_start_state", state_mappings, motion_mappings, tag_to_binding, [], target_clip_id)
        observed_end = _snapshot(source, clip_index, legacy, "observed_end_state", state_mappings, motion_mappings, tag_to_binding, clip_map["observed_endpoint_states"], target_clip_id)
        clips.append(
            {
                "clip_id": target_clip_id, "parent_clip_id": rewrite_id("clip", legacy["parent_clip_id"], f"/clips/{clip_index}/parent_clip_id"), "scene_id": rewrite_id("scene", legacy["scene_id"], f"/clips/{clip_index}/scene_id"),
                "sequence_index": legacy["sequence_index"], "status": clip_map["target_status"], "accepted_deviation_ids": [], "sequence_relation": clip_map["sequence_relation"],
                "felt_intent": legacy["felt_intent"], "already_happened": [rewrite_id("beat", beat_id, f"/clips/{clip_index}/already_happened") for beat_id in legacy["already_happened"]],
                "this_clip_only": [rewrite_id("beat", beat_id, f"/clips/{clip_index}/this_clip_only") for beat_id in legacy["this_clip_only"]], "reserved_for_later": [rewrite_id("beat", beat_id, f"/clips/{clip_index}/reserved_for_later") for beat_id in legacy["reserved_for_later"]],
                "planned_start_snapshot": planned_start, "planned_end_snapshot": planned_end,
                "observed_start_snapshot": observed_start, "observed_end_snapshot": observed_end,
                "continuity_rules": clip_map["continuity_rules"],
                "planning_link": {"status": "planning_required", "binding_ids": planned_start["binding_ids"], "resolved_binding_proofs": [], "reference_manifest_sha256": None, "scene_ir_sha256": None, "planning_report_sha256": None},
                "execution_readiness": clip_map["execution_readiness"], "compile_required": True, "extension_depth": legacy["extension_depth"],
            }
        )
    semantic = {
        "clip_budget_sec": source["clip_budget_sec"], "prompt_budget": source["prompt_budget"], "story": source["story"],
        "world_bible": source["world_bible"], "reanchor_policy": mapping["reanchor_policy"], "timing_policy": mapping["timing_policy"], "reference_assets": assets, "scenes": scenes,
        "beats": [{"beat_id": rewrite_id("beat", beat["beat_id"], f"/beats/{index}/beat_id"), "description": beat["description"], "status": beat["status"], "assigned_clip_id": rewrite_id("clip", beat["assigned_clip_id"], f"/beats/{index}/assigned_clip_id"), "dependencies": [rewrite_id("beat", dependency, f"/beats/{index}/dependencies") for dependency in beat["dependencies"]]} for index, beat in enumerate(source["beats"])],
        "clips": clips, "current_clip_id": rewrite_id("clip", source["current_clip_id"], "/current_clip_id"),
    }
    result = {
        "$schema": state_v2.SCHEMA_URI, "schema_version": 2, "project_id": project_id, "project_mode": source["project_mode"],
        "state_revision": source["state_revision"], "canon_revision": source["canon_revision"], "semantic_state": semantic,
        "semantic_state_sha256": canonical_hash({"project_id": project_id, "state_revision": source["state_revision"], "canon_revision": source["canon_revision"], "semantic_state": semantic}),
        "migration_provenance": {"status": "migrated", "source_schema_version": source["schema_version"], "source_raw_sha256": source_raw_sha256, "source_canonical_sha256": canonical_hash(source), "migration_map_sha256": canonical_hash(mapping), "migration_tool_sha256": TOOL_SHA256},
        "updated_at": source["updated_at"],
    }
    for disposition in dispositions:
        if disposition["disposition"] != "mapped":
            continue
        target = pointer_get(result, disposition["target_pointer"])
        if legacy_value_hash(target) != disposition["target_value_sha256"]:
            fail("MIG026_DISPOSITION_TARGET_MISMATCH", disposition["target_pointer"])
    _reject_provider_values(result["semantic_state"], [reference["tag"] for reference in source["reference_registry"]])
    try:
        return state_v2.validate_project_state(result)
    except state_v2.StateV2Error as exc:
        fail("MIG020_V2_STATE_INVALID", exc.pointer)


def verify(source: dict[str, Any], mapping: dict[str, Any], candidate: object, source_raw_sha256: str) -> None:
    expected = migrate(source, mapping, source_raw_sha256)
    try:
        checked = state_v2.validate_project_state(candidate)
    except state_v2.StateV2Error as exc:
        fail("MIG020_V2_STATE_INVALID", exc.pointer)
    if state_v2.canonical_json(checked) != state_v2.canonical_json(expected):
        fail("MIG021_STATE_HASH_MISMATCH")


def _self_test() -> None:
    duplicate = b'{"schema_version":"6.6.0","schema_version":"6.6.0"}'
    try:
        parse(duplicate, MAX_SOURCE_BYTES)
    except MigrationError as exc:
        if exc.code != "JSON_DUPLICATE_KEY":
            fail("SELF_TEST_FAILED")
    else:
        fail("SELF_TEST_FAILED")
    if canonical_hash({"b": 2, "a": 1}) != hashlib.sha256(b'{"a":1,"b":2}\n').hexdigest():
        fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-destructive project-state-v2 migration; canonical output is stdout-only.")
    subparsers = parser.add_subparsers(dest="command")
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("source")
    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("source")
    migrate_parser.add_argument("--map", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("source")
    verify_parser.add_argument("candidate")
    verify_parser.add_argument("--map", required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("project state migration self-test passed")
            return 0
        if args.command is None:
            parser.error("a command is required")
        source_raw = safe_read(args.source, MAX_SOURCE_BYTES)
        source_raw_sha256 = raw_hash(source_raw)
        source = source_contract(parse(source_raw, MAX_SOURCE_BYTES))
        if args.command == "inspect":
            output = inspect_source(source, source_raw_sha256)
        else:
            mapping = validate_map(parse(safe_read(args.map, MAX_MAP_BYTES), MAX_MAP_BYTES), source, source_raw_sha256)
            if args.command == "migrate":
                output = migrate(source, mapping, source_raw_sha256)
            else:
                candidate = parse(safe_read(args.candidate, state_v2.MAX_INPUT_BYTES), state_v2.MAX_INPUT_BYTES)
                verify(source, mapping, candidate, source_raw_sha256)
                output = {"status": "verified", "source_raw_sha256": source_raw_sha256, "source_project_state_sha256": canonical_hash(source), "project_state_v2_sha256": canonical_hash(candidate)}
        sys.stdout.buffer.write(state_v2.canonical_json(output))
        sys.stdout.buffer.flush()
    except (MigrationError, state_v2.StateV2Error) as exc:
        print(f"project-state-migrate error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        print("project-state-migrate error: MIG002_SOURCE_CONTRACT_INVALID at /", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
