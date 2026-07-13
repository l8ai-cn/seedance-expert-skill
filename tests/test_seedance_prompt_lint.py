from __future__ import annotations

import unittest

from scripts.seedance_prompt_lint import lint_prompt


class SeedancePromptLintTests(unittest.TestCase):
    def test_rejects_empty_prompt(self) -> None:
        self.assertIn("prompt is empty", lint_prompt("")[0])

    def test_rejects_unresolved_image_reference(self) -> None:
        errors = lint_prompt("图片2中的纸船缓慢漂过水面。", image_count=1)

        self.assertIn("图片2", errors[0])

    def test_rejects_unresolved_video_and_audio_references(self) -> None:
        errors = lint_prompt(
            "Video2 guides the motion while Audio2 guides the voice.",
            video_count=1,
            audio_count=1,
        )

        self.assertTrue(any("Video2" in error for error in errors))
        self.assertTrue(any("Audio2" in error for error in errors))

    def test_rejects_conflicting_primary_camera_moves(self) -> None:
        errors = lint_prompt("镜头缓慢推进，同时持续拉远，人物转身看向窗外。")

        self.assertTrue(any("camera" in error for error in errors))

    def test_rejects_overloaded_timeline(self) -> None:
        prompt = " ".join(f"{second}-{second + 1}s 人物完成一个动作。" for second in range(9))

        errors = lint_prompt(prompt)

        self.assertTrue(any("timeline" in error for error in errors))

    def test_accepts_compact_production_prompt(self) -> None:
        errors = lint_prompt(
            "固定机位，中景。晨光从左侧窗户照入，女孩把纸船放入浅水，"
            "纸船缓慢漂向镜头，环境中只有水声和远处鸟鸣。"
        )

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
