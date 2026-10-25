#!/usr/bin/env bash
# pi-agents — start a pi session that IS the role, not a session you tell to be the role.
#
# A hand-launched pane gets two things wrong by default: it inherits your DEFAULT model (so a "worker"
# pane quietly runs the brain's mimo-v2.6-pro:high), and the tool gate never engages because the gate
# reads `.pi-role` from the working directory, not from your intention. This script supplies both.
#
#   pi-agents                      pick a role interactively
#   pi-agents worker               start as worker in the current directory
#   pi-agents worker --repo ~/x/proj --wt partB/desc
#                                 create/enter the worker's worktree first (gate file written inside)
#   pi-agents brain --claim        write `brain` into ./.pi-role here, then start
#   pi-agents scout --dry          print the pi command, run nothing
#   pi-agents worker --strict    also apply the agent file's `tools:` line as a hard whitelist
#   pi-agents verifier -- -p "…"  extra args after -- go straight to pi
set -euo pipefail

AGENTS_DIR="${PI_AGENTS_DIR:-$HOME/.pi/agent/agents}"
WT_SCRIPT="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
RETIRED="implementer planner"          # kept as pinned shims; a package re-creates them each session

die() { echo "pi-agents: $*" >&2; exit 2; }

vault_root() {  # where 10-Projects/ lives: env, then a one-line config file
  [ -n "${PI_VAULT_ROOT:-}" ] && { echo "$PI_VAULT_ROOT"; return; }
  [ -n "${VAULT_ROOT:-}" ] && { echo "$VAULT_ROOT"; return; }
  [ -f "$HOME/.config/pi/vault-root" ] && { head -1 "$HOME/.config/pi/vault-root" | tr -d "[:space:]"; return; }
  echo ""
}

guess_vault() {  # $1 = repo path; mirror worktree.sh's reverse lookup, then a name match
  local repo="$1" vr vproj
  vr="$(vault_root)"; [ -n "$vr" ] || return 0
  for vproj in "$vr"/10-Projects/* "$vr"/10-Projects/Collabs/*; do
    [ -f "$vproj/status/repos.txt" ] || continue
    if grep -qF "$repo" "$vproj/status/repos.txt" 2>/dev/null; then echo "$vproj"; return; fi
  done
  for vproj in "$vr"/10-Projects/* "$vr"/10-Projects/Collabs/*; do
    [ -d "$vproj" ] || continue
    if [ "$(basename "$vproj")" = "$(basename "$repo")" ]; then echo "$vproj"; return; fi
  done
  echo ""
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi
ROLE="${1:-}"; case "$ROLE" in -*) ROLE="";; esac
[ -n "$ROLE" ] && shift || true
REPO="" WT="" CLAIM=0 DRY=0 STRICT=0 VAULT="" TEST_CMD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:?}"; shift 2;;
    --wt)   WT="${2:?}"; shift 2;;
    --vault) VAULT="${2:?}"; shift 2;;
    --test-cmd) TEST_CMD="${2:?}"; shift 2;;
    --claim) CLAIM=1; shift;;
    --dry)  DRY=1; shift;;
    --strict) STRICT=1; shift;;
    --)     shift; break;;
    *)      die "unknown flag: $1 (see: pi-agents --help)";;
  esac
done
PI_ARGS=("$@")

[ -d "$AGENTS_DIR" ] || die "$AGENTS_DIR not found — run orchestration/deploy.sh"

# ---------------------------------------------------------------- role menu
roles=()
for f in "$AGENTS_DIR"/*.md; do [ -e "$f" ] || continue; roles+=("$(basename "$f" .md)"); done
[ ${#roles[@]} -gt 0 ] || die "no agent definitions in $AGENTS_DIR"

if [ -z "$ROLE" ]; then
  echo "roles in $AGENTS_DIR:"
  for r in "${roles[@]}"; do
    desc=$(awk -F': ' '/^description:/{print substr($0, index($0,$2)); exit}' "$AGENTS_DIR/$r.md")
    model=$(awk '/^model:/{print $2; exit}' "$AGENTS_DIR/$r.md")
    mark=""; case " $RETIRED " in *" $r "*) mark=" [retired shim]";; esac
    printf '  %-19s %-28s %s%s\n' "$r" "${model:-NO PIN}" "${desc:0:60}" "$mark"
  done
  PS3='role> '
  select pick in "${roles[@]}"; do
    [ -n "${pick:-}" ] && { ROLE="$pick"; break; }
    echo "pick a listed role"
  done
fi

FILE="$AGENTS_DIR/$ROLE.md"
[ -f "$FILE" ] || die "no such role: $ROLE (have: ${roles[*]})"
MODEL=$(awk '/^model:/{print $2; exit}' "$FILE")
# An unpinned role silently inherits the default model — the bug that made every subagent a premium
# session. Refuse rather than burn quota in silence (deploy.sh checks the same thing).
[ -n "$MODEL" ] || die "$ROLE.md has no 'model:' in frontmatter — pin it before launching"

# ---------------------------------------------------------------- where do we run?
CWD="$PWD"
if [ -n "$WT" ]; then
  case "$ROLE" in worker|calcs|scout) :;; *) die "--wt is for leaf roles (worker|calcs|scout), not $ROLE";; esac
  [ -n "$REPO" ] || die "--wt needs --repo"
  PART="${WT%%/*}"; SLICE="${WT#*/}"
  [ "$PART" != "$WT" ] && [ -n "$SLICE" ] || die "--wt wants part/agent, e.g. partB/desc"
  [ -x "$WT_SCRIPT" ] || [ -f "$WT_SCRIPT" ] || die "missing $WT_SCRIPT"
  REPO="$(cd "$REPO" && pwd)"
  # `add` refuses without .agent-paths (no integration_branch to branch the lock from), and telling a
  # human to run init first is a step that gets missed — so do the bootstrap here instead.
  if [ ! -f "$REPO/.agent-paths" ]; then
    echo "pi-agents: no .agent-paths in $REPO — running worktree.sh init" >&2
    [ -n "$VAULT" ] || VAULT="$(guess_vault "$REPO")"
    [ -n "$VAULT" ] || die "cannot find the vault project folder for $(basename "$REPO").
        Pass it explicitly:  --vault ~/path/to/vault/10-Projects/<X>
        or once, for every repo:  echo ~/path/to/vault > ~/.config/pi/vault-root"
    if [ -z "$TEST_CMD" ]; then
      echo "pi-agents: WARNING no --test-cmd — the integrator will have no command that means GREEN." >&2
      echo "           add one later with: worktree.sh init --repo $REPO --vault $VAULT --test-cmd '<cmd>'" >&2
    fi
    bash "$WT_SCRIPT" init --repo "$REPO" --vault "$VAULT" --part "$PART" ${TEST_CMD:+--test-cmd "$TEST_CMD"}
  fi
  bash "$WT_SCRIPT" add --repo "$REPO" --part "$PART" --agent "$SLICE" --role "$ROLE"
  CWD="$REPO/.worktrees/$PART-$SLICE"
