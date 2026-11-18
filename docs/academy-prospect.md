# «Воспитанник Академии»

The user's own child footballer, raised from 6 years old to his peak in about
100 real days. One per user, a separate entity (`academy_prospects`), not a
Player/UserCard: never sold, traded, fed or dropped from packs.

Code: `backend/app/services/prospect_service.py`, router `/prospect`,
page `frontend/src/pages/ProspectPage.tsx` (`/academy/prospect`, tile on
`AcademyPage`). Numbers: `GameConfig.prospect` over `prospect_service.DEFAULTS`
(admin «Игры» → «🧒 Воспитанник Академии», validated by `prospect_service.validate`).

## Progression

- **Age** follows the calendar: `days_per_year` real days = one year
  (default 8, so 6 → 18 years in 96 days).
- **Stages** by age (`stage_ages`): Двор 6, Детская школа 9, Юноши 12,
  U-19 15, Дебют 18. Each stage caps the rating (`stage_caps`); XP over the
  cap is banked and counts once the age opens the next stage.
- **Rating** = `start_rating` + XP / `xp_per_point`, capped by the stage and
  by the peak. **Peak** = `peak_base + peak_per_star × potential` + peak
  bonuses (≤ 99): «Династия» `dynasty_peak_bonus` per earlier generation (≤
  `dynasty_peak_max`) and +1 per `academy_levels_per_peak` levels of the
  owner's «Академия» (sum of wing levels, stored in `academy_peak`, refreshed
  on reads / creation / graduation, never lowered). The hidden potential
  ★1-5 is rolled at creation (`potential_weights`; the user's first child,
  generation 1, never below `first_min_potential`), revealed by a scout
  (Stars) or by itself at the `reveal_stage`.
- **The ★ grows by effort only**: +1 for every `potential_streak_days`
  training days in a row (at most `potential_streak_max` times,
  `stats.streak_potential`), +1 for a passed stage trial — the first
  `trial_matches` «Ответка» matches on each stage of `trial_stages`,
  `trial_wins` wins pass it, too many losses fail it (`stats.trials`).
  Story forks don't give ★ directly: the win of a gamble option marked
  `trial` (exam, scout, agent, national team) counts as a won match of the
  current stage trial, once a stage (`trials[stage].story`) — luck helps,
  playing still decides.
- **XP sources**: a free daily training (a drill, graded 1-3 ⭐) with a
  streak bonus every `streak_days`; story forks every `story_every_days`
  (some cost coins, some are a gamble);
  matches in «Ответка» and «Менеджер» — these are capped by `daily_xp_cap`.
- **Bonuses** (% to all XP): the «Академия» training wing
  (`academy_service.user_effects`), a mentor (an owned «Академия» path
  card), the «Личный тренер» (Stars, `coach_days`).
- **Position**: a universal player (provisional CM, `position_set` false)
  whose daily drills are one of every line; drills are counted per line
  (`stats.drills`). At `position_stage` («Юноши») the coach offers
  `position_options` positions — two of the line he leans to most (drills +
  talents, `SPEC_LINES`), then the next lines (`POST /prospect/position`).
  A line whose share among prospects with a position (growing + graduates,
  smoothed) is below `deficit_share_pct`% of its formation share (1/4/4/2 of
  11) is in deficit: `deficit_xp_pct` % XP (bonus part "deficit") and
  `deficit_value_pct` % «Менеджер» value, frozen at the choice in
  `stats.deficit`. A later change is a Stars purchase `pos:<POS>`
  (`position_change_stars`), which re-freezes the deficit for the new line.
  The look can change any time.
- Extras: an NPC rival of the same age, the weekly cohort of prospects
  started in the same ISO week, an album of memories.

## Stars and coins

