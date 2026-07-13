from __future__ import annotations

from pathlib import Path

from scripts.project_state_relationships import (
    validate_assignments,
    validate_relationships,
)
from scripts.project_state_rules import (
    ACCEPTED,
    ARC_POSITIONS,
    MAX_CHAIN_DEPTH_CEILING,
    REQUIRED_CLIP_FIELDS,
    REQUIRED_PROJECT_FIELDS,
    REQUIRED_SCENE_FIELDS,
    REQUIRED_STORY_FIELDS,
    SCENE_STATUSES,
    check_required,
    load_json,
)


def validate_project(path: Path, root: Path) -> list[str]:
    rel = path.relative_to(root).as_posix()
    errors: list[str] = []
    try:
        data = load_json(path)
    except Exception as error:
        return [f"{rel}: invalid JSON: {error}"]
    if not isinstance(data, dict):
        return [f"{rel}: project state must be an object"]

    check_required(data, REQUIRED_PROJECT_FIELDS, rel, errors)
    if errors:
        return errors
    if data["project_mode"] not in {"standalone_clip", "sequence_project"}:
        errors.append(f"{rel}: invalid project_mode {data['project_mode']}")
    if data["project_mode"] == "sequence_project" and not data["story"].get("final_outcome"):
        errors.append(f"{rel}: sequence project missing final_outcome")
    check_required(data["story"], REQUIRED_STORY_FIELDS, f"{rel}: story", errors)

    clip_ids: set[object] = set()
    accepted_ids: set[object] = set()
    scene_ids: set[object] = set()
    scene_depth_caps: dict[object, int] = {}
    scene_indexes: set[int] = set()
    scene_assigned: dict[object, set[object]] = {}
    clip_scene: dict[object, object] = {}
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list):
        errors.append(f"{rel}: scenes must be an array of scene objects")
        scenes = []
    for scene in scenes:
        if not isinstance(scene, dict):
            errors.append(f"{rel}: scenes entries must be objects")
            continue
        check_required(scene, REQUIRED_SCENE_FIELDS, f"{rel}: scene", errors)
        scene_id = scene.get("scene_id")
        if scene_id in scene_ids:
            errors.append(f"{rel}: duplicate scene_id {scene_id}")
        scene_ids.add(scene_id)
        index = scene.get("scene_index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 1:
            errors.append(f"{rel}: scene {scene_id} scene_index must be an integer >= 1")
        elif index in scene_indexes:
            errors.append(f"{rel}: duplicate scene_index {index}")
        else:
            scene_indexes.add(index)
        if scene.get("status") not in SCENE_STATUSES:
            errors.append(f"{rel}: scene {scene_id} invalid status {scene.get('status')}")
        if scene.get("arc_position") not in ARC_POSITIONS:
            errors.append(
                f"{rel}: scene {scene_id} invalid arc_position {scene.get('arc_position')}"
            )
        depth_cap = scene.get("max_chain_depth")
        if (
            not isinstance(depth_cap, int)
            or isinstance(depth_cap, bool)
            or depth_cap < 0
            or depth_cap > MAX_CHAIN_DEPTH_CEILING
        ):
            errors.append(
                f"{rel}: scene {scene_id} max_chain_depth must be an integer "
                f"between 0 and {MAX_CHAIN_DEPTH_CEILING}"
            )
        else:
            scene_depth_caps[scene_id] = depth_cap
        assigned_list = scene.get("assigned_clip_ids", [])
        seen_assigned: set[object] = set()
        for assigned in assigned_list if isinstance(assigned_list, list) else []:
            if assigned in seen_assigned:
                errors.append(
                    f"{rel}: scene {scene_id} lists clip {assigned} more than once"
                )
            seen_assigned.add(assigned)
        scene_assigned[scene_id] = seen_assigned

    for clip in data["clips"]:
        check_required(clip, REQUIRED_CLIP_FIELDS, f"{rel}: clip", errors)
        clip_id = clip.get("clip_id")
        if clip_id in clip_ids:
            errors.append(f"{rel}: duplicate clip_id {clip_id}")
        clip_ids.add(clip_id)
        scene_id = clip.get("scene_id")
        clip_scene[clip_id] = scene_id
        depth = clip.get("extension_depth")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            errors.append(
                f"{rel}: clip {clip_id} extension_depth must be a non-negative integer"
            )
            depth = None
        felt_intent = clip.get("felt_intent")
        if "felt_intent" in clip and (
            not isinstance(felt_intent, str) or not felt_intent.strip()
        ):
            errors.append(
                f"{rel}: clip {clip_id} felt_intent must be a non-empty one-line string"
            )
        if scene_id not in scene_ids:
            errors.append(f"{rel}: clip {clip_id} scene {scene_id} is missing")
        elif (
            scene_id in scene_depth_caps
            and depth is not None
            and depth > scene_depth_caps[scene_id]
        ):
            errors.append(
                f"{rel}: clip {clip_id} extension_depth {depth} exceeds scene "
                f"{scene_id} max_chain_depth {scene_depth_caps[scene_id]}; "
                "open from canonical references instead"
            )
        if clip.get("status") in ACCEPTED:
            accepted_ids.add(clip_id)
            if not clip.get("observed_end_state"):
                errors.append(
                    f"{rel}: accepted clip {clip_id} missing observed_end_state"
                )
        if clip.get("status") == "rejected" and clip.get("observed_end_state"):
            errors.append(
                f"{rel}: rejected clip {clip_id} must not publish observed_end_state as canon"
            )

    validate_relationships(data, rel, clip_ids, accepted_ids, errors)
    validate_assignments(
        rel,
        clip_ids,
        scene_assigned,
        clip_scene,
        errors,
    )
    for reference in data.get("reference_registry", []):
        if not reference.get("preserve_exact_tag"):
            errors.append(
                f"{rel}: reference {reference.get('tag')} must set preserve_exact_tag true"
            )
    if data["current_clip_id"] not in clip_ids:
        errors.append(f"{rel}: current_clip_id missing from clips")
    return errors
