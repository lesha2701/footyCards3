# Player Tournaments — Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 16-player, 30-round tournaments for the main game (squad from the player's own cards, tactics, configurable match/place rewards, rating by place), simulated 3 times a day by the bot.

**Architecture:** A parallel subsystem (`player_tournament_*` tables/services, `personal_squads`) that reuses the club tournament match engine (`tournament_match_engine.simulate_match`, `club_tactical_matchup_service.build_side`), the club formation registry and the queue/slot-log patterns. Club tournament code and tables are not modified (except two additive enum values, one additive param on the bot's `_due_slots`).

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, pytest (in-memory SQLite), aiogram bot.

**Spec:** `docs/superpowers/specs/2026-09-25-league-tournaments-design.md` (see Naming rulings below — it says "league", this plan says "player tournament").

## Naming rulings (override the spec's names)

- The word "league" is already taken (rank tiers: `league_service`, `/leagues`, `models/league.py`). This subsystem is **"player tournament"**: tables `player_tournament*`, `personal_squads*`, services `player_tournament_*`, router `/player-tournaments`, config prefix `ptour_`, user column `tournament_rating`.
- `is_withdrawn` from the spec is **dropped** (the club one has no writer either — YAGNI).

## Scope

This plan is stage 1 of 3: **backend core only**. Frontend (player UI, profile/leaderboard display) and admin panel UI are separate plans. Admin *editing* of the new `GameConfig` fields is in the admin plan; here the fields only exist with defaults.

## Global Constraints

- Economy numbers (match rewards, place rewards, rating table) come from `GameConfig` (`game_config_service.get_config()`); never hardcode them in services.
- Coins only via `wallet_service.lock_user_for_update()` + `wallet_service.credit_coins()` (the caller commits).
- Async DB access only; `SELECT ... FOR UPDATE` with `.execution_options(populate_existing=True)` for race-sensitive rows.
- Simulation idempotency: `TournamentSimulationSlotLog` try-insert with `slot_key` format `"%Y-%m-%dT%H:%M"` (kinds `player_tournament_round`, `player_tournament_reminders`; both ≤ 32 chars) plus a per-tournament row lock.
- Alembic revisions are sequential: new head is `0119`, `down_revision = "0118"`.
- Raise `AppError` subclasses from `core/exceptions.py` (`ConflictError`, `ForbiddenError`, `NotFoundError`).
- Simulation slots: 10:00, 15:00, 21:00 in `app_timezone()` (bot: `settings.timezone`).
- Tournament: 16 players, 30 rounds (2 legs × 15), 8 matches per round.
- Rating per place default: `[5,4,3,2,1,0,0,0,0,0,0,-1,-2,-3,-4,-5]`, may go negative.
- Tests use in-memory SQLite (`Base.metadata.create_all`, not Alembic) → row locks are NOT exercised; Task 10 verifies on real Postgres.
- Do not read/print/edit `.env`. Do not run destructive Git/Docker/DB commands. **Do not commit** unless the user asks (project rule in CLAUDE.md) — there are deliberately no commit steps in this plan.
- Match engine actors: the engine reads `card.id`, `card.player_id`, `card.player.display_name`, `card.player.rating`, `card.player.position`; pass an adapter (Task 6) so `UserCard.diamond_rating_bonus` counts toward rating.

## File Structure

**Create**
- `backend/app/models/personal_squad.py` — `PersonalSquad`, `PersonalSquadCard`.
- `backend/app/models/player_tournament.py` — tournament, participant, standing, match, result, queue tables.
- `backend/alembic/versions/0119_player_tournaments.py`
- `backend/app/services/player_tournament_fixture_service.py` — constants + 16-player fixtures.
- `backend/app/services/player_tournament_standing_service.py` — points and ranking.
- `backend/app/services/personal_squad_service.py` — 5 templates, cards, tactics, coach, resolve for simulation.
- `backend/app/services/player_tournament_queue_service.py` — apply, current status.
- `backend/app/services/player_tournament_simulation_service.py` — round simulation, conclusion, rewards, rating.
- `backend/app/services/player_tournament_notification_service.py` — lineup reminders.
- `backend/app/services/player_tournament_query_service.py` — read models (detail, match, leaderboard, next-round countdown).
- `backend/app/schemas/personal_squad.py`, `backend/app/schemas/player_tournament.py`
- `backend/app/routers/player_tournaments.py`
- `bot/services/player_tournament_scheduler.py`
- Tests: `backend/tests/player_tournament_helpers.py`, `test_player_tournament_models.py`, `test_player_tournament_fixture_service.py`, `test_player_tournament_standing_service.py`, `test_personal_squad_service.py`, `test_player_tournament_queue_service.py`, `test_player_tournament_simulation.py`, `test_player_tournament_notifications.py`, `test_player_tournament_api.py`

**Modify**
- `backend/app/models/enums.py`, `backend/app/models/game_config.py`, `backend/app/models/user.py`, `backend/app/models/__init__.py`
- `backend/app/routers/internal.py`, `backend/app/main.py`
- `bot/services/tournament_scheduler.py` (`_due_slots` gets an optional `slots` argument), `bot/services/notifier.py`, `bot/bot.py`

---

### Task 1: Enums, config, user rating, models, migration 0119

**Files:**
- Modify: `backend/app/models/enums.py`, `backend/app/models/game_config.py`, `backend/app/models/user.py`, `backend/app/models/__init__.py`
- Create: `backend/app/models/personal_squad.py`, `backend/app/models/player_tournament.py`, `backend/alembic/versions/0119_player_tournaments.py`
- Test: `backend/tests/test_player_tournament_models.py`

**Interfaces:**
- Produces: classes named in File Structure; `TransactionType.player_tournament_match_reward`, `TransactionType.player_tournament_place_reward`; `NotificationType.player_tournament_match`, `.player_tournament_results_ready`, `.player_tournament_reminder`; `GameConfig.ptour_match_reward_win/draw/loss` (int), `ptour_place_rewards` / `ptour_rating_by_place` (JSON list of 16 ints); `User.tournament_rating` (int, default 0).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_player_tournament_models.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.personal_squad import PersonalSquad
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentQueue,
    PlayerTournamentQueueEntry, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.services.game_config_service import get_config
from tests.player_tournament_helpers import make_user


async def test_config_defaults(db_session):
    config = await get_config(db_session)
    assert (config.ptour_match_reward_win, config.ptour_match_reward_draw, config.ptour_match_reward_loss) == (100, 40, 15)
    assert len(config.ptour_place_rewards) == 16
    assert config.ptour_rating_by_place == [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]
    assert sum(config.ptour_rating_by_place) == 0


async def test_user_rating_defaults_to_zero(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840001)
    assert user.tournament_rating == 0


async def test_participant_unique_per_tournament(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840002)
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=user.id))
    await db_session.commit()
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_squad_template_unique_and_one_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840003)
    db_session.add(PersonalSquad(user_id=user.id, template_index=1, is_active=True))
    await db_session.commit()
    db_session.add(PersonalSquad(user_id=user.id, template_index=1, is_active=False))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    db_session.add(PersonalSquad(user_id=user.id, template_index=2, is_active=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_match_round_range_check(client, db_session, bot_token):
    a = await make_user(client, db_session, bot_token, 840004)
    b = await make_user(client, db_session, bot_token, 840005)
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    from datetime import datetime, timezone
    db_session.add(PlayerTournamentMatch(
        tournament_id=tournament.id, round_number=31, user_a_id=a.id, user_b_id=b.id,
        score_a=1, score_b=0, event_log=[], simulated_at=datetime.now(timezone.utc),
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

(SQLite enforces CHECK constraints created by `create_all`; if a CHECK is not enforced in this environment, drop the last test rather than weakening the constraint.)

Also create `backend/tests/player_tournament_helpers.py` (used by every later task):

```python
from app.models.card import UserCard
from app.models.enums import CardSource
from app.schemas.personal_squad import PersonalSquadSetRequest, PersonalSquadSlotIn
from app.services import personal_squad_service
from app.services.club_formation_service import get_formation_slots
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def make_user(client, db_session, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def give_cards_for_formation(db_session, user, formation="4-3-3", rating=70):
    """Creates one UserCard per slot of `formation`, returns [(slot, card)]."""
    pairs = []
    for slot in get_formation_slots(formation):
        player = await create_player(db_session, position=slot.ideal_position, rating=rating)
        card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed)
        db_session.add(card)
        pairs.append((slot, card))
    await db_session.commit()
    for _slot, card in pairs:
        await db_session.refresh(card)
    return pairs


async def make_ready_user(client, db_session, bot_token, telegram_id, rating=70):
    """User with a complete 11/11 active squad (4-3-3)."""
    user = await make_user(client, db_session, bot_token, telegram_id)
    pairs = await give_cards_for_formation(db_session, user, rating=rating)
    await personal_squad_service.set_squad_cards(
        db_session, user,
        PersonalSquadSetRequest(slots=[PersonalSquadSlotIn(slot_code=s.code, user_card_id=c.id) for s, c in pairs]),
    )
    return user
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_models.py -v`
Expected: FAIL (ImportError: `app.models.personal_squad`).

- [ ] **Step 3: Implement enums, config, user column**

`enums.py`: after `club_tournament_match_reward = "club_tournament_match_reward"` (inside `TransactionType`) add
```python
    player_tournament_match_reward = "player_tournament_match_reward"
    player_tournament_place_reward = "player_tournament_place_reward"
```
and after `club_lineup_reminder = "club_lineup_reminder"` (inside `NotificationType`) add
```python
    player_tournament_match = "player_tournament_match"
    player_tournament_results_ready = "player_tournament_results_ready"
    player_tournament_reminder = "player_tournament_reminder"
```

`game_config.py`: add `JSON` to the `sqlalchemy` import and append fields to `GameConfig`:
```python
    ptour_match_reward_win: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    ptour_match_reward_draw: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    ptour_match_reward_loss: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Index 0 = 1st place ... index 15 = 16th place.
    ptour_place_rewards: Mapped[list] = mapped_column(
        JSON, default=lambda: [3000, 2000, 1500, 1000, 750, 500, 400, 300, 250, 200, 150, 100, 75, 50, 25, 0], nullable=False,
    )
    ptour_rating_by_place: Mapped[list] = mapped_column(
        JSON, default=lambda: [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5], nullable=False,
    )
```

`user.py`: next to `hangman_hourly_attempts` add
```python
    tournament_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

- [ ] **Step 4: Implement models**

`backend/app/models/personal_squad.py`:
```python
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class PersonalSquad(TimestampMixin, Base):
    """One of 5 fixed saved squads per user used ONLY by player tournaments —
    separate from Card Arena `Lineup` and Тактико squads. Templates 2-5 are
    lazily created by personal_squad_service._ensure_templates."""

    __tablename__ = "personal_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Шаблон 1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3", server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), nullable=False, default="BALANCED", server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), nullable=False, default="CENTRAL_PLAY", server_default="CENTRAL_PLAY")
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True
    )

    cards: Mapped[list["PersonalSquadCard"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    user_coach_card: Mapped["UserCoachCard | None"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_personal_squad_user_template"),
        Index(
            "uq_personal_squad_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )


class PersonalSquadCard(Base):
    __tablename__ = "personal_squad_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("personal_squads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    squad: Mapped["PersonalSquad"] = relationship(back_populates="cards")
    user_card: Mapped["UserCard"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("squad_id", "user_card_id", name="uq_personal_squad_card_once"),
        UniqueConstraint("squad_id", "slot_code", name="uq_personal_squad_slot_once"),
    )
```
(`TimestampMixin` is the same one `Lineup` uses; if it adds `created_at/updated_at` the migration below must include them — see Step 5.)

`backend/app/models/player_tournament.py`:
```python
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentQueueStatus, TournamentStatus
from app.models.mixins import utcnow


class PlayerTournament(Base):
    __tablename__ = "player_tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(TournamentStatus, name="tournament_status_enum", create_type=False),
        default=TournamentStatus.active, nullable=False,
    )
    rounds_simulated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 30", name="ck_player_tournaments_rounds_range"),
    )


class PlayerTournamentParticipant(Base):
    __tablename__ = "player_tournament_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_participant_once"),)


class PlayerTournamentStanding(Base):
    __tablename__ = "player_tournament_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_standing_once"),)


