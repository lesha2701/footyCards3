# Coach Cards — Phase 1 (Shared Foundations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** introduce the `Coach` card archetype end to end at the data/admin
layer — model, migration, boost-dispatch service (unit-tested but not yet
wired into any match engine), and admin CRUD — with zero user-facing
change and zero acquisition path yet.

**Architecture:** `Coach`/`CoachBoost` mirror `Player`'s existing shape
minus position/attack-defense/collection fields, in their own new files
(not reusing `Player`, so nothing accidentally inherits diamond-upgrade or
position-fit logic). A new `coach_boost_service.py` implements the boost
dispatch functions the match engines will call in a later phase, taking
their inputs as plain parameters (never importing from
`club_tactical_profile_service.py`/`club_tactical_matchup_service.py`, to
keep the import direction one-way and avoid a future circular import once
those services start calling *into* this one). Admin CRUD mirrors
`admin_players.py`/`AdminPlayersPage.tsx` closely enough that an admin
familiar with managing players needs no new mental model.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, Pydantic v2, pytest
(async, in-memory SQLite), React 18 + TypeScript + TanStack Query +
Tailwind.

**Spec:** `docs/superpowers/specs/2026-09-08-coach-cards-design.md` — this
plan implements §3 (data model), §6 (boost dispatch layer), and the admin
half of §9, per §13's "Phase 1 — shared foundations" scope.

## Global Constraints

- Coach rarity is capped at `legendary` — enforced by a DB `CheckConstraint`
  on the `coaches` table, not only admin-form validation (spec §3).
- A `CoachBoost`'s `(coach_id, boost_type)` pair is unique — a DB
  `UniqueConstraint`, not only app-level checking (spec §3).
- Boost slot count vs. rarity: common/rare → 1 boost, epic → 2, legendary →
  3, and every boost on one coach must be a distinct `CoachBoostType`
  (spec §4) — enforced in the Pydantic schema layer (a clean 422, not a
  raw `IntegrityError`).
- `CoachBoost.magnitude` in this phase is **whatever the admin types in**
  (a sane `Field` bound to catch fat-fingering only) — the spec §4
  base-unit table is tuning *guidance* for the admin, not a formula this
  phase computes or enforces. No match engine reads this value yet.
- No new `GameConfig` fields anywhere in this phase (spec §10).
- No match-engine wiring, no `ClubLineup`/`Lineup` changes, no pack/
  acquisition system, no equip endpoint — all later phases (spec §13).
  `coach_boost_service.py`'s functions are built and unit-tested in
  isolation; nothing calls them from `club_tactical_profile_service.py`,
  `club_tactical_matchup_service.py`, or `match_service.py` yet.
- Every behavior change gets a test (repo `CLAUDE.md` Definition of Done).
- Alembic revision numbers are sequential off whatever HEAD actually is
  when Task 1 runs — confirmed at spec-writing time to be `0089` (`ls
  backend/alembic/versions | sort | tail -3`), but re-check this at
  execution time rather than assuming `0090` is still free.
- This repo's standing rule (`CLAUDE.md`): do not commit or push beyond
  what's needed to complete each task's own step — no unrelated
  refactoring, no `git add -A`/`git add .`.

---

### Task 1: `Coach`/`CoachBoost` models, migration, model registration

**Files:**
- Modify: `backend/app/models/enums.py` (add `CoachBoostType`)
- Create: `backend/app/models/coach.py`
- Modify: `backend/app/models/__init__.py` (register the new models)
- Create: `backend/alembic/versions/00NN_coach_cards.py` (exact number per
  Global Constraints — check HEAD before naming this file)
- Test: `backend/tests/test_coach_models.py`

**Interfaces:**
- Produces: `Coach` (columns: `id`, `display_name: str`, `rarity: Rarity`,
  `image_path: str | None`, `quick_sell_price: int`, `is_active: bool`,
  `is_pack_droppable: bool`, `next_serial_number: int`,
  `next_club_serial_number: int`, `boosts: list[CoachBoost]` relationship),
  `CoachBoost` (columns: `id`, `coach_id: int`, `boost_type:
  CoachBoostType`, `magnitude: float`), `CoachBoostType` enum with exactly
  these 11 members: `ATTACK_CENTRAL`, `ATTACK_WING`, `MIDFIELD_CONTROL`,
  `DEFENCE_CENTRAL`, `DEFENCE_WING`, `GOALKEEPING`, `PASSING_ACCURACY`,
  `BALL_CONTROL`, `DEFENSIVE_DISCIPLINE`, `COUNTER_MASTERY`,
  `SQUAD_STABILITY`. Later tasks import `Coach`/`CoachBoost`/
  `CoachBoostType` from `app.models.coach`/`app.models.enums` respectively.

- [ ] **Step 1: Add `CoachBoostType` to `enums.py`**

Open `backend/app/models/enums.py` and find the existing `Rarity` class
(it starts `class Rarity(str, enum.Enum):`, confirming `enum` is already
imported at the top of this file). Add this new enum directly after the
`Rarity`/`RARITY_ORDER` block:

```python
class CoachBoostType(str, enum.Enum):
    ATTACK_CENTRAL = "attack_central"
    ATTACK_WING = "attack_wing"
    MIDFIELD_CONTROL = "midfield_control"
    DEFENCE_CENTRAL = "defence_central"
    DEFENCE_WING = "defence_wing"
    GOALKEEPING = "goalkeeping"
    PASSING_ACCURACY = "passing_accuracy"
    BALL_CONTROL = "ball_control"
    DEFENSIVE_DISCIPLINE = "defensive_discipline"
    COUNTER_MASTERY = "counter_mastery"
    SQUAD_STABILITY = "squad_stability"
```

- [ ] **Step 2: Write the failing model test**

Create `backend/tests/test_coach_models.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity


async def test_coach_with_boosts_persists(db_session):
    coach = Coach(display_name="Test Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.SQUAD_STABILITY, magnitude=2.0),
    ]
    db_session.add(coach)
    await db_session.commit()
    await db_session.refresh(coach)

    assert coach.id is not None
    assert len(coach.boosts) == 3
    assert coach.is_active is True
    assert coach.is_pack_droppable is True


async def test_coach_rarity_cannot_be_diamond(db_session):
    coach = Coach(display_name="Illegal Diamond Coach", rarity=Rarity.diamond)
    db_session.add(coach)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coach_boost_type_unique_per_coach(db_session):
    coach = Coach(display_name="Duplicate Boost Coach", rarity=Rarity.common)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=2.0),
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=3.0),
    ]
    db_session.add(coach)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_coach_cascades_to_boosts(db_session):
    coach = Coach(display_name="Deletable Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=4.0)]
    db_session.add(coach)
    await db_session.commit()
    coach_id = coach.id

    await db_session.delete(coach)
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(CoachBoost).where(CoachBoost.coach_id == coach_id))
    assert result.scalars().all() == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_coach_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.coach'`.

- [ ] **Step 4: Create `backend/app/models/coach.py`**

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CoachBoostType, Rarity
from app.models.mixins import TimestampMixin


