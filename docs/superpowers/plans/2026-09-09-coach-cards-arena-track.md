# Coach Cards — Personal/Arena Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring coaches to the personal (non-club) track: coaches drop from
regular packs, players equip one coach on their personal Card Arena squad,
an equipped coach gives a flat, rarity-scaled boost to squad power, and the
Arena page explains what actually determines squad power (position fit and
chemistry, not just player rating).

**Architecture:** Mirrors the just-shipped club-track pattern wherever the
codebase genuinely supports it (a `UserCoachCard` ownership model paralleling
`ClubCoachCard`; a `coach_drop_chance` column on `Pack` paralleling `ClubPack`;
a grid-cell equip UI paralleling the club squad page), but with two
deliberate departures where the personal track's real shape differs: (1)
`Pack`'s roll logic lives in `roll_and_create_cards`, one function shared by
purchases, task/collection/league rewards, wheel bonuses, and Stars
purchases — so `PackOpenResult` gains a new, purely *additive*
`coach_cards` field instead of replacing `cards` with a discriminated union,
keeping every other caller of that shared function unchanged; (2)
`PackOpenPage.tsx` already carries real complexity (Stars re-purchase, a
single-card shortcut, referral/collection banners) — a coach card appears in
the results summary grid, not as its own staged reveal animation, for this
first cut. The Arena squad-power bonus is a new, simple, rarity-tier lookup
(any equipped coach gives a bonus scaled only by its rarity, regardless of
which specific boosts it has) — a deliberately simpler mechanism than the
already-built-but-unused per-boost-type Arena hooks in `coach_boost_service.py`
(`arena_category_bonus`, `arena_team_strength_bonus`,
`arena_pass_fail_chance_reduction`), which remain in place for a future,
full-fidelity pass.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 + TypeScript
+ TanStack Query + Framer Motion (frontend), Alembic migrations, pytest
(in-memory SQLite).

**Spec:** No standalone spec document for this plan — it implements the
"Основная игра" (main game) requirements from this session's own design
conversation (see the chat history immediately preceding this plan's
creation for the full brainstorm), building on
`docs/superpowers/specs/2026-09-08-coach-cards-design.md` (§7-§9's personal-
track sketch, which this plan supersedes with the ground-truth code details
found while writing this plan — the spec's illustrative code was written
before `Pack`/`roll_and_create_cards`/`PackOpenResult`'s real complexity was
fully mapped).

## Global Constraints

- Never trust frontend-submitted values for balances/rewards/cards — all
  probability rolls and card minting stay server-side.
- Any operation involving coins/cards/packs must be atomic and idempotency-
  key-protected — `open_pack`'s existing locking/idempotency pattern must be
  preserved exactly, not weakened.
- Use row locking for race-sensitive operations — the new
  `create_user_coach_card`'s `Coach.next_serial_number` counter lock must use
  `db.refresh(..., with_for_update=True)`, never a racy
  `MAX(serial_number) + 1` scan (mirrors `create_user_card`'s own existing
  pattern for `Player.next_serial_number` exactly).
- A diamond-rarity roll must never be eligible to become a coach — `Coach`
  carries a DB check constraint that a coach can never be `diamond` rarity
  (`ck_coaches_rarity_not_diamond`), so `pick_random_coach(db, Rarity.diamond)`
  always falls through to an "any active pack-droppable coach" fallback
  (arbitrary rarity). The club-track's final review caught this exact bug
  after the fact (a diamond-guaranteed pack slot could silently pay out an
  arbitrary-rarity coach); this plan's roll logic must exclude
  `Rarity.diamond` from the coach-eligible branch from the start, not as a
  follow-up fix.
- Do not touch `coach_boost_service.py`'s *existing* functions
  (`resolve_active_boosts`, `apply_zone_boosts`, `depth_bonus_cap_for`,
  `initiative_mult_for`, `defensive_shift_for`, `transition_bonus_for`,
  `first_pass_input_bonus`, `arena_category_bonus`,
  `arena_pass_fail_chance_reduction`, `arena_team_strength_bonus`) — this
  plan only *adds* one new function to that file.
- Do not touch `club_tactical_matchup_service.py`,
  `club_tactical_profile_service.py`, `tournament_simulation_service.py`,
  `club_squad_service.py`, or any club-track file from the two prior Coach
  Cards plans — this plan is personal/Arena-track only.
- `calculate_base_strength` (`lineup_service.py`) is shared by
  `club_tactical_profile_service.py`, `tournament_simulation_service.py`,
  and `club_squad_service.py` in addition to `lineup_service.py`'s own
  personal-Arena callers — its signature may only change by adding an
  **optional** parameter with a default that preserves every existing
  caller's behavior unchanged (none of those three files may be edited to
  pass the new argument; they keep calling it exactly as they do today).
- Alembic revisions are named sequentially (`NNNN_short_description.py`),
  current HEAD is `0095_drop_club_coach_packs.py` — this plan's migrations
  are `0096`, `0097`, `0098` (one per schema-changing task, matching the
  club-track plan's own one-migration-per-task discipline).
- CHECK constraints must be written in portable SQL both Postgres and the
  SQLite test suite can apply (no Postgres-only functions).
- `UserCoachCard.source` reuses the existing `card_source_enum` Postgres
  type (`Enum(CardSource, name="card_source_enum", create_type=False)`) —
  the same enum `UserCard.source` already uses — rather than inventing a new
  enum, since `roll_and_create_cards` already threads a `CardSource` value
  through from every one of its callers (purchases, task rewards, collection
  rewards, league rewards, wheel bonuses, Stars purchases).

---

### Task 1: Personal coach ownership — `UserCoachCard` model + migration

**Files:**
- Create: `backend/app/models/user_coach_card.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/card_creation.py`
- Create: `backend/alembic/versions/0096_user_coach_cards.py`
- Test: `backend/tests/test_user_coach_card_model.py`

**Interfaces:**
- Produces: `UserCoachCard` model (`id`, `user_id`, `coach_id`,
  `serial_number`, `source: CardSource`, `source_ref_id`, `acquired_at`,
  `coach` relationship, `lazy="joined"`); `create_user_coach_card(db,
  owner_id, coach_id, source: CardSource, source_ref_id=None) ->
  UserCoachCard` — Task 3 consumes both.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_user_coach_card_model.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.coach import Coach, CoachBoost
from app.models.enums import CardSource, CoachBoostType, Rarity
from app.models.user import User
from app.models.user_coach_card import UserCoachCard


async def test_user_coach_card_requires_a_real_coach_and_user(db_session):
    user = User(telegram_id=999_200_100, username="coach_card_test_user")
    db_session.add(user)
    coach = Coach(display_name="Personal Test Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()

    card = UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source=CardSource.pack)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)

    assert card.id is not None
    assert card.acquired_at is not None


async def test_user_coach_card_rejects_a_nonexistent_coach(db_session):
    user = User(telegram_id=999_200_101, username="coach_card_test_user_2")
    db_session.add(user)
    await db_session.flush()

    card = UserCoachCard(user_id=user.id, coach_id=999_999, serial_number=1, source=CardSource.pack)
    db_session.add(card)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_user_coach_card_model.py -v`

Expected: FAIL — `app.models.user_coach_card` doesn't exist yet.

- [ ] **Step 3: Create the `UserCoachCard` model**

Read `backend/app/models/club_coach_card.py` in full first (already exists,
this is the exact model to mirror — `club_id`/`ClubCoachCardSource` become
`user_id`/`CardSource`):

```python
# backend/app/models/user_coach_card.py
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CardSource
from app.models.mixins import utcnow


