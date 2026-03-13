import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', { lineHeight: '1.4' }],
      },
      colors: {
        background:  'var(--background)',
        surface: {
          1: 'var(--surface-1)',
          2: 'var(--surface-2)',
          3: 'var(--surface-3)',
          4: 'var(--surface-4)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover:   'var(--accent-hover)',
          active:  'var(--accent-active)',
          subtle:  'var(--accent-subtle)',
          border:  'var(--accent-border)',
          glow:    'var(--accent-glow)',
        },
      },
      borderRadius: {
        sm:   'var(--radius-sm)',
        md:   'var(--radius-md)',
        lg:   'var(--radius-lg)',
        xl:   'var(--radius-xl)',
        full: 'var(--radius-full)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      transitionTimingFunction: {
        'out':    'cubic-bezier(0.0, 0.0, 0.2, 1)',
        'in-out': 'cubic-bezier(0.4, 0.0, 0.2, 1)',
      },
      transitionDuration: {
        fast: '120ms',
        base: '200ms',
        slow: '350ms',
      },
      animation: {
        'pulse-dot':  'pulse-dot 1.8s ease-in-out infinite',
        'shimmer':    'shimmer 2s ease-in-out infinite',
        'fade-in':    'fade-in 200ms cubic-bezier(0.0,0.0,0.2,1) forwards',
        'slide-up':   'slide-up 220ms cubic-bezier(0.0,0.0,0.2,1) forwards',
        'slide-left': 'slide-in-left 180ms cubic-bezier(0.0,0.0,0.2,1) forwards',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1',   transform: 'scale(1)' },
          '50%':      { opacity: '0.35', transform: 'scale(0.82)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-left': {
          from: { opacity: '0', transform: 'translateX(-6px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
}

export default config
