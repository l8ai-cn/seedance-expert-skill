# Multilingual Community Examples

These are original, safety-screened examples distilled from public multilingual Seedance 2.0 practice. Use them as structures and vocabulary patterns, not copied community prompts.

Binding notation: `binding(name)` denotes a typed segment, never literal prompt text. A selected profile preserves an externally captured handle, derives an evidence-pinned ordinal, or assigns a structured role. Do not attach language-specific particles directly to an unknown opaque handle; separate the rendered binding from its clause with punctuation.

## Boundary

Language mixing is an operator and collaboration choice, not a proven way to improve model understanding or bypass moderation. Use it only when it makes a benign production instruction clearer. Do not use another language to hide unsafe content, protected identity copying, real-person imitation, graphic harm, or platform-rule evasion.

Safe language mixing means:

- Keep each externally supplied opaque handle byte-exact; let an API profile derive its own ordinal; never translate either in language prose.
- Keep technical camera terms in English only when the operator explicitly prefers that shared vocabulary: `35mm lens`, `locked medium shot`, `slow dolly-in`, `no text`.
- Use Chinese role clauses when a surface or collaborator expects them: `锁定主体身份`, `仅参考运镜`; the typed renderer inserts any exact handle separately.
- Use the target dialogue language only for the spoken line.
- Use local-language constraints to remove ambiguity, not to soften an unsafe request.
- If a safe prompt is blocked, rewrite the scene with clearer production context, ownership, age/consent if relevant, non-graphic wording, and narrower target/dimension transfer.

## V7 paired-language boundary

A paired English/Chinese rendering is not runtime translation. One validated scene IR supplies the IDs, event graph, camera semantics, audio links, and invariants; a closed catalog supplies English and Chinese forms for those exact semantic nodes. `scripts/prompt_compile.py` renders one locale without inventing text, while `scripts/semantic_lint.py` verifies that both outputs carry the same structural trace. The catalog records only an unauthenticated human-attestation declaration. A bilingual reviewer must separately approve translation quality, compiler grammar, and the final pair because matching IDs and placeholders cannot prove that two natural-language clauses mean the same thing.

Keep entity names stable across every event. Do not infer gendered pronouns or omit the Chinese subject when doing so could make the actor unclear. V7-07 rejects dialogue and voiceover because the current IR lacks an exact utterance contract. When a later contract adds dialogue, keep the exact spoken line unchanged between prompt-language variants; a translated dub is a new semantic variant. Missing locale forms, placeholder mismatch, ambiguous speaker identity, unsupported provider syntax, or contradictory event order must fail closed.

## What Works

| Pattern | Use it for | Operator rationale |
|---|---|---|
| Chinese role binding + English camera | R2V, I2V, FLF2V | use only when collaborators have chosen this mixed production vocabulary |
| Local-language dialogue + English blocking | Lip-sync scenes | preserves the authored spoken line while using the operator's chosen blocking language |
| English safety/constraint block | Community-shared prompts | use when all reviewers understand these exact terms; otherwise localize them |
| One-language prompt + bilingual glossary note | Translation work | Avoids mixing grammar when the user needs a polished final prompt. |
| Bilingual clarification | Safe prompts with ambiguous production terms | records the same benign production meaning in terminology the operator can audit |

## What To Avoid

- Do not translate unsafe identity, harm, or adult-content terms into another language to sneak them through a filter.
- Do not mix multiple style systems in one prompt: cinematic realism, watercolor, anime, claymation, and documentary handheld in one shot usually creates visual mush.
- Do not let language mixing hide reference authority. If a bound video wins camera motion, name that target/dimension and exclude its identity, set, style, audio, and other observed leakage.
- Do not mix protected IP names in one language with “generic” wording in another; rewrite the concept into an original world.
- Do not over-pack multilingual constraints. Five precise constraints beat twenty negative phrases.

## Chinese-English Patterns

