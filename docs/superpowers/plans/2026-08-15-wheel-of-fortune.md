# Wheel of Fortune Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily prize-reel mechanic (coins/packs/rare-epic-legendary cards/badges), with 2 free spins/day and paid spins (coins or Telegram Stars), fully admin-configurable via weighted prize entries.

**Architecture:** New `WheelPrize` (admin-managed weighted prize pool) and `WheelSpin` (one row per spin, the durable "receipt" — same role `PackOpening`/`Gift` play for their reward types) tables. A single `wheel_service.py` funnels all three payment paths (free / coins / Stars) through one `_roll_prize` + `_grant_prize` pair, so odds and granting logic exist in exactly one place. The Stars path reuses the existing `StarsInvoice` + bot-relay mechanism used by packs/gifts/coin top-ups.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pytest (async, in-memory SQLite) on the backend; React 18, TypeScript, TanStack Query, Framer Motion on the frontend; aiogram 3 for the bot's payment relay.

## Global Constraints

- Free spins: `GameConfig.wheel_free_spins_per_day` (default 2), reset at local midnight — same pattern as `hangman_rewarded_attempts_today`/`hangman_attempts_reset_at` (`local_today()` comparison, see `backend/app/services/hangman_service.py:60-63`).
- Paid spin costs: `GameConfig.wheel_spin_cost_coins` (default 1000) and `GameConfig.wheel_spin_cost_stars` (default 10), both admin-editable, no daily cap on paid spins.
- Duplicate badge prize: credit `GameConfig.wheel_duplicate_badge_coins` (default 200) instead of a second `UserBadge` row.
- Card-rarity prizes (`rare`/`epic`/`legendary`) are three independent `WheelPrize` rows, each with its own admin-set `weight` — no rarity-internal sub-roll.
- Reel is a horizontal "carousel" strip (center prize enlarged/outlined), not a circular wheel — uses the app's real icon set (`IconCoin`, `IconPack`, `IconCard`), never emoji, per `docs/superpowers/specs/2026-08-15-wheel-of-fortune-design.md`.
- Never trust client-supplied values for balances or prize odds — all rolling and granting happens server-side (existing project rule, CLAUDE.md).
- Use row locking (`lock_user_for_update`) for every balance-mutating spin path — matches every other coin-spending flow in this codebase.

---

## File Structure

**Backend — new files:**
- `backend/app/models/wheel.py` — `WheelPrize`, `WheelSpin` models.
- `backend/alembic/versions/0042_wheel_of_fortune.py` — migration.
- `backend/app/schemas/wheel.py` — all wheel Pydantic schemas.
- `backend/app/services/wheel_service.py` — roll/grant/spin logic.
- `backend/app/routers/wheel.py` — player-facing endpoints.
- `backend/app/routers/admin_wheel.py` — admin CRUD for `WheelPrize`.
- `backend/tests/test_wheel.py` — all backend wheel tests.

**Backend — modified files:**
- `backend/app/models/enums.py` — `WheelPrizeType`, `WheelSpinSource`, new `CardSource`/`TransactionType` members.
- `backend/app/models/user.py` — 2 new columns.
- `backend/app/models/game_config.py` — 4 new columns.
- `backend/app/models/pack.py` — 2 new columns on `StarsInvoice`.
- `backend/app/models/__init__.py` — register `WheelPrize`, `WheelSpin`.
- `backend/app/schemas/stars.py` — `wheel_result` field + `WheelSpinResultOut` import.
- `backend/app/schemas/admin.py` — 4 new `GameConfigOut`/`GameConfigUpdate` fields.
- `backend/app/services/stars_payment_service.py` — wheel branch in `create_invoice`-equivalent, `validate_pre_checkout`, `deliver_payment`, `_delivered_result`.
- `backend/app/main.py` — register the 2 new routers.
- `backend/tests/factories.py` — `create_wheel_prize` helper.
- `bot/handlers/payments.py` — a `wheel_result` message branch.

**Frontend — new files:**
- `frontend/src/api/wheel.ts`
- `frontend/src/pages/WheelPage.tsx`
- `frontend/src/admin/pages/AdminWheelPage.tsx`

**Frontend — modified files:**
- `frontend/src/types/index.ts` — wheel types.
- `frontend/src/admin/types.ts` — admin wheel types + 4 new `GameConfig` fields.
- `frontend/src/admin/api.ts` — wheel CRUD calls.
- `frontend/src/pages/HomePage.tsx` — teaser `NoticeCard`.
- `frontend/src/App.tsx` — `/wheel` and `/admin/wheel` routes.
- `frontend/src/admin/AdminLayout.tsx` — nav entry.
- `frontend/src/admin/pages/AdminGamesPage.tsx` — 4 new economy fields.

---

### Task 1: Data model — enums, columns, `WheelPrize`/`WheelSpin`, migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/game_config.py`
- Modify: `backend/app/models/pack.py`
- Create: `backend/app/models/wheel.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0042_wheel_of_fortune.py`
- Modify: `backend/tests/factories.py`
- Test: `backend/tests/test_wheel.py`

**Interfaces:**
- Produces: `WheelPrizeType` (`coins`/`pack`/`card_rarity`/`badge`), `WheelSpinSource` (`free`/`coins`/`stars`) enums; `WheelPrize` model (`id, prize_type, weight, is_active, sort_order, coins_amount, pack_id, card_rarity, badge_id, pack, badge`); `WheelSpin` model (`id, user_id, prize_id, source, pack_opening_id, user_card_id, badge_granted, duplicate_badge_coins, coins_amount, created_at, prize`); `User.wheel_free_spins_used_today: int`, `User.wheel_spins_reset_at: datetime | None`; `GameConfig.wheel_free_spins_per_day/wheel_spin_cost_coins/wheel_spin_cost_stars/wheel_duplicate_badge_coins: int`; `StarsInvoice.is_wheel_spin: bool`, `StarsInvoice.wheel_spin_id: int | None`; `CardSource.wheel`; `TransactionType.wheel_spin_cost`/`wheel_spin_reward`; `tests.factories.create_wheel_prize(session, prize_type, weight=1, **overrides) -> WheelPrize`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_wheel.py`:

```python
from app.models.enums import CardSource, TransactionType, WheelPrizeType, WheelSpinSource
from app.models.wheel import WheelPrize, WheelSpin
from tests.factories import create_wheel_prize


async def test_wheel_prize_model_roundtrip(db_session):
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=10, coins_amount=50)
    assert prize.id is not None
    assert prize.weight == 10
    assert prize.coins_amount == 50
    assert prize.is_active is True


async def test_wheel_spin_model_roundtrip(db_session):
    from tests.factories import create_player, create_pack, get_user_by_telegram_id
    from tests.utils import telegram_headers

    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, coins_amount=25)
    spin = WheelSpin(user_id=1, prize_id=prize.id, source=WheelSpinSource.free, coins_amount=25)
    db_session.add(spin)
    await db_session.commit()
    await db_session.refresh(spin)
    assert spin.id is not None
    assert spin.source == WheelSpinSource.free


def test_new_enum_members_exist():
    assert CardSource.wheel == "wheel"
    assert TransactionType.wheel_spin_cost == "wheel_spin_cost"
    assert TransactionType.wheel_spin_reward == "wheel_spin_reward"
    assert WheelPrizeType.card_rarity == "card_rarity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.wheel'` (and `ImportError` for `WheelPrizeType`/`WheelSpinSource`/`create_wheel_prize`).

- [ ] **Step 3: Add new enum members to `backend/app/models/enums.py`**

Add `wheel = "wheel"` as the last member of `CardSource` (after `gift = "gift"`).

Add `wheel_spin_cost = "wheel_spin_cost"` and `wheel_spin_reward = "wheel_spin_reward"` as the last two members of `TransactionType` (after `gift_coins = "gift_coins"`).

Add two new enum classes at the end of the file:

```python
class WheelPrizeType(str, enum.Enum):
    coins = "coins"
    pack = "pack"
    card_rarity = "card_rarity"
    badge = "badge"


class WheelSpinSource(str, enum.Enum):
    free = "free"
    coins = "coins"
    stars = "stars"
```

- [ ] **Step 4: Create `backend/app/models/wheel.py`**

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity, WheelPrizeType, WheelSpinSource
from app.models.mixins import TimestampMixin, utcnow
from sqlalchemy import Enum as SAEnum


class WheelPrize(TimestampMixin, Base):
    """One admin-configured entry in the wheel's prize pool. Selected by
    weighted random pick (see wheel_service._roll_prize) — weight is a plain
    relative number, not a normalized probability, so an admin can add or
    remove entries without rebalancing everything else to sum to 1.

    Exactly one of coins_amount/pack_id/card_rarity/badge_id is set,
    matching prize_type — enforced at the application layer (schemas +
    service), not a DB constraint, mirroring how Pack/GiftSet handle their
    own similarly-shaped "one of several optional fields" data.
    """

    __tablename__ = "wheel_prizes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prize_type: Mapped[WheelPrizeType] = mapped_column(SAEnum(WheelPrizeType, name="wheel_prize_type_enum"), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    coins_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="CASCADE"), nullable=True)
    card_rarity: Mapped[Optional[Rarity]] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=True)
    badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), nullable=True)

    pack: Mapped[Optional["Pack"]] = relationship(lazy="joined")
    badge: Mapped[Optional["Badge"]] = relationship(lazy="joined")


