/** Admin fields of «Кабинет президента» (GameConfig.manager_finance): every
 * number with a label, sponsors / tours / shirt brands as JSON. The backend
 * returns the effective values (stored overrides over its defaults). */
const LABELS: [string, string][] = [
  ["sponsor_marketing_pct_per_level", "Спонсоры: +% за уровень «Отдела маркетинга»"],
  ["loan_grant_pct", "Кредит: лимит, % гранта дивизиона"],
  ["loan_value_pct", "Кредит: лимит, % стоимости клуба (берётся меньший)"],
  ["loan_min_eur", "Кредит: минимум, €"],
  ["loan_seasons_max", "Кредит: срок, сезонов максимум"],
  ["loan_rate_pct", "Кредит: ставка за сезон, %"],
  ["loan_rate_cut_per_level", "Кредит: −% ставки за уровень «Бухгалтерии»"],
  ["loan_rate_min_pct", "Кредит: ставка не ниже, %"],
  ["loan_penalty_pct", "Кредит: штраф за просрочку, % долга"],
  ["value_per_base_level", "Стоимость клуба: € за уровень «Клубной базы»"],
  ["value_per_fan", "Стоимость клуба: € за фаната"],
  ["value_per_title", "Стоимость клуба: € за чемпионство"],
  ["fan_ticket_eur", "Фанаты с турне: € за фаната за домашний матч (× % дивизиона)"],
  ["kit_base_eur", "Спонсор на форме: € за сезон, база (× % дивизиона)"],
  ["kit_eur_per_level", "Спонсор на форме: +€ за сезон за уровень «Клубного магазина»"],
  ["kit_long_bonus_pct", "Спонсор на форме: +% за каждый сезон контракта сверх первого"],
  ["kit_seasons_max", "Спонсор на форме: сезонов максимум"],
  ["tour_hotel_cut_per_level", "Турне: −% расходов за уровень «Клубного отеля»"],
  ["tour_media_fans_pct_per_level", "Турне: +% фанатов за уровень «Медиацентра»"],
  ["tv_discount_pct", "ТВ-права: скидка, %"],
  ["tv_media_cut_per_level", "ТВ-права: −% скидки за уровень «Медиацентра»"],
  ["tv_discount_min_pct", "ТВ-права: скидка не меньше, %"],
  ["deposit_rate_pct", "Депозит: ставка за сезон, %"],
  ["deposit_rate_per_level", "Депозит: +% за уровень «Бухгалтерии»"],
  ["deposit_max_budget_pct", "Депозит: не больше, % бюджета"],
  ["deposit_min_eur", "Депозит: минимум, €"],
  ["venture_win_pct", "Венчур: шанс успеха, %"],
  ["venture_multiplier", "Венчур: множитель при успехе"],
  ["venture_max_budget_pct", "Венчур: не больше, % бюджета"],
  ["venture_min_eur", "Венчур: минимум, €"],
  ["farm_fee_pct", "Фарм-клуб: цена, % гранта дивизиона"],
  ["farm_loan_cut_pct", "Фарм-клуб: аренды дешевле на, %"],
  ["farm_kid_rating", "Фарм-клуб: воспитанники сильнее на, рейтинга"],
  ["farm_kid_per_training_level", "Фарм-клуб: + рейтинга воспитанникам за уровень «Тренировочного центра»"],
  ["shares_total", "Биржа: акций у клуба"],
  ["ipo_max_pct", "Биржа: IPO не больше, % акций"],
  ["holder_max_pct", "Биржа: в одних руках не больше, % акций клуба"],
  ["exchange_fee_pct", "Биржа: комиссия сделки, % (сгорает)"],
  ["buyback_premium_pct", "Биржа: премия акционерам при выкупе, %"],
  ["exchange_spread_pct", "Биржа: мгновенная продажа бирже дешевле цены на, %"],
  ["ask_band_pct", "Биржа: заявка на продажу в пределах ±% от цены"],
  ["ipo_season_cap_pct", "Биржа: IPO приносит клубу за сезон не больше, % гранта"],
  ["price_ppg_pct", "Цена акции: +% за очко в среднем за матч сверх 1,4 (сезон)"],
  ["price_form_pct", "Цена акции: +% за очко сверх 1,4 (последние 5 матчей)"],
  ["price_min_pct", "Цена акции: не ниже, % базы"],
  ["price_max_pct", "Цена акции: не выше, % базы"],
  ["dividend_pct", "Дивиденды: % прибыли сезона акционерам"],
  ["bond_rate_min_pct", "Облигации: купон от, % за сезон"],
  ["bond_rate_max_pct", "Облигации: купон до, % за сезон"],
  ["bond_unit_eur", "Облигации: номинал одной, €"],
  ["bond_grant_pct", "Облигации: долг не больше, % гранта дивизиона"],
  ["bond_value_pct", "Облигации: долг не больше, % стоимости клуба (берётся меньший)"],
  ["bond_seasons_max", "Облигации: срок, сезонов максимум"],
  ["bond_holder_max_pct", "Облигации: в одних руках не больше, % выпуска"],
  ["ticket_min_pct", "Билеты: цена от, % базовой"],
  ["ticket_max_pct", "Билеты: цена до, % базовой"],
  ["ticket_elasticity", "Билеты: −% зрителей за +1% цены"],
  ["ticket_attendance_min_pct", "Билеты: зрителей не меньше, %"],
  ["ticket_attendance_max_pct", "Билеты: зрителей не больше, % (дешёвые билеты)"],
  ["ticket_support_pct", "Билеты: поддержка дома, % к линиям за 1% зрителей сверх 100"],
  ["ticket_fans_per_pct", "Билеты: болельщиков за сезон за 1% зрителей сверх 100"],
  ["injury_chance_pct", "Травмы: шанс после матча, %"],
  ["injury_rounds_min", "Травмы: пропуск от, туров"],
  ["injury_rounds_max", "Травмы: пропуск до, туров"],
  ["injury_treatment_pct", "Травмы: лечение, % стоимости игрока"],
  ["insurance_premium_pct", "Страховка: взнос, % гранта дивизиона"],
  ["insurance_medical_cut_pct", "Страховка: −% взноса за уровень «Медцентра» (до −50%)"],
  ["insurance_cover_pct", "Страховка: оплачивает, % лечения"],
  ["rating_size", "«Лучший президент»: клубов в рейтинге"],
  ["onboarding_bonus_eur", "«Первый сезон»: бонус за чек-лист, €"],
  ["cup_min_clubs", "Кубок менеджеров: минимум клубов для розыгрыша"],
  ["friendly_per_day", "Товарищеские матчи: в день на клуб"],
  ["remind_hours", "«Аналитика Pro»: напомнить за N ч до закрытия окна"],
  ["analytics_stars", "«Аналитика Pro»: цена, ⭐ (0 — не продаётся)"],
  ["analytics_days", "«Аналитика Pro»: дней"],
  ["price_alert_pct", "«Аналитика Pro»: алерт при изменении курса акций на %"],
];

