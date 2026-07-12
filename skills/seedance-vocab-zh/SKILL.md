---
name: seedance-vocab-zh
description: "This skill should be used when the user asks for Chinese Seedance 2.0 prompt wording, Mandarin cinematic vocabulary, Chinese prompt compression, or translation of camera, lighting, action, VFX, audio, and production terms into Chinese."
license: MIT
user-invocable: true
tags:
  - chinese
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

# seedance-vocab-zh

Use Chinese vocabulary when the user asks for Chinese prompts, Chinese-language production wording, role binding, first/last-frame workflow, or a compact Chinese version. Chinese wording must preserve the same mode, typed bindings and selected surface policies, action, camera, lighting, audio, and constraints as any paired English realization.

## Intent

Write concise, natural Chinese without treating brevity as proof of better model understanding. Every compact phrase must still name something visible, audible, or operationally testable.

## Usage Rule

Binding is a separate typed step: a selected profile preserves an external opaque handle, derives an evidenced ordinal, or uses structured roles with no token. Never translate provider syntax. Use short production phrases instead of abstract adjectives.

Load `[ref:vocab/zh]` for role-binding, first/last-frame, camera, lighting, audio, edit/extend, constraint, and safety vocabulary. When a validated V7 scene IR and paired language catalog are available, let `scripts/prompt_compile.py` realize the Chinese clauses and let `scripts/semantic_lint.py` verify structural parity; do not translate arbitrary IR prose at runtime.

| Function | Chinese wording |
|---|---|
| Camera | `缓慢推镜`, `横向跟拍`, `固定中景`, `低角度`, `特写`, `从剪影到正面四分之三角度` |
| Lighting | `侧逆光`, `柔和窗光`, `暖色实用灯`, `冷色月光`, `轮廓光`, `体积光` |
| Motion | `慢慢转身`, `快速掠过画面`, `水珠沿表面下滑`, `薄雾贴地扩散` |
| Audio | `安静环境声`, `一句短对白`, `轻微金属声`, `无配乐`, `脚步声卡点` |
| First/last frame | assign verified structured endpoint roles; prompt `自然过渡到尾帧`, `中间动作连续，不跳切` without invented tokens |
| Constraints | `严格保持logo、标签、形状和颜色不变` |

## Compact Pattern

在类型化引用绑定后的独立文本片段中添加：`：授权参考。严格保持[主体/产品/脸部/标志]不变；仅加入[动作/光线/镜头变化]。镜头：[一个动作]。声音：[音效或环境声]。`

## De-Slop Rule

When the prompt leans on `电影感`, `氛围感`, `高级感`, `大片感`, or bare `质感`, load the Slop Traps table in `references/vocab/zh.md` and decompose each into the physical elements that produce it - 材质, 光线, 色彩, 空气.

## Output Contract

Return concise Chinese prose segments, an optional English gloss, and the unchanged typed binding plan for surface rendering.
