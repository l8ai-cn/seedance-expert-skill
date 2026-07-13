#!/usr/bin/env python3
"""Reject unsupported positive claims about hidden model mechanics.

This is a narrow wording audit, not a semantic classifier.  It scans active
skill guidance and public evaluation oracles for a closed set of claims that
must not be presented as established Seedance internals.  Diagnostics expose
only a stable rule ID and repository-relative line location; matched text is
never echoed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


MAX_TEXT_BYTES = 4 * 1024 * 1024
ACTIVE_ROOT_FILES = {"README.md", "SKILL.md"}
ACTIVE_PREFIXES = ("skills/", "references/")
ACTIVE_EVAL_FILES = {"evals/evals.json"}
EXCLUDED_PREFIXES = ("references/migrated/",)


@dataclass(frozen=True)
class Rule:
    code: str
    pattern: re.Pattern[str]


def _rx(expression: str) -> re.Pattern[str]:
    return re.compile(expression, re.IGNORECASE | re.DOTALL)


CLAUSE_GAP = r"[^.!?;\u3002\uff01\uff1f\uff1b]{0,512}?"
SHORT_CLAUSE_GAP = r"[^.!?;\u3002\uff01\uff1f\uff1b]{0,96}?"


RULES = (
    Rule(
        "MECH001_PHYSICS_INTERNAL_CLAIM",
        _rx(
            rf"\b(?:seedance|the\s+model|the\s+generator|video\s+model)\b{CLAUSE_GAP}"
            rf"\b(?:understands?|simulates?|computes?|reasons?\s+about|has|uses|possesses?)\b{SHORT_CLAUSE_GAP}"
            r"\b(?:physics|physical\s+laws?|physics\s+engine|world\s+model)\b"
        ),
    ),
    Rule(
        "MECH002_ARCHITECTURE_CLAIM",
        _rx(
            rf"\b(?:seedance|the\s+model|the\s+generator|video\s+model)\b{CLAUSE_GAP}"
            rf"\b(?:uses|has|possesses?|relies\s+on|allocates?|routes?|processes?)\b{SHORT_CLAUSE_GAP}"
            r"\b(?:attention\s+budget|text\s+encoder|latent\s+space|denois(?:ing|er)|"
            r"diffusion\s+process|joint\s+audio[- ]video\s+architecture|trajectory\s+prior)\b"
        ),
    ),
    Rule(
        "MECH003_TRAINING_DISTRIBUTION_CAUSE",
        _rx(
            r"\b(?:training[- ]distribution\s+rarity|distribution[- ]rare|"
            r"caused\s+by\s+(?:the\s+)?training\s+(?:data|distribution)|"
            r"because\s+of\s+(?:the\s+)?training\s+(?:data|distribution))\b"
        ),
    ),
    Rule(
        "MECH004_TRAJECTORY_INTERNAL_CLAIM",
        _rx(r"\b(?:trajectory\s+(?:conflict|prior)|mechanism[- ]aligned\s+staging)\b"),
    ),
    Rule(
        "MECH005_SAMPLING_CAUSE_ASSERTED",
        _rx(
            r"\b(?:sample\s+was\s+unlucky|unlucky\s+sample|pure\s+re[- ]?roll|"
            r"sampling\s+variance)\b"
        ),
    ),
    Rule(
        "MECH006_SEED_DETERMINISM_ASSERTED",
        _rx(
            rf"\b(?:same\s+seed|fixed\s+seed){SHORT_CLAUSE_GAP}"
            r"\b(?:controlled\s+experiment|pure\s+control|isolates?\s+the\s+prompt|"
            r"guarantees?\s+(?:the\s+)?same)\b"
        ),
    ),
    Rule(
        "MECH007_REPEAT_PROVES_CAUSE",
        _rx(
            r"\b(?:two|three|2|3)(?:\s+or\s+(?:three|3))?\s+"
            r"(?:re[- ]?rolls?|retries|takes?).{0,64}\b(?:by\s+definition|proves?|must\s+be)\b"
            r"|\b(?:the\s+prompt|prompt\s+is).{0,32}\b(?:by\s+definition|proven)\b"
        ),
    ),
    Rule(
        "MECH008_CHAIN_DEPTH_PHYSICS_ASSERTED",
        _rx(
            rf"\b(?:extension|chain)\s+depth\s+(?:of\s+)?\d+{SHORT_CLAUSE_GAP}"
            rf"\b(?:guarantees?|proves?|causes?|amplifies?)\b{SHORT_CLAUSE_GAP}\b(?:drift|failure|degradation)\b"
        ),
    ),
    Rule(
        "MECH009_CHAIN_IDENTITY_DECAY_ASSERTED",
        _rx(
            rf"\bidentity\b{SHORT_CLAUSE_GAP}\b(?:decays?|degrades?|deteriorates?)\b"
            rf"{SHORT_CLAUSE_GAP}\b(?:output[- ]sourced|continuation|extension|chained?)\s+(?:clips?|chains?|generations?|passes?)\b"
            r"|"
            rf"\b(?:output[- ]sourced|continuation|extension|chained?)\s+(?:clips?|chains?|generations?|passes?)\b"
            rf"{SHORT_CLAUSE_GAP}\bidentity\b{SHORT_CLAUSE_GAP}\b(?:decays?|degrades?|deteriorates?)\b"
        ),
    ),
    Rule(
        "MECH010_FINITE_FIDELITY_BUDGET_ASSERTED",
        _rx(r"\b(?:finite|limited|fixed)\s+fidelity\s+budget\b"),
    ),
    Rule(
        "MECH011_ZH_PHYSICS_INTERNAL_CLAIM",
        _rx(
            r"(?:seedance|(?:该|此|这个)?模型|(?:该|此|这个)?生成器)"
            r"[^。！？；]{0,128}?"
            r"(?:内置|拥有|具备|使用|依赖|理解|模拟|推理)"
            r"[^。！？；]{0,64}?"
            r"(?:物理引擎|物理规律|真实(?:世界)?物理|世界模型)"
        ),
    ),
    Rule(
        "MECH012_ZH_ATTENTION_BUDGET_CLAIM",
        _rx(
            r"(?:seedance|(?:该|此|这个)?模型|(?:该|此|这个)?生成器)"
            r"[^。！？；]{0,128}?"
            r"(?:分配|使用|拥有|具备|依赖)"
            r"[^。！？；]{0,64}?注意力预算"
        ),
    ),
)


CLAUSE_BOUNDARY = re.compile(r"[.!?;\u3002\uff01\uff1f\uff1b]")
DIRECT_NEGATION = _rx(
    r"\b(?:do|does|did|is|are|was|were|may|might|can|could|would|should|has|have|had)\s+not"
    r"(?:\s+\w+){0,4}\s+(?:understand|simulate|compute|reason|have|use|possess|rely|allocate|route|process|"
    r"make|constitute|isolate|guarantee|prove|cause|amplify|decay|degrade|deteriorate)\w*\b"
    r"|\b(?:cannot|can't|never)(?:\s+\w+){0,4}\s+"
    r"(?:understand|simulate|compute|reason|have|use|possess|rely|allocate|route|process|"
    r"make|constitute|isolate|guarantee|prove|cause|amplify|decay|degrade|deteriorate)\w*\b"
    r"|\b(?:doesn't|isn't|aren't|wasn't|weren't|couldn't|wouldn't|shouldn't|hasn't|haven't|hadn't)"
    r"(?:\s+\w+){0,4}\s+(?:understand|simulate|compute|reason|have|use|possess|rely|allocate|route|process|"
    r"make|constitute|isolate|guarantee|prove|cause|amplify|decay|degrade|deteriorate)\w*\b"
    r"|\b(?:same\s+seed|fixed\s+seed)[^.!?;]{0,48}\bisn't\s+(?:an?\s+)?controlled\s+experiment\b"
    r"|\b(?:has|have)\s+no(?:\s+\w+){0,4}\s+(?:physics|world\s+model|attention\s+budget)\b"
    r"|\bnot\s+(?:an?\s+)?(?:finite|limited|fixed)\s+fidelity\s+budget\b"
    r"|(?:并不|并非|不|未|没有|不能|无法)[^。！？；]{0,12}?"
    r"(?:内置|拥有|具备|使用|依赖|理解|模拟|推理|分配|证明|表明)"
)
CLAIM_NEGATION_PREFIX = _rx(
    r"(?:\b(?:do\s+not|does\s+not|must\s+not|cannot|can't|never)\s+"
    r"(?:claim|infer|attribute|describe|present|treat|assume|assert|say)\b"
    r"|\b(?:retained\s+|public\s+)?evidence\s+(?:does\s+not|cannot|can't)\s+"
    r"(?:establish|show|prove|reveal|support)\b"
    r"|\bno\s+(?:public\s+|retained\s+)?evidence\b"
    r"|(?:不要|不得|不可|不能)[^。！？；]{0,12}?(?:声称|推断|归因|描述|认定)"
    r"|(?:没有|缺乏)[^。！？；]{0,12}?证据[^。！？；]{0,12}?(?:证明|表明|支持))"
)


def _comparison_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    visible = "".join(character for character in normalized if not _default_ignorable(character))
    return " ".join(visible.split())


def _default_ignorable(character: str) -> bool:
    """Return whether a Unicode code point is unsafe to ignore in comparison."""

    codepoint = ord(character)
    if unicodedata.category(character) == "Cf":
        return True
    return (
        codepoint == 0x034F
        or 0x115F <= codepoint <= 0x1160
        or 0x17B4 <= codepoint <= 0x17B5
        or 0x180B <= codepoint <= 0x180F
        or 0x3164 == codepoint
        or 0xFE00 <= codepoint <= 0xFE0F
        or codepoint == 0xFFA0
        or 0x1BCA0 <= codepoint <= 0x1BCA3
        or 0x1D173 <= codepoint <= 0x1D17A
        or 0xE0000 <= codepoint <= 0xE0FFF
    )


def _guidance_units(text: str) -> list[tuple[int, str]]:
    """Join wrapped prose lines while preserving the paragraph's first line."""

    units: list[tuple[int, str]] = []
    start = 0
    lines: list[str] = []

    def flush() -> None:
        nonlocal start, lines
        if lines:
            units.append((start, " ".join(line.strip() for line in lines)))
        start = 0
        lines = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        isolated = bool(re.match(r"^(?:#{1,6}\s|\||```|~~~)", stripped))
        if isolated:
            flush()
            units.append((line_number, stripped))
            continue
        list_item = bool(re.match(r"^(?:[-+*]\s|\d+[.)]\s)", stripped))
        if list_item:
            flush()
            start = line_number
            lines.append(stripped)
            continue
        if not lines:
            start = line_number
        lines.append(stripped)
    flush()
    return units


