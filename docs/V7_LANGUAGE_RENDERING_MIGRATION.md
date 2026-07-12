# V7-07 paired language rendering migration

V7-07 adds a candidate-only path from one validated reference manifest and causal scene IR to two natural-language prompt realizations: English and Simplified Chinese. The path is deliberately honest about what software can and cannot prove.

The compiler does not translate arbitrary scene prose, infer a preferred language, claim access to Seedance internals, or activate a provider request. A hash-bound catalog contains English and Chinese forms for the exact localized units that can reach the prompt. Runtime checks prove coverage, order, source binding, and resolved-key parity. A production catalog requires a human assertion about those catalog forms; fixed compiler grammar and the final renders require separate publishing review.

## Why the scene IR cannot be translated directly

The V7 causal scene IR validates entities, materials, event phases, dependencies, camera observability, audio-event links, invariants, acceptance tests, and fallbacks. Several fields remain natural-language prose:

- entity labels and stable features;
- material response properties;
- visible event changes;
- camera framing, path, speed, relationship, and endpoint descriptions;
- audio descriptions; and
- requested invariant descriptions.

Those strings are not a language-neutral ontology. A dictionary, regex pass, or generative translation step could silently change the actor, screen direction, causal order, camera move, speaker, or endpoint. V7-07 therefore requires two authored realizations for every localized unit that can reach the prompt rather than pretending that runtime translation is deterministic.

Entity stable features, material response properties, known fragilities, acceptance tests, and post fallbacks remain hash-bound review inputs. They are not localized or emitted in V7-07. Reference authority, visible events, camera clauses, audio clauses, and invariants own the provider prompt; copying every review note into both languages would add dead translation work and could contradict those prompt-owned units.

## Candidate pipeline

```text
reference manifest + scene IR + paired realization catalog
    -> scripts/semantic_lint.py
    -> surface-independent prompt program with ordered provenance units
    -> scripts/prompt_compile.py
    -> typed English and zh-Hans text/binding segments
    -> existing surface binding renderer
    -> candidate preview only
```

`scripts/semantic_lint.py` validates the manifest and scene IR, binds the catalog to the canonical scene-IR hash, checks exact catalog coverage, and emits the same ordered semantic program for both locales. Review-only entity features, material properties, fragilities, acceptance tests, and post fallbacks remain traceable through the scene hash and review units but do not become provider prompt prose.

`scripts/prompt_compile.py` consumes only validated contracts. It renders both `en` and `zh-Hans` from the same prompt program, applies fixed locale grammar and punctuation, preserves semantic unit order, and keeps binding segments separate from text. It performs no network call, media upload, provider activation, or machine translation.

The existing surface renderer remains the only component allowed to preserve an externally captured opaque handle, derive an evidence-pinned media ordinal, or omit a token for a structured request role. The language compiler must never construct provider-shaped numbered reference syntax from asset order or prose.

### Unreleased candidate contract replacement

V7-07 replaces the unreleased, candidate-only V7-06 draft version-1 authority partition rather than maintaining compatibility with external V7 draft manifests. The partition expands from 13 to 15 dimensions by adding `opening_state` and `endpoint_framing`. Every checked-in manifest is migrated: ordinary reference-generation targets mark both not applicable unless used, while first/last-frame targets explicitly assign the two new dimensions. No active 6.6 runtime contract or enabled provider profile is changed. Any external prototype built from the V7-06 draft must be migrated before V7-07 compilation; this replacement must not be repeated after the contract is released without a schema-version bump.

## Exact offline interfaces

Both commands read one strict JSON object from standard input, write canonical JSON to standard output, emit stable non-echoing diagnostics to standard error, and make no network or provider request.

Each compiler envelope has an intentional 64 MiB aggregate UTF-8 limit. Inputs above it fail with `JSON_TOO_LARGE`; the runtime never truncates them. This is a resource boundary across the complete nested request, not a claim that every schema maximum can be combined simultaneously. A locally schema-valid set of maximum-length documents can still exceed the aggregate ceiling and must be split or reduced before compilation. The focused CLI regression includes a valid input above the surface renderer's ordinary 2 MiB parser default to prove that the compiler-specific override is effective.

