// Human-readable display metadata for DLP labels.
//
// PYTHON IS THE SOURCE OF TRUTH:
//   services/gateway/praesidio_gateway/dlp/display.py
// This file is the TypeScript twin. `scripts/check_label_display_sync.py`
// runs in CI to ensure the two never drift. Update Python first, then
// mirror here.
//
// `lookup(label)` is forward-compatible: a label not in this map gets
// a synthesised display that renders sensibly (`other` category, the
// raw label as the name) so a new detector doesn't break the UI before
// the map catches up.

import type { DetectorLabel, LabelCategory } from './types';

export type LabelSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface LabelDisplay {
  id: DetectorLabel;
  name: string;
  short: string;
  category: LabelCategory;
  severity: LabelSeverity;
  description: string;
  example?: string;
}

export const LABELS: Record<string, LabelDisplay> = {
  // ---- PII ---------------------------------------------------------
  'pii.person': {
    id: 'pii.person',
    name: 'Person name',
    short: 'PERSON',
    category: 'pii',
    severity: 'medium',
    description: 'Name of a real person identified by named-entity recognition.',
    example: 'Jane Doe',
  },
  'pii.organization': {
    id: 'pii.organization',
    name: 'Organization name',
    short: 'ORGANIZATION',
    category: 'pii',
    severity: 'low',
    description: 'Named organization — company, government body, NGO, university.',
    example: 'Acme Corp',
  },
  'pii.location': {
    id: 'pii.location',
    name: 'Location',
    short: 'LOCATION',
    category: 'pii',
    severity: 'low',
    description: 'Place name — city, country, region, landmark.',
    example: 'San Francisco',
  },
  'pii.email': {
    id: 'pii.email',
    name: 'Email address',
    short: 'EMAIL',
    category: 'pii',
    severity: 'medium',
    description: 'RFC-5321 email address. Frequently doubles as a user identifier.',
    example: 'alice@acme.com',
  },
  'pii.phone': {
    id: 'pii.phone',
    name: 'Phone number',
    short: 'PHONE',
    category: 'pii',
    severity: 'medium',
    description: 'Telephone number in any of the common international or local formats.',
    example: '+1 415 555 0123',
  },
  'pii.date': {
    id: 'pii.date',
    name: 'Date or time',
    short: 'DATE',
    category: 'pii',
    severity: 'low',
    description: 'Calendar date or time — useful context, but can identify when combined with other fields.',
    example: '1985-03-21',
  },
  'pii.nationality': {
    id: 'pii.nationality',
    name: 'Nationality, religion, or political group',
    short: 'NATIONALITY',
    category: 'pii',
    severity: 'high',
    description:
      "Presidio's NRP entity — nationality, religious affiliation, or political group. GDPR Article 9 special category.",
    example: 'French',
  },
  'pii.us_ssn': {
    id: 'pii.us_ssn',
    name: 'US Social Security number',
    short: 'US_SSN',
    category: 'pii',
    severity: 'critical',
    description: 'US Social Security number — direct identifier, regulatory minefield.',
    example: '123-45-6789',
  },
  'pii.us_drivers_license': {
    id: 'pii.us_drivers_license',
    name: "US driver's licence",
    short: 'US_DRIVERS_LICENSE',
    category: 'pii',
    severity: 'high',
    description: "US state driver's licence number.",
    example: 'D12345678',
  },
  'pii.url': {
    id: 'pii.url',
    name: 'URL',
    short: 'URL',
    category: 'pii',
    severity: 'low',
    description: 'URL — often a tracking link or contains identifiers in the query string.',
    example: 'https://acme.com/u/jane',
  },
  // ---- Financial ---------------------------------------------------
  'financial.credit_card': {
    id: 'financial.credit_card',
    name: 'Credit card number',
    short: 'CREDIT_CARD',
    category: 'financial',
    severity: 'critical',
    description: 'Payment card number, Luhn-validated. PCI-DSS scope when present.',
    example: '4111 1111 1111 1111',
  },
  'financial.iban': {
    id: 'financial.iban',
    name: 'IBAN bank account',
    short: 'IBAN',
    category: 'financial',
    severity: 'high',
    description: 'International Bank Account Number — uniquely identifies a bank account.',
    example: 'DE89 3704 0044 0532 0130 00',
  },
  // ---- Healthcare --------------------------------------------------
  'healthcare.medical_license': {
    id: 'healthcare.medical_license',
    name: 'Medical licence number',
    short: 'MEDICAL_LICENSE',
    category: 'healthcare',
    severity: 'high',
    description: 'Medical practitioner licence identifier.',
    example: 'MD123456',
  },
  // ---- Credentials -------------------------------------------------
  'credential.aws_access_key': {
    id: 'credential.aws_access_key',
    name: 'AWS access key ID',
    short: 'AWS_ACCESS_KEY',
    category: 'credential',
    severity: 'critical',
    description: 'AWS access key identifier (AKIA / ASIA / AIDA / AROA prefix).',
    example: 'AKIAIOSFODNN7EXAMPLE',
  },
  'credential.aws_secret_key': {
    id: 'credential.aws_secret_key',
    name: 'AWS secret access key',
    short: 'AWS_SECRET_KEY',
    category: 'credential',
    severity: 'critical',
    description: '40-character AWS secret access key, detected alongside its key id.',
  },
  'credential.github_pat': {
    id: 'credential.github_pat',
    name: 'GitHub personal access token',
    short: 'GITHUB_PAT',
    category: 'credential',
    severity: 'critical',
    description: 'GitHub PAT (`ghp_…`) or fine-grained PAT (`github_pat_…`).',
  },
  'credential.openai_api_key': {
    id: 'credential.openai_api_key',
    name: 'OpenAI API key',
    short: 'OPENAI_KEY',
    category: 'credential',
    severity: 'critical',
    description: 'OpenAI secret key (`sk-…`).',
  },
  'credential.anthropic_api_key': {
    id: 'credential.anthropic_api_key',
    name: 'Anthropic API key',
    short: 'ANTHROPIC_KEY',
    category: 'credential',
    severity: 'critical',
    description: 'Anthropic secret key (`sk-ant-…`).',
  },
  'credential.slack_bot_token': {
    id: 'credential.slack_bot_token',
    name: 'Slack bot or user token',
    short: 'SLACK_TOKEN',
    category: 'credential',
    severity: 'high',
    description: 'Slack token (`xoxb-…` / `xoxa-…` / `xoxp-…`).',
  },
  'credential.gcp_service_account': {
    id: 'credential.gcp_service_account',
    name: 'GCP service-account JSON',
    short: 'GCP_SA',
    category: 'credential',
    severity: 'critical',
    description: 'Google Cloud service-account credentials JSON.',
  },
  'credential.azure_storage_key': {
    id: 'credential.azure_storage_key',
    name: 'Azure Storage connection string',
    short: 'AZURE_STORAGE',
    category: 'credential',
    severity: 'critical',
    description: 'Azure Storage account key embedded in a connection string.',
  },
  'credential.private_key': {
    id: 'credential.private_key',
    name: 'Private key (PEM)',
    short: 'PRIVATE_KEY',
    category: 'credential',
    severity: 'critical',
    description: 'PEM-encoded private key block (RSA / EC / DSA / OpenSSH / PGP).',
  },
  'credential.stripe_api_key': {
    id: 'credential.stripe_api_key',
    name: 'Stripe API key',
    short: 'STRIPE_KEY',
    category: 'credential',
    severity: 'critical',
    description: 'Stripe secret or restricted key (`sk_live_…` / `rk_test_…`).',
  },
  'credential.jwt': {
    id: 'credential.jwt',
    name: 'JSON Web Token',
    short: 'JWT',
    category: 'credential',
    severity: 'high',
    description: 'Three-segment JWT (`eyJ…`). Often a bearer credential.',
  },
  'credential.generic_high_entropy': {
    id: 'credential.generic_high_entropy',
    name: 'Generic high-entropy token',
    short: 'TOKEN',
    category: 'credential',
    severity: 'medium',
    description:
      'Length ≥ 32, Shannon entropy ≥ 3.5, no overlap with a known-shape detector. Likely an opaque API token; could be a false positive.',
  },
  // ---- Network -----------------------------------------------------
  'network.ip_address': {
    id: 'network.ip_address',
    name: 'IP address',
    short: 'IP_ADDRESS',
    category: 'network',
    severity: 'low',
    description: 'IP address (Presidio-detected — emitted when the variant is unknown).',
    example: '203.0.113.42',
  },
  'network.ipv4': {
    id: 'network.ipv4',
    name: 'IPv4 address',
    short: 'IPV4',
    category: 'network',
    severity: 'low',
    description: 'Dotted-quad IPv4 address.',
    example: '203.0.113.42',
  },
  'network.ipv6': {
    id: 'network.ipv6',
    name: 'IPv6 address',
    short: 'IPV6',
    category: 'network',
    severity: 'low',
    description: 'Colon-separated IPv6 address.',
    example: '2001:db8::1',
  },
  'network.mac_address': {
    id: 'network.mac_address',
    name: 'MAC address',
    short: 'MAC_ADDRESS',
    category: 'network',
    severity: 'low',
    description: '48-bit hardware MAC address.',
    example: 'aa:bb:cc:dd:ee:ff',
  },
  // ---- Code --------------------------------------------------------
  'code.block': {
    id: 'code.block',
    name: 'Fenced code block',
    short: 'CODE_BLOCK',
    category: 'code',
    severity: 'low',
    description: "Triple-backtick code fence. Language hint preserved in the finding's meta.",
  },
  'code.dense': {
    id: 'code.dense',
    name: 'Code-like dense region',
    short: 'CODE_DENSE',
    category: 'code',
    severity: 'low',
    description: "High punctuation density that wasn't explicitly fenced.",
  },
  'code.proprietary_marker': {
    id: 'code.proprietary_marker',
    name: 'Proprietary or confidential marker',
    short: 'PROPRIETARY',
    category: 'code',
    severity: 'high',
    description:
      'Document marker such as "INTERNAL USE ONLY" or "Proprietary and Confidential" — strong signal the content is sensitive.',
  },
  // ---- Infra -------------------------------------------------------
  'infra.uuid': {
    id: 'infra.uuid',
    name: 'UUID',
    short: 'UUID',
    category: 'infra',
    severity: 'low',
    description: 'RFC-4122 UUID. Frequently a request, resource, or tenant identifier.',
    example: '550e8400-e29b-41d4-a716-446655440000',
  },
  // ---- Behavior ----------------------------------------------------
  'behavior.injection_ignore_previous': {
    id: 'behavior.injection_ignore_previous',
    name: 'Injection — "ignore previous instructions"',
    short: 'INJECTION_IGNORE',
    category: 'behavior',
    severity: 'high',
    description:
      'Classic instruction-override pattern ("ignore previous / above / prior … instructions").',
  },
  'behavior.injection_role_swap': {
    id: 'behavior.injection_role_swap',
    name: 'Injection — "you are now …"',
    short: 'INJECTION_ROLE_SWAP',
    category: 'behavior',
    severity: 'medium',
    description: 'Role-impersonation opener ("you are now …"). Often pairs with a jailbreak.',
  },
  'behavior.injection_jailbreak': {
    id: 'behavior.injection_jailbreak',
    name: 'Injection — known jailbreak invocation',
    short: 'INJECTION_JAILBREAK',
    category: 'behavior',
    severity: 'high',
    description: '"Act as DAN / unrestricted / developer mode / admin" — known jailbreak handles.',
  },
  'behavior.injection_system_override': {
    id: 'behavior.injection_system_override',
    name: 'Injection — system override',
    short: 'INJECTION_SYSTEM',
    category: 'behavior',
    severity: 'high',
    description:
      'Phrases combining a privileged role ("system / admin / root") with override verbs.',
  },
  'behavior.injection_prompt_exfil': {
    id: 'behavior.injection_prompt_exfil',
    name: 'Injection — prompt exfiltration attempt',
    short: 'INJECTION_EXFIL',
    category: 'behavior',
    severity: 'high',
    description: 'Asks the model to reveal its system prompt or hidden instructions.',
  },
  'behavior.injection_base64_tool_abuse': {
    id: 'behavior.injection_base64_tool_abuse',
    name: 'Injection — base64 tool-abuse hint',
    short: 'INJECTION_BASE64',
    category: 'behavior',
    severity: 'medium',
    description: 'Mentions base64 alongside execute/run/decode — common obfuscation vector.',
  },
  'behavior.injection_ml_classifier': {
    id: 'behavior.injection_ml_classifier',
    name: 'Injection — ML classifier hit',
    short: 'INJECTION_ML',
    category: 'behavior',
    severity: 'high',
    description: 'ML prompt-injection classifier scored the input above threshold.',
  },
};

