import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  acceptPlayerCareerOffer,
  counterPlayerCareerOffer,
  fetchPlayerCareer,
  leavePlayerCareerSeason,
  signPlayerCareerContract,
  startPlayerCareerSeason,
  type PlayerCareerClub,
  type PlayerCareerCup,
  type PlayerCareerGoldenBall,
  type PlayerCareerHistoryEntry,
  type PlayerCareerOffer,
  type PlayerCareerSeason,
  type PlayerCareerView,
} from "@/api/playerCareer";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin, IconLock, IconProfile, IconTrophy } from "@/components/icons";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { BonusTab, CareerStatus, HallOfFame, NewsFeed, RankingsTab, StoryEvent } from "@/components/playerCareer/CareerLife";
import FriendsLeagueTab from "@/components/playerCareer/FriendsLeagueTab";
import KeyMoments from "@/components/playerCareer/KeyMoments";
import GameHero from "@/components/common/GameHero";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useCareerStars } from "@/lib/useCareerStars";
import { useAuthStore } from "@/store/authStore";

const starsText = (n: number) => "★".repeat(Math.max(1, Math.min(5, n)));

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86_400_000);
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `сегодня в ${time}`;
  if (d.toDateString() === tomorrow.toDateString()) return `завтра в ${time}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} в ${time}`;
}

type PageTab = "club" | "cups" | "friends" | "ranks" | "ball" | "bonus";
const PAGE_TABS: [PageTab, string][] = [
  ["club", "Клуб"], ["cups", "Кубки"], ["friends", "Лига друзей"], ["ranks", "Рейтинги"], ["ball", "Золотой мяч"], ["bonus", "Бонусы"],
];

/** «Карьера игрока»: «Мой игрок» signs for a club of the «Карьера тренера»
 * list (divisions = leagues) and plays week-long seasons. Bigger clubs need
 * rating and prestige; contracts end, clubs make offers in the transfer
 * window (haggling may make them walk away); the Champions League, the
 * national team and the monthly «Золотой мяч» on top. */
