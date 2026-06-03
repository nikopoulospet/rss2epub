from dataclasses import dataclass

import requests


@dataclass
class Article:
    id: str
    title: str
    url: str
    content: str
    author: str
    published: int
    feed_title: str


class FreshRSSClient:
    def __init__(self, base_url: str, username: str, api_password: str) -> None:
        self.base_url = base_url
        self.username = username
        self.api_password = api_password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "rss2rm/0.1"

    def authenticate(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/greader.php/accounts/ClientLogin",
            data={
                "Email": self.username,
                "Passwd": self.api_password,
                "service": "reader",
                "accountType": "HOSTED_OR_GOOGLE",
                "source": "rss2rm",
            },
        )
        resp.raise_for_status()

        token = None
        for line in resp.text.splitlines():
            if line.startswith("Auth="):
                token = line[5:]
                break
        if not token:
            raise RuntimeError(f"ClientLogin response missing Auth token:\n{resp.text[:200]}")

        self.session.headers["Authorization"] = f"GoogleLogin auth={token}"

    def get_unread_articles(self, max_count: int = 50) -> list[Article]:
        resp = self.session.get(
            f"{self.base_url}/api/greader.php/reader/api/0/stream/contents/user/-/state/com.google/reading-list",
            params={
                "n": max_count,
                "xt": "user/-/state/com.google/read",
                "output": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get("items", []):
            url = _first_href(item.get("canonical")) or _first_href(item.get("alternate")) or ""
            content = _item_content(item)
            articles.append(
                Article(
                    id=item["id"],
                    title=item.get("title", "Untitled"),
                    url=url,
                    content=content,
                    author=item.get("author", ""),
                    published=item.get("published", 0),
                    feed_title=item.get("origin", {}).get("title", ""),
                )
            )
        return articles

    def mark_read(self, article_ids: list[str]) -> None:
        csrf_token = self._get_csrf_token()
        url = f"{self.base_url}/api/greader.php/reader/api/0/edit-tag"
        for article_id in article_ids:
            resp = self.session.post(
                url,
                data={
                    "i": article_id,
                    "a": "user/-/state/com.google/read",
                    "T": csrf_token,
                },
            )
            resp.raise_for_status()

    def _get_csrf_token(self) -> str:
        resp = self.session.get(f"{self.base_url}/api/greader.php/reader/api/0/token")
        resp.raise_for_status()
        return resp.text.strip()


def _first_href(links: list | None) -> str | None:
    if links:
        return links[0].get("href")
    return None


def _item_content(item: dict) -> str:
    for key in ("summary", "content"):
        if block := item.get(key):
            return block.get("content", "")
    return ""
