# Multi-Shot Grammar — candidate cut planning inside one generation

Use only after selecting a surface and operation with current evidence for multi-shot prompting. Provider examples demonstrate authored request forms, not cut accuracy, timing adherence, or repeatability. Unknown support fails closed.

## Retained provider tension

- `[claim:bp.timing.exact-caution]` records a BytePlus-scoped example/guidance pattern using ordered shot labels while cautioning against strict time ranges.
- `[claim:volc.timing.exact-example]` records a Volcengine-scoped example using exact second ranges.

These records apply only to their captured surface, operation, region, and date. They do not establish a universal `Shot N` grammar, a Chinese-versus-English prompting rule, seconds per shot, transferable provider syntax, or adherence to the requested cuts/ranges.

## Versioned semantic contract

Plan the edit independently of provider syntax. A later versioned multi-shot contract and checker should require:

- ordered shot IDs and one active shot at a time;
- one primary visible action and endpoint per shot;
- a typed editorial transition between adjacent shots, such as hard cut, match cut, dissolve, or fade; continuous camera movement stays inside one shot and is never a cut type;
- shot-local camera, sound, dialogue-turn, and reference authority;
- one timing policy for the request;
- the selected model, surface, operation, region, evidence claim IDs, and capture date;
- explicit unknowns and acceptance checks for cut order, transition, event completion, and timing.

Until that contract is active, do not flatten multi-shot state into the single-shot V7-07 compiler or hand-edit its paired render while retaining compiler provenance.

## Timing policies

Choose exactly one policy that the active surface/operation permits:

- `ordered_phases`: editorial order without exact ranges;
- `relative_beats`: events linked to named semantic cues; or
- `surface_exact_ranges`: exact ranges only when current evidence permits them for that operation.

Duration, valid values, shot count, audio behavior, and `auto` semantics are separate surface facts. There is no universal seconds-per-shot formula. Reduce shot count when an authored event cannot complete within the selected operation's evidenced duration.

## Rendering boundary

Only a selected surface profile may turn the semantic contract into labels, timestamps, ordinals, handles, or structured request fields. Do not invent provider-looking syntax. The same semantic edit may need different renderers for BytePlus and Volcengine because their retained timing evidence points in different directions.

One reference gets one explicit target role. Assign character identity, set, camera, motion, palette, audio, or endpoint authority separately and state exclusions. Upload order is not a conflict policy.

## Dialogue and sound

Each spoken turn belongs to one resolved speaker and shot, with an exact utterance and spoken-language tag independent of prompt locale. Keep important lines short enough to review. Name requested ambience and effects, but verify audio output, turn order, lip-sync, and cross-shot continuity separately. A unifying score can be planned in post.

## Semantic worked shapes

These are planning records, not paste-ready provider prompts.

| Beat | Visible action and endpoint | Camera/sound intent |
|---|---|---|
| Product A | condensation slides down a glass bottle and reaches the label | extreme close-up; ice clink requested |
| Product B | bottle rises clear of crushed ice | tilt follows the bottle into a backlit halo |
| Product C | hand closes around bottle and holds | rooftop wide; city ambience requested |

| Beat | Visible action and endpoint | Dialogue/transition intent |
|---|---|---|
| Dialogue A | detective holds under a platform light | exact line assigned to detective; transition type declared separately |
| Dialogue B | train doors finish closing behind the woman | reaction only unless a separate exact turn is authored |

The renderer may emit provider-evidenced labels or ranges only after the surface and operation are resolved.

## Single-take alternative

For an unbroken take, declare one shot with continuous camera intent and no transition edges, then review whether the returned result follows it. `Single continuous take` is an intent, not a guarantee that the model will avoid cuts.

## Failure → controlled retry

| Symptom | Controlled retry |
|---|---|
| One continuous take returned | verify multi-shot operation support, then use only its evidenced renderer or reduce the edit |
| Action skipped or compressed | remove a shot or reduce to one completed action per shot |
| Cut lands mid-action | give the outgoing shot a visible settled endpoint; open the next shot on the new state |
| Wrong transition | make the typed transition unambiguous and remove competing camera continuity |
| Atmosphere breaks | state the persistent world condition at contract level and review it in every shot |
| Exact range missed | report adherence failure; do not infer that adding more timestamps will repair it |

## Sequence boundary

Multi-shot grammar describes cuts requested inside one generation. Sequence state describes multiple connected generations. Do not paste future clip prompts into the current request. If a beat belongs to a later generation, reserve it outside the current clip.

Dense multi-shot edits use typed shots and transitions. Continuous takes use ordered phases and continuous camera. Do not mix those contracts.
