# Lineup Templates — Phase 2: Тактико Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `TacticoSquad` moves from "one squad per user" to "exactly 5 named
templates per user, one active" — mirrors Phase 1 (Card Arena) exactly,
minus formation/tactic/coach (Тактико has none, per design Q&A: nothing
new is added there). Existing `GET/PUT /tactico/squad` keep meaning "the
active template," so every match-start path (`tactico_service.py:350-357,
391-393, 453-455, 525-527, 591-592, 1122, 1257-1258`) needs zero changes.

**Architecture:** Identical pattern to Phase 1: `TacticoSquad` gains
`template_index` (1..5) + `name` + `is_active`; `_ensure_squad_templates`
lazily seeds missing rows; `get_squad`/`set_squad` grow an optional
`template_index: int | None = None` param; new `list_squad_templates`,
`rename_squad_template`, `activate_squad_template`.

**Spec:** [docs/superpowers/specs/2026-09-17-lineup-templates-design.md](../specs/2026-09-17-lineup-templates-design.md)

## Global Constraints

- Same as Phase 1: exactly 5 templates always, lazily seeded; a card can
  sit in multiple templates; `is_in_tactico_squad` reflects only the
  active template; no new tactics/formation concept for Тактико.
- All 9 existing `get_squad(db, user)`/`get_squad(db, sender)` call sites
  in `tactico_service.py` must keep working unchanged.

---

### Task 1: Migration — template columns on `tactico_squads`

**Files:**
- Create: `backend/alembic/versions/0117_tactico_squad_templates.py`

- [ ] **Step 1: Write the migration**

```python
"""Тактико squads become 5 named templates per user (template_index 1..5,
one active) instead of a single row, mirroring migration 0116's Card
Arena change. Templates 2-5 are lazily created by tactico_service on
first read, not backfilled here.

Revision ID: 0117
Revises: 0116
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0117"
down_revision: Union[str, None] = "0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tactico_squads", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tactico_squads", sa.Column("name", sa.String(length=64), nullable=False, server_default="Основной состав"))
    op.add_column("tactico_squads", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.drop_constraint("uq_tactico_squads_user_id", "tactico_squads", type_="unique")
    op.create_unique_constraint("uq_tactico_squad_user_template", "tactico_squads", ["user_id", "template_index"])
    op.create_index(
        "uq_tactico_squad_one_active_per_user", "tactico_squads", ["user_id"], unique=True,
        postgresql_where=sa.text("is_active"), sqlite_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_tactico_squad_one_active_per_user", table_name="tactico_squads")
    op.drop_constraint("uq_tactico_squad_user_template", "tactico_squads", type_="unique")
    op.create_unique_constraint("uq_tactico_squads_user_id", "tactico_squads", ["user_id"])
    op.drop_column("tactico_squads", "is_active")
    op.drop_column("tactico_squads", "name")
    op.drop_column("tactico_squads", "template_index")
```

- [ ] **Step 2: Confirm the existing unique constraint's real name before applying**

The model declares `user_id: Mapped[int] = mapped_column(..., unique=True, ...)`
(a column-level `unique=True`, not a named `UniqueConstraint`) — Postgres
auto-names this `uq_tactico_squads_user_id`. Verify before running:

Run: `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\d tactico_squads"`
Expected: a unique constraint on `user_id` — note its exact name; if it
differs from `uq_tactico_squads_user_id`, update the migration's
`drop_constraint`/`create_unique_constraint` calls to match before
proceeding.

- [ ] **Step 3: Apply and verify**

Run: `docker compose exec backend alembic upgrade head`
Expected: `Running upgrade 0116 -> 0117, Тактико squads become 5 named templates...`

Run: `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\d tactico_squads"`
Expected: `template_index`, `name`, `is_active` columns present;
`uq_tactico_squad_user_template` and `uq_tactico_squad_one_active_per_user`
present; old plain `user_id` unique constraint gone.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0117_tactico_squad_templates.py
git commit -m "feat(tactico): add template columns to tactico_squads"
```

---

### Task 2: Model — `TacticoSquad` template fields

**Files:**
- Modify: `backend/app/models/tactico.py`

- [ ] **Step 1: Edit the model**

```python
class TacticoSquad(TimestampMixin, Base):
    __tablename__ = "tactico_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1..5 — mirrors Lineup.template_index (see lineup.py) exactly; one of
    # 5 fixed, always-present saved squads (see
    # tactico_service._ensure_squad_templates).
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cards: Mapped[list["TacticoSquadCard"]] = relationship(back_populates="squad", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_tactico_squad_user_template"),
        Index(
            "uq_tactico_squad_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )
```

(Remove the old bare `unique=True` on `user_id` — replaced by the two
constraints above. Update the imports at the top of the file to add
`Boolean, Index, UniqueConstraint, text` to the existing `sqlalchemy`
import and `TimestampMixin` to the existing `app.models.mixins` import —
check what's already imported there and add only what's missing.)

- [ ] **Step 2: Verify the app still imports cleanly**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/tactico.py
git commit -m "feat(tactico): add template_index/name/is_active to TacticoSquad"
```

---

### Task 3: Schema — expose template fields, add rename request

**Files:**
- Modify: `backend/app/schemas/tactico.py`

- [ ] **Step 1: Edit `TacticoSquadOut`, add `TacticoSquadRenameRequest`**

```python
class TacticoSquadOut(BaseModel):
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    cards: list[UserCardOut]
    max_legendary: int
    max_epic: int
    max_diamond: int


class TacticoSquadSetRequest(BaseModel):
    user_card_ids: list[int]


class TacticoSquadRenameRequest(BaseModel):
    name: str
```

(Only `template_index`/`name`/`is_active` are new fields on
`TacticoSquadOut`, inserted before `is_complete`; `TacticoSquadRenameRequest`
is new, added after the existing `TacticoSquadSetRequest`.)

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/tactico.py
git commit -m "feat(tactico): expose template fields on TacticoSquadOut"
```

---

### Task 4: Service — template listing, per-template edits, activation

**Files:**
- Modify: `backend/app/services/tactico_service.py`
- Test: `backend/tests/test_tactico_squad_templates.py` (new)

- [ ] **Step 1: Replace `_get_or_create_squad` with `_ensure_squad_templates` + row lookup**

Replace `_get_or_create_squad` (existing lines 59-66) with:

```python
SQUAD_TEMPLATE_COUNT = 5
DEFAULT_SQUAD_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, SQUAD_TEMPLATE_COUNT + 1)}


def _squad_templates_query(user_id: int):
    return select(TacticoSquad).where(TacticoSquad.user_id == user_id).order_by(TacticoSquad.template_index)


async def _ensure_squad_templates(db: AsyncSession, user_id: int) -> list[TacticoSquad]:
    """Lazily seeds any of the 5 fixed template slots that don't exist yet
    for this user — same pattern as lineup_service._ensure_templates."""
    result = await db.execute(_squad_templates_query(user_id))
    templates = list(result.scalars().all())
    existing_indexes = {t.template_index for t in templates}
    missing = [i for i in range(1, SQUAD_TEMPLATE_COUNT + 1) if i not in existing_indexes]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        async with db.begin_nested():
            for i in missing:
                db.add(TacticoSquad(
                    user_id=user_id, template_index=i, name=DEFAULT_SQUAD_TEMPLATE_NAMES[i],
                    is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        pass

    result = await db.execute(_squad_templates_query(user_id))
    return list(result.scalars().all())


async def _get_squad_template_row(db: AsyncSession, user_id: int, template_index: int | None) -> TacticoSquad:
    templates = await _ensure_squad_templates(db, user_id)
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= SQUAD_TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {SQUAD_TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)
```

- [ ] **Step 2: Split `get_squad` into a row-serializer + public accessors**

Replace `get_squad` (existing lines 69-91) with:

```python
async def _serialize_squad(db: AsyncSession, squad: TacticoSquad) -> TacticoSquadOut:
    config = await get_config(db)
    result = await db.execute(select(TacticoSquadCard).where(TacticoSquadCard.squad_id == squad.id))
    squad_cards = result.scalars().all()
    card_ids = [sc.user_card_id for sc in squad_cards]
    cards: list[UserCard] = []
    if card_ids:
        cards_result = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )
        # Filters out cards that left the user's ownership since being
        # squadded (e.g. an older squad set before is_in_tactico_squad
        # locking existed, since traded away) instead of surfacing a
        # phantom card the frontend can neither render nor deselect —
        # is_complete correctly drops to False so the player can just pick
        # a replacement, rather than getting a raw 403 loop on every save.
        cards = [c for c in cards_result.unique().scalars().all() if c.owner_id == squad.user_id]
    return TacticoSquadOut(
        template_index=squad.template_index, name=squad.name, is_active=squad.is_active,
        is_complete=len(cards) == SQUAD_SIZE, cards=cards,
        max_legendary=config.tactico_max_legendary_cards, max_epic=config.tactico_max_epic_cards,
        max_diamond=config.tactico_max_diamond_cards,
    )


async def get_squad(db: AsyncSession, user: User, template_index: int | None = None) -> TacticoSquadOut:
    squad = await _get_squad_template_row(db, user.id, template_index)
    return await _serialize_squad(db, squad)


async def list_squad_templates(db: AsyncSession, user: User) -> list[TacticoSquadOut]:
    templates = await _ensure_squad_templates(db, user.id)
    return [await _serialize_squad(db, t) for t in templates]


async def rename_squad_template(db: AsyncSession, user: User, template_index: int, name: str) -> TacticoSquadOut:
    if not name.strip():
        raise ConflictError("Название не может быть пустым")
    squad = await _get_squad_template_row(db, user.id, template_index)
    squad.name = name.strip()[:64]
    db.add(squad)
    await db.commit()
    return await get_squad(db, user, template_index)
```

- [ ] **Step 3: Update `set_squad` to take an optional `template_index`, lock only when active**

Replace `set_squad`'s row lookup and lock loop (existing lines 94-142) —
validation is unchanged, only the row lookup and the two `is_in_tactico_squad`
loops change:

```python
async def set_squad(db: AsyncSession, user: User, user_card_ids: list[int], template_index: int | None = None) -> TacticoSquadOut:
    config = await get_config(db)
    unique_ids = list(dict.fromkeys(user_card_ids))
    if len(unique_ids) != SQUAD_SIZE:
        raise ConflictError(f"A Tactico squad must have exactly {SQUAD_SIZE} distinct cards")

    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(unique_ids)).options(joinedload(UserCard.player))
    )
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}
    if len(cards_by_id) != len(unique_ids):
        raise NotFoundError("One or more cards not found")
    for card in cards_by_id.values():
        if card.owner_id != user.id:
            raise ForbiddenError("You can only use your own cards in your Tactico squad")
        if card.is_locked_by_admin:
            raise ConflictError(f"Card #{card.serial_number} is locked and cannot be used")
        if card.is_locked_in_trade:
            raise ConflictError(f"Card #{card.serial_number} is locked in an active trade and cannot be used")

    legendary_count = sum(1 for c in cards_by_id.values() if c.player.rarity == Rarity.legendary)
    epic_count = sum(1 for c in cards_by_id.values() if c.player.rarity == Rarity.epic)
    diamond_count = sum(1 for c in cards_by_id.values() if c.player.rarity == Rarity.diamond)
    if legendary_count > config.tactico_max_legendary_cards:
        raise ConflictError(f"Максимум {config.tactico_max_legendary_cards} легендарных карт в составе Тактико")
    if epic_count > config.tactico_max_epic_cards:
        raise ConflictError(f"Максимум {config.tactico_max_epic_cards} эпических карт в составе Тактико")
    if diamond_count > config.tactico_max_diamond_cards:
        raise ConflictError(f"Максимум {config.tactico_max_diamond_cards} диамантовых карт в составе Тактико")

    squad = await _get_squad_template_row(db, user.id, template_index)
    old_result = await db.execute(select(TacticoSquadCard).where(TacticoSquadCard.squad_id == squad.id))
    old_squad_cards = old_result.scalars().all()
    old_card_ids = [sc.user_card_id for sc in old_squad_cards]

    # Trade/upgrade locking reflects only the ACTIVE template — editing a
    # template that isn't currently active must never touch
    # is_in_tactico_squad on any card.
    if squad.is_active and old_card_ids:
        old_cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(old_card_ids)))
        for c in old_cards_result.scalars().all():
            c.is_in_tactico_squad = False
            db.add(c)
    for sc in old_squad_cards:
        await db.delete(sc)
    await db.flush()
    for card_id in unique_ids:
        if squad.is_active:
            cards_by_id[card_id].is_in_tactico_squad = True
            db.add(cards_by_id[card_id])
        db.add(TacticoSquadCard(squad_id=squad.id, user_card_id=card_id))

    await db.commit()
    return await get_squad(db, user, squad.template_index)
```

- [ ] **Step 4: Add `activate_squad_template`**

Append after `set_squad`:

```python
async def activate_squad_template(db: AsyncSession, user: User, template_index: int) -> TacticoSquadOut:
    """Mirrors lineup_service.activate_template exactly, for TacticoSquad —
    see that function's docstring for the shared-card/no-flicker reasoning."""
    templates = await _ensure_squad_templates(db, user.id)
    if not 1 <= template_index <= SQUAD_TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {SQUAD_TEMPLATE_COUNT}")
    new_active = next(t for t in templates if t.template_index == template_index)
    old_active = next((t for t in templates if t.is_active), None)

    if old_active is not None and old_active.id == new_active.id:
        return await get_squad(db, user, template_index)

    old_card_ids: set[int] = set()
    if old_active is not None:
        old_result = await db.execute(select(TacticoSquadCard.user_card_id).where(TacticoSquadCard.squad_id == old_active.id))
        old_card_ids = set(old_result.scalars().all())
    new_result = await db.execute(select(TacticoSquadCard.user_card_id).where(TacticoSquadCard.squad_id == new_active.id))
    new_card_ids = set(new_result.scalars().all())

    to_unlock = old_card_ids - new_card_ids
    to_lock = new_card_ids - old_card_ids
    touched_ids = to_unlock | to_lock
    if touched_ids:
        cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(touched_ids)))
        for card in cards_result.scalars().all():
            card.is_in_tactico_squad = card.id in to_lock
            db.add(card)

    if old_active is not None:
        old_active.is_active = False
        db.add(old_active)
    new_active.is_active = True
    db.add(new_active)

    await db.commit()
    return await get_squad(db, user, template_index)
