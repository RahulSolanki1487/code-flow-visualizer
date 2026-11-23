#!/usr/bin/env python3
"""Build the full route table of a backend repo: method + full path (with class/group prefixes).

Usage:
    python route_table.py <backend_repo> [--json]

Built on find_entry_points.py. Per framework, a resolver adds the prefix that the entry-point
scan reports separately (Spring class @RequestMapping, ASP.NET [Route("api/[controller]")] and
MapGroup(...), Express app.use('/api', router), NestJS @Controller('x'), FastAPI/Flask prefixes).
A route whose prefix could not be determined has prefix_known = False; the matcher then treats it
as "the real URL may carry more path segments in front".
"""
import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import django_routes
import find_entry_points
import rails_routes
from find_entry_points import SKIP_DIRS

VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}


@dataclass
class Route:
    method: str | None  # None = any method
    path: str
    file: str
    line: int
    framework: str
    action: str = ""
    prefix_known: bool = True
    repo: str = ""  # backend repo name; set by match_api when several repos are involved


def join_path(*parts: str) -> str:
    segments = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segments)


def verb_of(raw: str) -> str | None:
    v = raw.lower().replace("http", "").replace("mapping", "")
    return v.upper() if v in VERBS else None


def read_text(repo: Path, rel: str, cache: dict) -> str:
    if rel not in cache:
        try:
            cache[rel] = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            cache[rel] = ""
    return cache[rel]


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def files_with_suffix(repo: Path, suffixes: set[str]):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if Path(name).suffix.lower() in suffixes:
                path = Path(root) / name
                yield path.relative_to(repo).as_posix(), path


# --- per-framework resolvers: (repo, route hits of that framework, all hits, text cache) -> [Route] -----------------

def resolve_spring(repo, hits, all_hits, cache):
    prefixes = [h for h in all_hits if h["framework"] == "spring" and h["kind"] == "prefix"]
    out = []
    for h in hits:
        verb, path, action = (h["groups"] + ["", "", ""])[:3]
        same_file = [p for p in prefixes if p["file"] == h["file"] and p["line"] <= h["line"]]
        prefix = max(same_file, key=lambda p: p["line"])["groups"][0] if same_file else ""
        out.append(Route(verb_of(verb), join_path(prefix, path), h["file"], h["line"], "spring", action))
    return out


CLASS_RE = re.compile(r"\bclass\s+(\w+)")
ROUTE_ATTR_RE = re.compile(r'\[Route\(\s*"([^"]*)"\s*\)\]')


def resolve_aspnet(repo, hits, all_hits, cache):
    out = []
    for h in hits:
        text = read_text(repo, h["file"], cache)
        verb, inline, route_attr, action = (h["groups"] + ["", "", "", ""])[:4]
        hit_pos = sum(len(x) + 1 for x in text.split("\n")[:h["line"] - 1])
        classes = [m for m in CLASS_RE.finditer(text) if m.start() < hit_pos]
        prefix, ctrl = "", ""
        if classes:
            cls = classes[-1]
            prev_end = classes[-2].end() if len(classes) > 1 else 0
            attrs = ROUTE_ATTR_RE.findall(text[max(prev_end, cls.start() - 600):cls.start()])
            ctrl = re.sub(r"Controller$", "", cls.group(1))
            prefix = attrs[-1] if attrs else ""
        prefix = prefix.replace("[controller]", ctrl.lower()).replace("[action]", action.lower())
        tail = (route_attr or inline).replace("[action]", action.lower()).replace("[controller]", ctrl.lower())
        out.append(Route(verb_of(verb), join_path(prefix, tail), h["file"], h["line"], "aspnet", action))
    return out


STATIC_MAP_RE = re.compile(r"static\s+[\w<>.?]+\s+(Map\w*)\s*\(\s*(this\b)?")
STATIC_CLASS_RE = re.compile(r"static\s+class\s+(\w+)")
MAPGROUP_RE = re.compile(r'MapGroup\(\s*"([^"]*)"')


def resolve_aspnet_minimal(repo, hits, all_hits, cache):
    """app.MapGet inside `static ... MapXEndpoint(this ...)` or `Class.Map(group)`: the prefix is the
    nearest MapGroup before the call site of that method."""
    cs = {rel: read_text(repo, rel, cache) for rel, _ in files_with_suffix(repo, {".cs"})}
    out = []
    for h in hits:
        verb, path = (h["groups"] + ["", ""])[:2]
        text = cs.get(h["file"]) or read_text(repo, h["file"], cache)
        before = "\n".join(text.split("\n")[:h["line"]])
        methods = list(STATIC_MAP_RE.finditer(before))
        if not methods:  # top-level (Program.cs) route
            out.append(Route(verb_of(verb), join_path(path), h["file"], h["line"], "aspnet-minimal"))
            continue
        method = methods[-1]
        name, is_extension = method.group(1), bool(method.group(2))
        classes = STATIC_CLASS_RE.findall(before)
        if is_extension or not classes:
            call_re = re.compile(r"\.\s*" + re.escape(name) + r"\s*\(")
        else:
            call_re = re.compile(r"\b" + re.escape(classes[-1]) + r"\s*\.\s*" + re.escape(name) + r"\s*\(")
        prefix, known = "", False
        for rel, body in cs.items():
            if rel == h["file"]:
                continue
            m = call_re.search(body)
            if m:
                groups = MAPGROUP_RE.findall(body[:m.start()])
                prefix, known = (groups[-1] if groups else ""), True
                break
        label = f"{classes[-1]}.{name}" if classes else name
        out.append(Route(verb_of(verb), join_path(prefix, path), h["file"], h["line"], "aspnet-minimal", label, known))
    return out


