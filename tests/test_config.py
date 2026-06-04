import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from rss2epub.config import load_config, parse_lookback


class TestParseLookback(unittest.TestCase):
    def test_days(self):
        self.assertEqual(parse_lookback("30d"), 30 * 86400)

    def test_hours(self):
        self.assertEqual(parse_lookback("72h"), 72 * 3600)

    def test_weeks(self):
        self.assertEqual(parse_lookback("6w"), 6 * 7 * 86400)

    def test_whitespace_stripped(self):
        self.assertEqual(parse_lookback("  7d  "), 7 * 86400)

    def test_raises_on_unknown_unit(self):
        with self.assertRaises(ValueError):
            parse_lookback("30m")

    def test_raises_on_zero(self):
        with self.assertRaises(ValueError):
            parse_lookback("0d")

    def test_raises_on_missing_unit(self):
        with self.assertRaises(ValueError):
            parse_lookback("30")

    def test_raises_on_empty(self):
        with self.assertRaises(ValueError):
            parse_lookback("")


class TestLoadConfig(unittest.TestCase):
    ENV = {"RSS2EPUB_API_PASSWORD": "s3cr3t"}

    def _write_config(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w")
        f.write(textwrap.dedent(content))
        f.close()
        return f.name

    def test_loads_minimal_config(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.server.url, "https://rss.example.com")
        self.assertEqual(cfg.server.username, "alice")
        self.assertEqual(cfg.server.password, "s3cr3t")

    def test_strips_trailing_slash_from_url(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com/"
            username = "alice"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.server.url, "https://rss.example.com")

    def test_raises_when_password_env_missing(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"
        """)
        env = {k: v for k, v in os.environ.items() if k != "RSS2EPUB_API_PASSWORD"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                load_config(path)

    def test_fetch_defaults(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.fetch.lookback, "30d")

    def test_fetch_lookback_override(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"

            [fetch]
            lookback = "7d"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.fetch.lookback, "7d")

    def test_epub_stylesheet_default_is_empty(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.epub.stylesheet, "")

    def test_epub_stylesheet_override(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"

            [epub]
            stylesheet = "~/my.css"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertEqual(cfg.epub.stylesheet, "~/my.css")

    def test_output_defaults(self):
        path = self._write_config("""
            [server]
            url = "https://rss.example.com"
            username = "alice"
        """)
        with patch.dict(os.environ, self.ENV):
            cfg = load_config(path)
        self.assertIn("rss2epub", cfg.output.dir)
        self.assertIn("catalog.db", cfg.output.db)

    def test_raises_on_missing_file(self):
        with patch.dict(os.environ, self.ENV):
            with self.assertRaises(FileNotFoundError):
                load_config("/nonexistent/path/config.toml")
