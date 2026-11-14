---
name: yt-research
description: >
  Research YouTube by topic or by video via transcripts, with timestamps for the parts you care
  about. Use when the user says: "research youtube on X", "find videos about X", "search youtube
  for X", "youtube search", "get the transcript of [url]", "transcript of this video",
  "summarize this youtube video", "where in the video does it mention X", "timestamps for X",
  "which parts of the video cover X", "find the section about X in [url]", "yt-research",
  or shares a youtu.be/youtube.com link asking what's in it.
tools: Bash, Read, Write
---

# yt-research

YouTube discovery + timed transcripts → candidate windows with timestamps → you judge relevance
and render a report. Deterministic work stays in scripts; you only judge and write prose.

## Dependencies (install once, machine-level)

```bash
uv tool install yt-dlp                            # binary → ~/.local/bin
pip install --user --break-system-packages youtube-transcript-api
# plain `pip install --user` fails on PEP 668 "externally managed" Pythons (Debian/Ubuntu);
# --user only writes ~/.local/lib — safe. Or: uv pip install --python python3 youtube-transcript-api
```

Both sources are optional per stage — scripts fall back automatically:

| Stage | Primary | Fallback |
|---|---|---|
| Topic search | YouTube Data API v3 (`YOUTUBE_API_KEY`) | `yt-dlp "ytsearchN:"` |
| Transcript | `youtube-transcript-api` | `yt-dlp` caption download (json3 → vtt) |

## Config keys (optional — sourced from config.local)

```bash
YOUTUBE_API_KEY   # YouTube Data API v3; free 10k units/day = 100 searches;
                  # console.cloud.google.com → enable YouTube Data API v3 → Credentials.
                  # Unset/empty → yt-dlp search fallback (no key, no quota).
```

```bash
# $SKILL_DIR = directory of this SKILL.md (symlink-verify: readlink -f "$SKILL_MD")
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
CONFIG="$SKILL_DIR/../../../config/config.local"
[[ -f "$CONFIG" ]] && source "$CONFIG"
SCRIPTS="$SKILL_DIR/scripts"
```

Scripts also read `YOUTUBE_API_KEY` from `config.local` themselves if the env var is unset, so
sourcing above is belt-and-braces.

## Outputs (all under gitignored `../yt-research-workspace/`)

```
literature/skills/yt-research-workspace/
  search-<slug>.json          # yt_search.py output
  <video_id>.<lang>.json      # transcript cache (auto)
  report-<slug>.md            # your final human-readable report
```

Never write to vault notes or any user file without showing a diff/preview first
(AGENTS.md approval-gate rule). Workspace scratch needs no approval.

## Step A — research by topic

1. **Search** (script):
   ```bash
   WS="$SKILL_DIR/../yt-research-workspace"; mkdir -p "$WS"
   python3 "$SCRIPTS/yt_search.py" --query "<topic>" --max-results 10 \
       [--require-captions] [--months 12] > "$WS/search-<slug>.json"
   ```
   `--require-captions` guarantees the transcript stage will work. Check `api_error` in the
   output: if it's set, results came from the yt-dlp fallback — say so in the report.

2. **Judge** (you): read `videos[]`, rank by title/channel/views/duration against the user's
   intent, pick 1–3 videos. Show the user your picks (title + url + one-line why) before
   spending transcript calls if the request was vague.

3. **Transcript** per picked video → **locate** (scripts): go to Step C.

## Step B — research by video (user gave a URL/ID)

Skip Step A. Extract video ID from the URL yourself or let `yt_transcript.py` do it — it accepts
URLs directly.

## Step C — transcript + locate (both scripts)

```bash
python3 "$SCRIPTS/yt_transcript.py" "<url-or-id>" --lang en > "$WS/<video_id>.en.json"
python3 "$SCRIPTS/yt_locate.py" --segments "$WS/<video_id>.en.json" \
    --keywords "phrase one;phrase two" --query "<free-text topic words>" \
    > "$WS/locate-<video_id>.json"
```

- `--keywords`: exact multi-word phrases, `;`-separated, weighted 2×.
- `--query`: loose topic words; stopwords are dropped automatically.
- Output `windows[]` is pre-sorted by score; each window carries `start_s`, `end_s`, `hits`,
  `excerpt`, and a ready-made `link` (`https://youtu.be/ID?t=SECS`).

## Step D — judge relevance (you) and report

1. Read `windows[]` — each already has excerpt + hit counts. **Discard windows irrelevant to the
   user's actual interest**, re-rank the survivors by the user's intent (not by keyword score),
   and merge/rename as needed. This is the only judgment step; do not re-read the raw transcript
   unless an excerpt is too truncated to decide.
2. Verify every timestamp you emit comes from a window's `start_s`/`link` — **never invent or
   recompute timestamps**.
3. Render the report (markdown) with clickable links:

   ```markdown
   # <topic> — YouTube research (YYYY-MM-DD)
   ## Picked videos
   | video | channel | dur | why |
   ## Timestamped parts
   | t | excerpt | link |
   |---|---|---|
   | 12:04 | "…" | https://youtu.be/ID?t=724 |
   ```
   Format `t` as `MM:SS`/`H:MM:SS` from `start_s` (script-side: `printf`/`date -d` style math or
   do it in one line of python — no new files).
4. State coverage honestly: source used (`google_api`/`yt_dlp`), captions source, fallbacks hit,
   videos skipped for missing captions.

Save report to `$WS/report-<slug>.md`. Only copy into the vault on explicit user request
(with preview).

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `api_error: ... quotaExceeded` | 100 searches/day used | Expected — fallback already ran; or wait/reset |
| `RequestBlocked`/`IpBlocked` | IP blocked by YT | Fallback to yt-dlp happens automatically; if both fail, retry later |
| `no captions found` | Video truly has none | Use another video (`--require-captions` on search prevents this) |
| `yt-dlp not found on PATH` | Not installed | `uv tool install yt-dlp` (or `pip install --user --break-system-packages yt-dlp`) |

## Tests

```bash
python3 "$SKILL_DIR/scripts/selftest.py"    # offline, fixture-based, no network
```

Script layer: `selftest.py` + `evals/fixtures/`. Model layer: `evals/evals.json`.
