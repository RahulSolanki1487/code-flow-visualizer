#!/usr/bin/env python3
"""Validate flow.json: schema, graph integrity and real file:line references.

Usage:
    python validate_flow.py flow.json [--repo PATH]
    python validate_flow.py flow.json --repo web=../web-app --repo api=../api   (nodes carry "repo": "web"|"api")

Exit code 0 = no errors (warnings allowed), 1 = errors found.
"""
import argparse
import json
import sys
from pathlib import Path

from repo_roots import normalize_roots, parse_repo_args, root_for

NODE_TYPES = {"entry", "logic", "data", "external", "decision", "error", "ui", "event"}
EDGE_KINDS = {"normal", "error", "async"}
DIAGRAMS = {"flowchart", "sequence", "state"}
MAX_NODES = 40
MAX_LABEL = 40
SNIPPET_NEAR = 15  # a snippet should start within this many lines of the cited line


def _norm(text: str) -> str:
    return " ".join(text.split())


def check_snippet(file_lines: list[str], snippet: str, line: int) -> str | None:
    """Return a problem description, or None if the snippet is real and near `line`.

    Each snippet line must appear in the file (whitespace-insensitive). A line
    containing '...' only has to match the text before the ellipsis.
    """
    norm_file = [_norm(x) for x in file_lines]
    first_hit = None
    for raw in snippet.splitlines():
        want = _norm(raw.split("...")[0])
        if not want:
            continue
        hits = [i + 1 for i, x in enumerate(norm_file) if want in x]
        if not hits:
            return f"snippet line not found in file: {want[:60]!r}"
        if first_hit is None:
            first_hit = min(hits, key=lambda h: abs(h - line))
    if first_hit is not None and abs(first_hit - line) > SNIPPET_NEAR:
        return f"snippet found at line {first_hit}, but node cites line {line}"
    return None


def validate(data: dict, repo=None):
    """`repo` may be None, one Path, or {name: Path} for flows that span several repos (node field `repo`)."""
    roots = normalize_roots(repo)
    errors, warnings = [], []
    flows = data.get("flows")
    if not isinstance(flows, list) or not flows:
        return ["top-level 'flows' must be a non-empty list"], warnings
    flow_ids = [f.get("id") for f in flows]
    if len(set(flow_ids)) != len(flow_ids):
        errors.append("duplicate flow ids")
    line_cache: dict[tuple, list[str]] = {}

    for f in flows:
        fid = f.get("id", "?")
        p = f"flow '{fid}'"
        for key in ("id", "title", "mode", "summary", "entry", "nodes", "edges"):
            if key not in f:
                errors.append(f"{p}: missing '{key}'")
        if f.get("mode") not in ("code", "user"):
            errors.append(f"{p}: mode must be 'code' or 'user'")
        if f.get("diagram", "flowchart") not in DIAGRAMS:
            errors.append(f"{p}: diagram must be one of {', '.join(sorted(DIAGRAMS))}")
        nodes = f.get("nodes", [])
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids):
            errors.append(f"{p}: duplicate node ids")
        idset = set(ids)
        if f.get("entry") not in idset:
            errors.append(f"{p}: entry '{f.get('entry')}' is not a node id")
        if len(nodes) > MAX_NODES:
            warnings.append(f"{p}: {len(nodes)} nodes (> {MAX_NODES}); consider splitting (python split_flow.py flow.json -o flow.json)")

        for n in nodes:
            np_ = f"{p} node '{n.get('id')}'"
            for key in ("id", "label", "type", "description"):
                if not n.get(key):
                    errors.append(f"{np_}: missing '{key}'")
            if n.get("type") and n["type"] not in NODE_TYPES:
                errors.append(f"{np_}: unknown type '{n['type']}'")
            if len(str(n.get("label", ""))) > MAX_LABEL:
                warnings.append(f"{np_}: label longer than {MAX_LABEL} chars")
            if n.get("link_to") and n["link_to"] not in flow_ids:
                errors.append(f"{np_}: link_to '{n['link_to']}' is not a flow id")
            for caller in n.get("callers") or []:
                if caller.get("flow") not in flow_ids:
                    errors.append(f"{np_}: callers entry points at unknown flow '{caller.get('flow')}'")
            if n.get("inferred") and not n.get("note"):
                warnings.append(f"{np_}: inferred but no 'note' explaining why")
            file_, line = n.get("file"), n.get("line")
            if not file_:
                if n.get("type") != "external":
                    errors.append(f"{np_}: missing 'file' (only external nodes may omit it)")
                continue
            if not roots:
                continue
            repo_root, repo_problem = root_for(roots, n)
            if repo_problem:
                errors.append(f"{np_}: {repo_problem}")
                continue
            path = (repo_root / file_).resolve()
            try:
                path.relative_to(repo_root.resolve())
            except ValueError:
                errors.append(f"{np_}: file '{file_}' is outside the repo")
                continue
            if not path.is_file():
                errors.append(f"{np_}: file not found: {file_}" + (f" (repo '{n['repo']}')" if n.get("repo") else ""))
                continue
            if line is None:
                warnings.append(f"{np_}: no line number")
                continue
            cache_key = (str(repo_root.resolve()), file_)
            if cache_key not in line_cache:
                line_cache[cache_key] = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            total = len(line_cache[cache_key])
            if not isinstance(line, int) or line < 1 or line > total:
                errors.append(f"{np_}: line {line} out of range (file has {total} lines)")
                continue
            if n.get("snippet"):
                problem = check_snippet(line_cache[cache_key], n["snippet"], line)
                if problem:
                    # invented code is an error; merely distant code is a warning
                    (warnings if "but node cites" in problem else errors).append(f"{np_}: {problem}")

        reached = set()
        for i, e in enumerate(f.get("edges", [])):
            ep = f"{p} edge #{i}"
            for end in ("from", "to"):
                if e.get(end) not in idset:
                    errors.append(f"{ep}: '{end}' = '{e.get(end)}' is not a node id")
            if e.get("kind", "normal") not in EDGE_KINDS:
                errors.append(f"{ep}: unknown kind '{e.get('kind')}'")
            reached.update((e.get("from"), e.get("to")))
        orphans = idset - reached - {f.get("entry")}
        if orphans and len(nodes) > 1:
            warnings.append(f"{p}: nodes with no edges: {', '.join(sorted(orphans))}")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow_json")
    ap.add_argument("--repo", action="append",
                    help="repo root; enables file:line checks. Repeat as NAME=PATH for flows spanning several repos")
    args = ap.parse_args()
    try:
        data = json.loads(Path(args.flow_json).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {args.flow_json}: {exc}")
        sys.exit(1)
    errors, warnings = validate(data, parse_repo_args(args.repo))
    for w in warnings:
        print(f"WARN:  {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
