#!/usr/bin/env python3
"""Compatibility entry point for the canonical claim-level evidence gate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the canonical claim-level evidence registry."
    )
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    sys.path.insert(0, str(root))
    try:
        from tools.evidence_registry import evaluate, layout_for_root
    except ModuleNotFoundError as exc:
        if exc.name == "jsonschema":
            print("missing dependency: install requirements-validation.lock")
            return 2
        raise

    report, errors, warnings = evaluate(
        layout_for_root(root),
        enforce_freshness=True,
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        print("Evidence registry errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Evidence registry passed structural and freshness validation: "
        f"{report['claim_count']} claims; release_gate_pass="
        f"{str(report['release_gate_pass']).lower()}."
    )
    if report["release_blockers"]:
        print(
            "Release remains intentionally blocked; run "
            "`python tools/evidence_registry.py --release` for blocker details."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