export default function PlayerCareerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["player-career"], queryFn: fetchPlayerCareer, refetchInterval: 60_000 });
  const [picking, setPicking] = useState(false);
  const [tab, setTab] = useState<PageTab>("club");
  const [error, setError] = useState<string | null>(null);
  const onView = (view: PlayerCareerView) => {
    queryClient.setQueryData(["player-career"], view);
    setError(null);
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const sign = useMutation({
    mutationFn: (key: string) => signPlayerCareerContract(key),
    onSuccess: (v) => { hapticNotify("success"); onView(v); setPicking(false); },
    onError,
  });
  const start = useMutation({
    mutationFn: (fast: boolean) => startPlayerCareerSeason(fast),
    onSuccess: (v) => { hapticNotify("success"); onView(v); },
    onError,
  });

  if (isLoading || !data) return <ListSkeleton />;
  if (!data.enabled) return <EmptyState icon={IconTrophy} title="«Карьера игрока» скоро вернётся" />;
  if (!data.has_player) {
    return (
      <EmptyState
        icon={IconProfile}
        title="Сначала создай своего игрока"
        description="В «Карьере игрока» твой футболист подписывает контракт с клубом и играет за него сезоны."
        action={<button onClick={() => navigate("/my-player")} className="rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base">Создать игрока</button>}
      />
    );
  }

  const season = data.season;
  const active = season?.status === "active";
  const contract = data.contract;
  const expired = !!contract?.expired;
  const openOffers = (season?.status === "finished" ? season.offers : []).filter((o) => o.status === "open");
  const activeCup = data.cups.some((c) => c.status === "active");
  const tabDot: Partial<Record<PageTab, boolean>> = {
    cups: activeCup, bonus: !!data.chest?.available || !!data.weekly?.tasks.some((t) => t.done && !t.claimed),
  };

  return (
    <div className="flex flex-col gap-4">
      <GameHero game="player-career" title="Карьера игрока" />

      <section className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4">
        {data.player && (
          <span className="h-16 w-16 shrink-0 overflow-hidden rounded-xl">
            <PlayerAvatar appearance={data.player.appearance} accessory={data.player.accessory} backdrop={data.player.background} number={data.player.number} className="h-full w-full" />
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold text-ink-chalk">
            {data.player?.name} · {data.rating}
            {data.shop?.pro && <span className="ml-1.5 rounded bg-violet-500 px-1.5 py-0.5 align-middle text-micro font-black text-white">PRO</span>}
          </span>
          <span className="block truncate text-xs text-ink-mist">
            {data.club ? (
              <>
                {data.club.name} · {data.club.league?.name} <span className="text-amber-300">{starsText(data.club.club_stars)}</span>
              </>
            ) : "Без клуба"}
          </span>
          <span className="block text-xs text-ink-chalk">
            Престиж <b className="text-accent-lime">{data.reputation}</b>
            {contract && !expired && <span className="text-ink-mist"> · контракт: {contract.seasons_left} сез. · {contract.salary}/сезон</span>}
            {expired && <span className="text-red-400"> · контракт закончился</span>}
          </span>
          {data.freshness && (
            <span className={`block text-caption ${data.freshness.value >= 70 ? "text-ink-mist" : data.freshness.value >= 40 ? "text-amber-300" : "text-red-400"}`}>
              Свежесть {data.freshness.value}% · матч −{data.freshness.per_match}
            </span>
          )}
        </span>
      </section>

      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {PAGE_TABS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative shrink-0 rounded-full px-3.5 py-2 text-xs font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {label}
            {tabDot[id] && tab !== id && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent-lime" />}
          </button>
        ))}
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {tab === "cups" && <CupsTab view={data} />}
      {tab === "friends" && <FriendsLeagueTab hasClub={!!data.club && !expired} />}
      {tab === "ranks" && <RankingsTab />}
      {tab === "ball" && data.golden_ball && <GoldenBallTab ball={data.golden_ball} />}
      {tab === "bonus" && <BonusTab view={data} onView={onView} onError={onError} />}

      {tab === "club" && (
        <>
          <KeyMoments view={data} onView={onView} onError={onError} />
          <StoryEvent view={data} onView={onView} onError={onError} />
          <CareerStatus view={data} onView={onView} onError={onError} />
          {expired && !active && (
            <section className="rounded-2xl bg-red-500/10 p-4 text-sm text-ink-chalk" data-testid="contract-expired">
              <b>Контракт закончился.</b>{" "}
              {openOffers.length
                ? "Прими одно из предложений ниже — или останешься без клуба и сможешь подписать только клуб низших дивизионов."
                : `Клубы ушли — теперь доступны только дивизионы с ${contract?.free_agent_level}-го и ниже.`}
            </section>
          )}
          {(!data.club || picking || (expired && !openOffers.length)) && data.can_change_club ? (
            <ClubPicker
              view={data}
              busy={sign.isPending}
              onPick={(club) => sign.mutate(club.key)}
              onCancel={data.club && picking ? () => setPicking(false) : undefined}
            />
          ) : (
            <>
              {season && <SeasonBlock season={season} view={data} onView={onView} onError={onError} />}
              {!active && data.club && !expired && (
                <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
                  <p className="text-sm text-ink-mist">
                    Сезон: 8 клубов дивизиона «{data.club.league?.name}», 14 туров по два в день. За результат +{data.rewards?.win}/
                    {data.rewards?.draw} монет, за гол +{data.rewards?.goal}, за матч +{data.rewards?.xp} опыта, в конце — награда за
                    место, зарплата и трофеи.
                  </p>
                  <p className="flex items-start gap-1.5 rounded-xl bg-bg-raised px-3 py-2 text-xs text-ink-chalk">
                    <IconCoin size={13} className="mt-0.5 shrink-0 text-accent-lime" />
                    <span>
                      Контракт: зарплата <b>{contract?.salary}</b> за сезон, ещё {contract?.seasons_left} сез. + {data.rewards?.objective_coins}{" "}
                      монет за каждую выполненную цель клуба
                    </span>
                  </p>
                  <button
                    disabled={start.isPending}
                    onClick={() => start.mutate(false)}
                    className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40 active:scale-[0.99]"
                  >
                    {season ? "Новый сезон" : "Начать сезон"} за «{data.club.name}»
                  </button>
                  {!!data.shop?.fast_enabled && (data.shop?.fast_season_credits ?? 0) > 0 && (
                    <button
                      disabled={start.isPending}
                      onClick={() => start.mutate(true)}
                      className="rounded-2xl bg-violet-500 py-2.5 text-sm font-bold text-white disabled:opacity-40"
                    >
                      ⏩ Ускоренный сезон (осталось {data.shop?.fast_season_credits})
                    </button>
                  )}
                  <p className="text-center text-caption text-ink-mist-dim">
                    Сменить клуб можно по предложению в трансферное окно — после сезона
                  </p>
                </section>
              )}
              <NewsFeed news={data.news} />
              <HallOfFame view={data} />
              {data.history.length > 0 && <CareerTimeline history={data.history} />}
            </>
          )}
        </>
      )}
    </div>
  );
}

function ClubPicker({
  view, busy, onPick, onCancel,
}: { view: PlayerCareerView; busy: boolean; onPick: (c: PlayerCareerClub) => void; onCancel?: () => void }) {
  const levels = [...new Set(view.clubs.map((c) => c.level))].sort((a, b) => a - b);
  const [level, setLevel] = useState<number>(() => {
    const open = view.clubs.filter((c) => !c.locked_reason).sort((a, b) => a.level - b.level);
    return open[0]?.level ?? levels[levels.length - 1] ?? 1;
  });
  const shown = view.clubs.filter((c) => c.level === level).sort((a, b) => Number(!!a.locked_reason) - Number(!!b.locked_reason) || b.rating - a.rating);
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="club-picker">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Выбери клуб</h2>
        {onCancel && <button onClick={onCancel} className="text-xs text-ink-mist">Отмена</button>}
      </div>
      <p className="text-caption text-ink-mist">
        Клубы и дивизионы — те же, что в «Карьере тренера». Чтобы подписать клуб сильнее, нужны рейтинг и престиж; чем выше
        дивизион, звёзды клуба и твой престиж — тем больше зарплата.
      </p>
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {levels.map((l) => {
          const name = view.clubs.find((c) => c.level === l)?.league?.name ?? `Дивизион ${l}`;
          const open = view.clubs.some((c) => c.level === l && !c.locked_reason);
          return (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${level === l ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
            >
              {!open && "🔒 "}{name}
            </button>
          );
        })}
      </div>
      {shown.map((club) => (
        <button
          key={club.key}
          disabled={!!club.locked_reason || busy || club.key === view.club?.key}
          onClick={() => onPick(club)}
          className={`flex items-center gap-3 rounded-xl p-3 text-left disabled:cursor-default ${
            club.key === view.club?.key ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"
          } ${club.locked_reason ? "opacity-60" : ""}`}
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-bg-surface font-display text-sm font-black text-ink-chalk">
            {club.rating}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink-chalk">
              {club.name} <span className="text-amber-300">{starsText(club.club_stars)}</span>
            </span>
            <span className="block truncate text-caption text-ink-mist">
              {club.is_demo ? "Клуб дивизиона" : `${club.real_cards} карточек · ${club.stars.join(", ")}`}
            </span>
            <span className="block text-micro text-accent-lime">
              Зарплата {club.salary} за сезон{club.reputation_needed > 0 && ` · престиж от ${club.reputation_needed}`}
              {!club.locked_reason && club.expected_role === "bench" && <span className="text-amber-300"> · будешь запасным</span>}
            </span>
            {club.legend && (
              <span className="block truncate text-micro text-ink-mist">🏛 Легенда: {club.legend.player_name} · ⚽ {club.legend.goals}</span>
            )}
          </span>
          {club.locked_reason ? (
            <span className="flex max-w-[7rem] shrink-0 items-center gap-1 text-right text-micro text-ink-mist"><IconLock size={12} /> {club.locked_reason}</span>
          ) : club.key === view.club?.key ? (
            <span className="text-xs font-bold text-accent-lime">твой</span>
          ) : (
            <span className="rounded-lg bg-floodlight px-2.5 py-1 text-xs font-bold text-bg-base">Подписать</span>
          )}
        </button>
      ))}
    </section>
  );
}

type Tab = "overview" | "table" | "calendar" | "scorers";

function SeasonBlock({
  season, view, onView, onError,
}: { season: PlayerCareerSeason; view: PlayerCareerView; onView: (v: PlayerCareerView) => void; onError: (e: unknown) => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [confirmLeave, setConfirmLeave] = useState(false);
  const leave = useMutation({ mutationFn: leavePlayerCareerSeason, onSuccess: onView, onError });
  const active = season.status === "active";
  const teams = season.teams;
  const last = [...season.rounds].reverse().find((r) => r.me);

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">
          {active ? `Сезон · тур ${season.rounds_played + 1} из ${season.total_rounds}` : `Сезон завершён · ${season.final_place} место`}
        </h2>
        <span className="text-xs text-ink-mist">+{season.coins_earned} монет</span>
      </div>

      <div className="grid grid-cols-4 gap-1 rounded-xl bg-bg-raised p-1">
        {([["overview", "Обзор"], ["table", "Таблица"], ["calendar", "Матчи"], ["scorers", "Бомбардиры"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-lg py-1.5 text-caption font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-4 gap-2 text-center">
            {[["Матчи", season.stats.matches], ["Голы", season.stats.goals], ["Пасы", season.stats.assists], ["Оценка", season.stats.avg_rating ?? "—"]].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-bg-raised py-2">
                <p className="font-display text-lg font-black text-ink-chalk">{value}</p>
                <p className="text-micro text-ink-mist">{label}</p>
              </div>
            ))}
          </div>
          {season.objectives.length > 0 && <Objectives season={season} rewardCoins={view.rewards?.objective_coins ?? 0} />}
          {!active && (season.salary > 0 || season.objective_coins > 0) && (
            <p className="rounded-xl bg-bg-raised px-3 py-2 text-xs text-ink-chalk">
              Зарплата +{season.salary} · цели клуба +{season.objective_coins}
            </p>
          )}
          {active && season.next_round_at && (
            <p className="text-sm text-ink-mist">Следующий тур: <b className="text-ink-chalk">{formatWhen(season.next_round_at)}</b></p>
          )}
          {last?.me && (
            <p className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk">
              Последний матч: {last.me.own}:{last.me.opp} с «{last.me.opponent}»
              {last.me.goals > 0 && ` · ⚽ ${last.me.goals}`}{last.me.assists > 0 && ` · 🅰️ ${last.me.assists}`}
              {last.me.rating != null && ` · оценка ${last.me.rating}`}
            </p>
          )}
          {!active && season.awards.length > 0 && (
            <p className="rounded-xl bg-amber-400/15 px-3 py-2 text-sm font-semibold text-amber-300">🏆 {season.awards.join(" · ")}</p>
          )}
          {!active && season.offers.length > 0 && <TransferWindow season={season} view={view} onView={onView} onError={onError} />}
          {active && (
            <button onClick={() => setConfirmLeave(true)} className="text-xs text-ink-mist-dim">Покинуть сезон</button>
          )}
        </div>
      )}

      {tab === "table" && (
        <table className="w-full text-left text-xs">
          <thead className="text-ink-mist">
            <tr><th className="py-1">#</th><th>Клуб</th><th className="text-center">И</th><th className="text-center">Р</th><th className="text-center">О</th></tr>
          </thead>
          <tbody>
            {season.table.map((row, i) => {
              const team = teams[row.team_index];
              return (
                <tr key={row.team_index} className={team?.is_mine ? "font-bold text-accent-lime" : "text-ink-chalk"}>
                  <td className="py-1.5">{i + 1}</td>
                  <td className="max-w-[9rem] truncate">{team?.name} <span className="text-ink-mist-dim">{team?.rating}</span></td>
                  <td className="text-center">{row.played}</td>
                  <td className="text-center">{row.gf - row.ga}</td>
                  <td className="text-center">{row.points}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {tab === "calendar" && (
        <div className="flex flex-col divide-y divide-white/5">
          {season.rounds.map((r) => {
            const homeMine = r.home === 0;
            const opp = teams[(homeMine ? r.away : r.home) ?? 0];
            const played = r.hs != null;
            const own = homeMine ? r.hs : r.away_score;
            const them = homeMine ? r.away_score : r.hs;
            return (
              <div key={r.index} className="flex items-center gap-3 py-2">
                <span className="w-6 font-mono text-micro text-ink-mist">{r.index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink-chalk">{homeMine ? "vs" : "@"} {opp?.name}</span>
                  <span className="block text-micro text-ink-mist-dim">
                    {played && r.me
                      ? [r.me.goals > 0 && `⚽ ${r.me.goals}`, r.me.assists > 0 && `🅰️ ${r.me.assists}`, r.me.rating != null && `оценка ${r.me.rating}`].filter(Boolean).join(" · ")
                      : formatWhen(r.at)}
                  </span>
                </span>
                {played && (
                  <span className={`font-mono text-sm font-bold ${own! > them! ? "text-accent-lime" : own === them ? "text-ink-mist" : "text-red-400"}`}>
                    {own}:{them}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {tab === "scorers" && (
        <div className="flex flex-col divide-y divide-white/5">
          {season.scorers.length === 0 && <p className="py-3 text-center text-sm text-ink-mist">Пока никто не забил</p>}
          {season.scorers.map((s, i) => (
            <div key={`${s.team}-${s.name}`} className={`flex items-center gap-3 py-2 text-sm ${s.name === view.player?.name && s.team === teams[0]?.name ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
              <span className="w-6 font-mono text-xs text-ink-mist">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate">{s.name} <span className="text-ink-mist">· {s.team}</span></span>
              <span className="font-mono font-bold">{s.goals}</span>
            </div>
          ))}
        </div>
      )}

      {confirmLeave && (
        <ConfirmDialog
          open
          title="Покинуть сезон?"
          description="Сезон закончится без награды за место. Заработанные монеты останутся."
          confirmLabel="Покинуть"
          danger
          onConfirm={() => { setConfirmLeave(false); leave.mutate(); }}
          onCancel={() => setConfirmLeave(false)}
        />
      )}
    </section>
  );
}

const OBJECTIVE_ICONS: Record<string, string> = { place: "🏁", goals: "⚽", clean_sheets: "🧱", avg_rating: "⭐" };

/** The club's season objectives: progress now, met / missed at the end. */
function Objectives({ season, rewardCoins }: { season: PlayerCareerSeason; rewardCoins: number }) {
  const active = season.status === "active";
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-bg-raised p-3" data-testid="career-objectives">
      <p className="flex items-center justify-between text-xs font-bold text-ink-chalk">
        Цели клуба <span className="font-normal text-ink-mist">+{rewardCoins} монет за каждую</span>
      </p>
      {season.objectives.map((o) => {
        const value = o.code === "place" ? (o.value ? `${o.value} место` : "—") : o.code === "avg_rating" ? (o.value || "—") : `${o.value}/${o.target}`;
        return (
          <div key={o.code} className="flex items-center gap-2 text-xs">
            <span>{OBJECTIVE_ICONS[o.code] ?? "🎯"}</span>
            <span className={`min-w-0 flex-1 truncate ${o.met ? "text-ink-chalk" : "text-ink-mist"}`}>{o.label}</span>
            <span className={`font-mono font-bold ${o.met ? "text-accent-lime" : active ? "text-ink-mist" : "text-red-400"}`}>
              {o.met ? "✓" : active ? value : "✗"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Career timeline: every finished season, newest first. */
function CareerTimeline({ history }: { history: PlayerCareerHistoryEntry[] }) {
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="career-timeline">
      <h2 className="font-display text-base font-bold text-ink-chalk">История карьеры</h2>
      <ol className="relative mt-3 flex flex-col gap-4 border-l border-white/10 pl-4">
        {history.map((h, i) => (
          <li key={h.id} className="relative">
            <span
              className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-bg-surface ${h.place === 1 ? "bg-amber-400" : "bg-accent-lime"}`}
            />
            <p className="text-sm font-semibold text-ink-chalk">
              Сезон {history.length - i} · {h.club}
              {h.club_rating != null && <span className="text-ink-mist-dim"> ({h.club_rating})</span>}
            </p>
            <p className="text-caption text-ink-mist">
              {h.place != null ? `${h.place} место` : "—"} · голов {h.goals} · передач {h.assists}
              {h.avg_rating != null && ` · оценка ${h.avg_rating}`}
            </p>
            {h.awards.length > 0 && <p className="text-caption font-semibold text-amber-300">🏆 {h.awards.join(" · ")}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Transfer window: offers with salary and signing bonus; accept, or ask
 * for more — each counter-offer may make the club walk away. */
function TransferWindow({
  season, view, onView, onError,
}: { season: PlayerCareerSeason; view: PlayerCareerView; onView: (v: PlayerCareerView) => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [result, setResult] = useState<PlayerCareerView["haggle"]>(null);
  const done = (v: PlayerCareerView) => {
    onView(v);
    if (v.balance != null) updateBalance(v.balance);
    void queryClient.invalidateQueries({ queryKey: ["my-player"], exact: true });
  };
  const accept = useMutation({
    mutationFn: (key: string) => acceptPlayerCareerOffer(key),
    onSuccess: (v) => { hapticNotify("success"); setResult(null); done(v); },
    onError,
  });
  const counter = useMutation({
    mutationFn: ({ key, pct }: { key: string; pct: number }) => counterPlayerCareerOffer(key, pct),
    onSuccess: (v) => {
      hapticNotify(v.haggle?.agreed ? "success" : "warning");
      setResult(v.haggle ?? null);
      done(v);
    },
    onError,
  });
  const stars = useCareerStars(onError);
  const shop = view.shop;
  const busy = accept.isPending || counter.isPending || !!stars.busy;
  const STATUS: Record<PlayerCareerOffer["status"], string> = { open: "", accepted: "Подписано", closed: "Закрыто", withdrawn: "Клуб ушёл" };
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-accent-lime/10 p-3" data-testid="transfer-window">
      <p className="text-sm font-bold text-accent-lime">Трансферное окно</p>
      <p className="text-caption text-ink-mist">
        Прими предложение или поторгуйся: чем больше просишь, тем выше риск, что клуб уйдёт. Торговаться можно до {view.max_counters} раз.
      </p>
      {season.agent ? (
        <p className="rounded-lg bg-bg-surface px-3 py-2 text-xs text-ink-chalk">🤝 Агент работает: +1 предложение и +{shop?.agent_haggle_bonus}% к шансу в торге</p>
      ) : shop && shop.agent_stars > 0 && (
        <button
          disabled={busy}
          onClick={() => stars.buy("agent")}
          className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-left text-xs text-ink-chalk disabled:opacity-40"
        >
          <span>🤝 Нанять агента: ещё предложение и +{shop.agent_haggle_bonus}% в торге</span>
          <span className="rounded bg-amber-400 px-2 py-0.5 font-bold text-bg-base">⭐ {shop.agent_stars}</span>
        </button>
      )}
      {result && (
        <p className={`rounded-lg px-3 py-2 text-xs font-semibold ${result.agreed ? "bg-accent-lime/15 text-accent-lime" : "bg-red-500/15 text-red-400"}`}>
          {result.agreed ? `«${result.club}» согласился на твои условия!` : `«${result.club}» отказался и ушёл.`}
        </p>
      )}
      {season.offers.map((o) => (
        <div key={o.key} className={`rounded-xl bg-bg-surface p-3 ${o.status !== "open" ? "opacity-60" : ""}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="min-w-0">
              <span className="block truncate text-sm font-bold text-ink-chalk">
                {o.renewal ? "Продление · " : ""}{o.name} <span className="text-amber-300">{starsText(o.club_stars)}</span>
              </span>
              <span className="block text-caption text-ink-mist">{o.league} · рейтинг {o.rating}</span>
            </span>
            {o.status !== "open" && <span className="shrink-0 text-xs font-semibold text-ink-mist">{STATUS[o.status]}</span>}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-center">
            <span className="rounded-lg bg-bg-raised py-1.5">
              <span className="block font-display text-base font-black text-ink-chalk">{o.salary}</span>
              <span className="block text-micro text-ink-mist">зарплата / сезон</span>
            </span>
            <span className="rounded-lg bg-bg-raised py-1.5">
              <span className="block font-display text-base font-black text-ink-chalk">{o.bonus}</span>
              <span className="block text-micro text-ink-mist">бонус за подпись</span>
            </span>
          </div>
          {o.status === "withdrawn" && !season.saved && shop && shop.save_offer_stars > 0 && (
            <button
              disabled={busy}
              onClick={() => stars.buy("save_offer", o.key)}
              className="mt-2 w-full rounded-lg bg-amber-400 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
            >
              Вернуть клуб · ⭐ {shop.save_offer_stars}
            </button>
          )}
          {o.status === "open" && (
            <div className="mt-2 flex gap-1.5">
              <button
                disabled={busy}
                onClick={() => accept.mutate(o.key)}
                className="flex-1 rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40"
              >
                Принять
              </button>
              {o.counters < view.max_counters &&
                view.haggle_steps.map((pct) => (
                  <button
                    key={pct}
                    disabled={busy}
                    onClick={() => { haptic("light"); counter.mutate({ key: o.key, pct }); }}
                    className="rounded-lg bg-bg-raised px-2.5 py-2 text-xs font-bold text-ink-chalk disabled:opacity-40"
                  >
                    +{pct}%
                  </button>
                ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function CupsTab({ view }: { view: PlayerCareerView }) {
  const national = view.national;
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl bg-bg-surface p-4" data-testid="national-status">
        <h2 className="font-display text-base font-bold text-ink-chalk">🌍 Сборная</h2>
        <p className="mt-1 text-sm text-ink-mist">
          {!national?.country
            ? "Выбери страну в конструкторе игрока («Изменить» → «Данные»), чтобы тебя могли вызвать в сборную."
            : national.called_up
              ? `Ты в сборной: ${national.country}. Турнир сборных — раз в две недели.`
              : `${national.country}: для вызова нужен престиж ${national.prestige_needed} (у тебя ${view.reputation}).`}
        </p>
      </section>
      <section className="rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">⭐ Лига чемпионов</h2>
        <p className="mt-1 text-sm text-ink-mist">
          Лучшие клубы высшего дивизиона после сезона играют Лигу чемпионов: 8 клубов, плей-офф, призы за каждый раунд и трофей.
        </p>
      </section>
      {view.cups.map((cup) => <CupCard key={cup.id} cup={cup} />)}
    </div>
  );
}

function CupCard({ cup }: { cup: PlayerCareerCup }) {
  const verdict = cup.status === "active" ? `идёт · ${cup.rounds[cup.rounds_played]?.label ?? ""}` : cup.won ? "🏆 победа!" : "вылет";
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid={`cup-${cup.kind}`}>
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">{cup.title}</h2>
        <span className={`text-xs font-semibold ${cup.won ? "text-amber-300" : cup.status === "active" ? "text-accent-lime" : "text-ink-mist"}`}>{verdict}</span>
      </div>
      {cup.status === "active" && cup.next_round_at && (
        <p className="text-sm text-ink-mist">Следующий матч: <b className="text-ink-chalk">{formatWhen(cup.next_round_at)}</b></p>
      )}
      {cup.rounds.map((round) => (
        <div key={round.label} className="rounded-xl bg-bg-raised p-3">
          <p className="mb-1.5 text-xs font-bold text-ink-chalk">{round.label}</p>
          {round.matches.map((m) => (
            <div key={`${m.home}-${m.away}`} className="flex items-center justify-between gap-2 py-0.5 text-xs">
              <span className={`min-w-0 flex-1 truncate ${m.home_mine ? "font-bold text-accent-lime" : "text-ink-chalk"} ${m.hs != null && !m.home_won ? "opacity-50" : ""}`}>{m.home}</span>
              <span className="shrink-0 font-mono text-ink-mist">{m.hs != null ? `${m.hs}:${m.away_score}${m.pens ? " п" : ""}` : "—"}</span>
              <span className={`min-w-0 flex-1 truncate text-right ${m.away_mine ? "font-bold text-accent-lime" : "text-ink-chalk"} ${m.hs != null && m.home_won ? "opacity-50" : ""}`}>{m.away}</span>
            </div>
          ))}
          {round.me?.played && (
            <p className="mt-1 text-micro text-ink-mist">
              Ты: {[round.me.goals > 0 && `⚽ ${round.me.goals}`, round.me.assists > 0 && `🅰️ ${round.me.assists}`, round.me.rating != null && `оценка ${round.me.rating}`].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      ))}
      {cup.coins_earned > 0 && <p className="text-xs text-ink-mist">Заработано: +{cup.coins_earned} монет</p>}
    </section>
  );
}

const LINE_LABELS: Record<string, string> = { GK: "Вратарь", DEF: "Защитник", MID: "Полузащитник", FWD: "Нападающий" };
const LINE_SHORT: Record<string, string> = { GK: "ВРТ", DEF: "ЗАЩ", MID: "ПЗ", FWD: "НАП" };

function GoldenBallTab({ ball }: { ball: PlayerCareerGoldenBall }) {
  return (
    <div className="flex flex-col gap-4" data-testid="golden-ball">
      <section className="rounded-2xl bg-gradient-to-br from-amber-400/25 to-bg-surface p-4">
        <p className="font-display text-lg font-bold text-ink-chalk">⚽ Золотой мяч · {ball.month_label}</p>
        <p className="mt-1 text-caption text-ink-mist">
          Лучший игрок месяца по всем матчам «Карьеры игрока» — для любой позиции: очки = средняя оценка × 10 + голы, передачи и
          сухие матчи по ценам своей линии. Нужно сыграть минимум {ball.min_matches} матчей. Приз: {ball.prize_coins} монет,
          +{ball.prize_prestige} престижа и трофей.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-1.5 text-caption" data-testid="golden-ball-weights">
          {["FWD", "MID", "DEF", "GK"].filter((l) => ball.weights?.[l]).map((l) => (
            <span key={l} className="rounded-lg bg-black/20 px-2 py-1 text-ink-mist">
              <b className="text-ink-chalk">{LINE_LABELS[l]}</b>: гол {ball.weights[l].goals} · пас {ball.weights[l].assists}
              {ball.weights[l].clean_sheets > 0 && ` · на ноль ${ball.weights[l].clean_sheets}`}
            </span>
          ))}
        </div>
        {ball.me && (
          <p className="mt-2 text-sm text-ink-chalk">
            Ты: {ball.me.place ? <b>{ball.me.place} место</b> : `матчей ${ball.me.matches}/${ball.min_matches}`} · {ball.me.score} очков
          </p>
        )}
      </section>
      <section className="rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">Гонка месяца</h2>
        {ball.table.length === 0 ? (
          <p className="mt-2 text-sm text-ink-mist">Пока никто не сыграл {ball.min_matches} матчей в этом месяце.</p>
        ) : (
          <div className="mt-2 flex flex-col divide-y divide-white/5">
            {ball.table.map((e) => (
              <div key={e.user_id} className={`flex items-center gap-3 py-2 text-sm ${e.is_me ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
                <span className="w-6 font-mono text-xs text-ink-mist">{e.place}</span>
                <span className="min-w-0 flex-1 truncate">
                  {e.user_name} <span className="font-mono text-micro text-ink-mist">{LINE_SHORT[e.line] ?? ""}</span>
                </span>
                <span className="text-caption text-ink-mist">
                  ⚽ {e.goals} · 🅰️ {e.assists}{e.clean_sheets > 0 && ` · 🧱 ${e.clean_sheets}`} · {e.avg_rating}
                </span>
                <span className="w-12 text-right font-mono font-bold">{e.score}</span>
              </div>
            ))}
          </div>
        )}
      </section>
      {ball.winners.length > 0 && (
        <section className="rounded-2xl bg-bg-surface p-4">
          <h2 className="font-display text-base font-bold text-ink-chalk">Обладатели</h2>
          <div className="mt-2 flex flex-col gap-1.5">
            {ball.winners.map((w) => (
              <p key={w.month} className={`text-sm ${w.is_me ? "font-bold text-amber-300" : "text-ink-chalk"}`}>
                🏆 {w.month_label}: {w.user_name} <span className="text-ink-mist">· {w.goals} голов, {w.assists ?? 0} передач, оценка {w.avg_rating}</span>
              </p>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
