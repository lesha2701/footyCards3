# Coach Cards — Phase 2 (Club Track) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** make coaches real for clubs — a club can buy a coach via a new
club-budget-funded pack, its captain/assistants can equip one, and the
equipped coach's boosts genuinely shape tournament matches.

**Architecture:** `ClubCoachCard`/`ClubCoachPack` mirror the existing
`ClubCard`/`ClubPack` pair exactly, reusing `roll_rarities` verbatim and a
new `pick_random_coach` mirroring `pick_random_player`. Equipping adds one
nullable FK (`ClubLineup.club_coach_card_id`) alongside the existing
formation/mentality/playstyle settings on that same row. The match-engine
half threads a `coach: Coach | None` through `ClubTacticalSide`/
`build_side`/`compute_profile`, reading every boost through Phase 1's
already-built, already-tested `coach_boost_service.py` — this plan never
re-implements boost logic, only wires existing functions into 4 read
sites in already-tuned, delicate code.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, Pydantic v2, pytest
(async, in-memory SQLite), React 18 + TypeScript + TanStack Query +
Tailwind + Framer Motion.

**Spec:** `docs/superpowers/specs/2026-09-08-coach-cards-design.md` — this
plan implements §7 (club acquisition), §8 (club equip flow), §5 (all 11
boost hook points), and the club half of §9, per §13's "Phase 2 — club
track, end to end."

## Global Constraints

- Never expose the OPPONENT club's equipped coach or its boosts anywhere —
  this plan never touches `get_next_opponent`/`NextOpponentOut`. No task
  here modifies `club_squad_service.get_next_opponent` or its schema.
- Coach boost magnitudes are exactly what Phase 1 left them (plain
  admin-entered floats) — this plan wires hooks up, it does not retune
  any `coach_boost_service.py` constant or add a `GameConfig` field.
- Every boost's hook point calls the EXACT existing `coach_boost_service.py`
  function named in this plan — never re-implement boost math inline.
  `coach_boost_service.py` itself is not modified by any task here.
