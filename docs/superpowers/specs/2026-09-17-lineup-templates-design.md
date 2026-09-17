# Lineup Templates (5 saved squads per owner) — Design Spec

## Goal

Players currently get exactly one saved squad in each of three independent
features — Card Arena (`Lineup`), Тактико (`TacticoSquad`), and Клубы
(`ClubLineup`) — and switching context (e.g. before a match) means
re-picking all 11 cards from scratch. This feature lets each owner (a user
for Card Arena/Тактико, a club for Клубы) save up to **5 named templates**
and switch which one is active. Tactics/formation (where that concept
exists) are saved per template, not globally.

Confirmed product decisions (from user Q&A):
- **A card can appear in more than one template at once.** No
  cross-template exclusivity to enforce or reconcile.
- **Trade/upgrade locking (`is_in_lineup` / `is_in_tactico_squad`) applies
  only to the currently ACTIVE template.** Cards parked in inactive
  templates stay freely tradeable/upgradeable.
- **Тактико gets no new tactics/formation concept.** It already has none
  today (just an unordered pool of 11 cards) — this feature only adds
  templating (5 saved squads, switchable), not new gameplay settings.
- **Клубы: 5 templates per club**, still manager-gated (same permission
  model as today — only the manager edits/switches).

Rollout is staged and shipped/verified one feature at a time, in this
order: **Card Arena → Тактико → Клубы.**

## Current State (for reference — nothing here changes by itself)

### Card Arena — `Lineup` / `LineupCard`
`backend/app/models/lineup.py:10-56`. One row per user today, enforced by
a partial unique index `uq_lineup_one_active_per_user` on
`(user_id) WHERE is_active`. Fields: `name` (defaults to `"Основной
состав"`, **never exposed in the API today** — `LineupOut` has no `name`
field), `formation` (always `"4-3-3"`, no endpoint changes it),
`tactic` ∈ `{attacking, balanced, defensive}`, `user_coach_card_id`.
`LineupCard` is a join table keyed by `slot_code` (`GK`, `DEF1..4`,
`MID1..3`, `FWD1..3`, from `FORMATION_SLOTS` in
`backend/app/services/lineup_service.py:29-41`).

Service: `backend/app/services/lineup_service.py`. Key functions:
`_get_or_create_lineup` (`:92-113`, lazy singleton-per-user, race-safe via
`db.begin_nested()` + the partial unique index), `get_active_lineup`
(`:178-221`), `set_tactic` (`:168-175`), `set_lineup_coach` (`:236-245`),
`set_lineup` (`:248-330` — full validation: unknown/duplicate slot,
duplicate card instance, ownership, `is_locked_by_admin`/
`is_locked_in_trade`, position-fits-slot-category, no duplicate *player*
across slots even via different card copies, diamond-count cap; then
row-locks the `Lineup` row via `with_for_update(of=Lineup)` before
swapping `LineupCard` rows and flipping `UserCard.is_in_lineup`).

Router: `backend/app/routers/lineups.py` — `GET /lineups/active`,
`GET /lineups/coach-cards`, `PUT /lineups/active`, `POST /lineups/tactic`,
`PUT /lineups/coach`. All implicitly mean "the one active lineup."

Consumer: `backend/app/services/match_service.py:625` calls
`get_active_lineup(db, user)` before a match, requires `is_complete`.
Also borrows the **opponent's** active lineup the same way (`:666`).

Frontend: no separate lineup page — the editor is inline inside
`frontend/src/pages/ArenaPage.tsx` (formation grid, tactic picker, coach
picker). `frontend/src/api/lineups.ts` wraps the four endpoints above.

### Тактико — `TacticoSquad` / `TacticoSquadCard`
`backend/app/models/tactico.py:12-34`. One row per user
(`user_id` `unique=True`). No formation/tactic fields — `cards` is a flat
unordered list of `TacticoSquadCard` (just `user_card_id`, no slot code).

Service: `backend/app/services/tactico_service.py` — `_get_or_create_squad`
(`:59-66`), `get_squad` (`:69-91`), `set_squad` (`:94-142`, validates
exactly `SQUAD_SIZE` (11) distinct owned cards + rarity caps
`tactico_max_legendary_cards`/`tactico_max_epic_cards`/
`tactico_max_diamond_cards`; flips `UserCard.is_in_tactico_squad`).

Router: `backend/app/routers/tactico.py` — `GET /tactico/squad`,
`PUT /tactico/squad` (body: `list[int]` of `user_card_id`s).

Consumers: every match/challenge start path in `tactico_service.py`
(`:350-357, 391-393, 453-455, 525-527, 591-592`) calls
`get_squad(db, user)` and requires `squad.is_complete`, then uses
`squad.cards` as a flat pool (no per-slot logic — Тактико has never had
formation math).

Frontend: `frontend/src/pages/TacticoSquadPage.tsx` — flat card-grid
selector, no formation UI. `frontend/src/api/tactico.ts` wraps the two
endpoints.

