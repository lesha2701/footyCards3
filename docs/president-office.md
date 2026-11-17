# «Менеджер» → «💼 Кабинет президента»

Financial levers of a «Менеджер» club for players who like money games.
Every amount is club euros (`ManagerClub.budget`) and never becomes coins.

Code: `backend/app/services/manager_finance.py`, models `ManagerLedger`,
`ManagerDeal`, `ManagerLoan` (`models/manager_club.py`), migration
`0230_manager_finance`, routes `/manager/office*` (`routers/manager.py`);
frontend `components/manager/PresidentTab.tsx`, admin
`admin/components/ManagerFinanceFields.tsx` (Админка → Игры → «Менеджер»).

## Numbers

`GameConfig.manager_finance` stores only overrides; `manager_finance.DEFAULTS`
fills the rest (`cfg(config)`), the admin page shows the effective values.
Most sums are a % of the club's division grant (`G`), so they grow with the
division.

## Ledger and report

Every budget change in `manager_service` / `manager_shop` goes through
`manager_finance.book(db, club, kind, amount, season_key, ref=None)` under
the club row lock: it changes the budget and writes a `manager_ledger` row.
`ref` (unique per club) makes a payout happen once (grants, sponsor results,
deposits, shirt sponsor seasons). Money of the transfer window belongs to the coming
season (`upcoming_key`), money of a running league to its season. The report
groups the last 6 seasons into income, expenses and financing (loans,
deposits, the venture fund). The ledger starts empty at 0230.

