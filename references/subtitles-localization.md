# Subtitles And Localization

Use this reference when a Seedance project needs global release, subtitles, captions, forced narratives, dubbing, multilingual prompts, or market-specific copy.

## Localization Plan

| Deliverable | Purpose | Prompt/post boundary |
|---|---|---|
| Subtitles | translate spoken dialogue | create in post from approved script, not generated as moving text |
| SDH captions | dialogue plus important sound cues | plan sound cues and speaker IDs; author captions in post |
| Forced narrative | translate signs, texts, or off-language lines | avoid burned-in AI text; keep clean plates |
| Dubbing | localized voice performance | use short speaker turns, stable framing, and post-sync review |
| M&E | music and effects without dialogue | plan audio layers separately |
| Textless | picture without titles/lower thirds | generate clean background/action plates |
| Market copy | local tagline or legal claim | add in design/edit tools after legal approval |

## V7-09 exact-language boundary

Prompt locale, spoken language, subtitle locale, and dub language are four separate fields. Changing the English/Chinese instruction wrapper must not change an exact spoken line. Translating that line creates a new dub semantic variant with a new event ID, speaker mapping, language tag, utterance hash, and relationship to the source line.

The initial V7-09 candidate compiler accepts only `none`, `post_subtitles`, `post_sdh_captions`, or `post_forced_narrative`. Post modes require a clean picture policy. Generated/burned-in subtitles fail closed until a separately evidenced future surface policy and review contract exists.

An AV take review checks unexpected in-picture text independently from speech accuracy. A final frame can show accidental text but cannot prove dialogue, audio timing, or lip sync.

## Prompting For Subtitle-Friendly Footage

- Keep dialogue short and assigned to a speaker.
- Use stable medium or medium close-up for important spoken lines.
- Leave negative space for captions when needed.
- Avoid generated subtitles or small moving text; the V7-09 candidate path rejects generated subtitle requests.
- Preserve clean plates for markets where copy changes.
- For multilingual dialogue, specify which language is spoken and which language is captioned in post.

## Reading And Placement Checks

For professional output, check:

- captions do not cover faces, product claims, logos, legal disclaimers, or key action;
- subtitles have enough reading time for the target language;
- speaker changes are clear;
- SDH sound cues describe story-relevant sounds only;
- forced narratives are used only when needed;
- line breaks preserve meaning;
- formal/informal address matches region and character relationship.

## Global Prompt Handoff

| Language need | Safe wording |
|---|---|
| Chinese prompt with English camera terms | Chinese for role binding, English for camera/lens terms if clearer; never for evasion |
| Japanese market copy | keep generated shot textless; add Japanese copy in post |
| Korean dialogue | short quoted line, stable face framing, no head turn |
| Spanish captions | plan caption-safe lower third and avoid burned-in source text |
| Russian localization | deliver textless plate plus separate Russian subtitle/copy file |

## Cultural Localization

Ask what must localize: dialogue, product claim, holiday/season, gesture, sign, food, wardrobe, legal text, or music cue. Do not assume a literal translation is a market-ready localization.

## Safe False-Positive Repair

Mixed-language wording may clarify benign production context and target/dimension reference authority, but it must not hide unsafe content. If a blocked prompt includes violence, real-person likeness, protected IP, sexual content, or evasion-like phrasing, repair the underlying issue in every language.
