#!/usr/bin/env python3
"""Render typed surface bindings without guessing or rewriting provider syntax.

V7-05 is deliberately non-activating. Provider profiles are candidate-only and
can be exercised only with ``--preview-candidate`` until the later activation
gate changes this code and the evidence policy together.
"""
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
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = "profiles/profile-index.json"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_PROFILE_BYTES = 512 * 1024
MAX_JSON_DEPTH = 48
MAX_TEXT_SEGMENT = 20_000
MAX_RENDERED_PROMPT = 100_000
ACTIVATION_SUPPORTED = False

SAFE_PROFILE_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
SAFE_BINDING_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
SAFE_PROFILE_PATH = re.compile(
    r"^profiles/(?:models|surfaces)/[a-z0-9][a-z0-9.-]*\.json$"
)
SHA256 = re.compile(r"^[a-f0-9]{64}$")

MODEL_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/model-profile.schema.json"
SURFACE_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/surface-profile.schema.json"
INDEX_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/profile-index.schema.json"
PLAN_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/binding-plan.schema.json"
RENDER_SCHEMA_URI = "https://github.com/Emily2040/seedance-2.0/schemas/binding-render.schema.json"

MODEL_KEYS = {
    "$schema", "schema_version", "profile_kind", "profile_id", "model_family",
    "model_version", "status", "runtime_enabled", "binding_contract",
    "input_modalities", "reference_control_dimensions", "evidence_pins",
}
SURFACE_KEYS = {
    "$schema", "schema_version", "profile_kind", "profile_id", "model_profile_id",
    "status", "runtime_enabled", "fallback_policy", "operations",
}
OPERATION_KEYS = {
    "operation", "request_transport", "prompt_binding", "allowed_media_types",
    "structured_roles", "required_role_set", "evidence_pins",
}
OPAQUE_PROMPT_BINDING_KEYS = {"kind", "source"}
DERIVED_PROMPT_BINDING_KEYS = {"kind", "position_scope", "media_formatters"}
NONE_PROMPT_BINDING_KEYS = {"kind"}
MEDIA_FORMATTER_KEYS = {"sigil", "media_label", "separator", "ordinal_base"}
PIN_KEYS = {"claim_id", "claim_sha256", "expires_at"}
INDEX_KEYS = {
    "$schema", "schema_version", "activation_enabled", "unknown_profile_policy",
    "models", "surfaces",
}
INDEX_ENTRY_KEYS = {"profile_id", "path", "sha256", "status", "runtime_enabled"}
PLAN_KEYS = {"$schema", "schema_version", "profile_id", "operation", "segments", "bindings"}
BINDING_KEYS = {"binding_id", "media_type", "prompt_visible_handle", "structured_role"}

MEDIA_TYPES = {"audio", "image", "video"}
OPERATIONS = {"reference_generation", "first_frame", "first_last_frame", "edit", "extend"}
TRANSPORTS = {
    "external_surface_unresolved", "typed_media_arrays",
    "ordered_content_objects", "structured_content_roles",
}
STRUCTURED_ROLES = {"first_frame", "last_frame"}
SECURE_DIRFD_SUPPORTED = (
    bool(getattr(os, "O_NOFOLLOW", 0))
    and bool(getattr(os, "O_DIRECTORY", 0))
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
)

# These characters can make an opaque handle ambiguous or misleading in logs,
# reviews, and bidirectional display. Ordinary Unicode, combining marks, emoji,
# ZWJ sequences, brackets, quotes, backslashes, at-signs, and spaces are kept.
FORBIDDEN_BIDI_CODEPOINTS = {
    0x061C,  # ARABIC LETTER MARK
    0x200E, 0x200F,  # LRM/RLM
    *range(0x202A, 0x202F),  # bidi embeddings/overrides plus PDF
    *range(0x2066, 0x2070),  # isolates plus deprecated bidi controls
}
FORBIDDEN_HANDLE_CODEPOINTS = {
    *FORBIDDEN_BIDI_CODEPOINTS,
    0x2028, 0x2029,  # line/paragraph separators
    0xFEFF,  # BOM / zero-width no-break space
}
REFERENCE_LIKE_TOKEN = re.compile(
    r"(?P<at>@(?:[Ii][Mm][Aa][Gg][Ee]|[Vv][Ii][Dd][Ee][Oo]|[Aa][Uu][Dd][Ii][Oo])\s*[0-9]+)"
    r"|(?:^|[^A-Za-z0-9_])(?P<bare>(?:[Ii][Mm][Aa][Gg][Ee]|[Vv][Ii][Dd][Ee][Oo]|[Aa][Uu][Dd][Ii][Oo])\s*[0-9]+)(?=$|[^A-Za-z0-9_])"
    r"|(?P<cjk>(?:图片|图像|视频|音频)\s*[0-9]+)"
)
DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class BindingError(RuntimeError):
    """A stable, non-echoing binding boundary failure."""

    def __init__(self, code: str, pointer: str = "/") -> None:
        super().__init__(f"{code} at {pointer}")
        self.code = code
        self.pointer = pointer


@dataclass(frozen=True)
class LoadedProfile:
    profile_id: str
    path: str
    sha256: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ProfileRegistry:
    index_sha256: str
    index: dict[str, Any]
    models: dict[str, LoadedProfile]
    surfaces: dict[str, LoadedProfile]


def _fail(code: str, pointer: str = "/") -> None:
    raise BindingError(code, pointer)


