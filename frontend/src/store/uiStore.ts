import { create } from "zustand";

import { getTelegramWebApp, isInsideTelegram } from "@/lib/telegram";

export type Theme = "dark" | "light";
/** "auto" follows Telegram's color scheme (or the OS outside Telegram). */
export type ThemePreference = Theme | "auto";

// Header/background colors handed to Telegram so its native chrome matches
// the page (same values as --c-bg-base / --c-bg-surface in index.css).
const CHROME: Record<Theme, { header: string; background: string }> = {
  dark: { header: "#10140f", background: "#07090a" },
  light: { header: "#ffffff", background: "#eef2ec" },
};

function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem("theme");
    if (stored === "light" || stored === "dark" || stored === "auto") return stored;
  } catch {
    /* storage unavailable */
  }
  return "auto";
}

function systemTheme(): Theme {
  if (isInsideTelegram()) return getTelegramWebApp()?.colorScheme === "light" ? "light" : "dark";
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function resolve(preference: ThemePreference): Theme {
  return preference === "auto" ? systemTheme() : preference;
}

function apply(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const webApp = getTelegramWebApp();
  webApp?.setHeaderColor?.(CHROME[theme].header);
  webApp?.setBackgroundColor?.(CHROME[theme].background);
}

interface UiState {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
  /** Re-resolves "auto" (call when Telegram reports a theme change). */
  syncTheme: () => void;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: typeof window === "undefined" ? "dark" : resolve(readPreference()),
  preference: typeof window === "undefined" ? "auto" : readPreference(),
  setPreference: (preference) => {
    try {
      window.localStorage.setItem("theme", preference);
    } catch {
      /* storage unavailable */
    }
    const theme = resolve(preference);
    apply(theme);
    set({ preference, theme });
  },
  syncTheme: () => {
    const theme = resolve(get().preference);
    apply(theme);
    set({ theme });
  },
  toggleTheme: () => get().setPreference(get().theme === "dark" ? "light" : "dark"),
  setTheme: (theme) => get().setPreference(theme),
}));
