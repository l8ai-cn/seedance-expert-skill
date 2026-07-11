#!/usr/bin/env python3
"""Execute repository JSON Schemas against their declared fixtures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError:  # pragma: no cover - exercised by the CLI dependency test
    Draft202012Validator = FormatChecker = None  # type: ignore[assignment,misc]
    SchemaError = Exception  # type: ignore[assignment,misc]


MANIFEST = Path("validation/schema-instances.json")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def parse_json(text: str) -> Any:
    if text.startswith("\ufeff"):
        raise ValueError("UTF-8 BOM is not permitted")
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    return value


def load_json(path: Path) -> Any:
    return parse_json(path.read_text(encoding="utf-8"))


def pointer(parts: Iterable[Any]) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


def reject_reference_keywords(value: Any, label: str) -> None:
    stack: list[tuple[str, Any]] = [("$", value)]
    while stack:
        location, current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                child = f"{location}/{key}"
                if key == "$ref" and (not isinstance(item, str) or not item.startswith("#")):
                    raise ValueError(f"{label}: non-local $ref is forbidden at {child}")
                if key in {"$dynamicRef", "$recursiveRef"}:
                    raise ValueError(f"{label}: reference-resolving keyword {key} is forbidden at {child}")
                stack.append((child, item))
        elif isinstance(current, list):
            stack.extend((f"{location}/{index}", item) for index, item in enumerate(current))


def safe_path(root: Path, value: object, label: str) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None, f"{label}: path must be a non-empty repository-relative POSIX path"
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, f"{label}: path escapes repository: {value!r}"
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, f"{label}: resolved path escapes repository: {value!r}"
    if not resolved.is_file():
        return None, f"{label}: missing file: {value}"
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            return None, f"{label}: symlink paths are not permitted: {value!r}"
    return resolved, None


def safe_manifest_path(root: Path, path: Path) -> tuple[Path | None, str | None]:
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, f"manifest path escapes repository or is missing: {path}"
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError:
        relative = None  # An aliased outer repository is allowed when it resolves to root.
    if relative is not None:
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return None, f"manifest path must not contain symlinks: {path}"
    if not resolved.is_file():
        return None, f"manifest path is not a regular file: {path}"
    return resolved, None


def iter_jsonl(path: Path) -> tuple[list[tuple[str, Any]], list[str]]:
    records: list[tuple[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append((f"{path.name}:{number}", parse_json(line)))
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{path.name}:{number}: invalid JSON: {exc}")
    if not records:
        errors.append(f"{path.name}: JSONL file contains no records")
    return records, errors


def validate_repository(root: Path, manifest_path: Path, strict: bool) -> tuple[list[str], list[str], int]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    if Draft202012Validator is None:
        return ["missing dependency: install requirements-validation.lock"], warnings, checked
    checked_manifest, manifest_error = safe_manifest_path(root, manifest_path)
    if manifest_error:
        return [manifest_error], warnings, checked
    assert checked_manifest is not None
    manifest_path = checked_manifest
    try:
        manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"{manifest_path}: cannot load manifest: {exc}"], warnings, checked
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return [f"{manifest_path}: schema_version must be integer 1"], warnings, checked
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        return [f"{manifest_path}: mappings must be a non-empty array"], warnings, checked

    declared: set[str] = set()
    for index, mapping in enumerate(mappings):
        label = f"manifest mapping {index}"
        if not isinstance(mapping, dict):
            errors.append(f"{label}: must be an object")
            continue
        allowed_keys = {"schema", "instances", "jsonl_instances", "strict_exemption"}
        extra_keys = sorted(set(mapping) - allowed_keys)
        if extra_keys:
            errors.append(f"{label}: unknown fields: {', '.join(extra_keys)}")
        schema_value = mapping.get("schema")
        schema_path, path_error = safe_path(root, schema_value, f"{label}.schema")
        if path_error:
            errors.append(path_error)
            continue
        assert schema_path is not None and isinstance(schema_value, str)
        if schema_value in declared:
            errors.append(f"{label}: duplicate schema mapping: {schema_value}")
            continue
        declared.add(schema_value)
        try:
            schema = load_json(schema_path)
            reject_reference_keywords(schema, schema_value)
            Draft202012Validator.check_schema(schema)
        except (OSError, json.JSONDecodeError, ValueError, SchemaError) as exc:
            errors.append(f"{schema_value}: invalid Draft 2020-12 schema: {exc}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{schema_value}: $schema must declare Draft 2020-12")
            continue
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        instance_count = 0
        for key, is_jsonl in (("instances", False), ("jsonl_instances", True)):
            values = mapping.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                errors.append(f"{label}.{key}: must be an array of paths")
                continue
            for value in values:
                instance_path, instance_error = safe_path(root, value, f"{label}.{key}")
                if instance_error:
                    errors.append(instance_error)
                    continue
                assert instance_path is not None
                if is_jsonl:
                    records, record_errors = iter_jsonl(instance_path)
                    errors.extend(f"{value}: {error}" for error in record_errors)
                else:
                    try:
                        records = [(value, load_json(instance_path))]
                    except (OSError, json.JSONDecodeError, ValueError) as exc:
                        errors.append(f"{value}: invalid JSON: {exc}")
                        continue
                for record_label, instance in records:
                    instance_count += 1
                    checked += 1
                    for error in sorted(
                        validator.iter_errors(instance),
                        key=lambda item: tuple(str(part) for part in item.absolute_path),
                    ):
                        errors.append(f"{record_label}{pointer(error.absolute_path)}: {error.message}")
        exemption = mapping.get("strict_exemption")
        if instance_count == 0:
            message = f"{schema_value}: no declared positive fixture"
            if isinstance(exemption, str) and exemption.strip():
                warnings.append(f"{message} ({exemption.strip()})")
            else:
                (errors if strict else warnings).append(message)

    schema_dir = root / "schemas"
    on_disk = {path.relative_to(root).as_posix() for path in schema_dir.glob("*.schema.json")}
    missing = sorted(on_disk - declared)
    if missing:
        message = "schemas missing from validation manifest: " + ", ".join(missing)
        (errors if strict else warnings).append(message)
    unknown = sorted(declared - on_disk)
    if unknown:
        errors.append("manifest declares non-canonical schemas: " + ", ".join(unknown))
    return errors, warnings, checked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--strict", action="store_true", help="fail schemas without fixtures and unmapped schemas")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    errors, warnings, checked = validate_repository(root, manifest_path, args.strict)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        print("Schema validation errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Schema validation passed: {len(load_json(manifest_path)['mappings'])} schemas, {checked} instances.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
