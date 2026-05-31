/**
 * Shared types for the Section browser extension.
 *
 * Mirror of the gateway's pydantic shapes in
 * `services/gateway/section_gateway/api/v1/scan.py`.
 * Keep the wire format in lockstep — there is no codegen.
 */

export type ScanAction = 'allow' | 'mask' | 'block';

export type ScanMethod = 'tokenise' | 'fpe' | 'redact';

export interface ScanTransform {
  label: string;
  placeholder: string;
  method: ScanMethod;
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
  client: 'browser-extension';
  url?: string;
  model?: string;
  session_id?: string;
}

export interface ScanResponse {
  request_id: string;
  action: ScanAction;
  sanitised: string | null;
  transforms: ScanTransform[];
  findings: ScanFinding[];
  decision: ScanDecision;
  bundle_digest: string;
  reason: string | null;
  severity: string | null;
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
 * Site identifier — used for per-site toggle + content-script tagging.
 * Keep in sync with `manifest.json#content_scripts` matches list.
 */
export type SiteId =
  | 'chatgpt'
  | 'claude'
  | 'gemini'
  | 'copilot'
  | 'perplexity'
  | 'mistral';

export interface SiteConfig {
  id: SiteId;
  label: string;
  origins: string[];
  /** Provider hint passed to /v1/scan as `model_hint` for audit panels. */
  modelHint: string;
}

export const SITES: SiteConfig[] = [
  {
    id: 'chatgpt',
    label: 'ChatGPT',
    origins: ['https://chatgpt.com', 'https://chat.openai.com'],
    modelHint: 'openai',
  },
  {
    id: 'claude',
    label: 'Claude',
    origins: ['https://claude.ai'],
    modelHint: 'anthropic',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    origins: ['https://gemini.google.com'],
    modelHint: 'google',
  },
  {
    id: 'copilot',
    label: 'Copilot',
    origins: ['https://copilot.microsoft.com'],
    modelHint: 'microsoft',
  },
  {
    id: 'perplexity',
    label: 'Perplexity',
    origins: ['https://www.perplexity.ai', 'https://perplexity.ai'],
    modelHint: 'perplexity',
  },
  {
    id: 'mistral',
    label: 'Mistral',
    origins: ['https://chat.mistral.ai'],
    modelHint: 'mistral',
  },
];

/** Stored settings (`chrome.storage.sync`). NEVER put secrets here. */
export interface Settings {
  gatewayUrl: string;
  /** Per-site enable flag, keyed by SiteId. Default: all true. */
  sites: Record<SiteId, boolean>;
  /** Operator's IdP issuer URL for OIDC device-code flow. */
  oidcIssuer: string;
  /** Operator's IdP client_id for device-code flow. */
  oidcClientId: string;
  /** Localisation override; falls back to chrome.i18n.getUILanguage(). */
  locale: 'en' | 'es' | null;
}

export const DEFAULT_SETTINGS: Settings = {
  gatewayUrl: 'https://localhost:8000',
  sites: {
    chatgpt: true,
    claude: true,
    gemini: true,
    copilot: true,
    perplexity: true,
    mistral: true,
  },
  oidcIssuer: '',
  oidcClientId: 'section-edge',
  locale: null,
};

/**
 * Secrets — `chrome.storage.local` only. Never `.sync` (would leak across
 * the user's logged-in Google Account synced devices).
 */
export interface Secrets {
  apiKey: string | null;
  oidc: {
    accessToken: string | null;
    refreshToken: string | null;
    /** Epoch ms when access token expires. */
    expiresAt: number | null;
  } | null;
}

export const EMPTY_SECRETS: Secrets = {
  apiKey: null,
  oidc: null,
};

/** Per-tab decision record stored in `chrome.storage.local`. */
export interface DecisionRecord {
  ts: number;
  site: SiteId;
  action: ScanAction;
  url: string;
  request_id: string;
  reason?: string | null;
  severity?: string | null;
  /** Number of placeholders applied (mask action only). */
  masked?: number;
}

/**
 * postMessage envelope used between the page-world inject script and the
 * isolated-world content script. The `tag` is a magic string both sides
 * check before parsing.
 */
export const PAGE_BRIDGE_TAG = '__section__' as const;

export type PageBridgeMessage =
  | { tag: typeof PAGE_BRIDGE_TAG; kind: 'fetch.intercept'; id: string; url: string; method: string; body: string }
  | { tag: typeof PAGE_BRIDGE_TAG; kind: 'fetch.decision'; id: string; action: ScanAction; sanitisedBody: string | null; reason?: string | null; severity?: string | null }
  | { tag: typeof PAGE_BRIDGE_TAG; kind: 'restore.request'; id: string; request_id: string; text: string }
  | { tag: typeof PAGE_BRIDGE_TAG; kind: 'restore.response'; id: string; text: string; restored: number; missing: string[] };

/**
 * Messages flowing between content scripts / popup and the background
 * service worker via `chrome.runtime.sendMessage`. Keep the discriminator
 * (`type`) so background can route with a switch.
 */
export type SettingsPatch =
  Partial<Omit<Settings, 'sites'>> & { sites?: Partial<Settings['sites']> };

export type RuntimeMessage =
  | { type: 'scan'; site: SiteId; url: string; text: string; sessionId?: string }
  | { type: 'restore'; request_id: string; text: string }
  | { type: 'ping' }
  | { type: 'oidc.start' }
  | { type: 'oidc.cancel' }
  | { type: 'settings.get' }
  | { type: 'settings.set'; partial: SettingsPatch }
  | { type: 'secrets.set'; partial: Partial<Secrets> }
  | { type: 'secrets.get' }
  | { type: 'decisions.get' }
  | { type: 'decisions.clear' };

export interface PingResponse {
  ok: boolean;
  gatewayUrl: string;
  authenticated: boolean;
  latencyMs?: number;
  error?: string;
}
