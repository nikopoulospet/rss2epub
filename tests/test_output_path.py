"""Tests for output_path.py and the configured-output-path pipeline.

All tests run without any network access or RSS aggregator interaction.
"""
import dataclasses
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rss2epub.config import Config, EPUBConfig, FetchConfig, OutputConfig, ServerConfig
from rss2epub.greader import Article
from rss2epub.output_path import (
    DEFAULT_FORMAT,
    _id_hash,
    _TEMPLATE_FIELDS,
    check_confined,
    resolve_output_path,
    validate_template,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _article(**kwargs) -> Article:
    defaults = dict(
        id="tag:google.com,2005:reader/item/0001",
        article_name="Test Article",
        url="https://example.com/article",
        content="<p>Content.</p>",
        author="Jane Doe",
        publish_date=1748995200,  # 2025-06-04 UTC
        feed_name="My Feed",
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _make_config(tmp_dir: str, fmt: str) -> Config:
    db_path = str(Path(tmp_dir) / "catalog.db")
    return Config(
        server=ServerConfig(url="https://example.com", username="u", password="p"),
        fetch=FetchConfig(lookback="30d"),
        epub=EPUBConfig(),
        output=OutputConfig(dir=tmp_dir, db=db_path, format=fmt),
        resolver_config={},
    )


# ── unit tests: validate_template ────────────────────────────────────────────

class TestValidateTemplate(unittest.TestCase):
    def test_known_fields_accepted(self):
        validate_template("{publish_date}/{article_name}")  # no exception

    def test_all_known_fields_accepted(self):
        template = "{publish_date}/{feed_name}/{author}/{article_name}"
        validate_template(template)  # no exception

    def test_unknown_field_raises(self):
        # Acceptance criterion #3
        with self.assertRaises(ValueError) as ctx:
            validate_template("{authr}/{article_name}")
        self.assertIn("authr", str(ctx.exception))

    def test_unknown_field_error_lists_valid_fields(self):
        with self.assertRaises(ValueError) as ctx:
            validate_template("{bad_field}")
        msg = str(ctx.exception)
        for field in _TEMPLATE_FIELDS:
            self.assertIn(field, msg)

    def test_absolute_path_rejected(self):
        # Acceptance criterion #13
        with self.assertRaises(ValueError):
            validate_template("/absolute/{article_name}")

    def test_dotdot_segment_rejected(self):
        # Acceptance criterion #13
        with self.assertRaises(ValueError):
            validate_template("../../{article_name}")

    def test_single_dotdot_segment_rejected(self):
        with self.assertRaises(ValueError):
            validate_template("{feed_name}/../{article_name}")

    def test_literal_text_with_no_fields_accepted(self):
        validate_template("static/subdir")  # no exception

    def test_empty_template_accepted(self):
        validate_template("")  # no exception; degenerate but structurally valid


# ── unit tests: resolve_output_path ──────────────────────────────────────────

class TestResolveOutputPath(unittest.TestCase):
    def test_basic_template_resolution(self):
        # Acceptance criterion #1
        art = _article(article_name="The Weekly Roundup", publish_date=1748995200)
        result = resolve_output_path("{publish_date}_{article_name}", art)
        self.assertTrue(result.startswith("2025-06-04_the-weekly-roundup-"))

    def test_subdirectory_template(self):
        # Acceptance criterion #2
        art = _article(article_name="The Weekly Roundup", feed_name="News Feed")
        result = resolve_output_path("{feed_name}/{publish_date}_{article_name}", art)
        parts = result.split("/")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "news-feed")
        self.assertIn("the-weekly-roundup", parts[1])

    def test_default_format_produces_date_subdirectory(self):
        # Acceptance criterion #4
        art = _article(publish_date=1748995200)
        result = resolve_output_path(DEFAULT_FORMAT, art)
        self.assertTrue(result.startswith("2025-06-04/"))

    def test_slash_in_title_becomes_single_component(self):
        # Acceptance criterion #5 — embedded slash must NOT create a subdirectory
        art = _article(article_name="Foo / Bar: Baz?")
        result = resolve_output_path("{article_name}", art)
        # Only one slash is allowed — the one between dirs (this template has none)
        self.assertNotIn("/", result)
        self.assertIn("foo", result)
        self.assertIn("bar", result)

    def test_slash_in_title_via_subdir_template(self):
        # Slash inside title must not create an extra subdirectory
        art = _article(article_name="Foo / Bar", feed_name="Feed")
        result = resolve_output_path("{feed_name}/{article_name}", art)
        parts = result.split("/")
        self.assertEqual(len(parts), 2, f"Expected 2 segments, got: {parts}")

    def test_distinct_articles_same_title_produce_distinct_paths(self):
        # Acceptance criterion #6
        art1 = _article(id="item-001", article_name="Same Title", publish_date=1748995200)
        art2 = _article(id="item-002", article_name="Same Title", publish_date=1748995200)
        path1 = resolve_output_path(DEFAULT_FORMAT, art1)
        path2 = resolve_output_path(DEFAULT_FORMAT, art2)
        self.assertNotEqual(path1, path2)

    def test_path_traversal_title_becomes_safe_component(self):
        # Acceptance criterion #7 — "../../etc/passwd" must slugify to a safe segment
        art = _article(article_name="../../etc/passwd")
        result = resolve_output_path("{article_name}", art)
        self.assertNotIn("..", result)
        self.assertNotIn("/etc/", result)

    def test_missing_author_segment_collapses(self):
        # Acceptance criterion #8 — empty author must not emit a blank segment or "None"
        art = _article(author="")
        result = resolve_output_path("{feed_name}/{author}/{article_name}", art)
        self.assertNotIn("None", result)
        # The author segment collapses so only two path components remain
        parts = result.split("/")
        self.assertEqual(len(parts), 2)

    def test_degenerate_template_falls_back_to_hash(self):
        # Acceptance criterion #9 — even a bare empty template writes to a retrievable path
        art = _article(article_name="", author="", feed_name="")
        result = resolve_output_path("{article_name}", art)
        self.assertTrue(len(result) > 0)
        # Should be exactly the hash (no other segments, since slug is empty)
        expected_hash = _id_hash(art.id)
        self.assertEqual(result, expected_hash)

    def test_id_hash_always_appended(self):
        # Invariant: every resolved path ends with the item_id hash
        art = _article()
        expected_hash = _id_hash(art.id)
        for template in [
            "{article_name}",
            "{publish_date}/{article_name}",
            "{feed_name}/{author}/{article_name}",
        ]:
            result = resolve_output_path(template, art)
            last_segment = result.split("/")[-1]
            self.assertTrue(
                last_segment.endswith(expected_hash),
                f"Template {template!r} → {result!r} does not end with hash",
            )

    def test_same_article_same_id_produces_stable_path(self):
        # Same article always resolves to the same path (deterministic)
        art = _article()
        path1 = resolve_output_path(DEFAULT_FORMAT, art)
        path2 = resolve_output_path(DEFAULT_FORMAT, art)
        self.assertEqual(path1, path2)

    def test_publish_date_formatted_as_iso_date(self):
        # 2025-06-04 00:00:00 UTC = 1748995200
        art = _article(publish_date=1748995200)
        result = resolve_output_path("{publish_date}", art)
        self.assertTrue(result.startswith("2025-06-04"))

    def test_no_none_string_in_output(self):
        # "None" must never appear in any resolved path
        art = _article(author="", feed_name="")
        for template in ["{author}", "{feed_name}/{article_name}"]:
            result = resolve_output_path(template, art)
            self.assertNotIn("None", result)


# ── unit tests: check_confined ────────────────────────────────────────────────

class TestCheckConfined(unittest.TestCase):
    def test_normal_path_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_confined(Path(tmp), "2025-06-04/article-abc123.epub")
            self.assertTrue(str(result).startswith(tmp))

    def test_path_traversal_rejected(self):
        # Acceptance criterion #7 (belt-and-suspenders confinement)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                check_confined(Path(tmp), "../../etc/passwd")

    def test_absolute_path_component_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                check_confined(Path(tmp), "/etc/passwd")

    def test_returned_path_is_absolute(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_confined(Path(tmp), "subdir/file.epub")
            self.assertTrue(result.is_absolute())


# ── meta test: valid fields derived from Article ─────────────────────────────

class TestValidFieldsFromArticle(unittest.TestCase):
    def test_valid_fields_match_article_template_metadata(self):
        # No hardcoded list — fields come from Article.metadata["template"]
        from rss2epub.greader import Article as A
        expected = frozenset(
            f.name for f in dataclasses.fields(A)
            if f.metadata.get("template")
        )
        self.assertEqual(_TEMPLATE_FIELDS, expected)

    def test_internal_fields_not_in_template_fields(self):
        self.assertNotIn("id", _TEMPLATE_FIELDS)
        self.assertNotIn("url", _TEMPLATE_FIELDS)
        self.assertNotIn("content", _TEMPLATE_FIELDS)

    def test_template_field_names_accepted_by_validate_template(self):
        template = "/".join(f"{{{name}}}" for name in sorted(_TEMPLATE_FIELDS))
        validate_template(template)  # must not raise

    def test_adding_unknown_field_to_template_raises(self):
        # Any name not in Article.metadata["template"] must be rejected
        with self.assertRaises(ValueError):
            validate_template("{totally_unknown_field}")


# ── integration tests: run() via mocked GReader ───────────────────────────────

class TestRunIntegration(unittest.TestCase):
    """End-to-end tests for __main__.run() with mocked GReader.

    These tests verify overwrite/move correctness without any network calls.
    """

    def _run(self, config, articles):
        from rss2epub.__main__ import run
        with patch("rss2epub.__main__.GReaderClient") as MockClient:
            instance = MockClient.return_value
            instance.authenticate.return_value = None
            instance.get_articles_since.return_value = (articles, [])
            return run(config, dry_run=False)

    def test_content_change_overwrites_same_path(self):
        # Acceptance criterion #10
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, DEFAULT_FORMAT)
            art = _article(content="<p>Version 1.</p>")

            self._run(config, [art])
            files_after_first = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(files_after_first), 1)
            original_path = files_after_first[0]
            original_mtime = original_path.stat().st_mtime
            original_size = original_path.stat().st_size

            art_v2 = _article(content="<p>Version 2 — substantially different content here.</p>")
            self._run(config, [art_v2])

            files_after_second = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(files_after_second), 1, "Exactly one file must exist after re-render")
            self.assertEqual(files_after_second[0], original_path, "File path must be stable")
            # The file was overwritten (size or mtime changed)
            new_size = files_after_second[0].stat().st_size
            new_mtime = files_after_second[0].stat().st_mtime
            self.assertTrue(
                new_mtime > original_mtime or new_size != original_size,
                "File should have been overwritten",
            )

    def test_template_change_moves_file(self):
        # Acceptance criterion #11
        with tempfile.TemporaryDirectory() as tmp:
            art = _article()

            # First run: flat template
            config1 = _make_config(tmp, "{article_name}")
            self._run(config1, [art])
            files_v1 = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(files_v1), 1)
            old_path = files_v1[0]

            # Second run: subdirectory template (content unchanged → UNCHANGED state → move)
            config2 = _make_config(tmp, "{publish_date}/{article_name}")
            self._run(config2, [art])

            all_files = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(all_files), 1, "Exactly one file must exist after template change")
            new_path = all_files[0]
            self.assertFalse(old_path.exists(), "Old path must be gone after move")
            self.assertTrue(new_path.exists(), "New path must exist")
            self.assertNotEqual(old_path, new_path, "File must have moved to a new path")

            # Catalog must reflect the new path
            from rss2epub.catalog import Catalog
            cat = Catalog(str(Path(tmp) / "catalog.db"))
            row = cat.lookup(art.id)
            cat.close()
            self.assertIsNotNone(row)
            self.assertIn(str(Path(new_path).relative_to(tmp)), row.filename)

    def test_title_change_moves_file(self):
        # Acceptance criterion #12 — upstream title change → exactly one file, old path gone
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "{article_name}")
            art_v1 = _article(article_name="Old Title", content="<p>Body.</p>")
            self._run(config, [art_v1])
            files_v1 = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(files_v1), 1)
            old_path = files_v1[0]

            # Same item_id, different title and content (title change is upstream edit)
            art_v2 = _article(article_name="New Title", content="<p>Body — updated.</p>")
            self._run(config, [art_v2])

            all_files = list(Path(tmp).rglob("*.epub"))
            self.assertEqual(len(all_files), 1, "Exactly one file must exist after title change")
            self.assertFalse(old_path.exists(), "Old path must be gone")
            self.assertIn("new-title", str(all_files[0]))

    def test_bad_template_fails_at_config_load(self):
        # Acceptance criterion #13 — unknown field raises at load_config, before any fetch
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                _make_config(tmp, "{authr}/{article_name}")
            self.assertIn("authr", str(ctx.exception))

    def test_absolute_template_fails_at_config_load(self):
        # Acceptance criterion #13 — absolute path rejected at config-load
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                _make_config(tmp, "/absolute/{article_name}")

    def test_new_article_creates_subdirectory(self):
        # Subdirectory implied by template must be created automatically
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "{publish_date}/{article_name}")
            art = _article(publish_date=1748995200)  # 2025-06-04
            self._run(config, [art])
            date_dir = Path(tmp) / "2025-06-04"
            self.assertTrue(date_dir.is_dir())
            self.assertEqual(len(list(date_dir.glob("*.epub"))), 1)

    def test_unchanged_article_skipped(self):
        # UNCHANGED articles are counted as skipped (not re-rendered)
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, DEFAULT_FORMAT)
            art = _article()
            stats1 = self._run(config, [art])
            self.assertEqual(stats1.new, 1)
            stats2 = self._run(config, [art])
            self.assertEqual(stats2.skipped, 1)
            self.assertEqual(stats2.new, 0)
            self.assertEqual(stats2.changed, 0)
