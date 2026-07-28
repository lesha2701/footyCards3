import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchArenaStats } from "@/api/matches";
import { IconBall, IconBrain, IconGoal, IconHelp, IconProfile, IconTarget, IconTrophy, type IconProps } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";

export default function PlayPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: arenaStats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });

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

      <div className="grid grid-cols-2 gap-3">
        <GameCard
          onClick={() => navigate("/play/memory")}
          Icon={IconBrain}
          badgeClass="bg-accent-cyan"
          title="Memory Sequence"
          description="Запомни и повтори последовательность символов"
          stat={`Рекорд: ${user?.memory_best_score ?? 0}`}
        />

        <GameCard
          onClick={() => navigate("/play/arena")}
          Icon={IconBall}
          badgeClass="bg-accent-green"
          title="Card Arena"
          description="Собери состав 4-3-3 и сыграй матч"
          stat={`Рейтинг: ${arenaStats?.arena_rating ?? user?.arena_rating ?? 1000}`}
        />

        <GameCard
          onClick={() => navigate("/play/saboteur")}
          Icon={IconProfile}
          badgeClass="bg-rarity-common"
          title="Футбольный сапёр"
          description="Проберись сквозь стюардов к любимому игроку"
        />

        <GameCard
          onClick={() => navigate("/play/penalty")}
          Icon={IconGoal}
          badgeClass="bg-rarity-legendary"
          title="Пенальти"
          description="Серия пенальти против бота"
        />

        <GameCard
          onClick={() => navigate("/play/free-kick")}
          Icon={IconTarget}
          badgeClass="bg-accent-lime"
          title="Штрафной удар"
          description="Останови шкалу силы в нужный момент"
        />

        <GameCard
          onClick={() => navigate("/play/hangman")}
          Icon={IconHelp}
          badgeClass="bg-rarity-epic"
          title="Футбольная виселица"
          description="Угадай футболиста или термин по буквам"
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
}: {
  onClick: () => void;
  Icon: (props: IconProps) => JSX.Element;
  badgeClass: string;
  title: string;
  description: string;
  stat?: string;
}) {
  return (
    <button onClick={onClick} className="flex flex-col rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]">
      <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${badgeClass}`}>
        <Icon size={20} className="text-bg-base" />
      </span>
      <p className="mt-2.5 font-display text-sm font-bold text-ink-chalk">{title}</p>
      <p className="mt-1 text-[11px] leading-tight text-ink-mist">{description}</p>
      <div className="mt-auto pt-2">
        {stat && <p className="font-mono text-[10px] text-ink-mist">{stat}</p>}
        <p className="mt-0.5 text-[10px] text-ink-mist-dim">До 3 попыток в час</p>
      </div>
    </button>
  );
}
