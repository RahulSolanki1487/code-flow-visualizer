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


# ---- 7.1 Django -------------------------------------------------------------

def django_project(tmp_path):
    write(tmp_path, "proj/settings.py", "ROOT_URLCONF = 'proj.urls'\n")
    write(tmp_path, "proj/urls.py",
          '"""Examples in a docstring must be ignored:\n    url(r\'^ghost/$\', views.home)\n"""\n'
          "from django.urls import path, include\n"
          "urlpatterns = [\n"
          "    # path('commented/', views.nope),\n"
          "    path('admin/', admin.site.urls),\n"
          "    path('api/v1/', include('shop.urls')),\n"
          "    path('api/', include(('billing.urls', 'billing'), namespace='billing')),\n"
          "]\n")
    write(tmp_path, "shop/urls.py",
          "from django.urls import path, re_path, include\n"
          "from rest_framework.routers import DefaultRouter\n"
          "router = DefaultRouter()\n"
          "router.register(r'products', ProductViewSet)\n"
          "router.register('tags', TagViewSet)\n"
          "urlpatterns = [\n"
          "    path('', include(router.urls)),\n"
          "    path('orders/<int:pk>/', OrderView.as_view()),\n"
          "    path('orders/<slug:code>/items/', OrderItemsView.as_view()),\n"
          "    re_path(r'^search/(?P<term>\\w+)/?$', search),\n"
          "]\n")
    write(tmp_path, "shop/views.py",
          "class ProductViewSet(viewsets.ModelViewSet):\n    lookup_field = 'sku'\n\n"
          "class TagViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,\n                 viewsets.GenericViewSet):\n    pass\n")
    write(tmp_path, "billing/urls.py", "urlpatterns = [\n    path('invoices/', InvoiceList.as_view()),\n]\n")
    return tmp_path


def test_django_includes_routers_converters_and_regex(tmp_path):
    got = routes_of(django_project(tmp_path))
    paths = {p for _m, p in got}
    assert {"/admin", "/api/v1/orders/{pk}", "/api/v1/orders/{code}/items", "/api/v1/search/{term}", "/api/invoices"} <= paths
    assert ("GET", "/api/v1/products") in got and ("POST", "/api/v1/products") in got           # ModelViewSet
    assert {m for m, p in got if p == "/api/v1/products/{sku}"} == {"GET", "PUT", "PATCH", "DELETE"}   # lookup_field
    assert {m for m, p in got if p == "/api/v1/tags/{pk}"} == {"GET"}                           # read-only mixins
    assert ("POST", "/api/v1/tags") not in got
    assert all(r.prefix_known for r in got.values())


def test_django_ignores_docstring_examples_and_comments(tmp_path):
    paths = {p for _m, p in routes_of(django_project(tmp_path))}
    assert "/ghost" not in paths and "/commented" not in paths and "/" not in paths


def test_django_unreferenced_urls_files_get_an_unknown_prefix(tmp_path):
    write(tmp_path, "a/urls.py", "urlpatterns = [\n    path('x/', X.as_view()),\n]\n")
    write(tmp_path, "b/urls.py", "urlpatterns = [\n    path('y/', Y.as_view()),\n]\n")
    got = routes_of(tmp_path)
    assert not got[(None, "/x")].prefix_known and not got[(None, "/y")].prefix_known


def test_django_regex_to_path():
    import django_routes
    f = django_routes.regex_to_path
    assert f(r"^articles/(?P<slug>[-\w]+)/favorite/?$") == "articles/{slug}/favorite"
    assert f(r"^users/login/?$") == "users/login" and f("api/") == "api" and f(r"^$") == ""
    assert f("<int:pk>/detail/") == "{pk}/detail" and f(r"^v(\d+)/ping$") == "v{}/ping"
    assert f(r"^zoom/AZ$") == "zoom/AZ"  # a trailing capital Z is part of the path, not an anchor
