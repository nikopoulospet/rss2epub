import argparse
import hashlib
import re
import sys
import tempfile
from pathlib import Path

from .config import load_config
from .epub import build_epub
from .freshrss import FreshRSSClient
from .localdir import LocalDirUploader
from .state import State


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch unread FreshRSS articles and convert to EPUB."
    )
    parser.add_argument(
        "--config",
        default="~/.config/rss2rm/config.toml",
        help="Path to TOML config file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and convert articles to a temp dir; do not update state",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Override max_articles from config",
    )
    args = parser.parse_args()

    try:
        config = load_config(Path(args.config).expanduser())
    except FileNotFoundError:
        sys.exit(f"Config file not found: {args.config}")
    except Exception as e:
        sys.exit(f"Config error: {e}")

    if args.limit is not None:
        config.fetch.max_articles = args.limit

    if args.dry_run:
        output_dir = tempfile.mkdtemp(prefix="rss2rm-dry-run-")
        print(f"Dry run — EPUBs will be written to {output_dir}")
    else:
        output_dir = config.output.directory

    uploader = LocalDirUploader(output_dir)
    state = State(config.state.path)

    client = FreshRSSClient(
        config.freshrss.url,
        config.freshrss.username,
        config.freshrss.api_password,
    )

    print("Authenticating with FreshRSS...")
    try:
        client.authenticate()
    except Exception as e:
        sys.exit(f"Authentication failed: {e}")

    print(f"Fetching up to {config.fetch.max_articles} unread articles...")
    try:
        articles = client.get_unread_articles(config.fetch.max_articles)
    except Exception as e:
        sys.exit(f"Failed to fetch articles: {e}")

    fetched = len(articles)
    converted = 0
    skipped = 0
    failed = 0
    mark_read_ids: list[str] = []

    for article in articles:
        if not args.dry_run and state.is_synced(article.id):
            skipped += 1
            continue

        try:
            epub_bytes = build_epub(article, config.epub)
            filename = _make_filename(article)
            uploader.upload(filename, epub_bytes)

            if not args.dry_run:
                state.mark_synced(article.id)
                if config.fetch.mark_read_after_upload:
                    mark_read_ids.append(article.id)

            converted += 1
            print(f"  OK  {filename}")
        except Exception as e:
            failed += 1
            print(f"  ERR {article.title!r}: {e}", file=sys.stderr)

    if mark_read_ids:
        try:
            client.mark_read(mark_read_ids)
        except Exception as e:
            print(f"Warning: failed to mark articles read: {e}", file=sys.stderr)

    if args.dry_run:
        print(f"\nDry run complete: fetched {fetched}, converted {converted}, failed {failed}")
        print(f"EPUBs written to: {output_dir}")
    else:
        print(f"\nDone: fetched {fetched}, converted {converted}, skipped {skipped}, failed {failed}")


def _make_filename(article) -> str:
    safe = re.sub(r"[^\w\s-]", "", article.title)
    safe = re.sub(r"[-\s]+", "-", safe).strip("-")[:60]
    id_hash = hashlib.md5(article.id.encode()).hexdigest()[:8]
    return f"{safe}-{id_hash}.epub"


if __name__ == "__main__":
    main()
