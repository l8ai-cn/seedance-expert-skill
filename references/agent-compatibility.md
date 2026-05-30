# Agent Compatibility

last_verified: 2026-05-30

Use this file when reviewing whether this repository is shaped correctly as an Agent Skill package. This is about packaging and agent behavior, not Seedance model capability.

## Current Agent-Skill Shape

Codex's current Agent Skills documentation describes a skill as a directory with a required `SKILL.md` file plus optional `scripts/`, `references/`, `assets/`, and `agents/` folders. It also describes progressive disclosure: the agent sees the name, description, and path first, then loads the full `SKILL.md` only when the skill matches the task.

This repository follows that pattern:

| Agent-skill expectation | Repository location | Status |
|---|---|---|
| Root skill metadata and routing | `SKILL.md` | Present |
| Task-specific sub-skills | `skills/*/SKILL.md` | Present |
| Dense reference material | `references/*.md` | Present |
| Validation and maintenance scripts | `scripts/*.py` | Present |
| README-facing visual resources | `assets/*` | Present |
| Behavioral evals | `evals/evals.json` | Present |
| CI validation | `.github/workflows/validate-skills.yml` | Present |

## Compatibility Rules

- Keep every active `description` in third-person activation wording so tools can match it from a shortened skill list.
- Keep the root `SKILL.md` small. Route to sub-skills and references instead of copying long tables into the root.
- Keep volatile facts in dated references such as `api-status.md` and `source-registry.md`.
- Keep generated bitmap images inside `assets/` if they are referenced by README.
- Keep scripts deterministic and local. They should validate structure, schema, design, and source metadata without requiring private credentials.
- Do not store API keys, account cookies, or private prompt corpora in the skill package.

## Cross-Client Notes

Different agent clients scan different local paths. Codex documentation says repository skills can live under `.agents/skills` at the current directory, parent directories, or repository root. Other agent clients may use `.claude/skills`, `.gemini/skills`, `.github/skills`, `.cursor/skills`, or `.windsurf/skills`. Treat those as installation targets, not separate source trees.

## Source Signals

- OpenAI Codex Agent Skills docs: https://developers.openai.com/codex/skills
- OpenAI Academy plugins and skills explainer: https://openai.com/academy/codex-plugins-and-skills/
- OpenAI skills catalog: https://github.com/openai/skills
- Agent Skills open standard overview: https://agentskills.io/

## Do Not Claim

- Do not claim every agent client can install directly from this repository URL.
- Do not claim every client honors the same metadata fields beyond `name` and `description`.
- Do not claim this repository provides a live Seedance API wrapper. It is an agent-skill workflow and reference package.
