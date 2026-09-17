# Lineup Templates — Phase 3: Клубы Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ClubLineup` moves from "one lineup per club" to "5 named
templates per club, one active" — same shape as Card Arena/Тактико, still
manager-gated (only captain/assistant may edit/rename/activate). Unlike
the previous two phases, **no card-locking logic is needed**: `ClubCard`
has no trade-lock concept at all (confirmed — no `is_in_lineup` flag on
`ClubCard`), so activating a template is just flipping `is_active` on two
rows.

**Why this phase is riskier than Phase 1/2:** `ClubLineup` is read from
FOUR other service files beyond `club_squad_service.py` itself —
`tournament_notification_service.py`, `tournament_simulation_service.py`,
`tournament_queue_service.py` (which runs its own direct query, not
through `_get_or_none_lineup`), and indirectly the opponent-preview path
in `get_next_opponent`. Once `club_id` stops being unique on `ClubLineup`,
every one of these needs to keep resolving to exactly the *active*
template, or they break with `MultipleResultsFound`.

**Architecture — the key design decision:** two different lookup paths,
not one:
- **`_get_or_none_lineup(db, club_id)`** (existing function, used by every
  *cross-club, read-only* consumer — opponent preview, tournament
  notification/simulation/queue): gains exactly one thing, an
  `is_active.is_(True)` filter. It **never lazily creates rows** — a read
  of another club's data must never have the side effect of writing to
  it. For every club that already has its one pre-migration row (which is
  `is_active=True` by the migration's `server_default`), this resolves to
  the exact same row as before — zero behavior change for these 4
  consumers.
- **`_get_club_lineup_row(db, club_id, template_index)`** (new, used only
  by the *owning club's own* squad-editing endpoints): lazily seeds all 5
  templates on first access (mirrors Phase 1/2's `_ensure_templates`
  exactly), then resolves the requested index (or the active one if
  `None`).

**Spec:** [docs/superpowers/specs/2026-09-17-lineup-templates-design.md](../specs/2026-09-17-lineup-templates-design.md)

## Global Constraints

- Exactly 5 templates per club, lazily seeded (own-club paths only).
- No card-locking logic for Клубы — `ClubCard` has none.
- `_get_or_none_lineup(db, club_id)`'s signature and Optional-returning,
  no-side-effect behavior must not change for its 4 existing callers.
- Manager-only gating (`_require_manager`) stays exactly as strict as
  today for every mutating endpoint, including the 3 new ones.

---

### Task 1: Migration — template columns on `club_lineups`

**Files:**
- Create: `backend/alembic/versions/0118_club_lineup_templates.py`

- [ ] **Step 1: Write the migration**

```python
"""Club lineups become 5 named templates per club (template_index 1..5,
one active) instead of a single row, mirroring migrations 0116/0117's
Card Arena/Тактико changes. Templates 2-5 are lazily created by
club_squad_service on first access by the club's own manager, not
backfilled here.

Revision ID: 0118
Revises: 0117
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0118"
down_revision: Union[str, None] = "0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("club_lineups", sa.Column("name", sa.String(length=64), nullable=False, server_default="Основной состав"))
    op.add_column("club_lineups", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.drop_constraint("club_lineups_club_id_key", "club_lineups", type_="unique")
    op.create_unique_constraint("uq_club_lineup_club_template", "club_lineups", ["club_id", "template_index"])
    op.create_index(
        "uq_club_lineup_one_active_per_club", "club_lineups", ["club_id"], unique=True,
        postgresql_where=sa.text("is_active"), sqlite_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_club_lineup_one_active_per_club", table_name="club_lineups")
    op.drop_constraint("uq_club_lineup_club_template", "club_lineups", type_="unique")
    op.create_unique_constraint("club_lineups_club_id_key", "club_lineups", ["club_id"])
    op.drop_column("club_lineups", "is_active")
    op.drop_column("club_lineups", "name")
    op.drop_column("club_lineups", "template_index")
```

- [ ] **Step 2: Apply and verify**

Run: `docker compose exec backend alembic upgrade head`
Expected: `Running upgrade 0117 -> 0118, Club lineups become 5 named templates...`

Run: `docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c "\d club_lineups"`
Expected: `template_index`, `name`, `is_active` present; `uq_club_lineup_club_template`
and `uq_club_lineup_one_active_per_club` present; `club_lineups_club_id_key` gone.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0118_club_lineup_templates.py
git commit -m "feat(clubs): add template columns to club_lineups"
```

---

### Task 2: Model — `ClubLineup` template fields

**Files:**
- Modify: `backend/app/models/club_lineup.py`

- [ ] **Step 1: Edit the model**

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubLineup(Base):
    __tablename__ = "club_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    # 1..5 — mirrors Lineup.template_index (lineup.py) / TacticoSquad
    # .template_index (tactico.py) exactly; one of 5 fixed, always-present
    # saved squads (see club_squad_service._ensure_club_lineup_templates).
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    formation: Mapped[str] = mapped_column(String(16), default="4-3-3", nullable=False, server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), default="BALANCED", nullable=False, server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), default="CENTRAL_PLAY", nullable=False, server_default="CENTRAL_PLAY")
    club_coach_card_id: Mapped[int | None] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True)

    cards: Mapped[list["ClubLineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")
    club_coach_card: Mapped["ClubCoachCard | None"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("club_id", "template_index", name="uq_club_lineup_club_template"),
        Index(
            "uq_club_lineup_one_active_per_club", "club_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )
```

(Only `template_index`/`name`/`is_active` and the new `__table_args__` are
additions; every other field/relationship is unchanged from today. The
`ClubLineupCard` class below it in the same file is untouched.)

- [ ] **Step 2: Verify the app still imports cleanly**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/club_lineup.py
git commit -m "feat(clubs): add template_index/name/is_active to ClubLineup"
```

---

### Task 3: Schema — expose template fields, add rename request

**Files:**
- Modify: `backend/app/schemas/club_squad.py`

- [ ] **Step 1: Edit `ClubLineupOut`, add `ClubLineupRenameRequest`**

```python
class ClubLineupOut(BaseModel):
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    tactical_fit_hint: str
    slots: list[ClubLineupSlotOut]
    coach: EquippedCoachOut | None = None
    training_uses_remaining: int = 0
    training_boost_active: bool = False
    in_active_tournament: bool = False
    attack: int = 0
    midfield: int = 0
    defence: int = 0
    goalkeeping: int = 0
```

(Only `template_index`/`name`/`is_active`, inserted at the top, are new —
every other field is unchanged.) Add after `ClubTacticsSetRequest`:

```python
class ClubLineupRenameRequest(BaseModel):
    name: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/club_squad.py
git commit -m "feat(clubs): expose template fields on ClubLineupOut"
```

---

### Task 4: Service — template ensure/lookup, per-template edits, activation

**Files:**
- Modify: `backend/app/services/club_squad_service.py`
- Test: `backend/tests/test_club_lineup_templates.py` (new)

- [ ] **Step 1: Add the ensure/lookup helpers, right after `seed_starting_squad`**

```python
CLUB_TEMPLATE_COUNT = 5
DEFAULT_CLUB_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, CLUB_TEMPLATE_COUNT + 1)}


