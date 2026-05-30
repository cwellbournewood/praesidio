/**
 * Minimal vanilla-DOM overlay banners used inside the content world.
 *
 * We don't load React in the content world — it would balloon the
 * per-tab memory footprint and force per-site CSP exceptions. The
 * banners are a small fixed-position card with a backdrop blur, indigo
 * accent (#4F46E5), Geist-style stack falling back to system sans.
 *
 * All three banners share one container so the most recent message
 * replaces older ones. Banners auto-dismiss after a few seconds; the
 * block banner stays until the user clicks Dismiss.
 */
const CONTAINER_ID = 'section-overlay-root';
const STYLE_ID = 'section-overlay-style';

const STYLES = `
  #${CONTAINER_ID} {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 2147483646;
    width: 360px;
    max-width: calc(100vw - 32px);
    pointer-events: none;
    font-family: 'Geist', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  #${CONTAINER_ID} .section-card {
    pointer-events: auto;
    background: #FAFAF7;
    color: #181818;
    border: 1px solid #181818;
    box-shadow: 0 1px 0 #181818;
    padding: 14px 16px;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.5;
    letter-spacing: -0.005em;
    animation: section-fade 140ms cubic-bezier(0.2, 0, 0, 1);
  }
  @media (prefers-color-scheme: dark) {
    #${CONTAINER_ID} .section-card {
      background: #111;
      color: #f7f7f4;
      border-color: #f7f7f4;
      box-shadow: 0 1px 0 #f7f7f4;
    }
  }
  #${CONTAINER_ID} .section-card[data-variant="block"] {
    border-left: 3px solid #b73a3a;
  }
  #${CONTAINER_ID} .section-card[data-variant="mask"] {
    border-left: 3px solid #4F46E5;
  }
  #${CONTAINER_ID} .section-card[data-variant="error"] {
    border-left: 3px solid #d97706;
  }
  #${CONTAINER_ID} .section-title {
    font-weight: 600;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  #${CONTAINER_ID} .section-eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 10px;
    color: #4F46E5;
    font-weight: 500;
  }
  #${CONTAINER_ID} .section-body {
    color: #4a4a4a;
    margin: 4px 0 0 0;
  }
  @media (prefers-color-scheme: dark) {
    #${CONTAINER_ID} .section-body { color: #c5c5c2; }
  }
  #${CONTAINER_ID} .section-actions {
    margin-top: 10px;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  #${CONTAINER_ID} button {
    font: inherit;
    border: 1px solid currentColor;
    background: transparent;
    color: inherit;
    padding: 4px 10px;
    cursor: pointer;
    letter-spacing: -0.005em;
  }
  #${CONTAINER_ID} button.primary {
    background: #4F46E5;
    color: #fff;
    border-color: #4F46E5;
  }
  #${CONTAINER_ID} button:focus-visible {
    outline: 2px solid #4F46E5;
    outline-offset: 2px;
  }
  @keyframes section-fade {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;

function ensureRoot(): HTMLElement {
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = STYLES;
    document.head.appendChild(style);
  }
  let root = document.getElementById(CONTAINER_ID);
  if (!root) {
    root = document.createElement('div');
    root.id = CONTAINER_ID;
    root.setAttribute('aria-live', 'polite');
    root.setAttribute('role', 'status');
    document.documentElement.appendChild(root);
  }
  return root;
}

function clearCards(root: HTMLElement, variant?: string): void {
  const sel = variant ? `.section-card[data-variant="${variant}"]` : '.section-card';
  root.querySelectorAll(sel).forEach((c) => c.remove());
}

function mountCard(opts: {
  variant: 'block' | 'mask' | 'error';
  eyebrow: string;
  title: string;
  body: string;
  actions?: Array<{ label: string; primary?: boolean; onClick: () => void }>;
  autoDismissMs?: number;
}): void {
  const root = ensureRoot();
  clearCards(root, opts.variant);
  const card = document.createElement('div');
  card.className = 'section-card';
  card.dataset.variant = opts.variant;
  card.setAttribute('role', opts.variant === 'block' ? 'alertdialog' : 'status');

  const titleBar = document.createElement('div');
  titleBar.className = 'section-title';
  const eyebrow = document.createElement('span');
  eyebrow.className = 'section-eyebrow';
  eyebrow.textContent = opts.eyebrow;
  const titleEl = document.createElement('span');
  titleEl.textContent = opts.title;
  titleBar.appendChild(titleEl);
  titleBar.appendChild(eyebrow);
  card.appendChild(titleBar);

  const body = document.createElement('p');
  body.className = 'section-body';
  body.textContent = opts.body;
  card.appendChild(body);

  if (opts.actions && opts.actions.length > 0) {
    const actionRow = document.createElement('div');
    actionRow.className = 'section-actions';
    for (const a of opts.actions) {
      const btn = document.createElement('button');
      btn.textContent = a.label;
      if (a.primary) btn.className = 'primary';
      btn.addEventListener('click', () => {
        a.onClick();
        card.remove();
      });
      actionRow.appendChild(btn);
    }
    card.appendChild(actionRow);
  }
  root.appendChild(card);
  if (opts.autoDismissMs && opts.autoDismissMs > 0) {
    setTimeout(() => card.remove(), opts.autoDismissMs);
  }
}

export function renderBlockOverlay(o: { reason: string; severity: string }): void {
  mountCard({
    variant: 'block',
    eyebrow: 'SECTION',
    title: 'This prompt was blocked',
    body: `${o.reason} · severity: ${o.severity}`,
    actions: [{ label: 'Dismiss', onClick: () => undefined }],
  });
}

export function renderMaskBanner(o: { count: number }): void {
  mountCard({
    variant: 'mask',
    eyebrow: 'SECTION',
    title: 'Sensitive data masked',
    body:
      o.count === 1
        ? '1 token was rewritten before send. The response will be restored automatically.'
        : `${o.count} tokens were rewritten before send. The response will be restored automatically.`,
    autoDismissMs: 4500,
  });
}

export function renderErrorOverlay(o: {
  message: string;
  onRetry: () => void | Promise<void>;
}): void {
  mountCard({
    variant: 'error',
    eyebrow: 'SECTION',
    title: 'Could not scan this prompt',
    body: `Gateway error: ${o.message}. Click retry to try again.`,
    actions: [{ label: 'Retry', primary: true, onClick: () => void o.onRetry() }],
  });
}

/** Public for tests. */
export const _internal = {
  CONTAINER_ID,
  STYLE_ID,
  ensureRoot,
};
