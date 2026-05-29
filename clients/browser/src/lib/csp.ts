/**
 * Runtime CSP / origin checks for the gateway URL.
 *
 * The MV3 manifest declares `connect-src` for a known small set of
 * defaults (`localhost:8000`, `localhost:8080`, `*.praesidio.local`).
 * Operators who point the extension at a different gateway need to
 * either (a) self-build the extension with their host added, or
 * (b) confirm the URL falls into one of the declared origins.
 *
 * This module surfaces a clear error from the popup BEFORE we attempt
 * a fetch — otherwise the user sees an inscrutable network panel error.
 */

/** Hosts pre-allowed by `manifest.json#content_security_policy`. */
export const DEFAULT_ALLOWED_HOSTS: ReadonlyArray<string> = [
  'localhost:8000',
  'localhost:8080',
];

/** Glob-allowed wildcard hosts in the default manifest. */
export const DEFAULT_ALLOWED_WILDCARDS: ReadonlyArray<string> = [
  '*.praesidio.local',
];

export interface GatewayUrlCheck {
  ok: boolean;
  reason?: string;
}

/**
 * Validate a gateway URL string.
 *
 * Returns `{ok:true}` if the URL parses, uses http/https, and matches one
 * of the manifest-declared origins. Otherwise returns `{ok:false}` with a
 * human-readable reason the popup can surface.
 *
 * The check is conservative: if `URL` parsing fails or the protocol is
 * exotic, we reject. We intentionally allow plain `http://localhost` for
 * dev — `connect-src` permits it.
 */
export function checkGatewayUrl(raw: string): GatewayUrlCheck {
  if (!raw || typeof raw !== 'string') {
    return { ok: false, reason: 'Gateway URL is empty.' };
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, reason: 'Gateway URL is not a valid URL.' };
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    return {
      ok: false,
      reason: `Unsupported protocol: ${url.protocol}. Use https or http.`,
    };
  }
  // `host` includes the port; we compare case-insensitively.
  const host = url.host.toLowerCase();
  if (DEFAULT_ALLOWED_HOSTS.includes(host)) return { ok: true };
  for (const wild of DEFAULT_ALLOWED_WILDCARDS) {
    if (matchWildcard(host, wild)) return { ok: true };
  }
  return {
    ok: false,
    reason:
      `Gateway host "${host}" is not in the extension's connect-src ` +
      `allow-list. Self-build the extension with this host added to ` +
      `manifest.json#content_security_policy or use one of: ` +
      `${[...DEFAULT_ALLOWED_HOSTS, ...DEFAULT_ALLOWED_WILDCARDS].join(', ')}.`,
  };
}

/**
 * Minimal wildcard matcher for `*.example.com` style entries. Only a
 * single leading `*.` is supported, matching one or more sub-labels.
 */
function matchWildcard(host: string, pattern: string): boolean {
  if (!pattern.startsWith('*.')) return host === pattern;
  const suffix = pattern.slice(2).toLowerCase();
  const lower = host.toLowerCase();
  if (lower === suffix) return false; // bare apex isn't matched
  return lower.endsWith('.' + suffix);
}

/**
 * Resolve the gateway URL into its canonical form (no trailing slash).
 * Used everywhere we concatenate `${gateway}${path}` so we don't get
 * `https://host//v1/scan`.
 */
export function canonicaliseGatewayUrl(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.endsWith('/')) return trimmed.slice(0, -1);
  return trimmed;
}
