"""GraphQL backends: the operations a server exposes, as routes.

Every field of the root `Query`, `Mutation` and `Subscription` types becomes a route with method QUERY / MUTATION /
SUBSCRIPTION and path `<endpoint>/<field>` (endpoint `/graphql` unless the server config says otherwise). The route points at
the field's resolver when one is found, otherwise at the field in the schema.

Schemas are read from `.graphql` / `.gql` / `.graphqls` files and from `gql` / `#graphql` template strings and similar
embedded SDL in source files. Resolvers are found in resolver maps (`Query: { launches: ... }`), NestJS (`@Query()`),
Spring for GraphQL (`@QueryMapping`) and HotChocolate-style `Query` / `Mutation` classes.
"""
import os
import re
from pathlib import Path

SOURCE_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".py", ".java", ".kt", ".cs", ".rb", ".go", ".php", ".scala"}
SDL_EXTS = {".graphql", ".gql", ".graphqls"}
SKIP = {"node_modules", "dist", "build", "target", "bin", "obj", "venv", ".venv", "__pycache__", "coverage", ".next", "__generated__", "generated"}
KINDS = {"query": "QUERY", "mutation": "MUTATION", "subscription": "SUBSCRIPTION"}

TYPE_BLOCK_RE = re.compile(r"(?<![\w.])(?:extend\s+)?type\s+(\w+)\s*(?:implements\s+[^{]*)?\{")
SCHEMA_BLOCK_RE = re.compile(r"(?<![\w.])schema\s*(?:@[^{]*)?\{([^}]*)\}")
ROOT_ENTRY_RE = re.compile(r"(query|mutation|subscription)\s*:\s*(\w+)")
ENDPOINT_PATTERNS = (
    re.compile(r"""\bpath\s*:\s*['"](/[^'"]*)['"]"""),                       # applyMiddleware({ path }), GraphQLModule.forRoot({ path })
    re.compile(r"""\buse\(\s*['"](/[^'"]*graphql[^'"]*)['"]""", re.I),       # app.use('/graphql', graphqlHTTP(...))
    re.compile(r"""spring\.graphql\.path\s*[=:]\s*(/\S+)"""),                # application.properties
    re.compile(r"""MapGraphQL\(\s*"(/[^"]*)"\s*\)"""),                       # ASP.NET HotChocolate
)


def join(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def blank_non_sdl(text: str) -> str:
    """Replace comments, descriptions and field arguments with spaces (newlines kept), leaving `name: Type` lines."""
    text = re.sub(r'(?s)"""(.*?)"""', lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    text = re.sub(r'"[^"\n]*"', lambda m: " " * len(m.group(0)), text)
    text = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), text)
    out, depth = [], 0
    for c in text:                                   # field arguments `launches(pageSize: Int, after: String)`
        if c == "(":
            depth += 1
            out.append(" ")
        elif c == ")":
            depth = max(0, depth - 1)
            out.append(" ")
        else:
            out.append(c if depth == 0 or c == "\n" else " ")
    return "".join(out)


def block_end(text: str, open_brace: int) -> int:
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def schema_fields(text: str) -> list[tuple[str, str, int]]:
    """[(kind, field, line offset)] for the root types declared in one SDL text."""
    clean = blank_non_sdl(text)
    declared = {name: kind for sm in SCHEMA_BLOCK_RE.finditer(clean) for kind, name in ROOT_ENTRY_RE.findall(sm.group(1))}
    roots = declared or {"Query": "query", "Mutation": "mutation", "Subscription": "subscription"}   # a schema block replaces the defaults
    out = []
    for m in TYPE_BLOCK_RE.finditer(clean):
        kind = roots.get(m.group(1))
        if not kind:
            continue
        body_start, body_end = m.end(), block_end(clean, m.end() - 1)
        for fm in re.finditer(r"(\w+)\s*:", clean[body_start:body_end]):   # arguments and descriptions are blanked, so only `field:` remains; fields may share a line
            line_offset = clean.count("\n", 0, body_start + fm.start(1))
            out.append((kind, fm.group(1), line_offset))
    return out


def embedded_sdl(text: str):
    """Yield (sdl text, line of its first character) for GraphQL documents embedded in source code."""
    for m in re.finditer(r"(?:gql|graphql|typeDefs)\s*(?:\(\s*)?`([^`]*)`|`\s*#graphql([^`]*)`|/\*\s*GraphQL\s*\*/\s*`([^`]*)`", text):
        body = m.group(1) or m.group(2) or m.group(3) or ""
        start = m.start(1) if m.group(1) is not None else (m.start(2) if m.group(2) is not None else m.start(3))
        yield body, text.count("\n", 0, start)
    # Python / Java / Kotlin / C# text blocks that contain a root type
    for m in re.finditer(r'(?s)(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', text):
        if re.search(r"\btype\s+(Query|Mutation|Subscription)\s*\{", m.group(1)):
            yield m.group(1), text.count("\n", 0, m.start(1))


