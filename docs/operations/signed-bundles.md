# Signed policy bundles

Praesidio policy bundles are the source of truth for what gets blocked,
transformed, or allowed. Because they're security-critical, they are
distributed as **signed OCI artefacts**: the gateway will refuse to load
a bundle whose signature it cannot verify against an expected identity.

This page covers:

1. [Bundle format](#bundle-format)
2. [Publishing (keyless Fulcio + GHCR)](#publishing-with-cosign-and-ghcr)
3. [Verifying out-of-band](#verifying-out-of-band)
4. [Gateway consumption](#gateway-consumption)
5. [Production rollout pattern](#production-rollout-pattern)

## Bundle format

A policy bundle is a directory of YAML files:

```
examples/policies/
├── manifest.yaml          # bundle version, name, description
├── models.yaml            # upstream model registry
├── routes.yaml            # path -> policy binding
└── policies/
    ├── 0001-pii-strict.yaml
    ├── 0002-code-protection.yaml
    └── 0100-healthcare.yaml
```

Bundles are packaged as a deterministic tar archive (sorted entries,
zero owner / group / mtime) with media type
`application/vnd.praesidio.policy-bundle.v1+tar`, then pushed to an OCI
registry. Cosign produces a separate signature/certificate pair stored
alongside the artefact (the standard Sigstore layout).

## Publishing with cosign and GHCR

The repo ships `scripts/policy_publish.sh` for one-shot publish + sign:

```bash
# Default: ./examples/policies -> ghcr.io/praesidio/policies:<timestamp>
PRAESIDIO_POLICY_REPO=ghcr.io/<your-org>/policies \
  bash scripts/policy_publish.sh -t v1.0.0
```

The script:

1. Re-validates the bundle locally (`scripts/seed_policies.py --no-reload`).
2. Builds a deterministic tar.
3. Pushes via `oras` with the Praesidio media type.
4. Signs with `cosign sign` against the immutable digest reference.

### Keyless signing (recommended for OSS)

`cosign sign --yes` defaults to keyless: it requests a short-lived
certificate from **Fulcio** bound to your OIDC identity (GitHub
Actions, Google, GitHub, etc.) and records the signature in the
**Rekor** transparency log. There is no long-lived private key to
protect or rotate.

In CI, the identity used is the GitHub OIDC token of the workflow run,
producing certificates whose SAN extension looks like:

```
https://github.com/cwellbournewood/praesidio/.github/workflows/release.yml@refs/tags/v1.0.0
```

This identity is what the gateway will verify against (see below).

### KMS-backed signing (regulated environments)

If you must use a long-lived key (e.g. SOC 2 audit trail requires a
hardware-backed key), set:

```bash
COSIGN_KEY=awskms:///alias/praesidio-policy-signer  # or gcpkms://, hashivault://
```

`scripts/policy_publish.sh` honours `COSIGN_KEY` if set in the env.

## Verifying out-of-band

```bash
# Verify the most recent push by tag
cosign verify ghcr.io/<your-org>/policies:v1.0.0 \
  --certificate-identity-regexp 'https://github\.com/<your-org>/praesidio/\.github/workflows/release\.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

# Pull the archive, then verify the blob in an offline workflow
oras pull ghcr.io/<your-org>/policies:v1.0.0
cosign verify-blob bundle.tar \
  --signature bundle.tar.sig \
  --certificate bundle.tar.pem \
  --certificate-identity-regexp '.*@refs/tags/v1\.0\.0' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

If verification fails, `cosign` exits non-zero and the gateway must
refuse to load the bundle.

## Gateway consumption

The gateway-side OCI puller is implemented as part of lane A
(`services/gateway`); this lane provides the publish + verify side.

When `PRAESIDIO_POLICY_BUNDLE` starts with `oci://`, the gateway will:

1. Resolve the reference to an immutable digest.
2. Verify the cosign signature against
   `PRAESIDIO_POLICY_SIGNER_IDENTITY` (regex) and
   `PRAESIDIO_POLICY_SIGNER_ISSUER` (exact OIDC issuer URL).
3. Pull the tar, unpack to an ephemeral dir, and load.
4. Pin the digest in the audit chain so every decision is traceable
   back to the exact bundle bytes.

Required env vars:

| Variable | Example |
|---|---|
| `PRAESIDIO_POLICY_BUNDLE` | `oci://ghcr.io/your-org/policies:v1.0.0` |
| `PRAESIDIO_POLICY_SIGNER_IDENTITY` | `https://github.com/your-org/praesidio/.github/workflows/release.yml@.*` |
| `PRAESIDIO_POLICY_SIGNER_ISSUER` | `https://token.actions.githubusercontent.com` |
| `PRAESIDIO_POLICY_REFRESH_SECONDS` | `60` (poll interval; the gateway only swaps on digest change) |

The poller is debounced: a tag move to the same digest is a no-op; a
new digest causes verification, then atomic swap of the in-memory
policy set.

## Production rollout pattern

1. **PR**: policy authors open a PR against the canonical `policies/`
   directory in a separate repo.
2. **CI**: on merge to `main`, the release workflow tags a semver
   (`v1.4.2`) and publishes a signed bundle to GHCR.
3. **Staging**: staging gateway is pinned to a moving tag (e.g.
   `:staging`); the OIDC identity check ensures only releases from
   the trusted workflow are accepted.
4. **Canary**: a fraction of prod traffic is routed through a gateway
   pinned to the new digest; simulate-mode diffs are reviewed via
   `POST /admin/policy/diff`.
5. **Promote**: production gateway moves to the new pinned tag.
6. **Rollback**: re-pin to the previous digest. Because every audit
   row records the bundle digest, the decision boundary on rollback
   is exact.

## Threat model linkage

This control is the answer to the "malicious policy bundle" row in
[`docs/threat-model.md`](../threat-model.md): signing is enforced at
load time and the bundle digest appears in every audit row, so a
silent swap is detectable post-hoc even if a registry credential is
compromised.