```

(No `with_for_update` row-lock here — unlike `set_lineup`/`set_squad`'s
overlapping-PUT race, `TacticoSquad` has no such precedent lock in the
original code, so this mirrors that as-is; the migration's partial unique
index still prevents two rows from being active at once even under a
race, just not the narrower "two activates for the same user landing
in the wrong order" race — acceptable since a lost race there just means
whichever activate committed last wins, with no invalid intermediate
state possible.)

- [ ] **Step 5: Run existing tests**

Run: `docker compose exec backend pytest tests/test_tactico.py -v`
Expected: all pass unchanged.

- [ ] **Step 6: Write new template tests**

Create `backend/tests/test_tactico_squad_templates.py`:

```python
from app.models.card import UserCard
from app.services.tactico_service import SQUAD_TEMPLATE_COUNT, activate_squad_template, get_squad, list_squad_templates, rename_squad_template, set_squad
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers
from app.services.card_creation import create_user_card
from app.models.enums import CardSource


async def _build_squad_cards(db_session, user_id: int, count: int = 11) -> list[int]:
    ids = []
    for _ in range(count):
        player = await create_player(db_session)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        ids.append(card.id)
    return ids


async def test_five_squad_templates_lazily_created(client, db_session, bot_token):
    headers = telegram_headers(860001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860001)

    templates = await list_squad_templates(db_session, user)
    assert len(templates) == SQUAD_TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    assert templates[1].name == "Шаблон 2"