`scripts/semantic_lint.py` accepts exactly `schema_version`, `reference_manifest`, `scene_ir`, and `realization_catalog`. It returns a `prompt-program.schema.json` instance. `scripts/prompt_compile.py --preview-candidate` accepts exactly those four fields plus `surface_binding_set`, and returns a `prompt-render.schema.json` instance. The compiler flag is mandatory because every checked-in provider profile remains disabled and candidate-only.

The nested contracts are documented by:

- `schemas/reference-manifest.schema.json` and `validation/fixtures/reference-manifest.valid.json`;
- `schemas/scene-ir.schema.json` and `validation/fixtures/scene-ir.valid.json`;
- `schemas/surface-binding-set.schema.json` and `validation/fixtures/surface-binding-set.valid.json`;
- `schemas/prompt-realization-catalog.schema.json` and `validation/fixtures/prompt-realization-catalog.valid.json`;
- `schemas/prompt-program.schema.json` and `validation/fixtures/prompt-program.valid.json`; and
- `schemas/prompt-render.schema.json` and `validation/fixtures/prompt-render.valid.json`.

The schema fixtures prove each document's local shape. Cross-document equality, source hashes, exact catalog coverage, asset/media/order alignment, semantic-unit order, evidence expiry, and output hashes are recomputed by the runtime; a schema-only pass is not compilation. `compiler_sha256` binds a render to the exact executing `scripts/prompt_compile.py` bytes, so a fixed grammar edit changes lineage even when the catalog is unchanged. `compiler_toolchain_sha256` separately binds the exact executing `prompt_compile.py`, `reference_planner.py`, `render_surface_bindings.py`, `scene_ir_check.py`, and `semantic_lint.py` bytes.

### Exact hash recipes

Whole-document semantic hashes such as `scene_ir_sha256`, `reference_manifest_sha256`, `realization_catalog_sha256`, `surface_binding_set_sha256`, `planning_report_sha256`, and `prompt_program_sha256` are SHA-256 over `canonical_json(value)`. That byte representation is UTF-8 JSON with keys sorted recursively, `ensure_ascii=false`, compact separators `,` and `:`, non-finite numbers forbidden, and exactly one trailing LF byte. Input indentation and object-key order therefore do not affect these hashes.

Each catalog `source_sha256` is different: it is SHA-256 over the exact UTF-8 bytes of that one source scene-IR string, with no JSON quotes, trailing LF, trimming, normalization, case folding, entity-token substitution, or wrapper text. Change a realization alone and its source hash stays unchanged; change the source field and regenerate that row's source hash plus every whole-document hash derived from the scene or catalog. `compiler_sha256` and toolchain component hashes use exact file bytes. `compiler_toolchain_sha256` is SHA-256 over `canonical_json({basename: sha256(file_bytes), ...})` for the five named executing files. Rendered-prompt hashes use the exact rendered UTF-8 string bytes with no added LF. These recipes describe lineage only; they do not authenticate a reviewer.

`prompt-realization-catalog.valid.json` is deliberately marked `unattested_fixture`. It demonstrates shape and deterministic plumbing; it is not a bilingual approval. The public CLIs reject that marker. Production input must replace it with a `user_attested` or `reviewer_attested` declaration for the exact canonical validated catalog content. That declaration is not authenticated, and the publishing workflow must separately verify catalog review plus review the compiler-authored wrappers and final rendered prompts.

## Paired catalog contract

The catalog is closed and hash-bound:

- `scene_ir_sha256` identifies the exact source scene;
- each `semantic_key` identifies one expected open-text unit;
- `source_sha256` prevents a stale translation from surviving a source edit;
- `en` and `zh_hans` contain the reviewed realization pair; and
- an explicit user or reviewer attestation states that paired meaning was reviewed.

The exact localized set is: one label per entity, every visible event-state change, the five camera fields per shot, every non-dialogue audio description, and every requested invariant. Stable features and material properties remain review-only scene data and therefore have no catalog row.

Catalog order follows the source scene contract. Missing entries, extra entries, reordered entries, duplicate keys, stale source hashes, or a scene-hash mismatch fail closed. Runtime guards reject a bounded, regression-tested corpus of high-confidence URL/file-locator, secret-shaped, provider-token, meta-instruction, exact time/frame, unstable-alias, endpoint-contradiction, and camera/audio-domain patterns, plus unsafe controls, default-ignorable characters, and visually blank mask characters. These lexical guards are defense in depth, not a general DLP, prompt-injection detector, translation judge, or semantic proof. Synonyms outside the corpus can exist; operators must keep credentials and instructions out of inputs and separately review the exact catalog and final pair. Endpoint contradiction checks are deliberately clause-level and subject-agnostic: keep unrelated ambient motion out of the settled-endpoint row or it may be conservatively rejected.

