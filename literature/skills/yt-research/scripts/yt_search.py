#!/usr/bin/env python3
"""yt_search.py — topic query -> ranked YouTube video list (JSON).

Search sources, in order:
  1. YouTube Data API v3 (needs YOUTUBE_API_KEY in config.local / env).
  2. yt-dlp "ytsearchN:" — used when no key, quota exhausted, or API error.

Output (stdout, JSON):
  {"query", "source": "google_api"|"yt_dlp", "captions_filter_applied": bool,
   "api_error": str|None, "videos": [{"video_id", "title", "channel",
   "published_at", "duration_s", "views", "captions", "url"}]}

No third-party deps for the Google path (stdlib urllib only).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_BASE = "https://www.googleapis.com/youtube/v3"


class ApiError(RuntimeError):
    pass


def load_api_key() -> str:
    """Env first (SKILL.md sources config.local), then parse config.local directly."""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        return key
    # scripts/ -> yt-research/ -> skills/ -> literature/ -> repo root
    cfg = Path(__file__).resolve().parents[4] / "config" / "config.local"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("YOUTUBE_API_KEY="):
                val = line.split("=", 1)[1].split("#", 1)[0].strip()
                return val.strip("\"'")
    return ""


def iso8601_duration(d: str) -> int | None:
    """PT4H13M2S -> seconds."""
    m = re.fullmatch(
        r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", d or ""
    )
    if not m or not any(m.groups()):
        return None
    days, hours, mins, secs = (int(g) if g else 0 for g in m.groups())
    return days * 86400 + hours * 3600 + mins * 60 + secs


def _http_get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            reason = json.loads(body)["error"]["message"]
        except Exception:
            reason = body[:300]
        raise ApiError(f"HTTP {e.code}: {reason}") from e
    except urllib.error.URLError as e:
        raise ApiError(f"network error: {e.reason}") from e


def search_google(
    query: str, max_results: int, require_captions: bool, months: int, key: str
) -> list[dict]:
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": str(min(max_results, 50)),
        "order": "relevance",
        "key": key,
    }
    if require_captions:
        params["videoCaption"] = "closedCaption"
    if months > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
        params["publishedAfter"] = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = _http_get(f"{API_BASE}/search?{urllib.parse.urlencode(params)}")
    items = data.get("items", [])
    ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    if not ids:
        return []

    vdata = _http_get(
        f"{API_BASE}/videos?"
        + urllib.parse.urlencode(
            {"part": "snippet,contentDetails,statistics", "id": ",".join(ids), "key": key}
        )
    )
    by_id = {v["id"]: v for v in vdata.get("items", [])}

    videos = []
    for vid in ids:  # preserve relevance order from search.list
        v = by_id.get(vid)
        if not v:
            continue
        sn, cd, st = v.get("snippet", {}), v.get("contentDetails", {}), v.get("statistics", {})
        videos.append(
            {
                "video_id": vid,
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "published_at": sn.get("publishedAt", "")[:10],
                "duration_s": iso8601_duration(cd.get("duration", "")),
                "views": int(st.get("viewCount", 0) or 0),
                "captions": cd.get("caption") == "true",
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return videos


def search_ytdlp(
    query: str, max_results: int, require_captions: bool
) -> list[dict]:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp not found on PATH (pip install yt-dlp)")
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--playlist-end",
        str(max_results),
        "--skip-download",
    ]
    if not require_captions:
        cmd.append("--flat-playlist")  # fast metadata-only; captions stay unknown
    cmd.append(f"ytsearch{max_results}:{query}")

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {proc.stderr.strip()[:500]}")
    entries = json.loads(proc.stdout).get("entries") or []

    videos = []
    for e in entries:
        if not e or not e.get("id"):
            continue
        upload = e.get("upload_date") or ""  # YYYYMMDD (absent in flat mode)
        has_caps = bool(e.get("subtitles") or e.get("automatic_captions"))
        flat = not require_captions
        if require_captions and not has_caps:
            continue  # full extraction ran; enforce filter ourselves
        captions = None if flat else has_caps
        videos.append(
            {
                "video_id": e["id"],
                "title": e.get("title", ""),
                "channel": e.get("channel") or e.get("uploader") or "",
                "published_at": (
                    f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else None
                ),
                "duration_s": e.get("duration"),
                "views": e.get("view_count"),
                "captions": captions,
                "url": f"https://www.youtube.com/watch?v={e['id']}",
            }
        )
    return videos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True)
    ap.add_argument("--max-results", type=int, default=10)
    ap.add_argument("--require-captions", action="store_true",
                    help="only videos with (manual or auto) captions")
    ap.add_argument("--months", type=int, default=0,
                    help="restrict to last N months (Google API only)")
    args = ap.parse_args()

    source, api_error, videos = "yt_dlp", None, []
    key = load_api_key()
    if key:
        try:
            videos = search_google(
                args.query, args.max_results, args.require_captions, args.months, key
            )
            source = "google_api"
        except ApiError as e:
            api_error = str(e)
    else:
        api_error = "YOUTUBE_API_KEY not set"

    if not videos:  # no key, API error, or zero results -> try yt-dlp
        try:
            videos = search_ytdlp(
                args.query, args.max_results, args.require_captions
            )
            source = "yt_dlp"
        except Exception as e:
            print(
                f"search failed: google=({api_error}); yt-dlp=({e})", file=sys.stderr
            )
            return 1

    out = {
        "query": args.query,
        "source": source,
        "api_error": api_error if source == "yt_dlp" else None,
        "captions_filter_applied": args.require_captions and (
            source == "google_api" or videos[0]["captions"] is not None
        ),
        "n_results": len(videos),
        "videos": videos,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
