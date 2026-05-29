# Praesidio Admin UI

Next.js 14 (App Router) operator console for the Praesidio AI Security Control
Plane. Read-only by design: review events, browse policies, inspect lineage,
and check the model registry.

## Quick start

```bash
pnpm install
pnpm dev
```

The UI runs at <http://localhost:3000>. When no gateway is reachable, it
automatically falls back to synthetic data so every screen is interactive.

Force mock mode explicitly:

```bash
NEXT_PUBLIC_MOCK=1 pnpm dev
```

## Environment variables

| Variable | Where read | Purpose |
|---|---|---|
| `NEXT_PUBLIC_GATEWAY_URL` | browser & server | Base URL for `/admin/*` endpoints (defaults to `http://localhost:8080`). |
| `PRAESIDIO_GATEWAY_INTERNAL_URL` | server only | In-cluster service DNS, used by RSC fetches. |
| `NEXT_PUBLIC_MOCK` | browser | When set to `1`, all API calls return synthetic data. |

See `.env.example`.

## Scripts

| Command | What it does |
|---|---|
| `pnpm dev` | Local dev server with hot reload. |
| `pnpm build` | Production build (Next.js standalone output). |
| `pnpm start` | Run the built server on port 3000. |
| `pnpm lint` | `next lint`. |
| `pnpm format` | Prettier across the tree. |
| `pnpm type-check` | `tsc --noEmit`. |

## Layout

```
services/ui/
├── app/                       # Next.js routes (app router)
│   ├── layout.tsx             # root: fonts, providers, sidebar, topbar
│   ├── page.tsx               # /         dashboard
│   ├── events/page.tsx        # /events   table + detail drawer
│   ├── policies/page.tsx      # /policies
│   ├── policies/[id]/page.tsx
│   ├── lineage/[requestId]/page.tsx
│   ├── models/page.tsx
│   ├── settings/page.tsx
│   ├── providers.tsx          # theme, tooltip, toast, cmd-k providers
│   └── globals.css            # CSS variables for the design tokens
├── components/
│   ├── ui/                    # primitives (Button, DataTable, Sheet, …)
│   └── praesidio/             # domain (EventDetail, LineageGraph, …)
├── lib/
│   ├── api.ts                 # SWR fetcher + admin API client
│   ├── types.ts               # mirrors gateway pydantic models
│   ├── mock.ts                # synthetic dataset (200+ events, 3 policies)
│   └── utils.ts               # cn(), formatters, decision/family helpers
├── tailwind.config.ts         # tokens wired to Tailwind semantic names
├── next.config.mjs            # output: 'standalone'
└── Dockerfile                 # multi-stage, non-root, port 3000
```

## Adding a page

1. Create `app/<route>/page.tsx`. If it needs SWR, mark it `'use client'`.
2. Add it to `components/praesidio/Sidebar.tsx` if it should appear in the nav,
   and to `components/praesidio/CommandPalette.tsx` so it's reachable via ⌘K.
3. Fetch data through `swrFetcher` from `lib/api.ts` — never `fetch()` the
   gateway directly, so mock mode keeps working.

## Adding a primitive

1. New file in `components/ui/<name>.tsx`. Keep it ≤ 120 lines.
2. Use `class-variance-authority` for visual variants and `cn()` (from
   `lib/utils.ts`) to merge class names.
3. Reference semantic tokens (`bg-surface`, `text-primary`, `border-border`),
   not raw colours. The light/dark mapping lives in `app/globals.css`.
4. If the component is interactive, ensure a visible focus ring (Tailwind's
   `focus-visible:ring-2 ring-accent ring-offset-2`).

## Design system

The visual language is fully defined in
[`../../docs/design-system.md`](../../docs/design-system.md). In short:

- Light-first ivory canvas, indigo accent.
- 14px UI default, Geist Sans, -0.005em tracking.
- Decision colour conventions are global — same colour means the same thing
  on every page.
- Honours `prefers-reduced-motion`.

## Notes

- `next-themes` controls light/dark via `data-theme` on `<html>`.
- Authentication is delegated to the gateway; this UI assumes it sits behind
  the same OIDC perimeter as the admin API.
- Policy edits are not made in the UI — the policy bundle ships from git as
  signed YAML (see `docs/architecture/03-policy-engine.md`).
