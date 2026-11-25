import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { Skeleton } from "@/components/common/Skeleton";
import { PublicMyPlayer } from "@/components/myPlayer/MyPlayerEntry";
import FriendButton from "@/components/profile/FriendButton";
import { ModeRecords, ProfileCard } from "@/components/profile/ProfileCard";
import { IconChevronLeft, IconSwap } from "@/components/icons";
import { fetchPublicProfile } from "@/api/profile";
import AcademyShowcase from "@/components/path/AcademyShowcase";
import GiftShelf from "@/components/profile/GiftShelf";
import { ProfileFeed, RespectBar } from "@/components/profile/ProfileSocial";
import { ShowcaseRow } from "@/components/profile/Showcase";
import { staticUrl } from "@/lib/api";
import { cardStats, modeRows } from "@/lib/profileStats";
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

  if (isLoading) return <ProfileSkeleton />;
  if (!profile) return null;
  const isMe = me?.id === profile.id;

  return (
    <div className="flex flex-col gap-5">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-sm text-accent-lime">
        <IconChevronLeft size={16} />
        Назад
      </button>

      <ProfileCard
        rank={profile.league_rank}
        rankLabel="рейтинг"
        avatarUrl={profile.avatar_url}
        cosmetics={profile.cosmetics}
        name={`${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim()}
        badge={profile.active_badge}
        subtitle={`${profile.username ? `@${profile.username} · ` : ""}с нами с ${new Date(profile.created_at).toLocaleDateString("ru-RU")}`}
        clubPass={profile.club_pass_active}
        userId={profile.id}
        isMe={isMe}
        stats={cardStats(profile)}
        details={<ModeRecords rows={modeRows(profile)} />}
        actions={
          <>
            <RespectBar userId={profile.id} isMe={isMe} />
            {!isMe && (
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    const target: UserPublic = {
                      id: profile.id, username: profile.username, first_name: profile.first_name,
                      last_name: profile.last_name, avatar_url: profile.avatar_url, level: profile.level,
                      arena_rating: profile.arena_rating, created_at: profile.created_at, active_badge: profile.active_badge,
                    };
                    navigate("/trades/new", { state: { target } });
                  }}
                  className="flex items-center justify-center gap-1.5 rounded-full bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
                >
                  <IconSwap size={14} />
                  Обмен
                </button>
                <FriendButton userId={profile.id} className="whitespace-nowrap !px-2" />
                <button
                  onClick={() => navigate(`/users/${profile.id}/album`)}
                  className="col-span-2 flex items-center justify-center gap-1.5 rounded-full bg-amber-300/15 px-4 py-2 text-xs font-bold text-amber-200 active:scale-95"
                  data-testid="open-friend-album"
                >
                  📖 Смотреть альбом
                </button>
              </div>
            )}
          </>
        }
      />

      <button
        onClick={() => navigate(`/users/${profile.id}/hall`)}
        className="relative flex items-center gap-3 overflow-hidden rounded-2xl border border-amber-300/30 bg-gradient-to-r from-[#3b2414] via-[#1a3628] to-[#0c1712] p-4 text-left active:scale-[0.98]"
        data-testid="open-hall"
      >
        <span className="text-4xl drop-shadow">🏛</span>
        <span className="min-w-0 flex-1">
          <span className="block font-display text-base font-bold text-amber-100">Зал славы</span>
          <span className="block text-caption text-ink-mist">Картины, кубки и подарки — в одной комнате</span>
        </span>
        <span className="rounded-full bg-amber-300/20 px-3 py-1.5 text-micro font-bold text-amber-100">Войти</span>
      </button>

      {!!profile.showcase?.length && <ShowcaseRow cards={profile.showcase} />}

      <GiftShelf userId={profile.id} />

      <ProfileFeed userId={profile.id} />

      <PublicMyPlayer userId={profile.id} />

      <AcademyShowcase userId={profile.id} />

      {profile.rarest_card && (
        <section className="flex items-center gap-3 rounded-2xl bg-rarity-legendary/10 p-4">
          <img decoding="async" loading="lazy"
            src={staticUrl(profile.rarest_card.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
            alt={profile.rarest_card.display_name}
            className="h-16 w-16 rounded-xl object-cover"
          />
          <div>
            <p className="text-caption text-rarity-legendary">Самая редкая карточка</p>
            <p className="font-display text-sm font-bold text-ink-chalk">{profile.rarest_card.display_name}</p>
          </div>
        </section>
      )}
    </div>
  );
}

/** The page's own shape while it loads: the header with the avatar, the
 * stats grid and a card row — not a full-screen splash over the app. */
function ProfileSkeleton() {
  return (
    <div className="flex flex-col gap-5" aria-busy="true" aria-label="Загрузка профиля">
      <Skeleton className="h-5 w-16" />
      <section className="flex flex-col items-center gap-2 rounded-3xl bg-bg-surface p-5">
        <Skeleton className="h-20 w-20 !rounded-full" />
        <Skeleton className="mt-1 h-6 w-40" />
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-32" />
        <Skeleton className="mt-2 h-8 w-44 !rounded-full" />
      </section>
      <section className="grid grid-cols-2 gap-x-4 gap-y-4 rounded-2xl bg-bg-surface p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-14" />
          </div>
        ))}
      </section>
      <Skeleton className="h-40 rounded-2xl" />
    </div>
  );
}
