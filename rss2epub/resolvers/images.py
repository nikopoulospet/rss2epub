import base64
import logging
import mimetypes
from urllib.parse import urljoin, urlparse

import requests

from .base import ResolveContext

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


class ImageInlinerResolver:
    """Fetch remote images and embed them as base64 data URIs.

    Converts <img src="https://..."> to <img src="data:image/...;base64,...">
    so the EPUB is self-contained and renders offline on the e-reader.

    Activated by the presence of an [image-inline] section in the config:

        [image-inline]
        timeout   = 10       # per-image request timeout in seconds (default: 10)
        max_bytes = 5242880  # skip images larger than this (default: 5 MB)

    Images that fail to fetch are left with their original src — the article
    still renders, just without that image.  Oversized images are skipped
    silently for the same reason.
    """

    CONFIG_KEY = "image-inline"

    def __init__(self, config: dict) -> None:
        self.timeout = int(config.get("timeout", _DEFAULT_TIMEOUT))
        self.max_bytes = int(config.get("max_bytes", _DEFAULT_MAX_BYTES))

    def resolve(self, html: str, ctx: ResolveContext) -> str:
        if not html:
            return html
        try:
            from lxml import etree
            from lxml import html as lhtml

            root = lhtml.fragment_fromstring(html, create_parent="div")
            modified = False

            for img in root.findall(".//img"):
                src = (img.get("src") or "").strip()
                if not src or src.startswith("data:"):
                    continue

                # Resolve relative URLs against the article's canonical URL.
                if not src.startswith(("http://", "https://")):
                    if not ctx.article_url:
                        continue
                    src = urljoin(ctx.article_url, src)

                data_uri = _fetch_as_data_uri(src, self.timeout, self.max_bytes)
                if data_uri:
                    img.set("src", data_uri)
                    modified = True
                    logger.debug("Inlined image: %s", src)
                else:
                    logger.debug("Could not inline image (kept remote src): %s", src)

            if not modified:
                return html

            return (root.text or "") + "".join(
                etree.tostring(child, method="xml", encoding="unicode")
                for child in root
            )
        except Exception as exc:
            logger.debug(
                "ImageInlinerResolver failed on %r, passing through: %s",
                ctx.title,
                exc,
            )
            return html


def _fetch_as_data_uri(url: str, timeout: int, max_bytes: int) -> str | None:
    """Download url and return a data URI string, or None on any failure."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "rss2epub/0.1"},
            stream=True,
        )
        resp.raise_for_status()

        # Honour Content-Length if the server sends it.
        declared = int(resp.headers.get("Content-Length", 0))
        if declared and declared > max_bytes:
            logger.debug("Skipping image %s: declared size %d > max %d", url, declared, max_bytes)
            return None

        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65_536):
            total += len(chunk)
            if total > max_bytes:
                logger.debug("Skipping image %s: download exceeded %d bytes", url, max_bytes)
                return None
            chunks.append(chunk)

        image_bytes = b"".join(chunks)
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if not content_type.startswith("image/"):
            content_type = _mime_from_url(url)

        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{content_type};base64,{b64}"

    except Exception as exc:
        logger.debug("Failed to fetch image %s: %s", url, exc)
        return None


def _mime_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    mime, _ = mimetypes.guess_type(path)
    return mime if mime and mime.startswith("image/") else "image/jpeg"
