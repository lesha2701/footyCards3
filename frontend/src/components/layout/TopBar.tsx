import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMyPlayer } from "@/api/myPlayer";
import HelpModal from "@/components/common/HelpModal";
import { IconCoin, IconHelp, IconProfile } from "@/components/icons";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { useAuthStore } from "@/store/authStore";
import { useMatchGuardStore } from "@/store/matchGuardStore";

export default function TopBar() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const guardActive = useMatchGuardStore((s) => s.active);
  const requestNavigate = useMatchGuardStore((s) => s.requestNavigate);
  const { data: myPlayer } = useQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer, enabled: !!user, staleTime: 60_000 });
  const mine = myPlayer?.player;
  // Something waits in «Мой игрок»: points, a free training, a level-up, income, club offers…
  const attention = !!myPlayer?.attention && Object.values(myPlayer.attention).some(Boolean);

  return (
    <header className="safe-top sticky top-0 z-30 border-b border-white/5 bg-bg-base/85 backdrop-blur">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-2.5">
        <button
          onClick={() => (guardActive ? requestNavigate("/") : navigate("/"))}
          className="flex items-center gap-2"
        >
          <img decoding="async" src="/brand/victor-fc-crest.jpg" alt="" className="h-7 w-7 rounded-full ring-1 ring-white/10" />
          <span className="font-display text-sm font-bold tracking-wide text-ink-chalk">
            VICTOR <span className="text-accent-lime">FC</span>
          </span>
        </button>
        <div className="flex items-center gap-2">
          {myPlayer?.enabled && (
            <button
              onClick={() => (guardActive ? requestNavigate("/my-player") : navigate("/my-player"))}
              aria-label="Мой игрок"
              className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-full bg-white/5 text-ink-mist ring-1 ring-white/10"
            >
              {mine ? (
                <PlayerAvatar appearance={mine.appearance} accessory={mine.accessory} backdrop={mine.background} className="h-full w-full" />
              ) : (
                <IconProfile size={17} />
              )}
              {attention && (
                <span
                  data-testid="my-player-dot"
                  className="absolute right-0.5 top-0.5 h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-bg-base"
                />
              )}
            </button>
          )}
          <button
            onClick={() => setHelpOpen(true)}
            aria-label="Помощь"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/5 text-ink-mist"
          >
            <IconHelp size={17} />
          </button>
          {/* The balance opens the shop's "Монеты" tab — the obvious place to tap
              when it runs low. */}
          <button
            onClick={() => (guardActive ? requestNavigate("/packs?tab=buy-coins") : navigate("/packs?tab=buy-coins"))}
            aria-label="Баланс — купить монеты"
            className="flex items-center gap-1.5 rounded-full border border-white/5 bg-bg-raised px-3 py-1.5 active:scale-95"
          >
            <IconCoin size={15} className="text-accent-lime" />
            <span className="font-mono text-[13px] font-semibold text-ink-chalk">{user?.balance ?? 0}</span>
          </button>
        </div>
      </div>
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </header>
  );
}
