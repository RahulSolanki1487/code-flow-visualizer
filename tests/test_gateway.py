"""Tests for gateway rewrite rules and their use by the matcher."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))

import gateway_rules  # noqa: E402
import match_api  # noqa: E402
import route_table  # noqa: E402

NGINX = """
server {
  location /orders-svc/ { proxy_pass http://orders-api:3000/; }
  location /legacy/    { proxy_pass http://old-app:8080/v2/; }
  location /keep/      { proxy_pass http://keeps-prefix:80; }
  location /api        { proxy_pass http://no-trailing-slash/; }
  location / { root /html; }
}
"""
OCELOT = '{"Routes": [{"UpstreamPathTemplate": "/shop/{everything}", "DownstreamPathTemplate": "/api/v1/{everything}",' \
         ' "DownstreamHostAndPorts": [{"Host": "orders-api", "Port": 5000}]},' \
         '{"UpstreamPathTemplate": "/same/{x}", "DownstreamPathTemplate": "/same/{x}", "DownstreamHostAndPorts": [{"Host": "h"}]}]}'


def call(url, methods=("GET",), **flags):
    return {"repo": "web", "file": "a.ts", "line": 1, "callee": "http.get", "methods": list(methods), "url": url, "dynamic": False,
            "base_unknown": False, "optional_suffix": False, "unresolved": False, **flags}


def route(method, path, repo, known=True):
    return route_table.Route(method, path, "R.js", 1, "x", "", known, repo)


def test_nginx_rules_strip_or_rewrite_and_skip_the_rest():
    rules = gateway_rules.parse_nginx(NGINX)
    assert [(r.upstream, r.downstream, r.host) for r in rules] == [
        (["orders-svc"], [], "orders-api"),      # trailing slash on proxy_pass: prefix stripped
        (["legacy"], ["v2"], "old-app"),         # replaced by /v2/
    ]  # no URI on proxy_pass = path forwarded unchanged; location /api without trailing slash is skipped


def test_ocelot_rules_use_the_literal_prefix_and_skip_identity_routes():
    rules = gateway_rules.parse_ocelot(OCELOT)
    assert [(r.upstream, r.downstream, r.host) for r in rules] == [(["shop"], ["api", "v1"], "orders-api")]


def test_hosts_resolve_to_backends_by_name_or_folder(tmp_path):
    rules = gateway_rules.parse_nginx(NGINX)
    resolved = gateway_rules.resolve_hosts(rules, [("orders", tmp_path / "orders-api"), ("other", tmp_path / "other")])
    assert [r.backend for r in resolved] == ["orders", None]  # old-app matches nothing
    by_prefix = gateway_rules.resolve_hosts(gateway_rules.parse_nginx(NGINX), [("orders", tmp_path / "x")])
    assert by_prefix[0].backend == "orders"  # host orders-api starts with the backend name


def test_explicit_rules_validate_input():
    r = gateway_rules.explicit_rules(["orders=orders-svc", "billing=/billing-svc"])
    assert [(x.backend, x.upstream) for x in r] == [("orders", ["orders-svc"]), ("billing", ["billing-svc"])]
    with pytest.raises(ValueError):
        gateway_rules.explicit_rules(["nonsense"])


def test_apply_rule_is_case_insensitive_and_only_on_prefix():
    rule = gateway_rules.GatewayRule(upstream=["orders-svc"], downstream=["api"])
    assert gateway_rules.apply_rule(rule, ["Orders-SVC", "v1", "orders"]) == ["api", "v1", "orders"]
    assert gateway_rules.apply_rule(rule, ["v1", "orders-svc"]) is None


def test_rule_makes_a_prefixed_call_match_only_its_own_backend():
    rules = [gateway_rules.GatewayRule(upstream=["orders-svc"], backend="orders", source="nginx.conf")]
    c = call("/orders-svc/api/v1/orders")
    assert match_api.match_call(c, route("GET", "/api/v1/orders", "orders"))is None            # no rule: no match
    hit = match_api.match_call(c, route("GET", "/api/v1/orders", "orders"), rules)
    assert hit[0] == "exact" and "nginx.conf" in hit[2]
    assert match_api.match_call(c, route("GET", "/api/v1/orders", "billing"), rules) is None  # another backend's route


def test_a_rule_must_explain_the_whole_difference():
    rules = [gateway_rules.GatewayRule(upstream=["orders-svc"], backend="orders")]
    c = call("/orders-svc/extra/api/v1/orders")
    # known prefix: the leftover /extra segment is unexplained, so even the rewritten URL does not match
    assert match_api.match_call(c, route("GET", "/api/v1/orders", "orders", known=True), rules) is None
    # unknown prefix: only the plain (guessing) comparison fits, so it is "likely" and not credited to the rule
    hit = match_api.match_call(c, route("GET", "/api/v1/orders", "orders", known=False), rules)
    assert hit[0] == "likely" and hit[2] == ""


def test_cli_with_nginx_config_and_with_explicit_prefixes(capsys):
    base = ROOT / "examples" / "cross-repo-gateway"
    common = ["--frontend", f"web={base / 'web'}", "--backend", f"orders={base / 'orders-api'}", "--backend", f"billing={base / 'billing-api'}", "--json"]
    import json
    for extra in (["--gateway-config", str(base / "gateway" / "nginx.conf")], ["--gateway-prefix", "orders=orders-svc", "--gateway-prefix", "billing=billing-svc"]):
        capsys.readouterr()
        assert match_api.main(common + extra) == 0
        result = json.loads(capsys.readouterr().out)
        assert {m["call"]["url"] for m in result["matches"]} == {
            "/orders-svc/api/v1/orders", "/orders-svc/api/v1/orders/{}", "/billing-svc/api/v1/invoices/{}", "/billing-svc/api/v1/payments"}
        assert [c["url"] for c in result["unmatched_calls"]] == ["/shipping-svc/api/v1/tracking/{}"]  # no such service
        assert sorted(r["path"] for r in result["uncalled_routes"]) == ["/api/v1/orders/:id", "/api/v1/refunds"]
    capsys.readouterr()
    match_api.main(common)  # without any gateway information nothing matches
    assert json.loads(capsys.readouterr().out)["matches"] == []
