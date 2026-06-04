"""Content resolver chain.

Resolvers transform article HTML between GReader fetch and EPUB build.
Each resolver is a small, independently-toggleable unit with one job.

Configuration
-------------
A resolver is enabled by the presence of its TOML section in the config
file.  The section's contents are the resolver's config.  No section means
the resolver is not in the chain — it doesn't run, it costs nothing.

    [twitter-link]
    replacement = "A fucking twitter link"

Adding a new resolver: write a class with a CONFIG_KEY class attribute and a
resolve(html, ctx) method, then add it to _REGISTRY below.

Fail-soft contract
------------------
apply_resolvers() wraps every call so that any exception from a resolver
returns the input unchanged.  A broken resolver never breaks article delivery.
Resolvers themselves should also follow this rule internally (return input on
failure) so that partial failures within a resolver (e.g. one bad img tag)
don't abort the rest of its work.
"""

import logging
from collections.abc import Sequence
from typing import Any

from .base import ResolveContext, Resolver
from .images import ImageInlinerResolver
from .twitter import TwitterLinkResolver

logger = logging.getLogger(__name__)

# Registry: maps CONFIG_KEY → resolver class.
# To add a new resolver, import its class and add it here.
_REGISTRY: dict[str, type] = {
    TwitterLinkResolver.CONFIG_KEY: TwitterLinkResolver,
    ImageInlinerResolver.CONFIG_KEY: ImageInlinerResolver,
}


def build_resolver_chain(config_data: dict[str, Any]) -> list[Resolver]:
    """Instantiate enabled resolvers from the parsed TOML config dict.

    A resolver is enabled when its CONFIG_KEY appears as a top-level section
    in the config.  The section's dict is passed as the resolver's config.
    Order in the chain matches the order resolvers appear in _REGISTRY.
    """
    chain: list[Resolver] = []
    for key, cls in _REGISTRY.items():
        if key in config_data:
            chain.append(cls(config_data[key]))
            logger.debug("Resolver enabled: %s", key)
    return chain


def apply_resolvers(
    html: str,
    ctx: ResolveContext,
    chain: Sequence[Resolver],
) -> str:
    """Apply each resolver in order, failing soft on any exception."""
    for resolver in chain:
        try:
            html = resolver.resolve(html, ctx)
        except Exception as exc:
            logger.warning(
                "Resolver %r raised on %r — passing through: %s",
                resolver.CONFIG_KEY,
                ctx.title,
                exc,
            )
    return html
