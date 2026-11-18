import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Admin fields of «Воспитанник Академии» (GameConfig.prospect): every
 * number with a label, the lists and cosmetics as JSON. The backend returns
 * the effective values (stored overrides over prospect_service.DEFAULTS). */
const LABELS: [string, string][] = [
  ["start_age", "Возраст на старте, лет"],
  ["days_per_year", "Реальных дней в одном году возраста"],
  ["start_rating", "Рейтинг на старте"],
  ["peak_base", "Пик: база (пик = база + ★ × шаг)"],
  ["peak_per_star", "Пик: + за каждую ★ потенциала"],
  ["reveal_stage", "Ступень, на которой потенциал откроется сам (0 = Двор … 4 = Дебют)"],
  ["xp_per_point", "Опыта за +1 к рейтингу"],
  ["daily_xp_cap", "Лимит опыта за матчи в день"],
  ["otvetka_match_xp", "«Ответка»: опыта за матч"],
  ["otvetka_goal_xp", "«Ответка»: опыта за гол"],
  ["otvetka_win_xp", "«Ответка»: опыта за победу"],
  ["match_edge_per_point", "«Ответка»: шаг силы за 1 рейтинга сверх возрастной нормы"],
  ["training_xp", "Тренировка: опыта (× оценка 0.8 / 1 / 1.3)"],
  ["streak_days", "Серия тренировок: бонус каждые N дней"],
  ["streak_bonus_xp", "Серия тренировок: бонус опыта"],
  ["story_every_days", "История-развилка: раз в N дней"],
  ["mentor_xp_pct", "Наставник (карта «Академии»): +% опыта"],
  ["coach_xp_pct", "Личный тренер: +% опыта"],
  ["coach_days", "Личный тренер: дней"],
  ["coach_stars", "Личный тренер: цена, ⭐"],
  ["extra_training_stars", "Доп. тренировка: цена, ⭐"],
  ["extra_trainings_max", "Доп. тренировок за ⭐ в день"],
  ["scout_stars", "Скаут (раскрыть потенциал): цена, ⭐"],
  ["cohort_size", "Рейтинг набора: мест"],
  ["manager_wage_max", "«Менеджер»: потолок зарплаты воспитанника/выпускника за сезон"],
  ["game_match_xp", "Пенальти / Штрафной / 1 на 1: опыта за игру"],
  ["game_goal_xp", "Пенальти / Штрафной / 1 на 1: опыта за гол"],
  ["game_win_xp", "Пенальти / Штрафной / 1 на 1: опыта за победу"],
  ["graduation_coins", "Выпускной: монет владельцу"],
  ["first_min_potential", "Первый воспитанник игрока: потенциал не ниже ★"],
  ["potential_streak_days", "Потенциал: +★ за каждые N дней тренировок подряд"],
  ["potential_streak_max", "Потенциал: максимум ★ за серии"],
  ["trial_matches", "Испытание ступени: первые N «Ответок» на ступени"],
  ["trial_wins", "Испытание ступени: побед из них для +★"],
  ["dynasty_peak_bonus", "Династия: + к рейтингу на пике за каждое прошлое поколение"],
  ["dynasty_peak_max", "Династия: максимум + к пику"],
  ["academy_levels_per_peak", "Академия: +1 к пику за каждые N уровней (0 = выкл.)"],
  ["position_stage", "Ступень, на которой тренер предлагает позицию (0 = Двор … 4 = Дебют)"],
  ["position_options", "Сколько позиций предлагает тренер"],
  ["deficit_share_pct", "Дефицит: доля линии ниже N% от её доли в составе (1/4/4/2 из 11)"],
  ["deficit_xp_pct", "Дефицитная позиция: +% опыта"],
  ["deficit_value_pct", "Дефицитная позиция: +% к цене в «Менеджере»"],
  ["position_change_stars", "Смена позиции: цена, ⭐"],
  ["duel_hours", "Дуэль друзей: часов на свой матч"],
  ["duels_per_day", "Дуэль друзей: вызовов в день"],
  ["duel_win_xp", "Дуэль друзей: опыта победителю"],
  ["notify_hour", "Вечерний дайджест бота: час (местное время)"],
  ["notify_active_days", "Дайджест: только заходившим за N дней"],
  ["bday_stars", "Коробка на день рождения: цена, ⭐"],
  ["bday_xp", "Коробка на день рождения: опыта"],
  ["gift_training_stars", "Подарок другу «тренировка»: ⭐"],
  ["gift_coach_stars", "Подарок другу «личный тренер»: ⭐"],
];

