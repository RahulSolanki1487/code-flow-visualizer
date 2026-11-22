# Eval results (2026-11-22)

One run per eval, each by a fresh subagent that read only `SKILL.md` and the target repo, scored by
`python evals/run_evals.py --outputs DIR`. Eval 5 (Spring Boot) was run later on springboot-react (see below).

## Round 1: skill as of the Phase 4 harness commit
| Eval | Target | Result | Notes |
|---|---|---|---|
| 1 | sample Express app | pass* | *Original check wanted the payment edge marked `inferred`; the call is a plain `fetch` with an env-var URL, so the check was replaced with "payment shown as an external node". |
| 2 | sample Express app (onboarding) | pass | 3 flows, 25 nodes |
| 3 | dotnet-starter-kit dashboard (React) | **fail** | 71% UI-level nodes, target 80% |
| 4 | dotnet-starter-kit outbox job | pass | sequence flow, PostgreSQL and RabbitMQ as external |
| 6 | dotnet-starter-kit Invoice | **fail** | state diagram had no forbidden transitions |
| 7 | Next.js eve-pocket-research | pass | |
| 8 | sample Angular app | **fail** | 47% UI-level nodes (19 nodes, 9 of them `logic`) |
| 9 | sample Flutter app | pass | |

## Fix
`SKILL.md` gained "Mode-specific rules": keep user mode at the screen/decision level, show forbidden
transitions in state diagrams as errors, and don't mark a hop `inferred` merely because a URL is config-driven.

## Round 2: tuned skill (evals 3, 6, 8 re-run)
| Eval | Result | Change |
|---|---|---|
| 3 | pass | 100% UI-level nodes |
| 6 | pass | 4 error nodes for forbidden transitions, idempotent no-ops |
| 8 | pass | 19 -> 10 nodes, 91% UI-level |

## Eval 5 (added later)
Run on `springboot-react`, `GET /v1/items/{itemId}` (the repo has no /customers). Passed first time: 16 nodes, DI wiring (component scan, constructor injection, Spring Data proxy, `@Transactional` proxy) marked inferred with notes, 404 and uncaught-error paths shown, Mermaid parses.

## Description trigger tuning (2026-11-22)
Ran skill-creator's `run_loop` (20 realistic queries: 10 should / 10 should-not, near-miss negatives, 3 runs each, 3 iterations, 12 train / 8 test) on Windows via `evals/trigger/run_loop_windows.py`.
- **The harness needed two Windows fixes** (it uses `select.select` on a pipe and launches the `claude.cmd` shim). An unpatched first run silently scored every query as "did not trigger", so its results were thrown away. The wrapper and a `sitecustomize.py` (needed because queries run in worker processes) fix both.
- **Result: no improvement.** Negatives never triggered (0/30). Positives almost never did: current description 2/30 runs, a shorter candidate 1/30. Three machine-proposed rewrites also scored the same (train 6/12, test 4/8), so the original description was kept.
- **Why this is not evidence the description is bad:** the harness only counts a trigger when the *first* tool call is the skill. For "trace this code" tasks Claude usually starts exploring the repo itself, and the queries name repos that are not present in the test directory. The setup cannot separate wording quality, so wording was not changed. A real test needs queries against a repo that exists in the working directory, or judging whether the skill is used at any point in the conversation.

## Caveats
- **No without-skill baseline.** A model without the skill would not produce `flow.json`, so these checks cannot score it. The comparison here is skill before vs. after tuning.
- **n = 1 per eval**, and round 2 was tuned on the same evals it was re-run on, so it may be over-fitted. New evals (and the unrun eval 5) are the real test.
- **The harness checks structure, not truth.** The eval 3 re-run agent itself reported one misattributed edge (root-tenant check drawn from the token call; it actually runs in `login()` after it returns), and all checks still passed.