def _exact_keys(value: object, expected: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != expected:
        _fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_profile_id(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 100 and SAFE_PROFILE_ID.fullmatch(value) is not None


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _nonfinite(_value: str) -> None:
    _fail("JSON_NONFINITE_NUMBER")


def _parse_integer(value: str) -> int:
    # Every integer in the V7-05 contracts is a small schema version. Bounding
    # the token before ``int`` avoids interpreter-dependent digit-limit errors
    # and keeps hostile inputs on the stable BindingError path.
    if len(value) > 128:
        _fail("JSON_NUMBER_OUT_OF_RANGE")
    try:
        return int(value)
    except (ValueError, OverflowError):
        _fail("JSON_NUMBER_OUT_OF_RANGE")


def _parse_float(value: str) -> float:
    if len(value) > 128:
        _fail("JSON_NUMBER_OUT_OF_RANGE")
    try:
        parsed = float(value)
    except (ValueError, OverflowError):
        _fail("JSON_NUMBER_OUT_OF_RANGE")
    if not math.isfinite(parsed):
        _fail("JSON_NONFINITE_NUMBER")
    return parsed


def _check_json_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        _fail("JSON_TOO_DEEP")
    if isinstance(value, dict):
        for key, child in value.items():
            _check_scalar_text(key, "/")
            _check_json_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json_depth(child, depth + 1)
    elif isinstance(value, str):
        _check_scalar_text(value, "/")


def _check_scalar_text(value: str, pointer: str) -> None:
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            _fail("UNICODE_SURROGATE_FORBIDDEN", pointer)
        if codepoint in FORBIDDEN_HANDLE_CODEPOINTS or (
            unicodedata.category(character) == "Cf" and codepoint != 0x200D
        ):
            _fail("UNICODE_FORMAT_CONTROL_FORBIDDEN", pointer)


def _valid_emoji_zwj_context(value: str, index: int) -> bool:
    if ord(value[index]) != 0x200D:
        return False

    def nearest_base(start: int, step: int) -> str | None:
        cursor = start
        while 0 <= cursor < len(value):
            character = value[cursor]
            if not unicodedata.category(character).startswith("M"):
                return character
            cursor += step
        return None

    left = nearest_base(index - 1, -1)
    right = nearest_base(index + 1, 1)
    def pictographic(character: str) -> bool:
        codepoint = ord(character)
        return 0x1F000 <= codepoint <= 0x1FAFF or 0x2600 <= codepoint <= 0x27BF

    return left is not None and right is not None and pictographic(left) and pictographic(right)


def _binding_delimiter(character: str) -> bool:
    return character.isspace() or unicodedata.category(character).startswith("P")


def _reference_token_spans(value: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in REFERENCE_LIKE_TOKEN.finditer(value):
        for group in ("at", "bare", "cjk"):
            if match.group(group) is not None:
                spans.append(match.span(group))
                break
    return spans


def _validate_visible_text(value: str, pointer: str) -> None:
    for index, character in enumerate(value):
        codepoint = ord(character)
        if (codepoint < 0x20 and codepoint not in {0x09, 0x0A, 0x0D}) or 0x7F <= codepoint <= 0x9F:
            _fail("TEXT_CONTROL_FORBIDDEN", pointer)
        if unicodedata.category(character) == "Cf" and not _valid_emoji_zwj_context(value, index):
            _fail("UNICODE_FORMAT_CONTROL_FORBIDDEN", pointer)


def parse_json_bytes(raw: bytes, label: str = "input") -> Any:
    if len(raw) > MAX_INPUT_BYTES:
        _fail("JSON_TOO_LARGE")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("JSON_BOM_FORBIDDEN")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("JSON_UTF8_REQUIRED")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_nonfinite,
            parse_int=_parse_integer,
            parse_float=_parse_float,
        )
    except BindingError:
        raise
    except RecursionError:
        _fail("JSON_TOO_DEEP")
    except json.JSONDecodeError:
        _fail("JSON_INVALID")
    _check_json_depth(value)
    return value


def canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail("OUTPUT_NOT_CANONICAL")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        checker = getattr(path, "is_junction", None)
        if checker is not None and checker():
            return True
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _read_plain_file(path: Path, max_bytes: int, *, internal_root: Path | None = None) -> bytes:
    candidate = path.absolute()
    if internal_root is not None:
        try:
            root = internal_root.resolve(strict=True)
        except (OSError, RuntimeError):
            _fail("FILE_ROOT_UNREADABLE")
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            _fail("FILE_ESCAPES_ROOT")
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if _is_link_like(cursor):
                _fail("FILE_LINK_FORBIDDEN")
    elif _is_link_like(candidate):
        _fail("FILE_LINK_FORBIDDEN")

    try:
        before = candidate.lstat()
    except OSError:
        _fail("FILE_UNREADABLE")
    if not stat.S_ISREG(before.st_mode):
        _fail("FILE_REGULAR_REQUIRED")
    if before.st_nlink != 1:
        _fail("FILE_HARDLINK_FORBIDDEN")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError:
        _fail("FILE_UNREADABLE")
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode) or after.st_nlink != 1:
            _fail("FILE_REGULAR_REQUIRED")
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            _fail("FILE_CHANGED_DURING_READ")
        def read_pass() -> bytes:
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(descriptor, min(65_536, max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    _fail("FILE_TOO_LARGE")
            return b"".join(chunks)

        first_raw = read_pass()
        final = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ):
            _fail("FILE_CHANGED_DURING_READ")
        os.lseek(descriptor, 0, os.SEEK_SET)
        second_raw = read_pass()
        second_final = os.fstat(descriptor)
        if first_raw != second_raw or (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_nlink,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        ) != (
            second_final.st_dev,
            second_final.st_ino,
            second_final.st_mode,
            second_final.st_nlink,
            second_final.st_size,
            second_final.st_mtime_ns,
            second_final.st_ctime_ns,
        ):
            _fail("FILE_CHANGED_DURING_READ")
        return first_raw
    except BindingError:
        raise
    except OSError:
        _fail("FILE_UNREADABLE")
    finally:
        os.close(descriptor)


def _internal_path(root: Path, relative: str) -> Path:
    if "\\" in relative:
        _fail("PROFILE_PATH_INVALID")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _fail("PROFILE_PATH_INVALID")
    return root.joinpath(*path.parts)


def _read_internal_descriptor_walk(root: Path, relative: str, max_bytes: int) -> bytes:
    """Open a fixed internal path without trusting mutable ancestor names."""
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("FILE_ROOT_UNREADABLE")
    candidate = _internal_path(root, relative)
    if not SECURE_DIRFD_SUPPORTED:
        return _read_plain_file(candidate, max_bytes, internal_root=root)

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    common = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_flags = common | directory | nofollow
    file_flags = common | nofollow
    directories: list[int] = []
    identities: list[tuple[int, tuple[int, int, int, int]]] = []
    descriptor: int | None = None
    try:
        root_descriptor = os.open(root, directory_flags)
        directories.append(root_descriptor)
        root_stat = os.fstat(root_descriptor)
        identities.append(
            (
                root_descriptor,
                (root_stat.st_dev, root_stat.st_ino, root_stat.st_mtime_ns, root_stat.st_ctime_ns),
            )
        )
        parent = root_descriptor
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            before = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                _fail("FILE_ANCESTOR_INVALID")
            opened_descriptor = os.open(part, directory_flags, dir_fd=parent)
            opened = os.fstat(opened_descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or opened.st_dev != root_stat.st_dev
            ):
                os.close(opened_descriptor)
                _fail("FILE_ANCESTOR_CHANGED")
            directories.append(opened_descriptor)
            identities.append(
                (
                    opened_descriptor,
                    (opened.st_dev, opened.st_ino, opened.st_mtime_ns, opened.st_ctime_ns),
                )
            )
            parent = opened_descriptor

        leaf = parts[-1]
        before_file = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before_file.st_mode):
            _fail("FILE_REGULAR_REQUIRED")
        if before_file.st_nlink != 1:
            _fail("FILE_HARDLINK_FORBIDDEN")
        if before_file.st_size > max_bytes:
            _fail("FILE_TOO_LARGE")
        descriptor = os.open(leaf, file_flags, dir_fd=parent)
        opened_file = os.fstat(descriptor)
        before_identity = (
            before_file.st_dev,
            before_file.st_ino,
            before_file.st_size,
            before_file.st_mtime_ns,
            before_file.st_ctime_ns,
        )
        opened_identity = (
            opened_file.st_dev,
            opened_file.st_ino,
            opened_file.st_size,
            opened_file.st_mtime_ns,
            opened_file.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(opened_file.st_mode)
            or opened_file.st_nlink != 1
            or opened_identity != before_identity
        ):
            _fail("FILE_CHANGED_DURING_OPEN")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after_file = os.fstat(descriptor)
        after_identity = (
            after_file.st_dev,
            after_file.st_ino,
            after_file.st_size,
            after_file.st_mtime_ns,
            after_file.st_ctime_ns,
        )
        if after_identity != opened_identity:
            _fail("FILE_CHANGED_DURING_READ")
        for directory_descriptor, expected in identities:
            current = os.fstat(directory_descriptor)
            if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns) != expected:
                _fail("FILE_ANCESTOR_CHANGED")
        if len(raw) > max_bytes or len(raw) != before_file.st_size:
            _fail("FILE_INCOMPLETE_READ")
        return raw
    except BindingError:
        raise
    except OSError:
        _fail("FILE_UNREADABLE")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_descriptor in reversed(directories):
            os.close(directory_descriptor)