async def test_editing_inactive_squad_template_does_not_lock_cards(client, db_session, bot_token):
    headers = telegram_headers(860002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860002)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids, template_index=2)

    for card_id in card_ids:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is False


async def test_editing_active_squad_template_locks_cards(client, db_session, bot_token):
    headers = telegram_headers(860003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860003)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids)  # template_index=None -> active (1)

    for card_id in card_ids:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is True


async def test_same_card_can_be_saved_into_two_squad_templates(client, db_session, bot_token):
    headers = telegram_headers(860004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860004)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids, template_index=1)
    result = await set_squad(db_session, user, card_ids, template_index=2)
    assert result.is_complete is True


async def test_activate_squad_template_moves_lock_to_new_cards_only(client, db_session, bot_token):
    headers = telegram_headers(860005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860005)

    ids_1 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_1, template_index=1)
    ids_2 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_2, template_index=2)

    await activate_squad_template(db_session, user, 2)

    for card_id in ids_1:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is False
    for card_id in ids_2:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is True


async def test_activate_squad_template_keeps_shared_card_locked(client, db_session, bot_token):
    headers = telegram_headers(860006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860006)

    ids_1 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_1, template_index=1)
    ids_2 = await _build_squad_cards(db_session, user.id, count=10) + [ids_1[0]]
    await set_squad(db_session, user, ids_2, template_index=2)

    await activate_squad_template(db_session, user, 2)

    shared = await db_session.get(UserCard, ids_1[0])
    assert shared.is_in_tactico_squad is True


