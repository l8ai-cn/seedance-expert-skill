from __future__ import annotations

from pathlib import Path


LEGACY_MIN, LEGACY_AVG = 2, 2.6
SEQUENCE_CRIT, SEQUENCE_AVG, SEQUENCE_FLOOR = 4, 3.5, 3


def aggregate(scored: list[dict]) -> int:
    legacy = [item for item in scored if not item["sequence"]]
    sequence = [item for item in scored if item["sequence"]]
    ok = True
    if legacy:
        average = sum(item["score"] for item in legacy) / len(legacy)
        below = [item["id"] for item in legacy if item["score"] < LEGACY_MIN]
        print(
            f"\nLegacy (0-3): {len(legacy)} cases, avg {average:.2f} "
            f"(need >= {LEGACY_AVG}); {len(below)} below {LEGACY_MIN}"
        )
        if average < LEGACY_AVG or below:
            ok = False
            if below:
                print("  below floor:", ", ".join(below))
    if sequence:
        average = sum(item["score"] for item in sequence) / len(sequence)
        critical_failures = [
            item["id"]
            for item in sequence
            if item.get("critical") and item["score"] < SEQUENCE_CRIT
        ]
        floor_failures = [
            item["id"] for item in sequence if item["score"] < SEQUENCE_FLOOR
        ]
        print(
            f"Sequence (0-4): {len(sequence)} cases, avg {average:.2f} "
            f"(need >= {SEQUENCE_AVG}); {len(critical_failures)} critical below "
            f"{SEQUENCE_CRIT}; {len(floor_failures)} below floor {SEQUENCE_FLOOR}"
        )
        if average < SEQUENCE_AVG or critical_failures or floor_failures:
            ok = False
            if critical_failures:
                print("  critical not at 4:", ", ".join(critical_failures))
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def write_ledger(path: Path, scored: list[dict], model: str, stamp: str) -> None:
    lines = [
        "# Eval Run Ledger",
        "",
        f"Last scored: **{stamp}** with responder+judge model `{model}` via `scripts/eval_run.py`.",
        "This is the evidence layer for the rubric in `references/eval-rubric.md`; the deterministic",
        "CI validators check shape, this checks output quality. Regenerate with",
        "`python scripts/eval_run.py --run --ledger evals/eval-run-ledger.md`.",
        "",
        "| id | scale | score | pass | notes |",
        "|---|---|---|---|---|",
    ]
    for item in sorted(scored, key=lambda value: (value["sequence"], value["id"])):
        scale = "0-4" if item["sequence"] else "0-3"
        note = (item.get("notes") or "").replace("|", "/").replace("\n", " ")[:80]
        passed = "yes" if item["pass"] else "NO"
        lines.append(
            f"| {item['id']} | {scale} | {item['score']} | {passed} | {note} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nLedger written to {path}")
