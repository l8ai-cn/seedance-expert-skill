#!/usr/bin/env python3
"""Build and verify the explicit Seedance runtime package.

The source manifest is a positive, path-by-path allowlist. Builds are content
deterministic: the generated payload manifest contains no timestamp, host path,
or build-machine metadata.
"""
from __future__ import annotations

import argparse
import errno
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


PACKAGE_NAME = "seedance-20"
SOURCE_MANIFEST_VERSION = 1
GENERATED_MANIFEST_VERSION = 1
GENERATED_MANIFEST_NAME = ".seedance-package.json"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_MANIFEST = DEFAULT_ROOT / "runtime" / "seedance-20.manifest.json"

SOURCE_MANIFEST_KEYS = {
    "schema_version",
    "package_name",
    "generated_manifest",
    "locked_payload_size_bytes",
    "locked_tree_sha256",
    "files",
}
GENERATED_MANIFEST_KEYS = {
    "schema_version",
    "package_name",
    "payload_file_count",
    "payload_size_bytes",
    "tree_sha256",
    "files",
}
PAYLOAD_RECORD_KEYS = {"path", "sha256", "size"}
REQUIRED_PAYLOAD_PATHS = {"LICENSE", "SKILL.md", "agents/openai.yaml"}
FORBIDDEN_TOP_LEVEL = {
    ".git", ".github", "data", "docs", "evals", "research", "runtime", "tests", "tools",
}
FORBIDDEN_TOP_LEVEL_FILES = {
    ".gitignore",
    "CHANGELOG.md",
    "README.md",
    "SECURITY.md",
    "V6_SEQUENCE_PROMPT_COMPILER_MANIFEST.md",
}
RUNTIME_SCRIPT_ALLOWLIST = {
    "scripts/av_take_review_check.py",
    "scripts/extract_last_frame.py",
    "scripts/prompt_compile.py",
    "scripts/prompt_compile_v2.py",
    "scripts/project_state_check.py",
    "scripts/project_state_migrate.py",
    "scripts/project_state_v2_check.py",
    "scripts/reference_planner.py",
    "scripts/render_surface_bindings.py",
    "scripts/scene_ir_check.py",
    "scripts/scene_ir_v2_check.py",
    "scripts/semantic_lint.py",
    "scripts/semantic_lint_v2.py",
    "scripts/v2_aux_check.py",
}
REQUIRED_OPERATIONAL_PATHS = {
    "examples/sequence-airport-arrival/clip-01-contract.json",
    "examples/sequence-airport-arrival/clip-01-prompt.md",
    "examples/sequence-airport-arrival/clip-01-take-review.json",
    "examples/sequence-airport-arrival/clip-02-continuation-contract.json",
    "examples/sequence-airport-arrival/clip-02-prompt.md",
    "examples/sequence-airport-arrival/project-state.json",
    "examples/standalone-clip-v2/project-state-v2.json",
    "examples/sequence-airport-arrival/sequence-plan.md",
    "examples/sequence-observed-deviation/project-state-after.json",
    "examples/sequence-observed-deviation/project-state-before.json",
    "examples/sequence-observed-deviation/take-review.json",
    "examples/standalone-clip/project-state.json",
    "profiles/models/seedance-2.0-model.json",
    "profiles/profile-index.json",
    "profiles/surfaces/byteplus-modelark.json",
    "profiles/surfaces/fal-reference-to-video.json",
    "profiles/surfaces/volcengine-ark.json",
    "schemas/binding-plan.schema.json",
    "schemas/binding-render.schema.json",
    "schemas/av-take-review-v1.schema.json",
    "schemas/clip-contract.schema.json",
    "schemas/generation-run.schema.json",
    "schemas/generation-run-v2.schema.json",
    "schemas/model-profile.schema.json",
    "schemas/profile-index.schema.json",
    "schemas/project-state.schema.json",
    "schemas/project-state-v2.schema.json",
    "schemas/project-state-v2-migration-map.schema.json",
    "schemas/project-state-v2-migration-report.schema.json",
    "schemas/planning-report.schema.json",
    "schemas/prompt-program.schema.json",
    "schemas/prompt-compile-request-v2.schema.json",
    "schemas/prompt-program-v2.schema.json",
    "schemas/prompt-realization-catalog.schema.json",
    "schemas/prompt-realization-catalog-v2.schema.json",
    "schemas/prompt-render.schema.json",
    "schemas/prompt-render-v2.schema.json",
    "schemas/prompt-spec.schema.json",
    "schemas/prompt-spec-v2.schema.json",
    "schemas/reference-manifest.schema.json",
    "schemas/scene-ir.schema.json",
    "schemas/scene-ir-v2.schema.json",
    "schemas/surface-av-policy.schema.json",
    "schemas/surface-binding-set-v2.schema.json",
    "schemas/surface-profile.schema.json",
    "schemas/surface-binding-set.schema.json",
    "schemas/take-review.schema.json",
    "schemas/take-review-v2.schema.json",
    "scripts/extract_last_frame.py",
    "scripts/av_take_review_check.py",
    "scripts/prompt_compile.py",
    "scripts/prompt_compile_v2.py",
    "scripts/project_state_check.py",
    "scripts/project_state_migrate.py",
    "scripts/project_state_v2_check.py",
    "scripts/reference_planner.py",
    "scripts/render_surface_bindings.py",
    "scripts/scene_ir_check.py",
    "scripts/scene_ir_v2_check.py",
    "scripts/semantic_lint.py",
    "scripts/semantic_lint_v2.py",
    "scripts/v2_aux_check.py",
}
REQUIRED_SKILL_PATHS = {
    "skills/seedance-antislop/SKILL.md",
    "skills/seedance-audio/SKILL.md",
    "skills/seedance-camera/SKILL.md",
    "skills/seedance-characters/SKILL.md",
    "skills/seedance-continuation/SKILL.md",
    "skills/seedance-copyright/SKILL.md",
    "skills/seedance-examples-ja/SKILL.md",
    "skills/seedance-examples-ko/SKILL.md",
    "skills/seedance-examples-zh/SKILL.md",
    "skills/seedance-filter/SKILL.md",
    "skills/seedance-interview-short/SKILL.md",
    "skills/seedance-interview/SKILL.md",
    "skills/seedance-lighting/SKILL.md",
    "skills/seedance-motion/SKILL.md",
    "skills/seedance-pipeline/SKILL.md",
    "skills/seedance-prompt-short/SKILL.md",
    "skills/seedance-prompt/SKILL.md",
    "skills/seedance-recipes/SKILL.md",
    "skills/seedance-sequence/SKILL.md",
    "skills/seedance-style/SKILL.md",
    "skills/seedance-troubleshoot/SKILL.md",
    "skills/seedance-vfx/SKILL.md",
    "skills/seedance-vocab-en/SKILL.md",
    "skills/seedance-vocab-es/SKILL.md",
    "skills/seedance-vocab-ja/SKILL.md",
    "skills/seedance-vocab-ko/SKILL.md",
    "skills/seedance-vocab-ru/SKILL.md",
    "skills/seedance-vocab-zh/SKILL.md",
}
REQUIRED_COMPATIBILITY_PATHS = {
    "references/json-schema.md",
    "references/platform-constraints.md",
    "references/storytelling-framework.md",
}
TEXT_PAYLOAD_SUFFIXES = {".json", ".md", ".py", ".txt", ".yaml", ".yml"}

