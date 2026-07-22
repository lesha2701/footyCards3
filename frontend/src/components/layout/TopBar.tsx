import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";

export default function TopBar() {
  const user = useAuthStore((s) => s.user);
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const navigate = useNavigate();

  return (
    <header className="safe-top sticky top-0 z-30 border-b border-white/5 bg-bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-3">
        <button onClick={() => navigate("/")} className="font-display text-lg font-bold tracking-wide text-slate-100">
          ⚽ Football Cards
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            aria-label="Переключить тему"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 text-base"
          >
            {theme === "dark" ? "🌙" : "☀️"}
          </button>
          <div className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5">
            <span className="text-base leading-none">🪙</span>
            <span className="font-display text-sm font-bold text-amber-300">{user?.balance ?? 0}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