def _club_lineup_templates_query(club_id: int):
    return (
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(
            joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card),
            joinedload(ClubLineup.club_coach_card).joinedload(ClubCoachCard.coach).joinedload(Coach.boosts),
        )
        .order_by(ClubLineup.template_index)
        .execution_options(populate_existing=True)
    )


async def _ensure_club_lineup_templates(db: AsyncSession, club_id: int) -> list[ClubLineup]:
    """Lazily seeds any of the 5 fixed template slots that don't exist yet
    for this club — same pattern as lineup_service._ensure_templates. Only
    ever called from the owning club's own squad-editing paths (never from
    a cross-club read like an opponent preview — see _get_or_none_lineup's
    docstring for why that distinction matters)."""
    result = await db.execute(_club_lineup_templates_query(club_id))
    templates = list(result.unique().scalars().all())
    existing_indexes = {t.template_index for t in templates}
    missing = [i for i in range(1, CLUB_TEMPLATE_COUNT + 1) if i not in existing_indexes]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        async with db.begin_nested():
            for i in missing:
                db.add(ClubLineup(
                    club_id=club_id, template_index=i, name=DEFAULT_CLUB_TEMPLATE_NAMES[i],
                    is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        pass

    result = await db.execute(_club_lineup_templates_query(club_id))
    return list(result.unique().scalars().all())


async def _get_club_lineup_row(db: AsyncSession, club_id: int, template_index: int | None) -> ClubLineup:
    templates = await _ensure_club_lineup_templates(db, club_id)
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= CLUB_TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {CLUB_TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)


async def _lock_club_lineup_row(db: AsyncSession, club_id: int, template_index: int | None) -> ClubLineup:
    """Ensures + resolves the target row (unlocked), then re-fetches it
    locked by id — mirrors set_club_lineup's original with_for_update
    comment: scoping the lock to ClubLineup.id (not a club_id/template_index
    WHERE) avoids Postgres's 'FOR UPDATE on the nullable side of an outer
    join' rejection from the eager-loaded cards/coach relationships."""
    row = await _get_club_lineup_row(db, club_id, template_index)
    result = await db.execute(
        select(ClubLineup).where(ClubLineup.id == row.id)
        .options(joinedload(ClubLineup.cards))
        .with_for_update(of=ClubLineup)
    )
    return result.unique().scalar_one()
```

Add `NotFoundError` to the existing `from app.core.exceptions import ConflictError`
import at the top of the file.

- [ ] **Step 2: Add `NotFoundError` import check and update `_get_or_none_lineup`**

```python
async def _get_or_none_lineup(db: AsyncSession, club_id: int) -> ClubLineup | None:
    # populate_existing=True is required here for the same reason as
    # wallet_service.lock_user_for_update: the session's identity map may
    # already hold this same ClubLineup object from earlier in the request
    # (e.g. set_club_lineup's locked query before its delete-then-recreate),
    # and this app's session factory uses expire_on_commit=False (see
    # database.py), so a plain re-SELECT after commit would silently return
    # that stale cached object — including its now-outdated `.cards`
    # collection — instead of what this query actually just fetched.
    #
    # This is the READ-ONLY, cross-club lookup — used by opponent-lineup
    # preview and tournament notification/simulation/queue services. It
    # deliberately never lazily creates rows (unlike _get_club_lineup_row,
    # used only by the owning club's own squad screen): a read of another
    # club's data must never have the side effect of writing to it. The
    # is_active filter is the only change from this function's pre-template
    # form — for every club's pre-migration row (is_active=True via the
    # migration's server_default) this resolves to the exact same row as
    # before.
    result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id, ClubLineup.is_active.is_(True))
        .options(
            joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card),
            joinedload(ClubLineup.club_coach_card).joinedload(ClubCoachCard.coach).joinedload(Coach.boosts),
        )
        .execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()
