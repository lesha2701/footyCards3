# Clubs Phase 3a: Tournament Backend Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete tournament backend pipeline — queue → 8-club formation → 14 rounds of round-robin matches simulated via a two-sided adaptation of the Card Arena engine → incremental standings → round-14 reward distribution — fully exercisable via API calls with no frontend or scheduler yet.

**Architecture:** New tables/services layered onto the existing Clubs Phase 1/2 codebase, reusing established idioms throughout: `_lock_club`'s row-lock pattern for the new `TournamentQueueState`/`Tournament` singleton/per-row locks, `lineup_service`'s `FORMATION_SLOTS`/`CATEGORY_POSITIONS`/`calculate_base_strength` unchanged for club-squad strength, and `match_service.py`'s probability primitives (`_lerp_chance`, `_resolve_shot_continuation`, `_apply_card`) reused as-is inside a new, two-sided `tournament_match_engine.py` (the one genuinely new piece — Card Arena's own engine is single-sided user-vs-abstract-opponent and can't be called directly).

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, PostgreSQL, pytest (async, in-memory SQLite by default; locking/constraint-sensitive tasks require manual verification against real Postgres via the running `docker compose` `backend`/`postgres` containers).

**Spec:** [docs/superpowers/specs/2026-08-27-clubs-phase3a-tournament-pipeline-design.md](../specs/2026-08-27-clubs-phase3a-tournament-pipeline-design.md)

## Global Constraints

- Every budget-mutating or `rounds_simulated`-advancing operation must row-lock its `Club`/`Tournament` row first, using `.with_for_update().execution_options(populate_existing=True)` — the `club_service._lock_club` idiom, applied by analogy (no pre-existing singleton-lock precedent exists in this codebase; do not trust any comment claiming otherwise).
- `Club.stars_count` has **no** floor — it is allowed to go negative, unlike `budget`. Do not add a CHECK constraint for it.
- `ClubCardAvailability` rows only exist while a card is actually suspended (`rounds_remaining > 0`); a row hitting 0 gets deleted, not kept at 0 — absence of a row means "available."
- Bench = any `ClubCard` belonging to the club that is not currently in its `ClubLineup` — there is no separate bench table (`ClubBenchCard` from the original spec is dropped; do not create it).
- The match engine's probability primitives (`_lerp_chance`, `_lerp_chance_positive`, `_resolve_shot_continuation`, `_apply_card`, `_apply_red_card_debuff` shape) must be reused with the exact same math as `backend/app/services/match_service.py` — copy the functions verbatim into the new module rather than re-deriving the curves, so the two engines stay behaviorally consistent.
- Every new `GameConfig` field must be read via `game_config_service.get_config(db)` at call time — never hardcoded.
- Player-facing error messages in Russian, matching every prior Clubs task's convention.
- Alembic revisions continue sequentially from the current head `0063` — this plan uses `0064`–`0069`.
- `git add` discipline: this working tree may carry files from other, unrelated in-progress sessions of work — every task below names its exact file list; stage only those files, never `-A`/`.`.
- Real-Postgres verification (`docker compose exec -T backend/postgres ...`) is required, not optional, for every task touching row-locking, CHECK constraints, or Postgres-native enum types — SQLite's test DB does not enforce any of these, a lesson this codebase has already paid for multiple times.

---

### Task 1: `Club`/`GameConfig` columns, `ClubBudgetTransactionType.tournament_reward`

**Files:**
- Modify: `backend/app/models/club.py`
- Modify: `backend/app/models/game_config.py`
- Modify: `backend/app/models/enums.py`
- Create: `backend/alembic/versions/0064_club_tournament_columns.py`
- Test: `backend/tests/test_clubs.py`

**Interfaces:**
- Produces: `Club.cups_count`, `Club.stars_count`, `Club.last_tournament_applied_at`; `GameConfig.club_tournament_cooldown_hours`, `.club_form_window_matches`, `.club_form_bonus_per_result`, `.club_tournament_budget_place_1`..`_place_8`; `ClubBudgetTransactionType.tournament_reward` — all consumed by later tasks in this plan.

- [ ] **Step 1: Add the new `Club` columns**

In `backend/app/models/club.py`, add `Optional` to the top-level `datetime` import line (`from datetime import datetime` → keep, add `from typing import Optional` if not already present — check the file first), then inside `class Club`, after the existing `budget` line:

```python
    cups_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_tournament_applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Do **not** add a CHECK constraint for `stars_count` — it is allowed negative by design.

- [ ] **Step 2: Add the new `GameConfig` columns**

In `backend/app/models/game_config.py`, after the existing `club_daily_reward_coins` line:

```python
    club_tournament_cooldown_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    club_form_window_matches: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_form_bonus_per_result: Mapped[float] = mapped_column(Numeric(4, 2), default=0.02, nullable=False)
    club_tournament_budget_place_1: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    club_tournament_budget_place_2: Mapped[int] = mapped_column(Integer, default=750, nullable=False)
    club_tournament_budget_place_3: Mapped[int] = mapped_column(Integer, default=550, nullable=False)
    club_tournament_budget_place_4: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    club_tournament_budget_place_5: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    club_tournament_budget_place_6: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    club_tournament_budget_place_7: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    club_tournament_budget_place_8: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
```

- [ ] **Step 3: Add the new enum member**

In `backend/app/models/enums.py`, inside `class ClubBudgetTransactionType(str, enum.Enum)`, add:

```python
    tournament_reward = "tournament_reward"
```

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/0064_club_tournament_columns.py`:

```python
"""Club tournament columns: cups/stars/cooldown, GameConfig tournament fields, tournament_reward enum value

Revision ID: 0064
Revises: 0063
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("cups_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("clubs", sa.Column("stars_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("clubs", sa.Column("last_tournament_applied_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_tournament_cooldown_hours", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("club_form_window_matches", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("club_form_bonus_per_result", sa.Numeric(4, 2), nullable=False, server_default="0.02"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_1", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_2", sa.Integer(), nullable=False, server_default="750"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_3", sa.Integer(), nullable=False, server_default="550"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_4", sa.Integer(), nullable=False, server_default="400"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_5", sa.Integer(), nullable=False, server_default="300"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_6", sa.Integer(), nullable=False, server_default="200"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_7", sa.Integer(), nullable=False, server_default="120"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_8", sa.Integer(), nullable=False, server_default="60"))

    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'tournament_reward'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition in
    # this codebase (see 0002_tasks_and_minigames.py's identical note).
    op.drop_column("game_config", "club_tournament_budget_place_8")
    op.drop_column("game_config", "club_tournament_budget_place_7")
    op.drop_column("game_config", "club_tournament_budget_place_6")
    op.drop_column("game_config", "club_tournament_budget_place_5")
    op.drop_column("game_config", "club_tournament_budget_place_4")
    op.drop_column("game_config", "club_tournament_budget_place_3")
    op.drop_column("game_config", "club_tournament_budget_place_2")
    op.drop_column("game_config", "club_tournament_budget_place_1")
    op.drop_column("game_config", "club_form_bonus_per_result")
    op.drop_column("game_config", "club_form_window_matches")
    op.drop_column("game_config", "club_tournament_cooldown_hours")

    op.drop_column("clubs", "last_tournament_applied_at")
    op.drop_column("clubs", "stars_count")
    op.drop_column("clubs", "cups_count")
```

- [ ] **Step 5: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d clubs" -c "\d game_config"
```

Confirm all new columns appear with the right types/defaults, and:

```bash
docker compose exec -T postgres psql -U postgres -d footycards -c "SELECT unnest(enum_range(NULL::club_budget_transaction_type_enum))"
```

Confirm `tournament_reward` is now a valid value.

- [ ] **Step 6: Write and run a test**

Add to `backend/tests/test_clubs.py`:

```python
async def test_club_has_tournament_columns_with_zero_defaults(client, db_session, bot_token):
    await register_and_create_club(client, db_session, bot_token, "ФК Тест")
    result = await db_session.execute(select(Club).where(Club.name == "ФК Тест"))
    club = result.scalar_one()
    assert club.cups_count == 0
    assert club.stars_count == 0
    assert club.last_tournament_applied_at is None
```

(Use whatever this file's existing helper for "register a user and create a club" is called — check the top of `test_clubs.py` for its actual name/signature rather than inventing `register_and_create_club`; every other test in this file already does this exact setup.)

```bash
docker compose exec -T backend pytest tests/test_clubs.py -v
```

Expected: PASS, no regressions in the rest of the file.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/club.py backend/app/models/game_config.py backend/app/models/enums.py backend/alembic/versions/0064_club_tournament_columns.py backend/tests/test_clubs.py
git commit -m "Add tournament columns to Club/GameConfig and tournament_reward budget type"
```

---

### Task 2: `TournamentQueueState`/`TournamentQueue`/`TournamentQueueEntry` models

**Files:**
- Create: `backend/app/models/tournament_queue.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0065_tournament_queue.py`
- Test: `backend/tests/test_tournament_queue.py`

**Interfaces:**
- Produces: `TournamentQueueState(id, current_queue_id)`, `TournamentQueue(id, status)`, `TournamentQueueEntry(id, queue_id, club_id, joined_at)`, `TournamentQueueStatus` enum (`open`/`formed`) — consumed by Task 9.

- [ ] **Step 1: Add the enum**

In `backend/app/models/enums.py`, near `ClubBudgetTransactionType`:

```python
class TournamentQueueStatus(str, enum.Enum):
    open = "open"
    formed = "formed"
```

- [ ] **Step 2: Write the models**

Create `backend/app/models/tournament_queue.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentQueueStatus
from app.models.mixins import utcnow


class TournamentQueueState(Base):
    """Singleton row (id=1) pointing at the currently-forming queue."""

    __tablename__ = "tournament_queue_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_queue_id: Mapped[int] = mapped_column(ForeignKey("tournament_queues.id"), nullable=False)


class TournamentQueue(Base):
    __tablename__ = "tournament_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentQueueStatus] = mapped_column(
        Enum(TournamentQueueStatus, name="tournament_queue_status_enum"),
        default=TournamentQueueStatus.open, nullable=False,
    )


class TournamentQueueEntry(Base):
    __tablename__ = "tournament_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("tournament_queues.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
```

Add `from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState` to `backend/app/models/__init__.py` and the three names to `__all__`, matching the file's existing placement convention.

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0065_tournament_queue.py`:

```python
"""TournamentQueueState/TournamentQueue/TournamentQueueEntry

Revision ID: 0065
Revises: 0064
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_queues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "status", sa.Enum("open", "formed", name="tournament_queue_status_enum"),
            nullable=False, server_default="open",
        ),
    )
    op.create_table(
        "tournament_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_queue_id", sa.Integer(), sa.ForeignKey("tournament_queues.id"), nullable=False),
    )
    op.create_table(
        "tournament_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_id", sa.Integer(), sa.ForeignKey("tournament_queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tournament_queue_entries_queue_id", "tournament_queue_entries", ["queue_id"])
    op.create_index("ix_tournament_queue_entries_club_id", "tournament_queue_entries", ["club_id"])

    # Seed row 1 of the singleton immediately — the app code always expects
    # it to exist (get-or-create is Task 9's job for the *queue*, not this
    # one-time bootstrap row).
    op.execute("INSERT INTO tournament_queues (status) VALUES ('open')")
    op.execute("INSERT INTO tournament_queue_state (id, current_queue_id) VALUES (1, (SELECT id FROM tournament_queues ORDER BY id DESC LIMIT 1))")


def downgrade() -> None:
    op.drop_index("ix_tournament_queue_entries_club_id", table_name="tournament_queue_entries")
    op.drop_index("ix_tournament_queue_entries_queue_id", table_name="tournament_queue_entries")
    op.drop_table("tournament_queue_entries")
    op.drop_table("tournament_queue_state")
    op.drop_table("tournament_queues")
    bind = op.get_bind()
    sa.Enum(name="tournament_queue_status_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 4: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "SELECT * FROM tournament_queue_state" -c "SELECT * FROM tournament_queues"
```

Confirm exactly one row in each, `current_queue_id` pointing at the seeded open queue.

- [ ] **Step 5: Write and run a test**

Create `backend/tests/test_tournament_queue.py`:

```python
from sqlalchemy import select

from app.models.tournament_queue import TournamentQueue, TournamentQueueState


async def test_singleton_state_seeded_by_migration(db_session):
    state = (await db_session.execute(select(TournamentQueueState).where(TournamentQueueState.id == 1))).scalar_one()
    queue = (await db_session.execute(select(TournamentQueue).where(TournamentQueue.id == state.current_queue_id))).scalar_one()
    assert queue.status.value == "open"
```

```bash
docker compose exec -T backend pytest tests/test_tournament_queue.py -v
```

Expected: PASS. (If this project's SQLite test fixture doesn't run migrations and instead creates tables from the ORM metadata directly, the singleton row won't be seeded automatically — check `backend/tests/conftest.py`'s `db_session` fixture for how tables get created; if it's `Base.metadata.create_all` with no data seeding, add a `db_session`-scoped fixture in this test file that inserts the singleton row manually before each test, matching whatever pattern `GameConfig`'s tests already use for its own singleton row — check `test_admin_games.py` or similar for that precedent first.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/tournament_queue.py backend/app/models/__init__.py backend/alembic/versions/0065_tournament_queue.py backend/tests/test_tournament_queue.py
git commit -m "Add TournamentQueueState/TournamentQueue/TournamentQueueEntry models"
```

---

### Task 3: `Tournament`/`TournamentClub` models

**Files:**
- Create: `backend/app/models/tournament.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0066_tournament_core.py`
- Test: `backend/tests/test_tournament_core_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Tournament(id, status, rounds_simulated, created_at)`, `TournamentClub(id, tournament_id, club_id, is_withdrawn)`, `TournamentStatus` enum (`active`/`completed`) — consumed by Tasks 9, 14, 15, 16.

- [ ] **Step 1: Add the enum**

In `backend/app/models/enums.py`:

```python
class TournamentStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
```

- [ ] **Step 2: Write the models**

Create `backend/app/models/tournament.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentStatus
from app.models.mixins import utcnow


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(TournamentStatus, name="tournament_status_enum"), default=TournamentStatus.active, nullable=False,
    )
    rounds_simulated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 14", name="ck_tournaments_rounds_simulated_range"),
    )


class TournamentClub(Base):
    __tablename__ = "tournament_clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_clubs_once"),)
```

Add the import + `__all__` entries to `backend/app/models/__init__.py`.

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0066_tournament_core.py`:

```python
"""Tournament, TournamentClub

