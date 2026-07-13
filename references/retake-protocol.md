# Retake Protocol — the iteration economy

*What happens after a generation comes back. The rest of this skill plans the shot and repairs outright failure; this governs everything in between — the partially good take, which is most of real production. Labels: [heuristic] = default to test · [internal] = workflow guidance. Cost figures are surface-specific and volatile: load `api-status.md` and verify live before budgeting.*

## Triage every take — five verdicts

| Verdict | When | Next move |
|---|---|---|
| **Keep** | The primary acceptance target from `allocation-model.md` passes and no hard-fail criterion is present. | Lock it, log it, and move on; route eligible secondary flaws to post. |
| **Fix in post** | The flaw lives in post's domain: color, on-screen text, sound mix, trim, a few unstable frames at the ends. | Never burn takes on what an editor fixes in minutes. |
| **Edit, don't regenerate** | Composition and timing are right; exactly one layer is wrong, and the surface supports edit. | Preserve the take as the source clip; change only the failing layer. |
| **Re-roll** | The prompt contract is still plausible and the surface exposes an eligible retry path. | Repeat the unchanged request only inside a declared attempt budget; record every returned difference without assigning a hidden cause. |
| **Rewrite** | Evidence from reviewed takes makes a prompt or staging change worth testing. | Form one observable workflow hypothesis from `model-mechanics.md`, change one declared variable, and compare. |

## The one-variable rule [heuristic]

Change one thing per retake when the surface permits it: one prompt clause, the exposed seed field, the mode, or one reference. Holding a field constant does not prove all other generation conditions are controlled, and an exposed seed is not a deterministic lock unless current provider evidence says so. The purpose is narrower attribution, not a controlled experiment claim.

## Attempt budget [heuristic]

Set it before take one: a project-chosen number of attempts and a written pass condition for the primary acceptance target. Do not infer the budget from tier names or treat a repeat count as proof that the prompt, model, or sampling mechanism is at fault. When the budget is exhausted without progress, change strategy: a different verified mode, decomposition into more shots, post work, or the honest exit below.

## Cost awareness [internal]

Every second of generation costs real money, and retakes multiply it: at the fal figures last verified in `api-status.md` (≈$0.30/s standard 720p, ≈$0.68/s 1080p — verify live), a single 15-second standard take is several dollars, and a ten-take session is a real invoice. Spend accordingly:

- **Draft cheap, lock expensive**: explore composition on the fast tier, short durations, or lower resolution; spend standard tier and full length only on the locked design.
- Prefer the smallest eligible draft that can answer the current acceptance question; verify duration and tier behavior on the active surface.
- Quote costs to users only with the verification date and a verify-live caveat.

## The shot log [internal]

One line per take — this is the story state made auditable:

`Take N · changed: [one declared variable or unchanged retry] · exposed seed: [value/unavailable] · verdict: [keep/post/edit/re-roll/rewrite] · observed evidence: [one sentence]`

Re-read the log before choosing the next test. Repeated flaws can justify a rewrite within the attempt budget, but repetition alone does not reveal a hidden mechanism or identify one cause.

## Sequence Canon [internal]

For sequence projects, a take review decides whether footage becomes canon.

- Accept: record observed start/end state and allow it to become a parent source.
- Accept with deviation: record the deviation, update downstream beats, and carry unfinished work forward.
- Repair: do not advance the sequence until the repaired tail or layer is accepted.
- Reject: do not update canon and do not use that take as a parent source.

Accepted observed state overrides planned state. If a clip unexpectedly completes a future beat, mark that beat completed and remove it from later prompts.

## When the answer is "don't generate"

Honest direction sometimes refuses the tool: dense on-screen text belongs to post, a real product's exact behavior may belong to a camera, archival reality belongs to licensing, and a shot that has failed its budget twice after decomposition belongs to a different idea. "Film this one for real" is a deliverable, not a failure.