class Coach(TimestampMixin, Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False, index=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_sell_price: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Separate from is_active, same convention as Player.is_pack_droppable:
    # a coach can stay active (visible, usable) while excluded from new
    # pack drops once a coach pack exists in a later phase.
    is_pack_droppable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Unused until the pack/acquisition phases exist — reserved now so the
    # migration that introduces UserCoachCard/ClubCoachCard doesn't also
    # need to alter this table. Mirrors Player.next_serial_number's own
    # atomic-per-template-serial pattern (services/card_creation.py).
    next_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_club_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    boosts: Mapped[list["CoachBoost"]] = relationship(back_populates="coach", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("rarity != 'diamond'", name="ck_coaches_rarity_not_diamond"),
    )


class CoachBoost(Base):
    __tablename__ = "coach_boosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id", ondelete="CASCADE"), nullable=False, index=True)
    boost_type: Mapped[CoachBoostType] = mapped_column(Enum(CoachBoostType, name="coach_boost_type_enum"), nullable=False)
    magnitude: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    coach: Mapped["Coach"] = relationship(back_populates="boosts")

    __table_args__ = (
        UniqueConstraint("coach_id", "boost_type", name="uq_coach_boost_type_once"),
    )
```

`TimestampMixin` (already used by `Player`) supplies `created_at`/
`updated_at` — confirm this by checking `backend/app/models/mixins.py`
before writing this file if the exact columns it adds matter to you; it's
already proven safe since `Player` uses the identical mixin.

- [ ] **Step 5: Register the new models in `app/models/__init__.py`**

Open `backend/app/models/__init__.py` and add, in alphabetical position
next to the other `c`-prefixed imports (e.g. near `from app.models.club_card
import ClubCard` and `from app.models.coin_package import CoinPackage`):

```python
from app.models.coach import Coach, CoachBoost
```

- [ ] **Step 6: Run the tests to verify they still fail (model exists, table doesn't)**

Run: `cd backend && pytest tests/test_coach_models.py -v`
Expected: FAIL now with a table-not-found / `OperationalError` — this
confirms the model imports cleanly and the remaining gap is the missing
table, i.e. `Base.metadata` now knows about `Coach`/`CoachBoost` (test DB
setup uses `Base.metadata.create_all`, `backend/tests/conftest.py:40`, so
this test failure mode should flip to PASS as soon as `create_all` runs
against a session that includes these new model imports — if it already
passes at this step instead of failing, that's fine too, since
`conftest.py` imports `app.models` wholesale and `create_all` doesn't need
the Alembic migration to exist for the SQLite test DB).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_coach_models.py -v`
Expected: PASS (4 passed) — the SQLite test database is built via
`Base.metadata.create_all`, so the model alone is enough for these tests;
the Alembic migration below is what makes the same tables exist in real
Postgres.

- [ ] **Step 8: Write the Alembic migration**

Check the current head first: `ls backend/alembic/versions | sort | tail -3`
— name this file `00NN_coach_cards.py` where `NN` is one past whatever
that shows (this plan was written against head `0089`, but confirm before
naming). Set `down_revision` to that head's own revision string.

```python
"""Coach, CoachBoost

Revision ID: 00NN
Revises: 0089
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "00NN"
down_revision = "0089"
branch_labels = None
depends_on = None

# rarity_enum already exists (created in 0001_initial, extended with
# "diamond" in 0083_diamond_rarity) — reuse it, don't re-declare, or
# Postgres will try to CREATE TYPE again and fail.
rarity_enum = postgresql.ENUM(
    "common", "rare", "epic", "legendary", "diamond", name="rarity_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "coaches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("quick_sell_price", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_club_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rarity != 'diamond'", name="ck_coaches_rarity_not_diamond"),
    )
    op.create_index("ix_coaches_display_name", "coaches", ["display_name"])
    op.create_index("ix_coaches_rarity", "coaches", ["rarity"])

    coach_boost_type_enum = sa.Enum(
        "attack_central", "attack_wing", "midfield_control", "defence_central", "defence_wing",
        "goalkeeping", "passing_accuracy", "ball_control", "defensive_discipline", "counter_mastery",
        "squad_stability", name="coach_boost_type_enum",
    )
    op.create_table(
        "coach_boosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("boost_type", coach_boost_type_enum, nullable=False),
        sa.Column("magnitude", sa.Numeric(6, 3), nullable=False),
        sa.UniqueConstraint("coach_id", "boost_type", name="uq_coach_boost_type_once"),
    )
    op.create_index("ix_coach_boosts_coach_id", "coach_boosts", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_coach_boosts_coach_id", table_name="coach_boosts")
    op.drop_table("coach_boosts")
    bind = op.get_bind()
    sa.Enum(name="coach_boost_type_enum").drop(bind, checkfirst=True)
    op.drop_index("ix_coaches_rarity", table_name="coaches")
    op.drop_index("ix_coaches_display_name", table_name="coaches")
    op.drop_table("coaches")
```

- [ ] **Step 9: Apply the migration against real Postgres**

Run (from the repo root, with `docker compose` up):
```bash
docker compose exec backend alembic upgrade head
```
Expected: no errors; `docker compose exec postgres psql -U postgres -d
footycards -c "\d coaches"` and `"\d coach_boosts"` show the new tables
with the constraints from Step 8.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/coach.py backend/app/models/__init__.py backend/alembic/versions/00NN_coach_cards.py backend/tests/test_coach_models.py
git commit -m "feat(coaches): add Coach/CoachBoost models and migration"
```

---

### Task 2: Pydantic schemas with rarity/boost-count validation

**Files:**
- Create: `backend/app/schemas/coach.py`
- Test: `backend/tests/test_coach_schemas.py`

**Interfaces:**
- Consumes: `Coach`, `CoachBoost`, `CoachBoostType` (Task 1).
- Produces: `CoachBoostOut`, `CoachBoostCreate`, `CoachOut`, `CoachCreate`,
  `CoachUpdate` — `CoachCreate`/`CoachUpdate` both carry `boosts:
  list[CoachBoostCreate]` and raise a Pydantic validation error (not just
  a DB error) when the boost count/distinctness doesn't match the coach's
  own `rarity` per the Global Constraints table. Later tasks import all
  five from `app.schemas.coach`.

- [ ] **Step 1: Write the failing schema tests**

Create `backend/tests/test_coach_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachBoostCreate, CoachCreate


def _boost(boost_type: CoachBoostType, magnitude: float = 2.0) -> CoachBoostCreate:
    return CoachBoostCreate(boost_type=boost_type, magnitude=magnitude)


def test_legendary_coach_needs_exactly_three_distinct_boosts():
    payload = CoachCreate(
        display_name="Legendary Coach", rarity=Rarity.legendary,
        boosts=[
            _boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL), _boost(CoachBoostType.GOALKEEPING),
        ],
    )
    assert len(payload.boosts) == 3


def test_legendary_coach_with_two_boosts_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Under-boosted Legendary", rarity=Rarity.legendary,
            boosts=[_boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL)],
        )


def test_epic_coach_with_three_boosts_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Over-boosted Epic", rarity=Rarity.epic,
            boosts=[
                _boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL), _boost(CoachBoostType.GOALKEEPING),
            ],
        )


def test_common_coach_needs_exactly_one_boost():
    payload = CoachCreate(display_name="Common Coach", rarity=Rarity.common, boosts=[_boost(CoachBoostType.PASSING_ACCURACY)])
    assert len(payload.boosts) == 1


def test_duplicate_boost_type_on_one_coach_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Duplicate Boost Coach", rarity=Rarity.rare,
            boosts=[_boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.ATTACK_CENTRAL, magnitude=3.0)],
        )


def test_diamond_rarity_is_rejected_at_the_schema_layer():
    with pytest.raises(ValidationError):
        CoachCreate(display_name="Illegal Diamond", rarity=Rarity.diamond, boosts=[_boost(CoachBoostType.ATTACK_CENTRAL)])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_coach_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.coach'`.

- [ ] **Step 3: Create `backend/app/schemas/coach.py`**

