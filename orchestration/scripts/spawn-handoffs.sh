#!/usr/bin/env bash
# spawn-handoffs.sh — deliver one batch's handoff prompts to worker panes. The brain prints the
# handoff (rule 3d) and runs THIS after José's one confirmation; it never types pane commands (R3).
# One tab per part (R6): `tab create --label <part>` once per batch, every worker split from that
# tab's FIRST pane (`.result.root_pane.pane_id` — verified live against herdr 0.9.1, 2026-10-26;
# note `pane split --current` would be wrong here: the script runs in the brain's pane, old tab).
# Dual naming (R6): `herdr agent rename <pane> <part>-<slice>` (herdr wait/prompt/get target) and
# `pi --name <part>-<slice>` forwarded through pi-agents (intercom presence name). Names derive
# from wt, matching herdr's rename constraint [a-z][a-z0-9_-]{0,31}.
#
#   spawn-handoffs.sh [--manifest FILE] [--part P]     # spawn the batch
#   spawn-handoffs.sh close --part P                   # close the part's tab (after worktree.sh prune)
#
# Manifest: TSV, `#` comment lines, one row per worker: role<TAB>wt<TAB>repo<TAB>prompt_file[<TAB>note]
#   wt = part/slice → worktree <repo>/.worktrees/<part>-<slice> via worktree.sh add (re-add on an
#   existing worktree is idempotent — verified live 2026-10-26 — but the script pre-creates anyway so
#   a worktree failure is a per-row error here, not a dead pane).
# prompt_file is an ABSOLUTE path: it reaches pi as `@file`, resolved from the pane's cwd = worktree.
#
# Env: HERDR_BIN (default herdr) — fixture shims run this without Herdr (A4/A5)
#      PI_WORKTREE_SH (default ~/.pi/agent/scripts/worktree.sh), HERDR_WORKSPACE_ID (tab's workspace)
# A failing row is reported as `ERROR …` and the batch continues (R3). No hand-composed commands:
# the pane runs `pi-agents … -- --name X @prompt` built with printf %q per argv, and the printed
# next-command lines are literal R1-style strings (emitter owner: worktree.sh, slice emitter).
# Exit: 0 all rows spawned · 1 some rows failed (the rest still spawned) · 2 usage/env/batch-cap.
set -euo pipefail

die() { echo "spawn-handoffs: $*" >&2; exit 2; }

usage() { cat <<'EOF'
usage: spawn-handoffs.sh --manifest FILE [--part P]    spawn the batch
       spawn-handoffs.sh close --part P                close the part's tab

Manifest: TSV, '#' comment lines, one row per worker:
  role<TAB>wt<TAB>repo<TAB>prompt_file[<TAB>note]
    role         worker|calcs|scout|verifier|integrator
    wt           part/slice (exactly one slash) -> worktree <repo>/.worktrees/<part>-<slice>
    repo         absolute repo path
    prompt_file  absolute path (reaches pi as @file, resolved from the pane's cwd = worktree)
    note         optional one-line human context for the SPAWN? summary

Convention: manifest lives beside the prompt files:
  .agent/scratch/handoffs/<YYYY-MM-DD>-<part>.manifest.tsv

Example:
  bash ~/.pi/agent/scripts/spawn-handoffs.sh \
    --manifest .agent/scratch/handoffs/2026-10-27-spawn-handoffs.smoke.manifest.tsv \
    --part spawn-handoffs
EOF
}

HERDR_BIN="${HERDR_BIN:-herdr}"
WT_SCRIPT="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
NAME_RE='^[a-z][a-z0-9_-]{0,31}$'

CMD=spawn
[ "${1:-}" = "close" ] && { CMD=close; shift; }
MANIFEST="" PART=""
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="${2:?}"; shift 2;;
    --part)     PART="${2:?}"; shift 2;;
    --help|-h)  usage; exit 0;;
    *) usage >&2; die "unknown arg $1";;
  esac
done
command -v jq >/dev/null || die "jq not found — the herdr JSON envelope is parsed with jq"

herdr_tab_ids() {  # tabs whose label is exactly $1, one id per line
  "$HERDR_BIN" tab list | jq -r --arg l "$1" '.result.tabs[] | select(.label == $l) | .tab_id'
}

if [ "$CMD" = close ]; then
  [ -n "$PART" ] || die "close needs --part"
  # sort, not head -1: two tabs may share the label (a crashed earlier batch leaves one behind), and
  # tab-list order is not creation order (live wB workspace, 2026-10-26) — close the newest tab id.
  TAB_ID="$(herdr_tab_ids "$PART" | sort | tail -1)"
  [ -n "$TAB_ID" ] || die "no tab labelled '$PART' — nothing to close"
  "$HERDR_BIN" tab close "$TAB_ID"
  echo "CLOSED TAB=$TAB_ID label=$PART"
  exit 0
