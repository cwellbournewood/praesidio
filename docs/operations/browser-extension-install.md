# Browser extension — install + operate

The Praesidio browser extension (Manifest V3) intercepts prompt submission
on the six most-used consumer AI sites and routes prompts through the
gateway's `/v1/scan` before they leave the browser.

For the supported-sites status see
[`docs/edge-coverage-matrix.md`](../edge-coverage-matrix.md); for the
threat model see [`docs/threat-model.md`](../threat-model.md).

## Supported sites

`chatgpt.com`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com`,
`perplexity.ai`, `chat.mistral.ai`.

Other sites are ignored — the extension only requests `host_permissions`
for the listed sites, so it can't intercept anything else.

## Install for end users

### Chrome / Brave / Edge / Arc / Opera

The same MV3 binary works in all Chromium-derived browsers.

1. Download the signed `.crx` from the latest [GitHub
   release](https://github.com/cwellbournewood/praesidio/releases/latest)
   (or use the operator-hosted update server below).
2. Drag the `.crx` into `chrome://extensions` (with **Developer mode**
   enabled), or push it via Chrome Enterprise policy.
3. Click the Praesidio icon in the toolbar.
4. Either paste an API key OR click **Sign in with OIDC** and approve
   in the popup tab.
5. Set the gateway URL (`https://gateway.your-corp.com`) and click
   **Save**.

A green dot in the popup means the gateway responded to a ping. A red
dot means the URL or credentials are wrong.

### Self-host (no Web Store)

For air-gapped deployments or operators who don't want to depend on the
Web Store, ship the `.crx` from GitHub releases and host an update
server.

```
https://updates.your-corp.com/praesidio-browser/update.xml
https://updates.your-corp.com/praesidio-browser/praesidio-edge-<version>.crx
```

Push to your fleet via the standard Chrome
[`ExtensionInstallForcelist`](https://chromeenterprise.google/policies/#ExtensionInstallForcelist)
group policy. We sign the `.crx` with cosign keyless and provide a
SLSA-3 provenance attestation per release.

## Install for developers

```bash
git clone https://github.com/cwellbournewood/praesidio
cd praesidio/clients/browser
npm install
npm run build
```

Then in Chrome:
1. `chrome://extensions`
2. Toggle **Developer mode** (top right).
3. **Load unpacked** → select `clients/browser/dist`.

## Operate

* The toolbar popup shows the last 10 decisions: allow / mask N tokens
  / block.
* Click **Open audit log** to view the full audit trail in the
  gateway UI (`<gateway>/admin/events`).
* The extension emits a heartbeat to the gateway every 5 minutes. A
  gap in heartbeats indicates the extension is disabled or the user
  signed out — SIEM should alert on the gap.

## Operator config

The extension reads its config from `chrome.storage.sync` (gateway URL,
OIDC issuer, per-site toggles) and `chrome.storage.local` (auth
tokens). For managed installs, push the config via Chrome enterprise
policy:

```json
{
  "Praesidio": {
    "gateway_url": {
      "Value": "https://gateway.your-corp.com"
    },
    "oidc_issuer": {
      "Value": "https://idp.your-corp.com/oauth2"
    },
    "sites": {
      "chatgpt.com": { "Value": true },
      "claude.ai": { "Value": true },
      "gemini.google.com": { "Value": true },
      "copilot.microsoft.com": { "Value": true },
      "perplexity.ai": { "Value": true },
      "chat.mistral.ai": { "Value": true }
    }
  }
}
```

Save as `Praesidio.json` and deploy via Chrome / Edge managed-storage
manifest.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Red dot in popup, gateway URL set | Cert / CORS issue | Confirm `<gateway>/healthz` returns 200 in a new tab; check `connect-src` CSP includes the gateway origin |
| Prompts go through unmasked | Site selectors drifted | File an issue with the URL + minimised HTML; we update content-script selectors in a patch release |
| Popup shows "blocked by policy" but I think it shouldn't | Policy match | Click the decision → "View policy" — opens the matched rule in the gateway UI |
| Extension stops working after browser update | MV3 policy change | We track every Chrome MV3 release; check `CHANGELOG.md` for a compat note |

## Uninstall

`chrome://extensions` → **Remove**. Local data is cleared.