`POST /prospect/stars-invoice` with `purchase` = `training` (extra training,
`extra_trainings_max` a day), `coach`, `scout`, `cos:<code>`, `pos:<POS>`
(position change, only after the coach's choice). The invoice
payload starts with `prospect:` and goes through the academy speed-up
dispatch (`academy_service.deliver_speedup` → `prospect_service.deliver_stars_invoice`);
`prospect_ledger.(user_id, idempotency_key)` makes a redelivery a no-op.
Coin cosmetics debit through `wallet_service` (`TransactionType.prospect_purchase`).
Everything bought is cosmetic or speeds growth; the peak never exceeds the
potential's.

## «Ответка»

`POST /games/otvetka/start` with `{"prospect": true}` fields the prospect.
The engine plays him at `match_rating` — an age-relative rating: 75 when he
is on the curve of an average ★3 boy of his age, ± `match_edge_per_point`
for every rating point ahead or behind (clamped 40-99), so he plays boys of
his age and a 10-year-old isn't hopeless. The claim awards prospect XP for the match,
goals in the first ten episodes and a win (`prospect_xp` in the response),
unless rewards are blocked.

## «Менеджер»

From `manager_min_stage` (default «Детская школа»):

- he plays for the owner's club for free (squad entry kind `prospect`);
  `ManagerClub.prospect_starts` («Всегда в старте», preseason only) puts him
  in the XI like «Мой игрок»;
- with «Ищу клуб» (`POST /manager/market` `subject: "prospect"`) other
  managers see him on the market and offer a contract
  (`POST /manager/offers` `subject: "prospect"`); sign / transfer / loan
  follow the same both-consents rules as «Мои игроки»;
- `ManagerContract.subject` ("player" | "prospect") lets one user have a
  contract for his «Мой игрок» and another for his prospect; while the
  prospect plays elsewhere the owner's club doesn't field him;
- league matches give capped XP (`manager_match_xp`, `manager_goal_xp`)
  and count `club_matches` / `club_goals`. Values follow the usual curve;
  his value history is not recorded.

Not done yet: what happens after the peak (graduation, packs) — to be decided.

## Life around the child (`prospect_life.py`)

Rows of `academy_prospects` carry a `status`: `growing` → `graduate` →
`retired`. Partial unique indexes allow one growing child and one active
graduate per user; older graduates stay as `retired` rows for the hall.

- **Talents** («Кем он станет?»): one pick on each stage of `spec_stages`
  from three seeded options (`SPECS`); `spec_effects` give % XP for goals /
  wins / matches / training / stories and +atk/+def in matches.
- **«Выпускной»** on the last stage (`POST /prospect/graduate`, two taps in
  the UI): the rating freezes (`final_rating`), the owner gets
  `graduation_coins` (ledger `graduation:<id>`), «Менеджер» moves his
  contracts to the subject `graduate` (`manager_service.on_graduation`); the
  previous graduate retires with his contracts closed. Refused while a league
  of the own club or a contract club runs (`graduation_block`).
- **«Династия»**: the next child gets `generation` + 1 and
  `dynasty_peak_bonus` to the peak rating per earlier generation (not ★). The graduate is a showcase
  card in «Зал выпускников» (top by final rating), not a collection card.
- **«Турнир набора»**: weekly XP inside the start-week cohort
  (`week_key`/`week_xp`, rolled in `grant_xp`); the finished week pays
  `week_prizes` to the top 3 once (ledger `week:<week>`), lazily on views and
  from the bot sweep.
- **Friends' duels**: a challenge to a friend's prospect; each side plays its
  own «Ответка» (`?duel=<id>`, `duel_id` on start) within `duel_hours`;
  win, then goal difference decide, the winner gets `duel_win_xp`; an expired
  duel is a walkover for the side that played. `duels_per_day` caps calls.
- **Gifts / birthday**: Stars gifts to a friend's child (`gift:training:<uid>`,
  `gift:coach:<uid>`) and a birthday box once per age (`bday`, ledger
  `bday:<id>:<age>`: XP + a coin cosmetic he lacks).
- **Seasonal cosmetics** (`season` + GameConfig `seasons` windows) are sold
  only in their season; owned ones stay.
- **Other modes**: Пенальти / Штрафной / «1 на 1» take `prospect: true`
  (`prospect_games.py`): `game_match_xp` / `game_goal_xp` / `game_win_xp`
  inside the daily cap.
- **Bot**: `/internal/prospect/sweep` every 10 min (`prospect_scheduler.py`)
  expires duels, settles weeks and writes one evening digest
  (`notify_hour`, ledger `notice:<date>`) as `prospect_event` notifications.
- **Share**: `kind: "prospect"` renders the child or the graduate.
- **Admin**: «🧒 Воспитанник Академии» shows `GET /admin/games/prospect-stats`.