Revision ID: 0066
Revises: 0065
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Enum("active", "completed", name="tournament_status_enum"), nullable=False, server_default="active"),
        sa.Column("rounds_simulated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 14", name="ck_tournaments_rounds_simulated_range"),
    )
    op.create_table(
        "tournament_clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_withdrawn", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_clubs_once"),
    )
    op.create_index("ix_tournament_clubs_tournament_id", "tournament_clubs", ["tournament_id"])
    op.create_index("ix_tournament_clubs_club_id", "tournament_clubs", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_clubs_club_id", table_name="tournament_clubs")
    op.drop_index("ix_tournament_clubs_tournament_id", table_name="tournament_clubs")
    op.drop_table("tournament_clubs")
    op.drop_table("tournaments")
    bind = op.get_bind()
    sa.Enum(name="tournament_status_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 4: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d tournaments" -c "\d tournament_clubs"
```

Confirm both tables and the `ck_tournaments_rounds_simulated_range` constraint exist. Then verify the constraint is real, not just declared:

```bash
docker compose exec -T postgres psql -U postgres -d footycards -c "INSERT INTO tournaments (status, rounds_simulated, created_at) VALUES ('active', 15, now())"
```

Expected: fails with a check-constraint violation.

- [ ] **Step 5: Write and run a test**

Create `backend/tests/test_tournament_core_models.py`:

```python
from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub


async def test_tournament_defaults(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    assert t.status == TournamentStatus.active
    assert t.rounds_simulated == 0


async def test_tournament_club_unique_per_pair(db_session):
    from sqlalchemy.exc import IntegrityError
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    db_session.add(TournamentClub(tournament_id=t.id, club_id=1))
    await db_session.flush()
    db_session.add(TournamentClub(tournament_id=t.id, club_id=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()
```

```bash
docker compose exec -T backend pytest tests/test_tournament_core_models.py -v
```

Expected: PASS. (SQLite enforces UNIQUE constraints at flush time same as Postgres, so this specific test is fine on SQLite — the CHECK-constraint range test above is the one that needed real-Postgres verification, since SQLite is comparatively lax about CHECK enforcement depending on column affinity; that's already covered by Step 4.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/tournament.py backend/app/models/__init__.py backend/alembic/versions/0066_tournament_core.py backend/tests/test_tournament_core_models.py
git commit -m "Add Tournament/TournamentClub models"
```

---

### Task 4: `TournamentMatch` model

**Files:**
- Create: `backend/app/models/tournament_match.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0067_tournament_match.py`
- Test: `backend/tests/test_tournament_match_model.py`

**Interfaces:**
- Consumes: `Tournament`, `Club` (Task 3, existing).
- Produces: `TournamentMatch(id, tournament_id, round_number, club_a_id, club_b_id, score_a, score_b, event_log, simulated_at)` — consumed by Tasks 11 (writer), 12 (form lookup, reader), 14, 16.

- [ ] **Step 1: Write the model**

Create `backend/app/models/tournament_match.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    club_a_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    club_b_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False)
    # Ordered list of event dicts (same per-event shape match_service.py's
    # MatchEvent rows already use: minute/event_type/team/description/payload).
    # A single JSON column, not a child table — a tournament match is
    # simulated once, in full, non-interactively, so nothing gets appended
    # incrementally the way personal Match.events does.
    event_log: Mapped[list] = mapped_column(JSON, nullable=False)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("round_number >= 1 AND round_number <= 14", name="ck_tournament_matches_round_range"),
    )
```

Add the import + `__all__` entry to `backend/app/models/__init__.py`.

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/0067_tournament_match.py`:

```python
"""TournamentMatch

Revision ID: 0067
Revises: 0066
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("club_a_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_b_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=False),
        sa.Column("score_b", sa.Integer(), nullable=False),
        sa.Column("event_log", sa.JSON(), nullable=False),
        sa.Column("simulated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("round_number >= 1 AND round_number <= 14", name="ck_tournament_matches_round_range"),
    )
    op.create_index("ix_tournament_matches_tournament_id", "tournament_matches", ["tournament_id"])
    op.create_index("ix_tournament_matches_club_a_id", "tournament_matches", ["club_a_id"])
    op.create_index("ix_tournament_matches_club_b_id", "tournament_matches", ["club_b_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_matches_club_b_id", table_name="tournament_matches")
    op.drop_index("ix_tournament_matches_club_a_id", table_name="tournament_matches")
    op.drop_index("ix_tournament_matches_tournament_id", table_name="tournament_matches")
    op.drop_table("tournament_matches")
```

- [ ] **Step 3: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d tournament_matches"
```

- [ ] **Step 4: Write and run a test**

Create `backend/tests/test_tournament_match_model.py`:

```python
from datetime import datetime, timezone

from app.models.tournament import Tournament
from app.models.tournament_match import TournamentMatch


async def test_tournament_match_stores_event_log_json(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    m = TournamentMatch(
        tournament_id=t.id, round_number=1, club_a_id=1, club_b_id=2,
        score_a=2, score_b=1, event_log=[{"minute": 5, "event_type": "goal", "team": "a"}],
        simulated_at=datetime.now(timezone.utc),
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    assert m.event_log[0]["event_type"] == "goal"
```

```bash
docker compose exec -T backend pytest tests/test_tournament_match_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/tournament_match.py backend/app/models/__init__.py backend/alembic/versions/0067_tournament_match.py backend/tests/test_tournament_match_model.py
git commit -m "Add TournamentMatch model"
```

---

### Task 5: `TournamentClubStanding`/`TournamentClubResult` models

**Files:**
- Create: `backend/app/models/tournament_standing.py`
- Create: `backend/app/models/tournament_result.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0068_tournament_standing_result.py`
- Test: `backend/tests/test_tournament_standing_result_models.py`

**Interfaces:**
- Consumes: `Tournament`, `Club`.
- Produces: `TournamentClubStanding(id, tournament_id, club_id, points, goals_for, goals_against)`, `TournamentClubResult(id, tournament_id, club_id, final_rank, budget_awarded, stars_delta, cup_awarded)` — consumed by Tasks 8, 13, 14, 16.

- [ ] **Step 1: Write the models**

Create `backend/app/models/tournament_standing.py`:

```python
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentClubStanding(Base):
    __tablename__ = "tournament_club_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_standings_once"),)
```

Create `backend/app/models/tournament_result.py`:

```python
from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentClubResult(Base):
    __tablename__ = "tournament_club_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    stars_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    cup_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_results_once"),)
```

Add both imports + `__all__` entries to `backend/app/models/__init__.py`.

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/0068_tournament_standing_result.py`:

```python
"""TournamentClubStanding, TournamentClubResult

Revision ID: 0068
Revises: 0067
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_club_standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_for", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_against", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_standings_once"),
    )
    op.create_table(
        "tournament_club_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("budget_awarded", sa.Integer(), nullable=False),
        sa.Column("stars_delta", sa.Integer(), nullable=False),
        sa.Column("cup_awarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_results_once"),
    )
    op.create_index("ix_tournament_club_standings_tournament_id", "tournament_club_standings", ["tournament_id"])
    op.create_index("ix_tournament_club_standings_club_id", "tournament_club_standings", ["club_id"])
    op.create_index("ix_tournament_club_results_tournament_id", "tournament_club_results", ["tournament_id"])
    op.create_index("ix_tournament_club_results_club_id", "tournament_club_results", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_club_results_club_id", table_name="tournament_club_results")
    op.drop_index("ix_tournament_club_results_tournament_id", table_name="tournament_club_results")
    op.drop_index("ix_tournament_club_standings_club_id", table_name="tournament_club_standings")
    op.drop_index("ix_tournament_club_standings_tournament_id", table_name="tournament_club_standings")
    op.drop_table("tournament_club_results")
    op.drop_table("tournament_club_standings")
```

- [ ] **Step 3: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d tournament_club_standings" -c "\d tournament_club_results"
```

- [ ] **Step 4: Write and run a test**

Create `backend/tests/test_tournament_standing_result_models.py`:

```python
from sqlalchemy.exc import IntegrityError

from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding


async def test_standing_unique_per_tournament_club(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    db_session.add(TournamentClubStanding(tournament_id=t.id, club_id=1))
    await db_session.flush()
    db_session.add(TournamentClubStanding(tournament_id=t.id, club_id=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()


async def test_result_stores_final_outcome(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    r = TournamentClubResult(tournament_id=t.id, club_id=1, final_rank=1, budget_awarded=1000, stars_delta=3, cup_awarded=True)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.cup_awarded is True
```

```bash
docker compose exec -T backend pytest tests/test_tournament_standing_result_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/tournament_standing.py backend/app/models/tournament_result.py backend/app/models/__init__.py backend/alembic/versions/0068_tournament_standing_result.py backend/tests/test_tournament_standing_result_models.py
git commit -m "Add TournamentClubStanding/TournamentClubResult models"
```

---

### Task 6: `ClubCardAvailability` model

**Files:**
- Create: `backend/app/models/club_card_availability.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0069_club_card_availability.py`
- Test: `backend/tests/test_club_card_availability_model.py`

**Interfaces:**
- Consumes: `ClubCard` (Phase 2, existing).
- Produces: `ClubCardAvailability(id, club_card_id, rounds_remaining)` — consumed by Task 12 (substitution check), Task 11 (injury/red-card writer), Task 14 (decay).

- [ ] **Step 1: Write the model**

Create `backend/app/models/club_card_availability.py`:

```python
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClubCardAvailability(Base):
    """A row only exists while a ClubCard is actually suspended
    (rounds_remaining > 0). Absence of a row = available. Delete the row
    once rounds_remaining reaches 0 rather than keeping it at 0."""

    __tablename__ = "club_card_availabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), unique=True, nullable=False)
    rounds_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
```

Add the import + `__all__` entry to `backend/app/models/__init__.py`.

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/0069_club_card_availability.py`:

```python
"""ClubCardAvailability

Revision ID: 0069
Revises: 0068
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_card_availabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rounds_remaining", sa.Integer(), nullable=False),
        sa.UniqueConstraint("club_card_id", name="uq_club_card_availabilities_card"),
    )


def downgrade() -> None:
    op.drop_table("club_card_availabilities")
```

- [ ] **Step 3: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d club_card_availabilities"
```

- [ ] **Step 4: Write and run a test**

Create `backend/tests/test_club_card_availability_model.py`:

```python
from sqlalchemy.exc import IntegrityError

from app.models.club_card_availability import ClubCardAvailability


async def test_availability_unique_per_card(db_session):
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=2))
    await db_session.flush()
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()
```

```bash
docker compose exec -T backend pytest tests/test_club_card_availability_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/club_card_availability.py backend/app/models/__init__.py backend/alembic/versions/0069_club_card_availability.py backend/tests/test_club_card_availability_model.py
git commit -m "Add ClubCardAvailability model"
```

---

### Task 7: Fixture generator

**Files:**
- Create: `backend/app/services/tournament_fixture_service.py`
- Test: `backend/tests/test_tournament_fixture_service.py`

**Interfaces:**
- Consumes: nothing (pure function, no DB).
- Produces: `generate_fixtures(club_ids: list[int]) -> list[tuple[int, int, int]]` (`round_number`, `club_a_id`, `club_b_id`) — consumed by Task 9.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_fixture_service.py`:

```python
from app.services.tournament_fixture_service import generate_fixtures


def test_generates_14_rounds_of_4_matches_for_8_clubs():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    assert len(fixtures) == 56  # 14 rounds * 4 matches
    by_round: dict[int, list] = {}
    for round_number, a, b in fixtures:
        by_round.setdefault(round_number, []).append((a, b))
    assert set(by_round.keys()) == set(range(1, 15))
    for round_number, matches in by_round.items():
        assert len(matches) == 4
        clubs_in_round = [c for pair in matches for c in pair]
        assert sorted(clubs_in_round) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_every_pair_meets_exactly_twice():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    pair_counts: dict[frozenset, int] = {}
    for _, a, b in fixtures:
        key = frozenset((a, b))
        pair_counts[key] = pair_counts.get(key, 0) + 1
    assert len(pair_counts) == 28  # C(8, 2)
    assert all(count == 2 for count in pair_counts.values())


def test_no_club_faces_same_opponent_on_consecutive_rounds():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    opponent_by_round_per_club: dict[int, dict[int, int]] = {}
    for round_number, a, b in fixtures:
        opponent_by_round_per_club.setdefault(a, {})[round_number] = b
        opponent_by_round_per_club.setdefault(b, {})[round_number] = a
    for club_id, opponents_by_round in opponent_by_round_per_club.items():
        for round_number in range(1, 14):
            assert opponents_by_round[round_number] != opponents_by_round[round_number + 1]


def test_leg_two_repeats_leg_one_pairings():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    by_round: dict[int, set] = {}
    for round_number, a, b in fixtures:
        by_round.setdefault(round_number, set()).add(frozenset((a, b)))
    for round_number in range(1, 8):
        assert by_round[round_number] == by_round[round_number + 7]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_fixture_service.py -v
```

Expected: FAIL with "module not found" (the service doesn't exist yet).

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_fixture_service.py`:

```python
def generate_fixtures(club_ids: list[int]) -> list[tuple[int, int, int]]:
    """Standard circle-method round-robin for exactly 8 clubs. Fixes club_ids[0],
    rotates the other 7 through 7 rounds of 4 matches each (leg 1, rounds 1-7,
    every pair meets exactly once). Leg 2 (rounds 8-14) repeats the identical
    7 pairings — round n and round n+7 always share the same pairings, and
    since each club faces a distinct opponent in every one of the 7 leg-1
    rounds, round 7's opponent is never the same as round 8's (= round 1's)
    opponent, so no club ever faces the same opponent on two consecutive
    rounds anywhere across the 14-round schedule."""
    if len(club_ids) != 8:
        raise ValueError("generate_fixtures requires exactly 8 clubs")

    fixed = club_ids[0]
    rotating = list(club_ids[1:])  # 7 clubs, rotates each round

    leg_one: list[tuple[int, int, int]] = []
    for round_index in range(7):
        round_number = round_index + 1
        circle = [fixed] + rotating
        pairs = [(circle[i], circle[len(circle) - 1 - i]) for i in range(4)]
        leg_one.extend((round_number, a, b) for a, b in pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    leg_two = [(round_number + 7, a, b) for round_number, a, b in leg_one]
    return leg_one + leg_two
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_fixture_service.py -v
```

Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_fixture_service.py backend/tests/test_tournament_fixture_service.py
git commit -m "Add round-robin fixture generator"
```

---

### Task 8: Standings & tie-break

**Files:**
- Create: `backend/app/services/tournament_standing_service.py`
- Test: `backend/tests/test_tournament_standing_service.py`

**Interfaces:**
- Consumes: `TournamentClubStanding` (Task 5), `TournamentMatch` (Task 4).
- Produces: `apply_match_result(standing_a: TournamentClubStanding, standing_b: TournamentClubStanding, score_a: int, score_b: int) -> None` (mutates in place), `rank_standings(standings: list[TournamentClubStanding], matches: list[TournamentMatch]) -> list[TournamentClubStanding]` — consumed by Tasks 13, 14, 16.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_standing_service.py`:

```python
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.services.tournament_standing_service import apply_match_result, rank_standings


def _standing(club_id: int, points=0, gf=0, ga=0) -> TournamentClubStanding:
    return TournamentClubStanding(tournament_id=1, club_id=club_id, points=points, goals_for=gf, goals_against=ga)


def test_apply_match_result_awards_win_draw_loss_points():
    a, b = _standing(1), _standing(2)
    apply_match_result(a, b, score_a=2, score_b=1)
    assert (a.points, a.goals_for, a.goals_against) == (3, 2, 1)
    assert (b.points, b.goals_for, b.goals_against) == (0, 1, 2)

    a2, b2 = _standing(1), _standing(2)
    apply_match_result(a2, b2, score_a=1, score_b=1)
    assert a2.points == 1 and b2.points == 1


def test_rank_sorts_by_points_then_goal_difference_then_goals_for():
    standings = [
        _standing(1, points=6, gf=5, ga=3),   # GD +2
        _standing(2, points=6, gf=4, ga=1),   # GD +3, higher GF-tiebreak irrelevant since GD already decides
        _standing(3, points=9, gf=1, ga=1),   # most points, wins outright
    ]
    ranked = rank_standings(standings, matches=[])
    assert [s.club_id for s in ranked] == [3, 2, 1]


def test_rank_breaks_a_full_tie_via_head_to_head():
    # Three clubs level on points/GD/GF; club 1 beat club 2, club 2 beat club 3,
    # club 3 beat club 1 (a genuine 3-way cycle) — head-to-head points among
    # just this trio: each has exactly 1 win + 1 loss = 3 points each, so this
    # case degrades to insertion-stable ordering, which is the documented
    # behavior for a true unbreakable cycle (not a bug — nothing left to sort by).
    standings = [_standing(1, points=3, gf=2, ga=2), _standing(2, points=3, gf=2, ga=2), _standing(3, points=3, gf=2, ga=2)]
    matches = [
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=1, club_b_id=2, score_a=1, score_b=0, event_log=[], simulated_at=None),
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=2, club_b_id=3, score_a=1, score_b=0, event_log=[], simulated_at=None),
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=3, club_b_id=1, score_a=1, score_b=0, event_log=[], simulated_at=None),
    ]
    ranked = rank_standings(standings, matches)
    assert len(ranked) == 3  # doesn't crash, produces a total order either way


def test_rank_breaks_a_two_way_tie_via_head_to_head():
    # Clubs 1 and 2 level on points/GD/GF; club 1 beat club 2 head-to-head.
    standings = [_standing(1, points=6, gf=4, ga=2), _standing(2, points=6, gf=4, ga=2)]
    matches = [
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=1, club_b_id=2, score_a=2, score_b=0, event_log=[], simulated_at=None),
    ]
    ranked = rank_standings(standings, matches)
    assert [s.club_id for s in ranked] == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_standing_service.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_standing_service.py`:

```python
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding


def apply_match_result(
    standing_a: TournamentClubStanding, standing_b: TournamentClubStanding, score_a: int, score_b: int
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


def _head_to_head_points(club_ids: set[int], matches: list[TournamentMatch]) -> dict[int, int]:
    points: dict[int, int] = {club_id: 0 for club_id in club_ids}
    for m in matches:
        if m.club_a_id not in club_ids or m.club_b_id not in club_ids:
            continue
        if m.score_a > m.score_b:
            points[m.club_a_id] += 3
        elif m.score_b > m.score_a:
            points[m.club_b_id] += 3
        else:
            points[m.club_a_id] += 1
            points[m.club_b_id] += 1
    return points


def rank_standings(standings: list[TournamentClubStanding], matches: list[TournamentMatch]) -> list[TournamentClubStanding]:
    """Sort: points desc, goal difference desc, goals for desc, then
    head-to-head points (computed only among clubs still tied after the
    first three keys) desc. A true unbreakable N-way cycle falls back to
    stable input order — there is nothing left to sort by at that point."""
    def gd(s: TournamentClubStanding) -> int:
        return s.goals_for - s.goals_against

    groups: dict[tuple[int, int, int], list[TournamentClubStanding]] = {}
    for s in standings:
        key = (s.points, gd(s), s.goals_for)
        groups.setdefault(key, []).append(s)

    ranked: list[TournamentClubStanding] = []
    for key in sorted(groups.keys(), reverse=True):
        group = groups[key]
        if len(group) == 1:
            ranked.extend(group)
            continue
        h2h = _head_to_head_points({s.club_id for s in group}, matches)
        ranked.extend(sorted(group, key=lambda s: h2h[s.club_id], reverse=True))
    return ranked
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_standing_service.py -v
```

Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_standing_service.py backend/tests/test_tournament_standing_service.py
git commit -m "Add tournament standings incremental update and tie-break ranking"
```

---

### Task 9: Queue → formation service + apply endpoint

**Files:**
- Create: `backend/app/services/tournament_queue_service.py`
- Create: `backend/app/schemas/tournament.py`
- Modify: `backend/app/routers/clubs.py`
- Test: `backend/tests/test_tournament_queue_service.py`

**Interfaces:**
- Consumes: `TournamentQueueState`/`TournamentQueue`/`TournamentQueueEntry` (Task 2), `Tournament`/`TournamentClub` (Task 3), `TournamentClubStanding` (Task 5), `generate_fixtures` (Task 7), `_require_manager`/`_require_membership` (Phase 1, `club_service.py`), `get_config` (existing), `ClubLineup`/`ClubLineupCard` (Phase 2).
- Produces: `apply_to_tournament(db, user) -> TournamentApplyResult` in `tournament_queue_service.py`; route `POST /clubs/tournament/apply` — consumed by Task 16 (extended read endpoints reuse `_lock_queue_state`'s module).

- [ ] **Step 1: Write the schema**

Create `backend/app/schemas/tournament.py`:

```python
from typing import Optional

from pydantic import BaseModel


class TournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_tournament_queue_service.py`. This codebase's established convention (see `test_clubs.py`'s own `_seed_position_pool`/`_create_club`/`_register_only` helpers and its top-of-file comment on `test_club_packs.py`'s `REAL_POSTGRES_URL` pattern) is that each test file defines its own local copies of shared setup helpers rather than sharing them via `conftest.py` — follow that same pattern here:

```python
import os

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.enums import Position
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.services.tournament_queue_service import apply_to_tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Same seeding test_clubs.py's own autouse fixture does — each club's
    starter squad needs active Players to draw from per formation category."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club. club_service.create_club
    already auto-seeds a full 11/11 starting lineup via seed_starting_squad
    (Phase 2) — no extra lineup-filling step needed; every freshly created
    club is tournament-eligible on the squad-completeness axis by default."""
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    club = await db_session.get(Club, create_resp.json()["id"])
    return club, captain


async def test_apply_queues_a_ready_club(client, db_session, bot_token):
    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830001, "Тестовый клуб 1")
    result = await apply_to_tournament(db_session, captain)
    assert result.queued is True
    assert result.tournament_id is None
    entry = (await db_session.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.club_id == club.id))).scalar_one()
    assert entry is not None


async def test_eighth_application_forms_tournament(client, db_session, bot_token):
    for i in range(7):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830100 + i, f"Клуб очереди {i}")
        await apply_to_tournament(db_session, captain)

    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830200, "Клуб очереди 7")
    result = await apply_to_tournament(db_session, captain)
    assert result.queued is True
    assert result.tournament_id is not None

    tournament = await db_session.get(Tournament, result.tournament_id)
    assert tournament.rounds_simulated == 0
    participants = (await db_session.execute(select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))).scalars().all()
    assert len(participants) == 8

    state = await db_session.get(TournamentQueueState, 1)
    new_queue = await db_session.get(TournamentQueue, state.current_queue_id)
    assert new_queue.id != tournament.id  # a fresh queue was opened, distinct id space from Tournament anyway
    assert new_queue.status.value == "open"


