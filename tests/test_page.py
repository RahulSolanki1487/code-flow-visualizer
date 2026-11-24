"""Browser-level test of the rendered page (jsdom + real Bootstrap, stubbed Mermaid)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "code-flow-visualizer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_page  # noqa: E402

JSDOM_DIR = SCRIPTS / "mermaid-check" / "node_modules" / "jsdom"
BOOTSTRAP = ROOT / "skill" / "code-flow-visualizer" / "assets" / "vendor" / "bootstrap.bundle.min.js"


def flow(i, marker):
    plain = {"plain_summary": "A shopper starts at FIRST and later reaches B, where the payment is taken."} if i == 1 else {}
    return {"id": f"f{i}", "title": f"Flow {i}", "mode": "code", "diagram": "flowchart", "summary": "s", "entry": "a", **plain,
            "nodes": [{"id": "a", "label": marker, "type": "entry", "file": "x.py", "line": 1, "description": "d"},
                      {"id": "b", "label": "B", "type": "logic", "file": "x.py", "line": 2, "description": "d"}],
            "edges": [{"from": "a", "to": "b"}]}


def other_diagram(i, kind):
    f = flow(i, f"N{i}")
    f["diagram"] = kind
    return f


@pytest.fixture(scope="module")
def sidebar_result(tmp_path_factory):
    if not shutil.which("node") or not JSDOM_DIR.is_dir():
        pytest.skip("Node/jsdom not installed (npm install in scripts/mermaid-check)")
    if not BOOTSTRAP.is_file():
        pytest.skip("Bootstrap vendor file missing (python scripts/fetch_vendor.py)")
    page = tmp_path_factory.mktemp("page") / "page.html"
    page.write_text(render_page.render({"project": "p", "flows": [flow(1, "FIRST"), flow(2, "SECOND"), other_diagram(3, "state"), other_diagram(4, "sequence")]}), encoding="utf-8")
    proc = subprocess.run(["node", str(ROOT / "tests" / "js" / "sidebar.mjs"), str(page), str(BOOTSTRAP), str(JSDOM_DIR)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr[:500]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_clicking_a_flow_returns_to_the_diagram_tab(sidebar_result):
    assert sidebar_result["stepsActiveBefore"] is True
    assert sidebar_result["diagramActiveAfter"] is True and sidebar_result["stepsActiveAfter"] is False
    assert sidebar_result["diagramActiveFromFiles"] is True


def test_clicking_a_flow_refreshes_the_data(sidebar_result):
    assert sidebar_result["title"] == "Flow 2"
    assert sidebar_result["diagramSource"] == "second"


def test_a_slow_earlier_render_does_not_overwrite_the_latest_flow(sidebar_result):
    assert sidebar_result["diagramAfterRace"] == "second"


def test_layout_button_flips_a_flowchart_between_vertical_and_horizontal_and_keeps_the_choice(sidebar_result):
    assert sidebar_result["layoutStart"] == {"label": "Horizontal", "hidden": False, "first": "flowchart TD"}
    assert sidebar_result["layoutHorizontal"] == {"label": "Vertical", "first": "flowchart LR"}
    assert sidebar_result["layoutKeptOnNextFlow"] == {"label": "Vertical", "first": "flowchart LR"}   # another flow stays horizontal
    assert sidebar_result["layoutBackToVertical"] == {"label": "Horizontal", "first": "flowchart TD"}


def test_layout_button_also_turns_state_diagrams_and_is_hidden_for_sequence_diagrams(sidebar_result):
    assert sidebar_result["stateVertical"]["line"] == "direction TB" and sidebar_result["stateHorizontal"]["line"] == "direction LR"
    assert sidebar_result["sequenceButtonHidden"] is True


def test_plain_words_names_the_diagram_steps_as_links_and_follows_the_selected_flow(sidebar_result):
    first, second = sidebar_result["plainFirst"], sidebar_result["plainSecond"]
    assert first["hidden"] is False and first["text"] == "A shopper starts at FIRST and later reaches B, where the payment is taken."
    assert first["links"] == [["FIRST", "a"], ["B", "b"]]          # each step name is a link to that step
    assert sidebar_result["refOpensSteps"] is True                  # clicking one opens the step card
    assert second["hidden"] is True and second["text"] == "" and second["links"] == []   # flow 2 has none: nothing stale stays
