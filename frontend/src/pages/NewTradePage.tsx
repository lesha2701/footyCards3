import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import StickyActionBar from "@/components/common/StickyActionBar";
import { UserBadge } from "@/components/common/UserBadge";
import { IconSearch } from "@/components/icons";
import NumberInput from "@/components/common/NumberInput";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { fetchCollection, fetchUserCollection } from "@/api/collection";
import { createTradeOffer, fetchTradeRules, previewTrade } from "@/api/trades";
import { fetchPublicProfile, searchUsers } from "@/api/profile";
import { ApiRequestError } from "@/lib/api";
import type { UserPublic } from "@/types";

const MAX_TRADE_CARDS_PER_SIDE = 3;

export default function NewTradePage() {
  const navigate = useNavigate();
  // "Предложить обмен" on a public profile opens this page with the
  // receiver already picked.
  // «Поиск обменов» also passes the cards it matched.
  const state = useLocation().state as { target?: UserPublic; offeredIds?: number[]; requestedIds?: number[] } | null;
  const prefilled = state?.target ?? null;

  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<UserPublic | null>(prefilled);
  // «Поделиться в чат» link from «Поиск обменов»: /trades/new?to=<user id>.
  const [searchParams] = useSearchParams();
  const toId = Number(searchParams.get("to")) || null;
  const { data: linkedTarget } = useQuery({
    queryKey: ["trade-link-target", toId],
    queryFn: () => fetchPublicProfile(toId!),
    enabled: !!toId && !prefilled,
  });
  useEffect(() => {
    if (linkedTarget && !target) setTarget(linkedTarget);
  }, [linkedTarget, target]);
  const [offeredIds, setOfferedIds] = useState<number[]>(state?.offeredIds ?? []);
  const [requestedIds, setRequestedIds] = useState<number[]>(state?.requestedIds ?? []);
  const [senderCoins, setSenderCoins] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [myCardSearch, setMyCardSearch] = useState("");
  const [theirCardSearch, setTheirCardSearch] = useState("");

  const { data: searchResults } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2 && !target,
  });

  const { data: myCollection } = useQuery({
    queryKey: ["collection-for-trade", myCardSearch],
    queryFn: () => fetchCollection({ page_size: 100, search: myCardSearch || undefined }),
  });

  const { data: rules } = useQuery({ queryKey: ["trade-rules"], queryFn: fetchTradeRules });

  const { data: theirCollection } = useQuery({
    queryKey: ["their-collection", target?.id, theirCardSearch],
    queryFn: () => fetchUserCollection(target!.id, { page_size: 100, search: theirCardSearch || undefined }),
    enabled: !!target,
  });

  // Neither side's collection ever offers/requests a card locked elsewhere
  // (admin lock, in a trade, in a Card Arena lineup, or in a Tactico
  // squad) — the backend rejects all four (plus diamond rarity, which never
  // trades — except «Академия» cards, whose path progress moves with the
  // card) at accept time anyway, so showing them as pickable here just sets
  // the offer up to fail later.
  // A legendary / diamond / «Академия» copy from a free source never leaves
  // its account (limited cards are left to the server check / preview).
  const isTradeable = (c: {
    is_locked_by_admin: boolean; is_locked_in_trade: boolean; is_in_lineup: boolean; is_in_tactico_squad: boolean;
    from_free_source?: boolean;
    player: { rarity: string; path_talent_code?: string | null };
  }) =>
    !c.is_locked_by_admin && !c.is_locked_in_trade && !c.is_in_lineup && !c.is_in_tactico_squad &&
    (c.player.rarity !== "diamond" || !!c.player.path_talent_code) &&
    !(c.from_free_source && (c.player.rarity === "legendary" || c.player.rarity === "diamond" || !!c.player.path_talent_code));

  const createMutation = useMutation({
    mutationFn: createTradeOffer,
    onSuccess: () => navigate("/trades"),
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать обмен"),
  });

  const toggle = (list: number[], setList: (v: number[]) => void, id: number) => {
    if (list.includes(id)) {
      setList(list.filter((x) => x !== id));
      setError(null);
      return;
    }
    if (list.length >= MAX_TRADE_CARDS_PER_SIDE) {
      setError(`Максимум ${MAX_TRADE_CARDS_PER_SIDE} карточки с одной стороны обмена`);
      return;
    }
    setList([...list, id]);
    setError(null);
  };

  const coinsEnabled = rules?.coins_enabled ?? true;
  const coins = coinsEnabled ? senderCoins : 0;
  // Values of both sides and the server's verdict, so an unequal or not
  // allowed trade is explained before it is sent.
  const { data: preview } = useQuery({
    queryKey: ["trade-preview", target?.id, offeredIds, requestedIds, coins],
    queryFn: () => previewTrade({
      receiver_id: target!.id, offered_card_ids: offeredIds, requested_card_ids: requestedIds, sender_coins: coins,
    }),
    enabled: !!target && (offeredIds.length > 0 || requestedIds.length > 0),
  });
  const canSubmit = (rules?.cards_both_sides
    ? offeredIds.length > 0 && requestedIds.length > 0
    : offeredIds.length > 0 || requestedIds.length > 0 || coins > 0) && preview?.ok !== false;

  const submit = () => {
    if (!target) return;
    createMutation.mutate({
      receiver_id: target.id,
      offered_card_ids: offeredIds,
      requested_card_ids: requestedIds,
      sender_coins: coins,
      message: message || undefined,
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Новый обмен</h1>

      {!target ? (
        <div className="flex flex-col gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Введи имя пользователя..."
            className="rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
          />
          <div className="flex flex-col gap-2">
            {searchResults?.map((u) => (
              <button
                key={u.id}
                onClick={() => setTarget(u)}
                className="flex items-center justify-between rounded-xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
              >
                <span className="flex items-center gap-1 text-sm text-ink-chalk">
                  {u.username ?? u.first_name ?? `Игрок #${u.id}`}
                  <UserBadge badge={u.active_badge} />
                </span>
                <span className="text-xs text-ink-mist-dim">Ур. {u.level}</span>
              </button>
            ))}
            {query.length >= 2 && !searchResults?.length && (
              <EmptyState icon={IconSearch} title="Никого не найдено" />
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between rounded-xl bg-bg-surface px-4 py-3">
            <span className="flex items-center gap-1 text-sm text-ink-chalk">
              Обмен с: <b>{target.username ?? target.first_name}</b>
              <UserBadge badge={target.active_badge} />
            </span>
            <button onClick={() => setTarget(null)} className="text-xs text-accent-lime">Сменить</button>
          </div>

          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
          {rules && !rules.can_give && rules.give_block_reason && (
            <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
              {rules.give_block_reason} Пока можно только получать карточки и монеты от других игроков.
            </p>
          )}
          {rules && !rules.verified && rules.verified_block_reason && (
            <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">
              🔒 Легендарки, алмазы, «Академию» и лимитки отдавать в обмене пока нельзя. {rules.verified_block_reason}
            </p>
          )}
          <p className="text-caption text-ink-mist-dim">
            Ценные карточки, полученные бесплатно (награды, бесплатные паки, колесо), привязаны к аккаунту и в обмене не показываются.
          </p>

          <section>
            <p className="mb-2 text-sm font-semibold text-ink-mist">Твои карточки ({offeredIds.length}/{MAX_TRADE_CARDS_PER_SIDE})</p>
            <input
              value={myCardSearch}
              onChange={(e) => setMyCardSearch(e.target.value)}
              placeholder="Поиск по имени..."
              className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
            />
            <div className="max-h-64 overflow-y-auto">
              <div className="grid grid-cols-3 gap-2">
                {myCollection?.items.filter(isTradeable).map((c) => (
                  <PlayerCard key={c.id} player={c.player} pathStage={c.path_stage} prestige={c.prestige} talentOverride={c.talent_override} size="sm" badge={<CardSkillBadge code={c.skill_code} level={c.skill_level} />} selected={offeredIds.includes(c.id)} onClick={() => toggle(offeredIds, setOfferedIds, c.id)} />
                ))}
                {myCollection && !myCollection.items.filter(isTradeable).length && (
                  <p className="col-span-3 text-xs text-ink-mist-dim">
                    {myCardSearch ? "Ничего не найдено" : "Нет доступных для обмена карточек"}
                  </p>
                )}
              </div>
            </div>
            {myCollection && myCollection.total > myCollection.items.length && !myCardSearch && (
              <p className="mt-1 text-caption text-ink-mist-dim">
                Показано {myCollection.items.length} из {myCollection.total} — используй поиск, чтобы найти конкретную карточку
              </p>
            )}
          </section>

          <section>
            <p className="mb-2 text-sm font-semibold text-ink-mist">Карточки {target.username ?? "игрока"} ({requestedIds.length}/{MAX_TRADE_CARDS_PER_SIDE})</p>
            <input
              value={theirCardSearch}
              onChange={(e) => setTheirCardSearch(e.target.value)}
              placeholder="Поиск по имени..."
              className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
            />
            <div className="max-h-64 overflow-y-auto">
              <div className="grid grid-cols-3 gap-2">
                {theirCollection?.items.filter(isTradeable).map((c) => (
                  <PlayerCard key={c.id} player={c.player} pathStage={c.path_stage} prestige={c.prestige} talentOverride={c.talent_override} size="sm" badge={<CardSkillBadge code={c.skill_code} level={c.skill_level} />} selected={requestedIds.includes(c.id)} onClick={() => toggle(requestedIds, setRequestedIds, c.id)} />
                ))}
                {theirCollection && theirCollection.items.filter(isTradeable).length === 0 && (
                  <p className="col-span-3 text-xs text-ink-mist-dim">
                    {theirCardSearch ? "Ничего не найдено" : "У игрока пока нет доступных для обмена карточек"}
                  </p>
                )}
              </div>
            </div>
            {theirCollection && theirCollection.total > theirCollection.items.length && !theirCardSearch && (
              <p className="mt-1 text-caption text-ink-mist-dim">
                Показано {theirCollection.items.length} из {theirCollection.total} — используй поиск, чтобы найти конкретную карточку
              </p>
            )}
          </section>

          {rules && (!rules.coins_enabled || rules.cards_both_sides) && (
            <p className="text-caption text-ink-mist-dim">
              {rules.cards_both_sides
                ? "Обмен — «карточка на карточку»: выбери хотя бы одну свою карточку и одну карточку игрока."
                : "Монеты в обменах сейчас отключены."}
            </p>
          )}

          {coinsEnabled && <div>
            <label className="mb-1 block text-sm font-semibold text-ink-mist">Добавить монет со своей стороны</label>
            <NumberInput
              min={0}
              value={senderCoins}
              onChange={setSenderCoins}
              className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
            />
            {rules && rules.coin_tax_pct > 0 && senderCoins > 0 && (
              <p className="mt-1 text-caption text-ink-mist-dim">
                Налог {rules.coin_tax_pct}%: игрок получит{" "}
                {senderCoins - Math.min(senderCoins, Math.ceil((senderCoins * rules.coin_tax_pct) / 100))} монет
              </p>
            )}
          </div>}

          <div>
            <label className="mb-1 block text-sm font-semibold text-ink-mist">Сообщение (необязательно)</label>
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={255}
              className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
            />
          </div>

          {preview && (
            <div className={`rounded-xl px-3 py-2 text-xs ${preview.ok ? "bg-white/5 text-ink-mist" : "bg-red-500/10 text-red-400"}`}>
              <p>
                Ценность: ты отдаёшь <b>{preview.give_value.toLocaleString("ru-RU")}</b> · получаешь{" "}
                <b>{preview.get_value.toLocaleString("ru-RU")}</b> монет
              </p>
              {preview.problem && <p className="mt-1">{preview.problem}</p>}
            </div>
          )}

          <StickyActionBar>
            <button
              onClick={submit}
              disabled={createMutation.isPending || !canSubmit}
              className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:bg-none disabled:bg-bg-raised disabled:text-ink-mist"
            >
              {createMutation.isPending ? "Отправка..." : "Отправить предложение"}
            </button>
          </StickyActionBar>
        </>
      )}
    </div>
  );
}
