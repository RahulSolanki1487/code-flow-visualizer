# Test repos for frontend <-> backend linking

All of these are public. Clone each into its own folder (`git clone --depth 1 <url>`) and treat them as read-only:
the tools only read source files and never run the code.

## The RealWorld family: one API contract, many stacks

The "RealWorld" spec (a Medium.com clone) is implemented by many frontends and many backends that all serve the
same endpoints (`/api/users/login`, `/api/articles/{slug}`, ...). Any frontend can be paired with any backend.

| Role | Stack | Repo |
|---|---|---|
| frontend | Angular | https://github.com/realworld-apps/angular-realworld-example-app |
| frontend | Vue | https://github.com/realworld-apps/vue-realworld-example-app |
| frontend | React + Redux (archived) | https://github.com/gothinkster/react-redux-realworld-example-app |
| backend | Spring Boot | https://github.com/gothinkster/spring-boot-realworld-example-app |
| backend | Express (TypeScript) | https://github.com/gothinkster/node-express-realworld-example-app |
| backend | Laravel (archived) | https://github.com/gothinkster/laravel-realworld-example-app |
| backend | Rails (archived) | https://github.com/gothinkster/rails-realworld-example-app |
| backend | Django (archived) | https://github.com/gothinkster/django-realworld-example-app |

Other full-stack repo: https://github.com/fastapi/full-stack-fastapi-template (React frontend and FastAPI backend in one repo).

```bash
python skill/code-flow-visualizer/scripts/match_api.py \
  --frontend web=../angular-realworld-example-app --backend api=../spring-boot-realworld-example-app
```

## What to expect today (checked 2026-11-22, after Phase 7.1-7.3)

The Angular RealWorld app adds its base URL in an HTTP interceptor (`https://api.realworld.show/api` + the call's path).
The tool detects that (`/api`) and applies it, so the frontend's 18 calls look like `/api/articles/{}`. The report prints a
`NOTE` saying where the base came from; `--base-url web=none` turns it off.

Angular frontend (18 calls) against each backend:

| Backend | Routes found | Calls matched | Notes |
|---|---|---|---|
| Django | 16 entries | 18 of 18, all exact | `url()` patterns, nested `include()`, DRF router (methods from mixins and `def` actions, `lookup_field`) |
| Rails | 22 | 18 of 18, all exact | `scope :api`, `resources ... param: :slug, except: [...]`, nested resources, `get :feed, on: :collection`, `devise_for` (approximated) |
| Laravel | 22 | 18 of 18, all exact | `/api` prefix from `RouteServiceProvider`, `Route::group`, `Route::match`, `Route::resource` options and nesting |
| Spring Boot | 19 | 18 of 18, all exact with `--base-url web=none` | the Spring app serves `/articles` without `/api`; by default the report says so instead of showing 0 matches: `HINT without the base URL (web=/api) 15 of 18 calls would match ...` |
| Express | 20 | 18 of 18 but all `likely` | controllers are composed through several levels of `router.use(...)`, so their prefix is unknown (Phase 7.6) |

Frontends: the Angular app works well. The Vue app routes every call through an `ApiService.get('articles', slug)` wrapper
that takes a resource name, which is not recognised yet. The FastAPI template's React client is generated
(`client.gen.ts`, `url:` object properties) and its backend uses `include_router(prefix=...)`; neither is resolved yet.

## Gateway demo (in this repo)

`examples/cross-repo-gateway/`: an Angular frontend, an Express orders service, a Spring billing service and an
nginx gateway that strips `/orders-svc` and `/billing-svc`.

```bash
python skill/code-flow-visualizer/scripts/match_api.py \
  --frontend web=examples/cross-repo-gateway/web \
  --backend orders=examples/cross-repo-gateway/orders-api --backend billing=examples/cross-repo-gateway/billing-api \
  --gateway-config examples/cross-repo-gateway/gateway/nginx.conf
```
Without `--gateway-config` (or `--gateway-prefix orders=orders-svc --gateway-prefix billing=billing-svc`) nothing matches,
because the frontend URL and the backend route differ by the gateway prefix. With it, 5 of 6 calls match; the
`/shipping-svc/...` call is reported as having no backend (there is no shipping service in the demo).
Write `--gateway-prefix` values without a leading slash: Git Bash rewrites `/x` into a Windows path.

## Known gaps these repos exposed (still open)

1. FastAPI: prefixes from `include_router(router, prefix=...)`; generated TypeScript clients that pass `{ url: '...' }` (Phase 7.5).
2. Express: routers composed through several levels of `router.use(...)` (Phase 7.6).
3. Frontend wrapper services that take a resource name (`ApiService.get('articles', slug)`) (Phase 7.6).
4. GraphQL (one endpoint, operation names) and gRPC (`.proto` services) (Phase 7.7).
5. Django function views and `@api_view` decorators are matched by path only (method `ANY`); Rails `concerns`, `draw(...)` of other files and conditionals are not followed.

Fixed since the first version of this guide: Django, Rails and Laravel route parsing, base URLs added by interceptors / axios `baseURL`,
calls split over several lines (`this.http` newline `.post<T>(...)`), `'/a/' + x + '/b'` URLs, and Spring method-level
`@RequestMapping(path = ..., method = POST)`.