async def test_rename_squad_template(client, db_session, bot_token):
    headers = telegram_headers(860007, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860007)

    result = await rename_squad_template(db_session, user, 3, "Резерв")
    assert result.name == "Резерв"
    templates = await list_squad_templates(db_session, user)
    assert templates[2].name == "Резерв"


async def test_get_squad_with_no_args_returns_active_template(client, db_session, bot_token):
    headers = telegram_headers(860008, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860008)

    await activate_squad_template(db_session, user, 4)
    result = await get_squad(db_session, user)
    assert result.template_index == 4
    assert result.is_active is True
```

Run: `docker compose exec backend pytest tests/test_tactico_squad_templates.py -v`
Expected: all 8 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tactico_service.py backend/tests/test_tactico_squad_templates.py
git commit -m "feat(tactico): add 5-template listing, per-template edits, activation"
```

---

### Task 5: Router — template endpoints

**Files:**
- Modify: `backend/app/routers/tactico.py`

- [ ] **Step 1: Add the routes**

```python
from app.schemas.tactico import (
    TacticoBotMatchRequest,
    TacticoChallengeRequest,
    TacticoMatchOut,
    TacticoOpenChallengePreviewOut,
    TacticoOpenChallengeRequest,
    TacticoRoundSubmitRequest,
    TacticoSearchStatusOut,
    TacticoSquadOut,
    TacticoSquadRenameRequest,
    TacticoSquadSetRequest,
    TacticoStatsOut,
)
```

