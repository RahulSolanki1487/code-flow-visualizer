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

# 3. Run tests and the eval harness
pip install pytest
python -m pytest -q
python evals/run_evals.py --golden
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
| Claude Code (personal) | `python tools/install_skill.py --personal` (copies to `~/.claude/skills/`) |
| Claude Code (project) | `python tools/install_skill.py --project <your-project>` |
| Claude Code plugin (teams) | `python tools/build_plugin.py --zip` → `dist/plugin/`; try with `claude --plugin-dir dist/plugin/code-flow-visualizer`. Bundle other team skills with `--extra-skills DIR [DIR ...]` and a custom `--name` |
| No internet at the client | `python tools/package_skill.py --offline --fetch` → `dist/code-flow-visualizer-offline.zip` (Bootstrap, Mermaid and svg-pan-zoom included; pages made with `render_page.py --offline` have no external requests). Add `--offline` to `install_skill.py` / `build_plugin.py` too |

All packaging commands validate `SKILL.md` first (name, description length, referenced files). The version is in `VERSION`.

Then ask Claude something like:
> "Show me the flow of `POST /orders` in this repo as an HTML page."

## Frontend and backend in separate repos
```bash
python skill/code-flow-visualizer/scripts/match_api.py --frontend web=../web-app --backend api=../api
```
prints which frontend call reaches which backend route (`exact`/`likely`), calls with no route, and
routes nobody calls. Flows can then cite files from both repos (`"repo": "web"` on each node) and be
validated with `--repo web=../web-app --repo api=../api`. Supported so far: calls via `fetch`, `axios`,
Angular `HttpClient`, Dart `http`/`dio`; routes for Spring, ASP.NET (controllers and minimal APIs with
`MapGroup`), Express, NestJS, FastAPI/Flask (other stacks are matched with an unknown prefix, so only as `likely`).

Behind a gateway, add `--gateway-config nginx.conf` (nginx or Ocelot JSON) or `--gateway-prefix orders=orders-svc`
so a call to `/orders-svc/api/v1/orders` is matched to the service's `/api/v1/orders`
(demo: `examples/cross-repo-gateway/`; public repos to try: [docs/TEST-REPOS.md](docs/TEST-REPOS.md)).

Link the two sides automatically: trace the frontend flow and a flow per backend route it reaches, then
```bash
python skill/code-flow-visualizer/scripts/stitch_flows.py flow.json --frontend web=../web-app --backend api=../api -o flow.json
```
adds "Open sub-flow" on the call-site step and "Called from" on the backend entry step, and lists calls
whose route has no flow yet. See `examples/cross-repo/` (sample Angular app + sample Express app).

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

## License

[MIT](LICENSE)
