import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import NumberInput from "@/components/common/NumberInput";
import PlayerCard from "@/components/cards/PlayerCard";
import { fetchCollection, fetchUserCollection } from "@/api/collection";
import { createTradeOffer } from "@/api/trades";
import { searchUsers } from "@/api/profile";
import { ApiRequestError } from "@/lib/api";
import type { UserPublic } from "@/types";

export default function NewTradePage() {
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [offeredIds, setOfferedIds] = useState<number[]>([]);
  const [requestedIds, setRequestedIds] = useState<number[]>([]);
  const [senderCoins, setSenderCoins] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: searchResults } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2 && !target,
  });

  const { data: myCollection } = useQuery({
    queryKey: ["collection-for-trade"],
    queryFn: () => fetchCollection({ page_size: 60 }),
  });

  const { data: theirCollection } = useQuery({
    queryKey: ["their-collection", target?.id],
    queryFn: () => fetchUserCollection(target!.id, { page_size: 60 }),
    enabled: !!target,
  });

  const createMutation = useMutation({
    mutationFn: createTradeOffer,
    onSuccess: () => navigate("/trades"),
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать обмен"),
  });

  const toggle = (list: number[], setList: (v: number[]) => void, id: number) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  };

  const submit = () => {
    if (!target) return;
    createMutation.mutate({
      receiver_id: target.id,
      offered_card_ids: offeredIds,
      requested_card_ids: requestedIds,
      sender_coins: senderCoins,
      message: message || undefined,
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold text-slate-100">Новый обмен</h1>

      {!target ? (
        <div className="flex flex-col gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Введи имя пользователя..."
            className="rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 outline-none"
          />
          <div className="flex flex-col gap-2">
            {searchResults?.map((u) => (
              <button
                key={u.id}
                onClick={() => setTarget(u)}
                className="flex items-center justify-between rounded-xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
              >
                <span className="text-sm text-slate-200">{u.username ?? u.first_name ?? `Игрок #${u.id}`}</span>
                <span className="text-xs text-slate-500">Ур. {u.level}</span>
              </button>
            ))}
            {query.length >= 2 && !searchResults?.length && (
              <EmptyState icon="🔍" title="Никого не найдено" />
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between rounded-xl bg-bg-surface px-4 py-3">
            <span className="text-sm text-slate-200">Обмен с: <b>{target.username ?? target.first_name}</b></span>
            <button onClick={() => setTarget(null)} className="text-xs text-accent">Сменить</button>
          </div>

          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

          <section>
            <p className="mb-2 text-sm font-semibold text-slate-300">Твои карточки ({offeredIds.length})</p>
            <div className="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto">
              {myCollection?.items.filter((c) => !c.is_locked_by_admin && !c.is_locked_in_trade && !c.is_in_lineup).map((c) => (
                <PlayerCard key={c.id} player={c.player} size="sm" selected={offeredIds.includes(c.id)} onClick={() => toggle(offeredIds, setOfferedIds, c.id)} />
              ))}
            </div>
          </section>

          <section>
            <p className="mb-2 text-sm font-semibold text-slate-300">Карточки {target.username ?? "игрока"} ({requestedIds.length})</p>
            <div className="grid grid-cols-3 gap-2 max-h-64 overflow-y-auto">
              {theirCollection?.items.map((c) => (
                <PlayerCard key={c.id} player={c.player} size="sm" selected={requestedIds.includes(c.id)} onClick={() => toggle(requestedIds, setRequestedIds, c.id)} />
              ))}
              {theirCollection && theirCollection.items.length === 0 && (
                <p className="col-span-3 text-xs text-slate-500">У игрока пока нет карточек</p>
              )}
            </div>
          </section>

          <div>
            <label className="mb-1 block text-sm font-semibold text-slate-300">Добавить монет со своей стороны</label>
            <NumberInput
              min={0}
              value={senderCoins}
              onChange={setSenderCoins}
              className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-slate-100 outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold text-slate-300">Сообщение (необязательно)</label>
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={255}
              className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-slate-100 outline-none"
            />
          </div>

          <button
            onClick={submit}
            disabled={createMutation.isPending || (offeredIds.length === 0 && requestedIds.length === 0 && senderCoins === 0)}
            className="rounded-2xl bg-accent py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {createMutation.isPending ? "Отправка..." : "Отправить предложение"}
          </button>
        </>
      )}
    </div>
  );
}