(Add `TacticoSquadRenameRequest` to the existing import list — everything
else in this import block is unchanged.)

Then add, right after the existing `GET`/`PUT /squad` routes:

```python
@router.get("/squad/templates", response_model=list[TacticoSquadOut])
async def read_squad_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.list_squad_templates(db, user)


@router.put("/squad/templates/{template_index}", response_model=TacticoSquadOut)
async def update_squad_template(
    template_index: int, payload: TacticoSquadSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await tactico_service.set_squad(db, user, payload.user_card_ids, template_index)


@router.put("/squad/templates/{template_index}/name", response_model=TacticoSquadOut)
async def rename_squad_template_route(
    template_index: int, payload: TacticoSquadRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await tactico_service.rename_squad_template(db, user, template_index, payload.name)


@router.post("/squad/templates/{template_index}/activate", response_model=TacticoSquadOut)
async def activate_squad_template_route(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await tactico_service.activate_squad_template(db, user, template_index)
```

- [ ] **Step 2: Run tests**

Run: `docker compose exec backend pytest tests/test_tactico.py tests/test_tactico_squad_templates.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/tactico.py
git commit -m "feat(tactico): add squad template list/edit/rename/activate endpoints"
```

---

### Task 6: Frontend — types, API client, template switcher

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/tactico.ts`
- Modify: `frontend/src/pages/TacticoSquadPage.tsx`

- [ ] **Step 1: Extend `TacticoSquad` type**

```typescript
export interface TacticoSquad {
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  cards: UserCard[];
  max_legendary: number;
  max_epic: number;
  max_diamond: number;
}
```

- [ ] **Step 2: Add template API functions**

```typescript
export async function fetchTacticoSquadTemplates(): Promise<TacticoSquad[]> {
  const { data } = await api.get<TacticoSquad[]>("/tactico/squad/templates");
  return data;
}

export async function setTacticoSquadTemplate(templateIndex: number, userCardIds: number[]): Promise<TacticoSquad> {
  const { data } = await api.put<TacticoSquad>(`/tactico/squad/templates/${templateIndex}`, { user_card_ids: userCardIds });
  return data;
}

export async function renameTacticoSquadTemplate(templateIndex: number, name: string): Promise<TacticoSquad> {
  const { data } = await api.put<TacticoSquad>(`/tactico/squad/templates/${templateIndex}/name`, { name });
  return data;
}

