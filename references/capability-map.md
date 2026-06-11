# Capability Map — design into strengths, around limits

*What Seedance 2.0 is best at, how to extract each strength, and what to design around. Load before prompt planning. Labels: [official] = ByteDance/fal/Ark docs · [field] = practitioner-reported · [heuristic] = default to test. Last verified 2026-06-09.*

## Design INTO these

| Capability | Extraction move |
|---|---|
| Multi-shot in one call [official] | `Shot 1:/2:/3:` labels · one action + one camera each · Standard tier · 10–15s/`auto` · shots×seconds budget |
| Native synced audio [official] | name specific sounds; dialogue as a natural quoted line on-screen; short lines; clean front face ref; SFX>music>dialogue — test dialogue first |
| Role-separated references [official] | per-asset role **+ exclusion** ("motion only, no appearance") |
| Motion transfer via @Video [official/field] | donor clip for choreography/camera rhythm + identity @Image |
| Audio-as-clock via @Audio [field] | "cut on the beat of @Audio1; the turn lands on the drop" |
| First/last frame [official] | lock endpoints; prompt initiate→travel→resolve; transformations & match-cuts |
| Literal camera verbs [official] | one motivated move per shot |
| Physics [official claim] | physical verbs & consequences, not pose adjectives |
| Slow motion [official] | Standard tier; on the single key action |
| Transformation [field] | endpoint states + the persisting carrier; hard cases → FLF decomposition |
| 2D/anime [field] | medium grammar: cel over painted bg, sakuga vs held frames, impact frames/speed lines/smears; no lens/DOF talk |
| Formats & `auto` [official] | 21:9 for cinema; `auto` sizes duration to complexity |
| Multilingual [official/field] | zh anchors for texture/mood; keep reference tags exact |

## Design AROUND these

≤15s/call; audio not continuous across calls → score in post [official] · on-screen text → post [official] · negation summons — exclude compositionally [field] · tiny detail (distant faces, hands, logos) degrades [field] · facial micro-acting weakest — stage emotion in body/staging, ration CUs [heuristic] · identity drift after ~4–5 chained gens — re-anchor original refs [field] · Fast tier: no reliable multi-shot/slow-mo/dolly [official] · seed = stabilizer, not lock [official].
