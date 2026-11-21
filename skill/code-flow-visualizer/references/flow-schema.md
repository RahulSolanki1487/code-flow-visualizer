# flow.json schema

```json
{
  "project": "shop-api",
  "generated_at": "2026-11-20",
  "flows": [
    {
      "id": "create_order",
      "title": "POST /orders – create order",
      "mode": "code",
      "diagram": "flowchart",
      "direction": "TD",
      "summary": "Validates the cart, reserves stock, charges the card and stores the order.",
      "entry": "orders_route",
      "nodes": [
        {
          "id": "orders_route",
          "label": "POST /orders",
          "type": "entry",
          "file": "src/routes/orders.js",
          "line": 12,
          "description": "Express route; applies auth middleware then calls the controller.",
          "snippet": "router.post('/orders', auth, ordersController.create)",
          "inferred": false,
          "note": ""
        }
      ],
      "edges": [
        { "from": "orders_route", "to": "create_ctrl", "label": "calls", "inferred": false, "kind": "normal" }
      ],
      "notes": ["Payment retries are configured in env, not visible in code."]
    }
  ]
}
```

## Fields

### Flow
| Field | Required | Notes |
|---|---|---|
| `id` | yes | unique, snake_case |
| `title` | yes | shown in sidebar and header |
| `mode` | yes | `code` or `user` |
| `diagram` | no | `flowchart` (default) or `sequence` |
| `direction` | no | flowchart only: `TD` (default) or `LR` |
| `summary` | yes | 1–3 sentences |
| `entry` | yes | node id of the starting node |
| `nodes` | yes | list |
| `edges` | yes | list |
| `participants` | sequence only | ordered node ids used as lifelines; defaults to node order |
| `notes` | no | risks, assumptions, inferred behaviour |

### Node
| Field | Required | Notes |
|---|---|---|
| `id` | yes | unique within flow |
| `label` | yes | ≤ 40 chars |
| `type` | yes | `entry, logic, data, external, decision, error, ui, event` |
| `file` | yes* | repo-relative path (*optional only for `external` nodes) |
| `line` | yes* | 1-based |
| `description` | yes | what happens and why |
| `snippet` | no | ≤ 8 lines of real code |
| `inferred` | no | default `false` |
| `note` | no | why inferred / caveats |
| `link_to` | no | id of another flow this node expands into |

### Edge
| Field | Required | Notes |
|---|---|---|
| `from`, `to` | yes | node ids |
| `label` | no | e.g. `calls`, `on error`, `yes`, `await` |
| `kind` | no | `normal` (default), `error`, `async` |
| `inferred` | no | rendered dashed |
| `order` | sequence only | number; defaults to list order |
