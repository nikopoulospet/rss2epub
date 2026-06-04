# rss2epub

## Why this exists

The target reading device cannot run a syncing RSS client and can only consume EPUB files dropped into a file store — it pulls files; it does not fetch data itself.

Standard syncing RSS clients (Reeder, NetNewsWire, etc.) require running on the device — impossible here. Calibre's news-recipe system is the closest prior art, but it produces **issue bundles** (one large periodical EPUB per fetch), not individually addressable per-article files. That breaks the core requirement: the reader must track position per article, and the user wants to pull individual articles à la carte through the day. No existing open-source tool produces *per-article EPUB files with content-change-aware overwrite semantics* against a GReader backend.

That specific orchestration — and only that — is what rss2epub does.

---

## What it does (and does not do)

**Does:**
- Authenticate to any GReader-compatible aggregator (FreshRSS, Miniflux) and fetch items within a configurable time window.
- Render each new or changed item as **one EPUB per article** into a flat output directory.
- On a content change, **overwrite the same file in place** — never rename, never version. The downstream reader keys reading-position to the file path, so overwrite-in-place preserves your place in a corrected article.
- Track all of the above in a local SQLite catalog (content fingerprints + filenames).

**Does not:**
- Fetch full-text article pages from the web. Content fidelity is the aggregator's job — enable FreshRSS's full-text fetch per feed if the feed publishes excerpts only.
- Embed images. Images referenced in the feed HTML appear as remote `<img>` tags in the EPUB.
- Sync files to your device. The output directory is the deliverable; how it reaches the reader (Drive, Nextcloud, rclone, syncthing, manual copy) is your sink, not this tool's concern.
- Track read state. Your e-reader owns reading position and read/unread state entirely.
- Run on a schedule. Wrap the CLI in a `systemd --user` timer or cron when you want automation — the entrypoint is the unit of execution and does not change.

---

## How it works

```
GReader aggregator (FreshRSS / Miniflux)
    │
    │  stream/contents?ot={cutoff}  — items newer than (now − lookback)
    ▼
for each item:
    xhtml  = tidy_to_xhtml(item.content)    # lxml: validity only, not extraction
    fp     = sha256(title + xhtml)           # content fingerprint
    state  = classify(item_id, fp, catalog)  # NEW | UNCHANGED | CHANGED
    if state in (NEW, CHANGED):
        write OUTPUT_DIR/{stable-name}.epub  # overwrite if CHANGED
        catalog.upsert(item_id, fp, ...)
    else:
        skip

print: fetched N, rendered M (new X / changed Y), skipped K, failed F
```

EPUB filenames are `{title-slug}-{id-hash}.epub`. The slug is for human readability; the ID hash is what makes the name **stable even if the title changes upstream** — the file is overwritten to the same path.

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A GReader-compatible aggregator (FreshRSS, Miniflux) with API access enabled
- **Full-text fetch enabled per feed** in the aggregator, for feeds that publish excerpts only (this tool does not fetch article URLs)

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/youruser/rss2epub
cd rss2epub
uv venv
uv pip install -e .
```

**2. Enable the aggregator API**

In FreshRSS: Settings → Profile → API Management → set an API password.
This is a separate credential from your login password.

**3. Create a config file**

```bash
mkdir -p ~/.config/rss2epub
cp config.example.toml ~/.config/rss2epub/config.toml
```

Edit `~/.config/rss2epub/config.toml` — set `url` and `username` under `[server]`.

**4. Set your API password**

```bash
export RSS2EPUB_API_PASSWORD=your-api-password
```

Add this to your shell profile so it persists across sessions.

---

## Running

```bash
# Normal run
rss2epub

# Dry run: renders to a temp dir, no catalog writes, no overwrites
rss2epub --dry-run

# Override lookback for this run
rss2epub --lookback 7d

# Verbose: show API calls and per-item classify decisions
rss2epub --verbose

# Quiet: suppress info output (warnings and final summary only)
rss2epub --quiet

# Custom config
rss2epub --config /path/to/config.toml
```

**Example output (default INFO level):**

```
INFO     Authenticating as peter @ https://rss.example.com
INFO     Fetching window: 2026-05-04 14:30 → now  (lookback: 30d)
INFO     Fetched 43 items
INFO     NEW       My Article Title  →  my-article-title-a1b2c3d4.epub
INFO     CHANGED   Edited Post       →  edited-post-e5f6g7h8.epub
fetched 43, rendered 2 (new 1 / changed 1), skipped 41, failed 0
```

The final summary line is always printed regardless of `-v`/`-q`.

**Exit codes:** `0` = success, `1` = fatal error (auth/config), `2` = partial failure (some articles failed to render).

---

## Configuration

`~/.config/rss2epub/config.toml`:

```toml
[server]
url      = "https://rss.example.com"
username = "peter"
# API password from env: RSS2EPUB_API_PASSWORD

[fetch]
lookback = "30d"    # window for edit-checking; accepts d, h, w (e.g. "7d", "72h", "2w")

[epub]
stylesheet = ""     # optional path to a CSS file for reader typography

[output]
dir = "~/rss2epub/out"          # where EPUBs are written
db  = "~/rss2epub/catalog.db"   # SQLite catalog
```

The config file is safe to commit to a dotfiles repo — secrets stay in the environment.

---

## The catalog

`catalog.db` is a SQLite file tracking every article ever processed. It stores the content fingerprint, EPUB filename, and timestamps. You can query it directly:

```sql
-- recent renders
SELECT title, datetime(last_written, 'unixepoch') FROM articles ORDER BY last_written DESC LIMIT 20;

-- articles that changed since first render
SELECT title FROM articles WHERE last_written > published + 86400;
```

**Edit detection:** the fingerprint is `sha256(title + tidy_xhtml)`, computed on the content the EPUB is actually built from (not the raw feed payload, which can carry rotating tracking tokens). A mismatch means the article was genuinely edited upstream.

**Persistence:** article files stay in the output directory until you manually remove them. The lookback window controls which articles are *re-examined for edits* on each run — it does not prune already-written files. Articles older than the window stay on disk and in the catalog.

**Force re-render:** delete the catalog row (or the entire catalog) and re-run.

```sql
DELETE FROM articles WHERE item_id = 'tag:google.com,...';
```

---

## Project layout

```
rss2epub/
  __main__.py   CLI + orchestration (classify, run loop, run stats)
  config.py     TOML loading, lookback parser, env secret resolution
  freshrss.py   GReader client (auth, windowed fetch, pagination)
  epub.py       tidy_to_xhtml (lxml), stable_name, build_epub (ebooklib)
  catalog.py    SQLite catalog (open/migrate, lookup, upsert, touch)
```

---

## Running tests

```bash
uv run pytest tests/ -v
```