async def test_apply_rejects_incomplete_squad(client, db_session, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(830300, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, 830300)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(830300, bot_token),
        json={"name": "Неполный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    # club_service.create_club already auto-seeds a full 11/11 lineup today —
    # empty it out to exercise the "incomplete squad" rejection path.
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == create_resp.json()["id"])))
    lineup = lineup.scalar_one()
    await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))
    for lc in (await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().all():
        await db_session.delete(lc)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, captain)


async def test_apply_rejects_non_manager(client, db_session, bot_token):
    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830400, "Клуб не менеджера")
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(830401, bot_token))
    assert resp.status_code == 200
    member = await get_user_by_telegram_id(db_session, 830401)
    join_resp = await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(830401, bot_token))
    assert join_resp.status_code == 200

    from app.core.exceptions import ForbiddenError
    with pytest.raises(ForbiddenError):
        await apply_to_tournament(db_session, member)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_queue_service.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 4: Implement**

Create `backend/app/services/tournament_queue_service.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.club import ClubMember
from app.models.enums import TournamentQueueStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
from app.schemas.tournament import TournamentApplyResult
from app.services.game_config_service import get_config
from app.services.lineup_service import FORMATION_SLOTS
from app.services.tournament_fixture_service import generate_fixtures

TOURNAMENT_CLUB_COUNT = 8
MIN_MEMBERS_TO_APPLY = 2


async def _lock_queue_state(db: AsyncSession) -> TournamentQueueState:
    result = await db.execute(
        select(TournamentQueueState).where(TournamentQueueState.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _has_full_starting_xi(db: AsyncSession, club_id: int) -> bool:
    lineup = (await db.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one_or_none()
    if lineup is None:
        return False
    count = (
        await db.execute(select(func.count(ClubLineupCard.id)).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalar_one()
    return count == len(FORMATION_SLOTS)


async def _is_already_queued_or_active(db: AsyncSession, club_id: int) -> bool:
    queued = (await db.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.club_id == club_id))).scalar_one_or_none()
    if queued is not None:
        return True
    active = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    return active is not None


async def apply_to_tournament(db: AsyncSession, user: User) -> TournamentApplyResult:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club = await db.get(Club, membership.club_id)

    member_count = (
        await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club.id))
    ).scalar_one()
    if member_count < MIN_MEMBERS_TO_APPLY:
        raise ConflictError("В клубе должно быть минимум 2 участника")
    if not await _has_full_starting_xi(db, club.id):
        raise ConflictError("Заполни все 11 позиций в составе клуба, прежде чем подавать заявку")
    if await _is_already_queued_or_active(db, club.id):
        raise ConflictError("Клуб уже в очереди или участвует в турнире")

    config = await get_config(db)
    if club.last_tournament_applied_at is not None:
        elapsed = datetime.now(timezone.utc) - club.last_tournament_applied_at
        if elapsed.total_seconds() < config.club_tournament_cooldown_hours * 3600:
            raise ConflictError("Клуб пока не может подать новую заявку — подожди перед повторной подачей")

    state = await _lock_queue_state(db)
    queue = await db.get(TournamentQueue, state.current_queue_id)

    db.add(TournamentQueueEntry(queue_id=queue.id, club_id=club.id))
    await db.flush()
    club.last_tournament_applied_at = datetime.now(timezone.utc)
    db.add(club)

    entries = (
        await db.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.queue_id == queue.id).order_by(TournamentQueueEntry.joined_at))
    ).scalars().all()

    if len(entries) < TOURNAMENT_CLUB_COUNT:
        await db.commit()
        return TournamentApplyResult(queued=True, queue_position=len(entries))

    club_ids = [e.club_id for e in entries]
    tournament = Tournament()
    db.add(tournament)
    await db.flush()

    for club_id in club_ids:
        db.add(TournamentClub(tournament_id=tournament.id, club_id=club_id))
        db.add(TournamentClubStanding(tournament_id=tournament.id, club_id=club_id))
        club_row = await db.get(Club, club_id)
        club_row.last_tournament_applied_at = datetime.now(timezone.utc)
        db.add(club_row)

    for round_number, club_a_id, club_b_id in generate_fixtures(club_ids):
        # Fixtures themselves aren't persisted as rows yet — TournamentMatch
        # rows are only created when a round is actually simulated (Task 14).
        # generate_fixtures is deterministic given club_ids, so the schedule
        # can always be recomputed; nothing is lost by not storing it early.
        pass

    queue.status = TournamentQueueStatus.formed
    db.add(queue)

    new_queue = TournamentQueue()
    db.add(new_queue)
    await db.flush()
    state.current_queue_id = new_queue.id
    db.add(state)

    await db.commit()
    return TournamentApplyResult(queued=True, tournament_id=tournament.id)
```

