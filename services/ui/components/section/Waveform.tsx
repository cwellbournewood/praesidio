'use client';

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react';

export type WaveformHandle = {
  /** Pluck a string. Optional x in canvas pixels; omitted = random within the arch's belly. */
  touch: (x?: number, strength?: number) => void;
};

type Ripple = { x: number; t0: number; amp: number };

// C major pentatonic across two octaves — every note sounds consonant
// with every other, so any combination of plucks resolves musically.
const HARP_SCALE = [
  261.63, // C4
  293.66, // D4
  329.63, // E4
  392.0, // G4
  440.0, // A4
  523.25, // C5
  587.33, // D5
  659.25, // E5
  783.99, // G5
  880.0, // A5
];

const ATTACK = 0.22; // seconds — cosine rise of each ripple
const RELEASE = 1.8; // seconds — exponential fall
const TOTAL_LIFE = ATTACK + RELEASE;

/**
 * Canvas waveform — a field of thin vertical strings spread across the width,
 * heights modulated by an arching envelope and a sum of low-frequency sines
 * (so the whole field idles like a sleeping instrument).
 *
 * On `touch()` (or mouse-hover, or touch-drag), a Gaussian ripple is added
 * at that x. Nearby strings smoothly amplify and glow vermillion, then
 * release back to idle over ~2s. Optionally plays a soft-harp note via
 * additive Web-Audio synthesis (4 sine partials + lowpass) on each pluck.
 *
 * Pure presentation. Honours `prefers-reduced-motion` for idle animation;
 * ripples remain to keep the page responsive to interaction.
 */
export const Waveform = forwardRef<
  WaveformHandle,
  { className?: string; sound?: boolean }
