from __future__ import annotations

import copy
import json
import random
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scripts import reference_planner as planner
from scripts import render_surface_bindings as bindings


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reference_planner.py"
FIXTURES = ROOT / "validation" / "fixtures"
FRESH_DATE = date(2026, 7, 17)
EXPIRED_DATE = date(2026, 7, 18)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fal_binding_plan(assets: list[dict]) -> dict:
    segments: list[dict] = []
    bindings_list: list[dict] = []
    for index, asset in enumerate(assets):
        if index:
            segments.append({"kind": "text", "value": "; "})
        segments.append({"kind": "binding", "binding_id": asset["asset_id"]})
        bindings_list.append(
            {"binding_id": asset["asset_id"], "media_type": asset["media_type"]}
        )
    segments.append({"kind": "text", "value": " follows only its declared authority."})
    return {
        "$schema": bindings.PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": "fal.reference-to-video",
        "operation": "reference_generation",
        "segments": segments,
        "bindings": bindings_list,
    }


def request_for(
    manifest: dict | None = None,
    *,
    scene: dict | None = None,
    binding_plan: dict | None = None,
) -> dict:
    selected_manifest = manifest or fixture("reference-manifest.valid.json")
    return {
        "schema_version": 1,
        "reference_manifest": selected_manifest,
        "scene_ir": scene or fixture("scene-ir.valid.json"),
        "binding_plan": binding_plan or fixture("binding-plan.derived.valid.json"),
    }


def rename_scene_entity(scene: dict, old: str, new: str) -> dict:
    renamed = copy.deepcopy(scene)
    for entity in renamed["entities"]:
        if entity["entity_id"] == old:
            entity["entity_id"] = new
    for material in renamed["materials"]:
        if material["entity_id"] == old:
            material["entity_id"] = new
    for shot in renamed["shots"]:
        for event in shot["events"]:
            event["actor_ids"] = [new if item == old else item for item in event["actor_ids"]]
            event["target_ids"] = [new if item == old else item for item in event["target_ids"]]
    for audio in renamed["audio_events"]:
        audio["source_entity_ids"] = [
            new if item == old else item for item in audio["source_entity_ids"]
        ]
    for invariant in renamed["requested_invariants"]:
        invariant["entity_ids"] = [
            new if item == old else item for item in invariant["entity_ids"]
        ]
    return renamed


