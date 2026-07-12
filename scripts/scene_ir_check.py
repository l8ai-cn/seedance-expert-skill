#!/usr/bin/env python3
"""Validate the V7 causal scene intermediate representation.

The IR is a planning and review contract.  It does not claim to expose a
provider model's internal architecture, simulate physics, or guarantee video
quality.  Validation is deliberately fail-closed and diagnostic output never
echoes caller-controlled values.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from typing import Any

try:  # Script execution and package imports both remain supported.
    from . import render_surface_bindings as bindings
except ImportError:  # pragma: no cover - exercised by CLI tests
    import render_surface_bindings as bindings


SCENE_IR_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/scene-ir.schema.json"
)
SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
LOCATOR_LIKE = re.compile(r"(?:https?://|file://)", re.IGNORECASE)

ROOT_KEYS = {
    "$schema",
    "schema_version",
    "entities",
    "materials",
    "shots",
    "audio_events",
    "requested_invariants",
    "known_fragilities",
    "acceptance_tests",
    "post_fallbacks",
}
ENTITY_KEYS = {"entity_id", "label", "kind", "stable_features"}
MATERIAL_KEYS = {
    "material_id",
    "entity_id",
    "kind",
    "response_properties",
}
SHOT_KEYS = {"shot_id", "shot_index", "events", "camera"}
EVENT_KEYS = {
    "event_id",
    "event_index",
    "phase",
    "actor_ids",
    "target_ids",
    "depends_on",
    "visible_state_change",
    "interaction_kind",
    "material_ids",
}
CAMERA_KEYS = {"primary_move", "observability"}
MOVE_KEYS = {
    "kind",
    "start_framing",
    "path",
    "speed",
    "subject_relationship",
    "endpoint_framing",
}
OBSERVABILITY_KEYS = {
    "before_state_event_id",
    "decisive_event_id",
    "consequence_event_ids",
    "endpoint_event_id",
    "occlusion_risks",
    "mitigations",
}
AUDIO_KEYS = {
    "audio_event_id",
    "shot_id",
    "linked_event_id",
    "temporal_relationship",
    "semantic_function",
    "source_entity_ids",
    "description",
}
INVARIANT_KEYS = {"invariant_id", "entity_ids", "description"}
FRAGILITY_KEYS = {"fragility_id", "event_ids", "description"}
ACCEPTANCE_KEYS = {"acceptance_id", "event_ids", "observable", "pass_condition"}
FALLBACK_KEYS = {"fallback_id", "trigger_acceptance_ids", "action"}

ENTITY_KINDS = {"character", "product", "object", "environment", "effect", "text"}
MATERIAL_KINDS = {
    "rigid",
    "elastic",
    "fabric",
    "liquid",
    "granular",
    "organic",
    "smoke",
    "fire",
    "other",
}
PHASES = (
    "initial_state",
    "trigger",
    "motion_path",
    "contact_or_state_change",
    "primary_response",
    "secondary_response",
    "follow_through",
    "settled_endpoint",
)
PHASE_RANK = {phase: index for index, phase in enumerate(PHASES)}
REQUIRED_PHASES = {
    "initial_state",
    "trigger",
    "contact_or_state_change",
    "primary_response",
    "follow_through",
    "settled_endpoint",
}
SINGLETON_PHASES = REQUIRED_PHASES | {"motion_path"}
INTERACTIONS = {"none", "contact", "material_change", "non_material_state_change"}
CAMERA_MOVES = {
    "locked",
    "crane",
    "dolly",
    "handheld",
    "orbit",
    "pan",
    "pull_out",
    "push_in",
    "tilt",
    "tracking",
}
TEMPORAL_RELATIONSHIPS = {
    "at_initial_state",
    "at_endpoint",
    "continuous",
    "during_follow_through",
    "during_motion",
    "during_response",
    "on_contact_or_state_change",
    "on_trigger",
}
TEMPORAL_PHASES = {
    "at_initial_state": {"initial_state"},
    "on_trigger": {"trigger"},
    "during_motion": {"motion_path"},
    "on_contact_or_state_change": {"contact_or_state_change"},
    "during_response": {"primary_response", "secondary_response"},
    "during_follow_through": {"follow_through"},
    "at_endpoint": {"settled_endpoint"},
    "continuous": set(PHASES),
}
SEMANTIC_FUNCTIONS = {
    "ambience",
    "dialogue",
    "music",
    "rhythm",
    "silence",
    "sound_effect",
    "voiceover",
}


class SceneIRError(bindings.BindingError):
    """Stable, non-echoing causal-IR validation failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise SceneIRError(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(
    value: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 256,
) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("ARRAY_BOUNDS_INVALID", pointer)
    return value


def _identifier(value: object, pointer: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        _fail("IDENTIFIER_INVALID", pointer)
    return value


def _text(value: object, pointer: str, *, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("TEXT_INVALID", pointer)
    bindings._validate_visible_text(value, pointer)
    if LOCATOR_LIKE.search(value):
        _fail("TEXT_LOCATOR_FORBIDDEN", pointer)
    return value


def _unique_ids(
    values: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 64,
) -> list[str]:
    raw = _array(values, pointer, minimum=minimum, maximum=maximum)
    checked = [_identifier(value, f"{pointer}/{index}") for index, value in enumerate(raw)]
    if len(checked) != len(set(checked)):
        _fail("IDENTIFIER_DUPLICATE", pointer)
    return checked


def _unique_texts(
    values: object,
    pointer: str,
    *,
    minimum: int = 0,
    maximum: int = 64,
    text_maximum: int = 1_000,
) -> list[str]:
    raw = _array(values, pointer, minimum=minimum, maximum=maximum)
    checked = [
        _text(value, f"{pointer}/{index}", maximum=text_maximum)
        for index, value in enumerate(raw)
    ]
    if len(checked) != len(set(checked)):
        _fail("TEXT_DUPLICATE", pointer)
    return checked


def _enum(value: object, allowed: set[str], pointer: str, code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        _fail(code, pointer)
    return value


def _require_known(values: Iterable[str], known: set[str], code: str, pointer: str) -> None:
    if any(value not in known for value in values):
        _fail(code, pointer)


def _ancestors(event_id: str, dependencies: dict[str, list[str]]) -> set[str]:
    result: set[str] = set()
    pending = list(dependencies[event_id])
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(dependencies[current])
    return result


def _require_reachable(
    later: str,
    earlier: str,
    dependencies: dict[str, list[str]],
    pointer: str,
) -> None:
    if earlier not in _ancestors(later, dependencies):
        _fail("EVT004_CAUSAL_CHAIN_UNREACHABLE", pointer)


def validate_scene_ir(value: object) -> dict[str, Any]:
    """Validate and return a causal IR without rewriting caller data."""

    scene = _object(value, ROOT_KEYS, "/scene_ir")
    if (
        scene["$schema"] != SCENE_IR_SCHEMA_URI
        or not bindings._is_int(scene["schema_version"])
        or scene["schema_version"] != 1
    ):
        _fail("SCENE_IR_CONTRACT_INVALID", "/scene_ir")

    entity_ids: set[str] = set()
    for index, raw in enumerate(_array(scene["entities"], "/scene_ir/entities", minimum=1, maximum=128)):
        pointer = f"/scene_ir/entities/{index}"
        entity = _object(raw, ENTITY_KEYS, pointer)
        entity_id = _identifier(entity["entity_id"], f"{pointer}/entity_id")
        if entity_id in entity_ids:
            _fail("ENTITY_ID_DUPLICATE", f"{pointer}/entity_id")
        entity_ids.add(entity_id)
        _text(entity["label"], f"{pointer}/label")
        _enum(entity["kind"], ENTITY_KINDS, f"{pointer}/kind", "ENTITY_KIND_INVALID")
        _unique_texts(
            entity["stable_features"],
            f"{pointer}/stable_features",
            minimum=1,
            maximum=16,
            text_maximum=200,
        )

    material_owner: dict[str, str] = {}
    for index, raw in enumerate(_array(scene["materials"], "/scene_ir/materials", maximum=128)):
        pointer = f"/scene_ir/materials/{index}"
        material = _object(raw, MATERIAL_KEYS, pointer)
        material_id = _identifier(material["material_id"], f"{pointer}/material_id")
        if material_id in material_owner:
            _fail("MATERIAL_ID_DUPLICATE", f"{pointer}/material_id")
        owner = _identifier(material["entity_id"], f"{pointer}/entity_id")
        if owner not in entity_ids:
            _fail("MATERIAL_ENTITY_UNKNOWN", f"{pointer}/entity_id")
        material_owner[material_id] = owner
        _enum(
            material["kind"],
            MATERIAL_KINDS,
            f"{pointer}/kind",
            "MATERIAL_CLASS_INVALID",
        )
        _unique_texts(
            material["response_properties"],
            f"{pointer}/response_properties",
            minimum=1,
            maximum=16,
            text_maximum=200,
        )

    shots = _array(scene["shots"], "/scene_ir/shots", minimum=1, maximum=64)
    shot_ids: set[str] = set()
    event_ids: set[str] = set()
    event_by_id: dict[str, dict[str, Any]] = {}
    event_shot: dict[str, str] = {}
    dependencies: dict[str, list[str]] = {}
    global_order: dict[str, int] = {}
    endpoint_by_shot: list[str] = []
    causal_order: list[dict[str, Any]] = []
    ordinal = 0

    for shot_offset, raw_shot in enumerate(shots):
        shot_pointer = f"/scene_ir/shots/{shot_offset}"
        shot = _object(raw_shot, SHOT_KEYS, shot_pointer)
        shot_id = _identifier(shot["shot_id"], f"{shot_pointer}/shot_id")
        if shot_id in shot_ids:
            _fail("SHOT_ID_DUPLICATE", f"{shot_pointer}/shot_id")
        shot_ids.add(shot_id)
        if not bindings._is_int(shot["shot_index"]) or shot["shot_index"] != shot_offset + 1:
            _fail("EVT003_SHOT_ORDER_INVALID", f"{shot_pointer}/shot_index")

        events = _array(shot["events"], f"{shot_pointer}/events", minimum=6, maximum=64)
        phases: list[str] = []
        local_ids: list[str] = []
        local_events: dict[str, dict[str, Any]] = {}
        for event_offset, raw_event in enumerate(events):
            event_pointer = f"{shot_pointer}/events/{event_offset}"
            event = _object(raw_event, EVENT_KEYS, event_pointer)
            event_id = _identifier(event["event_id"], f"{event_pointer}/event_id")
            if event_id in event_ids:
                _fail("EVENT_ID_DUPLICATE", f"{event_pointer}/event_id")
            if not bindings._is_int(event["event_index"]) or event["event_index"] != event_offset + 1:
                _fail("EVT003_EVENT_ORDER_INVALID", f"{event_pointer}/event_index")
            phase = _enum(event["phase"], set(PHASES), f"{event_pointer}/phase", "EVENT_PHASE_INVALID")
            actor_ids = _unique_ids(event["actor_ids"], f"{event_pointer}/actor_ids", maximum=16)
            target_ids = _unique_ids(event["target_ids"], f"{event_pointer}/target_ids", maximum=16)
            if not actor_ids and not target_ids:
                _fail("EVENT_PARTICIPANT_REQUIRED", event_pointer)
            _require_known(actor_ids, entity_ids, "EVENT_ENTITY_UNKNOWN", f"{event_pointer}/actor_ids")
            _require_known(target_ids, entity_ids, "EVENT_ENTITY_UNKNOWN", f"{event_pointer}/target_ids")
            dependency_ids = _unique_ids(event["depends_on"], f"{event_pointer}/depends_on", maximum=16)
            _text(event["visible_state_change"], f"{event_pointer}/visible_state_change")
            interaction = _enum(
                event["interaction_kind"],
                INTERACTIONS,
                f"{event_pointer}/interaction_kind",
                "EVENT_INTERACTION_INVALID",
            )
            event_materials = _unique_ids(event["material_ids"], f"{event_pointer}/material_ids", maximum=16)
            _require_known(
                event_materials,
                set(material_owner),
                "EVENT_MATERIAL_UNKNOWN",
                f"{event_pointer}/material_ids",
            )
            participants = set(actor_ids) | set(target_ids)
            if any(material_owner[material_id] not in participants for material_id in event_materials):
                _fail("EVENT_MATERIAL_OWNER_NOT_PARTICIPANT", f"{event_pointer}/material_ids")
            if interaction in {"none", "non_material_state_change"} and event_materials:
                _fail("EVENT_MATERIAL_WITHOUT_INTERACTION", f"{event_pointer}/material_ids")
            if interaction in {"contact", "material_change"} and not event_materials:
                _fail("EVT002_MATERIAL_RESPONSE_REQUIRED", f"{event_pointer}/material_ids")
            if phase in {
                "initial_state",
                "trigger",
                "motion_path",
                "follow_through",
                "settled_endpoint",
            } and interaction != "none":
                _fail("EVT003_PHASE_INTERACTION_INVALID", f"{event_pointer}/interaction_kind")
            if phase == "contact_or_state_change" and interaction == "none":
                _fail("EVT002_DECISIVE_INTERACTION_REQUIRED", f"{event_pointer}/interaction_kind")

            event_ids.add(event_id)
            local_ids.append(event_id)
            local_events[event_id] = event
            event_by_id[event_id] = event
            event_shot[event_id] = shot_id
            dependencies[event_id] = dependency_ids
            global_order[event_id] = ordinal
            ordinal += 1
            phases.append(phase)

        if any(PHASE_RANK[phases[index]] > PHASE_RANK[phases[index + 1]] for index in range(len(phases) - 1)):
            _fail("EVT003_PHASE_ORDER_INVALID", f"{shot_pointer}/events")
        # Keep diagnostic precedence stable across hash seeds: an absent
        # initial state is always reported before later phase cardinality.
        for phase in (
            "initial_state",
            "trigger",
            "contact_or_state_change",
            "primary_response",
            "follow_through",
            "settled_endpoint",
        ):
            if phases.count(phase) != 1:
                code = "EVT001_INITIAL_STATE_REQUIRED" if phase == "initial_state" else "EVT003_PHASE_CARDINALITY_INVALID"
                _fail(code, f"{shot_pointer}/events")
        for phase in SINGLETON_PHASES:
            if phases.count(phase) > 1:
                _fail("EVT003_PHASE_CARDINALITY_INVALID", f"{shot_pointer}/events")

        initial_id = local_ids[phases.index("initial_state")]
        trigger_id = local_ids[phases.index("trigger")]
        decisive_id = local_ids[phases.index("contact_or_state_change")]
        response_id = local_ids[phases.index("primary_response")]
        follow_id = local_ids[phases.index("follow_through")]
        endpoint_id = local_ids[phases.index("settled_endpoint")]

        if shot_offset == 0:
            if dependencies[initial_id]:
                _fail("EVT003_INITIAL_DEPENDENCY_INVALID", f"{shot_pointer}/events/0/depends_on")
        elif endpoint_by_shot[-1] not in dependencies[initial_id]:
            _fail("EVT003_CROSS_SHOT_ENDPOINT_REQUIRED", f"{shot_pointer}/events/0/depends_on")

        for event_offset, event_id in enumerate(local_ids):
            event_pointer = f"{shot_pointer}/events/{event_offset}/depends_on"
            if event_id != initial_id and not dependencies[event_id]:
                _fail("EVT003_DEPENDENCY_REQUIRED", event_pointer)
            for dependency in dependencies[event_id]:
                if dependency not in global_order:
                    _fail("EVT003_DEPENDENCY_UNKNOWN", event_pointer)
                if global_order[dependency] >= global_order[event_id]:
                    _fail("EVT003_FUTURE_DEPENDENCY", event_pointer)

        _require_reachable(trigger_id, initial_id, dependencies, f"{shot_pointer}/events")
        _require_reachable(decisive_id, trigger_id, dependencies, f"{shot_pointer}/events")
        _require_reachable(response_id, decisive_id, dependencies, f"{shot_pointer}/events")
        _require_reachable(follow_id, response_id, dependencies, f"{shot_pointer}/events")
        _require_reachable(endpoint_id, follow_id, dependencies, f"{shot_pointer}/events")

        decisive = local_events[decisive_id]
        response = local_events[response_id]
        response_events = [
            local_events[event_id]
            for event_id in local_ids
            if local_events[event_id]["phase"] in {"primary_response", "secondary_response"}
        ]
        if decisive["interaction_kind"] in {"contact", "material_change"}:
            if not decisive["material_ids"] or any(not item["material_ids"] for item in response_events):
                _fail("EVT002_MATERIAL_RESPONSE_REQUIRED", f"{shot_pointer}/events")
            if any(item["interaction_kind"] not in {"contact", "material_change"} for item in response_events):
                _fail("EVT002_MATERIAL_RESPONSE_REQUIRED", f"{shot_pointer}/events")
        elif decisive["interaction_kind"] == "non_material_state_change":
            if decisive["material_ids"] or any(item["material_ids"] for item in response_events):
                _fail("EVT002_NON_MATERIAL_HAS_MATERIAL", f"{shot_pointer}/events")
            if any(item["interaction_kind"] != "non_material_state_change" for item in response_events):
                _fail("EVT002_VISIBLE_CONSEQUENCE_REQUIRED", f"{shot_pointer}/events")

        camera = _object(shot["camera"], CAMERA_KEYS, f"{shot_pointer}/camera")
        move = _object(camera["primary_move"], MOVE_KEYS, f"{shot_pointer}/camera/primary_move")
        move_kind = _enum(
            move["kind"], CAMERA_MOVES, f"{shot_pointer}/camera/primary_move/kind", "CAM001_PRIMARY_MOVE_INVALID"
        )
        for field in ("start_framing", "path", "subject_relationship", "endpoint_framing"):
            _text(move[field], f"{shot_pointer}/camera/primary_move/{field}")
        _text(move["speed"], f"{shot_pointer}/camera/primary_move/speed")
        if move_kind == "locked" and move["speed"].strip().casefold() != "static":
            _fail("CAM002_LOCKED_SPEED_MISMATCH", f"{shot_pointer}/camera/primary_move")

        observation = _object(
            camera["observability"], OBSERVABILITY_KEYS, f"{shot_pointer}/camera/observability"
        )
        before_id = _identifier(
            observation["before_state_event_id"],
            f"{shot_pointer}/camera/observability/before_state_event_id",
        )
        observed_decisive = _identifier(
            observation["decisive_event_id"],
            f"{shot_pointer}/camera/observability/decisive_event_id",
        )
        consequence_ids = _unique_ids(
            observation["consequence_event_ids"],
            f"{shot_pointer}/camera/observability/consequence_event_ids",
            minimum=1,
            maximum=16,
        )
        observed_endpoint = _identifier(
            observation["endpoint_event_id"],
            f"{shot_pointer}/camera/observability/endpoint_event_id",
        )
        observed_ids = [before_id, observed_decisive, *consequence_ids, observed_endpoint]
        if any(value not in local_events for value in observed_ids):
            _fail("EVT005_CAMERA_EVENT_UNKNOWN", f"{shot_pointer}/camera/observability")
        if before_id != initial_id or observed_decisive != decisive_id or observed_endpoint != endpoint_id:
            _fail("EVT005_CAMERA_PHASE_MISMATCH", f"{shot_pointer}/camera/observability")
        if observed_endpoint in consequence_ids:
            _fail("EVT005_CONSEQUENCE_PHASE_INVALID", f"{shot_pointer}/camera/observability")
        if response_id not in consequence_ids:
            _fail("EVT005_PRIMARY_RESPONSE_NOT_OBSERVED", f"{shot_pointer}/camera/observability")
        if any(PHASE_RANK[local_events[item]["phase"]] < PHASE_RANK["primary_response"] for item in consequence_ids):
            _fail("EVT005_CONSEQUENCE_PHASE_INVALID", f"{shot_pointer}/camera/observability")
        risks = _unique_texts(
            observation["occlusion_risks"],
            f"{shot_pointer}/camera/observability/occlusion_risks",
            maximum=16,
        )
        mitigations = _unique_texts(
            observation["mitigations"],
            f"{shot_pointer}/camera/observability/mitigations",
            maximum=16,
        )
        if risks and not mitigations:
            _fail("EVT005_OCCLUSION_UNMITIGATED", f"{shot_pointer}/camera/observability")

        endpoint_by_shot.append(endpoint_id)
        causal_order.append({"shot_id": shot_id, "event_ids": local_ids})

    for event_id, dependency_ids in dependencies.items():
        for dependency in dependency_ids:
            if dependency not in event_ids:
                _fail("EVT003_DEPENDENCY_UNKNOWN", "/scene_ir/shots")

    audio_ids: set[str] = set()
    for index, raw in enumerate(_array(scene["audio_events"], "/scene_ir/audio_events", maximum=128)):
        pointer = f"/scene_ir/audio_events/{index}"
        audio = _object(raw, AUDIO_KEYS, pointer)
        audio_id = _identifier(audio["audio_event_id"], f"{pointer}/audio_event_id")
        if audio_id in audio_ids:
            _fail("AUDIO_EVENT_ID_DUPLICATE", f"{pointer}/audio_event_id")
        audio_ids.add(audio_id)
        shot_id = _identifier(audio["shot_id"], f"{pointer}/shot_id")
        linked_event = _identifier(audio["linked_event_id"], f"{pointer}/linked_event_id")
        if shot_id not in shot_ids or linked_event not in event_ids or event_shot[linked_event] != shot_id:
            _fail("AUDIO_EVENT_LINK_INVALID", pointer)
        temporal_relationship = _enum(
            audio["temporal_relationship"],
            TEMPORAL_RELATIONSHIPS,
            f"{pointer}/temporal_relationship",
            "AUDIO001_TEMPORAL_RELATIONSHIP_INVALID",
        )
        if event_by_id[linked_event]["phase"] not in TEMPORAL_PHASES[temporal_relationship]:
            _fail("AUDIO001_TEMPORAL_EVENT_MISMATCH", f"{pointer}/temporal_relationship")
        _enum(
            audio["semantic_function"],
            SEMANTIC_FUNCTIONS,
            f"{pointer}/semantic_function",
            "AUDIO001_SEMANTIC_FUNCTION_INVALID",
        )
        sources = _unique_ids(audio["source_entity_ids"], f"{pointer}/source_entity_ids", maximum=16)
        _require_known(sources, entity_ids, "AUDIO_SOURCE_UNKNOWN", f"{pointer}/source_entity_ids")
        _text(audio["description"], f"{pointer}/description")

    invariant_ids: set[str] = set()
    for index, raw in enumerate(
        _array(scene["requested_invariants"], "/scene_ir/requested_invariants", minimum=1, maximum=128)
    ):
        pointer = f"/scene_ir/requested_invariants/{index}"
        invariant = _object(raw, INVARIANT_KEYS, pointer)
        invariant_id = _identifier(invariant["invariant_id"], f"{pointer}/invariant_id")
        if invariant_id in invariant_ids:
            _fail("INVARIANT_ID_DUPLICATE", f"{pointer}/invariant_id")
        invariant_ids.add(invariant_id)
        owners = _unique_ids(invariant["entity_ids"], f"{pointer}/entity_ids", minimum=1, maximum=16)
        _require_known(owners, entity_ids, "INVARIANT_ENTITY_UNKNOWN", f"{pointer}/entity_ids")
        _text(invariant["description"], f"{pointer}/description")

    fragility_ids: set[str] = set()
    for index, raw in enumerate(
        _array(scene["known_fragilities"], "/scene_ir/known_fragilities", minimum=1, maximum=128)
    ):
        pointer = f"/scene_ir/known_fragilities/{index}"
        fragility = _object(raw, FRAGILITY_KEYS, pointer)
        fragility_id = _identifier(fragility["fragility_id"], f"{pointer}/fragility_id")
        if fragility_id in fragility_ids:
            _fail("FRAGILITY_ID_DUPLICATE", f"{pointer}/fragility_id")
        fragility_ids.add(fragility_id)
        linked = _unique_ids(fragility["event_ids"], f"{pointer}/event_ids", minimum=1, maximum=32)
        _require_known(linked, event_ids, "FRAGILITY_EVENT_UNKNOWN", f"{pointer}/event_ids")
        _text(fragility["description"], f"{pointer}/description")

    acceptance_ids: set[str] = set()
    covered_events: set[str] = set()
    for index, raw in enumerate(
        _array(scene["acceptance_tests"], "/scene_ir/acceptance_tests", minimum=1, maximum=128)
    ):
        pointer = f"/scene_ir/acceptance_tests/{index}"
        acceptance = _object(raw, ACCEPTANCE_KEYS, pointer)
        acceptance_id = _identifier(acceptance["acceptance_id"], f"{pointer}/acceptance_id")
        if acceptance_id in acceptance_ids:
            _fail("ACCEPTANCE_ID_DUPLICATE", f"{pointer}/acceptance_id")
        acceptance_ids.add(acceptance_id)
        linked = _unique_ids(acceptance["event_ids"], f"{pointer}/event_ids", minimum=1, maximum=32)
        _require_known(linked, event_ids, "ACCEPTANCE_EVENT_UNKNOWN", f"{pointer}/event_ids")
        covered_events.update(linked)
        _text(acceptance["observable"], f"{pointer}/observable")
        _text(acceptance["pass_condition"], f"{pointer}/pass_condition")
    for endpoint in endpoint_by_shot:
        if endpoint not in covered_events:
            _fail("EVT004_ENDPOINT_NOT_ACCEPTANCE_LINKED", "/scene_ir/acceptance_tests")

    fallback_ids: set[str] = set()
    for index, raw in enumerate(
        _array(scene["post_fallbacks"], "/scene_ir/post_fallbacks", minimum=1, maximum=128)
    ):
        pointer = f"/scene_ir/post_fallbacks/{index}"
        fallback = _object(raw, FALLBACK_KEYS, pointer)
        fallback_id = _identifier(fallback["fallback_id"], f"{pointer}/fallback_id")
        if fallback_id in fallback_ids:
            _fail("FALLBACK_ID_DUPLICATE", f"{pointer}/fallback_id")
        fallback_ids.add(fallback_id)
        triggers = _unique_ids(
            fallback["trigger_acceptance_ids"],
            f"{pointer}/trigger_acceptance_ids",
            minimum=1,
            maximum=32,
        )
        _require_known(
            triggers,
            acceptance_ids,
            "FALLBACK_ACCEPTANCE_UNKNOWN",
            f"{pointer}/trigger_acceptance_ids",
        )
        _text(fallback["action"], f"{pointer}/action")

    return scene


def causal_order(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the already-validated, deterministic shot/event order."""

    return [
        {"shot_id": shot["shot_id"], "event_ids": [event["event_id"] for event in shot["events"]]}
        for shot in scene["shots"]
    ]


def _self_test() -> None:
    # The complete positive contracts live in validation fixtures.  This test
    # proves hostile parser failures stay on the stable, non-echoing path.
    try:
        bindings.parse_json_bytes(b'{"x":1,"x":2}')
    except bindings.BindingError as exc:
        if exc.code != "JSON_DUPLICATE_KEY":
            _fail("SELF_TEST_FAILED")
    else:
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a candidate causal scene IR from JSON stdin or a local file."
    )
    parser.add_argument("request", nargs="?", default="-", help="JSON request path, or - for stdin")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("causal scene IR self-test passed")
            return 0
        raw = bindings._read_request(args.request)
        scene = validate_scene_ir(bindings.parse_json_bytes(raw))
        payload = bindings.canonical_json(
            {
                "schema_version": 1,
                "status": "valid",
                "scene_ir_sha256": bindings.sha256_bytes(bindings.canonical_json(scene)),
            }
        )
    except bindings.BindingError as exc:
        print(f"scene-ir error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
