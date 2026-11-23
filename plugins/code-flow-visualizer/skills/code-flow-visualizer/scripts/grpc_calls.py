"""gRPC calls a frontend makes through generated clients (grpc-web, Connect/Buf), as HTTP calls.

`const client = new GreeterClient(host)` / `createPromiseClient(GreeterService, transport)` followed by `client.sayHello(...)` is
read as `POST /<package>.Greeter/SayHello` (the path gRPC-Web and Connect send). The package comes from `.proto` files or generated
code in the frontend repo; when unknown the URL uses `/{}.Greeter/SayHello`, which the matcher treats as a partial parameter.
A file is only read when it imports generated gRPC code, so `new ApolloClient()` or `new S3Client()` are not mistaken for services.
"""
import re

GRPC_IMPORT_RE = re.compile(r"_grpc_web_pb|ServiceClientPb|_pb['\"]|grpc-web|@grpc/|@connectrpc|@bufbuild|connect-web|_connect['\"]|nice-grpc|grpc-js")
NEW_CLIENT_RE = re.compile(r"(?:this\.)?(\w+)\s*(?::\s*[\w.<>]+\s*)?=\s*new\s+(?:[\w.]+\.)?(\w+?)(?:Promise)?Client\s*\(")
CONNECT_RE = re.compile(r"(?:this\.)?(\w+)\s*=\s*create(?:Promise)?Client\s*\(\s*([\w.]+)\s*,")
PROTO_PATH_RE = re.compile(r"""['"]/([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)*)\.(\w+)/(\w+)['"]""")
NOT_RPC = {"close", "on", "off", "once", "cancel", "end", "write", "setOptions", "withCredentials", "toString", "constructor",
           "then", "catch", "finally", "emit", "removeListener", "addListener", "getHostname", "hostname"}


def detect_packages(files) -> dict:
    """{service name: package} from `.proto` files and generated paths such as '/helloworld.Greeter/SayHello'.

    `files` yields (relative path, text).
    """
    packages = {}
    for rel, text in files:
        if rel.endswith(".proto"):
            import grpc_routes  # local import: only needed when protos exist
            for r in grpc_routes.parse_proto(text):
                packages.setdefault(r["service"], r["package"])
        else:
            for m in PROTO_PATH_RE.finditer(text):
                packages.setdefault(m.group(2), m.group(1))
    return packages


def find(text: str, rel: str, packages: dict) -> list[dict]:
    if not GRPC_IMPORT_RE.search(text):
        return []
    clients = {}  # variable -> service
    for m in NEW_CLIENT_RE.finditer(text):
        clients[m.group(1)] = m.group(2)
    for m in CONNECT_RE.finditer(text):
        service = m.group(2).split(".")[-1]
        clients[m.group(1)] = service[:-len("Service")] if service.endswith("Service") and len(service) > 7 else service
    calls = []
    for var, service in clients.items():
        pattern = re.compile(r"(?<![\w$])(?:this\.)?" + re.escape(var) + r"\s*\.\s*(\w+)\s*\(")
        for m in pattern.finditer(text):
            method = m.group(1)
            if method in NOT_RPC:
                continue
            rpc = method[0].upper() + method[1:]
            package = packages.get(service)
            url = "/" + (package if package else "{}") + f".{service}/{rpc}"
            calls.append({"file": rel, "line": text.count("\n", 0, m.start()) + 1, "callee": f"{service}Client.{method}", "methods": ["POST"],
                          "url": url, "dynamic": not package, "base_unknown": False, "optional_suffix": False, "unresolved": False})
    return calls
