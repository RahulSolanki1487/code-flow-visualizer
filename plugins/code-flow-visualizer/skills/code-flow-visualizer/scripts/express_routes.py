"""Express routes with the prefixes of their router graph.

Understands `const r = Router()` / `express()`, route calls (`r.get('/x', ...)`, `r.route('/x').get(...).post(...)`),
mounts (`app.use('/api', r)`, `app.use(r)`, `r.use(a).use(b)` chains, `Router().use('/api', api)` as an anonymous default
export) and how routers reach each other: `import x from './x'`, `import { x } from './x'`, `require('./x')`,
`export default router`, `module.exports = router`. A router that nothing mounts is a root with an unknown prefix.
"""
import os
import re
from pathlib import Path

VERBS = ("get", "post", "put", "patch", "delete", "options", "head", "all")
SKIP = {"node_modules", "dist", "build", "coverage", ".next", "test", "tests", "__tests__"}
EXTS = (".ts", ".js", ".mjs", ".cjs")

DEFINITION_RE = re.compile(
    r"(?:const|let|var)\s+(\w+)\s*(?::\s*[\w<>\[\]., ]+)?=\s*(?:await\s+)?((?:express\.|require\(\s*['\"]express['\"]\s*\)\.)?(?:Router|express))\s*\(")
DEFAULT_EXPORT_RE = re.compile(r"(?:export\s+default|module\.exports\s*=)\s*((?:express\.)?Router\s*\(|\w+\s*;?)")
CHAIN_RE = re.compile(r"\s*\.\s*(use|route|all|get|post|put|patch|delete|options|head)\s*\(")
STATEMENT_RE = re.compile(r"(?<![\w.$])(\w+)\s*\.\s*(?=(?:use|route|all|get|post|put|patch|delete|options|head)\s*\()")
IMPORT_DEFAULT_RE = re.compile(r"import\s+(\w+)\s+from\s+['\"](\.[^'\"]*)['\"]")
IMPORT_NAMED_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s+['\"](\.[^'\"]*)['\"]")
REQUIRE_RE = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['\"](\.[^'\"]*)['\"]\s*\)")
REQUIRE_DESTRUCT_RE = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*['\"](\.[^'\"]*)['\"]\s*\)")
INLINE_REQUIRE_RE = re.compile(r"^require\(\s*['\"](\.[^'\"]*)['\"]\s*\)$")
STRING_ARG_RE = re.compile(r"""^(['"`])(.*)\1$""", re.S)


