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

## What to expect today (checked 2026-11-22, after Phase 7.0-7.6)

Both RealWorld frontends add their base URL outside the call sites: Angular in an HTTP interceptor
(`https://api.realworld.show/api` + the call's path), Vue in a constant (`API_URL = ... || "https://api.realworld.show/api"`).
The tool detects it (`/api`) and applies it; the report prints a `NOTE` saying where it came from, and `--base-url web=none`
turns it off. The Vue app calls everything through `ApiService.get('articles', slug)`; the tool detects that wrapper
(its methods take a resource as the first parameter) and prints a `NOTE`; `--wrapper none` turns it off.

Frontend (18 calls each) against each backend: **every pair matches 18 of 18, all exact.**

| Backend | Routes found | How |
|---|---|---|
| Django | 16 entries | `url()` patterns, nested `include()`, DRF router (methods from mixins and `def` actions, `lookup_field`) |
| Rails | 22 | `scope :api`, `resources ... param: :slug, except: [...]`, nested resources, `get :feed, on: :collection`, `devise_for` (approximated) |
| Laravel | 22 | `/api` prefix from `RouteServiceProvider`, `Route::group`, `Route::match`, `Route::resource` options and nesting |
| Express | 20 | three levels of `router.use(...)`: controllers -> `Router().use(...)` chain -> `Router().use('/api', api)` default export -> `app.use(routes)` |
| Spring Boot | 19 | needs `--base-url web=none`: the Spring app serves `/articles` without `/api`. By default the report says so instead of showing 0 matches: `HINT without the base URL (web=/api) 18 of 18 calls would match ...` |

FastAPI full-stack template (React + FastAPI in one repo): 23 routes, all under `/api/v1` (`app.include_router(api_router, prefix=settings.API_V1_STR)`
resolved through three files and a constant in `config.py`); the generated TypeScript client's 23 calls are found and all match.

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

## Known gaps (still open)

1. GraphQL (one endpoint, operation names) and gRPC (`.proto` services) (Phase 7.7).
2. Django function views and `@api_view` decorators are matched by path only (method `ANY`); Rails `concerns`, `draw(...)` of other files and conditionals are not followed.
3. Wrappers are recognised when their methods take the resource/url as first parameter (`get(resource, slug)`); wrappers with other shapes need `--wrapper NAME`.
4. Express routers registered through loops, factories or `app.use(path, require(...)())` are not followed.

Fixed since the first version of this guide: Django, Rails, Laravel, FastAPI, Express route parsing; base URLs added by interceptors,
axios `baseURL` and `API_URL` constants; HTTP wrapper services; generated TypeScript clients; calls split over several lines
(`this.http` newline `.post<T>(...)`); `'/a/' + x + '/b'` URLs; Spring method-level `@RequestMapping(path = ..., method = POST)`.
