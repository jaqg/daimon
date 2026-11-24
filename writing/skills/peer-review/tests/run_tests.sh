#!/usr/bin/env bash
# run_tests.sh — deterministic contract suite for peer-review v2 (plan peer-review-v2 §4.3).
# This is the part's green command (test_cmd in .agent-paths).
#
# Asserts the stable contracts of plan §3.2 against the skill's scripts:
#   C5  check_reviews.py   — {ok, generic:[ids]}, exit 1 on missing evidence
#   C6  check_review_envs  — dual-name matrix + new keys (reviewcolor_defined,
#                            revieweditor_defined, macro) + --check-resolved mode
#   C7  extract_manuscript --claims heuristic candidates
#   C8  inject_reviews     — legacy bare array byte-compatible with v1 (byte golden),
#                            C4 object rendering (editor block, % pr:<id>, rank order)
#
# Capability gating: a group whose capability marker is ABSENT from the scripts tree is
# reported as `PENDING` (scripts slice not integrated yet) — never silently skipped. Once the
# marker exists, every assertion in that group is enforced. Set PEER_REVIEW_SCRIPTS_DIR to
# point the suite at another worktree's scripts (e.g. the parallel scripts slice).
#
# Usage: bash writing/skills/peer-review/tests/run_tests.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$TESTS_DIR/.." && pwd)"
ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
SCRIPTS="${PEER_REVIEW_SCRIPTS_DIR:-$SKILL_DIR/scripts}"
FIXTURES="$SKILL_DIR/evals/fixtures"
GOLDENS="$TESTS_DIR/goldens"
SMOKE_FIX="$TESTS_DIR/fixtures"

TMP="$(mktemp -d /tmp/peer-review-v2-tests.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0; pend=0
ok()   { echo "PASS $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1${2:+ — $2}"; fail=$((fail+1)); }
pend() { echo "PENDING $1 — $2"; pend=$((pend+1)); }

for f in "$SCRIPTS/extract_manuscript.py" "$SCRIPTS/check_review_envs.py" \
         "$SCRIPTS/inject_reviews.py" "$FIXTURES/minimal.tex" "$FIXTURES/full-preamble.tex"; do
  [ -f "$f" ] || { echo "missing required file: $f"; exit 1; }
done

# ---------------------------------------------------------------- G1 fixture rules + gold lint
g1=1
grep -q claudeorange "$FIXTURES/full-preamble.tex" \
  && ok "G1 full-preamble.tex keeps its claudeorange strings (legacy-patch fixture)" \
  || { bad "G1 full-preamble.tex lost claudeorange strings — legacy fixture must not be renamed"; g1=0; }
grep -q reviewcolor "$FIXTURES/reviewcolor-preamble.tex" \
  && ok "G1 reviewcolor-preamble.tex fixture exists with reviewcolor" \
  || { bad "G1 reviewcolor-preamble.tex missing or lacks reviewcolor"; g1=0; }
grep -q claudeorange "$FIXTURES/reviewcolor-preamble.tex" \
  && bad "G1 reviewcolor-preamble.tex must not contain claudeorange" \
  || ok "G1 reviewcolor-preamble.tex contains no claudeorange"
# no machine paths / real names in my new committed fixtures
if grep -rlE '/home/|/Users/|[A-Za-z]:\\\\' "$FIXTURES/seeded-a.tex" "$FIXTURES/seeded-b.tex" \
     "$FIXTURES/reviewcolor-preamble.tex" "$FIXTURES/seeded-defects.json" 2>/dev/null; then
  bad "G1 new fixtures must not contain machine paths"
else
  ok "G1 new fixtures contain no machine paths"
fi

python3 - "$FIXTURES" "$SCRIPTS" <<'PY' && ok "G1 seeded-defects.json gold lints (shape, 5-type coverage, anchors)" \
  || { bad "G1 seeded-defects.json gold lint"; g1=0; }
import json, subprocess, sys
from pathlib import Path

fixtures_dir = Path(sys.argv[1])
scripts_dir = Path(sys.argv[2])
gold = json.load(open(fixtures_dir / "seeded-defects.json"))
PLAN_TYPES = {"missing_scf_criterion", "section_inversion", "abstract_overclaim",
              "new_claim_in_conclusions", "absent_data_availability"}
errs = []
def req(c, m):
    if not c: errs.append(m)

req(isinstance(gold, dict) and len(gold) >= 2, "gold must cover >= 2 manuscripts")
req(all(isinstance(v, list) and v for v in gold.values()), "every fixture needs a defect list")
seen = set()
for fx, defects in gold.items():
    req((fixtures_dir / fx).exists(), f"gold fixture missing: {fx}")
    for d in defects:
        missing = {"defect_id", "type", "section", "para_anchor", "detect_keywords"} - set(d)
        req(not missing, f"{fx}/{d.get('defect_id', '?')}: missing keys {sorted(missing)}")
        seen.add(d["type"])
