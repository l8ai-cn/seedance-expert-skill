# Prompt Compiler

This reference separates a conceptual project-to-prompt planning order from the executable V7-07 paired renderer. JSON or YAML can organize planning, but the final prompt stays readable prose unless the user explicitly asks for structured output. Compilation is not provider activation and does not translate arbitrary scene-IR prose.

V7-07 remains byte-stable and accepts exactly a version-1 `reference_manifest`, `scene_ir`, `surface_binding_set`, and `realization_catalog`. It does not ingest project state or a clip contract and cannot claim project-state provenance. Project-state-v2, owner-scoped motion handoffs, typed local endpoint modes, dialogue, multi-shot transitions, and surface-exact timing are not silently flattened into that renderer. Every v2 clip remains `compile_required: true`; never hand-edit a V7-07 paired render while retaining its provenance claim.

V7-09 adds a separate offline candidate-preview stack for exact dialogue and explicit editorial cuts. It does not modify or auto-upgrade V7-07, clear V7-08's execution blocker, activate a provider, or prove returned audio/video adherence.

## Conceptual planning inputs

- project state;
- current clip contract;
- surface prompt profile;
- reference transfer contract;
- observed source state for continuations;
- completed and reserved beats;
- continuity locks and allowed changes;
- prompt budget.

These inputs guide a human or future state-aware compiler; they are not the stdin contract of `scripts/prompt_compile.py`.

## Executable V7-07 inputs

The V7-07 request contains only `schema_version`, `reference_manifest`, `scene_ir`, `surface_binding_set`, and `realization_catalog`. The renderer produces typed natural-language segments and binding segments before the final join. The selected surface operation owns request transport and prompt-visible syntax; the scene plan never does. Load `[ref:surface-prompt-profiles]` and fail closed when the profile, operation, required external handle, evidenced formatter, or structured role is unavailable. The V7 contracts are split deliberately: `scripts/prompt_compile.py` realizes a closed language catalog, while `scripts/semantic_lint.py` checks semantic coverage and cross-language structural parity.

## V7-09 AV candidate-preview inputs

The V7-09 path uses `scene-ir-v2`, a closed `surface-av-policy`, a policy-hash-bound `surface-binding-set-v2`, a V2 realization catalog, and a V2 compile request/program/render. It is exact-version only and remains offline. No trusted AV policy binding ships in this stage. The checked-in supported policy is an internal/test fixture, default CLI use rejects it, and any explicit fixture preview is visibly labeled in both status and diagnostics. Scene IR v2 carries state binding, one take structure, explicit shots and events, typed editorial transitions, speakers, exact audio events, subtitle policy, invariants, fragilities, acceptance tests, and fallbacks.

The policy—not user prose—controls whether the renderer may emit a provider-evidenced shot grammar or timing form. Unknown dialogue, voice-reference, multi-shot, subtitle, or exact-range support fails closed. Prompt locale does not select a surface or region.

Exact dialogue bypasses localization. Each line has one resolved speaker, byte-exact NFC utterance, UTF-8 hash, spoken-language tag, turn order, localized delivery intent, explicit overlap/lip-sync control, event-bound timing, voice mode, and authorization binding. Speaker labels remain comparison-distinct per locale. Authorized voice assignment is request-carried as speaker/authority/audio-binding provenance and never converted to prompt prose. Both locale renders prove the same utterance slice and hash. A translated dub is a new semantic variant. `post_dub` and post subtitles are post-only units and cannot leak into the prompt.

`single_continuous_take` has one shot and no transitions. `edited_multi_shot` has at least two shots and exactly one adjacent transition per boundary. Hard cut, match cut, dissolve, and fade are editorial types; continuous camera movement stays inside a shot. Array order never invents a cut or a causal dependency.

The V7-09 output is a candidate preview, not a provider request or generation receipt. Use the hash-bound AV review companion on returned video before making any claim about word accuracy, speaker assignment, spoken language, lip sync, timing, sound, cuts, continuity, or unexpected text. A final frame cannot prove audio.

## Conceptual planning order