const JSON_KEYS: [string, string][] = [
  ["stage_ages", "Возраст начала ступеней: Двор, Школа, Юноши, U-19, Дебют"],
  ["stage_caps", "Потолок рейтинга ступеней: Двор, Школа, Юноши, U-19 (у Дебюта — пик)"],
  ["potential_weights", "Веса потенциала ★1…★5 при создании"],
  ["cosmetics", "Косметика: код → {coins, stars}; 0 = не продаётся за эту валюту"],
  ["spec_stages", "Ступени, на которых выбирается талант (0 = Двор … 4 = Дебют)"],
  ["trial_stages", "Ступени с испытанием на +★ (0 = Двор … 4 = Дебют)"],
  ["week_prizes", "Турнир набора: призы за 1, 2, 3 место, монет"],
  ["spec_effects", "Таланты: код → {goal_pct, win_pct, match_pct, train_pct, story_pct, atk, def}"],
  ["seasons", "Сезонная косметика: сезон → {from: \"MM-DD\", to: \"MM-DD\"}"],
];

export default function ProspectFields({ value, onChange }: {
  value: Record<string, unknown> | undefined; onChange: (next: Record<string, unknown>) => void;
}) {
  const data = value ?? {};
  return (
    <div className="grid grid-cols-2 gap-3">
      <label className="col-span-2 flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={data.enabled !== false} onChange={(e) => onChange({ ...data, enabled: e.target.checked })} />
        Воспитанник доступен (создание, рост, покупки)
      </label>
      {LABELS.map(([key, label]) => (
        <label key={key} className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">{label}</span>
          <input
            type="number" min={0} value={Number(data[key] ?? 0)}
            onChange={(e) => onChange({ ...data, [key]: Number(e.target.value) })}
            className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
          />
        </label>
      ))}
      {JSON_KEYS.map(([key, label]) => (
        <label key={key} className="col-span-2 flex flex-col gap-1">
          <span className="text-xs text-slate-400">{label}</span>
          <textarea
            rows={["cosmetics", "spec_effects", "seasons"].includes(key) ? 6 : 1}
            defaultValue={JSON.stringify(data[key] ?? [], null, ["cosmetics", "spec_effects", "seasons"].includes(key) ? 1 : 0)}
            onBlur={(e) => {
              try {
                onChange({ ...data, [key]: JSON.parse(e.target.value || "[]") });
                e.target.classList.remove("ring-1", "ring-red-500");
              } catch {
                e.target.classList.add("ring-1", "ring-red-500");
              }
            }}
            className="rounded-lg bg-bg-surface px-3 py-2 font-mono text-xs outline-none"
          />
        </label>
      ))}
    </div>
  );
}

interface ProspectStats {
  total: number; growing: number; graduates: number; active_week: number; stars: number; coins_cosmetics: number; duels: number;
  avg_graduate_rating: number | null; by_stage: { stage: string; count: number }[];
}

/** GET /admin/games/prospect-stats: how many raise a child and where they are. */
export function ProspectStatsPanel() {
  const { data } = useQuery({
    queryKey: ["admin-prospect-stats"],
    queryFn: async () => (await api.get<ProspectStats>("/admin/games/prospect-stats")).data,
  });
  if (!data) return null;
  const tiles: [string, string | number][] = [
    ["Растут", data.growing], ["Активны за 7 дн.", data.active_week], ["Выпускников", data.graduates],
    ["Ср. рейтинг выпуска", data.avg_graduate_rating ?? "—"], ["Дуэлей", data.duels], ["⭐ получено", data.stars],
  ];
  return (
    <div className="mb-3 flex flex-col gap-2" data-testid="prospect-stats">
      <div className="grid grid-cols-3 gap-2">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-black/20 px-2 py-1.5">
            <p className="font-mono text-base font-bold">{value}</p>
            <p className="text-micro text-slate-400">{label}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400">По ступеням: {data.by_stage.map((s) => `${s.stage} ${s.count}`).join(" · ")}</p>
    </div>
  );
}
