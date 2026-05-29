import { useCallback, useEffect, useState } from 'react';
import type { Translate } from '../../lib/i18n.js';
import type { RuntimeMessage } from '../../lib/types.js';

interface SecretsBrief {
  hasApiKey: boolean;
  hasOidc: boolean;
  oidcExpiresAt: number | null;
}

interface DeviceCode {
  userCode: string;
  verificationUri: string;
  verificationUriComplete?: string;
}

export function AuthPanel(props: {
  t: Translate;
  secrets: SecretsBrief;
  oidcIssuer: string;
  oidcClientId: string;
  onChange: () => void | Promise<void>;
}): JSX.Element {
  const { t, secrets, oidcIssuer, onChange } = props;
  const [keyDraft, setKeyDraft] = useState('');
  const [deviceCode, setDeviceCode] = useState<DeviceCode | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const saveKey = useCallback(async () => {
    if (!keyDraft.trim()) return;
    await sendMessage<unknown>({
      type: 'secrets.set',
      partial: { apiKey: keyDraft.trim() },
    });
    setKeyDraft('');
    setAuthError(null);
    await onChange();
  }, [keyDraft, onChange]);

  const clearKey = useCallback(async () => {
    await sendMessage<unknown>({
      type: 'secrets.set',
      partial: { apiKey: null, oidc: null },
    });
    setAuthError(null);
    await onChange();
  }, [onChange]);

  const startOidc = useCallback(async () => {
    if (!oidcIssuer) {
      setAuthError(t('popup.auth.oidc.issuerMissing'));
      return;
    }
    setAuthBusy(true);
    setAuthError(null);
    const resp = await sendMessage<
      | { ok: true; userCode: string; verificationUri: string; verificationUriComplete?: string }
      | { ok: false; reason: string }
    >({ type: 'oidc.start' });
    if (resp.ok) {
      setDeviceCode({
        userCode: resp.userCode,
        verificationUri: resp.verificationUri,
        verificationUriComplete: resp.verificationUriComplete,
      });
    } else {
      setAuthBusy(false);
      setAuthError(t('popup.auth.oidc.error', { reason: resp.reason }));
    }
  }, [oidcIssuer, t]);

  const cancelOidc = useCallback(async () => {
    await sendMessage<unknown>({ type: 'oidc.cancel' });
    setDeviceCode(null);
    setAuthBusy(false);
  }, []);

  // Listen for OIDC completion notifications from the service worker.
  useEffect(() => {
    if (typeof chrome === 'undefined' || !chrome.runtime?.onMessage) return undefined;
    const handler = (msg: unknown) => {
      if (
        typeof msg === 'object' &&
        msg !== null &&
        (msg as { type?: string }).type === 'oidc.completed'
      ) {
        const m = msg as { ok: boolean; reason?: string };
        setAuthBusy(false);
        setDeviceCode(null);
        if (m.ok) {
          setAuthError(null);
          void onChange();
        } else {
          setAuthError(t('popup.auth.oidc.error', { reason: m.reason ?? 'unknown' }));
        }
      }
    };
    chrome.runtime.onMessage.addListener(handler);
    return () => chrome.runtime.onMessage.removeListener(handler);
  }, [onChange, t]);

  const isSignedIn = secrets.hasApiKey || secrets.hasOidc;

  return (
    <section className="section" aria-labelledby="auth-h">
      <h2 id="auth-h">
        {t('popup.auth.title')}
        {isSignedIn && (
          <span className="badge" aria-label={t('popup.auth.authenticated')}>
            {t('popup.auth.authenticated')}
          </span>
        )}
      </h2>
      {authError && (
        <div className="banner error" role="alert">
          {authError}
        </div>
      )}
      {!isSignedIn && !deviceCode && (
        <>
          <label className="field">
            <span className="label">{t('popup.auth.apiKey.label')}</span>
            <input
              type="password"
              value={keyDraft}
              onChange={(e) => setKeyDraft(e.target.value)}
              placeholder={t('popup.auth.apiKey.placeholder')}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <div className="row">
            <button onClick={saveKey} className="primary" disabled={!keyDraft.trim()}>
              {t('popup.auth.apiKey.save')}
            </button>
            <button onClick={startOidc} className="ghost" disabled={authBusy}>
              {t('popup.auth.oidc.button')}
            </button>
          </div>
        </>
      )}
      {deviceCode && (
        <div>
          <p className="subtitle">{t('popup.auth.oidc.code')}</p>
          <div className="device-code" aria-live="polite">
            {deviceCode.userCode}
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <a
              href={deviceCode.verificationUriComplete ?? deviceCode.verificationUri}
              target="_blank"
              rel="noreferrer noopener"
              className="primary"
              role="button"
              style={{ textAlign: 'center', textDecoration: 'none', display: 'block', padding: '6px 10px', color: '#fff' }}
            >
              {t('popup.auth.oidc.openTab')}
            </a>
            <button onClick={cancelOidc} className="ghost">
              {t('popup.auth.oidc.cancel')}
            </button>
          </div>
        </div>
      )}
      {isSignedIn && !deviceCode && (
        <div className="row">
          <button onClick={clearKey} className="ghost">
            {t('popup.auth.apiKey.clear')}
          </button>
        </div>
      )}
    </section>
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
