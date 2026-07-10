from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import install_codex_skill as installer
from tools import runtime_package as package


ROOT = Path(__file__).resolve().parents[1]


def write_file(root: Path, relative: str, content: str | bytes) -> None:
    path = root.joinpath(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def make_fixture(root: Path, *, selected_asset: bool = False) -> Path:
    files = [
        "LICENSE",
        "SKILL.md",
        "agents/openai.yaml",
        "references/guide.md",
        "skills/child/SKILL.md",
    ]
    write_file(root, "LICENSE", "fixture license\n")
    write_file(
        root,
        "SKILL.md",
        "---\nname: seedance-20\ndescription: fixture\n---\n"
        "Load `[skill:child]`, `[ref:guide]`, and [the guide](references/guide.md).\n",
    )
    write_file(root, "agents/openai.yaml", "interface:\n  display_name: Fixture\n")
    write_file(
        root,
        "skills/child/SKILL.md",
        "---\nname: child\ndescription: fixture child\n---\nLoad `[ref:guide]`.\n",
    )
    write_file(root, "references/guide.md", "# Fixture guide\n")
    fixture_requirements = (
        package.REQUIRED_OPERATIONAL_PATHS
        | package.REQUIRED_SKILL_PATHS
        | package.REQUIRED_COMPATIBILITY_PATHS
    )
    for relative in sorted(fixture_requirements):
        if relative in files:
            continue
        files.append(relative)
        if relative.endswith(".json"):
            write_file(root, relative, "{}\n")
        elif relative.endswith(".py"):
            write_file(root, relative, "#!/usr/bin/env python3\npass\n")
        else:
            write_file(root, relative, "# Operational fixture\n")
    if selected_asset:
        files.append("assets/selected.PNG")
        write_file(root, "assets/selected.PNG", b"\x89PNG\r\nfixture\x00bytes")
    files.sort()
    manifest = {
        "schema_version": 1,
        "package_name": "seedance-20",
        "generated_manifest": package.GENERATED_MANIFEST_NAME,
        "locked_payload_size_bytes": 0,
        "locked_tree_sha256": "0" * 64,
        "files": files,
    }
    manifest_path = root / "runtime" / "seedance-20.manifest.json"
    write_file(root, "runtime/seedance-20.manifest.json", json.dumps(manifest, indent=2) + "\n")
    plan = package.package_plan(root, manifest_path, enforce_lock=False)
    manifest["locked_payload_size_bytes"] = plan["payload_size_bytes"]
    manifest["locked_tree_sha256"] = plan["tree_sha256"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def required_runtime_files() -> list[str]:
    return sorted(
        package.REQUIRED_PAYLOAD_PATHS
        | package.REQUIRED_OPERATIONAL_PATHS
        | package.REQUIRED_SKILL_PATHS
        | package.REQUIRED_COMPATIBILITY_PATHS
    )


def refresh_fixture_lock(root: Path) -> dict:
    manifest_path = root / "runtime" / "seedance-20.manifest.json"
    manifest = read_manifest(manifest_path)
    plan = package.package_plan(root, manifest_path, enforce_lock=False)
    manifest["locked_payload_size_bytes"] = plan["payload_size_bytes"]
    manifest["locked_tree_sha256"] = plan["tree_sha256"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return package.package_plan(root)


def resign_built_package(root: Path) -> dict:
    manifest_path = root / package.GENERATED_MANIFEST_NAME
    manifest = read_manifest(manifest_path)
    records = []
    for record in manifest["files"]:
        relative = str(record["path"])
        content = root.joinpath(*relative.split("/")).read_bytes()
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    manifest["files"] = records
    manifest["payload_file_count"] = len(records)
    manifest["payload_size_bytes"] = sum(record["size"] for record in records)
    manifest["tree_sha256"] = package._tree_sha256(records)
    manifest_path.write_bytes(package.render_generated_manifest(manifest))
    return manifest


class RuntimePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_repository_manifest_builds_conservative_runtime_exactly(self) -> None:
        plan = package.package_plan(ROOT)
        self.assertEqual(plan["payload_file_count"], 103)
        self.assertEqual(plan["payload_size_bytes"], 540738)
        self.assertEqual(plan["tree_sha256"], "fef52e3e1b62748334c95350af8c71e6266973d4a0faa27a6d9dcc538708027d")

        first = self.base / "first"
        second = self.base / "second"
        package.build_package(ROOT, first)
        os.utime(ROOT / "SKILL.md", None)
        package.build_package(ROOT, second)
        first_manifest = (first / package.GENERATED_MANIFEST_NAME).read_bytes()
        second_manifest = (second / package.GENERATED_MANIFEST_NAME).read_bytes()
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(package.verify_package(first)["tree_sha256"], plan["tree_sha256"])

        found = package._scan_plain_tree(first)
        self.assertEqual(len(found), 104)
        self.assertIn("references/interview-starters.md", found)
        self.assertNotIn("README.md", found)
        self.assertFalse(any(path.startswith(("docs/", "evals/", "tests/", "data/")) for path in found))
        self.assertFalse(any(path.startswith("references/migrated/") for path in found))
        self.assertFalse(any(path.startswith("assets/") for path in found))

        frame_tool = subprocess.run(
            [sys.executable, "-B", str(first / "scripts" / "extract_last_frame.py"), "--self-test"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(frame_tool.returncode, 0, frame_tool.stdout + frame_tool.stderr)
        state_tool = subprocess.run(
            [
                sys.executable,
                "-B",
                str(first / "scripts" / "project_state_check.py"),
                str(first),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(state_tool.returncode, 0, state_tool.stdout + state_tool.stderr)

    def test_selected_binary_asset_is_exactly_preserved(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo, selected_asset=True)
        output = self.base / "output"
        package.build_package(repo, output)
        self.assertEqual((output / "assets" / "selected.PNG").read_bytes(), b"\x89PNG\r\nfixture\x00bytes")
        self.assertNotIn("assets/unlisted.png", package._scan_plain_tree(output))

    def test_manifest_rejects_unsafe_and_development_paths(self) -> None:
        base = {
            "schema_version": 1,
            "package_name": "seedance-20",
            "generated_manifest": package.GENERATED_MANIFEST_NAME,
            "locked_payload_size_bytes": 0,
            "locked_tree_sha256": "0" * 64,
            "files": required_runtime_files(),
        }
        cases = [
            ("../outside", "stay inside|safe POSIX"),
            ("/absolute", "stay inside"),
            ("tests/secret.txt", "development-only"),
            ("Tests/secret.txt", "development-only"),
            ("scripts/eval_run.py", "development script"),
            ("references/migrated/old.md", "migrated archive"),
            ("NUL.txt", "portable"),
            ("CONIN$", "portable"),
            ("bad\\path", "safe POSIX"),
            ("bad\npath", "safe POSIX"),
        ]
        for bad_path, error in cases:
            with self.subTest(path=bad_path):
                data = dict(base)
                data["files"] = sorted([*required_runtime_files(), bad_path])
                with self.assertRaisesRegex(package.PackageError, error):
                    package._validate_source_manifest_data(data)

        duplicate = dict(base)
        duplicate["files"] = sorted([*required_runtime_files(), "LICENSE"])
        with self.assertRaisesRegex(package.PackageError, "unique"):
            package._validate_source_manifest_data(duplicate)

        unsorted = dict(base)
        unsorted["files"] = list(reversed(required_runtime_files()))
        with self.assertRaisesRegex(package.PackageError, "sorted"):
            package._validate_source_manifest_data(unsorted)

        for invalid_version in (True, 1.0):
            typed = dict(base)
            typed["schema_version"] = invalid_version
            with self.subTest(schema_version=invalid_version):
                with self.assertRaisesRegex(package.PackageError, "unsupported"):
                    package._validate_source_manifest_data(typed)

    def test_casefold_and_prefix_collisions_fail(self) -> None:
        base = {
            "schema_version": 1,
            "package_name": "seedance-20",
            "generated_manifest": package.GENERATED_MANIFEST_NAME,
            "locked_payload_size_bytes": 0,
            "locked_tree_sha256": "0" * 64,
        }
        for collision in [
            ["A.txt", "a.TXT"],
            ["path", "PATH/child.txt"],
            ["a", "a-foo", "a/bar"],
            [package.GENERATED_MANIFEST_NAME.upper()],
        ]:
            data = dict(base)
            data["files"] = sorted([*required_runtime_files(), *collision])
            with self.assertRaisesRegex(package.PackageError, "collid|prefix|cannot list itself"):
                package._validate_source_manifest_data(data)

    def test_link_closure_catches_missing_ref_skill_and_markdown_target(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        mutations = [
            "Load `[ref:missing]`.\n",
            "Load `[skill:missing]`.\n",
            "Read [missing](references/missing.md).\n",
            "Run `python scripts/missing_runtime_tool.py --strict`.\n",
        ]
        original = (repo / "SKILL.md").read_text(encoding="utf-8")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                (repo / "SKILL.md").write_text(original + mutation, encoding="utf-8")
                with self.assertRaisesRegex(package.PackageError, "link closure"):
                    package.package_plan(repo, enforce_lock=False)
        (repo / "SKILL.md").write_text(original, encoding="utf-8")

    def test_lock_detects_runtime_source_drift(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        with (repo / "references" / "guide.md").open("a", encoding="utf-8") as handle:
            handle.write("changed\n")
        with self.assertRaisesRegex(package.PackageError, "locked_tree_sha256"):
            package.package_plan(repo)

    def test_source_symlink_is_rejected(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        guide = repo / "references" / "guide.md"
        external = self.base / "external.md"
        external.write_text("external\n", encoding="utf-8")
        guide.unlink()
        try:
            guide.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(package.PackageError, "symlink"):
            package.package_plan(repo, enforce_lock=False)

    @unittest.skipIf(os.name == "nt", "setuid mode bits are POSIX-specific")
    def test_setuid_source_is_rejected(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        script = repo / "scripts" / "extract_last_frame.py"
        script.chmod(0o4755)
        with self.assertRaisesRegex(package.PackageError, "setuid"):
            package.package_plan(repo, enforce_lock=False)

    def test_source_manifest_parent_and_package_root_symlinks_are_rejected(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        runtime = repo / "runtime"
        external_runtime = self.base / "external-runtime"
        shutil.copytree(runtime, external_runtime)
        shutil.rmtree(runtime)
        try:
            runtime.symlink_to(external_runtime, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(package.PackageError, "symlink"):
            package.package_plan(repo)

        clean_repo = self.base / "clean-repo"
        make_fixture(clean_repo)
        outside_manifest_alias = self.base / "outside-manifest.json"
        outside_manifest_alias.symlink_to(clean_repo / "runtime" / "seedance-20.manifest.json")
        with self.assertRaisesRegex(package.PackageError, "stay inside"):
            package.package_plan(clean_repo, outside_manifest_alias)
        cli_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "tools" / "runtime_package.py"),
                "--repo-root",
                str(clean_repo),
                "--manifest",
                str(outside_manifest_alias),
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(cli_result.returncode, 1, cli_result.stdout + cli_result.stderr)
        self.assertIn("stay inside", cli_result.stdout)
        output = self.base / "real-output"
        package.build_package(clean_repo, output)
        linked_output = self.base / "linked-output"
        linked_output.symlink_to(output, target_is_directory=True)
        with self.assertRaisesRegex(package.PackageError, "root.*special"):
            package.verify_package(linked_output)

    def test_outer_repository_alias_is_canonicalized(self) -> None:
        physical_parent = self.base / "physical"
        alias_parent = self.base / "alias"
        physical_parent.mkdir()
        try:
            alias_parent.symlink_to(physical_parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks unavailable")
        aliased_repo = alias_parent / "repo"
        make_fixture(aliased_repo)
        plan = package.package_plan(aliased_repo)
        manifest = read_manifest(aliased_repo / "runtime" / "seedance-20.manifest.json")
        self.assertEqual(plan["tree_sha256"], manifest["locked_tree_sha256"])
        output = self.base / "aliased-build"
        package.build_package(
            aliased_repo,
            output,
            aliased_repo / "runtime" / "seedance-20.manifest.json",
        )
        self.assertEqual(package.verify_package(output)["tree_sha256"], plan["tree_sha256"])
        cli_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "tools" / "runtime_package.py"),
                "--repo-root",
                str(aliased_repo),
                "--manifest",
                str(aliased_repo / "runtime" / "seedance-20.manifest.json"),
                "--dry-run",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(cli_result.returncode, 0, cli_result.stdout + cli_result.stderr)

        external_runtime = self.base / "aliased-external-runtime"
        shutil.copytree(aliased_repo / "runtime", external_runtime)
        shutil.rmtree(aliased_repo / "runtime")
        (aliased_repo / "runtime").symlink_to(external_runtime, target_is_directory=True)
        with self.assertRaisesRegex(package.PackageError, "symlink"):
            package.package_plan(aliased_repo)

    def test_special_backup_and_journal_slots_fail_closed(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        external = self.base / "external"
        external.mkdir()
        backup = skills / installer.BACKUP_NAME
        try:
            backup.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(installer.InstallError, "rollback slot"):
            installer.install(repo, skills, force=True)
        self.assertTrue(backup.is_symlink())
        backup.unlink()

        journal = skills / installer.JOURNAL_NAME
        journal.symlink_to(self.base / "missing-journal")
        with self.assertRaisesRegex(installer.InstallError, "journal is special"):
            installer.recover_transaction(skills, skills / "seedance-20", True)
        self.assertTrue(journal.is_symlink())

    def test_built_package_detects_tamper_missing_extra_and_symlink(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)

        tampered = self.base / "tampered"
        package.build_package(repo, tampered)
        (tampered / "references" / "guide.md").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "integrity mismatch"):
            package.verify_package(tampered)

        missing = self.base / "missing"
        package.build_package(repo, missing)
        (missing / "references" / "guide.md").unlink()
        with self.assertRaisesRegex(package.PackageError, "file set mismatch"):
            package.verify_package(missing)

        extra = self.base / "extra"
        package.build_package(repo, extra)
        (extra / ".env").write_text("SECRET=never-package\n", encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "file set mismatch"):
            package.verify_package(extra)

        linked = self.base / "linked"
        package.build_package(repo, linked)
        target = linked / "references" / "guide.md"
        target.unlink()
        try:
            target.symlink_to(self.base / "external.md")
        except (OSError, NotImplementedError):
            return
        with self.assertRaisesRegex(package.PackageError, "special"):
            package.verify_package(linked)

    def test_resigned_forbidden_payload_and_extra_empty_directories_fail(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)

        forbidden = self.base / "forbidden"
        package.build_package(repo, forbidden)
        write_file(forbidden, "tests/secret.txt", "secret\n")
        manifest_path = forbidden / package.GENERATED_MANIFEST_NAME
        manifest = read_manifest(manifest_path)
        manifest["files"].append({"path": "tests/secret.txt", "sha256": "0" * 64, "size": 0})
        manifest["files"].sort(key=lambda record: record["path"])
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        resign_built_package(forbidden)
        with self.assertRaisesRegex(package.PackageError, "development-only"):
            package.verify_package(forbidden)

        extra_directory = self.base / "extra-directory"
        package.build_package(repo, extra_directory)
        (extra_directory / ".git").mkdir()
        with self.assertRaisesRegex(package.PackageError, "directory set mismatch"):
            package.verify_package(extra_directory)

    def test_generated_manifest_must_be_canonical_and_strictly_typed(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)

        minified = self.base / "minified"
        package.build_package(repo, minified)
        manifest_path = minified / package.GENERATED_MANIFEST_NAME
        manifest = read_manifest(manifest_path)
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "canonical"):
            package.verify_package(minified)

        for field, value, error in [
            ("schema_version", 1.0, "identity/version"),
            ("payload_file_count", True, "file count"),
            ("payload_size_bytes", float(manifest["payload_size_bytes"]), "payload size"),
        ]:
            output = self.base / f"typed-{field}"
            package.build_package(repo, output)
            typed = read_manifest(output / package.GENERATED_MANIFEST_NAME)
            typed[field] = value
            (output / package.GENERATED_MANIFEST_NAME).write_text(
                json.dumps(typed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.subTest(field=field):
                with self.assertRaisesRegex(package.PackageError, error):
                    package.verify_package(output)

    def test_self_signed_allowed_change_is_internal_only_and_trusted_checks_fail(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        active = skills / "seedance-20"
        with (active / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("self-signed local change\n")
        resigned = resign_built_package(active)
        self.assertEqual(
            (active / package.GENERATED_MANIFEST_NAME).read_bytes(),
            package.render_generated_manifest(resigned),
        )
        package.verify_package(active)

        with mock.patch.object(installer, "REPO_ROOT", repo):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(installer.check_install(skills), 1)
        command = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "tools" / "runtime_package.py"),
                "--repo-root",
                str(repo),
                "--verify",
                str(active),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(command.returncode, 1, command.stdout + command.stderr)
        self.assertIn("reviewed source lock", command.stdout)

    def test_crlf_sources_are_canonical_and_invalid_utf8_fails(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        expected = package.package_plan(repo)
        for relative in read_manifest(repo / "runtime" / "seedance-20.manifest.json")["files"]:
            path = repo.joinpath(*relative.split("/"))
            if path.suffix.lower() in package.TEXT_PAYLOAD_SUFFIXES or path.name == "LICENSE":
                canonical = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                path.write_bytes(canonical.replace(b"\n", b"\r\n"))
                self.assertNotIn(b"\r\r\n", path.read_bytes())
        self.assertEqual(package.package_plan(repo), expected)
        output = self.base / "crlf-output"
        package.build_package(repo, output)
        self.assertNotIn(b"\r", (output / "SKILL.md").read_bytes())

        invalid = repo / "schemas" / "clip-contract.schema.json"
        invalid.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(package.PackageError, "valid UTF-8"):
            package.package_plan(repo, enforce_lock=False)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits are not portable to Windows")
    def test_package_permissions_are_umask_independent(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        output = self.base / "permissions"
        previous_umask = os.umask(0o077)
        try:
            package.build_package(repo, output)
        finally:
            os.umask(previous_umask)
        for current, directories, files in os.walk(output):
            self.assertEqual(stat.S_IMODE(os.stat(current).st_mode), 0o755)
            for name in files:
                self.assertEqual(stat.S_IMODE(os.stat(Path(current) / name).st_mode), 0o644)

    def test_durability_barrier_precedes_package_activation(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        output = self.base / "durable"
        events: list[str] = []
        real_sync = package._fsync_package_tree
        real_replace = package.os.replace

        def record_sync(path: Path) -> None:
            events.append("tree-fsynced")
            real_sync(path)

        def record_replace(source: Path, destination: Path) -> None:
            events.append("activated")
            real_replace(source, destination)

        with mock.patch.object(package, "_fsync_package_tree", side_effect=record_sync):
            with mock.patch.object(package.os, "replace", side_effect=record_replace):
                package.build_package(repo, output)
        self.assertLess(events.index("tree-fsynced"), events.index("activated"))

    def test_file_fsync_failure_aborts_before_output_activation(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        output = self.base / "fsync-failure"
        with mock.patch.object(package.os, "fsync", side_effect=OSError("injected fsync failure")):
            with self.assertRaisesRegex(OSError, "fsync failure"):
                package.build_package(repo, output)
        self.assertFalse(output.exists())

    def test_post_activation_verification_failure_quarantines_output(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        output = self.base / "post-activation-failure"
        real_verify = package.verify_package
        calls = 0

        def fail_second_verify(path: Path) -> dict:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise package.PackageError("injected post-activation verification failure")
            return real_verify(path)

        with mock.patch.object(package, "verify_package", side_effect=fail_second_verify):
            with self.assertRaisesRegex(package.PackageError, "post-activation"):
                package.build_package(repo, output)
        self.assertFalse(output.exists())
        quarantines = list(self.base.glob(f".{package.PACKAGE_NAME}.failed-build-*"))
        self.assertEqual(len(quarantines), 1)
        real_verify(quarantines[0])

    @unittest.skipIf(os.name == "nt", "Windows directory fsync is best-effort")
    def test_directory_fsync_errors_are_not_silenced_on_posix(self) -> None:
        with mock.patch.object(installer.os, "fsync", side_effect=OSError("injected directory EIO")):
            with self.assertRaisesRegex(OSError, "directory EIO"):
                installer._fsync_directory(self.base)

    def test_alternate_link_syntax_and_yaml_resources_are_closed(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skill = repo / "SKILL.md"
        original_skill = skill.read_text(encoding="utf-8")
        mutations = [
            "Read [missing][guide].\n[guide]: references/missing.md\n",
            "Read <references/missing.md>.\n",
            '<img src="assets/missing.png">\n',
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                skill.write_text(original_skill + mutation, encoding="utf-8")
                with self.assertRaisesRegex(package.PackageError, "link closure"):
                    package.package_plan(repo, enforce_lock=False)
        skill.write_text(original_skill, encoding="utf-8")
        agent = repo / "agents" / "openai.yaml"
        agent.write_text(agent.read_text(encoding="utf-8") + "icon: assets/missing.png\n", encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "link closure"):
            package.package_plan(repo, enforce_lock=False)

    def test_required_operational_path_cannot_be_dropped(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        manifest_path = repo / "runtime" / "seedance-20.manifest.json"
        manifest = read_manifest(manifest_path)
        manifest["files"].remove("examples/standalone-clip/project-state.json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "misses required"):
            package.package_plan(repo, enforce_lock=False)

    def test_dry_run_performs_no_writes(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "does-not-exist" / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            result = installer.install(repo, skills, dry_run=True)
        self.assertEqual(result, 0)
        self.assertFalse((self.base / "does-not-exist").exists())
        with self.assertRaisesRegex(installer.InstallError, "cannot recover"):
            installer.install(repo, skills, dry_run=True, recover=True)

    def test_documented_dry_run_does_not_write_bytecode_to_checkout(self) -> None:
        checkout = self.base / "checkout"
        make_fixture(checkout)
        (checkout / "scripts").mkdir(exist_ok=True)
        (checkout / "tools").mkdir(exist_ok=True)
        shutil.copy2(ROOT / "scripts" / "install_codex_skill.py", checkout / "scripts" / "install_codex_skill.py")
        shutil.copy2(ROOT / "tools" / "runtime_package.py", checkout / "tools" / "runtime_package.py")
        shutil.copy2(ROOT / "tools" / "__init__.py", checkout / "tools" / "__init__.py")
        environment = os.environ.copy()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        result = subprocess.run(
            [
                sys.executable,
                str(checkout / "scripts" / "install_codex_skill.py"),
                "--dest",
                str(self.base / "dry-run-skills"),
                "--dry-run",
            ],
            cwd=checkout,
            env=environment,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((checkout / "tools" / "__pycache__").exists())
        self.assertFalse((checkout / "scripts" / "__pycache__").exists())

    def test_cli_rejects_ambiguous_recovery_combinations(self) -> None:
        script = ROOT / "scripts" / "install_codex_skill.py"
        for arguments in (["--check", "--recover"], ["--dry-run", "--recover"]):
            result = subprocess.run(
                [sys.executable, "-B", str(script), *arguments],
                text=True,
                capture_output=True,
            )
            with self.subTest(arguments=arguments):
                self.assertEqual(result.returncode, 2)
                self.assertIn("cannot be combined", result.stderr)

    def test_dry_run_reports_no_changes_for_verified_install(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        plan = package.package_plan(repo)
        self.assertEqual(installer._dry_run_changes(skills / "seedance-20", plan), (0, 0, 0))

    def test_source_and_destination_overlap_fails_before_writes(self) -> None:
        checkout = self.base / "seedance-20"
        make_fixture(checkout)
        with self.assertRaisesRegex(installer.InstallError, "disjoint"):
            installer.install(checkout, self.base, force=True)
        self.assertTrue((checkout / "SKILL.md").is_file())

        nested_skills = checkout / "local" / "skills"
        with self.assertRaisesRegex(installer.InstallError, "disjoint"):
            installer.install(checkout, nested_skills, force=True)
        self.assertFalse(nested_skills.exists())

    def test_destination_symlink_is_untouched(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        external = self.base / "external"
        skills.mkdir()
        external.mkdir()
        destination = skills / "seedance-20"
        try:
            destination.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(installer.InstallError, "symlink"):
            installer.install(repo, skills, force=True)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(list(external.iterdir()), [])

    def test_destination_mount_or_junction_signal_is_untouched(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        destination = skills / "seedance-20"
        destination.mkdir(parents=True)
        write_file(destination, "sentinel.txt", "keep\n")
        with mock.patch.object(installer, "is_special_path", return_value=True):
            with self.assertRaisesRegex(installer.InstallError, "mount"):
                installer.install(repo, skills, force=True)
        self.assertEqual((destination / "sentinel.txt").read_text(encoding="utf-8"), "keep\n")

    def test_fresh_force_dirty_backup_and_rollback(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.install(repo, skills), 0)
        active = skills / "seedance-20"
        original_manifest = (active / package.GENERATED_MANIFEST_NAME).read_bytes()

        with (active / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("dirty marker\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.install(repo, skills, force=True), 0)
        self.assertNotIn("dirty marker", (active / "SKILL.md").read_text(encoding="utf-8"))
        backup = skills / installer.BACKUP_NAME
        self.assertIn("dirty marker", (backup / "SKILL.md").read_text(encoding="utf-8"))

        with mock.patch.object(installer, "REPO_ROOT", repo):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(installer.rollback(skills), 0)
        self.assertIn("dirty marker", (active / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual((backup / package.GENERATED_MANIFEST_NAME).read_bytes(), original_manifest)

    def test_legacy_upgrade_is_preserved_and_recoverable(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        legacy = skills / "seedance-20"
        legacy.mkdir(parents=True)
        write_file(legacy, "SKILL.md", "---\nname: seedance-20\n---\nlegacy\n")
        write_file(legacy, "README.md", "legacy-only\n")

        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills, force=True)
            installer.install(repo, skills, force=True)
        legacy_backup = skills / installer.LEGACY_BACKUP_NAME
        self.assertTrue((legacy_backup / "README.md").is_file())

        with mock.patch.object(installer, "REPO_ROOT", repo):
            with contextlib.redirect_stdout(io.StringIO()):
                installer.rollback(skills, legacy=True)
        self.assertTrue((skills / "seedance-20" / "README.md").is_file())

    def test_failure_after_old_move_recovers_verified_install(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        before = (skills / "seedance-20" / package.GENERATED_MANIFEST_NAME).read_bytes()
        real_replace = installer.atomic_replace
        calls = 0

        def fail_second_directory_replace(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected rename failure")
            real_replace(source, destination)

        output = io.StringIO()
        with mock.patch.object(installer, "atomic_replace", side_effect=fail_second_directory_replace):
            with contextlib.redirect_stdout(output):
                self.assertEqual(installer.install(repo, skills, force=True), 0)
        self.assertIn("Recovered a verified installation", output.getvalue())
        active = skills / "seedance-20"
        self.assertEqual((active / package.GENERATED_MANIFEST_NAME).read_bytes(), before)
        package.verify_package(active)
        self.assertFalse((skills / installer.JOURNAL_NAME).exists())

    def test_stage_build_failure_leaves_active_install_untouched(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        active = skills / "seedance-20"
        before = (active / package.GENERATED_MANIFEST_NAME).read_bytes()
        with mock.patch.object(installer, "materialize_package", side_effect=OSError("injected ENOSPC")):
            with self.assertRaisesRegex(OSError, "ENOSPC"):
                with contextlib.redirect_stdout(io.StringIO()):
                    installer.install(repo, skills, force=True)
        self.assertEqual((active / package.GENERATED_MANIFEST_NAME).read_bytes(), before)
        self.assertFalse(any(path.name.startswith(installer.STAGE_PREFIX) for path in skills.iterdir()))

    def test_runtime_source_change_during_copy_aborts_build(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        output = self.base / "output"
        real_read = package.read_plain_source_file
        skill_reads = 0

        def mutate_second_skill_read(root: Path, relative: str) -> bytes:
            nonlocal skill_reads
            data = real_read(root, relative)
            if relative == "SKILL.md":
                skill_reads += 1
                if skill_reads == 2:
                    return data + b"changed during copy\n"
            return data

        with mock.patch.object(package, "read_plain_source_file", side_effect=mutate_second_skill_read):
            with self.assertRaisesRegex(package.PackageError, "changed during packaging"):
                package.build_package(repo, output)
        self.assertFalse(output.exists())

    def test_rollback_rename_failure_preserves_both_versions(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        with (repo / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("rollback failure version two\n")
        refresh_fixture_lock(repo)
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills, force=True)
        active = skills / "seedance-20"
        backup = skills / installer.BACKUP_NAME
        real_replace = installer.atomic_replace
        calls = 0

        def fail_backup_move(source: Path, destination: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected rollback failure")
            real_replace(source, destination)

        with mock.patch.object(installer, "REPO_ROOT", repo):
            with mock.patch.object(installer, "atomic_replace", side_effect=fail_backup_move):
                with self.assertRaisesRegex(OSError, "rollback failure"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        installer.rollback(skills)
        package.verify_package(active)
        package.verify_package(backup)
        self.assertFalse((skills / installer.JOURNAL_NAME).exists())

    def test_recovered_committed_rollback_reports_success_and_is_not_retried(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        with (repo / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("version two\n")
        refresh_fixture_lock(repo)
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills, force=True)
        active = skills / "seedance-20"
        backup = skills / installer.BACKUP_NAME
        self.assertIn("version two", (active / "SKILL.md").read_text(encoding="utf-8"))
        self.assertNotIn("version two", (backup / "SKILL.md").read_text(encoding="utf-8"))

        real_write_journal = installer.write_journal
        writes = 0

        def fail_third_journal(directory: Path, data: dict[str, object]) -> None:
            nonlocal writes
            writes += 1
            if writes == 3:
                raise OSError("injected third journal failure")
            real_write_journal(directory, data)

        output = io.StringIO()
        with mock.patch.object(installer, "REPO_ROOT", repo):
            with mock.patch.object(installer, "write_journal", side_effect=fail_third_journal):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(installer.rollback(skills), 0)
        self.assertIn("Recovered the requested rollback", output.getvalue())
        self.assertNotIn("version two", (active / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("version two", (backup / "SKILL.md").read_text(encoding="utf-8"))

        swap = Path(tempfile.mkdtemp(prefix=installer.SWAP_PREFIX, dir=skills))
        swap.rmdir()
        real_write_journal(
            skills,
            {
                "version": 1,
                "phase": "rollback_current_moved",
                "backup_name": backup.name,
                "swap_name": swap.name,
            },
        )
        installer.atomic_replace(active, swap)
        installer.atomic_replace(backup, active)
        with mock.patch.object(installer, "REPO_ROOT", repo):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(installer.rollback(skills, recover=True), 0)
        self.assertIn("version two", (active / "SKILL.md").read_text(encoding="utf-8"))
        self.assertNotIn("version two", (backup / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((skills / installer.JOURNAL_NAME).exists())

    def test_recover_prepared_phase_after_old_move_restores_active(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        active = skills / "seedance-20"
        backup = skills / installer.BACKUP_NAME
        stage = Path(tempfile.mkdtemp(prefix=installer.STAGE_PREFIX, dir=skills))
        plan = package.materialize_package(repo, stage)
        old = Path(tempfile.mkdtemp(prefix=installer.OLD_PREFIX, dir=skills))
        old.rmdir()
        installer.write_journal(
            skills,
            {
                "version": 1,
                "phase": "prepared",
                "backup_name": backup.name,
                "backup_kind": "none",
                "stage_name": stage.name,
                "old_name": old.name,
                "expected_tree_sha256": plan["tree_sha256"],
                "expected_payload_file_count": plan["payload_file_count"],
                "expected_payload_size_bytes": plan["payload_size_bytes"],
            },
        )
        installer.atomic_replace(active, old)
        self.assertFalse(active.exists())
        with (repo / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("checkout drift after crash\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.install(repo, skills, recover=True), 0)
        self.assertTrue(active.exists())
        package.verify_package(active)
        self.assertFalse(stage.exists())
        self.assertFalse((skills / installer.JOURNAL_NAME).exists())

    def test_recover_old_moved_phase_commits_only_expected_new_tree(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        active = skills / "seedance-20"
        backup = skills / installer.BACKUP_NAME
        plan = package.package_plan(repo)

        for forged in (False, True):
            with self.subTest(forged=forged):
                stage = Path(tempfile.mkdtemp(prefix=installer.STAGE_PREFIX, dir=skills))
                package.materialize_package(repo, stage)
                if forged:
                    with (stage / "SKILL.md").open("a", encoding="utf-8") as handle:
                        handle.write("forged but self-consistent\n")
                    resign_built_package(stage)
                    package.verify_package(stage)
                old = Path(tempfile.mkdtemp(prefix=installer.OLD_PREFIX, dir=skills))
                old.rmdir()
                journal = {
                    "version": 1,
                    "phase": "old_moved",
                    "backup_name": backup.name,
                    "backup_kind": "none" if not backup.exists() else "verified",
                    "stage_name": stage.name,
                    "old_name": old.name,
                    "expected_tree_sha256": plan["tree_sha256"],
                    "expected_payload_file_count": plan["payload_file_count"],
                    "expected_payload_size_bytes": plan["payload_size_bytes"],
                }
                installer.write_journal(skills, journal)
                installer.atomic_replace(active, old)
                installer.atomic_replace(stage, active)
                if forged:
                    installer.recover_transaction(skills, active, True)
                else:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(installer.install(repo, skills, recover=True), 0)
                installed = package.verify_package(active)
                self.assertEqual(installed, plan)
                self.assertNotIn("forged", (active / "SKILL.md").read_text(encoding="utf-8"))
                self.assertTrue(backup.is_dir())

    def test_recover_post_rotation_missing_or_corrupt_active_restores_backup(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        plan = package.package_plan(repo)

        for damage in ("missing", "corrupt"):
            with self.subTest(damage=damage):
                if not (skills / "seedance-20").exists():
                    with contextlib.redirect_stdout(io.StringIO()):
                        installer.install(repo, skills)
                with contextlib.redirect_stdout(io.StringIO()):
                    installer.install(repo, skills, force=True)
                active = skills / "seedance-20"
                backup = skills / installer.BACKUP_NAME
                stage = Path(tempfile.mkdtemp(prefix=installer.STAGE_PREFIX, dir=skills))
                stage.rmdir()
                old = Path(tempfile.mkdtemp(prefix=installer.OLD_PREFIX, dir=skills))
                old.rmdir()
                installer.write_journal(
                    skills,
                    {
                        "version": 1,
                        "phase": "new_moved",
                        "backup_name": backup.name,
                        "backup_kind": "verified",
                        "stage_name": stage.name,
                        "old_name": old.name,
                        "expected_tree_sha256": plan["tree_sha256"],
                        "expected_payload_file_count": plan["payload_file_count"],
                        "expected_payload_size_bytes": plan["payload_size_bytes"],
                    },
                )
                if damage == "missing":
                    shutil.rmtree(active)
                else:
                    with (active / "SKILL.md").open("a", encoding="utf-8") as handle:
                        handle.write("corrupt after rotation\n")
                installer.recover_transaction(skills, active, True)
                package.verify_package(active)
                self.assertFalse(backup.exists())
                self.assertFalse((skills / installer.JOURNAL_NAME).exists())

    def test_recover_rollback_crash_windows_restores_two_version_invariant(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
            installer.install(repo, skills, force=True)
        active = skills / "seedance-20"
        backup = skills / installer.BACKUP_NAME

        swap = Path(tempfile.mkdtemp(prefix=installer.SWAP_PREFIX, dir=skills))
        swap.rmdir()
        installer.write_journal(
            skills,
            {
                "version": 1,
                "phase": "rollback_prepared",
                "backup_name": backup.name,
                "swap_name": swap.name,
            },
        )
        installer.atomic_replace(active, swap)
        installer.recover_transaction(skills, active, True)
        package.verify_package(active)
        package.verify_package(backup)

        swap = Path(tempfile.mkdtemp(prefix=installer.SWAP_PREFIX, dir=skills))
        swap.rmdir()
        installer.write_journal(
            skills,
            {
                "version": 1,
                "phase": "rollback_current_moved",
                "backup_name": backup.name,
                "swap_name": swap.name,
            },
        )
        installer.atomic_replace(active, swap)
        installer.atomic_replace(backup, active)
        installer.recover_transaction(skills, active, True)
        package.verify_package(active)
        package.verify_package(backup)
        self.assertFalse(swap.exists())

    def test_prior_backup_survives_journal_write_failure_before_commit(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        with (repo / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("version two\n")
        refresh_fixture_lock(repo)
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills, force=True)
        backup = skills / installer.BACKUP_NAME
        before_backup = (backup / package.GENERATED_MANIFEST_NAME).read_bytes()

        with (repo / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("version three\n")
        refresh_fixture_lock(repo)
        with mock.patch.object(installer, "write_journal", side_effect=OSError("injected ENOSPC")):
            with self.assertRaisesRegex(OSError, "ENOSPC"):
                with contextlib.redirect_stdout(io.StringIO()):
                    installer.install(repo, skills, force=True)
        self.assertEqual((backup / package.GENERATED_MANIFEST_NAME).read_bytes(), before_backup)
        package.verify_package(skills / "seedance-20")
        package.verify_package(backup)

    def test_staging_plan_change_aborts_before_activation(self) -> None:
        repo = self.base / "repo"
        make_fixture(repo)
        skills = self.base / "skills"
        with contextlib.redirect_stdout(io.StringIO()):
            installer.install(repo, skills)
        active = skills / "seedance-20"
        before = (active / package.GENERATED_MANIFEST_NAME).read_bytes()
        real_materialize = installer.materialize_package

        def mismatched_plan(source: Path, stage: Path) -> dict:
            result = dict(real_materialize(source, stage))
            result["tree_sha256"] = "f" * 64
            return result

        with mock.patch.object(installer, "materialize_package", side_effect=mismatched_plan):
            with self.assertRaisesRegex(installer.InstallError, "planning and staging"):
                with contextlib.redirect_stdout(io.StringIO()):
                    installer.install(repo, skills, force=True)
        self.assertEqual((active / package.GENERATED_MANIFEST_NAME).read_bytes(), before)

    def test_recover_removes_interrupted_journal_temporary_file(self) -> None:
        skills = self.base / "skills"
        skills.mkdir()
        active = skills / "seedance-20"
        temporary = skills / f"{installer.JOURNAL_NAME}.tmp"
        temporary.write_text("partial", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "incomplete"):
            installer.recover_transaction(skills, active, False)
        installer.recover_transaction(skills, active, True)
        self.assertFalse(temporary.exists())

    def test_destination_lock_serializes_and_stale_file_needs_no_pid_probe(self) -> None:
        skills = self.base / "skills"
        skills.mkdir()
        with installer.InstallLock(skills, recover=False):
            with self.assertRaisesRegex(installer.InstallError, "active"):
                with installer.InstallLock(skills, recover=False):
                    pass

        lock = skills / installer.LOCK_NAME
        self.assertTrue(lock.is_file())
        lock.write_text('{"pid": 999999999}\n', encoding="utf-8")
        with mock.patch.object(os, "kill", side_effect=AssertionError("PID probing is forbidden"), create=True):
            with installer.InstallLock(skills, recover=False):
                self.assertTrue(lock.is_file())
        self.assertTrue(lock.is_file())

    def test_os_lock_contends_across_processes(self) -> None:
        skills = self.base / "skills"
        skills.mkdir()
        code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from scripts.install_codex_skill import InstallLock\n"
            "with InstallLock(Path(sys.argv[1]), False):\n"
            "    print('READY', flush=True)\n"
            "    sys.stdin.readline()\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", code, str(skills)],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "READY")
            with self.assertRaisesRegex(installer.InstallError, "active"):
                with installer.InstallLock(skills, recover=True):
                    pass
        finally:
            if process.stdin:
                process.stdin.write("\n")
                process.stdin.flush()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)

    def test_hardlinked_lock_cannot_modify_external_file(self) -> None:
        skills = self.base / "skills"
        skills.mkdir()
        external = self.base / "outside.txt"
        external.write_text("DO NOT MODIFY\n", encoding="utf-8")
        try:
            os.link(external, skills / installer.LOCK_NAME)
        except (OSError, NotImplementedError):
            self.skipTest("hard links unavailable")
        with self.assertRaisesRegex(installer.InstallError, "private regular file"):
            with installer.InstallLock(skills, recover=False):
                pass
        self.assertEqual(external.read_text(encoding="utf-8"), "DO NOT MODIFY\n")


if __name__ == "__main__":
    unittest.main()
