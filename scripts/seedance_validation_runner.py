from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.seedance_validation_core import validate_skill


def run_validation(
    root: Path,
    *,
    expected_skills: list[str],
    expected_version: str,
    required_files: list[str],
    required_references: list[str],
    strict: bool,
) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    for rel in required_files + required_references:
        if not (root / rel).exists():
            errors.append(f"missing required file: {rel}")

    skill_root = root / "skills"
    dirs = sorted(path.name for path in skill_root.glob("seedance-*") if path.is_dir())
    missing = sorted(set(expected_skills) - set(dirs))
    extra = sorted(set(dirs) - set(expected_skills))
    if missing:
        errors.append("missing expected skill dirs: " + ", ".join(missing))
    if extra:
        warnings.append("extra skill dirs: " + ", ".join(extra))

    validate_skill(root / "SKILL.md", root, expected_version, errors, warnings)
    for name in expected_skills:
        path = root / "skills" / name / "SKILL.md"
        if path.exists():
            validate_skill(path, root, expected_version, errors, warnings)

    _validate_caches(root, errors)
    _validate_evals(root, errors)
    _validate_scripts(root, errors)
    _validate_installer(root, errors)
    _validate_openai_yaml(root, errors)
    _validate_disclosure(root, errors)

    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"- {warning}")
        print()
    if errors:
        print("ERRORS:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Validated root plus {len(expected_skills)} sub-skills and required v{expected_version} files.")
    return 0


def _validate_caches(root: Path, errors: list[str]) -> None:
    pycache = root / "scripts" / "__pycache__"
    if pycache.exists():
        errors.append("scripts/__pycache__ must not be committed")
    for pyc in root.rglob("*.pyc"):
        if ".seedance_backups" not in pyc.parts:
            errors.append(f"compiled Python cache must not be committed: {pyc.relative_to(root)}")


def _validate_evals(root: Path, errors: list[str]) -> None:
    path = root / "evals" / "evals.json"
    if not path.exists():
        return
    try:
        if len(json.loads(path.read_text(encoding="utf-8")).get("cases", [])) < 16:
            errors.append("evals/evals.json must contain at least 16 cases")
    except Exception as exc:
        errors.append(f"evals/evals.json parse error: {exc}")


def _validate_scripts(root: Path, errors: list[str]) -> None:
    names = (
        "validate_skills.py",
        "content_audit.py",
        "eval_schema_check.py",
        "design_audit.py",
        "install_codex_skill.py",
        "source_registry_check.py",
        "vocab_schema_check.py",
        "prompt_lint.py",
        "project_state_check.py",
        "continuity_chain_check.py",
        "behavior_contract_check.py",
        "sequence_eval_check.py",
        "generation_run_check.py",
        "extract_last_frame.py",
    )
    for name in names:
        path = root / "scripts" / name
        if path.exists() and len(path.read_text(encoding="utf-8").splitlines()) < 20:
            errors.append(f"scripts/{name}: script appears collapsed or incomplete")


def _validate_installer(root: Path, errors: list[str]) -> None:
    path = root / "scripts" / "install_codex_skill.py"
    if path.exists() and re.search(
        r"IGNORE_NAMES\s*=\s*{[^}]*[\"']docs[\"']",
        path.read_text(encoding="utf-8"),
        re.S,
    ):
        errors.append("scripts/install_codex_skill.py must include docs/")


def _validate_openai_yaml(root: Path, errors: list[str]) -> None:
    path = root / "agents" / "openai.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    required = (
        'display_name: "Seedance Expert"',
        'short_description: "Direct and generate Seedance 2.0 videos"',
        'default_prompt: "Use $seedance-expert',
        "allow_implicit_invocation: true",
    )
    for snippet in required:
        if snippet not in text:
            errors.append(f"agents/openai.yaml missing `{snippet}`")


def _validate_disclosure(root: Path, errors: list[str]) -> None:
    path = root / "references" / "progressive-disclosure.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for needed in ("directing-engine.md", "directing-engine-genre-library.md"):
        if needed not in text:
            errors.append(f"progressive-disclosure.md must document the heavy reference {needed}")
