import json
import unittest
from unittest.mock import MagicMock, patch

from rss2rm.freshrss import FreshRSSClient, _first_href, _item_content


def _make_client() -> FreshRSSClient:
    return FreshRSSClient("https://rss.example.com", "user", "secret")


class TestAuthenticate(unittest.TestCase):
    @patch("rss2rm.freshrss.requests.Session.post")
    def test_sets_auth_header_on_success(self, mock_post):
        mock_post.return_value.text = "SID=ignored\nAuth=mytoken123\n"
        mock_post.return_value.raise_for_status = MagicMock()

        client = _make_client()
        client.authenticate()

        self.assertEqual(
            client.session.headers["Authorization"],
            "GoogleLogin auth=mytoken123",
        )

    @patch("rss2rm.freshrss.requests.Session.post")
    def test_raises_when_auth_token_missing(self, mock_post):
        mock_post.return_value.text = "Error=BadAuthentication\n"
        mock_post.return_value.raise_for_status = MagicMock()

        with self.assertRaises(RuntimeError):
            _make_client().authenticate()


class TestGetUnreadArticles(unittest.TestCase):
    def _patched_client(self, payload: dict) -> FreshRSSClient:
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)
        return client

    def _sample_item(self, **overrides) -> dict:
        item = {
            "id": "tag:google.com,2005:reader/item/0000000000000001",
            "title": "Sample Title",
            "canonical": [{"href": "https://example.com/article"}],
            "summary": {"content": "<p>Body text.</p>"},
            "author": "Jane Doe",
            "published": 1748908800,
            "origin": {"title": "My Feed", "htmlUrl": "https://example.com"},
        }
        item.update(overrides)
        return item

    def test_returns_articles_list(self):
        client = self._patched_client({"items": [self._sample_item()]})
        articles = client.get_unread_articles()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Sample Title")
        self.assertEqual(articles[0].url, "https://example.com/article")
        self.assertEqual(articles[0].content, "<p>Body text.</p>")
        self.assertEqual(articles[0].author, "Jane Doe")
        self.assertEqual(articles[0].feed_title, "My Feed")

    def test_returns_empty_list_when_no_items(self):
        client = self._patched_client({"items": []})
        self.assertEqual(client.get_unread_articles(), [])

    def test_falls_back_to_alternate_for_url(self):
        item = self._sample_item()
        del item["canonical"]
        item["alternate"] = [{"href": "https://alternate.example.com/article"}]
        client = self._patched_client({"items": [item]})
        articles = client.get_unread_articles()
        self.assertEqual(articles[0].url, "https://alternate.example.com/article")

    def test_uses_content_field_when_summary_absent(self):
        item = self._sample_item()
        del item["summary"]
        item["content"] = {"content": "<p>From content field.</p>"}
        client = self._patched_client({"items": [item]})
        articles = client.get_unread_articles()
        self.assertEqual(articles[0].content, "<p>From content field.</p>")

    def test_empty_content_when_both_fields_absent(self):
        item = self._sample_item()
        del item["summary"]
        client = self._patched_client({"items": [item]})
        articles = client.get_unread_articles()
        self.assertEqual(articles[0].content, "")

    def test_passes_max_count_as_n_param(self):
        client = self._patched_client({"items": []})
        client.get_unread_articles(max_count=7)
        call_kwargs = client.session.get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(params["n"], 7)


class TestHelpers(unittest.TestCase):
    def test_first_href_returns_first(self):
        self.assertEqual(_first_href([{"href": "https://a.com"}, {"href": "https://b.com"}]), "https://a.com")

    def test_first_href_returns_none_for_none(self):
        self.assertIsNone(_first_href(None))

    def test_first_href_returns_none_for_empty(self):
        self.assertIsNone(_first_href([]))

    def test_item_content_prefers_summary(self):
        item = {"summary": {"content": "from summary"}, "content": {"content": "from content"}}
        self.assertEqual(_item_content(item), "from summary")

    def test_item_content_falls_back_to_content_key(self):
        item = {"content": {"content": "from content"}}
        self.assertEqual(_item_content(item), "from content")

    def test_item_content_empty_when_both_absent(self):
        self.assertEqual(_item_content({}), "")
