# Prompt Compiler

The compiler turns validated internal project state into typed natural-language segments for the current clip only. JSON or YAML can organize planning, but the final prompt stays readable prose unless the user explicitly asks for structured output. Compilation is not provider activation and does not translate arbitrary scene-IR prose.

## Inputs

- project state;
- current clip contract;
- surface prompt profile;
- reference transfer contract;
- observed source state for continuations;
- completed and reserved beats;
- continuity locks and allowed changes;
- prompt budget.

The compiler produces typed text and binding segments before the final join. The selected surface operation owns request transport and prompt-visible syntax; the scene plan never does. Load `[ref:surface-prompt-profiles]` and fail closed when the profile, operation, required external handle, evidenced formatter, or structured role is unavailable. The V7 contracts are split deliberately: `scripts/prompt_compile.py` realizes a closed language catalog, while `scripts/semantic_lint.py` checks semantic coverage and cross-language structural parity.

## Compile Order

1. Lineage: name `project_id`, `clip_id`, and parent in the user-facing contract or capsule; omit them from the final prompt when they would waste prompt budget.
2. Source role: identify semantic binding IDs, media types, external handles only where required, structured roles, and what each controls. Derived ordinal syntax stays out of the scene plan.
3. Actual opening state: use observed footage for continuations and planned state only for first clips. When the source clip or final frame is attached, bind it semantically and let the selected operation preserve, derive, or omit prompt-visible syntax; state only what the source cannot carry.
4. Current clip action: one narrative job with an endpoint.
5. Felt intent: the clip's one-line `felt_intent` - what the viewer should feel or notice - is the directing engine's intention made persistent in state. It never ships to Seedance as an abstract emotion word; it compiles as the specific camera, light, performance, and sound choices that carry it.
6. Camera and motion phase: include inherited vectors when continuity matters.
7. Light, environment, style, and audio: include only state-critical or intent-critical clauses.
8. Exclusions: completed beats and reserved future beats.
9. Endpoint: the completed state this clip must reach.

## Source-Carries-State Rule

When an accepted source is attached as a reference, the source carries the state and the text carries the delta. Do not re-describe in prose what the attached source already shows: prose restatement spends budget on information the model already has, and where the words disagree with the pixels, the prose becomes a drift instruction.

- Accepted clip attached as a video reference: the clip carries static and dynamic state. A typed binding segment is resolved by the surface policy when that operation uses prompt-visible binding; text carries the role, current action and endpoint, exclusions, and only the continuity locks at known drift risk.
- Accepted prior clip's final frame attached as the next shot's opening source: the frame carries that opening static state only. Text must still carry what a still cannot show - open motion vectors, camera movement phase, and audio phase - then the current action, endpoint, and exclusions.
- Structured first/last-frame target operation: the first-frame binding carries the initial visible state and opening framing; the last-frame binding carries the settled endpoint and end framing. Text carries the transition, intermediate causal events, camera path/speed/subject relationship, audio, invariants, and exclusions without restating those four static fields.
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

For V7-07's supported non-dialogue scope, resolved-key parity means both locales resolve the same ordered event, entity-label, camera, audio, and invariant catalog atoms from one semantic program. Each atom is bound to its semantic unit ID, one exact typed-text segment, an inclusive-start/exclusive-end UTF-8 byte range, and the resolved-value hash; runtime verifies the addressed slice after locale rendering returns. A separate hash-bound binding-unit trace maps every prompt-visible binding to its exact authority unit and rejects moves or duplicates. UTF-8 byte offsets are not JavaScript UTF-16 string indexes, so a browser verifier must slice `TextEncoder` bytes. Runtime checks also preserve the same dependencies, reference authority, and bindings. These checks cannot prove that two sentences are good translations. A bilingual human assertion covers the catalog forms only; compiler-authored wrappers and final prompts still require publishing review. `compiler_sha256` binds the exact executing compiler bytes; `compiler_toolchain_sha256` binds the compiler, planner, binding renderer, scene checker, and semantic linter bytes. A later typed dialogue contract would also need byte-exact utterance preservation, but V7-07 rejects dialogue and voiceover before rendering.

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

The generic scene-IR audio `description` is not an exact dialogue contract. V7-07 fails closed on `dialogue` and `voiceover` because scene-IR version 1 has no exact utterance, single authoritative speaker, spoken-language tag, delivery contract, or subtitle policy. Later dialogue support requires those versioned fields. Prompt locale and spoken language remain independent; the same utterance must stay byte-exact across English and Chinese instruction variants, while a translated dub is a different semantic variant.

V7 language rendering is initially single-shot. Multiple scene-IR shots do not state whether the transition is a hard cut, match cut, or continuous move. Until a typed transition contract is available, the compiler fails closed instead of inventing `Shot N` labels or Chinese timeline syntax.

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
