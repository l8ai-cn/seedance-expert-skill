---
name: seedance-continuation
description: "This skill should be used when a Seedance 2.0 user asks to continue, extend, make the next part, repair the tail, bridge between known frames, re-anchor drift, or create a successor prompt from accepted footage."
license: MIT
user-invocable: true
tags:
  - continuation
  - extend
  - continuity
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

# seedance-continuation

Use this for seamless continuation, intentional next shots, bridge clips, tail repair, and re-anchoring after drift. A continuation prompt must be grounded in accepted footage, not only in the old plan.

Load `[ref:continuation-handoff]`, `[ref:sequence-project-state]`, `[ref:prompt-compiler]`, `[ref:reference-transfer-contract]`, and `[ref:continuity-qc]`. Load `[ref:failure-atlas]` when the continuation failed or drift is visible. Load `[ref:directing-engine]` so the next clip inherits the project's directorial voice and its position on the long-form spine; the look never re-rolls between clips.

## Intent

The user already made something they accepted, and now they are trusting the story to continue from exactly where it really landed - not where the plan hoped it would. The soul of this skill is fidelity to what actually happened: honor the accepted footage as the only truth, refuse to invent the bridge, and ask for the real ending rather than guess it. Continuity is a promise that the film the user already has will not be quietly contradicted.

## Required Input Gate

Before writing any continuation prompt, require:

- `project_id`;
- current `clip_id`;
- valid `parent_clip_id`;
- `scene_id`, and whether the next clip stays inside the scene or crosses a scene boundary;
- full-story objective;
- final story outcome;
- next planned narrative job;
- next clip `felt_intent` - what the viewer should feel or notice;
- accepted previous clip or accepted final frame;
- `observed_end_state`;
- continuity locks;
- inherited directorial voice and arc position;
- semantic reference registry plus the active surface's opaque, derived-ordinal, or structured binding policy;
- active surface or conservative surface profile.

If the source is unavailable, say: "I have the story plan, but I do not have the actual ending of the previous generation. Upload the clip or its final frame - `python scripts/extract_last_frame.py <take>` pulls the final frame locally - or describe exactly what is visible at the end. I should not invent the continuation state."

Once a frame or clip is attached, run the Observation Fast Path from `[ref:continuation-handoff]`: fill only what the attachment can establish and ask about the remaining gaps. A still can show pose and framing but cannot establish owner velocity, camera movement phase, or audio phase. Never invent those fields.

Do not hide this uncertainty by writing a speculative prompt.

## Continuation Types

`seamless_continuation`: requested continuation of the same shot and geography, carrying the accepted source's observable owner-scoped open motion. This is a handoff contract, not a fidelity guarantee.

`intentional_next_shot`: an editorial cut is appropriate. Story continuity matters, but exact frame continuity is not promised. Do not call it seamless.

`bridge_between_known_states`: a defined start state and end state must be connected, often with first/last-frame generation when the active surface supports it.

`repair_tail`: the previous final seconds failed their named acceptance checks. Repair, edit, or regenerate the tail before continuing so the next opening does not canonize a rejected state.

`reanchor_after_drift`: identity, detail, geography, motion, audio, or world continuity degraded. Return to canonical identity, the strongest accepted final frame, a stable source clip, or a new intentional shot using canonical references.

## Scene Boundary Rule

Crossing a scene boundary defaults to `intentional_next_shot` opening from canonical references. Do not label a cross-scene request `seamless_continuation`; it conflicts with this workflow's scene contract. If the user explicitly asks for continuity across the boundary, record the reason and plan a separately reviewed bridge or intentional transition without predicting drift from the boundary alone.

## Canon Rule

Accepted observed footage overrides planned state. If the plan says the subject reached the car door but the accepted clip ends two steps away, the next prompt begins two steps away. It does not replay the terminal exit, and it does not assume the subject is inside the car.

Rejected footage never updates canon and never becomes a parent source.

Track `extension_depth` as consecutive output-sourced generations since the last canonical re-anchor; it resets to 0 when a clip opens from canonical references. The count is review context, not a failure threshold. Re-anchor when a named identity, layout, motion, endpoint, audio, or world-continuity check fails, or under an explicitly documented project policy chosen by the owner. No universal default or hard ceiling is supported.

Record motion and endpoints per owner. A subject may reach `held_static` while rain continues; a camera may remain `open_handoff` after the subject completes its action. Use one endpoint mode per relevant owner: `held_static`, `dissipated_or_resolved`, `completed_with_motion`, `frame_exit`, `cyclic_phase_boundary`, or `open_handoff`. Record `carry_forward` separately: it requires a matching open vector, and the successor must preserve that owner's domain, coordinate frame, direction, and speed trend exactly unless the transition is reclassified as a cut.

Every project-state-v2 clip declares `compile_required: true`. Use only a compiler compatible with that exact state contract. V7-07 remains byte-stable and does not support v2 motion/endpoint state; return a blocker rather than flattening it into hand-edited paired prompts. No v2 human-bypass path or provider activation exists in this contract.

## Output Contract

Return:

1. Continuation type.
2. Source evidence used.
3. Observed end state.
4. Next clip contract.
5. Intent echo: one line - "this clip exists so the viewer feels X" - confirmed before generation spends money.
6. Continuity locks and allowed changes.
7. Completed beats to exclude.
8. Reserved future beats to exclude.
9. Final natural-language Seedance prompt for the current clip only.
10. Updated Project State Capsule or a request for missing source evidence.
