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
| **CLI (any)** | `main()`, `argparse`, `click`, `commander`, `cobra` | subcommand registration | command → handler → core |
| **Jobs / events** | cron config, `@Scheduled`, Celery `@task`, queue consumers | broker config | trigger → handler → service |

## Inferred hops – always mark `inferred: true`
- DI container resolving an interface to an implementation
- Event bus / signal / pub-sub subscribers
- Reflection, decorators that register handlers at runtime
- Config-driven routing (YAML, env vars)
- ORM lazy loading triggering queries

## User-flow mode tips
- Nodes are screens (`ui`) and decisions (`decision`), edges are user actions ("taps Pay", "invalid OTP").
- Get screens from the router config; get transitions from `navigate()/push()/redirect()` calls and form submit handlers.
