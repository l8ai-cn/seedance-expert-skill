#!/usr/bin/env python3
"""Render a paired English/zh-Hans V7-09 AV candidate preview.

Exact speech bytes are copied directly from scene-ir-v2 into both locale
renders.  They never enter the realization catalog.  Surface bindings remain
typed request data and this module contains no provider execution path.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from datetime import date

try:
    from . import render_surface_bindings as bindings
    from . import semantic_lint as v1_lint
    from . import semantic_lint_v2 as lint
except ImportError:  # pragma: no cover - CLI path
    import render_surface_bindings as bindings
    import semantic_lint as v1_lint
    import semantic_lint_v2 as lint


ROOT = Path(__file__).resolve().parents[1]
RENDER_URI = "https://github.com/Emily2040/seedance-2.0/schemas/prompt-render-v2.schema.json"
MAX_RENDER_BYTES = 512 * 1024
LOCALES = ("en", "zh-Hans")
TRANSITIONS = {
    "en": {"hard_cut": "Hard cut", "match_cut": "Match cut", "dissolve": "Dissolve", "fade": "Fade"},
    "zh-Hans": {"hard_cut": "硬切", "match_cut": "匹配剪辑", "dissolve": "叠化", "fade": "淡变"},
}
AUDIO_NAMES = {
    "en": {"dialogue": "Dialogue", "voiceover": "Voice-over", "sound_effect": "Sound effect", "ambience": "Ambience", "music": "Music", "rhythm": "Rhythm", "silence": "Silence"},
    "zh-Hans": {"dialogue": "对白", "voiceover": "旁白", "sound_effect": "音效", "ambience": "环境声", "music": "音乐", "rhythm": "节奏", "silence": "静音"},
}
OVERLAP_NAMES = {
    "en": {"no_overlap": "no overlapping speech", "overlap_allowed": "overlapping speech is allowed"},
    "zh-Hans": {"no_overlap": "不与其他台词重叠", "overlap_allowed": "允许与其他台词重叠"},
}
LIP_SYNC_NAMES = {
    "en": {"required": "visible lip sync required", "not_required": "visible lip sync not required", "post_only": "lip sync handled only in post"},
    "zh-Hans": {"required": "需要可见口型同步", "not_required": "不要求可见口型同步", "post_only": "口型同步仅在后期处理"},
}


class PromptCompileV2Error(bindings.BindingError):
    """Stable, non-echoing paired-render failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise PromptCompileV2Error(code, pointer)


def _canonical_sha(value: object) -> str:
    return bindings.sha256_bytes(bindings.canonical_json(value))


def _toolchain_sha256() -> str:
    paths = (
        "scripts/render_surface_bindings.py",
        "scripts/semantic_lint.py",
        "scripts/semantic_lint_v2.py",
        "scripts/scene_ir_v2_check.py",
        "scripts/prompt_compile_v2.py",
        "schemas/prompt-compile-request-v2.schema.json",
        "schemas/prompt-realization-catalog-v2.schema.json",
        "schemas/prompt-program-v2.schema.json",
        "schemas/prompt-render-v2.schema.json",
        "schemas/scene-ir-v2.schema.json",
        "schemas/surface-av-policy.schema.json",
        "schemas/surface-binding-set-v2.schema.json",
    )
    rows = []
    for path in paths:
        candidate = ROOT / path
        if not candidate.is_file():
            _fail("COMPILE002_TOOLCHAIN_INCOMPLETE", "/compiler_toolchain")
        rows.append({"path": path, "sha256": bindings.sha256_bytes(candidate.read_bytes())})
    return _canonical_sha(rows)


def _substitute_entities(value: str, catalog: dict[str, dict[str, str]], locale: str, pointer: str) -> str:
    field = "en" if locale == "en" else "zh_hans"

    def replace(match: re.Match[str]) -> str:
        key = f"entity.{match.group(1)}.label"
        try:
            return catalog[key][field]
        except KeyError:
            _fail("PRM004_ENTITY_AMBIGUOUS", pointer)

    resolved = v1_lint.ENTITY_TOKEN.sub(replace, value)
    category = "audio" if pointer.startswith("/audio") else "camera" if "/camera/" in pointer else "event" if pointer.startswith("/event") else "invariant"
    try:
        return v1_lint.validate_composed_text(resolved, pointer, locale=locale, category=category, language_view=value)
    except bindings.BindingError as exc:
        raise PromptCompileV2Error(exc.code, exc.pointer) from None


