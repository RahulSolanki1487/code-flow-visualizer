#!/usr/bin/env python3
"""Regenerate the Claude Code marketplace files that are committed to the repository.

Usage:
    python tools/sync_marketplace.py            # rewrite plugins/code-flow-visualizer/ and .claude-plugin/marketplace.json
    python tools/sync_marketplace.py --check    # exit 1 if the committed copy differs from skill/ (used by CI)

Users install from the repository with:
    /plugin marketplace add RahulSolanki1487/code-flow-visualizer
    /plugin install code-flow-visualizer@code-flow-visualizer
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import build_plugin
import skill_files

NAME = "code-flow-visualizer"
OWNER = "RahulSolanki1487"
LICENSE_ID = "MIT"
PLUGINS_DIR = skill_files.ROOT / "plugins"
MARKETPLACE_FILE = skill_files.ROOT / ".claude-plugin" / "marketplace.json"


def marketplace_manifest() -> dict:
    return {
        "name": NAME,
        "owner": {"name": OWNER},
        "description": "Code Flow Visualizer: turn a slice of a codebase into one interactive HTML page.",
        "plugins": [{
            "name": NAME,
            "source": f"./plugins/{NAME}",
            "version": skill_files.version(),
            "description": "Trace how code runs, across frontend and backend repos, and render it as an interactive HTML flow page.",
        }],
    }


def marketplace_text() -> str:
    return json.dumps(marketplace_manifest(), indent=2) + "\n"


def build_plugin_into(out_root: Path) -> Path:
    return build_plugin.build(NAME, [], False, out_root=out_root, author=OWNER, license_id=LICENSE_ID)


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def differences() -> list[str]:
    """What the committed marketplace files lack, add or change compared with a fresh build."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh = _tree(build_plugin_into(Path(tmp)))
    committed_root = PLUGINS_DIR / NAME
    committed = _tree(committed_root) if committed_root.is_dir() else {}
    found = [f"missing: plugins/{NAME}/{p}" for p in fresh if p not in committed]
    found += [f"extra: plugins/{NAME}/{p}" for p in committed if p not in fresh]
    found += [f"changed: plugins/{NAME}/{p}" for p in fresh if p in committed and fresh[p] != committed[p]]
    current = MARKETPLACE_FILE.read_text(encoding="utf-8") if MARKETPLACE_FILE.exists() else None
    if current is None or json.loads(current) != marketplace_manifest():
        found.append(f"{MARKETPLACE_FILE.relative_to(skill_files.ROOT).as_posix()} is missing or out of date")
    return found


def sync() -> None:
    build_plugin_into(PLUGINS_DIR)
    MARKETPLACE_FILE.parent.mkdir(exist_ok=True)
    MARKETPLACE_FILE.write_text(marketplace_text(), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        found = differences()
        print("\n".join(found) if found else "marketplace files are up to date")
        if found:
            print("run: python tools/sync_marketplace.py", file=sys.stderr)
        return 1 if found else 0
    sync()
    print(f"wrote plugins/{NAME}/ and {MARKETPLACE_FILE.relative_to(skill_files.ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
