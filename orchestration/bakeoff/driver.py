#!/usr/bin/env python3
"""Parallel bake-off driver.

  driver.py <model[,...]> <thinking> <role[,...]> [--maxpar N] [--timeout SECS]

Each probe runs as its own process group: bash holds pi's stdin open (verified required), and this
driver polls rpc.jsonl for `agent_settled`, then SIGKILLs the group (the stdin holder would
otherwise sit there for the whole sleep). Results land in run/<model>__<role>/meta.json + OUT.md
and are appended to results.jsonl.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent))
import probe as P

HERE = Path(__file__).resolve().parent


def launch(model, think, role, timeout):
    work = P.setup_work(model, role)
    P.TIMEOUT = timeout
    t0 = time.time()
    p = subprocess.Popen(["bash", "-c", P.launcher(work, model, think, role)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    out = work / "rpc.jsonl"
    # rpc.jsonl is written by the launcher itself; we only watch it for completion.
    settled = False
    while time.time() - t0 < timeout:
        if out.exists():
            try:
                if "agent_settled" in out.read_text(errors="replace"):
                    settled = True
                    break
            except Exception:
                pass
        if p.poll() is not None:
            break
        time.sleep(3)
    grace = time.time()
    while time.time() - grace < 20:  # let the last events flush
        if out.exists() and "agent_settled" in out.read_text(errors="replace"):
            settled = True
            break
        time.sleep(2)
    try:
        import os, signal
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        p.wait(timeout=10)
    except Exception:
        pass
    secs = round(time.time() - t0, 1)
    met = {"model": model, "thinking": think, "role": role, "rc": p.returncode, "secs": secs,
           "settled": settled, **P.score(work)}
    met["timed_out"] = not settled and secs >= timeout - 5
    (work / "meta.json").write_text(json.dumps(met, indent=1))
    line = (f"{model:26s} {role:9s} {think:6s} out={met['output']:>6d} cold={met['input']:>6d} "
            f"cache={met['cacheRead']:>7d} ${met['cost']:.4f} {secs:>6.1f}s turns={met['turns']} "
            f"tools={met['tool_calls']} gate={met['gate_hits']}"
            f"{' TIMEOUT' if met['timed_out'] else ''}")
    print(line, flush=True)
    with open(HERE / "results.jsonl", "a") as fh:
        fh.write(json.dumps(met) + "\n")
    return met


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models"); ap.add_argument("thinking"); ap.add_argument("roles")
    ap.add_argument("--maxpar", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=780)
    a = ap.parse_args()
    models = a.models.split(","); roles = a.roles.split(",")
    jobs = [(m, a.thinking, r) for m in models for r in roles]
    print(f"# {len(jobs)} probes, {a.maxpar} parallel, timeout {a.timeout}s", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.maxpar) as ex:
        res = list(ex.map(lambda j: launch(*j, a.timeout), jobs))
    cold = sum(r["cost"] for r in res)
    print(f"\n# done in {round(time.time()-t0)}s · total metered cost ${cold:.3f} · "
          f"{sum(1 for r in res if r['timed_out'])} timeouts", flush=True)


main()
