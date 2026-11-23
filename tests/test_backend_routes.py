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


# ---- 7.5 FastAPI / Flask router graphs and generated clients -------------------------

def fastapi_project(tmp_path):
    write(tmp_path, "app/core/config.py", 'class Settings:\n    API_V1_STR: str = "/api/v1"\n    PROJECT: str = "demo"\n')
    write(tmp_path, "app/main.py",
          "from fastapi import FastAPI\nfrom app.api.main import api_router\nfrom app.core.config import settings\n"
          "app = FastAPI(title='x')\n"
          "app.include_router(api_router, prefix=settings.API_V1_STR)\n"
          "@app.get('/health')\ndef health(): ...\n")
    write(tmp_path, "app/api/main.py",
          "from fastapi import APIRouter\nfrom app.api.routes import items, users\nfrom .routes.admin import router as admin_router\n"
          "api_router = APIRouter()\n"
          "api_router.include_router(users.router)\n"
          "api_router.include_router(items.router, prefix='/catalog')\n"
          "if settings.ENV == 'dev':\n    api_router.include_router(admin_router, prefix=f'/{settings.PROJECT}')\n")
    write(tmp_path, "app/api/routes/items.py",
          "from fastapi import APIRouter\nrouter = APIRouter(prefix='/items', tags=['items'])\n"
          "@router.get('/')\ndef read_items(): ...\n@router.put('/{id}')\ndef update_item(id): ...\n")
    write(tmp_path, "app/api/routes/users.py",
          "from fastapi import APIRouter\nrouter = APIRouter(prefix='/users')\n"
          "@router.api_route('/me', methods=['GET', 'PATCH'])\ndef me(): ...\n@router.post('/signup')\ndef signup(): ...\n")
    write(tmp_path, "app/api/routes/admin.py", "from fastapi import APIRouter\nrouter = APIRouter(prefix='/admin')\n@router.delete('/{name}')\ndef rm(name): ...\n")
    write(tmp_path, "app/api/routes/orphan.py", "from fastapi import APIRouter\nlost = APIRouter(prefix='/lost')\n@lost.get('/x')\ndef x(): ...\n")
    return tmp_path


def test_fastapi_prefix_chain_across_files_constants_and_fstrings(tmp_path):
    got = routes_of(fastapi_project(tmp_path))
    included = {k: v for k, v in got.items() if k[1] != "/lost/x"}
    assert set(included) == {
        ("GET", "/health"),                                   # decorator on the app itself
        ("GET", "/api/v1/users/me"), ("PATCH", "/api/v1/users/me"),   # api_route(methods=[...]); API_V1_STR from another file
        ("POST", "/api/v1/users/signup"),
        ("GET", "/api/v1/catalog/items"), ("PUT", "/api/v1/catalog/items/{id}"),   # include_router(prefix=...) + own prefix
        ("DELETE", "/api/v1/demo/admin/{name}"),               # f-string prefix using a constant; aliased relative import
    }
    assert all(r.prefix_known for r in included.values())


def test_fastapi_item_routes_use_the_prefix_they_are_included_with(tmp_path):
    keys = set(routes_of(fastapi_project(tmp_path)))
    assert ("GET", "/api/v1/catalog/items") in keys and ("PUT", "/api/v1/catalog/items/{id}") in keys
    assert ("GET", "/api/v1/items") not in keys     # items.router is only included under /catalog


def test_fastapi_router_nobody_includes_has_an_unknown_prefix(tmp_path):
    got = routes_of(fastapi_project(tmp_path))
    assert got[("GET", "/lost/x")].prefix_known is False


def test_flask_blueprints_and_methods(tmp_path):
    write(tmp_path, "shop/orders.py",
          "from flask import Blueprint\nbp = Blueprint('orders', __name__, url_prefix='/orders')\n"
          "@bp.route('/', methods=['GET', 'POST'])\ndef index(): ...\n@bp.route('/<int:id>')\ndef one(id): ...\n")
    write(tmp_path, "shop/__init__.py",
          "from flask import Flask\nfrom .orders import bp\napp = Flask(__name__)\napp.register_blueprint(bp, url_prefix='/v1')\n"
          "@app.route('/ping')\ndef ping(): ...\n")
    keys = set(routes_of(tmp_path))
    assert {("GET", "/v1/orders"), ("POST", "/v1/orders"), ("GET", "/v1/orders/<int:id>"), ("GET", "/ping")} <= keys