- Preserve `club_tactical_matchup_service.py`'s existing balance-safety
  properties — the `DEFENSIVE_DISCIPLINE` clamp inside `defensive_shift_for`
  (already enforced by Phase 1's own tests) and `zone_ratio`'s `[0.05, 0.95]`
  clamp. A coach boost must never be able to break either bound; this
  plan's tests must include a regression test proving it can't.
- No unrelated refactoring of `club_tactical_matchup_service.py`/
  `club_tactical_profile_service.py` beyond what's needed to thread a
  `coach` parameter through — this is delicate, already-once-rebalanced
  code (see that file's own extensive comments on why its constants are
  what they are). Touch only what's necessary.
- Row-locking (`with_for_update`) for the club-budget debit and the
  `ClubLineup` mutation, exactly mirroring `open_club_pack`/
  `set_club_tactics`'s existing patterns. Idempotency-key uniqueness for
  the pack-opening endpoint, exactly mirroring `open_club_pack`.
- Every behavior change gets a test (repo `CLAUDE.md` Definition of
  Done), AND — matching this session's own established practice for
  match-engine changes — statistical evidence (not just unit tests) that
  a boost's effect on real matches is real but bounded.
- **Setup ruling (binding, not a task-time decision):** this plan is
  executed directly on local `main`, not a fresh worktree — the club
  tactical tournament engine this plan wires into is itself 100%
  local-only (never pushed to origin). At ship time, only this plan's own
  new commits get pushed to `origin/main` (an isolated branch containing
  just those commits, fast-forward-pushed) — never the pre-existing
  club-tactical commits already sitting on local `main`, per this
  session's standing instruction that track stays local-only.
- Do NOT include anything from spec §7/§8's personal (non-club) track —
  no `UserCoachCard`, no personal `CoachPack`, no `Lineup.user_coach_card_id`,
  no personal equip endpoint, no `coach_boost_service.py` Arena function
  call sites. That is Phase 3, a separate future plan.

---

### Task 1: `ClubCoachCard` model + migration

**Files:**
- Modify: `backend/app/models/enums.py` (add `ClubCoachCardSource`)
- Create: `backend/app/models/club_coach_card.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/00NN_club_coach_cards.py` (check
  `ls backend/alembic/versions | sort | tail -3` for the real current
  head before naming — do not assume a number)
- Test: `backend/tests/test_club_coach_card_model.py`

**Interfaces:**
- Produces: `ClubCoachCard` (`id`, `club_id` FK `clubs.id` CASCADE,
  `coach_id` FK `coaches.id`, `serial_number: int`, `source:
  ClubCoachCardSource`, `source_ref_id: int | None`, `acquired_at`,
  `coach` relationship `lazy="joined"`). Later tasks import this from
  `app.models.club_coach_card`.

- [ ] **Step 1: Add `ClubCoachCardSource` to `enums.py`**

Add directly after the existing `ClubCardSource` class
(`backend/app/models/enums.py:116-119`):

```python
class ClubCoachCardSource(str, enum.Enum):
    club_pack = "club_pack"
```

(No `starter_seed` — clubs don't start with a free coach, per spec §7.)

- [ ] **Step 2: Write the failing model test**

Create `backend/tests/test_club_coach_card_model.py`:

```python
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach, CoachBoost
from app.models.enums import ClubCoachCardSource, CoachBoostType, Rarity


async def test_club_coach_card_persists_and_loads_coach_joined(db_session, seed_club):
    coach = Coach(display_name="Test Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=4.0)]
    db_session.add(coach)
    await db_session.flush()

    card = ClubCoachCard(club_id=seed_club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)

    assert card.id is not None
    assert card.coach.display_name == "Test Coach"
```

If this repo's test suite doesn't already have a `seed_club` fixture,
check `backend/tests/conftest.py` and `backend/tests/factories.py` for
whatever existing helper creates a `Club` row for other club-related
tests (e.g. `test_club_squad.py`'s own setup) and use that exact pattern
instead of inventing a new one.

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_card_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.club_coach_card'`.

- [ ] **Step 3: Create `backend/app/models/club_coach_card.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ClubCoachCardSource
from app.models.mixins import utcnow


class ClubCoachCard(Base):
    __tablename__ = "club_coach_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[ClubCoachCardSource] = mapped_column(Enum(ClubCoachCardSource, name="club_coach_card_source_enum"), nullable=False)
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    coach: Mapped["Coach"] = relationship(lazy="joined")
```

- [ ] **Step 4: Register in `app/models/__init__.py`**

Add, alphabetically near the existing `from app.models.club_card import
ClubCard`:

```python
from app.models.club_coach_card import ClubCoachCard
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_card_model.py -v`
Expected: PASS.

- [ ] **Step 6: Write the migration**

Check `ls backend/alembic/versions | sort | tail -3` for the real head
first. Mirror `backend/alembic/versions/0061_club_packs.py`'s pattern for
reusing an existing Postgres enum type where relevant (not needed here —
`club_coach_card_source_enum` is brand new, so no `create_type=False`
trick required):

```python
"""ClubCoachCard

Revision ID: 00NN
Revises: <real current head>
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "00NN"
down_revision = "<real current head>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_coach_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Enum("club_pack", name="club_coach_card_source_enum"), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_coach_cards_club_id", "club_coach_cards", ["club_id"])
    op.create_index("ix_club_coach_cards_coach_id", "club_coach_cards", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_club_coach_cards_coach_id", table_name="club_coach_cards")
    op.drop_index("ix_club_coach_cards_club_id", table_name="club_coach_cards")
    op.drop_table("club_coach_cards")
    bind = op.get_bind()
    sa.Enum(name="club_coach_card_source_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 7: Verify the migration**

Run: `cd backend && alembic upgrade head --sql` (dry-run, no live DB
needed) — confirm it renders clean `CREATE TABLE club_coach_cards` SQL
with no Python errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/club_coach_card.py backend/app/models/__init__.py backend/alembic/versions/00NN_club_coach_cards.py backend/tests/test_club_coach_card_model.py
git commit -m "feat(coaches): add ClubCoachCard model and migration"
```

---

### Task 2: `ClubCoachPack` + opening models + migration

**Files:**
- Modify: `backend/app/models/enums.py` (add `ClubBudgetTransactionType.coach_pack_purchase`)
- Create: `backend/app/models/club_coach_pack.py`
- Create: `backend/app/models/club_coach_pack_opening.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/00NN_club_coach_packs.py`
- Test: `backend/tests/test_club_coach_pack_model.py`

**Interfaces:**
- Consumes: `ClubCoachCard` (Task 1).
- Produces: `ClubCoachPack` (`id`, `slug`, `name`, `description`, `price`,
  `card_count`, `guaranteed_min_rarity`, `image_path`, `is_active`,
  `sort_order`, `rarity_probabilities` relationship), `ClubCoachPackRarityProbability`
  (`id`, `club_coach_pack_id` FK, `rarity`, `probability`), `ClubCoachPackOpening`
  (`id`, `club_id`, `club_coach_pack_id`, `opened_by_user_id`, `price_paid`,
  `idempotency_key`, `created_at`, `cards` relationship), `ClubCoachPackOpeningCard`
  (`id`, `opening_id` FK, `club_coach_card_id` FK, `is_new_coach: bool`).
  Task 3 imports all four.

- [ ] **Step 1: Add `coach_pack_purchase` to `ClubBudgetTransactionType`**

`backend/app/models/enums.py:98-104` currently:
```python
class ClubBudgetTransactionType(str, enum.Enum):
    daily_claim = "daily_claim"
    pack_purchase = "pack_purchase"
    tournament_reward = "tournament_reward"
    club_game_reward = "club_game_reward"
    club_missing_item_reward = "club_missing_item_reward"
```
Add one member:
```python
    coach_pack_purchase = "coach_pack_purchase"
```

- [ ] **Step 2: Write the failing model test**

Create `backend/tests/test_club_coach_pack_model.py`:

```python
from app.models.club_coach_pack import ClubCoachPack, ClubCoachPackRarityProbability
from app.models.club_coach_pack_opening import ClubCoachPackOpening, ClubCoachPackOpeningCard
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach
from app.models.enums import ClubCoachCardSource, Rarity


async def test_club_coach_pack_with_probabilities_persists(db_session):
    pack = ClubCoachPack(slug="test-coach-pack", name="Test Coach Pack", price=100, card_count=1)
    pack.rarity_probabilities = [ClubCoachPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    assert pack.id is not None
    assert len(pack.rarity_probabilities) == 1


async def test_club_coach_pack_opening_links_cards(db_session, seed_club, seed_user):
    coach = Coach(display_name="Opened Coach", rarity=Rarity.common)
    db_session.add(coach)
    await db_session.flush()
    card = ClubCoachCard(club_id=seed_club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    pack = ClubCoachPack(slug="opening-test-pack", name="Opening Test Pack", price=50, card_count=1)
    db_session.add(pack)
    await db_session.flush()

    opening = ClubCoachPackOpening(club_id=seed_club.id, club_coach_pack_id=pack.id, opened_by_user_id=seed_user.id, price_paid=50)
    opening.cards = [ClubCoachPackOpeningCard(club_coach_card_id=card.id, is_new_coach=True)]
    db_session.add(opening)
    await db_session.commit()
    await db_session.refresh(opening)

    assert len(opening.cards) == 1
```

Check `backend/tests/conftest.py`/`factories.py` for the exact
`seed_club`/`seed_user`-shaped fixtures this repo's existing club tests
already use (e.g. what `test_club_squad.py` or `test_club_packs.py`
uses) and match those fixture names exactly rather than guessing.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_pack_model.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Create `backend/app/models/club_coach_pack.py`**

Direct mirror of `backend/app/models/club_pack.py`:

```python
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class ClubCoachPack(TimestampMixin, Base):
    __tablename__ = "club_coach_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    card_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    guaranteed_min_rarity: Mapped[Optional[Rarity]] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rarity_probabilities: Mapped[list["ClubCoachPackRarityProbability"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )


class ClubCoachPackRarityProbability(Base):
    __tablename__ = "club_coach_pack_rarity_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_coach_pack_id: Mapped[int] = mapped_column(ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False)
    rarity: Mapped[Rarity] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=False)
    probability: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)

    pack: Mapped["ClubCoachPack"] = relationship(back_populates="rarity_probabilities")

    __table_args__ = (UniqueConstraint("club_coach_pack_id", "rarity", name="uq_club_coach_pack_rarity_once"),)
```

Note: `card_count` defaults to `1` here (not `3` like `ClubPack`) — a
coach is a bigger, rarer pull than a filler player card; a Coach Pack is
naturally a "buy one coach" product. Admins can still set a different
`card_count` per pack if they choose.

- [ ] **Step 5: Create `backend/app/models/club_coach_pack_opening.py`**

Direct mirror of `backend/app/models/club_pack_opening.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubCoachPackOpening(Base):
    __tablename__ = "club_coach_pack_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    club_coach_pack_id: Mapped[int] = mapped_column(ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    price_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cards: Mapped[list["ClubCoachPackOpeningCard"]] = relationship(back_populates="opening", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("club_id", "idempotency_key", name="uq_club_coach_pack_opening_idempotency"),)


class ClubCoachPackOpeningCard(Base):
    __tablename__ = "club_coach_pack_opening_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(ForeignKey("club_coach_pack_openings.id", ondelete="CASCADE"), nullable=False, index=True)
    club_coach_card_id: Mapped[int] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="CASCADE"), nullable=False)
    is_new_coach: Mapped[bool] = mapped_column(Boolean, nullable=False)

    opening: Mapped["ClubCoachPackOpening"] = relationship(back_populates="cards")
```

- [ ] **Step 6: Register in `app/models/__init__.py`**

```python
from app.models.club_coach_pack import ClubCoachPack, ClubCoachPackRarityProbability
from app.models.club_coach_pack_opening import ClubCoachPackOpening, ClubCoachPackOpeningCard
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_pack_model.py -v`
Expected: PASS.

- [ ] **Step 8: Write the migration**

Mirror `backend/alembic/versions/0061_club_packs.py`'s shape (reusing
`rarity_enum` via `postgresql.ENUM(..., create_type=False)`), combined
with `0066_tournament_core.py`'s multi-table-in-one-migration style, plus
adding the new `coach_pack_purchase` value to the EXISTING
`club_budget_transaction_type_enum` Postgres type via `ALTER TYPE ... ADD
VALUE` (the same technique `0083_diamond_rarity.py` used for adding
`diamond` to `rarity_enum` — check that file for the exact
`op.execute("ALTER TYPE ... ADD VALUE ...")` syntax used there and
replicate it for `club_budget_transaction_type_enum`/`'coach_pack_purchase'`,
confirming the real enum type name by checking `ClubBudgetTransaction`'s
model column definition first). Name the file
`00NN_club_coach_packs.py`, `down_revision` set to Task 1's migration.

```python
"""ClubCoachPack, ClubCoachPackOpening, coach_pack_purchase budget tx type

Revision ID: 00NN
Revises: <Task 1's migration revision>
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "00NN"
down_revision = "<Task 1's migration revision>"
branch_labels = None
depends_on = None

rarity_enum = postgresql.ENUM(
    "common", "rare", "epic", "legendary", "diamond", name="rarity_enum", create_type=False
)


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'coach_pack_purchase'")

    op.create_table(
        "club_coach_packs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guaranteed_min_rarity", rarity_enum, nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_coach_pack_rarity_probabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_coach_pack_id", sa.Integer(), sa.ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("probability", sa.Numeric(6, 4), nullable=False),
    )
    op.create_unique_constraint(
        "uq_club_coach_pack_rarity_once", "club_coach_pack_rarity_probabilities", ["club_coach_pack_id", "rarity"]
    )

    op.create_table(
        "club_coach_pack_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_coach_pack_id", sa.Integer(), sa.ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_coach_pack_openings_club_id", "club_coach_pack_openings", ["club_id"])
    op.create_unique_constraint(
        "uq_club_coach_pack_opening_idempotency", "club_coach_pack_openings", ["club_id", "idempotency_key"]
    )
    op.create_table(
        "club_coach_pack_opening_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opening_id", sa.Integer(), sa.ForeignKey("club_coach_pack_openings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_coach_card_id", sa.Integer(), sa.ForeignKey("club_coach_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_coach", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_club_coach_pack_opening_cards_opening_id", "club_coach_pack_opening_cards", ["opening_id"])


def downgrade() -> None:
    op.drop_index("ix_club_coach_pack_opening_cards_opening_id", table_name="club_coach_pack_opening_cards")
    op.drop_table("club_coach_pack_opening_cards")
    op.drop_index("ix_club_coach_pack_openings_club_id", table_name="club_coach_pack_openings")
    op.drop_table("club_coach_pack_openings")
    op.drop_table("club_coach_pack_rarity_probabilities")
    op.drop_table("club_coach_packs")
    # Postgres cannot remove a single enum value once added — 'coach_pack_purchase'
    # stays in club_budget_transaction_type_enum on downgrade, same accepted
    # limitation as 0083_diamond_rarity.py's downgrade for 'diamond'.
```

- [ ] **Step 9: Verify the migration**

Run: `cd backend && alembic upgrade head --sql` — confirm clean SQL, no
errors. Note `ALTER TYPE ... ADD VALUE` cannot run inside the same
transaction as later statements in the SAME migration on Postgres in
some configurations — if `alembic upgrade head --sql`'s dry-run output
looks fine but a real `alembic upgrade head` against Postgres later
fails with a "ALTER TYPE ... ADD VALUE cannot run inside a transaction
block" error, check how `0083_diamond_rarity.py` avoided this (it may
use `op.get_bind().execute(sa.text(...))` outside implicit
transaction wrapping, or Alembic's `env.py` may already run enum-adding
migrations non-transactionally in this repo — check `backend/alembic/env.py`
before assuming this needs a fix; flag it if it does).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/club_coach_pack.py backend/app/models/club_coach_pack_opening.py backend/app/models/__init__.py backend/alembic/versions/00NN_club_coach_packs.py backend/tests/test_club_coach_pack_model.py
git commit -m "feat(coaches): add ClubCoachPack and opening models"
```

---

### Task 3: `pick_random_coach` + `club_coach_pack_service.py`

**Files:**
- Modify: `backend/app/services/pack_service.py` (add `pick_random_coach`)
- Create: `backend/app/services/club_coach_pack_service.py`
- Test: `backend/tests/test_club_coach_pack_service.py`

**Interfaces:**
- Consumes: `ClubCoachCard` (Task 1), `ClubCoachPack`/`ClubCoachPackOpening`/
  `ClubCoachPackOpeningCard` (Task 2), `roll_rarities` (existing,
  `pack_service.py`), `debit_club_budget`/`ClubBudgetTransactionType.coach_pack_purchase`
  (existing service + Task 2's enum member).
- Produces: `pick_random_coach(db, rarity: Rarity) -> Coach`,
  `open_club_coach_pack(db, user, club_coach_pack_id, idempotency_key) -> ClubCoachPackOpenResult`.
  Task 4's admin router doesn't consume these (admin doesn't open packs);
  a later task's `PUT`/`POST /clubs/coach-packs` router consumes
  `open_club_coach_pack` directly (this plan folds that router into this
  same task rather than a separate one — see Step 6).

- [ ] **Step 1: Add `pick_random_coach` to `pack_service.py`**

Mirror `pick_random_player` (`backend/app/services/pack_service.py:84-108`)
exactly, minus the `CardCollection` join (coaches have no seasonal
collections):

```python
async def pick_random_coach(db: AsyncSession, rarity: Rarity) -> Coach:
    result = await db.execute(
        select(Coach)
        .where(Coach.rarity == rarity, Coach.is_active.is_(True), Coach.is_pack_droppable.is_(True))
        .order_by(func.random())
        .limit(1)
    )
    coach = result.scalar_one_or_none()
    if coach is None:
        result = await db.execute(
            select(Coach).where(Coach.is_active.is_(True), Coach.is_pack_droppable.is_(True)).order_by(func.random()).limit(1)
        )
        coach = result.scalar_one_or_none()
    if coach is None:
        raise ConflictError("No active coaches configured; cannot open coach packs")
    return coach
```

Add `from app.models.coach import Coach` to this file's imports (check
the file doesn't already import something named `Coach` from elsewhere
first — it shouldn't, but confirm).

- [ ] **Step 2: Write the failing service test**

Create `backend/tests/test_club_coach_pack_service.py`:

```python
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.services.pack_service import pick_random_coach


async def test_pick_random_coach_respects_rarity_and_droppable_flags(db_session):
    droppable = Coach(display_name="Droppable", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    droppable.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    not_droppable = Coach(display_name="Retired", rarity=Rarity.common, is_active=True, is_pack_droppable=False)
    not_droppable.boosts = [CoachBoost(boost_type=CoachBoostType.BALL_CONTROL, magnitude=1.0)]
    db_session.add_all([droppable, not_droppable])
    await db_session.commit()

    for _ in range(10):
        picked = await pick_random_coach(db_session, Rarity.common)
        assert picked.id == droppable.id
```

Router-level tests for `open_club_coach_pack` live in Step 6 below (the
club-coach-packs router test), not here — this file covers only
`pick_random_coach`'s own filter logic.

- [ ] **Step 3: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_pack_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'pick_random_coach'`.

- [ ] **Step 4: Run the test to verify it passes**

Run: same command.
Expected: PASS.

- [ ] **Step 5: Create `backend/app/services/club_coach_pack_service.py`**

Mirror `club_pack_service.py::open_club_pack`
(`backend/app/services/club_pack_service.py:44-108`+, already fully read)
exactly, substituting the coach model/pack pair and
`ClubBudgetTransactionType.coach_pack_purchase`:

```python
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError
from app.models.club_coach_card import ClubCoachCard
from app.models.club_coach_pack import ClubCoachPack
from app.models.club_coach_pack_opening import ClubCoachPackOpening, ClubCoachPackOpeningCard
from app.models.enums import ClubCoachCardSource, ClubBudgetTransactionType
from app.models.user import User
from app.schemas.club_coach_pack import ClubCoachPackOpenResult, OpenedClubCoachCardOut
from app.services.club_budget_service import debit_club_budget
from app.services.club_service import _lock_club, _require_manager, _require_membership
from app.services.pack_service import pick_random_coach, roll_rarities


async def _get_result_for_existing_opening(db: AsyncSession, opening: ClubCoachPackOpening) -> ClubCoachPackOpenResult:
    result = await db.execute(
        select(ClubCoachPackOpeningCard)
        .where(ClubCoachPackOpeningCard.opening_id == opening.id)
        .options(joinedload(ClubCoachPackOpeningCard.club_coach_card).joinedload(ClubCoachCard.coach))
    )
    opening_cards = result.unique().scalars().all()
    pack = await db.get(ClubCoachPack, opening.club_coach_pack_id)
    club = await db.get(_ClubForBudget, opening.club_id)  # see Step 5 note below
    return ClubCoachPackOpenResult(
        pack=pack,
        cards=[OpenedClubCoachCardOut(card=oc.club_coach_card, is_new=oc.is_new_coach) for oc in opening_cards],
        new_budget=club.budget,
    )


async def open_club_coach_pack(
    db: AsyncSession, user: User, club_coach_pack_id: int, idempotency_key: Optional[str]
) -> ClubCoachPackOpenResult:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)

    if idempotency_key:
        existing = await db.execute(
            select(ClubCoachPackOpening).where(
                ClubCoachPackOpening.club_id == membership.club_id, ClubCoachPackOpening.idempotency_key == idempotency_key
            )
        )
        existing_opening = existing.scalar_one_or_none()
        if existing_opening is not None:
            return await _get_result_for_existing_opening(db, existing_opening)

    pack = await db.get(ClubCoachPack, club_coach_pack_id, options=[joinedload(ClubCoachPack.rarity_probabilities)])
    if pack is None or not pack.is_active:
        raise NotFoundError("Клубный пак тренеров не найден")

    club = await _lock_club(db, membership.club_id)
    await debit_club_budget(
        db, club, pack.price, ClubBudgetTransactionType.coach_pack_purchase, f"Открытие пака «{pack.name}»", "club_coach_pack", pack.id
    )
    club_id = club.id  # captured before any possible rollback — see club_pack_service.open_club_pack's own comment on why

    opening = ClubCoachPackOpening(
        club_id=club_id, club_coach_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=idempotency_key
    )

    try:
        db.add(opening)
        await db.flush()

        rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
        opened_cards: list[OpenedClubCoachCardOut] = []
        for rarity in rarities:
            coach = await pick_random_coach(db, rarity)
            serial_result = await db.execute(
                select(ClubCoachCard).where(ClubCoachCard.club_id == club_id, ClubCoachCard.coach_id == coach.id)
            )
            is_new = serial_result.first() is None
            next_serial = (
                await db.execute(select(ClubCoachCard).where(ClubCoachCard.coach_id == coach.id).order_by(ClubCoachCard.serial_number.desc()))
            ).scalars().first()
            serial_number = (next_serial.serial_number + 1) if next_serial else 1
            club_coach_card = ClubCoachCard(
                club_id=club_id, coach_id=coach.id, serial_number=serial_number,
                source=ClubCoachCardSource.club_pack, source_ref_id=pack.id,
            )
            db.add(club_coach_card)
            await db.flush()
            db.add(ClubCoachPackOpeningCard(opening_id=opening.id, club_coach_card_id=club_coach_card.id, is_new_coach=is_new))
            opened_cards.append(OpenedClubCoachCardOut(card=club_coach_card, is_new=is_new))

        await db.commit()
    except IntegrityError:
        # Same idempotency-key race as open_club_pack's own handler —
        # concurrent identical requests can collide on
        # uq_club_coach_pack_opening_idempotency.
        await db.rollback()
        existing = await db.execute(
            select(ClubCoachPackOpening).where(ClubCoachPackOpening.club_id == club_id, ClubCoachPackOpening.idempotency_key == idempotency_key)
        )
        existing_opening = existing.scalar_one_or_none()
        if existing_opening is not None:
            return await _get_result_for_existing_opening(db, existing_opening)
        raise

    await db.refresh(club)
    return ClubCoachPackOpenResult(pack=pack, cards=opened_cards, new_budget=club.budget)
```

`_get_result_for_existing_opening`'s `_ClubForBudget` placeholder is
wrong — read `club_pack_service.py::_get_result_for_existing_opening`'s
actual full text (not just the excerpt already quoted in this plan) to
see exactly how it re-fetches the club/budget for the idempotent-replay
path, and copy that exact pattern instead (likely `await db.get(Club,
opening.club_id)` — `Club` imported from `app.models.club`). Fix this
before writing the test in Step 6.

- [ ] **Step 6: Create the schema and router, write the failing router test**

Create `backend/app/schemas/club_coach_pack.py`, mirroring
`backend/app/schemas/club_pack.py`'s `ClubPackOpenResult`/
`OpenedClubCardOut` shapes (read that file first for the exact field
names/types to mirror):

```python
from pydantic import BaseModel, ConfigDict

from app.schemas.club_squad import ClubCoachCardOut  # see Task 5 — defined there


class ClubCoachPackRarityProbabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rarity: str
    probability: float


class ClubCoachPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    description: str
    price: int
    card_count: int
    image_path: str | None
    is_active: bool
    rarity_probabilities: list[ClubCoachPackRarityProbabilityOut]


class OpenedClubCoachCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    card: ClubCoachCardOut
    is_new: bool


class ClubCoachPackOpenResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pack: ClubCoachPackOut
    cards: list[OpenedClubCoachCardOut]
    new_budget: int
```

This imports `ClubCoachCardOut` from `app.schemas.club_squad` — that
schema is defined in Task 5 (it's the natural home, alongside
`ClubLineupOut`/`EquippedCoachOut`, since it represents an owned coach
card the same way `ClubCardOut` already lives in that file next to
`ClubLineupOut`). **Reorder if needed**: if Task 3 is implemented before
Task 5 lands, this import will fail — either implement Task 5's
`ClubCoachCardOut` schema first (a small, self-contained addition, safe
to pull earlier), or accept this plan's task order requires Task 5's
schema addition to exist before Task 3's router file imports it (i.e.
execute Task 5's schema-only portion before Task 3's Step 6, or simply
execute the tasks in a different order than numbered — flag this
explicitly to whoever runs subagent-driven-development on this plan: add
`ClubCoachCardOut` to `club_squad.py` as part of THIS task's Step 6
instead of waiting for Task 5, since Task 3 needs it first
chronologically. `ClubCoachCardOut` mirrors the existing `ClubCardOut` in
that same file exactly: `id: int, serial_number: int, coach: CoachOut,
acquired_at: datetime` (reuse Phase 1's `CoachOut` from `app.schemas.coach`).

New `backend/app/routers/club_coach_packs.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.club_coach_pack import ClubCoachPack
from app.models.user import User
from app.schemas.club_coach_pack import ClubCoachPackOpenResult, ClubCoachPackOut
from app.services.club_coach_pack_service import open_club_coach_pack
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/coach-packs", response_model=list[ClubCoachPackOut])
async def list_club_coach_packs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ClubCoachPack).where(ClubCoachPack.is_active.is_(True)).options(joinedload(ClubCoachPack.rarity_probabilities)).order_by(ClubCoachPack.sort_order)
    )
    return result.unique().scalars().all()


class OpenClubCoachPackRequest(BaseModel):
    idempotency_key: Optional[str] = None


@router.post("/me/coach-packs/{club_coach_pack_id}/open", response_model=ClubCoachPackOpenResult)
async def open_club_coach_pack_route(
    club_coach_pack_id: int, payload: OpenClubCoachPackRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    result = await open_club_coach_pack(db, user, club_coach_pack_id, payload.idempotency_key)
    await db.commit()
    return result
```

Check `backend/app/routers/clubs.py` for the exact route path convention
this repo already uses for the equivalent PLAYER club-pack endpoints
(`GET /clubs/packs`, `POST /clubs/me/packs/{id}/open` per the frontend
precedent already confirmed) — this new router's paths
(`/clubs/coach-packs`, `/clubs/me/coach-packs/{id}/open`) mirror that
exactly; confirm `get_current_user`'s import path matches whatever
`clubs.py`'s own routes already use (may be `get_current_user` from
`app.core.dependencies`, confirm before assuming).

Now write the failing router test in
`backend/tests/test_club_coach_pack_service.py` (same file as Step 2,
appended):

```python
from tests.utils import telegram_headers


async def test_open_club_coach_pack_debits_budget_and_grants_coach(client, db_session, bot_token, seed_club_with_budget):
    # Follow whatever pattern this repo's existing test_club_packs.py uses
    # to get an authenticated club captain with a funded club — mirror
    # that fixture/setup exactly rather than reinventing it.
    ...
```

Read `backend/tests/test_club_packs.py` in full before writing this test
— copy its exact setup pattern (club creation, captain auth, budget
funding) for the coach-pack equivalent, asserting: a successful open
debits the club's budget by the pack's price, creates a `ClubCoachCard`
owned by that club, and a repeated call with the same idempotency key
returns the identical result without double-charging.

- [ ] **Step 7: Register the router in `main.py`**

Add `club_coach_packs` to the import list and
`app.include_router(club_coach_packs.router, prefix=API_PREFIX)` near
the existing club-related router registrations.

- [ ] **Step 8: Run all the tests in this task, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_pack_service.py tests/ -v`
Expected: task tests PASS; full suite shows only already-known
pre-existing failures/skips (see this plan's Global Constraints for how
to distinguish those from a real regression).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/pack_service.py backend/app/services/club_coach_pack_service.py backend/app/schemas/club_coach_pack.py backend/app/schemas/club_squad.py backend/app/routers/club_coach_packs.py backend/app/main.py backend/tests/test_club_coach_pack_service.py
git commit -m "feat(coaches): add club coach pack purchase/opening flow"
```

---

### Task 4: Admin CRUD for `ClubCoachPack`

**Files:**
- Create: `backend/app/schemas/admin_club_coach_pack.py` (or fold into
  `club_coach_pack.py` if this repo's existing `club_pack.py`/
  `admin`-facing schemas already share one file — check
  `backend/app/schemas/club_pack.py` first to see whether
  `ClubPackCreate`/`ClubPackUpdate` live there or in a separate admin
  schema file, and match that convention exactly)
- Create: `backend/app/routers/admin_club_coach_packs.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_club_coach_packs.py`

**Interfaces:**
- Consumes: `ClubCoachPack`/`ClubCoachPackRarityProbability` (Task 2).
- Produces: `GET/POST /admin/club-coach-packs`, `PUT/DELETE
  /admin/club-coach-packs/{id}` — Task 13 (frontend admin page) consumes
  these.

- [ ] **Step 1: Write the failing router tests**

Mirror whatever `backend/tests/test_admin_club_packs.py` already does
for `ClubPack` CRUD (read that file in full first) — same shape, same
assertions, for `ClubCoachPack` instead. Include at minimum: create with
valid rarity probabilities, create rejected when probabilities don't sum
to ~1.0, list, update.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_admin_club_coach_packs.py -v`
Expected: FAIL — `404`s (router doesn't exist yet).

- [ ] **Step 3: Create the schemas and router**

Mirror `backend/app/routers/admin_club_packs.py` (already read in full
this session) exactly: `_get_pack_or_404` (against `ClubCoachPack`),
`_validate_probabilities` (identical logic, reusable verbatim if that
function is generic enough to import directly rather than duplicate —
check whether it's already written generically over any "has
`.probability`" list; if so, import and reuse it instead of copy-pasting),
`GET ""` list, `POST ""` create, `PUT "/{id}"` update, at
`prefix="/admin/club-coach-packs"`.

Create `ClubCoachPackCreate`/`ClubCoachPackUpdate` schemas mirroring
whatever `ClubPackCreate`/`ClubPackUpdate` already look like (read
`backend/app/schemas/club_pack.py` for the exact fields/validators
first) — same fields minus anything player-specific, plus
`rarity_probabilities: list[...]` following that same existing pattern.

- [ ] **Step 4: Register the router in `main.py`**

Add the import + `app.include_router(admin_club_coach_packs.router,
prefix=API_PREFIX)`.

- [ ] **Step 5: Run the tests to verify they pass, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_admin_club_coach_packs.py tests/ -v`
Expected: task tests PASS; full suite shows only known pre-existing
issues.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/admin_club_coach_pack.py backend/app/routers/admin_club_coach_packs.py backend/app/main.py backend/tests/test_admin_club_coach_packs.py
git commit -m "feat(coaches): add admin CRUD for club coach packs"
```

(Adjust the `git add` file list if Step 3 folded schemas into an
existing file instead of creating a new one.)

---

### Task 5: Club coach equip — model, service, endpoint, schema

**Files:**
- Modify: `backend/app/models/club_lineup.py` (add `club_coach_card_id` + relationship)
- Create: `backend/alembic/versions/00NN_club_lineup_coach.py`
- Modify: `backend/app/schemas/club_squad.py` (add `EquippedCoachOut`,
  `ClubCoachCardOut` if not already added by Task 3's reordering note,
  `ClubCoachSetRequest`, extend `ClubLineupOut`)
- Modify: `backend/app/services/club_squad_service.py` (`_get_or_none_lineup`'s
  joinedload chain, `_lineup_to_out`, new `set_club_coach`, new
  `list_club_coach_cards`)
- Modify: `backend/app/routers/clubs.py` (`PUT /clubs/me/coach`, `GET
  /clubs/me/coach-cards`)
- Test: `backend/tests/test_club_coach_equip.py`

**Interfaces:**
- Consumes: `ClubCoachCard` (Task 1), `CoachOut`/`CoachBoostOut` (Phase 1,
  `app.schemas.coach`).
- Produces: `set_club_coach(db, user, payload: ClubCoachSetRequest) ->
  ClubLineupOut`, `ClubLineupOut.coach: EquippedCoachOut | None` — Task 8
  (match-engine wiring) and Task 11 (frontend equip UI) both consume the
  `club_coach_card_id` column and `set_club_coach`'s behavior.

- [ ] **Step 1: Add `club_coach_card_id` to `ClubLineup`**

`backend/app/models/club_lineup.py` currently (full file already read):
```python
class ClubLineup(Base):
    __tablename__ = "club_lineups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    formation: Mapped[str] = mapped_column(String(16), default="4-3-3", nullable=False, server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), default="BALANCED", nullable=False, server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), default="CENTRAL_PLAY", nullable=False, server_default="CENTRAL_PLAY")
    cards: Mapped[list["ClubLineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")
```
Add, after `playstyle`:
```python
    club_coach_card_id: Mapped[int | None] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True)

    club_coach_card: Mapped["ClubCoachCard | None"] = relationship(lazy="joined")
```

- [ ] **Step 2: Write the migration**

```python
"""ClubLineup.club_coach_card_id

Revision ID: 00NN
Revises: <Task 2's migration revision — the last task to actually add one;
Tasks 3 and 4 are router/service-only and never create a migration file,
so do NOT chain off either of them>
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "00NN"
down_revision = "<Task 2's migration revision>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("club_coach_card_id", sa.Integer(), sa.ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_club_lineups_club_coach_card_id", "club_lineups", ["club_coach_card_id"])


def downgrade() -> None:
    op.drop_index("ix_club_lineups_club_coach_card_id", table_name="club_lineups")
    op.drop_column("club_lineups", "club_coach_card_id")
```

Verify: `cd backend && alembic upgrade head --sql`.

- [ ] **Step 3: Extend `club_squad.py` schemas**

`backend/app/schemas/club_squad.py`'s `ClubLineupOut`
(`lines 23-31`, full text already read) currently:
```python
class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    tactical_fit_hint: str
    slots: list[ClubLineupSlotOut]
```
Add `coach: "EquippedCoachOut | None"` as a new field. Add these two new
schemas to the same file (or wherever this file's other small nested
schemas already live):

```python
from app.schemas.coach import CoachBoostOut


class EquippedCoachOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str
    rarity: str
    image_path: str | None
    boosts: list[CoachBoostOut]


class ClubCoachCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    serial_number: int
    coach: EquippedCoachOut
    acquired_at: datetime


class ClubCoachSetRequest(BaseModel):
    club_coach_card_id: int | None
```

(If Task 3 already added `ClubCoachCardOut` to this file per its own
Step 6 reordering note, don't duplicate it here — just add
`EquippedCoachOut`, `ClubCoachSetRequest`, and the `ClubLineupOut.coach`
field in this task instead.)

- [ ] **Step 4: Write the failing service/endpoint tests**

Create `backend/tests/test_club_coach_equip.py`:

```python
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach, CoachBoost
from app.models.enums import ClubCoachCardSource, CoachBoostType, Rarity
from app.services.club_squad_service import set_club_coach
from app.schemas.club_squad import ClubCoachSetRequest


async def test_captain_can_equip_and_clear_club_coach(db_session, seed_club_with_captain_and_lineup):
    # Follow whatever pattern test_club_squad.py already uses to build a
    # club with a captain User and an existing ClubLineup row — mirror it
    # exactly rather than reinventing setup.
    club, captain, lineup = seed_club_with_captain_and_lineup

    coach = Coach(display_name="Equip Test Coach", rarity=Rarity.epic)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    card = ClubCoachCard(club_id=club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    await db_session.commit()

    result = await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=card.id))
    assert result.coach is not None
    assert result.coach.display_name == "Equip Test Coach"
    assert len(result.coach.boosts) == 2

    cleared = await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=None))
    assert cleared.coach is None


async def test_cannot_equip_another_clubs_coach_card(db_session, seed_club_with_captain_and_lineup, seed_second_club):
    club, captain, lineup = seed_club_with_captain_and_lineup
    other_club = seed_second_club

    coach = Coach(display_name="Foreign Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()
    foreign_card = ClubCoachCard(club_id=other_club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(foreign_card)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=foreign_card.id))
```

Add `import pytest` and `from app.core.exceptions import ConflictError`
at the top. Check `backend/tests/test_club_squad.py` for the exact
existing fixture names/patterns for "a club with a captain and an
existing lineup" and "a second, unrelated club" — reuse those exact
fixtures/helpers rather than inventing `seed_club_with_captain_and_lineup`/
`seed_second_club` from scratch if equivalent ones already exist.

- [ ] **Step 5: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_equip.py -v`
Expected: FAIL — `ImportError: cannot import name 'set_club_coach'`.

- [ ] **Step 6: Extend `_get_or_none_lineup`'s joinedload chain**

`backend/app/services/club_squad_service.py:137-152` (full text already
read) currently:
```python
    result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card))
        .execution_options(populate_existing=True)
    )
```
Extend the `.options(...)` chain to also eager-load the equipped coach:
```python
    result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(
            joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card),
            joinedload(ClubLineup.club_coach_card).joinedload(ClubCoachCard.coach).joinedload(Coach.boosts),
        )
        .execution_options(populate_existing=True)
    )
```
Add `from app.models.club_coach_card import ClubCoachCard` and `from
app.models.coach import Coach` to this file's imports.

- [ ] **Step 7: Add `set_club_coach` and update `_lineup_to_out`**

Add, near `set_club_tactics` (mirroring its exact locking/gating shape,
`backend/app/services/club_squad_service.py:299-335`):

```python
async def set_club_coach(db: AsyncSession, user: User, payload: ClubCoachSetRequest) -> ClubLineupOut:
    """PUT /clubs/me/coach — mirrors set_club_tactics's captain/assistant-
    only gating and row-locking. A None club_coach_card_id clears the
    equipped coach."""
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    if payload.club_coach_card_id is not None:
        card = await db.get(ClubCoachCard, payload.club_coach_card_id)
        if card is None or card.club_id != club_id:
            raise ConflictError("Тренер не принадлежит этому клубу")

    lineup_result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards)).with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    lineup.club_coach_card_id = payload.club_coach_card_id
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id)
```

Update `_lineup_to_out` (`club_squad_service.py:172-204`, full text
already read) — after computing `tactical_fit_hint`, add:
```python
    coach_out = None
    if lineup and lineup.club_coach_card:
        coach_out = EquippedCoachOut.model_validate(lineup.club_coach_card.coach)
```
and add `coach=coach_out` to the `ClubLineupOut(...)` constructor call.
Import `EquippedCoachOut` from `app.schemas.club_squad` (same file, no
cross-file import needed if you added it there in Step 3).

Also add a small `list_club_coach_cards(db, user) -> list[ClubCoachCardOut]`
function mirroring `list_club_cards` (`club_squad_service.py:162-169`,
already read) — queries `ClubCoachCard` filtered by the caller's
`club_id`, ordered by `acquired_at`.

- [ ] **Step 8: Add the router endpoints**

In `backend/app/routers/clubs.py`, near the existing `PUT
/clubs/me/tactics` route (find it first — this plan doesn't reproduce
`clubs.py`'s full route tree, so read the file to place these
consistently with the existing club-squad routes' grouping):

```python
@router.put("/me/coach", response_model=ClubLineupOut)
async def set_club_coach_route(payload: ClubCoachSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await club_squad_service.set_club_coach(db, user, payload)
    return result


@router.get("/me/coach-cards", response_model=list[ClubCoachCardOut])
async def list_club_coach_cards_route(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.list_club_coach_cards(db, user)
```

Match whatever import style (`club_squad_service.X` vs. importing `X`
directly) `clubs.py` already uses for its other `club_squad_service`
calls.

- [ ] **Step 9: Run the tests to verify they pass, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_coach_equip.py tests/ -v`
Expected: task tests PASS; full suite shows only known pre-existing
issues. Specifically re-run `tests/test_club_squad.py` in this same
command — confirm the `_get_or_none_lineup` joinedload extension didn't
break any existing club-squad test (a wrong relationship/join could
silently duplicate rows or change an existing query's row count).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/club_lineup.py backend/alembic/versions/00NN_club_lineup_coach.py backend/app/schemas/club_squad.py backend/app/services/club_squad_service.py backend/app/routers/clubs.py backend/tests/test_club_coach_equip.py
git commit -m "feat(coaches): add club coach equip endpoint and lineup FK"
```

---

### Task 6: Wire boost hooks into `compute_profile` (zone + depth bonus)

**Files:**
- Modify: `backend/app/services/club_tactical_profile_service.py`
- Test: `backend/tests/test_club_tactical_profile_service.py`

**Interfaces:**
- Consumes: `resolve_active_boosts`, `apply_zone_boosts`,
  `depth_bonus_cap_for` (Phase 1, `coach_boost_service.py`).
- Produces: `compute_profile(cards_with_slots, coach: "Coach | None" =
  None) -> TeamTacticalProfile` — Task 7 (`build_side`) consumes this new
  optional parameter.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_club_tactical_profile_service.py` (read the
file's existing imports/fixtures first to match its style — it already
has helpers for building `cards_with_slots` fixtures for
`compute_profile`'s existing tests; reuse those, don't invent new ones):

```python
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity


def test_compute_profile_with_no_coach_matches_current_behavior(<existing fixture args>):
    # Reuse whatever cards_with_slots fixture this file's existing
    # compute_profile tests already use.
    profile_without_arg = compute_profile(cards_with_slots)
    profile_with_none = compute_profile(cards_with_slots, coach=None)
    assert profile_without_arg == profile_with_none


def test_compute_profile_applies_attack_central_boost(<existing fixture args>):
    coach = Coach(display_name="Attack Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=5.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=5.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=5.0),
    ]
    base = compute_profile(cards_with_slots)
    boosted = compute_profile(cards_with_slots, coach=coach)
    assert boosted.central_attack == round(min(99.0, base.central_attack + 5.0), 1)
    assert boosted.wing_attack == base.wing_attack  # unaffected zone stays exactly the same


def test_compute_profile_squad_stability_raises_effective_depth_cap(<existing fixture args>):
    coach = Coach(display_name="Stability Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.SQUAD_STABILITY, magnitude=2.0)]
    # Use a fixture with real formation depth (weight_total meaningfully
    # above 1.0 in at least one zone, e.g. a 3-5-2-shaped midfield) so the
    # depth bonus is actually near its cap pre-boost — check this file's
    # existing depth-bonus tests for which fixture already produces that,
    # and reuse it, rather than building a new one.
    base = compute_profile(cards_with_slots_with_real_depth)
    boosted = compute_profile(cards_with_slots_with_real_depth, coach=coach)
    assert boosted.midfield_control >= base.midfield_control  # never LOWER with a positive boost
```

The exact fixture names above (`cards_with_slots`,
`cards_with_slots_with_real_depth`) are placeholders for whatever this
file's existing tests actually call their own — replace with the real
names once you've read the file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_tactical_profile_service.py -v`
Expected: the 2 new coach-specific tests FAIL with a `TypeError`
(`compute_profile() got an unexpected keyword argument 'coach'`); the
"matches current behavior" test also fails for the same reason on its
`coach=None` call.

- [ ] **Step 3: Update `compute_profile`**

`backend/app/services/club_tactical_profile_service.py:80-97` currently:
```python
def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]]) -> TeamTacticalProfile:
    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        if weight_total > 0:
            base_avg = weighted_sum / weight_total
            depth_bonus = max(0.0, min(DEPTH_BONUS_CAP, DEPTH_BONUS_SCALE * (weight_total - 1.0)))
            zone_values[zone] = round(min(99.0, base_avg + depth_bonus), 1)
        else:
            zone_values[zone] = 0.0

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)
```
Change to:
```python
def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]], coach: "Coach | None" = None) -> TeamTacticalProfile:
    boosts = resolve_active_boosts(coach)
    depth_cap = depth_bonus_cap_for(DEPTH_BONUS_CAP, boosts)

    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        if weight_total > 0:
            base_avg = weighted_sum / weight_total
            depth_bonus = max(0.0, min(depth_cap, DEPTH_BONUS_SCALE * (weight_total - 1.0)))
            zone_values[zone] = round(min(99.0, base_avg + depth_bonus), 1)
        else:
            zone_values[zone] = 0.0

    zone_values = apply_zone_boosts(zone_values, boosts)
    zone_values = {zone: round(min(99.0, value), 1) for zone, value in zone_values.items()}

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)
```
Note the boost is applied AFTER the depth-bonus/base-average computation
and re-clamped to 99.0 — a zone that's already at the 99.0 ceiling from
card ratings alone must not exceed it just because a coach boost is
also present (matches spec §5's "flat rating points, capped at 99"
framing). A zone that was `0.0` (no eligible contributor at all — e.g. a
squad using a formation with no goalkeeper slot filled) intentionally
stays boostable too — a coach can't invent a zone from nothing, but if
the zone legitimately has SOME weight, the boost adds to whatever's
there.

Add the two new imports at the top of the file:
```python
from app.models.coach import Coach
from app.services.coach_boost_service import apply_zone_boosts, depth_bonus_cap_for, resolve_active_boosts
```

- [ ] **Step 4: Run the tests to verify they pass, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_tactical_profile_service.py tests/ -v`
Expected: task tests PASS. Full suite: confirm no regression in any
OTHER test that calls `compute_profile` positionally without `coach=`
(the new parameter is optional with a default, so this should be a
non-issue, but verify — grep `compute_profile(` across the whole
`backend/` tree first to find every call site and confirm none of them
break).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/club_tactical_profile_service.py backend/tests/test_club_tactical_profile_service.py
git commit -m "feat(coaches): wire zone and depth-bonus boosts into compute_profile"
```

---

### Task 7: Wire boost hooks into `club_tactical_matchup_service.py`

**Files:**
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py`

**Interfaces:**
- Consumes: `compute_profile(cards_with_slots, coach=...)` (Task 6),
  `defensive_shift_for`, `transition_bonus_for`, `first_pass_input_bonus`,
  `initiative_mult_for`, `resolve_active_boosts` (Phase 1,
  `coach_boost_service.py`).
- Produces: `ClubTacticalSide.coach: "Coach | None" = None` (new field),
  `build_side(cards_with_slots, mentality, playstyle, coach: "Coach |
  None" = None) -> ClubTacticalSide` — Task 8 (the `tournament_simulation_service.py`
  callers) consumes this new optional parameter.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_club_tactical_matchup_service.py` (read the
file's existing fixtures for building a `ClubTacticalSide`/duel-ready
card list first — reuse those exactly):

```python
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity


def test_defender_ratio_shift_for_applies_defensive_discipline_only_when_attacking(<existing side fixture>):
    coach = Coach(display_name="Discipline Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.DEFENSIVE_DISCIPLINE, magnitude=0.02)]
    attacking_side = ClubTacticalSide(cards=<...>, profile=<...>, mentality="ATTACKING", playstyle="BALANCED", coach=coach)
    balanced_side = ClubTacticalSide(cards=<...>, profile=<...>, mentality="BALANCED", playstyle="BALANCED", coach=coach)

    shift_attacking = defender_ratio_shift_for(attacking_side)
    shift_balanced = defender_ratio_shift_for(balanced_side)
    assert shift_attacking > MENTALITY_DEFENSE_SHIFT["ATTACKING"]  # boost narrowed the penalty
    assert shift_balanced == MENTALITY_DEFENSE_SHIFT["BALANCED"]  # no-op for non-ATTACKING


def test_defender_ratio_shift_for_never_exceeds_zero_with_extreme_coach_magnitude(<existing side fixture>):
    coach = Coach(display_name="Extreme Coach", rarity=Rarity.legendary)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.DEFENSIVE_DISCIPLINE, magnitude=100.0)]
    side = ClubTacticalSide(cards=<...>, profile=<...>, mentality="ATTACKING", playstyle="BALANCED", coach=coach)
    assert defender_ratio_shift_for(side) == 0.0  # regression test for coach_boost_service.py's own clamp


def test_build_side_threads_coach_into_profile(<existing cards_with_slots fixture>):
    coach = Coach(display_name="Profile Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=3.0)]
    side_without = build_side(cards_with_slots, "BALANCED", "CENTRAL_PLAY")
    side_with = build_side(cards_with_slots, "BALANCED", "CENTRAL_PLAY", coach=coach)
    assert side_with.profile.central_attack > side_without.profile.central_attack
    assert side_with.coach is coach
```

Replace `<existing side fixture>`/`<existing cards_with_slots fixture>`/
`<...>` with this file's real existing fixture helpers once read — do
not invent new card-building helpers if this file already has them
(it does, per this file's own existing tests for `zone_ratio`/
`resolve_counter`/etc.).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_tactical_matchup_service.py -v`
Expected: FAIL — `TypeError: ClubTacticalSide.__init__() got an
unexpected keyword argument 'coach'`.

- [ ] **Step 3: Add `coach` to `ClubTacticalSide` and thread it through `build_side`**

`backend/app/services/club_tactical_matchup_service.py:232-237` currently:
```python
@dataclass
class ClubTacticalSide:
    cards: list[Any]
    profile: TeamTacticalProfile
    mentality: str
    playstyle: str
```
Change to:
```python
@dataclass
class ClubTacticalSide:
    cards: list[Any]
    profile: TeamTacticalProfile
    mentality: str
    playstyle: str
    coach: "Coach | None" = None
```

`build_side` (`club_tactical_matchup_service.py:427-430`) currently:
```python
def build_side(cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots)
    cards = [card for card, _slot in cards_with_slots]
    return ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle)
```
Change to:
```python
def build_side(cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str, coach: "Coach | None" = None) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots, coach=coach)
    cards = [card for card, _slot in cards_with_slots]
    return ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle, coach=coach)
```

Add `from app.models.coach import Coach` to this file's imports (near
the existing `from app.services.club_tactical_profile_service import
TeamTacticalProfile, position_fit, zone_weight` line — also add
`compute_profile` to that same import if it isn't already imported at
module scope; check the file's existing local `from
app.services.club_tactical_profile_service import compute_profile` at
line 286 — this may already cover it, in which case don't add a
duplicate import).

- [ ] **Step 4: Wire `defender_ratio_shift_for` (DEFENSIVE_DISCIPLINE)**

`club_tactical_matchup_service.py:396-400` currently:
```python
def defender_ratio_shift_for(defender: "ClubTacticalSide") -> float:
    shift = MENTALITY_DEFENSE_SHIFT[defender.mentality]
    if defender.playstyle == "HIGH_PRESS":
        shift += HIGH_PRESS_DEFENSE_SHIFT
    return shift
```
Change to:
```python
def defender_ratio_shift_for(defender: "ClubTacticalSide") -> float:
    shift = MENTALITY_DEFENSE_SHIFT[defender.mentality]
    if defender.playstyle == "HIGH_PRESS":
        shift += HIGH_PRESS_DEFENSE_SHIFT
    return defensive_shift_for(defender.mentality, shift, resolve_active_boosts(defender.coach))
```

- [ ] **Step 5: Wire `resolve_counter`'s `TRANSITION_BONUS`/first-pass sites (COUNTER_MASTERY + PASSING_ACCURACY)**

`club_tactical_matchup_service.py:265` currently:
```python
    eff_y = y_duelist.player.rating * position_fit(y_duelist.player.position, zone) * TRANSITION_BONUS[y.playstyle] * _first_pass_quality_factor(y.profile.midfield_control)
```
Change to:
```python
    y_boosts = resolve_active_boosts(y.coach)
    transition_bonus = transition_bonus_for(y.playstyle, TRANSITION_BONUS[y.playstyle], y_boosts)
    midfield_for_pass = y.profile.midfield_control + first_pass_input_bonus(y_boosts)
    eff_y = y_duelist.player.rating * position_fit(y_duelist.player.position, zone) * transition_bonus * _first_pass_quality_factor(midfield_for_pass)
```
(Insert this right before the existing `eff_y = ...` line, inside
`resolve_counter`, `club_tactical_matchup_service.py:249-`.)

- [ ] **Step 6: Wire `initiative_probability` (BALL_CONTROL)**

`initiative_probability` (`club_tactical_matchup_service.py:64-68`)
currently:
```python
def initiative_probability(profile_a: TeamTacticalProfile, mentality_a: str, profile_b: TeamTacticalProfile, mentality_b: str) -> float:
    score_a = profile_a.midfield_control * INITIATIVE_MULT[mentality_a]
    score_b = profile_b.midfield_control * INITIATIVE_MULT[mentality_b]
    total = score_a + score_b
    return score_a / total if total else 0.5
```
Its only caller, `simulate_phase` (`club_tactical_matchup_service.py:522-526`):
```python
def simulate_phase(minute: int, side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> Chance | None:
    p_a_initiative = initiative_probability(side_a.profile, side_a.mentality, side_b.profile, side_b.mentality)
    if random.random() < p_a_initiative:
        return _resolve_progression_and_duel(side_a, side_b, "a", minute, config)
    return _resolve_progression_and_duel(side_b, side_a, "b", minute, config)
```
Change `initiative_probability`'s signature to take the two sides
directly (simpler than adding 2 more positional params, and this
function has exactly one caller so there's no wider API to preserve):
```python
def initiative_probability(side_a: "ClubTacticalSide", side_b: "ClubTacticalSide") -> float:
    mult_a = initiative_mult_for(INITIATIVE_MULT[side_a.mentality], resolve_active_boosts(side_a.coach))
    mult_b = initiative_mult_for(INITIATIVE_MULT[side_b.mentality], resolve_active_boosts(side_b.coach))
    score_a = side_a.profile.midfield_control * mult_a
    score_b = side_b.profile.midfield_control * mult_b
    total = score_a + score_b
    return score_a / total if total else 0.5
```
And its call site:
```python
    p_a_initiative = initiative_probability(side_a, side_b)
```
This is a signature change to an existing function — grep
`initiative_probability(` across the whole `backend/` tree (including
`backend/scripts/`) to confirm `simulate_phase` really is its only
caller before making this change; if `scripts/simulate_tactical_matrix.py`
or `scripts/simulate_tactical_balance.py` also call it directly (plausible,
since those scripts exercise this file's functions for balance testing),
update those call sites too or note in the commit message that they need
a follow-up (don't silently break the balance-simulation tooling this
session built).

- [ ] **Step 7: Add the new imports**

At the top of `club_tactical_matchup_service.py`, alongside the existing
`from app.services.club_tactical_profile_service import ...` line:
```python
from app.services.coach_boost_service import (
    defensive_shift_for,
    first_pass_input_bonus,
    initiative_mult_for,
    resolve_active_boosts,
    transition_bonus_for,
)
```

- [ ] **Step 8: Run the tests to verify they pass, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_tactical_matchup_service.py tests/test_club_tactical_balance.py tests/ -v`
Expected: task tests PASS; `test_club_tactical_balance.py` (Phase 1's
own pre-coach balance suite) must ALSO still pass unchanged — every
touched function's new behavior is a strict no-op when `coach=None`
(`resolve_active_boosts(None)` returns an empty dict, every
`coach_boost_service.py` function is proven in Phase 1 to be a no-op
against an empty `ActiveCoachBoosts`), so no existing balance assertion
should move at all. If any DOES move, that's a real regression — do not
adjust the pre-existing test's expected values, fix the wiring instead.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/club_tactical_matchup_service.py backend/tests/test_club_tactical_matchup_service.py
git commit -m "feat(coaches): wire mentality/counter-attack/initiative boosts into the matchup engine"
```

---

### Task 8: Thread the equipped coach through `tournament_simulation_service.py`

**Files:**
- Modify: `backend/app/services/tournament_simulation_service.py`
- Test: `backend/tests/test_tournament_simulation_service.py`

**Interfaces:**
- Consumes: `build_side(..., coach=...)` (Task 7), `ClubLineup.club_coach_card`
  relationship (Task 5).
- Produces: nothing new consumed by a later task — this is the final
  integration point connecting equip data to real tournament matches.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tournament_simulation_service.py` (read the
file's existing setup for simulating a round between two clubs with real
lineups first — reuse that exact fixture/helper chain rather than
building a new one):

```python
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach, CoachBoost
from app.models.enums import ClubCoachCardSource, CoachBoostType, Rarity


async def test_equipped_coach_boosts_flow_into_simulated_match(db_session, <existing two-club-with-lineups fixture>):
    club_a, club_b, lineup_a, lineup_b = <existing fixture unpacking>

    coach = Coach(display_name="Simulation Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=8.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    card = ClubCoachCard(club_id=club_a.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    await db_session.flush()
    lineup_a.club_coach_card_id = card.id
    db_session.add(lineup_a)
    await db_session.commit()

    lineup_a_reloaded, _, cards_with_slots_a, club_lineup_a = await resolve_match_lineup(db_session, club_a.id)
    side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle, coach=club_lineup_a.club_coach_card.coach if club_lineup_a.club_coach_card else None)
    assert side_a.coach is not None
    assert side_a.coach.display_name == "Simulation Coach"
```

This test exercises the exact same `resolve_match_lineup` →
`club_lineup.club_coach_card.coach` → `build_side(..., coach=...)` chain
the real round-simulation code path (Step 3 below) uses — replace
`<existing two-club-with-lineups fixture>` with whatever this file
already has (it must, since existing round-simulation tests already
build two full clubs with lineups).

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_tournament_simulation_service.py -v`
Expected: FAIL — `side_a.coach` is `None` (the real call site doesn't
pass `coach=` yet).

- [ ] **Step 3: Update the 2 `build_side` call sites**

`backend/app/services/tournament_simulation_service.py:280-281` currently:
```python
            side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle)
            side_b = build_side(cards_with_slots_b, club_lineup_b.mentality, club_lineup_b.playstyle)
```
Change to:
```python
            coach_a = club_lineup_a.club_coach_card.coach if club_lineup_a.club_coach_card else None
            coach_b = club_lineup_b.club_coach_card.coach if club_lineup_b.club_coach_card else None
            side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle, coach=coach_a)
            side_b = build_side(cards_with_slots_b, club_lineup_b.mentality, club_lineup_b.playstyle, coach=coach_b)
```
This works without any further query changes because `resolve_match_lineup`
(same file, line 34-) already returns `club_lineup_a`/`club_lineup_b` as
whatever `_get_or_none_lineup` (`club_squad_service.py`) produces, and
Task 5 Step 6 already extended THAT function's joinedload chain to
eager-load `club_coach_card.coach.boosts` — no lazy-load risk here.

- [ ] **Step 4: Run the test to verify it passes, then the full suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_tournament_simulation_service.py tests/ -v`
Expected: task test PASSES; full suite shows only known pre-existing
issues (the 2 Postgres-only tests in this same file that skip under a
standalone `docker run` per this plan's Setup ruling notes — confirm you
see the SAME 2 skipping, not the new test skipping for the same reason,
which would indicate it wrongly needs real Postgres when it shouldn't).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_simulation_service.py backend/tests/test_tournament_simulation_service.py
git commit -m "feat(coaches): thread the equipped club coach into tournament match simulation"
```

---

### Task 9: Balance regression tests + simulation script extension

**Files:**
- Modify: `backend/scripts/simulate_tactical_matrix.py`
- Test: `backend/tests/test_coach_boost_balance.py`

**Interfaces:**
- Consumes: `build_side(..., coach=...)` (Task 7), full match simulation
  pipeline (existing, `tournament_match_engine.simulate_match` — check
  that module for its exact entry point signature before writing this
  task's tests, matching whatever `test_club_tactical_balance.py`
  already calls to run a full simulated match rather than guessing).

- [ ] **Step 1: Write the balance regression tests**

Create `backend/tests/test_coach_boost_balance.py`. Read
`backend/tests/test_club_tactical_balance.py` in full first — this new
file follows its exact style (many matches per data point, statistical
assertions with tolerance bands, never a single-match assertion) rather
than inventing a new testing approach:

```python
"""Coach-boost balance regression tests — mirrors test_club_tactical_balance.py's
style: many matches per comparison, statistical tolerance, never a
single-match assertion. Confirms a coach boost has a REAL but BOUNDED
effect — never enough to flip a large rating-gap matchup, matching this
session's own established balance-safety practice."""
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity


def test_legendary_coach_does_not_flip_a_large_rating_gap_matchup(<existing helpers>):
    """A ~200+ point team_strength gap (per this repo's own established
    target bands from the mentality/playstyle rebalance) should still
    heavily favor the stronger squad even when the WEAKER squad has a
    fully-loaded legendary coach and the stronger squad has none."""
    weak_coach = Coach(display_name="Weak Squad's Coach", rarity=Rarity.legendary)
    weak_coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=8.0),
    ]
    # Build a strong-squad-vs-weak-squad-with-coach matchup using this
    # file's own existing strength-gap fixture helpers (test_club_tactical_balance.py
    # already has these — reuse them, passing coach=weak_coach only to the
    # weak side's build_side call), run N=300+ matches, assert the weak
    # side's win rate stays well under 50% (a coach should narrow the gap
    # a little, not invert it) — pick the exact tolerance band by running
    # the simulation once and eyeballing a sane threshold, documenting the
    # observed number in a comment the way this session's other balance
    # tests already do (see MENTALITY_DEFENSE_SHIFT's own calibration
    # comment for the established style).
    ...


