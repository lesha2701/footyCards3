import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchCurrentBingo } from "@/api/bingo";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchPacks } from "@/api/packs";
import { fetchMyProfile } from "@/api/profile";
import { fetchTasks } from "@/api/tasks";
import { fetchWheelStatus } from "@/api/wheel";
import { Skeleton } from "@/components/common/Skeleton";
import HomeHero from "@/components/home/HomeHero";
import TodayCard from "@/components/home/TodayCard";
import { sortPacksByPrice } from "@/lib/packs";
import {
  IconChat,
  IconChevronRight,
  IconCoin,
  IconHandshake,
  IconUsers,
  type IconProps,
} from "@/components/icons";
import type { BingoCurrent } from "@/types";
import { staticUrl } from "@/lib/api";
import { haptic, openTelegramLink } from "@/lib/telegram";

const CHAT_INVITE_LINK = "https://t.me/+42EZisiOi8w1ZmMy";

function chunkPairs<T>(items: T[]): T[][] {
  const pairs: T[][] = [];
  for (let i = 0; i < items.length; i += 2) pairs.push(items.slice(i, i + 2));
  return pairs;
}

export default function HomePage() {
  const navigate = useNavigate();

  const { data: packs, isLoading: packsLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const coinPacks = packs?.filter((p) => p.stars_price == null);
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: taskList } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const { data: wheelStatus } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: bingo } = useQuery({ queryKey: ["bingo-current"], queryFn: fetchCurrentBingo });

  const claimableTaskCount = [...(taskList?.regular ?? []), ...(taskList?.premium ?? [])].filter(
    (t) => t.is_completed && !t.is_claimed
  ).length;

  // The league row in HomeHero is the entry point to /league — it also
  // renders below the lowest tier so a new player can still reach it.

  return (
    <div className="flex flex-col gap-6">
      <HomeHero
        profile={profile}
        league={leagueStatus}
        leaguesEnabled={flags?.leagues_enabled !== false}
        claimableTasks={claimableTaskCount}
      />

      <TodayCard wheel={flags?.wheel_enabled !== false ? wheelStatus : null} />

      <ChatInviteCard />

      {bingo?.is_enabled && <BingoBanner bingo={bingo} onClick={() => navigate("/bingo")} />}

      <div className="flex flex-col gap-3">
        {profile?.referral_reward_pending && (
          <NoticeCard
            Icon={IconHandshake}
            title="Тебя пригласил друг!"
            subtitle={`Открой любой пак (можно бесплатный) и получи ${profile.referral_referred_reward} монет`}
            onClick={() => navigate("/packs")}
          />
        )}

      </div>

      {(packsLoading || !!coinPacks?.length) && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-display text-base font-bold text-ink-chalk">Доступные паки</h2>
            <button onClick={() => navigate("/packs")} className="font-mono text-xs text-accent-lime">Все паки →</button>
          </div>
          {packsLoading ? (
            <div className="grid grid-cols-2 gap-3">
              <Skeleton className="h-28 rounded-2xl" />
              <Skeleton className="h-28 rounded-2xl" />
            </div>
          ) : (
            <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-1">
              {chunkPairs(sortPacksByPrice(coinPacks ?? [])).map((pair, i) => (
                <div key={i} className="grid w-full shrink-0 snap-start grid-cols-2 gap-3">
                  {pair.map((pack) => (
                    <button
                      key={pack.id}
                      onClick={() => navigate("/packs")}
                      className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface py-4 active:scale-95"
                    >
                      <img
                        src={staticUrl(pack.image_path ?? undefined)}
                        alt={pack.name}
                        className="h-16 w-16 rounded-2xl object-cover"
                      />
                      <p className="truncate px-1 text-xs font-semibold text-ink-chalk">{pack.name}</p>
                      <p className="flex items-center gap-1 font-mono text-[11px] text-accent-lime">
                        <IconCoin size={12} />
                        {pack.price}
                      </p>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {profile && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <h2 className="mb-4 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-mist">Твоя статистика</h2>
          <div className="grid grid-cols-2 gap-y-4">
            <Stat label="Уникальных карточек" value={profile.unique_cards} />
            <Stat label="Всего карточек" value={profile.total_cards} />
            <Stat label="Паков открыто" value={profile.packs_opened} />
            <Stat label="Место в рейтинге" value={`#${profile.arena_rank}`} accent />
          </div>
        </section>
      )}
    </div>
  );
}

function ChatInviteCard() {
  return (
    <button
      onClick={() => {
        haptic("light");
        openTelegramLink(CHAT_INVITE_LINK);
      }}
      className="relative flex items-center gap-4 overflow-hidden rounded-3xl bg-gradient-to-br from-sky-500/25 via-cyan-500/10 to-bg-surface p-5 text-left active:scale-[0.98]"
    >
      <div className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-sky-400/20 blur-2xl" />
      <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-sky-400/20 text-sky-300">
        <IconChat size={22} />
      </div>
      <div className="relative min-w-0 flex-1">
        <p className="font-display text-base font-bold text-ink-chalk">Чат VICTOR FC</p>
        <p className="mt-0.5 text-xs leading-snug text-ink-mist">
          Хвастайся дропом, договаривайся об обменах и открывай паки по слову «вкарта» — раз в 4 часа прямо в чате
        </p>
      </div>
      <IconChevronRight size={18} className="relative shrink-0 text-ink-mist-dim" />
    </button>
  );
}

// Time remaining is computed once, from `ends_at`, whenever this component
// mounts/re-renders (i.e. whenever the player navigates to Home) — no
// setInterval ticking it down live, by design.
function formatTimeRemaining(endsAt: string): string {
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return "меньше минуты";
  const days = Math.floor(ms / (24 * 60 * 60 * 1000));
  const hours = Math.floor((ms % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
  if (days > 0) return `${days} дн. ${hours} ч.`;
  const minutes = Math.floor((ms % (60 * 60 * 1000)) / (60 * 1000));
  if (hours > 0) return `${hours} ч. ${minutes} мин.`;
  return `${minutes} мин.`;
}

function BingoBanner({ bingo, onClick }: { bingo: BingoCurrent; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="relative flex items-center gap-4 overflow-hidden rounded-3xl bg-gradient-to-br from-fuchsia-500/25 via-purple-600/10 to-bg-surface p-5 text-left active:scale-[0.98]"
    >
      <div className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-fuchsia-400/20 blur-2xl" />
      <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-fuchsia-400/20 text-fuchsia-300">
        <IconUsers size={22} />
      </div>
      <div className="relative min-w-0 flex-1">
        <p className="font-display text-base font-bold text-ink-chalk">Бинго недели</p>
        {bingo.ends_at && (
          <p className="mt-0.5 text-xs leading-snug text-ink-mist">
            Осталось: {formatTimeRemaining(bingo.ends_at)}
          </p>
        )}
      </div>
      <IconChevronRight size={18} className="relative shrink-0 text-ink-mist-dim" />
    </button>
  );
}

function NoticeCard({
  Icon,
  title,
  subtitle,
  onClick,
  disabled,
  trailingIcon: TrailingIcon,
}: {
  Icon: (props: IconProps) => JSX.Element;
  title: string;
  subtitle: string;
  onClick: () => void;
  disabled?: boolean;
  trailingIcon?: (props: IconProps) => JSX.Element;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-3 rounded-2xl bg-bg-surface px-4 py-3 text-left transition active:scale-[0.98] disabled:opacity-50"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bg-raised text-accent-lime">
        <Icon size={18} />
      </div>
      <div className="flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        <p className="text-xs text-ink-mist">{subtitle}</p>
      </div>
      <span className="text-ink-mist-dim">
        {TrailingIcon ? <TrailingIcon size={16} /> : <IconChevronRight size={16} />}
      </span>
    </button>
  );
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div>
      <p
        className={`font-display text-2xl font-bold ${
          accent ? "bg-floodlight bg-clip-text text-transparent" : "text-ink-chalk"
        }`}
      >
        {value}
      </p>
      <p className="mt-0.5 text-[11px] text-ink-mist">{label}</p>
    </div>
  );
}
