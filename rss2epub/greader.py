import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class Article:
    id: str
    title: str
    url: str
    content: str
    author: str
    published: int
    feed_title: str


class GReaderClient:
    """Generic GReader API client.

    `base_url` must be the full API root *including any path prefix* the
    backend requires, so that endpoint suffixes appended here work unchanged:

        FreshRSS:  base_url = "https://rss.example.com/api/greader.php"
        Miniflux:  base_url = "https://miniflux.example.com"

    The `/api/greader.php` prefix is FreshRSS's convention, not part of the
    GReader spec — keeping it out of this file means any conforming backend
    works without code changes.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self._password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "rss2epub/0.1"

    def authenticate(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/accounts/ClientLogin",
            data={
                "Email": self.username,
                "Passwd": self._password,
                "service": "reader",
                "accountType": "HOSTED_OR_GOOGLE",
                "source": "rss2epub",
            },
        )
        resp.raise_for_status()

        token = None
        for line in resp.text.splitlines():
            if line.startswith("Auth="):
                token = line[5:]
                break
        if not token:
            raise RuntimeError(
                f"ClientLogin response missing Auth token:\n{resp.text[:200]}"
            )

        self.session.headers["Authorization"] = f"GoogleLogin auth={token}"
        logger.debug("Auth token obtained")

    def get_articles_since(self, cutoff: int) -> tuple[list[Article], list[str]]:
        """Fetch all items with published >= cutoff, paginating as needed.

        Returns (articles, diagnostic_lines).  Uses `ot` as a server-side lower
        bound; items are also filtered client-side since feed timestamps vary
        across backends.
        """
        articles: list[Article] = []
        diag: list[str] = []
        continuation: str | None = None
        stream_url = (
            f"{self.base_url}/reader/api/0/stream/contents/"
            "user/-/state/com.google/reading-list"
        )

        for page in range(10):  # safety cap: 10 × 100 = 1 000 items
            params: dict = {"n": 100, "ot": cutoff, "r": "d", "output": "json"}
            if continuation:
                params["c"] = continuation

            diag.append(f"GET {stream_url} params={params}")
            resp = self.session.get(stream_url, params=params)
            diag.append(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()

            raw = data.get("items", [])
            diag.append(f"page {page + 1}: {len(raw)} items")

            kept = dropped = 0
            for item in raw:
                if item.get("published", 0) < cutoff:
                    dropped += 1
                    continue
                articles.append(_parse_item(item))
                kept += 1

            if dropped:
                diag.append(f"  dropped {dropped} items with published < cutoff")

            continuation = data.get("continuation")
            if not continuation:
                break

        return articles, diag


def _parse_item(item: dict) -> Article:
    url = _first_href(item.get("canonical")) or _first_href(item.get("alternate")) or ""
    return Article(
        id=item["id"],
        title=item.get("title", "Untitled"),
        url=url,
        content=_item_content(item),
        author=item.get("author", ""),
        published=item.get("published", 0),
        feed_title=item.get("origin", {}).get("title", ""),
    )


def _first_href(links: list | None) -> str | None:
    if links:
        return links[0].get("href")
    return None


def _item_content(item: dict) -> str:
    # GReader spec: `content` = article body, `summary` = excerpt.
    # Prefer `content`; fall back to `summary` if absent or empty.
    # "Take the longer one" was a patch for an observed FreshRSS failure and is
    # not a correct general rule — it breaks if a backend populates both fields
    # with meaningful full-length content for different purposes.
    for key in ("content", "summary"):
        if block := item.get(key):
            if text := block.get("content", ""):
                return text
    return ""
