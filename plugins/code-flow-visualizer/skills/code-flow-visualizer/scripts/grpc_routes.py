"""gRPC backends: every `rpc` of every `service` in the repo's `.proto` files, as a route.

Path is `/<package>.<Service>/<Method>` and method POST: the HTTP/2 path of native gRPC and the URL gRPC-Web and Connect clients
send. The route points at the method's implementation when one is found (an `addService(...)` handler map in Node, a
`...ImplBase` / `...Base` / `...Servicer` subclass in Java, C# and Python, a `func (s *server) Method` in Go), otherwise at the
`rpc` line of the `.proto`.
"""
import os
import re
from pathlib import Path

SOURCE_EXTS = {".js", ".mjs", ".cjs", ".ts", ".py", ".java", ".kt", ".cs", ".go", ".rb", ".php", ".scala", ".rs", ".cc", ".cpp"}
SKIP = {"node_modules", "dist", "build", "target", "bin", "obj", "venv", ".venv", "__pycache__", "vendor", "third_party"}
GENERATED = re.compile(r"(_pb\.js|_pb\.d\.ts|_pb2\.py|_pb2_grpc\.py|\.pb\.go|_grpc\.pb\.go|Grpc\.java|ServiceClientPb\.ts|_grpc_web_pb\.js|\.d\.ts|\.pb\.cc|\.pb\.h|_connect\.(?:js|ts))$")
PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
SERVICE_RE = re.compile(r"\bservice\s+(\w+)\s*\{")
RPC_RE = re.compile(r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?[\w.]+\s*\)\s*returns\s*\(\s*(stream\s+)?[\w.]+\s*\)")


def strip_comments(text: str) -> str:
    text = re.sub(r"(?s)/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), text)


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


def parse_proto(text: str) -> list[dict]:
    """[{"package", "service", "rpc", "line", "streaming"}] for one .proto file."""
    clean = strip_comments(text)
    pkg = PACKAGE_RE.search(clean)
    out = []
    for sm in SERVICE_RE.finditer(clean):
        end = block_end(clean, sm.end() - 1)
        for rm in RPC_RE.finditer(clean, sm.end(), end):
            kind = {(True, True): "bidirectional streaming", (False, True): "server streaming",
                    (True, False): "client streaming"}.get((bool(rm.group(2)), bool(rm.group(3))), "unary")
            out.append({"package": pkg.group(1) if pkg else "", "service": sm.group(1), "rpc": rm.group(1),
                        "line": clean.count("\n", 0, rm.start()) + 1, "streaming": kind})
    return out


def find_implementations(sources: dict, rpcs: list[dict]) -> dict:
    """{(service, rpc): (file, line)} for the first file that mentions the service and defines the method."""
    found = {}
    for rpc in rpcs:
        names = {rpc["rpc"], rpc["rpc"][0].lower() + rpc["rpc"][1:]}
        alt = "|".join(re.escape(n) for n in sorted(names))
        service_word = re.compile(re.escape(rpc["service"]))   # no word boundary: Java names it OrdersGrpc.OrdersImplBase
        definition = re.compile(
            r"(?m)(?<![\w.])(?:"
            r"(?:async\s+)?(?:function|def|func|fn)\s+(?:\([^)]*\)\s*)?(?:" + alt + r")\s*\("                       # function sayHello( / def SayHello( / func (s *srv) SayHello(
            r"|(?:public|protected|override|virtual|async|static|suspend)\b[^;{}()\n]*?\b(?:" + alt + r")\s*\("   # public override Task<R> SayHello(
            r"|(?:" + alt + r")\s*(?::|\([^)]*\)\s*\{)"                                                              # sayHello: handler,  sayHello(call, cb) {
            r")")
        for rel, text in sources.items():
            if not service_word.search(text):
                continue
            m = definition.search(text)
            if m:
                found[(rpc["service"], rpc["rpc"])] = (rel, text.count("\n", 0, m.start()) + 1)
                break
    return found


def collect(repo: Path, read) -> list[dict]:
    rpcs, files = [], []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for n in names:
            rel = (Path(root) / n).relative_to(repo).as_posix()
            if n.endswith(".proto"):
                for r in parse_proto(read(rel)):
                    rpcs.append({**r, "file": rel})
            elif Path(n).suffix.lower() in SOURCE_EXTS and not GENERATED.search(n):
                files.append(rel)
    if not rpcs:
        return []
    sources = {rel: strip_comments(read(rel)) for rel in files if re.search(r"grpc|Grpc|Servicer|ImplBase|addService|Register\w+Server|\.Base\b|Base\b", read(rel))}
    impl = find_implementations(sources, rpcs)
    out = []
    for r in rpcs:
        where = impl.get((r["service"], r["rpc"]))
        path = "/" + (f"{r['package']}." if r["package"] else "") + f"{r['service']}/{r['rpc']}"
        out.append({"method": "POST", "path": path, "file": where[0] if where else r["file"], "line": where[1] if where else r["line"],
                    "view": f"{r['service']}.{r['rpc']} ({r['streaming']})" + ("" if where else " (proto)"), "known": True})
    return out
