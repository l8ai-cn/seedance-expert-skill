#!/usr/bin/env python3
"""Dependency-free V7-10 evaluation programme validator.

The checked-in programme is public development scaffolding. This checker never
opens a socket, executes a plan-supplied command, runs a provider, or derives a
release/quality verdict. It validates a closed inventory and exercises bounded
mutations of that inventory so weakened gates fail closed.
"""
from __future__ import annotations

import argparse
import ast
import copy
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Callable


PROGRAM_PATH = Path("evals/evaluation-program-v1.json")
BENCHMARK_PATH = Path("validation/fixtures/benchmark-manifest-v1.valid.json")
ANNOTATION_PATH = Path("validation/fixtures/atomic-output-annotation-v1.valid.json")
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 200_000
MAX_JSON_STRING_BYTES = 1 * 1024 * 1024
BASE_COMMIT = "8c79cc6e0784d746b96216917699f057e4833e66"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,127}$")

REQUIRED_TOP_LEVEL = {
    "$schema",
    "schema_version",
    "program_id",
    "program_date",
    "candidate_base_commit",
    "status",
    "network_policy",
    "release_gate",
    "quality_claims_allowed",
    "public_corpora",
    "deterministic_suites",
    "mutation_campaigns",
    "metamorphic_relations",
    "output_review_policy",
    "deferred_release_requirements",
}

DETERMINISTIC_SUITES = {
    "text_eval_contracts": {
        "coverage": {"blind_case_loading", "empty_selection_failure", "judge_false_failure"},
        "entrypoints": {"scripts/eval_schema_check.py", "tests/test_eval_harness.py"},
    },
    "evidence_authority": {
        "coverage": {"claim_closure", "expiry", "authority_removal"},
        "entrypoints": {"tests/test_evidence_registry.py"},
    },
    "surface_binding": {
        "coverage": {"operation_gate", "reference_order", "surface_transport"},
        "entrypoints": {"tests/test_surface_bindings.py"},
    },
    "semantic_compiler": {
        "coverage": {"causal_order", "locale_parity", "surface_invariance"},
        "entrypoints": {
            "tests/test_semantic_lint.py",
            "tests/test_prompt_compile.py",
            "tests/test_evaluation_metamorphic.py",
        },
    },
    "project_state": {
        "coverage": {"canon_handoff", "motion_ownership", "non_destructive_migration"},
        "entrypoints": {"tests/test_project_state_v2.py", "tests/test_project_state_migration.py"},
    },
    "av_semantics": {
        "coverage": {"exact_speech", "audio_continuity", "editorial_transitions", "temporal_evidence"},
        "entrypoints": {
            "tests/test_scene_ir_v2.py",
            "tests/test_semantic_lint_v2.py",
            "tests/test_prompt_compile_v2.py",
            "tests/test_av_take_review.py",
        },
    },
    "runtime_install": {
        "coverage": {"package_boundary", "transaction_rollback", "portability"},
        "entrypoints": {"tests/test_runtime_package.py"},
    },
}

PROGRAM_MUTATIONS = {
    "network_enable",
    "release_enable",
    "quality_claim_enable",
    "held_out_enable",
    "drop_suite",
    "unknown_entrypoint",
    "duplicate_suite",
    "weaken_threshold",
    "drop_metamorphic_relation",
    "model_relation_as_offline",
    "reduce_attempt_count",
    "allow_dropped_attempts",
}

OUTPUT_REVIEW_MUTATIONS = {
    "release_enable",
    "quality_claim_enable",
    "generator_reviewer_collision",
    "false_independence",
    "media_hash_mismatch",
    "manifest_digest_mismatch",
    "unknown_observable",
    "rubric_item_mismatch",
    "evidence_parent_mismatch",
    "derived_without_record",
    "temporal_still_pass",
    "temporal_metadata_pass",
    "temporal_single_frame_pass",
    "time_range_out_of_bounds",
    "frame_range_out_of_bounds",
    "audio_absent_pass",
    "whole_output_partial_pass",
    "hidden_cause_claim",
    "missing_evidence_locus",
    "invalid_confidence",
    "extra_field",
}

METAMORPHIC_RELATIONS = {
    "surface_swap_preserves_semantics": {
        "execution": "offline_deterministic",
        "oracle_path": "tests/test_evaluation_metamorphic.py",
        "oracle_ids": {"test_surface_swap_preserves_semantics"},
        "invariants": {"semantic_program", "causal_order", "entity_identity", "binding_identity"},
    },
    "language_swap_preserves_semantics": {
        "execution": "offline_deterministic",
        "oracle_path": "tests/test_evaluation_metamorphic.py",
        "oracle_ids": {"test_language_swap_preserves_semantics"},
        "invariants": {"semantic_program", "event_order", "exact_utterance", "binding_identity"},
    },
    "reference_order_follows_profile": {
        "execution": "offline_deterministic",
        "oracle_path": "tests/test_evaluation_metamorphic.py",
        "oracle_ids": {"test_reference_reorder_follows_profile"},
        "invariants": {"authority", "binding_identity", "typed_media_role"},
    },
    "authority_removal_fails_closed": {
        "execution": "offline_deterministic",
        "oracle_path": "tests/test_evidence_registry.py",
        "oracle_ids": {"test_missing_selected_claim_blocks_release"},
        "invariants": {"release_blocked", "diagnostic_present"},
    },
    "irrelevant_style_preserves_operation": {
        "execution": "development_model_only",
        "oracle_path": "evals/evals.json",
        "oracle_ids": {
            "task_classification_baseline_first_last_frame",
            "task_classification_ignores_style_adjectives",
        },
        "invariants": {"operation", "input_contract", "authority_requirements"},
    },
    "final_frame_weakens_temporal_evidence": {
        "execution": "offline_deterministic",
        "oracle_path": "tests/test_evaluation_metamorphic.py",
        "oracle_ids": {"test_final_frame_weakens_temporal_evidence"},
        "invariants": {"temporal_unknown", "audio_unknown", "release_blocked"},
    },
}

REQUIRED_OBSERVABLES = {
    "operation_correctness",
    "binding_integrity",
    "identity_adherence",
    "composition_adherence",
    "subject_motion",
    "camera_motion",
    "causal_order",
    "physical_consequence",
    "material_response",
    "settled_endpoint",
    "temporal_audio_sync",
    "semantic_audio_sync",
    "speaker_assignment",
    "dialogue_exactness",
    "spoken_language",
    "dialogue_intelligibility",
    "lip_sync",
    "audio_continuity",
    "editorial_cut",
    "multishot_continuity",
    "unexpected_text_logo",
    "overall_usable_take",
}

TEMPORAL_OBSERVABLES = {
    "operation_correctness",
    "subject_motion",
    "camera_motion",
    "causal_order",
    "physical_consequence",
    "material_response",
    "settled_endpoint",
    "temporal_audio_sync",
    "semantic_audio_sync",
    "speaker_assignment",
    "dialogue_exactness",
    "spoken_language",
    "dialogue_intelligibility",
    "lip_sync",
    "audio_continuity",
    "editorial_cut",
    "multishot_continuity",
    "overall_usable_take",
}

AUDIO_OBSERVABLES = {
    "temporal_audio_sync",
    "semantic_audio_sync",
    "speaker_assignment",
    "dialogue_exactness",
    "spoken_language",
    "dialogue_intelligibility",
    "lip_sync",
    "audio_continuity",
}

WHOLE_VIDEO_PASS_OBSERVABLES = {
    "operation_correctness",
    "binding_integrity",
    "identity_adherence",
    "composition_adherence",
    "unexpected_text_logo",
}

DEFERRED_RELEASE_REQUIREMENTS = {
    "protected_runner",
    "approved_held_out_digest",
    "private_held_out_corpus",
    "independent_reviewer_attestation",
    "live_provider_outputs",
    "complete_attempt_retention",
    "provider_adherence_review",
    "release_authority_approval",
}

BENCHMARK_FIELDS = {
    "$schema",
    "schema_version",
    "benchmark_id",
    "manifest_status",
    "execution_mode",
    "release_eligible",
    "quality_claim_status",
    "is_synthetic_fixture",
    "evaluated_on",
    "generator_identity_sha256",
    "model",
    "surface",
    "operation",
    "protocol",
    "condition",
    "required_attempt_count",
    "retention_policy",
    "attempts",
    "reviewers",
    "review_policy",
}

ATTEMPT_FIELDS = {
    "attempt_id",
    "attempt_index",
    "condition_id",
    "generation_record_sha256",
    "input_manifest_sha256",
    "request_sha256",
    "request_template_sha256",
    "generation_settings_sha256",
    "requested_seed",
    "prompt_render_sha256",
    "attempt_status",
    "output_id",
    "output_media_sha256",
    "media_kind",
    "media_metadata_sha256",
    "duration_ms",
    "frame_count",
    "audio_present",
    "failure_record_sha256",
    "retained",
}