1. Lineage: name `project_id`, `clip_id`, and parent in the user-facing contract or capsule; omit them from the final prompt when they would waste prompt budget.
2. Source role: identify semantic binding IDs, media types, external handles only where required, structured roles, and what each controls. Derived ordinal syntax stays out of the scene plan.
3. Actual opening state: use observed footage for continuations and planned state only for first clips. When the source clip or final frame is attached, bind it semantically and let the selected operation preserve, derive, or omit prompt-visible syntax; state only what the source cannot carry.
4. Current clip action: one narrative job with an endpoint.
5. Felt intent: the clip's one-line `felt_intent` - what the viewer should feel or notice - is the directing engine's intention made persistent in state. It never ships to Seedance as an abstract emotion word; it compiles as the specific camera, light, performance, and sound choices that carry it.
6. Camera and motion phase: include inherited vectors when continuity matters.
7. Light, environment, style, and audio: include only state-critical or intent-critical clauses.
8. Exclusions: completed beats and reserved future beats.
9. Endpoint: the completed state this clip must reach.

## Source-state authority heuristic

When an accepted source is attached and explicitly assigned opening-state authority, ask the selected operation to preserve those declared dimensions and let text describe the delta. Avoid unnecessary visual restatement; this simplifies the instruction and reduces source/prose conflict, but it does not prove that the model will preserve the source. When words and pixels disagree, treat the request as ambiguous and repair it before generation rather than predicting a specific drift mechanism.

- Accepted clip attached as a video reference: request the declared visible static and dynamic opening-state dimensions from the clip. A typed binding segment is resolved by the surface policy when that operation uses prompt-visible binding; text states the role, current action and endpoint, exclusions, and necessary review locks.
- Accepted prior clip's final frame attached as the next shot's opening source: assign only visible static opening-state dimensions to the still. State any known open motion, camera movement phase, and audio phase from a supporting clip or user attestation; otherwise mark them unknown.
- Structured first/last-frame target operation: assign initial visible state/opening framing to the first-frame request role and endpoint/end framing to the last-frame role. Text requests the transition, intermediate events, camera path/speed/subject relationship, audio, invariants, and exclusions without redundantly restating those four static fields.
- No visual source attached: write the observed opening state in prose, as for a cross-session continuation where the footage is unavailable.

## Natural-Language Prompt Rules

Do not emit internal JSON to Seedance. Do not include all future clips. Do not describe a planned ending as if it happened. Do not replay completed actions. Do not perform reserved later actions. Do not invent deterministic guarantees. Do not re-describe content an attached source reference already shows.

Use clip-scope language:

- "Begin with..." for observed opening state.
- "Continue the same..." only when source footage exists.
- "This clip only..." for the current narrative job.
- "Stop when..." for endpoint control.
- "Do not yet..." for reserved future beats.

## V7 English/Chinese realization

The V7 scene IR contains a validated causal graph but still carries free prose in entity, event, camera, audio, and invariant descriptions. A compiler must not treat those strings as a language-neutral representation and must not silently machine-translate them. One paired realization catalog supplies reviewed `en` and `zh-Hans` forms keyed to the same semantic IDs and bound to the canonical scene-IR hash.

For V7-07's supported non-dialogue scope, resolved-key parity means both locales resolve the same ordered event, entity-label, camera, audio, and invariant catalog atoms from one semantic program. Each atom is bound to its semantic unit ID, one exact typed-text segment, an inclusive-start/exclusive-end UTF-8 byte range, and the resolved-value hash; runtime verifies the addressed slice after locale rendering returns. A separate hash-bound binding-unit trace maps every prompt-visible binding to its exact authority unit and rejects moves or duplicates. UTF-8 byte offsets are not JavaScript UTF-16 string indexes, so a browser verifier must slice `TextEncoder` bytes. Runtime checks also preserve the same dependencies, reference authority, and bindings. These checks cannot prove that two sentences are good translations. A bilingual human assertion covers the catalog forms only; compiler-authored wrappers and final prompts still require publishing review. `compiler_sha256` binds the exact executing compiler bytes; `compiler_toolchain_sha256` binds the compiler, planner, binding renderer, scene checker, and semantic linter bytes. V7-07 still rejects dialogue and voiceover before rendering; only the separate V7-09 V2 path can carry the new exact-line contract.

