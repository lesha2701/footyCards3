# Leagues ("Лиги") — Design Spec

## Goal

Introduce a meta-progression ladder ("leagues") that players climb by earning rating across the three modes that already have a rating concept: Card Arena (`arena_rating`), Тактико (`tactics_rating`), Пенальти (`penalty_rating`). League rating is the live sum of these three fields — no new stored/cached total, computed on read.

Leagues are purely a presentation + reward layer on top of the existing rating fields, with three changes to how those fields themselves are earned (see "Rating rule changes" below), plus a new admin-managed tier ladder, a home-screen banner, a detail/leaderboard screen, a rules/help modal, and a one-time (repeatable, idempotent) retroactive reward pass for players who already have rating when leagues launch.

## Rating rule changes

These are changes to the *existing* rating-grant logic in `tactico_service.py` and `penalty_match_service.py` — not a new parallel system. `tactics_rating`/`penalty_rating` themselves stop changing for friend matches; nothing reads a separate "league-only" ledger.

| Mode | Today | New |
|---|---|---|
| Тактико vs friend | ±3/-1/+1 to both sides | **No change to `tactics_rating` at all**, either side. Coins were already 0 for friend matches — friend matches become pure-fun, zero progression. |
| Тактико vs bot (Лёгкий) | win +3 | **win +1** (loss -1, draw +1 unchanged) |
| Тактико vs bot (Средний/Продвинутый) | +3/-1/+1 | unchanged |
| Тактико online (matchmaking) | ±3/-1/+1 to both sides | **×2 all outcomes**: win +6/-2, loss -2/+6, draw +2/+2 (same mirroring logic as today, just doubled) |
| Пенальти vs friend | ±3/-1/+1 to both sides | **No change to `penalty_rating` at all**, either side — same reasoning as Тактико friend |
| Пенальти vs bot | ±3/-1 | unchanged |
| Пенальти online (matchmaking) | ±3/-1/+1 to both sides | **×2 all outcomes**, same as Тактико online |
| Card Arena (any difficulty) | +3/-1/+1 | **unchanged** — explicitly out of scope; only Тактико's Лёгкий bot gets the farming cap |

Card Arena has no friend/online concept (bot-only), so no friend/×2 rule applies there.

## Data model

### `LeagueTier` (new table, admin-managed)

Mirrors `TrophyDefinition`'s shape (id, name, icon, admin CRUD, `is_active` not needed — deleting a tier is enough since nothing else references it by id except claims, which cascade).

```python
class LeagueTier(TimestampMixin, Base):
    __tablename__ = "league_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)          # "Дворовая лига", "Высшая лига", etc — admin's own football-flavored names
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)  # total (arena+tactics+penalty) needed to enter this tier
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="🏆")    # emoji, same convention as TrophyDefinition.icon
    reward_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

`min_rating=0` should exist as the bottom tier (everyone starts in a league, not "no league") — the admin page should nudge toward this but it's not DB-enforced; `GET /leagues/status` handles the "no tier matches" case by returning `current_league: null` regardless (covers the pre-setup window too).

### `UserLeagueRewardClaim` (new table, idempotency ledger)

```python
class UserLeagueRewardClaim(Base):
    __tablename__ = "user_league_reward_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    league_tier_id: Mapped[int] = mapped_column(ForeignKey("league_tiers.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "league_tier_id"),)
