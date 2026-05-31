import { describe, expect, it } from 'vitest';
import {
  clearDecisions,
  loadDecisions,
  loadSecrets,
  loadSettings,
  makeMemoryArea,
  recordDecision,
  saveSecrets,
  saveSettings,
} from '../src/lib/storage.js';

describe('settings storage', () => {
  it('returns defaults when unset', async () => {
    const area = makeMemoryArea();
    const s = await loadSettings(area);
    expect(s.gatewayUrl).toBe('https://localhost:8000');
    expect(Object.keys(s.sites)).toHaveLength(6);
  });

  it('round-trips a partial save without losing site keys', async () => {
    const area = makeMemoryArea();
    await saveSettings({ gatewayUrl: 'https://localhost:8080' }, area);
    const s = await loadSettings(area);
    expect(s.gatewayUrl).toBe('https://localhost:8080');
    expect(s.sites.chatgpt).toBe(true);
    expect(s.sites.claude).toBe(true);
  });

  it('merges per-site toggle into the existing map', async () => {
    const area = makeMemoryArea();
    await saveSettings({ sites: { claude: false } }, area);
    const s = await loadSettings(area);
    expect(s.sites.claude).toBe(false);
    expect(s.sites.chatgpt).toBe(true);
  });
});

describe('secrets storage', () => {
  it('round-trips api key', async () => {
    const area = makeMemoryArea();
    await saveSecrets({ apiKey: 'k1' }, area);
    expect((await loadSecrets(area)).apiKey).toBe('k1');
  });

  it('clears apiKey when explicitly set null', async () => {
    const area = makeMemoryArea();
    await saveSecrets({ apiKey: 'k1' }, area);
    await saveSecrets({ apiKey: null }, area);
    expect((await loadSecrets(area)).apiKey).toBeNull();
  });
});

describe('decisions log', () => {
  it('keeps newest first and caps at 10', async () => {
    const area = makeMemoryArea();
    for (let i = 0; i < 15; i += 1) {
      await recordDecision({ ts: i, site: 'chatgpt', action: 'allow', url: 'u', request_id: String(i) }, area);
    }
    const list = await loadDecisions(area);
    expect(list).toHaveLength(10);
    expect(list[0].request_id).toBe('14');
    expect(list[9].request_id).toBe('5');
  });

  it('clear empties the log', async () => {
    const area = makeMemoryArea();
    await recordDecision({ ts: 1, site: 'claude', action: 'mask', url: 'u', request_id: '1', masked: 3 }, area);
    await clearDecisions(area);
    expect(await loadDecisions(area)).toHaveLength(0);
  });
});
