/**
 * MV3 service worker — single source of truth for:
 *
 *  - settings + secrets storage
 *  - gateway calls (scan, restore, ping)
 *  - OIDC device-code flow + refresh
 *  - 5-minute heartbeat that POSTs `__section_heartbeat__` to /v1/scan
 *    so SIEM dashboards can spot agent gaps
 *  - rolling decision log shown in the popup
 *
 * Content scripts and the popup talk to this worker only via
 * `chrome.runtime.sendMessage`. The worker never touches the page DOM
 * directly. This keeps the trust boundary clean: content scripts can
 * only ask the worker "scan this string" — they can't read tokens or
 * the operator's gateway URL.
 */
import { DeviceFlow, OidcError, OidcUserCancelled } from '../lib/auth.js';
import { GatewayClient } from '../lib/gateway.js';
import {
  clearDecisions,
  loadDecisions,
  loadSecrets,
  loadSettings,
  recordDecision,
  saveSecrets,
  saveSettings,
} from '../lib/storage.js';
import {
  SITES,
  type DecisionRecord,
  type PingResponse,
  type RestoreResponse,
  type RuntimeMessage,
  type ScanResponse,
  type Secrets,
  type Settings,
  type SiteId,
} from '../lib/types.js';

const HEARTBEAT_ALARM = 'section.heartbeat';
const HEARTBEAT_PERIOD_MIN = 5;

interface RuntimeContext {
  settings: Settings;
  secrets: Secrets;
  client: GatewayClient;
}

async function ctx(): Promise<RuntimeContext> {
  const [settings, secrets] = await Promise.all([loadSettings(), loadSecrets()]);
  return {
    settings,
    secrets,
    client: new GatewayClient(settings, secrets),
  };
}

// In-flight device flow controller, so the popup can cancel.
let activeDeviceFlow: AbortController | null = null;

// ---------------------------------------------------------------------------
// Message dispatcher.
// ---------------------------------------------------------------------------

/** Public entry — exported for tests, registered as `chrome.runtime.onMessage`. */
export async function handleMessage(
  msg: RuntimeMessage,
  sender: chrome.runtime.MessageSender,
): Promise<unknown> {
  switch (msg.type) {
    case 'ping':
      return ping();
    case 'scan':
      return scanAndRecord(msg.site, msg.url, msg.text, msg.sessionId);
    case 'restore':
      return doRestore(msg.request_id, msg.text);
    case 'oidc.start':
      return oidcStart();
    case 'oidc.cancel':
      return oidcCancel();
    case 'settings.get':
      return loadSettings();
    case 'settings.set':
      return saveSettings(msg.partial);
    case 'secrets.get':
      return redactSecrets(await loadSecrets());
    case 'secrets.set':
      return redactSecrets(await saveSecrets(msg.partial));
    case 'decisions.get':
      return loadDecisions();
    case 'decisions.clear':
      await clearDecisions();
      return { ok: true };
    default:
      void sender;
      return { error: `unknown message type: ${(msg as { type: string }).type}` };
  }
}

function redactSecrets(s: Secrets): { hasApiKey: boolean; hasOidc: boolean; oidcExpiresAt: number | null } {
  return {
    hasApiKey: !!s.apiKey,
    hasOidc: !!s.oidc?.accessToken,
    oidcExpiresAt: s.oidc?.expiresAt ?? null,
  };
}

// ---------------------------------------------------------------------------
// Gateway operations.
// ---------------------------------------------------------------------------

async function ping(): Promise<PingResponse> {
  const { client } = await ctx();
  return client.ping();
}

async function scanAndRecord(
  site: SiteId,
  url: string,
  text: string,
  sessionId?: string,
): Promise<ScanResponse & { skipped?: true }> {
  const { settings, client } = await ctx();
  if (!settings.sites[site]) {
    // Per-site toggle off → tell the caller to skip.
    return {
      request_id: '',
      action: 'allow',
      sanitised: text,
      transforms: [],
      findings: [],
      decision: {
        action: 'allow',
        mode: 'enforce',
        effective_action: 'allow',
        is_shadow: false,
        policy_id: null,
        policy_version: null,
        rule_index: null,
        reason: null,
        severity: null,
      },
      bundle_digest: '',
      reason: null,
      severity: null,
      skipped: true,
    };
  }
  const siteCfg = SITES.find((s) => s.id === site);
  const modelHint = siteCfg?.modelHint ?? site;
  const resp = await client.scan({
    text,
    client: 'browser-extension',
    url,
    model: modelHint,
    session_id: sessionId,
  });
  const masked =
    resp.action === 'mask' ? resp.transforms.length : undefined;
  const record: DecisionRecord = {
    ts: Date.now(),
    site,
    action: resp.action,
    url,
    request_id: resp.request_id,
    reason: resp.reason ?? null,
    severity: resp.severity ?? null,
    masked,
  };
  await recordDecision(record);
  return resp;
}

