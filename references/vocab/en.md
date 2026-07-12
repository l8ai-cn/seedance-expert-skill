# English Vocabulary

Use this reference when the requested prompt or production handoff is in English. Replace empty quality words ("cinematic, stunning, 8K") and ambiguous production shorthand with observable direction. Binding is a separate typed step: the selected profile preserves an external opaque handle, derives an evidenced media ordinal, or uses structured roles with no token. Never translate provider syntax.

| Function | English wording | What it decides |
|---|---|---|
| Request role | assign the supplied opening image as first frame | carries the explicitly assigned visible opening state and opening composition; do not invent a prompt token for a structured field |
| Request role | assign the supplied endpoint image as last frame | sets the final visual target; do not invent prompt text for a structured field |
| Binding clause | `locks character identity` | face, hair, and wardrobe stay stable |
| Binding clause | `controls camera movement only` | motion donor, no appearance transfer |
| Binding clause | `controls action rhythm only` | pacing donor, nothing else transfers |
| Binding clause | `controls tempo and mood only` | the clock of the edit, not its content |
| FirstLastFrame | `keep the first frame unchanged` | anchors the opening state |
| FirstLastFrame | `treat the last frame as the final visual target` | endpoint, not mood reference |
| FirstLastFrame | `one continuous motion, no jump cut` | forces a single transition path |
| FirstLastFrame | `preserve the same character, wardrobe, and layout` | continuity lock across frames |
| Camera | `slow push-in` | replaces "cinematic zoom" |
| Camera | `pull back to reveal the space` | motivated reveal, not "epic wide" |
| Camera | `stable lateral tracking` | clean sideways travel |
| Camera | `locked medium shot` | stability for faces and dialogue |
| Camera | `macro close-up` | material and product detail |
| Camera | `low-angle shot` | stature without the word "epic" |
| Camera | `over-the-shoulder shot` | conversation geometry |
| Camera | `handheld with slight breathing sway` | documentary energy, controlled |
| Shot | `medium close-up` | emotion with context |
| Shot | `wide establishing shot` | place before people |
| Shot | `three-quarter profile` | dimensional face angle |
| Lens | `24mm wide spatial feel` | space and context |
| Lens | `50mm natural portrait perspective` | honest faces |
| Lens | `macro lens on material detail` | texture as the subject |
| Lighting | `soft backlight` | separation without glow words |
| Lighting | `warm practical light from the left` | sourced, directional warmth |
| Lighting | `cool moonlight rim` | night shape without "moody" |
| Lighting | `volumetric light through thin mist` | visible beams, physical cause |
| Lighting | `wet asphalt reflecting neon` | the reflection is the light |
| Motion | `fog parts around the footsteps` | environment reacts to subject |
| Motion | `droplets merge and slide down the label` | product motion, physical |
| Motion | `a slow head turn that stops` | acting beat with an endpoint |
| Motion | `fabric settles after the gesture` | follow-through proves the move |
| VFX | `gold particles rise, catch the backlight, and dissipate` | source, path, endpoint |
| VFX | `thin electrical arcs crawl along the cable` | effect anchored to an object |
| VFX | `cold vapor rolls over the rim and sinks` | density and direction |
| Audio | `quiet room tone` | silence with presence |
| Audio | `one clear spoken line in quotes` | dialogue the lip-sync can hold |
| Audio | `a single soft metallic tick` | one sound, one event |
| Audio | `no music until after the line` | mix priority stated plainly |
| Audio | `distant traffic bed under rain` | layered ambience, no slop |
| Text | `no on-screen text, no watermark` | text belongs in post |
| Editing | `match cut on the circular shape` | named transition, not "cool" |
| Editing | `hard cut on the downbeat` | edit tied to the sound |
| Constraint | `keep the logo, label, and shape unchanged` | product identity lock |
| Constraint | `no identity change, no object redesign` | drift guard |
| Constraint | `one action, one camera move` | the budget rule in six words |
| Constraint | `nothing else moves` | isolates the hero motion |
| Safety | `staged confrontation, no graphic injury` | action without harm reading |
| Safety | `original character with broad archetype traits` | identity without likeness |
| Safety | `prop object handled safely` | objects without threat reading |

## Dialogue Notes

Test the exact surface, model version, line, voice path, and framing. The retained evidence does not establish a universal ranking or English word-count limit.

- Start with one short, performable clause and measure its actual spoken duration and articulation load.
- Expand only after the same surface, operation, voice path, and framing pass a controlled test.
- A written beat between sentences is field-reported to help on some surfaces: `She pauses, then continues:`. Treat it as a testable prompt variant, not a synchronization mechanism.

## Paired V7 Realization Boundary

When a validated scene IR and paired English/Chinese catalog are available, `scripts/prompt_compile.py` renders the authored English forms and `scripts/semantic_lint.py` checks structural parity. The compiler does not translate the scene IR. Entity IDs, event order, causal relations, camera semantics, audio links, and requested invariants must stay aligned with the Chinese trace. Keep stable entity names instead of inferring pronouns. V7-07 rejects dialogue and voiceover because the current IR lacks an exact utterance contract. Missing or contradictory language forms fail closed.

## Slop Traps

English prompts attract empty evaluation words. Each adds tokens and zero signal; replace with something a camera, microphone, light meter, or stopwatch could detect.

| Slop | Say instead |
|---|---|
| cinematic | name the shot scale, camera move, and light source |
| epic | physical scale: crowd size, lens distance, structure height |
| stunning / breathtaking | the one visible contrast or reveal that earns it |
| beautiful | color, texture, material, light behavior |
| masterpiece / award-winning | delete; quality is not a request |
| 8K / ultra-HD / hyper-detailed | delete; resolution is a render setting, not prose |
| dynamic | the specific movement, its speed, and its endpoint |
| dramatic | blocking, shadow, silence, or camera pressure |
| atmosphere of mystery | what is hidden, by what: doorway, shadow, fog |
| ultra-realistic | material behavior, skin texture, natural motion |
| insanely detailed | the two details that matter, named |
| trending / viral style | the actual format: vertical, fast hook, caption-safe framing |

## Ambiguity Repairs

Use this only to clarify safe filmmaking language, never to disguise intent or evade a safety decision. Genuinely prohibited content routes to a plain refusal via the filter skill.

| Trigger-prone English | Professional clarification |
|---|---|
| shoot the scene / shooting | film the scene, capture the take |
| kill the lights | cut the lights to black |
| gun it / shot after shot | accelerate hard / take after take |
| execution of the move | the move performed cleanly |
| dead silence | held silence, room tone only |
| blow up the image | enlarge the image to full frame |
| fight breaks out | choreographed action beat begins, no graphic injury |

Anything genuinely risky - minors, real-person likeness, sexual or graphic content - is not a wording problem; route it to the filter skill's boundary for a plain refusal.

Load `filter-vocab.md` for the full false-positive repair table and `anti-slop-lexicon.md` for the core replacement rule.
