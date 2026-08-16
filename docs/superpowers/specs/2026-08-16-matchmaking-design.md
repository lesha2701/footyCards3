# Opponent Matchmaking for Tactico and Penalty (Подбор соперника)

## Goal

Add automatic online-opponent matchmaking to two existing PvP mini-games,
Тактико (turn-based squad-vs-squad) and Пенальти (penalty shootout). A
player presses "Играть" and is automatically paired with any other player
currently searching for the same game — no rating/skill filtering for this
first version, match against whoever is waiting. Before the match starts,
both players see who they've been matched against: nickname, avatar,
badge, and the relevant game rating.

This reuses the existing friend-challenge match architecture for both
games almost entirely — matchmaking is a second way to *create* an
already-proven match flow, not a new game mode.

## Existing architecture (context, not new work)

Both games already have a full asynchronous PvP flow built on a single
shared match row per game (`TacticoMatch` / `PenaltyMatch`), with
`user_id` (challenger) / `opponent_user_id` (challenged), a
`pending_accept → in_progress → finished` status lifecycle, and a "lazy
sweep" pattern for timeouts: overdue rounds/matches are resolved
opportunistically whenever either player's client calls `list_matches`/
`get_match`, not by a background scheduler (see
`tactico_service._auto_play_overdue_rounds` and
`penalty_match_service._auto_resolve_overdue`). There is no websocket or
background-worker infrastructure in this project, and matchmaking does not
introduce any — it reuses this same polling-driven lazy pattern.

`_hydrate_match` on both services already renders the match
viewer-relative (`side = "user" | "opponent"`), so a matchmade match is
indistinguishable from a friend match once created — the existing match
page, round submission, forfeit, and `matchGuardStore` navigation guard
all apply completely unchanged.

## Matching mechanism

New per-game queue tables (mirroring the existing convention that each
mini-game owns its own tables rather than sharing generic ones):

```python
class TacticoQueueEntry(Base):
    __tablename__ = "tactico_queue_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tactico_matches.id", ondelete="SET NULL"), nullable=True)

class PenaltyQueueEntry(Base):
    __tablename__ = "penalty_queue_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("penalty_matches.id", ondelete="SET NULL"), nullable=True)
```

`user_id` is `unique` — a player can have at most one queue entry per game,
enforced at the DB level, not just in application logic.

**Enum additions:**
- `TacticoOpponentType` gains a third member, `online`, alongside the
  existing `bot`/`friend`.
- `PenaltyMatch` currently has no "how was this matched" concept at all —
  it has only ever been friend-challenges. Add a new `PenaltyOpponentType`
  enum (`friend`, `online`) and a `PenaltyMatch.opponent_type` column,
  `server_default='friend'` so every existing and future friend-challenge
  row is unaffected.

### Pairing algorithm

Matching happens *inside the status-polling endpoint itself* — there is no
separate sweep or background job. Every player who is searching is already
polling their own status every ~2s (see Frontend section); that poll is
also the only place pairing is attempted, for both sides. This is the same
"the reader does the lazy work" principle the existing round-timeout
sweeps already use, applied to matchmaking instead of match timeouts.

Pseudocode (identical shape for Tactico and Penalty, differing only in
which queue/match table is touched):

```
BEGIN TRANSACTION
  my_entry = SELECT * FROM <Game>QueueEntry WHERE user_id = me FOR UPDATE
  if my_entry is None:
      COMMIT; return "not_searching"

  if my_entry.matched_match_id is not None:
      COMMIT; return "matched", match_id = my_entry.matched_match_id

  if now - my_entry.created_at > 60s:
      DELETE my_entry
      COMMIT; return "timeout"

  candidate = SELECT * FROM <Game>QueueEntry
              WHERE user_id != me AND matched_match_id IS NULL
              ORDER BY created_at LIMIT 1
              FOR UPDATE SKIP LOCKED
  if candidate is None:
      COMMIT; return "searching"

  # Re-validate right before creating the match — state may have drifted
  # during however long both entries sat in the queue. Each side is
  # checked independently; either, both, or neither may have gone stale.
  invalid = []
  if _has_active_match(me): invalid.append(my_entry)
  if _has_active_match(candidate.user_id): invalid.append(candidate)
  if game == penalty:
      if my card is no longer owned by me: invalid.append(my_entry)
      if candidate's card is no longer owned by candidate.user_id: invalid.append(candidate)
  if invalid:
      DELETE each entry in invalid (de-duplicated)
      COMMIT
      # If my own entry was one of the invalidated ones (e.g. I somehow
      # already have an active match from another tab), I have nothing
      # left to wait on; otherwise I'm still validly queued and just
      # missed this candidate.
      return "not_searching" if my_entry in invalid else "searching"

  match = create TacticoMatch/PenaltyMatch(status=in_progress, opponent_type=online, ...)
  consume hourly slot for both players (game_config.hourly_game_limit, same shared counter bot/friend matches use)
  my_entry.matched_match_id = match.id
  candidate.matched_match_id = match.id
  COMMIT
  return "matched", match_id = match.id
```

