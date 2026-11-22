#!/usr/bin/env python3
"""Zip skill/code-flow-visualizer into dist/code-flow-visualizer.zip for upload."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "code-flow-visualizer"
DIST = ROOT / "dist"
EXCLUDED_DIRS = {"__pycache__", "node_modules"}  # node_modules: optional mermaid-check deps


def main():
    DIST.mkdir(exist_ok=True)
    out = DIST / "code-flow-visualizer.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and not EXCLUDED_DIRS.intersection(path.parts) and path.name != ".gitkeep":
                zf.write(path, Path("code-flow-visualizer") / path.relative_to(SKILL))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