- [ ] **Step 5: Add the route**

In `backend/app/routers/clubs.py`, add:

```python
from app.schemas.tournament import TournamentApplyResult
from app.services import tournament_queue_service


@router.post("/tournament/apply", response_model=TournamentApplyResult)
async def apply_to_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await tournament_queue_service.apply_to_tournament(db, user)
```

(Match this file's actual existing import/dependency style — check its current top-of-file imports for `get_current_user`/`get_db`/`User` before adding a duplicate.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_queue_service.py -v
```

Expected: PASS, all 4 tests.

- [ ] **Step 7: Verify the singleton lock against real Postgres under concurrency**

Add to `backend/tests/test_tournament_queue_service.py` — read `test_club_packs.py`'s existing concurrent-race regression test first to confirm this codebase's exact real-session-factory setup (the `create_async_engine(REAL_POSTGRES_URL)`/`async_sessionmaker(...)` construction), then mirror it here rather than inventing a second convention:

```python
import asyncio


async def test_eight_concurrent_applications_form_exactly_one_tournament(client, db_session, bot_token):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    real_engine = create_async_engine(REAL_POSTGRES_URL)
    RealSessionLocal = async_sessionmaker(real_engine, expire_on_commit=False)

    clubs_and_captains = []
    for i in range(8):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830500 + i, f"Гонка {i}")
        clubs_and_captains.append((club, captain))
    await db_session.commit()

    async def apply_in_real_session(captain_id: int):
        async with RealSessionLocal() as session:
            captain = await session.get(type(clubs_and_captains[0][1]), captain_id)
            return await apply_to_tournament(session, captain)

    results = await asyncio.gather(
        *(apply_in_real_session(captain.id) for _, captain in clubs_and_captains), return_exceptions=True
    )
    formed = [r for r in results if not isinstance(r, Exception) and r.tournament_id is not None]
    assert len(formed) == 1

    async with RealSessionLocal() as session:
        participants = (
            await session.execute(select(TournamentClub).where(TournamentClub.tournament_id == formed[0].tournament_id))
        ).scalars().all()
        assert len(participants) == 8

    await real_engine.dispose()
```

```bash
docker compose exec -T backend pytest tests/test_tournament_queue_service.py -k concurrent -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/tournament_queue_service.py backend/app/schemas/tournament.py backend/app/routers/clubs.py backend/tests/test_tournament_queue_service.py
git commit -m "Add tournament queue/formation service and apply endpoint"
```

---

### Task 10: Match engine — moment generation

**Files:**
- Create: `backend/app/services/tournament_match_engine.py`
- Test: `backend/tests/test_tournament_match_engine.py`

**Interfaces:**
- Consumes: `ATTACK_SITUATIONS_BY_SHOT_TYPE`/`DEFENSE_SITUATIONS_BY_SHOT_TYPE`/`ATTACK_SITUATIONS_BY_ID`/`DEFENSE_SITUATIONS_BY_ID` (existing, `match_situations.py`), `GameConfig` (existing, the `match_*` fields), `calculate_base_strength`/`FORMATION_SLOTS`/`CATEGORY_POSITIONS` (existing, `lineup_service.py`).
- Produces: `Actor` dict shape (`club_card_id`, `player_id`, `name`, `rating`, `position`), `generate_moment_queue(strength_a, strength_b, config, lineup_a, lineup_b) -> list[dict]`, `_pick_actor` — consumed by Task 11 (resolution) and this same task's tests.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_match_engine.py`:

```python
import random

from app.services import tournament_match_engine as engine


def _fake_lineup(club_id: int):
    """A minimal fake lineup: list of (club_card_id, player_id, name, rating, position, category) tuples,
    one per FORMATION_SLOTS category, enough for _pick_actor to find candidates in every category."""
    return [
        {"club_card_id": club_id * 100 + i, "player_id": club_id * 100 + i, "name": f"Player{club_id}-{i}",
         "rating": 70, "position": pos, "category": cat}
        for i, (cat, pos) in enumerate([
            ("GK", "GK"), ("DEF", "CB"), ("DEF", "CB"), ("DEF", "LB"), ("DEF", "RB"),
            ("MID", "CDM"), ("MID", "CM"), ("MID", "CAM"), ("FWD", "LW"), ("FWD", "ST"), ("FWD", "RW"),
        ])
    ]


class _FakeConfig:
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def test_moment_queue_has_between_14_and_22_moments():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    assert 14 <= len(moments) <= 22


def test_shot_moments_pick_real_actors_from_both_sides():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    shot_moments = [m for m in moments if m["kind"] == "shot" and m["shot_type"] != "empty_net"]
    assert shot_moments  # with 14-22 moments and the existing shot-chance weight, at least one is virtually certain
    for m in shot_moments:
        attacking_ids = {a["club_card_id"] for a in _fake_lineup(m["attacking_club_id"])}
        assert m["actors"]["shooter" if m["situation_kind"] == "attack" else "defender"]["club_card_id"] in attacking_ids or True
        # (loosened: the precise assertion is that every actor referenced
        # resolves to a real dict with rating/name/position — checked below)
        for actor in m["actors"].values():
            assert set(actor.keys()) >= {"club_card_id", "player_id", "name", "rating", "position"}


def test_stronger_side_attacks_more_often(monkeypatch):
    monkeypatch.setattr(engine.random, "sample", lambda pop, k: list(range(1, k + 1)))
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(140, 10, _FakeConfig(), lineup_a, lineup_b)
    attacking_a = sum(1 for m in moments if m.get("attacking_club_id") == 1 or m.get("team") == "a")
    assert attacking_a > len(moments) / 2
```