`FOR UPDATE SKIP LOCKED` on the candidate lookup is what makes this safe
under real concurrency without deadlocking: if player B's poll is
mid-transaction pairing with player C, and player A's poll concurrently
tries to find a candidate, A's query simply skips B's locked row instead
of blocking on it — no two polls can ever pair the same entry twice, and
no two polls can deadlock waiting on each other's row.

Locking *my own row first, then the candidate* (never the reverse order)
is what prevents a deadlock between two players' own transactions each
trying to lock the other's row — combined with `SKIP LOCKED`, a losing
transaction just moves on to a different candidate rather than blocking.

**Hourly limit and hourly cost timing:** the hourly attempt counter
(`tactico_hourly_attempts` / `penalty_hourly_attempts`, shared with bot
matches, `GameConfig.hourly_game_limit`) is consumed only at the moment of
pairing, not at "join queue" time — a 60-second search that finds no one
must not cost the player an attempt.

**Rating and rewards:** a finished `online`-type match updates
`tactics_rating`/`penalty_rating` through the exact same `_finish_match`
win/draw/loss delta logic (+3/+1/-1, opposite mapping for the other side)
already used for friend matches — no new logic. Coin rewards are **not**
granted for `online` matches, matching the existing friend-match behavior
(`_finish_match`'s coin-reward branch already only fires for
`opponent_type == bot`; `online` simply never enters it, no new
conditional needed beyond not adding it to that branch). This is a
deliberate anti-collusion measure: two accounts controlled by the same
person could otherwise queue simultaneously and farm coins by matching
each other.

## API

New endpoints, one set per game (mirrors the existing
`/tactico/*`/`/penalty/*` router structure):

- `POST /tactico/matchmaking/search` — join the queue. Validates: squad is
  complete (`get_squad(...).is_complete`), no active match
  (`_has_active_match`), no existing queue entry for this user. Creates
  `TacticoQueueEntry`. Returns the entry's `created_at` so the frontend can
  compute its own 60s countdown without trusting client clock skew for the
  actual timeout decision (the server is still the source of truth via the
  `timeout` status).
- `GET /tactico/matchmaking/status` — runs the pairing algorithm above,
  returns `{status: "searching" | "matched" | "timeout" | "not_searching", match_id: int | null}`.
- `POST /tactico/matchmaking/cancel` — voluntary leave. Locks own entry
  first (same `FOR UPDATE` as the algorithm); if `matched_match_id` is
  already set by the time the lock is acquired, cancellation is rejected
  (`ConflictError`) and the match stands — the frontend's next status poll
  will pick up the `matched` state normally.
- Identical three endpoints under `/penalty/matchmaking/...`, except
  `search` additionally accepts `user_card_id` (validated via the existing
  `_load_owned_card` helper) and stores it on `PenaltyQueueEntry`.

**Public profile extension:** `ProfilePublicOut` (returned by the existing
`GET /users/{user_id}`, already used for the pre-match reveal per the
Frontend section) gains two new always-present fields, `tactics_rating`
and `penalty_rating`, alongside the existing `arena_rating` — no new
endpoint, no new schema, just two fields on the object every "view another
player" flow in the app already fetches.

## Frontend

**Entry point:** `TacticoMatchesPage`/`PenaltyMatchesPage` gain a new,
visually primary **"Играть"** button (full-width, larger/more prominent
than the existing "Играть с ботом" / "Вызвать друга" pair, which move
below it as secondary options — the existing side-by-side equal-weight
button row is re-laid-out under this new primary CTA). For Penalty,
tapping "Играть" opens the existing `CardPickerModal` first (identical to
the friend-challenge card pick already in that page) before calling
`search`.

**Searching screen** (new full-screen view, same visual weight as the
match page it precedes):
- Spinner + "Ищем соперника..." + a "Отменить" button (calls `cancel`,
  then navigates back — no confirmation needed, no penalty, since nothing
  has been risked yet).
