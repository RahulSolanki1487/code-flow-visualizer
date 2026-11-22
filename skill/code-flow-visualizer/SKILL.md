---
name: code-flow-visualizer
description: Trace how code runs and produce a self-contained Bootstrap 5 HTML page with an interactive Mermaid diagram (flowchart, sequence or state), a step-by-step walkthrough and file:line references. Use when the user wants to understand, explain, document, visualize or diagram how something works end to end: "what happens when POST /x is called", a request or call flow, an API route, a background job or cron run, an event/message handler, a CLI command, a status or workflow lifecycle (state diagram), or a user journey / screen navigation flow (React, Next.js, Angular, Flutter). Also for onboarding maps of a repo's main flows. Not for architecture/ER/deployment diagrams of a whole system, charts of data, or reviewing code quality.
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
- More than ~40 nodes → split into several flows in the same file (`flows[]`) and link them with `"link_to": "<flow_id>"`.

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

## Files
- `templates/flow-page.html` – Bootstrap 5 + Mermaid page template (placeholders filled by the renderer)
- `scripts/find_entry_points.py` – heuristics for routes/handlers/main across common stacks
- `scripts/validate_flow.py` – schema + file:line checks
- `scripts/render_page.py` – JSON → Mermaid → HTML
- `scripts/check_mermaid.py` – optional Mermaid syntax check (Node)
- `references/flow-schema.md` – the `flow.json` format
- `references/mermaid-patterns.md` – safe Mermaid patterns and escaping rules
- `references/frameworks.md` – where to look per framework
