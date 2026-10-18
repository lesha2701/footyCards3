import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCardFilterOptions, saveCardFilterDefault } from "@/api/collection";
import { activeCount, EMPTY_FILTER, sameFilter, toSaved, type CardFilter } from "@/lib/cardFilter";
import { formatGameError } from "@/lib/errors";
import { POSITION_LABELS, RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary", "diamond"];
const POSITIONS = Object.keys(POSITION_LABELS);

/** Rarity chips + a «Фильтры» panel (country, club, position, sort) with
 * «Сохранить по умолчанию»: the saved filter is applied whenever the
 * collection, the album or the Forge opens. */
export default function CardFilterBar({
  filter,
  onChange,
  defaultFilter,
  showRarity = true,
  showSort = true,
  showSkill = true,
  extraPanel,
  extraActive = 0,
}: {
  filter: CardFilter;
  onChange: (next: CardFilter) => void;
  defaultFilter: CardFilter;
  showRarity?: boolean;
  showSort?: boolean;
  showSkill?: boolean;
  /** More fields shown inside the «Фильтры» panel (e.g. the collection picker). */
  extraPanel?: React.ReactNode;
  /** How many of those extra fields are set (counts in the «Фильтры» badge). */
  extraActive?: number;
}) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: options } = useQuery({ queryKey: ["card-filter-options"], queryFn: fetchCardFilterOptions, enabled: open });
  const set = (patch: Partial<CardFilter>) => { setNotice(null); onChange({ ...filter, ...patch }); };

  const save = useMutation({
    mutationFn: () => saveCardFilterDefault(sameFilter(filter, EMPTY_FILTER) ? null : toSaved(filter)),
    onSuccess: (saved) => {
      queryClient.setQueryData(["card-filter-default"], saved);
      setNotice(saved ? "Фильтр сохранён — он будет включаться сам" : "Фильтр по умолчанию сброшен");
    },
    onError: (err) => setNotice(formatGameError(err, "Не удалось сохранить фильтр")),
  });

  const extra = [filter.country, filter.club, filter.position ? POSITION_LABELS[filter.position] : null].filter(Boolean);
  const count = activeCount(filter) + extraActive;
  const isDefault = sameFilter(filter, defaultFilter);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${
            open || extra.length ? "bg-accent-cyan/20 text-accent-cyan" : "bg-white/5 text-ink-mist"
          }`}
        >
          ⚙ Фильтры{count > 0 ? ` · ${count}` : ""}
        </button>
        {showRarity && (
          <>
            <Chip active={filter.rarity === null} label="Все" onClick={() => set({ rarity: null })} />
            {RARITIES.map((r) => (
              <Chip key={r} active={filter.rarity === r} label={RARITY_LABELS[r]} onClick={() => set({ rarity: r })} />
            ))}
          </>
        )}
        {showSkill && <Chip active={filter.has_skill} label="С навыком" onClick={() => set({ has_skill: !filter.has_skill })} />}
      </div>

      {!open && extra.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {filter.country && <Removable label={filter.country} onRemove={() => set({ country: null })} />}
          {filter.club && <Removable label={filter.club} onRemove={() => set({ club: null })} />}
          {filter.position && <Removable label={POSITION_LABELS[filter.position]} onRemove={() => set({ position: null })} />}
        </div>
      )}

      {open && (
        <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3" role="group" aria-label="Фильтры карточек">
          <div className="grid grid-cols-2 gap-2">
            <Select label="Страна" value={filter.country} onChange={(v) => set({ country: v })}
              options={(options?.countries ?? withCurrent(filter.country)).map((c) => [c, c])} />
            <Select label="Клуб" value={filter.club} onChange={(v) => set({ club: v })}
              options={(options?.clubs ?? withCurrent(filter.club)).map((c) => [c, c])} />
            <Select label="Позиция" value={filter.position} onChange={(v) => set({ position: v })}
              options={POSITIONS.map((p) => [p, `${p} · ${POSITION_LABELS[p]}`])} />
            {extraPanel}
            {showSort && (
              <label className="flex flex-col gap-1">
                <span className="text-micro text-ink-mist-dim">Сортировка</span>
                <select
                  value={filter.sort_by}
                  onChange={(e) => set({ sort_by: e.target.value as CardFilter["sort_by"] })}
                  className="rounded-xl bg-bg-raised px-2.5 py-2 text-xs text-ink-chalk outline-none"
                >
                  <option value="acquired_at">По дате получения</option>
                  <option value="rating">По рейтингу</option>
                  <option value="rarity">По редкости</option>
                </select>
              </label>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => set(EMPTY_FILTER)}
              className="min-h-[40px] flex-1 rounded-xl bg-white/5 text-xs font-semibold text-ink-mist"
            >
              Очистить
            </button>
            <button
              type="button"
              onClick={() => save.mutate()}
              disabled={save.isPending || isDefault}
              className="min-h-[40px] flex-[1.6] rounded-xl bg-accent-lime text-xs font-bold text-bg-base disabled:opacity-40"
            >
              {isDefault ? "Это фильтр по умолчанию" : "Сохранить по умолчанию"}
            </button>
          </div>
          <p className="text-micro text-ink-mist-dim">
            Фильтр по умолчанию сам включается в коллекции, альбоме и Кузнице.
          </p>
        </div>
      )}
      {notice && <p className="text-xs text-accent-lime" role="status">{notice}</p>}
    </div>
  );
}

function withCurrent(value: string | null): string[] {
  return value ? [value] : [];
}

function Chip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}

function Removable({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <button
      type="button"
      onClick={onRemove}
      aria-label={`Убрать фильтр ${label}`}
      className="flex items-center gap-1 rounded-full bg-accent-cyan/15 px-2.5 py-1 text-caption font-semibold text-accent-cyan"
    >
      {label} <span aria-hidden>×</span>
    </button>
  );
}

function Select({
  label, value, onChange, options,
}: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-ink-mist-dim">{label}</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-xl bg-bg-raised px-2.5 py-2 text-xs text-ink-chalk outline-none"
      >
        <option value="">Все</option>
        {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </label>
  );
}