def _clause_for_match(text: str, match: re.Match[str]) -> tuple[str, int]:
    """Return the containing clause and the match offset inside that clause."""

    left = 0
    for boundary in CLAUSE_BOUNDARY.finditer(text, 0, match.start()):
        left = boundary.end()
    boundary = CLAUSE_BOUNDARY.search(text, match.end())
    right = boundary.start() if boundary else len(text)
    return text[left:right], match.start() - left


def _match_is_negated(text: str, match: re.Match[str], rule_code: str) -> bool:
    """Allow only negation that governs the matched claim in its own clause."""

    clause, offset = _clause_for_match(text, match)
    local_match = clause[offset : offset + len(match.group(0))]
    if DIRECT_NEGATION.search(local_match):
        return True
    prefix = clause[:offset]
    boundaries = list(CLAIM_NEGATION_PREFIX.finditer(prefix))
    if not boundaries:
        return False
    boundary = boundaries[-1]
    bridge = prefix[boundary.end() :]
    if rule_code in {
        "MECH003_TRAINING_DISTRIBUTION_CAUSE",
        "MECH004_TRAJECTORY_INTERNAL_CLAIM",
        "MECH005_SAMPLING_CAUSE_ASSERTED",
    } and not re.search(r"\b(?:but|however|yet)\b|(?:但|然而|可是|不过)", bridge, re.IGNORECASE):
        return True
    return re.fullmatch(
        r"\s*(?:(?:that|whether|how|shows?|establishes?|proves?|reveals?|supports?)\s+)*",
        bridge,
        re.IGNORECASE,
    ) is not None


