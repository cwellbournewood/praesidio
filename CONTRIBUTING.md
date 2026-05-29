# Contributing to Praesidio

Thanks for considering a contribution. Praesidio is a security control
plane — quality and clarity matter more than speed.

## Ground rules

1. **One change, one PR.** Don't bundle refactors with features.
2. **Discuss large changes first** by opening an issue or RFC under
   `docs/rfc/` (template provided).
3. **Tests are required** for any change to detection, policy evaluation,
   anonymisation, audit, or routing logic.
4. **Architecture decisions go in `docs/adr/`.** Use the existing
   template; assign the next number.

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

Commits must be DCO-signed (`git commit -s`). Release artefacts
(container images, policy bundles, SBOM) are signed with cosign.

## Code of Conduct

By participating you agree to the [Contributor Covenant](CODE_OF_CONDUCT.md).
