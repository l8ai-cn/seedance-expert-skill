# Evidence v2 foundation

This directory is an evidence-only shadow registry. It records narrowly scoped claims for review without changing Seedance skill instructions, prompt output, routing, examples, assets, or installed behavior.

## Non-activation contract

- `runtime_eligible` is schema-locked to `false`.
- The checker also rejects every runtime-eligible record, even when `--shadow-only` is omitted.
- The workflow runs with both `--shadow-only` and `--enforce-freshness`.
- Nothing in the installed skill reads this directory. The installer excludes `.github`.
- Raw evidence records must never become a runtime input. Any future projection into the skill requires a separate policy, implementation, evaluation, and review PR.

Editorial approval is not activation authorization. A future activation policy must bind approval to trusted identities and the reviewed commit, protect policy code independently from submitted records, and define provenance requirements. This foundation intentionally implements none of those capabilities.

## Reading a claim

The status fields are independent:

| Field | Meaning |
| --- | --- |
| `support_status` | Whether the cited source supports the exact atomic statement. It does not mean the skill adopts the statement. |
| `volatility` | How quickly the evidence may become stale. Volatile claims must be verified from a same-day source snapshot. |
| `agreement_status` | Whether other in-scope evidence is uncontested, qualified, conflicting, or not assessed. Unverified claims must use `not_assessed`. |
| `lifecycle_status` | Whether the record is active evidence, expired, or replaced by a compatible successor. |
| `runtime_disposition` | Editorial intent while activation remains locked. `allow` is invalid for every current record. |
| `review` | Editorial review metadata only. It is not a security boundary or runtime authorization. |

Active supported claims with different values are compared when their normalized keys and scopes overlap. Conflicts require a shared conflict group. Qualification relations must be reciprocal. Superseded records require a compatible active successor.

## Sources, hashes, and captures

`retrieved_document_sha256` records the bytes used during research when those bytes were available. A hash demonstrates integrity against those bytes; it does not prove publisher identity, acquisition method, completeness, or provenance.

`capture_path: null` means no retained artifact can be independently hash-verified from this repository. A retained artifact, if one is later justified and legally appropriate, must live under `.github/evidence-v2/captures/`; the checker rejects paths elsewhere. Full third-party pages and the user-supplied screenshots are not committed in this pilot.

Supported claims also pass a claim-class/source-type compatibility matrix. Community sources cannot support model capability, API contract, pricing, model ID, official-example, or prompt-grammar claims. Release watchlists and community patterns cannot activate runtime behavior even after the foundation lock is removed.

## Freshness

Each claim class has a maximum TTL. The scheduled job fails when active evidence expires. Updating `verified_at` is not enough for volatile evidence: a new same-day source snapshot is required, and its ID must end with the `retrieved_at` date.

The current pilot intentionally contains:

- 12 atomic claims and 5 source snapshots;
- 0 retained, artifact-verified source captures;
- 0 runtime-eligible records;
- 12 pending editorial reviews; and
- 2 user-supplied Seedance 2.5 watchlist records marked unverified, not assessed, and blocked.

## Local validation

Use Python 3.12 on Linux x86-64 so the hash-locked wheel set matches CI:

```bash
python -m venv /tmp/seedance-evidence-venv
/tmp/seedance-evidence-venv/bin/python -m pip install --require-hashes -r .github/evidence-v2/requirements.lock
/tmp/seedance-evidence-venv/bin/python -B -m unittest discover -s .github/evidence-v2/tests -v
/tmp/seedance-evidence-venv/bin/python -B .github/evidence-v2/check_evidence.py --shadow-only --enforce-freshness --report /tmp/evidence-v2-report.json
```

The JSON report is deterministic for the same records and `as_of` date. It exposes errors, warnings, status counts, retained-capture verification count, and runtime-eligible count.
