import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchBlackjackStatus } from "@/api/blackjack";
import { fetchCareer } from "@/api/career";
import { fetchMatchDay, fetchWeeklyCup } from "@/api/events";
import { fetchGameLimits, fetchPenaltyStats } from "@/api/games";
import { fetchArenaStats } from "@/api/matches";
import { fetchKontraHub } from "@/api/kontra";
import { fetchMordoboiInfo, fetchMordoboiMatches, fetchMordoboiStats } from "@/api/mordoboi";
import { fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { fetchStrategoStats } from "@/api/stratego";
import { fetchTacticoMatches, fetchTacticoStats } from "@/api/tactico";
import {
  IconBall,
  IconBoxingGlove,
  IconBrain,
  IconCard,
  IconChart,
  IconCollection,
  IconCounter,
  IconDice,
  IconFlag,
  IconGoal,
  IconLetters,
  IconPairs,
  IconParty,
  IconProfile,
  IconTactics,
  IconTarget,
  IconTrophy,
  IconWhistle,
  type IconProps,
} from "@/components/icons";
import { Skeleton } from "@/components/common/Skeleton";
import { hapticSelection } from "@/lib/telegram";
import { formatClock } from "@/lib/today";
import { usePersistentState } from "@/lib/usePersistentState";
import { useAuthStore } from "@/store/authStore";
import type { GameLimits } from "@/types";

/** Illustrated game art (192 px webp); games without one keep their tinted icon. */
const GAME_ART = import.meta.glob<string>("@/assets/games/*.webp", { eager: true, import: "default" });
const artOf = (key: string): string | undefined => GAME_ART[`/src/assets/games/${key}.webp`];

function playerTournamentStatusLabel(status?: string, queuePosition?: number | null): string {
  switch (status) {
    case "queued":
      return `В очереди — место ${queuePosition ?? "?"}`;
    case "active":
      return "Турнир идёт";
    case "completed":
      return "Турнир завершён";
    default:
      return "Собери состав и подай заявку";
  }
}

type LimitKey = Exclude<keyof GameLimits, "hourly_limit" | "resets_at">;
type Group = "quick" | "tactics" | "long";
type Filter = "all" | Group | "friend" | "favs";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "quick", label: "⚡ Быстрые" },
  { id: "tactics", label: "🧠 Тактика" },
  { id: "long", label: "🏆 Сезоны" },
  { id: "friend", label: "👥 С другом" },
  { id: "favs", label: "❤️ Избранное" },
];

interface GameDef {
  path: string;
  Icon: (props: IconProps) => JSX.Element;
  /** Each game has its own colour — no two tiles alike. Literal classes. */
  tint: string;
  /** Picture for the tile instead of the icon (src/assets/games/<key>.webp). */
  art?: string;
  title: string;
  description: string;
  group: Group;
  /** «⏱ 3 мин», «неделя». */
  time: string;
  friend?: boolean;
  bot?: boolean;
  stat?: string;
  limitKey?: LimitKey;
  rightLabel?: string;
  noLimit?: boolean;
}

/** One item of the «Сейчас» strip: something waiting for the player. */
interface NowItem {
  key: string;
  kicker: string;
  title: string;
  tone: string;
  to: string;
}

const CAREER_SOON_MS = 3 * 60 * 60 * 1000;

