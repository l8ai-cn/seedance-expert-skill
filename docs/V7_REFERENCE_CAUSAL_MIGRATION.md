# V7-06 reference authority and causal-planning migration

V7-06 replaces the v6 "one primary role per asset" shortcut with two candidate-only planning contracts:

1. a target-and-dimension reference authority map; and
2. a causal scene plan whose events can be checked for order and camera observability.

Neither contract describes Seedance's hidden architecture, guarantees transfer fidelity, or proves that a generated video will obey the plan. They are deterministic preflight tools: they make conflicts visible before prompt prose or a provider request is built.

## Runtime boundary

`scripts/reference_planner.py` accepts one JSON document on standard input and no provider or media arguments:

```json
{
  "schema_version": 1,
  "reference_manifest": {"$schema": ".../reference-manifest.schema.json"},
  "scene_ir": {"$schema": ".../scene-ir.schema.json"},
  "binding_plan": {"$schema": ".../binding-plan.schema.json"}
}
```

Invoke it only with `--preview-candidate`. The inner objects must be complete instances of their checked-in schemas; the abbreviated objects above show envelope ownership, not valid fixtures. The process reads once from standard input, performs no network or filesystem output, and emits a canonical `planning-report.schema.json` document containing IDs, evidence closure, ordering, diagnostics, and content hashes—not prompt prose, media, paths, URLs, handles, or caller text. `scripts/scene_ir_check.py` can validate the causal object alone.

## Decision

The planning invariant is:

```text
asset + intended target + controlled dimension + explicit exclusions
→ one authority winner for that target/dimension
→ surface-specific binding policy

initial state → trigger → decisive state change → visible response
→ follow-through → settled endpoint
→ camera observability check
```

Reference authority and surface binding are separate. The authority map decides what an asset is allowed to influence. The V7-05 binding plan decides how that asset reaches one exact provider operation: an externally captured opaque handle, an evidence-pinned derived ordinal, or a structured request role with no prompt token.

## Reference authority contract

Every included asset must have a purposeful use. Authority is resolved on the key `(target, dimension)`, not by media type, filename, upload order, confidence, or a universal image/video/audio hierarchy.

The planner uses these controlled dimensions:

> V7-07 adds visible opening state and endpoint framing to the unreleased V7-06 candidate partition. Existing candidate manifests must migrate their complete dimension partitions; this is not an active 6.6 contract change.

- identity;
- face detail;
- wardrobe;
- product or object geometry;
- environment;
- visual style;
- visible opening state;
- opening composition;
- subject motion;
- camera motion;
- timing or rhythm;
- audio or voice;
- endpoint;
- endpoint framing;
- text or logo treatment.

For each target, every dimension is either assigned exactly one winning asset or marked not applicable. A single asset may legitimately win several dimensions; several assets may not win the same target/dimension. Other assets that could leak into that dimension must be explicitly excluded. Priority and confidence document the human decision but never break a tie automatically.

Target IDs also bind the authority graph to the causal scene: character, product, object, environment, and text/logo targets resolve to typed scene entities; shot targets resolve to exact shot IDs; audio targets resolve to exact audio-event IDs. A character or object with audio/voice authority must appear as an audio-event source. Each asset separately records how its intended subject is located inside the media, so a multi-person image/video or multi-speaker recording cannot hide behind a target ID alone.

This removes two unsafe shortcuts:

- `image = identity`, `video = motion`, and `audio = timing` are not universal rules; and
- adding more references is not automatically better.

The smallest set is the set in which every asset owns at least one necessary target/dimension. Remove an asset that owns nothing; add one only to fill a documented authority gap. Media preflight observations are user- or reviewer-attested metadata, not computer-vision findings inferred by this skill.

Media compatibility is explicit rather than guessed from filenames: images may own static visual dimensions, audio may own audio/voice or timing/rhythm, and video may own visual or motion dimensions plus audio/voice only when embedded audio is attested. An asset's declared use must match its media and at least one dimension it wins. A donor video's compound camera is allowed when camera motion is explicitly excluded; it blocks only when that donor is asked to own camera motion.

## Appearance references are not frame roles

An ordinary image reference may control identity, wardrobe, product geometry, environment, style, or another declared dimension. It does not become a first or last frame merely because it is an image.

A first/last-frame operation is different. V7-07 makes all source-carried meaning explicit in the authority matrix:

- the structured first-frame role must win both `opening_state` and `opening_composition`;
- the structured last-frame role must win both `endpoint` and `endpoint_framing`; and
- the prompt describes the continuous transition between those supplied states.

The retained Volcengine claim `volc.binding.first-last-frame-role` establishes structured role designation only. The four semantic authority dimensions are a local validated planning contract, not a provider capability claim. Neither layer establishes universal syntax, exact pixel preservation, or support on another surface or operation. The claim and associated profile are candidate-only and time-bounded.

## Leakage and rights preflight

