#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_CLAIM_SCHEMA = HERE / "evidence-claim.schema.json"
DEFAULT_SOURCE_SCHEMA = HERE / "evidence-source.schema.json"
DEFAULT_CLAIMS = HERE / "claims"
DEFAULT_SOURCES = HERE / "sources"

TTL_LIMITS = {
    "pricing": 1,
    "model_id": 1,
    "api_field": 7,
    "prompt_grammar": 30,
    "model_capability": 180,
    "workflow": 60,
    "official_example": 30,
    "release_watchlist": 7,
    "community_pattern": 30,
}

AUTHORITY_HOSTS = {
    ("first_party_platform_doc", "BytePlus"): {"docs.byteplus.com"},
    ("first_party_platform_doc", "Volcengine"): {"docs.volcengine.com", "www.volcengine.com"},
    ("first_party_model_doc", "ByteDance"): {"seed.bytedance.com"},
    ("provider_owned_doc", "fal"): {"fal.ai", "www.fal.ai"},
}

CLAIM_SOURCE_TYPES = {
    "pricing": {"first_party_platform_doc", "provider_owned_doc"},
    "model_id": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "api_field": {"first_party_platform_doc", "provider_owned_doc"},
    "prompt_grammar": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "model_capability": {"first_party_model_doc", "first_party_platform_doc"},
    "workflow": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "official_example": {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"},
    "release_watchlist": {"first_party_model_doc", "first_party_platform_doc"},
    "community_pattern": {"community_source", "research_paper"},
}

RUNTIME_SOURCE_TYPES = {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"}
NON_RUNTIME_CLASSES = {"community_pattern", "release_watchlist"}
RELATION_INVERSES = {
    "supports": "supported_by",
    "supported_by": "supports",
    "qualifies": "qualified_by",
    "qualified_by": "qualifies",
    "tension_with": "tension_with",
}
SCOPE_WILDCARDS = {"*", "all", "any", "global", "multilingual", "prompting", "unspecified"}

SURFACE_PREFIXES = {
    "docs.byteplus.com": "byteplus.",
    "docs.volcengine.com": "volcengine.",
    "www.volcengine.com": "volcengine.",
    "fal.ai": "fal.",
    "www.fal.ai": "fal.",
}

SUCCESSFUL_RETRIEVALS = {"fetched", "browser_verified"}
NON_RUNTIME_SUPPORT = {"unverified", "retracted"}
NON_RUNTIME_LIFECYCLE = {"expired", "superseded"}


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def sha256_text(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_model_generation(value: str) -> tuple[int, int] | None:
    normalized = re.sub(r"[^a-z0-9]+", ".", value.casefold()).strip(".")
    match = re.search(r"(?:^|\.)(?:v)?(\d+)\.(\d+)(?:\.|$)", normalized)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def values_overlap(left: list[str], right: list[str]) -> bool:
    left_values = set(left)
    right_values = set(right)
    return (
        not left_values
        or not right_values
        or bool(left_values & right_values)
        or bool(left_values & SCOPE_WILDCARDS)
        or bool(right_values & SCOPE_WILDCARDS)
    )


def scalar_overlap(left: str, right: str) -> bool:
    return left == right or left in SCOPE_WILDCARDS or right in SCOPE_WILDCARDS


def scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        values_overlap(left.get("surfaces", []), right.get("surfaces", []))
        and values_overlap(left.get("tasks", []), right.get("tasks", []))
        and scalar_overlap(left.get("locale", "unspecified"), right.get("locale", "unspecified"))
        and scalar_overlap(left.get("region", "unspecified"), right.get("region", "unspecified"))
    )


def parse_date(value: str, label: str, errors: list[str]) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: invalid ISO date `{value}`")
        return None


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_schema(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(data)
    return data


def load_records(path: Path, record_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists() or not path.is_dir():
        return records, [f"{record_name} directory not found: {path}"]

    files = sorted(path.glob("*.json"))
    if not files:
        return records, [f"{record_name} directory is empty: {path}"]

    for file_path in files:
        try:
            record = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{file_path.name}: JSON parse error: {exc}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{file_path.name}: {record_name} must be a JSON object")
            continue
        record["__file__"] = file_path.name
        records.append(record)
    return records, errors


def schema_errors(schema: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for raw_record in records:
        record = {key: value for key, value in raw_record.items() if key != "__file__"}
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            errors.append(f"{raw_record['__file__']}:{location}: {error.message}")
    return errors


def source_errors(
    sources: list[dict[str, Any]], repo_root: Path, as_of: date
) -> tuple[list[str], dict[str, dict[str, Any]], set[str]]:
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    artifact_verified: set[str] = set()

    for source in sources:
        snapshot_id = source.get("source_snapshot_id")
        if not snapshot_id:
            continue
        if snapshot_id in by_id:
            errors.append(f"duplicate source_snapshot_id `{snapshot_id}`")
        else:
            by_id[snapshot_id] = source

        source_url = source.get("source_url")
        source_type = source.get("source_type")
        publisher = source.get("publisher")
        host = urlparse(source_url).hostname if source_url else None

        if source_url and not source_url.startswith("https://"):
            errors.append(f"{snapshot_id}: source_url must use HTTPS")

        authority_key = (source_type, publisher)
        if source_type in {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc"}:
            allowed_hosts = AUTHORITY_HOSTS.get(authority_key)
            if not allowed_hosts or host not in allowed_hosts:
                errors.append(
                    f"{snapshot_id}: source authority `{source_type}` / `{publisher}` is not approved for host `{host}`"
                )

        if source_type in {"first_party_model_doc", "first_party_platform_doc", "provider_owned_doc", "research_paper"} and not source_url:
            errors.append(f"{snapshot_id}: source type `{source_type}` requires a URL")

        retrieved = parse_date(source.get("retrieved_at", ""), f"{snapshot_id}.retrieved_at", errors)
        updated_raw = source.get("document_updated_at")
        updated = parse_date(updated_raw, f"{snapshot_id}.document_updated_at", errors) if updated_raw else None
        snapshot_date_match = re.search(r"(?:^|[._-])(\d{4}-\d{2}-\d{2})$", snapshot_id)
        if not snapshot_date_match:
            errors.append(f"{snapshot_id}: source_snapshot_id must end with its retrieval date")
        elif retrieved and snapshot_date_match.group(1) != retrieved.isoformat():
            errors.append(f"{snapshot_id}: source_snapshot_id date must equal retrieved_at")
        if retrieved and retrieved > as_of:
            errors.append(f"{snapshot_id}: retrieval date is in the future relative to {as_of.isoformat()}")
        if updated and updated > as_of:
            errors.append(f"{snapshot_id}: document update date is in the future relative to {as_of.isoformat()}")
        if updated and retrieved and updated > retrieved:
            errors.append(f"{snapshot_id}: document update date is after retrieval date")

        capture_path = source.get("capture_path")
        expected_hash = source.get("retrieved_document_sha256")
        if capture_path:
            candidate = (repo_root / capture_path).resolve()
            capture_root = (repo_root / ".github" / "evidence-v2" / "captures").resolve()
            try:
                candidate.relative_to(capture_root)
            except ValueError:
                errors.append(
                    f"{snapshot_id}: capture_path must stay under `.github/evidence-v2/captures/`"
                )
            else:
                if not candidate.is_file():
                    errors.append(f"{snapshot_id}: capture artifact not found: {capture_path}")
                elif not expected_hash:
                    errors.append(f"{snapshot_id}: capture artifact requires a SHA-256")
                elif sha256_file(candidate) != expected_hash:
                    errors.append(f"{snapshot_id}: capture artifact hash mismatch")
                else:
                    artifact_verified.add(snapshot_id)

    return sorted(set(errors)), by_id, artifact_verified


def claim_errors(
    claims: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    artifact_verified: set[str],
    repo_root: Path,
    as_of: date,
    enforce_freshness: bool,
    shadow_only: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}

    for claim in claims:
        claim_id = claim.get("claim_id")
        if not claim_id:
            continue
        if claim_id in by_id:
            errors.append(f"duplicate claim_id `{claim_id}`")
        else:
            by_id[claim_id] = claim

        summary = claim.get("evidence_summary", "")
        if summary and claim.get("evidence_summary_sha256") and sha256_text(summary) != claim["evidence_summary_sha256"]:
            errors.append(f"{claim_id}: evidence summary hash mismatch")

        lines = claim.get("source_locator", {}).get("captured_lines")
        if lines and lines[1] < lines[0]:
            errors.append(f"{claim_id}: captured line range is reversed")

        snapshot_id = claim.get("source_snapshot_id")
        source = sources.get(snapshot_id)
        if source is None:
            errors.append(f"{claim_id}: unknown source_snapshot_id `{snapshot_id}`")
            source = {}

        support = claim.get("support_status")
        lifecycle = claim.get("lifecycle_status")
        agreement = claim.get("agreement_status")
        runtime_eligible = claim.get("runtime_eligible") is True
        disposition = claim.get("runtime_disposition")
        retrieval_status = source.get("retrieval_status")
        source_url = source.get("source_url")
        source_type = source.get("source_type")
        claim_class = claim.get("claim_class")

        if support == "supported" and source_type not in CLAIM_SOURCE_TYPES.get(claim_class, set()):
            errors.append(
                f"{claim_id}: claim class `{claim_class}` cannot be supported by source type `{source_type}`"
            )

        if support == "supported":
            if retrieval_status not in SUCCESSFUL_RETRIEVALS:
                errors.append(f"{claim_id}: supported claim requires successful source retrieval")
            if not source_url:
                errors.append(f"{claim_id}: supported claim requires a source URL")
        if support in NON_RUNTIME_SUPPORT and runtime_eligible:
            errors.append(f"{claim_id}: support status `{support}` cannot be runtime-eligible")
        if support == "retracted" and lifecycle == "active":
            errors.append(f"{claim_id}: retracted support cannot remain active")
        if support == "unverified" and agreement != "not_assessed":
            errors.append(f"{claim_id}: unverified evidence must use `not_assessed` agreement")
        if support != "unverified" and agreement == "not_assessed":
            errors.append(f"{claim_id}: `not_assessed` agreement is reserved for unverified evidence")
        if lifecycle in NON_RUNTIME_LIFECYCLE and runtime_eligible:
            errors.append(f"{claim_id}: lifecycle `{lifecycle}` cannot be runtime-eligible")

        model_generation = None
        if claim.get("model_family", "").casefold() == "seedance":
            model_generation = parse_model_generation(claim.get("model_version", ""))
            if model_generation is None:
                errors.append(f"{claim_id}: Seedance model_version must contain a parseable major.minor generation")

        verified = parse_date(claim.get("verified_at", ""), f"{claim_id}.verified_at", errors)
        expires = parse_date(claim.get("expires_at", ""), f"{claim_id}.expires_at", errors)
        retrieved = None
        if source.get("retrieved_at"):
            retrieved = parse_date(source["retrieved_at"], f"{claim_id}.source.retrieved_at", errors)
        if verified and verified > as_of:
            errors.append(f"{claim_id}: verification date is in the future relative to {as_of.isoformat()}")
        if verified and retrieved and verified < retrieved:
            errors.append(f"{claim_id}: verification date precedes source retrieval")
        if claim.get("volatility") == "volatile" and verified and retrieved and verified != retrieved:
            errors.append(f"{claim_id}: volatile evidence must be verified from a same-day source snapshot")
        expired_now = False
        if verified and expires:
            if expires < verified:
                errors.append(f"{claim_id}: expiry precedes verification")
            ttl = (expires - verified).days
            limit = TTL_LIMITS.get(claim.get("claim_class"), 0)
            if ttl > limit:
                errors.append(f"{claim_id}: TTL {ttl} days exceeds {limit}-day class limit")
            expired_now = expires < as_of
            if expired_now and lifecycle == "active":
                message = f"{claim_id}: evidence expired on {expires.isoformat()}"
                (errors if enforce_freshness else warnings).append(message)
            if lifecycle == "expired" and not expired_now:
                errors.append(f"{claim_id}: lifecycle says expired before the expiry date")

        review = claim.get("review", {})
        review_status = review.get("status")
        reviewers = review.get("reviewers", [])
        if review_status == "pending" and reviewers:
            errors.append(f"{claim_id}: pending review cannot name completed reviewers")
        if review_status == "approved":
            if len(reviewers) < 2:
                errors.append(f"{claim_id}: approved editorial review requires at least two reviewers")
            if support != "supported" or lifecycle != "active":
                errors.append(f"{claim_id}: approved editorial review requires supported, active evidence")
        if review_status == "rejected":
            if not reviewers:
                errors.append(f"{claim_id}: rejected editorial review must name at least one reviewer")
            if runtime_eligible or disposition != "block":
                errors.append(f"{claim_id}: rejected editorial review must remain blocked from runtime")

        if runtime_eligible:
            errors.append(
                f"{claim_id}: evidence-v2 foundation has no activation policy; runtime activation is locked"
            )
            if shadow_only:
                errors.append(f"{claim_id}: shadow mode forbids runtime-eligible records")
            if support != "supported":
                errors.append(f"{claim_id}: runtime activation requires supported evidence")
            if lifecycle != "active" or expired_now:
                errors.append(f"{claim_id}: runtime activation requires active, unexpired evidence")
            if agreement not in {"uncontested", "qualified"}:
                errors.append(f"{claim_id}: runtime activation requires assessed, non-conflicting agreement")
            if retrieval_status not in SUCCESSFUL_RETRIEVALS or not source_url:
                errors.append(f"{claim_id}: runtime activation requires a retrieved source URL")
            if source_type not in RUNTIME_SOURCE_TYPES:
                errors.append(f"{claim_id}: runtime activation requires an authoritative platform source")
            if claim_class in NON_RUNTIME_CLASSES:
                errors.append(f"{claim_id}: claim class `{claim_class}` cannot activate runtime behavior")
            if snapshot_id not in artifact_verified:
                errors.append(f"{claim_id}: runtime activation requires a retained, hash-verified capture artifact")
            if disposition != "allow":
                errors.append(f"{claim_id}: runtime-eligible claim must use `allow` disposition")
            if review_status != "approved" or len(reviewers) < 2:
                errors.append(f"{claim_id}: runtime activation requires two approved editorial reviewers")
        elif disposition == "allow":
            errors.append(f"{claim_id}: non-runtime claim cannot use `allow` disposition")

        if model_generation and model_generation >= (2, 5) and runtime_eligible:
            errors.append(
                f"{claim_id}: Seedance {model_generation[0]}.{model_generation[1]} cannot be runtime-eligible "
                "until an official-contract activation policy exists"
            )

        source_host = urlparse(source_url).hostname if source_url else None
        required_prefix = SURFACE_PREFIXES.get(source_host)
        surfaces = claim.get("scope", {}).get("surfaces", [])
        if claim.get("claim_class") in {"pricing", "model_id", "api_field", "prompt_grammar", "official_example"} and not surfaces:
            errors.append(f"{claim_id}: surface-specific claim requires at least one surface")
        if required_prefix and any(not surface.startswith(required_prefix) for surface in surfaces):
            errors.append(f"{claim_id}: source host `{source_host}` cannot support surface scope {surfaces}")

        if agreement == "conflicting" and not claim.get("conflict_group"):
            errors.append(f"{claim_id}: conflicting agreement requires a conflict_group")
        if agreement != "conflicting" and claim.get("conflict_group"):
            errors.append(f"{claim_id}: non-conflicting agreement cannot declare a conflict_group")
        if agreement == "qualified" and not any(
            relation.get("type") in {"qualifies", "qualified_by", "tension_with"}
            for relation in claim.get("relations", [])
        ):
            errors.append(f"{claim_id}: qualified agreement requires a typed qualification relation")

        for affected_path in claim.get("affected_paths", []):
            relative_path = Path(affected_path)
            candidate = (repo_root / relative_path).resolve()
            try:
                candidate.relative_to(repo_root.resolve())
            except ValueError:
                errors.append(f"{claim_id}: affected path must stay inside the repository: {affected_path}")
            else:
                if relative_path.is_absolute():
                    errors.append(f"{claim_id}: affected path must be repository-relative: {affected_path}")
                elif not candidate.exists():
                    errors.append(f"{claim_id}: affected path does not exist: {affected_path}")

    incoming_supersedes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relation_index = {
        (claim.get("claim_id"), relation.get("claim_id"), relation.get("type"))
        for claim in claims
        for relation in claim.get("relations", [])
    }
    for claim in claims:
        claim_id = claim.get("claim_id")
        if not claim_id:
            continue
        for target in claim.get("supersedes", []):
            if target == claim_id:
                errors.append(f"{claim_id}: claim cannot supersede itself")
            if target not in by_id:
                errors.append(f"{claim_id}: dangling supersedes target `{target}`")
                continue
            target_claim = by_id[target]
            incoming_supersedes[target].append(claim)
            if claim.get("lifecycle_status") != "active" or claim.get("support_status") != "supported":
                errors.append(f"{claim_id}: a successor must be active and supported")
            if target_claim.get("lifecycle_status") != "superseded":
                errors.append(f"{claim_id}: supersedes target `{target}` must declare lifecycle `superseded`")
            if claim.get("normalized_key") != target_claim.get("normalized_key"):
                errors.append(f"{claim_id}: supersedes target `{target}` must use the same normalized_key")
            if not scopes_overlap(claim.get("scope", {}), target_claim.get("scope", {})):
                errors.append(f"{claim_id}: supersedes target `{target}` must have overlapping scope")
        for relation in claim.get("relations", []):
            target = relation.get("claim_id")
            relation_type = relation.get("type")
            if target == claim_id:
                errors.append(f"{claim_id}: claim cannot relate to itself")
            if target not in by_id:
                errors.append(f"{claim_id}: dangling relation target `{target}`")
                continue
            inverse = RELATION_INVERSES.get(relation_type)
            if inverse and (target, claim_id, inverse) not in relation_index:
                errors.append(
                    f"{claim_id}: relation `{relation_type}` to `{target}` requires reciprocal `{inverse}`"
                )

    for claim in claims:
        claim_id = claim.get("claim_id")
        if claim_id and claim.get("lifecycle_status") == "superseded" and not incoming_supersedes.get(claim_id):
            errors.append(f"{claim_id}: superseded lifecycle requires an incoming successor edge")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(claim_id: str, path: list[str]) -> None:
        if claim_id in visiting:
            errors.append(f"supersedes cycle: {' -> '.join(path + [claim_id])}")
            return
        if claim_id in visited or claim_id not in by_id:
            return
        visiting.add(claim_id)
        for target in by_id[claim_id].get("supersedes", []):
            visit(target, path + [claim_id])
        visiting.remove(claim_id)
        visited.add(claim_id)

    for claim_id in sorted(by_id):
        visit(claim_id, [])

    conflict_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        group = claim.get("conflict_group")
        if group:
            conflict_groups[group].append(claim)
    for group, members in sorted(conflict_groups.items()):
        if len(members) < 2:
            errors.append(f"conflict group `{group}` has fewer than two claims")
            continue
        if len({canonical(member.get("value")) for member in members}) < 2:
            errors.append(f"conflict group `{group}` does not contain incompatible values")
        if any(member.get("agreement_status") != "conflicting" for member in members):
            errors.append(f"conflict group `{group}` contains non-conflicting agreement")
        if len({member.get("normalized_key") for member in members}) != 1:
            errors.append(f"conflict group `{group}` mixes normalized keys")
        for left, right in combinations(members, 2):
            if not scopes_overlap(left.get("scope", {}), right.get("scope", {})):
                errors.append(f"conflict group `{group}` contains non-overlapping scopes")

    active_claims = [
        claim
        for claim in claims
        if claim.get("lifecycle_status") == "active" and claim.get("support_status") == "supported"
    ]
    for left, right in combinations(active_claims, 2):
        normalized_key = left.get("normalized_key")
        if normalized_key != right.get("normalized_key"):
            continue
        if not scopes_overlap(left.get("scope", {}), right.get("scope", {})):
            continue
        if canonical(left.get("value")) == canonical(right.get("value")):
            continue
        group = left.get("conflict_group")
        if (
            not group
            or group != right.get("conflict_group")
            or left.get("agreement_status") != "conflicting"
            or right.get("agreement_status") != "conflicting"
        ):
            errors.append(f"undeclared value conflict for `{normalized_key}`")

    return sorted(set(errors)), sorted(set(warnings))


def build_report(
    claim_schema: dict[str, Any],
    claims: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    artifact_verified: set[str],
    errors: list[str],
    warnings: list[str],
    as_of: date,
) -> dict[str, Any]:
    def counts(field: str) -> dict[str, int]:
        return dict(sorted(Counter(claim.get(field, "invalid") for claim in claims).items()))

    return {
        "as_of": as_of.isoformat(),
        "schema_id": claim_schema.get("$id"),
        "claim_count": len(claims),
        "source_snapshot_count": len(sources),
        "artifact_verified_source_count": len(artifact_verified),
        "runtime_eligible_count": sum(claim.get("runtime_eligible") is True for claim in claims),
        "support_counts": counts("support_status"),
        "volatility_counts": counts("volatility"),
        "agreement_counts": counts("agreement_status"),
        "lifecycle_counts": counts("lifecycle_status"),
        "review_counts": dict(sorted(Counter(claim.get("review", {}).get("status", "invalid") for claim in claims).items())),
        "errors": sorted(errors),
        "warnings": sorted(warnings),
        "claims": [
            {
                "claim_id": claim.get("claim_id"),
                "support_status": claim.get("support_status"),
                "agreement_status": claim.get("agreement_status"),
                "lifecycle_status": claim.get("lifecycle_status"),
                "runtime_eligible": claim.get("runtime_eligible"),
                "review_status": claim.get("review", {}).get("status"),
            }
            for claim in sorted(claims, key=lambda item: item.get("claim_id", ""))
        ],
    }


def evaluate(
    claim_schema_path: Path,
    source_schema_path: Path,
    claims_path: Path,
    sources_path: Path,
    repo_root: Path,
    as_of: date,
    enforce_freshness: bool,
    shadow_only: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    claim_schema = load_schema(claim_schema_path)
    source_schema = load_schema(source_schema_path)
    claims, claim_load_errors = load_records(claims_path, "claims")
    sources, source_load_errors = load_records(sources_path, "sources")
    errors = claim_load_errors + source_load_errors
    errors.extend(schema_errors(claim_schema, claims))
    errors.extend(schema_errors(source_schema, sources))

    artifact_verified: set[str] = set()
    warnings: list[str] = []
    if not errors:
        source_semantic, sources_by_id, artifact_verified = source_errors(sources, repo_root, as_of)
        errors.extend(source_semantic)
        claim_semantic, warnings = claim_errors(
            claims,
            sources_by_id,
            artifact_verified,
            repo_root,
            as_of,
            enforce_freshness,
            shadow_only,
        )
        errors.extend(claim_semantic)

    report = build_report(
        claim_schema,
        claims,
        sources,
        artifact_verified,
        sorted(set(errors)),
        sorted(set(warnings)),
        as_of,
    )
    return report, report["errors"], report["warnings"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate non-activating Seedance evidence records.")
    parser.add_argument("--claim-schema", type=Path, default=DEFAULT_CLAIM_SCHEMA)
    parser.add_argument("--source-schema", type=Path, default=DEFAULT_SOURCE_SCHEMA)
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--enforce-freshness", action="store_true")
    parser.add_argument("--shadow-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        report, errors, warnings = evaluate(
            args.claim_schema.resolve(),
            args.source_schema.resolve(),
            args.claims.resolve(),
            args.sources.resolve(),
            args.repo_root.resolve(),
            args.as_of,
            args.enforce_freshness,
            args.shadow_only,
        )
    except Exception as exc:
        print(f"Evidence validation failed before evaluation: {exc}")
        return 1

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if warnings:
        print("Evidence warnings:")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("Evidence record errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"Evidence records validated: {report['claim_count']} claims; "
        f"runtime-eligible records: {report['runtime_eligible_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
