# «Клубная база»

The player's own training campus, modelled on real top-club training
grounds (Valdebebas, Ciutat Esportiva Joan Gamper, Cobham): a stadium in
the middle, buildings around it, the «Академия» as one district. Players
develop it alone (it is not the shared club of `clubs/*`).

Code: `backend/app/services/club_base_service.py`,
`models/club_base.py` (`user_club_bases`, `club_base_ledger`),
`routers/club_base.py` (`/club-base`), `routers/admin_club_base.py`
(`/admin/club-base/art|ledger`), migration `0179_club_base`, bot loop
`bot/services/club_base_scheduler.py`; frontend `pages/ClubBasePage.tsx`,
`components/base/BaseMap.tsx`, `components/home/BaseHomeCard.tsx`,
`admin/pages/AdminClubBasePage.tsx`.

## Buildings

25 levels each, like the whole «Академия» (5 wings × 5). Defaults come from
formulas in `models/game_config.py` (copied into migration 0179): costs
grow as L^1.9, build hours as L^2, effects go linearly from level 1 to 25.
A regular building costs 800 → 100 000 coins per level (≈ 925 000 in all)
and takes 3 h → 190 h (≈ 72 days in all); the HQ 700 → 75 000 and
2 h → 158 h; the stadium 1 800 → 160 000 and 6 h → 287 h. A Stars
speed-up costs 2 ⭐ per started hour (`club_base_stars_per_hour`).

| Code | Building | Effect, level 1 → 25 |
|---|---|---|
| `hq` | Штаб-квартира | every other base building is capped at the HQ level |
| `stadium` | Стадион | +10 … 150 coins per home league match of «Карьера тренера»; capacity 3 000 → 90 000 and the look are cosmetic |
| `hotel` | Клубный отель | +2 … 55 % matchday income |
| `training` | Тренировочный центр | +2 … 55 % familiarity growth (career), +1 … 25 % XP of «Мой игрок» trainings |
| `medical` | Медцентр | −2 … 42 % injury chance, +1 … 14 fatigue recovery (rest and the «Восстановление» training) |
| `analytics` | Аналитический центр | «Разбор соперника» / «Стандарты» trainings +1 … 20 % stronger (the part above ×1.0) |
| `media` | Медиацентр | +1 … 25 % to positive career reputation |
| `marketing` | Отдел маркетинга | sponsors +20 … 300 coins a day; ticket prices +1 … 25 % matchday income |
| `shop` | Клубный магазин | merchandise +15 … 210 coins a day; +1 … 10 % quick-sell price |
| `accounting` | Бухгалтерия | −1 … 15 % to every construction cost (base and «Академия») |

Stadium look = a shop (`GameConfig.club_base_cosmetics`, Админка → Клубная
база → «Магазин стадиона»): seats colour, roof (canopies / full), floodlights,
video screen, pitch pattern (stripes / checks / diagonal) and facade (concrete
/ brick / glass / gold). The defaults are free; every other option is an item
with a coin price and/or a Stars price (0 = not sold for it, both 0 = free)
and a min stadium level. Bought items are kept forever in
`user_base_cosmetics` (unique per user and item): coins under the user lock
(`buy_cosmetic`, ledger kind `cosmetic`, `TransactionType.club_base_cosmetic`),
Stars through a StarsInvoice with `academy_speedup = "basecos:<code>"`
(`deliver_cosmetic`). `set_look` accepts only defaults, owned or free items at
their level.

Marketing, shop and accounting form the «Финансовый департамент».
Effects are summed by name and clamped by `GameConfig.club_base_caps`
(matchday +100 %, injuries −50 %, coins a day 600, …). Every number —
costs, hours, effects, caps, Stars per hour, days of income — is in
`GameConfig.club_base_*` and editable in Админка → Клубная база.

## Rules

- **One queue** for the whole base, the «Академия» wings included: both
  `club_base_service.start_upgrade` and `academy_service.start_upgrade`
  check the other side under the user row lock.
- **HQ gate**: nothing but the HQ can be built before HQ 1; a building
  can't go above the HQ level.
- **Construction** is completed lazily (GET `/club-base`, any write) and by
  the bot every minute (`POST /internal/club-base/sweep`, `FOR UPDATE SKIP
  LOCKED`, re-checked under the lock, then a `club_base_built`
  notification). Stars finish it now (StarsInvoice `academy_speedup =
  "base:<code>:<level>"`, price = started hours × `club_base_stars_per_hour`).
- **Income** (sponsors + merchandise) accrues continuously, at most
  `club_base_income_max_days` days; a finished level settles the income at
  the old rate first. Claimed with an idempotency key; a user with
  `game_rewards_blocked` gets 0.
- **Career effects are frozen per season**: `CareerParticipant.base_effects`
  is taken from the base at the participant's first round. Seasons running
  when 0179 was applied got `{}` — no base effects until the next season.
- Money: every coin movement is under `wallet_service.lock_user_for_update`
  with its own transaction type (`club_base_upgrade`, `club_base_income`,
  `club_base_matchday`); every operation is journaled in `club_base_ledger`
  with a unique `(user_id, idempotency_key)`.
- PvP modes (Арена, турниры игроков, Тактико, Стратего, клубные турниры) are
  not touched.

## Map art

The map is drawn in SVG (`components/base/BaseMap.tsx` — meadow with
contour-line hills, pond, forest, river with a bridge, roads, car park,
pitches; `BaseArt.tsx` — an illustration per building: glass HQ tower,
hotel with a neon sign and pool, vaulted training hall, clinic with a
helipad and ambulance, analytics data wall and dome, TV studio with dishes
and a mast, billboard office, club shop with an awning, a classical bank).
Buildings grow with the share of their max level (10 visual steps,
`artMetrics.visualLevel`; only the top level gets the gold trim);
a crane stands over a construction; the stadium shows seat colour, roof,
floodlights and screen from its look. An admin can upload a background and a picture per building
(`static/club_base/uploads`); levels and the crane are drawn on top.
Player-uploaded photos are deliberately not supported (moderation).

## Leaderboard

`RankingMetric.base_level` = base buildings + «Академия» wings.
