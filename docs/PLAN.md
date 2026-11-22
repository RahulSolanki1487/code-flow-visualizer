# Code Flow Visualizer – analysis & plan

## Goal
A Claude skill that takes a codebase (or one slice of it: a route, a screen, a CLI
command) and produces **one self-contained HTML page** built with Bootstrap 5 and an
interactive flow diagram, so any developer can understand how the code flows
without reading every file.

---

## Analysis

### 1. Bootstrap handles layout; it can't draw diagrams
We need a diagram renderer next to Bootstrap. **Mermaid.js** is the choice:
- Claude writes Mermaid syntax reliably
- Renders in the browser from plain text
- Supports flowcharts, sequence diagrams and state diagrams
- `svg-pan-zoom` adds zoom/pan for big diagrams

Alternatives (Cytoscape.js, D3, ELK) give more control but are much harder to
generate correctly. Revisit only if Mermaid layouts become the bottleneck.

### 2. Two modes: user flow vs code flow
| Mode | Nodes | Edges | Best diagram |
|---|---|---|---|
| `user` | screens, decisions | user actions ("taps Pay") | flowchart |
| `code` | functions, services, DB, external APIs | calls, returns, errors | flowchart or sequence |

### 3. Separate analysis from rendering (key decision)
```
Claude reads code ──► flow.json ──► validate_flow.py ──► render_page.py ──► flow.html
```
- Output is consistent: same JSON → same page
- Fewer tokens: Claude never writes the HTML/CSS/JS
- The page design can change without touching the analysis instructions
- The JSON can feed other outputs later (Markdown docs, Confluence, a VS Code panel)

### 4. Accuracy is the biggest risk
An LLM can invent a call that doesn't exist. Safeguards:
- Every node must cite a real `file:line`; `validate_flow.py` checks the file exists and the line is in range
- Hops not visible in code (DI, reflection, event bus, config routing) are drawn **dashed** with an "inferred" badge and a note
- Tracing stops at depth 5 by default

### 5. Scale limits
- Mermaid layouts degrade beyond ~40 nodes → split into sub-flows linked by `link_to`
- A whole repo won't fit in context → always scope to one flow; `find_entry_points.py` lists candidates

### 6. Technical details
- Mermaid label escaping (`"`, `<`, `>`, and **edge labels must be quoted** or `()` breaks parsing; found and fixed in testing)
- HTML-escape snippets; JSON payload escapes `</` so code can't break out of the `<script>` tag
- Offline mode: `fetch_vendor.py` + `--offline` inlines the libraries for locked-down client networks

---

## Repository layout
```
skill/code-flow-visualizer/     ← the skill itself (zip this folder to install)
  SKILL.md
  templates/flow-page.html
  scripts/find_entry_points.py
  scripts/validate_flow.py
  scripts/render_page.py
  scripts/fetch_vendor.py
  references/flow-schema.md
  references/mermaid-patterns.md
  references/frameworks.md
  assets/vendor/                ← optional offline copies of the libraries
examples/                       ← sample Express app + flow.json + rendered page
evals/evals.json                ← test prompts for measuring the skill
tests/                          ← pytest for the scripts
tools/package_skill.py          ← builds dist/code-flow-visualizer.zip
docs/PLAN.md                    ← this file
```

---

## Build plan

### Phase 1 – Prototype ✅ (done in this repo)
- [x] Bootstrap 5 + Mermaid page template (sidebar, tabs, step accordion, files, notes, dark mode, search, click-node-to-step)
- [x] `flow.json` schema
- [x] `render_page.py` (flowchart + sequence), `validate_flow.py`, `find_entry_points.py`
- [x] Sample Express app + sample flow, unit tests

### Phase 2 – Accuracy (3–4 days) ✅
- [x] Run the skill on 3 real repos; compare the diagram with reality (dotnet-starter-kit `POST /products`; PDIFAnalyticsAPI `POST /api/Assets/AddUpdateAsset`, kept private outside this repo; springboot-react `PUT /v1/items/{itemId}`)
- [~] Tighten SKILL.md trace rules wherever Claude drew wrong or missing edges (cross-cutting pipeline, registration check, verbatim snippets added; continue per repo)
- [x] Add a Mermaid parse check (`check_mermaid.py`, Node + mermaid + jsdom, optional) to catch syntax errors before delivery
- [x] Automatic splitting when a flow has > 40 nodes (`split_flow.py`: head flow + linked sub-flows, back-links, tested on a 100-node chain and a 122-node fan-out)
- [x] Snippet verification in `validate_flow.py` (snippet text must exist in the cited file, near the cited line)
- [x] Entry-point heuristics ignore commented-out examples
- [x] Third real repo: springboot-react `PUT /v1/items/{itemId}` (`examples/springboot-react/`); Spring entry-point output fixed (verb, path, method name, class prefix)

### Phase 3 – Modes & frameworks (≈ 1 week) ✅
- [x] User-flow mode tested on React (dotnet-starter-kit dashboard login), Next.js (zazencodes eve-pocket-research chat journey), Angular and Flutter (small bundled sample apps `examples/sample-angular-app`, `examples/sample-flutter-app`; synthetic, not real-world codebases)
- [x] Extend `find_entry_points.py` patterns (Go routers, Laravel, Rails, gRPC, Next.js pages, react-router object routes)
- [x] State-diagram support (`diagram: "state"`), example: invoice lifecycle
- [x] Optional "Open in VS Code" links (`render_page.py --repo`) (`vscode://file/<abs-path>:<line>`)

### Phase 4 – Evals (2–3 days) – done except description trigger tuning
- [x] Run the evals with the skill and score them (`evals/RESULTS.md`): 4 of 8 runnable evals failed in round 1, the skill was tuned, and the re-run of the 3 failing skill-related evals passed. No without-skill baseline (it cannot produce `flow.json`); eval 5 not run (no Spring repo)
- [x] Checks: every `file:line` real, Mermaid parses, key steps present, error paths shown, inferred hops explained, node limits, mode/diagram type (`evals/flow_checks.py`, `python evals/run_evals.py --golden`; 9 evals, goldens for 1, 6, 7, 8, 9)
- [~] Tune the `description` in SKILL.md so the skill triggers for "explain/diagram/visualize this flow" requests (description rewritten with trigger phrases and exclusions; `evals/trigger_queries.json` has 10 should/shouldn't queries, still to be run through skill-creator's description optimizer)

### Phase 5 – Packaging & distribution ✅ (except the manual upload to the Claude app)
- [x] `python tools/package_skill.py` builds a validated zip (name/description limits, referenced files); `tools/install_skill.py` copies into `~/.claude/skills/` or a project. Manual step left: upload the zip in the Claude app (Settings → Capabilities → Skills)
- [x] Bundle with other team skills as a plugin (`tools/build_plugin.py --extra-skills`); `claude plugin validate` passes (only warns when no `--author`)
- [x] Offline build: `package_skill.py --offline --fetch` (libraries pinned: Mermaid 11.17.2, Bootstrap 5.3.3, svg-pan-zoom 3.6.1); offline page verified to have no external refs

---

## Ideas for later
- Diff mode: highlight which steps changed in a PR
- Multi-flow index page for a whole service
- Export to Markdown/Confluence from the same `flow.json`
- Coverage overlay: mark steps with no tests
