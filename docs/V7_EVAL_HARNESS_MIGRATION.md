# V7 blind evaluation harness migration

V7-03 replaces the v6 model-in-the-loop script because its responder was given `skills_expected_to_activate`, silently truncated loaded resources, defaulted the responder and judge to the same model, and could report PASS for an empty selection or for a judge verdict with `pass: false`.

## Trust labels

- **Development:** 126 public cases. Assertion-blinded, not held out, and never release-eligible.
- **Live canary:** eight public cases sent through the configured provider. Detects provider/model/judge drift; it does not generate or score Seedance video and is not a quality release gate.
- **Held out:** a sealed external case pack intended for a future protected release gate. V7-03 can validate its contract in offline tests, but the public CLI refuses to execute external suites and hard-locks `release_pass` to false. A self-declared flag cannot establish a trusted runner.

## Explicit network execution

Offline CI runs only:

```bash
python scripts/eval_run.py --self-test
```

A private development run is explicit and requires two distinct models, an egress acknowledgement, a clean commit, and a private output directory:

```bash
install -d -m 700 ../seedance-private-eval-runs
export ANTHROPIC_API_KEY=...
python scripts/eval_run.py --run \
  --suite development \
  --responder-model <responder-model-id> \
  --judge-model <different-judge-model-id> \
  --acknowledge-network-egress \
  --output-root ../seedance-private-eval-runs
```

The example uses POSIX mode `0700`, which the harness enforces. On Windows, choose an output directory whose ACL grants access only to the intended account; Python mode bits do not establish that ACL.

Do not commit run bundles. Successful calls preserve exact request and complete provider-response bytes. Failed calls preserve the observed response bytes with explicit completeness, truncation, and byte-limit fields. The harness does not serialize credential environment variables or authorization headers, but raw prompts, fixtures, or responses can themselves contain secrets. Verify a completed bundle offline with `python scripts/eval_run.py --verify-bundle PATH`.

Each provider stage is checkpointed as it completes. The run directory is reserved exclusively before the first checkpoint, and `COMPLETE.json` is the commit point. If a process dies before finalization, mark that reserved directory with `python scripts/eval_run.py --recover-incomplete PATH`; recovery is idempotent and can only produce `passed: false` and `release_pass: false`.

The Markdown ledger is no longer an evidence source. A completed v2 bundle is no-overwrite, checksum-manifested, completion-bound, and includes candidate commit/tree state, hashes of the harness files actually executing, Python/platform provenance, suite/rubric/runtime hashes, requested and returned models, provider endpoint/settings, resources, asset declarations, timings, usage, IDs, attempts, seed-support status, honest unknown-cost status, raw bytes, parsed judgments, and the locally derived verdict. Bundle verification checks strict schemas and internal semantic consistency; checksums are not signatures or protected-runner attestations, so a malicious party able to rewrite a bundle can recompute them.

`asset_paths` are recorded as hash-only declarations in V7-03; no image, video, or audio bytes are sent to the provider. Development/live results therefore test text behavior and wiring, not Seedance video quality or multimodal understanding.

## v6 to v7 CLI map

| v6 behavior | V7-03 replacement |
|---|---|
| no action flag | choose explicit offline `--self-test`, networked `--run`, `--verify-bundle`, or `--recover-incomplete` |
| `--model MODEL` | explicit `--responder-model MODEL` plus a different `--judge-model MODEL` |
| `--ledger FILE` | private `--output-root DIRECTORY`; POSIX mode is owner-only, Windows requires a private ACL, and repository Markdown is not evidence |
| `--stamp TEXT` | generated or explicit `--run-id`, plus commit/tree, suite, configuration, and attempt provenance |
| external `--suite-file` execution | disabled in the public harness until a protected runner and approved private corpus exist |
