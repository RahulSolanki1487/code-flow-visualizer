#!/usr/bin/env python3
"""Check that the Mermaid diagram generated for each flow actually parses.

Optional step: needs Node.js and a one-time `npm install` in scripts/mermaid-check/.

Usage:
    python check_mermaid.py flow.json

Exit code: 0 = all diagrams parse, 1 = a syntax error, 2 = checker unavailable (Node or
dependencies missing; nothing was checked).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import render_page

CHECKER_DIR = Path(__file__).resolve().parent / "mermaid-check"


class CheckerUnavailable(Exception):
    pass


def diagrams(data: dict) -> list[dict]:
    return [{"id": f["id"], "text": render_page.build_flow(f)["mermaid"]} for f in data["flows"]]


def run_checker(items: list[dict], node: str | None = None) -> list[dict]:
    node = node or shutil.which("node")
    if not node:
        raise CheckerUnavailable("Node.js not found on PATH")
    if not (CHECKER_DIR / "node_modules" / "mermaid").is_dir():
        raise CheckerUnavailable(f"run `npm install` in {CHECKER_DIR} first")
    proc = subprocess.run([node, "parse.mjs"], cwd=CHECKER_DIR, input=json.dumps(items),
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise CheckerUnavailable(f"checker crashed: {proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow_json")
    args = ap.parse_args()
    data = json.loads(Path(args.flow_json).read_text(encoding="utf-8"))
    try:
        results = run_checker(diagrams(data))
    except CheckerUnavailable as exc:
        print(f"SKIPPED: {exc}")
        sys.exit(2)
    bad = [r for r in results if not r["ok"]]
    for r in bad:
        print(f"ERROR: flow '{r['id']}': {r['error']}")
    print(f"\n{len(results) - len(bad)}/{len(results)} diagram(s) parse")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
