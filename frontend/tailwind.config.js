/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'subtle': 'var(--shadow-sm)',
        'soft': 'var(--shadow-md)',
        'lift': 'var(--shadow-lg)',
      },
      borderRadius: {
        'panel': 'var(--radius-md)',
        'pill': '9999px',
      },
    },
  },
  plugins: [],
}
