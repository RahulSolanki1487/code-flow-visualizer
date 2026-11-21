# Code Flow Visualizer – Claude skill

A Claude skill that traces how code runs (an API route, a user journey, a CLI command)
and produces a **self-contained Bootstrap 5 HTML page** with an interactive Mermaid
flow diagram, step-by-step walkthrough, file list and risk notes.

![flow](https://img.shields.io/badge/status-prototype-blue)

## Quick start

```bash
# 1. Try the scripts on the bundled sample
python skill/code-flow-visualizer/scripts/find_entry_points.py examples/sample-express-app
python skill/code-flow-visualizer/scripts/validate_flow.py examples/sample-flow.json --repo examples/sample-express-app
python skill/code-flow-visualizer/scripts/render_page.py examples/sample-flow.json -o examples/sample-flow.html

# 2. Open examples/sample-flow.html in a browser (needs internet for the CDN libraries)

# 3. Run tests
pip install pytest
python -m pytest -q
```

Requires Python 3.10+. No other dependencies.

### Offline pages
```bash
python skill/code-flow-visualizer/scripts/fetch_vendor.py      # one-time download
python skill/code-flow-visualizer/scripts/render_page.py examples/sample-flow.json -o out.html --offline
```

## Install the skill

| Where | How |
|---|---|
| Claude app (web/desktop) | `python tools/package_skill.py` → upload `dist/code-flow-visualizer.zip` under Settings → Capabilities → Skills |
| Claude Code (personal) | copy `skill/code-flow-visualizer/` to `~/.claude/skills/` |
| Claude Code (project) | copy it to `<your-project>/.claude/skills/` |

Then ask Claude something like:
> "Show me the flow of `POST /orders` in this repo as an HTML page."

## How it works

```
Claude reads code ──► flow.json ──► validate_flow.py ──► render_page.py ──► flow.html
```
Claude only does the analysis (`flow.json`); scripts handle validation and the HTML,
so pages are consistent and every node points to a real `file:line`.

See [`docs/PLAN.md`](docs/PLAN.md) for the full analysis and roadmap, and
[`skill/code-flow-visualizer/references/flow-schema.md`](skill/code-flow-visualizer/references/flow-schema.md) for the JSON format.

## Repo layout
```
skill/code-flow-visualizer/   the skill (SKILL.md, template, scripts, references)
examples/                     sample Express app, sample flow.json, rendered page
evals/                        test prompts for measuring the skill
tests/                        pytest for the scripts
tools/                        packaging
docs/                         plan & analysis
```
