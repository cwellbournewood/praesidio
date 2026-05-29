# Design System — Praesidio

> Trustworthy AI, at enterprise scale.

The design system is light-first, calm, and instrument-like. It is meant to feel
the way a CT scanner UI feels: precise, legible, never decorative for its own
sake. The visual language draws from Linear, Vercel, Stripe Docs, and Datadog APM
— but warmer, with paper-white backgrounds rather than the typical dark
"security tool" aesthetic. Praesidio operators stare at this UI for hours; it
needs to be a place to *live*, not a place to react.

## 1. Brand

| | |
|---|---|
| Name | **Praesidio** |
| Etymology | Latin *praesidium* — garrison, protection, escort |
| Tagline | *Trustworthy AI, at enterprise scale.* |
| Voice | direct, technical, never breathless. Sentences end. |
| Anti-voice | "leverage", "synergy", "next-gen", "AI-powered" |

## 2. Colour tokens

The palette is structured as semantic intent first, hue second. Every token
has a `bg-`, `fg-`, and `border-` variant in code.

### Light (default)

| Token | Hex | Use |
|---|---|---|
| `canvas` | `#FAFAF7` | Page background — warm ivory, not pure white |
| `surface` | `#FFFFFF` | Cards, panels, table surfaces |
| `surface-sunken` | `#F4F4F0` | Code blocks, inset wells |
| `surface-raised` | `#FFFFFF` | Modals, popovers (with shadow) |
| `border` | `#E5E5E0` | Default 1px dividers |
| `border-strong` | `#D4D4CE` | Emphasised dividers |
| `text-primary` | `#0F172A` | Headings, primary body |
| `text-secondary` | `#475569` | Labels, captions |
| `text-tertiary` | `#94A3B8` | Placeholder, disabled |
| **`accent`** | **`#4F46E5`** | **Primary action — indigo** |
| `accent-hover` | `#4338CA` | Hovered primary |
| `accent-soft` | `#EEF2FF` | Selection backgrounds, highlight chips |
| `success` | `#059669` | Allowed, healthy, compliant |
| `success-soft` | `#ECFDF5` | |
| `warn` | `#D97706` | Transformed, degraded, attention |
| `warn-soft` | `#FFFBEB` | |
| `block` | `#DB2777` | Blocked by policy (chosen distinct from danger) |
| `block-soft` | `#FDF2F8` | |
| `danger` | `#B91C1C` | Errors, irreversible actions |
| `danger-soft` | `#FEF2F2` | |
| `info` | `#0EA5E9` | Neutral metadata, links |

### Dark (opt-in via `data-theme="dark"`)

| Token | Hex |
|---|---|
| `canvas` | `#0B0F1A` |
| `surface` | `#111827` |
| `surface-sunken` | `#0B0F1A` |
| `surface-raised` | `#1F2937` |
| `border` | `#1F2937` |
| `border-strong` | `#374151` |
| `text-primary` | `#F8FAFC` |
| `text-secondary` | `#CBD5E1` |
| `text-tertiary` | `#64748B` |
| `accent` | `#818CF8` |
| `accent-soft` | `#1E1B4B` |
| `success` | `#34D399` |
| `warn` | `#FBBF24` |
| `block` | `#F472B6` |
| `danger` | `#F87171` |
| `info` | `#38BDF8` |

## 3. Typography

| Role | Family | Weight | Tracking |
|---|---|---|---|
| UI text | **Geist Sans** (fallback: Inter, system-ui) | 400 / 500 / 600 | -0.005em |
| Code & data | **Geist Mono** (fallback: JetBrains Mono, ui-monospace) | 400 / 500 | 0 |
| Display (rare) | Geist Sans | 600 | -0.02em |

**Scale (1.125 minor third):**

```
xs   12 / 16
sm   13 / 18
base 14 / 20      ← UI default; this is dense, scan-friendly
md   16 / 24
lg   18 / 26
xl   20 / 28
2xl  24 / 32
3xl  32 / 40
4xl  40 / 48      ← page titles
```

UI default is 14px. The interface is for analysts; density matters more than
display flair.

## 4. Spacing & layout