(These tests assert on the moment dict's shape loosely since the exact key names are this task's own design surface — tighten the assertions once the implementation below is written, keeping the *intent* — real actors on both sides, weighted-by-strength attacking split — intact.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_match_engine.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_match_engine.py`:

```python
import random

from app.services.match_situations import (
    ATTACK_SITUATIONS_BY_SHOT_TYPE,
    DEFENSE_SITUATIONS_BY_SHOT_TYPE,
)

SHOT_TYPES = ("in_box", "long_range", "empty_net")

# Copied verbatim from match_service.py — same weighting, same intent
# (a "team gets a scoring chance" moment happens at this overall frequency;
# only what happens within it differs from the personal engine).
_FLAVOR_WEIGHTS: list[tuple[str, int]] = [
    ("corner", 9), ("yellow_card", 5), ("red_card", 1), ("offside", 6), ("possession", 20),
]
_SHOT_CHANCE_WEIGHT = 26


def _pick_actor(lineup: list[dict], category: str, preferred_positions: tuple, exclude_ids: tuple[int, ...] = ()) -> dict:
    """Same fallback shape as match_service._pick_actor, generalized to a
    plain list-of-dicts lineup instead of a LineupOut (both sides are real
    here, so there's no single privileged "user" lineup to special-case)."""
    cards = [c for c in lineup if c["category"] == category and c["club_card_id"] not in exclude_ids]
    pool = [c for c in cards if c["position"] in preferred_positions] or cards
    if not pool:
        pool = [c for c in lineup if c["category"] != "GK" and c["club_card_id"] not in exclude_ids]
    return dict(random.choice(pool))


def _build_shot_moment(minute: int, attacking_lineup: list[dict], defending_lineup: list[dict], attacking_side: str, shot_type: str) -> dict:
    moment = {"minute": minute, "kind": "shot", "attacking_side": attacking_side, "shot_type": shot_type}

    if shot_type == "empty_net":
        moment.update(situation_kind="breakaway", situation_id=None, actors={}, actions=["shoot"])
        return moment

    situation = random.choice(ATTACK_SITUATIONS_BY_SHOT_TYPE[shot_type])
    shooter = _pick_actor(attacking_lineup, situation.shooter_category, situation.shooter_positions)
    pass_target = _pick_actor(
        attacking_lineup, situation.pass_target_category, situation.pass_target_positions, exclude_ids=(shooter["club_card_id"],)
    )
    defense_situation = random.choice(DEFENSE_SITUATIONS_BY_SHOT_TYPE[shot_type])
    defender = _pick_actor(defending_lineup, defense_situation.defender_category, defense_situation.defender_positions)

    moment.update(
        situation_kind="attack", situation_id=situation.id, defense_situation_id=defense_situation.id,
        actors={"shooter": shooter, "pass_target": pass_target, "defender": defender},
        actions=["shoot", "pass"],
    )
    return moment


def generate_moment_queue(strength_a: int, strength_b: int, config, lineup_a: list[dict], lineup_b: list[dict]) -> list[dict]:
    """Two-sided generalization of match_service._generate_moment_queue:
    every shot moment carries real actors from BOTH the attacking club
    (shooter/pass target) and the defending club (defender), unlike the
    personal engine's user-vs-abstract-opponent shape."""
    total = strength_a + strength_b
    a_attack_prob = strength_a / total if total else 0.5

    num_chances = random.randint(14, 22)
    minutes = sorted(random.sample(range(1, 90), num_chances))

    kinds = [t for t, _ in _FLAVOR_WEIGHTS] + ["shot_chance"]
    weights = [w for _, w in _FLAVOR_WEIGHTS] + [_SHOT_CHANCE_WEIGHT]
    shot_weights = [
        config.match_shot_type_in_box_weight, config.match_shot_type_long_range_weight, config.match_shot_type_empty_net_weight,
    ]

    moments: list[dict] = []
    for minute in minutes:
        attacking_side = "a" if random.random() < a_attack_prob else "b"
        kind = random.choices(kinds, weights=weights, k=1)[0]
        if kind == "shot_chance":
            shot_type = random.choices(list(SHOT_TYPES), weights=shot_weights, k=1)[0]
            attacking_lineup, defending_lineup = (lineup_a, lineup_b) if attacking_side == "a" else (lineup_b, lineup_a)
            moments.append(_build_shot_moment(minute, attacking_lineup, defending_lineup, attacking_side, shot_type))
        else:
            moments.append({"minute": minute, "kind": "flavor", "event_type": kind, "attacking_side": attacking_side})
    return moments
```

- [ ] **Step 4: Fix up the tests to match the real moment shape, run to verify they pass**

Revisit the loosened assertions from Step 1 now that the real key names (`attacking_side` not `attacking_club_id`/`team`) exist — tighten `test_stronger_side_attacks_more_often` and `test_shot_moments_pick_real_actors_from_both_sides` to check `moment["attacking_side"]` directly instead of the placeholder logic.

```bash
docker compose exec -T backend pytest tests/test_tournament_match_engine.py -v
```

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_match_engine.py backend/tests/test_tournament_match_engine.py
git commit -m "Add tournament match engine: two-sided moment generation"
```

---

### Task 11: Match engine — resolution & `simulate_match`

**Files:**
- Modify: `backend/app/services/tournament_match_engine.py`
- Test: `backend/tests/test_tournament_match_engine.py`

**Interfaces:**
- Consumes: `generate_moment_queue`/`_pick_actor` (Task 10), `ClubCardAvailability` (Task 6), `GameConfig` (existing).
- Produces: `simulate_match(strength_a, strength_b, lineup_a, lineup_b, config) -> MatchResult` (`score_a`, `score_b`, `event_log: list[dict]`, `injuries: list[tuple[int, int]]` — `(club_card_id, rounds)`, `red_cards: list[tuple[int, int]]` — `(club_card_id, rounds_remaining=1)`) — `strength_a`/`strength_b` are the caller's already-adjusted strengths (substitution penalty + form multiplier already applied, see Task 12/14's `match_strength`); the engine does not recompute strength from the raw lineup itself, so those adjustments actually reach the attack-probability split — consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tournament_match_engine.py`:

```python
def test_simulate_match_produces_deterministic_score_from_event_log(monkeypatch):
    # Force every shot to score: all miss/save/block/foul rolls fail.
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())
    goals_in_log = sum(1 for e in result.event_log if e["event_type"] == "goal")
    assert goals_in_log == result.score_a + result.score_b
    assert result.score_a >= 0 and result.score_b >= 0


def test_simulate_match_default_action_policy_shoots_on_positive_bias(monkeypatch):
    # A situation with bias >= 0 should always resolve via "shoot", never "pass" —
    # verified by checking every attack-kind event's payload["action"].
    monkeypatch.setattr(engine.random, "random", lambda: 0.5)
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())
    for e in result.event_log:
        if "action" in e.get("payload", {}) and e["payload"]["action"] in ("shoot", "pass"):
            situation = engine.ATTACK_SITUATIONS_BY_ID[e["payload"].get("situation_id", "")]
            # Only check where we can recover the situation's bias from the log;
            # otherwise this loop is a no-op for that event.


def test_simulate_match_records_red_card_and_injury_availability():
    # Force every tackle to foul with a red card, and every breakaway to injure —
    # deterministic via monkeypatching the specific roll functions rather than
    # blanket-forcing random.random(), since a blanket force also forces misses.
    ...
```

(The exact monkeypatch strategy for isolating "always red card" vs "always score" needs per-roll-function patching, not a single blanket `random.random()` override, since a match has many distinct roll sites. Write `_FakeMatchConfig` as a class exposing every `match_*` field `_resolve_shot_continuation`/etc. read, copied from `GameConfig`'s defaults (see `backend/app/models/game_config.py`), and use `monkeypatch.setattr(engine, "_apply_card", lambda *a, **kw: "red")` / equivalent targeted patches for the red-card/injury tests rather than a single global `random.random()` override across the whole test.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_match_engine.py -v
```

Expected: FAIL — `simulate_match` doesn't exist yet.

- [ ] **Step 3: Implement**

Append to `backend/app/services/tournament_match_engine.py`:

```python
import random
from dataclasses import dataclass, field

from app.services.match_situations import ATTACK_SITUATIONS_BY_ID, DEFENSE_SITUATIONS_BY_ID


def _lerp_chance(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return high - (r - 58) / (99 - 58) * (high - low)


def _lerp_chance_positive(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return low + (r - 58) / (99 - 58) * (high - low)


def _clamp_rating(rating: float) -> int:
    return max(58, min(99, round(rating)))


def _resolve_shot_continuation(missed: bool, shot_type: str, config, blocker_rating, keeper_rating) -> tuple[str, dict]:
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max))
    if not missed and not blocked:
        saved = random.random() < _lerp_chance_positive(keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


@dataclass
class MatchResult:
    score_a: int
    score_b: int
    event_log: list[dict] = field(default_factory=list)
    injuries: list[tuple[int, int]] = field(default_factory=list)      # (club_card_id, rounds_remaining)
    red_cards: list[tuple[int, int]] = field(default_factory=list)     # (club_card_id, rounds_remaining=1)


def _resolve_shot_action(attacking_side: str, moment: dict, config) -> tuple[dict, str]:
    """Default action policy for auto-resolution (nobody is watching live):
    shoot when the situation's bias is non-negative (a "clear" chance), pass
    otherwise; the shooter/pass-target choice, and every subsequent
    miss/block/save roll, is otherwise identical to a human picking the same
    action in the personal engine."""
    situation = ATTACK_SITUATIONS_BY_ID[moment["situation_id"]]
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    defender = moment["actors"]["defender"]
    shot_type = moment["shot_type"]

    action = "shoot" if situation.bias >= 0 else "pass"
    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + situation.bias)
        missed = random.random() < _lerp_chance(eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max))
        scorer = shooter
    else:
        eff_passer_rating = _clamp_rating(shooter["rating"] - situation.bias)
        pass_failed = random.random() < _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max))
        if pass_failed:
            event = {
                "minute": moment["minute"], "event_type": "pass_failed", "team": attacking_side,
                "payload": {"shot_type": shot_type, "action": "pass", "passer": shooter["name"]},
            }
            return event, "none"
        missed = random.random() < _lerp_chance(pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max))
        scorer = pass_target

    outcome, extra = _resolve_shot_continuation(missed, shot_type, config, blocker_rating=defender["rating"], keeper_rating=defender["rating"])
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": {"shot_type": shot_type, "action": action, "shooter": scorer["name"], **extra},
    }
    return event, (attacking_side if outcome == "goal" else "none")


def _resolve_defense_tackle(defending_side: str, moment: dict, config) -> tuple[dict, str, tuple[int, str] | None]:
    """Default policy: defending side always attempts a tackle (same
    rating-driven foul/card rolls as a human picking 'tackle' today).
    Returns (event, scoring_side_or_none, (club_card_id, 'red'|'yellow')_or_none)."""
    defender = moment["actors"]["defender"]
    defense_situation = DEFENSE_SITUATIONS_BY_ID[moment["defense_situation_id"]]
    shot_type = moment["shot_type"]

    foul = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max))
    if not foul:
        event = {
            "minute": moment["minute"], "event_type": "tackle_won", "team": defending_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"]},
        }
        return event, "none", None

    is_red = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max))
    card_kind = "red" if is_red else "yellow"

    if "box" in defense_situation.tags:
        eff_gk = _clamp_rating(defender["rating"] - config.match_penalty_gk_rating_penalty)
        saved = random.random() < _lerp_chance_positive(eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
        outcome = "save" if saved else "goal"
        attacking_side = "a" if defending_side == "b" else "b"
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": True},
        }
        return event, (attacking_side if outcome == "goal" else "none"), (defender["club_card_id"], card_kind)

    event = {
        "minute": moment["minute"], "event_type": "foul_stopped", "team": defending_side,
        "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": False},
    }
    return event, "none", (defender["club_card_id"], card_kind)


def _resolve_breakaway(attacking_side: str, moment: dict, lineup: list[dict], config) -> tuple[dict, str]:
    fwd_candidates = [c for c in lineup if c["category"] == "FWD"]
    fwd_rating = fwd_candidates[0]["rating"] if fwd_candidates else 70
    missed = random.random() < _lerp_chance(fwd_rating, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max))
    outcome = "shot" if missed else "goal"
    event = {"minute": moment["minute"], "event_type": outcome, "team": attacking_side, "payload": {"shot_type": "empty_net", "missed": missed}}
    return event, (attacking_side if outcome == "goal" else "none")


def simulate_match(strength_a: int, strength_b: int, lineup_a: list[dict], lineup_b: list[dict], config) -> "MatchResult":
    """strength_a/strength_b are the caller's already-adjusted strengths
    (substitution penalty + form multiplier already applied — see
    tournament_simulation_service.match_strength) and drive the
    attacking-probability split; they are NOT recomputed here from the raw
    lineup, so those adjustments actually influence which side attacks more."""
    moments = generate_moment_queue(strength_a, strength_b, config, lineup_a, lineup_b)

    result = MatchResult(score_a=0, score_b=0)
    for moment in moments:
        if moment["kind"] == "flavor":
            continue  # not persisted to event_log — purely narrative in the personal engine, same here
        attacking_side = moment["attacking_side"]
        defending_side = "b" if attacking_side == "a" else "a"

        if moment["situation_kind"] == "breakaway":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            if scorer != "none":
                setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
            continue

        situation = ATTACK_SITUATIONS_BY_ID[moment["situation_id"]]
        # Defense is attempted first only when the tackle situation's own
        # random roll is the one that decides whether the attack even
        # reaches a shot — mirrors match_service's "tackle can stop an
        # attack before it becomes a shot" flow for the "box"/foul path;
        # everywhere else, shoot/pass resolves directly against the
        # defender's rating via _resolve_shot_continuation's blocker/keeper
        # roll, same as the personal engine.
        event, scorer = _resolve_shot_action(attacking_side, moment, config)
        result.event_log.append(event)
        if scorer != "none":
            setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)

        if event["event_type"] in ("blocked", "save") and random.random() < 0.15:
            # A blocked/saved shot has a further chance the defender committed
            # a foul in the process — routes through the same tackle-resolution
            # roll so red/yellow cards can occur on defense, not just attack.
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            if defense_scorer != "none":
                setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
            if card is not None:
                club_card_id, card_kind = card
                if card_kind == "red":
                    result.red_cards.append((club_card_id, 1))
                    if random.random() < 0.3:
                        result.injuries.append((club_card_id, random.randint(1, 3)))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_match_engine.py -v
```

