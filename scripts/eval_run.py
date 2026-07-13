#!/usr/bin/env python3
"""Model-in-the-loop eval harness for the seedance-expert skill.

The deterministic CI validators (eval_schema_check.py, sequence_eval_check.py, ...)
prove the eval suite is well-formed. They do not prove the skill actually produces
good output. This harness closes that gap: it runs each case prompt through the
real skill content (root SKILL.md plus the case's expected skills) to get a
response, then asks a judge model to score that response against the case's own
assertions using references/eval-rubric.md.

Two modes:
  --self-test   Offline. Validates wiring only - cases load, the rubric parses,
                every case's skills resolve, a responder context can be built,
                and assertions are non-empty. No network. Safe for CI.
  (default)     Live. Requires ANTHROPIC_API_KEY. Runs responder + judge for each
                case, prints per-case scores, aggregates against the rubric
                thresholds, and (with --ledger) writes a markdown score ledger.

Standard library only; honors HTTPS_PROXY and SSL_CERT_FILE from the environment.
This script is intentionally NOT part of the strict offline CI gate - run it
manually (or in a network-enabled job) when you want evidence, not just shape.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seedance_eval_reporting import aggregate, write_ledger
from scripts.seedance_eval_runtime import call_api, judge

DEFAULT_MODEL = "claude-sonnet-4-6"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_cases(root: Path) -> list[dict]:
    data = json.loads((root / "evals" / "evals.json").read_text(encoding="utf-8"))
    return data.get("cases", [])


def read_text(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def is_sequence_case(case: dict) -> bool:
    return "expected_sequence_relation" in case or case.get("critical") is True


def responder_context(root: Path, case: dict) -> str:
    parts = ["# Skill: seedance-expert (root router)", read_text(root / "SKILL.md")]
    for name in case.get("skills_expected_to_activate", []):
        if name == "seedance-expert":
            continue  # the root router is already included above
        body = read_text(root / "skills" / name / "SKILL.md", limit=8000)
        if body:
            parts.append(f"\n# Sub-skill: {name}\n{body}")
    fixture = case.get("state_fixture")
    if fixture and (root / fixture).exists():
        parts.append(f"\n# Project state fixture ({fixture})\n{read_text(root / fixture, limit=6000)}")
    return "\n\n".join(parts)


def self_test(root: Path) -> int:
    errors: list[str] = []
    cases = load_cases(root)
    if len(cases) < 16:
        errors.append("fewer than 16 cases")
    rubric = read_text(root / "references" / "eval-rubric.md")
    if "0 to 3" not in rubric or "0-4" not in rubric:
        errors.append("eval-rubric.md missing the 0-3 and 0-4 scales")
    seq = 0
    for case in cases:
        cid = case.get("id", "?")
        if not case.get("assertions"):
            errors.append(f"{cid}: no assertions")
        for name in case.get("skills_expected_to_activate", []):
            if name != "seedance-expert" and not (root / "skills" / name).is_dir():
                errors.append(f"{cid}: skill '{name}' does not resolve")
        if not responder_context(root, case).strip():
            errors.append(f"{cid}: empty responder context")
        if is_sequence_case(case):
            seq += 1
    if errors:
        print("eval_run self-test FAILED:")
        for e in errors[:40]:
            print(f"- {e}")
        return 1
    print(f"eval_run self-test passed: {len(cases)} cases wired, {seq} on the 0-4 sequence scale, rubric parsed, all skills resolve.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Model-in-the-loop eval harness for seedance-expert.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--self-test", action="store_true", help="offline wiring check, no network")
    parser.add_argument("--strict", action="store_true", help="accepted for parity with other validators")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="responder + judge model id")
    parser.add_argument("--judge-model", default=None, help="override judge model (defaults to --model)")
    parser.add_argument("--id", action="append", help="run only these case ids")
    parser.add_argument("--limit", type=int, default=0, help="cap number of cases (0 = all)")
    parser.add_argument("--ledger", default=None, help="write a markdown score ledger to this path")
    parser.add_argument("--stamp", default="unstamped", help="date label for the ledger (pass an ISO date)")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    if args.self_test:
        return self_test(root)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set. Use --self-test for an offline wiring check, "
              "or export a key to run a live scored pass.")
        return 2

    rubric = read_text(root / "references" / "eval-rubric.md")
    judge_model = args.judge_model or args.model
    cases = load_cases(root)
    if args.id:
        wanted = set(args.id)
        cases = [c for c in cases if c.get("id") in wanted]
    if args.limit:
        cases = cases[: args.limit]

    scored: list[dict] = []
    for case in cases:
        cid = case.get("id", "?")
        try:
            response = call_api(responder_context(root, case), case["prompt"], args.model, api_key)
            verdict = judge(
                case,
                response,
                judge_model,
                api_key,
                rubric,
                sequence=is_sequence_case(case),
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"[{cid}] API error: {exc}")
            verdict = {"overall_score": 0, "pass": False, "notes": f"api error: {exc}"}
        score = int(verdict.get("overall_score", 0) or 0)
        passed = bool(verdict.get("pass"))
        scored.append({"id": cid, "score": score, "pass": passed,
                       "sequence": is_sequence_case(case), "critical": case.get("critical"),
                       "notes": verdict.get("notes", "")})
        print(f"[{cid}] {'PASS' if passed else 'FAIL'} score={score} :: {str(verdict.get('notes',''))[:70]}")

    if args.ledger:
        write_ledger(Path(args.ledger), scored, args.model, args.stamp)
    return aggregate(scored)


if __name__ == "__main__":
    raise SystemExit(main())
