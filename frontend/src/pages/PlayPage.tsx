import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchArenaStats } from "@/api/matches";
import { useAuthStore } from "@/store/authStore";

export default function PlayPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const { data: arenaStats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-slate-100">Играть</h1>
        <button
          onClick={() => navigate("/ranking")}
          className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-amber-300 active:scale-95"
        >
          <span>🏆</span>
          <span>Рейтинг</span>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => navigate("/play/memory")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-cyan-600 to-blue-700 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">🧠</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Memory Sequence</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Запомни и повтори последовательность символов</p>
          <p className="mt-2 text-[10px] text-white/70">Рекорд: {user?.memory_best_score ?? 0}</p>
          <p className="mt-0.5 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>

        <button
          onClick={() => navigate("/play/arena")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-600 to-teal-700 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">⚽</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Card Arena</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Собери состав 4-3-3 и сыграй матч</p>
          <p className="mt-2 text-[10px] text-white/70">
            Рейтинг: {arenaStats?.arena_rating ?? user?.arena_rating ?? 1000}
          </p>
          <p className="mt-0.5 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>

        <button
          onClick={() => navigate("/play/saboteur")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-slate-600 to-slate-900 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">💣</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Футбольный сапёр</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Открывай ячейки, копи монеты, берегись бомбы</p>
          <p className="mt-2 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>

        <button
          onClick={() => navigate("/play/penalty")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-orange-600 to-red-700 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">🥅</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Пенальти</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Серия пенальти против бота</p>
          <p className="mt-2 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>

        <button
          onClick={() => navigate("/play/free-kick")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-lime-600 to-green-700 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">🎯</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Штрафной удар</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Останови шкалу силы в нужный момент</p>
          <p className="mt-2 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>

        <button
          onClick={() => navigate("/play/hangman")}
          className="overflow-hidden rounded-2xl bg-gradient-to-br from-fuchsia-700 to-purple-900 p-4 text-left active:scale-[0.98]"
        >
          <p className="text-2xl">🪢</p>
          <p className="mt-1.5 font-display text-sm font-bold text-white">Футбольная виселица</p>
          <p className="mt-1 text-[11px] leading-tight text-white/80">Угадай футболиста или термин по буквам</p>
          <p className="mt-2 text-[10px] text-white/50">До 3 попыток в час</p>
        </button>
      </div>
    </div>
  );
}