For `first_last_frame`, do not restate the four static fields assigned to the structured request: initial state and opening framing belong to the first-frame binding; settled endpoint and end framing belong to the last-frame binding. They remain catalog-validated and hash-bound in the prompt program. The render records their exact semantic key, unit, binding ID, and role under `request_carried`, while semantic traces and atoms cover only prose actually emitted. This records declared provenance; it does not verify frame pixels.

Use stable entity names in every event. Do not infer `he`, `she`, `他`, or `她`, and do not omit a Chinese subject when omission makes the actor ambiguous. Render phase order with conservative locale grammar:

| Causal phase | English connective | Chinese connective |
|---|---|---|
| initial state | `Initially, ...` | `初始时，……` |
| trigger after the opening state | `From that initial state, ...` | `从该初始状态起，……` |
| motion path | `As that motion continues, ...` | `随着该动作继续，……` |
| decisive change | `Then, ...` | `随后，……` |
| primary response | `As a result, ...` | `因此，……` |
| later response or follow-through | `Next, ...` or `Afterward, ...` | `接着，……` or `之后，……` |
| settled endpoint | `Finally, ...` | `最终，……` |

Do not add `gradually` or `逐渐` from phase alone. A gradual or decaying modifier must be present in the aligned semantic realization. The endpoint must express the authored completed or held state; the compiler must not invent stillness.

The generic scene-IR audio `description` is not an exact dialogue contract. V7-07 fails closed on `dialogue` and `voiceover` because scene-IR version 1 has no exact utterance, single authoritative speaker, spoken-language tag, delivery contract, or subtitle policy. V7-09 supplies those fields in a separate contract. Prompt locale and spoken language remain independent; the same utterance stays byte-exact across English and Chinese instruction variants, while a translated dub is a different semantic variant.

V7-07 rendering remains single-shot. Multiple version-1 scene-IR shots do not state whether the transition is a hard cut, match cut, dissolve, fade, or one continuous camera move, so that compiler still fails closed. V7-09's separate typed-transition path may render only the closed grammar selected by its surface policy; it never invents `Shot N` labels or Chinese timeline syntax from prompt language.

Missing locale forms, extra catalog IDs, placeholder mismatch, ambiguous entity names, unresolved dialogue, reference-like text tokens, unsupported surface bindings, prompt-budget overflow, or a stale catalog hash all fail closed. Meta-instruction, timing, alias, endpoint, and camera/audio lexical guards cover a bounded regression corpus; they are defense in depth and do not prove the meaning or safety of arbitrary natural language. Compiler input has a 64 MiB aggregate UTF-8 ceiling and returns `JSON_TOO_LARGE` above it; schema maxima are not a promise that every maximum can be combined in one envelope. Never truncate a prompt because truncation can remove one side of the semantic contract.

Both locales render through the same selected surface binding profile. The compiler does not infer locale support from the language used in a provider-syntax example. Keep provider syntax byte-exact and test natural-language behavior on the exact active surface and operation.

## Compression

When the prompt must shrink, preserve in this order:

1. Typed bindings and selected surface policies, plus role boundaries.
2. Actual opening state the attached source cannot carry.
3. Current action and endpoint.
4. Felt-intent carriers: the specific light, performance, and sound clauses that make the viewer feel what this clip exists to make them feel.
5. Continuity locks.
6. Completed beat exclusions.
7. Reserved beat exclusions.
8. Camera or open motion vector.
9. Audio phase.

Delete generic style boosters, duplicate adjectives, future story summary, background visible in references, secondary actions, and speculative internal notes first. When a visual source is attached, opening-state prose that repeats the source is deleted before anything else on this list. Felt-intent carriers are not "speculative emotional labels": the label never ships, but its carriers ship as concrete visible choices, and they outrank locks and exclusions because a continuity-correct, affect-flat clip is a failed clip that costs a retake anyway.
