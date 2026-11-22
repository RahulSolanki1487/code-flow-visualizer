#!/usr/bin/env python3
"""Render flow.json into a self-contained Bootstrap 5 + Mermaid HTML page.

Usage:
    python render_page.py flow.json -o flow.html [--offline] [--repo PATH]
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "flow-page.html"
VENDOR = SKILL_DIR / "assets" / "vendor"

CDN = {
    "bootstrap_css": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
    "bootstrap_js": "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
    "mermaid_js": "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js",
    "panzoom_js": "https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js",
}
VENDOR_FILES = {
    "bootstrap_css": "bootstrap.min.css",
    "bootstrap_js": "bootstrap.bundle.min.js",
    "mermaid_js": "mermaid.min.js",
    "panzoom_js": "svg-pan-zoom.min.js",
}

SHAPES = {
    "entry": ('(["', '"])'),
    "logic": ('["', '"]'),
    "data": ('[("', '")]'),
    "external": ('[["', '"]]'),
    "decision": ('{"', '"}'),
    "error": ('{{"', '"}}'),
    "ui": ('("', '")'),
    "event": ('>"', '"]'),
}
CLASS_STYLES = {
    "entry": "fill:#cfe2ff,stroke:#0d6efd,color:#052c65",
    "logic": "fill:#f8f9fa,stroke:#6c757d,color:#212529",
    "data": "fill:#d1e7dd,stroke:#198754,color:#0a3622",
    "external": "fill:#e2d9f3,stroke:#6f42c1,color:#2c1a4d",
    "decision": "fill:#ffe5d0,stroke:#fd7e14,color:#58300a",
    "error": "fill:#f8d7da,stroke:#dc3545,color:#58151c",
    "ui": "fill:#cff4fc,stroke:#0dcaf0,color:#055160",
    "event": "fill:#f7d6e6,stroke:#d63384,color:#561435",
}


def mlabel(text: str) -> str:
    """Escape a label for use inside Mermaid double quotes."""
    s = str(text or "").replace("\r", " ").replace("\n", " ")
    return s.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


def safe_id(node_id: str) -> str:
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in str(node_id))
    return ("n_" + out) if not out or out[0].isdigit() or out in {"end", "graph", "style", "class"} else out


def order_nodes(flow):
    """Breadth-first from the entry node; unreachable nodes appended in file order."""
    nodes = {n["id"]: n for n in flow["nodes"]}
    adj = {}
    for e in flow["edges"]:
        adj.setdefault(e["from"], []).append(e["to"])
    seen, out = set(), []
    q = deque([flow.get("entry") or flow["nodes"][0]["id"]])
    while q:
        nid = q.popleft()
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        out.append(nid)
        q.extend(adj.get(nid, []))
    out += [n["id"] for n in flow["nodes"] if n["id"] not in seen]
    return out


def flowchart(flow) -> str:
    lines = [f"flowchart {flow.get('direction', 'TD')}"]
    for n in flow["nodes"]:
        open_, close = SHAPES.get(n.get("type", "logic"), SHAPES["logic"])
        label = mlabel(n["label"]) + (" ⚠" if n.get("inferred") else "")
        lines.append(f"  {safe_id(n['id'])}{open_}{label}{close}")
    error_links = []
    for i, e in enumerate(flow["edges"]):
        a, b = safe_id(e["from"]), safe_id(e["to"])
        kind = e.get("kind", "normal")
        lab = mlabel(e.get("label", ""))
        if kind == "error":
            arrow = "==>"
            error_links.append(i)
        elif e.get("inferred") or kind == "async":
            arrow = "-.->"
        else:
            arrow = "-->"
        lines.append(f'  {a} {arrow}|"{lab}"| {b}' if lab else f"  {a} {arrow} {b}")
    for t, style in CLASS_STYLES.items():
        lines.append(f"  classDef {t} {style}")
    for n in flow["nodes"]:
        lines.append(f"  class {safe_id(n['id'])} {n.get('type', 'logic')}")
        lines.append(f'  click {safe_id(n["id"])} call cfvSelect("{n["id"]}")')
    if error_links:
        lines.append(f"  linkStyle {','.join(map(str, error_links))} stroke:#dc3545,stroke-width:2px")
    return "\n".join(lines)


def sequence(flow) -> str:
    nodes = {n["id"]: n for n in flow["nodes"]}
    parts = flow.get("participants") or [n["id"] for n in flow["nodes"]]
    lines = ["sequenceDiagram", "  autonumber"]
    for pid in parts:
        n = nodes.get(pid, {"label": pid, "type": "logic"})
        kw = "actor" if n.get("type") == "ui" else "participant"
        lines.append(f"  {kw} {safe_id(pid)} as {mlabel(n['label'])}")
    edges = sorted(enumerate(flow["edges"]), key=lambda p: (p[1].get("order", p[0]), p[0]))
    for _, e in edges:
        kind = e.get("kind", "normal")
        arrow = "-x" if kind == "error" else "-)" if kind == "async" else "-->>" if e.get("inferred") else "->>"
        lab = mlabel(e.get("label") or "calls").replace(":", " ")
        lines.append(f"  {safe_id(e['from'])}{arrow}{safe_id(e['to'])}: {lab}")
    return "\n".join(lines)


def state(flow) -> str:
    """stateDiagram-v2: nodes are states, edges are transitions. Sinks end in [*]."""
    lines = ["stateDiagram-v2", f"  direction {'LR' if flow.get('direction') == 'LR' else 'TB'}"]
    for n in flow["nodes"]:
        lines.append(f'  state "{mlabel(n["label"])}" as {safe_id(n["id"])}')
    entry = flow.get("entry") or flow["nodes"][0]["id"]
    lines.append(f"  [*] --> {safe_id(entry)}")
    sources = {e["from"] for e in flow["edges"]}
    for e in flow["edges"]:
        lab = mlabel(e.get("label", "")).replace(":", " ")
        lines.append(f"  {safe_id(e['from'])} --> {safe_id(e['to'])}" + (f" : {lab}" if lab else ""))
    for n in flow["nodes"]:
        if n["id"] not in sources and n["id"] != entry:
            lines.append(f"  {safe_id(n['id'])} --> [*]")
    errors = [safe_id(n["id"]) for n in flow["nodes"] if n.get("type") == "error"]
    if errors:
        lines.append("  classDef err fill:#f8d7da,stroke:#dc3545,color:#58151c")
        lines.append(f"  class {','.join(errors)} err")
    return "\n".join(lines)


DIAGRAMS = {"flowchart": flowchart, "sequence": sequence, "state": state}


def vscode_url(repo_root: Path | None, file_: str | None, line) -> str:
    """vscode://file link for a repo-relative path; empty when no repo root was given."""
    if not repo_root or not file_:
        return ""
    absolute = (repo_root / file_).resolve().as_posix()
    return f"vscode://file/{absolute}" + (f":{line}" if line else "")