```python
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CoachBoostType, Rarity

# Spec §4's rarity -> required boost count. A coach must have EXACTLY this
# many boosts, all of distinct CoachBoostType — not "up to N", since a
# coach with fewer boosts than its rarity allows would just be a worse
# version of a lower rarity, which is confusing rather than a deliberate
# design choice this admin tool should allow by accident.
BOOST_SLOTS_BY_RARITY: dict[Rarity, int] = {
    Rarity.common: 1,
    Rarity.rare: 1,
    Rarity.epic: 2,
    Rarity.legendary: 3,
}


class CoachBoostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    boost_type: CoachBoostType
    magnitude: float


class CoachBoostCreate(BaseModel):
    boost_type: CoachBoostType
    # Sane fat-finger guard only in this phase — see this plan's Global
    # Constraints: the real tuned magnitude table (spec §4) isn't enforced
    # here, since nothing reads this value yet.
    magnitude: float = Field(ge=-1.0, le=20.0)


def _validate_boosts(rarity: Rarity, boosts: list[CoachBoostCreate]) -> list[CoachBoostCreate]:
    if rarity not in BOOST_SLOTS_BY_RARITY:
        raise ValueError(f"Coach rarity must be one of {list(BOOST_SLOTS_BY_RARITY)}, got {rarity}")
    required = BOOST_SLOTS_BY_RARITY[rarity]
    if len(boosts) != required:
        raise ValueError(f"{rarity.value} coaches must have exactly {required} boost(s), got {len(boosts)}")
    types = [b.boost_type for b in boosts]
    if len(set(types)) != len(types):
        raise ValueError("A coach cannot have the same boost_type twice")
    return boosts


class CoachOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rarity: Rarity
    image_path: Optional[str]
    quick_sell_price: int
    is_active: bool
    is_pack_droppable: bool
    boosts: list[CoachBoostOut]


class CoachCreate(BaseModel):
    display_name: str
    rarity: Rarity
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True
    is_pack_droppable: bool = True
    boosts: list[CoachBoostCreate]

    @model_validator(mode="after")
    def _check_boosts(self) -> "CoachCreate":
        _validate_boosts(self.rarity, self.boosts)
        return self


class CoachUpdate(BaseModel):
    display_name: Optional[str] = None
    rarity: Optional[Rarity] = None
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    is_pack_droppable: Optional[bool] = None
    boosts: Optional[list[CoachBoostCreate]] = None

    @model_validator(mode="after")
    def _check_boosts(self) -> "CoachUpdate":
        # Only validate the rarity/boost-count pairing when BOTH are being
        # set together — partial updates (e.g. just toggling is_active)
        # must not require re-submitting the boost list every time.
        if self.rarity is not None and self.boosts is not None:
            _validate_boosts(self.rarity, self.boosts)
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_coach_schemas.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/coach.py backend/tests/test_coach_schemas.py
git commit -m "feat(coaches): add Coach schemas with rarity/boost validation"
```

---

### Task 3: `save_coach_image`/`delete_coach_image` + `coach_service.py`

**Files:**
- Modify: `backend/app/services/image_service.py`
- Create: `backend/app/services/coach_service.py`
- Test: `backend/tests/test_coach_service.py`

**Interfaces:**
- Consumes: `Coach`, `CoachBoost` (Task 1); `CoachCreate`, `CoachUpdate`
  (Task 2).
- Produces: `save_coach_image(upload: UploadFile, rarity: Rarity,
  display_name: str) -> str`, `delete_coach_image(relative_path: str |
  None) -> None` in `image_service.py`; `create_coach(db: AsyncSession,
  payload: CoachCreate) -> Coach` and `update_coach(db: AsyncSession,
  coach_id: int, payload: CoachUpdate) -> Coach` (raises `NotFoundError`
  for a missing id) in `coach_service.py`. Task 4's router calls these.

- [ ] **Step 1: Add `save_coach_image`/`delete_coach_image`**

Open `backend/app/services/image_service.py`. Add a new directory constant
next to the existing ones (`PLAYERS_DIR`, etc.):

```python
COACHES_DIR = STATIC_DIR / "coaches"
```

Then add these two functions, placed after `delete_player_image` — a
direct copy of `save_player_image`/`delete_player_image` (lines already
read this session) with `PLAYERS_DIR`/`"players/"` swapped for
`COACHES_DIR`/`"coaches/"`:

```python
async def save_coach_image(upload: UploadFile, rarity: Rarity, display_name: str) -> str:
    """Validates and stores an uploaded coach image; returns the DB-stored relative path."""
    if not upload.filename or "." not in upload.filename:
        raise AppError("invalid_file", "File has no extension", 400)

    extension = upload.filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError("invalid_file_type", f"Extension .{extension} is not allowed", 400)
    if upload.content_type and upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise AppError("invalid_file_type", f"Content-Type {upload.content_type} is not allowed", 400)

    contents = await upload.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise AppError("file_too_large", f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit", 400)
    if len(contents) == 0:
        raise AppError("invalid_file", "Uploaded file is empty", 400)

    target_dir = COACHES_DIR / rarity.value
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = _sanitize_filename(display_name, extension)
    target_path = target_dir / filename
    target_path.write_bytes(contents)

    return f"coaches/{rarity.value}/{filename}"


def delete_coach_image(relative_path: str | None) -> None:
    if not relative_path:
        return
    full_path = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() in full_path.parents and full_path.is_file():
        full_path.unlink(missing_ok=True)
```

- [ ] **Step 2: Write the failing service tests**

Create `backend/tests/test_coach_service.py`:

```python
import pytest

from app.core.exceptions import NotFoundError
from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachBoostCreate, CoachCreate, CoachUpdate
from app.services.coach_service import create_coach, update_coach


async def test_create_coach_persists_boosts(db_session):
    payload = CoachCreate(
        display_name="Service Test Coach", rarity=Rarity.epic,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=4.0),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING, magnitude=4.0),
        ],
    )
    coach = await create_coach(db_session, payload)
    assert coach.id is not None
    assert {b.boost_type for b in coach.boosts} == {CoachBoostType.ATTACK_WING, CoachBoostType.DEFENCE_WING}


async def test_update_coach_replaces_all_boosts(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Replaceable Coach", rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)],
    ))

    updated = await update_coach(db_session, created.id, CoachUpdate(
        rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.PASSING_ACCURACY, magnitude=2.0)],
    ))

    assert len(updated.boosts) == 1
    assert updated.boosts[0].boost_type == CoachBoostType.PASSING_ACCURACY


async def test_update_coach_without_boosts_leaves_them_untouched(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Partial Update Coach", rarity=Rarity.rare,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.BALL_CONTROL, magnitude=1.0)],
    ))

    updated = await update_coach(db_session, created.id, CoachUpdate(is_active=False))

    assert updated.is_active is False
    assert len(updated.boosts) == 1
    assert updated.boosts[0].boost_type == CoachBoostType.BALL_CONTROL


async def test_update_missing_coach_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        await update_coach(db_session, 999999, CoachUpdate(is_active=False))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_coach_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.coach_service'`.

