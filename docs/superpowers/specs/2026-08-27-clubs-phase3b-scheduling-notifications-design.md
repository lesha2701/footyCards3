# Clubs Phase 3b: Scheduling & Notifications — Design Spec

## Goal

Give the Phase 3a tournament pipeline (already shipped) a real clock: two bot-side daily loops that fire the round simulation and remind clubs about suspended players before it, plus notification wiring so players actually hear about match results and tournament conclusions instead of having to check the app. This is the second of three Phase 3 sub-phases — Phase 3a (the pipeline itself) is done; Phase 3c (frontend/admin) follows separately.

## Corrections to the original spec / prior survey work

- The original spec's "Backend↔bot wiring" section left the lineup-reminder mechanism as an open choice ("returns which clubs need a reminder... **or**, more consistent with the existing `notify()`+dispatcher pattern, the internal endpoint itself just enqueues `Notification` rows"). This spec resolves it: the internal endpoint enqueues `Notification` rows directly — the bot's only job anywhere in this codebase is deliver-and-mark-sent, never compute-what-to-say.
- `_MATCH_PATH_PREFIXES` (`bot/services/notifier.py`) maps a single `related_object_type` → a single `related_object_id`, matching the shape `Notification.related_object_id` already has (one nullable int column, no schema for a composite id). Deep-linking straight into one specific `TournamentMatch` would need a second id (tournament + match) that doesn't fit this existing mechanism without a schema change. Rather than extend a generic, three-other-feature-shared mechanism for one case, `club_match` notifications deep-link to `/clubs/tournament/{tournament_id}` (the bracket/standings page, which Phase 3c will build) — one tap further than a direct-to-replay link, zero changes to the existing deep-link plumbing.

## Architecture

Two new bot-side `while True: sleep()` loops (`bot/services/tournament_scheduler.py`, same shape as the existing-but-disabled `daily_reminder.py` — this remains genuinely new infrastructure, no other loop in this codebase fires at fixed clock times today), registered in `bot/bot.py` alongside the three already-running loops (`run_notification_dispatcher`, `run_free_pack_notifier`, `run_premium_subscription_check`), in both `run_polling()` and `run_webhook()`. Each loop calls a backend internal endpoint over HTTP (the same `aiohttp.ClientSession` + `X-Internal-Secret` header pattern `bot/handlers/chat_pack.py` already uses). All notification *content* decisions happen in the backend; the bot only delivers.

## The two loops

```python
SIMULATION_SLOTS: list[tuple[int, int]] = [(12, 0), (20, 0)]  # (hour, minute), server-local
REMINDER_LEAD_MINUTES = 60
LOOP_CHECK_INTERVAL_SECONDS = 900  # 15 min
```

Both loops share the same catch-up shape as `daily_reminder.py`'s `last_sent_date`/hour-threshold check, generalized from "once a day" to "once per slot per day": track `last_fired: dict[tuple[int,int], date]` keyed by slot, and on each 15-minute wake-up, for every slot whose fire-time (simulation loop: the slot itself; reminder loop: the slot minus `REMINDER_LEAD_MINUTES`) has passed today and hasn't fired today yet, fire it. This means a bot restart or transient outage that misses the exact minute still fires once the loop is back up, rather than silently skipping the day — important because `simulate_next_round`'s own guarantee ("no club ever skips a scheduled round") depends on every slot actually firing, not just approximately firing.

- **`run_simulation_loop(bot)`**: on each due slot, `POST {internal_backend_url}/internal/clubs/simulate-round` (already exists, unchanged). Log the response (`matches_simulated` count) at INFO; log+continue (never crash the loop) on any request failure, matching every other loop's `try/except Exception: logger.exception(...)` shape.
- **`run_lineup_reminder_loop(bot)`**: on each due slot-minus-60-min, `POST {internal_backend_url}/internal/clubs/lineup-reminders` (new).

## New internal endpoint: `POST /internal/clubs/lineup-reminders`

Guarded by `verify_internal_secret` (added to the existing `/internal` router, same as every other internal route). Calls a new `tournament_notification_service.send_lineup_reminders(db) -> int`:

