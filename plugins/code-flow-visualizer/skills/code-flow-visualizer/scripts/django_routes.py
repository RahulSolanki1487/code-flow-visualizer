"""Django URL routes: `urlpatterns` with `path()`, `re_path()` and the older `url()`, nested `include()`
prefixes and DRF `router.register()`.

Entry: `collect(repo, read)` returns routes with their full path. The root is the module named by
`ROOT_URLCONF` in settings; `urls.py` files nobody includes are treated as roots with an unknown prefix.
View methods are not known statically (class based views choose in `get()`/`post()`), so routes accept any method.
"""
import os
import re
from pathlib import Path

PATTERN_CALL_RE = re.compile(r"(?<![\w.])(?:re_path|path|url)\s*\(\s*")
STRING_RE = re.compile(r"""[rbu]*(['"])(.*?)(?<!\\)\1""", re.S)
ROOT_URLCONF_RE = re.compile(r"""ROOT_URLCONF\s*=\s*['"]([\w.]+)['"]""")
ROUTER_RE = re.compile(r"""(\w+)\s*=\s*(?:\w+\.)?(?:Default|Simple)Router\(([^)]*)\)""")
REGISTER_RE = re.compile(r"""(\w+)\.register\(\s*r?['"]([^'"]*)['"]\s*,\s*([\w.]+)""")
LOOKUP_FIELD_RE = re.compile(r"""lookup_field\s*=\s*['"](\w+)['"]""")
NAMED_GROUP_RE = re.compile(r"\(\?P<(\w+)>[^()]*(?:\([^()]*\)[^()]*)*\)")
PATH_CONVERTER_RE = re.compile(r"<(?:\w+:)?(\w+)>")
UNNAMED_GROUP_RE = re.compile(r"\((?!\?)[^()]*\)")


def regex_to_path(pattern: str) -> str:
    """`^articles/(?P<slug>[-\\w]+)/favorite/?$` -> `articles/{slug}/favorite`."""
    p = pattern.strip()
    p = re.sub(r"^\^", "", p)
    p = re.sub(r"(/\?)?(?:\$|\\Z)?$", "", p)        # trailing optional slash and end anchors
    p = NAMED_GROUP_RE.sub(lambda m: "{" + m.group(1) + "}", p)
    p = PATH_CONVERTER_RE.sub(lambda m: "{" + m.group(1) + "}", p)
    p = UNNAMED_GROUP_RE.sub("{}", p)
    p = p.replace("\\.", ".").replace("\\/", "/")
    return p.strip("/")


def _balanced(text: str, start: int) -> str:
    """Text from `start` (just after an opening paren) up to its matching closing paren."""
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


def parse_urlpatterns(text: str) -> list[dict]:
    """[{"pattern": str, "include": dotted module | "router:<var>" | None, "view": str, "line": int}]"""
    out = []
    for m in PATTERN_CALL_RE.finditer(text):
        if text[:m.start()].rstrip().endswith(("def", "import", "from")):
            continue
        args = _balanced(text, m.end())
        s = STRING_RE.match(args)
        if not s:
            continue
        rest = args[s.end():].lstrip()
        if not rest.startswith(","):
            continue
        target = rest[1:].strip()
        include = None
        inc = re.match(r"include\s*\(", target)
        if inc:
            body = _balanced(target, inc.end())
            mod = STRING_RE.search(body)
            router = re.search(r"(\w+)\.urls", body)
            if mod and body.lstrip().startswith(("'", '"', "(")) and "." in mod.group(2):
                include = mod.group(2)
            elif router:
                include = "router:" + router.group(1)
        view = re.match(r"[\w.]+", target)
        out.append({"pattern": s.group(2), "include": include,
                    "view": (view.group(0) if view and not include else ""), "line": text.count("\n", 0, m.start()) + 1})
    return out


def _module_file(files: dict, dotted: str) -> str | None:
    """Repo-relative path of the module `a.b.urls` (a/b/urls.py or a/b/urls/__init__.py), by path suffix."""
    tail = dotted.replace(".", "/")
    for rel in files:
        if rel.endswith(tail + ".py") or rel.endswith(tail + "/__init__.py"):
            return rel
    return None


LIST_ACTIONS = {"list": "GET", "create": "POST"}
DETAIL_ACTIONS = {"retrieve": "GET", "update": "PUT", "partial_update": "PATCH", "destroy": "DELETE"}
MIXIN_ACTIONS = {"ListModelMixin": "list", "CreateModelMixin": "create", "RetrieveModelMixin": "retrieve",
                 "UpdateModelMixin": ("update", "partial_update"), "DestroyModelMixin": "destroy"}


