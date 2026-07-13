from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOCKED_V707 = {
    "scripts/scene_ir_check.py": "546ba78508e21000e4573f3ad05384bd584ebd52df62a241f923eb20f175bd65",
    "scripts/reference_planner.py": "b67052521bcc42e02be47855a456fe729942aed7d483a53d7ea0a69a54287138",
    "scripts/semantic_lint.py": "0221e395e39d1211027dabb2ccd320f14bd75d1d295be7f70d6105330b7cabf9",
    "scripts/prompt_compile.py": "d1f88300d2ec6ba695a04c00ac54fa6455b088b82e308f7db10355d0e233a2f0",
    "scripts/render_surface_bindings.py": "f994d514ab5bb98ee28d4903f9151b14633526548830cf57b04be26c4911e3fd",
    "schemas/scene-ir.schema.json": "eb36b1a0c06c07d75489bae694c3dac32c58364814a1d4993e642ed2438a6415",
    "schemas/prompt-program.schema.json": "1589623a30afcda55fd68fcbe0f4e6b5dc2a0cbe2bf7af8329e2d773d966c53b",
    "schemas/prompt-realization-catalog.schema.json": "5b45391e2d8afdebcb1bd56354db0062f95ae9c76b805f7324e0dcf0e296642e",
    "schemas/prompt-render.schema.json": "28f8c6dda5511684b65dff714a8bd76f1de0d7e80f5acf7330924333dfe972cb",
}

LOCKED_V708 = {
    "schemas/project-state-v2.schema.json": "1f6531ccb501aa8c986ae8b8826a92a3542fe10ab2870b2c30c151b7c733f5e6",
    "schemas/prompt-spec-v2.schema.json": "ba83d443c939a67881bb2a17a142c513327014d4ac05cb26959228d8da4bc037",
    "schemas/generation-run-v2.schema.json": "61af033f15c50d91f5c5293d329245831828da5480009d7e99db88f29a6f8716",
    "schemas/take-review-v2.schema.json": "318fe0ffa9b8a09d90a4aa938404e085227486654c48eadc923f0219c9752956",
    "scripts/project_state_v2_check.py": "d1ba013700848d6ed15e6d41715632f0a88d129a5280454de996f9935932c51f",
    "scripts/v2_aux_check.py": "0e7c5ce0a4b0ae21d08f4e4ab7855125b492806f972afe552c70955aa78157db",
}


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


class V709RegressionTests(unittest.TestCase):
    def test_v707_toolchain_remains_byte_exact(self) -> None:
        self.assertEqual({path: digest(path) for path in LOCKED_V707}, LOCKED_V707)

    def test_v708_state_and_execution_blockers_remain_byte_exact(self) -> None:
        self.assertEqual({path: digest(path) for path in LOCKED_V708}, LOCKED_V708)

    def test_provider_activation_remains_closed(self) -> None:
        profile_index = json.loads((ROOT / "profiles/profile-index.json").read_text(encoding="utf-8"))
        release_policy = json.loads((ROOT / "research/evidence/release-policy.json").read_text(encoding="utf-8"))
        self.assertIs(profile_index["activation_enabled"], False)
        self.assertIs(release_policy["activation_enabled"], False)
        for group in ("models", "surfaces"):
            for entry in profile_index[group]:
                self.assertEqual(entry["status"], "candidate")
                self.assertIs(entry["runtime_enabled"], False)

    def test_v709_scripts_have_no_provider_transport(self) -> None:
        forbidden = ("requests.", "urllib.request", "http.client", "subprocess.", "socket.")
        for relative in (
            "scripts/scene_ir_v2_check.py",
            "scripts/semantic_lint_v2.py",
            "scripts/prompt_compile_v2.py",
            "scripts/av_take_review_check.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertFalse(any(token in text for token in forbidden), relative)


if __name__ == "__main__":
    unittest.main()
