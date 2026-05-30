import { test, expect } from '@playwright/test';

test.describe('claude fixture intercept', () => {
  test('mask: ProseMirror content is rewritten via paragraph replace', async ({
    page,
  }) => {
    await page.goto('claude.html');
    await page.evaluate(() => {
      const oldBtn = document.querySelector(
        '[aria-label="Send Message"]',
      ) as HTMLButtonElement;
      const editor = document.querySelector('.ProseMirror') as HTMLElement;
      const out = document.getElementById('response') as HTMLElement;
      const newBtn = oldBtn.cloneNode(true) as HTMLButtonElement;
      oldBtn.replaceWith(newBtn);
      const readText = () => {
        const ps = editor.querySelectorAll('p');
        if (ps.length > 0) {
          return Array.from(ps).map((p) => (p as HTMLElement).innerText).join('\n');
        }
        return editor.innerText ?? editor.textContent ?? '';
      };
      newBtn.addEventListener('click', () => {
        if (newBtn.dataset.sectionPass) {
          setTimeout(() => {
            out.textContent = `Assistant: I received ${readText()}`;
          }, 50);
          return;
        }
        const text = readText();
        const sanitised = text.replace(
          /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
          '<EMAIL_K7M2>',
        );
        editor.innerHTML = '';
        const p = document.createElement('p');
        p.textContent = sanitised;
        editor.appendChild(p);
        newBtn.dataset.sectionPass = '1';
        newBtn.click();
        delete newBtn.dataset.sectionPass;
      });
    });

    // Seed the contenteditable directly — page.keyboard.type into a
    // contenteditable is flaky across DOM bindings and not what we're
    // testing here. We just want to confirm the intercept + rewrite
    // path works once content is in place.
    await page.evaluate(() => {
      const editor = document.querySelector('.ProseMirror') as HTMLElement;
      editor.innerHTML = '';
      const p = document.createElement('p');
      p.textContent = 'please email bob@example.com asap';
      editor.appendChild(p);
    });
    await page.click('[aria-label="Send Message"]');

    await expect(page.locator('.ProseMirror')).toContainText('<EMAIL_K7M2>');
    await expect(page.locator('#response')).toContainText('<EMAIL_K7M2>');
  });

  test('block: extension can refuse send', async ({ page }) => {
    await page.goto('claude.html');
    await page.addScriptTag({
      content: `
        document.addEventListener('click', (e) => {
          const btn = e.target && e.target.closest && e.target.closest('[aria-label="Send Message"]');
          if (!btn) return;
          // Simulate Section block: prevent default and mark.
          e.preventDefault();
          e.stopImmediatePropagation();
          document.body.setAttribute('data-section-blocked', '1');
        }, true);
      `,
    });
    await page.locator('.ProseMirror').focus();
    await page.keyboard.type('here is a secret: AKIAEXAMPLE');
    await page.click('[aria-label="Send Message"]');

    // The fixture's response container should be untouched.
    await expect(page.locator('#response')).toHaveText('');
    await expect(page.locator('body')).toHaveAttribute('data-section-blocked', '1');
  });
});
