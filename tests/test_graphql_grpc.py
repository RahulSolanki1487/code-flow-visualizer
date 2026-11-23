"""Phase 7.7: GraphQL and gRPC as routes and calls."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "code-flow-visualizer" / "scripts"))

import find_api_calls  # noqa: E402
import graphql_calls  # noqa: E402
import grpc_calls  # noqa: E402
import grpc_routes  # noqa: E402
import match_api  # noqa: E402
import route_table  # noqa: E402


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def routes_of(repo: Path) -> dict:
    return {(r.method, r.path): r for r in route_table.collect_routes(repo)}


def calls_of(repo: Path) -> list:
    return [(tuple(c["methods"]), c["url"], c["file"], c["line"]) for c in find_api_calls.scan(repo)]


# ---- GraphQL backend -----------------------------------------------------------------

SDL = '''"""The root"""
type Query {
  "one launch"
  launch(id: ID!): Launch
  # fakeField: String
  launches(
    """page size"""
    pageSize: Int
    after: String
  ): [Launch!]!
  me: User
}

type Mutation {
  bookTrips(launchIds: [ID]!): Result!
}

extend type Query {
  health: String
}

type Launch { id: ID! site: String }
type Subscription { tripBooked: Launch }
'''


def test_graphql_sdl_file_fields_args_comments_and_extend(tmp_path):
    write(tmp_path, "schema.graphql", SDL)
    got = routes_of(tmp_path)
    assert set(got) == {("QUERY", "/graphql/launch"), ("QUERY", "/graphql/launches"), ("QUERY", "/graphql/me"), ("QUERY", "/graphql/health"),
                        ("MUTATION", "/graphql/bookTrips"), ("SUBSCRIPTION", "/graphql/tripBooked")}
    assert got[("QUERY", "/graphql/launches")].line == 6 and "(schema)" in got[("QUERY", "/graphql/launches")].action


def test_graphql_custom_root_type_names_via_schema_block(tmp_path):
    write(tmp_path, "schema.graphql", "schema { query: RootQuery mutation: RootMutation }\ntype RootQuery { ping: String }\ntype RootMutation { reset: Boolean }\ntype Query { notRoot: String }\n")
    assert set(routes_of(tmp_path)) == {("QUERY", "/graphql/ping"), ("MUTATION", "/graphql/reset")}


def test_graphql_embedded_template_resolver_map_and_endpoint(tmp_path):
    write(tmp_path, "server/schema.js", "const typeDefs = gql`\n  type Query {\n    launches: [Launch]\n    me: User\n  }\n  type Mutation {\n    login(email: String): User\n  }\n`;\n")
    write(tmp_path, "server/resolvers.js",
          "module.exports = {\n  Query: {\n    launches: async (_, args, ctx) => ctx.api.all(),\n    me(_, __, ctx) { return ctx.user; },\n  },\n"
          "  Mutation: {\n    login: (_, { email }) => user(email),\n  },\n  Launch: { site: () => 'x' },\n};\n")
    write(tmp_path, "server/index.js", "app.use('/api/graphql', expressMiddleware(server));\n")
    got = routes_of(tmp_path)
    assert set(got) == {("QUERY", "/api/graphql/launches"), ("QUERY", "/api/graphql/me"), ("MUTATION", "/api/graphql/login")}
    assert got[("QUERY", "/api/graphql/launches")].file == "server/resolvers.js" and got[("QUERY", "/api/graphql/launches")].line == 3
    assert got[("QUERY", "/api/graphql/me")].line == 4          # method shorthand
    assert "Launch.site" not in " ".join(r.action for r in got.values())   # non-root type resolvers are not operations


def test_graphql_decorator_and_class_resolvers(tmp_path):
    write(tmp_path, "schema.graphql", "type Query { launches: [L] launch(id: ID): L }\ntype Mutation { book(id: ID): L }\n")
    write(tmp_path, "src/launch.resolver.ts", "@Resolver()\nexport class LaunchResolver {\n  @Query(() => [Launch])\n  launches() {}\n\n  @Mutation(() => Launch, { name: 'book' })\n  async bookTrip() {}\n}\n")
    write(tmp_path, "src/main/java/Api.java", "@Controller\nclass Api {\n  @QueryMapping\n  public Launch launch(@Argument String id) { return null; }\n}\n")
    got = routes_of(tmp_path)
    assert got[("QUERY", "/graphql/launches")].file == "src/launch.resolver.ts" and got[("QUERY", "/graphql/launches")].line == 4
    assert got[("MUTATION", "/graphql/book")].line == 7           # decorator name option, not the method name
    assert got[("QUERY", "/graphql/launch")].file == "src/main/java/Api.java"


# ---- GraphQL frontend -----------------------------------------------------------------

def test_graphql_operations_fragments_aliases_variables_and_client_fields(tmp_path):
    write(tmp_path, "src/client.ts", "const client = new ApolloClient({\n  uri: 'http://localhost:4000/api/graphql',\n  cache,\n});\n")
    write(tmp_path, "src/queries.ts",
          "export const A = gql`\n  query LaunchDetails($id: ID!) {\n    launch(id: $id) {\n      site\n      ...LaunchTile\n    }\n    me { id }\n  }\n  ${LAUNCH_TILE}\n`;\n"
          "export const B = gql`\n  mutation Book($ids: [ID]!) @live {\n    result: bookTrips(launchIds: $ids) { success }\n  }\n`;\n"
          "const C = gql`{ launches(pageSize: 5) { id } }`;\n"
          "const D = gql`\n  query Local {\n    isLoggedIn @client\n    cartItems @client\n    cart { id }\n  }\n`;\n"
          "const E = gql`\n  subscription OnBooked { tripBooked { id } }\n`;\n")
    got = {(m, u) for m, u, _f, _l in calls_of(tmp_path)}
    assert got == {(("QUERY",), "/api/graphql/launch"), (("QUERY",), "/api/graphql/me"), (("MUTATION",), "/api/graphql/bookTrips"),
                   (("QUERY",), "/api/graphql/launches"), (("QUERY",), "/api/graphql/cart"), (("SUBSCRIPTION",), "/api/graphql/tripBooked")}


def test_graphql_files_and_other_text_are_handled(tmp_path):
    write(tmp_path, "src/queries.graphql", "query Profile {\n  me { id }\n}\n\nmutation Logout {\n  logout\n}\n")
    write(tmp_path, "src/plain.ts", "const query = 'select * from t';\nconst gqlish = `query not gql {` ;\n")
    got = calls_of(tmp_path)
    assert {(m, u) for m, u, _f, _l in got} == {(("QUERY",), "/graphql/me"), (("MUTATION",), "/graphql/logout")}
    assert {(u, ln) for _m, u, _f, ln in got} == {("/graphql/me", 1), ("/graphql/logout", 5)}


def test_graphql_end_to_end_match_and_unknown_operation(tmp_path):
    write(tmp_path, "be/schema.graphql", "type Query { launches: [L] me: U }\ntype Mutation { login(e: String): U }\n")
    write(tmp_path, "be/resolvers.js", "module.exports = { Query: { launches: () => [], me: () => null }, Mutation: { login: () => null } };\n")
    write(tmp_path, "fe/q.ts", "const Q = gql`query { launches { id } ghost { id } }`;\nconst M = gql`mutation Login($e: String) { login(e: $e) { id } }`;\n")
    result = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")])
    assert {(m["call"]["url"], m["confidence"]) for m in result["matches"]} == {("/graphql/launches", "exact"), ("/graphql/login", "exact")}
    assert [c["url"] for c in result["unmatched_calls"]] == ["/graphql/ghost"]
    assert [r["path"] for r in result["uncalled_routes"]] == ["/graphql/me"]


# ---- gRPC backend ----------------------------------------------------------------------

PROTO = '''syntax = "proto3";
package shop.v1;

// the shop
service Orders {
  // unary
  rpc Place(PlaceRequest) returns (Order);
  rpc Watch(WatchRequest) returns (stream Order);
  rpc Upload(stream Chunk) returns (Summary);
  rpc Chat(stream Msg) returns (stream Msg) {}
  /* rpc Hidden(A) returns (B); */
}
service Billing { rpc Charge (ChargeRequest) returns (Receipt); }
'''


def test_proto_services_streaming_kinds_and_comments():
    rows = grpc_routes.parse_proto(PROTO)
    assert [(r["service"], r["rpc"], r["streaming"], r["package"]) for r in rows] == [
        ("Orders", "Place", "unary", "shop.v1"), ("Orders", "Watch", "server streaming", "shop.v1"),
        ("Orders", "Upload", "client streaming", "shop.v1"), ("Orders", "Chat", "bidirectional streaming", "shop.v1"),
        ("Billing", "Charge", "unary", "shop.v1")]
    assert rows[0]["line"] == 7


def test_grpc_routes_point_at_implementations_in_several_languages(tmp_path):
    write(tmp_path, "shop.proto", PROTO)
    write(tmp_path, "node/server.js", "const orders = proto.shop.v1.Orders;\nserver.addService(orders.service, {\n  place: doPlace,\n  watch: doWatch,\n});\nfunction doPlace() {}\n")
    write(tmp_path, "java/OrdersImpl.java", "class OrdersImpl extends OrdersGrpc.OrdersImplBase {\n  @Override\n  public void upload(StreamObserver<Summary> o) {}\n}\n")
    write(tmp_path, "cs/Billing.cs", "public class BillingService : Billing.BillingBase\n{\n    public override Task<Receipt> Charge(ChargeRequest r, ServerCallContext c) => null;\n}\n")
    write(tmp_path, "gen/shop_pb2_grpc.py", "class OrdersServicer:\n    def Chat(self, request_iterator, context): ...\n")   # generated: ignored
    got = routes_of(tmp_path)
    assert set(got) == {("POST", "/shop.v1.Orders/Place"), ("POST", "/shop.v1.Orders/Watch"), ("POST", "/shop.v1.Orders/Upload"),
                        ("POST", "/shop.v1.Orders/Chat"), ("POST", "/shop.v1.Billing/Charge")}
    assert (got[("POST", "/shop.v1.Orders/Place")].file, got[("POST", "/shop.v1.Orders/Place")].line) == ("node/server.js", 3)
    assert (got[("POST", "/shop.v1.Orders/Upload")].file, got[("POST", "/shop.v1.Orders/Upload")].line) == ("java/OrdersImpl.java", 3)
    assert got[("POST", "/shop.v1.Billing/Charge")].file == "cs/Billing.cs"
    assert got[("POST", "/shop.v1.Orders/Chat")].file == "shop.proto" and "(proto)" in got[("POST", "/shop.v1.Orders/Chat")].action  # only a generated file mentions it


def test_proto_without_a_package(tmp_path):
    write(tmp_path, "a.proto", "service Echo { rpc Say(M) returns (M); }\n")
    assert ("POST", "/Echo/Say") in routes_of(tmp_path)


# ---- gRPC frontend ----------------------------------------------------------------------

def test_grpc_web_and_connect_clients_and_the_imports_that_gate_them(tmp_path):
    write(tmp_path, "src/orders.ts",
          "import { OrdersClient } from './gen/OrdersServiceClientPb';\n"
          "class Api {\n  private client = new OrdersClient('http://h:8080');\n  place(r) { return this.client.place(r, {}); }\n}\n"
          "const stream = new OrdersClient(host);\nstream.watch(req).on('data', f);\nstream.close();\n")
    write(tmp_path, "src/billing.ts",
          "import { createPromiseClient } from '@connectrpc/connect';\nimport { BillingService } from './gen/billing_connect';\n"
          "const billing = createPromiseClient(BillingService, transport);\nawait billing.charge({ amount: 1 });\n")
    write(tmp_path, "src/other.ts", "const apollo = new ApolloClient({ uri });\napollo.query({ query });\nconst s3 = new S3Client({});\ns3.send(x);\n")
    got = {(u, f) for _m, u, f, _l in calls_of(tmp_path)}
    assert got == {("/{}.Orders/Place", "src/orders.ts"), ("/{}.Orders/Watch", "src/orders.ts"), ("/{}.Billing/Charge", "src/billing.ts")}


def test_grpc_package_is_taken_from_protos_or_generated_paths_in_the_frontend(tmp_path):
    write(tmp_path, "proto/shop.proto", PROTO)
    write(tmp_path, "src/a.ts", "import { OrdersClient } from './gen/OrdersServiceClientPb';\nconst c = new OrdersClient(h);\nc.place(r);\n")
    assert [u for _m, u, f, _l in calls_of(tmp_path) if f == "src/a.ts"] == ["/shop.v1.Orders/Place"]
    other = tmp_path / "gen_only"
    write(other, "src/gen/Orders_grpc_web_pb.js", "var m = new grpc.web.MethodDescriptor('/acme.shop.Orders/Place', x);\n")
    write(other, "src/a.ts", "import { OrdersClient } from './gen/Orders_grpc_web_pb';\nconst c = new OrdersClient(h);\nc.place(r);\n")
    assert [u for _m, u, f, _l in calls_of(other) if f == "src/a.ts"] == ["/acme.shop.Orders/Place"]


def test_grpc_end_to_end_with_and_without_a_known_package(tmp_path):
    write(tmp_path, "be/shop.proto", PROTO)
    write(tmp_path, "fe/src/a.ts", "import { OrdersClient } from './gen/OrdersServiceClientPb';\nconst c = new OrdersClient(h);\nc.place(r);\nc.watch(r);\nc.refund(r);\n")
    result = match_api.run([("web", tmp_path / "fe")], [("api", tmp_path / "be")])
    assert {(m["call"]["url"], m["confidence"]) for m in result["matches"]} == {("/{}.Orders/Place", "exact"), ("/{}.Orders/Watch", "exact")}
    assert [c["url"] for c in result["unmatched_calls"]] == ["/{}.Orders/Refund"]      # no such rpc
    assert sorted(r["path"] for r in result["uncalled_routes"]) == ["/shop.v1.Billing/Charge", "/shop.v1.Orders/Chat", "/shop.v1.Orders/Upload"]
