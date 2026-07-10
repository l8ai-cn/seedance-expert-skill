#!/usr/bin/env python3
"""Explicit, blind, auditable model-in-the-loop evaluation harness."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import eval_harness
import eval_harness.core as harness_core
import eval_harness.providers as harness_providers
from eval_harness.core import (
    HarnessError,
    RunBundle,
    RuntimeResources,
    aggregate,
    canonical_json,
    default_run_id,
    execute_case,
    load_suite,
    repository_provenance,
    recover_incomplete,
    run_metadata,
    sha256_bytes,
    split_case,
    utc_now,
    verify_bundle,
)
from eval_harness.providers import anthropic_completion


def root_from(value: str) -> Path:
    return Path(value).expanduser().resolve()


def suite_path(root: Path, name: str) -> Path:
    return root / "evals" / "suites" / f"{name}.json"


def executed_harness_sources() -> list[dict[str, object]]:
    paths = [
        ("executed:eval_harness/__init__.py", Path(eval_harness.__file__).resolve()),
        ("executed:eval_harness/core.py", Path(harness_core.__file__).resolve()),
        ("executed:eval_harness/providers.py", Path(harness_providers.__file__).resolve()),
        ("executed:eval_run.py", Path(__file__).resolve()),
    ]
    return [
        {"path": label, "size": len(path.read_bytes()), "sha256": sha256_bytes(path.read_bytes())}
        for label, path in sorted(paths)
    ]


def self_test(root: Path) -> int:
    errors: list[str] = []
    try:
        development = load_suite(root, suite_path(root, "development"))
        live = load_suite(root, suite_path(root, "live"))
        resources = RuntimeResources(root)
        resources.validate_suite_resources(development)
        resources.validate_suite_resources(live)
        router_system, router_records = resources.router_system()
        root_text = (root / "SKILL.md").read_text(encoding="utf-8")
        if root_text not in router_system or "...[truncated]" in router_system:
            errors.append("router does not contain the complete root skill")
        if len(router_records) != len(resources.catalog) + len(resources.reference_catalog) + 1:
            errors.append("router resource manifest is incomplete")
        synthetic = {
            "id": "blindness-sentinel",
            "prompt": "Return one concise prompt.",
            "assertions": ["ORACLE_ASSERTION_SENTINEL"],
            "expected_output": "ORACLE_OUTPUT_SENTINEL",
            "failure_mode": "ORACLE_FAILURE_SENTINEL",
            "skills_expected_to_activate": ["ORACLE_ROUTE_SENTINEL"],
        }
        case_input, oracle = split_case(synthetic)
        projected = canonical_json(case_input)
        for value in oracle.values():
            for sentinel in value if isinstance(value, list) else [value]:
                if isinstance(sentinel, str) and sentinel.encode("utf-8") in projected:
                    errors.append("oracle value leaked into responder input projection")
        empty = aggregate([], development)
        if empty["passed"] or empty["release_pass"]:
            errors.append("empty aggregate fails open")
        false_high = [{
            "case_id": case["id"], "status": "completed", "passed": False,
            "sequence": False, "score": 3,
        } for case in development["cases"]]
        if aggregate(false_high, development)["passed"]:
            errors.append("pass:false can be overridden by a high score")
        if development["release_eligible"] or live["release_eligible"]:
            errors.append("public suites must not be release eligible")
    except Exception as exc:
        errors.append(f"self-test exception: {type(exc).__name__}: {exc}")
    if errors:
        print("eval harness v2 self-test FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "eval harness v2 self-test passed: "
        f"{len(development['cases'])} development cases, {len(live['cases'])} live canaries, "
        f"{len(resources.catalog)} blind-route catalog entries; zero network calls."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind evaluation harness v2 for seedance-20.")
    parser.add_argument("repo", nargs="?", default=".")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--self-test", action="store_true", help="offline architecture check; never uses network")
    actions.add_argument("--run", action="store_true", help="explicitly run a networked responder/router/judge evaluation")
    actions.add_argument("--verify-bundle", type=Path, help="verify a completion-bound run bundle without network")
    actions.add_argument("--recover-incomplete", type=Path, help="mark a crashed reserved run directory as permanently incomplete")
    parser.add_argument("--suite", choices=["development", "live"], default="development")
    parser.add_argument("--suite-file", type=Path, help="reserved for a future protected runner; rejected by this public harness")
    parser.add_argument("--provider", choices=["anthropic"], default="anthropic")
    parser.add_argument("--responder-model")
    parser.add_argument("--judge-model")
    parser.add_argument("--id", action="append", help="development-only diagnostic case selection")
    parser.add_argument("--limit", type=int, default=0, help="development-only diagnostic cap")
    parser.add_argument("--attempt-index", type=int, default=1)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--acknowledge-network-egress", action="store_true")
    parser.add_argument("--allow-dirty-development", action="store_true")
    args = parser.parse_args()

    root = root_from(args.repo)
    if args.self_test:
        return self_test(root)
    if args.verify_bundle:
        try:
            record = verify_bundle(args.verify_bundle)
        except HarnessError as exc:
            print(f"Bundle verification FAILED: {exc}")
            return 1
        summary = record.get("summary", {}) if isinstance(record, dict) else {}
        print(f"Verified eval bundle: status={summary.get('status')} passed={summary.get('passed')} release_pass={summary.get('release_pass')}")
        return 0
    if args.recover_incomplete:
        try:
            recovered = recover_incomplete(args.recover_incomplete)
        except HarnessError as exc:
            print(f"Incomplete bundle recovery FAILED: {exc}")
            return 1
        print(f"Recovered incomplete eval evidence: {recovered}; passed=False release_pass=False")
        return 0

    try:
        if not args.acknowledge_network_egress:
            raise HarnessError("--run requires --acknowledge-network-egress")
        if not args.responder_model or not args.judge_model:
            raise HarnessError("--run requires explicit --responder-model and --judge-model")
        if args.responder_model == args.judge_model:
            raise HarnessError("responder and judge model IDs must be distinct")
        if type(args.attempt_index) is not int or args.attempt_index < 1:
            raise HarnessError("attempt-index must be an integer >= 1")
        if args.output_root is None:
            raise HarnessError("--run requires --output-root; raw evidence is never written into the repository by default")
        if args.suite_file is not None:
            raise HarnessError(
                "external/held-out execution is disabled in the shipped V7-03 CLI; "
                "the protected runner and private-corpus boundary are not operational"
            )
        try:
            args.output_root.expanduser().absolute().resolve().relative_to(root)
        except ValueError:
            pass
        else:
            raise HarnessError("raw eval bundles must be stored outside the candidate repository")
        manifest = args.suite_file or suite_path(root, args.suite)
        suite = load_suite(root, manifest, requested_ids=args.id, limit=args.limit)
        kind = suite["manifest"]["kind"]
        if kind == "held_out":
            raise HarnessError("held-out execution is not implemented by this public harness")
        resources = RuntimeResources(root)
        resources.validate_suite_resources(suite)
        provenance = repository_provenance(root)
        if not provenance["clean"] and not (kind == "development" and args.allow_dirty_development):
            raise HarnessError("networked evaluation requires a clean Git tree (dirty runs are development-only and explicit)")
        if not provenance["clean"]:
            suite["release_eligible"] = False
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HarnessError("ANTHROPIC_API_KEY is not set")
        rubric_path = root / "references" / "eval-rubric.md"
        rubric = rubric_path.read_text(encoding="utf-8")
        run_id = args.run_id or default_run_id(suite["manifest"]["suite_id"], provenance["commit_sha"], args.attempt_index)
        metadata = run_metadata(suite, provenance, args.responder_model, args.judge_model, args.attempt_index, run_id)
        metadata["rubric"] = {"path": "references/eval-rubric.md", "sha256": sha256_bytes(rubric.encode("utf-8"))}
        metadata["runtime_tree_sha256"] = resources.tree_sha256
        metadata["harness_sources"] = executed_harness_sources()
        metadata["configuration_sha256"] = sha256_bytes(canonical_json({
            "provider": args.provider,
            "responder_model": args.responder_model,
            "judge_model": args.judge_model,
            "attempt_index": args.attempt_index,
            "suite_manifest_sha256": suite["manifest_sha256"],
            "case_pack_sha256": suite["case_sha256"],
        }))
        metadata["egress_acknowledged"] = True
        provider_factories = {"anthropic": anthropic_completion}
        completion = provider_factories[args.provider](api_key)
        bundle = RunBundle(args.output_root, run_id)
        records = []
        try:
            total = len(suite["cases"])
            for index, case in enumerate(suite["cases"], 1):
                def checkpoint(stage: str, partial: dict, *, ordinal: int = index) -> None:
                    bundle.write_json(f"checkpoints/{ordinal:04d}-{stage}.json", partial)

                record = execute_case(
                    root, resources, case, rubric, args.responder_model, args.judge_model,
                    completion, args.attempt_index,
                    checkpoint=checkpoint,
                )
                records.append(record)
                bundle.write_json(f"cases/{index:04d}.json", record)
                label = case["id"] if kind != "held_out" else f"sealed-case-{index}"
                print(f"[{index}/{total}] {label}: {record['status']} {'PASS' if record['passed'] else 'FAIL'}")
            summary = aggregate(records, suite)
            metadata["cases"] = [
                {
                    "ordinal": index,
                    "case_record_sha256": sha256_bytes(canonical_json(record)),
                    "status": record["status"],
                    "passed": record["passed"],
                }
                for index, record in enumerate(records, 1)
            ]
            metadata["summary"] = summary
            metadata["finished_at"] = utc_now()
            bundle.write_json("public-summary.json", {
                "schema_version": 2,
                "run_id": run_id,
                "suite_kind": kind,
                "case_count": summary["case_count"],
                "status": summary["status"],
                "passed": summary["passed"],
                "release_pass": summary["release_pass"],
                "failed_case_count": len(summary.get("failed_case_ids", [])),
                "commit_sha": provenance["commit_sha"],
                "runtime_tree_sha256": resources.tree_sha256,
            })
            final = bundle.finish(metadata)
        except Exception:
            bundle.abort()
            raise
        print(f"Run bundle: {final}")
        print(f"RESULT: {'PASS' if summary['passed'] else 'FAIL'}; RELEASE_PASS: {summary['release_pass']}")
        return 0 if summary["passed"] else 1
    except HarnessError as exc:
        print(f"Eval harness error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
