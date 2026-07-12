---
name: seedance-vocab-ja
description: "This skill should be used when the user asks for Japanese Seedance 2.0 prompt wording, Japanese cinematic vocabulary, or translation of camera, lighting, action, VFX, audio, and production terms into Japanese."
license: MIT
user-invocable: true
tags:
  - japanese
  - vocabulary
  - seedance-20
metadata:
  version: "6.6.0"
  updated: "2026-07-04"
  parent: "seedance-20"
  author: "Iamemily2050 (@iamemily2050)"
  repository: "https://github.com/Emily2040/seedance-2.0"
  openclaw:
    emoji: "🎬"
    homepage: "https://github.com/Emily2040/seedance-2.0"
---

# seedance-vocab-ja

Use Japanese cinematic vocabulary when the user asks for Japanese prompt wording, bilingual delivery, compact translation, or production vocabulary for camera, lighting, motion, VFX, and audio. Binding is a separate typed step: a selected profile preserves an external opaque handle, derives an evidenced ordinal, or uses structured roles with no token.

## Intent

Serve the user's chosen Japanese register with natural sentences and recognizable production terms. Preserve the intended medium—live action, animation, product, or another form—without assuming a model preference from the prompt language.

## Usage Rule

Prefer concise production Japanese over literal translation. Keep the structure readable: subject, action, camera, lighting, sound, and preservation constraint.

| Function | Japanese wording |
|---|---|
| Camera | `ゆっくりドリーイン`, `横移動のトラッキング`, `固定の中景`, `低いアングル`, `クローズアップ` |
| Lighting | `逆光`, `柔らかい窓光`, `暖かいプラクティカルライト`, `冷たい月明かり`, `輪郭光` |
| Motion | `ゆっくり振り返る`, `画面を素早く横切る`, `水滴が下へ流れる`, `煙が薄く広がる` |
| Audio | `静かな環境音`, `短い台詞`, `金属音`, `音楽なし` |
| Constraints | `ロゴ、ラベル、形状を正確に維持する` |

## Compact Pattern

In a separate text segment after the typed binding, avoid attaching a particle to an unknown handle: `：参照素材。被写体の顔/商品形状/ロゴを正確に維持する。変化は[動き/光/カメラ]のみ。カメラ：[一つの動き]。音：[音声指示]。`

## De-Slop Rule

When the prompt leans on `映画のような`, `エモい`, `雰囲気のある`, `壮大な`, or `高画質`, load the Slop Traps table in `references/vocab/ja.md` and decompose each into the physical elements that produce it - 動作動詞＋速度＋視点, 光源＋方向＋挙動.

## Output Contract

Return Japanese prose segments, an optional English gloss, and the unchanged typed binding plan for surface rendering.
