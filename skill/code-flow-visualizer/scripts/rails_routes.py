"""Rails routes: a small interpreter for the `config/routes.rb` DSL.

Understands `namespace`, `scope`, `resources`, `resource` (with `only`, `except`, `param`, `path`), nested resources,
`member`/`collection` blocks, `on: :member|:collection`, verb lines (`get 'x', to: 'c#a'`, `post 'x' => 'c#a'`),
`match ... via:`, `root`, `mount` and, approximately, `devise_for`. Unknown blocks pass their prefix through.
It does not run Ruby: conditionals, loops, concerns and `draw(...)` of other files are not followed.
"""
import re
from pathlib import Path

VERBS = ("get", "post", "put", "patch", "delete")
BLOCK_KEYWORDS = ("if", "unless", "case", "while", "until", "begin", "def", "class", "module", "for")
RESOURCE_ACTIONS = [  # (action, verbs, suffix kind)
    ("index", ["GET"], "collection"), ("create", ["POST"], "collection"), ("new", ["GET"], "new"),
    ("show", ["GET"], "member"), ("edit", ["GET"], "edit"), ("update", ["PUT", "PATCH"], "member"), ("destroy", ["DELETE"], "member"),
]
SINGULAR_ACTIONS = [
    ("create", ["POST"], ""), ("new", ["GET"], "new"), ("show", ["GET"], ""), ("edit", ["GET"], "edit"),
    ("update", ["PUT", "PATCH"], ""), ("destroy", ["DELETE"], ""),
]
STATEMENT_RE = re.compile(r"^(?P<word>[a-z_]+)\b\s*\(?\s*(?P<rest>.*?)\)?\s*(?P<do>\bdo\b(?:\s*\|[^|]*\|)?)?\s*$")


def singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("sses", "xes", "ches", "shes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def strip_comment(line: str) -> str:
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "#":
            return line[:i]
    return line


def statements(text: str):
    """Yield (line number, statement text) with continuation lines joined and comments removed."""
    buf, start, depth = "", 0, 0
    for n, raw in enumerate(text.split("\n"), 1):
        line = strip_comment(raw).strip()
        if not line and not buf:
            continue
        if not buf:
            start = n
        buf = (buf + " " + line).strip()
        depth = sum(buf.count(c) for c in "([{") - sum(buf.count(c) for c in ")]}")
        if buf.endswith((",", "\\")) or depth > 0:
            continue
        yield start, buf
        buf = ""
    if buf:
        yield start, buf


def symbols(text: str) -> list[str]:
    """Names in `:a, :b` / `'a'` / `[:a, :b]` (not option values after `key:`)."""
    return [m for m in re.findall(r"(?<![\w:])(?::(\w+)|['\"]([^'\"]+)['\"])", text) for m in [m[0] or m[1]] if m]


def option(text: str, key: str):
    """The raw value after `key:` or `:key =>` up to the next top-level comma."""
    m = re.search(r"(?:\b" + key + r":|:" + key + r"\s*=>)\s*(\[[^\]]*\]|\{[^}]*\}|[^,]+)", text)
    return m.group(1).strip() if m else None


def option_symbols(text: str, key: str):
    raw = option(text, key)
    return None if raw is None else [s for s in re.findall(r"[:'\"]?(\w+)['\"]?", raw)]


def head_names(rest: str) -> list[str]:
    """Resource names before the first option: `:a, :b, only: [...]` -> [a, b]."""
    names = []
    for part in re.split(r",\s*", rest):
        m = re.match(r"^(?::(\w+)|['\"]([^'\"]+)['\"])\s*$", part.strip())
        if not m:
            break
        names.append(m.group(1) or m.group(2))
    return names


def join(*parts: str) -> str:
    return "/" + "/".join(p.strip("/") for p in parts if p and p.strip("/"))


def param_segment(name: str) -> str:
    return "{" + name + "}"


def collect(repo: Path, read) -> list[dict]:
    files = [rel for rel in ("config/routes.rb",) if (repo / rel).is_file()]
    files += sorted(p.relative_to(repo).as_posix() for p in (repo / "config" / "routes").glob("*.rb")) if (repo / "config" / "routes").is_dir() else []
    app_conf = (repo / "config" / "application.rb")
    api_only = app_conf.is_file() and re.search(r"config\.api_only\s*=\s*true", read("config/application.rb")) is not None
    out: list[dict] = []
    for rel in files:
        out.extend(_interpret(rel, read(rel), api_only))
    return out


def _interpret(rel: str, text: str, api_only: bool) -> list[dict]:
    out: list[dict] = []
    # stack entries: {"kind", "path" (prefix for children), "member" (path of one record), "collection", "param_name"}
    root = {"kind": "root", "path": "", "member": "", "collection": "", "singular": ""}
    stack = [root]

    def emit(methods, path, line, view):
        for m in methods:
            out.append({"method": m, "path": path, "file": rel, "line": line, "view": view, "known": True})

    def actions_for(table, rest):
        only, except_ = option_symbols(rest, "only"), option_symbols(rest, "except")
        for action, verbs, suffix in table:
            if only is not None and action not in only:
                continue
            if except_ is not None and action in except_:
                continue
            if api_only and suffix in ("new", "edit"):
                continue
            yield action, verbs, suffix

    for line, st in statements(text):
        top = stack[-1]
        if st == "end":
            if len(stack) > 1:
                stack.pop()
            continue
        m = STATEMENT_RE.match(st)
        if not m:
            continue
        word, rest, opens = m.group("word"), m.group("rest"), bool(m.group("do"))
        if word == "devise_for" and not opens:
            names = head_names(rest)
            sign_in = (re.search(r"sign_in:\s*:?['\"]?(\w+)", rest) or [None, "sign_in"])[1]
            sign_out = (re.search(r"sign_out:\s*:?['\"]?(\w+)", rest) or [None, "sign_out"])[1]
            for n in names:
                base = join(top["path"], option(rest, "path").strip(":'\" ") if option(rest, "path") else n)
                emit(["POST"], join(base, sign_in), line, "devise sessions (assumed)")
                emit(["DELETE"], join(base, sign_out), line, "devise sessions (assumed)")
                emit(["POST"], base, line, "devise registrations (assumed)")
            continue
        if word in ("namespace", "scope"):
            path_opt = option(rest, "path")
            first = re.match(r"^(?::(\w+)|['\"]([^'\"]*)['\"])", rest.strip())  # `scope :api`, `namespace 'v1'`; not `scope module: :x`
            seg = path_opt.strip(":'\" ") if path_opt else ((first.group(1) or first.group(2)) if first else "")
            if opens:
                stack.append({**top, "kind": word, "path": join(top["path"], seg)})
            continue
        if word in BLOCK_KEYWORDS:  # plain Ruby blocks (if/unless/case/...) also end with `end`
            stack.append({**top, "kind": "other"})
            continue
        if word in ("resources", "resource"):
            names = head_names(rest)
            custom = option(rest, "path")
            if not opens:
                for n in names:
                    seg = custom.strip(":'\" ") if custom else n
                    _emit_resource(word, n, seg, rest, top, line, emit, actions_for, None)
            else:
                n = names[0] if names else ""
                seg = custom.strip(":'\" ") if custom else n
                ctx = _emit_resource(word, n, seg, rest, top, line, emit, actions_for, True)
                stack.append(ctx)
            continue
        if word in ("member", "collection") and opens:
            owner = next((s for s in reversed(stack) if s["kind"] == "resource"), None)
            if owner:
                stack.append({**top, "kind": word, "path": owner["member"] if word == "member" else owner["collection"]})
            else:
                stack.append({**top, "kind": "other"})
            continue
        if word in VERBS or word == "match":
            _emit_verb(word, rest, top, stack, line, emit)
            if opens:
                stack.append({**top, "kind": "other"})
            continue
        if word == "root":
            emit(["GET"], join(top["path"]), line, rest.split("to:")[-1].strip(" '\"") or "root")
            continue
        if word == "mount":
            target = re.search(r"=>\s*['\"]([^'\"]+)['\"]", rest) or re.search(r"at:\s*['\"]([^'\"]+)['\"]", rest)
            if target:
                emit([None], join(top["path"], target.group(1)), line, "mount")
            continue
        if opens:  # constraints, defaults, concern, authenticate ...: transparent for the prefix
            stack.append({**top, "kind": "other"})
    return out


def _emit_resource(word, name, seg, rest, top, line, emit, actions_for, opens):
    """Emit the routes of one resource and return the context for its nested block."""
    plural = word == "resources"
    owner = next((s for s in reversed([top]) if s["kind"] == "resource"), None)
    base = join(top["path"], seg)
    param = (option(rest, "param") or "id").strip(":'\" ")
    if plural:
        member_param = param_segment(param)
        for action, verbs, suffix in actions_for(RESOURCE_ACTIONS, rest):
            path = {"collection": base, "new": join(base, "new"), "member": join(base, member_param), "edit": join(base, member_param, "edit")}[suffix]
            emit(verbs, path, line, f"{name}#{action}")
        member = join(base, member_param)                                  # the record's own routes: /articles/{slug}/publish
        nested = join(base, param_segment(f"{singular(name)}_{param}"))   # its children: /articles/{article_slug}/comments
        collection = base
    else:
        for action, verbs, suffix in actions_for(SINGULAR_ACTIONS, rest):
            emit(verbs, join(base, suffix) if suffix else base, line, f"{name}#{action}")
        member = collection = nested = base
    return {"kind": "resource", "path": nested, "member": member, "collection": collection, "singular": singular(name)}


def _emit_verb(word, rest, top, stack, line, emit):
    methods = [word.upper()] if word in VERBS else [v.upper() for v in (option_symbols(rest, "via") or []) if v.lower() in VERBS or v == "all"] or [None]
    if methods == ["ALL"]:
        methods = [None]
    first = rest.split(",")[0].strip()
    m = re.match(r"^(?::(\w+)|['\"]([^'\"]*)['\"])", first)
    on = (option(rest, "on") or "").strip(":'\" ")
    if not m:
        arrow = re.match(r"^['\"]([^'\"]+)['\"]\s*=>", rest)
        if not arrow:
            return
        path_text = arrow.group(1)
    else:
        path_text = m.group(1) or m.group(2)
    path_text = re.sub(r":(\w+)", lambda x: "{" + x.group(1) + "}", path_text)
    owner = next((s for s in reversed(stack) if s["kind"] == "resource"), None)
    if on and owner:
        base = owner["member"] if on == "member" else owner["collection"]
    else:
        base = top["path"]
    emit(methods, join(base, path_text), line, (re.search(r"to:\s*['\"]([^'\"]+)", rest) or [None, path_text])[1])