```

(Replaces the existing function body — only the `where(...)` clause gains
`, ClubLineup.is_active.is_(True)`; everything else, including the
docstring's original content, is preserved and extended.)

- [ ] **Step 3: Refactor `_lineup_to_out` to take a resolved row, add `list_club_lineup_templates`/`rename`/`activate`**

Replace `_lineup_to_out`'s signature and its first line:

```python
async def _lineup_to_out(db: AsyncSession, club_id: int, template_index: int | None = None) -> ClubLineupOut:
    lineup = await _get_club_lineup_row(db, club_id, template_index)
    formation = lineup.formation if lineup else DEFAULT_FORMATION
```

(Only the first line changes — from `lineup = await _get_or_none_lineup(db, club_id)`
to the line above. Every remaining line of the function — `mentality`,
`by_slot`, `is_complete`, `team_strength`, `coach_out`, the final
`ClubLineupOut(...)` construction — is unchanged; `lineup` is now
guaranteed non-`None` in practice, but the existing `if lineup else`
guards are harmless left as-is.)

Add `template_index=lineup.template_index, name=lineup.name, is_active=lineup.is_active,`
as the first three constructor arguments in the final `return ClubLineupOut(...)` call.

Append after `set_club_coach` (Task 5 will edit that function's body, but
add these new functions now regardless of edit order):

```python
async def list_club_lineup_templates(db: AsyncSession, user: User) -> list[ClubLineupOut]:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    templates = await _ensure_club_lineup_templates(db, membership.club_id)
    return [await _lineup_to_out(db, membership.club_id, t.template_index) for t in templates]


