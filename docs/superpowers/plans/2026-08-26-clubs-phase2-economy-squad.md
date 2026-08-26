# Clubs — Phase 2: Economy & Squad Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every club a budget, a club-owned card pool, a fixed-4-3-3 squad the captain/assistants can manage, and a small club-only pack list to spend the budget on. This is Phase 2 of the Clubs feature — Phase 1 (creation, membership, roles, invites) is already merged; the tournament system is Phase 3, not started.

**Architecture:** Every backend piece reuses an exact precedent already in this codebase rather than inventing a new pattern: `create_club_card` mirrors `card_creation.create_user_card` verbatim (own row-locked per-player serial counter); the club squad editor reuses `lineup_service`'s `FORMATION_SLOTS`/`CATEGORY_POSITIONS`/`calculate_base_strength` directly (a `ClubCard` exposes the same `.player` relationship shape a `UserCard` does, so the strength formula needs no club-specific fork); `ClubPack` mirrors `Pack`'s shape and `club_pack_service.open_club_pack` mirrors `pack_service.open_pack`'s flow (idempotency, row-locked debit, roll-and-mint), just paying from `Club.budget` instead of a personal wallet; the daily claim mirrors `daily_reward_service`'s `local_today()`-keyed uniqueness. The frontend squad editor is a near-verbatim adaptation of `ArenaPage.tsx`'s tap-slot-then-modal-picker lineup UI.

**One deliberate simplification vs. the original design spec:** the spec's `ClubBenchCard` table is dropped. A club's "bench" for Phase 2 is simply every `ClubCard` the club owns that isn't currently placed in a `ClubLineupCard` slot — exactly how the personal squad editor's `CardPickerModal` already treats "available cards" (filtered from the full collection, not a separately-tracked pool). The starting-squad seed still mints 4 extra cards (one per category) beyond the 11 starters, satisfying the spec's "4 reserves from day one" requirement — they just aren't tracked in a dedicated table. Phase 3 (tournaments) is what actually needs a *designated* substitution pool for its auto-sub logic, and can introduce `ClubBenchCard` then if the simple "any unused club card" model turns out to be insufficient; introducing it now would be unused infrastructure.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, PostgreSQL, Pydantic v2 (backend); React 18, TypeScript, Vite, TanStack Query, Tailwind, Framer Motion (frontend).

**Spec:** [docs/superpowers/specs/2026-08-26-clubs-design.md](../specs/2026-08-26-clubs-design.md) — this plan implements the "Economy" section in full except the mini-game contribution mode (deferred — it touches every existing mini-game's service/router/frontend individually and deserves its own plan once this phase's budget plumbing exists to credit into), and the squad-management half of the spec (fixed formation, bench-as-reserve-pool). Cups/stars/tournament sections remain out of scope for Phase 2.

## Global Constraints

- Every club budget-mutating operation must row-lock the `Club` row first (`club_service._lock_club`, already built in Phase 1) before reading/writing `Club.budget`.
- `Club.budget` gets a `CHECK (budget >= 0)` constraint from day one — unlike the personal-coin clawback feature, there's no legitimate reason for a club budget to go negative.
- Every card-minting operation must row-lock the `Player` row's serial counter exactly like `create_user_card` already does (`db.refresh(player, attribute_names=[...], with_for_update=True)`), scoped to the new `next_club_serial_number` column — never a broader refresh (breaks the same nullable-outer-join/eager-load caveats already documented in `card_creation.py`).
- Club cards never touch `UserCard`/personal collections — no `owner_id`, no trade-lock fields, entirely separate serial numbering (`Player.next_club_serial_number`, independent of `Player.next_serial_number`).
- Only captain + assistants may mutate a club's lineup or open club packs; all members may view.
- Never hardcode `club_daily_reward_coins` or any club pack price — always read from `game_config_service.get_config(db)` / the `ClubPack` row.
- Alembic revisions continue sequentially from `0056` (Phase 1's head) — this plan uses `0057`–`0059`.
- Player-facing error messages in Russian, matching Phase 1's convention.
- `git add` discipline: this working tree may still carry files from other, unrelated sessions of work — every task below names its exact file list; stage only those files, never `-A`/`.`.

---

### Task 1: Club budget, budget ledger, and `club_daily_reward_coins`

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/club.py`
- Modify: `backend/app/models/game_config.py`
- Create: `backend/app/models/club_budget.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0057_club_budget.py`

**Interfaces:**
- Produces: `ClubBudgetTransactionType` enum (`daily_claim`, `pack_purchase`), `Club.budget` column, `ClubBudgetTransaction` model, `GameConfig.club_daily_reward_coins` — consumed by every later task in this plan.

- [ ] **Step 1: Add the enum**

In `backend/app/models/enums.py`, add (anywhere near the other small enums):

```python
class ClubBudgetTransactionType(str, enum.Enum):
    daily_claim = "daily_claim"
    pack_purchase = "pack_purchase"
```

- [ ] **Step 2: Add `Club.budget`**

In `backend/app/models/club.py`, add to the `Club` class (after `invite_code`) and add the `__table_args__` block (the class currently has none):

```python
    budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

```python
    __table_args__ = (CheckConstraint("budget >= 0", name="ck_clubs_budget_non_negative"),)
```

Add `CheckConstraint` to the existing `from sqlalchemy import ...` line in that file.

- [ ] **Step 3: `ClubBudgetTransaction` model**

Create `backend/app/models/club_budget.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ClubBudgetTransactionType
from app.models.mixins import utcnow


class ClubBudgetTransaction(Base):
    __tablename__ = "club_budget_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_before: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[ClubBudgetTransactionType] = mapped_column(
        Enum(ClubBudgetTransactionType, name="club_budget_transaction_type_enum"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    related_object_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    related_object_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
```

- [ ] **Step 4: `GameConfig.club_daily_reward_coins`**

In `backend/app/models/game_config.py`, add:

```python
    club_daily_reward_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
```

- [ ] **Step 5: Register the model**

In `backend/app/models/__init__.py`, add `from app.models.club_budget import ClubBudgetTransaction` and `"ClubBudgetTransaction"` to `__all__`, following the file's existing alphabetical-ish placement (near the `Club` import from Phase 1).

- [ ] **Step 6: Migration**

Create `backend/alembic/versions/0057_club_budget.py`:

```python
"""Club budget: Club.budget, ClubBudgetTransaction, club_daily_reward_coins

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("budget", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_clubs_budget_non_negative", "clubs", "budget >= 0")

    op.add_column("game_config", sa.Column("club_daily_reward_coins", sa.Integer(), nullable=False, server_default="200"))

    op.create_table(
        "club_budget_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "type", sa.Enum("daily_claim", "pack_purchase", name="club_budget_transaction_type_enum"), nullable=False
        ),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("related_object_type", sa.String(length=64), nullable=True),
        sa.Column("related_object_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_budget_transactions_club_id", "club_budget_transactions", ["club_id"])
    op.create_index("ix_club_budget_transactions_created_at", "club_budget_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_club_budget_transactions_created_at", table_name="club_budget_transactions")
    op.drop_index("ix_club_budget_transactions_club_id", table_name="club_budget_transactions")
    op.drop_table("club_budget_transactions")
    op.drop_column("game_config", "club_daily_reward_coins")
    op.drop_constraint("ck_clubs_budget_non_negative", "clubs", type_="check")
    op.drop_column("clubs", "budget")
    bind = op.get_bind()
    sa.Enum(name="club_budget_transaction_type_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 7: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d clubs" -c "\d club_budget_transactions"
```
Confirm `budget` column + `ck_clubs_budget_non_negative` constraint on `clubs`, and the new table's shape.

- [ ] **Step 8: Sanity check + commit**

```bash
docker compose exec -T backend python -c "from app.main import app; print('ok')"
git add backend/app/models/enums.py backend/app/models/club.py backend/app/models/game_config.py backend/app/models/club_budget.py backend/app/models/__init__.py backend/alembic/versions/0057_club_budget.py
git commit -m "Add club budget, budget ledger, and club_daily_reward_coins"
```

---

### Task 2: `ClubCard` model, separate serial numbering, and `create_club_card`

**Files:**
- Modify: `backend/app/models/enums.py`
- Create: `backend/app/models/club_card.py`
- Modify: `backend/app/models/player.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/club_card_service.py`
- Create: `backend/alembic/versions/0058_club_cards.py`
- Create: `backend/tests/test_club_cards.py`

**Interfaces:**
- Produces: `ClubCardSource` enum (`starter_seed`, `club_pack`), `ClubCard(id, club_id, player_id, source, source_ref_id, acquired_at, serial_number)` with a `.player` relationship, `Player.next_club_serial_number`, `create_club_card(db, club_id, player_id, source, source_ref_id=None) -> ClubCard` — consumed by Tasks 3 (seeding), 6 (lineup), 8 (pack opening).

- [ ] **Step 1: Add the enum**

In `backend/app/models/enums.py`:

```python
class ClubCardSource(str, enum.Enum):
    starter_seed = "starter_seed"
    club_pack = "club_pack"
```

- [ ] **Step 2: `ClubCard` model**

Create `backend/app/models/club_card.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ClubCardSource
from app.models.mixins import utcnow


class ClubCard(Base):
    __tablename__ = "club_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[ClubCardSource] = mapped_column(Enum(ClubCardSource, name="club_card_source_enum"), nullable=False)
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    player: Mapped["Player"] = relationship(lazy="joined")
```

Note: `lazy="joined"` matches how `UserCard.player` is loaded (confirm by checking `backend/app/models/card.py` if unsure — the point is every `ClubCard` query gets its `.player` eagerly, since `calculate_base_strength` (reused in Task 6) accesses `.player.rating`/`.player.rarity`/`.player.position`/`.player.club`/`.player.country` and nothing here should trigger a sync lazy-load.

- [ ] **Step 3: `Player.next_club_serial_number`**

In `backend/app/models/player.py`, add right after the existing `next_serial_number` column:

```python
    next_club_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
```

- [ ] **Step 4: Register the model**

In `backend/app/models/__init__.py`: `from app.models.club_card import ClubCard`, add `"ClubCard"` to `__all__`.

- [ ] **Step 5: `create_club_card`**

Create `backend/app/services/club_card_service.py`:

```python
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club_card import ClubCard
from app.models.enums import ClubCardSource
from app.models.player import Player


async def create_club_card(
    db: AsyncSession, club_id: int, player_id: int, source: ClubCardSource, source_ref_id: Optional[int] = None
) -> ClubCard:
    """Mirrors card_creation.create_user_card exactly, but against the
    separate `next_club_serial_number` counter — club packs must never
    affect personal-card serial-number scarcity."""
    player = await db.get(Player, player_id)
    await db.refresh(player, attribute_names=["next_club_serial_number"], with_for_update=True)
    serial_number = player.next_club_serial_number
    player.next_club_serial_number += 1
    db.add(player)

    card = ClubCard(club_id=club_id, player_id=player_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card
```

- [ ] **Step 6: Migration**

Create `backend/alembic/versions/0058_club_cards.py`:

```python
"""ClubCard: club-owned card pool with its own serial-number sequence

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("next_club_serial_number", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "club_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Enum("starter_seed", "club_pack", name="club_card_source_enum"), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_cards_club_id", "club_cards", ["club_id"])
    op.create_index("ix_club_cards_player_id", "club_cards", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_club_cards_player_id", table_name="club_cards")
    op.drop_index("ix_club_cards_club_id", table_name="club_cards")
    op.drop_table("club_cards")
    op.drop_column("players", "next_club_serial_number")
    bind = op.get_bind()
    sa.Enum(name="club_card_source_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 7: Apply, verify, and write a locking test**

```bash
docker compose exec -T backend alembic upgrade head
```

Create `backend/tests/test_club_cards.py`:

```python
from sqlalchemy import select

from app.models.club_card import ClubCard
from app.models.enums import ClubCardSource
from app.services.club_card_service import create_club_card
from tests.factories import create_player


async def test_create_club_card_uses_separate_serial_sequence_from_personal_cards(db_session):
    player = await create_player(db_session)
    assert player.next_serial_number == 1
    assert player.next_club_serial_number == 1

    club_card_1 = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.starter_seed)
    club_card_2 = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.starter_seed)
    await db_session.commit()

    assert club_card_1.serial_number == 1
    assert club_card_2.serial_number == 2
    await db_session.refresh(player)
    assert player.next_serial_number == 1  # untouched — personal-card sequence is independent
    assert player.next_club_serial_number == 3


