# Multi-Shot Grammar — candidate cut planning inside one generation

*Use only after selecting a surface and operation whose current evidence supports multi-shot prompting. Labels: [provider example] = syntax observed in the named provider material, not an adherence guarantee; [field] = scoped practitioner report; [heuristic] = planning default to test. V7-09 must re-verify the provider behavior before activation.*

## The grammar [provider example + heuristic]
When the selected surface's current examples use them, explicit `Shot 1:` / `Shot 2:` labels can state the requested cut structure. The labels express editorial intent; they do not create or guarantee cut points. Per shot, start by testing one primary action, one camera plan, and its sound. Keep subject, action, camera, and sound ownership readable.

## The duration budget [heuristic]
Every shot needs enough returned time for its authored event and endpoint to be reviewed. Do not use a universal seconds-per-shot formula. Verify the selected operation's duration field, allowed values, and `auto` semantics before use, then reduce shot count when the returned cut or action is compressed.

## Surface requirements
- A shared request schema does not prove equal behavior across standard, fast, mini, or routed variants. Treat tier comparisons as field tests tied to the exact endpoint and date.
- Duration, shot count, audio behavior, and `auto` remain separate surface facts. Unknown values fail closed rather than inheriting a generic Seedance default.

## Timing syntax is surface-scoped
Choose one evidenced timing policy for the active surface and operation:

- `ordered_phases`: causal or editorial order without exact ranges;
- `relative_beats`: actions tied to a named beat or cue; or
- `surface_exact_ranges`: exact ranges only when current provider evidence for that operation permits them.

The retained BytePlus claim cautions against strict ranges for its scoped multi-shot workflow, while a retained Volcengine example uses exact ranges. Neither establishes a universal language or regional rule. V7-07 rejects unevidenced ranges and remains byte-stable; do not hand-edit a compiled pair to work around that boundary.

## Dialogue and audio placement [heuristic]
A spoken line belongs to its resolved speaker and shot. Keep important lines short enough to review and name each requested sound. Verify cross-call audio continuity instead of assuming it; a unifying score can be planned in post.

## The single-take alternative [heuristic]
For an unbroken take, request `single continuous take, no cuts` and review the returned structure. This states intent; it does not guarantee the absence of cuts.

## Worked shapes
*Three-shot commercial shape:* Shot 1: extreme close-up of condensation sliding down a glass bottle, ice clinking. Shot 2: the bottle rises from crushed ice, camera tilting up into a backlit halo. Shot 3: a hand grabs it against a sunset rooftop, the city humming below. Set duration only from the active surface contract.

*Two-shot dialogue shape:* Shot 1: close on the detective under a flickering platform light, rain on his shoulders; he says quietly, "You were never on that train." Shot 2: cut to the woman's face as the train doors close behind her, a half-smile; the departure chime swallows the silence.

## Failure → fix [field]
| Symptom | Fix |
|---|---|
| Renders as one continuous take | verify that the operation supports multi-shot, use its evidenced labels, or reduce shot count |
| A shot's action skipped/compressed | fewer shots, an eligible longer duration, or one action per shot |
| Cut lands mid-action | end each shot's sentence on the completed beat; let the next shot open the new one |
| Atmosphere breaks between shots | declare the persisting effect once for the whole piece: "thin mist throughout, every shot" (全程薄雾) |

## Sequence Boundary

Multi-shot grammar describes cuts inside one generation. Sequence-state planning describes multiple connected generations. Do not paste future clip prompts into the current multishot prompt. If a beat belongs to a later generation, mark it reserved and leave it out.

Dense multishot prompts use shot labels and endpoints. Continuous takes use phases and no hard cuts. Do not mix those contracts.
