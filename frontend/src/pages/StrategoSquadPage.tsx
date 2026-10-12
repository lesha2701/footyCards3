import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchStrategoSquad, saveStrategoSquad } from "@/api/stratego";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft } from "@/components/icons";
import { ROLE_META, autoLayout, roleOfSlot } from "@/components/stratego/strategoMeta";
import { formatGameError } from "@/lib/errors";
import type { StrategoCard, StrategoSquad } from "@/types";

type Layout = Record<string, [number, number]>;

/** Pre-match preparation: cards per role + placement in the two home rows.
 *  Saved once here, then used for every match until changed — so a match
 *  starts immediately, and both sides placed independently in secret. */
export default function StrategoSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: squad, isLoading } = useQuery({ queryKey: ["stratego-squad"], queryFn: fetchStrategoSquad });
  const [cards, setCards] = useState<Record<string, number>>({});
  const [layout, setLayout] = useState<Layout>({});
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [pickerSlot, setPickerSlot] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!squad || dirty) return;
    setCards(Object.fromEntries(squad.card_slots.filter((s) => s.card).map((s) => [s.slot, s.card!.user_card_id!])));
    setLayout(squad.layout);
  }, [squad, dirty]);

  const cardById = useMemo(
    () => new Map((squad?.options ?? []).map((c) => [c.user_card_id!, c])),
    [squad],
  );

  const save = useMutation({
    mutationFn: () => saveStrategoSquad(cards, layout),
    onSuccess: (data) => {
      queryClient.setQueryData(["stratego-squad"], data);
      setDirty(false);
      setMessage({ ok: true, text: "Подготовка сохранена — можно играть" });
    },
    onError: (err) => setMessage({ ok: false, text: formatGameError(err, "Не удалось сохранить") }),
  });

  if (isLoading || !squad) return <ListSkeleton />;

  const size = squad.board_size;
  const slotAt = (r: number, c: number) => Object.keys(layout).find((s) => layout[s][0] === r && layout[s][1] === c);

  const onCell = (r: number, c: number) => {
    const here = slotAt(r, c);
    if (!selectedSlot) {
      if (here) setSelectedSlot(here);
      return;
    }
    if (here === selectedSlot) {
      setSelectedSlot(null);
      return;
    }
    const next = { ...layout, [selectedSlot]: [r, c] as [number, number] };
    if (here) next[here] = layout[selectedSlot];
    setLayout(next);
    setSelectedSlot(null);
    setDirty(true);
  };

  const onAuto = () => {
    setLayout(autoLayout(squad.slots, size));
    setSelectedSlot(null);
    setDirty(true);
  };

  const assign = (slot: string, card: StrategoCard) => {
    const next = { ...cards };
    const prevHolder = Object.keys(next).find((s) => next[s] === card.user_card_id);
    if (prevHolder && cards[slot] !== undefined) next[prevHolder] = cards[slot];
    else if (prevHolder) delete next[prevHolder];
    next[slot] = card.user_card_id!;
    setCards(next);
    setPickerSlot(null);
    setDirty(true);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play/stratego")} className="rounded-full bg-white/5 p-2 text-ink-mist active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Подготовка</h1>
      </div>

      {!squad.is_complete && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Нужно минимум {squad.cards_needed} карточек в коллекции, чтобы собрать состав.
        </p>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-mist">Роли</h2>
        {squad.card_slots.map((s) => {
          const card = cards[s.slot] !== undefined ? cardById.get(cards[s.slot]) : undefined;
          const meta = ROLE_META[s.role];
          return (
            <button
              key={s.slot}
              onClick={() => setPickerSlot(s.slot)}
              className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3 text-left active:scale-[0.98]"
            >
              <span className="text-xl">{meta.glyph}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-bold text-ink-chalk">{meta.label}</span>
                <span className="block truncate text-[11px] text-ink-mist">
                  {card ? `${card.display_name} · ${card.position}` : "Не выбрана"}
                </span>
              </span>
              {card && <span className="font-mono text-sm font-bold text-ink-chalk">{card.rating}</span>}
            </button>
          );
        })}
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-mist">Расстановка</h2>
          <button onClick={onAuto} className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95">
            🎲 Авто
          </button>
        </div>
        <p className="text-[11px] text-ink-mist-dim">
          Верхний ряд — ближний к сопернику. Нажми фишку, потом клетку — фишки поменяются местами.
        </p>
        <div
          className="grid w-full gap-1 rounded-2xl bg-accent-green/15 p-1.5"
          style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
        >
          {[0, 1].flatMap((r) =>
            Array.from({ length: size }, (_, c) => {
              const slot = slotAt(r, c);
              const role = slot ? roleOfSlot(slot) : null;
              const card = slot && cards[slot] !== undefined ? cardById.get(cards[slot]) : undefined;
              return (
                <button
                  key={`${r}:${c}`}
                  onClick={() => onCell(r, c)}
                  className={`flex aspect-square flex-col items-center justify-center rounded-lg leading-none ${
                    (r + c) % 2 === 0 ? "bg-accent-green/25" : "bg-accent-green/15"
                  } ${slot && slot === selectedSlot ? "ring-2 ring-accent-lime" : ""}`}
                >
                  {role && (
                    <span className="flex h-[88%] w-[88%] flex-col items-center justify-center rounded-md bg-accent-cyan text-bg-base">
                      <span className="text-base">{ROLE_META[role].glyph}</span>
                      {card && <span className="mt-0.5 font-mono text-[9px] font-bold">{card.rating}</span>}
                    </span>
                  )}
                </button>
              );
            }),
          )}
        </div>
      </section>

      {message && (
        <p className={`rounded-xl px-3 py-2 text-xs ${message.ok ? "bg-accent-green/10 text-accent-green" : "bg-red-500/10 text-red-400"}`}>
          {message.text}
        </p>
      )}

      <button
        onClick={() => save.mutate()}
        disabled={save.isPending || !squad.is_complete}
        className="rounded-2xl bg-floodlight py-4 text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
      >
        {save.isPending ? "Сохраняем..." : "Сохранить подготовку"}
      </button>

      {pickerSlot && (
        <CardPicker
          squad={squad}
          slot={pickerSlot}
          currentId={cards[pickerSlot]}
          onClose={() => setPickerSlot(null)}
          onPick={(card) => assign(pickerSlot, card)}
        />
      )}
    </div>
  );
}

