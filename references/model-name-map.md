# Model Name Map

last_verified: 2026-06-14

Use this file when a user says "Seedance Pro", "Seedance V2", "Seed2.0 Pro", or wrapper-specific model names.

## Canonical Names

| Name | Meaning | Guidance |
|---|---|---|
| Seedance 2.0 | ByteDance Seed video generation model line | Correct public name for the v2 video model family. Use this as the default wording. |
| Seedance 2.0 Fast | Faster Seedance 2.0 variant reported by official/product and wrapper surfaces | Use for draft, iteration, or low-latency discussion when the active surface exposes it. Recheck exact resolution, duration, and pricing. |
| Doubao Seedance 2.0 | Volcengine/Doubao-flavored surface naming | Treat as a product/API surface label, not a different creative method. |
| `doubao-seedance-2-0-260128` | Volcengine Ark model ID observed in May 29 tutorial | Useful for implementation examples only after rechecking the active console/docs. Do not treat as universal BytePlus/global availability. |
| `doubao-seedance-2-0-fast-260128` | Volcengine Ark Fast model ID observed in May 29 tutorial | Use only when the active surface exposes the Fast variant and current pricing/limits are checked. |
| `doubao-seedance-2-0-pro-260215` | Volcengine Ark Pro model ID (reported 2026-06-14, not console-verified here) | Use only after rechecking the live Ark console. Do not confuse with the `doubao-seed-2-0-pro-*` LLM (see Non-Seedance section). |
| `dreamina-seedance-2-0-260128` / `-fast-260128` | BytePlus ModelArk model IDs — the international counterpart of the Volcengine `doubao-` IDs (reported 2026-06-14) | BytePlus uses a `dreamina-` prefix where Volcengine uses `doubao-`. Same model family, different surface; recheck the live ModelArk docs before quoting. |
| `seedance2` | Runway API model ID | Use only for Runway's API surface. Do not substitute for Volcengine/Doubao model IDs. |
| fal Seedance 2.0 endpoints | fal's hosted Seedance 2.0 surface: `text-to-video`, `image-to-video`, `reference-to-video`, each with a `/fast` tier | Use fal endpoint naming only for the fal surface (verified 2026-06-09). Recheck endpoint IDs, resolution tiers, and per-second pricing live before quoting. Do not substitute for Volcengine, Doubao, or Runway model IDs. |
| Seedance V2 | Community shorthand | Normalize to Seedance 2.0 unless the user is clearly referring to a wrapper-specific model. |
| Seedance 2.0 Pro | Ambiguous community shorthand | Do not assume this is an official video-model name. Ask which surface, or normalize to Seedance 2.0 / Fast with a caveat. |
| Seed2.0 Pro | Separate Seed/Doubao naming seen outside the Seedance video model line | Do not confuse with Seedance 2.0 video generation. |
| Seedance 1.5 Pro | Earlier Seedance generation | Useful for historical comparison only. Do not mix its limits with Seedance 2.0. |

## Answer Pattern

If the user says "Seedance 2.0 Pro", answer:

`I will treat this as Seedance 2.0 unless you mean a specific wrapper's Pro label. Official public video-model wording is Seedance 2.0 and, on some surfaces, Seedance 2.0 Fast. Seed2.0 Pro is a different naming lane and should not be used as the Seedance video model name without source confirmation.`

## Non-Seedance Models (Do Not Confuse)

These are NOT Seedance and should not trigger Seedance-specific syntax, specs, or surfaces. Versions verified 2026-06-14; recheck before quoting.

| Name | What it actually is | Note |
|---|---|---|
| Seedream (e.g. Seedream 4.5) | ByteDance's **image** generation model | Same vendor, near-identical name (Seedr**ea**m vs Seed**a**nce). Highest confusion risk. Not video. |
| Doubao-Seed-2.0 (`doubao-seed-2-0-pro-*`) | ByteDance's **LLM** on Volcengine | Shares the Ark surface and the "Seed" lineage but is a language model, not Seedance video. |
| Sora 2 (OpenAI) | Competing video model | Note: OpenAI announced Sora's sunset — app closed ~Apr 2026, API ending ~Sept 2026. Not Seedance. |
| Veo 3.1 (Google) | Competing video model (family: 3.1 / Fast / Lite) | "Veo 3" is the prior gen. Not Seedance. |
| Kling 3.0 (Kuaishou) | Competing video model ("Omni" = its multimodal variants) | Not Seedance. |
| Runway Gen-4.5 | Runway's own video model line | Distinct from Runway *hosting* Seedance 2.0 via its API. Not Seedance. |
| Hailuo / Vidu / Luma Ray3 / Pika / Wan | Other competing video models | Not Seedance. |

For these, offer general filmmaking craft only — never Seedance reference tags, shot grammar, or surface-specific settings.

## Wrapper Names

Third-party wrappers may expose names such as `doubao-seedance-2.0`, `doubao-seedance-2.0-fast`, or provider-prefixed variants. These can be useful for implementation, but they are not the repo's source of truth for official naming.

Do not quote current BytePlus Seedance 2.0 pricing or model IDs from JavaScript-rendered pricing pages unless the value has been verified in a current official page or console. Volcengine prices can be cited only with source date, model, surface, currency, and a recheck warning.
