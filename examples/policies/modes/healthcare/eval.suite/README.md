# Healthcare Mode — Eval Suite

Twelve gold-standard cases that exercise the healthcare mode end-to-end.

| #  | File                                  | Type     | Exercises                              |
|----|---------------------------------------|----------|----------------------------------------|
| 01 | discharge-summary                     | positive | regex.mrn, regex.dob, PERSON, DATE_TIME|
| 02 | ssn-redacted-not-tokenised            | positive | rule 4 (SSN redact)                    |
| 03 | credential-leak-blocked               | block    | rule 1 (secrets block)                 |
| 04 | part2-blocked-without-role            | block    | rule 2 (42 CFR Part 2 role check)      |
| 05 | part2-allowed-with-role               | positive | rule 2 inverse                         |
| 06 | adverse-event-irreversible            | positive | rule 3 (adverse-event redact)          |
| 07 | device-identifier                     | positive | regex.device_identifier, tenant scope  |
| 08 | negative-pure-protocol                | negative | no findings on generic clinical Q      |
| 09 | negative-icd10-no-context             | negative | over-firing guard                      |
| 10 | negative-npi-bare-digits              | negative | over-firing guard                      |
| 11 | break-glass-reidentify                | re-ID    | break-glass audit fields               |
| 12 | reidentify-denied-no-purpose          | re-ID    | TPO purpose enforcement                |

Coverage against the
[Mode Authoring Guide § 8](../../../../../docs/modes/mode-authoring-guide.md) minimums:

- ✅ ≥ 1 positive prompt per declared regex/classifier entity
- ✅ ≥ 3 negative prompts (08, 09, 10)
- ✅ ≥ 1 prompt per block-action rule (03, 04)
- ✅ ≥ 1 break-glass / re-identify prompt (11, 12)

## Running

```bash
make eval-mode MODE=healthcare
```

Pass threshold: ≥ 95% accuracy overall. Any failure in a `block`-action case
(03, 04, 12) is treated as a hard failure regardless of overall score.
