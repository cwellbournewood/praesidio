import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class', '[data-theme="dark"]'],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: {
        '2xl': '1440px',
      },
    },
    extend: {
      fontFamily: {
        // UI chrome — Geist Sans
        sans: ['var(--font-geist-sans)', 'Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Data / IDs / timestamps — JetBrains Mono
        mono: ['var(--font-geist-mono)', 'JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Editorial display — Instrument Serif
        serif: ['var(--font-instrument-serif)', '"Instrument Serif"', '"Iowan Old Style"', 'Georgia', 'serif'],
        // Alias for editorial display
        display: ['var(--font-instrument-serif)', '"Instrument Serif"', '"Iowan Old Style"', 'Georgia', 'serif'],
      },
      letterSpacing: {
        ui: '-0.005em',
        display: '-0.01em',
        eyebrow: '0.14em',
      },
      fontSize: {
        xs: ['11px', { lineHeight: '15px' }],
        sm: ['12.5px', { lineHeight: '17px' }],
        base: ['13.5px', { lineHeight: '20px' }],
        md: ['15px', { lineHeight: '22px' }],
        lg: ['18px', { lineHeight: '26px' }],
        xl: ['22px', { lineHeight: '28px' }],
        '2xl': ['28px', { lineHeight: '34px' }],
        '3xl': ['38px', { lineHeight: '44px' }],
        '4xl': ['52px', { lineHeight: '58px' }],
        '5xl': ['72px', { lineHeight: '76px' }],
      },
      colors: {
        canvas: 'rgb(var(--color-canvas) / <alpha-value>)',
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          sunken: 'rgb(var(--color-surface-sunken) / <alpha-value>)',
          raised: 'rgb(var(--color-surface-raised) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--color-border) / <alpha-value>)',
          strong: 'rgb(var(--color-border-strong) / <alpha-value>)',
        },
        text: {
          primary: 'rgb(var(--color-text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--color-text-secondary) / <alpha-value>)',
          tertiary: 'rgb(var(--color-text-tertiary) / <alpha-value>)',
        },
        ink: 'rgb(var(--color-text-primary) / <alpha-value>)',
        dust: 'rgb(var(--color-text-tertiary) / <alpha-value>)',
        rule: 'rgb(var(--color-border) / <alpha-value>)',
        bone: {
          DEFAULT: 'rgb(var(--color-canvas) / <alpha-value>)',
          lift: 'rgb(var(--color-surface) / <alpha-value>)',
          deep: 'rgb(var(--color-surface-sunken) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--color-accent) / <alpha-value>)',
          hover: 'rgb(var(--color-accent-hover) / <alpha-value>)',
          soft: 'rgb(var(--color-accent-soft) / <alpha-value>)',
        },
        vermillion: 'rgb(var(--color-accent) / <alpha-value>)',
        moss: 'rgb(var(--color-success) / <alpha-value>)',
        sienna: 'rgb(var(--color-warn) / <alpha-value>)',
        success: {
          DEFAULT: 'rgb(var(--color-success) / <alpha-value>)',
          soft: 'rgb(var(--color-success-soft) / <alpha-value>)',
        },
        warn: {
          DEFAULT: 'rgb(var(--color-warn) / <alpha-value>)',
          soft: 'rgb(var(--color-warn-soft) / <alpha-value>)',
        },
        block: {
          DEFAULT: 'rgb(var(--color-block) / <alpha-value>)',
          soft: 'rgb(var(--color-block-soft) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--color-danger) / <alpha-value>)',
          soft: 'rgb(var(--color-danger-soft) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--color-info) / <alpha-value>)',
        },
      },
      borderColor: {
        DEFAULT: 'rgb(var(--color-border))',
      },
      // Instrument aesthetic: sharp corners across the board.
      // `pill` remains for status dots / circular indicators.
      borderRadius: {
        none: '0',
        xs: '0',
        sm: '0',
        DEFAULT: '0',
        md: '0',
        lg: '0',
        xl: '0',
        '2xl': '0',
        '3xl': '0',
        full: '999px',
        pill: '999px',
      },
      // Hairlines, not shadows.
      boxShadow: {
        low: 'none',
        mid: 'none',
        high: 'none',
        focus: '0 0 0 1px rgb(var(--color-canvas)), 0 0 0 2px rgb(var(--color-accent))',
        rule: 'inset 0 -1px 0 0 rgb(var(--color-border))',
        'rule-t': 'inset 0 1px 0 0 rgb(var(--color-border))',
      },
      transitionTimingFunction: {
        standard: 'cubic-bezier(0.2, 0, 0, 1)',
        emphasised: 'cubic-bezier(0.3, 0, 0, 1)',
      },
      transitionDuration: {
        fast: '80ms',
        base: '140ms',
        slow: '280ms',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-in-right': {
          from: { transform: 'translateX(8px)', opacity: '0' },
          to: { transform: 'translateX(0)', opacity: '1' },
        },
        'slide-in-up': {
          from: { transform: 'translateY(4px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        blink: {
          '0%,49%': { opacity: '1' },
          '50%,100%': { opacity: '0' },
        },
        ticker: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 140ms cubic-bezier(0.2,0,0,1)',
        'slide-in-right': 'slide-in-right 280ms cubic-bezier(0.3,0,0,1)',
        'slide-in-up': 'slide-in-up 140ms cubic-bezier(0.2,0,0,1)',
        'pulse-soft': 'pulse 1.6s ease-in-out infinite',
        blink: 'blink 1s steps(2) infinite',
        ticker: 'ticker 60s linear infinite',
      },
    },
  },
  plugins: [],
};

export default config;
