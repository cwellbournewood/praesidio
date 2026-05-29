/**
 * Popup root.
 *
 * Composes:
 *   - header status (gateway URL + ping state)
 *   - AuthPanel (API key OR OIDC device-code)
 *   - SiteToggle (per-site enable)
 *   - DecisionList (last 10 decisions)
 *   - footer (audit log link, docs)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { pickLocale, makeT } from '../lib/i18n.js';
import {
  DEFAULT_SETTINGS,
  SITES,
  type DecisionRecord,
  type RuntimeMessage,
  type SiteId,
  type Settings,
} from '../lib/types.js';
import { AuthPanel } from './components/AuthPanel.js';
import { DecisionList } from './components/DecisionList.js';
import { SiteToggle } from './components/SiteToggle.js';

interface SecretsBrief {
  hasApiKey: boolean;
  hasOidc: boolean;
  oidcExpiresAt: number | null;
}

const VERSION = '1.1.0';

export function App(): JSX.Element {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [secrets, setSecrets] = useState<SecretsBrief>({
    hasApiKey: false,
    hasOidc: false,
    oidcExpiresAt: null,
  });
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [pingState, setPingState] = useState<
    'unknown' | 'pinging' | 'ok' | 'offline'
  >('unknown');
  const [pingError, setPingError] = useState<string | null>(null);
  const [gatewayDraft, setGatewayDraft] = useState('');
  const [saveBanner, setSaveBanner] = useState<string | null>(null);

  const locale = useMemo(() => pickLocale(settings.locale), [settings.locale]);
  const t = useMemo(() => makeT(locale), [locale]);

  // ---- bootstrap ---------------------------------------------------------
  useEffect(() => {
    void (async () => {
      const [s, sec, dec] = await Promise.all([
        sendMessage<Settings>({ type: 'settings.get' }),
        sendMessage<SecretsBrief>({ type: 'secrets.get' }),
        sendMessage<DecisionRecord[]>({ type: 'decisions.get' }),
      ]);
      setSettings(s);
      setSecrets(sec);
      setDecisions(dec ?? []);
      setGatewayDraft(s.gatewayUrl);
      void ping();
    })();
  }, []);

  const ping = useCallback(async () => {
    setPingState('pinging');
    setPingError(null);
    const resp = await sendMessage<{ ok: boolean; latencyMs?: number; error?: string }>({ type: 'ping' });
    if (resp?.ok) {
      setPingState('ok');
    } else {
      setPingState('offline');
      setPingError(resp?.error ?? 'offline');
    }
  }, []);

  const saveGateway = useCallback(async () => {
    const next = await sendMessage<Settings>({
      type: 'settings.set',
      partial: { gatewayUrl: gatewayDraft.trim() },
    });
    setSettings(next);
    setSaveBanner(t('popup.gateway.saved'));
    setTimeout(() => setSaveBanner(null), 1500);
    void ping();
  }, [gatewayDraft, ping, t]);

  const toggleSite = useCallback(
    async (id: SiteId, enabled: boolean) => {
      const partial: Partial<Settings> = {
        sites: { ...settings.sites, [id]: enabled },
      };
      const next = await sendMessage<Settings>({ type: 'settings.set', partial });
      setSettings(next);
    },
    [settings.sites],
  );

  const onAuthChange = useCallback(async () => {
    const [sec, dec] = await Promise.all([
      sendMessage<SecretsBrief>({ type: 'secrets.get' }),
      sendMessage<DecisionRecord[]>({ type: 'decisions.get' }),
    ]);
    setSecrets(sec);
    setDecisions(dec ?? []);
    void ping();
  }, [ping]);

  const clearDecisions = useCallback(async () => {
    await sendMessage<{ ok: boolean }>({ type: 'decisions.clear' });
    setDecisions([]);
  }, []);

  // ---- render ------------------------------------------------------------

  const auditLogHref = useMemo(() => {
    try {
      const u = new URL(settings.gatewayUrl);
      u.pathname = '/admin/events';
      return u.toString();
    } catch {
      return '#';
    }
  }, [settings.gatewayUrl]);

  return (
    <>
      <header className="header">
        <div>
          <h1>
            <span className="logo-dot" aria-hidden="true" />
            {t('popup.title')}
          </h1>
          <div className="tagline">{t('popup.tagline')}</div>
        </div>
        <span
          className={`status-pill ${pingState === 'ok' ? 'online' : pingState === 'offline' ? 'offline' : ''}`}
          aria-live="polite"
        >
          <span className="dot" />
          {pingState === 'pinging'
            ? t('popup.gateway.testing')
            : pingState === 'ok'
              ? t('popup.gateway.connected')
              : pingState === 'offline'
                ? t('popup.gateway.offline')
                : '...'}
        </span>
      </header>

      <section className="section" aria-labelledby="gateway-h">
        <h2 id="gateway-h">{t('popup.gateway.label')}</h2>
        {saveBanner && <div className="banner success">{saveBanner}</div>}
        {pingState === 'offline' && pingError && (
          <div className="banner error" role="alert">
            {pingError}
          </div>
        )}
        <label className="field">
          <span className="label">URL</span>
          <input
            type="url"
            value={gatewayDraft}
            onChange={(e) => setGatewayDraft(e.target.value)}
            placeholder={t('popup.gateway.placeholder')}
            spellCheck={false}
          />
        </label>
        <div className="row">
          <button onClick={saveGateway} className="primary">
            {t('popup.gateway.save')}
          </button>
          <button onClick={() => void ping()} className="ghost">
            {pingState === 'pinging'
              ? t('popup.gateway.testing')
              : t('popup.gateway.connected')}
          </button>
        </div>
      </section>

      <AuthPanel
        t={t}
        secrets={secrets}
        oidcIssuer={settings.oidcIssuer}
        oidcClientId={settings.oidcClientId}
        onChange={onAuthChange}
      />

      <section className="section" aria-labelledby="sites-h">
        <h2 id="sites-h">{t('popup.sites.title')}</h2>
        <p className="subtitle">{t('popup.sites.subtitle')}</p>
        {SITES.map((s) => (
          <SiteToggle
            key={s.id}
            site={s}
            enabled={settings.sites[s.id]}
            onChange={(next) => void toggleSite(s.id, next)}
          />
        ))}
      </section>

      <section className="section" aria-labelledby="decisions-h">
        <h2 id="decisions-h">
          {t('popup.decisions.title')}
          {decisions.length > 0 && (
            <button
              className="ghost"
              style={{ float: 'right', padding: '2px 8px', fontSize: 10 }}
              onClick={() => void clearDecisions()}
            >
              {t('popup.decisions.clear')}
            </button>
          )}
        </h2>
        <DecisionList decisions={decisions} t={t} />
      </section>

      <footer className="footer">
        <span>{t('popup.footer.version', { version: VERSION })}</span>
        <span>
          <a href={auditLogHref} target="_blank" rel="noreferrer noopener">
            {t('popup.footer.auditLog')}
          </a>
        </span>
      </footer>
    </>
  );
}

async function sendMessage<T>(msg: RuntimeMessage): Promise<T> {
  if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
    return Promise.reject(new Error('chrome runtime unavailable'));
  }
  return new Promise<T>((resolve, reject) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(err.message));
        return;
      }
      resolve(resp as T);
    });
  });
}
