#!/usr/bin/env python3
"""Split flows that have too many nodes into linked sub-flows.

Mermaid layouts degrade beyond ~40 nodes. This keeps the first nodes (breadth-first from the
entry) in the original flow and moves each remaining connected group into its own flow. The
original gets a stub node ("Continues: ...") with `link_to` pointing at the new flow, and the
new flow gets a stub that links back.

Usage:
    python split_flow.py flow.json -o flow.split.json [--limit 40]

Limitation: every connected group left over becomes its own flow, so a very wide fan-out (one node with
many independent branches) produces many small flows.

Only `flowchart` and `state` flows are split; `sequence` flows are left alone (a sequence
diagram cannot be cut along a graph boundary) and reported on stderr.
"""
import argparse
import copy
import json
import sys
from collections import deque
from pathlib import Path

from render_page import order_nodes

DEFAULT_LIMIT = 40
SPLITTABLE = {"flowchart", "state"}
MAX_LABEL = 40


def _components(ids: set, edges: list) -> list[set]:
    """Connected components of `ids`, treating edges as undirected, ordered by smallest BFS index."""
    adj = {i: set() for i in ids}
    for e in edges:
        if e["from"] in ids and e["to"] in ids:
            adj[e["from"]].add(e["to"])
            adj[e["to"]].add(e["from"])
    seen, out = set(), []
    for start in sorted(ids):
        if start in seen:
            continue
        comp, queue = set(), deque([start])
        while queue:
            n = queue.popleft()
            if n in comp:
                continue
            comp.add(n)
            queue.extend(adj[n] - comp)
        seen |= comp
        out.append(comp)
    return out


def _stub(stub_id: str, label: str, target_flow: str, anchor: dict, description: str) -> dict:
    """A navigation node. It borrows file/line from `anchor` so it still points at real code."""
    node = {
        "id": stub_id, "label": label[:MAX_LABEL], "type": "logic", "link_to": target_flow,
        "description": description,
    }
    if anchor.get("file"):
        node["file"], node["line"] = anchor["file"], anchor.get("line", 1)
        if anchor.get("repo"):
            node["repo"] = anchor["repo"]  # stays valid when a flow spans several repos
    return node


def _split_once(flow: dict, limit: int, part_no: int) -> tuple[dict, list[dict]]:
    """Return (head flow within the limit, child flows). Children may still exceed the limit."""
    nodes = {n["id"]: n for n in flow["nodes"]}
    order = order_nodes(flow)
    entry = flow["entry"]

    head_size = limit - 1
    while True:
        head = set(order[:head_size])
        rest = set(order[head_size:])
        comps = _components(rest, flow["edges"])
        # one stub per component that the head actually reaches
        linked = [c for c in comps if any(e["from"] in head and e["to"] in c for e in flow["edges"])]
        if head_size + len(linked) <= limit or head_size <= 1:
            break
        head_size -= 1
    if entry not in head:
        head.add(entry)

    children = []
    head_nodes = [copy.deepcopy(nodes[i]) for i in order if i in head]
    head_edges = []
    stubs = {}  # component index -> stub id
    comp_of = {n: idx for idx, c in enumerate(comps) for n in c}

    for idx, comp in enumerate(comps):
        part_no += 1
        child_id = f"{flow['id']}_part{part_no}"
        into = [e for e in flow["edges"] if e["from"] in head and e["to"] in comp]
        child_entry = into[0]["to"] if into else next(i for i in order if i in comp)
        title = f"{flow['title']} (part {part_no + 1})"
        back_stub = f"back_to_{flow['id']}"
        child_nodes = [copy.deepcopy(nodes[i]) for i in order if i in comp]
        child_edges = [copy.deepcopy(e) for e in flow["edges"] if e["from"] in comp and e["to"] in comp]
        back_edges = [e for e in flow["edges"] if e["from"] in comp and e["to"] in head]
        if back_edges:
            anchor = nodes[back_edges[0]["to"]]
            child_nodes.append(_stub(back_stub, f"Back: {flow['title']}", flow["id"], anchor,
                                     f"Returns to the main flow at '{anchor['label']}'."))
            for e in back_edges:
                moved = copy.deepcopy(e)
                moved["to"] = back_stub
                child_edges.append(moved)
        child = {k: v for k, v in flow.items() if k not in ("nodes", "edges", "notes", "entry", "id", "title")}
        child.update(id=child_id, title=title, entry=child_entry, nodes=child_nodes, edges=child_edges,
                     summary=f"Continuation of '{flow['title']}'. {flow.get('summary', '')}".strip())
        children.append(child)
        if into:
            anchor = nodes[into[0]["to"]]
            stub_id = f"continues_{child_id}"
            head_nodes.append(_stub(stub_id, f"Continues: {anchor['label']}", child_id, anchor,
                                    f"The flow continues in '{title}'."))
            stubs[idx] = stub_id

    for e in flow["edges"]:
        if e["from"] in head and e["to"] in head:
            head_edges.append(copy.deepcopy(e))
        elif e["from"] in head and e["to"] in comp_of and comp_of[e["to"]] in stubs:
            redirected = copy.deepcopy(e)
            redirected["to"] = stubs[comp_of[e["to"]]]
            if not any(x["from"] == redirected["from"] and x["to"] == redirected["to"] for x in head_edges):
                head_edges.append(redirected)

    new_head = {**{k: v for k, v in flow.items() if k not in ("nodes", "edges")},
                "nodes": head_nodes, "edges": head_edges}
    return new_head, children


def split_flow(flow: dict, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Split one flow into flows of at most `limit` nodes (plus nothing else to configure)."""
    if len(flow["nodes"]) <= limit or flow.get("diagram", "flowchart") not in SPLITTABLE:
        return [flow]
    result, queue, part_no = [], deque([flow]), 0
    while queue:
        current = queue.popleft()
        if len(current["nodes"]) <= limit:
            result.append(current)
            continue
        head, children = _split_once(current, limit, part_no)
        part_no += len(children)
        if len(head["nodes"]) >= len(current["nodes"]):  # cannot make progress; keep as is
            result.append(current)
            continue
        result.append(head)
        queue.extend(children)
    return result


def split_data(data: dict, limit: int = DEFAULT_LIMIT) -> dict:
    out = copy.deepcopy(data)
    flows = []
    for f in data["flows"]:
        pieces = split_flow(f, limit)
        if len(pieces) == 1 and len(f["nodes"]) > limit:
            print(f"warning: flow '{f['id']}' has {len(f['nodes'])} nodes but was not split "
                  f"({f.get('diagram', 'flowchart')} diagrams cannot be split)", file=sys.stderr)
        flows.extend(pieces)
    out["flows"] = flows
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow_json")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args(argv)
    data = json.loads(Path(args.flow_json).read_text(encoding="utf-8"))
    out = split_data(data, args.limit)
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {len(data['flows'])} flow(s) -> {len(out['flows'])} flow(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
