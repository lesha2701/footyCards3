import { useQuery } from "@tanstack/react-query";

import { fetchLuckyBoardEstimate } from "@/admin/api";
import type { GameConfig, LuckyBoardOutcomeConfig, LuckyBoardSideConfig } from "@/admin/types";

const SIDES = ["free", "paid"] as const;
const PRIZE_FIELDS: [keyof LuckyBoardSideConfig, string][] = [["coins", "монеты"], ["tokens", "жетоны"], ["shards", "осколки"]];

/** «Табло удачи»: prices, limits and the weight + prize table the server rolls on
 * (and the game shows as odds). Paid spins never pay coins — the server refuses it. */
export default function LuckyBoardAdminSection({ form, setForm }: { form: GameConfig; setForm: (f: GameConfig) => void }) {
  const { data: estimate } = useQuery({ queryKey: ["admin-lucky-board-estimate"], queryFn: fetchLuckyBoardEstimate });
  const outcomes = form.lucky_board_outcomes ?? [];
  const totals = {
    free: outcomes.reduce((s, o) => s + (o.free_weight || 0), 0),
    paid: outcomes.reduce((s, o) => s + (o.paid_weight || 0), 0),
  };

  const setOutcome = (index: number, next: LuckyBoardOutcomeConfig) =>
    setForm({ ...form, lucky_board_outcomes: outcomes.map((o, i) => (i === index ? next : o)) });

  const num = (key: keyof GameConfig, label: string) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number"
        value={(form[key] as number | null) ?? 0}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">«Табло удачи»</p>
      <p className="mb-3 text-xs text-slate-500">
        Цена запуска фиксированная, ставок нет. Призы платного запуска — только жетоны навыков, осколки и косметика
        (привязаны к аккаунту); монеты в платной колонке сервер не примет. Шансы в игре показываются из этой же таблицы.
      </p>
      <label className="mb-3 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.lucky_board_enabled}
          onChange={(e) => setForm({ ...form, lucky_board_enabled: e.target.checked })}
        />
        Игра включена (запуски и покупка)
      </label>
      <div className="grid grid-cols-2 gap-3">
        {num("lucky_board_free_per_day", "Бесплатных запусков в день")}
        {num("lucky_board_stars_cost", "Платный запуск, ⭐")}
        {num("lucky_board_paid_daily_limit", "Платных запусков в день (покупок, 0 = выкл)")}
        {num("lucky_board_hourly_limit", "Запусков в час (все)")}
        {num("lucky_board_shards_per_token", "Осколков на 1 жетон")}
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">ID значка за «Бутсу» (пусто = нет)</span>
          <input
            type="number"
            value={form.lucky_board_badge_id ?? ""}
            onChange={(e) => setForm({ ...form, lucky_board_badge_id: e.target.value ? Number(e.target.value) : null })}
            className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
          />
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-xs text-slate-400">ID косметики за платную «Бутсу», через запятую</span>
          <input
            value={(form.lucky_board_cosmetic_ids ?? []).join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                lucky_board_cosmetic_ids: e.target.value.split(/[ ,]+/).map(Number).filter((n) => Number.isInteger(n) && n > 0),
              })
            }
            className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
          />
        </label>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="text-slate-400">
            <tr>
              <th className="py-1 text-left">Исход</th>
              {SIDES.map((side) => (
                <th key={side} className="py-1 text-left" colSpan={side === "paid" ? 6 : 5}>
                  {side === "free" ? "Бесплатный" : "Платный"}: вес · % · {side === "paid" ? "жетоны · осколки · косметика" : "монеты · жетоны · осколки"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {outcomes.map((o, index) => (
              <tr key={o.code} className="border-t border-white/5">
                <td className="py-1 pr-2">
                  <input
                    value={o.label}
                    onChange={(e) => setOutcome(index, { ...o, label: e.target.value })}
                    className="w-24 rounded bg-bg-base px-2 py-1"
                  />
                  <span className="ml-1 text-slate-500">{o.code}</span>
                </td>
                {SIDES.map((side) => {
                  const weightKey = side === "free" ? "free_weight" : "paid_weight";
                  const share = totals[side] ? (o[weightKey] / totals[side]) * 100 : 0;
                  const fields = side === "free" ? PRIZE_FIELDS : PRIZE_FIELDS.filter(([k]) => k !== "coins");
                  return [
                    <td key={`${side}-w`} className="py-1 pr-1">
                      <input
                        type="number" min={0} value={o[weightKey]}
                        onChange={(e) => setOutcome(index, { ...o, [weightKey]: Number(e.target.value) })}
                        className="w-16 rounded bg-bg-base px-2 py-1"
                      />
                    </td>,
                    <td key={`${side}-p`} className="whitespace-nowrap py-1 pr-2 font-mono text-slate-300">{share.toFixed(1)}%</td>,
                    ...fields.map(([k, label]) => (
                      <td key={`${side}-${k}`} className="py-1 pr-1">
                        <input
                          type="number" min={0} title={label} value={Number(o[side][k] ?? 0)}
                          onChange={(e) => setOutcome(index, { ...o, [side]: { ...o[side], [k]: Number(e.target.value) } })}
                          className="w-14 rounded bg-bg-base px-2 py-1"
                        />
                      </td>
                    )),
                    ...(side === "paid"
                      ? [
                        <td key="paid-c" className="py-1">
                          <input
                            type="checkbox" checked={!!o.paid.cosmetic}
                            onChange={(e) => setOutcome(index, { ...o, paid: { ...o.paid, cosmetic: e.target.checked } })}
                          />
                        </td>,
                      ]
                      : []),
                  ];
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Косметика: игрок получает случайную ещё не полученную вещь из списка выше (или значок); если всё собрано — осколки
        этой строки.
      </p>
      {estimate && (
        <p className="mt-2 text-xs text-slate-300">
          Сохранённая таблица в среднем за запуск: бесплатный — {estimate.free.coins} монет и {estimate.free.tokens} жетона;
          платный — {estimate.paid.tokens} жетона (с осколками), косметика с шансом {(estimate.paid.cosmetic_chance * 100).toFixed(1)}%.
        </p>
      )}
    </section>
  );
}
