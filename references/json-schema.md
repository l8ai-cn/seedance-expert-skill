# Seedance Prompt JSON Schema

Use this schema when the user wants structured output or when an automation pipeline needs stable fields.

```json
{
  "mode": "t2v | i2v | v2v | r2v | flf2v | edit | extend | audio-led",
  "duration": "string",
  "aspect_ratio": "string",
  "references": [
    {
      "binding_id": "character_identity",
      "media_type": "image | video | audio",
      "control_role": "identity | product | pose | environment | style | motion | camera | pacing | blocking | voice | rhythm | ambience | music | tempo | source_clip | first_frame | last_frame",
      "surface_resolution": "external_opaque_handle | derived_media_ordinal | structured_request_role"
    }
  ],
  "characters": [],
  "production": {
    "phase": "brief | preproduction | generation | review | post | localization | delivery",
    "role": "director | dp | producer | editor | colorist | sound | localization | qc",
    "delivery_surface": "web | broadcast | social | theatrical | client_review | archive",
    "approval_owner": ""
  },
  "shot_list": [
    {
      "shot_id": "S01_SH01",
      "purpose": "establish | reveal | demonstrate | emotional_turn | end_card",
      "shot_contract": "shot size, angle, lens feel, camera move, endpoint",
      "start_frame": "",
      "end_frame": "",
      "risks": []
    }
  ],
  "continuity_anchors": {
    "character": [],
    "product": [],
    "wardrobe": [],
    "props": [],
    "location": "",
    "screen_direction": "",
    "eyeline": "",
    "lighting_state": "",
    "audio_state": ""
  },
  "scene": "",
  "camera": "",
  "motion": "",
  "lighting": "",
  "style": "",
  "audio": "",
  "color_pipeline": {
    "look_intent": "",
    "working_assumption": "",
    "output_transform": "SDR Rec.709 | HDR PQ | theatrical | social",
    "show_lut_or_cdl_notes": "",
    "qc_notes": []
  },
  "subtitle_plan": {
    "subtitles": false,
    "sdh": false,
    "forced_narrative": false,
    "dubbing": false,
    "textless_required": false,
    "languages": []
  },
  "audio_deliverables": {
    "full_mix": true,
    "stems": [],
    "m_and_e": false,
    "loudness_target": "",
    "sync_cues": []
  },
  "delivery": {
    "frame_rate": "",
    "resolution": "",
    "aspect_ratio": "",
    "safe_area": "",
    "version_name": "",
    "qc_checks": []
  },
  "safety_notes": [],
  "final_prompt": ""
}
```

The JSON wrapper is for planning. `binding_id` is semantic and must never contain guessed provider syntax. Resolve it through the selected surface operation: preserve an externally captured handle only where required, derive only an evidence-pinned ordinal, or assign a structured request role with no text token. The final prompt still needs to read naturally. For professional work, keep the production, shot-list, continuity, localization, audio, color, and delivery fields as handoff metadata; do not cram all of them into the prompt.

## Sequence-State Schemas

Version 6 adds machine-valid state fixtures under `schemas/`:

- `project-state.schema.json` for project state, story, scenes, beats, clip lineage, take history, canon revision, and reference registry.
- `clip-contract.schema.json` for the current clip production task.
- `take-review.schema.json` for observed start/end state, accepted deviations, completed beats, and rejection/repair verdicts.
- `prompt-spec.schema.json` for internal prompt compilation metadata.
- `generation-run.schema.json` for synthetic benchmark and local run records.

These schemas are planning artifacts. The final Seedance prompt remains natural language unless the user explicitly requests structured output.

## V7 Paired-Language Contracts

The candidate English/Simplified Chinese path uses strict nested contracts instead of translating the planning wrapper above:

- `reference-manifest.schema.json` owns target/dimension authority and selected asset order;
- `scene-ir.schema.json` owns the causal event graph, camera observability, audio links, and requested invariants;
- `surface-binding-set.schema.json` owns binding-only provider input and contains no prompt prose;
- `prompt-realization-catalog.schema.json` owns hash-bound `en` and `zh-Hans` catalog forms plus their declared attestation status;
- `prompt-program.schema.json` records the one ordered, surface-independent semantic trace, including units whose static meaning is assigned to structured frame roles; and
- `prompt-render.schema.json` records both candidate renders, typed segments, hash-bound binding-to-authority traces, surface bindings, request-carried assignments, evidence, parity hashes, and diagnostics.

Run `scripts/semantic_lint.py` to build and validate the semantic program, then `scripts/prompt_compile.py --preview-candidate` to render the paired prompts. Local schema validity is necessary but not sufficient: the runtime also recomputes source hashes, exact catalog coverage, binding order/media alignment, semantic-unit order, UTF-8 byte-span/value-hash provenance for every resolved catalog atom, request-carried structured-role assignments, compiler and toolchain lineage, evidence expiry, and output hashes. The compiler envelope has a 64 MiB aggregate UTF-8 ceiling even when its nested documents are locally schema-valid. V7-07 rejects dialogue, voiceover, and multi-shot input rather than inventing missing semantic contracts.

The checked-in catalog fixture uses `unattested_fixture` so it cannot be mistaken for a real bilingual approval. Public runtime commands reject that test marker. Production must supply an actual user/reviewer declaration for the catalog rows, then separately review the compiler-authored grammar and final prompt pair.
