#!/usr/bin/env python3
"""Run the eval assertions in evals.json against flow.json outputs.

Usage:
    python evals/run_evals.py --golden            # check the shipped example flows (harness self-test)
    python evals/run_evals.py --outputs DIR       # DIR/eval-<id>/flow.json produced by a model run

Each eval in evals.json lists machine-checkable `checks`; `golden` names a shipped example
flow (and its repo) that must pass them. Exit code 1 if any check fails; skipped checks
(e.g. Mermaid checker not installed) do not fail the run.
"""
import argparse
import json
import sys
from pathlib import Path

import flow_checks

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def locate(spec, args, ev):
    """Return (flow_json_path, repo_path|None) for this eval, or None if there is nothing to check."""
    if args.golden:
        g = ev.get("golden")
        return (ROOT / g["flow"], ROOT / g["repo"] if g.get("repo") else None) if g else None
    path = Path(args.outputs) / f"eval-{ev['id']}" / "flow.json"
    repo = ev.get("repo")
    return (path, ROOT / repo if repo else None) if path.is_file() else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--golden", action="store_true")
    mode.add_argument("--outputs")
    ap.add_argument("--evals", default=str(ROOT / "evals" / "evals.json"))
    args = ap.parse_args(argv)

    spec = load_json(Path(args.evals))
    failed = 0
    for ev in spec["evals"]:
        found = locate(spec, args, ev)
        if not found:
            print(f"[{ev['id']}] SKIP  no {'golden flow' if args.golden else 'output'}")
            continue
        flow_path, repo = found
        if repo is not None and not repo.is_dir():
            print(f"      note: repo {repo.name} not found next to this checkout; file:line checks skipped")
            repo = None
        results = flow_checks.run_checks(load_json(flow_path), repo, ev.get("checks", []))
        bad = [r for r in results if r[1] is False]
        failed += len(bad)
        print(f"[{ev['id']}] {'FAIL' if bad else 'PASS'}  {flow_path.name}")
        for name, passed, detail in results:
            tag = "skip" if passed is None else "ok  " if passed else "FAIL"
            print(f"      {tag} {name}: {detail}")
    print(f"\n{failed} failing check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