def read_internal_bytes(root: Path, relative: str) -> bytes:
    _internal_path(root, relative)
    return _read_internal_descriptor_walk(root, relative, MAX_PROFILE_BYTES)


def _validate_pin(pin: object, pointer: str) -> dict[str, Any]:
    data = _exact_keys(pin, PIN_KEYS, pointer)
    if not _is_profile_id(data["claim_id"]):
        _fail("CLAIM_ID_INVALID", f"{pointer}/claim_id")
    if not isinstance(data["claim_sha256"], str) or not SHA256.fullmatch(data["claim_sha256"]):
        _fail("CLAIM_HASH_INVALID", f"{pointer}/claim_sha256")
    if not isinstance(data["expires_at"], str):
        _fail("CLAIM_EXPIRY_INVALID", f"{pointer}/expires_at")
    if not DATE_TEXT.fullmatch(data["expires_at"]):
        _fail("CLAIM_EXPIRY_INVALID", f"{pointer}/expires_at")
    try:
        date.fromisoformat(data["expires_at"])
    except ValueError:
        _fail("CLAIM_EXPIRY_INVALID", f"{pointer}/expires_at")
    return data


def _validate_profile_header(data: dict[str, Any], pointer: str) -> None:
    if data["schema_version"] != 1 or not _is_int(data["schema_version"]):
        _fail("PROFILE_VERSION_UNSUPPORTED", f"{pointer}/schema_version")
    if not _is_profile_id(data["profile_id"]):
        _fail("PROFILE_ID_INVALID", f"{pointer}/profile_id")
    if not isinstance(data["status"], str) or data["status"] not in {"candidate", "active", "retired"}:
        _fail("PROFILE_STATUS_INVALID", f"{pointer}/status")
    if not isinstance(data["runtime_enabled"], bool):
        _fail("PROFILE_RUNTIME_FLAG_INVALID", f"{pointer}/runtime_enabled")


