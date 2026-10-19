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

| Code | Building | Effect per level (defaults, levels 1→5) |
|---|---|---|
| `hq` | Штаб-квартира | every other base building is capped at the HQ level |
| `stadium` | Стадион | +20/35/55/80/110 coins per home league match of «Карьера тренера»; capacity and the look are cosmetic |
| `hotel` | Клубный отель | +10…50 % matchday income |
| `training` | Тренировочный центр | +10…50 % familiarity growth (career), +5…25 % XP of «Мой игрок» trainings |
| `medical` | Медцентр | −10/15/20/30/40 % injury chance, +3…12 fatigue recovery (rest and the «Восстановление» training) |
| `analytics` | Аналитический центр | «Разбор соперника» / «Стандарты» trainings +4…20 % stronger (the part above ×1.0) |
| `media` | Медиацентр | +5…25 % to positive career reputation |
| `marketing` | Отдел маркетинга | sponsors +50…260 coins a day; ticket prices +5…25 % matchday income |
| `shop` | Клубный магазин | merchandise +30…170 coins a day; +2…10 % quick-sell price |
| `accounting` | Бухгалтерия | −3…15 % to every construction cost (base and «Академия») |

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

The map is drawn in SVG (contour-line terrain, river, roads, pitches,
buildings with a floor of lit windows per level, crane over a
construction, stadium with seat colour / roof / lights / screen from its
look). An admin can upload a background and a picture per building
(`static/club_base/uploads`); levels and the crane are drawn on top.
Player-uploaded photos are deliberately not supported (moderation).

## Leaderboard

`RankingMetric.base_level` = base buildings + «Академия» wings.
