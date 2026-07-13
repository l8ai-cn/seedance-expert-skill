# Continuation Handoff

Use this reference for every continue, extend, next-shot, bridge, repair-tail, or re-anchor request. A successor prompt must be based on accepted source footage or an accepted final frame.

## Source Gate

Do not write a continuation prompt until these are known:

- project ID and current clip ID;
- parent clip ID;
- `scene_id`, and whether this continuation stays inside the scene or crosses a scene boundary;
- accepted source clip or accepted final frame;
- observed end state;
- next clip's `felt_intent` - what the viewer should feel or notice;
- completed beats;
- reserved future beats;
- continuity locks;
- semantic reference registry plus the active surface's opaque, derived-ordinal, or structured binding policy;
- active surface or conservative surface profile.

If the source is missing, ask for the clip, final frame, or an exact visible-end description. Do not invent it.

## Observation Fast Path

The user should never be the state sensor. The moment a final frame or the accepted clip is attached, the AGENT fills the observation record from what is visible and asks only about what the attachment cannot show:

- **Final frame attached:** the agent reads pose, screen position, wardrobe and props, environment, visible lighting state, and framing directly off the still. Motion direction, speed/trend, camera movement phase, and audio phase remain unknown unless another source supplies them; ask only targeted questions about those gaps.
- **Full clip attached:** the agent records observable subject, prop, environment, and camera motion separately, plus audible phase when present. State confidence and uncertainty; a clip observation does not reveal hidden force, momentum, or model state.
- **Nothing attached:** only then fall back to asking the user to describe the visible end - and offer the extraction tool first.

For users working with this repository locally, `python scripts/extract_last_frame.py <take>` extracts the final frame of an accepted take (`--first-frame` for the opening; `--emit-record` prints this observation skeleton with the frame-readable and frame-blind categories marked). The extracted frame doubles as the continuation image reference, so one attachment pays for both the observation record and the next generation's anchor.

Do not interrogate the user across all record categories when an attachment is present: fill what is visible, state `observation_confidence`, and confirm rather than ask.

## Handoff Record

Record:

- observed start state;
- observed end state;
- owner-scoped open motion: owner ID, coordinate frame, direction, qualitative speed/trend, action phase, observation source, confidence, and uncertainty;
- camera phase;
- screen direction;
- character pose and gaze;
- prop ownership, position, and condition;
- location and persistent environment;
- lighting phase;
- ambience, completed dialogue, active dialogue, music phase, and SFX phase;
- observation confidence and uncertainties.

## Seamless Versus Next Shot

Use `seamless_continuation` only when the next generation is intended to continue the same shot, geography, and owner-scoped open motion from accepted footage. This is the requested handoff contract, not a guarantee that the returned take will preserve it.

A scene boundary defaults to `intentional_next_shot`: open from canonical references and reset `extension_depth` to 0. Do not promise seamless continuation across a scene boundary.

Use `intentional_next_shot` when an editorial cut is appropriate. It may preserve story continuity, but it does not promise exact frame continuity.

Use `bridge_between_known_states` when a known start state must reach a known final state.

Use `repair_tail` when the final seconds of the parent clip failed.

Use `reanchor_after_drift` when a named continuity check fails. Keep extension depth as context, but do not infer a universal failure threshold from the count.

## Motion And Endpoint Handoff

Keep each moving owner separate. A subject may stop while rain continues; a camera may remain open while the subject reaches its mark. Do not let unrelated ambient or camera motion make a completed subject endpoint look unfinished.

Classify the current clip endpoint as `held_static`, `dissipated_or_resolved`, `completed_with_motion`, `frame_exit`, `cyclic_phase_boundary`, or `open_handoff`, then record `carry_forward` separately. `open_handoff` always carries; a completed moving/exit/cyclic owner may carry only when explicitly marked and backed by an open vector. For an intentional next shot, declare the reset instead of pretending the vectors remained continuous.

Timing is also surface-scoped. Preserve observed order and relative phase by default. Carry exact timestamps only when the selected surface and operation have current evidence for that syntax; never invent them from a still or translate them into a different surface contract.

## Completed And Reserved Beats

Every continuation prompt must exclude completed beats and reserved future beats. If Clip 01 already exited the terminal, Clip 02 must not show the terminal exit again. If vehicle departure is reserved for Clip 03, Clip 02 must stop before departure.

## Exact Surface Bindings

Preserve every externally captured handle byte-for-byte and keep it separate from the semantic asset ID. For a derived ordinal, retain the typed media binding and let the exact surface profile recalculate its position; never carry provider syntax as semantic state. If continuation media uses a structured field, retain that role and do not invent prompt text. Resolve only after selecting the exact surface and operation profile.

## Acceptance Rule

Accepted observed state overrides planned state. Rejected footage never becomes canon. Future prompts stay provisional until the previous accepted take is reviewed.
