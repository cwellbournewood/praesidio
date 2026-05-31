# Demo prompts

Hand-picked prompts to exercise the gateway end-to-end. Each file is a
ready-to-POST JSON body for `/v1/chat/completions`.

| File | Triggers | Expected decision |
|---|---|---|
| `01-pii-tokenisation.json` | PERSON, EMAIL | transform (tokenise) |
| `02-secret-block.json` | secrets.aws | **block** |
| `03-iban-redact.json` | financial.iban | transform (redact) |
| `04-multi-entity.json` | PERSON, EMAIL, PHONE | transform (tokenise + FPE) |

## Run

```bash
export GATEWAY=http://localhost:8080
export KEY=section-demo-key

for f in examples/demo-prompts/0*.json; do
  echo "==> $f"
  curl -sS -H "Authorization: Bearer $KEY" \
       -H "Content-Type: application/json" \
       -d @"$f" \
       "$GATEWAY/v1/chat/completions" | head -c 400; echo
done
```

Or use `scripts/demo.sh` which adds assertions.
