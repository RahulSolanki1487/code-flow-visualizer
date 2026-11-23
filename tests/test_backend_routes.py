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


# ---- 7.2 Rails --------------------------------------------------------------

def rails_routes(tmp_path, body, api_only=False):
    write(tmp_path, "config/routes.rb", "Rails.application.routes.draw do\n" + body + "end\n")
    if api_only:
        write(tmp_path, "config/application.rb", "config.api_only = true\n")
    return routes_of(tmp_path)


def test_rails_resources_only_except_param_and_nesting(tmp_path):
    got = rails_routes(tmp_path,
                       "  scope :api, defaults: { format: :json } do\n"
                       "    resources :articles, param: :slug, except: [:edit, :new] do\n"
                       "      resource :favorite, only: [:create, :destroy]\n"
                       "      resources :comments, only: [:create, :index, :destroy]\n"
                       "      get :feed, on: :collection\n"
                       "      post :publish, on: :member\n"
                       "    end\n"
                       "    resources :tags, only: [:index]\n"
                       "  end\n")
    keys = set(got)
    assert {("GET", "/api/articles"), ("POST", "/api/articles"), ("GET", "/api/articles/{slug}"), ("PUT", "/api/articles/{slug}"),
            ("PATCH", "/api/articles/{slug}"), ("DELETE", "/api/articles/{slug}")} <= keys
    assert ("GET", "/api/articles/new") not in keys and ("GET", "/api/articles/{slug}/edit") not in keys
    assert {("POST", "/api/articles/{article_slug}/favorite"), ("DELETE", "/api/articles/{article_slug}/favorite"),
            ("GET", "/api/articles/{article_slug}/comments"), ("POST", "/api/articles/{article_slug}/comments"),
            ("DELETE", "/api/articles/{article_slug}/comments/{id}")} <= keys
    assert ("GET", "/api/articles/feed") in keys and ("POST", "/api/articles/{slug}/publish") in keys
    assert ("GET", "/api/tags") in keys and ("POST", "/api/tags") not in keys


def test_rails_singular_resource_namespace_verbs_root_mount_and_match(tmp_path):
    got = rails_routes(tmp_path,
                       "  root 'home#index'\n"
                       "  namespace :admin do\n"
                       "    namespace :v2 do\n"
                       "      resource :profile, only: [:show, :update]\n"
                       "    end\n"
                       "  end\n"
                       "  get '/health', to: 'health#show'\n"
                       "  post 'login' => 'sessions#create'\n"
                       "  match 'hook', to: 'hooks#run', via: [:get, :post]\n"
                       "  mount Sidekiq::Web => '/sidekiq'\n"
                       "  resources :photos, :albums, only: :index\n")
    keys = set(got)
    assert {("GET", "/"), ("GET", "/admin/v2/profile"), ("PUT", "/admin/v2/profile"), ("PATCH", "/admin/v2/profile"),
            ("GET", "/health"), ("POST", "/login"), ("GET", "/hook"), ("POST", "/hook"), (None, "/sidekiq"),
            ("GET", "/photos"), ("GET", "/albums")} <= keys
    assert ("GET", "/admin/v2/profile/new") not in keys   # only: [:show, :update]


def test_rails_api_only_apps_have_no_new_and_edit_routes(tmp_path):
    plain = rails_routes(tmp_path / "plain", "  resources :orders\n")
    api = rails_routes(tmp_path / "api", "  resources :orders\n", api_only=True)
    assert ("GET", "/orders/new") in plain and ("GET", "/orders/{id}/edit") in plain
    assert ("GET", "/orders/new") not in api and ("GET", "/orders/{id}/edit") not in api and ("GET", "/orders") in api


def test_rails_ruby_blocks_comments_and_continuations_do_not_unbalance_nesting(tmp_path):
    got = rails_routes(tmp_path,
                       "  # resources :ghosts\n"
                       "  if Rails.env.development?\n"
                       "    resources :dev_tools, only: :index\n"
                       "  end\n"
                       "  resources :users,\n"
                       "            only: [:index, :show] do   # trailing comment\n"
                       "    resources :posts, only: :index\n"
                       "  end\n"
                       "  resources :after, only: :index\n")
    keys = set(got)
    assert ("GET", "/dev_tools") in keys and ("GET", "/users/{user_id}/posts") in keys
    assert ("GET", "/after") in keys and ("GET", "/ghosts") not in keys   # `after` is at top level, not nested


def test_rails_devise_for_adds_assumed_session_routes(tmp_path):
    got = rails_routes(tmp_path, "  scope :api do\n    devise_for :users, path_names: { sign_in: :login }\n  end\n")
    assert {("POST", "/api/users/login"), ("DELETE", "/api/users/sign_out"), ("POST", "/api/users")} <= set(got)
    assert "assumed" in got[("POST", "/api/users/login")].action


# ---- call finder fixes found with the RealWorld Angular app --------------------

def test_formatter_style_chains_and_concatenated_urls(tmp_path):
    write(tmp_path, "src/profile.service.ts",
          "follow(username: string) {\n  return this.http\n    .post<{ profile: Profile }>('/profiles/' + username + '/follow', {})\n}\n"
          "get(username: string) {\n  return this.http.get('/profiles/' + username);\n}\n"
          "put(slug: string) {\n  return this.http\n    .put<{ article: A }>(`/articles/${slug}`, {});\n}\n"
          "all() {\n  return this.http.get('/items' + (id ? '/' + id : ''));\n}\n")
    got = [(c["methods"], c["url"], c["optional_suffix"]) for c in find_api_calls.scan(tmp_path)]
    assert got == [(["POST"], "/profiles/{}/follow", False), (["GET"], "/profiles/{}", False),
                   (["PUT"], "/articles/{}", False), (["GET"], "/items", True)]


