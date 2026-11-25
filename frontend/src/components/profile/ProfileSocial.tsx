import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchProfileSocial, giveRespect } from "@/api/profile";
import ShareButton from "@/components/common/ShareButton";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

/** «👍 Респект» (one a day from each visitor) and, on your own profile, «Поделиться профилем». */
export function RespectBar({ userId, isMe }: { userId: number; isMe: boolean }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["profile-social", userId], queryFn: () => fetchProfileSocial(userId) });
  const respect = useMutation({
    mutationFn: () => giveRespect(userId),
    onSuccess: (fresh) => {
      hapticNotify("success");
      queryClient.setQueryData(["profile-social", userId], fresh);
    },
  });
  if (!data) return null;
  return (
    <div className="mt-2 flex w-full flex-col items-center gap-2">
      <div className="flex items-center gap-2">
        <button
          onClick={() => respect.mutate()}
          disabled={!data.can_respect || data.respected_today || respect.isPending}
          className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold active:scale-95 ${
            data.respected_today ? "bg-accent-lime/20 text-accent-lime" : data.can_respect ? "bg-white/10 text-ink-chalk" : "bg-white/5 text-ink-mist"
          }`}
          data-testid="respect-button"
        >
          👍 {data.respected_today ? "Респект отправлен" : data.can_respect ? "Респект" : "Респекты"} · {data.respects}
        </button>
        {isMe && <ShareButton kind="profile" id={0} label="Поделиться профилем" compact />}
      </div>
      {respect.error && <p className="text-micro text-red-400">{formatGameError(respect.error, "Не получилось")}</p>}
    </div>
  );
}

/** The profile's latest moments: rare prints, trophies, completed collections. */
const FEED_PREVIEW = 3;

export function ProfileFeed({ userId }: { userId: number }) {
  const [showAll, setShowAll] = useState(false);
  const { data } = useQuery({ queryKey: ["profile-social", userId], queryFn: () => fetchProfileSocial(userId) });
  if (!data?.feed.length) return null;
  const events = showAll ? data.feed : data.feed.slice(0, FEED_PREVIEW);
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="profile-feed">
      <p className="mb-2 text-micro font-bold uppercase tracking-[0.2em] text-ink-mist">📰 Последние события</p>
      <ol className="relative flex flex-col gap-2 border-l border-white/10 pl-4">
        {events.map((e, i) => (
          <li key={i} className="relative flex items-center gap-2.5">
            <span className="absolute -left-[23px] flex h-4 w-4 items-center justify-center rounded-full bg-bg-base text-[10px] ring-1 ring-white/15">
              {e.icon}
            </span>
            {e.image_path && (
              <img decoding="async" loading="lazy" src={staticUrl(e.image_path) ?? undefined} className="h-9 w-9 shrink-0 rounded-lg object-cover" />
            )}
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-ink-chalk">{e.text}</span>
              <span className="text-micro text-ink-mist-dim">{new Date(e.at).toLocaleDateString("ru-RU")}</span>
            </span>
          </li>
        ))}
      </ol>
      {data.feed.length > FEED_PREVIEW && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 w-full rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-[0.98]"
          data-testid="profile-feed-toggle"
        >
          {showAll ? "Свернуть" : `Показать все · ${data.feed.length}`}
        </button>
      )}
    </section>
  );
}
