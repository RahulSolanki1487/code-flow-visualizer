"""Tests for stitch_flows: linking frontend flows to backend flows through the call/route match."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))

import match_api  # noqa: E402
import render_page  # noqa: E402
import route_table  # noqa: E402
import stitch_flows  # noqa: E402
import validate_flow  # noqa: E402


def node(i, repo, file, line, **extra):
    return {"id": i, "label": i, "type": "logic", "description": "d", "repo": repo, "file": file, "line": line, **extra}


def flow(fid, entry, nodes, title=None):
    return {"id": fid, "title": title or fid, "mode": "code", "summary": "s", "entry": entry, "nodes": nodes,
            "edges": [{"from": nodes[0]["id"], "to": n["id"]} for n in nodes[1:]]}


def call(url, line, methods=("POST",), repo="web", file="src/api.ts", **flags):
    return {"repo": repo, "file": file, "line": line, "callee": "http.post", "methods": list(methods), "url": url, "dynamic": False,
            "base_unknown": False, "optional_suffix": False, "unresolved": False, **flags}


def route(method, path, file, line, repo="api", known=True):
    r = route_table.Route(method, path, file, line, "x", "", known)
    return {**r.__dict__, "repo": repo}


def run_stitch(flows, calls, routes, tolerance=3):
    """Build the match result with the real matcher, then stitch."""
    result = match_api.match(calls, [route_table.Route(**{k: v for k, v in r.items() if k != "repo"}) for r in routes])
    for m in result["matches"]:
        m["route"]["repo"] = "api"
    return stitch_flows.stitch({"flows": flows}, result, ["web"], ["api"], tolerance)


def by_id(data, fid, nid):
    return next(n for f in data["flows"] if f["id"] == fid for n in f["nodes"] if n["id"] == nid)


def test_exact_match_links_both_directions_and_validates(tmp_path):
    flows = [flow("screen", "open", [node("open", "web", "src/page.ts", 3), node("save", "web", "src/api.ts", 12)]),
             flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20), node("svc", "api", "Svc.cs", 5)])]
    out, report = run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    assert by_id(out, "screen", "save")["link_to"] == "create"
    assert by_id(out, "create", "ctl")["callers"] == [{"flow": "screen", "node": "save", "label": "screen: save"}]
    assert report["linked"][0]["confidence"] == "exact" and not report["no_backend_flow"] and not report["backend_flows_without_caller"]
    assert validate_flow.validate(out, None)[0] == []


def test_only_the_node_closest_to_the_call_is_linked():
    flows = [flow("screen", "ok", [node("ok", "web", "src/api.ts", 11), node("fail", "web", "src/api.ts", 14)]),
             flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20)])]
    out, _ = run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    assert by_id(out, "screen", "ok").get("link_to") == "create"
    assert "link_to" not in by_id(out, "screen", "fail")


def test_handler_line_tolerance_for_annotation_above_method():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]), flow("upd", "ctl", [node("ctl", "api", "Ctl.java", 52)])]
    out, _ = run_stitch(flows, [call("/v1/items/{}", 12, ["PUT"])], [route("PUT", "/v1/items/{itemId}", "Ctl.java", 51)])
    assert by_id(out, "screen", "a")["link_to"] == "upd"  # route annotation at 51, flow entry cites the method at 52


def test_likely_match_is_marked_inferred_with_a_note():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]), flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20)])]
    out, report = run_stitch(flows, [call("/gw/v1/items", 12)], [route("POST", "/v1/items", "Ctl.cs", 20, known=False)])
    n = by_id(out, "screen", "a")
    assert n["link_to"] == "create" and n["inferred"] is True and "likely match" in n["note"]
    assert report["linked"][0]["confidence"] == "likely"
    assert validate_flow.validate(out, None)[0] == []  # inferred nodes carry a note


def test_reports_routes_without_a_flow_and_calls_without_a_route_and_links_nothing():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12), node("b", "web", "src/api.ts", 30)])]
    calls = [call("/api/items", 12), call("/api/ghost", 30)]
    out, report = run_stitch(flows, calls, [route("POST", "/api/items", "Ctl.cs", 20)])
    assert [x["node"] for x in report["no_backend_flow"]] == ["a"] and "POST /api/items" in report["no_backend_flow"][0]["routes"][0]
    assert [x["node"] for x in report["no_route"]] == ["b"]
    assert not report["linked"] and "link_to" not in by_id(out, "screen", "a") and "links" not in out


def test_backend_flow_nobody_calls_is_reported():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]),
             flow("create", "c1", [node("c1", "api", "Ctl.cs", 20)]), flow("other", "c2", [node("c2", "api", "Ctl.cs", 40)])]
    routes = [route("POST", "/api/items", "Ctl.cs", 20), route("DELETE", "/api/other", "Ctl.cs", 40)]
    _, report = run_stitch(flows, [call("/api/items", 12)], routes)
    assert report["backend_flows_without_caller"] == ["other"]


def test_two_backend_flows_for_one_route_is_ambiguous_and_not_linked():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]),
             flow("v1", "c1", [node("c1", "api", "Ctl.cs", 19)]), flow("v2", "c2", [node("c2", "api", "Ctl.cs", 21)])]
    out, report = run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    assert report["ambiguous"][0]["flows"] == ["v1", "v2"] and "link_to" not in by_id(out, "screen", "a")


def test_stitching_twice_changes_nothing_more():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]), flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20)])]
    once, _ = run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    twice, report = run_stitch(once["flows"], [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    assert twice["flows"] == once["flows"] and not report["linked"]


def test_input_is_not_modified():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]), flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20)])]
    before = copy.deepcopy(flows)
    run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    assert flows == before


def test_validator_rejects_a_caller_pointing_at_an_unknown_flow():
    data = {"flows": [flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20, callers=[{"flow": "ghost", "node": "x", "label": "l"}])])]}
    assert any("unknown flow 'ghost'" in e for e in validate_flow.validate(data, None)[0])


def test_page_shows_called_from_and_open_sub_flow_buttons():
    flows = [flow("screen", "a", [node("a", "web", "src/api.ts", 12)]), flow("create", "ctl", [node("ctl", "api", "Ctl.cs", 20)])]
    out, _ = run_stitch(flows, [call("/api/items", 12)], [route("POST", "/api/items", "Ctl.cs", 20)])
    html = render_page.render(out)
    assert "Called from:" in html and '"callers"' in html  # template renders them; data carries them
    steps = {s["id"]: s for f in render_page.build_flow(out["flows"][1])["steps"] for s in [f]}
    assert steps["ctl"]["callers"][0]["flow"] == "screen"


def test_cli_end_to_end_on_the_bundled_sample_apps(tmp_path):
    out_path = tmp_path / "stitched.json"
    assert stitch_flows.main([str(ROOT / "examples" / "cross-repo" / "unlinked.flow.json"),
                              "--frontend", f"web={ROOT / 'examples' / 'sample-angular-app'}",
                              "--backend", f"api={ROOT / 'examples' / 'sample-express-app'}", "-o", str(out_path)]) == 0
    import json
    stitched = json.loads(out_path.read_text(encoding="utf-8"))
    linked = {n["id"]: n.get("link_to") for f in stitched["flows"] for n in f["nodes"] if n.get("link_to")}
    assert linked == {"checkout": "create_order"}  # not pay_error (same call), not login_api (no backend route)
