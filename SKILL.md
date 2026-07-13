---
name: seedance-20
description: "This skill should be used when creating, improving, or troubleshooting Seedance 2.0 video on any surface - Dreamina, Jimeng, CapCut, Doubao, Volcengine/Ark, BytePlus, Runway's Seedance route, fal, or third-party provider/router surfaces such as EvoLink, OpenRouter, Kie.ai, PiAPI, LaoZhang, Runware, ModelsLab, AI/ML API, MuAPI, SeeGen, and Segmind - including text/image/video/reference-to-video prompts, first/last frame, dialogue, lip-sync and audio, IP-safe rewrites, API, pricing and model-ID questions, and zh/ja/ko/es/ru prompt work. Not for non-Seedance models (Sora, Veo, Kling, Runway's own Gen models) or image-only prompting."
license: MIT
user-invocable: true
tags: [seedance]
metadata:
  version: "6.6.0"
---

# seedance-20

Seedance 2.0 operating loop for agent-directed video work. Use this root skill to route, check facts, protect references, and keep prompts compact before loading specialized sub-skills.

## Soul

This skill exists so that a person who arrives with a feeling leaves with a film. Three principles govern everything below:

1. **Hear the intent behind the words.** Users describe outcomes ("make it feel like home"), not parameters. Every gate and sub-skill translates feeling into craft; none of them may hand the translation work back to the user.
2. **Keep the story alive.** Hold a story state across the conversation: subject, mode, look, references, decided constraints, and what failed before. Every skill reads it before asking anything and updates it after acting. A user should never have to repeat a decision, and a new request inherits the world already built.
3. **Evolve with the user.** Speak plainly to a beginner and in director language to a professional - and notice when the same user grows from one into the other across a project. The register adapts; the standards never do.

## Fast Lane

Most requests are one short clip from someone who just wants to see their idea. Do not run the full gate loop on them. Take the fast path when the request is a single standalone clip, from a non-expert, with no IP/likeness/brand/real-person or safety flag and no platform-fact question (API, pricing, model ID, limits, region):

1. Go straight to `[skill:seedance-interview-short]` - or write the brief immediately if the idea is already clear - then `[skill:seedance-prompt-short]`.
2. Apply craft inline from memory: one visible beat, one motivated camera move, one motivated light source, sound intent, and the directing coherence rule (name one intention; make camera, light, and performance serve it). Load `[ref:directing-engine]`, `[ref:capability-map]`, `[ref:allocation-model]`, and the source or professional gates only when something actually invokes them.
3. Treat it as one clip: do not ask sequence or continuation questions yet. Raise "should this be a series, part two, or longer" only after the first draft, or when the user says continue, extend, next part, or longer.
4. Keep the single-clip prompt compact (about 40-110 words) unless the active surface is a verified stricter API, and keep director language (blocking, directorial voice, shot contracts) inside the internal brief - speak to the user in plain words.

Leave the fast lane the instant the request earns a gate: IP/likeness/brand/safety risk goes to the safety gate (step 9); a platform-fact question loads the source gate; a film, client, or delivery request loads the professional gate; a long story, connected clips, or continuation goes to the Sequence Gate. When in doubt about safety, leave the fast lane. The Operating Loop below is the full procedure - the fast lane is the default for the common case, and every gate it skips stays one signal away.

## Operating Loop

1. Intake: identify the user's goal, production phase, target surface, mode, duration, aspect ratio, references, audio needs, deliverables, and safety/IP risks. If intake surfaces a clear safety, IP, likeness, or evasion risk, jump straight to the safety gate (step 9) before any planning.
2. Source gate: before platform claims, load `[ref:api-status]` and `[ref:source-registry]`. For Runway, Volcengine, fal, provider/router, or China-facing surface specifics, also load `[ref:platform-surface-matrix]`.
3. Professional gate: if the user asks for film, ad, campaign, client, delivery, localization, color, sound, subtitle, post, QC, or multi-shot work, load `[ref:pro-filmmaking-standards]` before drafting.
4. Sequence Gate: classify the request as `standalone_clip` or `sequence_project` before the Mode Gate. Use `sequence_project` for long stories, connected clips, continuation/extend/next-part requests, dense action/dialogue scenes, campaigns, or any idea whose beats cannot clearly fit inside one verified active-surface generation. For sequence work, load `[skill:seedance-sequence]`, `[ref:sequence-project-state]`, `[ref:continuation-handoff]`, and `[ref:prompt-compiler]`; for continuation, repair-tail, or re-anchor requests, also load `[skill:seedance-continuation]`.
5. Mode gate: choose T2V, I2V, V2V, R2V, FLF2V, edit, native extend when verified for that exact surface operation, or troubleshoot before writing prose.

   Mode availability is operation- and surface-specific. Do not infer an endpoint, entitlement, request field, duration, or fallback from a provider name. Use a checked-in profile only for its exact registered operation; unknown or disabled operations fail closed and require current provider-owned documentation.

