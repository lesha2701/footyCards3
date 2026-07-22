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
      <h1 className="font-display text-2xl font-bold text-slate-100">Играть</h1>

      <button
        onClick={() => navigate("/play/memory")}
        className="overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-600 to-blue-700 p-5 text-left active:scale-[0.98]"
      >
        <p className="text-3xl">🧠</p>
        <p className="mt-2 font-display text-lg font-bold text-white">Memory Sequence</p>
        <p className="text-sm text-white/80">Запомни и повтори последовательность футбольных символов</p>
        <p className="mt-2 text-xs text-white/70">Рекорд: {user?.memory_best_score ?? 0}</p>
      </button>

      <button
        onClick={() => navigate("/play/arena")}
        className="overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-600 to-teal-700 p-5 text-left active:scale-[0.98]"
      >
        <p className="text-3xl">⚽</p>
        <p className="mt-2 font-display text-lg font-bold text-white">Card Arena</p>
        <p className="text-sm text-white/80">Собери состав 4-3-3 и сыграй матч</p>
        <p className="mt-2 text-xs text-white/70">
          Рейтинг: {arenaStats?.arena_rating ?? user?.arena_rating ?? 1000} · Энергия: {arenaStats?.match_energy ?? "—"}/{arenaStats?.max_energy ?? "—"}
        </p>
      </button>
    </div>
  );
}
