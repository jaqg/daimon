#!/usr/bin/env python3
"""Bake-off probe: one model, one role, isolated work dir, real tool whitelist + role gate.

Usage: probe.py <model-id> <thinking> <role>

Why Python and not bash: pi exits when stdin closes, so stdin must be held open — but the holder
must die with pi, or the pipeline hangs. start_new_session + killpg does that cleanly.
"""
import json, os, signal, subprocess, sys, time, shutil
from pathlib import Path

BAKE = Path(__file__).resolve().parent
PRIVATE = Path(os.environ.get("PI_BAKEOFF_PRIVATE") or (BAKE.parents[2] / "bakeoff-private"))

TOOLS = {
    "scout": "read,bash,ls,grep,find",
    "worker": "read,edit,write,bash,ls,grep,find",
    "calcs": "read,edit,write,bash,ls,grep,find",
    "verifier": "read,bash,ls,grep,find",
    # `-short` is a TASK alias, not a tier: same whitelist, same gate role, smaller spec.
    "worker-short": "read,edit,write,bash,ls,grep,find",
    "writer": "read,write,ls",
}
TIMEOUT = 780


def fixture(name: str):
    """Resolve a probe fixture. Synthetic ones (`thermo/`, `calc-bug/`) live in the repo; the
    research-derived ones (`selection/`, `lib/`, `METHODS.md`, the real acceptance test, `.venv`) live
    OUTSIDE the public repo, in `bakeoff-private/` next to it. Override with `PI_BAKEOFF_PRIVATE`.
    A missing fixture is skipped rather than faked: a probe that silently runs on stub data measures
    nothing."""
    for base in (BAKE, PRIVATE):
        cand = base / name
        if cand.exists():
            return cand
    return None


def setup_work(model: str, role: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_").replace(".", "_")
    # PROBE_TAG separates runs of the SAME model+role at different thinking levels — the crossed
    # high/medium/low probe would otherwise overwrite its own run dir three times.
    tag = os.environ.get("PROBE_TAG", "").strip()
    if tag:
        safe = f"{safe}__{tag}"
    work = BAKE / "run" / f"{safe}__{role}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for name in ("selection", "lib", "thermo", "calc-bug", "METHODS.md", ".venv"):
        src = fixture(name)
        if src is None:
            continue
        if src.name.startswith("."):
            os.symlink(src, work / src.name)
        elif src.is_dir():
            shutil.copytree(src, work / name, symlinks=True)
        else:
            shutil.copy(src, work / name)
    for f in (f"task-{role}.md", "SPEC-max-rings.md"):
        if (BAKE / f).exists():
            shutil.copy(BAKE / f, work / f)
    # The gate knows tiers, not task aliases — `worker-short` must still resolve to the worker profile,
    # or the probe would measure an UNGATED worker and call it thinking-level data.
    (work / ".pi-role").write_text(role.split("-")[0] + "\n")
    (work / "prompt.json").write_text(
        json.dumps({"type": "prompt", "message": (work / f"task-{role}.md").read_text()}) + "\n")
    return work


def launcher(work: Path, model: str, think: str, role: str) -> str:
    """Bash that pi genuinely stays attached to (verified: a Python-spawned stdin dies at ~0.3s,
    a bash-held pipe runs to completion). The trailing `sleep` is only a stdin holder — the
    driver kills the process group once agent_settled lands in the output file."""
    return (f'cd "{work}" || exit 1\n'
            f'{{ cat "{work}/prompt.json"; sleep {TIMEOUT}; }} | '
            f'exec timeout {TIMEOUT} pi --mode rpc --model "{model}" --thinking "{think}" '
            f'--no-session --tools "{TOOLS[role]}" > "{work}/rpc.jsonl" 2> "{work}/stderr.txt"\n')


def score(work: Path):
    tot = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    cost = 0.0; texts = []; gate = []; tools = 0; turns = 0
    for line in (work / "rpc.jsonl").read_text(errors="replace").splitlines():
        try: r = json.loads(line)
        except Exception: continue
        m = r.get("message")
        if isinstance(m, dict) and m.get("role") == "assistant":
            u = m.get("usage") or {}
            for k in tot: tot[k] += u.get(k, 0) or 0
            cost += (u.get("cost") or {}).get("total", 0) or 0
            buf = "".join(c.get("text", "") for c in (m.get("content") or []) if c.get("type") == "text")
            if buf.strip(): texts.append(buf)
        if r.get("type") == "tool_execution_start": tools += 1
        if r.get("type") == "turn_end": turns += 1
        s = json.dumps(r)
        if "tier]" in s: gate.append(s[:160])
    # message_end repeats the same text on every turn of the run — keep the last non-empty one
    # per assistant message and drop exact duplicates, else OUT.md doubles the answer.
    # Streaming emits the same answer twice with different trailing whitespace, and sometimes a strict
    # prefix of it. Dedupe on normalised text and drop any entry that is contained in a later one, else
    # OUT.md doubles the answer and every digest size reads 2x too big (measured 2026-10-24).
    norm = lambda s: " ".join(s.split())
    uniq = []
    for x in texts:
        nx = norm(x)
        if any(nx == u or nx in u for u in uniq): continue
        uniq = [x for x in uniq if norm(x) not in nx] + [x]
    (work / "OUT.md").write_text("\n\n---\n\n".join(uniq))
    (work / "GATE-HITS.jsonl").write_text("\n".join(gate))
    return {**tot, "cost": round(cost, 5), "turns": turns, "tool_calls": tools,
            "gate_hits": len(gate), "out_chars": sum(len(t) for t in uniq)}


def main():
    import subprocess as sp, os, signal
    if len(sys.argv) != 4:
        print(__doc__); sys.exit(2)
    model, think, role = sys.argv[1:4]
    work = setup_work(model, role)
    with open(work / "launcher.sh", "w") as fh:
        fh.write(launcher(work, model, think, role))
    t0 = time.time()
    p = sp.Popen(["bash", str(work / "launcher.sh")], start_new_session=True)
    timed_out = False
    try:
        p.wait(timeout=TIMEOUT + 30)
    except sp.TimeoutExpired:
        timed_out = True
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        p.wait(timeout=10)
    except Exception:
        pass
    met = {"model": model, "thinking": think, "role": role, "rc": p.returncode,
           "secs": round(time.time() - t0, 1), "timed_out": timed_out, **score(work)}
    (work / "meta.json").write_text(json.dumps(met, indent=1))
    print(f"{model:26s} {role:9s} {think:6s} out={met['output']:>6d} cold={met['input']:>6d} "
          f"cache={met['cacheRead']:>7d} ${met['cost']:.4f} {met['secs']:>6.1f}s "
          f"turns={met['turns']} tools={met['tool_calls']} gate={met['gate_hits']}")


if __name__ == "__main__":
    main()
