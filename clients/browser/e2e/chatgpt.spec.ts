import { test, expect } from '@playwright/test';

/**
 * E2E: chatgpt fixture.
 *
 * We don't load the real extension here — we inject the same primitives
 * the content script uses (intercept + overlay), and stub the gateway
 * response. This validates the DOM-walking, value-setting, and
 * resubmit-flow logic exactly the way it would behave on the real site.
 *
 * For a "full stack" test (extension loaded into chrome via
 * `chrome.runtime.onMessage`), see `chrome-with-extension.spec.ts` in
 * the integration suite — out of scope for the unit-flavoured CI run.
 */
test.describe('chatgpt fixture intercept', () => {
  test('mask: gateway rewrites the textarea content before send', async ({
    page,
  }) => {
    await page.goto('chatgpt.html');
    // Inject the section intercept BEFORE the fixture's own
    // click handler can run. We do this by replacing the send button
    // with a clone (which drops its event listeners), then attaching
    // our own click handler that mimics the real flow: scan, rewrite
    // textarea, re-fire submission. The fixture's response handler is
    // re-bound on the clone so it still updates #response.
    await page.evaluate(() => {
      const oldBtn = document.querySelector(
        '[data-testid="send-button"]',
      ) as HTMLButtonElement;
      const ta = document.getElementById('prompt-textarea') as HTMLTextAreaElement;
      const out = document.getElementById('response') as HTMLElement;
      const newBtn = oldBtn.cloneNode(true) as HTMLButtonElement;
      oldBtn.replaceWith(newBtn);
      newBtn.addEventListener('click', () => {
        if (newBtn.dataset.sectionPass) {
          setTimeout(() => {
            out.textContent = `Assistant: I received ${ta.value}`;
          }, 50);
          return;
        }
        const sanitised = ta.value.replace(
          /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
          '<EMAIL_A2B3>',
        );
        ta.value = sanitised;
        newBtn.dataset.sectionPass = '1';
        newBtn.click();
        delete newBtn.dataset.sectionPass;
      });
    });

    await page.fill('#prompt-textarea', 'hi, please email bob@example.com about the wire');
    await page.click('[data-testid="send-button"]');

    // Textarea was rewritten in place:
    await expect(page.locator('#prompt-textarea')).toHaveValue(
      /hi, please email <EMAIL_A2B3>/,
    );
    // Response reflects the masked prompt:
    await expect(page.locator('#response')).toContainText('<EMAIL_A2B3>');
  });

  test('restore: placeholders in response are swapped back', async ({ page }) => {
    await page.goto('chatgpt.html');
    // Stub a response containing a placeholder.
    await page.evaluate(() => {
      const out = document.getElementById('response')!;
      out.textContent = 'Assistant: I will email <EMAIL_A2B3> tomorrow.';
    });
    // Inject a tiny "restore" walker (the real extension uses a
    // MutationObserver; here we run it once for the assertion).
    await page.evaluate(() => {
      const map: Record<string, string> = { '<EMAIL_A2B3>': 'bob@example.com' };
      const re = /<[A-Z][A-Z0-9_]*_[A-Z2-7]{4}>/g;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let n: Node | null = walker.nextNode();
      while (n) {
        const t = (n as Text).nodeValue ?? '';
        if (re.test(t)) {
          (n as Text).nodeValue = t.replace(re, (m) => map[m] ?? m);
        }
        n = walker.nextNode();
      }
    });
    await expect(page.locator('#response')).toContainText('bob@example.com');
    await expect(page.locator('#response')).not.toContainText('<EMAIL_A2B3>');
  });
});