```

## League progression engine

One function, `league_service.sync_league_rewards_for_user(db, user, *, notify_mode="per_tier" | "summary") -> list[LeagueTier]`:

1. Compute `total = user.arena_rating + user.tactics_rating + user.penalty_rating`.
2. Fetch all `LeagueTier` where `min_rating <= total`.
3. Fetch this user's existing `UserLeagueRewardClaim` tier ids.
4. For every qualifying tier not yet claimed: credit `reward_coins` (if > 0, via `credit_coins` same as collection rewards), grant `reward_pack_id` (if set, via the same pack-opening path `grant_collection_rewards_for_new_cards`'s sibling code uses), insert the claim row.
5. Return the newly-granted tiers (caller decides what to do with them — commit is the caller's responsibility, matching this codebase's existing service-function convention).

This same function serves both:
- **Live play**: called at the end of every rating-affecting match-finish path (Тактико `_finish_match` for bot/online only — not friend, since friend no longer touches rating; Пенальти's equivalent bot/online finish paths; Card Arena's match finish). `notify_mode="per_tier"` — send one `league_promoted` notification per newly-granted tier (in practice almost always 0 or 1 tiers per call).
- **Retroactive rollout**: the admin "Начислить награды" endpoint loops over every user and calls this with `notify_mode="summary"` — if any tiers were newly granted, send exactly one notification summarizing the player's current (final) league, not one per tier, so a player who jumps 5 tiers at launch doesn't get 5 notifications.

## API surface

### Public (`GET`, any logged-in user)

- `GET /leagues` → `list[LeagueTierOut]` (id, name, min_rating, icon, reward_coins, reward_pack_name). Full ladder, ordered by `min_rating` ascending. Powers the detail screen's ladder view and the rules modal's rating-math explanation.
- `GET /leagues/status` → `LeagueStatusOut`:
  ```
  total_rating: int
  arena_rating: int
  tactics_rating: int
  penalty_rating: int
  current_league: LeagueTierOut | null
  next_league: LeagueTierOut | null
  points_to_next: int | null
  ```
  `current_league` is the highest tier with `min_rating <= total_rating` (`null` if no tiers configured, or none with `min_rating <= 0`... in practice always non-null once the admin sets up a `min_rating=0` tier). `next_league` is the lowest tier with `min_rating > total_rating` (`null` if already at the top tier).

### Leaderboard (reuse existing generic endpoint)

Add `league_rating` to `RankingMetric` and to `ranking_service._DIRECT_COLUMNS` as a computed expression `(User.arena_rating + User.tactics_rating + User.penalty_rating)`. The existing `GET /leaderboard/ranking?metric=league_rating` then returns top-10 + "me" in the same `RankingOut` shape every other ranking already uses — no new endpoint.

### Admin (`/admin/leagues`, existing `get_current_admin` dependency pattern)

- `GET /admin/leagues` → all tiers (no pagination needed — this list stays small).
- `POST /admin/leagues` → create (`LeagueTierCreate`).
- `PUT /admin/leagues/{id}` → update (`LeagueTierUpdate`, all fields optional).
- `DELETE /admin/leagues/{id}` → delete (cascades `UserLeagueRewardClaim` rows for it).
- `POST /admin/leagues/backfill-rewards` → runs `sync_league_rewards_for_user(notify_mode="summary")` for every non-banned user, returns `{"rewarded_count": int}` (count of users who received at least one new tier grant). Safe to call repeatedly.

## Frontend

**Home screen**: new banner card (visually distinct from the existing claim-style notice cards — a persistent status display, not a "claim me" prompt) placed under the quick-actions row, above the Wheel/daily-reward/free-pack cards. Shows current league icon + name and a slim progress bar toward `next_league` ("ещё N очков до «X»"). Tapping navigates to `/league`.

**`/league` detail screen**:
- Own-stats card: current league, total rating with a 3-way breakdown (Арена / Тактико / Пенальти), progress bar to next tier.
- Full ladder (from `GET /leagues`), current tier highlighted.
- Top-10 leaderboard (`GET /leaderboard/ranking?metric=league_rating`), reusing `RankingPage.tsx`'s existing list-rendering pattern.
- "?" icon button (same small circular button `TacticoMatchesPage` uses for its rules modal) opening the league rules modal.

**League rules modal**: same data-driven `sections` pattern as `TacticoRulesModal` — explains the ladder concept, that rating = sum of the three modes, and the specific earning rules (friend = 0, online = ×2, Тактико Лёгкий bot = +1 win only).

**Existing rules-modal text fix**: `TacticoRulesModal`'s "Против друга" section and Пенальти's equivalent currently justify friend-match rating as an anti-collusion-for-coins measure — now stale since friend matches no longer touch rating at all. Update both to describe the new zero-rating-for-friend behavior.

**Admin**: new "Лиги" sidebar page, list/edit-modal/delete UI mirroring `AdminTrophiesPage.tsx` exactly (name, min_rating, icon, reward_coins, reward_pack picker), plus a "Начислить награды" button calling the backfill endpoint and showing the returned count.

## Notifications

New `NotificationType.league_promoted`. Sent by `sync_league_rewards_for_user`:
- Live crossing: one notification per newly-granted tier — "Новая лига! Ты в «{name}»" style, mirroring `trophy_granted`'s existing copy tone.
- Retroactive backfill: one summary notification per affected user regardless of how many tiers were granted in that pass.

## Edge cases

- **No tiers configured**: `GET /leagues/status` returns `current_league: null` — home banner doesn't render. No error state.
- **Banned/admin accounts**: excluded from the `league_rating` leaderboard, consistent with every other `ranking_service` metric.
- **Rating floor**: existing `max(0, ...)` clamps on all three rating fields are untouched — league total can't go negative.
- **Tier deletion after claims exist**: cascades away the claim rows for that tier (no orphan-prevention needed — if the admin removes a tier, its historical "you earned this" record going away is an acceptable admin action, same as deleting any other admin-defined reward-granting entity in this codebase).

## Testing

- Backend: rating-grant rule tests per mode (Тактико friend = 0 delta both sides, Тактико Лёгкий bot win = +1, Тактико online = ×2 all outcomes; same three for Пенальти minus the bot-difficulty case since Пенальти's bot has no difficulty tiers).
- `sync_league_rewards_for_user`: single-tier crossing, multi-tier jump in one call (the retroactive-rollout scenario), already-claimed idempotency (calling twice grants nothing the second time), zero-tiers-configured no-op.
- Admin CRUD + backfill endpoint tests (auth-gating, backfill idempotency, backfill actually reaching multiple users).
- Frontend: typecheck coverage is sufficient (this app's Vitest suite is unit-level utilities, not page-level) — no new Vitest tests required, matching how prior page-level features in this codebase were verified (manual Playwright smoke-check during implementation instead).
