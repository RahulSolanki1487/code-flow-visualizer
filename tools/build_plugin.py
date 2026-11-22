#!/usr/bin/env python3
"""Build a Claude Code plugin that bundles code-flow-visualizer (and optionally other team skills).

Usage:
    python tools/build_plugin.py                              # dist/plugin/code-flow-visualizer/
    python tools/build_plugin.py --extra-skills DIR [DIR ...] # also bundle other skill folders
    python tools/build_plugin.py --name acme-skills --offline # custom plugin name, offline libraries
    python tools/build_plugin.py --zip                        # also write <name>-<version>.zip

Layout produced:
    <name>/.claude-plugin/plugin.json
    <name>/skills/<skill-name>/SKILL.md ...
Install it with `claude --plugin-dir dist/plugin/<name>` to try it, or publish it in a marketplace.
"""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

import skill_files

DIST = skill_files.ROOT / "dist" / "plugin"


def plugin_manifest(name: str, skills: list[str], author: str | None = None, license_id: str | None = None) -> dict:
    manifest = {
        "name": name,
        "version": skill_files.version(),
        "description": "Trace how code runs and render it as an interactive HTML flow page. Bundles: " + ", ".join(skills),
    }
    if author:
        manifest["author"] = {"name": author}
    if license_id:
        manifest["license"] = license_id
    return manifest


def copy_skill(src: Path, dest_root: Path, include_vendor: bool) -> str:
    problems = skill_files.check_skill(src)
    if problems:
        raise SystemExit(f"skill {src.name} is invalid:\n  " + "\n  ".join(problems))
    for path in skill_files.collect(src, include_vendor):
        target = dest_root / src.name / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return src.name


def build(name: str, extra: list[Path], include_vendor: bool, out_root: Path = DIST, author: str | None = None,
          license_id: str | None = None) -> Path:
    dest = out_root / name
    if dest.exists():
        shutil.rmtree(dest)
    skills_dir = dest / "skills"
    names = [copy_skill(skill_files.SKILL, skills_dir, include_vendor)]
    for src in extra:
        if src.name in names:
            raise SystemExit(f"duplicate skill name {src.name!r}")
        names.append(copy_skill(src, skills_dir, False))
    manifest = dest / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(plugin_manifest(name, names, author, license_id), indent=2) + "\n", encoding="utf-8")
    return dest


def zip_dir(src: Path) -> Path:
    out = src.parent / f"{src.name}-{skill_files.version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="code-flow-visualizer")
    ap.add_argument("--extra-skills", nargs="*", default=[], type=Path)
    ap.add_argument("--offline", action="store_true", help="include vendored libraries (run package_skill.py --offline --fetch first)")
    ap.add_argument("--author", help="author name for plugin.json (optional; the plugin validator warns without it)")
    ap.add_argument("--license", dest="license_id", help="SPDX id for plugin.json, e.g. MIT")
    ap.add_argument("--zip", action="store_true")
    args = ap.parse_args(argv)
    if args.offline and len(skill_files.vendor_files()) < 4:
        raise SystemExit("offline libraries missing; run `python tools/package_skill.py --offline --fetch` first")
    dest = build(args.name, args.extra_skills, args.offline, author=args.author, license_id=args.license_id)
    print(f"wrote {dest}")
    if args.zip:
        print(f"wrote {zip_dir(dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
