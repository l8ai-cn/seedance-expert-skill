#!/usr/bin/env python3
"""Validate the non-activating V7-05 model and surface profile projection."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import render_surface_bindings as renderer  # noqa: E402
from tools.evidence_registry import evaluate as evaluate_evidence  # noqa: E402
from tools.evidence_registry import layout_for_root  # noqa: E402

EXPECTED_MODEL_PATHS = {
    "seedance-2.0-model": "profiles/models/seedance-2.0-model.json",
}
EXPECTED_SURFACE_PATHS = {
    "byteplus.modelark": "profiles/surfaces/byteplus-modelark.json",
    "fal.reference-to-video": "profiles/surfaces/fal-reference-to-video.json",
    "volcengine.ark": "profiles/surfaces/volcengine-ark.json",
}
EXPECTED_MODEL_PROJECTION = {
    "input_modalities": ["audio", "image", "text", "video"],
    "reference_control_dimensions": ["camera_movement", "lighting", "performance", "shadow"],
    "claim_ids": {
        "bytedance.model.multimodal-inputs",
        "bytedance.model.reference-control",
    },
}
EXPECTED_OPERATIONS = {
    ("byteplus.modelark", "reference_generation"): {
        "request_transport": "external_surface_unresolved",
        "prompt_binding": {
            "kind": "opaque_external_handle",
            "source": "surface_captured_exact",
        },
        "allowed_media_types": ["image"],
        "structured_roles": [],
        "required_role_set": [],
        "claim_ids": {
            "global.binding.no-universal-token",
            "bp.binding.spaced-example-token",
        },
    },
    ("fal.reference-to-video", "reference_generation"): {
        "request_transport": "typed_media_arrays",
        "prompt_binding": {
            "kind": "derived_media_ordinal",
            "position_scope": "per_media_type",
            "media_formatters": {
                "audio": {"sigil": "@", "media_label": "Audio", "separator": "", "ordinal_base": 1},
                "image": {"sigil": "@", "media_label": "Image", "separator": "", "ordinal_base": 1},
                "video": {"sigil": "@", "media_label": "Video", "separator": "", "ordinal_base": 1},
            },
        },
        "allowed_media_types": ["audio", "image", "video"],
        "structured_roles": [],
        "required_role_set": [],
        "claim_ids": {
            "global.binding.no-universal-token",
            "fal.binding.at-ordinal",
        },
    },
    ("volcengine.ark", "reference_generation"): {
        "request_transport": "ordered_content_objects",
        "prompt_binding": {
            "kind": "derived_media_ordinal",
            "position_scope": "per_media_type",
            "media_formatters": {
                "image": {"sigil": "", "media_label": "图片", "separator": "", "ordinal_base": 1},
            },
        },
        "allowed_media_types": ["image"],
        "structured_roles": [],
        "required_role_set": [],
        "claim_ids": {
            "global.binding.no-universal-token",
            "volc.binding.asset-ordinal",
        },
    },
    ("volcengine.ark", "first_last_frame"): {
        "request_transport": "structured_content_roles",
        "prompt_binding": {"kind": "none"},
        "allowed_media_types": ["image"],
        "structured_roles": ["first_frame", "last_frame"],
        "required_role_set": ["first_frame", "last_frame"],
        "claim_ids": {"volc.binding.first-last-frame-role"},
    },
}

EXPECTED_ORDINAL_CLAIM_VALUES = {
    ("fal.reference-to-video", "reference_generation"): ("fal.binding.at-ordinal", "@Image1"),
    ("volcengine.ark", "reference_generation"): ("volc.binding.asset-ordinal", "图片1"),
}


def _claim_records(root: Path, errors: list[str]) -> dict[str, tuple[dict[str, Any], str]]:
    directory = root / "research" / "evidence" / "claims"
    result: dict[str, tuple[dict[str, Any], str]] = {}
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError:
        errors.append("claims: directory is unreadable")
        return result
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            raw = renderer.read_internal_bytes(root, relative)
            value = renderer.parse_json_bytes(raw, relative)
        except renderer.BindingError as exc:
            errors.append(f"{relative}: {exc.code}")
            continue
        if not isinstance(value, dict) or not isinstance(value.get("claim_id"), str):
            errors.append(f"{relative}: claim record is invalid")
            continue
        claim_id = value["claim_id"]
        if claim_id in result:
            errors.append(f"{relative}: duplicate claim ID")
            continue
        result[claim_id] = (value, hashlib.sha256(raw).hexdigest())
    return result


def _check_pin(
    pin: dict[str, Any],
    *,
    profile_id: str,
    operation: str | None,
    model_level: bool,
    claims: dict[str, tuple[dict[str, Any], str]],
    today: date,
    errors: list[str],
) -> None:
    claim_id = pin["claim_id"]
    record = claims.get(claim_id)
    label = f"{profile_id}:{operation or 'model'}:{claim_id}"
    if record is None:
        errors.append(f"{label}: claim is missing")
        return
    claim, digest = record
    if pin["claim_sha256"] != digest:
        errors.append(f"{label}: claim hash mismatch")
    if pin["expires_at"] != claim.get("expires_at"):
        errors.append(f"{label}: expiry projection mismatch")
    try:
        expiry = date.fromisoformat(pin["expires_at"])
    except (TypeError, ValueError):
        errors.append(f"{label}: expiry is invalid")
        return
    if today >= expiry:
        errors.append(f"{label}: evidence is expired")
    if claim.get("support_status") != "supported":
        errors.append(f"{label}: claim is not supported")
    if claim.get("lifecycle_status") != "active":
        errors.append(f"{label}: claim is not active")
    if claim.get("runtime_status") != "candidate":
        errors.append(f"{label}: claim is not candidate-scoped")
    review = claim.get("review")
    if not isinstance(review, dict) or review.get("status") not in {"pending", "approved"}:
        errors.append(f"{label}: claim review state blocks projection")
    affected_profiles = claim.get("affected_profiles")
    if not isinstance(affected_profiles, list) or not all(
        isinstance(item, str) for item in affected_profiles
    ):
        errors.append(f"{label}: affected profiles are invalid")
    elif profile_id not in affected_profiles:
        errors.append(f"{label}: affected profile is not declared")
    scope = claim.get("scope")
    if not isinstance(scope, dict):
        errors.append(f"{label}: claim scope is invalid")
        return
    surfaces = scope.get("surfaces", [])
    operations = scope.get("operations", [])
    if not isinstance(surfaces, list) or not all(isinstance(item, str) for item in surfaces):
        errors.append(f"{label}: claim surfaces are invalid")
        return
    if not isinstance(operations, list) or not all(isinstance(item, str) for item in operations):
        errors.append(f"{label}: claim operations are invalid")
        return
    if model_level:
        if surfaces != ["model"]:
            errors.append(f"{label}: surface evidence leaked into model profile")
    else:
        if profile_id not in surfaces:
            errors.append(f"{label}: claim surface does not match profile")
        if operation not in operations:
            errors.append(f"{label}: claim operation does not match profile")


def check_profiles(root: Path = ROOT, *, today: date | None = None) -> tuple[list[str], dict[str, int]]:
    root = root.resolve()
    current = today or datetime.now(timezone.utc).date()
    errors: list[str] = []
    try:
        registry = renderer.load_registry(root)
    except renderer.BindingError as exc:
        return [f"profile-registry: {exc.code} at {exc.pointer}"], {}

    report, evidence_errors, _warnings = evaluate_evidence(
        layout_for_root(root), as_of=current, enforce_freshness=True
    )
    errors.extend(f"evidence-registry: {item}" for item in evidence_errors)
    if report.get("activation_enabled") is not False:
        errors.append("evidence-registry: activation must remain disabled")

    if registry.index.get("activation_enabled") is not False:
        errors.append("profile-index: activation must remain disabled")
    model_paths = {profile_id: item.path for profile_id, item in registry.models.items()}
    surface_paths = {profile_id: item.path for profile_id, item in registry.surfaces.items()}
    if model_paths != EXPECTED_MODEL_PATHS:
        errors.append("profile-index: model profile closure changed")
    if surface_paths != EXPECTED_SURFACE_PATHS:
        errors.append("profile-index: surface profile closure changed")

    indexed_paths = set(model_paths.values()) | set(surface_paths.values())
    disk_paths = {
        path.relative_to(root).as_posix()
        for directory in (root / "profiles" / "models", root / "profiles" / "surfaces")
        for path in directory.glob("*.json")
    }
    if indexed_paths != disk_paths:
        errors.append("profile-index: unindexed or missing profile files")

    claims = _claim_records(root, errors)
    model = registry.models.get("seedance-2.0-model")
    if model is not None:
        if model.data["input_modalities"] != EXPECTED_MODEL_PROJECTION["input_modalities"]:
            errors.append("seedance-2.0-model: modality projection changed")
        if model.data["reference_control_dimensions"] != EXPECTED_MODEL_PROJECTION["reference_control_dimensions"]:
            errors.append("seedance-2.0-model: reference-control projection changed")
        pins = model.data["evidence_pins"]
        if {pin["claim_id"] for pin in pins} != EXPECTED_MODEL_PROJECTION["claim_ids"]:
            errors.append("seedance-2.0-model: evidence closure changed")
        for pin in pins:
            _check_pin(
                pin,
                profile_id=model.profile_id,
                operation=None,
                model_level=True,
                claims=claims,
                today=current,
                errors=errors,
            )

    actual_operation_keys: set[tuple[str, str]] = set()
    for profile_id, profile in registry.surfaces.items():
        if profile.data["status"] != "candidate" or profile.data["runtime_enabled"] is not False:
            errors.append(f"{profile_id}: V7-05 profile must remain a disabled candidate")
        for operation in profile.data["operations"]:
            key = (profile_id, operation["operation"])
            actual_operation_keys.add(key)
            expected = EXPECTED_OPERATIONS.get(key)
            if expected is None:
                errors.append(f"{profile_id}:{operation['operation']}: unreviewed operation")
                continue
            for field in (
                "request_transport", "prompt_binding", "allowed_media_types",
                "structured_roles", "required_role_set",
            ):
                if operation[field] != expected[field]:
                    errors.append(f"{profile_id}:{operation['operation']}:{field}: projection changed")
            pins = operation["evidence_pins"]
            if {pin["claim_id"] for pin in pins} != expected["claim_ids"]:
                errors.append(f"{profile_id}:{operation['operation']}: evidence closure changed")
            for pin in pins:
                _check_pin(
                    pin,
                    profile_id=profile_id,
                    operation=operation["operation"],
                    model_level=False,
                    claims=claims,
                    today=current,
                    errors=errors,
                )
            entailment = EXPECTED_ORDINAL_CLAIM_VALUES.get(key)
            if entailment is not None:
                claim_id, expected_value = entailment
                claim_record = claims.get(claim_id)
                formatter = operation["prompt_binding"]["media_formatters"].get("image", {})
                projected_value = (
                    formatter.get("sigil", "")
                    + formatter.get("media_label", "")
                    + formatter.get("separator", "")
                    + str(formatter.get("ordinal_base", ""))
                )
                if claim_record is None or claim_record[0].get("value") != expected_value:
                    errors.append(f"{profile_id}:{operation['operation']}: ordinal claim value changed")
                if projected_value != expected_value:
                    errors.append(f"{profile_id}:{operation['operation']}: formatter is not entailed by claim value")
    if actual_operation_keys != set(EXPECTED_OPERATIONS):
        errors.append("surface profiles: operation closure changed")

    counts = {
        "model_profiles": len(registry.models),
        "surface_profiles": len(registry.surfaces),
        "surface_operations": len(actual_operation_keys),
        "evidence_pins": sum(
            len(profile.data["evidence_pins"]) for profile in registry.models.values()
        ) + sum(
            len(operation["evidence_pins"])
            for profile in registry.surfaces.values()
            for operation in profile.data["operations"]
        ),
    }
    return sorted(set(errors)), counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate V7-05 model and surface profiles.")
    parser.add_argument("repo", nargs="?", type=Path, default=ROOT)
    args = parser.parse_args()
    errors, counts = check_profiles(args.repo)
    if errors:
        print("Profile validation errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Profile projection validated: "
        f"{counts['model_profiles']} model, {counts['surface_profiles']} surfaces, "
        f"{counts['surface_operations']} operations, {counts['evidence_pins']} evidence pins; "
        "activation_enabled=false."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
