from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - validation dependency is CI-only
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prompt_compile_v2 as compiler
import render_surface_bindings as bindings
import semantic_lint_v2 as lint


def fixture() -> dict:
    return json.loads((ROOT / "validation/fixtures/prompt-compile-request-v2.valid.json").read_text(encoding="utf-8"))


def rebind_scene(request: dict) -> None:
    request["realization_catalog"]["scene_ir_sha256"] = lint._canonical_sha(request["scene_ir"])


def rebind_policy(request: dict) -> None:
    policy = request["surface_av_policy"]
    request["surface_binding_set"]["policy_id"] = policy["policy_id"]
    request["surface_binding_set"]["surface_av_policy_sha256"] = lint._canonical_sha(policy)


def schema_validator(name: str):
    assert Draft202012Validator is not None
    schema = json.loads((ROOT / f"schemas/{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class PromptCompileV2Tests(unittest.TestCase):
    def compile(self, request: dict | None = None) -> dict:
        return compiler.compile_request(fixture() if request is None else request, preview_candidate=True, allow_unattested_fixture=True)

    def test_exact_utterance_bytes_and_order_are_identical_in_both_locales(self) -> None:
        report = self.compile()
        self.assertEqual(report["status"], "unattested_fixture_preview")
        self.assertIn("UNATTESTED_POLICY_FIXTURE", report["diagnostics"])
        expected = b"I found it."
        traces = []
        for render in report["renders"]:
            raw = render["text"].encode("utf-8")
            self.assertEqual(len(render["utterance_spans"]), 1)
            span = render["utterance_spans"][0]
            self.assertEqual(raw[span["start_byte"]:span["end_byte"]], expected)
            self.assertEqual(bindings.sha256_bytes(expected), span["utterance_sha256"])
            traces.append((span["audio_event_id"], span["speaker_id"], span["spoken_language"], span["turn_index"], span["utterance_sha256"]))
        self.assertEqual(traces[0], traces[1])

    def test_semantic_trace_covers_every_unit_and_is_byte_exact(self) -> None:
        report = self.compile()
        units = report["prompt_program"]["units"]
        for render in report["renders"]:
            self.assertEqual([row["unit_id"] for row in render["semantic_trace"]], [row["unit_id"] for row in units])
            raw = render["text"].encode("utf-8")
            for unit, trace in zip(units, render["semantic_trace"]):
                self.assertEqual(trace["emission"], unit["emission"])
                if unit["emission"] == "prompt":
                    chunk = raw[trace["start_byte"]:trace["end_byte"]]
                    self.assertEqual(bindings.sha256_bytes(chunk), trace["content_sha256"])
                else:
                    self.assertIsNone(trace["start_byte"])
                    self.assertIsNone(trace["end_byte"])

    def test_delivery_overlap_and_lip_sync_mutations_change_both_renders(self) -> None:
        baseline = self.compile()
        cases = []

        delivery = fixture()
        speech = delivery["scene_ir"]["audio_events"][0]["speech"]
        speech["delivery_intent"] = "Whispered, urgent, and sharply articulated."
        entry = next(
            row
            for row in delivery["realization_catalog"]["entries"]
            if row["semantic_key"] == "audio.detective_line.delivery_intent"
        )
        entry.update({
            "source_sha256": bindings.sha256_bytes(speech["delivery_intent"].encode("utf-8")),
            "en": "whispered, urgent, and sharply articulated",
            "zh_hans": "低声、急迫且咬字锐利",
        })
        rebind_scene(delivery)
        cases.append(("speech_delivery.detective_line", self.compile(delivery)))

        overlap = fixture()
        overlap["scene_ir"]["audio_events"][0]["speech"]["overlap_policy"] = "overlap_allowed"
        rebind_scene(overlap)
        cases.append(("speech_overlap.detective_line", self.compile(overlap)))

        lip_sync = fixture()
        lip_sync["scene_ir"]["audio_events"][0]["speech"]["lip_sync"] = "not_required"
        rebind_scene(lip_sync)
        cases.append(("speech_lip_sync.detective_line", self.compile(lip_sync)))

        for unit_id, changed in cases:
            with self.subTest(unit_id=unit_id):
                changed_unit = next(row for row in changed["prompt_program"]["units"] if row["unit_id"] == unit_id)
                self.assertEqual(changed_unit["emission"], "prompt")
                for before_render, after_render in zip(baseline["renders"], changed["renders"]):
                    self.assertNotEqual(before_render["text"], after_render["text"])
                    self.assertNotEqual(before_render["text_sha256"], after_render["text_sha256"])
                    trace = next(row for row in after_render["semantic_trace"] if row["unit_id"] == unit_id)
                    self.assertEqual(trace["emission"], "prompt")
                    self.assertIsInstance(trace["start_byte"], int)
                    self.assertIsInstance(trace["end_byte"], int)
                    self.assertIsNotNone(trace["content_sha256"])

    def test_visual_event_window_mutation_changes_render_and_timing_provenance(self) -> None:
        first = fixture()
        first_timing = first["scene_ir"]["audio_events"][1]["timing"]
        first_timing.update({
            "mode": "visual_event_window",
            "start_event_id": "shot_01_open",
            "end_event_id": "shot_02_end",
        })
        rebind_scene(first)
        first_report = self.compile(first)

        second = copy.deepcopy(first)
        second_timing = second["scene_ir"]["audio_events"][1]["timing"]
        second_timing.update({"start_event_id": "shot_01_end", "end_event_id": "shot_02_open"})
        rebind_scene(second)
        second_report = self.compile(second)

        unit_id = "audio_timing.platform_ambience"
        first_unit = next(row for row in first_report["prompt_program"]["units"] if row["unit_id"] == unit_id)
        second_unit = next(row for row in second_report["prompt_program"]["units"] if row["unit_id"] == unit_id)
        self.assertEqual(first_unit["source_ids"], ["platform_ambience", "shot_01_open", "shot_02_end"])
        self.assertEqual(second_unit["source_ids"], ["platform_ambience", "shot_01_end", "shot_02_open"])
        self.assertNotEqual(first_unit["content_sha256"], second_unit["content_sha256"])
        for first_render, second_render in zip(first_report["renders"], second_report["renders"]):
            self.assertNotEqual(first_render["text"], second_render["text"])
            self.assertNotEqual(first_render["text_sha256"], second_render["text_sha256"])
            first_trace = next(row for row in first_render["semantic_trace"] if row["unit_id"] == unit_id)
            second_trace = next(row for row in second_render["semantic_trace"] if row["unit_id"] == unit_id)
            self.assertEqual(first_trace["source_ids"], first_unit["source_ids"])
            self.assertEqual(second_trace["source_ids"], second_unit["source_ids"])
            self.assertNotEqual(first_trace["content_sha256"], second_trace["content_sha256"])

    def test_authorized_voice_is_request_carried_with_ordered_provenance(self) -> None:
        request = fixture()
        policy_audio = request["surface_av_policy"]["audio"]
        policy_audio["voice_modes"].append("authorized_reference")
        policy_audio["voice_reference_status"] = "supported"
        request["surface_binding_set"]["bindings"].append({
            "binding_id": "detective_voice_audio",
            "media_type": "audio",
        })
        voice = request["scene_ir"]["speakers"][0]["voice"]
        voice.update({
            "mode": "authorized_reference",
            "authority_target_id": "detective",
            "asset_id": "detective_voice_audio",
            "authorization_status": "user_attested_authorized",
            "attestation_sha256": "a" * 64,
        })
        rebind_policy(request)
        rebind_scene(request)
        report = self.compile(request)

        unit_id = "voice_binding.detective_voice"
        unit = next(row for row in report["prompt_program"]["units"] if row["unit_id"] == unit_id)
        self.assertEqual(unit["emission"], "request_carried")
        self.assertEqual(unit["speaker_id"], "detective_voice")
        self.assertEqual(unit["source_ids"], ["detective_voice", "detective", "detective_voice_audio"])
        self.assertIsNotNone(unit["content_sha256"])
        for render in report["renders"]:
            trace = next(row for row in render["semantic_trace"] if row["unit_id"] == unit_id)
            self.assertEqual(trace["emission"], "request_carried")
            self.assertEqual(trace["source_ids"], unit["source_ids"])
            self.assertEqual(trace["content_sha256"], unit["content_sha256"])
            self.assertIsNone(trace["start_byte"])
            self.assertIsNone(trace["end_byte"])
            self.assertNotIn("detective_voice_audio", render["text"])

    def test_post_dub_and_subtitles_are_post_only_and_never_emit(self) -> None:
        request = fixture()
        voice = request["scene_ir"]["speakers"][0]["voice"]
        voice.update({"mode": "post_dub", "authority_target_id": None, "asset_id": None, "authorization_status": "not_applicable", "attestation_sha256": None})
        request["scene_ir"]["audio_events"][0]["speech"]["lip_sync"] = "post_only"
        rebind_scene(request)
        report = self.compile(request)
        for render in report["renders"]:
            self.assertNotIn("I found it.", render["text"])
            self.assertEqual(render["utterance_spans"], [])
            post_units = [row for row in render["semantic_trace"] if row["emission"] == "post_only"]
            self.assertTrue(post_units)
            self.assertTrue(all(row["start_byte"] is None for row in post_units))
        self.assertIn("post_dub", [item["kind"] for item in report["post_only"]])
        self.assertIn("post_subtitles", [item["kind"] for item in report["post_only"]])

    def test_empty_baseline_bindings_remain_empty_without_token_derivation(self) -> None:
        request = fixture()
        report = self.compile(request)
        self.assertEqual(request["surface_binding_set"]["bindings"], [])
        self.assertEqual(report["request_bindings"], [])
        self.assertEqual(report["binding_trace"], [])

    def test_hashes_state_policy_order_and_golden_fixture_match(self) -> None:
        report = self.compile()
        self.assertEqual(report["state_binding"], report["prompt_program"]["state_binding"])
        self.assertEqual(report["ordering"], report["prompt_program"]["ordering"])
        self.assertEqual(report["policy_provenance"], report["prompt_program"]["policy_provenance"])
        self.assertEqual(report["prompt_program_sha256"], compiler._canonical_sha(report["prompt_program"]))
        golden = json.loads((ROOT / "validation/fixtures/prompt-render-v2.valid.json").read_text(encoding="utf-8"))
        self.assertEqual(report, golden)

    def test_production_path_rejects_unattested_and_compiler_has_no_execution_imports(self) -> None:
        with self.assertRaises(bindings.BindingError) as caught:
            compiler.compile_request(fixture(), preview_candidate=True)
        self.assertEqual(caught.exception.code, "AVP004_UNATTESTED_POLICY_FORBIDDEN")
        source = (ROOT / "scripts/prompt_compile_v2.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import subprocess", "import requests", "urllib.request", "eval(", "exec("):
            self.assertNotIn(forbidden, source)

    def test_cli_is_byte_deterministic_across_ten_processes(self) -> None:
        raw = json.dumps(fixture(), ensure_ascii=False).encode("utf-8")
        script = ROOT / "scripts/prompt_compile_v2.py"
        expected = None
        for seed in (0, 1, 2, 3, 7, 11, 42, 101, 709, 999):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            completed = subprocess.run([sys.executable, "-B", str(script), "--preview-candidate", "--allow-unattested-fixture"], cwd=ROOT, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            expected = completed.stdout if expected is None else expected
            self.assertEqual(completed.stdout, expected)

    def test_all_prompt_schemas_use_only_local_refs(self) -> None:
        for name in ("prompt-compile-request-v2", "prompt-realization-catalog-v2", "prompt-program-v2", "prompt-render-v2"):
            schema = json.loads((ROOT / f"schemas/{name}.schema.json").read_text(encoding="utf-8"))
            pending = [schema]
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    for key, value in item.items():
                        if key == "$ref":
                            self.assertTrue(value.startswith("#"), (name, value))
                        pending.append(value)
                elif isinstance(item, list):
                    pending.extend(item)

    def test_request_schema_embeds_exact_authoritative_contracts(self) -> None:
        request_schema = json.loads((ROOT / "schemas/prompt-compile-request-v2.schema.json").read_text(encoding="utf-8"))

        def unprefix(value, prefix: str):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    if key == "$ref" and isinstance(item, str) and item.startswith(f"#/$defs/{prefix}"):
                        suffix = item.removeprefix(f"#/$defs/{prefix}")
                        result[key] = f"#/$defs/{suffix}"
                    else:
                        result[key] = unprefix(item, prefix)
                return result
            if isinstance(value, list):
                return [unprefix(item, prefix) for item in value]
            return value

        for filename, prefix, embedded_root in (
            ("scene-ir-v2.schema.json", "scene_", "scene_root"),
            ("surface-av-policy.schema.json", "policy_", "policy_root"),
            ("surface-binding-set-v2.schema.json", "binding_v2_", "binding_set"),
        ):
            source = json.loads((ROOT / f"schemas/{filename}").read_text(encoding="utf-8"))
            expected_root = {key: value for key, value in source.items() if key not in {"$schema", "$id", "title", "$comment", "$defs"}}
            self.assertEqual(unprefix(request_schema["$defs"][embedded_root], prefix), expected_root)
            for name, definition in source["$defs"].items():
                self.assertEqual(unprefix(request_schema["$defs"][f"{prefix}{name}"], prefix), definition, name)

    def test_render_embeds_exact_prompt_program_unit_contract(self) -> None:
        program = json.loads((ROOT / "schemas/prompt-program-v2.schema.json").read_text(encoding="utf-8"))["$defs"]["unit"]
        render = json.loads((ROOT / "schemas/prompt-render-v2.schema.json").read_text(encoding="utf-8"))["$defs"]
        binding = json.loads((ROOT / "schemas/surface-binding-set-v2.schema.json").read_text(encoding="utf-8"))["$defs"]["binding"]
        self.assertEqual(render["program_unit"]["properties"], program["properties"])
        self.assertEqual(render["program_unit"]["allOf"], program["allOf"])
        self.assertEqual(render["semantic_trace"]["properties"]["kind"], program["properties"]["kind"])
        self.assertEqual(render["binding"], binding)
        self.assertEqual(render["binding_trace"]["properties"]["binding_kind"], {"const": "typed_media"})

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_request_schema_rejects_malformed_nested_contracts(self) -> None:
        validator = schema_validator("prompt-compile-request-v2")
        self.assertEqual(list(validator.iter_errors(fixture())), [])

        invalid_scene = fixture()
        invalid_scene["scene_ir"]["shots"][0]["camera"]["move_kind"] = "teleport"
        invalid_policy = fixture()
        invalid_policy["surface_av_policy"]["audio"]["voice_reference_status"] = "magically_supported"
        invalid_binding = fixture()
        invalid_binding["surface_binding_set"]["bindings"].append({
            "binding_id": "picture_ref",
            "media_type": "image",
            "prompt_visible_handle": "@picture_ref",
        })
        for label, candidate in (("scene", invalid_scene), ("policy", invalid_policy), ("binding", invalid_binding)):
            with self.subTest(label=label):
                self.assertTrue(list(validator.iter_errors(candidate)))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_render_schema_requires_exactly_one_render_per_locale(self) -> None:
        validator = schema_validator("prompt-render-v2")
        valid = json.loads((ROOT / "validation/fixtures/prompt-render-v2.valid.json").read_text(encoding="utf-8"))
        self.assertEqual(list(validator.iter_errors(valid)), [])

        duplicate_locale = copy.deepcopy(valid)
        duplicate_locale["renders"][1]["locale"] = "en"
        self.assertTrue(list(validator.iter_errors(duplicate_locale)))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_render_schema_rejects_v1_binding_shapes(self) -> None:
        validator = schema_validator("prompt-render-v2")
        valid = json.loads((ROOT / "validation/fixtures/prompt-render-v2.valid.json").read_text(encoding="utf-8"))

        opaque_handle = copy.deepcopy(valid)
        opaque_handle["request_bindings"].append({
            "binding_id": "picture_ref",
            "media_type": "image",
            "prompt_visible_handle": "@picture_ref",
        })
        structured_trace = copy.deepcopy(valid)
        structured_trace["binding_trace"].append({
            "binding_id": "picture_ref",
            "media_type": "image",
            "binding_kind": "structured_role",
            "binding_sha256": "0" * 64,
        })
        for label, candidate in (("opaque handle", opaque_handle), ("structured trace", structured_trace)):
            with self.subTest(label=label):
                self.assertTrue(list(validator.iter_errors(candidate)))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_render_schema_rejects_illegal_trace_spans_and_hashes_by_emission(self) -> None:
        validator = schema_validator("prompt-render-v2")
        valid = json.loads((ROOT / "validation/fixtures/prompt-render-v2.valid.json").read_text(encoding="utf-8"))
        trace = valid["renders"][0]["semantic_trace"]
        prompt_index = next(index for index, row in enumerate(trace) if row["emission"] == "prompt")
        carried_index = next(index for index, row in enumerate(trace) if row["emission"] == "request_carried")
        review_index = next(index for index, row in enumerate(trace) if row["emission"] == "review_only")
        subtitle_index = next(index for index, row in enumerate(trace) if row["kind"] == "subtitle")

        cases = []
        missing_prompt_span = copy.deepcopy(valid)
        missing_prompt_span["renders"][0]["semantic_trace"][prompt_index]["start_byte"] = None
        cases.append(("prompt span must be present", missing_prompt_span))
        missing_prompt_hash = copy.deepcopy(valid)
        missing_prompt_hash["renders"][0]["semantic_trace"][prompt_index]["content_sha256"] = None
        cases.append(("prompt hash must be present", missing_prompt_hash))
        emitted_carried_span = copy.deepcopy(valid)
        emitted_carried_span["renders"][0]["semantic_trace"][carried_index]["start_byte"] = 0
        emitted_carried_span["renders"][0]["semantic_trace"][carried_index]["end_byte"] = 1
        cases.append(("request-carried span must be null", emitted_carried_span))
        missing_carried_hash = copy.deepcopy(valid)
        missing_carried_hash["renders"][0]["semantic_trace"][carried_index]["content_sha256"] = None
        cases.append(("request-carried hash must be present", missing_carried_hash))
        missing_review_hash = copy.deepcopy(valid)
        missing_review_hash["renders"][0]["semantic_trace"][review_index]["content_sha256"] = None
        cases.append(("review-only hash must be present", missing_review_hash))
        invented_subtitle_hash = copy.deepcopy(valid)
        invented_subtitle_hash["renders"][0]["semantic_trace"][subtitle_index]["content_sha256"] = "0" * 64
        cases.append(("post-only subtitle hash must be null", invented_subtitle_hash))

        post_dub_request = fixture()
        voice = post_dub_request["scene_ir"]["speakers"][0]["voice"]
        voice.update({"mode": "post_dub", "authority_target_id": None, "asset_id": None, "authorization_status": "not_applicable", "attestation_sha256": None})
        post_dub_request["scene_ir"]["audio_events"][0]["speech"]["lip_sync"] = "post_only"
        rebind_scene(post_dub_request)
        post_dub_render = self.compile(post_dub_request)
        self.assertEqual(list(validator.iter_errors(post_dub_render)), [])
        post_dub_audio_index = next(
            index
            for index, row in enumerate(post_dub_render["renders"][0]["semantic_trace"])
            if row["kind"] == "audio" and row["emission"] == "post_only"
        )
        invented_post_dub_audio_hash = copy.deepcopy(post_dub_render)
        invented_post_dub_audio_hash["renders"][0]["semantic_trace"][post_dub_audio_index]["content_sha256"] = "0" * 64
        cases.append(("post-only audio hash must be null", invented_post_dub_audio_hash))
        for label, candidate in cases:
            with self.subTest(label=label):
                self.assertTrue(list(validator.iter_errors(candidate)))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_render_embeds_prompt_program_emission_conditionals(self) -> None:
        validator = schema_validator("prompt-render-v2")
        valid = json.loads((ROOT / "validation/fixtures/prompt-render-v2.valid.json").read_text(encoding="utf-8"))
        for kind, illegal_emission in (("state", "prompt"), ("review", "prompt"), ("subtitle", "prompt")):
            candidate = copy.deepcopy(valid)
            unit = next(row for row in candidate["prompt_program"]["units"] if row["kind"] == kind)
            unit["emission"] = illegal_emission
            with self.subTest(kind=kind):
                self.assertTrue(list(validator.iter_errors(candidate)))


if __name__ == "__main__":
    unittest.main()
