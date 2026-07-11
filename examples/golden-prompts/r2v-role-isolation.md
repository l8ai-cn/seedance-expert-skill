# Golden Prompt: R2V Role Isolation

## Source Brief

Use an image for identity, a video for camera rhythm, and audio for tempo.

## Internal Prompt Specification

Mode: R2V. Internal binding `character` controls identity, `camera_reference` controls camera rhythm only, and `tempo_reference` controls tempo only. Endpoint: character reaches the doorway. All three are typed segments.

## Typed Segment Composition

`binding(character)` + ` controls the original character identity and wardrobe. ` + `binding(camera_reference)` + ` controls camera rhythm only; ignore its performer, room, logo, and costume. ` + `binding(tempo_reference)` + ` controls tempo only; do not copy voice or song identity. The character walks toward the doorway in three steady steps as the camera matches the reference rhythm and stops when her hand reaches the handle.`

The `binding(...)` markers describe typed segments and are never sent literally.

## Lint Result

semantic lint: pass; surface render: required

## Control-Critical Sentences

why this remains: `controls camera rhythm only` prevents video identity transfer.

why this remains: `ignore its performer, room, logo, and costume` states the non-transfer boundary explicitly.
