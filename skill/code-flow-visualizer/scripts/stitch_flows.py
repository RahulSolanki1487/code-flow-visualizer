#!/usr/bin/env python3
"""Link frontend flows to backend flows automatically, using the frontend-call / backend-route match.

Usage:
    python stitch_flows.py flow.json --frontend web=../web-app --backend api=../api -o stitched.json

For every node that sits on a frontend HTTP call (same repo, same file, within a few lines of the call)
the stitcher looks up the backend route that call reaches (match_api.py) and then the flow whose entry
node is that route's handler. When it finds one it
  * sets `link_to` on the frontend node (the page shows "Open sub-flow"), and
  * adds a `callers` entry on the backend flow's entry node (the page shows "Called from ...").
A `likely` match also marks the frontend node `inferred` with a note. Nothing is invented: calls whose
route has no flow yet, calls with no route at all, and backend flows nobody calls are only reported.

Node and flow fields written: `link_to`, `callers: [{"flow": id, "node": id, "label": text}]`, and a
top-level `links` list (the evidence: call site, route, confidence).
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import match_api

TOLERANCE = 3  # lines between a node's cited line and the call / route line


def _repo_of(node: dict, default: str | None) -> str | None:
    return node.get("repo") or default


def _closest(items, line: int, tolerance: int, key=lambda x: x["line"]):
    near = [i for i in items if abs(key(i) - line) <= tolerance]
    return min(near, key=lambda i: abs(key(i) - line)) if near else None


def _closest_all(items, line: int, tolerance: int) -> list:
    """Every item at the smallest distance from `line` (within tolerance); several means a tie."""
    near = [(abs(i["line"] - line), i) for i in items if abs(i["line"] - line) <= tolerance]
    if not near:
        return []
    best = min(d for d, _ in near)
    return [i for d, i in near if d == best]


def _call_index(match_result: dict) -> dict:
    """(repo, file) -> list of {"line", "call", "matches": [...]} for calls that reach a route."""
    index: dict[tuple, dict] = {}
    for m in match_result["matches"]:
        c = m["call"]
        entry = index.setdefault((c["repo"], c["file"], c["line"]), {"line": c["line"], "call": c, "matches": []})
        entry["matches"].append(m)
    by_file: dict[tuple, list] = {}
    for (repo, file, _line), entry in index.items():
        by_file.setdefault((repo, file), []).append(entry)
    return by_file


def _unmatched_index(match_result: dict) -> dict:
    out: dict[tuple, list] = {}
    for c in match_result["unmatched_calls"]:
        out.setdefault((c["repo"], c["file"]), []).append(c)
    return out


def _entry_index(data: dict, backend_names: list, default_backend: str | None) -> dict:
    """(repo, file) -> list of {"line", "flow", "node"} for each flow's entry node."""
    out: dict[tuple, list] = {}
    for f in data["flows"]:
        nodes = {n["id"]: n for n in f["nodes"]}
        entry = nodes.get(f.get("entry"))
        if not entry or not entry.get("file") or entry.get("line") is None:
            continue
        repo = _repo_of(entry, default_backend)
        out.setdefault((repo, entry["file"]), []).append({"line": entry["line"], "flow": f["id"], "node": entry["id"], "title": f["title"]})
    return out


def _closest_nodes_per_call(data, frontend_names, default_front, calls_by_file, unmatched_by_file, tolerance) -> set:
    """(flow id, node id) of the node that owns each call: the nearest node to the call line, per call.

    Without this, the neighbouring nodes of one call (its success step, its error handler a few lines
    below) would all be linked to the same backend flow.
    """
    best: dict[tuple, list] = {}  # call key -> [distance, [(flow, node), ...]]
    for f in data["flows"]:
        for n in f["nodes"]:
            if not n.get("file") or n.get("line") is None or n.get("link_to"):
                continue
            repo = _repo_of(n, default_front)
            if repo not in frontend_names:
                continue
            for pool in (calls_by_file.get((repo, n["file"]), []), unmatched_by_file.get((repo, n["file"]), [])):
                for call in pool:
                    dist = abs(call["line"] - n["line"])
                    if dist > tolerance:
                        continue
                    key = (repo, n["file"], call["line"])
                    if key not in best or dist < best[key][0]:
                        best[key] = [dist, [(f["id"], n["id"])]]
                    elif dist == best[key][0]:
                        best[key][1].append((f["id"], n["id"]))
    return {owner for _dist, owners in best.values() for owner in owners}