class PlayerTournamentMatch(Base):
    __tablename__ = "player_tournament_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False)
    event_log: Mapped[list] = mapped_column(JSON, nullable=False)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("round_number >= 1 AND round_number <= 30", name="ck_player_tournament_matches_round_range"),
    )


class PlayerTournamentResult(Base):
    __tablename__ = "player_tournament_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_result_once"),)


class PlayerTournamentQueueState(Base):
    """Singleton row (id=1) pointing at the currently-forming queue."""

    __tablename__ = "player_tournament_queue_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_queue_id: Mapped[int] = mapped_column(ForeignKey("player_tournament_queues.id"), nullable=False)


class PlayerTournamentQueue(Base):
    __tablename__ = "player_tournament_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentQueueStatus] = mapped_column(
        Enum(TournamentQueueStatus, name="tournament_queue_status_enum", create_type=False),
        default=TournamentQueueStatus.open, nullable=False,
    )


class PlayerTournamentQueueEntry(Base):
    __tablename__ = "player_tournament_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("player_tournament_queues.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("queue_id", "user_id", name="uq_player_tournament_queue_entry_once"),)
```

`models/__init__.py`: add
```python
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentQueue,
    PlayerTournamentQueueEntry, PlayerTournamentQueueState, PlayerTournamentResult, PlayerTournamentStanding,
)
```
(follow the file's existing import style/ordering).

`schemas/personal_squad.py` must exist for the helpers import; create it in Task 4 — for now Task 1's helper import of `personal_squad_service` fails at import time only in tests that call `make_ready_user`. To keep Task 1 green, make the helper's imports of `PersonalSquadSetRequest`, `PersonalSquadSlotIn`, `personal_squad_service` **local to `make_ready_user`** (move them inside the function body).

- [ ] **Step 5: Write migration**

`backend/alembic/versions/0119_player_tournaments.py`:
```python
"""Player tournaments: 16 players, 30 rounds, personal squads (5 templates),
configurable rewards and a per-user tournament rating.

Revision ID: 0119
Revises: 0118
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0119"
down_revision: Union[str, None] = "0118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACE_REWARDS = "[3000, 2000, 1500, 1000, 750, 500, 400, 300, 250, 200, 150, 100, 75, 50, 25, 0]"
_RATING_BY_PLACE = "[5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]"


def _status_enum():
    return postgresql.ENUM("active", "completed", name="tournament_status_enum", create_type=False)


def _queue_status_enum():
    return postgresql.ENUM("open", "formed", name="tournament_queue_status_enum", create_type=False)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_match_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_place_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_match'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_results_ready'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_reminder'")

    op.add_column("users", sa.Column("tournament_rating", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("game_config", sa.Column("ptour_match_reward_win", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("game_config", sa.Column("ptour_match_reward_draw", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("ptour_match_reward_loss", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("ptour_place_rewards", sa.JSON(), nullable=False, server_default=sa.text(f"'{_PLACE_REWARDS}'::json")))
    op.add_column("game_config", sa.Column("ptour_rating_by_place", sa.JSON(), nullable=False, server_default=sa.text(f"'{_RATING_BY_PLACE}'::json")))

    op.create_table(
        "personal_squads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("formation", sa.String(16), nullable=False, server_default="4-3-3"),
        sa.Column("mentality", sa.String(16), nullable=False, server_default="BALANCED"),
        sa.Column("playstyle", sa.String(16), nullable=False, server_default="CENTRAL_PLAY"),
        sa.Column("user_coach_card_id", sa.Integer(), sa.ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "template_index", name="uq_personal_squad_user_template"),
    )
    op.create_index("ix_personal_squads_user_id", "personal_squads", ["user_id"])
    op.create_index(
        "uq_personal_squad_one_active_per_user", "personal_squads", ["user_id"], unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "personal_squad_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("personal_squads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_code", sa.String(16), nullable=False),
        sa.UniqueConstraint("squad_id", "user_card_id", name="uq_personal_squad_card_once"),
        sa.UniqueConstraint("squad_id", "slot_code", name="uq_personal_squad_slot_once"),
    )
    op.create_index("ix_personal_squad_cards_squad_id", "personal_squad_cards", ["squad_id"])
    op.create_index("ix_personal_squad_cards_user_card_id", "personal_squad_cards", ["user_card_id"])

    op.create_table(
        "player_tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", _status_enum(), nullable=False, server_default="active"),
        sa.Column("rounds_simulated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 30", name="ck_player_tournaments_rounds_range"),
    )
    op.create_table(
        "player_tournament_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_participant_once"),
    )
    op.create_index("ix_player_tournament_participants_tournament_id", "player_tournament_participants", ["tournament_id"])
    op.create_index("ix_player_tournament_participants_user_id", "player_tournament_participants", ["user_id"])
    op.create_table(
        "player_tournament_standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_for", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_against", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_standing_once"),
    )
    op.create_index("ix_player_tournament_standings_tournament_id", "player_tournament_standings", ["tournament_id"])
    op.create_index("ix_player_tournament_standings_user_id", "player_tournament_standings", ["user_id"])
    op.create_table(
        "player_tournament_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("user_a_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_b_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=False),
        sa.Column("score_b", sa.Integer(), nullable=False),
        sa.Column("event_log", sa.JSON(), nullable=False),
        sa.Column("simulated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("round_number >= 1 AND round_number <= 30", name="ck_player_tournament_matches_round_range"),
    )
    op.create_index("ix_player_tournament_matches_tournament_id", "player_tournament_matches", ["tournament_id"])
    op.create_index("ix_player_tournament_matches_user_a_id", "player_tournament_matches", ["user_a_id"])
    op.create_index("ix_player_tournament_matches_user_b_id", "player_tournament_matches", ["user_b_id"])
    op.create_table(
        "player_tournament_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("coins_awarded", sa.Integer(), nullable=False),
        sa.Column("rating_delta", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_result_once"),
    )
    op.create_index("ix_player_tournament_results_tournament_id", "player_tournament_results", ["tournament_id"])
    op.create_index("ix_player_tournament_results_user_id", "player_tournament_results", ["user_id"])

    op.create_table(
        "player_tournament_queues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", _queue_status_enum(), nullable=False, server_default="open"),
    )
    op.create_table(
        "player_tournament_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_queue_id", sa.Integer(), sa.ForeignKey("player_tournament_queues.id"), nullable=False),
    )
    op.create_table(
        "player_tournament_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_id", sa.Integer(), sa.ForeignKey("player_tournament_queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("queue_id", "user_id", name="uq_player_tournament_queue_entry_once"),
    )
    op.create_index("ix_player_tournament_queue_entries_queue_id", "player_tournament_queue_entries", ["queue_id"])
    op.create_index("ix_player_tournament_queue_entries_user_id", "player_tournament_queue_entries", ["user_id"])

    # Seed the singleton queue state (real Postgres only; tests lazily create it,
    # see player_tournament_queue_service._lock_queue_state).
    op.execute("INSERT INTO player_tournament_queues (status) VALUES ('open')")
    op.execute(
        "INSERT INTO player_tournament_queue_state (id, current_queue_id) "
        "SELECT 1, id FROM player_tournament_queues ORDER BY id LIMIT 1"
    )


def downgrade() -> None:
    op.drop_table("player_tournament_queue_entries")
    op.drop_table("player_tournament_queue_state")
    op.drop_table("player_tournament_queues")
    op.drop_table("player_tournament_results")
    op.drop_table("player_tournament_matches")
    op.drop_table("player_tournament_standings")
    op.drop_table("player_tournament_participants")
    op.drop_table("player_tournaments")
    op.drop_table("personal_squad_cards")
    op.drop_table("personal_squads")
    for column in ("ptour_rating_by_place", "ptour_place_rewards", "ptour_match_reward_loss", "ptour_match_reward_draw", "ptour_match_reward_win"):
        op.drop_column("game_config", column)
    op.drop_column("users", "tournament_rating")
    # Postgres cannot drop enum values; the added transaction/notification
    # enum members are left in place (same note as 0109).
```
Check `TimestampMixin` columns in `models/mixins.py`; if it defines different columns/nullability than `created_at`/`updated_at` above, make the `personal_squads` table match it exactly.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_player_tournament_models.py -v && python -c "from app.main import app"`
Expected: all PASS, no import error.

- [ ] **Step 7: Verify the migration chain**

Run: `cd backend && alembic heads`
Expected: single head `0119`.

---

### Task 2: 16-player fixtures and schedule constants

**Files:**
- Create: `backend/app/services/player_tournament_fixture_service.py`
- Test: `backend/tests/test_player_tournament_fixture_service.py`

**Interfaces:**
- Produces: `TOURNAMENT_SIZE = 16`, `TOTAL_ROUNDS = 30`, `SIMULATION_SLOTS = [(10, 0), (15, 0), (21, 0)]`, `generate_fixtures(user_ids: list[int]) -> list[tuple[int, int, int]]` returning `(round_number, user_a_id, user_b_id)`.

- [ ] **Step 1: Write the failing test**

```python
from collections import Counter

import pytest

from app.services.player_tournament_fixture_service import SIMULATION_SLOTS, TOTAL_ROUNDS, TOURNAMENT_SIZE, generate_fixtures


def test_constants():
    assert TOURNAMENT_SIZE == 16
    assert TOTAL_ROUNDS == 30
    assert SIMULATION_SLOTS == [(10, 0), (15, 0), (21, 0)]


def test_shape_and_pairings():
    ids = list(range(101, 117))
    fixtures = generate_fixtures(ids)
    assert len(fixtures) == 240
    assert {r for r, _, _ in fixtures} == set(range(1, 31))
    for r in range(1, 31):
        players = [p for rr, a, b in fixtures if rr == r for p in (a, b)]
        assert sorted(players) == ids
    pair_counts = Counter(frozenset((a, b)) for _, a, b in fixtures)
    assert len(pair_counts) == 120
    assert set(pair_counts.values()) == {2}


def test_no_back_to_back_same_opponent():
    ids = list(range(1, 17))
    fixtures = generate_fixtures(ids)
    previous: dict[int, int] = {}
    for r in range(1, 31):
        opponent: dict[int, int] = {}
        for rr, a, b in fixtures:
            if rr == r:
                opponent[a], opponent[b] = b, a
        for user_id in ids:
            assert opponent[user_id] != previous.get(user_id)
        previous = opponent


def test_requires_exactly_16():
    with pytest.raises(ValueError):
        generate_fixtures(list(range(15)))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_fixture_service.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

```python
TOURNAMENT_SIZE = 16
TOTAL_ROUNDS = 30
# Local app timezone; keep in sync with bot/services/player_tournament_scheduler.py.
# Deliberately not 20:00 — that is the club tournament slot.
SIMULATION_SLOTS: list[tuple[int, int]] = [(10, 0), (15, 0), (21, 0)]


def generate_fixtures(user_ids: list[int]) -> list[tuple[int, int, int]]:
    """Circle-method round-robin for exactly 16 players: fixes user_ids[0],
    rotates the other 15 through 15 rounds of 8 matches (leg 1, every pair
    meets once). Leg 2 (rounds 16-30) repeats the same pairings with home/away
    swapped. Each player faces a different opponent in each of the 15 leg-1
    rounds, so round 15's opponent never equals round 16's (= round 1's)."""
    if len(user_ids) != TOURNAMENT_SIZE:
        raise ValueError("generate_fixtures requires exactly 16 players")

    fixed = user_ids[0]
    rotating = list(user_ids[1:])

    leg_one: list[tuple[int, int, int]] = []
    for round_index in range(TOURNAMENT_SIZE - 1):
        circle = [fixed] + rotating
        pairs = [(circle[i], circle[len(circle) - 1 - i]) for i in range(TOURNAMENT_SIZE // 2)]
        leg_one.extend((round_index + 1, a, b) for a, b in pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    leg_two = [(round_number + 15, b, a) for round_number, a, b in leg_one]
    return leg_one + leg_two
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_fixture_service.py -v`
Expected: 4 PASS.

---

### Task 3: Standings and ranking

**Files:**
- Create: `backend/app/services/player_tournament_standing_service.py`
- Test: `backend/tests/test_player_tournament_standing_service.py`

**Interfaces:**
- Consumes: `PlayerTournamentStanding` (fields `user_id`, `points`, `goals_for`, `goals_against`), `PlayerTournamentMatch` (`user_a_id`, `user_b_id`, `score_a`, `score_b`).
- Produces: `apply_match_result(standing_a, standing_b, score_a, score_b) -> None`; `rank_standings(standings, matches) -> list[PlayerTournamentStanding]` (points desc, goal difference desc, goals for desc, then head-to-head points among still-tied players).

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace as NS

from app.services.player_tournament_standing_service import apply_match_result, rank_standings


def _standing(user_id, points=0, gf=0, ga=0):
    return NS(user_id=user_id, points=points, goals_for=gf, goals_against=ga)


def _match(a, b, sa, sb):
    return NS(user_a_id=a, user_b_id=b, score_a=sa, score_b=sb)


def test_apply_win_draw():
    a, b = _standing(1), _standing(2)
    apply_match_result(a, b, 2, 1)
    assert (a.points, a.goals_for, a.goals_against) == (3, 2, 1)
    assert (b.points, b.goals_for, b.goals_against) == (0, 1, 2)
    apply_match_result(a, b, 1, 1)
    assert (a.points, b.points) == (4, 1)


def test_rank_by_points_then_goal_difference():
    s = [_standing(1, 6, 5, 5), _standing(2, 6, 7, 3), _standing(3, 9, 1, 1)]
    assert [x.user_id for x in rank_standings(s, [])] == [3, 2, 1]


def test_rank_head_to_head_breaks_full_tie():
    s = [_standing(1, 3, 2, 1), _standing(2, 3, 2, 1)]
    matches = [_match(1, 2, 0, 1)]
    assert [x.user_id for x in rank_standings(s, matches)] == [2, 1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_standing_service.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

```python
from app.models.player_tournament import PlayerTournamentMatch, PlayerTournamentStanding


def apply_match_result(
    standing_a: PlayerTournamentStanding, standing_b: PlayerTournamentStanding, score_a: int, score_b: int
) -> None:
    standing_a.goals_for += score_a
    standing_a.goals_against += score_b
    standing_b.goals_for += score_b
    standing_b.goals_against += score_a
    if score_a > score_b:
        standing_a.points += 3
    elif score_b > score_a:
        standing_b.points += 3
    else:
        standing_a.points += 1
        standing_b.points += 1


def _head_to_head_points(user_ids: set[int], matches: list[PlayerTournamentMatch]) -> dict[int, int]:
    points = {user_id: 0 for user_id in user_ids}
    for m in matches:
        if m.user_a_id not in user_ids or m.user_b_id not in user_ids:
            continue
        if m.score_a > m.score_b:
            points[m.user_a_id] += 3
        elif m.score_b > m.score_a:
            points[m.user_b_id] += 3
        else:
            points[m.user_a_id] += 1
            points[m.user_b_id] += 1
    return points


def rank_standings(
    standings: list[PlayerTournamentStanding], matches: list[PlayerTournamentMatch]
) -> list[PlayerTournamentStanding]:
    """Same ordering rules as tournament_standing_service.rank_standings
    (clubs): points, goal difference, goals for, then head-to-head points
    computed only among players still tied. An unbreakable cycle keeps the
    stable input order."""
    groups: dict[tuple[int, int, int], list[PlayerTournamentStanding]] = {}
    for s in standings:
        groups.setdefault((s.points, s.goals_for - s.goals_against, s.goals_for), []).append(s)

    ranked: list[PlayerTournamentStanding] = []
    for key in sorted(groups.keys(), reverse=True):
        group = groups[key]
        if len(group) == 1:
            ranked.extend(group)
            continue
        h2h = _head_to_head_points({s.user_id for s in group}, matches)
        ranked.extend(sorted(group, key=lambda s: h2h[s.user_id], reverse=True))
    return ranked
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_standing_service.py -v`
Expected: 3 PASS.

---

### Task 4: Personal squads (schemas + service)

**Files:**
- Create: `backend/app/schemas/personal_squad.py`, `backend/app/services/personal_squad_service.py`
- Modify: `backend/tests/player_tournament_helpers.py` (nothing — its local imports now resolve)
- Test: `backend/tests/test_personal_squad_service.py`

**Interfaces:**
- Consumes: `PersonalSquad`, `PersonalSquadCard`, `CLUB_FORMATIONS`/`get_formation_slots` (`club_formation_service`), `MENTALITIES`/`PLAYSTYLES` (`club_tactical_matchup_service`), `CATEGORY_POSITIONS`/`FormationSlot` (`lineup_service`).
- Produces (schemas): `PersonalSquadSlotIn(slot_code: str, user_card_id: int)`, `PersonalSquadSetRequest(slots: list[PersonalSquadSlotIn])`, `PersonalSquadTacticsRequest(formation, mentality, playstyle)`, `PersonalSquadCoachRequest(user_coach_card_id: int | None)`, `PersonalSquadRenameRequest(name: str)`, `PersonalSquadSlotOut(slot_code, category, ideal_position, user_card_id: int | None, serial_number: int | None, player: PlayerOut | None)`, `PersonalSquadOut(template_index, name, is_active, is_complete, formation, mentality, playstyle, slots, coach: EquippedCoachOut | None)`.
- Produces (service, all `async`, `user: User`): `TEMPLATE_COUNT = 5`; `list_templates(db, user) -> list[PersonalSquadOut]`; `get_squad(db, user, template_index=None) -> PersonalSquadOut`; `set_squad_cards(db, user, payload, template_index=None) -> PersonalSquadOut`; `set_tactics(db, user, payload, template_index=None) -> PersonalSquadOut`; `set_coach(db, user, payload, template_index=None) -> PersonalSquadOut`; `rename_template(db, user, template_index, name) -> PersonalSquadOut`; `activate_template(db, user, template_index) -> PersonalSquadOut`; `list_user_coach_cards` is NOT duplicated — the existing `lineup_service.list_user_coach_cards` is reused by the router. Simulation-facing: `resolve_active_squad(db, user_id) -> tuple[PersonalSquad, list[tuple[UserCard, FormationSlot]]]` (only cards still owned by `user_id`); `is_squad_complete(db, user_id) -> bool`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_personal_squad_service.py`:
```python
import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError
from app.models.enums import Position
from app.models.personal_squad import PersonalSquad
from app.schemas.personal_squad import (
    PersonalSquadSetRequest, PersonalSquadSlotIn, PersonalSquadTacticsRequest,
)
from app.services import personal_squad_service as svc
from tests.factories import create_player
from tests.player_tournament_helpers import give_cards_for_formation, make_ready_user, make_user


def _payload(pairs):
    return PersonalSquadSetRequest(slots=[PersonalSquadSlotIn(slot_code=s.code, user_card_id=c.id) for s, c in pairs])


async def test_templates_are_seeded_once_with_first_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841001)
    templates = await svc.list_templates(db_session, user)
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    again = await svc.list_templates(db_session, user)
    assert len(again) == 5
    rows = (await db_session.execute(select(PersonalSquad).where(PersonalSquad.user_id == user.id))).scalars().all()
    assert len(rows) == 5


async def test_full_squad_is_complete(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 841002)
    assert await svc.is_squad_complete(db_session, user.id) is True
    squad = await svc.get_squad(db_session, user)
    assert squad.is_complete is True
    assert len(squad.slots) == 11


async def test_wrong_position_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841003)
    pairs = await give_cards_for_formation(db_session, user)
    striker = await create_player(db_session, position=Position.ST)
    from app.models.card import UserCard
    from app.models.enums import CardSource
    card = UserCard(owner_id=user.id, player_id=striker.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    gk_slot = pairs[0][0]
    with pytest.raises(ConflictError):
        await svc.set_squad_cards(db_session, user, PersonalSquadSetRequest(
            slots=[PersonalSquadSlotIn(slot_code=gk_slot.code, user_card_id=card.id)]))


async def test_foreign_card_rejected(client, db_session, bot_token):
    owner = await make_user(client, db_session, bot_token, 841004)
    thief = await make_user(client, db_session, bot_token, 841005)
    pairs = await give_cards_for_formation(db_session, owner)
    slot, card = pairs[0]
    with pytest.raises(ForbiddenError):
        await svc.set_squad_cards(db_session, thief, PersonalSquadSetRequest(
            slots=[PersonalSquadSlotIn(slot_code=slot.code, user_card_id=card.id)]))


async def test_duplicate_slot_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841006)
    pairs = await give_cards_for_formation(db_session, user)
    slot, card = pairs[1]
    other = pairs[2][1]
    with pytest.raises(ConflictError):
        await svc.set_squad_cards(db_session, user, PersonalSquadSetRequest(slots=[
            PersonalSquadSlotIn(slot_code=slot.code, user_card_id=card.id),
            PersonalSquadSlotIn(slot_code=slot.code, user_card_id=other.id),
        ]))


async def test_formation_change_clears_slots_missing_in_new_formation(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 841007)
    squad = await svc.set_tactics(db_session, user, PersonalSquadTacticsRequest(
        formation="4-4-2", mentality="ATTACKING", playstyle="WING_PLAY"))
    assert squad.formation == "4-4-2"
    assert (squad.mentality, squad.playstyle) == ("ATTACKING", "WING_PLAY")
    assert squad.is_complete is False  # FWD3 gone, MID4/... empty
    codes_with_cards = {s.slot_code for s in squad.slots if s.user_card_id}
    assert "FWD3" not in codes_with_cards


async def test_unknown_tactics_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841008)
    with pytest.raises(ConflictError):
        await svc.set_tactics(db_session, user, PersonalSquadTacticsRequest(
            formation="9-9-9", mentality="BALANCED", playstyle="WING_PLAY"))


async def test_activate_template_switches_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841009)
    await svc.list_templates(db_session, user)
    await svc.activate_template(db_session, user, 3)
    templates = await svc.list_templates(db_session, user)
    assert [t.template_index for t in templates if t.is_active] == [3]


async def test_card_no_longer_owned_is_excluded_from_resolve(client, db_session, bot_token):
    seller = await make_ready_user(client, db_session, bot_token, 841010)
    buyer = await make_user(client, db_session, bot_token, 841011)
    _squad, cards = await svc.resolve_active_squad(db_session, seller.id)
    assert len(cards) == 11
    moved = cards[0][0]
    moved.owner_id = buyer.id  # simulates a trade
    db_session.add(moved)
    await db_session.commit()
    _squad, cards = await svc.resolve_active_squad(db_session, seller.id)
    assert len(cards) == 10
    assert await svc.is_squad_complete(db_session, seller.id) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_personal_squad_service.py -v`
Expected: FAIL (ModuleNotFoundError: `app.schemas.personal_squad`).

- [ ] **Step 3: Implement schemas**

`backend/app/schemas/personal_squad.py`:
```python
from pydantic import BaseModel, Field

from app.schemas.lineup import EquippedCoachOut
from app.schemas.player import PlayerOut


class PersonalSquadSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class PersonalSquadSetRequest(BaseModel):
    slots: list[PersonalSquadSlotIn]


class PersonalSquadTacticsRequest(BaseModel):
    formation: str
    mentality: str
    playstyle: str


class PersonalSquadCoachRequest(BaseModel):
    user_coach_card_id: int | None = None


class PersonalSquadRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PersonalSquadSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    user_card_id: int | None = None
    serial_number: int | None = None
    player: PlayerOut | None = None


class PersonalSquadOut(BaseModel):
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    formation: str
    mentality: str
    playstyle: str
    slots: list[PersonalSquadSlotOut]
    coach: EquippedCoachOut | None = None
```
Before writing, open `app/schemas/lineup.py` and confirm `EquippedCoachOut` is defined there (lineup_service imports it from `app.schemas.lineup`) and `app/schemas/player.py` exports `PlayerOut`; adjust imports if either lives elsewhere.

- [ ] **Step 4: Implement service**

`backend/app/services/personal_squad_service.py`:
```python
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
from app.schemas.lineup import EquippedCoachOut
from app.schemas.personal_squad import (
    PersonalSquadCoachRequest, PersonalSquadOut, PersonalSquadSetRequest, PersonalSquadSlotOut,
    PersonalSquadTacticsRequest,
)
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot

TEMPLATE_COUNT = 5
DEFAULT_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, TEMPLATE_COUNT + 1)}


def _templates_query(user_id: int):
    # populate_existing=True for the same reason as lineup_service._templates_query:
    # expire_on_commit=False means a plain re-SELECT after a commit would return
    # stale cached objects.
    return (
        select(PersonalSquad)
        .where(PersonalSquad.user_id == user_id)
        .options(
            joinedload(PersonalSquad.cards).joinedload(PersonalSquadCard.user_card).joinedload(UserCard.player),
            joinedload(PersonalSquad.user_coach_card).joinedload(UserCoachCard.coach).selectinload(Coach.boosts),
        )
        .order_by(PersonalSquad.template_index)
        .execution_options(populate_existing=True)
    )


async def _ensure_templates(db: AsyncSession, user_id: int) -> list[PersonalSquad]:
    """Lazily seeds the 5 fixed template slots (same idea as
    lineup_service._ensure_templates). Template 1 starts active."""
    result = await db.execute(_templates_query(user_id))
    templates = list(result.unique().scalars().all())
    existing = {t.template_index for t in templates}
    missing = [i for i in range(1, TEMPLATE_COUNT + 1) if i not in existing]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        # SAVEPOINT so a lost race only undoes this insert batch instead of
        # expiring the caller's whole session.
        async with db.begin_nested():
            for i in missing:
                db.add(PersonalSquad(
                    user_id=user_id, template_index=i, name=DEFAULT_TEMPLATE_NAMES[i],
                    is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        pass

    result = await db.execute(_templates_query(user_id))
    return list(result.unique().scalars().all())


async def _get_row(db: AsyncSession, user_id: int, template_index: int | None) -> PersonalSquad:
    templates = await _ensure_templates(db, user_id)
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)


async def _lock_row(db: AsyncSession, user_id: int, template_index: int | None) -> PersonalSquad:
    squad = await _get_row(db, user_id, template_index)
    # of=PersonalSquad: user_coach_card is lazy="joined" (nullable outer join),
    # which Postgres refuses to FOR UPDATE (see lineup_service.set_lineup).
    await db.execute(select(PersonalSquad).where(PersonalSquad.id == squad.id).with_for_update(of=PersonalSquad))
    return squad


def _slots_by_code(formation: str) -> dict[str, FormationSlot]:
    return {s.code: s for s in get_formation_slots(formation)}


def _serialize(squad: PersonalSquad) -> PersonalSquadOut:
    by_slot = {c.slot_code: c.user_card for c in squad.cards}
    slots = []
    for slot in get_formation_slots(squad.formation):
        card = by_slot.get(slot.code)
        slots.append(PersonalSquadSlotOut(
            slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
            user_card_id=card.id if card else None,
            serial_number=card.serial_number if card else None,
            player=card.player if card else None,
        ))
    coach = None
    if squad.user_coach_card is not None:
        coach = EquippedCoachOut.model_validate(squad.user_coach_card.coach)
    return PersonalSquadOut(
        template_index=squad.template_index, name=squad.name, is_active=squad.is_active,
        is_complete=all(s.user_card_id is not None for s in slots),
        formation=squad.formation, mentality=squad.mentality, playstyle=squad.playstyle,
        slots=slots, coach=coach,
    )


async def _out(db: AsyncSession, user_id: int, template_index: int) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user_id, template_index))


async def list_templates(db: AsyncSession, user: User) -> list[PersonalSquadOut]:
    return [_serialize(t) for t in await _ensure_templates(db, user.id)]


async def get_squad(db: AsyncSession, user: User, template_index: int | None = None) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user.id, template_index))


async def set_squad_cards(
    db: AsyncSession, user: User, payload: PersonalSquadSetRequest, template_index: int | None = None
) -> PersonalSquadOut:
    squad = await _lock_row(db, user.id, template_index)
    slots_by_code = _slots_by_code(squad.formation)

    seen_slots: set[str] = set()
    seen_cards: set[int] = set()
    for slot_in in payload.slots:
        if slot_in.slot_code not in slots_by_code:
            raise ConflictError(f"Неизвестная позиция схемы: {slot_in.slot_code}")
        if slot_in.slot_code in seen_slots:
            raise ConflictError(f"Позиция указана дважды: {slot_in.slot_code}")
        if slot_in.user_card_id in seen_cards:
            raise ConflictError("Одна карта не может занимать две позиции")
        seen_slots.add(slot_in.slot_code)
        seen_cards.add(slot_in.user_card_id)

    cards = (
        await db.execute(select(UserCard).where(UserCard.id.in_(seen_cards)).options(joinedload(UserCard.player)))
    ).unique().scalars().all()
    cards_by_id = {c.id: c for c in cards}
    if len(cards_by_id) != len(seen_cards):
        raise NotFoundError("Одна или несколько карт не найдены")

    seen_players: set[int] = set()
    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        slot = slots_by_code[slot_in.slot_code]
        if card.owner_id != user.id:
            raise ForbiddenError("В составе можно использовать только свои карты")
        if card.is_locked_by_admin or card.is_locked_in_trade:
            raise ConflictError("Карта заблокирована и не может быть в составе")
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(
                f"{card.player.display_name} ({card.player.position.value}) не подходит на позицию {slot.category}"
            )
        if card.player_id in seen_players:
            raise ConflictError(f"{card.player.display_name} уже стоит на другой позиции")
        seen_players.add(card.player_id)

    for existing in list(squad.cards):
        await db.delete(existing)
    await db.flush()
    for slot_in in payload.slots:
        db.add(PersonalSquadCard(squad_id=squad.id, user_card_id=slot_in.user_card_id, slot_code=slot_in.slot_code))
    await db.commit()
    return await _out(db, user.id, squad.template_index)


async def set_tactics(
    db: AsyncSession, user: User, payload: PersonalSquadTacticsRequest, template_index: int | None = None
) -> PersonalSquadOut:
    if payload.formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Неизвестная схема: {payload.formation}")
    if payload.mentality not in MENTALITIES:
        raise ConflictError(f"Неизвестный настрой: {payload.mentality}")
    if payload.playstyle not in PLAYSTYLES:
        raise ConflictError(f"Неизвестный стиль игры: {payload.playstyle}")

    squad = await _lock_row(db, user.id, template_index)
    new_codes = set(_slots_by_code(payload.formation))
    for card in list(squad.cards):
        if card.slot_code not in new_codes:
            await db.delete(card)
    squad.formation = payload.formation
    squad.mentality = payload.mentality
    squad.playstyle = payload.playstyle
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, squad.template_index)


async def set_coach(
    db: AsyncSession, user: User, payload: PersonalSquadCoachRequest, template_index: int | None = None
) -> PersonalSquadOut:
    if payload.user_coach_card_id is not None:
        coach_card = await db.get(UserCoachCard, payload.user_coach_card_id)
        if coach_card is None or coach_card.user_id != user.id:
            raise ConflictError("Тренер не принадлежит тебе")
    squad = await _lock_row(db, user.id, template_index)
    squad.user_coach_card_id = payload.user_coach_card_id
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, squad.template_index)


async def rename_template(db: AsyncSession, user: User, template_index: int, name: str) -> PersonalSquadOut:
    squad = await _lock_row(db, user.id, template_index)
    squad.name = " ".join(name.split())[:64] or DEFAULT_TEMPLATE_NAMES[squad.template_index]
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, squad.template_index)


async def activate_template(db: AsyncSession, user: User, template_index: int) -> PersonalSquadOut:
    templates = await _ensure_templates(db, user.id)
    target = await _lock_row(db, user.id, template_index)
    if not target.is_active:
        for t in templates:
            if t.is_active:
                t.is_active = False
                db.add(t)
        # Flush the deactivation first: uq_personal_squad_one_active_per_user
        # would otherwise see two active rows mid-flush.
        await db.flush()
        target.is_active = True
        db.add(target)
    await db.commit()
    return await _out(db, user.id, template_index)


async def resolve_active_squad(
    db: AsyncSession, user_id: int
) -> tuple[PersonalSquad, list[tuple[UserCard, FormationSlot]]]:
    """Active squad + its (card, slot) pairs for match simulation. Cards the
    user no longer owns (traded away) are silently skipped; a card that was
    sold/deleted is already gone via ON DELETE CASCADE."""
    squad = await _get_row(db, user_id, None)
    slots = _slots_by_code(squad.formation)
    pairs = [
        (pc.user_card, slots[pc.slot_code])
        for pc in squad.cards
        if pc.slot_code in slots and pc.user_card.owner_id == user_id
    ]
    return squad, pairs


async def is_squad_complete(db: AsyncSession, user_id: int) -> bool:
    squad, pairs = await resolve_active_squad(db, user_id)
    return len(pairs) == len(get_formation_slots(squad.formation))
```
Copy the exact `Coach`/`UserCoachCard` import lines from `lineup_service.py` (`app.models.coach`, `app.models.user_coach_card`) — they are already correct above. `NotFoundError`'s status/format matches `lineup_service`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/test_personal_squad_service.py tests/test_player_tournament_models.py -v`
Expected: all PASS. If `test_formation_change_clears_slots_missing_in_new_formation` fails because 4-4-2 shares `MID3`/`FWD2` codes with different ideal positions, that is expected behavior (codes are kept, position rule is category-based) — assert only on the `FWD3` removal, as written.

---

### Task 5: Queue and tournament formation

**Files:**
- Create: `backend/app/schemas/player_tournament.py` (queue/status part), `backend/app/services/player_tournament_queue_service.py`
- Test: `backend/tests/test_player_tournament_queue_service.py`

**Interfaces:**
- Consumes: `personal_squad_service.is_squad_complete`, `generate_fixtures` not needed here, `TOURNAMENT_SIZE`.
- Produces (schemas): `PlayerTournamentApplyResult(queued: bool, tournament_id: int | None, queue_position: int | None, queue_size: int)`, `PlayerTournamentCurrentOut(status: str, queue_position: int | None, queue_size: int, tournament_id: int | None, can_apply: bool)` where `status` ∈ `"not_queued" | "queued" | "active" | "completed"`.
- Produces (service): `apply_to_tournament(db, user) -> PlayerTournamentApplyResult`; `get_current(db, user) -> PlayerTournamentCurrentOut`; `_lock_queue_state(db)`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentParticipant, PlayerTournamentQueue, PlayerTournamentStanding,
)
from app.services.player_tournament_queue_service import apply_to_tournament, get_current
from tests.player_tournament_helpers import make_ready_user, make_user


async def test_apply_queues_ready_user(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 850001)
    result = await apply_to_tournament(db_session, user)
    assert result.queued is True and result.tournament_id is None
    assert result.queue_position == 1 and result.queue_size == 16
    current = await get_current(db_session, user)
    assert current.status == "queued" and current.queue_position == 1 and current.can_apply is False


async def test_incomplete_squad_cannot_apply(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 850002)
    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, user)


async def test_double_apply_rejected(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 850003)
    await apply_to_tournament(db_session, user)
    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, user)


async def test_sixteenth_application_forms_tournament(client, db_session, bot_token):
    users = [await make_ready_user(client, db_session, bot_token, 850100 + i) for i in range(16)]
    for u in users[:15]:
        result = await apply_to_tournament(db_session, u)
        assert result.tournament_id is None
    result = await apply_to_tournament(db_session, users[15])
    assert result.tournament_id is not None

    tournament = await db_session.get(PlayerTournament, result.tournament_id)
    assert tournament.status.value == "active" and tournament.rounds_simulated == 0
    participants = (await db_session.execute(select(PlayerTournamentParticipant))).scalars().all()
    standings = (await db_session.execute(select(PlayerTournamentStanding))).scalars().all()
    assert len(participants) == 16 and len(standings) == 16

    formed = (await db_session.execute(select(PlayerTournamentQueue).where(PlayerTournamentQueue.status == "formed"))).scalars().all()
    assert len(formed) == 1
    current = await get_current(db_session, users[0])
    assert current.status == "active" and current.tournament_id == tournament.id

    with pytest.raises(ConflictError):  # already in an active tournament
        await apply_to_tournament(db_session, users[0])

    # A new queue is open for the next 16.
    next_result = await apply_to_tournament(db_session, await make_ready_user(client, db_session, bot_token, 850200))
    assert next_result.queued is True and next_result.queue_position == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_queue_service.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement schemas**

`backend/app/schemas/player_tournament.py`:
```python
from typing import Optional

from pydantic import BaseModel


class PlayerTournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None
    queue_size: int = 16


class PlayerTournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    queue_size: int = 16
    tournament_id: Optional[int] = None
    can_apply: bool = False
```
(More schemas are appended in Tasks 7–8.)

- [ ] **Step 4: Implement service**

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.enums import NotificationType, TournamentQueueStatus, TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentParticipant, PlayerTournamentQueue, PlayerTournamentQueueEntry,
    PlayerTournamentQueueState, PlayerTournamentStanding,
)
from app.models.user import User
from app.schemas.player_tournament import PlayerTournamentApplyResult, PlayerTournamentCurrentOut
from app.services import personal_squad_service
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOURNAMENT_SIZE


