"""GraphQL operations a frontend sends, as calls.

Each root field of a query / mutation / subscription becomes one call with method QUERY / MUTATION / SUBSCRIPTION and
url `<endpoint>/<field>`, the same shape graphql_routes.py gives the server's fields, so the existing matcher, base URLs and
stitcher work unchanged. Operations are read from `gql` / `graphql` / `#graphql` template strings and from `.graphql` / `.gql` files;
`${Fragment}` interpolations, fragment spreads, aliases, variables and directives are handled.
"""
import re

DOC_RE = re.compile(r"(?:\bgql|\bgraphql)\s*(?:\(\s*)?`([^`]*)`|`\s*#graphql([^`]*)`|/\*\s*GraphQL\s*\*/\s*`([^`]*)`")
OPERATION_RE = re.compile(r"(?<![\w$])(query|mutation|subscription)\b\s*(\w*)\s*(?:\([^)]*\))?\s*(?:@\w+(?:\([^)]*\))?\s*)*\{")
CLIENT_HINT_RE = re.compile(r"ApolloClient|HttpLink|createHttpLink|GraphQLClient|urql|createClient|graphql-request|useQuery", re.I)
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]+", re.I)


def blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def erase_nested(text: str) -> str:
    """Keep only depth-0 text of a selection set: nested `{...}` and `(...)` become spaces (newlines kept)."""
    out, depth = [], 0
    for c in text:
        if c in "{(":
            depth += 1
            out.append(" ")
        elif c in "})":
            depth = max(0, depth - 1)
            out.append(" ")
        else:
            out.append(c if depth == 0 or c == "\n" else " ")
    return "".join(out)


def selection_end(text: str, open_brace: int) -> int:
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def root_fields(selection: str) -> list[str]:
    """Names of the fields at depth 0 of a selection set (aliases resolved, fragment spreads ignored)."""
    flat = erase_nested(selection)
    flat = re.sub(r"\.\.\.\s*\w*", " ", flat)          # `...LaunchTile`, `... on Type`
    names = []
    for m in re.finditer(r"(?:(\w+)\s*:\s*)?(\w+)((?:\s*@\w+)*)", flat):
        if m.group(2) == "on" or "@client" in m.group(3):   # @client fields are answered from the local cache, never sent
            continue
        names.append(m.group(2))
    return names


def find_in_document(doc: str, first_line: int):
    """Yield (kind, operation name, root field, line) for each operation in one GraphQL document."""
    doc = re.sub(r"\$\{[^}]*\}", lambda m: blank(m.group(0)), doc)    # `${LAUNCH_TILE_DATA}` fragment interpolation
    doc = re.sub(r"#[^\n]*", lambda m: blank(m.group(0)), doc)
    found = False
    for m in OPERATION_RE.finditer(doc):
        found = True
        start = m.end() - 1
        end = selection_end(doc, start)
        line = first_line + doc.count("\n", 0, m.start(1))
        for field in root_fields(doc[start + 1:end]):
            yield m.group(1), m.group(2), field, line
    stripped = doc.lstrip()
    if not found and stripped.startswith("{"):                          # shorthand `{ launches { id } }` is a query
        start = doc.index("{")
        for field in root_fields(doc[start + 1:selection_end(doc, start)]):
            yield "query", "", field, first_line + doc.count("\n", 0, start)


def find(text: str, rel: str, endpoint: str = "/graphql") -> list[dict]:
    """Calls for every GraphQL operation in a source file (templates) or a .graphql / .gql file (whole file)."""
    docs = []
    if rel.endswith((".graphql", ".gql")):
        docs.append((text, 0))
    else:
        if "gql" not in text and "graphql" not in text.lower() and "#graphql" not in text:
            return []
        for m in DOC_RE.finditer(text):
            idx = 1 if m.group(1) is not None else (2 if m.group(2) is not None else 3)
            docs.append((m.group(idx), text.count("\n", 0, m.start(idx))))
    calls = []
    for doc, first_line in docs:
        for kind, name, field, line in find_in_document(doc, first_line):
            calls.append({"file": rel, "line": line + 1, "callee": f"{kind} {name}".strip(), "methods": [kind.upper()],
                          "url": "/" + "/".join(s for s in (endpoint.strip("/"), field) if s), "dynamic": False,
                          "base_unknown": False, "optional_suffix": False, "unresolved": False})
    return calls


CLIENT_CALL_RE = re.compile(r"(?:new\s+ApolloClient|new\s+HttpLink|createHttpLink|new\s+GraphQLClient|createClient|new\s+ApolloLink)\s*\(")
URI_RE = re.compile(r"""\b(?:uri|url)\s*:\s*['"`]([^'"`$\s]+)['"`]|^\s*['"`]([^'"`$\s]+)['"`]""")


def detect_endpoint(texts) -> str:
    """The client's GraphQL endpoint path, read only from the arguments of a GraphQL client constructor; else /graphql."""
    for text in texts:
        if not CLIENT_HINT_RE.search(text):
            continue
        for call in CLIENT_CALL_RE.finditer(text):
            window = text[call.end():call.end() + 300]
            m = URI_RE.search(window)
            if m:
                path = SCHEME_RE.sub("", m.group(1) or m.group(2)).split("?", 1)[0]
                if path.strip("/"):
                    return "/" + path.strip("/")
    return "/graphql"