async def test_create_club_card_persists_with_player_relationship(db_session):
    player = await create_player(db_session)
    card = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.club_pack, source_ref_id=42)
    await db_session.commit()

    result = await db_session.execute(select(ClubCard).where(ClubCard.id == card.id))
    fetched = result.scalar_one()
    assert fetched.player.id == player.id
    assert fetched.source == ClubCardSource.club_pack
    assert fetched.source_ref_id == 42
```

Check `tests/factories.py`'s `create_player` signature before writing this (it's used elsewhere in the suite, e.g. `test_lineups_matches.py`/`test_tasks.py` already call it) — call it exactly as those existing tests do; don't guess its parameters.

Run: `docker compose exec -T backend pytest tests/test_club_cards.py -v` — expect both to pass.

- [ ] **Step 8: Full suite + commit**

```bash
docker compose exec -T backend pytest tests/ -q
git add backend/app/models/enums.py backend/app/models/club_card.py backend/app/models/player.py backend/app/models/__init__.py backend/app/services/club_card_service.py backend/alembic/versions/0058_club_cards.py backend/tests/test_club_cards.py
git commit -m "Add ClubCard model, separate serial numbering, and create_club_card"
```

---

### Task 3: `ClubLineup`/`ClubLineupCard` models

**Files:**
- Create: `backend/app/models/club_lineup.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0059_club_lineup.py`

**Interfaces:**
- Consumes: `ClubCard` (Task 2).
- Produces: `ClubLineup(id, club_id unique, created_at)`, `ClubLineupCard(id, club_lineup_id, club_card_id, slot_code)` — consumed by Task 4 (seeding) and Task 6 (squad editor).

- [ ] **Step 1: Write the models**

Create `backend/app/models/club_lineup.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubLineup(Base):
    __tablename__ = "club_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cards: Mapped[list["ClubLineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")


class ClubLineupCard(Base):
    __tablename__ = "club_lineup_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_lineup_id: Mapped[int] = mapped_column(ForeignKey("club_lineups.id", ondelete="CASCADE"), nullable=False, index=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    lineup: Mapped["ClubLineup"] = relationship(back_populates="cards")
    club_card: Mapped["ClubCard"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("club_lineup_id", "club_card_id", name="uq_club_lineup_card_once"),
        UniqueConstraint("club_lineup_id", "slot_code", name="uq_club_lineup_slot_once"),
    )
```

Note `Club.budget` is unique-per-club via `club_id: unique=True` — every club gets exactly one `ClubLineup`, created eagerly at squad-seed time (Task 4), never lazily get-or-created — this sidesteps the concurrent-first-creation race the personal `Lineup` model needs a partial unique index + SAVEPOINT dance for (see `lineup_service._get_or_create_lineup`'s comment) — club creation is already fully serialized by Task 4's own locking, so there's no equivalent race to guard against here.

- [ ] **Step 2: Register the models**

In `backend/app/models/__init__.py`: `from app.models.club_lineup import ClubLineup, ClubLineupCard`, add both to `__all__`.

- [ ] **Step 3: Migration**

Create `backend/alembic/versions/0059_club_lineup.py`:

```python
"""ClubLineup/ClubLineupCard: fixed 4-3-3 squad for a club

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_lineups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "club_lineup_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_lineup_id", sa.Integer(), sa.ForeignKey("club_lineups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_code", sa.String(length=16), nullable=False),
    )
    op.create_index("ix_club_lineup_cards_club_lineup_id", "club_lineup_cards", ["club_lineup_id"])
    op.create_index("ix_club_lineup_cards_club_card_id", "club_lineup_cards", ["club_card_id"])
    op.create_unique_constraint("uq_club_lineup_card_once", "club_lineup_cards", ["club_lineup_id", "club_card_id"])
    op.create_unique_constraint("uq_club_lineup_slot_once", "club_lineup_cards", ["club_lineup_id", "slot_code"])


def downgrade() -> None:
    op.drop_table("club_lineup_cards")
    op.drop_table("club_lineups")
```

- [ ] **Step 4: Apply, verify, sanity check, commit**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "\d club_lineups" -c "\d club_lineup_cards"
docker compose exec -T backend python -c "from app.main import app; print('ok')"
git add backend/app/models/club_lineup.py backend/app/models/__init__.py backend/alembic/versions/0059_club_lineup.py
git commit -m "Add ClubLineup/ClubLineupCard models"
```

---

### Task 4: Starting squad auto-seed, hooked into club creation

**Files:**
- Create: `backend/app/services/club_squad_service.py`
- Modify: `backend/app/services/club_service.py`
- Modify: `backend/tests/test_clubs.py`

**Interfaces:**
- Consumes: `create_club_card` (Task 2), `ClubLineup`/`ClubLineupCard` (Task 3), `lineup_service.FORMATION_SLOTS`/`CATEGORY_POSITIONS` (existing).
- Produces: `seed_starting_squad(db, club_id) -> None` — called from `club_service.create_club` right after the club row + captain membership are created, before that function's final commit.

- [ ] **Step 1: Write the seeding function**

Create `backend/app/services/club_squad_service.py`:

```python
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubCardSource, Position
from app.models.player import Player
from app.services.club_card_service import create_club_card
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS

# Bench categories seeded alongside the 11 starters — one extra card per
# category, giving every fresh club a small reserve pool from day one (per
# the design spec's "so a club is never caught with nobody to substitute").
BENCH_CATEGORIES = ["GK", "DEF", "MID", "FWD"]


async def _pick_weakest_active_player_id(db: AsyncSession, positions: list[Position], excluded_player_ids: set[int]) -> int:
    query = (
        select(Player.id, Player.rating)
        .where(Player.is_active.is_(True), Player.position.in_(positions))
        .order_by(Player.rating.asc())
        .limit(20)
    )
    if excluded_player_ids:
        query = query.where(Player.id.notin_(excluded_player_ids))
    rows = (await db.execute(query)).all()
    if not rows:
        # Fall back to allowing repeats if the active player pool for this
        # position is smaller than the number of slots needing it (e.g. a
        # freshly-seeded dev database) — a duplicate weak player beats no
        # player at all for a brand-new club's starting squad.
        rows = (
            await db.execute(
                select(Player.id, Player.rating)
                .where(Player.is_active.is_(True), Player.position.in_(positions))
                .order_by(Player.rating.asc())
                .limit(20)
            )
        ).all()
    lowest_rating = rows[0][1]
    lowest_rated_ids = [player_id for player_id, rating in rows if rating == lowest_rating]
    return random.choice(lowest_rated_ids)


async def seed_starting_squad(db: AsyncSession, club_id: int) -> None:
    """Mints the club's first 15 ClubCards (11 starters, placed directly
    into a fresh ClubLineup, plus 4 bench cards — one per category) using
    the lowest-rated active Player available per slot, random among ties.
    Deliberately weak by design — the club has to earn its way up via
    packs. Called once, synchronously, from club_service.create_club."""
    lineup = ClubLineup(club_id=club_id)
    db.add(lineup)
    await db.flush()

    used_player_ids: set[int] = set()

    for slot in FORMATION_SLOTS:
        positions = list(CATEGORY_POSITIONS[slot.category])
        # Position enum members compare by value against Player.position's
        # own enum column — no str() conversion needed, matches how
        # lineup_service itself queries by these same enum members.
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        club_card = await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=club_card.id, slot_code=slot.code))

    for category in BENCH_CATEGORIES:
        positions = list(CATEGORY_POSITIONS[category])
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        # No ClubLineupCard row for bench cards — per this plan's "bench =
        # any club card not currently in the lineup" simplification, these
        # are just extra ClubCard rows the squad editor's picker surfaces.

    await db.flush()
```

Note: `list(CATEGORY_POSITIONS[slot.category])` — `CATEGORY_POSITIONS` in `lineup_service.py` maps to a `set[Position]`; `Player.position.in_(positions)` needs a list/tuple for SQLAlchemy's `in_()`, hence the `list(...)` conversion.

- [ ] **Step 2: Hook into `create_club`**

In `backend/app/services/club_service.py`, add the import `from app.services.club_squad_service import seed_starting_squad`, then in `create_club`, right after the existing:

```python
    db.add(ClubMember(club_id=club.id, user_id=locked_user.id, role=ClubRole.captain))
    await db.flush()
```

add:

```python
    await seed_starting_squad(db, club.id)
```

(before the function's final `await db.commit()`).

- [ ] **Step 3: Write a test verifying the hook**

Append to `backend/tests/test_clubs.py`:

```python
async def test_create_club_seeds_a_complete_starting_squad(client, db_session, bot_token):
    from app.models.club_card import ClubCard
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    from sqlalchemy import func, select

    await _register_only(client, bot_token, 820200)
    headers = telegram_headers(820200, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": "Клуб со стартовым составом", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    club_id = resp.json()["id"]

    total_cards = (
        await db_session.execute(select(func.count(ClubCard.id)).where(ClubCard.club_id == club_id))
    ).scalar_one()
    assert total_cards == 15  # 11 starters + 4 bench

    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one()
    lineup_card_count = (
        await db_session.execute(select(func.count(ClubLineupCard.id)).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalar_one()
    assert lineup_card_count == 11

    slot_codes = (
        await db_session.execute(select(ClubLineupCard.slot_code).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalars().all()
    assert len(set(slot_codes)) == 11  # every formation slot filled exactly once
```

Uses the existing `_register_only`/`telegram_headers` helpers already present in this file (from Phase 1's Task 5).

- [ ] **Step 4: Run, iterate, full suite, commit**

```bash
docker compose exec -T backend pytest tests/test_clubs.py -v
docker compose exec -T backend pytest tests/ -q
git add backend/app/services/club_squad_service.py backend/app/services/club_service.py backend/tests/test_clubs.py
git commit -m "Auto-seed a starting squad (11 starters + 4 bench) at club creation"
```

If this test is slow or flaky in a dev DB with a small `players` table (fewer than a handful of active players per position), that's a pre-existing dev-seed-data limitation, not a bug in this code — note it in the commit if encountered, don't work around it by loosening the plan's own selection logic.

---

### Task 5: Club daily reward claim

**Files:**
- Create: `backend/app/models/club_daily_claim.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0060_club_daily_claim.py`
- Create: `backend/app/services/club_budget_service.py`
- Modify: `backend/app/services/club_service.py`
- Modify: `backend/app/routers/clubs.py`
- Modify: `backend/tests/test_clubs.py`

**Interfaces:**
- Consumes: `_lock_club`/`_require_membership` (Phase 1, `club_service.py`), `ClubBudgetTransaction`/`ClubBudgetTransactionType` (Task 1), `local_today()` (existing `core/timeutil.py`).
- Produces: `credit_club_budget(db, club, amount, tx_type, description="", related_object_type=None, related_object_id=None) -> ClubBudgetTransaction` and `debit_club_budget(...)` (same signature, raises if insufficient) in `club_budget_service.py` — reused by Task 8's pack-opening debit; `claim_daily_reward(db, user) -> ClubDetailOut` in `club_service.py`; route `POST /clubs/me/daily-claim`.

- [ ] **Step 1: `ClubDailyClaim` model**

Create `backend/app/models/club_daily_claim.py`:

```python
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClubDailyClaim(Base):
    __tablename__ = "club_daily_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("club_id", "user_id", "claim_date", name="uq_club_daily_claim_once_per_day"),)
```

Register in `backend/app/models/__init__.py` (`from app.models.club_daily_claim import ClubDailyClaim`, add to `__all__`).

- [ ] **Step 2: Migration**

Create `backend/alembic/versions/0060_club_daily_claim.py`:

```python
"""ClubDailyClaim: one club-budget daily reward per member per day

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_daily_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_date", sa.Date(), nullable=False),
    )
    op.create_index("ix_club_daily_claims_club_id", "club_daily_claims", ["club_id"])
    op.create_index("ix_club_daily_claims_user_id", "club_daily_claims", ["user_id"])
    op.create_unique_constraint(
        "uq_club_daily_claim_once_per_day", "club_daily_claims", ["club_id", "user_id", "claim_date"]
    )


