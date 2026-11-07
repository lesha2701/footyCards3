import type { ComponentType, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { ClubWarArt } from "@/components/clubs/ClubWarArt";
import { ClubWarScoreboard } from "@/components/clubs/ClubWarScoreboard";
import { IconChat, IconChevronRight, IconClock, IconCoin, IconFlagCheckered, IconGift, IconShirt, IconTarget, IconTrophy, IconUsers } from "@/components/icons";
import { useOpenClubSheet } from "@/lib/clubSheet";
import { formatCountdown } from "@/lib/format";
import type { ClubTab } from "@/lib/clubTabs";
import type { Club, ClubWar, NextOpponent, TournamentCurrent } from "@/types";

const secondsUntil = (iso: string) => Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000));

function warLead(war: ClubWar): string {
  const mine = war.me?.score ?? 0;
  const theirs = war.opponent?.score ?? 0;
  if (mine === theirs) return "Равный бой";
  return mine > theirs ? `Ведём на ${mine - theirs}` : `Уступаем ${theirs - mine}`;
}

/** Live war score — the top of the club home while a war is on. */
function WarHero({ war }: { war: ClubWar }) {
  const openSheet = useOpenClubSheet();
  const { me, opponent } = war;
  if (!me || !opponent) return null;
  return (
    <button onClick={() => openSheet("war")} className="block w-full text-left active:scale-[0.99]">
      <ClubWarArt className="p-4">
        <div className="flex items-center justify-between text-caption">
          <span className="flex items-center gap-1.5 font-bold text-red-300">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" /> Идёт война
          </span>
          <span className="flex items-center gap-1 text-white/80"><IconClock size={12} /> {formatCountdown(secondsUntil(war.ends_at))}</span>
        </div>
        <div className="mt-3"><ClubWarScoreboard me={me} opponent={opponent} /></div>
        <p className="mt-2 text-center text-xs text-white/75">{warLead(war)} · играй, чтобы принести очки</p>
      </ClubWarArt>
    </button>
  );
}

/** The next tournament opponent, line by line. */
function OpponentHero({ opponent, canEditSquad }: { opponent: NextOpponent; canEditSquad: boolean }) {
  const navigate = useNavigate();
  const lines: [string, number][] = [
    ["Атака", opponent.attack], ["Полузащита", opponent.midfield], ["Защита", opponent.defence], ["Вратарь", opponent.goalkeeping],
  ];
  return (
    <section className="rounded-3xl bg-gradient-to-br from-accent-lime/15 via-bg-surface to-bg-surface p-4">
      <p className="text-caption font-semibold text-accent-lime">Турнир · тур {opponent.round_number}</p>
      <p className="mt-1 truncate font-display text-lg font-bold text-ink-chalk">{opponent.opponent_club_name}</p>
      <div className="mt-3 grid grid-cols-4 gap-2 text-center">
        {lines.map(([label, value]) => (
          <div key={label}>
            <p className="font-mono text-sm font-bold text-accent-cyan">{value}</p>
            <p className="text-micro text-ink-mist-dim">{label}</p>
          </div>
        ))}
      </div>
      {canEditSquad && (
        <button
          onClick={() => navigate("/clubs/squad")}
          className="mt-3 w-full rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95"
        >
          Изменить состав
        </button>
      )}
    </section>
  );
}

function NowRow({ icon: Icon, tint, onClick, disabled, children }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  tint: string;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  const body = (
    <>
      <Icon size={16} className={`shrink-0 ${tint}`} />
      <span className="min-w-0 flex-1 text-sm text-ink-chalk">{children}</span>
      {onClick && <IconChevronRight size={15} className="shrink-0 text-ink-mist-dim" />}
    </>
  );
  const row = "flex w-full items-center gap-2.5 rounded-2xl bg-bg-surface px-3 py-2.5 text-left";
  if (!onClick) return <div className={row}>{body}</div>;
  return <button onClick={onClick} disabled={disabled} className={`${row} active:scale-[0.99] disabled:opacity-40`}>{body}</button>;
}

/** «Сейчас в клубе»: what wants the player's attention right now, the most
 * urgent thing on top. Everything else lives in the sections below it. */
