# Where flows start, per framework

| Stack | Entry points | Wiring / DI to check | Typical layers |
|---|---|---|---|
| **Express / Node** | `app.get/post(...)`, `router.*`, `app.use` | `app.js`/`server.js` mounting routers, middleware order | route → middleware → controller → service → model |
| **NestJS** | `@Controller`, `@Get/@Post` | `@Module({providers})`, constructor injection | controller → service → repository |
| **Django** | `urls.py` `path()`, views/viewsets | `settings.py` MIDDLEWARE, signals (`post_save`) | url → view → form/serializer → model |
| **FastAPI / Flask** | `@app.get`, `@router.post`, `@app.route`, blueprints | `Depends(...)`, `app.include_router` | route → dependency → service → ORM |
| **Spring Boot** | `@RestController`, `@GetMapping/@PostMapping` | `@Autowired`, `@Service`, `@Repository`, AOP `@Transactional` | controller → service → repository → JPA |
| **ASP.NET Core** | `[ApiController]`, `[HttpGet]`, `app.MapGet` | `Program.cs` `builder.Services.Add*`, middleware pipeline | controller → service → DbContext |
| **React / Next.js** | routes in `App.tsx` (`<Route>`), `pages/`, `app/` dirs | context providers, hooks, API clients | page → component → hook → API call |
| **Angular** | `RouterModule.forRoot(routes)` | `providedIn`, module providers | route → component → service → HttpClient |
| **Flutter** | `MaterialApp(routes:)`, `Navigator.push`, go_router | Provider/Riverpod/Bloc | screen → widget → bloc/provider → repository |
| **Go** | `r.GET(...)` (gin/echo/chi), `mux.HandleFunc`, `func main` | router setup in `main`/`routes.go`, middleware chains | handler → service → repo |
| **Laravel** | `Route::get/post(...)` in `routes/*.php` | service providers, middleware aliases | controller → service → Eloquent model |
| **Rails** | `config/routes.rb` (`get`, `resources`) | `before_action`, concerns | controller → model/service |
| **gRPC** | `rpc Name(...)` in `.proto` | service implementation registration | rpc → service impl → repo |
| **CLI (any)** | `main()`, `argparse`, `click`, `commander`, `cobra` | subcommand registration | command → handler → core |
| **Jobs / events** | cron config, `@Scheduled`, Celery `@task`, queue consumers | broker config | trigger → handler → service |

## Inferred hops – always mark `inferred: true`
- DI container resolving an interface to an implementation
- Event bus / signal / pub-sub subscribers
- Reflection, decorators that register handlers at runtime
- Config-driven routing (YAML, env vars)
- ORM lazy loading triggering queries

## User-flow mode tips
- **Next.js:** pages are `app/**/page.tsx`; check `middleware.ts`/`proxy.ts` first (auth gates every route) and client-side navigation (`router.push`, `history.replaceState`, `window.location.assign`).
- **Angular:** routes in `*.routes.ts`; guards (`canActivate`) are decisions; `navigate`/`navigateByUrl` and `returnUrl` query params are the edges.
- **Flutter (go_router):** the global `redirect` is the main decision; `context.go/push` are the edges.
- **React Router:** object routes (`createBrowserRouter`) or `<Route>`; wrapper elements like `ProtectedRoute` are decisions.
- Nodes are screens (`ui`) and decisions (`decision`), edges are user actions ("taps Pay", "invalid OTP").
- Get screens from the router config; get transitions from `navigate()/push()/redirect()` calls and form submit handlers.
