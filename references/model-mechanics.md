# Operational Reasoning Model — workflow hypotheses, not hidden mechanics

Use this reference to choose the next test when a prompt or generated take fails. The eight sections below are production hypotheses assembled from scoped documentation, field observations, and general filmmaking practice. They do not describe Seedance's unpublished architecture, training data, attention, denoising process, spatial representation, sampling, or internal audio pipeline. A hypothesis earns continued use only when it predicts an observable result on the selected model, surface, operation, and version. Repetition alone does not identify a cause; record the changed variable and returned evidence.

## The eight operational hypotheses

### 1. Prompt scope can become unclear

A prompt with many subjects, actions, camera moves, styles, and constraints is harder for a reviewer to prioritize and harder to diagnose after a failed take. Empty evaluators add length without defining an observable target.

**Workflow consequence:** put the main subject and visible action first; keep one primary camera move; replace quality claims with measurable direction; remove duplicated clauses. This is information design, not an assertion about an internal attention budget.

### 2. Unusual combinations need stronger staging

Some requested combinations fail more often in field testing than familiar, physically legible setups. The retained evidence does not reveal why. Treat rarity as a production risk to test, not as knowledge of the training distribution.

**Workflow consequence:** decompose a difficult effect into visible states, give it a stable carrier, and compare a simple version with the ambitious version. Repeat a required medium or style anchor for continuity only when an A/B test supports that choice.

### 3. Negative constraints can be ambiguous

A long list of possible defects does not clearly describe the desired frame. Some surfaces also reserve specific negative wording for a constraint field, while others accept ordinary prose.

**Workflow consequence:** state the desired positive composition or settled state, then keep only necessary exclusions such as `no on-screen text` in the selected surface's supported constraint form. Do not describe this as a universal inability to understand negation.

### 4. Causal trajectory is a useful planning heuristic

Motion is easier to stage and evaluate when the brief names an initial state, trigger, visible state change, response, follow-through, and endpoint. A disconnected list of micro-instructions gives the director and reviewer no stable event chain.

**Workflow consequence:** prefer one trigger with observable consequences; distinguish material contact from a performance, lighting, or other non-material change; give the event an authored clip endpoint. An endpoint completes the current job but need not stop every moving owner. Record subject, camera, and environmental motion separately so a stopped object can coexist with moving rain or an open camera move. This does not establish any internal temporal or physical representation.

### 5. Chained workflows can accumulate visible deviation

Repeated continuation or edit passes may diverge from an approved identity, layout, motion phase, or endpoint. This is an observed workflow risk, not proof of a frame-generation mechanism or a universal chain-depth threshold.

**Workflow consequence:** compare each accepted take with canonical authorized references and recorded project state; re-anchor when a named continuity check fails or a project owner chooses a documented conservative policy. Keep `extension_depth` as context, not a failure predictor. Never promise that a specific generation number will fail.

### 6. Overlapping references and prose can conflict

Image, video, audio, and text inputs can request incompatible attributes. Field-observed donor leakage makes it unsafe to assume that media type, upload order, or prose emphasis chooses the winner. The exact priority behavior is not public and can vary by operation.

**Workflow consequence:** choose one authority winner for each target and controlled dimension; allow one purposeful asset to own several compatible dimensions; explicitly exclude likely leakage from competing assets; test the exact surface profile.

### 7. Small or occluded details are harder to verify

Distant faces, hands, logos, text, and brief contact points provide fewer visible pixels to inspect and are often obscured by motion or framing. This is an observability problem even before considering model behavior.

**Workflow consequence:** declare how the chosen framing is intended to expose the before-state, change, response, and endpoint, then verify the returned pixels. Make a critical detail large and unobstructed enough to review, or give it a dedicated shot. A declared observability map is not proof that an event is visible, and screen-area percentages do not reveal internal representation.

### 8. Audio and picture require coordinated direction

Supported Seedance surfaces may produce picture and audio in the same requested result, but retained public evidence does not expose the internal generation process. Dialogue, sound effects, camera motion, and performance still compete for limited clip time and review attention.

**Workflow consequence:** assign each spoken line to a named speaker; keep important dialogue short; use readable face framing; link each important sound to one visible event; verify lip-sync and mix behavior on the active surface. Exact timestamps are surface- and operation-scoped syntax, not a universal control. Do not claim that timing is locked by construction or that audio and video use a particular joint architecture.

## Deriving guidance for a novel case

When no existing rule covers the request:

1. Name the observable failure and the exact surface context.
2. Select the smallest operational hypothesis that could explain it without asserting hidden internals.
3. Change one variable.
4. Compare the result against the same acceptance test.
5. Record the observation as surface-scoped evidence, not a universal mechanism. A repeated result narrows the next test; it does not reveal the mechanism by itself.

**Worked example: a mirror reflection should move differently from the subject.** This asks one region to preserve a mirror relationship while violating it. The observable risks are merging, unintended synchronization, or an unreadable transition. Test a simplified shot in which the mirror is the only important region, or split subject and reflection into separate shots. This recommendation follows staging and observability, not a claim about training data or sampling.

## Hypothesis-indexed diagnosis

| Symptom | First hypothesis to test | Conservative lever |
|---|---|---|
| Output is generic after a long prompt | scope is unclear | remove empty language and secondary instructions |
| Style or medium varies between shots | continuity anchor is under-specified | keep one exact, observable medium clause and compare |
| An excluded element appears | desired replacement is not explicit | describe the positive composition and keep one necessary exclusion |
| Action is skipped or unreadable | causal chain or endpoint is unclear | one trigger, visible response, follow-through, endpoint |
| Identity or layout drifts in a chain | accepted state diverged from canonical state | measure the difference and re-anchor from authorized originals |
| A reference changes the wrong attribute | authority or leakage boundary conflicts | repair the target/dimension winner and exclusions |
| A small detail fails review | detail is too small or occluded | enlarge it, simplify motion, or isolate it in another shot |
| Dialogue, sound, or lip-sync fails | audiovisual brief is overloaded or unsupported | shorten the line, stabilize framing, simplify sound, verify the surface |

These labels are diagnostic shorthand only. They must never be cited as Seedance architecture.
