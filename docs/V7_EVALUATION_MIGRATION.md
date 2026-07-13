# V7-10 evaluation coverage migration

V7-10 adds an offline, candidate-only evaluation control plane. It expands public behavior cases, declares existing deterministic and metamorphic oracles, and defines a hash-bound format for reviewing externally returned media. It does not call a provider, inspect the checked-in synthetic media hashes, authenticate reviewers, execute a held-out corpus, establish Seedance quality, or enable a release gate.

## Four separate evaluation layers

1. **Public behavior cases:** the blind V7-03 responder/judge harness now has 145 public development cases. Seven new cases cover route leakage, a baseline/style-transformed operation pair, returned-media evidence, final-frame limits, complete attempt retention, and the synthetic-fixture boundary. Public development and live-canary suites remain non-release-eligible.
2. **Deterministic programme inventory:** `evals/evaluation-program-v1.json` binds seven existing offline suites to exact test or script entrypoints. The validator checks a closed inventory; it never executes a path or command supplied by the JSON.
3. **Metamorphic inventory:** six named relations bind to exact test methods or public case IDs. Five are offline deterministic. Operation classification under irrelevant style adjectives remains a public development model case, not a deterministic or release oracle.
4. **Returned-output review:** a benchmark manifest preregisters one condition, exact provenance hashes, all ten attempts, observables, and declared reviewer roles. Atomic annotations bind one reviewer, one output, and one observable to an exact evidence locus. Aggregation is double-review, disagreement-aware, complete-attempt, and failure-first.

These layers are not interchangeable. Passing a schema, a text-agent case, or a synthetic aggregation probe does not show that a provider accepted a request or that a generated video followed it.

## Declared metamorphic relations

| Relation | Execution class | Bound oracle |
|---|---|---|
| surface swap preserves the semantic programme | offline deterministic | `test_surface_swap_preserves_semantics` |
| English/Chinese wrapper swap preserves semantic order and exact utterance bytes | offline deterministic | `test_language_swap_preserves_semantics` |
| reference reordering follows the selected typed surface profile | offline deterministic | `test_reference_reorder_follows_profile` |
| removing a selected authority blocks release | offline deterministic | `test_missing_selected_claim_blocks_release` |
| irrelevant style adjectives preserve operation classification | development model only | `task_classification_baseline_first_last_frame` + `task_classification_ignores_style_adjectives` |
| replacing video with a derived final frame weakens temporal evidence | offline deterministic | `test_final_frame_weakens_temporal_evidence` |

The programme validator confirms that every path is a plain in-repository file and that every declared oracle ID still exists. Python sources are parsed as syntax trees, not searched as substrings or executed. Registration does not run plan-supplied code or turn a model case into a deterministic test.

## Benchmark manifest

`benchmark-manifest-v1` describes one exact condition. It records:

- model, model version, surface, surface version, region, and operation;
- model-profile, surface-profile, AV-policy, operation-contract, protocol, rubric, and annotation-schema hashes;
- semantic-program, prompt-render, input-manifest, condition, request-template, generation-settings, request, generation-record, returned-media, metadata, and failure-record hashes as applicable;
- a declared request-variance policy with an exact allowed-field list and explicit fixed/not-requested seed handling;
- exactly ten indexed attempts, with every attempt retained;
- an original retained video plus duration, frame count, and audio-presence metadata for every successful attempt, or an explicit failure record with every output field null; and
- a closed observable catalog that covers all 22 dimensions while permitting distinct repeated items such as multiple dialogue lines or cuts; and
- primary, secondary, and adjudicator declarations.

The checked-in manifest is a synthetic contract fixture. Its model and surface versions say so explicitly. All benchmark manifests are `offline_candidate`, `offline_review_only`, `release_eligible: false`, and `quality_claim_status: prohibited`. Hashes establish internal identity only; request-template/settings hashes are declarations unless separately reproduced from retained canonical request bytes. None of these hashes is a signature or proof of who generated, retained, or reviewed an artifact.

## Atomic observable review

An atomic annotation covers exactly one output and one preregistered observable. The closed vocabulary contains 22 dimensions:

