import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createClubPost, deleteClubPost, fetchClubWall, pinClubPost } from "@/api/clubFeatures";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChat, IconChevronLeft, IconFlag, IconTrash } from "@/components/icons";
import { CLUB_ROLE_LABELS } from "@/lib/clubRoles";
import { formatGameError } from "@/lib/errors";
import { formatCountdown } from "@/lib/format";
import { hapticNotify } from "@/lib/telegram";
import type { ClubWall } from "@/types";

const timeLabel = (iso: string) => {
  const d = new Date(iso);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
};

/** «Стена клуба»: сообщения участников, объявления капитана (бот присылает их всем), закреп. */
export default function ClubWallPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: wall, isLoading } = useQuery({
    queryKey: ["clubs", "wall"],
    queryFn: fetchClubWall,
    refetchInterval: 15_000,
  });
  const [text, setText] = useState("");
  const [announce, setAnnounce] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onWall = (data: ClubWall) => {
    queryClient.setQueryData(["clubs", "wall"], data);
    queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    setError(null);
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось отправить"));
  const post = useMutation({
    mutationFn: () => createClubPost(text, announce),
    onSuccess: (data) => { onWall(data); setText(""); setAnnounce(false); hapticNotify("success"); },
    onError,
  });
  const remove = useMutation({ mutationFn: deleteClubPost, onSuccess: onWall, onError });
  const pin = useMutation({ mutationFn: pinClubPost, onSuccess: onWall, onError });

  if (isLoading || !wall) return <ListSkeleton />;
  const cooldown = wall.announce_cooldown_seconds;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Стена клуба</h1>
      </div>

      <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={500}
          rows={3}
          placeholder={announce ? "Объявление для всего клуба..." : "Напиши клубу..."}
          className="resize-none rounded-xl bg-black/20 px-3 py-2 text-sm text-ink-chalk outline-none"
        />
        <div className="flex items-center gap-2">
          {wall.can_announce && (
            <label className={`flex items-center gap-1.5 text-xs ${cooldown > 0 ? "text-ink-mist-dim" : "text-ink-mist"}`}>
              <input type="checkbox" checked={announce} disabled={cooldown > 0} onChange={(e) => setAnnounce(e.target.checked)} />
              {cooldown > 0 ? `Объявление через ${formatCountdown(cooldown)}` : "Объявление — бот пришлёт всем"}
            </label>
          )}
          <span className="ml-auto text-micro text-ink-mist-dim">{text.length}/500</span>
          <button
            onClick={() => post.mutate()}
            disabled={!text.trim() || post.isPending}
            className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            Отправить
          </button>
        </div>
      </div>
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {wall.posts.length === 0 && (
        <EmptyState icon={IconChat} title="На стене пока пусто" description="Поздоровайся с клубом или договорись о турнире" />
      )}
      {wall.posts.map((p) => (
        <div
          key={p.id}
          className={`rounded-2xl p-3 ${p.is_announcement ? "border border-amber-300/30 bg-amber-400/10" : "bg-bg-surface"}`}
        >
          <div className="flex items-center gap-2 text-caption">
            {p.is_pinned && <IconFlag size={11} className="text-accent-lime" />}
            <span className="font-semibold text-ink-chalk">{p.username ?? p.first_name ?? `#${p.user_id}`}</span>
            {p.role && p.role !== "member" && <span className="text-ink-mist-dim">{CLUB_ROLE_LABELS[p.role]}</span>}
            {p.is_announcement && <span className="rounded-full bg-amber-400/20 px-1.5 text-micro font-bold text-amber-300">📣 объявление</span>}
            <span className="ml-auto text-ink-mist-dim">{timeLabel(p.created_at)}</span>
          </div>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-chalk">{p.text}</p>
          {(wall.can_pin || p.can_delete) && (
            <div className="mt-2 flex justify-end gap-2">
              {wall.can_pin && (
                <button onClick={() => pin.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-micro text-ink-mist">
                  {p.is_pinned ? "Открепить" : "Закрепить"}
                </button>
              )}
              {p.can_delete && (
                <button onClick={() => remove.mutate(p.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-micro text-red-400" aria-label="Удалить">
                  <IconTrash size={11} />
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
