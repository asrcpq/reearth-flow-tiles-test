#!/usr/bin/env python3
"""Dump workflow topology: node names and edge pairs, per graph."""
import sys
import yaml

# Handle !include tags without following them
yaml.add_constructor("!include", lambda loader, node: None, Loader=yaml.SafeLoader)


def dump(path):
    with open(path) as f:
        wf = yaml.safe_load(f)

    graphs = wf.get("graphs") or ([wf] if "nodes" in wf else [])
    for g in graphs:
        if g is None:
            continue  # was an !include
        name = g.get("name", g.get("id", "?"))
        nodes = g.get("nodes") or []
        edges = g.get("edges") or []

        id_to_name = {n["id"]: n["name"] for n in nodes}

        print(f"=== {name} ===")
        for n in nodes:
            label = n.get("action") or f'subGraph:{n.get("subGraphId", "?")[-8:]}'
            print(f"  {n['name']} ({label})")
        for e in edges:
            src = id_to_name.get(e["from"], e["from"][-8:])
            dst = id_to_name.get(e["to"], e["to"][-8:])
            print(f"  {src}:{e['fromPort']} -> {dst}:{e['toPort']}")
        print()


for path in sys.argv[1:]:
    print(f"# {path}")
    dump(path)
