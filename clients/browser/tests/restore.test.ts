import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createRestoreManager } from '../src/content/lib/restore.js';

// Stub the messaging module so we can return synthetic restore responses.
vi.mock('../src/content/lib/messaging.js', () => {
  return {
    restoreInBackground: vi.fn(async (_id: string, text: string) => {
      // Hard-coded restore table.
      const out = text
        .replace(/<EMAIL_A2B3>/g, 'bob@example.com')
        .replace(/<ACCOUNT_NUMBER_K7M2>/g, '12345');
      return {
        request_id: 'r1',
        text: out,
        restored: (text.match(/<[A-Z][A-Z0-9_]*_[A-Z2-7]{4}>/g) ?? []).length,
        missing: [],
      };
    }),
  };
});

describe('createRestoreManager', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('rewrites placeholders after observe + sweep', async () => {
    document.body.innerHTML = '<div id="conv"><p>Hi <em>&lt;EMAIL_A2B3&gt;</em></p></div>';
    // Re-set the text without HTML encoding:
    const conv = document.getElementById('conv') as HTMLElement;
    conv.innerHTML = '';
    const p = document.createElement('p');
    p.textContent = 'Hello <EMAIL_A2B3>, your account <ACCOUNT_NUMBER_K7M2> is set up.';
    conv.appendChild(p);

    const mgr = createRestoreManager();
    mgr.ctx.setRequestId('r1');
    const stop = mgr.observe(conv);

    // Advance debounce + flush microtasks.
    await vi.advanceTimersByTimeAsync(300);
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(50);

    expect(conv.textContent).toContain('bob@example.com');
    expect(conv.textContent).toContain('12345');
    stop();
  });

  it('does nothing when requestId is unset', async () => {
    const conv = document.createElement('div');
    const p = document.createElement('p');
    p.textContent = 'has <EMAIL_A2B3> token';
    conv.appendChild(p);
    document.body.appendChild(conv);

    const mgr = createRestoreManager();
    mgr.observe(conv);
    await vi.advanceTimersByTimeAsync(500);
    expect(conv.textContent).toContain('<EMAIL_A2B3>');
  });
});