def stitch(data: dict, match_result: dict, frontend_names: list, backend_names: list, tolerance: int = TOLERANCE):
    """Return (new_data, report). Pure: no file access."""
    out = copy.deepcopy(data)
    default_front = frontend_names[0] if len(frontend_names) == 1 else None
    default_back = backend_names[0] if len(backend_names) == 1 else None
    calls_by_file = _call_index(match_result)
    unmatched_by_file = _unmatched_index(match_result)
    entries = _entry_index(out, backend_names, default_back)
    flows = {f["id"]: f for f in out["flows"]}

    owners = _closest_nodes_per_call(out, frontend_names, default_front, calls_by_file, unmatched_by_file, tolerance)
    links, no_flow, no_route, ambiguous = [], [], [], []
    called_flows = set()
    for f in out["flows"]:
        for n in f["nodes"]:
            if (f["id"], n["id"]) not in owners:
                continue  # not the node that sits on a call (or another node is closer to that call)
            repo = _repo_of(n, default_front)
            hit = _closest(calls_by_file.get((repo, n["file"]), []), n["line"], tolerance)
            if not hit:
                miss = _closest(unmatched_by_file.get((repo, n["file"]), []), n["line"], tolerance)
                if miss:
                    no_route.append({"flow": f["id"], "node": n["id"], "call": f"{'/'.join(miss['methods'])} {miss['url'] or '(variable)'}"})
                continue
            candidates = []  # (confidence_rank, route_match, entry)
            for m in hit["matches"]:
                r = m["route"]
                pool = entries.get((r.get("repo") or default_back, r["file"]), [])
                for target in _closest_all(pool, r["line"], tolerance):  # equally close flows are all candidates
                    if target["flow"] != f["id"]:
                        candidates.append((0 if m["confidence"] == "exact" else 1, m, target))
            call = hit["call"]
            label = f"{'/'.join(call['methods'])} {call['url']}"
            if not candidates:
                no_flow.append({"flow": f["id"], "node": n["id"], "call": label,
                                "routes": [f"{m['route']['method'] or 'ANY'} {m['route']['path']} ({m['route']['file']}:{m['route']['line']})" for m in hit["matches"]]})
                continue
            best_rank = min(c[0] for c in candidates)
            best = [c for c in candidates if c[0] == best_rank]
            if len({c[2]["flow"] for c in best}) > 1:
                ambiguous.append({"flow": f["id"], "node": n["id"], "call": label, "flows": sorted({c[2]["flow"] for c in best})})
                continue
            rank, m, target = best[0]
            n["link_to"] = target["flow"]
            if rank == 1:  # a guess is shown as one
                n["inferred"] = True
                n["note"] = (n.get("note", "") + " " if n.get("note") else "") + \
                    f"Backend link is a likely match (heuristic: {label} -> {m['route']['method'] or 'ANY'} {m['route']['path']})."
            entry_node = next(x for x in flows[target["flow"]]["nodes"] if x["id"] == target["node"])
            caller = {"flow": f["id"], "node": n["id"], "label": f"{f['title']}: {n['label']}"}
            if caller not in entry_node.setdefault("callers", []):
                entry_node["callers"].append(caller)
            called_flows.add(target["flow"])
            links.append({"from_flow": f["id"], "from_node": n["id"], "to_flow": target["flow"], "to_node": target["node"],
                          "confidence": "exact" if rank == 0 else "likely", "call": label,
                          "route": f"{m['route']['method'] or 'ANY'} {m['route']['path']}"})

    backend_entries = {e["flow"] for lst in entries.values() for e in lst}
    uncalled = sorted(fid for fid in backend_entries if fid not in called_flows and _is_route_flow(flows[fid], match_result))
    if links:
        out["links"] = (out.get("links") or []) + links
    return out, {"linked": links, "no_backend_flow": no_flow, "no_route": no_route, "ambiguous": ambiguous, "backend_flows_without_caller": uncalled}


def _is_route_flow(flow: dict, match_result: dict) -> bool:
    """True when the flow's entry is a known backend route (so 'nobody calls it' is meaningful)."""
    entry = next((n for n in flow["nodes"] if n["id"] == flow.get("entry")), None)
    if not entry or not entry.get("file"):
        return False
    routes = [m["route"] for m in match_result["matches"]] + match_result["uncalled_routes"]
    return any(r["file"] == entry["file"] and abs(r["line"] - entry.get("line", -99)) <= TOLERANCE for r in routes)


def format_report(report: dict) -> str:
    lines = [f"LINKED ({len(report['linked'])})"]
    for l in report["linked"]:
        lines.append(f"  [{l['confidence']}] {l['from_flow']}/{l['from_node']}  --{l['call']}-->  {l['to_flow']}   ({l['route']})")
    lines.append(f"\nCALL FOUND, BUT NO BACKEND FLOW FOR ITS ROUTE ({len(report['no_backend_flow'])}): trace these routes next")
    for x in report["no_backend_flow"]:
        lines.append(f"  {x['flow']}/{x['node']}  {x['call']}  ->  {'; '.join(x['routes'])}")
    lines.append(f"\nCALL FOUND, BUT NO BACKEND ROUTE ({len(report['no_route'])}): third-party, static or built at runtime")
    for x in report["no_route"]:
        lines.append(f"  {x['flow']}/{x['node']}  {x['call']}")
    if report["ambiguous"]:
        lines.append(f"\nAMBIGUOUS ({len(report['ambiguous'])}): several backend flows fit; nothing linked")
        for x in report["ambiguous"]:
            lines.append(f"  {x['flow']}/{x['node']}  {x['call']}  ->  {', '.join(x['flows'])}")
    lines.append(f"\nBACKEND FLOWS NO FRONTEND FLOW CALLS ({len(report['backend_flows_without_caller'])})")
    for fid in report["backend_flows_without_caller"]:
        lines.append(f"  {fid}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow_json")
    ap.add_argument("--frontend", action="append", required=True, help="[NAME=]PATH, repeatable")
    ap.add_argument("--backend", action="append", required=True, help="[NAME=]PATH, repeatable")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--tolerance", type=int, default=TOLERANCE)
    match_api.add_matching_arguments(ap)
    args = ap.parse_args(argv)
    frontends, backends = match_api.parse_repo_args(args.frontend), match_api.parse_repo_args(args.backend)
    data = json.loads(Path(args.flow_json).read_text(encoding="utf-8"))
    result = match_api.run(frontends, backends, match_api.build_rules(args, backends), match_api.build_bases(args),
                           match_api.build_wrappers(args))
    stitched, report = stitch(data, result, [n for n, _ in frontends], [n for n, _ in backends], args.tolerance)
    Path(args.output).write_text(json.dumps(stitched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(format_report(report))
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
