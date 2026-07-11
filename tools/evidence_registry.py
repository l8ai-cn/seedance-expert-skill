#!/usr/bin/env python3
"""Strict, offline claim-level evidence registry for the Seedance v7 rebuild."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
EVIDENCE = ROOT / "research" / "evidence"
CLAIMS = EVIDENCE / "claims"
SOURCES = EVIDENCE / "sources"
CAPTURES = EVIDENCE / "captures"
AUTHORITIES = EVIDENCE / "authorities.json"
RUNTIME_MAP = EVIDENCE / "runtime-map.json"
RELEASE_POLICY = EVIDENCE / "release-policy.json"
RUNTIME_MANIFEST = ROOT / "runtime" / "seedance-20.manifest.json"

CLAIM_SCHEMA = SCHEMAS / "evidence-claim.schema.json"
SOURCE_SCHEMA = SCHEMAS / "evidence-source.schema.json"
CAPTURE_SCHEMA = SCHEMAS / "evidence-capture.schema.json"
AUTHORITY_SCHEMA = SCHEMAS / "evidence-authorities.schema.json"
RUNTIME_MAP_SCHEMA = SCHEMAS / "evidence-runtime-map.schema.json"
POLICY_SCHEMA = SCHEMAS / "evidence-policy.schema.json"

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 48
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
PORTABLE_SEGMENT = re.compile(r"^[^<>:\"|?*\x00-\x1f]+$")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
UNSAFE_RENDER_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")
SURROGATE_CHARS = re.compile(r"[\ud800-\udfff]")

TTL_LIMITS = {
    "pricing": 1,
    "model_id": 1,
    "api_field": 7,
    "prompt_grammar": 30,
    "model_capability": 180,
    "workflow": 60,
    "official_example": 30,
    "release_watchlist": 7,
    "annotation_ontology": 180,
    "community_pattern": 30,
}

CLAIM_SOURCE_TYPES = {
    "pricing": {"first_party_platform_doc", "provider_owned_doc"},
    "model_id": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "api_field": {"first_party_platform_doc", "provider_owned_doc"},
    "prompt_grammar": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "model_capability": {"first_party_model_doc", "provider_authored_model_card"},
    "workflow": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "official_example": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "release_watchlist": {"first_party_model_doc", "first_party_platform_doc"},
    "annotation_ontology": {"third_party_dataset", "research_paper"},
    "community_pattern": {"community_source", "research_paper", "third_party_dataset"},
}

RELATION_INVERSES = {
    "supports": "supported_by",
    "supported_by": "supports",
    "qualifies": "qualified_by",
    "qualified_by": "qualifies",
    "tension_with": "tension_with",
}
CRITICALITY_RANK = {"informational": 0, "important": 1, "critical": 2}
CONFIDENCE_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
SUCCESSFUL_RETRIEVALS = {"fetched", "browser_verified"}
TEXT_SUFFIXES = {"", ".json", ".md", ".py", ".yaml", ".yml", ".txt"}
SECURE_DIRFD_SUPPORTED = (
    bool(getattr(os, "O_NOFOLLOW", 0))
    and bool(getattr(os, "O_DIRECTORY", 0))
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)
V7_REQUIRED_LINEAGE_ROOTS = {
    "bp.assets.purposeful-set",
    "bp.binding.spaced-example-token",
    "bp.camera.one-move",
    "bp.character.headshot-fullbody",
    "bp.operation.edit-extend-classifier",
    "bp.subject.stable-label",
    "bp.timing.exact-caution",
    "bytedance.model.multimodal-inputs",
    "bytedance.model.reference-control",
    "contra.annotation.observable-dimensions",
    "fal.binding.at-ordinal",
    "fal.input.seed-absent",
    "fal.resolution.standard-4k",
    "global.binding.no-universal-token",
    "volc.binding.asset-ordinal",
    "volc.binding.first-last-frame-role",
    "volc.timing.exact-example",
}
V7_CLEAN_RUNTIME_PATHS = {
    "LICENSE",
    "agents/openai.yaml",
    "examples/sequence-airport-arrival/clip-01-take-review.json",
    "examples/sequence-observed-deviation/take-review.json",
    "references/continuity-qc.md",
    "references/surface-prompt-profiles.md",
    "schemas/clip-contract.schema.json",
    "schemas/generation-run.schema.json",
    "schemas/prompt-spec.schema.json",
    "schemas/take-review.schema.json",
    "scripts/extract_last_frame.py",
}
V705_CANDIDATE_PROFILE_PATHS = {
    "profiles/models/seedance-2.0-model.json": "seedance-2.0-model",
    "profiles/surfaces/byteplus-modelark.json": "byteplus.modelark",
    "profiles/surfaces/fal-reference-to-video.json": "fal.reference-to-video",
    "profiles/surfaces/volcengine-ark.json": "volcengine.ark",
}
V705_CLEAN_RUNTIME_PATHS = (
    V7_CLEAN_RUNTIME_PATHS
    - {"references/surface-prompt-profiles.md"}
    | {
        "profiles/profile-index.json",
        "schemas/binding-plan.schema.json",
        "schemas/binding-render.schema.json",
        "schemas/model-profile.schema.json",
        "schemas/planning-report.schema.json",
        "schemas/profile-index.schema.json",
        "schemas/reference-manifest.schema.json",
        "schemas/scene-ir.schema.json",
        "schemas/surface-profile.schema.json",
        "scripts/reference_planner.py",
        "scripts/render_surface_bindings.py",
        "scripts/scene_ir_check.py",
    }
)
V7_AUTHORITIES_SHA256 = "f7f62449d52aa7c096d14e26e21dd4fdcc40d7458cf1d696cf7b4c2949a4c16b"
V7_SOURCE_RECORD_SHA256 = {
    "bytedance.seedance-2-0.model-page.2026-07-11": "9914a258a746fd88c4c3e8d853283e5184c2110e06a59a4c1f45426a24f13203",
    "byteplus.prompt-guide.2222480.2026-07-11": "721a4df57104731951904c050e5baba76b8cbd10ee9f1e7caece5809118d105b",
    "contra.video-detail-annotation.2026-07-11": "d87abbd06f0ba50083f872ee12369fcae2a0804640792f9478ffb2d5b6468184",
    "contra.video-detail-annotation-csv.2026-07-11": "5b18a7d17e288a3d965bc62f2b4bd69df37bbb4424aaeaeab1d7a50091ce1973",
    "fal.reference-to-video.2026-07-11": "20865b3d27883770e41f187ea702d3597c02ee641a268c83b2c4673b926e0e9b",
    "volcengine.tutorial.2291680.2026-07-11": "fb3b43c92fc92f9ef9f0cf4839196dd865c17ae963cd6d7a375a3da5169ab801",
}
V7_POLICY_BASELINE = {
    "bp.assets.purposeful-set": ("reference.selection.minimum-purposeful-set", "important", "supported", "candidate", "byteplus.modelark", "tests/test_evidence_registry.py#test_byteplus_claims_remain_surface_scoped"),
    "bp.binding.spaced-example-token": ("reference.binding.image.ordinal", "critical", "supported", "candidate", "byteplus.modelark", "evals/evals.json#exact_reference_tag_preserved"),
    "bp.camera.one-move": ("prompt.camera.primary_moves_per_shot", "important", "supported", "candidate", "byteplus.modelark", "evals/evals.json#camera_has_start_path_and_endpoint"),
    "bp.character.headshot-fullbody": ("reference.character.preflight", "important", "supported", "candidate", "byteplus.modelark", "tests/test_evidence_registry.py#test_byteplus_claims_remain_surface_scoped"),
    "bp.operation.edit-extend-classifier": ("prompt.operation.edit_extend.reference_prefix", "critical", "supported", "candidate", "byteplus.modelark", "evals/evals.json#edit_extend_vs_regenerate"),
    "bp.subject.stable-label": ("prompt.subject.stable-label", "important", "supported", "candidate", "byteplus.modelark", "evals/evals.json#multi_character_scene"),
    "bp.timing.exact-caution": ("prompt.timing.exact-seconds", "important", "supported", "candidate", "byteplus.modelark", "evals/evals.json#multishot_uses_shot_labels_not_continuous_take"),
    "bytedance.model.multimodal-inputs": ("model.input.modalities", "important", "supported", "candidate", "seedance-2.0-model", "tests/test_evidence_registry.py#test_bytedance_claims_remain_model_level"),
    "bytedance.model.reference-control": ("model.reference.control-dimensions", "important", "supported", "candidate", "seedance-2.0-model", "tests/test_evidence_registry.py#test_bytedance_claims_remain_model_level"),
    "contra.annotation.observable-dimensions": ("evaluation.annotation.observable-dimensions", "informational", "supported", "research_only", "future.benchmark-ontology", "tests/test_evidence_registry.py#test_contra_dataset_is_research_only_not_model_or_prompt_proof"),
    "fal.binding.at-ordinal": ("reference.binding.image.ordinal", "critical", "supported", "candidate", "fal.reference-to-video", "evals/evals.json#exact_reference_tag_preserved"),
    "fal.input.seed-absent": ("provider.fal.reference.input.seed", "critical", "supported", "candidate", "fal.reference-to-video", "tests/test_evidence_registry.py#test_provider_reference_tokens_are_explicitly_surface_scoped"),
    "fal.resolution.standard-4k": ("provider.fal.reference.resolution", "important", "supported", "candidate", "fal.reference-to-video", "tests/test_evidence_registry.py#test_provider_reference_tokens_are_explicitly_surface_scoped"),
    "global.binding.no-universal-token": ("reference.binding.universal-token", "critical", "supported", "candidate", "byteplus.modelark", "evals/evals.json#exact_reference_tag_preserved"),
    "volc.binding.asset-ordinal": ("reference.binding.image.ordinal", "critical", "supported", "candidate", "volcengine.ark", "evals/evals.json#exact_reference_tag_preserved"),
    "volc.binding.first-last-frame-role": ("reference.binding.frame-role", "critical", "supported", "candidate", "volcengine.ark", "evals/evals.json#first_last_frame_workflow"),
    "volc.timing.exact-example": ("prompt.timing.exact-seconds", "important", "supported", "candidate", "volcengine.ark", "tests/test_evidence_registry.py#test_volcengine_claims_remain_surface_scoped"),
}
V7_CLAIM_BASELINE = {
    "bp.assets.purposeful-set": ("workflow", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.binding.spaced-example-token": ("official_example", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.camera.one-move": ("prompt_grammar", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.character.headshot-fullbody": ("workflow", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.operation.edit-extend-classifier": ("prompt_grammar", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.subject.stable-label": ("prompt_grammar", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bp.timing.exact-caution": ("prompt_grammar", "volatile", 30, "seedance", "2.0-series", {"byteplus.modelark"}),
    "bytedance.model.multimodal-inputs": ("model_capability", "stable", 180, "seedance", "2.0", {"model"}),
    "bytedance.model.reference-control": ("model_capability", "stable", 180, "seedance", "2.0", {"model"}),
    "contra.annotation.observable-dimensions": ("annotation_ontology", "stable", 180, "cross-model", "dataset-2026-07-02", {"research"}),
    "fal.binding.at-ordinal": ("api_field", "volatile", 7, "seedance", "2.0-series", {"fal.reference-to-video"}),
    "fal.input.seed-absent": ("api_field", "volatile", 7, "seedance", "2.0-series", {"fal.reference-to-video"}),
    "fal.resolution.standard-4k": ("api_field", "volatile", 7, "seedance", "2.0-series", {"fal.reference-to-video"}),
    "global.binding.no-universal-token": ("workflow", "volatile", 7, "seedance", "2.0-series", {"byteplus.modelark", "fal.reference-to-video", "volcengine.ark"}),
    "volc.binding.asset-ordinal": ("api_field", "volatile", 7, "seedance", "2.0-series", {"volcengine.ark"}),
    "volc.binding.first-last-frame-role": ("api_field", "volatile", 7, "seedance", "2.0-series", {"volcengine.ark"}),
    "volc.timing.exact-example": ("official_example", "volatile", 30, "seedance", "2.0-series", {"volcengine.ark"}),
}
V7_SEMANTIC_BASELINE = {
    "bp.assets.purposeful-set": ({"reference_generation"}, "en", "global", "high", "060d196179dec90bb358f8a4c746d8ea326c54903be0dc24ede85ee8ce14f6d8"),
    "bp.binding.spaced-example-token": ({"reference_generation"}, "en", "global", "high", "0c88d0e657eba9968f55823b0f203ffd9f613fff7d96b7285715da62e155b99d"),
    "bp.camera.one-move": ({"reference_generation"}, "en", "global", "high", "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"),
    "bp.character.headshot-fullbody": ({"reference_generation"}, "en", "global", "high", "f7f43d46b67360d92409e50599002d3d72a5c4232f7b124980fda49f8bcf3948"),
    "bp.operation.edit-extend-classifier": ({"edit", "extend"}, "en", "global", "high", "2e72472f7c4ac32778b04f21a4928185833cb5f71080ee0516671459ee37cf36"),
    "bp.subject.stable-label": ({"reference_generation"}, "en", "global", "high", "54ec028547c4e1f170cb104566ca822bb3d1000167b3027dd6013da216d4dbe9"),
    "bp.timing.exact-caution": ({"multi_shot"}, "en", "global", "high", "c4223b8564075bc188f09454e40b3d76a51ac7b3e20a342d77c60d726117fc4c"),
    "bytedance.model.multimodal-inputs": ({"generation"}, "en", "global", "high", "67755b636ea8df31660234e3bc303beb32981761a47fa48b1411af53938cf41d"),
    "bytedance.model.reference-control": ({"reference_generation"}, "en", "global", "high", "f7af0d800d87c6bc47cee5380583e2c2b6bc06cb046938d6d8109408c20805f0"),
    "contra.annotation.observable-dimensions": ({"video_evaluation"}, "en", "global", "medium", "f0c54b216d546f016fb2ab3db7ce5e5f8d3df57778a1f4aaa91015525dd5bd8f"),
    "fal.binding.at-ordinal": ({"reference_generation"}, "en", "global", "high", "cf5b39cccbd254836b9c5b4b5b3814bb18c8a344f6b0d36422fc39dfc9096298"),
    "fal.input.seed-absent": ({"reference_generation"}, "en", "global", "high", "fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa"),
    "fal.resolution.standard-4k": ({"reference_generation"}, "en", "global", "high", "83172282fbb8e122629a80fa0afc5df95076fcb5f33ab38fa7274d9e93f5b47e"),
    "global.binding.no-universal-token": ({"reference_generation"}, "multilingual", "global", "high", "fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa"),
    "volc.binding.asset-ordinal": ({"reference_generation"}, "zh-CN", "CN", "high", "8265266dd7d0ca28642c6b0e59550978de4fe87375b1e0bf03931aae00c4e091"),
    "volc.binding.first-last-frame-role": ({"first_last_frame"}, "zh-CN", "CN", "high", "095e1cabe99be8824af05b4e0074c5afa9b66cc0c26fbd1218b75c7a8779ccbf"),
    "volc.timing.exact-example": ({"reference_generation", "multi_shot"}, "zh-CN", "CN", "high", "19290241733ca162c57071cee39add6f26861f52c7d2817a161a67195c5e646c"),
}
V7_QUALIFIED_RELATIONS = {
    "bp.timing.exact-caution": {("volc.timing.exact-example", "tension_with")},
    "volc.timing.exact-example": {("bp.timing.exact-caution", "tension_with")},
}
V7_CLAIM_SOURCE_BASELINE = {
    **{
        claim_id: {"byteplus.prompt-guide.2222480.2026-07-11"}
        for claim_id in (
            "bp.assets.purposeful-set", "bp.binding.spaced-example-token", "bp.camera.one-move",
            "bp.character.headshot-fullbody", "bp.operation.edit-extend-classifier",
            "bp.subject.stable-label", "bp.timing.exact-caution",
        )
    },
    **{
        claim_id: {"bytedance.seedance-2-0.model-page.2026-07-11"}
        for claim_id in (
            "bytedance.model.multimodal-inputs", "bytedance.model.reference-control",
        )
    },
    "contra.annotation.observable-dimensions": {
        "contra.video-detail-annotation.2026-07-11",
        "contra.video-detail-annotation-csv.2026-07-11",
    },
    **{
        claim_id: {"fal.reference-to-video.2026-07-11"}
        for claim_id in (
            "fal.binding.at-ordinal", "fal.input.seed-absent", "fal.resolution.standard-4k",
        )
    },
    "global.binding.no-universal-token": {
        "byteplus.prompt-guide.2222480.2026-07-11",
        "fal.reference-to-video.2026-07-11",
        "volcengine.tutorial.2291680.2026-07-11",
    },
    **{
        claim_id: {"volcengine.tutorial.2291680.2026-07-11"}
        for claim_id in (
            "volc.binding.asset-ordinal", "volc.binding.first-last-frame-role",
            "volc.timing.exact-example",
        )
    },
}


class EvidenceError(RuntimeError):
    """Raised for deterministic registry boundary failures."""


@dataclass(frozen=True)
class LoadedRecord:
    relative_path: str
    path: Path
    raw: bytes
    sha256: str
    data: dict[str, Any]


@dataclass(frozen=True)
class RegistryLayout:
    root: Path = ROOT
    claim_schema: Path = CLAIM_SCHEMA
    source_schema: Path = SOURCE_SCHEMA
    capture_schema: Path = CAPTURE_SCHEMA
    authority_schema: Path = AUTHORITY_SCHEMA
    runtime_map_schema: Path = RUNTIME_MAP_SCHEMA
    policy_schema: Path = POLICY_SCHEMA
    claims: Path = CLAIMS
    sources: Path = SOURCES
    captures: Path = CAPTURES
    authorities: Path = AUTHORITIES
    runtime_map: Path = RUNTIME_MAP
    policy: Path = RELEASE_POLICY
    runtime_manifest: Path = RUNTIME_MANIFEST


def layout_for_root(root: Path) -> RegistryLayout:
    """Return a complete layout rooted at a repository or isolated test fixture."""
    root = root.resolve()
    schemas = root / "schemas"
    evidence = root / "research" / "evidence"
    return RegistryLayout(
        root=root,
        claim_schema=schemas / "evidence-claim.schema.json",
        source_schema=schemas / "evidence-source.schema.json",
        capture_schema=schemas / "evidence-capture.schema.json",
        authority_schema=schemas / "evidence-authorities.schema.json",
        runtime_map_schema=schemas / "evidence-runtime-map.schema.json",
        policy_schema=schemas / "evidence-policy.schema.json",
        claims=evidence / "claims",
        sources=evidence / "sources",
        captures=evidence / "captures",
        authorities=evidence / "authorities.json",
        runtime_map=evidence / "runtime-map.json",
        policy=evidence / "release-policy.json",
        runtime_manifest=root / "runtime" / "seedance-20.manifest.json",
    )


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(normalize_text(value).encode("utf-8"))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number: {value}")


def _depth(value: Any) -> int:
    maximum = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, level = stack.pop()
        maximum = max(maximum, level)
        if maximum > MAX_JSON_DEPTH:
            return maximum
        if isinstance(current, dict):
            stack.extend((item, level + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, level + 1) for item in current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise EvidenceError("non-finite JSON number")
        elif isinstance(current, str) and SURROGATE_CHARS.search(current):
            raise EvidenceError("unpaired Unicode surrogate")
    return maximum


def parse_json(raw: bytes, label: str) -> Any:
    if len(raw) > MAX_JSON_BYTES:
        raise EvidenceError(f"{label}: JSON exceeds {MAX_JSON_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{label}: invalid UTF-8: {exc}") from exc
    if text.startswith("\ufeff"):
        raise EvidenceError(f"{label}: UTF-8 BOM is forbidden")
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, EvidenceError, RecursionError, OverflowError, ValueError) as exc:
        raise EvidenceError(f"{label}: invalid strict JSON: {exc}") from exc
    try:
        depth = _depth(value)
    except EvidenceError as exc:
        raise EvidenceError(f"{label}: invalid strict JSON: {exc}") from exc
    if depth > MAX_JSON_DEPTH:
        raise EvidenceError(f"{label}: JSON nesting exceeds {MAX_JSON_DEPTH}")
    return value


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def canonical_value(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(sorted(value), ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise EvidenceError("non-finite claim value")
        return format(Decimal(str(value)).normalize(), "f")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _is_mount(path: Path) -> bool:
    try:
        return path.is_mount()
    except (NotImplementedError, OSError):
        return False


def normalize_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvidenceError(f"{label}: path must be a non-empty repository-relative POSIX path")
    if unicodedata.normalize("NFC", value) != value:
        raise EvidenceError(f"{label}: path must use NFC normalization")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise EvidenceError(f"{label}: unsafe relative path: {value!r}")
    if pure.as_posix() != value or UNSAFE_RENDER_CHARS.search(value):
        raise EvidenceError(f"{label}: path must be canonical and free of control/bidi characters: {value!r}")
    for segment in pure.parts:
        if not PORTABLE_SEGMENT.fullmatch(segment) or segment.endswith((" ", ".")):
            raise EvidenceError(f"{label}: non-portable path segment: {segment!r}")
        stem = segment.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED:
            raise EvidenceError(f"{label}: reserved path segment: {segment!r}")
    return pure.as_posix()


def read_regular_file(
    root: Path,
    value: object,
    label: str,
    *,
    allowed_parent: Path | None = None,
    max_bytes: int = MAX_JSON_BYTES,
) -> tuple[Path, bytes]:
    root = root.resolve(strict=True)
    relative = normalize_relative(value, label)
    candidate = root / relative
    if allowed_parent is not None:
        try:
            allowed_relative = Path(os.path.abspath(allowed_parent)).relative_to(
                Path(os.path.abspath(root))
            ).as_posix()
        except ValueError as exc:
            raise EvidenceError(f"{label}: allowed parent is outside repository") from exc
        if relative != allowed_relative and not relative.startswith(allowed_relative + "/"):
            raise EvidenceError(f"{label}: path is outside {allowed_parent}: {relative}")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not SECURE_DIRFD_SUPPORTED:
        raise EvidenceError(f"{label}: platform lacks secure descriptor-relative file walking")
    common_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_flags = common_flags | directory | nofollow
    descriptor_flags = common_flags | nofollow
    descriptors: list[int] = []
    directory_identities: list[tuple[int, tuple[int, int, int, int]]] = []
    descriptor: int | None = None
    try:
        root_descriptor = os.open(root, directory_flags)
        descriptors.append(root_descriptor)
        root_stat = os.fstat(root_descriptor)
        directory_identities.append((root_descriptor, (
            root_stat.st_dev, root_stat.st_ino, root_stat.st_mtime_ns, root_stat.st_ctime_ns,
        )))
        parent_descriptor = root_descriptor
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            before_directory = os.stat(part, dir_fd=parent_descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(before_directory.st_mode):
                raise EvidenceError(f"{label}: ancestor is not a plain directory: {relative}")
            child_descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
            opened_directory = os.fstat(child_descriptor)
            if (
                not stat.S_ISDIR(opened_directory.st_mode)
                or (opened_directory.st_dev, opened_directory.st_ino)
                != (before_directory.st_dev, before_directory.st_ino)
            ):
                os.close(child_descriptor)
                raise EvidenceError(f"{label}: ancestor changed while opening: {relative}")
            if opened_directory.st_dev != root_stat.st_dev:
                os.close(child_descriptor)
                raise EvidenceError(f"{label}: nested filesystem is forbidden: {relative}")
            descriptors.append(child_descriptor)
            directory_identities.append((child_descriptor, (
                opened_directory.st_dev, opened_directory.st_ino,
                opened_directory.st_mtime_ns, opened_directory.st_ctime_ns,
            )))
            parent_descriptor = child_descriptor

        leaf = parts[-1]
        before = os.stat(leaf, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceError(f"{label}: not a regular file: {relative}")
        if before.st_nlink != 1:
            raise EvidenceError(f"{label}: hard-linked files are forbidden: {relative}")
        if before.st_size > max_bytes:
            raise EvidenceError(f"{label}: file exceeds {max_bytes} bytes: {relative}")
        descriptor = os.open(leaf, descriptor_flags, dir_fd=parent_descriptor)
    except EvidenceError:
        for opened_directory in reversed(descriptors):
            os.close(opened_directory)
        raise
    except OSError as exc:
        for opened_directory in reversed(descriptors):
            os.close(opened_directory)
        raise EvidenceError(f"{label}: cannot open safely: {relative}: {exc}") from exc
    try:
        assert descriptor is not None
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise EvidenceError(f"{label}: opened object is not a unique regular file: {relative}")
        opened_identity = (
            opened.st_dev, opened.st_ino, opened.st_size,
            opened.st_mtime_ns, opened.st_ctime_ns,
        )
        before_identity = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        if opened_identity != before_identity:
            raise EvidenceError(f"{label}: file changed while opening: {relative}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        after_identity = (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
        if after_identity != opened_identity:
            raise EvidenceError(f"{label}: file changed while reading: {relative}")
        for directory_descriptor, expected_identity in directory_identities:
            current_directory = os.fstat(directory_descriptor)
            current_identity = (
                current_directory.st_dev, current_directory.st_ino,
                current_directory.st_mtime_ns, current_directory.st_ctime_ns,
            )
            if current_identity != expected_identity:
                raise EvidenceError(f"{label}: ancestor changed while reading: {relative}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for opened_directory in reversed(descriptors):
            os.close(opened_directory)
    if len(raw) > max_bytes or len(raw) != before.st_size:
        raise EvidenceError(f"{label}: incomplete or oversized read: {relative}")
    return candidate, raw


def relative_to_root(root: Path, path: Path) -> str:
    try:
        return Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError as exc:
        raise EvidenceError(f"path is outside repository: {path}") from exc


def load_one(root: Path, path: Path, label: str, *, max_bytes: int = MAX_JSON_BYTES) -> LoadedRecord:
    relative = relative_to_root(root, path)
    resolved, raw = read_regular_file(root, relative, label, max_bytes=max_bytes)
    value = parse_json(raw, label)
    if not isinstance(value, dict):
        raise EvidenceError(f"{label}: top-level JSON must be an object")
    return LoadedRecord(relative, resolved, raw, sha256_bytes(raw), value)


def load_directory(root: Path, directory: Path, label: str, *, max_bytes: int = MAX_JSON_BYTES) -> list[LoadedRecord]:
    relative_dir = relative_to_root(root, directory)
    directory_path = root / relative_dir
    if _is_link_like(directory_path) or not directory_path.is_dir():
        raise EvidenceError(f"{label}: missing or linked directory: {relative_dir}")
    records: list[LoadedRecord] = []
    for entry in sorted(os.scandir(directory_path), key=lambda item: item.name.casefold()):
        entry_path = Path(entry.path)
        if entry.name.startswith(".") or not entry.name.endswith(".json"):
            raise EvidenceError(f"{label}: unexpected entry: {entry.name}")
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or _is_link_like(entry_path):
            raise EvidenceError(f"{label}: entries must be regular non-link JSON files: {entry.name}")
        records.append(load_one(root, entry_path, f"{label}/{entry.name}", max_bytes=max_bytes))
    if not records:
        raise EvidenceError(f"{label}: directory is empty")
    folded = [unicodedata.normalize("NFC", record.relative_path).casefold() for record in records]
    if len(folded) != len(set(folded)):
        raise EvidenceError(f"{label}: file names collide after NFC/case folding")
    return records


def load_schema(root: Path, path: Path) -> dict[str, Any]:
    record = load_one(root, path, f"schema {path.name}")
    stack: list[tuple[str, Any]] = [("$", record.data)]
    while stack:
        pointer, value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{pointer}/{key}"
                if key in {"$ref", "$dynamicRef", "$recursiveRef"}:
                    raise EvidenceError(
                        f"schema {path.name}: reference-resolving keyword {key} is forbidden at {child}"
                    )
                stack.append((child, item))
        elif isinstance(value, list):
            stack.extend((f"{pointer}/{index}", item) for index, item in enumerate(value))
    try:
        Draft202012Validator.check_schema(record.data)
    except SchemaError as exc:
        raise EvidenceError(f"schema {path.name}: invalid Draft 2020-12 schema: {exc}") from exc
    return record.data


def schema_errors(schema: dict[str, Any], records: Iterable[LoadedRecord]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for record in records:
        for error in sorted(validator.iter_errors(record.data), key=lambda item: tuple(map(str, item.absolute_path))):
            pointer = "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)
            errors.append(f"{record.relative_path}{pointer}: {error.message}")
    return errors


def parse_date(value: object, label: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"{label}: expected ISO date")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label}: invalid ISO date: {value!r}")
        return None


def parse_model_generation(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z0-9]+", ".", value.casefold()).strip(".")
    match = re.search(r"(?:^|\.)(?:v)?(\d+)\.(\d+)(?:\.|$)", normalized)
    return (int(match.group(1)), int(match.group(2))) if match else None


def list_overlap(left: list[str], right: list[str]) -> bool:
    return "*" in left or "*" in right or bool(set(left) & set(right))


def scalar_overlap(left: str, right: str) -> bool:
    return left == right or left == "*" or right == "*"


def scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        list_overlap(left.get("surfaces", []), right.get("surfaces", []))
        and list_overlap(left.get("operations", []), right.get("operations", []))
        and scalar_overlap(left.get("locale", ""), right.get("locale", ""))
        and scalar_overlap(left.get("region", ""), right.get("region", ""))
    )


def _unique(records: Iterable[LoadedRecord], field: str, label: str, errors: list[str]) -> dict[str, LoadedRecord]:
    result: dict[str, LoadedRecord] = {}
    folded: dict[str, str] = {}
    for record in records:
        value = record.data.get(field)
        if not isinstance(value, str):
            continue
        key = unicodedata.normalize("NFC", value).casefold()
        if key in folded:
            errors.append(f"duplicate {label} after NFC/case folding: {folded[key]!r} and {value!r}")
        else:
            folded[key] = value
            result[value] = record
    return result


def validate_authorities(record: LoadedRecord, errors: list[str]) -> dict[str, dict[str, Any]]:
    if record.sha256 != V7_AUTHORITIES_SHA256:
        errors.append("authorities: V7-04 closed authority record byte pin mismatch")
    authorities = record.data.get("authorities", [])
    result: dict[str, dict[str, Any]] = {}
    folded: set[str] = set()
    for authority in authorities:
        authority_id = authority.get("authority_id")
        if not isinstance(authority_id, str):
            continue
        key = authority_id.casefold()
        if key in folded:
            errors.append(f"duplicate authority_id: {authority_id}")
        folded.add(key)
        result[authority_id] = authority
        if not authority.get("allow_null_url") and not authority.get("hosts"):
            errors.append(f"{authority_id}: URL-required authority must list at least one host")
    return result


def validate_url(value: object, label: str, allowed_hosts: set[str], errors: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{label}: URL must be a string or null")
        return None
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        errors.append(f"{label}: invalid port")
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port not in {None, 443}:
        errors.append(f"{label}: URL must use HTTPS, no userinfo, and port 443 only")
    host = (parsed.hostname or "").casefold()
    if host not in {item.casefold() for item in allowed_hosts}:
        errors.append(f"{label}: unapproved host: {host or '<missing>'}")
    return host


def validate_captures(
    layout: RegistryLayout,
    captures: list[LoadedRecord],
    sources: list[LoadedRecord],
    authorities: dict[str, dict[str, Any]],
    as_of: date,
    errors: list[str],
) -> tuple[dict[str, LoadedRecord], dict[str, dict[str, dict[str, Any]]], set[str]]:
    source_by_id = _unique(sources, "source_snapshot_id", "source_snapshot_id", errors)
    if set(source_by_id) != set(V7_SOURCE_RECORD_SHA256):
        errors.append("sources: V7-04 closed source snapshot set changed")
    for source_id, source_record in source_by_id.items():
        expected_source_sha = V7_SOURCE_RECORD_SHA256.get(source_id)
        if expected_source_sha is not None and source_record.sha256 != expected_source_sha:
            errors.append(f"{source_id}: V7-04 source record byte pin mismatch")
    _unique(captures, "capture_id", "capture_id", errors)
    capture_by_source: dict[str, LoadedRecord] = {}
    item_index: dict[str, dict[str, dict[str, Any]]] = {}
    verified: set[str] = set()
    used_paths: set[str] = set()

    for source_id, source_record in source_by_id.items():
        source = source_record.data
        authority_id = source.get("authority_id")
        authority = authorities.get(authority_id)
        if authority is None:
            errors.append(f"{source_id}: unknown authority_id {authority_id!r}")
            authority = {"hosts": [], "publishers": [], "source_types": [], "allow_null_url": False}
        if source.get("publisher") not in authority.get("publishers", []):
            errors.append(f"{source_id}: publisher is not approved by authority {authority_id}")
        if source.get("source_type") not in authority.get("source_types", []):
            errors.append(f"{source_id}: source_type is not approved by authority {authority_id}")
        hosts = set(authority.get("hosts", []))
        canonical_host = validate_url(source.get("canonical_url"), f"{source_id}.canonical_url", hosts, errors)
        final_host = validate_url(source.get("final_url"), f"{source_id}.final_url", hosts, errors)
        if source.get("canonical_url") is None and not authority.get("allow_null_url"):
            errors.append(f"{source_id}: authority requires a canonical URL")
        if source.get("final_url") is None and not authority.get("allow_null_url"):
            errors.append(f"{source_id}: authority requires a final URL")
        if canonical_host and final_host and final_host not in hosts:
            errors.append(f"{source_id}: final redirect host is not approved")

        retrieved = parse_date(source.get("retrieved_at"), f"{source_id}.retrieved_at", errors)
        updated_raw = source.get("document_updated_at")
        updated = parse_date(updated_raw, f"{source_id}.document_updated_at", errors) if updated_raw else None
        suffix = re.search(r"(?:^|[._-])(\d{4}-\d{2}-\d{2})$", source_id)
        if not suffix:
            errors.append(f"{source_id}: snapshot ID must end with retrieval date")
        elif retrieved and suffix.group(1) != retrieved.isoformat():
            errors.append(f"{source_id}: snapshot ID date does not equal retrieved_at")
        if retrieved and retrieved > as_of:
            errors.append(f"{source_id}: retrieval date is in the future relative to UTC as_of")
        if updated and retrieved and updated > retrieved:
            errors.append(f"{source_id}: document update date is after retrieval")
        if updated and updated > as_of:
            errors.append(f"{source_id}: document update date is in the future")
        if source.get("retrieval_status") in SUCCESSFUL_RETRIEVALS and not isinstance(source.get("raw_document_sha256"), str):
            errors.append(f"{source_id}: successful retrieval requires a raw document SHA-256")

        kind = source.get("capture_kind")
        path = source.get("capture_path")
        capture_sha = source.get("capture_sha256")
        if kind == "normalized_evidence":
            if not isinstance(path, str) or not isinstance(capture_sha, str):
                errors.append(f"{source_id}: retained capture requires path and capture SHA-256")
                continue
            if path in used_paths:
                errors.append(f"{source_id}: capture path is shared by multiple snapshots")
            used_paths.add(path)
            try:
                _capture_path, raw = read_regular_file(
                    layout.root,
                    path,
                    f"{source_id}.capture_path",
                    allowed_parent=layout.captures,
                    max_bytes=MAX_CAPTURE_BYTES,
                )
            except EvidenceError as exc:
                errors.append(str(exc))
                continue
            if sha256_bytes(raw) != capture_sha:
                errors.append(f"{source_id}: capture SHA-256 mismatch")
            matching = [record for record in captures if record.relative_path == path]
            if len(matching) != 1:
                errors.append(f"{source_id}: capture path does not resolve to exactly one registered capture")
                continue
            capture_record = matching[0]
            capture = capture_record.data
            if capture.get("source_snapshot_id") != source_id:
                errors.append(f"{source_id}: capture source_snapshot_id mismatch")
            if capture.get("capture_kind") != kind:
                errors.append(f"{source_id}: source and retained capture kinds do not match")
            for field in ("canonical_url", "final_url", "raw_document_sha256"):
                if capture.get(field) != source.get(field):
                    errors.append(f"{source_id}: capture {field} does not match source record")
            created = parse_date(capture.get("created_at"), f"{source_id}.capture.created_at", errors)
            if created and created > as_of:
                errors.append(f"{source_id}: capture date is in the future")
            if created and retrieved and created != retrieved:
                errors.append(f"{source_id}: capture date must equal source retrieval date")
            items: dict[str, dict[str, Any]] = {}
            for item in capture.get("items", []):
                item_id = item.get("evidence_item_id")
                if not isinstance(item_id, str):
                    continue
                if item_id in items:
                    errors.append(f"{source_id}: duplicate evidence_item_id {item_id}")
                items[item_id] = item
                normalized = item.get("normalized_evidence", "")
                if not isinstance(normalized, str) or sha256_text(normalized) != item.get("normalized_evidence_sha256"):
                    errors.append(f"{source_id}/{item_id}: normalized evidence hash mismatch")
                if isinstance(normalized, str) and UNSAFE_RENDER_CHARS.search(normalized):
                    errors.append(f"{source_id}/{item_id}: normalized evidence contains unsafe control characters")
            capture_by_source[source_id] = capture_record
            item_index[source_id] = items
            if sha256_bytes(raw) == capture_sha and items:
                verified.add(source_id)
        elif kind in {"hash_only", "none"}:
            if path is not None or capture_sha is not None:
                errors.append(f"{source_id}: {kind} source must not declare a retained capture")
        else:
            errors.append(f"{source_id}: unknown capture_kind {kind!r}")

    referenced_capture_paths = {record.relative_path for record in capture_by_source.values()}
    for capture in captures:
        if capture.relative_path not in referenced_capture_paths:
            errors.append(f"orphan retained capture: {capture.relative_path}")
    return source_by_id, item_index, verified


def validate_claims(
    layout: RegistryLayout,
    claims: list[LoadedRecord],
    source_by_id: dict[str, LoadedRecord],
    item_index: dict[str, dict[str, dict[str, Any]]],
    verified_captures: set[str],
    as_of: date,
    enforce_freshness: bool,
    errors: list[str],
    warnings: list[str],
) -> dict[str, LoadedRecord]:
    claim_by_id = _unique(claims, "claim_id", "claim_id", errors)
    relation_index = {
        (record.data.get("claim_id"), relation.get("claim_id"), relation.get("type"))
        for record in claims
        for relation in record.data.get("relations", [])
    }

    def validate_test_binding(test_id: object, claim_id: str) -> None:
        if not isinstance(test_id, str) or test_id.count("#") != 1:
            errors.append(f"{claim_id}: affected test must use path#exact-id syntax")
            return
        path_value, anchor = test_id.split("#", 1)
        if not anchor or not re.fullmatch(r"[A-Za-z0-9_.-]+", anchor):
            errors.append(f"{claim_id}: affected test has an unsafe or empty exact ID")
            return
        try:
            _path, raw = read_regular_file(layout.root, path_value, f"{claim_id}.affected_test")
        except EvidenceError as exc:
            errors.append(str(exc))
            return
        identifiers: list[str]
        if path_value.endswith(".json"):
            try:
                payload = parse_json(raw, f"{claim_id}.affected_test")
            except EvidenceError as exc:
                errors.append(str(exc))
                return
            cases = payload.get("cases") if isinstance(payload, dict) else None
            if not isinstance(cases, list):
                errors.append(f"{claim_id}: JSON affected test must expose a cases array")
                return
            identifiers = [
                case.get("id") for case in cases
                if isinstance(case, dict) and isinstance(case.get("id"), str)
            ]
        elif path_value.endswith(".py"):
            try:
                tree = ast.parse(raw.decode("utf-8"), filename=path_value)
            except (UnicodeDecodeError, SyntaxError) as exc:
                errors.append(f"{claim_id}: affected Python test cannot be parsed: {exc}")
                return
            identifiers = [
                node.name for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            ]
        else:
            errors.append(f"{claim_id}: affected test path must be JSON eval cases or Python unittest code")
            return
        count = identifiers.count(anchor)
        if count != 1:
            errors.append(f"{claim_id}: affected test ID {anchor!r} resolves {count} times in {path_value}")

    for claim_id, record in claim_by_id.items():
        claim = record.data
        support = claim.get("support_status")
        agreement = claim.get("agreement_status")
        lifecycle = claim.get("lifecycle_status")
        runtime_status = claim.get("runtime_status")
        claim_class = claim.get("claim_class")
        verified_at = parse_date(claim.get("verified_at"), f"{claim_id}.verified_at", errors)
        expires_at = parse_date(claim.get("expires_at"), f"{claim_id}.expires_at", errors)
        ttl_days = claim.get("ttl_days")
        if verified_at and verified_at > as_of:
            errors.append(f"{claim_id}: verification date is in the future relative to UTC as_of")
        if verified_at and expires_at and isinstance(ttl_days, int):
            if expires_at != verified_at + timedelta(days=ttl_days):
                errors.append(f"{claim_id}: expires_at must equal verified_at + ttl_days using exclusive UTC semantics")
            limit = TTL_LIMITS.get(claim_class, 0)
            if ttl_days > limit:
                errors.append(f"{claim_id}: TTL {ttl_days} exceeds {limit}-day class limit")
            if as_of >= expires_at and lifecycle == "active":
                message = f"{claim_id}: evidence expired at UTC date {expires_at.isoformat()}"
                (errors if enforce_freshness else warnings).append(message)

        if support == "supported":
            if agreement == "not_assessed":
                errors.append(f"{claim_id}: supported evidence must be assessed")
            if claim.get("confidence") == "unknown":
                errors.append(f"{claim_id}: supported evidence cannot use unknown confidence")
            if runtime_status == "blocked":
                errors.append(f"{claim_id}: supported claim cannot use blocked runtime status")
        elif support == "unverified":
            if agreement != "not_assessed" or runtime_status != "blocked":
                errors.append(f"{claim_id}: unverified claim must be not_assessed and blocked")
        elif support == "retracted" and lifecycle == "active":
            errors.append(f"{claim_id}: retracted claim cannot remain active")

        if runtime_status == "candidate" and support != "supported":
            errors.append(f"{claim_id}: candidate runtime status requires supported evidence")
        if runtime_status == "research_only" and claim_class not in {"annotation_ontology", "community_pattern"}:
            errors.append(f"{claim_id}: research_only status is limited to research claim classes")
        generation = parse_model_generation(claim.get("model_version"))
        if claim.get("model_family", "").casefold() == "seedance" and generation and generation >= (2, 5):
            if runtime_status != "blocked" or support != "unverified":
                errors.append(f"{claim_id}: Seedance {generation[0]}.{generation[1]} must remain unverified and blocked")

        supporting_refs = 0
        supporting_retrieval_dates: list[date] = []
        referenced_retrieval_dates: list[date] = []
        for evidence in claim.get("source_evidence", []):
            snapshot_id = evidence.get("source_snapshot_id")
            source_record = source_by_id.get(snapshot_id)
            if source_record is None:
                errors.append(f"{claim_id}: unknown source_snapshot_id {snapshot_id!r}")
                continue
            source = source_record.data
            if evidence.get("source_snapshot_sha256") != source_record.sha256:
                errors.append(f"{claim_id}: source snapshot byte pin mismatch for {snapshot_id}")
            if evidence.get("capture_sha256") != source.get("capture_sha256"):
                errors.append(f"{claim_id}: capture byte pin mismatch for {snapshot_id}")
            relation = evidence.get("relation")
            item_refs = evidence.get("evidence_items", [])
            retrieved = parse_date(source.get("retrieved_at"), f"{claim_id}.source.retrieved_at", errors)
            if retrieved:
                referenced_retrieval_dates.append(retrieved)
            if relation == "supports":
                supporting_refs += 1
                if source.get("source_type") not in CLAIM_SOURCE_TYPES.get(claim_class, set()):
                    errors.append(f"{claim_id}: source type {source.get('source_type')} cannot support {claim_class}")
                if source.get("retrieval_status") not in SUCCESSFUL_RETRIEVALS:
                    errors.append(f"{claim_id}: supporting source was not successfully retrieved")
                if snapshot_id not in verified_captures:
                    errors.append(f"{claim_id}: supporting source lacks retained hash-verified evidence")
                if retrieved:
                    supporting_retrieval_dates.append(retrieved)
            items = item_index.get(snapshot_id, {})
            for item_ref in item_refs:
                item_id = item_ref.get("evidence_item_id")
                if item_id not in items:
                    errors.append(f"{claim_id}: unknown evidence item {snapshot_id}/{item_id}")
                elif item_ref.get("normalized_evidence_sha256") != items[item_id].get("normalized_evidence_sha256"):
                    errors.append(f"{claim_id}: evidence item byte pin mismatch for {snapshot_id}/{item_id}")
            if relation == "supports" and not item_refs:
                errors.append(f"{claim_id}: supporting evidence must name at least one retained item")
        if support == "supported" and supporting_refs == 0:
            errors.append(f"{claim_id}: supported claim has no supporting evidence relation")
        if support == "supported" and verified_at and supporting_retrieval_dates:
            if verified_at != max(supporting_retrieval_dates):
                errors.append(f"{claim_id}: verification date must equal the newest supporting source snapshot")
        if support == "unverified" and verified_at and referenced_retrieval_dates:
            if verified_at != max(referenced_retrieval_dates):
                errors.append(f"{claim_id}: watchlist verification date must equal its newest context snapshot")
        if claim.get("volatility") == "volatile" and verified_at:
            if not supporting_retrieval_dates or any(item != verified_at for item in supporting_retrieval_dates):
                errors.append(f"{claim_id}: volatile verification requires same-day supporting source snapshots")

        presence = claim.get("runtime_presence")
        affected_paths = claim.get("affected_paths", [])
        if presence == "legacy_active" and not affected_paths:
            errors.append(f"{claim_id}: legacy_active claim must name affected runtime paths")
        for affected_path in affected_paths:
            try:
                read_regular_file(layout.root, affected_path, f"{claim_id}.affected_path")
            except EvidenceError as exc:
                errors.append(str(exc))
        for test_id in claim.get("affected_tests", []):
            validate_test_binding(test_id, claim_id)
        if claim.get("criticality") == "critical" and not claim.get("affected_tests"):
            errors.append(f"{claim_id}: critical claim must name at least one regression test")

        review = claim.get("review", {})
        review_status = review.get("status")
        reviewers = review.get("reviewers", [])
        decision_at = review.get("decision_at")
        review_hash = review.get("claim_sha256")
        review_payload = dict(claim)
        review_payload.pop("review", None)
        expected_review_hash = sha256_bytes(canonical_json(review_payload))
        normalized_reviewers = [unicodedata.normalize("NFC", item).casefold() for item in reviewers]
        if len(normalized_reviewers) != len(set(normalized_reviewers)):
            errors.append(f"{claim_id}: reviewers must be distinct after NFC/case folding")
        if any(normalize_text(item) != item or UNSAFE_RENDER_CHARS.search(item) for item in reviewers):
            errors.append(f"{claim_id}: reviewer identities must be normalized printable strings")
        decision_date = parse_date(decision_at, f"{claim_id}.review.decision_at", errors) if decision_at else None
        if decision_date and decision_date > as_of:
            errors.append(f"{claim_id}: review decision date is in the future")
        if decision_date and verified_at and decision_date < verified_at:
            errors.append(f"{claim_id}: review decision predates claim verification")
        if review_status == "pending":
            if reviewers or decision_at is not None or review_hash is not None:
                errors.append(f"{claim_id}: pending review must not contain a decision")
        elif review_status == "approved":
            if len(reviewers) < 2 or not decision_at or review_hash != expected_review_hash:
                errors.append(f"{claim_id}: approved review must name two reviewers and bind the exact claim payload")
        elif review_status == "rejected":
            if not reviewers or not decision_at or review_hash != expected_review_hash or runtime_status != "blocked":
                errors.append(f"{claim_id}: rejected review must be bound and remain blocked")

        if agreement == "conflicting" and not claim.get("conflict_group"):
            errors.append(f"{claim_id}: conflicting agreement requires conflict_group")
        if agreement != "conflicting" and claim.get("conflict_group"):
            errors.append(f"{claim_id}: non-conflicting agreement cannot declare conflict_group")
        if agreement == "qualified" and not any(
            relation.get("type") in {"qualifies", "qualified_by", "tension_with"}
            for relation in claim.get("relations", [])
        ):
            errors.append(f"{claim_id}: qualified claim requires a typed qualification relation")
        for relation in claim.get("relations", []):
            target = relation.get("claim_id")
            relation_type = relation.get("type")
            if target == claim_id:
                errors.append(f"{claim_id}: claim cannot relate to itself")
            if target not in claim_by_id:
                errors.append(f"{claim_id}: dangling relation target {target!r}")
                continue
            inverse = RELATION_INVERSES.get(relation_type)
            if inverse and (target, claim_id, inverse) not in relation_index:
                errors.append(f"{claim_id}: relation {relation_type} to {target} requires reciprocal {inverse}")

    incoming: dict[str, list[LoadedRecord]] = defaultdict(list)
    for claim_id, record in claim_by_id.items():
        claim = record.data
        for target in claim.get("supersedes", []):
            target_record = claim_by_id.get(target)
            if target == claim_id:
                errors.append(f"{claim_id}: claim cannot supersede itself")
            if target_record is None:
                errors.append(f"{claim_id}: dangling supersedes target {target!r}")
                continue
            incoming[target].append(record)
            target_claim = target_record.data
            if target_claim.get("lifecycle_status") != "superseded":
                errors.append(f"{claim_id}: superseded target must declare superseded lifecycle")
            if claim.get("normalized_key") != target_claim.get("normalized_key"):
                errors.append(f"{claim_id}: successor normalized_key mismatch")
            if claim.get("model_family") != target_claim.get("model_family") or claim.get("model_version") != target_claim.get("model_version"):
                errors.append(f"{claim_id}: successor model scope mismatch")
            if not scopes_overlap(claim.get("scope", {}), target_claim.get("scope", {})):
                errors.append(f"{claim_id}: successor scope does not overlap target")
            current_date = date.fromisoformat(claim["verified_at"])
            target_date = date.fromisoformat(target_claim["verified_at"])
            if current_date <= target_date:
                errors.append(f"{claim_id}: successor verification must be later than target")
    for claim_id, record in claim_by_id.items():
        if record.data.get("lifecycle_status") == "superseded" and not incoming.get(claim_id):
            errors.append(f"{claim_id}: superseded claim has no selected successor")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(claim_id: str, chain: list[str]) -> None:
        if claim_id in visiting:
            errors.append("supersedes cycle: " + " -> ".join(chain + [claim_id]))
            return
        if claim_id in visited or claim_id not in claim_by_id:
            return
        visiting.add(claim_id)
        for target in claim_by_id[claim_id].data.get("supersedes", []):
            visit(target, chain + [claim_id])
        visiting.remove(claim_id)
        visited.add(claim_id)

    for claim_id in sorted(claim_by_id):
        visit(claim_id, [])

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in claims:
        if record.data.get("conflict_group"):
            groups[record.data["conflict_group"]].append(record.data)
    for group, members in sorted(groups.items()):
        if len(members) < 2:
            errors.append(f"conflict group {group!r} has fewer than two claims")
            continue
        if len({canonical_value(item.get("value")) for item in members}) < 2:
            errors.append(f"conflict group {group!r} does not contain incompatible values")
        if any(item.get("agreement_status") != "conflicting" for item in members):
            errors.append(f"conflict group {group!r} contains a non-conflicting claim")
        if len({(item.get("normalized_key"), item.get("model_family"), item.get("model_version")) for item in members}) != 1:
            errors.append(f"conflict group {group!r} mixes key or model scope")
        for left, right in combinations(members, 2):
            if not scopes_overlap(left.get("scope", {}), right.get("scope", {})):
                errors.append(f"conflict group {group!r} contains non-overlapping scopes")

    active_supported = [
        record.data for record in claims
        if record.data.get("lifecycle_status") == "active" and record.data.get("support_status") == "supported"
    ]
    for left, right in combinations(active_supported, 2):
        if (
            left.get("normalized_key") != right.get("normalized_key")
            or left.get("model_family") != right.get("model_family")
            or left.get("model_version") != right.get("model_version")
            or not scopes_overlap(left.get("scope", {}), right.get("scope", {}))
            or canonical_value(left.get("value")) == canonical_value(right.get("value"))
        ):
            continue
        group = left.get("conflict_group")
        if not group or group != right.get("conflict_group"):
            errors.append(f"undeclared value conflict for {left.get('normalized_key')}")
    return claim_by_id


def validate_runtime_map(
    layout: RegistryLayout,
    runtime_record: LoadedRecord,
    manifest_record: LoadedRecord,
    claim_by_id: dict[str, LoadedRecord],
    errors: list[str],
) -> dict[str, int]:
    runtime_map = runtime_record.data
    manifest = manifest_record.data
    if runtime_map.get("runtime_manifest_sha256") != manifest_record.sha256:
        errors.append("runtime-map: runtime manifest SHA-256 mismatch")
    manifest_files = manifest.get("files", [])
    entries = runtime_map.get("files", [])
    paths = [entry.get("path") for entry in entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        errors.append("runtime-map: file paths must be sorted and unique")
    if set(paths) != set(manifest_files):
        errors.append("runtime-map: file set must exactly equal the runtime manifest allowlist")
    counts: Counter[str] = Counter()
    mapped_occurrences: dict[tuple[str, str], int] = Counter()
    for entry in entries:
        path = entry.get("path")
        status_value = entry.get("audit_status")
        counts[status_value] += 1
        if path in V705_CANDIDATE_PROFILE_PATHS:
            expected_status = "mapped_candidate"
        elif path in V705_CLEAN_RUNTIME_PATHS:
            expected_status = "no_volatile_claims"
        else:
            expected_status = "legacy_blocked"
        if status_value != expected_status:
            errors.append(
                f"runtime-map/{path}: V7-05 audit status must remain {expected_status}, got {status_value}"
            )
        try:
            _, raw = read_regular_file(layout.root, path, f"runtime-map/{path}", max_bytes=MAX_JSON_BYTES)
        except EvidenceError as exc:
            errors.append(str(exc))
            continue
        if sha256_bytes(raw) != entry.get("sha256"):
            errors.append(f"runtime-map/{path}: file SHA-256 mismatch")
        occurrences = entry.get("occurrences", [])
        if status_value in {"mapped", "mapped_candidate"} and not occurrences:
            errors.append(f"runtime-map/{path}: mapped file must contain occurrences")
        if status_value in {"no_volatile_claims", "non_text"} and occurrences:
            errors.append(f"runtime-map/{path}: clean/non-text file cannot contain occurrences")
        try:
            text = raw.decode("utf-8") if Path(path).suffix in TEXT_SUFFIXES else ""
        except UnicodeDecodeError:
            text = ""
        for occurrence in occurrences:
            claim_id = occurrence.get("claim_id")
            claim_record = claim_by_id.get(claim_id)
            if claim_record is None:
                errors.append(f"runtime-map/{path}: unknown claim_id {claim_id!r}")
                continue
            anchor = occurrence.get("anchor_text", "")
            if sha256_text(anchor) != occurrence.get("anchor_sha256"):
                errors.append(f"runtime-map/{path}/{claim_id}: anchor hash mismatch")
            actual_count = text.count(anchor)
            if actual_count != occurrence.get("occurrence_count"):
                errors.append(f"runtime-map/{path}/{claim_id}: expected one exact anchor, found {actual_count}")
            claim = claim_record.data
            if status_value == "mapped" and (
                claim.get("lifecycle_status") != "active"
                or claim.get("support_status") != "supported"
                or claim.get("runtime_status") != "candidate"
                or claim.get("review", {}).get("status") != "approved"
                or occurrence.get("disposition") != "supported_candidate"
            ):
                errors.append(f"runtime-map/{path}/{claim_id}: mapped occurrence is not activation-ready")
            if status_value == "mapped_candidate" and (
                claim.get("lifecycle_status") != "active"
                or claim.get("support_status") != "supported"
                or claim.get("runtime_status") != "candidate"
                or claim.get("review", {}).get("status") not in {"pending", "approved"}
                or occurrence.get("disposition") != "supported_candidate"
                or occurrence.get("profile_ids") != [V705_CANDIDATE_PROFILE_PATHS.get(path)]
            ):
                errors.append(f"runtime-map/{path}/{claim_id}: candidate occurrence is not projection-ready")
            candidate_profile_projection = (
                status_value == "mapped_candidate"
                and V705_CANDIDATE_PROFILE_PATHS.get(path) in claim.get("affected_profiles", [])
            )
            if path not in claim.get("affected_paths", []) and not candidate_profile_projection:
                errors.append(f"runtime-map/{path}/{claim_id}: path is absent from claim affected_paths")
            if not set(occurrence.get("profile_ids", [])).issubset(set(claim.get("affected_profiles", []))):
                errors.append(f"runtime-map/{path}/{claim_id}: profile mapping exceeds claim consumers")
            if not set(occurrence.get("test_ids", [])).issubset(set(claim.get("affected_tests", []))):
                errors.append(f"runtime-map/{path}/{claim_id}: test mapping exceeds claim consumers")
            mapped_occurrences[(claim_id, path)] += 1
    for claim_id, record in claim_by_id.items():
        claim = record.data
        for path in claim.get("affected_paths", []):
            entry = next((item for item in entries if item.get("path") == path), None)
            if entry is None:
                errors.append(f"runtime-map: affected path {path!r} for {claim_id} is absent")
                continue
            if entry.get("audit_status") in {"no_volatile_claims", "non_text"}:
                errors.append(f"runtime-map/{path}: clean status contradicts affected claim {claim_id}")
            if claim.get("runtime_presence") == "legacy_active" and entry.get("audit_status") == "mapped" and not mapped_occurrences.get((claim_id, path)):
                errors.append(f"runtime-map/{path}: mapped file omits legacy-active claim {claim_id}")
    return dict(sorted(counts.items()))


def lineage_contains(selected: str, root: str, claim_by_id: dict[str, LoadedRecord], seen: set[str] | None = None) -> bool:
    if selected == root:
        return True
    seen = seen or set()
    if selected in seen or selected not in claim_by_id:
        return False
    seen.add(selected)
    return any(lineage_contains(parent, root, claim_by_id, seen) for parent in claim_by_id[selected].data.get("supersedes", []))


def validate_policy(
    policy_record: LoadedRecord,
    claim_by_id: dict[str, LoadedRecord],
    verified_captures: set[str],
    coverage_counts: dict[str, int],
    as_of: date,
    errors: list[str],
) -> list[str]:
    policy = policy_record.data
    blockers: list[str] = ["policy.activation:disabled"]
    requirements = policy.get("requirements", [])
    identifiers = [item.get("requirement_id") for item in requirements]
    if len(identifiers) != len(set(identifiers)):
        errors.append("release-policy: duplicate requirement_id")
    if policy.get("activation_enabled") is not False:
        errors.append("release-policy: V7-04 activation must remain disabled")
    if policy.get("policy_id") != "v7.evidence.activation":
        errors.append("release-policy: unexpected policy_id")
    lineage_roots = [item.get("lineage_root_claim_id") for item in requirements]
    missing_roots = sorted(V7_REQUIRED_LINEAGE_ROOTS - set(lineage_roots))
    if missing_roots:
        errors.append(f"release-policy: required lineage roots are missing: {missing_roots}")
    duplicate_roots = sorted(root for root, count in Counter(lineage_roots).items() if count > 1)
    if duplicate_roots:
        errors.append(f"release-policy: lineage roots must be selected exactly once: {duplicate_roots}")
    for requirement in requirements:
        requirement_id = requirement.get("requirement_id", "invalid.requirement")
        selected_id = requirement.get("selected_claim_id")
        root = requirement.get("lineage_root_claim_id")
        baseline = V7_POLICY_BASELINE.get(root)
        if baseline:
            normalized_key, criticality, support, runtime_status, profile_id, test_id = baseline
            expected_requirement_id = "requirement." + root.replace(".", "-")
            if requirement_id != expected_requirement_id:
                errors.append(f"release-policy: requirement_id changed for lineage root {root}")
            if requirement.get("normalized_key") != normalized_key:
                errors.append(f"release-policy: normalized_key baseline changed for lineage root {root}")
            if CRITICALITY_RANK.get(requirement.get("criticality"), -1) < CRITICALITY_RANK[criticality]:
                errors.append(f"release-policy: criticality floor changed for lineage root {root}")
            if requirement.get("expected_support_status") != support:
                errors.append(f"release-policy: support baseline changed for lineage root {root}")
            if requirement.get("allowed_runtime_status") != [runtime_status]:
                errors.append(f"release-policy: runtime baseline changed for lineage root {root}")
            if requirement.get("enforce_freshness") is not True:
                errors.append(f"release-policy: freshness enforcement removed for lineage root {root}")
            if requirement.get("require_capture") is not (support == "supported"):
                errors.append(f"release-policy: capture requirement changed for lineage root {root}")
            if profile_id not in requirement.get("required_profile_ids", []):
                errors.append(f"release-policy: required profile removed for lineage root {root}")
            if test_id not in requirement.get("required_test_ids", []):
                errors.append(f"release-policy: required test removed for lineage root {root}")
        record = claim_by_id.get(selected_id)
        if record is None:
            blockers.append(f"{requirement_id}:selected-claim-missing")
            continue
        claim = record.data
        claim_baseline = V7_CLAIM_BASELINE.get(root)
        if claim_baseline:
            claim_class, volatility, ttl_days, model_family, model_version, surfaces = claim_baseline
            if claim.get("claim_class") != claim_class:
                errors.append(f"release-policy: claim class baseline changed for lineage root {root}")
            if claim.get("volatility") != volatility:
                errors.append(f"release-policy: volatility baseline changed for lineage root {root}")
            if claim.get("ttl_days") != ttl_days:
                errors.append(f"release-policy: TTL baseline changed for lineage root {root}")
            if claim.get("model_family") != model_family or claim.get("model_version") != model_version:
                errors.append(f"release-policy: model baseline changed for lineage root {root}")
            if set(claim.get("scope", {}).get("surfaces", [])) != surfaces:
                errors.append(f"release-policy: surface scope baseline changed for lineage root {root}")
        semantic_baseline = V7_SEMANTIC_BASELINE.get(root)
        if semantic_baseline:
            operations, locale, region, confidence, value_sha256 = semantic_baseline
            scope = claim.get("scope", {})
            if set(scope.get("operations", [])) != operations:
                errors.append(f"release-policy: operation scope baseline changed for lineage root {root}")
            if scope.get("locale") != locale or scope.get("region") != region:
                errors.append(f"release-policy: locale/region baseline changed for lineage root {root}")
            if CONFIDENCE_RANK.get(claim.get("confidence"), -1) < CONFIDENCE_RANK[confidence]:
                errors.append(f"release-policy: confidence floor changed for lineage root {root}")
            current_value_sha256 = sha256_bytes(canonical_value(claim.get("value")).encode("utf-8"))
            if current_value_sha256 != value_sha256:
                errors.append(f"release-policy: claim value baseline changed for lineage root {root}")
        expected_agreement = "qualified" if root in V7_QUALIFIED_RELATIONS else "uncontested"
        if claim.get("agreement_status") != expected_agreement:
            errors.append(f"release-policy: agreement baseline changed for lineage root {root}")
        expected_relations = V7_QUALIFIED_RELATIONS.get(root, set())
        actual_relations = {
            (relation.get("claim_id"), relation.get("type"))
            for relation in claim.get("relations", [])
        }
        if actual_relations != expected_relations:
            errors.append(f"release-policy: relation baseline changed for lineage root {root}")
        actual_sources = {
            evidence.get("source_snapshot_id")
            for evidence in claim.get("source_evidence", [])
        }
        if actual_sources != V7_CLAIM_SOURCE_BASELINE.get(root, set()):
            errors.append(f"release-policy: source closure baseline changed for lineage root {root}")
        if record.sha256 != requirement.get("selected_claim_sha256"):
            blockers.append(f"{requirement_id}:selected-claim-byte-pin-mismatch")
        if root not in claim_by_id or not lineage_contains(selected_id, root, claim_by_id):
            blockers.append(f"{requirement_id}:lineage-root-missing")
        if claim.get("normalized_key") != requirement.get("normalized_key"):
            blockers.append(f"{requirement_id}:normalized-key-mismatch")
        if CRITICALITY_RANK.get(claim.get("criticality"), -1) < CRITICALITY_RANK.get(requirement.get("criticality"), 99):
            blockers.append(f"{requirement_id}:criticality-downgraded")
        if claim.get("support_status") != requirement.get("expected_support_status"):
            blockers.append(f"{requirement_id}:support-status-unhealthy")
        if claim.get("runtime_status") not in requirement.get("allowed_runtime_status", []):
            blockers.append(f"{requirement_id}:runtime-status-unhealthy")
        if claim.get("lifecycle_status") != "active":
            blockers.append(f"{requirement_id}:selected-claim-not-active")
        if claim.get("agreement_status") in {"conflicting"}:
            blockers.append(f"{requirement_id}:unresolved-conflict")
        if claim.get("support_status") == "supported" and claim.get("agreement_status") == "not_assessed":
            blockers.append(f"{requirement_id}:agreement-not-assessed")
        if requirement.get("enforce_freshness") and as_of >= date.fromisoformat(claim["expires_at"]):
            blockers.append(f"{requirement_id}:expired")
        if requirement.get("require_capture"):
            supporting_sources = {
                item.get("source_snapshot_id")
                for item in claim.get("source_evidence", [])
                if item.get("relation") == "supports"
            }
            if not supporting_sources or not supporting_sources.issubset(verified_captures):
                blockers.append(f"{requirement_id}:retained-capture-unhealthy")
        if not set(requirement.get("required_profile_ids", [])).issubset(set(claim.get("affected_profiles", []))):
            blockers.append(f"{requirement_id}:required-profile-missing")
        if not set(requirement.get("required_test_ids", [])).issubset(set(claim.get("affected_tests", []))):
            blockers.append(f"{requirement_id}:required-test-missing")
        if claim.get("criticality") == "critical" and claim.get("review", {}).get("status") != "approved":
            blockers.append(f"{requirement_id}:critical-review-not-approved")
        if claim.get("agreement_status") == "qualified":
            for relation in claim.get("relations", []):
                if relation.get("type") not in {"qualifies", "qualified_by", "tension_with"}:
                    continue
                target = claim_by_id.get(relation.get("claim_id"))
                if target is None:
                    blockers.append(f"{requirement_id}:qualification-target-unhealthy")
                    continue
                target_claim = target.data
                target_supporting_sources = {
                    item.get("source_snapshot_id")
                    for item in target_claim.get("source_evidence", [])
                    if item.get("relation") == "supports"
                }
                target_expires = date.fromisoformat(target_claim["expires_at"])
                if (
                    target_claim.get("lifecycle_status") != "active"
                    or target_claim.get("support_status") != "supported"
                    or target_claim.get("runtime_status") != "candidate"
                    or target_claim.get("agreement_status") in {"conflicting", "not_assessed"}
                    or as_of >= target_expires
                    or not target_supporting_sources
                    or not target_supporting_sources.issubset(verified_captures)
                    or target_claim.get("review", {}).get("status") != "approved"
                ):
                    blockers.append(f"{requirement_id}:qualification-target-unhealthy")
    if coverage_counts.get("legacy_blocked", 0):
        blockers.append(f"runtime.coverage:legacy-blocked-files={coverage_counts['legacy_blocked']}")
    return sorted(set(blockers))


def freshness_rows(claims: Iterable[LoadedRecord], as_of: date, lead_days: int = 7) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in sorted(
        claims,
        key=lambda item: item.data.get("claim_id")
        if isinstance(item.data.get("claim_id"), str)
        else item.relative_path,
    ):
        claim = record.data
        claim_id = claim.get("claim_id") if isinstance(claim.get("claim_id"), str) else record.relative_path
        expires_raw = claim.get("expires_at")
        try:
            expires = date.fromisoformat(expires_raw) if isinstance(expires_raw, str) else None
        except ValueError:
            expires = None
        if expires is None:
            rows.append({
                "claim_id": claim_id,
                "criticality": claim.get("criticality") if isinstance(claim.get("criticality"), str) else "invalid",
                "expires_at": expires_raw if isinstance(expires_raw, str) else None,
                "days_remaining": None,
                "freshness_status": "invalid",
                "runtime_status": claim.get("runtime_status") if isinstance(claim.get("runtime_status"), str) else "invalid",
                "support_status": claim.get("support_status") if isinstance(claim.get("support_status"), str) else "invalid",
            })
            continue
        remaining = (expires - as_of).days
        status_value = "expired" if remaining <= 0 else "due_soon" if remaining <= lead_days else "healthy"
        rows.append({
            "claim_id": claim_id,
            "criticality": claim.get("criticality") if isinstance(claim.get("criticality"), str) else "invalid",
            "expires_at": expires.isoformat(),
            "days_remaining": remaining,
            "freshness_status": status_value,
            "runtime_status": claim.get("runtime_status") if isinstance(claim.get("runtime_status"), str) else "invalid",
            "support_status": claim.get("support_status") if isinstance(claim.get("support_status"), str) else "invalid",
        })
    return rows


def build_report(
    *,
    claims: list[LoadedRecord],
    sources: list[LoadedRecord],
    captures: list[LoadedRecord],
    verified_captures: set[str],
    coverage_counts: dict[str, int],
    release_blockers: list[str],
    as_of: date,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    def counts(field: str) -> dict[str, int]:
        return dict(sorted(Counter(
            record.data.get(field) if isinstance(record.data.get(field), str) else "invalid"
            for record in claims
        ).items()))

    def review_status(record: LoadedRecord) -> str:
        review = record.data.get("review")
        if not isinstance(review, dict) or not isinstance(review.get("status"), str):
            return "invalid"
        return review["status"]

    rows = freshness_rows(claims, as_of)
    return {
        "schema_version": 1,
        "as_of_utc": as_of.isoformat(),
        "activation_enabled": False,
        "claim_count": len(claims),
        "source_snapshot_count": len(sources),
        "capture_count": len(captures),
        "verified_capture_source_count": len(verified_captures),
        "support_counts": counts("support_status"),
        "criticality_counts": counts("criticality"),
        "runtime_presence_counts": counts("runtime_presence"),
        "runtime_status_counts": counts("runtime_status"),
        "review_counts": dict(sorted(Counter(review_status(record) for record in claims).items())),
        "runtime_coverage_counts": coverage_counts,
        "release_gate_pass": not errors and not release_blockers,
        "release_blockers": sorted(release_blockers),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "freshness": rows,
    }


def evaluate(
    layout: RegistryLayout | None = None,
    *,
    as_of: date | None = None,
    enforce_freshness: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    layout = layout or RegistryLayout()
    as_of = as_of or utc_today()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        schemas = {
            "claims": load_schema(layout.root, layout.claim_schema),
            "sources": load_schema(layout.root, layout.source_schema),
            "captures": load_schema(layout.root, layout.capture_schema),
            "authorities": load_schema(layout.root, layout.authority_schema),
            "runtime_map": load_schema(layout.root, layout.runtime_map_schema),
            "policy": load_schema(layout.root, layout.policy_schema),
        }
        claims = load_directory(layout.root, layout.claims, "claims")
        sources = load_directory(layout.root, layout.sources, "sources")
        captures = load_directory(layout.root, layout.captures, "captures", max_bytes=MAX_CAPTURE_BYTES)
        authority_record = load_one(layout.root, layout.authorities, "authorities")
        runtime_record = load_one(layout.root, layout.runtime_map, "runtime-map")
        policy_record = load_one(layout.root, layout.policy, "release-policy")
        manifest_record = load_one(layout.root, layout.runtime_manifest, "runtime-manifest")
    except (EvidenceError, OSError, ValueError) as exc:
        report = build_report(
            claims=[], sources=[], captures=[], verified_captures=set(), coverage_counts={},
            release_blockers=["registry.load-failure"], as_of=as_of, errors=[str(exc)], warnings=[]
        )
        return report, report["errors"], report["warnings"]

    errors.extend(schema_errors(schemas["claims"], claims))
    errors.extend(schema_errors(schemas["sources"], sources))
    errors.extend(schema_errors(schemas["captures"], captures))
    errors.extend(schema_errors(schemas["authorities"], [authority_record]))
    errors.extend(schema_errors(schemas["runtime_map"], [runtime_record]))
    errors.extend(schema_errors(schemas["policy"], [policy_record]))
    if errors:
        report = build_report(
            claims=claims, sources=sources, captures=captures, verified_captures=set(), coverage_counts={},
            release_blockers=["registry.schema-invalid"], as_of=as_of, errors=errors, warnings=warnings
        )
        return report, report["errors"], report["warnings"]

    authorities = validate_authorities(authority_record, errors)
    source_by_id, item_index, verified_captures = validate_captures(
        layout, captures, sources, authorities, as_of, errors
    )
    claim_by_id = validate_claims(
        layout, claims, source_by_id, item_index, verified_captures,
        as_of, enforce_freshness, errors, warnings
    )
    coverage_counts = validate_runtime_map(
        layout, runtime_record, manifest_record, claim_by_id, errors
    )
    release_blockers = validate_policy(
        policy_record, claim_by_id, verified_captures, coverage_counts, as_of, errors
    )
    report = build_report(
        claims=claims,
        sources=sources,
        captures=captures,
        verified_captures=verified_captures,
        coverage_counts=coverage_counts,
        release_blockers=release_blockers,
        as_of=as_of,
        errors=errors,
        warnings=warnings,
    )
    return report, report["errors"], report["warnings"]


def proposal_payload(report: dict[str, Any], lead_days: int) -> dict[str, Any] | None:
    claims = [
        {
            "claim_id": row["claim_id"],
            "criticality": row["criticality"],
            "expires_at": row["expires_at"],
            "freshness_status": row["freshness_status"],
            "trigger_date": (
                date.fromisoformat(row["expires_at"])
                if row["freshness_status"] == "expired"
                else date.fromisoformat(row["expires_at"]) - timedelta(days=lead_days)
            ).isoformat(),
        }
        for row in report.get("freshness", [])
        if row.get("freshness_status") in {"due_soon", "expired"}
    ]
    if not claims and not report.get("errors"):
        return None
    blockers = [item for item in report.get("release_blockers", []) if SAFE_ID.match(item.split(":", 1)[0])]
    return {
        "schema_version": 1,
        "activation_enabled": False,
        "claim_actions": claims,
        "release_blocker_ids": sorted(item.split(":", 1)[0] for item in blockers),
        "registry_error_count": len(report.get("errors", [])),
        "notice": "Offline alert only. Human source review is required; no claim freshness or runtime status was changed.",
    }


def render_proposal_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Evidence freshness proposal",
        "",
        "This is an offline, deterministic alert generated from checked-in TTLs and the closed release policy.",
        "It did not fetch the web, renew evidence, approve a claim, or activate runtime guidance.",
        "",
        "## Claims requiring review",
        "",
        "| Claim ID | Criticality | Status | Expiry | Trigger date |",
        "|---|---|---|---|---|",
    ]
    for item in payload.get("claim_actions", []):
        lines.append(
            f"| `{item['claim_id']}` | {item['criticality']} | {item['freshness_status']} | "
            f"{item['expires_at']} | {item['trigger_date']} |"
        )
    if not payload.get("claim_actions"):
        lines.append("| none | — | — | — | — |")
    lines.extend(["", "## Release blockers", ""])
    blockers = payload.get("release_blocker_ids", [])
    lines.extend(f"- `{item}`" for item in blockers)
    if not blockers:
        lines.append("- None from the closed policy.")
    if payload.get("registry_error_count"):
        lines.extend(["", f"Registry errors detected: {payload['registry_error_count']}. Inspect the validation artifact locally."])
    lines.extend([
        "",
        "A human must retrieve the official source, retain bounded evidence, create an immutable snapshot or successor claim, run the offline gate, and review the resulting diff.",
        "",
    ])
    return "\n".join(lines)


def write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the non-activating Seedance v7 evidence registry.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=utc_today())
    parser.add_argument("--enforce-freshness", action="store_true")
    parser.add_argument("--release", action="store_true", help="fail when the closed evidence release policy is unhealthy")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--proposal-json", type=Path)
    parser.add_argument("--proposal-markdown", type=Path)
    parser.add_argument("--lead-days", type=int, default=7)
    args = parser.parse_args()
    if args.lead_days < 0 or args.lead_days > 30:
        print("lead-days must be between 0 and 30")
        return 2
    report, errors, warnings = evaluate(as_of=args.as_of, enforce_freshness=args.enforce_freshness)
    if args.report:
        write_bytes(args.report, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n")
    payload = proposal_payload(report, args.lead_days)
    if payload is not None:
        if args.proposal_json:
            write_bytes(args.proposal_json, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        if args.proposal_markdown:
            write_bytes(args.proposal_markdown, render_proposal_markdown(payload).encode("utf-8"))
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        print("Evidence registry errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    if args.release and not report["release_gate_pass"]:
        print("Evidence release gate blocked:")
        for blocker in report["release_blockers"]:
            print(f"- {blocker}")
        return 1
    print(
        f"Evidence registry validated: {report['claim_count']} claims, "
        f"{report['verified_capture_source_count']} retained sources, "
        f"release_gate_pass={str(report['release_gate_pass']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