4px base grid. Use `space-0 .. space-16` (multiples of 4). Page gutter `24px`
mobile, `40px` desktop. Sidebar `260px`. Maximum content width `1440px`.

## 5. Elevation

Praesidio avoids heavy shadows. Three levels only:

```css
--shadow-low:   0 1px 2px 0 rgb(15 23 42 / 0.04);
--shadow-mid:   0 4px 12px -2px rgb(15 23 42 / 0.06),
                0 2px 4px -2px rgb(15 23 42 / 0.04);
--shadow-high:  0 12px 32px -8px rgb(15 23 42 / 0.12),
                0 4px 8px -4px rgb(15 23 42 / 0.06);
```

Borders do most of the structural work; shadows are reserved for things that
float (modals, popovers, dragged items).

## 6. Radius

```
xs   2px   inline chips, indicator dots
sm   4px   inputs, small buttons
md   6px   cards, table rows
lg   10px  panels, dialogs
xl   14px  full-screen sheets
pill 999px badges
```

## 7. Motion

Motion is structural, not ornamental. `prefers-reduced-motion` is honoured.

```
duration-fast    120ms   property changes, hover
duration-base    180ms   panel enter/exit
duration-slow    320ms   modal, drawer
ease-standard    cubic-bezier(0.2, 0, 0, 1)
ease-emphasised  cubic-bezier(0.3, 0, 0, 1)
```

## 8. Iconography

[Lucide](https://lucide.dev), 1.5px stroke, 16px or 20px. Icons match the
weight of surrounding text. Never use icons without a label except for
universally understood affordances (close, search, sort).

## 9. Components (shadcn-style primitives in `services/ui/components/ui/`)

`Button`, `Input`, `Select`, `Textarea`, `Switch`, `Checkbox`, `Radio`,
`Badge`, `Tag`, `Tabs`, `Card`, `Dialog`, `Sheet`, `Popover`, `Tooltip`,
`Toast`, `Table`, `Pagination`, `Skeleton`, `Avatar`, `Progress`,
`Separator`, `Breadcrumb`, `Command` (cmd-k palette), `DataTable`,
`KeyValue`, `EmptyState`.

### Domain components (`services/ui/components/praesidio/`)

| Component | Purpose |
|---|---|
| `EventRow` | one inspection event in the live feed |
| `EventDetail` | full drawer: principal, findings, policy hit, decision, request/response diff |
| `FindingChip` | colour-coded entity badge (PERSON, EMAIL, SECRET, CODE…) |
| `DecisionBadge` | allow / transform / block / error |
| `RedlineDiff` | side-by-side payload showing what was redacted/tokenised |
| `PolicyEditor` | YAML editor with live validation and dry-run |
| `LineageGraph` | node/edge view of a request's provenance chain |
| `ModelCard` | registry entry: provider, region, certifications, route policy |
| `MetricSpark` | tiny inline sparkline (no axis chrome) |

## 10. Decision colour conventions (used everywhere)

| Decision | Token | Glyph |
|---|---|---|
| Allowed unmodified | `success` | `●` |
| Allowed with transform | `warn` | `◐` |
| Blocked by policy | `block` | `■` |
| System error / fail-open | `danger` | `▲` |
| Dry-run (simulated) | `info` | `◇` |

These are global. The same colour means the same thing on every page.

## 11. Accessibility

- Minimum contrast AA on all text (4.5:1 body, 3:1 ≥18pt).
- Focus rings are 2px `accent` with 2px offset, *never* removed.
- All interactive elements reachable by keyboard; cmd-k for everything.
- Status communicated by text + colour + shape, never colour alone.
- `prefers-reduced-motion`, `prefers-color-scheme` respected.
- ARIA live regions for the event stream.

## 12. Empty states

Every list view has a designed empty state — a single short sentence, a
useful next action, and a link to the relevant doc. Never a sad cloud.

## 13. Tokens implementation

All tokens live in `services/ui/styles/tokens.css` and are surfaced to
Tailwind via `tailwind.config.ts`. Components reference *semantic* tokens
(`bg-surface`, `text-primary`) not raw hexes.