req(seen == PLAN_TYPES, f"gold must cover exactly the 5 plan defect types; missing {sorted(PLAN_TYPES - seen)}")
# anchors + sections must exist in the extracted manuscript text
for fx, defects in gold.items():
    p = subprocess.run([sys.executable, str(scripts_dir / "extract_manuscript.py"),
                        "--file", str(fixtures_dir / fx)], capture_output=True, text=True)
    req(p.returncode == 0, f"extract failed on {fx}: {p.stderr[:120]}")
    paras = json.loads(p.stdout) if p.returncode == 0 else []
    texts = [x["text"].lower() for x in paras]
    sections = {x["section"] for x in paras}
    for d in defects:
        req(any(str(d["para_anchor"]).lower() in t for t in texts),
            f"{fx}/{d['defect_id']}: para_anchor not found")
        if d["type"] != "absent_data_availability":
            req(d["section"] in sections, f"{fx}/{d['defect_id']}: section {d['section']!r} absent")
if errs:
    print("\n".join(errs)); sys.exit(1)
PY

# ---------------------------------------------------------------- G2 evals.json schema + frozen entries
python3 - "$ROOT" "$SKILL_DIR/evals/evals.json" <<'PY' && ok "G2 evals.json valid, first 6 entries byte-frozen vs HEAD, new flags covered" \
  || bad "G2 evals.json"
import json, subprocess, sys
root, path = sys.argv[1], sys.argv[2]
errs = []
def req(c, m):
    if not c: errs.append(m)

doc = json.load(open(path))
req(doc.get("skill_name") == "peer-review", "skill_name must stay 'peer-review'")
evs = doc.get("evals")
req(isinstance(evs, list) and len(evs) >= 7, "need >= 7 entries (6 frozen + new v2 entries)")
ids = [e.get("id") for e in evs]
req(len(ids) == len(set(ids)), "ids must be unique")
for e in evs:
    missing = {"id", "prompt", "expected_output", "files", "expectations"} - set(e)
    req(not missing, f"entry {e.get('id')}: missing fields {sorted(missing)}")
# the 6 pre-existing entries must be untouched (deep-equal to HEAD's first 6)
head = subprocess.run(["git", "show", "HEAD:writing/skills/peer-review/evals/evals.json"],
                      cwd=root, capture_output=True, text=True)
if head.returncode == 0:
    head_evs = json.loads(head.stdout)["evals"]
    req(len(head_evs) >= 6 and evs[:6] == head_evs[:6],
        "first 6 evals entries changed vs HEAD — they must stay byte-identical")
blob = json.dumps(evs)
for flag in ("--journal", "--preprint", "--blind", "--claims", "--check-resolved", "--passes"):
    req(flag in blob, f"no eval entry covers {flag}")
req("passes 1" in blob and "passes 3" in blob, "A/B protocol entry must mention --passes 1 vs --passes 3")
if errs:
    print("\n".join(errs)); sys.exit(1)
PY