class UserCoachCard(Base):
    __tablename__ = "user_coach_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[CardSource] = mapped_column(
        Enum(CardSource, name="card_source_enum", create_type=False), nullable=False
    )
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    coach: Mapped["Coach"] = relationship(lazy="joined")
```

- [ ] **Step 4: Register the model in `app/models/__init__.py`**

Read the file first to find where `ClubCoachCard` is imported/exported (the
club-track plan's final review caught a real bug from an implementer
forgetting this exact step — don't repeat it). Add, alongside the existing
coach-related imports/exports:

```python
from app.models.user_coach_card import UserCoachCard
```

and add `"UserCoachCard"` to the file's `__all__` list, in the same
alphabetical/grouped position style the file already uses near
`"ClubCoachCard"`.

- [ ] **Step 5: Add `create_user_coach_card` to `card_creation.py`**

Read `backend/app/services/card_creation.py` in full first (short file, just
`create_user_card`). Add this function, mirroring `create_user_card` exactly
(and mirroring `club_card_service.create_club_coach_card`'s identical
counter-locking reasoning for `Coach.next_serial_number` — note this is the
**personal** counter, `next_serial_number`, not `next_club_serial_number`):

```python
async def create_user_coach_card(
    db: AsyncSession, owner_id: int, coach_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserCoachCard:
    """Mirrors create_user_card exactly, but against Coach.next_serial_number
    (the personal-ownership counter — distinct from next_club_serial_number,
    which club coach acquisitions use) — personal coach acquisitions must
    never affect club-side serial-number scarcity, and the counter must be
    read-and-incremented under a row lock rather than a racy
    MAX(serial_number) + 1 scan, matching every other serial-number
    allocation in this codebase."""
    coach = await db.get(Coach, coach_id)
    await db.refresh(coach, attribute_names=["next_serial_number"], with_for_update=True)
    serial_number = coach.next_serial_number
    coach.next_serial_number += 1
    db.add(coach)

    card = UserCoachCard(user_id=owner_id, coach_id=coach_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card
```

Add the needed imports at the top of `card_creation.py`:

```python
from app.models.coach import Coach
from app.models.user_coach_card import UserCoachCard
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_user_coach_card_model.py -v`

Expected: PASS.

- [ ] **Step 7: Write the migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest revision -m "user coach cards"`

Rename the generated file to `0096_user_coach_cards.py`:

```python
"""Add UserCoachCard — personal (non-club) coach ownership

Revision ID: 0096
Revises: 0095
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0096"
down_revision: Union[str, None] = "0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_coach_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("pack", "daily_reward", "trade", "admin_grant", "achievement", "game_reward", "seed", "task",
                    "free_pack", "card_upgrade", "collection_reward", "stars_purchase", "chat_pack", "gift", "wheel",
                    "league_reward", name="card_source_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_coach_cards_user_id", "user_coach_cards", ["user_id"])
    op.create_index("ix_user_coach_cards_coach_id", "user_coach_cards", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_user_coach_cards_coach_id", table_name="user_coach_cards")
    op.drop_index("ix_user_coach_cards_user_id", table_name="user_coach_cards")
    op.drop_table("user_coach_cards")
```

(The inline `sa.Enum(...)` value list for `source` must list every current
`CardSource` member — read `backend/app/models/enums.py`'s real `CardSource`
class first and copy its exact current member list verbatim; `create_type=False`
means this migration never issues `CREATE TYPE`, it only references the enum
type Postgres already has from `0001_initial.py`, so the exact member list
here is just documentation for `sa.Enum`'s Python-side validation, not a
schema-affecting value — but keep it accurate.)

- [ ] **Step 8: Verify the migration against real Postgres**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest upgrade head --sql` —
confirm clean SQL, no errors. If the real `docker compose` Postgres is
running, also run `docker compose exec backend alembic upgrade head` to
confirm it actually applies, then `docker compose exec postgres psql -U
postgres -d footycards -c "\d user_coach_cards"` to confirm the table shape.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user_coach_card.py backend/app/models/__init__.py backend/app/services/card_creation.py backend/alembic/versions/0096_user_coach_cards.py backend/tests/test_user_coach_card_model.py
git commit -m "feat(coaches): add UserCoachCard — personal coach ownership"
```

---

### Task 2: `Pack` gains a coach slot + `PackOpeningCard` becomes a dual-kind row

**Files:**
- Modify: `backend/app/models/pack.py`
- Modify: `backend/app/schemas/pack.py`
- Create: `backend/alembic/versions/0097_pack_coach_slots.py`
- Test: `backend/tests/test_pack_model.py` (create if it doesn't exist — check first; if a model-level test file for `Pack` already exists, add to it instead)

**Interfaces:**
- Produces: `Pack.coach_drop_chance: float`; `PackOpeningCard.user_card_id:
  Optional[int]` (now nullable), `PackOpeningCard.user_coach_card_id:
  Optional[int]` (new); `PackOut.coach_drop_chance`, `PackCreate.coach_drop_chance`,
  `PackUpdate.coach_drop_chance`; `OpenedCoachCardOut` (new schema);
  `PackOpenResult.coach_cards: list[OpenedCoachCardOut] = []` (new, additive
  field — `cards: list[OpenedCardOut]` is completely unchanged) — Task 3
  consumes all of this.

- [ ] **Step 1: Check for an existing `Pack` model test file**

Run: `ls backend/tests/ | grep -i "test_pack"` (careful: this also matches
`test_pack_service.py`/similar — you want a *model*-level test file
specifically; if none exists, create `test_pack_model.py`).

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_pack_model.py (add to existing file, or create new)
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.pack import Pack, PackOpening, PackOpeningCard


async def test_pack_coach_drop_chance_defaults_to_zero(db_session):
    pack = Pack(slug="test-pack-default-arena", name="Test Pack", price=100, card_count=3)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    assert pack.coach_drop_chance == 0.0


async def test_pack_opening_card_rejects_neither_fk_set(db_session):
    from datetime import datetime, timezone

    from app.models.user import User

    user = User(telegram_id=999_200_200, username="pack_slot_test_user")
    db_session.add(user)
    pack = Pack(slug="test-pack-slot-arena", name="Test Pack", price=100, card_count=1)
    db_session.add(pack)
    await db_session.flush()
    opening = PackOpening(user_id=user.id, pack_id=pack.id, price_paid=100, created_at=datetime.now(timezone.utc))
    db_session.add(opening)
    await db_session.flush()

    db_session.add(PackOpeningCard(opening_id=opening.id, user_card_id=None, user_coach_card_id=None, is_new=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_pack_model.py -v`

Expected: FAIL — `coach_drop_chance` doesn't exist, and `user_card_id`
isn't nullable yet.

- [ ] **Step 4: Add `coach_drop_chance` to `Pack`**

In `backend/app/models/pack.py`, add one column (exact insertion point:
right after `sort_order`):

```python
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Fraction of this pack's card_count slots that roll a coach instead of
    # a player (independent per-slot coin flip, see
    # pack_service.roll_and_create_cards — mirrors ClubPack.coach_drop_chance
    # exactly). 0.0 (default) means every existing pack stays player-only
    # until an admin opts it in.
    coach_drop_chance: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
```

`Numeric` is already imported in this file.

- [ ] **Step 5: Make `PackOpeningCard` a "player XOR coach" row**

In `backend/app/models/pack.py`, replace the `PackOpeningCard` class
(leave `Pack`, `PackRarityProbability`, `PackOpening`, and `StarsInvoice`
untouched — only `PackOpeningCard` changes):

```python
class PackOpeningCard(Base):
    __tablename__ = "pack_opening_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(
        ForeignKey("pack_openings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Exactly one of these two is set per row — a pack slot resolves to
    # either a player or a coach (see pack_service.roll_and_create_cards's
    # per-slot coach_drop_chance coin flip), never both, never neither.
    # Portable boolean-expression CHECK (no Postgres-only functions) so the
    # SQLite test suite enforces it too — mirrors
    # ck_club_pack_opening_card_exactly_one_kind exactly.
    user_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="CASCADE"), nullable=True
    )
    is_new: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    opening: Mapped["PackOpening"] = relationship(back_populates="cards")

    __table_args__ = (
        CheckConstraint(
            "(user_card_id IS NOT NULL AND user_coach_card_id IS NULL) OR "
            "(user_card_id IS NULL AND user_coach_card_id IS NOT NULL)",
            name="ck_pack_opening_card_exactly_one_kind",
        ),
    )
```

(`is_new_player` renamed to `is_new` — grep the whole repo for
`is_new_player` first: it's used in `pack_service.py` [rewritten in Task 3],
`daily_reward_service.py` [one line, updated in Task 3], and
`stars_payment_service.py`'s own comment referencing it [read that comment,
update it if it names the field directly] — confirm no other file reads it
before renaming. Add `CheckConstraint` to this file's existing SQLAlchemy
import line.)

- [ ] **Step 6: Add `coach_drop_chance` to the pack schemas**

In `backend/app/schemas/pack.py`, add the field to `PackOut`, `PackCreate`,
and `PackUpdate` (exact insertion point: right after `rarity_probabilities`
in `PackOut`, right after `rarity_probabilities` in `PackCreate`, right
after `rarity_probabilities` in `PackUpdate` — this file's field ordering
puts `rarity_probabilities` in the middle rather than last, unlike
`club_pack.py`'s schema; read the real current file to place it correctly):

```python
    coach_drop_chance: float = Field(default=0.0, ge=0, le=1)  # PackCreate
    coach_drop_chance: Optional[float] = Field(default=None, ge=0, le=1)  # PackUpdate
    coach_drop_chance: float  # PackOut (no Field(...) needed, from_attributes handles it)
```

(These three lines are illustrative of each class's own field style — add
each to its correct class, matching that class's existing `Optional`/
required conventions field-by-field, not as one block.)

Add a new schema, next to `OpenedCardOut`:

```python
class OpenedCoachCardOut(BaseModel):
    card: "UserCoachCardOut"
    is_new: bool
    duplicate_count: int
```

Import `UserCoachCardOut` from `app.schemas.coach` if it already exists
there (check first — Coach Cards Phase 1/2 may have already defined a
`UserCoachCardOut`-shaped or `ClubCoachCardOut`-shaped schema you should
reuse or mirror; if nothing personal-side exists yet, define it in
`backend/app/schemas/pack.py` itself, right above `OpenedCoachCardOut`,
mirroring `ClubCoachCardOut`'s exact shape from `app.schemas.club_squad`:
`id: int, serial_number: int, coach: CoachOut, acquired_at: datetime` —
`CoachOut` already exists in `app.schemas.coach`, import it).

Add `coach_cards: list[OpenedCoachCardOut] = []` to `PackOpenResult`
(exact insertion point: right after `cards: list[OpenedCardOut]` — do NOT
change `cards`'s own type or remove any existing field from
`PackOpenResult`).

- [ ] **Step 7: Write the migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest revision -m "pack coach slots"`

Rename to `0097_pack_coach_slots.py`:

```python
"""Add Pack.coach_drop_chance and make PackOpeningCard a player-XOR-coach row

Revision ID: 0097
Revises: 0096
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0097"
down_revision: Union[str, None] = "0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packs",
        sa.Column("coach_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )

    op.add_column("pack_opening_cards", sa.Column("user_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pack_opening_cards_user_coach_card_id", "pack_opening_cards",
        "user_coach_cards", ["user_coach_card_id"], ["id"], ondelete="CASCADE",
    )

    op.alter_column("pack_opening_cards", "user_card_id", nullable=True)
    op.alter_column("pack_opening_cards", "is_new_player", new_column_name="is_new")

    op.create_check_constraint(
        "ck_pack_opening_card_exactly_one_kind",
        "pack_opening_cards",
        "(user_card_id IS NOT NULL AND user_coach_card_id IS NULL) OR "
        "(user_card_id IS NULL AND user_coach_card_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.alter_column("pack_opening_cards", "is_new", new_column_name="is_new_player")
    op.alter_column("pack_opening_cards", "user_card_id", nullable=False)
    op.drop_constraint("fk_pack_opening_cards_user_coach_card_id", "pack_opening_cards", type_="foreignkey")
    op.drop_column("pack_opening_cards", "user_coach_card_id")
    op.drop_column("packs", "coach_drop_chance")
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_pack_model.py -v`

Expected: PASS. (The full suite will show new failures in `pack_service.py`/
`daily_reward_service.py` at this point — expected, fixed in Task 3, not
this one; note it in your report.)

- [ ] **Step 9: Verify the migration against real Postgres**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest upgrade head --sql` — confirm clean SQL. If the real `docker compose` Postgres is available, `docker compose exec backend alembic upgrade head` to actually apply it, then confirm the CHECK constraint genuinely rejects a bad row via a direct `psql` insert attempt (mirroring how the club-track plan's Task 1 proved this).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/pack.py backend/app/schemas/pack.py backend/alembic/versions/0097_pack_coach_slots.py backend/tests/test_pack_model.py
git commit -m "feat(packs): add coach_drop_chance and a player-XOR-coach opening-card shape"
```

---

### Task 3: Roll logic — `roll_and_create_cards` mixes coach draws

**Files:**
- Modify: `backend/app/services/pack_service.py`
- Modify: `backend/app/services/daily_reward_service.py`
- Test: `backend/tests/test_packs.py` (read this file in full first — the
  existing route-level test file for `open_pack`; extend it, don't create a
  new one — if the real filename differs, e.g. `test_pack_service.py`, use
  that one instead)

**Interfaces:**
- Consumes: `Pack.coach_drop_chance`, `PackOpeningCard.user_coach_card_id`/
  `is_new` (Task 2); `create_user_coach_card` (Task 1); `pick_random_coach`
  (`app.services.pack_service`, already exists, unchanged — it's already in
  this same file).
- Produces: `roll_and_create_cards`'s new mixed-item behavior (still returns
  `list[OpenedCardOut]` for `cards` unchanged — the coach items it also
  creates get returned via a second value; adjust its return type to
  `tuple[list[OpenedCardOut], list[OpenedCoachCardOut]]` and update its 2
  callers, `open_pack` and `grant_bonus_pack_opening`, accordingly) — Task 6
  (frontend types) and Task 7 (pack-open page) consume `PackOpenResult.coach_cards`.

- [ ] **Step 1: Read the current file in full**

Read `backend/app/services/pack_service.py` in full (already partially read
this session — re-read now since you're about to rewrite `roll_and_create_cards`,
`get_opening_result`, `open_pack`, and `grant_bonus_pack_opening`). Also read
`backend/tests/test_packs.py` (or whichever file is the real one, per Step 0
below) to find its existing fixture helpers for creating a pack + opening it
as a test user.

- [ ] **Step 0: Confirm the real test file name**

Run: `ls backend/tests/ | grep -iE "test_pack[s]?\.py|test_pack_service"` —
use whichever file already tests `open_pack` at the route level.

- [ ] **Step 2: Write the failing tests**

```python
async def test_open_pack_with_coach_drop_chance_can_yield_a_coach(client, db_session, bot_token):
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType, Rarity
    from app.models.pack import Pack, PackRarityProbability

    coach = Coach(display_name="Personal Slot Test Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
    db_session.add(coach)

    pack = Pack(slug="coach-slot-personal-pack", name="Coach Slot Pack", price=50, card_count=5, coach_drop_chance=1.0)
    pack.rarity_probabilities = [PackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    headers = telegram_headers(830600, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    # Fund the user enough to afford a 50-coin pack — check test_packs.py's
    # own existing tests for how they fund a fresh user (e.g. a daily claim,
    # or an admin balance grant) and use the exact same approach here.

    resp = await client.post("/api/v1/packs/coach-slot-personal-pack/open", headers=headers, json={"idempotency_key": "personal-slot-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 0
    assert len(body["coach_cards"]) == 5
    assert all(item["card"]["coach"]["display_name"] == "Personal Slot Test Coach" for item in body["coach_cards"])


async def test_open_pack_with_diamond_rarity_never_yields_a_coach(client, db_session, bot_token):
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType, Position, Rarity
    from app.models.pack import Pack, PackRarityProbability
    from tests.factories import create_player

    coach = Coach(display_name="Should Never Appear Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
    db_session.add(coach)
    await create_player(db_session, rarity=Rarity.diamond, position=Position.ST)

    pack = Pack(slug="diamond-personal-pack", name="Diamond Pack", price=50, card_count=5, coach_drop_chance=1.0)
    pack.rarity_probabilities = [PackRarityProbability(rarity=Rarity.diamond, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    headers = telegram_headers(830601, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/packs/diamond-personal-pack/open", headers=headers, json={"idempotency_key": "diamond-personal-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["coach_cards"]) == 0
    assert len(body["cards"]) == 5
    assert all(item["card"]["player"]["rarity"] == "diamond" for item in body["cards"])
```

(Adjust the funding/auth setup and the exact `POST /packs/{slug|id}/open`
path to match `test_packs.py`'s own real, established fixture pattern for
funding a fresh test user and the real route path — read the file first,
don't guess.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_packs.py -k coach_drop_chance -v` (adjust filename per Step 0)

Expected: FAIL.

- [ ] **Step 4: Rewrite `roll_and_create_cards`**

In `backend/app/services/pack_service.py`, replace the function:

```python
async def _duplicate_coach_counts_snapshot(db: AsyncSession, user_id: int) -> dict[int, int]:
    result = await db.execute(
        select(UserCoachCard.coach_id, func.count(UserCoachCard.id)).where(UserCoachCard.user_id == user_id).group_by(UserCoachCard.coach_id)
    )
    return {coach_id: count for coach_id, count in result.all()}


async def roll_and_create_cards(
    db: AsyncSession,
    user: User,
    pack: Pack,
    opening: PackOpening,
    dup_counts: dict[int, int],
    source: CardSource,
) -> tuple[list[OpenedCardOut], list[OpenedCoachCardOut]]:
    seen_this_opening: set[int] = set()
    seen_coaches_this_opening: set[int] = set()
    rolled_rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
    coach_dup_counts = await _duplicate_coach_counts_snapshot(db, user.id)
    coach_drop_chance = float(pack.coach_drop_chance)

    opened_items: list[OpenedCardOut] = []
    opened_coach_items: list[OpenedCoachCardOut] = []
    for rarity in rolled_rarities:
        # Diamond can never be a coach (Coach carries ck_coaches_rarity_not_diamond) —
        # a diamond-rarity slot always resolves as a player, or pick_random_coach's
        # own fallback would silently substitute an arbitrary-rarity coach for a
        # guaranteed diamond, exactly the bug the club-track plan's final review
        # caught and had to fix after the fact.
        if coach_drop_chance > 0 and rarity != Rarity.diamond and random.random() < coach_drop_chance:
            coach = await pick_random_coach(db, rarity)
            is_new = coach_dup_counts.get(coach.id, 0) == 0 and coach.id not in seen_coaches_this_opening
            seen_coaches_this_opening.add(coach.id)
            coach_dup_counts[coach.id] = coach_dup_counts.get(coach.id, 0) + 1

            user_coach_card = await create_user_coach_card(db, user.id, coach.id, source, opening.id)

            db.add(PackOpeningCard(opening_id=opening.id, user_card_id=None, user_coach_card_id=user_coach_card.id, is_new=is_new))
            user_coach_card.coach = coach
            opened_coach_items.append(
                OpenedCoachCardOut(card=user_coach_card, is_new=is_new, duplicate_count=coach_dup_counts[coach.id])
            )
        else:
            player = await pick_random_player(db, rarity)
            is_new = dup_counts.get(player.id, 0) == 0 and player.id not in seen_this_opening
            seen_this_opening.add(player.id)
            dup_counts[player.id] = dup_counts.get(player.id, 0) + 1

            user_card = await create_user_card(db, user.id, player.id, source, opening.id)

            db.add(PackOpeningCard(opening_id=opening.id, user_card_id=user_card.id, user_coach_card_id=None, is_new=is_new))
            user_card.player = player
            opened_items.append(
                OpenedCardOut(card=user_card, is_new=is_new, duplicate_count=dup_counts[player.id])
            )

    opened_items.sort(key=lambda item: RARITY_ORDER[item.card.player.rarity])
    opened_coach_items.sort(key=lambda item: RARITY_ORDER[item.card.coach.rarity])
    return opened_items, opened_coach_items
```

Add the needed imports at the top of `pack_service.py`:

```python
from app.models.user_coach_card import UserCoachCard
from app.schemas.pack import OpenedCoachCardOut
from app.services.card_creation import create_user_coach_card
```

(`create_user_card`, `RARITY_ORDER`, `Rarity` should already be imported —
confirm, add if missing.)

- [ ] **Step 5: Update `roll_and_create_cards`'s 2 callers**

`open_pack` currently has a line like `opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, source)` followed by building the `PackOpenResult`. Update it to unpack the tuple and pass both lists through:

```python
        opened_items, opened_coach_items = await roll_and_create_cards(db, locked_user, pack, opening, dup_counts, CardSource.pack)
```

(keep every other line of `open_pack` around this call exactly as it is —
read the real current function first to find the exact surrounding
variable names, since `locked_user` vs `user` naming depends on the real
code, not this snippet). Update the `PackOpenResult(...)` construction at
the end of `open_pack` to add `coach_cards=opened_coach_items` alongside its
existing `cards=opened_items`.

Do the identical unpack-and-thread-through update in `grant_bonus_pack_opening`.

- [ ] **Step 6: Update `get_opening_result`'s idempotent-replay path**

Replace the function body (keep its signature `async def get_opening_result(db: AsyncSession, user: User, opening: PackOpening) -> PackOpenResult:` unchanged):

```python
async def get_opening_result(db: AsyncSession, user: User, opening: PackOpening) -> PackOpenResult:
    pack = await _get_pack_or_404(db, opening.pack_id)
    result = await db.execute(
        select(PackOpeningCard)
        .where(PackOpeningCard.opening_id == opening.id)
        .options(joinedload(PackOpeningCard.opening))
        .order_by(PackOpeningCard.id)
    )
    opening_cards = result.unique().scalars().all()

    card_ids = [oc.user_card_id for oc in opening_cards if oc.user_card_id is not None]
    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
    ) if card_ids else None
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()} if cards_result else {}

    coach_card_ids = [oc.user_coach_card_id for oc in opening_cards if oc.user_coach_card_id is not None]
    coach_cards_result = await db.execute(
        select(UserCoachCard).where(UserCoachCard.id.in_(coach_card_ids)).options(joinedload(UserCoachCard.coach).selectinload(Coach.boosts))
    ) if coach_card_ids else None
    coach_cards_by_id = {c.id: c for c in coach_cards_result.unique().scalars().all()} if coach_cards_result else {}

    dup_counts = await _duplicate_counts_snapshot(db, user.id)
    coach_dup_counts = await _duplicate_coach_counts_snapshot(db, user.id)

    items: list[OpenedCardOut] = []
    coach_items: list[OpenedCoachCardOut] = []
    for oc in opening_cards:
        if oc.user_card_id is not None:
            card = cards_by_id[oc.user_card_id]
            items.append(OpenedCardOut(card=card, is_new=oc.is_new, duplicate_count=dup_counts.get(card.player_id, 1)))
        else:
            coach_card = coach_cards_by_id[oc.user_coach_card_id]
            coach_items.append(OpenedCoachCardOut(card=coach_card, is_new=oc.is_new, duplicate_count=coach_dup_counts.get(coach_card.coach_id, 1)))
```

Read the rest of the real current `get_opening_result` (the part building
the final `PackOpenResult` return value, referral bonus, collection rewards
etc. — already partially read this session) and keep it exactly as-is,
except: replace whatever variable the old code used for `cards=` with
`items`, and add `coach_cards=coach_items` to the `PackOpenResult(...)`
construction. Add `Coach` to this file's imports if not already present
(`from app.models.coach import Coach`).

- [ ] **Step 7: Fix `daily_reward_service.py`'s one write site**

In `backend/app/services/daily_reward_service.py`, find the line
`db.add(PackOpeningCard(opening_id=opening.id, user_card_id=card.id, is_new_player=False))` and update it for the renamed column and the new nullable FK:

```python
        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=card.id, user_coach_card_id=None, is_new=False))
```

(The daily free pack never rolls a coach — it grants a specific,
pre-selected card directly, bypassing `roll_and_create_cards` entirely — so
`user_coach_card_id` is always `None` here, unconditionally.)

- [ ] **Step 8: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_packs.py -v` (adjust filename per Step 0)

Expected: PASS, including every pre-existing test in that file (this rewrite
must not change behavior for `coach_drop_chance=0` packs).

- [ ] **Step 9: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: same pass count as before this task plus your 2 new tests, no new
failures beyond the one pre-existing, already-flagged, unrelated failure
(`test_tasks.py::test_task_reward_pack_grants_all_cards`).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/pack_service.py backend/app/services/daily_reward_service.py backend/tests/test_packs.py
git commit -m "feat(packs): roll coaches into existing pack slots via coach_drop_chance"
```

(Adjust the test filename in the `git add` to whatever Step 0 found.)

---

### Task 4: Personal equip flow — `Lineup.user_coach_card_id` + a rarity-tier Arena bonus

**Files:**
- Modify: `backend/app/models/lineup.py`
- Modify: `backend/app/schemas/lineup.py`
- Modify: `backend/app/services/lineup_service.py`
- Modify: `backend/app/services/coach_boost_service.py`
- Modify: `backend/app/routers/lineups.py`
- Create: `backend/alembic/versions/0098_lineup_coach.py`
- Test: `backend/tests/test_lineup_coach.py`

**Interfaces:**
- Consumes: `UserCoachCard` (Task 1).
- Produces: `Lineup.user_coach_card_id`; `LineupOut.coach:
  Optional[EquippedCoachOut] = None` (new schema, mirrors
  `EquippedCoachOut` from the club track's `app.schemas.club_squad` — check
  whether a personal-track equivalent already exists somewhere reusable
  before defining a new one); `set_lineup_coach(db, user, user_coach_card_id:
  int | None) -> LineupOut`; `PUT /lineups/coach` endpoint;
  `coach_boost_service.arena_rarity_team_strength_bonus(coach: Coach | None) -> int`;
  `calculate_base_strength(cards_with_slots, coach: Coach | None = None) -> int`
  (signature changed by adding an optional param with a default — verify
  via grep that `club_tactical_profile_service.py`,
  `tournament_simulation_service.py`, and `club_squad_service.py`'s existing
  call sites are unaffected, since none of them pass the new argument).

- [ ] **Step 1: Read the current files in full**

Read `backend/app/models/club_lineup.py` (the exact model to mirror for the
new column — `club_coach_card_id`, `ondelete="SET NULL"`), `backend/app/schemas/club_squad.py`'s
`EquippedCoachOut` (the exact schema to mirror), and the current full
`backend/app/services/lineup_service.py` (already partially read this
session — re-read now since you're about to edit `calculate_base_strength`
and `get_active_lineup`, and add `set_lineup_coach`).

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_lineup_coach.py
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.models.user_coach_card import UserCoachCard
from app.schemas.lineup import LineupCoachSetRequest
from app.services.lineup_service import set_lineup_coach
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_captain_can_equip_and_clear_personal_coach(client, db_session, bot_token):
    headers = telegram_headers(840200, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840200)

    coach = Coach(display_name="Arena Equip Test Coach", rarity=Rarity.epic)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    card = UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source="pack")
    db_session.add(card)
    await db_session.commit()

    result = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=card.id))
    assert result.coach is not None
    assert result.coach.display_name == "Arena Equip Test Coach"

    cleared = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=None))
    assert cleared.coach is None


