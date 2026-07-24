"""
Patch graph.json nodes with full_text_available from paper note frontmatter.
Then regenerate graph.html.

Usage:
    python patch_full_text.py [vault_root] [graphify_out_dir]

Defaults: vault_root = cwd, graphify_out_dir = vault_root/graphify-out
"""
import json
import re
import sys
from pathlib import Path

VAULT_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
GRAPH_OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else VAULT_ROOT / "graphify-out"
GRAPH_JSON = GRAPH_OUT / "graph.json"


def parse_frontmatter(md_path: Path) -> dict:
    try:
        text = md_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    result = {}
    for line in block.splitlines():
        m = re.match(r"^(\w[\w_]*):\s*(.+)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.lower() == "true":
                result[key] = True
            elif val.lower() == "false":
                result[key] = False
            else:
                result[key] = val
    return result


def main():
    data = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))

    patched = 0
    missing_file = 0
    no_field = 0

    for node in data["nodes"]:
        src = node.get("source_file")
        if not src:
            continue
        md_path = VAULT_ROOT / src
        fm = parse_frontmatter(md_path)
        if not md_path.exists():
            missing_file += 1
            node["full_text_available"] = None
            continue
        if "full_text_available" in fm:
            node["full_text_available"] = fm["full_text_available"]
            patched += 1
        else:
            node["full_text_available"] = None
            no_field += 1

    GRAPH_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Patched {patched} nodes | no field: {no_field} | missing file: {missing_file}")

    # Regenerate HTML
    from graphify.build import build_from_json
    from graphify.export import to_html

    G = build_from_json(data)

    communities: dict[int, list[str]] = {}
    for node in data["nodes"]:
        c = node.get("community")
        if c is not None:
            communities.setdefault(c, []).append(node["id"])

    labels_path = GRAPH_OUT / ".graphify_labels.json"
    community_labels = json.loads(labels_path.read_text()) if labels_path.exists() else None

    member_counts = {c: len(ids) for c, ids in communities.items()}

    html_path = str(GRAPH_OUT / "graph.html")
    to_html(G, communities, html_path, community_labels=community_labels, member_counts=member_counts)
    print(f"HTML regenerated -> {html_path}")


if __name__ == "__main__":
    main()
