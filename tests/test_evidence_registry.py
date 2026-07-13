from __future__ import annotations

import ast
import copy
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tools import evidence_registry as registry


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 7, 11)
EVIDENCE = Path("research/evidence")


def json_data(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_repository_fixture(destination: Path) -> None:
    shutil.copytree(ROOT / "schemas", destination / "schemas")
    shutil.copytree(ROOT / "research" / "evidence", destination / "research" / "evidence")
    manifest_source = ROOT / "runtime" / "seedance-20.manifest.json"
    manifest_target = destination / "runtime" / "seedance-20.manifest.json"
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_source, manifest_target)
    manifest = json_data(manifest_source)
    for relative in manifest["files"]:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in ["evals/evals.json", "tests/test_evidence_registry.py"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def literal_workflow_run_blocks(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        if line.lstrip() != "run: |":
            continue
        marker_indent = len(line) - len(line.lstrip())
        block: list[str] = []
        for candidate in lines[index + 1 :]:
            if candidate.strip():
                candidate_indent = len(candidate) - len(candidate.lstrip())
                if candidate_indent <= marker_indent:
                    break
                block.append(candidate[marker_indent + 2 :])
            else:
                block.append("")
        blocks.append("\n".join(block) + "\n")
    return blocks


class EvidenceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template_temp = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_temp.name) / "template"
        copy_repository_fixture(cls.template)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.template_temp.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(self.template, self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def evaluate(self, *, as_of: date = AS_OF, enforce: bool = False):
        return registry.evaluate(
            registry.layout_for_root(self.root),
            as_of=as_of,
            enforce_freshness=enforce,
        )

    def mutate(self, relative: str, callback) -> dict:
        path = self.root / relative
        value = json_data(path)
        callback(value)
        write_json(path, value)
        return value

    def repin_claim(self, claim_id: str) -> None:
        claim_path = self.root / EVIDENCE / "claims" / f"{claim_id.replace('.', '-')}.json"
        digest = hashlib.sha256(claim_path.read_bytes()).hexdigest()
        policy_path = self.root / EVIDENCE / "release-policy.json"
        policy = json_data(policy_path)
        requirement = next(
            item for item in policy["requirements"] if item["selected_claim_id"] == claim_id
        )
        requirement["selected_claim_sha256"] = digest
        write_json(policy_path, policy)

    def all_messages(self, report: dict, errors: list[str], warnings: list[str]) -> str:
        return "\n".join([*errors, *warnings, *report.get("release_blockers", [])])

    def test_canonical_registry_is_structurally_valid_but_release_closed(self) -> None:
        report, errors, warnings = registry.evaluate(as_of=AS_OF, enforce_freshness=True)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(report["claim_count"], 17)
        self.assertEqual(report["source_snapshot_count"], 6)
        self.assertEqual(report["capture_count"], 6)
        self.assertEqual(report["verified_capture_source_count"], 6)
        self.assertEqual(report["runtime_coverage_counts"], {
            "legacy_blocked": 93,
            "mapped_candidate": 4,
            "no_volatile_claims": 38,
        })
        self.assertEqual(report["review_counts"], {"pending": 17})
        self.assertFalse(report["release_gate_pass"])
        self.assertIn("runtime.coverage:legacy-blocked-files=93", report["release_blockers"])

    def test_closed_release_cli_fails_without_changing_structural_result(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "evidence_registry.py"),
                "--as-of", "2026-07-11",
                "--release",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Evidence release gate blocked", result.stdout)
        self.assertIn("critical-review-not-approved", result.stdout)

    def test_runtime_map_exactly_covers_the_runtime_manifest(self) -> None:
        runtime_map = json_data(ROOT / EVIDENCE / "runtime-map.json")
        manifest_path = ROOT / "runtime" / "seedance-20.manifest.json"
        manifest = json_data(manifest_path)
        self.assertEqual(runtime_map["runtime_manifest_sha256"], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        self.assertEqual([item["path"] for item in runtime_map["files"]], manifest["files"])
        for item in runtime_map["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest())

    def test_candidate_profile_occurrences_are_complete_but_not_activated(self) -> None:
        runtime_map = json_data(ROOT / EVIDENCE / "runtime-map.json")
        candidates = {
            item["path"]: item
            for item in runtime_map["files"]
            if item["audit_status"] == "mapped_candidate"
        }
        self.assertEqual(set(candidates), set(registry.V705_CANDIDATE_PROFILE_PATHS))
        self.assertEqual(sum(len(item["occurrences"]) for item in candidates.values()), 9)
        for path, item in candidates.items():
            expected_profile = registry.V705_CANDIDATE_PROFILE_PATHS[path]
            self.assertTrue(item["occurrences"])
            for occurrence in item["occurrences"]:
                self.assertEqual(occurrence["disposition"], "supported_candidate")
                self.assertEqual(occurrence["profile_ids"], [expected_profile])

    def test_candidate_profile_cannot_be_relabeled_activation_ready(self) -> None:
        def activate(value: dict) -> None:
            entry = next(
                item for item in value["files"]
                if item["path"] == "profiles/surfaces/byteplus-modelark.json"
            )
            entry["audit_status"] = "mapped"

        self.mutate("research/evidence/runtime-map.json", activate)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("mapped occurrence is not activation-ready", messages)
        self.assertFalse(report["release_gate_pass"])

    def test_candidate_profile_requires_occurrences_and_exact_profile_scope(self) -> None:
        path = "research/evidence/runtime-map.json"

        def remove_occurrences(value: dict) -> None:
            entry = next(
                item for item in value["files"]
                if item["path"] == "profiles/surfaces/fal-reference-to-video.json"
            )
            entry["occurrences"] = []

        self.mutate(path, remove_occurrences)
        report, errors, warnings = self.evaluate()
        self.assertIn("mapped file must contain occurrences", self.all_messages(report, errors, warnings))

    def test_contra_dataset_is_research_only_not_model_or_prompt_proof(self) -> None:
        claim = json_data(ROOT / EVIDENCE / "claims" / "contra-annotation-observable-dimensions.json")
        self.assertEqual(claim["claim_class"], "annotation_ontology")
        self.assertEqual(claim["runtime_status"], "research_only")
        self.assertEqual(claim["runtime_presence"], "not_present")
        self.assertNotIn("seedance-2.0-model", claim["affected_profiles"])
        self.assertEqual(claim["value"], [
            "brand_text", "camera_adherence", "material_realism",
            "multishot_continuity", "product_consistency",
        ])

    def test_seedance_25_and_later_records_are_forced_unverified_and_blocked(self) -> None:
        self.assertFalse(any(
            json_data(path)["model_version"] == "2.5"
            for path in (ROOT / EVIDENCE / "claims").glob("*.json")
        ))
        path = "research/evidence/claims/bp-camera-one-move.json"
        for version in ["2.5", "2.6", "2.10", "3.0", "v2.5-preview", "2.5-series"]:
            with self.subTest(version=version):
                self.mutate(path, lambda value: value.__setitem__("model_version", version))
                report, errors, warnings = self.evaluate()
                generation = registry.parse_model_generation(version)
                self.assertIsNotNone(generation)
                assert generation is not None
                self.assertIn(
                    f"Seedance {generation[0]}.{generation[1]} must remain unverified and blocked",
                    self.all_messages(report, errors, warnings),
                )

    def test_provider_reference_tokens_are_explicitly_surface_scoped(self) -> None:
        claims = {
            json_data(path)["claim_id"]: json_data(path)
            for path in (ROOT / EVIDENCE / "claims").glob("*.json")
        }
        self.assertEqual(claims["bp.binding.spaced-example-token"]["value"], "@Image 1")
        self.assertEqual(claims["fal.binding.at-ordinal"]["value"], "@Image1")
        self.assertEqual(claims["volc.binding.asset-ordinal"]["value"], "图片1")
        universal = claims["global.binding.no-universal-token"]
        self.assertFalse(universal["value"])
        self.assertEqual(set(universal["scope"]["surfaces"]), {
            "byteplus.modelark", "fal.reference-to-video", "volcengine.ark",
        })
        for claim_id in ["fal.binding.at-ordinal", "fal.input.seed-absent", "fal.resolution.standard-4k"]:
            self.assertEqual(claims[claim_id]["scope"]["surfaces"], ["fal.reference-to-video"])
            self.assertEqual(claims[claim_id]["runtime_status"], "candidate")
        self.assertFalse(claims["fal.input.seed-absent"]["value"])
        self.assertEqual(claims["fal.resolution.standard-4k"]["value"], "4k")

    def test_byteplus_claims_remain_surface_scoped(self) -> None:
        claims = [
            json_data(path)
            for path in (ROOT / EVIDENCE / "claims").glob("bp-*.json")
        ]
        self.assertEqual(len(claims), 7)
        for claim in claims:
            self.assertEqual(claim["scope"]["surfaces"], ["byteplus.modelark"])
            self.assertEqual(claim["runtime_status"], "candidate")
            self.assertNotEqual(claim["claim_class"], "model_capability")
        by_id = {claim["claim_id"]: claim for claim in claims}
        self.assertEqual(by_id["bp.assets.purposeful-set"]["value"], "start_small_add_incrementally")
        self.assertEqual(by_id["bp.binding.spaced-example-token"]["value"], "@Image 1")
        self.assertEqual(by_id["bp.camera.one-move"]["value"], 1)
        self.assertEqual(by_id["bp.camera.one-move"]["scope"]["operations"], ["reference_generation"])
        self.assertEqual(by_id["bp.character.headshot-fullbody"]["value"], [
            "clean_headshot", "separate_full_body", "avoid_multiview_collage",
        ])
        self.assertEqual(by_id["bp.operation.edit-extend-classifier"]["value"], "avoid_generic_reference_prefix")
        self.assertEqual(by_id["bp.subject.stable-label"]["value"], "repeat_same_unambiguous_label")
        self.assertEqual(by_id["bp.timing.exact-caution"]["value"], "prefer_ordered_phases")
        self.assertEqual(by_id["bp.assets.purposeful-set"]["runtime_presence"], "future_profile")
        self.assertEqual(by_id["bp.character.headshot-fullbody"]["runtime_presence"], "future_profile")

    def test_bytedance_claims_remain_model_level(self) -> None:
        for name in ["bytedance-model-multimodal-inputs.json", "bytedance-model-reference-control.json"]:
            claim = json_data(ROOT / EVIDENCE / "claims" / name)
            self.assertEqual(claim["claim_class"], "model_capability")
            self.assertEqual(claim["scope"]["surfaces"], ["model"])
            self.assertEqual(claim["runtime_status"], "candidate")
        modalities = json_data(ROOT / EVIDENCE / "claims" / "bytedance-model-multimodal-inputs.json")
        controls = json_data(ROOT / EVIDENCE / "claims" / "bytedance-model-reference-control.json")
        self.assertEqual(modalities["value"], ["audio", "image", "text", "video"])
        self.assertEqual(controls["value"], ["camera_movement", "lighting", "performance", "shadow"])
        authorities = {
            item["authority_id"]: item
            for item in json_data(ROOT / EVIDENCE / "authorities.json")["authorities"]
        }
        self.assertEqual(authorities["bytedance.seed"]["source_types"], ["first_party_model_doc"])
        self.assertEqual(authorities["bytedance.seed"]["hosts"], ["seed.bytedance.com"])

    def test_volcengine_claims_remain_surface_scoped(self) -> None:
        claims = {
            json_data(path)["claim_id"]: json_data(path)
            for path in (ROOT / EVIDENCE / "claims").glob("volc-*.json")
        }
        self.assertEqual(set(claims), {
            "volc.binding.asset-ordinal",
            "volc.binding.first-last-frame-role",
            "volc.timing.exact-example",
        })
        for claim in claims.values():
            self.assertEqual(claim["scope"]["surfaces"], ["volcengine.ark"])
            self.assertEqual(claim["runtime_status"], "candidate")
        self.assertEqual(claims["volc.binding.asset-ordinal"]["value"], "图片1")
        frame_role = claims["volc.binding.first-last-frame-role"]
        self.assertEqual(frame_role["value"], ["first_frame", "last_frame"])
        self.assertIn("designate supplied images as endpoint frames", frame_role["claim_text"])
        self.assertIn("not guaranteed", frame_role["notes"])
        self.assertEqual(claims["volc.timing.exact-example"]["value"], "official_example_uses_ranges")

    def test_every_supported_source_reference_resolves_to_a_retained_item(self) -> None:
        captures = {}
        for path in (ROOT / EVIDENCE / "captures").glob("*.json"):
            capture = json_data(path)
            captures[capture["source_snapshot_id"]] = {
                item["evidence_item_id"] for item in capture["items"]
            }
        for path in (ROOT / EVIDENCE / "claims").glob("*.json"):
            claim = json_data(path)
            for evidence in claim["source_evidence"]:
                if evidence["relation"] != "supports":
                    continue
                item_ids = {item["evidence_item_id"] for item in evidence["evidence_items"]}
                self.assertTrue(item_ids)
                self.assertTrue(item_ids.issubset(captures[evidence["source_snapshot_id"]]))

    def test_capture_file_hash_mutation_fails_closed(self) -> None:
        capture = self.root / EVIDENCE / "captures" / "fal-reference-to-video-2026-07-11.json"
        capture.write_bytes(capture.read_bytes() + b" \n")
        report, errors, warnings = self.evaluate()
        self.assertIn("capture SHA-256 mismatch", self.all_messages(report, errors, warnings))

    def test_normalized_evidence_item_hash_mutation_fails_closed(self) -> None:
        path = "research/evidence/captures/byteplus-prompt-guide-2222480-2026-07-11.json"
        self.mutate(path, lambda value: value["items"][0].__setitem__("normalized_evidence", value["items"][0]["normalized_evidence"] + " changed"))
        report, errors, warnings = self.evaluate()
        self.assertIn("normalized evidence hash mismatch", self.all_messages(report, errors, warnings))

    def test_unknown_evidence_item_fails_closed(self) -> None:
        path = "research/evidence/claims/fal-binding-at-ordinal.json"
        self.mutate(
            path,
            lambda value: value["source_evidence"][0]["evidence_items"].append({
                "evidence_item_id": "fal.missing.item",
                "normalized_evidence_sha256": "0" * 64,
            }),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("unknown evidence item", self.all_messages(report, errors, warnings))

    def test_affected_test_anchor_must_resolve_exactly_once(self) -> None:
        self.mutate(
            "research/evidence/claims/fal-binding-at-ordinal.json",
            lambda value: value["affected_tests"].__setitem__(
                0, "evals/evals.json#fictional_green_test"
            ),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("resolves 0 times", self.all_messages(report, errors, warnings))

    def test_claim_pin_detects_coordinated_source_and_capture_rewrite(self) -> None:
        capture_path = self.root / EVIDENCE / "captures" / "fal-reference-to-video-2026-07-11.json"
        capture = json_data(capture_path)
        capture["items"][0]["normalized_evidence"] += " rewritten"
        capture["items"][0]["normalized_evidence_sha256"] = registry.sha256_text(
            capture["items"][0]["normalized_evidence"]
        )
        write_json(capture_path, capture)
        source_path = self.root / EVIDENCE / "sources" / "fal-reference-to-video-2026-07-11.json"
        source = json_data(source_path)
        source["capture_sha256"] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
        write_json(source_path, source)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("source snapshot byte pin mismatch", messages)
        self.assertIn("capture byte pin mismatch", messages)
        self.assertIn("evidence item byte pin mismatch", messages)

    def test_duplicate_and_orphan_captures_fail_closed(self) -> None:
        original = self.root / EVIDENCE / "captures" / "fal-reference-to-video-2026-07-11.json"
        duplicate = self.root / EVIDENCE / "captures" / "orphan-duplicate.json"
        shutil.copy2(original, duplicate)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("duplicate capture_id", messages)
        self.assertIn("orphan retained capture", messages)

    def test_unapproved_authority_host_fails_closed(self) -> None:
        path = "research/evidence/sources/fal-reference-to-video-2026-07-11.json"
        self.mutate(path, lambda value: value.__setitem__("canonical_url", "https://attacker.example/fake"))
        report, errors, warnings = self.evaluate()
        self.assertIn("unapproved host", self.all_messages(report, errors, warnings))

    def test_closed_authority_allowlist_cannot_be_coordinately_rewritten(self) -> None:
        self.mutate(
            "research/evidence/authorities.json",
            lambda value: value["authorities"][0]["hosts"].append("attacker.example"),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("closed authority record byte pin mismatch", self.all_messages(report, errors, warnings))

    def test_non_https_source_url_fails_closed(self) -> None:
        path = "research/evidence/sources/fal-reference-to-video-2026-07-11.json"
        self.mutate(path, lambda value: value.__setitem__("final_url", "http://fal.ai/fake"))
        report, errors, warnings = self.evaluate()
        self.assertIn("URL must use HTTPS", self.all_messages(report, errors, warnings))

    def test_future_source_and_document_dates_fail_closed(self) -> None:
        path = "research/evidence/sources/byteplus-prompt-guide-2222480-2026-07-11.json"
        self.mutate(path, lambda value: value.__setitem__("document_updated_at", "2026-07-12"))
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("document update date is after retrieval", messages)
        self.assertIn("document update date is in the future", messages)

    def test_duplicate_json_key_is_rejected(self) -> None:
        path = self.root / EVIDENCE / "claims" / "bp-assets-purposeful-set.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("{", '{\n  "claim_id": "duplicate.id",', 1), encoding="utf-8")
        report, errors, warnings = self.evaluate()
        self.assertIn("duplicate JSON object key", self.all_messages(report, errors, warnings))

    def test_nan_and_infinite_exponents_are_rejected(self) -> None:
        for token in ["NaN", "1e9999"]:
            with self.subTest(token=token):
                path = self.root / EVIDENCE / "release-policy.json"
                raw = path.read_text(encoding="utf-8")
                path.write_text(raw.replace('"schema_version": 1', f'"schema_version": {token}', 1), encoding="utf-8")
                report, errors, warnings = self.evaluate()
                self.assertIn("non-finite JSON number", self.all_messages(report, errors, warnings))
                shutil.copy2(self.template / EVIDENCE / "release-policy.json", path)

    def test_utf8_bom_is_rejected(self) -> None:
        path = self.root / EVIDENCE / "runtime-map.json"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        report, errors, warnings = self.evaluate()
        self.assertIn("UTF-8 BOM is forbidden", self.all_messages(report, errors, warnings))

    def test_unpaired_surrogate_and_noncanonical_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(registry.EvidenceError, "unpaired Unicode surrogate"):
            registry.parse_json(b'{"value":"\\ud800"}', "surrogate")
        for value in ["a//b.json", "a/./b.json", "a/\u202eb.json"]:
            with self.subTest(value=value), self.assertRaises(registry.EvidenceError):
                registry.normalize_relative(value, "path")

    def test_excessive_json_depth_is_rejected_without_crashing(self) -> None:
        path = self.root / EVIDENCE / "release-policy.json"
        path.write_text("[" * 60 + "0" + "]" * 60, encoding="utf-8")
        report, errors, warnings = self.evaluate()
        self.assertIn("JSON nesting exceeds", self.all_messages(report, errors, warnings))

    def test_symlinked_record_is_rejected(self) -> None:
        target = self.root / "outside-source.json"
        record = self.root / EVIDENCE / "sources" / "fal-reference-to-video-2026-07-11.json"
        shutil.copy2(record, target)
        record.unlink()
        record.symlink_to(target)
        report, errors, warnings = self.evaluate()
        self.assertIn("regular non-link JSON files", self.all_messages(report, errors, warnings))

    def test_symlinked_record_directory_is_rejected(self) -> None:
        claims = self.root / EVIDENCE / "claims"
        real_claims = self.root / EVIDENCE / "claims-real"
        claims.rename(real_claims)
        claims.symlink_to(real_claims, target_is_directory=True)
        report, errors, warnings = self.evaluate()
        self.assertIn("missing or linked directory", self.all_messages(report, errors, warnings))

    def test_symlinked_singleton_record_is_rejected(self) -> None:
        policy = self.root / EVIDENCE / "release-policy.json"
        real_policy = self.root / EVIDENCE / "release-policy-real.json"
        policy.rename(real_policy)
        policy.symlink_to(real_policy)
        report, errors, warnings = self.evaluate()
        self.assertIn("not a regular file", self.all_messages(report, errors, warnings))

    def test_ancestor_swap_cannot_redirect_descriptor_walk(self) -> None:
        safe_parent = self.root / "walk" / "a"
        safe_parent.mkdir(parents=True)
        (safe_parent / "file.txt").write_text("inside\n", encoding="utf-8")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        moved = outside / "moved"
        real_open = registry.os.open
        swapped = False

        def swap_before_leaf(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "file.txt" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                safe_parent.rename(moved)
                safe_parent.mkdir()
                (safe_parent / "file.txt").write_text("attacker\n", encoding="utf-8")
            return real_open(path, flags, *args, **kwargs)

        try:
            with mock.patch.object(registry.os, "open", side_effect=swap_before_leaf):
                _path, raw = registry.read_regular_file(self.root, "walk/a/file.txt", "swap-test")
        except registry.EvidenceError as exc:
            self.assertIn("ancestor changed while reading", str(exc))
        else:
            self.assertEqual(raw, b"inside\n")
            self.assertNotEqual(raw, (safe_parent / "file.txt").read_bytes())

    def test_hardlinked_capture_is_rejected(self) -> None:
        capture = self.root / EVIDENCE / "captures" / "fal-reference-to-video-2026-07-11.json"
        os.link(capture, self.root / "capture-hardlink-backup")
        report, errors, warnings = self.evaluate()
        self.assertIn("hard-linked files are forbidden", self.all_messages(report, errors, warnings))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_special_file_in_record_directory_is_rejected_without_reading(self) -> None:
        os.mkfifo(self.root / EVIDENCE / "claims" / "blocked-fifo.json")
        report, errors, warnings = self.evaluate()
        self.assertIn("regular non-link JSON files", self.all_messages(report, errors, warnings))

    def test_capture_path_traversal_is_rejected(self) -> None:
        path = "research/evidence/sources/fal-reference-to-video-2026-07-11.json"
        self.mutate(path, lambda value: value.__setitem__("capture_path", "research/evidence/captures/../authorities.json"))
        report, errors, warnings = self.evaluate()
        self.assertIn("unsafe relative path", self.all_messages(report, errors, warnings))

    def test_expiry_uses_exclusive_utc_semantics(self) -> None:
        report, errors, warnings = self.evaluate(as_of=date(2026, 7, 17), enforce=True)
        self.assertFalse(any("evidence expired" in item for item in errors))
        report, errors, warnings = self.evaluate(as_of=date(2026, 7, 18), enforce=True)
        self.assertTrue(any("fal.binding.at-ordinal: evidence expired" in item for item in errors))
        self.assertTrue(any("volc.binding.asset-ordinal: evidence expired" in item for item in errors))

    def test_ttl_date_mismatch_fails_closed(self) -> None:
        path = "research/evidence/claims/bp-assets-purposeful-set.json"
        self.mutate(path, lambda value: value.__setitem__("expires_at", "2026-08-09"))
        report, errors, warnings = self.evaluate()
        self.assertIn("expires_at must equal verified_at + ttl_days", self.all_messages(report, errors, warnings))

    def test_stable_claim_cannot_renew_without_a_new_source_snapshot(self) -> None:
        claim_id = "bytedance.model.multimodal-inputs"
        self.mutate(
            "research/evidence/claims/bytedance-model-multimodal-inputs.json",
            lambda value: (
                value.__setitem__("verified_at", "2026-07-12"),
                value.__setitem__("expires_at", "2027-01-08"),
            ),
        )
        self.repin_claim(claim_id)
        report, errors, warnings = self.evaluate(as_of=date(2026, 7, 12))
        self.assertIn("verification date must equal the newest supporting source snapshot", self.all_messages(report, errors, warnings))

    def test_claim_class_and_ttl_baselines_cannot_be_coordinately_relaxed(self) -> None:
        claim_id = "fal.input.seed-absent"
        self.mutate(
            "research/evidence/claims/fal-input-seed-absent.json",
            lambda value: (
                value.__setitem__("claim_class", "workflow"),
                value.__setitem__("ttl_days", 60),
                value.__setitem__("expires_at", "2026-09-09"),
            ),
        )
        self.repin_claim(claim_id)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("claim class baseline changed", messages)
        self.assertIn("TTL baseline changed", messages)

    def test_scope_confidence_and_value_baselines_cannot_be_rewritten(self) -> None:
        claim_id = "fal.resolution.standard-4k"
        self.mutate(
            "research/evidence/claims/fal-resolution-standard-4k.json",
            lambda value: (
                value["scope"].__setitem__("operations", ["*"]),
                value["scope"].__setitem__("locale", "multilingual"),
                value.__setitem__("confidence", "low"),
                value.__setitem__("value", "8k"),
            ),
        )
        self.repin_claim(claim_id)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("operation scope baseline changed", messages)
        self.assertIn("locale/region baseline changed", messages)
        self.assertIn("confidence floor changed", messages)
        self.assertIn("claim value baseline changed", messages)

    def test_claim_source_closure_cannot_be_swapped_between_providers(self) -> None:
        replacement = json_data(
            self.root / EVIDENCE / "claims" / "volc-binding-asset-ordinal.json"
        )["source_evidence"]
        self.mutate(
            "research/evidence/claims/bp-binding-spaced-example-token.json",
            lambda value: value.__setitem__("source_evidence", copy.deepcopy(replacement)),
        )
        self.repin_claim("bp.binding.spaced-example-token")
        report, errors, warnings = self.evaluate()
        self.assertIn("source closure baseline changed", self.all_messages(report, errors, warnings))

    def test_policy_detects_any_selected_claim_byte_mutation(self) -> None:
        path = self.root / EVIDENCE / "claims" / "bp-assets-purposeful-set.json"
        path.write_bytes(path.read_bytes() + b" \n")
        report, errors, warnings = self.evaluate()
        self.assertIn("selected-claim-byte-pin-mismatch", self.all_messages(report, errors, warnings))

    def test_claim_and_policy_requirement_cannot_be_deleted_together(self) -> None:
        claim_id = "contra.annotation.observable-dimensions"
        (self.root / EVIDENCE / "claims" / "contra-annotation-observable-dimensions.json").unlink()
        self.mutate(
            "research/evidence/release-policy.json",
            lambda value: value.__setitem__(
                "requirements",
                [item for item in value["requirements"] if item["selected_claim_id"] != claim_id],
            ),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("required lineage roots are missing", self.all_messages(report, errors, warnings))

    def test_policy_detects_criticality_downgrade_even_after_repin(self) -> None:
        claim_id = "fal.input.seed-absent"
        self.mutate(
            "research/evidence/claims/fal-input-seed-absent.json",
            lambda value: value.__setitem__("criticality", "important"),
        )
        self.repin_claim(claim_id)
        report, errors, warnings = self.evaluate()
        self.assertIn("criticality-downgraded", self.all_messages(report, errors, warnings))

    def test_policy_baseline_cannot_be_downgraded_with_the_claim(self) -> None:
        claim_id = "fal.input.seed-absent"
        self.mutate(
            "research/evidence/claims/fal-input-seed-absent.json",
            lambda value: value.__setitem__("criticality", "informational"),
        )
        self.repin_claim(claim_id)
        self.mutate(
            "research/evidence/release-policy.json",
            lambda value: next(
                item for item in value["requirements"] if item["selected_claim_id"] == claim_id
            ).__setitem__("criticality", "informational"),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("criticality floor changed", self.all_messages(report, errors, warnings))

    def test_missing_selected_claim_blocks_release(self) -> None:
        (self.root / EVIDENCE / "claims" / "fal-input-seed-absent.json").unlink()
        report, errors, warnings = self.evaluate()
        self.assertIn("selected-claim-missing", self.all_messages(report, errors, warnings))

    def test_runtime_file_byte_mutation_invalidates_coverage(self) -> None:
        path = self.root / "SKILL.md"
        path.write_bytes(path.read_bytes() + b"\n")
        report, errors, warnings = self.evaluate()
        self.assertIn("runtime-map/SKILL.md: file SHA-256 mismatch", self.all_messages(report, errors, warnings))

    def test_runtime_map_cannot_omit_a_manifest_file(self) -> None:
        self.mutate(
            "research/evidence/runtime-map.json",
            lambda value: value["files"].pop(),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("file set must exactly equal", self.all_messages(report, errors, warnings))

    def test_runtime_debt_cannot_be_bulk_relabeled_clean(self) -> None:
        def erase_debt(value: dict) -> None:
            for entry in value["files"]:
                if entry["audit_status"] == "legacy_blocked":
                    entry["audit_status"] = "no_volatile_claims"

        self.mutate("research/evidence/runtime-map.json", erase_debt)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("V7-05 audit status must remain legacy_blocked", messages)
        self.assertFalse(report["release_gate_pass"])

    def test_runtime_manifest_byte_mutation_invalidates_map_pin(self) -> None:
        self.mutate(
            "runtime/seedance-20.manifest.json",
            lambda value: value.__setitem__("locked_payload_size_bytes", value["locked_payload_size_bytes"] + 1),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("runtime manifest SHA-256 mismatch", self.all_messages(report, errors, warnings))

    def test_qualification_relation_must_remain_reciprocal(self) -> None:
        self.mutate(
            "research/evidence/claims/volc-timing-exact-example.json",
            lambda value: value.__setitem__("relations", []),
        )
        report, errors, warnings = self.evaluate()
        self.assertIn("requires reciprocal tension_with", self.all_messages(report, errors, warnings))

    def test_qualified_tension_cannot_be_coordinately_erased(self) -> None:
        for claim_id, filename in [
            ("bp.timing.exact-caution", "bp-timing-exact-caution.json"),
            ("volc.timing.exact-example", "volc-timing-exact-example.json"),
        ]:
            self.mutate(
                f"research/evidence/claims/{filename}",
                lambda value: (
                    value.__setitem__("agreement_status", "uncontested"),
                    value.__setitem__("relations", []),
                ),
            )
            self.repin_claim(claim_id)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("agreement baseline changed", messages)
        self.assertIn("relation baseline changed", messages)

    def test_overlapping_incompatible_values_require_declared_conflict(self) -> None:
        source_path = self.root / EVIDENCE / "claims" / "bp-camera-one-move.json"
        claim = json_data(source_path)
        claim["claim_id"] = "bp.camera.conflict-test"
        claim["value"] = 2
        write_json(self.root / EVIDENCE / "claims" / "bp-camera-conflict-test.json", claim)
        report, errors, warnings = self.evaluate()
        self.assertIn("undeclared value conflict", self.all_messages(report, errors, warnings))

    def test_review_approval_must_bind_exact_payload_and_two_reviewers(self) -> None:
        def corrupt_review(value: dict) -> None:
            value["review"] = {
                "status": "approved",
                "reviewers": ["one-reviewer"],
                "decision_at": "2026-07-11",
                "claim_sha256": "0" * 64,
            }

        self.mutate("research/evidence/claims/fal-input-seed-absent.json", corrupt_review)
        report, errors, warnings = self.evaluate()
        self.assertIn("approved review must name two reviewers and bind the exact claim payload", self.all_messages(report, errors, warnings))

    def test_reviewers_are_casefold_distinct_and_decision_cannot_be_future(self) -> None:
        def ambiguous_review(value: dict) -> None:
            payload = copy.deepcopy(value)
            payload.pop("review")
            value["review"] = {
                "status": "approved",
                "reviewers": ["Alice", "alice"],
                "decision_at": "2026-07-12",
                "claim_sha256": hashlib.sha256(registry.canonical_json(payload)).hexdigest(),
            }

        self.mutate("research/evidence/claims/fal-input-seed-absent.json", ambiguous_review)
        report, errors, warnings = self.evaluate()
        messages = self.all_messages(report, errors, warnings)
        self.assertIn("reviewers must be distinct after NFC/case folding", messages)
        self.assertIn("review decision date is in the future", messages)

    def test_activation_remains_blocked_even_with_declared_reviewer_labels(self) -> None:
        report, errors, warnings = self.evaluate()
        self.assertIn("policy.activation:disabled", report["release_blockers"])
        self.assertFalse(report["release_gate_pass"])

    def test_supersession_cycle_is_rejected(self) -> None:
        first = "research/evidence/claims/bp-timing-exact-caution.json"
        second = "research/evidence/claims/volc-timing-exact-example.json"
        self.mutate(first, lambda value: (value.__setitem__("lifecycle_status", "superseded"), value.__setitem__("supersedes", ["volc.timing.exact-example"])))
        self.mutate(second, lambda value: (value.__setitem__("lifecycle_status", "superseded"), value.__setitem__("supersedes", ["bp.timing.exact-caution"])))
        report, errors, warnings = self.evaluate()
        self.assertIn("supersedes cycle", self.all_messages(report, errors, warnings))

    def test_proposal_is_deterministic_bounded_and_non_activating(self) -> None:
        first, errors, _ = registry.evaluate(as_of=AS_OF)
        self.assertEqual(errors, [])
        payload_one = registry.proposal_payload(first, 7)
        second, errors, _ = registry.evaluate(as_of=AS_OF)
        self.assertEqual(errors, [])
        payload_two = registry.proposal_payload(second, 7)
        self.assertEqual(registry.canonical_json(payload_one), registry.canonical_json(payload_two))
        self.assertIsNotNone(payload_one)
        assert payload_one is not None
        self.assertFalse(payload_one["activation_enabled"])
        rendered = registry.render_proposal_markdown(payload_one)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("normalized_evidence", rendered)
        self.assertIn("did not fetch the web", rendered)

    def test_proposal_is_absent_without_due_claims_or_registry_errors(self) -> None:
        report = {"freshness": [], "release_blockers": ["runtime.coverage:blocked"], "errors": []}
        self.assertIsNone(registry.proposal_payload(report, 7))

    def test_explicit_as_of_report_bytes_are_reproducible(self) -> None:
        one = Path(self.temp.name) / "one.json"
        two = Path(self.temp.name) / "two.json"
        command = [
            sys.executable,
            str(ROOT / "tools" / "evidence_registry.py"),
            "--as-of", "2026-07-11",
        ]
        for output in [one, two]:
            result = subprocess.run(command + ["--report", str(output)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_checker_has_no_network_client_or_fetch_call(self) -> None:
        source = (ROOT / "tools" / "evidence_registry.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"requests", "httpx", "socket", "urllib.request", "aiohttp"}
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        self.assertTrue(imports.isdisjoint(forbidden))
        self.assertNotIn("urlopen(", source)

    def test_remote_schema_reference_is_rejected_without_a_request(self) -> None:
        requested = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib handler contract
                requested.set()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"type":"object"}')

            def log_message(self, _format, *_args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 0.2
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            schema_path = self.root / "schemas" / "evidence-claim.schema.json"
            write_json(schema_path, {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": f"http://127.0.0.1:{server.server_port}/leak",
            })
            with self.assertRaisesRegex(registry.EvidenceError, "reference-resolving keyword"):
                registry.load_schema(self.root, schema_path)
            thread.join(timeout=1)
            self.assertFalse(requested.is_set())
        finally:
            server.server_close()
            thread.join(timeout=1)

    def test_schema_invalid_claims_report_without_crashing(self) -> None:
        cases = {
            "missing-expiry": lambda value: value.pop("expires_at"),
            "null-review": lambda value: value.__setitem__("review", None),
            "list-status": lambda value: value.__setitem__("runtime_status", ["candidate"]),
        }
        for name, mutation in cases.items():
            with self.subTest(name=name):
                claim_path = self.root / EVIDENCE / "claims" / "bp-assets-purposeful-set.json"
                claim = json_data(claim_path)
                mutation(claim)
                write_json(claim_path, claim)
                report, errors, warnings = self.evaluate()
                self.assertTrue(errors)
                self.assertEqual(report["release_blockers"], ["registry.schema-invalid"])
                shutil.copy2(self.template / EVIDENCE / "claims" / "bp-assets-purposeful-set.json", claim_path)

    def test_malformed_schema_reports_without_crashing(self) -> None:
        schema = self.root / "schemas" / "evidence-claim.schema.json"
        value = json_data(schema)
        value["type"] = "not-a-json-schema-type"
        write_json(schema, value)
        report, errors, warnings = self.evaluate()
        self.assertTrue(errors)
        self.assertIn("invalid Draft 2020-12 schema", "\n".join(errors))

    def test_scheduled_workflow_is_default_branch_offline_and_least_privilege(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "evidence-freshness.yml").read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('cron: "17 4 * * *"', workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("--force-with-lease", workflow)
        self.assertIn("unexpected=", workflow)
        self.assertGreaterEqual(workflow.count("git ls-tree"), 2)
        self.assertGreaterEqual(workflow.count("100644 blob"), 2)
        self.assertIn("test ! -L .github/evidence-freshness", workflow)
        self.assertIn("gh pr close", workflow)
        self.assertNotIn("curl ", workflow)
        self.assertNotIn("wget ", workflow)
        publish = workflow.split("\n  publish:\n", 1)[1]
        self.assertNotIn("python ", publish)
        self.assertNotIn("pip install", publish)

    def test_literal_workflow_run_blocks_parse_as_bash(self) -> None:
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        block_count = 0
        for workflow in workflows:
            for block_number, script in enumerate(literal_workflow_run_blocks(workflow), start=1):
                block_count += 1
                result = subprocess.run(
                    ["bash", "-n"],
                    input=script,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{workflow.relative_to(ROOT)} literal run block {block_number}: {result.stderr}",
                )
        self.assertGreater(block_count, 0)

    def test_schema_manifest_declares_every_evidence_instance(self) -> None:
        manifest = json_data(ROOT / "validation" / "schema-instances.json")
        declared = {
            item
            for mapping in manifest["mappings"]
            if mapping["schema"].startswith("schemas/evidence-")
            for item in mapping.get("instances", [])
        }
        expected = {
            path.relative_to(ROOT).as_posix()
            for path in [
                ROOT / EVIDENCE / "authorities.json",
                ROOT / EVIDENCE / "runtime-map.json",
                ROOT / EVIDENCE / "release-policy.json",
                *(ROOT / EVIDENCE / "claims").glob("*.json"),
                *(ROOT / EVIDENCE / "sources").glob("*.json"),
                *(ROOT / EVIDENCE / "captures").glob("*.json"),
            ]
        }
        self.assertEqual(declared, expected)

    def test_runtime_boundary_forbids_registry_and_control_schemas(self) -> None:
        from tools import runtime_package

        manifest = json_data(ROOT / "runtime" / "seedance-20.manifest.json")
        self.assertFalse(any(path.startswith("research/") for path in manifest["files"]))
        self.assertFalse(any(path.startswith("schemas/evidence-") for path in manifest["files"]))
        for path in ["research/evidence/claims/test.json", "schemas/evidence-claim.schema.json"]:
            with self.subTest(path=path):
                with self.assertRaises(runtime_package.PackageError):
                    runtime_package._validate_runtime_paths(
                        tuple(sorted([*manifest["files"], path])),
                        require_sorted=True,
                    )


if __name__ == "__main__":
    unittest.main()
