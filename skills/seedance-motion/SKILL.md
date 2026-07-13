---
name: seedance-motion
description: "This skill should be used when the user asks for body action, choreography, physics, object movement, movement timing, action continuity, stunt direction, or motion-reference mapping in Seedance 2.0."
license: MIT
user-invocable: true
tags:
  - motion
  - choreography
  - physics
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

# seedance-motion

Use observable verbs and consequences. Assign every motion state to a subject, object, camera, or environmental owner. Prefer one clear action with a reviewable clip endpoint over several vague actions competing for attention.

Load `[ref:reference-workflow]` for video-motion references, `[ref:shot-list-continuity]` for action handoffs across shots, `[ref:examples-by-mode]` for safe edit, extend, and R2V patterns, and `[ref:directing-engine]` when motion is performance: translate the scene's emotion into one true visible gesture per beat - a playable action with an objective and subtext - instead of an emotion word that gives no observable acceptance condition.

## Intent

Motion is the verb of the user's story, the thing they came to see happen. The useful unit is an authored before-state, change, and consequence that a reviewer can identify. Cyclic or continuing motion is valid when it is the intended endpoint; completion does not require every owner to stop.

## Motion Contract

State: owner, coordinate frame, action, direction, qualitative speed/trend, timing policy, visible consequence, continuity requirement, endpoint mode, source observation, and confidence. Keep subject, prop, camera, and environment motion separate.

| Motion type | Strong phrase | Weak phrase |
|---|---|---|
| Subtle acting | `Character A inhales, grips the cup tighter, then sets it down without looking away` | `she feels nervous` |
| Product material | `condensation beads gather, merge, and slide down the bottle neck` | `the product looks refreshing` |
| Choreography | `Character B ducks under the swinging bag, pivots left, and stops in a guarded stance` | `fast action fight scene` |
| Object physics | `paper receipt lifts in the fan breeze, flips once, and lands face-up` | `papers move dynamically` |
| Environmental motion | `rain streaks diagonally across the backlight while puddle ripples spread from footsteps` | `stormy weather atmosphere` |

## Observable Interaction Pattern

Use causal language as a planning and evaluation heuristic, not as proof of Seedance's internal physics architecture or physical accuracy. For material interaction, name the contact participants and visible before/after states: `the oak door swings shut; the nearby candle flames bend toward the doorway` is more reviewable than `the door closes dramatically`. Request visible cues such as landing compression, overshoot and recovery, skid distance, or displaced cloth, but do not claim they measure mass, force, momentum, or friction. Keep a material response and a performer's reaction as separate owner-scoped consequences. For a performance, reveal, or lighting beat, use a visible non-material state change instead of inventing contact physics.

Choose one endpoint mode: `held_static`, `dissipated_or_resolved`, `completed_with_motion`, `frame_exit`, `cyclic_phase_boundary`, or `open_handoff`. The endpoint completes the current clip's job. Unrelated rain, cloth, crowd, or camera motion does not invalidate a stopped subject endpoint.

## Timing Pattern

Use setup, action, and changed endpoint as an ordered planning shape. Timing syntax is surface- and operation-scoped: choose ordered phases or relative beats by default, and use exact ranges only when current evidence for the selected operation permits them. V7-07 rejects exact ranges and remains byte-stable; if `compile_required` is true, do not hand-edit its output to add timestamps.

When sound drives the motion, pair each important visible change with one relative beat or SFX, such as `light pulses on the downbeat; the hand releases the cup on the final chime`. Use exact seconds only under the selected surface timing policy. Do not ask for many cuts, locations, and micro-actions inside one short clip.

## Reference Motion Rules

For reference footage, use only owned, licensed, public-domain, stock, mocap, rehearsal, or self-recorded material. Bind the typed video source to motion, camera, timing, or blocking—not identity unless authorized—and resolve it through the selected surface policy. If a reference contains a real person, transfer only general motion or camera behavior and explicitly exclude likeness transfer.

## Stability Rules

Treat hands, faces, logos, and product geometry as fragile review targets when several actions are combined. Simplify motion around a required detail, test a stable camera for lip-sync, keep hand action readable, and separate product motion from environmental motion. These are conservative staging tests, not hidden-capacity rules.

## Sequence State

When sequence state is present, inherit each observed motion owner's coordinate frame, direction, speed/trend, action phase, source kind, confidence, uncertainty, current clip scope, continuity locks, typed bindings and surface policies, and reserved future beats. Do not infer motion from a still. Do not replay completed actions or perform a reserved beat early; a seamless continuation carries exactly the owners marked `carry_forward`, each backed by a matching open vector. `open_handoff` always carries; other moving/exit/cyclic completion modes carry only when explicitly marked.

## Output Contract

Return the owner-scoped motion phrase, causal event chain when needed, endpoint mode, declared camera coverage, selected timing policy, target/dimension reference authority if any, and repaired prompt language. Label the result as an authored request and review contract, not a physical prediction.