def test_defensive_discipline_boost_never_lets_attacking_defend_better_than_balanced(<existing helpers>):
    """Direct match-level regression test for coach_boost_service.py's own
    unit-tested clamp (Phase 1) — confirms the clamp holds at the FULL
    match-simulation level too, not just in the isolated function call."""
    ...
```

Given this task needs real fixture helpers from
`test_club_tactical_balance.py`, read that file's full content before
writing this one — do not guess its helper names.

- [ ] **Step 2: Run the tests to verify they fail, then pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_coach_boost_balance.py -v`
This task is inherently more exploratory than most (calibrating a real
tolerance band requires actually running the simulation first) — expect
to iterate: run once without assertions to observe real numbers, then
add assertions with a sane margin, matching how this session's earlier
tactical rebalance work was done (see `club_tactical_matchup_service.py`'s
own extensive calibration comments for the expected process).

- [ ] **Step 3: Extend `scripts/simulate_tactical_matrix.py`**

Read the script's existing structure first (it already has
`mentality_grid`/`playstyle_grid`/`strength_gap_sweep`-style functions
per this session's earlier work). Add a new function following the same
pattern, e.g. `coach_boost_sweep(...)`, that runs a strong-squad-vs-
weak-squad-with-various-coach-boost-combinations matrix and prints a
results table — mirroring the script's existing output style exactly
(this is a reusable diagnostic tool for future balance passes, not a
one-off script, matching how this session treated its earlier
`simulate_tactical_matrix.py`/`simulate_tactical_balance.py` additions).

