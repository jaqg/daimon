#!/usr/bin/env bash
# Run graphify --update on vault after new notes are imported.
# Usage: update_graph.sh

CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$CONFIG" ]] && source "$CONFIG"

VAULT="${VAULT_DIR:-$HOME/vault}"
VAULT="${VAULT/#\~/$HOME}"

if [[ ! -f "$VAULT/graphify-out/graph.json" ]]; then
  echo "No graph.json found at $VAULT/graphify-out/ — run /graphify $VAULT first."
  exit 1
fi

cd "$VAULT" && graphify . --update