Entity references inside event, audio, and invariant entries use closed tokens such as `{entity:bottle}`. Both locale forms must contain the same required entity-token set. Tokens are replaced from the catalog's stable localized entity labels, never from pronoun inference or fuzzy matching.

## Structural parity and human attestation

Machine-checked structural parity means the two realizations share:

1. the same scene-IR and reference-semantics hashes;
2. the same authority assignments, asset order, and exclusions;
3. the same entity IDs and localized-name substitutions;
4. the same shot and event order;
5. the same phase, interaction, and dependency tags;
6. the same camera move and event-observability links;
7. the same audio-event source, function, timing, and linked event;
8. the same requested invariants; and
9. the same review-only provenance units.

Each emitted catalog resolution also produces a `resolved_semantic_atoms` record. It binds the semantic unit ID, semantic key, and value hash to an exact text segment and an inclusive-start/exclusive-end UTF-8 byte range. Runtime verification checks that byte slice after locale rendering returns, so a duplicate phrase or substring in another unit cannot disguise an omitted or repointed value. The offsets are UTF-8 bytes, not Python character indexes or JavaScript UTF-16 `String.slice` indexes; browser code must use `TextEncoder` bytes (or an equivalent UTF-8 implementation) before slicing. Only the keys are compared across locales because reviewed translations have different value hashes.

Every prompt-visible binding segment also produces a hash-bound `binding_unit_trace` record naming its exact authority unit and `binding_id`. The compiler independently derives the expected trace from the prompt program and rejects a moved, duplicated, omitted, or cross-unit binding. Structured frame roles intentionally have an empty prompt binding trace because they travel in request structure; their static semantics use `request_carried` instead.

For `first_last_frame`, the manifest must explicitly assign `opening_state` and `opening_composition` to the declared first frame, plus `endpoint` and `endpoint_framing` to the declared last frame. Those four static fields remain required, source-hash checked catalog rows and remain bound inside `prompt_program_sha256`, but the renderer does not repeat them as prompt prose. The report's hash-bound `request_carried` records map each omitted semantic key and unit to the exact `binding_id` and structured role. Render `semantic_unit_ids`, key traces, binding-unit traces, and resolved atoms cover emitted prompt units only. This mapping proves a contract assignment from the validated manifest; it does not inspect pixels, prove that a frame depicts the declared state, or attest reference quality.

Matching structure does not prove that two sentences are idiomatic or semantically equivalent. A catalog can mention the same entities in the same event while mistranslating the action. The `user_attested` or `reviewer_attested` record is therefore substantive, not ceremonial. For the catalog forms, the reviewer checks actor, target, direction, manner, result, tense or aspect, camera behavior, sound meaning, and final state in both languages. That declaration does not cover compiler-authored operation, authority, phase, camera, audio, or invariant wrappers.

The system must never report a declared human assertion as authenticated review or machine-proven equivalence.

The catalog's `user_attested` or `reviewer_attested` method is a declaration, not authentication. It does not prove reviewer identity, independence, fluency, or that review occurred. A publishing workflow must collect and verify the actual human approval separately; the compiler reports `catalog_linguistic_equivalence: human_asserted_not_machine_verified` and never upgrades it to a final-render or machine verdict.

## Stable entity names

Each entity has one non-empty English label and one non-empty Simplified Chinese label for a catalog. Labels must be distinct within each locale after comparison normalization. Event, audio, and invariant entries use the required entity tokens instead of pronouns.

The compiler does not infer `he`, `she`, `it`, `they`, `他`, `她`, `它`, `其`, or a similar alias. Repeating the stable name is preferable to changing the actor. Chinese subject omission is not allowed when the source event requires that entity token. Proper names that must remain literal should use the same reviewed bytes in both label entries.

Screen direction must state its reference frame. Use `screen-left`, `screen-right`, `subject-left`, or `subject-right`, with paired forms such as `画面左侧`, `画面右侧`, `主体左侧`, or `主体右侧`. Bare `left`, `right`, `左`, or `右` is ambiguous and fails semantic lint for event text.

## Causal phase grammar

