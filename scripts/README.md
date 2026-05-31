# scripts/

Helper scripts for development, demos, and release.

| Script | Purpose |
|---|---|
| `demo.sh` | End-to-end demo. Waits for the gateway to be healthy, sends three illustrative requests (PII transform, AWS-key block, IBAN redact), and asserts the audit-log decisions. Exits non-zero on any assertion failure. |
| `seed_policies.py` | Validates a policy bundle and POSTs `/admin/policies/reload`. Optional JSON-Schema validation if `schema.json` is present in the bundle. |
| `dev-keys.sh` | Generates dev-quality random values for `SECTION_VAULT_KEY`, `SECTION_FPE_KEY`, `SECTION_FPE_TWEAK` via `openssl rand`. **Dev only** — production keys come from KMS. |
| `sbom.sh` | Runs `syft` against the gateway and UI images and writes CycloneDX JSON to `dist/sbom-{gateway,ui}.cdx.json`. Prints an install hint and exits 0 if `syft` is missing. |

## Common usage

```bash
# 1. bring the stack up (in another terminal)
make dev

# 2. generate keys and put them in .env
scripts/dev-keys.sh > .env.local

# 3. seed policies
python scripts/seed_policies.py --bundle ./examples/policies --gateway http://localhost:8080

# 4. run the demo
make demo   # or: bash scripts/demo.sh

# 5. (release) generate SBOMs
scripts/sbom.sh
```

All shell scripts are POSIX-friendly bash and run under Git Bash on Windows.
