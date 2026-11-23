"""FastAPI and Flask routes with the prefixes of their router graph.

FastAPI: `router = APIRouter(prefix="/items")`, `@router.get("/{id}")`, and `parent.include_router(child, prefix=...)`
chains that can span several files (`app.include_router(api_router, prefix=settings.API_V1_STR)`).
Flask: `Blueprint(..., url_prefix=...)`, `@bp.route("/x", methods=[...])` and `app.register_blueprint(bp, url_prefix=...)`.

Prefix expressions may be string literals, f-strings, or names/attributes of string constants defined anywhere in the repo
(`API_V1_STR: str = "/api/v1"`). A prefix that cannot be resolved marks the routes below it as unknown. Routers that nothing
includes are roots with an unknown prefix.
"""
import os
import re
from pathlib import Path

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")
SKIP = {"node_modules", "venv", ".venv", "env", "__pycache__", "site-packages", "alembic", "migrations", "tests", "test"}

DEFINITION_RE = re.compile(r"^(\w+)\s*(?::\s*[\w\[\], .]+)?=\s*(FastAPI|APIRouter|Blueprint|Flask)\s*\(", re.M)
DECORATOR_RE = re.compile(r"^[ \t]*@(\w+)\.(get|post|put|patch|delete|options|head|route|api_route)\s*\(", re.M)
INCLUDE_RE = re.compile(r"(\w+)\.(include_router|register_blueprint)\s*\(")
CONSTANT_RE = re.compile(r"^[ \t]*(\w+)\s*(?::\s*[\w\[\], .]+)?=\s*(['\"])(.*?)\2\s*$", re.M)
FROM_IMPORT_RE = re.compile(r"^from\s+(\.*)([\w.]*)\s+import\s+(\(.*?\)|[^\n]+)", re.M | re.S)
IMPORT_AS_RE = re.compile(r"^import\s+([\w.]+)(?:\s+as\s+(\w+))?", re.M)
STRING_RE = re.compile(r"""\s*(f?)(['"])(.*?)(?<!\\)\2\s*$""", re.S)


