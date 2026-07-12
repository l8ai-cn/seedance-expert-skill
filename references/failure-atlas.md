# Failure Atlas

Use this reference when sequence or continuation output fails.

| Symptom | Likely cause | Primary repair variable |
|---|---|---|
| Continuation begins from planned ending | Parent observed state was not reviewed. | Replace opening with observed end state. |
| Action restarts | Completed beat was not marked already happened. | Add completed beat exclusion. |
| Future event appears early | Reserved beat leaked into prompt. | Remove future beat from prompt and endpoint. |
| Identity drifts through extensions | Continuity source displaced canonical identity reference. | Re-anchor identity from canonical image. |
| Screen direction flips | Axis was not locked or reset intentionally. | State screen direction or declare axis reset. |
| Open motion stops | Motion vector was not inherited. | Carry subject/camera speed and direction. |
| Camera phase restarts | Camera endpoint from parent was missing. | Start from observed camera phase. |
| Prop contradicts prior clip | Prop owner/position/condition was not tracked. | Add prop state handoff. |
| Dialogue repeats | Completed dialogue was not logged. | Mark line completed and continue audio phase. |
| Extension quality degrades | Extension depth and drift were ignored. | Re-anchor or create intentional next shot. |
| Two references fight over one attribute | The same target/dimension has multiple authority winners. | Choose one winner; exclude that dimension from every competing asset. |
| Donor identity, room, style, audio, or logo leaks | Leakage risks were not mapped to explicit exclusions. | Keep the donor's intended dimensions and exclude each observed competing dimension. |
| Extra reference makes the result less stable | The asset owns no necessary target/dimension. | Remove it; add references only to fill a documented authority gap. |
| Appearance image behaves like an endpoint request | Appearance authority was conflated with a structured first/last-frame role. | Select the exact supported operation and keep frame roles in request structure. |
| Contact happens but nothing visibly changes | The decisive event has no observable response. | Add one visible consequence and a settled endpoint. |
| Action order collapses | Events lack backward dependencies or a reachable causal chain. | Order initial state, trigger, decisive change, response, follow-through, and endpoint. |
| Key action is hidden | The camera cannot observe the before-state, decisive event, consequence, and endpoint. | Change blocking/framing or simplify to one primary move that can see them. |
| Audio lands at the wrong moment or serves the wrong purpose | Timing and semantic function were conflated. | Specify when the cue occurs separately from whether it is dialogue, SFX, ambience, music, rhythm, or silence. |
| Event density is too high | Several beats were compiled into one prompt. | Reassign future beats to later clips. |
| English and Chinese prompts change actor, direction, event order, or endpoint | One finished prompt was translated instead of rendering both locales from one semantic program. | Repair the hash-bound paired catalog entry, obtain human attestation, and recompile both locales together. |
| A localized prompt changes or renumbers an `@` reference | Provider syntax was treated as natural language. | Restore the externally captured opaque handle byte-for-byte or the evidence-pinned derived binding; never translate or normalize it. |
| Two localized entities collapse to the same name or turn into pronouns | Stable entity aliases were omitted or collided. | Give every entity one distinct reviewed label per locale and use closed entity tokens in events, audio, and invariants. |
| Timing becomes an invented timestamp or strict second range | Locale prose added unsupported timing precision. | Keep causal phase order; remove unevidenced timestamps and strict time ranges. |
| Paired compiler rejects dialogue or voiceover | Scene IR v1 lacks an exact utterance, resolved speaker, spoken-language tag, and subtitle policy. | Keep dialogue outside V7-07 or wait for the versioned dialogue contract; do not invent or translate a line. |
| Paired compiler rejects multiple shots | Scene IR v1 has no typed transition or evidenced surface timeline grammar. | Compile one shot/clip at a time; do not infer a cut or timestamp from array order. |
| Surface binding order differs from selected asset order | The binding set was reordered during prompt assembly or locale handling. | Restore the manifest `selection_order`; a locale change may alter prose, not binding identity or order. |

## Paired compiler language-layer and common transport index

The offline language tools return stable codes and JSON pointers without echoing input. This table is not exhaustive for inherited profile, binding, manifest, or scene checks; those upstream codes propagate unchanged. Repair the pointed field and consult the V7-05/V7-06 migration diagnostics; never work around a failure by deleting a semantic unit or editing a finished locale prompt.

