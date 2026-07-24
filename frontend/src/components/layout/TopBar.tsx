import { useState } from "react";
import { useNavigate } from "react-router-dom";

import HelpModal from "@/components/common/HelpModal";
import { useAuthStore } from "@/store/authStore";

export default function TopBar() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <header className="safe-top sticky top-0 z-30 border-b border-white/5 bg-bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-3">
        <button onClick={() => navigate("/")} className="font-display text-lg font-bold tracking-wide text-slate-100">
          ⚽ FootyCards
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHelpOpen(true)}
            aria-label="Помощь"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 text-base"
          >
            ❓
          </button>
          <div className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5">
            <span className="text-base leading-none">🪙</span>
            <span className="font-display text-sm font-bold text-amber-300">{user?.balance ?? 0}</span>
          </div>
        </div>
      </div>
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </header>
  );
}
