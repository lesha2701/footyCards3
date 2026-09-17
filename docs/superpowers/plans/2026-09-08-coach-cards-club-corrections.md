# Coach Cards — Club-Track Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct three things about the just-shipped club coach-card feature
(Coach Cards Phase 2, local-only, commits `5a6a055..7312355`): coaches drop
from the *same* `ClubPack` as players instead of a dedicated `ClubCoachPack`;
the squad-page equip control becomes a formation-grid cell (mirroring the
player-slot picker) instead of a dropdown; and the coach picker shows each
candidate's boosts at selection time, not only after equipping.

**Architecture:** `ClubPack` gains a `coach_drop_chance` float column. Each
of a pack's existing `card_count` roll slots independently coin-flips against
that chance to become a coach draw instead of a player draw, reusing
`roll_rarities`/`pick_random_player`/`pick_random_coach` verbatim — no new
roll machinery. `ClubPackOpeningCard` becomes a "one of two kinds" row (a
nullable `club_card_id` XOR a nullable `club_coach_card_id`). The entire
`ClubCoachPack`/`ClubCoachPackOpening` subsystem (models, service, routes,
admin page, player-facing pages) is deleted — it was never pushed anywhere
and has zero real data, so removal is a straightforward drop, not a
deprecation. The squad page's coach `TacticSelect` dropdown is replaced by a
grid cell + a new `ClubCoachCardPickerModal.tsx`, a direct structural mirror
of the existing `ClubCardPickerModal.tsx` used for player slots.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 + TypeScript
+ TanStack Query + Framer Motion (frontend), Alembic migrations, pytest
(in-memory SQLite).

**Spec:** `docs/superpowers/specs/2026-09-08-coach-cards-design.md` (§7 of
that spec originally called for two independent pack systems — this plan is
a deliberate, user-approved revision of that decision for the club track
only; the spec's personal/Arena track, §7-§9's non-club half, is unaffected
and out of scope here).

## Global Constraints

- Never trust frontend-submitted values for balances/rewards/cards — all
  probability rolls and card minting stay server-side (existing pattern,
  unchanged by this plan).
- Any operation involving coins/cards/packs must be atomic and idempotency-
  key-protected — `open_club_pack`'s existing idempotency-key-unique-
  constraint + row-locking pattern must be preserved exactly as this plan
  extends it, not weakened.
- Use row locking for race-sensitive operations — `create_club_coach_card`'s
  `Coach.next_club_serial_number` counter lock (already built, being moved
  not rewritten) must keep using `db.refresh(..., with_for_update=True)`,
  never a racy `MAX(serial_number) + 1` scan.
- Alembic revisions are named sequentially (`NNNN_short_description.py`),
  current HEAD is `0093_club_lineup_coach.py` — this plan's migrations are
  `0094` and `0095`.
- CHECK constraints must be written in portable SQL both Postgres and the
  SQLite test suite can apply (no Postgres-only functions like
  `num_nonnulls()` — this codebase's test suite creates tables from the ORM
  metadata directly, so a Postgres-only CHECK expression breaks every test
  in the file that touches that table, not just Postgres deployments).
- `ClubCoachCardSource.club_pack` already has the generic value `"club_pack"`
  (not `"club_coach_pack"`) — no enum rename needed for coaches minted via a
  regular `ClubPack`.
- Do not touch `coach_boost_service.py`, `club_tactical_matchup_service.py`,
  `club_tactical_profile_service.py`, or `tournament_simulation_service.py`
  — this plan is acquisition/equip-UX only, the match-engine wiring from
  Phase 2 is untouched and out of scope.
- Do not touch the personal (non-club) `Pack`/`PackOpeningCard` models or
  `pack_service.open_pack` — those are player-only today and stay that way;
  adding coaches to them is explicitly deferred to a later plan (per this
  session's own sequencing decision).

---

### Task 1: Migration + model/schema changes — `ClubPack` gains a coach slot

**Files:**
- Modify: `backend/app/models/club_pack.py`
- Modify: `backend/app/models/club_pack_opening.py`
- Modify: `backend/app/schemas/club_pack.py`
- Modify: `backend/app/schemas/club_pack_open.py`
- Create: `backend/alembic/versions/0094_club_pack_coach_slots.py`
- Test: `backend/tests/test_club_pack_model.py` (create if it doesn't exist — check first; if there's no existing model-level test file for `ClubPack`, add one)

**Interfaces:**
- Produces: `ClubPack.coach_drop_chance: float`; `ClubPackOpeningCard.club_card_id: Optional[int]` (now nullable), `ClubPackOpeningCard.club_coach_card_id: Optional[int]` (new), `ClubPackOpeningCard.is_new: bool` (renamed from `is_new_player`); `ClubPackOut.coach_drop_chance`, `ClubPackCreate.coach_drop_chance`, `ClubPackUpdate.coach_drop_chance`; `OpenedClubPackItemOut` (replaces `OpenedClubCardOut`) — Task 2 consumes all of these.

- [ ] **Step 1: Check for an existing `ClubPack` model test file**

Run: `ls backend/tests/ | grep -i club_pack`

If `test_club_pack_model.py` (or similarly named) already exists, read it in
full and add your new test there instead of creating a new file — match its
existing fixture style exactly.

- [ ] **Step 2: Write the failing test for the new column and the dual-FK shape**

```python
# backend/tests/test_club_pack_model.py (add to existing file, or create new)
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.club import Club
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.enums import ClubLogoShape, ClubType
from app.models.user import User


@pytest.mark.asyncio
async def test_club_pack_coach_drop_chance_defaults_to_zero(db_session):
    pack = ClubPack(slug="test-pack-default", name="Test Pack", price=100, card_count=3)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    assert pack.coach_drop_chance == 0.0


@pytest.mark.asyncio
async def test_club_pack_opening_card_rejects_both_or_neither_fk_set(db_session):
    user = User(telegram_id=999_100_900, username="pack_slot_test_user")
    db_session.add(user)
    await db_session.flush()
    club = Club(name="Slot Test Club", club_type=ClubType.open, logo_shape=ClubLogoShape.shield, logo_color="#FF0000", captain_id=user.id)
    db_session.add(club)
    await db_session.flush()
    pack = ClubPack(slug="test-pack-slot", name="Test Pack", price=100, card_count=1)
    db_session.add(pack)
    await db_session.flush()
    opening = ClubPackOpening(club_id=club.id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=100)
    db_session.add(opening)
    await db_session.flush()

    # Neither FK set — must be rejected.
    db_session.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=None, club_coach_card_id=None, is_new=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_pack_model.py -v`

Expected: FAIL — `coach_drop_chance` doesn't exist yet (`AttributeError`), and
the "neither FK set" test fails to raise `IntegrityError` because
`club_card_id` isn't nullable yet (it'll raise a `NOT NULL` violation
instead of running the new CHECK — both fine as "fails for the right
reason", the point of this step is confirming the model doesn't yet do what
the test expects).

