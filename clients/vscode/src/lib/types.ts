/**
 * Shared types for the Section VS Code extension.
 *
 * Mirrors the gateway API contract defined in
 * `services/gateway/section_gateway/api/v1/scan.py`.
 */

export type ScanAction = "allow" | "mask" | "block";

export type TransformMethod = "tokenise" | "fpe" | "redact";

/** Edge client identifiers accepted by /v1/scan. */
export type EdgeClient =
  | "browser-extension"
  | "vscode"
  | "jetbrains"
  | "edge-proxy"
  | "cli"
  | "other";

export interface ScanTransform {
  label: string;
  placeholder: string;
  method: TransformMethod;
  scope: string;
}

export interface ScanFinding {
  label: string;
  detector: string;
  confidence: number;
  start: number;
  end: number;
}

export interface ScanDecision {
  action: string;
  mode: string;
  effective_action: string;
  is_shadow: boolean;
  policy_id: string | null;
  policy_version: string | null;
  rule_index: number | null;
  reason: string | null;
  severity: string | null;
}

export interface ScanRequest {
  text: string;
  client: EdgeClient;
  url?: string | null;
  model?: string | null;
  session_id?: string | null;
}

export interface ScanResponse {
  request_id: string;
  action: ScanAction;
  sanitised: string | null;
  transforms: ScanTransform[];
  findings: ScanFinding[];
  decision: ScanDecision;
  bundle_digest: string;
  reason?: string | null;
  severity?: string | null;
}

export interface RestoreRequest {
  request_id: string;
  text: string;
}

export interface RestoreResponse {
  request_id: string;
  text: string;
  restored: number;
  missing: string[];
}

/**
 * Local record of one decision the user has seen — surfaced in the
 * activity-bar tree view. Kept in-memory only; never persisted.
 */
export interface DecisionRecord {
  request_id: string;
  action: ScanAction;
  reason: string | null;
  severity: string | null;
  uri: string | null;
  occurredAt: string;
  findingCount: number;
  transformCount: number;
  excerpt: string;
}

/** Internal proxy state. */
export type ProxyState = "stopped" | "starting" | "running" | "error";
