import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchStrategoSquad, saveStrategoSquad } from "@/api/stratego";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft } from "@/components/icons";
import { CELL_LINES, GRASS_STYLE } from "@/components/stratego/boardStyle";
import RoleIcon from "@/components/stratego/RoleIcon";
import { PieceChip } from "@/components/stratego/StrategoBoard";
import { ROLE_META, autoLayout, roleOfSlot, slotLabel } from "@/components/stratego/strategoMeta";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS, RARITY_ORDER } from "@/lib/rarity";
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

  // Live rarity counters over the current (possibly unsaved) picks; the
  // server re-checks the same rules on save and at match start.
  const picked = Object.values(cards).map((id) => cardById.get(id)).filter(Boolean) as StrategoCard[];
  // «Академия» cards count against their own limit, not the diamond one.
  const count = (r: string) =>
    picked.filter((c) => (r === "path" ? !!c.is_path : c.rarity === r && !(r === "diamond" && c.is_path))).length;
  const lim = squad.rarity_limits;
  const rules = [
    { label: "Легендарных", value: count("legendary"), ok: count("legendary") <= lim.max_legendary, hint: `≤${lim.max_legendary}` },
    { label: "Диамантов", value: count("diamond"), ok: count("diamond") <= lim.max_diamond, hint: `≤${lim.max_diamond}` },
    ...(count("path") > 0
      ? [{ label: "Академия", value: count("path"), ok: count("path") <= (lim.max_path ?? 1), hint: `≤${lim.max_path ?? 1}` }]
      : []),
    { label: "Редких", value: count("rare"), ok: count("rare") >= lim.min_rare, hint: `≥${lim.min_rare}` },
    { label: "Обычных", value: count("common"), ok: count("common") >= lim.min_common, hint: `≥${lim.min_common}` },
  ];
  const full = picked.length === squad.cards_needed;
  const caps = squad.role_max_rarity ?? {};
  const tooRareRoles = [...new Set(Object.entries(cards).flatMap(([slot, id]) => {
    const c = cardById.get(id);
    const cap = caps[roleOfSlot(slot)];
    return c && cap && RARITY_ORDER[c.rarity] > RARITY_ORDER[cap] ? [ROLE_META[roleOfSlot(slot)].label] : [];
  }))];
  const valid = full && rules.every((r) => r.ok) && tooRareRoles.length === 0;

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

      {squad.options.length < squad.cards_needed && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Нужно минимум {squad.cards_needed} карточек в коллекции, чтобы собрать состав.
        </p>
      )}

      <div className="grid grid-cols-4 gap-1.5">
        {rules.map((r) => (
          <div key={r.label} className={`rounded-xl px-2 py-1.5 text-center ${r.ok ? "bg-bg-surface" : "bg-red-500/15"}`}>
            <p className={`font-mono text-sm font-bold ${r.ok ? "text-ink-chalk" : "text-red-400"}`}>
              {r.value}<span className="text-micro font-normal text-ink-mist"> {r.hint}</span>
            </p>
            <p className="text-micro text-ink-mist">{r.label}</p>
          </div>
        ))}
      </div>
      {Object.keys(caps).length > 0 && (
        <p className="-mt-2 text-caption text-ink-mist-dim">
          {(Object.entries(caps) as [keyof typeof ROLE_META, keyof typeof RARITY_LABELS][])
            .map(([role, cap]) => `${ROLE_META[role].label} — не выше: ${RARITY_LABELS[cap].toLowerCase()}`)
            .join(" · ")}
        </p>
      )}
      {tooRareRoles.length > 0 && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Слишком редкая карточка на роли: {tooRareRoles.join(", ")} — замени её.
        </p>
      )}
      {!dirty && squad.violations.length > 0 && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Из твоей коллекции не собрать состав по правилам: {squad.violations.join("; ")}.
        </p>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="font-mono text-caption uppercase tracking-wider text-ink-mist">Роли</h2>
        {squad.card_slots.map((s) => {
          const card = cards[s.slot] !== undefined ? cardById.get(cards[s.slot]) : undefined;
          const meta = ROLE_META[s.role];
          return (
            <button
              key={s.slot}
              onClick={() => setPickerSlot(s.slot)}
              className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3 text-left active:scale-[0.98]"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bg-raised text-accent-lime">
                <RoleIcon role={s.role} size={20} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-bold text-ink-chalk" title={meta.hint}>{slotLabel(s.slot)}</span>
                <span className="block truncate text-caption text-ink-mist">
                  {card ? `${card.is_my_player ? "Мой игрок: " : ""}${card.display_name} · ${card.position}` : "Не выбрана"}
                </span>
              </span>
              {card && <span className="font-mono text-sm font-bold text-ink-chalk">{card.rating}</span>}
            </button>
          );
        })}
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-caption uppercase tracking-wider text-ink-mist">Расстановка</h2>
          <button onClick={onAuto} className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95">
            Авто
          </button>
        </div>
        <p className="text-caption text-ink-mist-dim">
          Верхний ряд — ближний к сопернику. Нажми фишку, потом клетку — фишки поменяются местами.
        </p>
        <div
          className="grid w-full overflow-hidden rounded-2xl border border-white/10 p-1 shadow-glow"
          style={{ ...GRASS_STYLE, gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
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
                  className={`flex aspect-square flex-col items-center justify-center leading-none ${CELL_LINES} ${
                    slot && slot === selectedSlot ? "bg-accent-lime/20 ring-2 ring-inset ring-accent-lime" : ""
                  }`}
                >
                  {role && (
                    <PieceChip
                      selected={slot === selectedSlot}
                      piece={{
                        id: r * size + c, mine: true, row: r, col: c, hidden: false, revealed: false, moved: false,
                        role, power: card?.rating ?? null, card: card ?? null,
                      }}
                    />
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
        disabled={save.isPending || !valid}
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
  const cap = squad.role_max_rarity?.[def.role];
  const allowed = (c: StrategoCard) => !cap || RARITY_ORDER[c.rarity] <= RARITY_ORDER[cap];
  const sorted = [...squad.options].sort(
    (a, b) => Number(allowed(b)) - Number(allowed(a)) || Number(fits(b)) - Number(fits(a)) || b.rating - a.rating,
  );
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="safe-bottom max-h-[75vh] w-full overflow-y-auto rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="font-display text-base font-bold text-ink-chalk">{slotLabel(slot)}</p>
        <p className="mb-3 text-caption text-ink-mist">
          {ROLE_META[def.role].hint}
          {eligible && ` · Позиции: ${eligible.join(", ")}`}
          {def.role === "star" && " · Должна быть самой сильной картой состава"}
          {cap && ` · Не выше: ${RARITY_LABELS[cap].toLowerCase()}`}
        </p>
        <div className="flex flex-col gap-1.5">
          {sorted.map((c) => (
            <button
              key={c.user_card_id}
              onClick={() => allowed(c) && onPick(c)}
              disabled={!allowed(c)}
              className={`flex items-center justify-between rounded-xl px-3 py-2 text-left text-sm active:scale-[0.98] disabled:opacity-35 ${
                c.user_card_id === currentId ? "bg-accent-green/20" : "bg-white/5"
              } ${fits(c) ? "text-ink-chalk" : "text-ink-mist-dim"}`}
            >
              <span className="truncate">
                {c.is_my_player && <span className="mr-1 rounded bg-accent-lime px-1 text-micro font-bold text-bg-base">Мой игрок</span>}
                {c.display_name} · {c.position}
              </span>
              <span className="font-mono font-bold">{c.rating}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
