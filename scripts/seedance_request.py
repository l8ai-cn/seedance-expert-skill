from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping

from scripts.seedance_url_policy import DEFAULT_API_BASE_URL, validate_api_base_url, validate_https_url


RATIOS = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
RESOLUTIONS = ("480p", "720p", "1080p")
REFERENCE_ROLES = {
    "image_url": {None, "first_frame", "last_frame", "reference_image"},
    "video_url": {None, "reference_video"},
    "audio_url": {None, "reference_audio"},
}
DEFAULT_ROLES = {
    "video_url": "reference_video",
    "audio_url": "reference_audio",
}
REFERENCE_LIMITS = {
    "image_url": 9,
    "video_url": 3,
    "audio_url": 3,
}
MAX_REFERENCES = 12
ARK_SEEDANCE_MODEL_PREFIX = "doubao-seedance-"


@dataclass(frozen=True)
class ReferenceInput:
    kind: str
    url: str
    role: str | None = None

    def content(self) -> dict:
        item = {"type": self.kind, self.kind: {"url": self.url}}
        if self.role:
            item["role"] = self.role
        return item


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    model: str
    duration: int = 5
    ratio: str = "16:9"
    resolution: str = "720p"
    generate_audio: bool = True
    watermark: bool = False
    references: tuple[ReferenceInput, ...] = field(default_factory=tuple)

    def content(self) -> list[dict]:
        return [
            {"type": "text", "text": self.prompt},
            *(reference.content() for reference in self.references),
        ]

    def payload(self) -> dict:
        return {
            "model": self.model,
            "content": self.content(),
            "duration": self.duration,
            "ratio": self.ratio,
            "resolution": self.resolution,
            "generate_audio": self.generate_audio,
            "watermark": self.watermark,
        }

    def approval_document(self, base_url: str = DEFAULT_API_BASE_URL) -> bytes:
        endpoint = f"{validate_api_base_url(base_url)}/contents/generations/tasks"
        return json.dumps(
            {"body": self.payload(), "method": "POST", "url": endpoint},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def metadata(self) -> dict:
        return self.payload()


def parse_reference(kind: str, value: str) -> ReferenceInput:
    allowed_roles = REFERENCE_ROLES[kind]
    prefix, separator, remainder = value.partition("=")
    if separator and prefix in allowed_roles:
        role, url = prefix, remainder
    else:
        role, url = DEFAULT_ROLES.get(kind), value
    reference = ReferenceInput(kind, url.strip(), role)
    validate_reference(reference)
    return reference


def validate_reference(reference: ReferenceInput) -> None:
    if reference.kind not in REFERENCE_ROLES:
        raise ValueError(f"unsupported reference type: {reference.kind}")
    if not reference.url:
        raise ValueError(f"{reference.kind} URL is required")
    if reference.role not in REFERENCE_ROLES[reference.kind]:
        raise ValueError(f"invalid role {reference.role!r} for {reference.kind}")
    validate_https_url(reference.url, label=f"{reference.kind} URL")


def validate_generation_request(request: GenerationRequest) -> None:
    if not request.prompt.strip():
        raise ValueError("prompt is required")
    model = request.model.strip()
    if not model:
        raise ValueError("model is required")
    if not model.startswith(ARK_SEEDANCE_MODEL_PREFIX):
        raise ValueError(
            "model must be a Volcengine Ark Seedance video model "
            f"starting with {ARK_SEEDANCE_MODEL_PREFIX!r}"
        )
    if not 4 <= request.duration <= 15:
        raise ValueError("duration must be an integer from 4 to 15 seconds")
    if request.ratio not in RATIOS:
        raise ValueError(f"ratio must be one of: {', '.join(RATIOS)}")
    if request.resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of: {', '.join(RESOLUTIONS)}")
    for reference in request.references:
        validate_reference(reference)
    counts = {
        kind: sum(reference.kind == kind for reference in request.references)
        for kind in REFERENCE_LIMITS
    }
    for kind, limit in REFERENCE_LIMITS.items():
        if counts[kind] > limit:
            label = kind.removesuffix("_url")
            raise ValueError(f"at most {limit} {label} references are allowed")
    if len(request.references) > MAX_REFERENCES:
        raise ValueError(f"at most {MAX_REFERENCES} total references are allowed")
    if any(item.kind == "audio_url" for item in request.references) and not any(
        item.kind in {"image_url", "video_url"} for item in request.references
    ):
        raise ValueError("audio_url requires at least one image_url or video_url reference")


def approval_fingerprint(
    request: GenerationRequest,
    base_url: str = DEFAULT_API_BASE_URL,
) -> str:
    validate_generation_request(request)
    return hashlib.sha256(request.approval_document(base_url)).hexdigest()


def approval_fingerprint_for_payload(
    payload: Mapping[str, object],
    base_url: str,
) -> str:
    endpoint = f"{validate_api_base_url(base_url)}/contents/generations/tasks"
    document = json.dumps(
        {"body": payload, "method": "POST", "url": endpoint},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(document).hexdigest()
