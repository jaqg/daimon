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
written or deltas consumed. Exit 3 = state unchanged (the rollup on disk already says what git says).
Exit 4 = contract broken (no .agent-paths, no status dir, unparseable delta names) — it never guesses a
destination.

It always reads the consumed deltas too, and always reports the part's git state. That is a fix, not a
feature: the first version returned early on "0 unprocessed deltas", so the rollup froze at whatever the
last delivery said and its most load-bearing line — how many agent branches are inside the integration
branch — went stale at the exact moment it changed. Measured 2026-10-26: the integrator had just merged
both slices (git says 2/2), the file still said 0/2, and the brain — obeying rule 3c, which forbids it
from inventing commands — recommended "delegate to integrator" on data that no longer existed.
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


def status_dir_of(paths: dict) -> Path:
    """Where the rollup goes, derived from the project dir EXACTLY ONCE.

    Live bug, measured twice 2026-10-28 in IQARIS-extension: a legacy .agent-paths held the relative
    `status_dir: 10-Projects/X/status`, and a brain running from `<vault>/10-Projects/X` got the
    rollup at `10-Projects/X/10-Projects/X/status/<part>.md` — the relative value resolved against a
    cwd that already sat inside the project. An absolute status_dir is trusted as-is; a relative one
    is joined onto vault_project, stripping the `10-Projects/<X>/` or `<X>/` prefix the legacy shape
    carries, so the project path appears exactly once no matter which of the two shapes the file has.
    """
    sd = Path(paths["status_dir"]).expanduser()
    if sd.is_absolute():
        return sd
    proj = Path(paths["vault_project"]).expanduser()
    rel = sd
    if rel.parts[:2] == ("10-Projects", proj.name):
        rel = Path(*rel.parts[2:])
    elif rel.parts[:1] == (proj.name,):
        rel = Path(*rel.parts[1:])
    return proj / rel


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
                if re.fullmatch(r"(?:none|nothing|n/?a|no|–|\-+|\.)[.:,\s—–\-]*", text, re.I):
                    break  # "blocked: nothing" is a non-finding; do not surface or count it
                if re.match(r"^(?:none|nothing|n/?a)(?:[.:,]|\s+[—–\-])", text, re.I):
                    # "blocked: none. Note: …" — a CLOSED blocker with context for the reader (the
                    # live case that asked the brain to "amend the spec — 1 BLOCKED" for zero
                    # blockers, 2026-10-28): keep it visible in the rollup, but it is not owed work,
                    # so it must not reach the tally or the next-command. "none of the tests pass"
                    # (space then a word) still counts as open.
                    found.setdefault(kw, (text[: cap - 1] + "…") if len(text) > cap else text)
                    break
                counts[kw] = counts.get(kw, 0) + 1
                found.setdefault(kw, (text[: cap - 1] + "…") if len(text) > cap else text)
                break
    return {"found": found, "counts": counts}


def _git_out(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()


def integ_note(repo: Path, integ: str, branches: list[str], part: str) -> tuple[str, str]:
    """Answer item 4 of the /merge-status contract *inside* the allowed script: the brain cannot run
    `git branch --list` (its tier denies bash by design), so existence and merged-ness have to come out
    of the rollup. Deterministic, positional, no prose interpretation.

    Returns (line, state). State is reported here and acted on in `next_commands`; keeping the two
    in sync by hand already failed once (the frozen 0/2 rollup), so this is the one place that
    decides whether a part still has work pending."""
    if not integ:
        return "unset — contract has no integration_branch (run `worktree.sh init --part <part>`)", "unset"
    if not _git_out(repo, "branch", "--list", integ):
        if not branches:
            # `prune` deletes the integration branch after a landing, so an absent branch with no agent
            # branches is the *finished* state — not an invitation to integrate a part that has no work.
            return (f"{integ} (absent) · no agent branches for this part — landed and pruned, or never "
                    f"started; main is the record", "no-work")
        return (f"{integ} (MISSING — `worktree.sh integrate --repo <repo> --part {part}` has not run)",
                "missing")
    merged = [b for b in branches
              if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", b, integ],
                                 capture_output=True).returncode == 0]
    back = [b for b in branches if b not in merged]
    tail = f" — not yet in it: {', '.join(back)}" if back else ""
    # Landed means the part's WORK is in main, not that the integration branch is an ancestor of it: an
    # untouched integration branch equals main, and the fixture caught this script calling an empty
    # scaffold "LANDED" with 0/1 merged. Requires every agent branch in main as well.
    if (branches and not back
            and all(subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", b, "main"],
                                   capture_output=True).returncode == 0 for b in branches)
            and subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", integ, "main"],
                                capture_output=True).returncode == 0):
        # Landed-ness belongs in the file, not only in the live commands: without it the rollup body is
        # byte-identical before and after José's merge, so landing reads as "nothing changed" to anyone
        # who opens the status dir tomorrow.
        return (f"{integ} (EXISTS, {len(merged)}/{len(branches)} agent branches merged · LANDED in main)",
                "landed")
    return f"{integ} (EXISTS, {len(merged)}/{len(branches)} agent branches merged{tail})", "exists"