# ---- 7.3 Laravel --------------------------------------------------------------

def laravel_repo(tmp_path, api_php, provider=None, bootstrap=None, web_php=None):
    write(tmp_path, "routes/api.php", "<?php\n" + api_php)
    if web_php is not None:
        write(tmp_path, "routes/web.php", "<?php\n" + web_php)
    if provider:
        write(tmp_path, "app/Providers/RouteServiceProvider.php", provider)
    if bootstrap:
        write(tmp_path, "bootstrap/app.php", bootstrap)
    return routes_of(tmp_path)


def test_laravel_api_prefix_groups_match_and_resources(tmp_path):
    got = laravel_repo(
        tmp_path,
        "// Route::get('ghost', 'X@y');\n"
        "Route::group(['namespace' => 'Api'], function () {\n"
        "    Route::post('users/login', 'AuthController@login');\n"
        "    Route::match(['put', 'patch'], 'user', 'UserController@update');\n"
        "    Route::get('profiles/{user}', 'ProfileController@show');\n"
        "    Route::get('maybe/{opt?}', 'M@show');\n"
        "    Route::resource('articles', 'ArticleController', ['except' => ['create', 'edit']]);\n"
        "    Route::resource('articles/{article}/comments', 'CommentController', ['only' => ['index', 'store', 'destroy']]);\n"
        "});\n"
        "Route::prefix('v2')->middleware('auth:api')->group(function () {\n"
        "    Route::apiResource('orders', OrderController::class)->only(['index', 'show']);\n"
        "    Route::group(['prefix' => 'admin'], function () {\n"
        "        Route::delete('users/{id}', 'U@destroy');\n"
        "    });\n"
        "});\n"
        "Route::any('webhook', 'W@run');\n",
        provider="Route::prefix('api')->middleware('api')->group(base_path('routes/api.php'));\n")
    keys = set(got)
    assert {("POST", "/api/users/login"), ("PUT", "/api/user"), ("PATCH", "/api/user"), ("GET", "/api/profiles/{user}"),
            ("GET", "/api/maybe/{opt}"), (None, "/api/webhook")} <= keys
    assert {("GET", "/api/articles"), ("POST", "/api/articles"), ("GET", "/api/articles/{article}"), ("PUT", "/api/articles/{article}"),
            ("DELETE", "/api/articles/{article}")} <= keys
    assert ("GET", "/api/articles/create") not in keys and ("GET", "/api/articles/{article}/edit") not in keys
    assert {("GET", "/api/articles/{article}/comments"), ("POST", "/api/articles/{article}/comments"),
            ("DELETE", "/api/articles/{article}/comments/{comment}")} <= keys
    assert {("GET", "/api/v2/orders"), ("GET", "/api/v2/orders/{order}")} <= keys and ("POST", "/api/v2/orders") not in keys  # apiResource ->only
    assert ("DELETE", "/api/v2/admin/users/{id}") in keys           # nested groups add up
    assert not any("ghost" in p for _m, p in keys)                  # commented-out route


def test_laravel_prefix_sources_provider_bootstrap_and_defaults(tmp_path):
    assert ("GET", "/api/ping") in laravel_repo(tmp_path / "default", "Route::get('ping', 'P@x');\n")                      # Laravel's default
    custom = laravel_repo(tmp_path / "provider", "Route::get('ping', 'P@x');\n",
                          provider="Route::prefix('rest/v1')->group(base_path('routes/api.php'));\n")
    assert ("GET", "/rest/v1/ping") in custom
    laravel11 = laravel_repo(tmp_path / "l11", "Route::get('ping', 'P@x');\n",
                             bootstrap="->withRouting(web: __DIR__.'/../routes/web.php', api: __DIR__.'/../routes/api.php', apiPrefix: 'service')\n",
                             web_php="Route::get('home', 'H@x');\n")
    assert ("GET", "/service/ping") in laravel11 and ("GET", "/home") in laravel11


# ---- 7.4 report hint and Spring method-level RequestMapping -------------------------

def test_spring_method_level_request_mapping_with_a_verb_attribute(tmp_path):
    write(tmp_path, "UsersApi.java",
          '@RestController\n@RequestMapping(path = "/accounts")\npublic class UsersApi {\n'
          '  @RequestMapping(path = "/login", method = POST)\n  public ResponseEntity login() {}\n'
          '  @RequestMapping(value = "/{id}", method = RequestMethod.DELETE)\n  public void remove() {}\n}\n')
    assert {("POST", "/accounts/login"), ("DELETE", "/accounts/{id}")} <= set(routes_of(tmp_path))


def test_a_base_url_that_hides_every_match_is_diagnosed(tmp_path):
    write(tmp_path, "fe/src/http.interceptor.ts", "intercept(req) { return next(req.clone({ url: `/api${req.url}` })); }\n")
    write(tmp_path, "fe/src/s.ts", "this.http.get('/items');\nthis.http.post('/items', {});\nthis.http.get('/items/' + id);\n")
    write(tmp_path, "be/ItemsController.cs",
          '[Route("items")]\npublic class ItemsController : ControllerBase\n{\n  [HttpGet]\n  public IActionResult All() { }\n'
          '  [HttpPost]\n  public IActionResult Add() { }\n  [HttpGet("{id}")]\n  public IActionResult One(int id) { }\n}\n')
    result = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")])
    assert result["matches"] == []
    assert any("HINT" in n and "3 of 3 calls would match" in n for n in result["notes"])
    ok = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")], bases={"web": ""})
    assert len({m["call"]["line"] for m in ok["matches"]}) == 3 and not any("HINT" in n for n in ok["notes"])
