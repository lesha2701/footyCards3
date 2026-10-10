import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  acceptFriendRequest,
  declineFriendRequest,
  fetchFriends,
  fetchFriendsFeed,
  removeFriend,
  sendFriendRequest,
} from "@/api/friends";
import { searchUsers } from "@/api/profile";
import { createTacticoChallenge } from "@/api/tactico";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { UserBadge } from "@/components/common/UserBadge";
import { IconFlagCheckered, IconSearch, IconSwap, IconUsers } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";
import type { UserPublic } from "@/types";

type Tab = "friends" | "requests" | "feed";

function displayName(u: UserPublic): string {
  return [u.first_name, u.last_name].filter(Boolean).join(" ") || u.username || "Игрок";
}

export default function FriendsPage() {
  const [tab, setTab] = useState<Tab>("friends");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["friends"], queryFn: fetchFriends });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["friends"] });
    queryClient.invalidateQueries({ queryKey: ["attention"] });
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const requests = data?.incoming.length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconUsers size={20} className="text-accent-lime" />
        Друзья
      </h1>
      <AddFriend existing={data} onDone={refresh} onError={onError} />
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["friends", `Друзья${data?.friends.length ? ` (${data.friends.length})` : ""}`], ["requests", `Заявки${requests ? ` (${requests})` : ""}`], ["feed", "Лента"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-xl py-2 text-xs font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && <ListSkeleton count={3} />}
      {tab === "friends" && data && <FriendList friends={data.friends.map((f) => f.user)} onChanged={refresh} onError={onError} />}
      {tab === "requests" && data && <Requests data={data} onChanged={refresh} onError={onError} />}
      {tab === "feed" && <Feed />}
    </div>
  );
}

function Avatar({ user }: { user: UserPublic }) {
  return (
    <img
      src={user.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
      alt=""
      className="h-10 w-10 shrink-0 rounded-full object-cover"
    />
  );
}

function AddFriend({
  existing, onDone, onError,
}: {
  existing: Awaited<ReturnType<typeof fetchFriends>> | undefined;
  onDone: () => void;
  onError: (e: unknown) => void;
}) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });
  const known = new Set([
    ...(existing?.friends.map((f) => f.user.id) ?? []),
    ...(existing?.outgoing.map((f) => f.user.id) ?? []),
  ]);
  const add = useMutation({
    mutationFn: sendFriendRequest,
    onSuccess: () => { haptic("light"); onDone(); },
    onError,
  });
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2.5">
        <IconSearch size={15} className="shrink-0 text-ink-mist-dim" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Найти игрока по имени или @нику"
          className="w-full bg-transparent text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
        />
      </div>
      {query.length >= 2 && results?.map((u) => (
        <div key={u.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <Avatar user={u} />
          <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{displayName(u)}</span>
          {known.has(u.id) ? (
            <span className="text-[11px] text-ink-mist">уже в списке</span>
          ) : (
            <button
              onClick={() => add.mutate(u.id)}
              disabled={add.isPending}
              className="rounded-full bg-accent-lime/15 px-3 py-1 text-xs font-semibold text-accent-lime disabled:opacity-50"
            >
              Добавить
            </button>
          )}
        </div>
      ))}
    </section>
  );
}

