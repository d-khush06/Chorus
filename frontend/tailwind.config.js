/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  corePlugins: {
    // Disabled globally per requirements to prevent breaking /login, /evidence
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        sidebar: 'var(--sidebar)',
        topbar: 'var(--topbar)',
        card: 'var(--card)',
        surface: 'var(--surface)',
        border: 'var(--border)',
        text: 'var(--text)',
        'text-secondary': 'var(--text-secondary)',
        accent: 'var(--accent)',
        'stage-bg': 'var(--stage-bg)',
        ok: 'var(--ok)',
        warning: 'var(--warning)',
        danger: 'var(--danger)',
        info: 'var(--info)',
        primary: 'var(--text)',
        secondary: 'var(--text-secondary)',
        cyber: {
          bg: 'var(--bg)',
          surface: 'var(--surface)',
          border: 'var(--border)',
          text: 'var(--text)',
          'text-secondary': 'var(--text-secondary)',
          accent: 'var(--accent)',
          ok: 'var(--ok)',
          warning: 'var(--warning)',
          danger: 'var(--danger)',
          info: 'var(--info)',
          'stage-bg': 'var(--stage-bg)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        serif: ['Source Serif 4', 'Georgia', 'serif'],
        heading: ['Source Serif 4', 'Georgia', 'serif'],
      },
      borderRadius: {
        card: 'var(--radius-card)',
        control: 'var(--radius-control)',
        small: 'var(--radius-small)',
      },
      spacing: {
        '1': 'var(--space-1)',
        '2': 'var(--space-2)',
        '3': 'var(--space-3)',
        '4': 'var(--space-4)',
        '5': 'var(--space-5)',
        '6': 'var(--space-6)',
        '8': 'var(--space-8)',
        '10': 'var(--space-10)',
        '12': 'var(--space-12)',
        '16': 'var(--space-16)',
      },
      transitionDuration: {
        fast: '150ms',
        mid: '200ms',
      }
    }
  },
  plugins: [],
};