The office keeps the common transfer window (`manager_finance.window_open` =
the club doesn't play and `manager_service.window_open`): deals, the loan,
the ticket price, IPO, buyback and bonds are shut for every club — one
founded too late included — from this week's season start until it is
settled. Buying and reselling shares stays open all season.

## Club value

Squad value + budget + money in deposits / the venture fund + «Клубная база»
levels × `value_per_base_level` + fans × `value_per_fan` + titles ×
`value_per_title` − the debt. Fans = merchandise buyers + `fans_bonus`
(supporters from tours; they also buy tickets at home matches).

## Deals (one of each kind per club and season — unique row)

Not stadium naming rights: the stadium name is a Stars cosmetic of the style
shop (`manager_shop`, `stadium_name`), so the club sells its shirt instead.

Signed only while the club does not play, for the coming season.

| Kind | Now | During the season | At its end | Campus multiplier |
|---|---|---|---|---|
| sponsor | upfront | bonus per win | by place / title / relegation | «Отдел маркетинга» +% to all sums |
| kit — shirt sponsor (1–3 seasons) | the first season's price | next seasons at their start | — | price = base + «Клубный магазин» level |
| tour | revenue − costs, fans | −fatigue_pct to every line in the first rounds | — | «Клубный отель» cuts costs, «Медиацентр» adds fans |
| tv | expected match income − discount | the club gets no match income | — | «Медиацентр» cuts the discount |
| deposit | stake leaves the budget | — | stake + rate | «Бухгалтерия» raises the rate |
| venture | stake (≤ % of budget) | — | ×multiplier with a chance, else 0 (seeded by deal) | — |
| farm | fee | cheaper loans of footballers, stronger academy kids | — | «Тренировочный центр» makes kids stronger |

Effects are frozen into the league team (`team["finance"]`) in
`manager_service._prepare_club`; results are paid in `_settle` once the
pyramid moves are known (relegation = really moved down).

## Bank loan

Limit = min(G × `loan_grant_pct`, club value × `loan_value_pct`), 1–3
seasons, one open loan per club (partial unique index). At every season start
while it runs the debt grows by the rate («Бухгалтерия» cuts it); the first
season start after the term collects it. Not enough budget → `overdue`: a
penalty on the debt, `ensure_can_transfer` refuses buying / loaning /
signing until it is repaid. Repay any part any time. No deposit while a loan
is open and no loan while money is on deposit (no rate arbitrage).

## Exchange (phase 2, `manager_exchange.py`, migration `0231_manager_exchange`)

Tables `manager_stocks` (one per listed club), `manager_shares` (holder
rows, unique club + holder), `manager_trades` (the tape), `manager_bonds`,
`manager_bond_holdings`. Routes `/manager/exchange*` and `/manager/bonds*`,
frontend `components/manager/ExchangePanel.tsx` («📈 Биржа» section).

- **Shares.** `shares_total` per club; the owner floats up to `ipo_max_pct`
  (always keeps control). Two markets, like a real exchange:
  - *primary* — unsold IPO shares (`unsold`): the buyer pays the issuing
    club, at most `ipo_season_cap_pct` of G per season;
  - *secondary* — a holder lists shares at an ask within ±`ask_band_pct` of
    the price (`manager_shares.listed/ask`, `POST /exchange/{id}/list`): the
    buyer pays the seller, the issuer gets nothing; or sells at once to the
    exchange at the price − `exchange_spread_pct` (`pool`; reselling pool
    shares pays nobody).
  A buy walks the offers cheapest first (at one price: holders' asks, the
  IPO, the pool). A burnt `exchange_fee_pct` on each side; one holder owns
  at most `holder_max_pct`; buyers pass `trade_guard_service.ensure_can_give`
  (no fresh multi-accounts pumping a club). What the owner gets from a high
  price: the next IPO raises more and the capitalization shows the club's
  worth; the secondary market is between investors.
- **Price.** base = club value without budget/invested money ÷ shares, ×
  form % = 100 + (ppg − 1.4)·`price_ppg_pct` + (last-5 ppg − 1.4)·
  `price_form_pct`, clamped to `price_min_pct..price_max_pct`. Set at
  listing and at every season start (`season_open`), recomputed after each
  round (`after_round`); trading never moves it, so there is nothing to
  pump. A trade first resolves the issuer's due round (`_fresh`).
- **Dividends.** At `season_end`: `dividend_pct` of the season profit
  (ledger income + expenses, excluding `dividend_out`) split per share;
  ledger refs make it pay once.
- **Buyback** (window only): unsold shares free, then pool shares at the
  price, then holders pro rata at price + `buyback_premium_pct`.
- **Bonds.** Units of `bond_unit_eur`, coupon chosen in
  `bond_rate_min_pct..bond_rate_max_pct`, 1..`bond_seasons_max` seasons,
  limit min(G × `bond_grant_pct`, value × `bond_value_pct`), one holder ≤
  `bond_holder_max_pct`. `selling` → `active` at the issuer's season start
  (unsold units dropped); coupon at every season end, principal with the
  last; can't pay → `default`, transfers blocked (`default_block`) until
  `repay_bond`.
- `exchange_enabled` switches the whole thing off.

## Phase 3: matchday, injuries, «Лучший президент» (migration `0232_manager_tickets`)

- **Ticket price** (`manager_clubs.ticket_pct`, `POST /manager/office/tickets`,
  window only, frozen into the league team's `finance.ticket_pct` at the
  season start). Attendance = 100 − (price − 100) × `ticket_elasticity`
  within `ticket_attendance_min_pct..max_pct`; a home match's tickets (the
  stadium and tour fans) × price × attendance; the home side gets
  (attendance − 100) × `ticket_support_pct` % on every line
  (`finance.support_mods`); at the season end fans change by
  (attendance − 100) × `ticket_fans_per_pct`. The money peaks around +30 %.
- **Injuries** (`manager_service._injury`, after every league match): with
  `injury_chance_pct` (cut by «Медцентр», `snap.injury_pct`) one of the
  club's live / catalog / academy players (never «Мой игрок») misses
  `injury_rounds_min..max` rounds — `league.state["injuries"][club_id][key]
  = {back, rounds, cost, name}`, the roster skips him until `back`; the
  treatment (`injury`) is `injury_treatment_pct` of his value. Seeded per
  league/round/club, so a replay is the same.
- **Insurance** — a season deal (`insurance`): the premium
  `insurance_premium_pct` of G (−`insurance_medical_cut_pct` per «Медцентр»
  level, at most −50 %); the season's treatments are paid back by
  `insurance_cover_pct` (`insurance_in`).