function FriendList({ friends, onChanged, onError }: { friends: UserPublic[]; onChanged: () => void; onError: (e: unknown) => void }) {
  const navigate = useNavigate();
  const challenge = useMutation({
    mutationFn: createTacticoChallenge,
    onSuccess: (match) => navigate(`/play/tactico/matches/${match.id}`),
    onError,
  });
  const remove = useMutation({ mutationFn: removeFriend, onSuccess: onChanged, onError });

  if (!friends.length) {
    return <EmptyState icon={IconUsers} title="Пока нет друзей" description="Найди игрока через поиск выше и отправь заявку" />;
  }
  return (
    <div className="flex flex-col gap-2">
      {friends.map((u) => (
        <div key={u.id} className="rounded-2xl bg-bg-surface p-3">
          <button onClick={() => navigate(`/users/${u.id}`)} className="flex w-full items-center gap-3 text-left">
            <Avatar user={u} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 truncate text-sm font-semibold text-ink-chalk">
                {displayName(u)} <UserBadge badge={u.active_badge} />
              </span>
              <span className="text-[11px] text-ink-mist">Рейтинг Arena {u.arena_rating}</span>
            </span>
          </button>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <QuickButton Icon={IconSwap} label="Обмен" onClick={() => navigate("/trades/new", { state: { target: u } })} />
            <QuickButton Icon={IconFlagCheckered} label="Тактико" onClick={() => challenge.mutate(u.id)} disabled={challenge.isPending} />
            <QuickButton Icon={IconUsers} label="Сезон" onClick={() => navigate(`/play/career?friend=${u.id}`)} />
          </div>
          <button onClick={() => remove.mutate(u.id)} className="mt-2 text-[11px] text-ink-mist-dim underline underline-offset-2">
            Удалить из друзей
          </button>
        </div>
      ))}
    </div>
  );
}

function QuickButton({
  Icon, label, onClick, disabled,
}: {
  Icon: (props: { size?: number }) => JSX.Element;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center justify-center gap-1 rounded-xl bg-bg-raised py-2 text-[11px] font-semibold text-ink-chalk active:scale-95 disabled:opacity-50"
    >
      <Icon size={13} /> {label}
    </button>
  );
}

function Requests({
  data, onChanged, onError,
}: {
  data: Awaited<ReturnType<typeof fetchFriends>>;
  onChanged: () => void;
  onError: (e: unknown) => void;
}) {
  const accept = useMutation({ mutationFn: acceptFriendRequest, onSuccess: onChanged, onError });
  const decline = useMutation({ mutationFn: declineFriendRequest, onSuccess: onChanged, onError });
  const cancel = useMutation({ mutationFn: removeFriend, onSuccess: onChanged, onError });
  if (!data.incoming.length && !data.outgoing.length) {
    return <EmptyState icon={IconUsers} title="Заявок нет" description="Здесь появятся входящие и отправленные заявки" />;
  }
  return (
    <div className="flex flex-col gap-2">
      {data.incoming.map((r) => (
        <div key={r.request_id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <Avatar user={r.user} />
          <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{displayName(r.user)}</span>
          <button onClick={() => accept.mutate(r.request_id)} className="rounded-full bg-floodlight px-3 py-1 text-xs font-bold text-bg-base">
            Принять
          </button>
          <button onClick={() => decline.mutate(r.request_id)} className="rounded-full bg-white/5 px-3 py-1 text-xs text-ink-mist">
            Нет
          </button>
        </div>
      ))}
      {data.outgoing.map((r) => (
        <div key={r.request_id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3 opacity-80">
          <Avatar user={r.user} />
          <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{displayName(r.user)}</span>
          <span className="text-[11px] text-ink-mist">ждёт ответа</span>
          <button onClick={() => cancel.mutate(r.user.id)} className="text-[11px] text-ink-mist-dim underline">
            отменить
          </button>
        </div>
      ))}
    </div>
  );
}

function Feed() {
  const { data, isLoading } = useQuery({ queryKey: ["friends", "feed"], queryFn: fetchFriendsFeed });
  if (isLoading) return <ListSkeleton count={3} />;
  if (!data?.length) {
    return <EmptyState icon={IconUsers} title="Тихо" description="Здесь появятся легендарки, трофеи и итоги сезонов друзей за неделю" />;
  }
  return (
    <div className="flex flex-col gap-2">
      {data.map((item, i) => (
        <div key={i} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <Avatar user={item.user} />
          <span className="min-w-0 flex-1 text-sm text-ink-chalk">
            <b>{displayName(item.user)}</b> {item.text}
            <span className="block text-[10px] text-ink-mist-dim">
              {new Date(item.at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
