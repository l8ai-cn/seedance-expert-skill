#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re


REFERENCE_PATTERNS = {
    "image": re.compile(r"(?:图片|Image)\s*(\d+)", re.IGNORECASE),
    "video": re.compile(r"(?:视频|Video)\s*(\d+)", re.IGNORECASE),
    "audio": re.compile(r"(?:音频|Audio)\s*(\d+)", re.IGNORECASE),
}
TIMELINE_EVENT = re.compile(r"\b\d+(?:\.\d+)?\s*[-–~至]\s*\d+(?:\.\d+)?\s*s\b", re.IGNORECASE)
CAMERA_CONFLICTS = (
    (("推进", "推近", "push in", "dolly in"), ("拉远", "pull out", "dolly out")),
    (("左摇", "pan left"), ("右摇", "pan right")),
    (("上升", "升起", "crane up"), ("下降", "降下", "crane down")),
)


def lint_prompt(
    prompt: str,
    image_count: int = 0,
    video_count: int = 0,
    audio_count: int = 0,
    max_timeline_events: int = 8,
) -> list[str]:
    text = prompt.strip()
    if not text:
        return ["prompt is empty"]

    errors: list[str] = []
    counts = {"image": image_count, "video": video_count, "audio": audio_count}
    for kind, pattern in REFERENCE_PATTERNS.items():
        for match in pattern.finditer(text):
            if int(match.group(1)) > counts[kind]:
                errors.append(f"unresolved {kind} reference: {match.group(0)}")

    lowered = text.lower()
    for first_moves, second_moves in CAMERA_CONFLICTS:
        first = next((move for move in first_moves if move in lowered), None)
        second = next((move for move in second_moves if move in lowered), None)
        if first and second:
            errors.append(f"conflicting primary camera moves: {first} and {second}")

    event_count = len(TIMELINE_EVENT.findall(text))
    if event_count > max_timeline_events:
        errors.append(
            f"timeline has {event_count} events; split the clip or keep at most "
            f"{max_timeline_events}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint a Seedance production prompt.")
    parser.add_argument("prompt")
    parser.add_argument("--image-count", type=int, default=0)
    parser.add_argument("--video-count", type=int, default=0)
    parser.add_argument("--audio-count", type=int, default=0)
    args = parser.parse_args()

    errors = lint_prompt(
        args.prompt,
        image_count=args.image_count,
        video_count=args.video_count,
        audio_count=args.audio_count,
    )
    if errors:
        for error in errors:
            print(f"- {error}")
        return 1
    print("Seedance prompt lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