- **«Лучший президент»** (`GET /manager/office/rating`, `finance.rating`):
  the season's profit (income + expense groups of the report for the
  running or last season) and the capital (budget + deposits and venture +
  shares at the price + bonds held − the loan debt − own bonds sold), top
  `rating_size` and my place.

## Decisions of the president (no migration: `manager_clubs.office` JSON + ledger refs)

- **Season budget** (`manager_budget.py`, `PUT /manager/budget`, `GET /manager/decisions`):
  in the window the president splits the pot (budget + the coming grant) into
  articles `budget_articles` (wages / transfers / the club — ledger kinds per
  article), the rest is the reserve. At season end (`season_end`, after
  `finance.season_end` in `_settle`) an article overspent by more than
  `budget_tolerance_pct` costs `budget_fans_penalty` fans each; all within plan
  → `budget_bonus` of `budget_bonus_pct` of the unspent (cap
  `budget_bonus_max_pct` of the grant), ref `budget:<key>`.
- **Hands-on** (`ACTOR` ContextVar, `act()`): each decision is counted as the
  president's or the assistant's (`office["acts"]`). From `hands_on_min`
  decisions the season pays `hands_on_fans` and `hands_on_bonus_pct` of the
  grant × the president's share (ref `hands_on:<key>`).
- **Achievements** `president_achievements` (goal, `reward_pct` of the
  grant): claimed once, ledger kind `achievement`, ref `ach:<code>`.
- **Analyst finance review** (`review`, with «Аналитик» only): income /
  expense / profit, the top costs, deals' net (`DEAL_LINES`), the budget rows
  and advice.
- **Assistant fine rules**: separate `transfer_limit` / `renew_limit` within
  `limit`, `min_sale`, untouchables `keep` (`npc:<id>` / `live:<contract>`),
  `mode` "act" | "advise". In "advise" every would-be action is a log line
  with an `action`; `POST /manager/assistant/advice/{id}` runs it as the
  president's own decision.
- **Sporting director** (staff role `director`, `GET /manager/staff/director`,
  budget `POST /manager/staff/director/budget`): for empty XI places and
  expiring footballers proposes `staff_effects.director` options from the
  catalog within his budget.
- **Staff conflicts** (`manager_conflicts.py`): after `conflict_rounds`, when
  both roles of a `staff_conflicts` template are hired, an event with slot
  CONFLICT_SLOT + round.
- **Tips lead to the action**: every «Сегодня в клубе» item carries a
  `target`; the frontend (`lib/managerFocus.ts`) opens its tab and sub-section
  and lights `[data-focus=<target>]`; the home tile links `?go=<tab>:<target>`.

## «Штат»: the round table (migration `0308_manager_staff_departments`)

Ten departments sit around the table with the president at its head (his
Telegram photo): coach, sporting director, scout, academy director (rating
points to the academy kids — `academy_pts` on the filler), physio, transport
(`away_pct` to every line away), stadium director (`stadium_pct` at home),
press, marketing, finance director (`finance_pts` off the loan rate, half on
deposits). `staff_slots` by division limits the taken seats. The old
`driver` became `transport`, the old `agent` became `academy`.

- **Fleet** (`fleet`, office `fleet`): a bus and a plane bought level by level
  for club euros (`price_pct` of the grant, window only, needs the head of
  transport), `upkeep_pct` booked at the season start (`fleet_upkeep`, can't
  pay → sold), `away_pct` / `injury_pct` folded into the snapshot.
- **Orders** (`staff_orders`, `POST /manager/staff/orders/{role}`): once a
  season per department (ledger ref `order:<role>:<key>`): fans now, form for
  the next rounds of the running league, or an injured footballer back.
- Art drops into `frontend/src/assets/manager/staff/<code>.webp`:
  `council_table`, `seat_empty` and the fleet codes (`minibus`, `coach_bus`,
  `liner`, `charter`, `jet`); without a file the UI draws its own.
