import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { claimFreePack, fetchFreePackStatus } from "@/api/freePack";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchPacks } from "@/api/packs";
import { fetchMyProfile } from "@/api/profile";
import { fetchTasks } from "@/api/tasks";
import { fetchWheelStatus } from "@/api/wheel";
import { Skeleton } from "@/components/common/Skeleton";
import { sortPacksByPrice } from "@/lib/packs";
import {
  IconChat,
  IconChevronRight,
  IconClock,
  IconCoin,
  IconCollection,
  IconGift,
  IconHandshake,
  IconPlay,
  IconTarget,
  IconUpgrade,
  type IconProps,
} from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { haptic, hapticNotify, openTelegramLink } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const CHAT_INVITE_LINK = "https://t.me/+42EZisiOi8w1ZmMy";

function chunkPairs<T>(items: T[]): T[][] {
  const pairs: T[][] = [];
  for (let i = 0; i < items.length; i += 2) pairs.push(items.slice(i, i + 2));
  return pairs;
}

export default function HomePage() {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: calendar } = useQuery({ queryKey: ["daily-reward-calendar"], queryFn: fetchDailyRewardCalendar });
  const { data: packs, isLoading: packsLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const coinPacks = packs?.filter((p) => p.stars_price == null);
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: taskList } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const { data: freePackStatus } = useQuery({
    queryKey: ["free-pack-status"],
    queryFn: fetchFreePackStatus,
    refetchInterval: 30000,
  });
  const { data: wheelStatus } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });

  const claimFreePackMutation = useMutation({
    mutationFn: claimFreePack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["free-pack-status"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data } });
    },
  });

  const claimableTaskCount = [...(taskList?.regular ?? []), ...(taskList?.premium ?? [])].filter(
    (t) => t.is_completed && !t.is_claimed
  ).length;

  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-3xl bg-bg-surface p-5">
        <ChalkTexture />
        <div className="relative flex items-center gap-2">
          <img src="/brand/victor-fc-crest.jpg" alt="" className="h-7 w-7 rounded-full ring-1 ring-white/10" />
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-mist">
            С возвращением, {user?.first_name ?? user?.username ?? "игрок"}
          </p>
        </div>
        <div className="relative mt-4 grid grid-cols-4 gap-2">
          <QuickAction Icon={IconPlay} label="Играть" onClick={() => navigate("/play")} />
          <QuickAction Icon={IconCollection} label="Карточки" onClick={() => navigate("/collection")} />
          <QuickAction Icon={IconUpgrade} label="Апгрейд" onClick={() => navigate("/upgrade")} />
          <QuickAction Icon={IconTarget} label="Задания" onClick={() => navigate("/tasks")} badge={claimableTaskCount || undefined} />
        </div>
      </section>

      {leagueStatus?.current_league && (
        <button
          onClick={() => navigate("/league")}
          className="flex items-center gap-3 rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-bg-raised text-2xl">
            {leagueStatus.current_league.icon}
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">{leagueStatus.current_league.name}</p>
            {leagueStatus.next_league ? (
              <>
                <p className="mt-0.5 text-[11px] text-ink-mist">
                  Ещё {leagueStatus.points_to_next} очков до «{leagueStatus.next_league.name}»
                </p>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-accent-lime"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.round(
                          ((leagueStatus.total_rating - leagueStatus.current_league.min_rating) /
                            (leagueStatus.next_league.min_rating - leagueStatus.current_league.min_rating)) *
                            100
                        )
                      )}%`,
                    }}
                  />
                </div>
              </>
            ) : (
              <p className="mt-0.5 text-[11px] text-accent-lime">Высшая лига!</p>
            )}
          </div>
          <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
        </button>
      )}

      <ChatInviteCard />

      <div className="flex flex-col gap-3">
        {profile?.referral_reward_pending && (
          <NoticeCard
            Icon={IconHandshake}
            title="Тебя пригласил друг!"
            subtitle={`Открой любой пак (можно бесплатный) и получи ${profile.referral_referred_reward} монет`}
            onClick={() => navigate("/packs")}
          />
        )}

        {calendar && !calendar.already_claimed_today && (
          <NoticeCard
            Icon={IconGift}
            title="Ежедневная награда готова"
            subtitle={`День ${calendar.current_streak} — забери в профиле`}
            onClick={() => navigate("/profile")}
          />
        )}

        {freePackStatus && (
          <NoticeCard
            Icon={IconGift}
            title="Бесплатный пак"
            subtitle={
              freePackStatus.available
                ? claimFreePackMutation.isPending
                  ? "Получаем..."
                  : "Готов к получению!"
                : `Появится в ${new Date(freePackStatus.available_at!).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`
            }
            onClick={() => freePackStatus.available && claimFreePackMutation.mutate()}
            disabled={!freePackStatus.available || claimFreePackMutation.isPending}
            trailingIcon={freePackStatus.available ? undefined : IconClock}
          />
        )}

        {wheelStatus && flags?.wheel_enabled !== false && (
          <NoticeCard
            Icon={IconGift}
            title="Колесо фортуны"
            subtitle={
              wheelStatus.free_spins_remaining > 0
                ? `Осталось ${wheelStatus.free_spins_remaining} бесплатных прокруток сегодня`
                : "Бесплатные прокрутки закончились — крути за монеты или ⭐"
            }
            onClick={() => navigate("/wheel")}
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

function ChalkTexture() {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.06]" viewBox="0 0 320 160" fill="none">
      <line x1="20" y1="14" x2="60" y2="42" stroke="currentColor" strokeWidth="1" />
      <polyline points="54,36 60,42 55,48" stroke="currentColor" strokeWidth="1" fill="none" />
      <circle cx="270" cy="22" r="9" stroke="currentColor" strokeWidth="1" />
      <path d="M160 8 Q195 32 170 72" stroke="currentColor" strokeWidth="1" fill="none" />
      <circle cx="50" cy="100" r="5" stroke="currentColor" strokeWidth="1" />
      <line x1="290" y1="96" x2="300" y2="106" stroke="currentColor" strokeWidth="1" />
      <line x1="300" y1="96" x2="290" y2="106" stroke="currentColor" strokeWidth="1" />
    </svg>
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

function QuickAction({
  Icon,
  label,
  onClick,
  badge,
}: {
  Icon: (props: IconProps) => JSX.Element;
  label: string;
  onClick: () => void;
  badge?: number;
}) {
  return (
    <button onClick={onClick} className="flex flex-col items-center gap-2 active:scale-95">
      <span className="relative flex h-12 w-12 items-center justify-center rounded-full bg-bg-raised text-ink-chalk">
        <Icon size={20} />
        {!!badge && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 font-mono text-[9px] font-bold text-bg-base">
            {badge}
          </span>
        )}
      </span>
      <span className="text-xs text-ink-mist">{label}</span>
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
