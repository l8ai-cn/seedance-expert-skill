from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import continuity_chain_check as continuity


ROOT = Path(__file__).resolve().parents[1]


class ContinuityChainTests(unittest.TestCase):
    def test_continuity_chain_examples_validate(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/continuity_chain_check.py", "--strict"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_allowances_are_dimension_scoped(self) -> None:
        clip = {
            "transition_in": "intentional next shot with axis reset",
            "allowed_changes": [],
            "accepted_deviations": [],
            "continuity_breaks": [],
        }
        self.assertFalse(continuity.has_allowance(clip, "wardrobe"))
        self.assertFalse(continuity.has_allowance(clip, "location"))
        self.assertTrue(continuity.has_allowance(clip, "travel_direction"))
        clip["allowed_changes"] = ["wardrobe may change"]
        self.assertTrue(continuity.has_allowance(clip, "wardrobe"))

    def test_ambiguous_nested_state_is_order_independent(self) -> None:
        def payload(owner_order: tuple[str, str]) -> dict:
            observed = {
                owner: {"wardrobe": "coat-a" if owner == "owner_a" else "coat-b"}
                for owner in owner_order
            }
            return {
                "clips": [
                    {"clip_id": "clip_01", "parent_clip_id": None, "status": "accepted", "observed_end_state": observed},
                    {
                        "clip_id": "clip_02",
                        "parent_clip_id": "clip_01",
                        "status": "ready",
                        "planned_start_state": {"owner_a": {"wardrobe": "coat-a"}},
                        "transition_in": "intentional next shot",
                        "allowed_changes": [],
                        "accepted_deviations": [],
                        "continuity_breaks": [],
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "project-state.json"
            outputs = []
            for order in (("owner_a", "owner_b"), ("owner_b", "owner_a")):
                path.write_text(json.dumps(payload(order)), encoding="utf-8")
                outputs.append(continuity.validate(path, root))
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(any("ambiguous wardrobe" in error for error in outputs[0][0]))


if __name__ == "__main__":
    unittest.main()