export async function activateTacticoSquadTemplate(templateIndex: number): Promise<TacticoSquad> {
  const { data } = await api.post<TacticoSquad>(`/tactico/squad/templates/${templateIndex}/activate`);
  return data;
}
```

(Append below the existing `fetchTacticoSquad`/`setTacticoSquad` — both
kept unchanged.)

- [ ] **Step 3: Rework `TacticoSquadPage.tsx` around a selected template**

Replace the query, selection-init effect, and save mutation:

```typescript
import { activateTacticoSquadTemplate, fetchTacticoSquadTemplates, renameTacticoSquadTemplate, setTacticoSquadTemplate } from "@/api/tactico";
```

```typescript
  const queryClient = useQueryClient();

  const { data: templates } = useQuery({ queryKey: ["tactico-squad-templates"], queryFn: fetchTacticoSquadTemplates });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const squad = templates?.find((t) => t.template_index === viewedIndex);

  const [search, setSearch] = useState("");
  const { data: collectionPage, isLoading } = useQuery({
    queryKey: ["collection-for-tactico", search],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: search || undefined }),
  });

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [initializedFor, setInitializedFor] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (squad && initializedFor !== squad.template_index) {
      setSelectedIds(squad.cards.map((c) => c.id));
      setInitializedFor(squad.template_index);
    }
  }, [squad, initializedFor]);

  const saveMutation = useMutation({
    mutationFn: () => setTacticoSquadTemplate(viewedIndex, selectedIds),
    onSuccess: () => {
      hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["tactico-squad-templates"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось сохранить состав")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateTacticoSquadTemplate(viewedIndex),
    onSuccess: () => { haptic("medium"); queryClient.invalidateQueries({ queryKey: ["tactico-squad-templates"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const [renamingTemplate, setRenamingTemplate] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const renameMutation = useMutation({
    mutationFn: (name: string) => renameTacticoSquadTemplate(viewedIndex, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["tactico-squad-templates"] }); setRenamingTemplate(false); },
  });
```

Remove the old `navigate("/play/tactico")` from `saveMutation`'s
`onSuccess` (saving one template no longer means "done editing" — the
player may want to switch tabs and build another) and drop the now-unused
`useNavigate` import/`navigate` call if nothing else in the file uses it
(check with `grep -n "navigate" frontend/src/pages/TacticoSquadPage.tsx`
before removing the import — if the "Сохранить" button's disabled/label
logic doesn't reference it, it's safe to remove both the import and the
`const navigate = useNavigate();` line).

Update every remaining reference to the old `squad` variable in the JSX
(`squad?.max_legendary`, etc.) — none need to change since `squad` is
still the right name, just now sourced from `templates.find(...)` instead
of `fetchTacticoSquad` directly.

- [ ] **Step 4: Add the template switcher UI**

Insert right after the opening `<div>` and its title block, before the
rarity-cap badges row:

```tsx
      <section className="flex gap-1.5 overflow-x-auto pb-1">
        {(templates ?? []).map((t) => (
          <button
            key={t.template_index}
            onClick={() => { setSelectedIndex(t.template_index); setRenamingTemplate(false); }}
            className={`flex shrink-0 flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 ${
              t.template_index === viewedIndex ? "bg-accent-lime text-bg-base" : "bg-white/5 text-ink-mist"
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

      {renamingTemplate ? (
        <div className="flex gap-2">
          <input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            maxLength={64}
            className="flex-1 rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
            autoFocus
          />
          <button
            onClick={() => renameMutation.mutate(renameValue)}
            disabled={!renameValue.trim() || renameMutation.isPending}
            className="rounded-xl bg-accent-lime px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
        </div>
      ) : (
        <button
          onClick={() => { setRenameValue(squad?.name ?? ""); setRenamingTemplate(true); }}
          className="self-start text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2"
        >
          Переименовать «{squad?.name}»
        </button>
      )}

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Сделать «${squad?.name}» активным для матчей`}
        </button>
      )}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Live verification**

Rebuild frontend container, then in the Browser pane:
1. Open `/play/tactico/squad` (or wherever this page is routed), confirm
   5 template pills, first marked "Активный".
2. Build 11 cards on template 2 — confirm those cards are NOT locked
   (check collection).
3. Activate template 2 — confirm template 1's cards unlock, template 2's
   lock.
4. Confirm a Tactico match still starts using whichever template is
   active (bot match or friend challenge).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/tactico.ts frontend/src/pages/TacticoSquadPage.tsx
git commit -m "feat(tactico): add 5-template switcher to squad page"
```

## Definition of Done (Phase 2)

- 8 new backend tests pass; `test_tactico.py` passes unmodified.
- `npm run typecheck` clean.
- Live-verified template switch + lock recompute + match still uses the
  active template.
