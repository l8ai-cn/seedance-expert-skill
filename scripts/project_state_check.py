#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.project_state_rules import (
    REQUIRED_CLIP_CONTRACT_FIELDS,
    REQUIRED_TAKE_REVIEW_FIELDS,
    check_required,
    load_json,
    sequence_paths,
)
from scripts.project_state_validation import validate_project


def validate_examples(root: Path, errors: list[str]) -> None:
    if not (root / "examples").exists():
        return
    for path in sorted((root / "examples").rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        try:
            obj = load_json(path)
        except Exception as error:
            errors.append(f"{rel}: invalid JSON: {error}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{rel}: JSON example must be an object")
            continue
        if "contract" in path.name:
            check_required(obj, REQUIRED_CLIP_CONTRACT_FIELDS, rel, errors)
            felt_intent = obj.get("felt_intent")
            if "felt_intent" in obj and (
                not isinstance(felt_intent, str) or not felt_intent.strip()
            ):
                errors.append(
                    f"{rel}: felt_intent must be a non-empty one-line string"
                )
            if set(obj.get("this_clip_only", [])) & set(
                obj.get("reserved_for_later", [])
            ):
                errors.append(f"{rel}: current and reserved beats overlap")
        if "take-review" in path.name or path.name == "take-review.json":
            check_required(obj, REQUIRED_TAKE_REVIEW_FIELDS, rel, errors)
            if obj.get("verdict") == "reject" and obj.get("accepted_deviations"):
                errors.append(f"{rel}: rejected take must not accept deviations")


def validate_schemas(root: Path, errors: list[str]) -> None:
    if not (root / "schemas").exists():
        return
    for schema in (root / "schemas").glob("*.schema.json"):
        try:
            load_json(schema)
        except Exception as error:
            rel = schema.relative_to(root).as_posix()
            errors.append(f"{rel}: invalid JSON: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    errors: list[str] = []
    paths = sequence_paths(root)
    if not paths:
        errors.append("missing project-state examples")
    for path in paths:
        errors.extend(validate_project(path, root))
    validate_examples(root, errors)
    validate_schemas(root, errors)

    if errors:
        print("Project state errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Project state check passed: {len(paths)} project states.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