async def rename_club_lineup_template(db: AsyncSession, user: User, template_index: int, name: str) -> ClubLineupOut:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    if not name.strip():
        raise ConflictError("Название не может быть пустым")

    lineup = await _get_club_lineup_row(db, membership.club_id, template_index)
    lineup.name = name.strip()[:64]
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, membership.club_id, template_index)


async def activate_club_lineup_template(db: AsyncSession, user: User, template_index: int) -> ClubLineupOut:
    """Unlike lineup_service.activate_template / tactico_service
    .activate_squad_template, no card-lock recompute is needed here —
    ClubCard has no trade-lock concept at all. This is just a two-row
    is_active flip."""
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    templates = await _ensure_club_lineup_templates(db, club_id)
    if not 1 <= template_index <= CLUB_TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {CLUB_TEMPLATE_COUNT}")
    new_active = next(t for t in templates if t.template_index == template_index)
    old_active = next((t for t in templates if t.is_active), None)

    if old_active is None or old_active.id != new_active.id:
        if old_active is not None:
            old_active.is_active = False
            db.add(old_active)
        new_active.is_active = True
        db.add(new_active)
        await db.commit()

    return await _lineup_to_out(db, club_id, template_index)
```

- [ ] **Step 4: Run existing tests**

Run: `docker compose exec backend pytest tests/test_club_squad.py -v`
Expected: all pass unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/club_squad_service.py
git commit -m "feat(clubs): add 5-template listing, rename, activation for club lineups"
```

---

### Task 5: Service — scope `set_club_lineup`/`set_club_tactics`/`set_club_coach` to a template

**Files:**
- Modify: `backend/app/services/club_squad_service.py`

- [ ] **Step 1: `set_club_lineup`**

Replace the row lookup and lock (existing lines ~371-425) — the slot/card
validation logic above it is unchanged:

```python
async def set_club_lineup(
    db: AsyncSession, user: User, payload: ClubLineupSetRequest, template_index: int | None = None
) -> ClubLineupOut:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    # Lock the target template row up front (this also ensures all 5
    # templates exist) — the formation-lookup and the delete-then-recreate
    # below both need the same locked row, avoiding the double
    # fetch-then-relock this function used to do against the club's single
    # row.
    lineup = await _lock_club_lineup_row(db, club_id, template_index)
    formation = lineup.formation
    slots_by_code = get_slots_by_code(formation)

    slot_codes = [s.slot_code for s in payload.slots]
    if len(slot_codes) != len(set(slot_codes)):
        raise ConflictError("Один слот не может использоваться дважды")
    if any(code not in slots_by_code for code in slot_codes):
        raise ConflictError("Неизвестный слот состава")

    card_ids = [s.club_card_id for s in payload.slots]
    if len(card_ids) != len(set(card_ids)):
        raise ConflictError("Одна карточка не может занимать два слота")

    club_cards = (await db.execute(select(ClubCard).where(ClubCard.id.in_(card_ids), ClubCard.club_id == club_id))).scalars().all()
    if len(club_cards) != len(card_ids):
        raise ConflictError("Карточка не принадлежит этому клубу")
    cards_by_id = {c.id: c for c in club_cards}

    player_ids = [cards_by_id[cid].player_id for cid in card_ids]
    if len(player_ids) != len(set(player_ids)):
        raise ConflictError("Один футболист не может занимать две позиции")

    for slot_in in payload.slots:
        slot = slots_by_code[slot_in.slot_code]
        card = cards_by_id[slot_in.club_card_id]
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(f"Игрок на позиции {card.player.position.value} не подходит для слота {slot.code}")

    for lc in list(lineup.cards):
        await db.delete(lc)
    await db.flush()
    for slot_in in payload.slots:
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=slot_in.club_card_id, slot_code=slot_in.slot_code))
    try:
        await db.commit()
    except IntegrityError:
        # See this function's pre-template history for why this exists:
        # observed in production as an unhandled 500 under real concurrent
        # load — reproduced directly with 6 concurrent identical saves
        # against real Postgres (2 succeeded, 4 hit this exact
        # IntegrityError). Surface a clean, retriable error instead.
        await db.rollback()
        raise ConflictError("Не удалось сохранить состав — попробуй ещё раз")
    return await _lineup_to_out(db, club_id, lineup.template_index)
```

