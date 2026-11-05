"""
Unit tests for safe two-file yt-dlp cookie architecture in LIGHT AI V1.0.
Verifies master-only initialization, preservation of both existing files,
empty/missing master safety, working directory independence, absolute path resolution,
and ensures yt-dlp receives runtime path only (never master).
All tests run in isolated temporary directories with mocked yt-dlp.
No real network requests or live YouTube extractions are performed.
"""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from actions.music_player import (
    MusicPlayer,
    setup_cookies,
    DEFAULT_MASTER_COOKIE_PATH,
    DEFAULT_RUNTIME_COOKIE_PATH,
)


class TestTwoFileCookieArchitecture(unittest.TestCase):
    """Tests the safe two-file cookie management routine in isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.assets_dir = self.base_path / "assets"
        self.master_cookie = self.assets_dir / "cookies.txt"
        self.runtime_cookie = self.base_path / "cookies.txt"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_1_master_only_initialization(self):
        """If master exists and runtime does not, runtime is initialized from master."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.master_cookie.write_text("# Master Cookie Header\n.youtube.com TRUE / FALSE 123456 TEST value\n", encoding="utf-8")

        self.assertFalse(self.runtime_cookie.exists())

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertTrue(self.runtime_cookie.is_file())
        self.assertEqual(resolved, str(self.runtime_cookie.resolve()))
        self.assertEqual(self.runtime_cookie.read_text(encoding="utf-8"), self.master_cookie.read_text(encoding="utf-8"))

    def test_2_both_files_present_preserves_both_without_overwrite(self):
        """If both master and runtime exist, neither is overwritten on startup."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        master_content = "# Master Original\n.youtube.com TRUE / FALSE 111111 TOKEN master\n"
        runtime_content = "# Runtime Existing\n.youtube.com TRUE / FALSE 222222 TOKEN session_updated\n"

        self.master_cookie.write_text(master_content, encoding="utf-8")
        self.runtime_cookie.write_text(runtime_content, encoding="utf-8")

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertEqual(resolved, str(self.runtime_cookie.resolve()))
        # Runtime must preserve its updated content and NOT be replaced by master
        self.assertEqual(self.runtime_cookie.read_text(encoding="utf-8"), runtime_content)
        # Master must remain completely untouched
        self.assertEqual(self.master_cookie.read_text(encoding="utf-8"), master_content)

    def test_3_missing_master_preserves_and_uses_existing_runtime(self):
        """If master is missing but runtime exists with data, runtime is preserved and used."""
        self.assertFalse(self.master_cookie.exists())
        runtime_content = "# Existing Runtime Only\n.youtube.com TRUE / FALSE 333333 TOKEN valid\n"
        self.runtime_cookie.write_text(runtime_content, encoding="utf-8")

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertEqual(resolved, str(self.runtime_cookie.resolve()))
        self.assertEqual(self.runtime_cookie.read_text(encoding="utf-8"), runtime_content)
        # Master should not be created as a fake or empty file
        self.assertFalse(self.master_cookie.exists())

    def test_4_missing_master_and_missing_runtime_returns_none(self):
        """If neither master nor runtime exists, returns None and creates no fake files."""
        self.assertFalse(self.master_cookie.exists())
        self.assertFalse(self.runtime_cookie.exists())

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertIsNone(resolved)
        self.assertFalse(self.master_cookie.exists())
        self.assertFalse(self.runtime_cookie.exists())

    def test_5_empty_master_does_not_overwrite_valid_runtime(self):
        """An empty (0-byte) master file must not overwrite an existing valid runtime file."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.master_cookie.write_text("", encoding="utf-8")  # 0 bytes
        runtime_content = "# Valid Runtime Cookie\n.youtube.com TRUE / FALSE 444444 TOKEN valid\n"
        self.runtime_cookie.write_text(runtime_content, encoding="utf-8")

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertEqual(resolved, str(self.runtime_cookie.resolve()))
        self.assertEqual(self.runtime_cookie.read_text(encoding="utf-8"), runtime_content)

    def test_6_empty_master_and_missing_runtime_returns_none(self):
        """If master is 0 bytes and runtime is missing, returns None without copying empty file."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.master_cookie.write_text("", encoding="utf-8")

        resolved = setup_cookies(self.master_cookie, self.runtime_cookie)

        self.assertIsNone(resolved)
        self.assertFalse(self.runtime_cookie.exists())

    def test_7_path_resolution_independent_of_working_directory(self):
        """Default paths are always absolute and independent of os.getcwd()."""
        original_cwd = os.getcwd()
        try:
            # Change CWD to an arbitrary temporary directory
            os.chdir(self.temp_dir.name)
            self.assertTrue(DEFAULT_MASTER_COOKIE_PATH.is_absolute())
            self.assertTrue(DEFAULT_RUNTIME_COOKIE_PATH.is_absolute())
            self.assertTrue(str(DEFAULT_MASTER_COOKIE_PATH).endswith(os.path.join("assets", "cookies.txt")))
            self.assertTrue(str(DEFAULT_RUNTIME_COOKIE_PATH).endswith("cookies.txt"))
        finally:
            os.chdir(original_cwd)

    def test_8_ytdl_receives_runtime_path_only_never_master(self):
        """MusicPlayer passes the runtime cookie path to yt-dlp, never the master path."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.master_cookie.write_text("# Master\n", encoding="utf-8")
        self.runtime_cookie.write_text("# Runtime\n", encoding="utf-8")

        mock_ytdl_instance = MagicMock()
        mock_ytdl_instance.__enter__.return_value = mock_ytdl_instance
        mock_ytdl_instance.extract_info.return_value = {
            "url": "https://googlevideo.com/stream",
            "title": "Mock Audio",
        }
        mock_ytdl_class = MagicMock(return_value=mock_ytdl_instance)

        player = MusicPlayer(
            ytdl_class=mock_ytdl_class,
            master_cookie_path=self.master_cookie,
            runtime_cookie_path=self.runtime_cookie,
        )

        stream_url, title = player._extract_stream_url("test song")
        self.assertEqual(stream_url, "https://googlevideo.com/stream")

        # Inspect ydl_opts passed to yt-dlp
        call_args, call_kwargs = mock_ytdl_class.call_args
        ydl_opts = call_args[0]

        self.assertIn("cookiefile", ydl_opts)
        self.assertEqual(ydl_opts["cookiefile"], str(self.runtime_cookie.resolve()))
        self.assertNotEqual(ydl_opts["cookiefile"], str(self.master_cookie.resolve()))

    def test_9_ytdl_does_not_set_cookiefile_if_no_cookies_available(self):
        """If neither master nor runtime cookies exist, yt-dlp proceeds without cookiefile option."""
        mock_ytdl_instance = MagicMock()
        mock_ytdl_instance.__enter__.return_value = mock_ytdl_instance
        mock_ytdl_instance.extract_info.return_value = {
            "url": "https://googlevideo.com/stream",
            "title": "Mock Audio",
        }
        mock_ytdl_class = MagicMock(return_value=mock_ytdl_instance)

        player = MusicPlayer(
            ytdl_class=mock_ytdl_class,
            master_cookie_path=self.master_cookie,
            runtime_cookie_path=self.runtime_cookie,
        )

        stream_url, title = player._extract_stream_url("test song")
        self.assertEqual(stream_url, "https://googlevideo.com/stream")

        call_args, _ = mock_ytdl_class.call_args
        ydl_opts = call_args[0]
        self.assertNotIn("cookiefile", ydl_opts)

    def test_10_master_file_never_modified_by_application_code(self):
        """Master file content and size remain strictly unchanged across multiple runs."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        original_master_content = "# Immutable Master Cookies\n.youtube.com TRUE / FALSE 99999999 TOKEN secret\n"
        self.master_cookie.write_text(original_master_content, encoding="utf-8")
        initial_size = self.master_cookie.stat().st_size

        mock_ytdl_instance = MagicMock()
        mock_ytdl_instance.__enter__.return_value = mock_ytdl_instance
        mock_ytdl_instance.extract_info.return_value = {"url": "http://stream", "title": "Track"}
        mock_ytdl_class = MagicMock(return_value=mock_ytdl_instance)

        # Run setup multiple times
        setup_cookies(self.master_cookie, self.runtime_cookie)
        player = MusicPlayer(
            ytdl_class=mock_ytdl_class,
            master_cookie_path=self.master_cookie,
            runtime_cookie_path=self.runtime_cookie,
        )
        player._extract_stream_url("any song")
        setup_cookies(self.master_cookie, self.runtime_cookie)

        # Confirm master was never altered
        self.assertEqual(self.master_cookie.read_text(encoding="utf-8"), original_master_content)
        self.assertEqual(self.master_cookie.stat().st_size, initial_size)


if __name__ == "__main__":
    unittest.main()
