# Clubs Phase 3a: Tournament Backend Pipeline — Design Spec

## Goal

Build the complete backend pipeline for the Clubs tournament system described in `docs/superpowers/specs/2026-08-26-clubs-design.md`'s Tournament sections: a club applies, a queue of 8 forms a `Tournament`, 14 rounds of round-robin matches get simulated (server-authoritative, deterministic replay log), standings update incrementally, and round 14 distributes cups/stars/budget rewards — all exercisable end-to-end via API calls alone. This is the first of three Phase 3 sub-phases:

- **3a (this spec):** the tournament pipeline itself — data model, queue/formation, fixtures, the two-sided match simulation engine, standings, rewards. No scheduling, no frontend.
- **3b (later):** the two bot-side time-of-day loops (lineup reminder, round-firing) wired to 3a's internal endpoint, plus the new notification types and their bot-side deep links.
- **3c (later):** frontend (bracket/standings, replay viewer, results screen, leaderboard) and admin (`AdminClubsPage`, the new `GameConfig` fields' admin UI, `club_ranking_service`).

Phases 1 (club core) and 2 (economy & squad) are already shipped on `main`.

## Corrections to the original spec (found via direct code survey before this design)

- `GameConfig` is never row-locked anywhere in the codebase today — the original spec's "locked exactly like the existing `GameConfig` singleton-row pattern" describes a pattern that doesn't exist. The `TournamentQueueState` singleton lock is built from the `club_service._lock_club` idiom instead (`with_for_update().execution_options(populate_existing=True)` — the `populate_existing` is required, see that function's docstring for why).
- `ClubBenchCard` (a dedicated bench table) is dropped. Phase 2 already established "bench = any `ClubCard` not currently in the `ClubLineup`" (see `club_squad_service.py`'s explicit comment to that effect) — the tournament substitution logic uses the same definition, filtering candidates by the vacated slot's category.
- Card Arena's match engine (`match_service.py`) is fundamentally one-sided: a real named "user" lineup vs. an abstracted, actor-less "opponent." A tournament match needs two real named lineups (injuries/red cards land on specific `ClubCard`s on either side; the replay must show real actor names for both clubs). The reusable part is the probability math (`_lerp_chance`, `_resolve_shot_continuation`, `_apply_card`, `_resolve_breakaway` — all parametrized by ratings, no side-specific assumptions); the moment-building/resolution layer (`_build_shot_moment`, `_resolve_attack`, `_resolve_defense`, `_generate_moment_queue`) gets rewritten as a new, symmetric module rather than reused directly.
- The original spec described `TournamentMatch.event_log` as "same shape as `MatchEvent`" — `MatchEvent` is actually a relational table (append-as-you-go, for personal matches' live interactivity). Since tournament matches are simulated once, in full, non-interactively, `event_log` is a single JSON column (an ordered list of event dicts, same per-event shape the engine already produces) — simpler, and there's nothing to append incrementally.
- `Club.cups_count`/`Club.stars_count` don't exist yet (sketched in the original spec but never added in Phase 1/2, since nothing needed them until now) — added here.

## Data model

New files, following this codebase's existing one-file-per-concept convention (see `club_pack.py`, `club_lineup.py`, etc.):

- `backend/app/models/club.py` — add `cups_count: Mapped[int]` (default 0), `stars_count: Mapped[int]` (default 0, no CHECK — explicitly allowed negative), `last_tournament_applied_at: Mapped[Optional[datetime]]` (nullable).
- `backend/app/models/tournament_queue.py` — `TournamentQueueState` (id=1 singleton, `current_queue_id` FK), `TournamentQueue` (`status`: `open`/`formed`), `TournamentQueueEntry` (`queue_id`, `club_id`, `joined_at`).
- `backend/app/models/tournament.py` — `Tournament` (`status`: `active`/`completed`, `rounds_simulated` int 0–14, `created_at`), `TournamentClub` (`tournament_id`, `club_id`, `is_withdrawn` bool default False).
- `backend/app/models/tournament_match.py` — `TournamentMatch` (`tournament_id`, `round_number` 1–14, `club_a_id`, `club_b_id`, `score_a`, `score_b`, `event_log` JSON, `simulated_at`).
- `backend/app/models/tournament_standing.py` — `TournamentClubStanding` (`tournament_id`, `club_id`, `points`, `goals_for`, `goals_against` — unique on `(tournament_id, club_id)`).
- `backend/app/models/tournament_result.py` — `TournamentClubResult` (`tournament_id`, `club_id`, `final_rank`, `budget_awarded`, `stars_delta`, `cup_awarded` bool — unique on `(tournament_id, club_id)`, written once at round 14).
- `backend/app/models/club_card_availability.py` — `ClubCardAvailability` (`club_card_id` unique FK, `rounds_remaining` int) — a row only exists while a card is actually suspended; absence = available. Ticks down by 1 only when the owning club's tournament match is simulated (not on a fixed clock), so it correctly carries across a tournament boundary and doesn't decay while a club is idle between tournaments.
- `GameConfig` gains: `club_tournament_cooldown_hours` (default ~2), `club_form_window_matches` (default 3), `club_form_bonus_per_result` (the ± strength adjustment per W/D/L in the form window), `club_tournament_budget_place_1` through `_place_8` (8 separate int columns, decreasing by rank, admin-tunable — matches this codebase's existing pattern of one column per discrete tier rather than a JSON/array column).

One Alembic migration per model file, sequential from the current head, following this plan's established convention.

## Queue → formation → fixtures

`backend/app/services/tournament_queue_service.py`:

1. `_lock_queue_state(db)` — row-locks `TournamentQueueState` (id=1, get-or-create if absent), same lock idiom as `club_service._lock_club`.
2. `apply_to_tournament(db, user)`: resolve the caller's club + require manager (captain/assistant, same `_require_manager` used everywhere else in Clubs). Validate: full starting XI (11/11 `ClubLineupCard`s filled), ≥2 members, club not already queued or in an active tournament, `now - club.last_tournament_applied_at >= config.club_tournament_cooldown_hours` (or null — first-ever application always allowed). Lock the queue state, get-or-create the open `TournamentQueue`, insert a `TournamentQueueEntry`. If this is the 8th entry: create the `Tournament`, generate all 14 rounds via `tournament_fixture_service.generate_fixtures` (below), insert 8 `TournamentClub` rows, mark the queue `formed`, create a fresh empty `TournamentQueue` and point the (still-locked) `TournamentQueueState` at it, set `last_tournament_applied_at = now()` for all 8 clubs. Commit once.

`backend/app/services/tournament_fixture_service.py`:

- `generate_fixtures(club_ids: list[int]) -> list[tuple[int, int, int]]` (round_number, club_a_id, club_b_id) — pure function, no DB access, easily unit-testable. Standard circle-method round-robin for 8 clubs: fix club 0, rotate the other 7 through 7 rounds of 4 matches each (28 matches total for one full round-robin — since 8 clubs → 7 rounds × 4 matches). Leg 2 repeats the identical 7 pairings as rounds 8–14, so round *n* and round *n+7* always share the same pairings. The only adjacent-round boundary that spans leg 1 into leg 2 is round 7 → round 8: since the circle method gives every club a distinct opponent in each of the 7 rounds within a leg, round 7's opponent and round 1's opponent (= round 8's opponent) are never the same club — so no club ever faces the same opponent on two consecutive rounds anywhere in the 14-round schedule.

## Match simulation orchestration

`backend/app/services/tournament_simulation_service.py` — the entry point both the internal endpoint and (later) 3b's scheduler call:

```
async def simulate_next_round(db: AsyncSession) -> list[TournamentMatch]:
    # For every Tournament with rounds_simulated < 14 (locked individually,
    # each tournament's own row, so a slow one doesn't block others):
    #   round_number = tournament.rounds_simulated + 1
    #   for each of that round's 4 fixtures (club_a, club_b):
    #     lineup_a, lineup_b = resolved active lineups with substitutions applied
    #     match = tournament_match_engine.simulate_match(lineup_a, lineup_b, config)
    #     persist TournamentMatch, update both TournamentClubStanding rows,
    #     decrement ClubCardAvailability.rounds_remaining for every card that played
    #   tournament.rounds_simulated += 1
    #   if tournament.rounds_simulated == 14: tournament_reward_service.conclude(db, tournament)
    #   commit
```

Idempotency: locking each `Tournament` row (`with_for_update`) before reading/incrementing `rounds_simulated` means a duplicate call to `simulate_next_round` (e.g. a retried internal request) can't double-simulate the same round — the second caller blocks until the first commits, then sees `rounds_simulated` already advanced and has nothing left to do for that tournament this cycle.

**Lineup resolution + substitution** (per club, per match, before handing lineups to the engine):
1. For each of the 11 `ClubLineupCard`s, check `ClubCardAvailability` — if suspended (`rounds_remaining > 0`), substitute from the bench (any `ClubCard` not currently in the lineup, same category first — GK/DEF/MID/FWD, per `CATEGORY_POSITIONS` — falling back to any category if none available), and flag this club's match strength for a flat 0.5× penalty (`GameConfig`-tunable? — no, the spec fixes this at 0.5×, not admin-configurable, matching the original spec's literal wording; revisit only if asked).
2. `calculate_base_strength` (reused unchanged from `lineup_service.py`, already proven to work with `ClubCard` tuples) computes the resulting team strength; the 0.5× gap penalty applies on top if any substitution happened.
3. Form multiplier: look at each club's last `config.club_form_window_matches` `TournamentMatch` results (across all of that club's tournament history, not just the current tournament, so form persists across tournament boundaries the same way `ClubCardAvailability` does), apply `± config.club_form_bonus_per_result` per win/draw/loss.

## Match engine: `tournament_match_engine.py` (new module)

Generalizes `match_service.py`'s moment-building/resolution layer to two named sides:

- `generate_moment_queue(strength_a, strength_b, config, lineup_a, lineup_b) -> list[dict]`: same minute-sampling and flavor/shot-chance weighting as `_generate_moment_queue`, but the attacking-probability split now comes from `strength_a`/`strength_b` (already form- and penalty-adjusted) instead of `user_attack`/`opponent_attack`, and each shot moment's actors are picked from **whichever club is attacking this moment** (shooter/pass target) and **the other club** (defender/keeper) — both real `ClubCard`-backed actors, not one real + one abstract.
- `resolve_moment(moment, state, config) -> event_dict`: reuses `_lerp_chance`/`_resolve_shot_continuation`/`_apply_card`/the breakaway roll unchanged (they only need rating numbers, already side-agnostic); the attack/defense branching (`_resolve_attack`/`_resolve_defense`-equivalent) is rewritten to read "attacking club" / "defending club" instead of "user" / "opponent," but keeps every existing `config.match_*` probability tunable as-is (same curves, same realism — this is the whole point of reusing rather than rebuilding).
- No live `resolve_action` round-trip: since nobody watches a tournament match live, every interactive moment gets its action decided by a fixed, simple default policy at resolution time (not client input): **attacking side shoots if the situation bias is non-negative (a "clear" chance), passes otherwise; defending side always attempts a tackle** (letting the existing rating-driven foul/card rolls decide the outcome, same as today). This keeps the decision deterministic-from-inputs and easy to reason about/test; revisit only if matches feel too samey once real games are played.
- `simulate_match(lineup_a, lineup_b, config) -> (score_a, score_b, event_log, red_carded_or_injured_card_ids)`: orchestrates the above end to end for one match, producing the full ordered `event_log` list to store on `TournamentMatch.event_log` directly (no incremental persistence needed).
- Injury (1–3 future rounds, random) or red card (next round only) rolls happen during resolution exactly as `_apply_card`/a new injury-roll do today, writing/upserting the affected `ClubCard`'s `ClubCardAvailability.rounds_remaining`.

## Standings & tie-break

`backend/app/services/tournament_standing_service.py`:

- Incremental update after each match: `TournamentClubStanding.points += 3/1/0`, `goals_for`/`goals_against` += score, for both clubs.
- `rank_standings(standings: list[TournamentClubStanding], matches: list[TournamentMatch]) -> list[TournamentClubStanding]`: pure function. Sort key: points ↓, goal difference ↓, goals for ↓, then head-to-head points ↓ (computed on the fly from just that tournament's matches between the tied clubs — no persisted head-to-head table). No existing precedent in the codebase for this sort; built and tested standalone.

## Conclusion & rewards

`backend/app/services/tournament_reward_service.py`, called by `simulate_next_round` the moment `rounds_simulated` hits 14, inside the same locked/committed transaction as the round-14 match simulation:

- Compute final ranking via `rank_standings`.
- For all 8 clubs: `credit_club_budget(db, club, config.club_tournament_budget_place_N, ClubBudgetTransactionType.tournament_reward, ...)` where N is that club's final rank.
- 1st place: `club.cups_count += 1`.
- Stars: 1st +3, 2nd +2, 3rd +1, 6th −1, 7th −2, 8th −3, 4th/5th unchanged (`club.stars_count`, uncapped either direction).
- Write one `TournamentClubResult` row per club (`final_rank`, `budget_awarded`, `stars_delta`, `cup_awarded`).
- `Tournament.status = completed`.

Idempotency is inherited from `simulate_next_round`'s own per-tournament row lock — round 14 only ever gets simulated once per tournament, so conclusion only ever runs once, in the same transaction as that round's simulation (not a separate, later step that could double-fire).

## Withdrawal (captain-less disband mid-tournament)

Per the original spec: if a club disbands while `TournamentClub.is_withdrawn` would need to become true (captain leaves, no assistant to promote), every one of that club's remaining scheduled matches auto-records as a 0–3 loss for the rest of the tournament (opponent gets the win) — implemented as a check inside `simulate_next_round`'s per-fixture loop: if either club in a fixture is withdrawn, skip the engine entirely and directly persist a 0–3 `TournamentMatch` with an empty `event_log` (nothing to replay). This keeps the schedule/standings internally consistent without reflowing the bracket. Wiring the actual disband-time `is_withdrawn` flag set is `club_service.leave_club`'s responsibility (an addition to existing Phase 1 code) — in scope for this phase since it's a small, necessary addition, not deferred to 3b/3c.

## API surface (backend only — no frontend consumes these yet)

- `POST /clubs/tournament/apply` — manager-gated, per above.
- `GET /clubs/tournament/current` — my club's queue position or active-tournament summary (standings + my club's remaining fixtures), null if not applicable.
- `GET /clubs/tournament/{id}` — public tournament detail: standings, fixtures, participant clubs. No auth beyond normal session (public bracket, matching the original spec's "public preview" framing).
- `GET /clubs/tournament/{id}/matches/{match_id}` — match detail including the full `event_log`, for replay (3c wires this to a frontend component; 3a just needs the endpoint to exist and be correct).
- `POST /internal/clubs/simulate-round` — `verify_internal_secret`-guarded (exact existing pattern, see `backend/app/routers/internal.py`'s chat-pack endpoint), calls `tournament_simulation_service.simulate_next_round`. This is what 3b's scheduler will call on a timer; in 3a it's directly callable (tests, manual curl) to exercise the whole pipeline without needing any scheduler yet.

## Testing plan

- Fixture generator: every pair meets exactly twice, never in consecutive rounds, for club counts other than a hardcoded 8 if the function is written generically (still only ever called with 8 in practice).
- Tie-break sort: points/GD/GF/head-to-head, including a full 3-way tie requiring head-to-head.
- Queue formation race safety: concurrent applications, mirroring the locking tests already written for Tactico pairing / `TournamentQueueState`.
- Match engine: deterministic event log shape, injury/red-card availability writes, the 0.5× gap-penalty substitution path (with and without a same-category bench card available).
- `Club.budget >= 0` and the new `TournamentClubResult`/`ClubCardAvailability` constraints — real-Postgres verification per this codebase's now-standard practice (SQLite won't catch a missing/misapplied CHECK or a locking bug).
- Reward distribution correctness and idempotency: round-14 crediting can't double-fire even under a retried/concurrent `simulate_next_round` call.
- Withdrawal: a mid-tournament disband correctly auto-scores remaining fixtures as 0–3 losses without disturbing other clubs' standings.