fi

# ---------------------------------------------------------------- parse + validate the manifest
[ -n "$MANIFEST" ] || { usage >&2; die "--manifest required"; }
[ -f "$MANIFEST" ] || die "no such manifest: $MANIFEST"
[ -f "$WT_SCRIPT" ] || [ -x "$WT_SCRIPT" ] || die "missing $WT_SCRIPT"

ROW_ROLE=() ROW_SLICE=() ROW_REPO=() ROW_PROMPT=() ROW_NAME=() ROW_WTREF=() ROW_NOTE=()
failed=0 lineno=0
row_err() { echo "ERROR $MANIFEST:$1: $2"; failed=$((failed+1)); }

while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno+1))
  case "$line" in ''|\#*) continue;; esac
  IFS=$'\t' read -r -a f <<<"$line"
  # 5th column (note) is optional: one line of human context for the brain's SPAWN? summary.
  if [ "${#f[@]}" -ne 4 ] && [ "${#f[@]}" -ne 5 ]; then row_err "$lineno" "want 4 (or 5 with note) tab-separated columns (role wt repo prompt_file [note]), got ${#f[@]} — skipped"; continue; fi
  role="${f[0]}"; wtref="${f[1]}"; repo="${f[2]}"; prompt="${f[3]}"; note="${f[4]:-}"
  case "$wtref" in
    */*/*) row_err "$lineno" "wt '$wtref' is not part/slice (exactly one slash) — skipped"; continue;;
    */*) :;;
    *) row_err "$lineno" "wt '$wtref' is not part/slice — skipped"; continue;;
  esac
  part="${wtref%%/*}"; slice="${wtref#*/}"
  name="$part-$slice"
  if ! [[ "$name" =~ $NAME_RE ]]; then
    row_err "$lineno" "'$name' breaks herdr rename constraint [a-z][a-z0-9_-]{0,31} — skipped"
    continue
  fi
  if [ -n "$PART" ] && [ "$part" != "$PART" ]; then
    row_err "$lineno" "wt part '$part' != --part '$PART' — one batch = one part/tab — skipped"
    continue
  fi
  if [ ! -f "$prompt" ]; then row_err "$lineno" "prompt file not found: $prompt — skipped"; continue; fi
  PART="${PART:-$part}"
  ROW_ROLE+=("$role"); ROW_SLICE+=("$slice"); ROW_REPO+=("$repo"); ROW_PROMPT+=("$prompt")
  ROW_NAME+=("$name"); ROW_WTREF+=("$wtref"); ROW_NOTE+=("$note")
done < "$MANIFEST"