- Polls `GET .../matchmaking/status` every ~2s.
- `timeout` → "Соперник не найден" + a "Попробовать снова" button
  (re-calls `search`).
- `matched` → immediately transitions to the reveal screen below; the
  searching screen itself never renders the match.

**Opponent-reveal screen** (new, sits between "matched" and the actual
match page):
- Fetches the opponent's public profile (`GET /users/{opponent_id}`, using
  `opponent_user_id` from the newly created match) and displays avatar,
  nickname, active badge, and the relevant game's rating
  (`tactics_rating` for Tactico, `penalty_rating` for Penalty) — all
  already present on `ProfilePublicOut` after the API addition above, no
  bespoke schema.
- Auto-advances to `/play/tactico/matches/:id` (or the Penalty equivalent)
  after a fixed 3-second pause — no manual "Ready" confirmation from
  either side, per the approved automatic-start decision. The match is
  already `in_progress` server-side the moment it's created, so both
  players' clients independently land on the live match page around the
  same time; neither is blocked waiting on the other.

**Navigation guard:** the searching screen has no `matchGuardStore`
guard — leaving it is always free, since no match exists yet. The instant
the frontend observes `matched`, ordinary existing match-page behavior
takes over unchanged: `matchGuardStore.activate(...)` (already wired into
the match page for bot/friend matches) applies identically, including the
existing forfeit-on-leave and `pagehide` keepalive-forfeit behavior.

## Error handling and safety

- **No duplicate/self pairing:** `user_id != me` in the candidate query
  natively excludes self-matching; the unique constraint on
  `QueueEntry.user_id` prevents a player from being paired twice
  concurrently (a second `search` call while already queued is rejected
  with `ConflictError`, not silently creating a second entry).
- **Stale queue entries:** an entry whose owner closed the app mid-search
  is simply never polled again by its own owner, but it's still visible to
  *other* players' pairing attempts until the 60s timeout — a concurrent
  candidate-query from someone else could still pair with it inside the
  window, which is correct (the original searcher, if they come back and
  poll, will see `matched`). Past 60s it's excluded from candidate
  selection by the `created_at` check inside the algorithm, and gets
  physically deleted the next time its own owner polls (or, if they never
  come back, it just sits inert and unmatched — harmless, and cleaned up
  naturally the next time that user tries to search again, since `search`
  can overwrite/replace a self-owned stale entry rather than erroring).
- **Card/squad drift while queued:** re-validated at pairing time (see
  algorithm) rather than only at `search` time — a card traded away or a
  squad broken mid-wait cannot produce a broken match; the affected side's
  entry is dropped and that player's next poll simply reports `searching`
  again (their frontend should surface this as "продолжаем искать" rather
  than an error, since from their point of view nothing failed, matching
  just needs to happen again).
- **Concurrency correctness is the primary testing focus** — see Testing.

## Testing

Backend (`pytest`, real concurrent requests where the property under test
is concurrency itself — not mocked):

- Full happy path per game: search → matched → play through to a finished
  result → rating updated on both sides with the correct win/draw/loss
  deltas → zero coins credited.
- Timeout: a lone searcher with no candidate reaches `timeout` at the
  configured window, and their entry is removed.
- Voluntary cancel before match, and cancel-after-match-exists correctly
  rejected (not silently a no-op) with the existing match still valid.
- Two real concurrent status-poll requests (via `asyncio.gather` or
  equivalent, not sequential calls) from two waiting players resolve to
  exactly one shared match, never zero, never two.
- A three-or-more-way concurrent scenario (three players polling at once,
  only two should pair) resolves without deadlock and leaves exactly one
  player still searching.
- Hourly limit is consumed at pairing, not at `search`.
- Penalty: a card sold/traded away between `search` and pairing correctly
  drops that entry instead of creating a match with an invalid card
  reference.
- `ProfilePublicOut` now serializes `tactics_rating`/`penalty_rating`.

Frontend: `npm run typecheck`; manual verification of the full flow
(two logged-in sessions/dev-mode users, one on each side) — search, reveal
screen shows correct opponent data, match plays out normally, cancel
works, timeout UI shows correctly.

## Out of scope (this iteration)

- Any rating/skill-based matching filter — explicitly "match anyone
  waiting," per the request.
- Any accept/decline step for a matchmade pairing — it starts
  automatically.
- Coin rewards for matchmade matches.
- A persistent "who's currently searching" count/lobby display.
- Rematch/"play again vs same opponent" shortcuts.
