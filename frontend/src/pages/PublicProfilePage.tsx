import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft } from "@/components/icons";
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
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-sm text-accent-lime">
        <IconChevronLeft size={16} />
        Назад
      </button>

      <section className="flex flex-col items-center gap-2 rounded-3xl bg-bg-surface p-5 text-center">
        <img
          src={profile.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt="avatar"
          className="h-20 w-20 rounded-full ring-2 ring-accent-lime object-cover"
        />
        <p className="font-display text-xl font-bold text-ink-chalk">{profile.first_name} {profile.last_name}</p>
        {profile.username && <p className="text-sm text-ink-mist">@{profile.username}</p>}
        <p className="text-xs text-ink-mist-dim">С нами с {new Date(profile.created_at).toLocaleDateString("ru-RU")}</p>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="grid grid-cols-2 gap-y-4">
          <Stat label="Уровень" value={profile.level} accentClass="text-accent-cyan" />
          <Stat label="Рейтинг Arena" value={profile.arena_rating} />
          <Stat label="Уникальных карточек" value={profile.unique_cards} />
          <Stat label="Всего карточек" value={profile.total_cards} />
          <Stat label="Место в рейтинге" value={`#${profile.arena_rank}`} accentClass="bg-floodlight bg-clip-text text-transparent" />
          <Stat label="Матчи П/Н/П" value={`${profile.matches_won}/${profile.matches_drawn}/${profile.matches_lost}`} />
        </div>
      </section>

      {profile.rarest_card && (
        <section className="flex items-center gap-3 rounded-2xl bg-rarity-legendary/10 p-4">
          <img
            src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={profile.rarest_card.display_name}
            className="h-16 w-16 rounded-xl object-cover"
          />
          <div>
            <p className="text-[11px] text-rarity-legendary">Самая редкая карточка</p>
            <p className="font-display text-sm font-bold text-ink-chalk">{profile.rarest_card.display_name}</p>
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value, accentClass }: { label: string; value: string | number; accentClass?: string }) {
  return (
    <div>
      <p className={`font-mono text-2xl font-bold ${accentClass ?? "text-ink-chalk"}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-ink-mist">{label}</p>
    </div>
  );
}
