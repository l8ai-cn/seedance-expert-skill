from __future__ import annotations

import importlib.util
import http.server
import json
import tempfile
import threading
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("schema_check", ROOT / "scripts" / "schema_check.py")
assert SPEC and SPEC.loader
schema_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schema_check)


class SchemaCheckTests(unittest.TestCase):
    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_repository_fixtures_pass_strict_validation(self) -> None:
        errors, warnings, count = schema_check.validate_repository(
            ROOT, ROOT / "validation" / "schema-instances.json", strict=True
        )
        self.assertEqual(errors, [])
        self.assertGreaterEqual(count, 10)
        self.assertEqual(warnings, [])

    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_negative_fixture_reports_json_pointer(self) -> None:
        schema = json.loads((ROOT / "schemas" / "clip-contract.schema.json").read_text(encoding="utf-8"))
        instance = json.loads(
            (ROOT / "examples" / "sequence-airport-arrival" / "clip-01-contract.json").read_text(encoding="utf-8")
        )
        instance["sequence_index"] = 0
        validator = schema_check.Draft202012Validator(schema, format_checker=schema_check.FormatChecker())
        messages = [f"{schema_check.pointer(error.absolute_path)}: {error.message}" for error in validator.iter_errors(instance)]
        self.assertTrue(any(message.startswith("/sequence_index:") for message in messages), messages)

    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_every_schema_rejects_unknown_root_property(self) -> None:
        manifest = json.loads((ROOT / "validation" / "schema-instances.json").read_text(encoding="utf-8"))
        for mapping in manifest["mappings"]:
            schema_path = ROOT / mapping["schema"]
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if mapping.get("instances"):
                instance = json.loads((ROOT / mapping["instances"][0]).read_text(encoding="utf-8"))
            else:
                line = (ROOT / mapping["jsonl_instances"][0]).read_text(encoding="utf-8").splitlines()[0]
                instance = json.loads(line)
            instance["unexpected_v702_field"] = True
            errors = list(schema_check.Draft202012Validator(schema).iter_errors(instance))
            with self.subTest(schema=mapping["schema"]):
                self.assertTrue(any(error.validator == "additionalProperties" for error in errors), errors)

    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_nested_contract_and_date_time_are_enforced(self) -> None:
        schema = json.loads((ROOT / "schemas" / "project-state.schema.json").read_text(encoding="utf-8"))
        instance = json.loads((ROOT / "examples" / "standalone-clip" / "project-state.json").read_text(encoding="utf-8"))
        instance["story"]["typo"] = "must fail"
        instance["updated_at"] = "not-a-date"
        errors = list(schema_check.Draft202012Validator(schema, format_checker=schema_check.FormatChecker()).iter_errors(instance))
        validators = {error.validator for error in errors}
        self.assertIn("additionalProperties", validators)
        self.assertIn("format", validators)

    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_strict_mode_rejects_unmapped_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            (root / "validation").mkdir()
            (root / "schemas" / "unmapped.schema.json").write_text(
                json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
                encoding="utf-8",
            )
            manifest = root / "validation" / "schema-instances.json"
            manifest.write_text(json.dumps({"schema_version": 1, "mappings": [{
                "schema": "schemas/unmapped.schema.json", "instances": [], "strict_exemption": "test"
            }]}), encoding="utf-8")
            # A second schema proves strict coverage is enforced.
            (root / "schemas" / "missing.schema.json").write_text(
                json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
                encoding="utf-8",
            )
            errors, _, _ = schema_check.validate_repository(root, manifest, strict=True)
            self.assertTrue(any("missing from validation manifest" in error for error in errors), errors)

    def test_manifest_rejects_escape_paths(self) -> None:
        path, error = schema_check.safe_path(ROOT, "../outside.json", "fixture")
        self.assertIsNone(path)
        self.assertIn("escapes repository", error or "")

    def test_manifest_itself_must_be_contained_and_not_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            for target, expected in (
                (Path(temporary) / "external.json", "escapes repository"),
                (root / "internal.json", "must not contain symlinks"),
            ):
                with self.subTest(target=target):
                    target.write_text('{"schema_version": 1, "mappings": []}', encoding="utf-8")
                    link = root / f"manifest-{target.stem}.json"
                    try:
                        link.symlink_to(target)
                    except OSError:
                        self.skipTest("symlinks are unavailable")
                    path, error = schema_check.safe_manifest_path(root.resolve(), link)
                    self.assertIsNone(path)
                    self.assertIn(expected, error or "")

    def test_strict_parser_rejects_duplicate_and_nonfinite_values(self) -> None:
        for text in ('{"value": 1, "value": 2}', '{"value": NaN}', '{"value": Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                schema_check.parse_json(text)

    @unittest.skipIf(schema_check.Draft202012Validator is None, "jsonschema dependency is not installed")
    def test_remote_schema_reference_is_rejected_without_network_access(self) -> None:
        requested = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib handler contract
                requested.set()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"type":"object"}')

            def log_message(self, _format, *_args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = 0.2
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "schemas").mkdir()
                (root / "validation").mkdir()
                (root / "fixtures").mkdir()
                (root / "schemas" / "remote.schema.json").write_text(json.dumps({
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": f"http://127.0.0.1:{server.server_port}/leak",
                }), encoding="utf-8")
                (root / "fixtures" / "instance.json").write_text("{}", encoding="utf-8")
                manifest = root / "validation" / "schema-instances.json"
                manifest.write_text(json.dumps({
                    "schema_version": 1,
                    "mappings": [{
                        "schema": "schemas/remote.schema.json",
                        "instances": ["fixtures/instance.json"],
                    }],
                }), encoding="utf-8")
                errors, _, _ = schema_check.validate_repository(root, manifest, strict=True)
                self.assertTrue(any("non-local $ref is forbidden" in error for error in errors), errors)
            thread.join(timeout=1)
            self.assertFalse(requested.is_set())
        finally:
            server.server_close()
            thread.join(timeout=1)

    def test_cli_fails_closed_when_dependency_is_missing(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", str(ROOT / "scripts" / "schema_check.py"), "--strict"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing dependency", result.stdout)

    def test_validation_tooling_is_not_runtime_payload(self) -> None:
        runtime = json.loads((ROOT / "runtime" / "seedance-20.manifest.json").read_text(encoding="utf-8"))
        payload = set(runtime["files"])
        self.assertNotIn("scripts/schema_check.py", payload)
        self.assertNotIn("requirements-validation.lock", payload)
        self.assertFalse(any(path.startswith("validation/") for path in payload))


if __name__ == "__main__":
    unittest.main()
