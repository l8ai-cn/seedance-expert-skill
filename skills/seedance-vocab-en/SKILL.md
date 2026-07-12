---
name: seedance-vocab-en
description: "This skill should be used when an English Seedance 2.0 prompt is slop-heavy, generic, padded with empty quality words, tripping false-positive filters, or needs precise English production vocabulary for camera, lighting, motion, VFX, audio, and constraints."
license: MIT
user-invocable: true
tags:
  - english
  - vocabulary
  - anti-slop
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

# seedance-vocab-en

Use English when the user, operator, or delivery workflow requests it. Replace empty evaluation words and ambiguous production shorthand with concrete, observable direction. Binding is a separate typed step: a selected profile preserves an external opaque handle, derives an evidenced ordinal, or uses structured roles with no token.

## Intent

The purpose of this vocabulary is precision without padding: give the user exact production language so the intended action, camera, light, sound, and constraint remain reviewable.

## Usage Rule

If a camera, microphone, light meter, or stopwatch cannot detect it, rewrite it. Every sentence should name something visible, audible, or measurable: subject, visible action, camera, light source, sound, constraint.

| Function | English wording |
|---|---|
| Camera | `slow push-in`, `locked medium shot`, `stable lateral tracking`, `pull back to reveal`, `macro close-up` |
| Lighting | `soft backlight`, `warm practical light from the left`, `cool moonlight rim`, `wet asphalt reflecting neon` |
| Motion | `a slow head turn that stops`, `droplets merge and slide down`, `fabric settles after the gesture` |
| Audio | `quiet room tone`, `one clear spoken line in quotes`, `no music until after the line` |
| Constraints | `keep the logo, label, and shape unchanged`, `one action, one camera move`, `nothing else moves` |

## De-Slop Pass

Strip quality adjectives before adding anything: `cinematic`, `epic`, `stunning`, `masterpiece`, `8K`, `ultra-realistic`, `award-winning`, `hyper-detailed` all delete or convert to one observable detail each. A prompt that earns "epic" names the crowd size, the lens distance, or the structure height instead of the word.

## Filter-Aware Wording

Some production homonyms are ambiguous outside filmmaking context: `shoot the scene`, `kill the lights`, `gun it`, `dead silence`, `blow up the image`. Use the clearer production synonym (`film the take`, `cut the lights to black`, `accelerate hard`, `held silence`, `enlarge to full frame`). This is clarity for safe prompts only, never evasion. Anything genuinely risky routes to `[skill:seedance-filter]` for its boundary rule, not to a wording substitution.

## Compact Pattern

After the typed reference binding: `is the reference; keep identity, color, and shape unchanged. Only [motion/light/camera] changes. Camera: [one move]. Sound: [one cue]. Constraints: [lock].`

Load `references/vocab/en.md` for the full function-organized vocabulary and ambiguity repairs. Load `[ref:anti-slop-lexicon]` for the core replacement rule and `[ref:filter-vocab]` for the safe-language boundary. When a validated V7 scene IR and paired language catalog are available, let `scripts/prompt_compile.py` realize the English clauses and let `scripts/semantic_lint.py` verify structural parity; do not translate arbitrary IR prose at runtime.

## Output Contract

Return the de-slopped English prose segments, each replacement made (slop → observable detail), any filter-trip repair applied, and the unchanged typed binding plan for surface rendering.
