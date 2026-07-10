from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = ROOT / ".github" / "evidence-v2"
CHECKER_PATH = EVIDENCE_ROOT / "check_evidence.py"
CLAIM_SCHEMA_PATH = EVIDENCE_ROOT / "evidence-claim.schema.json"
SOURCE_SCHEMA_PATH = EVIDENCE_ROOT / "evidence-source.schema.json"
CLAIMS_PATH = EVIDENCE_ROOT / "claims"
SOURCES_PATH = EVIDENCE_ROOT / "sources"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "evidence-v2-shadow.yml"

SPEC = importlib.util.spec_from_file_location("check_evidence", CHECKER_PATH)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def valid_source(root: Path) -> dict:
    capture = root / ".github" / "evidence-v2" / "captures" / "capture.txt"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text("bounded source capture\n", encoding="utf-8")
    digest = hashlib.sha256(capture.read_bytes()).hexdigest()
    return {
        "$schema": "../evidence-source.schema.json",
        "source_snapshot_id": "test.official.source.2026-07-10",
        "source_id": "test.official.source",
        "title": "Official test source",
        "source_url": "https://docs.byteplus.com/en/docs/ModelArk/test",
        "source_type": "first_party_platform_doc",
        "publisher": "BytePlus",
        "original_language": "en",
        "document_updated_at": "2026-07-01",
        "retrieved_at": "2026-07-10",
        "retrieval_status": "fetched",
        "retrieval_method": "test_fixture",
        "retrieved_document_sha256": digest,
        "capture_path": ".github/evidence-v2/captures/capture.txt",
    }


def valid_claim() -> dict:
    summary = "Official guidance describes one bounded surface behavior for deterministic validator testing."
    return {
        "$schema": "../evidence-claim.schema.json",
        "claim_id": "test.prompt.example",
        "claim_text": "A sufficiently specific atomic assertion used only by the validator test suite.",
        "normalized_key": "test.prompt.example",
        "value": "bounded_value",
        "model_family": "seedance",
        "model_version": "2.0-series",
        "claim_class": "prompt_grammar",
        "scope": {"surfaces": ["byteplus.test"], "tasks": ["reference_generation"], "locale": "en", "region": "unspecified"},
        "support_status": "supported",
        "volatility": "volatile",
        "agreement_status": "uncontested",
        "lifecycle_status": "active",
        "runtime_eligible": False,
        "runtime_disposition": "defer",
        "source_snapshot_id": "test.official.source.2026-07-10",
        "source_locator": {"heading_path": ["Prompting"], "fragment_hint": "example", "captured_lines": [1, 2]},
        "evidence_summary": summary,
        "evidence_summary_sha256": CHECKER.sha256_text(summary),
        "verified_at": "2026-07-10",
        "expires_at": "2026-08-09",
        "supersedes": [],
        "relations": [],
        "conflict_group": None,
        "affected_paths": ["existing.md"],
        "review": {"status": "pending", "reviewers": []},
        "notes": "Fixture only.",
    }


class EvidenceCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.claim_schema = CHECKER.load_schema(CLAIM_SCHEMA_PATH)
        self.source_schema = CHECKER.load_schema(SOURCE_SCHEMA_PATH)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "existing.md").write_text("fixture\n", encoding="utf-8")
        self.source = valid_source(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def semantic(self, claims: list[dict], sources: list[dict] | None = None, *, as_of=date(2026, 7, 10), enforce=False, shadow=False):
        source_records = sources or [copy.deepcopy(self.source)]
        source_errors, by_id, artifact_verified = CHECKER.source_errors(source_records, self.root, as_of)
        claim_errors, warnings = CHECKER.claim_errors(
            claims, by_id, artifact_verified, self.root, as_of, enforce, shadow
        )
        return sorted(source_errors + claim_errors), warnings, artifact_verified

    def test_pilot_claims_validate_as_non_activating_shadow_records(self) -> None:
        report, errors, _warnings = CHECKER.evaluate(
            CLAIM_SCHEMA_PATH,
            SOURCE_SCHEMA_PATH,
            CLAIMS_PATH,
            SOURCES_PATH,
            ROOT,
            date(2026, 7, 10),
            False,
            True,
        )
        self.assertEqual(errors, [])
        self.assertGreaterEqual(report["claim_count"], 10)
        self.assertEqual(report["runtime_eligible_count"], 0)
        self.assertEqual(report["artifact_verified_source_count"], 0)
        self.assertEqual(report["review_counts"], {"pending": report["claim_count"]})

    def test_claim_schema_rejects_missing_and_additional_fields(self) -> None:
        missing = valid_claim()
        del missing["claim_text"]
        extra = valid_claim()
        extra["invented"] = True
        errors = CHECKER.schema_errors(
            self.claim_schema,
            [{**missing, "__file__": "missing.json"}, {**extra, "__file__": "extra.json"}],
        )
        self.assertTrue(any("claim_text" in error for error in errors))
        self.assertTrue(any("Additional properties" in error for error in errors))

        activated = valid_claim()
        activated["runtime_eligible"] = True
        errors = CHECKER.schema_errors(self.claim_schema, [{**activated, "__file__": "activated.json"}])
        self.assertTrue(any("False was expected" in error for error in errors))

    def test_source_schema_rejects_invalid_hash_and_date(self) -> None:
        source = copy.deepcopy(self.source)
        source["retrieved_document_sha256"] = "bad"
        source["retrieved_at"] = "not-a-date"
        errors = CHECKER.schema_errors(self.source_schema, [{**source, "__file__": "bad-source.json"}])
        self.assertTrue(any("does not match" in error for error in errors))
        self.assertTrue(any("not a 'date'" in error for error in errors))

    def test_duplicate_id_and_summary_hash_mismatch_fail(self) -> None:
        first = valid_claim()
        second = copy.deepcopy(first)
        second["evidence_summary_sha256"] = "b" * 64
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("duplicate claim_id" in error for error in errors))
        self.assertTrue(any("summary hash mismatch" in error for error in errors))

    def test_authority_claim_requires_reviewed_host_and_publisher_mapping(self) -> None:
        attacker = copy.deepcopy(self.source)
        attacker["source_url"] = "https://attacker.example/fake"
        errors, _warnings, _verified = self.semantic([valid_claim()], [attacker])
        self.assertTrue(any("authority" in error for error in errors))

    def test_non_https_and_future_source_dates_fail(self) -> None:
        source = copy.deepcopy(self.source)
        source["source_url"] = "http://docs.byteplus.com/fake"
        source["retrieved_at"] = "2026-07-11"
        source["document_updated_at"] = "2026-07-12"
        errors, _warnings, _verified = self.semantic([valid_claim()], [source])
        self.assertTrue(any("HTTPS" in error for error in errors))
        self.assertTrue(any("future" in error for error in errors))

    def test_capture_artifact_hash_is_recomputed(self) -> None:
        errors, _warnings, verified = self.semantic([valid_claim()])
        self.assertEqual(errors, [])
        self.assertIn(self.source["source_snapshot_id"], verified)

        source = copy.deepcopy(self.source)
        source["retrieved_document_sha256"] = "f" * 64
        errors, _warnings, _verified = self.semantic([valid_claim()], [source])
        self.assertTrue(any("capture artifact hash mismatch" in error for error in errors))

    def test_capture_artifact_must_use_dedicated_directory(self) -> None:
        outside = self.root / "SKILL.md"
        outside.write_text("not evidence\n", encoding="utf-8")
        source = copy.deepcopy(self.source)
        source["capture_path"] = "SKILL.md"
        source["retrieved_document_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        errors, _warnings, verified = self.semantic([valid_claim()], [source])
        self.assertTrue(any("must stay under" in error for error in errors))
        self.assertNotIn(source["source_snapshot_id"], verified)

    def test_runtime_activation_requires_capture_review_and_unexpired_evidence(self) -> None:
        claim = valid_claim()
        claim["runtime_eligible"] = True
        claim["runtime_disposition"] = "allow"
        claim["review"] = {"status": "approved", "reviewers": ["one", "two"]}
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("activation is locked" in error for error in errors))

        source = copy.deepcopy(self.source)
        source["capture_path"] = None
        errors, _warnings, _verified = self.semantic([claim], [source])
        self.assertTrue(any("hash-verified capture" in error for error in errors))

        errors, _warnings, _verified = self.semantic([claim], as_of=date(2026, 8, 10))
        self.assertTrue(any("active, unexpired" in error for error in errors))

    def test_shadow_mode_hard_fails_every_runtime_eligible_record(self) -> None:
        claim = valid_claim()
        claim["runtime_eligible"] = True
        claim["runtime_disposition"] = "allow"
        claim["review"] = {"status": "approved", "reviewers": ["one", "two"]}
        errors, _warnings, _verified = self.semantic([claim], shadow=True)
        self.assertTrue(any("shadow mode forbids" in error for error in errors))

    def test_unverified_and_seedance_25_cannot_activate(self) -> None:
        claim = valid_claim()
        claim["support_status"] = "unverified"
        claim["agreement_status"] = "not_assessed"
        claim["runtime_eligible"] = True
        claim["runtime_disposition"] = "allow"
        claim["review"] = {"status": "approved", "reviewers": ["one", "two"]}
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("cannot be runtime-eligible" in error for error in errors))

        for model_version in ["2.5", "seedance-2.5", "seedance_2_5", "Seedance V2.5 preview", "3.0"]:
            claim = valid_claim()
            claim["model_version"] = model_version
            claim["runtime_eligible"] = True
            claim["runtime_disposition"] = "allow"
            claim["review"] = {"status": "approved", "reviewers": ["one", "two"]}
            errors, _warnings, _verified = self.semantic([claim])
            self.assertTrue(any("official-contract activation policy" in error for error in errors), model_version)

    def test_unverified_requires_not_assessed_agreement(self) -> None:
        claim = valid_claim()
        claim["support_status"] = "unverified"
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("must use `not_assessed`" in error for error in errors))

        claim["agreement_status"] = "not_assessed"
        errors, _warnings, _verified = self.semantic([claim])
        self.assertEqual(errors, [])

    def test_claim_class_restricts_source_authority(self) -> None:
        community = copy.deepcopy(self.source)
        community["source_url"] = "https://community.example/post"
        community["source_type"] = "community_source"
        community["publisher"] = "Community"
        claim = valid_claim()
        claim["claim_class"] = "model_capability"
        claim["expires_at"] = "2026-12-31"
        errors, _warnings, _verified = self.semantic([claim], [community])
        self.assertTrue(any("cannot be supported by source type" in error for error in errors))

        claim["claim_class"] = "community_pattern"
        claim["expires_at"] = "2026-08-09"
        claim["runtime_eligible"] = True
        claim["runtime_disposition"] = "allow"
        claim["review"] = {"status": "approved", "reviewers": ["one", "two"]}
        errors, _warnings, _verified = self.semantic([claim], [community])
        self.assertTrue(any("cannot activate runtime behavior" in error for error in errors))
        self.assertTrue(any("authoritative platform source" in error for error in errors))

    def test_reversed_capture_lines_and_missing_surface_fail(self) -> None:
        claim = valid_claim()
        claim["source_locator"]["captured_lines"] = [10, 1]
        claim["scope"]["surfaces"] = []
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("line range is reversed" in error for error in errors))
        self.assertTrue(any("requires at least one surface" in error for error in errors))

    def test_future_verification_invalid_ttl_and_missing_path_fail(self) -> None:
        claim = valid_claim()
        claim["verified_at"] = "2026-07-11"
        claim["expires_at"] = "2026-09-01"
        claim["affected_paths"] = ["missing.md"]
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("future" in error for error in errors))
        self.assertTrue(any("TTL" in error for error in errors))
        self.assertTrue(any("does not exist" in error for error in errors))

        claim = valid_claim()
        claim["affected_paths"] = [str(self.root / "existing.md")]
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("repository-relative" in error for error in errors))

    def test_volatile_freshness_cannot_be_reset_without_new_snapshot(self) -> None:
        claim = valid_claim()
        claim["verified_at"] = "2026-07-11"
        claim["expires_at"] = "2026-08-10"
        source = copy.deepcopy(self.source)
        source["retrieved_at"] = "2026-07-11"
        errors, _warnings, _verified = self.semantic([claim], [source], as_of=date(2026, 7, 11))
        self.assertTrue(any("source_snapshot_id date must equal" in error for error in errors))

        source["source_snapshot_id"] = "test.official.source.2026-07-11"
        claim["source_snapshot_id"] = source["source_snapshot_id"]
        errors, _warnings, _verified = self.semantic([claim], [source], as_of=date(2026, 7, 11))
        self.assertEqual(errors, [])

        claim["verified_at"] = "2026-07-12"
        claim["expires_at"] = "2026-08-11"
        errors, _warnings, _verified = self.semantic([claim], [source], as_of=date(2026, 7, 12))
        self.assertTrue(any("same-day source snapshot" in error for error in errors))

    def test_expiry_warns_in_shadow_freshness_and_fails_when_enforced(self) -> None:
        claim = valid_claim()
        errors, warnings, _verified = self.semantic([claim], as_of=date(2026, 8, 10), enforce=False)
        self.assertEqual(errors, [])
        self.assertTrue(any("expired" in warning for warning in warnings))
        errors, _warnings, _verified = self.semantic([claim], as_of=date(2026, 8, 10), enforce=True)
        self.assertTrue(any("expired" in error for error in errors))

    def test_qualified_evidence_uses_typed_relation_not_false_conflict(self) -> None:
        first = valid_claim()
        first["claim_id"] = "test.qualified.first"
        first["agreement_status"] = "qualified"
        first["relations"] = [{"claim_id": "test.qualified.second", "type": "tension_with"}]
        second = copy.deepcopy(first)
        second["claim_id"] = "test.qualified.second"
        second["value"] = "different_surface_example"
        second["scope"]["surfaces"] = ["byteplus.other"]
        second["relations"] = [{"claim_id": "test.qualified.first", "type": "tension_with"}]
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertEqual(errors, [])

    def test_conflict_groups_require_distinct_values_and_two_members(self) -> None:
        first = valid_claim()
        first["claim_id"] = "test.conflict.first"
        first["agreement_status"] = "conflicting"
        first["conflict_group"] = "real-conflict"
        errors, _warnings, _verified = self.semantic([first])
        self.assertTrue(any("fewer than two" in error for error in errors))

        second = copy.deepcopy(first)
        second["claim_id"] = "test.conflict.second"
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("incompatible values" in error for error in errors))

        second["value"] = "different"
        second["normalized_key"] = "test.different.key"
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("mixes normalized keys" in error for error in errors))

    def test_differing_active_values_require_declared_conflict(self) -> None:
        first = valid_claim()
        first["claim_id"] = "test.value.first"
        first["scope"]["surfaces"] = ["byteplus.test", "byteplus.other"]
        first["scope"]["tasks"] = ["reference_generation", "edit"]
        second = copy.deepcopy(first)
        second["claim_id"] = "test.value.second"
        second["value"] = "different"
        second["scope"]["surfaces"] = list(reversed(second["scope"]["surfaces"]))
        second["scope"]["tasks"] = list(reversed(second["scope"]["tasks"]))
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("undeclared value conflict" in error for error in errors))

    def test_relations_reject_self_links_and_require_reciprocal_types(self) -> None:
        first = valid_claim()
        first["claim_id"] = "test.relation.first"
        first["relations"] = [{"claim_id": first["claim_id"], "type": "tension_with"}]
        errors, _warnings, _verified = self.semantic([first])
        self.assertTrue(any("cannot relate to itself" in error for error in errors))

        second = copy.deepcopy(first)
        second["claim_id"] = "test.relation.second"
        second["relations"] = []
        first["relations"] = [{"claim_id": second["claim_id"], "type": "qualifies"}]
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("requires reciprocal `qualified_by`" in error for error in errors))

        second["relations"] = [{"claim_id": first["claim_id"], "type": "qualified_by"}]
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertEqual(errors, [])

    def test_superseded_lifecycle_requires_compatible_successor(self) -> None:
        old = valid_claim()
        old["claim_id"] = "test.superseded.old"
        old["lifecycle_status"] = "superseded"
        errors, _warnings, _verified = self.semantic([old])
        self.assertTrue(any("incoming successor edge" in error for error in errors))

        successor = valid_claim()
        successor["claim_id"] = "test.superseded.new"
        successor["supersedes"] = [old["claim_id"]]
        errors, _warnings, _verified = self.semantic([old, successor])
        self.assertEqual(errors, [])

    def test_editorial_review_states_are_consistent(self) -> None:
        claim = valid_claim()
        claim["review"] = {"status": "pending", "reviewers": ["one"]}
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("pending review" in error for error in errors))

        claim["review"] = {"status": "rejected", "reviewers": []}
        errors, _warnings, _verified = self.semantic([claim])
        self.assertTrue(any("must name at least one" in error for error in errors))
        self.assertTrue(any("must remain blocked" in error for error in errors))

    def test_workflow_enforces_shadow_and_freshness_modes(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("--shadow-only", workflow)
        self.assertIn("--enforce-freshness", workflow)

    def test_dangling_relation_and_cyclic_supersession_fail(self) -> None:
        first = valid_claim()
        first["claim_id"] = "test.supersedes.first"
        first["relations"] = [{"claim_id": "missing.claim", "type": "supports"}]
        errors, _warnings, _verified = self.semantic([first])
        self.assertTrue(any("dangling relation" in error for error in errors))

        second = valid_claim()
        second["claim_id"] = "test.supersedes.second"
        first["relations"] = []
        first["supersedes"] = [second["claim_id"]]
        second["supersedes"] = [first["claim_id"]]
        errors, _warnings, _verified = self.semantic([first, second])
        self.assertTrue(any("supersedes cycle" in error for error in errors))

    def test_empty_and_malformed_record_directories_fail(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        records, errors = CHECKER.load_records(empty, "claims")
        self.assertEqual(records, [])
        self.assertTrue(any("empty" in error for error in errors))

        (empty / "bad.json").write_text("{not-json", encoding="utf-8")
        records, errors = CHECKER.load_records(empty, "claims")
        self.assertEqual(records, [])
        self.assertTrue(any("JSON parse error" in error for error in errors))

    def test_report_is_deterministic(self) -> None:
        report_one = self.root / "one.json"
        report_two = self.root / "two.json"
        command = [
            sys.executable,
            "-B",
            str(CHECKER_PATH),
            "--claim-schema",
            str(CLAIM_SCHEMA_PATH),
            "--source-schema",
            str(SOURCE_SCHEMA_PATH),
            "--claims",
            str(CLAIMS_PATH),
            "--sources",
            str(SOURCES_PATH),
            "--repo-root",
            str(ROOT),
            "--as-of",
            "2026-07-10",
            "--shadow-only",
        ]
        for output in [report_one, report_two]:
            result = subprocess.run(command + ["--report", str(output)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report_one.read_bytes(), report_two.read_bytes())


if __name__ == "__main__":
    unittest.main()
