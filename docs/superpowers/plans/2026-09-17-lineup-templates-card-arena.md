# Lineup Templates — Phase 1: Card Arena Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Card Arena's personal `Lineup` moves from "one squad per user" to
"exactly 5 named templates per user, one active." Editing a non-active
template never locks its cards; activating a template recomputes
`UserCard.is_in_lineup` for exactly the cards that changed. Existing
`/lineups/active`-style endpoints keep working unmodified (they now mean
"whichever template is active"), so `match_service.py` and every other
consumer of `get_active_lineup` needs zero changes.

**Architecture:** Every `Lineup` row gains a `template_index` (1..5)
column; the DB enforces `(user_id, template_index)` uniqueness plus the
existing "at most one active per user" partial index. A lazy-seed helper
(`_ensure_templates`) creates any missing rows 1..5 on first read, mirroring
the existing single-row lazy-creation pattern. All existing service
functions gain an optional `template_index: int | None = None` parameter
(`None` = "the active one", preserving every existing call site
byte-for-byte); new functions handle listing, activating and renaming.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 +
TypeScript + TanStack Query (frontend), Alembic migration.

**Spec:** [docs/superpowers/specs/2026-09-17-lineup-templates-design.md](../specs/2026-09-17-lineup-templates-design.md)

## Global Constraints

