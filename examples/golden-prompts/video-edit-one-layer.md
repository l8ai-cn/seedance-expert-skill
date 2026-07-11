# Golden Prompt: Video Edit One Layer

## Source Brief

Fix lighting in an otherwise good clip.

## Internal Prompt Specification

Mode: edit. Internal binding `source_clip` is the source. Change one layer only.

## Typed Segment Composition

`binding(source_clip)` + ` is the source clip. Preserve the existing subject, timing, camera path, background layout, and action exactly. Change only the lighting layer: add a soft warm practical lamp from frame left and a faint blue rim on the shoulder, keeping the same motion and endpoint. Do not regenerate wardrobe, face, props, dialogue, or camera movement.`

The binding marker is typed plan notation. No edit operation is activated by the V7-05 profiles.

## Lint Result

semantic lint: pass; surface render: unavailable in V7-05

## Control-Critical Sentences

why this remains: `Change only the lighting layer` enforces one-layer edit discipline.

why this remains: `Do not regenerate wardrobe, face, props, dialogue, or camera movement` protects accepted continuity.
