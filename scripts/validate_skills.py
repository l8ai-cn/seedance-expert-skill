#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seedance_validation_core import (
    ROOT_REQUIRED_FIELDS,
    SUBSKILL_REQUIRED_FIELDS,
)
from scripts.seedance_validation_runner import run_validation

EXPECTED_SKILLS = [
    "seedance-antislop", "seedance-audio", "seedance-camera", "seedance-characters", "seedance-continuation",
    "seedance-copyright", "seedance-examples-ja", "seedance-examples-ko", "seedance-examples-zh", "seedance-filter", "seedance-interview",
    "seedance-interview-short", "seedance-lighting", "seedance-motion", "seedance-pipeline",
    "seedance-prompt", "seedance-prompt-short", "seedance-recipes", "seedance-style",
    "seedance-sequence", "seedance-troubleshoot", "seedance-vfx", "seedance-vocab-en", "seedance-vocab-es", "seedance-vocab-ja",
    "seedance-vocab-ko", "seedance-vocab-ru", "seedance-vocab-zh",
]

EXPECTED_VERSION = "6.6.0"

REQUIRED_REFERENCES = [
    "references/api-status.md",
    "references/source-registry.md",
    "references/research-2026-05-30.md",
    "references/agent-compatibility.md",
    "references/api-workflow.md",
    "references/capability-map.md",
    "references/directing-engine.md",
    "references/directing-engine-genre-library.md",
    "references/model-mechanics.md",
    "references/retake-protocol.md",
    "references/allocation-model.md",
    "references/multishot-grammar.md",
    "references/2d-anime-grammar.md",
    "references/pro-filmmaking-standards.md",
    "references/cinematography-shot-language.md",
    "references/shot-list-continuity.md",
    "references/color-pipeline-aces.md",
    "references/aspect-ratio-delivery.md",
    "references/subtitles-localization.md",
    "references/audio-post-delivery.md",
    "references/delivery-qc.md",
    "references/examples-by-mode.md",
    "references/multilingual-community-examples.md",
    "references/platform-surface-matrix.md",
    "references/model-name-map.md",
    "references/first-last-frame-guide.md",
    "references/field-observed-tips.md",
    "references/community-source-methodology.md",
    "references/platform-constraints.md",
    "references/quick-ref.md",
    "references/audio-guide.md",
    "references/anti-slop-lexicon.md",
    "references/filter-vocab.md",
    "references/frontend-design-system.md",
    "references/json-schema.md",
    "references/reference-workflow.md",
    "references/i2v-guide.md",
    "references/genre-guides.md",
    "references/storytelling-framework.md",
    "references/intent-vs-precision.md",
    "references/eval-rubric.md",
    "references/progressive-disclosure.md",
    "references/prompt-examples.md",
    "references/sequence-project-state.md",
    "references/continuation-handoff.md",
    "references/prompt-compiler.md",
    "references/reference-transfer-contract.md",
    "references/dense-storyboard-mode.md",
    "references/surface-prompt-profiles.md",
    "references/event-density.md",
    "references/continuity-qc.md",
    "references/failure-atlas.md",
    "references/sequence-worked-trace.md",
    "references/vocab/en.md",
    "references/vocab/zh.md",
    "references/vocab/ja.md",
    "references/vocab/ko.md",
    "references/vocab/es.md",
    "references/vocab/ru.md",
]

REQUIRED_FILES = [
    "README.md",
    "SKILL.md",
    "CHANGELOG.md",
    "V6_SEQUENCE_PROMPT_COMPILER_MANIFEST.md",
    "scripts/validate_skills.py",
    "scripts/content_audit.py",
    "scripts/eval_schema_check.py",
    "scripts/eval_run.py",
    "scripts/design_audit.py",
    "scripts/install_codex_skill.py",
    "scripts/source_registry_check.py",
    "scripts/vocab_schema_check.py",
    "scripts/prompt_lint.py",
    "scripts/project_state_check.py",
    "scripts/continuity_chain_check.py",
    "scripts/behavior_contract_check.py",
    "scripts/sequence_eval_check.py",
    "scripts/generation_run_check.py",
    "scripts/extract_last_frame.py",
    ".github/workflows/validate-skills.yml",
    "agents/openai.yaml",
    "evals/evals.json",
    "evals/generation-benchmark.json",
    "data/sources.seedance-2026-05-30.json",
    "data/community-patterns.seedance-2026-05-30.json",
    "data/generation-runs.example.jsonl",
    "schemas/project-state.schema.json",
    "schemas/clip-contract.schema.json",
    "schemas/take-review.schema.json",
    "schemas/prompt-spec.schema.json",
    "schemas/generation-run.schema.json",
    "examples/sequence-airport-arrival/project-state.json",
    "examples/sequence-airport-arrival/sequence-plan.md",
    "examples/sequence-airport-arrival/clip-01-contract.json",
    "examples/sequence-airport-arrival/clip-01-prompt.md",
    "examples/sequence-airport-arrival/clip-01-take-review.json",
    "examples/sequence-airport-arrival/clip-02-continuation-contract.json",
    "examples/sequence-airport-arrival/clip-02-prompt.md",
    "examples/sequence-observed-deviation/project-state-before.json",
    "examples/sequence-observed-deviation/take-review.json",
    "examples/sequence-observed-deviation/project-state-after.json",
    "examples/standalone-clip/project-state.json",
    "examples/standalone-clip/prompt.md",
    "examples/golden-prompts/compact-i2v.md",
    "examples/golden-prompts/r2v-role-isolation.md",
    "examples/golden-prompts/phased-single-take.md",
    "examples/golden-prompts/dense-2d-storyboard.md",
    "examples/golden-prompts/sequence-continuation.md",
    "examples/golden-prompts/continuation-observed-deviation.md",
    "examples/golden-prompts/first-last-frame-transition.md",
    "examples/golden-prompts/video-edit-one-layer.md",
    "assets/hero-command-center.png",
    "assets/hero-global-filmmaker-mode.png",
    "assets/infographic-skill-capabilities.png",
    "assets/infographic-cdn-delivery-map.png",
    "assets/infographic-reference-role-map.png",
    "assets/infographic-production-delivery.png",
    "assets/infographic-professional-qc-stack.png",
    "assets/hero-cinematic.png",
    "assets/skill-os-infographic.png",
    "assets/skill-map-cinematic.png",
    "assets/hero-dark.svg",
    "assets/hero-light.svg",
    "assets/skill-map.svg",
    "docs/frontend-redesign.md",
    "docs/v6-release-readiness.md",
    "docs/README.zh.md",
    "docs/README.ja.md",
    "docs/README.ko.md",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    return run_validation(
        Path(args.repo).resolve(),
        expected_skills=EXPECTED_SKILLS,
        expected_version=EXPECTED_VERSION,
        required_files=REQUIRED_FILES,
        required_references=REQUIRED_REFERENCES,
        strict=args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
