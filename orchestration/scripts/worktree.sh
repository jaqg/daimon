#!/usr/bin/env bash
# worktree.sh — one git worktree per worker/calcs agent, plus the `.agent-paths` file that ties a
# repo to its vault project. Branch names and worktree paths are DERIVED, never invented by an agent:
# the integrator is forbidden from guessing them, so they have to come from somewhere mechanical.
#
#   worktree.sh init   --repo R --vault V [--part P] [--test-cmd C] [--integration-branch B]
#   worktree.sh add    --repo R --part P --agent A [--role worker|calcs|scout] [--base BR] [--link PATH]...
#   worktree.sh integrate --repo R --part P [--base BR]   # the integrator's worktree, on integration/P
#   worktree.sh list   --repo R
#   worktree.sh remove --repo R --part P --agent A [--force]
#   worktree.sh prune  --repo R --part P          # drop worktrees whose branch is already merged
#
# Exit codes: 0 ok · 2 bad usage · 5 refused (would lose work / branch not merged).
set -euo pipefail

die() { echo "worktree: $*" >&2; exit 2; }
refuse() { echo "worktree: REFUSED — $*" >&2; exit 5; }

CMD="${1:-}"; [[ -n "$CMD" ]] || die "need a subcommand (init|add|list|remove|prune)"
shift

REPO="" VAULT="" PART="" AGENT="" ROLE="worker" BASE="" TESTCMD="" INTEG="" FORCE=0
LINKS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --vault) VAULT="$2"; shift 2;;
    --part) PART="$2"; shift 2;;
    --agent) AGENT="$2"; shift 2;;
    --role) ROLE="$2"; shift 2;;
    --base) BASE="$2"; shift 2;;
    --test-cmd) TESTCMD="$2"; shift 2;;
    --integration-branch) INTEG="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --link) LINKS+=("$2"); shift 2;;
    *) die "unknown arg $1";;
  esac
done

[[ -n "$REPO" ]] || die "--repo required"
REPO="$(cd "$REPO" && pwd)"
git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || die "$REPO is not a git repo"
WT_ROOT="$REPO/.worktrees"

