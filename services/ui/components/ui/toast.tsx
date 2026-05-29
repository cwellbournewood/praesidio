'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface Toast {
  id: number;
  title: string;
  description?: string;
  tone?: 'neutral' | 'success' | 'warn' | 'danger';
}

const ToastContext = React.createContext<{ push: (t: Omit<Toast, 'id'>) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const push = React.useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random();
    setToasts((xs) => [...xs, { ...t, id }]);
    window.setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), 4_000);
  }, []);
  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div
        role="region"
        aria-label="Notifications"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto rounded-md border bg-surface-raised px-3 py-2 shadow-mid animate-slide-in-right',
              t.tone === 'success' && 'border-success/30',
              t.tone === 'warn' && 'border-warn/30',
              t.tone === 'danger' && 'border-danger/30',
              !t.tone && 'border-border',
            )}
          >
            <div className="text-sm font-medium tracking-ui">{t.title}</div>
            {t.description && <div className="mt-0.5 text-xs text-text-secondary">{t.description}</div>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