async def test_cannot_equip_another_users_coach_card(client, db_session, bot_token):
    import pytest

    from app.core.exceptions import ConflictError

    headers = telegram_headers(840201, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840201)

    other_headers = telegram_headers(840202, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other_user = await get_user_by_telegram_id(db_session, 840202)

    coach = Coach(display_name="Foreign Personal Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()
    foreign_card = UserCoachCard(user_id=other_user.id, coach_id=coach.id, serial_number=1, source="pack")
    db_session.add(foreign_card)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=foreign_card.id))
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_lineup_coach.py -v`

Expected: FAIL.

- [ ] **Step 4: Add `user_coach_card_id` to `Lineup`**

In `backend/app/models/lineup.py`, add (exact insertion point: right after
`is_active`):

```python
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True
    )
```

Add `user_coach_card: Mapped["UserCoachCard | None"] = relationship(lazy="joined")`
right after the `cards` relationship. Add the needed import:
`from app.models.user_coach_card import UserCoachCard` (only needed for the
type-checking string annotation to resolve — check whether this file uses
`TYPE_CHECKING`-guarded imports elsewhere for forward refs like `ClubCard`
and follow the same pattern).

- [ ] **Step 5: Add the equip schemas**

In `backend/app/schemas/lineup.py`, add:

```python
from app.schemas.coach import CoachBoostOut


