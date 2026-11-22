#!/usr/bin/env python3
"""Zip skill/code-flow-visualizer for upload (Claude app: Settings -> Capabilities -> Skills).

Usage:
    python tools/package_skill.py                 # dist/code-flow-visualizer.zip (CDN libraries)
    python tools/package_skill.py --offline       # dist/code-flow-visualizer-offline.zip (libraries inlined)
    python tools/package_skill.py --offline --fetch   # download the libraries first if missing

The skill is validated first; packaging stops if SKILL.md is invalid.
"""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

import skill_files

DIST = skill_files.ROOT / "dist"
REQUIRED_VENDOR = 4  # bootstrap css+js, mermaid, svg-pan-zoom


def build_zip(out: Path, files: list[Path], skill_dir: Path = skill_files.SKILL) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, Path(skill_dir.name) / path.relative_to(skill_dir))


def ensure_vendor(fetch: bool) -> None:
    if len(skill_files.vendor_files()) >= REQUIRED_VENDOR:
        return
    if not fetch:
        raise SystemExit("offline libraries missing in assets/vendor/. Re-run with --fetch (downloads from the CDN).")
    subprocess.run([sys.executable, str(skill_files.SKILL / "scripts" / "fetch_vendor.py")], check=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="include the vendored libraries")
    ap.add_argument("--fetch", action="store_true", help="with --offline: download the libraries if missing")
    args = ap.parse_args(argv)

    problems = skill_files.check_skill()
    if problems:
        print("Skill is invalid:\n  " + "\n  ".join(problems))
        return 1
    if args.offline:
        ensure_vendor(args.fetch)
    out = DIST / ("code-flow-visualizer-offline.zip" if args.offline else "code-flow-visualizer.zip")
    files = skill_files.collect(include_vendor=args.offline)
    build_zip(out, files)
    print(f"wrote {out} ({len(files)} files, {out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
