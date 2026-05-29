# Maintainers

Praesidio is governed as an open project. This page lists the people
responsible for the codebase, explains how to become a committer, and
documents the Code of Conduct enforcement chain.

## Current maintainers

| Name | GitHub | Areas | Joined |
|---|---|---|---|
| Connor (project lead) | `@connor` *(placeholder — replace before first GitHub release)* | All | 2026-05 |

> This list is intentionally small at 1.0. The roadmap commits to growing
> it to at least three maintainers before declaring 1.1 GA — see
> [`docs/roadmap.md`](roadmap.md).

### What a maintainer does

* Reviews and merges PRs into `main`.
* Cuts releases per [`docs/release-process.md`](release-process.md) *(Lane D)*.
* Triages issues into the GitHub Projects board within 5 business days.
* Approves additions to the policy DSL, audit-row schema, or HTTP API
  (each requires an ADR — see [`docs/adr/`](adr/)).
* Holds an Apache-style **PMC vote** (lazy consensus by default; ±1
  votes if anyone objects) for breaking changes.

## Becoming a maintainer

We follow a *contribution-first*, two-stage path:

### Stage 1 — Committer

You become a **committer** (write access to a single lane / package)
after the existing maintainers agree, typically when you:

* Have authored ≥ 5 merged non-trivial PRs in the relevant area in the
  last 6 months.
* Have triaged or reviewed at least 10 issues / PRs by other people.
* Have signed the DCO on every commit (see [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
* Are nominated by an existing maintainer on a GitHub Discussion;
  approval is by lazy consensus (no objections in 7 days).

### Stage 2 — Maintainer

You become a **maintainer** (write access to all lanes, vote on
breaking changes) after a further 6 months of committer activity, on
nomination by an existing maintainer, approved by a ±1 vote of all
current maintainers with no veto.

### Emeritus

A maintainer who is inactive for 12 months is moved to **emeritus**
status (read-only on the org). They can return by request — we don't
re-run the process.

## Code of Conduct enforcement chain

Praesidio adopts the [Contributor Covenant 2.1](../CODE_OF_CONDUCT.md)
unmodified.

| Step | Who | When |
|---|---|---|
| 1 | Any maintainer | First report; private DM or email to `conduct@praesidio.example` *(placeholder)* |
| 2 | CoC committee (≥ 2 maintainers, not the reporter, not the subject) | Triage, gather facts, decide remediation within 14 days |
| 3 | Project lead | Final escalation if the committee is split |
| 4 | External mediator (TBD, e.g. a Linux Foundation neutral) | Reserved for cross-project disputes; 1.1 milestone |

Decisions are documented in `governance/coc-decisions/` (private
repo — `@connor` has access; transcripts of public actions are mirrored
to `docs/governance/` after redaction).

## Vendor / sponsor relationships

Maintainers may be employed by companies that ship Praesidio
commercially. To preserve neutrality:

* No single employer holds a majority of maintainer seats. If a hire
  or departure would breach this, the affected maintainer voluntarily
  steps down or moves to emeritus.
* Sponsorship is welcome via [GitHub Sponsors](https://github.com/sponsors/praesidio-project)
  *(placeholder)* and is publicly disclosed in `SPONSORS.md` once that
  file exists.
* Sponsorship does **not** grant roadmap influence beyond what any
  community member has. Sponsors get a "thank you" line; that's it.

## Decision making in practice

Most decisions are made by **lazy consensus** on the PR or discussion.
The bar rises with blast radius:

| Decision | Mechanism |
|---|---|
| Bug fix, doc, test | Lazy consensus on PR — one maintainer approval merges |
| New feature behind a flag | Lazy consensus on PR + roadmap entry |
| Stable API surface change | ADR + ±1 vote of maintainers |
| Breaking change | ADR + ±1 vote of maintainers, no vetoes |
| CoC remediation | CoC committee, see chain above |
| Security disclosure | [`SECURITY.md`](../SECURITY.md) coordinated disclosure |

## Contact

* General questions: GitHub Discussions.
* Security: see [`SECURITY.md`](../SECURITY.md).
* Conduct: `conduct@praesidio.example` *(placeholder)*.
