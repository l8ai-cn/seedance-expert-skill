# Sequence Worked Trace

<!-- fixed_handle_audit: synthetic_fixture -->

One legacy version-1 project, walked end to end through the full loop - plan, compile, generate, observe, deviate, reconcile, apply its project-selected re-anchor policy, break for the night, and resume. The machine half of this trace already lives in `examples/`; this is the prose half that shows how the compatibility fields are used. The numeric policy in this fixture is not a Seedance limit or default for new projects.

The project: **seq_airport_arrival** (`examples/sequence-airport-arrival/`) - a traveler exits the terminal, enters a waiting car, and the car departs. Deviation-handling details borrow the second fixture, **sequence-observed-deviation** (`examples/sequence-observed-deviation/`), which records a real unexpected-completed-beat event.

## 0 - Plan globally

The idea ("my character lands and is driven away") is bigger than one generation, so the Sequence Gate classifies it `sequence_project`. Before Clip 01 exists, the plan fixes: the story promise and final outcome, beats grouped into **scenes**, and per clip a `narrative_job`, a `felt_intent`, and a completed endpoint.

Here everything happens at one location in one time envelope, so the scene map is a single scene: `scene_01`, arc position `release`, canonical anchor `@Image 1` (the exact opaque handle supplied by this fixture - note the internal space; it is never a default for new output), a legacy-v1 `max_chain_depth: 2` chosen as this project's conservative local policy, and an audio plan of curb ambience and sync SFX per clip with score unified in post. Three clips are assigned: exit terminal and approach the car (Clip 01), enter and close the door (Clip 02), the car departs (Clip 03). See `project-state.json` - `scenes`, `beats`, `clips`.

Only Clip 01 is compiled. Clips 02-03 stay provisional intent cards, because their opening states do not exist yet.

## 1 - Compile Clip 01

The contract (`clip-01-contract.json`) carries the job ("Exit terminal and approach the open rear car door"), the felt intent ("the quiet relief of arrival"), the reserved beats (entering the car, departure), and the locks. The compiler (see `[ref:prompt-compiler]`) emits one natural-language prompt (`clip-01-prompt.md`) - T2V, since nothing exists yet - and before generation the intent echo is stated in one line: *this clip exists so the viewer feels the relief of arrival.* No internal JSON ships to Seedance.

## 2 - Observe, and accept a deviation

The take comes back. The user attaches the clip or its final frame (locally: `python scripts/extract_last_frame.py take.mp4`), and the **agent** fills the observation record from the pixels - the Observation Fast Path in `[ref:continuation-handoff]` - asking only what a still cannot show. The review (`clip-01-take-review.json`) records the honest result: the traveler is **two steps short of the open door**, still walking, left-to-right. The plan said "reaches the door"; the pixels disagree.

Verdict: `accept_with_deviation`. Reconciliation (see `[ref:sequence-project-state]`) updates canon: the deviation is recorded, the observed end state overrides the planned one, and Clip 02's contract is recompiled to open **two steps out, mid-stride** - it does not replay the terminal exit, and it does not pretend she reached the door. Rejected takes, by contrast, would change nothing: rejected footage never becomes canon or a parent source.

## 3 - Continue from what actually happened

Clip 02 (`clip-02-continuation-contract.json`) is a `seamless_continuation` inside `scene_01`: parent `clip_01`, `extension_depth: 1`, sourced from the accepted take attached as `[Video 1]`. The **source-carries-state rule** applies: the video reference carries the opening state, so the prompt text carries only the delta - finish the approach, enter, close the door, plus the felt intent's carriers (the door shutting as an exhale) and the reserved-beat exclusion (no departure yet). Prose that re-describes what `[Video 1]` already shows would be budget spent turning disagreement into drift.

## 4 - The other way plans break: a beat completes early

The second fixture shows the mirror-image deviation. A rooftop courier take planned only "unlock the case" - but the accepted footage shows the case unlocked **and opened** (`take-review.json`: "case opened one clip earlier than planned"). Reconciliation removes the now-completed `beat_open_case` from the future (compare `project-state-before.json` with `project-state-after.json`: three planned clips become two, and the next clip's job becomes "Light the already visible signal device"). The rule in both directions is the same: **accepted observed state overrides planned state** - whether the take fell short or ran ahead.

## 5 - The local re-anchor policy and the scene boundary

Clip 03 chains from Clip 02's accepted footage: `extension_depth: 2`, exactly at this fixture's explicit `max_chain_depth`. The legacy-v1 validator therefore requires this project to open the next shot from canonical references. That enforcement proves only that the record follows its chosen local policy; it does not predict drift or establish a universal chain threshold. At the planned scene boundary the next shot would be an intentional cut opened from `@Image 1`, with depth back to 0. A named continuity failure at any earlier point triggers `reanchor_after_drift`; absent such a failure or an explicit project policy, depth alone is context rather than a reason to reset.

## 6 - Break for the night, resume tomorrow

Sessions end; canon must not. The Project State Capsule (template in `[ref:sequence-project-state]`) carries the whole project in under ~40 lines: scene map (completed scenes compressed to one line each), current scene, current actual state, open motion, completed beats, next clip job **and intent**, locks, reserved beats, extension depth, uncertainties. A new session pastes the capsule and continues from the recorded actual state - no hidden memory is assumed, and the machine truth (`project-state.json`, per the State Lifecycle) regenerates the capsule whenever `state_revision` bumps.

## 7 - Close out

Clip 03 ends the scene and the story: the car departs, the final outcome is met, the scene closes (its line in the capsule compresses to its outcome), and the take log archives. Total user effort per cycle after the plan: attach the take, confirm the agent's observation record, approve the intent echo, generate. The state checks keep replay, future-beat leakage, and unsupported observations visible for review; they do not guarantee generated-video behavior.