- [ ] **Step 4: Create `backend/app/services/coach_service.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.coach import Coach, CoachBoost
from app.schemas.coach import CoachCreate, CoachUpdate


async def _get_coach_or_404(db: AsyncSession, coach_id: int) -> Coach:
    coach = await db.get(Coach, coach_id)
    if not coach:
        raise NotFoundError("Coach not found")
    return coach


async def create_coach(db: AsyncSession, payload: CoachCreate) -> Coach:
    data = payload.model_dump(exclude={"boosts"})
    coach = Coach(**data)
    coach.boosts = [CoachBoost(boost_type=b.boost_type, magnitude=b.magnitude) for b in payload.boosts]
    db.add(coach)
    await db.flush()
    await db.refresh(coach, attribute_names=["boosts"])
    return coach


async def update_coach(db: AsyncSession, coach_id: int, payload: CoachUpdate) -> Coach:
    coach = await _get_coach_or_404(db, coach_id)
    updates = payload.model_dump(exclude_unset=True, exclude={"boosts"})
    for key, value in updates.items():
        setattr(coach, key, value)

    if payload.boosts is not None:
        # Replace-all: simplest correct semantics for "up to 3 rows" in an
        # admin-only phase — no per-boost PATCH exists yet.
        coach.boosts = [CoachBoost(boost_type=b.boost_type, magnitude=b.magnitude) for b in payload.boosts]

    db.add(coach)
    await db.flush()
    await db.refresh(coach, attribute_names=["boosts"])
    return coach
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_coach_service.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/image_service.py backend/app/services/coach_service.py backend/tests/test_coach_service.py
git commit -m "feat(coaches): add coach image upload and create/update service"
```

---

### Task 4: `admin_coaches.py` router + registration

**Files:**
- Create: `backend/app/routers/admin_coaches.py`
- Modify: `backend/app/main.py` (import + `include_router`)
- Test: `backend/tests/test_admin_coaches.py`

**Interfaces:**
- Consumes: `create_coach`/`update_coach` (Task 3), `CoachOut`/`CoachCreate`/
  `CoachUpdate` (Task 2), `Coach` (Task 1).
- Produces: `GET /admin/coaches`, `POST /admin/coaches`, `PUT
  /admin/coaches/{id}`, `POST /admin/coaches/{id}/toggle-active`, `POST
  /admin/coaches/{id}/toggle-pack-droppable`, `DELETE /admin/coaches/{id}`,
  `POST /admin/coaches/{id}/image`, `DELETE /admin/coaches/{id}/image` —
  Task 6/7 (frontend) call these exact paths.

- [ ] **Step 1: Write the failing router tests**

Create `backend/tests/test_admin_coaches.py`:

```python
from tests.utils import telegram_headers


async def _admin_token(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    resp = await client.post("/api/v1/auth/session", headers=headers)
    return resp.json()["admin_token"]


async def test_admin_coaches_routes_reject_missing_token(client):
    resp = await client.get("/api/v1/admin/coaches")
    assert resp.status_code == 401


async def test_admin_can_create_list_and_update_coach(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={
            "display_name": "Пеп Хренандес", "rarity": "legendary", "quick_sell_price": 50,
            "boosts": [
                {"boost_type": "attack_central", "magnitude": 6.0},
                {"boost_type": "defence_central", "magnitude": 6.0},
                {"boost_type": "goalkeeping", "magnitude": 4.0},
            ],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    coach_id = create_resp.json()["id"]
    assert len(create_resp.json()["boosts"]) == 3

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    assert list_resp.status_code == 200
    assert any(c["id"] == coach_id for c in list_resp.json()["items"])

    update_resp = await client.put(
        f"/api/v1/admin/coaches/{coach_id}", headers=auth, json={"display_name": "Пеп Хренандес II"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["display_name"] == "Пеп Хренандес II"
    assert len(update_resp.json()["boosts"]) == 3  # untouched by the partial update


async def test_create_coach_rejects_bad_rarity_boost_count(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/coaches", headers={"Authorization": f"Bearer {token}"},
        json={
            "display_name": "Under-boosted", "rarity": "legendary",
            "boosts": [{"boost_type": "attack_central", "magnitude": 4.0}],
        },
    )
    assert resp.status_code == 422


async def test_toggle_active_and_delete_coach(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={"display_name": "Togglable Coach", "rarity": "common", "boosts": [{"boost_type": "ball_control", "magnitude": 1.0}]},
    )
    coach_id = create_resp.json()["id"]

    toggle_resp = await client.post(f"/api/v1/admin/coaches/{coach_id}/toggle-active", headers=auth)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/admin/coaches/{coach_id}", headers=auth)
    assert delete_resp.status_code == 200

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    assert all(c["id"] != coach_id for c in list_resp.json()["items"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_admin_coaches.py -v`
Expected: FAIL — `404 Not Found` for every request (router doesn't exist/
isn't registered yet).

- [ ] **Step 3: Create `backend/app/routers/admin_coaches.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.coach import Coach
from app.models.user import User
from app.schemas.coach import CoachCreate, CoachOut, CoachUpdate
from app.services.admin_log_service import log_action
from app.services.coach_service import _get_coach_or_404, create_coach, update_coach
from app.services.image_service import delete_coach_image, save_coach_image

router = APIRouter(prefix="/admin/coaches", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[CoachOut])
async def list_all_coaches(
    search: Optional[str] = None,
    include_inactive: bool = True,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    query = select(Coach)
    count_query = select(func.count(Coach.id))
    if not include_inactive:
        query = query.where(Coach.is_active.is_(True))
        count_query = count_query.where(Coach.is_active.is_(True))
    if search:
        query = query.where(Coach.display_name.ilike(f"%{search}%"))
        count_query = count_query.where(Coach.display_name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Coach.id.desc()).offset(params.offset).limit(params.page_size)
    coaches = (await db.execute(query)).unique().scalars().all()
    return Page.build([CoachOut.model_validate(c) for c in coaches], total, params)


@router.post("", response_model=CoachOut)
async def create_coach_route(
    payload: CoachCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    coach = await create_coach(db, payload)
    await log_action(
        db, admin.id, "create_coach", "coach", coach.id, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.put("/{coach_id}", response_model=CoachOut)
async def update_coach_route(
    coach_id: int, payload: CoachUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    old_value = CoachOut.model_validate(await _get_coach_or_404(db, coach_id)).model_dump(mode="json")
    coach = await update_coach(db, coach_id, payload)
    await log_action(
        db, admin.id, "update_coach", "coach", coach_id, old_value=old_value,
        new_value=payload.model_dump(exclude_unset=True, mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.post("/{coach_id}/toggle-active", response_model=CoachOut)
async def toggle_active(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await _get_coach_or_404(db, coach_id)
    coach.is_active = not coach.is_active
    db.add(coach)
    await log_action(
        db, admin.id, "toggle_coach_active", "coach", coach_id, new_value={"is_active": coach.is_active},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.post("/{coach_id}/toggle-pack-droppable", response_model=CoachOut)
async def toggle_pack_droppable(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await _get_coach_or_404(db, coach_id)
    coach.is_pack_droppable = not coach.is_pack_droppable
    db.add(coach)
    await log_action(
        db, admin.id, "toggle_coach_pack_droppable", "coach", coach_id,
        new_value={"is_pack_droppable": coach.is_pack_droppable}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.delete("/{coach_id}")
async def delete_coach(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await _get_coach_or_404(db, coach_id)
    # No FK-guard against owned copies yet (UserCoachCard/ClubCoachCard
    # don't exist until a later phase) — unlike delete_player's card_count
    # check, deleting a coach in this phase is unconditional. A later
    # phase MUST add an equivalent guard once those tables exist.
    delete_coach_image(coach.image_path)
    await log_action(
        db, admin.id, "delete_coach", "coach", coach_id, old_value={"display_name": coach.display_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(coach)
    await db.commit()
    return {"status": "ok"}


@router.post("/{coach_id}/image", response_model=CoachOut)
async def upload_image(coach_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await _get_coach_or_404(db, coach_id)
    old_path = coach.image_path
    new_path = await save_coach_image(file, coach.rarity, coach.display_name)
    coach.image_path = new_path
    db.add(coach)
    if old_path:
        delete_coach_image(old_path)
    await log_action(
        db, admin.id, "upload_coach_image", "coach", coach_id, old_value={"image_path": old_path},
        new_value={"image_path": new_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.delete("/{coach_id}/image", response_model=CoachOut)
async def remove_image(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await _get_coach_or_404(db, coach_id)
    old_path = coach.image_path
    delete_coach_image(old_path)
    coach.image_path = None
    db.add(coach)
    await log_action(
        db, admin.id, "delete_coach_image", "coach", coach_id, old_value={"image_path": old_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)
```

`_get_coach_or_404` is imported from `coach_service.py` despite its
leading underscore — it's private to that module's own callers by
convention, but the router needs the exact same lookup-or-404 behavior for
`update_coach_route`'s `old_value` snapshot and the toggle/delete/image
routes, and duplicating it would drift. If this feels wrong at review
time, promoting it to a public `get_coach_or_404` (no underscore) in
`coach_service.py` is a one-line rename — either is fine, but pick one and
keep it consistent with how `admin_players.py` keeps its own
`_get_player_or_404` local instead (a real inconsistency between the two
routers that this task's reviewer should flag either way, not silently
copy forward).

- [ ] **Step 4: Register the router in `main.py`**

Open `backend/app/main.py`. Add `admin_coaches` to the router-module import
list (alphabetical, near `admin_players`) and add, near
`app.include_router(admin_players.router, prefix=API_PREFIX)`:

```python
app.include_router(admin_coaches.router, prefix=API_PREFIX)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_admin_coaches.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest tests/ -v`
Expected: PASS, except any pre-existing unrelated failure already known
from this session's other work on this codebase (if you see exactly one
failure in `tests/test_tasks.py::test_task_reward_pack_grants_all_cards`,
that is pre-existing and unrelated to this plan — confirm by checking it
also fails on a `git stash` of this task's changes before assuming it's
safe to ignore).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/admin_coaches.py backend/app/main.py backend/tests/test_admin_coaches.py
git commit -m "feat(coaches): add admin CRUD endpoints for coaches"
```

---

### Task 5: `coach_boost_service.py` — dispatch layer + unit tests

**Files:**
- Create: `backend/app/services/coach_boost_service.py`
- Test: `backend/tests/test_coach_boost_service.py`

**Interfaces:**
- Consumes: `Coach`, `CoachBoost`, `CoachBoostType` (Task 1).
- Produces: `ActiveCoachBoosts` (frozen dataclass), `resolve_active_boosts`,
  `apply_zone_boosts`, `depth_bonus_cap_for`, `initiative_mult_for`,
  `defensive_shift_for`, `transition_bonus_for`, `first_pass_input_bonus`,
  `arena_category_bonus`, `arena_pass_fail_chance_reduction`,
  `arena_team_strength_bonus` — a later phase's plan imports these into
  `club_tactical_profile_service.py`/`club_tactical_matchup_service.py`/
  `match_service.py`. This task does not modify any of those three files.

- [ ] **Step 1: Write the failing unit tests**

Create `backend/tests/test_coach_boost_service.py`:

```python
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.services.coach_boost_service import (
    apply_zone_boosts,
    arena_category_bonus,
    arena_pass_fail_chance_reduction,
    arena_team_strength_bonus,
    defensive_shift_for,
    depth_bonus_cap_for,
    first_pass_input_bonus,
    initiative_mult_for,
    resolve_active_boosts,
    transition_bonus_for,
)