IMPORT_RE = re.compile(
    r"""(?:(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['"](\.[^'"]+)['"]\s*\)|import\s+(\w+)\s+from\s+['"](\.[^'"]+)['"])""")
USE_RE = re.compile(r"""\.use\(\s*['"]([^'"]*)['"]\s*,\s*(\w+)""")


def resolve_express(repo, hits, all_hits, cache):
    js = {rel: read_text(repo, rel, cache) for rel, _ in files_with_suffix(repo, {".js", ".ts", ".mjs"})}
    mounts: dict[str, list[str]] = {}  # router file -> prefixes
    for rel, body in js.items():
        imports = {}
        for m in IMPORT_RE.finditer(body):
            name, target = (m.group(1) or m.group(3)), (m.group(2) or m.group(4))
            base = (Path(rel).parent / target).as_posix()
            for cand in (base, base + ".js", base + ".ts", base + "/index.js", base + "/index.ts"):
                norm = os.path.normpath(cand).replace("\\", "/")
                if norm in js:
                    imports[name] = norm
                    break
        for m in USE_RE.finditer(body):
            target = imports.get(m.group(2))
            if target:
                mounts.setdefault(target, []).append(m.group(1))
    out = []
    for h in hits:
        verb, path = (h["groups"] + ["", ""])[:2]
        prefixes = mounts.get(h["file"])
        if prefixes:
            out.extend(Route(verb_of(verb), join_path(p, path), h["file"], h["line"], "express") for p in prefixes)
        else:
            is_app_file = "express()" in js.get(h["file"], "")
            out.append(Route(verb_of(verb), join_path(path), h["file"], h["line"], "express", "", is_app_file))
    return out


NEST_CTRL_RE = re.compile(r"""@Controller\(\s*['"]([^'"]*)['"]""")


def resolve_nestjs(repo, hits, all_hits, cache):
    out = []
    for h in hits:
        verb, path = (h["groups"] + ["", ""])[:2]
        text = read_text(repo, h["file"], cache)
        pos = sum(len(x) + 1 for x in text.split("\n")[:h["line"] - 1])
        prefixes = NEST_CTRL_RE.findall(text[:pos])
        out.append(Route(verb_of(verb), join_path(prefixes[-1] if prefixes else "", path), h["file"], h["line"], "nestjs"))
    return out


PY_PREFIX_RE = re.compile(r"""(?:APIRouter\([^)]*prefix\s*=|Blueprint\([^)]*url_prefix\s*=)\s*['"]([^'"]+)['"]""")


def resolve_python(repo, hits, all_hits, cache):
    out = []
    for h in hits:
        verb, path = (h["groups"] + ["", ""])[:2]
        text = read_text(repo, h["file"], cache)
        prefixes = PY_PREFIX_RE.findall(text)
        uses_router = bool(re.search(r"APIRouter\(|Blueprint\(", text))
        known = bool(prefixes) or not uses_router
        out.append(Route(verb_of(verb), join_path(prefixes[0] if prefixes else "", path), h["file"], h["line"], h["framework"], "", known))
    return out


def resolve_default(repo, hits, all_hits, cache):
    out = []
    for h in hits:
        groups = h["groups"] + ["", ""]
        method = verb_of(groups[0]) if groups[0] else None
        path = next((g for g in groups if g.startswith("/") or "/" in g), groups[1])
        out.append(Route(method, join_path(path), h["file"], h["line"], h["framework"], "", False))
    return out


def resolve_django_repo(repo, cache):
    read = lambda rel: read_text(repo, rel, cache)  # noqa: E731
    return [Route(r["method"], r["path"], r["file"], r["line"], "django", r["view"], r["known"])
            for r in django_routes.collect(repo, read)]


def resolve_rails_repo(repo, cache):
    read = lambda rel: read_text(repo, rel, cache)  # noqa: E731
    return [Route(r["method"], r["path"], r["file"], r["line"], "rails", r["view"], r["known"])
            for r in rails_routes.collect(repo, read)]


# resolvers that read whole route files of a repo (keyed by the framework names the entry-point scan uses)
REPO_RESOLVERS = {"django": resolve_django_repo, "rails": resolve_rails_repo}

RESOLVERS = {
    "spring": resolve_spring, "aspnet": resolve_aspnet, "aspnet-minimal": resolve_aspnet_minimal,
    "express": resolve_express, "nestjs": resolve_nestjs, "fastapi-flask": resolve_python,
}
ROUTE_FRAMEWORK_ALIASES = {"fastapi": "fastapi-flask", "flask": "fastapi-flask"}


def collect_routes(repo: Path, limit: int = 100000) -> list[Route]:
    hits = find_entry_points.scan(repo, limit)
    route_hits = [h for h in hits if h["kind"] == "route"]
    by_fw: dict[str, list[dict]] = {}
    for h in route_hits:
        by_fw.setdefault(ROUTE_FRAMEWORK_ALIASES.get(h["framework"], h["framework"]), []).append(h)
    cache: dict = {}
    routes: list[Route] = []
    for fw, fw_hits in by_fw.items():
        if fw in REPO_RESOLVERS:
            continue  # these frameworks are resolved from whole route files, not from single entry-point hits
        routes.extend(RESOLVERS.get(fw, resolve_default)(repo, fw_hits, hits, cache))
    for resolver in REPO_RESOLVERS.values():
        routes.extend(resolver(repo, cache))
    return routes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    routes = collect_routes(Path(args.repo))
    if args.json:
        print(json.dumps([asdict(r) for r in routes], indent=2))
        return 0
    for r in routes:
        print(f"  {(r.method or 'ANY'):<7} {r.path:<52} {r.file}:{r.line}" + ("" if r.prefix_known else "  [prefix unknown]"))
    print(f"\n{len(routes)} route(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