def build_flow(flow, repo_root: Path | None = None):
    nodes = {n["id"]: n for n in flow["nodes"]}
    order = order_nodes(flow)
    outgoing = {}
    for e in flow["edges"]:
        if e["to"] in nodes:
            outgoing.setdefault(e["from"], []).append(
                {"to": e["to"], "label": e.get("label", ""), "label_to": nodes[e["to"]]["label"]}
            )
    steps = []
    for nid in order:
        n = dict(nodes[nid])
        n["vscode"] = vscode_url(repo_root, n.get("file"), n.get("line"))
        n["outgoing"] = outgoing.get(nid, [])
        steps.append(n)
    mermaid = DIAGRAMS.get(flow.get("diagram", "flowchart"), flowchart)(flow)
    return {
        "id": flow["id"], "title": flow["title"], "mode": flow.get("mode", "code"),
        "summary": flow.get("summary", ""), "notes": flow.get("notes", []),
        "steps": steps, "mermaid": mermaid,
    }


def asset_tag(key: str, offline: bool) -> str:
    is_css = key.endswith("_css")
    vendor_file = VENDOR / VENDOR_FILES[key]
    if offline and vendor_file.exists():
        body = vendor_file.read_text(encoding="utf-8")
        if is_css:
            return f"<style>\n{body}\n</style>"
        return "<script>\n" + body.replace("</script", "<\\/script") + "\n</script>"
    if offline:
        print(f"warning: {vendor_file} not found, using CDN for {key}", file=sys.stderr)
    url = CDN[key]
    return f'<link rel="stylesheet" href="{url}">' if is_css else f'<script src="{url}"></script>'


def render(data: dict, offline: bool = False, repo_root: Path | None = None) -> str:
    page = {
        "project": data.get("project", "Project"),
        "generated_at": data.get("generated_at", ""),
        "flows": [build_flow(f, repo_root) for f in data["flows"]],
    }
    payload = json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    title = f"{page['project']} – code flow"
    title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    replacements = {
        "{{TITLE}}": title,
        "{{BOOTSTRAP_CSS}}": asset_tag("bootstrap_css", offline),
        "{{BOOTSTRAP_JS}}": asset_tag("bootstrap_js", offline),
        "{{MERMAID_JS}}": asset_tag("mermaid_js", offline),
        "{{PANZOOM_JS}}": asset_tag("panzoom_js", offline),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)
    # DATA_JSON last so placeholders inside user data are never re-substituted
    return html.replace("{{DATA_JSON}}", payload)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow_json")
    ap.add_argument("-o", "--output", default="flow.html")
    ap.add_argument("--offline", action="store_true", help="inline vendor libraries from assets/vendor/")
    ap.add_argument("--repo", help="repo root; adds 'Open in VS Code' links to each step")
    args = ap.parse_args()
    data = json.loads(Path(args.flow_json).read_text(encoding="utf-8"))
    Path(args.output).write_text(render(data, args.offline, Path(args.repo).resolve() if args.repo else None), encoding="utf-8")
    print(f"wrote {args.output} ({len(data['flows'])} flow(s))")


if __name__ == "__main__":
    main()