fi

# ---------------------------------------------------------------- gate consistency
# The gate enforces whatever .pi-role says upward from cwd — if that disagrees with the prompt we just
# loaded, you get one tier's instructions under another tier's tool policy. Loud, never silent.
FOUND=""; D="$CWD"
while [ "$D" != "/" ]; do
  if [ -f "$D/.pi-role" ]; then FOUND="$(tr -d '[:space:]' < "$D/.pi-role")"; GATADIR="$D"; break; fi
  D="$(dirname "$D")"
done
if [ "$CLAIM" = 1 ]; then
  printf '%s\n' "$ROLE" > "$CWD/.pi-role"
  echo "pi-agents: wrote .pi-role=$ROLE in $CWD" >&2
  FOUND="$ROLE"; GATADIR="$CWD"
fi
if [ -z "$FOUND" ]; then
  echo "pi-agents: NOTE no .pi-role above $CWD — the tool gate is INACTIVE (prompt-only role)." >&2
  echo "           fix: cd to the right dir, or re-run with --claim, or use --wt for leaf roles." >&2
elif [ "$FOUND" != "$ROLE" ]; then
  die "gate says role=$FOUND ($GATADIR/.pi-role) but you asked for $ROLE — that is a mixed tier.
        Either launch $FOUND, or --claim to overwrite this directory's role, or --wt for a clean leaf."
fi

CMD=(pi --append-system-prompt "$FILE" --model "$MODEL")
# The agent file's `tools:` line is a hard whitelist for subagents but pi has no --agent flag, so a pane
# would otherwise get the full default toolset minus the gate's denies. --strict closes that last gap
# for tiers whose tools line is known to be complete (leaves); off by default because a role file that
# forgets a tool would silently cripple the pane.
if [ "$STRICT" = 1 ]; then
  TOOLS=$(awk -F': ' '/^tools:/{print $2; exit}' "$FILE")
  [ -n "$TOOLS" ] && CMD+=(--tools "${TOOLS// /}")  # frontmatter is already comma-separated: delete spaces, do not add commas || echo "pi-agents: --strict ignored ($ROLE.md declares no tools line)" >&2
fi
[ ${#PI_ARGS[@]} -gt 0 ] && CMD+=("${PI_ARGS[@]}")
echo "pi-agents: role=$ROLE model=$MODEL gate=${FOUND:-none} dir=$CWD" >&2
[ "$DRY" = 1 ] && { printf '  %q' "${CMD[@]}"; echo; exit 0; }
cd "$CWD"
exec "${CMD[@]}"
