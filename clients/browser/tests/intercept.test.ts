import { describe, expect, it } from 'vitest';
import { _internal as restoreInternal } from '../src/content/lib/restore.js';
import { checkGatewayUrl, canonicaliseGatewayUrl } from '../src/lib/csp.js';

describe('csp.checkGatewayUrl', () => {
  it('accepts localhost:8000', () => {
    expect(checkGatewayUrl('https://localhost:8000').ok).toBe(true);
  });
  it('accepts wildcard *.section.local', () => {
    expect(checkGatewayUrl('https://gw.section.local').ok).toBe(true);
  });
  it('rejects unrelated hosts', () => {
    expect(checkGatewayUrl('https://evil.example.com').ok).toBe(false);
  });
  it('rejects garbage URLs', () => {
    expect(checkGatewayUrl('not a url').ok).toBe(false);
  });
});

describe('csp.canonicaliseGatewayUrl', () => {
  it('strips trailing slash', () => {
    expect(canonicaliseGatewayUrl('https://localhost:8000/')).toBe('https://localhost:8000');
  });
  it('preserves URLs without trailing slash', () => {
    expect(canonicaliseGatewayUrl('https://localhost:8000')).toBe('https://localhost:8000');
  });
});

describe('restore.collectPlaceholderNodes', () => {
  it('finds placeholders inside a subtree', () => {
    document.body.innerHTML = '<div><p>Hi <span>&lt;EMAIL_A2B3&gt;</span></p></div>';
    // Use the real text, not entity-encoded:
    document.body.innerHTML = '';
    const root = document.createElement('div');
    const p = document.createElement('p');
    p.textContent = 'Hello <EMAIL_A2B3>, your account <ACCOUNT_NUMBER_K7M2> is ready.';
    root.appendChild(p);
    document.body.appendChild(root);
    const matches = restoreInternal.collectPlaceholderNodes(root);
    expect(matches.length).toBe(1);
    expect(matches[0].placeholders).toEqual(['<EMAIL_A2B3>', '<ACCOUNT_NUMBER_K7M2>']);
  });

  it('skips style content', () => {
    document.body.innerHTML = '';
    const root = document.createElement('div');
    const st = document.createElement('style');
    // A style block whose content syntactically contains a placeholder
    // string. The walker should skip it.
    st.appendChild(document.createTextNode('/* <EMAIL_AAAA> */ body { color: black; }'));
    root.appendChild(st);
    const p = document.createElement('p');
    p.textContent = 'see <EMAIL_BBBB> here';
    root.appendChild(p);
    document.body.appendChild(root);
    const matches = restoreInternal.collectPlaceholderNodes(root);
    expect(matches.length).toBe(1);
    expect(matches[0]?.placeholders).toEqual(['<EMAIL_BBBB>']);
  });

  it('skips text without a placeholder', () => {
    document.body.innerHTML = '';
    const root = document.createElement('div');
    root.textContent = 'plain text with no tokens';
    document.body.appendChild(root);
    expect(restoreInternal.collectPlaceholderNodes(root).length).toBe(0);
  });
});

describe('restore.applyToNode', () => {
  it('replaces placeholders from cache', () => {
    const node = document.createTextNode('Hello <EMAIL_A2B3>!');
    const cache = new Map<string, string>([['<EMAIL_A2B3>', 'bob@x.com']]);
    restoreInternal.applyToNode(node, cache);
    expect(node.nodeValue).toBe('Hello bob@x.com!');
  });

  it('leaves placeholders intact when cache misses', () => {
    const node = document.createTextNode('Hello <EMAIL_ZZZZ>!');
    const cache = new Map<string, string>();
    restoreInternal.applyToNode(node, cache);
    expect(node.nodeValue).toBe('Hello <EMAIL_ZZZZ>!');
  });
});

describe('placeholder regex matches gateway grammar', () => {
  it('matches base32 charset (no 0/1)', () => {
    // Per-call: build a fresh non-global regex from the same source so
    // .match() return value semantics aren't affected by /g state.
    const src = restoreInternal.PLACEHOLDER_RE.source;
    const re = new RegExp(src);
    expect(re.test('see <EMAIL_A2B3>')).toBe(true);
    expect(re.test('see <EMAIL_A1B2>')).toBe(false); // '1' not in [A-Z2-7]
    expect(re.test('see <ACCOUNT_NUMBER_K7M2>')).toBe(true);
  });
});
