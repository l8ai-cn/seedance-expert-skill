# V7-05 model/surface profiles and typed binding renderer

V7-05 removes the universal-token rule without activating provider guidance. It projects the V7-04 evidence registry into one model profile, three operation-scoped surface profiles, a strict typed binding plan, and an offline renderer that never guesses syntax.

## Decision

The invariant is:

```text
semantic binding ID + media type
→ exact captured handle, evidence-pinned media ordinal, or structured request role
→ surface-specific render
```

Request transport and prompt-visible binding are independent. An external UI may supply an opaque handle; an API profile may derive an evidenced media ordinal from request position; structured first/last-frame roles require no prompt-visible handle.

## Shipped boundary

- `profiles/models/seedance-2.0-model.json` contains model-level projections only. It cannot enable a provider operation.
- `profiles/surfaces/byteplus-modelark.json` preserves an exact handle captured from the external surface. The observed spaced example is not a construction rule, and the retained evidence does not establish request transport.
- `profiles/surfaces/fal-reference-to-video.json` represents typed media arrays and derives compact `@Image{n}`, `@Video{n}`, and `@Audio{n}` bindings from each media type's one-based array position. Caller overrides are forbidden.
- `profiles/surfaces/volcengine-ark.json` derives only the evidence-pinned image form `图片{n}` for ordered-content reference generation and separates structured first/last-frame roles. Audio/video labels remain unsupported until their exact bytes are independently retained; Asset IDs are never inserted into prose.
- `profiles/profile-index.json` byte-pins every profile, fails unknown profiles closed, and keeps activation disabled.
- `scripts/render_surface_bindings.py` joins typed text/binding segments, emits abstract request-binding records, and performs no network calls or file writes.

No Runway, Replicate, router, or Seedance 2.5 profile is included because the retained V7-04 registry does not establish those operation contracts.

## Candidate-only activation state

All model and provider profiles are `candidate` and `runtime_enabled: false`. The index and evidence policy both keep activation disabled. Normal rendering refuses candidates; `--preview-candidate` exists only to inspect and test a projection, labels its output as preview, enforces evidence expiry, and does not claim production support.

The critical provider claims remain pending independent review. The global, fal, and Volcengine binding claims expire on the exclusive date 2026-07-18 unless successor evidence is retained and reviewed. The runtime renderer has no public backdating switch.

## Input contract

A binding plan contains:

- exact `profile_id` and `operation`;
- ordered typed segments: literal text or an internal ASCII `binding_id`;
- binding records with media type and, only for an opaque external profile, an exact `prompt_visible_handle`; derived API profiles accept no caller handle; structured operations use a role.

The renderer never discovers bindings inside text. Strings that resemble `${name}`, `{name}`, or `{{binding:name}}` remain literal text, while provider-shaped numbered reference syntax is forbidden in text segments and may appear only through an authoritative binding segment. Every text/binding boundary must contain whitespace or punctuation so surrounding text cannot mutate a rendered handle. For example, a binding segment followed by `：锁定主体身份。` is valid; a binding followed immediately by `99 controls identity` or a manually typed numbered provider handle fails closed. Opaque prompt-visible handles may contain ordinary Unicode, leading/trailing/internal spaces, brackets, quotes, backslashes, multiple at-signs, decomposed characters, CJK, Arabic text, and valid emoji/ZWJ sequences. They are emitted unchanged. Derived ordinals are constructed only from the evidence-pinned formatter in the selected profile and the renderer-computed per-media position.

Ambiguous controls, line separators, bidi formatting controls, BOM characters, lone surrogates, duplicate IDs, and exact/NFC/casefold/ZWJ-equivalent handle collisions fail closed. Errors report stable codes and JSON pointers without echoing handle, media, URL, or secret values.

## Output contract

The result separates:

- `rendered_prompt`;
- abstract `request_bindings` with per-media positions or structured roles;
- surface and model profile IDs;
- exact profile hash;
- request-transport kind;
- preview/candidate state;
- the earliest expiry and claim IDs across both the model and operation evidence layers.

It emits no media URL, API key, file path, provider asset ID, raw request body, or media bytes.

## Runtime migration

V7-05 surgically changes the routing, compiler, continuation, first/last-frame, multilingual, and public quickstart boundaries. Fixed literal handles remain only in six explicitly quarantined runtime Markdown files as machine-marked fixture values, contrast cases, or an observed surface example; tests pin that closed set. The V7-04 runtime is a historical baseline; the final V7-05 file count and integrity hash are calculated by the runtime packager rather than maintained as prose.

This PR intentionally does not:

- replace one-primary-role planning with the V7 authority matrix (V7-06);
- migrate project state or generation-run schemas (later compiler/state work);
- add causal physics IR or language renderers;
- collapse the 28 subskills;
- rebuild the frontend or images;
- approve evidence or activate provider profiles.

## Validation

The focused suite covers strict JSON, candidate and expiry gates, profile/hash/link tamper, unknown operation cross-products, structured-role isolation, per-media request positions, secret noninterference, literal-placeholder non-parsing, deterministic subprocess output, every forbidden control class, a fixed adversarial corpus, and 10,000 seeded Unicode handle round trips. The final gate runs the focused suite, the complete repository suite, runtime build/install/rollback, and ten consecutive stress passes.
