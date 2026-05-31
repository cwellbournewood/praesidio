/**
 * www.perplexity.ai content script.
 *
 * The composer is a standard `<textarea placeholder="Ask anything…">`.
 * Send is a button with `aria-label="Submit"`. New "Pro Search" turns
 * the send button into one with `data-testid="ask-button"`.
 */
import { installSubmitHook } from './lib/intercept.js';
import { createRestoreManager } from './lib/restore.js';
import { injectPageScript, installPageBridge, scanInBackground, restoreInBackground } from './lib/messaging.js';
import { PAGE_BRIDGE_TAG } from '../lib/types.js';

// TODO 1.1.1: verify selectors against latest perplexity.ai markup.
const INPUT_SELECTORS = [
  'textarea[placeholder*="Ask"]',
  'textarea[placeholder*="Pregunta"]',
  'div[contenteditable="true"][role="textbox"]',
];

const SEND_BUTTON_SELECTORS = [
  'button[aria-label="Submit"]',
  'button[data-testid="ask-button"]',
  'button[aria-label="Send"]',
];

const restore = createRestoreManager();
restore.observe(document.body);

const cleanupSubmit = installSubmitHook({
  site: 'perplexity',
  inputSelectors: INPUT_SELECTORS,
  sendButtonSelectors: SEND_BUTTON_SELECTORS,
});

injectPageScript();
const bridge = installPageBridge(async (msg) => {
  if (msg.kind === 'fetch.intercept') {
    const scan = await scanInBackground('perplexity', msg.url, msg.body);
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
