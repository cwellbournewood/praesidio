# Section DLP — coverage matrix

_Last run: 2026-05-27T22:10:15.793588+00:00_

Per-detector precision / recall / F1, using **label-presence**
scoring (does the pipeline raise the expected label set for each
example?). Span-exact accuracy is reported separately in the JSON
artefact (`bench/eval/results/<utc>.json`) under the `rows` key.

## Corpus checksums

| Corpus | examples | sha256 |
|---|---:|---|
| `bench/eval/corpora/presidio_sample.jsonl` | 150 | `3b5e74b97eddc27c…` |
| `bench/eval/corpora/secrets.jsonl` | 50 | `e6688f361f12b96d…` |
| `bench/eval/corpora/redteam.jsonl` | 60 | `1f7ad9355f27b54b…` |

## Corpus: `presidio_sample`

Micro-averaged: precision=0.709, recall=0.923, F1=0.802 (tp=180, fp=74, fn=15)

| label | support | tp | fp | fn | precision | recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `financial.credit_card` | 12 | 11 | 2 | 1 | 0.846 | 0.917 | 0.880 |
| `pii.date` | 26 | 26 | 42 | 0 | 0.382 | 1.000 | 0.553 |
| `pii.email` | 12 | 9 | 0 | 3 | 1.000 | 0.750 | 0.857 |
| `financial.iban` | 11 | 9 | 0 | 2 | 1.000 | 0.818 | 0.900 |
| `network.ip_address` | 11 | 11 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `pii.location` | 17 | 16 | 3 | 1 | 0.842 | 0.941 | 0.889 |
| `healthcare.medical_license` | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 |
| `pii.person` | 18 | 17 | 5 | 1 | 0.773 | 0.944 | 0.850 |
| `pii.phone` | 12 | 11 | 3 | 1 | 0.786 | 0.917 | 0.846 |
| `pii.us_ssn` | 9 | 6 | 0 | 3 | 1.000 | 0.667 | 0.800 |
| `financial.credit_card` | 12 | 11 | 0 | 1 | 1.000 | 0.917 | 0.957 |
| `pii.email` | 12 | 12 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `financial.iban` | 11 | 11 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `network.ipv4` | 11 | 11 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `pii.phone` | 12 | 11 | 19 | 1 | 0.367 | 0.917 | 0.524 |
| `pii.us_ssn` | 9 | 8 | 0 | 1 | 1.000 | 0.889 | 0.941 |

## Corpus: `secrets`

Micro-averaged: precision=0.872, recall=0.944, F1=0.907 (tp=34, fp=5, fn=2)

| label | support | tp | fp | fn | precision | recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `credential.jwt` | 2 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.anthropic_api_key` | 3 | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.aws_access_key` | 7 | 5 | 0 | 2 | 1.000 | 0.714 | 0.833 |
| `credential.aws_secret_key` | 2 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.azure_storage_key` | 1 | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.gcp_service_account` | 2 | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.generic_high_entropy` | 2 | 2 | 2 | 0 | 0.500 | 1.000 | 0.667 |
| `credential.github_pat` | 4 | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.openai_api_key` | 3 | 3 | 3 | 0 | 0.500 | 1.000 | 0.667 |
| `credential.private_key` | 3 | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.slack_bot_token` | 3 | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `credential.stripe_api_key` | 4 | 4 | 0 | 0 | 1.000 | 1.000 | 1.000 |

## Corpus: `redteam`

Micro-averaged: precision=0.971, recall=0.773, F1=0.861 (tp=34, fp=1, fn=10)

| label | support | tp | fp | fn | precision | recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `behavior.injection_jailbreak` | 5 | 5 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| `behavior.injection_prompt_exfil` | 11 | 8 | 0 | 3 | 1.000 | 0.727 | 0.842 |
| `behavior.injection_ignore_previous` | 11 | 8 | 0 | 3 | 1.000 | 0.727 | 0.842 |
| `behavior.injection_system_override` | 7 | 4 | 1 | 3 | 0.800 | 0.571 | 0.667 |
| `behavior.injection_base64_tool_abuse` | 4 | 3 | 0 | 1 | 1.000 | 0.750 | 0.857 |
| `behavior.injection_role_swap` | 6 | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |

## How to reproduce

```bash
make eval                                   # full eval + regen this page
python bench/eval/run_eval.py               # same, explicit
python bench/eval/regression-check.py       # diff latest vs baseline
```

## Regression policy

`bench/eval/regression-check.py` fails CI when any per-label
**recall** drops more than 5 percentage points vs the committed
`bench/eval/baseline.json`. Precision regressions are reported but
do not gate the build (operators tune confidence thresholds in
their own policies).
