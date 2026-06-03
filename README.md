# rss2rm

## Why this exists

The reMarkable 2 is a great reading device, but getting articles onto it is awkward. The official workflow requires either the browser extension (desktop only, no server-side automation) or manually saving URLs one at a time.

This tool closes that gap for self-hosted RSS readers. If you run FreshRSS, you already have a queue of articles you've marked worth reading — rss2rm turns that queue into a folder of EPUBs on your reMarkable, via Google Drive.

The design is deliberately minimal: a single CLI command you run when you want to sync. It fetches your unread articles from FreshRSS, runs each one through a readability extractor to strip away navigation and ads, packages each article as an EPUB, and drops the files into a Google Drive folder that your tablet can browse. Nothing runs on the tablet; nothing is installed on it. The render server does all the work.

---

## How it works

```
FreshRSS (GReader API)
    │
    ▼
fetch unread articles
    │
    ▼
readability extract (fetches full article page)
    │
    ▼
build EPUB (one file per article)
    │
    ▼
write to output directory  ──▶  (later: upload to Google Drive)
```

On the tablet: open the Drive sidebar, browse to your folder, copy files to My Files.

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A [FreshRSS](https://freshrss.org) instance with API access enabled

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/youruser/rss2rm
cd rss2rm
uv venv
uv pip install -e .
```

**2. Enable the FreshRSS API**

In FreshRSS: Settings → Profile → scroll to "API Management" → set an API password. This is distinct from your login password and is what rss2rm uses — your login password will not work.

**3. Create a config file**

```bash
mkdir -p ~/.config/rss2rm
cp config.example.toml ~/.config/rss2rm/config.toml
```

Then edit `~/.config/rss2rm/config.toml` (see [Configuration](#configuration) below).

**4. Set your API password**

```bash
export FRESHRSS_API_PASSWORD=your-api-password
```

Add this to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) to avoid re-entering it each session.

---

## Running

```bash
# Dry run: fetch and convert articles, write EPUBs to a temp directory, no state changes
.venv/bin/rss2rm --dry-run

# Normal run: write EPUBs to the configured output directory, record synced IDs
.venv/bin/rss2rm

# Limit to N articles (overrides max_articles in config)
.venv/bin/rss2rm --limit 10

# Use a non-default config file
.venv/bin/rss2rm --config /path/to/config.toml
```

Output looks like:

```
Authenticating with FreshRSS...
Fetching up to 50 unread articles...
  OK  My-Article-Title-a1b2c3d4.epub
  OK  Another-Article-e5f6g7h8.epub
  ERR 'Paywalled Post': HTTP 403
Done: fetched 3, converted 2, skipped 0, failed 1
```

EPUBs are named `{sanitized-title}-{short-id-hash}.epub` to avoid collisions between articles with identical titles.

---

## Configuration

`~/.config/rss2rm/config.toml`:

```toml
[freshrss]
url = "https://rss.example.com"
username = "peter"
# API password is read from the FRESHRSS_API_PASSWORD environment variable

[fetch]
max_articles = 50          # max articles to fetch per run
only_unread = true         # only fetch unread items
mark_read_after_upload = false  # flip to true to use FreshRSS unread state as the sync queue

[epub]
include_images = true      # keep <img> tags in the EPUB (remote URLs, not embedded)
page_title_prefix = ""     # prepend a string to every article title, e.g. "[RSS] "

[output]
directory = "~/rss2rm-output"   # where EPUBs are written

[state]
path = "~/.local/state/rss2rm/synced.json"  # tracks which articles have been synced
```

### Deduplication and state

rss2rm records the GReader item ID of every article it successfully converts. On the next run it skips those IDs. This means:

- A failed conversion is retried automatically on the next run.
- Deleting an EPUB from the output directory does **not** re-sync it — edit the state file to remove the ID if you want to re-convert an article.
- If `mark_read_after_upload = true`, FreshRSS's own read state becomes the queue and the state file is belt-and-suspenders. If `false` (the default), the state file is the sole dedup mechanism — articles stay unread in FreshRSS.

---

## Running tests

```bash
.venv/bin/python -m pytest tests/ -v
```

---

## Project layout

```
rss2rm/
  __main__.py   CLI entry point — orchestration and summary output
  config.py     TOML config loading, env-var secret resolution
  freshrss.py   FreshRSS GReader API client (auth, fetch, mark-read)
  epub.py       readability extraction → EPUB bytes
  uploader.py   abstract Uploader interface
  localdir.py   local directory implementation of Uploader
  state.py      atomic load/save of synced article IDs
```

`localdir.py` is a placeholder for the eventual Google Drive uploader. The interface is `upload(filename: str, data: bytes) -> bool` — swapping in Drive changes one file only.

---

## Roadmap

- [ ] Google Drive uploader (`drive.py`) so EPUBs land directly in the Drive folder visible to the reMarkable
- [ ] `systemd --user` timer example for automated periodic sync
