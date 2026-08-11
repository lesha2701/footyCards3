import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchGameLimits, fetchPenaltyStats } from "@/api/games";
import { fetchArenaStats } from "@/api/matches";
import { fetchTacticoStats } from "@/api/tactico";
import {
  IconBall,
  IconBrain,
  IconCard,
  IconFlagCheckered,
  IconGoal,
  IconHelp,
  IconProfile,
  IconTarget,
  IconTrophy,
  type IconProps,
} from "@/components/icons";
import { useAuthStore } from "@/store/authStore";

export default function PlayPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: arenaStats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });
  const { data: tacticoStats } = useQuery({ queryKey: ["tactico-stats"], queryFn: fetchTacticoStats });
  const { data: penaltyStats } = useQuery({ queryKey: ["penalty-stats"], queryFn: fetchPenaltyStats });
  const { data: limits } = useQuery({ queryKey: ["game-limits"], queryFn: fetchGameLimits });

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

      <div className="flex flex-col gap-3">
        <GameCard
          onClick={() => navigate("/play/arena")}
          Icon={IconBall}
          badgeClass="bg-accent-green"
          title="Card Arena"
          description="Собери состав 4-3-3 и сыграй матч"
          stat={`Рейтинг: ${arenaStats?.arena_rating ?? user?.arena_rating ?? 1000}`}
          remaining={limits?.arena}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/tactico")}
          Icon={IconFlagCheckered}
          badgeClass="bg-rarity-rare"
          title="Тактико"
          description="Собери состав из 11 карт и переиграй соперника раунд за раундом"
          stat={`Рейтинг: ${tacticoStats?.tactics_rating ?? user?.tactics_rating ?? 0}`}
          remaining={limits?.tactico}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/memory")}
          Icon={IconBrain}
          badgeClass="bg-accent-cyan"
          title="Memory Sequence"
          description="Запомни и повтори последовательность символов"
          stat={`Рекорд: ${user?.memory_best_score ?? 0}`}
          remaining={limits?.memory}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/saboteur")}
          Icon={IconProfile}
          badgeClass="bg-rarity-common"
          title="Футбольный фанат"
          description="Проберись сквозь стюардов к любимому игроку"
          remaining={limits?.saboteur}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/penalty")}
          Icon={IconGoal}
          badgeClass="bg-rarity-legendary"
          title="Пенальти"
          description="Серия пенальти против бота или друга"
          stat={`Рейтинг: ${penaltyStats?.penalty_rating ?? user?.penalty_rating ?? 0}`}
          remaining={limits?.penalty}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/free-kick")}
          Icon={IconTarget}
          badgeClass="bg-accent-lime"
          title="Штрафной удар"
          description="Останови шкалу силы в нужный момент"
          remaining={limits?.free_kick}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/hangman")}
          Icon={IconHelp}
          badgeClass="bg-rarity-epic"
          title="Футбольные буквы"
          description="Угадай футболиста или термин по буквам"
          remaining={limits?.hangman}
          limit={limits?.hourly_limit}
        />

        <GameCard
          onClick={() => navigate("/play/pairs")}
          Icon={IconCard}
          badgeClass="bg-rarity-rare"
          title="Найди пару"
          description="Переворачивай карточки и находи одинаковых футболистов"
          remaining={limits?.pairs}
          limit={limits?.hourly_limit}
        />
      </div>
    </div>
  );
}

function GameCard({
  onClick,
  Icon,
  badgeClass,
  title,
  description,
  stat,
  remaining,
  limit,
}: {
  onClick: () => void;
  Icon: (props: IconProps) => JSX.Element;
  badgeClass: string;
  title: string;
  description: string;
  stat?: string;
  remaining?: number;
  limit?: number;
}) {
  return (
    <button onClick={onClick} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]">
      <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${badgeClass}`}>
        <Icon size={22} className="text-bg-base" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        <p className="mt-0.5 text-[11px] leading-tight text-ink-mist">{description}</p>
        {stat && <p className="mt-1 font-mono text-[10px] text-ink-mist">{stat}</p>}
      </div>
      <div className="shrink-0 text-right">
        {remaining !== undefined && limit !== undefined ? (
          <>
            <p className={`font-mono text-sm font-bold ${remaining > 0 ? "text-ink-chalk" : "text-red-400"}`}>
              {remaining}/{limit}
            </p>
            <p className="text-[10px] text-ink-mist-dim">осталось в час</p>
          </>
        ) : (
          <p className="text-[10px] text-ink-mist-dim">...</p>
        )}
      </div>
    </button>
  );
}
