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
          base: "#0b0f1a",
          surface: "#121826",
          raised: "#1a2235",
        },
        accent: {
          DEFAULT: "#22d3ee",
          soft: "#67e8f9",
        },
      },
      fontFamily: {
        display: ["'Rajdhani'", "system-ui", "sans-serif"],
        body: ["'Inter'", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(34, 211, 238, 0.35)",
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