- [ ] **Step 4: Run the full backend suite one more time**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -v`
Expected: PASS except known pre-existing issues.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_coach_boost_balance.py backend/scripts/simulate_tactical_matrix.py
git commit -m "test(coaches): add balance regression tests and simulation sweep for coach boosts"
```

---

### Task 10: Frontend — types + API clients

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/clubCoachPacks.ts`
- Modify: `frontend/src/api/clubSquad.ts` (or wherever `setClubTactics`
  already lives — check the exact file first)

**Interfaces:**
- Produces: `ClubCoachPack`, `ClubCoachCard`, `EquippedCoach` TS types,
  `ClubLineup.coach: EquippedCoach | null` field, `fetchClubCoachPacks`,
  `openClubCoachPack`, `fetchClubCoachCards`, `setClubCoach` — Tasks 11/12
  consume these.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, near the existing `ClubPack`/
`ClubLineup` interfaces (read their exact current shape first — this
plan's earlier research already confirmed `ClubLineup`'s current fields
include `tactical_fit_hint`; add `coach: EquippedCoach | null` to that
same interface):

```typescript
export interface EquippedCoach {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  boosts: CoachBoost[];
}

export interface ClubCoachCard {
  id: number;
  serial_number: number;
  coach: EquippedCoach;
  acquired_at: string;
}