exclude_file() {  # git prints info/exclude relative to cwd; we always mean it relative to $REPO
  local x
  x="$(git -C "$REPO" rev-parse --git-path info/exclude)"
  case "$x" in /*) :;; *) x="$REPO/$x";; esac
  mkdir -p "$(dirname "$x")"
  echo "$x"
}

old_val() {  # keep whatever was already set for a key we were not told to change
  # Must never fail: `set -e` + command substitution means a non-zero awk here silently aborted
  # `init` on a fresh repo (awk exits 2 when .agent-paths does not exist yet). Caught by gate-test B1.
  [ -f "$REPO/.agent-paths" ] || return 0
  awk -F': ' -v k="$1" '$1==k {print substr($0, length(k)+3)}' "$REPO/.agent-paths" | head -1
  return 0
}

paths_file() {
  local f="$REPO/.agent-paths" tmp
  VAULT="${VAULT:-$(old_val vault_project)}"
  STATUS_DIR="${STATUS_DIR:-$(old_val status_dir)}"
  AI_OUT="${AI_OUT:-$(old_val ai_out)}"
  INTEG="${INTEG:-$(old_val integration_branch)}"
  TESTCMD="${TESTCMD:-$(old_val test_cmd)}"
  tmp="$(mktemp)"
  {
    echo "# .agent-paths — written by worktree.sh; the brain owns the values, agents only read them."
    echo "# Contract: daimon/orchestration/scripts/templates/agent-paths.md"
    echo "repo: $REPO"
    echo "vault_project: $VAULT"
    echo "status_dir: $STATUS_DIR"
    echo "ai_out: $AI_OUT"
    echo "worktrees: $WT_ROOT"
    echo "integration_branch: $INTEG"
    echo "test_cmd: $TESTCMD"
  } > "$tmp"
  mv "$tmp" "$f"
}

case "$CMD" in
  init)
    [[ -n "$VAULT" ]] || VAULT="$(old_val vault_project)"
    [[ -n "$VAULT" ]] || die "init needs --vault <10-Projects/X> (or an existing .agent-paths to inherit)"
    STATUS_DIR="$VAULT/status"; AI_OUT="$VAULT/ai-out"; PLANS_DIR="$VAULT/plans"
    # plans/ is where /brain writes the plan and where /merge-status reads specs from; it was the one
    # element of the contract that nothing created, so 7/7 vault projects lacked it (2026-10-25).
    mkdir -p "$STATUS_DIR" "$AI_OUT" "$PLANS_DIR" "$REPO/.agent/status" "$REPO/.agent/scratch" "$REPO/.agent/digests"
    # `.gitkeep` so an empty plans/status/ai-out survives a vault commit — vault-init.sh does the same,
    # and the verifier (2026-10-25) caught that the two tools matched at directory level only.
    for d in "$PLANS_DIR" "$STATUS_DIR" "$AI_OUT"; do
      [[ -e "$d/.gitkeep" ]] || : > "$d/.gitkeep"
    done
    [[ -n "$PART" ]] && INTEG="${INTEG:-integration/$PART}"
    [[ -z "$INTEG" ]] && INTEG="$(old_val integration_branch)"
    paths_file
    # Keep the whole apparatus out of the repo's history WITHOUT editing .gitignore:
    x="$(exclude_file)"
    for pat in ".agent/" ".agent-paths" ".worktrees/" ".pi-role"; do
      grep -qxF "$pat" "$x" 2>/dev/null || echo "$pat" >> "$x"
    done
    echo "init: $REPO/.agent-paths written (status_dir=$STATUS_DIR integration_branch=${INTEG:-unset})"
    ;;

  add)
    [[ -n "$PART" && -n "$AGENT" ]] || die "add needs --part and --agent"
    case "$ROLE" in worker|calcs|scout) ;; *) die "--role must be worker|calcs|scout";; esac
    WT="$WT_ROOT/$PART-$AGENT"; BR="agent/$PART-$AGENT"
    # Check the contract BEFORE creating anything: the old order built the worktree, wrote .pi-role,
    # linked resources and only then refused for a missing integration_branch, leaving a half-made
    # leaf that the next invocation had to reason about.
    grep -q '^integration_branch: .*$' "$REPO/.agent-paths" 2>/dev/null \
      || die "no integration_branch in $REPO/.agent-paths — run init first (pi-agents does this automatically)"
    mkdir -p "$WT_ROOT"
    if [[ -d "$WT" ]]; then
      echo "add: worktree already there: $WT ($BR)"
    else
      [[ -n "$BASE" ]] || BASE="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
      if git -C "$REPO" show-ref --verify --quiet "refs/heads/$BR"; then
        git -C "$REPO" worktree add "$WT" "$BR" >/dev/null
      else
        git -C "$REPO" worktree add -b "$BR" "$WT" "$BASE" >/dev/null
      fi
    fi
    # The gate is only as good as the role declaration, and a spawned agent never declares one.
    echo "$ROLE" > "$WT/.pi-role"
    # One status queue per repo, not one per worktree. `.agent/` is untracked, so a fresh worktree would
    # otherwise get its own `.agent/status`, and a leaf's delta would strand where no rollup ever reads it
    # (measured 2026-10-25: slice A's delta sat in .worktrees/structure-init-script/.agent/status while
    # merge-status only reads $REPO/.agent/status). Symlinking makes the documented relative path correct
    # from inside the worktree, so the leaf cannot get it wrong. Runs for existing worktrees too, so
    # re-adding repairs a stranded queue.
    mkdir -p "$REPO/.agent/status" "$WT/.agent"
    if [[ -d "$WT/.agent/status" && ! -L "$WT/.agent/status" ]]; then
      mv "$WT/.agent/status"/*.md "$WT/.agent/status"/*.md.processed "$REPO/.agent/status/" 2>/dev/null || true
      rmdir "$WT/.agent/status" 2>/dev/null || refuse "$WT/.agent/status holds non-delta files; move them by hand"
    fi
    [[ -L "$WT/.agent/status" ]] || ln -s "$REPO/.agent/status" "$WT/.agent/status"
    # Exclude the scaffolding locally: an untracked .pi-role or a linked .venv would otherwise make
    # every worktree look dirty forever, and `remove`/`prune` would refuse on it.
    EXC="$(exclude_file)"
    for pat in .pi-role ${LINKS[@]+"${LINKS[@]}"}; do
      grep -qxF "$pat" "$EXC" 2>/dev/null || echo "$pat" >> "$EXC"
    done
    for L in ${LINKS[@]+"${LINKS[@]}"}; do
      [[ -e "$REPO/$L" || -d "$REPO/$L" ]] || refuse "--link $L does not exist in $REPO"
      if [[ ! -e "$WT/$L" && ! -L "$WT/$L" ]]; then
        mkdir -p "$WT/$(dirname "$L")"
        ln -s "$REPO/$L" "$WT/$L"
        echo "add: linked $L -> $REPO/$L"
      fi
    done
    echo "WORKTREE=$WT"
    echo "BRANCH=$BR"
    echo "ROLE=$ROLE"
    echo "PATHS=$REPO/.agent-paths"
    echo "PI_ROLE=$WT/.pi-role"
    # Exact delta name, so the dot convention is not something each leaf re-derives by hand.
    echo "DELTA=$REPO/.agent/status/$(date +%F)-$PART.$AGENT.md"
    # R1: the launch line for THIS row, machine-emitted (rule 3c forbids composing it from memory).
    # The rollup line's flags come from merge-status.py's own argparse (--repo and --part are both
    # real), not from either prose contract that disagreed on --part.
    echo "next-command[operator]: pi-agents $ROLE --repo $REPO --wt $PART/$AGENT"
    echo "next-command[operator]: python3 \$HOME/.pi/agent/scripts/merge-status.py --repo $REPO --part $PART"
    ;;

  integrate)
    [[ -n "$PART" ]] || die "integrate needs --part"
    INTEG_BRANCH="integration/$PART"
    WT="$WT_ROOT/integrate-$PART"
    mkdir -p "$WT_ROOT"
    if [[ ! -d "$WT" ]]; then
      # --base defaults to main, NOT to wherever the brain happens to be standing, so an integration
      # branch never silently inherits an unmerged feature tip.
      [[ -n "$BASE" ]] || BASE="main"
      if git -C "$REPO" show-ref --verify --quiet "refs/heads/$INTEG_BRANCH"; then
        git -C "$REPO" worktree add "$WT" "$INTEG_BRANCH" >/dev/null
      else
        git -C "$REPO" worktree add -b "$INTEG_BRANCH" "$WT" "$BASE" >/dev/null
      fi
    fi
    echo integrator > "$WT/.pi-role"
    EXC="$(exclude_file)"
    grep -qxF .pi-role "$EXC" 2>/dev/null || echo .pi-role >> "$EXC"
    echo "WORKTREE=$WT"; echo "BRANCH=$INTEG_BRANCH"; echo "ROLE=integrator"
    echo "note: the merge lock in role-gate.ts lets this session merge ONLY while HEAD is $INTEG_BRANCH"
    # Byte-identical to the line merge-status.py prints in its post-worker rollup (next_commands),
    # so the two emitters can never drift apart.
    echo "next-command[operator]: pi-agents integrator --repo $WT"
    ;;

  lab)
    # A checker must not share a lab with a producer (contract rule). Until now the machinery had no way
    # to express that: `/merge-status` could tell you to verify a part but nobody could say *where*, so
    # the verifier ended up reading the integrator's own worktree. `lab` makes a throwaway detached
    # checkout of the ref under review, tagged with the checker's role, and prints the pane command.
    [[ -n "$PART" ]] || die "lab needs --part"
    # Default ref, in the order a checker actually needs it: the integration branch if the part has one
    # (the normal pre-landing check), else the newest agent branch for the part (verifying one slice while
    # it is still separate), else main. An earlier version insisted on integration/<part> and so refused
    # the single-slice case, which is exactly when cross-lab checking was invented.
    if [[ -z "${BASE:-}" ]]; then
      if git -C "$REPO" show-ref --verify --quiet "refs/heads/integration/$PART"; then BASE="integration/$PART"
      else BASE="$(git -C "$REPO" branch --list "agent/$PART-*" --format='%(refname:short)' | tail -1)"; fi
      [[ -n "$BASE" ]] || BASE="main"
    fi
    REF="$BASE"
    git -C "$REPO" show-ref --verify --quiet "refs/heads/$REF" \
      || git -C "$REPO" rev-parse --verify --quiet "$REF" >/dev/null \
      || die "lab: no such ref: $REF (pass --base <ref>)"
    LAB="$REPO/.labs/$PART"
    if [[ -e "$LAB" ]]; then
      # Re-verifying a part is normal (the integrator landed a fix, or the first verdict was wrong), so an
      # existing lab is reused rather than refused — but never silently moved: a worktree can still hold an
      # open session, and pulling its HEAD out from under a verifier is how a verdict describes a commit
      # nobody looked at. If it points elsewhere, the refresh command is printed for the operator.
      if git -C "$LAB" rev-parse --git-dir >/dev/null 2>&1; then
        CUR="$(git -C "$LAB" rev-parse --short HEAD 2>/dev/null || echo '?')"
        WANT="$(git -C "$REPO" rev-parse --short "$REF" 2>/dev/null || echo '?')"
        echo "LAB=$LAB (existing)"
        if [[ "$CUR" == "$WANT" ]]; then
          echo "REF=$REF (already checked out at $CUR)"
        else
          echo "REF=$REF — lab is at $CUR, NOT refreshed. operator: git -C $LAB checkout --detach $REF"
        fi
        echo "ROLE=$(cat "$LAB/.pi-role" 2>/dev/null || echo verifier)"
        echo "next-command[operator]: pi-agents verifier --repo $LAB"
        exit 0
      fi
      if [[ -L "$LAB" ]]; then rm "$LAB"; else refuse "$LAB exists and is not a git worktree — remove it by hand"; fi
    fi
    git -C "$REPO" worktree add --detach "$LAB" "$REF" >/dev/null 2>&1 \
      || die "lab: git worktree add --detach $LAB $REF failed"
    # Hardcoded, not ${ROLE:-verifier}: the global `ROLE` already defaults to `worker` from the shared
    # flag parser, so honouring it tagged every checker workspace as a producer. A lab is a checker's
    # workspace by definition; if another checker tier needs one, add --checker-role rather than reuse ROLE.
    echo verifier > "$LAB/.pi-role"
    grep -qxF '.labs/' "$(exclude_file)" 2>/dev/null || echo '.labs/' >> "$(exclude_file)"
    echo "LAB=$LAB"; echo "REF=$REF"; echo "ROLE=verifier"
    echo "next-command[operator]: pi-agents verifier --repo $LAB"
    ;;

  list)
    git -C "$REPO" worktree list
    ;;

  remove)
    [[ -n "$PART" && -n "$AGENT" ]] || die "remove needs --part and --agent"
    WT="$WT_ROOT/$PART-$AGENT"; BR="agent/$PART-$AGENT"
    [[ -d "$WT" ]] || { echo "remove: no worktree at $WT"; exit 0; }
    if [[ $FORCE -eq 0 ]]; then
      dirty="$(git -C "$WT" status --porcelain 2>/dev/null | grep -v '^?? \.pi-role$' || true)"
      [[ -z "$dirty" ]] || refuse "$WT has uncommitted changes:$(echo "$dirty" | head -5 | sed 's/^/   /')"
      unmerged="$(git -C "$REPO" log --format=%h "$BR" --not HEAD 2>/dev/null || true)"
      INTEG_BRANCH="$(old_val integration_branch)"
      if [[ -n "$INTEG_BRANCH" ]] && git -C "$REPO" show-ref --verify --quiet "refs/heads/$INTEG_BRANCH"; then
        unmerged="$(git -C "$REPO" log --format=%h "$BR" --not "$INTEG_BRANCH" 2>/dev/null || true)"
      fi
      [[ -z "$unmerged" ]] || refuse "$BR has $(echo "$unmerged" | wc -l) commit(s) not in ${INTEG_BRANCH:-HEAD} — merge or delete the branch by hand"
    fi
    git -C "$REPO" worktree remove "$WT"
    echo "remove: dropped $WT (branch $BR kept; deltas kept as .md.processed until the next prune)"
    ;;

  prune)
    [[ -n "$PART" ]] || die "prune needs --part"
    # Prefer the per-part name (what `integrate` creates and what merge-status derives); fall back to the
    # contract file only if that ref does not exist. Reading the contract first meant pruning looked for a
    # branch nobody created when a second part shared the repo.
    INTEG_BRANCH="integration/$PART"
    if ! git -C "$REPO" show-ref --verify --quiet "refs/heads/$INTEG_BRANCH"; then
      ALT="$(old_val integration_branch)"
      [[ -n "$ALT" && "$ALT" != "$INTEG_BRANCH" ]] && git -C "$REPO" show-ref --verify --quiet "refs/heads/$ALT" \
        && INTEG_BRANCH="$ALT"
    fi
    # Same rule as merge-status: landed means the part's work is in main. An integration branch that was
    # created and never merged equals main, and would otherwise be "landed" with nothing in it.
    LANDED=0
    if git -C "$REPO" merge-base --is-ancestor "$INTEG_BRANCH" main 2>/dev/null; then
      LANDED=1
      for BRX in $(git -C "$REPO" branch --list "agent/$PART-*" --format='%(refname:short)'); do
        git -C "$REPO" merge-base --is-ancestor "$BRX" main 2>/dev/null || { LANDED=0; break; }
      done
    fi
    n=0
    for WT in "$WT_ROOT"/"$PART"-*; do
      [[ -d "$WT" ]] || continue
      name="$(basename "$WT")"; BR="agent/${name}"
      if ! git -C "$REPO" show-ref --verify --quiet "refs/heads/$INTEG_BRANCH"; then
        echo "prune: $name kept — integration branch '${INTEG_BRANCH}' does not exist yet"
        continue
      fi
      if git -C "$REPO" merge-base --is-ancestor "$BR" "$INTEG_BRANCH" 2>/dev/null; then
        dirty="$(git -C "$WT" status --porcelain | grep -v '^?? \.pi-role$' || true)"
        [[ -z "$dirty" ]] || { echo "prune: $name dirty, kept"; continue; }
        git -C "$REPO" worktree remove "$WT" && echo "prune: dropped $name (merged into $INTEG_BRANCH)" && n=$((n+1))
        git -C "$REPO" branch -d "$BR" 2>/dev/null || echo "prune: $BR left — not deletable from here"
      else
        echo "prune: $name still ahead of $INTEG_BRANCH, kept"
      fi
    done

    # A branch is not the same thing as its worktree: a slice pruned on an earlier pass keeps its branch
    # when `branch -d` was refused then (not yet in main), and nothing ever revisits it — the part would
    # report phantom branches forever. Sweep by ref, independent of any directory.
    for BRX in $(git -C "$REPO" branch --list "agent/$PART-*" --format='%(refname:short)'); do
      [[ -d "$WT_ROOT/${BRX#agent/}" ]] && continue
      if [[ $LANDED -eq 1 ]] && git -C "$REPO" merge-base --is-ancestor "$BRX" main 2>/dev/null; then
        git -C "$REPO" branch -d "$BRX" >/dev/null 2>&1 \
          && echo "prune: dropped $BRX (in main, no worktree)" || true
      fi
    done

    # The integration worktree and the checker's lab matched no glob here, so both survived the landing
    # that finished the part: `git worktree list` kept advertising directories whose whole purpose was over.
    # Removal is gated on the same fact a human would check — the branch is in main, and the tree is clean.
    IWT="$WT_ROOT/integrate-$PART"
    if [[ -e "$IWT" ]]; then
      if [[ $LANDED -eq 1 ]]; then
        dirty="$(git -C "$IWT" status --porcelain 2>/dev/null | grep -v '^?? \.pi-role$' || true)"
        if [[ -z "$dirty" ]]; then
          git -C "$REPO" worktree remove "$IWT" && echo "prune: dropped integrate-$PART" && n=$((n+1))
          git -C "$REPO" branch -d "$INTEG_BRANCH" 2>/dev/null || echo "prune: $INTEG_BRANCH left — not deletable from here"
        else
          echo "prune: integrate-$PART dirty, kept (the integrator may still be in there)"
        fi
      else
        echo "prune: integrate-$PART kept — $INTEG_BRANCH is not in main yet"
      fi
    fi
    LAB="$REPO/.labs/$PART"
    if [[ -e "$LAB" ]]; then
      if [[ $LANDED -ne 1 ]]; then
        echo "prune: .labs/$PART kept — verdict still open for this part"
      else
        dirty="$(git -C "$LAB" status --porcelain 2>/dev/null | grep -v '^?? \.pi-role$' || true)"
        if [[ -z "$dirty" ]]; then
          git -C "$REPO" worktree remove --force "$LAB" 2>/dev/null \
            || { rm -rf "$LAB"; git -C "$REPO" worktree prune; }
          echo "prune: dropped lab .labs/$PART"; n=$((n+1))
        else
          echo "prune: .labs/$PART dirty, kept (unsaved verifier notes?)"
        fi
      fi
    fi
    echo "prune: $n worktree(s) removed"
    ;;

  *) die "unknown subcommand $CMD (init|add|integrate|list|remove|prune)";;
esac
