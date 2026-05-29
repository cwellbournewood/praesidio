# Lineage view — manual smoke checklist

The lineage detail page (`/lineage/<request_id>`) is wired to the gateway
endpoint `GET /admin/lineage/{request_id}`. The bare `/lineage` route lists
the most recent request IDs that have lineage rows for the current tenant.

## Required behaviour

| # | Scenario | Expected |
|---|---|---|
| 1 | Visit `/lineage` with no data in the database | Empty-state card with link to the audit docs, no console errors. |
| 2 | Visit `/lineage` after at least one request has flowed through the gateway | List of recent `request_id`s, each linked to its detail view; "X ago" timestamps render. |
| 3 | Visit `/lineage/does-not-exist` | Empty-state card "No lineage recorded for this request." — NOT a 404. |
| 4 | Visit `/lineage/<known_id>` while gateway is down | "Could not load lineage…" error card with Retry button; clicking Retry refetches. |
| 5 | Visit `/lineage/<known_id>` with valid data | DAG renders; node count chips in the header match `nodes.length` by kind. |
| 6 | Click a node | The right-hand "Node detail" card fills in with kind, id, meta. Node id is copied to the clipboard with an aria-live announcement. |
| 7 | Press Tab to focus the graph | First node receives a visible focus ring; further Tab cycles through nodes. |
| 8 | With focus inside the graph, press ↓ / → | Focus moves to the next node in DOM order. ↑ / ← move backward. Home / End jump to first / last. |
| 9 | With a node focused, press Enter | The node selects (right-hand card updates) and the id is copied. |
| 10 | When a node with `audit_event_id` is selected | "Open in events" link appears in the detail card and deep-links to `/events?id=<event_id>`. |
| 11 | Hover an edge | Edge changes from dashed grey to solid indigo; relation label is legible against both light and dark themes. |
| 12 | Reload with `?lang=es` query | Headings ("Linaje", "Atrás", etc.) render in Spanish — proves the i18n wiring on this route. |

## A11y / contrast

* AA contrast on every chip and label in both `data-theme="light"` and `data-theme="high-contrast"`.
* `aria-live="polite"` region announces "Copied node …" without stealing focus.
* No mouse-only affordances; every node is reachable by keyboard, every edge label is rendered as text (not just a path).
* The detail card uses semantic `<dl>` / `<dt>` / `<dd>`.

## Performance

* `LineageGraph` is `React.lazy`-loaded (V5) so it doesn't ship in the initial dashboard bundle.
* The layout algorithm is a simple longest-path layering — O(N + E). For N > ~80 nodes consider swapping in `elkjs` (commented out in the future-work section of the V3 design doc).