async def _lock_queue_state(db: AsyncSession) -> PlayerTournamentQueueState:
    """Locks the singleton queue-state row (id=1) so concurrent applications
    serialize — same idiom as tournament_queue_service._lock_queue_state.
    Lazily creates the singleton: migration 0119 seeds it on real Postgres,
    but tests build the schema with create_all."""
    result = await db.execute(
        select(PlayerTournamentQueueState).where(PlayerTournamentQueueState.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    state = result.scalar_one_or_none()
    if state is None:
        queue = PlayerTournamentQueue()
        db.add(queue)
        await db.flush()
        state = PlayerTournamentQueueState(id=1, current_queue_id=queue.id)
        db.add(state)
        await db.flush()
    return state


async def _active_tournament_id(db: AsyncSession, user_id: int) -> int | None:
    return (
        await db.execute(
            select(PlayerTournament.id)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user_id, PlayerTournament.status == TournamentStatus.active)
        )
    ).scalar_one_or_none()


async def _queue_position(db: AsyncSession, user_id: int, queue_id: int) -> int | None:
    entries = (
        await db.execute(
            select(PlayerTournamentQueueEntry.user_id)
            .where(PlayerTournamentQueueEntry.queue_id == queue_id)
            .order_by(PlayerTournamentQueueEntry.joined_at, PlayerTournamentQueueEntry.id)
        )
    ).scalars().all()
    return entries.index(user_id) + 1 if user_id in entries else None


async def apply_to_tournament(db: AsyncSession, user: User) -> PlayerTournamentApplyResult:
    if not await personal_squad_service.is_squad_complete(db, user.id):
        raise ConflictError("Заполни все позиции активного состава турнира, прежде чем подавать заявку")
    if await _active_tournament_id(db, user.id) is not None:
        raise ConflictError("Ты уже участвуешь в турнире")

    state = await _lock_queue_state(db)
    queue = await db.get(PlayerTournamentQueue, state.current_queue_id)
    already = (
        await db.execute(
            select(PlayerTournamentQueueEntry.id).where(
                PlayerTournamentQueueEntry.queue_id == queue.id, PlayerTournamentQueueEntry.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if already is not None:
        raise ConflictError("Ты уже в очереди на турнир")

    db.add(PlayerTournamentQueueEntry(queue_id=queue.id, user_id=user.id))
    await db.flush()

    entries = (
        await db.execute(
            select(PlayerTournamentQueueEntry)
            .where(PlayerTournamentQueueEntry.queue_id == queue.id)
            .order_by(PlayerTournamentQueueEntry.joined_at, PlayerTournamentQueueEntry.id)
        )
    ).scalars().all()

    if len(entries) < TOURNAMENT_SIZE:
        await db.commit()
        return PlayerTournamentApplyResult(queued=True, queue_position=len(entries), queue_size=TOURNAMENT_SIZE)

    tournament = PlayerTournament()
    db.add(tournament)
    await db.flush()
    for entry in entries:
        db.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=entry.user_id))
        db.add(PlayerTournamentStanding(tournament_id=tournament.id, user_id=entry.user_id))
        await notify(
            db, entry.user_id, NotificationType.player_tournament_match, "Турнир начался",
            "Набрался полный состав участников — первый тур скоро сыграют!",
            related_object_type="player_tournament", related_object_id=tournament.id,
        )

    queue.status = TournamentQueueStatus.formed
    db.add(queue)
    new_queue = PlayerTournamentQueue()
    db.add(new_queue)
    await db.flush()
    state.current_queue_id = new_queue.id
    db.add(state)

    await db.commit()
    return PlayerTournamentApplyResult(queued=True, tournament_id=tournament.id, queue_size=TOURNAMENT_SIZE)


async def get_current(db: AsyncSession, user: User) -> PlayerTournamentCurrentOut:
    active_id = await _active_tournament_id(db, user.id)
    if active_id is not None:
        return PlayerTournamentCurrentOut(status="active", tournament_id=active_id, queue_size=TOURNAMENT_SIZE)

    state = await _lock_queue_state(db)
    position = await _queue_position(db, user.id, state.current_queue_id)
    await db.commit()  # release the state-row lock taken above
    if position is not None:
        return PlayerTournamentCurrentOut(status="queued", queue_position=position, queue_size=TOURNAMENT_SIZE)

    last_completed = (
        await db.execute(
            select(PlayerTournament.id)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user.id, PlayerTournament.status == TournamentStatus.completed)
            .order_by(PlayerTournament.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    can_apply = await personal_squad_service.is_squad_complete(db, user.id)
    return PlayerTournamentCurrentOut(
        status="completed" if last_completed is not None else "not_queued",
        tournament_id=last_completed, queue_size=TOURNAMENT_SIZE, can_apply=can_apply,
    )
```
Remove the unused `func` import. In `get_current`, the `test_apply_queues_ready_user` assertion `can_apply is False` holds because the user is queued (returns before the `can_apply` line). `get_current` locking the queue state is only to lazily create the singleton; if a plain non-locking read is preferred, replace `_lock_queue_state` here with a `select(...)` that returns `None`→"not queued" — but keep the lazy creation inside `apply_to_tournament` only. Prefer the non-locking read: read `PlayerTournamentQueueState` with `db.get(PlayerTournamentQueueState, 1)`; if `None`, position is `None`. (Do this; drop the `db.commit()` line.)

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_queue_service.py -v`
Expected: 4 PASS. (This test creates 17 users × 11 cards; it takes several seconds.)

---

### Task 6: Round simulation, conclusion, rewards, rating

**Files:**
- Create: `backend/app/services/player_tournament_simulation_service.py`
- Test: `backend/tests/test_player_tournament_simulation.py`

**Interfaces:**
- Consumes: Tasks 1–5 (`generate_fixtures`, `rank_standings`, `apply_match_result`, `resolve_active_squad`), `tournament_match_engine.simulate_match(side_a, side_b, lineup_a, lineup_b, config, name_a, name_b) -> MatchResult(score_a, score_b, event_log, red_cards, injuries)`, `club_tactical_matchup_service.build_side(cards_with_slots, mentality, playstyle, coach=None)`, `wallet_service.lock_user_for_update(db, user_id)`, `wallet_service.credit_coins(db, user, amount, tx_type, description, related_object_type, related_object_id)`, `notification_service.notify`.
- Produces: `simulate_next_round(db, slot_key: str | None = None) -> list[PlayerTournamentMatch]`; `conclude_tournament(db, tournament, standings, matches, config) -> list[PlayerTournamentResult]`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_player_tournament_simulation.py`:
```python
from sqlalchemy import func, select

from app.models.enums import TransactionType, TournamentStatus
from app.models.personal_squad import PersonalSquadCard
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.player_tournament_queue_service import apply_to_tournament
from app.services.player_tournament_simulation_service import simulate_next_round
from tests.player_tournament_helpers import make_ready_user


async def _form_tournament(client, db_session, bot_token, base_id):
    users = [await make_ready_user(client, db_session, bot_token, base_id + i) for i in range(16)]
    for u in users:
        result = await apply_to_tournament(db_session, u)
    return users, result.tournament_id


async def test_round_simulates_eight_matches_and_pays_match_rewards(client, db_session, bot_token):
    users, tournament_id = await _form_tournament(client, db_session, bot_token, 860000)
    config = await get_config(db_session)
    matches = await simulate_next_round(db_session)
    assert len(matches) == 8

    tournament = await db_session.get(PlayerTournament, tournament_id)
    assert tournament.rounds_simulated == 1

    standings = (await db_session.execute(select(PlayerTournamentStanding))).scalars().all()
    assert sum(s.points for s in standings) >= 8 * 2  # every match yields 2 (draw) or 3 (win) points
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.player_tournament_match_reward)
    )).scalars().all()
    assert len(txs) == 16
    allowed = {config.ptour_match_reward_win, config.ptour_match_reward_draw, config.ptour_match_reward_loss}
    assert {t.amount for t in txs} <= allowed


async def test_same_slot_key_is_idempotent(client, db_session, bot_token):
    _users, tournament_id = await _form_tournament(client, db_session, bot_token, 861000)
    first = await simulate_next_round(db_session, slot_key="2026-09-25T10:00")
    second = await simulate_next_round(db_session, slot_key="2026-09-25T10:00")
    assert len(first) == 8 and second == []
    tournament = await db_session.get(PlayerTournament, tournament_id)
    assert tournament.rounds_simulated == 1


async def test_full_season_concludes_with_places_rewards_and_rating(client, db_session, bot_token):
    users, tournament_id = await _form_tournament(client, db_session, bot_token, 862000)
    config = await get_config(db_session)
    for _ in range(30):
        await simulate_next_round(db_session)

    tournament = await db_session.get(PlayerTournament, tournament_id)
    await db_session.refresh(tournament)
    assert tournament.status == TournamentStatus.completed and tournament.rounds_simulated == 30
    assert (await db_session.execute(select(func.count(PlayerTournamentMatch.id)))).scalar_one() == 240

    results = (await db_session.execute(
        select(PlayerTournamentResult).order_by(PlayerTournamentResult.final_rank)
    )).scalars().all()
    assert [r.final_rank for r in results] == list(range(1, 17))
    for r in results:
        assert r.rating_delta == config.ptour_rating_by_place[r.final_rank - 1]
        assert r.coins_awarded == config.ptour_place_rewards[r.final_rank - 1]
        user = await db_session.get(User, r.user_id)
        await db_session.refresh(user)
        assert user.tournament_rating == r.rating_delta
    assert sum(r.rating_delta for r in results) == 0

    place_txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.player_tournament_place_reward)
    )).scalars().all()
    assert len(place_txs) == sum(1 for r in results if r.coins_awarded > 0)

    # Finished tournaments are not simulated again.
    assert await simulate_next_round(db_session) == []