# ---------------------------------------------------------------- G3 C6 env-detection matrix
if [ -f "$SCRIPTS/check_review_envs.py" ] && grep -q reviewcolor "$SCRIPTS/check_review_envs.py"; then
  # partial fixtures: a macro defined but envs missing (built in tmp — not committed)
  printf '%s\n' '\documentclass{article}' '\usepackage{xcolor}' \
    '\definecolor{claudeorange}{HTML}{D97757}' '\begin{document}' 'text' '\end{document}' \
    > "$TMP/partial-legacy.tex"
  printf '%s\n' '\documentclass{article}' '\usepackage{xcolor}' \
    '\definecolor{reviewcolor}{HTML}{2563EB}' '\begin{document}' 'text' '\end{document}' \
    > "$TMP/partial-reviewcolor.tex"

  run_env_case() { # run_env_case <case-name> <fixture-path>
    local name="$1" file="$2" out="$TMP/env-$1.json"
    if ! python3 "$SCRIPTS/check_review_envs.py" --file "$file" > "$out" 2>"$TMP/env-$1.err"; then
      bad "C6 env matrix [$name]" "script exited nonzero: $(head -c 200 "$TMP/env-$1.err")"
      return
    fi
    if python3 - "$name" "$out" <<'PY'
import json, sys
case, path = sys.argv[1], sys.argv[2]
d = json.load(open(path))
errs = []
def req(c, m):
    if not c: errs.append(m)

# existing keys preserved (backward compat), new keys additive (C6)
for k in ("review_defined", "suggestion_defined", "insert_line", "xcolor_defined",
          "claudeorange_defined", "patch"):
    req(k in d, f"missing existing key {k}")
for k in ("reviewcolor_defined", "revieweditor_defined", "macro"):
    req(k in d, f"missing C6 key {k}")
req(isinstance(d.get("insert_line"), int) and d["insert_line"] > 0, "insert_line must be a positive int")
req(d.get("macro") in ("reviewcolor", "claudeorange"), f"macro must be reviewcolor|claudeorange, got {d.get('macro')!r}")
patch = d.get("patch", "")
req(isinstance(patch, str), "patch must be a string")

if case == "bare":
    req(d.get("review_defined") is False and d.get("suggestion_defined") is False, "bare: envs undefined")
    req(d.get("claudeorange_defined") is False and d.get("reviewcolor_defined") is False, "bare: no macro defined")
    req(d.get("revieweditor_defined") is False, "bare: revieweditor undefined")
    req(d.get("macro") == "reviewcolor", f"bare: new injections must use reviewcolor, got {d.get('macro')!r}")
    req(r"\definecolor{reviewcolor}" in patch, "bare: patch must define reviewcolor")
    req(r"\newenvironment{revieweditor}" in patch, "bare: patch must define revieweditor")
    req(r"\newenvironment{review}" in patch, "bare: patch must define review env")
    req("color{reviewcolor}" in patch, "bare: env defs must reference reviewcolor")
    req("claudeorange" not in patch, "bare: patch must not reference legacy claudeorange")
    req(r"\usepackage{xcolor}" in patch, "bare: patch must add xcolor")
elif case == "legacy-claudeorange":
    req(d.get("claudeorange_defined") is True, "legacy: claudeorange_defined true")
    req(d.get("reviewcolor_defined") is False, "legacy: reviewcolor_defined false")
    req(d.get("macro") == "claudeorange", f"legacy: macro must be claudeorange, got {d.get('macro')!r}")
    req(patch.strip() == "", f"legacy: patch must be empty (zero migration), got {patch!r}")
elif case == "reviewcolor-fixture":
    req(d.get("reviewcolor_defined") is True, "rc: reviewcolor_defined true")
    req(d.get("claudeorange_defined") is False, "rc: claudeorange_defined false")
    req(d.get("macro") == "reviewcolor", f"rc: macro must be reviewcolor, got {d.get('macro')!r}")
    req(patch.strip() == "", f"rc: patch must be empty, got {patch!r}")
elif case == "partial-legacy":
    req(d.get("macro") == "claudeorange", f"partial-legacy: macro claudeorange, got {d.get('macro')!r}")
    req(r"\newenvironment{review}" in patch, "partial-legacy: env defs missing from patch")
    req("color{claudeorange}" in patch, "partial-legacy: env defs must reference claudeorange")
    req("definecolor" not in patch, "partial-legacy: color line suppressed (macro pre-defined)")
    req("revieweditor" not in patch, "partial-legacy: revieweditor suppressed (macro pre-defined)")
elif case == "partial-reviewcolor":
    req(d.get("macro") == "reviewcolor", f"partial-reviewcolor: macro reviewcolor, got {d.get('macro')!r}")
    req(r"\newenvironment{review}" in patch, "partial-reviewcolor: env defs missing from patch")
    req("color{reviewcolor}" in patch, "partial-reviewcolor: env defs must reference reviewcolor")
    req("definecolor" not in patch, "partial-reviewcolor: color line suppressed (macro pre-defined)")
    req("revieweditor" not in patch, "partial-reviewcolor: revieweditor suppressed (macro pre-defined)")
else:
    req(False, f"unknown case {case}")

if errs:
    print("; ".join(errs))
    sys.exit(1)
PY
    then ok "C6 env matrix [$name]"; else bad "C6 env matrix [$name]"; fi
  }

  run_env_case bare              "$FIXTURES/minimal.tex"
  run_env_case legacy-claudeorange "$FIXTURES/full-preamble.tex"
  run_env_case reviewcolor-fixture "$FIXTURES/reviewcolor-preamble.tex"
  run_env_case partial-legacy    "$TMP/partial-legacy.tex"
  run_env_case partial-reviewcolor "$TMP/partial-reviewcolor.tex"
else
  pend "C6 env-detection matrix" "check_review_envs.py has no reviewcolor support yet (scripts slice not integrated)"
fi

# ---------------------------------------------------------------- shared: extract once
if ! python3 "$SCRIPTS/extract_manuscript.py" --file "$FIXTURES/minimal.tex" > "$TMP/minimal-paras.json" 2>"$TMP/extract.err"; then
  bad "extract_manuscript on minimal.tex" "$(head -c 200 "$TMP/extract.err")"
