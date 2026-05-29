# 04 · Semantic DLP

## Pipeline

```
                              ┌─── fast lane (always on, ms) ───┐
   inbound text ──► tokenise ─┤  regex · secrets · keyword      ├──┐
                              └─────────────────────────────────┘  │
                              ┌─── nlp lane (default on) ───────┐  │
                              ┤  spaCy + Presidio analyzer       ├──┤── merge ──► Findings[]
                              └─────────────────────────────────┘  │
                              ┌─── semantic lane (opt-in) ──────┐  │
                              ┤  embedding similarity            ├──┤
                              ┤  ONNX intent classifier          ├──┘
                              └─────────────────────────────────┘
```

All lanes run concurrently. Slow detectors have a soft deadline (default
80ms); on miss they're skipped and the audit log marks the policy decision
`partial=true`.

## Detector taxonomy

| Family | Examples | Tech |
|---|---|---|
| **Regex** | email, phone, IBAN, NRIC, NHS#, IPv4/6, MAC, UUID, JWT, CC# (Luhn) | hyperscan-compatible patterns, falls back to `re2` |
| **Secrets** | AWS / GCP / Azure / Stripe / GitHub / Slack / OpenAI / Anthropic / SSH private keys / .pem / `.env` shapes | port of `detect-secrets` + Yelp signatures + custom |
| **NLP entities** | PERSON, LOCATION, ORG, DATE, NRP, MEDICAL_LICENSE, US_DRIVER_LICENSE, UK_NHS, AU_TFN, EU country PII | [Presidio Analyzer](https://github.com/microsoft/presidio) over spaCy `en_core_web_lg` |
| **Code** | language detection + symbol heuristics; flags repos with proprietary markers | `guesslang` ONNX |
| **Trade secret** | per-tenant lexicons + project-name dictionaries | bloom filter |
| **Financial** | account numbers, SWIFT/BIC, MICR, sort codes | regex + Luhn/IBAN check digit |
| **Prompt injection** | "ignore previous instructions", indirect injection patterns, base64/rot13 obfuscation peels | curated patterns + classifier |
| **Jailbreak** | DAN-family templates, roleplay-to-bypass, multi-language jailbreaks | classifier + signature DB |
| **Exfiltration intent** | "summarise all files in", "list all customers and their", repeated chunked retrieval | behavioural baseline + per-session counter |

## Finding shape

```python
class Finding(BaseModel):
    id: str                  # ULID
    label: str               # 'pii.email' | 'pii.person' | ...
    start: int               # char offset in the canonical request body
    end: int
    text_hash: str           # sha256 of matched text (raw text NEVER logged)
    confidence: float        # 0..1
    detector: str            # 'regex' | 'presidio' | 'secrets' | ...
    detector_version: str
    meta: dict               # detector-specific (e.g. entity subtype)
```

Raw matched substrings are *never* persisted. The audit log stores hashes.
The token vault stores the original only when reversal is required, encrypted
with a per-tenant key, with a TTL.

## False-positive controls

1. **Per-policy thresholds** — every label has a confidence cutoff.
2. **Context windows** — name detectors require an entity boundary,
   not a substring (`"Mr Smith"` → match; `"smithing"` → no).
3. **Allow-lists** — tenant-managed dictionaries of acceptable
   strings (own employees, product names) that suppress matches.
4. **Analyst feedback loop** — UI offers `mark as FP` on any finding;
   feedback flows to a per-tenant suppression list and (optionally) to
   the classifier's online-learning queue.
5. **Semantic similarity suppression** — when a candidate finding is
   semantically very close (cosine ≥ 0.92) to a recent allow-listed item,
   suppress.

Target false-positive rate **< 2%** on validated policies, measured against
`docs/benchmarks/fp-validation.md`.

## Multilingual

Presidio with multi-language models, plus a tenant-configurable list of
languages. The semantic classifier uses
`paraphrase-multilingual-MiniLM-L12-v2` (ONNX-exported, ~110MB).

## Multimodal (roadmap)

The same `Finding` shape covers image and audio findings. The pipeline has
typed lanes for `image/*` (OCR via Tesseract → text lane) and `audio/*`
(Whisper-small → text lane). Documented in
[`07-agent-governance.md`](07-agent-governance.md#multimodal).

## Output DLP

The same pipeline runs on streamed model output (in a sidecar coroutine so
it doesn't add to user-visible TTFB). Detects:
- training-data regurgitation (semantic match against known sensitive corpora);
- new entity types appearing in output that weren't in input (suggests model
  hallucination of private data — rare but auditable);
- prompt-leak echoing (model emitting the system prompt).
