from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scripts import evaluation_program_check as checker
from scripts import prompt_compile
from scripts import prompt_compile_v2
from scripts import render_surface_bindings as bindings


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "validation" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def v1_binding_set(profile_id: str, opaque_handle: str | None = None) -> dict:
    binding: dict[str, object] = {"binding_id": "product", "media_type": "image"}
    if opaque_handle is not None:
        binding["prompt_visible_handle"] = opaque_handle
    return {
        "$schema": prompt_compile.BINDING_SET_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": profile_id,
        "operation": "reference_generation",
        "bindings": [binding],
    }


def compile_v1(profile_id: str, opaque_handle: str | None = None) -> dict:
    manifest = fixture("reference-manifest.valid.json")
    manifest["profile_id"] = profile_id
    request = {
        "schema_version": 1,
        "reference_manifest": manifest,
        "scene_ir": fixture("scene-ir.valid.json"),
        "surface_binding_set": v1_binding_set(profile_id, opaque_handle),
        "realization_catalog": fixture("prompt-realization-catalog.valid.json"),
    }
    return prompt_compile.compile_request(
        request,
        preview_candidate=True,
        today=date(2026, 7, 12),
        _allow_unattested_fixture=True,
    )


class EvaluationMetamorphicTests(unittest.TestCase):
    def test_surface_swap_preserves_semantics(self) -> None:
        reports = {
            "byteplus.modelark": compile_v1("byteplus.modelark", "[[产品主图 🔒]]"),
            "fal.reference-to-video": compile_v1("fal.reference-to-video"),
            "volcengine.ark": compile_v1("volcengine.ark"),
        }
        baseline = reports["fal.reference-to-video"]
        for profile_id, report in reports.items():
            with self.subTest(profile=profile_id):
                self.assertEqual(report["reference_semantics_sha256"], baseline["reference_semantics_sha256"])
                self.assertEqual(report["prompt_program_sha256"], baseline["prompt_program_sha256"])
                self.assertEqual(
                    [render["semantic_unit_ids"] for render in report["renders"]],
                    [render["semantic_unit_ids"] for render in baseline["renders"]],
                )
                self.assertEqual(
                    [render["semantic_key_trace"] for render in report["renders"]],
                    [render["semantic_key_trace"] for render in baseline["renders"]],
                )
                self.assertEqual(
                    [(row["binding_id"], row["media_type"]) for row in report["request_bindings"]],
                    [(row["binding_id"], row["media_type"]) for row in baseline["request_bindings"]],
                )
        self.assertEqual(
            {report["request_transport"] for report in reports.values()},
            {"external_surface_unresolved", "typed_media_arrays", "ordered_content_objects"},
        )
        self.assertIn("[[产品主图 🔒]]", reports["byteplus.modelark"]["renders"][0]["rendered_prompt"])
        self.assertIn("@Image1", baseline["renders"][0]["rendered_prompt"])
        self.assertIn("图片1", reports["volcengine.ark"]["renders"][0]["rendered_prompt"])

    def test_language_swap_preserves_semantics(self) -> None:
        request = fixture("prompt-compile-request-v2.valid.json")
        baseline = prompt_compile_v2.compile_request(
            copy.deepcopy(request), preview_candidate=True, allow_unattested_fixture=True
        )
        with mock.patch.object(prompt_compile_v2, "LOCALES", ("zh-Hans", "en")):
            swapped = prompt_compile_v2.compile_request(
                copy.deepcopy(request), preview_candidate=True, allow_unattested_fixture=True
            )

        for field in ("prompt_program", "prompt_program_sha256", "ordering", "request_bindings", "binding_trace"):
            self.assertEqual(swapped[field], baseline[field])
        baseline_renders = {render["locale"]: render for render in baseline["renders"]}
        swapped_renders = {render["locale"]: render for render in swapped["renders"]}
        self.assertEqual(swapped_renders, baseline_renders)
        normalized_traces = {}
        for locale, render in baseline_renders.items():
            normalized_traces[locale] = [
                {
                    "unit_id": row["unit_id"],
                    "kind": row["kind"],
                    "emission": row["emission"],
                    "source_ids": row["source_ids"],
                    "semantic_key": row["semantic_key"],
                }
                for row in render["semantic_trace"]
            ]
        self.assertEqual(normalized_traces["en"], normalized_traces["zh-Hans"])
        traces = []
        for render in baseline_renders.values():
            raw = render["text"].encode("utf-8")
            span = render["utterance_spans"][0]
            self.assertEqual(raw[span["start_byte"] : span["end_byte"]], b"I found it.")
            traces.append(
                (span["audio_event_id"], span["speaker_id"], span["spoken_language"], span["turn_index"])
            )
        self.assertEqual(traces[0], traces[1])

    def test_reference_reorder_follows_profile(self) -> None:
        plan = {
            "$schema": bindings.PLAN_SCHEMA_URI,
            "schema_version": 1,
            "profile_id": "fal.reference-to-video",
            "operation": "reference_generation",
            "segments": [
                {"kind": "binding", "binding_id": "image-a"},
                {"kind": "text", "value": " with "},
                {"kind": "binding", "binding_id": "video-a"},
                {"kind": "text", "value": " then "},
                {"kind": "binding", "binding_id": "image-b"},
            ],
            "bindings": [
                {"binding_id": "image-a", "media_type": "image"},
                {"binding_id": "video-a", "media_type": "video"},
                {"binding_id": "image-b", "media_type": "image"},
            ],
        }
        registry = bindings.load_registry(ROOT)
        with mock.patch.object(bindings, "load_registry", return_value=registry):
            baseline = bindings.render_plan(copy.deepcopy(plan), preview_candidate=True, today=date(2026, 7, 13))
            reordered_plan = copy.deepcopy(plan)
            reordered_plan["bindings"] = [
                reordered_plan["bindings"][2],
                reordered_plan["bindings"][1],
                reordered_plan["bindings"][0],
            ]
            reordered = bindings.render_plan(reordered_plan, preview_candidate=True, today=date(2026, 7, 13))

        self.assertEqual(baseline["rendered_prompt"], "@Image1 with @Video1 then @Image2")
        self.assertEqual(reordered["rendered_prompt"], "@Image2 with @Video1 then @Image1")
        baseline_roles = {(row["binding_id"], row["media_type"]) for row in baseline["request_bindings"]}
        reordered_roles = {(row["binding_id"], row["media_type"]) for row in reordered["request_bindings"]}
        self.assertEqual(reordered_roles, baseline_roles)
        self.assertEqual(baseline["profile_id"], reordered["profile_id"])
        self.assertEqual(baseline["operation"], reordered["operation"])
        self.assertEqual(baseline["request_transport"], reordered["request_transport"])
        self.assertEqual(baseline["evidence_claim_ids"], reordered["evidence_claim_ids"])

    def test_final_frame_weakens_temporal_evidence(self) -> None:
        manifest_snapshot = checker.strict_load_snapshot(
            FIXTURES / "benchmark-manifest-v1.valid.json"
        )
        annotation = checker.strict_load_json(FIXTURES / "atomic-output-annotation-v1.valid.json")
        self.assertEqual(checker.validate_atomic_annotation(annotation, manifest_snapshot), [])
        attempt = manifest_snapshot.value["attempts"][0]

        derived = copy.deepcopy(annotation)
        derived.update({
            "evidence_asset_kind": "derived_final_frame",
            "evidence_asset_sha256": "10467e3558cff078bb98ac3363164bc1d4dce469ab4d5660503f55fd0d082361",
            "evidence_parent_output_sha256": attempt["output_media_sha256"],
            "derivation_record_sha256": "e136aa019a233120a713b40be72eaf97599ff393720344c27eba34647b5f4bbd",
            "evidence_locus": {"kind": "single_frame", "frame_index": attempt["frame_count"] - 1},
        })
        self.assertIn(
            "annotation.temporal_requires_video",
            checker.validate_atomic_annotation(derived, manifest_snapshot),
        )

        derived.update({
            "status": "unknown",
            "confidence": "unknown",
            "evidence_locus": {"kind": "unavailable"},
        })
        self.assertEqual(checker.validate_atomic_annotation(derived, manifest_snapshot), [])


if __name__ == "__main__":
    unittest.main()
