from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_DOCS = (
    ROOT / "README.md",
    *(ROOT / "docs").glob("QUICKSTART*.md"),
    ROOT / "references" / "agent-compatibility.md",
)


class SeedancePackagingTests(unittest.TestCase):
    def test_installer_uses_independent_seedance_expert_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills_dir = Path(directory)
            legacy = skills_dir / "seedance-20"
            legacy.mkdir()
            marker = legacy / "marker.txt"
            marker.write_text("keep", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "install_codex_skill.py"),
                    "--dest",
                    str(skills_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((skills_dir / "seedance-expert" / "SKILL.md").exists())
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))

    def test_active_loading_chain_uses_native_markdown_links(self) -> None:
        paths = [ROOT / "SKILL.md", *(ROOT / "skills").glob("*/SKILL.md")]
        paths.extend(
            path
            for path in (ROOT / "references").rglob("*.md")
            if "migrated" not in path.parts
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("[ref:", text, path.as_posix())
            self.assertNotIn("[skill:", text, path.as_posix())

    def test_all_subskills_point_to_seedance_expert(self) -> None:
        for path in (ROOT / "skills").glob("seedance-*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn('parent: "seedance-expert"', text, path.as_posix())

    def test_installation_docs_use_seedance_expert_name(self) -> None:
        for path in INSTALL_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("seedance-20", text, path.as_posix())
            if path.name.startswith("QUICKSTART") or path.name == "README.md":
                self.assertIn("seedance-expert", text, path.as_posix())

    def test_non_test_python_files_stay_under_two_hundred_lines(self) -> None:
        oversized = {
            path.relative_to(ROOT).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
            for path in ROOT.rglob("*.py")
            if "tests" not in path.parts
            and ".git" not in path.parts
            and len(path.read_text(encoding="utf-8").splitlines()) >= 200
        }

        self.assertEqual({}, oversized)

    def test_validator_keeps_upstream_subskill_fields_strict(self) -> None:
        module_path = ROOT / "scripts" / "validate_skills.py"
        spec = importlib.util.spec_from_file_location("validate_skills", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(
            ["name", "description", "license", "metadata"],
            module.ROOT_REQUIRED_FIELDS,
        )
        self.assertEqual(
            ["name", "description", "license", "user-invocable", "tags", "metadata"],
            module.SUBSKILL_REQUIRED_FIELDS,
        )

    def test_validator_does_not_relax_subskill_frontmatter(self) -> None:
        from scripts.seedance_validation_core import validate_skill

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "seedance-child" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\n"
                "name: seedance-child\n"
                "description: This skill should be used when testing.\n"
                "license: MIT\n"
                "metadata:\n"
                '  version: "6.6.0"\n'
                '  parent: "seedance-expert"\n'
                "---\n\n"
                "## Intent\n\n"
                + "Detailed behavior. " * 20,
                encoding="utf-8",
            )
            errors: list[str] = []

            validate_skill(skill, root, "6.6.0", errors, [])

            self.assertTrue(any("user-invocable" in error for error in errors), errors)
            self.assertTrue(any("tags" in error for error in errors), errors)

    def test_validator_root_adaptation_does_not_change_warning_semantics(self) -> None:
        from scripts.seedance_validation_runner import run_validation

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text(
                "---\n"
                "name: seedance-expert\n"
                "description: This skill should be used when testing.\n"
                "license: MIT\n"
                "metadata:\n"
                '  version: "6.6.0"\n'
                "---\n\n"
                "Short body.\n",
                encoding="utf-8",
            )

            result = run_validation(
                root,
                expected_skills=[],
                expected_version="6.6.0",
                required_files=[],
                required_references=[],
                strict=True,
            )

            self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
