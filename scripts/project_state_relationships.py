from __future__ import annotations

from scripts.project_state_rules import REQUIRED_BEAT_FIELDS, check_required


def validate_relationships(
    data: dict,
    rel: str,
    clip_ids: set[object],
    accepted_ids: set[object],
    errors: list[str],
) -> None:
    for clip in data["clips"]:
        clip_id = clip.get("clip_id")
        parent = clip.get("parent_clip_id")
        if clip.get("sequence_index", 1) > 1:
            if not parent:
                errors.append(f"{rel}: later clip {clip_id} missing parent_clip_id")
            elif parent not in clip_ids:
                errors.append(f"{rel}: later clip {clip_id} parent {parent} is missing")
            elif clip.get("status") != "planned" and parent not in accepted_ids:
                errors.append(
                    f"{rel}: later clip {clip_id} parent {parent} is not accepted"
                )
        current = set(clip.get("this_clip_only", []))
        reserved = set(clip.get("reserved_for_later", []))
        completed = set(clip.get("already_happened", []))
        if current & reserved:
            errors.append(
                f"{rel}: clip {clip_id} overlaps current and reserved beats: "
                f"{sorted(current & reserved)}"
            )
        if completed & current:
            errors.append(
                f"{rel}: clip {clip_id} replays completed beats: "
                f"{sorted(completed & current)}"
            )
    for beat in data["beats"]:
        check_required(beat, REQUIRED_BEAT_FIELDS, f"{rel}: beat", errors)
        assigned = beat.get("assigned_clip_id")
        if assigned is not None and assigned not in clip_ids:
            errors.append(
                f"{rel}: beat {beat.get('beat_id')} assigned to missing clip {assigned}"
            )


def validate_assignments(
    rel: str,
    clip_ids: set[object],
    scene_assigned: dict[object, set[object]],
    clip_scene: dict[object, object],
    errors: list[str],
) -> None:
    owners: dict[object, list[object]] = {}
    for scene_id, assigned_set in scene_assigned.items():
        for assigned in assigned_set:
            if assigned not in clip_ids:
                errors.append(
                    f"{rel}: scene {scene_id} assigned to missing clip {assigned}"
                )
            owners.setdefault(assigned, []).append(scene_id)
    for clip_id, scene_owners in owners.items():
        if len(scene_owners) > 1:
            errors.append(
                f"{rel}: clip {clip_id} is assigned to multiple scenes: "
                f"{sorted(scene_owners)}"
            )
    for clip_id, scene_id in clip_scene.items():
        if scene_id in scene_assigned and clip_id not in scene_assigned[scene_id]:
            errors.append(
                f"{rel}: clip {clip_id} carries scene_id {scene_id} but scene "
                f"{scene_id} does not list it in assigned_clip_ids"
            )
        scene_owners = owners.get(clip_id, [])
        if scene_owners and scene_id not in scene_owners:
            errors.append(
                f"{rel}: clip {clip_id} carries scene_id {scene_id} but is listed "
                f"under scene {scene_owners[0]}"
            )
