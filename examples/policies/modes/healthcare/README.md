# Healthcare Mode — Reference Implementation

This directory is the **reference mode bundle** for Section. It demonstrates
the full set of files described in the
[Mode Authoring Guide](../../../../docs/modes/mode-authoring-guide.md).

## Use cases

| Workflow                          | What this mode does                                          |
|-----------------------------------|--------------------------------------------------------------|
| Clinical assistant / scribe       | Tokenises patient identifiers; re-IDs on clinician read-back |
| Discharge-summary drafting        | Reversible tokens; bounded session TTL                       |
| De-identification for analytics   | Strict overlay → all 18 Safe Harbor categories redacted      |
| Adverse-event triage              | Irreversible redaction + audit escalation                    |
| 42 CFR Part 2 (SUD records)       | Hard-block unless caller is `treating-physician`             |

## What this mode *does not* do

- It does not assert that downstream use is HIPAA-compliant — that is a
  property of the entire system, not of any one component.
- It does not perform full Safe Harbor de-identification certification — that
  requires an expert determination (45 CFR §164.514(b)(1)) in addition to
  rule-based tokenisation.
- It does not handle DICOM images or other binary clinical data — text only.

## Loading the mode

Add to your bundle manifest:

```yaml
# examples/policies/manifest.yaml
spec:
  modes:
    - modes/healthcare/mode.yaml
  overlays:
    - strict           # optional — switches default action from tokenise to redact
```

## Running the eval suite

```bash
make eval-mode MODE=healthcare
```

Pass threshold: **≥ 95%** accuracy across the suite. Any failure in a
`block`-action test counts as a hard failure regardless of overall score.

## Known limitations

- **NPI detection** has score 0.55 and relies on context boost — bare
  10-digit strings without context words will not fire. This is intentional;
  raise the base score only if your tenant has high-recall requirements and
  accepts more false positives on phone-number-shaped strings.
- **ICD-10 / CPT** patterns can over-fire on free-text alphanumerics. They
  ship disabled in `strict` overlay scenarios where false positives are
  preferable to misses; enable for clinical assistants only.
- **Behavioural-health classifier** is on-prem only (`ollama/llama3.1-70b`).
  Cloud LLM classification of Part-2 content is not supported.
