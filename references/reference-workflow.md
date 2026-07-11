# Reference Workflow

## Binding Gate

Select the exact surface and operation before writing prompt-visible reference prose. Seedance 2.0 has no evidenced universal `@` syntax, fixed media range, or parser rule.

For each asset keep three concepts separate:

- semantic `binding_id`: a stable internal ID such as `product` or `motion_donor`;
- request transport: interface attachment, typed media array, ordered content object, or structured role;
- prompt binding policy: an external opaque value, a profile-derived media ordinal, or none for a structured role.

Load `[ref:surface-prompt-profiles]`. Preserve external opaque handles byte-for-byte. For a derived API operation, supply media type and ordering but no caller handle; the profile owns the exact ordinal. Asset IDs, filenames, URLs, external handles, and derived ordinals are not interchangeable. A structured first/last-frame field needs no textual token.

Use typed text/binding segments. Do not search prose for placeholder-looking strings and do not treat any notation in this document as literal provider syntax.

## Asset Role Map

Before writing prompt prose, assign every uploaded asset a role. Role mapping prevents accidental transfer of identity, logos, scene ownership, or incompatible camera and motion instructions.

| Asset | Good roles | Avoid |
|---|---|---|
| Image | identity, product, pose, costume, environment, first frame, last frame | asking it to define unseen motion |
| Video | motion, camera, pacing, blocking, timing, gesture rhythm | copying protected identity, logo, or scene ownership |
| Audio | rhythm, tempo, mood, ambience, delivery tone, music texture | assuming voice, song, or likeness authorization |
| Text brief | action, genre, camera plan, constraints | replacing concrete reference roles with vague mood words |

The single-primary-role rule in this v6-compatible file remains a conservative planning shortcut. The V7 authority planner will replace it with dimension-level conflict resolution; do not expand that architecture inside this binding migration.

## Rules

- Preserve external opaque bindings; derive ordinals only in the selected surface renderer.
- Give every reference one primary role before writing style language.
- Do not ask one reference to control incompatible roles unless the tradeoff is explicit.
- Use owned, licensed, public-domain, or clearly authorized references.
- Write what should transfer and what should not transfer.
- When authorization is unclear, transfer broad motion, tempo, mood, or production function rather than protected identity.
- Treat multimodal reference generation, video edit, video extend, and first/last-frame generation as separate operations. Never infer one operation's fields from another.
- If audio and video references compete, state which semantic binding owns camera/motion and which owns tempo. The renderer resolves each selected surface policy later.
- In sequences, separate canonical identity/product references from accepted continuity sources.
- Never let a motion reference overwrite continuity locks, completed beats, reserved beats, or typed binding policy.

## Workflow-Specific Clauses

These are prose clauses appended after typed bindings; they are not token templates.

| Workflow | Strong clause | Avoid |
|---|---|---|
| Multimodal reference | `controls product identity; the motion donor controls camera rhythm; the audio donor controls tempo only.` | `Use all references for style.` |
| Video edit | `is the verified edit target; preserve composition and timing, change only [lighting/background/VFX].` | Regenerating the whole concept from scratch. |
| Video extend | `is the accepted source clip; continue the same shot and preserve the observed endpoint.` | Starting from a planned ending or an unverified endpoint. |
| First/last frame | Assign verified structured endpoint roles; prompt only the continuous transition. | Inventing prompt tokens for structured fields. |
| Audio reference | `controls tempo and energy; do not copy protected voice, song, or performance identity.` | Treating audio as authorization proof. |

## Motion Transfer

Field-observed technique; test before promising results. A donor video can drive choreography or camera rhythm while an image keeps identity.

- Bind one donor video and one identity anchor through the active operation profile, then state that the donor controls choreography only and transfers no performer, costume, room, or logo.
- Pick donor clips with one clear action, a clean silhouette, and a steady camera. Busy multi-person footage transfers noise, not motion.
- Mute the donor clip before upload unless its sound should drive timing; if it keeps sound, state which semantic binding owns the clock.
- Transfers well: choreography, gesture timing, camera rhythm, blocking. Transfers poorly: fine hand detail, multi-person sync, facial performance.
- Use only owned, licensed, stock, mocap, rehearsal, or self-recorded donor footage; real-person donors transfer general motion only, never likeness.

## Typed Plan Pattern

Build the prompt from ordered segments:

1. binding segment for the identity or product reference;
2. text stating its allowed transfer and exclusions;
3. binding segment for the motion or camera donor;
4. text stating its allowed transfer and exclusions;
5. the current action, endpoint, camera, sound, and constraints.

If the selected operation uses structured roles, omit binding segments and return only request-role records plus transition prose. If an opaque profile requires an external handle and it is missing, stop and ask for the interface value. If the profile derives an ordinal, reject any caller handle and calculate from media type and position.

## Sequence Transfer

The accepted previous clip controls only the observed opening state, camera phase, motion phase, ambience, and environment arrangement. Canonical identity assets keep immutable design. Preserve each typed binding and selected surface policy, exclude unrelated identity/costume/logo transfer, and do not perform future action early.