6. Capability check: when planning any shot, mode, or budget, load `[ref:capability-map]` for dated, surface-scoped constraints and `[ref:allocation-model]` to choose the take's primary acceptance target and simplify competing review risks before drafting. Do not turn those heuristics into claims about hidden model capacity.
7. Reference authority: for every intended target and controlled dimension, name exactly one winning asset or mark the dimension not applicable; the same asset may own several dimensions. Record every other asset that must be excluded from that target/dimension, and remove any asset that owns nothing. Do not infer authority from media type, upload order, a legacy tag, priority, or confidence. Keep ordinary appearance references separate from structured first/last-frame roles. Then load `[ref:reference-workflow]`, `[ref:reference-transfer-contract]`, and `[ref:surface-prompt-profiles]`: keep the semantic `binding_id` separate from authority, request transport, and prompt syntax. Preserve an externally captured handle, derive only an evidence-pinned surface ordinal, or use structured roles with no token. Never invent a universal `@` tag, parse a placeholder, accept a caller override for a derived binding, or put an asset ID/URL into prompt prose. When a complete V7 reference manifest, causal scene IR, and binding plan are available, pass their strict envelope to `scripts/reference_planner.py --preview-candidate`; treat its hash-only report as preflight, never as prompt text or provider activation. When the matching surface binding set and paired realization catalog carrying a human-attestation declaration are also available, pass the closed request to `scripts/prompt_compile.py --preview-candidate`; do not reuse caller binding prose or hand-edit its typed binding segments.
8. Multilingual gate: if the prompt uses Chinese, Russian, Japanese, Korean, Spanish, or code-mixed wording, load `[ref:multilingual-community-examples]` and preserve exact opaque surface bindings byte-for-byte without translating or normalizing them. For a V7 English/Chinese pair, load `[ref:prompt-compiler]`: both locales must come from one validated semantic program and a hash-bound catalog with a human-attestation declaration. Structural parity is machine-checked. The declaration is not authenticated; translation meaning, naturalness, compiler grammar, and the final pair must be separately human-reviewed. V7-07 rejects exact dialogue, voiceover, and multi-shot input. The separate V7-09 path requires one resolved speaker, byte-exact utterance, spoken-language tag independent from prompt locale, ordered turn, voice-rights state, subtitle/post policy, and explicit editorial transitions; validate it through `scene_ir_v2_check.py`, `semantic_lint_v2.py`, and `prompt_compile_v2.py`, then bind returned-media review through `av_take_review_check.py`. It remains candidate preview only, ships no trusted AV surface policy, and rejects the checked-in unattested fixture by default. For native Chinese, Japanese, or Korean example-driven requests outside those closed compiler paths, route to `[skill:seedance-examples-zh]`, `[skill:seedance-examples-ja]`, or `[skill:seedance-examples-ko]`.
9. Safety gate: route IP, likeness, voice, brand, real-person, graphic, or evasion-like wording through `[skill:seedance-copyright]` or `[skill:seedance-filter]`.
10. Direction: before drafting any scene, name one intention and make camera, lens, light, blocking, performance, and sound serve it instead of picking a "cinematic look" - apply this coherence rule inline. Load `[ref:directing-engine]` only when scenes need distinct treatment, one directorial voice must hold across many clips, or the right setup is genuinely unclear.
11. Prompt build: route to `[skill:seedance-interview]`, `[skill:seedance-prompt]`, `[skill:seedance-prompt-short]`, `[skill:seedance-sequence]`, `[skill:seedance-continuation]`, or a domain skill for camera, motion, lighting, audio, characters, VFX, style, recipes, or pipeline.
12. Quality pass: run anti-slop and the directing coherence test, then check one visible beat, one primary camera move, physically motivated light, sound intent, continuity anchors, constraints, delivery caveats, and source-date caveats. For interaction-heavy or fragile shots, verify an ordered visible chain from initial state through trigger, decisive change, response, follow-through, and a local endpoint; name the exact events the camera is intended to cover. Keep subject, prop, camera, and environmental motion under separate owners: a completed subject endpoint may coexist with continuing rain, a cyclic fan, a frame exit, or an open camera handoff. Treat the chain and coverage as authored planning and review criteria, never as proof of visible output, Seedance internals, or physical accuracy.
13. Repair loop: when a take returns, triage it with `[ref:retake-protocol]` (keep / fix in post / edit / re-roll / rewrite, one variable per retake, inside an attempt budget); if it fails outright, diagnose root cause before adding adjectives via `[skill:seedance-troubleshoot]`.

