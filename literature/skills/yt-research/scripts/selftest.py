#!/usr/bin/env python3
"""Offline selftest for yt-research scripts (fixtures only, no network).

Run: python3 scripts/selftest.py
Exit 0 = all assertions pass.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yt_locate
import yt_search
import yt_transcript

FIX = Path(__file__).resolve().parents[1] / "evals" / "fixtures"
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  ok  {name}")
    else:
        FAILURES.append(name)
        print(f" FAIL {name}  {detail}")


def test_locate():
    print("yt_locate:")
    segs, meta = yt_locate.load_segments(FIX / "transcript_sample.json")
    check("load_segments count", len(segs) == 12, f"got {len(segs)}")

    kws = yt_locate.parse_keywords(
        "what is the density functional theory for adsorption energy", []
    )
    check(
        "parse_keywords drops stopwords",
        {"what", "is", "the", "for"} .isdisjoint(kws),
        f"kws={kws}",
    )
    check("parse_keywords keeps terms", {"density", "functional", "theory", "adsorption"} <= set(kws))

    yt_locate.score_segments(segs, kws)
    windows = yt_locate.build_windows(segs, merge_gap=15.0, top_k=10)
    check("two windows found", len(windows) == 2, f"got {len(windows)}")
    if len(windows) != 2:
        return
    w1, w2 = windows
    # note: substring counting means "functional" also hits "functionals"
    check("w1 ranked first (score 8)", w1["score"] == 8, f"got {w1['score']}")
    check("w1 starts at 20.0", w1["start_s"] == 20.0, f"got {w1['start_s']}")
    check("w1 ends at 66.0", w1["end_s"] == 66.0, f"got {w1['end_s']}")
    check("w2 score 6", w2["score"] == 6, f"got {w2['score']}")
    check("w2 starts at 66.0", w2["start_s"] == 66.0, f"got {w2['start_s']}")
    check("w1 hits include functional", w1["hits"].get("functional", 0) >= 3, str(w1["hits"]))
    check("excerpt non-empty", len(w1["excerpt"]) > 50)

    # end-to-end through main(): link format
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "yt_locate.py"),
            "--segments", str(FIX / "transcript_sample.json"),
            "--keywords", "adsorption energy;density functional theory",
        ],
        capture_output=True, text=True,
    )
    check("locate CLI exit 0", proc.returncode == 0, proc.stderr.strip())
    out = json.loads(proc.stdout)
    check("CLI link format", out["windows"][0]["link"] ==
          "https://youtu.be/dQw4w9WgXcQ?t=20", str(out["windows"][0].get("link")))


def test_parsers():
    print("yt_transcript parsers:")
    segs = yt_transcript.parse_vtt((FIX / "captions_sample.vtt").read_text())
    check("vtt: 3 segments after dedupe", len(segs) == 3, f"got {len(segs)}")
    if segs:
        check("vtt: rolling duplicate merged", segs[0]["end_s"] == 8.0, str(segs[0]))
        check("vtt: tags stripped", segs[0]["text"] == "Welcome to the lecture on catalysts.", segs[0]["text"])
        check("vtt: entities decoded", "&" in segs[-1]["text"] and "&amp;" not in segs[-1]["text"])

    segs = yt_transcript.parse_json3((FIX / "captions_sample.json3").read_text())
    check("json3: 3 segments (empty event skipped)", len(segs) == 3, f"got {len(segs)}")
    if len(segs) == 3:
        check("json3: start times", segs[0]["start_s"] == 0.0 and segs[1]["start_s"] == 4.0)
        check("json3: merged segs text", "Sabatier principle" in segs[1]["text"], segs[1]["text"])
        check("json3: end_s present", segs[2]["end_s"] == 14.0, str(segs[2]))

    vid = yt_transcript.extract_video_id
    check("id from short url", vid("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ")
    check("id from watch url + t", vid("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=20") == "dQw4w9WgXcQ")
    check("bare id", vid("dQw4w9WgXcQ") == "dQw4w9WgXcQ")
    try:
        vid("https://www.youtube.com/playlist?list=PL123")
        check("bad url rejected", False)
    except SystemExit:
        check("bad url rejected", True)


def test_search_helpers():
    print("yt_search helpers:")
    d = yt_search.iso8601_duration
    check("PT1H2M3S", d("PT1H2M3S") == 3723)
    check("PT13M5S", d("PT13M5S") == 785)
    check("PT45S", d("PT45S") == 45)
    check("empty -> None", d("") is None)
    check("P0D -> 0 s", d("P0D") == 0)
    check("garbage -> None", d("notaduration") is None)


def main():
    test_locate()
    test_parsers()
    test_search_helpers()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
