/**
 * chatgpt.com content script.
 *
 * The textarea is a `<textarea id="prompt-textarea">` (or a
 * contenteditable `<div>` on the newer composer). The send button is
 * `button[data-testid="send-button"]` on the standard layout and
 * `button[aria-label="Send prompt"]` on the redesigned one. We try both.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge } from './lib/messaging.js';
import { scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest chatgpt.com markup.
const INPUT_SELECTORS = [
  '#prompt-textarea',
  'textarea[data-id="prompt-textarea"]',
  'div[contenteditable="true"][data-id="root"]',
  'div[contenteditable="true"][data-virtualkeyboard]',
];

const SEND_BUTTON_SELECTORS = [
  'button[data-testid="send-button"]',
  'button[aria-label="Send prompt"]',
  'button[aria-label="Send message"]',
];

// Track the latest scan request_id so the restore manager can attribute
// placeholders found in the next response.
const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'chatgpt',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
});

// Bridge for page-world fetch hook.
injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    // Run via the background worker (so secrets stay there).
    const scan = await scanInBackground(
      'chatgpt',
      msg.url,
      msg.body,
      // session_id intentionally omitted; the page-world body is the
      // canonical anchor, not a content-script-derived id.
    );
    if (scan.skipped) {
      bridge.send({
        tag: PAGE_BRIDGE_TAG,
        kind: 'fetch.decision',
        id: msg.id,
        action: 'allow',
        sanitisedBody: msg.body,
      });
      return;
    }
    if (scan.action === 'block') {
      bridge.send({
        tag: PAGE_BRIDGE_TAG,
        kind: 'fetch.decision',
        id: msg.id,
        action: 'block',
        sanitisedBody: null,
        reason: scan.reason,
        severity: scan.severity,
      });
      return;
    }
    if (scan.action === 'mask') {
      restore.ctx.setRequestId(scan.request_id);
      bridge.send({
        tag: PAGE_BRIDGE_TAG,
        kind: 'fetch.decision',
        id: msg.id,
        action: 'mask',
        sanitisedBody: scan.sanitised ?? msg.body,
      });
      return;
    }
    bridge.send({
      tag: PAGE_BRIDGE_TAG,
      kind: 'fetch.decision',
      id: msg.id,
      action: 'allow',
      sanitisedBody: msg.body,
    });
  } else if (msg.kind === 'restore.request') {
    const resp = await restoreInBackground(msg.request_id, msg.text);
    bridge.send({
      tag: PAGE_BRIDGE_TAG,
      kind: 'restore.response',
      id: msg.id,
      text: resp.text,
      restored: resp.restored,
      missing: resp.missing,
    });
  }
});

// Hook into beforeunload to clean up — Chrome usually GCs anyway.
window.addEventListener('beforeunload', () => {
  cleanupSubmit();
  bridge.detach();
  restore.detachAll();
});