def next_commands(repo: Path, part: str, integ: str, branches: list[str], blocked: int,
                  state: str) -> list[str]:
    """The commands, spelled out, for whoever has to act next.

    Why this lives in the script and not in the brain's prose: José should never have to remember a
    spawn command, and a brain that writes a command from memory can drift (wrong path, a flag that no
    longer exists) while still sounding confident. Machine-emitted here means the rollup and the
    instructions cannot disagree. `WT` is the brain's own allowed script, so it can paste its line back
    verbatim; the pane line is José's, because opening a pane is the one thing no agent may do for itself.
    """
    wt = "$HOME/.pi/agent/scripts/worktree.sh"
    if blocked:
        return [f"next-command[brain]: amend the {part} spec — {blocked} BLOCKED line(s); nothing to integrate yet"]
    if state == "no-work":
        # Nothing exists for this part: no slice branches, no integration branch. `integrate` would fail
        # (there is nothing to combine) and `add` needs a slice name this script cannot know, so the honest
        # answer is no command at all — the brain reports `no command for: <step>` instead of guessing.
        return []
    if state in ("missing", "unset"):
        return [
            f"next-command[brain]: bash {wt} integrate --repo {repo} --part {part}",
            f"next-command[operator]: pi-agents integrator --repo {repo}/.worktrees/integrate-{part}",
        ]
    if state == "landed":
        return [f"next-command[operator]: bash {wt} prune --repo {repo} --part {part}  ({integ} is already in main)"]
    merged = [b for b in branches
              if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", b, integ],
                                 capture_output=True).returncode == 0]
    if len(merged) < len(branches):
        back = [b for b in branches if b not in merged]
        return [
            f"next-command[operator]: pi-agents integrator --repo {repo}/.worktrees/integrate-{part}",
            f"  not yet in {integ}: {', '.join(back)}",
        ]
    # Ready to land, but the contract wants a checker that never shared a lab with the producers, so the
    # verify step is printed as a command too rather than left as something José has to remember.
    return [
        f"next-command[operator]: bash {wt} lab --repo {repo} --part {part}   # detached checkout for the verifier",
        f"next-command[operator]: pi-agents verifier --repo {repo}/.labs/{part}",
        f"next-command[operator, after reading the integrator's report (it has no write tool) and the verdict]: git -C {repo} merge --no-ff {integ}",
        f"next-command[operator]: bash {wt} prune --repo {repo} --part {part}",
    ]