[ ${#ROW_NAME[@]} -gt 0 ] || { echo "spawn-handoffs: 0 valid rows ($failed error(s))" >&2; exit 1; }

# ---------------------------------------------------------------- batch-size guardrail (brain, 2026-10-26)
# One confirmation per batch must mean one batch: a big manifest must not spawn N panes at José.
# Cap lives in .agent-paths (`batch_size: N`, machine-local, next to test_cmd); pending deltas in
# status_dir are yesterday's workers still un-rolled-up. Refusal is BEFORE the tab exists — zero
# side effects, exit 2, no partial batch. Unset key = no cap (old repos) but never silent.
REPO0="${ROW_REPO[0]}"
AP="$REPO0/.agent-paths"
BATCH_SIZE="" STATUS_DIR=""
if [ -f "$AP" ]; then
  BATCH_SIZE="$(awk -F': ' '$1=="batch_size" {print substr($0, length("batch_size")+3); exit}' "$AP")"
  STATUS_DIR="$(awk -F': ' '$1=="status_dir" {print substr($0, length("status_dir")+3); exit}' "$AP")"
fi
NROWS=${#ROW_NAME[@]}
if [ -z "$BATCH_SIZE" ]; then
  echo "batch-gate: NOTE no batch_size in $AP — no cap enforced (add 'batch_size: N' to enable)"
else
  PENDING=0
  [ -n "$STATUS_DIR" ] && [ -d "$STATUS_DIR" ] \
    && PENDING="$(find "$STATUS_DIR" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
  CAP=$((BATCH_SIZE - PENDING))
  echo "batch-gate rows=$NROWS batch_size=$BATCH_SIZE pending_deltas=$PENDING cap=$CAP"
  [ "$NROWS" -le "$CAP" ] \
    || die "manifest has $NROWS valid rows; batch_size=$BATCH_SIZE minus $PENDING pending delta(s) in ${STATUS_DIR:-status_dir unset} = $CAP. Wait for deltas to roll up (/merge-status) or raise batch_size in $AP"
fi

# ---------------------------------------------------------------- the part's tab (R6, once per batch)
WS_ARGS=()
[ -n "${HERDR_WORKSPACE_ID:-}" ] && WS_ARGS=(--workspace "$HERDR_WORKSPACE_ID")
if ! tab_json=$("$HERDR_BIN" tab create ${WS_ARGS[@]+"${WS_ARGS[@]}"} --label "$PART" 2>&1); then
  die "herdr tab create --label $PART failed: $tab_json"
fi
# Verified live 2026-10-26 (herdr 0.9.1): the new tab's first pane id is at .result.root_pane.pane_id
# (the brief's ASSUMPTION — JSON DOES expose it). The tab id rides along at .result.tab.tab_id.
TAB_ID="$(jq -er '.result.tab.tab_id' <<<"$tab_json")" || die "tab create JSON has no .result.tab.tab_id: $tab_json"
TAB_PANE="$(jq -er '.result.root_pane.pane_id' <<<"$tab_json")" || die "tab create JSON has no .result.root_pane.pane_id: $tab_json"
echo "TAB=$TAB_ID PANE=$TAB_PANE label=$PART"

# ---------------------------------------------------------------- spawn each row
MAP=() NEXTCMDS=()
spawned=0
i=-1
for i in "${!ROW_NAME[@]}"; do
  role="${ROW_ROLE[$i]}"; slice="${ROW_SLICE[$i]}"; repo="${ROW_REPO[$i]}"
  prompt="${ROW_PROMPT[$i]}"; name="${ROW_NAME[$i]}"; wtref="${ROW_WTREF[$i]}"; note="${ROW_NOTE[$i]}"
  err() { row_err "row $((i+1))" "$name: $1"; }

  if ! add_out=$("$WT_SCRIPT" add --repo "$repo" --part "${wtref%%/*}" --agent "$slice" --role "$role" 2>&1); then
    err "worktree.sh add failed: $add_out"; continue
  fi
  wt="$(sed -n 's/^WORKTREE=//p' <<<"$add_out" | head -1)"
  if [ -z "$wt" ]; then err "no WORKTREE= line in worktree.sh add output: $add_out"; continue; fi
  delta="$(sed -n 's/^DELTA=//p' <<<"$add_out" | head -1)"

  # Split targets the TAB's first pane explicitly — never --current (that is the brain's pane).
  if ! split_json=$("$HERDR_BIN" pane split "$TAB_PANE" --direction right --cwd "$wt" --no-focus 2>&1); then
    err "pane split failed: $split_json"; continue
  fi
  if ! pane="$(jq -er '.result.pane.pane_id' <<<"$split_json" 2>/dev/null)"; then
    err "pane split JSON has no .result.pane.pane_id: $split_json"; continue
  fi

  # One argv element per token, %q-quoted, joined: pane run takes exactly ONE positional command
  # string which the pane's shell interprets (digest 1 §2). `--` hands pi the rest verbatim:
  # --name seeds the intercom presence name, @file seeds turn 1 from the worktree cwd.
  cmd="$(printf '%q ' pi-agents "$role" --repo "$repo" --wt "$wtref" -- --name "$name" "@$prompt")"
  if ! "$HERDR_BIN" pane run "$pane" "$cmd"; then err "pane run failed for pane $pane"; continue; fi
  # Rename retry: the pane's pi registers as an agent asynchronously (dogfood, 2026-10-27:
  # SPAWNED=1 FAILED=1 on a healthy worker) — retry before counting a failure.
  rn_ok=""
  for _ in 1 2 3; do
    if "$HERDR_BIN" agent rename "$pane" "$name"; then rn_ok=1; break; fi
    sleep 1
  done
  if [ -z "$rn_ok" ]; then
    # The worker is already running at this point — report, do not lose the mapping.
    echo "ERROR $MANIFEST:row $((i+1)): agent rename $pane $name failed after 3 attempts (worker still spawned)"
    failed=$((failed+1))
  fi

  MAP+=("MAP slice=$slice TAB=$TAB_ID PANE=$pane NAME=$name INTERCOM=$name DELTA=${delta:-unknown} NOTE=$note")
  NEXTCMDS+=("next-command[operator]: pi-agents $role --repo $repo --wt $wtref")
  spawned=$((spawned+1))
done

# ---------------------------------------------------------------- printout (§0 step 5)
for m in ${MAP[@]+"${MAP[@]}"}; do echo "$m"; done
for c in ${NEXTCMDS[@]+"${NEXTCMDS[@]}"}; do echo "$c"; done
# Rollup line: merge-status.py's real argparse accepts --repo and --part (verified in its source,
# slice emitter owns the same string in worktree.sh add's tail).
[ ${#NEXTCMDS[@]} -gt 0 ] && echo "next-command[operator]: python3 $HOME/.pi/agent/scripts/merge-status.py --repo ${ROW_REPO[0]} --part $PART"
echo "SPAWNED=$spawned FAILED=$failed TAB=$TAB_ID"
[ "$failed" -eq 0 ] || exit 1
