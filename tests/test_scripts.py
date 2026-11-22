"""Basic tests for the skill scripts. Run with:  python -m pytest -q"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "code-flow-visualizer" / "scripts"
SAMPLE_JSON = ROOT / "examples" / "sample-flow.json"
SAMPLE_REPO = ROOT / "examples" / "sample-express-app"
sys.path.insert(0, str(SCRIPTS))

import find_entry_points  # noqa: E402
import render_page  # noqa: E402
import validate_flow  # noqa: E402


def load():
    return json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))


def test_sample_is_valid():
    errors, _ = validate_flow.validate(load(), SAMPLE_REPO)
    assert errors == []


def test_bad_line_and_missing_file_are_caught():
    data = load()
    node = data["flows"][0]["nodes"][0]
    node["line"] = 9999
    bad = copy.deepcopy(node)
    bad["id"], bad["file"] = "ghost", "src/does_not_exist.js"
    data["flows"][0]["nodes"].append(bad)
    errors, _ = validate_flow.validate(data, SAMPLE_REPO)
    assert any("out of range" in e for e in errors)
    assert any("file not found" in e for e in errors)


def test_dangling_edge_is_caught():
    data = load()
    data["flows"][0]["edges"].append({"from": "route", "to": "nowhere"})
    errors, _ = validate_flow.validate(data, None)
    assert any("nowhere" in e for e in errors)


def test_render_produces_page():
    html = render_page.render(load())
    assert "{{" not in html.split('id="cfv-data"')[0]  # all template placeholders filled
    assert "flowchart TD" in html and "sequenceDiagram" in html
    assert 'cfvSelect(\\"route\\")' in html


def test_edge_labels_are_quoted_and_escaped():
    flow = load()["flows"][0]
    flow["edges"][0]["label"] = 'call("x") <b>'
    mm = render_page.flowchart(flow)
    assert '|"call(#quot;x#quot;) #lt;b#gt;"|' in mm


def test_script_tag_cannot_break_out():
    data = load()
    data["flows"][0]["nodes"][0]["snippet"] = "</script><script>alert(1)</script>"
    html = render_page.render(data)
    assert "</script><script>alert(1)" not in html


def test_entry_points_found():
    hits = find_entry_points.scan(SAMPLE_REPO, 50)
    assert {h["match"] for h in hits} >= {"post /orders", "get /orders/:id"}


def test_entry_points_ignore_commented_examples(tmp_path):
    (tmp_path / "Doc.cs").write_text(
        '/// endpoints.MapPost("/reset", ...)\n'
        'endpoints.MapPost("/real", () => 1);\n', encoding="utf-8")
    hits = find_entry_points.scan(tmp_path, 50)
    assert [h["match"] for h in hits] == ["Post /real"]


def test_snippet_must_exist_in_file():
    lines = ["class A {", "  void Run() {", "    Save(x);", "  }", "}"]
    assert validate_flow.check_snippet(lines, "void Run() {\n    Save(x);", 2) is None
    assert "not found" in validate_flow.check_snippet(lines, "InventedCall(y);", 2)
    assert validate_flow.check_snippet(lines, "Save(x); ...", 3) is None  # ellipsis tolerated


def test_snippet_far_from_cited_line_is_flagged():
    lines = ["x"] * 40 + ["Save(x);"]
    assert "but node cites" in validate_flow.check_snippet(lines, "Save(x);", 1)


def test_invented_snippet_is_a_validation_error():
    data = load()
    data["flows"][0]["nodes"][0]["snippet"] = "router.destroyEverything();"
    errors, _ = validate_flow.validate(data, SAMPLE_REPO)
    assert any("snippet line not found" in e for e in errors)


def test_mermaid_checker_flags_syntax_errors_or_skips():
    import check_mermaid
    items = [{"id": "ok", "text": 'flowchart TD\n a["x"] --> b["y"]\n'},
             {"id": "bad", "text": "flowchart TD\n a[x -->|calls()| b[y\n"}]
    try:
        results = {r["id"]: r["ok"] for r in check_mermaid.run_checker(items)}
    except check_mermaid.CheckerUnavailable:
        import pytest
        pytest.skip("Node/mermaid-check dependencies not installed")
    assert results == {"ok": True, "bad": False}


def test_generated_diagrams_cover_all_flows():
    import check_mermaid
    ids = [d["id"] for d in check_mermaid.diagrams(load())]
    assert ids == [f["id"] for f in load()["flows"]]


def test_new_entry_point_patterns(tmp_path):
    (tmp_path / "main.go").write_text('r.GET("/users/:id", h)\nmux.HandleFunc("/health", h)\n', encoding="utf-8")
    (tmp_path / "web.php").write_text("Route::get('/orders', [C::class, 'i']);\n", encoding="utf-8")
    (tmp_path / "routes.rb").write_text("  get '/orders', to: 'orders#index'\n", encoding="utf-8")
    (tmp_path / "svc.proto").write_text("service S {\n  rpc GetUser (Req) returns (Res);\n}\n", encoding="utf-8")
    (tmp_path / "page.tsx").write_text("export default async function DashboardPage() {}\n", encoding="utf-8")
    (tmp_path / "routes.tsx").write_text('const r = [{\n  path: "/login",\n  element: <Login />,\n}];\n', encoding="utf-8")
    found = {(h["framework"], h["match"]) for h in find_entry_points.scan(tmp_path, 50)}
    assert {("go-http", "GET /users/:id"), ("go-http", "HandleFunc /health"), ("laravel", "get /orders"),
            ("rails", "get /orders"), ("grpc", "GetUser"), ("nextjs", "DashboardPage"),
            ("react-router-objects", "/login")} <= found


STATE_FLOW = {
    "id": "inv", "title": "Invoice", "mode": "code", "diagram": "state", "summary": "s", "entry": "draft",
    "nodes": [
        {"id": "draft", "label": "Draft", "type": "logic", "description": "d", "file": "a.py", "line": 1},
        {"id": "paid", "label": "Paid: done", "type": "data", "description": "d", "file": "a.py", "line": 1},
        {"id": "oops", "label": "Error", "type": "error", "description": "d", "file": "a.py", "line": 1},
    ],
    "edges": [{"from": "draft", "to": "paid", "label": "pay: now"}, {"from": "paid", "to": "oops", "kind": "error"}],
}


def test_state_diagram_is_valid_and_rendered():
    errors, _ = validate_flow.validate({"flows": [STATE_FLOW]}, None)
    assert errors == []
    mm = render_page.state(STATE_FLOW)
    assert mm.startswith("stateDiagram-v2")
    assert "[*] --> draft" in mm
    assert "draft --> paid : pay  now" in mm  # colon in a label would break the transition syntax
    assert "oops --> [*]" in mm                # sink state ends the diagram
    assert "class oops err" in mm


def test_unknown_diagram_type_rejected():
    flow = {**STATE_FLOW, "diagram": "pie"}
    errors, _ = validate_flow.validate({"flows": [flow]}, None)
    assert any("diagram must be one of" in e for e in errors)


def test_vscode_links(tmp_path):
    url = render_page.vscode_url(tmp_path, "src/a.py", 12)
    assert url.startswith("vscode://file/") and url.endswith("src/a.py:12")
    assert render_page.vscode_url(None, "src/a.py", 12) == ""
    assert render_page.vscode_url(tmp_path, None, 12) == ""
    steps = render_page.build_flow(STATE_FLOW, tmp_path)["steps"]
    assert all(s["vscode"] for s in steps)
    assert not any(s["vscode"] for s in render_page.build_flow(STATE_FLOW)["steps"])


def test_state_diagram_parses_in_mermaid():
    import check_mermaid
    try:
        res = check_mermaid.run_checker([{"id": "s", "text": render_page.state(STATE_FLOW)}])
    except check_mermaid.CheckerUnavailable:
        import pytest
        pytest.skip("Node/mermaid-check dependencies not installed")
    assert res[0]["ok"], res


def test_aspnet_controller_routes_show_route_and_action(tmp_path):
    (tmp_path / "AssetsController.cs").write_text(
        '    [HttpPost]\n    [Route("AddUpdateAsset")]\n'
        '    public async Task<IActionResult> AddUpdateAsset([FromBody] Asset a)\n    {\n    }\n'
        '    [HttpGet("{id}")]\n    public IActionResult GetOne(int id) { }\n', encoding="utf-8")
    matches = [h["match"] for h in find_entry_points.scan(tmp_path, 50)]
    assert "HttpPost AddUpdateAsset AddUpdateAsset" in matches
    assert "HttpGet {id} GetOne" in matches


# ---- evals harness -------------------------------------------------------
EVALS = ROOT / "evals"
sys.path.insert(0, str(EVALS))
import flow_checks  # noqa: E402
import run_evals  # noqa: E402


def test_golden_evals_pass():
    assert run_evals.main(["--golden"]) == 0


def test_every_eval_has_checks_and_known_check_names():
    spec = json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))
    for ev in spec["evals"]:
        assert ev["checks"], f"eval {ev['id']} has no machine-checkable checks"
        for c in ev["checks"]:
            assert c["check"] in flow_checks.CHECKS, c


def test_checks_catch_bad_flows():
    data = load()
    bad = copy.deepcopy(data)
    for f in bad["flows"]:
        for e in f["edges"]:
            e.pop("kind", None)
            e.pop("inferred", None)
        for n in f["nodes"]:
            n.pop("inferred", None)
            if n["type"] == "error":
                n["type"] = "logic"
    res = {n: p for n, p, _ in flow_checks.run_checks(bad, SAMPLE_REPO, [
        {"check": "has_error_path"}, {"check": "inferred_has_note"},
        {"check": "max_nodes", "param": 3}, {"check": "mode", "param": "user"},
        {"check": "mentions", "param": ["kafka"]}, {"check": "nonexistent"}])}
    assert res == {"has_error_path": False, "inferred_has_note": False, "max_nodes": False,
                   "mode": False, "mentions": False, "nonexistent": False}


def test_run_evals_reads_model_outputs(tmp_path):
    out = tmp_path / "eval-1"
    out.mkdir()
    (out / "flow.json").write_text(SAMPLE_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    assert run_evals.main(["--outputs", str(tmp_path)]) == 0
    broken = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
    broken["flows"][0]["nodes"][0]["file"] = "src/nope.js"
    (out / "flow.json").write_text(json.dumps(broken), encoding="utf-8")
    assert run_evals.main(["--outputs", str(tmp_path)]) == 1


def test_trigger_queries_are_well_formed():
    q = json.loads((EVALS / "trigger_queries.json").read_text(encoding="utf-8"))
    assert len(q["should_trigger"]) >= 8 and len(q["should_not_trigger"]) >= 8
    assert not set(q["should_trigger"]) & set(q["should_not_trigger"])