export interface ClubCoachPackRarityProbability {
  rarity: Rarity;
  probability: number;
}

export interface ClubCoachPack {
  id: number;
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  image_path: string | null;
  is_active: boolean;
  rarity_probabilities: ClubCoachPackRarityProbability[];
}

export interface ClubCoachPackOpenResult {
  pack: ClubCoachPack;
  cards: { card: ClubCoachCard; is_new: boolean }[];
  new_budget: number;
}
```

Add `coach: EquippedCoach | null;` to the existing `ClubLineup`
interface.

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (additive types only).

- [ ] **Step 3: Add the API client functions**

Create `frontend/src/api/clubCoachPacks.ts`, mirroring
`frontend/src/api/clubPacks.ts` (14 lines, already read in full)
exactly:

```typescript
import { api } from "@/lib/api";
import type { ClubCoachPack, ClubCoachPackOpenResult } from "@/types";

export async function fetchClubCoachPacks(): Promise<ClubCoachPack[]> {
  const { data } = await api.get<ClubCoachPack[]>("/clubs/coach-packs");
  return data;
}

export async function openClubCoachPack(packId: number, idempotencyKey?: string): Promise<ClubCoachPackOpenResult> {
  const { data } = await api.post<ClubCoachPackOpenResult>(`/clubs/me/coach-packs/${packId}/open`, {
    idempotency_key: idempotencyKey ?? crypto.randomUUID(),
  });
  return data;
}
```

In whichever file already exports `setClubTactics`/`fetchClubLineup`
(confirm the exact path — this plan's earlier research referenced
`@/api/clubSquad` for `ClubSquadPage.tsx`'s imports), add:

```typescript
export async function fetchClubCoachCards(): Promise<ClubCoachCard[]> {
  const { data } = await api.get<ClubCoachCard[]>("/clubs/me/coach-cards");
  return data;
}

