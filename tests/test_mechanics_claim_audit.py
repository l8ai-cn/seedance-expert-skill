from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import mechanics_claim_audit as audit


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mechanics_claim_audit.py"


class MechanicsClaimAuditTests(unittest.TestCase):
    def make_repo(self, text: str, *, relative: str = "references/mechanics.md") -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return temporary, root

    def test_positive_hidden_mechanism_claims_are_rejected(self) -> None:
        cases = (
            ("Seedance understands real physics internally.\n", "MECH001_PHYSICS_INTERNAL_CLAIM"),
            ("The model uses an attention budget for every moving subject.\n", "MECH002_ARCHITECTURE_CLAIM"),
            ("This fails because of the training distribution.\n", "MECH003_TRAINING_DISTRIBUTION_CAUSE"),
            ("Use mechanism-aligned staging for the trajectory conflict.\n", "MECH004_TRAJECTORY_INTERNAL_CLAIM"),
            ("The sample was unlucky because of sampling variance.\n", "MECH005_SAMPLING_CAUSE_ASSERTED"),
            ("The same seed makes this a controlled experiment.\n", "MECH006_SEED_DETERMINISM_ASSERTED"),
            ("Three retries prove the prompt is wrong by definition.\n", "MECH007_REPEAT_PROVES_CAUSE"),
            ("Extension depth 2 causes identity drift.\n", "MECH008_CHAIN_DEPTH_PHYSICS_ASSERTED"),
            ("Identity decays along output-sourced chains.\n", "MECH009_CHAIN_IDENTITY_DECAY_ASSERTED"),
            ("Motion and identity compete for a finite fidelity budget.\n", "MECH010_FINITE_FIDELITY_BUDGET_ASSERTED"),
            ("Seedance 内置物理引擎，能够理解真实世界物理。\n", "MECH011_ZH_PHYSICS_INTERNAL_CLAIM"),
            ("该模型会分配注意力预算来处理每个运动主体。\n", "MECH012_ZH_ATTENTION_BUDGET_CLAIM"),
        )
        for text, code in cases:
            temporary, root = self.make_repo(text)
            with temporary, self.subTest(code=code):
                findings = audit.audit_paths(root)
                self.assertEqual([item[2] for item in findings], [code])

    def test_explicit_uncertainty_and_boundary_language_is_allowed(self) -> None:
        text = "\n".join(
            (
                "Do not attribute a result to training data or sampling without evidence.",
                "The retained evidence does not establish how Seedance computes physics internally.",
                "This event graph is a planning heuristic, not proof of a physics engine.",
                "The internal architecture and denoising process are unpublished and unknown.",
                "Record the observable failure on the exact surface and change one variable.",
            )
        )
        temporary, root = self.make_repo(text)
        with temporary:
            self.assertEqual(audit.audit_paths(root), [])

    def test_nfkc_confusable_spelling_cannot_bypass_a_rule(self) -> None:
        temporary, root = self.make_repo("Ｔｈｅ ｍｏｄｅｌ ｕｓｅｓ ａｎ ａｔｔｅｎｔｉｏｎ ｂｕｄｇｅｔ.\n")
        with temporary:
            findings = audit.audit_paths(root)
            self.assertEqual(findings[0][2], "MECH002_ARCHITECTURE_CLAIM")

    def test_default_ignorable_cannot_split_a_prohibited_name(self) -> None:
        temporary, root = self.make_repo("Seed\u200bance understands physics internally.\n")
        with temporary:
            findings = audit.audit_paths(root)
            self.assertEqual([item[2] for item in findings], ["MECH001_PHYSICS_INTERNAL_CLAIM"])

    def test_wrapped_and_long_gap_claims_are_rejected(self) -> None:
        wrapped = "Seedance understands real\nphysics internally.\n"
        wrapped_list = "- Seedance understands real\n  physics internally.\n"
        long_gap = "The model " + ("carefully and deliberately " * 6) + "possesses a world model.\n"
        for text in (wrapped, wrapped_list, long_gap):
            temporary, root = self.make_repo(text)
            with temporary, self.subTest(text=text):
                findings = audit.audit_paths(root)
                self.assertEqual([item[2] for item in findings], ["MECH001_PHYSICS_INTERNAL_CLAIM"])

    def test_correct_negations_pass_but_unrelated_boundary_does_not(self) -> None:
        allowed = (
            "Seedance does not understand physics internally.\n",
            "The model doesn't understand physics internally.\n",
            "The same seed does not make this a controlled experiment.\n",
            "The same seed isn't a controlled experiment.\n",
            "Three retries do not prove the prompt is wrong.\n",
            "Extension depth 2 does not cause identity drift.\n",
            "Do not claim Seedance understands physics internally.\n",
            "没有证据表明该模型拥有世界模型。\n",
        )
        for text in allowed:
            temporary, root = self.make_repo(text)
            with temporary, self.subTest(text=text):
                self.assertEqual(audit.audit_paths(root), [])

        temporary, root = self.make_repo(
            "Seedance understands physics internally. Do not infer sampling causes.\n"
        )
        with temporary:
            findings = audit.audit_paths(root)
            self.assertEqual([item[2] for item in findings], ["MECH001_PHYSICS_INTERNAL_CLAIM"])

        unrelated_boundaries = (
            "Do not claim attention, but Seedance understands physics internally.\n",
            "Seedance does not rotate, but understands physics internally.\n",
        )
        for text in unrelated_boundaries:
            temporary, root = self.make_repo(text)
            with temporary, self.subTest(text=text):
                findings = audit.audit_paths(root)
                self.assertEqual([item[2] for item in findings], ["MECH001_PHYSICS_INTERNAL_CLAIM"])

    def test_eval_user_attack_prompt_is_not_audited_as_project_guidance(self) -> None:
        payload = (
            '{"cases":[{"id":"case","prompt":"Seedance understands physics internally",'
            '"expected_output":"Correct the unsupported premise",'
            '"assertions":["do not claim a hidden physics engine"],'
            '"failure_mode":"accepting the premise",'
            '"skills_expected_to_activate":["seedance-motion"]}]}\n'
        )
        temporary, root = self.make_repo(payload, relative="evals/evals.json")
        with temporary:
            self.assertEqual(audit.audit_paths(root), [])

    def test_positive_eval_oracle_is_rejected_while_prompt_remains_excluded(self) -> None:
        payload = (
            '{"cases":[{"id":"case","prompt":"Seedance understands physics internally",'
            '"expected_output":"The model possesses a world model",'
            '"assertions":["reject the premise"],'
            '"failure_mode":"accepting the premise",'
            '"skills_expected_to_activate":["seedance-motion"]}]}\n'
        )
        temporary, root = self.make_repo(payload, relative="evals/evals.json")
        with temporary:
            findings = audit.audit_paths(root)
            self.assertEqual([item[2] for item in findings], ["MECH001_PHYSICS_INTERNAL_CLAIM"])

    def test_public_eval_oracles_contain_no_positive_hidden_mechanism_claims(self) -> None:
        findings = audit.audit_paths(ROOT, [ROOT / "evals" / "evals.json"])
        self.assertEqual(findings, [])

    def test_cli_does_not_echo_matched_input(self) -> None:
        sentinel = "DO_NOT_ECHO_SECRET_SENTINEL"
        temporary, root = self.make_repo(
            f"Seedance understands physics internally {sentinel}.\n"
        )
        with temporary:
            process = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 1)
            self.assertIn("MECH001_PHYSICS_INTERNAL_CLAIM", process.stdout)
            self.assertNotIn(sentinel, process.stdout + process.stderr)

    def test_cli_is_byte_deterministic_across_ten_hash_seeds(self) -> None:
        temporary, root = self.make_repo(
            "The model uses an attention budget.\n"
            "Seedance understands physics internally.\n"
        )
        outputs: list[tuple[int, bytes, bytes]] = []
        with temporary:
            for seed in ("0", "1", "2", "3", "7", "11", "42", "101", "706", "999"):
                environment = os.environ.copy()
                environment["PYTHONHASHSEED"] = seed
                process = subprocess.run(
                    [sys.executable, "-S", "-B", str(SCRIPT), str(root)],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    check=False,
                )
                outputs.append((process.returncode, process.stdout, process.stderr))
        self.assertTrue(all(output == outputs[0] for output in outputs))
        self.assertEqual(outputs[0][0], 1)

    def test_cli_runs_without_site_packages_or_bytecode_writes(self) -> None:
        temporary, root = self.make_repo("The model possesses a world model.\n")
        with temporary:
            process = subprocess.run(
                [sys.executable, "-S", "-B", str(SCRIPT), str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(process.returncode, 1)
        self.assertIn("MECH001_PHYSICS_INTERNAL_CLAIM", process.stdout)
        self.assertEqual(process.stderr, "")

    def test_migrated_archive_is_not_active_guidance(self) -> None:
        temporary, root = self.make_repo(
            "Seedance understands physics internally.\n",
            relative="references/migrated/legacy.md",
        )
        with temporary:
            self.assertEqual(audit.audit_paths(root), [])


if __name__ == "__main__":
    unittest.main()