fi
cat > "$TMP/legacy-reviews.json" <<'EOF'
[
  {"para_idx": 0, "severity": "major", "comment": "Legacy golden comment one: the abstract claims strong physisorption without citing the binding analysis.", "suggestion": "Add a qualifier linking the physisorption claim to the computed energies."},
  {"para_idx": 3, "severity": "minor", "comment": "Legacy golden comment two: the method parameters omit the convergence threshold.", "suggestion": null}
]
EOF

# ---------------------------------------------------------------- G4 C8 legacy bare-array byte-golden
if [ -f "$GOLDENS/inject-legacy-array.diff" ]; then
  if python3 "$SCRIPTS/inject_reviews.py" --file "$FIXTURES/minimal.tex" \
       --reviews "$(cat "$TMP/legacy-reviews.json")" --paragraphs "$(cat "$TMP/minimal-paras.json")" \
       --dry-run > "$TMP/legacy.diff" 2>"$TMP/legacy.err"; then
    if cmp -s "$TMP/legacy.diff" "$GOLDENS/inject-legacy-array.diff"; then
      ok "C8 legacy bare array renders byte-identical to v1 (dry-run golden)"
    else
      bad "C8 legacy bare array dry-run differs from golden" \
          "$(diff "$GOLDENS/inject-legacy-array.diff" "$TMP/legacy.diff" | head -5 | tr '\n' ' ')"
    fi
  else
    bad "C8 legacy bare array inject --dry-run errored" "$(head -c 200 "$TMP/legacy.err")"
  fi
else
  bad "C8 golden missing" "$GOLDENS/inject-legacy-array.diff"
fi

# ---------------------------------------------------------------- G5 C8 C4 rendering
if grep -q revieweditor "$SCRIPTS/inject_reviews.py" 2>/dev/null \
   && grep -q reviewcolor "$SCRIPTS/check_review_envs.py" 2>/dev/null; then
  # C4 object: input order deliberately shuffled vs rank order, and rank order matches
  # document order (cross-paragraph file layout is forced by paragraph positions, so
  # rank is only observable within a paragraph — the s-01/s-02 pair sits on the SAME
  # paragraph with s-02 fed FIRST: input order would render s-02 before s-01).
  cat > "$TMP/c4.json" <<'EOF'
{
  "header": {
    "summary": "The manuscript is coherent but the methods reporting is incomplete.",
    "recommendation": "major"
  },
  "comments": [
    {"id": "s-02", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
     "comment": "Rank probe: fed first but must render second by rank on the same paragraph.",
     "suggestion": null, "evidence": "adsorption energies were computed", "rank": 2,
     "merged_from": ["r2-03"]},
    {"id": "s-04", "para_idx": 6, "section": "Conclusions", "severity": "minor", "lens": "1f",
     "comment": "Rank probe: fourth comment, must render last.",
     "suggestion": null, "evidence": "DFT calculations show", "rank": 4,
     "merged_from": ["r3-02"]},
    {"id": "s-03", "para_idx": 3, "section": "Computational Methods", "severity": "major", "lens": "4",
     "comment": "Rank probe: convergence threshold absent from the methods description.",
     "suggestion": "State the SCF convergence threshold used.",
     "evidence": "plane-wave cutoff of 520 eV", "rank": 3, "merged_from": ["r1-04"]},
    {"id": "s-01", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
     "comment": "Rank probe: fed last but must render first by rank on the same paragraph.",
     "suggestion": null, "evidence": "adsorption energies were computed", "rank": 1,
     "merged_from": ["r1-01"]}
  ]
}
EOF
  python3 "$SCRIPTS/check_review_envs.py" --file "$FIXTURES/minimal.tex" > "$TMP/env-bare.json" 2>/dev/null

  if python3 "$SCRIPTS/inject_reviews.py" --file "$FIXTURES/minimal.tex" \
       --reviews "$(cat "$TMP/c4.json")" --paragraphs "$(cat "$TMP/minimal-paras.json")" \
       --preamble-json "$(cat "$TMP/env-bare.json")" --dry-run > "$TMP/c4.diff" 2>"$TMP/c4.err"; then
    if python3 - "$TMP/c4.diff" <<'PY'
import sys
d = open(sys.argv[1], encoding="utf-8").read()
lines = d.splitlines()
errs = []
def req(c, m):
    if not c: errs.append(m)

req("% pr:editor" in d, "missing % pr:editor invisible comment line")
req("\\begin{revieweditor}" in d, "editor block must use the revieweditor env")
req("The manuscript is coherent but the methods reporting is incomplete." in d, "header summary missing from editor block")
req("Recommendation: major" in d, "recommendation missing from editor block")
# editor block is the FIRST injected block
req(d.index("% pr:editor") < min(d.index(f"% pr:s-0{i}") for i in range(1, 5)),
    "editor block must precede every comment block")
