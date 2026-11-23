"""Phase 7: frontend base URLs and backend route coverage (Django, Rails, Laravel)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))

import find_api_calls  # noqa: E402
import match_api  # noqa: E402
import route_table  # noqa: E402


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def routes_of(repo: Path) -> dict:
    return {(r.method, r.path): r for r in route_table.collect_routes(repo)}


# ---- 7.0 frontend base URL ------------------------------------------------

def test_axios_baseurl_and_interceptor_bases_are_detected(tmp_path):
    write(tmp_path, "a/src/http.ts", "export const http = axios.create({ baseURL: 'https://example.com/api/v1/' });\n")
    write(tmp_path, "b/src/api.interceptor.ts", "const r = req.clone({ url: `https://api.realworld.show/api${req.url}` });\n")
    write(tmp_path, "c/src/http.ts", "axios.create({ baseURL: 'https://example.com' });\n")
    assert [d["base"] for d in find_api_calls.detect_base_urls(tmp_path / "a")] == ["/api/v1"]
    assert [d["base"] for d in find_api_calls.detect_base_urls(tmp_path / "b")] == ["/api"]
    assert find_api_calls.detect_base_urls(tmp_path / "c") == []  # a host alone is not a base path


def test_apply_base_url_prefixes_once():
    calls = [{"url": "/items", "unresolved": False}, {"url": "/api/items", "unresolved": False}, {"url": None, "unresolved": True}]
    out = find_api_calls.apply_base_url(calls, "api")
    assert [c["url"] for c in out] == ["/api/items", "/api/items", None]


def test_run_uses_detected_base_and_explicit_override(tmp_path):
    write(tmp_path, "fe/src/http.interceptor.ts", "intercept(req) { return next(req.clone({ url: `/api${req.url}` })); }\n")
    write(tmp_path, "fe/src/items.service.ts", "this.http.get('/items');\n")
    write(tmp_path, "be/Routes.cs", 'public class R {\n  void M() {\n    app.MapGet("/api/items", () => 1);\n  }\n}\n')
    fe, be = [("web", tmp_path / "fe")], [("api", tmp_path / "be")]
    detected = match_api.run(fe, be)
    assert [m["confidence"] for m in detected["matches"]] == ["exact"] and "detected at" in detected["notes"][0]
    off = match_api.run(fe, be, bases={"web": ""})
    assert off["matches"] == []   # without the base the call is `/items`, which cannot reach `/api/items`
    forced = match_api.run(fe, be, bases={"web": "api"})
    assert forced["matches"][0]["confidence"] == "exact" and "from --base-url" in forced["notes"][0]


def test_several_different_bases_are_reported_not_applied(tmp_path):
    write(tmp_path, "fe/src/a.ts", "axios.create({ baseURL: '/api' });\n")
    write(tmp_path, "fe/src/b.ts", "axios.create({ baseURL: '/admin' });\n")
    bases, notes = match_api.resolve_bases([("web", tmp_path / "fe")], None)
    assert bases == {} and "several base URLs" in notes[0]
