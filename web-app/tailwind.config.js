/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // GitHub Dark Theme colors
        primary: {
          DEFAULT: '#58a6ff',
          hover: '#79b8ff',
        },
        secondary: {
          DEFAULT: '#ffd700',
          hover: '#ffed4a',
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
        // Legacy golden theme support
        golden: {
          DEFAULT: '#ffd700',
          dark: '#1a1a2e',
          surface: '#16213e',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
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