Leakage is recorded as typed transfer risk, not buried in an open-ended note. Common conflicts include donor identity, wardrobe, environment, visual style, camera motion, audio or voice, and text or logos. Each risk must point to the exact target/dimension and an explicit exclusion or other resolution. Future-beat leakage remains a separate clip-scope error because it is not one of the reference-authority dimensions.

Authorization is also dimension-specific. Media-use rights do not prove likeness, voice or performance, music, or brand and logo authorization. `unknown` or `not authorized` cannot be treated as permission to transfer the protected dimension; it is allowed only when that dimension is declared as leakage and explicitly excluded. The planning report does not serialize media bytes, URLs, paths, provider asset IDs, API keys, or prompt-visible handles.

## Causal scene plan

The causal plan describes visible filmmaking intent as ordered events. A material interaction records participating entities, a typed contact or material change, material ownership and response properties, an optional motion-path event, and the visible result. Force or contact-location detail belongs in the observable event wording until a later typed contract adds those fields. A performance beat, light change, reveal, or other non-material event may instead declare a visible state change without inventing contact physics.

A complete shot normally contains:

1. initial state;
2. trigger;
3. optional motion path;
4. contact or another decisive state change;
5. primary visible response;
6. optional secondary responses;
7. follow-through; and
8. settled endpoint.

Dependencies must point to earlier events. The decisive event must be reachable from the trigger, its visible consequence must be reachable from that decisive event, and the endpoint must be reachable from the consequence chain. These checks reject unordered stage-direction lists; they do not claim access to the model's internal simulation.

## Camera and audio observability

Each shot has one primary camera move, including `locked` when no translation or rotation is intended. The plan records start framing, path and speed, subject relationship, and endpoint framing. Its observability map names the exact event IDs for:

- the readable before-state;
- the decisive event;
- one or more visible consequences; and
- the settled endpoint.

This lets preflight reject a shot whose camera cannot plausibly show the requested change. It is a staging test, not a quality score or a generation guarantee.

Audio timing and audio meaning remain separate. A sound can occur on the trigger, during motion, after impact, at the endpoint, or continuously while serving dialogue, sound effect, ambience, music, rhythm, or deliberate silence. A temporal cue never proves voice, music, or performance authorization.

## Evidence boundary

V7-06 does not promote field observations or pending evidence into general Seedance capabilities.

- `bytedance.model.reference-control` is limited to the retained model-level statement that references can guide camera movement, lighting, performance, and shadow for reference generation. It does not establish the planner's full dimension taxonomy, priority rules, or perfect transfer.
- `bp.assets.purposeful-set` and `bp.character.headshot-fullbody` remain pending, candidate BytePlus `reference_generation` workflow guidance; the runtime does not activate either recommendation. Its generic multiview check blocks only an ambiguous identity/appearance/product/frame transfer and accepts an explicitly located subject, so it is not a provider capability claim or universal ban on collage imagery.
- `volc.binding.first-last-frame-role` remains a pending, candidate Volcengine `first_last_frame` API-field claim. It establishes role designation only.
- Contra Labs annotations are research-only vocabulary for observable video description. They are not Seedance architecture, prompt syntax, or capability evidence.

The existing V7-05 profiles remain `candidate` with `runtime_enabled: false`. V7-06 planning output is likewise preview-only. Evidence expiry, profile/operation matching, and exact binding-set equality continue to fail closed.

## V6 compatibility boundary

The current project-state, prompt-spec, and generation-run schemas still carry v6 `tag` and single-role fields. They are compatibility input only until V7-08 migrates state and compiler contracts. New V7-06 planning must not infer authority from those fields, write authority decisions back into them, or treat a legacy tag as a prompt-visible provider handle.

During the transition:

- preserve legacy state so existing projects remain readable;
- create the V7 authority map independently;
- keep semantic binding IDs stable;
- let the selected V7-05 surface profile own transport and prompt syntax; and
- do not activate provider profiles or generate final English/Chinese prompt prose in this stage.

## Diagnostic intent

Stable failures distinguish planning problems:

- reference binding mismatch, multiple winners, task/operation conflict, collage risk, unresolved leakage, purposeless assets, incomplete preflight, media incompatibility, missing authority, and insufficient rights;
- missing initial state, a decisive event without visible consequence, invalid order or dependency, and missing or unreachable endpoint;
- a camera that cannot observe the required phases or specifies multiple primary moves; and
- audio instructions that conflate temporal relationship with semantic function.

The remedy is to repair the smallest failed contract field. Adding adjectives, extra references, or undocumented provider tokens is not a valid repair.

## Intentionally deferred

V7-06 does not:

- claim or reverse-engineer a Seedance 2.5 architecture;
- activate any model or provider profile;
- extend expired evidence;
- infer media contents automatically;
- rewrite legacy project-state schemas;
- render final multilingual prompts;
- perform network calls or upload media; or
- guarantee physical accuracy, reference fidelity, continuity, or output quality.
