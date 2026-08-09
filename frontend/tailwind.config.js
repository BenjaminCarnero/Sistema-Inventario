/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Los colores de marca salen de variables CSS para que cada comercio
        // pueda cambiarlos desde Configuración sin recompilar. Las variables
        // guardan el triplete RGB ("130 81 238") y las define ConfigProvider.
        brand: {
          DEFAULT: 'rgb(var(--color-brand) / <alpha-value>)',
          hover: 'rgb(var(--color-brand-hover) / <alpha-value>)',
          light: 'rgb(var(--color-brand-light) / <alpha-value>)',
          subtle: 'rgb(var(--color-brand) / 0.15)',
        },
        accent: {
          DEFAULT: 'rgb(var(--color-accent) / <alpha-value>)',
          hover: 'rgb(var(--color-accent-hover) / <alpha-value>)',
        },
        neutral: {
          bg1: '#0F0F13', // Deep dark background
          bg2: '#18181C',
          bg3: '#222227',
          bg4: '#2D2D35',
        },
        text: {
          primary: '#FFFFFF',
          secondary: '#A1A1AA',
          muted: '#71717A',
        },
        status: {
          success: '#10B981',
          error: '#EF4444',
          warning: '#F59E0B',
        },
        border: {
          subtle: 'rgba(255, 255, 255, 0.05)',
          DEFAULT: 'rgba(255, 255, 255, 0.1)',
        },
      },
      fontFamily: {
        sans: ['Outfit', 'sans-serif'],
      },
      boxShadow: {
        'glow': '0 0 20px rgb(var(--color-brand) / 0.3)',
        'glow-accent': '0 0 20px rgb(var(--color-accent) / 0.3)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
};
