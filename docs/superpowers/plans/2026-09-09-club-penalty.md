# Club Penalty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Что исчезло?" club mini-game with a club-scoped, bot-only Penalty
shootout — the player picks any card from the club's squad (not their personal
collection) and plays the exact same bot-only Penalty mechanics already live in the
main game, with the reward crediting the club's budget instead of the player's wallet.

**Architecture:** Port `backend/app/services/penalty_service.py`'s bot-only mechanics
(shared, imported directly — `PENALTY_ZONES`, `REGULATION_KICKS`, `_resolve_shot`,
`player_miss_chance` — not re-implemented) into a new `club_penalty_service.py` that
swaps personal `UserCard`/wallet-credit for club `ClubCard`/club-budget-credit, mirroring
`club_missing_item_service.py`'s club-scoping idiom (`_require_membership`, `_lock_club`,
`credit_club_budget`, per-user hourly/daily rate limiting). The frontend reuses the
existing `PenaltyGoalScene` animation and `ClubCardPickerModal` picker unchanged, in a
new `ClubPenaltyPage.tsx` modeled on `PenaltyGamePage.tsx`'s bot-only flow plus
`ClubMissingItemPage.tsx`'s club-budget finish screen. "Что исчезло?" is fully removed:
its service, schemas, router endpoints, frontend page, types, API functions, and admin
config section are all deleted as part of this same plan.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 + TypeScript + TanStack
Query (frontend), Alembic migrations, pytest (async, in-memory SQLite; Postgres for
migration/locking verification per this repo's CLAUDE.md).

**Spec:** No separate spec document — this plan was scoped directly in chat with the
user (a "bounded" change per the brainstorming skill: a well-understood port of one
existing feature into another existing feature's slot, with clear precedent on both
sides). The full research this plan is based on is summarized in the Global Constraints
below and in each task's own context.

## Global Constraints

- **Nothing else about "Что исчезло?" broke** — this plan removes it deliberately, in
  full, as its explicit purpose. Do not treat its removal as accidental scope; do not
  try to preserve any of its UI/routes/config "just in case."
- **The bot-only Penalty mechanics must be reused, not reimplemented.** Import
  `PENALTY_ZONES`, `REGULATION_KICKS`, `_resolve_shot`, `player_miss_chance` directly
  from `app.services.penalty_service` — this is the exact pattern
  `penalty_match_service.py` (the PvP Penalty system) already uses for the same reason.
  Never touch `penalty_service.py`, `penalty_match_service.py`, or anything under
  `/play/penalty*` — those are a completely separate, already-working system this plan
  does not modify.
- **Club Penalty stays decoupled from the personal track**, matching
  `club_missing_item_service.py` and `club_game_service.py`'s own precedent: no
  `penalty_rating` equivalent, no `league_service` call, no `task_service` hook. Reward
  goes to `club.budget` via `club_budget_service.credit_club_budget`, never to the
  player's personal wallet.
- **Gating is `_require_membership`** (any club member may play), not `_require_manager`
  — matching both existing club games, not the captain/assistant-only lineup-editing
  rule.
- **Card ownership check**: a club card is eligible if `ClubCard.id == club_card_id AND
  ClubCard.club_id == membership.club_id` — mirrors `club_squad_service.py`'s exact
  idiom for validating a card belongs to the caller's own club. `ClubCard.player` is
  `lazy="joined"` — no explicit `joinedload` needed when fetching a `ClubCard`.
  Cards already assigned to the club's tactical lineup are still eligible (no
  `is_in_lineup` restriction) — this is a different, unrelated card use.
- **Postgres enum values can never be dropped once added** (`ALTER TYPE ... DROP VALUE`
  doesn't exist in Postgres) — this repo's own established rule, see the
  `coach_pack_purchase` comment in `backend/app/models/enums.py`. `GameType.club_missing_item`
  and `ClubBudgetTransactionType.club_missing_item_reward` MUST stay in their Python
  enums forever, even though nothing will construct them going forward after this plan.
  Table **columns** are not enum values and CAN be dropped safely — the `club_missing_item_*`
  columns on `User`/`GameConfig` are removed as dead weight once nothing reads/writes them.
- **Every `nullable=False` column added to an existing table needs `server_default=`
  in the migration's `op.add_column(...)` call**, not just a Python-side `default=` on
  the model — `default=` only applies to new ORM inserts, not to the existing row(s) an
  `ALTER TABLE ADD COLUMN` has to backfill. See `0097_pack_coach_slots.py`'s
  `coach_drop_chance` column for the established precedent.
- **`GameSession` is fully generic** (`server_state: JSON`) — club Penalty needs no
  dedicated round table (unlike `MissingItemRound`, which stays untouched, dead-but-inert,
  since dropping it isn't necessary and its historical rows have no bearing on this
  plan). Store `club_id` in `server_state` at start time, exactly like
  `club_missing_item_service.start_session` already does, so `claim_reward` knows which
  club's budget to credit without a second lookup.
- **`session.status = GameSessionStatus.won` is set on EVERY finish, win or loss** —
  this is a real, intentional quirk of `penalty_service.py`'s existing code (`won` means
  "finished, reward claimable", not "the player won"; the actual outcome lives in
  `state["result"]`). Mirror this exactly. Do not "fix" it — it works, it's tested, and
  changing it is out of scope.