The event graph owns order. Locale grammar makes that order legible without adding a new event or claiming that particular connectives expose model physics.

| Phase | English realization frame | Simplified Chinese realization frame |
|---|---|---|
| `initial_state` | `Initially, ...` | `初始时，……` |
| `trigger` | `From that initial state, ...` | `从该初始状态起，……` |
| `motion_path` | `As that motion continues, ...` | `随着该动作继续，……` |
| `contact_or_state_change` | `Then, ...` | `随后，……` |
| `primary_response` | `As a result, ...` | `因此，……` |
| `secondary_response` | `Next, ...` | `接着，……` |
| `follow_through` | `Afterward, ...` | `之后，……` |
| `settled_endpoint` | `Finally, ...` | `最终，……` |

The compiler adds only the phase frame. It does not add `gradually`, `逐渐`, acceleration, decay, impact strength, material deformation, or stillness unless that meaning exists in the reviewed paired entry. Chinese result complements such as `停住`, `停稳`, `散尽`, `落定`, or `保持静止` must describe the authored result, not decorate the sentence.

A settled endpoint must be written as a completed or held observable state in both languages. Recognized contradictions such as `continues moving` or `仍在移动` fail closed. The typed `settled_endpoint` phase plus bilingual review remains authoritative; lexical rejection cannot prove finality across all natural-language synonyms. This is a candidate prompt-contract consistency check, not a guarantee of generated physical accuracy.

## Camera and audio boundaries

Camera fields remain separate from audio fields. The linter rejects a bounded corpus of clear sound terms in camera rows and clear camera/framing terms in audio rows. The typed category and publishing review remain authoritative because a lexical denylist cannot prove domain purity across every synonym. This separation still protects parity and makes a failed take diagnosable without claiming exhaustive natural-language understanding.

Audio timing and audio meaning remain independent. An event can be linked to `on_trigger`, `during_motion`, `on_contact_or_state_change`, a response, follow-through, endpoint, or continuous timing while its semantic function remains dialogue, voiceover, sound effect, ambience, music, rhythm, or silence.

The retained evidence does not establish that English, Mandarin, or another language is universally superior for prompting or lip-sync. Any comparison must identify the exact prompt, spoken line, surface, operation, model version, voice path, region, and date.

## Exact dialogue is deferred

Scene-IR version 1 provides an audio `description`, source entity IDs, timing, and semantic function. It does not provide an exact utterance, a single authoritative speaker, spoken-language tag, delivery contract, or subtitle policy. A renderer must not convert that description into invented dialogue or translate it into a new line.

V7-07 therefore fails closed when an audio event is `dialogue` or `voiceover`. Later dialogue support requires a versioned semantic contract with:

- one resolved speaker for each line;
- an exact utterance;
- a spoken-language tag independent of prompt locale;
- event timing and turn order;
- an authorized voice path where relevant; and
- an explicit subtitle or post-production policy.

When dialogue support is added, the same spoken line must remain byte-exact between English and Chinese instruction variants. Translating the line for a localized dub creates a different semantic variant. Subtitles, captions, legal copy, and market text remain post-production deliverables unless a separately verified workflow explicitly supports them.

## Multi-shot rendering is deferred

The scene IR can order several shots and require cross-shot endpoint continuity, but version 1 does not state whether the transition is a hard cut, match cut, dissolve, or continuous camera move. It also does not choose between portable `Shot N` labels and a surface-specific Chinese timeline convention.

V7-07 compiles one shot only. A scene with more than one shot fails with a stable deferred-capability diagnostic. Later support requires a typed transition contract plus active-surface evidence. The compiler must not infer a cut from array order or invent timestamps.

## Surface and locale evidence boundary

Language realization and surface rendering are independent axes:

- the paired catalog decides how the same reviewed semantic unit is written in English and Simplified Chinese;
- the surface profile decides request transport and prompt-visible binding syntax; and
- current evidence decides whether the exact model, surface, operation, media combination, language behavior, and audio feature may be claimed.

A Chinese prompt does not imply a China-facing surface. An English prompt does not imply a global API. `zh-Hans` is a written locale, not proof that the spoken line is Mandarin. Mixed English camera terms are an explicit operator choice, not an automatic optimization. No locale selection bypasses safety, rights, moderation, or evidence expiry.