def join(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def strip_comments(text: str) -> str:
    """Blank out // and /* */ comments (quote aware, so `'http://x'` survives), keeping newlines."""
    out, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(re.sub(r"[^\n]", " ", text[i:end]))
            i = end
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def balanced(text: str, start: int) -> str:
    depth, i, quote = 1, start, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return text[start:]


def split_args(args: str) -> list[str]:
    out, depth, quote, cur = [], 0, None, []
    for c in args:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


class Source:
    def __init__(self, rel: str, text: str):
        self.rel, self.text = rel, text
        self.nodes: dict[str, str] = {}               # variable -> "app" | "router"
        self.events: dict[str, list] = {}             # variable -> [(call, args, pos)]
        self.default: str | None = None               # variable exported as default / module.exports
        self.imports: dict[str, tuple] = {}           # local name -> (relative path, imported name or "default")


def collect(repo: Path, read) -> list[dict]:
    sources = {}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for n in files:
            if n.endswith(EXTS) and not n.endswith((".d.ts", ".spec.ts", ".test.ts", ".spec.js", ".test.js")):
                rel = (Path(root) / n).relative_to(repo).as_posix()
                text = strip_comments(read(rel))
                if re.search(r"\bRouter\s*\(|\bexpress\s*\(|\b(?:router|app|api|routes)\s*\.\s*(?:use|get|post|put|patch|delete|route|all)\s*\(", text):
                    sources[rel] = Source(rel, text)
    if not sources:
        return []
    for s in sources.values():
        _parse(s)
    if not any(s.nodes for s in sources.values()):
        return []

    def target_file(rel_from: str, relative: str):
        base = (Path(rel_from).parent / relative).as_posix()
        for cand in [base] + [base + e for e in EXTS] + [base + "/index" + e for e in EXTS]:
            norm = os.path.normpath(cand).replace("\\", "/")
            if norm in sources:
                return norm
        return None

    def default_node(rel: str):
        s = sources.get(rel)
        if not s:
            return None
        if s.default:
            return rel, s.default
        routers = [v for v, k in s.nodes.items() if k == "router"]
        return (rel, routers[0]) if len(routers) == 1 else None

    def resolve(s: Source, expr: str):
        """(file, variable) a mount argument refers to, or None for middleware / unknown values."""
        expr = expr.strip()
        inline = INLINE_REQUIRE_RE.match(expr)
        if inline:
            f = target_file(s.rel, inline.group(1))
            return default_node(f) if f else None
        if re.fullmatch(r"\w+", expr):
            if expr in s.nodes:
                return s.rel, expr
            if expr in s.imports:
                relative, name = s.imports[expr]
                f = target_file(s.rel, relative)
                if not f:
                    return None
                if name == "default":
                    return default_node(f)
                return (f, name) if name in sources[f].nodes else None
        return None

    children: dict[tuple, list] = {}   # node -> [(child node, prefix, known)]
    routes: dict[tuple, list] = {}     # node -> [{"method", "path", "line", "file"}]
    mounted = set()
    for s in sources.values():
        for var, events in s.events.items():
            node = (s.rel, var)
            current = None
            for call, args, pos in events:
                line = s.text.count("\n", 0, pos) + 1
                first = STRING_ARG_RE.match(args[0]) if args else None
                if call == "route":
                    current = first.group(2) if first else None
                elif call == "use":
                    prefix, rest = (first.group(2), args[1:]) if first else ("", args)
                    for a in rest:
                        child = resolve(s, a)
                        if child:
                            children.setdefault(node, []).append((child, prefix))
                            mounted.add(child)
                elif call in VERBS:
                    path = first.group(2) if first else current
                    if path is not None:
                        for method in ([None] if call == "all" else [call.upper()]):
                            routes.setdefault(node, []).append({"method": method, "path": path, "line": line, "file": s.rel})
    out: list[dict] = []

    def walk(node, prefix: str, known: bool, seen: tuple):
        for r in routes.get(node, []):
            out.append({**r, "path": join(prefix, r["path"]), "known": known, "view": ""})
        for child, p in children.get(node, []):
            if child not in seen:
                walk(child, join(prefix, p), known, seen + (child,))

    for s in sources.values():
        for var, kind in s.nodes.items():
            node = (s.rel, var)
            if kind == "app":
                walk(node, "", True, (node,))
            elif node not in mounted:
                walk(node, "", False, (node,))
    return out


def _parse(s: Source) -> None:
    text = s.text
    for m in IMPORT_DEFAULT_RE.finditer(text):
        s.imports[m.group(1)] = (m.group(2), "default")
    for m in IMPORT_NAMED_RE.finditer(text):
        for part in m.group(1).split(","):
            name, _, alias = part.strip().partition(" as ")
            if name.strip():
                s.imports[(alias or name).strip()] = (m.group(2), name.strip())
    for m in REQUIRE_RE.finditer(text):
        s.imports[m.group(1)] = (m.group(2), "default")
    for m in REQUIRE_DESTRUCT_RE.finditer(text):
        for part in m.group(1).split(","):
            name, _, alias = part.strip().partition(":")
            if name.strip():
                s.imports[(alias or name).strip()] = (m.group(2), name.strip())
    consumed: list[tuple[int, int]] = []

    def chain(var: str, pos: int):
        """Collect the `.use()/.get()/.route()` calls chained from `pos`; returns the end of the chain."""
        while True:
            m = CHAIN_RE.match(text, pos)
            if not m:
                return pos
            body = balanced(text, m.end())
            s.events.setdefault(var, []).append((m.group(1), split_args(body), m.start()))
            pos = m.end() + len(body) + 1

    for m in DEFINITION_RE.finditer(text):
        var, kind = m.group(1), ("app" if m.group(2).endswith("express") and "Router" not in m.group(2) else "router")
        s.nodes[var] = kind
        after = m.end() + len(balanced(text, m.end())) + 1
        end = chain(var, after)
        consumed.append((m.start(), end))
    anonymous = DEFAULT_EXPORT_RE.search(text)
    if anonymous:
        tail = anonymous.group(1)
        if tail.rstrip().startswith(("Router", "express.Router")):
            var = "<default>"
            s.nodes[var] = "router"
            start = anonymous.end()
            end = chain(var, start + len(balanced(text, start)) + 1)
            consumed.append((anonymous.start(), end))
            s.default = var
        else:
            s.default = tail.strip().rstrip(";").strip()
    for m in STATEMENT_RE.finditer(text):
        if any(a <= m.start() < b for a, b in consumed):
            continue
        var = m.group(1)
        if var in s.nodes or var in ("app", "router", "api", "routes"):
            s.nodes.setdefault(var, "router")   # used but defined elsewhere (or not detected): an implicit router
            chain(var, m.end(1))
    if s.default and s.default not in s.nodes:
        s.default = None