def _catalog_value(catalog: dict[str, dict[str, str]], key: str, locale: str) -> str:
    field = "en" if locale == "en" else "zh_hans"
    try:
        raw = catalog[key][field]
    except KeyError:
        _fail("PRM025_LOCALE_CATALOG_INVALID", f"/realization_catalog/{key}")
    return _substitute_entities(raw, catalog, locale, f"/{key.replace('.', '/')}")


class _Writer:
    def __init__(self, program: dict[str, Any]) -> None:
        self.payload = bytearray()
        self.spans: list[dict[str, Any]] = []
        self.program = program
        self.traces: dict[str, tuple[int | None, int | None, str | None]] = {}

    def append(self, value: str) -> None:
        self.payload.extend(value.encode("utf-8"))

    def append_unit(self, unit_id: str, value: str) -> None:
        start = len(self.payload)
        raw = value.encode("utf-8")
        self.payload.extend(raw)
        self.traces[unit_id] = (start, len(self.payload), bindings.sha256_bytes(raw))

    def utterance(self, value: str, *, unit_id: str, audio_event_id: str, speaker_id: str, spoken_language: str, turn_index: int, utterance_sha256: str) -> None:
        raw = value.encode("utf-8")
        start = len(self.payload)
        self.payload.extend(raw)
        end = len(self.payload)
        if bindings.sha256_bytes(raw) != utterance_sha256:
            _fail("AUDIO006_UTTERANCE_HASH_MISMATCH", "/scene_ir/audio_events")
        self.spans.append({"audio_event_id": audio_event_id, "speaker_id": speaker_id, "spoken_language": spoken_language, "turn_index": turn_index, "utterance_sha256": utterance_sha256, "start_byte": start, "end_byte": end})
        self.traces[unit_id] = (start, end, utterance_sha256)

    def finish(self, locale: str) -> dict[str, Any]:
        if not self.payload or len(self.payload) > MAX_RENDER_BYTES:
            _fail("PRM015_BUDGET_EXCEEDED", f"/renders/{locale}")
        try:
            text = bytes(self.payload).decode("utf-8")
        except UnicodeDecodeError:
            _fail("PRM013_UNICODE_UNSAFE", f"/renders/{locale}")
        for span in self.spans:
            raw = bytes(self.payload[span["start_byte"]:span["end_byte"]])
            if bindings.sha256_bytes(raw) != span["utterance_sha256"]:
                _fail("AUDIO007_UTTERANCE_LOCALE_MUTATION", f"/renders/{locale}/utterance_spans")
        semantic_trace: list[dict[str, Any]] = []
        for unit in self.program["units"]:
            start, end, digest = self.traces.get(unit["unit_id"], (None, None, unit["content_sha256"]))
            if unit["emission"] == "prompt" and (start is None or end is None or digest is None):
                _fail("PARITY001_SEMANTIC_TRACE_MISMATCH", f"/renders/{locale}/semantic_trace")
            semantic_trace.append({
                "unit_id": unit["unit_id"],
                "kind": unit["kind"],
                "emission": unit["emission"],
                "source_ids": unit["source_ids"],
                "semantic_key": unit["semantic_key"],
                "content_sha256": digest,
                "start_byte": start,
                "end_byte": end,
            })
        return {"locale": locale, "text": text, "text_sha256": bindings.sha256_bytes(bytes(self.payload)), "utterance_spans": self.spans, "semantic_trace": semantic_trace}


def _shot_header(locale: str, grammar: str, index: int) -> str:
    if grammar == "ascii_numbered_shot_labels":
        return f"Shot {index}:\n"
    if grammar == "localized_numbered_shot_labels":
        return f"Shot {index}:\n" if locale == "en" else f"镜头 {index}：\n"
    if grammar == "ordered_paragraphs":
        return ""
    _fail("MS007_SURFACE_GRAMMAR_UNRESOLVED", "/surface_av_policy/multi_shot/grammar")


