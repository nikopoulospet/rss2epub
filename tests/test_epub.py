import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from rss2rm.config import EPUBConfig
from rss2rm.epub import build_epub, _strip_images, _xhtml_wrap
from rss2rm.freshrss import Article


def _make_article(**kwargs) -> Article:
    defaults = dict(
        id="tag:google.com,2005:reader/item/0000000000000001",
        title="Test Article",
        url="",
        content="<p>Hello <b>world</b>. This is a test article with enough content to pass.</p>",
        author="Test Author",
        published=1748908800,
        feed_title="Test Feed",
    )
    defaults.update(kwargs)
    return Article(**defaults)


class TestBuildEpub(unittest.TestCase):
    def test_returns_valid_zip(self):
        data = build_epub(_make_article(), EPUBConfig())
        self.assertTrue(data[:2] == b"PK", "EPUB must start with ZIP magic bytes")

    def test_epub_contains_article_xhtml(self):
        data = build_epub(_make_article(), EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        self.assertTrue(any("article.xhtml" in n for n in names), f"article.xhtml missing from {names}")

    def test_epub_content_contains_title(self):
        data = build_epub(_make_article(title="My Special Title"), EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("My Special Title", text)

    def test_epub_content_contains_body_text(self):
        data = build_epub(_make_article(content="<p>Unique body text here.</p>"), EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("Unique body text here", text)

    def test_page_title_prefix(self):
        config = EPUBConfig(page_title_prefix="[RSS] ")
        data = build_epub(_make_article(title="My Article"), config)
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("[RSS] My Article", text)

    def test_include_images_false_strips_img_tags(self):
        article = _make_article(
            url="",
            content='<p>Text</p><img src="http://example.com/img.png" />',
        )
        config = EPUBConfig(include_images=False)
        data = build_epub(article, config)
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertNotIn("<img", text.lower())

    def test_include_images_true_keeps_img_tags(self):
        article = _make_article(
            url="",
            content='<p>Text</p><img src="http://example.com/img.png" />',
        )
        config = EPUBConfig(include_images=True)
        data = build_epub(article, config)
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("img", text.lower())

    def test_falls_back_to_feed_content_when_url_fetch_fails(self):
        article = _make_article(
            url="https://example.invalid/no-such-page",
            content="<p>Fallback content from feed.</p>",
        )
        data = build_epub(article, EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("Fallback content from feed", text)

    def test_no_content_placeholder(self):
        article = _make_article(url="", content="")
        data = build_epub(article, EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("No content available", text)

    @patch("rss2rm.epub.requests.get")
    def test_uses_readability_extracted_content_over_feed(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = (
            "<html><body>"
            + "<p>" + ("Extracted article text. " * 10) + "</p>"
            + "</body></html>"
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        article = _make_article(
            url="https://example.com/article",
            content="<p>Short feed snippet.</p>",
        )
        data = build_epub(article, EPUBConfig())
        zf = zipfile.ZipFile(io.BytesIO(data))
        article_path = next(n for n in zf.namelist() if "article.xhtml" in n)
        text = zf.read(article_path).decode("utf-8")
        self.assertIn("Extracted article text", text)


class TestHelpers(unittest.TestCase):
    def test_strip_images_removes_self_closing(self):
        html = '<p>Text</p><img src="a.png" />'
        self.assertNotIn("<img", _strip_images(html))
        self.assertIn("<p>Text</p>", _strip_images(html))

    def test_strip_images_removes_open_tag(self):
        html = '<p>Text</p><img src="a.png">'
        self.assertNotIn("<img", _strip_images(html))

    def test_xhtml_wrap_escapes_title(self):
        wrapped = _xhtml_wrap("A & <B>", "<p>body</p>")
        self.assertIn("A &amp; &lt;B&gt;", wrapped)
        self.assertNotIn("<B>", wrapped.split("<body>")[0])

    def test_xhtml_wrap_includes_body_content(self):
        wrapped = _xhtml_wrap("Title", "<p>my content</p>")
        self.assertIn("<p>my content</p>", wrapped)