(The docstring-length comment about *why* `with_for_update(of=ClubLineup)`
is scoped the way it is now lives on `_lock_club_lineup_row` instead of
being repeated here — still true, just not duplicated.)

- [ ] **Step 2: `set_club_tactics`**

```python
async def set_club_tactics(
    db: AsyncSession, user: User, payload: ClubTacticsSetRequest, template_index: int | None = None
) -> ClubLineupOut:
    """PUT /clubs/me/tactics — mirrors set_club_lineup's captain/assistant-
    only gating. Changing formation reconciles existing slots (spec §3):
    ClubLineupCard rows whose slot_code doesn't exist in the new formation
    are cleared (freeing their card to the bench); slots that share a code
    across both formations (GK, DEF1, ...) keep their card."""
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    if payload.formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Неизвестная схема: {payload.formation}")
    if payload.mentality not in MENTALITIES:
        raise ConflictError(f"Неизвестный настрой: {payload.mentality}")
    if payload.playstyle not in PLAYSTYLES:
        raise ConflictError(f"Неизвестный стиль игры: {payload.playstyle}")

    lineup = await _lock_club_lineup_row(db, club_id, template_index)

    new_slot_codes = set(get_slots_by_code(payload.formation).keys())
    for lc in list(lineup.cards):
        if lc.slot_code not in new_slot_codes:
            await db.delete(lc)

    lineup.formation = payload.formation
    lineup.mentality = payload.mentality
    lineup.playstyle = payload.playstyle
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id, lineup.template_index)
```

- [ ] **Step 3: `set_club_coach`**

```python
async def set_club_coach(
    db: AsyncSession, user: User, payload: ClubCoachSetRequest, template_index: int | None = None
) -> ClubLineupOut:
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

    lineup = await _lock_club_lineup_row(db, club_id, template_index)
    lineup.club_coach_card_id = payload.club_coach_card_id
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id, lineup.template_index)
```

- [ ] **Step 4: `get_club_lineup` and `activate_training` pass through `template_index`**

```python
async def get_club_lineup(db: AsyncSession, user: User, template_index: int | None = None) -> ClubLineupOut:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    return await _lineup_to_out(db, membership.club_id, template_index)
```

`activate_training` needs no signature change (it always operates on
whatever the club's active template is — training boosts apply
club-wide/tournament-wide, not per-template) — leave its final
`return await _lineup_to_out(db, club_id)` call exactly as-is; the new
`template_index=None` default resolves it to the active template
automatically.

- [ ] **Step 5: Run tests**