def _validate_model_profile(value: object) -> dict[str, Any]:
    data = _exact_keys(value, MODEL_KEYS, "/model")
    _validate_profile_header(data, "/model")
    if data["$schema"] != MODEL_SCHEMA_URI or data["profile_kind"] != "model":
        _fail("MODEL_PROFILE_CONTRACT_INVALID", "/model")
    if not isinstance(data["model_family"], str) or not 1 <= len(data["model_family"]) <= 80:
        _fail("MODEL_FAMILY_INVALID", "/model/model_family")
    if not isinstance(data["model_version"], str) or not 1 <= len(data["model_version"]) <= 80:
        _fail("MODEL_VERSION_INVALID", "/model/model_version")
    contract = _exact_keys(data["binding_contract"], {"owner", "universal_prompt_handle"}, "/model/binding_contract")
    if contract != {"owner": "surface_profile", "universal_prompt_handle": False}:
        _fail("MODEL_BINDING_OWNERSHIP_INVALID", "/model/binding_contract")
    if not isinstance(data["input_modalities"], list) or not data["input_modalities"]:
        _fail("MODEL_MODALITIES_INVALID", "/model/input_modalities")
    if not all(isinstance(item, str) for item in data["input_modalities"]):
        _fail("MODEL_MODALITIES_INVALID", "/model/input_modalities")
    if set(data["input_modalities"]) - {"audio", "image", "text", "video"}:
        _fail("MODEL_MODALITIES_INVALID", "/model/input_modalities")
    if len(data["input_modalities"]) != len(set(data["input_modalities"])):
        _fail("MODEL_MODALITIES_INVALID", "/model/input_modalities")
    dimensions = data["reference_control_dimensions"]
    if not isinstance(dimensions, list) or not dimensions or not all(isinstance(item, str) for item in dimensions):
        _fail("MODEL_DIMENSIONS_INVALID", "/model/reference_control_dimensions")
    if set(dimensions) - {"camera_movement", "lighting", "performance", "shadow"}:
        _fail("MODEL_DIMENSIONS_INVALID", "/model/reference_control_dimensions")
    if len(dimensions) != len(set(dimensions)):
        _fail("MODEL_DIMENSIONS_INVALID", "/model/reference_control_dimensions")
    if not isinstance(data["evidence_pins"], list) or not data["evidence_pins"]:
        _fail("PROFILE_EVIDENCE_REQUIRED", "/model/evidence_pins")
    pins = [_validate_pin(pin, f"/model/evidence_pins/{index}") for index, pin in enumerate(data["evidence_pins"])]
    if len({pin["claim_id"] for pin in pins}) != len(pins):
        _fail("PROFILE_EVIDENCE_DUPLICATE", "/model/evidence_pins")
    return data