def _coach(*boosts: tuple[CoachBoostType, float]) -> Coach:
    coach = Coach(display_name="Fixture Coach", rarity=Rarity.legendary)
    coach.boosts = [CoachBoost(boost_type=bt, magnitude=mag) for bt, mag in boosts]
    return coach


def test_resolve_active_boosts_of_none_is_empty():
    boosts = resolve_active_boosts(None)
    assert boosts.by_type == {}


def test_resolve_active_boosts_reads_each_coach_boost():
    coach = _coach((CoachBoostType.ATTACK_CENTRAL, 4.0), (CoachBoostType.GOALKEEPING, 6.0))
    boosts = resolve_active_boosts(coach)
    assert boosts.by_type == {CoachBoostType.ATTACK_CENTRAL: 4.0, CoachBoostType.GOALKEEPING: 6.0}


def test_apply_zone_boosts_adds_to_matching_zones_only():
    boosts = resolve_active_boosts(_coach((CoachBoostType.ATTACK_CENTRAL, 5.0)))
    zone_values = {"central_attack": 70.0, "wing_attack": 70.0, "midfield_control": 70.0}
    result = apply_zone_boosts(zone_values, boosts)
    assert result["central_attack"] == 75.0
    assert result["wing_attack"] == 70.0
    assert result["midfield_control"] == 70.0


def test_apply_zone_boosts_is_a_no_op_with_no_coach():
    zone_values = {"central_attack": 70.0}
    assert apply_zone_boosts(zone_values, resolve_active_boosts(None)) == zone_values


def test_depth_bonus_cap_for_adds_squad_stability():
    boosts = resolve_active_boosts(_coach((CoachBoostType.SQUAD_STABILITY, 2.0)))
    assert depth_bonus_cap_for(6.0, boosts) == 8.0
    assert depth_bonus_cap_for(6.0, resolve_active_boosts(None)) == 6.0


def test_initiative_mult_for_adds_ball_control():
    boosts = resolve_active_boosts(_coach((CoachBoostType.BALL_CONTROL, 0.1)))
    assert round(initiative_mult_for(1.0, boosts), 4) == 1.1
    assert initiative_mult_for(1.0, resolve_active_boosts(None)) == 1.0


def test_defensive_shift_for_only_applies_to_attacking_mentality():
    boosts = resolve_active_boosts(_coach((CoachBoostType.DEFENSIVE_DISCIPLINE, 0.03)))
    assert round(defensive_shift_for("ATTACKING", -0.07, boosts), 4) == -0.04
    assert defensive_shift_for("BALANCED", 0.0, boosts) == 0.0
    assert defensive_shift_for("DEFENSIVE", 0.09, boosts) == 0.09


def test_defensive_shift_for_never_exceeds_zero_even_at_extreme_magnitude():
    # Regression test for this session's own "extreme values inverted a
    # matchup" lesson: no coach boost should let ATTACKING defend better
    # than BALANCED (0.0) purely from a coach, regardless of magnitude.
    boosts = resolve_active_boosts(_coach((CoachBoostType.DEFENSIVE_DISCIPLINE, 100.0)))
    assert defensive_shift_for("ATTACKING", -0.07, boosts) == 0.0


def test_transition_bonus_for_only_applies_to_counter_attack_playstyle():
    boosts = resolve_active_boosts(_coach((CoachBoostType.COUNTER_MASTERY, 0.3)))
    assert round(transition_bonus_for("COUNTER_ATTACK", 2.0, boosts), 4) == 2.3
    assert transition_bonus_for("HIGH_PRESS", 1.3, boosts) == 1.3


def test_first_pass_input_bonus_reads_passing_accuracy():
    boosts = resolve_active_boosts(_coach((CoachBoostType.PASSING_ACCURACY, 3.0)))
    assert first_pass_input_bonus(boosts) == 3.0
    assert first_pass_input_bonus(resolve_active_boosts(None)) == 0.0


def test_arena_category_bonus_maps_fwd_def_gk_only():
    boosts = resolve_active_boosts(_coach(
        (CoachBoostType.ATTACK_CENTRAL, 4.0), (CoachBoostType.DEFENCE_CENTRAL, 6.0), (CoachBoostType.GOALKEEPING, 8.0),
    ))
    assert arena_category_bonus("FWD", boosts) == 4
    assert arena_category_bonus("DEF", boosts) == 6
    assert arena_category_bonus("GK", boosts) == 8
    assert arena_category_bonus("MID", boosts) == 0


