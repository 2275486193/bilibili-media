"""Offline checks for download mode and page selection."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bilibili_media as media


BVID = "BV1234567890"
PAGES = [
    {"page": 1, "cid": 101, "part": "First part", "duration": 60},
    {"page": 2, "cid": 102, "part": "Second part", "duration": 90},
]


class SelectionTests(unittest.TestCase):
    def metadata(self, pages=None):
        return {"title": "Example", "owner": {"name": "Example author"},
                "desc": "", "pages": PAGES if pages is None else pages}

    def test_missing_url_page_remains_unspecified(self):
        self.assertEqual(media.parse_target(BVID), (BVID, None))
        self.assertEqual(media.parse_target(f"https://www.bilibili.com/video/{BVID}/"), (BVID, None))

    def test_explicit_url_page_is_preserved(self):
        self.assertEqual(media.parse_target(f"https://www.bilibili.com/video/{BVID}/?p=1"), (BVID, 1))

    def test_single_page_is_selected_automatically(self):
        with patch.object(media, "api", return_value=self.metadata(PAGES[:1])):
            self.assertEqual(media.get_info(BVID)["selected_page"], PAGES[0])

    def test_multiple_pages_remain_unselected(self):
        with patch.object(media, "api", return_value=self.metadata()):
            info = media.get_info(BVID)
        self.assertIsNone(info["selected_page"])
        self.assertEqual(info["pages"], PAGES)
        self.assertNotIn("?p=", info["source_url"])

    def test_explicit_selection_by_page_cid_or_url(self):
        cases = [(BVID, {"page": 1}, PAGES[0]), (BVID, {"page": 2}, PAGES[1]),
                 (BVID, {"cid": 102}, PAGES[1]),
                 (f"https://www.bilibili.com/video/{BVID}/?p=2", {}, PAGES[1])]
        for target, kwargs, expected in cases:
            with self.subTest(target=target, kwargs=kwargs):
                with patch.object(media, "api", return_value=self.metadata()):
                    self.assertEqual(media.get_info(target, **kwargs)["selected_page"], expected)

    def test_invalid_selection_and_empty_pages_are_rejected(self):
        for pages, kwargs in [(PAGES, {"page": 3}), (PAGES, {"cid": 999}), ([], {})]:
            with self.subTest(pages=pages, kwargs=kwargs):
                with patch.object(media, "api", return_value=self.metadata(pages)):
                    with self.assertRaises(ValueError):
                        media.get_info(BVID, **kwargs)

    def test_inspect_returns_candidates_without_fetching_tracks(self):
        with patch.object(sys, "argv", ["bilibili_media.py", "inspect", BVID]):
            with patch.object(media, "api", return_value=self.metadata()), \
                    patch.object(media, "get_tracks") as tracks, patch.object(media, "emit") as emit:
                media.main()
        tracks.assert_not_called()
        result = emit.call_args.args[0]
        self.assertEqual(result["status"], "needs_selection")
        self.assertEqual(result["pages"], PAGES)
        self.assertIsNone(result["selected_page"])

    def test_download_rejects_multiple_pages_before_media_or_file_operations(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "not-created"
            args = SimpleNamespace(target=BVID, page=None, cid=None, mode="video", output_dir=str(output))
            with patch.object(media, "api", return_value=self.metadata()), \
                    patch.object(media, "get_tracks") as tracks, \
                    patch.object(media, "download_track") as download_track:
                with self.assertRaisesRegex(ValueError, "Multiple pages require selection"):
                    media.download(args)
            tracks.assert_not_called()
            download_track.assert_not_called()
            self.assertFalse(output.exists())

    def test_download_cli_returns_selection_request_with_page_choices(self):
        argv = ["bilibili_media.py", "download", BVID, "--mode", "video", "--output-dir", "unused"]
        with patch.object(sys, "argv", argv), \
                patch.object(media, "api", return_value=self.metadata()), \
                patch.object(media, "get_tracks") as tracks, patch.object(media, "emit") as emit:
            media.main()
        tracks.assert_not_called()
        result = emit.call_args.args[0]
        self.assertEqual(result["status"], "needs_selection")
        self.assertEqual(result["pages"], PAGES)

    def test_missing_mode_is_rejected_before_api_call(self):
        with patch.object(sys, "argv", ["bilibili_media.py", "download", BVID, "--output-dir", "unused"]):
            with patch.object(media, "api") as api, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    media.main()
        self.assertEqual(error.exception.code, 2)
        api.assert_not_called()

    def test_explicit_modes_reach_download(self):
        for mode in ("audio", "video"):
            argv = ["bilibili_media.py", "download", BVID, "--mode", mode, "--output-dir", "unused"]
            with self.subTest(mode=mode), patch.object(sys, "argv", argv):
                with patch.object(media, "download") as download:
                    media.main()
                self.assertEqual(download.call_args.args[0].mode, mode)


if __name__ == "__main__":
    unittest.main()
