"""Tests for the packaging tools (skill validation, zip, plugin bundle, installer)."""
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_plugin  # noqa: E402
import install_skill  # noqa: E402
import package_skill  # noqa: E402
import skill_files  # noqa: E402


def make_skill(tmp_path, name="demo-skill", description="Does a thing.", body="Body"):
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8")
    return d


def test_real_skill_is_valid():
    assert skill_files.check_skill() == []


def test_check_skill_flags_problems(tmp_path):
    assert any("max 1024" in p for p in skill_files.check_skill(make_skill(tmp_path, description="x" * 1100)))
    bad = tmp_path / "other"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: Wrong_Name\ndescription: d\n---\n", encoding="utf-8")
    problems = skill_files.check_skill(bad)
    assert any("lowercase" in p for p in problems) and any("does not match folder" in p for p in problems)
    assert skill_files.check_skill(tmp_path / "missing") == ["SKILL.md is missing"]


def test_check_skill_flags_dangling_file_reference(tmp_path):
    d = make_skill(tmp_path, body="See `references/nope.md` for more.")
    assert any("references/nope.md" in p for p in skill_files.check_skill(d))


def test_collect_excludes_vendor_and_junk_unless_offline(tmp_path):
    d = make_skill(tmp_path)
    (d / "assets" / "vendor").mkdir(parents=True)
    (d / "assets" / "vendor" / "lib.min.js").write_text("x", encoding="utf-8")
    (d / "assets" / "vendor" / ".gitkeep").write_text("", encoding="utf-8")
    (d / "node_modules").mkdir()
    (d / "node_modules" / "m.js").write_text("x", encoding="utf-8")
    names = lambda files: {p.relative_to(d).as_posix() for p in files}  # noqa: E731
    assert names(skill_files.collect(d)) == {"SKILL.md"}
    assert names(skill_files.collect(d, include_vendor=True)) == {"SKILL.md", "assets/vendor/lib.min.js"}


def test_zip_has_skill_folder_root_and_no_node_modules(tmp_path):
    out = tmp_path / "s.zip"
    package_skill.build_zip(out, skill_files.collect())
    names = zipfile.ZipFile(out).namelist()
    assert "code-flow-visualizer/SKILL.md" in names
    assert all(n.startswith("code-flow-visualizer/") for n in names)
    assert not any("node_modules" in n or "__pycache__" in n for n in names)


def test_plugin_bundle_layout_and_extra_skills(tmp_path):
    extra = make_skill(tmp_path, name="team-skill")
    dest = build_plugin.build("acme", [extra], include_vendor=False, out_root=tmp_path / "out", author="Acme")
    manifest = json.loads((dest / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "acme" and manifest["version"] == skill_files.version()
    assert manifest["author"] == {"name": "Acme"}
    assert (dest / "skills" / "code-flow-visualizer" / "SKILL.md").is_file()
    assert (dest / "skills" / "team-skill" / "SKILL.md").is_file()
    assert "team-skill" in manifest["description"]


def test_plugin_rejects_invalid_or_duplicate_skill(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        build_plugin.build("x", [make_skill(tmp_path, description="x" * 1100)], False, tmp_path / "o")
    dup = tmp_path / "dup" / "code-flow-visualizer"
    dup.parent.mkdir()
    shutil.copytree(skill_files.SKILL, dup, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    with pytest.raises(SystemExit):
        build_plugin.build("x", [dup], False, tmp_path / "o2")


def test_install_targets_and_copy(tmp_path):
    assert install_skill.target_dir(True, None, home=tmp_path) == tmp_path / ".claude" / "skills" / "code-flow-visualizer"
    assert install_skill.target_dir(True, None, home=tmp_path, target="copilot") == tmp_path / ".copilot" / "skills" / "code-flow-visualizer"
    assert install_skill.target_dir(False, tmp_path / "proj", target="copilot") == tmp_path / "proj" / ".github" / "skills" / "code-flow-visualizer"
    assert install_skill.target_dir(False, tmp_path / "proj") == tmp_path / "proj" / ".claude" / "skills" / "code-flow-visualizer"
    target = tmp_path / "t" / "code-flow-visualizer"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("old", encoding="utf-8")
    count = install_skill.install(target, include_vendor=False)
    assert count >= 10 and (target / "SKILL.md").is_file() and not (target / "stale.txt").exists()


def test_cdn_versions_are_pinned():
    sys.path.insert(0, str(skill_files.SKILL / "scripts"))
    import render_page
    for url in render_page.CDN.values():
        assert "@" in url.split("/npm/")[1].split("/")[0] and not url.split("@")[1].split("/")[0].isalpha()
    assert "mermaid@11.17.2" in render_page.CDN["mermaid_js"]


def test_unquoted_colon_in_description_is_caught(tmp_path):
    """Regression: a description with ': ' parsed as empty metadata in Claude (found by `claude plugin validate`)."""
    d = make_skill(tmp_path, description='Use when asked "what happens when X: now"')
    assert any("unquoted value" in p for p in skill_files.check_skill(d))
    ok = tmp_path / "ok-skill"
    ok.mkdir()
    (ok / "SKILL.md").write_text("---\nname: ok-skill\ndescription: >-\n  Has a colon: here\n  and wraps.\n---\nBody\n", encoding="utf-8")
    assert skill_files.check_skill(ok) == []
    assert skill_files.read_frontmatter(ok / "SKILL.md")["description"] == "Has a colon: here and wraps."


def test_committed_marketplace_copy_matches_the_skill():
    """The plugin served by `/plugin marketplace add` is a generated copy; fail when skill/ changed and it was not regenerated."""
    import sync_marketplace
    assert sync_marketplace.differences() == [], "run: python tools/sync_marketplace.py"


def test_marketplace_points_at_the_committed_plugin_and_current_version():
    import sync_marketplace
    manifest = sync_marketplace.marketplace_manifest()
    entry = manifest["plugins"][0]
    assert (skill_files.ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()
    assert entry["version"] == skill_files.version()