- Use async DB access only; never trust frontend-supplied values for rewards; keep
  probability/economy calculations backend-only (this repo's CLAUDE.md mandatory rules).

---

### Task 1: Backend — models + migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/game_config.py`
- Create: `backend/alembic/versions/0099_club_penalty.py`

**Interfaces:**
- Produces: `GameType.club_penalty`, `ClubBudgetTransactionType.club_penalty_reward`;
  `User.club_penalty_rewarded_attempts_today` / `club_penalty_attempts_reset_at` /
  `club_penalty_hourly_attempts` / `club_penalty_hour_started_at`;
  `GameConfig.club_penalty_hourly_limit` / `club_penalty_daily_reward_limit` /
  `club_penalty_reward_win` / `club_penalty_reward_loss` / `club_penalty_bot_miss_chance`.
  Task 2's service consumes all of these by exact name.

- [ ] **Step 1: Add the two enum members**

In `backend/app/models/enums.py`, in `GameType` (currently ends `club_missing_item =
"club_missing_item"`), add a line right after it:

```python
class GameType(str, enum.Enum):
    memory_sequence = "memory_sequence"
    card_arena = "card_arena"
    saboteur = "saboteur"
    penalty = "penalty"
    free_kick = "free_kick"
    football_hangman = "football_hangman"
    card_pairs = "card_pairs"
    club_sequence = "club_sequence"
    club_missing_item = "club_missing_item"
    club_penalty = "club_penalty"
```

In `ClubBudgetTransactionType` (currently has `club_missing_item_reward =
"club_missing_item_reward"` followed by the `coach_pack_purchase` dead-value comment
block), add the new member right after `club_missing_item_reward`, before that comment:

```python
class ClubBudgetTransactionType(str, enum.Enum):
    daily_claim = "daily_claim"
    pack_purchase = "pack_purchase"
    tournament_reward = "tournament_reward"
    club_game_reward = "club_game_reward"
    club_missing_item_reward = "club_missing_item_reward"
    club_penalty_reward = "club_penalty_reward"
    # Zero writers left anywhere in the codebase — the dedicated ClubCoachPack system
    # that produced this value was removed (see 0095_drop_club_coach_packs.py). Do NOT
    # delete this member: Postgres cannot drop a single enum value once added, so the
    # real DB enum still carries 'coach_pack_purchase' and removing the Python member
    # would break parity with it.
    coach_pack_purchase = "coach_pack_purchase"
```

- [ ] **Step 2: Add club_penalty columns on User — do NOT touch club_missing_item columns**

`club_missing_item_service.py` is still live and wired into the router at this point in
the plan (it isn't deleted until Task 4) — its `_ensure_daily_reset`/`_ensure_hourly_reset`/
`start_session`/`claim_reward` all read and write the `club_missing_item_*` columns on
every real request. Dropping those columns now would break that still-live feature for
the entire window between this task and Task 4. Both column blocks coexist in the model
until Task 4 deletes the service and the columns together, atomically.

In `backend/app/models/user.py`, the current block (around line 103) reads:

```python
    # Что исчезло? (club-scoped mini-game; reward credits the club's budget)
    club_missing_item_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_missing_item_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    club_missing_item_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_missing_item_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Leave it completely unchanged. Add a NEW block right after it:

```python
    # Пенальти (club-scoped mini-game; reward credits the club's budget)
    club_penalty_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_penalty_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    club_penalty_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_penalty_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3: Add club_penalty columns on GameConfig — do NOT touch club_missing_item columns**

Same reasoning as Step 2. In `backend/app/models/game_config.py`, the current block
(around line 35) reads:

```python
    club_missing_item_hourly_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    club_missing_item_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_missing_item_reward_cap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
```

Leave it completely unchanged. Add a NEW block right after it:

```python
    club_penalty_hourly_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    club_penalty_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_penalty_reward_win: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    club_penalty_reward_loss: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    club_penalty_bot_miss_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.12, nullable=False)
```

(`Numeric` is already imported at the top of this file — it's used by
`club_form_bonus_per_result` a few lines above.)

- [ ] **Step 4: Write the migration — additive only**

Run `cd backend && alembic revision -m "club penalty"` to get a fresh revision file
skeleton, then replace its contents with (confirm the auto-generated `revision`/
`down_revision` match — head is `0098` at plan-start time, so this should land as
`0099`; if another migration has landed first, adjust `down_revision` and the filename
number to match the real current head):

```python
"""Club Penalty — replaces "Что исчезло?" as the third club mini-game

Revision ID: 0099
Revises: 0098
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: Union[str, None] = "0098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("club_penalty_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_penalty_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_penalty_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_penalty_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_penalty_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_penalty_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_penalty_reward_win", sa.Integer(), nullable=False, server_default="45"))
    op.add_column("game_config", sa.Column("club_penalty_reward_loss", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("club_penalty_bot_miss_chance", sa.Numeric(4, 2), nullable=False, server_default="0.12"))


def downgrade() -> None:
    op.drop_column("users", "club_penalty_rewarded_attempts_today")
    op.drop_column("users", "club_penalty_attempts_reset_at")
    op.drop_column("users", "club_penalty_hourly_attempts")
    op.drop_column("users", "club_penalty_hour_started_at")

    op.drop_column("game_config", "club_penalty_hourly_limit")
    op.drop_column("game_config", "club_penalty_daily_reward_limit")
    op.drop_column("game_config", "club_penalty_reward_win")
    op.drop_column("game_config", "club_penalty_reward_loss")
    op.drop_column("game_config", "club_penalty_bot_miss_chance")
```

This migration ONLY adds columns — it must not touch `club_missing_item_*` at all.
Task 4 gets its own separate migration to drop them, once the service using them is
gone.

- [ ] **Step 5: Verify against real Postgres**

Run: `docker compose exec backend alembic upgrade head`, then confirm via
`docker compose exec postgres psql -U postgres -d footycards -c "\d users"` and `\d
game_config"` that the new `club_penalty_*` columns are present AND the
`club_missing_item_*` columns are still there, untouched. Then run `docker compose exec
backend alembic downgrade -1` followed by `alembic upgrade head` again to confirm the
round-trip is clean (no leftover constraint/column conflicts), leaving the DB at head
when done.

- [ ] **Step 6: Sanity check + commit**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint python football-cards-backend:latest -c "from app.main import app"`
— expect no import errors. Run the full backend suite (`docker run --rm -v
"$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`) —
expect only the one pre-existing, unrelated failure
(`test_tasks.py::test_task_reward_pack_grants_all_cards`); nothing else should break
from this purely-additive column/enum change — in particular,
`test_club_missing_item_game.py` must pass completely unmodified, since
`club_missing_item_service.py` and its columns are untouched by this task.

```bash
git add backend/app/models/enums.py backend/app/models/user.py backend/app/models/game_config.py backend/alembic/versions/0099_club_penalty.py
git commit -m "feat(club-penalty): add club_penalty model fields and migration (additive only)"
```

---

### Task 2: Backend — schemas + service

**Files:**
- Create: `backend/app/schemas/club_penalty.py`
- Create: `backend/app/services/club_penalty_service.py`
- Test: `backend/tests/test_club_penalty_game.py`

**Interfaces:**
- Consumes: `GameType.club_penalty`, `ClubBudgetTransactionType.club_penalty_reward`,
  the 4 `User.club_penalty_*` columns, the 5 `GameConfig.club_penalty_*` columns (Task
  1). `PENALTY_ZONES`, `REGULATION_KICKS`, `_resolve_shot`, `player_miss_chance` from
  `app.services.penalty_service` (pre-existing, unmodified). `_lock_club`,
  `_require_membership` from `app.services.club_service` (pre-existing, module-private
  — already imported this way by `club_missing_item_service.py`, an accepted pattern in
  this codebase). `credit_club_budget` from `app.services.club_budget_service`
  (pre-existing).
- Produces: `start_session(db, user, club_card_id) -> ClubPenaltyStartOut`,
  `resolve_kick(db, user, session_id, direction) -> ClubPenaltyKickOut`,
  `claim_reward(db, user, session_id) -> ClubPenaltyClaimOut`,
  `forfeit_session(db, user, session_id) -> ClubPenaltyForfeitOut`. Task 3's router
  calls all four by exact name.

- [ ] **Step 1: Write the schemas**

Create `backend/app/schemas/club_penalty.py`:

```python
from typing import Optional

from pydantic import BaseModel


class ClubPenaltyStartRequest(BaseModel):
    club_card_id: int


class ClubPenaltyStartOut(BaseModel):
    session_id: int
    player_rating: int
    first_kicker: str


class ClubPenaltyKickRequest(BaseModel):
    direction: str


class ClubPenaltyKickOut(BaseModel):
    session_id: int
    kicker: str
    outcome: str
    player_direction: Optional[str] = None
    bot_direction: str
    player_score: int
    bot_score: int
    next_kicker: Optional[str] = None
    is_finished: bool
    result: Optional[str] = None


class ClubPenaltyClaimOut(BaseModel):
    reward_coins: int
    new_club_budget: int
    result: str
    # True when reward_coins is 0 specifically because the player already used up
    # today's rewarded attempts for this game — same meaning as
    # ClubMissingItemClaimOut.daily_cap_reached.
    daily_cap_reached: bool = False


class ClubPenaltyForfeitOut(BaseModel):
    session_id: int
    player_score: int
    bot_score: int
    result: str
```

- [ ] **Step 2: Write the service**

Create `backend/app/services/club_penalty_service.py`:

```python
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, GameType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.club_penalty import (
    ClubPenaltyClaimOut,
    ClubPenaltyForfeitOut,
    ClubPenaltyKickOut,
    ClubPenaltyStartOut,
)
from app.services.club_budget_service import credit_club_budget
from app.services.club_service import _lock_club, _require_membership
from app.services.game_config_service import get_config
from app.services.penalty_service import PENALTY_ZONES, REGULATION_KICKS, _resolve_shot, player_miss_chance
from app.services.wallet_service import lock_user_for_update


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.club_penalty_attempts_reset_at) if user.club_penalty_attempts_reset_at else None
    if reset_day != today:
        user.club_penalty_rewarded_attempts_today = 0
        user.club_penalty_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.club_penalty_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.club_penalty_hourly_attempts = 0
        user.club_penalty_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User, club_card_id: int) -> ClubPenaltyStartOut:
    membership = await _require_membership(db, user.id)
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.club_penalty_hourly_attempts >= config.club_penalty_hourly_limit:
        remaining = timedelta(hours=1) - (
            datetime.now(timezone.utc) - ensure_aware(locked_user.club_penalty_hour_started_at)
        )
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.club_penalty_hourly_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.club_penalty_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    result = await db.execute(
        select(ClubCard).where(ClubCard.id == club_card_id, ClubCard.club_id == membership.club_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.club_penalty, status=GameSessionStatus.in_progress,
        server_state={
            "club_id": membership.club_id, "selected_card_id": card.id, "player_rating": card.player.rating,
            "rounds": [], "player_score": 0, "bot_score": 0, "kicks_taken": 0, "sudden_death": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ClubPenaltyStartOut(session_id=session.id, player_rating=card.player.rating, first_kicker="player")


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.club_penalty:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _current_kicker(state: dict) -> str:
    return "player" if state["kicks_taken"] % 2 == 0 else "bot"


def _apply_finish(session: GameSession, state: dict, result: str, config) -> None:
    """Shared by a natural finish (resolve_kick) and an explicit forfeit — marks the
    session finished with the given result and its reward. Unlike personal Penalty, no
    rating/league/task hooks: club mini-games stay decoupled from the personal track,
    same as club_game_service and club_missing_item_service. session.status is always
    GameSessionStatus.won regardless of win/loss — mirrors penalty_service.py's own
    quirk exactly ("won" means "finished, reward claimable", not "the player won"; the
    real outcome lives in state["result"])."""
    state["result"] = result
    session.server_state = state
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = {
        "win": config.club_penalty_reward_win, "loss": config.club_penalty_reward_loss,
    }[result]


async def resolve_kick(db: AsyncSession, user: User, session_id: int, direction: str) -> ClubPenaltyKickOut:
    if direction not in PENALTY_ZONES:
        raise ConflictError("Invalid direction")

    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    kicker = _current_kicker(state)

    if kicker == "player":
        bot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(player_miss_chance(state["player_rating"]), direction, bot_dir)
        if outcome == "goal":
            state["player_score"] += 1
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_shot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(float(config.club_penalty_bot_miss_chance), bot_shot_dir, direction)
        if outcome == "goal":
            state["bot_score"] += 1
        round_entry = {
            "kicker": "bot", "player_direction": direction, "bot_direction": bot_shot_dir, "outcome": outcome,
        }

    state["rounds"] = list(state["rounds"]) + [round_entry]
    state["kicks_taken"] += 1

    is_finished = False
    result: str | None = None
    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0:
        if state["player_score"] != state["bot_score"]:
            is_finished = True
        else:
            state["sudden_death"] = True

    session.server_state = state
    if is_finished:
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        _apply_finish(session, state, result, config)

    db.add(session)
    await db.commit()

    next_kicker = None if is_finished else _current_kicker(state)
    return ClubPenaltyKickOut(
        session_id=session.id, kicker=kicker, outcome=outcome,
        player_direction=direction, bot_direction=round_entry["bot_direction"],
        player_score=state["player_score"], bot_score=state["bot_score"],
        next_kicker=next_kicker, is_finished=is_finished, result=result,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> ClubPenaltyClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.club_penalty_rewarded_attempts_today >= config.club_penalty_daily_reward_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.club_penalty_rewarded_attempts_today += 1
    db.add(locked_user)
    db.add(session)

    club_id = (session.server_state or {}).get("club_id")
    new_budget = None
    if reward > 0 and club_id is not None:
        club = await _lock_club(db, club_id)
        if club is not None and not club.is_disbanded:
            await credit_club_budget(
                db, club, reward, ClubBudgetTransactionType.club_penalty_reward,
                f"Пенальти: {user.username or user.first_name or f'#{user.id}'}",
                related_object_type="game_session", related_object_id=session.id,
            )
            new_budget = club.budget
        else:
            reward = 0

    await db.commit()

    if new_budget is None and club_id is not None:
        club = await db.get(Club, club_id)
        new_budget = club.budget if club is not None else 0

    return ClubPenaltyClaimOut(
        reward_coins=reward, new_club_budget=new_budget or 0, daily_cap_reached=daily_cap_reached,
        result=session.server_state["result"],
    )


async def forfeit_session(db: AsyncSession, user: User, session_id: int) -> ClubPenaltyForfeitOut:
    """Immediately ends an in-progress session as a loss for the player, regardless of
    the partial score — mirrors penalty_service.forfeit_session's same rule. Called from
    the frontend's leave-confirmation dialog (matchGuardStore)."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session is not in progress")

    state = dict(session.server_state)
    _apply_finish(session, state, "loss", config)
    db.add(session)
    await db.commit()

    return ClubPenaltyForfeitOut(
        session_id=session.id, player_score=state["player_score"], bot_score=state["bot_score"], result="loss",
    )
```

- [ ] **Step 3: Write service-level tests**

Create `backend/tests/test_club_penalty_game.py`. Mirror
`test_club_missing_item_game.py`'s fixture and club-creation helper exactly (a fresh
club auto-seeds a starting squad via `club_service.create_club`, drawing from whatever
`Player` pool the test seeded first):

```python
import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club creation — give
    every test in this file enough active players per formation category to draw from,
    mirroring test_club_missing_item_game.py's identical fixture."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_and_join(client, bot_token, telegram_id, name):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _first_club_card_id(client, headers) -> int:
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert cards, "expected create_club's auto-seeded starting squad to give at least one club card"
    return cards[0]["id"]


async def test_penalty_start_requires_club_membership(client, bot_token):
    headers = telegram_headers(764001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": 1})
    assert resp.status_code == 404


async def test_penalty_start_rejects_a_card_from_another_club(client, bot_token):
    _, headers_a = await _create_club_and_join(client, bot_token, 764002, "Клуб А")
    other_card_id = await _first_club_card_id(client, headers_a)

    _, headers_b = await _create_club_and_join(client, bot_token, 764003, "Клуб Б")
    resp = await client.post(
        "/api/v1/clubs/me/penalty/start", headers=headers_b, json={"club_card_id": other_card_id}
    )
    assert resp.status_code == 404


async def test_penalty_full_shootout_reaches_a_result_and_credits_club_budget(client, bot_token):
    club, headers = await _create_club_and_join(client, bot_token, 764004, "Пенальти Клуб")
    card_id = await _first_club_card_id(client, headers)

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    is_finished = False
    result = None
    for _ in range(40):  # regulation (10) + generous sudden-death headroom
        kick = await client.post(
            f"/api/v1/clubs/me/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"}
        )
        assert kick.status_code == 200
        body = kick.json()
        if body["is_finished"]:
            is_finished = True
            result = body["result"]
            break
    assert is_finished
    assert result in ("win", "loss")

    claim = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    claim_body = claim.json()
    assert claim_body["result"] == result
    assert claim_body["reward_coins"] > 0

    club_resp = await client.get("/api/v1/clubs/me", headers=headers)
    assert club_resp.status_code == 200
    assert club_resp.json()["budget"] == club["budget"] + claim_body["reward_coins"]


async def test_penalty_forfeit_mid_match_counts_as_a_loss(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 764005, "Форфейт Клуб")
    card_id = await _first_club_card_id(client, headers)

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    session_id = start.json()["session_id"]

    forfeit = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/forfeit", headers=headers)
    assert forfeit.status_code == 200
    assert forfeit.json()["result"] == "loss"

    kick_after_forfeit = await client.post(
        f"/api/v1/clubs/me/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"}
    )
    assert kick_after_forfeit.status_code == 409
```

Note: these tests hit `/api/v1/clubs/me/penalty/*`, which does not exist until Task 3
wires up the router — this task's own test run will therefore 404 on every request
until Task 3 lands. That is expected and fine: Task 3's own verification step is what
actually turns this test file green. Do not try to make Task 2 pass in isolation by
guessing at router shape; write the tests against the schemas/service you just built and
let Task 3 close the loop.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/club_penalty.py backend/app/services/club_penalty_service.py backend/tests/test_club_penalty_game.py
git commit -m "feat(club-penalty): add club-scoped bot-only Penalty service, reusing penalty_service's shared mechanics"
```

---

### Task 3: Backend — router + admin config + club activity feed

**Files:**
- Modify: `backend/app/routers/clubs.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/club_activity_service.py`

**Interfaces:**
- Consumes: `club_penalty_service.start_session/resolve_kick/claim_reward/forfeit_session`,
  `ClubPenaltyStartRequest`/`ClubPenaltyKickRequest`/`ClubPenaltyStartOut`/
  `ClubPenaltyKickOut`/`ClubPenaltyClaimOut`/`ClubPenaltyForfeitOut` (Task 2).
- Produces: `POST /clubs/me/penalty/start`, `POST /clubs/me/penalty/{session_id}/kick`,
  `POST /clubs/me/penalty/{session_id}/claim`, `POST /clubs/me/penalty/{session_id}/forfeit`
  — Task 5's frontend API client calls these four routes by exact path.

- [ ] **Step 1: Read the current file section you're editing**

Read `backend/app/routers/clubs.py` in full once (already read this session — re-read
to confirm the exact current line numbers before editing, since earlier tasks in other
plans may have shifted them). You are ADDING the new `/me/penalty/*` routes here; do NOT
remove the `/me/missing-item/*` routes yet — that happens in Task 4, as its own reviewable
step. Both blocks will coexist in this file between Task 3 and Task 4.

- [ ] **Step 2: Add the schema import**

In the `from app.schemas.club_missing_item import (...)` import block, leave it as-is
(Task 4 removes it). Add a new import right after it:

```python
from app.schemas.club_penalty import (
    ClubPenaltyClaimOut,
    ClubPenaltyForfeitOut,
    ClubPenaltyKickOut,
    ClubPenaltyKickRequest,
    ClubPenaltyStartOut,
    ClubPenaltyStartRequest,
)
```

- [ ] **Step 3: Add the service import**

In the `from app.services import (...)` tuple (currently: `club_activity_service,
club_game_service, club_missing_item_service, club_pack_service, club_ranking_service,
club_service, club_squad_service, tournament_match_engine, tournament_queue_service`),
add `club_penalty_service` — keep the list alphabetically sorted, so it lands right after
`club_pack_service` and before `club_ranking_service`:

```python
from app.services import (
    club_activity_service,
    club_game_service,
    club_missing_item_service,
    club_pack_service,
    club_penalty_service,
    club_ranking_service,
    club_service,
    club_squad_service,
    tournament_match_engine,
    tournament_queue_service,
)
```

- [ ] **Step 4: Add the four routes**

Add this block right after the existing `claim_missing_item_reward` route (i.e.
immediately before `@router.post("/tournament/apply", ...)`):

```python
@router.post("/me/penalty/start", response_model=ClubPenaltyStartOut)
async def start_club_penalty(
    payload: ClubPenaltyStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"club_penalty_start:{user.id}", max_calls=20, window_seconds=60)
    return await club_penalty_service.start_session(db, user, payload.club_card_id)


@router.post("/me/penalty/{session_id}/kick", response_model=ClubPenaltyKickOut)
async def kick_club_penalty(
    session_id: int, payload: ClubPenaltyKickRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_penalty_service.resolve_kick(db, user, session_id, payload.direction)


@router.post("/me/penalty/{session_id}/claim", response_model=ClubPenaltyClaimOut)
async def claim_club_penalty_reward(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_penalty_service.claim_reward(db, user, session_id)


@router.post("/me/penalty/{session_id}/forfeit", response_model=ClubPenaltyForfeitOut)
async def forfeit_club_penalty(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_penalty_service.forfeit_session(db, user, session_id)
```

- [ ] **Step 5: Update the club activity feed to count club_penalty sessions**

In `backend/app/services/club_activity_service.py`, `get_club_activity`'s query
currently filters:

```python
                GameSession.game_type.in_([GameType.club_sequence, GameType.club_missing_item]),
```

Change it to:

```python
                # club_missing_item stays in this list even though nothing produces it
                # going forward (see club_penalty plan, 2026-09-09) — it's a 7-day
                # rolling window (ACTIVITY_WINDOW_DAYS), so recently-played sessions from
                # before the cutover still need to count until they age out naturally.
                GameSession.game_type.in_([GameType.club_sequence, GameType.club_missing_item, GameType.club_penalty]),
```

Also update this function's docstring (currently: `"""Club-scoped activity only: the
club's own mini-games (GameType.club_sequence and club_missing_item, played via
/clubs/game and /clubs/missing-item — ..."""`) to mention `/clubs/penalty` instead of
`/clubs/missing-item`, since that route stops existing after Task 7.

- [ ] **Step 6: Update the admin GameConfig schema**

In `backend/app/schemas/admin.py`, `GameConfigOut` currently has (leave the
`club_missing_item_*` lines in place — Task 4 removes them):

```python
    club_missing_item_hourly_limit: int
    club_missing_item_daily_reward_limit: int
    club_missing_item_reward_cap: int
```

Add right after those three lines:

```python
    club_penalty_hourly_limit: int
    club_penalty_daily_reward_limit: int
    club_penalty_reward_win: int
    club_penalty_reward_loss: int
    club_penalty_bot_miss_chance: float
```

Do the identical addition in `GameConfigUpdate`, right after its own
`club_missing_item_*` block:

```python
    club_penalty_hourly_limit: Optional[int] = Field(default=None, ge=1)
    club_penalty_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    club_penalty_reward_win: Optional[int] = Field(default=None, ge=0)
    club_penalty_reward_loss: Optional[int] = Field(default=None, ge=0)
    club_penalty_bot_miss_chance: Optional[float] = Field(default=None, ge=0, le=1)
```

(`admin_games.py`'s `update_config` route needs no change — it already applies
`GameConfigUpdate`'s fields generically via `setattr` in a loop.)

- [ ] **Step 7: Run the tests**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_penalty_game.py tests/test_club_activity.py -v`
— all of `test_club_penalty_game.py` (written in Task 2, unreachable until now) should
pass; `test_club_activity.py` should be unaffected (it inserts `game_type="club_missing_item"`
directly and asserts on the resulting count — still valid since that value stays in the
IN-list). Then run the FULL suite (not just these two files) — expect only the one
pre-existing, unrelated failure.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/clubs.py backend/app/schemas/admin.py backend/app/services/club_activity_service.py
git commit -m "feat(club-penalty): wire up /clubs/me/penalty/* routes, admin config fields, and club activity counting"
```

---

### Task 4: Backend — remove "Что исчезло?"

**Files:**
- Delete: `backend/app/services/club_missing_item_service.py`
- Delete: `backend/app/schemas/club_missing_item.py`
- Delete: `backend/tests/test_club_missing_item_game.py`
- Modify: `backend/app/routers/clubs.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/game_config.py`
- Create: `backend/alembic/versions/0100_drop_club_missing_item_columns.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only removes dead surface. `MissingItemRound`
  (`backend/app/models/game.py`) and `GameType.club_missing_item` /
  `ClubBudgetTransactionType.club_missing_item_reward` (enums.py) are explicitly OUT OF
  SCOPE for this task — leave them exactly as they are (see Global Constraints: the two
  enum values can never be dropped from Postgres, and the round table's historical rows
  have no bearing on this removal).
- **This is the task that drops the `club_missing_item_*` columns from `User` and
  `GameConfig`** — Task 1 deliberately left them in place (additive-only migration)
  specifically because `club_missing_item_service.py` was still live and reading/writing
  them at that point. Now that this task deletes the service itself, the columns become
  genuinely dead and safe to drop in the same task, atomically — no window where a live
  feature loses its backing columns.

- [ ] **Step 1: Delete the three whole files**

```bash
git rm backend/app/services/club_missing_item_service.py backend/app/schemas/club_missing_item.py backend/tests/test_club_missing_item_game.py
```

- [ ] **Step 2: Remove the missing-item routes and imports from clubs.py**

Read the current file fresh (Task 3 already added new content above the block you're
about to delete — line numbers have moved). Remove:

- The `from app.schemas.club_missing_item import (...)` import block in full.
- `club_missing_item_service` from the `from app.services import (...)` tuple (keep the
  rest of that tuple, including `club_penalty_service`, alphabetically sorted).
- These five routes, in full:

```python
@router.post("/me/missing-item/start", response_model=ClubMissingItemStartOut)
async def start_missing_item_game(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"club_missing_item_start:{user.id}", max_calls=20, window_seconds=60)
    return await club_missing_item_service.start_session(db, user)


@router.post("/me/missing-item/{session_id}/reveal", response_model=ClubMissingItemRevealOut)
async def reveal_missing_item_round(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_missing_item_service.reveal_round(db, user, session_id)


@router.post("/me/missing-item/{session_id}/submit", response_model=ClubMissingItemSubmitOut)
async def submit_missing_item_round(
    session_id: int, payload: ClubMissingItemSubmitRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_missing_item_service.submit_round(db, user, session_id, payload.answer)


@router.post("/me/missing-item/{session_id}/end", response_model=ClubMissingItemSubmitOut)
async def end_missing_item_game(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_missing_item_service.end_session(db, user, session_id)


@router.post("/me/missing-item/{session_id}/claim", response_model=ClubMissingItemClaimOut)
async def claim_missing_item_reward(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_missing_item_service.claim_reward(db, user, session_id)
```

- [ ] **Step 3: Remove the admin GameConfig schema fields**

In `backend/app/schemas/admin.py`, remove these three lines from `GameConfigOut`:

```python
    club_missing_item_hourly_limit: int
    club_missing_item_daily_reward_limit: int
    club_missing_item_reward_cap: int
```

And these three from `GameConfigUpdate`:

```python
    club_missing_item_hourly_limit: Optional[int] = Field(default=None, ge=1)
    club_missing_item_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    club_missing_item_reward_cap: Optional[int] = Field(default=None, ge=0)
```

- [ ] **Step 4: Drop the now-dead club_missing_item columns**

In `backend/app/models/user.py`, remove this block entirely (it has sat unused since
Task 1 added the `club_penalty_*` block right after it — leave that `club_penalty_*`
block untouched):

```python
    # Что исчезло? (club-scoped mini-game; reward credits the club's budget)
    club_missing_item_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_missing_item_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    club_missing_item_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_missing_item_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

In `backend/app/models/game_config.py`, remove this block entirely (same reasoning,
leave the `club_penalty_*` block Task 1 added right after it untouched):

```python
    club_missing_item_hourly_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    club_missing_item_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_missing_item_reward_cap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
```

Run `cd backend && alembic revision -m "drop club missing item columns"` to get a fresh
revision skeleton, then replace its contents with (confirm the auto-generated
`revision`/`down_revision` match — head is `0099` once Task 1 has landed, so this should
land as `0100`; if something else has landed first, adjust to match the real current
head):

```python
"""Drop the now-dead club_missing_item_* columns — club_missing_item_service is
removed in this same commit, so nothing reads or writes them any more

Revision ID: 0100
Revises: 0099
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0100"
down_revision: Union[str, None] = "0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "club_missing_item_rewarded_attempts_today")
    op.drop_column("users", "club_missing_item_attempts_reset_at")
    op.drop_column("users", "club_missing_item_hourly_attempts")
    op.drop_column("users", "club_missing_item_hour_started_at")

    op.drop_column("game_config", "club_missing_item_hourly_limit")
    op.drop_column("game_config", "club_missing_item_daily_reward_limit")
    op.drop_column("game_config", "club_missing_item_reward_cap")


def downgrade() -> None:
    op.add_column("users", sa.Column("club_missing_item_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_missing_item_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_missing_item_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_missing_item_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_missing_item_reward_cap", sa.Integer(), nullable=False, server_default="100"))
```

Verify against real Postgres: `docker compose exec backend alembic upgrade head`, then
confirm via `docker compose exec postgres psql -U postgres -d footycards -c "\d users"`
and `\d game_config"` that `club_missing_item_*` is gone and `club_penalty_*` is still
present. Then `docker compose exec backend alembic downgrade -1` followed by `alembic
upgrade head` again to confirm a clean round-trip, leaving the DB at head when done.

- [ ] **Step 5: Verify nothing else references the removed module**

Run: `grep -rn "club_missing_item_service\|ClubMissingItem\|club_missing_item_hourly_limit\|club_missing_item_daily_reward_limit\|club_missing_item_reward_cap\|club_missing_item_rewarded_attempts_today\|club_missing_item_attempts_reset_at\|club_missing_item_hourly_attempts\|club_missing_item_hour_started_at" backend/app/`
— expect ZERO matches (the `GameType.club_missing_item` / `ClubBudgetTransactionType.club_missing_item_reward`
enum member NAMES will still appear in `enums.py` and in `club_activity_service.py`'s
IN-list — that's correct and expected, not a leftover reference to clean up).

- [ ] **Step 6: Run the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint python football-cards-backend:latest -c "from app.main import app"`
then the full suite. Expect only the one pre-existing, unrelated failure — specifically
confirm `test_club_activity.py` still passes (it references the `club_missing_item`
enum VALUE directly via a raw string, not the deleted service or its columns, so it
should be unaffected).

- [ ] **Step 7: Commit**

```bash
git add -A backend/
git commit -m "refactor(club-penalty): remove club_missing_item_service, its schemas, routes, tests, admin config fields, and now-dead columns"
```

---

### Task 5: Frontend — types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/clubs.ts`
- Modify: `frontend/src/admin/types.ts`

**Interfaces:**
- Consumes: nothing new (mirrors Task 2/3's backend shapes by hand — this repo has no
  codegen step from OpenAPI to TS).
- Produces: `ClubPenaltyStart`, `ClubPenaltyKick`, `ClubPenaltyClaim`,
  `ClubPenaltyForfeit` (types); `startClubPenalty`, `kickClubPenalty`,
  `claimClubPenaltyReward`, `forfeitClubPenalty` (API functions). Task 6's
  `ClubPenaltyPage.tsx` consumes all of these by exact name.

- [ ] **Step 1: Replace the ClubMissingItem* types with ClubPenalty* types**

In `frontend/src/types/index.ts`, the current block (around line 347) reads:

```typescript
export interface ClubMissingItemStart {
  session_id: number;
  round_number: number;
  items: string[];
}

export interface ClubMissingItemReveal {
  session_id: number;
  round_number: number;
  items_shown: string[];
  hide_after_ms: number;
  answer_timeout_ms: number;
}

export interface ClubMissingItemSubmitResult {
  correct: boolean;
  session_id: number;
  score: number;
  status: string;
  next_round?: ClubMissingItemStart;
}

export interface ClubMissingItemClaimResult {
  reward_coins: number;
  new_club_budget: number;
  daily_cap_reached: boolean;
}
```

Replace it with:

```typescript
export interface ClubPenaltyStart {
  session_id: number;
  player_rating: number;
  first_kicker: "player" | "bot";
}

export interface ClubPenaltyKick {
  session_id: number;
  kicker: "player" | "bot";
  outcome: "goal" | "saved" | "miss";
  player_direction: PenaltyDirection | null;
  bot_direction: PenaltyDirection;
  player_score: number;
  bot_score: number;
  next_kicker: "player" | "bot" | null;
  is_finished: boolean;
  result: "win" | "loss" | null;
}

export interface ClubPenaltyClaim {
  reward_coins: number;
  new_club_budget: number;
  result: string;
  daily_cap_reached: boolean;
}

export interface ClubPenaltyForfeit {
  session_id: number;
  player_score: number;
  bot_score: number;
  result: string;
}
```

`PenaltyDirection` is already defined further down this same file (around line 864) —
no new import needed since this is all one module, but this new block is being inserted
BEFORE that type's declaration (order doesn't matter for TypeScript type declarations
within a module — forward references between `interface`/`type` in the same file are
fine).

- [ ] **Step 2: Replace the missing-item API functions with club-penalty ones**

In `frontend/src/api/clubs.ts`, update the type import block: remove
`ClubMissingItemClaimResult, ClubMissingItemReveal, ClubMissingItemStart,
ClubMissingItemSubmitResult` and add `ClubPenaltyClaim, ClubPenaltyForfeit,
ClubPenaltyKick, ClubPenaltyStart, PenaltyDirection` (keep the import list alphabetically
sorted; `PenaltyDirection` is needed for `kickClubPenalty`'s parameter type below).

Replace the current block (around line 173):

```typescript
export async function startMissingItemGame(): Promise<ClubMissingItemStart> {
  const { data } = await api.post<ClubMissingItemStart>("/clubs/me/missing-item/start");
  return data;
}

export async function revealMissingItemRound(sessionId: number): Promise<ClubMissingItemReveal> {
  const { data } = await api.post<ClubMissingItemReveal>(`/clubs/me/missing-item/${sessionId}/reveal`);
  return data;
}

export async function submitMissingItemRound(sessionId: number, answer: string): Promise<ClubMissingItemSubmitResult> {
  const { data } = await api.post<ClubMissingItemSubmitResult>(`/clubs/me/missing-item/${sessionId}/submit`, { answer });
  return data;
}

export async function endMissingItemGame(sessionId: number): Promise<ClubMissingItemSubmitResult> {
  const { data } = await api.post<ClubMissingItemSubmitResult>(`/clubs/me/missing-item/${sessionId}/end`);
  return data;
}

export async function claimMissingItemReward(sessionId: number): Promise<ClubMissingItemClaimResult> {
  const { data } = await api.post<ClubMissingItemClaimResult>(`/clubs/me/missing-item/${sessionId}/claim`);
  return data;
}
```

with:

```typescript
export async function startClubPenalty(clubCardId: number): Promise<ClubPenaltyStart> {
  const { data } = await api.post<ClubPenaltyStart>("/clubs/me/penalty/start", { club_card_id: clubCardId });
  return data;
}

export async function kickClubPenalty(sessionId: number, direction: PenaltyDirection): Promise<ClubPenaltyKick> {
  const { data } = await api.post<ClubPenaltyKick>(`/clubs/me/penalty/${sessionId}/kick`, { direction });
  return data;
}

export async function claimClubPenaltyReward(sessionId: number): Promise<ClubPenaltyClaim> {
  const { data } = await api.post<ClubPenaltyClaim>(`/clubs/me/penalty/${sessionId}/claim`);
  return data;
}

export async function forfeitClubPenalty(sessionId: number): Promise<ClubPenaltyForfeit> {
  const { data } = await api.post<ClubPenaltyForfeit>(`/clubs/me/penalty/${sessionId}/forfeit`);
  return data;
}
```

- [ ] **Step 3: Update admin/types.ts**

In `frontend/src/admin/types.ts`, replace:

```typescript
  club_missing_item_hourly_limit: number;
  club_missing_item_daily_reward_limit: number;
  club_missing_item_reward_cap: number;
```

with:

```typescript
  club_penalty_hourly_limit: number;
  club_penalty_daily_reward_limit: number;
  club_penalty_reward_win: number;
  club_penalty_reward_loss: number;
  club_penalty_bot_miss_chance: number;
```

And update `AdminClubBudgetTransaction`'s `type` union (currently `"daily_claim" |
"pack_purchase" | "tournament_reward" | "club_game_reward" |
"club_missing_item_reward"`) to add the new value, keeping the old one for historical
transaction rows still in the DB:

```typescript
  type: "daily_claim" | "pack_purchase" | "tournament_reward" | "club_game_reward" | "club_missing_item_reward" | "club_penalty_reward";
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck` — this WILL fail at this point, because
`ClubMissingItemPage.tsx` still imports the now-deleted `startMissingItemGame` etc.
functions from `@/api/clubs`, and `AdminGamesPage.tsx` still calls `field(...)` with the
now-removed `club_missing_item_*` keys. That is expected — Task 7 deletes
`ClubMissingItemPage.tsx` entirely, and Task 8 fixes `AdminGamesPage.tsx`.
`ClubGamesPage.tsx` and `App.tsx` do NOT reference anything this task removed (they
navigate to `/clubs/missing-item` by plain string route / import the page component,
neither of which broke yet), so they should show no NEW errors — they'll keep pointing
at the old page/route until Task 7 rewires them, which is a behavior gap, not a type
error, at this point. Confirm the typecheck errors you see are confined to
`ClubMissingItemPage.tsx` and `AdminGamesPage.tsx` — if you see an error anywhere else,
that's a real problem introduced by this task and must be fixed before moving on.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/clubs.ts frontend/src/admin/types.ts
git commit -m "feat(club-penalty): add frontend types + API client for club penalty, remove club-missing-item ones"
```

---

### Task 6: Frontend — ClubPenaltyPage

**Files:**
- Create: `frontend/src/pages/ClubPenaltyPage.tsx`

**Interfaces:**
- Consumes: `startClubPenalty`, `kickClubPenalty`, `claimClubPenaltyReward`,
  `forfeitClubPenalty` (Task 5); `fetchClubCards`, `fetchMyClub` (pre-existing,
  `@/api/clubSquad` and `@/api/clubs` respectively); `ClubCardPickerModal`
  (pre-existing, `@/components/clubs/ClubCardPickerModal`); `PenaltyGoalScene`
  (pre-existing, `@/components/penalty/PenaltyGoalScene`, unmodified).
- Produces: default export `ClubPenaltyPage`. Task 7 routes `/clubs/penalty` to it.

- [ ] **Step 1: Read the two pages this mirrors**

Read `frontend/src/pages/PenaltyGamePage.tsx` in full (already read this session — the
"С ботом" phase flow, `PenaltyGoalScene` wiring, `matchGuardStore` integration, and the
900ms settle-then-advance `useEffect` are all reused near-verbatim). Read
`frontend/src/pages/ClubMissingItemPage.tsx` in full (already read this session — the
club-budget finish-screen pattern: `Бюджет клуба +N`, `Новый бюджет клуба: N`,
`daily_cap_reached` messaging, and the `fetchMyClub` query for interpolating the club's
name into the idle-screen description).

- [ ] **Step 2: Write the page**

Create `frontend/src/pages/ClubPenaltyPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimClubPenaltyReward, fetchMyClub, forfeitClubPenalty, kickClubPenalty, startClubPenalty } from "@/api/clubs";
import { fetchClubCards } from "@/api/clubSquad";
import ClubCardPickerModal from "@/components/clubs/ClubCardPickerModal";
import { IconChevronLeft, IconCoin, IconFlagCheckered, IconTrophy } from "@/components/icons";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useMatchGuardStore } from "@/store/matchGuardStore";
import type { ClubPenaltyKick, PenaltyDirection } from "@/types";

type Phase = "idle" | "pick_card" | "playing" | "finished";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

function goalKickFrom(result: ClubPenaltyKick): PenaltyGoalKick | null {
  if (!result.player_direction) return null;
  return result.kicker === "player"
    ? { shotZone: result.player_direction, diveZone: result.bot_direction, outcome: result.outcome }
    : { shotZone: result.bot_direction, diveZone: result.player_direction, outcome: result.outcome };
}

function outcomeLabelFor(result: ClubPenaltyKick): { label: string; good: boolean } {
  if (result.kicker === "player") {
    if (result.outcome === "goal") return { label: "Гол!", good: true };
    if (result.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (result.outcome === "saved") return { label: "Отбил!", good: true };
  if (result.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function ClubPenaltyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [lastKick, setLastKick] = useState<ClubPenaltyKick | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number; new_club_budget: number; daily_cap_reached: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [settled, setSettled] = useState(true);
  const [pickedZone, setPickedZone] = useState<PenaltyDirection | null>(null);

  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const { data: clubCards } = useQuery({ queryKey: ["clubs", "me", "cards"], queryFn: fetchClubCards });

  const startMutation = useMutation({
    mutationFn: startClubPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => {
      setPhase("idle");
      setErrorMsg(formatGameError(err, "Не удалось начать игру"));
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimClubPenaltyReward(sessionId!),
    onSuccess: (data) => {
      hapticNotify("success");
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
    },
  });

  const kickMutation = useMutation({
    mutationFn: (direction: PenaltyDirection) => kickClubPenalty(sessionId!, direction),
    onSuccess: (result) => {
      haptic(result.outcome === "goal" || result.outcome === "saved" ? "medium" : "light");
      setLastKick(result);
    },
  });

  // Same hold-then-advance pattern as PenaltyGamePage: let the deciding kick's
  // animation play before swapping this whole screen out for the finish screen.
  useEffect(() => {
    if (!lastKick) {
      setSettled(true);
      return;
    }
    setSettled(false);
    const timer = setTimeout(() => {
      setSettled(true);
      setPickedZone(null);
      if (lastKick.is_finished) {
        hapticNotify(lastKick.result === "win" ? "success" : "error");
        setPhase("finished");
        claimMutation.mutate();
        queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      }
    }, 900);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastKick]);

  useEffect(() => {
    if (phase === "playing" && sessionId != null) {
      useMatchGuardStore.getState().activate(
        "Серия пенальти не завершена. Если выйдешь сейчас, она будет засчитана как поражение.",
        () => {
          forfeitClubPenalty(sessionId)
            .then(() => claimClubPenaltyReward(sessionId))
            .catch(() => {});
        },
        `/clubs/me/penalty/${sessionId}/forfeit`,
      );
    } else {
      useMatchGuardStore.getState().deactivate();
    }
    return () => useMatchGuardStore.getState().deactivate();
  }, [phase, sessionId]);

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/clubs/games")} className="rounded-full bg-bg-surface p-2 active:scale-95">
            <IconChevronLeft size={18} className="text-ink-chalk" />
          </button>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        </div>

        <p className="text-sm text-ink-mist">
          Серия пенальти против бота — выбери игрока из состава клуба{club ? ` «${club.name}»` : ""}. Чем выше его
          рейтинг, тем меньше шанс промазать по воротам. Доступно раз в час каждому участнику клуба — награда
          пополняет бюджет клуба.
        </p>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        <button
          onClick={() => setPhase("pick_card")}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
        >
          Начать игру
        </button>
      </div>
    );
  }

  if (phase === "pick_card") {
    return (
      <ClubCardPickerModal
        open
        title="Выбери игрока"
        cards={clubCards ?? []}
        onSelect={(card) => startMutation.mutate(card.id)}
        onClose={() => setPhase("idle")}
      />
    );
  }

  if (phase === "finished") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        {lastKick?.result === "win" ? (
          <IconTrophy size={40} className="text-accent-lime" />
        ) : (
          <IconFlagCheckered size={40} className="text-ink-mist" />
        )}
        <p className="font-display text-2xl font-bold text-ink-chalk">
          {lastKick?.result === "win" ? "Победа!" : "Поражение"}
        </p>
        <p className="text-sm text-ink-mist">
          Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score} : {lastKick?.bot_score}</span>
        </p>

        {claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claimResult ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Бюджет клуба +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
            <p className="text-xs text-accent-green">Новый бюджет клуба: {claimResult.new_club_budget}</p>
            {claimResult.reward_coins === 0 && claimResult.daily_cap_reached && (
              <p className="mt-1 text-xs text-amber-300">
                Дневной лимит наградных попыток в этой игре исчерпан — результат не пропал, но награда не
                начисляется до завтра.
              </p>
            )}
          </div>
        ) : claimMutation.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claimMutation.error, "Не удалось начислить награду")}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button onClick={() => setPhase("idle")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/clubs/games")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const isPlayerKicking = !lastKick || lastKick.next_kicker === "player";
  const roleLabel = kickMutation.isPending
    ? "..."
    : isPlayerKicking
      ? "Твой удар — выбери зону"
      : "Бот бьёт — угадай, куда прыгнуть";

  const outcome = lastKick ? outcomeLabelFor(lastKick) : null;

  const upcomingKicker = lastKick?.next_kicker ?? "player";
  const sceneKeeperSide = settled
    ? upcomingKicker === "bot" ? "own" : "opponent"
    : lastKick?.kicker === "bot" ? "own" : "opponent";
  const sceneKick = settled || !lastKick ? null : goalKickFrom(lastKick);
  const sceneOutcome = settled ? null : outcome;

  return (
    <div className="flex flex-col items-center gap-5 py-6">
      <p className="text-sm text-ink-mist">
        Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score ?? 0} : {lastKick?.bot_score ?? 0}</span>
      </p>

      <PenaltyGoalScene
        keeperSide={sceneKeeperSide}
        kick={sceneKick}
        outcomeLabel={sceneOutcome?.label ?? null}
        outcomeGood={sceneOutcome?.good ?? false}
      />

      {!lastKick?.is_finished && (
        <>
          <p className="text-sm font-semibold text-ink-mist">{roleLabel}</p>

          <div className="grid grid-cols-3 gap-2.5">
            {ZONES.map((z) => (
              <button
                key={z.value}
                onClick={() => { setPickedZone(z.value); kickMutation.mutate(z.value); }}
                disabled={kickMutation.isPending}
                className={`flex flex-col items-center gap-1 rounded-2xl px-3 py-3.5 text-[11px] font-semibold text-ink-chalk transition-colors active:scale-90 disabled:opacity-40 ${
                  pickedZone === z.value ? "bg-accent-cyan/20 ring-2 ring-accent-cyan" : "bg-bg-surface"
                }`}
              >
                <span className="text-base leading-none">{z.arrow}</span>
                {z.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck` — this file itself should now be clean. The
pre-existing errors from Task 5 in `ClubMissingItemPage.tsx` and `AdminGamesPage.tsx`
are still expected at this point (Tasks 7-8 fix them).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClubPenaltyPage.tsx
git commit -m "feat(club-penalty): add ClubPenaltyPage, reusing PenaltyGoalScene and ClubCardPickerModal"
```

---

### Task 7: Frontend — wire in the new page, remove the old one

**Files:**
- Modify: `frontend/src/pages/ClubGamesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/pages/ClubMissingItemPage.tsx`

**Interfaces:**
- Consumes: `ClubPenaltyPage` (Task 6, default export).
- Produces: `/clubs/penalty` route. Nothing downstream in this plan consumes this route
  by name (it's a leaf), but Task 9's live verification navigates to it directly.

- [ ] **Step 1: Update the club games menu**

In `frontend/src/pages/ClubGamesPage.tsx`, the `GAMES` array currently has:

```typescript
  {
    to: "/clubs/missing-item",
    icon: IconTarget,
    title: "Что исчезло?",
    description: "Запомни предметы и угадай, какой из них пропал",
  },
```

Replace it with:

```typescript
  {
    to: "/clubs/penalty",
    icon: IconGoal,
    title: "Пенальти",
    description: "Серия пенальти против бота — выбери игрока из состава клуба",
  },
```

Update the import line at the top of the file (currently `import { IconBrain,
IconChevronLeft, IconChevronRight, IconTarget } from "@/components/icons";`) to swap
`IconTarget` for `IconGoal` (the same icon personal Penalty already uses on
`PlayPage.tsx` — keeps the iconography consistent across both Penalty entry points):

```typescript
import { IconBrain, IconChevronLeft, IconChevronRight, IconGoal } from "@/components/icons";
```

- [ ] **Step 2: Update App.tsx**

Remove the import `import ClubMissingItemPage from "@/pages/ClubMissingItemPage";` and
add `import ClubPenaltyPage from "@/pages/ClubPenaltyPage";` in its place (keep the
surrounding import block's ordering — it's alphabetical by default-export name in this
file's existing `@/pages/Club*` import cluster).

Replace the route:

```tsx
        <Route path="/clubs/missing-item" element={<ClubMissingItemPage />} />
```

with:

```tsx
        <Route path="/clubs/penalty" element={<ClubPenaltyPage />} />
```

- [ ] **Step 3: Delete the old page**

```bash
git rm frontend/src/pages/ClubMissingItemPage.tsx
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npm run typecheck` — expect PASS now (this was the last frontend
file referencing the deleted `ClubMissingItem*` types/`IconTarget`-for-missing-item
usage from Task 5). Run `npm run lint` too — this repo has a known, pre-existing,
unrelated `eslint.config.js`-missing failure; confirm it's that exact same error, not a
new one.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ClubGamesPage.tsx frontend/src/App.tsx
git commit -m "feat(club-penalty): swap "Что исчезло?" for Пенальти in the club games menu and routes"
```

---

### Task 8: Admin panel — config UI

**Files:**
- Modify: `frontend/src/admin/pages/AdminGamesPage.tsx`

**Interfaces:**
- Consumes: `club_penalty_hourly_limit`, `club_penalty_daily_reward_limit`,
  `club_penalty_reward_win`, `club_penalty_reward_loss`, `club_penalty_bot_miss_chance`
  (Task 5's `admin/types.ts` `GameConfig`).

- [ ] **Step 1: Replace the "Что исчезло?" section**

In `frontend/src/admin/pages/AdminGamesPage.tsx`, the current section (around line 106)
reads:

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Что исчезло? (клубная игра)</p>
        <p className="mb-3 text-xs text-slate-500">Награда за игру идёт в бюджет клуба, а не игроку лично.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_missing_item_hourly_limit", "Лимит игр в час (на участника)")}
          {field("club_missing_item_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("club_missing_item_reward_cap", "Максимальная награда")}
        </div>
      </section>
```

Replace it with:

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Пенальти (клубная игра)</p>
        <p className="mb-3 text-xs text-slate-500">Награда за игру идёт в бюджет клуба, а не игроку лично.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_penalty_hourly_limit", "Лимит игр в час (на участника)")}
          {field("club_penalty_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("club_penalty_reward_win", "Награда за победу")}
          {field("club_penalty_reward_loss", "Награда за поражение")}
          {field("club_penalty_bot_miss_chance", "Шанс промаха бота (0-1)")}
        </div>
      </section>
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck` — expect PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/admin/pages/AdminGamesPage.tsx
git commit -m "feat(club-penalty): replace the admin config section for Что исчезло? with Пенальти"
```

---

### Task 9: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: all pass except the one pre-existing, already-flagged, unrelated failure
(`test_tasks.py::test_task_reward_pack_grants_all_cards`).

- [ ] **Step 2: Run the full frontend typecheck and lint**

Run: `cd frontend && npm run typecheck` — expect PASS.
Run: `cd frontend && npm run lint` — expect only the known, pre-existing
`eslint.config.js`-missing failure.

- [ ] **Step 3: Verify migration chain is sound**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest history`
— confirm `0099` then `0100` appear after `0098`, `0100` is head, no branching. Run `docker compose exec
backend alembic upgrade head` against the live dev Postgres to confirm it's actually at
head (Task 1 already verified this once — confirm it's still true after every later
task's own container rebuilds).

- [ ] **Step 4: Verify the full club-penalty flow live in the browser**

Rebuild and restart the stack (`docker compose up -d --build frontend backend` — this
repo's `docker-compose.override.yml`/build setup does not hot-reload the frontend, a
stale build is a common false negative). As a club member (create a club via dev-mode
if needed — `POST /clubs` auto-seeds a starting squad), navigate to `/clubs/games`,
confirm the menu now shows "Пенальти" (not "Что исчезло?"), tap into it, confirm the
club's own name appears in the description, start a game, pick a club card via the
picker (confirm it shows real club squad cards, not the player's personal collection),
play through a full shootout (own kicks + bot kicks alternating, `PenaltyGoalScene`
animating correctly for both), confirm it resolves to a win or loss, confirm the finish
screen shows "Бюджет клуба +N" and the club's new total budget, and confirm that number
actually matches the club's real budget afterward (check via `/clubs` page or admin
panel). Check the browser console for errors throughout. Separately, confirm
`/clubs/missing-item` no longer resolves to a working page (React Router will just fail
to match it — that's correct, not a bug to fix).

- [ ] **Step 5: Verify the admin config page**

As an admin, open `/admin/games`, confirm the "Пенальти (клубная игра)" section shows
with its five fields populated from real `GameConfig` defaults (45 / 8 / 0.12 / 1 / 5),
change one value, save, reload, confirm it persisted. Confirm there is no leftover "Что
исчезло?" section anywhere on the page.

- [ ] **Step 6: Report**

No commit for this task (verification only) — summarize the full pass/fail state of
Steps 1-5.

---