def test_generated_client_urls_in_option_objects(tmp_path):
    write(tmp_path, "src/client/sdk.gen.ts",
          "export class ItemsService {\n"
          "  public static readItems(options) {\n"
          "    return (options.client ?? client).get<A, B, C>({\n      responseType: 'json',\n      url: '/api/v1/items/',\n      ...options\n    });\n  }\n"
          "  public static deleteItem(options) {\n"
          "    return (options.client ?? client).delete<A, B>({\n      url: '/api/v1/items/{id}',\n      ...options\n    });\n  }\n}\n"
          "const r = client.post({ url: '/api/v1/login', body });\n")
    got = [(c["methods"], c["url"]) for c in find_api_calls.scan(tmp_path)]
    assert got == [(["GET"], "/api/v1/items"), (["DELETE"], "/api/v1/items/{id}"), (["POST"], "/api/v1/login")]


# ---- 7.6 Express router graph --------------------------------------------------------

def express_project(tmp_path):
    write(tmp_path, "src/main.ts",
          "import express from 'express';\nimport routes from './app/routes/routes';\n"
          "const app = express();\napp.use(cors());\napp.use(routes);\n"
          "app.get('/', (req, res) => res.json({ docs: 'http://example.com/docs' })); // see http://x.y\n")
    write(tmp_path, "src/app/routes/routes.ts",
          "import { Router } from 'express';\nimport tags from './tag/tag.controller';\nimport { articles } from './article/article.controller';\n"
          "import users = require('./user/user.controller');\n"
          "const api = Router()\n  .use(tags)\n  .use('/content', articles)\n  .use(require('./misc'));\n\n"
          "export default Router().use('/api', api);\n")
    write(tmp_path, "src/app/routes/tag/tag.controller.ts", "import { Router } from 'express';\nconst router = Router();\nrouter.get('/tags', h);\nexport default router;\n")
    write(tmp_path, "src/app/routes/article/article.controller.ts",
          "import { Router } from 'express';\nexport const articles = Router();\n"
          "articles.route('/articles/:slug')\n  .get(h)\n  .put(auth, h)\n  .delete(h);\n"
          "// articles.get('/ghost', h);\n")
    write(tmp_path, "src/app/routes/misc.js", "const router = require('express').Router();\nrouter.all('/ping', h);\nmodule.exports = router;\n")
    write(tmp_path, "src/orphan.ts", "import { Router } from 'express';\nconst lonely = Router();\nlonely.get('/lonely', h);\n")
    return tmp_path


def test_express_chained_use_anonymous_default_export_and_route_chains(tmp_path):
    got = routes_of(express_project(tmp_path))
    keys = {k for k, v in got.items() if v.prefix_known}
    assert keys == {
        ("GET", "/"),                                   # a route on the app itself
        ("GET", "/api/tags"),                           # app.use(routes) -> Router().use('/api', api) -> .use(tags)
        ("GET", "/api/content/articles/:slug"), ("PUT", "/api/content/articles/:slug"), ("DELETE", "/api/content/articles/:slug"),  # named import, route().get().put().delete()
        (None, "/api/ping"),                            # .use(require('./misc')) and router.all
    }
    assert ("GET", "/api/content/ghost") not in set(got)      # commented-out route


def test_express_unmounted_router_has_an_unknown_prefix(tmp_path):
    got = routes_of(express_project(tmp_path))
    assert got[("GET", "/lonely")].prefix_known is False


def test_express_url_in_a_string_is_not_mistaken_for_a_comment(tmp_path):
    write(tmp_path, "app.js", "const app = require('express')();\napp.get('/docs', (q, r) => r.redirect('http://example.com/a//b'));\napp.get('/after', h);\n")
    assert {("GET", "/docs"), ("GET", "/after")} <= set(routes_of(tmp_path))


# ---- 7.6 frontend wrapper services ----------------------------------------------------

