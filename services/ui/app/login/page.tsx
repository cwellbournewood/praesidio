'use client';

export const dynamic = 'force-dynamic';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { signIn } from 'next-auth/react';
import { ArrowRight, Loader2, Volume2, VolumeX } from 'lucide-react';
import { Waveform, type WaveformHandle } from '@/components/praesidio/Waveform';
import { LiveClock } from '@/components/praesidio/LoginAmbient';

/**
 * Praesidio sign-in — minimal centered card above an arching string field
 * that "plucks" with every keystroke. Strip everything else away. Let the
 * instrument speak.
 */
export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const callbackUrl = params.get('callbackUrl') || '/';
  const initialError = params.get('error');
  const wave = useRef<WaveformHandle>(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(
    initialError ? 'Sign-in failed. Try again.' : null,
  );

  // Sound on/off, persisted. Default OFF — browsers require a gesture to
  // start audio anyway, and silent-first respects shared-office contexts.
  const [sound, setSound] = useState(false);
  useEffect(() => {
    setSound(localStorage.getItem('praesidio.login.sound') === 'on');
  }, []);
  const toggleSound = () => {
    setSound((s) => {
      const next = !s;
      localStorage.setItem('praesidio.login.sound', next ? 'on' : 'off');
      // Pluck once on enable so the user immediately hears the timbre.
      if (next) window.setTimeout(() => wave.current?.touch(undefined, 0.7), 30);
      return next;
    });
  };

  const pluck = (strength = 0.6) => wave.current?.touch(undefined, strength);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (pending) return;
    setError(null);
    setPending(true);
    // A three-note flourish on submit.
    pluck(1.2);
    window.setTimeout(() => pluck(0.9), 110);
    window.setTimeout(() => pluck(0.7), 230);
    try {
      const result = await signIn('keycloak', {
        username,
        password,
        callbackUrl,
        redirect: false,
      });
      if (result?.ok && !result.error) {
        router.push(result.url ?? callbackUrl);
        router.refresh();
      } else {
        setError(
          result?.error === 'CredentialsSignin'
            ? 'Wrong username or password.'
            : 'Sign-in failed. Try again.',
        );
        setPending(false);
      }
    } catch {
      setError('Network error. Is Keycloak reachable?');
      setPending(false);
    }
  };

  return (
    <div className="relative min-h-screen flex flex-col bg-canvas text-text-primary overflow-hidden">
      {/* topbar — almost nothing */}
      <header className="relative z-30 h-10 flex items-center justify-between px-6 border-b border-border bg-canvas/95 backdrop-blur-[2px]">
        <div className="flex items-center gap-2.5 font-mono text-[11px] tracking-[0.06em]">
          <span className="font-serif italic text-vermillion text-[20px] leading-none -translate-y-px">
            §
          </span>
          <span className="font-serif italic text-[15px] text-text-primary">
            Praesidio
          </span>
        </div>
        <div className="flex items-center gap-4 font-mono text-[10px] tracking-[0.14em] uppercase text-text-tertiary">
          <button
            type="button"
            onClick={toggleSound}
            className="inline-flex items-center gap-1.5 text-text-tertiary hover:text-text-primary transition-colors focus-visible:outline-2 focus-visible:outline-vermillion focus-visible:outline-offset-2"
            aria-label={sound ? 'Mute the strings' : 'Play the strings'}
            aria-pressed={sound}
          >
            {sound ? (
              <Volume2 className="h-3 w-3 text-vermillion" strokeWidth={1.75} />
            ) : (
              <VolumeX className="h-3 w-3" strokeWidth={1.75} />
            )}
            <span>{sound ? 'sound' : 'silent'}</span>
          </button>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-[6px] w-[6px] bg-moss"
              aria-hidden
            />
            <span>gateway ok</span>
          </span>
          <span className="tabular-nums">
            UTC <LiveClock className="ml-1 text-text-primary" />
          </span>
        </div>
      </header>

      {/* centered sign-in — main is pointer-transparent so mouse events
          fall through the empty area onto the canvas below; only the form
          section opts back in to receive clicks. */}
      <main className="relative z-20 flex-1 flex items-start justify-center pt-[14vh] pb-[40vh] pointer-events-none">
        <section className="w-[380px] pointer-events-auto" aria-labelledby="t">
          <h1
            id="t"
            className="font-serif italic font-normal text-[44px] leading-[1] tracking-[-0.02em] text-text-primary m-0 text-center"
          >
            Sign in
          </h1>
          <p className="font-serif italic text-text-tertiary text-[15px] text-center m-0 mt-1.5 mb-10">
            to{' '}
            <span className="text-vermillion">praesidio</span>
            <span className="text-text-tertiary">.</span>
          </p>

          {error && (
            <div
              role="alert"
              className="mb-6 grid grid-cols-[3px_1fr] gap-3 items-stretch px-3 py-2.5 border border-border bg-surface"
            >
              <span className="bg-vermillion" />
              <span className="font-mono text-[11px] text-text-primary leading-snug">
                {error}
              </span>
            </div>
          )}

          <form onSubmit={onSubmit} noValidate className="grid gap-7">
            <Field
              name="username"
              label="Username"
              type="text"
              value={username}
              onChange={(v) => {
                setUsername(v);
                pluck(0.5);
              }}
              autoFocus
              autoComplete="username"
              disabled={pending}
            />
            <Field
              name="password"
              label="Password"
              type="password"
              value={password}
              onChange={(v) => {
                setPassword(v);
                pluck(0.4);
              }}
              autoComplete="current-password"
              disabled={pending}
              mono
            />

            <button
              type="submit"
              disabled={pending || !username || !password}
              className="group relative mt-2 inline-flex items-center justify-center gap-2.5 px-5 py-3 bg-text-primary text-canvas border border-text-primary font-mono text-[11.5px] tracking-[0.18em] uppercase hover:bg-text-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-2 focus-visible:outline-vermillion focus-visible:outline-offset-2"
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <span
                  className="inline-block w-[7px] h-[7px] bg-moss transition-colors group-hover:bg-vermillion"
                  aria-hidden
                />
              )}
              <span>{pending ? 'Signing in…' : 'Enter'}</span>
              {!pending && (
                <ArrowRight
                  className="h-3.5 w-3.5 ml-auto transition-transform group-hover:translate-x-0.5"
                  strokeWidth={2}
                />
              )}
            </button>
          </form>

          <p className="mt-10 text-center font-mono text-[10px] tracking-[0.18em] uppercase text-text-tertiary">
            12.4k mediated · 0.4% blocked
            <span className="text-border mx-1.5">·</span>
            last 24h
          </p>
        </section>
      </main>

      {/* arching waveform — lower 40% */}
      <div className="absolute bottom-7 left-0 right-0 h-[40vh] z-10">
        <Waveform
          ref={wave}
          sound={sound}
          className="absolute inset-0 w-full h-full"
        />
      </div>

      {/* footer — single micro line */}
      <footer className="relative z-30 border-t border-border bg-canvas/95 backdrop-blur-[2px] h-7 flex items-center justify-between px-6 font-mono text-[10px] tracking-[0.18em] uppercase text-text-tertiary">
        <span>
          realm <span className="text-text-primary">praesidio</span>
        </span>
        <span className="font-serif italic normal-case tracking-[0] text-[12px] text-text-secondary">
          Look before you ship.
        </span>
        <span>v0.1.0 · staging</span>
      </footer>
    </div>
  );
}

// ---------- field ----------

function Field({
  label,
  name,
  type,
  value,
  onChange,
  autoComplete,
  autoFocus,
  disabled,
  mono,
}: {
  label: string;
  name: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  mono?: boolean;
}) {
  return (
    <label className="grid gap-2">
      <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-tertiary">
        {label}
      </span>
      <div className="relative">
        <input
          type={type}
          name={name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          spellCheck={false}
          disabled={disabled}
          className={[
            'peer w-full appearance-none rounded-none px-0 pb-2 pt-1 bg-transparent border-0 border-b border-border outline-none text-text-primary text-[15px] focus:border-text-primary placeholder:text-text-tertiary disabled:opacity-50 transition-colors',
            mono ? 'font-mono tracking-[0.06em]' : 'font-sans',
          ].join(' ')}
        />
        {/* vermillion focus-line grows from center */}
        <span
          aria-hidden
          className="pointer-events-none absolute left-0 right-0 bottom-0 h-[2px] origin-center scale-x-0 bg-vermillion transition-transform duration-300 ease-out peer-focus:scale-x-100"
        />
      </div>
    </label>
  );
}
