from __future__ import annotations

import tempfile
import unittest
import urllib.request
from pathlib import Path

from scripts.seedance_ark_client import ArkSeedanceClient
from scripts.seedance_download import HttpsOnlyRedirectHandler
from scripts.seedance_request import GenerationRequest, ReferenceInput, validate_generation_request

from tests.test_seedance_generate import FakeOpener, FakeResponse


TEST_MODEL = "doubao-seedance-2-0-260128"


class ReferenceSecurityTests(unittest.TestCase):
    def test_reference_urls_require_https_without_embedded_credentials(self) -> None:
        for url in (
            "http://assets.example/image.png",
            "file:///etc/hosts",
            "https://user:secret@assets.example/image.png",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "HTTPS|credentials"):
                validate_generation_request(
                    GenerationRequest(
                        "A lamp turns on.",
                        TEST_MODEL,
                        references=(ReferenceInput("image_url", url, "reference_image"),),
                    )
                )

    def test_reference_counts_enforce_type_and_total_limits(self) -> None:
        cases = (
            (
                tuple(
                    ReferenceInput("image_url", f"https://assets.example/{index}.png", "reference_image")
                    for index in range(10)
                ),
                "9 image",
            ),
            (
                tuple(
                    ReferenceInput("video_url", f"https://assets.example/{index}.mp4", "reference_video")
                    for index in range(4)
                ),
                "3 video",
            ),
            (
                (
                    ReferenceInput("image_url", "https://assets.example/visual.png", "reference_image"),
                    *(
                        ReferenceInput("audio_url", f"https://assets.example/{index}.mp3", "reference_audio")
                        for index in range(4)
                    ),
                ),
                "3 audio",
            ),
            (
                (
                    *(
                        ReferenceInput("image_url", f"https://assets.example/i-{index}.png", "reference_image")
                        for index in range(7)
                    ),
                    *(
                        ReferenceInput("video_url", f"https://assets.example/v-{index}.mp4", "reference_video")
                        for index in range(3)
                    ),
                    *(
                        ReferenceInput("audio_url", f"https://assets.example/a-{index}.mp3", "reference_audio")
                        for index in range(3)
                    ),
                ),
                "12 total",
            ),
        )

        for references, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                validate_generation_request(
                    GenerationRequest("A lamp turns on.", TEST_MODEL, references=references)
                )


class DownloadSecurityTests(unittest.TestCase):
    def test_redirect_handler_rejects_a_non_https_intermediate_target(self) -> None:
        handler = HttpsOnlyRedirectHandler()
        request = urllib.request.Request("https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/start.mp4")

        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://ark-acg-cn-beijing.tos-cn-beijing.volces.com/final.mp4",
            )

    def test_https_redirect_is_accepted_after_validation(self) -> None:
        opener = FakeOpener(
            [
                FakeResponse(
                    b"video",
                    content_type="video/mp4",
                    url="https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/final.mp4",
                )
            ]
        )
        client = ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            download_opener=opener,
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            client.download("https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/start.mp4", output)

            self.assertEqual(b"video", output.read_bytes())

    def test_redirect_to_non_https_and_missing_content_type_are_rejected(self) -> None:
        client = ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            download_opener=FakeOpener(
                [FakeResponse(b"video", content_type="video/mp4", url="http://ark-acg-cn-beijing.tos-cn-beijing.volces.com/final.mp4")]
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                client.download("https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/start.mp4", output)

            client.download_opener = FakeOpener(
                [FakeResponse(b"video", content_type="", url="https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/start.mp4")]
            )
            with self.assertRaisesRegex(RuntimeError, "Content-Type"):
                client.download("https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/start.mp4", output)

            self.assertFalse(output.exists())

    def test_sub2api_downloads_only_from_lovart_hosts(self) -> None:
        client = ArkSeedanceClient(
            "secret",
            "https://token.aiedulab.cn/api/v3",
            download_opener=FakeOpener(
                [FakeResponse(b"internal", content_type="video/mp4", url="https://127.0.0.1/video.mp4")]
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            with self.assertRaisesRegex(ValueError, "not allowed"):
                client.download("https://127.0.0.1/video.mp4", output)

            client.download_opener = FakeOpener(
                [FakeResponse(b"video", content_type="video/mp4", url="https://a.lovart.ai/video.mp4")]
            )
            client.download("https://a.lovart.ai/video.mp4", output)
            self.assertEqual(b"video", output.read_bytes())

    def test_official_ark_downloads_only_from_ark_storage_hosts(self) -> None:
        client = ArkSeedanceClient(
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            download_opener=FakeOpener([]),
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not allowed"):
                client.download("https://127.0.0.1/internal.mp4", Path(directory) / "result.mp4")


if __name__ == "__main__":
    unittest.main()