- operation correctness and binding integrity;
- identity and composition adherence;
- subject motion, camera motion, causal order, physical consequence, material response, and settled endpoint;
- temporal and semantic audio sync, speaker assignment, exact dialogue, spoken language, dialogue intelligibility, lip sync, and audio continuity;
- editorial-cut and multi-shot continuity;
- unexpected text/logo; and
- overall usable take.

There is no notes or hidden-cause field. A reviewer records `pass`, `fail`, `unknown`, or `not_applicable`, a bounded confidence, and one frame/time evidence locus. Every time/frame range is checked against retained duration/frame-count metadata; a temporal frame span must contain more than one frame. Decisive audio observations additionally require retained audio-presence metadata. Whole-output passes and overall-take decisions require the complete returned video. A derived final frame can localize a static observation; it cannot decide temporal behavior or establish whole-video absence/adherence.

The annotation binds the exact raw-byte manifest snapshot, condition, attempt index, generation record, global rubric, rubric item, output ID, original returned-video hash, evidence-asset hash, parent-output hash, derivation record when applicable, and declared reviewer identity. The validator reads the manifest bytes once into a digest-carrying snapshot, preventing a caller from supplying detached parsed content and a separate digest. The reviewer declaration is metadata, not authentication or proof of independence.

## Complete-condition aggregation

The dependency-free validator requires primary and secondary annotations for every preregistered observable on every returned attempt. A disagreement requires the declared adjudicator. Missing, duplicate, unregistered, mismatched, or unnecessary review cells fail closed.

Aggregation never averages away a failure:

- any generation failure or resolved observable failure makes the condition fail;
- missing coverage, unresolved disagreement, `unknown`, or `not_applicable` makes it incomplete; and
- a pass requires complete agreement or adjudication across every retained attempt and required observable.

Even a complete synthetic `pass` reports `release_pass: false` and `quality_claims_allowed: false`. Reports retain the exact manifest digest, an order-invariant annotation-set digest, and resolved confidence counts so a low-confidence pass is not erased. The checked-in annotations are only single-record fixtures; the complete 10-attempt by 22-observable matrix is constructed in memory to test aggregation and row-order invariance.

## Mutation and determinism requirements

Two closed mutation campaigns contain 12 programme mutations and 21 output-review mutations. They attack network/release/quality flags, corpus status, suite and oracle inventory, minimum attempts, retention, reviewer separation, manifest/output/provenance hashes, observable/rubric registration, temporal and whole-output evidence, bounds, audio presence, hidden-cause boundaries, confidence, and object closure. The declared minimum detection rate is 90%; the checked-in self-test detects all 33 mutations.

Four aggregation probes cover complete double review, input-row reordering, missing review, and failure-first resolution. CI also runs the checker ten times in fresh dependency-free Python processes on Python 3.11 and 3.12 across Linux, macOS, and Windows.

```bash
python -S -B scripts/evaluation_program_check.py --self-test
python -S -B scripts/evaluation_program_check.py --self-test --json
python -S -B -m unittest tests.test_evaluation_program tests.test_evaluation_metamorphic tests.test_v710_regression -v
```

For an offline review bundle, pass both files together. The command loads the manifest once, validates the annotation array, and prints only the canonical non-release aggregate report and diagnostic codes:

```bash
python -S -B scripts/evaluation_program_check.py \
  --review-benchmark path/to/benchmark.json \
  --review-annotations path/to/annotations.json
```

## Preserved and deferred boundaries

- V7-07, V7-08, and V7-09 contracts, tools, and fixtures remain byte-exact.
- `generation-run-v2` remains a blocked/not-run receipt. The legacy three-case generation benchmark remains a historical structural fixture and is not promoted into output evidence.
- The V7-03 public CLI still refuses external held-out execution and hard-locks `release_pass` false.
- No provider profile, evidence policy, trusted AV policy, network path, or installable runtime file is activated.
- Raw/private media and held-out cases stay outside the repository.

Operational held-out execution, authenticated reviewer independence, retained live provider outputs, provider-adherence conclusions, and activation remain V7-12 work under protected review.

## Exit criteria

V7-10 is complete when the schemas and dependency-free semantics agree, all declared mutations fail closed, aggregation is order-invariant and failure-first, public behavior cases load blindly, ten-process and cross-platform CI pass, the V7-09 byte locks hold, and activation remains disabled. These checks prove evaluation-contract integrity, not model quality.
