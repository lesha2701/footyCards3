/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        rarity: {
          common: "#94a3b8",
          rare: "#3b82f6",
          epic: "#a855f7",
          legendary: "#f59e0b",
        },
        bg: {
          base: "#07090a",
          surface: "#10140f",
          raised: "#161c15",
        },
        accent: {
          DEFAULT: "#3ed17e",
          cyan: "#22d3c4",
          green: "#3ed17e",
          lime: "#c6e63a",
          soft: "#8fe3b8",
        },
        ink: {
          chalk: "#f3f6f2",
          mist: "#8a968e",
          "mist-dim": "#5b655e",
        },
      },
      fontFamily: {
        display: ["'Benzin'", "system-ui", "sans-serif"],
        body: ["'Manrope'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        floodlight: "linear-gradient(90deg, #22d3c4 0%, #3ed17e 55%, #c6e63a 100%)",
      },
      boxShadow: {
        glow: "0 0 24px rgba(62, 209, 126, 0.35)",
        "glow-legendary": "0 0 32px rgba(245, 158, 11, 0.55)",
        "glow-epic": "0 0 32px rgba(168, 85, 247, 0.5)",
        "glow-rare": "0 0 24px rgba(59, 130, 246, 0.45)",
      },
      animation: {
        shimmer: "shimmer 2.2s linear infinite",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-500px 0" },
          "100%": { backgroundPosition: "500px 0" },
        },
      },
    },
  },
  plugins: [],
};