ANNOTATION_FIELDS = {
    "$schema",
    "schema_version",
    "annotation_id",
    "benchmark_id",
    "condition_id",
    "attempt_id",
    "attempt_index",
    "benchmark_manifest_sha256",
    "condition_sha256",
    "generation_record_sha256",
    "rubric_sha256",
    "rubric_item_sha256",
    "output_id",
    "output_media_sha256",
    "evidence_asset_kind",
    "evidence_asset_sha256",
    "evidence_parent_output_sha256",
    "derivation_record_sha256",
    "observable_id",
    "observable_dimension",
    "status",
    "evidence_locus",
    "confidence",
    "reviewer",
    "claim_boundary",
    "quality_claim_status",
    "release_eligible",
    "is_synthetic_fixture",
}


class DuplicateKeyError(ValueError):
    pass


class JsonSnapshot:
    """Immutable exact bytes with parsed value and digest derived on access."""

    __slots__ = ("__raw",)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("JsonSnapshot cannot be subclassed")

    def __init__(self, raw: bytes) -> None:
        payload = bytes(raw)
        strict_parse_json_bytes(payload)
        object.__setattr__(self, "_JsonSnapshot__raw", payload)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    @property
    def raw(self) -> bytes:
        return self.__raw

    @property
    def value(self) -> Any:
        return strict_parse_json_bytes(self.__raw)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.__raw).hexdigest()


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def _validate_json_resources(value: Any) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON resource limit exceeded")
        if isinstance(item, dict):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item.encode("utf-8")) > MAX_JSON_STRING_BYTES:
            raise ValueError("JSON string resource limit exceeded")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("non-finite JSON number")


def strict_parse_json_bytes(payload: bytes) -> Any:
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise ValueError("JSON byte length outside allowed range")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (json.JSONDecodeError, RecursionError, UnicodeError) as exc:
        raise ValueError("invalid JSON") from exc
    _validate_json_resources(value)
    return value


