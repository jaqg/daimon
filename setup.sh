#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CLAUDE_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
CONFIG_LOCAL="$REPO_DIR/config/config.local"

REQUIRED_PLUGINS=(
    "scientific-skills@claude-scientific-skills"
    "claude-scientific-writer@claude-scientific-writer"
    "caveman@caveman"
    "skill-creator@claude-plugins-official"
    "voltagent-meta@voltagent-subagents"
)

# Check config.local exists
if [[ ! -f "$CONFIG_LOCAL" ]]; then
    echo "config/config.local not found. Copy config/config.example and fill in values."
    exit 1
fi

# Check required plugins
echo "Checking plugins..."
missing=0
for plugin in "${REQUIRED_PLUGINS[@]}"; do
    plugin_key="${plugin%%@*}@${plugin##*@}"
    if [[ -f "$CLAUDE_PLUGINS" ]] && grep -q "\"${plugin_key}\"" "$CLAUDE_PLUGINS"; then
        echo "  ok: $plugin"
    else
        echo "  MISSING: $plugin — run /install $plugin in Claude Code"
        ((++missing))
    fi
done
[[ $missing -gt 0 ]] && echo "Warning: $missing plugin(s) missing. See config/plugins.md." || echo "All plugins present."
echo

# Symlink all skill directories into ~/.claude/skills/
skill_count=0
for skill_dir in "$REPO_DIR"/*/skills/*/; do
    [[ -d "$skill_dir" ]] || continue
    skill_name="$(basename "$skill_dir")"
    target="$CLAUDE_SKILLS_DIR/$skill_name"

    if [[ -L "$target" ]]; then
        echo "  skip (already linked): $skill_name"
    elif [[ -e "$target" ]]; then
        echo "  WARNING: $target exists and is not a symlink — skipping"
    else
        ln -s "$skill_dir" "$target"
        echo "  linked: $skill_name"
        ((++skill_count))
    fi
done

echo "Done. $skill_count skill(s) linked to $CLAUDE_SKILLS_DIR"

# Check vault-specific setup
if [[ -f "$CONFIG_LOCAL" ]]; then
    source "$CONFIG_LOCAL"
    if [[ -n "${VAULT_DIR:-}" ]]; then
        VAULT_HASH=$(echo "$VAULT_DIR" | sed 's|/|-|g')
        MEMORY_DIR="$HOME/.claude/projects/$VAULT_HASH/memory"
        if [[ ! -f "$MEMORY_DIR/research_interests.md" ]]; then
            echo
            echo "WARNING: memory/research_interests.md not found."
            echo "  The process-inbox skill needs this for conference relevance scoring."
            echo "  Template: $REPO_DIR/vault/skills/process-inbox/research_interests.template.md"
            echo "  Copy it to: $MEMORY_DIR/research_interests.md and fill in your research areas."
        fi
    fi
fi
