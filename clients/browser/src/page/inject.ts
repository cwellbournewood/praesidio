/**
 * Page-world script: monkey-patches `window.fetch` and
 * `XMLHttpRequest.prototype.send` so any outbound LLM-provider request
 * is intercepted BEFORE it leaves the tab.
 *
 * This runs in the page realm (loaded as a <script src=...> with the
 * extension's web_accessible_resources). Content scripts run in an
 * isolated realm and would patch a different `window.fetch` reference
 * than the one the page actually uses — that's why this lives here.
 *
 * Communication with the content script is via `window.postMessage`
 * tagged `__section__`. The content script is the only listener that
 * cares; everyone else's origin checks should drop these messages.
 *
 * Scope: we only intercept POST requests whose body contains a chat
 * message payload (heuristic: a `messages` array OR a `prompt` field).
 * For everything else (avatar uploads, telemetry pings) we pass through
 * unchanged.
 */
(() => {
  const TAG = '__section__';

  // Provider URL patterns we care about. Conservative: each site's
  // own SPA fetches its OWN backend, not the LLM provider directly, so
  // the substring "backend-api/conversation" or "completion" covers
  // ChatGPT, Claude's `/api/append_message`, Gemini's
  // `BardChatUi.GenerateContent`, Copilot's `/c/api/chat`,
  // perplexity.ai's `/rest/ppl/...`, Mistral's `/api/chat/completions`.
  const SHOULD_INTERCEPT_HOSTS = [
    'chatgpt.com',
    'chat.openai.com',
    'claude.ai',
    'gemini.google.com',
    'copilot.microsoft.com',
    'perplexity.ai',
    'www.perplexity.ai',
    'chat.mistral.ai',
  ];

  const SHOULD_INTERCEPT_PATHS = [
    '/backend-api/conversation',
    '/api/append_message',
    '/api/organizations/',
    '/api/chat',
    '/api/chat/completions',
    '/rest/ppl/',
    '/_/BardChatUi/',
    '/c/api/chat',
  ];

  function shouldIntercept(url: string): boolean {
    let parsed: URL;
    try {
      parsed = new URL(url, window.location.origin);
    } catch {
      return false;
    }
    if (!SHOULD_INTERCEPT_HOSTS.includes(parsed.host)) return false;
    return SHOULD_INTERCEPT_PATHS.some((p) => parsed.pathname.includes(p));
  }

  /**
   * Best-effort: extract user-authored text from a request body. Returns
   * null when we don't recognise the shape (we pass through unchanged
   * in that case to avoid breaking the site).
   */
  function extractText(body: string): { text: string; path: string[] } | null {
    let j: unknown;
    try {
      j = JSON.parse(body);
    } catch {
      return null;
    }
    if (j === null || typeof j !== 'object') return null;
    const obj = j as Record<string, unknown>;

    // OpenAI / Mistral / Copilot — `messages: [{role:'user', content:...}]`
    if (Array.isArray(obj['messages'])) {
      const msgs = obj['messages'] as Array<Record<string, unknown>>;
      for (let i = msgs.length - 1; i >= 0; i -= 1) {
        const m = msgs[i];
        if (!m) continue;
        if (m['role'] !== 'user') continue;
        const content = m['content'];
        if (typeof content === 'string' && content.length > 0) {
          return { text: content, path: ['messages', String(i), 'content'] };
        }
        if (Array.isArray(content)) {
          // Anthropic-style content blocks: [{type:'text', text:'...'}].
          for (let k = 0; k < content.length; k += 1) {
            const part = content[k] as Record<string, unknown> | undefined;
            if (part && part['type'] === 'text' && typeof part['text'] === 'string') {
              return {
                text: part['text'] as string,
                path: ['messages', String(i), 'content', String(k), 'text'],
              };
            }
          }
        }
      }
    }

    // ChatGPT legacy `prompt: 'string'`
    if (typeof obj['prompt'] === 'string') {
      return { text: obj['prompt'] as string, path: ['prompt'] };
    }

    return null;
  }

  function setPath(root: unknown, path: string[], value: string): void {
    if (path.length === 0) return;
    let cur: unknown = root;
    for (let i = 0; i < path.length - 1; i += 1) {
      const k = path[i];
      if (cur === null || typeof cur !== 'object' || k === undefined) return;
      const idx: string | number = /^\d+$/.test(k) ? Number(k) : k;
      cur = (cur as Record<string | number, unknown>)[idx];
    }
    const last = path[path.length - 1];
    if (last === undefined || cur === null || typeof cur !== 'object') return;
    const lastIdx: string | number = /^\d+$/.test(last) ? Number(last) : last;
    (cur as Record<string | number, unknown>)[lastIdx] = value;
  }

  /**
   * Round-trip a decision via the content script. Returns the modified
   * body OR `null` to mean "block — abort the fetch".
   */
  function requestDecision(url: string, method: string, body: string): Promise<string | null> {
    return new Promise<string | null>((resolve) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const onMessage = (ev: MessageEvent) => {
        if (ev.source !== window) return;
        const data = ev.data as { tag?: string; kind?: string; id?: string; action?: string; sanitisedBody?: string | null };
        if (!data || data.tag !== TAG || data.id !== id || data.kind !== 'fetch.decision') return;
        window.removeEventListener('message', onMessage);
        if (data.action === 'block') {
          resolve(null);
          return;
        }
        if (data.action === 'mask' && typeof data.sanitisedBody === 'string') {
          resolve(data.sanitisedBody);
          return;
        }
        resolve(body);
      };
      window.addEventListener('message', onMessage);
      const out: { tag: string; kind: string; id: string; url: string; method: string; body: string } = {
        tag: TAG,
        kind: 'fetch.intercept',
        id,
        url,
        method,
        body,
      };
      window.postMessage(out, window.location.origin);
      // Safety net: drop after 8 s.
      setTimeout(() => {
        window.removeEventListener('message', onMessage);
        resolve(body);
      }, 8000);
    });
  }

  // ---- fetch -------------------------------------------------------------
  const origFetch = window.fetch.bind(window);
  type FetchArgs = Parameters<typeof window.fetch>;
  window.fetch = async function sectionFetch(...args: FetchArgs): Promise<Response> {
    const [input, init] = args;
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input instanceof Request
            ? input.url
            : '';
    const method = (
      init?.method ?? (input instanceof Request ? input.method : 'GET')
    ).toUpperCase();
    if (method !== 'POST' || !shouldIntercept(url)) {
      return origFetch(...args);
    }
    let rawBody: string | null = null;
    if (init?.body && typeof init.body === 'string') rawBody = init.body;
    else if (input instanceof Request) {
      try {
        rawBody = await input.clone().text();
      } catch {
        rawBody = null;
      }
    }
    if (!rawBody) return origFetch(...args);
    const extracted = extractText(rawBody);
    if (!extracted) return origFetch(...args);
    const sanitisedBody = await requestDecision(url, method, rawBody);
    if (sanitisedBody === null) {
      // Block — fabricate a synthetic response so the page sees an
      // explicit error instead of hanging.
      return new Response('blocked by Section', {
        status: 451,
        statusText: 'Unavailable For Legal Reasons',
      });
    }
    // Mask path: replace the user text in the body and pass on.
    let nextBody = sanitisedBody;
    if (nextBody === rawBody) {
      nextBody = rawBody; // allow
    } else {
      try {
        const parsed = JSON.parse(rawBody);
        setPath(parsed, extracted.path, sanitisedBody);
        nextBody = JSON.stringify(parsed);
      } catch {
        // Caller sent us a literal replacement body — use as-is.
      }
    }
    const newInit: RequestInit = { ...(init ?? {}), body: nextBody };
    if (input instanceof Request) {
      return origFetch(new Request(input, newInit));
    }
    return origFetch(input as RequestInfo | URL, newInit);
  };

  // ---- XMLHttpRequest ----------------------------------------------------
  const origXhrOpen = XMLHttpRequest.prototype.open;
  const origXhrSend = XMLHttpRequest.prototype.send;
  // The DOM lib types XHR.open as having two overloads; here we declare
  // it as a single rest-args function so we can pass through unchanged.
  type XhrOpen = (this: XMLHttpRequest, ...args: unknown[]) => void;
  (XMLHttpRequest.prototype.open as unknown as XhrOpen) = function sectionOpen(
    this: XMLHttpRequest,
    ...args: unknown[]
  ): void {
    const method = String(args[0] ?? 'GET');
    const url = args[1];
    (this as XMLHttpRequest & { __sectionMethod?: string; __sectionUrl?: string }).__sectionMethod = method;
    (this as XMLHttpRequest & { __sectionMethod?: string; __sectionUrl?: string }).__sectionUrl = String(url ?? '');
    return (origXhrOpen as unknown as XhrOpen).apply(this, args);
  };
  XMLHttpRequest.prototype.send = function sectionSend(
    body?: Document | XMLHttpRequestBodyInit | null,
  ): void {
    const meta = this as XMLHttpRequest & { __sectionMethod?: string; __sectionUrl?: string };
    const method = (meta.__sectionMethod ?? 'GET').toUpperCase();
    const url = meta.__sectionUrl ?? '';
    if (method !== 'POST' || !shouldIntercept(url) || typeof body !== 'string') {
      return origXhrSend.call(this, body ?? null);
    }
    const extracted = extractText(body);
    if (!extracted) return origXhrSend.call(this, body);
    requestDecision(url, method, body).then(
      (sanitised) => {
        if (sanitised === null) {
          // Abort + dispatch a fake error so the page sees the block.
          this.abort();
          return;
        }
        let next = sanitised;
        if (sanitised !== body) {
          try {
            const parsed = JSON.parse(body);
            setPath(parsed, extracted.path, sanitised);
            next = JSON.stringify(parsed);
          } catch {
            // pass
          }
        }
        origXhrSend.call(this, next);
      },
      () => origXhrSend.call(this, body),
    );
  };
})();