### Клубы — `ClubLineup` / `ClubLineupCard`
`backend/app/models/club_lineup.py:10-39`. One row **per club**
(`club_id` `unique=True` — this is club-owned, not user-owned). Fields:
`formation` (real choice among 4 formations — `CLUB_FORMATIONS` in
`backend/app/services/club_formation_service.py:12-48`: `4-3-3`, `4-4-2`,
`3-5-2`, `5-3-2`, each its own slot layout), `mentality` (default
`BALANCED`), `playstyle` (default `CENTRAL_PLAY`), `club_coach_card_id`.
`ClubLineupCard` references `ClubCard` (a separate club-owned card pool,
not `UserCard` — **`ClubCard` has no lock/trade-flag concept at all**,
confirmed via `backend/app/models/club_card.py`, so Клубы templating needs
no card-locking logic).

Service: `backend/app/services/club_squad_service.py` (568 lines),
manager-gated via `_require_manager(membership)` before any mutation.
`_get_or_none_lineup(db, club_id)` (`:150-...`), `set_lineup`,
`set_tactics`, `set_coach`.

Router: `backend/app/routers/clubs.py` — `GET/PUT /clubs/me/lineup`,
`PUT /clubs/me/tactics`, `PUT /clubs/me/coach`, `POST /clubs/me/training`.