For a Chinese-language workflow, start from the role of each reference, then write one visible action and one camera move. Preserve imported surface handles only through typed binding segments, even inside Chinese sentences.

**Official-style role formula**

`binding(character)` + `：锁定原创角色身份与服装；` + `binding(street_mood)` + `：仅参考雨夜街道氛围；` + `binding(camera_reference)` + `：仅参考 slow lateral tracking，不复制人物、地点或品牌。原创角色穿过湿润站台，停在一盏闪烁灯下。Camera: locked medium-wide, 35mm lens, one slow side track. Sound: rain, footsteps, no music.`

**False-positive repair for safe staged action**

`原创成年角色进行 staged confrontation，非写实伤害、无血腥、无真实武器。动作是 choreographed action beat：角色后退一步，桌面道具滑落，镜头固定中景。Lighting: low warm practical, blue window rim. Sound: chair scrape, breath, silence after.`

**Product preservation**

`binding(product)` + `：产品参考。严格保持logo、标签、瓶身形状、颜色和盖子不变。Only motion changes: condensation beads merge and slide down the glass. Camera: slow dolly-in to label detail. Sound: soft room tone, single glass tick.`

## Japanese-English Patterns

For a Japanese-language workflow, keep identity, costume, frame layout, motion endpoint, and post-production text handling explicit. Avoid vague quality words unless they are decomposed into camera, light, material, and action.

**Portrait micro-performance**

`binding(character)` + `：人物の顔、髪型、衣装、背景構図を保持。動きは小さく：一度まばたきし、視線を少し下げ、最後に控えめに微笑む。Camera: locked medium close-up, no reframing. Lighting: soft window light from frame right. Sound: quiet room tone.`

**Low-angle commercial shot**

`オリジナルの宅配ロボットが夜明けの濡れた歩道をゆっくり進む。地面すれすれのローアングル、slow push-in、35mm lens feel。濡れた路面に朝の光が反射し、最後にロボットが小さく停止する。No text, no logo, no extra people.`

**Dialogue in Japanese with English blocking**

`Character A faces camera in a locked medium close-up and softly says, "もう一度だけ。" Keep head still during the line, small mouth movement, no dramatic turn. Lighting: warm interior practical, cool rain reflection on wall.`

## Korean-English Patterns

For a Korean-language workflow, separate subject lock, camera movement, lighting, audio, and textless delivery. Begin dialogue testing with stable framing, minimal head movement, and one short line; do not treat this as a language-specific capability ranking.

**Melodrama micro-expression**

`현대 아파트 주방, 두 명의 original adult characters only. Character A lowers a ceramic mug and looks away; Character B stays near the window, no approach. Camera: locked medium-wide, subtle handheld breathing sway. Lighting: warm tungsten practical, faint blue city spill. Sound: refrigerator hum, fabric movement, no music.`

**Broadcast realism**

`동네 야간 농구장, original players only, no brands. Camera: handheld sideline broadcast feel, slight autofocus correction, practical court lights, natural crowd ambience. One beat: player catches pass, pauses, shoots, ball leaves frame at final second.`

**Korean dialogue with clear framing**

`Character A sits at a cafe table, locked medium close-up, shoulders still. She says, "괜찮아, 천천히 말해." Keep the line short and dry, no music under dialogue, soft cafe room tone.`

## Spanish-English Patterns

**Product ad**

`binding(product)` + `: referencia del producto; conservar forma, etiqueta, logo y color sin cambios. Solo cambia el ambiente: una luz cálida cruza el vidrio y aparecen gotas pequeñas. Camera: slow slider from left to right, locked product scale. Sound: room tone, soft glass tap at the end.`

**Three-beat story**

`0-5s: plano general de una estación vacía al amanecer, Character A entra desde la izquierda. 5-10s: slow dolly-in as she finds a folded map. 10-15s: she closes the map and looks toward the train lights. Constraints: original character, no logos, no text overlays, one continuous mood.`

**False-positive repair**

