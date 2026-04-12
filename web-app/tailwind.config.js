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
          DEFAULT: 'oklch(82% 0.165 82)',   // Amber gold
          dark: 'oklch(73% 0.165 82)',
          light: 'oklch(92% 0.100 85)',
          hover: 'oklch(92% 0.100 85)',
        },
        summit: {
          DEFAULT: 'oklch(60% 0.085 222)',  // Summit blue — alpine/mountain brand color
          light: 'oklch(72% 0.070 222)',
          dark: 'oklch(46% 0.080 222)',
        },
        accent: {
          green: '#2a9c4a',
          red: 'oklch(48% 0.190 22)',       // Deep crimson
        },
        bg: {
          dark: 'oklch(13% 0.012 65)',      // Lightened warm near-black
          surface: 'oklch(19% 0.016 65)',   // Lightened warm surface
          elevated: 'oklch(26% 0.024 65)',  // Lightened warm elevated
        },
        text: {
          DEFAULT: 'oklch(96% 0.008 80)',   // Warm off-white
          muted: 'oklch(62% 0.007 80)',     // Warm muted
        },
        border: {
          DEFAULT: 'oklch(96% 0.005 80 / 0.15)',
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