def build_rollup(part: str, per_agent: list[tuple[str, str, dict]], branches: list[str],
                 integ: str, max_lines: int, note: str = "",
                 fresh: int | None = None, total: int | None = None) -> list[str]:
    tot: dict[str, int] = {}
    for _, _, d in per_agent:
        for k, v in d["counts"].items():
            tot[k] = tot.get(k, 0) + v
    n_total = len(per_agent) if total is None else total
    n_fresh = len(per_agent) if fresh is None else fresh
    agents = ", ".join(sorted({a for _, a, _ in per_agent})) or "—"
    dl = f"deltas: {n_total} · agents: {agents}"
    if n_total == 0:
        dl += " — no delivery records for this part yet"
    elif n_fresh == 0:
        dl += " — all consumed; git state below is live"
    head = [
        f"# {part} — status (rolled up {dt.datetime.now():%Y-%m-%d %H:%M} by merge-status)",
        dl,
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


def gather_deltas(src: Path) -> tuple[list[Path], list[Path]]:
    """(unprocessed, processed) with the current delivery winning per (part, agent).

    A worker can re-deliver the same slice on the same date — the queue is append-only, so the old record
    is history and the new one is the report. Keeping both would double-count the tally."""
    unproc = sorted(p for p in src.glob("*.md") if not p.name.endswith(".processed"))
    live = set()
    for p in unproc:
        m = DELTA_RE.match(p.name)
        if m:
            live.add((m.group("part"), m.group("agent")))
    proc = []
    # The same dedup applies WITHIN the processed set: a re-delivered slice leaves two .processed
    # files (one per date), and the older one used to resurrect its BLOCKED/DEBT lines into an empty
    # queue — the live "5 BLOCKED" on spawn-handoffs, 2026-10-28. Newest wins: date in the name,
    # then mtime for a same-day tie.
    newest: dict[tuple[str, str], Path] = {}
    for p in sorted(src.glob("*.md.processed")):
        m = DELTA_RE.match(p.name)
        if m and (m.group("part"), m.group("agent")) in live:
            continue
        if not m:
            proc.append(p)  # unmatched names die loudly in parse_delta; keep them here
            continue
        key = (m.group("part"), m.group("agent"))
        cur = newest.get(key)
        if cur is None or (p.name, p.stat().st_mtime) >= (cur.name, cur.stat().st_mtime):
            newest[key] = p
    proc = proc + sorted(newest.values())
    return unproc, proc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--part")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-lines", type=int, default=15)
    ap.add_argument("--force", action="store_true", help="rewrite the rollup even if it is unchanged")
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    paths = read_paths(repo)
    status_dir = status_dir_of(paths)
    if not status_dir.is_dir():
        die(4, f"status_dir {status_dir} does not exist (create it or fix .agent-paths; a relative "
               f"status_dir is derived from vault_project — `worktree.sh init --vault <abs vault path>` "
               f"pins both absolute)")
    src = repo / ".agent" / "status"
    if not src.is_dir():
        print(f"merge-status: no {src} — no queue yet. `worktree.sh add` symlinks it; until then nobody can report.")
        raise SystemExit(3)

    unproc, proc = gather_deltas(src)
    by_part: dict[str, list[tuple[Path, str, dict]]] = {}
    for p in unproc + proc:
        part, agent, lines = parse_delta(p)
        by_part.setdefault(part, []).append((p, agent, digest(lines)))

    # The part is reportable whether or not it has deltas: its branches and its integration state come
    # from git, and those are what the next command depends on. Without this, `/merge-status <part>` on a
    # fully consumed queue answered nothing at all.
    if a.part:
        if a.part not in by_part:
            by_part[a.part] = []
        by_part = {a.part: by_part[a.part]}

    contract_integ = paths.get("integration_branch", "")
    wrote = consumed_here = 0
    for part, ds in sorted(by_part.items()):
        integ = f"integration/{part}"
        brs = branch_of(repo, part)
        fresh = sum(1 for f_path, _, _ in ds if not f_path.name.endswith(".processed"))
        note, state = integ_note(repo, integ, brs, part)
        rollup = build_rollup(part, ds, brs, integ, a.max_lines, note, fresh=fresh, total=len(ds))
        dst = status_dir / f"{part}.md"
        print(f"=== {dst} ({len(rollup)} lines, {fresh} fresh / {len(ds) - fresh} consumed)")
        for l in rollup:
            print(l)
        # Not part of the rollup body: the rollup is a durable artifact, these are live instructions for
        # the terminal, and they would go stale the moment another branch lands.
        # counts, not found: a "blocked: none. Note: …" line is surfaced in the rollup but is not owed work
        blocked = sum(d["counts"].get("blocked", 0) for _, _, d in ds)
        if contract_integ and contract_integ != integ:
            print(f"note[drift]: .agent-paths integration_branch={contract_integ} is not this part's "
                  f"branch ({integ}); re-run worktree.sh init --repo {repo} --part {part}")
        for c in next_commands(repo, part, integ, brs, blocked, state):
            print(c)
        if a.dry_run:
            continue
        # Rewrite only when the state actually differs — the header timestamp is not state, or every run
        # would dirty the vault and "is this tree clean?" would stop meaning anything.
        body = [l for l in rollup[1:]]
        old = dst.read_text(errors="replace").splitlines() if dst.exists() else []
        old_body = [l for l in old[1:]]
        if body != old_body or a.force or not old:
            dst.write_text("\n".join(rollup) + "\n")
            wrote += 1
        here = [p for p, _, _ in ds if not p.name.endswith(".processed")]
        for p in here:
            p.rename(p.with_name(p.name + ".processed"))
        consumed_here += len(here)
    if a.dry_run:
        print("--- dry run: nothing written, no delta marked .processed")
        raise SystemExit(0)
    if not wrote and not consumed_here:
        print("note: rollup already matches git state; nothing changed")
        raise SystemExit(3)



if __name__ == "__main__":
    main()
