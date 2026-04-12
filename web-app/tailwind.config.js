/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // GitHub Dark palette (matches style.css)
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
          green: '#238636',
          red: '#f85149',
        },
        bg: {
          dark: '#0d1117',
          surface: '#161b22',
          elevated: '#21262d',
        },
        text: {
          DEFAULT: '#f0f6fc',
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
