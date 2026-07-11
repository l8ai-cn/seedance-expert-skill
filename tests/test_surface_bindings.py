from __future__ import annotations

import ast
import copy
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

from scripts import content_audit, profile_check
from scripts import render_surface_bindings as renderer


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_surface_bindings.py"
FRESH_DATE = date(2026, 7, 17)
EXPIRED_DATE = date(2026, 7, 18)


def opaque_plan(
    handle: str,
    *,
    profile_id: str = "byteplus.modelark",
    binding_id: str = "subject",
    media_type: str = "image",
    suffix: str = " remains unchanged.",
) -> dict:
    return {
        "$schema": renderer.PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": profile_id,
        "operation": "reference_generation",
        "segments": [
            {"kind": "binding", "binding_id": binding_id},
            {"kind": "text", "value": suffix},
        ],
        "bindings": [
            {
                "binding_id": binding_id,
                "media_type": media_type,
                "prompt_visible_handle": handle,
            }
        ],
    }


def structured_plan() -> dict:
    return {
        "$schema": renderer.PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": "volcengine.ark",
        "operation": "first_last_frame",
        "segments": [
            {
                "kind": "text",
                "value": "Complete one continuous action between the supplied frames.",
            }
        ],
        "bindings": [
            {"binding_id": "opening", "media_type": "image", "structured_role": "first_frame"},
            {"binding_id": "endpoint", "media_type": "image", "structured_role": "last_frame"},
        ],
    }


def derived_plan(*, profile_id: str = "fal.reference-to-video") -> dict:
    return {
        "$schema": renderer.PLAN_SCHEMA_URI,
        "schema_version": 1,
        "profile_id": profile_id,
        "operation": "reference_generation",
        "segments": [
            {"kind": "binding", "binding_id": "subject"},
            {"kind": "text", "value": " controls subject identity."},
        ],
        "bindings": [{"binding_id": "subject", "media_type": "image"}],
    }


def copy_profiles(destination: Path) -> None:
    shutil.copytree(ROOT / "profiles", destination / "profiles")


class SurfaceBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = renderer.load_registry(ROOT)

    def render(self, plan: dict, *, today: date = FRESH_DATE) -> dict:
        with mock.patch.object(renderer, "load_registry", return_value=self.registry):
            return renderer.render_plan(plan, preview_candidate=True, today=today)

    def test_repository_profiles_are_evidence_locked_and_non_activating(self) -> None:
        errors, counts = profile_check.check_profiles(ROOT, today=FRESH_DATE)
        self.assertEqual(errors, [])
        self.assertEqual(
            counts,
            {
                "model_profiles": 1,
                "surface_profiles": 3,
                "surface_operations": 4,
                "evidence_pins": 9,
            },
        )
        self.assertFalse(self.registry.index["activation_enabled"])
        self.assertFalse(renderer.ACTIVATION_SUPPORTED)
        for profile in [*self.registry.models.values(), *self.registry.surfaces.values()]:
            self.assertEqual(profile.data["status"], "candidate")
            self.assertFalse(profile.data["runtime_enabled"])

    def test_opaque_handle_round_trip_corpus(self) -> None:
        handles = [
            "@Image1",
            "@Image 1",
            "  leading and trailing  ",
            "[Video 1]",
            "[[custom @ handle]]",
            "@@@ reference @@@",
            "图片1",
            "产品 主图",
            "Кадр №1",
            "مرجع-١",
            "e\u0301",
            "é",
            "👩🏽\u200d🚀 frame",
            "𠮷野家",
            "{img1}",
            "{{binding:img1}}",
            "${img1}",
            "$()[]{}\\\"'",
        ]
        for handle in handles:
            with self.subTest(handle=handle):
                result = self.render(opaque_plan(handle))
                rendered_handle = result["rendered_prompt"][: len(handle)]
                self.assertEqual(rendered_handle.encode("utf-8"), handle.encode("utf-8"))

    def test_ten_thousand_seeded_unicode_handles_round_trip(self) -> None:
        rng = random.Random(705)
        alphabet = [
            *"@ []{}()$%_-.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            "图", "片", "视", "频", "音", "频", "参", "考",
            "Ж", "я", "م", "ر", "ج", "ع",
            "é", "e", "\u0301", "👩", "🏽", "🚀", "👩🏽\u200d🚀", "𠮷",
        ]
        for index in range(10_000):
            length = rng.randint(1, 24)
            handle = "h" + "".join(rng.choice(alphabet) for _ in range(length))
            if index % 13 == 0:
                handle = " " + handle
            if index % 17 == 0:
                handle += " "
            result = self.render(opaque_plan(handle, suffix=" is exact."))
            self.assertEqual(
                result["rendered_prompt"][: len(handle)].encode("utf-8"),
                handle.encode("utf-8"),
            )

    def test_every_unsafe_handle_control_is_rejected_without_echo(self) -> None:
        unsafe = [
            *range(0x00, 0x20),
            *range(0x7F, 0xA0),
            *sorted(renderer.FORBIDDEN_HANDLE_CODEPOINTS),
            0xD800,
            0xDFFF,
            0x00AD,
            0x200B,
            0x2060,
            0x2061,
            0x2062,
            0x2063,
            0x2064,
            0xE0020,
            0xE007F,
        ]
        for codepoint in unsafe:
            handle = "safe" + chr(codepoint) + "sentinel"
            with self.subTest(codepoint=hex(codepoint)):
                with self.assertRaises(renderer.BindingError) as caught:
                    renderer._validate_handle(handle, "/handle")
                self.assertNotIn("sentinel", str(caught.exception))

        for invisible in (" ", "   ", "\u0301", "\u200d"):
            with self.subTest(invisible=repr(invisible)), self.assertRaises(renderer.BindingError):
                renderer._validate_handle(invisible, "/handle")

        self.assertEqual(renderer._validate_handle("👩🏽\u200d🚀 frame", "/handle"), "👩🏽\u200d🚀 frame")

    def test_binding_segments_never_parse_literal_placeholders(self) -> None:
        literals = ["${img1}", "{img1}", "{{binding:img1}}", "@img1", "img1/img10"]
        plan = opaque_plan("EXACT HANDLE", suffix=" " + " | ".join(literals))
        result = self.render(plan)
        self.assertEqual(result["rendered_prompt"], "EXACT HANDLE " + " | ".join(literals))

    def test_handle_collision_matrix(self) -> None:
        pairs = [
            ("same", "same"),
            ("é", "e\u0301"),
            ("IMAGE", "image"),
            ("Straße", "STRASSE"),
            ("☀☀", "☀\u200d☀"),
            ("👩🚀", "👩\u200d🚀"),
        ]
        for first, second in pairs:
            plan = opaque_plan(first)
            plan["segments"].extend(
                [
                    {"kind": "text", "value": " and "},
                    {"kind": "binding", "binding_id": "second"},
                ]
            )
            plan["bindings"].append(
                {
                    "binding_id": "second",
                    "media_type": "image",
                    "prompt_visible_handle": second,
                }
            )
            with self.subTest(first=first, second=second), self.assertRaisesRegex(
                renderer.BindingError, "HANDLE_COLLISION"
            ):
                self.render(plan)

        duplicate_id = opaque_plan("first")
        duplicate_id["bindings"].append(copy.deepcopy(duplicate_id["bindings"][0]))
        with self.assertRaisesRegex(renderer.BindingError, "BINDING_ID_DUPLICATE"):
            self.render(duplicate_id)

    def test_surface_owned_ordinals_are_derived_from_media_and_position(self) -> None:
        plan = derived_plan()
        plan["segments"] = [
            {"kind": "binding", "binding_id": "image-a"},
            {"kind": "text", "value": " with "},
            {"kind": "binding", "binding_id": "video-a"},
            {"kind": "text", "value": " then "},
            {"kind": "binding", "binding_id": "image-b"},
            {"kind": "text", "value": " over "},
            {"kind": "binding", "binding_id": "audio-a"},
            {"kind": "text", "value": "."},
        ]
        plan["bindings"] = [
            {"binding_id": "image-a", "media_type": "image"},
            {"binding_id": "video-a", "media_type": "video"},
            {"binding_id": "image-b", "media_type": "image"},
            {"binding_id": "audio-a", "media_type": "audio"},
        ]
        result = self.render(plan)
        self.assertEqual(result["request_transport"], "typed_media_arrays")
        self.assertEqual(
            result["request_bindings"],
            [
                {"binding_id": "image-a", "media_type": "image", "request_position": 1},
                {"binding_id": "video-a", "media_type": "video", "request_position": 1},
                {"binding_id": "image-b", "media_type": "image", "request_position": 2},
                {"binding_id": "audio-a", "media_type": "audio", "request_position": 1},
            ],
        )
        self.assertEqual(result["rendered_prompt"], "@Image1 with @Video1 then @Image2 over @Audio1.")

        fal_image = self.render(derived_plan())
        volc = self.render(derived_plan(profile_id="volcengine.ark"))
        self.assertEqual(volc["request_transport"], "ordered_content_objects")
        self.assertEqual(fal_image["rendered_prompt"], "@Image1 controls subject identity.")
        self.assertEqual(volc["rendered_prompt"], "图片1 controls subject identity.")
        self.assertNotEqual(fal_image["rendered_prompt"], volc["rendered_prompt"])

        for mismatch in ("@Video99", "@Image 1", "图片1"):
            bad = derived_plan()
            bad["bindings"][0]["prompt_visible_handle"] = mismatch
            with self.subTest(mismatch=mismatch), self.assertRaisesRegex(
                renderer.BindingError, "DERIVED_BINDING_FIELDS_INVALID"
            ):
                self.render(bad)

        for unsupported in ("audio", "video"):
            bad = derived_plan(profile_id="volcengine.ark")
            bad["bindings"][0]["media_type"] = unsupported
            with self.subTest(volc_media=unsupported), self.assertRaisesRegex(
                renderer.BindingError, "BINDING_MEDIA_UNSUPPORTED"
            ):
                self.render(bad)

    def test_structured_roles_never_create_prompt_tokens(self) -> None:
        result = self.render(structured_plan())
        self.assertEqual(result["request_transport"], "structured_content_roles")
        self.assertEqual(
            result["request_bindings"],
            [
                {"binding_id": "opening", "media_type": "image", "structured_role": "first_frame"},
                {"binding_id": "endpoint", "media_type": "image", "structured_role": "last_frame"},
            ],
        )
        self.assertNotIn("opening", result["rendered_prompt"])
        self.assertNotIn("endpoint", result["rendered_prompt"])
        self.assertNotIn("@", result["rendered_prompt"])

        bad = structured_plan()
        bad["segments"].append({"kind": "binding", "binding_id": "opening"})
        with self.assertRaisesRegex(renderer.BindingError, "STRUCTURED_BINDING_IN_PROMPT"):
            self.render(bad)

        for literal in ("@Image1 is first.", "@Image 1 is first.", "[Video 1] is first.", "图片1是首帧。"):
            bad = structured_plan()
            bad["segments"][0]["value"] = literal
            with self.subTest(literal=literal), self.assertRaisesRegex(
                renderer.BindingError, "REFERENCE_TOKEN_IN_TEXT_FORBIDDEN"
            ):
                self.render(bad)

        for profile_id, literal in (
            ("fal.reference-to-video", "Use @Image99 and @Video42."),
            ("volcengine.ark", "请使用图片99。"),
        ):
            bad = derived_plan(profile_id=profile_id)
            bad["segments"][1]["value"] = literal
            with self.subTest(profile=profile_id), self.assertRaisesRegex(
                renderer.BindingError, "REFERENCE_TOKEN_IN_TEXT_FORBIDDEN"
            ):
                self.render(bad)

        opaque = opaque_plan("custom-handle", suffix=" also use @Image999.")
        with self.assertRaisesRegex(renderer.BindingError, "REFERENCE_TOKEN_IN_TEXT_FORBIDDEN"):
            self.render(opaque)

    def test_reference_tokens_cannot_be_split_or_mutated_around_typed_bindings(self) -> None:
        split_cases = [
            ("fal.reference-to-video", " plus @Image", "99 is stale."),
            ("fal.reference-to-video", " plus @iMaGe", "99 is stale."),
            ("volcengine.ark", " 加上图像", "99。"),
        ]
        for profile_id, first, second in split_cases:
            plan = derived_plan(profile_id=profile_id)
            plan["segments"].extend(
                [
                    {"kind": "text", "value": first},
                    {"kind": "text", "value": second},
                ]
            )
            with self.subTest(profile=profile_id, first=first), self.assertRaisesRegex(
                renderer.BindingError, "REFERENCE_TOKEN_PROVENANCE_INVALID"
            ):
                self.render(plan)

        for profile_id in ("fal.reference-to-video", "volcengine.ark"):
            plan = derived_plan(profile_id=profile_id)
            plan["segments"][1]["value"] = "99 controls subject identity."
            with self.subTest(profile=profile_id), self.assertRaisesRegex(
                renderer.BindingError, "BINDING_DELIMITER_REQUIRED"
            ):
                self.render(plan)

        adjacent = derived_plan()
        adjacent["bindings"].append({"binding_id": "environment", "media_type": "image"})
        adjacent["segments"] = [
            {"kind": "binding", "binding_id": "subject"},
            {"kind": "binding", "binding_id": "environment"},
        ]
        with self.assertRaisesRegex(renderer.BindingError, "BINDING_DELIMITER_REQUIRED"):
            self.render(adjacent)

        for suffix in (
            " controls identity.",
            "：锁定主体身份。",
            "：人物の同一性を固定する。",
            ": 인물 정체성을 고정한다.",
        ):
            plan = derived_plan()
            plan["segments"][1]["value"] = suffix
            with self.subTest(suffix=suffix):
                self.assertEqual(self.render(plan)["rendered_prompt"], "@Image1" + suffix)

    def test_reference_token_schema_and_runtime_detection_agree(self) -> None:
        schema = json.loads((ROOT / "schemas" / "binding-plan.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for literal in (
            " Image1 is stale.",
            " [Image1] is stale.",
            " [Audio1 role] is stale.",
            " @IMAGE1 is stale.",
            " 图像1已过期。",
            " 视频 2已过期。",
        ):
            plan = opaque_plan("surface-handle", suffix=literal)
            with self.subTest(literal=literal):
                self.assertTrue(list(validator.iter_errors(plan)))
                with self.assertRaisesRegex(renderer.BindingError, "REFERENCE_TOKEN_IN_TEXT_FORBIDDEN"):
                    self.render(plan)

        safe = opaque_plan("surface-handle", suffix=" myImage1 field is semantic metadata.")
        self.assertEqual(list(validator.iter_errors(safe)), [])
        self.assertTrue(self.render(safe)["rendered_prompt"].endswith(safe["segments"][1]["value"]))

    def test_profile_operation_cross_product_fails_closed(self) -> None:
        supported = {
            "byteplus.modelark": {"reference_generation"},
            "fal.reference-to-video": {"reference_generation"},
            "volcengine.ark": {"reference_generation", "first_last_frame"},
        }
        for profile_id, operations in supported.items():
            for operation in renderer.OPERATIONS - operations:
                plan = opaque_plan("surface handle", profile_id=profile_id)
                plan["operation"] = operation
                with self.subTest(profile=profile_id, operation=operation), self.assertRaisesRegex(
                    renderer.BindingError, "OPERATION_UNSUPPORTED"
                ):
                    self.render(plan)

        unknown = opaque_plan("surface handle", profile_id="unknown.surface")
        with self.assertRaisesRegex(renderer.BindingError, "PROFILE_UNKNOWN"):
            self.render(unknown)

    def test_missing_handle_never_synthesizes_a_default(self) -> None:
        plan = opaque_plan("temporary")
        del plan["bindings"][0]["prompt_visible_handle"]
        with self.assertRaisesRegex(renderer.BindingError, "OPAQUE_BINDING_FIELDS_INVALID"):
            self.render(plan)

    def test_candidate_and_expiry_gates_cannot_be_bypassed(self) -> None:
        with mock.patch.object(renderer, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(renderer.BindingError, "PROFILE_CANDIDATE_REQUIRES_PREVIEW"):
                renderer.render_plan(opaque_plan("@custom"), today=FRESH_DATE)
        with self.assertRaisesRegex(renderer.BindingError, "PROFILE_EVIDENCE_EXPIRED"):
            self.render(opaque_plan("@custom"), today=EXPIRED_DATE)
        self.assertNotIn("--as-of", SCRIPT.read_text(encoding="utf-8"))

    def test_model_and_operation_evidence_jointly_gate_rendering(self) -> None:
        registry = copy.deepcopy(self.registry)
        operation = registry.surfaces["byteplus.modelark"].data["operations"][0]
        for pin in operation["evidence_pins"]:
            pin["expires_at"] = "2028-01-01"
        for pin in registry.models["seedance-2.0-model"].data["evidence_pins"]:
            pin["expires_at"] = "2027-01-07"
        with mock.patch.object(renderer, "load_registry", return_value=registry):
            with self.assertRaisesRegex(renderer.BindingError, "PROFILE_EVIDENCE_EXPIRED"):
                renderer.render_plan(
                    opaque_plan("@custom"),
                    preview_candidate=True,
                    today=date(2027, 1, 7),
                )

        result = self.render(opaque_plan("@custom"))
        self.assertEqual(
            result["evidence_claim_ids"],
            [
                "bytedance.model.multimodal-inputs",
                "bytedance.model.reference-control",
                "global.binding.no-universal-token",
                "bp.binding.spaced-example-token",
            ],
        )

    def test_unknown_fields_and_media_secrets_do_not_leak(self) -> None:
        sentinel = "SECRET-SIGNED-URL-705"
        plan = opaque_plan("@custom")
        plan["bindings"][0]["media_url"] = sentinel
        with self.assertRaises(renderer.BindingError) as caught:
            self.render(plan)
        self.assertNotIn(sentinel, str(caught.exception))

        payload = opaque_plan("@custom")
        payload["api_key"] = sentinel
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--preview-candidate"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertNotIn(sentinel, completed.stderr)

    def test_strict_json_parser_matrix(self) -> None:
        invalid = [
            b"\xef\xbb\xbf{}",
            b'{"value":1,"value":2}',
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b"\xff",
            b"{",
            b'{"value":"\\ud800"}',
        ]
        for raw in invalid:
            with self.subTest(raw=raw[:20]), self.assertRaises(renderer.BindingError):
                renderer.parse_json_bytes(raw)
        deep: object = "leaf"
        for _ in range(renderer.MAX_JSON_DEPTH + 2):
            deep = [deep]
        with self.assertRaisesRegex(renderer.BindingError, "JSON_TOO_DEEP"):
            renderer.parse_json_bytes(json.dumps(deep).encode())
        with self.assertRaisesRegex(renderer.BindingError, "JSON_TOO_LARGE"):
            renderer.parse_json_bytes(b" " * (renderer.MAX_INPUT_BYTES + 1))

    def test_text_segment_limit_and_unicode_format_controls_fail_closed(self) -> None:
        accepted_suffix = " " + "x" * (renderer.MAX_TEXT_SEGMENT - 1)
        accepted = opaque_plan("@custom", suffix=accepted_suffix)
        result = self.render(accepted)
        self.assertTrue(result["rendered_prompt"].endswith(accepted_suffix))

        rejected = opaque_plan("@custom", suffix=" " + "x" * renderer.MAX_TEXT_SEGMENT)
        with self.assertRaisesRegex(renderer.BindingError, "TEXT_SEGMENT_TOO_LARGE"):
            self.render(rejected)

        independent_bidi_controls = [
            0x061C, 0x200E, 0x200F,
            *range(0x202A, 0x202F),
            *range(0x2066, 0x2070),
        ]
        for codepoint in independent_bidi_controls:
            with self.subTest(codepoint=hex(codepoint)):
                raw = json.dumps({"value": "safe" + chr(codepoint) + "text"}, ensure_ascii=False).encode()
                with self.assertRaisesRegex(renderer.BindingError, "UNICODE_FORMAT_CONTROL_FORBIDDEN"):
                    renderer.parse_json_bytes(raw)

        for codepoint in [
            *range(0x00, 0x09),
            0x0B,
            0x0C,
            *range(0x0E, 0x20),
            *range(0x7F, 0xA0),
        ]:
            bad = opaque_plan("@custom", suffix="safe" + chr(codepoint) + "text")
            with self.subTest(text_control=hex(codepoint)), self.assertRaisesRegex(
                renderer.BindingError, "TEXT_CONTROL_FORBIDDEN"
            ):
                self.render(bad)

        multiline = opaque_plan("@custom", suffix=" line one\nline two\tend\r")
        self.assertIn(" line one\nline two\tend\r", self.render(multiline)["rendered_prompt"])

    def test_adversarial_json_and_wrong_types_never_escape_as_tracebacks(self) -> None:
        wrong_operation = opaque_plan("@custom")
        wrong_operation["operation"] = []
        wrong_kind = opaque_plan("@custom")
        wrong_kind["segments"][0]["kind"] = {}
        wrong_media = opaque_plan("@custom")
        wrong_media["bindings"][0]["media_type"] = []
        cases = [
            json.dumps(wrong_operation).encode(),
            json.dumps(wrong_kind).encode(),
            json.dumps(wrong_media).encode(),
            b'{' + b'"unknown":' + (b"9" * 5_000) + b'}',
            (b"[" * 10_000) + b"0" + (b"]" * 10_000),
            b'{"unknown":1e999999}',
        ]
        for raw in cases:
            with self.subTest(prefix=raw[:30]):
                completed = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "--preview-candidate"],
                    input=raw,
                    capture_output=True,
                    cwd=ROOT,
                )
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(completed.stdout, b"")
                self.assertTrue(completed.stderr.startswith(b"binding-render error:"))
                self.assertNotIn(b"Traceback", completed.stderr)

    def test_internal_profile_hash_and_link_attacks_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_profiles(root)
            target = root / "profiles" / "surfaces" / "byteplus-modelark.json"
            target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaisesRegex(renderer.BindingError, "PROFILE_HASH_MISMATCH"):
                renderer.load_registry(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_profiles(root)
            target = root / "profiles" / "surfaces" / "byteplus-modelark.json"
            backup = root / "profile-backup.json"
            shutil.copyfile(target, backup)
            target.unlink()
            try:
                target.symlink_to(backup)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(renderer.BindingError, "FILE_(?:LINK_FORBIDDEN|REGULAR_REQUIRED)"):
                renderer.load_registry(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_profiles(root)
            target = root / "profiles" / "surfaces" / "byteplus-modelark.json"
            alias = root / "profile-hardlink.json"
            try:
                os.link(target, alias)
            except OSError:
                self.skipTest("hard links are unavailable")
            with self.assertRaisesRegex(renderer.BindingError, "FILE_HARDLINK_FORBIDDEN"):
                renderer.load_registry(root)

    def test_input_file_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "request.json"
            target.write_text(json.dumps(opaque_plan("@custom")), encoding="utf-8")
            link = root / "link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(renderer.BindingError, "FILE_LINK_FORBIDDEN"):
                renderer._read_request(str(link))

    def test_input_file_same_inode_rewrite_is_detected_by_ctime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            old = b'A' * 130_000
            new = b'B' * len(old)
            path.write_bytes(old)
            before = path.stat()
            real_read = renderer.os.read
            mutated = False

            def mutate_after_first_read(descriptor: int, size: int) -> bytes:
                nonlocal mutated
                chunk = real_read(descriptor, size)
                if chunk and not mutated:
                    mutated = True
                    path.write_bytes(new)
                    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                return chunk

            with mock.patch.object(renderer.os, "read", side_effect=mutate_after_first_read):
                with self.assertRaisesRegex(renderer.BindingError, "FILE_CHANGED_DURING_READ"):
                    renderer._read_plain_file(path, renderer.MAX_INPUT_BYTES)

    @unittest.skipUnless(renderer.SECURE_DIRFD_SUPPORTED, "secure descriptor walking is unavailable")
    def test_profile_ancestor_swap_cannot_redirect_descriptor_walk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            safe_parent = root / "walk" / "a"
            safe_parent.mkdir(parents=True)
            (safe_parent / "file.txt").write_text("inside\n", encoding="utf-8")
            outside = Path(temporary) / "outside"
            outside.mkdir()
            moved = outside / "moved"
            real_open = renderer.os.open
            swapped = False

            def swap_before_leaf(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "file.txt" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    safe_parent.rename(moved)
                    safe_parent.mkdir()
                    (safe_parent / "file.txt").write_text("attacker\n", encoding="utf-8")
                return real_open(path, flags, *args, **kwargs)

            try:
                with mock.patch.object(renderer.os, "open", side_effect=swap_before_leaf):
                    raw = renderer.read_internal_bytes(root, "walk/a/file.txt")
            except renderer.BindingError as exc:
                self.assertEqual(exc.code, "FILE_ANCESTOR_CHANGED")
            else:
                self.assertEqual(raw, b"inside\n")
                self.assertNotEqual(raw, (safe_parent / "file.txt").read_bytes())

    def test_render_is_byte_deterministic_across_ten_processes(self) -> None:
        plan = derived_plan()
        outputs: list[bytes] = []
        for index in range(10):
            keys = list(plan)
            random.Random(index).shuffle(keys)
            reordered = {key: plan[key] for key in keys}
            raw = json.dumps(reordered, ensure_ascii=False, separators=(",", ":"))
            raw += "\r\n" if index % 2 else "\n"
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONHASHSEED": str(index + 1),
                    "TZ": "UTC" if index % 2 else "Australia/Sydney",
                    "LC_ALL": "C",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--preview-candidate"],
                input=raw.encode("utf-8"),
                capture_output=True,
                cwd=Path(tempfile.gettempdir()),
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stderr, b"")
            outputs.append(completed.stdout)
        self.assertEqual(len(set(outputs)), 1)
        decoded = json.loads(outputs[0])
        self.assertEqual(decoded["rendered_prompt"], "@Image1 controls subject identity.")

    def test_renderer_has_no_template_or_network_execution_path(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.names[0].name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        } | {
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertTrue(imported.isdisjoint({"http", "requests", "socket", "urllib"}))
        forbidden_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}:
                forbidden_calls.append(node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"format", "format_map", "replace", "sub"}:
                forbidden_calls.append(node.func.attr)
        self.assertEqual(forbidden_calls, [])

    def test_profile_binding_policies_are_explicit_and_surface_scoped(self) -> None:
        forbidden_keys = {"default_handle", "handle_template", "token_template", "prompt_prefix"}
        for profile in [*self.registry.models.values(), *self.registry.surfaces.values()]:
            raw = (ROOT / profile.path).read_text(encoding="utf-8")
            self.assertTrue(forbidden_keys.isdisjoint(profile.data))
            if profile.data.get("profile_kind") != "surface":
                continue
            for operation in profile.data["operations"]:
                kind = operation["prompt_binding"]["kind"]
                if kind == "derived_media_ordinal":
                    self.assertEqual(
                        set(operation["prompt_binding"]["media_formatters"]),
                        set(operation["allowed_media_types"]),
                    )
                elif kind == "opaque_external_handle":
                    self.assertNotIn("media_formatters", operation["prompt_binding"])
                else:
                    self.assertEqual(operation["prompt_binding"], {"kind": "none"})

    def test_binding_schemas_reject_cross_profile_and_impossible_output_states(self) -> None:
        plan_schema = json.loads((ROOT / "schemas" / "binding-plan.schema.json").read_text(encoding="utf-8"))
        plan_validator = Draft202012Validator(plan_schema, format_checker=FormatChecker())

        byteplus_without_handle = opaque_plan("@custom")
        del byteplus_without_handle["bindings"][0]["prompt_visible_handle"]
        self.assertTrue(list(plan_validator.iter_errors(byteplus_without_handle)))

        fal_with_override = derived_plan()
        fal_with_override["bindings"][0]["prompt_visible_handle"] = "@Video99"
        self.assertTrue(list(plan_validator.iter_errors(fal_with_override)))

        volc_audio = derived_plan(profile_id="volcengine.ark")
        volc_audio["bindings"][0]["media_type"] = "audio"
        self.assertTrue(list(plan_validator.iter_errors(volc_audio)))

        structured_with_prompt_binding = structured_plan()
        structured_with_prompt_binding["segments"].append({"kind": "binding", "binding_id": "opening"})
        self.assertTrue(list(plan_validator.iter_errors(structured_with_prompt_binding)))

        for invalid_plan in (
            opaque_plan("@custom", profile_id="unknown.surface"),
            {**opaque_plan("@custom"), "operation": "first_last_frame"},
            {**derived_plan(), "operation": "first_last_frame"},
            {**structured_plan(), "profile_id": "fal.reference-to-video"},
        ):
            self.assertTrue(list(plan_validator.iter_errors(invalid_plan)))

        render_schema = json.loads((ROOT / "schemas" / "binding-render.schema.json").read_text(encoding="utf-8"))
        render_validator = Draft202012Validator(render_schema, format_checker=FormatChecker())
        valid_renders = {
            "byteplus": self.render(opaque_plan("@custom")),
            "fal": self.render(derived_plan()),
            "volc_reference": self.render(derived_plan(profile_id="volcengine.ark")),
            "volc_flf": self.render(structured_plan()),
        }
        for label, value in valid_renders.items():
            with self.subTest(valid=label):
                self.assertEqual(list(render_validator.iter_errors(value)), [])

        mutations = [
            ("byteplus preview", "byteplus", lambda value: value.update({"preview": False})),
            ("byteplus status", "byteplus", lambda value: value.update({"profile_status": "active"})),
            ("byteplus unknown profile", "byteplus", lambda value: value.update({"profile_id": "unknown.surface"})),
            ("byteplus fal profile", "byteplus", lambda value: value.update({"profile_id": "fal.reference-to-video"})),
            ("byteplus wrong operation", "byteplus", lambda value: value.update({"operation": "first_last_frame"})),
            ("byteplus typed transport", "byteplus", lambda value: value.update({"request_transport": "typed_media_arrays"})),
            ("byteplus position", "byteplus", lambda value: value["request_bindings"][0].update({"request_position": 1})),
            ("byteplus role", "byteplus", lambda value: value["request_bindings"][0].update({"structured_role": "first_frame"})),
            ("byteplus audio", "byteplus", lambda value: value["request_bindings"][0].update({"media_type": "audio"})),
            ("fal external transport", "fal", lambda value: value.update({"request_transport": "external_surface_unresolved"})),
            ("fal missing position", "fal", lambda value: value["request_bindings"][0].pop("request_position")),
            ("fal structured role", "fal", lambda value: value["request_bindings"][0].update({"structured_role": "first_frame"})),
            ("fal byteplus profile", "fal", lambda value: value.update({"profile_id": "byteplus.modelark"})),
            ("volc typed transport", "volc_reference", lambda value: value.update({"request_transport": "typed_media_arrays"})),
            ("volc audio", "volc_reference", lambda value: value["request_bindings"][0].update({"media_type": "audio"})),
            ("volc video", "volc_reference", lambda value: value["request_bindings"][0].update({"media_type": "video"})),
            ("flf wrong media", "volc_flf", lambda value: value["request_bindings"][0].update({"media_type": "audio"})),
            ("flf missing last", "volc_flf", lambda value: value["request_bindings"].pop()),
            ("flf duplicate first", "volc_flf", lambda value: value["request_bindings"][1].update({"structured_role": "first_frame"})),
            ("flf injected position", "volc_flf", lambda value: value["request_bindings"][0].update({"request_position": 1})),
            ("flf operation swap", "volc_flf", lambda value: value.update({"operation": "reference_generation"})),
            ("flf profile swap", "volc_flf", lambda value: value.update({"profile_id": "fal.reference-to-video"})),
            ("wrong model ID", "byteplus", lambda value: value.update({"model_profile_id": "seedance-2.5-model"})),
            ("wrong index hash", "byteplus", lambda value: value.update({"profile_index_sha256": "0" * 64})),
            ("wrong model hash", "byteplus", lambda value: value.update({"model_profile_sha256": "0" * 64})),
            ("wrong profile hash", "byteplus", lambda value: value.update({"profile_sha256": "0" * 64})),
            ("wrong evidence", "byteplus", lambda value: value["evidence_claim_ids"].__setitem__(0, "forged.claim")),
            ("reordered evidence", "byteplus", lambda value: value["evidence_claim_ids"].reverse()),
            ("future expiry", "byteplus", lambda value: value.update({"evidence_expires_at": "2026-07-19"})),
        ]
        for label, source, mutate in mutations:
            impossible = copy.deepcopy(valid_renders[source])
            mutate(impossible)
            with self.subTest(invalid=label):
                self.assertTrue(list(render_validator.iter_errors(impossible)))

        surface_schema = json.loads((ROOT / "schemas" / "surface-profile.schema.json").read_text(encoding="utf-8"))
        surface_validator = Draft202012Validator(surface_schema, format_checker=FormatChecker())
        fal_profile = copy.deepcopy(self.registry.surfaces["fal.reference-to-video"].data)
        fal_profile["operations"][0]["request_transport"] = "external_surface_unresolved"
        self.assertTrue(list(surface_validator.iter_errors(fal_profile)))

        fal_missing_formatter = copy.deepcopy(self.registry.surfaces["fal.reference-to-video"].data)
        del fal_missing_formatter["operations"][0]["prompt_binding"]["media_formatters"]["audio"]
        self.assertTrue(list(surface_validator.iter_errors(fal_missing_formatter)))

        fal_missing_media = copy.deepcopy(self.registry.surfaces["fal.reference-to-video"].data)
        fal_missing_media["operations"][0]["allowed_media_types"].remove("video")
        self.assertTrue(list(surface_validator.iter_errors(fal_missing_media)))

        structured_profile = copy.deepcopy(self.registry.surfaces["volcengine.ark"].data)
        structured_profile["operations"][1]["required_role_set"] = []
        self.assertTrue(list(surface_validator.iter_errors(structured_profile)))

        structured_role_mismatch = copy.deepcopy(self.registry.surfaces["volcengine.ark"].data)
        structured_role_mismatch["operations"][1]["structured_roles"] = ["first_frame"]
        self.assertTrue(list(surface_validator.iter_errors(structured_role_mismatch)))

    def test_profile_schemas_enforce_candidate_only_state(self) -> None:
        index_schema = json.loads((ROOT / "schemas" / "profile-index.schema.json").read_text(encoding="utf-8"))
        index_validator = Draft202012Validator(index_schema, format_checker=FormatChecker())
        index = copy.deepcopy(self.registry.index)
        self.assertEqual(list(index_validator.iter_errors(index)), [])
        for label, mutate in (
            ("activation true", lambda value: value.update({"activation_enabled": True})),
            ("activation numeric", lambda value: value.update({"activation_enabled": 0})),
            ("model active", lambda value: value["models"][0].update({"status": "active"})),
            ("model retired", lambda value: value["models"][0].update({"status": "retired"})),
            ("model enabled", lambda value: value["models"][0].update({"runtime_enabled": True})),
            ("surface active", lambda value: value["surfaces"][0].update({"status": "active"})),
            ("surface enabled", lambda value: value["surfaces"][0].update({"runtime_enabled": True})),
        ):
            changed = copy.deepcopy(index)
            mutate(changed)
            with self.subTest(index=label):
                self.assertTrue(list(index_validator.iter_errors(changed)))

        for schema_name, profile in (
            ("model-profile.schema.json", self.registry.models["seedance-2.0-model"].data),
            ("surface-profile.schema.json", self.registry.surfaces["byteplus.modelark"].data),
        ):
            schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            self.assertEqual(list(validator.iter_errors(profile)), [])
            for field, forbidden in (("status", "active"), ("status", "retired"), ("runtime_enabled", True), ("runtime_enabled", 0)):
                changed = copy.deepcopy(profile)
                changed[field] = forbidden
                with self.subTest(schema=schema_name, field=field, forbidden=forbidden):
                    self.assertTrue(list(validator.iter_errors(changed)))

    def test_runtime_guidance_rejects_retired_universal_tag_rules(self) -> None:
        paths = [
            "SKILL.md",
            "references/reference-workflow.md",
            "references/surface-prompt-profiles.md",
            "references/first-last-frame-guide.md",
            "references/prompt-compiler.md",
            "skills/seedance-prompt/SKILL.md",
            "skills/seedance-prompt-short/SKILL.md",
            "skills/seedance-interview/SKILL.md",
            *[f"references/vocab/{language}.md" for language in ("en", "es", "ja", "ko", "ru", "zh")],
            *[f"skills/seedance-vocab-{language}/SKILL.md" for language in ("en", "es", "ja", "ko", "ru", "zh")],
            *[f"skills/seedance-examples-{language}/SKILL.md" for language in ("ja", "ko", "zh")],
        ]
        retired = [
            "@Image1`–`@Image9",
            "@Video1`–`@Video3",
            "@Audio1`–`@Audio3",
            "platform's `@`-parser",
            "Keep reference tags unchanged",
            "Preserve reference tags exactly",
        ]
        for relative in paths:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for phrase in retired:
                with self.subTest(path=relative, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_literal_handle_examples_are_closed_and_explicitly_quarantined(self) -> None:
        manifest = json.loads((ROOT / "runtime" / "seedance-20.manifest.json").read_text(encoding="utf-8"))
        found = {
            path
            for path in manifest["files"]
            if path.endswith((".md", "SKILL.md"))
            and content_audit.NUMBERED_HANDLE.search((ROOT / path).read_text(encoding="utf-8"))
        }
        expected = {
            "examples/sequence-airport-arrival/clip-01-prompt.md",
            "examples/sequence-airport-arrival/clip-02-prompt.md",
            "examples/sequence-airport-arrival/sequence-plan.md",
            "references/reference-transfer-contract.md",
            "references/sequence-worked-trace.md",
            "references/surface-prompt-profiles.md",
        }
        self.assertEqual(found, expected)
        boundary_terms = {
            "examples/sequence-airport-arrival/clip-01-prompt.md": "exact opaque values supplied by this synthetic fixture",
            "examples/sequence-airport-arrival/clip-02-prompt.md": "exact opaque values supplied by this synthetic fixture",
            "examples/sequence-airport-arrival/sequence-plan.md": "exact opaque values supplied by the fixture",
            "references/reference-transfer-contract.md": "its spelling proves nothing about another surface",
            "references/sequence-worked-trace.md": "exact opaque handle supplied by this fixture",
            "references/surface-prompt-profiles.md": "not a token-construction rule",
        }
        for path, phrase in boundary_terms.items():
            self.assertIn(phrase, (ROOT / path).read_text(encoding="utf-8"))

        for literal in (
            "@Image1",
            "@image 2",
            "Image1",
            "VIDEO 9",
            "[Image1]",
            "[Audio1 role]",
            "图片1",
            "图像 2",
            "视频3",
            "音频 4",
        ):
            with self.subTest(detected=literal):
                self.assertIsNotNone(content_audit.NUMBERED_HANDLE.search(literal))
        for semantic in ("myImage1", "Image1field", "binding(image)", "@Image{n}", "图像参考"):
            with self.subTest(not_detected=semantic):
                self.assertIsNone(content_audit.NUMBERED_HANDLE.search(semantic))

    def test_evidence_pin_scope_and_hash_mutations_fail(self) -> None:
        claim = {
            "claim_id": "example.claim",
            "expires_at": "2026-07-18",
            "support_status": "supported",
            "lifecycle_status": "active",
            "runtime_status": "candidate",
            "review": {"status": "pending"},
            "affected_profiles": ["example.surface"],
            "scope": {"surfaces": ["example.surface"], "operations": ["reference_generation"]},
        }
        pin = {
            "claim_id": "example.claim",
            "claim_sha256": "a" * 64,
            "expires_at": "2026-07-18",
        }
        for mutation, expected in (
            ({"claim_sha256": "b" * 64}, "hash mismatch"),
            ({"expires_at": "2026-07-19"}, "expiry projection mismatch"),
        ):
            changed = {**pin, **mutation}
            errors: list[str] = []
            profile_check._check_pin(
                changed,
                profile_id="example.surface",
                operation="reference_generation",
                model_level=False,
                claims={"example.claim": (claim, "a" * 64)},
                today=FRESH_DATE,
                errors=errors,
            )
            self.assertTrue(any(expected in error for error in errors), errors)

        errors = []
        profile_check._check_pin(
            pin,
            profile_id="other.surface",
            operation="reference_generation",
            model_level=False,
            claims={"example.claim": (claim, "a" * 64)},
            today=FRESH_DATE,
            errors=errors,
        )
        self.assertTrue(any("affected profile" in error or "surface does not match" in error for error in errors))

        for malformed in (
            {**claim, "affected_profiles": None},
            {**claim, "scope": {"surfaces": None, "operations": None}},
        ):
            errors = []
            profile_check._check_pin(
                pin,
                profile_id="example.surface",
                operation="reference_generation",
                model_level=False,
                claims={"example.claim": (malformed, "a" * 64)},
                today=FRESH_DATE,
                errors=errors,
            )
            self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