def _validate_operation(value: object, pointer: str) -> dict[str, Any]:
    data = _exact_keys(value, OPERATION_KEYS, pointer)
    if not isinstance(data["operation"], str) or data["operation"] not in OPERATIONS:
        _fail("OPERATION_INVALID", f"{pointer}/operation")
    if not isinstance(data["request_transport"], str) or data["request_transport"] not in TRANSPORTS:
        _fail("TRANSPORT_INVALID", f"{pointer}/request_transport")
    media = data["allowed_media_types"]
    if (
        not isinstance(media, list)
        or not media
        or not all(isinstance(item, str) for item in media)
        or set(media) - MEDIA_TYPES
        or len(media) != len(set(media))
    ):
        _fail("MEDIA_TYPES_INVALID", f"{pointer}/allowed_media_types")
    prompt_binding = data["prompt_binding"]
    if not isinstance(prompt_binding, dict) or not isinstance(prompt_binding.get("kind"), str):
        _fail("PROMPT_BINDING_MODE_INVALID", f"{pointer}/prompt_binding")
    binding_kind = prompt_binding["kind"]
    if binding_kind == "opaque_external_handle":
        binding = _exact_keys(prompt_binding, OPAQUE_PROMPT_BINDING_KEYS, f"{pointer}/prompt_binding")
        if binding["source"] != "surface_captured_exact":
            _fail("OPAQUE_HANDLE_SOURCE_INVALID", f"{pointer}/prompt_binding/source")
        if data["request_transport"] != "external_surface_unresolved":
            _fail("OPAQUE_TRANSPORT_MISMATCH", pointer)
    elif binding_kind == "derived_media_ordinal":
        binding = _exact_keys(prompt_binding, DERIVED_PROMPT_BINDING_KEYS, f"{pointer}/prompt_binding")
        if binding["position_scope"] != "per_media_type":
            _fail("POSITION_SCOPE_INVALID", f"{pointer}/prompt_binding/position_scope")
        if data["request_transport"] not in {"typed_media_arrays", "ordered_content_objects"}:
            _fail("POSITION_TRANSPORT_MISMATCH", pointer)
        formatters = binding["media_formatters"]
        if not isinstance(formatters, dict) or set(formatters) != set(media):
            _fail("MEDIA_FORMATTERS_INVALID", f"{pointer}/prompt_binding/media_formatters")
        generated: set[str] = set()
        for media_type in sorted(formatters):
            formatter_pointer = f"{pointer}/prompt_binding/media_formatters/{media_type}"
            formatter = _exact_keys(formatters[media_type], MEDIA_FORMATTER_KEYS, formatter_pointer)
            if (
                not isinstance(formatter["sigil"], str)
                or not isinstance(formatter["media_label"], str)
                or not formatter["media_label"]
                or not isinstance(formatter["separator"], str)
                or formatter["ordinal_base"] != 1
                or not _is_int(formatter["ordinal_base"])
                or any(len(formatter[field]) > 32 for field in ("sigil", "media_label", "separator"))
            ):
                _fail("MEDIA_FORMATTER_INVALID", formatter_pointer)
            for ordinal in range(1, 65):
                handle = _validate_handle(
                    formatter["sigil"]
                    + formatter["media_label"]
                    + formatter["separator"]
                    + str(ordinal),
                    formatter_pointer,
                )
                collision_key = _handle_collision_key(handle)
                if collision_key in generated:
                    _fail("MEDIA_FORMATTER_COLLISION", formatter_pointer)
                generated.add(collision_key)
    elif binding_kind == "none":
        _exact_keys(prompt_binding, NONE_PROMPT_BINDING_KEYS, f"{pointer}/prompt_binding")
    else:
        _fail("PROMPT_BINDING_MODE_INVALID", f"{pointer}/prompt_binding/kind")
    roles = data["structured_roles"]
    required_roles = data["required_role_set"]
    if (
        not isinstance(roles, list)
        or not isinstance(required_roles, list)
        or not all(isinstance(item, str) for item in roles)
        or not all(isinstance(item, str) for item in required_roles)
        or set(roles) - STRUCTURED_ROLES
        or set(required_roles) - set(roles)
        or len(roles) != len(set(roles))
        or len(required_roles) != len(set(required_roles))
    ):
        _fail("STRUCTURED_ROLES_INVALID", pointer)
    if data["request_transport"] == "structured_content_roles":
        if binding_kind != "none" or not roles:
            _fail("STRUCTURED_BINDING_CONTRACT_INVALID", pointer)
    elif roles or required_roles or binding_kind == "none":
        _fail("STRUCTURED_ROLE_TRANSPORT_MISMATCH", pointer)
    pins = data["evidence_pins"]
    if not isinstance(pins, list) or not pins:
        _fail("PROFILE_EVIDENCE_REQUIRED", f"{pointer}/evidence_pins")
    checked = [_validate_pin(pin, f"{pointer}/evidence_pins/{index}") for index, pin in enumerate(pins)]
    if len({pin["claim_id"] for pin in checked}) != len(checked):
        _fail("PROFILE_EVIDENCE_DUPLICATE", f"{pointer}/evidence_pins")
    return data


def _validate_surface_profile(value: object) -> dict[str, Any]:
    data = _exact_keys(value, SURFACE_KEYS, "/surface")
    _validate_profile_header(data, "/surface")
    if data["$schema"] != SURFACE_SCHEMA_URI or data["profile_kind"] != "surface":
        _fail("SURFACE_PROFILE_CONTRACT_INVALID", "/surface")
    if not _is_profile_id(data["model_profile_id"]):
        _fail("MODEL_PROFILE_ID_INVALID", "/surface/model_profile_id")
    if data["fallback_policy"] != "fail_closed":
        _fail("PROFILE_FALLBACK_FORBIDDEN", "/surface/fallback_policy")
    operations = data["operations"]
    if not isinstance(operations, list) or not operations:
        _fail("PROFILE_OPERATIONS_REQUIRED", "/surface/operations")
    checked = [_validate_operation(item, f"/surface/operations/{index}") for index, item in enumerate(operations)]
    names = [item["operation"] for item in checked]
    if len(names) != len(set(names)):
        _fail("PROFILE_OPERATION_DUPLICATE", "/surface/operations")
    return data


def _validate_index_entry(value: object, pointer: str) -> dict[str, Any]:
    data = _exact_keys(value, INDEX_ENTRY_KEYS, pointer)
    if not _is_profile_id(data["profile_id"]):
        _fail("PROFILE_ID_INVALID", f"{pointer}/profile_id")
    if not isinstance(data["path"], str) or not SAFE_PROFILE_PATH.fullmatch(data["path"]):
        _fail("PROFILE_PATH_INVALID", f"{pointer}/path")
    if not isinstance(data["sha256"], str) or not SHA256.fullmatch(data["sha256"]):
        _fail("PROFILE_HASH_INVALID", f"{pointer}/sha256")
    if (
        not isinstance(data["status"], str)
        or data["status"] not in {"candidate", "active", "retired"}
        or not isinstance(data["runtime_enabled"], bool)
    ):
        _fail("PROFILE_INDEX_STATE_INVALID", pointer)
    return data


