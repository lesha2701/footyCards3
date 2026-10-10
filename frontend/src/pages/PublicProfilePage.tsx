import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import LoadingScreen from "@/components/common/LoadingScreen";
import { UserBadge } from "@/components/common/UserBadge";
import FriendButton from "@/components/profile/FriendButton";
import { IconChevronLeft, IconSwap } from "@/components/icons";
import { fetchPublicProfile } from "@/api/profile";
import { staticUrl } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { UserPublic } from "@/types";

export default function PublicProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const me = useAuthStore((s) => s.user);
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
        <p className="flex items-center gap-1.5 font-display text-xl font-bold text-ink-chalk">
          {profile.first_name} {profile.last_name}
          <UserBadge badge={profile.active_badge} />
        </p>
        {profile.username && <p className="text-sm text-ink-mist">@{profile.username}</p>}
        <p className="text-xs text-ink-mist-dim">С нами с {new Date(profile.created_at).toLocaleDateString("ru-RU")}</p>
        {me?.id !== profile.id && (
          <button
            onClick={() => {
              const target: UserPublic = {
                id: profile.id, username: profile.username, first_name: profile.first_name,
                last_name: profile.last_name, avatar_url: profile.avatar_url, level: profile.level,
                arena_rating: profile.arena_rating, created_at: profile.created_at, active_badge: profile.active_badge,
              };
              navigate("/trades/new", { state: { target } });
            }}
            className="mt-2 flex items-center gap-1.5 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
          >
            <IconSwap size={14} />
            Предложить обмен
          </button>
        )}
        {me?.id !== profile.id && <FriendButton userId={profile.id} />}
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="grid grid-cols-2 gap-y-4">
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
