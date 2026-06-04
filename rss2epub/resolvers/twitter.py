import logging

from lxml import etree
from lxml import html as lhtml

from .base import ResolveContext

logger = logging.getLogger(__name__)

_DEFAULT_REPLACEMENT = "A fucking twitter link"


class TwitterLinkResolver:
    """Replace Twitter/X embeds and links with a plain-text placeholder.

    Activated by the presence of a [twitter-link] section in the config:

        [twitter-link]
        replacement = "A fucking twitter link"   # optional; shown above is the default

    Handles:
    - <blockquote class="twitter-tweet"> embedded tweet widgets
    - <script> tags that load twitter's widget JS
    - <a href="https://twitter.com/..."> and <a href="https://x.com/..."> links
    """

    CONFIG_KEY = "twitter-link"

    def __init__(self, config: dict) -> None:
        self.replacement = config.get("replacement", _DEFAULT_REPLACEMENT)

    def resolve(self, html: str, ctx: ResolveContext) -> str:
        if not html:
            return html
        try:
            root = lhtml.fragment_fromstring(html, create_parent="div")
            changed = False

            # Remove twitter widget <script> tags entirely.
            for script in root.findall(".//script"):
                src = script.get("src", "")
                if "twitter.com" in src or "platform.twitter.com" in src:
                    script.getparent().remove(script)
                    changed = True

            # Replace <blockquote class="twitter-tweet"> with placeholder text.
            for bq in root.findall(".//blockquote"):
                if "twitter-tweet" in (bq.get("class") or ""):
                    replacement = lhtml.fragment_fromstring(
                        f"<p>{self.replacement}</p>"
                    )
                    bq.getparent().replace(bq, replacement)
                    changed = True

            # Replace <a href="https://twitter.com/..."> and x.com links.
            for a in root.findall(".//a"):
                href = a.get("href") or ""
                if _is_twitter_url(href):
                    replacement = lhtml.fragment_fromstring(
                        f"<span>{self.replacement}</span>"
                    )
                    a.getparent().replace(a, replacement)
                    changed = True

            if not changed:
                return html

            return (root.text or "") + "".join(
                etree.tostring(child, method="xml", encoding="unicode")
                for child in root
            )
        except Exception as exc:
            logger.debug("TwitterLinkResolver failed on %r, passing through: %s", ctx.title, exc)
            return html


def _is_twitter_url(href: str) -> bool:
    return "twitter.com/" in href or "x.com/" in href