def load_registry(root: Path = ROOT) -> ProfileRegistry:
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("FILE_ROOT_UNREADABLE")
    index_raw = read_internal_bytes(root, INDEX_PATH)
    index = _exact_keys(parse_json_bytes(index_raw, INDEX_PATH), INDEX_KEYS, "/index")
    if index["$schema"] != INDEX_SCHEMA_URI or index["schema_version"] != 1 or not _is_int(index["schema_version"]):
        _fail("PROFILE_INDEX_CONTRACT_INVALID", "/index")
    if index["activation_enabled"] is not False or index["unknown_profile_policy"] != "fail_closed":
        _fail("PROFILE_ACTIVATION_FORBIDDEN", "/index")
    if ACTIVATION_SUPPORTED:
        _fail("V705_ACTIVATION_GUARD_INVALID")

    loaded_groups: dict[str, dict[str, LoadedProfile]] = {"models": {}, "surfaces": {}}
    all_paths: set[str] = set()
    for group in ("models", "surfaces"):
        entries = index[group]
        if not isinstance(entries, list) or not entries:
            _fail("PROFILE_INDEX_EMPTY", f"/index/{group}")
        checked = [_validate_index_entry(item, f"/index/{group}/{number}") for number, item in enumerate(entries)]
        if [item["profile_id"] for item in checked] != sorted(item["profile_id"] for item in checked):
            _fail("PROFILE_INDEX_UNSORTED", f"/index/{group}")
        for item in checked:
            if item["profile_id"] in loaded_groups[group] or item["path"] in all_paths:
                _fail("PROFILE_INDEX_DUPLICATE", f"/index/{group}")
            expected_prefix = f"profiles/{'models' if group == 'models' else 'surfaces'}/"
            if not item["path"].startswith(expected_prefix):
                _fail("PROFILE_PATH_KIND_MISMATCH", f"/index/{group}")
            raw = read_internal_bytes(root, item["path"])
            digest = sha256_bytes(raw)
            if digest != item["sha256"]:
                _fail("PROFILE_HASH_MISMATCH", f"/index/{group}")
            parsed = parse_json_bytes(raw, item["path"])
            data = _validate_model_profile(parsed) if group == "models" else _validate_surface_profile(parsed)
            if (
                data["profile_id"] != item["profile_id"]
                or data["status"] != item["status"]
                or data["runtime_enabled"] != item["runtime_enabled"]
            ):
                _fail("PROFILE_INDEX_CONTENT_MISMATCH", f"/index/{group}")
            if data["status"] != "candidate" or data["runtime_enabled"] is not False:
                _fail("V705_PROFILE_MUST_BE_CANDIDATE", f"/index/{group}")
            loaded_groups[group][item["profile_id"]] = LoadedProfile(
                item["profile_id"], item["path"], digest, data
            )
            all_paths.add(item["path"])

    for profile in loaded_groups["surfaces"].values():
        if profile.data["model_profile_id"] not in loaded_groups["models"]:
            _fail("MODEL_PROFILE_NOT_FOUND", "/surface/model_profile_id")
    return ProfileRegistry(
        index_sha256=sha256_bytes(index_raw),
        index=index,
        models=loaded_groups["models"],
        surfaces=loaded_groups["surfaces"],
    )


def _validate_handle(handle: object, pointer: str) -> str:
    if not isinstance(handle, str) or not handle or len(handle) > 512:
        _fail("HANDLE_INVALID", pointer)
    has_visible_base = False
    for index, character in enumerate(handle):
        codepoint = ord(character)
        if (
            codepoint < 0x20
            or 0x7F <= codepoint <= 0x9F
            or 0xD800 <= codepoint <= 0xDFFF
            or codepoint in FORBIDDEN_HANDLE_CODEPOINTS
            or (
                unicodedata.category(character) == "Cf"
                and not _valid_emoji_zwj_context(handle, index)
            )
        ):
            _fail("HANDLE_UNSAFE_CODEPOINT", pointer)
        if (
            not character.isspace()
            and unicodedata.category(character)[0] not in {"C", "M"}
        ):
            has_visible_base = True
    if not has_visible_base:
        _fail("HANDLE_VISIBLE_BASE_REQUIRED", pointer)
    return handle


def _handle_collision_key(handle: str) -> str:
    # A permitted emoji joiner may be invisible or ignored by a renderer. Treat
    # joined and unjoined spellings as the same review identity while preserving
    # the caller's exact bytes in the rendered prompt.
    visible_identity = "".join(character for character in handle if ord(character) != 0x200D)
    return unicodedata.normalize("NFC", visible_identity).casefold()


def _operation_profile(profile: LoadedProfile, operation: str) -> dict[str, Any]:
    matches = [item for item in profile.data["operations"] if item["operation"] == operation]
    if len(matches) != 1:
        _fail("OPERATION_UNSUPPORTED", "/operation")
    return matches[0]


def _effective_evidence(
    model_profile: dict[str, Any], operation_profile: dict[str, Any]
) -> tuple[list[str], date]:
    pins = [*model_profile["evidence_pins"], *operation_profile["evidence_pins"]]
    seen: dict[str, tuple[str, str]] = {}
    claim_ids: list[str] = []
    for pin in pins:
        identity = (pin["claim_sha256"], pin["expires_at"])
        previous = seen.get(pin["claim_id"])
        if previous is not None and previous != identity:
            _fail("PROFILE_EVIDENCE_CONFLICT", "/profile_id")
        if previous is None:
            seen[pin["claim_id"]] = identity
            claim_ids.append(pin["claim_id"])
    return claim_ids, min(date.fromisoformat(pin["expires_at"]) for pin in pins)


def validate_plan(value: object) -> dict[str, Any]:
    plan = _exact_keys(value, PLAN_KEYS, "/")
    if plan["$schema"] != PLAN_SCHEMA_URI or plan["schema_version"] != 1 or not _is_int(plan["schema_version"]):
        _fail("PLAN_CONTRACT_INVALID", "/")
    if not _is_profile_id(plan["profile_id"]):
        _fail("PROFILE_ID_INVALID", "/profile_id")
    if not isinstance(plan["operation"], str) or plan["operation"] not in OPERATIONS:
        _fail("OPERATION_INVALID", "/operation")
    if not isinstance(plan["segments"], list) or not 1 <= len(plan["segments"]) <= 256:
        _fail("SEGMENTS_INVALID", "/segments")
    if not isinstance(plan["bindings"], list) or not 1 <= len(plan["bindings"]) <= 64:
        _fail("BINDINGS_INVALID", "/bindings")
    return plan