>(function Waveform({ className, sound = false }, ref) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const ripplesRef = useRef<Ripple[]>([]);
  const sizeRef = useRef<{ w: number; h: number; dpr: number }>({
    w: 0,
    h: 0,
    dpr: 1,
  });

  // Audio
  const audioRef = useRef<{ ctx: AudioContext; master: GainNode } | null>(null);
  const soundRef = useRef(sound);
  useEffect(() => {
    soundRef.current = sound;
  }, [sound]);

  const ensureAudio = () => {
    if (audioRef.current) return audioRef.current;
    try {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const ctx = new AC();
      const master = ctx.createGain();
      master.gain.value = 0.45;
      master.connect(ctx.destination);
      audioRef.current = { ctx, master };
      return audioRef.current;
    } catch {
      return null;
    }
  };

  /**
   * Schedule a soft-harp pluck. Note is chosen by mapping x to the
   * pentatonic scale, so any sweep across the canvas plays an arpeggio.
   */
  const playNote = (x: number, strength: number) => {
    if (!soundRef.current) return;
    const audio = ensureAudio();
    if (!audio) return;
    const { ctx, master } = audio;
    if (ctx.state === 'suspended') ctx.resume();

    const w = sizeRef.current.w;
    if (!w) return;
    const idx = Math.max(
      0,
      Math.min(
        HARP_SCALE.length - 1,
        Math.floor((x / w) * HARP_SCALE.length),
      ),
    );
    const freq = HARP_SCALE[idx];
    const t0 = ctx.currentTime;
    const peak = 0.12 * Math.max(0.15, Math.min(1.4, strength));

    // Warm lowpass that closes as the note decays (mellower fall).
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(3400, t0);
    filter.frequency.exponentialRampToValueAtTime(820, t0 + 1.6);
    filter.Q.value = 0.5;
    filter.connect(master);

    // 4 sine partials with descending gain/decay — gives a harp-like timbre
    // without the percussive edge of Karplus-Strong.
    const partials = [
      { mul: 1, gain: 1.0, decay: 1.7 },
      { mul: 2, gain: 0.42, decay: 1.1 },
      { mul: 3, gain: 0.2, decay: 0.85 },
      { mul: 4, gain: 0.1, decay: 0.65 },
    ];
    for (const p of partials) {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = freq * p.mul;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.linearRampToValueAtTime(peak * p.gain, t0 + 0.006);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + p.decay);
      osc.connect(g).connect(filter);
      osc.start(t0);
      osc.stop(t0 + p.decay + 0.05);
    }
  };

  useImperativeHandle(
    ref,
    () => ({
      touch(x?: number, strength = 1) {
        const w = sizeRef.current.w;
        if (!w) return;
        const touchX =
          typeof x === 'number' ? x : w * (0.3 + Math.random() * 0.4);
        ripplesRef.current.push({
          x: touchX,
          t0: performance.now(),
          amp: 0.7 * strength + Math.random() * 0.4 * strength,
        });
        if (ripplesRef.current.length > 18) ripplesRef.current.shift();
        playNote(touchX, strength);
      },
    }),
    [],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const setSize = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sizeRef.current = { w, h, dpr };
    };
    setSize();
    const ro = new ResizeObserver(setSize);
    ro.observe(canvas);

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Denser strings + tighter spacing = smoother continuous wave read.
    const SPACING = 5;
    const STRING_W = 1.5;

    let raf = 0;
    const draw = (time: number) => {
      const { w, h } = sizeRef.current;
      ctx.clearRect(0, 0, w, h);

      const cy = h * 0.5;
      // Bow line: a hairline through the resting axis of the strings.
      ctx.fillStyle = 'rgba(15, 15, 14, 0.06)';
      ctx.fillRect(0, cy - 0.5, w, 1);

      const ripples = ripplesRef.current;
      for (let x = 0; x <= w; x += SPACING) {
        const env = Math.sin((Math.PI * x) / w);
        if (env < 0.012) continue;

        // Idle: 4 layered sines at slow speeds — looks like a gently
        // breathing surface rather than a twitchy field.
        let base = 0;
        if (!reducedMotion) {
          const t = time / 1000;
          const a = Math.sin(x * 0.014 + t * 0.55);
          const b = Math.sin(x * 0.009 - t * 0.4 + 1.3);
          const c = Math.sin(x * 0.022 + t * 0.32 + 2.1);
          const d = Math.sin(x * 0.006 - t * 0.2 + 0.7);
          base = a * 0.40 + b * 0.28 + c * 0.18 + d * 0.14;
        }

        // Ripples: cosine attack (smooth rise) → exponential release.
        let rip = 0;
        let hot = 0;
        for (let i = 0; i < ripples.length; i += 1) {
          const r = ripples[i];
          const dt = (time - r.t0) / 1000;
          if (dt < 0 || dt > TOTAL_LIFE) continue;
          let envT: number;
          if (dt < ATTACK) {
            // 0 → 1 over ATTACK seconds, smooth cosine ease-in.
            envT = 0.5 * (1 - Math.cos((Math.PI * dt) / ATTACK));
          } else {
            // Then exponential decay toward zero.
            envT = Math.exp(-(dt - ATTACK) * 1.5);
          }
          const sigma = 32 + dt * 75; // expanding wavefront
          const d2 = x - r.x;
          const g = Math.exp(-(d2 * d2) / (2 * sigma * sigma));
          rip += envT * g * r.amp;
          hot += envT * g * r.amp;
        }

        const idle = env * (h * 0.4) * (0.28 + 0.22 * base);
        const ripple = env * (h * 0.42) * rip;
        const totalH = Math.max(1.5, idle + ripple);

        // Lerp toward vermillion when the string is hot.
        const hotMix = Math.min(1, hot * 1.3);
        const baseAlpha = 0.16 + env * 0.55;
        const alpha = Math.min(1, baseAlpha + hotMix * 0.35);
        const rC = Math.round(15 + (209 - 15) * hotMix);
        const gC = Math.round(15 + (75 - 15) * hotMix);
        const bC = Math.round(14 + (44 - 14) * hotMix);
        ctx.fillStyle = `rgba(${rC}, ${gC}, ${bC}, ${alpha})`;
        ctx.fillRect(x - STRING_W / 2, cy - totalH / 2, STRING_W, totalH);
      }

      // GC ripples past their lifetime.
      ripplesRef.current = ripples.filter(
        (r) => time - r.t0 < TOTAL_LIFE * 1000 + 50,
      );

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    // Mouse: plucks strings under the cursor. Visual ripples throttled
    // to ~90ms, audio throttled to ~290ms so hovering doesn't spam notes.
    let lastMove = 0;
    let lastSound = 0;
    const onMove = (e: MouseEvent) => {
      const now = performance.now();
      if (now - lastMove < 90) return;
      lastMove = now;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      ripplesRef.current.push({ x, t0: now, amp: 0.35 });
      if (now - lastSound > 290) {
        lastSound = now;
        playNote(x, 0.35);
      }
    };
    canvas.addEventListener('mousemove', onMove);

    const onTouch = (e: TouchEvent) => {
      const now = performance.now();
      if (now - lastMove < 70) return;
      lastMove = now;
      const rect = canvas.getBoundingClientRect();
      for (let i = 0; i < e.touches.length; i += 1) {
        const x = e.touches[i].clientX - rect.left;
        ripplesRef.current.push({ x, t0: now, amp: 0.55 });
        if (now - lastSound > 220) {
          lastSound = now;
          playNote(x, 0.55);
        }
      }
    };
    canvas.addEventListener('touchmove', onTouch, { passive: true });
    canvas.addEventListener('touchstart', onTouch, { passive: true });

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('touchmove', onTouch);
      canvas.removeEventListener('touchstart', onTouch);
    };
  }, []);

  // Suspend audio on unmount.
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        try {
          audioRef.current.ctx.close();
        } catch {
          /* noop */
        }
        audioRef.current = null;
      }
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden />;
});
