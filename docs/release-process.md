# Release process

The release pipeline is fully automated from a signed git tag, but the
human steps before and after the tag are worth following carefully. The
goals are: every release is reproducible, verifiable, and reversible.

## Cadence

* **Patch** (`0.1.x`) — as needed for security or stability fixes.
* **Minor** (`0.x.0`) — every 4–6 weeks during the 0.x line.
* **Major** (`x.0.0`) — coordinated with deprecation window
  (`docs/versioning.md`) and a public RFC.

## Pre-tag checklist

1. **All required CI is green on `main`.**
   - `ci`, `e2e`, `helm`, `helm-upgrade`, `codeql`, `scorecard`, `rls`,
     `admission`, `redteam` workflows must be passing on the commit you
     intend to tag.

2. **CHANGELOG is up to date.**
   - Move entries from `## [Unreleased]` into a new `## [x.y.z] — YYYY-MM-DD`
     heading at the top.
   - Add the version compare-link footnotes at the bottom.
   - Land this as a single PR titled `release: prepare vX.Y.Z`.

3. **Version bumps land in the same PR.**

   | File | Field |
   |---|---|
   | `services/gateway/pyproject.toml` | `[project] version = "x.y.z"` |
   | `services/ui/package.json` | `"version": "x.y.z"` |
   | `deploy/helm/praesidio/Chart.yaml` | `version: x.y.z` and `appVersion: "x.y.z"` |
   | `services/gateway/praesidio_gateway/main.py` | `FastAPI(... version="x.y.z" ...)` |

4. **Manually run** `bash scripts/demo.sh` against `docker compose up`
   from the release candidate commit. The 6/6 PASS line must show.

5. **Cosign / SLSA dry run.**
   - Push a release-candidate tag like `vX.Y.Z-rc.1`. The `release`
     workflow publishes `*-rc.N` images and chart, signs them, and
     attaches provenance — verify the artefacts using the commands in
     `docs/security/supply-chain.md`.

## Tagging

```bash
git checkout main
git pull
git tag -s "v$VERSION" -m "Praesidio v$VERSION"
git push origin "v$VERSION"
```

The `-s` flag signs the tag with your committer GPG key. If you do not
have one set up, use `-a` instead; the cosign keyless signature on the
artefacts is the source of trust either way, but a signed tag is a small
extra ground-truth.

## Automated post-tag

`.github/workflows/release.yml` fires on `v*.*.*` and:

1. Builds gateway + UI images for `linux/amd64` + `linux/arm64`, pushes
   to GHCR with tags `vX.Y.Z`, `vX.Y`, and `sha-<sha>`.
2. Cosign keyless-signs each image with the workflow OIDC identity.
3. Generates a CycloneDX SBOM per image (syft) and cosign-attests it.
4. Generates SLSA-3 build provenance per image
   (`slsa-framework/slsa-github-generator`).
5. Packages the Helm chart and pushes it to
   `oci://ghcr.io/<org>/charts/praesidio:vX.Y.Z`, cosign-signed.
6. Creates the GitHub Release with:
   - chart `.tgz`
   - per-image SBOM
   - `praesidio-release.sha256` checksum manifest
   - cosign-blob signature + cert for the manifest
   - auto-generated release notes (PRs since the previous tag)

## Manual post-tag

1. **Smoke-test the published images** on a real cluster (kind is fine):

   ```bash
   helm install praesidio oci://ghcr.io/cwellbournewood/charts/praesidio \
       --version "$VERSION" -n praesidio --create-namespace \
       -f deploy/helm/praesidio/values.production.yaml
   ```

2. **Verify the cosign signatures** following
   `docs/security/supply-chain.md`. Treat any verification failure as a
   release-blocker; revoke the GitHub Release (`gh release delete vX.Y.Z`)
   and dig in.

3. **Publish the docs site.** The `docs` workflow deploys
   `docs-site/` to GitHub Pages on every push to `main`; for a release we
   also publish a versioned snapshot under `/vX.Y/`.

4. **Cut the announcement.**
   - Update `README.md` Status badge if appropriate.
   - Discuss board: GitHub Discussions release thread.
   - Social: short post with the headline change and verification link.

## Rollback / yank

A bad release can be neutralised in two ways:

* **Soft yank** — publish `vX.Y.(Z+1)` reverting the offending change.
  Always preferred.
* **Hard yank** — delete the GitHub Release and the GHCR tag. The OCI
  image and chart remain accessible by digest for anyone who already
  pulled them; do not assume hard-yank removes them from the network.

Either way, file a `SECURITY ADVISORY` for the affected window
explaining the issue, the verification command users can run to detect
the bad version, and the upgrade path.

## Hotfix branches

For patches against an older minor:

```bash
git switch -c hotfix/0.2.x v0.2.4
# cherry-pick the fix
git tag -s v0.2.5 -m "Praesidio v0.2.5 (hotfix)"
git push origin v0.2.5 hotfix/0.2.x
```

The release pipeline picks it up from the tag exactly as for `main`.
