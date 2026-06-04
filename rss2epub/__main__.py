import argparse
import enum
import hashlib
import logging
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .catalog import Catalog, CatalogRow
from .config import Config, load_config, parse_lookback
from .epub import build_epub, tidy_to_xhtml
from .greader import GReaderClient
from .output_path import check_confined, resolve_output_path
from .resolvers import apply_resolvers, build_resolver_chain
from .resolvers.base import ResolveContext

logger = logging.getLogger(__name__)


# ── classification ────────────────────────────────────────────────────────────

class State(enum.Enum):
    NEW       = "NEW"
    UNCHANGED = "SKIP"
    CHANGED   = "CHANGED"


def classify(existing: CatalogRow | None, fp: str) -> State:
    """Determine the render decision for one article."""
    if existing is None:
        return State.NEW
    return State.UNCHANGED if existing.content_hash == fp else State.CHANGED


# ── run stats ─────────────────────────────────────────────────────────────────

@dataclass
class RunStats:
    fetched: int = 0
    new: int = 0
    changed: int = 0
    skipped: int = 0
    failed: int = 0

    @property
    def rendered(self) -> int:
        return self.new + self.changed

    def summary(self) -> str:
        return (
            f"fetched {self.fetched}, "
            f"rendered {self.rendered} (new {self.new} / changed {self.changed}), "
            f"skipped {self.skipped}, "
            f"failed {self.failed}"
        )


# ── orchestration ─────────────────────────────────────────────────────────────

def run(config: Config, dry_run: bool) -> RunStats:
    stats = RunStats()
    now = int(time.time())
    cutoff = now - parse_lookback(config.fetch.lookback)

    client = GReaderClient(config.server.url, config.server.username, config.server.password)
    logger.info("Authenticating as %s @ %s", config.server.username, config.server.url)
    client.authenticate()

    logger.info(
        "Fetching window: %s → now  (lookback: %s)",
        _fmt_epoch(cutoff),
        config.fetch.lookback,
    )
    items, diag = client.get_articles_since(cutoff)
    for line in diag:
        logger.debug(line)
    stats.fetched = len(items)
    logger.info("Fetched %d items", stats.fetched)

    stylesheet = _load_stylesheet(config.epub.stylesheet)
    resolver_chain = build_resolver_chain(config.resolver_config)
    if resolver_chain:
        logger.info("Resolvers: %s", [r.CONFIG_KEY for r in resolver_chain])
    catalog = Catalog(config.output.db)
    output_dir = Path(config.output.dir).expanduser()
    fmt = config.output.format

    if dry_run:
        write_dir = Path(tempfile.mkdtemp(prefix="rss2epub-dry-"))
        logger.info("Dry run — writing to %s (not committed to output dir)", write_dir)
    else:
        write_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        try:
            xhtml = tidy_to_xhtml(item.content)
            ctx = ResolveContext(item_id=item.id, title=item.article_name, article_url=item.url)
            xhtml = apply_resolvers(xhtml, ctx, resolver_chain)
            # Hash post-resolution: an upstream edit that only changes resolver
            # output (e.g. a new tweet embed added) still triggers a re-render.
            fp = hashlib.sha256((item.article_name + xhtml).encode()).hexdigest()
            existing = catalog.lookup(item.id)
            state = classify(existing, fp)

            new_rel = resolve_output_path(fmt, item) + ".epub"
            new_abs = check_confined(output_dir, new_rel)

            logger.debug(
                "%-8s  %s  (%d bytes content)",
                state.value, item.article_name[:70], len(item.content),
            )

            if state is State.UNCHANGED:
                if not dry_run:
                    if existing.filename != new_rel:
                        _move_epub(output_dir / existing.filename, new_abs)
                        catalog.upsert(CatalogRow(
                            item_id=item.id,
                            content_hash=existing.content_hash,
                            filename=new_rel,
                            title=item.article_name,
                            published=item.publish_date,
                            last_seen=now,
                            last_written=existing.last_written,
                        ))
                    else:
                        catalog.touch(item.id, now)
                stats.skipped += 1
                continue

            epub_bytes = build_epub(
                item.article_name,
                xhtml,
                author=item.author,
                source_url=item.url,
                stylesheet=stylesheet,
            )

            write_path = write_dir / new_rel
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_bytes(epub_bytes)

            if not dry_run:
                if state is State.CHANGED and existing.filename != new_rel:
                    (output_dir / existing.filename).unlink(missing_ok=True)
                catalog.upsert(CatalogRow(
                    item_id=item.id,
                    content_hash=fp,
                    filename=new_rel,
                    title=item.article_name,
                    published=item.publish_date,
                    last_seen=now,
                    last_written=now,
                ))

            if state is State.NEW:
                stats.new += 1
            else:
                stats.changed += 1
            logger.info("%-8s  %s  →  %s", state.value, item.article_name[:60], new_rel)

        except Exception as exc:
            stats.failed += 1
            logger.warning("FAILED    %r: %s", item.article_name, exc)

    catalog.close()
    return stats


# ── helpers ───────────────────────────────────────────────────────────────────

def _move_epub(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.rename(dst)
    except FileNotFoundError:
        pass


def _load_stylesheet(path: str) -> str:
    if not path:
        return ""
    p = Path(path).expanduser()
    if not p.exists():
        logger.warning("Stylesheet not found: %s", p)
        return ""
    return p.read_text(encoding="utf-8")


def _fmt_epoch(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rss2epub",
        description="Render recent RSS articles as per-article EPUB files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Content quality (full text, images) is the aggregator's job.\n"
            "This tool's only job: new-or-changed articles → EPUB files in OUTPUT_DIR."
        ),
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging (API calls, per-item classify decisions)",
    )
    verbosity.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress info output (warnings and errors only)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default="~/.config/rss2epub/config.toml",
        help="Config file path (default: ~/.config/rss2epub/config.toml)",
    )
    parser.add_argument(
        "--lookback",
        metavar="WINDOW",
        help="Override lookback window from config (e.g. 7d, 24h, 2w)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render EPUBs to a temp dir; no catalog writes, no overwrites",
    )
    args = parser.parse_args()

    level = (
        logging.DEBUG if args.verbose
        else logging.WARNING if args.quiet
        else logging.INFO
    )
    logging.basicConfig(level=level, format="%(levelname)-8s %(message)s")

    try:
        config = load_config(Path(args.config).expanduser())
    except FileNotFoundError:
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)
    except Exception as exc:
        logger.error("Config error: %s", exc)
        sys.exit(1)

    if args.lookback:
        config.fetch.lookback = args.lookback

    try:
        stats = run(config, dry_run=args.dry_run)
    except Exception as exc:
        logger.error("Fatal: %s", exc)
        sys.exit(1)

    print(stats.summary())
    sys.exit(2 if stats.failed else 0)


if __name__ == "__main__":
    main()
