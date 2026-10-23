import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchMagnateDefaults } from "@/admin/api";
import type { MagnateBoardConfig, MagnateBoardCellConfig } from "@/admin/types";

const TYPE_LABELS: Record<string, string> = {
  start: "Старт", club: "Клуб", stadium: "Стадион", var: "VAR", transfer: "Трансферное окно",
  fine: "Штраф", jail: "Дисквалификация", break: "Перерыв", go_to_jail: "Красная карточка",
  chance: "Пенальти 50/50", red_card: "Пропуск хода",
};

interface Props {
  board: MagnateBoardConfig | null;
  cards: Record<string, unknown> | null;
  onChange: (board: MagnateBoardConfig | null, cards: Record<string, unknown> | null) => void;
}

/** «Футбольный магнат» board: group names/colours and each cell's name,
 *  price, rents and building cost. Cell types and order stay as they are
 *  (the backend validates the result on save). null = built-in default. */
export default function AdminMagnateBoardEditor({ board, cards, onChange }: Props) {
  const { data: defaults } = useQuery({ queryKey: ["admin-magnate-defaults"], queryFn: fetchMagnateDefaults });
  const [cardsText, setCardsText] = useState<string | null>(null);
  const [cardsError, setCardsError] = useState<string | null>(null);
  const current = board ?? defaults?.board ?? null;
  const currentCards = cards ?? defaults?.cards ?? null;
  if (!current) return <p className="text-xs text-slate-500">Загрузка поля...</p>;

  const setCell = (index: number, patch: Partial<MagnateBoardCellConfig>) =>
    onChange({ ...current, cells: current.cells.map((c, i) => (i === index ? { ...c, ...patch } : c)) }, cards);
  const setGroup = (index: number, patch: Partial<{ name: string; color: string }>) =>
    onChange({ ...current, groups: current.groups.map((g, i) => (i === index ? { ...g, ...patch } : g)) }, cards);

  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Поле {board ? "(изменено)" : "(стандартное)"}</p>
        {board && (
          <button onClick={() => onChange(null, cards)} className="rounded-lg bg-white/5 px-3 py-1 text-xs text-slate-300">
            Вернуть стандартное
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {current.groups.map((g, i) => (
          <label key={i} className="flex items-center gap-2 text-xs">
            <input type="color" value={g.color} onChange={(e) => setGroup(i, { color: e.target.value })} className="h-7 w-8 rounded" />
            <input
              value={g.name}
              onChange={(e) => setGroup(i, { name: e.target.value })}
              className="min-w-0 flex-1 rounded-lg bg-bg-base px-2 py-1.5 outline-none"
            />
          </label>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-xs">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-1">#</th><th>Тип</th><th>Название</th><th>Группа</th><th>Цена</th>
              <th>Аренда: база, 1–3 трибуны, арена</th><th>Стройка</th>
            </tr>
          </thead>
          <tbody>
            {current.cells.map((c, i) => (
              <tr key={i} className="border-t border-white/5">
                <td className="py-1 pr-1 text-slate-500">{i}</td>
                <td className="pr-1 text-slate-400">{TYPE_LABELS[c.type] ?? c.type}</td>
                <td className="pr-1">
                  <input value={c.name} onChange={(e) => setCell(i, { name: e.target.value })} className="w-full rounded bg-bg-base px-1.5 py-1 outline-none" />
                </td>
                <td className="pr-1">
                  {c.type === "club" && (
                    <select
                      value={c.group ?? 0}
                      onChange={(e) => setCell(i, { group: Number(e.target.value) })}
                      className="rounded bg-bg-base px-1 py-1"
                    >
                      {current.groups.map((g, gi) => <option key={gi} value={gi}>{g.name}</option>)}
                    </select>
                  )}
                </td>
                <td className="pr-1">
                  {(c.type === "club" || c.type === "stadium") && (
                    <input type="number" value={c.price ?? 0} onChange={(e) => setCell(i, { price: Number(e.target.value) })} className="w-16 rounded bg-bg-base px-1.5 py-1 outline-none" />
                  )}
                </td>
                <td className="pr-1">
                  {c.type === "club" && (
                    <input
                      defaultValue={(c.rent ?? []).join(", ")}
                      onBlur={(e) => setCell(i, { rent: e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => Number.isFinite(v)) })}
                      className="w-full rounded bg-bg-base px-1.5 py-1 outline-none"
                    />
                  )}
                </td>
                <td>
                  {c.type === "club" && (
                    <input type="number" value={c.build_cost ?? 0} onChange={(e) => setCell(i, { build_cost: Number(e.target.value) })} className="w-14 rounded bg-bg-base px-1.5 py-1 outline-none" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-xs text-slate-400">
          Карточки событий (JSON: var / transfer; kind: money, move_to, move_by, nearest_stadium, jail, jail_card,
          collect_each, pay_each, repairs) {cards ? "(изменены)" : "(стандартные)"}
        </span>
        <textarea
          rows={8}
          value={cardsText ?? JSON.stringify(currentCards, null, 2)}
          onChange={(e) => setCardsText(e.target.value)}
          onBlur={() => {
            if (cardsText === null) return;
            try {
              onChange(board, JSON.parse(cardsText));
              setCardsError(null);
            } catch {
              setCardsError("Некорректный JSON — карточки не изменены");
            }
          }}
          className="rounded-lg bg-bg-base px-3 py-2 font-mono text-caption outline-none"
        />
        {cardsError && <span className="text-xs text-red-400">{cardsError}</span>}
        {cards && (
          <button onClick={() => { setCardsText(null); onChange(board, null); }} className="self-start rounded-lg bg-white/5 px-3 py-1 text-xs text-slate-300">
            Вернуть стандартные карточки
          </button>
        )}
      </label>
    </div>
  );
}
