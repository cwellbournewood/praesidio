'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { StatusBar } from './StatusBar';

/**
 * Wraps page content in the operator-console chrome (sidebar / topbar /
 * status bar) — except on auth routes like /login, where we render the
 * page edge-to-edge so the landing fills the viewport.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const isAuthRoute =
    path?.startsWith('/login') ||
    path?.startsWith('/signout') ||
    path?.startsWith('/auth-error');

  if (isAuthRoute) {
    return <main className="min-h-screen bg-canvas">{children}</main>;
  }

  return (
    <div className="app-grid">
      <Sidebar />
      <div className="app-main min-w-0 flex flex-col">
        <Topbar />
        <main className="flex-1 min-w-0">{children}</main>
        <StatusBar />
      </div>
    </div>
  );
}