async def test_player_without_full_squad_forfeits(client, db_session, bot_token):
    users, _tournament_id = await _form_tournament(client, db_session, bot_token, 863000)
    victim = users[0]
    from app.models.personal_squad import PersonalSquad
    squad_ids = (await db_session.execute(select(PersonalSquad.id).where(PersonalSquad.user_id == victim.id))).scalars().all()
    rows = (await db_session.execute(select(PersonalSquadCard).where(PersonalSquadCard.squad_id.in_(squad_ids)))).scalars().all()
    for row in rows:
        await db_session.delete(row)
    await db_session.commit()

    await simulate_next_round(db_session)
    match = (await db_session.execute(
        select(PlayerTournamentMatch).where(
            (PlayerTournamentMatch.user_a_id == victim.id) | (PlayerTournamentMatch.user_b_id == victim.id)
        )
    )).scalar_one()
    victim_score, other_score = (match.score_a, match.score_b) if match.user_a_id == victim.id else (match.score_b, match.score_a)
    assert (victim_score, other_score) == (0, 3)
    assert match.event_log == []
```
- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_simulation.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

`backend/app/services/player_tournament_simulation_service.py`:
```python
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import UserCard
from app.models.enums import NotificationType, TransactionType, TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentResult,
    PlayerTournamentStanding,
)
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.user import User
from app.services import personal_squad_service, tournament_match_engine, wallet_service
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import FormationSlot
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOTAL_ROUNDS, generate_fixtures
from app.services.player_tournament_standing_service import apply_match_result, rank_standings