function CardPicker({
  squad, slot, currentId, onClose, onPick,
}: {
  squad: StrategoSquad;
  slot: string;
  currentId?: number;
  onClose: () => void;
  onPick: (card: StrategoCard) => void;
}) {
  const def = squad.card_slots.find((s) => s.slot === slot)!;
  const eligible = def.eligible_positions;
  const fits = (c: StrategoCard) => !eligible || eligible.includes(c.position);
  const sorted = [...squad.options].sort((a, b) => Number(fits(b)) - Number(fits(a)) || b.rating - a.rating);
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="safe-bottom max-h-[75vh] w-full overflow-y-auto rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="font-display text-base font-bold text-ink-chalk">{ROLE_META[def.role].label}</p>
        <p className="mb-3 text-[11px] text-ink-mist">
          {ROLE_META[def.role].hint}
          {eligible && ` · Позиции: ${eligible.join(", ")}`}
          {def.role === "star" && " · Должна быть самой сильной картой состава"}
        </p>
        <div className="flex flex-col gap-1.5">
          {sorted.map((c) => (
            <button
              key={c.user_card_id}
              onClick={() => onPick(c)}
              className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-sm active:scale-[0.98] ${
                c.user_card_id === currentId ? "bg-accent-green/20" : "bg-white/5"
              } ${fits(c) ? "text-ink-chalk" : "text-ink-mist-dim"}`}
            >
              <span className="truncate">{c.display_name} · {c.position}</span>
              <span className="font-mono font-bold">{c.rating}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
