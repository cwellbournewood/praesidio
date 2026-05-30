'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { SessionProvider } from 'next-auth/react';
import { ThemeProvider } from 'next-themes';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ToastProvider } from '@/components/ui/toast';
import { CommandPaletteProvider } from '@/components/section/CommandPalette';
import { KeyboardShortcuts } from '@/components/section/KeyboardShortcuts';
import { RuntimeModeProvider } from '@/lib/runtime-mode';
import { TenantProvider } from '@/lib/tenant';
import { mountAxe } from '@/lib/a11y';

/**
 * First-run gate. If the operator has never completed onboarding (no
 * `section.onboarded` flag in localStorage) and is landing on the
 * dashboard, send them through the wizard. Honoured once per session so a
 * deliberate revisit to "/" doesn't trap them.
 */
function FirstRunGate() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (pathname !== '/') return;
    // Escape hatch: `?bypass=onboarding` lets headless screenshots, e2e
    // tests, and the README capture script land on the dashboard directly
    // without polluting localStorage.
    if (window.location.search.includes('bypass=onboarding')) return;
    const onboarded = window.localStorage.getItem('section.onboarded');
    const redirected = window.sessionStorage.getItem('section.firstRunRedirected');
    if (!onboarded && !redirected) {
      window.sessionStorage.setItem('section.firstRunRedirected', '1');
      router.replace('/onboarding');
    }
  }, [pathname, router]);

  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Mount axe-core in dev only. No-op in production builds.
    void mountAxe();
  }, []);

  return (
    <SessionProvider>
      <ThemeProvider
        attribute="data-theme"
        defaultTheme="light"
        themes={['light', 'dark', 'high-contrast']}
        enableSystem={false}
      >
        <RuntimeModeProvider>
          <TenantProvider>
            <TooltipProvider delayDuration={200}>
              <ToastProvider>
                <CommandPaletteProvider>
                  <FirstRunGate />
                  <KeyboardShortcuts />
                  {children}
                </CommandPaletteProvider>
              </ToastProvider>
            </TooltipProvider>
          </TenantProvider>
        </RuntimeModeProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}