SLOT_KIND = "player_tournament_round"


@dataclass
class _EngineCard:
    """Adapter so the club-tuned engine sees a UserCard as (id, player_id,
    player.{display_name, rating, position}); rating includes the diamond
    upgrade bonus earned by that specific copy."""

    id: int
    player_id: int
    player: SimpleNamespace


def _engine_card(card: UserCard) -> _EngineCard:
    p = card.player
    return _EngineCard(
        id=card.id, player_id=card.player_id,
        player=SimpleNamespace(
            display_name=p.display_name, position=p.position, rating=min(99, p.rating + card.diamond_rating_bonus),
        ),
    )


@dataclass
class _Side:
    side: object  # ClubTacticalSide
    lineup: list[dict]


async def _build_side(db: AsyncSession, user_id: int) -> _Side | None:
    """None when the player cannot field a full starting XI (cards sold or
    traded away since applying)."""
    squad, pairs = await personal_squad_service.resolve_active_squad(db, user_id)
    if len(pairs) != len(get_formation_slots(squad.formation)):
        return None
    with_slots: list[tuple[_EngineCard, FormationSlot]] = [(_engine_card(c), slot) for c, slot in pairs]
    coach = squad.user_coach_card.coach if squad.user_coach_card else None
    side = build_side(with_slots, squad.mentality, squad.playstyle, coach=coach)
    lineup = [
        {
            "club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name,
            "rating": c.player.rating, "position": c.player.position.value, "category": slot.category,
        }
        for c, slot in with_slots
    ]
    return _Side(side=side, lineup=lineup)


