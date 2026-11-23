"""Gateway rewrite rules: how a URL the frontend calls becomes the URL a backend serves.

A gateway or reverse proxy often sits between the two: the frontend calls `/orders-svc/api/v1/orders`,
the gateway strips `/orders-svc` and the orders service serves `/api/v1/orders`. A rule records that:
`upstream` is the prefix the frontend uses, `downstream` replaces it on the way to the backend.

Sources: explicit `NAME=/prefix` mappings (strip the prefix for backend NAME), nginx.conf
(`location /x/ { proxy_pass http://host:port/; }`) and Ocelot JSON (`UpstreamPathTemplate` /
`DownstreamPathTemplate` / `DownstreamHostAndPorts`). Rules found in a config name a host, which is
resolved to a backend by name or folder name.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LOCATION_RE = re.compile(r"location\s+(?:[=~^*]+\s+)?(/[^\s{]*)\s*\{(.*?)\}", re.S)
PROXY_PASS_RE = re.compile(r"proxy_pass\s+https?://([\w.-]+)(?::\d+)?(/[^;\s]*)?\s*;")


@dataclass
class GatewayRule:
    upstream: list[str]
    downstream: list[str] = field(default_factory=list)
    backend: str | None = None  # backend repo name once resolved
    host: str | None = None     # upstream host named in the config, before it is resolved
    source: str = ""


def segs(path: str) -> list[str]:
    return [s for s in (path or "").split("/") if s]


def explicit_rules(values) -> list[GatewayRule]:
    """['orders=/orders-svc'] -> strip /orders-svc for the backend named orders."""
    rules = []
    for v in values or []:
        name, sep, prefix = v.partition("=")
        if not sep or not name or not segs(prefix):
            raise ValueError(f"--gateway-prefix expects BACKEND=/prefix, got {v!r}")
        rules.append(GatewayRule(upstream=segs(prefix), backend=name, source="--gateway-prefix"))
    return rules


def parse_nginx(text: str, source: str = "nginx") -> list[GatewayRule]:
    rules = []
    for m in LOCATION_RE.finditer(text):
        location, body = m.group(1), m.group(2)
        proxy = PROXY_PASS_RE.search(body)
        if not proxy or not location.endswith("/") or len(segs(location)) == 0:
            continue
        host, uri = proxy.group(1), proxy.group(2)
        if uri is None:  # proxy_pass without a URI forwards the path unchanged: nothing to rewrite
            continue
        rules.append(GatewayRule(upstream=segs(location), downstream=segs(uri), host=host, source=source))
    return rules


def _literal_prefix(template: str) -> list[str]:
    out = []
    for s in segs(template):
        if "{" in s:
            break
        out.append(s)
    return out


def parse_ocelot(text: str, source: str = "ocelot") -> list[GatewayRule]:
    data = json.loads(text)
    rules = []
    for route in data.get("Routes") or data.get("ReRoutes") or []:
        hosts = route.get("DownstreamHostAndPorts") or []
        host = hosts[0].get("Host") if hosts else None
        up, down = _literal_prefix(route.get("UpstreamPathTemplate", "")), _literal_prefix(route.get("DownstreamPathTemplate", ""))
        if up != down:
            rules.append(GatewayRule(upstream=up, downstream=down, host=host, source=source))
    return rules


def load_config(path: Path) -> list[GatewayRule]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if text.lstrip().startswith("{"):
        return parse_ocelot(text, path.name)
    return parse_nginx(text, path.name)


def resolve_hosts(rules: list[GatewayRule], backends: list[tuple[str, Path]]) -> list[GatewayRule]:
    """Attach each config rule to a backend whose name or folder name matches the upstream host."""
    resolved = []
    for r in rules:
        if r.backend or not r.host:
            resolved.append(r)
            continue
        host = r.host.lower()
        for name, path in backends:
            candidates = {name.lower(), Path(path).resolve().name.lower()}
            if host in candidates or any(host.startswith(c + "-") or c.startswith(host + "-") for c in candidates):
                r.backend = name
                break
        resolved.append(r)
    return resolved


def apply_rule(rule: GatewayRule, url_segments: list[str]):
    """The URL segments the backend sees, or None when the rule does not apply to this URL."""
    n = len(rule.upstream)
    if len(url_segments) >= n and [s.lower() for s in url_segments[:n]] == [s.lower() for s in rule.upstream]:
        return list(rule.downstream) + url_segments[n:]
    return None
