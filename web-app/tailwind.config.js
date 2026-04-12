/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Sorcerers Summit — warm dark arcane theme
        primary: {
          DEFAULT: '#58a6ff',
          hover: '#79b8ff',
        },
        secondary: {
          DEFAULT: '#e8a800',  // Rich amber gold (warmer than flat #ffd700)
          hover: '#f5c000',
        },
        accent: {
          green: '#2a9c4a',
          red: '#a82828',     // Deep crimson (replaces bright #f85149)
        },
        bg: {
          dark: '#0f0d0a',    // Warm near-black (was cold #0d1117)
          surface: '#171411', // Warm surface (was cold #161b22)
          elevated: '#201d17', // Warm elevated (was cold #21262d)
        },
        text: {
          DEFAULT: '#f5f1ea',  // Warm off-white (was cool #f0f6fc)
          muted: '#908c86',    // Warm muted (was cool #8b949e)
        },
        border: {
          DEFAULT: '#2c2924',  // Warm border (was cool #30363d)
        },
        // Legacy golden theme support
        golden: {
          DEFAULT: '#e8a800',
          dark: '#100f0c',
          surface: '#171411',
        },
      },
      fontFamily: {
        display: ['Almendra', 'Georgia', 'Times New Roman', 'serif'],
        sans: ['Figtree', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['Fira Code', 'ui-monospace', 'Courier New', 'monospace'],
      },
      spacing: {
        // Match existing CSS variables
        xs: '0.25rem',    // 4px
        sm: '0.5rem',     // 8px
        md: '1rem',       // 16px
        lg: '1.5rem',     // 24px
        xl: '2.5rem',     // 40px
        '2xl': '4rem',    // 64px
      },
      borderRadius: {
        soft: '8px',      // Match --radius-soft
      },
      boxShadow: {
        harsh: '0 8px 24px rgba(0, 0, 0, 0.25)',
      },
      transitionDuration: {
        fast: '150ms',
        normal: '300ms',
      },
      screens: {
        // Enhanced breakpoints for better responsive design
        'xs': '480px',    // Extra small phones
        'sm': '640px',    // Small tablets
        'md': '768px',    // Tablets (existing breakpoint)
        'lg': '1024px',   // Laptops
        'xl': '1280px',   // Desktops
        '2xl': '1536px',  // Large desktops
      },
      maxWidth: {
        content: '1400px', // Match main max-width
      },
    },
  },
  plugins: [],
}
