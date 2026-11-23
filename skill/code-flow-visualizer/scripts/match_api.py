#!/usr/bin/env python3
"""Match the HTTP calls of one or more frontend repos to the routes of one or more backend repos.

Usage:
    python match_api.py --frontend ../web-app --backend ../api [--json]
    python match_api.py --frontend web=../web-app --frontend admin=../admin --backend api=../api

Reports, for every frontend call, the backend route(s) it reaches, with a confidence:
  exact   same method, same number of segments, every segment equal or a parameter
  likely  the match needs a guess: a prefix the scan could not resolve (gateway, context path,
          proxy), a base URL held in a variable, or an optional path suffix
and lists calls with no backend route (third-party APIs, static files, dynamic URLs) and routes
that no frontend calls.
"""
import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

import find_api_calls
import gateway_rules
import route_table

PARAM_RE = re.compile(r"\{[^}]*\}|:\w+|<[^>]*>|\[[^\]]*\]")
VERSION_PARAM = re.compile(r"v\{\}")
VERSION_LITERAL = re.compile(r"v\d+")


def segments(path: str) -> list[str]:
    path = find_api_calls.SCHEME_RE.sub("", path or "").split("?", 1)[0].split("#", 1)[0]
    return [PARAM_RE.sub("{}", s.lower()) for s in path.split("/") if s]


def segment_matches(a: str, b: str) -> bool:
    if a == b or "{}" in (a, b) and (a == "{}" or b == "{}"):
        return True
    if (VERSION_PARAM.fullmatch(a) and VERSION_LITERAL.fullmatch(b)) or (VERSION_PARAM.fullmatch(b) and VERSION_LITERAL.fullmatch(a)):
        return True
    for pattern, literal in ((a, b), (b, a)):  # partial parameters such as `item-{}`
        if "{}" in pattern and "{}" not in literal:
            regex = "[^/]+".join(re.escape(p) for p in pattern.split("{}"))
            if re.fullmatch(regex, literal):
                return True
    return False


def compare(call_segs: list[str], route_segs: list[str]):
    """Return (kind, score) when the segment lists line up, else None. kind: equal | call_longer | call_shorter."""
    if len(call_segs) == len(route_segs):
        pairs, kind = list(zip(call_segs, route_segs)), "equal"
    elif len(call_segs) > len(route_segs):
        pairs, kind = list(zip(call_segs[-len(route_segs):] if route_segs else [], route_segs)), "call_longer"
    else:
        pairs, kind = list(zip(call_segs, route_segs[-len(call_segs):] if call_segs else [])), "call_shorter"
    if not all(segment_matches(a, b) for a, b in pairs):
        return None
    return kind, sum(1 for a, b in pairs if a == b)


def match_call(call: dict, route: route_table.Route, rules=()):
    """Return (confidence, score, via) or None. `via` names the gateway rule that rewrote the URL, if any.

    equal length            -> exact (likely when only the optional path suffix made it fit)
    call has extra leading  -> only if the route's prefix is unknown (context path): likely
    route has extra leading -> only if the call starts from a variable base URL: likely
    gateway rule for the route's backend rewrites the call's prefix -> compared as equal: exact
    """
    if route.method is not None and route.method not in call["methods"]:
        return None
    if call.get("unresolved") or call.get("url") is None:
        return None
    base = segments(call["url"])
    variants = [(base, False, "")]
    if call.get("optional_suffix"):
        variants.append((base + ["{}"], True, ""))
    for rule in rules:
        if rule.backend and rule.backend == route.repo:
            for call_segs, via_suffix, _ in list(variants):
                rewritten = gateway_rules.apply_rule(rule, call_segs)
                if rewritten is not None:
                    variants.append((rewritten, via_suffix, f"gateway {rule.source}: /{'/'.join(rule.upstream)}"))
    route_segs = segments(route.path)
    best = None
    for call_segs, via_suffix, via in variants:
        result = compare(call_segs, route_segs)
        if not result:
            continue
        kind, score = result
        if via and kind != "equal":
            continue  # a gateway rule must explain the whole difference
        if kind == "call_longer" and route.prefix_known:
            continue
        if kind == "call_shorter" and not call.get("base_unknown"):
            continue
        confidence = "exact" if kind == "equal" and not via_suffix else "likely"
        candidate = (confidence, score, via)
        if best is None or (confidence == "exact", score) > (best[0] == "exact", best[1]):
            best = candidate
    return best


