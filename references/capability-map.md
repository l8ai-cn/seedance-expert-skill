# Capability Map — plan from scoped evidence and observed limits

*Use this map before prompt planning. Labels: [official] = retained provider documentation within its stated model, surface, operation, region, and date · [field] = practitioner-reported · [heuristic] = a workflow starting point to test. A model-level statement does not automatically apply to every surface. The operational reasoning behind these rows lives in `model-mechanics.md`.*

## Design INTO these

| Capability | Extraction move |
|---|---|
| Multi-shot in one call [official] | `Shot 1:/2:/3:` labels · one action + one camera each · Standard tier · 10–15s/`auto` · shots×seconds budget |
| Native synced audio [official] | name specific sounds; dialogue as a natural quoted line on-screen; short lines; clean front face ref; SFX>music>dialogue — test dialogue first |
| Reference control [official model-level claim; operation-specific] | assign target/dimension authority **+ exclusions**; the retained claim names camera movement, lighting, performance, and shadow, not a universal priority mechanism |
| Motion transfer through typed video/image bindings [official/field] | donor clip for choreography/camera rhythm + a separately bound identity image; surface syntax is resolved later |
| Audio-as-clock via a verified surface binding [field-observed] | typed audio binding + "controls beat timing; the turn lands on the drop" |
| First/last frame role designation [official, Volcengine-scoped] | assign verified structured opening/endpoint roles; prompt initiate→travel→resolve; test endpoint fidelity rather than assuming a lock |
| Literal camera verbs [official] | one motivated move per shot |
| Causal action staging [heuristic] | initial state → trigger → visible consequence → settled endpoint; verify the camera can observe each required phase |
| Slow motion [official] | Standard tier; on the single key action |
| Transformation [field] | endpoint states + the persisting carrier; hard cases → FLF decomposition |
| 2D/anime [field] | medium grammar: cel over painted bg, sakuga vs held frames, impact frames/speed lines/smears; no lens/DOF talk — full grammar in `[ref:2d-anime-grammar]` |
| Formats & `auto` [official] | 21:9 for cinema; `auto` sizes duration to complexity |
| Multilingual prompting [official/field, scope varies] | use the requested production language; preserve exact opaque surface bindings byte-for-byte; compare localized results on the selected surface instead of assuming language superiority |

## Design AROUND these

For connected generations, design around continuity drift by keeping each clip small, recording accepted observed state, preserving exact target/dimension authority and semantic bindings, and re-anchoring on schedule at the scene's chain-depth cap instead of waiting for visible drift. This is workflow guidance, not a deterministic platform guarantee.

Surface duration caps are active-surface facts, not universal Seedance facts; audio continuity across separate calls needs explicit verification, so score in post when needed · on-screen text → post where the selected workflow requires a clean plate · prefer positive observable states to long defect lists [heuristic] · tiny details such as distant faces, hands, logos, and text require close review [field] · stage fragile facial performance with readable blocking [heuristic] · re-anchor chained generations from authorized canonical references when drift is observed [field] · simplify character-to-prop contact in crowded shots [heuristic] · Fast-tier behavior is surface-specific [field] · a seed may aid repeatability where exposed, but is not a fidelity guarantee.

## Competitive Context *(2026-06-14)*

Do not market a capability as unique from an undated comparison table. Describe only the capability set supported by current retained evidence for the selected Seedance surface and operation, such as accepted reference modalities, multi-shot prompting, audio options, or language support. Resolution, duration, audio, lip-sync, and reference combinations remain surface-specific; check `api-status.md` and the active profile before making a delivery claim.