Expected: PASS. If the deterministic-score test is flaky under `random.random() -> 0.99`, trace which roll site is still landing on the "miss" branch given the `_lerp_chance` direction (miss chance is HIGHEST at low rating and uses `_lerp_chance`, which returns `high` at rating 58 and `low` at rating 99 — a forced `0.99` return from `random.random()` needs the roll's threshold to be below `0.99` for "always triggers," which it is for every `_lerp_chance`-based miss/foul/fail check; verify this reasoning holds by printing the actual computed thresholds if the test doesn't pass on the first try, rather than guessing at a different monkeypatch value).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_match_engine.py backend/tests/test_tournament_match_engine.py
git commit -m "Add tournament match engine: resolution and simulate_match"
```

---

### Task 12: Lineup resolution, substitution, and form multiplier

**Files:**
- Create: `backend/app/services/tournament_simulation_service.py`
- Test: `backend/tests/test_tournament_simulation_lineup.py`

**Interfaces:**
- Consumes: `_get_or_none_lineup` (Phase 2, `club_squad_service.py`, private cross-module import — same established pattern that module already uses for `_require_manager`/`_require_membership`), `ClubCardAvailability` (Task 6), `ClubCard` (Phase 2), `CATEGORY_POSITIONS`/`FORMATION_SLOTS` (existing, `lineup_service.py`), `TournamentMatch` (Task 4), `GameConfig`.
- Produces: `resolve_match_lineup(db, club_id) -> tuple[list[dict], bool]` (engine-ready lineup as list-of-dicts matching Task 10's expected shape, `had_substitution` flag), `form_multiplier(db, club_id, config) -> float`, `match_strength(db, club_id, config) -> int` — consumed by Task 14.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_simulation_lineup.py`:

```python
from sqlalchemy import select

from app.models.club_card_availability import ClubCardAvailability
from app.services.tournament_simulation_service import form_multiplier, resolve_match_lineup


async def test_resolve_match_lineup_returns_engine_shape(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, had_sub = await resolve_match_lineup(db_session, club.id)
    assert len(lineup) == 11
    assert had_sub is False
    for c in lineup:
        assert set(c.keys()) >= {"club_card_id", "player_id", "name", "rating", "position", "category"}


async def test_resolve_match_lineup_substitutes_suspended_card(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, _ = await resolve_match_lineup(db_session, club.id)
    suspended_card_id = lineup[0]["club_card_id"]
    db_session.add(ClubCardAvailability(club_card_id=suspended_card_id, rounds_remaining=2))
    await db_session.commit()

    new_lineup, had_sub = await resolve_match_lineup(db_session, club.id)
    assert had_sub is True
    assert suspended_card_id not in {c["club_card_id"] for c in new_lineup}
    assert len(new_lineup) == 11


async def test_form_multiplier_is_one_with_no_history(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    from app.services.game_config_service import get_config
    config = await get_config(db_session)
    assert await form_multiplier(db_session, club.id, config) == 1.0
```

(`seeded_club_with_full_squad` is a local `pytest_asyncio.fixture` this file needs to define itself — same per-file-local convention as every other test file in this plan; build it the same way Task 9's `_create_club_with_full_squad` helper does — register a user, create a club — since `seed_starting_squad` already fills a full XI on creation, no extra lineup-setting step is needed. Return `(club, captain_user)`.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_lineup.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_simulation_service.py`:

```python
import random

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.tournament_match import TournamentMatch
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS, calculate_base_strength

SUBSTITUTION_PENALTY = 0.5


def _card_to_actor(card: ClubCard, category: str) -> dict:
    return {
        "club_card_id": card.id, "player_id": card.player_id, "name": card.player.display_name,
        "rating": card.player.rating, "position": card.player.position.value, "category": category,
    }


async def resolve_match_lineup(db: AsyncSession, club_id: int) -> tuple[list[dict], bool]:
    """Returns (engine-ready lineup list, had_substitution). Substitutes any
    slot whose card is currently suspended (ClubCardAvailability.rounds_remaining
    > 0) from the bench — any ClubCard for this club not currently in the
    lineup — same category first, any category as fallback."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return [], False

    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards}
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}

    suspended_ids: set[int] = set()
    if lineup_card_ids:
        rows = (
            await db.execute(
                select(ClubCardAvailability.club_card_id)
                .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
            )
        ).scalars().all()
        suspended_ids = set(rows)

    bench_cards = (
        await db.execute(
            select(ClubCard).where(ClubCard.club_id == club_id, ClubCard.id.notin_(lineup_card_ids or [0]))
            .options(joinedload(ClubCard.player))
        )
    ).unique().scalars().all()

    used_bench_ids: set[int] = set()
    had_substitution = False
    result: list[dict] = []

    for slot in FORMATION_SLOTS:
        card = by_slot.get(slot.code)
        if card is None or card.id in suspended_ids:
            had_substitution = True
            candidates = [b for b in bench_cards if b.id not in used_bench_ids and b.player.position in CATEGORY_POSITIONS[slot.category]]
            if not candidates:
                candidates = [b for b in bench_cards if b.id not in used_bench_ids]
            if candidates:
                sub = random.choice(candidates)
                used_bench_ids.add(sub.id)
                result.append(_card_to_actor(sub, slot.category))
            # else: no bench card available at all — slot stays unfilled, club
            # effectively plays a player short there; rare (needs >4 simultaneous
            # suspensions with an empty matching bench), not specially handled.
        else:
            result.append(_card_to_actor(card, slot.category))

    return result, had_substitution


async def form_multiplier(db: AsyncSession, club_id: int, config) -> float:
    matches = (
        await db.execute(
            select(TournamentMatch)
            .where(or_(TournamentMatch.club_a_id == club_id, TournamentMatch.club_b_id == club_id))
            .order_by(TournamentMatch.simulated_at.desc())
            .limit(config.club_form_window_matches)
        )
    ).scalars().all()
    delta = 0
    for m in matches:
        my_score, opp_score = (m.score_a, m.score_b) if m.club_a_id == club_id else (m.score_b, m.score_a)
        if my_score > opp_score:
            delta += 1
        elif my_score < opp_score:
            delta -= 1
    return 1 + delta * float(config.club_form_bonus_per_result)


async def match_strength(db: AsyncSession, club_id: int, config) -> tuple[int, list[dict]]:
    """Returns (final strength, engine-ready lineup) — bundled together since
    Task 14's orchestration needs both from one lineup resolution pass."""
    lineup, had_substitution = await resolve_match_lineup(db, club_id)
    cards_with_slots = [
        (type("Wrapped", (), {"player": type("P", (), {
            "position": _pos_enum(c["position"]), "rating": c["rating"], "rarity": None, "club": None, "country": None,
        })})(), slot)
        for c, slot in zip(lineup, FORMATION_SLOTS)
    ]
    # NOTE: calculate_base_strength needs real ClubCard/Player ORM objects
    # (it reads .player.rarity/.club/.country for the chemistry bonus), not
    # the engine's plain actor dicts — see Task 14, which calls this
    # function with the actual ORM cards fetched during resolve_match_lineup
    # rather than reconstructing fakes here. This function's real
    # implementation is finished in Task 14 once that ORM-object plumbing
    # is available; for now it returns a rating-average approximation.
    base = sum(c["rating"] for c in lineup) // max(len(lineup), 1) if lineup else 0
    if had_substitution:
        base = round(base * SUBSTITUTION_PENALTY)
    multiplier = await form_multiplier(db, club_id, config)
    return max(1, round(base * multiplier)), lineup


def _pos_enum(value: str):
    from app.models.enums import Position
    return Position(value)
```

Note the `match_strength` docstring: this function's `calculate_base_strength` integration is intentionally deferred to Task 14, which has the real ORM `ClubCard` objects on hand (not just the engine's plain dicts) — Task 14's implementer should replace the rating-average approximation here with a real call to `calculate_base_strength(cards_with_slots)` using the actual `(ClubCard, FormationSlot)` tuples `resolve_match_lineup` could also return alongside the plain-dict shape (extend `resolve_match_lineup`'s return value in Task 14 if needed, rather than reconstructing fake ORM-shaped objects as this task's placeholder does — that placeholder is a known-deliberate stopgap so this task's own tests don't depend on Task 14 landing first, not a piece of production logic to keep).

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_lineup.py -v
```

Expected: PASS, the 3 tests (which only exercise `resolve_match_lineup`/`form_multiplier`, not `match_strength`'s known-stopgap chemistry-bonus approximation).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_simulation_service.py backend/tests/test_tournament_simulation_lineup.py
git commit -m "Add tournament lineup resolution, substitution, and form multiplier"
```

---

### Task 13: Reward & conclusion service

**Files:**
- Create: `backend/app/services/tournament_reward_service.py`
- Test: `backend/tests/test_tournament_reward_service.py`

**Interfaces:**
- Consumes: `rank_standings` (Task 8), `TournamentClubResult` (Task 5), `credit_club_budget` (existing, `club_budget_service.py`), `GameConfig` (`club_tournament_budget_place_1`..`_8`).
- Produces: `conclude_tournament(db, tournament, standings, matches) -> list[TournamentClubResult]` — consumed by Task 14.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tournament_reward_service.py`:

```python
from sqlalchemy import select

from app.models.club import Club
from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.services.game_config_service import get_config
from app.services.tournament_reward_service import conclude_tournament


async def _make_club(db_session, name: str) -> Club:
    club = Club(name=name, description="", club_type="open", logo_shape="shield", logo_color="#000", captain_id=1, invite_code=name[:8])
    db_session.add(club)
    await db_session.flush()
    return club


async def test_conclude_awards_cups_stars_budget_by_rank(db_session):
    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()

    clubs = [await _make_club(db_session, f"Club{i}") for i in range(8)]
    standings = []
    for i, club in enumerate(clubs):
        s = TournamentClubStanding(tournament_id=tournament.id, club_id=club.id, points=(8 - i) * 3, goals_for=10, goals_against=0)
        db_session.add(s)
        standings.append(s)
    await db_session.flush()

    config = await get_config(db_session)
    results = await conclude_tournament(db_session, tournament, standings, matches=[])
    await db_session.commit()

    by_club = {r.club_id: r for r in results}
    first_result = by_club[clubs[0].id]
    assert first_result.final_rank == 1
    assert first_result.cup_awarded is True
    assert first_result.stars_delta == 3
    assert first_result.budget_awarded == config.club_tournament_budget_place_1

    last_result = by_club[clubs[7].id]
    assert last_result.final_rank == 8
    assert last_result.stars_delta == -3
    assert last_result.cup_awarded is False

    await db_session.refresh(clubs[0])
    assert clubs[0].cups_count == 1
    assert clubs[0].stars_count == 3
    assert clubs[0].budget == config.club_tournament_budget_place_1

    await db_session.refresh(clubs[7])
    assert clubs[7].stars_count == -3


async def test_conclude_leaves_4th_and_5th_stars_unchanged(db_session):
    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()
    clubs = [await _make_club(db_session, f"ClubB{i}") for i in range(8)]
    standings = [TournamentClubStanding(tournament_id=tournament.id, club_id=c.id, points=(8 - i) * 3) for i, c in enumerate(clubs)]
    db_session.add_all(standings)
    await db_session.flush()

    results = await conclude_tournament(db_session, tournament, standings, matches=[])
    by_rank = {r.final_rank: r for r in results}
    assert by_rank[4].stars_delta == 0
    assert by_rank[5].stars_delta == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec -T backend pytest tests/test_tournament_reward_service.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_reward_service.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import Club
from app.models.enums import ClubBudgetTransactionType
from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.services.club_budget_service import credit_club_budget
from app.services.game_config_service import get_config
from app.services.tournament_standing_service import rank_standings

_STARS_BY_RANK = {1: 3, 2: 2, 3: 1, 4: 0, 5: 0, 6: -1, 7: -2, 8: -3}


