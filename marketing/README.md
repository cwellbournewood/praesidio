# Praesidio — Marketing Assets

LinkedIn announcement kit for the Praesidio v1.0 release.
Brand: **Praesidio "Instrument"** — bone canvas + ink text + a single vermillion accent,
hairlines instead of shadows, sharp corners, Instrument Serif italic for display +
the `§` mark, JetBrains Mono for data, Geist Sans for UI chrome.

All raster assets are rendered at **2× retina** from self-contained HTML pages.
Source HTML lives in `services/ui/public/marketing/` and is served by the dev
server during builds — see [Re-rendering](#re-rendering) below.

---

## Assets

### LinkedIn — link preview & feed posts (`linkedin/`)

A 1200×627 link-preview hero plus a 7-slide 1080×1080 carousel. Posted in order,
they read as a single announcement story: cover → problem → solution → policy
→ audit → providers → call to action.

| # | File | Use | Dimensions |
|---|---|---|---|
| — | `01-hero.png`      | LinkedIn link-preview / OG image / page header | 1200×627 |
| 1 | `02-cover.png`     | Carousel slide 1 — cover / brand                | 1080×1080 |
| 2 | `03-problem.png`   | Carousel slide 2 — the problem                  | 1080×1080 |
| 3 | `04-tokenise.png`  | Carousel slide 3 — tokenisation in action       | 1080×1080 |
| 4 | `05-policy.png`    | Carousel slide 4 — policy as code (YAML + CEL)  | 1080×1080 |
| 5 | `06-audit.png`     | Carousel slide 5 — audit + hash-chained lineage | 1080×1080 |
| 6 | `07-providers.png` | Carousel slide 6 — multi-provider routing       | 1080×1080 |
| 7 | `08-cta.png`       | Carousel slide 7 — get started / OSS            | 1080×1080 |

### Figures (`figures/`)

Wide format diagrams for long-form posts, the README, or blog/landing usage.

| File | Subject | Dimensions |
|---|---|---|
| `architecture.png`  | Fig. 1 — Request flow through the gateway (client → detect → decide → transform → route → upstream; restore-stream return; hash-chained audit rail) | 1600×1000 |
| `tokenisation.png`  | Fig. 2 — Tokenisation: vault round-trip, FPE, redact (before/after + vault row + restored response) | 1600×900 |

### Live UI captures (`ui-screenshots/`)

Headless-Chrome captures of the running console at 1440×900. The tool, in
action, with mock data. All show the live globals.css tokens — no Photoshop
polish.

| File | Page | URL captured |
|---|---|---|
| `overview.png`         | The masthead `i. Overview` dashboard with KPIs, throughput, top detectors, live tape | `/` |
| `onboarding.png`       | First-run path picker (Local demo · Self-hosted · Kubernetes) | `/onboarding` |
| `events.png`           | `ii. Events` — the audit/decision log with decision dots, principal, detector, latency | `/events` |
| `simulator.png`        | `§ Simulator` — paste-prompt → preview decision, with samples | `/simulator` |
| `policies.png`         | `iii. Policies` — pii-strict / code-protection / healthcare-phi cards | `/policies` |
| `models.png`           | `v. Models` — registry of upstreams with jurisdiction, certifications, routes | `/models` |
| `recommendations.png`  | `iv. Recommendations` — evidence-driven overlays adoptable as PRs | `/recommendations` |

---

## Brand quick-reference

| Token | Value | Role |
|---|---|---|
| bone (canvas)   | `#EFEAE0` | Background |
| ink             | `#0F0F0E` | Primary text |
| graphite        | `#3A352E` | Secondary text |
| dust            | `#7A7367` | Tertiary / metadata |
| rule            | `#C9C3B5` | Hairlines, borders |
| vermillion      | `#D14B2C` | **The only accent.** Use sparingly. |
| moss            | `#3B5F3B` | Verdict: allow |
| sienna          | `#A8541C` | Verdict: warn |
| Instrument Serif | display, italic, `§` mark | |
| Geist Sans       | UI chrome | |
| JetBrains Mono   | data, IDs, latencies, eyebrows | |

Sharp corners everywhere (radius 0). Hairlines, not shadows.
One accent: vermillion. If a second colour feels needed, the answer is: don't.

---

## Re-rendering

The source HTML for the hero, carousel slides, and figures lives in:

```
services/ui/public/marketing/
├── carousel.css                  # shared styles
├── hero.html
├── slide-1-cover.html …          # one file per carousel slide
├── slide-7-cta.html
├── figure-architecture.html
└── figure-tokenisation.html
```

Re-render any asset with headless Chrome at 2× retina:

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"

# 1200×627 hero
"$CHROME" --headless=new --hide-scrollbars --no-sandbox \
  --window-size=1200,627 --force-device-scale-factor=2 \
  --virtual-time-budget=8000 \
  --screenshot=marketing/linkedin/01-hero.png \
  http://localhost:3010/marketing/hero.html

# 1080×1080 carousel slide
"$CHROME" --headless=new --hide-scrollbars --no-sandbox \
  --window-size=1080,1080 --force-device-scale-factor=2 \
  --virtual-time-budget=8000 \
  --screenshot=marketing/linkedin/02-cover.png \
  http://localhost:3010/marketing/slide-1-cover.html
```

`virtual-time-budget=8000` is needed because the slides pull Instrument Serif
from Google Fonts — fewer ms and the headline falls back to Georgia.

The dev server runs on **port 3010** (not 3000 — taken by the launchpad).
Confirm with `mcp__Claude_Preview__preview_list` or `curl localhost:3010`.

---

## Suggested post sequence

1. **Single post + link preview** — caption + `01-hero.png` linked to the repo.
2. **Carousel** — drop slides 1–7 (`02-cover.png` through `08-cta.png`) in order
   as a LinkedIn document/PDF carousel.
3. **Long-form article** — embed `figures/architecture.png` near the top and
   `figures/tokenisation.png` next to the tokenisation paragraph. Use any
   `ui-screenshots/*.png` inline as "the console" exhibits.

---

*Built 2026-05-29 against Praesidio v1.0. License: Apache 2.0 (same as Praesidio).*