def downgrade() -> None:
    op.drop_table("club_daily_claims")
```

Apply: `docker compose exec -T backend alembic upgrade head`.

- [ ] **Step 3: Budget credit/debit helpers**

Create `backend/app/services/club_budget_service.py`:

```python
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientBalanceError
from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.enums import ClubBudgetTransactionType


async def credit_club_budget(
    db: AsyncSession,
    club: Club,
    amount: int,
    tx_type: ClubBudgetTransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> ClubBudgetTransaction:
    if amount < 0:
        raise ValueError("credit_club_budget amount must be >= 0")
    balance_before = club.budget
    club.budget = balance_before + amount
    tx = ClubBudgetTransaction(
        club_id=club.id, amount=amount, balance_before=balance_before, balance_after=club.budget,
        type=tx_type, description=description, related_object_type=related_object_type, related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(club)
    return tx


async def debit_club_budget(
    db: AsyncSession,
    club: Club,
    amount: int,
    tx_type: ClubBudgetTransactionType,
    description: str = "",
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> ClubBudgetTransaction:
    if amount < 0:
        raise ValueError("debit_club_budget amount must be >= 0")
    if club.budget < amount:
        raise InsufficientBalanceError("Недостаточно средств в бюджете клуба", details={"budget": club.budget, "required": amount})
    balance_before = club.budget
    club.budget = balance_before - amount
    tx = ClubBudgetTransaction(
        club_id=club.id, amount=-amount, balance_before=balance_before, balance_after=club.budget,
        type=tx_type, description=description, related_object_type=related_object_type, related_object_id=related_object_id,
    )
    db.add(tx)
    db.add(club)
    return tx
```

This is a deliberate, near-verbatim mirror of `wallet_service.credit_coins`/`debit_coins` — same shape, different ledger table, per the Global Constraints' row-locking requirement (callers must lock the `Club` row before calling either of these, exactly like personal-wallet callers lock the `User` row first).

- [ ] **Step 4: `claim_daily_reward` service function**

In `backend/app/services/club_service.py`, add imports: `from datetime import date` is not needed directly (use `local_today()`); add `from app.core.timeutil import local_today`, `from app.models.club_daily_claim import ClubDailyClaim`, `from app.models.enums import ClubBudgetTransactionType`, `from app.services.club_budget_service import credit_club_budget`. Then add:

```python
async def claim_daily_reward(db: AsyncSession, user: User) -> ClubDetailOut:
    membership = await _require_membership(db, user.id)
    today = local_today()

    existing = await db.execute(
        select(ClubDailyClaim).where(
            ClubDailyClaim.club_id == membership.club_id, ClubDailyClaim.user_id == user.id, ClubDailyClaim.claim_date == today,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Сегодня награда уже получена")

    club = await _lock_club(db, membership.club_id)
    config = await get_config(db)
    await credit_club_budget(
        db, club, config.club_daily_reward_coins, ClubBudgetTransactionType.daily_claim,
        f"Ежедневная награда от {user.username or user.first_name or f'#{user.id}'}",
    )
    db.add(ClubDailyClaim(club_id=club.id, user_id=user.id, claim_date=today))
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=user.id)
```

- [ ] **Step 5: Router**

In `backend/app/routers/clubs.py`, add:

```python
@router.post("/me/daily-claim", response_model=ClubDetailOut)
async def claim_daily_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.claim_daily_reward(db, user)
```

- [ ] **Step 6: Tests**

Append to `backend/tests/test_clubs.py`:

```python
async def test_claim_daily_reward_credits_budget_once_per_day(client, db_session, bot_token):
    club, headers = await _create_club(client, bot_token, 820201, "Клуб с наградой")
    resp = await client.post("/api/v1/clubs/me/daily-claim", headers=headers)
    assert resp.status_code == 200

    from app.models.club import Club
    updated_club = await db_session.get(Club, club["id"])
    await db_session.refresh(updated_club)
    assert updated_club.budget == 200  # GameConfig.club_daily_reward_coins default

    second_attempt = await client.post("/api/v1/clubs/me/daily-claim", headers=headers)
    assert second_attempt.status_code == 409
```

- [ ] **Step 7: Run, iterate, full suite, commit**

```bash
docker compose exec -T backend pytest tests/test_clubs.py -v
docker compose exec -T backend pytest tests/ -q
git add backend/app/models/club_daily_claim.py backend/app/models/__init__.py backend/alembic/versions/0060_club_daily_claim.py backend/app/services/club_budget_service.py backend/app/services/club_service.py backend/app/routers/clubs.py backend/tests/test_clubs.py
git commit -m "Add club daily reward claim and the club budget credit/debit helpers"
```

---

### Task 6: Squad editor — view and set the club lineup

**Files:**
- Create: `backend/app/schemas/club_squad.py`
- Modify: `backend/app/services/club_squad_service.py`
- Modify: `backend/app/routers/clubs.py`
- Create: `backend/tests/test_club_squad.py`

**Interfaces:**
- Consumes: `FORMATION_SLOTS`/`CATEGORY_POSITIONS`/`calculate_base_strength` (existing `lineup_service.py`), `ClubCard`/`ClubLineup`/`ClubLineupCard` (Tasks 2-3), `_require_membership`/`_require_manager`/`_lock_club` (Phase 1).
- Produces: `ClubCardOut`, `ClubLineupSlotOut`, `ClubLineupOut`, `ClubLineupSetRequest` schemas; `get_club_lineup(db, user) -> ClubLineupOut`, `set_club_lineup(db, user, payload) -> ClubLineupOut`, `list_club_cards(db, user) -> list[ClubCardOut]` service functions; routes `GET /clubs/me/lineup`, `PUT /clubs/me/lineup`, `GET /clubs/me/cards`.

- [ ] **Step 1: Schemas**

Create `backend/app/schemas/club_squad.py`:

```python
from datetime import datetime

from pydantic import BaseModel

from app.schemas.player import PlayerOut


class ClubCardOut(BaseModel):
    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    is_in_lineup: bool


class ClubLineupSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    card: ClubCardOut | None = None


class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    slots: list[ClubLineupSlotOut]


class ClubLineupSlotIn(BaseModel):
    slot_code: str
    club_card_id: int


class ClubLineupSetRequest(BaseModel):
    slots: list[ClubLineupSlotIn]
```

`PlayerOut` is the existing schema already used by `UserCardOut` (`backend/app/schemas/player.py`) — reused as-is, `ClubCard`'s `.player` is a plain `Player` row like any other.

- [ ] **Step 2: Service functions**

Append to `backend/app/services/club_squad_service.py`. Add these imports to the file's existing import block: `from sqlalchemy.orm import joinedload`; `from app.core.exceptions import ConflictError`; `from app.models.club_card import ClubCard`; `from app.models.user import User`; `from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest, ClubLineupSlotOut`; `from app.schemas.player import PlayerOut`; `from app.services.lineup_service import CATEGORY_POSITIONS, SLOTS_BY_CODE, calculate_base_strength` (this file already imports `CATEGORY_POSITIONS`/`FORMATION_SLOTS` from Task 4 — just add `SLOTS_BY_CODE`/`calculate_base_strength` to that existing import line rather than duplicating it).

```python
async def _get_or_none_lineup(db: AsyncSession, club_id: int) -> ClubLineup | None:
    result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card))
    )
    return result.unique().scalar_one_or_none()


def _club_card_to_out(card: ClubCard, in_lineup_ids: set[int]) -> ClubCardOut:
    return ClubCardOut(
        id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
        acquired_at=card.acquired_at, is_in_lineup=card.id in in_lineup_ids,
    )


async def list_club_cards(db: AsyncSession, user: User) -> list[ClubCardOut]:
    membership = await _require_membership(db, user.id)
    cards = (await db.execute(select(ClubCard).where(ClubCard.club_id == membership.club_id).order_by(ClubCard.acquired_at))).scalars().all()
    lineup = await _get_or_none_lineup(db, membership.club_id)
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()
    return [_club_card_to_out(c, in_lineup_ids) for c in cards]


async def _lineup_to_out(db: AsyncSession, club_id: int) -> ClubLineupOut:
    lineup = await _get_or_none_lineup(db, club_id)
    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards} if lineup else {}
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()

    slots = []
    cards_with_slots = []
    for slot in FORMATION_SLOTS:
        card = by_slot.get(slot.code)
        slots.append(
            ClubLineupSlotOut(
                slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
                card=_club_card_to_out(card, in_lineup_ids) if card else None,
            )
        )
        if card:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(FORMATION_SLOTS)
    team_strength = calculate_base_strength(cards_with_slots) if is_complete else None
    return ClubLineupOut(is_complete=is_complete, team_strength=team_strength, slots=slots)


