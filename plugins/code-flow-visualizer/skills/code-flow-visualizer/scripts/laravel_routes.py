"""Laravel routes: `routes/*.php` with groups, prefixes and resource routes.

Understands `Route::get/post/put/patch/delete/options/any`, `Route::match([...], ...)`, `Route::resource` and
`apiResource` (options array or `->only()` / `->except()`), and groups in both forms:
`Route::group(['prefix' => 'v1'], function () {...})` and `Route::prefix('v1')->middleware(...)->group(function () {...})`.
The prefix of a route file comes from where it is loaded: `RouteServiceProvider` (`Route::prefix('api')->group(base_path(
'routes/api.php'))`) or `bootstrap/app.php` (`apiPrefix:`), with Laravel's defaults (`api` for routes/api.php, none for
web.php) when neither says otherwise.
"""
import re
from pathlib import Path

HTTP_VERBS = ("get", "post", "put", "patch", "delete", "options", "any")
ROUTE_CALL_RE = re.compile(r"Route::(get|post|put|patch|delete|options|any)\s*\(\s*(['\"])([^'\"]*)\2")
MATCH_RE = re.compile(r"Route::match\s*\(\s*\[([^\]]*)\]\s*,\s*(['\"])([^'\"]*)\2")
RESOURCE_RE = re.compile(r"Route::(resource|apiResource)\s*\(\s*(['\"])([^'\"]*)\2")
GROUP_RE = re.compile(r"Route::((?:\s*\w+\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*->)*)\s*group\s*\(|Route::group\s*\(")
CHAIN_PREFIX_RE = re.compile(r"\bprefix\s*\(\s*['\"]([^'\"]*)['\"]\s*\)")
ARRAY_PREFIX_RE = re.compile(r"['\"]prefix['\"]\s*=>\s*['\"]([^'\"]*)['\"]")
PROVIDER_GROUP_RE = re.compile(
    r"Route::((?:\s*\w+\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*->)*)\s*group\s*\(\s*base_path\s*\(\s*['\"]routes/([\w.-]+\.php)['\"]\s*\)")
BOOTSTRAP_ROUTING_RE = re.compile(r"(\w+)\s*:\s*__DIR__\s*\.\s*['\"]/\.\./routes/([\w.-]+\.php)['\"]")
API_PREFIX_RE = re.compile(r"apiPrefix\s*:\s*['\"]([^'\"]*)['\"]")

RESOURCE_ACTIONS = [("index", ["GET"], ""), ("create", ["GET"], "create"), ("store", ["POST"], ""), ("show", ["GET"], "{p}"),
                    ("edit", ["GET"], "{p}/edit"), ("update", ["PUT", "PATCH"], "{p}"), ("destroy", ["DELETE"], "{p}")]


def join(*parts: str) -> str:
    return "/" + "/".join(p.strip("/") for p in parts if p and p.strip("/"))


def singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def strip_comments(text: str) -> str:
    """Blank out /* */, // and # comments (keeping newlines) so examples in them are not read as routes."""
    text = re.sub(r"(?s)/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return re.sub(r"(?m)(?<![:'\"])(//|#(?!\[)).*$", "", text)


def balanced_block(text: str, open_pos: int):
    """(start, end) of the {...} block whose `{` is the first one at or after open_pos; None if there is none."""
    start = text.find("{", open_pos)
    if start < 0:
        return None
    depth, i, quote = 0, start, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i
        i += 1
    return start, len(text)


def group_ranges(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, prefix)] for every group closure in the file."""
    out = []
    for m in GROUP_RE.finditer(text):
        head_end = m.end()
        chain = m.group(1) or ""
        # prefix from the chain (`Route::prefix('x')->group(`) or from the array form (`Route::group(['prefix' => 'x'], ...`)
        window = text[m.start():m.end() + 200] if not chain else chain
        p = CHAIN_PREFIX_RE.search(chain) if chain else ARRAY_PREFIX_RE.search(text[head_end:head_end + 300].split("function")[0])
        block = balanced_block(text, head_end)
        if block:
            out.append((block[0], block[1], p.group(1) if p else ""))
    return out


def resource_selection(text: str, end: int) -> tuple[set | None, set | None]:
    """(only, except) from the third-argument array or the chained ->only([...]) / ->except([...])."""
    tail = text[end:end + 400]
    stop = tail.find(";")
    tail = tail[:stop] if stop >= 0 else tail
    only = re.search(r"(?:['\"]only['\"]\s*=>|->only\()\s*\[([^\]]*)\]", tail)
    exc = re.search(r"(?:['\"]except['\"]\s*=>|->except\()\s*\[([^\]]*)\]", tail)
    names = lambda m: set(re.findall(r"['\"](\w+)['\"]", m.group(1))) if m else None  # noqa: E731
    return names(only), names(exc)


def file_prefixes(repo: Path, read) -> dict:
    """{'routes/api.php': 'api', ...} from RouteServiceProvider / bootstrap/app.php, with Laravel's defaults."""
    prefixes = {}
    provider = repo / "app" / "Providers" / "RouteServiceProvider.php"
    if provider.is_file():
        for m in PROVIDER_GROUP_RE.finditer(strip_comments(read("app/Providers/RouteServiceProvider.php"))):
            p = CHAIN_PREFIX_RE.search(m.group(1) or "")
            prefixes["routes/" + m.group(2)] = p.group(1) if p else ""
    boot = repo / "bootstrap" / "app.php"
    if boot.is_file():
        text = strip_comments(read("bootstrap/app.php"))
        api_prefix = API_PREFIX_RE.search(text)
        for kind, name in BOOTSTRAP_ROUTING_RE.findall(text):
            if kind == "api":
                prefixes.setdefault("routes/" + name, api_prefix.group(1) if api_prefix else "api")
            elif kind == "web":
                prefixes.setdefault("routes/" + name, "")
    prefixes.setdefault("routes/api.php", "api")
    prefixes.setdefault("routes/web.php", "")
    return prefixes


def collect(repo: Path, read) -> list[dict]:
    routes_dir = repo / "routes"
    if not routes_dir.is_dir():
        return []
    prefixes = file_prefixes(repo, read)
    out = []
    for path in sorted(routes_dir.glob("*.php")):
        rel = path.relative_to(repo).as_posix()
        if rel not in prefixes:
            continue  # a route file nothing loads (or whose loader we could not read): not a known route set
        text = strip_comments(read(rel))
        groups = group_ranges(text)

        def prefix_at(pos: int) -> str:
            enclosing = sorted((g for g in groups if g[0] < pos < g[1]), key=lambda g: g[0])
            return join(prefixes[rel], *[g[2] for g in enclosing])

        def emit(methods, route_path, pos, view):
            line = text.count("\n", 0, pos) + 1
            full = join(prefix_at(pos), re.sub(r"\{(\w+)\?\}", r"{\1}", route_path))
            for method in methods:
                out.append({"method": method, "path": full, "file": rel, "line": line, "view": view, "known": True})

        for m in ROUTE_CALL_RE.finditer(text):
            verb = m.group(1)
            emit([None] if verb == "any" else [verb.upper()], m.group(3), m.start(), verb)
        for m in MATCH_RE.finditer(text):
            verbs = [v.upper() for v in re.findall(r"['\"](\w+)['\"]", m.group(1))]
            emit(verbs or [None], m.group(3), m.start(), "match")
        for m in RESOURCE_RE.finditer(text):
            kind, base = m.group(1), m.group(3).strip("/")
            only, except_ = resource_selection(text, m.end())
            last = base.split("/")[-1]
            param = "{" + singular(re.sub(r"\{|\}", "", last)) + "}"
            for action, verbs, suffix in RESOURCE_ACTIONS:
                if kind == "apiResource" and action in ("create", "edit"):
                    continue
                if (only is not None and action not in only) or (except_ is not None and action in except_):
                    continue
                emit(verbs, join(base, suffix.replace("{p}", param)) if suffix else base, m.start(), f"{kind}.{action}")
    return out