Consumers: `club_squad_service.py:557` (`opponent_lineup =
await _get_or_none_lineup(db, opponent_club_id)` — tournament fixture
simulation reads the *opposing* club's lineup the same way).

Frontend: `frontend/src/pages/ClubSquadPage.tsx` — its own formation-grid
UI against `/clubs/me/lineup`.

### Shared pattern already half-built
`Lineup.name` + `Lineup.is_active` + the partial unique index already
anticipate "multiple rows, one active" — just never wired to a real API.
This is the natural precedent to generalize rather than invent something
new.

## Shared Design: fixed 5 template slots per owner

Rather than a dynamic create/delete CRUD (arbitrary count, need
add/remove endpoints, more edge cases — e.g. deleting the active
template), **every owner always has exactly 5 template rows**, addressed
by a 1-based `template_index` (1..5). Rows are lazily created on first
read if missing — the same pattern already used for `GameConfig`
(`game_config_service.get_config`) and `DailyRewardOption`
(`daily_reward_service.get_day_options`): check-then-insert-defaults,
guarded by a unique constraint + `IntegrityError` retry for the race case.

This matches "5 templates" (not "up to 5") literally, and sidesteps an
entire class of edge cases (what does deleting the active template mean?
what's the minimum count?) that a dynamic scheme would need to answer.

For all three tables:
- Replace the single-row unique constraint (`user_id` alone / `club_id`
  alone) with `(owner_id, template_index)` unique, plus a **new** partial
  unique index `(owner_id) WHERE is_active` (already exists for `Lineup`,
  needs adding for `TacticoSquad` and `ClubLineup`) so exactly one
  template is active at a time.
- `name` becomes real and editable everywhere (`Lineup.name` already
  exists; add it to `TacticoSquad` and `ClubLineup`). Default names:
  `"Шаблон 1"` .. `"Шаблон 5"`.
- Lazy-seed helper: on first read for an owner, if fewer than 5 rows exist,
  insert the missing ones (`template_index` 1..5, `is_active=True` only
  for index 1, defaults otherwise) — same commit-then-retry-on-conflict
  shape as `_get_or_create_lineup` today, just seeding up to 5 rows
  instead of 1.

### API shape (per feature, mirrored)

- `GET .../templates` → list of all 5 (each: `template_index`, `name`,
  `is_active`, plus the feature's existing per-lineup fields: slots/cards,
  formation/tactic/coach where applicable).
- `PUT .../templates/{template_index}` → edit that template's cards
  (slots) — works on ANY template, not just the active one, so a player
  can build out template 2 while template 1 stays active and in use.
- `PUT .../templates/{template_index}/tactic` (Card Arena) /
  `/tactics` (Клубы) → per-template tactic/formation/mentality/playstyle.
  No equivalent needed for Тактико (no tactics concept).
- `PUT .../templates/{template_index}/coach` → per-template coach, where
  coaches already exist (Card Arena, Клубы).
- `PUT .../templates/{template_index}/name` → rename.
- `POST .../templates/{template_index}/activate` → switches the active
  template. This is the one operation with real side effects beyond a
  plain field update — see locking below.
- Existing single-lineup endpoints (`GET/PUT /lineups/active`,
  `POST /lineups/tactic`, `PUT /lineups/coach`, `GET/PUT /tactico/squad`,
  `GET/PUT /clubs/me/lineup`, `PUT /clubs/me/tactics`,
  `PUT /clubs/me/coach`) **keep working**, redefined as "whichever
  template is active" — so `match_service.py`, `tactico_service.py`'s
  match-start paths, and `club_squad_service.py`'s opponent-lineup reads
  need **no changes at all**, they keep reading "the active one."

### Card locking on activate (Card Arena + Тактико only — Клубы has no lock concept)

`POST .../templates/{template_index}/activate`:
1. Row-lock both the old-active and new-active template rows (same
   `with_for_update(of=Lineup)` pattern already used in `set_lineup`, to
   serialize against a concurrent edit/activate).
2. For every card in the **old** active template not also present in the
   **new** one: clear `is_in_lineup` / `is_in_tactico_squad`.
3. For every card in the **new** active template: set the flag (it may
   already be set if the card was also in the old active template — care
   needed to not accidentally double-toggle or momentarily clear-then-set
   a card that's in both).
4. Flip `is_active` on both rows, commit.

This must also run whenever `PUT .../templates/{template_index}` edits
the *currently active* template's cards (the existing `set_lineup`/
`set_squad` per-card locking logic already does this correctly today —
it only needs to become "only touch locks if `template_index` refers to
the active row," a guard, not a rewrite).

Editing a **non-active** template's cards never touches
`is_in_lineup`/`is_in_tactico_squad` — those cards stay unlocked/tradeable
exactly as the Q&A decided.

## Card Arena specifics

- `Lineup`: add `template_index: int` (1..5), keep `is_active`. Drop the
  old `Index("uq_lineup_one_active_per_user", "user_id", unique=True,
  postgresql_where=text("is_active"))`'s implicit "only one row" framing
  in favor of two constraints: `UniqueConstraint("user_id",
  "template_index")` (new) and keep the existing partial-active index
  as-is (still valid: "one active row per user" is still true, just now
  among 5 rather than among 1).
- `FORMATION_SLOTS` stays a single hardcoded formation (`formation` field
  on `Lineup` still exists but the app still never lets it be anything but
  `"4-3-3"` — unchanged, out of scope for this feature).
- Frontend (`ArenaPage.tsx`): add a 5-tab/pill template switcher above the
  existing formation grid; editing acts on whichever template tab is
  open; a distinct visual marker for which one is active (used in
  matches) vs which one is just being viewed/edited.

## Тактико specifics

- `TacticoSquad`: add `template_index`, `is_active`, `name`. No formation/
  tactic fields (per Q&A). `TacticoSquadCard` unchanged (still just
  `user_card_id`, no slot code — Тактико has no positional concept).
- Frontend (`TacticoSquadPage.tsx`): same 5-tab switcher; each tab is the
  existing flat card-grid selector, scoped to that template.

## Клубы specifics

- `ClubLineup`: add `template_index`, `is_active`, `name`. Still
  manager-gated — only the manager edits/renames/activates any template.
  No card-locking changes needed (`ClubCard` has none).
- Frontend (`ClubSquadPage.tsx`): same 5-tab switcher, manager-only
  (mirrors the existing manager gate already in place for editing).

## Migration Plan

One Alembic migration per phase (Card Arena / Тактико / Клубы), each:
1. Add `template_index` (Integer, `nullable=False`, `server_default="1"`)
   and `name` (String, with a sensible default) where missing.
2. Backfill: every existing row becomes `template_index=1` (its
   `server_default` already does this for existing rows).
3. Add `UniqueConstraint(owner_id, template_index)`.
4. For Тактико/Клубы: add `is_active` (`Boolean, nullable=False,
   server_default="true"`) since neither has it today, plus the new
   partial unique index `(owner_id) WHERE is_active` (mirroring
   `uq_lineup_one_active_per_user`).
5. Templates 2-5 are **not** backfilled by the migration — they're
   lazily created on first read (same as the pattern description above),
   keeping the migration itself a pure schema change with no
   heavy/slow data seeding pass over every user.

## Testing Strategy

Per phase: extend that feature's existing test file
(`backend/tests/test_lineups_matches.py` and `test_lineup_coach.py` for
Card Arena; `test_tactico.py` for Тактико; `test_club_squad.py` for
Клубы) rather than a new shared file, since the three systems stay
independently testable. Cover, per phase:
- All 5 templates lazily created on first `GET .../templates` (defaults:
  1 active, 2-5 inactive, `template_index` 1..5, default names).
- Editing a non-active template does not lock/unlock any cards.
- Activating a template: cards exclusive to the old active template get
  unlocked; cards in the new active template get locked; cards present in
  BOTH old and new stay locked throughout (no flicker/race where a
  concurrent trade could slip through mid-switch).
- The same card can be saved into two different templates simultaneously
  (no conflict/error).
- Existing single-lineup endpoints continue to operate on "whichever is
  active" (regression coverage for `match_service.py`'s lineup consumption,
  Тактико match-start paths, Клубы opponent-lineup reads — these must
  keep passing unmodified).
- Клубы: non-manager member cannot edit/activate any template (existing
  `_require_manager` gate still enforced per-template).

## Explicitly Out of Scope

- No new formations/tactics for Тактико.
- No change to Card Arena's fixed `"4-3-3"` formation (still no
  formation-picker endpoint).
- No cross-template card exclusivity/reconciliation logic (per Q&A, a
  card can sit in multiple templates).
- No arbitrary template count / create/delete UI — always exactly 5.
- No changes to `calculate_base_strength`, `FormationSlot`,
  `CLUB_FORMATIONS`, or any match-simulation math — only *which* squad
  feeds into them changes (still "the active one").
