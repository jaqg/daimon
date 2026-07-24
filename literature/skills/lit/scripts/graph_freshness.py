#!/usr/bin/env python3
"""
Check if graphify-out/graph.json is stale relative to vault notes.
Output: JSON {"fresh": bool, "stale_notes": int, "graph_json": str|null, "vault": str}
"""
import json, os, sys
from pathlib import Path


def _resolve_vault() -> Path:
    # 1. Walk up from this script to find daimon root (has config/config.local)
    for parent in Path(__file__).resolve().parents:
        cfg = parent / "config" / "config.local"
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                if line.startswith("VAULT_DIR="):
                    return Path(os.path.expanduser(line.split("=", 1)[1].strip()))
            break
    # 2. Env var (set in settings.json or shell)
    if os.environ.get("VAULT_DIR"):
        return Path(os.path.expanduser(os.environ["VAULT_DIR"]))
    # 3. CWD detection (vault has 20-Sources + 30-Galaxy)
    for candidate in [Path.cwd(), Path.cwd().parent]:
        if (candidate / "20-Sources").exists() and (candidate / "30-Galaxy").exists():
            return candidate
    return Path(os.path.expanduser("~/vault"))


vault = _resolve_vault()
graph_json = vault / "graphify-out" / "graph.json"

if not graph_json.exists():
    print(json.dumps({"fresh": False, "stale_notes": -1,
                      "graph_json": None, "vault": str(vault),
                      "error": "graph.json not found"}))
    sys.exit(0)

graph_mtime = graph_json.stat().st_mtime
stale = []
for folder in ["20-Sources", "30-Galaxy"]:
    p = vault / folder
    if p.exists():
        for f in p.rglob("*.md"):
            if f.stat().st_mtime > graph_mtime:
                stale.append(str(f.relative_to(vault)))

print(json.dumps({
    "fresh": len(stale) == 0,
    "stale_notes": len(stale),
    "graph_json": str(graph_json),
    "vault": str(vault),
}))
