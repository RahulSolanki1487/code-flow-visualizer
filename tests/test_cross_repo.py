"""Tests for frontend <-> backend linking: API call finder, route table, matcher, multi-repo roots."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))

import find_api_calls  # noqa: E402
import match_api  # noqa: E402
import render_page  # noqa: E402
import repo_roots  # noqa: E402
import route_table  # noqa: E402
import split_flow  # noqa: E402
import validate_flow  # noqa: E402


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def calls(tmp_path, source: str, name="src/api.ts"):
    write(tmp_path, name, source)
    return find_api_calls.scan(tmp_path)


# ---- find_api_calls ------------------------------------------------------

def test_method_comes_from_the_calls_own_options_not_the_next_call(tmp_path):
    found = calls(tmp_path, "fetch('/v1/items');\nfetch(`/v1/items/${id}`, { method: 'DELETE' });\n", "a.js")
    assert [(c["methods"], c["url"]) for c in found] == [(["GET"], "/v1/items"), (["DELETE"], "/v1/items/{}")]


def test_runtime_verb_and_optional_suffix(tmp_path):
    found = calls(tmp_path, "await fetch('/v1/items' + (item.id ? '/' + item.id : ''), {\n method: (item.id) ? 'PUT' : 'POST',\n});\n", "a.js")
    assert found[0]["methods"] == ["POST", "PUT"] and found[0]["url"] == "/v1/items" and found[0]["optional_suffix"]


def test_typescript_generics_and_angular_http(tmp_path):
    found = calls(tmp_path,
                  "apiFetch<Foo[]>(`/api/v1/x/${id}?${qs}`);\n"
                  "this.http.post<{ token: string }>('/api/login', { email });\n"
                  "axios.delete('/api/v1/y/' + id);\n")
    assert [(c["methods"], c["url"]) for c in found] == [(["GET"], "/api/v1/x/{}"), (["POST"], "/api/login"), (["DELETE"], "/api/v1/y/{}")]


def test_constants_are_inlined_including_chained_ones(tmp_path):
    found = calls(tmp_path,
                  'const IDENTITY = "/api/v1/identity";\nconst BASE = `${IDENTITY}/sessions`;\n'
                  "apiFetch(`${BASE}/me`);\napiFetch(`${BASE}/${id}`, { method: 'DELETE' });\n")
    assert [(c["methods"], c["url"]) for c in found] == [(["GET"], "/api/v1/identity/sessions/me"), (["DELETE"], "/api/v1/identity/sessions/{}")]


def test_definitions_tests_and_external_urls(tmp_path):
    write(tmp_path, "src/client.ts", "export async function apiFetch<T>(url: string) { return fetch(url); }\n")
    write(tmp_path, "src/x.test.ts", "fetch('/api/in-test');\n")
    found = find_api_calls.scan(tmp_path)
    assert [c["url"] for c in found] == [None] and found[0]["unresolved"]  # fetch(url): a variable, not a literal
    assert all("in-test" not in (c["url"] or "") for c in found)
    assert find_api_calls.find_calls_in_text("fetch('https://api.example.com/v1/q?a=1');", "a.js")[0]["url"] == "/v1/q"


def test_base_url_variable_is_flagged(tmp_path):
    found = calls(tmp_path, "this.http.get(this.baseUrl + '/orders');\n")
    assert found[0]["url"] == "/orders" and found[0]["base_unknown"]


# ---- route_table ---------------------------------------------------------

def test_spring_prefix_is_applied(tmp_path):
    write(tmp_path, "C.java", '@RestController\n@RequestMapping("/v1/items")\npublic class C {\n'
                              '  @PutMapping("/{itemId}")\n  public void update() {}\n  @GetMapping\n  public void all() {}\n}\n')
    got = {(r.method, r.path) for r in route_table.collect_routes(tmp_path)}
    assert got == {("PUT", "/v1/items/{itemId}"), ("GET", "/v1/items")}


def test_aspnet_controller_and_minimal_api_prefixes(tmp_path):
    write(tmp_path, "AssetsController.cs",
          '[Route("api/[controller]")]\n[ApiController]\npublic class AssetsController : ControllerBase\n{\n'
          '    [HttpPost]\n    [Route("Add")]\n    public IActionResult Add() { }\n}\n')
    write(tmp_path, "Module.cs", 'var group = endpoints.MapGroup("api/v{version:apiVersion}/tenants");\n'
                                 'ThemeEndpoint.Map(group);\ngroup.MapListEndpoint();\n')
    write(tmp_path, "ThemeEndpoint.cs", 'public static class ThemeEndpoint\n{\n    public static void Map(RouteGroupBuilder g)\n    {\n'
                                        '        g.MapGet("/theme", () => 1);\n    }\n}\n')
    write(tmp_path, "ListEndpoint.cs", 'public static class ListEndpoint\n{\n    public static RouteHandlerBuilder MapListEndpoint(this IEndpointRouteBuilder e)\n    {\n'
                                       '        return e.MapGet("/", () => 1);\n    }\n}\n')
    got = {(r.method, r.path): r.prefix_known for r in route_table.collect_routes(tmp_path)}
    assert got[("POST", "/api/assets/Add")] is True
    assert got[("GET", "/api/v{version:apiVersion}/tenants/theme")] is True
    assert got[("GET", "/api/v{version:apiVersion}/tenants")] is True


def test_express_router_mount_prefix(tmp_path):
    write(tmp_path, "src/app.js", "const express = require('express');\nconst orders = require('./routes/orders');\n"
                                  "const app = express();\napp.use('/api', orders);\n")
    write(tmp_path, "src/routes/orders.js", "router.post('/orders', h);\nrouter.get('/orders/:id', h);\n")
    got = {(r.method, r.path) for r in route_table.collect_routes(tmp_path)}
    assert got == {("POST", "/api/orders"), ("GET", "/api/orders/:id")}


def test_nest_controller_prefix_and_unknown_prefix_flag(tmp_path):
    write(tmp_path, "items.controller.ts", "@Controller('items')\nexport class ItemsController {\n  @Get(':id')\n  one() {}\n}\n")
    write(tmp_path, "web.php", "Route::get('/orders', [C::class, 'i']);\n")
    routes = {r.path: r for r in route_table.collect_routes(tmp_path)}
    assert routes["/items/:id"].prefix_known is True
    assert routes["/orders"].prefix_known is False  # Laravel groups are not resolved


# ---- match_api -----------------------------------------------------------

def route(method, path, known=True):
    return route_table.Route(method, path, "R.java", 1, "x", "", known)


def call(url, methods=("GET",), **flags):
    return {"file": "a.js", "line": 1, "callee": "fetch", "methods": list(methods), "url": url, "dynamic": False,
            "base_unknown": False, "optional_suffix": False, "unresolved": False, **flags}


def test_parameter_styles_and_api_version_segment_match():
    assert match_api.match_call(call("/api/v1/items/{}"), route("GET", "/api/v{version:apiVersion}/items/{id:guid}"))[0] == "exact"
    assert match_api.match_call(call("/items/{}"), route("GET", "/items/:id"))[0] == "exact"
    assert match_api.match_call(call("/items/{}"), route("POST", "/items/{id}")) is None
    assert match_api.match_call(call("/items/trash"), route("GET", "/items/{id}"))[0] == "exact"


def test_unknown_prefix_or_base_url_gives_likely_never_exact():
    assert match_api.match_call(call("/gw/v1/items"), route("GET", "/v1/items", known=False))[0] == "likely"
    assert match_api.match_call(call("/gw/v1/items"), route("GET", "/v1/items", known=True)) is None
    assert match_api.match_call(call("/me", base_unknown=True), route("GET", "/api/v1/sessions/me"))[0] == "likely"
    assert match_api.match_call(call("/me"), route("GET", "/api/v1/sessions/me")) is None


def test_runtime_verb_reaches_one_route_per_verb_and_most_specific_route_wins():
    routes = [route("POST", "/v1/items"), route("PUT", "/v1/items/{itemId}"), route("GET", "/v1/items/trash"), route("GET", "/v1/items/{id}")]
    result = match_api.match([call("/v1/items", ["POST", "PUT"], optional_suffix=True)], routes)
    assert {(m["route"]["method"], m["confidence"]) for m in result["matches"]} == {("POST", "exact"), ("PUT", "likely")}
    result = match_api.match([call("/v1/items/{}")], routes)
    assert [m["route"]["path"] for m in result["matches"]] == ["/v1/items/{id}"]  # not the literal /trash route


def test_report_lists_unmatched_and_uncalled(tmp_path):
    write(tmp_path, "fe/src/a.js", "fetch('/api/x');\nfetch('/api/missing');\nfetch(url);\n")
    write(tmp_path, "be/Routes.cs", 'public class Routes {\n  public void M() {\n    app.MapGet("/api/x", () => 1);\n    app.MapGet("/api/unused", () => 1);\n  }\n}\n')
    result = match_api.run([("fe", tmp_path / "fe")], [("be", tmp_path / "be")])
    assert [m["route"]["path"] for m in result["matches"]] == ["/api/x"] and result["matches"][0]["route"]["repo"] == "be"
    assert sorted(c["url"] or "(variable)" for c in result["unmatched_calls"]) == ["(variable)", "/api/missing"]
    assert [r["path"] for r in result["uncalled_routes"]] == ["/api/unused"]
    assert "MATCHED (1 call(s))" in match_api.format_report(result, with_repo=True)


# ---- repo_roots, validation and rendering across repos --------------------

def two_repo_flow():
    node = lambda i, repo, file: {"id": i, "label": i, "type": "logic", "description": "d", "file": file, "line": 1, "repo": repo}  # noqa: E731
    return {"flows": [{"id": "f", "title": "t", "mode": "code", "summary": "s", "entry": "ui",
                       "nodes": [node("ui", "web", "src/a.js"), node("api", "api", "Ctl.java")],
                       "edges": [{"from": "ui", "to": "api", "label": "POST /x"}]}]}


def test_parse_repo_args():
    assert repo_roots.parse_repo_args(["web=../w", "api=C:\\x\\api"]) == {"web": Path("../w"), "api": Path("C:\\x\\api")}
    assert repo_roots.parse_repo_args(["C:\\x\\single"]) == {None: Path("C:\\x\\single")}
    assert repo_roots.parse_repo_args(None) == {}


def test_each_node_is_validated_against_its_own_repo(tmp_path):
    write(tmp_path, "web/src/a.js", "x\n")
    write(tmp_path, "api/Ctl.java", "y\n")
    roots = {"web": tmp_path / "web", "api": tmp_path / "api"}
    assert validate_flow.validate(two_repo_flow(), roots)[0] == []
    swapped = two_repo_flow()
    swapped["flows"][0]["nodes"][0]["repo"] = "api"  # src/a.js does not exist in the api repo
    assert any("file not found" in e for e in validate_flow.validate(swapped, roots)[0])


def test_multi_repo_needs_repo_field_and_known_names(tmp_path):
    write(tmp_path, "web/src/a.js", "x\n")
    write(tmp_path, "api/Ctl.java", "y\n")
    roots = {"web": tmp_path / "web", "api": tmp_path / "api"}
    missing = two_repo_flow()
    del missing["flows"][0]["nodes"][0]["repo"]
    assert any("needs a 'repo' field" in e for e in validate_flow.validate(missing, roots)[0])
    unknown = two_repo_flow()
    unknown["flows"][0]["nodes"][1]["repo"] = "backend"
    assert any("unknown repo 'backend'" in e for e in validate_flow.validate(unknown, roots)[0])
    # a single unnamed repo keeps working with flows that carry no repo field
    single = two_repo_flow()
    for n in single["flows"][0]["nodes"]:
        n.pop("repo")
        n["file"] = "src/a.js"
    assert validate_flow.validate(single, tmp_path / "web")[0] == []


def test_vscode_links_use_each_nodes_repo(tmp_path):
    roots = {"web": tmp_path / "web", "api": tmp_path / "api"}
    steps = {s["id"]: s["vscode"] for s in render_page.build_flow(two_repo_flow()["flows"][0], roots)["steps"]}
    assert "/web/src/a.js:1" in steps["ui"] and "/api/Ctl.java:1" in steps["api"]


def test_split_stub_keeps_the_repo_field():
    anchor = {"file": "a.js", "line": 3, "repo": "web", "label": "x"}
    assert split_flow._stub("s", "Continues", "f2", anchor, "d")["repo"] == "web"