async def _lock_tournament(db: AsyncSession, tournament_id: int) -> PlayerTournament:
    result = await db.execute(
        select(PlayerTournament).where(PlayerTournament.id == tournament_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _credit(db: AsyncSession, user_id: int, amount: int, tx_type: TransactionType, description: str, tournament_id: int) -> None:
    if amount <= 0:
        return
    user = await wallet_service.lock_user_for_update(db, user_id)
    await wallet_service.credit_coins(
        db, user, amount, tx_type, description,
        related_object_type="player_tournament", related_object_id=tournament_id,
    )


def _reward_for(config, own: int, opp: int) -> int:
    if own > opp:
        return config.ptour_match_reward_win
    if own < opp:
        return config.ptour_match_reward_loss
    return config.ptour_match_reward_draw


def _at(values: list, index: int) -> int:
    return int(values[index]) if 0 <= index < len(values) else 0


async def _play_match(
    db: AsyncSession, tournament_id: int, round_number: int, user_a_id: int, user_b_id: int,
    names: dict[int, str], config,
) -> tuple[int, int, list]:
    side_a = await _build_side(db, user_a_id)
    side_b = await _build_side(db, user_b_id)
    if side_a is not None and side_b is not None:
        result = tournament_match_engine.simulate_match(
            side_a.side, side_b.side, side_a.lineup, side_b.lineup, config, names[user_a_id], names[user_b_id],
        )
        return result.score_a, result.score_b, result.event_log
    if side_a is None and side_b is None:
        return 0, 0, []
    return (0, 3, []) if side_a is None else (3, 0, [])


async def simulate_next_round(db: AsyncSession, slot_key: str | None = None) -> list[PlayerTournamentMatch]:
    """Simulates the next round of every active player tournament, updates
    standings, pays per-match rewards, and on round 30 concludes the
    tournament (place rewards + rating). Idempotency: a duplicate slot_key is
    a no-op (try-insert into TournamentSimulationSlotLog); concurrent callers
    are serialized by the per-tournament row lock, and the loser re-reads
    rounds_simulated and skips — same design as
    tournament_simulation_service.simulate_next_round (clubs)."""
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind=SLOT_KIND, slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return []

    config = await get_config(db)
    candidates = (
        await db.execute(
            select(PlayerTournament.id, PlayerTournament.rounds_simulated)
            .where(PlayerTournament.status == TournamentStatus.active, PlayerTournament.rounds_simulated < TOTAL_ROUNDS)
        )
    ).all()

    all_matches: list[PlayerTournamentMatch] = []
    for tournament_id, observed_rounds in candidates:
        tournament = await _lock_tournament(db, tournament_id)
        round_number = observed_rounds + 1
        if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= round_number:
            continue

        participants = (
            await db.execute(
                select(PlayerTournamentParticipant)
                .where(PlayerTournamentParticipant.tournament_id == tournament.id)
                .order_by(PlayerTournamentParticipant.id)
            )
        ).scalars().all()
        user_ids = [p.user_id for p in participants]
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        names = {u.id: u.full_display_name() for u in users}
        standings = {
            s.user_id: s for s in (
                await db.execute(select(PlayerTournamentStanding).where(PlayerTournamentStanding.tournament_id == tournament.id))
            ).scalars().all()
        }

        round_matches: list[PlayerTournamentMatch] = []
        for _, user_a_id, user_b_id in (f for f in generate_fixtures(user_ids) if f[0] == round_number):
            score_a, score_b, event_log = await _play_match(
                db, tournament.id, round_number, user_a_id, user_b_id, names, config,
            )
            match = PlayerTournamentMatch(
                tournament_id=tournament.id, round_number=round_number, user_a_id=user_a_id, user_b_id=user_b_id,
                score_a=score_a, score_b=score_b, event_log=event_log, simulated_at=datetime.now(timezone.utc),
            )
            db.add(match)
            apply_match_result(standings[user_a_id], standings[user_b_id], score_a, score_b)

            description = f"Матч {round_number}-го тура турнира"
            for uid in sorted((user_a_id, user_b_id)):  # stable lock order
                own, opp = (score_a, score_b) if uid == user_a_id else (score_b, score_a)
                await _credit(
                    db, uid, _reward_for(config, own, opp), TransactionType.player_tournament_match_reward,
                    description, tournament.id,
                )
            # No score in the notification: the app reveals the match step by
            # step (TournamentMatchReplay); a push would spoil it.
            for uid in (user_a_id, user_b_id):
                await notify(
                    db, uid, NotificationType.player_tournament_match, "Матч сыгран",
                    f"Сыгран матч {round_number}-го тура турнира — смотри результат в приложении",
                    related_object_type="player_tournament", related_object_id=tournament.id,
                )
            round_matches.append(match)

        tournament.rounds_simulated = round_number
        db.add(tournament)

        if round_number == TOTAL_ROUNDS:
            season_matches = (
                await db.execute(select(PlayerTournamentMatch).where(PlayerTournamentMatch.tournament_id == tournament.id))
            ).scalars().all()
            await conclude_tournament(db, tournament, list(standings.values()), list(season_matches), config)

        await db.commit()
        all_matches.extend(round_matches)

    return all_matches


async def conclude_tournament(
    db: AsyncSession, tournament: PlayerTournament, standings: list[PlayerTournamentStanding],
    matches: list[PlayerTournamentMatch], config,
) -> list[PlayerTournamentResult]:
    ranked = rank_standings(standings, matches)
    results: list[PlayerTournamentResult] = []
    for index, standing in enumerate(ranked):
        rank = index + 1
        coins = _at(config.ptour_place_rewards, index)
        rating_delta = _at(config.ptour_rating_by_place, index)

        await _credit(
            db, standing.user_id, coins, TransactionType.player_tournament_place_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}", tournament.id,
        )
        user = await wallet_service.lock_user_for_update(db, standing.user_id)
        user.tournament_rating += rating_delta
        db.add(user)

        result = PlayerTournamentResult(
            tournament_id=tournament.id, user_id=standing.user_id, final_rank=rank,
            coins_awarded=coins, rating_delta=rating_delta,
        )
        db.add(result)
        results.append(result)

        await notify(
            db, standing.user_id, NotificationType.player_tournament_results_ready, "Турнир завершён",
            f"Ты занял {rank}-е место в турнире — загляни за результатами!",
            related_object_type="player_tournament", related_object_id=tournament.id,
        )

    tournament.status = TournamentStatus.completed
    db.add(tournament)
    return results
```
Notes for the implementer: (1) remove the unused `tournament_id`/`round_number` parameters from `_play_match` if unused after wiring; (2) if `simulate_match` reads any attribute of the adapter that `_EngineCard` lacks (e.g. `card.player.rarity`), the tests will raise `AttributeError` — add that attribute to the `SimpleNamespace` from the real `Player`, do not switch to the raw ORM object (it would drop the diamond bonus).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_simulation.py -v`
Expected: 4 PASS (the season test runs 240 real engine matches; allow up to a couple of minutes).

- [ ] **Step 5: Run the club suite for regressions**

Run: `cd backend && pytest tests/test_tournament_match_engine.py tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (no shared code was modified).

---

### Task 7: Lineup reminders and internal endpoints

**Files:**
- Create: `backend/app/services/player_tournament_notification_service.py`
- Modify: `backend/app/schemas/player_tournament.py` (add `PlayerTournamentReminderResult`), `backend/app/routers/internal.py`
- Test: `backend/tests/test_player_tournament_notifications.py`

**Interfaces:**
- Produces: `send_lineup_reminders(db, slot_key: str | None = None) -> int` (users notified); `PlayerTournamentReminderResult(users_notified: int)`; endpoints `POST /internal/player-tournaments/simulate-round?slot_key=` → `SimulateRoundResult`, `POST /internal/player-tournaments/lineup-reminders?slot_key=` → `PlayerTournamentReminderResult`.

- [ ] **Step 1: Write the failing test**

```python
from sqlalchemy import select

from app.models.notification import Notification
from app.models.enums import NotificationType
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.services.player_tournament_notification_service import send_lineup_reminders
from app.services.player_tournament_queue_service import apply_to_tournament
from tests.player_tournament_helpers import make_ready_user


async def _tournament(client, db_session, bot_token, base):
    users = [await make_ready_user(client, db_session, bot_token, base + i) for i in range(16)]
    for u in users:
        await apply_to_tournament(db_session, u)
    return users


async def test_reminds_only_players_with_incomplete_squad(client, db_session, bot_token):
    users = await _tournament(client, db_session, bot_token, 870000)
    squad_ids = (await db_session.execute(select(PersonalSquad.id).where(PersonalSquad.user_id == users[0].id))).scalars().all()
    for row in (await db_session.execute(select(PersonalSquadCard).where(PersonalSquadCard.squad_id.in_(squad_ids)))).scalars().all():
        await db_session.delete(row)
    await db_session.commit()

    count = await send_lineup_reminders(db_session, slot_key="2026-09-25T10:00")
    assert count == 1
    rows = (await db_session.execute(
        select(Notification).where(Notification.type == NotificationType.player_tournament_reminder)
    )).scalars().all()
    assert [n.user_id for n in rows] == [users[0].id]


async def test_reminder_slot_key_is_idempotent(client, db_session, bot_token):
    users = await _tournament(client, db_session, bot_token, 871000)
    squad_ids = (await db_session.execute(select(PersonalSquad.id).where(PersonalSquad.user_id == users[0].id))).scalars().all()
    for row in (await db_session.execute(select(PersonalSquadCard).where(PersonalSquadCard.squad_id.in_(squad_ids)))).scalars().all():
        await db_session.delete(row)
    await db_session.commit()
    assert await send_lineup_reminders(db_session, slot_key="2026-09-25T15:00") == 1
    assert await send_lineup_reminders(db_session, slot_key="2026-09-25T15:00") == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_notifications.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement service**

```python
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType, TournamentStatus
from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.services import personal_squad_service
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOTAL_ROUNDS

REMINDER_KIND = "player_tournament_reminders"


async def send_lineup_reminders(db: AsyncSession, slot_key: str | None = None) -> int:
    """Notifies every participant of an active tournament whose active squad
    can no longer field a full XI. Returns the number of users notified.
    Deduped by slot_key (see tournament_notification_service for the pattern)."""
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind=REMINDER_KIND, slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return 0

    user_ids = (
        await db.execute(
            select(PlayerTournamentParticipant.user_id)
            .join(PlayerTournament, PlayerTournament.id == PlayerTournamentParticipant.tournament_id)
            .where(PlayerTournament.status == TournamentStatus.active, PlayerTournament.rounds_simulated < TOTAL_ROUNDS)
        )
    ).scalars().all()

    notified = 0
    for user_id in user_ids:
        if await personal_squad_service.is_squad_complete(db, user_id):
            continue
        await notify(
            db, user_id, NotificationType.player_tournament_reminder, "Заполни состав",
            "В твоём составе турнира не хватает игроков — следующий тур скоро!",
        )
        notified += 1
    await db.commit()
    return notified
```

- [ ] **Step 4: Add schema and endpoints**

Append to `schemas/player_tournament.py`:
```python
class PlayerTournamentReminderResult(BaseModel):
    users_notified: int
```

`routers/internal.py`: extend the imports (`from app.schemas.player_tournament import PlayerTournamentReminderResult`, `from app.services import player_tournament_notification_service, player_tournament_simulation_service`) and append:
```python
@router.post("/player-tournaments/simulate-round", response_model=SimulateRoundResult)
async def simulate_player_tournament_round(slot_key: str | None = None, db: AsyncSession = Depends(get_db)):
    """Called by the bot's player-tournament scheduler at each daily slot.
    Duplicate slot_key = no-op (see player_tournament_simulation_service)."""
    matches = await player_tournament_simulation_service.simulate_next_round(db, slot_key=slot_key)
    return SimulateRoundResult(matches_simulated=len(matches))


@router.post("/player-tournaments/lineup-reminders", response_model=PlayerTournamentReminderResult)
async def player_tournament_lineup_reminders(slot_key: str | None = None, db: AsyncSession = Depends(get_db)):
    count = await player_tournament_notification_service.send_lineup_reminders(db, slot_key=slot_key)
    return PlayerTournamentReminderResult(users_notified=count)
```
Check how the existing `internal.py` endpoints are authenticated (router-level dependency on `X-Internal-Secret`) — the new endpoints inherit it automatically because they are added to the same `router`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_notifications.py -v`
Expected: 2 PASS. Then add one endpoint test to `test_player_tournament_api.py` in Task 8 (internal secret + response shape).

---

### Task 8: Player-facing API (router + query service)

**Files:**
- Create: `backend/app/services/player_tournament_query_service.py`, `backend/app/routers/player_tournaments.py`
- Modify: `backend/app/schemas/player_tournament.py`, `backend/app/main.py`
- Test: `backend/tests/test_player_tournament_api.py`

**Interfaces:**
- Consumes: everything above; `lineup_service.list_user_coach_cards(db, user)`; `core.dependencies.get_current_user`; `core.timeutil.app_timezone`.
- Produces schemas (append): `PlayerTournamentStandingOut(user_id, display_name, points, goals_for, goals_against, final_rank: int | None, coins_awarded: int | None, rating_delta: int | None)`, `PlayerTournamentMatchSummaryOut(id, round_number, user_a_id, user_b_id, score_a, score_b)`, `PlayerTournamentDetailOut(id, status, rounds_simulated, standings, matches, next_round_seconds_remaining: int | None)`, `PlayerTournamentMatchDetailOut(id, round_number, user_a_id, user_b_id, user_a_name, user_b_name, score_a, score_b, event_log)`, `TournamentRatingRowOut(user_id, display_name, tournament_rating)`.
- Produces service: `get_tournament_detail(db, tournament_id) -> PlayerTournamentDetailOut`, `get_match_detail(db, match_id) -> PlayerTournamentMatchDetailOut`, `get_rating_leaderboard(db, limit=50) -> list[TournamentRatingRowOut]`, `next_round_seconds_remaining(db, tournament) -> int | None`.
- Endpoints (prefix `/player-tournaments`, all `Depends(get_current_user)`): `GET /squads`, `GET /squads/coach-cards`, `PUT /squads/{template_index}/cards`, `PUT /squads/{template_index}/tactics`, `PUT /squads/{template_index}/coach`, `PUT /squads/{template_index}/name`, `POST /squads/{template_index}/activate`, `POST /apply`, `GET /current`, `GET /rating`, `GET /matches/{match_id}`, `GET /{tournament_id}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_player_tournament_api.py`:
```python
from app.services.player_tournament_queue_service import apply_to_tournament
from app.services.player_tournament_simulation_service import simulate_next_round
from tests.player_tournament_helpers import make_ready_user
from tests.utils import telegram_headers

BASE = "/api/v1/player-tournaments"


async def test_squads_list_and_tactics(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 880001)
    h = telegram_headers(880001, bot_token)
    resp = await client.get(f"{BASE}/squads", headers=h)
    assert resp.status_code == 200
    squads = resp.json()
    assert [s["template_index"] for s in squads] == [1, 2, 3, 4, 5]
    assert squads[0]["is_complete"] is True

    resp = await client.put(
        f"{BASE}/squads/1/tactics", headers=h,
        json={"formation": "4-4-2", "mentality": "DEFENSIVE", "playstyle": "POSSESSION"},
    )
    assert resp.status_code == 200 and resp.json()["formation"] == "4-4-2"

    resp = await client.post(f"{BASE}/squads/2/activate", headers=h)
    assert resp.status_code == 200 and resp.json()["is_active"] is True

    resp = await client.put(f"{BASE}/squads/2/name", headers=h, json={"name": "Атакующий"})
    assert resp.json()["name"] == "Атакующий"


async def test_apply_current_and_full_flow(client, db_session, bot_token):
    users = [await make_ready_user(client, db_session, bot_token, 880100 + i) for i in range(16)]
    for u in users[:15]:
        await apply_to_tournament(db_session, u)
    h = telegram_headers(880100 + 15, bot_token)
    resp = await client.post(f"{BASE}/apply", headers=h)
    assert resp.status_code == 200 and resp.json()["tournament_id"] is not None
    tournament_id = resp.json()["tournament_id"]

    resp = await client.get(f"{BASE}/current", headers=h)
    assert resp.json()["status"] == "active" and resp.json()["tournament_id"] == tournament_id

    await simulate_next_round(db_session)
    resp = await client.get(f"{BASE}/{tournament_id}", headers=h)
    body = resp.json()
    assert resp.status_code == 200 and body["rounds_simulated"] == 1
    assert len(body["standings"]) == 16 and len(body["matches"]) == 8
    assert body["next_round_seconds_remaining"] is not None

    match_id = body["matches"][0]["id"]
    resp = await client.get(f"{BASE}/matches/{match_id}", headers=h)
    assert resp.status_code == 200 and "event_log" in resp.json()


async def test_apply_without_squad_is_409(client, db_session, bot_token):
    from tests.player_tournament_helpers import make_user
    await make_user(client, db_session, bot_token, 880300)
    resp = await client.post(f"{BASE}/apply", headers=telegram_headers(880300, bot_token))
    assert resp.status_code == 409


async def test_rating_leaderboard_sorted(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 880400)
    b = await make_ready_user(client, db_session, bot_token, 880401)
    a.tournament_rating, b.tournament_rating = 3, 8
    db_session.add_all([a, b])
    await db_session.commit()
    resp = await client.get(f"{BASE}/rating", headers=telegram_headers(880400, bot_token))
    rows = resp.json()
    assert [r["tournament_rating"] for r in rows][:2] == [8, 3]


async def test_internal_endpoints_require_secret(client):
    resp = await client.post("/api/v1/internal/player-tournaments/simulate-round")
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_player_tournament_api.py -v`
Expected: FAIL (404s / ModuleNotFoundError).

- [ ] **Step 3: Append schemas**

To `schemas/player_tournament.py`:
```python
class PlayerTournamentStandingOut(BaseModel):
    user_id: int
    display_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    coins_awarded: Optional[int] = None
    rating_delta: Optional[int] = None


class PlayerTournamentMatchSummaryOut(BaseModel):
    id: int
    round_number: int
    user_a_id: int
    user_b_id: int
    score_a: int
    score_b: int


class PlayerTournamentDetailOut(BaseModel):
    id: int
    status: str
    rounds_simulated: int
    standings: list[PlayerTournamentStandingOut]
    matches: list[PlayerTournamentMatchSummaryOut]
    next_round_seconds_remaining: Optional[int] = None


class PlayerTournamentMatchDetailOut(BaseModel):
    id: int
    round_number: int
    user_a_id: int
    user_b_id: int
    user_a_name: str
    user_b_name: str
    score_a: int
    score_b: int
    event_log: list[dict]


class TournamentRatingRowOut(BaseModel):
    user_id: int
    display_name: str
    tournament_rating: int
```

- [ ] **Step 4: Implement query service**

```python
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.timeutil import app_timezone
from app.models.enums import TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.user import User
from app.schemas.player_tournament import (
    PlayerTournamentDetailOut, PlayerTournamentMatchDetailOut, PlayerTournamentMatchSummaryOut,
    PlayerTournamentStandingOut, TournamentRatingRowOut,
)
from app.services.player_tournament_fixture_service import SIMULATION_SLOTS, TOTAL_ROUNDS
from app.services.player_tournament_simulation_service import SLOT_KIND
from app.services.player_tournament_standing_service import rank_standings


async def next_round_seconds_remaining(db: AsyncSession, tournament: PlayerTournament) -> int | None:
    """Seconds until the next slot fires, or 0 when the last passed slot has
    not been processed yet (the bot polls every ~15 min, so there is a
    catch-up window after each slot time — same reasoning as
    routers/clubs._next_round_seconds_remaining)."""
    if tournament.status != TournamentStatus.active or tournament.rounds_simulated >= TOTAL_ROUNDS:
        return None

    now = datetime.now(app_timezone())
    today = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in SIMULATION_SLOTS]
    instants = sorted(today + [t + timedelta(days=1) for t in today] + [t - timedelta(days=1) for t in today])
    past = [t for t in instants if t <= now]
    upcoming = [t for t in instants if t > now]

    if past:
        last_key = past[-1].strftime("%Y-%m-%dT%H:%M")
        processed = (
            await db.execute(
                select(TournamentSimulationSlotLog.id).where(
                    TournamentSimulationSlotLog.kind == SLOT_KIND, TournamentSimulationSlotLog.slot_key == last_key,
                )
            )
        ).scalar_one_or_none()
        if processed is None and (now - past[-1]) < timedelta(hours=6):
            return 0
    return max(0, int((upcoming[0] - now).total_seconds()))