export default function PlayPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [lastGame, setLastGame] = usePersistentState<string | null>("play.last", null);
  const [filter, setFilter] = usePersistentState<Filter>("play.filter", "all");
  const [favs, setFavs] = usePersistentState<string[]>("play.favs", []);
  const { data: arenaStats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });
  const { data: tacticoStats } = useQuery({ queryKey: ["tactico-stats"], queryFn: fetchTacticoStats });
  const { data: strategoStats } = useQuery({ queryKey: ["stratego-stats"], queryFn: fetchStrategoStats });
  const { data: penaltyStats } = useQuery({ queryKey: ["penalty-stats"], queryFn: fetchPenaltyStats });
  const { data: limits } = useQuery({ queryKey: ["game-limits"], queryFn: fetchGameLimits });
  const { data: blackjack } = useQuery({ queryKey: ["blackjack-status"], queryFn: fetchBlackjackStatus });
  const { data: mordoboi } = useQuery({ queryKey: ["mordoboi-info"], queryFn: fetchMordoboiInfo });
  const { data: kontra } = useQuery({ queryKey: ["kontra-hub"], queryFn: fetchKontraHub });
  const { data: mordoboiStats } = useQuery({
    queryKey: ["mordoboi-stats"], queryFn: fetchMordoboiStats, enabled: !!mordoboi?.enabled,
  });
  const { data: mordoboiMatches } = useQuery({
    queryKey: ["mordoboi-matches"], queryFn: fetchMordoboiMatches, enabled: !!mordoboi?.enabled,
  });
  const { data: playerTournamentCurrent } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });
  // Same keys as the Tactico and career pages — shared caches.
  const { data: tacticoMatches } = useQuery({ queryKey: ["tactico-matches"], queryFn: fetchTacticoMatches });
  const { data: career } = useQuery({ queryKey: ["career"], queryFn: fetchCareer, staleTime: 60_000 });
  const { data: weeklyCup } = useQuery({ queryKey: ["weekly-cup"], queryFn: fetchWeeklyCup, staleTime: 60_000 });
  const { data: matchDay } = useQuery({ queryKey: ["match-day"], queryFn: fetchMatchDay, staleTime: 60_000 });

  const blackjackEntries = blackjack ? blackjack.free_remaining + blackjack.replay_entries + blackjack.paid_entries : 0;
  const games: GameDef[] = [
    // ⚡ quick
    {
      path: "/play/arena", art: artOf("arena"), Icon: IconBall, tint: "bg-emerald-500", title: "Card Arena", group: "quick", time: "3 мин", bot: true,
      description: "Собери состав и сыграй матч",
      stat: arenaStats?.division
        ? `Дивизион ${arenaStats.division.division} · ${arenaStats.division.points} очк.`
        : `Рейтинг ${arenaStats?.arena_rating ?? user?.arena_rating ?? 1000}`,
      limitKey: "arena",
    },
    {
      path: "/play/penalty", art: artOf("penalty"), Icon: IconGoal, tint: "bg-orange-500", title: "Пенальти", group: "quick", time: "2 мин", bot: true, friend: true,
      description: "Серия пенальти против бота или друга",
      stat: `Рейтинг ${penaltyStats?.penalty_rating ?? user?.penalty_rating ?? 0}`, limitKey: "penalty",
    },
    {
      path: "/play/free-kick", art: artOf("free-kick"), Icon: IconTarget, tint: "bg-blue-500", title: "Штрафной удар", group: "quick", time: "1 мин",
      description: "Останови шкалу силы в нужный момент", limitKey: "free_kick",
    },
    {
      path: "/play/memory", art: artOf("memory"), Icon: IconBrain, tint: "bg-teal-500", title: "Memory", group: "quick", time: "1 мин",
      description: "Запомни и повтори последовательность",
      stat: `Рекорд ${user?.memory_best_score ?? 0}`, limitKey: "memory",
    },
    {
      path: "/play/hangman", art: artOf("hangman"), Icon: IconLetters, tint: "bg-purple-500", title: "Футбольные буквы", group: "quick", time: "2 мин",
      description: "Угадай футболиста или термин по буквам", limitKey: "hangman",
    },
    {
      path: "/play/pairs", art: artOf("pairs"), Icon: IconPairs, tint: "bg-slate-400", title: "Найди пару", group: "quick", time: "2 мин",
      description: "Находи одинаковых футболистов", limitKey: "pairs",
    },
    {
      path: "/play/saboteur", art: artOf("saboteur"), Icon: IconParty, tint: "bg-pink-500", title: "Футбольный фанат", group: "quick", time: "2 мин",
      description: "Проберись сквозь стюардов к любимому игроку", limitKey: "saboteur",
    },
    ...(blackjack?.enabled
      ? [{
        path: "/play/blackjack", art: artOf("blackjack"), Icon: IconCard, tint: "bg-rose-500", title: "21: Добавленное время", group: "quick" as Group,
        time: "3 мин", bot: true,
        description: "Блэкджек против Тренера — победа крутит Золотое колесо",
        stat: blackjack.active_match ? "Партия идёт" : `Попыток: ${blackjackEntries}`,
        rightLabel: blackjack.free_remaining > 0 ? "бесплатно сегодня" : `⭐ ${blackjack.stars_cost}`,
      }]
      : []),
    // 🧠 tactics
    {
      path: "/play/tactico", art: artOf("tactico"), Icon: IconTactics, tint: "bg-sky-500", title: "Тактико", group: "tactics", time: "10 мин", bot: true, friend: true,
      description: "Состав из 11 карт, раунд за раундом",
      stat: `Рейтинг ${tacticoStats?.tactics_rating ?? user?.tactics_rating ?? 0}`, limitKey: "tactico",
    },
    {
      path: "/play/stratego", art: artOf("stratego"), Icon: IconFlag, tint: "bg-red-500", title: "Футбольное Стратего", group: "tactics", time: "15 мин", bot: true, friend: true,
      description: "Скрытая расстановка: найди и захвати Кубок соперника",
      stat: `Рейтинг ${strategoStats?.stratego_rating ?? 0}`, limitKey: "stratego",
    },
    ...(mordoboi?.enabled
      ? [{
        path: "/play/mordoboi", art: artOf("mordoboi"), Icon: IconBoxingGlove, tint: "bg-yellow-500", title: "Мордобой", group: "tactics" as Group,
        time: "5 мин", bot: true, friend: true,
        description: "Боксёрский поединок карточек: угадай удар соперника",
        stat: `Рейтинг ${mordoboiStats?.mordoboi_rating ?? 0}`, limitKey: "mordoboi" as LimitKey,
      }]
      : []),
    ...(kontra?.enabled
      ? [{
        path: "/play/kontra", art: artOf("kontra"), Icon: IconCounter, tint: "bg-green-600", title: "Контратака", group: "tactics" as Group,
        time: "5 мин", bot: true,
        description: "Отряд из 5 карт: арена и босс недели",
        stat: `Арена ${kontra.rating}`, limitKey: "kontra" as LimitKey,
      }]
      : []),
    {
      path: "/play/magnate", art: artOf("magnate"), Icon: IconDice, tint: "bg-violet-500", title: "Футбольный магнат", group: "tactics", time: "15 мин", bot: true, friend: true,
      description: "Клубы, стадионы и аренда — 4 игрока, онлайн или с ботами", limitKey: "magnate",
    },
    {
      path: "/play/fut-draft", art: artOf("fut-draft"), Icon: IconCollection, tint: "bg-fuchsia-500", title: "FUT Draft", group: "tactics", time: "10 мин", bot: true,
      description: "Состав из случайных карт и серия матчей", noLimit: true,
    },
    // 🏆 long
    {
      path: "/play/career", art: artOf("career"), Icon: IconWhistle, tint: "bg-cyan-500", title: "Карьера тренера", group: "long", time: "неделя", friend: true,
      description: "8 команд, 14 туров, свои карточки — один или с другом", rightLabel: "2 тура в день",
    },
    {
      path: "/play/player-career", art: artOf("player-career"), Icon: IconProfile, tint: "bg-lime-500", title: "Карьера игрока", group: "long", time: "сезон",
      description: "Твой игрок в клубе: голы, оценки, трансферы", rightLabel: "Мой игрок",
    },
    {
      path: "/play/manager", art: artOf("manager"), Icon: IconChart, tint: "bg-indigo-500", title: "Менеджер", group: "long", time: "неделя",
      description: "Свой клуб, трансферы и 10 дивизионов", rightLabel: "Новое",
    },
    {
      path: "/player-tournament", art: artOf("player-tournament"), Icon: IconTrophy, tint: "bg-amber-400", title: "Личный турнир", group: "long", time: "30 туров",
      description: "16 игроков — свой состав и тактика",
      stat: playerTournamentStatusLabel(playerTournamentCurrent?.status, playerTournamentCurrent?.queue_position),
      rightLabel: "16 игроков",
    },
  ];

  const exhausted = (g: GameDef) => !!limits && !!g.limitKey && limits[g.limitKey] === 0;
  const isFav = (g: GameDef) => favs.includes(g.path);
  const shown = games
    .filter((g) =>
      filter === "all" ? true : filter === "friend" ? g.friend : filter === "favs" ? isFav(g) : g.group === filter,
    )
    // Favourites first, used-up games last — the top is always playable.
    .sort((a, b) => Number(isFav(b)) - Number(isFav(a)) || Number(exhausted(a)) - Number(exhausted(b)));

  const open = (path: string) => {
    setLastGame(path);
    navigate(path);
  };
  const toggleFav = (g: GameDef) => {
    hapticSelection();
    setFavs(isFav(g) ? favs.filter((p) => p !== g.path) : [...favs, g.path]);
  };

  // «Сейчас»: what waits for the player right now, most urgent first.
  const now: NowItem[] = [];
  for (const m of tacticoMatches ?? []) {
    if (m.status === "in_progress" && !m.waiting_for_opponent && m.opponent_type !== "bot") {
      now.push({ key: `t${m.id}`, kicker: "Твой ход", title: `Тактико · ${m.opponent_name}`, tone: "bg-sky-500/15 text-sky-200 ring-sky-400/30", to: `/play/tactico/matches/${m.id}` });
    } else if (m.status === "pending_accept" && m.viewer_side === "opponent") {
      now.push({ key: `c${m.id}`, kicker: "Вызов", title: `Тактико · ${m.opponent_name}`, tone: "bg-amber-400/15 text-amber-200 ring-amber-400/30", to: "/play/tactico" });
    }
  }
  for (const m of mordoboiMatches ?? []) {
    if (m.status === "in_progress" && m.can_pick && m.opponent_type !== "bot") {
      now.push({ key: `m${m.id}`, kicker: "Твой удар", title: `Мордобой · ${m.opponent_name}`, tone: "bg-yellow-500/15 text-yellow-200 ring-yellow-400/30", to: `/play/mordoboi/matches/${m.id}` });
    } else if (m.status === "pending_accept" && m.viewer_side === "opponent") {
      now.push({ key: `mc${m.id}`, kicker: "Вызов на ринг", title: `Мордобой · ${m.opponent_name}`, tone: "bg-amber-400/15 text-amber-200 ring-amber-400/30", to: `/play/mordoboi/matches/${m.id}` });
    }
  }
  if (kontra?.active_battle_id) {
    now.push({ key: "k", kicker: "Бой идёт", title: "Контратака", tone: "bg-green-500/15 text-green-200 ring-green-400/30", to: `/play/kontra/battles/${kontra.active_battle_id}` });
  }
  if (career?.invite) {
    now.push({ key: "ci", kicker: "Приглашение", title: `Карьера · ${career.invite.from_name}`, tone: "bg-cyan-500/15 text-cyan-200 ring-cyan-400/30", to: "/play/career" });
  } else if (career?.season?.status === "active" && career.season.next_round_at) {
    const at = new Date(career.season.next_round_at).getTime();
    if (at - Date.now() < CAREER_SOON_MS) {
      now.push({ key: "cr", kicker: `Тур в ${formatClock(career.season.next_round_at)}`, title: "Карьера · проверь состав", tone: "bg-cyan-500/15 text-cyan-200 ring-cyan-400/30", to: "/play/career" });
    }
  }
  if (playerTournamentCurrent?.status === "active") {
    now.push({ key: "pt", kicker: "Идёт", title: "Личный турнир", tone: "bg-amber-400/15 text-amber-200 ring-amber-400/30", to: "/player-tournament" });
  }
  if (blackjack?.active_match) {
    now.push({ key: "bj", kicker: "Партия идёт", title: "21: Добавленное время", tone: "bg-rose-500/15 text-rose-200 ring-rose-400/30", to: "/play/blackjack" });
  }
  if (weeklyCup?.unclaimed_coins) {
    now.push({ key: "wc", kicker: "Приз недели", title: `Забрать ${weeklyCup.unclaimed_coins} монет`, tone: "bg-amber-400/15 text-amber-200 ring-amber-400/30", to: "/weekly-cup" });
  }
  if (matchDay?.unclaimed) {
    now.push({ key: "mdc", kicker: "Матч дня", title: "Награда ждёт", tone: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30", to: "/match-day" });
  } else if (matchDay?.enabled && matchDay.current?.open && !matchDay.current.prediction) {
    now.push({ key: "md", kicker: "Матч дня", title: `${matchDay.current.home} — ${matchDay.current.away}`, tone: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/30", to: "/match-day" });
  }
  const last = games.find((g) => g.path === lastGame);
  if (last && !exhausted(last)) {
    now.push({ key: "last", kicker: "Продолжить", title: last.title, tone: "bg-accent-lime/15 text-accent-lime ring-accent-lime/30", to: last.path });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Играть</h1>
        <button
          onClick={() => navigate("/ranking")}
          className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95"
        >
          <IconTrophy size={14} />
          <span>Рейтинг</span>
        </button>
      </div>

      {now.length > 0 && (
        <section>
          <h2 className="mb-2 font-mono text-caption uppercase tracking-wider text-ink-mist">Сейчас</h2>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
            {now.map((n) => (
              <button
                key={n.key}
                onClick={() => (n.key === "last" ? open(n.to) : navigate(n.to))}
                className={`flex w-[150px] shrink-0 flex-col rounded-2xl px-3 py-2.5 text-left ring-1 active:scale-[0.97] ${n.tone}`}
              >
                <span className="text-micro font-bold uppercase tracking-wider opacity-80">{n.kicker}</span>
                <span className="truncate font-display text-sm font-bold text-ink-chalk">{n.title}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {(weeklyCup?.enabled || matchDay?.enabled) && (
        <section className="grid grid-cols-2 gap-2">
          {weeklyCup?.enabled && (
            <button
              onClick={() => navigate("/weekly-cup")}
              className="flex min-w-0 flex-col gap-1 rounded-2xl bg-gradient-to-br from-orange-500/25 to-bg-surface p-3 text-left ring-1 ring-orange-400/25 active:scale-[0.98]"
            >
              <span className="text-micro font-bold uppercase tracking-wider text-orange-200">🏆 Неделя</span>
              <span className="line-clamp-2 font-display text-sm font-bold leading-tight text-ink-chalk">{weeklyCup.title}</span>
              <span className="truncate text-caption text-ink-mist">
                {weeklyCup.me ? `${weeklyCup.me.place} место · ${weeklyCup.me.points} очк.` : `Приз за 1 место — ${weeklyCup.prizes[0] ?? 0}`}
              </span>
            </button>
          )}
          {matchDay?.enabled && (
            <button
              onClick={() => navigate("/match-day")}
              className="flex min-w-0 flex-col gap-1 rounded-2xl bg-gradient-to-br from-emerald-600/25 to-bg-surface p-3 text-left ring-1 ring-emerald-400/25 active:scale-[0.98]"
            >
              <span className="text-micro font-bold uppercase tracking-wider text-emerald-200">⚽ Матч дня</span>
              <span className="line-clamp-2 font-display text-sm font-bold leading-tight text-ink-chalk">
                {matchDay.current ? `${matchDay.current.home} — ${matchDay.current.away}` : "Скоро"}
              </span>
              <span className="truncate text-caption text-ink-mist">
                {matchDay.current?.prediction
                  ? `Прогноз ${matchDay.current.prediction.home}:${matchDay.current.prediction.away}`
                  : matchDay.current?.open ? `Угадай счёт — до ${matchDay.rewards.exact} монет` : "Ждём результат"}
              </span>
            </button>
          )}
        </section>
      )}

      {/* All filters visible at once: a 3×2 grid like the shop sections. */}
      <div className="grid grid-cols-3 gap-1.5" role="tablist" aria-label="Фильтр игр">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`min-w-0 truncate rounded-full px-2 py-2 text-xs font-semibold active:scale-95 ${
              filter === f.id ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {shown.map((g) => (
          <GameRow
            key={g.path}
            game={g}
            fav={isFav(g)}
            onToggleFav={() => toggleFav(g)}
            onClick={() => open(g.path)}
            remaining={g.limitKey ? limits?.[g.limitKey] : undefined}
            limit={limits?.hourly_limit}
            resetsAt={g.limitKey ? limits?.resets_at?.[g.limitKey] : undefined}
          />
        ))}
        {!shown.length && (
          <p className="rounded-2xl bg-bg-surface px-4 py-6 text-center text-sm text-ink-mist">
            {filter === "favs" ? "Нажми ♡ у игры, чтобы она была здесь и наверху списка" : "Здесь пока пусто"}
          </p>
        )}
      </div>
    </div>
  );
}

function GameRow({
  game, fav, onToggleFav, onClick, remaining, limit, resetsAt,
}: {
  game: GameDef;
  fav: boolean;
  onToggleFav: () => void;
  onClick: () => void;
  remaining?: number;
  limit?: number;
  resetsAt?: string;
}) {
  const { Icon } = game;
  const used = remaining === 0;
  return (
    <div className={`flex items-center gap-1 rounded-2xl bg-bg-surface p-3 ${used ? "opacity-60" : ""}`}>
      <button onClick={onClick} className="flex min-w-0 flex-1 items-center gap-3 text-left active:scale-[0.98]">
        <span
          className={`relative flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-2xl shadow-[0_6px_16px_-6px_rgba(0,0,0,0.6)] ${game.tint}`}
        >
          {game.art ? (
            <img src={game.art} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" />
          ) : (
            <>
              <span className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/35 to-transparent" aria-hidden />
              <Icon size={22} className="relative text-white drop-shadow-sm" />
            </>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-sm font-bold text-ink-chalk">{game.title}</span>
          <span className="block truncate text-caption text-ink-mist">{game.description}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-micro text-ink-mist-dim">
            <span>⏱ {game.time}</span>
            {game.friend && <span>👥 с другом</span>}
            {game.bot && <span>🤖 с ботом</span>}
            {game.stat && <span className="font-mono">{game.stat}</span>}
          </span>
        </span>
        <span className="shrink-0 text-right">
          {game.rightLabel !== undefined ? (
            <span className="block max-w-[72px] text-micro text-ink-mist-dim">{game.rightLabel}</span>
          ) : remaining !== undefined && limit !== undefined ? (
            used ? (
              <>
                <span className="block font-mono text-sm font-bold text-red-400">0/{limit}</span>
                <span className="block text-micro text-ink-mist-dim">{resetsAt ? `в ${formatClock(resetsAt)}` : "лимит"}</span>
              </>
            ) : (
              <>
                <span className="block font-mono text-sm font-bold text-ink-chalk">{remaining}/{limit}</span>
                <span className="block text-micro text-ink-mist-dim">в час</span>
              </>
            )
          ) : game.noLimit ? (
            <span className="block text-micro text-ink-mist-dim">Платный вход</span>
          ) : (
            <Skeleton className="h-8 w-10" />
          )}
        </span>
      </button>
      <button
        onClick={onToggleFav}
        aria-label={fav ? `Убрать «${game.title}» из избранного` : `Добавить «${game.title}» в избранное`}
        aria-pressed={fav}
        className={`-mr-1 flex h-8 w-7 shrink-0 items-center justify-center rounded-full text-base active:scale-90 ${fav ? "text-rose-400" : "text-ink-mist-dim"}`}
      >
        {fav ? "♥" : "♡"}
      </button>
    </div>
  );
}
