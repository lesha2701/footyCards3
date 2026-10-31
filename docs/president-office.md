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