The compiler makes no locale-support judgment from the language used in a retained provider-syntax example. Provider syntax remains governed by the profile; natural-language behavior needs a separate test on the exact model, surface, operation, region, and date.

## Fail-closed boundary

Compilation stops on:

- invalid manifest, scene IR, catalog, prompt program, or binding set;
- stale scene or source hashes;
- missing, extra, duplicate, or reordered catalog entries;
- missing or mismatched entity tokens;
- duplicate localized entity labels or unstable pronouns;
- ambiguous direction;
- a non-final settled endpoint;
- camera/audio conflation;
- exact dialogue or voiceover under the version 1 contract;
- more than one shot;
- reference-like tokens, locators, secrets, or meta-instructions in locale text;
- unsupported or stale surface bindings;
- an expired evidence pin; or
- prompt-budget overflow.

The compiler never repairs these errors by translating, dropping a unit, selecting a different provider profile, renumbering a reference, trimming an opaque handle, or truncating the prompt.

## Language-layer and common transport repair index

Diagnostics are stable machine codes plus JSON pointers; input text is never echoed. The table below covers language-layer and common transport failures, not every inherited planner, scene, profile, or binding diagnostic. Upstream codes propagate unchanged; use the V7-05/V7-06 routing in [`V7_SURFACE_PROFILE_MIGRATION.md`](V7_SURFACE_PROFILE_MIGRATION.md), [`V7_REFERENCE_CAUSAL_MIGRATION.md`](V7_REFERENCE_CAUSAL_MIGRATION.md), and [`references/failure-atlas.md`](../references/failure-atlas.md). Use the pointer to locate the failing field, then apply the narrow repair below.

