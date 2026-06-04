import io
import unittest
import zipfile

from rss2epub.epub import build_epub, stable_name, tidy_to_xhtml


class TestTidyToXhtml(unittest.TestCase):
    def test_empty_string_returns_empty(self):
        self.assertEqual(tidy_to_xhtml(""), "")

    def test_valid_html_preserved(self):
        result = tidy_to_xhtml("<p>Hello <b>world</b></p>")
        self.assertIn("Hello", result)
        self.assertIn("<b>", result)

    def test_unclosed_tags_are_closed(self):
        result = tidy_to_xhtml("<p>text")
        self.assertIn("</p>", result)

    def test_ampersand_in_text_escaped(self):
        result = tidy_to_xhtml("<p>A & B</p>")
        # Must be valid XML (& not bare)
        self.assertNotIn(" & ", result)

    def test_multiple_paragraphs_preserved(self):
        result = tidy_to_xhtml("<p>First</p><p>Second</p>")
        self.assertIn("First", result)
        self.assertIn("Second", result)

    def test_plain_text_wrapped_in_paragraph(self):
        # Raw text with no HTML tags must produce an element node, not a bare
        # text node — ebooklib counts child elements (not text nodes) to decide
        # if the body is empty.
        result = tidy_to_xhtml("Plain text excerpt with no tags.")
        self.assertIn("<p>", result)
        self.assertIn("Plain text excerpt", result)

    def test_parse_failure_returns_escaped_fallback(self):
        # A string that can't parse as HTML still returns something
        result = tidy_to_xhtml("plain text with no tags")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_returns_string_not_bytes(self):
        self.assertIsInstance(tidy_to_xhtml("<p>hi</p>"), str)


class TestStableName(unittest.TestCase):
    ITEM_ID = "tag:google.com,2005:reader/item/0000000000000001"

    def test_ends_with_epub(self):
        self.assertTrue(stable_name(self.ITEM_ID, "Title").endswith(".epub"))

    def test_title_slug_present(self):
        self.assertIn("Hello-World", stable_name(self.ITEM_ID, "Hello World"))

    def test_same_id_same_filename(self):
        a = stable_name(self.ITEM_ID, "Title")
        b = stable_name(self.ITEM_ID, "Title")
        self.assertEqual(a, b)

    def test_different_ids_different_filenames(self):
        id2 = "tag:google.com,2005:reader/item/0000000000000002"
        self.assertNotEqual(
            stable_name(self.ITEM_ID, "Title"),
            stable_name(id2, "Title"),
        )

    def test_title_change_doesnt_change_hash_suffix(self):
        # Hash part (last 8 chars before .epub) is derived from id, not title
        name_a = stable_name(self.ITEM_ID, "Original Title")
        name_b = stable_name(self.ITEM_ID, "Edited Title")
        hash_a = name_a.rsplit("-", 1)[-1]
        hash_b = name_b.rsplit("-", 1)[-1]
        self.assertEqual(hash_a, hash_b)

    def test_special_chars_stripped_from_slug(self):
        name = stable_name(self.ITEM_ID, "Hello: World! (Test)")
        slug = name.rsplit("-", 1)[0]
        self.assertRegex(slug, r"^[\w-]+$")


class TestBuildEpub(unittest.TestCase):
    def _build(self, title="Test Article", body="<p>Body text here.</p>", **kwargs) -> bytes:
        return build_epub(title, tidy_to_xhtml(body), **kwargs)

    def test_returns_bytes(self):
        self.assertIsInstance(self._build(), bytes)

    def test_returns_valid_zip(self):
        self.assertEqual(self._build()[:2], b"PK")

    def test_contains_article_xhtml(self):
        names = zipfile.ZipFile(io.BytesIO(self._build())).namelist()
        self.assertTrue(any("article.xhtml" in n for n in names))

    def test_title_in_xhtml(self):
        data = self._build(title="My Unique Title")
        zf = zipfile.ZipFile(io.BytesIO(data))
        path = next(n for n in zf.namelist() if "article.xhtml" in n)
        self.assertIn("My Unique Title", zf.read(path).decode())

    def test_body_text_in_xhtml(self):
        data = self._build(body="<p>Distinctive body phrase here.</p>")
        zf = zipfile.ZipFile(io.BytesIO(data))
        path = next(n for n in zf.namelist() if "article.xhtml" in n)
        self.assertIn("Distinctive body phrase here", zf.read(path).decode())

    def test_empty_body_does_not_raise(self):
        data = build_epub("Title", "")
        self.assertEqual(data[:2], b"PK")

    def test_stylesheet_embedded_when_provided(self):
        css = "body { font-family: serif; }"
        data = self._build(stylesheet=css)
        zf = zipfile.ZipFile(io.BytesIO(data))
        css_files = [n for n in zf.namelist() if n.endswith(".css")]
        self.assertTrue(css_files, "No CSS file in EPUB")
        self.assertIn(b"font-family", zf.read(css_files[0]))

    def test_no_stylesheet_by_default(self):
        data = self._build()
        zf = zipfile.ZipFile(io.BytesIO(data))
        self.assertFalse(any(n.endswith(".css") for n in zf.namelist()))
