#!/usr/bin/env python3
"""Compile reference authority plus causal scene intent into a review report.

V7-06 is intentionally candidate-only.  It validates user/reviewer-attested
reference semantics, a causal planning IR, and the V7-05 surface binding plan;
it never uploads media, discovers provider handles, writes prompts, calls a
network, or claims that the planning graph is a model architecture.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

try:  # Support both ``python scripts/...`` and ``from scripts import ...``.
    from . import render_surface_bindings as bindings
    from . import scene_ir_check
except ImportError:  # pragma: no cover - exercised by CLI tests
    import render_surface_bindings as bindings
    import scene_ir_check


REFERENCE_MANIFEST_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/reference-manifest.schema.json"
)
PLANNING_REPORT_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/planning-report.schema.json"
)
SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
LOCATOR_LIKE = re.compile(
    r"(?:https?://|file://|(?:^|\s)(?:[A-Za-z]:[\\/]|/(?:[^\s/]+/)*[^\s/]+))",
    re.IGNORECASE,
)

REQUEST_KEYS = {"schema_version", "reference_manifest", "scene_ir", "binding_plan"}
MANIFEST_KEYS = {
    "$schema",
    "schema_version",
    "profile_id",
    "operation",
    "task_intent",
    "targets",
    "assets",
    "authority_assignments",
    "selection_order",
    "ablation_order",
}
TARGET_KEYS = {"target_id", "target_kind", "required_dimensions", "not_applicable_dimensions"}
ASSET_KEYS = {
    "asset_id",
    "media_type",
    "use",
    "selection_status",
    "subject_selector",
    "subject_locator",
    "observed_leakage_dimensions",
    "preflight_status",
    "preflight",
    "rights",
}
SUBJECT_LOCATOR_KEYS = {"method", "description"}
ASSIGNMENT_KEYS = {
    "target_id",
    "dimension",
    "winner_asset_id",
    "excluded_asset_ids",
    "priority",
    "confidence",
    "excluded_transfer_dimensions",
    "leakage_risks",
    "resolved_leakage",
    "acceptance_criteria",
}
RIGHTS_KEYS = {"media_use", "likeness", "voice_performance", "music", "brand_logo"}
IMAGE_PREFLIGHT_KEYS = {
    "inspection_method",
    "subject_count",
    "face_visibility",
    "face_frame_fraction",
    "body_coverage",
    "view_layout",
    "background_complexity",
    "has_text",
    "has_logo",
    "occlusion",
    "composition_use",
}
VIDEO_PREFLIGHT_KEYS = {
    "inspection_method",
    "duration_seconds",
    "cut_count",
    "actor_count",
    "camera_motion",
    "subject_motion",
    "embedded_audio",
    "has_voice",
    "has_music",
    "occlusion",
    "silhouette_readable",
    "start_state_visible",
    "end_state_visible",
    "decisive_event_visible",
}
AUDIO_PREFLIGHT_KEYS = {
    "inspection_method",
    "duration_seconds",
    "has_voice",
    "has_music",
    "has_sound_effects",
    "has_ambience",
    "speaker_count",
    "clarity",
    "timing_useful",
}

DIMENSIONS = (
    "identity",
    "face_detail",
    "wardrobe",
    "product_object_geometry",
    "environment",
    "visual_style",
    "opening_composition",
    "subject_motion",
    "camera_motion",
    "timing_rhythm",
    "audio_voice",
    "endpoint",
    "text_logo_treatment",
)
DIMENSION_SET = set(DIMENSIONS)
TARGET_KINDS = {"character", "product", "object", "environment", "shot", "audio", "text_logo"}
ASSET_USES = {
    "identity_reference",
    "appearance_reference",
    "motion_reference",
    "environment_reference",
    "style_reference",
    "opening_frame",
    "endpoint_frame",
    "audio_reference",
    "product_reference",
    "text_logo_reference",
}
MEDIA_DIMENSIONS = {
    "image": {
        "identity",
        "face_detail",
        "wardrobe",
        "product_object_geometry",
        "environment",
        "visual_style",
        "opening_composition",
        "endpoint",
        "text_logo_treatment",
    },
    "video": set(DIMENSIONS),
    "audio": {"timing_rhythm", "audio_voice"},
}
USE_MEDIA = {
    "identity_reference": {"image", "video"},
    "appearance_reference": {"image", "video"},
    "motion_reference": {"video"},
    "environment_reference": {"image", "video"},
    "style_reference": {"image", "video"},
    "opening_frame": {"image"},
    "endpoint_frame": {"image"},
    "audio_reference": {"audio", "video"},
    "product_reference": {"image", "video"},
    "text_logo_reference": {"image", "video"},
}
USE_DIMENSIONS = {
    "identity_reference": {"identity", "face_detail", "wardrobe"},
    "appearance_reference": {
        "identity",
        "face_detail",
        "wardrobe",
        "product_object_geometry",
        "environment",
        "visual_style",
        "text_logo_treatment",
    },
    "motion_reference": {"subject_motion", "camera_motion", "timing_rhythm"},
    "environment_reference": {"environment", "visual_style", "opening_composition"},
    "style_reference": {"visual_style"},
    "opening_frame": {"opening_composition"},
    "endpoint_frame": {"endpoint"},
    "audio_reference": {"audio_voice", "timing_rhythm"},
    "product_reference": {"product_object_geometry", "text_logo_treatment"},
    "text_logo_reference": {"text_logo_treatment"},
}
RIGHT_VALUES = {
    "user_asserted_authorized",
    "not_applicable",
    "unknown",
    "not_authorized",
}
INSPECTION_METHODS = {"user_attested", "reviewer_attested"}
PROFILE_OPERATIONS = {
    ("byteplus.modelark", "reference_generation"),
    ("fal.reference-to-video", "reference_generation"),
    ("volcengine.ark", "reference_generation"),
    ("volcengine.ark", "first_last_frame"),
}


class ReferencePlanningError(bindings.BindingError):
    """Stable, non-echoing reference planning failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise ReferencePlanningError(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(
    value: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 832,
) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("ARRAY_BOUNDS_INVALID", pointer)
    return value


def _identifier(value: object, pointer: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        _fail("IDENTIFIER_INVALID", pointer)
    return value


def _text(value: object, pointer: str, *, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("TEXT_INVALID", pointer)
    bindings._validate_visible_text(value, pointer)
    if LOCATOR_LIKE.search(value) or bindings.REFERENCE_LIKE_TOKEN.search(value):
        _fail("REF001_LOCATOR_OR_HANDLE_FORBIDDEN", pointer)
    return value


def _enum(value: object, allowed: set[str], pointer: str, code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(code, pointer)
    return value


def _integer(value: object, pointer: str, minimum: int, maximum: int) -> int:
    if not bindings._is_int(value) or not minimum <= value <= maximum:
        _fail("NUMBER_INVALID", pointer)
    return value


def _number(value: object, pointer: str, minimum: float, maximum: float, *, exclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("NUMBER_INVALID", pointer)
    if (value <= minimum if exclusive else value < minimum) or value > maximum:
        _fail("NUMBER_INVALID", pointer)
    return float(value)


def _boolean(value: object, pointer: str) -> bool:
    if not isinstance(value, bool):
        _fail("BOOLEAN_REQUIRED", pointer)
    return value


def _unique_ids(
    value: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 64,
) -> list[str]:
    values = _array(value, pointer, minimum=minimum, maximum=maximum)
    result = [_identifier(item, f"{pointer}/{index}") for index, item in enumerate(values)]
    if len(result) != len(set(result)):
        _fail("IDENTIFIER_DUPLICATE", pointer)
    return result


def _dimension_set(value: object, pointer: str, *, minimum: int = 0) -> list[str]:
    values = _array(value, pointer, minimum=minimum, maximum=len(DIMENSIONS))
    result = [
        _enum(item, DIMENSION_SET, f"{pointer}/{index}", "REFERENCE_DIMENSION_INVALID")
        for index, item in enumerate(values)
    ]
    if len(result) != len(set(result)):
        _fail("REFERENCE_DIMENSION_DUPLICATE", pointer)
    return result


def _validate_preflight(asset: dict[str, Any], pointer: str) -> None:
    media_type = asset["media_type"]
    preflight = asset["preflight"]
    if media_type == "image":
        data = _object(preflight, IMAGE_PREFLIGHT_KEYS, f"{pointer}/preflight")
        _enum(data["inspection_method"], INSPECTION_METHODS, f"{pointer}/preflight/inspection_method", "REF007_INSPECTION_METHOD_INVALID")
        _integer(data["subject_count"], f"{pointer}/preflight/subject_count", 0, 64)
        _enum(data["face_visibility"], {"none", "partial", "clear"}, f"{pointer}/preflight/face_visibility", "REF007_IMAGE_PREFLIGHT_INVALID")
        _number(data["face_frame_fraction"], f"{pointer}/preflight/face_frame_fraction", 0, 1)
        _enum(data["body_coverage"], {"none", "partial", "full"}, f"{pointer}/preflight/body_coverage", "REF007_IMAGE_PREFLIGHT_INVALID")
        _enum(data["view_layout"], {"single_scene", "multiview_collage"}, f"{pointer}/preflight/view_layout", "REF007_IMAGE_PREFLIGHT_INVALID")
        _enum(data["background_complexity"], {"low", "medium", "high"}, f"{pointer}/preflight/background_complexity", "REF007_IMAGE_PREFLIGHT_INVALID")
        _boolean(data["has_text"], f"{pointer}/preflight/has_text")
        _boolean(data["has_logo"], f"{pointer}/preflight/has_logo")
        _enum(data["occlusion"], {"none", "partial", "severe"}, f"{pointer}/preflight/occlusion", "REF007_IMAGE_PREFLIGHT_INVALID")
        _enum(
            data["composition_use"],
            {"appearance_reference", "opening_frame", "endpoint_frame", "environment_reference", "product_reference", "style_reference"},
            f"{pointer}/preflight/composition_use",
            "REF007_IMAGE_PREFLIGHT_INVALID",
        )
    elif media_type == "video":
        data = _object(preflight, VIDEO_PREFLIGHT_KEYS, f"{pointer}/preflight")
        _enum(data["inspection_method"], INSPECTION_METHODS, f"{pointer}/preflight/inspection_method", "REF007_INSPECTION_METHOD_INVALID")
        _number(data["duration_seconds"], f"{pointer}/preflight/duration_seconds", 0, 600, exclusive=True)
        _integer(data["cut_count"], f"{pointer}/preflight/cut_count", 0, 1_000)
        _integer(data["actor_count"], f"{pointer}/preflight/actor_count", 0, 64)
        _enum(data["camera_motion"], {"locked", "single_move", "compound", "unknown"}, f"{pointer}/preflight/camera_motion", "REF007_VIDEO_PREFLIGHT_INVALID")
        _enum(data["subject_motion"], {"none", "subtle", "clear", "complex", "unknown"}, f"{pointer}/preflight/subject_motion", "REF007_VIDEO_PREFLIGHT_INVALID")
        for field in (
            "embedded_audio",
            "has_voice",
            "has_music",
            "silhouette_readable",
            "start_state_visible",
            "end_state_visible",
            "decisive_event_visible",
        ):
            _boolean(data[field], f"{pointer}/preflight/{field}")
        if not data["embedded_audio"] and (data["has_voice"] or data["has_music"]):
            _fail("REF007_VIDEO_AUDIO_PREFLIGHT_INVALID", f"{pointer}/preflight")
        _enum(data["occlusion"], {"none", "partial", "severe"}, f"{pointer}/preflight/occlusion", "REF007_VIDEO_PREFLIGHT_INVALID")
    else:
        data = _object(preflight, AUDIO_PREFLIGHT_KEYS, f"{pointer}/preflight")
        _enum(data["inspection_method"], INSPECTION_METHODS, f"{pointer}/preflight/inspection_method", "REF007_INSPECTION_METHOD_INVALID")
        _number(data["duration_seconds"], f"{pointer}/preflight/duration_seconds", 0, 600, exclusive=True)
        for field in ("has_voice", "has_music", "has_sound_effects", "has_ambience", "timing_useful"):
            _boolean(data[field], f"{pointer}/preflight/{field}")
        _integer(data["speaker_count"], f"{pointer}/preflight/speaker_count", 0, 64)
        _enum(data["clarity"], {"clear", "mixed", "poor", "unknown"}, f"{pointer}/preflight/clarity", "REF007_AUDIO_PREFLIGHT_INVALID")
        if data["has_voice"] != (data["speaker_count"] > 0):
            _fail("REF007_AUDIO_SPEAKER_COUNT_INVALID", f"{pointer}/preflight/speaker_count")


def _right_sufficient(value: str) -> bool:
    return value in {"user_asserted_authorized", "not_applicable"}


def validate_reference_manifest(value: object) -> dict[str, Any]:
    """Validate the semantic reference plan without inferring any winner."""

    manifest = _object(value, MANIFEST_KEYS, "/reference_manifest")
    if (
        manifest["$schema"] != REFERENCE_MANIFEST_SCHEMA_URI
        or not bindings._is_int(manifest["schema_version"])
        or manifest["schema_version"] != 1
    ):
        _fail("REFERENCE_MANIFEST_CONTRACT_INVALID", "/reference_manifest")
    profile_id = _enum(
        manifest["profile_id"],
        {item[0] for item in PROFILE_OPERATIONS},
        "/reference_manifest/profile_id",
        "PROFILE_ID_INVALID",
    )
    operation = _enum(
        manifest["operation"],
        {"reference_generation", "first_last_frame"},
        "/reference_manifest/operation",
        "OPERATION_INVALID",
    )
    if (profile_id, operation) not in PROFILE_OPERATIONS:
        _fail("REF003_PROFILE_OPERATION_CONFLICT", "/reference_manifest/operation")
    _text(manifest["task_intent"], "/reference_manifest/task_intent")

    target_by_id: dict[str, dict[str, Any]] = {}
    target_order: dict[str, int] = {}
    for index, raw in enumerate(
        _array(manifest["targets"], "/reference_manifest/targets", minimum=1, maximum=64)
    ):
        pointer = f"/reference_manifest/targets/{index}"
        target = _object(raw, TARGET_KEYS, pointer)
        target_id = _identifier(target["target_id"], f"{pointer}/target_id")
        if target_id in target_by_id:
            _fail("TARGET_ID_DUPLICATE", f"{pointer}/target_id")
        _enum(target["target_kind"], TARGET_KINDS, f"{pointer}/target_kind", "TARGET_KIND_INVALID")
        required = _dimension_set(target["required_dimensions"], f"{pointer}/required_dimensions", minimum=1)
        not_applicable = _dimension_set(target["not_applicable_dimensions"], f"{pointer}/not_applicable_dimensions")
        if set(required) & set(not_applicable) or set(required) | set(not_applicable) != DIMENSION_SET:
            _fail("REF009_DIMENSION_PARTITION_INCOMPLETE", pointer)
        target_by_id[target_id] = target
        target_order[target_id] = index

    assets_by_id: dict[str, dict[str, Any]] = {}
    required_assets: list[str] = []
    supporting_assets: list[str] = []
    for index, raw in enumerate(
        _array(manifest["assets"], "/reference_manifest/assets", minimum=1, maximum=64)
    ):
        pointer = f"/reference_manifest/assets/{index}"
        asset = _object(raw, ASSET_KEYS, pointer)
        asset_id = _identifier(asset["asset_id"], f"{pointer}/asset_id")
        if asset_id in assets_by_id:
            _fail("ASSET_ID_DUPLICATE", f"{pointer}/asset_id")
        media_type = _enum(asset["media_type"], {"image", "video", "audio"}, f"{pointer}/media_type", "REF008_MEDIA_INVALID")
        use = _enum(asset["use"], ASSET_USES, f"{pointer}/use", "REFERENCE_USE_INVALID")
        status = _enum(asset["selection_status"], {"required", "supporting"}, f"{pointer}/selection_status", "SELECTION_STATUS_INVALID")
        selector = _identifier(asset["subject_selector"], f"{pointer}/subject_selector")
        if selector not in target_by_id:
            _fail("ASSET_TARGET_UNKNOWN", f"{pointer}/subject_selector")
        locator = _object(asset["subject_locator"], SUBJECT_LOCATOR_KEYS, f"{pointer}/subject_locator")
        locator_method = _enum(
            locator["method"],
            {"whole_asset", "single_subject", "position", "role", "visible_feature", "speaker_label"},
            f"{pointer}/subject_locator/method",
            "REF007_SUBJECT_LOCATOR_INVALID",
        )
        _text(locator["description"], f"{pointer}/subject_locator/description")
        _dimension_set(asset["observed_leakage_dimensions"], f"{pointer}/observed_leakage_dimensions")
        if asset["preflight_status"] != "inspected":
            _fail("REF007_PREFLIGHT_INCOMPLETE", f"{pointer}/preflight_status")
        _validate_preflight(asset, pointer)
        preflight = asset["preflight"]
        subject_count = (
            preflight["subject_count"]
            if media_type == "image"
            else preflight["actor_count"]
            if media_type == "video"
            else preflight["speaker_count"]
        )
        if locator_method == "single_subject" and subject_count != 1:
            _fail("REF007_SUBJECT_LOCATOR_AMBIGUOUS", f"{pointer}/subject_locator")
        if subject_count > 1:
            allowed_multi = (
                {"role", "speaker_label"}
                if media_type == "audio"
                else {"position", "role", "visible_feature"}
            )
            if locator_method not in allowed_multi:
                _fail("REF007_SUBJECT_LOCATOR_AMBIGUOUS", f"{pointer}/subject_locator")
        if locator_method == "speaker_label" and media_type != "audio":
            _fail("REF007_SUBJECT_LOCATOR_INVALID", f"{pointer}/subject_locator/method")
        if operation != "first_last_frame" and (
            use in {"opening_frame", "endpoint_frame"}
            or (
                media_type == "image"
                and preflight["composition_use"] in {"opening_frame", "endpoint_frame"}
            )
        ):
            _fail("REF003_STRUCTURED_ROLE_USE_MISMATCH", f"{pointer}/use")
        rights = _object(asset["rights"], RIGHTS_KEYS, f"{pointer}/rights")
        for field in sorted(RIGHTS_KEYS):
            _enum(rights[field], RIGHT_VALUES, f"{pointer}/rights/{field}", "REF010_RIGHT_ASSERTION_INVALID")
        if rights["media_use"] != "user_asserted_authorized":
            _fail("REF010_MEDIA_USE_NOT_AUTHORIZED", f"{pointer}/rights/media_use")
        assets_by_id[asset_id] = asset
        (required_assets if status == "required" else supporting_assets).append(asset_id)

    if operation == "first_last_frame":
        opening_assets = [asset for asset in assets_by_id.values() if asset["use"] == "opening_frame"]
        endpoint_assets = [asset for asset in assets_by_id.values() if asset["use"] == "endpoint_frame"]
        if len(opening_assets) != 1 or len(endpoint_assets) != 1 or len(assets_by_id) != 2:
            _fail("REF003_STRUCTURED_ROLE_SET_INVALID", "/reference_manifest/assets")
        for asset, expected in ((opening_assets[0], "opening_frame"), (endpoint_assets[0], "endpoint_frame")):
            if (
                asset["media_type"] != "image"
                or asset["preflight"]["composition_use"] != expected
            ):
                _fail("REF003_STRUCTURED_ROLE_USE_MISMATCH", "/reference_manifest/assets")

    selection_order = _unique_ids(
        manifest["selection_order"], "/reference_manifest/selection_order", minimum=1, maximum=64
    )
    if set(selection_order) != set(assets_by_id):
        _fail("REF006_SELECTION_SET_MISMATCH", "/reference_manifest/selection_order")
    first_supporting = next(
        (index for index, asset_id in enumerate(selection_order) if assets_by_id[asset_id]["selection_status"] == "supporting"),
        len(selection_order),
    )
    if any(assets_by_id[item]["selection_status"] == "required" for item in selection_order[first_supporting:]):
        _fail("REF006_SELECTION_ORDER_INVALID", "/reference_manifest/selection_order")
    ablation_order = _unique_ids(
        manifest["ablation_order"], "/reference_manifest/ablation_order", maximum=64
    )
    expected_ablation = [item for item in reversed(selection_order) if item in set(supporting_assets)]
    if ablation_order != expected_ablation:
        _fail("REF006_ABLATION_ORDER_INVALID", "/reference_manifest/ablation_order")

    assignment_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    won_by_asset: dict[str, set[str]] = {asset_id: set() for asset_id in assets_by_id}
    assignment_pointer: dict[tuple[str, str], str] = {}
    for index, raw in enumerate(
        _array(
            manifest["authority_assignments"],
            "/reference_manifest/authority_assignments",
            minimum=1,
            maximum=832,
        )
    ):
        pointer = f"/reference_manifest/authority_assignments/{index}"
        assignment = _object(raw, ASSIGNMENT_KEYS, pointer)
        target_id = _identifier(assignment["target_id"], f"{pointer}/target_id")
        if target_id not in target_by_id:
            _fail("AUTHORITY_TARGET_UNKNOWN", f"{pointer}/target_id")
        dimension = _enum(assignment["dimension"], DIMENSION_SET, f"{pointer}/dimension", "REFERENCE_DIMENSION_INVALID")
        if dimension not in target_by_id[target_id]["required_dimensions"]:
            _fail("REF009_AUTHORITY_NOT_REQUIRED", f"{pointer}/dimension")
        key = (target_id, dimension)
        if key in assignment_by_key:
            _fail("REF002_MULTIPLE_WINNERS", pointer)
        winner = _identifier(assignment["winner_asset_id"], f"{pointer}/winner_asset_id")
        if winner not in assets_by_id:
            _fail("REF009_WINNER_UNKNOWN", f"{pointer}/winner_asset_id")
        if assets_by_id[winner]["subject_selector"] != target_id:
            _fail("REF009_WINNER_TARGET_MISMATCH", f"{pointer}/winner_asset_id")
        excluded = _unique_ids(assignment["excluded_asset_ids"], f"{pointer}/excluded_asset_ids", maximum=63)
        if winner in excluded or any(item not in assets_by_id for item in excluded):
            _fail("REF005_EXCLUDED_ASSET_INVALID", f"{pointer}/excluded_asset_ids")
        _enum(assignment["priority"], {"required", "supporting"}, f"{pointer}/priority", "AUTHORITY_PRIORITY_INVALID")
        _enum(assignment["confidence"], {"high", "medium", "low"}, f"{pointer}/confidence", "AUTHORITY_CONFIDENCE_INVALID")
        excluded_dimensions = _dimension_set(
            assignment["excluded_transfer_dimensions"], f"{pointer}/excluded_transfer_dimensions"
        )
        leakage = _dimension_set(assignment["leakage_risks"], f"{pointer}/leakage_risks")
        resolved = _dimension_set(assignment["resolved_leakage"], f"{pointer}/resolved_leakage")
        if dimension in excluded_dimensions or dimension in leakage or dimension in resolved:
            _fail("REF005_WINNER_DIMENSION_EXCLUDED", pointer)
        if set(leakage) != set(resolved) or not set(leakage).issubset(excluded_dimensions):
            _fail("REF005_UNRESOLVED_LEAKAGE", pointer)
        criteria = _array(assignment["acceptance_criteria"], f"{pointer}/acceptance_criteria", minimum=1, maximum=16)
        checked_criteria = [_text(item, f"{pointer}/acceptance_criteria/{offset}") for offset, item in enumerate(criteria)]
        if len(checked_criteria) != len(set(checked_criteria)):
            _fail("ACCEPTANCE_CRITERION_DUPLICATE", f"{pointer}/acceptance_criteria")
        assignment_by_key[key] = assignment
        assignment_pointer[key] = pointer
        won_by_asset[winner].add(dimension)

    expected_keys = {
        (target_id, dimension)
        for target_id, target in target_by_id.items()
        for dimension in target["required_dimensions"]
    }
    if set(assignment_by_key) != expected_keys:
        _fail("REF009_AUTHORITY_MATRIX_INCOMPLETE", "/reference_manifest/authority_assignments")
    if any(not dimensions for dimensions in won_by_asset.values()):
        _fail("REF006_PURPOSELESS_ASSET", "/reference_manifest/assets")

    # First/last-frame transfer has a tighter semantic contract than the
    # generic use-to-authority matrix. Validate that contract first so an
    # inverted frame pair reports the actionable structured-role failure.
    if operation == "first_last_frame":
        opening_asset_id = next(
            asset_id for asset_id, asset in assets_by_id.items() if asset["use"] == "opening_frame"
        )
        endpoint_asset_id = next(
            asset_id for asset_id, asset in assets_by_id.items() if asset["use"] == "endpoint_frame"
        )
        opening_rows = [
            assignment
            for (target_id, dimension), assignment in assignment_by_key.items()
            if dimension == "opening_composition"
        ]
        endpoint_rows = [
            assignment
            for (target_id, dimension), assignment in assignment_by_key.items()
            if dimension == "endpoint"
        ]
        if (
            len(opening_rows) != 1
            or len(endpoint_rows) != 1
            or opening_rows[0]["winner_asset_id"] != opening_asset_id
            or endpoint_rows[0]["winner_asset_id"] != endpoint_asset_id
            or opening_rows[0]["target_id"] != endpoint_rows[0]["target_id"]
            or target_by_id[opening_rows[0]["target_id"]]["target_kind"] != "shot"
        ):
            _fail(
                "REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH",
                "/reference_manifest/authority_assignments",
            )

    for asset_id, asset in assets_by_id.items():
        target_id = asset["subject_selector"]
        won_dimensions = won_by_asset[asset_id]
        preflight = asset["preflight"]
        media_type = asset["media_type"]
        use = asset["use"]
        if media_type not in USE_MEDIA[use]:
            _fail("REF008_USE_MEDIA_INCOMPATIBLE", "/reference_manifest/assets")
        if not won_dimensions.issubset(MEDIA_DIMENSIONS[media_type]):
            _fail("REF008_MEDIA_DIMENSION_INCOMPATIBLE", "/reference_manifest/assets")
        if not won_dimensions & USE_DIMENSIONS[use]:
            _fail("REF008_USE_AUTHORITY_INCOMPATIBLE", "/reference_manifest/assets")
        if media_type == "video":
            if "audio_voice" in won_dimensions and not preflight["embedded_audio"]:
                _fail("REF008_MEDIA_DIMENSION_INCOMPATIBLE", "/reference_manifest/assets")
            if use == "audio_reference" and not preflight["embedded_audio"]:
                _fail("REF008_USE_MEDIA_INCOMPATIBLE", "/reference_manifest/assets")
            if preflight["camera_motion"] == "compound" and "camera_motion" in won_dimensions:
                _fail("CAM001_MULTIPLE_PRIMARY_MOVES", "/reference_manifest/assets")
        required_risks: set[str] = set()
        if media_type == "image" and (preflight["has_text"] or preflight["has_logo"]):
            required_risks.add("text_logo_treatment")
        if media_type == "video":
            if preflight["camera_motion"] not in {"locked", "unknown"}:
                required_risks.add("camera_motion")
            if preflight["subject_motion"] not in {"none", "unknown"}:
                required_risks.add("subject_motion")
            if preflight["has_voice"] or preflight["has_music"]:
                required_risks.add("audio_voice")
        if media_type == "audio":
            if preflight["has_voice"] or preflight["has_music"]:
                required_risks.add("audio_voice")
            if preflight["timing_useful"]:
                required_risks.add("timing_rhythm")
        missing_risks = required_risks - won_dimensions - set(asset["observed_leakage_dimensions"])
        if missing_risks:
            _fail("REF005_PREFLIGHT_RISK_UNDECLARED", "/reference_manifest/assets")

        for leakage_dimension in asset["observed_leakage_dimensions"]:
            if leakage_dimension in won_dimensions:
                continue
            if leakage_dimension in target_by_id[target_id]["required_dimensions"]:
                assignment = assignment_by_key[(target_id, leakage_dimension)]
                if asset_id not in assignment["excluded_asset_ids"]:
                    _fail("REF005_LEAKAGE_ASSET_NOT_EXCLUDED", assignment_pointer[(target_id, leakage_dimension)])
            if not any(
                leakage_dimension in assignment["resolved_leakage"]
                for assignment in assignment_by_key.values()
                if assignment["winner_asset_id"] == asset_id
            ):
                _fail("REF005_UNRESOLVED_LEAKAGE", "/reference_manifest/authority_assignments")

        rights = asset["rights"]
        target_kind = target_by_id[target_id]["target_kind"]
        if (
            media_type == "image"
            and preflight["view_layout"] == "multiview_collage"
            and won_dimensions
            & {
                "identity",
                "face_detail",
                "wardrobe",
                "product_object_geometry",
                "opening_composition",
                "endpoint",
            }
            and asset["subject_locator"]["method"]
            not in {"position", "role", "visible_feature"}
        ):
            _fail("REF004_COLLAGE_RISK", "/reference_manifest/assets")
        if target_kind == "character" and won_dimensions & {"identity", "face_detail"}:
            if not _right_sufficient(rights["likeness"]):
                _fail("REF010_LIKENESS_NOT_AUTHORIZED", "/reference_manifest/assets")
        if "audio_voice" in won_dimensions and media_type in {"audio", "video"}:
            if preflight["has_voice"] and rights["voice_performance"] != "user_asserted_authorized":
                _fail("REF010_VOICE_NOT_AUTHORIZED", "/reference_manifest/assets")
            if preflight["has_music"] and rights["music"] != "user_asserted_authorized":
                _fail("REF010_MUSIC_NOT_AUTHORIZED", "/reference_manifest/assets")
        has_logo = media_type == "image" and preflight["has_logo"]
        has_text = media_type == "image" and preflight["has_text"]
        if (
            "text_logo_treatment" in won_dimensions
            and has_logo
            and rights["brand_logo"] != "user_asserted_authorized"
        ):
            _fail("REF010_BRAND_NOT_AUTHORIZED", "/reference_manifest/assets")
        if (
            "text_logo_treatment" in won_dimensions
            and has_text
            and not has_logo
            and not _right_sufficient(rights["brand_logo"])
        ):
            _fail("REF010_BRAND_NOT_AUTHORIZED", "/reference_manifest/assets")

    return manifest


def _align_binding_plan(
    manifest: dict[str, Any],
    binding_plan: object,
    *,
    preview_candidate: bool,
    today: date | None,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = bindings.validate_plan(binding_plan)
    if plan["profile_id"] != manifest["profile_id"] or plan["operation"] != manifest["operation"]:
        _fail("REF001_BINDING_PROFILE_MISMATCH", "/binding_plan")
    render = bindings.render_plan(
        plan,
        preview_candidate=preview_candidate,
        today=today,
        root=root,
    )
    assets = {item["asset_id"]: item for item in manifest["assets"]}
    request_bindings = {item["binding_id"]: item for item in render["request_bindings"]}
    if set(assets) != set(request_bindings):
        _fail("REF001_BINDING_SET_MISMATCH", "/binding_plan/bindings")
    for asset_id, asset in assets.items():
        if request_bindings[asset_id]["media_type"] != asset["media_type"]:
            _fail("REF008_BINDING_MEDIA_MISMATCH", "/binding_plan/bindings")

    if manifest["operation"] == "first_last_frame":
        role_assets = {
            item["structured_role"]: item["binding_id"] for item in render["request_bindings"]
        }
        first_id = role_assets["first_frame"]
        last_id = role_assets["last_frame"]
        if assets[first_id]["use"] != "opening_frame" or assets[last_id]["use"] != "endpoint_frame":
            _fail("REF003_STRUCTURED_ROLE_USE_MISMATCH", "/reference_manifest/assets")
        opening_rows = [
            item
            for item in manifest["authority_assignments"]
            if item["dimension"] == "opening_composition"
        ]
        endpoint_rows = [
            item
            for item in manifest["authority_assignments"]
            if item["dimension"] == "endpoint"
        ]
        targets = {target["target_id"]: target for target in manifest["targets"]}
        if (
            len(opening_rows) != 1
            or len(endpoint_rows) != 1
            or opening_rows[0]["winner_asset_id"] != first_id
            or endpoint_rows[0]["winner_asset_id"] != last_id
            or opening_rows[0]["target_id"] != endpoint_rows[0]["target_id"]
            or targets[opening_rows[0]["target_id"]]["target_kind"] != "shot"
        ):
            _fail("REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH", "/reference_manifest/authority_assignments")
    return plan, render


def _align_manifest_targets_to_scene(
    manifest: dict[str, Any], scene: dict[str, Any]
) -> None:
    """Prevent authority and causal plans from silently naming different subjects."""

    scene_entities = {entity["entity_id"]: entity for entity in scene["entities"]}
    scene_shots = {shot["shot_id"] for shot in scene["shots"]}
    scene_audio = {audio["audio_event_id"]: audio for audio in scene["audio_events"]}
    linked_kinds = {"character", "product", "object", "environment"}
    for index, target in enumerate(manifest["targets"]):
        target_id = target["target_id"]
        target_kind = target["target_kind"]
        pointer = f"/reference_manifest/targets/{index}"
        if target_kind == "shot":
            if target_id not in scene_shots:
                _fail("REF009_SHOT_TARGET_NOT_IN_SCENE", f"{pointer}/target_id")
            continue
        if target_kind == "audio":
            if target_id not in scene_audio:
                _fail("REF009_AUDIO_TARGET_NOT_IN_SCENE", f"{pointer}/target_id")
            continue
        if target_kind == "text_logo":
            entity = scene_entities.get(target_id)
            if entity is None or entity["kind"] != "text":
                _fail("REF009_TEXT_TARGET_NOT_IN_SCENE", f"{pointer}/target_id")
            continue
        if target_kind not in linked_kinds:
            _fail("REF009_TARGET_KIND_UNSUPPORTED", f"{pointer}/target_kind")
        entity = scene_entities.get(target_id)
        if entity is None:
            _fail(
                "REF009_TARGET_NOT_IN_SCENE",
                f"{pointer}/target_id",
            )
        if entity["kind"] != target_kind:
            _fail(
                "REF009_TARGET_KIND_MISMATCH",
                f"{pointer}/target_kind",
            )
        if "audio_voice" in target["required_dimensions"] and not any(
            target_id in audio["source_entity_ids"] for audio in scene_audio.values()
        ):
            _fail("REF009_AUDIO_TARGET_NOT_IN_SCENE", f"{pointer}/target_id")


def plan_request(
    value: object,
    *,
    preview_candidate: bool = False,
    today: date | None = None,
    root: Path = bindings.ROOT,
) -> dict[str, Any]:
    """Validate a strict planning envelope and emit its deterministic report."""

    request = _object(value, REQUEST_KEYS, "/")
    if not bindings._is_int(request["schema_version"]) or request["schema_version"] != 1:
        _fail("PLANNING_REQUEST_VERSION_UNSUPPORTED", "/schema_version")
    if not preview_candidate:
        _fail("PROFILE_CANDIDATE_REQUIRES_PREVIEW", "/reference_manifest/profile_id")
    manifest = validate_reference_manifest(request["reference_manifest"])
    scene = scene_ir_check.validate_scene_ir(request["scene_ir"])
    _align_manifest_targets_to_scene(manifest, scene)
    plan, render = _align_binding_plan(
        manifest,
        request["binding_plan"],
        preview_candidate=preview_candidate,
        today=today,
        root=root,
    )

    target_order = {
        target["target_id"]: index for index, target in enumerate(manifest["targets"])
    }
    dimension_order = {dimension: index for index, dimension in enumerate(DIMENSIONS)}
    authority_matrix = sorted(
        (
            {
                "target_id": item["target_id"],
                "dimension": item["dimension"],
                "winner_asset_id": item["winner_asset_id"],
            }
            for item in manifest["authority_assignments"]
        ),
        key=lambda item: (target_order[item["target_id"]], dimension_order[item["dimension"]]),
    )
    return {
        "$schema": PLANNING_REPORT_SCHEMA_URI,
        "schema_version": 1,
        "status": "ready",
        "profile_id": manifest["profile_id"],
        "profile_status": render["profile_status"],
        "preview": True,
        "operation": manifest["operation"],
        "reference_manifest_sha256": bindings.sha256_bytes(bindings.canonical_json(manifest)),
        "scene_ir_sha256": bindings.sha256_bytes(bindings.canonical_json(scene)),
        "binding_plan_sha256": bindings.sha256_bytes(bindings.canonical_json(plan)),
        "selected_asset_ids": list(manifest["selection_order"]),
        "selection_order": list(manifest["selection_order"]),
        "ablation_order": list(manifest["ablation_order"]),
        "authority_matrix": authority_matrix,
        "causal_order": scene_ir_check.causal_order(scene),
        "evidence_claim_ids": render["evidence_claim_ids"],
        "evidence_expires_at": render["evidence_expires_at"],
        "diagnostics": [
            {
                "code": "CANDIDATE_PREVIEW_ONLY",
                "severity": "warning",
                "pointer": "/preview",
            },
            {
                "code": "CAUSAL_IR_IS_PLANNING_HEURISTIC",
                "severity": "info",
                "pointer": "/causal_order",
            },
        ],
    }


def _self_test() -> None:
    try:
        bindings.parse_json_bytes(b'{"schema_version":1,"schema_version":1}')
    except bindings.BindingError as exc:
        if exc.code != "JSON_DUPLICATE_KEY":
            _fail("SELF_TEST_FAILED")
    else:
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a V7 reference/scene/binding envelope from stdin."
    )
    parser.add_argument(
        "--preview-candidate",
        action="store_true",
        help="exercise disabled candidate profiles; emitted report remains preview-only",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("reference planner self-test passed")
            return 0
        raw = sys.stdin.buffer.read(bindings.MAX_INPUT_BYTES + 1)
        if len(raw) > bindings.MAX_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        request = bindings.parse_json_bytes(raw)
        report = plan_request(request, preview_candidate=args.preview_candidate)
        payload = bindings.canonical_json(report)
    except bindings.BindingError as exc:
        print(f"reference-planner error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