For every `Tournament` with `status == active` and `rounds_simulated < 14`: compute `round_number = rounds_simulated + 1`, fetch that tournament's `TournamentClub` rows **ordered by `id`** (matching the exact ordering `simulate_next_round` itself uses — `generate_fixtures` is a pure function keyed on list order, so computing this round's fixtures with a differently-ordered club-id list would predict the wrong pairings), and get that round's fixtures via `generate_fixtures` (Task 7, unchanged). For each fixture where **neither** club is `is_withdrawn` (a fixture touching a withdrawn club auto-resolves as a 0–3 with no engine run for either side — per Task 14's design, neither club "plays" a real match that round, so neither needs a suspension check), check both clubs' active `ClubLineup`'s 11 slots for any card whose `ClubCardAvailability.rounds_remaining > 0`. If found, `notify()` every member of that club (`club_lineup_reminder` type, no deep-link — generic "open the app" button, since there's no single object to link to). Commit once at the end. Returns the count of clubs notified, surfaced in the endpoint's response for the bot's log line.

This reuses the exact same "which cards are suspended" check `tournament_simulation_service.resolve_match_lineup` already does (Task 12) — but this is a **read-only preview**, not a simulation, so it must not mutate anything; it's a new, smaller function that duck-types the same `ClubCardAvailability` lookup rather than calling `resolve_match_lineup` (which also performs substitution and returns engine-shaped actor dicts neither needed nor wanted here).

## Notification hooks added to already-shipped Phase 3a code

Two functions gain `notify()` calls — both already accept a `db: AsyncSession` and already sit inside a single commit boundary per round/conclusion, so no new transaction handling is needed, just additional `db.add`-via-`notify()` calls before the existing `await db.commit()`:

- **`tournament_simulation_service.simulate_next_round`**: after persisting each real (non-withdrawn) `TournamentMatch`, fetch both clubs' member lists and `notify()` every member of both (`club_match` type, `related_object_type="club_match"`, `related_object_id=tournament.id`). Withdrawn-club auto-loss matches do **not** notify (nothing meaningful happened for either side to react to).
- **`tournament_reward_service.conclude_tournament`**: after writing each `TournamentClubResult`, `notify()` every member of that club (`club_tournament_results_ready` type, no deep-link — generic "open the app" button, since the frontend's own "replay-first, then results unlock" sequencing gate means there's no single URL that's valid to jump straight into yet).

## New `NotificationType` members

`club_match`, `club_lineup_reminder`, `club_tournament_results_ready` — three new Postgres enum values via `ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS`, exact idiom already used for every prior addition to this enum (e.g. `club_kicked` in Phase 1). One new Alembic migration, `0071`, sequential from the current head (`0070`).

## Bot-side deep-link routing

`bot/services/notifier.py`'s `_MATCH_PATH_PREFIXES` gains one entry: `"club_match": "/clubs/tournament"` (not `/clubs/tournament/matches` — per the Corrections section above, this deep-links to the bracket page, keyed by `related_object_id=tournament_id`, not a specific match). `club_lineup_reminder` and `club_tournament_results_ready` are deliberately absent from this dict — `_keyboard_for` already falls back to no custom button (just the generic "open the app" keyboard every notification gets) when a type has no prefix entry, so no code change is needed there beyond the one new dict entry.

## Testing plan

- `send_lineup_reminders`: a suspended starter in an upcoming round's lineup produces exactly one notification per club member, none for clubs with no suspension, none for either side of a fixture where one club is withdrawn, and it's read-only (no `ClubCardAvailability`/`ClubLineup` row is mutated by calling it).
- `simulate_next_round`'s new notify calls: a simulated round produces the right notification count (2 clubs × member count, per real match; zero for withdrawn-club auto-losses) with the right `type`/`related_object_id`.
- `conclude_tournament`'s new notify calls: round 14 produces one `club_tournament_results_ready` notification per member per club (8 clubs × their member counts).
- The two bot loops' catch-up logic: unit-testable in isolation (pure function taking "now" and "last fired per slot" as inputs, returning "which slots are due") — do not require real `asyncio.sleep`-driven timing tests, which would be slow/flaky; test the decision function directly.
- Real-Postgres verification for the new `notification_type_enum` values, per this codebase's established practice.