def _router_routes(text: str, repo_files: dict, read) -> dict:
    """{router var: [(prefix path, viewset class, viewset info)]} from `router.register()` calls."""
    routers = {m.group(1): m.group(2) for m in ROUTER_RE.finditer(text)}
    out = {}
    for var, prefix, viewset in REGISTER_RE.findall(text):
        if var in routers:
            name = viewset.split(".")[-1]
            out.setdefault(var, []).append((prefix.strip("/"), name, viewset_info(name, repo_files, read)))
    return out


def viewset_info(viewset: str, files: dict, read) -> dict:
    """{"lookup": field, "list": [methods], "detail": [methods]} from the class's bases, mixins and `def` actions.

    Empty method lists mean the class could not be read (unknown), not "no routes".
    """
    for rel in files:
        body = read(rel)
        m = re.search(r"class\s+" + re.escape(viewset) + r"\s*\((.*?)\)\s*:\s*\n(.*?)(?=\nclass\s|\Z)", body, re.S)
        if not m:
            continue
        bases, block = m.group(1), m.group(2)
        found = LOOKUP_FIELD_RE.search(block)
        actions = set()
        if re.search(r"\bModelViewSet\b", bases):
            actions = set(LIST_ACTIONS) | set(DETAIL_ACTIONS)
        elif re.search(r"\bReadOnlyModelViewSet\b", bases):
            actions = {"list", "retrieve"}
        for mixin, acts in MIXIN_ACTIONS.items():
            if re.search(r"\b" + mixin + r"\b", bases):
                actions.update((acts,) if isinstance(acts, str) else acts)
        actions.update(a for a in re.findall(r"\n\s+def\s+(\w+)\s*\(self", block) if a in LIST_ACTIONS or a in DETAIL_ACTIONS)
        return {"lookup": found.group(1) if found else "pk",
                "list": sorted(LIST_ACTIONS[a] for a in actions if a in LIST_ACTIONS),
                "detail": sorted({DETAIL_ACTIONS[a] for a in actions if a in DETAIL_ACTIONS}
                                 | ({"PATCH"} if "update" in actions else set()))}
    return {"lookup": "pk", "list": [], "detail": []}


def strip_non_code(text: str) -> str:
    """Blank out docstrings and whole-line comments (keeping line numbers) so examples in them are not parsed."""
    text = re.sub(r'(?s)("""|\'\'\').*?\1', lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return "\n".join("" if line.lstrip().startswith("#") else line for line in text.split("\n"))


def collect(repo: Path, read) -> list[dict]:
    """Routes as dicts {path, method, file, line, view, known}. `read(rel)` returns a repo-relative file's text."""
    files = {}
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in {"node_modules", "venv", ".venv", "env", "__pycache__", "migrations", "site-packages"} and not d.startswith(".")]
        for n in names:
            if n.endswith(".py"):
                files[(Path(root) / n).relative_to(repo).as_posix()] = None
    url_files = {rel for rel in files if Path(rel).name == "urls.py" or Path(rel).parent.name == "urls"}
    code = lambda rel: strip_non_code(read(rel))  # noqa: E731
    url_files = {rel for rel in url_files if "urlpatterns" in code(rel)}
    if not url_files:
        return []
    parsed = {rel: parse_urlpatterns(code(rel)) for rel in url_files}
    included = {t for rel, entries in parsed.items() for e in entries if e["include"] and not e["include"].startswith("router:")
                for t in [_module_file(files, e["include"])] if t}
    root_conf = next((m.group(1) for rel in files if Path(rel).name in {"settings.py", "base.py", "common.py"} or "settings" in Path(rel).parts
                      for m in ROOT_URLCONF_RE.finditer(read(rel))), None)
    root_file = _module_file(files, root_conf) if root_conf else None
    roots = [root_file] if root_file in url_files else sorted(url_files - included)
    out = []

    def emit(path: str, rel: str, line: int, view: str, known: bool, methods):
        for method in methods or [None]:  # None = any method (class based views choose in get()/post())
            out.append({"path": "/" + path, "file": rel, "line": line, "view": view, "known": known, "method": method})

    def walk(rel: str, prefix: str, known: bool, seen: tuple):
        routers = _router_routes(code(rel), files, code)
        for e in parsed[rel]:
            here = "/".join(x for x in (prefix, regex_to_path(e["pattern"])) if x)
            if e["include"] and e["include"].startswith("router:"):
                for p, viewset, info in routers.get(e["include"][7:], []):
                    emit("/".join(x for x in (here, p) if x), rel, e["line"], viewset + " (list)", known, info["list"])
                    emit("/".join(x for x in (here, p, "{" + info["lookup"] + "}") if x), rel, e["line"], viewset + " (detail)", known, info["detail"])
            elif e["include"]:
                target = _module_file(files, e["include"])
                if target in parsed and target not in seen:
                    walk(target, here, known, seen + (target,))
            else:
                emit(here, rel, e["line"], e["view"], known, None)

    for r in roots:
        walk(r, "", known=(r == root_file) or len(roots) == 1, seen=(r,))
    return out