class EquippedCoachOut(BaseModel):
    id: int
    display_name: str
    rarity: str
    image_path: Optional[str]
    boosts: list[CoachBoostOut]


class LineupCoachSetRequest(BaseModel):
    user_coach_card_id: Optional[int] = None
```

Add `coach: Optional[EquippedCoachOut] = None` to `LineupOut` (exact
insertion point: right after `max_diamond`).

(If `EquippedCoachOut`-equivalent already exists importable from
`app.schemas.club_squad` with an identical shape, prefer importing and
reusing it over redefining — check first; but note it currently lives in a
club-specific schema module, so defining a lineup-local copy here may be
the more correct call for a personal-track schema file not to depend on a
club-track one. Use your judgment and note which you chose in your report.)

- [ ] **Step 6: Add the rarity-tier Arena bonus function**

In `backend/app/services/coach_boost_service.py`, add (do not modify any
existing function in this file — this is purely additive, at the end of the
file):

```python
# Starting-point numbers on the same scale this codebase already uses for
# zone-boost base_units (spec §4: common=1 tier -> 2 rating points, up to
# legendary=4 tier -> 8) — not validated by simulation yet, same "starting
# point, not final" caveat every other magnitude in this match engine
# carries until it's been through a real balance pass.
_ARENA_RARITY_TEAM_STRENGTH_BONUS: dict[Rarity, int] = {
    Rarity.common: 2,
    Rarity.rare: 4,
    Rarity.epic: 6,
    Rarity.legendary: 8,
}


