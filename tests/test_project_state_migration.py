from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import project_state_migrate as migrate
from scripts import project_state_v2_check as state


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "validation" / "fixtures"
SOURCE = FIXTURES / "project-state-v1.migration-source.json"
MAPPING = FIXTURES / "project-state-v2-migration-map.valid.json"
GOLDEN = FIXTURES / "project-state-v2.migration-golden.json"
REPORT = FIXTURES / "project-state-v2-migration-report.valid.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-S", "-B", "scripts/project_state_migrate.py", *args],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )


class ProjectStateMigrationTests(unittest.TestCase):
    def source_and_raw_hash(self) -> tuple[dict, str]:
        raw = SOURCE.read_bytes()
        return migrate.source_contract(json.loads(raw)), migrate.raw_hash(raw)

    def rebind(self, source: dict, mapping: dict) -> str:
        raw = state.canonical_json(source)
        mapping["source_raw_sha256"] = migrate.raw_hash(raw)
        mapping["source_project_state_sha256"] = migrate.canonical_hash(source)
        return mapping["source_raw_sha256"]

    def refresh_inventory(self, source: dict, mapping: dict) -> None:
        occurrence_hashes = {item["pointer"]: item["value_sha256"] for item in migrate._legacy_field_occurrences(source)}
        for disposition in mapping["legacy_dispositions"]:
            if disposition["source_pointer"] in occurrence_hashes:
                disposition["source_value_sha256"] = occurrence_hashes[disposition["source_pointer"]]

    def rebuild_dispositions(self, source: dict, mapping: dict, target: dict) -> None:
        dispositions = []
        for occurrence in migrate._legacy_field_occurrences(source):
            targets = migrate._authorized_disposition_targets(source, occurrence["pointer"])
            if targets:
                target_pointer = sorted(targets)[0]
                dispositions.append({
                    "source_pointer": occurrence["pointer"], "source_value_sha256": occurrence["value_sha256"],
                    "disposition": "mapped", "reason": "Exact test mapping.", "target_pointer": target_pointer,
                    "target_value_sha256": migrate.legacy_value_hash(migrate.pointer_get(target, target_pointer)),
                })
            else:
                dispositions.append({
                    "source_pointer": occurrence["pointer"], "source_value_sha256": occurrence["value_sha256"],
                    "disposition": "retired_with_reason", "reason": "Exact test retirement.",
                    "target_pointer": None, "target_value_sha256": None,
                })
        mapping["legacy_dispositions"] = dispositions

    def test_self_test_is_dependency_free(self) -> None:
        result = run_cli("--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_inspect_is_redacted_and_matches_golden_report(self) -> None:
        result = run_cli("inspect", str(SOURCE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, REPORT.read_bytes())
        self.assertNotIn(b"@Image1", result.stdout)
        self.assertNotIn(b"watch identity", result.stdout)

    def test_migration_is_exact_deterministic_and_preserves_source_bytes(self) -> None:
        before = SOURCE.read_bytes()
        outputs = []
        for seed in range(10):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            result = subprocess.run(
                [sys.executable, "-S", "-B", "scripts/project_state_migrate.py", "migrate", str(SOURCE), "--map", str(MAPPING)],
                cwd=ROOT,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(len(set(outputs)), 1)
        self.assertEqual(outputs[0], GOLDEN.read_bytes())
        self.assertEqual(SOURCE.read_bytes(), before)
        migrated = json.loads(outputs[0])
        self.assertEqual(state.validate_project_state(migrated), migrated)
        clip = migrated["semantic_state"]["clips"][0]
        self.assertEqual(clip["status"], "planned")
        self.assertEqual(clip["planned_start_snapshot"]["motion_handoff"]["vectors"], [])
        self.assertEqual([item["motion_id"] for item in clip["planned_end_snapshot"]["motion_handoff"]["vectors"]], ["watch.still"])
        self.assertNotIn("@Image1", outputs[0].decode("utf-8"))

        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        status_disposition = next(item for item in mapping["legacy_dispositions"] if item["source_pointer"] == "/clips/0/status")
        self.assertEqual(mapping["clip_mappings"][0]["target_status"], "planned")
        self.assertEqual(status_disposition["disposition"], "mapped")
        self.assertEqual(status_disposition["source_value_sha256"], migrate.legacy_value_hash("ready"))
        self.assertEqual(status_disposition["target_pointer"], "/semantic_state/clips/0/status")
        self.assertEqual(status_disposition["target_value_sha256"], migrate.legacy_value_hash("planned"))

    def test_verify_recomputes_the_entire_migration(self) -> None:
        result = run_cli("verify", str(SOURCE), str(GOLDEN), "--map", str(MAPPING))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "verified")

    def test_wrong_source_hash_and_unmapped_leaf_fail_without_echoing_values(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["source_project_state_sha256"] = "0" * 64
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG004_MAPPING_SOURCE_HASH_MISMATCH")

        missing_status_audit = json.loads(MAPPING.read_text(encoding="utf-8"))
        missing_status_audit["legacy_dispositions"] = [item for item in missing_status_audit["legacy_dispositions"] if item["source_pointer"] != "/clips/0/status"]
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(missing_status_audit, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG025_LEGACY_DISPOSITION_REQUIRED")

        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["state_atom_mappings"].pop()
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG011_STATE_ATOM_UNMAPPED")

        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["source_raw_sha256"] = "0" * 64
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG004_MAPPING_SOURCE_HASH_MISMATCH")

    def test_motion_destination_provider_rewrite_and_disposition_target_fail_closed(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        wrong_destination = json.loads(MAPPING.read_text(encoding="utf-8"))
        wrong_destination["motion_mappings"][0]["destination_snapshot"] = "observed_end_state"
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(wrong_destination, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG012_MOTION_BASIS_UNRESOLVED")

        provider_rewrite = json.loads(MAPPING.read_text(encoding="utf-8"))
        provider_rewrite["state_atom_mappings"][0]["replacement_value"] = "keep @Image1 exactly"
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(provider_rewrite, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED")

        false_mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapped = next(item for item in false_mapping["legacy_dispositions"] if item["disposition"] == "mapped")
        mapped["target_value_sha256"] = "0" * 64
        checked = migrate.validate_map(false_mapping, source, source_raw_sha256)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.migrate(source, checked, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG026_DISPOSITION_TARGET_MISMATCH")

        arbitrary_target = json.loads(MAPPING.read_text(encoding="utf-8"))
        disposition = next(item for item in arbitrary_target["legacy_dispositions"] if item["source_pointer"] == "/surface")
        disposition.update(
            disposition="mapped",
            reason="False structural mapping.",
            target_pointer="/schema_version",
            target_value_sha256=migrate.legacy_value_hash(2),
        )
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(arbitrary_target, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG026_DISPOSITION_TARGET_MISMATCH")

        scalar_source = copy.deepcopy(source)
        scalar_source["clips"][0]["planned_start_state"]["visible"] = True
        scalar_map = json.loads(MAPPING.read_text(encoding="utf-8"))
        scalar_map["source_project_state_sha256"] = migrate.canonical_hash(scalar_source)
        self.refresh_inventory(scalar_source, scalar_map)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(scalar_map, migrate.source_contract(scalar_source), source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG011_STATE_ATOM_UNMAPPED")

    def test_empty_containers_and_nested_reference_tags_are_never_silently_dropped(self) -> None:
        source, _ = self.source_and_raw_hash()
        source["clips"][0]["planned_start_state"]["hidden_constraints"] = []
        source["clips"][0]["planned_end_state"]["nested"] = {"reference_tags": ["semantic_marker"]}
        raw = state.canonical_json(source)
        source_raw_sha256 = migrate.raw_hash(raw)
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["source_raw_sha256"] = source_raw_sha256
        mapping["source_project_state_sha256"] = migrate.canonical_hash(source)
        source = migrate.source_contract(source)
        report = migrate.inspect_source(source, source_raw_sha256)
        pointers = {item["pointer"] for item in report["state_leaf_occurrences"]}
        self.assertIn("/clips/0/planned_start_state/hidden_constraints", pointers)
        self.assertIn("/clips/0/planned_end_state/nested/reference_tags/0", pointers)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG011_STATE_ATOM_UNMAPPED")

    def test_accepted_legacy_status_is_explicitly_downgraded_without_media_fabrication(self) -> None:
        for source_status in ("accepted", "accepted_with_deviation"):
            with self.subTest(source_status=source_status):
                source, _ = self.source_and_raw_hash()
                source["clips"][0]["status"] = source_status
                mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
                mapping["clip_mappings"][0]["target_status"] = "reviewed"
                status_disposition = next(item for item in mapping["legacy_dispositions"] if item["source_pointer"] == "/clips/0/status")
                status_disposition["source_value_sha256"] = migrate.legacy_value_hash(source_status)
                status_disposition["target_value_sha256"] = migrate.legacy_value_hash("reviewed")
                self.refresh_inventory(source, mapping)
                source_raw_sha256 = self.rebind(source, mapping)
                checked_source = migrate.source_contract(source)
                output = migrate.migrate(checked_source, migrate.validate_map(mapping, checked_source, source_raw_sha256), source_raw_sha256)
                clip = output["semantic_state"]["clips"][0]
                self.assertEqual(clip["status"], "reviewed")
                for snapshot_name in ("observed_start_snapshot", "observed_end_snapshot"):
                    snapshot = clip[snapshot_name]
                    if snapshot is not None:
                        self.assertEqual(snapshot["source"]["kind"], "legacy_state_description")
                        self.assertIsNone(snapshot["source"]["take_id"])
                        self.assertIsNone(snapshot["source"]["media_sha256"])
                        self.assertTrue(snapshot["requires_confirmation"])

    def test_take_history_story_world_and_source_tag_are_exhaustively_audited(self) -> None:
        source, _ = self.source_and_raw_hash()
        source["take_history"] = [{"take_id": "legacy_take", "media_sha256": "a" * 64, "provider_note": "legacy only"}]
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["legacy_dispositions"] = [item for item in mapping["legacy_dispositions"] if item["source_pointer"] != "/take_history"]
        source_raw_sha256 = self.rebind(source, mapping)
        checked_source = migrate.source_contract(source)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, checked_source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG025_LEGACY_DISPOSITION_REQUIRED")

        for occurrence in migrate._terminal_occurrences(source["take_history"], "/take_history", 16384):
            mapping["legacy_dispositions"].append({
                "source_pointer": occurrence["pointer"], "source_value_sha256": occurrence["value_sha256"],
                "disposition": "retired_with_reason", "reason": "Explicitly retired pending typed take-evidence migration.",
                "target_pointer": None, "target_value_sha256": None,
            })
        output = migrate.migrate(checked_source, migrate.validate_map(mapping, checked_source, source_raw_sha256), source_raw_sha256)
        self.assertNotIn("take_history", output["semantic_state"])

        safe_unknown = copy.deepcopy(source)
        safe_unknown["take_history"] = []
        safe_unknown["world_bible"]["material_note"] = "matte black acrylic"
        unknown_map = json.loads(MAPPING.read_text(encoding="utf-8"))
        unknown_raw_sha256 = self.rebind(safe_unknown, unknown_map)
        checked_unknown = migrate.source_contract(safe_unknown)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(unknown_map, checked_unknown, unknown_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG004_MAPPING_SOURCE_HASH_MISMATCH")
        world_disposition = next(item for item in unknown_map["legacy_dispositions"] if item["source_pointer"] == "/world_bible")
        world_disposition["source_value_sha256"] = migrate.legacy_value_hash(safe_unknown["world_bible"])
        world_disposition["target_value_sha256"] = migrate.legacy_value_hash(safe_unknown["world_bible"])
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(unknown_map, checked_unknown, unknown_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG025_LEGACY_DISPOSITION_REQUIRED")
        unknown_map["legacy_dispositions"].append({
            "source_pointer": "/world_bible/material_note", "source_value_sha256": migrate.legacy_value_hash("matte black acrylic"),
            "disposition": "mapped", "reason": "Carried unchanged as provider-independent world state.",
            "target_pointer": "/semantic_state/world_bible/material_note", "target_value_sha256": migrate.legacy_value_hash("matte black acrylic"),
        })
        migrate.migrate(checked_unknown, migrate.validate_map(unknown_map, checked_unknown, unknown_raw_sha256), unknown_raw_sha256)

        hidden = copy.deepcopy(safe_unknown)
        hidden["world_bible"]["provider_id"] = "seedance-2.0"
        hidden_map = copy.deepcopy(unknown_map)
        hidden_raw_sha256 = self.rebind(hidden, hidden_map)
        world_disposition = next(item for item in hidden_map["legacy_dispositions"] if item["source_pointer"] == "/world_bible")
        world_disposition["source_value_sha256"] = migrate.legacy_value_hash(hidden["world_bible"])
        world_disposition["target_value_sha256"] = migrate.legacy_value_hash(hidden["world_bible"])
        hidden_map["legacy_dispositions"].append({
            "source_pointer": "/world_bible/provider_id", "source_value_sha256": migrate.legacy_value_hash("seedance-2.0"),
            "disposition": "mapped", "reason": "Adversarial hidden claim.",
            "target_pointer": "/semantic_state/world_bible/provider_id", "target_value_sha256": migrate.legacy_value_hash("seedance-2.0"),
        })
        checked_hidden = migrate.source_contract(hidden)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.migrate(checked_hidden, migrate.validate_map(hidden_map, checked_hidden, hidden_raw_sha256), hidden_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG020_V2_STATE_INVALID")

        missing_tag, _ = self.source_and_raw_hash()
        missing_tag["clips"][0].pop("source_clip_tag")
        missing_map = json.loads(MAPPING.read_text(encoding="utf-8"))
        tag_disposition = next(item for item in missing_map["legacy_dispositions"] if item["source_pointer"] == "/clips/0/source_clip_tag")
        null_hash = tag_disposition["source_value_sha256"]
        tag_disposition["source_value_sha256"] = migrate.legacy_value_hash(migrate.MISSING_VALUE)
        self.assertNotEqual(tag_disposition["source_value_sha256"], null_hash)
        self.refresh_inventory(missing_tag, missing_map)
        missing_raw_sha256 = self.rebind(missing_tag, missing_map)
        checked_missing = migrate.source_contract(missing_tag)
        migrate.migrate(checked_missing, migrate.validate_map(missing_map, checked_missing, missing_raw_sha256), missing_raw_sha256)

    def test_inspect_fails_before_oversized_state_occurrence_report(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        source["clips"][0]["planned_start_state"]["many"] = list(range(4095))
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.inspect_source(migrate.source_contract(source), source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG024_RESOURCE_LIMIT")

    def test_toolchain_hash_binds_validator_and_provider_rewrites_are_normalized(self) -> None:
        migrate_only = hashlib.sha256((ROOT / "scripts" / "project_state_migrate.py").read_bytes()).hexdigest()
        self.assertNotEqual(migrate.TOOL_SHA256, migrate_only)
        self.assertEqual(migrate.TOOL_SHA256, migrate._toolchain_sha256())
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate._reject_provider_values({"value": "watchref"}, ["WATCHREF"])
        self.assertEqual(caught.exception.code, "MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED")

        source, source_raw_sha256 = self.source_and_raw_hash()
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["clip_mappings"][0]["execution_readiness"] = "compile_required"
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG018_COMPILER_PROVENANCE_INCOMPLETE")

    def test_v1_contract_and_mapping_schema_parity_fail_before_provenance(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        source_mutations = [
            lambda value: value.update(surface="not-an-object"),
            lambda value: value.update(state_revision=True),
            lambda value: value.update(project_mode="invalid"),
            lambda value: value.update(project_mode=[]),
            lambda value: value.update(clip_budget_sec=0),
            lambda value: value.update(prompt_budget=True),
            lambda value: value["story"].update(extra="closed"),
            lambda value: value["reference_registry"][0].update(tag=""),
            lambda value: value["scenes"][0].update(scene_index=0),
            lambda value: value["scenes"][0].update(arc_position="invalid"),
            lambda value: value["scenes"][0].update(arc_position={}),
            lambda value: value["beats"][0].update(status="invalid"),
            lambda value: value["clips"][0].update(planned_start_state=None),
            lambda value: value["clips"][0].update(continuity_locks=["same", "same"]),
            lambda value: value.update(updated_at="2026-02-31"),
            lambda value: value.update(updated_at="20260713"),
        ]
        for index, mutation in enumerate(source_mutations):
            with self.subTest(source_mutation=index):
                candidate = copy.deepcopy(source)
                mutation(candidate)
                with self.assertRaises(migrate.MigrationError) as caught:
                    migrate.source_contract(candidate)
                self.assertEqual(caught.exception.code, "MIG002_SOURCE_CONTRACT_INVALID")

        map_mutations = [
            lambda value: value.update(schema_version=True),
            lambda value: value["timing_policy"].update(mode=[]),
            lambda value: value["reference_mappings"][0].update(source_kind={}),
            lambda value: value["state_atom_mappings"][0].update(owner_kind=[]),
            lambda value: value["clip_mappings"][0].update(target_status={}),
            lambda value: value["clip_mappings"][0]["planned_endpoint_states"][0].update(completion_mode=[]),
            lambda value: value["legacy_dispositions"][0].update(disposition={}),
            lambda value: value["legacy_dispositions"][0].update(reason="x" * 2001),
            lambda value: value["reference_mappings"][0].update(description="x" * 2001),
            lambda value: value["state_atom_mappings"][0].update(replacement_value="x" * 20001),
            lambda value: value["motion_mappings"][0].update(coordinate_frame="invalid"),
            lambda value: value["clip_mappings"][0].update(extra="closed"),
            lambda value: value["reanchor_policy"].update(extra="closed"),
            lambda value: value["timing_policy"].update(block_reason="unexpected"),
        ]
        for index, mutation in enumerate(map_mutations):
            with self.subTest(map_mutation=index):
                candidate = json.loads(MAPPING.read_text(encoding="utf-8"))
                mutation(candidate)
                with self.assertRaises(migrate.MigrationError) as caught:
                    migrate.validate_map(candidate, source, source_raw_sha256)
                self.assertIn(caught.exception.code, {"MIG003_MAPPING_CONTRACT_INVALID", "MIG007_EMBEDDED_REFERENCE_REWRITE_REQUIRED", "MIG012_MOTION_BASIS_UNRESOLVED", "MIG018_COMPILER_PROVENANCE_INCOMPLETE"})

    def test_unsafe_v1_ids_have_explicit_hash_bound_rewrite_path(self) -> None:
        source, _ = self.source_and_raw_hash()
        source["project_id"] = "Project A"
        source["scenes"][0]["scene_id"] = "Scene A"
        source["scenes"][0]["assigned_clip_ids"] = ["Clip A"]
        source["beats"][0]["beat_id"] = "Beat A"
        source["beats"][0]["assigned_clip_id"] = "Clip A"
        source["clips"][0]["clip_id"] = "Clip A"
        source["clips"][0]["scene_id"] = "Scene A"
        source["clips"][0]["this_clip_only"] = ["Beat A"]
        source["current_clip_id"] = "Clip A"
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        targets = {
            "/project_id": ("project", "project_a"),
            "/scenes/0/scene_id": ("scene", "scene_a"),
            "/beats/0/beat_id": ("beat", "beat_a"),
            "/clips/0/clip_id": ("clip", "clip_a"),
        }
        for record in mapping["id_mappings"]:
            kind, target_id = targets[record["source_pointer"]]
            source_id = migrate.pointer_get(source, record["source_pointer"])
            record.update(entity_kind=kind, source_value_sha256=migrate.legacy_value_hash(source_id), target_id=target_id)
        mapping["motion_mappings"][0]["clip_id"] = "Clip A"
        mapping["clip_mappings"][0]["clip_id"] = "Clip A"
        target = json.loads(GOLDEN.read_text(encoding="utf-8"))
        target["project_id"] = "project_a"
        scene = target["semantic_state"]["scenes"][0]
        scene.update(scene_id="scene_a", assigned_clip_ids=["clip_a"])
        beat = target["semantic_state"]["beats"][0]
        beat.update(beat_id="beat_a", assigned_clip_id="clip_a")
        clip = target["semantic_state"]["clips"][0]
        clip.update(clip_id="clip_a", scene_id="scene_a", this_clip_only=["beat_a"])
        target["semantic_state"]["current_clip_id"] = "clip_a"
        self.rebuild_dispositions(source, mapping, target)
        source_raw_sha256 = self.rebind(source, mapping)
        checked_source = migrate.source_contract(source)
        output = migrate.migrate(checked_source, migrate.validate_map(mapping, checked_source, source_raw_sha256), source_raw_sha256)
        self.assertEqual(output["project_id"], "project_a")
        self.assertEqual(output["semantic_state"]["current_clip_id"], "clip_a")
        self.assertEqual(output["semantic_state"]["scenes"][0]["scene_id"], "scene_a")
        self.assertEqual(output["semantic_state"]["beats"][0]["beat_id"], "beat_a")
        report = migrate.inspect_source(checked_source, source_raw_sha256)
        self.assertTrue(any(item["pointer"] == "/project_id" for item in report["id_occurrences"]))
        self.assertNotIn("Project A", json.dumps(report))

        missing_id = copy.deepcopy(mapping)
        missing_id["id_mappings"].pop()
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(missing_id, checked_source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG027_ID_MAPPING_REQUIRED")

    def test_prompt_budget_and_all_direct_fields_require_exact_disposition(self) -> None:
        source, _ = self.source_and_raw_hash()
        source["prompt_budget"] = 777
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        source_raw_sha256 = self.rebind(source, mapping)
        checked_source = migrate.source_contract(source)
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, checked_source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG004_MAPPING_SOURCE_HASH_MISMATCH")
        disposition = next(item for item in mapping["legacy_dispositions"] if item["source_pointer"] == "/prompt_budget")
        disposition["source_value_sha256"] = migrate.legacy_value_hash(777)
        disposition["target_value_sha256"] = migrate.legacy_value_hash(777)
        output = migrate.migrate(checked_source, migrate.validate_map(mapping, checked_source, source_raw_sha256), source_raw_sha256)
        self.assertEqual(output["semantic_state"]["prompt_budget"], 777)

    def test_reference_provenance_and_authority_remain_fail_closed(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        reference = mapping["reference_mappings"][0]
        reference["source_kind"] = "accepted_take"
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.migrate(source, migrate.validate_map(mapping, source, source_raw_sha256), source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG003_MAPPING_CONTRACT_INVALID")

        migrated = migrate.migrate(source, migrate.validate_map(json.loads(MAPPING.read_text(encoding="utf-8")), source, source_raw_sha256), source_raw_sha256)
        asset = migrated["semantic_state"]["reference_assets"][0]
        self.assertEqual(asset["status"], "pending")
        self.assertEqual(asset["authority_status"], "unresolved")
        self.assertNotIn("binding_policy", asset)

    def test_reference_collision_and_source_clip_guessing_fail_closed(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["reference_mappings"].append(copy.deepcopy(mapping["reference_mappings"][0]))
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, source, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG006_REFERENCE_AMBIGUOUS")

        source["clips"][0]["source_clip_tag"] = "../../secret"
        mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
        mapping["source_project_state_sha256"] = migrate.canonical_hash(source)
        next(item for item in mapping["legacy_dispositions"] if item["source_pointer"] == "/clips/0/source_clip_tag")["source_value_sha256"] = migrate.legacy_value_hash("../../secret")
        self.refresh_inventory(source, mapping)
        # The raw-byte binding is authoritative; construct the matching hash only for this direct negative.
        synthetic_raw_sha256 = mapping["source_raw_sha256"]
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.validate_map(mapping, migrate.source_contract(source), synthetic_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG010_SOURCE_CLIP_UNMAPPED")

    def test_duplicate_keys_and_symlink_inputs_fail(self) -> None:
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.parse(b'{"a":1,"a":2}', migrate.MAX_SOURCE_BYTES)
        self.assertEqual(caught.exception.code, "JSON_DUPLICATE_KEY")

        with tempfile.TemporaryDirectory() as temporary:
            link = Path(temporary) / "source.json"
            try:
                link.symlink_to(SOURCE)
            except OSError:
                self.skipTest("symlinks unavailable")
            result = run_cli("inspect", str(link))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"MIG023_FILE_UNSAFE", result.stderr)

        malformed = json.loads(SOURCE.read_text(encoding="utf-8"))
        malformed["clips"][0].pop("scene_id")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "malformed.json"
            path.write_text(json.dumps(malformed), encoding="utf-8")
            result = run_cli("inspect", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"MIG002_SOURCE_CONTRACT_INVALID", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertNotIn(b"watch identity", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            crlf = Path(temporary) / "source-crlf.json"
            crlf.write_bytes(SOURCE.read_bytes().replace(b"\n", b"\r\n"))
            result = run_cli("migrate", str(crlf), "--map", str(MAPPING))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"MIG004_MAPPING_SOURCE_HASH_MISMATCH", result.stderr)
            self.assertEqual(result.stdout, b"")

    def test_tampered_golden_fails_verify(self) -> None:
        source, source_raw_sha256 = self.source_and_raw_hash()
        mapping = migrate.validate_map(json.loads(MAPPING.read_text(encoding="utf-8")), source, source_raw_sha256)
        candidate = json.loads(GOLDEN.read_text(encoding="utf-8"))
        candidate["semantic_state"]["story"]["tone"] = "tampered"
        with self.assertRaises(migrate.MigrationError) as caught:
            migrate.verify(source, mapping, candidate, source_raw_sha256)
        self.assertEqual(caught.exception.code, "MIG020_V2_STATE_INVALID")


if __name__ == "__main__":
    unittest.main()
