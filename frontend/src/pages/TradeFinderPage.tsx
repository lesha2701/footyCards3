import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { UserBadge } from "@/components/common/UserBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { IconClose, IconSearch, IconSwap } from "@/components/icons";
import CardsSectionTabs from "@/components/layout/CardsSectionTabs";
import { fetchCollection } from "@/api/collection";
import {
  addTradeWish,
  fetchTradeMatches,
  fetchTradeWishes,
  removeTradeWish,
  searchPlayers,
  type TradeMatch,
  type TradeWishKind,
} from "@/api/trades";
import { ApiRequestError } from "@/lib/api";
import type { Player } from "@/types";

type Tab = "matches" | "lists";

/** «Поиск обменов»: the player lists who they look for («Ищу») and who they
 * are ready to give («Отдаю»); the server suggests active partners. The
 * offer itself opens the usual new-trade screen with the cards picked. */
export default function TradeFinderPage() {
  const [tab, setTab] = useState<Tab>("matches");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Поиск обменов</h1>
      <CardsSectionTabs />
      <div className="flex gap-2">
        <TabButton active={tab === "matches"} label="Совпадения" onClick={() => setTab("matches")} />
        <TabButton active={tab === "lists"} label="Мои списки" onClick={() => setTab("lists")} />
      </div>
      {tab === "matches" ? <Matches onEditLists={() => setTab("lists")} /> : <Lists />}
    </div>
  );
}

function Matches({ onEditLists }: { onEditLists: () => void }) {
  const navigate = useNavigate();
  const { data: matches, isLoading } = useQuery({ queryKey: ["trade-matches"], queryFn: fetchTradeMatches });

  if (isLoading) return <ListSkeleton />;
  if (!matches?.length) {
    return (
      <div className="flex flex-col items-center gap-3">
        <EmptyState
          icon={IconSearch}
          title="Пока никого"
          description="Добавь в «Ищу» карточки, которых тебе не хватает, а в «Отдаю» — те, что готов обменять. Мы подберём активных игроков."
        />
        <button onClick={onEditLists} className="rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95">
          Заполнить списки
        </button>
      </div>
    );
  }

  const propose = (m: TradeMatch) =>
    navigate("/trades/new", {
      state: {
        target: m.user,
        offeredIds: m.they_want.slice(0, 3).map((c) => c.card_id),
        requestedIds: m.they_have.slice(0, 3).map((c) => c.card_id),
      },
    });

  return (
    <div className="flex flex-col gap-3">
      {matches.map((m) => (
        <div key={m.user.id} className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1 truncate text-sm font-semibold text-ink-chalk">
              {m.user.username ?? m.user.first_name ?? `Игрок #${m.user.id}`}
              <UserBadge badge={m.user.active_badge} />
            </span>
            {m.mutual && (
              <span className="shrink-0 rounded-full bg-accent-lime/15 px-2 py-0.5 text-caption font-bold text-accent-lime">
                Взаимно
              </span>
            )}
          </div>
          <MatchRow label="Есть у игрока" cards={m.they_have} empty="Ничего из твоего «Ищу»" />
          <MatchRow label="Нужно игроку от тебя" cards={m.they_want} empty="Ничего из твоих лишних карточек" />
          <button
            onClick={() => propose(m)}
            className="flex items-center justify-center gap-1 rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95"
          >
            <IconSwap size={14} />
            Предложить обмен
          </button>
        </div>
      ))}
      <p className="text-caption text-ink-mist-dim">
        Показываем игроков, заходивших в игру за последние дни. Карточки в предложении можно поменять перед отправкой.
      </p>
    </div>
  );
}

