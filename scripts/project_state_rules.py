from __future__ import annotations

import json
from pathlib import Path


REQUIRED_PROJECT_FIELDS = {
    "schema_version", "state_revision", "project_id", "project_mode", "surface",
    "clip_budget_sec", "prompt_budget", "story", "world_bible", "reference_registry",
    "scenes", "beats", "clips", "take_history", "current_clip_id", "canon_revision",
    "updated_at",
}
REQUIRED_SCENE_FIELDS = {
    "scene_id", "scene_index", "narrative_function", "arc_position", "location",
    "time_of_day", "anchor_source", "max_chain_depth", "audio_plan",
    "assigned_clip_ids", "transition_out", "status",
}
REQUIRED_STORY_FIELDS = {
    "logline", "story_promise", "objective", "initial_condition", "final_outcome",
    "target_duration_sec", "tone", "medium",
}
REQUIRED_BEAT_FIELDS = {
    "beat_id", "description", "narrative_function", "status", "assigned_clip_id",
    "dependencies",
}
REQUIRED_CLIP_FIELDS = {
    "clip_id", "parent_clip_id", "scene_id", "sequence_index", "prompt_version",
    "generation_mode", "status", "narrative_job", "felt_intent", "already_happened",
    "this_clip_only", "reserved_for_later", "planned_start_state", "planned_end_state",
    "observed_start_state", "observed_end_state", "continuity_locks", "allowed_changes",
    "continuity_breaks", "accepted_deviations", "transition_in", "transition_out",
    "open_motion_vectors", "handoff_requirements", "extension_depth",
}
REQUIRED_CLIP_CONTRACT_FIELDS = {
    "project_id", "clip_id", "parent_clip_id", "scene_id", "sequence_index",
    "narrative_job", "felt_intent", "target_duration_sec", "generation_mode",
    "shot_structure", "already_happened", "this_clip_only", "reserved_for_later",
    "planned_start_state", "planned_end_state", "continuity_locks", "allowed_changes",
    "status",
}
REQUIRED_TAKE_REVIEW_FIELDS = {
    "project_id", "clip_id", "take_id", "source_status", "verdict",
    "observed_start_state", "observed_end_state", "completed_beats", "incomplete_beats",
    "unexpected_completed_beats", "continuity_breaks", "accepted_deviations",
    "observation_confidence", "uncertainties", "requires_user_confirmation",
}
ARC_POSITIONS = {"open", "rising", "turn", "climax", "release"}
SCENE_STATUSES = {"planned", "current", "completed", "omitted", "replaced"}
MAX_CHAIN_DEPTH_CEILING = 3
ACCEPTED = {"accepted", "accepted_with_deviation"}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def check_required(
    obj: dict,
    required: set[str],
    label: str,
    errors: list[str],
) -> None:
    missing = sorted(required - set(obj))
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(missing)}")


def sequence_paths(root: Path) -> list[Path]:
    if not (root / "examples").exists():
        return []
    return sorted(
        path
        for path in (root / "examples").rglob("*.json")
        if "project-state" in path.name
    )