async function doRestore(requestId: string, text: string): Promise<RestoreResponse> {
  const { client } = await ctx();
  return client.restore({ request_id: requestId, text });
}

// ---------------------------------------------------------------------------
// OIDC device-code flow.
// ---------------------------------------------------------------------------

async function oidcStart(): Promise<
  | { ok: true; userCode: string; verificationUri: string; verificationUriComplete?: string }
  | { ok: false; reason: string }
> {
  const { settings } = await ctx();
  if (!settings.oidcIssuer) {
    return { ok: false, reason: 'OIDC issuer not configured' };
  }
  if (activeDeviceFlow) activeDeviceFlow.abort();
  activeDeviceFlow = new AbortController();
  const signal = activeDeviceFlow.signal;
  const flow = new DeviceFlow(settings.oidcIssuer, settings.oidcClientId);
  try {
    const discovery = await flow.discover();
    const auth = await flow.startDeviceAuth(discovery);
    // Open the verification URL in a new tab — best-effort.
    chrome.tabs.create({
      url: auth.verification_uri_complete ?? auth.verification_uri,
    }).catch(() => undefined);
    // Continue polling in the background; resolve immediately so the
    // popup can show the code. We persist tokens when polling resolves.
    void (async () => {
      try {
        const result = await flow.pollForToken(discovery, auth, signal);
        await saveSecrets({
          oidc: {
            accessToken: result.accessToken,
            refreshToken: result.refreshToken,
            expiresAt: result.expiresAt,
          },
        });
        chrome.runtime.sendMessage({ type: 'oidc.completed', ok: true }).catch(() => undefined);
      } catch (err) {
        const reason =
          err instanceof OidcUserCancelled
            ? 'cancelled'
            : err instanceof OidcError
              ? (err.code ?? err.message)
              : String(err);
        chrome.runtime.sendMessage({ type: 'oidc.completed', ok: false, reason }).catch(() => undefined);
      } finally {
        activeDeviceFlow = null;
      }
    })();
    return {
      ok: true,
      userCode: auth.user_code,
      verificationUri: auth.verification_uri,
      verificationUriComplete: auth.verification_uri_complete,
    };
  } catch (err) {
    activeDeviceFlow = null;
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    };
  }
}

function oidcCancel(): { ok: true } {
  if (activeDeviceFlow) {
    activeDeviceFlow.abort();
    activeDeviceFlow = null;
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Heartbeat.
// ---------------------------------------------------------------------------

/** Public for tests. */
export async function heartbeat(): Promise<void> {
  const { client, secrets } = await ctx();
  if (!secrets.apiKey && !secrets.oidc?.accessToken) {
    // Unauthenticated — skip silently; SIEM gap is by design here.
    return;
  }
  try {
    await client.scan({
      text: '__section_heartbeat__',
      client: 'browser-extension',
      url: 'section://heartbeat',
      model: 'heartbeat',
    });
  } catch {
    // Heartbeats are best-effort; failures are visible as gaps in SIEM.
  }
}

// ---------------------------------------------------------------------------
// Worker bootstrap — only run when running inside chrome.
// ---------------------------------------------------------------------------

function bootstrap(): void {
  if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.onMessage) {
    return;
  }
  chrome.runtime.onMessage.addListener(
    (msg: RuntimeMessage, sender, sendResponse) => {
      handleMessage(msg, sender).then(
        (result) => sendResponse(result),
        (err) =>
          sendResponse({
            error: err instanceof Error ? err.message : String(err),
            name: err instanceof Error ? err.name : 'Error',
          }),
      );
      return true; // keep the message channel open for async response
    },
  );

  // Heartbeat alarm — registered once per install.
  if (chrome.alarms) {
    chrome.alarms.create(HEARTBEAT_ALARM, {
      periodInMinutes: HEARTBEAT_PERIOD_MIN,
    });
    chrome.alarms.onAlarm.addListener((alarm) => {
      if (alarm.name === HEARTBEAT_ALARM) void heartbeat();
    });
  }

  // Welcome page on install — opens the popup info; non-fatal if it fails.
  if (chrome.runtime.onInstalled) {
    chrome.runtime.onInstalled.addListener(({ reason }) => {
      if (reason === 'install') {
        chrome.action?.openPopup?.().catch(() => undefined);
      }
    });
  }
}

bootstrap();
