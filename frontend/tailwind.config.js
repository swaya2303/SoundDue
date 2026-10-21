/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        surface: {
          DEFAULT: '#ffffff',
          subtle: '#f8fafc',
          muted: '#f1f5f9',
          inset: '#e2e8f0',
        },
        status: {
          success: {
            bg: '#ecfdf5',
            border: '#a7f3d0',
            text: '#065f46',
            solid: '#059669',
          },
          warning: {
            bg: '#fffbeb',
            border: '#fde68a',
            text: '#92400e',
            solid: '#d97706',
          },
          error: {
            bg: '#fef2f2',
            border: '#fecdd3',
            text: '#9f1239',
            solid: '#e11d48',
          },
          info: {
            bg: '#f0f9ff',
            border: '#bae6fd',
            text: '#0369a1',
            solid: '#0284c7',
          },
          neutral: {
            bg: '#f8fafc',
            border: '#cbd5e1',
            text: '#334155',
            solid: '#64748b',
          },
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          '"Liberation Mono"',
          '"Courier New"',
          'monospace',
        ],
      },
      boxShadow: {
        subtle: '0 1px 2px 0 rgba(15, 23, 42, 0.05)',
        card: '0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 1px 2px -1px rgba(15, 23, 42, 0.04)',
        elevated: '0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.04)',
        popover: '0 10px 15px -3px rgba(15, 23, 42, 0.1), 0 4px 6px -4px rgba(15, 23, 42, 0.05)',
      },
    },
  },
  plugins: [],
}