def join(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def balanced(text: str, start: int) -> str:
    """Text from just after an opening paren to its matching close paren."""
    depth, i, quote = 1, start, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return text[start:]


def split_args(args: str) -> list[str]:
    """Top-level comma-separated arguments."""
    out, depth, quote, cur = [], 0, None, []
    for c in args:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in "'\"":
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


def keyword(args: list[str], *names: str):
    for a in args:
        m = re.match(r"(\w+)\s*=\s*(.*)$", a, re.S)
        if m and m.group(1) in names:
            return m.group(2).strip()
    return None


class Module:
    def __init__(self, rel: str, text: str):
        self.rel, self.text = rel, text
        self.defs: dict[str, dict] = {}     # var -> {"kind", "prefix_expr", "line"}
        self.imports: dict[str, tuple] = {}  # local name -> (dotted module, symbol or None)


def collect(repo: Path, read) -> list[dict]:
    files = {}
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for n in names:
            if n.endswith(".py"):
                files[(Path(root) / n).relative_to(repo).as_posix()] = None
    mods = {}
    for rel in files:
        text = read(rel)
        if re.search(r"\b(FastAPI|APIRouter|Blueprint|Flask)\s*\(", text) or DECORATOR_RE.search(text):
            mods[rel] = Module(rel, text)
    if not mods:
        return []
    constants = _constants(files, read)
    for m in mods.values():
        _parse_definitions(m)
        _parse_imports(m)
    if not any(d for m in mods.values() for d in m.defs):
        return []

    def module_file(dotted: str, rel_from: str = "", dots: int = 0):
        """File of a dotted module (absolute by path suffix, relative by package of `rel_from`)."""
        parts = dotted.split(".") if dotted else []
        if dots:
            base = Path(rel_from).parent
            for _ in range(dots - 1):
                base = base.parent
            parts = list(base.parts) + parts
        tail = "/".join(parts)
        for rel in files:
            if rel == tail + ".py" or rel.endswith("/" + tail + ".py") or rel == tail + "/__init__.py" or rel.endswith("/" + tail + "/__init__.py"):
                return rel
        return None

    def resolve_name(mod: Module, expr: str):
        """(file, var) a router expression refers to: `router`, `items.router`, `alias`."""
        expr = expr.strip()
        head, _, rest = expr.partition(".")
        if not rest and head in mod.defs:
            return mod.rel, head
        if head in mod.imports:
            dotted, symbol, dots = mod.imports[head]
            if symbol is None:          # imported a module: `from app.api.routes import items` / `import items`
                target = module_file(dotted, mod.rel, dots)
                return (target, rest) if target and rest else None
            target = module_file(dotted, mod.rel, dots)  # imported a symbol: `from .items import router as r`
            sub = module_file((dotted + "." if dotted else "") + symbol, mod.rel, dots)
            if sub and rest:                                # symbol is itself a module
                return sub, rest
            return (target, symbol) if target and not rest else None
        return None

    def prefix_value(expr, mod):
        """(string, known). A missing prefix is known and empty."""
        if expr is None:
            return "", True
        return _eval_prefix(expr, constants)

    # nodes and edges ------------------------------------------------------
    routes_by_node: dict[tuple, list] = {}
    for m in mods.values():
        for d in DECORATOR_RE.finditer(m.text):
            var = d.group(1)
            node = resolve_name(m, var)
            if not node or node[1] not in mods.get(node[0], Module("", "")).defs:
                continue
            args = split_args(balanced(m.text, d.end()))
            path_arg = args[0] if args and not re.match(r"\w+\s*=", args[0]) else (keyword(args, "path", "rule") or '""')
            path, known = _eval_prefix(path_arg, constants)
            verb = d.group(2)
            if verb in HTTP_METHODS:
                methods = [verb.upper()]
            else:
                found = keyword(args, "methods")
                methods = [v.upper() for v in re.findall(r"['\"](\w+)['\"]", found)] if found else ["GET"]
            line = m.text.count("\n", 0, d.start()) + 1
            fn = re.search(r"def\s+(\w+)", m.text[d.end():d.end() + 600])
            for method in methods:
                routes_by_node.setdefault(node, []).append({"method": method, "path": path, "known": known, "file": m.rel, "line": line,
                                                            "view": fn.group(1) if fn else ""})
    children: dict[tuple, list] = {}   # parent node -> [(child node, prefix, known)]
    included = set()
    for m in mods.values():
        for inc in INCLUDE_RE.finditer(m.text):
            parent = resolve_name(m, inc.group(1))
            args = split_args(balanced(m.text, inc.end()))
            if not parent or not args:
                continue
            child = resolve_name(m, args[0])
            if not child:
                continue
            expr = keyword(args[1:], "prefix", "url_prefix")
            value, known = prefix_value(expr, m)
            children.setdefault(parent, []).append((child, value, known))
            included.add(child)

    def own_prefix(node):
        mod = mods.get(node[0])
        d = mod.defs.get(node[1]) if mod else None
        if not d or d["kind"] in ("FastAPI", "Flask"):
            return "", True
        return prefix_value(d["prefix_expr"], mod)

    out: list[dict] = []

    def walk(node, effective: str, known: bool, seen: tuple):
        for r in routes_by_node.get(node, []):
            out.append({**r, "path": join(effective, r["path"]), "known": known and r["known"]})
        for child, value, ok in children.get(node, []):
            if child in seen:
                continue
            own, own_ok = own_prefix(child)
            walk(child, join(effective, value, own), known and ok and own_ok, seen + (child,))

    all_nodes = [(m.rel, v) for m in mods.values() for v in m.defs]
    for node in all_nodes:
        kind = mods[node[0]].defs[node[1]]["kind"]
        if kind in ("FastAPI", "Flask"):
            walk(node, "", True, (node,))
        elif node not in included:  # a router/blueprint nobody includes: prefix unknown
            own, own_ok = own_prefix(node)
            walk(node, own, False, (node,))
    return out


def _constants(files: dict, read) -> dict:
    out = {}
    for rel in files:
        for m in CONSTANT_RE.finditer(read(rel)):
            out.setdefault(m.group(1), m.group(3))
    return out


def _parse_definitions(mod: Module) -> None:
    for m in DEFINITION_RE.finditer(mod.text):
        args = split_args(balanced(mod.text, m.end()))
        mod.defs[m.group(1)] = {"kind": m.group(2), "prefix_expr": keyword(args, "prefix", "url_prefix"),
                                "line": mod.text.count("\n", 0, m.start()) + 1}


def _parse_imports(mod: Module) -> None:
    for m in FROM_IMPORT_RE.finditer(mod.text):
        dots, base, names = len(m.group(1)), m.group(2), m.group(3).strip("() \n")
        for part in re.split(r"\s*,\s*", names.replace("\n", " ")):
            if not part:
                continue
            name, _, alias = part.partition(" as ")
            mod.imports[(alias or name).strip()] = (base, name.strip(), dots)
    for m in IMPORT_AS_RE.finditer(mod.text):
        dotted, alias = m.group(1), m.group(2)
        mod.imports[alias or dotted.split(".")[0]] = (dotted, None, 0)
    # `from app.api.routes import items` imports a *module*; the symbol-vs-module choice is made at resolution time
    for local, (base, symbol, dots) in list(mod.imports.items()):
        if symbol is not None:
            mod.imports[local] = (base, symbol, dots)


def _eval_prefix(expr: str, constants: dict):
    """(value, known) of a prefix/path expression: literal, f-string, constant or attribute of a constant."""
    expr = expr.strip()
    m = STRING_RE.match(expr)
    if m:
        is_f, body = bool(m.group(1)), m.group(3)
        if not is_f:
            return body, True
        known = True

        def sub(ref):
            nonlocal known
            name = ref.group(1).split(".")[-1]
            if name in constants:
                return constants[name]
            known = False
            return ""
        return re.sub(r"\{([\w.]+)\}", sub, body), known
    name = expr.split(".")[-1]
    if re.fullmatch(r"[\w.]+", expr) and name in constants:
        return constants[name], True
    return "", False