# every % pr:<id> line is immediately followed by the block it prefixes
# (strip the unified-diff +/- prefix before inspecting content)
def content(line):
    return line[1:] if line[:1] in ("+", "-") else line
contents = [content(l) for l in lines]
for i, c in enumerate(contents):
    if c.startswith("% pr:"):
        req(i + 1 < len(contents) and contents[i + 1].startswith("\\begin{"),
            f"no block immediately after {c!r}")
# rendered sequence = rank order (s-02 was fed first but must render second on the
# shared paragraph; cross-paragraph layout follows document order, which here equals
# rank order by construction)
seq = [c[5:] for c in contents if c.startswith("% pr:")]
req(seq == ["editor", "s-01", "s-02", "s-03", "s-04"],
    f"render order must be editor, s-01..s-04 by rank; got {seq}")
req("\\begin{addition-suggestion}" in d, "suggestion must render in addition-suggestion env")
req("State the SCF convergence threshold used." in d, "suggestion text missing")
req("\\definecolor{reviewcolor}" in d, "new patch must define reviewcolor")
req("\\newenvironment{revieweditor}" in d, "new patch must define revieweditor")
if errs:
    print("; ".join(errs)); sys.exit(1)
PY
    then ok "C8 C4 object rendering (editor block, % pr:<id>, rank order, reviewcolor patch)"
    else bad "C8 C4 object rendering"; fi
    # dry-run diff must apply cleanly
    mkdir "$TMP/apply-c4" && cp "$FIXTURES/minimal.tex" "$TMP/apply-c4/minimal.tex"
    if patch --batch -p1 -d "$TMP/apply-c4" < "$TMP/c4.diff" >/dev/null 2>&1 \
       && grep -q 'begin{revieweditor}' "$TMP/apply-c4/minimal.tex"; then
      ok "C8 C4 dry-run diff applies cleanly with revieweditor block"
    else
      bad "C8 C4 dry-run diff does not apply cleanly"
    fi
  else
    bad "C8 C4 inject --dry-run errored" "$(head -c 300 "$TMP/c4.err")"
  fi

  # legacy claudeorange manuscript: editor block falls back to `review` env + EDITOR SUMMARY:
  if ! python3 "$SCRIPTS/extract_manuscript.py" --file "$FIXTURES/full-preamble.tex" \
       > "$TMP/full-paras.json" 2>/dev/null; then
    bad "extract full-preamble.tex"
  fi
  cat > "$TMP/c4-legacy.json" <<'EOF'
{
  "header": {"summary": "Legacy manuscript review synthesis line.", "recommendation": "major"},
  "comments": [
    {"id": "s-02", "para_idx": 2, "section": "Introduction", "severity": "minor", "lens": "2",
     "comment": "Legacy probe comment two fed before rank one.", "suggestion": null,
     "evidence": "zeolites", "rank": 2},
    {"id": "s-01", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
     "comment": "Legacy probe comment one must render first by rank.", "suggestion": null,
     "evidence": "physisorption", "rank": 1}
  ]
}
EOF
  if python3 "$SCRIPTS/inject_reviews.py" --file "$FIXTURES/full-preamble.tex" \
       --reviews "$(cat "$TMP/c4-legacy.json")" --paragraphs "$(cat "$TMP/full-paras.json")" \
       --dry-run > "$TMP/c4-legacy.diff" 2>"$TMP/c4-legacy.err"; then
    if python3 - "$TMP/c4-legacy.diff" <<'PY'
import sys
d = open(sys.argv[1], encoding="utf-8").read()
errs = []
def req(c, m):
    if not c: errs.append(m)

req("\\begin{revieweditor}" not in d, "legacy claudeorange manuscript must NOT get a revieweditor env")
req("EDITOR SUMMARY:" in d, "legacy editor block must use EDITOR SUMMARY: prefix")
req("Legacy manuscript review synthesis line." in d, "header summary missing from legacy editor block")
req("Recommendation: major" in d, "recommendation missing from legacy editor block")
req("definecolor" not in d, "legacy manuscript: zero migration, no new color definition")
req(d.index("% pr:s-01") < d.index("% pr:s-02"), "legacy comments must ascend by rank")
if errs:
    print("; ".join(errs)); sys.exit(1)
PY
    then ok "C8 C4 legacy claudeorange fallback (review env + EDITOR SUMMARY:, zero migration)"
    else bad "C8 C4 legacy claudeorange fallback"; fi
  else
    bad "C8 C4 legacy inject --dry-run errored" "$(head -c 300 "$TMP/c4-legacy.err")"
  fi
else
  pend "C8 C4 object rendering" "inject_reviews.py has no revieweditor support yet (scripts slice not integrated)"
fi

