"""Repo roots for flows that span more than one repository (frontend + backend).

`--repo PATH` (one unnamed repo) keeps working. For several repos name them: `--repo web=../web-app
--repo api=../api`, and give each node in flow.json a `"repo": "web"` / `"repo": "api"` field.
"""
from pathlib import Path


def parse_repo_args(values) -> dict:
    """['web=../web', 'api=../api'] or ['../one'] -> {name|None: Path}."""
    roots = {}
    for v in values or []:
        name, sep, path = v.partition("=")
        if sep and name and "/" not in name and "\\" not in name and ":" not in name:
            roots[name] = Path(path)
        else:
            roots[None] = Path(v)
    return roots


def normalize_roots(repos) -> dict:
    """Accept None, a single Path, or a {name|None: Path} mapping."""
    if repos is None:
        return {}
    if isinstance(repos, dict):
        return repos
    return {None: Path(repos)}


def root_for(roots: dict, node: dict):
    """Return (root|None, problem|None) for a node. problem is a message when the node cannot be resolved."""
    name = node.get("repo")
    if name:
        if name in roots:
            return roots[name], None
        if None in roots and len(roots) == 1:
            return roots[None], None  # single unnamed repo: the node's label is informational
        return None, f"unknown repo '{name}' (known: {', '.join(sorted(k for k in roots if k)) or 'none'})"
    if None in roots:
        return roots[None], None
    if len(roots) == 1:
        return next(iter(roots.values())), None
    if roots:
        return None, "node needs a 'repo' field because several repos were given"
    return None, None
