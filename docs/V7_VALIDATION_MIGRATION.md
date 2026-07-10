# V7 validation migration note

V7-02 makes the five existing Draft 2020-12 schemas executable contracts. It is intentionally stacked on the unreleased v7 integration line and is not a v6 stable-release change.

Legacy `--strict` switches that did not alter validation have been removed. The flag remains only on validators where it promotes warnings or enables strict coverage; scripts with a single validation policy now expose that policy directly.

The structured contract objects are now closed with `additionalProperties: false`, critical identifiers and text fields reject empty strings, collection item types are explicit, positive durations are enforced, and project `updated_at` values use the JSON Schema `date` format. Deliberately free-form state containers such as `world_bible`, `surface`, and planned or observed state objects remain extensible.

Before adopting the v7 runtime, validate saved fixtures with:

```bash
# Reproducible release environment only: Linux x86-64, CPython 3.12.
python -m pip install --require-hashes --requirement requirements-validation.lock
python scripts/schema_check.py --strict
```

If a structured record contains an extension field, move that information into an intentionally free-form state container or propose the field as part of the canonical schema before migration. Preserve the original v6 state file; do not overwrite it during repair. V7-08 will provide the non-destructive project-state-v2 migration.