Run: `docker compose exec backend pytest tests/test_club_squad.py -v`
Expected: all pass unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/club_squad_service.py
git commit -m "feat(clubs): scope lineup/tactics/coach edits to a specific template"
```

---

### Task 6: Fix `tournament_queue_service.py`'s direct `ClubLineup` query

**Files:**
- Modify: `backend/app/services/tournament_queue_service.py`

**Why:** `_has_full_starting_xi` runs its own `select(ClubLineup).where(ClubLineup.club_id == club_id)`
instead of calling `_get_or_none_lineup` — once a club can have 5 rows,
`.scalar_one_or_none()` here would raise `MultipleResultsFound` for any
club with more than one template row.

- [ ] **Step 1: Add the `is_active` filter**

```python
async def _has_full_starting_xi(db: AsyncSession, club_id: int) -> bool:
    lineup = (
        await db.execute(
            select(ClubLineup).where(ClubLineup.club_id == club_id, ClubLineup.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if lineup is None:
        return False
    count = (
        await db.execute(select(func.count(ClubLineupCard.id)).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalar_one()
    return count == len(FORMATION_SLOTS)
```

(Only the `where(...)` clause in the first query gains
`, ClubLineup.is_active.is_(True)` — everything else in the function is
unchanged.)

- [ ] **Step 2: Run tournament tests**

Run: `docker compose exec backend pytest tests/test_tournament_queue.py -v`
(adjust the filename if this test lives elsewhere — grep
`_has_full_starting_xi\|test_tournament_queue` in `backend/tests/` to
confirm before running)
Expected: all pass unchanged.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/tournament_queue_service.py
git commit -m "fix(clubs): scope tournament-queue lineup check to the active template"
```

---

### Task 7: Router — template endpoints

**Files:**
- Modify: `backend/app/routers/clubs.py`

- [ ] **Step 1: Add `ClubLineupRenameRequest` to the existing schema import, add the routes**

Find the existing import from `app.schemas.club_squad` and add
`ClubLineupRenameRequest` to it. Then add, right after the existing
`GET/PUT /me/lineup`, `PUT /me/tactics`, `PUT /me/coach` routes:

```python
@router.get("/me/lineup/templates", response_model=list[ClubLineupOut])
async def read_club_lineup_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.list_club_lineup_templates(db, user)


@router.put("/me/lineup/templates/{template_index}", response_model=ClubLineupOut)
async def update_club_lineup_template(
    template_index: int, payload: ClubLineupSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_squad_service.set_club_lineup(db, user, payload, template_index)


@router.put("/me/tactics/templates/{template_index}", response_model=ClubLineupOut)
async def update_club_tactics_template(
    template_index: int, payload: ClubTacticsSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_squad_service.set_club_tactics(db, user, payload, template_index)


@router.put("/me/coach/templates/{template_index}", response_model=ClubLineupOut)
async def update_club_coach_template(
    template_index: int, payload: ClubCoachSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_squad_service.set_club_coach(db, user, payload, template_index)


@router.put("/me/lineup/templates/{template_index}/name", response_model=ClubLineupOut)
async def rename_club_lineup_template_route(
    template_index: int, payload: ClubLineupRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_squad_service.rename_club_lineup_template(db, user, template_index, payload.name)


@router.post("/me/lineup/templates/{template_index}/activate", response_model=ClubLineupOut)
async def activate_club_lineup_template_route(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_squad_service.activate_club_lineup_template(db, user, template_index)
```

- [ ] **Step 2: Run the full club test suite**

Run: `docker compose exec backend pytest tests/test_club_squad.py tests/test_clubs.py -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/clubs.py
git commit -m "feat(clubs): add club lineup template list/edit/rename/activate endpoints"
```

---

### Task 8: Backend tests for templates

**Files:**
- Create: `backend/tests/test_club_lineup_templates.py`

- [ ] **Step 1: Write the tests**

```python
from app.models.club_lineup import ClubLineup
from app.models.enums import ClubLogoShape, ClubType, Position
from app.schemas.club_squad import ClubLineupSetRequest, ClubLineupSlotIn
from app.services.club_squad_service import (
    CLUB_TEMPLATE_COUNT, activate_club_lineup_template, get_club_lineup, list_club_lineup_templates,
    rename_club_lineup_template, set_club_lineup,
)
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _seed_position_pool(db_session):
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


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


async def test_five_club_lineup_templates_lazily_created(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870001, "Клуб шаблонов")
    user = await get_user_by_telegram_id(db_session, 870001)

    templates = await list_club_lineup_templates(db_session, user)
    assert len(templates) == CLUB_TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    # seed_starting_squad already filled template 1 with a complete XI.
    assert templates[0].is_complete is True
    assert templates[1].name == "Шаблон 2"
    assert templates[1].is_complete is False


async def test_rename_club_lineup_template(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870002, "Клуб переименований")
    user = await get_user_by_telegram_id(db_session, 870002)

    result = await rename_club_lineup_template(db_session, user, 2, "Оборонительный")
    assert result.name == "Оборонительный"
    templates = await list_club_lineup_templates(db_session, user)
    assert templates[1].name == "Оборонительный"


async def test_activate_club_lineup_template_swaps_active_flag(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870003, "Клуб переключений")
    user = await get_user_by_telegram_id(db_session, 870003)

    result = await activate_club_lineup_template(db_session, user, 3)
    assert result.template_index == 3
    assert result.is_active is True

    templates = await list_club_lineup_templates(db_session, user)
    assert templates[0].is_active is False  # template 1, previously active
    assert templates[2].is_active is True   # template 3, now active


async def test_editing_non_active_template_does_not_disturb_active_one(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870004, "Клуб независимых шаблонов")
    user = await get_user_by_telegram_id(db_session, 870004)

    before = await get_club_lineup(db_session, user)  # active = template 1, complete
    assert before.is_complete is True

    # Editing template 2 (empty formation slots, no cards assigned) must not
    # touch template 1's own completeness/content.
    result = await set_club_lineup(db_session, user, ClubLineupSetRequest(slots=[]), template_index=2)
    assert result.template_index == 2
    assert result.is_complete is False

    after = await get_club_lineup(db_session, user)
    assert after.template_index == 1
    assert after.is_complete is True


async def test_get_club_lineup_with_no_args_returns_active_template(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870005, "Клуб дефолта")
    user = await get_user_by_telegram_id(db_session, 870005)

    await activate_club_lineup_template(db_session, user, 4)
    result = await get_club_lineup(db_session, user)
    assert result.template_index == 4
    assert result.is_active is True
```

- [ ] **Step 2: Run**

Run: `docker compose exec backend pytest tests/test_club_lineup_templates.py -v`
Expected: all 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_club_lineup_templates.py
git commit -m "test(clubs): add club lineup template coverage"
```

---

### Task 9: Frontend — types, API client, template switcher

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/clubSquad.ts`
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

- [ ] **Step 1: Extend `ClubLineup` type**

```typescript
export interface ClubLineup {
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  tactical_fit_hint: string;
  coach: EquippedCoach | null;
  slots: ClubLineupSlot[];
  training_uses_remaining: number;
  training_boost_active: boolean;
  in_active_tournament: boolean;
  attack: number;
  midfield: number;
  defence: number;
  goalkeeping: number;
}
```

(Only `template_index`/`name`/`is_active` are new, inserted at the top.)

- [ ] **Step 2: Add template API functions**

```typescript
export async function fetchClubLineupTemplates(): Promise<ClubLineup[]> {
  const { data } = await api.get<ClubLineup[]>("/clubs/me/lineup/templates");
  return data;
}

export async function setClubLineupTemplate(
  templateIndex: number, slots: { slot_code: string; club_card_id: number }[],
): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}`, { slots });
  return data;
}

export async function setClubTacticsTemplate(
  templateIndex: number, payload: { formation: string; mentality: string; playstyle: string },
): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/tactics/templates/${templateIndex}`, payload);
  return data;
}

export async function setClubCoachTemplate(templateIndex: number, clubCoachCardId: number | null): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/coach/templates/${templateIndex}`, { club_coach_card_id: clubCoachCardId });
  return data;
}

export async function renameClubLineupTemplate(templateIndex: number, name: string): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}/name`, { name });
  return data;
}

export async function activateClubLineupTemplate(templateIndex: number): Promise<ClubLineup> {
  const { data } = await api.post<ClubLineup>(`/clubs/me/lineup/templates/${templateIndex}/activate`);
  return data;
}
```

