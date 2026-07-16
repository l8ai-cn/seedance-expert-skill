#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seedance_ark_client import ArkSeedanceClient
from scripts.seedance_prompt_lint import lint_prompt
from scripts.seedance_request import (
    RATIOS,
    RESOLUTIONS,
    GenerationRequest,
    ReferenceInput,
    approval_fingerprint,
    parse_reference,
    validate_ark_seedance_model,
    validate_generation_request,
)
from scripts.seedance_task import generate, resume
from scripts.seedance_url_policy import DEFAULT_API_BASE_URL, validate_api_base_url


def parser_for_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a video with Volcengine Ark Seedance.")
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--resume", type=Path, help="Resume an existing task metadata file.")
    parser.add_argument(
        "--check-credentials",
        action="store_true",
        help="Check Ark credentials through the non-billing task-list API.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--ratio", choices=RATIOS, default="16:9")
    parser.add_argument("--resolution", choices=RESOLUTIONS, default="720p")
    parser.add_argument("--image-url", action="append", default=[], metavar="[ROLE=]URL")
    parser.add_argument("--video-url", action="append", default=[], metavar="[ROLE=]URL")
    parser.add_argument("--audio-url", action="append", default=[], metavar="[ROLE=]URL")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--watermark", action="store_true")
    parser.add_argument("--print-approval", action="store_true")
    parser.add_argument("--approval")
    parser.add_argument("--poll-interval", type=_positive_float, default=10)
    parser.add_argument("--max-wait", type=_positive_float, default=1800)
    return parser


def _generation_request(args: argparse.Namespace, parser: argparse.ArgumentParser) -> GenerationRequest:
    if not args.prompt:
        parser.error("prompt is required unless --resume is used")
    if not args.output:
        parser.error("--output is required unless --resume is used")
    references = []
    try:
        for kind, values in (
            ("image_url", args.image_url),
            ("video_url", args.video_url),
            ("audio_url", args.audio_url),
        ):
            references.extend(parse_reference(kind, value) for value in values)
        request = GenerationRequest(
            prompt=args.prompt,
            model=os.environ.get("SEEDANCE_MODEL", "").strip(),
            duration=args.duration,
            ratio=args.ratio,
            resolution=args.resolution,
            generate_audio=not args.no_audio,
            watermark=args.watermark,
            references=tuple(references),
        )
        validate_generation_request(request)
    except ValueError as error:
        parser.error(str(error))
    errors = lint_prompt(
        request.prompt,
        image_count=sum(item.kind == "image_url" for item in request.references),
        video_count=sum(item.kind == "video_url" for item in request.references),
        audio_count=sum(item.kind == "audio_url" for item in request.references),
    )
    if errors:
        parser.error("; ".join(errors))
    return request


def _base_url(parser: argparse.ArgumentParser) -> str:
    try:
        return validate_api_base_url(
            os.environ.get("SEEDANCE_BASE_URL", DEFAULT_API_BASE_URL),
        )
    except ValueError as error:
        parser.error(str(error))


def _client(parser: argparse.ArgumentParser, base_url: str) -> ArkSeedanceClient:
    try:
        return ArkSeedanceClient(
            os.environ.get("SEEDANCE_API_KEY", ""),
            base_url,
            allowed_api_hosts=_allowed_api_hosts(),
        )
    except ValueError as error:
        parser.error(str(error))


def _allowed_api_hosts() -> set[str]:
    raw = os.environ.get("SEEDANCE_ALLOWED_API_HOSTS", "")
    hosts = set()
    for value in raw.split(","):
        host = value.strip().lower()
        if not host:
            continue
        parsed = urlsplit("//" + host)
        if (
            parsed.hostname != host
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise ValueError(
                "SEEDANCE_ALLOWED_API_HOSTS must contain comma-separated hostnames only"
            )
        hosts.add(host)
    return hosts


def main() -> int:
    parser = parser_for_cli()
    args = parser.parse_args()
    base_url = _base_url(parser)
    if args.check_credentials:
        if args.prompt or args.resume or args.output or args.print_approval or args.approval:
            parser.error("--check-credentials cannot be combined with generation arguments")
        try:
            model = validate_ark_seedance_model(os.environ.get("SEEDANCE_MODEL", ""))
            _client(parser, base_url).check_credentials(model)
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        print("credentials verified; generation entitlement not verified")
        return 0
    if args.resume:
        if args.prompt or args.output or args.print_approval or args.approval:
            parser.error("--resume cannot be combined with generation or approval arguments")
        try:
            metadata = resume(
                _client(parser, base_url),
                args.resume,
                poll_interval=args.poll_interval,
                max_wait=args.max_wait,
            )
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        print(metadata)
        return 0

    request = _generation_request(args, parser)
    fingerprint = approval_fingerprint(request, base_url)
    if args.print_approval:
        print(fingerprint)
        return 0
    if args.approval != fingerprint:
        parser.error("approval fingerprint does not match this exact request")
    try:
        metadata = generate(
            _client(parser, base_url),
            request,
            args.output,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(metadata)
    return 0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
