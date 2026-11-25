import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchProfileSocial } from "@/api/profile";
import { UserBadge } from "@/components/common/UserBadge";
import { IconFire } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { backgroundClass, frameClass } from "@/lib/cosmetics";
import { dayStreakLabel } from "@/lib/profileStats";
import type { Badge, EquippedCosmetics } from "@/types";

/** One mode's W-D-L, for the card's «tap the numbers» details. */
export function ModeRecords({ rows }: { rows: [string, number, number, number][] }) {
  const played = rows.reduce((acc, [, w, d, l]) => acc + w + d + l, 0);
  const won = rows.reduce((acc, [, w]) => acc + w, 0);
  return (
    <div className="mt-3 rounded-2xl bg-black/25 p-2 text-center text-caption">
      <div className="grid grid-cols-3 gap-1.5">
        {rows.map(([mode, w, d, l]) => (
          <span key={mode} className="flex flex-col">
            <span className="font-mono font-bold text-ink-chalk">{w}-{d}-{l}</span>
            <span className="text-[10px] text-ink-mist">{mode} П-Н-П</span>
          </span>
        ))}
      </div>
      {played > 0 && (
        <p className="mt-1.5 text-[11px] text-amber-100/70">
          Побед: <b className="text-amber-100">{Math.round((won / played) * 100)}%</b> из {played} матчей
        </p>
      )}
    </div>
  );
}

/** A profile as a player card — the owner's and a visitor's view share it:
 * the place on the left, the avatar in its frame, name, chips, the numbers
 * as card stats (tap → `details`), and `actions` under them. */
export function ProfileCard({
  rank, rankLabel, rankImage, onRank, corner, avatarUrl, cosmetics, name, badge, subtitle,
  streak, clubPass, userId, isMe, stats, details, actions,
}: {
  rank: number;
  rankLabel: string;
  rankImage?: string | null;
  onRank?: () => void;
  corner?: ReactNode;
  avatarUrl: string | null;
  cosmetics?: EquippedCosmetics;
  name: string;
  badge: Badge | null;
  subtitle: string;
  streak?: number;
  clubPass?: boolean;
  userId: number;
  isMe: boolean;
  stats: [string, string][];
  details?: ReactNode;
  actions?: ReactNode;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const frame = frameClass(cosmetics?.frame);
  const background = backgroundClass(cosmetics?.background);
  return (
    <section
      className={`relative overflow-hidden rounded-3xl border border-amber-300/40 p-4 ${background ?? "bg-gradient-to-b from-[#3d2e10] via-[#1f1a0c] to-[#0f100c]"}`}
      data-testid="profile-card"
    >
      {corner && <div className="absolute right-3 top-3">{corner}</div>}
      <div className="flex items-start gap-3">
        <button onClick={onRank} disabled={!onRank} className="flex w-16 shrink-0 flex-col items-center pt-1 text-center active:scale-95">
          <span className="font-display text-3xl font-black leading-none text-amber-200">{rank > 0 ? `#${rank}` : "—"}</span>
          <span className="mt-1 line-clamp-2 text-[10px] font-bold uppercase leading-tight tracking-wide text-amber-100/70">{rankLabel}</span>
          {rankImage && <img src={staticUrl(rankImage) ?? undefined} className="mt-1 h-7 w-7 rounded-full object-cover" />}
        </button>
        <div className="flex min-w-0 flex-1 flex-col items-center pr-10">
          <span className={`rounded-full ${frame ? `p-[3px] ${frame}` : ""}`}>
            <img decoding="async" loading="lazy"
              src={avatarUrl ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt="avatar"
              className={`h-20 w-20 rounded-full object-cover ${frame ? "ring-2 ring-bg-base" : "ring-2 ring-amber-300"}`}
            />
          </span>
        </div>
      </div>
      <p className="mt-2 flex items-center justify-center gap-1.5 text-center font-display text-xl font-bold text-ink-chalk">
        {name}
        <UserBadge badge={badge} />
      </p>
      <p className="text-center text-xs text-amber-100/60">{subtitle}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-1.5">
        {clubPass && (
          <span className="rounded-full bg-emerald-400/15 px-2.5 py-0.5 text-caption font-semibold text-emerald-300">Клубный абонемент</span>
        )}
        {!!streak && streak > 0 && (
          <span className="flex items-center gap-1 rounded-full bg-orange-500/15 px-2.5 py-0.5 text-caption font-bold text-orange-300">
            <IconFire size={12} />
            {streak} {dayStreakLabel(streak)} подряд
          </span>
        )}
        {isMe && <RespectChip userId={userId} />}
      </div>
      {isMe && <TodayRespects userId={userId} />}
      <div className="my-3 h-px bg-gradient-to-r from-transparent via-amber-300/50 to-transparent" />
      <button
        onClick={() => details && setShowDetails((v) => !v)}
        className="grid w-full grid-cols-3 text-center active:opacity-80"
        data-testid="profile-stats"
      >
        {stats.map(([value, label]) => (
          <span key={label} className="flex flex-col">
            <span className="font-mono text-2xl font-bold leading-tight text-amber-100">{value}</span>
            <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-amber-100/50">{label}</span>
          </span>
        ))}
      </button>
      {showDetails && details}
      {actions && <div className="mt-3 flex flex-col gap-2">{actions}</div>}
    </section>
  );
}

function RespectChip({ userId }: { userId: number }) {
  const { data } = useQuery({ queryKey: ["profile-social", userId], queryFn: () => fetchProfileSocial(userId) });
  if (!data) return null;
  return (
    <span className="rounded-full bg-amber-300/15 px-2.5 py-0.5 text-caption font-bold text-amber-200" data-testid="respect-count">
      👍 {data.respects.toLocaleString("ru-RU")}
    </span>
  );
}

/** The owner's «сегодня заходили»: who gave a respect today. */
function TodayRespects({ userId }: { userId: number }) {
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["profile-social", userId], queryFn: () => fetchProfileSocial(userId) });
  const givers = data?.today_givers ?? [];
  if (!givers.length) return null;
  return (
    <div className="mt-2 flex items-center justify-center gap-2" data-testid="today-respects">
      <span className="flex -space-x-2">
        {givers.slice(0, 5).map((g) => (
          <button key={g.id} onClick={() => navigate(`/users/${g.id}`)} title={g.first_name ?? undefined}>
            <img
              src={g.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp") ?? undefined}
              alt=""
              className="h-6 w-6 rounded-full border-2 border-[#1f1a0c] object-cover"
            />
          </button>
        ))}
      </span>
      <span className="text-caption text-amber-100/70">
        {givers.length === 1 ? `${givers[0].first_name ?? "Игрок"} поставил(а) респект сегодня` : `сегодня респектов: +${givers.length}${givers.length >= 8 ? "…" : ""}`}
      </span>
    </div>
  );
}