def test_arena_pass_fail_chance_reduction_reads_passing_accuracy():
    boosts = resolve_active_boosts(_coach((CoachBoostType.PASSING_ACCURACY, 2.0)))
    assert arena_pass_fail_chance_reduction(boosts) == 2.0


def test_arena_team_strength_bonus_reads_midfield_control():
    boosts = resolve_active_boosts(_coach((CoachBoostType.MIDFIELD_CONTROL, 5.0)))
    assert arena_team_strength_bonus(boosts) == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_coach_boost_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named
'app.services.coach_boost_service'`.

- [ ] **Step 3: Create `backend/app/services/coach_boost_service.py`**

```python
from dataclasses import dataclass, field

from app.models.coach import Coach
from app.models.enums import CoachBoostType

# This module is deliberately a one-way leaf: it imports nothing from
# club_tactical_profile_service.py / club_tactical_matchup_service.py /
# match_service.py. A later phase makes those three modules call INTO
# this one (passing their own base values as plain parameters) — if this
# module imported back from any of them, that would be a circular import
# the moment that wiring lands.


@dataclass(frozen=True)
class ActiveCoachBoosts:
    by_type: dict[CoachBoostType, float] = field(default_factory=dict)


def resolve_active_boosts(coach: Coach | None) -> ActiveCoachBoosts:
    """coach=None (nothing equipped) returns an empty ActiveCoachBoosts, so
    every function below needs zero special-casing for "no coach".

    `float(b.magnitude)` matters here, not stylistically: CoachBoost.magnitude
    is a `Numeric` column, which SQLAlchemy returns as `decimal.Decimal`, not
    `float`, once a Coach is loaded from a real database (this module's own
    unit tests never round-trip through a DB, so they cannot catch this —
    every `Coach`/`CoachBoost` in test_coach_boost_service.py is a bare
    in-memory object, never flushed). Mixing `Decimal` into this module's
    plain-float arithmetic (`base_shift + offset`, etc.) would raise
    `TypeError` the moment a later phase calls this against a real DB-backed
    Coach. Casting once, right here, is this codebase's own established
    pattern for the identical gotcha — see `float(p.probability)` in
    `pack_service.roll_rarities`."""
    if coach is None:
        return ActiveCoachBoosts(by_type={})
    return ActiveCoachBoosts(by_type={b.boost_type: float(b.magnitude) for b in coach.boosts})


_ZONE_TO_BOOST_TYPE: dict[str, CoachBoostType] = {
    "central_attack": CoachBoostType.ATTACK_CENTRAL,
    "wing_attack": CoachBoostType.ATTACK_WING,
    "midfield_control": CoachBoostType.MIDFIELD_CONTROL,
    "central_defence": CoachBoostType.DEFENCE_CENTRAL,
    "wing_defence": CoachBoostType.DEFENCE_WING,
    "goalkeeping": CoachBoostType.GOALKEEPING,
}


def apply_zone_boosts(zone_values: dict[str, float], boosts: ActiveCoachBoosts) -> dict[str, float]:
    """Tournament hook — compute_profile's 6 zones, spec §5 items 1-6."""
    return {
        zone: value + boosts.by_type.get(_ZONE_TO_BOOST_TYPE[zone], 0.0)
        for zone, value in zone_values.items()
    }


def depth_bonus_cap_for(base_cap: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 11 (SQUAD_STABILITY)."""
    return base_cap + boosts.by_type.get(CoachBoostType.SQUAD_STABILITY, 0.0)


def initiative_mult_for(base_mult: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 8 (BALL_CONTROL)."""
    return base_mult + boosts.by_type.get(CoachBoostType.BALL_CONTROL, 0.0)


def defensive_shift_for(mentality: str, base_shift: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 9 (DEFENSIVE_DISCIPLINE), only for
    ATTACKING mentality, clamped so the result never exceeds 0.0 (an
    ATTACKING-mentality team can never be pushed to defend as well as
    BALANCED purely by a coach — see this session's Phase 1 STATUS doc's
    "safety bug" writeup for why an uncapped bonus here would be unsafe)."""
    if mentality != "ATTACKING":
        return base_shift
    offset = boosts.by_type.get(CoachBoostType.DEFENSIVE_DISCIPLINE, 0.0)
    return min(0.0, base_shift + offset)


def transition_bonus_for(playstyle: str, base_bonus: float, boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 10 (COUNTER_MASTERY), only for
    COUNTER_ATTACK playstyle."""
    if playstyle != "COUNTER_ATTACK":
        return base_bonus
    return base_bonus + boosts.by_type.get(CoachBoostType.COUNTER_MASTERY, 0.0)


def first_pass_input_bonus(boosts: ActiveCoachBoosts) -> float:
    """Tournament hook — spec §5 item 7 (PASSING_ACCURACY), tournament
    half: added to midfield_control before _first_pass_quality_factor
    runs, per the spec — this function only resolves the bonus value, the
    call site itself is a later phase's job."""
    return boosts.by_type.get(CoachBoostType.PASSING_ACCURACY, 0.0)


_ARENA_CATEGORY_TO_BOOST_TYPE: dict[str, CoachBoostType] = {
    "FWD": CoachBoostType.ATTACK_CENTRAL,
    "DEF": CoachBoostType.DEFENCE_CENTRAL,
    "GK": CoachBoostType.GOALKEEPING,
}


def arena_category_bonus(category: str, boosts: ActiveCoachBoosts) -> int:
    """Arena hook — spec §5 items 1/4/6's Arena half (FWD/DEF/GK category
    averages). Any other category (e.g. "MID", which Arena doesn't even
    have) resolves to 0, never raises."""
    boost_type = _ARENA_CATEGORY_TO_BOOST_TYPE.get(category)
    if boost_type is None:
        return 0
    return round(boosts.by_type.get(boost_type, 0.0))


def arena_pass_fail_chance_reduction(boosts: ActiveCoachBoosts) -> float:
    """Arena hook — spec §5 item 7's Arena half (percentage points to
    subtract from match_pass_fail_chance_min/max)."""
    return boosts.by_type.get(CoachBoostType.PASSING_ACCURACY, 0.0)


def arena_team_strength_bonus(boosts: ActiveCoachBoosts) -> int:
    """Arena hook — spec §5 item 3's Arena stand-in (MIDFIELD_CONTROL has
    no Arena category of its own, so it bumps team_strength directly)."""
    return round(boosts.by_type.get(CoachBoostType.MIDFIELD_CONTROL, 0.0))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_coach_boost_service.py -v`
Expected: PASS (14 passed).

- [ ] **Step 5: Run the full backend suite one more time**

Run: `cd backend && pytest tests/ -v`
Expected: PASS, same pre-existing-unrelated-failure caveat as Task 4 Step 6.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/coach_boost_service.py backend/tests/test_coach_boost_service.py
git commit -m "feat(coaches): add coach boost dispatch service with unit tests"
```

---

### Task 6: Frontend — `Coach`/`CoachBoost` types + admin API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/admin/api.ts`

**Interfaces:**
- Consumes: nothing frontend-side yet (mirrors backend schemas from Tasks
  1/2/4 by field name).
- Produces: `Coach`, `CoachBoost`, `CoachBoostType` TS types;
  `fetchAdminCoaches`, `createCoach`, `updateCoach`, `toggleCoachActive`,
  `toggleCoachPackDroppable`, `deleteCoach`, `uploadCoachImage`,
  `deleteCoachImage` — Task 7's `AdminCoachesPage.tsx` imports all of
  these.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, add near the existing `Player`
interface (mirroring its own field order/style):

```typescript
export type CoachBoostType =
  | "attack_central" | "attack_wing" | "midfield_control"
  | "defence_central" | "defence_wing" | "goalkeeping"
  | "passing_accuracy" | "ball_control" | "defensive_discipline"
  | "counter_mastery" | "squad_stability";

export interface CoachBoost {
  id: number;
  boost_type: CoachBoostType;
  magnitude: number;
}

export interface Coach {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  quick_sell_price: number;
  is_active: boolean;
  is_pack_droppable: boolean;
  boosts: CoachBoost[];
}
```

- [ ] **Step 2: Run typecheck to confirm the new types alone compile**

Run: `cd frontend && npm run typecheck`
Expected: PASS (new exported types with no consumers yet can't break
anything).

- [ ] **Step 3: Add the admin API functions**

In `frontend/src/admin/api.ts`, add `Coach` to the existing `@/types`
import line, then add this block after the existing `// --- Players ---`
section (mirroring `fetchAdminPlayers`/`createPlayer`/etc. verbatim, lines
already read this session):

```typescript
// --- Coaches ---
export async function fetchAdminCoaches(search: string, page: number): Promise<Page<Coach>> {
  const { data } = await api.get<Page<Coach>>("/admin/coaches", { params: { search: search || undefined, page, include_inactive: true } });
  return data;
}

export async function createCoach(payload: Record<string, unknown>): Promise<Coach> {
  const { data } = await api.post<Coach>("/admin/coaches", payload);
  return data;
}

export async function updateCoach(id: number, payload: Record<string, unknown>): Promise<Coach> {
  const { data } = await api.put<Coach>(`/admin/coaches/${id}`, payload);
  return data;
}

export async function toggleCoachActive(id: number): Promise<Coach> {
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/toggle-active`);
  return data;
}