| Code family | Repair |
|---|---|
| `JSON_INVALID` | Serialize one complete JSON object without comments, trailing commas, or concatenated documents. |
| `JSON_DUPLICATE_KEY`, `JSON_NONFINITE_NUMBER`, `JSON_NUMBER_OUT_OF_RANGE`, `JSON_TOO_DEEP`, `JSON_TOO_LARGE`, `JSON_UTF8_REQUIRED`, `JSON_BOM_FORBIDDEN` | Re-serialize one bounded UTF-8 JSON object with unique keys, finite numbers, supported depth, and no BOM. |
| `TYPE_OBJECT_REQUIRED`, `OBJECT_FIELDS_INVALID`, `ARRAY_LENGTH_INVALID` | Rebuild the pointed closed object/array from its schema without extra convenience fields. |
| `PROFILE_CANDIDATE_REQUIRES_PREVIEW` | Use the explicit non-activating `--preview-candidate` gate; it does not submit a provider request. |
| `REFERENCE_MANIFEST_CONTRACT_INVALID`, `SCENE_IR_CONTRACT_INVALID` | Repair the upstream V7-06 contract at its pointer before language compilation. |
| `PROFILE_EVIDENCE_EXPIRED`, `REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH`, `REF003_STRUCTURED_ROLE_USE_MISMATCH` | Refresh reviewed evidence or repair role/use plus the four explicit structured-frame authority dimensions; never compensate in prose. |
| `COMPILE001_REQUEST_CONTRACT_INVALID` | Restore the exact version-1 envelope and allowed keys. |
| `LANG001_UNSTABLE_SUBJECT_ALIAS` | Replace pronouns with the required closed entity token and stable localized label. |
| `LANG003_LOCALIZATION_SET_MISMATCH` | Rebuild the exact ordered catalog-key set from the current scene IR. |
| `PARITY001_SEMANTIC_TRACE_MISMATCH` | Repair the catalog key, entity substitution, or exact emitted value span named by the pointer. |
| `PARITY002_LOCALIZED_UNIT_ORDER_MISMATCH` | Restore one shared semantic-unit order for both locales. |
| `PRM001_EVENT_COVERAGE_INVALID`, `PRM002_CAUSAL_ORDER_INVALID` | Rebuild event coverage and order from the causal graph. |
| `PRM003_ALIAS_COLLISION`, `PRM004_ENTITY_AMBIGUOUS` | Use distinct labels, exact entity tokens, and an explicit screen/subject/world direction frame. |
| `PRM007_CAMERA_AUDIO_CONFLATED` | Move camera and audio meaning back to their separately owned units. |
| `PRM008_TIME_RANGE_UNEVIDENCED` | Remove exact seconds, frames, or timestamps; retain causal phase order. |
| `PRM009_BINDING_CORE_MISMATCH`, `REF001_BINDING_ORDER_MISMATCH` | Rebuild binding identity, media, profile, operation, and order from the manifest. |
| `PRM010_SURFACE_SEMANTIC_DRIFT` | Rerun all passes from one unchanged profile/evidence snapshot. |
| `PRM011_META_INSTRUCTION` | Remove instruction-override prose from catalog text or opaque-handle composition. |
| `PRM012_SECRET_OR_LOCATOR` | Remove credential-, URL-, and path-shaped content. |
| `PRM013_UNICODE_UNSAFE` | Normalize authored catalog text to NFC and remove unsafe controls, default-ignorables, or visually blank mask characters; opaque handles are rejected without rewriting their bytes. |
| `PRM014_PROGRAM_HASH_MISMATCH` | Rebuild from the exact manifest, scene, catalog, and compiler lineage. |
| `PRM015_BUDGET_EXCEEDED` | Reduce semantic density or split the shot; output is never truncated. |
| `PRM017_ENDPOINT_NOT_FINAL` | State an observable completed endpoint, make zero/absent/dissipated dynamics explicit, and keep unrelated ambient motion out of the subject's endpoint row. |
| `PRM021_DIALOGUE_TEXT_REQUIRED` | Defer dialogue/voiceover until an exact speaker/language/utterance contract exists. |
| `PRM022_MULTI_SHOT_DEFERRED` | Compile one shot at a time until transitions are typed. |
| `PRM023_EVENT_TEXT_DUPLICATE` | Give each event a distinct observable localized state change. |
| `PRM025_LOCALE_CATALOG_INVALID` | Repair the pointed shape, attestation declaration, source hash, text, or endpoint field and renew the declaration for the resulting canonical catalog hash. |
