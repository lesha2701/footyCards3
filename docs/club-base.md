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

Ten levels each. Build time grows from 12 h to 12 days (HQ 4 h → 10 days,
stadium 1 → 14 days); a Stars speed-up costs 2 ⭐ per started hour
(`club_base_stars_per_hour`). Costs: a regular building 1 500 → 140 000
coins per level, the HQ 1 000 → 105 000, the stadium 3 000 → 220 000.

| Code | Building | Effect per level (defaults, levels 1→10) |
|---|---|---|
| `hq` | Штаб-квартира | every other base building is capped at the HQ level |
| `stadium` | Стадион | +12 … 150 coins per home league match of «Карьера тренера»; capacity 5 000 → 86 000 and the look are cosmetic |
| `hotel` | Клубный отель | +5 … 55 % matchday income |
| `training` | Тренировочный центр | +5 … 55 % familiarity growth (career), +3 … 25 % XP of «Мой игрок» trainings |
| `medical` | Медцентр | −5 … 42 % injury chance, +2 … 14 fatigue recovery (rest and the «Восстановление» training) |
| `analytics` | Аналитический центр | «Разбор соперника» / «Стандарты» trainings +2 … 20 % stronger (the part above ×1.0) |
| `media` | Медиацентр | +3 … 25 % to positive career reputation |
| `marketing` | Отдел маркетинга | sponsors +30 … 300 coins a day; ticket prices +3 … 25 % matchday income |
| `shop` | Клубный магазин | merchandise +20 … 210 coins a day; +1 … 10 % quick-sell price |
| `accounting` | Бухгалтерия | −2 … 15 % to every construction cost (base and «Академия») |

Stadium look unlocks: seats any level, canopies 3, floodlights 5, full
roof 7, video screen 9.

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
Buildings grow with the level (tiers 1–3 / 4–6 / 7–9 / 10 with gold trim);
a crane stands over a construction; the stadium shows seat colour, roof,
floodlights and screen from its look. An admin can upload a background and a picture per building
(`static/club_base/uploads`); levels and the crane are drawn on top.
Player-uploaded photos are deliberately not supported (moderation).

## Leaderboard

`RankingMetric.base_level` = base buildings + «Академия» wings.
