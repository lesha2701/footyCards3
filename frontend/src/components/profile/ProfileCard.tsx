import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchProfileSocial } from "@/api/profile";
import { UserBadge } from "@/components/common/UserBadge";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { IconFire } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { backgroundArt, backgroundClass, frameClass } from "@/lib/cosmetics";
import { dayStreakLabel } from "@/lib/profileStats";
import type { Badge, EquippedCosmetics, Player, ProfileClub } from "@/types";

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
  rank, rankLabel, rankImage, onRank, avatarUrl, cosmetics, name, badge, subtitle,
  streak, clubPass, club, lastSeenAt, topCard, onTopCard, userId, isMe, stats, details, actions,
}: {
  rank: number;
  rankLabel: string;
  rankImage?: string | null;
  onRank?: () => void;
  avatarUrl: string | null;
  cosmetics?: EquippedCosmetics;
  name: string;
  badge: Badge | null;
  subtitle: string;
  streak?: number;
  clubPass?: boolean;
  club?: ProfileClub | null;
  lastSeenAt?: string | null;
  topCard?: Player | null;
  onTopCard?: () => void;
  userId: number;
  isMe: boolean;
  stats: [string, string][];
  details?: ReactNode;
  actions?: ReactNode;
}) {
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useState(false);
  const frame = frameClass(cosmetics?.frame);
  const background = backgroundClass(cosmetics?.background);
  const art = backgroundArt(cosmetics?.background);
  return (
    <section
      className={`relative isolate overflow-hidden rounded-3xl border border-amber-300/40 p-4 ${
        art ? "bg-black" : background ?? "bg-gradient-to-b from-[#3d2e10] via-[#1f1a0c] to-[#0f100c]"
      }`}
      data-testid="profile-card"
    >
      {art && (
        <>
          <img src={art} alt="" className="pointer-events-none absolute inset-0 -z-10 h-full w-full object-cover" data-testid="profile-bg-art" />
          <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-black/20 via-black/45 to-black/70" />
        </>
      )}
      <div className="flex items-start gap-3">
        <button onClick={onRank} disabled={!onRank} className="flex w-16 shrink-0 flex-col items-center pt-1 text-center active:scale-95">
          <span className="font-display text-3xl font-black leading-none text-amber-200">{rank > 0 ? `#${rank}` : "—"}</span>
          <span className="mt-1 line-clamp-2 text-[10px] font-bold uppercase leading-tight tracking-wide text-amber-100/70">{rankLabel}</span>
          {rankImage && <img src={staticUrl(rankImage) ?? undefined} className="mt-1 h-7 w-7 rounded-full object-cover" />}
        </button>
        <div className="flex min-w-0 flex-1 flex-col items-center">
          <span className={`rounded-full ${frame ? `p-[3px] ${frame}` : ""}`}>
            <img decoding="async" loading="lazy"
              src={avatarUrl ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt="avatar"
              className={`h-20 w-20 rounded-full object-cover ${frame ? "ring-2 ring-bg-base" : "ring-2 ring-amber-300"}`}
            />
          </span>
        </div>
        <TopCard card={topCard} onClick={onTopCard} />
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
        {!isMe && lastSeenAt && <LastSeen at={lastSeenAt} />}
        {club && (
          <button
            onClick={() => navigate(`/clubs/${club.id}/trophies`)}
            className="flex items-center gap-1 rounded-full bg-white/10 py-0.5 pl-1 pr-2.5 text-caption font-semibold text-ink-chalk active:scale-95"
            data-testid="profile-club"
          >
            <ClubLogo shape={club.logo_shape} color={club.logo_color} emblem={club.emblem} size={18} />
            {club.name}
          </button>
        )}
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

/** The best card, as a small FUT card on the right of the avatar. */
function TopCard({ card, onClick }: { card?: Player | null; onClick?: () => void }) {
  if (!card) return <div className="w-16 shrink-0" />;
  const rings: Record<string, string> = { diamond: "ring-cyan-300", legendary: "ring-amber-300", epic: "ring-fuchsia-400", rare: "ring-sky-400" };
  const ring = rings[card.rarity] ?? "ring-white/30";
  return (
    <button onClick={onClick} className="flex w-16 shrink-0 flex-col items-center pt-0.5 active:scale-95" data-testid="profile-top-card">
      <span className={`relative h-[74px] w-14 overflow-hidden rounded-lg bg-black/40 ring-2 ${ring}`}>
        <img
          decoding="async" loading="lazy"
          src={staticUrl(card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp") ?? undefined}
          alt={card.display_name}
          className="h-full w-full object-cover"
        />
        <span className="absolute left-0.5 top-0.5 rounded bg-black/70 px-1 font-mono text-[11px] font-black leading-tight text-amber-200">{card.rating}</span>
      </span>
      <span className="mt-1 w-full truncate text-center text-[9px] font-bold uppercase tracking-wide text-amber-100/70">топ-карта</span>
    </button>
  );
}

/** «в игре» / «был 3 ч назад» — rounded, never an exact time. */
function LastSeen({ at }: { at: string }) {
  const minutes = (Date.now() - new Date(at).getTime()) / 60000;
  const online = minutes < 10;
  let text = "в игре";
  if (!online) {
    if (minutes < 60) text = "был(а) недавно";
    else if (minutes < 60 * 24) text = `был(а) ${Math.floor(minutes / 60)} ч назад`;
    else if (minutes < 60 * 24 * 2) text = "был(а) вчера";
    else if (minutes < 60 * 24 * 30) text = `был(а) ${Math.floor(minutes / 1440)} дн. назад`;
    else text = "давно не заходил(а)";
  }
  return (
    <span className="flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-0.5 text-caption font-semibold text-ink-mist" data-testid="profile-last-seen">
      <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-accent-lime" : "bg-ink-mist-dim"}`} />
      {text}
    </span>
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
