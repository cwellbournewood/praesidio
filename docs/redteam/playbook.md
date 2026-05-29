# Red-team playbook (excerpt)

A short, public excerpt of the internal red-team playbook used to validate
Praesidio's detectors and policy enforcement. Full suite lives in a
separate internal repository.

## Goals

For each attack class, validate that:
1. The detector fires (true positive on the malicious sample),
2. The decision is correct (block / transform per policy),
3. The audit row is written with the right severity,
4. The placeholder (if any) is correctly restored on the way out without
   leaking the original.

## Attack classes

### 1. PII obfuscation
- zero-width chars between digits of an SSN
- homoglyph substitution in names (Cyrillic `а` for Latin `a`)
- base64 / hex / rot-N around a credit card

### 2. Secret exfiltration
- AWS access key split across two paragraphs
- private key with custom PEM markers
- API key inside a code block

### 3. Prompt injection
- "ignore previous instructions"
- indirect injection via fetched web content
- multi-language injection (German, Chinese)

### 4. Jailbreak
- DAN-family templates
- roleplay-to-bypass
- few-shot priming

### 5. Streaming-boundary
- placeholder that lands exactly on the SSE chunk boundary
- placeholder that is malformed by the upstream

### 6. Agent capability escalation (architected)
- tool argument injection
- chained-tool data shuttle (read → encode → send via "innocent" tool)

### 7. Vector / RAG (architected)
- cross-tenant retrieval probe
- embedding inversion
- stale-PII recall

## Running

```bash
# requires Praesidio running locally
cd bench/redteam
uv run python run.py --target http://localhost:8080 --policy pii-strict
```

Output: per-class pass/fail with detector versions and policy bundle digest.