| Code | Meaning | Repair |
|---|---|---|
| `JSON_INVALID` | Input is not valid JSON. | Serialize one complete JSON object; do not send comments, trailing commas, or concatenated documents. |
| `JSON_DUPLICATE_KEY` / `JSON_NONFINITE_NUMBER` / `JSON_NUMBER_OUT_OF_RANGE` / `JSON_TOO_DEEP` / `JSON_TOO_LARGE` / `JSON_UTF8_REQUIRED` / `JSON_BOM_FORBIDDEN` | The JSON transport is ambiguous, non-portable, malformed, or outside the compiler resource envelope. | Serialize one UTF-8 JSON object with unique keys, finite bounded numbers, supported depth, no BOM, and an aggregate size at or below 64 MiB. |
| `TYPE_OBJECT_REQUIRED` / `OBJECT_FIELDS_INVALID` / `ARRAY_LENGTH_INVALID` | A closed object or array has the wrong type, field set, or length. | Regenerate the pointed contract from its schema; do not add convenience fields. |
| `PROFILE_CANDIDATE_REQUIRES_PREVIEW` | Candidate profiles were invoked without the mandatory non-activating preview gate. | Re-run locally with `--preview-candidate`; this still does not activate or submit a provider request. |
| `REFERENCE_MANIFEST_CONTRACT_INVALID` / `SCENE_IR_CONTRACT_INVALID` | An inherited V7-06 manifest or scene contract failed before language rendering. | Repair it with the upstream V7-06 schema and diagnostic pointer before building a catalog. |
| `PROFILE_EVIDENCE_EXPIRED` / `REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH` / `REF003_STRUCTURED_ROLE_USE_MISMATCH` | Candidate profile evidence is stale or structured frame roles disagree with typed authority/use. | Refresh evidence through the reviewed evidence workflow, or repair the four explicit frame-authority dimensions and role-aligned assets; never bypass the gate in prose. |
| `COMPILE001_REQUEST_CONTRACT_INVALID` | Wrong top-level version or envelope. | Use the exact documented keys and integer schema version 1. |
| `LANG001_UNSTABLE_SUBJECT_ALIAS` | A localized unit uses a pronoun or unstable subject alias. | Restore the required closed entity token and stable locale label. |
| `LANG003_LOCALIZATION_SET_MISMATCH` | Catalog keys are missing, extra, or out of canonical order. | Rebuild the ordered set from the exact scene IR. |
| `PARITY001_SEMANTIC_TRACE_MISMATCH` | Locale keys, entity substitutions, or an emitted value span diverged. | Repair the named catalog unit or renderer; never copy one finished prompt over the other. |
| `PARITY002_LOCALIZED_UNIT_ORDER_MISMATCH` | English and Chinese semantic-unit order differs. | Restore the shared prompt program order. |
| `PRM001_EVENT_COVERAGE_INVALID` / `PRM002_CAUSAL_ORDER_INVALID` | An event is absent, extra, or reordered. | Rebuild from the validated causal event graph. |
| `PRM003_ALIAS_COLLISION` / `PRM004_ENTITY_AMBIGUOUS` | Labels collide, entity tokens drift, or direction lacks a frame. | Use distinct labels, the exact required token set, and screen/subject/world direction. |
| `PRM007_CAMERA_AUDIO_CONFLATED` | Camera prose contains audio direction or audio prose contains camera direction. | Move each instruction to its owned catalog unit. |
| `PRM008_TIME_RANGE_UNEVIDENCED` | Authored locale text invents exact seconds, frames, or timestamps. | Express causal phase order without exact timing. |
| `PRM009_BINDING_CORE_MISMATCH` / `REF001_BINDING_ORDER_MISMATCH` | Binding identity, media, profile, operation, or order drifted. | Regenerate the binding-only set from manifest `selection_order`. |
| `PRM010_SURFACE_SEMANTIC_DRIFT` | Planning and locale render passes used different surface evidence. | Stop and rerun from one unchanged profile registry snapshot. |
| `PRM011_META_INSTRUCTION` | Catalog text or a text/handle composition resembles an instruction override. | Remove the meta-instruction; do not hide it in another field. |
| `PRM012_SECRET_OR_LOCATOR` | Secret-shaped or URL/path-like text reached the compiler. | Remove credentials and locators from semantic and handle inputs. |
| `PRM013_UNICODE_UNSAFE` | Authored text is non-NFC or contains unsafe controls, default-ignorables, or visually blank mask characters. | Normalize authored catalog text to NFC and remove those masks; opaque handles are rejected at the same boundary without rewriting their bytes. |
| `PRM014_PROGRAM_HASH_MISMATCH` | Prompt-program or source lineage was mutated. | Rebuild the program from the exact canonical validated manifest, scene, and catalog content. |
| `PRM015_BUDGET_EXCEEDED` | Typed segments or final prompt exceed the compiler budget. | Reduce semantic density or split the work; the compiler will not truncate. |
| `PRM017_ENDPOINT_NOT_FINAL` | The settled endpoint is ongoing, negated, merely future, or carries contradictory held/persistent dynamics. | State one observable completed condition; express terminal dynamics explicitly as zero, absent, transferred, absorbed, dissipated, or damped, and move unrelated ambient motion to another unit. |
| `PRM021_DIALOGUE_TEXT_REQUIRED` | Dialogue/voiceover lacks the later exact-line contract. | Keep it outside V7-07 pending a typed speaker/language/utterance contract. |
| `PRM022_MULTI_SHOT_DEFERRED` | More than one shot requires a transition contract. | Compile one shot at a time pending typed multi-shot support. |
| `PRM023_EVENT_TEXT_DUPLICATE` | Two events use the same localized state change. | Author distinct observable changes for the distinct events. |
| `PRM025_LOCALE_CATALOG_INVALID` | Catalog shape, attestation declaration, source hash, text, or endpoint contract is invalid. | Repair the pointed catalog field and renew the declaration for the resulting canonical catalog hash. |

Catalog worksheet generation is deliberately not hidden inside compilation. A later usability change should add a separately versioned, non-compilable draft artifact that exposes ordered keys and source hashes for human completion; until then, operators must build the closed catalog from `_expected_catalog`-equivalent tooling and validate it before use. This limitation is explicit so an incomplete draft cannot be mistaken for a reviewed bilingual catalog.

## Claims this migration does not make

V7-07 does not:

- describe Seedance's hidden text encoder, attention, training distribution, denoising, physics, or audiovisual architecture;
- prove that Chinese is more compact, more controllable, or better understood than English;
- prove translation quality from matching IDs or placeholders;
- guarantee prompt adherence, physical accuracy, lip-sync, endpoint fidelity, or reference transfer;
- activate a provider profile or submit generation requests;
- add exact dialogue or multi-shot compilation; or
- extend evidence beyond its recorded model, surface, operation, region, or expiry.

The result is a reviewable language-rendering boundary: one semantic plan, two catalog-driven natural-language realizations, a machine-checked resolved-key trace, an explicit catalog-attestation status, and no hidden translation step. Human approval of the final prompt pair remains a release task.
