# V7-08 physics, motion, and state migration

V7-08 separates observable production guidance from claims about hidden model mechanics and installs a candidate-only executable project-state-v2 layer. It adds six closed schemas, strict state validation, a non-destructive migration tool, fixtures, failure-focused evals, a bounded wording audit, runtime packaging, and CI coverage. The V7-07 compiler/toolchain files remain byte-stable, no v2 compiler exists, provider profiles remain disabled, and activation policy remains closed.

## Claim boundary

The repository may describe:

- authored visible states and event order;
- requested target/dimension authority;
- declared camera coverage and review criteria;
- observed take differences tied to a model, surface, operation, version, and date; and
- provider syntax or capability only through current scoped evidence.

It must not infer training-distribution rarity, attention allocation, denoising, sampling causes, a world model, internal physics, conservation, or a universal continuation threshold. Repeated failure narrows the next test but does not identify a hidden cause. A seed field is not a deterministic lock unless current provider evidence says so.

The causal scene IR remains a structural planning contract. It validates declared IDs, order, dependencies, material ownership, event links, and authored acceptance coverage. It does not validate natural-language physical consistency, generated-video accuracy, or whether the returned pixels make an event visible.

## Local motion vocabulary

Motion is recorded per owner rather than as one scene-wide vector. Each state identifies:

- owner: subject, prop, camera, or environment;
- coordinate frame: screen, camera, subject, or world when known;
- direction and qualitative speed/trend;
- action phase;
- observation source, confidence, and uncertainty; and
- whether the state remains open at the cut.

A still can establish pose, position, and framing. It cannot establish velocity, momentum, camera movement phase, or audio phase. Leave those unknown unless a clip or user-supplied record supports them.

An endpoint completes the current clip's authored job; it does not require every owner to stop. Use one local mode per relevant owner:

| Mode | Meaning |
|---|---|
| `held_static` | the owner reaches and holds the required visible state |
| `dissipated_or_resolved` | the authored effect or response visibly resolves |
| `completed_with_motion` | the action is complete while the owner continues moving |
| `frame_exit` | the owner completes the beat by leaving the declared frame |
| `cyclic_phase_boundary` | a repeating motion reaches the authored review phase |
| `open_handoff` | motion intentionally remains open for seamless continuation |

This taxonomy is a local state contract, not a claim that Seedance represents these modes internally.

## Interaction and observability boundary

For interaction-heavy shots, record contact participants, the affected owner/material, and separate visible consequences. A rigid-object response and a performer's flinch are different consequences; one must not be forced to inherit the other's material type.

Describe cues such as compression, overshoot, skid distance, displaced fabric, deformation, or dissipation as reviewable pixels. Do not claim that those words measure mass, force, momentum, friction, elasticity, or energy.

Camera coverage is declared, not proven. The plan names the intended before-state, decisive change, response, and endpoint plus occlusion risks and mitigations. Only review of the returned take can establish whether those events are visible. Acceptance coverage should include every required phase, not merely attach one test to an endpoint ID.

## Timing policy

Timing syntax belongs to the selected surface and operation:

1. `ordered_phases`: event order without exact ranges;
2. `relative_beats`: changes tied to a named cue; or
3. `surface_exact_ranges`: exact ranges only under current evidence for that operation; project-state-v2 records this mode as blocked in V7-08 because its installable runtime has no trusted evidence registry.

The retained BytePlus guidance cautions against strict ranges in its scoped multi-shot workflow, while a retained Volcengine example uses them. These are qualified, surface-specific records, not a Western/Chinese language rule. V7-07's current exact-range rejection remains unchanged; a required exact-range compile therefore blocks until a compatible compiler exists.

## Measured-drift continuation

Keep `extension_depth` as review context. There is no supported universal default of two or hard ceiling of three. Re-anchor when a named identity, layout, motion, endpoint, audio, or world-continuity check fails. A project owner may choose a conservative local cap, but the state must record it as project policy with a reason, not Seedance capability.

## Non-destructive project-state v2 migration

Do not overwrite a saved version-1 state. Preserve its bytes and hash, then create a separate version-2 artifact with migration diagnostics. The v2 contract:

- replaces legacy tag/single-role fields with explicit semantic binding IDs and asset/take/media provenance while leaving target/dimension authority unresolved for later planning;
- records owner-scoped motion and owner-scoped endpoint modes, with carry-forward legal only for a matching open motion vector; `open_handoff` always carries, while another locally complete moving mode may remain open without requiring a seamless successor;
- keeps observed facts separate from planned intent and unknowns;
- treats extension depth as context rather than a failure predictor;
- records an optional project-selected re-anchor policy and reason plus a typed timing policy; and
- requires `compile_required: true` on every v2 clip.

`compile_required: true` means final prompt text must come from a compiler that accepts the exact state contract. V7-07 is byte-stable and supports only its existing one-shot, no-dialogue scene-IR boundary; it does not ingest project state. V2 motion, dialogue, multi-shot transitions, or exact surface timing therefore remain blocked. Do not flatten the state, hand-edit a paired render, or claim V7-07/project-state provenance.

`prompt-spec-v2` records the same `compile_required` status. `generation-run-v2` can record only a blocked/not-run receipt and cannot carry render, compiler, submission, provider-response, or output provenance. This prevents a planning artifact from masquerading as a generation.

The tools are dependency-free and write only to stdout:

```bash
python -S -B scripts/project_state_v2_check.py < project-state-v2.json
python -S -B scripts/project_state_migrate.py inspect project-state-v1.json
python -S -B scripts/project_state_migrate.py migrate project-state-v1.json --map migration-map.json
python -S -B scripts/project_state_migrate.py verify project-state-v1.json project-state-v2.json --map migration-map.json
python -S -B scripts/v2_aux_check.py --self-test
```

Capture `migrate` output as a new file only after review. Never target the source path. The mapping binds both raw source bytes and canonical JSON, explicitly supplies every binding/media provenance and state/motion/endpoint decision, and gives every other legacy semantic field a hash-bound mapped/retired/blocked disposition. A mapped disposition must resolve to the exact target pointer and value hash. Unresolved leaves fail closed rather than being inferred from tags, roles, source-clip strings, order, filenames, or prose.

## Evidence and evaluation

No retained claim proves Seedance physical accuracy, collision behavior, material simulation, or continuation depth. The Contra Labs annotation data is research-only evaluation vocabulary and does not prove prompt effectiveness or model architecture.

Offline tests can validate schema structure, provenance, deterministic diagnostics, typed consistency, and fail-closed behavior. They cannot establish generated-video quality. Promotion of a heuristic requires exact surface/model/version output trials with saved prompts, inputs, attempts, dates, and human review of the named observable. Until then the wording remains `heuristic`, `field-observed` with scope, or `candidate`; runtime activation stays disabled.

## Follow-on boundary

A later reviewed and versioned change may add a compiler that consumes the exact v2 contract. It must bind state/program/render provenance end to end, preserve owner-scoped endpoints and timing/evidence decisions, add output-backed surface trials, and fail on contract-version mismatch. Provider activation remains a separate release step requiring refreshed evidence, exact occurrence coverage, protected review, and regenerated runtime locks.
