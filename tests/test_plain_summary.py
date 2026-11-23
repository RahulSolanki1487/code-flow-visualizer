"""The 'In plain words' summary: a short story that names every diagram step exactly, so management can match text to boxes."""
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

LABELS = ["POST /orders", "auth middleware", "401 Unauthorized", "orderService.place"]
GOOD = ("A customer places an order by sending POST /orders. The auth middleware checks they are signed in; if not, the order stops with "
        "401 Unauthorized. Otherwise orderService.place saves the order and the customer is told it worked.")


def flow(plain=GOOD, fid="f", labels=LABELS):
    nodes = [{"id": f"n{i}", "label": l, "type": "logic", "description": "d", "file": "x.py", "line": 1} for i, l in enumerate(labels)]
    f = {"id": fid, "title": "t", "mode": "code", "summary": "technical", "entry": "n0", "nodes": nodes,
         "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(len(nodes) - 1)]}
    if plain is not None:
        f["plain_summary"] = plain
    return f


def test_step_names_are_allowed_and_required():
    assert plain_language.problems(GOOD, LABELS) == []           # routes, dotted and camelCase names are fine when they are step names
    assert plain_language.problems("", LABELS) == ["missing"] and plain_language.problems(None, LABELS) == ["missing"]


def test_missing_steps_are_listed_by_name():
    text = GOOD.replace("401 Unauthorized", "an error").replace("orderService.place", "the shop")
    found = plain_language.problems(text, LABELS)
    assert any("does not mention 2 of 4 steps" in p and "'401 Unauthorized'" in p and "'orderService.place'" in p for p in found), found


def test_step_names_match_whole_words_case_insensitively():
    assert plain_language.mentions("The invoice is Paid today.", "Paid") and plain_language.mentions("the invoice is paid", "Paid")
    assert not plain_language.mentions("The invoice is unpaid.", "Paid")                 # not inside another word
    assert plain_language.mentions("It ends in Paid cannot be voided.", "Paid cannot be voided")
    assert plain_language.mentions("Open /cart first", "Open /cart") and plain_language.mentions("then 'URL becomes /s/<id>'.", "URL becomes /s/<id>")


def test_anything_that_is_not_a_step_name_must_still_be_plain():
    cases = {
        "A customer sends POST /orders and the createOrder routine saves it while the customer waits for the result, ok.": "code name",
        "The order passes the auth middleware, 401 Unauthorized, orderService.place and POST /orders and goes to orders.js for storage.": "file name",
        "The order passes POST /orders, auth middleware, 401 Unauthorized, orderService.place and also GET /health for the monitor.": "URL or route",
        "The order passes POST /orders, auth middleware, 401 Unauthorized, orderService.place, then run() is called afterwards.": "code syntax",
        "The order passes POST /orders, auth middleware, 401 Unauthorized, orderService.place and the stock_check step as well.": "code name",
    }
    for text, expected in cases.items():
        assert any(expected in p for p in plain_language.problems(text, LABELS)), (text[:50], plain_language.problems(text, LABELS))


def test_length_limits_grow_with_the_number_of_steps():
    assert any("too short" in p for p in plain_language.problems("Short.", []))
    long_text = "word " * 150                                       # 750 chars
    assert any("too long" in p for p in plain_language.problems(long_text, []))
    assert not any("too long" in p for p in plain_language.problems(long_text, ["a"] * 10))   # 10 steps allow more text


def test_well_known_product_names_are_not_mistaken_for_code():
    assert plain_language.problems("Customers sign in with OAuth and their orders are kept in PostgreSQL, with a summary sent to GitHub.", []) == []


def test_validator_warns_when_missing_incomplete_or_technical_but_never_errors():
    cases = ((None, "no 'plain_summary'"), (GOOD.replace("auth middleware", "a check"), "does not mention"),
             (GOOD + " It also calls createUser()", "code"))
    for plain, expect in cases:
        errors, warnings = validate_flow.validate({"flows": [flow(plain)]}, None)
        assert errors == [] and any(expect in w for w in warnings), (expect, warnings)
    errors, warnings = validate_flow.validate({"flows": [flow(GOOD)]}, None)
    assert errors == [] and not any("plain" in w for w in warnings)


def test_plain_summary_reaches_the_page_data_and_the_template_has_the_box_and_the_links():
    html = render_page.render({"project": "p", "flows": [flow(GOOD)]})
    assert "In plain words" in html and 'id="cfv-plain-text"' in html and "cfv-ref" in html
    assert render_page.build_flow(flow(GOOD))["plain_summary"] == GOOD
    assert render_page.build_flow(flow(None))["plain_summary"] == ""


def test_the_diagram_is_not_changed_by_the_plain_summary():
    with_plain, without = flow(GOOD), flow(None)
    assert render_page.build_flow(with_plain)["mermaid"] == render_page.build_flow(without)["mermaid"]


def test_split_parts_list_their_own_steps_and_pass_the_rule():
    labels = [f"Step number {i}" for i in range(30)]
    big = flow("Placeholder text that does mention every single step number from zero to twenty nine in order. " + ", ".join(labels) + ".", labels=labels)
    parts = split_flow.split_flow(big, 12)
    assert len(parts) > 1
    for child in parts[1:]:
        assert child["plain_summary"].startswith("This page continues")
        assert plain_language.problems(child["plain_summary"], plain_language.step_labels(child)) == [], child["plain_summary"]
    plain_less = flow(None, labels=labels)
    assert all("plain_summary" not in p for p in split_flow.split_flow(plain_less, 12))
    assert plain_language.step_labels({"nodes": [{"id": "continues_x", "label": "Continues: A"}, {"id": "a", "label": "A"}]}) == ["A"]


def test_eval_check_fails_when_a_flow_has_no_plain_summary_or_leaves_a_step_out():
    ok = flow_checks.run_checks({"flows": [flow(GOOD)]}, None, [{"check": "plain_summary"}])[0]
    assert ok[1] is True
    for bad in (None, GOOD.replace("auth middleware", "a check")):
        name, passed, detail = flow_checks.run_checks({"flows": [flow(GOOD, "a"), flow(bad, "b")]}, None, [{"check": "plain_summary"}])[0]
        assert passed is False and detail.startswith("b:")


def test_every_shipped_example_flow_names_all_its_steps_in_the_plain_summary():
    files = [p for p in (ROOT / "examples").rglob("*.json") if "flows" in json.loads(p.read_text(encoding="utf-8"))]
    assert len(files) >= 9
    for p in files:
        for f in json.loads(p.read_text(encoding="utf-8"))["flows"]:
            assert plain_language.problems(f.get("plain_summary"), plain_language.step_labels(f)) == [], (p.name, f["id"])