# ---------------------------------------------------------------- G6 C7 --claims
if grep -q -- '--claims' "$SCRIPTS/extract_manuscript.py" 2>/dev/null; then
  cat > "$TMP/claims-doc.tex" <<'EOF'
\documentclass{article}
\begin{document}
\section{Introduction}
We show that the proposed protocol reduces the prediction error compared with the baseline
across all of the tested systems in this study.

\section{Results}
The binding energy is 42.7 kJ mol-1 at 300 K for the smallest cluster in the series.

This approach significantly improves the accuracy of the prediction under realistic conditions.

\end{document}
EOF
  if python3 "$SCRIPTS/extract_manuscript.py" --file "$TMP/claims-doc.tex" --claims \
       > "$TMP/claims.json" 2>"$TMP/claims.err"; then
    # backward compat (C7): without the flag the output stays the bare C1 array
    if python3 "$SCRIPTS/extract_manuscript.py" --file "$TMP/claims-doc.tex" \
         > "$TMP/no-claims.json" 2>/dev/null \
       && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if isinstance(d, list) else 1)' "$TMP/no-claims.json"; then
      ok "C7 without --claims stays the bare C1 array"
    else
      bad "C7 without --claims changed the default output shape"
    fi
    if python3 - "$TMP/claims.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
errs = []
def req(c, m):
    if not c: errs.append(m)

req(isinstance(doc, dict), "--claims output must be a JSON object {paragraphs, claims}")
req(isinstance(doc.get("claims"), list) and doc["claims"], "claims must be a non-empty list")
req(isinstance(doc.get("paragraphs"), list) and len(doc["paragraphs"]) >= 3,
    "paragraphs (C1 array) must be present alongside claims")
if doc.get("paragraphs"):
    for k in ("section", "para_idx", "text"):
        req(k in doc["paragraphs"][0], f"C1 paragraph missing key {k}")
# pinned C7 candidate shape: {id, section, para_idx, text, type}
claims = doc.get("claims") or []
for c in claims:
    missing = {"id", "section", "para_idx", "text", "type"} - set(c or {})
    req(not missing, f"claim candidate missing pinned keys {sorted(missing)}: {c!r}")
idxs = {c.get("para_idx") for c in claims if isinstance(c, dict)}
req(len(idxs & {0, 1, 2}) >= 2, f"claims must reference the claim paragraphs, got para_idx {sorted(idxs)}")
texts = " ".join(str(c.get("text", "")) for c in claims).lower()
for needle in ("we show", "42.7", "significantly"):
    req(needle in texts, f"claims text missing heuristic match {needle!r}")
if errs:
    print("; ".join(errs)); sys.exit(1)
PY
    then ok "C7 extract --claims returns pinned {paragraphs, claims} with heuristic candidates"
    else bad "C7 extract --claims output"
    fi
  else
    bad "C7 extract --claims errored" "$(head -c 200 "$TMP/claims.err")"
  fi
else
  pend "C7 --claims" "extract_manuscript.py has no --claims flag yet (scripts slice not integrated)"
fi

# ---------------------------------------------------------------- G7 C6 --check-resolved
if grep -q -- '--check-resolved' "$SCRIPTS/check_review_envs.py" 2>/dev/null; then
  # Fixture mirrors real injection layout: [paragraph][% pr:<id>][review block],
  # so the % pr marker anchors each comment to the paragraph it follows.
  cat > "$TMP/resolved.tex" <<'EOF'
\documentclass{article}
\usepackage{xcolor}
\definecolor{claudeorange}{HTML}{D97757}
\newenvironment{review}{\par\noindent\color{claudeorange}\textbf{Reviewer: }}{\par}

\begin{document}
\section{Methods}

All calculations used a plane-wave cutoff of 520 eV; the cutoff was set to 520 eV after a
convergence study, and the k-point mesh was fixed at 6x6x6 throughout the work.
% pr:s-01
\begin{review}
The SCF convergence criterion is not stated for the plane-wave calculations.
\end{review}

The magnetic moments were initialized per atom and relaxed until the forces fell below the
tolerance described above for every site considered in the supercell.
% pr:s-02
\begin{review}
No Hubbard U value is reported for the d-electrons.
\end{review}

A third probe paragraph mentions the integration window used for the free energy estimate.
% pr:s-03
\begin{review}
The integration window quote lives in a different paragraph than this anchor.
\end{review}