async def get_club_lineup(db: AsyncSession, user: User) -> ClubLineupOut:
    membership = await _require_membership(db, user.id)
    return await _lineup_to_out(db, membership.club_id)


async def set_club_lineup(db: AsyncSession, user: User, payload: ClubLineupSetRequest) -> ClubLineupOut:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    slot_codes = [s.slot_code for s in payload.slots]
    if len(slot_codes) != len(set(slot_codes)):
        raise ConflictError("Один слот не может использоваться дважды")
    if any(code not in SLOTS_BY_CODE for code in slot_codes):
        raise ConflictError("Неизвестный слот состава")

    card_ids = [s.club_card_id for s in payload.slots]
    if len(card_ids) != len(set(card_ids)):
        raise ConflictError("Одна карточка не может занимать два слота")

    club_cards = (await db.execute(select(ClubCard).where(ClubCard.id.in_(card_ids), ClubCard.club_id == club_id))).scalars().all()
    if len(club_cards) != len(card_ids):
        raise ConflictError("Карточка не принадлежит этому клубу")
    cards_by_id = {c.id: c for c in club_cards}

    # No duplicate-player check across slots, mirroring lineup_service.set_lineup's
    # same rule for personal squads: one player instance per slot.
    player_ids = [cards_by_id[cid].player_id for cid in card_ids]
    if len(player_ids) != len(set(player_ids)):
        raise ConflictError("Один футболист не может занимать две позиции")

    for slot_in in payload.slots:
        slot = SLOTS_BY_CODE[slot_in.slot_code]
        card = cards_by_id[slot_in.club_card_id]
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(f"Игрок на позиции {card.player.position} не подходит для слота {slot.code}")

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    for lc in list(lineup.cards):
        await db.delete(lc)
    await db.flush()
    for slot_in in payload.slots:
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=slot_in.club_card_id, slot_code=slot_in.slot_code))
    await db.commit()
    return await _lineup_to_out(db, club_id)
```

Note: `get_club_lineup`/`set_club_lineup` need `_require_membership`/`_require_manager` from `club_service.py` — add `from app.services.club_service import _require_manager, _require_membership` to `club_squad_service.py`'s imports (alongside the ones listed in Step 2 above). This is a legitimate cross-service import within the same feature (both files live under `app/services/`, matching how other services in this codebase already import helpers from each other, e.g. `task_service.py` importing from `pack_service.py`).

- [ ] **Step 3: Router**

In `backend/app/routers/clubs.py`, add imports `from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest` and `from app.services import club_squad_service`, then:

```python
@router.get("/me/lineup", response_model=ClubLineupOut)
async def get_club_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.get_club_lineup(db, user)


@router.put("/me/lineup", response_model=ClubLineupOut)
async def set_club_lineup(payload: ClubLineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.set_club_lineup(db, user, payload)


@router.get("/me/cards", response_model=list[ClubCardOut])
async def list_club_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.list_club_cards(db, user)
```

- [ ] **Step 4: Tests**

Create `backend/tests/test_club_squad.py`:

```python
from app.models.club_lineup import ClubLineup, ClubLineupCard
from sqlalchemy import select

from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def test_get_club_lineup_is_complete_after_creation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820300, "Клуб с готовым составом")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] is not None
    assert len(body["slots"]) == 11
    assert all(s["card"] is not None for s in body["slots"])


async def test_list_club_cards_includes_bench(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820301, "Клуб со скамейкой")
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 15
    assert sum(1 for c in cards if not c["is_in_lineup"]) == 4


CATEGORY_POSITIONS_FOR_TEST = {
    "GK": {"GK"}, "DEF": {"LB", "CB", "RB"}, "MID": {"CDM", "CM", "CAM", "LM", "RM"}, "FWD": {"LW", "ST", "RW"},
}


def _category_for_position(position: str) -> str:
    return next(category for category, positions in CATEGORY_POSITIONS_FOR_TEST.items() if position in positions)


async def test_set_club_lineup_swaps_a_bench_card_into_a_slot(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820302, "Клуб с заменой")
    cards = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    bench_card = next(c for c in cards if not c["is_in_lineup"])
    bench_category = _category_for_position(bench_card["player"]["position"])
    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()

    # Every club is seeded with exactly one bench card per category and one
    # starter per formation slot within that same category, so there is
    # always at least one legal target slot — same category, any slot.
    matching_slot = next(s for s in lineup["slots"] if s["category"] == bench_category)
    slots_payload = [
        {"slot_code": s["slot_code"], "club_card_id": bench_card["id"] if s["slot_code"] == matching_slot["slot_code"] else s["card"]["id"]}
        for s in lineup["slots"]
    ]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=headers, json={"slots": slots_payload})
    assert resp.status_code == 200
    assert resp.json()["is_complete"] is True


async def test_non_manager_cannot_set_lineup(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820303, "Клуб без прав")
    await _register_only(client, bot_token, 820304)
    member_headers = telegram_headers(820304, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=member_headers)).json()
    slots_payload = [{"slot_code": s["slot_code"], "club_card_id": s["card"]["id"]} for s in lineup["slots"]]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=member_headers, json={"slots": slots_payload})
    assert resp.status_code == 403
```

- [ ] **Step 5: Run, iterate, full suite, commit**

```bash
docker compose exec -T backend pytest tests/test_club_squad.py -v
docker compose exec -T backend pytest tests/ -q
git add backend/app/schemas/club_squad.py backend/app/services/club_squad_service.py backend/app/routers/clubs.py backend/tests/test_club_squad.py
git commit -m "Add club squad editor: view/set lineup, list club cards"
```

---

### Task 7: `ClubPack` model + admin CRUD

**Files:**
- Create: `backend/app/models/club_pack.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/club_pack.py`
- Create: `backend/alembic/versions/0061_club_packs.py`
- Create: `backend/app/routers/admin_club_packs.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_admin_club_packs.py`

**Interfaces:**
- Produces: `ClubPack(id, slug, name, description, price, card_count, guaranteed_min_rarity, image_path, is_active, sort_order)`, `ClubPackRarityProbability(club_pack_id, rarity, probability)`, admin CRUD at `/admin/club-packs` — consumed by Task 8 (opening flow) and later frontend tasks.

- [ ] **Step 1: Models**

Create `backend/app/models/club_pack.py`:

```python
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class ClubPack(TimestampMixin, Base):
    __tablename__ = "club_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    card_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    guaranteed_min_rarity: Mapped[Optional[Rarity]] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rarity_probabilities: Mapped[list["ClubPackRarityProbability"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )


class ClubPackRarityProbability(Base):
    __tablename__ = "club_pack_rarity_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_pack_id: Mapped[int] = mapped_column(ForeignKey("club_packs.id", ondelete="CASCADE"), nullable=False)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    probability: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)

    pack: Mapped["ClubPack"] = relationship(back_populates="rarity_probabilities")

    __table_args__ = (UniqueConstraint("club_pack_id", "rarity", name="uq_club_pack_rarity_once"),)
```

Register both in `backend/app/models/__init__.py`.

- [ ] **Step 2: Schemas**

Create `backend/app/schemas/club_pack.py`:

```python
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity


class ClubPackRarityProbabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rarity: Rarity
    probability: float


class ClubPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    description: str
    price: int
    card_count: int
    guaranteed_min_rarity: Optional[Rarity]
    image_path: Optional[str]
    is_active: bool
    sort_order: int
    rarity_probabilities: list[ClubPackRarityProbabilityOut]


class ClubPackRarityProbabilityIn(BaseModel):
    rarity: Rarity
    probability: float = Field(ge=0, le=1)


class ClubPackCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    price: int = Field(ge=0)
    card_count: int = Field(default=3, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: list[ClubPackRarityProbabilityIn]
    is_active: bool = True
    sort_order: int = 0


class ClubPackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    card_count: Optional[int] = Field(default=None, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: Optional[list[ClubPackRarityProbabilityIn]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
```

- [ ] **Step 3: Migration**

Create `backend/alembic/versions/0061_club_packs.py`:

```python
"""ClubPack + ClubPackRarityProbability: club-only pack list

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_packs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("guaranteed_min_rarity", sa.Enum("common", "rare", "epic", "legendary", name="rarity_enum"), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_pack_rarity_probabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_pack_id", sa.Integer(), sa.ForeignKey("club_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", sa.Enum("common", "rare", "epic", "legendary", name="rarity_enum"), nullable=False),
        sa.Column("probability", sa.Numeric(6, 4), nullable=False),
    )
    op.create_unique_constraint(
        "uq_club_pack_rarity_once", "club_pack_rarity_probabilities", ["club_pack_id", "rarity"]
    )


def downgrade() -> None:
    op.drop_table("club_pack_rarity_probabilities")
    op.drop_table("club_packs")
```

Note: `rarity_enum` already exists (created by `0001_initial.py`) — this migration reuses it via plain `sa.Enum(..., name="rarity_enum")` without re-creating the type (SQLAlchemy/Alembic only emits `CREATE TYPE` for an enum name it hasn't seen in this same migration file; since `rarity_enum` already exists in the database, adding a column typed with it is safe and standard — this exact reuse pattern is already used throughout this codebase's models, e.g. `Player.rarity`).

Apply: `docker compose exec -T backend alembic upgrade head`, verify via `\d club_packs` / `\d club_pack_rarity_probabilities`.

- [ ] **Step 4: Admin CRUD router**

Create `backend/app/routers/admin_club_packs.py` (mirror `admin_packs.py`'s exact shape, minus image-upload's slug templating differences — reuse the identical image helpers):

```python
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.user import User
from app.schemas.club_pack import ClubPackCreate, ClubPackOut, ClubPackUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_pack_image, save_pack_image

router = APIRouter(prefix="/admin/club-packs", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_pack_or_404(db: AsyncSession, pack_id: int) -> ClubPack:
    result = await db.execute(
        select(ClubPack).where(ClubPack.id == pack_id).options(joinedload(ClubPack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if pack is None:
        raise NotFoundError("Club pack not found")
    return pack


def _validate_probabilities(rarity_probabilities: list) -> None:
    total = sum(p.probability for p in rarity_probabilities)
    if not (0.98 <= total <= 1.02):
        raise ConflictError(f"Вероятности должны суммироваться к 1.0 (сейчас {total:.4f})")


@router.get("", response_model=list[ClubPackOut])
async def list_all_club_packs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClubPack).options(joinedload(ClubPack.rarity_probabilities)).order_by(ClubPack.sort_order))
    return result.unique().scalars().all()


@router.post("", response_model=ClubPackOut)
async def create_club_pack(payload: ClubPackCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    _validate_probabilities(payload.rarity_probabilities)
    data = payload.model_dump(exclude={"rarity_probabilities"})
    pack = ClubPack(**data)
    db.add(pack)
    await db.flush()
    for p in payload.rarity_probabilities:
        db.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    await log_action(db, admin.id, "create_club_pack", "club_pack", pack.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack.id)


@router.put("/{pack_id}", response_model=ClubPackOut)
async def update_club_pack(pack_id: int, payload: ClubPackUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_value = ClubPackOut.model_validate(pack).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"rarity_probabilities"})
    for key, value in updates.items():
        setattr(pack, key, value)
    if payload.rarity_probabilities is not None:
        _validate_probabilities(payload.rarity_probabilities)
        for existing in list(pack.rarity_probabilities):
            await db.delete(existing)
        await db.flush()
        for p in payload.rarity_probabilities:
            db.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    db.add(pack)
    await log_action(db, admin.id, "update_club_pack", "club_pack", pack_id, old_value=old_value, new_value=payload.model_dump(mode="json", exclude_unset=True), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack_id)


@router.post("/{pack_id}/image", response_model=ClubPackOut)
async def upload_club_pack_image(pack_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_image = pack.image_path
    pack.image_path = await save_pack_image(file, f"club-{pack.slug}")
    db.add(pack)
    await db.commit()
    delete_pack_image(old_image)
    return await _get_pack_or_404(db, pack_id)


@router.post("/{pack_id}/toggle-active", response_model=ClubPackOut)
async def toggle_club_pack_active(pack_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    pack.is_active = not pack.is_active
    db.add(pack)
    await log_action(db, admin.id, "toggle_club_pack_active", "club_pack", pack_id, new_value={"is_active": pack.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack_id)


@router.delete("/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_club_pack(pack_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    await log_action(db, admin.id, "delete_club_pack", "club_pack", pack_id, old_value=ClubPackOut.model_validate(pack).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    delete_pack_image(pack.image_path)
    await db.delete(pack)
    await db.commit()
```

The `f"club-{pack.slug}"` prefix passed to `save_pack_image` (which builds the stored filename from this string) avoids the shared-`PACKS_DIR` filename collision risk between a `ClubPack` and a personal `Pack` that happen to share the same slug — cheap, sufficient namespacing.

- [ ] **Step 5: Register the router**

In `backend/app/main.py`: add `admin_club_packs` to the router import block (alphabetically, near `admin_card_upgrades`) and `app.include_router(admin_club_packs.router, prefix=API_PREFIX)` near the other `admin_*` routers.

- [ ] **Step 6: Tests**

Create `backend/tests/test_admin_club_packs.py` (mirror the shape of whatever existing `test_admin_packs.py`-equivalent test file covers personal packs, if one exists — check `backend/tests/` for it first and follow its exact fixture/assertion style; if none exists, use this codebase's other admin-CRUD test files, e.g. `test_leagues.py`'s admin section, as the style precedent):

```python
from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_club_pack_requires_probabilities_summing_to_one(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-basic", "name": "Клубный базовый", "price": 500, "card_count": 3,
            "rarity_probabilities": [{"rarity": "common", "probability": 0.5}],
        },
    )
    assert resp.status_code == 409


async def test_create_and_update_club_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-premium", "name": "Клубный премиум", "price": 1000, "card_count": 3,
            "rarity_probabilities": [
                {"rarity": "common", "probability": 0.6}, {"rarity": "rare", "probability": 0.3}, {"rarity": "epic", "probability": 0.1},
            ],
        },
    )
    assert create_resp.status_code == 200
    pack_id = create_resp.json()["id"]
    assert len(create_resp.json()["rarity_probabilities"]) == 3

    update_resp = await client.put(f"/api/v1/admin/club-packs/{pack_id}", headers=auth, json={"price": 1500})
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 1500

    toggle_resp = await client.post(f"/api/v1/admin/club-packs/{pack_id}/toggle-active", headers=auth)
    assert toggle_resp.json()["is_active"] is False

    list_resp = await client.get("/api/v1/admin/club-packs", headers=auth)
    assert any(p["id"] == pack_id for p in list_resp.json())

    delete_resp = await client.delete(f"/api/v1/admin/club-packs/{pack_id}", headers=auth)
    assert delete_resp.status_code == 204
```

- [ ] **Step 7: Run, iterate, full suite, commit**

```bash
docker compose exec -T backend pytest tests/test_admin_club_packs.py -v
docker compose exec -T backend pytest tests/ -q
git add backend/app/models/club_pack.py backend/app/models/__init__.py backend/app/schemas/club_pack.py backend/alembic/versions/0061_club_packs.py backend/app/routers/admin_club_packs.py backend/app/main.py backend/tests/test_admin_club_packs.py
git commit -m "Add ClubPack model, schemas, migration, and admin CRUD"
```

---

### Task 8: Club pack opening

**Files:**
- Create: `backend/app/models/club_pack_opening.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0062_club_pack_openings.py`
- Create: `backend/app/schemas/club_pack_open.py`
- Create: `backend/app/services/club_pack_service.py`
- Modify: `backend/app/routers/clubs.py`
- Create: `backend/tests/test_club_packs.py`

**Interfaces:**
- Consumes: `ClubPack` (Task 7), `create_club_card` (Task 2), `debit_club_budget` (Task 5), `_lock_club`/`_require_manager`/`_require_membership` (Phase 1), `pack_service.roll_rarities`/`pick_random_player` (existing, reused as-is).
- Produces: `open_club_pack(db, user, club_pack_id, idempotency_key) -> ClubPackOpenResult`; route `POST /clubs/me/packs/{club_pack_id}/open`; route `GET /clubs/packs` (browse, all members).

- [ ] **Step 1: `ClubPackOpening`/`ClubPackOpeningCard` models**

Create `backend/app/models/club_pack_opening.py`:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubPackOpening(Base):
    __tablename__ = "club_pack_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    club_pack_id: Mapped[int] = mapped_column(ForeignKey("club_packs.id"), nullable=False)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    price_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cards: Mapped[list["ClubPackOpeningCard"]] = relationship(back_populates="opening", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("club_id", "idempotency_key", name="uq_club_pack_opening_idempotency"),)


class ClubPackOpeningCard(Base):
    __tablename__ = "club_pack_opening_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(ForeignKey("club_pack_openings.id", ondelete="CASCADE"), nullable=False, index=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False)
    is_new_player: Mapped[bool] = mapped_column(Boolean, nullable=False)

    opening: Mapped["ClubPackOpening"] = relationship(back_populates="cards")
```

Register both in `backend/app/models/__init__.py`.

- [ ] **Step 2: Migration**

Create `backend/alembic/versions/0062_club_pack_openings.py`:

```python
"""ClubPackOpening/ClubPackOpeningCard: club pack purchase history

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_pack_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_pack_id", sa.Integer(), sa.ForeignKey("club_packs.id"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_pack_openings_club_id", "club_pack_openings", ["club_id"])
    op.create_unique_constraint("uq_club_pack_opening_idempotency", "club_pack_openings", ["club_id", "idempotency_key"])

    op.create_table(
        "club_pack_opening_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opening_id", sa.Integer(), sa.ForeignKey("club_pack_openings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_player", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_club_pack_opening_cards_opening_id", "club_pack_opening_cards", ["opening_id"])


def downgrade() -> None:
    op.drop_table("club_pack_opening_cards")
    op.drop_table("club_pack_openings")
```

Apply: `docker compose exec -T backend alembic upgrade head`.

- [ ] **Step 3: Schemas**

Create `backend/app/schemas/club_pack_open.py`:

```python
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut
from pydantic import BaseModel


class OpenedClubCardOut(BaseModel):
    card: ClubCardOut
    is_new: bool


class ClubPackOpenResult(BaseModel):
    opening_id: int
    pack: ClubPackOut
    cards: list[OpenedClubCardOut]
    new_budget: int


class OpenClubPackRequest(BaseModel):
    idempotency_key: str | None = None
```

- [ ] **Step 4: `open_club_pack` service function**

Create `backend/app/services/club_pack_service.py`:

```python
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.enums import ClubBudgetTransactionType, ClubCardSource
from app.models.user import User
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_pack_open import ClubPackOpenResult, OpenedClubCardOut
from app.schemas.club_squad import ClubCardOut
from app.services.club_card_service import create_club_card
from app.services.club_budget_service import debit_club_budget
from app.services.club_service import _lock_club, _require_manager, _require_membership
from app.services.pack_service import pick_random_player, roll_rarities


async def list_club_packs(db: AsyncSession) -> list[ClubPackOut]:
    result = await db.execute(
        select(ClubPack).where(ClubPack.is_active.is_(True)).options(joinedload(ClubPack.rarity_probabilities)).order_by(ClubPack.sort_order)
    )
    return result.unique().scalars().all()


async def _get_result_for_existing_opening(db: AsyncSession, opening: ClubPackOpening) -> ClubPackOpenResult:
    pack = await db.get(ClubPack, opening.club_pack_id, options=[joinedload(ClubPack.rarity_probabilities)])
    cards_result = await db.execute(select(ClubPackOpeningCard).where(ClubPackOpeningCard.opening_id == opening.id))
    opening_cards = cards_result.scalars().all()
    club_cards = {c.id: c for c in (await db.execute(select(ClubCard).where(ClubCard.id.in_([oc.club_card_id for oc in opening_cards])))).scalars().all()}
    club_row = await db.get(Club, opening.club_id)
    return ClubPackOpenResult(
        opening_id=opening.id, pack=ClubPackOut.model_validate(pack),
        cards=[OpenedClubCardOut(card=ClubCardOut(id=cc.id, serial_number=cc.serial_number, player=cc.player, acquired_at=cc.acquired_at, is_in_lineup=False), is_new=oc.is_new_player) for oc, cc in ((oc, club_cards[oc.club_card_id]) for oc in opening_cards)],
        new_budget=club_row.budget,
    )


async def open_club_pack(db: AsyncSession, user: User, club_pack_id: int, idempotency_key: Optional[str]) -> ClubPackOpenResult:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)

    if idempotency_key:
        existing = await db.execute(
            select(ClubPackOpening).where(ClubPackOpening.club_id == membership.club_id, ClubPackOpening.idempotency_key == idempotency_key)
        )
        existing_opening = existing.scalar_one_or_none()
        if existing_opening is not None:
            return await _get_result_for_existing_opening(db, existing_opening)

    pack = await db.get(ClubPack, club_pack_id, options=[joinedload(ClubPack.rarity_probabilities)])
    if pack is None or not pack.is_active:
        raise NotFoundError("Клубный пак не найден")

    club = await _lock_club(db, membership.club_id)
    await debit_club_budget(db, club, pack.price, ClubBudgetTransactionType.pack_purchase, f"Открытие пака «{pack.name}»", "club_pack", pack.id)

    opening = ClubPackOpening(club_id=club.id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=idempotency_key)
    db.add(opening)
    await db.flush()

    existing_player_ids_result = await db.execute(select(ClubCard.player_id).where(ClubCard.club_id == club.id))
    existing_player_ids = set(existing_player_ids_result.scalars().all())

    rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
    opened_cards: list[OpenedClubCardOut] = []
    for rarity in rarities:
        player = await pick_random_player(db, rarity)
        is_new = player.id not in existing_player_ids
        existing_player_ids.add(player.id)
        club_card = await create_club_card(db, club.id, player.id, ClubCardSource.club_pack, opening.id)
        db.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=club_card.id, is_new_player=is_new))
        opened_cards.append(OpenedClubCardOut(card=ClubCardOut(id=club_card.id, serial_number=club_card.serial_number, player=club_card.player, acquired_at=club_card.acquired_at, is_in_lineup=False), is_new=is_new))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.execute(
            select(ClubPackOpening).where(ClubPackOpening.club_id == membership.club_id, ClubPackOpening.idempotency_key == idempotency_key)
        )
        return await _get_result_for_existing_opening(db, existing.scalar_one())

    await db.refresh(club)
    return ClubPackOpenResult(opening_id=opening.id, pack=ClubPackOut.model_validate(pack), cards=opened_cards, new_budget=club.budget)
```

`pick_random_player(db, rarity)`'s signature above is confirmed exact (`backend/app/services/pack_service.py:84`) — call it verbatim as written. `roll_rarities(probabilities, card_count, guaranteed_min_rarity)` (`pack_service.py:60`) is confirmed too: it duck-types its `probabilities` argument (only ever reads `.rarity`/`.probability` off each item), so passing `pack.rarity_probabilities` — a list of `ClubPackRarityProbability`, not the personal-pack `PackRarityProbability` its own type hint names — works correctly despite the type-hint mismatch; don't "fix" this by converting to tuples or another shape, the function as written wants plain objects with those two attributes.

- [ ] **Step 5: Router**

In `backend/app/routers/clubs.py`, add `from app.schemas.club_pack import ClubPackOut` and `from app.schemas.club_pack_open import ClubPackOpenResult, OpenClubPackRequest`, `from app.services import club_pack_service`, `from app.core.rate_limit import check_rate_limit`, then:

```python
@router.get("/packs", response_model=list[ClubPackOut])
async def list_club_packs(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await club_pack_service.list_club_packs(db)


@router.post("/me/packs/{club_pack_id}/open", response_model=ClubPackOpenResult)
async def open_club_pack(club_pack_id: int, payload: OpenClubPackRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"open_club_pack:{user.id}", max_calls=10, window_seconds=60)
    return await club_pack_service.open_club_pack(db, user, club_pack_id, payload.idempotency_key)
```

- [ ] **Step 6: Tests**

Create `backend/tests/test_club_packs.py`:

```python
from tests.factories import create_player
from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    return {"Authorization": f"Bearer {session_resp.json()['admin_token']}"}


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    return resp.json(), headers


async def test_open_club_pack_debits_budget_and_mints_cards(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-test-pack", "name": "Тестовый клубный пак", "price": 100, "card_count": 2,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]

    club, headers = await _create_club(client, bot_token, 820400, "Клуб с паками")
    # Give the club enough budget via the daily claim (200 coins by default) — not enough
    # for a 100-coin pack twice, but enough to open once and verify the debit.
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    open_resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "test-key-1"})
    assert open_resp.status_code == 200
    body = open_resp.json()
    assert body["new_budget"] == 100  # 200 - 100
    assert len(body["cards"]) == 2

    cards_resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert len(cards_resp.json()) == 17  # 15 starting + 2 from the pack


async def test_open_club_pack_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-idem-pack", "name": "Идемпотентный пак", "price": 50, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820401, "Клуб с идемпотентностью")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    first = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    second = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    assert first.json()["opening_id"] == second.json()["opening_id"]
    assert first.json()["new_budget"] == second.json()["new_budget"]


async def test_open_club_pack_fails_on_insufficient_budget(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-expensive-pack", "name": "Дорогой пак", "price": 999999, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820402, "Бедный клуб")

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={})
    assert resp.status_code == 400
```

- [ ] **Step 7: Run, iterate, full suite, commit**

```bash
docker compose exec -T backend pytest tests/test_club_packs.py -v
docker compose exec -T backend pytest tests/ -q
git add backend/app/models/club_pack_opening.py backend/app/models/__init__.py backend/alembic/versions/0062_club_pack_openings.py backend/app/schemas/club_pack_open.py backend/app/services/club_pack_service.py backend/app/routers/clubs.py backend/tests/test_club_packs.py
git commit -m "Add club pack opening (idempotent, budget-debited)"
```

---

### Task 9: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/clubSquad.ts`
- Create: `frontend/src/api/clubPacks.ts`
- Modify: `frontend/src/api/clubs.ts`

**Interfaces:**
- Produces: `ClubCard`, `ClubLineup`, `ClubLineupSlot`, `ClubPack` TS types; `fetchClubLineup`, `setClubLineup`, `fetchClubCards`, `fetchClubPacks`, `openClubPack`, `claimDailyReward` API functions — consumed by every later frontend task.

- [ ] **Step 1: Types**

In `frontend/src/types/index.ts`, add (note: this is the real file — see Phase 1's Task 7 ledger note that the plan's own text may say `types.ts`, always the same file):

```typescript
export interface ClubCard {
  id: number;
  serial_number: number;
  player: Player;
  acquired_at: string;
  is_in_lineup: boolean;
}

export interface ClubLineupSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  card: ClubCard | null;
}

export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  slots: ClubLineupSlot[];
}

export interface ClubPackRarityProbability {
  rarity: string;
  probability: number;
}

export interface ClubPack {
  id: number;
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: string | null;
  image_path: string | null;
  is_active: boolean;
  sort_order: number;
  rarity_probabilities: ClubPackRarityProbability[];
}

export interface OpenedClubCard {
  card: ClubCard;
  is_new: boolean;
}

export interface ClubPackOpenResult {
  opening_id: number;
  pack: ClubPack;
  cards: OpenedClubCard[];
  new_budget: number;
}
```

Also update the existing `Club` interface (from Phase 1) to add `budget: number;`.

- [ ] **Step 2: Squad API client**

Create `frontend/src/api/clubSquad.ts`:

```typescript
import { api } from "@/lib/api";
import type { ClubCard, ClubLineup } from "@/types";

export async function fetchClubLineup(): Promise<ClubLineup> {
  const { data } = await api.get<ClubLineup>("/clubs/me/lineup");
  return data;
}

export async function setClubLineup(slots: { slot_code: string; club_card_id: number }[]): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/lineup", { slots });
  return data;
}

export async function fetchClubCards(): Promise<ClubCard[]> {
  const { data } = await api.get<ClubCard[]>("/clubs/me/cards");
  return data;
}
```

- [ ] **Step 3: Packs API client**

Create `frontend/src/api/clubPacks.ts`:

```typescript
import { api } from "@/lib/api";
import type { ClubPack, ClubPackOpenResult } from "@/types";

export async function fetchClubPacks(): Promise<ClubPack[]> {
  const { data } = await api.get<ClubPack[]>("/clubs/packs");
  return data;
}

export async function openClubPack(packId: number, idempotencyKey?: string): Promise<ClubPackOpenResult> {
  const { data } = await api.post<ClubPackOpenResult>(`/clubs/me/packs/${packId}/open`, {
    idempotency_key: idempotencyKey ?? crypto.randomUUID(),
  });
  return data;
}
```

- [ ] **Step 4: Add `claimDailyReward` to the existing club API client**

In `frontend/src/api/clubs.ts`, add:

```typescript
export async function claimDailyReward(): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/me/daily-claim");
  return data;
}
```

- [ ] **Step 5: Typecheck, commit**

```bash
docker compose exec -T frontend npm run typecheck
git add frontend/src/types/index.ts frontend/src/api/clubSquad.ts frontend/src/api/clubPacks.ts frontend/src/api/clubs.ts
git commit -m "Add frontend types and API clients for club squad, packs, and daily claim"
```

---

### Task 10: Squad editor page

**Files:**
- Create: `frontend/src/components/clubs/ClubCardPickerModal.tsx`
- Create: `frontend/src/pages/ClubSquadPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `fetchClubLineup`/`setClubLineup`/`fetchClubCards` (Task 9), `FORMATION_SLOTS`/`CATEGORY_POSITIONS`/`CATEGORY_LABELS` (existing `@/lib/formation`).
- Produces: `/clubs/squad` route, a link from `ClubHome` (captain/assistant only) to reach it.

- [ ] **Step 1: `ClubCardPickerModal`**

Create `frontend/src/components/clubs/ClubCardPickerModal.tsx` — a near-verbatim copy of `frontend/src/components/cards/CardPickerModal.tsx`, typed for `ClubCard` instead of `UserCard`:

```typescript
import { AnimatePresence, motion } from "framer-motion";

import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import PlayerCard from "@/components/cards/PlayerCard";
import type { ClubCard } from "@/types";

interface Props {
  open: boolean;
  title: string;
  cards: ClubCard[];
  disabledCardIds?: number[];
  onSelect: (card: ClubCard) => void;
  onClose: () => void;
}

export default function ClubCardPickerModal({ open, title, cards, disabledCardIds = [], onSelect, onClose }: Props) {
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
              <p className="font-display text-lg font-bold text-slate-100">{title}</p>
              <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm text-slate-300">Закрыть</button>
            </div>
            {cards.length === 0 ? (
              <EmptyState icon={IconCollection} title="Нет подходящих карточек" description="Открой клубные паки, чтобы получить игроков этой позиции" />
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {cards.map((card) => (
                  <PlayerCard
                    key={card.id}
                    player={card.player}
                    size="sm"
                    dimmed={disabledCardIds.includes(card.id)}
                    onClick={() => !disabledCardIds.includes(card.id) && onSelect(card)}
                  />
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

- [ ] **Step 2: `ClubSquadPage`**

Create `frontend/src/pages/ClubSquadPage.tsx` — adapted from `ArenaPage.tsx`'s lineup-editor section (lines ~140-235 of that file), dropping the tactic picker (club squads have no tactic per this plan's scope) and the match-play parts:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import ClubCardPickerModal from "@/components/clubs/ClubCardPickerModal";
import { IconChevronLeft, IconPlus } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubCards, fetchClubLineup, setClubLineup } from "@/api/clubSquad";
import { staticUrl } from "@/lib/api";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import type { ClubCard, ClubLineupSlot } from "@/types";

export default function ClubSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: lineup, isLoading: lineupLoading } = useQuery({ queryKey: ["clubs", "lineup"], queryFn: fetchClubLineup });
  const { data: cards } = useQuery({ queryKey: ["clubs", "cards"], queryFn: fetchClubCards });
  const [pickerSlot, setPickerSlot] = useState<ClubLineupSlot | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setLineupMutation = useMutation({
    mutationFn: setClubLineup,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup"] }); queryClient.invalidateQueries({ queryKey: ["clubs", "cards"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  if (lineupLoading) return <ListSkeleton />;

  const usedPlayerIds = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.slot_code)
    : lineup?.slots.filter((s) => s.card)
  )?.map((s) => s.card!.player.id) ?? [];

  const cardsForSlot = (slot: ClubLineupSlot): ClubCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category as FormationSlot["category"]];
    return (cards ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: ClubLineupSlot, card: ClubCard) => {
    const currentSlots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== slot.slot_code)
      .map((s) => ({ slot_code: s.slot_code, club_card_id: s.card!.id }));
    currentSlots.push({ slot_code: slot.slot_code, club_card_id: card.id });
    await setLineupMutation.mutateAsync(currentSlots);
    setPickerSlot(null);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Состав клуба</h1>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав 4-3-3</p>
          {lineup?.is_complete && <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>}
        </div>
        <div className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
            <div key={category} className="relative flex justify-evenly gap-2">
              {lineup?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button
                    key={slot.slot_code}
                    onClick={() => setPickerSlot(slot)}
                    disabled={setLineupMutation.isPending}
                    className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                  >
                    {slot.card ? (
                      <>
                        <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                          <img
                            src={staticUrl(slot.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">{slot.card.player.position}</span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.card.player.rating}</span>
                      </>
                    ) : (
                      <>
                        <IconPlus size={18} className="text-ink-mist-dim" />
                        <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                      </>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </div>
      </section>

      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Запас</p>
        <div className="grid grid-cols-4 gap-2">
          {(cards ?? []).filter((c) => !c.is_in_lineup).map((c) => (
            <div key={c.id} className="flex flex-col items-center gap-1 rounded-xl bg-bg-surface p-1.5">
              <img
                src={staticUrl(c.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt="" className="aspect-square w-full rounded-lg object-cover"
              />
              <span className="font-mono text-[9px] text-ink-mist-dim">{c.player.position} · {c.player.rating}</span>
            </div>
          ))}
        </div>
      </div>

      {pickerSlot && (
        <ClubCardPickerModal
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category as FormationSlot["category"]]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => setPickerSlot(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Route + link from club home**

In `frontend/src/App.tsx`: add `import ClubSquadPage from "@/pages/ClubSquadPage";` and `<Route path="/clubs/squad" element={<ClubSquadPage />} />` next to the other `/clubs/*` routes.

In `frontend/src/pages/ClubsPage.tsx`'s `ClubHome`, add a button visible only to `isManager` linking to `/clubs/squad` (place it near the invite-link block, e.g. right after it):

```typescript
      {isManager && (
        <button
          onClick={() => navigate("/clubs/squad")}
          className="rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          ⚽ Управление составом
        </button>
      )}
```

`ClubHome` doesn't currently call `useNavigate()` — check whether it's already imported/available in that component's scope (it's a separate function from `ClubBrowseList` in the same file); if not, add `const navigate = useNavigate();` inside `ClubHome` (the `useNavigate` import itself should already exist at the top of `ClubsPage.tsx` from Task 9/10's original Phase 1 work if `ClubBrowseList` uses it — confirm by reading the file first).

- [ ] **Step 4: Typecheck + browser verification**

```bash
docker compose exec -T frontend npm run typecheck
```
Rebuild (`docker compose up -d --build frontend`) and manually verify in-browser: open a club you captain, tap "Управление составом", confirm the 11-slot pitch grid renders with the seeded starters, tap an empty-looking... actually every slot is filled from the seed — tap a FILLED slot, confirm the picker modal opens showing same-category cards (including the 4 bench cards), pick one, confirm the swap persists (team strength updates, the previously-assigned card now shows in "Запас").

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clubs/ClubCardPickerModal.tsx frontend/src/pages/ClubSquadPage.tsx frontend/src/App.tsx frontend/src/pages/ClubsPage.tsx
git commit -m "Add club squad editor page"
```

---

### Task 11: Club budget UI on the club home page

**Files:**
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `claimDailyReward` (Task 9), `club.budget` (Task 9's type addition).

- [ ] **Step 1: Add budget display + daily-claim button to `ClubHome`**

In `frontend/src/pages/ClubsPage.tsx`, add the import `claimDailyReward` to the existing `@/api/clubs` import line, then inside `ClubHome`, add:

```typescript
  const [claimError, setClaimError] = useState<string | null>(null);
  const claimMutation = useMutation({
    mutationFn: claimDailyReward,
    onSuccess: () => { invalidate(); setClaimError(null); },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось получить награду"),
  });
```

(`useState` needs importing if not already present in this file — check first.) Render, right after the member-count/role line near the top of `ClubHome`'s JSX:

```typescript
      <div className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
        <div>
          <p className="text-xs text-ink-mist-dim">Бюджет клуба</p>
          <p className="font-mono text-lg font-bold text-accent-lime">🪙 {club.budget}</p>
        </div>
        <button
          onClick={() => claimMutation.mutate()}
          disabled={claimMutation.isPending}
          className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          Ежедневная награда
        </button>
      </div>
      {claimError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{claimError}</p>}
```

- [ ] **Step 2: Typecheck + browser verification**

```bash
docker compose exec -T frontend npm run typecheck
```
Rebuild and verify in-browser: club home shows "Бюджет клуба 🪙 0", tap "Ежедневная награда", confirm it jumps to 200 and the button click twice in a row surfaces the "already claimed today" error message.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClubsPage.tsx
git commit -m "Add club budget display and daily-reward claim button"
```

---

### Task 12: Club packs page

**Files:**
- Create: `frontend/src/pages/ClubPacksPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `fetchClubPacks`/`openClubPack` (Task 9).
- Produces: `/clubs/packs` route, a link from `ClubHome` (manager-only, to open packs — spec says only captain/assistants spend budget; browsing the list itself could be open to all members, but this task keeps the whole page manager-gated for simplicity since only they can act on it).

- [ ] **Step 1: `ClubPacksPage`**

Create `frontend/src/pages/ClubPacksPage.tsx`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { IconChevronLeft } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubPacks, openClubPack } from "@/api/clubPacks";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { ClubPackOpenResult } from "@/types";

export default function ClubPacksPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["clubs", "packs"], queryFn: fetchClubPacks });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClubPackOpenResult | null>(null);

  const openMutation = useMutation({
    mutationFn: (packId: number) => openClubPack(packId),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось открыть пак")),
  });

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубные паки</h1>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {result && (
        <div className="rounded-2xl bg-bg-surface p-4">
          <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Получено:</p>
          <div className="grid grid-cols-3 gap-2">
            {result.cards.map((oc) => (
              <div key={oc.card.id} className="flex flex-col items-center gap-1 rounded-xl bg-bg-base p-1.5">
                <img
                  src={staticUrl(oc.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt="" className="aspect-square w-full rounded-lg object-cover"
                />
                <span className="font-mono text-[9px] text-ink-mist-dim">{oc.card.player.display_name}</span>
                {oc.is_new && <span className="text-[9px] text-accent-lime">Новый!</span>}
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-mist-dim">Новый бюджет: 🪙 {result.new_budget}</p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {(packs ?? []).map((pack) => (
          <div key={pack.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <img
              src={staticUrl(pack.image_path ?? undefined) ?? staticUrl("packs/basic.webp")}
              alt="" className="h-14 w-14 rounded-xl object-cover"
            />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{pack.name}</p>
              <p className="text-xs text-ink-mist-dim">{pack.card_count} карточки · 🪙 {pack.price}</p>
            </div>
            <button
              onClick={() => openMutation.mutate(pack.id)}
              disabled={openMutation.isPending}
              className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
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

- [ ] **Step 2: Route + link from club home**

In `frontend/src/App.tsx`: add `import ClubPacksPage from "@/pages/ClubPacksPage";` and `<Route path="/clubs/packs" element={<ClubPacksPage />} />`.

In `frontend/src/pages/ClubsPage.tsx`'s `ClubHome`, add another manager-only button right next to the squad-management one from Task 10:

```typescript
        <button
          onClick={() => navigate("/clubs/packs")}
          className="rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          🎁 Клубные паки
        </button>
```

- [ ] **Step 3: Typecheck + browser verification**

```bash
docker compose exec -T frontend npm run typecheck
```
Rebuild and verify in-browser end-to-end: as an admin, create a club pack via `/admin/club-packs` (once Task 13 adds the admin UI — if this task runs before Task 13, use the API directly via Swagger/`curl` for this verification step instead, and re-verify via the real admin UI once Task 13 lands). Then as a club captain with budget (claim the daily reward first), open `/clubs/packs`, open the pack, confirm new cards appear and the budget decrements, then confirm those cards show up in `/clubs/squad`'s "Запас" section.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ClubPacksPage.tsx frontend/src/App.tsx frontend/src/pages/ClubsPage.tsx
git commit -m "Add club packs page"
```

---

### Task 13: Admin `ClubPacksPage`

**Files:**
- Modify: `frontend/src/admin/api.ts`
- Modify: `frontend/src/admin/types.ts`
- Create: `frontend/src/admin/pages/AdminClubPacksPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: the `/admin/club-packs` endpoints (Task 7).
- Produces: `/admin/club-packs` admin route, a near-copy of `AdminPacksPage.tsx`'s CRUD UI, priced in club budget instead of personal coins/stars (no stars_price/bonus_coins/badge/purchase-limit/availability-window fields, since `ClubPack` deliberately doesn't have them).

- [ ] **Step 1: Admin API client**

In `frontend/src/admin/api.ts`, add a `ClubPack` section (near the existing `Packs` section):

```typescript
// --- Club Packs ---
export async function fetchAdminClubPacks(): Promise<ClubPack[]> {
  const { data } = await api.get<ClubPack[]>("/admin/club-packs");
  return data;
}

export async function createClubPack(payload: Record<string, unknown>): Promise<ClubPack> {
  const { data } = await api.post<ClubPack>("/admin/club-packs", payload);
  return data;
}

export async function updateClubPack(id: number, payload: Record<string, unknown>): Promise<ClubPack> {
  const { data } = await api.put<ClubPack>(`/admin/club-packs/${id}`, payload);
  return data;
}

export async function uploadClubPackImage(id: number, file: File): Promise<ClubPack> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<ClubPack>(`/admin/club-packs/${id}/image`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function toggleClubPackActive(id: number): Promise<ClubPack> {
  const { data } = await api.post<ClubPack>(`/admin/club-packs/${id}/toggle-active`);
  return data;
}

export async function deleteClubPack(id: number): Promise<void> {
  await api.delete(`/admin/club-packs/${id}`);
}
```

Add `ClubPack` to the existing `import type { ... } from "@/types"` block at the top of this file (it's a player-facing type already added in Task 9, reused here since the admin CRUD returns/consumes the exact same shape).

- [ ] **Step 2: Admin types**

`ClubPack` already lives in `frontend/src/types/index.ts` (Task 9) — no separate admin-only type needed; `frontend/src/admin/types.ts` doesn't need a new interface, just import `ClubPack` from `@/types` wherever the admin page needs it.

- [ ] **Step 3: `AdminClubPacksPage`**

Create `frontend/src/admin/pages/AdminClubPacksPage.tsx` — a trimmed copy of `AdminPacksPage.tsx`'s CRUD shape, dropping every field `ClubPack` doesn't have (stars_price, bonus_coins, badge, purchase_limit_per_user, available_from/until). Read `AdminPacksPage.tsx` first for its exact modal/form structure (already summarized: local `PackForm`-shaped state, `probabilities: Record<Rarity, number>` converted to `rarity_probabilities` on submit, sum-to-100%-validated save button, image upload or template picker). Build the equivalent:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createClubPack, deleteClubPack, fetchAdminClubPacks, toggleClubPackActive, updateClubPack, uploadClubPackImage } from "@/admin/api";
import { staticUrl } from "@/lib/api";
import type { ClubPack } from "@/types";

type Rarity = "common" | "rare" | "epic" | "legendary";
const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];

interface ClubPackForm {
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: Rarity | "";
  probabilities: Record<Rarity, number>;
  is_active: boolean;
}

function packToForm(p?: ClubPack): ClubPackForm {
  const probabilities = { common: 0, rare: 0, epic: 0, legendary: 0 } as Record<Rarity, number>;
  for (const rp of p?.rarity_probabilities ?? []) probabilities[rp.rarity as Rarity] = rp.probability * 100;
  return {
    slug: p?.slug ?? "", name: p?.name ?? "", description: p?.description ?? "",
    price: p?.price ?? 100, card_count: p?.card_count ?? 3,
    guaranteed_min_rarity: (p?.guaranteed_min_rarity as Rarity) ?? "",
    probabilities, is_active: p?.is_active ?? true,
  };
}

export default function AdminClubPacksPage() {
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["admin-club-packs"], queryFn: fetchAdminClubPacks });
  const [editing, setEditing] = useState<ClubPack | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<ClubPackForm>(packToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-club-packs"] });
  const toggleMutation = useMutation({ mutationFn: toggleClubPackActive, onSuccess: invalidate });
  const deleteMutation = useMutation({ mutationFn: deleteClubPack, onSuccess: invalidate });

  const probabilitySum = RARITIES.reduce((sum, r) => sum + (form.probabilities[r] || 0), 0);
  const probabilitiesValid = Math.abs(probabilitySum - 100) < 2;

  const buildPayload = () => ({
    slug: form.slug, name: form.name, description: form.description, price: form.price, card_count: form.card_count,
    guaranteed_min_rarity: form.guaranteed_min_rarity || null,
    rarity_probabilities: RARITIES.filter((r) => form.probabilities[r] > 0).map((r) => ({ rarity: r, probability: form.probabilities[r] / 100 })),
    is_active: form.is_active,
  });

  const createMutation = useMutation({ mutationFn: () => createClubPack(buildPayload()), onSuccess: () => { invalidate(); setCreating(false); }, onError: () => setError("Не удалось создать пак") });
  const updateMutation = useMutation({ mutationFn: () => updateClubPack(editing!.id, buildPayload()), onSuccess: () => { invalidate(); setEditing(null); }, onError: () => setError("Не удалось обновить пак") });

  const openEdit = (p: ClubPack) => { setEditing(p); setForm(packToForm(p)); setError(null); };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Клубные паки</h1>
        <button onClick={() => { setCreating(true); setForm(packToForm()); setError(null); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">+ Новый пак</button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {packs?.map((p) => (
          <div key={p.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center gap-3">
              <img src={staticUrl(p.image_path ?? undefined) ?? staticUrl("packs/basic.webp")} className="h-12 w-12 rounded-lg object-cover" />
              <div className="flex-1">
                <p className="font-display text-sm font-bold">{p.name}</p>
                <p className="text-xs text-slate-400">{p.card_count} карточки · 🪙 {p.price}</p>
              </div>
            </div>
            <p className="mt-1 text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">{p.is_active ? "Отключить" : "Включить"}</button>
              <button onClick={() => deleteMutation.mutate(p.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать клубный пак" : "Новый клубный пак"}</p>
            <div className="flex flex-col gap-2 text-sm">
              {!editing && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Slug</span>
                  <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Название</span>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Описание</span>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Цена (бюджет клуба)</span>
                  <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Карточек в паке</span>
                  <input type="number" value={form.card_count} onChange={(e) => setForm({ ...form, card_count: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              </div>
              <p className="mt-2 text-xs text-slate-400">Вероятности редкости (сумма ≈ 100%): {probabilitySum.toFixed(1)}%</p>
              <div className="grid grid-cols-2 gap-2">
                {RARITIES.map((r) => (
                  <label key={r} className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">{r}</span>
                    <input
                      type="number" value={form.probabilities[r]}
                      onChange={(e) => setForm({ ...form, probabilities: { ...form.probabilities, [r]: Number(e.target.value) } })}
                      className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                    />
                  </label>
                ))}
              </div>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
            </div>
            {error && <p className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                disabled={!probabilitiesValid || !form.slug.trim() && !editing || !form.name.trim()}
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

Note: `uploadClubPackImage` is imported by the API client (Step 1) but this minimal form doesn't wire an image upload control — that's an intentional scope trim for Phase 2 (packs render with a placeholder image via `staticUrl("packs/basic.webp")` until an admin uploads one via a follow-up; don't add unused-import lint noise — if `uploadClubPackImage` ends up unused in this file, don't import it here at all, only import what Step 1 actually calls from this specific page).

- [ ] **Step 4: Route**

In `frontend/src/App.tsx`, inside the `<Route path="/admin" ...>` block: add `import AdminClubPacksPage from "@/admin/pages/AdminClubPacksPage";` and `<Route path="club-packs" element={<AdminClubPacksPage />} />` near the existing `<Route path="packs" element={<AdminPacksPage />} />`.

- [ ] **Step 5: Typecheck + full verification pass**

```bash
docker compose exec -T frontend npm run typecheck
docker compose exec -T backend pytest tests/ -q
```
Both clean except the one pre-existing unrelated failure. Rebuild and do the deferred Task 12 verification now (create a club pack via the real admin UI at `/admin/club-packs`, then open it as a club captain via `/clubs/packs`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/api.ts frontend/src/admin/pages/AdminClubPacksPage.tsx frontend/src/App.tsx
git commit -m "Add admin ClubPacksPage"
```