async def get_tournament_detail(db: AsyncSession, tournament_id: int) -> PlayerTournamentDetailOut:
    tournament = await db.get(PlayerTournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (
        await db.execute(select(PlayerTournamentStanding).where(PlayerTournamentStanding.tournament_id == tournament_id))
    ).scalars().all()
    matches = (
        await db.execute(
            select(PlayerTournamentMatch).where(PlayerTournamentMatch.tournament_id == tournament_id)
            .order_by(PlayerTournamentMatch.round_number, PlayerTournamentMatch.id)
        )
    ).scalars().all()
    users = {
        u.id: u for u in (await db.execute(select(User).where(User.id.in_([s.user_id for s in standings])))).scalars().all()
    }
    results = {
        r.user_id: r for r in (
            await db.execute(select(PlayerTournamentResult).where(PlayerTournamentResult.tournament_id == tournament_id))
        ).scalars().all()
    }

    ranked = rank_standings(list(standings), list(matches))
    rows = []
    for s in ranked:
        result = results.get(s.user_id)
        rows.append(PlayerTournamentStandingOut(
            user_id=s.user_id, display_name=users[s.user_id].full_display_name(),
            points=s.points, goals_for=s.goals_for, goals_against=s.goals_against,
            final_rank=result.final_rank if result else None,
            coins_awarded=result.coins_awarded if result else None,
            rating_delta=result.rating_delta if result else None,
        ))
    return PlayerTournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=rows,
        matches=[PlayerTournamentMatchSummaryOut(
            id=m.id, round_number=m.round_number, user_a_id=m.user_a_id, user_b_id=m.user_b_id,
            score_a=m.score_a, score_b=m.score_b,
        ) for m in matches],
        next_round_seconds_remaining=await next_round_seconds_remaining(db, tournament),
    )


async def get_match_detail(db: AsyncSession, match_id: int) -> PlayerTournamentMatchDetailOut:
    match = await db.get(PlayerTournamentMatch, match_id)
    if match is None:
        raise NotFoundError("Матч не найден")
    a = await db.get(User, match.user_a_id)
    b = await db.get(User, match.user_b_id)
    return PlayerTournamentMatchDetailOut(
        id=match.id, round_number=match.round_number, user_a_id=a.id, user_b_id=b.id,
        user_a_name=a.full_display_name(), user_b_name=b.full_display_name(),
        score_a=match.score_a, score_b=match.score_b, event_log=match.event_log,
    )


