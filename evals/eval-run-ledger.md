# Eval Run Ledger

This file is a historical v6 placeholder, **not evaluation evidence**. No valid
live run was recorded here. V7-03 replaces overwriteable Markdown tables with
private, no-overwrite, checksum-manifested JSON bundles produced by
`scripts/eval_run.py`.

## Offline wiring validation

The deterministic CI check performs no scored provider run and needs no key:

```bash
python scripts/eval_run.py --self-test
```

The v2 harness performs blind route selection before loading complete allowlisted
resources, uses a distinct judge model, validates every assertion and sequence
dimension, and derives pass/fail locally. See
[`docs/V7_EVAL_HARNESS_MIGRATION.md`](../docs/V7_EVAL_HARNESS_MIGRATION.md).

For the explicit networked development command and its trust limits, see
[`docs/V7_EVAL_HARNESS_MIGRATION.md`](../docs/V7_EVAL_HARNESS_MIGRATION.md).

## Latest scored run

_Not yet scored live in this environment (no `ANTHROPIC_API_KEY` available offline)._
Do not populate or overwrite this file. Store raw bundles outside the repository
and publish only a verified, redacted aggregate.

| id | scale | score | pass | notes |
|---|---|---|---|---|
| _no valid v2 run_ | — | — | — | held-out release runner not yet operational |
