from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import project_state_check as project_state


ROOT = Path(__file__).resolve().parents[1]


class ProjectStateTests(unittest.TestCase):
    def test_project_state_examples_validate(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/project_state_check.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_checker_routes_v2_away_from_v1(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "standalone-clip" / "project-state.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples"
            examples.mkdir()
            (examples / "project-state.json").write_text(json.dumps(source), encoding="utf-8")
            (examples / "project-state-v2.json").write_text(
                json.dumps(
                    {
                        "$schema": project_state.V2_SCHEMA_URI,
                        "schema_version": 2,
                        "clips": "deliberately not a v1 clip list",
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "project_state_check.py"), str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 project states", result.stdout)

    def test_legacy_lineage_rejects_invalid_indexes_and_cycles(self) -> None:
        base = json.loads(
            (ROOT / "examples" / "sequence-airport-arrival" / "project-state.json").read_text(encoding="utf-8")
        )
        mutations = {
            "boolean index": lambda value: value["clips"][1].update(sequence_index=True),
            "duplicate index": lambda value: value["clips"][1].update(sequence_index=1),
            "self parent": lambda value: value["clips"][1].update(parent_clip_id="clip_02"),
            "future parent": lambda value: value["clips"][1].update(parent_clip_id="clip_03"),
            "beat cycle": lambda value: value["beats"][0].update(dependencies=[value["beats"][1]["beat_id"]]),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "project-state.json"
            for label, mutate in mutations.items():
                value = copy.deepcopy(base)
                mutate(value)
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(label=label):
                    self.assertTrue(project_state.validate_project(path, root))


if __name__ == "__main__":
    unittest.main()
