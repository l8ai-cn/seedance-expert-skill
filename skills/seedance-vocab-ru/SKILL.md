---
name: seedance-vocab-ru
description: "This skill should be used when the user asks for Russian Seedance 2.0 prompt wording, Russian cinematic vocabulary, or translation of camera, lighting, action, VFX, audio, and production terms into Russian."
license: MIT
user-invocable: true
tags:
  - russian
  - vocabulary
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

# seedance-vocab-ru

Use Russian cinematic vocabulary when the user asks for Russian prompt wording, bilingual delivery, compact translation, role binding, first/last-frame workflow, or production vocabulary for camera, lighting, action, VFX, audio, and constraints. Binding is a separate typed step: a selected profile preserves an external opaque handle, derives an evidenced ordinal, or uses structured roles with no token.

## Intent

Give Russian-speaking users natural, ordered production language while marking surface, voice, and dialogue uncertainty honestly. Do not infer a capability ranking or accent outcome from the prompt language.

## Usage Rule

Translate production intent, not every English word. Russian prompts should stay compact, concrete, and ordered by subject, action, camera, light, sound, and constraint.

Load `[ref:vocab/ru]` for dense role-binding, first/last-frame, camera, lighting, audio, edit/extend, constraint, and safety vocabulary.

| Function | Russian wording |
|---|---|
| Camera | `медленный наезд камеры`, `боковое сопровождение`, `фиксированный средний план`, `нижний ракурс`, `крупный план` |
| Lighting | `контровой свет`, `мягкий свет из окна`, `теплый практический источник`, `холодный лунный свет`, `контурная подсветка` |
| Motion | `медленно поворачивается`, `быстро проходит через кадр`, `капли стекают вниз`, `дым мягко рассеивается` |
| Audio | `тихий фон помещения`, `короткая реплика`, `мягкий металлический щелчок`, `без музыки` |
| First/last frame | assign verified structured endpoint roles; prompt `естественный переход к последнему кадру` without invented tokens |
| Constraints | `сохранить логотип, этикетку и форму без изменений` |

## Compact Pattern

After the typed reference binding: `— референс; сохранить лицо/форму продукта/логотип без изменений. Меняются только [движение/свет/камера]. Камера: [одно движение]. Звук: [аудиосигнал].`

## De-Slop Rule

When the prompt leans on `кинематографичный`, `эпичный`, `атмосферный`, `потрясающий`, or `высокое качество`, load the Slop Traps table in `references/vocab/ru.md` and decompose each into the physical elements that produce it - движение камеры, источник света, материал, звук.

## Dialogue Rule

For spoken Russian, load the Russian Dialogue Notes in `references/vocab/ru.md`: start with one short line and one named speaker, test Cyrillic and transliterated variants as separate operator choices when useful, and keep a post-dub plan for longer voiced pieces.

## Output Contract

Return Russian prose segments, an optional English gloss, and the unchanged typed binding plan for surface rendering.
