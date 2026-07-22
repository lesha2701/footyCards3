import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import LoadingScreen from "@/components/common/LoadingScreen";
import { fetchPublicProfile } from "@/api/profile";
import { staticUrl } from "@/lib/api";

export default function PublicProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { data: profile, isLoading } = useQuery({
    queryKey: ["public-profile", userId],
    queryFn: () => fetchPublicProfile(Number(userId)),
  });

  if (isLoading) return <LoadingScreen />;
  if (!profile) return null;

  return (
    <div className="flex flex-col gap-5">
      <button onClick={() => navigate(-1)} className="self-start text-sm text-accent">← Назад</button>

      <section className="flex flex-col items-center gap-2 rounded-3xl border border-white/5 bg-bg-surface p-5 text-center">
        <img
          src={profile.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt="avatar"
          className="h-20 w-20 rounded-full border-2 border-accent object-cover"
        />
        <p className="font-display text-xl font-bold text-slate-100">{profile.first_name} {profile.last_name}</p>
        {profile.username && <p className="text-sm text-slate-400">@{profile.username}</p>}
        <p className="text-xs text-slate-500">С нами с {new Date(profile.created_at).toLocaleDateString("ru-RU")}</p>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <Stat label="Уровень" value={`⭐ ${profile.level}`} />
        <Stat label="Рейтинг Arena" value={profile.arena_rating} />
        <Stat label="Уникальных карточек" value={profile.unique_cards} />
        <Stat label="Всего карточек" value={profile.total_cards} />
        <Stat label="Место в рейтинге" value={`#${profile.arena_rank}`} />
        <Stat label="Матчи П/Н/П" value={`${profile.matches_won}/${profile.matches_drawn}/${profile.matches_lost}`} />
      </section>

      {profile.rarest_card && (
        <section className="flex items-center gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4">
          <img
            src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={profile.rarest_card.display_name}
            className="h-16 w-16 rounded-xl object-cover"
          />
          <div>
            <p className="text-[11px] text-amber-400">Самая редкая карточка</p>
            <p className="font-display text-sm font-bold text-slate-100">{profile.rarest_card.display_name}</p>
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface px-3 py-2.5">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-display text-base font-bold text-slate-100">{value}</p>
    </div>
  );
}