def render_plan(
    value: object,
    *,
    preview_candidate: bool = False,
    today: date | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    plan = validate_plan(value)
    registry = load_registry(root)
    profile = registry.surfaces.get(plan["profile_id"])
    if profile is None:
        _fail("PROFILE_UNKNOWN", "/profile_id")
    if not preview_candidate:
        _fail("PROFILE_CANDIDATE_REQUIRES_PREVIEW", "/profile_id")
    if profile.data["status"] != "candidate" or profile.data["runtime_enabled"] is not False:
        _fail("V705_PROFILE_MUST_BE_CANDIDATE", "/profile_id")

    operation = _operation_profile(profile, plan["operation"])
    model_profile = registry.models[profile.data["model_profile_id"]]
    evidence_claim_ids, expiry = _effective_evidence(model_profile.data, operation)
    current = today or datetime.now(timezone.utc).date()
    if current >= expiry:
        _fail("PROFILE_EVIDENCE_EXPIRED", "/profile_id")

    bindings_by_id: dict[str, dict[str, Any]] = {}
    handle_keys: dict[str, str] = {}
    request_bindings: list[dict[str, Any]] = []
    prompt_handles: dict[str, str] = {}
    media_positions = {media: 0 for media in MEDIA_TYPES}
    roles_seen: set[str] = set()
    binding_kind = operation["prompt_binding"]["kind"]

    for index, raw_binding in enumerate(plan["bindings"]):
        pointer = f"/bindings/{index}"
        if not isinstance(raw_binding, dict) or not set(raw_binding).issubset(BINDING_KEYS):
            _fail("BINDING_FIELDS_INVALID", pointer)
        if set(raw_binding) < {"binding_id", "media_type"}:
            _fail("BINDING_FIELDS_INVALID", pointer)
        binding_id = raw_binding["binding_id"]
        if not isinstance(binding_id, str) or not SAFE_BINDING_ID.fullmatch(binding_id):
            _fail("BINDING_ID_INVALID", f"{pointer}/binding_id")
        if binding_id in bindings_by_id:
            _fail("BINDING_ID_DUPLICATE", f"{pointer}/binding_id")
        media_type = raw_binding["media_type"]
        if not isinstance(media_type, str) or media_type not in operation["allowed_media_types"]:
            _fail("BINDING_MEDIA_UNSUPPORTED", f"{pointer}/media_type")

        request_record: dict[str, Any] = {"binding_id": binding_id, "media_type": media_type}
        if binding_kind == "derived_media_ordinal":
            media_positions[media_type] += 1
            request_record["request_position"] = media_positions[media_type]

        if binding_kind == "opaque_external_handle":
            if set(raw_binding) != {"binding_id", "media_type", "prompt_visible_handle"}:
                _fail("OPAQUE_BINDING_FIELDS_INVALID", pointer)
            handle = _validate_handle(raw_binding["prompt_visible_handle"], f"{pointer}/prompt_visible_handle")
            collision_key = _handle_collision_key(handle)
            if collision_key in handle_keys:
                _fail("HANDLE_COLLISION", f"{pointer}/prompt_visible_handle")
            handle_keys[collision_key] = binding_id
            prompt_handles[binding_id] = handle
        elif binding_kind == "derived_media_ordinal":
            if set(raw_binding) != {"binding_id", "media_type"}:
                _fail("DERIVED_BINDING_FIELDS_INVALID", pointer)
            formatter = operation["prompt_binding"]["media_formatters"][media_type]
            handle = _validate_handle(
                formatter["sigil"]
                + formatter["media_label"]
                + formatter["separator"]
                + str(media_positions[media_type]),
                pointer,
            )
            collision_key = _handle_collision_key(handle)
            if collision_key in handle_keys:
                _fail("HANDLE_COLLISION", pointer)
            handle_keys[collision_key] = binding_id
            prompt_handles[binding_id] = handle
        else:
            if set(raw_binding) != {"binding_id", "media_type", "structured_role"}:
                _fail("STRUCTURED_BINDING_FIELDS_INVALID", pointer)
            role = raw_binding["structured_role"]
            if not isinstance(role, str) or role not in operation["structured_roles"]:
                _fail("STRUCTURED_ROLE_UNSUPPORTED", f"{pointer}/structured_role")
            if role in roles_seen:
                _fail("STRUCTURED_ROLE_DUPLICATE", f"{pointer}/structured_role")
            roles_seen.add(role)
            request_record["structured_role"] = role

        bindings_by_id[binding_id] = raw_binding
        request_bindings.append(request_record)

    if roles_seen != set(operation["required_role_set"]):
        _fail("STRUCTURED_ROLE_SET_INCOMPLETE", "/bindings")

    chunks: list[str] = []
    binding_spans: list[tuple[int, int]] = []
    used_bindings: set[str] = set()
    total = 0
    previous_kind: str | None = None
    for index, segment in enumerate(plan["segments"]):
        pointer = f"/segments/{index}"
        if not isinstance(segment, dict):
            _fail("SEGMENT_INVALID", pointer)
        kind = segment.get("kind")
        if not isinstance(kind, str) or kind not in {"text", "binding"}:
            _fail("SEGMENT_INVALID", pointer)
        if kind == "text":
            if set(segment) != {"kind", "value"} or not isinstance(segment["value"], str) or not segment["value"]:
                _fail("TEXT_SEGMENT_INVALID", pointer)
            if len(segment["value"]) > MAX_TEXT_SEGMENT:
                _fail("TEXT_SEGMENT_TOO_LARGE", f"{pointer}/value")
            _check_scalar_text(segment["value"], f"{pointer}/value")
            _validate_visible_text(segment["value"], f"{pointer}/value")
            if REFERENCE_LIKE_TOKEN.search(segment["value"]):
                _fail("REFERENCE_TOKEN_IN_TEXT_FORBIDDEN", f"{pointer}/value")
            if previous_kind == "binding" and not _binding_delimiter(segment["value"][0]):
                _fail("BINDING_DELIMITER_REQUIRED", f"{pointer}/value")
            chunk = segment["value"]
        else:
            if set(segment) != {"kind", "binding_id"}:
                _fail("BINDING_SEGMENT_INVALID", pointer)
            if binding_kind == "none":
                _fail("STRUCTURED_BINDING_IN_PROMPT", pointer)
            binding_id = segment["binding_id"]
            if not isinstance(binding_id, str) or binding_id not in bindings_by_id:
                _fail("BINDING_SEGMENT_UNKNOWN", f"{pointer}/binding_id")
            if previous_kind == "binding":
                _fail("BINDING_DELIMITER_REQUIRED", pointer)
            if previous_kind == "text" and not _binding_delimiter(chunks[-1][-1]):
                _fail("BINDING_DELIMITER_REQUIRED", pointer)
            used_bindings.add(binding_id)
            chunk = prompt_handles[binding_id]
            binding_spans.append((total, total + len(chunk)))
        total += len(chunk)
        if total > MAX_RENDERED_PROMPT:
            _fail("RENDERED_PROMPT_TOO_LARGE", "/segments")
        chunks.append(chunk)
        previous_kind = kind

    if binding_kind != "none" and used_bindings != set(bindings_by_id):
        _fail("PROMPT_BINDING_UNUSED", "/bindings")
    rendered_prompt = "".join(chunks)
    if not rendered_prompt:
        _fail("RENDERED_PROMPT_EMPTY", "/segments")
    for token_start, token_end in _reference_token_spans(rendered_prompt):
        if not any(start <= token_start and token_end <= end for start, end in binding_spans):
            _fail("REFERENCE_TOKEN_PROVENANCE_INVALID", "/segments")

    return {
        "$schema": RENDER_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": profile.profile_id,
        "profile_index_sha256": registry.index_sha256,
        "profile_sha256": profile.sha256,
        "profile_status": profile.data["status"],
        "preview": True,
        "model_profile_id": profile.data["model_profile_id"],
        "model_profile_sha256": model_profile.sha256,
        "operation": plan["operation"],
        "request_transport": operation["request_transport"],
        "rendered_prompt": rendered_prompt,
        "request_bindings": request_bindings,
        "evidence_claim_ids": evidence_claim_ids,
        "evidence_expires_at": expiry.isoformat(),
    }


def _read_request(path: str) -> bytes:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        return raw
    return _read_plain_file(Path(path), MAX_INPUT_BYTES)


def _self_test() -> None:
    opaque_request = {
        "$schema": PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": "byteplus.modelark",
        "operation": "reference_generation",
        "segments": [
            {"kind": "binding", "binding_id": "product"},
            {"kind": "text", "value": " controls product geometry."},
        ],
        "bindings": [
            {
                "binding_id": "product",
                "media_type": "image",
                "prompt_visible_handle": "@Image 1",
            }
        ],
    }
    result = render_plan(opaque_request, preview_candidate=True)
    if result["rendered_prompt"] != "@Image 1 controls product geometry.":
        _fail("SELF_TEST_FAILED")
    if result["request_bindings"] != [{"binding_id": "product", "media_type": "image"}]:
        _fail("SELF_TEST_FAILED")

    derived_request = {
        "$schema": PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": "fal.reference-to-video",
        "operation": "reference_generation",
        "segments": [
            {"kind": "binding", "binding_id": "product"},
            {"kind": "text", "value": " controls product geometry."},
        ],
        "bindings": [{"binding_id": "product", "media_type": "image"}],
    }
    derived = render_plan(derived_request, preview_candidate=True)
    if derived["rendered_prompt"] != "@Image1 controls product geometry.":
        _fail("SELF_TEST_FAILED")
    if derived["request_bindings"] != [
        {"binding_id": "product", "media_type": "image", "request_position": 1}
    ]:
        _fail("SELF_TEST_FAILED")

    derived_request["profile_id"] = "volcengine.ark"
    volc = render_plan(derived_request, preview_candidate=True)
    if volc["rendered_prompt"] != "图片1 controls product geometry.":
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a typed binding plan through an exact, candidate surface profile."
    )
    parser.add_argument("request", nargs="?", default="-", help="JSON request path, or - for stdin")
    parser.add_argument(
        "--preview-candidate",
        action="store_true",
        help="exercise a disabled candidate profile; output remains explicitly preview-only",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("surface binding renderer self-test passed")
            return 0
        request = parse_json_bytes(_read_request(args.request))
        result = render_plan(request, preview_candidate=args.preview_candidate)
        payload = canonical_json(result)
    except BindingError as exc:
        print(f"binding-render error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