## Sequence Gate

For a sequence project, do not write Clip 01 until these are known: story objective, final story outcome, ordered major beats grouped into scenes, active surface or conservative surface assumption, clip budget, current clip narrative job and felt intent, and current clip completed endpoint.

Do not write a continuation prompt until the previous accepted clip or its actual final frame has been reviewed and its observed end state recorded.

Sequence invariants:

- every sequence prompt has `project_id` and `clip_id` lineage;
- accepted observed state overrides planned state;
- rejected footage is excluded from canon and cannot become a continuation source;
- future prompts remain provisional until the preceding accepted take is reviewed;
- semantic binding IDs survive every clip unchanged. A surface policy—opaque external, derived ordinal, or structured role—exists only in a later explicit, hash-bound planning/profile artifact; v2 migration never infers or embeds one from legacy state;
- project-state-v1 `tag`, `role`, and `source_clip_tag` fields are legacy compatibility input only; migrate them through an explicit mapping and never use them, upload order, or prose to infer V7 authority, media type, binding policy, or provider syntax;
- project-state-v2 keeps planned and observed snapshots separate, records motion per owner, treats extension depth as review context rather than a failure threshold, and leaves uncertain motion unknown instead of deriving it from a still;
- every v2 clip is `compile_required`; V7-09 may produce an offline candidate preview for its exact AV contract, but it does not clear provider execution or V7-08 generation-run blockers. V7-07 does not accept v2, so never flatten v2 state or hand-edit its paired render;
- seamless continuation stays inside a scene; a scene boundary opens from canonical references and resets `extension_depth`;
- completed beats cannot replay and reserved future beats cannot leak early;
- continuity state must be updated after each accepted take;
- final Seedance prompts remain natural language unless the user explicitly asks for structured output.

## Load Map