- [ ] **Step 4: Add `coach_drop_chance` to `ClubPack`**

In `backend/app/models/club_pack.py`, add one column (exact insertion point:
right after `sort_order`):

```python
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Fraction of this pack's card_count slots that roll a coach instead of a
    # player (independent per-slot coin flip, see club_pack_service.open_club_pack).
    # 0.0 (default) means every existing pack stays player-only until an admin
    # opts it in.
    coach_drop_chance: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0, nullable=False)
```

`Numeric` is already imported in this file (used by `ClubPackRarityProbability.probability`).

- [ ] **Step 5: Make `ClubPackOpeningCard` a "player XOR coach" row**

In `backend/app/models/club_pack_opening.py`, replace the whole file:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubPackOpening(Base):
    __tablename__ = "club_pack_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    club_pack_id: Mapped[int] = mapped_column(ForeignKey("club_packs.id", ondelete="CASCADE"), nullable=False)
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
    # Exactly one of these two is set per row — a pack slot resolves to either
    # a player or a coach (see open_club_pack's per-slot coach_drop_chance
    # coin flip), never both, never neither. Portable boolean-expression CHECK
    # (not Postgres's num_nonnulls()) so the SQLite test suite enforces it too.
    club_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=True)
    club_coach_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="CASCADE"), nullable=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False)

    opening: Mapped["ClubPackOpening"] = relationship(back_populates="cards")

    __table_args__ = (
        CheckConstraint(
            "(club_card_id IS NOT NULL AND club_coach_card_id IS NULL) OR "
            "(club_card_id IS NULL AND club_coach_card_id IS NOT NULL)",
            name="ck_club_pack_opening_card_exactly_one_kind",
        ),
    )
```

(`is_new_player` renamed to `is_new` — confirmed via a full-repo grep that
its only callers are `club_pack_service.py`'s own 2 read/write sites, both
updated in Task 2. The separate personal-pack `PackOpeningCard.is_new_player`
in `backend/app/models/pack.py` is a different model — untouched.)

- [ ] **Step 6: Add `coach_drop_chance` to the pack schemas**

In `backend/app/schemas/club_pack.py`, add the field to `ClubPackOut`,
`ClubPackCreate`, and `ClubPackUpdate` (exact insertion point: right after
`sort_order` in each class):

```python
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
    coach_drop_chance: float
    rarity_probabilities: list[ClubPackRarityProbabilityOut]


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
    coach_drop_chance: float = Field(default=0.0, ge=0, le=1)


class ClubPackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    card_count: Optional[int] = Field(default=None, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: Optional[list[ClubPackRarityProbabilityIn]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    coach_drop_chance: Optional[float] = Field(default=None, ge=0, le=1)
```

- [ ] **Step 7: Replace `OpenedClubCardOut` with a discriminated `OpenedClubPackItemOut`**

Replace `backend/app/schemas/club_pack_open.py` entirely:

```python
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut, ClubCoachCardOut


class OpenedClubPackItemOut(BaseModel):
    kind: Literal["player", "coach"]
    card: Optional[ClubCardOut] = None
    coach_card: Optional[ClubCoachCardOut] = None
    is_new: bool


class ClubPackOpenResult(BaseModel):
    opening_id: int
    pack: ClubPackOut
    cards: list[OpenedClubPackItemOut]
    new_budget: int


class OpenClubPackRequest(BaseModel):
    idempotency_key: str | None = None
```

`ClubCoachCardOut` already lives in `app.schemas.club_squad` (confirmed —
`club_coach_pack_service.py` already imports it from there).

- [ ] **Step 8: Write the migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest revision -m "club pack coach slots"`

This writes a new file under `backend/alembic/versions/` with an
auto-generated revision id — **rename it** to `0094_club_pack_coach_slots.py`
and set its `revision`/`down_revision` to match this codebase's sequential
convention. Replace its contents:

```python
"""Add ClubPack.coach_drop_chance and make ClubPackOpeningCard a
player-XOR-coach row

Revision ID: 0094
Revises: 0093
Create Date: 2026-09-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "club_packs",
        sa.Column("coach_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )

    op.add_column("club_pack_opening_cards", sa.Column("club_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_club_pack_opening_cards_club_coach_card_id", "club_pack_opening_cards",
        "club_coach_cards", ["club_coach_card_id"], ["id"], ondelete="CASCADE",
    )

    op.alter_column("club_pack_opening_cards", "club_card_id", nullable=True)
    op.alter_column("club_pack_opening_cards", "is_new_player", new_column_name="is_new")

    op.create_check_constraint(
        "ck_club_pack_opening_card_exactly_one_kind",
        "club_pack_opening_cards",
        "(club_card_id IS NOT NULL AND club_coach_card_id IS NULL) OR "
        "(club_card_id IS NULL AND club_coach_card_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_club_pack_opening_card_exactly_one_kind", "club_pack_opening_cards", type_="check")
    op.alter_column("club_pack_opening_cards", "is_new", new_column_name="is_new_player")
    op.alter_column("club_pack_opening_cards", "club_card_id", nullable=False)
    op.drop_constraint("fk_club_pack_opening_cards_club_coach_card_id", "club_pack_opening_cards", type_="foreignkey")
    op.drop_column("club_pack_opening_cards", "club_coach_card_id")
    op.drop_column("club_packs", "coach_drop_chance")
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_pack_model.py -v`

Expected: PASS.

- [ ] **Step 10: Verify the migration applies cleanly against real Postgres**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest upgrade head --sql` — confirm `0094`'s SQL appears with no errors, and (if you have the running `docker compose` Postgres available) `docker compose exec backend alembic upgrade head` actually applies it.

- [ ] **Step 11: Commit**

```bash
git add backend/app/models/club_pack.py backend/app/models/club_pack_opening.py backend/app/schemas/club_pack.py backend/app/schemas/club_pack_open.py backend/alembic/versions/0094_club_pack_coach_slots.py backend/tests/test_club_pack_model.py
git commit -m "feat(club-packs): add coach_drop_chance and a player-XOR-coach opening-card shape"
```

---

### Task 2: Roll logic — `open_club_pack` mixes coach draws into its existing slots

**Files:**
- Modify: `backend/app/services/club_card_service.py`
- Modify: `backend/app/services/club_pack_service.py`
- Modify: `backend/app/routers/admin_club_packs.py` (no code change needed —
  confirm `ClubPackCreate`/`Update` already carry `coach_drop_chance` from
  Task 1 and this router passes payloads through via `payload.model_dump()`,
  so nothing to edit here; this line exists only so the task's "Files" list
  is honest about what was checked)
- Test: `backend/tests/test_club_packs.py` (read this file in full first —
  it's the existing route-level test file for `open_club_pack`; extend it,
  don't create a new file)

**Interfaces:**
- Consumes: `ClubPack.coach_drop_chance`, `ClubPackOpeningCard.club_coach_card_id`/`is_new` (Task 1); `pick_random_coach`, `roll_rarities` (`app.services.pack_service`, already exist, unchanged); `ClubCoachCardSource` (already exists, unchanged).
- Produces: `club_card_service.create_club_coach_card(db, club_id, coach_id, source, source_ref_id=None) -> ClubCoachCard` — Task 3 (removal) and any future caller reuse this; `club_pack_service.open_club_pack`'s new mixed-item behavior — Task 5 (frontend reveal flow) consumes `OpenedClubPackItemOut`'s `kind` field.

- [ ] **Step 1: Move `create_club_coach_card` into `club_card_service.py`**

Read `backend/app/services/club_card_service.py` in full first (it's short,
already read this session: just `create_club_card`). Add this function to
it, right after `create_club_card` — this is a direct move of
`club_coach_pack_service.py`'s existing `_create_club_coach_card` (made
public, no `source_ref_id` type change, logic byte-identical):

```python
async def create_club_coach_card(
    db: AsyncSession, club_id: int, coach_id: int, source: ClubCoachCardSource, source_ref_id: Optional[int] = None
) -> ClubCoachCard:
    """Mirrors create_club_card exactly, but against the separate
    Coach.next_club_serial_number counter (reserved for this purpose since
    the Coach model was introduced) — club coach acquisitions must never
    affect personal-card serial-number scarcity, and the counter must be
    read-and-incremented under a row lock rather than a racy
    MAX(serial_number) + 1 scan, matching every other serial-number
    allocation in this codebase."""
    coach = await db.get(Coach, coach_id)
    await db.refresh(coach, attribute_names=["next_club_serial_number"], with_for_update=True)
    serial_number = coach.next_club_serial_number
    coach.next_club_serial_number += 1
    db.add(coach)

    card = ClubCoachCard(club_id=club_id, coach_id=coach_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card
```

Add the needed imports at the top of `club_card_service.py`:

```python
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach
from app.models.enums import ClubCoachCardSource
```

(`Optional` is presumably already imported for `create_club_card`'s own
signature — confirm, add if missing.)

- [ ] **Step 2: Write the failing test for the mixed-slot roll**

Read `backend/tests/test_club_packs.py` in full to find its existing
`_create_club`/position-pool-seeding fixture helpers (this codebase's
established pattern — every club-pack test file this session has repeated
this same autouse fixture verbatim since fixtures are file-scoped) and reuse
them exactly. Add:

```python
async def test_open_club_pack_with_coach_drop_chance_can_yield_a_coach(client, db_session, bot_token):
    from app.models.club_pack import ClubPack, ClubPackRarityProbability
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType, Rarity

    coach = Coach(display_name="Slot Test Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
    db_session.add(coach)

    pack = ClubPack(slug="coach-slot-pack", name="Coach Slot Pack", price=50, card_count=5, coach_drop_chance=1.0)
    pack.rarity_probabilities = [ClubPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    club, headers = await _create_club(client, bot_token, 830500, "Клуб со слотами тренеров")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "slot-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 5
    # coach_drop_chance=1.0 -> every slot must resolve to a coach.
    assert all(item["kind"] == "coach" for item in body["cards"])
    assert all(item["coach_card"]["coach"]["display_name"] == "Slot Test Coach" for item in body["cards"])
    assert all(item["card"] is None for item in body["cards"])


async def test_open_club_pack_with_zero_coach_drop_chance_never_yields_a_coach(client, db_session, bot_token):
    from app.models.club_pack import ClubPack, ClubPackRarityProbability
    from app.models.enums import Rarity

    pack = ClubPack(slug="no-coach-pack", name="No Coach Pack", price=50, card_count=3, coach_drop_chance=0.0)
    pack.rarity_probabilities = [ClubPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    club, headers = await _create_club(client, bot_token, 830501, "Клуб без тренеров")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "slot-key-2"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(item["kind"] == "player" for item in body["cards"])
```

(Adjust `_create_club`'s call signature to match whatever the real helper in
`test_club_packs.py` actually takes — the two calls above assume it matches
`club_coach_pack_service`'s own test helper shape, `(client, bot_token,
telegram_id, name) -> (club_dict, headers)`; confirm against the real file.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_packs.py -k coach_drop_chance -v`

Expected: FAIL — `open_club_pack` doesn't roll coaches yet, and the response
shape doesn't have `kind`/`coach_card` fields yet.

- [ ] **Step 3: Rewrite `open_club_pack`'s roll loop**

In `backend/app/services/club_pack_service.py`, replace the whole file:

```python
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_coach_card import ClubCoachCard
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.coach import Coach
from app.models.enums import ClubBudgetTransactionType, ClubCardSource, ClubCoachCardSource
from app.models.user import User
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_pack_open import ClubPackOpenResult, OpenedClubPackItemOut
from app.schemas.club_squad import ClubCardOut, ClubCoachCardOut
from app.services.club_card_service import create_club_card, create_club_coach_card
from app.services.club_budget_service import debit_club_budget
from app.services.club_service import _lock_club, _require_manager, _require_membership
from app.services.pack_service import pick_random_coach, pick_random_player, roll_rarities


async def list_club_packs(db: AsyncSession) -> list[ClubPackOut]:
    result = await db.execute(
        select(ClubPack).where(ClubPack.is_active.is_(True)).options(joinedload(ClubPack.rarity_probabilities)).order_by(ClubPack.sort_order)
    )
    return result.unique().scalars().all()


def _player_item(club_card: ClubCard, is_new: bool) -> OpenedClubPackItemOut:
    return OpenedClubPackItemOut(
        kind="player",
        card=ClubCardOut(id=club_card.id, serial_number=club_card.serial_number, player=club_card.player, acquired_at=club_card.acquired_at, is_in_lineup=False),
        is_new=is_new,
    )


def _coach_item(club_coach_card: ClubCoachCard, is_new: bool) -> OpenedClubPackItemOut:
    return OpenedClubPackItemOut(
        kind="coach",
        coach_card=ClubCoachCardOut(id=club_coach_card.id, serial_number=club_coach_card.serial_number, coach=club_coach_card.coach, acquired_at=club_coach_card.acquired_at),
        is_new=is_new,
    )


async def _get_result_for_existing_opening(db: AsyncSession, opening: ClubPackOpening) -> ClubPackOpenResult:
    pack = await db.get(ClubPack, opening.club_pack_id, options=[joinedload(ClubPack.rarity_probabilities)])
    opening_cards = (await db.execute(select(ClubPackOpeningCard).where(ClubPackOpeningCard.opening_id == opening.id))).scalars().all()

    club_card_ids = [oc.club_card_id for oc in opening_cards if oc.club_card_id is not None]
    club_cards = {c.id: c for c in (await db.execute(select(ClubCard).where(ClubCard.id.in_(club_card_ids)))).scalars().all()} if club_card_ids else {}

    club_coach_card_ids = [oc.club_coach_card_id for oc in opening_cards if oc.club_coach_card_id is not None]
    club_coach_cards = {
        c.id: c
        for c in (
            await db.execute(
                select(ClubCoachCard).where(ClubCoachCard.id.in_(club_coach_card_ids)).options(joinedload(ClubCoachCard.coach).selectinload(Coach.boosts))
            )
        ).scalars().all()
    } if club_coach_card_ids else {}

    items: list[OpenedClubPackItemOut] = []
    for oc in opening_cards:
        if oc.club_card_id is not None:
            items.append(_player_item(club_cards[oc.club_card_id], oc.is_new))
        else:
            items.append(_coach_item(club_coach_cards[oc.club_coach_card_id], oc.is_new))

    club_row = await db.get(Club, opening.club_id)
    return ClubPackOpenResult(opening_id=opening.id, pack=ClubPackOut.model_validate(pack), cards=items, new_budget=club_row.budget)


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

    # See club_coach_pack_service.py's identical historical comment (now
    # removed with that file) on why this must be a plain int, captured
    # before any possible rollback below.
    club_id = club.id

    opening = ClubPackOpening(club_id=club_id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=idempotency_key)

    try:
        db.add(opening)
        await db.flush()

        existing_player_ids = set((await db.execute(select(ClubCard.player_id).where(ClubCard.club_id == club_id))).scalars().all())
        existing_coach_ids = set((await db.execute(select(ClubCoachCard.coach_id).where(ClubCoachCard.club_id == club_id))).scalars().all())

        rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
        opened_items: list[OpenedClubPackItemOut] = []
        coach_drop_chance = float(pack.coach_drop_chance)
        for rarity in rarities:
            if coach_drop_chance > 0 and random.random() < coach_drop_chance:
                coach = await pick_random_coach(db, rarity)
                is_new = coach.id not in existing_coach_ids
                existing_coach_ids.add(coach.id)
                club_coach_card = await create_club_coach_card(db, club_id, coach.id, ClubCoachCardSource.club_pack, opening.id)
                db.add(ClubPackOpeningCard(opening_id=opening.id, club_coach_card_id=club_coach_card.id, club_card_id=None, is_new=is_new))
                opened_items.append(_coach_item(club_coach_card, is_new))
            else:
                player = await pick_random_player(db, rarity)
                is_new = player.id not in existing_player_ids
                existing_player_ids.add(player.id)
                club_card = await create_club_card(db, club_id, player.id, ClubCardSource.club_pack, opening.id)
                db.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=club_card.id, club_coach_card_id=None, is_new=is_new))
                opened_items.append(_player_item(club_card, is_new))

        await db.commit()
    except IntegrityError:
        # Same idempotency-key race and reasoning as before this change —
        # Postgres enforces the (club_id, idempotency_key) unique constraint
        # at INSERT/flush time, not just at COMMIT.
        await db.rollback()
        if not idempotency_key:
            raise
        existing = await db.execute(
            select(ClubPackOpening).where(ClubPackOpening.club_id == club_id, ClubPackOpening.idempotency_key == idempotency_key)
        )
        return await _get_result_for_existing_opening(db, existing.scalar_one())

    await db.refresh(club)
    return ClubPackOpenResult(opening_id=opening.id, pack=ClubPackOut.model_validate(pack), cards=opened_items, new_budget=club.budget)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_club_packs.py -v`

Expected: PASS, including the pre-existing tests in that file (this rewrite
must not change behavior for `coach_drop_chance=0` packs — the two default-
`is_new`/idempotency tests already in that file are your regression check).

- [ ] **Step 5: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: same pass count as before this task plus your new tests, no new
failures (the file `test_club_coach_pack_service.py` will fail at this point
— that's expected and fixed in Task 3, not this one; note it in your report
rather than trying to fix it here).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/club_card_service.py backend/app/services/club_pack_service.py backend/tests/test_club_packs.py
git commit -m "feat(club-packs): roll coaches into existing pack slots via coach_drop_chance"
```

---

### Task 3: Remove the `ClubCoachPack` subsystem entirely

**Files:**
- Delete: `backend/app/models/club_coach_pack.py`
- Delete: `backend/app/models/club_coach_pack_opening.py`
- Delete: `backend/app/services/club_coach_pack_service.py`
- Delete: `backend/app/routers/club_coach_packs.py`
- Delete: `backend/app/routers/admin_club_coach_packs.py`
- Delete: `backend/app/schemas/club_coach_pack.py`
- Delete: `backend/tests/test_club_coach_pack_model.py`
- Delete: `backend/tests/test_club_coach_pack_service.py`
- Delete: `backend/tests/test_admin_club_coach_packs.py`
- Modify: `backend/app/main.py`
- Create: `backend/alembic/versions/0095_drop_club_coach_packs.py`

**Interfaces:**
- Consumes: nothing new — this task only removes.
- Produces: nothing new — confirms via full-repo grep that nothing outside
  the deleted files still imports from them (Task 4/5/6/7's frontend
  deletions are the only other consumers, handled separately).

- [ ] **Step 1: Confirm nothing else imports the files you're about to delete**

Run:
```bash
grep -rn "club_coach_pack\b\|ClubCoachPack\b" backend/app/ --include="*.py" | grep -v "backend/app/models/club_coach_pack.py\|backend/app/models/club_coach_pack_opening.py\|backend/app/services/club_coach_pack_service.py\|backend/app/routers/club_coach_packs.py\|backend/app/routers/admin_club_coach_packs.py\|backend/app/schemas/club_coach_pack.py"
```

Expected output: only 2 lines in `backend/app/main.py` (the router
registrations) — if you see anything else, STOP and report NEEDS_CONTEXT
rather than deleting something still in use.

- [ ] **Step 2: Delete the 6 backend files and 3 test files**

```bash
git rm backend/app/models/club_coach_pack.py backend/app/models/club_coach_pack_opening.py backend/app/services/club_coach_pack_service.py backend/app/routers/club_coach_packs.py backend/app/routers/admin_club_coach_packs.py backend/app/schemas/club_coach_pack.py backend/tests/test_club_coach_pack_model.py backend/tests/test_club_coach_pack_service.py backend/tests/test_admin_club_coach_packs.py
```

- [ ] **Step 3: Remove the router registrations from `main.py`**

In `backend/app/main.py`, find and remove:
1. The two import lines for `club_coach_packs`/`admin_club_coach_packs`
   (grep for `club_coach_packs` in the imports section at the top of the
   file to find their exact current lines).
2. The `app.include_router(club_coach_packs.router, ...)` line and its
   preceding explanatory comment (added in this session's earlier work,
   about `club_coach_packs.router` needing to be registered before
   `clubs.router` — that comment and the line it explains both go away
   together, since the router itself no longer exists).
3. The `app.include_router(admin_club_coach_packs.router, ...)` line.

- [ ] **Step 4: Write the removal migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest revision -m "drop club coach packs"`

Rename the generated file to `0095_drop_club_coach_packs.py`:

```python
"""Drop the ClubCoachPack/ClubCoachPackOpening tables — coaches now drop
from ClubPack directly (see 0094)

Revision ID: 0095
Revises: 0094
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("club_coach_pack_opening_cards")
    op.drop_table("club_coach_pack_openings")
    op.drop_table("club_coach_pack_rarity_probabilities")
    op.drop_table("club_coach_packs")


def downgrade() -> None:
    # These tables held only local-only, never-pushed, zero-real-data test
    # rows (confirmed at the time this migration was written) — an
    # asymmetric downgrade is accepted, same convention as every other
    # "add a new optional thing, remove it cleanly, don't bother recreating
    # the exact schema on rollback" migration in this codebase.
    raise NotImplementedError("This migration is not reversible — see its own docstring.")
```

- [ ] **Step 5: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: same pass count as Task 2's end state, minus the deleted test
files' own test counts, no new failures. `python -c "from app.main import
app"` (this codebase's own import/startup sanity check per CLAUDE.md) must
also succeed — run it too.

- [ ] **Step 6: Verify the migration chain and application**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest upgrade head --sql` — confirm `0095`'s `DROP TABLE` statements appear with no errors, then (against the real running `docker compose` Postgres if available) `docker compose exec backend alembic upgrade head` to actually apply both `0094` and `0095`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(club-packs): remove the ClubCoachPack subsystem — coaches now drop from ClubPack"
```

---

### Task 4: Frontend — types + API client cleanup

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/cards/CardRevealStage.tsx` (comment only)
- Delete: `frontend/src/api/clubCoachPacks.ts`
- Modify: `frontend/src/admin/api.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan (this is the frontend's
  own first task) — mirrors the backend shapes from Task 1/2 by hand.
- Produces: `ClubPack.coach_drop_chance: number`, `OpenedClubPackItem`
  (replaces `OpenedClubCard`) with `kind: "player" | "coach"`, `card:
  ClubCard | null`, `coach_card: ClubCoachCard | null` — Tasks 5, 6 consume
  this.

- [ ] **Step 1: Update `ClubPack` and replace `OpenedClubCard`**

In `frontend/src/types/index.ts`, add `coach_drop_chance` to `ClubPack`
(exact insertion point: right after `sort_order`):

```typescript
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
  coach_drop_chance: number;
  rarity_probabilities: ClubPackRarityProbability[];
}
```

Replace `OpenedClubCard` (delete it) with:

```typescript
export interface OpenedClubPackItem {
  kind: "player" | "coach";
  card: ClubCard | null;
  coach_card: ClubCoachCard | null;
  is_new: boolean;
}
```

Update `ClubPackOpenResult.cards`'s type from `OpenedClubCard[]` to
`OpenedClubPackItem[]`.

`ClubCoachCard` already exists in this file (added in Coach Cards Phase 2's
Task 10) — confirm its shape (`id`, `serial_number`, `coach: EquippedCoach`,
`acquired_at`) is unchanged; you're only referencing it, not editing it.

Also delete the now-unused `ClubCoachPack`, `ClubCoachPackRarityProbability`,
and `ClubCoachPackOpenResult` interfaces from this file (they were the
dedicated coach-pack's own types, now dead — confirm via grep, per Step 3,
before deleting).

- [ ] **Step 2: Update the one comment referencing the old type name**

In `frontend/src/components/cards/CardRevealStage.tsx`, the comment above
`RevealableOpenedCard` (around line 13-17) currently says "reused by
ClubPackOpenPage.tsx for OpenedClubCard" — update it to say
`OpenedClubPackItem` instead (the type it's actually reused for as of this
plan). No other change to this file.

- [ ] **Step 3: Confirm nothing else references the deleted types before deleting them**

```bash
grep -rn "ClubCoachPack\b\|ClubCoachPackRarityProbability\b\|ClubCoachPackOpenResult\b\|OpenedClubCard\b" frontend/src/
```

Expected: only `frontend/src/api/clubCoachPacks.ts` (deleted next step),
`frontend/src/pages/ClubCoachPacksPage.tsx`/`ClubCoachPackOpenPage.tsx`
(deleted in Task 6), and `frontend/src/admin/pages/AdminClubCoachPacksPage.tsx`
(deleted in Task 6) — if you see anything else, STOP and report
NEEDS_CONTEXT.

- [ ] **Step 4: Delete the coach-pack API client**

```bash
git rm frontend/src/api/clubCoachPacks.ts
```

- [ ] **Step 5: Remove the coach-pack admin API functions**

In `frontend/src/admin/api.ts`, find and remove `fetchAdminClubCoachPacks`,
`createClubCoachPack`, `updateClubCoachPack`, `deleteClubCoachPack`, and the
`ClubCoachPackAdmin` interface (all added in Coach Cards Phase 2's Task 13 —
grep for `ClubCoachPack` in this file to find their exact current lines).

- [ ] **Step 6: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: FAIL at this point — `ClubCoachPacksPage.tsx`,
`ClubCoachPackOpenPage.tsx`, and `AdminClubCoachPacksPage.tsx` still import
the types/functions you just deleted. This is expected; Task 6 deletes those
files. Note the failure in your report rather than trying to fix it here —
do not delete those page files yourself in this task, that's Task 6's job
and doing it here would blur the task boundary.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/cards/CardRevealStage.tsx frontend/src/admin/api.ts
git rm frontend/src/api/clubCoachPacks.ts
git commit -m "feat(club-packs): frontend types for the merged coach-in-pack-slot shape"
```

---

### Task 5: Frontend — `ClubPackOpenPage.tsx` mixed player/coach reveal flow

**Files:**
- Modify: `frontend/src/pages/ClubPackOpenPage.tsx`

**Interfaces:**
- Consumes: `OpenedClubPackItem` (Task 4); `RevealStage`/`STAGES`/
  `STAGE_DURATION_MS` (`CardRevealStage.tsx`, unchanged); `CoachRevealStage`/
  `COACH_STAGES`/`COACH_STAGE_DURATION_MS` (`CoachRevealStage.tsx`,
  unchanged, already built in Phase 2 — do not modify that file, it already
  has everything this task needs).
- Produces: nothing new for later tasks — this is a leaf page.

- [ ] **Step 1: Read the current file in full**

Already read this session (177 lines) — re-read it now to confirm nothing
has shifted, since you're about to rewrite most of it.

- [ ] **Step 2: Rewrite the file to branch on `kind` per opened item**

Replace `frontend/src/pages/ClubPackOpenPage.tsx` entirely:

```tsx
import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RevealStage, STAGES, STAGE_DURATION_MS } from "@/components/cards/CardRevealStage";
import { CoachRevealStage, COACH_STAGES, COACH_STAGE_DURATION_MS } from "@/components/cards/CoachRevealStage";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconCoin } from "@/components/icons";
import { openClubPack } from "@/api/clubPacks";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { ClubPackOpenResult, OpenedClubPackItem } from "@/types";

function stagesFor(item: OpenedClubPackItem) {
  return item.kind === "coach"
    ? { stages: COACH_STAGES as readonly string[], duration: COACH_STAGE_DURATION_MS }
    : { stages: STAGES as readonly string[], duration: STAGE_DURATION_MS };
}

export default function ClubPackOpenPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<"packshot" | "revealing" | "summary">("packshot");
  const [cardIndex, setCardIndex] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasStartedRef = useRef(false);
  const idempotencyKeyRef = useRef<string | null>(null);
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = `club-pack-${packId}-${crypto.randomUUID()}`;
  }

  const [requestState, setRequestState] = useState<
    { status: "pending" } | { status: "success"; data: ClubPackOpenResult } | { status: "error"; message: string }
  >({ status: "pending" });

  useEffect(() => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    openClubPack(Number(packId), idempotencyKeyRef.current!)
      .then((data) => setRequestState({ status: "success", data }))
      .catch((err: unknown) => {
        setRequestState({
          status: "error",
          message: err instanceof ApiRequestError ? err.message : "Не удалось открыть пак",
        });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const result = requestState.status === "success" ? requestState.data : null;
  const currentItem = result ? result.cards[cardIndex] : null;
  const currentStages = currentItem ? stagesFor(currentItem) : null;

  const advance = () => {
    if (!result || !currentStages) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (stageIndex < currentStages.stages.length - 1) setStageIndex((i) => i + 1);
  };

  const nextCard = () => {
    if (!result) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (cardIndex < result.cards.length - 1) {
      setCardIndex((i) => i + 1);
      setStageIndex(0);
      return;
    }
    hapticNotify("success");
    setPhase("summary");
  };

  useEffect(() => {
    if (phase !== "revealing" || !currentStages || stageIndex >= currentStages.stages.length - 1) return;
    timerRef.current = setTimeout(advance, currentStages.duration);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cardIndex, stageIndex, result]);

  const skipAll = () => {
    if (!result) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    haptic("light");
    setPhase("revealing");
    const lastIndex = result.cards.length - 1;
    setCardIndex(lastIndex);
    setStageIndex(stagesFor(result.cards[lastIndex]).stages.length - 1);
  };

  if (requestState.status === "pending") return <LoadingScreen />;
  if (requestState.status === "error") {
    return <ErrorScreen message={requestState.message} onRetry={() => navigate("/clubs/packs")} />;
  }
  if (!result || !currentItem || !currentStages) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      {phase !== "summary" && (
        <button
          onClick={skipAll}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
        >
          Пропустить всё
        </button>
      )}

      {phase === "packshot" && (
        <button
          onClick={() => { haptic("medium"); setPhase("revealing"); }}
          className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center"
        >
          <motion.img
            src={staticUrl(result.pack.image_path ?? undefined)}
            alt={result.pack.name}
            className="w-52 drop-shadow-2xl"
            animate={{ scale: [1, 1.04, 1], rotate: [0, -1.5, 1.5, 0] }}
            transition={{ repeat: Infinity, duration: 1.6 }}
          />
          <p className="font-display text-xl font-bold text-ink-chalk">{result.pack.name}</p>
          <p className="animate-pulse text-sm text-accent-lime">Нажми, чтобы открыть</p>
        </button>
      )}

      {phase === "revealing" && (
        <div className="flex flex-1 flex-col">
          {currentItem.kind === "coach" ? (
            <CoachRevealStage
              key={`${cardIndex}-${stageIndex}`}
              opened={{ card: { coach: currentItem.coach_card!.coach }, is_new: currentItem.is_new }}
              stage={COACH_STAGES[stageIndex] ?? COACH_STAGES[COACH_STAGES.length - 1]}
              index={cardIndex}
              total={result.cards.length}
              onTap={advance}
            />
          ) : (
            <RevealStage
              key={`${cardIndex}-${stageIndex}`}
              opened={{ card: { player: currentItem.card!.player }, is_new: currentItem.is_new }}
              stage={STAGES[stageIndex] ?? STAGES[STAGES.length - 1]}
              index={cardIndex}
              total={result.cards.length}
              onTap={advance}
            />
          )}
          {stageIndex === currentStages.stages.length - 1 && (
            <div className="safe-bottom px-6 pb-6 pt-2">
              <button
                onClick={nextCard}
                className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
              >
                {cardIndex < result.cards.length - 1 ? "Следующая карта" : "Готово"}
              </button>
            </div>
          )}
        </div>
      )}

      {phase === "summary" && (
        <div className="safe-bottom flex flex-1 flex-col gap-4 overflow-y-auto px-5 pb-6 pt-16">
          <h2 className="text-center font-display text-2xl font-bold text-ink-chalk">Пак открыт!</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {result.cards.map((item, i) =>
              item.kind === "coach" ? (
                <div key={`coach-${item.coach_card!.id}`} className="flex flex-col items-center gap-1 rounded-xl bg-bg-surface p-2">
                  <img
                    src={staticUrl(item.coach_card!.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                    alt={item.coach_card!.coach.display_name}
                    className="aspect-square w-full rounded-lg object-cover"
                  />
                  <span className="truncate text-[10px] font-semibold text-ink-chalk">{item.coach_card!.coach.display_name}</span>
                  <span className="text-[9px] font-bold text-accent-cyan">Тренер</span>
                  {item.is_new && <span className="text-[9px] font-bold text-accent-green">Новый!</span>}
                </div>
              ) : (
                <div key={`player-${item.card!.id}`} className="flex flex-col items-center gap-1 rounded-xl bg-bg-surface p-2">
                  <img
                    src={staticUrl(item.card!.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                    alt={item.card!.player.display_name}
                    className="aspect-square w-full rounded-lg object-cover"
                  />
                  <span className="truncate text-[10px] font-semibold text-ink-chalk">{item.card!.player.display_name}</span>
                  {item.is_new && <span className="text-[9px] font-bold text-accent-green">Новая!</span>}
                </div>
              )
            )}
          </div>
          <p className="flex items-center justify-center gap-1 text-sm text-ink-mist-dim">
            Новый бюджет клуба:
            <IconCoin size={14} className="text-accent-lime" />
            <span className="font-mono font-bold text-accent-lime">{result.new_budget}</span>
          </p>
          <button
            onClick={() => navigate("/clubs/packs")}
            className="mt-2 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
          >
            Готово
          </button>
        </div>
      )}
    </div>
  );
}
```

(The `i` parameter in the summary `.map((item, i) => ...)` is unused —
remove it if your linter flags it; kept here only if you find a genuine use
for it, otherwise use `.map((item) => ...)`.)

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS for this file specifically (the whole-project typecheck will
still fail on the files Task 6 hasn't deleted yet — that's fine, same as
Task 4's Step 6).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ClubPackOpenPage.tsx
git commit -m "feat(club-packs): mix coach reveals into the existing pack-opening flow"
```

---

### Task 6: Frontend — remove the dedicated coach-pack pages, add the admin field

**Files:**
- Delete: `frontend/src/pages/ClubCoachPacksPage.tsx`
- Delete: `frontend/src/pages/ClubCoachPackOpenPage.tsx`
- Delete: `frontend/src/admin/pages/AdminClubCoachPacksPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/admin/AdminLayout.tsx`
- Modify: `frontend/src/pages/ClubsPage.tsx`
- Modify: `frontend/src/admin/pages/AdminClubPacksPage.tsx`

**Interfaces:**
- Consumes: `ClubPack.coach_drop_chance` (Task 4).
- Produces: nothing new — this is cleanup + the admin form's new field.

- [ ] **Step 1: Delete the 3 dedicated coach-pack page files**

```bash
git rm frontend/src/pages/ClubCoachPacksPage.tsx frontend/src/pages/ClubCoachPackOpenPage.tsx frontend/src/admin/pages/AdminClubCoachPacksPage.tsx
```

- [ ] **Step 2: Remove their routes from `App.tsx`**

In `frontend/src/App.tsx`, remove:
- The 3 import lines: `AdminClubCoachPacksPage`, `ClubCoachPacksPage`,
  `ClubCoachPackOpenPage` (grep for `CoachPacksPage`/`CoachPackOpenPage` to
  find their exact current lines).
- `<Route path="club-coach-packs" element={<AdminClubCoachPacksPage />} />`
- `<Route path="/clubs/coach-packs" element={<ClubCoachPacksPage />} />`
- `<Route path="/clubs/coach-packs/:packId/open" element={<ClubCoachPackOpenPage />} />`

- [ ] **Step 3: Remove the admin nav entry**

In `frontend/src/admin/AdminLayout.tsx`, remove the line: `{ to:
"/admin/club-coach-packs", label: "Клубные паки тренеров", icon: "🧑‍🏫" }`.

- [ ] **Step 4: Remove the "Паки тренеров" entry point from `ClubsPage.tsx`**

In `frontend/src/pages/ClubsPage.tsx`, remove this whole block (currently
right after the "Клубные паки" button):

```tsx
      {isManager && (
        <button
          onClick={() => navigate("/clubs/coach-packs")}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconTools size={16} className="text-accent-lime" />
          Паки тренеров
        </button>
      )}
```

Check whether `IconTools` is still used elsewhere in this file after this
removal (grep `IconTools` in `ClubsPage.tsx`) — if this was its only use,
remove it from the import line too.

- [ ] **Step 5: Add `coach_drop_chance` to the club-pack admin form**

In `frontend/src/admin/pages/AdminClubPacksPage.tsx`:

Add the field to `ClubPackForm` (right after `card_count`):

```typescript
interface ClubPackForm {
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  coach_drop_chance: number;
  guaranteed_min_rarity: Rarity | "";
  probabilities: Record<Rarity, number>;
  is_active: boolean;
  image_path: string | null;
}
```

In `packToForm`, add a default and read the real value (form state holds it
as a 0-100 percentage for the same UX convention the rarity-probability
inputs already use, converted to 0-1 on submit):

```typescript
function packToForm(p?: ClubPack): ClubPackForm {
  const probabilities = { common: 0, rare: 0, epic: 0, legendary: 0, diamond: 0 } as Record<Rarity, number>;
  for (const rp of p?.rarity_probabilities ?? []) probabilities[rp.rarity as Rarity] = rp.probability * 100;
  return {
    slug: p?.slug ?? "", name: p?.name ?? "", description: p?.description ?? "",
    price: p?.price ?? 100, card_count: p?.card_count ?? 3,
    coach_drop_chance: (p?.coach_drop_chance ?? 0) * 100,
    guaranteed_min_rarity: (p?.guaranteed_min_rarity as Rarity) ?? "",
    probabilities, is_active: p?.is_active ?? true, image_path: p?.image_path ?? null,
  };
}
```

In `buildPayload`, add the field converted back to 0-1:

```typescript
  const buildPayload = () => ({
    slug: form.slug, name: form.name, description: form.description, price: form.price, card_count: form.card_count,
    coach_drop_chance: form.coach_drop_chance / 100,
    guaranteed_min_rarity: form.guaranteed_min_rarity || null,
    rarity_probabilities: RARITIES.filter((r) => form.probabilities[r] > 0).map((r) => ({ rarity: r, probability: form.probabilities[r] / 100 })),
    is_active: form.is_active,
  });
```

In the form's JSX, add a new input right after the "Карточек в паке" grid
(before the rarity-probabilities section):

```tsx
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Шанс тренера вместо игрока (%) — 0 = только игроки</span>
                <input
                  type="number" min={0} max={100} value={form.coach_drop_chance}
                  onChange={(e) => setForm({ ...form, coach_drop_chance: Number(e.target.value) })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              </label>
```

- [ ] **Step 6: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS — this is the last frontend file with a dangling reference to
the deleted coach-pack types/pages, so the whole-project typecheck should
now be fully clean (Task 7 adds new files but doesn't remove anything
already working).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(club-packs): remove dedicated coach-pack pages, add coach_drop_chance to the admin form"
```

---

### Task 7: Frontend — grid-based coach equip + skills-visible picker

**Files:**
- Create: `frontend/src/components/clubs/ClubCoachCardPickerModal.tsx`
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Consumes: `fetchClubCoachCards`, `setClubCoach`, `ClubCoachCard`,
  `EquippedCoach` (already exist, Coach Cards Phase 2 Tasks 10/11);
  `BOOST_TYPE_LABELS` (`@/lib/coaches`, already exists).
- Produces: nothing new for later tasks — leaf UI.

- [ ] **Step 1: Read `ClubCardPickerModal.tsx` and the current `ClubSquadPage.tsx` in full**

Both already read this session (61 and current-post-Task-11 lines
respectively) — re-read now to confirm nothing has shifted since.

- [ ] **Step 2: Create `ClubCoachCardPickerModal.tsx`, a direct structural mirror**

```tsx
import { AnimatePresence, motion } from "framer-motion";

import EmptyState from "@/components/common/EmptyState";
import { IconCollection } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { RARITY_LABELS } from "@/lib/rarity";
import type { ClubCoachCard } from "@/types";

interface Props {
  open: boolean;
  cards: ClubCoachCard[];
  onSelect: (card: ClubCoachCard | null) => void;
  onClose: () => void;
}

export default function ClubCoachCardPickerModal({ open, cards, onSelect, onClose }: Props) {
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
            {cards.length === 0 ? (
              <EmptyState icon={IconCollection} title="У клуба пока нет тренера" description="Открой клубные паки, чтобы получить тренера" />
            ) : (
              <div className="flex flex-col gap-2">
                {cards.map((c) => (
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

(A vertical list, not the player picker's `grid-cols-3` — a coach tile needs
room for its boosts line, which a 3-column grid tile is too narrow for.
`RARITY_LABELS` already exists in `@/lib/rarity`, same module the picker for
players uses.)

- [ ] **Step 3: Replace the `TacticSelect` coach dropdown with a grid cell**

In `frontend/src/pages/ClubSquadPage.tsx`:

Remove the `TacticSelect`-based "Тренер" row entirely (added in Coach Cards
Phase 2's Task 11 — grep for `label="Тренер"` to find its exact current
location) and the boosts-summary block below it (the `{lineup?.coach && (...
)}` block, also from Task 11 — this plan's new grid cell replaces both, the
boosts are now shown in-picker per Requirement 3 and directly under the grid
after equipping via the cell itself).

Add the import:

```typescript
import ClubCoachCardPickerModal from "@/components/clubs/ClubCoachCardPickerModal";
```

Add a `coachPickerOpen` state next to the existing `pickerSlot` state:

```typescript
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
```

Find the GK row inside the formation-grid `.map((category) => ...)` block
(the row where `category === "GK"`) and wrap it so the coach cell can sit to
its left while GK stays visually centered. The current row markup is:

```tsx
            <div key={category} className="relative flex justify-evenly gap-2">
              {lineup?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button ...>...</button>
                ))}
            </div>
```

Change it to special-case the GK row:

```tsx
            <div key={category} className="relative flex justify-evenly gap-2">
              {category === "GK" && (
                <button
                  onClick={canEdit ? () => setCoachPickerOpen(true) : undefined}
                  disabled={!canEdit || setCoachMutation.isPending}
                  className={`absolute left-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm ${
                    canEdit ? "active:scale-95" : ""
                  } ${setCoachMutation.isPending ? "opacity-60" : ""}`}
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
                      {canEdit ? (
                        <IconPlus size={16} className="text-ink-mist-dim" />
                      ) : (
                        <span className="flex h-[16px] items-center text-ink-mist-dim">—</span>
                      )}
                      <span className="text-[8px] text-ink-mist-dim">Тренер</span>
                    </>
                  )}
                </button>
              )}
              {lineup?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button ...>...</button>
                ))}
            </div>
```

(Leave the existing `.map((slot) => ...)` button body exactly as it already
is — only the new `category === "GK" && (...)` block above it is new. The
coach cell is `absolute left-0 top-0` inside the row's own `relative`
container, so it doesn't participate in the `justify-evenly` distribution
that keeps GK centered among the *other* GK-category slots — there is
normally exactly one GK slot, so `justify-evenly` with a single flex child
already centers it; the absolutely-positioned coach cell sits independently
in the same row without affecting that.)

Add the `setCoachMutation` (mirrors the existing `setLineupMutation`/
`setTacticsMutation` pattern already in this file) and the two queries it
needs, near the other queries/mutations at the top of the component:

```typescript
  const { data: coachCards } = useQuery({ queryKey: ["clubs", "coach-cards"], queryFn: fetchClubCoachCards, enabled: canEdit });
  const setCoachMutation = useMutation({
    mutationFn: setClubCoach,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup"] }); setCoachPickerOpen(false); },
    onError: (err) => setError(formatGameError(err, "Не удалось назначить тренера")),
  });
```

Add the modal render, next to the existing `{pickerSlot && (<ClubCardPickerModal .../>)}` block:

```tsx
      <ClubCoachCardPickerModal
        open={coachPickerOpen}
        cards={coachCards ?? []}
        onSelect={(card) => setCoachMutation.mutate(card ? card.id : null)}
        onClose={() => setCoachPickerOpen(false)}
      />
```

Add `fetchClubCoachCards`, `setClubCoach` to the existing `@/api/clubSquad`
import line (both already exist there from Phase 2's Task 10 — just add
them to this file's import if not already imported; check first, Task 11
may have already imported them for the dropdown version being removed).

Remove the `BOOST_TYPE_LABELS` import from this file if the deleted
boosts-summary block was its only use (check via grep before removing the
import — `ClubCoachCardPickerModal.tsx` now owns that display, not this
page).

- [ ] **Step 4: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: PASS.

- [ ] **Step 5: Verify live in the browser**

Start the dev stack if not already running (`docker compose up -d --build
frontend backend` — this repo's `docker-compose.override.yml`, if present,
replaces the frontend's dev command with a static `build && preview`, which
does not hot-reload; rebuild after this task's edits). Open `/clubs/squad`
as a club captain whose club owns at least one `ClubCoachCard` (use existing
test data from earlier this session, or open a `coach_drop_chance`-enabled
pack via the admin panel + player flow to mint a fresh one). Confirm: the GK
row shows a coach cell to its left, GK itself stays centered; tapping the
coach cell opens the new picker showing each owned coach's name, rarity, and
boosts; selecting one equips it and the cell updates to show the coach's
image; selecting "Без тренера" clears it; a non-manager viewing the page
sees no tappable coach cell (only whatever's equipped, non-interactive, per
this file's existing `canEdit` convention for every other cell).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/clubs/ClubCoachCardPickerModal.tsx frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(club-squad): equip the coach via a grid cell + skills-visible picker, not a dropdown"
```

---

### Task 8: Full verification pass

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: all pass except the one pre-existing, already-flagged, unrelated
failure this whole session has consistently seen
(`test_tasks.py::test_task_reward_pack_grants_all_cards`) — if you see any
other failure, stop and investigate before proceeding; do not wave it away
as "probably pre-existing" without checking.

- [ ] **Step 2: Run the full frontend typecheck and lint**

Run: `cd frontend && npm run typecheck` — expect PASS.
Run: `cd frontend && npm run lint` — this repo has a known, pre-existing,
unrelated `eslint.config.js`-missing failure (already flagged separately
this session) that makes this command fail outright regardless of your
changes; confirm the failure is that exact same pre-existing error, not a
new one introduced by this plan.

- [ ] **Step 3: Verify the full club-pack-to-equip flow live in the browser**

Using the running dev stack: as an admin, set an existing club pack's
`coach_drop_chance` to `1.0` via `/admin/club-packs` (confirm the new field
you added in Task 6 is there and works). As a club captain, open that pack
from `/clubs/packs` — confirm the reveal flow shows the shorter
rarity/silhouette/reveal coach sequence (not the longer 6-stage player
sequence) with boosts visible at reveal, the summary grid shows a "Тренер"
tag on the coach tile, and the budget updates correctly. Navigate to
`/clubs/squad` and confirm the newly-acquired coach is selectable via the
grid cell picker (Task 7), with boosts visible in the picker list itself.
Check the browser console for errors throughout.

- [ ] **Step 4: Confirm the migration chain is sound end-to-end**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest history` — confirm `0094` and `0095` both appear, in order, with no branching. (This plan does not attempt to fix the separate, already-flagged, pre-existing `0083`/`0090` fresh-DB migration ordering bug — don't re-investigate it here.)

- [ ] **Step 5: Report**

No commit for this task (verification only) — summarize the full pass/fail
state of Steps 1-4 for the controller.
