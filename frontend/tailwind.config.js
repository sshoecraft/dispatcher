import daisyui from 'daisyui'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        poppins: ['Poppins', 'sans-serif'],
        roboto: ['Roboto', 'sans-serif'],
      },
    },
  },
  darkMode: ['selector', '[data-theme="dark"]'],
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        light: {
          primary: '#005a8c',
          secondary: '#64748b',
          accent: '#10b981',
          neutral: '#374151',
          'base-100': '#ffffff',
          'base-200': '#f8fafc',
          'base-300': '#e2e8f0',
          info: '#0ea5e9',
          success: '#22c55e',
          warning: '#f59e0b',
          error: '#ef4444',
        },
        dark: {
          primary: '#60a5fa',
          secondary: '#94a3b8',
          accent: '#34d399',
          neutral: '#d1d5db',
          'base-100': '#1f2937',
          'base-200': '#111827',
          'base-300': '#0f172a',
          info: '#38bdf8',
          success: '#4ade80',
          warning: '#fbbf24',
          error: '#f87171',
        },
      },
    ],
    darkTheme: 'dark',
    base: true,
    styled: true,
    utils: true,
    prefix: '',
    logs: false,
    themeRoot: ':root',
  },
}