- [ ] **Step 3: Rework `ClubSquadPage.tsx` around a selected template**

Replace the whole import line for `@/api/clubSquad` with:

```typescript
import {
  activateClubLineupTemplate, activateClubTraining, fetchClubCards, fetchClubCoachCards, fetchClubLineupTemplates,
  renameClubLineupTemplate, setClubCoachTemplate, setClubLineupTemplate, setClubTacticsTemplate,
} from "@/api/clubSquad";
```

Replace the lineup query and add template-selection state (right after
the existing `canEdit` line):

```typescript
  const { data: templates, isLoading: lineupLoading } = useQuery({ queryKey: ["clubs", "lineup-templates"], queryFn: fetchClubLineupTemplates });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const lineup = templates?.find((t) => t.template_index === viewedIndex);
```

Replace the three edit mutations' `mutationFn`s and invalidation keys:

```typescript
  const setLineupMutation = useMutation({
    mutationFn: (slots: { slot_code: string; club_card_id: number }[]) => setClubLineupTemplate(viewedIndex, slots),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }); queryClient.invalidateQueries({ queryKey: ["clubs", "cards"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticsMutation = useMutation({
    mutationFn: (payload: { formation: string; mentality: string; playstyle: string }) => setClubTacticsTemplate(viewedIndex, payload),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }); queryClient.invalidateQueries({ queryKey: ["clubs", "cards"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить тактику")),
  });

  const setCoachMutation = useMutation({
    mutationFn: (clubCoachCardId: number | null) => setClubCoachTemplate(viewedIndex, clubCoachCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }); setCoachPickerOpen(false); },
    onError: (err) => setError(formatGameError(err, "Не удалось назначить тренера")),
  });

  const trainingMutation = useMutation({
    mutationFn: activateClubTraining,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }),
    onError: (err) => setError(formatGameError(err, "Не удалось активировать тренировку")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateClubLineupTemplate(viewedIndex),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }),
    onError: (err) => setError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const [renamingTemplate, setRenamingTemplate] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const renameMutation = useMutation({
    mutationFn: (name: string) => renameClubLineupTemplate(viewedIndex, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup-templates"] }); setRenamingTemplate(false); },
  });
```