class WheelSpin(Base):
    """One row per spin, regardless of payment path — the durable "receipt"
    for what was won, filling the same role PackOpening/Gift play for their
    reward types. Needed so a Stars-paid spin's invoice-status poll
    (StarsInvoiceStatusOut) can reconstruct "what did this delivered
    invoice actually grant" after the fact (see
    stars_payment_service._delivered_result)."""

    __tablename__ = "wheel_spins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("wheel_prizes.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[WheelSpinSource] = mapped_column(SAEnum(WheelSpinSource, name="wheel_spin_source_enum"), nullable=False)

    pack_opening_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True)
    badge_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_badge_coins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    prize: Mapped["WheelPrize"] = relationship(lazy="joined")
```

- [ ] **Step 5: Add columns to `backend/app/models/user.py`**

Add next to the other `*_reset_at`/`*_today` pairs (e.g. right after the `daily_login_streak` field):

```python
    wheel_free_spins_used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wheel_spins_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

(`Optional` and `datetime`/`DateTime`/`Integer`/`mapped_column` are already imported in this file — every other `*_reset_at` column uses the identical imports.)

- [ ] **Step 6: Add columns to `backend/app/models/game_config.py`**

Add at the end of the class body:

```python
    wheel_free_spins_per_day: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    wheel_spin_cost_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    wheel_spin_cost_stars: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    wheel_duplicate_badge_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
```

- [ ] **Step 7: Add columns to `StarsInvoice` in `backend/app/models/pack.py`**

Add just before `completed_at: Mapped[Optional[datetime]] = mapped_column(...)` at the end of the `StarsInvoice` class:

```python
    # Set together for a wheel-spin Stars purchase (never with pack_id/
    # gift_set_id/coins_amount). wheel_spin_id is filled in at delivery,
    # once the WheelSpin row exists — mirrors pack_opening_id/gift_id above.
    is_wheel_spin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wheel_spin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wheel_spins.id", ondelete="SET NULL"), nullable=True)
```

- [ ] **Step 8: Register the new models in `backend/app/models/__init__.py`**

Add `from app.models.wheel import WheelPrize, WheelSpin` (alphabetically after the `trophy` import, before `user`), and add `"WheelPrize"`, `"WheelSpin"` to `__all__` in the same relative position.

- [ ] **Step 9: Add `create_wheel_prize` to `backend/tests/factories.py`**

Add near `create_badge`:

```python
from app.models.wheel import WheelPrize


async def create_wheel_prize(session, prize_type, weight: int = 1, **overrides) -> WheelPrize:
    defaults = dict(is_active=True, sort_order=0, coins_amount=None, pack_id=None, card_rarity=None, badge_id=None)
    defaults.update(overrides)
    prize = WheelPrize(prize_type=prize_type, weight=weight, **defaults)
    session.add(prize)
    await session.commit()
    await session.refresh(prize)
    return prize
```

(Add the import line alongside the other `from app.models.* import ...` lines at the top of the file.)

- [ ] **Step 10: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: 3 passed.

- [ ] **Step 11: Write the migration**

Create `backend/alembic/versions/0042_wheel_of_fortune.py`:

```python
"""Wheel of fortune: weighted prize pool, spin history, Stars-spin support

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

wheel_prize_type_enum = postgresql.ENUM("coins", "pack", "card_rarity", "badge", name="wheel_prize_type_enum", create_type=False)
wheel_spin_source_enum = postgresql.ENUM("free", "coins", "stars", name="wheel_spin_source_enum", create_type=False)

NEW_ENUMS = [wheel_prize_type_enum, wheel_spin_source_enum]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'wheel'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'wheel_spin_cost'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'wheel_spin_reward'")

    op.add_column("users", sa.Column("wheel_free_spins_used_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("wheel_spins_reset_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("wheel_free_spins_per_day", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("wheel_spin_cost_coins", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("game_config", sa.Column("wheel_spin_cost_stars", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("wheel_duplicate_badge_coins", sa.Integer(), nullable=False, server_default="200"))

    op.create_table(
        "wheel_prizes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prize_type", wheel_prize_type_enum, nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coins_amount", sa.Integer(), nullable=True),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("card_rarity", postgresql.ENUM(name="rarity_enum", create_type=False), nullable=True),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "wheel_spins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prize_id", sa.Integer(), sa.ForeignKey("wheel_prizes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", wheel_spin_source_enum, nullable=False),
        sa.Column("pack_opening_id", sa.Integer(), sa.ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("badge_granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duplicate_badge_coins", sa.Integer(), nullable=True),
        sa.Column("coins_amount", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_wheel_spins_user_id", "wheel_spins", ["user_id"])

    op.add_column("stars_invoices", sa.Column("is_wheel_spin", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("stars_invoices", sa.Column("wheel_spin_id", sa.Integer(), sa.ForeignKey("wheel_spins.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("stars_invoices", "wheel_spin_id")
    op.drop_column("stars_invoices", "is_wheel_spin")

    op.drop_index("ix_wheel_spins_user_id", table_name="wheel_spins")
    op.drop_table("wheel_spins")
    op.drop_table("wheel_prizes")

    op.drop_column("game_config", "wheel_duplicate_badge_coins")
    op.drop_column("game_config", "wheel_spin_cost_stars")
    op.drop_column("game_config", "wheel_spin_cost_coins")
    op.drop_column("game_config", "wheel_free_spins_per_day")

    op.drop_column("users", "wheel_spins_reset_at")
    op.drop_column("users", "wheel_free_spins_used_today")

    for enum_type in NEW_ENUMS:
        enum_type.drop(op.get_bind(), checkfirst=True)
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'wheel'/
    # 'wheel_spin_cost'/'wheel_spin_reward' on their enums on downgrade is
    # harmless (mirrors 0035's note on the same limitation).
```

