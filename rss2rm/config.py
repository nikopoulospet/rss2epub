import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FreshRSSConfig:
    url: str
    username: str
    api_password: str


@dataclass
class FetchConfig:
    max_articles: int = 50
    only_unread: bool = True
    mark_read_after_upload: bool = False


@dataclass
class EPUBConfig:
    include_images: bool = True
    page_title_prefix: str = ""


@dataclass
class OutputConfig:
    directory: str = "~/rss2rm-output"


@dataclass
class StateConfig:
    path: str = "~/.local/state/rss2rm/synced.json"


@dataclass
class Config:
    freshrss: FreshRSSConfig
    fetch: FetchConfig
    epub: EPUBConfig
    output: OutputConfig
    state: StateConfig


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    api_password = os.environ.get("FRESHRSS_API_PASSWORD")
    if not api_password:
        raise RuntimeError("FRESHRSS_API_PASSWORD environment variable is not set")

    fr = data["freshrss"]

    return Config(
        freshrss=FreshRSSConfig(
            url=fr["url"].rstrip("/"),
            username=fr["username"],
            api_password=api_password,
        ),
        fetch=FetchConfig(**data.get("fetch", {})),
        epub=EPUBConfig(**data.get("epub", {})),
        output=OutputConfig(**data.get("output", {})),
        state=StateConfig(**data.get("state", {})),
    )
