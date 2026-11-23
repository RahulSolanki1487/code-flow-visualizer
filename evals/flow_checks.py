"""Machine-checkable assertions for flow.json outputs.

Each check is a small function registered in CHECKS (open/closed: add a function and
register it, nothing else changes). A check receives the parsed flow file, the repo
path (or None) and its parameter, and returns (passed, detail). A check that cannot run
returns (None, reason) and is reported as skipped.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skill" / "code-flow-visualizer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_mermaid  # noqa: E402
import plain_language  # noqa: E402
import validate_flow  # noqa: E402

CHECKS = {}


def check(name):
    def register(fn):
        CHECKS[name] = fn
        return fn
    return register


def _flows(data):
    return data.get("flows", [])


def _nodes(data):
    return [n for f in _flows(data) for n in f.get("nodes", [])]


def _edges(data):
    return [e for f in _flows(data) for e in f.get("edges", [])]


@check("validates")
def validates(data, repo, _param):
    errors, _ = validate_flow.validate(data, repo)
    return (not errors), "; ".join(errors[:3]) or "0 errors"


@check("mermaid_parses")
def mermaid_parses(data, _repo, _param):
    try:
        results = check_mermaid.run_checker(check_mermaid.diagrams(data))
    except check_mermaid.CheckerUnavailable as exc:
        return None, str(exc)
    bad = [r["id"] for r in results if not r["ok"]]
    return (not bad), f"unparseable: {bad}" if bad else f"{len(results)} diagram(s) parse"


@check("max_nodes")
def max_nodes(data, _repo, limit):
    worst = max((len(f.get("nodes", [])) for f in _flows(data)), default=0)
    return worst <= limit, f"largest flow has {worst} nodes (limit {limit})"


@check("mode")
def mode(data, _repo, expected):
    modes = {f.get("mode") for f in _flows(data)}
    return expected in modes, f"modes present: {sorted(modes)}"


@check("diagram")
def diagram(data, _repo, expected):
    kinds = {f.get("diagram", "flowchart") for f in _flows(data)}
    return expected in kinds, f"diagram types present: {sorted(kinds)}"


@check("min_flows")
def min_flows(data, _repo, minimum):
    return len(_flows(data)) >= minimum, f"{len(_flows(data))} flow(s)"


@check("has_error_path")
def has_error_path(data, _repo, _param):
    n = sum(1 for e in _edges(data) if e.get("kind") == "error") or \
        sum(1 for x in _nodes(data) if x.get("type") == "error")
    return n > 0, f"{n} error edge(s)/node(s)"


@check("inferred_has_note")
def inferred_has_note(data, _repo, _param):
    inferred = [x for x in _nodes(data) if x.get("inferred")]
    inferred_edges = [e for e in _edges(data) if e.get("inferred")]
    if not (inferred or inferred_edges):
        return False, "nothing is marked inferred"
    missing = [x["id"] for x in inferred if not x.get("note")]
    notes = [n for f in _flows(data) for n in f.get("notes", [])]
    ok = not missing and (inferred or notes)
    return bool(ok), f"inferred nodes without note: {missing}" if missing else "inferred hops are explained"


@check("share_of_types")
def share_of_types(data, _repo, param):
    types, minimum = set(param["types"]), param["min"]
    nodes = _nodes(data)
    share = sum(1 for n in nodes if n.get("type") in types) / len(nodes) if nodes else 0
    return share >= minimum, f"{share:.0%} of nodes are {sorted(types)} (min {minimum:.0%})"


@check("has_external")
def has_external(data, _repo, _param):
    n = sum(1 for x in _nodes(data) if x.get("type") == "external")
    return n > 0, f"{n} external node(s)"


@check("plain_summary")
def plain_summary(data, _repo, _param):
    """Every flow has an 'In plain words' text a non-technical reader can follow (no code names, paths or syntax)."""
    bad = {f.get("id", "?"): plain_language.problems(f.get("plain_summary")) for f in _flows(data)}
    bad = {fid: why for fid, why in bad.items() if why}
    detail = "; ".join(f"{fid}: {', '.join(why)}" for fid, why in list(bad.items())[:2])
    return (not bad), detail or "every flow has a plain summary"


@check("mentions")
def mentions(data, _repo, words):
    haystack = " ".join(f"{n.get('label', '')} {n.get('description', '')}" for n in _nodes(data)).lower()
    missing = [w for w in words if w.lower() not in haystack]
    return not missing, f"missing: {missing}" if missing else "all key steps present"


def run_checks(data, repo, checks):
    """checks: list of {"check": name, "param": ...}. Returns [(name, passed|None, detail)]."""
    out = []
    for c in checks:
        fn = CHECKS.get(c["check"])
        if fn is None:
            out.append((c["check"], False, "unknown check"))
            continue
        passed, detail = fn(data, repo, c.get("param"))
        out.append((c["check"], passed, detail))
    return out
