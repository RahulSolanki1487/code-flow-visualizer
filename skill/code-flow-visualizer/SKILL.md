---
name: code-flow-visualizer
description: >-
  Trace how code runs and produce a self-contained Bootstrap 5 HTML page with an interactive
  Mermaid diagram (flowchart, sequence or state), a step-by-step walkthrough and file:line
  references. Use when the user wants to understand, explain, document, visualize or diagram how
  something works end to end: "what happens when POST /x is called", a request or call flow, an
  API route, a background job or cron run, an event/message handler, a CLI command, a status or
  workflow lifecycle (state diagram), or a user journey / screen navigation flow (React, Next.js,
  Angular, Flutter). Also for onboarding maps of a repo's main flows. Not for
  architecture/ER/deployment diagrams of a whole system, charts of data, or reviewing code
  quality.
---

# Code Flow Visualizer

Turn a slice of a codebase into one HTML page a developer can open and understand
without reading every file. The page has a diagram, a step-by-step walkthrough,
a file list and notes on anything uncertain.

## Core principle

**Analysis and rendering are separate.** You (Claude) analyse code and write
`flow.json`. Scripts validate it and render the HTML. Never hand-write the HTML page.

## Workflow

### 1. Scope
Decide two things before reading much code:
- **Entry point** – a route (`POST /orders`), a screen (`LoginPage`), a command (`cli sync`), a job or event handler.
- **Mode**
  - `code` – execution path of one entry point (controller → service → repo → DB). Diagram: `sequence` or `flowchart`; for a status/workflow lifecycle use `state` (nodes = states, edges = transitions, e.g. `Draft → Issued → Paid`).
  - `user` – screens and user actions (Login → Dashboard → Checkout). Diagram: `flowchart`.

If the user gave no entry point, run:
```bash
python scripts/find_entry_points.py <repo_path>
```
and offer the list (or pick the most central one if nobody is there to ask).

### 2. Discover
Identify the framework (see `references/frameworks.md`) so you know where
routes, controllers, DI registrations and screens live.

### 2b. Frontend and backend in separate repos
When the user has a UI repo and an API repo, find the join points first instead of guessing:
```bash
python scripts/match_api.py --frontend web=<web_repo> --backend api=<api_repo>
```
It lists every frontend HTTP call, the backend route it reaches (`exact` or `likely`), calls with no
route (third-party APIs, static files, URLs built at runtime) and routes nobody calls. Use it to:
- start a flow at a screen, follow it to the call site (`find_api_calls.py <web_repo>`), cross to the
  matched route (`route_table.py <api_repo>`) and keep tracing in the backend;
- mark a `likely` match as `inferred` and say why; never draw a link for an unmatched call.
Give every node a `"repo": "web"` / `"repo": "api"` field and validate with
`validate_flow.py flow.json --repo web=<web_repo> --repo api=<api_repo>` (same flags for `render_page.py`).

If a gateway or reverse proxy sits between them (the frontend calls `/orders-svc/api/v1/orders`, the service
serves `/api/v1/orders`), tell the matcher how URLs are rewritten, or those calls stay unmatched:
`--gateway-config nginx.conf` (or an Ocelot JSON file; upstream hosts are mapped to backends by name or folder
name) or `--gateway-prefix orders=orders-svc` (no leading slash). Same flags on `stitch_flows.py`.

