# Anti-Slop Lexicon

Replace empty evaluation language with observable production language. Concrete clauses such as camera verb + speed + viewpoint, light source + direction + behavior, and material + texture + motion are easier to review, compare, and revise than abstract quality words. This is an authoring and evaluation rule, not a claim about hidden model processing or a guarantee that one wording will improve every surface.

## The Six Slop Classes

| Class | Looks like | Repair |
|---|---|---|
| Empty evaluators | `cinematic, epic, stunning, beautiful, dramatic` | convert each to the one observable detail that earns it |
| Borrowed image-model tokens | `8K, masterpiece, award-winning, trending on ArtStation, Unreal Engine, RAW` | delete; resolution and quality are settings or outcomes, never prose |
| Tag salad | comma-separated keyword dumps ported from image prompting | rewrite as shooting-brief prose: one sentence per element - subject, action, camera, light, sound |
| Negation slop | `no blur, no artifacts, no distortion, no extra fingers` | prefer a positive, observable composition or state; keep only necessary constraint syntax |
| Adjective stacking | `gorgeous, breathtaking, mesmerizing sunset` | three synonyms make one weak claim; pick the single detail that matters |
| Feel-suffix words | `电影感 · 雰囲気のある · 감성적인 · atmosférico · атмосферный · vibey` | name the physical cause of the feeling; every vocab file has a language-specific Slop Traps table |

## Replacement Table

| Weak phrase | Replace with |
|---|---|
| cinematic | shot scale, camera move, lighting, grade |
| epic | physical scale, stakes, crowd size, lens distance |
| beautiful | color, texture, composition, material, light behavior |
| stunning / breathtaking | visible contrast, reveal, movement, or detail |
| dynamic | specific movement, speed, and endpoint |
| dramatic | blocking, shadow, silence, or camera pressure |
| ultra-realistic | material behavior, skin texture, lens artifacts, natural motion |
| cool transition | match cut, whip pan, dissolve, hard cut, object wipe |
| magical | particle behavior, glow source, motion path, interaction |
| professional | product lighting setup, clean background, controlled camera |
| masterpiece / award-winning | delete; quality is not a request |
| 8K / ultra-HD / high quality | delete; resolution is a render setting, not prose |
| atmosphere of mystery | what is hidden, by what: doorway, shadow, fog |
| insanely / highly detailed | the two details that matter, named |
| visually striking | the one frame the viewer remembers, described |
| trending / viral style | the actual format: vertical, fast hook, caption-safe framing |

## Tag Salad Repair

The tag list `girl, sunset, 8K, cinematic, beautiful light, masterpiece, detailed face` does not specify an action, camera move, or time order. Rewrite it as a reviewable brief: `A woman turns from the railing at sunset; the low sun flares behind her hair. Camera: slow push-in to a medium close-up. Sound: wind and distant surf.` Prefer one clear clause per production element to an unordered keyword list.

## Negation Rule

Prefer the desired observable state to a long list of possible defects. Instead of `no blur, no extra fingers, no watermark text`, write `hands rest still on the table`, `clean unbroken label`, or `empty sky above the skyline`. Keep necessary constraints such as `no on-screen text, no watermark` in the constraint slot. Whether positive wording changes generation behavior is surface-dependent and must be tested.

Rule: if a camera, microphone, light meter, or stopwatch cannot detect it, rewrite it.

Each language file in `references/vocab/` carries a Slop Traps table for its own community's empty words: English (`vocab/en.md`), Chinese (`vocab/zh.md`), Japanese (`vocab/ja.md`), Korean (`vocab/ko.md`), Spanish (`vocab/es.md`), Russian (`vocab/ru.md`).