export async function setClubCoach(clubCoachCardId: number | null): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/coach", { club_coach_card_id: clubCoachCardId });
  return data;
}
```

Add `ClubCoachCard` to that file's existing `@/types` import line.

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/clubCoachPacks.ts frontend/src/api/clubSquad.ts
git commit -m "feat(coaches): add frontend club-coach types and API clients"
```

(Adjust the last `git add` path if Step 3 found `setClubTactics` living
in a different file than `clubSquad.ts`.)

---

### Task 11: Frontend — squad-page "Тренер" equip UI

**Files:**
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Consumes: `fetchClubCoachCards`, `setClubCoach`, `ClubCoachCard`,
  `EquippedCoach` (Task 10).

- [ ] **Step 1: Add the equip row**

In `frontend/src/pages/ClubSquadPage.tsx` (316 lines, full current state
already read this session), add a `fetchClubCoachCards` query and a
`setClubCoach` mutation near the existing `lineup`/`cards`
queries/mutations:

```tsx
  const { data: coachCards } = useQuery({ queryKey: ["clubs", "coach-cards"], queryFn: fetchClubCoachCards, enabled: canEdit });
  const setCoachMutation = useMutation({
    mutationFn: setClubCoach,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "lineup"] }),
    onError: (err) => setError(formatGameError(err, "Не удалось назначить тренера")),
  });
```