def match(calls: list[dict], routes: list[route_table.Route], rules=()) -> dict:
    matches, unmatched = [], []
    called = set()
    for call in calls:
        scored = [(hit, idx) for idx, route in enumerate(routes) if (hit := match_call(call, route, rules))]
        if not scored:
            unmatched.append(call)
            continue
        rank = lambda item: (item[0][0] == "exact", item[0][1])  # noqa: E731
        chosen = set()
        for method in call["methods"]:  # a call that picks its verb at runtime can reach one route per verb
            pool = [s for s in scored if routes[s[1]].method in (None, method)]
            if pool:
                top = max(rank(s) for s in pool)
                chosen.update(s[1] for s in pool if rank(s) == top)
        for hit, idx in scored:
            if idx in chosen:
                called.add(idx)
                entry = {"call": call, "route": asdict(routes[idx]), "confidence": hit[0]}
                if hit[2]:
                    entry["via"] = hit[2]
                matches.append(entry)
    uncalled = [asdict(r) for i, r in enumerate(routes) if i not in called]
    return {"matches": matches, "unmatched_calls": unmatched, "uncalled_routes": uncalled}


def parse_repo_args(values: list[str]) -> list[tuple[str, Path]]:
    out = []
    for v in values:
        name, sep, path = v.partition("=")
        if sep and len(name) > 1 and "\\" not in name and "/" not in name:  # NAME=PATH (not C:\... or a path)
            out.append((name, Path(path)))
        else:
            out.append((Path(v).resolve().name, Path(v)))
    return out


def run(frontends: list[tuple[str, Path]], backends: list[tuple[str, Path]], rules=()) -> dict:
    calls = []
    for name, path in frontends:
        for c in find_api_calls.scan(path):
            calls.append({**c, "repo": name})
    routes = []
    for name, path in backends:
        for r in route_table.collect_routes(path):
            r.repo = name
            routes.append(r)
    return match(calls, routes, rules)


def add_gateway_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--gateway-prefix", action="append", metavar="BACKEND=prefix",
                    help="calls to BACKEND carry this prefix, which a gateway strips (repeatable). "
                         "Write it without a leading slash (orders=orders-svc): Git Bash turns /x into a Windows path")
    ap.add_argument("--gateway-config", action="append", metavar="PATH",
                    help="nginx.conf or Ocelot JSON; its rewrite rules are applied (upstream host -> backend by name/folder)")


def build_rules(args, backends: list[tuple[str, Path]]) -> list:
    rules = gateway_rules.explicit_rules(args.gateway_prefix)
    for path in args.gateway_config or []:
        rules.extend(gateway_rules.resolve_hosts(gateway_rules.load_config(Path(path)), backends))
    return rules


def format_report(result: dict, with_repo: bool) -> str:
    lines = []
    grouped: dict[tuple, list] = {}
    for m in result["matches"]:
        c = m["call"]
        grouped.setdefault((c["repo"], c["file"], c["line"], "/".join(c["methods"]), c["url"]), []).append(m)
    lines.append(f"MATCHED ({len(grouped)} call(s))")
    for (repo, file, line, methods, url), ms in sorted(grouped.items()):
        tag = (repo + ":") if with_repo else ""
        lines.append(f"  {methods:<12} {url:<44} {tag}{file}:{line}")
        for m in ms:
            r = m["route"]
            via = f"  ({m['via']})" if m.get("via") else ""
            lines.append(f"      -> [{m['confidence']}] {r['method'] or 'ANY'} {r['path']}   {r.get('repo', '') + ':' if with_repo else ''}{r['file']}:{r['line']}{via}")
    lines.append(f"\nCALLS WITH NO BACKEND ROUTE ({len(result['unmatched_calls'])})")
    for c in result["unmatched_calls"]:
        why = "unresolved URL" if c.get("unresolved") else ("not an internal path" if "://" in (c["url"] or "") else "no route")
        lines.append(f"  {'/'.join(c['methods']):<12} {c['url'] or '(variable)':<44} {c['file']}:{c['line']}   ({why})")
    lines.append(f"\nROUTES NO FRONTEND CALLS ({len(result['uncalled_routes'])})")
    for r in result["uncalled_routes"][:40]:
        lines.append(f"  {r['method'] or 'ANY':<7} {r['path']:<52} {r['file']}:{r['line']}")
    if len(result["uncalled_routes"]) > 40:
        lines.append(f"  ... and {len(result['uncalled_routes']) - 40} more (use --json for all)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frontend", action="append", required=True, help="[NAME=]PATH, repeatable")
    ap.add_argument("--backend", action="append", required=True, help="[NAME=]PATH, repeatable")
    ap.add_argument("--json", action="store_true")
    add_gateway_arguments(ap)
    args = ap.parse_args(argv)
    frontends, backends = parse_repo_args(args.frontend), parse_repo_args(args.backend)
    result = run(frontends, backends, build_rules(args, backends))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result, with_repo=len(frontends) + len(backends) > 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
