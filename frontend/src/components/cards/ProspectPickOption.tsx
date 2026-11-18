import type { Prospect } from "@/api/prospect";

/** «🌱 Мой воспитанник» above a mini-game's card list (CardPickerModal `header`). */
export function ProspectPickOption({ prospect, onPick }: { prospect: Prospect; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="mb-3 flex w-full items-center gap-3 rounded-2xl border border-path/40 bg-path/10 p-3 text-left active:scale-[0.99]"
    >
      <span className="text-2xl" aria-hidden>
        🌱
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">Мой воспитанник: {prospect.name}</span>
        <span className="block text-xs text-ink-mist">
          {prospect.age} лет · рейтинг {prospect.rating} · играет против сверстников и растёт
        </span>
      </span>
    </button>
  );
}

/** «+N опыта воспитаннику» after the claim (nothing when a card played). */
export function ProspectXpNote({ xp }: { xp: number | null | undefined }) {
  if (xp === null || xp === undefined) return null;
  return (
    <p className="mt-1 text-sm font-semibold text-path">
      +{xp} опыта воспитаннику{xp === 0 ? " (лимит опыта за матчи на сегодня)" : ""}
    </p>
  );
}
