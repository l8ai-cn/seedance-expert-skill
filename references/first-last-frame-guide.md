# First/Last Frame Guide

last_verified: 2026-07-11

Use this guide for FLF2V, first-frame/last-frame transitions, Chinese `首帧/尾帧`, or requests to generate the motion between two images.

Source boundary: retained Volcengine evidence documents structured `first_frame` and `last_frame` roles on its registered operation profile. This proves role designation only, not pixel-perfect endpoint fidelity or a universal request body. The exact `FLF2V` label remains product-surface vocabulary, so select the active surface and operation profile before rendering.

## Core Principle

The first frame defines where the clip begins. The last frame defines the target state. The prompt should describe only the transition logic, camera behavior, lighting continuity, audio intent, and what must stay unchanged.

## Endpoint Roles

| Role | English transition clause | Chinese transition clause | Russian transition clause |
|---|---|---|---|
| First frame | Assign the supplied opening image the operation's first-frame role. | `将提供的起始图像设为首帧。` | Назначить предоставленное начальное изображение первым кадром. |
| Last frame | Assign the supplied endpoint image the operation's last-frame role. | `将提供的目标图像设为尾帧。` | Назначить предоставленное конечное изображение последним кадром. |
| Identity lock | `Preserve the same subject identity, outfit, shape, and scene logic.` | `保持同一主体、服装、形状和场景逻辑。` | `Сохранить того же персонажа, одежду, форму и логику сцены.` |
| Transition only | `Generate only the motion between the two frames.` | `只生成两帧之间的连续动作。` | `Сгенерировать только переход между кадрами.` |

Endpoint role assignment belongs to request transport. Do not insert these editorial sentences into the prompt when the surface uses structured roles, and never invent prompt-visible handles for them. If another verified surface requires prompt-visible bindings, use typed segments and let that profile preserve an external handle or derive its evidenced ordinal.

## Surface Field Notes

| Surface | Practical wording |
|---|---|
| Volcengine/Ark | Use current docs to verify `first_frame`, `last_frame`, `image_with_roles`, duration, resolution, and whether video/audio references can be mixed with first/last-frame mode. |
| Runway | Use `promptImage` positions such as `first` or `last` on the Runway surface, and recheck the current API docs before assuming field parity with Volcengine. |
| ComfyUI / partner workflows | `FLF2V` is useful workflow shorthand, but still confirm the node's exact inputs and face/portrait policy. |

## Prompt Template

```text
Preserve [subject/product/character], [outfit/logo/shape], and scene layout.
Generate a continuous transition from [starting state] to [ending state].
Motion: [one physical action path].
Camera: [one controlled move or locked frame].
Lighting: [source and continuity].
Sound: [ambience/dialogue/SFX/music/silence].
Constraints: no new text, no watermark, no identity change, no object redesign.
```

## Product-Safe Transition

`Preserve the bottle logo, label, glass shape, cap geometry, and color exactly between the supplied endpoint frames. Only the condensation and light change: droplets gather at the shoulder, slide toward the label, and a narrow warm highlight travels left to right. Camera stays locked in a medium product shot. Sound: low room tone, one soft glass tick at the end.`

## Character-Safe Transition

`Preserve the original character's face structure, hairstyle, jacket, and room layout between the supplied endpoint frames. The character slowly stands from the chair, turns toward the window, and stops in the final pose. Camera: locked medium shot with a slight push-in. Lighting: same cool window light, warmer lamp glow at the end. Sound: quiet room tone and soft floor creak.`

## Transformation Method

Field-observed technique; test before promising results. Transformations succeed when the prompt names the two endpoint states plus the persisting carrier - the element that survives the change and carries continuity: a logo, a silhouette, a light source, a camera position.

- State A, state B, and the carrier: `the paper crane unfolds into a flat sheet; the red wax seal stays fixed at center frame throughout.`
- Let the carrier own the eye-line: the viewer tracks the unchanged element while everything around it transforms, which hides intermediate-frame weirdness.
- Hard cases decompose into first/last-frame steps: generate A → carrier-stable midpoint, then midpoint → B as a second FLF2V pass, and cut them together.
- Match-cut variant: hold the carrier's screen position and scale across the cut and let the surroundings swap.

## Common Failures

| Failure | Repair |
|---|---|
| Subject morphs | Lock only the identity anchors that matter; remove extra style changes. |
| Product/logo redraws | Use locked camera and say only light/weather moves. |
| Jump cut | Add "continuous transition" and one physical action path. |
| Camera chaos | Replace multiple moves with locked frame or one slow push-in. |
| Ending misses target | Confirm the endpoint asset has the verified last-frame role, then state that the supplied last frame is the final visual target rather than a mood reference. |
