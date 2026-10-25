#!/usr/bin/env python3
"""Script-path tests for render.py (plain asserts, no pytest).

Run: PYTHON=python3 bash run_tests.sh
Covers: all gold specs render; structured errors on bad specs; usetex
fallback with stripped PATH; palette/style sync; real-bool transparent.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
RENDER = os.path.join(SKILL_DIR, "scripts", "render.py")
FIXTURES = os.path.join(SKILL_DIR, "evals", "fixtures")

sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
from palette import PALETTE, check_style_sync  # noqa: E402

PASSED = []


def ok(name):
    PASSED.append(name)
    print("PASS %s" % name)


def run(spec_path, extra=None, env=None):
    cmd = [sys.executable, RENDER, spec_path]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def load(name):
    with open(os.path.join(FIXTURES, name)) as fh:
        return json.load(fh)


def write_tmp(spec, dirname):
    path = os.path.join(dirname, "spec.json")
    with open(path, "w") as fh:
        json.dump(spec, fh)
    return path


# --- 1. every gold spec renders deterministically ---------------------------
with tempfile.TemporaryDirectory() as tmp:
    for fname in sorted(os.listdir(FIXTURES)):
        if not fname.startswith("gold_") or not fname.endswith(".json"):
            continue
        res = run(os.path.join(FIXTURES, fname), ["--outdir", tmp])
        out = json.loads(res.stdout)
        assert res.returncode == 0, "%s: %s" % (fname, res.stdout + res.stderr)
        assert out["ok"] is True, fname
        for f in out["files"]:
            assert os.path.isfile(f) and os.path.getsize(f) > 0, f
        ok("render %s" % fname)

# --- 2. structured errors on bad specs ---------------------------------------
with tempfile.TemporaryDirectory() as tmp:

    def expect_error(name, mutate, must_match):
        spec = load("gold_line.json")
        mutate(spec)
        res = run(write_tmp(spec, tmp), ["--outdir", tmp, "--data-dir", FIXTURES])
        assert res.returncode == 1, name
        out = json.loads(res.stdout)
        assert "error" in out, name
        assert must_match in out["error"], "%s: %s" % (name, out["error"])
        ok("error: %s" % name)

    expect_error("unknown preset", lambda s: s.update(preset="violin"), "unknown preset")
    expect_error("unknown data format", lambda s: s["layout"]["panels"][0]["series"][0]
                 ["data"].update(format="xlsx"), "unknown data format")
    expect_error("unknown output format", lambda s: s["output"].update(formats=["svg"]),
                 "unknown output format")
    expect_error("string transparent (old-repo bug)", lambda s: s["output"].update(transparent="True"),
                 "boolean")
    expect_error("missing data file", lambda s: s["layout"]["panels"][0]["series"][0]
                 ["data"].update(file="nope.csv"), "data file not found")
    expect_error("bad column name", lambda s: s["layout"]["panels"][0]["series"][0]
                 ["data"]["y"].update(column="bogus"), "not found")
    expect_error("unknown field", lambda s: s["layout"]["panels"][0].update(titel="x"),
                 "unknown field")
    expect_error("nrows*ncols mismatch", lambda s: s["layout"].update(nrows=2, ncols=2),
                 "nrows*ncols")
    expect_error("unknown color", lambda s: s["layout"]["panels"][0]["series"][0]
                 .update(color="mauve"), "unknown color")
    def _heatmap_with_x(s):
        s["preset"] = "heatmap"
        s["layout"]["panels"][0]["series"][0]["data"]["x"] = {"column": 0}

    expect_error("heatmap with x ref", _heatmap_with_x, "must not set data.x")

# --- 3. usetex fallback: PATH without pdflatex/latex -------------------------
with tempfile.TemporaryDirectory() as tmp:
    bare_bin = os.path.join(tmp, "bin")
    os.mkdir(bare_bin)
    for tool in ("python3", "sh", "env"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, os.path.join(bare_bin, tool))
    env = dict(os.environ, PATH=bare_bin)
    res = run(os.path.join(FIXTURES, "gold_line.json"), ["--outdir", tmp], env=env)
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stdout + res.stderr
    assert out["ok"] is True
    assert any("usetex unavailable" in w["warning"] for w in out["warnings"]), out["warnings"]
    ok("usetex fallback (PATH stripped)")

# --- 4. palette/style sync ---------------------------------------------------
check_style_sync()
ok("palette.py <-> paper.mplstyle prop_cycle sync")
for style in ("paper", "poster", "screen"):
    path = os.path.join(SKILL_DIR, "styles", style + ".mplstyle")
    assert os.path.isfile(path), path
    ok("style exists: %s" % style)

# --- 5. transparent=true is a real boolean -----------------------------------
with tempfile.TemporaryDirectory() as tmp:
    spec = load("gold_npz_multipanel.json")  # transparent: true, png
    spec["output"]["formats"] = ["png"]
    res = run(write_tmp(spec, tmp), ["--outdir", tmp, "--data-dir", FIXTURES])
    out = json.loads(res.stdout)
    assert out["ok"] is True, out
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    img = mpimg.imread(out["files"][0])
    assert img.shape[-1] == 4, "PNG has no alpha channel"
    ok("transparent=true yields alpha PNG")

# --- 6. unbalanced $ in labels: structured error or safe fallback -----------
with tempfile.TemporaryDirectory() as tmp:
    spec = load("gold_radial_distribution.json")
    spec["layout"]["panels"][0]["axes"]["x"]["label"] = "$g(r)"  # unbalanced
    res = run(write_tmp(spec, tmp), ["--outdir", tmp, "--data-dir", FIXTURES])
    assert "Traceback" not in res.stderr, "must not crash with traceback"
    assert res.stdout.strip(), "stdout must never be empty"
    out = json.loads(res.stdout)
    if res.returncode == 1:  # usetex active: latex rejects the label
        assert out.get("error") == "latex_render_failed", out
        assert "hint" in out["details"] and "$" in out["details"]["hint"], out
        assert "message" in out["details"], out
    else:  # mathtext fallback path (no TeX on machine) renders it instead
        assert out["ok"] is True, out
        assert any("usetex unavailable" in w["warning"] for w in out["warnings"]), out
    ok("unbalanced $ label -> structured latex_render_failed (or fallback)")

# --- 7. latex present but dvipng missing -> probe falls back, no crash -------
with tempfile.TemporaryDirectory() as tmp:
    bare_bin = os.path.join(tmp, "bin")
    os.mkdir(bare_bin)
    for tool in ("python3", "sh", "env", "latex", "kpsewhich"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, os.path.join(bare_bin, tool))
    # deliberately NO dvipng
    assert shutil.which("dvipng", path=bare_bin) is None
    env = dict(os.environ, PATH=bare_bin)
    res = run(os.path.join(FIXTURES, "gold_line.json"), ["--outdir", tmp], env=env)
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stdout + res.stderr
    assert out["ok"] is True
    warns = " ".join(w["warning"] for w in out["warnings"])
    assert "usetex unavailable" in warns and "dvipng" in warns, out["warnings"]
    assert "Traceback" not in res.stderr
    ok("latex-without-dvipng -> mathtext fallback warning")

# --- 8. fixture labels: balanced $ (guards gold-spec regression) -------------
def iter_spec_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from iter_spec_strings(v, path + "." + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_spec_strings(v, "%s[%d]" % (path, i))
    elif isinstance(node, str) and "$" in node:
        yield path, node

for fname in sorted(os.listdir(FIXTURES)):
    if fname.startswith("gold_"):
        for path, s in iter_spec_strings(load(fname)):
            assert s.count("$") % 2 == 0, "unbalanced $ in %s %s: %r" % (fname, path, s)
ok("all gold specs have balanced $ in strings")

print("\n%d tests passed" % len(PASSED))