- Exactly 5 templates per user, always — no create/delete API, lazily
  seeded on first read (see spec's "Shared Design" section).
- A card can sit in multiple templates simultaneously — no cross-template
  exclusivity check anywhere.
- `UserCard.is_in_lineup` reflects only the ACTIVE template's cards.
  Editing a non-active template never touches it.
- Existing endpoints (`GET/PUT /lineups/active`, `POST /lineups/tactic`,
  `PUT /lineups/coach`) must keep working with their current request/
  response shapes, now implicitly scoped to the active template.
- `match_service.py`'s `get_active_lineup(db, user)` / `get_active_lineup(db, opponent_user)`
  calls must work with no changes.

---

### Task 1: Migration — `template_index` column on `lineups`

**Files:**
- Create: `backend/alembic/versions/0116_lineup_templates.py`

**Interfaces:**
- Produces: a `lineups.template_index` Integer column (`NOT NULL`,
  `server_default='1'` — every existing row is exactly one user's single
  lineup today, so backfilling everyone to `template_index=1` is safe) and
  a `UniqueConstraint("user_id", "template_index")` named
  `uq_lineup_user_template`.

- [ ] **Step 1: Write the migration**

```python
"""Card Arena lineups become 5 named templates per user (template_index
1..5, one active) instead of a single row — templates 2-5 are lazily
created by lineup_service on first read, not backfilled here.

Revision ID: 0116
Revises: 0115
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0116"
down_revision: Union[str, None] = "0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lineups", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_lineup_user_template", "lineups", ["user_id", "template_index"])


def downgrade() -> None:
    op.drop_constraint("uq_lineup_user_template", "lineups", type_="unique")
    op.drop_column("lineups", "template_index")
```

- [ ] **Step 2: Apply it and verify**

Run: `docker compose exec backend alembic upgrade head`
Expected: `Running upgrade 0115 -> 0116, Card Arena lineups become 5 named templates...`

Then: `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\d lineups"` — confirm
`template_index` column and `uq_lineup_user_template` constraint are present.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0116_lineup_templates.py
git commit -m "feat(lineups): add template_index column for 5 saved squads per user"
```

---

### Task 2: Model — `Lineup.template_index`

**Files:**
- Modify: `backend/app/models/lineup.py`

**Interfaces:**
- Produces: `Lineup.template_index: int`.

- [ ] **Step 1: Add the column and constraint**

In `backend/app/models/lineup.py`, add `UniqueConstraint` to the existing
`sqlalchemy` import (it's already imported — verify) and add the field:

```python
class Lineup(TimestampMixin, Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1..5 — one of 5 fixed, always-present saved squads (see
    # lineup_service._ensure_templates). Not user-facing as a raw number;
    # the UI shows `name` and a 5-tab switcher.
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3")
    tactic: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True
    )

    cards: Mapped[list["LineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")
    user_coach_card: Mapped["UserCoachCard | None"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_lineup_user_template"),
        # Enforces "at most one active lineup per user" at the DB level —
        # lineup_service._ensure_templates does a check-then-insert with no
        # row to lock when a template doesn't exist yet, so without this,
        # two concurrent first-time requests could both seed template_index=1
        # as active. Still valid with 5 templates: "at most one active
        # among a user's rows" is unchanged, just now among 5 instead of 1.
        Index(
            "uq_lineup_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )
```

(Only the `template_index` field and its comment, and the new
`UniqueConstraint` line in `__table_args__`, are additions — everything
else in the class is unchanged from today.)

- [ ] **Step 2: Verify the app still imports cleanly**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/lineup.py
git commit -m "feat(lineups): add template_index to Lineup model"
```

---

### Task 3: Schemas — expose `template_index`/`name`/`is_active`, add rename request

**Files:**
- Modify: `backend/app/schemas/lineup.py`

**Interfaces:**
- Produces: `LineupOut.template_index: int`, `LineupOut.name: str`,
  `LineupOut.is_active: bool`, new `LineupRenameRequest`.

- [ ] **Step 1: Edit the schema**

```python
class LineupOut(BaseModel):
    id: Optional[int] = None
    template_index: int
    name: str
    is_active: bool
    formation: str
    tactic: str
    is_complete: bool
    team_strength: Optional[int] = None
    max_diamond: int
    coach: Optional[EquippedCoachOut] = None
    slots: list[LineupSlotOut]
```

(Insert `template_index`, `name`, `is_active` right after `id` — the rest
of the class is unchanged.)

Add at the end of the file:

```python
class LineupRenameRequest(BaseModel):
    name: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/lineup.py
git commit -m "feat(lineups): expose template_index/name/is_active on LineupOut"
```

---

### Task 4: Service — template listing, per-template edits, activation

**Files:**
- Modify: `backend/app/services/lineup_service.py`
- Test: `backend/tests/test_lineup_templates.py` (new)

**Interfaces:**
- Consumes: `Lineup`, `LineupCard` (Task 2), `LineupOut` (Task 3).
- Produces: `TEMPLATE_COUNT = 5`; `list_templates(db, user) -> list[LineupOut]`;
  `activate_template(db, user, template_index: int) -> LineupOut`;
  `rename_template(db, user, template_index: int, name: str) -> LineupOut`;
  `get_active_lineup(db, user, template_index: int | None = None) -> LineupOut`
  (signature grows an optional param, old 2-arg call sites unaffected);
  same optional-param growth for `set_tactic`, `set_lineup_coach`,
  `set_lineup`.

- [ ] **Step 1: Replace `_get_or_create_lineup` with `_ensure_templates` + row lookup**

In `backend/app/services/lineup_service.py`, replace the existing
`_active_lineup_query` / `_get_or_create_lineup` pair (lines 71-113) with:

```python
TEMPLATE_COUNT = 5
DEFAULT_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, TEMPLATE_COUNT + 1)}


def _templates_query(user_id: int):
    # populate_existing=True is required here for the same reason as
    # wallet_service.lock_user_for_update / club_squad_service._get_or_none_lineup:
    # the session's identity map may already hold one of these Lineup
    # objects from earlier in the request (e.g. set_lineup_coach re-fetching
    # after its own commit), and this app's session factory uses
    # expire_on_commit=False (see database.py), so a plain re-SELECT after
    # commit would silently return that stale cached object instead of what
    # this query actually just fetched.
    return (
        select(Lineup)
        .where(Lineup.user_id == user_id)
        .options(
            joinedload(Lineup.cards),
            joinedload(Lineup.user_coach_card).joinedload(UserCoachCard.coach).selectinload(Coach.boosts),
        )
        .order_by(Lineup.template_index)
        .execution_options(populate_existing=True)
    )


async def _ensure_templates(db: AsyncSession, user_id: int) -> list[Lineup]:
    """Lazily seeds any of the 5 fixed template slots that don't exist yet
    for this user — same lazy-singleton-row pattern as game_config_service
    .get_config and daily_reward_service.get_day_options, just seeding up
    to 5 rows instead of 1. A brand-new user gets all 5 on their first
    lineup-related request; an existing user (who already has their single
    pre-migration row at template_index=1) gets templates 2-5 filled in."""
    result = await db.execute(_templates_query(user_id))
    templates = list(result.unique().scalars().all())
    existing_indexes = {t.template_index for t in templates}
    missing = [i for i in range(1, TEMPLATE_COUNT + 1) if i not in existing_indexes]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        # A SAVEPOINT (not a full db.rollback()) so a lost race only undoes
        # this one failed insert batch — a plain rollback expires every
        # object in the session, including the caller's already-loaded
        # `user`, which then blows up with a greenlet error the next time
        # something touches it.
        async with db.begin_nested():
            for i in missing:
                db.add(Lineup(
                    user_id=user_id, template_index=i, name=DEFAULT_TEMPLATE_NAMES[i],
                    formation="4-3-3", is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent first-time request for this same
        # user (uq_lineup_user_template / uq_lineup_one_active_per_user) —
        # the winner's rows are what we want, not a second set.
        pass

    result = await db.execute(_templates_query(user_id))
    return list(result.unique().scalars().all())


async def _get_template_row(db: AsyncSession, user_id: int, template_index: int | None) -> Lineup:
    templates = await _ensure_templates(db, user_id)
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)
```

- [ ] **Step 2: Add `list_templates` and update `get_active_lineup` to serialize any row**

Replace `get_active_lineup` (existing lines 178-221) with a two-function
split — a row serializer plus the public per-template/active accessors:

```python
async def _serialize_lineup(db: AsyncSession, lineup: Lineup) -> LineupOut:
    result = await db.execute(select(LineupCard).where(LineupCard.lineup_id == lineup.id))
    lineup_cards = result.scalars().all()

    card_ids = [lc.user_card_id for lc in lineup_cards]
    cards_by_id: dict[int, UserCard] = {}
    if card_ids:
        cards_result = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )
        cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}

    by_slot_code = {lc.slot_code: cards_by_id.get(lc.user_card_id) for lc in lineup_cards}

    slots_out = []
    cards_with_slots = []
    for slot in FORMATION_SLOTS:
        card = by_slot_code.get(slot.code)
        slots_out.append(
            LineupSlotOut(slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value, card=card)
        )
        if card is not None:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(FORMATION_SLOTS)
    coach = lineup.user_coach_card.coach if lineup.user_coach_card else None
    strength = calculate_base_strength(cards_with_slots, coach=coach, tactic=lineup.tactic) if is_complete else None
    config = await get_config(db)

    return LineupOut(
        id=lineup.id, template_index=lineup.template_index, name=lineup.name, is_active=lineup.is_active,
        formation=lineup.formation, tactic=lineup.tactic, is_complete=is_complete,
        team_strength=strength, max_diamond=config.match_max_diamond_cards,
        coach=EquippedCoachOut(
            id=coach.id, display_name=coach.display_name, rarity=coach.rarity.value,
            image_path=coach.image_path, boosts=coach.boosts,
        ) if coach else None,
        slots=slots_out,
    )


async def get_active_lineup(db: AsyncSession, user: User, template_index: int | None = None) -> LineupOut:
    lineup = await _get_template_row(db, user.id, template_index)
    return await _serialize_lineup(db, lineup)


async def list_templates(db: AsyncSession, user: User) -> list[LineupOut]:
    templates = await _ensure_templates(db, user.id)
    return [await _serialize_lineup(db, t) for t in templates]
```

- [ ] **Step 3: Update `set_tactic` and `set_lineup_coach` to take an optional `template_index`**

```python
async def set_tactic(db: AsyncSession, user: User, tactic: str, template_index: int | None = None) -> LineupOut:
    if tactic not in TACTIC_MULTIPLIERS:
        raise ConflictError(f"Unknown tactic: {tactic}")
    lineup = await _get_template_row(db, user.id, template_index)
    lineup.tactic = tactic
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)


async def set_lineup_coach(
    db: AsyncSession, user: User, payload: LineupCoachSetRequest, template_index: int | None = None
) -> LineupOut:
    lineup = await _get_template_row(db, user.id, template_index)
    if payload.user_coach_card_id is not None:
        card = await db.get(UserCoachCard, payload.user_coach_card_id)
        if card is None or card.user_id != user.id:
            raise ConflictError("Тренер не найден в вашей коллекции")
    lineup.user_coach_card_id = payload.user_coach_card_id
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)


async def rename_template(db: AsyncSession, user: User, template_index: int, name: str) -> LineupOut:
    if not name.strip():
        raise ConflictError("Название не может быть пустым")
    lineup = await _get_template_row(db, user.id, template_index)
    lineup.name = name.strip()[:64]
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, template_index)
```

- [ ] **Step 4: Update `set_lineup` to take an optional `template_index` and only lock cards when editing the active template**

Replace the body of `set_lineup` (existing lines 248-330) — the
validation logic (slot/card/position/duplicate-player/diamond-cap checks)
is unchanged; only the row lookup and the locking guard change:

```python
async def set_lineup(
    db: AsyncSession, user: User, payload: LineupSetRequest, template_index: int | None = None
) -> LineupOut:
    slot_codes_seen = set()
    card_ids_seen = set()
    for slot_in in payload.slots:
        if slot_in.slot_code not in SLOTS_BY_CODE:
            raise ConflictError(f"Unknown formation slot: {slot_in.slot_code}")
        if slot_in.slot_code in slot_codes_seen:
            raise ConflictError(f"Duplicate slot in request: {slot_in.slot_code}")
        if slot_in.user_card_id in card_ids_seen:
            raise ConflictError("The same card instance cannot fill two slots")
        slot_codes_seen.add(slot_in.slot_code)
        card_ids_seen.add(slot_in.user_card_id)

    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(card_ids_seen)).options(joinedload(UserCard.player))
    )
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}
    if len(cards_by_id) != len(card_ids_seen):
        raise NotFoundError("One or more cards not found")

    player_ids_seen: set[int] = set()
    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        slot = SLOTS_BY_CODE[slot_in.slot_code]
        if card.owner_id != user.id:
            raise ForbiddenError("You can only use your own cards in your lineup")
        if card.is_locked_by_admin or card.is_locked_in_trade:
            raise ConflictError(f"Card #{card.serial_number} is locked and cannot be used in a lineup")
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(
                f"Player {card.player.display_name} ({card.player.position.value}) cannot fill a {slot.category} slot"
            )
        if card.player_id in player_ids_seen:
            raise ConflictError(
                f"Player {card.player.display_name} is already assigned to another slot; even duplicate copies can't fill two slots"
            )
        player_ids_seen.add(card.player_id)

    config = await get_config(db)
    diamond_count = sum(1 for card in cards_by_id.values() if card.player.rarity == Rarity.diamond)
    if diamond_count > config.match_max_diamond_cards:
        raise ConflictError(f"Максимум {config.match_max_diamond_cards} диамантовых карт в составе")

    lineup = await _get_template_row(db, user.id, template_index)

    # Locks the lineup row so two overlapping PUTs for the same template
    # (e.g. tapping a second slot before the first pick's request has
    # returned) serialize instead of racing — see set_lineup's original
    # comment (this behavior is unchanged, just scoped to one template row
    # instead of the user's only row).
    await db.execute(select(Lineup).where(Lineup.id == lineup.id).with_for_update(of=Lineup))

    old_result = await db.execute(select(LineupCard).where(LineupCard.lineup_id == lineup.id))
    old_lineup_cards = old_result.scalars().all()
    old_card_ids = [lc.user_card_id for lc in old_lineup_cards]

    # Trade/upgrade locking reflects only the ACTIVE template — editing a
    # template that isn't currently active must never touch is_in_lineup on
    # any card (per design: cards parked in inactive templates stay freely
    # tradeable).
    if lineup.is_active and old_card_ids:
        old_cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(old_card_ids)))
        for c in old_cards_result.scalars().all():
            c.is_in_lineup = False
            db.add(c)
    for lc in old_lineup_cards:
        await db.delete(lc)
    await db.flush()

    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        if lineup.is_active:
            card.is_in_lineup = True
            db.add(card)
        db.add(LineupCard(lineup_id=lineup.id, user_card_id=card.id, slot_code=slot_in.slot_code))

    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)
```

- [ ] **Step 5: Add `activate_template`**

Append to the end of the file:

```python
async def activate_template(db: AsyncSession, user: User, template_index: int) -> LineupOut:
    """Switches which of the user's 5 templates is active, recomputing
    UserCard.is_in_lineup for exactly the cards whose lock status changes:
    cards exclusive to the old active template are unlocked, cards in the
    new active template are locked, and cards present in BOTH stay locked
    throughout (computed as a set difference before any writes, so there's
    no window where a shared card is momentarily unlocked)."""
    templates = await _ensure_templates(db, user.id)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    new_active = next(t for t in templates if t.template_index == template_index)
    old_active = next((t for t in templates if t.is_active), None)

    if old_active is not None and old_active.id == new_active.id:
        return await get_active_lineup(db, user, template_index)

    lock_ids = [t.id for t in (old_active, new_active) if t is not None]
    await db.execute(select(Lineup).where(Lineup.id.in_(lock_ids)).with_for_update(of=Lineup))

    old_card_ids: set[int] = set()
    if old_active is not None:
        old_result = await db.execute(select(LineupCard.user_card_id).where(LineupCard.lineup_id == old_active.id))
        old_card_ids = set(old_result.scalars().all())
    new_result = await db.execute(select(LineupCard.user_card_id).where(LineupCard.lineup_id == new_active.id))
    new_card_ids = set(new_result.scalars().all())

    to_unlock = old_card_ids - new_card_ids
    to_lock = new_card_ids - old_card_ids
    touched_ids = to_unlock | to_lock
    if touched_ids:
        cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(touched_ids)))
        for card in cards_result.scalars().all():
            card.is_in_lineup = card.id in to_lock
            db.add(card)

    if old_active is not None:
        old_active.is_active = False
        db.add(old_active)
    new_active.is_active = True
    db.add(new_active)

    await db.commit()
    return await get_active_lineup(db, user, template_index)
```

- [ ] **Step 6: Run existing tests to confirm nothing broke**

Run: `docker compose exec backend pytest tests/test_lineups_matches.py tests/test_lineup_coach.py -v`
Expected: all pass unchanged (they call `get_active_lineup`/`set_lineup`/
`set_tactic`/`set_lineup_coach` positionally without `template_index`,
which still means "the active template").

- [ ] **Step 7: Write new template tests**

Create `backend/tests/test_lineup_templates.py`:

```python
from app.models.card import UserCard
from app.models.enums import CardSource
from app.schemas.lineup import LineupSetRequest, LineupSlotIn, LineupTacticRequest
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS, TEMPLATE_COUNT, activate_template, get_active_lineup, list_templates, rename_template, set_lineup
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _build_full_squad(db_session, user_id: int) -> list[LineupSlotIn]:
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append(LineupSlotIn(slot_code=slot.code, user_card_id=card.id))
    return slots


async def test_five_templates_lazily_created_on_first_read(client, db_session, bot_token):
    headers = telegram_headers(850001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850001)

    templates = await list_templates(db_session, user)
    assert len(templates) == TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    assert templates[1].name == "Шаблон 2"


async def test_editing_inactive_template_does_not_lock_cards(client, db_session, bot_token):
    headers = telegram_headers(850002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850002)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=2)

    for slot in slots:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is False


async def test_editing_active_template_locks_cards(client, db_session, bot_token):
    headers = telegram_headers(850003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850003)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots))  # template_index=None -> active (1)

    for slot in slots:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is True


async def test_same_card_can_be_saved_into_two_templates(client, db_session, bot_token):
    headers = telegram_headers(850004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850004)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=1)
    result = await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=2)
    assert result.is_complete is True


async def test_activate_template_moves_lock_to_new_cards_only(client, db_session, bot_token):
    headers = telegram_headers(850005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850005)

    slots_1 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_1), template_index=1)

    slots_2 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_2), template_index=2)

    await activate_template(db_session, user, 2)

    for slot in slots_1:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is False
    for slot in slots_2:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is True


async def test_activate_template_keeps_shared_card_locked_throughout(client, db_session, bot_token):
    headers = telegram_headers(850006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850006)

    slots_1 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_1), template_index=1)

    # Template 2 reuses slots_1's goalkeeper (shared card) plus a fresh XI
    # for the rest.
    slots_2 = await _build_full_squad(db_session, user.id)
    slots_2[0] = slots_1[0]
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_2), template_index=2)

    await activate_template(db_session, user, 2)

    shared_card = await db_session.get(UserCard, slots_1[0].user_card_id)
    assert shared_card.is_in_lineup is True


async def test_rename_template(client, db_session, bot_token):
    headers = telegram_headers(850007, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850007)

    result = await rename_template(db_session, user, 3, "Оборонительный")
    assert result.name == "Оборонительный"
    templates = await list_templates(db_session, user)
    assert templates[2].name == "Оборонительный"


async def test_get_active_lineup_with_no_args_still_returns_active_template(client, db_session, bot_token):
    headers = telegram_headers(850008, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850008)

    await activate_template(db_session, user, 3)
    result = await get_active_lineup(db_session, user)
    assert result.template_index == 3
    assert result.is_active is True
```

Run: `docker compose exec backend pytest tests/test_lineup_templates.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/lineup_service.py backend/tests/test_lineup_templates.py
git commit -m "feat(lineups): add 5-template listing, per-template edits, and activation"
```

---

### Task 5: Router — template endpoints

**Files:**
- Modify: `backend/app/routers/lineups.py`

**Interfaces:**
- Consumes: `list_templates`, `activate_template`, `rename_template`,
  updated `set_lineup`/`set_tactic`/`set_lineup_coach` (Task 4).
- Produces: `GET /lineups/templates`, `PUT /lineups/templates/{template_index}`,
  `POST /lineups/templates/{template_index}/tactic`,
  `PUT /lineups/templates/{template_index}/coach`,
  `PUT /lineups/templates/{template_index}/name`,
  `POST /lineups/templates/{template_index}/activate`.

- [ ] **Step 1: Add the new routes**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.lineup import (
    LineupCoachSetRequest, LineupOut, LineupRenameRequest, LineupSetRequest, LineupTacticRequest, UserCoachCardOut,
)
from app.services.lineup_service import (
    activate_template, get_active_lineup, list_templates, list_user_coach_cards, rename_template,
    set_lineup, set_lineup_coach, set_tactic,
)

router = APIRouter(prefix="/lineups", tags=["lineups"])


@router.get("/active", response_model=LineupOut)
async def read_active_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_active_lineup(db, user)


@router.get("/coach-cards", response_model=list[UserCoachCardOut])
async def read_user_coach_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_user_coach_cards(db, user)


@router.put("/active", response_model=LineupOut)
async def update_active_lineup(
    payload: LineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup(db, user, payload)


@router.post("/tactic", response_model=LineupOut)
async def update_tactic(
    payload: LineupTacticRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_tactic(db, user, payload.tactic)


@router.put("/coach", response_model=LineupOut)
async def update_lineup_coach(
    payload: LineupCoachSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup_coach(db, user, payload)


@router.get("/templates", response_model=list[LineupOut])
async def read_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_templates(db, user)


@router.put("/templates/{template_index}", response_model=LineupOut)
async def update_template(
    template_index: int, payload: LineupSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_lineup(db, user, payload, template_index)


@router.post("/templates/{template_index}/tactic", response_model=LineupOut)
async def update_template_tactic(
    template_index: int, payload: LineupTacticRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_tactic(db, user, payload.tactic, template_index)


@router.put("/templates/{template_index}/coach", response_model=LineupOut)
async def update_template_coach(
    template_index: int, payload: LineupCoachSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_lineup_coach(db, user, payload, template_index)


@router.put("/templates/{template_index}/name", response_model=LineupOut)
async def update_template_name(
    template_index: int, payload: LineupRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await rename_template(db, user, template_index, payload.name)


@router.post("/templates/{template_index}/activate", response_model=LineupOut)
async def activate_template_route(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await activate_template(db, user, template_index)
```

- [ ] **Step 2: Run the full lineup test suite plus a manual smoke check**

Run: `docker compose exec backend pytest tests/test_lineups_matches.py tests/test_lineup_coach.py tests/test_lineup_templates.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/lineups.py
git commit -m "feat(lineups): add template list/edit/activate/rename endpoints"
```

---

### Task 6: Frontend — types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/lineups.ts`

**Interfaces:**
- Produces: `Lineup.template_index`, `Lineup.name`, `Lineup.is_active`;
  `fetchLineupTemplates`, `setLineupTemplate`, `setLineupTemplateTactic`,
  `setLineupTemplateCoach`, `renameLineupTemplate`, `activateLineupTemplate`.

- [ ] **Step 1: Extend the `Lineup` type**

In `frontend/src/types/index.ts`, find `export interface Lineup { ... }`
and add three fields:

```typescript
export interface Lineup {
  id: number | null;
  template_index: number;
  name: string;
  is_active: boolean;
  formation: string;
  tactic: LineupTactic;
  is_complete: boolean;
  team_strength: number | null;
  max_diamond: number;
  coach: EquippedCoach | null;
  slots: LineupSlot[];
}
```

- [ ] **Step 2: Add the new API functions**

```typescript
import { api } from "@/lib/api";
import type { Lineup, LineupTactic, UserCoachCard } from "@/types";

export async function fetchActiveLineup(): Promise<Lineup> {
  const { data } = await api.get<Lineup>("/lineups/active");
  return data;
}

export async function setActiveLineup(slots: { slot_code: string; user_card_id: number }[]): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/active", { slots });
  return data;
}

export async function setLineupTactic(tactic: LineupTactic): Promise<Lineup> {
  const { data } = await api.post<Lineup>("/lineups/tactic", { tactic });
  return data;
}

export async function setLineupCoach(userCoachCardId: number | null): Promise<Lineup> {
  const { data } = await api.put<Lineup>("/lineups/coach", { user_coach_card_id: userCoachCardId });
  return data;
}

export async function fetchUserCoachCards(): Promise<UserCoachCard[]> {
  const { data } = await api.get<UserCoachCard[]>("/lineups/coach-cards");
  return data;
}

export async function fetchLineupTemplates(): Promise<Lineup[]> {
  const { data } = await api.get<Lineup[]>("/lineups/templates");
  return data;
}

export async function setLineupTemplate(
  templateIndex: number, slots: { slot_code: string; user_card_id: number }[],
): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}`, { slots });
  return data;
}

export async function setLineupTemplateTactic(templateIndex: number, tactic: LineupTactic): Promise<Lineup> {
  const { data } = await api.post<Lineup>(`/lineups/templates/${templateIndex}/tactic`, { tactic });
  return data;
}

export async function setLineupTemplateCoach(templateIndex: number, userCoachCardId: number | null): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}/coach`, { user_coach_card_id: userCoachCardId });
  return data;
}

export async function renameLineupTemplate(templateIndex: number, name: string): Promise<Lineup> {
  const { data } = await api.put<Lineup>(`/lineups/templates/${templateIndex}/name`, { name });
  return data;
}

export async function activateLineupTemplate(templateIndex: number): Promise<Lineup> {
  const { data } = await api.post<Lineup>(`/lineups/templates/${templateIndex}/activate`);
  return data;
}
```

(The five original functions are unchanged — kept for any other future
caller, though `ArenaPage.tsx` moves off them in Task 7.)

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors (nothing consumes the new fields/functions yet, so
this only validates the additions themselves compile).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/lineups.ts
git commit -m "feat(lineups): add template-scoped API client functions"
```

---

### Task 7: Frontend — template switcher on `ArenaPage.tsx`

**Files:**
- Modify: `frontend/src/pages/ArenaPage.tsx`

**Interfaces:**
- Consumes: `fetchLineupTemplates`, `setLineupTemplate`,
  `setLineupTemplateTactic`, `setLineupTemplateCoach`,
  `activateLineupTemplate`, `renameLineupTemplate` (Task 6).

- [ ] **Step 1: Replace the single-lineup query with a templates query + selected-index state**

In `ArenaPage.tsx`, replace:

```typescript
  const { data: lineup, isLoading: lineupLoading } = useQuery({ queryKey: ["lineup"], queryFn: fetchActiveLineup });
```

with:

```typescript
  const { data: templates, isLoading: lineupLoading } = useQuery({ queryKey: ["lineup-templates"], queryFn: fetchLineupTemplates });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const lineup = templates?.find((t) => t.template_index === viewedIndex);
```

Update the import line to pull the new functions instead of the old
single-lineup ones:

```typescript
import {
  activateLineupTemplate, fetchLineupTemplates, fetchUserCoachCards,
  renameLineupTemplate, setLineupTemplate, setLineupTemplateCoach, setLineupTemplateTactic,
} from "@/api/lineups";
```

- [ ] **Step 2: Scope the three mutations to `viewedIndex`, invalidate the new query key**

Replace the three mutation declarations:

```typescript
  const setLineupMutation = useMutation({
    mutationFn: (slots: { slot_code: string; user_card_id: number }[]) => setLineupTemplate(viewedIndex, slots),
    onSuccess: () => { setLineupError(null); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticMutation = useMutation({
    mutationFn: (tactic: LineupTactic) => setLineupTemplateTactic(viewedIndex, tactic),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }),
  });

  const setCoachMutation = useMutation({
    mutationFn: (userCoachCardId: number | null) => setLineupTemplateCoach(viewedIndex, userCoachCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); setCoachPickerOpen(false); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось назначить тренера")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateLineupTemplate(viewedIndex),
    onSuccess: () => { haptic("medium"); queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }); },
    onError: (err) => setLineupError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const renameMutation = useMutation({
    mutationFn: (name: string) => renameLineupTemplate(viewedIndex, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup-templates"] }),
  });
```

Add the `LineupTactic` type to the existing `import type { ... } from "@/types"` line.

- [ ] **Step 3: Add the 5-tab template switcher above the formation section**

Immediately after the `{lineupError && ...}` block and before
`<section className="rounded-2xl bg-bg-surface p-4">` (the formation
section), insert:

```tsx
      <section className="flex gap-1.5 overflow-x-auto pb-1">
        {(templates ?? []).map((t) => (
          <button
            key={t.template_index}
            onClick={() => setSelectedIndex(t.template_index)}
            className={`flex shrink-0 flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 ${
              t.template_index === viewedIndex ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <span className="whitespace-nowrap text-[11px] font-bold">{t.name}</span>
            {t.is_active && (
              <span className={`text-[8px] ${t.template_index === viewedIndex ? "text-bg-base/70" : "text-accent-lime"}`}>
                Активный
              </span>
            )}
          </button>
        ))}
      </section>

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Сделать «${lineup?.name}» активным для матчей`}
        </button>
      )}
```

- [ ] **Step 4: Wire up the mutation call sites that changed shape**

`setTacticMutation.mutate(t.value)` and `setCoachMutation.mutate(card ? card.id : null)`
already pass the right single argument (tactic string / coach id) to the
now-differently-implemented mutations — no call-site change needed there.
`assignSlot`'s `setLineupMutation.mutateAsync(currentSlots)` also already
passes just the slots array — no change needed.

- [ ] **Step 5: Typecheck and lint**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Live verification**

Rebuild the frontend container (`docker compose up -d --build frontend` —
this repo's override disables hot-reload, see CLAUDE.md) and, in the
Browser pane:
1. Open `/play` → Card Arena, confirm 5 template pills render, first one
   marked "Активный".
2. Build a full XI on template 1 (activates cards → verify via collection
   page that those cards show as "in lineup"/non-tradeable).
3. Switch to template 2 pill, build a different full XI there — confirm
   template 1's cards are NOT required to be different (a shared card is
   allowed) and that template 2's cards do NOT show as locked yet.
4. Tap "Сделать активным" on template 2 — confirm template 1's
   exclusive cards become unlocked and template 2's become locked; a
   card present in both stays locked throughout (spot-check its
   collection page state right after the switch).
5. Play a match — confirm it now uses template 2's squad/tactic/coach
   (whichever is active), matching pre-existing single-lineup behavior.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ArenaPage.tsx
git commit -m "feat(lineups): add 5-template switcher to Card Arena"
```

---

## Definition of Done (Phase 1)

- All 8 new backend tests pass; `test_lineups_matches.py` and
  `test_lineup_coach.py` pass unmodified.
- `npm run typecheck` clean.
- Live-verified: template switcher renders, per-template editing doesn't
  lock inactive cards, activation correctly moves the lock (including the
  shared-card case), and playing a match still uses the active template.
- Nothing committed/pushed beyond what the user explicitly asks for next.
