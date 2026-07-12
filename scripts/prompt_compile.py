#!/usr/bin/env python3
"""Compile one validated semantic plan into paired English and zh-Hans prompts.

The compiler accepts a binding-only surface input and constructs all prose
itself.  Both locales consume one surface-independent prompt program; the
selected profile sees only typed text/binding segments.  V7-07 remains an
offline, candidate-preview contract and does not prove translation quality or
model behavior.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

try:  # Support both ``python scripts/...`` and package imports.
    from . import reference_planner
    from . import render_surface_bindings as bindings
    from . import scene_ir_check
    from . import semantic_lint
except ImportError:  # pragma: no cover - exercised by CLI tests
    import reference_planner
    import render_surface_bindings as bindings
    import scene_ir_check
    import semantic_lint


BINDING_SET_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/surface-binding-set.schema.json"
)
RENDER_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/prompt-render.schema.json"
)
REQUEST_KEYS = {
    "schema_version",
    "reference_manifest",
    "scene_ir",
    "surface_binding_set",
    "realization_catalog",
}
BINDING_SET_KEYS = {"$schema", "schema_version", "profile_id", "operation", "bindings"}
MAX_PROMPT_CHARS = 20_000
MAX_TYPED_SEGMENTS = 256
COMPILER_SHA256 = bindings.sha256_bytes(Path(__file__).resolve().read_bytes())
COMPILER_TOOLCHAIN_COMPONENTS = {
    "prompt_compile.py": COMPILER_SHA256,
    "reference_planner.py": bindings.sha256_bytes(
        Path(reference_planner.__file__).resolve().read_bytes()
    ),
    "render_surface_bindings.py": bindings.sha256_bytes(
        Path(bindings.__file__).resolve().read_bytes()
    ),
    "scene_ir_check.py": bindings.sha256_bytes(
        Path(scene_ir_check.__file__).resolve().read_bytes()
    ),
    "semantic_lint.py": bindings.sha256_bytes(
        Path(semantic_lint.__file__).resolve().read_bytes()
    ),
}
COMPILER_TOOLCHAIN_SHA256 = bindings.sha256_bytes(
    bindings.canonical_json(COMPILER_TOOLCHAIN_COMPONENTS)
)
ENTITY_BACKED_TARGET_KINDS = {
    "character",
    "product",
    "object",
    "environment",
    "text_logo",
}


@dataclass(frozen=True)
class LocalSemanticAtom:
    semantic_key: str
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class AnnotatedText:
    value: str
    atoms: tuple[LocalSemanticAtom, ...] = ()


@dataclass(frozen=True)
class ResolvedSemanticAtom:
    semantic_unit_id: str
    semantic_key: str
    value: str
    segment_index: int
    start: int
    end: int

DIMENSIONS = {
    "en": {
        "identity": "identity",
        "face_detail": "face detail",
        "wardrobe": "wardrobe",
        "product_object_geometry": "geometry",
        "environment": "environment",
        "visual_style": "visual style",
        "opening_state": "visible opening state",
        "opening_composition": "opening composition",
        "subject_motion": "subject motion",
        "camera_motion": "camera motion",
        "timing_rhythm": "timing and rhythm",
        "audio_voice": "audio and voice",
        "endpoint": "settled final state",
        "endpoint_framing": "end framing",
        "text_logo_treatment": "text and logo treatment",
    },
    "zh-Hans": {
        "identity": "主体身份",
        "face_detail": "面部细节",
        "wardrobe": "服装",
        "product_object_geometry": "几何形状",
        "environment": "环境",
        "visual_style": "视觉风格",
        "opening_state": "可见的初始状态",
        "opening_composition": "开场构图",
        "subject_motion": "主体动作",
        "camera_motion": "镜头运动",
        "timing_rhythm": "时序与节奏",
        "audio_voice": "声音与人声",
        "endpoint": "稳定的最终状态",
        "endpoint_framing": "结束构图",
        "text_logo_treatment": "文字与标志处理",
    },
}
CAMERA_KINDS = {
    "en": {
        "locked": "locked off",
        "push_in": "push-in",
        "pull_out": "pull-out",
        "pan": "pan",
        "tilt": "tilt",
        "tracking": "tracking move",
        "orbit": "orbit",
        "crane": "crane move",
        "dolly": "dolly move",
        "handheld": "controlled handheld move",
    },
    "zh-Hans": {
        "locked": "固定机位",
        "push_in": "推镜",
        "pull_out": "拉镜",
        "pan": "横摇",
        "tilt": "纵摇",
        "tracking": "跟拍",
        "orbit": "弧形绕摄",
        "crane": "升降镜头",
        "dolly": "轨道移动",
        "handheld": "受控手持镜头",
    },
}
TEMPORAL = {
    "en": {
        "at_initial_state": "at the initial state",
        "on_trigger": "at the trigger",
        "during_motion": "during the motion",
        "on_contact_or_state_change": "at the described contact or state change",
        "during_response": "during the response",
        "during_follow_through": "during follow-through",
        "at_endpoint": "on reaching the final state",
        "continuous": "throughout the shot",
    },
    "zh-Hans": {
        "at_initial_state": "初始状态时",
        "on_trigger": "触发时",
        "during_motion": "动作过程中",
        "on_contact_or_state_change": "发生上述接触或状态变化时",
        "during_response": "响应过程中",
        "during_follow_through": "后续动作中",
        "at_endpoint": "到达最终状态时",
        "continuous": "贯穿整个镜头",
    },
}
AUDIO_FUNCTIONS = {
    "en": {
        "sound_effect": "sound effect",
        "ambience": "ambience",
        "music": "music",
        "rhythm": "rhythm",
        "silence": "deliberate silence",
    },
    "zh-Hans": {
        "sound_effect": "音效",
        "ambience": "环境声",
        "music": "音乐",
        "rhythm": "节奏",
        "silence": "有意保持静音",
    },
}
PHASE_PREFIX = {
    "en": {
        "initial_state": "Initially, ",
        "trigger": "From that initial state, ",
        "motion_path": "As that motion continues, ",
        "contact_or_state_change": "Then, ",
        "primary_response": "As a result, ",
        "secondary_response": "Next, ",
        "follow_through": "Afterward, ",
        "settled_endpoint": "Finally, ",
    },
    "zh-Hans": {
        "initial_state": "初始时，",
        "trigger": "从该初始状态起，",
        "motion_path": "随着该动作继续，",
        "contact_or_state_change": "随后，",
        "primary_response": "因此，",
        "secondary_response": "接着，",
        "follow_through": "之后，",
        "settled_endpoint": "最终，",
    },
}


class PromptCompileError(semantic_lint.SemanticLintError):
    """Stable, non-echoing paired-render failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise PromptCompileError(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _validate_binding_set(value: object) -> dict[str, Any]:
    data = _object(value, BINDING_SET_KEYS, "/surface_binding_set")
    if (
        data["$schema"] != BINDING_SET_SCHEMA_URI
        or data["schema_version"] != 1
        or not bindings._is_int(data["schema_version"])
        or not isinstance(data["profile_id"], str)
        or not isinstance(data["operation"], str)
        or not isinstance(data["bindings"], list)
        or not 1 <= len(data["bindings"]) <= 64
    ):
        _fail("COMPILE001_REQUEST_CONTRACT_INVALID", "/surface_binding_set")
    for index, binding in enumerate(data["bindings"]):
        if isinstance(binding, dict) and "prompt_visible_handle" in binding:
            semantic_lint.validate_opaque_handle_payload(
                binding["prompt_visible_handle"],
                f"/surface_binding_set/bindings/{index}/prompt_visible_handle",
            )
    return data


def _carrier_plan(binding_set: dict[str, Any]) -> dict[str, Any]:
    if binding_set["operation"] == "first_last_frame":
        segments: list[dict[str, Any]] = [
            {"kind": "text", "value": "Structured media roles are supplied outside prompt text."}
        ]
    else:
        segments = []
        for index, binding in enumerate(binding_set["bindings"]):
            binding_id = binding.get("binding_id") if isinstance(binding, dict) else None
            segments.append({"kind": "binding", "binding_id": binding_id})
            segments.append(
                {
                    "kind": "text",
                    "value": "." if index == len(binding_set["bindings"]) - 1 else "; ",
                }
            )
    return {
        "$schema": bindings.PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": binding_set["profile_id"],
        "operation": binding_set["operation"],
        "segments": segments,
        "bindings": binding_set["bindings"],
    }


def _resolve_entity_text(
    value: str,
    *,
    locale: str,
    catalog: dict[str, dict[str, str]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        entity_id = match.group(1)
        try:
            return catalog[f"entity.{entity_id}.label"][locale]
        except KeyError:
            _fail("PRM004_ENTITY_AMBIGUOUS", "/realization_catalog/entries")
    return semantic_lint.ENTITY_TOKEN.sub(replace, value)


def _catalog_value(
    catalog: dict[str, dict[str, str]],
    key: str,
    locale: str,
) -> AnnotatedText:
    try:
        raw = catalog[key][locale]
    except KeyError:
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/entries")
    chunks: list[str] = []
    entity_spans: dict[str, tuple[str, int, int]] = {}
    cursor = 0
    length = 0
    for match in semantic_lint.ENTITY_TOKEN.finditer(raw):
        prefix = raw[cursor:match.start()]
        chunks.append(prefix)
        length += len(prefix)
        entity_id = match.group(1)
        entity_key = f"entity.{entity_id}.label"
        try:
            label = catalog[entity_key][locale]
        except KeyError:
            _fail("PRM004_ENTITY_AMBIGUOUS", "/realization_catalog/entries")
        start = length
        chunks.append(label)
        length += len(label)
        entity_spans[entity_id] = (label, start, length)
        cursor = match.end()
    chunks.append(raw[cursor:])
    resolved = "".join(chunks)
    if key.startswith("event."):
        category = "event"
    elif ".camera." in key:
        category = "camera"
    elif key.startswith("audio."):
        category = "audio"
    else:
        category = "invariant"
    checked = semantic_lint.validate_composed_text(
        resolved,
        f"/resolved_catalog/{locale}/{key}",
        locale=locale,
        category=category,
        language_view=raw,
    )
    atoms = [LocalSemanticAtom(key, checked, 0, len(checked))]
    for entity_id in sorted(entity_spans):
        label, start, end = entity_spans[entity_id]
        atoms.append(
            LocalSemanticAtom(f"entity.{entity_id}.label", label, start, end)
        )
    return AnnotatedText(checked, tuple(atoms))


def _target_label(
    target_id: str,
    target_kind: str,
    locale: str,
    catalog: dict[str, dict[str, str]],
) -> AnnotatedText:
    entity_key = f"entity.{target_id}.label"
    if target_kind in ENTITY_BACKED_TARGET_KINDS and entity_key in catalog:
        label = catalog[entity_key][locale]
        return AnnotatedText(
            label,
            (LocalSemanticAtom(entity_key, label, 0, len(label)),),
        )
    if locale == "en":
        label = {
            "character": "this character",
            "product": "this product",
            "object": "this object",
            "environment": "this environment",
            "shot": "this shot",
            "audio": "this audio event",
            "text_logo": "this text or logo element",
        }[target_kind]
        return AnnotatedText(label)
    label = {
        "character": "此角色",
        "product": "此产品",
        "object": "此物体",
        "environment": "此环境",
        "shot": "本镜头",
        "audio": "此声音事件",
        "text_logo": "此文字或标志元素",
    }[target_kind]
    return AnnotatedText(label)


def _concat_annotated(*values: str | AnnotatedText) -> AnnotatedText:
    chunks: list[str] = []
    atoms: list[LocalSemanticAtom] = []
    length = 0
    for item in values:
        annotated = item if isinstance(item, AnnotatedText) else AnnotatedText(item)
        chunks.append(annotated.value)
        atoms.extend(
            LocalSemanticAtom(
                atom.semantic_key,
                atom.value,
                length + atom.start,
                length + atom.end,
            )
            for atom in annotated.atoms
        )
        length += len(annotated.value)
    return AnnotatedText("".join(chunks), tuple(atoms))


def _append_annotated_text(
    segments: list[dict[str, Any]],
    semantic_atoms: list[ResolvedSemanticAtom],
    value: str | AnnotatedText,
    semantic_unit_id: str | None = None,
) -> None:
    annotated = value if isinstance(value, AnnotatedText) else AnnotatedText(value)
    if not annotated.value:
        return
    if segments and segments[-1]["kind"] == "text":
        segment_index = len(segments) - 1
        start = len(segments[-1]["value"])
        segments[-1]["value"] += annotated.value
    else:
        segment_index = len(segments)
        start = 0
        segments.append({"kind": "text", "value": annotated.value})
    semantic_atoms.extend(
        ResolvedSemanticAtom(
            semantic_unit_id or "",
            atom.semantic_key,
            atom.value,
            segment_index,
            start + atom.start,
            start + atom.end,
        )
        for atom in annotated.atoms
    )


def _join_terms(values: list[str], locale: str) -> str:
    if locale == "zh-Hans":
        return "、".join(values)
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return " and ".join(values)
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _join_alternatives(values: list[str], locale: str) -> str:
    if len(values) == 1:
        return values[0]
    if locale == "zh-Hans":
        return "或".join(values) if len(values) == 2 else f"{'、'.join(values[:-1])}或{values[-1]}"
    if len(values) == 2:
        return " or ".join(values)
    return f"{', '.join(values[:-1])}, or {values[-1]}"


def _validate_semantic_atom_coverage(
    segments: list[dict[str, Any]],
    semantic_atoms: list[ResolvedSemanticAtom],
    semantic_unit_ids: list[str],
    locale: str,
) -> None:
    """Bind every resolved catalog value to one exact authored-text slice."""

    primary_spans: dict[int, list[tuple[int, int]]] = {}
    entity_spans: dict[tuple[int, str], list[tuple[int, int]]] = {}
    unit_indexes = {
        unit_id: index for index, unit_id in enumerate(semantic_unit_ids)
    }
    segment_start_units: list[int] = []
    current_unit = 0
    for segment in segments:
        segment_start_units.append(current_unit)
        if segment.get("kind") == "text":
            current_unit += segment["value"].count("\n")
    for index, atom in enumerate(semantic_atoms):
        if (
            not isinstance(atom, ResolvedSemanticAtom)
            or not 0 <= atom.segment_index < len(segments)
            or segments[atom.segment_index].get("kind") != "text"
            or not 0 <= atom.start < atom.end <= len(
                segments[atom.segment_index].get("value", "")
            )
            or segments[atom.segment_index]["value"][atom.start:atom.end]
            != atom.value
            or atom.semantic_unit_id not in unit_indexes
            or segment_start_units[atom.segment_index]
            + segments[atom.segment_index]["value"][:atom.start].count("\n")
            != unit_indexes[atom.semantic_unit_id]
            or "\n" in segments[atom.segment_index]["value"][atom.start:atom.end]
        ):
            _fail(
                "PARITY001_SEMANTIC_TRACE_MISMATCH",
                f"/renders/{locale}/resolved_semantic_atoms/{index}",
            )
        if atom.semantic_key.startswith("entity."):
            spans = entity_spans.setdefault(
                (atom.segment_index, atom.semantic_unit_id),
                [],
            )
            if any(
                max(atom.start, start) < min(atom.end, end)
                for start, end in spans
            ):
                _fail(
                    "PARITY001_SEMANTIC_TRACE_MISMATCH",
                    f"/renders/{locale}/resolved_semantic_atoms/{index}",
                )
            spans.append((atom.start, atom.end))
        else:
            spans = primary_spans.setdefault(atom.segment_index, [])
            if any(
                max(atom.start, start) < min(atom.end, end)
                for start, end in spans
            ):
                _fail(
                    "PARITY001_SEMANTIC_TRACE_MISMATCH",
                    f"/renders/{locale}/resolved_semantic_atoms/{index}",
                )
            spans.append((atom.start, atom.end))


def _validate_semantic_unit_text(
    segments: list[dict[str, Any]],
    semantic_unit_ids: list[str],
    locale: str,
) -> None:
    """Require one nonblank authored clause for every ordered prompt unit."""

    authored = "".join(
        segment["value"] for segment in segments if segment["kind"] == "text"
    )
    clauses = authored.split("\n")
    if len(clauses) != len(semantic_unit_ids) or any(
        not clause.strip() for clause in clauses
    ):
        _fail("PARITY002_LOCALIZED_UNIT_ORDER_MISMATCH", f"/renders/{locale}")


def _public_semantic_atoms(
    segments: list[dict[str, Any]],
    semantic_atoms: list[ResolvedSemanticAtom],
) -> list[dict[str, str | int]]:
    """Expose UTF-8 byte spans and hashes without duplicating catalog prose."""

    utf8_offsets: dict[int, list[int]] = {}
    for atom in semantic_atoms:
        if atom.segment_index in utf8_offsets:
            continue
        text = segments[atom.segment_index]["value"]
        offsets = [0]
        for character in text:
            offsets.append(offsets[-1] + len(character.encode("utf-8")))
        utf8_offsets[atom.segment_index] = offsets
    return [
        {
            "semantic_key": atom.semantic_key,
            "semantic_unit_id": atom.semantic_unit_id,
            "segment_index": atom.segment_index,
            "start_utf8_byte": utf8_offsets[atom.segment_index][atom.start],
            "end_utf8_byte": utf8_offsets[atom.segment_index][atom.end],
            "value_sha256": bindings.sha256_bytes(atom.value.encode("utf-8")),
        }
        for atom in semantic_atoms
    ]


def _validate_semantic_atoms_against_catalog(
    semantic_atoms: list[ResolvedSemanticAtom],
    catalog: dict[str, dict[str, str]],
    locale: str,
) -> None:
    """Prevent provenance metadata from substituting text from another key."""

    for index, atom in enumerate(semantic_atoms):
        try:
            raw = catalog[atom.semantic_key][locale]
        except KeyError:
            _fail(
                "PARITY001_SEMANTIC_TRACE_MISMATCH",
                f"/renders/{locale}/resolved_semantic_atoms/{index}",
            )
        expected = (
            raw
            if atom.semantic_key.startswith("entity.")
            else _resolve_entity_text(raw, locale=locale, catalog=catalog)
        )
        if atom.value != expected:
            _fail(
                "PARITY001_SEMANTIC_TRACE_MISMATCH",
                f"/renders/{locale}/resolved_semantic_atoms/{index}",
            )


def _expected_semantic_key_trace(
    program: dict[str, Any],
    manifest: dict[str, Any],
    catalog: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    """Derive the complete locale-independent catalog trace from source contracts."""

    target_order = {
        item["target_id"]: index for index, item in enumerate(manifest["targets"])
    }
    target_by_id = {item["target_id"]: item for item in manifest["targets"]}
    assignments_by_asset: dict[str, list[dict[str, Any]]] = {
        asset_id: [] for asset_id in manifest["selection_order"]
    }
    for assignment in manifest["authority_assignments"]:
        assignments_by_asset[assignment["winner_asset_id"]].append(assignment)

    trace: list[tuple[str, str]] = []

    def add_catalog_key(unit_id: str, key: str) -> None:
        trace.append((unit_id, key))
        try:
            raw = catalog[key]["en"]
        except KeyError:
            _fail("PARITY001_SEMANTIC_TRACE_MISMATCH", "/prompt_program/units")
        trace.extend(
            (unit_id, f"entity.{entity_id}.label")
            for entity_id in sorted(
                {
                    match.group(1)
                    for match in semantic_lint.ENTITY_TOKEN.finditer(raw)
                }
            )
        )

    for unit in program["units"]:
        if unit["emission"] != "prompt":
            continue
        kind = unit["kind"]
        unit_id = unit["unit_id"]
        if kind == "authority":
            asset_id = unit["binding_ids"][0]
            rows = sorted(
                assignments_by_asset[asset_id],
                key=lambda row: (
                    target_order[row["target_id"]],
                    reference_planner.DIMENSIONS.index(row["dimension"]),
                ),
            )
            for target_id in dict.fromkeys(row["target_id"] for row in rows):
                key = f"entity.{target_id}.label"
                if (
                    target_by_id[target_id]["target_kind"]
                    in ENTITY_BACKED_TARGET_KINDS
                    and key in catalog
                ):
                    trace.append((unit_id, key))
        elif kind == "event":
            add_catalog_key(
                unit_id,
                f"event.{unit['event_ids'][0]}.visible_state_change"
            )
        elif kind == "camera":
            shot_id = unit["source_ids"][0]
            fields = (
                ("path", "speed", "subject_relationship")
                if manifest["operation"] == "first_last_frame"
                else (
                    "start_framing",
                    "path",
                    "speed",
                    "subject_relationship",
                    "endpoint_framing",
                )
            )
            for field in fields:
                add_catalog_key(unit_id, f"shot.{shot_id}.camera.{field}")
        elif kind == "audio":
            add_catalog_key(
                unit_id,
                f"audio.{unit['source_ids'][0]}.description",
            )
        elif kind == "invariant":
            add_catalog_key(
                unit_id,
                f"invariant.{unit['source_ids'][0]}.description",
            )
    return trace


def _request_carried_records(
    manifest: dict[str, Any],
    scene: dict[str, Any],
    binding_set: dict[str, Any],
) -> list[dict[str, str]]:
    """Describe static semantics assigned to structured frame roles, not prose."""

    if manifest["operation"] != "first_last_frame":
        return []
    bindings_by_role = {
        binding["structured_role"]: binding["binding_id"]
        for binding in binding_set["bindings"]
    }
    shot = scene["shots"][0]
    events_by_phase = {event["phase"]: event for event in shot["events"]}
    initial_id = events_by_phase["initial_state"]["event_id"]
    endpoint_id = events_by_phase["settled_endpoint"]["event_id"]
    shot_id = shot["shot_id"]
    return [
        {
            "semantic_unit_id": f"event.{initial_id}",
            "semantic_key": f"event.{initial_id}.visible_state_change",
            "binding_id": bindings_by_role["first_frame"],
            "structured_role": "first_frame",
        },
        {
            "semantic_unit_id": f"camera.{shot_id}",
            "semantic_key": f"shot.{shot_id}.camera.start_framing",
            "binding_id": bindings_by_role["first_frame"],
            "structured_role": "first_frame",
        },
        {
            "semantic_unit_id": f"event.{endpoint_id}",
            "semantic_key": f"event.{endpoint_id}.visible_state_change",
            "binding_id": bindings_by_role["last_frame"],
            "structured_role": "last_frame",
        },
        {
            "semantic_unit_id": f"camera.{shot_id}",
            "semantic_key": f"shot.{shot_id}.camera.endpoint_framing",
            "binding_id": bindings_by_role["last_frame"],
            "structured_role": "last_frame",
        },
    ]


def _expected_binding_unit_trace(
    program: dict[str, Any],
    binding_set: dict[str, Any],
) -> list[dict[str, str]]:
    prompt_visible = {
        binding["binding_id"]
        for binding in binding_set["bindings"]
        if "structured_role" not in binding
    }
    return [
        {"semantic_unit_id": unit["unit_id"], "binding_id": binding_id}
        for unit in program["units"]
        if unit["emission"] == "prompt" and unit["kind"] == "authority"
        for binding_id in unit["binding_ids"]
        if binding_id in prompt_visible
    ]


def _binding_unit_trace(
    segments: list[dict[str, Any]],
    semantic_unit_ids: list[str],
    locale: str,
) -> list[dict[str, str]]:
    """Map each binding segment to its newline-delimited semantic unit."""

    unit_index = 0
    trace: list[dict[str, str]] = []
    for segment in segments:
        if segment["kind"] == "text":
            unit_index += segment["value"].count("\n")
            continue
        if unit_index >= len(semantic_unit_ids):
            _fail("PRM009_BINDING_CORE_MISMATCH", f"/renders/{locale}/typed_segments")
        trace.append(
            {
                "semantic_unit_id": semantic_unit_ids[unit_index],
                "binding_id": segment["binding_id"],
            }
        )
    return trace


def _render_unit_segments(
    *,
    locale: str,
    program: dict[str, Any],
    manifest: dict[str, Any],
    scene: dict[str, Any],
    binding_set: dict[str, Any],
    catalog: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str], list[ResolvedSemanticAtom]]:
    target_by_id = {item["target_id"]: item for item in manifest["targets"]}
    target_order = {
        item["target_id"]: index for index, item in enumerate(manifest["targets"])
    }
    binding_by_id = {item["binding_id"]: item for item in binding_set["bindings"]}
    assignments_by_asset: dict[str, list[dict[str, Any]]] = {
        asset_id: [] for asset_id in manifest["selection_order"]
    }
    for assignment in manifest["authority_assignments"]:
        assignments_by_asset[assignment["winner_asset_id"]].append(assignment)
    event_by_id = {
        event["event_id"]: event for shot in scene["shots"] for event in shot["events"]
    }
    shot_by_id = {item["shot_id"]: item for item in scene["shots"]}
    audio_by_id = {item["audio_event_id"]: item for item in scene["audio_events"]}
    invariant_by_id = {item["invariant_id"]: item for item in scene["requested_invariants"]}

    clauses: list[list[dict[str, Any]]] = []
    semantic_unit_ids: list[str] = []
    for unit in program["units"]:
        if unit["emission"] != "prompt":
            continue
        unit_id = unit["unit_id"]
        kind = unit["kind"]
        parts: list[dict[str, Any]] = []
        if kind == "operation":
            if manifest["operation"] == "reference_generation":
                text = (
                    "Generate one continuous shot using the supplied references."
                    if locale == "en"
                    else "使用提供的参考素材生成一个连续镜头。"
                )
            else:
                text = (
                    "Generate one continuous transition using the supplied first and last frames. "
                    "Apply only the reference scopes stated below."
                    if locale == "en"
                    else "使用提供的首帧与尾帧生成一个连续过渡。仅按下述范围使用这些参考素材。"
                )
            parts.append({"kind": "text", "value": text})
        elif kind == "authority":
            asset_id = unit["binding_ids"][0]
            rows = sorted(
                assignments_by_asset[asset_id],
                key=lambda row: (
                    target_order[row["target_id"]],
                    reference_planner.DIMENSIONS.index(row["dimension"]),
                ),
            )
            rows_by_target: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                rows_by_target.setdefault(row["target_id"], []).append(row)
            binding = binding_by_id[asset_id]
            structured_role = binding.get("structured_role")
            if structured_role is None:
                parts.append({"kind": "binding", "binding_id": asset_id})
                text = AnnotatedText(": " if locale == "en" else "：")
                media_type = binding["media_type"]
                reference_source = {
                    "en": {
                        "image": "the reference image's",
                        "video": "the reference video's",
                        "audio": "the reference audio's",
                    },
                    "zh-Hans": {
                        "image": "参考图",
                        "video": "参考视频",
                        "audio": "参考音频",
                    },
                }[locale][media_type]
            else:
                role = (
                    ("supplied first frame" if locale == "en" else "提供的首帧")
                    if structured_role == "first_frame"
                    else ("supplied last frame" if locale == "en" else "提供的尾帧")
                )
                text = AnnotatedText(f"The {role}" if locale == "en" else role)
                reference_source = "that frame's" if locale == "en" else "该帧"

            exclusions: list[tuple[str, list[str]]] = []
            for group_index, (target_id, target_rows) in enumerate(rows_by_target.items()):
                target = target_by_id[target_id]
                label = _target_label(
                    target_id,
                    target["target_kind"],
                    locale,
                    catalog,
                )
                dimensions = [
                    DIMENSIONS[locale][row["dimension"]] for row in target_rows
                ]
                dimension_codes = [row["dimension"] for row in target_rows]
                structured_shot_scope = (
                    structured_role is not None
                    and target["target_kind"] == "shot"
                    and (
                        (
                            structured_role == "first_frame"
                            and set(dimension_codes)
                            == {"opening_state", "opening_composition"}
                        )
                        or (
                            structured_role == "last_frame"
                            and set(dimension_codes)
                            == {"endpoint", "endpoint_framing"}
                        )
                    )
                )
                if structured_shot_scope:
                    if locale == "en":
                        scope = (
                            " establishes this shot's visible opening state and opening composition"
                            if structured_role == "first_frame"
                            else " establishes this shot's settled final state and end framing"
                        )
                        prefix = "" if group_index == 0 else "; the same frame"
                    else:
                        scope = (
                            "确定本镜头可见的初始状态与开场构图"
                            if structured_role == "first_frame"
                            else "确定本镜头稳定的最终状态与结束构图"
                        )
                        prefix = "" if group_index == 0 else "；同一帧"
                    text = _concat_annotated(text, prefix, scope)
                elif locale == "en":
                    if group_index == 0:
                        prefix = (
                            "use only as the "
                            if structured_role is None
                            else " is used only as the "
                        )
                    else:
                        prefix = (
                            "; use this reference only as the "
                            if structured_role is None
                            else "; the same frame is used only as the "
                        )
                    text = _concat_annotated(
                        text,
                        prefix,
                        _join_terms(dimensions, locale),
                        " reference for ",
                        label,
                    )
                else:
                    prefix = (
                        "仅用于参考"
                        if group_index == 0
                        else (
                            "；同一参考素材仅用于参考"
                            if structured_role is None
                            else "；同一帧仅用于参考"
                        )
                    )
                    text = _concat_annotated(
                        text,
                        prefix,
                        label,
                        f"的{_join_terms(dimensions, locale)}",
                    )
                excluded = sorted(
                    {
                        dimension
                        for row in target_rows
                        for dimension in row["excluded_transfer_dimensions"]
                    },
                    key=reference_planner.DIMENSIONS.index,
                )
                if excluded:
                    exclusions.append(
                        (label.value, [DIMENSIONS[locale][item] for item in excluded])
                    )
            if exclusions:
                for label, localized in exclusions:
                    if structured_role is not None and len(rows_by_target) == 1:
                        if locale == "en" and set(localized) == {
                            "environment",
                            "visual style",
                        }:
                            text = _concat_annotated(
                                text,
                                "; do not treat that frame as an additional environment or visual-style reference",
                            )
                        elif locale == "zh-Hans":
                            text = _concat_annotated(
                                text,
                                "；不要把该帧作为额外的",
                                _join_alternatives(localized, locale),
                                "参考",
                            )
                        else:
                            text = _concat_annotated(
                                text,
                                "; do not treat that frame as an additional ",
                                _join_alternatives(localized, locale),
                                " reference",
                            )
                        continue
                    destination = (
                        ""
                        if len(rows_by_target) == 1
                        else (
                            f" when applying it to {label}"
                            if locale == "en"
                            else f"用于{label}时，"
                        )
                    )
                    text = _concat_annotated(
                        text,
                        (
                            f"; do not carry over {reference_source} "
                            f"{_join_alternatives(localized, locale)}{destination}"
                            if locale == "en"
                            else f"；{destination}不沿用{reference_source}中的"
                            f"{_join_alternatives(localized, locale)}"
                        ),
                    )
                text = _concat_annotated(text, "." if locale == "en" else "。")
            else:
                text = _concat_annotated(
                    text,
                    (
                        "; do not carry over any other attributes."
                        if locale == "en"
                        else "；不沿用其他属性。"
                    ),
                )
            parts.append({"kind": "text", "value": text})
        elif kind == "event":
            event_id = unit["event_ids"][0]
            event = event_by_id[event_id]
            predicate = _catalog_value(
                catalog,
                f"event.{event_id}.visible_state_change",
                locale,
            )
            parts.append(
                {
                    "kind": "text",
                    "value": _concat_annotated(
                        PHASE_PREFIX[locale][event["phase"]],
                        predicate,
                        "." if locale == "en" else "。",
                    ),
                }
            )
        elif kind == "camera":
            shot_id = unit["source_ids"][0]
            move = shot_by_id[shot_id]["camera"]["primary_move"]
            camera_fields = (
                ("path", "speed", "subject_relationship")
                if manifest["operation"] == "first_last_frame"
                else (
                    "start_framing",
                    "path",
                    "speed",
                    "subject_relationship",
                    "endpoint_framing",
                )
            )
            values = {
                field: _catalog_value(
                    catalog,
                    f"shot.{shot_id}.camera.{field}",
                    locale,
                )
                for field in camera_fields
            }
            if manifest["operation"] == "first_last_frame" and locale == "en":
                text = _concat_annotated(
                    f"Camera — movement: {CAMERA_KINDS[locale][move['kind']]}; movement path: ",
                    values["path"],
                    "; movement speed: ",
                    values["speed"],
                    "; subject placement during the transition: ",
                    values["subject_relationship"],
                    ".",
                )
            elif manifest["operation"] == "first_last_frame":
                text = _concat_annotated(
                    f"镜头——运动方式：{CAMERA_KINDS[locale][move['kind']]}；运动路径：",
                    values["path"],
                    "；运动速度：",
                    values["speed"],
                    "；过渡过程中的主体位置：",
                    values["subject_relationship"],
                    "。",
                )
            elif locale == "en":
                text = _concat_annotated(
                    f"Camera — movement: {CAMERA_KINDS[locale][move['kind']]}; opening framing: ",
                    values["start_framing"],
                    "; movement path: ",
                    values["path"],
                    "; movement speed: ",
                    values["speed"],
                    "; subject placement: ",
                    values["subject_relationship"],
                    "; end framing: ",
                    values["endpoint_framing"],
                    ".",
                )
            else:
                text = _concat_annotated(
                    f"镜头——运动方式：{CAMERA_KINDS[locale][move['kind']]}；起始构图：",
                    values["start_framing"],
                    "；运动路径：",
                    values["path"],
                    "；运动速度：",
                    values["speed"],
                    "；主体位置：",
                    values["subject_relationship"],
                    "；结束构图：",
                    values["endpoint_framing"],
                    "。",
                )
            parts.append({"kind": "text", "value": text})
        elif kind == "audio":
            audio_id = unit["source_ids"][0]
            audio = audio_by_id[audio_id]
            description = _catalog_value(
                catalog,
                f"audio.{audio_id}.description",
                locale,
            )
            temporal = TEMPORAL[locale][audio["temporal_relationship"]]
            if audio["temporal_relationship"] == "on_contact_or_state_change":
                linked_event = event_by_id[audio["linked_event_id"]]
                if linked_event["interaction_kind"] == "contact":
                    temporal = (
                        "at the described contact"
                        if locale == "en"
                        else "发生上述接触时"
                    )
                else:
                    temporal = (
                        "at the described state change"
                        if locale == "en"
                        else "发生上述状态变化时"
                    )
            if locale == "en":
                text = _concat_annotated(
                    f"{AUDIO_FUNCTIONS[locale][audio['semantic_function']].capitalize()} "
                    f"({temporal}): ",
                    description,
                    ".",
                )
            else:
                text = _concat_annotated(
                    f"{AUDIO_FUNCTIONS[locale][audio['semantic_function']]}（{temporal}）：",
                    description,
                    "。",
                )
            parts.append({"kind": "text", "value": text})
        elif kind == "invariant":
            invariant_id = unit["source_ids"][0]
            invariant_by_id[invariant_id]
            description = _catalog_value(
                catalog,
                f"invariant.{invariant_id}.description",
                locale,
            )
            text = _concat_annotated(
                "Continuity constraint: " if locale == "en" else "连续性约束：",
                description,
                "." if locale == "en" else "。",
            )
            parts.append({"kind": "text", "value": text})
        else:
            _fail("PRM001_EVENT_COVERAGE_INVALID", f"/prompt_program/units/{unit_id}")
        clauses.append(parts)
        semantic_unit_ids.append(unit_id)

    segments: list[dict[str, Any]] = []
    semantic_atoms: list[ResolvedSemanticAtom] = []
    for index, parts in enumerate(clauses):
        if index:
            _append_annotated_text(segments, semantic_atoms, "\n")
        for part in parts:
            if part["kind"] == "text":
                _append_annotated_text(
                    segments,
                    semantic_atoms,
                    part["value"],
                    semantic_unit_ids[index],
                )
            else:
                segments.append(part)
    if len(segments) > MAX_TYPED_SEGMENTS:
        _fail("PRM015_BUDGET_EXCEEDED", f"/renders/{locale}/typed_segments")
    text_characters = sum(
        len(segment["value"]) for segment in segments if segment["kind"] == "text"
    )
    if text_characters > MAX_PROMPT_CHARS:
        _fail("PRM015_BUDGET_EXCEEDED", f"/renders/{locale}/typed_segments")
    composed_text = "".join(
        segment["value"] for segment in segments if segment["kind"] == "text"
    )
    semantic_lint.validate_composed_payload(
        composed_text,
        f"/renders/{locale}/composed_text",
        allow_structured_frame_terms=manifest["operation"] == "first_last_frame",
    )
    _validate_semantic_atom_coverage(
        segments,
        semantic_atoms,
        semantic_unit_ids,
        locale,
    )
    _validate_semantic_unit_text(segments, semantic_unit_ids, locale)
    return segments, semantic_unit_ids, semantic_atoms


def _validate_binding_order(
    manifest: dict[str, Any], binding_set: dict[str, Any], rendered: dict[str, Any]
) -> None:
    expected = manifest["selection_order"]
    actual = [item["binding_id"] for item in binding_set["bindings"]]
    if actual != expected:
        _fail("REF001_BINDING_ORDER_MISMATCH", "/surface_binding_set/bindings")
    assets = {item["asset_id"]: item for item in manifest["assets"]}
    for index, request_binding in enumerate(rendered["request_bindings"]):
        asset_id = expected[index]
        if (
            request_binding["binding_id"] != asset_id
            or request_binding["media_type"] != assets[asset_id]["media_type"]
        ):
            _fail("PRM009_BINDING_CORE_MISMATCH", "/surface_binding_set/bindings")


def _validate_surface_coherence(
    carrier: dict[str, Any],
    planning_report: dict[str, Any],
    rendered_results: list[dict[str, Any]],
) -> None:
    planning_fields = (
        "profile_id",
        "profile_status",
        "operation",
        "evidence_claim_ids",
        "evidence_expires_at",
    )
    for field in planning_fields:
        if planning_report[field] != carrier[field]:
            _fail("PRM010_SURFACE_SEMANTIC_DRIFT", f"/surface_evidence/{field}")
    render_fields = (
        "profile_id",
        "profile_status",
        "model_profile_id",
        "model_profile_sha256",
        "profile_sha256",
        "profile_index_sha256",
        "operation",
        "request_transport",
        "request_bindings",
        "evidence_claim_ids",
        "evidence_expires_at",
    )
    for result in rendered_results:
        for field in render_fields:
            if result[field] != carrier[field]:
                _fail("PRM010_SURFACE_SEMANTIC_DRIFT", f"/surface_evidence/{field}")


def compile_request(
    value: object,
    *,
    preview_candidate: bool = False,
    today: date | None = None,
    root: Path = bindings.ROOT,
    _allow_unattested_fixture: bool = False,
) -> dict[str, Any]:
    request = _object(value, REQUEST_KEYS, "/")
    if request["schema_version"] != 1 or not bindings._is_int(request["schema_version"]):
        _fail("COMPILE001_REQUEST_CONTRACT_INVALID", "/schema_version")
    if not preview_candidate:
        _fail("PROFILE_CANDIDATE_REQUIRES_PREVIEW", "/surface_binding_set/profile_id")
    manifest = reference_planner.validate_reference_manifest(request["reference_manifest"])
    scene = scene_ir_check.validate_scene_ir(request["scene_ir"])
    reference_planner._align_manifest_targets_to_scene(manifest, scene)
    semantic_lint.validate_supported_scope(scene)
    binding_set = _validate_binding_set(request["surface_binding_set"])
    if (
        binding_set["profile_id"] != manifest["profile_id"]
        or binding_set["operation"] != manifest["operation"]
    ):
        _fail("PRM009_BINDING_CORE_MISMATCH", "/surface_binding_set")

    carrier = _carrier_plan(binding_set)
    carrier_render = bindings.render_plan(
        carrier,
        preview_candidate=True,
        today=today,
        root=root,
    )
    _validate_binding_order(manifest, binding_set, carrier_render)
    planning_report = reference_planner.plan_request(
        {
            "schema_version": 1,
            "reference_manifest": manifest,
            "scene_ir": scene,
            "binding_plan": carrier,
        },
        preview_candidate=True,
        today=today,
        root=root,
    )
    catalog, catalog_hash = semantic_lint.validate_catalog(
        scene,
        request["realization_catalog"],
        allow_unattested_fixture=_allow_unattested_fixture,
    )
    program = semantic_lint.build_prompt_program(
        manifest, scene, catalog, catalog_hash
    )
    program_hash = bindings.sha256_bytes(bindings.canonical_json(program))
    expected_semantic_key_trace = _expected_semantic_key_trace(
        program,
        manifest,
        catalog,
    )
    expected_semantic_unit_ids = [
        unit["unit_id"]
        for unit in program["units"]
        if unit["emission"] == "prompt"
    ]
    expected_binding_unit_trace = _expected_binding_unit_trace(program, binding_set)
    request_carried = _request_carried_records(manifest, scene, binding_set)

    renders: list[dict[str, Any]] = []
    rendered_results: list[dict[str, Any]] = []
    for locale in ("en", "zh-Hans"):
        segments, semantic_unit_ids, semantic_atoms = _render_unit_segments(
            locale=locale,
            program=program,
            manifest=manifest,
            scene=scene,
            binding_set=binding_set,
            catalog=catalog,
        )
        # Deliberately repeat this check outside the renderer helper so a
        # refactor or monkeypatched locale branch cannot preserve provenance
        # metadata while dropping the resolved catalog value from the text.
        _validate_semantic_atom_coverage(
            segments,
            semantic_atoms,
            semantic_unit_ids,
            locale,
        )
        _validate_semantic_unit_text(segments, semantic_unit_ids, locale)
        if semantic_unit_ids != expected_semantic_unit_ids:
            _fail("PARITY002_LOCALIZED_UNIT_ORDER_MISMATCH", f"/renders/{locale}")
        binding_unit_trace = _binding_unit_trace(
            segments,
            semantic_unit_ids,
            locale,
        )
        if binding_unit_trace != expected_binding_unit_trace:
            _fail("PRM009_BINDING_CORE_MISMATCH", f"/renders/{locale}/typed_segments")
        _validate_semantic_atoms_against_catalog(semantic_atoms, catalog, locale)
        semantic_key_trace = [atom.semantic_key for atom in semantic_atoms]
        semantic_unit_key_trace = [
            (atom.semantic_unit_id, atom.semantic_key)
            for atom in semantic_atoms
        ]
        if semantic_unit_key_trace != expected_semantic_key_trace:
            _fail("PARITY001_SEMANTIC_TRACE_MISMATCH", f"/renders/{locale}")
        public_semantic_atoms = _public_semantic_atoms(segments, semantic_atoms)
        plan = {
            "$schema": bindings.PLAN_SCHEMA_URI,
            "schema_version": 1,
            "profile_id": binding_set["profile_id"],
            "operation": binding_set["operation"],
            "segments": segments,
            "bindings": binding_set["bindings"],
        }
        result = bindings.render_plan(
            plan,
            preview_candidate=True,
            today=today,
            root=root,
        )
        if len(result["rendered_prompt"]) > MAX_PROMPT_CHARS:
            _fail("PRM015_BUDGET_EXCEEDED", f"/renders/{locale}/rendered_prompt")
        semantic_lint.validate_rendered_composition(
            result["rendered_prompt"],
            f"/renders/{locale}/rendered_prompt",
        )
        rendered_results.append(result)
        renders.append(
            {
                "locale": locale,
                "typed_segments": segments,
                "typed_segments_sha256": bindings.sha256_bytes(
                    bindings.canonical_json(segments)
                ),
                "rendered_prompt": result["rendered_prompt"],
                "rendered_prompt_sha256": bindings.sha256_bytes(
                    result["rendered_prompt"].encode("utf-8")
                ),
                "semantic_unit_ids": semantic_unit_ids,
                "binding_unit_trace": binding_unit_trace,
                "binding_unit_trace_sha256": bindings.sha256_bytes(
                    bindings.canonical_json(binding_unit_trace)
                ),
                "semantic_key_trace": semantic_key_trace,
                "semantic_key_trace_sha256": bindings.sha256_bytes(
                    bindings.canonical_json(semantic_key_trace)
                ),
                "resolved_semantic_atoms": public_semantic_atoms,
                "resolved_semantic_atoms_sha256": bindings.sha256_bytes(
                    bindings.canonical_json(public_semantic_atoms)
                ),
            }
        )

    _validate_surface_coherence(carrier_render, planning_report, rendered_results)
    if renders[0]["semantic_unit_ids"] != renders[1]["semantic_unit_ids"]:
        _fail("PARITY002_LOCALIZED_UNIT_ORDER_MISMATCH", "/renders")
    if renders[0]["semantic_key_trace"] != renders[1]["semantic_key_trace"]:
        _fail("PARITY001_SEMANTIC_TRACE_MISMATCH", "/renders")
    if renders[0]["binding_unit_trace"] != renders[1]["binding_unit_trace"]:
        _fail("PRM009_BINDING_CORE_MISMATCH", "/renders")
    trace_hash = bindings.sha256_bytes(
        bindings.canonical_json(renders[0]["semantic_unit_ids"])
    )
    semantic_key_trace_hash = bindings.sha256_bytes(
        bindings.canonical_json(renders[0]["semantic_key_trace"])
    )
    fixture_unattested = (
        request["realization_catalog"]["attestation"]["method"]
        == "unattested_fixture"
    )
    diagnostics = [
        {"code": "CANDIDATE_PREVIEW_ONLY", "severity": "warning", "pointer": "/preview"},
        {
            "code": (
                "CATALOG_FORMS_NOT_ATTESTED_FIXTURE"
                if fixture_unattested
                else "CATALOG_FORMS_HUMAN_ATTESTATION_DECLARED"
            ),
            "severity": "warning" if fixture_unattested else "info",
            "pointer": "/parity/catalog_linguistic_equivalence",
        },
        {
            "code": "CAUSAL_IR_PLANNING_HEURISTIC",
            "severity": "info",
            "pointer": "/prompt_program_sha256",
        },
    ]
    manifest_hash = bindings.sha256_bytes(bindings.canonical_json(manifest))
    scene_hash = bindings.sha256_bytes(bindings.canonical_json(scene))
    if (
        planning_report["reference_manifest_sha256"] != manifest_hash
        or planning_report["scene_ir_sha256"] != scene_hash
    ):
        _fail("PRM014_PROGRAM_HASH_MISMATCH", "/planning_report_sha256")
    first = rendered_results[0]
    return {
        "$schema": RENDER_SCHEMA_URI,
        "schema_version": 1,
        "status": "rendered",
        "preview": True,
        "profile_id": first["profile_id"],
        "profile_status": first["profile_status"],
        "model_profile_id": first["model_profile_id"],
        "model_profile_sha256": first["model_profile_sha256"],
        "profile_sha256": first["profile_sha256"],
        "profile_index_sha256": first["profile_index_sha256"],
        "operation": manifest["operation"],
        "reference_manifest_sha256": manifest_hash,
        "reference_semantics_sha256": program["reference_semantics_sha256"],
        "scene_ir_sha256": scene_hash,
        "surface_binding_set_sha256": bindings.sha256_bytes(
            bindings.canonical_json(binding_set)
        ),
        "realization_catalog_sha256": catalog_hash,
        "planning_report_sha256": bindings.sha256_bytes(
            bindings.canonical_json(planning_report)
        ),
        "prompt_program_sha256": program_hash,
        "compiler_sha256": COMPILER_SHA256,
        "compiler_toolchain_sha256": COMPILER_TOOLCHAIN_SHA256,
        "request_carried": request_carried,
        "request_carried_sha256": bindings.sha256_bytes(
            bindings.canonical_json(request_carried)
        ),
        "renders": renders,
        "request_transport": first["request_transport"],
        "request_bindings": first["request_bindings"],
        "evidence_claim_ids": first["evidence_claim_ids"],
        "evidence_expires_at": first["evidence_expires_at"],
        "parity": {
            "semantic_unit_ids_sha256": trace_hash,
            "en_semantic_unit_ids_sha256": trace_hash,
            "zh_hans_semantic_unit_ids_sha256": trace_hash,
            "semantic_key_trace_sha256": semantic_key_trace_hash,
            "en_semantic_key_trace_sha256": semantic_key_trace_hash,
            "zh_hans_semantic_key_trace_sha256": semantic_key_trace_hash,
            "structural_trace_matched": True,
            "surface_independent": True,
            "catalog_linguistic_equivalence": (
                "not_attested_fixture"
                if fixture_unattested
                else "human_asserted_not_machine_verified"
            ),
        },
        "diagnostics": diagnostics,
    }


def _self_test() -> None:
    binding_set = {
        "$schema": BINDING_SET_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": "fal.reference-to-video",
        "operation": "reference_generation",
        "bindings": [{"binding_id": "product", "media_type": "image"}],
    }
    plan = _carrier_plan(binding_set)
    if plan["segments"] != [
        {"kind": "binding", "binding_id": "product"},
        {"kind": "text", "value": "."},
    ]:
        _fail("SELF_TEST_FAILED")
    if set(DIMENSIONS["en"]) != set(DIMENSIONS["zh-Hans"]):
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile one V7 semantic plan into paired EN/zh-Hans candidate prompts."
    )
    parser.add_argument(
        "--preview-candidate",
        action="store_true",
        help="exercise disabled candidate profiles; output remains preview-only",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("paired prompt compiler self-test passed")
            return 0
        raw = sys.stdin.buffer.read(semantic_lint.MAX_COMPILER_INPUT_BYTES + 1)
        if len(raw) > semantic_lint.MAX_COMPILER_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        request = bindings.parse_json_bytes(
            raw,
            max_bytes=semantic_lint.MAX_COMPILER_INPUT_BYTES,
        )
        report = compile_request(
            request,
            preview_candidate=args.preview_candidate,
        )
        payload = bindings.canonical_json(report)
    except bindings.BindingError as exc:
        print(f"prompt-compile error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
