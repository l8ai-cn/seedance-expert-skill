# Failure Atlas

Use this reference when sequence or continuation output fails.

| Symptom | Likely cause | Primary repair variable |
|---|---|---|
| Continuation begins from planned ending | Parent observed state was not reviewed. | Replace opening with observed end state. |
| Action restarts | Completed beat was not marked already happened. | Add completed beat exclusion. |
| Future event appears early | Reserved beat leaked into prompt. | Remove future beat from prompt and endpoint. |
| Identity drifts through extensions | Continuity source displaced canonical identity reference. | Re-anchor identity from canonical image. |
| Screen direction flips | Axis was not locked or reset intentionally. | State screen direction or declare axis reset. |
| Open motion stops | Motion vector was not inherited. | Carry subject/camera speed and direction. |
| Camera phase restarts | Camera endpoint from parent was missing. | Start from observed camera phase. |
| Prop contradicts prior clip | Prop owner/position/condition was not tracked. | Add prop state handoff. |
| Dialogue repeats | Completed dialogue was not logged. | Mark line completed and continue audio phase. |
| Extension quality degrades | Extension depth and drift were ignored. | Re-anchor or create intentional next shot. |
| Two references fight over one attribute | The same target/dimension has multiple authority winners. | Choose one winner; exclude that dimension from every competing asset. |
| Donor identity, room, style, audio, or logo leaks | Leakage risks were not mapped to explicit exclusions. | Keep the donor's intended dimensions and exclude each observed competing dimension. |
| Extra reference makes the result less stable | The asset owns no necessary target/dimension. | Remove it; add references only to fill a documented authority gap. |
| Appearance image behaves like an endpoint request | Appearance authority was conflated with a structured first/last-frame role. | Select the exact supported operation and keep frame roles in request structure. |
| Contact happens but nothing visibly changes | The decisive event has no observable response. | Add one visible consequence and a settled endpoint. |
| Action order collapses | Events lack backward dependencies or a reachable causal chain. | Order initial state, trigger, decisive change, response, follow-through, and endpoint. |
| Key action is hidden | The camera cannot observe the before-state, decisive event, consequence, and endpoint. | Change blocking/framing or simplify to one primary move that can see them. |
| Audio lands at the wrong moment or serves the wrong purpose | Timing and semantic function were conflated. | Specify when the cue occurs separately from whether it is dialogue, SFX, ambience, music, rhythm, or silence. |
| Event density is too high | Several beats were compiled into one prompt. | Reassign future beats to later clips. |