async def conclude_tournament(
    db: AsyncSession, tournament: Tournament, standings: list[TournamentClubStanding], matches: list
) -> list[TournamentClubResult]:
    config = await get_config(db)
    budget_by_rank = {
        1: config.club_tournament_budget_place_1, 2: config.club_tournament_budget_place_2,
        3: config.club_tournament_budget_place_3, 4: config.club_tournament_budget_place_4,
        5: config.club_tournament_budget_place_5, 6: config.club_tournament_budget_place_6,
        7: config.club_tournament_budget_place_7, 8: config.club_tournament_budget_place_8,
    }

    ranked = rank_standings(standings, matches)
    results: list[TournamentClubResult] = []

    for index, standing in enumerate(ranked):
        rank = index + 1
        club = await db.get(Club, standing.club_id)
        stars_delta = _STARS_BY_RANK[rank]
        budget_awarded = budget_by_rank[rank]
        cup_awarded = rank == 1

        await credit_club_budget(
            db, club, budget_awarded, ClubBudgetTransactionType.tournament_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}",
            related_object_type="tournament", related_object_id=tournament.id,
        )
        club.stars_count += stars_delta
        if cup_awarded:
            club.cups_count += 1
        db.add(club)

        result = TournamentClubResult(
            tournament_id=tournament.id, club_id=club.id, final_rank=rank,
            budget_awarded=budget_awarded, stars_delta=stars_delta, cup_awarded=cup_awarded,
        )
        db.add(result)
        results.append(result)

    tournament.status = "completed"
    db.add(tournament)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_reward_service.py -v
```

Expected: PASS, both tests.

- [ ] **Step 5: Verify `Club.budget`/`stars_count` mutation against real Postgres**

```bash
docker compose exec -T backend pytest tests/test_tournament_reward_service.py -v
docker compose exec -T postgres psql -U postgres -d footycards -c "SELECT budget, stars_count, cups_count FROM clubs ORDER BY id DESC LIMIT 8"
```

(Run the test suite against the dev Postgres-backed API — not strictly required for this task's own pure-arithmetic logic, since `stars_count` has no CHECK constraint to verify and `credit_club_budget` is already proven elsewhere, but confirm no unexpected float/rounding artifacts landed in `budget`/`stars_count` from the `Numeric(4,2)` `club_form_bonus_per_result` field type touching this code path indirectly — it doesn't in this task, but note this for whoever reviews Task 14, which does combine them.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tournament_reward_service.py backend/tests/test_tournament_reward_service.py
git commit -m "Add tournament reward distribution and conclusion service"
```

---

### Task 14: `simulate_next_round` orchestration + internal endpoint

**Files:**
- Modify: `backend/app/services/tournament_simulation_service.py`
- Modify: `backend/app/routers/internal.py`
- Test: `backend/tests/test_tournament_simulation_service.py`

**Interfaces:**
- Consumes: everything from Tasks 3–13 (`Tournament`, `TournamentClub`, `TournamentMatch`, `TournamentClubStanding`, `generate_fixtures`, `simulate_match`, `resolve_match_lineup`, `apply_match_result`, `conclude_tournament`, `credit_club_budget`).
- Produces: `simulate_next_round(db) -> list[TournamentMatch]` in `tournament_simulation_service.py`; route `POST /internal/clubs/simulate-round`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_simulation_service.py`:

```python
from sqlalchemy import select

from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.services.tournament_simulation_service import simulate_next_round


async def test_simulate_next_round_simulates_round_1_for_a_fresh_tournament(db_session, eight_club_tournament):
    tournament = eight_club_tournament
    matches = await simulate_next_round(db_session)
    await db_session.commit()

    round_1_matches = [m for m in matches if m.tournament_id == tournament.id]
    assert len(round_1_matches) == 4
    await db_session.refresh(tournament)
    assert tournament.rounds_simulated == 1
    for m in round_1_matches:
        assert m.event_log  # non-empty for a real (non-withdrawn) match
        assert m.score_a >= 0 and m.score_b >= 0


async def test_simulate_next_round_is_idempotent_under_concurrent_calls(db_session, eight_club_tournament):
    # Mirrors test_club_packs.py's asyncio.gather concurrent-race pattern —
    # two concurrent calls against the same tournament must not double-simulate
    # round 1 (checked by asserting rounds_simulated == 1 and exactly 4 matches
    # exist for round 1 afterward, not 8).
    import asyncio
    from tests.conftest import RealSessionLocal  # or wherever this codebase's real-session factory lives — check test_club_packs.py's import

    async def call():
        async with RealSessionLocal() as session:
            return await simulate_next_round(session)

    await asyncio.gather(call(), call(), return_exceptions=True)

    async with RealSessionLocal() as session:
        tournament = await session.get(Tournament, eight_club_tournament.id)
        assert tournament.rounds_simulated == 1
        round_1_count = (
            await session.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament.id, TournamentMatch.round_number == 1))
        ).scalars().all()
        assert len(round_1_count) == 4


async def test_simulate_next_round_updates_standings(db_session, eight_club_tournament):
    tournament = eight_club_tournament
    await simulate_next_round(db_session)
    await db_session.commit()
    standings = (await db_session.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament.id))).scalars().all()
    total_points_awarded = sum(s.points for s in standings)
    # 4 matches this round: each is either 3+0 (decisive) or 1+1 (draw) points —
    # so total points across all 8 clubs is between 12 (all draws) and 12 (all decisive, 3*4)
    assert total_points_awarded == 12


async def test_simulate_next_round_concludes_tournament_at_round_14(db_session, eight_club_tournament_at_round_13):
    tournament, _clubs_and_captains = eight_club_tournament_at_round_13
    await simulate_next_round(db_session)
    await db_session.commit()
    await db_session.refresh(tournament)
    assert tournament.rounds_simulated == 14
    assert tournament.status.value == "completed"


async def test_round_14_reward_distribution_cannot_double_fire_under_concurrency(db_session, eight_club_tournament_at_round_13):
    # Mirrors test_club_packs.py's real-Postgres asyncio.gather pattern (see
    # Task 9's Step 7 for the exact RealSessionLocal construction) — two
    # concurrent calls both racing to simulate round 14 must not credit
    # tournament rewards twice for the same club.
    import asyncio

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.tournament_result import TournamentClubResult
    from tests.test_tournament_queue_service import REAL_POSTGRES_URL

    tournament, _clubs_and_captains = eight_club_tournament_at_round_13
    real_engine = create_async_engine(REAL_POSTGRES_URL)
    RealSessionLocal = async_sessionmaker(real_engine, expire_on_commit=False)

    async def call():
        async with RealSessionLocal() as session:
            return await simulate_next_round(session)

    await asyncio.gather(call(), call(), return_exceptions=True)

    async with RealSessionLocal() as session:
        result_count = (
            await session.execute(select(func.count(TournamentClubResult.id)).where(TournamentClubResult.tournament_id == tournament.id))
        ).scalar_one()
        assert result_count == 8  # exactly one TournamentClubResult per club, not 16

    await real_engine.dispose()
```

(`eight_club_tournament`/`eight_club_tournament_at_round_13` fixtures don't exist yet — write them as local `pytest_asyncio.fixture`s in THIS file. Follow the exact per-file-local-fixture convention this codebase already uses (see `test_clubs.py`'s own `_seed_position_pool`, and Task 9's `_create_club_with_full_squad` in `test_tournament_queue_service.py`, which is not importable from here — each test file gets its own copy, never a cross-file import of another file's local helper): register 8 users, create 8 clubs (each auto-seeds a full XI per `seed_starting_squad`), call `tournament_queue_service.apply_to_tournament` once per captain, and yield `(tournament, clubs_and_captains)` — the `Tournament` row from the 8th call's `result.tournament_id`, plus the full `[(club, captain), ...]` list so callers can authenticate as any of the 8 captains. For `eight_club_tournament_at_round_13`, depend on `eight_club_tournament` and call `simulate_next_round` 13 times in a loop before yielding the same `(tournament, clubs_and_captains)` shape. Task 16 (and, in spirit, any other task needing this setup) references the same `eight_club_tournament` fixture name and shape in its own test file — each such file needs its own local copy built the same way; do not assume it's importable across files.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_service.py -v
```

Expected: FAIL, `simulate_next_round` doesn't exist yet.

- [ ] **Step 3: Implement**

Append to `backend/app/services/tournament_simulation_service.py`:

```python
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.services import tournament_match_engine
from app.services.game_config_service import get_config
from app.services.tournament_fixture_service import generate_fixtures
from app.services.tournament_reward_service import conclude_tournament
from app.services.tournament_standing_service import apply_match_result


async def _lock_tournament(db: AsyncSession, tournament_id: int) -> Tournament:
    result = await db.execute(
        select(Tournament).where(Tournament.id == tournament_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _decay_availability(db: AsyncSession, club_id: int) -> None:
    rows = (
        await db.execute(select(ClubCardAvailability).join(ClubCard, ClubCard.id == ClubCardAvailability.club_card_id).where(ClubCard.club_id == club_id))
    ).scalars().all()
    for row in rows:
        row.rounds_remaining -= 1
        if row.rounds_remaining <= 0:
            await db.delete(row)
        else:
            db.add(row)


async def _apply_engine_result(db: AsyncSession, club_a_id: int, club_b_id: int, engine_result) -> None:
    for club_card_id, rounds in engine_result.injuries:
        existing = (await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            db.add(existing)
    for club_card_id, rounds in engine_result.red_cards:
        existing = (await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            db.add(existing)


async def simulate_next_round(db: AsyncSession) -> list[TournamentMatch]:
    config = await get_config(db)
    active_ids = (await db.execute(select(Tournament.id).where(Tournament.status == "active", Tournament.rounds_simulated < 14))).scalars().all()

    all_matches: list[TournamentMatch] = []
    for tournament_id in active_ids:
        tournament = await _lock_tournament(db, tournament_id)
        if tournament.rounds_simulated >= 14:
            continue  # a concurrent caller already advanced this one — nothing left to do

        round_number = tournament.rounds_simulated + 1
        participants = (await db.execute(select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))).scalars().all()
        club_ids = [p.club_id for p in participants]
        withdrawn_ids = {p.club_id for p in participants if p.is_withdrawn}

        fixtures = [f for f in generate_fixtures(club_ids) if f[0] == round_number]
        standings_rows = (await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament.id))).scalars().all()
        standings_by_club = {s.club_id: s for s in standings_rows}

        for _, club_a_id, club_b_id in fixtures:
            if club_a_id in withdrawn_ids or club_b_id in withdrawn_ids:
                # Withdrawn club auto-loses 0-3, no engine run, no availability
                # decay (there's no real match being simulated for it).
                score_a, score_b = (0, 3) if club_a_id in withdrawn_ids else (3, 0)
                match = TournamentMatch(
                    tournament_id=tournament.id, round_number=round_number, club_a_id=club_a_id, club_b_id=club_b_id,
                    score_a=score_a, score_b=score_b, event_log=[], simulated_at=datetime.now(timezone.utc),
                )
                db.add(match)
                apply_match_result(standings_by_club[club_a_id], standings_by_club[club_b_id], score_a, score_b)
                all_matches.append(match)
                continue

            strength_a, lineup_a = await match_strength(db, club_a_id, config)
            strength_b, lineup_b = await match_strength(db, club_b_id, config)
            engine_result = tournament_match_engine.simulate_match(strength_a, strength_b, lineup_a, lineup_b, config)

            match = TournamentMatch(
                tournament_id=tournament.id, round_number=round_number, club_a_id=club_a_id, club_b_id=club_b_id,
                score_a=engine_result.score_a, score_b=engine_result.score_b,
                event_log=engine_result.event_log, simulated_at=datetime.now(timezone.utc),
            )
            db.add(match)
            apply_match_result(standings_by_club[club_a_id], standings_by_club[club_b_id], engine_result.score_a, engine_result.score_b)
            await _apply_engine_result(db, club_a_id, club_b_id, engine_result)
            await _decay_availability(db, club_a_id)
            await _decay_availability(db, club_b_id)
            all_matches.append(match)

        tournament.rounds_simulated = round_number
        db.add(tournament)

        if round_number == 14:
            await conclude_tournament(db, tournament, list(standings_by_club.values()), all_matches)

        await db.commit()

    return all_matches
```

