# Clubs (кланы) — Design Spec

## Goal

Add a clan-like "Клубы" feature: up to 11 players group into a club with a captain/2 assistants/members hierarchy, jointly build a club-owned squad funded by a shared budget, and compete in an 8-club round-robin tournament (14 matches over a week, 2 rounds/day) with realistic, fully-server-simulated matches that every viewer sees identically. Tournaments run continuously and in parallel — a queue of applicants forms a new tournament the instant it reaches 8 clubs, and a fresh queue opens immediately after.

## Entry point

The Clubs section is **not** a new bottom-nav tab. It's a banner block on the Home tab (`frontend/src/pages/HomePage.tsx`), placed immediately after the existing League banner block (the one navigating to `/league`, ~line 100). Same visual treatment (icon/progress-style banner, click-through), navigating to `/clubs`.

## Data model

- **`Club`**: `id`, `name`, `description`, `club_type` (`open`/`closed`), `logo_shape` (enum, 6–8 templates), `logo_color`, `budget` (int, `CHECK (budget >= 0)` from day one — unlike the recent coin-clawback lesson, there's no legitimate reason for a club budget to go negative, so the DB invariant should hold from the start), `cups_count` (int, default 0), `stars_count` (int, default 0, **can** go negative — no floor), `captain_id` (FK `User`), `invite_code` (unique, permanent), `founded_at`, `last_tournament_applied_at` (nullable, drives the re-apply cooldown), `is_disbanded` (soft marker, or hard-delete on disband — see Lifecycle).
- **`ClubMember`**: `club_id`, `user_id` (unique — a user is in at most one club at a time), `role` (`captain`/`assistant`/`member`), `joined_at` (needed for "longest-tenured assistant" auto-succession).
- **`ClubJoinRequest`**: `club_id`, `user_id`, `status` (`pending`/`accepted`/`rejected`), `created_at`. Unique on `(club_id, user_id)` while pending.
- **`ClubCard`**: the club's own card pool, structurally independent of `UserCard`. `club_id`, `player_id`, `rarity`, `serial_number` (own sequence — see below), `source` (`starter_seed`/`club_pack`), `acquired_at`. No trade-lock/owner fields — never touches a personal collection.
- **`ClubLineup`/`ClubLineupCard`**: mirrors `Lineup`/`LineupCard` exactly. Fixed `FORMATION_SLOTS` (the same 4-3-3, 11 slots, `ideal_position`/`category`/fit-multiplier logic already used for personal Составы — no formation choice). Editable by captain + assistants only.
- **`ClubBenchCard`**: up to a handful of reserve `ClubCard`s tagged by category (GK/DEF/MID/FWD) for substitution. Seeded with exactly 4 (one per category) at club creation; can grow as more club packs are opened.
- **`ClubCardAvailability`**: tracks a `ClubCard`'s injury/red-card suspension — `rounds_remaining` (int) or null/0 = available. This is a plain decrementing counter, not tied to any one tournament's round numbers: it ticks down by 1 only when the *owning club* has a match simulated (so a suspension carries correctly across a tournament boundary if a new tournament starts right after, and doesn't tick down for free while the club sits idle between tournaments).
- **`ClubDailyClaim`**: `club_id`, `user_id`, `claim_date`, unique on `(club_id, user_id, claim_date)` — same shape as the existing `daily_rewards` table, but credits `Club.budget` instead of a personal balance.
- **`ClubBudgetTransaction`**: `club_id`, `amount`, `balance_before`, `balance_after`, `type` (daily_claim/minigame/pack_purchase/tournament_reward/creation_refund-n/a), `description`, `related_object_type/id`, `created_at` — mirrors `CoinTransaction`'s shape, gives the club page an auditable ledger.
- **`ClubPack`**: a small, separate, admin-managed pack list (own table, not the personal `Pack` table) — same probability-table shape, priced and paid in `Club.budget`, opened by captain/assistants, minting `ClubCard` rows.
- **`TournamentQueueState`** (singleton, id=1): points at the currently-forming `TournamentQueue`.
- **`TournamentQueue`** / **`TournamentQueueEntry`**: `status` (`open`/`formed`), entries = `(queue_id, club_id, joined_at)`.
- **`Tournament`**: `id`, `status` (`active`/`completed`), `rounds_simulated` (int, 0–14), `created_at`.
- **`TournamentClub`**: `(tournament_id, club_id)` — the 8 participants.
- **`TournamentMatch`**: `tournament_id`, `round_number` (1–14), `club_a_id`, `club_b_id`, `score_a`, `score_b`, `event_log` (JSON — ordered goals/cards/injuries, same "replayable log" shape as `MatchEvent`/`Match.server_state`), `simulated_at`.
- **`TournamentClubStanding`**: `(tournament_id, club_id)` — `points`, `goals_for`, `goals_against`, updated incrementally as each round resolves.
- **`TournamentClubResult`**: final per-club outcome — `final_rank`, `budget_awarded`, `stars_delta`, `cup_awarded` (bool) — written once at round 14.

New `TransactionType`-style enum isn't reused for club budget (different currency/entity — `ClubBudgetTransaction` has its own small `type` enum instead of overloading `TransactionType`, since club budget is a distinct ledger from personal coins).

## Roles & permissions

- **Captain**: everything below + transfer captaincy + disband.
- **Assistants** (max 2, appointed/removed by captain): manage lineup/bench, open club packs, approve/reject join requests, edit description — everything except transfer captaincy, disband, or remove the captain.
- **Members**: view everything, claim the daily club reward, play the club-contribution mini-game mode, leave.
- **Captain leaves**: auto-promotes the longest-tenured assistant (by `joined_at` as assistant); if there are no assistants, the club disbands — budget forfeited, `ClubCard`s deleted, all members freed. If the club is mid-tournament, it's marked `withdrawn`: every remaining scheduled match for it auto-records as a 0–3 loss (opponent gets the win) — this keeps the schedule and standings internally consistent without needing to reflow the bracket.

## Club lifecycle

- **Creation**: name, description, `club_type`, logo (shape + single fill color), optional description. Costs `GameConfig.club_creation_cost_coins`, debited from the creator via the existing `wallet_service.debit_coins`. On creation: the 15-card starter squad is auto-seeded (see Economy), the creator becomes captain.
- **Browsing** (`/clubs`, not in a club): list of clubs (open + closed), search by name, "Создать клуб" button. Closed clubs show "Подать заявку" instead of instant-join.
- **Already in a club** (`/clubs`): renders that club's home directly — no list.
- **Joining**: open clubs — instant join if under 11 members. Closed clubs — `ClubJoinRequest`, reviewable by captain+assistants. **Invite links**: `t.me/{bot}?start=club_{invite_code}` → the bot appends `?joinClub={invite_code}` to the WebApp URL → the Mini App reads it and sends it as a header on `POST /auth/session` — the exact same 3-hop mechanism referral links already use in this codebase. An invite link joins directly (bypassing the join-request step) if there's room, respecting the 11-member cap either way.
- **Leaving/kicking**: any member can leave; captain/assistants can kick regular members (not each other, not the captain).

## Economy

- **Club daily reward**: one claim per member per day (`ClubDailyClaim`), amount = `GameConfig.club_daily_reward_coins`, credited to `Club.budget`.
- **Mini-game contribution**: reuse the existing mini-games unchanged (Memory/Saboteur/Free Kick/etc.) — add a "play for your club" mode gated by a small daily counter (`GameConfig.club_minigame_daily_plays`, e.g. 2/day), using the same reward-roll logic as personal play, but the coins route straight into `Club.budget` (`ClubBudgetTransaction`) instead of the player's wallet.
- **Starting squad auto-seed** (15 `ClubCard`s: 11 starters + 4 bench, one per category): for each formation slot's position, and for each of the 4 bench categories, query active `Player`s ordered by `rating ASC`, take the lowest; break ties randomly. Minted directly as `ClubCard`s — no pack roll, no cost, deliberately weak.
- **Club packs**: separate admin-managed `ClubPack` list, priced/opened against `Club.budget` by captain/assistants, results minted as `ClubCard`s.
- **Club card numbering**: `ClubCard.serial_number` draws from its own sequence, entirely separate from `Player.next_serial_number` (which personal packs use) — club packs never affect personal-card scarcity/numbering.

## Tournament: queue → formation

Single-row `TournamentQueueState` (id=1) locked exactly like the existing `GameConfig` singleton-row pattern. On application:

1. Row-lock the singleton; get-or-create the open `TournamentQueue`.
2. Validate: full starting XI (all 11 slots filled), ≥2 members, not already queued/in an active tournament, and `now - last_tournament_applied_at >= GameConfig.club_tournament_cooldown_hours` (default ~2h).
3. Insert a `TournamentQueueEntry`. If this is the 8th: create the `Tournament`, generate all 14 rounds' fixtures, mark the queue `formed`, and — still holding the lock — open a fresh empty queue immediately for the next applicants. Set `last_tournament_applied_at` for all 8.
4. Commit.

One lock is sufficient (there's only ever one queue being filled at a time) and race-free without SKIP LOCKED complexity — simpler than Tactico's pairing lock, which has to search among many simultaneous waiters, because here there's a single well-defined "current" queue.

## Tournament: fixtures

Standard circle-method round-robin for 8 clubs: fix club 0, rotate the other 7 through 7 rounds of 4 matches each (28 matches — every pair exactly once). Leg 2 repeats the identical 7 pairings a second time as rounds 8–14. Since round *n* and round *n+7* share pairings, no club ever faces the same opponent in consecutive rounds.

**Simulation clock is global, not per-tournament.** A fixed twice-daily firing (e.g. 12:00 and 20:00 server-local) drives **every** active tournament at once. Each `Tournament` just tracks `rounds_simulated` (0–14). At every firing, every tournament with `rounds_simulated < 14` gets exactly round `rounds_simulated + 1` simulated, then the counter increments. A tournament formed at any moment waits for the next firing to play round 1, then gets one round at every firing after that — 14 firings (7 days) later it's done. This guarantees, by construction, that no club ever skips a scheduled round.

## Tournament: standings & tie-break

`TournamentClubStanding`: points (win 3/draw 1/loss 0), goals for/against, goal difference (computed). Sort: points ↓, goal difference ↓, goals for ↓, head-to-head points ↓ (computed on the fly from just that tournament's matches between the tied clubs). No existing precedent in the codebase for this sort — built from scratch as a standalone function.

## Tournament: match simulation

For each of a round's 4 matches, for each club:

1. **Lineup gap check**: if any `ClubCard` in an active lineup slot is still `ClubCardAvailability`-suspended at kickoff, auto-substitute from the bench (same-category first, any-category fallback if none), **and** apply a flat 0.5× penalty to that club's effective strength for this match (on top of whatever strength the substitute itself contributes) — a club that proactively fixed its lineup in time pays no penalty.
2. **Strength**: reuse the personal-Lineup fit formula exactly (`FORMATION_SLOTS`/`CATEGORY_POSITIONS`, ideal/category/off-category multipliers) — no new position-fit logic needed.
3. **Form**: multiply by a small factor derived from each club's last `GameConfig.club_form_window_matches` (default 3) tournament results (`GameConfig.club_form_bonus_per_result`, applied ±per W/D/L).
4. **Match engine**: a fully server-auto-resolved adaptation of the Card Arena moment-queue engine (same realism — many small independent rolls decide the score, not one aggregate coin-flip) — but every moment resolves immediately in one pass (no interactive human input, since nobody's watching live), producing one persisted ordered `event_log` per match (goals/cards/injuries), stored on `TournamentMatch`.
5. **Random events**: injury (1–3 future rounds, random) or red card (next round only) roll during resolution, substitute immediately for the rest of *that* match, and set `ClubCardAvailability.rounds_remaining` accordingly.

**Pre-round reminder**: one hour before each firing, for every tournament about to get its next round simulated, check each of that round's 8 clubs' active lineups for a still-suspended card; if found, notify that club's members with a deep link to the squad editor. This is a separate, earlier bot job/check from the simulation itself.

**Result-ready notification**: fires the moment a round's simulation completes, deep-linking straight to the replay (`_MATCH_PATH_PREFIXES` gets a new `"club_match": "/clubs/tournament/.../matches/..."` entry).

## Tournament: replay ("same simulation for everyone")

The Card-Arena `MatchSimulation` reveal-over-a-persisted-log component, reused in a pure-replay mode (no interactive prompts — the outcome is already fixed). Every viewer who opens the match replays the identical stored `event_log` from event 0, with the same skip-to-end control. This is what guarantees identical score progression for every club member of both sides.

## Tournament: conclusion & rewards

After round 14 resolves, the backend immediately (atomically) computes `TournamentClubResult` for all 8 clubs and credits everything — cups, stars, budget — regardless of whether anyone's looking. The **"see the last round before results" requirement is a frontend-only sequencing gate**: each viewer's client shows the round-14 replay first; only after dismissing it does the results screen unlock (tracked with a simple per-user "seen" flag). The economy doesn't wait on this.

**Reward table:**
- Cups: 1st place +1 `cups_count`.
- Stars: 1st +3, 2nd +2, 3rd +1, 6th −1, 7th −2, 8th −3 (mirrored), 4th/5th unchanged.
- Budget: 8 admin-configurable amounts (`GameConfig.club_tournament_budget_place_1..8`), decreasing by rank, credited to **every** club.

## Leaderboards & bracket info

Two separate club leaderboards (by `cups_count`, by `stars_count`) — a small parallel `club_ranking_service` mirroring the existing player-ranking service's shape (top N + "my club's position"), since the ranked entity is now `Club` not `User`. Clicking any club in a bracket/standings table opens a shared brief-info popup (founded date, cups, stars) — the same component used for the browse-list preview.

## Frontend routes

- `/clubs` — browse list (not in a club) or auto-render of your club's home (in a club).
- `/clubs/create` — creation form.
- `/clubs/:id` — public preview (join/request, brief info) — also the content of the bracket-click popup.
- `/clubs/mine/squad` — lineup + bench editor (captain/assistant only), reusing the personal-Lineup editor's UI.
- `/clubs/mine/packs` — club pack list + open flow.
- `/clubs/tournament/:id` — bracket/standings.
- `/clubs/tournament/:id/matches/:matchId` — replay (pure-replay Card-Arena component).
- `/clubs/leaderboard` — cups tab / stars tab.

New notification types: match result ready, lineup reminder, tournament results ready, join-request received/accepted/rejected, role changed, kicked, captain transferred to you.

## Admin additions

- `AdminClubsPage.tsx` — view/moderate/disband any club, view tournaments.
- `AdminClubPacksPage.tsx` — manage the club-only pack list (separate from `AdminPacksPage.tsx` since pricing is in club budget, not personal coins).
- `AdminGamesPage.tsx` — new `GameConfig` fields: `club_creation_cost_coins`, `club_daily_reward_coins`, `club_minigame_daily_plays`, `club_tournament_cooldown_hours`, `club_form_window_matches`, `club_form_bonus_per_result`, `club_tournament_budget_place_1..8`.

## Backend↔bot wiring

Two new bot-side time-of-day loops (same shape as the existing-but-disabled `daily_reminder.py`, extended to fire-once-per-`(date, slot)`):
- Lineup-reminder loop, firing 1h before each simulation slot, calling a new internal endpoint that returns which clubs need a reminder (bot sends the notifications — or, more consistent with the existing `notify()`+dispatcher pattern, the internal endpoint itself just enqueues `Notification` rows and the existing dispatcher delivers them, same as everything else).
- Simulation loop, firing at the two daily slots, calling `POST /internal/clubs/simulate-round` (privileged via `verify_internal_secret`, same pattern as the existing chat-pack internal call) — all simulation logic lives in the backend service layer, not the bot.

## Testing plan (summary — full list belongs in the implementation plan)

- Club CRUD/roles/permissions, budget atomicity + row-locking.
- Queue-formation race safety under concurrent applications (mirrors the locking tests already written for Tactico/Leagues backfill).
- Fixture generator: every pair meets exactly twice, never in consecutive rounds.
- Tie-break sort function (points/GD/GF/head-to-head).
- Match simulation: deterministic stored event log, injury/red-card substitution + the 0.5× unaddressed-gap penalty.
- Reward distribution correctness and idempotency (round-14 crediting can't double-fire).
- Manual real-Postgres verification for the queue singleton lock and the new `Club.budget >= 0` constraint (per the lesson from the premium-task clawback feature — SQLite tests won't catch a missing/misapplied CHECK constraint).
- Frontend: creation, join/request flow, squad editor, bracket view, and replay-consistency verified by comparing two different logged-in sessions viewing the same match.
