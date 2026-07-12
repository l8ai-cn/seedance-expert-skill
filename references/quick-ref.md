# Quick Reference

## Default route

- Vague idea: `seedance-interview`.
- Clear idea: `seedance-prompt`.
- Long story or connected clips: `seedance-sequence`.
- Continue, extend, repair tail, or re-anchor accepted footage: `seedance-continuation`.
- Short prompt: `seedance-prompt-short`.
- Bad result: `seedance-troubleshoot`.
- IP or real-person risk: `seedance-copyright`.
- Blocked prompt: `seedance-filter`.
- Camera, light, motion, style, VFX, audio, or character-specific work: load the matching specialist sub-skill.

## Prompt checklist

| Gate | Pass condition |
|---|---|
| Mode | T2V, I2V, V2V, or R2V is explicit. |
| References | Every applicable target/dimension has exactly one winning asset; every included asset owns at least one necessary dimension and lists likely leakage exclusions. |
| Subject | Main subject appears in the first clause and has stable tags if needed. |
| Action | One visible beat has an observable endpoint. |
| Camera | One primary move has start, speed, subject relationship, and endpoint. |
| Lighting | Source, direction, color, atmosphere, or transition is physical. |
| Audio | Dialogue, ambience, SFX, music, or silence is intentional. |
| Safety | Protected identity, IP, and unsafe wording are rewritten or authorization-gated. |
| Anti-slop | Hollow boosters are replaced by observable production language. |
| Budget | Final prompt fits the verified active-surface prompt budget. |
| Sequence lineage | Sequence prompts have `project_id`, `clip_id`, and parent when continuing. |
| Actual state | Continuations start from accepted observed state, not planned state. |
| Clip scope | Completed beats are excluded and reserved future beats stay out. |
| Causal chain | Fragile action has an ordered initial state, trigger, decisive change, visible response, follow-through, and settled endpoint. |
| Observability | One primary camera move can show the before-state, decisive event, consequence, and endpoint. |
| Paired locale source | English and Simplified Chinese forms come from the exact hash-bound scene catalog, not runtime translation. |
| Locale parity | Both renders preserve the same semantic unit IDs, event order, entities, camera/audio links, invariants, and typed bindings; the catalog carries an unauthenticated human-attestation declaration, and a bilingual human must separately review meaning and naturalness. |

## Fast repair phrases

| Failure | Add or replace with |
|---|---|
| I2V drift | typed image binding + `preserve subject/product exactly; only motion, light, and camera change` |
| Generic look | `physical light source + material behavior + specific camera endpoint` |
| Camera chaos | `one controlled [move] from [start frame] to [end frame]` |
| Weak action | `actor + verb + timing + consequence + final state` |
| Lip-sync instability | `locked medium close-up, short quoted line, no head turn during dialogue` |
| Noisy VFX | `source + material + path + interaction + dissipation endpoint` |
| Style/IP risk | `medium + texture + palette + composition + motion rhythm` |
| Planned ending mismatch | `begin from the observed final frame: [actual visible state]` |
| Future beat leakage | `this clip stops at [endpoint]; do not show [reserved future beat] yet` |
| Reference authority conflict | choose one winner for the exact target/dimension; exclude that dimension from every competing asset |
| Donor leakage | keep only the donor's assigned motion/camera/timing dimensions; exclude identity, wardrobe, environment, style, audio, and logo as applicable |
| Invisible consequence | make the trigger, state change, visible response, and endpoint readable from the chosen camera |
| English/Chinese drift | return to the paired catalog; repair the exact semantic entry and recompile both locales from one program |

## Reference boundary

- Authority is `(target, dimension)`, not one role per file. A single asset may control several compatible dimensions.
- Media type, upload order, priority, confidence, and legacy project-state tags never choose a winner.
- An appearance image is not a first or last frame unless the verified operation assigns that structured role.
- Keep semantic binding IDs separate from authority, request transport, and prompt-visible syntax.
- Treat causal and observability planning as a preflight heuristic, not a Seedance architecture or physics guarantee.
- The V7-07 paired compiler accepts one shot with no dialogue or voiceover. It fails closed instead of inventing a line, speaker, cut, timeline, translation, or provider token.
- Do not hand-translate, renumber, normalize, or compress an opaque provider handle. A surface swap may change only the binding realization and request transport, never the semantic authority plan.
