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

## What to expect today (checked 2026-11-22)

The Angular app adds its base URL in an HTTP interceptor (`https://api.realworld.show/api` + the call's path), so
its calls look like `/articles` and `/users/login`. The scan cannot see an interceptor, and several backends also
show their routes without `/api`, so those pairs line up because both sides omit the prefix, not because a prefix
was resolved.

Angular frontend (13 calls) against each backend:

| Backend | Result | Why |
|---|---|---|
| Spring Boot | 11 of 13 calls matched, mostly exact | class `@RequestMapping` prefixes resolved (`/articles/{slug}`); no `/api` on either side |
| Express | 13 of 13 matched | 19 of its 20 routes show "prefix unknown" (controllers are composed through `router.use(...)`), but they line up with the Angular paths |
| Laravel | 12 of 13 matched, several only `likely` | `routes/api.php` gets an automatic `/api` prefix and `Route::group` prefixes are not resolved yet |
| Rails | 12 calls matched, but 25 `likely` matches: too loose | `resources :articles` is not expanded into its routes yet |
| Django | 0 routes found | `url(r'^...')` patterns and `include()` prefixes are not parsed yet |

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

## Known gaps these repos exposed (to build next)

0. Base URLs added by an HTTP interceptor or client setup (Angular `HttpInterceptor`, axios `baseURL`) are invisible to the call scan.
1. Django: `url()`/`re_path` regex patterns and nested `include()` prefixes.
2. Rails: `resources`/`resource`, `namespace`, `scope`, nested and member routes.
3. Laravel: the automatic `/api` prefix of `routes/api.php`, `Route::prefix()->group()` and `Route::group(['prefix' => ...])`.
4. FastAPI: prefixes from `include_router(router, prefix=...)`; generated TypeScript clients that pass `{ url: '...' }`.
5. Express: routers composed through several levels of `router.use(...)`.
6. Frontend wrapper services that take a resource name (`ApiService.get('articles', slug)`).
7. Not started: GraphQL (one endpoint, operation names) and gRPC (`.proto` services).
