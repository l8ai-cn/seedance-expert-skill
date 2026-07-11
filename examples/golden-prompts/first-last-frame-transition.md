# Golden Prompt: First Last Frame Transition

## Source Brief

Move from one known product state to another.

## Internal Prompt Specification

Mode: FLF2V. Internal bindings `opening` and `endpoint` carry structured `first_frame` and `last_frame` roles. No prompt token and no unrelated story beats.

## Compiled Natural-Language Prompt

Preserve the same product identity, logo, label, and tabletop geometry between the supplied first and last frames. Generate only the continuous transition: condensation forms on the bottle, slides once down the front glass, and settles at the supplied endpoint. Camera remains locked; sound is a single soft glass tick at the endpoint.

Request metadata—not prompt prose—assigns the two frame roles.

## Lint Result

lint: pass

## Control-Critical Sentences

why this remains: the structured `last_frame` role locks the endpoint without inventing a textual tag.

why this remains: `Generate only the continuous transition` prevents extra story from leaking in.