REF_TOKEN = re.compile(r"\[ref:([a-z0-9_./-]+)\]")
SKILL_TOKEN = re.compile(r"\[skill:([a-z0-9_./-]+)\]")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_REFERENCE = re.compile(r"(?m)^[ \t]*\[[^\]]+\]:[ \t]*(\S+)")
AUTOLINK = re.compile(r"<([^<>\s]+)>")
HTML_RESOURCE = re.compile(r"(?i)\b(?:href|src)\s*=\s*[\"']([^\"']+)[\"']")
YAML_RESOURCE = re.compile(r"(?m)^[ \t]*(?:icon|image|path|resource|file)\s*:[ \t]*[\"']?([^#\s\"']+)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
ROOT_RESOURCE = re.compile(r"(?<![A-Za-z0-9_.-])((?:assets|examples|profiles|references|schemas|scripts|skills)/[A-Za-z0-9._/*-]+)")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
WINDOWS_ILLEGAL = set('<>:"|?*')
MAX_COMPONENT_LENGTH = 120
MAX_PORTABLE_PATH_LENGTH = 240


class PackageError(ValueError):
    """Raised when a source or built runtime violates the package contract."""


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker and checker())


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def is_special_path(path: Path) -> bool:
    return path.is_symlink() or _is_junction(path) or _is_reparse_point(path) or os.path.ismount(path)


