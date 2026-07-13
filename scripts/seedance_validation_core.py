from __future__ import annotations

import re
from pathlib import Path


ROOT_REQUIRED_FIELDS = ["name", "description", "license", "metadata"]
SUBSKILL_REQUIRED_FIELDS = [
    "name",
    "description",
    "license",
    "user-invocable",
    "tags",
    "metadata",
]


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter must start with a standalone --- line")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter must end with a standalone --- line") from exc
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])


def top_keys(frontmatter: str) -> list[str]:
    return [
        line.split(":", 1)[0].strip()
        for line in frontmatter.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith(" ") and ":" in line
    ]


def value_for(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.*)$", frontmatter, re.MULTILINE)
    return _unquote(match.group(1).strip()) if match else None


def metadata_value(frontmatter: str, key: str) -> str | None:
    in_metadata = False
    for line in frontmatter.splitlines():
        if line.startswith("metadata:"):
            in_metadata = True
            continue
        if in_metadata and line and not line.startswith(" "):
            break
        if in_metadata:
            match = re.match(rf"^\s+{re.escape(key)}:\s*(.*)$", line)
            if match:
                return _unquote(match.group(1).strip())
    return None


def validate_skill(
    path: Path,
    root: Path,
    expected_version: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    rel = path.relative_to(root).as_posix()
    try:
        frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{rel}: {exc}")
        return

    is_root = path == root / "SKILL.md"
    required_fields = ROOT_REQUIRED_FIELDS if is_root else SUBSKILL_REQUIRED_FIELDS
    keys = top_keys(frontmatter)
    for field in required_fields:
        if field not in keys:
            errors.append(f"{rel}: missing top-level field `{field}`")
    if "parent" in keys:
        errors.append(f"{rel}: illegal top-level `parent`; use metadata.parent")

    name = value_for(frontmatter, "name")
    if not is_root and path.parent.name.startswith("seedance-") and name != path.parent.name:
        errors.append(f"{rel}: name `{name}` does not match folder `{path.parent.name}`")
    if not is_root and metadata_value(frontmatter, "parent") != "seedance-expert":
        errors.append(f"{rel}: missing metadata.parent: seedance-expert")
    if metadata_value(frontmatter, "version") != expected_version:
        errors.append(f"{rel}: metadata.version must be {expected_version}")
    if not is_root and "## Intent" not in body:
        errors.append(f"{rel}: sub-skill missing a `## Intent` section")
    if not (value_for(frontmatter, "description") or "").startswith("This skill should be used when"):
        errors.append(f"{rel}: description must use third-person activation wording")
    if len(body.strip()) < 200:
        warnings.append(f"{rel}: body is very short")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
        return value[1:-1]
    return value
