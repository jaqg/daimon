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
    INTEG_BRANCH="$(old_val integration_branch)"
    n=0
    for WT in "$WT_ROOT"/$PART-*; do
      [[ -d "$WT" ]] || continue
      name="$(basename "$WT")"; BR="agent/${name}"
      if [[ -z "$INTEG_BRANCH" ]] || ! git -C "$REPO" show-ref --verify --quiet "refs/heads/$INTEG_BRANCH"; then
        echo "prune: $name kept — integration branch '${INTEG_BRANCH:-unset}' does not exist yet"
        continue
      fi
      if git -C "$REPO" merge-base --is-ancestor "$BR" "$INTEG_BRANCH" 2>/dev/null; then
        dirty="$(git -C "$WT" status --porcelain | grep -v '^?? \.pi-role$' || true)"
        [[ -z "$dirty" ]] || { echo "prune: $name dirty, kept"; continue; }
        git -C "$REPO" worktree remove "$WT" && echo "prune: dropped $name (merged into $INTEG_BRANCH)" && n=$((n+1))
        git -C "$REPO" branch -d "$BR" 2>/dev/null || true
      else
        echo "prune: $name still ahead of $INTEG_BRANCH, kept"
      fi
    done
    echo "prune: $n worktree(s) removed"
    ;;

  *) die "unknown subcommand $CMD (init|add|integrate|list|remove|prune)";;
esac