Then let the tool connect the two sides instead of drawing the join by hand. Trace the frontend flow
(cite the line of the HTTP call) and one backend flow per route it reaches (entry node = the handler,
at the route's file:line), keep them as separate flows in one `flow.json`, and run:
```bash
python scripts/stitch_flows.py flow.json --frontend web=<web_repo> --backend api=<api_repo> -o flow.json
```
It sets `link_to` on the call-site node ("Open sub-flow") and `callers` on the backend entry node
("Called from"), marks a `likely` match as inferred, and reports calls whose route has no flow yet
(trace those next), calls with no route, ambiguous matches and backend flows nobody calls.
Do not hand-write cross-repo `link_to`s for calls the report says have no route.

### 3. Trace
Follow calls from the entry point:
- Default **max depth 5**. Stop at framework/library boundaries (don't trace into node_modules, site-packages, JDK).
- Record branches (if/else, switch), loops worth mentioning, async/await, queues/events, DB reads/writes, external HTTP calls, error/exception paths.
- **Read the code you cite.** Every node needs a real `file` and `line`.
- **Trace the cross-cutting pipeline, not just the handler.** Real requests pass through code the handler never mentions: auth/permission policies, endpoint filters, mediator/pipeline behaviors, ORM save interceptors, global exception handlers, middleware. Find where each is *registered* (grep `AddTransient(typeof(IPipelineBehavior`, `.WithIdempotency`, `ISaveChangesInterceptor`, `UseExceptionHandler`, `app.Use*`) and add a node for each that affects behavior.
- **Confirm registration before drawing a hop.** A class that looks like part of the flow may never be wired up (dead code). Grep for its call sites; if none, leave it out and mention it in `notes`.
- **Snippets are copied, not recalled.** Copy lines verbatim from the cited file, near the cited `line`. The validator rejects snippets that do not exist in the file.
- If a hop is not visible in code (DI container, reflection, event bus, config-driven routing), still add it but set `"inferred": true` and say why in `note`.

### 4. Model
Write `flow.json` following `references/flow-schema.md`. Rules:
- Node ids: short, `snake_case`, unique.
- Node `type` ∈ `entry, logic, data, external, decision, error, ui, event`.
- Keep labels short (≤ 40 chars); put detail in `description`.
- More than ~40 nodes → prefer scoping the flow down. If it must stay large, run `python scripts/split_flow.py flow.json -o flow.json` (splits flowchart/state flows into linked sub-flows; sequence flows are not split) or split by hand with `"link_to": "<flow_id>"`.

### 5. Validate
```bash
python scripts/validate_flow.py flow.json --repo <repo_path>
```
Fix every error (missing files, lines out of range, dangling edges, snippet text that is not in the file) and re-run until clean.
Warnings about inferred edges are fine.

Optional but recommended (needs Node; one-time `npm install` in `scripts/mermaid-check/`):
```bash
python scripts/check_mermaid.py flow.json
```
It parses the generated Mermaid for every flow. Exit 2 means the checker is not installed (nothing was checked).

### 6. Render
```bash
python scripts/render_page.py flow.json -o flow.html            # CDN libraries
python scripts/render_page.py flow.json -o flow.html --repo <repo_path>  # adds "Open in VS Code" links
python scripts/render_page.py flow.json -o flow.html --offline  # see note below
```
`--offline` inlines Bootstrap/Mermaid from `assets/vendor/` if those files exist
(download them once; see README). Without them it falls back to CDN with a warning.

### 7. Deliver
Give the user `flow.html` plus a 3–5 line summary: what the flow does, the number of
steps, and anything inferred or risky (from `notes`).

## Quality bar
- No invented functions. If you could not find it, don't draw it.
- Every step card should answer: *what happens here and why does it matter?*
- Error paths are first-class – show where failures go.
- Prefer one clear flow over a sprawling map of the whole repo.

## Mode-specific rules (learned from eval runs)
- **`user` mode stays at the user's level.** At least ~80% of nodes should be screens (`ui`), choices (`decision`), failures (`error`) or backend calls (`external`). Do not give each service/helper call its own node: fold code-level plumbing (token storage, router calls, signals) into the `description` of the screen or decision it belongs to, or into an edge label.
- **`state` diagrams show what is forbidden, not just what is allowed.** Read the guards (`RequireStatus`, `if (status is ...) throw`, switch defaults). Every transition the code rejects becomes an `error` node (or `error` edge) naming the exception, and repeatable/idempotent calls get a note. A state diagram with only happy-path arrows is incomplete.
- **Do not mark a hop `inferred` just because a URL comes from config**; mark it only when the call target or handler cannot be found by reading the code.

## Files
- `templates/flow-page.html` – Bootstrap 5 + Mermaid page template (placeholders filled by the renderer)
- `scripts/find_entry_points.py` – heuristics for routes/handlers/main across common stacks
- `scripts/find_api_calls.py` – HTTP calls a frontend makes (fetch, axios, HttpClient, Dart)
- `scripts/route_table.py` – a backend's routes with full paths (class/group prefixes resolved)
- `scripts/match_api.py` – match frontend calls to backend routes across repos
- `scripts/gateway_rules.py` – gateway rewrite rules (nginx.conf, Ocelot JSON, explicit prefixes)
- `scripts/stitch_flows.py` – link frontend flows to backend flows (`link_to` / `callers`) from that match
- `scripts/validate_flow.py` – schema + file:line checks
- `scripts/split_flow.py` – split flows over 40 nodes into linked sub-flows
- `scripts/render_page.py` – JSON → Mermaid → HTML
- `scripts/check_mermaid.py` – optional Mermaid syntax check (Node)
- `references/flow-schema.md` – the `flow.json` format
- `references/mermaid-patterns.md` – safe Mermaid patterns and escaping rules
- `references/frameworks.md` – where to look per framework