def _timing_text(locale: str, timing: dict[str, Any], catalog: dict[str, dict[str, str]]) -> str:
    mode = timing["mode"]
    if mode == "visual_event_window":
        start_id = timing.get("start_event_id")
        end_id = timing.get("end_event_id")
        if not isinstance(start_id, str) or not isinstance(end_id, str):
            _fail("AUDIO001_TEMPORAL_RELATIONSHIP_INVALID", "/scene_ir/audio_events/timing")
        start_text = _catalog_value(catalog, f"event.{start_id}.visible_state_change", locale)
        end_text = _catalog_value(catalog, f"event.{end_id}.visible_state_change", locale)
        if start_id == end_id:
            return f" at the visible event '{start_text}'" if locale == "en" else f"，对应可见事件“{start_text}”"
        return (
            f" from the visible event '{start_text}' through '{end_text}'"
            if locale == "en"
            else f"，从可见事件“{start_text}”持续到“{end_text}”"
        )
    if mode == "continuous_shot":
        return " throughout its shot" if locale == "en" else "，贯穿所属镜头"
    if mode == "continuous_sequence":
        return " throughout the sequence" if locale == "en" else "，贯穿整个序列"
    if mode == "relative_beat":
        label = timing.get("beat_label")
        cue_id = timing.get("cue_event_id")
        if not isinstance(label, str) or not label or not isinstance(cue_id, str):
            _fail("AUDIO001_TEMPORAL_RELATIONSHIP_INVALID", "/scene_ir/audio_events/timing/beat_label")
        cue_text = _catalog_value(catalog, f"event.{cue_id}.visible_state_change", locale)
        return f" on cue {label} at '{cue_text}'" if locale == "en" else f"，在“{cue_text}”事件的 {label} 节拍触发"
    if mode != "surface_exact_range":
        _fail("AUDIO001_TEMPORAL_RELATIONSHIP_INVALID", "/scene_ir/audio_events/timing/mode")
    start = timing.get("start_seconds")
    end = timing.get("end_seconds")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or start < 0 or end <= start:
        _fail("PRM008_TIME_RANGE_UNEVIDENCED", "/scene_ir/audio_events/timing")
    return f" from {start:g} to {end:g} seconds" if locale == "en" else f"，从 {start:g} 秒到 {end:g} 秒"


