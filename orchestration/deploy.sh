#!/usr/bin/env bash
# Deploy daimon orchestration resources that setup.sh does not cover yet:
# Pi extensions and role state. Idempotent; safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_EXT="$HOME/.pi/agent/extensions"

mkdir -p "$PI_EXT"
for ext in "$REPO_DIR"/orchestration/extensions/*.ts; do
    [[ -f "$ext" ]] || continue
    name="$(basename "$ext")"
    target="$PI_EXT/$name"
    if [[ -L "$target" ]]; then
        echo "  relink: $name"
        ln -sfn "$ext" "$target"
    elif [[ -e "$target" ]]; then
        echo "  WARNING: $target is a real file, not a symlink — leaving it alone."
        echo "           Diff it against $ext manually, then replace with a symlink."
    else
        ln -s "$ext" "$target"
        echo "  linked extension: $name -> $target"
    fi
done

# Agent definitions (brain, worker, calcs, scout, verifier, integrator, reviewers). Same rule as extensions:
# the repo is the source of truth, ~/.pi/agent/agents/ holds symlinks. A real file in the way is
# reported, never overwritten — diff it against the repo copy first.
PI_AGENTS="$HOME/.pi/agent/agents"
mkdir -p "$PI_AGENTS"
for ag in "$REPO_DIR"/orchestration/agents/*.md; do
    [[ -f "$ag" ]] || continue
    name="$(basename "$ag")"
    target="$PI_AGENTS/$name"
    if [[ -L "$target" ]]; then
        echo "  relink: agents/$name"
        ln -sfn "$ag" "$target"
    elif [[ -e "$target" ]]; then
        echo "  WARNING: $target is a real file, not a symlink — leaving it alone."
        echo "           Diff it against $ag manually, then replace with a symlink."
    else
        ln -s "$ag" "$target"
        echo "  linked agent: agents/$name -> $target"
    fi
done

# Commands (prompts) and the deterministic scripts they call. Same symlink rule: the repo is the
# source of truth, ~/.pi/agent/{prompts,scripts} are link farms. A real file in the way is reported.
link_dir() {  # $1 = subdir of this repo, $2 = target dir under ~/.pi/agent
  local src glob target name
  src="$REPO_DIR/orchestration/$1"; target="$HOME/.pi/agent/$2"
  [[ -d "$src" ]] || return 0
  mkdir -p "$target"
  for f in "$src"/*; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f")"
    if [[ -L "$target/$name" ]]; then ln -sfn "$f" "$target/$name"; echo "  relink: $2/$name"
    elif [[ -e "$target/$name" ]]; then echo "  WARNING: $target/$name is a real file, not a symlink — leaving it alone."
    else ln -s "$f" "$target/$name"; chmod +x "$target/$name" 2>/dev/null || true; echo "  linked $2/$name"; fi
  done
}
link_dir prompts prompts
link_dir scripts scripts

# The role launcher must be on PATH, not inside ~/.pi/agent: you type it in a shell, not in a session.
link_bin() {  # $1 = repo-relative script, $2 = command name
    src="$REPO_DIR/orchestration/$1"
    dst_dir="${HOME}/.local/bin"
    [[ -f "$src" ]] || { echo "  WARN: missing $src — skipping $2"; return; }
    chmod +x "$src"
    mkdir -p "$dst_dir"
    ln -sfn "$src" "$dst_dir/$2"
    echo "  linked $dst_dir/$2 -> $src"
    case ":$PATH:" in *":$dst_dir:"*) :;; *)
        echo "  NOTE: $dst_dir is not on your PATH — add:  export PATH=\"$HOME/.local/bin:\$PATH\"";;
    esac
}
link_bin scripts/pi-agents.sh pi-agents

# Advisor lane (the escalation model behind `advisor()`), source of truth = this repo.
# Installed only when absent, so a model you picked by hand with /advisor on either machine
# is never clobbered.
ADVISOR_SRC="$REPO_DIR/orchestration/advisor.json"
ADVISOR_DST="${XDG_CONFIG_HOME:-$HOME/.config}/rpiv-advisor/advisor.json"
if [ -f "$ADVISOR_DST" ]; then
    echo "  advisor config already present, leaving it: $ADVISOR_DST"
elif [ -f "$HOME/.pi/agent/auth.json" ]; then
    mkdir -p "$(dirname "$ADVISOR_DST")"
    cp "$ADVISOR_SRC" "$ADVISOR_DST" && chmod 600 "$ADVISOR_DST"
    echo "  installed advisor config: $ADVISOR_DST (glm-5.3:high)"
else
    echo "  SKIP advisor config: no pi auth.json on this machine yet"
fi

cat <<'EOF'

Role gate notes (orchestration/extensions/role-gate.ts):
  - Active in EVERY session, but a no-op unless a `.pi-role` file is found
    walking upward from cwd. Existing repos are unaffected.
  - Launch a role correctly:      pi-agents                (interactive menu)
                                   pi-agents worker --repo ~/proj --wt partB/desc
                                   pi-agents brain --claim  (writes ./.pi-role here first)
    A hand-typed `pi` pane inherits settings.defaultModel and has NO gate. pi-agents pins the model
    from the agent file and refuses to start on a role/model mismatch.
  - Declare a role per workspace:  pi-agents <role> --claim   (or echo brain > .pi-role)
  - Inspect what is enforced:      /role
  - Disable instantly:             mv ~/.pi/agent/extensions/role-gate.ts{,.off}
EOF

# A model pin is load-bearing: `subagent` only passes --model when the agent file declares one, so an
# unpinned agent silently runs on settings.defaultModel (the brain's expensive model). Fail loudly.
unpinned=$(grep -L '^model:' "$REPO_DIR"/orchestration/agents/*.md 2>/dev/null || true)
if [[ -n "$unpinned" ]]; then
    echo "  ERROR: agent files without a model: pin (they would inherit the brain's model):"
    echo "$unpinned" | sed 's/.*\///;s/^/           /'
    exit 1
fi
