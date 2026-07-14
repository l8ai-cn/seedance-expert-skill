---
name: seedance-expert
description: This skill should be used when creating, directing, generating, reviewing, or repairing Seedance 2.0 videos, including text-to-video, image/reference-to-video, first/last-frame control, connected clips, camera and continuity planning, multilingual prompts, Volcengine Ark task execution, and Seedance-specific troubleshooting.
license: MIT
metadata:
  version: "6.6.0"
  adaptation_version: "1.0.0"
  upstream: "Emily2040/seedance-2.0@57d01dc66f93ecb03c2475be5f22dc416d9b701d"
---

# Seedance Expert

Turn the user's intent into a production-ready Seedance brief, obtain approval
before spending generation quota, execute the exact configured Ark model, and
return durable video and run-metadata files.

## Operating Contract

1. Identify the story beat, target surface, mode, duration, ratio, references,
   audio intent, deliverable, and safety constraints.
2. Choose one primary visual beat, one motivated camera move, one motivated
   light source, and explicit sound intent.
3. Present a concise brief and the final natural-language prompt. Do not expose
   internal reasoning or substitute JSON for the final prompt.
4. Run `scripts/seedance_prompt_lint.py` before generation. Repair every reported
   issue instead of bypassing the validator.
5. Print the SHA-256 approval fingerprint for the exact prompt, model,
   parameters, and references. Ask the user to approve that fingerprint.
6. Only after approval, run `scripts/seedance_generate.py` with the same
   arguments and `--approval FINGERPRINT`. Never change provider, model,
   duration, or references to make a failed request appear successful.
7. Return the generated MP4 and its adjacent JSON metadata file. Review the
   actual take before proposing a continuation or retake.

## Fast Lane

For one safe standalone clip with a clear idea:

- Produce a 40-110 word prompt.
- Keep one visible action and one primary camera move.
- State duration, ratio, resolution, audio, and watermark choices.
- Show the brief and wait for approval.

Use [compact prompt guidance](skills/seedance-prompt-short/SKILL.md) when the
idea is simple. Use the full [prompt workflow](skills/seedance-prompt/SKILL.md)
when references, dialogue, or several constraints must be coordinated.

## Production Routing

- Vague idea: load [interview guidance](skills/seedance-interview-short/SKILL.md).
- Camera and blocking: load [camera guidance](skills/seedance-camera/SKILL.md)
  and [shot language](references/cinematography-shot-language.md).
- Image or multimodal references: load
  [reference workflow](references/reference-workflow.md).
- Connected clips or continuation: load
  [sequence workflow](skills/seedance-sequence/SKILL.md),
  [continuation guidance](skills/seedance-continuation/SKILL.md), and
  [continuity QC](references/continuity-qc.md).
- Returned take or failed generation: load
  [retake protocol](references/retake-protocol.md) and
  [troubleshooting](skills/seedance-troubleshoot/SKILL.md).
- API or model claims: load [Ark API workflow](references/api-workflow.md) and
  recheck the official provider documentation before implementation.
- Real-person likeness, voice, brands, protected characters, graphic content,
  or policy evasion: load [copyright guidance](skills/seedance-copyright/SKILL.md)
  and [filter guidance](skills/seedance-filter/SKILL.md) before drafting.

## Sequence Gate

For connected clips, plan the final outcome and ordered beats before Clip 01.
Accepted observed state overrides planned state. Rejected footage never enters
canon or becomes a continuation source. Preserve exact reference tags across
every clip, and do not finalize the next prompt until the previous accepted
clip or its actual final frame has been reviewed.

## Generation

The Worker injects these credential-backed variables:

- `SEEDANCE_API_KEY`
- `SEEDANCE_BASE_URL`
- `SEEDANCE_MODEL`

`SEEDANCE_MODEL` must be an Ark video model ID beginning with
`doubao-seedance-`. A `doubao-seed-*` ID is a language model and must be
rejected before approval or network access.

Before a billable request, verify the credential and official video-task route:

```bash
python3 scripts/seedance_generate.py --check-credentials
```

This non-billing check does not prove model entitlement, quota, moderation
acceptance, or generation success.

Every reference must be an HTTPS URL without embedded credentials. One request
may contain at most 9 image references, 3 video references, 3 audio references,
and 12 references total. Audio references require at least one image or video.
Use `--image-url`, `--video-url`, and `--audio-url` repeatedly; add
`ROLE=https://...` when a role such as `first_frame`, `last_frame`,
`reference_image`, `reference_video`, or `reference_audio` is required.

First print the approval fingerprint without making a network request:

```bash
python3 scripts/seedance_generate.py \
  "FINAL APPROVED PROMPT" \
  --output output/seedance-video.mp4 \
  --duration 5 \
  --ratio 16:9 \
  --resolution 720p \
  --print-approval
```

Then repeat the exact request with the returned fingerprint:

```bash
python3 scripts/seedance_generate.py \
  "FINAL APPROVED PROMPT" \
  --output output/seedance-video.mp4 \
  --duration 5 \
  --ratio 16:9 \
  --resolution 720p \
  --approval SHA256_FINGERPRINT
```

The approval value is the SHA-256 request fingerprint of the canonical HTTP
method, approved HTTPS API endpoint, and complete JSON body. Changing the model,
prompt, parameters, references, or API path invalidates approval.

Before the billable create request, the command atomically writes
`output/seedance-video.json` with status `creating` and the request fingerprint.
After a successful creation response, it immediately persists the task id,
polls `queued` and `running`, and never creates another task while that metadata
file exists. Provider HTTP 4xx responses are persisted as `creation_rejected`;
timeouts, transport failures, and HTTP 5xx responses are persisted as
`creation_unknown`. Inspect any unknown creation outcome before removing the
metadata; do not rerun the original create command.

If polling times out, resume the persisted task with
`python3 scripts/seedance_generate.py --resume output/seedance-video.json`.
The downloader follows only validated HTTPS redirects, streams into a temporary
file, requires a video or binary Content-Type, rejects empty or oversized
content, and atomically replaces the output. The output and metadata paths must
remain distinct. Credentials must never appear in prompts, metadata, logs, or
committed files.

## Review

Judge the returned take against the approved beat, identity and product
continuity, action completion, camera intent, lighting, audio, and delivery
requirements. Keep successful footage. For a retake, change one causal variable
at a time and keep an explicit attempt budget.

This adaptation preserves the upstream MIT work from
`Emily2040/seedance-2.0` at commit
`57d01dc66f93ecb03c2475be5f22dc416d9b701d`.
