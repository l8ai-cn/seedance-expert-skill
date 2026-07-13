#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


IMMUTABLE_KEYS = [
    "canonical_identity_id",
    "wardrobe",
    "product_identity",
    "prop_owner",
    "location",
    "vehicle_identity",
    "persistent_environment",
    "reference_tags",
]
TRANSIENT_KEYS = [
    "pose",
    "position_in_frame",
    "travel_direction",
    "motion_vector",
    "camera_phase",
    "focus_state",
    "lighting_phase",
    "emotional_state",
    "audio_phase",
]
V2_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/project-state-v2.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def is_v2_document(data: object, path: Path) -> bool:
    if isinstance(data, dict) and (data.get("$schema") == V2_SCHEMA_URI or data.get("schema_version") == 2):
        return True
    return "project-state-v2" in path.name.casefold()


def _entries(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, str)]
    return []


def _names_dimension(entry: str, key: str) -> bool:
    normalized = entry.casefold()
    variants = {key.casefold(), key.replace("_", " ").casefold()}
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", normalized)
        for variant in variants
    )


def has_allowance(clip: dict, key: str) -> bool:
    entries: list[str] = []
    for field in ("transition_in", "allowed_changes", "accepted_deviations", "continuity_breaks"):
        entries.extend(_entries(clip.get(field)))
    if any(_names_dimension(entry, key) for entry in entries):
        return True
    if key == "travel_direction":
        return any(
            "axis reset" in entry.casefold() or "reset screen axis" in entry.casefold()
            for entry in entries
        )
    return False


def state_values(state: dict | None, key: str) -> list[tuple[str, object]]:
    if not isinstance(state, dict):
        return []
    found: list[tuple[str, object]] = []
    if key in state:
        found.append((f"/{key}", state.get(key)))
    for owner in sorted(state):
        value = state[owner]
        if isinstance(value, dict) and key in value:
            found.append((f"/{owner}/{key}", value.get(key)))
    return found


def validate(path: Path, root: Path) -> tuple[list[str], list[str]]:
    rel = path.relative_to(root).as_posix()
    try:
        data = load(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{rel}: invalid JSON: {type(exc).__name__}"], []
    if is_v2_document(data, path):
        return [], []
    if not isinstance(data, dict):
        return [f"{rel}: project state must be an object"], []
    clips = {clip["clip_id"]: clip for clip in data.get("clips", [])}
    errors: list[str] = []
    warnings: list[str] = []
    for clip in data.get("clips", []):
        parent_id = clip.get("parent_clip_id")
        if not parent_id:
            continue
        parent = clips.get(parent_id)
        if not parent:
            errors.append(f"{rel}: clip {clip['clip_id']} parent {parent_id} missing")
            continue
        if clip.get("status") == "planned" and parent.get("status") not in {"accepted", "accepted_with_deviation"}:
            continue
        if parent.get("status") not in {"accepted", "accepted_with_deviation"}:
            errors.append(f"{rel}: clip {clip['clip_id']} parent {parent_id} is not accepted")
            continue
        end_state = parent.get("observed_end_state")
        start_state = clip.get("planned_start_state")
        if not end_state:
            errors.append(f"{rel}: parent {parent_id} missing observed_end_state")
            continue
        if not start_state:
            errors.append(f"{rel}: clip {clip['clip_id']} missing planned_start_state")
            continue
        for key in IMMUTABLE_KEYS:
            a_values = state_values(end_state, key)
            b_values = state_values(start_state, key)
            if len(a_values) > 1:
                errors.append(f"{rel}: parent {parent_id} has ambiguous {key} at {', '.join(item[0] for item in a_values)}")
                continue
            if len(b_values) > 1:
                errors.append(f"{rel}: clip {clip['clip_id']} has ambiguous {key} at {', '.join(item[0] for item in b_values)}")
                continue
            a = a_values[0][1] if a_values else None
            b = b_values[0][1] if b_values else None
            if a is not None and b is not None and a != b and not has_allowance(clip, key):
                errors.append(f"{rel}: immutable {key} changes from {a!r} to {b!r} without allowance")
        for key in TRANSIENT_KEYS:
            a_values = state_values(end_state, key)
            b_values = state_values(start_state, key)
            if len(a_values) > 1:
                errors.append(f"{rel}: parent {parent_id} has ambiguous {key} at {', '.join(item[0] for item in a_values)}")
                continue
            if len(b_values) > 1:
                errors.append(f"{rel}: clip {clip['clip_id']} has ambiguous {key} at {', '.join(item[0] for item in b_values)}")
                continue
            a = a_values[0][1] if a_values else None
            b = b_values[0][1] if b_values else None
            if a is not None and b is not None and a != b and not has_allowance(clip, key):
                warnings.append(f"{rel}: transient {key} changes from {a!r} to {b!r} without allowance")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    for path in sorted((root / "examples").rglob("*project-state*.json")) if (root / "examples").exists() else []:
        e, w = validate(path, root)
        errors.extend(e)
        warnings.extend(w)
    if warnings:
        print("Continuity warnings:")
        for warning in warnings:
            print(f"- {warning}")
        print()
    if errors or (args.strict and warnings):
        print("Continuity errors:")
        for error in errors:
            print(f"- {error}")
        if args.strict:
            for warning in warnings:
                print(f"- {warning}")
        return 1
    print("Continuity chain check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