async def get_rating_leaderboard(db: AsyncSession, limit: int = 50) -> list[TournamentRatingRowOut]:
    users = (
        await db.execute(
            select(User).where(User.tournament_rating != 0)
            .order_by(User.tournament_rating.desc(), User.id).limit(limit)
        )
    ).scalars().all()
    return [
        TournamentRatingRowOut(user_id=u.id, display_name=u.full_display_name(), tournament_rating=u.tournament_rating)
        for u in users
    ]
```
`test_rating_leaderboard_sorted` sets both ratings non-zero, so the `!= 0` filter is fine; players with rating 0 are intentionally omitted from the board. Check how existing leaderboards exclude banned users (`app/routers/leaderboard.py`) and apply the same exclusion here if one exists.

- [ ] **Step 5: Implement router and register it**

`backend/app/routers/player_tournaments.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.lineup import UserCoachCardOut
from app.schemas.personal_squad import (
    PersonalSquadCoachRequest, PersonalSquadOut, PersonalSquadRenameRequest, PersonalSquadSetRequest,
    PersonalSquadTacticsRequest,
)
from app.schemas.player_tournament import (
    PlayerTournamentApplyResult, PlayerTournamentCurrentOut, PlayerTournamentDetailOut,
    PlayerTournamentMatchDetailOut, TournamentRatingRowOut,
)
from app.services import (
    personal_squad_service, player_tournament_query_service, player_tournament_queue_service,
)
from app.services.lineup_service import list_user_coach_cards

router = APIRouter(prefix="/player-tournaments", tags=["player-tournaments"])


@router.get("/squads", response_model=list[PersonalSquadOut])
async def read_squads(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await personal_squad_service.list_templates(db, user)


@router.get("/squads/coach-cards", response_model=list[UserCoachCardOut])
async def read_coach_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_user_coach_cards(db, user)


@router.put("/squads/{template_index}/cards", response_model=PersonalSquadOut)
async def update_squad_cards(
    template_index: int, payload: PersonalSquadSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_squad_cards(db, user, payload, template_index)


@router.put("/squads/{template_index}/tactics", response_model=PersonalSquadOut)
async def update_squad_tactics(
    template_index: int, payload: PersonalSquadTacticsRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_tactics(db, user, payload, template_index)


@router.put("/squads/{template_index}/coach", response_model=PersonalSquadOut)
async def update_squad_coach(
    template_index: int, payload: PersonalSquadCoachRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_coach(db, user, payload, template_index)


@router.put("/squads/{template_index}/name", response_model=PersonalSquadOut)
async def rename_squad(
    template_index: int, payload: PersonalSquadRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.rename_template(db, user, template_index, payload.name)


@router.post("/squads/{template_index}/activate", response_model=PersonalSquadOut)
async def activate_squad(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.activate_template(db, user, template_index)


@router.post("/apply", response_model=PlayerTournamentApplyResult)
async def apply(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_tournament_queue_service.apply_to_tournament(db, user)


@router.get("/current", response_model=PlayerTournamentCurrentOut)
async def current(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_tournament_queue_service.get_current(db, user)


@router.get("/rating", response_model=list[TournamentRatingRowOut])
async def rating(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_rating_leaderboard(db)


@router.get("/matches/{match_id}", response_model=PlayerTournamentMatchDetailOut)
async def match_detail(match_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_match_detail(db, match_id)


@router.get("/{tournament_id}", response_model=PlayerTournamentDetailOut)
async def tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_tournament_detail(db, tournament_id)
```
In `app/main.py`: add `player_tournaments` to the `from app.routers import (...)` list and `app.include_router(player_tournaments.router, prefix=API_PREFIX)` next to `clubs.router`. `/squads/coach-cards` is declared before any `/{...}` route, and the int-typed `/{tournament_id}` cannot shadow `/rating`.

- [ ] **Step 6: Run to verify it passes**

Run: `cd backend && pytest tests/test_player_tournament_api.py -v`
Expected: 5 PASS.

---

### Task 9: Bot scheduler and notification routing

**Files:**
- Create: `bot/services/player_tournament_scheduler.py`
- Modify: `bot/services/tournament_scheduler.py` (`_due_slots` gets an optional `slots` parameter), `bot/services/notifier.py`, `bot/bot.py`
- Test: extend whatever test module already covers `_due_slots` (find it with `grep -rn "_due_slots" bot/ backend/tests`); if none exists, create `bot/tests/test_player_tournament_scheduler.py` following the bot's existing test layout.

**Interfaces:**
- Consumes: `tournament_scheduler._due_slots(now, last_fired, lead_minutes=0, slots=None)`, `_post_internal`-style helper, internal endpoints from Task 7.
- Produces: `PLAYER_TOURNAMENT_SLOTS = [(10, 0), (15, 0), (21, 0)]`, `run_player_tournament_simulation_loop()`, `run_player_tournament_reminder_loop()`.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.player_tournament_scheduler import PLAYER_TOURNAMENT_SLOTS
from services.tournament_scheduler import SIMULATION_SLOTS, _due_slots

TZ = ZoneInfo("Europe/Moscow")


def test_player_slots_are_10_15_21():
    assert PLAYER_TOURNAMENT_SLOTS == [(10, 0), (15, 0), (21, 0)]


def test_due_slots_with_custom_slots_catches_up():
    now = datetime(2026, 9, 25, 16, 0, tzinfo=TZ)
    assert _due_slots(now, {}, slots=PLAYER_TOURNAMENT_SLOTS) == [(10, 0), (15, 0)]
    assert _due_slots(now, {(10, 0): now.date()}, slots=PLAYER_TOURNAMENT_SLOTS) == [(15, 0)]


def test_club_slots_unchanged_by_default():
    now = datetime(2026, 9, 25, 13, 0, tzinfo=TZ)
    assert _due_slots(now, {}) == [slot for slot in SIMULATION_SLOTS if slot == (12, 0)]


def test_reminder_lead_with_custom_slots():
    now = datetime(2026, 9, 25, 20, 10, tzinfo=TZ)
    assert _due_slots(now, {}, lead_minutes=60, slots=PLAYER_TOURNAMENT_SLOTS) == [(10, 0), (15, 0), (21, 0)]
```
(Adapt import paths to how the bot's own tests import `services.*`.)

- [ ] **Step 2: Run to verify it fails**

Run the bot's test command (check `bot/` for pytest config; typically `cd bot && pytest`).
Expected: FAIL (`ModuleNotFoundError` / unexpected `slots` kwarg).

- [ ] **Step 3: Implement**

In `bot/services/tournament_scheduler.py` change the signature only (behavior for existing callers is identical):
```python
def _due_slots(
    now: datetime, last_fired: dict[tuple[int, int], date], lead_minutes: int = 0,
    slots: list[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    ...
    for slot in (SIMULATION_SLOTS if slots is None else slots):
```

`bot/services/player_tournament_scheduler.py`:
```python
import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import get_bot_settings
from services.tournament_scheduler import LOOP_CHECK_INTERVAL_SECONDS, REMINDER_LEAD_MINUTES, _due_slots, _post_internal

logger = logging.getLogger(__name__)
settings = get_bot_settings()

# Keep in sync with backend/app/services/player_tournament_fixture_service.SIMULATION_SLOTS.
# 21:00, not 20:00 — 20:00 is the club tournament slot.
PLAYER_TOURNAMENT_SLOTS: list[tuple[int, int]] = [(10, 0), (15, 0), (21, 0)]


async def _run_loop(path: str, label: str, lead_minutes: int) -> None:
    """Same design as tournament_scheduler.run_simulation_loop: fire each due
    slot once per day with catch-up; duplicate/late fires are made no-ops by
    the backend's slot_key dedup (TournamentSimulationSlotLog)."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=lead_minutes, slots=PLAYER_TOURNAMENT_SLOTS):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal(path, slot_key)
                logger.info("%s fired for slot %s (key %s): %s", label, slot, slot_key, data)
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("%s loop iteration failed", label)
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_player_tournament_simulation_loop() -> None:
    await _run_loop("/player-tournaments/simulate-round", "Player tournament simulation", 0)


async def run_player_tournament_reminder_loop() -> None:
    await _run_loop("/player-tournaments/lineup-reminders", "Player tournament reminders", REMINDER_LEAD_MINUTES)
```

`bot/bot.py`: import the two new coroutines and start them next to `run_simulation_loop()`/`run_lineup_reminder_loop()` in **both** places those are started (lines ~50–51 and ~77–78: `asyncio.create_task(run_player_tournament_simulation_loop())`, `asyncio.create_task(run_player_tournament_reminder_loop())`).

`bot/services/notifier.py`: next to the `"club_match": "/clubs/tournament"` entry add mappings for `player_tournament_match`, `player_tournament_results_ready`, `player_tournament_reminder` → `"/player-tournament"` (the frontend route is created in the frontend plan; the bot only deep-links). Read the surrounding dict/handling first: if the notifier has other per-type logic (titles, keyboards) for `club_*` types, mirror it for the three new types.

- [ ] **Step 4: Run to verify it passes**

Run the bot test command again. Expected: PASS. Also run any pre-existing tests of `_due_slots` — they must still pass unchanged.

---

### Task 10: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite**

Run: `cd backend && pytest tests/ -v`
Expected: all PASS, including all pre-existing club tournament tests. Record the pass count.

- [ ] **Step 2: Import/startup sanity**

Run: `cd backend && python -c "from app.main import app" && alembic heads`
Expected: no error; single head `0119`.

- [ ] **Step 3: Migration on real Postgres (dev compose)**

Run: `docker compose exec backend alembic upgrade head` then `docker compose exec backend alembic current`
Expected: `0119 (head)`. Do NOT run `alembic downgrade` without asking the user first (it drops the new tables).

- [ ] **Step 4: Locking checks on real Postgres**

SQLite does not exercise row locks. Against the dev Postgres (through `docker compose exec backend python`), with an ad-hoc script kept in the scratchpad directory (not committed):
1. Create 16 users with full squads, fire 16 `apply_to_tournament` calls concurrently with `asyncio.gather`, each on its own `AsyncSession`. Expect exactly one tournament, 16 participants, and exactly one `formed` queue.
2. With an active tournament, fire `simulate_next_round(db, slot_key=None)` from 3 concurrent sessions. Expect `rounds_simulated == 1` and exactly 8 matches.
3. Fire two calls with the same `slot_key` concurrently. Expect a single round.
Report the outputs. If a `FOR UPDATE cannot be applied to the nullable side of an outer join` error appears, the `of=PersonalSquad` clause in `personal_squad_service._lock_row` is the place to fix.

- [ ] **Step 5: Review the diff**

Run: `git status && git diff --stat` and skim for: club tournament files untouched (except the additive edits listed in File Structure), no `.env` or scratch files staged, `backend/race_test.py` / `find_missing_columns.sql` still untracked and not included.

- [ ] **Step 6: Report**

List modified/created files, test counts, the Postgres check results, and remaining risks: (a) place/match reward defaults are placeholders to tune in the admin plan, (b) `GameConfig` fields are not yet editable in the admin UI (admin plan), (c) no frontend yet (frontend plan), (d) cards in the tournament squad are not locked against sale/trade — a sold or traded card leads to forfeit or a reminder, by design.

---

## Self-review

**Spec coverage:** 16 players / 30 rounds — Tasks 2, 6. 3 slots 10/15/21 — Tasks 2, 8 (countdown), 9. Squad from own cards with tactic (formation, mentality, playstyle, coach, 5 templates) — Task 4. Queue, no bots — Task 5. Configurable match rewards and place rewards — Tasks 1, 6. Rating +5..+1 / −1..−5, may be negative — Tasks 1, 6. Reminders — Task 7. Idempotent bot slots — Tasks 6, 7, 9. Row locks + Postgres verification — Tasks 5, 6, 10. Admin UI, frontend, profile/leaderboard display are explicitly out of scope (later plans); the rating leaderboard endpoint exists (Task 8).

**Placeholder scan:** the only deliberately open items are named (default reward values tuned later; bot `_due_slots` test location found by grep).
**Type consistency:** `PlayerTournament*` model names, `user_a_id/user_b_id`, `SLOT_KIND`, `resolve_active_squad`/`is_squad_complete`, `PersonalSquad*` schemas, and `SIMULATION_SLOTS`/`TOTAL_ROUNDS`/`TOURNAMENT_SIZE` are used identically across tasks.
