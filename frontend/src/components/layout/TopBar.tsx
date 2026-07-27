import { useState } from "react";
import { useNavigate } from "react-router-dom";

import HelpModal from "@/components/common/HelpModal";
import { IconCoin, IconHelp } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";

export default function TopBar() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <header className="safe-top sticky top-0 z-30 border-b border-white/5 bg-bg-base/85 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-2.5">
        <button onClick={() => navigate("/")} className="flex items-center gap-2">
          <img src="/brand/victor-fc-crest.jpg" alt="" className="h-7 w-7 rounded-full ring-1 ring-white/10" />
          <span className="font-display text-sm font-bold tracking-wide text-ink-chalk">
            VICTOR <span className="text-accent-lime">FC</span>
          </span>
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHelpOpen(true)}
            aria-label="Помощь"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 text-ink-mist"
          >
            <IconHelp size={17} />
          </button>
          <div className="flex items-center gap-1.5 rounded-full border border-white/5 bg-bg-raised px-3 py-1.5">
            <IconCoin size={15} className="text-accent-lime" />
            <span className="font-mono text-[13px] font-semibold text-ink-chalk">{user?.balance ?? 0}</span>
          </div>
        </div>
      </div>
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </header>
  );
}
