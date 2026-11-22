# Eval results (2026-11-22)

One run per eval, each by a fresh subagent that read only `SKILL.md` and the target repo, scored by
`python evals/run_evals.py --outputs DIR`. Eval 5 (Spring Boot) was not run: no Spring repo was available.

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

## Caveats
- **No without-skill baseline.** A model without the skill would not produce `flow.json`, so these checks cannot score it. The comparison here is skill before vs. after tuning.
- **n = 1 per eval**, and round 2 was tuned on the same evals it was re-run on, so it may be over-fitted. New evals (and the unrun eval 5) are the real test.
- **The harness checks structure, not truth.** The eval 3 re-run agent itself reported one misattributed edge (root-tenant check drawn from the token call; it actually runs in `login()` after it returns), and all checks still passed.
- `evals/trigger_queries.json` (does the skill trigger on the right prompts) has not been run through an optimizer.
