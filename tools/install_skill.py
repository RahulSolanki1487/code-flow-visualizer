#!/usr/bin/env python3
"""Copy the skill into the skills folder of an AI coding assistant (Claude Code or GitHub Copilot).

Usage:
    python tools/install_skill.py --personal              # ~/.claude/skills/code-flow-visualizer
    python tools/install_skill.py --project PATH          # PATH/.claude/skills/code-flow-visualizer
    python tools/install_skill.py --target copilot --personal        # ~/.copilot/skills/code-flow-visualizer
    python tools/install_skill.py --target copilot --project PATH    # PATH/.github/skills/code-flow-visualizer
    python tools/install_skill.py --personal --offline    # include vendored libraries
Add --dry-run to see the target without copying. An existing copy is replaced.
"""
import argparse
import shutil
import sys
from pathlib import Path

import skill_files


# Where each assistant looks for skills, relative to the home folder (personal) or a project root (project).
# Supporting another assistant means adding a row here.
TARGETS = {
    "claude": {"personal": Path(".claude/skills"), "project": Path(".claude/skills")},
    "copilot": {"personal": Path(".copilot/skills"), "project": Path(".github/skills")},
}


def target_dir(personal: bool, project: Path | None, home: Path | None = None, target: str = "claude") -> Path:
    folders = TARGETS[target]
    base = (home or Path.home()) / folders["personal"] if personal else Path(project) / folders["project"]
    return base / skill_files.SKILL.name


def install(target: Path, include_vendor: bool) -> int:
    if target.exists():
        shutil.rmtree(target)
    files = skill_files.collect(include_vendor=include_vendor)
    for path in files:
        dest = target / path.relative_to(skill_files.SKILL)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    return len(files)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--personal", action="store_true")
    where.add_argument("--project", type=Path)
    ap.add_argument("--target", choices=sorted(TARGETS), default="claude", help="which assistant to install for (default: claude)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    problems = skill_files.check_skill()
    if problems:
        print("Skill is invalid:\n  " + "\n  ".join(problems))
        return 1
    target = target_dir(args.personal, args.project, target=args.target)
    if args.dry_run:
        print(f"would install to {target}")
        return 0
    print(f"installed {install(target, args.offline)} files to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
