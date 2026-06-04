from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ResolveContext:
    item_id: str
    title: str
    article_url: str


@runtime_checkable
class Resolver(Protocol):
    """Contract every resolver must satisfy.

    A resolver takes content HTML and returns content HTML.  Same type in,
    same type out — so the chain composes by simple iteration.

    Rules every implementation must follow:
    - Return the input unchanged on any failure (fail-soft).  A resolver
      that throws couples article delivery to external uptime; a resolver
      that returns the unmodified input degrades gracefully.
    - Be deterministic on failure: use a stable placeholder rather than
      a varying error string, so "content unchanged upstream" reliably
      produces the same fingerprint.
    """

    CONFIG_KEY: str  # matches the TOML section name that enables this resolver

    def resolve(self, html: str, ctx: ResolveContext) -> str:
        ...
