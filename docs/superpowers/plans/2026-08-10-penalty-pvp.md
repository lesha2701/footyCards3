# Penalty PvP (Friend Challenges) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an async friend-challenge PvP mode to Penalty — challenge/accept, a 10-second-per-kick / 3-minute-per-match timed shootout with blind simultaneous picks, a `penalty_rating` leaderboard, and no coin reward (anti-collusion, mirrors Tactico's friend matches).

**Architecture:** A new `PenaltyMatch` model/table (not `GameSession` — that's single-player only) and a new `penalty_match_service.py`, both closely mirroring `tactico_service.py`'s challenge/accept/lazy-timeout-sweep architecture, adapted to one card instead of an 11-card squad and to much shorter, hardcoded timers. Frontend gets two new pages (`PenaltyMatchesPage`, `PenaltyMatchPage`) reusing the `PenaltyGoalScene` component built in the visuals plan.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic (backend), React + TypeScript + TanStack Query (frontend). No new dependencies.

## Global Constraints

- **Depends on** `docs/superpowers/plans/2026-08-10-penalty-visuals-6-zones.md` shipping first — this plan imports `PENALTY_ZONES`/`_resolve_shot` from `penalty_service.py` and reuses `PenaltyGoalScene`/`PenaltyGoalKick` from `frontend/src/components/penalty/PenaltyGoalScene.tsx`, both produced there.
- **No coins for PvP**, ever, regardless of outcome — only `penalty_rating` and W/D/L history. This is the whole point of the anti-collusion design (see spec's "Анти-абьюз" section) — never add a `credit_coins` call anywhere in this plan's PvP code path.
- 10 seconds per kick, 3 minutes per match — hardcoded Python constants, **not** `GameConfig` fields (spec's "Открытые допущения": these are game rules, not admin-tunable economy knobs).
- The challenger always kicks first (no randomization).
- Regulation is the same 10 kicks / 5 rounds as the bot mode; the 3-minute match timer can cut it short at any point, including mid-sudden-death, and a still-tied score at that point is a draw.
- Every `PenaltyMatch` row mutation that races with a concurrent request (accept, pick, timeout sweep) must go through `SELECT ... FOR UPDATE` (`_lock_match`, mirroring `tactico_service._lock_match`) — this is CLAUDE.md's mandatory row-locking rule, not optional here.
- Challenger must be live-transported into the match: `PenaltyMatchPage`'s query must poll while `status === "pending_accept" && viewer_side === "user"` (same fix already shipped for Tactico on 2026-08-10, see `frontend/src/pages/TacticoMatchPage.tsx`'s `refetchInterval`) — do not repeat that regression here.
- Reference spec: `docs/superpowers/specs/2026-08-10-penalty-visuals-and-pvp-design.md` (sections "PvP flow", "Рейтинг и лидерборд", "Фронтенд").

### Two deliberate deviations from the spec's illustrative pseudocode

The spec's "Архитектура" section sketches `PenaltyMatchResult` as a new enum. Implementation reuses the **existing** `MatchResult` enum (`win`/`draw`/`loss`, already shared by Card Arena and Tactico) instead — it's already the exact same shape, and adding a duplicate would just be redundant. `PenaltyMatchStatus` stays a **new**, Penalty-owned enum/Postgres type as the spec describes (even though its 6 values look identical to `TacticoMatchStatus`) — unlike a plain result, a lifecycle status is subsystem-specific and the two shouldn't be coupled through one shared DB type.

---

## File Structure

- Modify: `backend/app/models/enums.py` — add `PenaltyMatchStatus`; add 5 `penalty_challenge_*` values to `NotificationType`.
- Modify: `backend/app/models/game_config.py` — add `penalty_challenge_expiry_hours` column.
- Create: `backend/app/models/penalty.py` — `PenaltyMatch` model.
- Modify: `backend/app/models/__init__.py` — export `PenaltyMatch`.
- Create: `backend/alembic/versions/0040_penalty_pvp.py` — everything above, in one migration (mirrors `0017_tactico_mode.py`'s shape). **Renumbered from 0039 to 0040** — `users.penalty_rating` and its `0039_penalty_rating.py` migration already shipped as part of the visuals plan's Task 1 fix (an unplanned gap caught mid-execution there), so this migration no longer creates that column, only chains after it.
- Create: `backend/app/schemas/penalty_match.py` — `PenaltyMatchOut`, request schemas.
- Create: `backend/app/services/penalty_match_service.py` — the whole PvP lifecycle.
- Create: `backend/app/routers/penalty_matches.py`.
- Modify: `backend/app/main.py` — register the new router.
- Modify: `backend/app/schemas/ranking.py` — add `penalty_rating` to `RankingMetric`.
- Modify: `backend/app/services/ranking_service.py` — add `penalty_rating` to `_DIRECT_COLUMNS`.
- Create: `frontend/src/api/penalty.ts` — PvP API client functions (the existing solo functions stay in `frontend/src/api/games.ts`, untouched).
- Modify: `frontend/src/types/index.ts` — add `PenaltyMatch`, `PenaltyMatchStatus`, `PenaltyRound` types.
- Create: `frontend/src/pages/PenaltyMatchesPage.tsx`.
- Create: `frontend/src/pages/PenaltyMatchPage.tsx`.
- Modify: `frontend/src/pages/PenaltyGamePage.tsx` — add a "Играть с другом" entry point.
- Modify: `frontend/src/App.tsx` — register the two new routes.
- Modify: `backend/tests/test_penalty.py` or create `backend/tests/test_penalty_pvp.py` — full PvP lifecycle coverage.

---

### Task 1: Backend — enums, models, migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/game_config.py`
- Create: `backend/app/models/penalty.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0040_penalty_pvp.py`

**Interfaces:**
- Produces: `PenaltyMatchStatus` enum, `PenaltyMatch` model (fields: `id, user_id, opponent_user_id, opponent_name, user_card_id, opponent_card_id, status, result, rating_delta, server_state, expires_at, created_at, resolved_at`), `GameConfig.penalty_challenge_expiry_hours: int`. All consumed by Task 2+. `User.penalty_rating: int` already exists (added by the visuals plan) — nothing to produce here, just consume it in Task 4's rating-delta logic.

- [ ] **Step 1: Add the enum values**

In `backend/app/models/enums.py`, find the `NotificationType` class and add these 5 lines right after `tactico_challenge_expired = "tactico_challenge_expired"` (matching the naming style of the existing tactico challenge notifications):
```python
    penalty_challenge_received = "penalty_challenge_received"
    penalty_challenge_accepted = "penalty_challenge_accepted"
    penalty_challenge_declined = "penalty_challenge_declined"
    penalty_challenge_cancelled = "penalty_challenge_cancelled"
    penalty_challenge_expired = "penalty_challenge_expired"
```

Then add a new `PenaltyMatchStatus` enum, right after the `TacticoMatchStatus` class:
```python
class PenaltyMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"
```

- [ ] **Step 2: Add `GameConfig.penalty_challenge_expiry_hours`**

In `backend/app/models/game_config.py`, right after the existing `penalty_daily_limit` column, add:
```python
    penalty_challenge_expiry_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
```

- [ ] **Step 3: Create the `PenaltyMatch` model**

Create `backend/app/models/penalty.py`:
```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MatchResult, PenaltyMatchStatus
from app.models.mixins import utcnow


class PenaltyMatch(Base):
    """A single-card, timed friend-challenge penalty shootout. Deliberately
    not a GameSession — that model is single-player only (one user_id, no
    opponent). Mirrors TacticoMatch's shape, minus the squad/bot concepts
    Penalty doesn't have."""

    __tablename__ = "penalty_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True
    )
    opponent_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PenaltyMatchStatus] = mapped_column(
        Enum(PenaltyMatchStatus, name="penalty_match_status_enum"),
        default=PenaltyMatchStatus.pending_accept, nullable=False, index=True,
    )
    user_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, name="match_result_enum"), nullable=True)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Note: `result`/`rating_delta` are always from the **challenger's** (`user_id`'s) point of view, exactly like `TacticoMatch` — the service layer flips them for the opponent's view when hydrating (Task 3).

- [ ] **Step 4: Register the model**

In `backend/app/models/__init__.py`, add (alphabetically, after `notification`):
```python
from app.models.penalty import PenaltyMatch
```

- [ ] **Step 5: Write the migration**

Create `backend/alembic/versions/0040_penalty_pvp.py`:
```python
"""Penalty PvP: friend-challenge shootout mode

Adds the penalty_matches table, a penalty_challenge_expiry_hours GameConfig
tunable, and the new NotificationType values used by its challenge
lifecycle. Reuses the existing match_result_enum (win/draw/loss) rather
than adding a duplicate. Does NOT add users.penalty_rating — that column
already exists as of 0039_penalty_rating.py (added by the visuals plan's
Task 1 fix, before this migration was written).

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

penalty_match_status_enum = postgresql.ENUM(
    "pending_accept", "in_progress", "finished", "declined", "cancelled", "expired",
    name="penalty_match_status_enum", create_type=False,
)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)


def upgrade() -> None:
    penalty_match_status_enum.create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_received'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_accepted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_declined'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_cancelled'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_expired'")

    op.add_column(
        "game_config", sa.Column("penalty_challenge_expiry_hours", sa.Integer(), nullable=False, server_default="24")
    )

    op.create_table(
        "penalty_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", penalty_match_status_enum, nullable=False, server_default="pending_accept"),
        sa.Column("user_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", match_result_enum, nullable=True),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_state", postgresql.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_penalty_matches_user_id", "penalty_matches", ["user_id"])
    op.create_index("ix_penalty_matches_status", "penalty_matches", ["status"])
    op.create_index("ix_penalty_matches_created_at", "penalty_matches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_penalty_matches_created_at", table_name="penalty_matches")
    op.drop_index("ix_penalty_matches_status", table_name="penalty_matches")
    op.drop_index("ix_penalty_matches_user_id", table_name="penalty_matches")
    op.drop_table("penalty_matches")

    op.drop_column("game_config", "penalty_challenge_expiry_hours")

    penalty_match_status_enum.drop(op.get_bind(), checkfirst=True)
    # notification_type_enum ADD VALUEs above are not reversible (mirrors 0017/0036's note).
```

- [ ] **Step 6: Sanity-check imports and apply the migration**

Run: `docker compose exec -T backend python -c "from app.main import app"`
Expected: no output (clean import).

Run: `docker compose exec -T backend alembic upgrade head`
Expected: `Running upgrade 0039 -> 0040, Penalty PvP: friend-challenge shootout mode`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/game_config.py \
        backend/app/models/penalty.py backend/app/models/__init__.py \
        backend/alembic/versions/0040_penalty_pvp.py
git commit -m "Add PenaltyMatch model and PvP notification types"
```

---

### Task 2: Backend — schemas

**Files:**
- Create: `backend/app/schemas/penalty_match.py`

**Interfaces:**
- Consumes: `PenaltyMatchStatus` (Task 1), `PenaltyDirection`-equivalent zone strings (plain `str`, validated against `PENALTY_ZONES` in the service layer, same convention as the existing solo `PenaltyKickRequest.direction: str`).
- Produces:
  ```python
  class PenaltyRoundOut(BaseModel): kicker: Literal["user","opponent"]; shot_zone: str; dive_zone: str; outcome: Literal["goal","saved","miss"]
  class PenaltyMatchOut(BaseModel): id, opponent_name, opponent_user_id, status, viewer_side, user_score, opponent_score, rounds, kicker, is_viewer_turn, kick_deadline, match_deadline, result, rating_delta, created_at, expires_at, resolved_at
  class PenaltyChallengeRequest(BaseModel): opponent_user_id: int; user_card_id: int
  class PenaltyAcceptRequest(BaseModel): user_card_id: int
  class PenaltyPickRequest(BaseModel): zone: str
  ```
  Consumed by Task 3/4/5 (service + router).

- [ ] **Step 1: Write the schemas**

Create `backend/app/schemas/penalty_match.py`:
```python
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.enums import MatchResult, PenaltyMatchStatus


class PenaltyRoundOut(BaseModel):
    kicker: Literal["user", "opponent"]
    shot_zone: str
    dive_zone: str
    outcome: Literal["goal", "saved", "miss"]


class PenaltyMatchOut(BaseModel):
    id: int
    opponent_name: str
    opponent_user_id: Optional[int] = None
    status: PenaltyMatchStatus
    viewer_side: Literal["user", "opponent"]
    user_score: int
    opponent_score: int
    rounds: list[PenaltyRoundOut]
    kicker: Optional[Literal["user", "opponent"]] = None
    is_viewer_turn: bool = False
    kick_deadline: Optional[datetime] = None
    match_deadline: Optional[datetime] = None
    result: Optional[MatchResult] = None
    rating_delta: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class PenaltyChallengeRequest(BaseModel):
    opponent_user_id: int
    user_card_id: int


class PenaltyAcceptRequest(BaseModel):
    user_card_id: int


class PenaltyPickRequest(BaseModel):
    zone: str
```

- [ ] **Step 2: Sanity-check imports**

Run: `docker compose exec -T backend python -c "from app.schemas.penalty_match import PenaltyMatchOut"`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/penalty_match.py
git commit -m "Add Penalty PvP schemas"
```

---

### Task 3: Backend — challenge lifecycle (create/accept/decline/cancel)

**Files:**
- Create: `backend/app/services/penalty_match_service.py`
- Test: `backend/tests/test_penalty_pvp.py`

**Interfaces:**
- Consumes: `PENALTY_ZONES` (from `penalty_service.py`, produced by the visuals plan's Task 1), `PenaltyMatch`/`PenaltyMatchStatus` (Task 1), `PenaltyMatchOut`/`PenaltyChallengeRequest`/`PenaltyAcceptRequest` (Task 2), `notify()` (`app.services.notification_service`), `lock_user_for_update` (`app.services.wallet_service`).
- Produces (this task): `create_challenge(db, sender, receiver_id, user_card_id) -> PenaltyMatchOut`, `accept_challenge(db, user, match_id, user_card_id) -> PenaltyMatchOut`, `decline_challenge(db, user, match_id) -> PenaltyMatchOut`, `cancel_challenge(db, user, match_id) -> PenaltyMatchOut`, plus the private helpers `_lock_match`, `_get_match_or_404`, `_load_owned_card`, `_hydrate_match` (partial — rounds/timers land in Task 4) — all consumed by Task 4/5.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_penalty_pvp.py`:
```python
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _grant_card(db_session, owner_id: int, rating: int = 80) -> UserCard:
    player = await create_player(db_session, rarity=Rarity.rare, rating=rating)
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.flush()
    card.serial_number = card.id
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def test_penalty_challenge_create_and_accept(client, db_session, bot_token):
    sender = await _register(client, db_session, 860101, bot_token)
    receiver = await _register(client, db_session, 860102, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    receiver_card = await _grant_card(db_session, receiver.id)
    sender_headers = telegram_headers(860101, bot_token)
    receiver_headers = telegram_headers(860102, bot_token)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_accept"
    assert body["viewer_side"] == "user"
    match_id = body["id"]

    accept = await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=receiver_headers,
        json={"user_card_id": receiver_card.id},
    )
    assert accept.status_code == 200
    accepted_body = accept.json()
    assert accepted_body["status"] == "in_progress"
    assert accepted_body["viewer_side"] == "opponent"
    assert accepted_body["kicker"] == "opponent"  # the challenger ("user" from their own view) kicks first;
    # from the accepting side's view the challenger is "opponent"
    assert accepted_body["kick_deadline"] is not None
    assert accepted_body["match_deadline"] is not None


async def test_penalty_cannot_challenge_self(client, db_session, bot_token):
    user = await _register(client, db_session, 860103, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(860103, bot_token)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=headers,
        json={"opponent_user_id": user.id, "user_card_id": card.id},
    )
    assert resp.status_code == 409


async def test_penalty_decline_challenge(client, db_session, bot_token):
    sender = await _register(client, db_session, 860104, bot_token)
    receiver = await _register(client, db_session, 860105, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    sender_headers = telegram_headers(860104, bot_token)
    receiver_headers = telegram_headers(860105, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    decline = await client.post(f"/api/v1/games/penalty/challenges/{match_id}/decline", headers=receiver_headers)
    assert decline.status_code == 200
    assert decline.json()["status"] == "declined"


async def test_penalty_cancel_challenge(client, db_session, bot_token):
    sender = await _register(client, db_session, 860106, bot_token)
    receiver = await _register(client, db_session, 860107, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    sender_headers = telegram_headers(860106, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    cancel = await client.post(f"/api/v1/games/penalty/challenges/{match_id}/cancel", headers=sender_headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


async def test_penalty_only_challenged_user_can_accept(client, db_session, bot_token):
    sender = await _register(client, db_session, 860108, bot_token)
    receiver = await _register(client, db_session, 860109, bot_token)
    stranger = await _register(client, db_session, 860110, bot_token)
    sender_card = await _grant_card(db_session, sender.id)
    stranger_card = await _grant_card(db_session, stranger.id)
    sender_headers = telegram_headers(860108, bot_token)
    stranger_headers = telegram_headers(860110, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]

    resp = await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=stranger_headers,
        json={"user_card_id": stranger_card.id},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec -T backend pytest tests/test_penalty_pvp.py -v`
Expected: all FAIL — `/games/penalty/challenges` doesn't exist yet (404s), no router is wired up.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/penalty_match_service.py`:
```python
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import MatchResult, NotificationType, PenaltyMatchStatus
from app.models.penalty import PenaltyMatch
from app.models.user import User
from app.schemas.penalty_match import PenaltyMatchOut, PenaltyRoundOut
from app.services.game_config_service import get_config
from app.services.notification_service import notify

KICK_TIMEOUT_SECONDS = 10
MATCH_TIMEOUT_SECONDS = 180
REGULATION_KICKS = 10  # 5 rounds x 2 kicks, same as the bot mode

_FLIP_RESULT = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}
_OPPONENT_RATING_DELTA = {3: -1, -1: 3, 1: 1}


async def _get_match_or_404(db: AsyncSession, match_id: int) -> PenaltyMatch:
    match = await db.get(PenaltyMatch, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _lock_match(db: AsyncSession, match_id: int) -> PenaltyMatch:
    result = await db.execute(
        select(PenaltyMatch).where(PenaltyMatch.id == match_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _load_owned_card(db: AsyncSession, user: User, user_card_id: int) -> UserCard:
    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != user.id:
        raise ForbiddenError("You can only use your own cards")
    return card


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int, user_card_id: int) -> PenaltyMatchOut:
    config = await get_config(db)
    if receiver_id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")
    await _load_owned_card(db, sender, user_card_id)

    match = PenaltyMatch(
        user_id=sender.id,
        opponent_user_id=receiver.id,
        opponent_name=receiver.full_display_name(),
        user_card_id=user_card_id,
        status=PenaltyMatchStatus.pending_accept,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.penalty_challenge_expiry_hours),
        server_state={
            "kicks_taken": 0, "kicker": "user", "rounds": [],
            "user_score": 0, "opponent_score": 0,
            "user_pending_zone": None, "opponent_pending_zone": None,
            "kick_deadline": None, "match_deadline": None,
        },
    )
    db.add(match)
    await db.flush()

    await notify(
        db, receiver.id, NotificationType.penalty_challenge_received,
        "Вызов на пенальти", f"{sender.full_display_name()} вызвал(а) вас на серию пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, sender)


async def accept_challenge(db: AsyncSession, user: User, match_id: int, user_card_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can accept this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    if match.expires_at and ensure_aware(match.expires_at) <= datetime.now(timezone.utc):
        match.status = PenaltyMatchStatus.expired
        match.resolved_at = datetime.now(timezone.utc)
        db.add(match)
        await db.commit()
        raise ConflictError("This challenge has expired")

    await _load_owned_card(db, user, user_card_id)

    now = datetime.now(timezone.utc)
    state = dict(match.server_state)
    state["kick_deadline"] = (now + timedelta(seconds=KICK_TIMEOUT_SECONDS)).isoformat()
    state["match_deadline"] = (now + timedelta(seconds=MATCH_TIMEOUT_SECONDS)).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    match.opponent_card_id = user_card_id
    match.status = PenaltyMatchStatus.in_progress
    db.add(match)

    challenger = await db.get(User, match.user_id)
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_accepted,
        "Вызов принят", f"{user.full_display_name()} принял(а) ваш вызов на пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def decline_challenge(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can decline this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = PenaltyMatchStatus.declined
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_declined,
        "Вызов отклонён", f"{user.full_display_name()} отклонил(а) ваш вызов на пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def cancel_challenge(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.user_id != user.id:
        raise ForbiddenError("Only the challenger can cancel this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = PenaltyMatchStatus.cancelled
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def _hydrate_match(db: AsyncSession, match: PenaltyMatch, viewer: User) -> PenaltyMatchOut:
    state = match.server_state or {}
    side = "user" if viewer.id == match.user_id else "opponent"
    other_side = "opponent" if side == "user" else "user"

    if side == "user":
        opponent_name = match.opponent_name
        opponent_user_id = match.opponent_user_id
        viewer_score, other_score = match.user_score, match.opponent_score
        result_out = match.result
        rating_delta = match.rating_delta
    else:
        challenger = await db.get(User, match.user_id)
        opponent_name = challenger.full_display_name() if challenger else match.opponent_name
        opponent_user_id = match.user_id
        viewer_score, other_score = match.opponent_score, match.user_score
        result_out = _FLIP_RESULT[match.result] if match.result else None
        rating_delta = state.get("opponent_rating_delta", 0)

    rounds_out = [
        PenaltyRoundOut(
            kicker=(r["kicker"] if r["kicker"] == side else other_side) if side == "user" else
                   ("user" if r["kicker"] == "opponent" else "opponent"),
            shot_zone=r["shot_zone"], dive_zone=r["dive_zone"], outcome=r["outcome"],
        )
        for r in state.get("rounds", [])
    ]

    kicker = state.get("kicker")
    kicker_out = kicker if side == "user" else ({"user": "opponent", "opponent": "user"}.get(kicker) if kicker else None)
    is_viewer_turn = (
        match.status == PenaltyMatchStatus.in_progress and state.get(f"{side}_pending_zone") is None
    )

    return PenaltyMatchOut(
        id=match.id,
        opponent_name=opponent_name,
        opponent_user_id=opponent_user_id,
        status=match.status,
        viewer_side=side,
        user_score=viewer_score,
        opponent_score=other_score,
        rounds=rounds_out,
        kicker=kicker_out,
        is_viewer_turn=is_viewer_turn,
        kick_deadline=ensure_aware(datetime.fromisoformat(state["kick_deadline"])) if state.get("kick_deadline") else None,
        match_deadline=ensure_aware(datetime.fromisoformat(state["match_deadline"])) if state.get("match_deadline") else None,
        result=result_out,
        rating_delta=rating_delta,
        created_at=match.created_at,
        expires_at=match.expires_at,
        resolved_at=match.resolved_at,
    )
```

Note on locking: `accept_challenge`/`decline_challenge`/`cancel_challenge` use `_lock_match` (not the unlocked `_get_match_or_404`) — this is a deliberate divergence from `tactico_service.py`'s equivalent functions, which leave those three unlocked. Caught during this plan's pre-flight review: the Global Constraints above require `_lock_match` for every mutation that can race, including accept, per CLAUDE.md's mandatory row-locking rule; Tactico's own code predates that constraint being written down this explicitly and has a narrow (if rare) double-accept race as a result. Not fixing Tactico's version here — out of scope for this plan.

Note on `rounds_out`'s `kicker` relabeling: each stored round records `kicker` as literally `"user"` or `"opponent"` from the **challenger's** perspective (matching how `state["kicker"]` is tracked). When hydrating for the *opponent's* view, both the per-round `kicker` and the live `state["kicker"]` need flipping so "who kicked this round" reads correctly from whoever is looking at it — exactly the same relabeling `tactico_service._relabel_round` does for its rounds.

- [ ] **Step 4: Wire the router**

Create `backend/app/routers/penalty_matches.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.penalty_match import (
    PenaltyAcceptRequest,
    PenaltyChallengeRequest,
    PenaltyMatchOut,
    PenaltyPickRequest,
)
from app.services import penalty_match_service

router = APIRouter(prefix="/games/penalty", tags=["penalty"])


@router.post("/challenges", response_model=PenaltyMatchOut)
async def create_challenge(
    payload: PenaltyChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"penalty_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await penalty_match_service.create_challenge(db, user, payload.opponent_user_id, payload.user_card_id)


@router.post("/challenges/{match_id}/accept", response_model=PenaltyMatchOut)
async def accept_challenge(
    match_id: int, payload: PenaltyAcceptRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await penalty_match_service.accept_challenge(db, user, match_id, payload.user_card_id)


@router.post("/challenges/{match_id}/decline", response_model=PenaltyMatchOut)
async def decline_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.decline_challenge(db, user, match_id)


@router.post("/challenges/{match_id}/cancel", response_model=PenaltyMatchOut)
async def cancel_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.cancel_challenge(db, user, match_id)
```

(The `/matches/...` routes — `pick`, `list`, `get` — are added in Task 4/5, in this same file.)

In `backend/app/main.py`, add `penalty_matches` to the router import list (alphabetically, right after `penalty` if present — there isn't one, so right after `packs`) and register it:
```python
    penalty_matches,
```
and, right after `app.include_router(maintenance.router, prefix=API_PREFIX)` (or anywhere among the other routers — order doesn't matter, FastAPI dispatches by path):
```python
app.include_router(penalty_matches.router, prefix=API_PREFIX)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec -T backend pytest tests/test_penalty_pvp.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `docker compose exec -T backend pytest tests/ -q`
Expected: same pass count plus these 5 new ones; the pre-existing unrelated `test_task_reward_pack_grants_all_cards` failure is the only failure.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/penalty_match_service.py backend/app/routers/penalty_matches.py \
        backend/app/main.py backend/tests/test_penalty_pvp.py
git commit -m "Add Penalty PvP challenge lifecycle (create/accept/decline/cancel)"
```

---

### Task 4: Backend — picks, timeouts, and match finish

**Files:**
- Modify: `backend/app/services/penalty_match_service.py`
- Modify: `backend/app/routers/penalty_matches.py`
- Modify: `backend/tests/test_penalty_pvp.py`

**Interfaces:**
- Consumes: `_resolve_shot`/`PENALTY_ZONES` (from `penalty_service.py`), `_lock_match`/`_hydrate_match`/`_get_match_or_404` (Task 3), `lock_user_for_update` (`app.services.wallet_service`).
- Produces: `submit_pick(db, user, match_id, zone) -> PenaltyMatchOut`, `_auto_resolve_overdue(db) -> int`, `_finish_match(db, match, state)` — consumed by Task 5's `list_matches`/`get_match`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_penalty_pvp.py`:
```python
async def _create_and_accept(client, db_session, bot_token, sender_tid, receiver_tid):
    sender = await _register(client, db_session, sender_tid, bot_token)
    receiver = await _register(client, db_session, receiver_tid, bot_token)
    sender_card = await _grant_card(db_session, sender.id, rating=99)
    receiver_card = await _grant_card(db_session, receiver.id, rating=99)
    sender_headers = telegram_headers(sender_tid, bot_token)
    receiver_headers = telegram_headers(receiver_tid, bot_token)

    create = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    match_id = create.json()["id"]
    await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=receiver_headers,
        json={"user_card_id": receiver_card.id},
    )
    return match_id, sender, receiver, sender_headers, receiver_headers


async def test_penalty_pvp_full_match_resolves_with_score_and_rating(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860201, 860202
    )
    sender.penalty_rating = 5
    receiver.penalty_rating = 5
    db_session.add_all([sender, receiver])
    await db_session.commit()

    # Regulation is 10 kicks (5 as each side's kicker). Both shooters always
    # aim "top_left"; the defender's dive zone is chosen to mismatch (goal)
    # on the sender's kicks and match (saved) on the receiver's — this
    # guarantees the sender finishes strictly ahead without ever needing a
    # tied score, so the match ends at regulation without sudden death, and
    # exercises the win/+3/-1 rating-delta path (draw/+1 is covered by the
    # match-timeout test instead, which forces a tie via the match clock).
    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        dive_zone = "top_right" if i % 2 == 0 else "top_left"  # mismatch for sender's kicks, match for receiver's
        r1 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"}
        )
        assert r1.status_code == 200
        r2 = await client.post(
            f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": dive_zone}
        )
        assert r2.status_code == 200

    final = r2.json()
    assert final["status"] == "finished"
    assert final["result"] == "win"
    assert final["user_score"] > 0 and final["opponent_score"] == 0

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.penalty_rating == 8  # 5 + 3 (win)
    assert receiver.penalty_rating == 4  # 5 - 1 (loss)


async def test_penalty_pvp_gives_no_coins(client, db_session, bot_token):
    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860203, 860204
    )
    balance_before = sender.balance

    # Same mismatch-vs-match pattern as the full-match test above, so the
    # sender finishes ahead and the match ends at regulation.
    for i in range(10):
        kicker_headers = sender_headers if i % 2 == 0 else receiver_headers
        other_headers = receiver_headers if i % 2 == 0 else sender_headers
        dive_zone = "top_right" if i % 2 == 0 else "top_left"
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=kicker_headers, json={"zone": "top_left"})
        await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=other_headers, json={"zone": dive_zone})

    await db_session.refresh(sender)
    await db_session.refresh(receiver)
    assert sender.balance == balance_before
    assert receiver.balance == 500


async def test_penalty_pvp_kick_timeout_auto_resolves(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860205, 860206
    )

    # sender (kicker) picks; receiver never does — force the kick_deadline
    # into the past to simulate the 10s window elapsing.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    match = await db_session.get(PenaltyMatch, match_id)
    state = dict(match.server_state)
    state["kick_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=sender_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rounds"]) == 1  # the round resolved despite receiver never picking


async def test_penalty_pvp_match_timeout_ends_in_current_score(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.penalty import PenaltyMatch

    match_id, sender, receiver, sender_headers, receiver_headers = await _create_and_accept(
        client, db_session, bot_token, 860207, 860208
    )

    # One kick resolved in the sender's favor, then force match_deadline
    # into the past — the match must end right there, sender ahead 1:0.
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=sender_headers, json={"zone": "top_left"})
    await client.post(f"/api/v1/games/penalty/matches/{match_id}/pick", headers=receiver_headers, json={"zone": "bottom_right"})

    match = await db_session.get(PenaltyMatch, match_id)
    state = dict(match.server_state)
    state["match_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=sender_headers)
    body = resp.json()
    assert body["status"] == "finished"
    assert body["result"] == "win"
    assert body["user_score"] == 1 and body["opponent_score"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec -T backend pytest tests/test_penalty_pvp.py -v`
Expected: the 4 new tests FAIL — `/games/penalty/matches/{id}/pick` and `GET /games/penalty/matches/{id}` don't exist yet (404).

- [ ] **Step 3: Implement pick, sweep, and finish**

In `backend/app/services/penalty_match_service.py`, add these imports at the top (alongside the existing ones):
```python
import random

from app.services.penalty_service import PENALTY_ZONES, _resolve_shot
from app.services.wallet_service import lock_user_for_update
```

Then append these functions to the end of the file:
```python
def _current_kicker(state: dict) -> str:
    return state["kicker"]


async def submit_pick(db: AsyncSession, user: User, match_id: int, zone: str) -> PenaltyMatchOut:
    if zone not in PENALTY_ZONES:
        raise ConflictError("Invalid zone")
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != PenaltyMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")

    side = "user" if user.id == match.user_id else "opponent"
    state = dict(match.server_state)
    if state.get(f"{side}_pending_zone") is not None:
        raise ConflictError("You already picked for this kick")
    state[f"{side}_pending_zone"] = zone

    other_side = "opponent" if side == "user" else "user"
    if state.get(f"{other_side}_pending_zone") is not None:
        await _resolve_current_kick(db, match, state)
    else:
        state["kick_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=KICK_TIMEOUT_SECONDS)
        ).isoformat()

    match.server_state = state
    flag_modified(match, "server_state")
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def _resolve_current_kick(db: AsyncSession, match: PenaltyMatch, state: dict) -> None:
    """Both sides have a pending zone for the current kick — resolve it,
    record the round, advance to the next kicker, and finish the match if
    regulation is complete. Mutates `state` in place; caller still has to
    persist `match.server_state`/commit."""
    kicker = state["kicker"]
    defender = "opponent" if kicker == "user" else "user"
    shot_zone = state[f"{kicker}_pending_zone"]
    dive_zone = state[f"{defender}_pending_zone"]

    card_id = match.user_card_id if kicker == "user" else match.opponent_card_id
    card_result = await db.execute(select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player)))
    card = card_result.unique().scalar_one_or_none()
    miss_chance = 0.12 if card is None else _shooter_miss_chance(card.player.rating)

    outcome = _resolve_shot(miss_chance, shot_zone, dive_zone)
    if outcome == "goal":
        state[f"{kicker}_score"] += 1

    state["rounds"] = list(state["rounds"]) + [
        {"kicker": kicker, "shot_zone": shot_zone, "dive_zone": dive_zone, "outcome": outcome}
    ]
    state["kicks_taken"] += 1
    state["kicker"] = defender
    state["user_pending_zone"] = None
    state["opponent_pending_zone"] = None
    match.user_score, match.opponent_score = state["user_score"], state["opponent_score"]

    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0 and state["user_score"] != state["opponent_score"]:
        await _finish_match(db, match, state)
    else:
        state["kick_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=KICK_TIMEOUT_SECONDS)
        ).isoformat()


def _shooter_miss_chance(rating: int) -> float:
    from app.services.penalty_service import player_miss_chance
    return player_miss_chance(rating)


async def _finish_match(db: AsyncSession, match: PenaltyMatch, state: dict) -> None:
    if match.user_score > match.opponent_score:
        result, user_delta = MatchResult.win, 3
    elif match.user_score < match.opponent_score:
        result, user_delta = MatchResult.loss, -1
    else:
        result, user_delta = MatchResult.draw, 1
    opponent_delta = _OPPONENT_RATING_DELTA[user_delta]
    state["opponent_rating_delta"] = opponent_delta

    match.result = result
    match.rating_delta = user_delta
    match.status = PenaltyMatchStatus.finished
    match.resolved_at = datetime.now(timezone.utc)
    match.server_state = state
    flag_modified(match, "server_state")

    first_id, second_id = sorted([match.user_id, match.opponent_user_id])
    first_locked = await lock_user_for_update(db, first_id)
    second_locked = await lock_user_for_update(db, second_id)
    locked_user = first_locked if first_locked.id == match.user_id else second_locked
    locked_opponent = first_locked if first_locked.id == match.opponent_user_id else second_locked

    locked_user.penalty_rating = max(0, locked_user.penalty_rating + user_delta)
    locked_opponent.penalty_rating = max(0, locked_opponent.penalty_rating + opponent_delta)
    db.add(locked_user)
    db.add(locked_opponent)

    await notify(
        db, match.opponent_user_id, NotificationType.penalty_challenge_accepted,
        "Пенальти завершены",
        f"Серия с {locked_user.full_display_name()} завершена — результат: {_FLIP_RESULT[result].value}.",
        "penalty_match", match.id,
    )
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_accepted,
        "Пенальти завершены",
        f"Серия с {locked_opponent.full_display_name()} завершена — результат: {result.value}.",
        "penalty_match", match.id,
    )
    db.add(match)


async def _auto_resolve_overdue(db: AsyncSession) -> int:
    """Lazy sweep, mirroring tactico_service._auto_play_overdue_rounds: runs
    opportunistically on every list_matches/get_match call rather than a
    background scheduler (see CLAUDE.md's turn-based-game-state note)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(PenaltyMatch).where(PenaltyMatch.status == PenaltyMatchStatus.in_progress))
    matches = result.scalars().all()
    swept = 0
    for match in matches:
        state = dict(match.server_state or {})

        match_deadline = state.get("match_deadline")
        if match_deadline and ensure_aware(datetime.fromisoformat(match_deadline)) <= now:
            if state.get("user_pending_zone") is not None and state.get("opponent_pending_zone") is not None:
                await _resolve_current_kick(db, match, state)
            if match.status == PenaltyMatchStatus.in_progress:  # still in progress: end it on the current score
                await _finish_match(db, match, state)
            else:
                match.server_state = state
                flag_modified(match, "server_state")
                db.add(match)
            await db.commit()
            swept += 1
            continue

        kick_deadline = state.get("kick_deadline")
        if not kick_deadline or ensure_aware(datetime.fromisoformat(kick_deadline)) > now:
            continue

        for side in ("user", "opponent"):
            if state.get(f"{side}_pending_zone") is None:
                state[f"{side}_pending_zone"] = random.choice(PENALTY_ZONES)

        await _resolve_current_kick(db, match, state)
        match.server_state = state
        flag_modified(match, "server_state")
        db.add(match)
        await db.commit()
        swept += 1
    return swept
```

Add the new route to `backend/app/routers/penalty_matches.py`, right after `cancel_challenge`:
```python
@router.post("/matches/{match_id}/pick", response_model=PenaltyMatchOut)
async def submit_pick(
    match_id: int, payload: PenaltyPickRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await penalty_match_service.submit_pick(db, user, match_id, payload.zone)
```

Note: `list_matches`/`get_match` (which call `_auto_resolve_overdue` before reading, same as Tactico's `list_matches`/`get_match`) are added in Task 5 — until then, the timeout tests above reach the sweep logic through the `GET /games/penalty/matches/{id}` call, so this task's own test for it (`test_penalty_pvp_kick_timeout_auto_resolves`, `test_penalty_pvp_match_timeout_ends_in_current_score`) will only go green once Task 5's `get_match` (which calls `_auto_resolve_overdue`) exists. **Run Task 5 before checking this task's Step 4** — or, if executing task-by-task with review gates, treat Step 4 of this task as covering only `test_penalty_pvp_full_match_resolves_with_score_and_rating` and `test_penalty_pvp_gives_no_coins`, and defer the two timeout tests' green check to Task 5's Step 2.

- [ ] **Step 4: Run tests (full pass expected only after Task 5 — see note above)**

Run: `docker compose exec -T backend pytest tests/test_penalty_pvp.py -v`
Expected now: `test_penalty_pvp_full_match_resolves_with_score_and_rating` and `test_penalty_pvp_gives_no_coins` PASS; the two timeout tests still 404 on the `GET` call (expected, `get_match` lands in Task 5).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/penalty_match_service.py backend/app/routers/penalty_matches.py \
        backend/tests/test_penalty_pvp.py
git commit -m "Add Penalty PvP pick resolution, timeout sweep, and match finish"
```

---

### Task 5: Backend — list/get endpoints and ranking integration

**Files:**
- Modify: `backend/app/services/penalty_match_service.py`
- Modify: `backend/app/routers/penalty_matches.py`
- Modify: `backend/app/schemas/ranking.py`
- Modify: `backend/app/services/ranking_service.py`

**Interfaces:**
- Consumes: `_auto_resolve_overdue`/`_hydrate_match` (Task 4).
- Produces: `list_matches(db, user) -> list[PenaltyMatchOut]`, `get_match(db, user, match_id) -> PenaltyMatchOut`, `RankingMetric.penalty_rating`.

- [ ] **Step 1: Implement list/get**

Append to `backend/app/services/penalty_match_service.py`:
```python
from sqlalchemy import or_


async def list_matches(db: AsyncSession, user: User) -> list[PenaltyMatchOut]:
    await _auto_resolve_overdue(db)
    result = await db.execute(
        select(PenaltyMatch)
        .where(or_(PenaltyMatch.user_id == user.id, PenaltyMatch.opponent_user_id == user.id))
        .order_by(PenaltyMatch.created_at.desc())
    )
    matches = result.scalars().all()
    return [await _hydrate_match(db, m, user) for m in matches]


async def get_match(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    await _auto_resolve_overdue(db)
    match = await _get_match_or_404(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    await db.refresh(match)
    return await _hydrate_match(db, match, user)
```
(Move the `from sqlalchemy import or_` up into the file's top import block instead, next to the existing `from sqlalchemy import select` — this is written inline here only to show exactly which new import is needed.)

Add the two routes to `backend/app/routers/penalty_matches.py`, at the end of the file:
```python
@router.get("/matches", response_model=list[PenaltyMatchOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.list_matches(db, user)


@router.get("/matches/{match_id}", response_model=PenaltyMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.get_match(db, user, match_id)
```

- [ ] **Step 2: Run the full PvP test file**

Run: `docker compose exec -T backend pytest tests/test_penalty_pvp.py -v`
Expected: all 9 tests PASS, including the 2 timeout tests deferred from Task 4.

- [ ] **Step 3: Add the ranking metric**

In `backend/app/schemas/ranking.py`, add to `RankingMetric`:
```python
    penalty_rating = "penalty_rating"
```

In `backend/app/services/ranking_service.py`, find `_DIRECT_COLUMNS` and add:
```python
    RankingMetric.penalty_rating: User.penalty_rating,
```

- [ ] **Step 4: Verify the leaderboard endpoint**

Run: `docker compose exec -T backend pytest tests/ -q`
Expected: full suite passes (same pre-existing unrelated failure as always). Then manually:
```bash
docker compose exec -T backend python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services import ranking_service
from app.schemas.ranking import RankingMetric
from app.models.user import User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        out = await ranking_service.get_ranking(db, RankingMetric.penalty_rating, user)
        print(out.metric, len(out.top))

asyncio.run(main())
"
```
Expected: prints `RankingMetric.penalty_rating <N>` with no traceback.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/penalty_match_service.py backend/app/routers/penalty_matches.py \
        backend/app/schemas/ranking.py backend/app/services/ranking_service.py
git commit -m "Add Penalty PvP list/get endpoints and penalty_rating to the leaderboard"
```

---

### Task 6: Frontend — types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/penalty.ts`

**Interfaces:**
- Consumes: nothing new (mirrors the backend shapes from Task 2/5).
- Produces: `PenaltyMatch`, `PenaltyMatchStatus`, `PenaltyRound` types; `createPenaltyChallenge`, `acceptPenaltyChallenge`, `declinePenaltyChallenge`, `cancelPenaltyChallenge`, `submitPenaltyPick`, `fetchPenaltyMatches`, `fetchPenaltyMatch` functions — consumed by Task 7/8.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, right after the existing `PenaltyClaimResult` interface, add:
```ts
export type PenaltyMatchStatus = "pending_accept" | "in_progress" | "finished" | "declined" | "cancelled" | "expired";

export interface PenaltyRound {
  kicker: "user" | "opponent";
  shot_zone: PenaltyDirection;
  dive_zone: PenaltyDirection;
  outcome: "goal" | "saved" | "miss";
}

export interface PenaltyMatch {
  id: number;
  opponent_name: string;
  opponent_user_id: number | null;
  status: PenaltyMatchStatus;
  viewer_side: "user" | "opponent";
  user_score: number;
  opponent_score: number;
  rounds: PenaltyRound[];
  kicker: "user" | "opponent" | null;
  is_viewer_turn: boolean;
  kick_deadline: string | null;
  match_deadline: string | null;
  result: MatchResult | null;
  rating_delta: number;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}
```
(`MatchResult` is already defined earlier in this file as `"win" | "draw" | "loss"` — no new import needed, it's in the same module.)

- [ ] **Step 2: Write the API client**

Create `frontend/src/api/penalty.ts`:
```ts
import { api } from "@/lib/api";
import type { PenaltyDirection, PenaltyMatch } from "@/types";

export async function createPenaltyChallenge(opponentUserId: number, userCardId: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>("/games/penalty/challenges", {
    opponent_user_id: opponentUserId, user_card_id: userCardId,
  });
  return data;
}

export async function acceptPenaltyChallenge(id: number, userCardId: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/accept`, { user_card_id: userCardId });
  return data;
}

export async function declinePenaltyChallenge(id: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/decline`);
  return data;
}

export async function cancelPenaltyChallenge(id: number): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/challenges/${id}/cancel`);
  return data;
}

export async function submitPenaltyPick(id: number, zone: PenaltyDirection): Promise<PenaltyMatch> {
  const { data } = await api.post<PenaltyMatch>(`/games/penalty/matches/${id}/pick`, { zone });
  return data;
}

export async function fetchPenaltyMatches(): Promise<PenaltyMatch[]> {
  const { data } = await api.get<PenaltyMatch[]>("/games/penalty/matches");
  return data;
}

export async function fetchPenaltyMatch(id: number): Promise<PenaltyMatch> {
  const { data } = await api.get<PenaltyMatch>(`/games/penalty/matches/${id}`);
  return data;
}
```

- [ ] **Step 3: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/penalty.ts
git commit -m "Add Penalty PvP frontend types and API client"
```

---

### Task 7: Frontend — `PenaltyMatchesPage` (hub: challenge, list, tabs)

**Files:**
- Create: `frontend/src/pages/PenaltyMatchesPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchPenaltyMatches`, `createPenaltyChallenge` (Task 6), `searchUsers` (`@/api/profile`, already used by `TacticoMatchesPage`), `CardPickerModal` (`@/components/cards/CardPickerModal`), `fetchCollection` (`@/api/collection`).
- Produces: route `/play/penalty/matches`.

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/PenaltyMatchesPage.tsx` — this mirrors `TacticoMatchesPage.tsx`'s structure closely, swapping the squad/bot-difficulty flow for a single card picker:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createPenaltyChallenge, fetchPenaltyMatches } from "@/api/penalty";
import { searchUsers } from "@/api/profile";
import { fetchCollection } from "@/api/collection";
import CardPickerModal from "@/components/cards/CardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconFlagCheckered, IconUsers } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import type { PenaltyMatch, UserPublic } from "@/types";

type Tab = "pending" | "active" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending_accept: "Ожидает ответа",
  in_progress: "В процессе",
  finished: "Завершён",
  declined: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};

export default function PenaltyMatchesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [challengeSheetOpen, setChallengeSheetOpen] = useState(false);
  const [pickingOpponent, setPickingOpponent] = useState<UserPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: matches, isLoading } = useQuery({ queryKey: ["penalty-matches"], queryFn: fetchPenaltyMatches });
  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-pvp"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
    enabled: pickingOpponent !== null,
  });
  const activeMatch = matches?.find((m) => m.status === "in_progress");

  const challengeMutation = useMutation({
    mutationFn: (cardId: number) => createPenaltyChallenge(pickingOpponent!.id, cardId),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/penalty/matches/${match.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось отправить вызов")),
  });

  const filtered = (matches ?? []).filter((m) => {
    if (tab === "pending") return m.status === "pending_accept";
    if (tab === "active") return m.status === "in_progress";
    return ["finished", "declined", "cancelled", "expired"].includes(m.status);
  });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти с другом</h1>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {activeMatch && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">
          У тебя есть незавершённый матч — заверши его, чтобы начать новый.
        </p>
      )}

      {activeMatch ? (
        <button
          onClick={() => navigate(`/play/penalty/matches/${activeMatch.id}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base ring-2 ring-accent-green/40 active:scale-95"
        >
          Продолжить матч
        </button>
      ) : (
        <button
          onClick={() => setChallengeSheetOpen(true)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight py-4 text-sm font-bold text-bg-base ring-2 ring-accent-cyan/40 active:scale-95"
        >
          <IconUsers size={17} />
          Вызвать друга
        </button>
      )}

      <div className="flex gap-2">
        <TabButton active={tab === "pending"} label="Вызовы" onClick={() => setTab("pending")} />
        <TabButton active={tab === "active"} label="В процессе" onClick={() => setTab("active")} />
        <TabButton active={tab === "history"} label="История" onClick={() => setTab("history")} />
      </div>

      {isLoading && <ListSkeleton />}
      {!isLoading && !filtered.length && (
        <EmptyState icon={IconFlagCheckered} title="Матчей нет" description="Вызови друга на серию пенальти" />
      )}

      <div className="flex flex-col gap-2.5">
        {filtered.map((match) => (
          <MatchRow key={match.id} match={match} onClick={() => navigate(`/play/penalty/matches/${match.id}`)} />
        ))}
      </div>

      {challengeSheetOpen && !pickingOpponent && (
        <ChallengeSheet
          onClose={() => setChallengeSheetOpen(false)}
          onPick={(u) => setPickingOpponent(u)}
        />
      )}

      {pickingOpponent && (
        <CardPickerModal
          open
          title={`Выбери карточку против ${pickingOpponent.username ?? pickingOpponent.first_name ?? "соперника"}`}
          cards={collection?.items ?? []}
          onSelect={(card) => { setChallengeSheetOpen(false); challengeMutation.mutate(card.id); }}
          onClose={() => { setPickingOpponent(null); setChallengeSheetOpen(false); }}
        />
      )}
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl py-2 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}

function MatchRow({ match, onClick }: { match: PenaltyMatch; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]">
      <div>
        <p className="font-display text-sm font-bold text-ink-chalk">{match.opponent_name}</p>
        <p className="mt-0.5 text-[11px] text-ink-mist">{STATUS_LABELS[match.status]}</p>
      </div>
      {match.status !== "pending_accept" && (
        <span className="font-mono text-sm font-bold text-ink-chalk">
          {match.user_score}:{match.opponent_score}
        </span>
      )}
    </button>
  );
}

function ChallengeSheet({ onClose, onPick }: { onClose: () => void; onPick: (user: UserPublic) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search-penalty", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-3 font-display text-base font-bold text-ink-chalk">Вызвать друга</p>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Введи имя пользователя..."
          className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
        />
        <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
          {results?.map((u) => (
            <button
              key={u.id}
              onClick={() => onPick(u)}
              className="flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-ink-chalk active:scale-[0.98]"
            >
              <IconUsers size={14} className="text-ink-mist-dim" />
              {u.username ?? u.first_name ?? `#${u.id}`}
            </button>
          ))}
          {query.length >= 2 && !results?.length && <p className="text-xs text-ink-mist-dim">Никого не найдено</p>}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`, add the import:
```tsx
import PenaltyMatchesPage from "@/pages/PenaltyMatchesPage";
```
and the route, right after the existing `<Route path="/play/penalty" element={<PenaltyGamePage />} />`:
```tsx
        <Route path="/play/penalty/matches" element={<PenaltyMatchesPage />} />
```

- [ ] **Step 3: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PenaltyMatchesPage.tsx frontend/src/App.tsx
git commit -m "Add PenaltyMatchesPage: challenge a friend, list PvP matches"
```

---

### Task 8: Frontend — `PenaltyMatchPage` (live match: timers, picks, live transport)

**Files:**
- Create: `frontend/src/pages/PenaltyMatchPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchPenaltyMatch`, `acceptPenaltyChallenge`, `declinePenaltyChallenge`, `cancelPenaltyChallenge`, `submitPenaltyPick` (Task 6), `PenaltyGoalScene`/`PenaltyGoalKick` (visuals plan Task 4), `fetchCollection`/`CardPickerModal` (accept needs its own card).
- Produces: route `/play/penalty/matches/:matchId`.

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/PenaltyMatchPage.tsx`:
```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import {
  acceptPenaltyChallenge,
  cancelPenaltyChallenge,
  declinePenaltyChallenge,
  fetchPenaltyMatch,
  submitPenaltyPick,
} from "@/api/penalty";
import CardPickerModal from "@/components/cards/CardPickerModal";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import type { PenaltyDirection, PenaltyMatch, PenaltyRound } from "@/types";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

function goalKickFrom(round: PenaltyRound, viewerIsKicker: boolean): PenaltyGoalKick {
  return {
    shotZone: round.shot_zone,
    diveZone: round.dive_zone,
    outcome: viewerIsKicker ? round.outcome : (round.outcome === "goal" ? "goal" : round.outcome === "saved" ? "saved" : "miss"),
  };
}

function outcomeFor(round: PenaltyRound, viewerIsKicker: boolean): { label: string; good: boolean } {
  if (viewerIsKicker) {
    if (round.outcome === "goal") return { label: "Гол!", good: true };
    if (round.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (round.outcome === "saved") return { label: "Отбил!", good: true };
  if (round.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function PenaltyMatchPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [acceptingCard, setAcceptingCard] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const { data: match, isLoading } = useQuery({
    queryKey: ["penalty-match", id],
    queryFn: () => fetchPenaltyMatch(id),
    refetchInterval: (query) => {
      const data = query.state.data as PenaltyMatch | undefined;
      // Same fix as TacticoMatchPage (2026-08-10): poll while the challenger
      // is waiting so acceptance is picked up live, without a manual reload.
      if (data?.status === "pending_accept" && data.viewer_side === "user") return 5000;
      if (data?.status !== "in_progress") return false;
      return 2500; // kicks are on a 10s clock, poll faster than Tactico's 3s
    },
  });

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-pvp-accept"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
    enabled: acceptingCard,
  });

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["penalty-match", id] });
    queryClient.invalidateQueries({ queryKey: ["penalty-matches"] });
  };

  const acceptMutation = useMutation({
    mutationFn: (cardId: number) => acceptPenaltyChallenge(id, cardId),
    onSuccess: () => { hapticNotify("success"); setAcceptingCard(false); invalidate(); },
    onError: (err) => setError(formatGameError(err, "Не удалось принять вызов")),
  });
  const declineMutation = useMutation({ mutationFn: () => declinePenaltyChallenge(id), onSuccess: () => navigate("/play/penalty/matches") });
  const cancelMutation = useMutation({ mutationFn: () => cancelPenaltyChallenge(id), onSuccess: () => navigate("/play/penalty/matches") });
  const pickMutation = useMutation({
    mutationFn: (zone: PenaltyDirection) => submitPenaltyPick(id, zone),
    onSuccess: () => invalidate(),
    onError: (err) => setError(formatGameError(err, "Не удалось сделать удар")),
  });

  if (isLoading || !match) {
    return <p className="text-sm text-ink-mist">Загрузка...</p>;
  }

  if (match.status === "pending_accept") {
    return (
      <div className="rounded-2xl bg-bg-surface p-4 text-center">
        <p className="text-sm text-ink-mist">
          {match.viewer_side === "user"
            ? "Вызов отправлен, ждём ответа."
            : `${match.opponent_name} вызывает тебя на серию пенальти.`}
        </p>
        {error && <p className="mt-2 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
        <div className="mt-3 flex justify-center gap-2">
          {match.viewer_side === "opponent" && (
            <>
              <button onClick={() => setAcceptingCard(true)} className="rounded-xl bg-accent-green px-5 py-2 text-xs font-bold text-bg-base active:scale-95">
                Принять
              </button>
              <button onClick={() => declineMutation.mutate()} className="rounded-xl bg-red-500/80 px-5 py-2 text-xs font-bold text-white active:scale-95">
                Отклонить
              </button>
            </>
          )}
          {match.viewer_side === "user" && (
            <button onClick={() => cancelMutation.mutate()} className="rounded-xl bg-white/5 px-5 py-2 text-xs font-bold text-ink-mist active:scale-95">
              Отменить вызов
            </button>
          )}
        </div>
        {acceptingCard && (
          <CardPickerModal
            open
            title="Выбери карточку"
            cards={collection?.items ?? []}
            onSelect={(card) => acceptMutation.mutate(card.id)}
            onClose={() => setAcceptingCard(false)}
          />
        )}
      </div>
    );
  }

  if (["declined", "cancelled", "expired"].includes(match.status)) {
    return (
      <div className="rounded-2xl bg-bg-surface p-4 text-center text-sm text-ink-mist">
        {match.status === "declined" && "Вызов отклонён"}
        {match.status === "cancelled" && "Вызов отменён"}
        {match.status === "expired" && "Вызов истёк"}
      </div>
    );
  }

  const lastRound = match.rounds[match.rounds.length - 1];
  const viewerWasLastKicker = lastRound ? lastRound.kicker === "user" : false;
  const isViewerTurn = match.status === "in_progress" && match.is_viewer_turn;

  const kickSecondsLeft = match.kick_deadline
    ? Math.max(0, Math.ceil((new Date(match.kick_deadline).getTime() - now) / 1000))
    : null;
  const matchSecondsLeft = match.match_deadline
    ? Math.max(0, Math.ceil((new Date(match.match_deadline).getTime() - now) / 1000))
    : null;

  return (
    <div className="flex flex-col items-center gap-4 py-4">
      <div className="flex items-center gap-3">
        <p className="text-xs text-ink-mist">Против {match.opponent_name}</p>
        <span className="font-mono text-sm font-bold text-accent-cyan">{match.user_score} : {match.opponent_score}</span>
      </div>

      {match.status === "in_progress" && (
        <div className="flex gap-3 text-[11px] font-mono">
          <span className={kickSecondsLeft !== null && kickSecondsLeft <= 3 ? "text-red-400" : "text-ink-mist"}>
            Ход: {kickSecondsLeft ?? "—"}с
          </span>
          <span className={matchSecondsLeft !== null && matchSecondsLeft <= 20 ? "text-red-400" : "text-ink-mist"}>
            Матч: {matchSecondsLeft !== null ? `${Math.floor(matchSecondsLeft / 60)}:${String(matchSecondsLeft % 60).padStart(2, "0")}` : "—"}
          </span>
        </div>
      )}

      <PenaltyGoalScene
        keeperSide={lastRound && !viewerWasLastKicker ? "own" : "opponent"}
        kick={lastRound ? goalKickFrom(lastRound, viewerWasLastKicker) : null}
        outcomeLabel={lastRound ? outcomeFor(lastRound, viewerWasLastKicker).label : null}
        outcomeGood={lastRound ? outcomeFor(lastRound, viewerWasLastKicker).good : false}
      />

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {match.status === "in_progress" && (
        <>
          <p className="text-sm font-semibold text-ink-mist">
            {isViewerTurn
              ? (match.kicker === "user" ? "Твой удар — выбери зону" : "Ты в воротах — угадай зону")
              : "Ждём соперника..."}
          </p>
          <div className="grid grid-cols-3 gap-2.5">
            {ZONES.map((z) => (
              <button
                key={z.value}
                onClick={() => pickMutation.mutate(z.value)}
                disabled={!isViewerTurn || pickMutation.isPending}
                className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-3 py-3.5 text-[11px] font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
              >
                <span className="text-base leading-none">{z.arrow}</span>
                {z.label}
              </button>
            ))}
          </div>
        </>
      )}

      {match.status === "finished" && (
        <div className="flex flex-col items-center gap-3">
          <p className="font-display text-lg font-bold text-accent-lime">
            {match.result ? RESULT_LABELS[match.result] : ""}
          </p>
          <p className={`text-xs ${match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}`}>
            Рейтинг Пенальти {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
          </p>
          <button
            onClick={() => navigate("/play/penalty/matches")}
            className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist"
          >
            К списку матчей
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`, add the import:
```tsx
import PenaltyMatchPage from "@/pages/PenaltyMatchPage";
```
and the route, right after the `/play/penalty/matches` route added in Task 7:
```tsx
        <Route path="/play/penalty/matches/:matchId" element={<PenaltyMatchPage />} />
```

- [ ] **Step 3: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PenaltyMatchPage.tsx frontend/src/App.tsx
git commit -m "Add PenaltyMatchPage: live PvP shootout with kick/match timers"
```

---

### Task 9: Frontend — entry point from the solo game

**Files:**
- Modify: `frontend/src/pages/PenaltyGamePage.tsx`

**Interfaces:**
- Consumes: nothing new (just a `navigate()` call).

- [ ] **Step 1: Add the button**

In `frontend/src/pages/PenaltyGamePage.tsx`, the `pick_card` phase currently renders:
```tsx
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
```
Insert a secondary entry point right before the error line:
```tsx
        <button
          onClick={() => navigate("/play/penalty/matches")}
          className="self-start rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95"
        >
          Играть с другом →
        </button>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
```

- [ ] **Step 2: Typecheck and rebuild**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: clean.

```bash
docker compose up -d --build frontend
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PenaltyGamePage.tsx
git commit -m "Add a way to reach Penalty PvP from the solo game screen"
```

---

### Task 10: End-to-end verification

No new files — this task drives the already-committed backend + frontend through a real challenge/accept/play/finish cycle, the same way the Tactico polling fix and the Tactico squad-lock fix were verified earlier in this project (direct service-function calls for the second account, since there's no second real Telegram session available in dev).

- [ ] **Step 1: Seed a second account and two cards**

```bash
cat > /tmp/setup_penalty_pvp_verify.py <<'PY'
import asyncio, sys
sys.path.insert(0, "/app")
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.enums import CardSource, Position, Rarity
from app.models.player import Player
from app.models.card import UserCard
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        dev_user = (await db.execute(select(User).where(User.telegram_id == 999000001))).scalar_one()
        friend = (await db.execute(select(User).where(User.telegram_id == 777000333))).scalar_one_or_none()
        if friend is None:
            friend = User(telegram_id=777000333, username="penalty_pvp_friend", first_name="Friend", last_name="Three", balance=500)
            db.add(friend)
            await db.commit()
            await db.refresh(friend)
        p1 = Player(first_name="PVP", last_name="Dev", display_name="PVP Dev", rating=90, attack_rating=90, defense_rating=90, rarity=Rarity.rare, country="Test", club="Test FC", position=Position.ST, is_active=True)
        p2 = Player(first_name="PVP", last_name="Friend", display_name="PVP Friend", rating=90, attack_rating=90, defense_rating=90, rarity=Rarity.rare, country="Test", club="Test FC", position=Position.ST, is_active=True)
        db.add_all([p1, p2])
        await db.flush()
        c1 = UserCard(owner_id=dev_user.id, player_id=p1.id, source=CardSource.seed, serial_number=1)
        c2 = UserCard(owner_id=friend.id, player_id=p2.id, source=CardSource.seed, serial_number=1)
        db.add_all([c1, c2])
        await db.commit()
        await db.refresh(c1); await db.refresh(c2)
        print("dev_user_card", c1.id, "friend_id", friend.id, "friend_card", c2.id)

asyncio.run(main())
PY
docker compose cp /tmp/setup_penalty_pvp_verify.py backend:/tmp/setup_penalty_pvp_verify.py
docker compose exec -T backend python /tmp/setup_penalty_pvp_verify.py
```
Note the printed `dev_user_card`, `friend_id`, `friend_card` values for the next steps.

- [ ] **Step 2: Create the challenge as the dev user (browser-authenticated side)**

```bash
curl -s -X POST http://localhost:8000/api/v1/games/penalty/challenges \
  -H "X-Dev-Mode: true" -H "Content-Type: application/json" \
  -d '{"opponent_user_id": <friend_id>, "user_card_id": <dev_user_card>}' | python3 -m json.tool
```
Expected: `"status": "pending_accept"`, note the returned `"id"`.

- [ ] **Step 3: Open the challenger's page in a browser and confirm it live-transports on accept**

Write and run a Playwright script (same pattern as the Tactico polling-fix verification earlier in this project) that:
1. Opens `http://localhost:5173/play/penalty/matches/<id>` as the dev user (`X-Dev-Mode` cookie/header via normal navigation, no real Telegram needed).
2. Confirms the page shows "Вызов отправлен, ждём ответа."
3. Runs a second script inside the backend container that calls `penalty_match_service.accept_challenge(db, friend, <id>, <friend_card>)` directly (no second HTTP session available).
4. Without reloading the page, waits up to ~7s and confirms the SAME open page now shows the live match UI (score, zone grid) — proving the `pending_accept`-aware polling from Task 8 works, exactly like the Tactico fix.

- [ ] **Step 4: Play out a full match and confirm no coins, correct rating**

Using `curl` (as the dev user) and the direct-service-call script (as the friend), alternate `POST /games/penalty/matches/<id>/pick` calls with matching zones (both pick `"top_left"` each kick, guaranteeing 10 straight saves and a 0:0 draw, same as the automated test) until `status` is `"finished"`. Confirm via `GET /games/penalty/matches/<id>`:
- `result: "draw"`.
- Balance unchanged for both accounts (`GET /api/v1/profile/me` before/after).
- `penalty_rating` incremented by 1 for both (query `users` table or `GET /api/v1/leaderboard?metric=penalty_rating` if that endpoint exists — check `backend/app/routers/leaderboard.py` for its exact query-param shape before relying on it).

- [ ] **Step 5: Clean up the throwaway account**

Mirror the cleanup pattern used earlier in this project (delete the `PenaltyMatch` row(s), the friend's `UserCard`/`Player` rows, then the friend `User` row) via a script in `/tmp`, run through `docker compose exec`. Do **not** touch the dev user's own real cards.

- [ ] **Step 6: Final full-suite check**

```bash
docker compose exec -T backend pytest tests/ -q
docker compose exec -T frontend sh -c "npm run test -- --run"
docker compose exec -T frontend sh -c "npm run typecheck"
```
Expected: same pass counts as after Task 9, pre-existing unrelated failure only.

- [ ] **Step 7: No commit for this task** — it's verification only, nothing to check in beyond what Tasks 1–9 already committed.

---

## Self-Review Notes

- **Spec coverage:** Challenge/accept/decline/cancel (Task 3) ✅. Blind simultaneous pick + kick timeout (Task 4) ✅. Match timeout ending in current score, including draw (Task 4) ✅. No coins for PvP, ever (Task 4's `_finish_match` never calls `credit_coins`; verified explicitly by `test_penalty_pvp_gives_no_coins`) ✅. `penalty_rating` for both bot and PvP: the column itself already exists (added out-of-band during the visuals plan's Task 1, see its plan file and File Structure note above — this plan's Task 1 no longer creates it, only consumes it) — PvP-side deltas are done here (Task 1/4); the bot-mode side lives in the visuals plan's `resolve_kick` `is_finished` branch, covered by its `test_penalty_bot_match_win_increases_penalty_rating`/`test_penalty_bot_match_loss_decreases_penalty_rating_with_floor`/`test_penalty_rating_never_drops_below_zero` (the original single test of that name was replaced with these three after a task review found it flaky). Both plans agree on schema ownership and behavior; no outstanding gap.
- **Live transport into the match** (the extra requirement from this session) ✅ — Task 8's `refetchInterval`, verified in Task 10 Step 3 the same way the Tactico fix was verified.
- **Placeholder scan:** none found — every step has complete code; Task 10 uses a documented "write a Playwright script following the established pattern" instruction rather than inlining the script itself, which is acceptable for a verification-only task with a concrete prior example to follow (the Tactico polling-fix verification earlier in this session), not a build step.
- **Type consistency:** `PenaltyMatchOut`/`PenaltyMatch` field names match end-to-end (`kick_deadline`, `match_deadline`, `is_viewer_turn`, `kicker`) across Task 2 → Task 6 → Task 7/8. `PenaltyGoalKick.outcome` values (`"goal"|"saved"|"miss"`) match `_resolve_shot`'s return values and `PenaltyRoundOut.outcome` exactly.