`Escena de suspense no gráfica: puerta cerrada, respiración, sombras en la pared, objeto de utilería sobre la mesa. No daño visible, no arma real, no sangre. Camera: locked close-up on the character's hand stopping before the handle.`

## Russian-English Patterns

**Structured product prompt**

`binding(product)` + `: референс продукта; сохранить логотип, этикетку, форму и цвет без изменений. Меняется только свет и микродвижение среды: теплый блик проходит по стеклу, капли медленно стекают вниз. Camera: locked medium product shot, slow push-in. Sound: quiet room tone.`

**Reference authority map**

`binding(character)` + `: оригинальный персонаж и плащ. ` + `binding(camera_reference)` + `: only camera rhythm, not people, place, costume, or brand. ` + `binding(tempo_reference)` + `: только темп. Персонаж идет по мокрой улице, останавливается под фонарем, финальный взгляд влево.`

**Safe staged tension**

`Постановочная напряженная сцена без натуралистичных деталей: взрослый оригинальный персонаж отступает от закрытой двери, роняет ключи, затем замирает. Camera: locked medium shot. Lighting: low warm practical plus blue window rim. Sound: key drop, breath, no music.`

## Multilingual Prompt Triage

When a multilingual prompt fails, repair in this order:

1. Remove protected identities, brands, and copied scenes in every language.
2. State the safe production context: staged, original, authorized, non-graphic, no real person.
3. Choose exactly one winner per applicable target/dimension; one asset may win several compatible dimensions.
4. Keep dialogue in the speaker language, but keep camera and constraints in the clearest language for the operator.
5. Reduce the prompt to one visible beat and one camera move.
6. If it still blocks, change the creative surface, not just the language.

## Global Production Handoff Patterns

Use these when the collaborator is not only prompting, but preparing a shot for a director, editor, localization team, or client.

| Language context | Production-safe structure |
|---|---|
| Chinese-English shot list | `Shot ID + typed target/dimension authority map + action endpoint + Camera in English + 后期备注: textless/localized copy in post` |
| Japanese review notes | `ショット目的 + 保持する要素 + 修正する動き + postで追加する字幕/コピー` |
| Korean dialogue handoff | `대사 + locked framing + speaker tag + 자막/더빙은 후반 작업에서 처리` |
| Spanish client versioning | `versión 15s/9:16 + producto protegido + texto en post + subtítulos separados` |
| Russian delivery note | `роль референса + что не менять + textless plate + отдельные субтитры/озвучка` |

### Chinese-English client shot

`S01_SH02: ` + `binding(product)` + `：锁定产品logo、标签、瓶身比例；` + `binding(camera_reference)` + `：仅参考 slow slider rhythm，不复制环境。产品在黑色亚克力台面上，暖色条形光扫过瓶身，最后停在正面四分之三角度。Camera: locked macro-to-medium push-in. Post: no generated text; add Chinese/English campaign copy in edit.`

### Japanese localization handoff

`binding(character)` + `：人物と衣装を保持。Character A says "I am ready" in English, locked medium close-up, no head turn. Post note: 日本語字幕と吹替は後処理で作成、画面下部を空ける、焼き込み文字なし。`

### Korean social cutdown

`9:16 모바일 컷다운, original product centered, no edge-critical action. Camera: slow push-in only. Sound: one clean product click. Post: 한국어 자막과 법적 문구는 편집에서 추가, textless plate required.`

### Spanish delivery note

`Versión 15s horizontal y 6s vertical. ` + `binding(product)` + `: conserva producto, etiqueta y color. No texto generado dentro de la imagen; entregar placa limpia para copy localizado. Subtítulos, claims y CTA se agregan en postproducción.`

### Russian QC handoff

`binding(character)` + `: сохраняет оригинального персонажа и костюм; ` + `binding(tempo_reference)` + `: задает только темп. Камера фиксированная, средний план, один короткий жест. Post/QC: отдельные русские субтитры, textless version, проверить липсинк и отсутствие изменений лица.`
