# Changelog

All notable changes to this project are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).
The version number lives in `VERSION`; `python tools/sync_marketplace.py` copies it into the plugin and marketplace files.

## [0.6.0] - 2026-11-27

### Added
- **Cross-repo linking:** follow a request from a frontend screen to the backend route it calls. Includes an API call finder, a route table, a matcher and a stitcher that links the flows, plus gateway support and demo repos.
- **Backend route coverage:** Django (`urls.py`, `include()` prefixes, DRF routers), Rails, Laravel, Spring method-level mappings, FastAPI/Flask router graphs, Express routers, GraphQL and gRPC, as routes and as calls.
- **Frontend call detection:** axios `baseURL` and interceptor bases, HTTP wrapper services, `API_URL` constants, multi-line call chains and `+` concatenation, and a `--base-url` override.
- **"How it works" box** on every diagram page: the flow in plain sentences that name each diagram step, with links to the steps. The validator checks that every step is mentioned.
- **Horizontal / Vertical toggle** for flowcharts and state diagrams; the choice is remembered in the browser.
- **GitHub Copilot** install target, and an assistant-neutral `SKILL.md`.
- **Claude Code marketplace** (`/plugin marketplace add RahulSolanki1487/code-flow-visualizer`).
- **CI** workflow (tests, golden evals, package check) and a ruleset for `main`.
- README: supported technologies and a "What you can ask" section.

### Fixed
- Switching flows in the sidebar now returns to the Diagram tab and drops stale renders.

## [0.5.0]

Packaging and distribution: validated skill zip, plugin bundle, installer and offline build. Earlier work covered the prototype, accuracy checks on real repositories, state diagrams, VS Code links, user-flow modes and the eval harness.
