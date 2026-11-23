# Code Flow Visualizer

A [Claude](https://claude.com) skill that traces how code actually runs and turns it into **one self-contained HTML page**:
an interactive diagram, a step-by-step walkthrough with `file:line` references, a file list and notes on anything uncertain.
It also follows a request **across repositories**, from a frontend screen to the backend route it calls, and on to the database.

![license](https://img.shields.io/badge/license-MIT-green) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![version](https://img.shields.io/badge/version-0.5.0-informational)

Ask Claude things like:

> "Show me the flow of `POST /orders` in this repo as an HTML page."
> "Draw the login-to-checkout journey of our Angular app, including the route guard."
> "Give me a state diagram of an Invoice: Draft, Issued, Paid, Void."
> "What happens from the Insights screen in `web/` to the database in `api/`? Link the two."

## What you get

- **Interactive diagram** (Mermaid, zoom and pan, dark mode). Click a node to jump to its step.
- **Step-by-step walkthrough**: what happens, why it matters, the real code snippet and its `file:line`, with an "Open in VS Code" link.
- **Error paths as first-class steps**, and a clear marker for hops that are *inferred* (dependency injection, event buses, proxies) with the reason.
- **Several flows in one page**, linked to each other (a call-site step opens the backend flow; the backend entry step says who calls it).
- **No server, no build**: one `.html` file that works offline if you want it to.

Flow types: `code` (an entry point to its effects) and `user` (screens and actions); diagrams: flowchart, sequence and state.

## Why you can trust a page

Claude only does the analysis; scripts check it and render it, so the page is consistent and checkable.

```
Claude reads code ──► flow.json ──► validate_flow.py ──► render_page.py ──► flow.html
```

- Every node must cite a real file and line; **snippets are verified to exist in that file** (invented code is an error).
- `check_mermaid.py` parses the generated diagram before delivery.
- Flows over 40 nodes can be split into linked sub-flows (`split_flow.py`).
- A suite of 126 tests and a set of evals (`evals/`) guard the scripts and the skill's output.

## Quick start

```bash
# Try the scripts on the bundled sample (Python 3.10+, no other dependencies)
python skill/code-flow-visualizer/scripts/find_entry_points.py examples/sample-express-app
python skill/code-flow-visualizer/scripts/validate_flow.py examples/sample-flow.json --repo examples/sample-express-app
python skill/code-flow-visualizer/scripts/render_page.py examples/sample-flow.json -o examples/sample-flow.html
```
Open `examples/sample-flow.html` in a browser (it loads Bootstrap and Mermaid from a CDN; see *Offline* below).
More rendered examples are in `examples/`: a .NET API, a React dashboard login, an invoice state diagram, a Next.js app,
a Spring Boot service, sample Angular and Flutter apps, and a frontend-to-backend example (`examples/cross-repo/`).

## Install the skill

| Where | How |
|---|---|
| Claude app (web/desktop) | `python tools/package_skill.py` → upload `dist/code-flow-visualizer.zip` under Settings → Capabilities → Skills |
| Claude Code (personal) | `python tools/install_skill.py --personal` (copies to `~/.claude/skills/`) |
| Claude Code (project) | `python tools/install_skill.py --project <your-project>` |
| Claude Code plugin (teams) | `python tools/build_plugin.py --zip` → `dist/plugin/`; try it with `claude --plugin-dir dist/plugin/code-flow-visualizer`. Bundle other team skills with `--extra-skills DIR [DIR ...]` |
| No internet at the client | `python tools/package_skill.py --offline --fetch` → `dist/code-flow-visualizer-offline.zip` (Bootstrap, Mermaid and svg-pan-zoom included). Add `--offline` to `install_skill.py` / `build_plugin.py` too |

Every packaging command validates `SKILL.md` first (name, description length, YAML, referenced files). The version is in `VERSION`.

**Offline pages:** `python skill/code-flow-visualizer/scripts/fetch_vendor.py` once, then `render_page.py ... --offline` makes a page with no external requests.

## Supported technologies

Claude can trace code in any language it can read. The helper scripts add detection for the technologies below; that is what finds
entry points, lists routes with their full paths, and matches a frontend call to a backend route.

**Languages:** JavaScript, TypeScript, Python, Java, Kotlin, C#, Go, PHP, Ruby, Dart, plus Protocol Buffers (`.proto`) and GraphQL schemas.

**Backends**

| Technology | Entry points | Routes with full paths | Notes |
|---|---|---|---|
| ASP.NET Core | yes | yes | controllers (`[Route]`, `[controller]`) and minimal APIs (`MapGroup`, endpoint classes) |
| Spring Boot (Java, Kotlin) | yes | yes | class and method `@RequestMapping`, `@GetMapping` and friends |
| Django (+ DRF) | yes | yes | `path` / `re_path` / `url`, nested `include()`, `router.register` with methods from mixins |
| Ruby on Rails | yes | yes | `routes.rb`: `resources`, `namespace`, `scope`, nesting, `member`/`collection` |
| Laravel | yes | yes | `routes/*.php`, groups, `resource`, automatic `/api` prefix |
| Express | yes | yes | router graphs across files (`router.use` chains, default exports) |
| FastAPI / Flask | yes | yes | `include_router` / `register_blueprint` chains, prefixes from constants |
| NestJS | yes | yes | `@Controller` prefix and method decorators |
| GraphQL | schema fields | yes | SDL files and `gql` templates; resolvers in maps, NestJS, Spring, HotChocolate |
| gRPC | `.proto` services | yes | unary and streaming; implementations in Node, Java, C#, Go, Python |
| Go (`net/http`, gin, echo, chi) | yes | paths only | prefix of router groups is not resolved, so matches stay `likely` |

**Frontends**

| Technology | Screens and journeys | HTTP calls found |
|---|---|---|
| React (React Router, `createBrowserRouter`) | yes | `fetch`, axios, wrapper objects, generated clients |
| Next.js (App Router pages) | yes | as React |
| Angular (routes, guards) | yes | `HttpClient`, including interceptor base URLs |
| Flutter (`go_router`, named routes) | yes | `http`, `dio` |
| Vue, Svelte | via Claude reading the code | calls in `.vue` / `.svelte` files, wrapper objects such as `ApiService` |
| GraphQL clients (Apollo and similar) | n/a | `gql` operations in code and `.graphql` files (`@client` fields skipped) |
| gRPC-Web, Connect | n/a | generated clients (`new GreeterClient(...)`, `createPromiseClient(...)`) |

**Also**
- **Jobs and CLIs:** Celery tasks, Spring `@Scheduled` / `@KafkaListener` / `@RabbitListener`, Python commands (`click`-style, `__main__`), Go `main`.
- **Gateways:** nginx (`nginx.conf`) and Ocelot (JSON) rewrite rules, or an explicit `--gateway-prefix`.
- **Databases, queues and external services** are traced by Claude from the code and shown as `data` / `external` nodes (the examples include SQL Server, PostgreSQL, Oracle and RabbitMQ); there is no database-specific parser.
- **Output:** Bootstrap 5 and Mermaid (flowchart, sequence, state), light and dark, optional offline libraries.
- **Runs on:** Python 3.10+ (scripts), Node.js optional (diagram syntax check). Developed and tested on Windows; the scripts are plain Python.
- **Works in:** the Claude app (web and desktop) and Claude Code (CLI, IDE extensions, as a skill or a plugin).

## Frontend and backend in separate repos

```bash
python skill/code-flow-visualizer/scripts/match_api.py --frontend web=../web-app --backend api=../api
```
prints which frontend call reaches which backend route (`exact` or `likely`), calls with no route, and routes nobody calls.
Then trace the frontend flow and one flow per backend route it reaches, and link them:

```bash
python skill/code-flow-visualizer/scripts/stitch_flows.py flow.json --frontend web=../web-app --backend api=../api -o flow.json
```
This adds **Open sub-flow** on the call-site step and **Called from** on the backend entry step, and lists the calls whose route has no flow yet.
Flows can cite files from both repos (`"repo": "web"` on each node); validate with `validate_flow.py --repo web=../web-app --repo api=../api`.

| Side | Understood |
|---|---|
| Frontend calls | `fetch`, axios, Angular `HttpClient`, Dart `http`/`dio`, wrapper objects (`ApiService.get('articles', slug)`), generated TypeScript clients, GraphQL `gql` operations, gRPC-Web / Connect clients |
| Backend routes | Spring, ASP.NET (controllers and minimal APIs with `MapGroup`), Django (`urls.py`, `include()`, DRF routers), Rails (`routes.rb`), Laravel (`routes/*.php`), Express and FastAPI/Flask (router graphs), NestJS, GraphQL (schema and resolvers), gRPC (`.proto` services) |
| Prefixes | base URLs added by an interceptor, axios `baseURL` or an `API_URL` constant (`--base-url web=none` turns it off); gateways via `--gateway-config nginx.conf` (nginx or Ocelot JSON) or `--gateway-prefix orders=orders-svc` |

Routes whose prefix cannot be resolved are matched only as `likely`. Public repos to try, with measured results, are in
[`docs/TEST-REPOS.md`](docs/TEST-REPOS.md); a gateway demo is in `examples/cross-repo-gateway/`.

## Command reference

All scripts are in `skill/code-flow-visualizer/scripts/` and need only Python 3.10+ unless noted.

| Script | What it does |
|---|---|
| `find_entry_points.py <repo>` | lists routes, screens, commands and jobs to start from |
| `validate_flow.py flow.json --repo <repo>` | schema, graph and `file:line` + snippet checks |
| `render_page.py flow.json -o flow.html` | renders the page (`--repo` adds VS Code links, `--offline` inlines the libraries) |
| `check_mermaid.py flow.json` | parses the generated diagrams (needs Node; run `npm install` once in `scripts/mermaid-check/`) |
| `split_flow.py flow.json -o out.json` | splits flows over 40 nodes into linked sub-flows |
| `find_api_calls.py <frontend>` · `route_table.py <backend>` | the HTTP calls a frontend makes · the full routes of a backend |
| `match_api.py --frontend ... --backend ...` | matches calls to routes and reports the gaps |
| `stitch_flows.py flow.json ...` | links frontend and backend flows |

## Develop and test

```bash
pip install pytest
python -m pytest -q                      # unit and integration tests
python evals/run_evals.py --golden       # check the shipped example flows against the eval assertions
```
`evals/RESULTS.md` records how the skill performed on real repos (including what failed and what was changed); see
`evals/run_evals.py --outputs DIR` to score new runs. There is no CI workflow yet, so run both before a pull request.

## Status and limits

- The route and call detection is **heuristic static analysis**, not a full parser for each framework. When it cannot be sure it says `likely` or `inferred` instead of guessing; `docs/TEST-REPOS.md` lists the known gaps.
- The skill's trigger description has not been shown to improve with tuning (see `evals/RESULTS.md`); invoke it by name if Claude does not pick it up.
- Tested on the repos in `examples/` and the public repos in `docs/TEST-REPOS.md`; expect to meet code shapes it does not know yet.

## Repo layout

```
skill/code-flow-visualizer/   the skill: SKILL.md, page template, scripts, references
examples/                     sample apps, flows and rendered pages (single repo, cross-repo, gateway)
evals/                        eval prompts, checks, results, description-tuning tools
tests/                        pytest suite
tools/                        packaging: skill zip, plugin, installer
docs/                         PLAN.md (roadmap and tracker), TEST-REPOS.md
```

The flow format is documented in [`skill/code-flow-visualizer/references/flow-schema.md`](skill/code-flow-visualizer/references/flow-schema.md);
the plan and what is done is in [`docs/PLAN.md`](docs/PLAN.md).

## License

[MIT](LICENSE)