- [ ] **Step 12: Full backend import sanity check**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no errors (confirms the new models, the migration's enum object names, and `__init__.py` registration are all consistent).

- [ ] **Step 13: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/user.py backend/app/models/game_config.py backend/app/models/pack.py backend/app/models/wheel.py backend/app/models/__init__.py backend/alembic/versions/0042_wheel_of_fortune.py backend/tests/factories.py backend/tests/test_wheel.py
git commit -m "Add wheel-of-fortune data model: WheelPrize, WheelSpin, config/User columns"
```

---

### Task 2: `wheel_service.py` — status, weighted roll, prize granting, free + coin-paid spins

**Files:**
- Create: `backend/app/services/wheel_service.py`
- Create: `backend/app/schemas/wheel.py`
- Test: `backend/tests/test_wheel.py` (append)

**Interfaces:**
- Consumes: `WheelPrize`/`WheelSpin`/`WheelPrizeType`/`WheelSpinSource` (Task 1); `lock_user_for_update`/`credit_coins`/`debit_coins` (`app.services.wallet_service`); `get_config` (`app.services.game_config_service`); `local_today`/`ensure_aware` (`app.core.timeutil`); `pick_random_player`/`roll_and_create_cards`-style card grant via `card_creation.create_user_card` + `pack_service.pick_random_player`; `grant_bonus_pack_opening`-equivalent pack grant via `pack_service.roll_and_create_cards` (see below); `UserBadge` (`app.models.badge`).
- Produces: `wheel_service.get_status(db, user) -> WheelStatusOut`, `wheel_service.spin_free(db, user) -> WheelSpinResultOut`, `wheel_service.spin_paid_coins(db, user) -> WheelSpinResultOut`, `wheel_service._roll_prize(db) -> WheelPrize`, `wheel_service._grant_prize(db, user, prize, source) -> WheelSpinResultOut` (used by Task 4's Stars delivery path too). Schemas: `WheelPrizeOut`, `WheelStatusOut`, `WheelSpinResultOut`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_wheel.py`:

```python
from app.core.exceptions import ConflictError, InsufficientBalanceError
from app.models.badge import UserBadge
from app.models.enums import Rarity, WheelPrizeType
from app.models.game_config import GameConfig
from app.services import wheel_service
from tests.factories import create_badge, create_pack, create_player, create_wheel_prize, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_roll_prize_picks_only_active_weighted(db_session):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=100, coins_amount=10)
    inactive = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=100, coins_amount=999, is_active=False)

    for _ in range(20):
        prize = await wheel_service._roll_prize(db_session)
        assert prize.id != inactive.id


async def test_roll_prize_raises_when_no_active_prizes(db_session):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=10, is_active=False)
    with pytest.raises(ConflictError):
        await wheel_service._roll_prize(db_session)


async def test_grant_coins_prize_credits_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 860001, bot_token)
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=77)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()
    await db_session.refresh(user)

    assert result.prize.id == prize.id
    assert user.balance == 500 + 77
    assert result.new_balance == 500 + 77


async def test_grant_pack_prize_opens_cards(client, db_session, bot_token):
    user = await _register(client, db_session, 860002, bot_token)
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "wheel-pack", price=0, card_count=2, probabilities={Rarity.common: 1.0})
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.pack, weight=1, pack_id=pack.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.pack_result is not None
    assert len(result.pack_result.cards) == 2


async def test_grant_card_rarity_prize_grants_one_card_of_that_rarity(client, db_session, bot_token):
    user = await _register(client, db_session, 860003, bot_token)
    await create_player(db_session, rarity=Rarity.legendary)
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.card_rarity, weight=1, card_rarity=Rarity.legendary)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.card_result is not None
    assert result.card_result.card.player.rarity == Rarity.legendary


async def test_grant_badge_prize_grants_new_badge(client, db_session, bot_token):
    user = await _register(client, db_session, 860004, bot_token)
    badge = await create_badge(db_session, name="Колесо", icon="🎡")
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.badge, weight=1, badge_id=badge.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.badge_result is not None
    assert result.badge_result.id == badge.id
    owned = (
        await db_session.execute(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
    ).scalar_one_or_none()
    assert owned is not None


async def test_grant_duplicate_badge_prize_credits_coins_instead(client, db_session, bot_token):
    user = await _register(client, db_session, 860005, bot_token)
    badge = await create_badge(db_session, name="Колесо", icon="🎡")
    db_session.add(UserBadge(user_id=user.id, badge_id=badge.id))
    await db_session.commit()
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.badge, weight=1, badge_id=badge.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()
    await db_session.refresh(user)

    assert result.badge_result is None
    assert result.duplicate_badge_coins == 200
    assert user.balance == 500 + 200


async def test_spin_free_consumes_daily_allowance_then_blocks(client, db_session, bot_token):
    user = await _register(client, db_session, 860006, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 1

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 2

    with pytest.raises(ConflictError):
        await wheel_service.spin_free(db_session, user)


async def test_spin_free_resets_on_a_new_day(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 860007, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    user.wheel_free_spins_used_today = 2
    user.wheel_spins_reset_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add(user)
    await db_session.commit()

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 1


async def test_spin_paid_coins_debits_configured_cost(client, db_session, bot_token):
    user = await _register(client, db_session, 860008, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    config = await db_session.get(GameConfig, 1)
    config.wheel_spin_cost_coins = 300
    db_session.add(config)
    await db_session.commit()

    result = await wheel_service.spin_paid_coins(db_session, user)
    await db_session.refresh(user)
    assert user.balance == 500 - 300 + 1
    assert result.new_balance == user.balance


async def test_spin_paid_coins_rejects_insufficient_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 860009, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    config = await db_session.get(GameConfig, 1)
    config.wheel_spin_cost_coins = 999999
    db_session.add(config)
    await db_session.commit()

    with pytest.raises(InsufficientBalanceError):
        await wheel_service.spin_paid_coins(db_session, user)


async def test_get_status_reports_remaining_free_spins_and_active_prizes(client, db_session, bot_token):
    user = await _register(client, db_session, 860010, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=2, is_active=False)

    status = await wheel_service.get_status(db_session, user)
    assert status.free_spins_remaining == 2
    assert status.free_spins_total == 2
    assert len(status.prizes) == 1
```

Add `import pytest` and `from sqlalchemy import select` at the top of `backend/tests/test_wheel.py` if not already present from Task 1 (Task 1's file did not need them).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.wheel_service'`.

- [ ] **Step 3: Create `backend/app/schemas/wheel.py`**

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity, WheelPrizeType
from app.schemas.badge import BadgeOut
from app.schemas.pack import OpenedCardOut, PackOpenResult, PackOut


class WheelPrizeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prize_type: WheelPrizeType
    weight: int
    is_active: bool
    sort_order: int
    coins_amount: Optional[int] = None
    pack_id: Optional[int] = None
    pack: Optional[PackOut] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    badge: Optional[BadgeOut] = None


class WheelPrizeCreate(BaseModel):
    prize_type: WheelPrizeType
    weight: int = Field(default=1, ge=1)
    coins_amount: Optional[int] = Field(default=None, ge=0)
    pack_id: Optional[int] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0


class WheelPrizeUpdate(BaseModel):
    prize_type: Optional[WheelPrizeType] = None
    weight: Optional[int] = Field(default=None, ge=1)
    coins_amount: Optional[int] = Field(default=None, ge=0)
    pack_id: Optional[int] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class WheelStatusOut(BaseModel):
    free_spins_remaining: int
    free_spins_total: int
    next_free_spin_reset_at: datetime
    spin_cost_coins: int
    spin_cost_stars: int
    prizes: list[WheelPrizeOut]


class WheelSpinResultOut(BaseModel):
    prize: WheelPrizeOut
    new_balance: int
    pack_result: Optional[PackOpenResult] = None
    card_result: Optional[OpenedCardOut] = None
    badge_result: Optional[BadgeOut] = None
    duplicate_badge_coins: Optional[int] = None
```

- [ ] **Step 4: Create `backend/app/services/wheel_service.py`**

```python
import random
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, local_today
from app.models.badge import UserBadge
from app.models.enums import CardSource, TransactionType, WheelPrizeType, WheelSpinSource
from app.models.pack import PackOpening
from app.models.user import User
from app.models.wheel import WheelPrize, WheelSpin
from app.schemas.badge import BadgeOut
from app.schemas.pack import OpenedCardOut, PackOpenResult, PackOut
from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut, WheelStatusOut
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.pack_service import _get_pack_or_404, _duplicate_counts_snapshot, pick_random_player, roll_and_create_cards
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


def _next_local_midnight_utc() -> datetime:
    tomorrow = local_today() + timedelta(days=1)
    midnight_local = datetime.combine(tomorrow, time.min, tzinfo=app_timezone())
    return midnight_local.astimezone(timezone.utc)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.wheel_spins_reset_at) if user.wheel_spins_reset_at else None
    if reset_day != today:
        user.wheel_free_spins_used_today = 0
        user.wheel_spins_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _active_prizes(db: AsyncSession) -> list[WheelPrize]:
    result = await db.execute(select(WheelPrize).where(WheelPrize.is_active.is_(True)).order_by(WheelPrize.sort_order))
    return list(result.scalars().all())


async def get_status(db: AsyncSession, user: User) -> WheelStatusOut:
    config = await get_config(db)
    await _ensure_daily_reset(db, user)
    prizes = await _active_prizes(db)
    return WheelStatusOut(
        free_spins_remaining=max(0, config.wheel_free_spins_per_day - user.wheel_free_spins_used_today),
        free_spins_total=config.wheel_free_spins_per_day,
        next_free_spin_reset_at=_next_local_midnight_utc(),
        spin_cost_coins=config.wheel_spin_cost_coins,
        spin_cost_stars=config.wheel_spin_cost_stars,
        prizes=[WheelPrizeOut.model_validate(p) for p in prizes],
    )


async def _roll_prize(db: AsyncSession) -> WheelPrize:
    prizes = await _active_prizes(db)
    if not prizes:
        raise ConflictError("The wheel has no active prizes configured; contact support")
    return random.choices(prizes, weights=[p.weight for p in prizes], k=1)[0]


async def _grant_prize(db: AsyncSession, user: User, prize: WheelPrize, source: WheelSpinSource) -> WheelSpinResultOut:
    spin = WheelSpin(user_id=user.id, prize_id=prize.id, source=source)

    pack_result: PackOpenResult | None = None
    card_result = None
    badge_result: BadgeOut | None = None
    duplicate_badge_coins: int | None = None

    if prize.prize_type == WheelPrizeType.coins:
        await credit_coins(
            db, user, prize.coins_amount, TransactionType.wheel_spin_reward,
            "Приз колеса фортуны: монеты", related_object_type="wheel_prize", related_object_id=prize.id,
        )
        spin.coins_amount = prize.coins_amount

    elif prize.prize_type == WheelPrizeType.pack:
        pack = await _get_pack_or_404(db, prize.pack_id)
        opening = PackOpening(
            user_id=user.id, pack_id=pack.id, price_paid=0,
            idempotency_key=f"wheel-{user.id}-{datetime.now(timezone.utc).timestamp()}",
            created_at=datetime.now(timezone.utc),
        )
        db.add(opening)
        await db.flush()
        dup_counts = await _duplicate_counts_snapshot(db, user.id)
        opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, CardSource.wheel)
        pack_result = PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=opened_items, new_balance=user.balance)
        spin.pack_opening_id = opening.id

    elif prize.prize_type == WheelPrizeType.card_rarity:
        player = await pick_random_player(db, prize.card_rarity)
        dup_counts = await _duplicate_counts_snapshot(db, user.id)
        user_card = await create_user_card(db, user.id, player.id, CardSource.wheel)
        user_card.player = player
        is_new = dup_counts.get(player.id, 0) == 0
        card_result = OpenedCardOut(card=user_card, is_new=is_new, duplicate_count=dup_counts.get(player.id, 0) + 1)
        spin.user_card_id = user_card.id

    elif prize.prize_type == WheelPrizeType.badge:
        config = await get_config(db)
        existing = await db.execute(
            select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == prize.badge_id)
        )
        if existing.scalar_one_or_none() is None:
            db.add(UserBadge(user_id=user.id, badge_id=prize.badge_id))
            badge_result = BadgeOut.model_validate(prize.badge)
            spin.badge_granted = True
        else:
            await credit_coins(
                db, user, config.wheel_duplicate_badge_coins, TransactionType.wheel_spin_reward,
                "Приз колеса фортуны: повтор значка (компенсация)",
                related_object_type="wheel_prize", related_object_id=prize.id,
            )
            duplicate_badge_coins = config.wheel_duplicate_badge_coins
            spin.duplicate_badge_coins = duplicate_badge_coins

    db.add(spin)
    db.add(user)
    await db.flush()

    return WheelSpinResultOut(
        prize=WheelPrizeOut.model_validate(prize),
        new_balance=user.balance,
        pack_result=pack_result,
        card_result=card_result,
        badge_result=badge_result,
        duplicate_badge_coins=duplicate_badge_coins,
    )


async def spin_free(db: AsyncSession, user: User) -> WheelSpinResultOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_daily_reset(db, locked_user)
    if locked_user.wheel_free_spins_used_today >= config.wheel_free_spins_per_day:
        raise ConflictError(
            "No free spins left today",
            details={"next_reset_at": _next_local_midnight_utc().isoformat()},
        )
    locked_user.wheel_free_spins_used_today += 1

    prize = await _roll_prize(db)
    result = await _grant_prize(db, locked_user, prize, WheelSpinSource.free)
    await db.commit()
    return result


async def spin_paid_coins(db: AsyncSession, user: User) -> WheelSpinResultOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await debit_coins(
        db, locked_user, config.wheel_spin_cost_coins, TransactionType.wheel_spin_cost,
        "Платная прокрутка колеса фортуны",
    )

    prize = await _roll_prize(db)
    result = await _grant_prize(db, locked_user, prize, WheelSpinSource.coins)
    await db.commit()
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: all passed.

- [ ] **Step 6: Full test suite regression check**

Run: `docker compose exec backend pytest tests/ -q`
Expected: no new failures (existing `pack_service`/`card_creation` functions are only imported, not modified).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/wheel.py backend/app/services/wheel_service.py backend/tests/test_wheel.py
git commit -m "Add wheel_service: weighted roll, all 4 prize grant types, free/coin-paid spins"
```

---

### Task 3: Player-facing router (`/wheel/status`, `/wheel/spin/free`, `/wheel/spin/coins`)

**Files:**
- Create: `backend/app/routers/wheel.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_wheel.py` (append)

**Interfaces:**
- Consumes: `wheel_service.get_status`/`spin_free`/`spin_paid_coins` (Task 2); `get_current_user`/`get_db` (existing, see `backend/app/routers/free_pack.py` for the exact dependency pattern).
- Produces: `GET /api/v1/wheel/status`, `POST /api/v1/wheel/spin/free`, `POST /api/v1/wheel/spin/coins` — consumed by the frontend in Task 7.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_wheel.py`:

```python
async def test_status_and_free_spin_endpoints(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    await _register(client, db_session, 860020, bot_token)
    headers = telegram_headers(860020, bot_token)

    status_resp = await client.get("/api/v1/wheel/status", headers=headers)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["free_spins_remaining"] == 2
    assert len(body["prizes"]) == 1

    spin_resp = await client.post("/api/v1/wheel/spin/free", headers=headers)
    assert spin_resp.status_code == 200
    assert spin_resp.json()["prize"]["prize_type"] == "coins"

    status_resp2 = await client.get("/api/v1/wheel/status", headers=headers)
    assert status_resp2.json()["free_spins_remaining"] == 1


async def test_free_spin_exhausted_returns_409(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    await _register(client, db_session, 860021, bot_token)
    headers = telegram_headers(860021, bot_token)

    for _ in range(2):
        assert (await client.post("/api/v1/wheel/spin/free", headers=headers)).status_code == 200

    resp = await client.post("/api/v1/wheel/spin/free", headers=headers)
    assert resp.status_code == 409


async def test_paid_coin_spin_endpoint(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    await _register(client, db_session, 860022, bot_token)
    headers = telegram_headers(860022, bot_token)

    resp = await client.post("/api/v1/wheel/spin/coins", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 500 - 1000 + 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_wheel.py -k "status_and_free or exhausted or paid_coin" -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Create `backend/app/routers/wheel.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.wheel import WheelSpinResultOut, WheelStatusOut
from app.services import wheel_service

router = APIRouter(prefix="/wheel", tags=["wheel"])


@router.get("/status", response_model=WheelStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.get_status(db, user)


@router.post("/spin/free", response_model=WheelSpinResultOut)
async def spin_free(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_free(db, user)


@router.post("/spin/coins", response_model=WheelSpinResultOut)
async def spin_paid_coins(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_paid_coins(db, user)
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Add `from app.routers import ... wheel` to the existing multi-import (alongside `trades`, matching alphabetical-ish grouping already used), and add:

```python
app.include_router(wheel.router, prefix=API_PREFIX)
```

right after `app.include_router(daily_rewards.router, prefix=API_PREFIX)` (or any consistent spot among the player-facing routers, before the `admin_*` ones).

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/wheel.py backend/app/main.py backend/tests/test_wheel.py
git commit -m "Add player-facing wheel endpoints: status, free spin, coin-paid spin"
```

---

### Task 4: Stars-paid spin (invoice creation, pre-checkout, delivery, bot message)

**Files:**
- Modify: `backend/app/services/wheel_service.py`
- Modify: `backend/app/services/stars_payment_service.py`
- Modify: `backend/app/schemas/stars.py`
- Modify: `backend/app/routers/wheel.py`
- Modify: `bot/handlers/payments.py`
- Test: `backend/tests/test_wheel.py` (append)

**Interfaces:**
- Consumes: `stars_payment_service._request_telegram_invoice_link`/`_get_invoice_or_404` (existing, `backend/app/services/stars_payment_service.py`); `StarsInvoice.is_wheel_spin`/`wheel_spin_id` (Task 1); `wheel_service._roll_prize`/`_grant_prize` (Task 2).
- Produces: `wheel_service.create_spin_invoice(db, user) -> StarsInvoiceCreateOut`; `POST /api/v1/wheel/spin/stars-invoice`; `GET /api/v1/wheel/stars-invoices/{payload_token}`; `StarsInvoiceStatusOut.wheel_result: Optional[WheelSpinResultOut]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_wheel.py`:

```python
from app.config import get_settings

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}


async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/invoice/{payload_token}"


async def test_stars_spin_full_flow(client, db_session, bot_token, monkeypatch):
    # wheel_service.create_spin_invoice calls a name it imported from
    # stars_payment_service at module load time
    # (`from app.services.stars_payment_service import _request_telegram_invoice_link`),
    # which is its own separate binding — patching
    # stars_payment_service._request_telegram_invoice_link afterwards would
    # not affect wheel_service's copy, so the mock must target
    # wheel_service's own name.
    monkeypatch.setattr(wheel_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=7)
    await _register(client, db_session, 860030, bot_token)
    headers = telegram_headers(860030, bot_token)

    invoice_resp = await client.post("/api/v1/wheel/spin/stars-invoice", headers=headers)
    assert invoice_resp.status_code == 200
    invoice = invoice_resp.json()
    assert invoice["stars_amount"] == 10  # default GameConfig.wheel_spin_cost_stars

    status_resp = await client.get(f"/api/v1/wheel/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp.json()["status"] == "pending"

    pre_checkout = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 10},
        headers=INTERNAL_HEADERS,
    )
    assert pre_checkout.json()["ok"] is True

    deliver = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 860030,
            "telegram_payment_charge_id": "wheel-charge-" + "f" * 120,
            "total_amount": 10,
        },
        headers=INTERNAL_HEADERS,
    )
    assert deliver.status_code == 200
    body = deliver.json()
    assert body["status"] == "completed"
    assert body["wheel_result"]["new_balance"] == 500 + 7

    status_resp2 = await client.get(f"/api/v1/wheel/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp2.json()["status"] == "completed"
    assert status_resp2.json()["wheel_result"]["new_balance"] == 500 + 7

    # Redelivering the same charge must not spin (and thus not credit) twice.
    second = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 860030,
            "telegram_payment_charge_id": "wheel-charge-" + "f" * 120,
            "total_amount": 10,
        },
        headers=INTERNAL_HEADERS,
    )
    assert second.json()["wheel_result"]["new_balance"] == 500 + 7
```

Add `from app.services import wheel_service` to the top of `backend/tests/test_wheel.py` if not already present (it was already imported in Task 2's step).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_wheel.py -k stars_spin_full_flow -v`
Expected: FAIL — `AttributeError` (`create_spin_invoice` doesn't exist) or 404 on `/wheel/spin/stars-invoice`.

- [ ] **Step 3: Add `wheel_result` to `backend/app/schemas/stars.py`**

Add the import and field:

```python
from app.schemas.wheel import WheelSpinResultOut
```

(add alongside the existing `from app.schemas.gift import GiftOut` / `from app.schemas.pack import PackOpenResult` imports)

```python
class StarsInvoiceStatusOut(BaseModel):
    status: Literal["pending", "completed"]
    result: Optional[PackOpenResult] = None
    coin_result: Optional[StarsCoinResultOut] = None
    gift_result: Optional[GiftOut] = None
    wheel_result: Optional[WheelSpinResultOut] = None
```

(add the `wheel_result` line to the existing class — do not otherwise change the file.)

- [ ] **Step 4: Add `create_spin_invoice` to `backend/app/services/wheel_service.py`**

Add near the bottom of the file (after `spin_paid_coins`):

```python
import secrets

from app.models.pack import StarsInvoice
from app.schemas.stars import StarsInvoiceCreateOut
from app.services.stars_payment_service import _request_telegram_invoice_link


async def create_spin_invoice(db: AsyncSession, user: User) -> StarsInvoiceCreateOut:
    config = await get_config(db)
    payload_token = secrets.token_urlsafe(16)
    invoice = StarsInvoice(
        user_id=user.id, is_wheel_spin=True, payload_token=payload_token, stars_amount=config.wheel_spin_cost_stars,
    )
    db.add(invoice)
    await db.flush()

    invoice_link = await _request_telegram_invoice_link(
        payload_token, "Прокрутка колеса фортуны", "Одна платная прокрутка колеса фортуны", config.wheel_spin_cost_stars,
    )

    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=config.wheel_spin_cost_stars)
```

Move the `import secrets` line to the top of the file with the other imports instead of inline (inline shown above only to mark where it's newly needed).

- [ ] **Step 5: Extend `backend/app/services/stars_payment_service.py`**

Change the enums import to add `WheelSpinSource`:

```python
from app.models.enums import CardSource, TransactionType, WheelSpinSource
```

Add three new imports alongside the existing `from app.models...`/`from app.schemas...`/`from app.services...` lines:

```python
from app.models.wheel import WheelSpin
from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut
from app.services import wheel_service
```

In `_delivered_result`, the function currently dispatches with two early `if` returns (`pack_id`, then `gift_set_id`) before falling through to the coin-purchase result at the bottom. Insert a third early return for wheel (position among the three doesn't matter — each is mutually exclusive and returns immediately), giving:

```python
async def _delivered_result(db: AsyncSession, invoice: StarsInvoice) -> StarsInvoiceStatusOut:
    """Reconstructs the completed result for an already-delivered invoice —
    either the granted pack or the coins credited, whichever this was for."""
    if invoice.pack_id is not None:
        user = await db.get(User, invoice.user_id)
        opening = await db.get(PackOpening, invoice.pack_opening_id)
        return StarsInvoiceStatusOut(status="completed", result=await get_opening_result(db, user, opening))

    if invoice.is_wheel_spin:
        spin = await db.get(WheelSpin, invoice.wheel_spin_id)
        user = await db.get(User, invoice.user_id)
        return StarsInvoiceStatusOut(
            status="completed",
            wheel_result=WheelSpinResultOut(
                prize=WheelPrizeOut.model_validate(spin.prize), new_balance=user.balance,
                duplicate_badge_coins=spin.duplicate_badge_coins,
            ),
        )

    if invoice.gift_set_id is not None:
        gift = await db.get(Gift, invoice.gift_id)
        return StarsInvoiceStatusOut(status="completed", gift_result=GiftOut.model_validate(gift))

    user = await db.get(User, invoice.user_id)
    return StarsInvoiceStatusOut(
        status="completed",
        coin_result=StarsCoinResultOut(coins_credited=invoice.coins_amount, new_balance=user.balance),
    )
```

(This is the whole function with the one wheel branch added — every other line matches the current file exactly.)

`validate_pre_checkout` needs **no changes**. It already rejects any payment whose `total_amount` doesn't match the invoice's frozen `stars_amount` before it ever inspects `pack_id`/`gift_set_id`, and a wheel invoice's `stars_amount` is frozen at creation the same way a plain coin-purchase invoice's is (see `create_spin_invoice`, Task 4 Step 4) — there's no "is this still available" concept for a wheel spin the way there is for a pack or gift set, so no extra branch is needed here.

In `deliver_payment`, the existing dispatch is `if invoice.pack_id is not None: ... elif invoice.gift_set_id is not None: ... else: <plain coin purchase>`. Insert a new `elif` for wheel between the `gift_set_id` branch and the existing `else`, turning the bare `else` into a guarded one — the `else` block's own body is unchanged:

```python
    elif invoice.is_wheel_spin:
        if invoice.stars_amount != total_amount:
            raise ConflictError("Stars amount does not match the invoice")
        prize = await wheel_service._roll_prize(db)
        spin_result = await wheel_service._grant_prize(db, user, prize, WheelSpinSource.stars)
        # _grant_prize already flushed a WheelSpin row (it has an id after
        # its own db.flush()) — fetch it back to link the invoice, mirroring
        # how invoice.pack_opening_id/invoice.gift_id are set above.
        spin_row = (
            await db.execute(
                select(WheelSpin).where(WheelSpin.user_id == user.id).order_by(WheelSpin.id.desc()).limit(1)
            )
        ).scalar_one()
        invoice.wheel_spin_id = spin_row.id
    else:
        if invoice.stars_amount != total_amount:
            raise ConflictError("Stars amount does not match the invoice")
        user = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, user, invoice.coins_amount, TransactionType.stars_coin_purchase,
            f"Покупка {invoice.coins_amount} монет за {invoice.stars_amount} ⭐",
            related_object_type="stars_invoice", related_object_id=invoice.id,
        )
```

At the end of `deliver_payment`, the existing result-building is two early `if` returns (`pack_id`, then `gift_set_id`) before a final default coin-result return. Add a third early return for wheel, in the same style:

```python
    await db.refresh(user)
    if invoice.pack_id is not None:
        granted.new_balance = user.balance
        return StarsInvoiceStatusOut(status="completed", result=granted)
    if invoice.is_wheel_spin:
        return StarsInvoiceStatusOut(status="completed", wheel_result=spin_result)
    if invoice.gift_set_id is not None:
        await db.refresh(gift)
        return StarsInvoiceStatusOut(status="completed", gift_result=GiftOut.model_validate(gift))
    return StarsInvoiceStatusOut(
        status="completed",
        coin_result=StarsCoinResultOut(coins_credited=invoice.coins_amount, new_balance=user.balance),
    )
```

- [ ] **Step 6: Add invoice endpoints to `backend/app/routers/wheel.py`**

```python
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.services import stars_payment_service


@router.post("/spin/stars-invoice", response_model=StarsInvoiceCreateOut)
async def create_stars_spin_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.create_spin_invoice(db, user)


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def get_stars_spin_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)
```

- [ ] **Step 7: Add a wheel message branch to `bot/handlers/payments.py`**

In `handle_successful_payment`, change the `if`/`elif`/`else` chain that decides which confirmation message to send — insert a wheel check before the generic pack fallback:

```python
    if ok:
        if body.get("gift_result"):
            await message.answer("🎁 Подарок отправлен! Получатель сможет открыть его в приложении.")
        elif body.get("wheel_result"):
            await message.answer("🎡 Колесо фортуны крутится — открой приложение, чтобы увидеть свой приз!")
        elif body.get("coin_result"):
            await message.answer("⭐ Монеты зачислены! Открой приложение, чтобы увидеть баланс.")
        else:
            await message.answer("🎉 Пак куплен и уже в твоей коллекции! Открой приложение, чтобы посмотреть карточку.")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: all passed.

- [ ] **Step 9: Full backend regression check**

Run: `docker compose exec backend pytest tests/ -q`
Expected: no new failures.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/wheel_service.py backend/app/services/stars_payment_service.py backend/app/schemas/stars.py backend/app/routers/wheel.py bot/handlers/payments.py backend/tests/test_wheel.py
git commit -m "Add Stars-paid wheel spins: invoice, pre-checkout, delivery, bot message"
```

---

### Task 5: Admin backend — `WheelPrize` CRUD router + `GameConfig` wheel fields

**Files:**
- Create: `backend/app/routers/admin_wheel.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_wheel.py` (append)

**Interfaces:**
- Consumes: `get_current_admin`, `log_action` (existing, see `backend/app/routers/admin_tasks.py` for the exact pattern being mirrored); `WheelPrizeCreate`/`WheelPrizeUpdate`/`WheelPrizeOut` (Task 2).
- Produces: `GET/POST /api/v1/admin/wheel/prizes`, `PUT/DELETE /api/v1/admin/wheel/prizes/{id}`, `POST /api/v1/admin/wheel/prizes/{id}/toggle-active`; 4 new fields on the existing `GET/PUT /api/v1/admin/games/config`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_wheel.py`:

```python
async def _admin_headers(client, db_session, bot_token):
    # settings.admin_ids includes DEV_USER_TELEGRAM_ID (999000001) per
    # conftest.py's test env — reuse it as the admin identity, matching
    # every other admin-router test file's pattern in this suite.
    await _register(client, db_session, 999000001, bot_token)
    return telegram_headers(999000001, bot_token)


async def test_admin_wheel_prize_crud(client, db_session, bot_token):
    headers = await _admin_headers(client, db_session, bot_token)

    create_resp = await client.post(
        "/api/v1/admin/wheel/prizes", headers=headers,
        json={"prize_type": "coins", "weight": 50, "coins_amount": 100},
    )
    assert create_resp.status_code == 200
    prize_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/admin/wheel/prizes", headers=headers)
    assert len(list_resp.json()) == 1

    update_resp = await client.put(
        f"/api/v1/admin/wheel/prizes/{prize_id}", headers=headers, json={"weight": 5}
    )
    assert update_resp.json()["weight"] == 5

    toggle_resp = await client.post(f"/api/v1/admin/wheel/prizes/{prize_id}/toggle-active", headers=headers)
    assert toggle_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/admin/wheel/prizes/{prize_id}", headers=headers)
    assert delete_resp.status_code == 204
    assert (await client.get("/api/v1/admin/wheel/prizes", headers=headers)).json() == []


async def test_admin_game_config_exposes_wheel_fields(client, db_session, bot_token):
    headers = await _admin_headers(client, db_session, bot_token)

    resp = await client.put(
        "/api/v1/admin/games/config", headers=headers,
        json={"wheel_free_spins_per_day": 3, "wheel_spin_cost_coins": 1500},
    )
    assert resp.status_code == 200
    assert resp.json()["wheel_free_spins_per_day"] == 3
    assert resp.json()["wheel_spin_cost_coins"] == 1500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_wheel.py -k admin_wheel -v`
Expected: FAIL — 404 (`admin_wheel` router not registered) and `422`/field-not-recognized on the config test (schema fields missing).

- [ ] **Step 3: Add wheel fields to `backend/app/schemas/admin.py`**

Add to `GameConfigOut` (anywhere in the field list — after the last `tactico_*` field is fine):

```python
    wheel_free_spins_per_day: int
    wheel_spin_cost_coins: int
    wheel_spin_cost_stars: int
    wheel_duplicate_badge_coins: int
```

Add to `GameConfigUpdate` in the same relative position:

```python
    wheel_free_spins_per_day: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_coins: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_stars: Optional[int] = Field(default=None, ge=0)
    wheel_duplicate_badge_coins: Optional[int] = Field(default=None, ge=0)
```

- [ ] **Step 4: Create `backend/app/routers/admin_wheel.py`**

```python
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.user import User
from app.models.wheel import WheelPrize
from app.schemas.wheel import WheelPrizeCreate, WheelPrizeOut, WheelPrizeUpdate
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/wheel", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_prize_or_404(db: AsyncSession, prize_id: int) -> WheelPrize:
    prize = await db.get(WheelPrize, prize_id)
    if not prize:
        raise NotFoundError("Wheel prize not found")
    return prize


@router.get("/prizes", response_model=list[WheelPrizeOut])
async def list_prizes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WheelPrize).order_by(WheelPrize.sort_order))
    return result.scalars().all()


@router.post("/prizes", response_model=WheelPrizeOut)
async def create_prize(payload: WheelPrizeCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = WheelPrize(**payload.model_dump())
    db.add(prize)
    await db.flush()
    await log_action(db, admin.id, "create_wheel_prize", "wheel_prize", prize.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(prize)
    return WheelPrizeOut.model_validate(prize)


@router.put("/prizes/{prize_id}", response_model=WheelPrizeOut)
async def update_prize(prize_id: int, payload: WheelPrizeUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    old_value = WheelPrizeOut.model_validate(prize).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prize, key, value)

    db.add(prize)
    await log_action(
        db, admin.id, "update_wheel_prize", "wheel_prize", prize_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(prize)
    return WheelPrizeOut.model_validate(prize)


@router.delete("/prizes/{prize_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prize(prize_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    await log_action(db, admin.id, "delete_wheel_prize", "wheel_prize", prize_id, old_value=WheelPrizeOut.model_validate(prize).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.delete(prize)
    await db.commit()


@router.post("/prizes/{prize_id}/toggle-active", response_model=WheelPrizeOut)
async def toggle_prize_active(prize_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    prize = await _get_prize_or_404(db, prize_id)
    prize.is_active = not prize.is_active
    db.add(prize)
    await log_action(db, admin.id, "toggle_wheel_prize_active", "wheel_prize", prize_id, new_value={"is_active": prize.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(prize)
    return WheelPrizeOut.model_validate(prize)
```

- [ ] **Step 5: Register the router in `backend/app/main.py`**

Add `admin_wheel` to the router import line, and add:

```python
app.include_router(admin_wheel.router, prefix=API_PREFIX)
```

right after `app.include_router(admin_gifts.router, prefix=API_PREFIX)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_wheel.py -v`
Expected: all passed.

- [ ] **Step 7: Full backend regression + import sanity**

Run: `docker compose exec backend pytest tests/ -q && docker compose exec backend python -c "from app.main import app"`
Expected: no new failures, clean import.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/admin_wheel.py backend/app/schemas/admin.py backend/app/main.py backend/tests/test_wheel.py
git commit -m "Add admin CRUD for wheel prizes + expose wheel economy fields in GameConfig"
```

---

### Task 6: Frontend types + `api/wheel.ts`

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/wheel.ts`

**Interfaces:**
- Consumes: `Badge`, `Pack`, `PackOpenResult`, `OpenedCard`-equivalent type (check the exact existing name — see Step 1), all already defined in `frontend/src/types/index.ts`.
- Produces: `WheelPrize`, `WheelStatus`, `WheelSpinResult` TS types; `fetchWheelStatus`, `spinFree`, `spinPaidCoins`, `createWheelStarsInvoice`, `fetchWheelStarsInvoiceStatus` functions, consumed by Task 7.

- [ ] **Step 1: Find the existing `OpenedCard`-shaped type name**

Run: `grep -n "cards: OpenedCard\|interface OpenedCard\|interface PackOpenResult" /Users/alex/Documents/dev/python/FootyCards/footyCards3/frontend/src/types/index.ts`

Use whatever type name that prints (it backs `PackOpenResult.cards`) as `OpenedCardT` below — the schema mirrors `app.schemas.pack.OpenedCardOut` (`card`, `is_new`, `duplicate_count`), so the existing frontend type for it applies unchanged to `WheelSpinResult.card_result`.

- [ ] **Step 2: Add types to `frontend/src/types/index.ts`**

Add near the `GiftSet`/`StarsInvoiceStatus` block:

```typescript
export interface WheelPrize {
  id: number;
  prize_type: "coins" | "pack" | "card_rarity" | "badge";
  weight: number;
  is_active: boolean;
  sort_order: number;
  coins_amount: number | null;
  pack_id: number | null;
  pack: Pack | null;
  card_rarity: "common" | "rare" | "epic" | "legendary" | null;
  badge_id: number | null;
  badge: Badge | null;
}

export interface WheelStatus {
  free_spins_remaining: number;
  free_spins_total: number;
  next_free_spin_reset_at: string;
  spin_cost_coins: number;
  spin_cost_stars: number;
  prizes: WheelPrize[];
}

export interface WheelSpinResult {
  prize: WheelPrize;
  new_balance: number;
  pack_result: PackOpenResult | null;
  card_result: OpenedCardT_REPLACE_WITH_REAL_NAME | null;
  badge_result: Badge | null;
  duplicate_badge_coins: number | null;
}
```

Replace `OpenedCardT_REPLACE_WITH_REAL_NAME` with the real type name found in Step 1 before saving (e.g. if it prints `cards: OpenedCard[]`, use `OpenedCard`).

Also add `wheel_result: WheelSpinResult | null;` to the existing `StarsInvoiceStatus` interface (same file, the block already containing `result`/`coin_result`/`gift_result`).

- [ ] **Step 3: Create `frontend/src/api/wheel.ts`**

```typescript
import { api } from "@/lib/api";
import type { StarsInvoiceCreate, StarsInvoiceStatus, WheelSpinResult, WheelStatus } from "@/types";

export async function fetchWheelStatus(): Promise<WheelStatus> {
  const { data } = await api.get<WheelStatus>("/wheel/status");
  return data;
}

export async function spinFree(): Promise<WheelSpinResult> {
  const { data } = await api.post<WheelSpinResult>("/wheel/spin/free");
  return data;
}

export async function spinPaidCoins(): Promise<WheelSpinResult> {
  const { data } = await api.post<WheelSpinResult>("/wheel/spin/coins");
  return data;
}

export async function createWheelStarsInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/wheel/spin/stars-invoice");
  return data;
}

export async function fetchWheelStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/wheel/stars-invoices/${payloadToken}`);
  return data;
}
```

- [ ] **Step 4: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors (this task adds no consumers yet, only types + a leaf API module, so nothing can be structurally wrong except the type itself failing to compile).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/wheel.ts
git commit -m "Add frontend types and API client for wheel of fortune"
```

---

### Task 7: `WheelPage.tsx` — the reel UI and all three spin paths

**Files:**
- Create: `frontend/src/pages/WheelPage.tsx`

**Interfaces:**
- Consumes: everything from Task 6's `api/wheel.ts` + types; `IconCoin`/`IconPack`/`IconCard` (`@/components/icons`); `openTelegramInvoice` (`@/lib/telegram`, see `frontend/src/pages/PacksPage.tsx:17-24` for the exact Stars-polling pattern to copy: `pollStarsInvoice`-style loop against `fetchWheelStarsInvoiceStatus`); `ApiRequestError` (`@/lib/api`); `useAuthStore` (`updateBalance`).
- Produces: default-exported `WheelPage` component, wired into `App.tsx` at `/wheel` in Task 8.

- [ ] **Step 1: Create `frontend/src/pages/WheelPage.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";

import { createWheelStarsInvoice, fetchWheelStarsInvoiceStatus, fetchWheelStatus, spinFree, spinPaidCoins } from "@/api/wheel";
import EmptyState from "@/components/common/EmptyState";
import { IconCard, IconCoin, IconInboxEmpty, IconPack } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { WheelPrize, WheelSpinResult } from "@/types";

async function pollWheelStarsInvoice(payloadToken: string): Promise<WheelSpinResult> {
  const maxAttempts = 20;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const status = await fetchWheelStarsInvoiceStatus(payloadToken);
    if (status.status === "completed" && status.wheel_result) return status.wheel_result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Приз ещё не пришёл — попробуй обновить страницу через минуту");
}

function prizeLabel(prize: WheelPrize): string {
  if (prize.prize_type === "coins") return `+${prize.coins_amount} монет`;
  if (prize.prize_type === "pack") return prize.pack?.name ?? "Пак";
  if (prize.prize_type === "card_rarity") {
    const labels: Record<string, string> = { common: "Обычная карта", rare: "Редкая карта", epic: "Эпическая карта", legendary: "Легендарная карта" };
    return labels[prize.card_rarity ?? "rare"];
  }
  return prize.badge?.name ?? "Значок";
}

function PrizeGlyph({ prize }: { prize: WheelPrize }) {
  if (prize.prize_type === "coins") return <IconCoin size={26} />;
  if (prize.prize_type === "pack") return <IconPack size={26} />;
  if (prize.prize_type === "card_rarity") return <IconCard size={26} />;
  if (prize.badge?.image_path) return <img src={staticUrl(prize.badge.image_path) ?? undefined} className="h-6 w-6 rounded-full object-cover" />;
  return <span className="text-lg leading-none">{prize.badge?.icon ?? "🏅"}</span>;
}

const GLYPH_BG: Record<WheelPrize["prize_type"], string> = {
  coins: "bg-accent-lime/12 text-accent-lime",
  pack: "bg-accent/12 text-accent",
  card_rarity: "bg-[#a855f7]/12 text-[#a855f7]",
  badge: "bg-amber-400/12 text-amber-300",
};

export default function WheelPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: status, isLoading } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const [centerIndex, setCenterIndex] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<WheelSpinResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payChoice, setPayChoice] = useState<"coins" | "stars" | null>(null);

  const runSpin = async (mutationFn: () => Promise<WheelSpinResult>) => {
    if (!status?.prizes.length) return;
    setError(null);
    setSpinning(true);
    try {
      const spinResult = await mutationFn();
      const wonIndex = status.prizes.findIndex((p) => p.id === spinResult.prize.id);
      // Land a few full loops further than the actual index so the strip
      // visibly spins past several prizes before settling, then holds on
      // the true winner — same "roll fast, ease into the result" idea used
      // by the pack-opening reveal, adapted to a horizontal strip.
      setCenterIndex((prev) => prev - (prev % status.prizes.length) + status.prizes.length * 3 + (wonIndex >= 0 ? wonIndex : 0));
      await new Promise((resolve) => setTimeout(resolve, 2600));
      setResult(spinResult);
      updateBalance(spinResult.new_balance);
      queryClient.invalidateQueries({ queryKey: ["wheel-status"] });
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Не удалось прокрутить колесо");
    } finally {
      setSpinning(false);
    }
  };

  const freeMutation = useMutation({ mutationFn: spinFree });
  const coinsMutation = useMutation({ mutationFn: spinPaidCoins });
  const starsMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createWheelStarsInvoice();
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") throw new Error("__cancelled__");
      if (paymentStatus === "failed") throw new Error("Платёж не прошёл");
      return pollWheelStarsInvoice(invoice.payload_token);
    },
  });

  if (isLoading || !status) return null;

  const prizeStrip = Array.from({ length: status.prizes.length * 6 }, (_, i) => status.prizes[i % status.prizes.length]);
  const CHIP_WIDTH = 88;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-xl font-bold text-ink-chalk">🎡 Колесо фортуны</h1>

      {!status.prizes.length ? (
        <EmptyState icon={IconInboxEmpty} title="Колесо пока не настроено" description="Загляни позже" />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-3xl bg-bg-surface py-8">
            <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 text-accent">▼</div>
            <motion.div
              className="flex"
              animate={{ x: -centerIndex * CHIP_WIDTH }}
              transition={{ duration: spinning ? 2.4 : 0, ease: [0.12, 0.8, 0.2, 1] }}
              style={{ paddingLeft: "calc(50% - 44px)" }}
            >
              {prizeStrip.map((prize, i) => {
                const isCenter = i === centerIndex && !spinning;
                return (
                  <div key={i} className="flex shrink-0 flex-col items-center gap-2" style={{ width: CHIP_WIDTH }}>
                    <div
                      className={`flex h-16 w-16 items-center justify-center rounded-2xl transition-all ${GLYPH_BG[prize.prize_type]} ${
                        isCenter ? "scale-125 outline outline-2 outline-accent" : "scale-90 opacity-50"
                      }`}
                    >
                      <PrizeGlyph prize={prize} />
                    </div>
                  </div>
                );
              })}
            </motion.div>
          </div>

          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

          <div className="flex flex-col gap-2">
            <button
              onClick={() => runSpin(() => freeMutation.mutateAsync())}
              disabled={spinning || status.free_spins_remaining === 0}
              className="w-full rounded-xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Крутить бесплатно ({status.free_spins_remaining}/{status.free_spins_total})
            </button>

            {payChoice === null ? (
              <button
                onClick={() => setPayChoice("coins")}
                disabled={spinning}
                className="w-full rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
              >
                Крутить платно
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => { setPayChoice(null); runSpin(() => coinsMutation.mutateAsync()); }}
                  disabled={spinning}
                  className="flex items-center justify-center gap-1 rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
                >
                  <IconCoin size={14} />{status.spin_cost_coins}
                </button>
                <button
                  onClick={() => { setPayChoice(null); runSpin(() => starsMutation.mutateAsync()); }}
                  disabled={spinning}
                  className="rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
                >
                  ⭐ {status.spin_cost_stars}
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {result && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6" onClick={() => setResult(null)}>
          <div className="w-full max-w-xs rounded-2xl border border-white/10 bg-bg-surface p-6 text-center" onClick={(e) => e.stopPropagation()}>
            <p className="font-display text-lg font-bold text-ink-chalk">
              {result.duplicate_badge_coins ? `+${result.duplicate_badge_coins} монет (значок уже был)` : `Приз получен!`}
            </p>
            <p className="mt-2 text-sm text-ink-mist">{prizeLabel(result.prize)}</p>
            <button onClick={() => setResult(null)} className="mt-5 w-full rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base active:scale-95">
              Ок
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors. If `IconInboxEmpty` or any icon name doesn't match the real export, run `grep -n "export function Icon" frontend/src/components/icons/index.tsx` and fix the import to the real names.

- [ ] **Step 3: Manual smoke test**

With `docker compose up` running (see CLAUDE.md's dev commands), navigate to `http://localhost:5173/wheel` directly (route is wired in Task 8 — until then this is a 404; skip this step now and re-run it as part of Task 8's manual check instead). Leave this step's checkbox for Task 8.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/WheelPage.tsx
git commit -m "Add WheelPage: reel UI, free/coin/Stars spin flows"
```

---

### Task 8: Home-page teaser + routing

**Files:**
- Modify: `frontend/src/pages/HomePage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `WheelPage` (Task 7), `fetchWheelStatus` (Task 6), `NoticeCard` (already defined in `HomePage.tsx`, see `backend`-adjacent existing usages for referral/daily-reward/free-pack).
- Produces: `/wheel` route reachable from the running app; a `NoticeCard` on `HomePage.tsx`.

- [ ] **Step 1: Add a wheel status query + `NoticeCard` to `frontend/src/pages/HomePage.tsx`**

Add the import:

```typescript
import { fetchWheelStatus } from "@/api/wheel";
```

Add alongside the other `useQuery` calls near the top of `HomePage`:

```typescript
  const { data: wheelStatus } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
```

Add a new `NoticeCard` in the notices `<div className="flex flex-col gap-3">` block, after the existing free-pack `NoticeCard` (reuse the already-imported `IconGift`, or import `IconTarget`-adjacent icon — `IconPlay` is already imported and reads fine for a "spin/play" affordance; simplest is reusing `IconGift` since no dedicated wheel icon exists in the set yet):

```tsx
        {wheelStatus && (
          <NoticeCard
            Icon={IconGift}
            title="Колесо фортуны"
            subtitle={
              wheelStatus.free_spins_remaining > 0
                ? `Осталось ${wheelStatus.free_spins_remaining} бесплатных прокруток сегодня`
                : "Бесплатные прокрутки закончились — крути за монеты или ⭐"
            }
            onClick={() => navigate("/wheel")}
          />
        )}
```

- [ ] **Step 2: Register routes in `frontend/src/App.tsx`**

Add the import:

```typescript
import WheelPage from "@/pages/WheelPage";
```

Add inside the existing `<Route element={<AppLayout />}>` block, alongside `/tasks`:

```tsx
        <Route path="/wheel" element={<WheelPage />} />
```

- [ ] **Step 3: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Manual smoke test**

With `docker compose up` running and at least one active `WheelPrize` seeded (use the admin panel from Task 9, or insert one directly: `docker compose exec backend python -c "..."` is unnecessary — just do this check after Task 9 is done instead, since there's no prize data yet. Leave this step's checkbox for Task 9's manual check.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HomePage.tsx frontend/src/App.tsx
git commit -m "Wire wheel of fortune into navigation: home teaser + /wheel route"
```

---

### Task 9: Admin frontend — `AdminWheelPage.tsx` + `GameConfig` economy fields

**Files:**
- Create: `frontend/src/admin/pages/AdminWheelPage.tsx`
- Modify: `frontend/src/admin/api.ts`
- Modify: `frontend/src/admin/types.ts`
- Modify: `frontend/src/admin/AdminLayout.tsx`
- Modify: `frontend/src/admin/pages/AdminGamesPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchAdminBadges`/`fetchAdminPacks` (already exist in `frontend/src/admin/api.ts`); `WheelPrizeType`-shaped values (Task 6 types, reused verbatim from `frontend/src/types.ts`'s `WheelPrize["prize_type"]`); the `AdminTasksPage.tsx` CRUD-form pattern (type-conditional fields, `Field`/`NumField` helpers) as the direct template.
- Produces: `/admin/wheel` route + nav entry; wheel prize management fully usable end-to-end.

- [ ] **Step 1: Add admin types to `frontend/src/admin/types.ts`**

Add near the existing `TaskDefinition` interface:

```typescript
export interface AdminWheelPrize {
  id: number;
  prize_type: "coins" | "pack" | "card_rarity" | "badge";
  weight: number;
  is_active: boolean;
  sort_order: number;
  coins_amount: number | null;
  pack_id: number | null;
  card_rarity: "common" | "rare" | "epic" | "legendary" | null;
  badge_id: number | null;
}
```

Add 4 fields to the end of the existing `GameConfig` interface (right before its closing `}`):

```typescript
  wheel_free_spins_per_day: number;
  wheel_spin_cost_coins: number;
  wheel_spin_cost_stars: number;
  wheel_duplicate_badge_coins: number;
```

- [ ] **Step 2: Add CRUD functions to `frontend/src/admin/api.ts`**

Add near the existing `fetchAdminTasks`/`createTask`/`updateTask`/`deleteTask`/`toggleTaskActive` block:

```typescript
export async function fetchAdminWheelPrizes(): Promise<AdminWheelPrize[]> {
  const { data } = await api.get<AdminWheelPrize[]>("/admin/wheel/prizes");
  return data;
}
export async function createWheelPrize(payload: Record<string, unknown>): Promise<AdminWheelPrize> {
  const { data } = await api.post<AdminWheelPrize>("/admin/wheel/prizes", payload);
  return data;
}
export async function updateWheelPrize(id: number, payload: Record<string, unknown>): Promise<AdminWheelPrize> {
  const { data } = await api.put<AdminWheelPrize>(`/admin/wheel/prizes/${id}`, payload);
  return data;
}
export async function deleteWheelPrize(id: number): Promise<void> {
  await api.delete(`/admin/wheel/prizes/${id}`);
}
export async function toggleWheelPrizeActive(id: number): Promise<AdminWheelPrize> {
  const { data } = await api.post<AdminWheelPrize>(`/admin/wheel/prizes/${id}/toggle-active`);
  return data;
}
```

Add `AdminWheelPrize` to the existing `import type { ... } from "@/admin/types"` block at the top of the file (alongside `TaskDefinition`, `GameConfig`, etc.).

- [ ] **Step 3: Create `frontend/src/admin/pages/AdminWheelPage.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createWheelPrize, deleteWheelPrize, fetchAdminBadges, fetchAdminPacks, fetchAdminWheelPrizes,
  toggleWheelPrizeActive, updateWheelPrize,
} from "@/admin/api";
import type { AdminWheelPrize } from "@/admin/types";
import { ApiRequestError } from "@/lib/api";

type PrizeType = AdminWheelPrize["prize_type"];
type CardRarity = NonNullable<AdminWheelPrize["card_rarity"]>;

interface PrizeForm {
  prize_type: PrizeType;
  weight: number;
  coins_amount: number;
  pack_id: number | "";
  card_rarity: CardRarity;
  badge_id: number | "";
  is_active: boolean;
  sort_order: number;
}

function prizeToForm(p?: AdminWheelPrize): PrizeForm {
  return {
    prize_type: p?.prize_type ?? "coins",
    weight: p?.weight ?? 10,
    coins_amount: p?.coins_amount ?? 50,
    pack_id: p?.pack_id ?? "",
    card_rarity: p?.card_rarity ?? "rare",
    badge_id: p?.badge_id ?? "",
    is_active: p?.is_active ?? true,
    sort_order: p?.sort_order ?? 0,
  };
}

const TYPE_LABELS: Record<PrizeType, string> = { coins: "Монеты", pack: "Пак", card_rarity: "Карта редкости", badge: "Значок" };
const RARITY_LABELS: Record<CardRarity, string> = { common: "Обычная", rare: "Редкая", epic: "Эпическая", legendary: "Легендарная" };

export default function AdminWheelPage() {
  const queryClient = useQueryClient();
  const { data: prizes, isLoading } = useQuery({ queryKey: ["admin-wheel-prizes"], queryFn: fetchAdminWheelPrizes });
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const { data: badges } = useQuery({ queryKey: ["admin-badges"], queryFn: fetchAdminBadges });
  const [editing, setEditing] = useState<AdminWheelPrize | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<PrizeForm>(prizeToForm());
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-wheel-prizes"] });
  const toggleMutation = useMutation({ mutationFn: toggleWheelPrizeActive, onSuccess: invalidate });
  const deleteMutation = useMutation({
    mutationFn: deleteWheelPrize,
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось удалить приз"),
  });

  const confirmDelete = (p: AdminWheelPrize) => {
    if (window.confirm("Удалить этот приз из колеса навсегда?")) deleteMutation.mutate(p.id);
  };

  const buildPayload = () => ({
    prize_type: form.prize_type,
    weight: form.weight,
    coins_amount: form.prize_type === "coins" ? form.coins_amount : null,
    pack_id: form.prize_type === "pack" ? form.pack_id || null : null,
    card_rarity: form.prize_type === "card_rarity" ? form.card_rarity : null,
    badge_id: form.prize_type === "badge" ? form.badge_id || null : null,
    is_active: form.is_active,
    sort_order: form.sort_order,
  });

  const createMutation = useMutation({ mutationFn: () => createWheelPrize(buildPayload()), onSuccess: () => { invalidate(); setCreating(false); } });
  const updateMutation = useMutation({ mutationFn: () => updateWheelPrize(editing!.id, buildPayload()), onSuccess: () => { invalidate(); setEditing(null); } });

  const openEdit = (p: AdminWheelPrize) => { setEditing(p); setForm(prizeToForm(p)); setError(null); };

  const prizeSummary = (p: AdminWheelPrize) => {
    if (p.prize_type === "coins") return `+${p.coins_amount} монет`;
    if (p.prize_type === "pack") return `Пак #${p.pack_id}`;
    if (p.prize_type === "card_rarity") return `Карта: ${RARITY_LABELS[p.card_rarity ?? "rare"]}`;
    return `Значок #${p.badge_id}`;
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Колесо фортуны</h1>
        <button onClick={() => { setCreating(true); setForm(prizeToForm()); }} className="rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg-base">
          + Новый приз
        </button>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Загрузка...</p>}
      {error && !creating && !editing && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {prizes?.map((p) => (
          <div key={p.id} className="rounded-2xl border border-white/5 bg-bg-surface p-3">
            <div className="flex items-center justify-between">
              <p className="font-display text-sm font-bold">{TYPE_LABELS[p.prize_type]}</p>
              <p className="text-xs text-slate-500">Вес: {p.weight}</p>
            </div>
            <p className="text-xs text-slate-400">{prizeSummary(p)}</p>
            <p className="text-xs text-slate-500">{p.is_active ? "Активен" : "Отключён"}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <button onClick={() => openEdit(p)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">Изменить</button>
              <button onClick={() => toggleMutation.mutate(p.id)} className="rounded-lg bg-white/5 px-2 py-1 text-[11px]">
                {p.is_active ? "Отключить" : "Включить"}
              </button>
              <button onClick={() => confirmDelete(p)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">Удалить</button>
            </div>
          </div>
        ))}
      </div>

      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => { setCreating(false); setEditing(null); }}>
          <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-4 font-display text-lg font-bold">{editing ? "Редактировать приз" : "Новый приз"}</p>
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Тип приза</span>
                <select
                  value={form.prize_type}
                  onChange={(e) => setForm({ ...form, prize_type: e.target.value as PrizeType })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                >
                  {(Object.keys(TYPE_LABELS) as PrizeType[]).map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Вес (относительный — больше = чаще выпадает)</span>
                <input type="number" value={form.weight} onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
              </label>

              {form.prize_type === "coins" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Количество монет</span>
                  <input type="number" value={form.coins_amount} onChange={(e) => setForm({ ...form, coins_amount: Number(e.target.value) })} className="rounded-lg bg-bg-surface px-3 py-2 outline-none" />
                </label>
              )}

              {form.prize_type === "pack" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Пак</span>
                  <select
                    value={form.pack_id}
                    onChange={(e) => setForm({ ...form, pack_id: e.target.value ? Number(e.target.value) : "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Выбери пак</option>
                    {packs?.map((pk) => <option key={pk.id} value={pk.id}>{pk.name}</option>)}
                  </select>
                </label>
              )}

              {form.prize_type === "card_rarity" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Редкость</span>
                  <select
                    value={form.card_rarity}
                    onChange={(e) => setForm({ ...form, card_rarity: e.target.value as CardRarity })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    {(["rare", "epic", "legendary"] as CardRarity[]).map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
                  </select>
                </label>
              )}

              {form.prize_type === "badge" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Значок</span>
                  <select
                    value={form.badge_id}
                    onChange={(e) => setForm({ ...form, badge_id: e.target.value ? Number(e.target.value) : "" })}
                    className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                  >
                    <option value="">Выбери значок</option>
                    {badges?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                  <p className="text-[11px] text-slate-500">Заведи отдельный значок специально для колеса — не выбирай значки, уже привязанные к платным пакам.</p>
                </label>
              )}

              <label className="mt-1 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                Активен
              </label>
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={() => { setCreating(false); setEditing(null); }} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm">Отмена</button>
              <button
                onClick={() => (editing ? updateMutation.mutate() : createMutation.mutate())}
                className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-bold text-bg-base"
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

- [ ] **Step 4: Register the admin route and nav entry**

In `frontend/src/App.tsx`, add the import `import AdminWheelPage from "@/admin/pages/AdminWheelPage";` and the route `<Route path="wheel" element={<AdminWheelPage />} />` inside the existing `/admin` route block (alongside `gifts`/`games`).

In `frontend/src/admin/AdminLayout.tsx`, add `{ to: "/admin/wheel", label: "Колесо фортуны", icon: "🎡" },` to the `SECTIONS` array (after the `/admin/gifts` entry).

- [ ] **Step 5: Add the 4 wheel economy fields to `frontend/src/admin/pages/AdminGamesPage.tsx`**

Add a new `<section>` (anywhere among the existing ones, e.g. right after the "Бесплатный пак" section):

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Колесо фортуны</p>
        <div className="grid grid-cols-2 gap-3">
          {field("wheel_free_spins_per_day", "Бесплатных прокруток в день")}
          {field("wheel_spin_cost_coins", "Платная прокрутка, монеты")}
          {field("wheel_spin_cost_stars", "Платная прокрутка, ⭐")}
          {field("wheel_duplicate_badge_coins", "Компенсация за повтор значка")}
        </div>
      </section>
```

- [ ] **Step 6: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Manual end-to-end smoke test**

With `docker compose up` running:
1. Open `http://localhost:5173/admin/wheel`, create at least one prize of each type (coins, pack, card_rarity, badge — create a test pack/badge first via their own admin pages if none exist).
2. Open `http://localhost:5173/` — confirm the "Колесо фортуны" notice card appears and shows the free-spin count.
3. Click through to `/wheel`, confirm the reel renders the configured prizes with real icons (no emoji chrome), spin a free spin, confirm the modal shows a result and the balance updates.
4. Spin until free spins are exhausted, confirm the paid-coins button works and debits the configured cost.
5. Test the Stars path against the real dev bot (per CLAUDE.md, Stars payments cannot be meaningfully unit-tested — this is the one path that needs a live check).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/admin/pages/AdminWheelPage.tsx frontend/src/admin/api.ts frontend/src/admin/types.ts frontend/src/admin/AdminLayout.tsx frontend/src/admin/pages/AdminGamesPage.tsx frontend/src/App.tsx
git commit -m "Add admin wheel-prize management UI + wheel economy fields in AdminGamesPage"
```
