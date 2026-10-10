import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchGameLimits, fetchPenaltyStats } from "@/api/games";
import { fetchArenaStats } from "@/api/matches";
import { fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { fetchTacticoStats } from "@/api/tactico";
import {
  IconBall,
  IconBrain,
  IconCard,
  IconChevronRight,
  IconFlagCheckered,
  IconGoal,
  IconHelp,
  IconProfile,
  IconStar,
  IconTarget,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { Skeleton } from "@/components/common/Skeleton";
import { formatClock } from "@/lib/today";
import { usePersistentState } from "@/lib/usePersistentState";
import { useAuthStore } from "@/store/authStore";
import type { GameLimits } from "@/types";

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

interface GameDef {
  path: string;
  Icon: (props: IconProps) => JSX.Element;
  badgeClass: string;
  title: string;
  description: string;
  stat?: string;
  limitKey?: LimitKey;
  rightLabel?: string;
  noLimit?: boolean;
}

export default function PlayPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [lastGame, setLastGame] = usePersistentState<string | null>("play.last", null);
  const { data: arenaStats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });
  const { data: tacticoStats } = useQuery({ queryKey: ["tactico-stats"], queryFn: fetchTacticoStats });
  const { data: penaltyStats } = useQuery({ queryKey: ["penalty-stats"], queryFn: fetchPenaltyStats });
  const { data: limits } = useQuery({ queryKey: ["game-limits"], queryFn: fetchGameLimits });
  const { data: playerTournamentCurrent } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });

  const matches: GameDef[] = [
    {
      path: "/play/arena", Icon: IconBall, badgeClass: "bg-accent-green", title: "Card Arena",
      description: "Собери состав 4-3-3 и сыграй матч",
      stat: `Рейтинг: ${arenaStats?.arena_rating ?? user?.arena_rating ?? 1000}`, limitKey: "arena",
    },
    {
      path: "/play/tactico", Icon: IconFlagCheckered, badgeClass: "bg-rarity-rare", title: "Тактико",
      description: "Состав из 11 карт против соперника, раунд за раундом",
      stat: `Рейтинг: ${tacticoStats?.tactics_rating ?? user?.tactics_rating ?? 0}`, limitKey: "tactico",
    },
    {
      path: "/player-tournament", Icon: IconFlagCheckered, badgeClass: "bg-accent-lime", title: "Личный турнир",
      description: "16 игроков, 30 туров — свой состав и тактика",
      stat: playerTournamentStatusLabel(playerTournamentCurrent?.status, playerTournamentCurrent?.queue_position),
      rightLabel: "16 игроков",
    },
    {
      path: "/play/penalty", Icon: IconGoal, badgeClass: "bg-rarity-legendary", title: "Пенальти",
      description: "Серия пенальти против бота или друга",
      stat: `Рейтинг: ${penaltyStats?.penalty_rating ?? user?.penalty_rating ?? 0}`, limitKey: "penalty",
    },
    {
      path: "/play/fut-draft", Icon: IconStar, badgeClass: "bg-rarity-legendary", title: "FUT Draft",
      description: "Временный состав из случайных карт и серия матчей", noLimit: true,
    },
  ];
  const miniGames: GameDef[] = [
    {
      path: "/play/memory", Icon: IconBrain, badgeClass: "bg-accent-cyan", title: "Memory Sequence",
      description: "Запомни и повтори последовательность символов",
      stat: `Рекорд: ${user?.memory_best_score ?? 0}`, limitKey: "memory",
    },
    {
      path: "/play/saboteur", Icon: IconProfile, badgeClass: "bg-rarity-common", title: "Футбольный фанат",
      description: "Проберись сквозь стюардов к любимому игроку", limitKey: "saboteur",
    },
    {
      path: "/play/free-kick", Icon: IconTarget, badgeClass: "bg-accent-lime", title: "Штрафной удар",
      description: "Останови шкалу силы в нужный момент", limitKey: "free_kick",
    },
    {
      path: "/play/hangman", Icon: IconHelp, badgeClass: "bg-rarity-epic", title: "Футбольные буквы",
      description: "Угадай футболиста или термин по буквам", limitKey: "hangman",
    },
    {
      path: "/play/pairs", Icon: IconCard, badgeClass: "bg-rarity-rare", title: "Найди пару",
      description: "Переворачивай карточки и находи одинаковых футболистов", limitKey: "pairs",
    },
  ];

  const exhausted = (g: GameDef) => !!limits && !!g.limitKey && limits[g.limitKey] === 0;
  // Games with plays left first; used-up ones sink to the bottom with the
  // time they come back, so the top of the list is always playable.
  const ordered = (games: GameDef[]) => [...games].sort((a, b) => Number(exhausted(a)) - Number(exhausted(b)));

  const open = (g: GameDef) => {
    setLastGame(g.path);
    navigate(g.path);
  };
  const last = [...matches, ...miniGames].find((g) => g.path === lastGame);

  const renderCard = (g: GameDef) => (
    <GameCard
      key={g.path}
      game={g}
      onClick={() => open(g)}
      remaining={g.limitKey ? limits?.[g.limitKey] : undefined}
      limit={limits?.hourly_limit}
      resetsAt={g.limitKey ? limits?.resets_at?.[g.limitKey] : undefined}
    />
  );

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

      {last && !exhausted(last) && (
        <button
          onClick={() => open(last)}
          className="flex items-center gap-3 rounded-2xl bg-floodlight p-3 text-left text-bg-base active:scale-[0.98]"
        >
          <last.Icon size={20} />
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-semibold uppercase tracking-wider opacity-70">Продолжить</span>
            <span className="block font-display text-sm font-bold">{last.title}</span>
          </span>
          <IconChevronRight size={18} />
        </button>
      )}

      <Section title="Матчи">{ordered(matches).map(renderCard)}</Section>
      <Section title="Мини-игры">{ordered(miniGames).map(renderCard)}</Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-mist">{title}</h2>
      {children}
    </section>
  );
}

function GameCard({
  game, onClick, remaining, limit, resetsAt,
}: {
  game: GameDef;
  onClick: () => void;
  remaining?: number;
  limit?: number;
  resetsAt?: string;
}) {
  const { Icon } = game;
  const used = remaining === 0;
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98] ${used ? "opacity-60" : ""}`}
    >
      <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${game.badgeClass}`}>
        <Icon size={22} className="text-bg-base" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">{game.title}</p>
        <p className="mt-0.5 text-[11px] leading-tight text-ink-mist">{game.description}</p>
        {game.stat && <p className="mt-1 font-mono text-[10px] text-ink-mist">{game.stat}</p>}
      </div>
      <div className="shrink-0 text-right">
        {game.rightLabel !== undefined ? (
          <p className="text-[10px] text-ink-mist-dim">{game.rightLabel}</p>
        ) : remaining !== undefined && limit !== undefined ? (
          used ? (
            <>
              <p className="font-mono text-sm font-bold text-red-400">0/{limit}</p>
              <p className="text-[10px] text-ink-mist-dim">{resetsAt ? `снова в ${formatClock(resetsAt)}` : "лимит на час"}</p>
            </>
          ) : (
            <>
              <p className="font-mono text-sm font-bold text-ink-chalk">{remaining}/{limit}</p>
              <p className="text-[10px] text-ink-mist-dim">осталось в час</p>
            </>
          )
        ) : game.noLimit ? (
          <p className="text-[10px] text-ink-mist-dim">Платный вход</p>
        ) : (
          <Skeleton className="h-8 w-12" />
        )}
      </div>
    </button>
  );
}
