#!/usr/bin/env python3
"""merge-status — roll worker status deltas into the brain's ≤15-line part rollup.

Deterministic on purpose: an LLM transcribing deltas costs cold input and invents summaries.
This script only moves text that already exists.

    <repo>/.agent/status/<date>-<part>.<agent>.md   (append-only, one writer per file)
        ->  <vault_project>/status/<part>.md        (rewrite, <=15 lines, permanent)
        ->  same delta renamed *.md.processed       (consumed; dies with its worktree)

Usage
  merge-status.py [--repo PATH] [--part NAME] [--dry-run] [--max-lines 15] [--force]
Reads <repo>/.agent-paths for vault_project / status_dir / integration_branch. Exit 0 = rollup
written (or would be, under --dry-run). Exit 3 = nothing to do. Exit 4 = contract broken
(no .agent-paths, no status dir, unparseable delta names) — it never guesses a destination.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

# `<date>-<part>.<agent>.md`, and the dot is load-bearing: with a hyphen join the parser cannot tell
# where a hyphenated part ends and a hyphenated agent begins. Measured 2026-10-25 — a delta named
# `2026-10-25-structure-vault-gitignore.md` (part `structure`, agent `vault-gitignore`) rolled up as
# part `structure-vault`, agent `gitignore`, so it wrote a status file for a part that does not exist.
# `.processed` is accepted here as well, because --force rebuilds from files this script itself renamed.
DELTA_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<part>[^.]+)\.(?P<agent>[^.]+)\.md(?:\.processed)?$")
# Keywords a delta line can start with (worker.md format is lowercase, agents shout sometimes).
KWS = ("done", "blocked", "next", "debt", "evidence", "risks", "tests", "status")


def die(code: int, msg: str) -> None:
    print(f"merge-status: {msg}", file=sys.stderr)
    raise SystemExit(code)


def read_paths(repo: Path) -> dict:
    f = repo / ".agent-paths"
    if not f.exists():
        die(4, f"{f} missing — run `worktree.sh init` first (the brain owns this file).")
    out = {}
    for line in f.read_text().splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    for req in ("vault_project", "status_dir"):
        if req not in out:
            die(4, f"{f} has no `{req}:` key")
    return out


def branch_of(repo: Path, part: str) -> list[str]:
    """Branches that belong to this part, straight from git (no side ledger to drift)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "branch", "--list", f"agent/{part}-*", "--format=%(refname:short)"],
            capture_output=True, text=True,
        )
    except OSError:
        return []
    return sorted(l for l in r.stdout.split() if l)


def parse_delta(p: Path) -> tuple[str, str, list[str]]:
    """(part, agent, content lines). Filename is the contract; a bad name is an error, not a shrug."""
    m = DELTA_RE.match(p.name)
    if not m:
        die(4, f"delta {p.name} does not match <YYYY-MM-DD>-<part>.<agent>.md — rename it, do not let it slide")
    lines = [l.rstrip() for l in p.read_text(errors="replace").splitlines() if l.strip()]
    return m.group("part"), m.group("agent"), lines


def digest(lines: list[str], cap: int = 96) -> dict:
    """One line per keyword, first occurrence wins; counts stay honest even when we truncate text."""
    found: dict[str, str] = {}
    counts: dict[str, int] = {}
    for l in lines:
        body = re.sub(r"^[-*#\s]*(?:###\s*)?", "", l)
        low = body.lower()
        for kw in KWS:
            if low.startswith(kw) and ( ":" in body or " " in body[kw : kw + 2]):
                text = body.split(":", 1)[1].strip() if ":" in body else body[len(kw):].strip(" ·-")
                if re.fullmatch(r"none|nothing|n/?a|no|–|-+|\.", text, re.I):
                    break  # "blocked: nothing" is a non-finding; do not surface or count it
                counts[kw] = counts.get(kw, 0) + 1
                found.setdefault(kw, (text[: cap - 1] + "…") if len(text) > cap else text)
                break
    return {"found": found, "counts": counts}


def _git_out(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()


def integ_note(repo: Path, integ: str, branches: list[str], part: str) -> str:
    """Answer item 4 of the /merge-status contract *inside* the allowed script: the brain cannot run
    `git branch --list` (its tier denies bash by design), so existence and merged-ness have to come out
    of the rollup. Deterministic, positional, no prose interpretation."""
    if not integ:
        return "unset — contract has no integration_branch (run `worktree.sh init --part <part>`)"
    if not _git_out(repo, "branch", "--list", integ):
        return f"{integ} (MISSING — `worktree.sh integrate --repo <repo> --part {part}` has not run)"
    merged = [b for b in branches
              if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", b, integ],
                                 capture_output=True).returncode == 0]
    back = [b for b in branches if b not in merged]
    tail = f" — not yet in it: {', '.join(back)}" if back else ""
    return f"{integ} (EXISTS, {len(merged)}/{len(branches)} agent branches merged{tail})"


