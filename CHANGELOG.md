# Changelog — seedance-20

All notable changes to this project are documented here.

## [5.4.1] — 2026-05-30

### Added

- Added `assets/skill-os-infographic.png` and a README section explaining the skill operating-system lanes.
- Added `references/agent-compatibility.md` for Codex/Agent Skills packaging, progressive disclosure, and install caveats.
- Added May 30 source records for Volcengine's May 29 model-list/tutorial updates, the Volcengine API-service ecosystem article, Agent Skills docs, and recent audio-video eval benchmark vocabulary.

### Changed

- Refreshed the dated research snapshot to `research-2026-05-30.md` and the source data file to `sources.seedance-2026-05-30.json`.
- Tightened README installation wording so local skill paths are treated as client-specific targets, not universal install guarantees.
- Updated validation scripts and design checks to enforce the new infographic, agent compatibility reference, v5.4.1 metadata, and May 30 source data.

### Fixed

- Kept FLF2V wording explicitly partner/surface-specific unless a current first-party API page exposes that exact workflow name.
- Added a stronger BytePlus caveat: do not quote Seedance 2.0 BytePlus pricing or model IDs from JavaScript-rendered pages without live official verification.

## [5.4.0] — 2026-05-27

### Added

- Added a generated cinematic README hero image at `assets/hero-cinematic.png`.
- Added dated research and source layers, later carried forward as `research-2026-05-30.md`, plus `platform-surface-matrix.md`, `model-name-map.md`, `first-last-frame-guide.md`, `field-observed-tips.md`, and `community-source-methodology.md`.
- Added structured source and community-pattern data files under `data/`.
- Added source freshness and vocabulary schema validators.
- Added eval cases for model-name accuracy, source freshness, first/last-frame workflow, Chinese/Russian role binding, unsafe bypass refusal, and community corpus safety.

### Changed

- Refreshed `api-status.md` and `source-registry.md` to 2026-05-27 source boundaries.
- Expanded active Chinese and Russian vocabulary references with role binding, first/last-frame, camera, lighting, audio, editing, constraint, and safety terms.
- Updated prompt, pipeline, recipe, filter, and multilingual skills to route into the new research and FLF2V references.
- Updated CI and release validation to run six checks instead of four.

### Fixed

- Prevented ambiguous `Seedance 2.0 Pro` naming from being treated as the official Seedance video-model name.
- Made public prompt-corpus mining safety-first: extract structures and vocabulary, not unsafe raw examples.

## [5.3.0] — 2026-05-08

### Fixed

- Removed the legacy duplicate `user-invokable` frontmatter key and updated the validator to the canonical `user-invocable` field.
- Expanded formerly thin production modules, multilingual vocabulary routers, and reference glossaries so each skill is useful as a standalone entry point.
- Deepened `references/source-registry.md` with source hierarchy, evidence labels, claim boundaries, and required wording for volatile platform claims.

### Changed

- Updated all skill metadata, README badges, validator text, and eval metadata to `5.3.0`.
- Recompressed the root `SKILL.md` into a lean router while keeping detailed guidance in sub-skills and references.

### Added

- Added eight eval cases covering VFX physics, multilingual vocabulary, Chinese examples, anti-slop repair, and short-interview routing.

## [5.2.0] — 2026-05-08

### Fixed

- Repaired the partial v5.1 deployment: restored multiline Markdown, multiline YAML frontmatter, real Python scripts, non-empty evals, and the missing GitHub Actions workflow.
- Replaced old one-line active files that made README, references, and scripts render poorly.
- Normalized all 23 sub-skill frontmatter blocks to `metadata.version: "5.2.0"` and `metadata.parent: "seedance-20"`.

### Changed

- Redesigned the GitHub-facing README as a cleaner project front page with a start-here table, skill map, reference library, validation section, and design standard.
- Replaced neon/overloaded visual language with a disciplined cinematic-control design system.
- Converted oversized active sub-skills into lean procedural routers while preserving old local content through the patcher backup/migration path.
- Updated platform guidance to source-aware, date-stamped language.

### Added

- New SVG frontend assets: `assets/hero-dark.svg`, `assets/hero-light.svg`, and `assets/skill-map.svg`.
- Validation scripts: `scripts/validate_skills.py`, `scripts/content_audit.py`, `scripts/eval_schema_check.py`, and `scripts/design_audit.py`.
- CI workflow: `.github/workflows/validate-skills.yml`.
- Evals: `evals/evals.json` with 18 realistic test cases.
- References: `api-status.md`, `source-registry.md`, `audio-guide.md`, `anti-slop-lexicon.md`, `filter-vocab.md`, `progressive-disclosure.md`, `eval-rubric.md`, and `frontend-design-system.md`.

## [5.1.0] — 2026-05-08

Validation, status, and progressive-disclosure repair release. Superseded by v5.2.0 because the pushed v5.1 files were partially collapsed and incomplete.

## [5.0.0] — 2026-03-03

Intent-first prompting release. Introduced the Director Formula, short-prompt preference, expanded references, and quad-modal workflow routing.

## Historical Releases

Earlier v3.x and v4.x releases built the modular skill structure, multilingual vocabulary, example library, troubleshooting modules, and platform support matrix. See repository history for the full legacy changelog.