const JSON_KEYS: [string, string][] = [
  ["sponsors", "Спонсоры (суммы — % гранта): upfront_pct сразу, win_pct за победу, place_pct по местам (0 = чемпион), rest_pct другие места, relegated_pct при вылете"],
  ["tours", "Турне: revenue_pct / cost_pct (% гранта), fans, fatigue_pct (−% ко всем линиям) в первых fatigue_rounds турах"],
  ["kit_brands", "Спонсор на форме: бренды на выбор"],
  ["match_plans", "Установки на матч: mods (% к линиям GK/DEF/MID/FWD на один матч), injury_x (× шанс травмы; 0 = без травм)"],
  ["event_rounds", "События клуба: после каких туров сезона приходит событие"],
  ["cup_round_hours", "Кубок менеджеров: часы кругов от старта сезона"],
  ["cup_prizes_pct", "Кубок менеджеров: призы, % гранта — победитель, финалист, полуфинал, …"],
  ["events", "События клуба: options — money_pct (% гранта, + доход / − расход), fans, form_pct на form_rounds следующих туров"],
];

export default function ManagerFinanceFields({ value, onChange }: {
  value: Record<string, unknown> | undefined; onChange: (next: Record<string, unknown>) => void;
}) {
  const data = value ?? {};
  return (
    <div className="col-span-2 grid grid-cols-2 gap-3 rounded-xl border border-amber-300/20 p-3">
      <p className="col-span-2 font-display text-sm font-bold">💼 Кабинет президента</p>
      <label className="col-span-2 flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={data.enabled !== false} onChange={(e) => onChange({ ...data, enabled: e.target.checked })} />
        Кабинет открыт (сделки, кредиты, спонсоры)
      </label>
      <label className="col-span-2 flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={data.exchange_enabled !== false} onChange={(e) => onChange({ ...data, exchange_enabled: e.target.checked })} />
        Биржа открыта (акции, IPO, облигации)
      </label>
      <label className="col-span-2 flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={data.cup_enabled !== false} onChange={(e) => onChange({ ...data, cup_enabled: e.target.checked })} />
        Кубок менеджеров разыгрывается
      </label>
      {LABELS.map(([key, label]) => (
        <label key={key} className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">{label}</span>
          <input
            type="number" step="any" value={Number(data[key] ?? 0)}
            onChange={(e) => onChange({ ...data, [key]: Number(e.target.value) })}
            className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
          />
        </label>
      ))}
      {JSON_KEYS.map(([key, label]) => (
        <label key={key} className="col-span-2 flex flex-col gap-1">
          <span className="text-xs text-slate-400">{label}</span>
          <textarea
            rows={key === "kit_brands" ? 2 : 6}
            defaultValue={JSON.stringify(data[key] ?? [], null, key === "kit_brands" ? 0 : 1)}
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
