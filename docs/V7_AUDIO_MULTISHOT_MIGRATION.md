# V7-09 audio, dialogue, and multi-shot migration

V7-09 adds a parallel, offline candidate-preview path for exact dialogue and explicit editorial cuts. It does not modify the V7-07 compiler or V7-08 state contracts, activate a provider, submit a request, or claim that a returned video will contain correct speech, lip sync, audio, cuts, or timing.

## Why this is a separate contract

Scene IR v1 has a useful causal plan but only a generic audio description and array-ordered shots. It cannot establish an exact utterance, one resolved speaker, spoken language, turn order, voice authorization, subtitle policy, or whether two shots are joined by a hard cut, match cut, dissolve, or fade. Adding those meanings to version 1 would change published compiler/toolchain hashes and could silently reinterpret existing fixtures.

V7-09 therefore keeps version 1 byte-stable and adds versioned AV contracts and tools. Version dispatch is exact; no tool guesses a document version, upgrades ambiguous dialogue, infers a cut from array order, or down-converts V2 while retaining V2 provenance.

## Eight independent evidence questions

Treat these as separate claims:

1. model-level audiovisual capability;
2. audio input on the selected surface and operation;
3. audio output on that surface and operation;
4. dialogue generation;
5. lip-sync behavior;
6. voice-reference behavior;
7. multi-shot request grammar; and
8. returned adherence.

One positive answer does not prove another. Prompt language does not select a provider, region, product form, or timing grammar. A Chinese instruction can target a global surface; an English instruction can target a China-scoped surface. The exact surface, operation, model variant, region, policy hash, evidence claims, and expiry remain explicit.

## Exact speech contract

Every dialogue or voiceover event has:

- exactly one resolved speaker;
- an exact NFC utterance and recomputed UTF-8 SHA-256;
- a BCP-47-style spoken-language tag independent of prompt locale;
- a contiguous turn index and explicit overlap policy;
- a shot/timing scope and delivery intent;
- a voice mode and authorization binding; and
- an explicit subtitle/post policy.

The utterance bypasses the localization catalog. English and Simplified Chinese instruction wrappers may differ, but the spoken substring, UTF-8 slice, and hash must be byte-identical. Translation for a dub creates a new semantic variant and hash. The compiler does not normalize punctuation, transliterate, add smart quotes, or infer speech from a description.

Provider-token-shaped text, URLs, paths, control characters, bidi/default-ignorable characters, ambiguous line breaks, wrapper sentinels, and non-NFC exact lines fail closed. Diagnostics never echo caller-controlled text.

Voice modes remain separate:

- `generic_synthetic` requests a non-identified voice only where the selected policy allows it;
- `authorized_reference` requires an exact asset/authority binding and rights state; and
- `post_dub` is `post_only` and must never appear in a provider prompt.

An accepted audio upload does not prove exact playback, voice identity, or lip sync. Voice and likeness authorization remain independent.

## Shot and transition contract

`single_continuous_take` contains exactly one shot and no editorial transition edges. Camera motion stays inside the shot.

`edited_multi_shot` contains at least two shots and exactly `N-1` adjacent, ordered transition edges. Each edge declares its outgoing endpoint, incoming opening, type, preserved invariants, allowed changes, and any audio crossing the boundary. Supported initial editorial types are hard cut, match cut, dissolve, and fade. Continuous camera motion is not a transition type.

Array adjacency never implies a cut. Missing, duplicate, reversed, skipped, branched, future, or self-linked edges fail. A hard cut is an editorial relationship, not an automatic causal dependency or continuity reset.

Current-clip beats must be covered exactly and remain disjoint from completed and reserved-future beats. Dialogue, effects, reveals, and transitions from a later generation cannot leak into the current preview.

## Timing and audio continuity

The semantic plan separates meaning from timing:

- ordered event phases without exact ranges;
- relative named beats or cues;
- whole-shot continuous audio;
- contiguous cross-shot continuous audio; and
- surface-exact ranges only under a current policy that permits them.

Exact ranges are never inferred from prose, language, shot count, or another provider's example. Conflicting timing modes, non-contiguous cross-shot scope, and unsupported exact ranges fail closed.

Ambience, music, speech, effects, rhythm, and silence have explicit owner and shot scope. Event-window effects name their start/end events, while genuinely continuous effects use a continuous timing mode. Cross-shot continuous audio names every transition it crosses. The initial schema does not yet type a silence suppression-layer list, so any such mix instruction remains reviewable description text rather than a machine-enforced field.

## Subtitle and review boundary

Initial V7-09 subtitle modes are `none`, `post_subtitles`, `post_sdh_captions`, and `post_forced_narrative`. Post modes require a clean picture. Generated in-picture subtitles are not supported by the candidate compiler.

The AV take-review companion is hash-bound to both the base take review and AV scene. Speech accuracy, speaker attribution, spoken language, lip sync, timing, non-speech audio, transitions, continuity, and unexpected in-picture text are separate results. A final frame cannot prove any temporal audio fact. A base take cannot enter the AV pass state while a required AV result failed or remains unknown.

## Provider and reference boundary

The surface AV policy is data, not user prose. Its evidence-pinned form is candidate-only, UTC-expiry-checked with an exclusive expiry date, and fail-closed. Any future trusted entry must bind the canonical SHA-256 of the complete immutable policy—not a few selected profile hashes—so scope, grammar, AV modes, timing, and evidence pins cannot be changed independently. V7-09 deliberately ships no trusted policy binding. The checked-in supported policy is an unmistakable `unattested_fixture`; only the hidden internal/test opt-in can inspect it, and every resulting preview carries `unattested_fixture_preview` plus `UNATTESTED_POLICY_FIXTURE`. The default CLI rejects it. User input cannot self-authorize dialogue, voice reference, multi-shot grammar, exact timing, subtitles, or provider execution.

V7-09 uses policy-hash-bound semantic media IDs only for an authorized voice assignment. Every supplied V2 binding must be consumed by exactly that typed relation; unused inventory fails closed. The initial V2 contract does not yet assign visual reference targets/dimensions, derive provider ordinals, accept prompt-visible handles, or encode structured first/last-frame roles; those remain in the separate V7-07 authority path until V2 gains a hash-bound reference-authority manifest. Prompt locale never changes a V2 voice binding or exact utterance.

## Candidate-preview boundary

The V7-09 renderer may produce paired offline previews and full provenance, but no output is an executable provider receipt. Existing provider profiles remain disabled. V7-08 `generation-run-v2` remains blocked/not-run. Actual quality claims require saved inputs, requests, returned media, model/surface/operation/version/date, and review of the named observable.

## Validation and stress requirements

The change is complete only when:

1. schema and dependency-free checker behavior agree;
2. exact utterance bytes and spans survive both locales;
3. speaker, turn, transition, beat, timing, authorization, subtitle, and reference conflicts fail closed;
4. post-dub text cannot enter a prompt;
5. final frames cannot prove audio;
6. diagnostics remain deterministic and non-echoing;
7. every new runtime file is packaged, hash-locked, installable, and rollback-safe;
8. all new and existing tests pass in ten fresh processes and on Python 3.11/3.12 across Linux, macOS, and Windows;
9. V7-07 compiler/toolchain bytes and V7-08 state/run contracts remain unchanged; and
10. evidence policy and provider activation remain disabled.

Offline validation proves contract integrity and candidate-render parity. It does not prove generated-video quality.
