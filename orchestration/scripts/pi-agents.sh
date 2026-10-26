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
elif [ -n "$REPO" ]; then
  # `--repo` without `--wt` means "run in that project directory". It used to be ignored for leafless
  # roles, so `pi-agents integrator --repo <worktree>` launched in the caller's cwd while claiming the
  # worktree — and then refused for the *parent* checkout's role. A path argument that does not position
  # you is worse than no path argument, because the printed command looked correct.
  CWD="$REPO"
fi

# ---------------------------------------------------------------- gate consistency
# The gate enforces whatever .pi-role says upward from cwd — if that disagrees with the prompt we just
# loaded, you get one tier's instructions under another tier's tool policy. Loud, never silent.
# A directory that does not exist must not be resolved by walking upward: `--repo
# .../.worktrees/integrate-structure` before `worktree.sh integrate` has run used to land on the MAIN
# checkout's `.pi-role=brain` and refuse with a mixed-tier error, which reads like a config problem and
# is really "the workspace has not been created yet".
if [ ! -d "$CWD" ]; then
  die "no such directory: $CWD
        for an integrator pane the integration worktree has to exist first — from the PROJECT ROOT run:
          bash $WT_SCRIPT integrate --repo <project-root> --part <part>
        /merge-status prints that line with the real paths; the brain owns the command."
fi
FOUND=""; D="$CWD"
while [ "$D" != "/" ]; do
  if [ -f "$D/.pi-role" ]; then FOUND="$(tr -d '[:space:]' < "$D/.pi-role")"; GATADIR="$D"; break; fi
  D="$(dirname "$D")"
done
# `operator` is the tier defined by the ABSENCE of a role tag: no .pi-role => role-gate fails open => full
# tools. Claiming it would write a name the gate does not know, which keeps the gate off (correct) yet
# blocks every later leaf launch in that directory with a mixed-tier refusal (a nuisance that reads like a
# config bug). So there is nothing to claim here.
if [ "$ROLE" = "operator" ] && [ "$CLAIM" = 1 ]; then
  die "operator needs no --claim — it IS the ungated pane. Running 'pi-agents operator' here is enough.
        (--claim writes .pi-role=operator, which no profile knows, and would then refuse a later
         'pi-agents worker' in the same directory as a mixed tier.)"
fi
if [ "$CLAIM" = 1 ]; then
  printf '%s\n' "$ROLE" > "$CWD/.pi-role"
  echo "pi-agents: wrote .pi-role=$ROLE in $CWD" >&2
  FOUND="$ROLE"; GATADIR="$CWD"
fi
if [ -z "$FOUND" ]; then
  if [ "$ROLE" = "operator" ]; then
    echo "pi-agents: role=operator — no .pi-role anywhere, which is the POINT: the gate is off by design." >&2
  else
    echo "pi-agents: NOTE no .pi-role above $CWD — the tool gate is INACTIVE (prompt-only role)." >&2
    echo "           fix: cd to the right dir, or re-run with --claim, or use --wt for leaf roles." >&2
  fi
elif [ "$FOUND" != "$ROLE" ]; then
  # Nearest directory ABOVE the tagged one that carries no tag — the only place `operator` can sit.
  U="$(dirname "$GATADIR")"
  while [ "$U" != "/" ] && [ -f "$U/.pi-role" ]; do U="$(dirname "$U")"; done
  if [ "$ROLE" = "operator" ]; then
    # The generic hint below is WRONG for this case: it offers --claim, which we refuse, and offers to
    # launch $FOUND, which is not what "open the daily-driver pane" means. operator has no tag by
    # definition, so the only honest answer is the path that has none.
    die "gate says role=$FOUND ($GATADIR/.pi-role) but you asked for operator — and operator has no tag.
        It is the tier defined by the ABSENCE of one, so there is nothing to claim here (--claim would
        also make a later 'pi-agents worker' in $GATADIR a mixed tier).
        Launch it from the nearest unclaimed directory instead:
          cd $U && pi-agents operator
        From there it still reads and writes $GATADIR: role-gate resolves the gate from the SESSION's
        cwd, not the target's — which is why state reconciliation lives in this tier.
        Do NOT delete $GATADIR/.pi-role to force this seat. The gate is re-read on every tool call, so a
        live $FOUND pane in that directory loses its denials mid-session and starts doing leaf work with
        full tools."
  fi
  die "gate says role=$FOUND ($GATADIR/.pi-role) but you asked for $ROLE — that is a mixed tier.
        Either launch $FOUND, or --claim to overwrite this directory's role, or --wt for a clean leaf.
        Caveat on --claim: it changes the gate for a LIVE $FOUND pane too (role-gate re-reads .pi-role on
        every tool call), so overwrite only when no pane is running in $GATADIR."
fi

CMD=(pi --append-system-prompt "$FILE" --model "$MODEL")
# The agent file's `tools:` line is a hard whitelist for subagents but pi has no --agent flag, so a pane
# would otherwise get the full default toolset minus the gate's denies. --strict closes that last gap
# for tiers whose tools line is known to be complete (leaves); off by default because a role file that
# forgets a tool would silently cripple the pane.
if [ "$STRICT" = 1 ]; then
  TOOLS=$(awk -F': ' '/^tools:/{print $2; exit}' "$FILE")
  # An inline `#` comment used to swallow the `||` fallback on the previous line, so a role with no tools
  # line silently produced `--tools` with an empty value instead of a warning.
  if [ -n "$TOOLS" ]; then CMD+=(--tools "${TOOLS// /}"); else echo "pi-agents: --strict ignored ($ROLE.md declares no tools line)" >&2; fi
fi
[ ${#PI_ARGS[@]} -gt 0 ] && CMD+=("${PI_ARGS[@]}")
echo "pi-agents: role=$ROLE model=$MODEL gate=${FOUND:-none} dir=$CWD" >&2
[ "$DRY" = 1 ] && { printf '  %q' "${CMD[@]}"; echo; exit 0; }
cd "$CWD"
exec "${CMD[@]}"
