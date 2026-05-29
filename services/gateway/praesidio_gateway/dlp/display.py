"""Canonical display metadata for DLP labels.

Every finding the gateway emits carries a `label` string of the form
`<category>.<thing>` (e.g. `pii.organization`, `financial.credit_card`,
`credential.aws_access_key`). The label is **wire-stable** — policy
YAML, CEL expressions, audit history, and SIEM rules all key off it.

This module owns three things that *derive* from the label and ship
alongside it whenever a human will read the finding:

  * `name`        — short, sentence-cased human label
                    (e.g. "Organization name")
  * `short`       — UPPER_SNAKE placeholder fragment used by the
                    tokenizer, e.g. `ORGANIZATION` for
                    `<ORGANIZATION_A2F4>`
  * `category`    — one of the eight category buckets the UI groups by
  * `severity`    — default operator-facing severity hint
                    (policies can override the *decision* but the
                    severity here is the entity's intrinsic risk)
  * `description` — one-sentence operator-facing explanation
  * `example`     — optional masked-style example for tooltips

`LABELS` is the source of truth. `services/ui/lib/labels.ts` is its
TypeScript twin — `scripts/check_label_display_sync.py` runs in CI to
ensure they never drift.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Category = Literal[
    "pii",
    "financial",
    "healthcare",
    "credential",
    "network",
    "code",
    "infra",
    "behavior",
]

Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class LabelDisplay:
    """Human-readable metadata for one DLP label.

    The wire label is `id`. Everything else is for humans.
    """

    id: str
    name: str
    short: str
    category: Category
    severity: Severity
    description: str
    example: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Source of truth.
#
# Ordered by category so diffs read sensibly. The order is preserved in
# the UI's filter sidebar.
# ---------------------------------------------------------------------------

LABELS: dict[str, LabelDisplay] = {
    # ---- PII ---------------------------------------------------------
    "pii.person": LabelDisplay(
        id="pii.person",
        name="Person name",
        short="PERSON",
        category="pii",
        severity="medium",
        description="Name of a real person identified by named-entity recognition.",
        example="Jane Doe",
    ),
    "pii.organization": LabelDisplay(
        id="pii.organization",
        name="Organization name",
        short="ORGANIZATION",
        category="pii",
        severity="low",
        description="Named organization — company, government body, NGO, university.",
        example="Acme Corp",
    ),
    "pii.location": LabelDisplay(
        id="pii.location",
        name="Location",
        short="LOCATION",
        category="pii",
        severity="low",
        description="Place name — city, country, region, landmark.",
        example="San Francisco",
    ),
    "pii.email": LabelDisplay(
        id="pii.email",
        name="Email address",
        short="EMAIL",
        category="pii",
        severity="medium",
        description="RFC-5321 email address. Frequently doubles as a user identifier.",
        example="alice@acme.com",
    ),
    "pii.phone": LabelDisplay(
        id="pii.phone",
        name="Phone number",
        short="PHONE",
        category="pii",
        severity="medium",
        description="Telephone number in any of the common international or local formats.",
        example="+1 415 555 0123",
    ),
    "pii.date": LabelDisplay(
        id="pii.date",
        name="Date or time",
        short="DATE",
        category="pii",
        severity="low",
        description="Calendar date or time — useful context, but can identify when combined with other fields.",
        example="1985-03-21",
    ),
    "pii.nationality": LabelDisplay(
        id="pii.nationality",
        name="Nationality, religion, or political group",
        short="NATIONALITY",
        category="pii",
        severity="high",
        description=(
            "Presidio's NRP entity — nationality, religious affiliation, or "
            "political group. GDPR Article 9 special category."
        ),
        example="French",
    ),
    "pii.us_ssn": LabelDisplay(
        id="pii.us_ssn",
        name="US Social Security number",
        short="US_SSN",
        category="pii",
        severity="critical",
        description="US Social Security number — direct identifier, regulatory minefield.",
        example="123-45-6789",
    ),
    "pii.us_drivers_license": LabelDisplay(
        id="pii.us_drivers_license",
        name="US driver's licence",
        short="US_DRIVERS_LICENSE",
        category="pii",
        severity="high",
        description="US state driver's licence number.",
        example="D12345678",
    ),
    "pii.url": LabelDisplay(
        id="pii.url",
        name="URL",
        short="URL",
        category="pii",
        severity="low",
        description="URL — often a tracking link or contains identifiers in the query string.",
        example="https://acme.com/u/jane",
    ),
    # ---- Financial ---------------------------------------------------
    "financial.credit_card": LabelDisplay(
        id="financial.credit_card",
        name="Credit card number",
        short="CREDIT_CARD",
        category="financial",
        severity="critical",
        description="Payment card number, Luhn-validated. PCI-DSS scope when present.",
        example="4111 1111 1111 1111",
    ),
    "financial.iban": LabelDisplay(
        id="financial.iban",
        name="IBAN bank account",
        short="IBAN",
        category="financial",
        severity="high",
        description="International Bank Account Number — uniquely identifies a bank account.",
        example="DE89 3704 0044 0532 0130 00",
    ),
    # ---- Healthcare --------------------------------------------------
    "healthcare.medical_license": LabelDisplay(
        id="healthcare.medical_license",
        name="Medical licence number",
        short="MEDICAL_LICENSE",
        category="healthcare",
        severity="high",
        description="Medical practitioner licence identifier.",
        example="MD123456",
    ),
    # ---- Credentials -------------------------------------------------
    "credential.aws_access_key": LabelDisplay(
        id="credential.aws_access_key",
        name="AWS access key ID",
        short="AWS_ACCESS_KEY",
        category="credential",
        severity="critical",
        description="AWS access key identifier (AKIA / ASIA / AIDA / AROA prefix).",
        example="AKIAIOSFODNN7EXAMPLE",
    ),
    "credential.aws_secret_key": LabelDisplay(
        id="credential.aws_secret_key",
        name="AWS secret access key",
        short="AWS_SECRET_KEY",
        category="credential",
        severity="critical",
        description="40-character AWS secret access key, detected alongside its key id.",
    ),
    "credential.github_pat": LabelDisplay(
        id="credential.github_pat",
        name="GitHub personal access token",
        short="GITHUB_PAT",
        category="credential",
        severity="critical",
        description="GitHub PAT (`ghp_…`) or fine-grained PAT (`github_pat_…`).",
    ),
    "credential.openai_api_key": LabelDisplay(
        id="credential.openai_api_key",
        name="OpenAI API key",
        short="OPENAI_KEY",
        category="credential",
        severity="critical",
        description="OpenAI secret key (`sk-…`).",
    ),
    "credential.anthropic_api_key": LabelDisplay(
        id="credential.anthropic_api_key",
        name="Anthropic API key",
        short="ANTHROPIC_KEY",
        category="credential",
        severity="critical",
        description="Anthropic secret key (`sk-ant-…`).",
    ),
    "credential.slack_bot_token": LabelDisplay(
        id="credential.slack_bot_token",
        name="Slack bot or user token",
        short="SLACK_TOKEN",
        category="credential",
        severity="high",
        description="Slack token (`xoxb-…` / `xoxa-…` / `xoxp-…`).",
    ),
    "credential.gcp_service_account": LabelDisplay(
        id="credential.gcp_service_account",
        name="GCP service-account JSON",
        short="GCP_SA",
        category="credential",
        severity="critical",
        description="Google Cloud service-account credentials JSON.",
    ),
    "credential.azure_storage_key": LabelDisplay(
        id="credential.azure_storage_key",
        name="Azure Storage connection string",
        short="AZURE_STORAGE",
        category="credential",
        severity="critical",
        description="Azure Storage account key embedded in a connection string.",
    ),
    "credential.private_key": LabelDisplay(
        id="credential.private_key",
        name="Private key (PEM)",
        short="PRIVATE_KEY",
        category="credential",
        severity="critical",
        description="PEM-encoded private key block (RSA / EC / DSA / OpenSSH / PGP).",
    ),
    "credential.stripe_api_key": LabelDisplay(
        id="credential.stripe_api_key",
        name="Stripe API key",
        short="STRIPE_KEY",
        category="credential",
        severity="critical",
        description="Stripe secret or restricted key (`sk_live_…` / `rk_test_…`).",
    ),
    "credential.jwt": LabelDisplay(
        id="credential.jwt",
        name="JSON Web Token",
        short="JWT",
        category="credential",
        severity="high",
        description="Three-segment JWT (`eyJ…`). Often a bearer credential.",
    ),
    "credential.generic_high_entropy": LabelDisplay(
        id="credential.generic_high_entropy",
        name="Generic high-entropy token",
        short="TOKEN",
        category="credential",
        severity="medium",
        description=(
            "Length ≥ 32, Shannon entropy ≥ 3.5, no overlap with a known-shape detector. "
            "Likely an opaque API token; could be a false positive."
        ),
    ),
    # ---- Network -----------------------------------------------------
    "network.ip_address": LabelDisplay(
        id="network.ip_address",
        name="IP address",
        short="IP_ADDRESS",
        category="network",
        severity="low",
        description="IP address (Presidio-detected — emitted when the variant is unknown).",
        example="203.0.113.42",
    ),
    "network.ipv4": LabelDisplay(
        id="network.ipv4",
        name="IPv4 address",
        short="IPV4",
        category="network",
        severity="low",
        description="Dotted-quad IPv4 address.",
        example="203.0.113.42",
    ),
    "network.ipv6": LabelDisplay(
        id="network.ipv6",
        name="IPv6 address",
        short="IPV6",
        category="network",
        severity="low",
        description="Colon-separated IPv6 address.",
        example="2001:db8::1",
    ),
    "network.mac_address": LabelDisplay(
        id="network.mac_address",
        name="MAC address",
        short="MAC_ADDRESS",
        category="network",
        severity="low",
        description="48-bit hardware MAC address.",
        example="aa:bb:cc:dd:ee:ff",
    ),
    # ---- Code --------------------------------------------------------
    "code.block": LabelDisplay(
        id="code.block",
        name="Fenced code block",
        short="CODE_BLOCK",
        category="code",
        severity="low",
        description="Triple-backtick code fence. Language hint preserved in the finding's meta.",
    ),
    "code.dense": LabelDisplay(
        id="code.dense",
        name="Code-like dense region",
        short="CODE_DENSE",
        category="code",
        severity="low",
        description="High punctuation density that wasn't explicitly fenced.",
    ),
    "code.proprietary_marker": LabelDisplay(
        id="code.proprietary_marker",
        name="Proprietary or confidential marker",
        short="PROPRIETARY",
        category="code",
        severity="high",
        description=(
            'Document marker such as "INTERNAL USE ONLY" or '
            '"Proprietary and Confidential" — strong signal the content is sensitive.'
        ),
    ),
    # ---- Infra -------------------------------------------------------
    "infra.uuid": LabelDisplay(
        id="infra.uuid",
        name="UUID",
        short="UUID",
        category="infra",
        severity="low",
        description="RFC-4122 UUID. Frequently a request, resource, or tenant identifier.",
        example="550e8400-e29b-41d4-a716-446655440000",
    ),
    # ---- Behavior (prompt injection + LLM-classifier signals) -------
    "behavior.injection_ignore_previous": LabelDisplay(
        id="behavior.injection_ignore_previous",
        name='Injection — "ignore previous instructions"',
        short="INJECTION_IGNORE",
        category="behavior",
        severity="high",
        description='Classic instruction-override pattern ("ignore previous / above / prior … instructions").',
    ),
    "behavior.injection_role_swap": LabelDisplay(
        id="behavior.injection_role_swap",
        name='Injection — "you are now …"',
        short="INJECTION_ROLE_SWAP",
        category="behavior",
        severity="medium",
        description='Role-impersonation opener ("you are now …"). Often pairs with a jailbreak.',
    ),
    "behavior.injection_jailbreak": LabelDisplay(
        id="behavior.injection_jailbreak",
        name="Injection — known jailbreak invocation",
        short="INJECTION_JAILBREAK",
        category="behavior",
        severity="high",
        description='"Act as DAN / unrestricted / developer mode / admin" — known jailbreak handles.',
    ),
    "behavior.injection_system_override": LabelDisplay(
        id="behavior.injection_system_override",
        name="Injection — system override",
        short="INJECTION_SYSTEM",
        category="behavior",
        severity="high",
        description='Phrases combining a privileged role ("system / admin / root") with override verbs.',
    ),
    "behavior.injection_prompt_exfil": LabelDisplay(
        id="behavior.injection_prompt_exfil",
        name="Injection — prompt exfiltration attempt",
        short="INJECTION_EXFIL",
        category="behavior",
        severity="high",
        description='Asks the model to reveal its system prompt or hidden instructions.',
    ),
    "behavior.injection_base64_tool_abuse": LabelDisplay(
        id="behavior.injection_base64_tool_abuse",
        name="Injection — base64 tool-abuse hint",
        short="INJECTION_BASE64",
        category="behavior",
        severity="medium",
        description='Mentions base64 alongside execute/run/decode — common obfuscation vector.',
    ),
    "behavior.injection_ml_classifier": LabelDisplay(
        id="behavior.injection_ml_classifier",
        name="Injection — ML classifier hit",
        short="INJECTION_ML",
        category="behavior",
        severity="high",
        description="ML prompt-injection classifier scored the input above threshold.",
    ),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def lookup(label: str) -> LabelDisplay:
    """Return display info for `label`, falling back to a synthesised entry.

    The synthesised fallback keeps the system forward-compatible: a new
    detector can emit an unknown label and the UI still renders something
    sensible. Operators see a `???` category and the raw label as the
    name, which is a clear signal to add the label to this file.
    """
    hit = LABELS.get(label)
    if hit is not None:
        return hit
    # Synthesise. Category is "infra" (most neutral); severity is "medium"
    # so it surfaces in dashboards but doesn't false-alarm.
    short = label.replace(".", "_").upper()
    return LabelDisplay(
        id=label,
        name=label,
        short=short,
        category="infra",
        severity="medium",
        description="(no display metadata registered for this label)",
        example=None,
    )


def short_for(label: str) -> str:
    """Placeholder fragment used by the tokenizer.

    Centralised here so `<ORG_xxxx>` vs `<ORGANIZATION_xxxx>` is a
    one-line change.
    """
    return lookup(label).short


def categories() -> list[str]:
    """Stable ordered list of category buckets the UI groups by."""
    return ["pii", "financial", "healthcare", "credential", "network", "code", "infra", "behavior"]


def by_category() -> dict[str, list[LabelDisplay]]:
    """All labels grouped by category, useful for the UI filter sidebar."""
    out: dict[str, list[LabelDisplay]] = {c: [] for c in categories()}
    for d in LABELS.values():
        out[d.category].append(d)
    return out
