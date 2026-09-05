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
          // Icy turquoise, not blue — rare already owns saturated blue as
          // its identity, so diamond leans lighter/cooler to read as
          // "ice/prism" rather than "another blue card". The rainbow itself
          // lives in the animated diamond-holo gradient/glow below.
          diamond: "#67e8f9",
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
        // Blended violet + cyan halo, evoking light splitting into color —
        // deliberately not a single flat blue like glow-rare. Static (no
        // pulsing) — only the border gradient itself animates.
        "glow-diamond": "0 0 20px rgba(232, 121, 249, 0.45), 0 0 36px rgba(103, 232, 249, 0.4)",
        "glow-epic": "0 0 32px rgba(168, 85, 247, 0.5)",
        "glow-rare": "0 0 24px rgba(59, 130, 246, 0.45)",
      },
      animation: {
        shimmer: "shimmer 2.2s linear infinite",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "goal-flash": "goalFlash 1.1s ease-out forwards",
        "legendary-pulse": "legendaryPulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "diamond-shimmer": "diamondShimmer 2.2s ease-in-out infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-500px 0" },
          "100%": { backgroundPosition: "500px 0" },
        },
        goalFlash: {
          "0%": { boxShadow: "0 0 0 0 rgba(62, 209, 126, 0.9)", opacity: "1" },
          "60%": { boxShadow: "0 0 24px 6px rgba(62, 209, 126, 0.15)", opacity: "1" },
          "100%": { boxShadow: "0 0 0 0 rgba(62, 209, 126, 0)", opacity: "0" },
        },
        // Unlike Tailwind's built-in `pulse` (which dips to 50% opacity),
        // this never lets a legendary card fade past 70% — it should still
        // read as "here", just gently breathing, not flicker toward invisible.
        legendaryPulse: {
          "50%": { opacity: "0.7" },
        },
        // Only the border's background-position travels — no opacity swing.
        // An animated opacity dip read as flicker/eye strain, so the diamond
        // border stays fully opaque throughout; the shimmer is carried
        // entirely by the gradient sweeping under the oversized
        // bg-[length:...] from RARITY_GLOW.diamond. Every call site's
        // gradient is `bg-gradient-to-b` (to bottom) — that only varies
        // along Y, so animating X (what this used to do) moved the position
        // without ever changing a visible pixel. Y is the axis that matters.
        diamondShimmer: {
          "0%, 100%": { backgroundPosition: "50% 0%" },
          "50%": { backgroundPosition: "50% 100%" },
        },
      },
    },
  },
  plugins: [],
};
