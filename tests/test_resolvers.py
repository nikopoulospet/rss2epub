import unittest

from rss2epub.resolvers import apply_resolvers, build_resolver_chain
from rss2epub.resolvers.base import ResolveContext
from rss2epub.resolvers.twitter import TwitterLinkResolver, _is_twitter_url


def _ctx(**kwargs) -> ResolveContext:
    defaults = dict(item_id="id-1", title="Test Article", article_url="https://example.com")
    defaults.update(kwargs)
    return ResolveContext(**defaults)


# ── apply_resolvers ───────────────────────────────────────────────────────────

class TestApplyResolvers(unittest.TestCase):
    def test_empty_chain_returns_unchanged(self):
        html = "<p>Content</p>"
        self.assertEqual(apply_resolvers(html, _ctx(), []), html)

    def test_resolvers_applied_in_order(self):
        class Append:
            def __init__(self, char):
                self.CONFIG_KEY = f"append_{char}"
                self._char = char
            def resolve(self, html, ctx):
                return html + self._char

        result = apply_resolvers("X", _ctx(), [Append("A"), Append("B")])
        self.assertEqual(result, "XAB")

    def test_failing_resolver_passes_through_unchanged(self):
        class Explosive:
            CONFIG_KEY = "explosive"
            def resolve(self, html, ctx):
                raise RuntimeError("boom")

        html = "<p>Safe content</p>"
        self.assertEqual(apply_resolvers(html, _ctx(), [Explosive()]), html)

    def test_failing_resolver_does_not_block_subsequent(self):
        class Explosive:
            CONFIG_KEY = "explosive"
            def resolve(self, html, ctx):
                raise RuntimeError("boom")

        class Append:
            CONFIG_KEY = "append"
            def resolve(self, html, ctx):
                return html + "A"

        self.assertEqual(apply_resolvers("X", _ctx(), [Explosive(), Append()]), "XA")


# ── build_resolver_chain ──────────────────────────────────────────────────────

class TestBuildResolverChain(unittest.TestCase):
    def test_unknown_section_ignored(self):
        self.assertEqual(build_resolver_chain({"no-such-resolver": {}}), [])

    def test_known_section_creates_resolver(self):
        chain = build_resolver_chain({"twitter-link": {}})
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].CONFIG_KEY, "twitter-link")

    def test_empty_config_gives_empty_chain(self):
        self.assertEqual(build_resolver_chain({}), [])

    def test_resolver_receives_its_section_config(self):
        chain = build_resolver_chain({"twitter-link": {"replacement": "custom text"}})
        self.assertEqual(chain[0].replacement, "custom text")

    def test_unrelated_sections_dont_create_resolvers(self):
        # Standard config sections like [server] and [output] must not be
        # mistaken for resolvers.
        data = {
            "server": {"url": "https://x.com", "username": "u"},
            "output": {"dir": "~/out"},
            "twitter-link": {},
        }
        chain = build_resolver_chain(data)
        self.assertEqual(len(chain), 1)


# ── TwitterLinkResolver ───────────────────────────────────────────────────────

class TestTwitterLinkResolver(unittest.TestCase):
    def _resolver(self, **cfg) -> TwitterLinkResolver:
        return TwitterLinkResolver(cfg)

    def test_default_replacement_text(self):
        r = self._resolver()
        self.assertIn("twitter link", r.replacement.lower())

    def test_custom_replacement_text(self):
        r = self._resolver(replacement="[tweet removed]")
        result = r.resolve(
            '<a href="https://twitter.com/user/status/1">tweet</a>', _ctx()
        )
        self.assertIn("[tweet removed]", result)

    def test_replaces_twitter_blockquote(self):
        html = '<blockquote class="twitter-tweet"><p>Some tweet text</p></blockquote>'
        result = self._resolver().resolve(html, _ctx())
        self.assertNotIn("twitter-tweet", result)
        self.assertNotIn("Some tweet text", result)
        self.assertIn(self._resolver().replacement, result)

    def test_replaces_twitter_link(self):
        html = '<p>See <a href="https://twitter.com/user/status/123">this</a></p>'
        result = self._resolver().resolve(html, _ctx())
        self.assertNotIn("twitter.com", result)

    def test_replaces_x_com_link(self):
        html = '<p>See <a href="https://x.com/user/status/123">this</a></p>'
        result = self._resolver().resolve(html, _ctx())
        self.assertNotIn("x.com", result)

    def test_removes_twitter_widget_script(self):
        html = (
            '<blockquote class="twitter-tweet"><p>tweet</p></blockquote>'
            '<script async src="https://platform.twitter.com/widgets.js"></script>'
        )
        result = self._resolver().resolve(html, _ctx())
        self.assertNotIn("widgets.js", result)
        self.assertNotIn("<script", result)

    def test_non_twitter_content_unchanged(self):
        html = "<p>Just a regular paragraph.</p>"
        self.assertEqual(self._resolver().resolve(html, _ctx()), html)

    def test_non_twitter_links_unchanged(self):
        html = '<p><a href="https://example.com/article">article</a></p>'
        result = self._resolver().resolve(html, _ctx())
        self.assertIn("example.com", result)

    def test_empty_input_returns_empty(self):
        self.assertEqual(self._resolver().resolve("", _ctx()), "")


class TestIsTwitterUrl(unittest.TestCase):
    def test_twitter_com(self):
        self.assertTrue(_is_twitter_url("https://twitter.com/user/status/1"))

    def test_x_com(self):
        self.assertTrue(_is_twitter_url("https://x.com/user/status/1"))

    def test_unrelated(self):
        self.assertFalse(_is_twitter_url("https://example.com/article"))

    def test_contains_twitter_in_path(self):
        # "twitter" appearing in a path segment should not be treated as a Twitter URL
        self.assertFalse(_is_twitter_url("https://example.com/about-twitter-strategy"))