def arena_rarity_team_strength_bonus(coach: "Coach | None") -> int:
    """A simple, universal Card Arena squad-power bonus scaled only by the
    equipped coach's own rarity — independent of which specific boosts it
    has. This is a deliberately simpler, first-cut mechanic than
    arena_category_bonus/arena_pass_fail_chance_reduction/
    arena_team_strength_bonus above (which read individual boost types via
    ActiveCoachBoosts) — those remain in place for a future full-fidelity
    Arena pass; this function only ever reads .rarity, never .boosts."""
    if coach is None:
        return 0
    return _ARENA_RARITY_TEAM_STRENGTH_BONUS.get(coach.rarity, 0)
```

(`Rarity` should already be imported in this file — confirm.)

- [ ] **Step 7: Thread the bonus through `calculate_base_strength`**

In `backend/app/services/lineup_service.py`, change `calculate_base_strength`'s
signature and add the bonus right before the final `round(total)`:

```python
def calculate_base_strength(cards_with_slots: list[tuple[UserCard, FormationSlot]], coach: "Coach | None" = None) -> int:
    if not cards_with_slots:
        return 0

    # ... existing body unchanged, down to the chemistry_bonus line ...

    total += chemistry_bonus
    total += arena_rarity_team_strength_bonus(coach)

    return round(total)
```

(Read the real current function body first — copy this exactly, only adding
the one new line and the new optional parameter; do not touch any other
line inside this function.) Add the import:
`from app.services.coach_boost_service import arena_rarity_team_strength_bonus`.

**Critical — verify this doesn't affect the 3 other callers**: run
`grep -rn "calculate_base_strength(" backend/app/` and confirm
`club_tactical_profile_service.py`, `tournament_simulation_service.py`, and
`club_squad_service.py`'s call sites all still call it with exactly one
positional argument (`cards_with_slots`), never passing a second — if any of
them do pass something, STOP and report NEEDS_CONTEXT rather than guessing
what that would mean; per this plan's Global Constraints, none of those
three files may be edited.

- [ ] **Step 8: Add `set_lineup_coach` and wire the coach into `get_active_lineup`**

In `lineup_service.py`, add (near `set_tactic`):

```python
async def set_lineup_coach(db: AsyncSession, user: User, payload: "LineupCoachSetRequest") -> LineupOut:
    lineup = await _get_or_create_lineup(db, user.id)
    if payload.user_coach_card_id is not None:
        card = await db.get(UserCoachCard, payload.user_coach_card_id)
        if card is None or card.user_id != user.id:
            raise ConflictError("Тренер не найден в вашей коллекции")
    lineup.user_coach_card_id = payload.user_coach_card_id
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user)
```

Add the import: `from app.models.user_coach_card import UserCoachCard`,
`from app.schemas.lineup import LineupCoachSetRequest` (or however this
file's existing schema imports are structured — check first).

In `get_active_lineup`, after loading `lineup` (via `_get_or_create_lineup`),
eager-load the coach chain so `resolve_active_boosts`/`calculate_base_strength`
never trigger a lazy load. `_active_lineup_query` currently does
`.options(joinedload(Lineup.cards))` — extend it:

```python
def _active_lineup_query(user_id: int):
    return (
        select(Lineup)
        .where(Lineup.user_id == user_id, Lineup.is_active.is_(True))
        .options(
            joinedload(Lineup.cards),
            joinedload(Lineup.user_coach_card).joinedload(UserCoachCard.coach).selectinload(Coach.boosts),
        )
    )
```

Add `from app.models.coach import Coach` and `from sqlalchemy.orm import
selectinload` (alongside the existing `joinedload` import) if not already
present.

In `get_active_lineup`'s body, where `strength = calculate_base_strength(cards_with_slots) if is_complete else None` is computed, change to pass the coach:

```python
    coach = lineup.user_coach_card.coach if lineup.user_coach_card else None
    strength = calculate_base_strength(cards_with_slots, coach=coach) if is_complete else None
```

And in the final `LineupOut(...)` construction, add:

```python
        coach=EquippedCoachOut(
            id=coach.id, display_name=coach.display_name, rarity=coach.rarity.value,
            image_path=coach.image_path, boosts=coach.boosts,
        ) if coach else None,
```

(Adjust field names to match whatever real shape `EquippedCoachOut` ended
up with in Step 5 — this is illustrative, not gospel, if your judgment call
there produced a different but equivalent shape.)

- [ ] **Step 9: Add the router endpoint**

In `backend/app/routers/lineups.py`, add:

```python
from app.services.lineup_service import get_active_lineup, set_lineup, set_lineup_coach, set_tactic
from app.schemas.lineup import LineupCoachSetRequest, LineupOut, LineupSetRequest, LineupTacticRequest


