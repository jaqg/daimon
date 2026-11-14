#!/usr/bin/env python3
"""yt_transcript.py - YouTube URL/video-ID -> timed transcript segments (JSON).

Transcript sources, in order:
  1. youtube-transcript-api (pip install youtube-transcript-api)
  2. yt-dlp caption download (json3, then vtt) - used on import error,
     block/HTTP errors, or --source ytdlp.

Output (stdout, JSON):
  {"video_id", "url", "language", "source",
   "duration_s", "segment_count",
   "segments": [{"start_s", "end_s", "text"}]}

Caches successful results in <workspace>/cache/<video_id>.<lang>.json
(use --no-cache to bypass).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_LANG = "en"


def extract_video_id(raw: str) -> str:
    raw = raw.strip()
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", raw):
        return raw
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([0-9A-Za-z_-]{11})", raw)
    if m:
        return m.group(1)
    raise SystemExit(f"cannot extract 11-char video id from: {raw!r}")


def build_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ---------------------------------------------------------------- youtube-transcript-api

def fetch_via_yta(video_id: str, lang: str) -> list[dict] | None:
    """Returns segments or None if the lib is unusable (missing/blocked/failed)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        if hasattr(YouTubeTranscriptApi(), "fetch"):  # v1.x instance API
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=[lang])
            raw = [(f.start, f.duration, f.text) for f in fetched]
        else:  # v0.x static API
            raw = [
                (d["start"], d["duration"], d["text"])
                for d in YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
            ]
    except Exception as e:  # blocked IP, no transcript, network - all -> fallback
        print(f"youtube-transcript-api failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    return [
        {"start_s": round(s, 3), "end_s": round(s + d, 3), "text": t.strip()}
        for s, d, t in raw
        if t.strip()
    ]


# ---------------------------------------------------------------- yt-dlp caption download

def parse_json3(text: str) -> list[dict]:
    """YouTube json3 caption dump -> segments."""
    data = json.loads(text)
    segs = []
    for ev in data.get("events", []):
        parts = [s.get("utf8", "") for s in ev.get("segs", [])]
        content = "".join(parts).replace("\n", " ").strip()
        if not content:
            continue
        start = ev.get("tStartMs", 0) / 1000.0
        dur = ev.get("dDurationMs", 0) / 1000.0
        segs.append(
            {"start_s": round(start, 3), "end_s": round(start + dur, 3), "text": content}
        )
    return _dedupe(segs)


def parse_vtt(text: str) -> list[dict]:
    """WebVTT -> segments, merging rolling auto-caption duplicates."""
    segs = []
    ts = re.compile(
        r"(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})"
    )

    def to_s(h, m, sec, ms) -> float:
        h = int(h.rstrip(":")) if h else 0
        return h * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0

    cur = None
    for line in text.splitlines():
        line = line.strip()
        m = ts.search(line)
        if m:
            if cur:
                segs.append(cur)
            cur = {
                "start_s": round(to_s(m.group(1), m.group(2), m.group(3), m.group(4)), 3),
                "end_s": round(to_s(m.group(5), m.group(6), m.group(7), m.group(8)), 3),
                "text": "",
            }
            continue
        if cur is None or not line or line in ("WEBVTT", "Kind: captions", "Language: en"):
            continue
        if line.startswith(("NOTE", "STYLE")):
            continue
        clean = re.sub(r"<[^>]+>", "", line)  # strip <c>, word timings
        clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        clean = clean.replace("&#39;", "'").replace("&quot;", '"').strip()
        if not clean:
            continue
        if clean == cur["text"]:  # rolling window repeated the line: extend, not duplicate
            continue
        cur["text"] = f"{cur['text']} {clean}".strip() if cur["text"] else clean
    if cur:
        segs.append(cur)
    return _dedupe([s for s in segs if s["text"]])


def _dedupe(segs: list[dict]) -> list[dict]:
    out = []
    for s in segs:
        if out and s["text"] == out[-1]["text"]:
            out[-1]["end_s"] = s["end_s"]
            continue
        out.append(s)
    return out


def fetch_via_ytdlp(video_id: str, lang: str) -> list[dict]:
    if not shutil.which("yt-dlp"):
        raise SystemExit(
            "no transcript: youtube-transcript-api unusable and yt-dlp not on PATH "
            "(pip install yt-dlp youtube-transcript-api)"
        )
    url = build_url(video_id)
    with tempfile.TemporaryDirectory(prefix="yt-research-") as tmp:
        for fmt in ("json3", "vtt"):
            proc = subprocess.run(
                [
                    "yt-dlp", "--skip-download",
                    "--write-subs", "--write-auto-subs",
                    "--sub-langs", lang, "--sub-format", fmt,
                    "-o", f"{tmp}/%(id)s.%(ext)s", url,
                ],
                capture_output=True, text=True, timeout=120,
            )
            files = sorted(Path(tmp).glob(f"{video_id}*.{fmt}"))
            if files:
                content = files[0].read_text(encoding="utf-8")
                segs = parse_json3(content) if fmt == "json3" else parse_vtt(content)
                if segs:
                    return segs
            if proc.returncode != 0 and fmt == "json3":
                print(f"yt-dlp: {proc.stderr.strip()[:300]}", file=sys.stderr)
    raise SystemExit(f"no captions found for {video_id} (lang={lang})")


# ---------------------------------------------------------------- cache + main

def cache_path(cache_dir: Path, video_id: str, lang: str) -> Path:
    return cache_dir / f"{video_id}.{lang}.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", help="YouTube URL or 11-char video ID")
    ap.add_argument("--lang", default=DEFAULT_LANG)
    ap.add_argument("--source", choices=("auto", "yta", "ytdlp"), default="auto")
    ap.add_argument("--cache-dir", default=None,
                    help="transcript cache dir (default: skill workspace cache/)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    video_id = extract_video_id(args.video)
    default_cache = Path(__file__).resolve().parents[1] / ".." / "yt-research-workspace" / "cache"
    cache_dir = Path(args.cache_dir) if args.cache_dir else default_cache.resolve()

    if not args.no_cache:
        cp = cache_path(cache_dir, video_id, args.lang)
        if cp.is_file():
            sys.stdout.write(cp.read_text(encoding="utf-8"))
            return 0

    source, segments = None, None
    if args.source in ("auto", "yta"):
        segments = fetch_via_yta(video_id, args.lang)
        if segments:
            source = "youtube_transcript_api"
    if segments is None or args.source == "ytdlp":
        segments = fetch_via_ytdlp(video_id, args.lang)
        source = "yt_dlp_captions"

    duration = segments[-1]["end_s"] if segments else 0.0
    out = {
        "video_id": video_id,
        "url": build_url(video_id),
        "language": args.lang,
        "source": source,
        "duration_s": round(duration, 3),
        "segment_count": len(segments),
        "segments": segments,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if not args.no_cache:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path(cache_dir, video_id, args.lang).write_text(text, encoding="utf-8")
        except OSError as e:
            print(f"cache write failed: {e}", file=sys.stderr)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