| Situation | Load |
|---|---|
| Vague idea or missing brief | `[skill:seedance-interview]` or `[skill:seedance-interview-short]` |
| Long story, connected clips, campaign sequence, dense action/dialogue scene, or a prompt that needs several generations | `[skill:seedance-sequence]`, `[ref:sequence-project-state]`, `[ref:prompt-compiler]` |
| Continue, extend, next part, repair tail, bridge known states, or re-anchor drift from accepted footage | `[skill:seedance-continuation]`, `[ref:continuation-handoff]`, `[ref:continuity-qc]` |
| Fragile contact, continuing/cyclic motion, owner-specific endpoints, or motion handoff between clips | `[skill:seedance-motion]`, `[ref:model-mechanics]`, `[ref:continuation-handoff]`, `[ref:sequence-project-state]` |
| Review a generated take and update canon before the next prompt | `[ref:retake-protocol]`, `[ref:sequence-project-state]`, `[ref:continuation-handoff]` |
| Migrate saved project-state-v1 without guessing tags, authority, or motion | `[ref:sequence-project-state]`, `[ref:reference-workflow]`, `scripts/project_state_migrate.py inspect/migrate/verify`, then `scripts/project_state_v2_check.py` |
| First multi-clip project, or how the sequence loop actually runs end to end | `[ref:sequence-worked-trace]` |
| Dense animation storyboard or multi-shot prompt | `[ref:dense-storyboard-mode]`, `[ref:multishot-grammar]`, `[ref:2d-anime-grammar]` |
| Production prompt | `[skill:seedance-prompt]`, `[ref:quick-ref]`, `[ref:prompt-examples]` |
| Matched English and Simplified Chinese prompts from one validated V7 scene | `[ref:prompt-compiler]`, `[ref:multilingual-community-examples]`, `scripts/semantic_lint.py`, `scripts/prompt_compile.py --preview-candidate` |
| Planning any shot, mode, or budget | `[ref:capability-map]` for dated constraints and conservative test design |
| Choosing the primary acceptance target across identity, motion, and scene readability | `[ref:allocation-model]`, `[ref:intent-vs-precision]` |
| Multi-shot prompt or cuts inside one generation | `[ref:multishot-grammar]`; resolve the exact surface-operation policy before labels, timing ranges, or provider-ready output |
| 2D, anime, or cel-style motion | `[ref:2d-anime-grammar]`, `[skill:seedance-style]` |
| Professional film, commercial, campaign, or delivery workflow | `[ref:pro-filmmaking-standards]`, `[ref:shot-list-continuity]`, `[ref:delivery-qc]` |
| Compact prompt or Chinese compression | `[skill:seedance-prompt-short]`, language vocab reference |
| Choosing the right camera, light, blocking, performance, and voice for a scene, keeping every choice motivated, or holding one directorial style across a long story | `[ref:directing-engine]` |
| Camera, lens, blocking, shot contract | `[skill:seedance-camera]`, `[ref:cinematography-shot-language]` |
| Image reference / first frame | `[ref:i2v-guide]`, `[ref:reference-workflow]` |
| First and last frame | `[ref:first-last-frame-guide]` |
| Several references, conflicting transfer, donor leakage, or choosing what each asset controls | `[ref:reference-workflow]`, `[ref:reference-transfer-contract]`, `[ref:surface-prompt-profiles]` |
| API, Runway, Volcengine, fal, provider/router surfaces, China-facing surfaces, workflow, pricing, model IDs | `[skill:seedance-pipeline]`, `[ref:api-workflow]`, `[ref:model-name-map]` |
| Color, ACES, HDR/SDR, aspect ratio, subtitles, audio post, or QC | `[ref:color-pipeline-aces]`, `[ref:aspect-ratio-delivery]`, `[ref:subtitles-localization]`, `[ref:audio-post-delivery]`, `[ref:delivery-qc]` |
| Genre template, examples, or a worked directing example in a specific genre | `[skill:seedance-recipes]`, `[ref:examples-by-mode]`, `[ref:genre-guides]`, `[ref:directing-engine-genre-library]` |
| Chinese examples or safe Chinese rewrites | `[skill:seedance-examples-zh]`, `[skill:seedance-vocab-zh]`, `[ref:vocab/zh]` |
| Japanese examples or safe Japanese rewrites | `[skill:seedance-examples-ja]`, `[skill:seedance-vocab-ja]`, `[ref:vocab/ja]` |
| Korean examples or safe Korean rewrites | `[skill:seedance-examples-ko]`, `[skill:seedance-vocab-ko]`, `[ref:vocab/ko]` |
| Russian/Spanish or mixed-language examples | `[skill:seedance-vocab-ru]`, `[skill:seedance-vocab-es]`, `[ref:multilingual-community-examples]` |
| Slop-heavy or filter-tripping English wording | `[skill:seedance-vocab-en]`, `[skill:seedance-antislop]` |
| Bad result | `[skill:seedance-troubleshoot]` |
| A take came back: keep, fix in post, edit, re-roll, or rewrite | `[ref:retake-protocol]` |
| Why an observable failure may occur, or a novel case no rule covers | `[ref:model-mechanics]` for bounded hypotheses and test design, never hidden-architecture certainty |

Preserve typed binding IDs and selected surface policies, keep prompts short, and never convert field-observed community tricks into official platform guarantees. Fixed tokens in legacy fixtures are local values, never defaults for new output. For professional filmmaker requests, deliver the workflow object the role needs: shot list, shot contract, continuity ledger, prompt, post handoff, localization plan, or QC checklist.
