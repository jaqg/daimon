#!/usr/bin/env python3
"""yt_locate.py - transcript segments + keywords -> candidate windows with timestamps.

Deterministic prefilter only (no model calls): scores transcript segments by
keyword hits, merges nearby hits into windows (plus gap-bridging non-matching
segments for readable context), ranks by total hits.

Input: JSON from yt_transcript.py ({"segments": [...], ...}) or a bare list
of {"start_s", "end_s", "text"} objects.

Output (stdout, JSON):
  {"video_id", "url", "keywords", "n_segments", "windows":
     [{"start_s", "end_s", "link", "score", "density_per_min", "hits", "excerpt"}]}
  window bounds are exact segment boundaries; link is
  https://youtu.be/ID?t=SECS ready for markdown reports.
"""

import argparse
import json
import re
import sys
from pathlib import Path

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "to", "in",
    "on", "at", "by", "for", "with", "about", "as", "is", "are", "was", "were",
    "be", "been", "it", "its", "this", "that", "these", "those", "from", "into",
    "how", "what", "why", "when", "where", "who", "which", "do", "does", "did",
    "can", "could", "should", "would", "will", "i", "you", "we", "they", "he",
    "she", "my", "your", "our", "their", "me", "us", "them", "not", "no", "yes",
    "video", "talk", "talks", "lecture", "tutorial",
}


def load_segments(path: Path) -> tuple[list[dict], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data if isinstance(data, dict) else {}
    segs = data.get("segments", []) if isinstance(data, dict) else data
    segs = [
        {
            "start_s": float(s["start_s"]),
            "end_s": float(s.get("end_s", s["start_s"])),
            "text": s.get("text", ""),
        }
        for s in segs
        if s.get("text")
    ]
    segs.sort(key=lambda s: s["start_s"])
    return segs, meta


def parse_keywords(query: str, phrases: list[str]) -> list[str]:
    kws = [p.strip().lower() for p in phrases if p.strip()]
    joined = " ".join(kws)
    seen = set()
    for w in re.findall(r"[a-z0-9][a-z0-9'-]*", query.lower()):
        if w in seen or len(w) <= 2 or w in STOPWORDS:
            continue
        if w in joined:  # already counted via a phrase
            continue
        kws.append(w)
        seen.add(w)
    return kws


def score_segments(segs: list[dict], keywords: list[str]) -> list[dict]:
    for s in segs:
        text = s["text"].lower()
        hits = {}
        score = 0
        for kw in keywords:  # phrases are exact substrings; single words too
            n = text.count(kw)
            if n:
                weight = 2 if " " in kw else 1
                hits[kw] = n
                score += n * weight
        s["score"], s["hits"] = score, hits
    return segs


def build_windows(segs: list[dict], merge_gap: float, top_k: int) -> list[dict]:
    """Group matching segments; bridge non-matching ones only while the time
    since the LAST MATCH stays <= merge_gap (otherwise contiguous transcripts
    would collapse into one window)."""
    windows, cur = [], None
    for s in segs:
        if s["score"] > 0:
            if cur is None or s["start_s"] - cur["last_match_end"] > merge_gap:
                if cur:
                    windows.append(cur)
                cur = {"segs": [], "hits": {}, "score": 0, "last_match_end": 0.0}
            cur["segs"].append(s)
            cur["score"] += s["score"]
            for k, v in s["hits"].items():
                cur["hits"][k] = cur["hits"].get(k, 0) + v
            cur["last_match_end"] = s["end_s"]
        elif cur is not None and s["start_s"] - cur["last_match_end"] <= merge_gap:
            cur["segs"].append(s)  # context bridge right after a match
    if cur:
        windows.append(cur)

    ranked = sorted(windows, key=lambda w: w["score"], reverse=True)[:top_k]

    out = []
    for w in ranked:
        ordered = sorted(w["segs"], key=lambda s: s["start_s"])
        start, end = ordered[0]["start_s"], ordered[-1]["end_s"]
        excerpt = " ".join(s["text"] for s in ordered).strip()
        if len(excerpt) > 400:
            excerpt = excerpt[:400].rsplit(" ", 1)[0] + " ..."
        dur_min = max((end - start) / 60.0, 1e-6)
        out.append(
            {
                "start_s": round(start, 1),
                "end_s": round(end, 1),
                "score": w["score"],
                "density_per_min": round(w["score"] / dur_min, 2),
                "hits": dict(sorted(w["hits"].items(), key=lambda kv: -kv[1])),
                "excerpt": excerpt,
            }
        )
    out.sort(key=lambda w: (-w["score"], -w["density_per_min"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments", required=True, help="JSON from yt_transcript.py")
    ap.add_argument("--query", default="", help="free-text topic -> term keywords")
    ap.add_argument("--keywords", default="",
                    help="exact phrases, ';'-separated (weighted 2x)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--merge-gap", type=float, default=15.0,
                    help="max time (s) since last match before a window closes")
    args = ap.parse_args()

    segs, meta = load_segments(Path(args.segments))
    if not segs:
        print("no segments in input", file=sys.stderr)
        return 1
    phrases = [p for p in args.keywords.split(";") if p.strip()]
    keywords = parse_keywords(args.query, phrases)
    if not keywords:
        print("no keywords after stopword removal", file=sys.stderr)
        return 1

    score_segments(segs, keywords)
    windows = build_windows(segs, args.merge_gap, args.top)

    video_id = meta.get("video_id")
    url = meta.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else None)
    for w in windows:
        t = int(w["start_s"])
        w["link"] = f"https://youtu.be/{video_id}?t={t}" if video_id else None

    out = {
        "video_id": video_id,
        "url": url,
        "keywords": keywords,
        "n_segments": len(segs),
        "n_windows": len(windows),
        "windows": windows,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
