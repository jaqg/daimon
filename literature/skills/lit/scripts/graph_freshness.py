#!/usr/bin/env python3
"""
Check if graphify-out/graph.json is stale relative to vault notes.
Output: JSON {"fresh": bool, "stale_notes": int, "graph_json": str|null, "vault": str}
"""
import json, os, sys, subprocess
from pathlib import Path

config_paths = subprocess.run(
    ["find", "-L", os.path.expanduser("~/.claude"), "-name", "config.local",
     "-path", "*/daimon/config/*"],
    capture_output=True, text=True
).stdout.strip().split("\n")

vault = None
for cp in config_paths:
    if cp and Path(cp).exists():
        for line in Path(cp).read_text().splitlines():
            if line.startswith("VAULT_DIR="):
                vault = os.path.expanduser(line.split("=", 1)[1].strip())
                break

if not vault:
    vault = os.environ.get("VAULT_DIR") or os.path.expanduser("~/vault")
vault = os.path.expanduser(vault)

graph_json = Path(vault) / "graphify-out" / "graph.json"

if not graph_json.exists():
    print(json.dumps({"fresh": False, "stale_notes": -1,
                      "graph_json": None, "vault": vault,
                      "error": "graph.json not found"}))
    sys.exit(0)

graph_mtime = graph_json.stat().st_mtime
stale = []
for folder in ["20-Sources", "30-Galaxy"]:
    p = Path(vault) / folder
    if p.exists():
        for f in p.rglob("*.md"):
            if f.stat().st_mtime > graph_mtime:
                stale.append(str(f.relative_to(vault)))

print(json.dumps({
    "fresh": len(stale) == 0,
    "stale_notes": len(stale),
    "graph_json": str(graph_json),
    "vault": vault,
}))
