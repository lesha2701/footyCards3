import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchPublicLifestyle } from "@/api/lifestyle";
import { fetchMyPlayer, fetchPublicMyPlayer } from "@/api/myPlayer";
import { IconChevronRight } from "@/components/icons";
import { TIER_TEXT } from "@/lib/myPlayer";

import MyPlayerCard from "./MyPlayerCard";
import PlayerAvatar from "./PlayerAvatar";
import TrophyShowcase from "./TrophyShowcase";

/** Profile row leading to /my-player: the avatar + level, or a "create" call. */
export function MyPlayerEntry() {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer });
  if (!data?.enabled) return null;
  const player = data.player;
  return (
    <button
      onClick={() => navigate("/my-player")}
      className="flex items-center justify-between gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-bg-raised">
          {player && (
            <PlayerAvatar appearance={player.appearance} accessory={player.accessory} backdrop={player.background} className="h-full w-full" />
          )}
          {!player && <span className="flex h-full items-center justify-center text-2xl">⚽</span>}
        </span>
        <span className="min-w-0">
          <span className="block font-display text-base font-bold text-ink-chalk">Мой игрок</span>
          <span className="block truncate text-xs text-ink-mist">
            {player ? (
              <>
                {player.name} · {player.rating} · <span className={TIER_TEXT[player.tier]}>{player.tier_label}</span> · ур. {data.level}
              </>
            ) : (
              "Создай своего футболиста и прокачивай его"
            )}
          </span>
        </span>
      </span>
      <span className="flex items-center gap-2">
        {player && data.points_available > 0 && (
          <span className="rounded-full bg-accent-lime px-2 py-0.5 font-mono text-micro font-bold text-bg-base">
            +{data.points_available}
          </span>
        )}
        <IconChevronRight size={16} className="text-ink-mist-dim" />
      </span>
    </button>
  );
}

/** Someone else's «Мой игрок» on their public profile (nothing if none). */
export function PublicMyPlayer({ userId }: { userId: number }) {
  const { data } = useQuery({ queryKey: ["my-player", "public", userId], queryFn: () => fetchPublicMyPlayer(userId) });
  const { data: property } = useQuery({
    queryKey: ["lifestyle", "public", userId], queryFn: () => fetchPublicLifestyle(userId), enabled: !!data?.player,
  });
  if (!data?.player) return null;
  return (
    <section className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-4">
      <h2 className="self-start font-display text-base font-bold text-ink-chalk">Мой игрок</h2>
      <div className="w-44">
        <MyPlayerCard player={data.player} level={data.level} />
      </div>
      {data.trophies.length > 0 && (
        <div className="w-full">
          <TrophyShowcase trophies={data.trophies} />
        </div>
      )}
      {!!property?.items.length && (
        <div className="w-full rounded-xl bg-bg-raised p-3">
          <p className="text-xs text-ink-mist">
            Имущество · <b className="text-amber-300">{property.prestige} престижа</b>
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {property.items.map((i) => (
              <span key={i.id} title={i.name} className="rounded-lg bg-bg-surface px-2 py-1 text-xs text-ink-chalk">
                {i.emoji} {i.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