def _render_locale(scene: dict[str, Any], policy: dict[str, Any], catalog: dict[str, dict[str, str]], program: dict[str, Any], locale: str) -> dict[str, Any]:
    writer = _Writer(program)
    if scene["take_structure"] == "single_continuous_take":
        writer.append_unit("take.structure", "Single continuous take; no cuts.\n" if locale == "en" else "单一连续镜头，不切镜。\n")
        grammar = "ordered_paragraphs"
    else:
        writer.append_unit("take.structure", "Edited multi-shot sequence.\n" if locale == "en" else "剪辑式多镜头序列。\n")
        grammar = policy["multi_shot"]["grammar"]
    transition_by_from = {item["from_shot_id"]: item for item in scene["transitions"]}
    for shot in scene["shots"]:
        shot_header = _shot_header(locale, grammar, shot["shot_index"]) if scene["take_structure"] == "edited_multi_shot" else "\n"
        writer.append_unit(f"shot.{shot['shot_id']}", shot_header or "\n")
        for event in shot["events"]:
            writer.append_unit(f"event.{event['event_id']}", _catalog_value(catalog, f"event.{event['event_id']}.visible_state_change", locale) + (".\n" if locale == "en" else "。\n"))
        move = shot["camera"]
        values = {field: _catalog_value(catalog, f"shot.{shot['shot_id']}.camera.{field}", locale) for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing")}
        labels = {
            "en": {"start_framing": "Camera opening", "path": "Camera path", "speed": "Camera speed", "subject_relationship": "Subject relationship", "endpoint_framing": "Camera endpoint"},
            "zh-Hans": {"start_framing": "镜头起始构图", "path": "镜头路径", "speed": "镜头速度", "subject_relationship": "主体关系", "endpoint_framing": "镜头结束构图"},
        }[locale]
        for field in ("start_framing", "path", "speed", "subject_relationship", "endpoint_framing"):
            writer.append_unit(f"camera.{shot['shot_id']}.{field}", f"{labels[field]}: {values[field]}.\n" if locale == "en" else f"{labels[field]}：{values[field]}。\n")
        transition = transition_by_from.get(shot["shot_id"])
        if transition is not None:
            writer.append_unit(f"transition.{transition['transition_id']}", f"{TRANSITIONS[locale][transition['transition_type']]}.\n" if locale == "en" else f"{TRANSITIONS[locale][transition['transition_type']]}。\n")

    speaker_by_id = {item["speaker_id"]: item for item in scene["speakers"]}
    for audio in scene["audio_events"]:
        speech = audio["speech"]
        if speech is not None and speaker_by_id[speech["speaker_id"]]["voice"]["mode"] == "post_dub":
            continue
        description = _catalog_value(catalog, f"audio.{audio['audio_event_id']}.description", locale)
        timing = _timing_text(locale, audio["timing"], catalog)
        name = AUDIO_NAMES[locale][audio["semantic_function"]]
        writer.append(name)
        writer.append_unit(f"audio_timing.{audio['audio_event_id']}", timing)
        writer.append(": " if locale == "en" else "：")
        writer.append_unit(f"audio.{audio['audio_event_id']}", description)
        writer.append(".\n" if locale == "en" else "。\n")
        if speech is not None:
            speaker = speaker_by_id[speech["speaker_id"]]
            speaker_name = _catalog_value(catalog, f"speaker.{speech['speaker_id']}.display_name", locale)
            delivery = _catalog_value(catalog, f"audio.{audio['audio_event_id']}.delivery_intent", locale)
            writer.append_unit(
                f"speech_delivery.{audio['audio_event_id']}",
                f"Delivery: {delivery}.\n" if locale == "en" else f"台词表达：{delivery}。\n",
            )
            writer.append_unit(
                f"speech_overlap.{audio['audio_event_id']}",
                f"Overlap: {OVERLAP_NAMES[locale][speech['overlap_policy']]}.\n" if locale == "en" else f"台词重叠：{OVERLAP_NAMES[locale][speech['overlap_policy']]}。\n",
            )
            writer.append_unit(
                f"speech_lip_sync.{audio['audio_event_id']}",
                f"Lip sync: {LIP_SYNC_NAMES[locale][speech['lip_sync']]}.\n" if locale == "en" else f"口型同步：{LIP_SYNC_NAMES[locale][speech['lip_sync']]}。\n",
            )
            if locale == "en":
                writer.append(f"{speaker_name} says exactly in {speech['spoken_language']}: \"")
            else:
                writer.append(f"{speaker_name}使用 {speech['spoken_language']} 原样说：\"")
            writer.utterance(speech["utterance"], unit_id=f"speech.{audio['audio_event_id']}", audio_event_id=audio["audio_event_id"], speaker_id=speech["speaker_id"], spoken_language=speech["spoken_language"], turn_index=speech["turn_index"], utterance_sha256=speech["utterance_sha256"])
            writer.append("\".\n" if locale == "en" else "\"。\n")
    for invariant in scene["requested_invariants"]:
        value = _catalog_value(catalog, f"invariant.{invariant['invariant_id']}.description", locale)
        writer.append_unit(f"invariant.{invariant['invariant_id']}", f"Constraint: {value}.\n" if locale == "en" else f"约束：{value}。\n")
    return writer.finish(locale)


def _post_only(scene: dict[str, Any]) -> list[dict[str, Any]]:
    speaker_by_id = {item["speaker_id"]: item for item in scene["speakers"]}
    result: list[dict[str, Any]] = []
    for audio in scene["audio_events"]:
        speech = audio["speech"]
        if speech is not None and speaker_by_id[speech["speaker_id"]]["voice"]["mode"] == "post_dub":
            result.append({"kind": "post_dub", "source_id": audio["audio_event_id"], "content_sha256": _canonical_sha(speech)})
    if scene["subtitle_policy"]["mode"] != "none":
        result.append({"kind": "post_subtitles", "source_id": "subtitle_policy", "content_sha256": _canonical_sha(scene["subtitle_policy"])})
    for fallback in scene["post_fallbacks"]:
        result.append({"kind": "post_fallback", "source_id": fallback["fallback_id"], "content_sha256": _canonical_sha(fallback)})
    return result


def _binding_trace(binding_set: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for binding in binding_set["bindings"]:
        if "prompt_visible_handle" in binding:
            kind = "opaque_external_handle"
        elif "structured_role" in binding:
            kind = "structured_role"
        else:
            kind = "typed_media"
        result.append({
            "binding_id": binding["binding_id"],
            "media_type": binding["media_type"],
            "binding_kind": kind,
            "binding_sha256": _canonical_sha(binding),
        })
    return result


def compile_request(value: object, *, preview_candidate: bool = False, allow_unattested_fixture: bool = False, today: date | None = None) -> dict[str, Any]:
    if not preview_candidate:
        _fail("CANDIDATE_PREVIEW_ONLY")
    try:
        scene, policy, binding_set, catalog, catalog_sha = lint.validate_request(value, allow_unattested_fixture=allow_unattested_fixture, today=today)
        program = lint.build_prompt_program(scene, policy, binding_set, catalog_sha)
    except bindings.BindingError as exc:
        raise PromptCompileV2Error(exc.code, exc.pointer) from None
    renders = [_render_locale(scene, policy, catalog, program, locale) for locale in LOCALES]
    left = [(item["audio_event_id"], item["speaker_id"], item["spoken_language"], item["turn_index"], item["utterance_sha256"]) for item in renders[0]["utterance_spans"]]
    right = [(item["audio_event_id"], item["speaker_id"], item["spoken_language"], item["turn_index"], item["utterance_sha256"]) for item in renders[1]["utterance_spans"]]
    if left != right:
        _fail("AUDIO007_UTTERANCE_LOCALE_MUTATION", "/renders")
    request_bindings = binding_set["bindings"]
    compiler_sha = bindings.sha256_bytes((ROOT / "scripts/prompt_compile_v2.py").read_bytes())
    diagnostics = ["CANDIDATE_PREVIEW_ONLY", "NO_PROVIDER_EXECUTION", "HUMAN_LANGUAGE_REVIEW_REQUIRED"]
    if policy["policy_kind"] == "unattested_fixture":
        diagnostics.append("UNATTESTED_POLICY_FIXTURE")
    return {
        "$schema": RENDER_URI,
        "schema_version": 2,
        "status": "unattested_fixture_preview" if policy["policy_kind"] == "unattested_fixture" else "candidate_preview",
        "preview": True,
        "runtime_enabled": False,
        "profile_id": policy["profile_id"],
        "operation": policy["operation"],
        "policy_id": policy["policy_id"],
        "state_binding": scene["state_binding"],
        "state_binding_sha256": _canonical_sha(scene["state_binding"]),
        "policy_provenance": program["policy_provenance"],
        "ordering": program["ordering"],
        "scene_ir_sha256": _canonical_sha(scene),
        "surface_av_policy_sha256": _canonical_sha(policy),
        "surface_binding_set_sha256": _canonical_sha(binding_set),
        "realization_catalog_sha256": catalog_sha,
        "prompt_program": program,
        "prompt_program_sha256": _canonical_sha(program),
        "compiler_sha256": compiler_sha,
        "compiler_toolchain_sha256": _toolchain_sha256(),
        "request_bindings": request_bindings,
        "request_bindings_sha256": _canonical_sha(request_bindings),
        "binding_trace": _binding_trace(binding_set),
        "renders": renders,
        "post_only": _post_only(scene),
        "diagnostics": diagnostics,
    }


def _self_test() -> None:
    try:
        lint._self_test()
    except bindings.BindingError as exc:
        raise PromptCompileV2Error(exc.code, exc.pointer) from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Render paired V7-09 AV candidate prompts from strict JSON.")
    parser.add_argument("request", nargs="?", default="-", help="JSON request path, or - for stdin")
    parser.add_argument("--preview-candidate", action="store_true")
    parser.add_argument("--allow-unattested-fixture", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("prompt compile v2 self-test passed")
            return 0
        raw = bindings._read_request(args.request)
        if len(raw) > lint.MAX_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        report = compile_request(bindings.parse_json_bytes(raw), preview_candidate=args.preview_candidate, allow_unattested_fixture=args.allow_unattested_fixture)
        payload = bindings.canonical_json(report)
    except bindings.BindingError as exc:
        print(f"prompt-compile-v2 error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
