# Reference Transfer Contract

<!-- fixed_handle_audit: contrast_only -->

Use this reference when images, videos, audio, previous clips, final frames, or interface tags appear in a sequence.

## Exact Binding Rule

Keep the semantic `binding_id` separate from the surface binding. When a profile requires an externally supplied opaque handle, preserve it byte-for-byte. Never invent, normalize, translate, reformat, renumber, correct spacing, change case, or add a prefix. A value such as `@Image1`, `@Image 1`, `[Video 1]`, or a Chinese/interface-generated name is opaque; its spelling proves nothing about another surface. Collision checks only treat recognized ordinal spellings such as `@Image1`, `@Image 1`, and `@Image01` as one review identity so two different bindings cannot claim an ambiguous tag; emitted bytes remain untouched. Derived profiles reject caller handles and construct only their pinned formatter.

Load `[ref:surface-prompt-profiles]` and render typed text/binding segments through the selected operation profile. Never parse placeholder-looking text. When the API uses structured media roles, keep those roles out of prompt prose and never substitute an asset ID, URL, or filename as a token.

## Authority Separation

Resolve authority for each `(target, dimension)` pair. Relevant dimensions are identity, face detail, wardrobe, product/object geometry, environment, visual style, visible opening state, opening composition, subject motion, camera motion, timing/rhythm, audio/voice, endpoint, endpoint framing, and text/logo treatment.

Exactly one asset wins each applicable target/dimension. One asset may win several dimensions; priority, confidence, media type, filename, and upload order never break a tie. Every other asset that could influence that dimension must be explicitly excluded, and every included asset must own at least one necessary dimension.

State what transfers and what must not transfer. Treat identity, motion, camera, environment, style, audio, and logo bleed as review risks, not an assumed priority mechanism. Record future-action leakage separately as a clip-scope failure; an asset cannot gain authority over a reserved beat.

Legacy version-1 project-state `tag` and single-role values remain readable compatibility input only. A non-destructive version-2 migration replaces them with semantic binding IDs and media provenance while target/dimension authority and surface policy remain unresolved until later hash-bound planning. Legacy values are never authority decisions, surface bindings, or prompt-visible tokens.

## Appearance Versus Structured Frame Roles

An appearance image controls only its declared dimensions. It is not an opening or endpoint frame unless the exact selected operation supports that structured role and the request assigns it.

For a verified first/last-frame operation, the first role must explicitly win both `opening_state` and `opening_composition`; the last role must explicitly win both `endpoint` and `endpoint_framing`. Those roles stay in request structure, not prompt tokens. The four dimensions are a local planning contract. Volcengine evidence establishes role designation only; it does not prove the declared frame content, promise exact endpoint fidelity, or establish support on another surface.

## Continuity Source Versus Motion Reference

A canonical identity reference owns only the targets/dimensions assigned to it in the local authority contract. An accepted previous clip can own declared transient opening-state dimensions. A donor video can own subject motion, camera motion, or timing only when explicitly assigned. These declarations state requested authority and exclusions; they do not prove provider priority or successful transfer. Do not let a donor overwrite character identity, wardrobe, product geometry, environment, style, text/logo treatment, audio, or accepted state unless it is the named winner for that exact target/dimension.

## Multi-Subject Selector

When a reference contains multiple subjects, identify the intended subject by position, tag, role, or visible feature. Do not assume the central or largest subject is correct when the user has not said so.

## Transfer And Exclusion Clause

Every reference should compile as a typed binding segment followed by a target-and-dimension transfer clause:

`for [target], controls [dimension list]; exclude [dimension list] from this reference.`

The surface renderer inserts a binding before that clause only when the active operation uses `opaque_external_handle` or `derived_media_ordinal`. Opaque values are preserved; ordinals are derived from the selected profile and request position. The bracketed words above are editorial fields, not prompt tokens.

Use only owned, licensed, public-domain, stock, self-recorded, or clearly authorized references for protected identity, voice, brand, logo, or performance transfer. Track media-use rights separately from likeness, voice/performance, music, and brand/logo authorization; one rights assertion cannot stand in for the others.

## Causal Observability Boundary

Reference authority does not prove that the requested event is stageable. For an interaction-heavy shot, separately order the initial state, trigger, decisive contact or state change, visible response, follow-through, and clip endpoint. Record the intended camera coverage for the before-state, change, response, and endpoint. This is a declared observability map; software can validate its event links but cannot prove visibility in generated pixels.

Motion and endpoint state are owner-scoped. Record subject, prop, camera, and environmental motion independently, and classify the endpoint as `held_static`, `dissipated_or_resolved`, `completed_with_motion`, `frame_exit`, `cyclic_phase_boundary`, or `open_handoff`. A stopped product does not require rain or camera motion to stop. This causal plan remains a production heuristic and acceptance checklist, not a claim about Seedance's hidden architecture or guaranteed physical simulation.

When project state marks `compile_required: true`, use only a compiler that supports the exact state contract. V7-07 remains byte-stable and cannot consume the proposed v2 motion/endpoint contract; report a compilation blocker instead of flattening typed state into hand-edited prose.