Add a new coach row, placed after the 3 existing `TacticSelect` rows
(after the closing `</div>` of the block at lines 97-121, before the
formation-grid `<div className="relative flex flex-col gap-3...">` at
line 122) — a `TacticSelect`-shaped row is the right fit here (a club
realistically owns very few coaches, so a compact dropdown beats a full
picker modal):

```tsx
        {canEdit && lineup && (
          <div className="mb-3">
            <TacticSelect
              label="Тренер"
              options={[
                { value: "", label: "Без тренера" },
                ...(coachCards ?? []).map((c) => ({ value: String(c.id), label: c.coach.display_name })),
              ]}
              value={lineup.coach ? String((coachCards ?? []).find((c) => c.coach.id === lineup.coach!.id)?.id ?? "") : ""}
              disabled={setCoachMutation.isPending}
              onChange={(value) => setCoachMutation.mutate(value ? Number(value) : null)}
            />
          </div>
        )}
```

And, mirroring the existing tactical-fit display block (lines 90-95),
show the equipped coach's boosts when present:

```tsx
        {lineup?.coach && (
          <div className="mb-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{lineup.coach.display_name}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">
              {lineup.coach.boosts.map((b) => BOOST_TYPE_LABELS[b.boost_type]).join(", ")}
            </p>
          </div>
        )}
```

`BOOST_TYPE_LABELS` doesn't exist in this file yet — copy the exact
11-entry map already defined in `frontend/src/admin/pages/AdminCoachesPage.tsx`
(Phase 1) rather than retyping it independently (import it if that file
exports it; if it's currently a local, unexported constant there, either
export it from there and import here, or move it to a small shared
module like `frontend/src/lib/coaches.ts` — prefer moving it to a shared
module if BOTH this file and `AdminCoachesPage.tsx` need the identical
map, to avoid the two copies silently drifting apart over time).

Add the necessary imports: `fetchClubCoachCards`, `setClubCoach` from
wherever Task 10 put them, `ClubCoachCard`/`EquippedCoach` types if
referenced explicitly (likely not needed given the inline usage above
relies on inference).

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Verify live in the browser**

