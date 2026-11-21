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
