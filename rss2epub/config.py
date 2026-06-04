import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerConfig:
    url: str
    username: str
    password: str


@dataclass
class FetchConfig:
    lookback: str = "30d"


@dataclass
class EPUBConfig:
    stylesheet: str = ""   # optional path to a CSS file; empty = no stylesheet


@dataclass
class OutputConfig:
    dir: str = "~/rss2epub/out"
    db: str = "~/rss2epub/catalog.db"


@dataclass
class Config:
    server: ServerConfig
    fetch: FetchConfig
    epub: EPUBConfig
    output: OutputConfig


def parse_lookback(s: str) -> int:
    """Return seconds for a duration string like '30d', '72h', '6w'."""
    s = s.strip()
    units = {"h": 3600, "d": 86400, "w": 604800}
    unit = s[-1].lower() if s else ""
    value = s[:-1]
    if unit not in units or not value.isdigit() or int(value) <= 0:
        raise ValueError(
            f"Invalid lookback {s!r} — expected a positive integer followed by h, d, or w"
            " (e.g. '30d', '72h', '2w')"
        )
    return int(value) * units[unit]


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    password = os.environ.get("RSS2EPUB_API_PASSWORD")
    if not password:
        raise RuntimeError("RSS2EPUB_API_PASSWORD environment variable is not set")

    srv = data["server"]
    return Config(
        server=ServerConfig(
            url=srv["url"].rstrip("/"),
            username=srv["username"],
            password=password,
        ),
        fetch=FetchConfig(**data.get("fetch", {})),
        epub=EPUBConfig(**data.get("epub", {})),
        output=OutputConfig(**data.get("output", {})),
    )
