// Types mirror the gateway's pydantic models. Kept intentionally permissive
// (optional metadata fields) so the UI degrades gracefully against older
// gateway versions.

export type Decision = 'allow' | 'transform' | 'block' | 'error' | 'simulate';

// The canonical wire-label union. Kept in lockstep with the Python
// source of truth at `services/gateway/praesidio_gateway/dlp/display.py`
// and the TS twin at `services/ui/lib/labels.ts` (which carries the
// full display metadata). `(string & {})` keeps the union open so new
// labels round-trip through the UI without a type rebuild.
export type DetectorLabel =
  // PII
  | 'pii.person'
  | 'pii.organization'
  | 'pii.location'
  | 'pii.email'
  | 'pii.phone'
  | 'pii.date'
  | 'pii.nationality'
  | 'pii.us_ssn'
  | 'pii.us_drivers_license'
  | 'pii.url'
  // Financial
  | 'financial.credit_card'
  | 'financial.iban'
  // Healthcare
  | 'healthcare.medical_license'
  // Credentials
  | 'credential.aws_access_key'
  | 'credential.aws_secret_key'
  | 'credential.github_pat'
  | 'credential.openai_api_key'
  | 'credential.anthropic_api_key'
  | 'credential.slack_bot_token'
  | 'credential.gcp_service_account'
  | 'credential.azure_storage_key'
  | 'credential.private_key'
  | 'credential.stripe_api_key'
  | 'credential.jwt'
  | 'credential.generic_high_entropy'
  // Network
  | 'network.ip_address'
  | 'network.ipv4'
  | 'network.ipv6'
  | 'network.mac_address'
  // Code
  | 'code.block'
  | 'code.dense'
  | 'code.proprietary_marker'
  // Infrastructure
  | 'infra.uuid'
  // Behavioural (prompt-injection / classifier)
  | 'behavior.injection_ignore_previous'
  | 'behavior.injection_role_swap'
  | 'behavior.injection_jailbreak'
  | 'behavior.injection_system_override'
  | 'behavior.injection_prompt_exfil'
  | 'behavior.injection_base64_tool_abuse'
  | 'behavior.injection_ml_classifier'
  | (string & {});

export type LabelCategory =
  | 'pii'
  | 'financial'
  | 'healthcare'
  | 'credential'
  | 'network'
  | 'code'
  | 'infra'
  | 'behavior';

// `LabelFamily` is the legacy name kept around for `utils.ts:labelFamily`
// and the FindingChip palette. Maps onto the new `LabelCategory`.
export type LabelFamily = LabelCategory | 'other';

export interface Finding {
  label: DetectorLabel;
  span: [number, number];
  score: number;
  detector_version: string;
  // The original text is never stored in the audit row — only a token, if any.
  vault_token?: string | null;
  replacement?: string | null;
}

export type TransformMethod = 'tokenise' | 'fpe' | 'redact' | 'mask' | 'hash';

export interface AppliedTransform {
  label: DetectorLabel;
  method: TransformMethod;
  count: number;
  scope?: 'session' | 'tenant' | 'global';
  ttl?: string;
}

export interface Principal {
  user_id: string;
  email?: string;
  tenant_id: string;
  groups: string[];
  device_id?: string;
  ip?: string;
  country?: string;
}

export interface AuditEvent {
  id: string;
  tenant_id: string;
  /** The request_id the audit row is keyed under — used to detokenise vault placeholders. */
  request_id?: string;
  occurred_at: string;
  principal: Principal;
  route: string;
  upstream: string;
  decision: Decision;
  rule_id?: string;
  rule_index?: number;
  policy_id?: string;
  policy_version?: string;
  bundle_digest?: string;
  findings: Finding[];
  transforms: AppliedTransform[];
  request_digest: string;
  response_digest?: string;
  latency_ms: number;
  bytes_in: number;
  bytes_out: number;
  degraded?: boolean;
  reason?: string;
  // Best-effort previews — vault tokens only, never the raw source text.
  sanitised_preview?: string;
  received_preview?: string;
}

export interface PolicyMatch {
  routes: string[];
  tenants: string[];
  principals?: { groups?: string[] };
  models?: string[];
}

export interface PolicyRule {
  when: string;
  action: 'allow' | 'transform' | 'block';
  reason?: string;
  severity?: 'info' | 'low' | 'medium' | 'high' | 'critical';
  transforms?: Array<{
    label: string;
    method: TransformMethod;
    scope?: string;
    ttl?: string;
    replacement?: string;
  }>;
}

export interface Policy {
  id: string;
  name: string;
  owner: string;
  description: string;
  version: string;
  enabled: boolean;
  fail_mode: 'open' | 'closed';
  match: PolicyMatch;
  detectors: string[];
  rules: PolicyRule[];
  raw_yaml: string;
  recent_decisions: { decision: Decision; count: number }[];
  updated_at: string;
}

export type LineageNodeKind =
  | 'prompt'
  | 'retrieval'
  | 'tool'
  | 'output'
  | 'embedding'
  | 'memory_write';

export interface LineageNode {
  id: string;
  kind: LineageNodeKind;
  label: string;
  meta?: Record<string, unknown>;
  audit_event_id?: string;
}

export interface LineageEdge {
  parent_id: string;
  child_id: string;
  relation: 'derived_from' | 'retrieved_from' | 'tool_output_of';
}

export interface LineageGraphData {
  request_id: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface ModelCardEntry {
  id: string;
  provider: string;
  model: string;
  display_name: string;
  jurisdiction: string;
  region: string;
  certifications: string[];
  privacy: {
    training_optout: boolean;
    data_retention_days: number;
    customer_managed_keys: boolean;
  };
  risk_tier: 'low' | 'medium' | 'high';
  route_mappings: string[];
  notes?: string;
}

export interface DashboardKpis {
  requests_today: number;
  transformed_pct: number;
  blocked_pct: number;
  top_detectors: { label: DetectorLabel; count: number }[];
  p99_latency_ms: number;
  spark: number[]; // 24 buckets, last 24h
}

export interface GatewayHealth {
  ok: boolean;
  version: string;
  bundle_digest: string;
  policy_count: number;
  env: string;
  fail_mode: 'open' | 'closed';
  gateway_url: string;
}

/* ─── Tenants ─────────────────────────────────────────────────────── */

export interface Tenant {
  id: string;
  name: string;
  env?: string;
  region?: string;
}

/* ─── Simulator (POST /admin/simulate) ────────────────────────────── */

export interface SimulateRequest {
  prompt: string;
  route?: string;
  upstream?: string;
  policy_id?: string;
  principal?: Partial<Principal>;
}

export interface SimulateTransform {
  label: DetectorLabel;
  method: TransformMethod;
  span: [number, number];
  replacement: string;
}

export interface SimulateResponse {
  decision: Decision;
  rule_id?: string;
  rule_index?: number;
  policy_id?: string;
  policy_version?: string;
  reason?: string;
  findings: Finding[];
  transforms: SimulateTransform[];
  sanitised: string;
  latency_ms?: number;
}