/**
 * Stable ordered list of category buckets the UI filter sidebar groups by.
 * Matches `services/gateway/.../dlp/display.py::categories()`.
 */
export const CATEGORIES: LabelCategory[] = [
  'pii',
  'financial',
  'healthcare',
  'credential',
  'network',
  'code',
  'infra',
  'behavior',
];

/**
 * Return display metadata for a label, synthesising a sensible fallback
 * for labels not yet registered here. The synthesised entry uses the
 * raw label string as `name` so the operator sees that a label is
 * missing rather than getting an opaque "Unknown" placeholder.
 */
export function lookup(label: string): LabelDisplay {
  const hit = LABELS[label];
  if (hit) return hit;
  return {
    id: label as DetectorLabel,
    name: label,
    short: label.replace(/\./g, '_').toUpperCase(),
    category: 'infra',
    severity: 'medium',
    description: '(no display metadata registered for this label)',
  };
}

/**
 * Short, human-readable name for badges. Falls back to the raw label.
 */
export function displayName(label: string): string {
  return lookup(label).name;
}

/**
 * Category for the chip palette / sidebar grouping.
 */
export function categoryOf(label: string): LabelCategory {
  return lookup(label).category;
}

/**
 * Default operator-facing severity hint.
 */
export function severityOf(label: string): LabelSeverity {
  return lookup(label).severity;
}

/**
 * One-sentence description for tooltips and detail panels.
 */
export function descriptionOf(label: string): string {
  return lookup(label).description;
}

/**
 * Group all registered labels by category, in `CATEGORIES` order.
 * Used by the filter sidebar.
 */
export function labelsByCategory(): Record<LabelCategory, LabelDisplay[]> {
  const out = {} as Record<LabelCategory, LabelDisplay[]>;
  for (const c of CATEGORIES) out[c] = [];
  for (const d of Object.values(LABELS)) out[d.category].push(d);
  return out;
}