class ReferencePlannerTests(unittest.TestCase):
    def assert_planning_error(self, request: dict, code: str, **kwargs: object) -> None:
        with self.assertRaises(bindings.BindingError) as caught:
            planner.plan_request(
                request,
                preview_candidate=True,
                today=FRESH_DATE,
                **kwargs,
            )
        self.assertEqual(caught.exception.code, code)

    def test_basic_material_multimodal_and_quiet_non_material_requests_are_ready(self) -> None:
        basic = request_for()
        multimodal_manifest = fixture("reference-manifest.multimodal.valid.json")
        multimodal = request_for(
            multimodal_manifest,
            scene=rename_scene_entity(
                fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
            ),
            binding_plan=fal_binding_plan(multimodal_manifest["assets"]),
        )

        basic_report = planner.plan_request(
            basic, preview_candidate=True, today=FRESH_DATE
        )
        multimodal_report = planner.plan_request(
            multimodal, preview_candidate=True, today=FRESH_DATE
        )

        self.assertEqual(basic_report["status"], "ready")
        self.assertEqual(basic_report["profile_status"], "candidate")
        self.assertTrue(basic_report["preview"])
        self.assertEqual(basic_report["selected_asset_ids"], ["product"])
        self.assertEqual(
            multimodal_report["selected_asset_ids"],
            ["hero_image", "motion_video", "voice_audio"],
        )
        self.assertEqual(multimodal_report["ablation_order"], ["voice_audio", "motion_video"])
        self.assertEqual(
            multimodal_report["authority_matrix"],
            [
                {"target_id": "hero", "dimension": "identity", "winner_asset_id": "hero_image"},
                {
                    "target_id": "hero",
                    "dimension": "subject_motion",
                    "winner_asset_id": "motion_video",
                },
                {"target_id": "hero", "dimension": "audio_voice", "winner_asset_id": "voice_audio"},
            ],
        )

    def test_one_asset_may_win_multiple_dimensions_without_role_collapse(self) -> None:
        manifest = fixture("reference-manifest.valid.json")
        target = manifest["targets"][0]
        target["required_dimensions"].append("visual_style")
        target["not_applicable_dimensions"].remove("visual_style")
        manifest["authority_assignments"].append(
            {
                "target_id": "bottle",
                "dimension": "visual_style",
                "winner_asset_id": "product",
                "excluded_asset_ids": [],
                "priority": "supporting",
                "confidence": "high",
                "excluded_transfer_dimensions": ["environment"],
                "leakage_risks": ["environment"],
                "resolved_leakage": ["environment"],
                "acceptance_criteria": ["The approved visual treatment remains stable."],
            }
        )
        report = planner.plan_request(
            request_for(manifest), preview_candidate=True, today=FRESH_DATE
        )
        self.assertEqual(
            report["authority_matrix"],
            [
                {
                    "target_id": "bottle",
                    "dimension": "product_object_geometry",
                    "winner_asset_id": "product",
                },
                {
                    "target_id": "bottle",
                    "dimension": "visual_style",
                    "winner_asset_id": "product",
                },
            ],
        )

    def test_non_structured_media_type_never_infers_authority(self) -> None:
        source = fixture("reference-manifest.multimodal.valid.json")
        video = copy.deepcopy(source["assets"][1])
        video["asset_id"] = "identity_video"
        video["use"] = "identity_reference"
        video["selection_status"] = "required"
        video["observed_leakage_dimensions"] = [
            "environment",
            "visual_style",
            "subject_motion",
            "camera_motion",
            "timing_rhythm",
        ]
        manifest = {
            "$schema": planner.REFERENCE_MANIFEST_SCHEMA_URI,
            "schema_version": 1,
            "profile_id": "fal.reference-to-video",
            "operation": "reference_generation",
            "task_intent": "Use an inspected video as explicit identity authority without importing its motion.",
            "targets": [
                {
                    "target_id": "performer",
                    "target_kind": "character",
                    "required_dimensions": ["identity"],
                    "not_applicable_dimensions": [
                        dimension for dimension in planner.DIMENSIONS if dimension != "identity"
                    ],
                }
            ],
            "assets": [video],
            "authority_assignments": [
                {
                    "target_id": "performer",
                    "dimension": "identity",
                    "winner_asset_id": "identity_video",
                    "excluded_asset_ids": [],
                    "priority": "required",
                    "confidence": "high",
                    "excluded_transfer_dimensions": [
                        "environment",
                        "visual_style",
                        "subject_motion",
                        "camera_motion",
                        "timing_rhythm",
                    ],
                    "leakage_risks": [
                        "environment",
                        "visual_style",
                        "subject_motion",
                        "camera_motion",
                        "timing_rhythm",
                    ],
                    "resolved_leakage": [
                        "environment",
                        "visual_style",
                        "subject_motion",
                        "camera_motion",
                        "timing_rhythm",
                    ],
                    "acceptance_criteria": [
                        "Identity follows the inspected video while its motion remains excluded."
                    ],
                }
            ],
            "selection_order": ["identity_video"],
            "ablation_order": [],
        }
        video["subject_selector"] = "performer"
        report = planner.plan_request(
            request_for(
                manifest,
                scene=fixture("scene-ir.nonmaterial.valid.json"),
                binding_plan=fal_binding_plan(manifest["assets"]),
            ),
            preview_candidate=True,
            today=FRESH_DATE,
        )
        self.assertEqual(
            report["authority_matrix"],
            [
                {
                    "target_id": "performer",
                    "dimension": "identity",
                    "winner_asset_id": "identity_video",
                }
            ],
        )

    def test_reference_entity_targets_must_exist_in_the_causal_scene(self) -> None:
        manifest = fixture("reference-manifest.valid.json")
        manifest["targets"][0]["target_id"] = "missing_product"
        manifest["assets"][0]["subject_selector"] = "missing_product"
        manifest["authority_assignments"][0]["target_id"] = "missing_product"
        self.assert_planning_error(
            request_for(manifest),
            "REF009_TARGET_NOT_IN_SCENE",
        )

        wrong_kind = fixture("reference-manifest.valid.json")
        wrong_kind["targets"][0]["target_kind"] = "object"
        self.assert_planning_error(
            request_for(wrong_kind),
            "REF009_TARGET_KIND_MISMATCH",
        )

        multimodal = fixture("reference-manifest.multimodal.valid.json")
        no_voice_source = rename_scene_entity(
            fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
        )
        no_voice_source["audio_events"][0]["source_entity_ids"] = []
        self.assert_planning_error(
            request_for(
                multimodal,
                scene=no_voice_source,
                binding_plan=fal_binding_plan(multimodal["assets"]),
            ),
            "REF009_AUDIO_TARGET_NOT_IN_SCENE",
        )

        missing_text = fixture("reference-manifest.valid.json")
        missing_text["targets"][0]["target_id"] = "missing_title"
        missing_text["targets"][0]["target_kind"] = "text_logo"
        missing_text["assets"][0]["subject_selector"] = "missing_title"
        missing_text["authority_assignments"][0]["target_id"] = "missing_title"
        self.assert_planning_error(
            request_for(missing_text),
            "REF009_TEXT_TARGET_NOT_IN_SCENE",
        )

    def test_structured_first_last_frame_roles_are_not_prompt_tokens(self) -> None:
        manifest = fixture("reference-manifest.structured.valid.json")
        binding_plan = fixture("binding-plan.structured.valid.json")
        report = planner.plan_request(
            request_for(manifest, binding_plan=binding_plan),
            preview_candidate=True,
            today=FRESH_DATE,
        )
        self.assertEqual(report["operation"], "first_last_frame")
        self.assertEqual(report["selected_asset_ids"], ["opening", "endpoint"])
        self.assertEqual(
            report["authority_matrix"],
            [
                {
                    "target_id": "bottle_tip",
                    "dimension": "opening_composition",
                    "winner_asset_id": "opening",
                },
                {
                    "target_id": "bottle_tip",
                    "dimension": "endpoint",
                    "winner_asset_id": "endpoint",
                },
            ],
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("structured_role", serialized)
        self.assertNotIn("rendered_prompt", report)

        swapped_roles = copy.deepcopy(binding_plan)
        swapped_roles["bindings"][0]["structured_role"] = "last_frame"
        swapped_roles["bindings"][1]["structured_role"] = "first_frame"
        self.assert_planning_error(
            request_for(manifest, binding_plan=swapped_roles),
            "REF003_STRUCTURED_ROLE_USE_MISMATCH",
        )

        swapped_authority = copy.deepcopy(manifest)
        swapped_authority["authority_assignments"][0]["winner_asset_id"] = "endpoint"
        swapped_authority["authority_assignments"][0]["excluded_asset_ids"] = ["opening"]
        swapped_authority["authority_assignments"][1]["winner_asset_id"] = "opening"
        swapped_authority["authority_assignments"][1]["excluded_asset_ids"] = ["endpoint"]
        self.assert_planning_error(
            request_for(swapped_authority, binding_plan=binding_plan),
            "REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH",
        )

        phantom_shot = copy.deepcopy(manifest)
        phantom_shot["targets"][0]["target_id"] = "phantom_shot"
        for asset in phantom_shot["assets"]:
            asset["subject_selector"] = "phantom_shot"
        for assignment in phantom_shot["authority_assignments"]:
            assignment["target_id"] = "phantom_shot"
        self.assert_planning_error(
            request_for(phantom_shot, binding_plan=binding_plan),
            "REF009_SHOT_TARGET_NOT_IN_SCENE",
        )

        product_target = copy.deepcopy(manifest)
        product_target["targets"][0]["target_id"] = "bottle"
        product_target["targets"][0]["target_kind"] = "product"
        for asset in product_target["assets"]:
            asset["subject_selector"] = "bottle"
        for assignment in product_target["authority_assignments"]:
            assignment["target_id"] = "bottle"
        self.assert_planning_error(
            request_for(product_target, binding_plan=binding_plan),
            "REF003_STRUCTURED_ROLE_AUTHORITY_MISMATCH",
        )

        generic_frame_role = fixture("reference-manifest.valid.json")
        generic_frame_role["assets"][0]["use"] = "opening_frame"
        generic_frame_role["assets"][0]["preflight"]["composition_use"] = "opening_frame"
        self.assert_planning_error(
            request_for(generic_frame_role),
            "REF003_STRUCTURED_ROLE_USE_MISMATCH",
        )

    def test_authority_conflicts_and_incomplete_dimension_partitions_fail(self) -> None:
        conflict = fixture("reference-manifest.valid.json")
        conflict["authority_assignments"].append(copy.deepcopy(conflict["authority_assignments"][0]))
        self.assert_planning_error(request_for(conflict), "REF002_MULTIPLE_WINNERS")

        incomplete = fixture("reference-manifest.valid.json")
        incomplete["targets"][0]["not_applicable_dimensions"].remove("identity")
        self.assert_planning_error(request_for(incomplete), "REF009_DIMENSION_PARTITION_INCOMPLETE")

        unknown_winner = fixture("reference-manifest.valid.json")
        unknown_winner["authority_assignments"][0]["winner_asset_id"] = "invented"
        self.assert_planning_error(request_for(unknown_winner), "REF009_WINNER_UNKNOWN")

    def test_leakage_must_be_typed_resolved_and_excluded_from_the_other_winner(self) -> None:
        unresolved = fixture("reference-manifest.multimodal.valid.json")
        unresolved["authority_assignments"][1]["resolved_leakage"].remove("identity")
        self.assert_planning_error(
            request_for(unresolved, binding_plan=fal_binding_plan(unresolved["assets"])),
            "REF005_UNRESOLVED_LEAKAGE",
        )

        donor_not_excluded = fixture("reference-manifest.multimodal.valid.json")
        donor_not_excluded["authority_assignments"][0]["excluded_asset_ids"].remove("motion_video")
        self.assert_planning_error(
            request_for(
                donor_not_excluded,
                binding_plan=fal_binding_plan(donor_not_excluded["assets"]),
            ),
            "REF005_LEAKAGE_ASSET_NOT_EXCLUDED",
        )

        self_excluding = fixture("reference-manifest.valid.json")
        self_excluding["authority_assignments"][0]["excluded_transfer_dimensions"].append(
            "product_object_geometry"
        )
        self.assert_planning_error(
            request_for(self_excluding),
            "REF005_WINNER_DIMENSION_EXCLUDED",
        )

    def test_purposeless_assets_selection_and_ablation_order_fail_closed(self) -> None:
        purposeless = fixture("reference-manifest.valid.json")
        spare = copy.deepcopy(purposeless["assets"][0])
        spare["asset_id"] = "spare"
        spare["selection_status"] = "supporting"
        purposeless["assets"].append(spare)
        purposeless["selection_order"].append("spare")
        purposeless["ablation_order"] = ["spare"]
        self.assert_planning_error(
            request_for(purposeless, binding_plan=fal_binding_plan(purposeless["assets"])),
            "REF006_PURPOSELESS_ASSET",
        )

        wrong_ablation = fixture("reference-manifest.multimodal.valid.json")
        wrong_ablation["ablation_order"] = ["motion_video", "voice_audio"]
        self.assert_planning_error(
            request_for(wrong_ablation, binding_plan=fal_binding_plan(wrong_ablation["assets"])),
            "REF006_ABLATION_ORDER_INVALID",
        )

    def test_rights_are_dimension_specific_and_never_inferred_from_media_use(self) -> None:
        media_unknown = fixture("reference-manifest.valid.json")
        media_unknown["assets"][0]["rights"]["media_use"] = "unknown"
        self.assert_planning_error(request_for(media_unknown), "REF010_MEDIA_USE_NOT_AUTHORIZED")

        likeness_unknown = fixture("reference-manifest.multimodal.valid.json")
        likeness_unknown["assets"][0]["rights"]["likeness"] = "unknown"
        self.assert_planning_error(
            request_for(
                likeness_unknown,
                binding_plan=fal_binding_plan(likeness_unknown["assets"]),
            ),
            "REF010_LIKENESS_NOT_AUTHORIZED",
        )

        voice_unknown = fixture("reference-manifest.multimodal.valid.json")
        voice_unknown["assets"][2]["rights"]["voice_performance"] = "unknown"
        self.assert_planning_error(
            request_for(voice_unknown, binding_plan=fal_binding_plan(voice_unknown["assets"])),
            "REF010_VOICE_NOT_AUTHORIZED",
        )

        voice_not_applicable = fixture("reference-manifest.multimodal.valid.json")
        voice_not_applicable["assets"][2]["rights"]["voice_performance"] = "not_applicable"
        self.assert_planning_error(
            request_for(
                voice_not_applicable,
                binding_plan=fal_binding_plan(voice_not_applicable["assets"]),
            ),
            "REF010_VOICE_NOT_AUTHORIZED",
        )

        music_not_applicable = fixture("reference-manifest.multimodal.valid.json")
        music_not_applicable["assets"][2]["preflight"]["has_voice"] = False
        music_not_applicable["assets"][2]["preflight"]["has_music"] = True
        music_not_applicable["assets"][2]["preflight"]["speaker_count"] = 0
        music_not_applicable["assets"][2]["subject_locator"] = {
            "method": "whole_asset",
            "description": "The complete music-only clip is the selected source.",
        }
        music_not_applicable["assets"][2]["rights"]["voice_performance"] = "not_applicable"
        music_not_applicable["assets"][2]["rights"]["music"] = "not_applicable"
        self.assert_planning_error(
            request_for(
                music_not_applicable,
                binding_plan=fal_binding_plan(music_not_applicable["assets"]),
            ),
            "REF010_MUSIC_NOT_AUTHORIZED",
        )

        timing_only = fixture("reference-manifest.multimodal.valid.json")
        target = timing_only["targets"][0]
        target["required_dimensions"].remove("audio_voice")
        target["required_dimensions"].append("timing_rhythm")
        target["not_applicable_dimensions"].remove("timing_rhythm")
        target["not_applicable_dimensions"].append("audio_voice")
        audio_asset = timing_only["assets"][2]
        audio_asset["observed_leakage_dimensions"] = ["audio_voice"]
        audio_asset["rights"]["voice_performance"] = "unknown"
        audio_assignment = timing_only["authority_assignments"][2]
        audio_assignment["dimension"] = "timing_rhythm"
        audio_assignment["excluded_transfer_dimensions"] = ["audio_voice"]
        audio_assignment["leakage_risks"] = ["audio_voice"]
        audio_assignment["resolved_leakage"] = ["audio_voice"]
        timing_report = planner.plan_request(
            request_for(
                timing_only,
                scene=rename_scene_entity(
                    fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
                ),
                binding_plan=fal_binding_plan(timing_only["assets"]),
            ),
            preview_candidate=True,
            today=FRESH_DATE,
        )
        self.assertEqual(timing_report["status"], "ready")

        embedded_voice_excluded = copy.deepcopy(timing_only)
        video_asset = embedded_voice_excluded["assets"][1]
        video_asset["preflight"]["embedded_audio"] = True
        video_asset["preflight"]["has_voice"] = True
        video_asset["rights"]["voice_performance"] = "unknown"
        video_asset["observed_leakage_dimensions"].append("audio_voice")
        motion_assignment = embedded_voice_excluded["authority_assignments"][1]
        motion_assignment["excluded_transfer_dimensions"].append("audio_voice")
        motion_assignment["leakage_risks"].append("audio_voice")
        motion_assignment["resolved_leakage"].append("audio_voice")
        embedded_report = planner.plan_request(
            request_for(
                embedded_voice_excluded,
                scene=rename_scene_entity(
                    fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
                ),
                binding_plan=fal_binding_plan(embedded_voice_excluded["assets"]),
            ),
            preview_candidate=True,
            today=FRESH_DATE,
        )
        self.assertEqual(embedded_report["status"], "ready")

        logo_excluded = fixture("reference-manifest.valid.json")
        logo_asset = logo_excluded["assets"][0]
        logo_asset["preflight"]["has_logo"] = True
        logo_asset["rights"]["brand_logo"] = "unknown"
        logo_asset["observed_leakage_dimensions"].append("text_logo_treatment")
        logo_assignment = logo_excluded["authority_assignments"][0]
        logo_assignment["excluded_transfer_dimensions"].append("text_logo_treatment")
        logo_assignment["leakage_risks"].append("text_logo_treatment")
        logo_assignment["resolved_leakage"].append("text_logo_treatment")
        self.assertEqual(
            planner.plan_request(
                request_for(logo_excluded),
                preview_candidate=True,
                today=FRESH_DATE,
            )["status"],
            "ready",
        )

    def test_multi_subject_assets_require_an_explicit_internal_locator(self) -> None:
        image = fixture("reference-manifest.valid.json")
        image["assets"][0]["preflight"]["subject_count"] = 3
        self.assert_planning_error(
            request_for(image),
            "REF007_SUBJECT_LOCATOR_AMBIGUOUS",
        )
        image["assets"][0]["subject_locator"] = {
            "method": "position",
            "description": "Select the bottle in the foreground center.",
        }
        self.assertIs(planner.validate_reference_manifest(image), image)

        audio = fixture("reference-manifest.multimodal.valid.json")
        audio["assets"][2]["preflight"]["speaker_count"] = 2
        self.assert_planning_error(
            request_for(audio, binding_plan=fal_binding_plan(audio["assets"])),
            "REF007_SUBJECT_LOCATOR_AMBIGUOUS",
        )
        audio["assets"][2]["subject_locator"] = {
            "method": "speaker_label",
            "description": "Select the speaker labeled hero in the recording notes.",
        }
        self.assertIs(planner.validate_reference_manifest(audio), audio)

    def test_binding_set_profile_and_media_mismatches_fail_closed(self) -> None:
        missing = fixture("binding-plan.derived.valid.json")
        missing["bindings"][0]["binding_id"] = "different"
        missing["segments"][0]["binding_id"] = "different"
        self.assert_planning_error(
            request_for(binding_plan=missing), "REF001_BINDING_SET_MISMATCH"
        )

        profile = fixture("binding-plan.derived.valid.json")
        profile["profile_id"] = "volcengine.ark"
        self.assert_planning_error(
            request_for(binding_plan=profile), "REF001_BINDING_PROFILE_MISMATCH"
        )

        media = fixture("binding-plan.derived.valid.json")
        media["bindings"][0]["media_type"] = "video"
        self.assert_planning_error(
            request_for(binding_plan=media), "REF008_BINDING_MEDIA_MISMATCH"
        )

    def test_preflight_rejects_collages_compound_camera_moves_and_uninspected_assets(self) -> None:
        collage = fixture("reference-manifest.valid.json")
        collage["assets"][0]["preflight"]["view_layout"] = "multiview_collage"
        collage["assets"][0]["subject_locator"] = {
            "method": "position",
            "description": "Select the bottle in the leftmost panel.",
        }
        self.assertIs(planner.validate_reference_manifest(collage), collage)

        source = fixture("reference-manifest.multimodal.valid.json")
        byteplus_collage = {
            **source,
            "profile_id": "byteplus.modelark",
            "targets": [
                {
                    "target_id": "hero",
                    "target_kind": "character",
                    "required_dimensions": ["identity"],
                    "not_applicable_dimensions": [
                        dimension for dimension in planner.DIMENSIONS if dimension != "identity"
                    ],
                }
            ],
            "assets": [copy.deepcopy(source["assets"][0])],
            "authority_assignments": [copy.deepcopy(source["authority_assignments"][0])],
            "selection_order": ["hero_image"],
            "ablation_order": [],
        }
        byteplus_collage["authority_assignments"][0]["excluded_asset_ids"] = []
        byteplus_collage["assets"][0]["preflight"]["view_layout"] = "multiview_collage"
        self.assert_planning_error(
            request_for(
                byteplus_collage,
                scene=rename_scene_entity(
                    fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
                ),
            ),
            "REF004_COLLAGE_RISK",
        )

        compound = fixture("reference-manifest.multimodal.valid.json")
        compound["assets"][1]["preflight"]["camera_motion"] = "compound"
        self.assertEqual(
            planner.plan_request(
                request_for(
                    compound,
                    scene=rename_scene_entity(
                        fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
                    ),
                    binding_plan=fal_binding_plan(compound["assets"]),
                ),
                preview_candidate=True,
                today=FRESH_DATE,
            )["status"],
            "ready",
        )

        camera_winner = copy.deepcopy(compound)
        camera_target = camera_winner["targets"][0]
        camera_target["required_dimensions"].remove("subject_motion")
        camera_target["required_dimensions"].append("camera_motion")
        camera_target["not_applicable_dimensions"].remove("camera_motion")
        camera_target["not_applicable_dimensions"].append("subject_motion")
        camera_asset = camera_winner["assets"][1]
        camera_asset["observed_leakage_dimensions"].remove("camera_motion")
        camera_asset["observed_leakage_dimensions"].append("subject_motion")
        camera_assignment = camera_winner["authority_assignments"][1]
        camera_assignment["dimension"] = "camera_motion"
        for field in (
            "excluded_transfer_dimensions",
            "leakage_risks",
            "resolved_leakage",
        ):
            camera_assignment[field].remove("camera_motion")
            camera_assignment[field].append("subject_motion")
        self.assert_planning_error(
            request_for(
                camera_winner,
                scene=rename_scene_entity(
                    fixture("scene-ir.nonmaterial.valid.json"), "performer", "hero"
                ),
                binding_plan=fal_binding_plan(camera_winner["assets"]),
            ),
            "CAM001_MULTIPLE_PRIMARY_MOVES",
        )

        uninspected = fixture("reference-manifest.valid.json")
        uninspected["assets"][0]["preflight_status"] = "uninspected"
        self.assert_planning_error(request_for(uninspected), "REF007_PREFLIGHT_INCOMPLETE")

        undeclared_logo = fixture("reference-manifest.valid.json")
        undeclared_logo["assets"][0]["preflight"]["has_logo"] = True
        self.assert_planning_error(
            request_for(undeclared_logo),
            "REF005_PREFLIGHT_RISK_UNDECLARED",
        )

        undeclared_embedded_voice = fixture("reference-manifest.multimodal.valid.json")
        donor = undeclared_embedded_voice["assets"][1]
        donor["preflight"]["embedded_audio"] = True
        donor["preflight"]["has_voice"] = True
        self.assert_planning_error(
            request_for(
                undeclared_embedded_voice,
                binding_plan=fal_binding_plan(undeclared_embedded_voice["assets"]),
            ),
            "REF005_PREFLIGHT_RISK_UNDECLARED",
        )

    def test_media_use_and_authority_compatibility_fail_closed(self) -> None:
        audio_geometry = fixture("reference-manifest.valid.json")
        audio_geometry["assets"][0] = copy.deepcopy(
            fixture("reference-manifest.multimodal.valid.json")["assets"][2]
        )
        audio_asset = audio_geometry["assets"][0]
        audio_asset["asset_id"] = "product"
        audio_asset["selection_status"] = "required"
        audio_asset["subject_selector"] = "bottle"
        audio_asset["subject_locator"] = {
            "method": "whole_asset",
            "description": "The complete sound-effect recording is selected.",
        }
        audio_asset["preflight"]["has_voice"] = False
        audio_asset["preflight"]["has_sound_effects"] = True
        audio_asset["preflight"]["speaker_count"] = 0
        audio_asset["rights"]["voice_performance"] = "not_applicable"
        audio_asset["observed_leakage_dimensions"] = []
        self.assert_planning_error(
            request_for(
                audio_geometry,
                binding_plan=fal_binding_plan(audio_geometry["assets"]),
            ),
            "REF008_MEDIA_DIMENSION_INCOMPATIBLE",
        )

        image_voice = fixture("reference-manifest.valid.json")
        target = image_voice["targets"][0]
        target["required_dimensions"] = ["audio_voice"]
        target["not_applicable_dimensions"] = [
            dimension for dimension in planner.DIMENSIONS if dimension != "audio_voice"
        ]
        image_voice["authority_assignments"][0]["dimension"] = "audio_voice"
        self.assert_planning_error(
            request_for(image_voice),
            "REF008_MEDIA_DIMENSION_INCOMPATIBLE",
        )

        image_audio_use = fixture("reference-manifest.valid.json")
        image_audio_use["assets"][0]["use"] = "audio_reference"
        self.assert_planning_error(
            request_for(image_audio_use),
            "REF008_USE_MEDIA_INCOMPATIBLE",
        )

        unrelated_use = fixture("reference-manifest.valid.json")
        unrelated_use["assets"][0]["use"] = "style_reference"
        self.assert_planning_error(
            request_for(unrelated_use),
            "REF008_USE_AUTHORITY_INCOMPATIBLE",
        )

    def test_candidate_preview_and_evidence_expiry_are_fail_closed(self) -> None:
        request = request_for()
        with self.assertRaises(bindings.BindingError) as no_preview:
            planner.plan_request(request, today=FRESH_DATE)
        self.assertEqual(no_preview.exception.code, "PROFILE_CANDIDATE_REQUIRES_PREVIEW")

        fresh = planner.plan_request(request, preview_candidate=True, today=FRESH_DATE)
        self.assertEqual(fresh["evidence_expires_at"], "2026-07-18")
        self.assertEqual(
            fresh["evidence_claim_ids"],
            [
                "bytedance.model.multimodal-inputs",
                "bytedance.model.reference-control",
                "global.binding.no-universal-token",
                "fal.binding.at-ordinal",
            ],
        )
        with self.assertRaises(bindings.BindingError) as expired:
            planner.plan_request(request, preview_candidate=True, today=EXPIRED_DATE)
        self.assertEqual(expired.exception.code, "PROFILE_EVIDENCE_EXPIRED")

    def test_report_hashes_and_output_are_canonical_across_ten_repeated_passes(self) -> None:
        request = request_for()
        reports = [
            planner.plan_request(request, preview_candidate=True, today=FRESH_DATE)
            for _ in range(10)
        ]
        encoded = [bindings.canonical_json(report) for report in reports]
        self.assertTrue(all(item == encoded[0] for item in encoded))
        report = reports[0]
        self.assertEqual(report, fixture("planning-report.valid.json"))
        self.assertEqual(
            report["reference_manifest_sha256"],
            bindings.sha256_bytes(bindings.canonical_json(request["reference_manifest"])),
        )
        self.assertEqual(
            report["scene_ir_sha256"],
            bindings.sha256_bytes(bindings.canonical_json(request["scene_ir"])),
        )
        self.assertEqual(
            report["binding_plan_sha256"],
            bindings.sha256_bytes(bindings.canonical_json(request["binding_plan"])),
        )

    def test_cli_is_stdin_stdout_only_deterministic_and_does_not_echo_secrets(self) -> None:
        raw = json.dumps(request_for(), ensure_ascii=False).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            outputs = []
            for _ in range(10):
                process = subprocess.run(
                    [sys.executable, str(SCRIPT), "--preview-candidate"],
                    input=raw,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    check=False,
                )
                self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8"))
                self.assertEqual(process.stderr, b"")
                outputs.append(process.stdout)
            self.assertTrue(all(output == outputs[0] for output in outputs))
            self.assertEqual(list(workdir.iterdir()), [])

            hostile = b'{"schema_version":1,"secret-sentinel":1,"secret-sentinel":2}'
            failed = subprocess.run(
                [sys.executable, str(SCRIPT), "--preview-candidate"],
                input=hostile,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                check=False,
            )
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(failed.stdout, b"")
            self.assertIn(b"JSON_DUPLICATE_KEY", failed.stderr)
            self.assertNotIn(b"secret-sentinel", failed.stderr)
            self.assertEqual(list(workdir.iterdir()), [])

    def test_planning_is_offline_and_report_never_serializes_source_text_or_handles(self) -> None:
        request = request_for()
        secret = "private-production-sentinel"
        request["reference_manifest"]["task_intent"] = secret
        request["binding_plan"]["segments"][1]["value"] = f" {secret}."
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
            report = planner.plan_request(
                request, preview_candidate=True, today=FRESH_DATE
            )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("rendered_prompt", report)
        self.assertNotIn("request_bindings", report)

        invalid = request_for()
        invalid["reference_manifest"]["task_intent"] = "@Image99 secret-sentinel"
        with self.assertRaises(bindings.BindingError) as caught:
            planner.plan_request(invalid, preview_candidate=True, today=FRESH_DATE)
        self.assertEqual(caught.exception.code, "REF001_LOCATOR_OR_HANDLE_FORBIDDEN")
        self.assertNotIn("secret-sentinel", str(caught.exception))

    def test_ten_thousand_seeded_safe_manifest_text_mutations_validate(self) -> None:
        rng = random.Random(706)
        alphabet = [*" abcdefghijklmnopqrstuvwxyz0123456789", "人", "物", "光", "é", "🚀"]
        manifest = fixture("reference-manifest.valid.json")
        for index in range(10_000):
            suffix = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 20))).strip() or "x"
            manifest["task_intent"] = f"Visible event {index}: {suffix}."
            manifest["authority_assignments"][0]["acceptance_criteria"][0] = (
                f"Observable result {index}: {suffix}."
            )
            self.assertIs(planner.validate_reference_manifest(manifest), manifest)


if __name__ == "__main__":
    unittest.main()