export function ClubNow({ club, war, tournament, nextOpponent, isManager, pendingRequests, onOpenRequests, onApply, applying }: {
  club: Club;
  war?: ClubWar;
  tournament?: TournamentCurrent;
  nextOpponent?: NextOpponent;
  isManager: boolean;
  pendingRequests: number;
  onOpenRequests?: () => void;
  onApply: () => void;
  applying: boolean;
}) {
  const navigate = useNavigate();
  const openSheet = useOpenClubSheet();
  const warLive = war?.state === "active" && !!war.me && !!war.opponent;
  const canApply = isManager && !!tournament?.can_apply;
  const rewards = club.rewards_unclaimed ?? 0;
  const unread = club.wall_unread ?? 0;
  const showOpponentHero = !warLive && !!nextOpponent && tournament?.status === "active";
  const quiet = !warLive && !showOpponentHero && !canApply && !rewards && !unread && !pendingRequests && tournament?.status !== "queued";

  return (
    <section className="flex flex-col gap-2" aria-label="Сейчас в клубе">
      <p className="font-display text-sm font-bold text-ink-chalk">Сейчас в клубе</p>
      {warLive && war && <WarHero war={war} />}
      {showOpponentHero && nextOpponent && <OpponentHero opponent={nextOpponent} canEditSquad={isManager} />}
      {rewards > 0 && (
        <NowRow icon={IconGift} tint="text-accent-lime" onClick={() => openSheet("shop")}>
          Наград ждут тебя: <b>{rewards}</b>
        </NowRow>
      )}
      {pendingRequests > 0 && (
        <NowRow icon={IconUsers} tint="text-accent-cyan" onClick={onOpenRequests}>
          Заявок в клуб: <b>{pendingRequests}</b>
        </NowRow>
      )}
      {warLive && nextOpponent && tournament?.status === "active" && (
        <NowRow icon={IconFlagCheckered} tint="text-accent-lime" onClick={() => navigate(`/clubs/tournament/${tournament.tournament_id}`)}>
          Тур {nextOpponent.round_number}: соперник {nextOpponent.opponent_club_name}
        </NowRow>
      )}
      {canApply && (
        <NowRow icon={IconTrophy} tint="text-accent-lime" onClick={onApply} disabled={applying}>
          Клуб готов к турниру — <b>подать заявку</b>
        </NowRow>
      )}
      {tournament?.status === "queued" && (
        <NowRow icon={IconFlagCheckered} tint="text-accent-lime">В очереди на турнир — место {tournament.queue_position}</NowRow>
      )}
      {unread > 0 && (
        <NowRow icon={IconChat} tint="text-accent-cyan" onClick={() => openSheet("wall")}>
          Новых сообщений на стене: <b>{unread}</b>
        </NowRow>
      )}
      {quiet && (
        <NowRow icon={IconTarget} tint="text-accent-lime" onClick={() => openSheet("quests")}>
          {war?.state === "upcoming"
            ? `Следующая война через ${formatCountdown(secondsUntil(war.starts_at))} — пока выполняйте задания`
            : "Срочных дел нет — загляни в задания недели"}
        </NowRow>
      )}
    </section>
  );
}

/** A compact tile of a club home section. `hint` carries live state when
 * there is any — a score, a place — not a description of the feature. */
export function ClubTile({ icon: Icon, tint = "text-accent-lime", title, hint, badge, onClick }: {
  icon: ComponentType<{ size?: number; className?: string }>;
  tint?: string;
  title: string;
  hint?: string;
  badge?: ReactNode;
  onClick: () => void;
}) {
  return (
    <button onClick={onClick} className="relative flex min-h-[68px] flex-col justify-between gap-1.5 rounded-2xl bg-bg-surface p-3 text-left active:scale-[0.98]">
      <Icon size={17} className={tint} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-ink-chalk">{title}</span>
        {hint && <span className="block truncate text-caption text-ink-mist">{hint}</span>}
      </span>
      {badge && (
        <span className="absolute right-2 top-2 rounded-full bg-accent-lime px-2 py-0.5 text-micro font-bold text-bg-base">{badge}</span>
      )}
    </button>
  );
}

/** Tabs on the bottom edge of the club card, Card Arena style: the active one
 * is part of the card, the others sit a shade darker and curve towards it.
 * A tap or a swipe switches them. */
function tabShape(index: number, active: number): string {
  if (index === active) return "text-accent-lime";
  const curve = index === active - 1 ? "rounded-tr-2xl" : index === active + 1 ? "rounded-tl-2xl" : "";
  return `bg-bg-base/55 text-ink-mist ${curve}`;
}

export function ClubTabs({ tab, onChange, badges }: {
  tab: ClubTab;
  onChange: (tab: ClubTab) => void;
  badges: Partial<Record<ClubTab, number>>;
}) {
  const items: [ClubTab, string, ComponentType<{ size?: number; className?: string }>][] = [
    ["now", "Сейчас", IconFlagCheckered], ["together", "Вместе", IconUsers], ["treasury", "Казна", IconCoin], ["club", "Клуб", IconShirt],
  ];
  return (
    <div role="tablist" aria-label="Разделы клуба" className="grid grid-cols-4">
      {items.map(([id, label, Icon], index) => (
        <button
          key={id}
          role="tab"
          aria-selected={tab === id}
          onClick={() => onChange(id)}
          className={`relative flex items-center justify-center gap-1 py-3 text-caption font-bold transition ${tabShape(index, items.findIndex(([key]) => key === tab))}`}
        >
          <Icon size={14} className="shrink-0" />
          {label}
          {!!badges[id] && (
            <span className="absolute right-1 top-1 min-w-[15px] rounded-full bg-accent-lime px-1 text-center text-[10px] font-bold leading-[15px] text-bg-base">{badges[id]}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function ClubSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <p className="font-mono text-caption uppercase tracking-wider text-ink-mist">{title}</p>
      <div className="grid grid-cols-2 gap-2 [&>*:last-child:nth-child(odd)]:col-span-2">{children}</div>
    </section>
  );
}
