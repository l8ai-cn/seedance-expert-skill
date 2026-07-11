# Reference Transfer Contract

<!-- fixed_handle_audit: contrast_only -->

Use this reference when images, videos, audio, previous clips, final frames, or interface tags appear in a sequence.

## Exact Binding Rule

Keep the semantic `binding_id` separate from the surface binding. When a profile requires an externally supplied opaque handle, preserve it byte-for-byte. Never invent, normalize, translate, reformat, renumber, correct spacing, change case, or add a prefix. A value such as `@Image1`, `@Image 1`, `[Video 1]`, or a Chinese/interface-generated name is opaque; its spelling proves nothing about another surface. Derived profiles reject those caller values and construct only their pinned formatter.

Load `[ref:surface-prompt-profiles]` and render typed text/binding segments through the selected operation profile. Never parse placeholder-looking text. When the API uses structured media roles, keep those roles out of prompt prose and never substitute an asset ID, URL, or filename as a token.

## Role Separation

Assign each reference one primary role:

- image: identity, product, pose, costume, environment, first frame, or last frame;
- video: source clip, motion, camera, timing, blocking, or continuity source;
- audio: tempo, ambience, music phase, rhythm, delivery tone, or active dialogue source;
- final frame: observed state or target endpoint.

State what transfers and what must not transfer. R2V and continuation work fail when identity, motion, camera, environment, and audio roles bleed together.

## Continuity Source Versus Motion Reference

A canonical identity reference controls immutable identity. An accepted previous clip or final frame controls transient opening state. A donor video can control motion or camera only when explicitly allowed. Do not let a motion reference overwrite character identity, wardrobe, product geometry, or accepted state.

## Multi-Subject Selector

When a reference contains multiple subjects, identify the intended subject by position, tag, role, or visible feature. Do not assume the central or largest subject is correct when the user has not said so.

## Transfer And Ignore Clause

Every role-bound reference should compile as a typed binding segment followed by a transfer clause:

`controls [role] only; ignore [identity/environment/logo/audio/camera/motion] from that reference.`

The surface renderer inserts a binding before that clause only when the active operation uses `opaque_external_handle` or `derived_media_ordinal`. Opaque values are preserved; ordinals are derived from the selected profile and request position. The bracketed words above are editorial fields, not prompt tokens.

Use only owned, licensed, public-domain, stock, self-recorded, or clearly authorized references for protected identity, voice, brand, logo, or performance transfer.