def _active_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in sorted(ACTIVE_ROOT_FILES):
        path = root / name
        if path.exists():
            paths.append(path)
    for prefix in ACTIVE_PREFIXES:
        directory = root / prefix.rstrip("/")
        if not directory.exists():
            continue
        paths.extend(sorted(directory.rglob("*.md")))
    for relative in sorted(ACTIVE_EVAL_FILES):
        path = root / relative
        if path.exists():
            paths.append(path)
    unique: dict[str, Path] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        unique[relative] = path
    return [unique[key] for key in sorted(unique)]


def _safe_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("MECH_FILE_NOT_REGULAR")
    raw = path.read_bytes()
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("MECH_FILE_TOO_LARGE")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("MECH_FILE_NOT_UTF8") from exc


def _oracle_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_oracle_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for key in sorted(value):
            if key in {"id", "prompt", "state_fixture", "asset_paths"}:
                continue
            result.extend(_oracle_strings(value[key]))
        return result
    return []


def _audit_units(relative: str, text: str) -> list[tuple[int, str]]:
    """Return trusted guidance or oracle units, excluding eval user prompts."""

    if relative not in ACTIVE_EVAL_FILES:
        return _guidance_units(text)
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        return [(0, "MECH_EVAL_JSON_INVALID")]
    cases = value.get("cases") if isinstance(value, dict) else None
    if not isinstance(cases, list):
        return [(0, "MECH_EVAL_JSON_INVALID")]
    units: list[tuple[int, str]] = []
    for ordinal, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            units.append((ordinal, "MECH_EVAL_JSON_INVALID"))
            continue
        for item in _oracle_strings(case):
            units.append((ordinal, item))
    return units