\end{document}
EOF
  cat > "$TMP/resolved-reviews.json" <<'EOF'
{
  "header": {"summary": "Round-trip review of the methods section.", "recommendation": "minor"},
  "comments": [
    {"id": "s-01", "para_idx": 0, "section": "Methods", "severity": "major", "lens": "4",
     "comment": "Probe: evidence quote present in its anchored paragraph.",
     "suggestion": null, "evidence": "the cutoff was set to 520 eV", "rank": 1},
    {"id": "s-02", "para_idx": 1, "section": "Methods", "severity": "major", "lens": "4",
     "comment": "Probe: evidence quote absent from the whole document.",
     "suggestion": null, "evidence": "a Hubbard U of 4.5 eV", "rank": 2},
    {"id": "s-03", "para_idx": 2, "section": "Methods", "severity": "minor", "lens": "4",
     "comment": "Probe: evidence quote exists only in a different paragraph.",
     "suggestion": null, "evidence": "the cutoff was set to 520 eV", "rank": 3}
  ]
}
EOF
  if python3 "$SCRIPTS/check_review_envs.py" --check-resolved --file "$TMP/resolved.tex" \
       --reviews "$TMP/resolved-reviews.json" > "$TMP/resolved-out.json" 2>"$TMP/resolved.err"; then
    if python3 - "$TMP/resolved-out.json" <<'PY'
import json, sys
raw = json.load(open(sys.argv[1]))
errs = []
def req(c, m):
    if not c: errs.append(m)

items = raw if isinstance(raw, list) else (raw.get("comments") if isinstance(raw, dict) else None)
req(isinstance(items, list), "output must be a list of per-comment entries (or object with a comments list)")
if isinstance(items, list):
    by_id = {e.get("id"): e for e in items if isinstance(e, dict)}
    req({"s-01", "s-02", "s-03"} <= set(by_id), f"every comment needs its own entry, got ids {sorted(by_id)}")
    for cid, e in by_id.items():
        req(e.get("status") in ("resolved", "unresolved", "uncertain"),
            f"{cid}: status {e.get('status')!r} not in resolved|unresolved|uncertain")
        req(isinstance(e.get("matched_quote"), str), f"{cid}: matched_quote must be a string")
    # pinned direction (plan §3.2 C6, confirmed 2026-11-24):
    #   quote present in anchored paragraph -> unresolved (matched_quote = quote)
    #   quote absent from whole document    -> resolved   (matched_quote = "")
    #   quote present only in ANOTHER para  -> uncertain  (matched_quote = quote)
    if "s-01" in by_id:
        req(by_id["s-01"]["status"] == "unresolved",
            f"s-01 (quote in anchored para) must be unresolved, got {by_id['s-01']['status']!r}")
        req(by_id["s-01"]["matched_quote"] != "", "s-01 matched_quote must carry the quote")
    if "s-02" in by_id:
        req(by_id["s-02"]["status"] == "resolved",
            f"s-02 (quote nowhere in doc) must be resolved, got {by_id['s-02']['status']!r}")
        req(by_id["s-02"]["matched_quote"] == "", "s-02 matched_quote must be empty")
    if "s-03" in by_id:
        req(by_id["s-03"]["status"] == "uncertain",
            f"s-03 (quote only in another para) must be uncertain, got {by_id['s-03']['status']!r}")
        req(by_id["s-03"]["matched_quote"] != "", "s-03 matched_quote must carry the found quote")
if errs:
    print("; ".join(errs)); sys.exit(1)
PY
    then
      # determinism: same input, same output
      python3 "$SCRIPTS/check_review_envs.py" --check-resolved --file "$TMP/resolved.tex" \
        --reviews "$TMP/resolved-reviews.json" > "$TMP/resolved-out2.json" 2>/dev/null
      cmp -s "$TMP/resolved-out.json" "$TMP/resolved-out2.json" \
        && ok "C6 --check-resolved (pinned direction: unresolved/resolved/uncertain, % pr anchors, deterministic)" \
        || bad "C6 --check-resolved not deterministic"
    else
      bad "C6 --check-resolved output"
    fi
  else
    bad "C6 --check-resolved errored" "$(head -c 300 "$TMP/resolved.err")"
  fi
else
  pend "C6 --check-resolved" "check_review_envs.py has no --check-resolved mode yet (scripts slice not integrated)"
fi

# ---------------------------------------------------------------- G8 C5 check_reviews
if [ -f "$SCRIPTS/check_reviews.py" ]; then
  cat > "$TMP/c5-pass.json" <<'EOF'
[
  {"id": "c1", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
   "comment": "Probe pass: the abstract claim outruns the reported numbers.",
   "suggestion": null, "evidence": "adsorption energies were computed"},
  {"id": "c2", "para_idx": 3, "section": "Computational Methods", "severity": "minor", "lens": "4",
   "comment": "Probe pass: convergence threshold missing from methods.",
   "suggestion": null, "evidence": "520 eV"}
]
EOF
  cat > "$TMP/c5-fail.json" <<'EOF'
