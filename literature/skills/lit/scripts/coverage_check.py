#!/usr/bin/env python3
"""
Query graphify for existing vault coverage of a topic.
Usage: coverage_check.py "QUERY" [BUDGET]
Output: JSON {"query", "node_count", "papers": [...], "galaxy_concepts": [...]}
"""
import json, os, re, subprocess, sys
from pathlib import Path

query = sys.argv[1] if len(sys.argv) > 1 else ""
budget = int(sys.argv[2]) if len(sys.argv) > 2 else 600

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
    print(json.dumps({"error": "graph.json not found", "node_count": 0,
                      "papers": [], "galaxy_concepts": []}))
    sys.exit(0)

result = subprocess.run(
    ["graphify", "query", query, "--budget", str(budget)],
    capture_output=True, text=True, cwd=vault
)
raw = result.stdout

papers, concepts = [], []
node_count = 0
node_re = re.compile(r"NODE (.+?) \[src=(.+?) loc=.*?community=(\d+)\]")

for line in raw.splitlines():
    m = node_re.match(line)
    if not m:
        continue
    node_count += 1
    label, src, community = m.group(1), m.group(2), int(m.group(3))
    entry = {"label": label, "source_file": src, "community": community}
    if src.startswith("20-Sources/papers/"):
        papers.append(entry)
    elif src.startswith("30-Galaxy/"):
        concepts.append(entry)

print(json.dumps({
    "query": query,
    "node_count": node_count,
    "papers": papers,
    "galaxy_concepts": concepts,
}, indent=2))
