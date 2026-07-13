from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOCKED_V709 = {
    "schemas/scene-ir-v2.schema.json": "5e777eb4b5a5a7385610f219a2f2f2143e54ef9c210537b85a85c6fcb22faf27",
    "schemas/surface-av-policy.schema.json": "b29781b0ac57cb55860d926affde46b47bc6e597b43dfc58178e1c7427c99750",
    "schemas/prompt-program-v2.schema.json": "ec524463b22bf323f3c190bf18ad32ba000a3f7b5457a795547eeef9584a7d04",
    "schemas/prompt-render-v2.schema.json": "8a9ca832d154ec08351c00463ca5cfd975324f6c19608ceb8967eb5283817276",
    "schemas/prompt-compile-request-v2.schema.json": "132bb9cbd2e31f0ba6347bba1262ffc156d55b48f83607c936aabb966b140770",
    "schemas/prompt-realization-catalog-v2.schema.json": "38104e23468c08600ac9ede88f81642dd9310f82f9ec96bcb3167347c599922c",
    "schemas/surface-binding-set-v2.schema.json": "b025be6b92b34ec64aef74593fca3440a5bdd69ae945e5157f1a4cbe2c502ca2",
    "schemas/av-take-review-v1.schema.json": "db91fcce20431c10be615051bd903be1b0910d126fac22c90ae02b5c894f9248",
    "scripts/scene_ir_v2_check.py": "f02b24518d4c3483a150864827939dac762668e81724af177c11c90be9be3556",
    "scripts/semantic_lint_v2.py": "d731afd98318488b9a3aef52f2d9a0d3314de34881f77e38bca9af41ff1c45d7",
    "scripts/prompt_compile_v2.py": "5eeb0dc1baf3932abd081d076e1b071b91e83827894b11e244e577d4b22c12ac",
    "scripts/av_take_review_check.py": "e706cf452e0e93327ca9dcfedc0103c39c8a6a41c9f6c5b3d0814146fa372ff1",
    "validation/fixtures/scene-ir-v2.valid.json": "0c5d4ed7a6e494058d1127c1ad3e5f4f13caaa626c2c70594b7774b3ed20f390",
    "validation/fixtures/surface-av-policy.valid.json": "16bb4ce484ec18b395fb313cf67ce24e00c3f3eb793de036c727fc64fbe331d6",
    "validation/fixtures/prompt-program-v2.valid.json": "d6f9dbec0f35b420dec498348f719a2a7e53a159b0f61017c8aad3578dc99c64",
    "validation/fixtures/prompt-render-v2.valid.json": "b2dace89e727398c22f096be1ca9e9cd61f8c731162a6bd95e5e96f70f30deec",
    "validation/fixtures/prompt-compile-request-v2.valid.json": "199fa85678f9fb3985fe2ad0bee5c6fb67a4aa699cba307223c8fd386756f4f0",
    "validation/fixtures/prompt-realization-catalog-v2.valid.json": "81b7e8738cc779d04b79c5caf02be8bac5a4dff04106206d4d5884724c11ccbc",
    "validation/fixtures/surface-binding-set-v2.valid.json": "50ba195c5b6bbb98d03be151ee62bfede45e7e2ffae65ad2ae39963860ad4d1b",
    "validation/fixtures/av-take-review-v1.valid.json": "43dcaef0133f9f52f1d09d972f12c25fd7eb18fddf39a2b0d0d121b53508635b",
}


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


class V710RegressionTests(unittest.TestCase):
    def test_v709_contracts_tools_and_fixtures_remain_byte_exact(self) -> None:
        self.assertEqual({path: digest(path) for path in LOCKED_V709}, LOCKED_V709)

    def test_provider_and_evidence_activation_remain_closed(self) -> None:
        profile_index = json.loads((ROOT / "profiles/profile-index.json").read_text(encoding="utf-8"))
        release_policy = json.loads((ROOT / "research/evidence/release-policy.json").read_text(encoding="utf-8"))
        self.assertIs(profile_index["activation_enabled"], False)
        self.assertIs(release_policy["activation_enabled"], False)

    def test_v710_checker_has_no_provider_or_process_transport(self) -> None:
        source = (ROOT / "scripts/evaluation_program_check.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_module_roots = {"socket", "subprocess", "requests", "urllib", "http"}
        forbidden_os_calls = {
            "system",
            "popen",
            "execl",
            "execle",
            "execlp",
            "execlpe",
            "execv",
            "execve",
            "execvp",
            "execvpe",
            "spawnl",
            "spawnle",
            "spawnlp",
            "spawnlpe",
            "spawnv",
            "spawnve",
            "spawnvp",
            "spawnvpe",
        }
        imported: set[str] = set()
        forbidden_calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                if node.module == "os":
                    forbidden_calls.extend(
                        f"from os import {alias.name}"
                        for alias in node.names
                        if alias.name in forbidden_os_calls
                    )
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    if node.func.attr in forbidden_os_calls:
                        forbidden_calls.append(f"os.{node.func.attr}")
        self.assertFalse({module.split(".", 1)[0] for module in imported} & forbidden_module_roots)
        self.assertEqual(forbidden_calls, [])
        self.assertNotIn("ANTHROPIC_API_KEY", source)
        self.assertNotIn("OPENAI_API_KEY", source)


if __name__ == "__main__":
    unittest.main()
