# Surface Prompt Profiles

<!-- fixed_handle_audit: evidence_example -->

Use this reference before any prompt contains a media binding. Seedance has no evidenced universal reference token. The binding contract is:

```text
semantic binding ID
→ exact captured handle, evidence-pinned media ordinal, or structured media role
→ surface-specific renderer
```

The semantic plan never owns provider syntax. Do not turn an asset ID, URL, filename, upload order, or provider handle into prompt text unless the selected operation profile explicitly defines that mapping.

## Two Independent Axes

Every operation resolves both axes independently:

1. **Request transport:** how media enters the request, such as surface-owned attachments, typed media arrays, ordered content objects, or structured frame roles.
2. **Prompt binding:** whether prompt prose uses an exact surface-captured opaque handle, a profile-derived media ordinal, or no visible handle.

A request can use structured media arrays and still require prompt-visible handles. Conversely, structured `first_frame` and `last_frame` roles need no invented prompt token.

## Current Candidate Profiles

The checked-in profiles are evidence projections, not activated provider guarantees. `profiles/profile-index.json` keeps `activation_enabled: false`; all provider profiles have `status: candidate` and `runtime_enabled: false`.

| Profile and operation | Request transport | Prompt binding | Current boundary |
|---|---|---|---|
| `byteplus.modelark` / `reference_generation` | unresolved by retained evidence | exact externally captured handle | an observed `@Image 1` example is not a token-construction rule |
| `fal.reference-to-video` / `reference_generation` | typed image/video/audio arrays | profile derives compact `@Image{n}`, `@Video{n}`, or `@Audio{n}` from one-based position within that media array | caller-supplied prompt handles are rejected |
| `volcengine.ark` / `reference_generation` | ordered content objects | profile derives evidence-pinned `图片{n}` from one-based image position | audio/video label bytes are unsupported pending stronger evidence; Asset ID is never the prompt reference |
| `volcengine.ark` / `first_last_frame` | structured `first_frame` and `last_frame` roles | none | never add a textual handle merely because an image is present |

Unknown profiles and operations fail closed. Do not select a “similar” provider profile. When the actual surface is unknown, ask for the surface and preserve any supplied handle as opaque planning data; do not claim the surface accepts it and do not invent a fallback token.

## How To Choose The Right Reference Binding

1. Select the exact surface and operation; the model name alone is insufficient.
2. Give each asset a stable ASCII `binding_id` and a media type.
3. Preserve the request order. A derived profile counts positions independently inside each media type, never across the combined list.
4. Let the renderer produce the prompt-visible value. Do not type a candidate API tag yourself.

For a fal request ordered as image `hero`, video `motion`, image `environment`, audio `tempo`, the independent counters resolve to `hero → @Image1`, `motion → @Video1`, `environment → @Image2`, and `tempo → @Audio1`. Reordering the image array changes which image owns each image ordinal. The Volc candidate currently resolves only images: its first and second image content objects become `图片1` and `图片2`; audio/video fail closed until their exact labels are retained. BytePlus is different: copy the exact visible external handle because the retained example does not prove a constructor. Structured first/last-frame roles use no tag.

## Binding Rules

- Keep valid opaque handles byte-for-byte, including spacing, case, brackets, at-signs, Chinese text, decomposed Unicode, and interface-generated wording.
- Never trim, normalize, translate, recase, renumber, repair spacing, or add an `@` prefix.
- For a derived API profile, omit `prompt_visible_handle`. The renderer owns the exact formatter and ordinal; a supplied override is an error.
- Keep the strict ASCII internal `binding_id` separate from the prompt-visible handle.
- Use typed text and binding segments. Never find or replace placeholders inside prose.
- Keep whitespace or punctuation at every text/binding boundary. A binding followed by `：锁定主体身份。` is valid; a binding followed immediately by `99 controls identity` is rejected because it could mutate the provider handle.
- Never type provider-shaped numbered reference syntax in a text segment. The selected binding segment is the only authority for an opaque or derived prompt-visible handle.
- Reject ambiguous control and bidirectional-display characters instead of silently rewriting them.
- If a profile is missing, disabled, stale, or unsupported, stop and request a current surface binding.

## Renderer Contract

`scripts/render_surface_bindings.py` accepts a closed JSON binding plan. A prompt-visible reference is a typed segment, not a magic substring:

```json
{
  "$schema": "https://github.com/Emily2040/seedance-2.0/schemas/binding-plan.schema.json",
  "schema_version": 1,
  "profile_id": "byteplus.modelark",
  "operation": "reference_generation",
  "segments": [
    {"kind": "binding", "binding_id": "product"},
    {"kind": "text", "value": " controls product geometry; preserve its label."}
  ],
  "bindings": [
    {"binding_id": "product", "media_type": "image", "prompt_visible_handle": "<exact handle copied from this surface>"}
  ]
}
```

The angle-bracket text above explains where the exact interface value belongs; it is not literal syntax and must never be sent as a handle. Candidate profiles can currently be exercised only with `--preview-candidate`. That flag does not activate them, bypass expiry, or claim production support.

For a structured first/last-frame operation, the bindings carry `structured_role` values and the prompt contains only transition prose. The renderer emits role records and no prompt token.

For fal, the same semantic binding is submitted without a prompt handle and resolves by media type and array position:

```json
{
  "$schema": "https://github.com/Emily2040/seedance-2.0/schemas/binding-plan.schema.json",
  "schema_version": 1,
  "profile_id": "fal.reference-to-video",
  "operation": "reference_generation",
  "segments": [{"kind": "binding", "binding_id": "product"}],
  "bindings": [{"binding_id": "product", "media_type": "image"}]
}
```

The first image binding renders as compact `@Image1`. On the Volc candidate profile the equivalent first image renders as `图片1`; cross-surface spelling is intentionally different.

Do not add a manual value such as `@Image99` before or after that typed segment. The renderer rejects the text token, including when its pieces are split across adjacent text segments, and verifies that every provider-shaped reference in the final prompt came entirely from an authoritative binding span.

## Evidence And Expiry

Each model and operation pins the exact claim bytes and exclusive expiry date that support its projection. Rendering stops when any effective pin reaches `today >= expires_at`, and output lists provenance from both layers. Refreshing a date without retaining and reviewing current evidence is not allowed. A model-level capability never enables a provider operation, and no Seedance 2.5 profile exists until official model and surface contracts are retained and reviewed.
