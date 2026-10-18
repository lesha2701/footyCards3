import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  buyClubEmblemItem,
  buyClubEmblemItemWithClubStars,
  createClubEmblemInvoice,
  fetchClubEmblem,
  saveClubEmblem,
} from "@/api/clubFeatures";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { CLUB_LOGO_COLORS, CLUB_LOGO_SHAPES } from "@/components/clubs/clubLogoOptions";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCheck, IconChevronLeft, IconCoin, IconLock, IconStar } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import type { ClubEmblem, ClubEmblemKind, ClubEmblemState, ClubLogoShape } from "@/types";

type Item = ClubEmblemState["items"][number];
type Draft = ClubEmblem & { logo_shape: ClubLogoShape; logo_color: string };

const LAYER_KEY: Record<"pattern" | "symbol" | "outline" | "effect", keyof ClubEmblem> = {
  pattern: "pattern", symbol: "symbol", outline: "outline", effect: "effect",
};

/** Конструктор эмблемы клуба: форма и цвет бесплатно, слои — за бюджет клуба
 * или за Stars (club_emblem_service). Любой участник может примерить что угодно
 * и подарить клубу элемент за звёзды; надевает эмблему капитан. */
export default function ClubEmblemPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: state, isLoading } = useQuery({ queryKey: ["clubs", "emblem"], queryFn: fetchClubEmblem });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (state && !draft) setDraft({ ...state.emblem, logo_shape: state.logo_shape, logo_color: state.logo_color });
  }, [state, draft]);

  const onState = (data: ClubEmblemState) => {
    queryClient.setQueryData(["clubs", "emblem"], data);
    queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    queryClient.invalidateQueries({ queryKey: ["clubs", "list"] });
    setError(null);
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось выполнить действие"));

  const buyCoins = useMutation({
    mutationFn: (item: Item) => buyClubEmblemItem(item.id),
    onSuccess: (data, item) => { onState(data); hapticNotify("success"); setNotice(`«${item.name}» открыт для клуба`); },
    onError,
  });
  const buyStars = useMutation({
    mutationFn: (item: Item) => payShopWithStars(() => createClubEmblemInvoice(item.id)),
    onSuccess: async (status, item) => {
      if (status !== "paid") return;
      hapticNotify("success");
      setNotice(`«${item.name}» открыт для клуба — спасибо!`);
      onState(await fetchClubEmblem());
    },
    onError,
  });
  const buyClubStars = useMutation({
    mutationFn: (item: Item) => buyClubEmblemItemWithClubStars(item.id),
    onSuccess: (data, item) => { onState(data); hapticNotify("success"); setNotice(`«${item.name}» открыт за звёзды клуба`); },
    onError,
  });
  const save = useMutation({
    mutationFn: () => saveClubEmblem(draft!),
    onSuccess: (data) => { onState(data); hapticNotify("success"); setNotice("Эмблема сохранена"); },
    onError,
  });

  const byKind = useMemo(() => {
    const map: Partial<Record<ClubEmblemKind, Item[]>> = {};
    for (const item of state?.items ?? []) (map[item.kind] ??= []).push(item);
    return map;
  }, [state]);

  if (isLoading || !state || !draft) return <ListSkeleton />;

  const find = (kind: ClubEmblemKind, style: string | null) => state.items.find((i) => i.kind === kind && i.style_key === style);
  const color2Item = find("color2", "second_color");
  const lettersItem = find("letters", "letters");
  const lockedInDraft: Item[] = [
    draft.color2 ? color2Item : undefined,
    draft.letters ? lettersItem : undefined,
    ...(["pattern", "symbol", "outline", "effect"] as const).map((k) => (draft[LAYER_KEY[k]] ? find(k, draft[LAYER_KEY[k]] as string) : undefined)),
  ].filter((i): i is Item => !!i && !i.unlocked);
  const dirty =
    JSON.stringify(draft) !== JSON.stringify({ ...state.emblem, logo_shape: state.logo_shape, logo_color: state.logo_color });
  const set = (patch: Partial<Draft>) => { setDraft((d) => (d ? { ...d, ...patch } : d)); setNotice(null); };
  const busy = buyCoins.isPending || buyStars.isPending || buyClubStars.isPending;

  const priceButton = (item: Item) => {
    if (item.unlocked) return null;
    if (item.stars_price > 0) {
      if (state.can_spend_budget && state.star_balance >= item.stars_price) {
        return (
          <button
            onClick={() => buyClubStars.mutate(item)}
            disabled={busy || !state.enabled}
            title="Со звёздного баланса клуба"
            className="flex items-center justify-center gap-1 rounded-lg bg-amber-400 px-2 py-1 text-caption font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            <IconStar size={11} /> {item.stars_price} клуба
          </button>
        );
      }
      return (
        <button
          onClick={() => buyStars.mutate(item)}
          disabled={busy || !state.enabled}
          className="flex items-center justify-center gap-1 rounded-lg bg-amber-400/15 px-2 py-1 text-caption font-bold text-amber-300 active:scale-95 disabled:opacity-40"
        >
          <IconStar size={11} /> {item.stars_price}
        </button>
      );
    }
    return (
      <button
        onClick={() => buyCoins.mutate(item)}
        disabled={busy || !state.enabled || !state.can_spend_budget || state.budget < item.coins_price}
        className="flex items-center justify-center gap-1 rounded-lg bg-accent-lime/10 px-2 py-1 text-caption font-bold text-accent-lime active:scale-95 disabled:opacity-40"
      >
        <IconCoin size={11} /> {item.coins_price}
      </button>
    );
  };

  const layerGrid = (kind: "pattern" | "symbol" | "outline" | "effect", title: string, hint: string) => {
    const items = byKind[kind] ?? [];
    if (!items.length) return null;
    const key = LAYER_KEY[kind];
    const current = draft[key] as string | null;
    return (
      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <div>
          <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
          <p className="text-caption text-ink-mist-dim">{hint}</p>
        </div>
        <div className="grid grid-cols-4 gap-2">
          <button
            onClick={() => set({ [key]: null } as Partial<Draft>)}
            className={`flex flex-col items-center gap-1 rounded-xl p-2 text-micro text-ink-mist ${current === null ? "bg-white/10 ring-2 ring-accent" : "bg-black/20"}`}
          >
            <ClubLogo shape={draft.logo_shape} color={draft.logo_color} emblem={{ ...draft, [key]: null }} size={40} />
            Нет
          </button>
          {items.map((item) => (
            <div
              key={item.id}
              className={`flex flex-col items-center gap-1 rounded-xl p-2 ${current === item.style_key ? "bg-white/10 ring-2 ring-accent" : "bg-black/20"}`}
            >
              <button onClick={() => set({ [key]: item.style_key } as Partial<Draft>)} className="relative flex flex-col items-center gap-1">
                <ClubLogo shape={draft.logo_shape} color={draft.logo_color} emblem={{ ...draft, [key]: item.style_key }} size={40} />
                {!item.unlocked && <IconLock size={10} className="absolute right-0 top-0 text-ink-mist-dim" />}
                <span className="text-center text-micro leading-tight text-ink-mist">{item.name}</span>
              </button>
              {priceButton(item)}
            </div>
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="flex flex-col gap-4 pb-24">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Эмблема клуба</h1>
      </div>

      <div className="flex flex-col items-center gap-2 rounded-3xl bg-gradient-to-b from-white/5 to-transparent p-6">
        <ClubLogo shape={draft.logo_shape} color={draft.logo_color} emblem={draft} size={150} />
        {lockedInDraft.length > 0 && (
          <span className="rounded-full bg-amber-400/15 px-3 py-1 text-caption font-semibold text-amber-300">
            Примерка: {lockedInDraft.map((i) => i.name).join(", ")}
          </span>
        )}
        <p className="flex items-center gap-1 text-caption text-ink-mist-dim">
          Бюджет: <IconCoin size={12} className="text-accent-lime" />
          <span className="font-mono font-bold text-accent-lime">{state.budget}</span>
          <span className="mx-1">·</span>
          Звёзды клуба: <IconStar size={12} className="text-amber-300" />
          <span className="font-mono font-bold text-amber-300">{state.star_balance}</span>
        </p>
      </div>

      {!state.enabled && (
        <p className="rounded-lg bg-white/5 px-3 py-2 text-xs text-ink-mist">Магазин эмблем временно закрыт — примерять можно.</p>
      )}
      {!state.can_edit && (
        <p className="rounded-lg bg-white/5 px-3 py-2 text-xs text-ink-mist">
          Надевает эмблему капитан. Ты можешь примерять и подарить клубу элемент за звёзды
          {state.can_spend_budget ? " или открыть его за бюджет клуба" : ""}.
        </p>
      )}

      <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-3">
        <p className="font-display text-sm font-bold text-ink-chalk">Форма и цвет · бесплатно</p>
        <div className="flex flex-wrap justify-center gap-2">
          {CLUB_LOGO_SHAPES.map((s) => (
            <button
              key={s}
              onClick={() => set({ logo_shape: s })}
              className={`rounded-xl p-2 ${draft.logo_shape === s ? "bg-white/10 ring-2 ring-accent" : "bg-black/20"}`}
            >
              <ClubLogo shape={s} color={draft.logo_color} size={28} />
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {CLUB_LOGO_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => set({ logo_color: c })}
              style={{ backgroundColor: c }}
              className={`h-8 w-8 rounded-full ${draft.logo_color.toLowerCase() === c.toLowerCase() ? "ring-2 ring-white" : ""}`}
            />
          ))}
          <input
            type="color"
            value={draft.logo_color.length === 7 ? draft.logo_color : "#ffffff"}
            onChange={(e) => set({ logo_color: e.target.value.toUpperCase() })}
            className="h-8 w-8 cursor-pointer rounded-full bg-transparent"
            aria-label="Свой цвет"
          />
        </div>
      </section>

      {color2Item && (
        <section className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <div className="flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">{color2Item.name}</p>
            <p className="text-caption text-ink-mist-dim">Цвет узора и символа</p>
          </div>
          {draft.color2 && (
            <button onClick={() => set({ color2: null })} className="rounded-lg bg-white/5 px-2 py-1 text-caption text-ink-mist">
              Убрать
            </button>
          )}
          <input
            type="color"
            value={draft.color2 ?? "#ffffff"}
            onChange={(e) => set({ color2: e.target.value.toUpperCase() })}
            className="h-9 w-9 cursor-pointer rounded-lg bg-transparent"
            aria-label="Второй цвет"
          />
          {priceButton(color2Item)}
        </section>
      )}

      {layerGrid("pattern", "Узор", "За бюджет клуба")}

      {lettersItem && (
        <section className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
          <div className="flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">{lettersItem.name}</p>
            <p className="text-caption text-ink-mist-dim">До 3 букв или цифр, например «ФК»</p>
          </div>
          <input
            value={draft.letters ?? ""}
            onChange={(e) => set({ letters: e.target.value.toUpperCase().replace(/[^A-ZА-ЯЁ0-9]/g, "").slice(0, 3) || null })}
            placeholder="ФК"
            className="w-16 rounded-lg bg-black/20 px-2 py-1.5 text-center font-display text-sm font-bold text-ink-chalk outline-none"
          />
          {priceButton(lettersItem)}
        </section>
      )}

      {layerGrid("symbol", "Символ", "За звёзды — навсегда для клуба")}

      {layerGrid("outline", "Обводка", "За звёзды — золото, серебро, бронза или неон")}
      {draft.outline && (
        <label className="-mt-2 flex items-center gap-2 px-3 text-xs text-ink-mist">
          <input type="checkbox" checked={draft.outline_thin} onChange={(e) => set({ outline_thin: e.target.checked })} />
          Тонкая обводка
        </label>
      )}

      {layerGrid("effect", "Анимация", "За звёзды — эмблема оживает во всех списках")}

      {notice && (
        <p className="flex items-center gap-1.5 rounded-lg bg-accent-green/10 px-3 py-2 text-xs text-accent-green">
          <IconCheck size={13} /> {notice}
        </p>
      )}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {state.can_edit && (
        <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 mx-auto max-w-md px-4 py-2">
          <button
            onClick={() => save.mutate()}
            disabled={!dirty || lockedInDraft.length > 0 || save.isPending}
            className="w-full rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base shadow-xl active:scale-95 disabled:opacity-60"
          >
            {lockedInDraft.length > 0 ? "Сначала открой элементы из примерки" : save.isPending ? "Сохранение..." : "Сохранить эмблему"}
          </button>
        </div>
      )}
    </div>
  );
}
