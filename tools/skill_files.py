"""Shared helpers for packaging the skill: validation and file collection."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "code-flow-visualizer"
VENDOR_DIR = SKILL / "assets" / "vendor"
EXCLUDED_DIRS = {"__pycache__", "node_modules"}  # node_modules: optional mermaid-check deps
EXCLUDED_NAMES = {".gitkeep"}
VENDOR_SUFFIXES = {".js", ".css"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION = 1024
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)
BLOCK_MARKERS = {">", ">-", "|", "|-"}


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _frontmatter_lines(skill_md: Path) -> list[str]:
    m = FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    return m.group(1).splitlines() if m else []


def read_frontmatter(skill_md: Path) -> dict:
    """Minimal YAML reader: `key: value` lines and `key: >-` / `|` block scalars (joined with spaces)."""
    fields: dict[str, str] = {}
    block_key = None
    for line in _frontmatter_lines(skill_md):
        if block_key is not None and line.startswith((" ", "\t")):
            fields[block_key] = (fields[block_key] + " " + line.strip()).strip()
            continue
        block_key = None
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if value in BLOCK_MARKERS:
            fields[key], block_key = "", key
        else:
            fields[key] = value
    return fields


def plain_scalar_problem(skill_md: Path) -> str | None:
    """Plain (unquoted) YAML scalars cannot contain ': ' or ' #'; Claude would then load empty metadata."""
    for line in _frontmatter_lines(skill_md):
        if line.startswith((" ", "\t")):
            continue
        key, sep, value = line.partition(":")
        value = value.strip()
        if sep and value and value[0] not in "\"'>|" and (": " in value or " #" in value):
            return f"frontmatter '{key.strip()}' has ': ' or ' #' in an unquoted value; quote it or use a '>-' block"
    return None


def check_skill(skill_dir: Path = SKILL) -> list[str]:
    """Return a list of problems that would stop the skill from loading or uploading."""
    problems = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ["SKILL.md is missing"]
    yaml_problem = plain_scalar_problem(skill_md)
    if yaml_problem:
        problems.append(yaml_problem)
    fm = read_frontmatter(skill_md)
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"name {name!r} must be lowercase letters/digits/hyphens, max 64 chars")
    if name and name != skill_dir.name:
        problems.append(f"name {name!r} does not match folder {skill_dir.name!r}")
    if not desc:
        problems.append("description is missing")
    elif len(desc) > MAX_DESCRIPTION:
        problems.append(f"description is {len(desc)} chars (max {MAX_DESCRIPTION})")
    body = skill_md.read_text(encoding="utf-8")
    for rel in re.findall(r"`((?:scripts|references|templates|assets)/[\w./-]+)`", body):
        if "<" in rel or rel.endswith("/"):
            continue
        if not (skill_dir / rel).exists():
            problems.append(f"SKILL.md mentions {rel} but it does not exist")
    return problems


def vendor_files(skill_dir: Path = SKILL) -> list[Path]:
    vendor = skill_dir / "assets" / "vendor"
    return sorted(p for p in vendor.glob("*") if p.suffix in VENDOR_SUFFIXES) if vendor.is_dir() else []


def collect(skill_dir: Path = SKILL, include_vendor: bool = False) -> list[Path]:
    """Files to ship. Vendor libraries are gitignored and only shipped in the offline build."""
    vendor = {p.resolve() for p in vendor_files(skill_dir)}
    out = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or EXCLUDED_DIRS.intersection(path.parts) or path.name in EXCLUDED_NAMES:
            continue
        if path.resolve() in vendor and not include_vendor:
            continue
        out.append(path)
    return out