def audit_paths(root: Path, paths: list[Path] | None = None) -> list[tuple[str, int, str]]:
    """Return sorted ``(relative path, line, rule ID)`` findings."""

    root = root.resolve()
    findings: list[tuple[str, int, str]] = []
    for path in paths if paths is not None else _active_paths(root):
        absolute = path.absolute()
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError:
            findings.append(("<outside-root>", 0, "MECH_FILE_OUTSIDE_ROOT"))
            continue
        try:
            text = _safe_text(absolute)
        except ValueError as exc:
            findings.append((relative, 0, str(exc)))
            continue
        for line_number, raw_line in _audit_units(relative, text):
            if raw_line == "MECH_EVAL_JSON_INVALID":
                findings.append((relative, line_number, raw_line))
                continue
            line = _comparison_text(raw_line)
            for rule in RULES:
                for match in rule.pattern.finditer(line):
                    if not _match_is_negated(line, match, rule.code):
                        findings.append((relative, line_number, rule.code))
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit active guidance and public evals for unsupported hidden-mechanics claims."
    )
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    findings = audit_paths(root)
    if findings:
        print("Mechanics claim audit findings:")
        for relative, line_number, code in findings:
            print(f"- {relative}:{line_number}: {code}")
        return 1
    print("Mechanics claim audit passed: no matches for the bounded prohibited-claim rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