function MatchRow({ label, cards, empty }: { label: string; cards: TradeMatch["they_have"]; empty: string }) {
  return (
    <div>
      <p className="mb-1.5 text-xs text-ink-mist">{label}</p>
      {cards.length === 0 ? (
        <p className="text-caption text-ink-mist-dim">{empty}</p>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {cards.map((c) => (
            <div key={c.card_id}>
              <PlayerCard player={c.player} size="sm" />
              {c.marked_to_give && <p className="mt-0.5 text-center text-micro text-accent-lime">готов отдать</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Lists() {
  const queryClient = useQueryClient();
  const { data: wishes } = useQuery({ queryKey: ["trade-wishes"], queryFn: fetchTradeWishes });
  const [adding, setAdding] = useState<TradeWishKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onSaved = (data: Awaited<ReturnType<typeof fetchTradeWishes>>) => {
    queryClient.setQueryData(["trade-wishes"], data);
    queryClient.invalidateQueries({ queryKey: ["trade-matches"] });
    setError(null);
  };
  const onError = (err: unknown) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить");
  const add = useMutation({ mutationFn: ({ kind, id }: { kind: TradeWishKind; id: number }) => addTradeWish(kind, id), onSuccess: onSaved, onError });
  const remove = useMutation({ mutationFn: ({ kind, id }: { kind: TradeWishKind; id: number }) => removeTradeWish(kind, id), onSuccess: onSaved, onError });

  if (!wishes) return <ListSkeleton />;

  const section = (kind: TradeWishKind, title: string, hint: string, list: Player[], max: number) => (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-chalk">
          {title} <span className="text-xs text-ink-mist-dim">{list.length}/{max}</span>
        </p>
        {list.length < max && (
          <button onClick={() => setAdding(adding === kind ? null : kind)} className="text-xs font-semibold text-accent-lime">
            {adding === kind ? "Готово" : "+ Добавить"}
          </button>
        )}
      </div>
      <p className="text-caption text-ink-mist-dim">{hint}</p>
      {adding === kind && <PlayerPicker kind={kind} onPick={(p) => add.mutate({ kind, id: p.id })} exclude={[...wishes.wants, ...wishes.gives].map((p) => p.id)} />}
      {list.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {list.map((p) => (
            <div key={p.id} className="relative">
              <PlayerCard player={p} size="sm" />
              <button
                onClick={() => remove.mutate({ kind, id: p.id })}
                aria-label="Убрать"
                className="absolute -right-1 -top-1 rounded-full bg-bg-base p-1 text-ink-mist active:scale-90"
              >
                <IconClose size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );

  return (
    <div className="flex flex-col gap-3">
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      {section("want", "Ищу", "Карточки, которых тебе не хватает.", wishes.wants, wishes.max_wants)}
      {section(
        "give",
        "Отдаю",
        "Карточки, которые готов обменять. Лишние копии (2+ одинаковых) предлагаем и без этого списка.",
        wishes.gives,
        wishes.max_gives,
      )}
    </div>
  );
}

/** «Ищу» searches every player; «Отдаю» only the player's own cards. */
function PlayerPicker({ kind, onPick, exclude }: { kind: TradeWishKind; onPick: (p: Player) => void; exclude: number[] }) {
  const [search, setSearch] = useState("");
  const { data: players } = useQuery({
    queryKey: ["trade-wish-search", kind, search],
    queryFn: async (): Promise<Player[]> => {
      if (kind === "want") return searchPlayers(search);
      const page = await fetchCollection({ page_size: 60, search: search || undefined });
      const seen = new Set<number>();
      return page.items.map((c) => c.player).filter((p) => (seen.has(p.id) ? false : (seen.add(p.id), true)));
    },
    enabled: kind === "give" || search.length >= 2,
  });
  const list = (players ?? []).filter(
    (p) => !exclude.includes(p.id) && (p.rarity !== "diamond" || !!p.path_talent_code),
  );

  return (
    <div className="flex flex-col gap-2">
      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={kind === "want" ? "Имя игрока (от 2 букв)..." : "Поиск по своим карточкам..."}
        className="w-full rounded-xl bg-bg-base px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />
      <div className="max-h-64 overflow-y-auto">
        <div className="grid grid-cols-3 gap-2">
          {list.map((p) => (
            <PlayerCard key={p.id} player={p} size="sm" onClick={() => onPick(p)} />
          ))}
        </div>
        {players && list.length === 0 && <p className="text-caption text-ink-mist-dim">Ничего не найдено</p>}
      </div>
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl py-2 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}
