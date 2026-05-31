/**
 * copilot.microsoft.com content script.
 *
 * Copilot uses a `<cib-serp>` custom element on the older markup and a
 * standard `<textarea id="searchbox">` on the newer chat layout. Send is
 * an icon button with `aria-label="Submit"`.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge, scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest copilot.microsoft.com markup.
const INPUT_SELECTORS = [
  '#searchbox',
  'textarea[aria-label="Submit your prompt here"]',
  'textarea[aria-label="Ask me anything..."]',
  'div[contenteditable="true"][role="textbox"]',
];

const SEND_BUTTON_SELECTORS = [
  'button[aria-label="Submit"]',
  'button[aria-label="Send"]',
  'button[data-testid="submit-button"]',
];

const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'copilot',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
});

injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    const scan = await scanInBackground('copilot', msg.url, msg.body);
    if (scan.skipped) {
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'allow', sanitisedBody: msg.body });
      return;
    }
    if (scan.action === 'block') {
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'block', sanitisedBody: null, reason: scan.reason, severity: scan.severity });
      return;
    }
    if (scan.action === 'mask') {
      restore.ctx.setRequestId(scan.request_id);
      bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'mask', sanitisedBody: scan.sanitised ?? msg.body });
      return;
    }
    bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'fetch.decision', id: msg.id, action: 'allow', sanitisedBody: msg.body });
  } else if (msg.kind === 'restore.request') {
    const resp = await restoreInBackground(msg.request_id, msg.text);
    bridge.send({ tag: PAGE_BRIDGE_TAG, kind: 'restore.response', id: msg.id, text: resp.text, restored: resp.restored, missing: resp.missing });
  }
});

window.addEventListener('beforeunload', () => {
  cleanupSubmit();
  bridge.detach();
  restore.detachAll();
});
