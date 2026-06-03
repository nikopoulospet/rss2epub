import re
import tempfile
from pathlib import Path

import requests
from ebooklib import epub
from readability import Document

from .config import EPUBConfig
from .freshrss import Article


def build_epub(article: Article, config: EPUBConfig) -> bytes:
    content_html = _extract_content(article)
    if not config.include_images:
        content_html = _strip_images(content_html)

    title = config.page_title_prefix + article.title

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")
    if article.author:
        book.add_author(article.author)
    if article.url:
        book.add_metadata("DC", "source", article.url)

    chapter = epub.EpubHtml(title=title, file_name="article.xhtml", lang="en")
    chapter.content = _xhtml_wrap(title, content_html).encode("utf-8")
    book.add_item(chapter)

    book.toc = (epub.Link("article.xhtml", title, "article"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    return _write_to_bytes(book)


def _extract_content(article: Article) -> str:
    if article.url:
        try:
            resp = requests.get(
                article.url,
                timeout=15,
                headers={"User-Agent": "rss2rm/0.1"},
                allow_redirects=True,
            )
            resp.raise_for_status()
            doc = Document(resp.text)
            extracted = doc.summary(html_partial=True)
            if extracted and len(extracted.strip()) > 100:
                return extracted
        except Exception:
            pass

    if article.content:
        return article.content

    return "<p>No content available.</p>"


def _strip_images(html: str) -> str:
    return re.sub(r"<img[^>]*/?>", "", html, flags=re.IGNORECASE)


def _xhtml_wrap(title: str, body_html: str) -> str:
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>{safe_title}</title></head>"
        f"<body>{body_html}</body>"
        "</html>"
    )


def _write_to_bytes(book: epub.EpubBook) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
        tmp_path = f.name
    try:
        epub.write_epub(tmp_path, book)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