def _read_stable_bytes(path: Path, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError("file is unreadable") from exc
    attributes = getattr(before, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or stat.S_ISLNK(before.st_mode)
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    ):
        raise ValueError("file is not a plain single-link file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("file is unreadable") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError("file changed during open")

        def read_pass() -> bytes:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(65_536, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("file byte length outside allowed range")
            return b"".join(chunks)

        first = read_pass()
        first_metadata = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        second = read_pass()
        second_metadata = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if (
            first != second
            or len(first) != opened.st_size
            or identity(opened) != identity(first_metadata)
            or identity(opened) != identity(second_metadata)
        ):
            raise ValueError("file changed during read")
        try:
            final_path = path.lstat()
        except OSError as exc:
            raise ValueError("file changed during read") from exc
        final_attributes = getattr(final_path, "st_file_attributes", 0)
        if (
            not stat.S_ISREG(final_path.st_mode)
            or final_path.st_nlink != 1
            or stat.S_ISLNK(final_path.st_mode)
            or bool(final_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
            or (final_path.st_dev, final_path.st_ino) != (opened.st_dev, opened.st_ino)
            or identity(before) != identity(final_path)
        ):
            raise ValueError("file changed during read")
        return first
    finally:
        os.close(descriptor)


def strict_load_snapshot(path: Path) -> JsonSnapshot:
    return JsonSnapshot(_read_stable_bytes(path))


def strict_load_json(path: Path) -> Any:
    return strict_load_snapshot(path).value


def _is_unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))


def _string_in(value: Any, allowed: set[str] | frozenset[str]) -> bool:
    """Membership for untrusted JSON scalars without unhashable-value crashes."""
    return isinstance(value, str) and value in allowed


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def snapshot_from_value(value: Any) -> JsonSnapshot:
    """Create an internally consistent snapshot for in-memory mutation probes."""
    return JsonSnapshot(_canonical_json_bytes(value))


def _safe_repo_file(root: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or "\\" in raw_path or "\x00" in raw_path:
        return None
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    current = root
    try:
        for part in pure.parts:
            current = current / part
            metadata = os.lstat(current)
            attributes = getattr(metadata, "st_file_attributes", 0)
            if stat.S_ISLNK(metadata.st_mode) or bool(
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                return None
        final_metadata = os.lstat(current)
        if not stat.S_ISREG(final_metadata.st_mode) or final_metadata.st_nlink != 1:
            return None
        current.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return current


def _index_objects(value: Any, id_key: str, errors: list[str], prefix: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    if not isinstance(value, list):
        errors.append(f"{prefix}.shape")
        return indexed
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get(id_key), str):
            errors.append(f"{prefix}.item")
            continue
        identifier = item[id_key]
        if identifier in indexed:
            errors.append(f"{prefix}.duplicate")
        indexed[identifier] = item
    return indexed


def _set_matches(value: Any, expected: set[str]) -> bool:
    return _is_unique_strings(value) and set(value) == expected


def _same_scalar(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    return type(actual) is type(expected) and actual == expected


def validate_program(program: Any, root: Path, *, check_oracles: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(program, dict):
        return ["program.shape"]
    if set(program) != REQUIRED_TOP_LEVEL:
        errors.append("program.fields")
    fixed = {
        "$schema": "https://github.com/Emily2040/seedance-2.0/schemas/evaluation-program-v1.schema.json",
        "schema_version": 1,
        "program_id": "v7_10_evaluation_candidate",
        "candidate_base_commit": BASE_COMMIT,
        "status": "candidate_non_release",
        "network_policy": "forbidden",
        "release_gate": False,
        "quality_claims_allowed": False,
    }
    for field, expected in fixed.items():
        if not _same_scalar(program.get(field), expected):
            errors.append(f"program.{field}")
    date = program.get("program_date")
    if date != "2026-07-13":
        errors.append("program.program_date")

    corpora = program.get("public_corpora")
    expected_corpora = {
        "development_release_eligible": False,
        "live_canary_release_eligible": False,
        "held_out_execution": "blocked_without_protected_runner",
    }
    if not isinstance(corpora, dict) or set(corpora) != set(expected_corpora) or any(
        not _same_scalar(corpora.get(field), expected) for field, expected in expected_corpora.items()
    ):
        errors.append("program.public_corpora")

    suites = _index_objects(program.get("deterministic_suites"), "suite_id", errors, "suite")
    if set(suites) != set(DETERMINISTIC_SUITES):
        errors.append("suite.ids")
    for suite_id, expected in DETERMINISTIC_SUITES.items():
        item = suites.get(suite_id)
        if item is None:
            continue
        if set(item) != {"suite_id", "coverage", "entrypoints"}:
            errors.append(f"suite.{suite_id}.fields")
        if not _set_matches(item.get("coverage"), expected["coverage"]):
            errors.append(f"suite.{suite_id}.coverage")
        if not _set_matches(item.get("entrypoints"), expected["entrypoints"]):
            errors.append(f"suite.{suite_id}.entrypoints")
        if check_oracles:
            for entrypoint in expected["entrypoints"]:
                if _safe_repo_file(root, entrypoint) is None:
                    errors.append(f"suite.{suite_id}.missing_entrypoint")

    campaigns = _index_objects(program.get("mutation_campaigns"), "campaign_id", errors, "campaign")
    if set(campaigns) != {"evaluation_program_contract", "output_review_contract"}:
        errors.append("campaign.ids")
    campaign_contracts = {
        "evaluation_program_contract": ("evals/evaluation-program-v1.json", PROGRAM_MUTATIONS),
        "output_review_contract": ("validation/fixtures/atomic-output-annotation-v1.valid.json", OUTPUT_REVIEW_MUTATIONS),
    }
    for campaign_id, (target, mutation_ids) in campaign_contracts.items():
        item = campaigns.get(campaign_id)
        if item is None:
            continue
        if set(item) != {"campaign_id", "target", "minimum_detection_rate", "mutation_ids"}:
            errors.append(f"campaign.{campaign_id}.fields")
        if item.get("target") != target:
            errors.append(f"campaign.{campaign_id}.target")
        threshold = item.get("minimum_detection_rate")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold < 0.9 or threshold > 1:
            errors.append(f"campaign.{campaign_id}.threshold")
        if not _set_matches(item.get("mutation_ids"), mutation_ids):
            errors.append(f"campaign.{campaign_id}.mutations")
        if check_oracles and _safe_repo_file(root, target) is None:
            errors.append(f"campaign.{campaign_id}.missing_target")

    relations = _index_objects(program.get("metamorphic_relations"), "relation_id", errors, "metamorphic")
    if set(relations) != set(METAMORPHIC_RELATIONS):
        errors.append("metamorphic.ids")
    for relation_id, expected in METAMORPHIC_RELATIONS.items():
        item = relations.get(relation_id)
        if item is None:
            continue
        if set(item) != {"relation_id", "execution", "oracle_path", "oracle_ids", "invariants"}:
            errors.append(f"metamorphic.{relation_id}.fields")
        for field in ("execution", "oracle_path"):
            if item.get(field) != expected[field]:
                errors.append(f"metamorphic.{relation_id}.{field}")
        if not _set_matches(item.get("oracle_ids"), expected["oracle_ids"]):
            errors.append(f"metamorphic.{relation_id}.oracle_ids")
        if not _set_matches(item.get("invariants"), expected["invariants"]):
            errors.append(f"metamorphic.{relation_id}.invariants")
        if check_oracles:
            oracle = _safe_repo_file(root, item.get("oracle_path"))
            declared_ids = set(item["oracle_ids"]) if _is_unique_strings(item.get("oracle_ids")) else set()
            if oracle is None:
                errors.append(f"metamorphic.{relation_id}.oracle_missing")
            else:
                try:
                    if oracle.suffix == ".py":
                        tree = ast.parse(_read_stable_bytes(oracle).decode("utf-8"), filename=oracle.as_posix())
                        bound_ids = {
                            node.name
                            for node in ast.walk(tree)
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        }
                    else:
                        payload = strict_load_json(oracle)
                        cases = payload.get("cases", []) if isinstance(payload, dict) else []
                        bound_ids = {
                            case["id"]
                            for case in cases
                            if isinstance(case, dict) and isinstance(case.get("id"), str)
                        }
                    present = bool(declared_ids) and declared_ids.issubset(bound_ids)
                except (OSError, UnicodeError, ValueError, TypeError):
                    present = False
                if not present:
                    errors.append(f"metamorphic.{relation_id}.oracle_unbound")

    policy = program.get("output_review_policy")
    if not isinstance(policy, dict):
        errors.append("output_policy.shape")
    else:
        expected_fields = {
            "benchmark_manifest_schema",
            "atomic_annotation_schema",
            "minimum_attempts_per_condition",
            "retain_all_attempts",
            "distinct_generator_and_reviewer",
            "required_observables",
            "temporal_observables",
        }
        if set(policy) != expected_fields:
            errors.append("output_policy.fields")
        if policy.get("benchmark_manifest_schema") != "schemas/benchmark-manifest-v1.schema.json":
            errors.append("output_policy.benchmark_schema")
        if policy.get("atomic_annotation_schema") != "schemas/atomic-output-annotation-v1.schema.json":
            errors.append("output_policy.annotation_schema")
        if policy.get("minimum_attempts_per_condition") != 10 or isinstance(policy.get("minimum_attempts_per_condition"), bool):
            errors.append("output_policy.attempt_count")
        if policy.get("retain_all_attempts") is not True:
            errors.append("output_policy.retention")
        if policy.get("distinct_generator_and_reviewer") is not True:
            errors.append("output_policy.reviewer_separation")
        if not _set_matches(policy.get("required_observables"), REQUIRED_OBSERVABLES):
            errors.append("output_policy.observables")
        if not _set_matches(policy.get("temporal_observables"), TEMPORAL_OBSERVABLES):
            errors.append("output_policy.temporal_observables")
        if check_oracles:
            for field in ("benchmark_manifest_schema", "atomic_annotation_schema"):
                if _safe_repo_file(root, policy.get(field)) is None:
                    errors.append(f"output_policy.{field}_missing")

    if not _set_matches(program.get("deferred_release_requirements"), DEFERRED_RELEASE_REQUIREMENTS):
        errors.append("program.deferred_release_requirements")
    return sorted(set(errors))


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(_read_stable_bytes(path)).hexdigest()


def _check_hash_fields(value: dict[str, Any], fields: set[str], errors: list[str], prefix: str) -> None:
    for field in fields:
        if not _valid_sha256(value.get(field)):
            errors.append(f"{prefix}.{field}")


def validate_benchmark_manifest(manifest: Any, root: Path | None = None) -> list[str]:
    """Validate the cross-field benchmark contract without third-party code."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["benchmark.shape"]
    if set(manifest) != BENCHMARK_FIELDS:
        errors.append("benchmark.fields")
    fixed = {
        "$schema": "https://github.com/Emily2040/seedance-2.0/schemas/benchmark-manifest-v1.schema.json",
        "schema_version": 1,
        "manifest_status": "offline_candidate",
        "execution_mode": "offline_review_only",
        "release_eligible": False,
        "quality_claim_status": "prohibited",
        "required_attempt_count": 10,
        "retention_policy": "all_attempts_retained",
    }
    for field, expected in fixed.items():
        if not _same_scalar(manifest.get(field), expected):
            errors.append(f"benchmark.{field}")
    if not _valid_id(manifest.get("benchmark_id")):
        errors.append("benchmark.benchmark_id")
    if type(manifest.get("is_synthetic_fixture")) is not bool:
        errors.append("benchmark.is_synthetic_fixture")
    if not _valid_date(manifest.get("evaluated_on")):
        errors.append("benchmark.evaluated_on")
    if not _valid_sha256(manifest.get("generator_identity_sha256")):
        errors.append("benchmark.generator_identity_sha256")

    model = manifest.get("model")
    if not isinstance(model, dict) or set(model) != {"model_id", "model_version", "model_profile_sha256"}:
        errors.append("benchmark.model.fields")
    else:
        model_version = model.get("model_version")
        if not _valid_id(model.get("model_id")) or not isinstance(model_version, str) or not 1 <= len(model_version) <= 128:
            errors.append("benchmark.model.identity")
        _check_hash_fields(model, {"model_profile_sha256"}, errors, "benchmark.model")

    surface = manifest.get("surface")
    surface_fields = {"surface_id", "surface_version", "region", "surface_profile_sha256", "surface_av_policy_sha256"}
    if not isinstance(surface, dict) or set(surface) != surface_fields:
        errors.append("benchmark.surface.fields")
    else:
        if not all(_valid_id(surface.get(field)) for field in ("surface_id", "region")):
            errors.append("benchmark.surface.identity")
        surface_version = surface.get("surface_version")
        if not isinstance(surface_version, str) or not 1 <= len(surface_version) <= 128:
            errors.append("benchmark.surface.version")
        _check_hash_fields(surface, {"surface_profile_sha256", "surface_av_policy_sha256"}, errors, "benchmark.surface")

    operation = manifest.get("operation")
    operation_fields = {"operation_id", "operation_kind", "operation_contract_sha256"}
    operation_kinds = {
        "text_to_video",
        "image_to_video",
        "reference_to_video",
        "first_last_frame",
        "edit",
        "extend",
        "audio_video",
        "multi_shot",
    }
    if not isinstance(operation, dict) or set(operation) != operation_fields:
        errors.append("benchmark.operation.fields")
    else:
        if not _valid_id(operation.get("operation_id")) or not _string_in(operation.get("operation_kind"), operation_kinds):
            errors.append("benchmark.operation.identity")
        _check_hash_fields(operation, {"operation_contract_sha256"}, errors, "benchmark.operation")

    protocol = manifest.get("protocol")
    protocol_fields = {"benchmark_protocol_sha256", "rubric_sha256", "annotation_schema_sha256"}
    if not isinstance(protocol, dict) or set(protocol) != protocol_fields:
        errors.append("benchmark.protocol.fields")
    else:
        _check_hash_fields(protocol, protocol_fields, errors, "benchmark.protocol")
        if root is not None:
            schema_file = _safe_repo_file(root, "schemas/atomic-output-annotation-v1.schema.json")
            if schema_file is None or protocol.get("annotation_schema_sha256") != _raw_sha256(schema_file):
                errors.append("benchmark.protocol.annotation_schema_sha256_mismatch")

    condition = manifest.get("condition")
    condition_fields = {
        "condition_id",
        "variant_id",
        "condition_sha256",
        "semantic_program_sha256",
        "prompt_render_sha256",
        "input_manifest_sha256",
        "request_variance_policy",
        "observable_catalog",
    }
    if not isinstance(condition, dict) or set(condition) != condition_fields:
        errors.append("benchmark.condition.fields")
        condition = {}
    else:
        if not _valid_id(condition.get("condition_id")) or not _valid_id(condition.get("variant_id")):
            errors.append("benchmark.condition.identity")
        _check_hash_fields(
            condition,
            {"condition_sha256", "semantic_program_sha256", "prompt_render_sha256", "input_manifest_sha256"},
            errors,
            "benchmark.condition",
        )
        variance_policy = condition.get("request_variance_policy")
        variance_fields = {
            "request_template_sha256",
            "generation_settings_sha256",
            "allowed_varying_fields",
            "seed_policy",
            "seed_value",
        }
        if not isinstance(variance_policy, dict) or set(variance_policy) != variance_fields:
            errors.append("benchmark.condition.request_variance_policy.fields")
            variance_policy = {}
        else:
            _check_hash_fields(
                variance_policy,
                {"request_template_sha256", "generation_settings_sha256"},
                errors,
                "benchmark.condition.request_variance_policy",
            )
            if variance_policy.get("allowed_varying_fields") != ["attempt_id"]:
                errors.append("benchmark.condition.request_variance_policy.allowed_varying_fields")
            seed_policy = variance_policy.get("seed_policy")
            seed_value = variance_policy.get("seed_value")
            if not _string_in(seed_policy, {"not_requested", "fixed"}):
                errors.append("benchmark.condition.request_variance_policy.seed_policy")
            elif seed_policy == "not_requested" and seed_value is not None:
                errors.append("benchmark.condition.request_variance_policy.seed_value")
            elif seed_policy == "fixed" and (type(seed_value) is not int or not 0 <= seed_value <= 2_147_483_647):
                errors.append("benchmark.condition.request_variance_policy.seed_value")

        catalog = condition.get("observable_catalog")
        observable_ids: list[str] = []
        observable_dimensions: list[str] = []
        rubric_item_hashes: list[str] = []
        if not isinstance(catalog, list) or not 22 <= len(catalog) <= 64:
            errors.append("benchmark.condition.observable_catalog.shape")
            catalog = []
        for position, item in enumerate(catalog, start=1):
            prefix = f"benchmark.condition.observable_catalog.{position}"
            if not isinstance(item, dict) or set(item) != {
                "observable_id",
                "observable_dimension",
                "rubric_item_sha256",
            }:
                errors.append(f"{prefix}.fields")
                continue
            if not _valid_id(item.get("observable_id")):
                errors.append(f"{prefix}.observable_id")
            else:
                observable_ids.append(item["observable_id"])
            if not _string_in(item.get("observable_dimension"), REQUIRED_OBSERVABLES):
                errors.append(f"{prefix}.observable_dimension")
            else:
                observable_dimensions.append(item["observable_dimension"])
            if not _valid_sha256(item.get("rubric_item_sha256")):
                errors.append(f"{prefix}.rubric_item_sha256")
            else:
                rubric_item_hashes.append(item["rubric_item_sha256"])
        if len(observable_ids) != len(set(observable_ids)):
            errors.append("benchmark.condition.observable_catalog.duplicate_ids")
        if len(rubric_item_hashes) != len(set(rubric_item_hashes)):
            errors.append("benchmark.condition.observable_catalog.duplicate_rubric_items")
        if set(observable_dimensions) != REQUIRED_OBSERVABLES:
            errors.append("benchmark.condition.observable_catalog.dimension_coverage")

    attempts = manifest.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 10:
        errors.append("benchmark.attempts.count")
        attempts = []
    indices: list[int] = []
    attempt_ids: list[str] = []
    output_ids: list[str] = []
    generation_hashes: list[str] = []
    synthetic = manifest.get("is_synthetic_fixture") is True
    variance_policy = condition.get("request_variance_policy") if isinstance(condition.get("request_variance_policy"), dict) else {}
    for position, attempt in enumerate(attempts, start=1):
        prefix = f"benchmark.attempts.{position}"
        if not isinstance(attempt, dict) or set(attempt) != ATTEMPT_FIELDS:
            errors.append(f"{prefix}.fields")
            continue
        attempt_id = attempt.get("attempt_id")
        attempt_index = attempt.get("attempt_index")
        if not _valid_id(attempt_id):
            errors.append(f"{prefix}.attempt_id")
        else:
            attempt_ids.append(attempt_id)
        if type(attempt_index) is not int or not 1 <= attempt_index <= 10:
            errors.append(f"{prefix}.attempt_index")
        else:
            indices.append(attempt_index)
        if attempt.get("condition_id") != condition.get("condition_id"):
            errors.append(f"{prefix}.condition_id")
        _check_hash_fields(
            attempt,
            {
                "generation_record_sha256",
                "input_manifest_sha256",
                "request_sha256",
                "request_template_sha256",
                "generation_settings_sha256",
                "prompt_render_sha256",
            },
            errors,
            prefix,
        )
        if _valid_sha256(attempt.get("generation_record_sha256")):
            generation_hashes.append(attempt["generation_record_sha256"])
        if attempt.get("input_manifest_sha256") != condition.get("input_manifest_sha256"):
            errors.append(f"{prefix}.input_manifest_sha256_mismatch")
        if attempt.get("prompt_render_sha256") != condition.get("prompt_render_sha256"):
            errors.append(f"{prefix}.prompt_render_sha256_mismatch")
        if attempt.get("request_template_sha256") != variance_policy.get("request_template_sha256"):
            errors.append(f"{prefix}.request_template_sha256_mismatch")
        if attempt.get("generation_settings_sha256") != variance_policy.get("generation_settings_sha256"):
            errors.append(f"{prefix}.generation_settings_sha256_mismatch")
        seed_policy = variance_policy.get("seed_policy")
        if seed_policy == "not_requested":
            if attempt.get("requested_seed") is not None:
                errors.append(f"{prefix}.requested_seed")
        elif seed_policy == "fixed":
            if type(attempt.get("requested_seed")) is not int or attempt.get("requested_seed") != variance_policy.get("seed_value"):
                errors.append(f"{prefix}.requested_seed")
        if attempt.get("retained") is not True:
            errors.append(f"{prefix}.retained")
        status_value = attempt.get("attempt_status")
        allowed_status = {"synthetic_fixture"} if synthetic else {"returned", "failed"}
        if not _string_in(status_value, allowed_status):
            errors.append(f"{prefix}.attempt_status")
        if _string_in(status_value, {"synthetic_fixture", "returned"}):
            if not _valid_id(attempt.get("output_id")):
                errors.append(f"{prefix}.output_id")
            else:
                output_ids.append(attempt["output_id"])
            if not _valid_sha256(attempt.get("output_media_sha256")):
                errors.append(f"{prefix}.output_media_sha256")
            if attempt.get("media_kind") != "video":
                errors.append(f"{prefix}.media_kind")
            if not _valid_sha256(attempt.get("media_metadata_sha256")):
                errors.append(f"{prefix}.media_metadata_sha256")
            if type(attempt.get("duration_ms")) is not int or not 1 <= attempt["duration_ms"] <= 3_600_000:
                errors.append(f"{prefix}.duration_ms")
            if type(attempt.get("frame_count")) is not int or not 2 <= attempt["frame_count"] <= 10_000_000:
                errors.append(f"{prefix}.frame_count")
            if type(attempt.get("audio_present")) is not bool:
                errors.append(f"{prefix}.audio_present")
            if attempt.get("failure_record_sha256") is not None:
                errors.append(f"{prefix}.failure_record_sha256")
        elif status_value == "failed":
            failed_output_fields = (
                "output_id",
                "output_media_sha256",
                "media_kind",
                "media_metadata_sha256",
                "duration_ms",
                "frame_count",
                "audio_present",
            )
            if any(attempt.get(field) is not None for field in failed_output_fields):
                errors.append(f"{prefix}.failed_output")
            if not _valid_sha256(attempt.get("failure_record_sha256")):
                errors.append(f"{prefix}.failure_record_sha256")
    if sorted(indices) != list(range(1, 11)) or len(indices) != len(set(indices)):
        errors.append("benchmark.attempts.indices")
    for label, values in (
        ("attempt_ids", attempt_ids),
        ("output_ids", output_ids),
        ("generation_hashes", generation_hashes),
    ):
        if len(values) != len(set(values)):
            errors.append(f"benchmark.attempts.duplicate_{label}")

    reviewers = manifest.get("reviewers")
    reviewer_ids: list[str] = []
    reviewer_hashes: list[str] = []
    if not isinstance(reviewers, dict) or set(reviewers) != {"primary", "secondary", "adjudicator"}:
        errors.append("benchmark.reviewers.fields")
    else:
        reviewer_fields = {"reviewer_id", "reviewer_identity_sha256", "role", "identity_assurance", "generator_relation"}
        for role in ("primary", "secondary", "adjudicator"):
            reviewer = reviewers.get(role)
            prefix = f"benchmark.reviewers.{role}"
            if not isinstance(reviewer, dict) or set(reviewer) != reviewer_fields:
                errors.append(f"{prefix}.fields")
                continue
            if not _valid_id(reviewer.get("reviewer_id")):
                errors.append(f"{prefix}.reviewer_id")
            else:
                reviewer_ids.append(reviewer["reviewer_id"])
            if not _valid_sha256(reviewer.get("reviewer_identity_sha256")):
                errors.append(f"{prefix}.reviewer_identity_sha256")
            else:
                reviewer_hashes.append(reviewer["reviewer_identity_sha256"])
            if reviewer.get("role") != role:
                errors.append(f"{prefix}.role")
            if reviewer.get("identity_assurance") != "unauthenticated_declaration":
                errors.append(f"{prefix}.identity_assurance")
            if reviewer.get("generator_relation") != "declared_separate":
                errors.append(f"{prefix}.generator_relation")
    if len(reviewer_ids) != 3 or len(set(reviewer_ids)) != 3:
        errors.append("benchmark.reviewers.distinct_ids")
    if len(reviewer_hashes) != 3 or len(set(reviewer_hashes)) != 3:
        errors.append("benchmark.reviewers.distinct_hashes")
    if manifest.get("generator_identity_sha256") in reviewer_hashes:
        errors.append("benchmark.reviewers.generator_collision")

    expected_review_policy = {
        "primary_secondary_required": True,
        "adjudication_on_disagreement": True,
        "reviewer_ids_declared_distinct": True,
        "generator_reviewer_separation": "declared_separate",
        "independence_authentication": "not_established",
    }
    policy = manifest.get("review_policy")
    if not isinstance(policy, dict) or set(policy) != set(expected_review_policy) or any(
        not _same_scalar(policy.get(field), expected) for field, expected in expected_review_policy.items()
    ):
        errors.append("benchmark.review_policy")
    return sorted(set(errors))


def _validate_evidence_locus(
    locus: Any,
    attempt: dict[str, Any],
    *,
    temporal_decisive: bool,
    derived_final_frame: bool,
) -> tuple[list[str], str | None]:
    errors: list[str] = []
    if not isinstance(locus, dict) or not isinstance(locus.get("kind"), str):
        return ["annotation.evidence_locus.shape"], None
    kind = locus["kind"]
    expected_fields = {
        "video_time_range": {"kind", "start_ms", "end_ms"},
        "video_frame_range": {"kind", "start_frame", "end_frame"},
        "whole_video": {"kind"},
        "single_frame": {"kind", "frame_index"},
        "unavailable": {"kind"},
    }
    if kind not in expected_fields or set(locus) != expected_fields.get(kind, set()):
        return ["annotation.evidence_locus.fields"], kind
    if kind == "video_time_range":
        start, end = locus.get("start_ms"), locus.get("end_ms")
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            errors.append("annotation.evidence_locus.time_range")
        elif type(attempt.get("duration_ms")) is not int or end > attempt["duration_ms"]:
            errors.append("annotation.evidence_locus.time_range_bounds")
    elif kind == "video_frame_range":
        start, end = locus.get("start_frame"), locus.get("end_frame")
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            errors.append("annotation.evidence_locus.frame_range")
        elif type(attempt.get("frame_count")) is not int or end >= attempt["frame_count"]:
            errors.append("annotation.evidence_locus.frame_range_bounds")
        elif temporal_decisive and end <= start:
            errors.append("annotation.evidence_locus.temporal_frame_span")
    elif kind == "single_frame":
        frame = locus.get("frame_index")
        if type(frame) is not int or frame < 0:
            errors.append("annotation.evidence_locus.frame_index")
        elif type(attempt.get("frame_count")) is not int or frame >= attempt["frame_count"]:
            errors.append("annotation.evidence_locus.frame_index_bounds")
        elif derived_final_frame and frame != attempt["frame_count"] - 1:
            errors.append("annotation.evidence_locus.not_final_frame")
    return errors, kind


def validate_atomic_annotation(
    annotation: Any,
    manifest_snapshot: Any,
) -> list[str]:
    """Validate an annotation and its exact manifest/attempt/reviewer links."""
    errors: list[str] = []
    if not isinstance(annotation, dict):
        return ["annotation.shape"]
    if type(manifest_snapshot) is not JsonSnapshot:
        return ["annotation.manifest_snapshot"]
    manifest = manifest_snapshot.value
    if not isinstance(manifest, dict):
        return ["annotation.manifest_shape"]
    if set(annotation) != ANNOTATION_FIELDS:
        errors.append("annotation.fields")
    fixed = {
        "$schema": "https://github.com/Emily2040/seedance-2.0/schemas/atomic-output-annotation-v1.schema.json",
        "schema_version": 1,
        "claim_boundary": "observable_only_no_hidden_cause",
        "quality_claim_status": "prohibited",
        "release_eligible": False,
    }
    for field, expected in fixed.items():
        if not _same_scalar(annotation.get(field), expected):
            errors.append(f"annotation.{field}")
    for field in (
        "annotation_id",
        "benchmark_id",
        "condition_id",
        "attempt_id",
        "output_id",
        "observable_id",
        "observable_dimension",
    ):
        if not _valid_id(annotation.get(field)):
            errors.append(f"annotation.{field}")
    _check_hash_fields(
        annotation,
        {
            "benchmark_manifest_sha256",
            "condition_sha256",
            "generation_record_sha256",
            "rubric_sha256",
            "rubric_item_sha256",
            "output_media_sha256",
            "evidence_asset_sha256",
            "evidence_parent_output_sha256",
        },
        errors,
        "annotation",
    )
    if type(annotation.get("attempt_index")) is not int or not 1 <= annotation["attempt_index"] <= 10:
        errors.append("annotation.attempt_index")
    if type(annotation.get("is_synthetic_fixture")) is not bool:
        errors.append("annotation.is_synthetic_fixture")
    derivation_record = annotation.get("derivation_record_sha256")
    if derivation_record is not None and not _valid_sha256(derivation_record):
        errors.append("annotation.derivation_record_sha256")
    if annotation.get("benchmark_manifest_sha256") != manifest_snapshot.sha256:
        errors.append("annotation.benchmark_manifest_sha256_mismatch")
    if annotation.get("benchmark_id") != manifest.get("benchmark_id"):
        errors.append("annotation.benchmark_id_mismatch")
    condition = manifest.get("condition") if isinstance(manifest.get("condition"), dict) else {}
    if annotation.get("condition_id") != condition.get("condition_id"):
        errors.append("annotation.condition_id_mismatch")
    if annotation.get("condition_sha256") != condition.get("condition_sha256"):
        errors.append("annotation.condition_sha256_mismatch")
    protocol = manifest.get("protocol") if isinstance(manifest.get("protocol"), dict) else {}
    if annotation.get("rubric_sha256") != protocol.get("rubric_sha256"):
        errors.append("annotation.rubric_sha256_mismatch")
    if annotation.get("is_synthetic_fixture") is not manifest.get("is_synthetic_fixture"):
        errors.append("annotation.synthetic_status_mismatch")

    attempts = manifest.get("attempts") if isinstance(manifest.get("attempts"), list) else []
    matching_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get("attempt_id") == annotation.get("attempt_id")
        and attempt.get("attempt_index") == annotation.get("attempt_index")
    ]
    if len(matching_attempts) != 1:
        errors.append("annotation.attempt_link")
        attempt: dict[str, Any] = {}
    else:
        attempt = matching_attempts[0]
    if not _string_in(attempt.get("attempt_status"), {"synthetic_fixture", "returned"}):
        errors.append("annotation.attempt_not_reviewable")
    for annotation_field, attempt_field in (
        ("generation_record_sha256", "generation_record_sha256"),
        ("output_id", "output_id"),
        ("output_media_sha256", "output_media_sha256"),
    ):
        if annotation.get(annotation_field) != attempt.get(attempt_field):
            errors.append(f"annotation.{annotation_field}_mismatch")

    dimension = annotation.get("observable_dimension")
    if not _string_in(dimension, REQUIRED_OBSERVABLES):
        errors.append("annotation.observable_dimension_unknown")
    catalog = condition.get("observable_catalog") if isinstance(condition.get("observable_catalog"), list) else []
    matching_catalog = [
        item
        for item in catalog
        if isinstance(item, dict) and item.get("observable_id") == annotation.get("observable_id")
    ]
    if len(matching_catalog) != 1:
        errors.append("annotation.observable_not_preregistered")
        catalog_item: dict[str, Any] = {}
    else:
        catalog_item = matching_catalog[0]
    if annotation.get("observable_dimension") != catalog_item.get("observable_dimension"):
        errors.append("annotation.observable_dimension_mismatch")
    if annotation.get("rubric_item_sha256") != catalog_item.get("rubric_item_sha256"):
        errors.append("annotation.rubric_item_sha256_mismatch")

    evidence_kind = annotation.get("evidence_asset_kind")
    output_hash = attempt.get("output_media_sha256")
    if annotation.get("evidence_parent_output_sha256") != output_hash:
        errors.append("annotation.evidence_parent_output_sha256_mismatch")
    if evidence_kind == "returned_video":
        if annotation.get("evidence_asset_sha256") != output_hash:
            errors.append("annotation.evidence_asset_sha256_mismatch")
        if derivation_record is not None:
            errors.append("annotation.returned_video_derivation")
    elif evidence_kind == "derived_final_frame":
        if not _valid_sha256(derivation_record):
            errors.append("annotation.derived_frame_derivation")
        if annotation.get("evidence_asset_sha256") == output_hash:
            errors.append("annotation.derived_frame_asset_not_distinct")
    else:
        errors.append("annotation.evidence_asset_kind")

    status_value = annotation.get("status")
    confidence = annotation.get("confidence")
    if not _string_in(status_value, {"pass", "fail", "unknown", "not_applicable"}):
        errors.append("annotation.status")
    if not _string_in(confidence, {"low", "medium", "high", "unknown"}):
        errors.append("annotation.confidence")
    decisive = _string_in(status_value, {"pass", "fail"})
    temporal_decisive = decisive and _string_in(dimension, TEMPORAL_OBSERVABLES)
    locus_errors, locus_kind = _validate_evidence_locus(
        annotation.get("evidence_locus"),
        attempt,
        temporal_decisive=temporal_decisive,
        derived_final_frame=evidence_kind == "derived_final_frame",
    )
    errors.extend(locus_errors)
    if decisive and (not _string_in(confidence, {"low", "medium", "high"}) or locus_kind == "unavailable"):
        errors.append("annotation.decisive_evidence")
    if _string_in(status_value, {"unknown", "not_applicable"}) and (
        confidence != "unknown" or locus_kind != "unavailable"
    ):
        errors.append("annotation.uncertain_evidence")
    video_loci = {"video_time_range", "video_frame_range", "whole_video"}
    if temporal_decisive:
        if evidence_kind != "returned_video" or not _string_in(locus_kind, video_loci):
            errors.append("annotation.temporal_requires_video")
        if type(attempt.get("frame_count")) is not int or attempt.get("frame_count") < 2:
            errors.append("annotation.temporal_requires_multiframe_video")
    if evidence_kind == "derived_final_frame" and not _string_in(locus_kind, {"single_frame", "unavailable"}):
        errors.append("annotation.final_frame_locus")
    if decisive and _string_in(dimension, AUDIO_OBSERVABLES) and attempt.get("audio_present") is not True:
        errors.append("annotation.audio_observable_requires_audio")
    if status_value == "pass" and _string_in(dimension, WHOLE_VIDEO_PASS_OBSERVABLES):
        if evidence_kind != "returned_video" or locus_kind != "whole_video":
            errors.append("annotation.global_pass_requires_whole_video")
    if dimension == "overall_usable_take" and decisive:
        if evidence_kind != "returned_video" or locus_kind != "whole_video":
            errors.append("annotation.usability_requires_whole_video")

    reviewer = annotation.get("reviewer")
    reviewer_fields = {
        "reviewer_id",
        "reviewer_identity_sha256",
        "role",
        "identity_assurance",
        "generator_relation",
        "reviewed_on",
        "review_method",
    }
    if not isinstance(reviewer, dict) or set(reviewer) != reviewer_fields:
        errors.append("annotation.reviewer.fields")
    else:
        role = reviewer.get("role")
        if not _string_in(role, {"primary", "secondary", "adjudicator"}):
            errors.append("annotation.reviewer.role")
        manifest_reviewers = manifest.get("reviewers") if isinstance(manifest.get("reviewers"), dict) else {}
        manifest_reviewer = manifest_reviewers.get(role) if isinstance(role, str) else None
        manifest_reviewer = manifest_reviewer if isinstance(manifest_reviewer, dict) else {}
        if reviewer.get("reviewer_id") != manifest_reviewer.get("reviewer_id"):
            errors.append("annotation.reviewer.id_mismatch")
        if reviewer.get("reviewer_identity_sha256") != manifest_reviewer.get("reviewer_identity_sha256"):
            errors.append("annotation.reviewer.hash_mismatch")
        if reviewer.get("reviewer_identity_sha256") == manifest.get("generator_identity_sha256"):
            errors.append("annotation.reviewer.generator_collision")
        if reviewer.get("identity_assurance") != "unauthenticated_declaration":
            errors.append("annotation.reviewer.identity_assurance")
        if reviewer.get("generator_relation") != "declared_separate":
            errors.append("annotation.reviewer.generator_relation")
        if not _valid_date(reviewer.get("reviewed_on")):
            errors.append("annotation.reviewer.reviewed_on")
        if reviewer.get("review_method") != "human_observation":
            errors.append("annotation.reviewer.review_method")
    return sorted(set(errors))


def _program_mutations(program: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mutations: dict[str, Callable[[dict[str, Any]], None]] = {
        "network_enable": lambda value: value.__setitem__("network_policy", "allowed"),
        "release_enable": lambda value: value.__setitem__("release_gate", True),
        "quality_claim_enable": lambda value: value.__setitem__("quality_claims_allowed", True),
        "held_out_enable": lambda value: value["public_corpora"].__setitem__("held_out_execution", "enabled"),
        "drop_suite": lambda value: value["deterministic_suites"].pop(),
        "unknown_entrypoint": lambda value: value["deterministic_suites"][0]["entrypoints"].__setitem__(0, "scripts/unknown.py"),
        "duplicate_suite": lambda value: value["deterministic_suites"].append(copy.deepcopy(value["deterministic_suites"][0])),
        "weaken_threshold": lambda value: value["mutation_campaigns"][0].__setitem__("minimum_detection_rate", 0.5),
        "drop_metamorphic_relation": lambda value: value["metamorphic_relations"].pop(),
        "model_relation_as_offline": lambda value: next(
            item for item in value["metamorphic_relations"] if item["relation_id"] == "irrelevant_style_preserves_operation"
        ).__setitem__("execution", "offline_deterministic"),
        "reduce_attempt_count": lambda value: value["output_review_policy"].__setitem__("minimum_attempts_per_condition", 9),
        "allow_dropped_attempts": lambda value: value["output_review_policy"].__setitem__("retain_all_attempts", False),
    }
    result: dict[str, dict[str, Any]] = {}
    for mutation_id, mutate in mutations.items():
        candidate = copy.deepcopy(program)
        mutate(candidate)
        result[mutation_id] = candidate
    return result


def run_program_mutations(program: dict[str, Any], root: Path) -> tuple[int, int, list[str]]:
    failures: list[str] = []
    mutations = _program_mutations(program)
    for mutation_id in sorted(PROGRAM_MUTATIONS):
        candidate = mutations[mutation_id]
        if not validate_program(candidate, root, check_oracles=False):
            failures.append(mutation_id)
    return len(mutations) - len(failures), len(mutations), failures


def _output_review_mutations(
    annotation: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    result: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    def candidate() -> tuple[dict[str, Any], dict[str, Any]]:
        return copy.deepcopy(annotation), copy.deepcopy(manifest)

    item, benchmark = candidate()
    item["release_eligible"] = True
    result["release_enable"] = (item, benchmark)

    item, benchmark = candidate()
    item["quality_claim_status"] = "permitted"
    result["quality_claim_enable"] = (item, benchmark)

    item, benchmark = candidate()
    item["reviewer"]["reviewer_identity_sha256"] = benchmark["generator_identity_sha256"]
    result["generator_reviewer_collision"] = (item, benchmark)

    item, benchmark = candidate()
    item["reviewer"]["generator_relation"] = "same_actor"
    result["false_independence"] = (item, benchmark)

    item, benchmark = candidate()
    item["output_media_sha256"] = "f" * 64
    result["media_hash_mismatch"] = (item, benchmark)

    item, benchmark = candidate()
    item["benchmark_manifest_sha256"] = "f" * 64
    result["manifest_digest_mismatch"] = (item, benchmark)

    item, benchmark = candidate()
    item["observable_id"] = "unknown_observable"
    item["observable_dimension"] = "unknown_observable"
    result["unknown_observable"] = (item, benchmark)

    item, benchmark = candidate()
    item["rubric_item_sha256"] = "f" * 64
    result["rubric_item_mismatch"] = (item, benchmark)

    item, benchmark = candidate()
    item["evidence_parent_output_sha256"] = "f" * 64
    result["evidence_parent_mismatch"] = (item, benchmark)

    item, benchmark = candidate()
    item.update({
        "evidence_asset_kind": "derived_final_frame",
        "evidence_asset_sha256": "f" * 64,
        "derivation_record_sha256": None,
        "evidence_locus": {"kind": "single_frame", "frame_index": benchmark["attempts"][0]["frame_count"] - 1},
    })
    result["derived_without_record"] = (item, benchmark)

    item, benchmark = candidate()
    item.update({
        "evidence_asset_kind": "derived_final_frame",
        "evidence_asset_sha256": "f" * 64,
        "derivation_record_sha256": "e" * 64,
        "evidence_locus": {"kind": "single_frame", "frame_index": benchmark["attempts"][0]["frame_count"] - 1},
    })
    result["temporal_still_pass"] = (item, benchmark)

    item, benchmark = candidate()
    item["evidence_locus"] = {"kind": "metadata"}
    result["temporal_metadata_pass"] = (item, benchmark)

    item, benchmark = candidate()
    item["evidence_locus"] = {"kind": "single_frame", "frame_index": 0}
    result["temporal_single_frame_pass"] = (item, benchmark)

    item, benchmark = candidate()
    item["evidence_locus"] = {
        "kind": "video_time_range",
        "start_ms": 0,
        "end_ms": benchmark["attempts"][0]["duration_ms"] + 1,
    }
    result["time_range_out_of_bounds"] = (item, benchmark)

    item, benchmark = candidate()
    item["evidence_locus"] = {
        "kind": "video_frame_range",
        "start_frame": 0,
        "end_frame": benchmark["attempts"][0]["frame_count"],
    }
    result["frame_range_out_of_bounds"] = (item, benchmark)

    item, benchmark = candidate()
    benchmark["attempts"][0]["audio_present"] = False
    result["audio_absent_pass"] = (item, benchmark)

    item, benchmark = candidate()
    global_item = next(
        entry
        for entry in benchmark["condition"]["observable_catalog"]
        if entry["observable_dimension"] == "operation_correctness"
    )
    item.update({
        "observable_id": global_item["observable_id"],
        "observable_dimension": global_item["observable_dimension"],
        "rubric_item_sha256": global_item["rubric_item_sha256"],
        "evidence_locus": {"kind": "video_time_range", "start_ms": 0, "end_ms": 1000},
    })
    result["whole_output_partial_pass"] = (item, benchmark)

    item, benchmark = candidate()
    item["claim_boundary"] = "hidden_architecture_cause"
    result["hidden_cause_claim"] = (item, benchmark)

    item, benchmark = candidate()
    del item["evidence_locus"]
    result["missing_evidence_locus"] = (item, benchmark)

    item, benchmark = candidate()
    item["confidence"] = "certain"
    result["invalid_confidence"] = (item, benchmark)

    item, benchmark = candidate()
    item["review_notes"] = "extra"
    result["extra_field"] = (item, benchmark)
    return result


def run_output_review_mutations(
    annotation: dict[str, Any],
    manifest_snapshot: JsonSnapshot,
) -> tuple[int, int, list[str]]:
    failures: list[str] = []
    if type(manifest_snapshot) is not JsonSnapshot or not isinstance(manifest_snapshot.value, dict):
        return 0, len(OUTPUT_REVIEW_MUTATIONS), ["manifest_snapshot"]
    manifest = manifest_snapshot.value
    mutations = _output_review_mutations(annotation, manifest)
    if set(mutations) != OUTPUT_REVIEW_MUTATIONS:
        return 0, len(OUTPUT_REVIEW_MUTATIONS), ["mutation_corpus_mismatch"]
    for mutation_id in sorted(OUTPUT_REVIEW_MUTATIONS):
        candidate, benchmark = mutations[mutation_id]
        candidate_snapshot = snapshot_from_value(benchmark)
        if mutation_id != "manifest_digest_mismatch":
            candidate["benchmark_manifest_sha256"] = candidate_snapshot.sha256
        annotation_errors = validate_atomic_annotation(candidate, candidate_snapshot)
        benchmark_errors = validate_benchmark_manifest(benchmark)
        if not annotation_errors and not benchmark_errors:
            failures.append(mutation_id)
    return len(mutations) - len(failures), len(mutations), failures


def aggregate_output_reviews(
    manifest_snapshot: JsonSnapshot,
    annotations: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Aggregate complete double review without averaging away failures."""
    if not isinstance(annotations, list):
        return {
            "benchmark_manifest_sha256": (
                manifest_snapshot.sha256 if type(manifest_snapshot) is JsonSnapshot else None
            ),
            "annotation_set_sha256": _annotation_set_sha256(annotations),
            "release_pass": False,
            "quality_claims_allowed": False,
            "condition_verdict": "incomplete",
        }, ["aggregate.annotations_shape"]
    if type(manifest_snapshot) is not JsonSnapshot or not isinstance(manifest_snapshot.value, dict):
        return {
            "benchmark_manifest_sha256": None,
            "annotation_set_sha256": _annotation_set_sha256(annotations),
            "release_pass": False,
            "quality_claims_allowed": False,
            "condition_verdict": "incomplete",
        }, ["aggregate.manifest_snapshot"]
    manifest = manifest_snapshot.value
    errors = validate_benchmark_manifest(manifest)
    condition = manifest.get("condition") if isinstance(manifest.get("condition"), dict) else {}
    catalog = condition.get("observable_catalog") if isinstance(condition.get("observable_catalog"), list) else []
    catalog = [item for item in catalog if isinstance(item, dict)]
    catalog_ids = [item.get("observable_id") for item in catalog if isinstance(item.get("observable_id"), str)]
    catalog_dimensions = {
        item.get("observable_dimension")
        for item in catalog
        if isinstance(item.get("observable_dimension"), str)
    }
    attempts = manifest.get("attempts") if isinstance(manifest.get("attempts"), list) else []
    returned_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and _string_in(attempt.get("attempt_status"), {"synthetic_fixture", "returned"})
    ]
    reviewable_attempts = [
        attempt for attempt in returned_attempts if isinstance(attempt.get("attempt_id"), str)
    ]
    failed_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("attempt_status") == "failed"
    ]
    cells: dict[tuple[str, str, str], dict[str, Any]] = {}
    valid_annotations: list[dict[str, Any]] = []
    for annotation in annotations:
        annotation_errors = validate_atomic_annotation(annotation, manifest_snapshot)
        if annotation_errors:
            errors.append("aggregate.invalid_annotation")
            continue
        valid_annotations.append(annotation)

    id_groups: dict[str, list[dict[str, Any]]] = {}
    for annotation in valid_annotations:
        id_groups.setdefault(annotation["annotation_id"], []).append(annotation)
    unique_id_annotations: list[dict[str, Any]] = []
    for group in id_groups.values():
        if len(group) != 1:
            errors.append("aggregate.duplicate_annotation_id")
        else:
            unique_id_annotations.append(group[0])

    cell_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for annotation in unique_id_annotations:
        key = (annotation["attempt_id"], annotation["observable_id"], annotation["reviewer"]["role"])
        cell_groups.setdefault(key, []).append(annotation)
    for key, group in cell_groups.items():
        if len(group) != 1:
            errors.append("aggregate.duplicate_review_cell")
        else:
            cells[key] = group[0]

    resolved: list[tuple[str, str]] = []
    disagreement_count = 0
    confidence_rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    for attempt in reviewable_attempts:
        attempt_id = attempt.get("attempt_id")
        for observable_id in catalog_ids:
            primary = cells.get((attempt_id, observable_id, "primary"))
            secondary = cells.get((attempt_id, observable_id, "secondary"))
            if primary is None or secondary is None:
                errors.append("aggregate.missing_primary_or_secondary")
                continue
            if primary["status"] == secondary["status"]:
                if (attempt_id, observable_id, "adjudicator") in cells:
                    errors.append("aggregate.unneeded_adjudication")
                confidence = min(
                    (primary["confidence"], secondary["confidence"]),
                    key=lambda value: confidence_rank[value],
                )
                resolved.append((primary["status"], confidence))
                continue
            disagreement_count += 1
            adjudicator = cells.get((attempt_id, observable_id, "adjudicator"))
            if adjudicator is None:
                errors.append("aggregate.missing_adjudication")
                continue
            resolved.append((adjudicator["status"], adjudicator["confidence"]))

    expected_attempt_ids = {attempt["attempt_id"] for attempt in reviewable_attempts}
    expected_observable_ids = set(catalog_ids)
    for attempt_id, observable_id, role in cells:
        if (
            attempt_id not in expected_attempt_ids
            or observable_id not in expected_observable_ids
            or not _string_in(role, {"primary", "secondary", "adjudicator"})
        ):
            errors.append("aggregate.unexpected_review_cell")

    status_counts = {
        status_value: sum(status == status_value for status, _ in resolved)
        for status_value in ("pass", "fail", "unknown", "not_applicable")
    }
    confidence_counts = {
        confidence: sum(resolved_confidence == confidence for _, resolved_confidence in resolved)
        for confidence in ("low", "medium", "high", "unknown")
    }
    annotation_confidence_counts = {
        confidence: sum(annotation.get("confidence") == confidence for annotation in valid_annotations)
        for confidence in ("low", "medium", "high", "unknown")
    }
    if failed_attempts or status_counts["fail"]:
        condition_verdict = "fail"
    elif errors or status_counts["unknown"] or status_counts["not_applicable"]:
        condition_verdict = "incomplete"
    else:
        condition_verdict = "pass"
    report = {
        "benchmark_id": manifest.get("benchmark_id"),
        "condition_id": condition.get("condition_id"),
        "benchmark_manifest_sha256": manifest_snapshot.sha256,
        "annotation_set_sha256": _annotation_set_sha256(annotations),
        "evidence_class": "synthetic_contract_fixture" if manifest.get("is_synthetic_fixture") is True else "offline_output_review",
        "attempt_count": len(attempts),
        "retained_attempt_count": sum(
            isinstance(attempt, dict) and attempt.get("retained") is True for attempt in attempts
        ),
        "failed_generation_attempt_count": len(failed_attempts),
        "observable_catalog_item_count": len(catalog_ids),
        "observable_dimension_count": len(catalog_dimensions),
        "resolved_review_cell_count": len(resolved),
        "disagreement_count": disagreement_count,
        "status_counts": status_counts,
        "confidence_counts": confidence_counts,
        "annotation_confidence_counts": annotation_confidence_counts,
        "condition_verdict": condition_verdict,
        "release_pass": False,
        "quality_claims_allowed": False,
    }
    return report, sorted(set(errors))


def _annotation_set_sha256(annotations: Any) -> str:
    """Order-invariant digest of exact canonical annotation records."""
    records = annotations if isinstance(annotations, list) else []
    encoded: list[bytes] = []
    for record in records:
        try:
            encoded.append(_canonical_json_bytes(record))
        except (TypeError, ValueError):
            encoded.append(b"null")
    payload = b"[" + b",".join(sorted(encoded)) + b"]"
    return hashlib.sha256(payload).hexdigest()


def synthetic_annotation_matrix(
    template: dict[str, Any],
    manifest_snapshot: JsonSnapshot,
) -> list[dict[str, Any]]:
    """Build in-memory contract probes; these are never model-output evidence."""
    if type(manifest_snapshot) is not JsonSnapshot or not isinstance(manifest_snapshot.value, dict):
        return []
    manifest = manifest_snapshot.value
    annotations: list[dict[str, Any]] = []
    catalog = manifest["condition"]["observable_catalog"]
    for attempt in manifest["attempts"]:
        if not _string_in(attempt.get("attempt_status"), {"synthetic_fixture", "returned"}):
            continue
        for catalog_index, catalog_item in enumerate(catalog, start=1):
            for role in ("primary", "secondary"):
                annotation = copy.deepcopy(template)
                annotation.update({
                    "annotation_id": f"ann_{attempt['attempt_index']:02d}_{catalog_index:03d}_{role}",
                    "attempt_id": attempt["attempt_id"],
                    "attempt_index": attempt["attempt_index"],
                    "benchmark_manifest_sha256": manifest_snapshot.sha256,
                    "generation_record_sha256": attempt["generation_record_sha256"],
                    "output_id": attempt["output_id"],
                    "output_media_sha256": attempt["output_media_sha256"],
                    "evidence_asset_kind": "returned_video",
                    "evidence_asset_sha256": attempt["output_media_sha256"],
                    "evidence_parent_output_sha256": attempt["output_media_sha256"],
                    "derivation_record_sha256": None,
                    "observable_id": catalog_item["observable_id"],
                    "observable_dimension": catalog_item["observable_dimension"],
                    "rubric_item_sha256": catalog_item["rubric_item_sha256"],
                    "status": "pass",
                    "evidence_locus": {"kind": "whole_video"},
                    "confidence": "high",
                })
                reviewer = manifest["reviewers"][role]
                annotation["reviewer"] = {
                    **copy.deepcopy(reviewer),
                    "reviewed_on": manifest["evaluated_on"],
                    "review_method": "human_observation",
                }
                annotations.append(annotation)
    return annotations


def run_aggregation_probes(
    annotation: dict[str, Any],
    manifest_snapshot: JsonSnapshot,
) -> list[str]:
    failures: list[str] = []
    complete = synthetic_annotation_matrix(annotation, manifest_snapshot)
    report, errors = aggregate_output_reviews(manifest_snapshot, complete)
    if errors or report["condition_verdict"] != "pass" or report["release_pass"] is not False:
        failures.append("complete_matrix")

    reordered = list(reversed(complete))
    reordered_report, reordered_errors = aggregate_output_reviews(manifest_snapshot, reordered)
    if reordered_errors or reordered_report != report:
        failures.append("row_order_invariance")

    missing_report, missing_errors = aggregate_output_reviews(manifest_snapshot, complete[:-1])
    if not missing_errors or missing_report["condition_verdict"] != "incomplete":
        failures.append("missing_review_failure")

    failed = copy.deepcopy(complete)
    failed[0]["status"] = "fail"
    failed[1]["status"] = "fail"
    failed_report, failed_errors = aggregate_output_reviews(manifest_snapshot, failed)
    if failed_errors or failed_report["condition_verdict"] != "fail" or failed_report["status_counts"]["fail"] != 1:
        failures.append("failure_first_aggregation")
    return failures


def summary(
    program: dict[str, Any],
    program_mutation_result: tuple[int, int, list[str]] | None = None,
    output_mutation_result: tuple[int, int, list[str]] | None = None,
    aggregation_probe_count: int | None = None,
) -> dict[str, Any]:
    relations = program["metamorphic_relations"]
    result: dict[str, Any] = {
        "program_id": program["program_id"],
        "status": "candidate_non_release",
        "network_calls": 0,
        "release_gate": False,
        "quality_claims_allowed": False,
        "deterministic_suite_count": len(program["deterministic_suites"]),
        "metamorphic_relation_count": len(relations),
        "offline_metamorphic_relation_count": sum(item["execution"] == "offline_deterministic" for item in relations),
        "development_model_relation_count": sum(item["execution"] == "development_model_only" for item in relations),
        "required_observable_count": len(program["output_review_policy"]["required_observables"]),
        "minimum_attempts_per_condition": program["output_review_policy"]["minimum_attempts_per_condition"],
    }
    if program_mutation_result is not None:
        detected, total, failures = program_mutation_result
        result["program_mutations"] = {
            "detected": detected,
            "total": total,
            "detection_rate": detected / total,
            "undetected": failures,
        }
    if output_mutation_result is not None:
        detected, total, failures = output_mutation_result
        result["output_review_mutations"] = {
            "detected": detected,
            "total": total,
            "detection_rate": detected / total,
            "undetected": failures,
        }
    if aggregation_probe_count is not None:
        result["aggregation_probes_passed"] = aggregation_probe_count
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public V7-10 offline evaluation programme.")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--self-test", action="store_true", help="also execute the bounded mutation corpus")
    parser.add_argument("--json", action="store_true", help="emit the non-release coverage summary as canonical JSON")
    parser.add_argument("--review-benchmark", help="validate and aggregate one benchmark manifest")
    parser.add_argument("--review-annotations", help="JSON array of atomic annotations for --review-benchmark")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    if bool(args.review_benchmark) != bool(args.review_annotations):
        parser.error("--review-benchmark and --review-annotations are required together")
    if args.review_benchmark:
        try:
            benchmark_snapshot = strict_load_snapshot(Path(args.review_benchmark).expanduser())
            annotation_rows = strict_load_snapshot(Path(args.review_annotations).expanduser()).value
            if not isinstance(annotation_rows, list) or len(annotation_rows) > 1_920:
                raise ValueError("review annotations must be an array of at most 1920 records")
            report, review_errors = aggregate_output_reviews(benchmark_snapshot, annotation_rows)
            review_errors.extend(validate_benchmark_manifest(benchmark_snapshot.value, root))
            review_errors = sorted(set(review_errors))
            if review_errors and report.get("condition_verdict") != "fail":
                report["condition_verdict"] = "incomplete"
            report["validation_errors"] = review_errors
            print(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
            return 1 if review_errors else 0
        except (OSError, UnicodeError, ValueError) as exc:
            print(json.dumps({
                "condition_verdict": "incomplete",
                "quality_claims_allowed": False,
                "release_pass": False,
                "validation_errors": [f"review_input:{exc}"],
            }, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
            return 1
    try:
        program_file = _safe_repo_file(root, PROGRAM_PATH.as_posix())
        benchmark_file = _safe_repo_file(root, BENCHMARK_PATH.as_posix())
        annotation_file = _safe_repo_file(root, ANNOTATION_PATH.as_posix())
        if program_file is None or benchmark_file is None or annotation_file is None:
            raise ValueError("evaluation contract path is absent or unsafe")
        program = strict_load_json(program_file)
        benchmark_snapshot = strict_load_snapshot(benchmark_file)
        benchmark = benchmark_snapshot.value
        annotation = strict_load_json(annotation_file)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Evaluation programme error: {exc}")
        return 1
    errors = validate_program(program, root)
    errors.extend(validate_benchmark_manifest(benchmark, root))
    errors.extend(validate_atomic_annotation(annotation, benchmark_snapshot))
    if errors:
        print("Evaluation programme errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    program_mutation_result = None
    output_mutation_result = None
    aggregation_probe_count = None
    if args.self_test:
        program_mutation_result = run_program_mutations(program, root)
        output_mutation_result = run_output_review_mutations(annotation, benchmark_snapshot)
        for campaign_id, mutation_result in (
            ("evaluation_program_contract", program_mutation_result),
            ("output_review_contract", output_mutation_result),
        ):
            detected, total, failures = mutation_result
            threshold = next(
                item["minimum_detection_rate"]
                for item in program["mutation_campaigns"]
                if item["campaign_id"] == campaign_id
            )
            if failures or detected / total < threshold:
                print("Evaluation programme mutation errors:")
                for mutation_id in failures:
                    print(f"- {campaign_id}.undetected.{mutation_id}")
                return 1
        aggregation_failures = run_aggregation_probes(annotation, benchmark_snapshot)
        if aggregation_failures:
            print("Evaluation aggregation probe errors:")
            for probe_id in aggregation_failures:
                print(f"- {probe_id}")
            return 1
        aggregation_probe_count = 4
    report = summary(program, program_mutation_result, output_mutation_result, aggregation_probe_count)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    else:
        suffix = ""
        if program_mutation_result is not None and output_mutation_result is not None:
            detected = program_mutation_result[0] + output_mutation_result[0]
            total = program_mutation_result[1] + output_mutation_result[1]
            suffix = f"; mutations {detected}/{total} detected"
        print(
            "Evaluation programme passed: "
            f"{report['deterministic_suite_count']} deterministic suites, "
            f"{report['metamorphic_relation_count']} metamorphic relations, "
            f"{report['required_observable_count']} output observables{suffix}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
