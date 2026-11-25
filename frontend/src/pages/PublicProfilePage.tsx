import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Skeleton } from "@/components/common/Skeleton";
import { PublicMyPlayer } from "@/components/myPlayer/MyPlayerEntry";
import FriendButton from "@/components/profile/FriendButton";
import { ModeRecords, ProfileCard } from "@/components/profile/ProfileCard";
import { IconChevronLeft, IconGift, IconSwap } from "@/components/icons";
import { fetchPublicProfile } from "@/api/profile";
import AcademyShowcase from "@/components/path/AcademyShowcase";
import GiftShelf from "@/components/profile/GiftShelf";
import { ProfileFeed, RespectBar } from "@/components/profile/ProfileSocial";
import { ShowcaseRow } from "@/components/profile/Showcase";
import { cardStats, modeRows } from "@/lib/profileStats";
import { useAuthStore } from "@/store/authStore";
import type { UserPublic } from "@/types";

import tileAlbum from "@/assets/profile/tile_album.webp";
import tileGifts from "@/assets/profile/tile_rewards.webp";
import tileHall from "@/assets/profile/tile_hall.webp";
import tileShowcase from "@/assets/profile/tile_showcase.webp";

type Panel = "showcase" | "gifts";

export default function PublicProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const me = useAuthStore((s) => s.user);
  const [panel, setPanel] = useState<Panel | null>(null);
  const { data: profile, isLoading } = useQuery({
    queryKey: ["public-profile", userId],
    queryFn: () => fetchPublicProfile(Number(userId)),
  });

  if (isLoading) return <ProfileSkeleton />;
  if (!profile) return null;
  const isMe = me?.id === profile.id;
  const asTarget: UserPublic = {
    id: profile.id, username: profile.username, first_name: profile.first_name,
    last_name: profile.last_name, avatar_url: profile.avatar_url, level: profile.level,
    arena_rating: profile.arena_rating, created_at: profile.created_at, active_badge: profile.active_badge,
  };
  const hasShowcase = !!profile.showcase?.length;
  const open: Panel = panel ?? (hasShowcase ? "showcase" : "gifts");

  return (
    <div className="flex flex-col gap-4">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-sm text-accent-lime">
        <IconChevronLeft size={16} />
        Назад
      </button>

      <ProfileCard
        rank={profile.league_rank}
        rankLabel={profile.league?.name ?? "рейтинг"}
        rankImage={profile.league?.image_path}
        avatarUrl={profile.avatar_url}
        cosmetics={profile.cosmetics}
        name={`${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim()}
        badge={profile.active_badge}
        subtitle={`${profile.username ? `@${profile.username} · ` : ""}с нами с ${new Date(profile.created_at).toLocaleDateString("ru-RU")}`}
        clubPass={profile.club_pass_active}
        club={profile.club}
        lastSeenAt={profile.last_seen_at}
        topCard={profile.rarest_card}
        onTopCard={() => navigate(`/users/${profile.id}/album`)}
        userId={profile.id}
        isMe={isMe}
        stats={cardStats(profile)}
        details={<ModeRecords rows={modeRows(profile)} />}
        actions={
          <>
            {!isMe && <RespectBar userId={profile.id} isMe={false} />}
            {!isMe && (
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => navigate("/trades/new", { state: { target: asTarget } })}
                  className="flex items-center justify-center gap-1.5 rounded-full bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
                >
                  <IconSwap size={14} />
                  Обмен
                </button>
                <button
                  onClick={() => navigate("/gifts", { state: { giftTo: asTarget } })}
                  className="flex items-center justify-center gap-1.5 rounded-full bg-rarity-epic/25 px-3 py-2 text-xs font-bold text-fuchsia-200 active:scale-95"
                  data-testid="gift-to-user"
                >
                  <IconGift size={14} />
                  Подарить
                </button>
                <span className="col-span-2 flex justify-center">
                  <FriendButton userId={profile.id} className="w-full whitespace-nowrap" />
                </span>
              </div>
            )}
          </>
        }
      />

      {/* Everything else in one row of tiles; the two that open in place share one panel. */}
      <div className="grid grid-cols-4 gap-2">
        <PlaceTile art={tileHall} title="Зал славы" onClick={() => navigate(`/users/${profile.id}/hall`)} testId="open-hall" />
        <PlaceTile
          art={tileShowcase}
          title="Витрина"
          active={open === "showcase"}
          onClick={() => setPanel("showcase")}
        />
        <PlaceTile art={tileGifts} title="Подарки" active={open === "gifts"} onClick={() => setPanel("gifts")} />
        <PlaceTile art={tileAlbum} title="Альбом" onClick={() => navigate(`/users/${profile.id}/album`)} testId="open-friend-album" />
      </div>
      {open === "showcase" &&
        (hasShowcase ? (
          <ShowcaseRow cards={profile.showcase!} />
        ) : (
          <p className="rounded-2xl bg-bg-surface p-4 text-center text-caption text-ink-mist">Витрина пока пустая</p>
        ))}
      {open === "gifts" && <GiftShelf userId={profile.id} />}

      <ProfileFeed userId={profile.id} />
      <PublicMyPlayer userId={profile.id} />
      <AcademyShowcase userId={profile.id} />
    </div>
  );
}

function PlaceTile({ art, emoji, title, active, onClick, testId }: {
  art?: string | null; emoji?: string; title: string; active?: boolean; onClick: () => void; testId?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-2xl border px-1 pb-2 pt-1.5 text-center active:scale-[0.95] ${
        active ? "border-amber-300/70 bg-amber-300/10" : "border-white/10 bg-bg-surface"
      }`}
      data-testid={testId}
    >
      {art ? (
        <img src={art} alt="" className="pointer-events-none h-14 w-14 rounded-lg object-contain drop-shadow-[0_4px_6px_rgba(0,0,0,0.55)]" />
      ) : (
        <span className="flex h-14 w-14 items-center justify-center text-4xl drop-shadow">{emoji}</span>
      )}
      <span className="text-[11px] font-bold leading-tight text-ink-chalk">{title}</span>
    </button>
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