def collect(repo: Path, read) -> list[dict]:
    schema_fields_found = []   # (kind, field, file, line)
    sources = {}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for n in files:
            p = Path(root) / n
            ext = p.suffix.lower()
            rel = p.relative_to(repo).as_posix()
            if ext in SDL_EXTS:
                for kind, field, off in schema_fields(read(rel)):
                    schema_fields_found.append((kind, field, rel, off + 1))
            elif ext in SOURCE_EXTS and not n.endswith((".d.ts", ".spec.ts", ".test.ts", ".test.js", ".spec.js")):
                text = read(rel)
                sources[rel] = text
                if "type" in text and re.search(r"\btype\s+\w+\s*(?:implements[^{]*)?\{", text):
                    for body, first_line in embedded_sdl(text):
                        for kind, field, off in schema_fields(body):
                            schema_fields_found.append((kind, field, rel, first_line + off + 1))
    resolvers = find_resolvers(sources)
    endpoint = detect_endpoint(sources, repo)
    seen, out = set(), []
    for kind, field, rel, line in schema_fields_found:
        key = (kind, field)
        if key in seen:
            continue  # the same field declared twice (extend type): report once
        seen.add(key)
        where = resolvers.get(key)
        out.append({"method": KINDS[kind], "path": join(endpoint, field), "file": where[0] if where else rel,
                    "line": where[1] if where else line, "view": f"{kind.capitalize()}.{field}" + ("" if where else " (schema)"),
                    "known": True})
    return out


def detect_endpoint(sources: dict, repo: Path) -> str:
    texts = list(sources.values())
    for name in ("application.properties", "application.yml", "application.yaml"):
        for p in repo.rglob(name):
            if "node_modules" not in p.parts:
                texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    for text in texts:
        if not re.search(r"graphql|ApolloServer|GraphQLModule", text, re.I):
            continue
        for pattern in ENDPOINT_PATTERNS:
            m = pattern.search(text)
            if m and "graphql" in m.group(1).lower():
                return m.group(1)
    return "/graphql"


RESOLVER_BLOCK_RE = re.compile(r"\b(Query|Mutation|Subscription)\s*:\s*\{")
KEY_RE = re.compile(r"^[ \t]*(?:async\s+)?(\w+)[ \t]*(?::|\()", re.M)
DECORATOR_RE = re.compile(r"@(Query|Mutation|Subscription|QueryMapping|MutationMapping|SubscriptionMapping)\b")
AFTER_DECORATOR_RE = re.compile(
    r"\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:(?:public|protected|private|async|static|override)\s+)*(?:[\w<>\[\],.? ]+?\s+)?(\w+)\s*\(")


def balanced_args(text: str, pos: int):
    """(arguments text, end) when `text[pos]` is `(`; else ("", pos)."""
    if pos >= len(text) or text[pos] != "(":
        return "", pos
    depth, i = 0, pos
    while i < len(text):
        depth += text[i] == "("
        depth -= text[i] == ")"
        if depth == 0:
            return text[pos + 1:i], i + 1
        i += 1
    return text[pos + 1:], len(text)


def find_resolvers(sources: dict) -> dict:
    """{(kind, field): (file, line)} from resolver maps, NestJS/Spring decorators and Query/Mutation classes."""
    found = {}
    for rel, text in sources.items():
        for m in RESOLVER_BLOCK_RE.finditer(text):               # resolvers = { Query: { launches: ..., me() {...} } }
            kind = m.group(1).lower()
            end = block_end(text, m.end() - 1)
            body = text[m.end():end]
            depth0 = _depth_zero(body)
            for km in KEY_RE.finditer(depth0):
                name = km.group(1)
                if name not in ("async", "function", "return", "if", "for"):
                    found.setdefault((kind, name), (rel, text.count("\n", 0, m.end() + km.start(1)) + 1))
        for m in DECORATOR_RE.finditer(text):                    # @Query(() => [L]) launches(), @QueryMapping public X launches(
            kind = m.group(1).replace("Mapping", "").lower()
            args, end = balanced_args(text, m.end())
            after = AFTER_DECORATOR_RE.match(text, end)
            if not after:
                continue
            named = re.search(r"""(?:name\s*[:=]\s*)?['"](\w+)['"]""", args)
            field = named.group(1) if named else after.group(1)
            found.setdefault((kind, field), (rel, text.count("\n", 0, after.start(1)) + 1))
        for cm in re.finditer(r"\bclass\s+(Query|Mutation|Subscription)\b[^{]*\{", text):   # HotChocolate: class Query { public ... Launches() }
            kind = cm.group(1).lower()
            end = block_end(text, cm.end() - 1)
            for mm in re.finditer(r"public\s+(?:async\s+)?[\w<>\[\],.? ]+?\s+(\w+)\s*\(", text[cm.end():end]):
                name = mm.group(1)
                found.setdefault((kind, name[0].lower() + name[1:]), (rel, text.count("\n", 0, cm.end() + mm.start(1)) + 1))
    return found


def _depth_zero(body: str) -> str:
    """Body with every nested {...} / (...) replaced by spaces (newlines kept): leaves only top-level keys."""
    out, depth = [], 0
    for c in body:
        if c in "{(":
            depth += 1
            out.append(" ")
        elif c in "})":
            depth = max(0, depth - 1)
            out.append(" ")
        else:
            out.append(c if depth == 0 or c == "\n" else " ")
    return "".join(out)