export async function toggleCoachPackDroppable(id: number): Promise<Coach> {
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/toggle-pack-droppable`);
  return data;
}

export async function deleteCoach(id: number) {
  await api.delete(`/admin/coaches/${id}`);
}

export async function uploadCoachImage(id: number, file: File): Promise<Coach> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<Coach>(`/admin/coaches/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteCoachImage(id: number): Promise<Coach> {
  const { data } = await api.delete<Coach>(`/admin/coaches/${id}/image`);
  return data;
}
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/admin/api.ts
git commit -m "feat(coaches): add frontend Coach types and admin API client"
```

---

### Task 7: Frontend — `AdminCoachesPage.tsx` + routing + nav

**Files:**
- Create: `frontend/src/admin/pages/AdminCoachesPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/admin/AdminLayout.tsx`

**Interfaces:**
- Consumes: `Coach`, `CoachBoost`, `CoachBoostType` and all 8 API
  functions (Task 6).
- Produces: nothing consumed by a later task — this plan's last task.

- [ ] **Step 1: Create `AdminCoachesPage.tsx`**

Mirrors `AdminPlayersPage.tsx`'s structure (already read in full this
session) minus CSV import/export and the position/attack/defense fields,
replacing them with a boosts editor capped by the same rarity→slot-count
table as the backend's `BOOST_SLOTS_BY_RARITY` (Task 2):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  createCoach, deleteCoach, deleteCoachImage, fetchAdminCoaches,
  toggleCoachActive, toggleCoachPackDroppable, updateCoach, uploadCoachImage,
} from "@/admin/api";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Coach, CoachBoostType, Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

const BOOST_SLOTS_BY_RARITY: Record<Rarity, number> = {
  common: 1, rare: 1, epic: 2, legendary: 3, diamond: 0,
};

const BOOST_TYPES: CoachBoostType[] = [
  "attack_central", "attack_wing", "midfield_control", "defence_central", "defence_wing",
  "goalkeeping", "passing_accuracy", "ball_control", "defensive_discipline", "counter_mastery", "squad_stability",
];

const BOOST_TYPE_LABELS: Record<CoachBoostType, string> = {
  attack_central: "Атака в центре", attack_wing: "Атака на флангах", midfield_control: "Контроль полузащиты",
  defence_central: "Защита в центре", defence_wing: "Защита на флангах", goalkeeping: "Игра вратаря",
  passing_accuracy: "Точность передач", ball_control: "Контроль мяча", defensive_discipline: "Дисциплина в обороне",
  counter_mastery: "Мастерство контратак", squad_stability: "Стабильность состава",
};

type BoostFormRow = { boost_type: CoachBoostType; magnitude: number };

const emptyForm = {
  display_name: "", rarity: "common" as Rarity, quick_sell_price: 10, is_active: true, is_pack_droppable: true,
  boosts: [{ boost_type: "attack_central" as CoachBoostType, magnitude: 2 }] as BoostFormRow[],
};

export default function AdminCoachesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Coach | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-coaches", search, page], queryFn: () => fetchAdminCoaches(search, page) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-coaches"] });

  const createMutation = useMutation({
    mutationFn: () => createCoach(form),
    onSuccess: () => { invalidate(); setCreating(false); setForm(emptyForm); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const updateMutation = useMutation({
    mutationFn: () => updateCoach(editing!.id, form),
    onSuccess: () => { invalidate(); setEditing(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Ошибка"),
  });
  const toggleMutation = useMutation({ mutationFn: toggleCoachActive, onSuccess: invalidate });
  const toggleDroppableMutation = useMutation({ mutationFn: toggleCoachPackDroppable, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteCoach, onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить"),
  });
  const uploadImageMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => uploadCoachImage(id, file), onSuccess: invalidate,
  });
  const deleteImageMutation = useMutation({ mutationFn: deleteCoachImage, onSuccess: invalidate });

  const openEdit = (c: Coach) => {
    setEditing(c);
    setForm({
      display_name: c.display_name, rarity: c.rarity, quick_sell_price: c.quick_sell_price,
      is_active: c.is_active, is_pack_droppable: c.is_pack_droppable,
      boosts: c.boosts.map((b) => ({ boost_type: b.boost_type, magnitude: b.magnitude })),
    });
  };

  const slotsForRarity = BOOST_SLOTS_BY_RARITY[form.rarity];
  const boostsValid = form.boosts.length === slotsForRarity && new Set(form.boosts.map((b) => b.boost_type)).size === form.boosts.length;

  const setRarity = (rarity: Rarity) => {
    const slots = BOOST_SLOTS_BY_RARITY[rarity];
    const boosts = form.boosts.slice(0, slots);
    while (boosts.length < slots) {
      const unused = BOOST_TYPES.find((t) => !boosts.some((b) => b.boost_type === t)) ?? BOOST_TYPES[0];
      boosts.push({ boost_type: unused, magnitude: 2 });
    }
    setForm({ ...form, rarity, boosts });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-2xl font-bold">Тренеры</h1>
        <button onClick={() => { setCreating(true); setForm(emptyForm); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Добавить
        </button>
      </div>

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по имени..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2" />
              <th className="px-3 py-2">Имя</th>
              <th className="px-3 py-2">Редкость</th>
              <th className="px-3 py-2">Усиления</th>
              <th className="px-3 py-2">Активен</th>
              <th className="px-3 py-2">В паках</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="px-3 py-2">
                  <img src={staticUrl(c.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-10 w-10 rounded-lg object-cover" />
                </td>
                <td className="px-3 py-2">{c.display_name}</td>
                <td className="px-3 py-2">{RARITY_LABELS[c.rarity]}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{c.boosts.map((b) => BOOST_TYPE_LABELS[b.boost_type]).join(", ")}</td>
                <td className="px-3 py-2">{c.is_active ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">{c.is_pack_droppable ? "✅" : "🚫"}</td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <button onClick={() => openEdit(c)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">✏️</button>
                    <button onClick={() => toggleMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {c.is_active ? "🚫" : "✅"}
                    </button>
                    <button onClick={() => toggleDroppableMutation.mutate(c.id)} className="rounded-lg bg-white/5 px-2 py-1 text-xs">
                      {c.is_pack_droppable ? "📦🚫" : "📦"}
                    </button>
                    <button onClick={() => deleteMutation.mutate(c.id)} className="rounded-lg bg-red-500/70 px-2 py-1 text-xs">🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="p-4 text-sm text-slate-400">Загрузка...</p>}
      </div>

      {data && data.pages > 1 && (
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать тренера" : "Новый тренер"}</p>
            {error && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Имя</span>
                <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Редкость</span>
                <select value={form.rarity} onChange={(e) => setRarity(e.target.value as Rarity)} className="rounded-lg bg-bg-surface px-3 py-2 outline-none">
                  {RARITIES.map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена продажи</span>
                <input
                  type="number" min={0} value={form.quick_sell_price}
                  onChange={(e) => setForm({ ...form, quick_sell_price: Number(e.target.value) })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>

              <p className="mt-2 text-xs font-semibold text-slate-300">Усиления ({slotsForRarity} для этой редкости)</p>
              {form.boosts.map((boost, i) => (
                <div key={i} className="grid grid-cols-2 gap-2">
                  <select
                    value={boost.boost_type}
                    onChange={(e) => {
                      const boosts = [...form.boosts];
                      boosts[i] = { ...boosts[i], boost_type: e.target.value as CoachBoostType };
                      setForm({ ...form, boosts });
                    }}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    {BOOST_TYPES.map((t) => <option key={t} value={t}>{BOOST_TYPE_LABELS[t]}</option>)}
                  </select>
                  <input
                    type="number" step="0.1" value={boost.magnitude}
                    onChange={(e) => {
                      const boosts = [...form.boosts];
                      boosts[i] = { ...boosts[i], magnitude: Number(e.target.value) };
                      setForm({ ...form, boosts });
                    }}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  />
                </div>
              ))}
              {!boostsValid && (
                <p className="text-[11px] text-red-400">
                  Нужно ровно {slotsForRarity} усилени{slotsForRarity === 1 ? "е" : "я"}, все разных типов.
                </p>
              )}

              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input type="checkbox" checked={form.is_pack_droppable} onChange={(e) => setForm({ ...form, is_pack_droppable: e.target.checked })} />
                Может выпасть из пака
              </label>

              {editing && (
                <div className="mt-2 flex items-center gap-2">
                  <img src={staticUrl(editing.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")} className="h-14 w-14 rounded-lg object-cover" />
                  <button onClick={() => fileInputRef.current?.click()} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs">Загрузить фото</button>
                  <input
                    ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
                    onChange={(e) => e.target.files?.[0] && uploadImageMutation.mutate({ id: editing.id, file: e.target.files[0] })}
                  />
                  {editing.image_path && (
                    <button onClick={() => deleteImageMutation.mutate(editing.id)} className="rounded-lg bg-red-500/70 px-3 py-1.5 text-xs">Удалить фото</button>
                  )}
                </div>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); setError(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                disabled={!boostsValid}
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register the route in `App.tsx`**

Add `import AdminCoachesPage from "@/admin/pages/AdminCoachesPage";` next
to the other admin page imports (near `AdminPlayersPage`'s own import
line), and add a `<Route path="coaches" element={<AdminCoachesPage />}
/>` alongside the existing `players`/`packs` admin routes (match whatever
nesting pattern those routes already use under the `/admin` layout route
— confirm the exact JSX shape by reading the surrounding lines before
adding, since this plan doesn't reproduce `App.tsx`'s full route tree).

- [ ] **Step 3: Add the nav item in `AdminLayout.tsx`**

In the nav items array (already read this session, starts around line 7),
add, near the "Футболисты"/"Паки" entries:

```typescript
{ to: "/admin/coaches", label: "Тренеры", icon: "🧑‍🏫" },
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Verify live in the browser**

Start the dev server per this repo's CLAUDE.md notes (`docker compose up
-d --build frontend backend` if `docker-compose.override.yml`'s static
preview mode is active), log in as the admin/dev user, open
`/admin/coaches`. Confirm: the page lists coaches (empty initially); "+
Добавить" opens the create form; picking "Легендарная" rarity auto-fills
3 boost rows and the save button is enabled only when exactly 3 distinct
boost types are set; creating a coach succeeds and appears in the table;
editing, toggling active/pack-droppable, uploading an image, and deleting
all work against the real backend with no console errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/pages/AdminCoachesPage.tsx frontend/src/App.tsx frontend/src/admin/AdminLayout.tsx
git commit -m "feat(coaches): add AdminCoachesPage with rarity-gated boost editor"
```

---

## Self-Review Notes

**Spec coverage:** §3 (data model) → Task 1 (models/migration) + Task 2
(schemas). §6 (boost dispatch layer) → Task 5, built and unit-tested per
spec §12's first bullet, deliberately not wired into any match engine yet
per §13's phasing. §9's admin-CRUD piece → Tasks 3/4 (backend) + Tasks
6/7 (frontend). §4's rarity→slot-count table → enforced in Task 2's
Pydantic validators and mirrored client-side in Task 7. §10 (no
`GameConfig` fields) → honored throughout; every magnitude lives on
`CoachBoost.magnitude` itself, no config knob anywhere. §1's "coach rarity
caps at legendary" → DB `CheckConstraint` in Task 1, schema-level
`BOOST_SLOTS_BY_RARITY` keys in Task 2 (only 4 rarities present).
Everything else in the spec (§5's exact hook points, §7's packs, §8's
equip flow, §11 UX beyond admin) is explicitly later-phase work per §13,
not silently dropped.

**Placeholder scan:** every step has real, complete code — no TBD/TODO,
no "add appropriate validation" without the validator shown, no "mirror
Task N" without the actual code repeated in place. Task 7 Step 2 is the
one intentionally-open step (exact `App.tsx` route JSX), flagged
explicitly as "read the surrounding lines first" rather than guessed,
since this plan's author did not re-read `App.tsx`'s full route tree at
plan-writing time and guessing its exact nesting would risk a wrong
placeholder.

**Fixed during self-review:** `resolve_active_boosts` (Task 5) now casts
`CoachBoost.magnitude` to `float()` explicitly — its `Numeric` column type
returns `decimal.Decimal` from a real database, which would raise
`TypeError` the moment this module's plain-float arithmetic runs against a
real DB-backed `Coach` in a later phase. Task 5's own unit tests never
round-trip through a DB (every fixture `Coach` is a bare in-memory object),
so they could not have caught this — it would have surfaced as a
production crash in whichever future phase first wires this service into
a real match. Fixed at the single choke point (`resolve_active_boosts`)
rather than scattered `float()` casts in every dispatch function, mirroring
this codebase's own existing convention for the identical gotcha
(`float(p.probability)` in `pack_service.roll_rarities`).

**Type consistency:** `CoachBoostType`'s 11 string values match verbatim
across Task 1 (Python enum), the migration (Postgres enum literal list),
Task 2 (Pydantic, same enum import), Task 5 (dispatch dict keys), and
Task 6/7 (TypeScript union + label map) — every occurrence was copied from
the same canonical list in spec §3, not retyped independently.
`BOOST_SLOTS_BY_RARITY`'s `{common:1, rare:1, epic:2, legendary:3}`
mapping appears identically in Task 2 (Python) and Task 7 (TypeScript).
`resolve_active_boosts`/`apply_zone_boosts`/etc.'s exact names and
signatures in Task 5 match spec §6's own listing verbatim.
