# Audio Guide

Use this reference for audio, dialogue, ambience, sound effects, music, beat-alignment requests, and lip-sync review. It provides production heuristics, not a claim that every Seedance surface accepts audio or returns sound.

For professional audio post, stems, M&E, dubbing, loudness, or delivery checks, also load `audio-post-delivery.md`.

## Eight boundaries to resolve first

Select the exact surface and operation before writing prompt-ready audio. A model-level announcement, an accepted upload, and a returned behavior are different facts. Unknown support fails closed.

| Boundary | What must be established | What it does not establish |
|---|---|---|
| Model audiovisual capability | retained model-level evidence for relevant input or output modalities | availability on the selected product surface |
| Surface audio input | the selected operation accepts the required audio input and binding role | that the returned clip contains audio or follows the input |
| Surface audio output | the selected operation documents or demonstrates an audio-bearing result | dialogue, synchronization, mix quality, or repeatability |
| Dialogue | the selected operation supports requested speech behavior | correct speaker, exact words, or intelligibility |
| Lip-sync | the selected operation exposes or evidences lip-sync behavior | frame-accurate mouth alignment or identity preservation |
| Voice reference | an authorized voice input is accepted for a named role | cloning, exact reproduction, direct lip-sync, or speaker fidelity |
| Multi-shot grammar | the selected operation has current, scoped evidence for its shot/timing form | universal `Shot N` syntax, exact cuts, or timing adherence |
| Adherence | the returned take passes separately defined picture and sound checks | an internal mechanism or a guarantee for the next take |

For each positive statement, retain its model or provider, surface, operation, region, capture date, and claim ID. A field report can define a test; it cannot reveal unpublished audiovisual architecture or become a cross-surface capability claim.

## Exact-dialogue contract

A production dialogue request needs all of these semantic fields before it can be rendered:

- one resolved speaker for each turn;
- the exact utterance, preserved without paraphrase or translation;
- a spoken-language tag independent of the instruction/prompt locale;
- turn order and a link to the intended shot or visible event;
- delivery direction that does not alter the words;
- subtitle policy: none, post-production, or a separately verified surface workflow;
- voice-source role and voice-rights status where a recording is involved.

An English and a Chinese instruction prompt directing the same Mandarin line must keep that spoken line byte-identical. A translated dub is a new semantic variant. Do not infer a line, speaker, language, or subtitle policy from a generic audio description.

The current generic V7 audio description is insufficient for exact dialogue and voiceover, so the existing compiler correctly fails closed. A later versioned audio contract and checker should validate the fields above, unique speaker resolution, ordered turns, rights state, and byte-exact utterance preservation before rendering either locale. Until that contract is active, return a compatibility blocker rather than hand-editing a compiled prompt.

## Conservative dialogue test

There is no retained universal per-language capacity or language ranking. Start with one short, performable clause, one visible speaker, stable readable framing, and minimal competing action. Record the exact utterance, spoken language, voice path, model, surface, operation, region, date, and returned result. Expand only after that controlled case passes.

- Keep one sentence or clause per turn.
- Quote exact spoken words in the semantic brief and assign the named speaker.
- Avoid head turns, large face motion, extreme camera moves, or busy hand action while evaluating mouth movement.
- Treat speaker correctness, word correctness, intelligibility, mouth alignment, timing, and mix as separate acceptance checks.
- If a line fails, shorten it, simplify concurrent action, split the exchange, or plan a rights-cleared post-dub.

Do not use inline tags, magic tokens, reference ordinals, or other provider-looking syntax unless the selected surface profile and current evidence define them.

## Reference-role mapping

One reference gets one explicit target role for the current test. The fact that a surface accepts an audio file does not prove what the model will copy, generate, synchronize, or preserve.

Bind a reference only through the selected surface/operation profile. Preserve an opaque handle only when that operation requires one; otherwise use the profile's evidenced ordinal or structured request role. Never invent a token.

| Requested role | Test brief | Required review |
|---|---|---|
| Tempo | the reference supplies tempo only; one visible event is requested on a named beat | event-to-beat alignment |
| Mood | the reference supplies a calm, sparse atmosphere only | broad mood without protected-performance copying |
| Voice character | soft, close-mic delivery from an authorized source, only where supported | speaker, words, timbre, rights, and mouth movement separately |
| Ambience | rainy-street room tone with distant traffic | presence, continuity, and unwanted leakage |
| Camera donor | video controls camera only; exclude audio and timing transfer | camera behavior without donor sound leakage |

An authorized spoken recording may be tested only when the selected operation accepts that input for the named voice or timing role. Acceptance does not prove voice cloning, exact playback, speaker fidelity, or direct lip-sync. Use only owned, licensed, or rights-cleared voice material; route unclear real-person voice rights through `[skill:seedance-copyright]`.

When references compete, assign subject motion, camera motion, timing, ambience, music, and voice independently. Do not rely on upload order or media type to resolve authority.

## Sound brief

Use a human-readable semantic brief, then let the selected surface profile render any required syntax:

`Dialogue: Character A says exactly "I found it." Spoken language: English. Sound: low room tone and distant rain. SFX: cup contact on the visible landing event. Music: absent during the line. Subtitles: post-production.`

This ordering is a readability convention, not a provider command language or a priority ladder. Choose only the layers that matter; do not assume sound effects outrank music or dialogue internally.

## Multi-character dialogue

Use separate short turns and explicit resolved speakers. For reliability-sensitive work, generate controlled single-speaker clips and composite them in post. If multiple turns are tested in one generation, keep the camera stable and review speaker assignment and turn order independently. Never let localized instruction prose rewrite the exact utterances.

## Beat alignment as a test

Audio may be used as an editorial timing brief only where the selected operation accepts the required binding: one named cue, one visible event, and one acceptance check. Phrases such as `the light pulse is requested on the downbeat` state intent; they do not prove an audio clock, hidden timing architecture, exact synchronization, or repeatable adherence.

- Begin with one unambiguous cue and one visible event.
- Exclude timing transfer from competing references.
- Do not combine a beat brief with contradictory timestamp rules.
- Verify every returned take; plan cross-clip score continuity in post.

## Troubleshooting

- Desync: verify operation support, shorten the line, stabilize framing, remove head motion, and reduce competing sound/action.
- Wrong speaker or words: repair the exact contract; split turns instead of adding emphasis prose.
- Audio absent: distinguish unsupported output from ignored prompt intent; verify the active operation before retrying.
- Overbusy mix: remove nonessential layers according to story priority, not a claimed model priority.
- Mouth drift: use a locked medium close-up, one short line, simple expression, and a separate sync review.
- Reference conflict: restore one-reference/one-role authority and explicit exclusions.
- Timing miss: reduce to one cue/event pair and report observed error rather than inferring a mechanism.

## Post handoff boundary

Prompt audio is a requested performance and timing brief, not a certified final mix. For paid or delivery work, record spoken language, exact utterances, voice authorization, subtitle/dub plan, M&E or stem needs, sync cues, and buyer loudness target separately from the generation prompt.
