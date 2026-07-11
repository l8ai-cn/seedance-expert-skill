# Claim-level evidence registry

This is the canonical research control plane for the Seedance v7 rebuild. It records atomic claims, exact retained evidence, runtime occurrences, freshness, conflicts, and a closed release policy. It does not change installed guidance by itself.

## V7-04 non-activation contract

- `release-policy.json` schema-locks `activation_enabled` to `false`.
- Claim `runtime_status` can only be `candidate`, `blocked`, or `research_only`.
- Every file in the 119-file runtime allowlist is byte-pinned in `runtime-map.json`.
- The staged audit marks 93 files `legacy_blocked`, 22 files `no_volatile_claims`, and 4 candidate profiles; the release gate must stay red until later migration PRs replace the remaining debt with exact claim occurrences.
- `research/` and every `schemas/evidence-*` control schema are forbidden from the installable runtime package.
- No skill, prompt compiler, installer, or runtime script reads this registry.
- A reviewer approving evidence is not authorizing runtime activation. Activation requires a later policy change, migrated runtime text, passing evals, and separate review.

The older `references/source-registry.md` and dated source corpus remain legacy runtime material during the staged migration. They are not the authority for this control plane and cannot satisfy this release policy.

## Registry layout

| Path | Purpose |
| --- | --- |
| `authorities.json` | Closed publisher, host, and source-type allowlist. |
| `sources/` | Immutable retrieval metadata and document-byte hashes. |
| `captures/` | Normalized, bounded evidence items retained for hash-bound review; provider paraphrases require source re-fetch. |
| `claims/` | Atomic claim records with scope, value, TTL, transitive source/capture/item byte pins, consumers, relations, and review state. |
| `runtime-map.json` | Exact manifest/file hashes and claim occurrences for every installable file. |
| `release-policy.json` | Closed requirements pinned to exact claim-file bytes and lineage roots. |

The repository currently contains 17 claims, 6 source snapshots, and 6 retained captures. The Contra dataset card and its pinned CSV audit are separate provenance chains. No Seedance 2.5 evidence record is retained. The validator independently forces any future Seedance 2.5 claim to remain `unverified` and `blocked` until official evidence is added in a separately reviewed change.

## What a claim proves

The dimensions are deliberately independent:

| Field | Meaning |
| --- | --- |
| `support_status` | Whether retained source items support the exact atomic statement. |
| `agreement_status` | Whether other evidence is uncontested, qualified, conflicting, or not assessed. |
| `runtime_status` | Candidate, blocked, or research-only disposition; never activation. |
| `runtime_presence` | Whether related wording already exists in legacy runtime files, is absent, is research-only, or is a watchlist item. |
| `criticality` | Release-policy severity, protected against downgrade. |
| `review` | Declared editorial metadata bound to the exact canonical claim payload. The strings do not prove identity or independent GitHub approval. |
| `affected_*` | Declared profiles, files, and regression tests; runtime occurrence mapping is separately enforced. |

Qualified relations must be reciprocal. In-scope incompatible values require an explicit conflict group. Superseded claims require a later compatible successor and retain a closed lineage root.

## Evidence and provenance limits

A document hash records the bytes observed during research; it does not prove publisher identity, retrieval completeness, or that a normalized paraphrase follows from the publisher page. Full provider bytes are not redistributed here, so the repository proves internal hash binding and tamper detection, not offline source reproduction. Reviewers must re-fetch the pinned URL, match the recorded raw hash, and inspect the declared locator before approving a provider-backed claim. Every claim binds the exact source-record bytes, capture bytes, and selected item hashes, so rewriting an evidence dependency invalidates the reviewed claim and its release-policy pin. Supported activation requirements cannot rely on a missing retained capture.

The Contra Labs dataset is third-party, CC BY 4.0 research material. Its retained record supports only an observable evaluation ontology. It does not prove Seedance architecture, prompt grammar, or model capability.

Provider prompt tokens are surface-scoped. Current retained evidence shows different representations on BytePlus, Volcengine, and fal, so the registry explicitly rejects a universal `@tag` assumption.

## Freshness semantics

Every claim class has a maximum TTL. Expiry is UTC and exclusive: a claim is expired when `as_of >= expires_at`. Updating a date without a matching source snapshot and evidence item does not refresh a claim.

The daily scheduled workflow is a best-effort offline reminder only. It performs no web fetch, does not rewrite evidence, does not approve a claim, and cannot make the release gate green. CI and the release command remain fail-closed at expiry even if a schedule is delayed. It proposes a deterministic report for human review from the trusted default branch.

GitHub suppresses recursive workflow runs for pushes and pull requests created with the repository `GITHUB_TOKEN`. The automation PR therefore stays draft and must not be merged until a human runs `validate-seedance-skill` with `workflow_dispatch` against that branch. Before activation, independent approval must be enforced through protected GitHub reviews and required code-owner review, not by typing two names into a claim file.

## Local validation

Use Linux x86-64 with CPython 3.12 and the repository's hash-locked validation environment. The secure evidence reader intentionally requires descriptor-relative `O_NOFOLLOW` traversal; evidence CI is Linux-only. This does not change the installable runtime's Linux, macOS, and Windows portability matrix.

```bash
python -m venv /tmp/seedance-validation
/tmp/seedance-validation/bin/python -m pip install --require-hashes --requirement requirements-validation.lock
/tmp/seedance-validation/bin/python tools/evidence_registry.py --enforce-freshness --report /tmp/evidence-report.json
/tmp/seedance-validation/bin/python -m unittest tests.test_evidence_registry -v
```

Structural validation succeeds while the release gate remains intentionally blocked:

```bash
/tmp/seedance-validation/bin/python tools/evidence_registry.py --release
```

`--release` exits non-zero until all exact policy requirements, freshness checks, independent critical reviews, retained captures, and runtime coverage checks pass. `--as-of YYYY-MM-DD` makes time-bound tests and reports reproducible.

See `docs/V7_EVIDENCE_MIGRATION.md` for ownership, migration order, and the later activation boundary.