(`trainingMutation`'s `onSuccess` changes from
`queryClient.setQueryData(["clubs", "lineup"], data)` to a plain
invalidate of the new `["clubs", "lineup-templates"]` key — training
applies to the active template, and invalidating triggers a refetch that
correctly reflects it there.)

- [ ] **Step 4: Add the template switcher UI, gated by `canEdit`**

Insert right after the `{!canEdit && club && (...)}` block and before the
`{error && ...}` line:

```tsx
      {canEdit && (
        <>
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
              onClick={() => { setRenameValue(lineup?.name ?? ""); setRenamingTemplate(true); }}
              className="self-start text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2"
            >
              Переименовать «{lineup?.name}»
            </button>
          )}

          {viewedIndex !== activeIndex && (
            <button
              onClick={() => activateMutation.mutate()}
              disabled={activateMutation.isPending}
              className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
            >
              {activateMutation.isPending ? "Переключаем..." : `Сделать «${lineup?.name}» активным для матчей`}
            </button>
          )}
        </>
      )}
```

(Non-managers never see the switcher at all — they only ever view the
active template, same as `lineup` already resolves to when `templates` is
loaded and `selectedIndex` is `null`.)

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Live verification**

Rebuild containers, then in the Browser pane, as a club manager:
1. Open the club squad page, confirm 5 template pills (only visible to
   managers), template 1 marked "Активный" and showing the seeded XI.
2. Switch to template 2 — confirm it's empty, `canEdit` controls still
   work (assign a slot, set tactics, equip a coach) scoped to template 2.
3. Activate template 2 — confirm the pill state flips and the top-level
   "Состав {formation}" / strength / line-stat numbers now reflect
   template 2 (once selection resets to viewing the active one, or by
   reselecting it).
4. As a non-manager club member, confirm no switcher renders and the page
   shows only the active template exactly as before this change.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/clubSquad.ts frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(clubs): add 5-template switcher to club squad page"
```

## Definition of Done (Phase 3)

- 5 new backend tests pass; `test_club_squad.py` passes unmodified;
  tournament-queue tests pass unmodified.
- `npm run typecheck` clean.
- Live-verified: template switch, manager-only gating preserved, opponent
  preview / tournament flows unaffected (still resolve to the active
  template with zero code changes in those consumers beyond Task 6's
  one-line fix).
