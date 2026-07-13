---
name: seedance-audio
description: "This skill should be used when the user asks for Seedance 2.0 audio, dialogue, lip-sync, music, sound effects, ambience, beat alignment, audio-reference mapping, desync troubleshooting, or sound-driven visual timing."
license: MIT
user-invocable: true
tags:
  - audio
  - lip-sync
  - dialogue
  - seedance-20
metadata:
  version: "6.6.0"
  updated: "2026-07-04"
  parent: "seedance-20"
  author: "Iamemily2050 (@iamemily2050)"
  repository: "https://github.com/Emily2040/seedance-2.0"
  openclaw:
    emoji: "🎬"
    homepage: "https://github.com/Emily2040/seedance-2.0"
---

# seedance-audio

Use this skill for dialogue, lip-sync review, sound layers, music, ambience, beat-alignment tests, audio-reference roles, and desync troubleshooting.

Load `[ref:audio-guide]` for the evidence boundary, exact-dialogue contract, authorized reference mapping, controlled tests, and repair workflow. Load `[ref:audio-post-delivery]` for stems, M&E, dubbing, loudness, synchronization, mix, or delivery guidance.

## Intent

Turn a sound idea into an evidence-scoped, reviewable production brief without confusing model-level audiovisual capability, surface access, or requested behavior with returned adherence.

## Evidence gate

Select the exact model, surface, operation, region, and evidence date before producing provider-ready syntax. Resolve these as separate facts: model audiovisual capability, surface audio input, surface audio output, dialogue, lip-sync, voice reference, multi-shot grammar, and returned adherence. Unknown support fails closed.

A model announcement does not activate a surface. An accepted audio upload does not prove audio output, dialogue, voice fidelity, or lip-sync. A provider example does not guarantee adherence or transfer its syntax to another operation.

## Exact dialogue

Before rendering dialogue, require:

- one resolved speaker per turn;
- exact quoted utterance;
- spoken-language tag independent of prompt locale;
- ordered turn linked to a shot or visible event;
- delivery direction;
- subtitle policy;
- voice-source role and authorization where relevant.

Keep the utterance byte-identical across English and Chinese instruction renderings. A translated dub is a new semantic variant. The current generic audio description does not satisfy this contract; until a versioned contract and checker accept it, return a compatibility blocker instead of inventing or translating speech.

## Reference and sound planning

Assign one reference to one explicit target role, with exclusions. Use the selected surface profile's structured role, evidenced ordinal, or opaque handle exactly; never invent provider syntax or rely on upload order.

Treat tempo, mood, ambience, music, voice character, exact words, speaker identity, and lip-sync as different roles and acceptance checks. A rights-cleared voice input may be tested only where the selected operation accepts it for the named role; do not promise cloning, exact playback, speaker fidelity, or direct lip-sync. Route unclear real-person voice or protected-music rights through `[skill:seedance-copyright]`.

Use a compact semantic brief, not a claimed priority ladder: `Dialogue: ... Spoken language: ... Sound: ... SFX: ... Music: ... Silence: ... Subtitles: ...`. Include only story-critical layers. Let the selected surface profile render any operation-specific syntax.

## Controlled production heuristics

- Start with one short, performable clause, one visible speaker, stable framing, and minimal competing action.
- Review speaker, exact words, intelligibility, mouth movement, event timing, sound presence, and mix separately.
- For multiple speakers, use short ordered turns; split into controlled single-speaker clips when reliability matters.
- For beat alignment, request one named cue and one visible event. This is an editorial test, not proof of an audio clock or internal mechanism.
- When sequence state is present, read completed/active dialogue, ambience, music phase, SFX phase, current scope, bindings, exclusions, surface policy, continuity locks, and reserved future beats. Verify continuity rather than assuming it.
- Plan post-dubbing, score continuity, subtitles, and final mix where generation cannot pass the required checks.

## Failure repair

- Desync: verify operation support, shorten the line, lock framing, remove head turns, and reduce competing sound/action.
- Wrong speaker or words: repair the exact speaker/utterance/turn contract; split turns.
- Audio absent: distinguish unsupported output from prompt non-adherence before retrying.
- Reference conflict: restore one-reference/one-role authority and explicit exclusions.
- Beat miss: reduce to one cue/event pair and measure the returned error.
- Overbusy mix: remove nonessential layers according to story priority, not a claimed model priority.

## Output contract

Return the selected scope and evidence status; unresolved boundaries; speaker/utterance/spoken-language/turn/subtitle/rights contract; sound layers; one-reference/one-role mapping and exclusions; lip-sync and timing acceptance checks; prompt-ready output only if a surface profile supports it; and post/delivery notes where needed.
