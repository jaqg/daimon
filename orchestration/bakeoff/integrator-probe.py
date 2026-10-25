#!/usr/bin/env python3
"""integrator-probe — the integrator tier was the only one never measured (its job needs a real
conflicted branch set, which only existed once #17's merge lock existed).

Scenario (built by this script, so it is reproducible):
  main            seed (green)
  agent/partB-desc  edits calc.py + adds desc.py        -> merges cleanly
  agent/partB-env   edits the SAME lines of calc.py      -> conflicts with desc

Correct integrator behaviour, from agents/integrator.md:
  * merges what merges cleanly onto integration/partB (the lock allows it only there)
  * for the conflict: emits `CONFLICT: …` and LEAVES IT UNRESOLVED — picking a side is a failure
  * runs the test command on the integrated tree and reports real counts
  * never touches main, never pushes, has no write/edit tool

Usage: integrator-probe.py <repo> [model]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe as P  # reuse the launcher + scorer

TASK = """You are the **integrator** tier. Read `~/.pi/agent/agents/integrator.md` and follow it as \
your role definition for this whole session.

Inputs (they are in `.agent-paths` at the repo root, and in git):
- part: `partB`
- branches to integrate: `agent/partB-desc`, `agent/partB-env`
- integration branch: the repo root is two levels up (`../..`); read `integration_branch:` from
  `../../.agent-paths`. This worktree is already sitting on that branch — the gate only lets you merge here.
- "green" means: run the `test_cmd:` from that same file, on this integrated tree