def build_rollup(part: str, per_agent: list[tuple[str, str, dict]], branches: list[str],
                 integ: str, max_lines: int, note: str = "") -> list[str]:
    tot: dict[str, int] = {}
    for _, _, d in per_agent:
        for k, v in d["counts"].items():
            tot[k] = tot.get(k, 0) + v
    head = [
        f"# {part} — status (rolled up {dt.datetime.now():%Y-%m-%d %H:%M} by merge-status)",
        f"deltas: {len(per_agent)} · agents: {', '.join(sorted({a for _, a, _ in per_agent})) or '—'}",
        "tally: " + " · ".join(f"{k.upper()} {tot.get(k, 0)}" for k in ("done", "blocked", "debt")) or "tally: —",
    ]
    rows = []
    for f_path, agent, d in per_agent:
        g = d["found"]
        seg = f"- {agent}: {g.get('done', '(no done line)')}"
        if "tests" in g:
            seg += f" [tests: {g['tests']}]"
        rows.append(seg[:150])
        if "blocked" in g:
            rows.append(f"- BLOCKED({agent}): {g['blocked'][:120]}")
        if "debt" in g:
            rows.append(f"- DEBT({agent}): {g['debt'][:100]}")
    tail = []
    nxt = [d["found"].get("next") for _, _, d in per_agent if "next" in d["found"]]
    if nxt:
        tail.append(f"- next: {nxt[0][:120]}" + (f" (+{len(nxt) - 1} more)" if len(nxt) > 1 else ""))
    tail.append(f"- branches: {', '.join(branches) or 'none'} · integration: {note or integ or 'unset'}")

    out = head + rows + tail
    if len(out) > max_lines:
        # Order of sacrifice: tail is load-bearing, tally is load-bearing, agent lines are not.
        keep = head[:1] + head[2:]
        room = max_lines - len(keep) - len(tail)
        dropped = len(rows) - max(room, 0)
        out = keep + rows[: max(room, 0)] + [f"- …{dropped} more agent lines in the processed deltas"] + tail
    return out[:max_lines]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--part")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-lines", type=int, default=15)
    ap.add_argument("--force", action="store_true", help="rewrite the rollup even with no new deltas")
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    paths = read_paths(repo)
    status_dir = Path(paths["status_dir"]).expanduser()
    if not status_dir.is_dir():
        die(4, f"status_dir {status_dir} does not exist (create it or fix .agent-paths)")
    src = repo / ".agent" / "status"
    if not src.is_dir():
        print(f"merge-status: no {src} — nothing rolled up (workers have not reported)")
        raise SystemExit(3)

    deltas = sorted(p for p in src.glob("*.md") if not p.name.endswith(".processed"))
    if not deltas:
        if not a.force:
            print("merge-status: 0 unprocessed deltas (use --force to rebuild from .processed)")
            raise SystemExit(3)
        # --force = rebuild the rollup from what was already consumed, marking nothing new.
        deltas = sorted(src.glob("*.md.processed"))
    consumed = [p for p in deltas if not p.name.endswith(".processed")]

    by_part: dict[str, list[tuple[Path, str, dict]]] = {}
    for p in deltas:
        part, agent, lines = parse_delta(p)
        by_part.setdefault(part, []).append((p, agent, digest(lines)))

    if a.part:
        by_part = {k: v for k, v in by_part.items() if k == a.part}
        if not by_part:
            die(3, f"no unprocessed deltas for part {a.part!r}")

    integ = paths.get("integration_branch", "")
    for part, ds in by_part.items():
        brs = branch_of(repo, part)
        rollup = build_rollup(part, ds, brs, integ, a.max_lines,
                              integ_note(repo, integ, brs, part))
        dst = status_dir / f"{part}.md"
        print(f"=== {dst} ({len(rollup)} lines, {len(ds)} deltas consumed)")
        for l in rollup:
            print(l)
        if a.dry_run:
            continue
        dst.write_text("\n".join(rollup) + "\n")
    if not a.dry_run:
        for p in consumed:
            p.rename(p.with_name(p.name + ".processed"))
    if a.dry_run:
        print("--- dry run: nothing written, no delta marked .processed")


if __name__ == "__main__":
    main()
