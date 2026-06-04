import hashlib
import html as _html
import re
import tempfile
from pathlib import Path

from ebooklib import epub
from lxml import etree
from lxml import html as lhtml


def tidy_to_xhtml(html: str) -> str:
    """Normalize feed HTML to a valid XHTML fragment for EPUB body content.

    The aggregator owns content quality.  This function does the minimum needed
    for EPUB validity: close unclosed tags, escape stray entities, produce
    well-formed XML.  Falls back to escaped plain text on parse failure.
    """
    if not html:
        return ""
    try:
        doc = lhtml.document_fromstring(f"<html><body>{html}</body></html>")
        body = doc.find(".//body")
        if body is not None:
            children = list(body)
            if children:
                # Normal case: body has element children.
                return (body.text or "") + "".join(
                    etree.tostring(child, method="xml", encoding="unicode")
                    for child in children
                )
            if body.text and body.text.strip():
                # Plain-text content with no wrapping elements (e.g. feed
                # excerpts that are raw text).  ebooklib's nav generator counts
                # child *elements*, not text nodes — a text-only body returns
                # len(body) == 0 and is treated as empty.  Wrap it.
                return f"<p>{_html.escape(body.text)}</p>"
    except Exception:
        pass
    return f"<p>{_html.escape(html)}</p>"


def stable_name(item_id: str, title: str) -> str:
    """Return a deterministic EPUB filename stable even when the title changes.

    Uniqueness comes from the id hash; the title slug is for human readability only.
    """
    slug = re.sub(r"[^\w\s-]", "", title)
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")[:60]
    id_hash = hashlib.md5(item_id.encode()).hexdigest()[:8]
    return f"{slug}-{id_hash}.epub"


def build_epub(
    title: str,
    xhtml_body: str,
    *,
    author: str = "",
    source_url: str = "",
    stylesheet: str = "",
) -> bytes:
    """Build a single-article EPUB container and return its raw bytes.

    xhtml_body should be a tidy XHTML fragment (from tidy_to_xhtml).
    stylesheet is optional CSS content (not a file path).
    """
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")
    if author:
        book.add_author(author)
    if source_url:
        book.add_metadata("DC", "source", source_url)

    css_href = ""
    if stylesheet:
        css_item = epub.EpubItem(
            uid="style",
            file_name="style/article.css",
            media_type="text/css",
            content=stylesheet.encode("utf-8"),
        )
        book.add_item(css_item)
        css_href = "style/article.css"

    chapter = epub.EpubHtml(title=title, file_name="article.xhtml", lang="en")
    # ebooklib's nav generator fails on a truly empty body — use a minimal placeholder.
    body = xhtml_body if xhtml_body.strip() else "<p/>"
    chapter.content = _xhtml_wrap(title, body, css_href=css_href).encode("utf-8")
    book.add_item(chapter)

    book.toc = (epub.Link("article.xhtml", title, "article"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    return _write_to_bytes(book)


def _xhtml_wrap(title: str, body_html: str, *, css_href: str = "") -> str:
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    style_link = (
        f'<link rel="stylesheet" type="text/css" href="{css_href}"/>'
        if css_href else ""
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>{safe_title}</title>{style_link}</head>"
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
