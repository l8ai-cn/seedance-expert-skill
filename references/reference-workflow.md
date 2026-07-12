# Reference Workflow

## Binding Gate

Select the exact surface and operation before writing prompt-visible reference prose. Seedance 2.0 has no evidenced universal `@` syntax, fixed media range, or parser rule.

For each asset keep three concepts separate:

- semantic `binding_id`: a stable internal ID such as `product` or `motion_donor`;
- request transport: interface attachment, typed media array, ordered content object, or structured role;
- prompt binding policy: an external opaque value, a profile-derived media ordinal, or none for a structured role.

Load `[ref:surface-prompt-profiles]`. Preserve external opaque handles byte-for-byte. For a derived API operation, supply media type and ordering but no caller handle; the profile owns the exact ordinal. Asset IDs, filenames, URLs, external handles, and derived ordinals are not interchangeable. A structured first/last-frame field needs no textual token.

Use typed text/binding segments. Do not search prose for placeholder-looking strings and do not treat any notation in this document as literal provider syntax.

## Target And Dimension Authority Map

Before writing prompt prose, identify each target—for example a character, product, set, shot, or audio source—and decide which asset controls each relevant dimension. Authority prevents accidental transfer of identity, logos, scene ownership, or incompatible camera and motion instructions.

| Asset | Plausible dimensions to inspect | Do not assume |
|---|---|---|
| Image | identity, face detail, wardrobe, product geometry, environment, visual style, composition | unseen motion, timing, or a structured frame role |
| Video | subject motion, camera motion, timing, blocking, performance, visible start/end states | identity, wardrobe, logo, audio, or scene ownership |
| Audio | timing, rhythm, ambience, delivery, voice, music texture | voice, song, performance, or likeness authorization |
| Text brief | action, genre, camera plan, constraints, acceptance criteria | authority over a supplied asset or provider transport |

Use the V7 controlled dimensions: identity, face detail, wardrobe, product/object geometry, environment, visual style, visible opening state, opening composition, subject motion, camera motion, timing/rhythm, audio/voice, endpoint, endpoint framing, and text/logo treatment. For every target, each dimension has exactly one winner or is marked not applicable. One asset may own several dimensions. Two assets may not win the same target/dimension.

Record typed leakage risks and explicit exclusions. Priority, confidence, media type, filename, and upload order may explain a human decision but never resolve a conflict automatically. Every included asset must win at least one necessary target/dimension; otherwise remove it.

The project-state `tag` and single-role fields are v6 compatibility input pending V7-08. Do not derive V7 authority or provider syntax from them.

## Rules

- Preserve external opaque bindings; derive ordinals only in the selected surface renderer.
- Resolve authority per target and dimension before writing style language.
- Allow one asset to control several compatible dimensions, but never allow two winners for the same target/dimension.
- State every allowed transfer and every likely leakage dimension that must be excluded.
- Keep appearance references distinct from structured first/last-frame roles.
- Use owned, licensed, public-domain, or clearly authorized references.
- Track media-use, likeness, voice/performance, music, and brand/logo authorization separately; one does not prove another.
- When authorization is unclear, transfer broad motion, tempo, mood, or production function rather than the protected dimension; record that protected dimension as leakage and exclude it explicitly.
- Record how the intended subject is found inside each asset. A whole-asset or single-subject locator is enough only when unambiguous; multi-person images/video require a position, role, or visible feature, and multi-speaker audio requires a role or speaker label.
- Treat multimodal reference generation, video edit, video extend, and first/last-frame generation as separate operations. Never infer one operation's fields from another.
- If audio and video references compete, assign camera motion, subject motion, timing, and audio/voice independently. The renderer resolves each selected surface policy later.
- In sequences, separate canonical identity/product references from accepted continuity sources.
- Never let a motion reference overwrite continuity locks, completed beats, reserved beats, or typed binding policy.

## Workflow-Specific Clauses

These are prose clauses appended after typed bindings; they are not token templates.

| Workflow | Strong clause | Avoid |
|---|---|---|
| Multimodal reference | `for the product, the image controls geometry and identity; the video controls camera rhythm only; the audio controls tempo only.` | `Use all references for style.` |
| Video edit | `is the verified edit target; preserve composition and timing, change only [lighting/background/VFX].` | Regenerating the whole concept from scratch. |
| Video extend | `is the accepted source clip; continue the same shot and preserve the observed endpoint.` | Starting from a planned ending or an unverified endpoint. |
| First/last frame | Assign verified structured opening/endpoint roles; prompt only the continuous transition. | Treating an appearance image as a frame role or inventing prompt tokens for structured fields. |
| Audio reference | `controls tempo and energy; do not copy protected voice, song, or performance identity.` | Treating audio as authorization proof. |

## Motion Transfer

Field-observed technique; test before promising results. A donor video can drive choreography or camera rhythm while an image keeps identity.

- Bind a donor video and an identity anchor through the active operation profile, then assign authority by target/dimension: for example, the donor wins subject motion while the image wins identity and wardrobe; exclude performer, room, style, audio, and logo leakage from the donor as applicable.
- Pick donor clips with one clear action, a clean silhouette, and a steady camera. Busy multi-person footage transfers noise, not motion.
- Mute the donor clip before upload unless its sound should drive timing; if it keeps sound, state which semantic binding owns the clock.
- Transfers well: choreography, gesture timing, camera rhythm, blocking. Transfers poorly: fine hand detail, multi-person sync, facial performance.
- Use only owned, licensed, stock, mocap, rehearsal, or self-recorded donor footage; real-person donors transfer general motion only, never likeness.

## Typed Plan Pattern

Build the prompt from ordered segments:

1. binding segment for a selected reference;
2. text stating the exact target/dimensions it controls and its exclusions;
3. any additional binding segments, each with its target/dimension authority and exclusions;
4. the current action, endpoint, camera, sound, and constraints.

If the selected operation uses structured roles, omit binding segments and return only request-role records plus transition prose. If an opaque profile requires an external handle and it is missing, stop and ask for the interface value. If the profile derives an ordinal, reject any caller handle and calculate from media type and position.

## Sequence Transfer

The accepted previous clip may control only the declared observed opening-state dimensions—for example composition, camera phase, motion phase, ambience, or environment arrangement. Canonical identity assets keep their assigned immutable dimensions. Preserve each typed binding and selected surface policy, exclude unrelated identity/wardrobe/logo transfer, and do not perform future action early. Future-beat leakage is a clip-scope error, not a reference-authority win.

## Causal And Observable Shot Check

For interaction-heavy or fragile shots, plan visible events before prose: initial state, trigger, optional motion path, decisive contact or non-material state change, primary response, optional secondary responses, follow-through, and settled endpoint. Dependencies point backward, and the endpoint must be reachable from the trigger through a visible consequence.

Give the shot one primary camera move, including `locked`, and identify the exact events that show the before-state, decisive change, consequence, and endpoint. Keep an audio cue's timing separate from its meaning. This is a preflight heuristic for staging and diagnosis, not a description of Seedance architecture, a physics guarantee, or evidence that the provider will follow the plan.
