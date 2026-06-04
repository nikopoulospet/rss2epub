import unittest
from unittest.mock import MagicMock

from rss2epub.greader import GReaderClient, _first_href, _item_content


def _make_client() -> GReaderClient:
    return GReaderClient("https://rss.example.com", "user", "secret")


def _patched_client(pages: list[dict]) -> GReaderClient:
    """Return a client whose session.get returns pages sequentially."""
    client = _make_client()
    responses = []
    for page in pages:
        mock_resp = MagicMock()
        mock_resp.json.return_value = page
        mock_resp.raise_for_status = MagicMock()
        responses.append(mock_resp)
    client.session.get = MagicMock(side_effect=responses)
    return client


def _item(item_id="tag:google.com,2005:reader/item/0000000000000001",
          title="Sample", published=2_000_000_000, **overrides) -> dict:
    base = {
        "id": item_id,
        "title": title,
        "canonical": [{"href": "https://example.com/article"}],
        "summary": {"content": "<p>Body text.</p>"},
        "author": "Jane Doe",
        "published": published,
        "origin": {"title": "My Feed", "htmlUrl": "https://example.com"},
    }
    base.update(overrides)
    return base


class TestAuthenticate(unittest.TestCase):
    def test_sets_auth_header_on_success(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.text = "SID=ignored\nAuth=mytoken123\n"
        mock_resp.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_resp)

        client.authenticate()

        self.assertEqual(
            client.session.headers["Authorization"],
            "GoogleLogin auth=mytoken123",
        )

    def test_auth_url_does_not_contain_greader_php(self):
        # The /api/greader.php prefix is FreshRSS's convention; it must come
        # from the config URL, not be hardcoded in the client.
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.text = "Auth=tok\n"
        mock_resp.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_resp)

        client.authenticate()

        called_url = client.session.post.call_args[0][0]
        self.assertNotIn("greader.php", called_url)
        self.assertTrue(called_url.endswith("/accounts/ClientLogin"))

    def test_freshrss_base_url_with_path_prefix_works(self):
        # Simulate FreshRSS: user sets url = "https://rss.example.com/api/greader.php"
        client = GReaderClient("https://rss.example.com/api/greader.php", "u", "p")
        mock_resp = MagicMock()
        mock_resp.text = "Auth=tok\n"
        mock_resp.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_resp)

        client.authenticate()

        called_url = client.session.post.call_args[0][0]
        self.assertEqual(
            called_url,
            "https://rss.example.com/api/greader.php/accounts/ClientLogin",
        )

    def test_raises_when_auth_token_missing(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.text = "Error=BadAuthentication\n"
        mock_resp.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_resp)

        with self.assertRaises(RuntimeError):
            client.authenticate()


class TestGetArticlesSince(unittest.TestCase):
    CUTOFF = 1_000_000_000

    def test_returns_articles_in_window(self):
        client = _patched_client([{"items": [_item(published=self.CUTOFF + 1)]}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Sample")
        self.assertEqual(articles[0].url, "https://example.com/article")
        self.assertEqual(articles[0].content, "<p>Body text.</p>")
        self.assertEqual(articles[0].author, "Jane Doe")
        self.assertEqual(articles[0].feed_title, "My Feed")

    def test_stream_url_does_not_contain_greader_php(self):
        client = _patched_client([{"items": []}])
        client.get_articles_since(self.CUTOFF)
        called_url = client.session.get.call_args[0][0]
        self.assertNotIn("greader.php", called_url)

    def test_filters_out_items_older_than_cutoff(self):
        old = _item(item_id="id-old", published=self.CUTOFF - 1)
        new = _item(item_id="id-new", published=self.CUTOFF + 1)
        client = _patched_client([{"items": [old, new]}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        ids = [a.id for a in articles]
        self.assertIn("id-new", ids)
        self.assertNotIn("id-old", ids)

    def test_returns_empty_list_for_empty_response(self):
        client = _patched_client([{"items": []}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(articles, [])

    def test_paginates_via_continuation_token(self):
        page1 = {"items": [_item(item_id="id-1", published=self.CUTOFF + 1)], "continuation": "tok1"}
        page2 = {"items": [_item(item_id="id-2", published=self.CUTOFF + 2)]}
        client = _patched_client([page1, page2])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(len(articles), 2)
        second_call_params = client.session.get.call_args_list[1][1]["params"]
        self.assertEqual(second_call_params["c"], "tok1")

    def test_stops_paginating_when_no_continuation(self):
        client = _patched_client([{"items": [_item(published=self.CUTOFF + 1)]}])
        client.get_articles_since(self.CUTOFF)
        self.assertEqual(client.session.get.call_count, 1)

    def test_passes_cutoff_as_ot_param(self):
        client = _patched_client([{"items": []}])
        client.get_articles_since(self.CUTOFF)
        params = client.session.get.call_args[1]["params"]
        self.assertEqual(params["ot"], self.CUTOFF)
        self.assertNotIn("nt", params)

    def test_falls_back_to_alternate_for_url(self):
        item = _item(published=self.CUTOFF + 1)
        del item["canonical"]
        item["alternate"] = [{"href": "https://alt.example.com/article"}]
        client = _patched_client([{"items": [item]}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(articles[0].url, "https://alt.example.com/article")

    def test_uses_content_field_when_summary_absent(self):
        item = _item(published=self.CUTOFF + 1)
        del item["summary"]
        item["content"] = {"content": "<p>From content field.</p>"}
        client = _patched_client([{"items": [item]}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(articles[0].content, "<p>From content field.</p>")

    def test_empty_content_when_both_fields_absent(self):
        item = _item(published=self.CUTOFF + 1)
        del item["summary"]
        client = _patched_client([{"items": [item]}])
        articles, _ = client.get_articles_since(self.CUTOFF)
        self.assertEqual(articles[0].content, "")


class TestHelpers(unittest.TestCase):
    def test_first_href_returns_first(self):
        self.assertEqual(
            _first_href([{"href": "https://a.com"}, {"href": "https://b.com"}]),
            "https://a.com",
        )

    def test_first_href_returns_none_for_none(self):
        self.assertIsNone(_first_href(None))

    def test_first_href_returns_none_for_empty_list(self):
        self.assertIsNone(_first_href([]))

    def test_item_content_prefers_content_over_summary(self):
        # GReader spec: `content` = body, `summary` = excerpt. Prefer body.
        item = {
            "content": {"content": "full article body"},
            "summary": {"content": "short excerpt"},
        }
        self.assertEqual(_item_content(item), "full article body")

    def test_item_content_falls_back_to_summary(self):
        item = {"summary": {"content": "only a summary here"}}
        self.assertEqual(_item_content(item), "only a summary here")

    def test_item_content_falls_back_to_content_key(self):
        self.assertEqual(_item_content({"content": {"content": "from content"}}), "from content")

    def test_item_content_empty_when_both_absent(self):
        self.assertEqual(_item_content({}), "")

    def test_item_content_skips_empty_content_field(self):
        # If `content` is present but empty, fall through to `summary`.
        item = {"content": {"content": ""}, "summary": {"content": "fallback"}}
        self.assertEqual(_item_content(item), "fallback")
