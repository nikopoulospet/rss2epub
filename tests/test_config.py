import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from rss2rm.config import load_config


class TestLoadConfig(unittest.TestCase):
    def _write_config(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w")
        f.write(textwrap.dedent(content))
        f.close()
        return f.name

    def test_loads_minimal_config(self):
        path = self._write_config("""
            [freshrss]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, {"FRESHRSS_API_PASSWORD": "s3cr3t"}):
            cfg = load_config(path)
        self.assertEqual(cfg.freshrss.url, "https://rss.example.com")
        self.assertEqual(cfg.freshrss.username, "alice")
        self.assertEqual(cfg.freshrss.api_password, "s3cr3t")

    def test_strips_trailing_slash_from_url(self):
        path = self._write_config("""
            [freshrss]
            url = "https://rss.example.com/"
            username = "alice"
        """)
        with patch.dict(os.environ, {"FRESHRSS_API_PASSWORD": "s3cr3t"}):
            cfg = load_config(path)
        self.assertEqual(cfg.freshrss.url, "https://rss.example.com")

    def test_raises_when_api_password_env_missing(self):
        path = self._write_config("""
            [freshrss]
            url = "https://rss.example.com"
            username = "alice"
        """)
        env = {k: v for k, v in os.environ.items() if k != "FRESHRSS_API_PASSWORD"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                load_config(path)

    def test_fetch_defaults(self):
        path = self._write_config("""
            [freshrss]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, {"FRESHRSS_API_PASSWORD": "s3cr3t"}):
            cfg = load_config(path)
        self.assertEqual(cfg.fetch.max_articles, 50)
        self.assertTrue(cfg.fetch.only_unread)
        self.assertFalse(cfg.fetch.mark_read_after_upload)

    def test_fetch_overrides(self):
        path = self._write_config("""
            [freshrss]
            url = "https://rss.example.com"
            username = "alice"

            [fetch]
            max_articles = 10
            mark_read_after_upload = true
        """)
        with patch.dict(os.environ, {"FRESHRSS_API_PASSWORD": "s3cr3t"}):
            cfg = load_config(path)
        self.assertEqual(cfg.fetch.max_articles, 10)
        self.assertTrue(cfg.fetch.mark_read_after_upload)

    def test_raises_on_missing_file(self):
        with patch.dict(os.environ, {"FRESHRSS_API_PASSWORD": "s3cr3t"}):
            with self.assertRaises(FileNotFoundError):
                load_config("/nonexistent/path/config.toml")