[
  {"id": "c1", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
   "comment": "Probe fail: generic comment with evidence not present anywhere.",
   "suggestion": null, "evidence": "quantum entanglement of the review process"},
  {"id": "c2", "para_idx": 3, "section": "Computational Methods", "severity": "minor", "lens": "4",
   "comment": "Probe pass: convergence threshold missing from methods.",
   "suggestion": null, "evidence": "520 eV"}
]
EOF
  cat > "$TMP/c5-c4.json" <<'EOF'
{
  "header": {"summary": "Synthesis line.", "recommendation": "minor"},
  "comments": [
    {"id": "s-01", "para_idx": 0, "section": "Abstract", "severity": "major", "lens": "1e",
     "comment": "Probe C4 input: comment with valid evidence.", "suggestion": null,
     "evidence": "adsorption energies were computed", "rank": 1}
  ]
}
EOF

  cat > "$TMP/c5-pass.assert.py" <<'PYEOF'
req(d["ok"] is True, f"ok must be true, got {d.get('ok')!r}")
req(d["generic"] == [], f"generic must be empty, got {d['generic']!r}")
PYEOF
  cat > "$TMP/c5-fail.assert.py" <<'PYEOF'
req(d["ok"] is False, "ok must be false")
req("c1" in d["generic"], f"c1 must be flagged generic, got {d['generic']!r}")
req("c2" not in d["generic"], "c2 has valid evidence and must not be flagged")
PYEOF
  cat > "$TMP/c5-c4.assert.py" <<'PYEOF'
req(d["ok"] is True, f"ok must be true for valid C4 input, got {d.get('ok')!r}")
req(d["generic"] == [], f"generic must be empty, got {d['generic']!r}")
PYEOF

  run_c5() { # run_c5 <name> <reviews-json> <expected-exit> <assert-file>
    local name="$1" reviews="$2" want_rc="$3" asserts="$4" out="$TMP/c5-$1.out"
    python3 "$SCRIPTS/check_reviews.py" --reviews "$reviews" \
      --paragraphs "$TMP/minimal-paras.json" > "$out" 2>"$TMP/c5-$1.err"
    local rc=$?
    if [ "$rc" -ne "$want_rc" ]; then
      bad "C5 $name" "exit $rc, want $want_rc ($(head -c 200 "$TMP/c5-$1.err"))"
      return
    fi
    if python3 - "$out" "$asserts" <<'PY'
import json, sys
raw = open(sys.argv[1]).read().strip()
try:
    d = json.loads(raw)
except json.JSONDecodeError:
    d = json.loads(raw.splitlines()[-1])
errs = []
def req(c, m):
    if not c: errs.append(m)
req(isinstance(d, dict) and "ok" in d and "generic" in d, "output must be an object with ok and generic")
req(isinstance(d.get("generic"), list), "generic must be a list of comment ids")
exec(compile(open(sys.argv[2]).read(), sys.argv[2], "exec"))
if errs:
    print("; ".join(errs)); sys.exit(1)
PY
    then ok "C5 $name"; else bad "C5 $name"; fi
  }

  run_c5 "pass (C3 array)" "$TMP/c5-pass.json" 0 "$TMP/c5-pass.assert.py"
  run_c5 "fail (generic evidence)" "$TMP/c5-fail.json" 1 "$TMP/c5-fail.assert.py"
  run_c5 "pass (C4 object input)" "$TMP/c5-c4.json" 0 "$TMP/c5-c4.assert.py"
else
  pend "C5 check_reviews" "scripts/check_reviews.py not present yet (scripts slice not integrated)"
fi

# ---------------------------------------------------------------- G9 seeded recall harness smoke
RECALL="$SKILL_DIR/evals/run_seeded_recall.py"
if [ -f "$RECALL" ]; then
  if python3 "$RECALL" --arm-a "$SMOKE_FIX/arm-smoke-a.json" --arm-b "$SMOKE_FIX/arm-smoke-b.json" \
       > "$TMP/recall.out" 2>"$TMP/recall.err"; then
    if grep -q "B >= A overall: yes" "$TMP/recall.out" \
       && grep -q "RESULT: OK" "$TMP/recall.out" \
       && grep -q "recall@5" "$TMP/recall.out"; then
      ok "run_seeded_recall.py computes recall@N and the A/B verdict on smoke fixtures"
    else
      bad "run_seeded_recall.py output" "$(tail -3 "$TMP/recall.out" | tr '\n' ' ')"
    fi
  else
    bad "run_seeded_recall.py exited nonzero" "$(head -c 300 "$TMP/recall.err")"
  fi
else
  bad "run_seeded_recall.py missing" "$RECALL"
fi

# ---------------------------------------------------------------- summary
echo "---- peer-review v2: $pass passed, $fail failed, $pend pending (capability not in scripts tree yet)"
[ "$fail" -eq 0 ]
