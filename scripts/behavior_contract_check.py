#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_SNIPPETS = {
    "SKILL.md": [
        "## Sequence Gate",
        "[skill:seedance-sequence]",
        "[skill:seedance-continuation]",
        "accepted observed state overrides planned state",
        "rejected footage",
        "evidence-pinned surface ordinal",
    ],
    "skills/seedance-sequence/SKILL.md": [
        "Plan globally",
        "final outcome",
        "provisional intent cards",
        "Clip 01 surface-rendered prompt",
    ],
    "skills/seedance-continuation/SKILL.md": [
        "Required Input Gate",
        "accepted previous clip or accepted final frame",
        "observed_end_state",
        "Do not hide this uncertainty",
    ],
    "references/prompt-compiler.md": [
        "typed natural-language segments",
        "Do not emit internal JSON",
        "Do not replay completed actions",
        "Do not perform reserved later actions",
    ],
    "references/surface-prompt-profiles.md": [
        "Two Independent Axes",
        "Unknown profiles and operations fail closed",
        "Never trim, normalize, translate, recase, renumber, repair spacing, or add an `@` prefix",
        "activation_enabled: false",
    ],
    "scripts/render_surface_bindings.py": [
        "ACTIVATION_SUPPORTED = False",
        "PROFILE_CANDIDATE_REQUIRES_PREVIEW",
        "PROFILE_EVIDENCE_EXPIRED",
        "STRUCTURED_BINDING_IN_PROMPT",
        "REFERENCE_TOKEN_IN_TEXT_FORBIDDEN",
    ],
    "scripts/semantic_lint.py": [
        "PRM022_MULTI_SHOT_DEFERRED",
        "PRM021_DIALOGUE_TEXT_REQUIRED",
        "PARITY001_SEMANTIC_TRACE_MISMATCH",
        "reviewer_attested",
    ],
    "scripts/prompt_compile.py": [
        "PROFILE_CANDIDATE_REQUIRES_PREVIEW",
        "REF001_BINDING_ORDER_MISMATCH",
        "linguistic_equivalence",
        "prompt_program_sha256",
    ],
}


DOMAIN_FILES = [
    "skills/seedance-camera/SKILL.md",
    "skills/seedance-motion/SKILL.md",
    "skills/seedance-characters/SKILL.md",
    "skills/seedance-audio/SKILL.md",
    "skills/seedance-lighting/SKILL.md",
    "skills/seedance-style/SKILL.md",
    "skills/seedance-recipes/SKILL.md",
    "skills/seedance-prompt-short/SKILL.md",
    "skills/seedance-troubleshoot/SKILL.md",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    errors: list[str] = []

    for rel, snippets in REQUIRED_SNIPPETS.items():
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        for snippet in snippets:
            if snippet.lower() not in low:
                errors.append(f"{rel}: missing behavior phrase `{snippet}`")

    for rel in DOMAIN_FILES:
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "sequence state" not in text or "reserved" not in text or "continuity locks" not in text:
            errors.append(f"{rel}: must read sequence state, continuity locks, and reserved beats when present")

    if errors:
        print("Behavior contract errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Behavior contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
