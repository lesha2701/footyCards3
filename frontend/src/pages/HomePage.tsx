import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { fetchPacks } from "@/api/packs";
import { fetchMyProfile } from "@/api/profile";
import { Skeleton } from "@/components/common/Skeleton";
import { staticUrl } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export default function HomePage() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();

  const { data: calendar } = useQuery({ queryKey: ["daily-reward-calendar"], queryFn: fetchDailyRewardCalendar });
  const { data: packs, isLoading: packsLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });

  return (
    <div className="flex flex-col gap-5">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-600/30 via-bg-surface to-purple-700/20 p-5">
        <p className="text-sm text-slate-300">С возвращением,</p>
        <p className="font-display text-2xl font-bold text-white">{user?.first_name ?? user?.username ?? "игрок"}!</p>
        <div className="mt-4 flex items-center gap-4">
          <div className="rounded-2xl bg-black/30 px-4 py-2">
            <p className="text-[11px] text-slate-400">Баланс</p>
            <p className="font-display text-xl font-bold text-amber-300">🪙 {user?.balance ?? 0}</p>
          </div>
          <div className="rounded-2xl bg-black/30 px-4 py-2">
            <p className="text-[11px] text-slate-400">Уровень</p>
            <p className="font-display text-xl font-bold text-cyan-300">⭐ {user?.level ?? 1}</p>
          </div>
        </div>
      </section>

      {calendar && !calendar.already_claimed_today && (
        <button
          onClick={() => navigate("/profile")}
          className="flex items-center justify-between rounded-2xl bg-gradient-to-r from-amber-500 to-orange-600 px-4 py-3 text-left active:scale-[0.98]"
        >
          <div>
            <p className="font-display text-sm font-bold text-white">🎁 Ежедневная награда готова!</p>
            <p className="text-xs text-white/80">День {calendar.current_streak} — забери в профиле</p>
          </div>
          <span className="text-2xl">→</span>
        </button>
      )}

      <section className="grid grid-cols-3 gap-3">
        <QuickAction icon="📦" label="Паки" onClick={() => navigate("/packs")} />
        <QuickAction icon="🎮" label="Играть" onClick={() => navigate("/play")} />
        <QuickAction icon="🗂️" label="Карточки" onClick={() => navigate("/collection")} />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-slate-100">Доступные паки</h2>
          <button onClick={() => navigate("/packs")} className="text-sm text-accent">Все паки →</button>
        </div>
        {packsLoading ? (
          <div className="flex gap-3 overflow-hidden">
            <Skeleton className="h-40 w-32 shrink-0 rounded-2xl" />
            <Skeleton className="h-40 w-32 shrink-0 rounded-2xl" />
          </div>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {packs?.map((pack) => (
              <button
                key={pack.id}
                onClick={() => navigate("/packs")}
                className="flex w-32 shrink-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-bg-surface active:scale-95"
              >
                <img src={staticUrl(pack.image_path ?? undefined)} alt={pack.name} className="h-24 w-full object-cover" />
                <div className="p-2 text-left">
                  <p className="truncate font-display text-xs font-bold text-slate-100">{pack.name}</p>
                  <p className="text-[11px] text-amber-300">🪙 {pack.price}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {profile && (
        <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
          <h2 className="mb-3 font-display text-base font-bold text-slate-100">Твоя статистика</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="Уникальных карточек" value={profile.unique_cards} />
            <Stat label="Всего карточек" value={profile.total_cards} />
            <Stat label="Паков открыто" value={profile.packs_opened} />
            <Stat label="Место в рейтинге" value={`#${profile.arena_rank}`} />
          </div>
        </section>
      )}
    </div>
  );
}

function QuickAction({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-1.5 rounded-2xl border border-white/5 bg-bg-surface py-4 active:scale-95"
    >
      <span className="text-2xl">{icon}</span>
      <span className="text-xs font-medium text-slate-300">{label}</span>
    </button>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-black/20 px-3 py-2">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-display text-lg font-bold text-slate-100">{value}</p>
    </div>
  );
}
