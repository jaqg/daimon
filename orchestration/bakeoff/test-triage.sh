#!/usr/bin/env bash
# test-triage.sh — deterministic checks for the brain's recon script (T1..T13). No model, no network.
#   bash orchestration/bakeoff/test-triage.sh
# These exist because `/triage` told the brain to run shell one-liners the gate denies, and because
# vault-root resolution had already invented a nonexistent path once (vault-init.sh, task #22).
set -uo pipefail
T="$(cd "$(dirname "$0")/.." && pwd)/scripts/triage.sh"
R=/tmp/test-triage
pass=0 fail=0
ok()   { echo "PASS $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1${2:+ — $2}"; fail=$((fail+1)); }

rm -rf "$R"; mkdir -p "$R/vault/10-Projects/PhD-Demo" "$R/vault/10-Projects/Collabs/Other-DEMO-two" \
              "$R/vault/memory" "$R/repo2" "$R/config"
cd "$R/repo2" && git init -q -b main && git config user.email t@t && git config user.name t && echo x > a.py \
  && git add -A && git commit -qm seed && echo dirty >> a.py
D="$R/vault/10-Projects/PhD-Demo"
cat > "$D/AGENTS.md" <<EOF
# Demo project
State file: memory/project_demo.md
EOF
printf 'current state here\n' > "$R/vault/memory/project_demo.md"
mkdir -p "$D/status" "$D/handoffs"
printf '## 2026-10-20 landed the selector\n### sub-step\n' > "$D/history.md"
printf -- '- [ ] pick the part\n- [ ] name the model\n' > "$D/open-questions.md"
printf '# demo — status (rolled up 2026-10-26 by merge-status)\ntally: DONE 2\n' > "$D/status/demo-part.md"
printf 'project-dashboard body\n' > "$D/project-dashboard.md"
printf '# format: repo: <path>   (~ expanded)\n# repo: ~/elsewhere/ignored\n%s\n' "$R/repo2" > "$D/status/repos.txt"
printf '# only comments here\n# repo: ~/Documents/whatever\n' > "$R/vault/10-Projects/Collabs/Other-DEMO-two/repos_dummy"
mkdir -p "$R/vault/10-Projects/Collabs/Other-DEMO-two/status"
mv "$R/vault/10-Projects/Collabs/Other-DEMO-two/repos_dummy" "$R/vault/10-Projects/Collabs/Other-DEMO-two/status/repos.txt"

# T1 — explicit --vault wins over everything.
o=$(bash "$T" PhD-Demo --vault "$R/vault" 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^VAULT=$R/vault$" <<<"$o" && ok "T1 --vault wins" || bad "T1 --vault wins" "$o"

# T2/T3 — environment beats the per-machine config file, and the config file is used when nothing else is.
echo "$R/nope" > "$R/config/vault-root"
o=$(VAULT_ROOT="$R/vault" bash "$T" PhD-Demo 2>&1)
grep -q "^VAULT=$R/vault$" <<<"$o" && ok "T2 VAULT_ROOT honored" || bad "T2 VAULT_ROOT honored" "$o"
o=$(HOME="$R/fakehome" bash -c "mkdir -p $R/fakehome/.config/pi && echo $R/vault > \$HOME/.config/pi/vault-root && bash $T PhD-Demo" 2>&1)
grep -q "^VAULT=$R/vault$" <<<"$o" && ok "T3 config file used when no flag/env" || bad "T3 config file used" "$(tail -1 <<<"$o")"

# T4/T5/T6/T7 — matching: exact, fuzzy-unique, ambiguous, absent.
o=$(bash "$T" PhD-Demo --vault "$R/vault" 2>&1)
grep -q "^PROJECT=$D$" <<<"$o" && ok "T4 exact match" || bad "T4 exact match"
o=$(bash "$T" demo-two --vault "$R/vault" 2>&1)
grep -q "^REL=Collabs/Other-DEMO-two$" <<<"$o" && ok "T5 fuzzy match reports vault-relative name" || bad "T5 fuzzy match"
bash "$T" demo --vault "$R/vault" >/tmp/tt-amb 2>&1; rc=$?
[ $rc -eq 4 ] && grep -q 'not a unique match' /tmp/tt-amb && ok "T6 ambiguous match refuses with candidates" || bad "T6 ambiguous match refuses" "rc=$rc"
bash "$T" nosuchproject --vault "$R/vault" >/dev/null 2>&1; [ $? -eq 4 ] && ok "T7 unknown project exits 4" || bad "T7 unknown project exits 4"

# T8 — the facts a brain would otherwise burn cache reading.
o=$(bash "$T" PhD-Demo --vault "$R/vault" 2>&1)
grep -q '^STATE=.*/memory/project_demo.md$' <<<"$o" && ok "T8 state pointer parsed from AGENTS.md" || bad "T8 state pointer parsed"
grep -q 'plans/ MISSING' <<<"$o" && grep -q 'status/ present (2 files)' <<<"$o" && ok "T9 structure dirs reported with counts" || bad "T9 structure dirs"
grep -q 'OPEN QUESTIONS=2' <<<"$o" && ok "T10 open-question count" || bad "T10 open-question count"
grep -q 'branch=main dirty=1' <<<"$o" && ok "T11 linked repo reported (branch, dirty, last commit)" || bad "T11 linked repo reported"

# T12 — debt comes with the command that clears it, vault already filled in.
grep -q 'next-command\[operator\]: bash .*vault-init.sh --project PhD-Demo --vault '"$R"'/vault' <<<"$o" \
  && ok "T12 debt line prints vault-init with resolved paths" || bad "T12 debt line prints the command" "$(grep next-command <<<"$o" | head -1)"

# T13 — a repos.txt whose only path-looking lines are comments must report "none declared", not invent a
# repo out of the file's own format documentation.
o=$(bash "$T" Other-DEMO-two --vault "$R/vault" 2>&1)
grep -q 'none declared' <<<"$o" && ok "T13 comment-only repos.txt reported as undeclared" || bad "T13 comment-only repos.txt" "$(grep -A2 REPOS <<<"$o" | head -3)"

echo "---- triage recon: $((pass-fail<0?0:pass)) passed, $fail failed"
[ $fail -eq 0 ] || exit 1
