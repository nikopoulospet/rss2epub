# rss2epub

**Read your RSS feeds on a reMarkable that can't run a reader app.**

The reMarkable can only open files you copy onto it — it can't fetch articles on its own. rss2epub bridges that gap: it grabs your latest unread articles and saves each one as a separate EPUB. Copy that folder to the device and you've got your reading list, one article per file.

If an article gets corrected after you've saved it, rss2epub quietly updates that one file so you don't lose your place. It only makes the files; getting them onto the device is left to whatever you already use to move files around (a cloud folder, a sync tool, or a plain copy).

> Built and tested against the reMarkable. It should work for any e-reader that reads EPUBs out of a folder (Kobo, KOReader, Boox, and similar), but the reMarkable is the only device it's been verified on.

## How it works

```
Your feed reader  ──fetches──►  rss2epub  ──you copy──►  Your reMarkable
 (holds articles)            (one EPUB per article)        (opens files)
```

Your feed reader holds the articles, rss2epub turns the new ones into files, and you copy the folder to the device. (The diagram above this README shows the same flow.)

## Why it exists

The usual feed-reader apps (Reeder, NetNewsWire, and the like) have to run *on* the device — impossible on a reMarkable. The closest tool that does run elsewhere is Calibre, but it bundles a whole batch of articles into one big EPUB per fetch, like a newspaper issue, instead of saving each article on its own.

That doesn't fit the reMarkable, which tracks your reading position per file. One big bundle means one reading position for the whole batch. rss2epub gives every article its own file, so you can read them à la carte through the day and keep your place in each — and when an article is edited upstream, it overwrites that same file in place rather than making a new one, so your position survives the correction.

## What it does (and doesn't)

**Does**
- Pull recent articles from a self-hosted feed reader (FreshRSS, Miniflux, or anything GReader-compatible).
- Save each new or edited article as its own EPUB in a flat folder.
- Overwrite an article's file in place when it changes upstream — never a rename, never a duplicate.

**Doesn't**
- **Fetch full article text from the web.** That's your feed reader's job — turn on its full-text fetch for feeds that only publish excerpts.
- **Embed images.** Images stay as links in the EPUB rather than being downloaded into it.
- **Move files to your device.** The output folder is the finished product; how it gets to the reMarkable is up to you.
- **Track what you've read.** Your reMarkable owns read/unread state.
- **Run on a timer.** Run it by hand, or wrap it in a cron job or `systemd` timer for automation.

## Similar projects

If rss2epub isn't quite the fit, these solve nearby problems:

- **[goosepaper](https://github.com/j6k4m8/goosepaper)** — assembles RSS, weather, and more into a single daily newspaper PDF and can upload it to the reMarkable. Reach for this if you *want* one bundled issue rather than per-article files.
- **[RSSPub](https://github.com/harshit181/RSSPub)** — a self-hosted server that builds a daily newspaper EPUB and serves it over OPDS, with a read-later inbox. More of a personal-newspaper server than a file producer.
- **[Calibre](https://calibre-ebook.com/)** — the "Fetch News" recipe system. Mature and general-purpose, but produces per-fetch issue bundles, not individually addressable articles.
- **[pocket2rm](https://github.com/GliderGeek/pocket2rm)** — pulls read-later articles onto the reMarkable, running directly on the device.

The thing rss2epub does that these don't: **one EPUB per article, overwritten in place when the article changes.**

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A self-hosted feed reader (FreshRSS, Miniflux) with its API enabled
- Full-text fetch turned on in that reader for any feeds that only publish excerpts

## Setup

**1. Install**
```bash
git clone https://github.com/youruser/rss2epub
cd rss2epub
uv venv
uv pip install -e .
```

**2. Enable your feed reader's API**

In FreshRSS: Settings → Profile → API Management → set an API password. This is separate from your login password.

**3. Create a config file**
```bash
mkdir -p ~/.config/rss2epub
cp config.example.toml ~/.config/rss2epub/config.toml
```
Then edit it to set your reader's `url` and `username` under `[server]`.

**4. Set your API password**
```bash
export RSS2EPUB_API_PASSWORD=your-api-password
```
Add this to your shell profile so it sticks.

## Running

```bash
rss2epub                       # normal run
rss2epub --dry-run             # preview: no files written, no state changed
rss2epub --lookback 7d         # only check articles from the last 7 days
rss2epub --verbose             # show what it's doing per article
rss2epub --quiet               # warnings and the final summary only
rss2epub --config /path/to/config.toml
```

A normal run prints a summary like:
```
Fetched 43 items
NEW       My Article Title  →  my-article-title-a1b2c3d4.epub
CHANGED   Edited Post       →  edited-post-e5f6g7h8.epub
fetched 43, rendered 2 (new 1 / changed 1), skipped 41, failed 0
```

**Exit codes:** `0` success · `1` fatal error (auth/config) · `2` some articles failed to render.

## Configuration

`~/.config/rss2epub/config.toml`:
```toml
[server]
url      = "https://rss.example.com"
username = "peter"
# API password comes from the RSS2EPUB_API_PASSWORD environment variable

[fetch]
lookback = "30d"    # how far back to check for new/edited articles; accepts d, h, w

[epub]
stylesheet = ""     # optional path to a CSS file for reader typography

[output]
dir = "~/rss2epub/out"          # where EPUBs are written
db  = "~/rss2epub/catalog.db"   # internal bookkeeping (see below)
```
The config file is safe to commit to a dotfiles repo — the password stays in the environment.

## Notes for the curious

You don't need any of this to use the tool, but if you want to know what's going on under the hood:

- **Filenames** are `{title-slug}-{id-hash}.epub`. The slug is for you to read; the hash keeps the filename stable even if the article's title changes upstream, so edits overwrite the same file.
- **Edit detection** works by fingerprinting each article's content (a SHA-256 of the title plus cleaned-up body) and comparing it to last time. A changed fingerprint means a genuine edit, not just a feed reshuffling its tracking tokens.
- **The catalog** (`catalog.db`) is a small SQLite file remembering every article it has processed — the fingerprint, the filename, and timestamps. It's how the tool knows what's new. To force a re-render, delete the relevant row (or the whole file) and run again. Already-written EPUBs are never auto-deleted; the lookback window only controls what gets *re-checked*, not what stays on disk.

## Project layout

```
rss2epub/
  __main__.py   CLI + orchestration
  config.py     config loading, lookback parsing, secret resolution
  freshrss.py   feed-reader client (auth, fetch, pagination)
  epub.py       HTML cleanup, stable filenames, EPUB building
  catalog.py    SQLite catalog
```

## Tests

```bash
uv run pytest tests/ -v
```
