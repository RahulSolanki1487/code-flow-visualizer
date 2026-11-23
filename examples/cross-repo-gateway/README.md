# Gateway demo (synthetic)

Three tiny repos behind one gateway, to test frontend <-> backend linking when the URL the frontend
calls is not the URL the backend serves:

```
web/          Angular app; every call goes to the gateway: /orders-svc/... and /billing-svc/...
gateway/      nginx.conf: strips the service prefix and forwards to the right service
orders-api/   Express; serves /api/v1/orders...
billing-api/  Spring Boot; serves /api/v1/invoices... and /api/v1/payments
```
Frontend `POST /orders-svc/api/v1/orders`  ->  gateway strips `/orders-svc`  ->  orders-api `POST /api/v1/orders`.
Not runnable: only the files needed for tracing are included.
