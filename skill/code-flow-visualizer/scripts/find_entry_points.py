#!/usr/bin/env python3
"""List likely flow entry points (routes, handlers, screens, CLI mains) in a repo.

Usage:
    python find_entry_points.py <repo_path> [--json] [--limit 200]
"""
import argparse
import json
import os
import re
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", "target",
    "bin", "obj", ".next", ".nuxt", "coverage", ".idea", ".vscode", "vendor", ".dart_tool", "Pods",
}

# (framework, kind, extensions, regex)
PATTERNS = [
    ("express", "route", {".js", ".ts", ".mjs", ".cjs"},
     r"""\b(?:app|router|server)\.(get|post|put|patch|delete|all)\s*\(\s*['"`]([^'"`]+)"""),
    ("nestjs", "route", {".ts"}, r"""@(Get|Post|Put|Patch|Delete)\s*\(\s*['"]?([^'")]*)"""),
    ("fastapi/flask", "route", {".py"},
     r"""@\w+\.(get|post|put|patch|delete|route)\s*\(\s*['"]([^'"]+)"""),
    ("django", "route", {".py"}, r"""\b(?:re_)?path\s*\(\s*r?['"]([^'"]*)['"]\s*,\s*([\w.]+)"""),
    ("spring", "route", {".java", ".kt"},
     r"""@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*\(?\s*(?:value\s*=\s*)?['"]?([^'")]*)"""),
    ("aspnet", "route", {".cs"}, r"""\[(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete)\s*(?:\(\s*"([^"]*)")?"""),
    ("aspnet-minimal", "route", {".cs"}, r"""\b\w+\.Map(Get|Post|Put|Patch|Delete)\s*\(\s*"([^"]+)\""""),
    ("react-router", "screen", {".jsx", ".tsx", ".js", ".ts"}, r"""<Route\b[^>]*\bpath\s*=\s*['"{]+([^'"}]+)"""),
    ("react-router-objects", "screen", {".jsx", ".tsx", ".js", ".ts"},
     r"""^\s*path:\s*['"]([^'"]+)['"],\s*(?:element|Component|lazy)\b()"""),
    ("angular", "screen", {".ts"}, r"""\bpath\s*:\s*['"]([^'"]*)['"]\s*,\s*(?:component|loadChildren|loadComponent)"""),
    ("flutter", "screen", {".dart"}, r"""(?:GoRoute\s*\(\s*path\s*:|['"](/[\w/:-]*)['"]\s*:\s*\()\s*['"]?([^'",)]*)"""),
    ("cli", "main", {".py"}, r"""if\s+__name__\s*==\s*['"]__main__['"]()()"""),
    ("cli", "main", {".go"}, r"""^func\s+main\s*\(\)()()"""),
    ("cli", "command", {".py"}, r"""@\w+\.command\s*\(\s*(?:['"]([^'"]*)['"])?()"""),
    ("jobs", "job", {".py"}, r"""@(?:\w+\.)?(task|shared_task|periodic_task)\b()"""),
    ("jobs", "job", {".java", ".kt"}, r"""@(Scheduled|KafkaListener|RabbitListener)\b()"""),
    ("go-http", "route", {".go"},
     r"""(?:\w+)\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete|HandleFunc|Handle)\s*\(\s*"([^"]+)\""""),
    ("laravel", "route", {".php"}, r"""Route::(get|post|put|patch|delete|any|resource|apiResource)\s*\(\s*['"]([^'"]+)"""),
    ("rails", "route", {".rb"}, r"""^\s*(get|post|put|patch|delete|resources|resource|root)\s+['":]?([\w/:.-]*)""" ),
    ("grpc", "rpc", {".proto"}, r"""^\s*rpc\s+(\w+)\s*\(()"""),
    ("nextjs", "screen", {".tsx", ".jsx", ".ts", ".js"}, r"""^export\s+default\s+(?:async\s+)?function\s+(\w*Page)\b()"""),
]
COMPILED = [(fw, kind, exts, re.compile(rx, re.MULTILINE)) for fw, kind, exts, rx in PATTERNS]


def is_commented(text: str, pos: int, ext: str) -> bool:
    """True if the match at `pos` sits on a comment/doc-comment line (e.g. C# `///` examples)."""
    start = text.rfind("\n", 0, pos) + 1
    prefix = text[start:pos].lstrip()
    if ext in {".py", ".rb"}:
        return prefix.startswith("#")
    return prefix.startswith(("//", "*", "/*"))


def scan(repo: Path, limit: int):
    hits = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            path = Path(root) / name
            ext = path.suffix.lower()
            if not any(ext in exts for _, _, exts, _ in COMPILED):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = path.relative_to(repo).as_posix()
            for fw, kind, exts, rx in COMPILED:
                if ext not in exts:
                    continue
                for m in rx.finditer(text):
                    if is_commented(text, m.start(), ext):
                        continue
                    line = text.count("\n", 0, m.start()) + 1
                    groups = [g for g in m.groups() if g]
                    hits.append({"framework": fw, "kind": kind, "file": rel, "line": line,
                                 "match": " ".join(groups)[:80] or m.group(0).strip()[:80]})
                    if len(hits) >= limit:
                        return hits
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    hits = scan(Path(args.repo), args.limit)
    if args.json:
        print(json.dumps(hits, indent=2))
        return
    if not hits:
        print("No entry points found by heuristics. Look for main files, router configs or ask the user.")
        return
    by_fw = {}
    for h in hits:
        by_fw.setdefault(h["framework"], []).append(h)
    for fw, items in sorted(by_fw.items(), key=lambda kv: -len(kv[1])):
        print(f"\n## {fw} ({len(items)})")
        for h in items:
            print(f"  [{h['kind']}] {h['match']:<40} {h['file']}:{h['line']}")
    if len(hits) >= args.limit:
        print(f"\n(limit {args.limit} reached; use --limit to see more)")


if __name__ == "__main__":
    main()
