# Sequence Project State

Use this reference when a Seedance request becomes a multi-clip project. The project state is the source of truth; prompts are temporary compiled instructions for one generation.

## Operating Model

User idea -> story spine -> world and continuity bible -> scene plan -> sequence plan -> current clip contract -> current clip prompt -> generated take -> observed take review -> canon reconciliation -> next clip contract -> next prompt.

Plan globally. Generate locally. Observe the real result. Update canon. Continue from actual accepted footage.

## Canonical State

Keep canonical and transient state separate.

Canonical references control identity and immutable design: character identity, product identity, wardrobe, product geometry, persistent props, location, and approved typed bindings with their selected surface policies.

Accepted previous footage controls transient opening state: pose, action phase, screen position, camera phase, environment arrangement, audio phase, open motion, and incomplete gestures.

## Scene Layer

A scene is the local re-anchor unit: one location and time envelope whose clips may use each other's accepted footage. Scenes group beats and own clips; every clip carries exactly one `scene_id`.

This workflow classifies seamless continuation only inside a scene. A scene boundary defaults to an intentional cut opened from canonical references, and `extension_depth` resets to 0. This is a local production contract, not a model limitation.

`extension_depth` counts consecutive output-sourced generations since the last canonical re-anchor. It resets to 0 whenever a clip opens from canonical references. The count provides review context; it does not predict failure and has no evidence-backed universal default or hard ceiling. Re-anchor when a named continuity acceptance check fails, or when a project owner has declared a conservative cap as local policy. Record that policy and its reason instead of presenting it as Seedance behavior.

Map the arc to scenes, not clips: each scene carries one `arc_position` (open, rising, turn, climax, or release) and its clips inherit it.

Audio plan: clips may request ambience, sync SFX, and on-camera dialogue where the selected operation supports them. Verify audio continuity between calls rather than assuming either continuity or discontinuity. A unifying music and score plan may remain in post when the project requires predictable continuity.

## Required Project Fields

The checked-in version-1 schema contains `schema_version`, `state_revision`, `project_id`, `project_mode`, `surface`, `clip_budget_sec`, `prompt_budget`, `story`, `world_bible`, `reference_registry`, `scenes`, `beats`, `clips`, `take_history`, `current_clip_id`, `canon_revision`, and `updated_at`. V7-08 leaves that legacy schema unchanged and adds a separate executable `project-state-v2` contract; it never injects v2 fields into a saved v1 object.

Story fields: `logline`, `story_promise`, `objective`, `initial_condition`, `final_outcome`, `target_duration_sec`, `tone`, and `medium`.

Version-1 scene fields include `scene_id`, `scene_index`, `narrative_function`, `arc_position`, `location`, `time_of_day`, `anchor_source`, `max_chain_depth`, `audio_plan`, `assigned_clip_ids`, `transition_out`, and `status`. Treat `max_chain_depth` as an explicit project-selected policy value during compatibility, not a default model threshold.

Beat fields: `beat_id`, `description`, `narrative_function`, `status`, `assigned_clip_id`, and `dependencies`.

Version-1 clip lineage includes `clip_id`, `parent_clip_id`, `scene_id`, `sequence_index`, `prompt_version`, `generation_mode`, `source_clip_tag`, `status`, `narrative_job`, `felt_intent`, `already_happened`, `this_clip_only`, `reserved_for_later`, `planned_start_state`, `planned_end_state`, `observed_start_state`, `observed_end_state`, `continuity_locks`, `allowed_changes`, `continuity_breaks`, `accepted_deviations`, `transition_in`, `transition_out`, `open_motion_vectors`, `handoff_requirements`, and `extension_depth`. Legacy tags and free-text vectors remain compatibility input only.

## Version-2 migration boundary

Project-state v2 is a new artifact, never an in-place rewrite of a saved v1 file. Preserve the source bytes and record both their SHA-256 and the canonical JSON SHA-256, then create the v2 state beside it. Every legacy semantic field receives a hashed mapped/retired/blocked disposition. Replace legacy tags with semantic binding IDs and typed media provenance, but leave target/dimension authority explicitly `unresolved`; a later hash-bound reference manifest and surface plan must select authority and binding policy.

The v2 design records motion per owner rather than as one scene-wide string. Each vector identifies the entity or camera owner, coordinate frame, direction, qualitative speed/trend, action phase, its own source kind, confidence, and uncertainty, so one snapshot may combine independently supported observations. A still cannot establish velocity or camera phase; mark those unknown unless a video or user attestation supplies a separate vector source.

