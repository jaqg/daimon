#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_LOCAL="$REPO_DIR/config/config.local"

# Check config.local exists
if [[ ! -f "$CONFIG_LOCAL" ]]; then
    echo "config/config.local not found. Copy config/config.example and fill in values."
    exit 1
fi
source "$CONFIG_LOCAL"

# Detect agent skill directories (override in config.local if needed)
if [[ -z "${SKILL_DIRS:-}" ]]; then
    SKILL_DIRS=()
    [[ -d "$HOME/.claude/skills" ]] && SKILL_DIRS+=("$HOME/.claude/skills")
    [[ -d "$HOME/.pi/agent/skills" ]] && SKILL_DIRS+=("$HOME/.pi/agent/skills")
    [[ -d "$HOME/.agents/skills" ]] && SKILL_DIRS+=("$HOME/.agents/skills")
fi
if [[ ${#SKILL_DIRS[@]} -eq 0 ]]; then
    echo "No agent skill directories found. Is Claude Code or Pi installed?"
    exit 1
fi

# Symlink all skill directories into detected agent skill dirs
echo "Detected agent skill dirs: ${SKILL_DIRS[*]}"
skill_count=0
for skill_dir in "$REPO_DIR"/*/skills/*/; do
    [[ -d "$skill_dir" ]] || continue
    skill_name="$(basename "$skill_dir")"

    for target_dir in "${SKILL_DIRS[@]}"; do
        target="$target_dir/$skill_name"
        if [[ -L "$target" ]]; then
            echo "  skip (already linked): $skill_name → $target_dir"
        elif [[ -e "$target" ]]; then
            echo "  WARNING: $target exists and is not a symlink — skipping"
        else
            ln -s "$skill_dir" "$target"
            echo "  linked: $skill_name → $target_dir"
            ((++skill_count))
        fi
    done
done

echo "Done. $skill_count skill link(s) created across ${#SKILL_DIRS[@]} agent(s)"

# Symlink agent definitions into Pi's agent dir (Pi subagent tool)
PI_AGENTS="$HOME/.pi/agent/agents"
agent_count=0
for agent_file in "$REPO_DIR"/*/agents/*.md; do
    [[ -f "$agent_file" ]] || continue
    agent_name="$(basename "$agent_file")"
    if [[ -L "$PI_AGENTS/$agent_name" ]]; then
        echo "  skip (already linked): $agent_name"
    elif [[ -e "$PI_AGENTS/$agent_name" ]]; then
        echo "  WARNING: $PI_AGENTS/$agent_name exists and is not a symlink — skipping"
    else
        mkdir -p "$PI_AGENTS"
        ln -s "$agent_file" "$PI_AGENTS/$agent_name"
        echo "  linked agent: $agent_name → $PI_AGENTS"
        ((++agent_count))
    fi
done
[[ $agent_count -gt 0 ]] && echo "Done. $agent_count agent link(s) created for Pi" || true

# Symlink prompt templates into Pi's prompts dir (slash commands: /report-writer, ...)
PI_PROMPTS="$HOME/.pi/agent/prompts"
prompt_count=0
for prompt_file in "$REPO_DIR"/*/prompts/*.md; do
    [[ -f "$prompt_file" ]] || continue
    prompt_name="$(basename "$prompt_file")"
    if [[ -L "$PI_PROMPTS/$prompt_name" ]]; then
        echo "  skip (already linked): $prompt_name"
    elif [[ -e "$PI_PROMPTS/$prompt_name" ]]; then
        echo "  WARNING: $PI_PROMPTS/$prompt_name exists and is not a symlink — skipping"
    else
        mkdir -p "$PI_PROMPTS"
        ln -s "$prompt_file" "$PI_PROMPTS/$prompt_name"
        echo "  linked prompt: $prompt_name → $PI_PROMPTS"
        ((++prompt_count))
    fi
done
[[ $prompt_count -gt 0 ]] && echo "Done. $prompt_count prompt link(s) created for Pi" || true

# Check vault-specific setup
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
