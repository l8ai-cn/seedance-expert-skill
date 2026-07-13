# V7 validation migration note

V7-02 made the original Draft 2020-12 schemas executable contracts. V7-08 adds six separate candidate-only v2 schemas without mutating the legacy project-state contract. These changes are stacked on the unreleased v7 integration line and are not a v6 stable-release change.

Legacy `--strict` switches that did not alter validation have been removed. The flag remains only on validators where it promotes warnings or enables strict coverage; scripts with a single validation policy now expose that policy directly.

The structured contract objects are now closed with `additionalProperties: false`, critical identifiers and text fields reject empty strings, collection item types are explicit, positive durations are enforced, and project `updated_at` values use the JSON Schema `date` format. Deliberately free-form state containers such as `world_bible`, `surface`, and planned or observed state objects remain extensible.

Before adopting the v7 runtime, validate saved fixtures with:

```bash
# Reproducible release environment only: Linux x86-64, CPython 3.12.
python -m pip install --require-hashes --requirement requirements-validation.lock
python scripts/schema_check.py --strict
```

If a legacy structured record contains an extension field, move that information into an intentionally free-form legacy state container or propose the field as part of a versioned contract before migration. Preserve the original v6/v1 state file; never overwrite it during repair.

V7-08 migration is explicit and non-destructive:

```bash
python -S -B scripts/project_state_migrate.py inspect project-state-v1.json
python -S -B scripts/project_state_migrate.py migrate project-state-v1.json --map migration-map.json
python -S -B scripts/project_state_migrate.py verify project-state-v1.json project-state-v2.json --map migration-map.json
python -S -B scripts/project_state_v2_check.py < project-state-v2.json
python -S -B scripts/v2_aux_check.py --self-test
```

The migration tool emits to stdout and never writes the source. The map binds both raw source bytes and canonical JSON, and must explicitly provide binding ID, media type, asset/take digest when known, state-atom ownership, motion destination, endpoint decisions, and a hashed disposition for every legacy semantic field. Target/dimension authority remains `unresolved`; selected provider policy is deliberately absent from surface-independent state. Legacy tags, roles, source-clip strings, upload order, filenames, and prose never authorize inference. Unmapped leaves, false mapped dispositions, and non-null legacy source tags fail closed.

Every V7-08 clip is `compile_required: true`. The v2 prompt/run contracts can represent only the blocked pre-compile state; they cannot claim a compiler, submission, provider response, render, or output. V7-07 remains byte-stable and is not wired to project-state-v2.
