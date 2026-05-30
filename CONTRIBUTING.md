# Contributing to Praesidio

Thanks for considering a contribution. Praesidio is a security control
plane — quality and clarity matter more than speed.

## Ground rules

1. **One change, one PR.** Don't bundle refactors with features.
2. **Discuss large changes first** by opening an issue or proposing an ADR
   in `docs/adr/` using the existing template.
3. **Tests are required** for any change to detection, policy evaluation,
   anonymisation, audit, or routing logic.

## Local dev

```bash
git clone https://github.com/cwellbournewood/praesidio.git
cd praesidio
cp .env.example .env
make dev
```

Gateway: http://localhost:8080 · UI: http://localhost:3000

## Style

- Python: `ruff` + `ruff format` (config in `services/gateway/pyproject.toml`)
- TypeScript: `eslint` + `prettier`
- Conventional commits in PR titles (`feat(gateway): …`, `fix(dlp): …`).

## Signing

Commits must be DCO-signed (`git commit -s`). Release artefacts (container
images, Helm chart, policy bundles, SBOMs) are cosign-signed by the release
workflow.

## Code of Conduct

By participating you agree to the [Contributor Covenant](CODE_OF_CONDUCT.md).
Report concerns via [GitHub Private Vulnerability
Reporting](https://github.com/cwellbournewood/praesidio/security/advisories/new).