@router.put("/coach", response_model=LineupOut)
async def update_lineup_coach(
    payload: LineupCoachSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup_coach(db, user, payload)
```

- [ ] **Step 10: Write the migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest revision -m "lineup coach"`

Rename to `0098_lineup_coach.py`:

```python
"""Add Lineup.user_coach_card_id — personal Card Arena coach equip

Revision ID: 0098
Revises: 0097
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lineups", sa.Column("user_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_lineups_user_coach_card_id", "lineups", "user_coach_cards", ["user_coach_card_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lineups_user_coach_card_id", "lineups", type_="foreignkey")
    op.drop_column("lineups", "user_coach_card_id")
```

- [ ] **Step 11: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_lineup_coach.py -v`

Expected: PASS.

- [ ] **Step 12: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: same pass count as Task 3's end state plus your 2 new tests, no
new failures. Also run `docker run --rm -v "$(pwd)/backend:/app" --entrypoint
python football-cards-backend:latest -c "from app.main import app"` to
confirm the router change didn't break app startup.

- [ ] **Step 13: Verify the migration against real Postgres**

Same pattern as Tasks 1-2 — `alembic upgrade head --sql`, and against the
real `docker compose` Postgres if available.

- [ ] **Step 14: Commit**

```bash
git add backend/app/models/lineup.py backend/app/schemas/lineup.py backend/app/services/lineup_service.py backend/app/services/coach_boost_service.py backend/app/routers/lineups.py backend/alembic/versions/0098_lineup_coach.py backend/tests/test_lineup_coach.py
git commit -m "feat(arena): add personal coach equip with a rarity-tier squad-power bonus"
```

---

### Task 5: Backend — `GET /lineups/coach-cards` (list owned personal coaches)

**Files:**
- Modify: `backend/app/services/lineup_service.py`
- Modify: `backend/app/routers/lineups.py`
- Test: `backend/tests/test_lineup_coach.py` (extend, from Task 4)

**Interfaces:**
- Consumes: `UserCoachCard` (Task 1).
- Produces: `list_user_coach_cards(db, user) -> list[UserCoachCardOut]`;
  `GET /lineups/coach-cards` — Task 10 (frontend Arena picker) consumes this.

(This task was folded out of Task 4 during self-review to keep Task 4's
scope to "equip a coach already owned" and this task's scope to "list which
coaches are owned" — the same split the club track used between its Task 5
[equip endpoint] and part of Task 5 [list endpoint], here made explicit as
its own task since Task 4 was already large. It's sequenced right after
Task 4 and before Task 6, since Task 6's frontend API client wraps this
endpoint.)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_lineup_coach.py`:

```python
async def test_list_user_coach_cards_returns_owned_coaches_with_boosts(client, db_session, bot_token):
    headers = telegram_headers(840203, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    coach = Coach(display_name="List Test Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=8.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    user = await get_user_by_telegram_id(db_session, 840203)
    db_session.add(UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source="pack"))
    await db_session.commit()

    resp = await client.get("/api/v1/lineups/coach-cards", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert len(body[0]["coach"]["boosts"]) == 3
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_lineup_coach.py -k list_user_coach_cards -v`

Expected: FAIL — 404, route doesn't exist.

- [ ] **Step 3: Implement `list_user_coach_cards`**

In `lineup_service.py`, add (mirrors
`club_squad_service.list_club_coach_cards`'s exact shape — check that
function first if it exists, for the precise eager-load pattern):

```python
async def list_user_coach_cards(db: AsyncSession, user: User) -> list["UserCoachCardOut"]:
    result = await db.execute(
        select(UserCoachCard)
        .where(UserCoachCard.user_id == user.id)
        .options(joinedload(UserCoachCard.coach).selectinload(Coach.boosts))
        .order_by(UserCoachCard.id)
    )
    return result.unique().scalars().all()
```

Add a `UserCoachCardOut` schema to `backend/app/schemas/lineup.py` (mirrors
`ClubCoachCardOut` from `app.schemas.club_squad`: `id: int, serial_number:
int, coach: CoachOut, acquired_at: datetime`).

- [ ] **Step 4: Add the router endpoint**

In `backend/app/routers/lineups.py`:

```python
@router.get("/coach-cards", response_model=list[UserCoachCardOut])
async def read_user_coach_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_user_coach_cards(db, user)
```

(Place this route before `/active`'s own path-parameter-free routes if
FastAPI's route-matching order matters here — it shouldn't, since neither
`/coach-cards` nor `/active` nor `/coach` has a path parameter to collide
with, unlike the club-track router-ordering bug from the prior plan — but
double-check there's no `/{something}` route in this same router file that
could shadow it; if there is, register `/coach-cards` before it.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_lineup_coach.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 6: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: same pass count as Task 4's end state plus this test, no new
failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/lineup_service.py backend/app/routers/lineups.py backend/app/schemas/lineup.py backend/tests/test_lineup_coach.py
git commit -m "feat(arena): add GET /lineups/coach-cards to list owned personal coaches"
```

---

### Task 6: Frontend — types + API clients

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/lineups.ts`

**Interfaces:**
- Consumes: `GET /lineups/coach-cards` (Task 5).
- Produces: `Pack.coach_drop_chance: number`; `UserCoachCard` type (mirrors
  `ClubCoachCard`'s shape: `id, serial_number, coach: EquippedCoach,
  acquired_at`); `OpenedCoachCard` (mirrors `OpenedCard`, with `card:
  UserCoachCard`); `PackOpenResult.coach_cards: OpenedCoachCard[]` (new,
  additive — `PackOpenResult.cards` stays exactly as it is); `Lineup.coach:
  EquippedCoach | null`; `fetchUserCoachCards`, `setLineupCoach` — Tasks 8,
  10 consume this.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, add `coach_drop_chance: number;` to the
`Pack` interface (exact insertion point: right after `sort_order`, matching
Task 2's backend field ordering note — check the real current `Pack`
interface's field order and place it correctly).

Add, near the existing `OpenedCard`/`PackOpenResult` interfaces:

```typescript
export interface UserCoachCard {
  id: number;
  serial_number: number;
  coach: EquippedCoach;
  acquired_at: string;
}

export interface OpenedCoachCard {
  card: UserCoachCard;
  is_new: boolean;
  duplicate_count: number;
}
```

Add `coach_cards: OpenedCoachCard[];` to `PackOpenResult` (right after
`cards: OpenedCard[];` — do not change `cards`'s own type).

Add `coach: EquippedCoach | null;` to the `Lineup` interface (right after
`max_diamond`).

`EquippedCoach` already exists in this file (added in the club-track work) —
reuse it as-is, don't redefine.

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS (additive types only).

- [ ] **Step 3: Add the API client functions**

In `frontend/src/api/lineups.ts`, add both — Task 5's `GET /lineups/coach-cards`
endpoint already exists at this point, so this is a plain wrap, not a
speculative one:

```typescript
export async function setLineupCoach(userCoachCardId: number | null): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/coach", { user_coach_card_id: userCoachCardId });
  return data;
}

export async function fetchUserCoachCards(): Promise<UserCoachCard[]> {
  const { data } = await api.get<UserCoachCard[]>("/lineups/coach-cards");
  return data;
}
```

(Check whether this codebase already has a `frontend/src/api/coaches.ts` or
similar personal-coach file from Phase 1's admin work that might be a
better home for `fetchUserCoachCards` specifically — if so, add it there
instead and import from there in Task 10; otherwise `lineups.ts` alongside
`setLineupCoach` is the right home, since both are lineup/equip-related.)

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/lineups.ts
git commit -m "feat(arena): frontend types and API clients for personal coaches"
```

---

### Task 7: Frontend — admin pack form gains `coach_drop_chance`

**Files:**
- Modify: `frontend/src/admin/pages/AdminPacksPage.tsx`

**Interfaces:**
- Consumes: `Pack.coach_drop_chance` (Task 6).

- [ ] **Step 1: Read the current file in full**

Already partially read this session — re-read to confirm the exact
`PackForm` interface, `packToForm`/`buildPayload` functions, and the
`NumField` helper component's real current shape.

- [ ] **Step 2: Add the field to the form**

Add `coach_drop_chance: number;` to `PackForm` (right after `card_count`).

In `packToForm`, add: `coach_drop_chance: (p?.coach_drop_chance ?? 0) * 100,`
(0-100 percentage UX convention, matching the club-track admin form's
identical choice).

In `buildPayload`, add: `coach_drop_chance: form.coach_drop_chance / 100,`.

In the form's JSX, add a `NumField` right after the existing "Карт в паке"
one:

```tsx
<NumField label="Шанс тренера вместо игрока (%) — 0 = только игроки" value={form.coach_drop_chance} min={0} max={100} onChange={(v) => setForm({ ...form, coach_drop_chance: v })} />
```

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/admin/pages/AdminPacksPage.tsx
git commit -m "feat(packs): add coach_drop_chance to the personal pack admin form"
```

---

### Task 8: Frontend — coach cards in the pack-opening summary

**Files:**
- Modify: `frontend/src/pages/PackOpenPage.tsx`

**Interfaces:**
- Consumes: `PackOpenResult.coach_cards`, `OpenedCoachCard` (Task 6).

- [ ] **Step 1: Read the current file in full**

Already read in full this session (416 lines) — re-read to confirm nothing
shifted. This is a deliberately minimal change: coach cards appear in the
summary grid, the reveal-stage state machine (`STAGES`/`cardIndex`/
`stageIndex`/`skipAll`/single-card-shortcut/Stars-reopen) is completely
untouched.

- [ ] **Step 2: Add coach cards to the `Summary` component's grid**

In the `Summary` function, the existing grid renders `result.cards.map((opened) => ...)`.
Add a second `.map` for coach cards, right after it, inside the same
`grid grid-cols-2 gap-3 sm:grid-cols-3` container:

```tsx
{result.coach_cards.map((opened) => (
  <div
    key={`coach-${opened.card.id}`}
    className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.coach.rarity]} p-[2px] ${RARITY_GLOW[opened.card.coach.rarity]}`}
  >
    <div className="flex flex-col rounded-[14px] bg-bg-surface">
      <img
        src={staticUrl(opened.card.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt={opened.card.coach.display_name}
        className="aspect-square w-full object-cover"
      />
      <div className="p-2 text-center">
        <p className="truncate text-xs font-bold text-ink-chalk">{opened.card.coach.display_name}</p>
        <p className="text-[10px] text-ink-mist">Тренер · {RARITY_LABELS[opened.card.coach.rarity]}</p>
      </div>
    </div>
    {opened.is_new && (
      <span className="absolute left-1 top-1 rounded-full bg-accent-green px-1.5 py-0.5 text-[9px] font-bold text-bg-base">NEW</span>
    )}
    {opened.duplicate_count > 1 && (
      <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-[9px] font-bold text-ink-chalk">
        ×{opened.duplicate_count}
      </span>
    )}
  </div>
))}
```

Also update `showRecap`'s condition (currently `result.cards.length > 1`) to
account for coach cards too, so a pack that yields e.g. 1 player + 1 coach
still shows the recap heading instead of treating it as a trivial
single-card pack:

```typescript
const showRecap = result.cards.length + result.coach_cards.length > 1;
```

And update `nextCard`'s single-card-shortcut condition (currently checks
`result.cards.length === 1 && ...`) to also require zero coach cards, so a
1-player+1-coach pack correctly falls through to the summary screen instead
of taking the single-card shortcut:

```typescript
    if (
      result.cards.length === 1 &&
      result.coach_cards.length === 0 &&
      !result.referral_bonus_coins &&
      result.collection_rewards.length === 0 &&
      !result.pack.bonus_coins &&
      !result.pack.badge
    ) {
```

(The reveal-stage loop itself, `result.cards[cardIndex]`/`result.cards.length`,
stays completely untouched — a coach-only slot never appears in the
staged reveal, only in the summary grid, per this plan's own design.)

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 4: Verify live in the browser**

Set an existing pack's `coach_drop_chance` to 100% via the admin form (Task
6), open it as a player. Confirm: the reveal animation still plays through
only the player cards (if `card_count` splits between coach/player slots,
fewer reveal steps than `card_count`) or is skipped entirely if all slots
rolled coaches (in which case the page should go straight to
`phase="summary"` — check `nextCard`'s logic handles `result.cards.length === 0`
correctly, i.e. `cardIndex < result.cards.length - 1` is `0 < -1`, false, so
the "if single-card..." branch's `result.cards.length === 1` check is also
false, falling through correctly to `setPhase("summary")` — verify this is
actually what happens by testing a pack with `coach_drop_chance=1.0` and a
small `card_count`, not just reasoning about it). Confirm the summary grid
shows coach tiles with the "Тренер · <rarity>" label. Check the browser
console for errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PackOpenPage.tsx
git commit -m "feat(packs): show coach cards in the pack-opening summary grid"
```

---

### Task 9: Frontend — Arena squad-power tooltip

**Files:**
- Modify: `frontend/src/pages/ArenaPage.tsx`

**Interfaces:**
- Consumes: nothing new — this is copy/UI only, using the real formula
  already read from `lineup_service.calculate_base_strength` while writing
  this plan.

- [ ] **Step 1: Read the current file in full**

Already partially read this session — re-read the section around `"Сила:
{lineup.team_strength}"` (currently a single `<span>`) to find the exact
insertion point.

- [ ] **Step 2: Add a tap-to-reveal hint next to the strength display**

Add a state variable near the top of the component:

```typescript
  const [strengthHintOpen, setStrengthHintOpen] = useState(false);
```

Change the existing strength display block:

```tsx
{lineup?.is_complete && (
  <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>
)}
```

to:

```tsx
{lineup?.is_complete && (
  <button
    onClick={() => setStrengthHintOpen((v) => !v)}
    className="flex items-center gap-1 font-mono text-sm font-bold text-accent-cyan"
  >
    Сила: {lineup.team_strength}
    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/10 text-[10px] font-bold text-ink-mist-dim">?</span>
  </button>
)}
```

Add the hint panel right after the strength-display line, before the
diamond-count line:

```tsx
{strengthHintOpen && (
  <div className="mb-3 rounded-xl bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-ink-mist">
    <p className="mb-1 font-semibold text-ink-chalk">Что влияет на силу состава:</p>
    <p>· Позиция игрока: 100% рейтинга на своей позиции, 90% на смежной, 75% не по профилю</p>
    <p>· Химия: бонус за игроков одного клуба и одной страны в составе</p>
    <p>· Редкость карточки: чем выше редкость, тем больше вклад рейтинга в силу</p>
    <p>· Тренер: даёт фиксированный бонус к силе по своей редкости, независимо от бустов</p>
    <p className="mt-1 text-ink-mist-dim">Поэтому простая замена на игрока с более высоким рейтингом не всегда увеличивает силу — важна ещё позиция и химия.</p>
  </div>
)}
```

(This copy is written from the real formula in `lineup_service.calculate_base_strength`
— position fit multipliers 1.0/0.9/0.75, the club/country chemistry bonus,
the `1 + 0.03 * RARITY_ORDER[rarity]` rarity multiplier, and this plan's own
new coach bonus. Keep it accurate to that function; if a future change
alters the formula, this copy must be updated too — it is not generic
placeholder text, it's a direct description of real game logic.)

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 4: Verify live in the browser**

Open `/matches` (or wherever `ArenaPage.tsx` is routed — check `App.tsx` for
the real path) with a complete lineup. Tap the "?" next to "Сила: N" and
confirm the hint panel toggles open/closed and reads correctly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ArenaPage.tsx
git commit -m "feat(arena): add a squad-power explainer hint"
```

---

### Task 10: Frontend — Arena grid-based coach equip

**Files:**
- Create: `frontend/src/components/cards/UserCoachCardPickerModal.tsx`
- Modify: `frontend/src/pages/ArenaPage.tsx`

**Interfaces:**
- Consumes: `fetchUserCoachCards`, `setLineupCoach`, `UserCoachCard`,
  `EquippedCoach` (Task 6); `GET /lineups/coach-cards`, `PUT /lineups/coach`
  (Task 5).

- [ ] **Step 1: Read the current files in full**

Read `frontend/src/components/clubs/ClubCoachCardPickerModal.tsx` in full —
this is the exact component to mirror, **including its just-shipped
deduplication fix** (grouping by `coach.id`, keeping the lowest
`serial_number` copy as the representative card) — do not reintroduce the
duplicate-rows bug the user just had fixed on the club side. Re-read the
current full `frontend/src/pages/ArenaPage.tsx` (already partially read
this session) to confirm the exact GK-row JSX structure and surrounding
state/mutation patterns.

- [ ] **Step 2: Create `UserCoachCardPickerModal.tsx`**

Direct mirror of `ClubCoachCardPickerModal.tsx`, including its dedup logic,
substituting `UserCoachCard` for `ClubCoachCard`:

```tsx
import { AnimatePresence, motion } from "framer-motion";

import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { RARITY_LABELS } from "@/lib/rarity";
import type { UserCoachCard } from "@/types";

interface Props {
  open: boolean;
  cards: UserCoachCard[];
  onSelect: (card: UserCoachCard | null) => void;
  onClose: () => void;
}

function dedupeByCoach(cards: UserCoachCard[]): UserCoachCard[] {
  // Mirrors ClubCoachCardPickerModal's own dedup — a player can own several
  // UserCoachCard copies of the same underlying Coach (packs can repeat),
  // but every copy shares identical boosts/rarity/name, so the picker
  // shows one row per distinct coach, not one per owned card.
  const byCoach = new Map<number, UserCoachCard>();
  for (const card of cards) {
    const existing = byCoach.get(card.coach.id);
    if (!existing || card.serial_number < existing.serial_number) {
      byCoach.set(card.coach.id, card);
    }
  }
  return [...byCoach.values()];
}

export default function UserCoachCardPickerModal({ open, cards, onSelect, onClose }: Props) {
  const uniqueCards = dedupeByCoach(cards);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-base p-5"
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            exit={{ y: 100 }}
            transition={{ type: "spring", damping: 26, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <p className="font-display text-lg font-bold text-slate-100">Выбери тренера</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-slate-300">Закрыть</button>
            </div>
            <button
              onClick={() => onSelect(null)}
              className="mb-3 w-full rounded-xl border border-dashed border-white/15 py-2.5 text-xs font-semibold text-ink-mist-dim active:scale-[0.99]"
            >
              Без тренера
            </button>
            {uniqueCards.length === 0 ? (
              <EmptyState icon={IconCollection} title="У тебя пока нет тренера" description="Открой паки, чтобы получить тренера" />
            ) : (
              <div className="flex flex-col gap-2">
                {uniqueCards.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelect(c)}
                    className="flex items-center gap-3 rounded-xl bg-white/5 p-2.5 text-left active:scale-[0.99]"
                  >
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-black/40">
                      <img
                        src={staticUrl(c.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                        alt="" className="h-full w-full object-cover"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink-chalk">{c.coach.display_name}</p>
                      <p className="text-[10px] text-ink-mist-dim">{RARITY_LABELS[c.coach.rarity]}</p>
                      <p className="mt-0.5 truncate text-[10px] text-ink-mist">
                        {c.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

- [ ] **Step 3: Add the grid cell and equipped-coach detail to `ArenaPage.tsx`**

Add the import: `import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";`
and `import { fetchUserCoachCards, setLineupCoach } from "@/api/lineups";`.

Add state and the query/mutation, near the existing ones:

```typescript
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const { data: coachCards } = useQuery({ queryKey: ["lineup", "coach-cards"], queryFn: fetchUserCoachCards });
  const setCoachMutation = useMutation({
    mutationFn: setLineupCoach,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["lineup"] }); setCoachPickerOpen(false); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось назначить тренера")),
  });
```

In the GK row (`category === "GK"` inside the `(["FWD", "MID", "DEF", "GK"] as const).map(...)` block), add a coach cell mirroring the club squad page's own — this page has no `canEdit` gating (a player always edits their own personal squad), so the cell is unconditionally tappable:

```tsx
              {category === "GK" && (
                <button
                  onClick={() => setCoachPickerOpen(true)}
                  disabled={setCoachMutation.isPending}
                  className={`absolute left-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${setCoachMutation.isPending ? "opacity-60" : ""}`}
                >
                  {lineup?.coach ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img
                          src={staticUrl(lineup.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[8px] font-bold leading-none text-accent-cyan">Тренер</span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-[8px] text-ink-mist-dim">Тренер</span>
                    </>
                  )}
                </button>
              )}
```

(This row's own container already needs `className="relative flex justify-evenly gap-2"` for the `absolute` positioning to anchor correctly — check the real current row `<div>`'s className and confirm `relative` is already there, matching the pre-existing pattern this file already uses for its player-slot rows.)

Add the equipped-coach detail block right after the grid's closing `</div>`
(mirroring exactly the club squad page's own restored block from its
final-review fix):

```tsx
{lineup?.coach && (
  <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
    <p className="text-xs font-semibold text-ink-chalk">{lineup.coach.display_name}</p>
    <p className="mt-0.5 text-[11px] text-ink-mist">
      {lineup.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
    </p>
  </div>
)}
```

Add the import `import { BOOST_TYPE_LABELS } from "@/lib/coaches";` if not
already present.

Add the modal render near the existing `<CardPickerModal .../>`:

```tsx
<UserCoachCardPickerModal
  open={coachPickerOpen}
  cards={coachCards ?? []}
  onSelect={(card) => setCoachMutation.mutate(card ? card.id : null)}
  onClose={() => setCoachPickerOpen(false)}
/>
```

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Verify live in the browser**

Ensure the dev stack is running and rebuilt (`docker compose up -d --build
frontend backend` — this repo's `docker-compose.override.yml` disables
hot-reload). Own at least one `UserCoachCard` (open a `coach_drop_chance`-
enabled personal pack via Task 7's flow, or insert one directly via
`docker compose exec postgres psql`). Open the Arena page, confirm the GK
row shows a coach cell in the corner with GK centered, tapping it opens the
picker showing every distinct owned coach (not duplicated) with boosts
visible, selecting one equips it and shows the name/boosts detail block
under the grid, and — critically — confirm "Сила: N" actually changes by
the expected rarity-tier amount when a coach is equipped vs. cleared (e.g.
+6 for an epic coach). Check the browser console for errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/cards/UserCoachCardPickerModal.tsx frontend/src/pages/ArenaPage.tsx
git commit -m "feat(arena): equip a personal coach via a grid cell + skills-visible picker"
```

---

### Task 11: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: all pass except the one pre-existing, already-flagged, unrelated
failure (`test_tasks.py::test_task_reward_pack_grants_all_cards`).

- [ ] **Step 2: Run the full frontend typecheck and lint**

Run: `cd frontend && npm run typecheck` — expect PASS.
Run: `cd frontend && npm run lint` — this repo has a known, pre-existing,
unrelated `eslint.config.js`-missing failure; confirm it's that exact same
error, not a new one.

- [ ] **Step 3: Verify the full personal-pack-to-Arena flow live in the browser**

As an admin, set a real pack's `coach_drop_chance` to a mid-range value
(e.g. 30%) via `/admin/packs`. As a player, open it several times, confirm
a mix of players and coaches appears across openings (coaches show in the
summary grid with a "Тренер" label, players get the full staged reveal as
before). Confirm a diamond-guaranteed pack (if one exists in seed data, or
create one) never yields a coach. Navigate to the Arena page, confirm the
new coach is available in the picker, equip it, confirm the strength number
updates by the correct rarity-tier amount, confirm the hint panel explains
the real formula correctly. Check the browser console for errors throughout.

- [ ] **Step 4: Confirm the migration chain is sound end-to-end**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic
football-cards-backend:latest history` — confirm `0096`, `0097`, `0098` all
appear in order, no branching.

- [ ] **Step 5: Report**

No commit for this task (verification only) — summarize the full pass/fail
state of Steps 1-4.

---

## Self-Review Notes

**Spec coverage:** all 3 "Основная игра" requirements from the design
conversation are covered — Task 1-3 (coaches in regular packs), Task 4/5/10
(coach available in Card Arena, rarity-scaled squad-power bonus), Task 9
(squad-power explainer hint).

**Placeholder scan:** every step has real code or a narrow, explicit "read
file X first, the exact name is there" pointer — no bare "add appropriate
handling" anywhere in the plan.

**Type consistency:** `create_user_coach_card` (Task 1) is called with
identical arguments in Task 3's `roll_and_create_cards`.
`OpenedCoachCardOut`/`OpenedCoachCard` (backend/frontend) match field-for-
field. `arena_rarity_team_strength_bonus` (Task 4) is defined once and
called once, from `calculate_base_strength`, never redefined.
`fetchUserCoachCards`/`setLineupCoach` (Task 6) match
`GET /lineups/coach-cards`/`PUT /lineups/coach` (Task 5/4) exactly.

**Fixed during self-review:** originally drafted Task 4 as one task
covering both the equip endpoint and the list endpoint — split once the
task's own step count made clear it was really two independently-testable
deliverables, matching this plan's own Task Right-Sizing guidance. The
split also surfaced a real task-ordering bug: the list endpoint (now Task 5)
must exist before the frontend types/API task (now Task 6) can wrap it
without guessing — the plan originally numbered them in the wrong order
(frontend before its own backend dependency, as "Task 5" and "Task 5b").
Renumbered the whole tail of the plan (Tasks 5-11) so the physical,
numeric, and dependency order all agree — no out-of-order dispatch note is
needed; execute 1 through 11 in a straight line.