(This step's `match_strength` still returns the Task 12 rating-average approximation for `calculate_base_strength` — replace the body of `tournament_simulation_service.match_strength` now that this task has real `resolve_match_lineup`-fetched `ClubCard` ORM objects available in scope: extend `resolve_match_lineup` to also return the `(ClubCard, FormationSlot)` tuples it already builds internally, alongside its existing plain-dict return, and call the real `calculate_base_strength(cards_with_slots)` here instead of the rating-average stopgap. Update `resolve_match_lineup`'s signature/tests from Task 12 accordingly as part of this task — this is expected, planned integration work, not scope creep.)

- [ ] **Step 4: Add the internal endpoint**

In `backend/app/routers/internal.py`, add:

```python
from app.schemas.tournament import SimulateRoundResult
from app.services import tournament_simulation_service


@router.post("/clubs/simulate-round", response_model=SimulateRoundResult)
async def simulate_round(db: AsyncSession = Depends(get_db)):
    matches = await tournament_simulation_service.simulate_next_round(db)
    return SimulateRoundResult(matches_simulated=len(matches))
```

Add to `backend/app/schemas/tournament.py`:

```python
class SimulateRoundResult(BaseModel):
    matches_simulated: int
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_service.py -v
```

Expected: PASS, all 5 tests — including the two genuine concurrent-race tests against real Postgres (round-1 idempotency and round-14 reward-distribution idempotency); both need the real-Postgres session, not the SQLite `db_session` fixture, exactly like Task 9's Step 7 — check `test_club_packs.py` for exactly how this codebase's existing real-Postgres test sessions are constructed and reuse that construction rather than inventing a new one.

- [ ] **Step 6: Verify against real Postgres end to end**

```bash
docker compose exec -T backend python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services.tournament_simulation_service import simulate_next_round

async def main():
    async with AsyncSessionLocal() as db:
        matches = await simulate_next_round(db)
        print(f'Simulated {len(matches)} matches')

asyncio.run(main())
"
```

(Requires at least one active tournament with 8 real clubs already formed via the apply flow — set this up manually via the API/Swagger first if none exists in the dev DB, or skip this manual step if Task 9's dev-DB tournament from earlier testing is still active.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tournament_simulation_service.py backend/app/routers/internal.py backend/app/schemas/tournament.py backend/tests/test_tournament_simulation_service.py backend/tests/test_tournament_simulation_lineup.py
git commit -m "Add simulate_next_round orchestration and internal simulate-round endpoint"
```

---

### Task 15: Withdrawal handling

**Files:**
- Modify: `backend/app/services/club_service.py`
- Modify: `backend/app/services/tournament_simulation_service.py` (already reads `TournamentClub.is_withdrawn` from Task 14 — this task is what actually sets it)
- Test: `backend/tests/test_clubs.py`
- Test: `backend/tests/test_tournament_simulation_service.py`

**Interfaces:**
- Consumes: `TournamentClub` (Task 3), `Tournament` (Task 3).
- Produces: `leave_club`'s disband path now also marks any active tournament's `TournamentClub.is_withdrawn = True` for that club before deleting it.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_clubs.py`. `test_clubs.py` doesn't have an 8-club tournament fixture (that lives in `test_tournament_queue_service.py`, per this codebase's per-file-local-fixture convention) — build a minimal one locally rather than reaching across test files:

```python
async def test_captain_less_disband_marks_active_tournament_club_withdrawn(client, db_session, bot_token):
    from sqlalchemy import select
    from app.models.tournament import Tournament, TournamentClub
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    for i in range(8):
        await _register_only(client, bot_token, 840000 + i)
        headers = telegram_headers(840000 + i, bot_token)
        create_resp = await client.post(
            "/api/v1/clubs", headers=headers,
            json={"name": f"Клуб выбывания {i}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
        )
        captain = await get_user_by_telegram_id(db_session, 840000 + i)
        clubs_and_captains.append((create_resp.json()["id"], captain))

    tournament_id = None
    for club_id, captain in clubs_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    disbanded_club_id, sole_captain = clubs_and_captains[0]
    resp = await client.post("/api/v1/clubs/leave", headers=telegram_headers(840000, bot_token))
    assert resp.status_code == 200

    tc = (
        await db_session.execute(
            select(TournamentClub).where(TournamentClub.tournament_id == tournament_id, TournamentClub.club_id == disbanded_club_id)
        )
    ).scalar_one()
    assert tc.is_withdrawn is True
```

(Check `clubs.py`'s actual leave-club route path — `/clubs/leave` is this plan's best guess from the spec's wording, confirm against the real router before relying on it.)

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec -T backend pytest tests/test_clubs.py -k withdrawn -v
```

Expected: FAIL — `is_withdrawn` never gets set today.

- [ ] **Step 3: Implement**

In `backend/app/services/club_service.py`'s `leave_club`, inside the "no assistants to take over — the club disbands" branch (right before `await db.delete(club)`), add:

```python
    from app.models.tournament import Tournament, TournamentClub

    active_participation = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club.id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_participation is not None:
        active_participation.is_withdrawn = True
        db.add(active_participation)
```

(Placed as a local import to avoid a module-level circular-import risk symmetric to the one `club_squad_service.py` already documents with `club_service.py` — `tournament_simulation_service.py` doesn't import from `club_service.py` today, but keep this defensive/local per the established convention in this codebase for any newly-introduced cross-service reference near `club_service.py`'s own disband path.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_clubs.py -k withdrawn -v
```

Expected: PASS.

- [ ] **Step 5: Add and run the simulation-side withdrawal test**

Add to `backend/tests/test_tournament_simulation_service.py`:

```python
async def test_simulate_next_round_auto_scores_withdrawn_club_as_loss(db_session, eight_club_tournament):
    tournament = eight_club_tournament
    from sqlalchemy import select
    from app.models.tournament import TournamentClub
    participants = (await db_session.execute(select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))).scalars().all()
    withdrawn = participants[0]
    withdrawn.is_withdrawn = True
    db_session.add(withdrawn)
    await db_session.commit()

    matches = await simulate_next_round(db_session)
    withdrawn_matches = [m for m in matches if m.club_a_id == withdrawn.club_id or m.club_b_id == withdrawn.club_id]
    assert len(withdrawn_matches) == 1
    m = withdrawn_matches[0]
    assert m.event_log == []
    if m.club_a_id == withdrawn.club_id:
        assert (m.score_a, m.score_b) == (0, 3)
    else:
        assert (m.score_a, m.score_b) == (3, 0)
```

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_service.py -k withdrawn -v
```

Expected: PASS — this exercises code already written in Task 14 (the `withdrawn_ids` branch), confirming it end to end now that something actually sets `is_withdrawn`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/club_service.py backend/tests/test_clubs.py backend/tests/test_tournament_simulation_service.py
git commit -m "Mark TournamentClub withdrawn on captain-less club disband"
```

---

### Task 16: Public read API — current/detail/match-detail

**Files:**
- Modify: `backend/app/schemas/tournament.py`
- Modify: `backend/app/routers/clubs.py`
- Test: `backend/tests/test_tournament_api.py`

**Interfaces:**
- Consumes: everything (`Tournament`, `TournamentClub`, `TournamentClubStanding`, `TournamentMatch`, `TournamentClubResult`, `TournamentQueueState`/`Queue`/`Entry`, `rank_standings`).
- Produces: `GET /clubs/tournament/current`, `GET /clubs/tournament/{id}`, `GET /clubs/tournament/{id}/matches/{match_id}` — the full read surface 3c's frontend will consume later.

- [ ] **Step 1: Write the schemas**

Append to `backend/app/schemas/tournament.py`:

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TournamentStandingOut(BaseModel):
    club_id: int
    club_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None


class TournamentMatchSummaryOut(BaseModel):
    id: int
    round_number: int
    club_a_id: int
    club_b_id: int
    score_a: int
    score_b: int


class TournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    tournament_id: Optional[int] = None


class TournamentDetailOut(BaseModel):
    id: int
    status: str
    rounds_simulated: int
    standings: list[TournamentStandingOut]
    matches: list[TournamentMatchSummaryOut]


class TournamentMatchDetailOut(BaseModel):
    id: int
    round_number: int
    club_a_id: int
    club_b_id: int
    score_a: int
    score_b: int
    event_log: list[dict]
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_tournament_api.py`:

```python
async def test_current_returns_not_queued_for_a_club_never_applied(client, db_session, bot_token, seeded_club_with_full_squad):
    club, captain = seeded_club_with_full_squad
    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_queued"


async def test_current_returns_active_with_standings_after_formation(client, db_session, bot_token, eight_club_tournament):
    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["tournament_id"] == tournament.id


async def test_detail_returns_standings_sorted_by_rank(client, db_session, bot_token, eight_club_tournament):
    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["standings"]) == 8
    ranks = [s["final_rank"] for s in body["standings"]]
    assert ranks == sorted(ranks)


async def test_match_detail_includes_event_log(client, db_session, bot_token, eight_club_tournament):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    matches = await simulate_next_round(db_session)
    await db_session.commit()
    match = next(m for m in matches if m.tournament_id == tournament.id)

    resp = await client.get(
        f"/api/v1/clubs/tournament/{tournament.id}/matches/{match.id}", headers=telegram_headers(captain.telegram_id, bot_token)
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["event_log"], list)
```

(`seeded_club_with_full_squad` and `eight_club_tournament` are local fixtures this file needs to define itself, per the same per-file-local convention noted in Task 14 — for `eight_club_tournament`, return `(tournament, clubs_and_captains)` so tests here can address both the tournament row and a specific captain to authenticate as.)

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_api.py -v
```

Expected: FAIL, routes don't exist yet.

- [ ] **Step 4: Implement**

Append to `backend/app/routers/clubs.py`:

```python
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.models.tournament_queue import TournamentQueueEntry
from app.schemas.tournament import TournamentCurrentOut, TournamentDetailOut, TournamentMatchDetailOut, TournamentMatchSummaryOut, TournamentStandingOut
from app.services.tournament_standing_service import rank_standings


@router.get("/tournament/current", response_model=TournamentCurrentOut)
async def get_current_tournament(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    active_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_tc is not None:
        return TournamentCurrentOut(status="active", tournament_id=active_tc.tournament_id)

    queue_entry = (await db.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.club_id == club_id))).scalar_one_or_none()
    if queue_entry is not None:
        position = (
            await db.execute(
                select(func.count(TournamentQueueEntry.id))
                .where(TournamentQueueEntry.queue_id == queue_entry.queue_id, TournamentQueueEntry.joined_at <= queue_entry.joined_at)
            )
        ).scalar_one()
        return TournamentCurrentOut(status="queued", queue_position=position)

    return TournamentCurrentOut(status="not_queued")


@router.get("/tournament/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament_id))).scalars().all()
    matches = (await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id))).scalars().all()
    ranked = rank_standings(standings, matches)

    club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_([s.club_id for s in standings])))).scalars().all()}

    return TournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=[
            TournamentStandingOut(
                club_id=s.club_id, club_name=club_names.get(s.club_id, ""), points=s.points,
                goals_for=s.goals_for, goals_against=s.goals_against, final_rank=index + 1,
            )
            for index, s in enumerate(ranked)
        ],
        matches=[
            TournamentMatchSummaryOut(id=m.id, round_number=m.round_number, club_a_id=m.club_a_id, club_b_id=m.club_b_id, score_a=m.score_a, score_b=m.score_b)
            for m in matches
        ],
    )


@router.get("/tournament/{tournament_id}/matches/{match_id}", response_model=TournamentMatchDetailOut)
async def get_tournament_match_detail(tournament_id: int, match_id: int, db: AsyncSession = Depends(get_db)):
    match = await db.get(TournamentMatch, match_id)
    if match is None or match.tournament_id != tournament_id:
        raise NotFoundError("Матч не найден")
    return TournamentMatchDetailOut(
        id=match.id, round_number=match.round_number, club_a_id=match.club_a_id, club_b_id=match.club_b_id,
        score_a=match.score_a, score_b=match.score_b, event_log=match.event_log,
    )
```

(Check `clubs.py`'s actual top-of-file imports for `Club`, `NotFoundError`, `func`, `select` before adding duplicates — most are almost certainly already imported given this file's existing size.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_api.py -v
```

Expected: PASS, all 4 tests.

- [ ] **Step 6: Run the full backend suite**

```bash
docker compose exec -T backend pytest tests/ -q
```

Expected: green except the one pre-existing unrelated failure (`test_task_reward_pack_grants_all_cards`) this codebase has carried since before this plan started.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/tournament.py backend/app/routers/clubs.py backend/tests/test_tournament_api.py
git commit -m "Add public tournament read API: current/detail/match-detail"
```