VUE_WRAPPER = (
    "async function request(method, path, body) {\n  const response = await fetch(`${API_URL}/${path}`, { method });\n  return { data: await response.json() };\n}\n"
    "const ApiService = {\n"
    "  query(resource, config) { return request('GET', resource); },\n"
    "  get(resource, slug = '') { return request('GET', slug ? `${resource}/${slug}` : resource); },\n"
    "  post(resource, params) { return request('POST', resource, params); },\n"
    "  update(resource, slug, params) { return request('PUT', `${resource}/${slug}`, params); },\n"
    "  delete(resource) { return request('DELETE', resource); }\n"
    "};\nexport default ApiService;\n"
    "export const ArticlesService = {\n  get(slug) { return ApiService.get('articles', slug); },\n  create(params) { return ApiService.post('articles', { article: params }); },\n"
    "  update(slug, params) { return ApiService.update('articles', slug, { article: params }); },\n"
    "  destroy(slug) { return ApiService.delete(`articles/${slug}`); }\n};\n"
    "export const CommentsService = {\n  get(slug) { return ApiService.get('articles', `${slug}/comments`); }\n};\n")


def test_wrapper_is_detected_by_its_resource_first_parameter_not_by_verb_names(tmp_path):
    write(tmp_path, "src/api.service.js", VUE_WRAPPER)
    assert [w["name"] for w in find_api_calls.detect_wrappers(tmp_path)] == ["ApiService"]   # ArticlesService.get(slug) is a domain service


def test_wrapper_calls_become_urls_with_segments_and_verbs(tmp_path):
    write(tmp_path, "src/api.service.js", VUE_WRAPPER)
    write(tmp_path, "src/store.js",
          "ApiService.post('users/login', { user });\nApiService.get('user');\nApiService.put('user', { user });\n"
          "ApiService.get('profiles', username);\nApiService.query('articles' + (type === 'feed' ? '/feed' : ''), { params });\n"
          "ApiService.update('articles', slug, params);\nApiService.delete(`profiles/${username}/follow`);\n")
    got = {(tuple(c["methods"]), c["url"]) for c in find_api_calls.scan(tmp_path) if c["file"] == "src/store.js"}
    assert got == {(("POST",), "/users/login"), (("GET",), "/user"), (("PUT",), "/user"), (("GET",), "/profiles/{}"),
                   (("GET",), "/articles"), (("PUT",), "/articles/{}"), (("DELETE",), "/profiles/{}/follow")}
    inside = {(tuple(c["methods"]), c["url"]) for c in find_api_calls.scan(tmp_path) if c["file"] == "src/api.service.js"}
    assert (("GET",), "/articles/{}") in inside and (("GET",), "/articles/{}/comments") in inside    # ApiService.get('articles', `${slug}/comments`)
    assert not any(u in ("/", "/{}") for _m, u in inside | got)       # the wrapper's own fetch(`${API_URL}/${path}`) says nothing


def test_wrappers_can_be_switched_off_or_named(tmp_path):
    write(tmp_path, "src/api.service.js", VUE_WRAPPER)
    write(tmp_path, "src/store.js", "ApiService.post('users/login', { user });\nHttpGateway.get('ping');\n")
    assert not [c for c in find_api_calls.scan(tmp_path, wrappers=[]) if c["file"] == "src/store.js"]
    named = [c["url"] for c in find_api_calls.scan(tmp_path, wrappers=["HttpGateway"]) if c["file"] == "src/store.js"]
    assert named == ["/ping"]


def test_api_url_constants_with_fallbacks_give_a_base_url(tmp_path):
    write(tmp_path, "src/config.js", 'export const API_URL =\n  import.meta.env.VITE_API_URL || "https://api.example.com/api";\n')
    write(tmp_path, "src/env.ts", "export const environment = { apiUrl: 'http://localhost:5000/v2' };\n")
    bases = sorted(d["base"] for d in find_api_calls.detect_base_urls(tmp_path))
    assert bases == ["/api", "/v2"]


def test_run_reports_the_detected_wrapper_and_matches_through_it(tmp_path):
    write(tmp_path, "fe/src/api.service.js", VUE_WRAPPER)
    write(tmp_path, "fe/src/store.js", "ApiService.get('tags');\nApiService.get('articles', slug);\n")
    write(tmp_path, "be/ArticlesController.cs",
          '[Route("articles")]\npublic class ArticlesController : ControllerBase\n{\n  [HttpGet("{slug}")]\n  public IActionResult One(string slug) { }\n}\n'
          '[Route("tags")]\npublic class TagsController : ControllerBase\n{\n  [HttpGet]\n  public IActionResult All() { }\n}\n')
    result = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")])
    assert any("HTTP wrapper ApiService detected" in n for n in result["notes"])
    assert {m["call"]["url"] for m in result["matches"]} == {"/tags", "/articles/{}"}
    off = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")], wrappers=[])
    assert off["matches"] == []