Start the dev stack (`docker compose up -d --build frontend backend` —
this repo's own `docker-compose.override.yml` note applies if present).
Open `/clubs/squad` as a club captain whose club owns at least one
`ClubCoachCard` (create one via the admin panel or the coach-pack
purchase flow from Task 12 if that's already implemented; otherwise
insert one directly via SQL for this manual check, mirroring how earlier
Phase 2 verification in this session set up test data directly in
Postgres). Confirm: the "Тренер" row lists owned coaches by name; picking
one calls `PUT /clubs/me/coach` and the boosts summary block appears
below; picking "Без тренера" clears it; a non-manager viewing the page
sees neither the picker nor an editable state (only the boosts summary,
if a coach happens to be equipped).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(coaches): add coach equip picker to the club squad page"
```

---

### Task 12: Frontend — club coach pack purchase/opening flow

**Files:**
- Create: `frontend/src/pages/ClubCoachPacksPage.tsx`
- Create: `frontend/src/pages/ClubCoachPackOpenPage.tsx`
- Create: `frontend/src/components/cards/CoachRevealStage.tsx`
- Modify: `frontend/src/App.tsx` (routes)

**Interfaces:**
- Consumes: `fetchClubCoachPacks`, `openClubCoachPack` (Task 10).

- [ ] **Step 1: Create `CoachRevealStage.tsx`**

A simpler, coach-appropriate reveal component — NOT a modification of
the existing shared `CardRevealStage.tsx` (that component's stage set
assumes Player-shaped data with position/country/club fields a Coach
doesn't have; building a separate component avoids touching a piece 2
existing player-pack flows already depend on):

```tsx
import { motion } from "framer-motion";

import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import type { EquippedCoach } from "@/types";

export type CoachStage = "rarity" | "silhouette" | "reveal";
export const COACH_STAGES: CoachStage[] = ["rarity", "silhouette", "reveal"];
export const COACH_STAGE_DURATION_MS = 900;

export interface RevealableOpenedCoachCard {
  card: { coach: EquippedCoach };
  is_new: boolean;
}

export function CoachRevealStage({
  opened, stage, index, total, onTap,
}: {
  opened: RevealableOpenedCoachCard;
  stage: CoachStage;
  index: number;
  total: number;
  onTap: () => void;
}) {
  const coach = opened.card.coach;

  return (
    <button onClick={onTap} className="flex flex-1 flex-col items-center justify-center gap-4 px-6">
      <p className="text-xs text-ink-mist-dim">{index + 1} / {total}</p>

      {stage === "rarity" && (
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          className={`rounded-2xl bg-gradient-to-b px-6 py-4 ${RARITY_GRADIENTS[coach.rarity]} ${RARITY_GLOW[coach.rarity]}`}
        >
          <p className="font-display text-lg font-bold text-white">{RARITY_LABELS[coach.rarity]}</p>
        </motion.div>
      )}

      {stage === "silhouette" && (
        <div className="h-40 w-40 overflow-hidden rounded-2xl bg-black/40">
          <img src={staticUrl(coach.image_path ?? undefined)} alt="" className="h-full w-full object-cover opacity-30 blur-sm" />
        </div>
      )}

      {stage === "reveal" && (
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex flex-col items-center gap-2">
          <div className={`h-40 w-40 overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[coach.rarity]} ${RARITY_GLOW[coach.rarity]}`}>
            <img src={staticUrl(coach.image_path ?? undefined)} alt="" className="h-full w-full object-cover" />
          </div>
          <p className="font-display text-lg font-bold text-ink-chalk">{coach.display_name}</p>
        </motion.div>
      )}
    </button>
  );
}
```

- [ ] **Step 2: Create `ClubCoachPacksPage.tsx`**

Direct mirror of `frontend/src/pages/ClubPacksPage.tsx` (48 lines,
already read in full):

```tsx
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { IconChevronLeft, IconCoin } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubCoachPacks } from "@/api/clubCoachPacks";
import { staticUrl } from "@/lib/api";

export default function ClubCoachPacksPage() {
  const navigate = useNavigate();
  const { data: packs, isLoading } = useQuery({ queryKey: ["clubs", "coach-packs"], queryFn: fetchClubCoachPacks });

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Паки тренеров</h1>
      </div>

      <div className="flex flex-col gap-2">
        {(packs ?? []).map((pack) => (
          <div key={pack.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <img
              src={staticUrl(pack.image_path ?? undefined) ?? staticUrl("packs/basic.webp")}
              alt="" className="h-14 w-14 rounded-xl object-cover"
            />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{pack.name}</p>
              <p className="flex items-center gap-1 text-xs text-ink-mist-dim">
                {pack.card_count} тренер{pack.card_count === 1 ? "" : "а"} · <IconCoin size={11} /> {pack.price}
              </p>
            </div>
            <button
              onClick={() => navigate(`/clubs/coach-packs/${pack.id}/open`)}
              className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
            >
              Открыть
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `ClubCoachPackOpenPage.tsx`**

Direct mirror of `frontend/src/pages/ClubPackOpenPage.tsx` (177 lines,
already read in full), substituting `openClubCoachPack`/
`CoachRevealStage`/`COACH_STAGES`/`COACH_STAGE_DURATION_MS` for their
player-pack equivalents, and the summary grid rendering
`oc.card.coach.display_name`/`oc.card.coach.image_path` instead of
`oc.card.player.display_name`/`.image_path`. Copy the file's exact
phase-state-machine structure (`packshot → revealing → summary`,
`hasStartedRef` StrictMode guard, `idempotencyKeyRef`, `skipAll`) —
these are proven, don't redesign them.

- [ ] **Step 4: Register the routes**

In `frontend/src/App.tsx`, near the existing `/clubs/packs` and
`/clubs/packs/:packId/open` routes (read the file to confirm the exact
route-tree nesting, same caution as Coach Cards Phase 1's Task 7 route
registration), add:

```tsx
<Route path="clubs/coach-packs" element={<ClubCoachPacksPage />} />
<Route path="clubs/coach-packs/:packId/open" element={<ClubCoachPackOpenPage />} />
```

(Adjust the exact path prefixes to match however the existing
`clubs/packs` routes are actually nested — this plan doesn't reproduce
`App.tsx`'s full route tree.)

Also add a way to navigate here from the Clubs page — check
`frontend/src/pages/ClubsPage.tsx` for how it currently links to
`/clubs/packs` (a button/card, per this session's earlier work on that
page) and add an equivalent entry point for `/clubs/coach-packs`,
matching its existing visual idiom exactly (same card/button style
already established there).

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Verify live in the browser**

Same verification approach as Coach Cards Phase 1's frontend tasks — if
a live dev stack is reachable, click through: pack list renders, opening
animates through rarity → silhouette → reveal → summary, budget updates,
navigating back to squad shows the new coach available in the equip
picker (Task 11). If genuinely unreachable in your environment, fall
back to typecheck + careful manual read, stating exactly why, per this
session's established fallback pattern.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ClubCoachPacksPage.tsx frontend/src/pages/ClubCoachPackOpenPage.tsx frontend/src/components/cards/CoachRevealStage.tsx frontend/src/App.tsx frontend/src/pages/ClubsPage.tsx
git commit -m "feat(coaches): add club coach pack purchase and opening UI"
```

---

### Task 13: Frontend — admin page for `ClubCoachPack`

**Files:**
- Create: `frontend/src/admin/pages/AdminClubCoachPacksPage.tsx`
- Modify: `frontend/src/admin/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/admin/AdminLayout.tsx`

**Interfaces:**
- Consumes: Task 4's admin endpoints.

- [ ] **Step 1: Add admin API functions**

In `frontend/src/admin/api.ts`, near the existing club-pack admin
functions (find and read them first — this repo's `AdminClubPacksPage.tsx`
already has a working equivalent to mirror), add
`fetchAdminClubCoachPacks`/`createClubCoachPack`/`updateClubCoachPack`
following that exact pattern.

- [ ] **Step 2: Create `AdminClubCoachPacksPage.tsx`**

Mirror `frontend/src/admin/pages/AdminClubPacksPage.tsx` (read it in
full first) closely — same list/create/edit form shape, substituting
coach-pack fields.

- [ ] **Step 3: Register the route and nav item**

`frontend/src/App.tsx`: add the import + route at `/admin/club-coach-packs`,
matching the existing `/admin/club-packs` route's nesting. 
`frontend/src/admin/AdminLayout.tsx`: add `{ to:
"/admin/club-coach-packs", label: "Клубные паки тренеров", icon: "🧑‍🏫" }`
near the existing "Клубные паки" entry.

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Verify live in the browser**

Same fallback pattern as prior frontend tasks if live verification isn't
reachable.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/api.ts frontend/src/admin/pages/AdminClubCoachPacksPage.tsx frontend/src/App.tsx frontend/src/admin/AdminLayout.tsx
git commit -m "feat(coaches): add admin page for club coach packs"
```

---

## Self-Review Notes

**Spec coverage:** §7 (club acquisition) → Tasks 1-4. §8 (club equip
flow) → Task 5. §5's all 11 boost hook points → Tasks 6-8 (zones +
depth-bonus in Task 6; mentality/counter/pass/initiative in Task 7;
real-match integration in Task 8), with Task 9's balance tests providing
the statistical evidence this session's own practice requires for any
match-engine change. Club half of §9 (Tactical Fit / squad UI) → Task 11
(the equip picker itself; the tactical-fit percentage/hint display
already shipped in the earlier club-tactical Phase 2 work this session
did, untouched here). Frontend acquisition/admin UX → Tasks 12-13.
Personal/Arena track (§7/§8's non-club half, coach_boost_service.py's
`arena_*` functions) is correctly excluded — Phase 3.

**Placeholder scan:** every step has real code or an explicit, narrow
"read file X first, the exact name is there" pointer — never a bare "add
appropriate handling." The handful of `<existing fixture>`-style
placeholders in Tasks 6-9's test code are flagged explicitly as
"replace with the real name once read," not silently left vague, because
this plan's author did not have live access to every test file's exact
fixture names at plan-writing time (unlike the extensively-quoted
service/model files, which were read in full). This is a deliberate,
narrower kind of incompleteness than the "No Placeholders" section
prohibits — it names exactly what to look up and where, rather than
describing an action without showing how.

**Type consistency:** `Coach | None` / `coach: "Coach | None" = None`
appears identically across `compute_profile` (Task 6), `ClubTacticalSide`/
`build_side` (Task 7), and the `tournament_simulation_service.py` call
sites (Task 8). `resolve_active_boosts`/`apply_zone_boosts`/
`depth_bonus_cap_for`/`defensive_shift_for`/`transition_bonus_for`/
`first_pass_input_bonus`/`initiative_mult_for` are called with exactly
the signatures Phase 1 already built and tested — never redefined or
shadowed. `EquippedCoachOut`/`ClubCoachCardOut` (backend, Task 5) and
`EquippedCoach`/`ClubCoachCard` (frontend, Task 10) match field-for-field
in the same order. `set_club_coach`/`setClubCoach` and
`open_club_coach_pack`/`openClubCoachPack` names are consistent between
backend and frontend throughout.

**Fixed during self-review:** Task 5's migration originally said `Revises:
<Task 4's migration revision>` — but Task 4 (admin CRUD for
`ClubCoachPack`) is router/schema-only and never creates a migration
file; only Tasks 1, 2, and 5 do. Corrected to chain off Task 2's
migration (the actual last migration-producing task before Task 5) in
both the docstring and the `down_revision` assignment.

**Known cross-task ordering wrinkle, flagged explicitly rather than
silently left for a subagent to discover:** Task 3's router
(`club_coach_packs.py`) needs `ClubCoachCardOut` from
`app.schemas.club_squad`, which this plan's task numbering formally
assigns to Task 5. Task 3's own Step 6 already calls this out and
instructs adding that one schema early, as part of Task 3, rather than
waiting for Task 5 — whoever executes this plan (subagent-driven-development
or a human) should treat this as a pre-resolved ruling, not rediscover
it as a blocker.
