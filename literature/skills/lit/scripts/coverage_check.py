#!/usr/bin/env python3
"""
Query graphify for existing vault coverage of a topic.
Usage: coverage_check.py "QUERY" [BUDGET]
Output: JSON {"query", "node_count", "papers": [...], "galaxy_concepts": [...]}
"""
import json, os, re, subprocess, sys
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


query = sys.argv[1] if len(sys.argv) > 1 else ""
budget = int(sys.argv[2]) if len(sys.argv) > 2 else 600

vault = _resolve_vault()

graph_json = vault / "graphify-out" / "graph.json"
if not graph_json.exists():
    print(json.dumps({"error": "graph.json not found", "node_count": 0,
                      "papers": [], "galaxy_concepts": []}))
    sys.exit(0)

result = subprocess.run(
    ["graphify", "query", query, "--budget", str(budget)],
    capture_output=True, text=True, cwd=str(vault)
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