def normalize_relative_path(raw: object, label: str = "path") -> str:
    if not isinstance(raw, str) or not raw:
        raise PackageError(f"{label} must be a non-empty string")
    if "\\" in raw or any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise PackageError(f"{label} must use a safe POSIX relative path: {raw!r}")
    if unicodedata.normalize("NFC", raw) != raw:
        raise PackageError(f"{label} must use NFC-normalized Unicode: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PackageError(f"{label} must stay inside the package: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw:
        raise PackageError(f"{label} is not canonical: {raw!r}")
    if len(raw) > MAX_PORTABLE_PATH_LENGTH:
        raise PackageError(f"{label} exceeds the portable path-length limit: {raw!r}")
    for part in path.parts:
        base = part.split(".", 1)[0].upper()
        if (
            len(part) > MAX_COMPONENT_LENGTH
            or part.endswith((".", " "))
            or any(character in WINDOWS_ILLEGAL for character in part)
            or base in WINDOWS_RESERVED
        ):
            raise PackageError(f"{label} is not portable across supported filesystems: {raw!r}")
    return normalized


def _path_from_posix(root: Path, relative: str) -> Path:
    return root.joinpath(*PurePosixPath(relative).parts)


def _assert_plain_source_file(repo_root: Path, relative: str) -> Path:
    root = repo_root.resolve()
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if is_special_path(cursor):
            raise PackageError(f"runtime source path cannot be a symlink, junction, or mount: {relative}")
    try:
        cursor.resolve().relative_to(root)
    except ValueError as exc:
        raise PackageError(f"runtime source path escapes the repository: {relative}") from exc
    if not cursor.is_file():
        raise PackageError(f"runtime source file is missing: {relative}")
    return cursor


def _validate_runtime_paths(paths: tuple[str, ...], *, require_sorted: bool) -> None:
    if require_sorted and list(paths) != sorted(paths):
        raise PackageError("runtime paths must be sorted")
    if len(paths) != len(set(paths)):
        raise PackageError("runtime paths must be unique")
    folded: dict[str, str] = {}
    generated_folded = unicodedata.normalize("NFC", GENERATED_MANIFEST_NAME).casefold()
    for relative in paths:
        key = unicodedata.normalize("NFC", relative).casefold()
        if key == generated_folded:
            raise PackageError("generated package manifest cannot list itself as a payload file")
        if key in folded:
            raise PackageError(
                f"runtime paths collide on a case-insensitive filesystem: {folded[key]}, {relative}"
            )
        folded[key] = relative
    for folded_path, relative in folded.items():
        parts = PurePosixPath(folded_path).parts
        for depth in range(1, len(parts)):
            ancestor = PurePosixPath(*parts[:depth]).as_posix()
            if ancestor in folded:
                raise PackageError(
                    f"runtime paths contain a file/directory prefix collision: {folded[ancestor]}, {relative}"
                )
    required = (
        REQUIRED_PAYLOAD_PATHS
        | REQUIRED_OPERATIONAL_PATHS
        | REQUIRED_SKILL_PATHS
        | REQUIRED_COMPATIBILITY_PATHS
    )
    missing_required = required - set(paths)
    if missing_required:
        raise PackageError(f"runtime payload misses required files: {sorted(missing_required)}")
    for relative in paths:
        top = PurePosixPath(relative).parts[0]
        top_folded = top.casefold()
        relative_folded = relative.casefold()
        if (
            top_folded in {item.casefold() for item in FORBIDDEN_TOP_LEVEL}
            or relative_folded in {item.casefold() for item in FORBIDDEN_TOP_LEVEL_FILES}
        ):
            raise PackageError(f"development-only path cannot enter runtime: {relative}")
        if relative_folded.startswith("references/migrated/"):
            raise PackageError(f"migrated archive cannot enter runtime: {relative}")
        if relative_folded.startswith("schemas/evidence-"):
            raise PackageError(f"evidence-control schema cannot enter runtime: {relative}")
        if top_folded == "scripts" and relative not in RUNTIME_SCRIPT_ALLOWLIST:
            raise PackageError(f"development script cannot enter runtime: {relative}")


def _validate_source_manifest_data(data: object) -> tuple[tuple[str, ...], str, int]:
    if not isinstance(data, dict):
        raise PackageError("runtime source manifest must be a JSON object")
    extra = set(data) - SOURCE_MANIFEST_KEYS
    missing = SOURCE_MANIFEST_KEYS - set(data)
    if missing or extra:
        raise PackageError(
            f"runtime source manifest fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if type(data["schema_version"]) is not int or data["schema_version"] != SOURCE_MANIFEST_VERSION:
        raise PackageError(f"unsupported runtime source manifest version: {data['schema_version']!r}")
    if data["package_name"] != PACKAGE_NAME:
        raise PackageError(f"unexpected package_name: {data['package_name']!r}")
    if data["generated_manifest"] != GENERATED_MANIFEST_NAME:
        raise PackageError(f"generated_manifest must be {GENERATED_MANIFEST_NAME}")
    locked_sha = data["locked_tree_sha256"]
    locked_size = data["locked_payload_size_bytes"]
    if not isinstance(locked_sha, str) or not SHA256.fullmatch(locked_sha):
        raise PackageError("locked_tree_sha256 must be a lowercase SHA-256")
    if not isinstance(locked_size, int) or isinstance(locked_size, bool) or locked_size < 0:
        raise PackageError("locked_payload_size_bytes must be a non-negative integer")
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise PackageError("runtime source manifest files must be a non-empty array")
    normalized = tuple(normalize_relative_path(item, "runtime file") for item in files)
    _validate_runtime_paths(normalized, require_sorted=True)
    return normalized, locked_sha, locked_size


def load_source_manifest(
    repo_root: Path, manifest_path: Path | None = None
) -> tuple[tuple[str, ...], str, int]:
    input_root = repo_root.expanduser().absolute()
    root = input_root.resolve()
    path = (manifest_path or input_root / "runtime" / "seedance-20.manifest.json").expanduser().absolute()
    try:
        relative_path = path.relative_to(input_root)
    except ValueError as exc:
        raise PackageError("source manifest must stay inside the repository") from exc
    relative = normalize_relative_path(relative_path.as_posix(), "source manifest path")
    path = _assert_plain_source_file(root, relative)
    try:
        data = json.loads(read_plain_source_file(root, relative).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read runtime source manifest: {exc}") from exc
    files, locked_sha, locked_size = _validate_source_manifest_data(data)
    for relative in files:
        _assert_plain_source_file(root, relative)
    return files, locked_sha, locked_size


def read_plain_source_file(repo_root: Path, relative: str) -> bytes:
    path = _assert_plain_source_file(repo_root, relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackageError(f"cannot open runtime source file safely: {relative}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PackageError(f"runtime source is not a regular file: {relative}")
        if metadata.st_mode & (stat.S_ISUID | stat.S_ISGID):
            raise PackageError(f"runtime source cannot carry setuid or setgid mode bits: {relative}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        suffix = PurePosixPath(relative).suffix.lower()
        if suffix in TEXT_PAYLOAD_SUFFIXES or PurePosixPath(relative).name == "LICENSE":
            if b"\x00" in content:
                raise PackageError(f"runtime text source contains a NUL byte: {relative}")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PackageError(f"runtime text source is not valid UTF-8: {relative}") from exc
            content = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        return content
    finally:
        os.close(descriptor)


def _resolve_local_link(source_relative: str, raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    elif " " in target:
        target = target.split(" ", 1)[0]
    if not target or target.startswith("#"):
        return None
    split = urlsplit(target)
    if split.scheme or split.netloc:
        return None
    decoded = unquote(split.path)
    if not decoded:
        return None
    if decoded.startswith("/") or "\\" in decoded:
        raise PackageError(f"absolute or non-POSIX local link in {source_relative}: {raw_target}")
    parts = list(PurePosixPath(source_relative).parent.parts)
    for part in PurePosixPath(decoded).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise PackageError(f"local link escapes the package in {source_relative}: {raw_target}")
            parts.pop()
        else:
            parts.append(part)
    return PurePosixPath(*parts).as_posix()


def validate_link_closure(root: Path, payload_files: tuple[str, ...]) -> None:
    allowed = set(payload_files)
    errors: list[str] = []
    for relative in payload_files:
        if not relative.endswith((".md", "SKILL.md", ".yaml", ".yml")):
            continue
        path = _path_from_posix(root, relative)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative}: cannot read UTF-8 text: {exc}")
            continue
        for ref_id in REF_TOKEN.findall(text):
            target = f"references/{ref_id}.md"
            if target not in allowed:
                errors.append(f"{relative}: unresolved [ref:{ref_id}] -> {target}")
        for skill_id in SKILL_TOKEN.findall(text):
            target = f"skills/{skill_id}/SKILL.md"
            if target not in allowed:
                errors.append(f"{relative}: unresolved [skill:{skill_id}] -> {target}")
        for raw_target in MARKDOWN_LINK.findall(text) + MARKDOWN_REFERENCE.findall(text):
            try:
                target = _resolve_local_link(relative, raw_target)
            except PackageError as exc:
                errors.append(str(exc))
                continue
            if target and target not in allowed:
                errors.append(f"{relative}: unresolved local Markdown link -> {target}")
        for raw_target in AUTOLINK.findall(text) + HTML_RESOURCE.findall(text) + YAML_RESOURCE.findall(text):
            split = urlsplit(raw_target.strip())
            if split.scheme or split.netloc:
                continue
            decoded = unquote(split.path)
            suffix = PurePosixPath(decoded).suffix.lower()
            if not (
                decoded.startswith(("assets/", "examples/", "profiles/", "references/", "schemas/", "scripts/", "skills/"))
                or ("/" in decoded and suffix in {".json", ".md", ".png", ".py", ".svg", ".yaml", ".yml"})
            ):
                continue
            try:
                if decoded.startswith(("assets/", "examples/", "profiles/", "references/", "schemas/", "scripts/", "skills/")):
                    target = decoded
                else:
                    target = _resolve_local_link(relative, raw_target)
            except PackageError as exc:
                errors.append(str(exc))
                continue
            if target and target not in allowed:
                errors.append(f"{relative}: unresolved local resource -> {target}")
        for raw_target in INLINE_CODE.findall(text):
            candidates = ROOT_RESOURCE.findall(raw_target)
            if not any(character.isspace() for character in raw_target):
                candidates.append(raw_target)
            for target_text in dict.fromkeys(candidate.strip().rstrip(".,:;") for candidate in candidates):
                if not target_text or urlsplit(target_text).scheme:
                    continue
                suffix = PurePosixPath(target_text).suffix.lower()
                looks_like_resource = (
                    target_text.startswith(("assets/", "examples/", "profiles/", "references/", "schemas/", "scripts/", "skills/"))
                    or ("/" in target_text and suffix in {".json", ".md", ".png", ".py", ".svg", ".yaml", ".yml"})
                    or ("*" in target_text and "/" in target_text)
                )
                if not looks_like_resource:
                    continue
                if target_text.startswith(("assets/", "examples/", "profiles/", "references/", "schemas/", "scripts/", "skills/")):
                    target = target_text
                else:
                    try:
                        target = _resolve_local_link(relative, target_text)
                    except PackageError as exc:
                        errors.append(str(exc))
                        continue
                if not target:
                    continue
                if "*" in target:
                    if not any(fnmatch.fnmatchcase(candidate, target) for candidate in allowed):
                        errors.append(f"{relative}: inline resource pattern matches no runtime file -> {target}")
                elif target.endswith("/"):
                    if not any(candidate.startswith(target) for candidate in allowed):
                        errors.append(f"{relative}: inline resource directory is absent -> {target}")
                elif target not in allowed:
                    errors.append(f"{relative}: unresolved inline resource -> {target}")
    if errors:
        raise PackageError("runtime link closure failed:\n- " + "\n- ".join(sorted(set(errors))))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_sha256(records: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(str(record["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(record["size"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def package_plan(
    repo_root: Path,
    manifest_path: Path | None = None,
    *,
    enforce_lock: bool = True,
) -> dict[str, object]:
    input_root = repo_root.expanduser().absolute()
    root = input_root.resolve()
    files, locked_sha, locked_size = load_source_manifest(input_root, manifest_path)
    validate_link_closure(root, files)
    records: list[dict[str, object]] = []
    for relative in files:
        data = read_plain_source_file(root, relative)
        records.append({"path": relative, "sha256": _sha256_bytes(data), "size": len(data)})
    plan = {
        "schema_version": GENERATED_MANIFEST_VERSION,
        "package_name": PACKAGE_NAME,
        "payload_file_count": len(records),
        "payload_size_bytes": sum(int(record["size"]) for record in records),
        "tree_sha256": _tree_sha256(records),
        "files": records,
    }
    if enforce_lock:
        if plan["tree_sha256"] != locked_sha:
            raise PackageError(
                f"runtime source tree differs from locked_tree_sha256; "
                f"expected {locked_sha}, got {plan['tree_sha256']}"
            )
        if plan["payload_size_bytes"] != locked_size:
            raise PackageError(
                f"runtime source size differs from locked_payload_size_bytes; "
                f"expected {locked_size}, got {plan['payload_size_bytes']}"
            )
    return plan


def render_generated_manifest(plan: dict[str, object]) -> bytes:
    return (json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_durable_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    try:
        path.chmod(0o644)
    except OSError:
        if os.name != "nt":
            raise


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        unsupported = {errno.EINVAL, getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -1)}
        if exc.errno in unsupported or (os.name == "nt" and exc.errno in {errno.EACCES, errno.EPERM}):
            return
        raise
    try:
        os.fsync(descriptor)
    except OSError as exc:
        unsupported = {errno.EINVAL, getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -1)}
        if exc.errno not in unsupported:
            raise
    finally:
        os.close(descriptor)


def _fsync_package_tree(package_dir: Path) -> None:
    directories = [Path(current) for current, _children, _files in os.walk(package_dir, followlinks=False)]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(directory)


def materialize_package(
    repo_root: Path,
    package_dir: Path,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    input_root = repo_root.expanduser().absolute()
    root = input_root.resolve()
    if is_special_path(package_dir):
        raise PackageError(f"package staging directory cannot be special: {package_dir}")
    if not package_dir.is_dir() or any(package_dir.iterdir()):
        raise PackageError(f"package staging directory must exist and be empty: {package_dir}")
    plan = package_plan(input_root, manifest_path)
    try:
        package_dir.chmod(0o755)
    except OSError:
        pass
    for record in plan["files"]:
        relative = str(record["path"])
        content = read_plain_source_file(root, relative)
        if len(content) != record["size"] or _sha256_bytes(content) != record["sha256"]:
            raise PackageError(f"runtime source changed during packaging: {relative}")
        destination = _path_from_posix(package_dir, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cursor = destination.parent
        while cursor != package_dir.parent:
            try:
                cursor.chmod(0o755)
            except OSError:
                pass
            if cursor == package_dir:
                break
            cursor = cursor.parent
        _write_durable_file(destination, content)
    generated_manifest = package_dir / GENERATED_MANIFEST_NAME
    _write_durable_file(generated_manifest, render_generated_manifest(plan))
    verify_package(package_dir)
    _fsync_package_tree(package_dir)
    return plan


def _validate_generated_manifest_data(data: object) -> tuple[dict[str, object], tuple[str, ...]]:
    if not isinstance(data, dict):
        raise PackageError("generated package manifest must be a JSON object")
    extra = set(data) - GENERATED_MANIFEST_KEYS
    missing = GENERATED_MANIFEST_KEYS - set(data)
    if missing or extra:
        raise PackageError(
            f"generated package manifest fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != GENERATED_MANIFEST_VERSION
        or not isinstance(data["package_name"], str)
        or data["package_name"] != PACKAGE_NAME
    ):
        raise PackageError("generated package manifest identity/version mismatch")
    records = data["files"]
    if not isinstance(records, list) or not records:
        raise PackageError("generated package manifest files must be a non-empty array")
    paths: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != PAYLOAD_RECORD_KEYS:
            raise PackageError(f"invalid payload record at index {index}")
        relative = normalize_relative_path(record["path"], f"payload record {index} path")
        if not isinstance(record["size"], int) or isinstance(record["size"], bool) or record["size"] < 0:
            raise PackageError(f"invalid payload size for {relative}")
        if not isinstance(record["sha256"], str) or not SHA256.fullmatch(record["sha256"]):
            raise PackageError(f"invalid payload SHA-256 for {relative}")
        paths.append(relative)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise PackageError("generated package manifest paths must be sorted and unique")
    _validate_runtime_paths(tuple(paths), require_sorted=True)
    if (
        type(data["payload_file_count"]) is not int
        or data["payload_file_count"] < 0
        or data["payload_file_count"] != len(records)
    ):
        raise PackageError("generated package manifest file count mismatch")
    if (
        type(data["payload_size_bytes"]) is not int
        or data["payload_size_bytes"] < 0
        or data["payload_size_bytes"] != sum(int(record["size"]) for record in records)
    ):
        raise PackageError("generated package manifest payload size mismatch")
    if (
        not isinstance(data["tree_sha256"], str)
        or not SHA256.fullmatch(data["tree_sha256"])
        or data["tree_sha256"] != _tree_sha256(records)
    ):
        raise PackageError("generated package manifest tree SHA-256 mismatch")
    return data, tuple(paths)


def _scan_plain_tree_details(root: Path) -> tuple[set[str], set[str]]:
    if not root.is_dir() or is_special_path(root):
        raise PackageError(f"package root is missing or special: {root}")
    found: set[str] = set()
    found_directories: set[str] = set()
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path != root:
            found_directories.add(current_path.relative_to(root).as_posix())
        for name in list(directories):
            path = current_path / name
            if is_special_path(path):
                raise PackageError(f"package contains a symlink, junction, or mount: {path}")
        for name in files:
            path = current_path / name
            if is_special_path(path) or not path.is_file():
                raise PackageError(f"package contains a special file: {path}")
            found.add(path.relative_to(root).as_posix())
    return found, found_directories


def _scan_plain_tree(root: Path) -> set[str]:
    return _scan_plain_tree_details(root)[0]


def verify_package(package_dir: Path) -> dict[str, object]:
    raw_root = package_dir.expanduser().absolute()
    if is_special_path(raw_root):
        raise PackageError(f"package root is missing or special: {raw_root}")
    root = raw_root.resolve()
    found, found_directories = _scan_plain_tree_details(root)
    manifest_path = root / GENERATED_MANIFEST_NAME
    if GENERATED_MANIFEST_NAME not in found:
        raise PackageError(f"installed package is missing {GENERATED_MANIFEST_NAME}")
    try:
        manifest_bytes = manifest_path.read_bytes()
        raw = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read generated package manifest: {exc}") from exc
    data, payload_files = _validate_generated_manifest_data(raw)
    if manifest_bytes != render_generated_manifest(data):
        raise PackageError("generated package manifest is not in canonical deterministic form")
    expected = set(payload_files) | {GENERATED_MANIFEST_NAME}
    if found != expected:
        raise PackageError(
            f"installed package file set mismatch; missing={sorted(expected - found)}, "
            f"extra={sorted(found - expected)}"
        )
    expected_directories: set[str] = set()
    for relative in expected:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    if found_directories != expected_directories:
        raise PackageError(
            f"installed package directory set mismatch; missing={sorted(expected_directories - found_directories)}, "
            f"extra={sorted(found_directories - expected_directories)}"
        )
    actual_records: list[dict[str, object]] = []
    for record in data["files"]:
        relative = str(record["path"])
        path = _path_from_posix(root, relative)
        if is_special_path(path) or not path.is_file():
            raise PackageError(f"installed payload is special or missing: {relative}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise PackageError(f"installed payload is not a regular file: {relative}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
        actual = {"path": relative, "sha256": _sha256_bytes(content), "size": len(content)}
        actual_records.append(actual)
        if actual != record:
            raise PackageError(f"installed payload integrity mismatch: {relative}")
    if _tree_sha256(actual_records) != data["tree_sha256"]:
        raise PackageError("installed package tree integrity mismatch")
    validate_link_closure(root, payload_files)
    return data


def build_package(
    repo_root: Path,
    output_dir: Path,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    input_root = repo_root.expanduser().absolute()
    root = input_root.resolve()
    output = output_dir.expanduser().absolute()
    if output == root or output in root.parents:
        raise PackageError("build output cannot replace the repository or one of its ancestors")
    if os.path.lexists(output):
        raise PackageError(f"build output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.build-", dir=output.parent))
    activated = False
    try:
        plan = materialize_package(input_root, stage, manifest_path)
        os.replace(stage, output)
        activated = True
        _fsync_directory(output.parent)
        verify_package(output)
        return plan
    except Exception as build_error:
        if activated and os.path.lexists(output):
            if is_special_path(output) or not output.is_dir():
                raise PackageError(f"failed build output became special and was not touched: {output}") from build_error
            quarantine = Path(tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.failed-build-", dir=output.parent))
            quarantine.rmdir()
            os.replace(output, quarantine)
            try:
                _fsync_directory(output.parent)
            except OSError as cleanup_error:
                if hasattr(build_error, "add_note"):
                    build_error.add_note(f"Could not fsync quarantine rename: {cleanup_error}")
            if hasattr(build_error, "add_note"):
                build_error.add_note(f"Failed activated output was quarantined at {quarantine}")
        elif stage.exists():
            shutil.rmtree(stage)
        raise


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _print_plan(plan: dict[str, object], prefix: str) -> None:
    print(f"{prefix}: {plan['payload_file_count']} payload files")
    print(f"Payload size: {format_size(int(plan['payload_size_bytes']))}")
    print(f"Tree SHA-256: {plan['tree_sha256']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the explicit Seedance runtime package.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--manifest", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="validate and print the package plan without writes")
    action.add_argument(
        "--calculate-lock",
        action="store_true",
        help="calculate lock values without enforcing the current lock or writing files",
    )
    action.add_argument("--output", type=Path, help="build into a new output directory")
    action.add_argument("--verify", type=Path, help="verify an existing built/installed package")
    args = parser.parse_args()

    root = args.repo_root.expanduser().absolute()
    manifest = args.manifest.expanduser().absolute() if args.manifest else None
    try:
        if args.verify:
            plan = verify_package(args.verify.expanduser())
            reviewed_plan = package_plan(root, manifest)
            if plan != reviewed_plan:
                raise PackageError("verified package does not match the reviewed source lock")
            _print_plan(plan, "Verified runtime package")
        elif args.output:
            plan = build_package(root, args.output, manifest)
            _print_plan(plan, f"Built runtime package at {args.output.expanduser().absolute()}")
        elif args.calculate_lock:
            plan = package_plan(root, manifest, enforce_lock=False)
            print(f'"locked_payload_size_bytes": {plan["payload_size_bytes"]},')
            print(f'"locked_tree_sha256": "{plan["tree_sha256"]}"')
        else:
            plan = package_plan(root, manifest)
            _print_plan(plan, "Runtime package dry run")
        return 0
    except PackageError as exc:
        print(f"Runtime package error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
