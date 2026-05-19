/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#58a6ff',
          dark: '#388bfd',
          light: '#79c0ff',
        },
        secondary: {
          DEFAULT: '#ffd700',
          dark: '#e6c200',
          light: '#ffed4e',
          hover: '#ffed4a',
        },
        summit: {
          DEFAULT: '#5b8db8',
          light: '#7aaed4',
          dark: '#3d6b8f',
        },
        accent: {
          green: '#2a9c4a',
          red: 'oklch(48% 0.190 22)',
        },
        bg: {
          dark: '#0d1117',
          base: '#0d1117',
          surface: '#161b22',
          elevated: '#21262d',
          raised: '#21262d',
        },
        text: {
          DEFAULT: '#f0f6fc',
          primary: '#f0f6fc',
          muted: '#8b949e',
        },
        border: {
          DEFAULT: '#30363d',
        },
      },
      fontFamily: {
        display: ['Almendra', 'Georgia', 'Times New Roman', 'serif'],
        sans: ['Figtree', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['Fira Code', 'ui-monospace', 'Courier New', 'monospace'],
      },
      spacing: {
        xs: '0.25rem',
        sm: '0.5rem',
        md: '1rem',
        lg: '1.5rem',
        xl: '2.5rem',
        '2xl': '4rem',
      },
      borderRadius: {
        soft: '8px',
      },
      boxShadow: {
        harsh: '0 8px 24px rgba(0, 0, 0, 0.25)',
      },
      transitionDuration: {
        fast: '150ms',
        normal: '300ms',
      },
      screens: {
        xs: '480px',
        sm: '640px',
        md: '768px',
        lg: '1024px',
        xl: '1280px',
        '2xl': '1536px',
      },
      maxWidth: {
        content: '1400px',
      },
    },
  },
  plugins: [],
}
