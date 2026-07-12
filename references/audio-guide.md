# Audio Guide

Use this reference for detailed audio, dialogue, beat-sync, ambience, and lip-sync workflows. Keep audio roles explicit and avoid promising exact platform behavior unless the active surface documents it.

For professional audio post, stems, M&E, dubbing, loudness, or delivery checks, also load `audio-post-delivery.md`.

## Evidence boundary before prompting

Audio support, accepted reference types, dialogue synthesis, lip-sync controls, and output behavior are surface- and operation-specific. Field observations can propose a test but cannot reveal the model's internal audiovisual architecture or establish a universal language ranking.

- Confirm that the active surface and operation expose the requested audio or lip-sync control before relying on it.
- Name the intended ambience, sound effect, dialogue, music, rhythm, or silence as an observable production requirement; review the returned take rather than assuming implicit sound behavior.
- Treat mouth movement, spoken audio, speaker identity, and timing as separate acceptance checks.
- Some field reports describe voice confusion, timing drift, or garbled on-screen text on complex tasks. Keep dialogue and competing action small enough to diagnose, then budget retakes or post work.
- Do not attribute a language difference to training data or another unpublished mechanism. Record it as an observation tied to the exact line, voice path, model, surface, operation, and date.

## Dialogue capacity: conservative tests

No official cross-surface per-language dialogue limit is retained. The values below are conservative starting tests from field reports, not capability limits and not a ranking between languages.

Count the actual spoken duration and articulation load, not just prompt words. Word counts do not compare cleanly across languages. Start with one short, performable clause and extend only after the exact surface passes a controlled test.

| Spoken-language context | Conservative first test | Review note |
|---|---|---|
| English | one line of about 5-10 words | measure duration, articulation, and sync on the selected voice path |
| Mandarin | one short clause; count spoken syllables and duration | do not infer performance from Chinese prompt compactness |
| Japanese | one short line | mora timing makes English word-count comparisons unhelpful |
| Korean | one short line | retained quantitative evidence is limited; report uncertainty |
| Russian | one short line, initially under 10 words | treat accent and timing as take-level observations, not universal properties |

If a line fails, shorten it, simplify concurrent action, test an authorized voice-reference path only where the selected surface supports one, or plan a post-dub.

## Dialogue

- Keep lines short, preferably one sentence per speaker turn.
- Put spoken dialogue in quotes.
- Assign every line to a named speaker.
- State the spoken language separately from the prompt language.
- Use stable framing when mouth accuracy matters.
- Avoid head turns, large face movement, extreme camera moves, or busy hand action while reviewing lip-sync.
- If the line matters more than the environment, reduce music and SFX during the line.
- For every language, start with a short line and expand only from observed success on the selected surface. For a long localized piece, plan a post-dub.
- Inline audio tags are field-reported on some surfaces, for example `"..." [low warm voice][distant bell]`. Treat them as surface-specific syntax; use them only when the selected profile or current evidence supports them.

## V7 exact-dialogue boundary

The V7 scene IR's generic audio `description` does not establish an exact speaker, spoken language, or utterance. V7-07 therefore fails closed on `dialogue` and `voiceover`; `scripts/prompt_compile.py` must not invent or translate a line from that description. Later support requires a versioned contract with an exact audio-event link, one resolved speaker, the spoken-language tag, the exact utterance, and an explicit subtitle policy. `scripts/semantic_lint.py` can then check structural alignment and exact dialogue preservation, while a human reviewer still attests the surrounding translation.

Prompt locale and spoken language are independent. An English and a Chinese prompt that direct the same Mandarin line must keep that spoken line byte-identical. Translating the line for a dub creates a new semantic variant rather than a parity rendering. Subtitles, captions, and market copy remain post-production deliverables unless a separately verified workflow says otherwise.

## Audio reference mapping

An authorized audio reference can guide rhythm, pacing, mood, voice tone, ambience, music texture, or beat timing where the active operation supports that role. Bind it through `[ref:surface-prompt-profiles]`: preserve a captured opaque handle only when that operation requires one, otherwise let the profile derive its evidenced ordinal or assign its structured request role without a token. Do not promise exact playback. If the source contains a real voice or recognizable song, treat it as authorization-sensitive and convert it into broad sonic descriptors when rights are unclear.

On a surface that explicitly accepts a spoken-voice audio reference for the selected operation, an authorized recording can be tested as the timing and voice source. Do not call this a universal lip-sync compiler or assume exact reproduction. Use only your own recorded, licensed, or rights-cleared voice; route unclear real-person voice rights through `[skill:seedance-copyright]`.

When audio and video references compete, assign camera motion, subject motion, timing, and audio or voice independently. Exclude timing or audio transfer from a video donor when the audio reference is the selected authority; do not rely on upload order or media type.

| Role | Good wording | Avoid |
|---|---|---|
| Tempo | typed audio binding + `provides tempo only; foot taps match the downbeat` | copying a protected performance |
| Mood | typed audio binding + `provides calm sparse atmosphere` | exact replay claim |
| Voice tone | `soft, close-mic delivery` | imitating a named real voice |
| Ambience | `rainy street room tone, distant traffic bed` | dense competing sound layers |
| Conflict repair | typed video binding + `controls camera only`; typed audio binding + `controls beat timing` | two sources both controlling rhythm |

## Multi-character dialogue

Use separate speaker turns when reliability matters. For two-person exchanges, generate controlled single-speaker clips and composite in post when necessary. If two speakers remain in one prompt, write `Character A says... pause. Character B answers...` and keep the camera locked or gently motivated. Exact speaker order belongs in the semantic audio contract, not an inferred translation.

## Sound layer syntax

`Dialogue: Character A says "I found it." Sound: low room tone + distant rain. SFX: cup lands on table at 2s. Music: no music until after the line.`

## Beat-sync syntax

After the typed audio binding: `provides tempo only. On each downbeat: back wall light pulses once, dancer hits one pose, camera remains locked wide.` Use one visible event for each requested beat and review the returned alignment.

## Audio as a planning clock

A bound audio reference may be tested as an editorial timing brief: `cut on its beat; the turn lands on the drop; the door closes on the final hit.` This is a requested alignment and review target, not a statement about internal timing architecture.

- Tie each musical landmark to exactly one visible event.
- Start with a single clear rhythm; compare more complex material only after a controlled pass.
- When audio is the selected timing authority, exclude timing transfer from competing references and avoid a contradictory timestamp system.
- Verify continuity between calls rather than assuming it; multi-clip pieces normally receive their unifying score in post.

## Troubleshooting

- Desync: shorten dialogue, stabilize camera, remove head motion, reduce competing sound, and verify the source audio role.
- Wrong speaker: repair the exact speaker mapping; split lines when needed.
- Audio ignored: verify operation support, then remove competing music or SFX instructions.
- Overbusy mix: choose ambience plus one key SFX; remove music if dialogue matters.
- Lip-sync drift: use a locked medium close-up, no head turn, one short quoted line, and a simple expression.
- Audio-reference conflict: repair target/dimension authority and remove competing timing instructions.

## Post handoff boundary

Prompt audio can shape the requested performance and timing, but final mixes need post-production review. For paid or delivery work, record spoken language, subtitle and dubbing needs, M&E or stem needs, sync cues, and buyer loudness target separately from the prompt.
