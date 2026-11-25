import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { fetchPublicProfile } from "@/api/profile";
import AlbumTab from "@/components/collection/AlbumTab";
import { IconChevronLeft, IconSwap } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";
import type { UserPublic } from "@/types";

/** Another player's album, read-only: leaf through it and offer a trade. */
export default function FriendAlbumPage() {
  const { userId } = useParams<{ userId: string }>();
  const id = Number(userId);
  const navigate = useNavigate();
  const me = useAuthStore((s) => s.user);
  const { data: profile } = useQuery({ queryKey: ["public-profile", userId], queryFn: () => fetchPublicProfile(id) });

  const offerTrade = () => {
    if (!profile) return;
    const target: UserPublic = {
      id: profile.id, username: profile.username, first_name: profile.first_name,
      last_name: profile.last_name, avatar_url: profile.avatar_url, level: profile.level,
      arena_rating: profile.arena_rating, created_at: profile.created_at, active_badge: profile.active_badge,
    };
    navigate("/trades/new", { state: { target } });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate(-1)} aria-label="Назад" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-bg-surface active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <p className="min-w-0 flex-1 truncate font-display text-lg font-bold text-ink-chalk">
          {profile ? `Альбом · ${`${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim() || "игрок"}` : "Альбом"}
        </p>
        {profile && me?.id !== profile.id && (
          <button
            onClick={offerTrade}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
          >
            <IconSwap size={14} />
            Обмен
          </button>
        )}
      </div>
      <AlbumTab ownerId={id} />
    </div>
  );
}
