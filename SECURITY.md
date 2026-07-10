# Security Policy

## Scope

Seedance 2.0 Skill OS is an **offline agent-skill and reference package**: Markdown skill/reference files, deterministic local validators, and a local package builder/installer. It is not a hosted service or an API wrapper. It stores no credentials and ships no telemetry. The installer writes only to the selected local skills directory, stages and verifies a checksum-locked allowlist, and retains the previous installation for rollback.

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than in a public issue:

- Use GitHub's **private vulnerability reporting** on this repository (the **Security** tab → **Report a vulnerability**).

Include what you found, where, and how to reproduce it. We aim to acknowledge reports within a reasonable time and will credit reporters who want it once a fix ships.

## Security posture of this package

- **No network calls, no telemetry.** The skill content is text. Runtime tools and validators need no credentials. The installer performs local filesystem writes only after a dry-run-capable package validation — read it before running.
- **No secrets in the repo.** API keys, account cookies, and private prompt corpora are never stored here (see `references/agent-compatibility.md`). Do not add them in a fork or PR.
- **CI validates structure, not just prose.** Every push and pull request runs the checks in `.github/workflows/validate-skills.yml`, including runtime-package tests on Linux, Windows, and macOS.
- **Checksums are integrity controls, not publisher signatures.** `--check` and `--verify` bind the package to the source lock in the checkout that runs them. Obtain that checkout and revision from a source you trust; a malicious checkout can replace its own lock and code.

## Using this skill safely inside an agent

This package is only as safe as the **agent client** you load it into. The skill itself does nothing on its own; the agent that reads it can do whatever that agent is allowed to do. Treat the agent — not this skill — as your trust boundary.

- **Install only into agent clients you trust** and keep them updated. Do not install into unknown or unvetted agents just because they accept the skill format.
- **Never paste secrets into an untrusted agent.** This skill never asks for API keys, tokens, account cookies, or private/client footage. If an agent — or a modified copy of this skill — asks for them, stop.
- **Prefer clients that sandbox or scan skills on install** (for example, Hermes runs a security scan on `hermes skills install`). Verify install paths in your own client; the cross-agent matrix in `references/agent-compatibility.md` is labeled "verify in your client," not a guarantee.
- **Review before you load.** Any skill from any source is Markdown that an agent will read as instructions. Review third-party skills — including forks of this one — before loading them into a privileged agent; prompt-injection-style text can hide in innocent-looking docs.
- **Keep the content boundaries.** The `seedance-copyright` and `seedance-filter` skills rewrite unsafe requests into safe, original equivalents and repair false-positive filtering by clarifying legitimate production context. They are not tools to defeat any platform's safety systems — do not use this package to evade provider moderation.

## What this project will not do

- It will not add telemetry, network calls, or credential prompts to the skill or its scripts.
- It will not claim that every agent client can install directly from the repository URL, or that any registry lists this skill unless it has actually been published there.