Each clip endpoint also declares one local completion mode: `held_static`, `dissipated_or_resolved`, `completed_with_motion`, `frame_exit`, `cyclic_phase_boundary`, or `open_handoff`. Completion and continuation are separate: `carry_forward` requires a matching open vector, `open_handoff` always carries, and another moving/exit/cyclic endpoint may be locally complete without forcing a seamless successor. A validated continuation must reproduce every carried owner with the same domain, coordinate frame, direction, and speed trend, and increment depth by exactly one.

Every v2 clip carries `compile_required: true`. Final prompt text must come from a compiler that supports the exact state and motion contract. V7-07 is byte-stable, accepts only its existing scene-IR request, and does not ingest project state, so a v2 clip returns a compilation blocker instead of being downgraded or hand-edited. No v2 field activates a provider profile.

## Visual State

Track only what matters and do not invent unclear details.

Characters: canonical identity ID, wardrobe, hair, position in world, position in frame, pose, action phase, emotional state, gaze, eyeline, travel direction, speed, and body orientation.

Props: identity, owner, position, condition, motion, and interaction state.

Environment: location, geography, background arrangement, time of day, weather, atmosphere, and persistent practical elements.

Camera: shot size, height, angle, support, path, direction, speed, movement phase, subject relationship, focus state, exposure state, and endpoint.

Lighting: key direction, intensity, color relationship, practical sources, and transition state.

Audio: ambience, completed dialogue, active dialogue, music phase, SFX phase, active engine or environmental sounds, and audio reference ownership.

Open motion: record each owner's direction, qualitative speed/trend, coordinate frame, incomplete action phase, and observation confidence. Keep subject, camera, moving props, cloth/hair, vehicle, and environmental motion separate; do not infer momentum, force, or velocity from a still.

Observation quality: `observation_confidence`, `uncertainties`, and `requires_user_confirmation`.

## Reconciliation

When an accepted clip differs from plan:

1. Record the deviation.
2. Decide whether to accept as canon, repair, reject/regenerate, or re-anchor the next shot.
3. If accepted, update downstream planning.
4. Remove any beat unexpectedly completed.
5. Carry any incomplete planned beat into the next appropriate clip.
6. Never pretend the planned ending happened when it did not.

Rejected footage does not alter canon and cannot become a continuation parent.

Take-review-v2 separates `decision_status: pending_confirmation` from `final`. Pending confirmation stays at reviewed/nonterminal status and cannot enter canon. A final ordinary accept requires known observation confidence and no unresolved incomplete beat, unexpected beat, continuity break, accepted deviation, or unknown/incomplete endpoint. A final-frame-only review cannot finally assert moving, cyclic, open-handoff, incomplete, or unknown temporal completion; use video evidence or keep the decision pending.

## Project State Capsule

Use a readable capsule for cross-session continuation. A new conversation cannot be assumed to possess hidden prior memory.

Required fields:

PROJECT ID:
STORY GOAL:
FINAL OUTCOME:
SURFACE:
REFERENCE BINDINGS (legacy v1 state may still call this field `tag`; treat each value as opaque):
CANONICAL REFERENCES:
ACCEPTED CLIPS:
SCENE MAP:
CURRENT SCENE:
CURRENT ACTUAL STATE:
OPEN MOTION BY OWNER:
COMPLETED BEATS:
NEXT CLIP JOB:
NEXT CLIP INTENT:
CONTINUITY LOCKS:
ALLOWED CHANGES:
RESERVED FUTURE BEATS:
EXTENSION DEPTH (context, not failure prediction):
LOCAL RE-ANCHOR POLICY (if explicitly chosen):
COMPILE REQUIRED:
UNRESOLVED UNCERTAINTIES:

## State Lifecycle

The state is append-heavy by nature - every take review adds detail - so a thirty-clip project needs compaction rules, or by clip 25 every session begins by re-pasting a monster.

File convention (for agents with a persistent workspace such as Claude Code or Codex): keep `project-state.json` as the machine truth and regenerate the readable capsule from it; never hand-maintain the same fact in two places. Archive the take log to a separate `take-log.md` (or `take-history.jsonl`) instead of letting `take_history` grow inside the working state.

Compaction rules:

- A **completed scene compresses to one line** in the scene map and the capsule: scene id, one-line outcome, and the accepted final frame it handed off. Its clip-level detail stays in the JSON and the archived take log, not in the capsule.
- **Full detail is kept only for the current scene** plus the immediately previous accepted clip - everything a continuation prompt can actually use.
- **Superseded takes** (rejected, or accepted-then-replaced) move to the archive on scene close; canon keeps only each clip's accepted review.
- The **capsule stays under roughly 40 lines**. If it is longer, something that should have been compacted was not.

`state_revision` bumps on every canon change - an accepted take, an accepted deviation, a re-anchor, a scene close, or a lock change - and the capsule is regenerated at the same moment. A capsule whose revision does not match the JSON is stale; trust the JSON.
