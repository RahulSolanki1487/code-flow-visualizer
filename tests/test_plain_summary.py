"""The 'In plain words' summary for non-technical readers: rule, validation, rendering, splitting, evals, shipped examples."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))
sys.path.insert(0, str(ROOT / "evals"))

import flow_checks  # noqa: E402
import plain_language  # noqa: E402
import render_page  # noqa: E402
import split_flow  # noqa: E402
import validate_flow  # noqa: E402

GOOD = ("A customer places an order in the shop. The system checks they are signed in and that every item is in stock, "
        "charges their card and confirms the order. If anything fails, the order is stopped and the customer is told why.")


def flow(plain=GOOD, fid="f"):
    nodes = [{"id": "a", "label": "Start", "type": "entry", "description": "d", "file": "x.py", "line": 1},
             {"id": "b", "label": "End", "type": "logic", "description": "d", "file": "x.py", "line": 2}]
    f = {"id": fid, "title": "t", "mode": "code", "summary": "technical", "entry": "a", "nodes": nodes, "edges": [{"from": "a", "to": "b"}]}
    if plain is not None:
        f["plain_summary"] = plain
    return f


def test_good_text_passes_and_each_kind_of_jargon_is_named():
    assert plain_language.problems(GOOD) == []
    assert plain_language.problems("") == ["missing"] and plain_language.problems(None) == ["missing"]
    cases = {
        "The createOrder handler saves the order and tells the customer that everything went well today.": "code name",
        "Orders are saved by the ProductService and the customer is told that everything went well today.": "code name",
        "The order is stored in orders.js and the customer is told that everything went well today, ok.": "file name",
        "The shop receives POST /api/orders from the customer and answers that everything went well today.": "URL or route",
        "The shop calls place() and then the customer is told that everything went well today, always.": "code syntax",
        "After `payment` succeeds the shop confirms the order and the customer is told it went well today.": "code syntax",
        "Short text.": "too short",
        "word " * 200: "too long",
        "The stock_check step runs first, then the customer is told that everything went well today ok.": "code name",
    }
    for text, expected in cases.items():
        assert any(expected in p for p in plain_language.problems(text)), (text[:40], plain_language.problems(text))


def test_well_known_product_names_are_not_mistaken_for_code():
    text = "Customers sign in with OAuth, their orders are kept in PostgreSQL and a summary is sent to GitHub for the team."
    assert plain_language.problems(text) == []


def test_validator_warns_when_missing_or_technical_but_never_errors(tmp_path):
    for plain, expect in ((None, "no 'plain_summary'"), ("The createOrder handler in orders.js does it all, as the team expected.", "not plain")):
        errors, warnings = validate_flow.validate({"flows": [flow(plain)]}, None)
        assert errors == [] and any(expect in w for w in warnings), warnings
    errors, warnings = validate_flow.validate({"flows": [flow(GOOD)]}, None)
    assert errors == [] and not any("plain" in w for w in warnings)


def test_plain_summary_reaches_the_page_data_and_the_template_has_the_box():
    html = render_page.render({"project": "p", "flows": [flow(GOOD)]})
    assert "In plain words" in html and 'id="cfv-plain-text"' in html
    built = render_page.build_flow(flow(GOOD))
    assert built["plain_summary"] == GOOD
    assert render_page.build_flow(flow(None))["plain_summary"] == ""


def test_split_gives_each_part_its_own_plain_text_and_adds_none_when_the_parent_has_none():
    big = flow(GOOD)
    big["nodes"] = [{"id": f"n{i}", "label": f"S{i}", "type": "logic", "description": "d", "file": "x.py", "line": 1} for i in range(60)]
    big["entry"] = "n0"
    big["edges"] = [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(59)]
    parts = split_flow.split_flow(big, 20)
    assert len(parts) > 1 and parts[0]["plain_summary"] == GOOD
    for child in parts[1:]:
        assert child["plain_summary"] != GOOD and plain_language.problems(child["plain_summary"]) == []
    plain_less = dict(big)
    del plain_less["plain_summary"]
    assert all("plain_summary" not in p for p in split_flow.split_flow(plain_less, 20))


def test_eval_check_fails_when_a_flow_has_no_plain_summary_or_a_technical_one():
    ok = flow_checks.run_checks({"flows": [flow(GOOD)]}, None, [{"check": "plain_summary"}])[0]
    assert ok[1] is True
    for bad in (None, "orders.js calls POST /api/orders and returns the created order to the caller, as designed."):
        name, passed, detail = flow_checks.run_checks({"flows": [flow(GOOD, "a"), flow(bad, "b")]}, None, [{"check": "plain_summary"}])[0]
        assert passed is False and detail.startswith("b:")


def test_every_shipped_example_flow_has_a_plain_summary():
    files = [p for p in (ROOT / "examples").rglob("*.json") if "flows" in json.loads(p.read_text(encoding="utf-8"))]
    assert len(files) >= 9
    for p in files:
        for f in json.loads(p.read_text(encoding="utf-8"))["flows"]:
            assert plain_language.problems(f.get("plain_summary")) == [], (p.name, f["id"])