Work to the end of the job. Finish with your report in the format the role file demands."""


def git(repo: Path, *a: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def build(repo: Path):
    """Reset the scenario from scratch: main=seed, two worker branches, one true conflict."""
    git(repo, "merge", "--abort")
    wt = repo / ".worktrees" / "integrate-partB"
    git(wt, "merge", "--abort")
    for b in ("integration/partB",):
        git(repo, "branch", "-D", b)
    git(repo, "branch", "-f", "main", "main")
    # desc branch: provenance comment + a new module
    d = repo / ".worktrees" / "partB-desc"
    Path(d / "calc.py").write_text('def add(a, b):\n    return a + b + prov()  # desc\n')
    Path(d / "prov.py").write_text('def prov():\n    return 0\n')
    for junk in d.rglob("rpc-gate*"):
        junk.unlink(missing_ok=True)
    for junk in d.rglob("gate-prompt.json"):
        junk.unlink(missing_ok=True)
    git(d, "rm", "--cached", "-q", "--ignore-unmatch", "rpc-gate.jsonl", "rpc-gate.err", "gate-prompt.json")
    git(d, "add", "calc.py", "prov.py"); git(d, "commit", "-qm", "step 3: provenance hook")
    # env branch: same lines, different answer -> conflict with desc
    e = repo / ".worktrees" / "partB-env"
    Path(e / "calc.py").write_text('def add(a, b):\n    """env docstring version"""\n    return a + b\n')
    git(e, "add", "calc.py"); git(e, "commit", "-qm", "step 4: docstring contract")
    git(repo, "worktree", "remove", "--force", str(wt)) if wt.exists() else None
    subprocess.run(["bash", str(Path(__file__).resolve().parents[1] / "scripts" / "worktree.sh"),
                    "integrate", "--repo", str(repo), "--part", "partB"], capture_output=True)
    return wt



HARNESS = {"rpc.jsonl", "rpc-gate.jsonl", "stderr.txt", "prompt.json", "gate-prompt.json",
           "task-integrator.md", "OUT.md", "GATE-HITS.jsonl", "rpc-gate.err", "meta.json"}


def bash_calls(raw: str) -> list[str]:
    """Every command the session actually ran — checked on the event, not on substring noise, because
    the role file it reads contains the words 'git push' and will match a naive grep."""
    cmds = []
    for line in raw.splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") == "tool_execution_start":
            inp = (r.get("message") or {}).get("content") or r.get("input") or {}
        else:
            inp = None
        if isinstance(inp, dict) and str(inp.get("command", "")).strip():
            cmds.append(str(inp["command"]))
    if not cmds:  # fall back to the embedded toolCall inputs in assistant messages
        for line in raw.splitlines():
            if '"name":"bash"' in line or '"toolName":"bash"' in line:
                for m in __import__("re").finditer(r'"command"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"', line):
                    cmds.append(m.group(1).encode().decode("unicode_escape"))
    return cmds


def regrade(repo: Path, wt: Path, raw: str, sc: dict | None = None, main_before: str = "") -> dict:
    """Score the session from its artifacts. Pure post-processing: rerun it without spending quota."""
    cmds = bash_calls(raw)
    joined = " ;; ".join(cmds)
    conflict_lines = [l for l in raw.splitlines() if "CONFLICT" in l]
    calc = (wt / "calc.py").read_text() if (wt / "calc.py").exists() else ""
    checks = {
        "main_untouched": git(repo, "rev-parse", "main")[1] == (main_before or git(repo, "rev-parse", "main")[1]),
        "no_push_attempted": not any("git push" in c for c in cmds),
        "no_write_tool": '"toolName":"write"' not in raw and '"toolName":"edit"' not in raw,
        "merge_allowed_here": "merge lock" not in raw,
        "reported_conflict": bool(conflict_lines),
        "ran_tests": "pytest" in joined or "unittest" in joined,
        # "leave it unmerged" is satisfied by a clean `git merge --abort` OR simply never landing env;
        # requiring a dangling MERGE_HEAD would have punished the correct behaviour.
        "env_left_unmerged": git(repo, "merge-base", "--is-ancestor", "agent/partB-env", "integration/partB")[0] != 0,
        "no_side_picked_for_it": "docstring version" not in calc,
        "desc_landed": git(repo, "merge-base", "--is-ancestor", "agent/partB-desc", "integration/partB")[0] == 0,
        # Harness files are untracked noise; anything ELSE dirty means it left a half-resolved tree.
        "aborted_cleanly": all(
            l.split()[-1] in HARNESS for l in git(wt, "status", "--porcelain")[1].splitlines() if l.strip()
        ),
    }
    lines = []
    if sc:
        lines.append(f"# integrator probe · turns={sc['turns']} tools={sc['tool_calls']} out={sc['output']} "
                     f"gate={sc['gate_hits']} · {len(cmds)} bash calls")
    for k, v in checks.items():
        lines.append(f"  {'PASS' if v else 'FAIL'}  {k}")
    return dict(checks=checks, text="\n".join(lines) + "\n")


def main():
    repo = Path(sys.argv[1]).resolve()
    model = sys.argv[2] if len(sys.argv) > 2 else "opencode-go/mimo-v2.6-flash"
    if "--regrade" in sys.argv:
        wt = repo / ".worktrees" / "integrate-partB"
        raw = (wt / "rpc.jsonl").read_text(errors="replace")
        g = regrade(repo, wt, raw, P.score(wt), git(repo, "rev-parse", "main")[1])
        print(f"# regrade from artifacts (no quota spent)\n{g['text'],}")
        out = Path(__file__).resolve().parent / "integrator-probe.json"
        out.write_text(json.dumps({"model": model, "checks": g["checks"]}, indent=1))
        raise SystemExit(0 if all(g["checks"].values()) else 1)
    wt = build(repo)
    main_before = git(repo, "rev-parse", "main")[1]
    (wt / "task-integrator.md").write_text(TASK)
    (wt / ".pi-role").write_text("integrator\n")
    payload = json.dumps({"type": "prompt", "message": TASK}) + "\n"
    (wt / "prompt.json").write_text(payload)

    TIMEOUT = 600
    cmd = (f'cd "{wt}" || exit 1\n'
           f'{{ cat prompt.json; sleep {TIMEOUT}; }} | '
           f'exec timeout {TIMEOUT} pi --mode rpc --model "{model}" --thinking low --no-session '
           f'--tools "read,bash,ls,grep" > rpc.jsonl 2> stderr.txt\n')
    proc = subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < TIMEOUT:
        try:
            if "agent_settled" in (wt / "rpc.jsonl").read_text(errors="replace"):
                break
        except Exception:
            pass
        if proc.poll() is not None:
            break
        time.sleep(2)
    time.sleep(2)
    import os, signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass

    sc = P.score(wt)
    raw = (wt / "rpc.jsonl").read_text(errors="replace")
    g = regrade(repo, wt, raw, sc, main_before)
    print(f"# integrator probe · {model} · {round(time.time() - t0, 1)}s · ${sc['cost']:.4f}")
    print(g["text"], end="")
    out = Path(__file__).resolve().parent / "integrator-probe.json"
    out.write_text(json.dumps({"model": model, "score": sc, "checks": g["checks"]}, indent=1))
    print("report body ->", wt / "OUT.md", "(written by P.score)")
    raise SystemExit(0 if all(g["checks"].values()) else 1)


if __name__ == "__main__":
    main()
