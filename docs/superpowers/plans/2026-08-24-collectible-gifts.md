# Collectible Gifts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second "Telegram-style" collectible gift type (image/gif, Stars and/or coins, self or friend) alongside the existing pack+coins gift bundles, by extending `GiftSet`/`Gift` with a `kind` discriminator instead of a parallel model — and relocate/reshape the Profile page's "Подарки" entry point into a live block under "Трофеи" showing up to 3 pinned collectibles.

**Architecture:** One `GiftKind` enum (`bundle` | `collectible`) added to the existing `GiftSet`/`Gift` tables. All existing creation paths (Stars delivery, admin send, admin broadcast) work unchanged for both kinds since they only ever take a bare `gift_set_id`. `claim_gift` branches on kind (bundle rolls a pack/credits coins; collectible just stamps `claimed_at`). A new coin-purchase endpoint and a pin/unpin endpoint are the only new backend surface.

**Tech Stack:** FastAPI + async SQLAlchemy 2 + Alembic (backend), React 18 + TypeScript + TanStack Query + Tailwind (frontend), pytest (async, in-memory SQLite) for backend tests.

**Spec:** [docs/superpowers/specs/2026-08-24-collectible-gifts-design.md](../specs/2026-08-24-collectible-gifts-design.md)

## Global Constraints

- Never hardcode economy numbers — `coins_price`/`stars_price` always come from the `GiftSet` row, never a frontend constant.
- Any coins/cards/packs mutation must be atomic with row locking — `buy_collectible_with_coins` must use `wallet_service.lock_user_for_update` + `debit_coins`, same as every other coin spend.
- `coins_price` follows the exact same convention as the existing `stars_price`: a plain non-nullable `int`, default `0`, where `0` means "not purchasable in this currency" — **not** `Optional[int]` (this refines one detail from the spec's data-model section after checking `stars_price`'s existing precedent in the same table; behavior is identical, just consistent typing).
- Preserve idempotency and existing test behavior — every existing test in `backend/tests/test_gifts.py` must keep passing unmodified.
- Frontend: `npm run typecheck` and `npm run test` must pass after every frontend task.
- Backend: `pytest tests/test_gifts.py -v` must pass after every backend task; `python -c "from app.main import app"` sanity check after any model/schema change.

---

### Task 1: Data model — `GiftKind`, `coins_price`, pinning columns, migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/gift.py`
- Create: `backend/alembic/versions/0052_gift_kind_and_pinning.py`

**Interfaces:**
- Produces: `GiftKind` enum (`app.models.enums.GiftKind`, values `"bundle"`/`"collectible"`), `GiftSet.kind: GiftKind`, `GiftSet.coins_price: int`, `Gift.is_pinned: bool`, `Gift.pinned_at: Optional[datetime]`, `TransactionType.gift_purchase_coins`.

- [ ] **Step 1: Add `GiftKind` to `app/models/enums.py`**

Insert immediately after the `TransactionType` class (after its last member, `league_reward = "league_reward"`, before `class TaskCategory`):

```python
class GiftKind(str, enum.Enum):
    bundle = "bundle"
    collectible = "collectible"
```

Also add a new member to the existing `TransactionType` class (insert after `league_reward = "league_reward"`, still inside the class body):

```python
    gift_purchase_coins = "gift_purchase_coins"
```

- [ ] **Step 2: Extend `GiftSet` and `Gift` models in `app/models/gift.py`**

Change the imports at the top of the file:

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import GiftKind
from app.models.mixins import TimestampMixin
```

In `class GiftSet`, add two new columns right after `stars_price`:

```python
    stars_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[GiftKind] = mapped_column(Enum(GiftKind, name="gift_kind_enum"), nullable=False, default=GiftKind.bundle)
    coins_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

(only the two new lines are additions — `stars_price` and `is_active` already exist, shown here for exact placement).

Update `GiftSet`'s docstring to mention both kinds:

```python
class GiftSet(TimestampMixin, Base):
    """An admin-curated gift definition offered in the in-app "Подарки"
    section — either a `bundle` (pack + coins, Stars-only, today's original
    gift type) or a `collectible` (a cosmetic image/gif, priced in Stars
    and/or coins — a Telegram-style gift). Players buy one for themselves or
    someone else (bundles disallow buying for yourself; collectibles allow
    it); admins can also hand one out for free (see Gift.is_admin_gift)."""
```

In `class Gift`, add two new columns right after `is_admin_gift`:

```python
    is_admin_gift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

(`is_admin_gift` and `claimed_at` already exist — only the two `is_pinned`/`pinned_at` lines are new).

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0052_gift_kind_and_pinning.py`:

```python
"""Collectible gifts: kind discriminator, coin pricing, pinning

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

gift_kind_enum = postgresql.ENUM("bundle", "collectible", name="gift_kind_enum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    gift_kind_enum.create(bind, checkfirst=True)

    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'gift_purchase_coins'")

    op.add_column("gift_sets", sa.Column("kind", gift_kind_enum, nullable=False, server_default="bundle"))
    op.add_column("gift_sets", sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gifts", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("gifts", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("gifts", "pinned_at")
    op.drop_column("gifts", "is_pinned")
    op.drop_column("gift_sets", "coins_price")
    op.drop_column("gift_sets", "kind")
    op.execute("DROP TYPE IF EXISTS gift_kind_enum")
```

- [ ] **Step 4: Verify**

Run:
```bash
cd backend
python -c "from app.main import app"
pytest tests/test_gifts.py -v
```
Expected: import succeeds, all existing gift tests still pass (the SQLite test DB is built from `Base.metadata.create_all`, not this migration, so the new columns take effect immediately for tests — the migration file itself is only exercised against real Postgres, verify separately per Task 9).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/gift.py backend/alembic/versions/0052_gift_kind_and_pinning.py
git commit -m "Add GiftKind, coins_price, and pinning columns to gift models"
```

---

### Task 2: Schemas — `kind`/`coins_price`/`is_pinned` on existing schemas, new purchase/pin schemas

**Files:**
- Modify: `backend/app/schemas/gift.py`

**Interfaces:**
- Consumes: `GiftKind` from `app.models.enums` (Task 1).
- Produces: `GiftSetOut.kind: GiftKind`, `GiftSetOut.coins_price: int`, `GiftOut.is_pinned: bool`, `GiftPurchaseResult(gift: GiftOut, new_balance: int)`, `GiftBuyWithCoinsIn(recipient_id: int, message: Optional[str])`, `GiftPinIn(pinned: bool)`.

- [ ] **Step 1: Rewrite `backend/app/schemas/gift.py`**

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GiftKind
from app.schemas.pack import PackOpenResult
from app.schemas.user import UserPublicOut


class GiftSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    image_path: Optional[str] = None
    kind: GiftKind
    pack_id: Optional[int] = None
    coins_amount: int
    stars_price: int
    coins_price: int
    is_active: bool
    sort_order: int


class GiftSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    kind: GiftKind = GiftKind.bundle
    pack_id: Optional[int] = None
    coins_amount: int = Field(default=0, ge=0)
    stars_price: int = Field(default=0, ge=0)
    coins_price: int = Field(default=0, ge=0)
    is_active: bool = True
    sort_order: int = 0


class GiftSetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    kind: Optional[GiftKind] = None
    pack_id: Optional[int] = None
    coins_amount: Optional[int] = Field(default=None, ge=0)
    stars_price: Optional[int] = Field(default=None, ge=0)
    coins_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class GiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gift_set: GiftSetOut
    sender: Optional[UserPublicOut] = None
    message: Optional[str] = None
    is_admin_gift: bool
    is_pinned: bool
    claimed_at: Optional[datetime] = None
    created_at: datetime


class GiftClaimResult(BaseModel):
    gift: GiftOut
    pack_result: Optional[PackOpenResult] = None
    coins_credited: int = 0
    new_balance: int


class GiftPurchaseResult(BaseModel):
    gift: GiftOut
    new_balance: int


class GiftSendIn(BaseModel):
    gift_set_id: int
    recipient_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class GiftBuyWithCoinsIn(BaseModel):
    recipient_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class GiftPinIn(BaseModel):
    pinned: bool


class AdminGiftSendIn(BaseModel):
    gift_set_id: int
    user_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class AdminGiftBroadcastIn(BaseModel):
    gift_set_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class AdminGiftBroadcastOut(BaseModel):
    recipients: int
```

- [ ] **Step 2: Verify**

```bash
cd backend
python -c "from app.main import app"
pytest tests/test_gifts.py -v
```
Expected: both pass unchanged (existing tests never assert against the exact JSON key set, so adding fields is non-breaking).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/gift.py
git commit -m "Add kind/coins_price/is_pinned fields and purchase/pin schemas to gift schemas"
```

---

### Task 3: Service + router logic — coin purchase, pin/unpin, kind-aware claim, relaxed self-gift guard

**Files:**
- Modify: `backend/app/services/gift_service.py`
- Modify: `backend/app/services/stars_payment_service.py`
- Modify: `backend/app/routers/gifts.py`
- Test: `backend/tests/test_gifts.py`

**Interfaces:**
- Consumes: `GiftKind`, `GiftSetOut`, `GiftOut`, `GiftPurchaseResult`, `GiftBuyWithCoinsIn`, `GiftPinIn` (Tasks 1–2); `wallet_service.lock_user_for_update`, `wallet_service.debit_coins` (existing).
- Produces: `gift_service.buy_collectible_with_coins(db, buyer, gift_set_id, recipient_id, message) -> GiftPurchaseResult`, `gift_service.set_gift_pinned(db, user, gift_id, pinned) -> GiftOut`, `POST /gifts/collectibles/{gift_set_id}/buy-with-coins`, `PATCH /gifts/{gift_id}/pin`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_gifts.py`. First change the existing `from app.models.enums import Rarity` line (line 6) to also import `GiftKind`:

```python
from app.models.enums import GiftKind, Rarity
```

Then add the new test functions:

```python
async def test_buy_collectible_gift_with_coins_for_self(client, db_session, bot_token):
    gift_set = await create_gift_set(
        db_session, name="Золотой кубок", kind=GiftKind.collectible, coins_price=150, stars_price=0, coins_amount=0,
    )
    user = await _register(client, db_session, 860010, bot_token)
    headers = telegram_headers(860010, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_balance"] == 500 - 150
    assert body["gift"]["gift_set"]["kind"] == "collectible"
    assert body["gift"]["claimed_at"] is None

    mine = await client.get("/api/v1/gifts/mine", headers=headers)
    assert len(mine.json()) == 1


async def test_buy_collectible_gift_with_coins_insufficient_balance(client, db_session, bot_token):
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=999999, stars_price=0)
    user = await _register(client, db_session, 860011, bot_token)
    headers = telegram_headers(860011, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 400


async def test_buy_bundle_gift_with_coins_is_rejected(client, db_session, bot_token):
    gift_set = await create_gift_set(db_session, kind=GiftKind.bundle, coins_amount=10, stars_price=20)
    user = await _register(client, db_session, 860012, bot_token)
    headers = telegram_headers(860012, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 409


async def test_collectible_gift_can_be_sent_to_self_with_stars(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, stars_price=15, coins_price=0)
    user = await _register(client, db_session, 860013, bot_token)
    headers = telegram_headers(860013, bot_token)

    resp = await client.post(
        "/api/v1/gifts/invoice", headers=headers,
        json={"gift_set_id": gift_set.id, "recipient_id": user.id},
    )
    assert resp.status_code == 200


async def test_claiming_collectible_gift_grants_nothing(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860014, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860014)

    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0)
    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]

    claim_resp = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["coins_credited"] == 0
    assert body["pack_result"] is None
    assert body["new_balance"] == 500


async def test_pin_and_unpin_collectible_gift(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860015, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860015)

    gift_ids = []
    for i in range(4):
        gift_set = await create_gift_set(
            db_session, name=f"Кубок {i}", kind=GiftKind.collectible, coins_price=10, stars_price=0,
        )
        send_resp = await client.post(
            "/api/v1/admin/gifts/send", headers=auth,
            json={"gift_set_id": gift_set.id, "user_id": recipient.id},
        )
        gift_id = send_resp.json()["id"]
        await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
        gift_ids.append(gift_id)

    for gift_id in gift_ids[:3]:
        resp = await client.patch(f"/api/v1/gifts/{gift_id}/pin", headers=recipient_headers, json={"pinned": True})
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    fourth = await client.patch(f"/api/v1/gifts/{gift_ids[3]}/pin", headers=recipient_headers, json={"pinned": True})
    assert fourth.status_code == 409

    unpin = await client.patch(f"/api/v1/gifts/{gift_ids[0]}/pin", headers=recipient_headers, json={"pinned": False})
    assert unpin.status_code == 200
    assert unpin.json()["is_pinned"] is False

    now_ok = await client.patch(f"/api/v1/gifts/{gift_ids[3]}/pin", headers=recipient_headers, json={"pinned": True})
    assert now_ok.status_code == 200


async def test_pin_bundle_gift_is_rejected(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860016, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860016)

    gift_set = await create_gift_set(db_session, kind=GiftKind.bundle, coins_amount=10, stars_price=0)
    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]
    await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)

    resp = await client.patch(f"/api/v1/gifts/{gift_id}/pin", headers=recipient_headers, json={"pinned": True})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd backend
pytest tests/test_gifts.py -k "collectible or pin_and_unpin or pin_bundle" -v
```
Expected: FAIL — `404` on `/gifts/collectibles/.../buy-with-coins` and `/gifts/{id}/pin` (routes don't exist yet), and the claim/self-gift tests fail because `claim_gift`/`create_gift_invoice` don't branch on kind yet.

- [ ] **Step 3: Implement — `gift_service.py`**

Change the imports at the top of `backend/app/services/gift_service.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import CardSource, GiftKind, NotificationType, TransactionType
from app.models.gift import Gift, GiftSet
from app.models.notification import Notification
from app.models.user import User
from app.schemas.gift import GiftClaimResult, GiftOut, GiftPurchaseResult, GiftSetOut
from app.services import collection_service
from app.services.pack_service import grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update
```

Replace `claim_gift`'s body — insert a kind branch right after `gift_set = gift.gift_set`:

```python
async def claim_gift(db: AsyncSession, user: User, gift_id: int) -> GiftClaimResult:
    """Opens a pending gift — reward is only granted once the recipient
    explicitly claims it (never on receipt), mirroring opening a pack. Row
    locks the gift before checking claimed_at so two concurrent claim taps
    (e.g. a double-tap) can't both pass the check and deliver twice."""
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.claimed_at is not None:
        raise ConflictError("This gift was already claimed")

    gift_set = gift.gift_set

    if gift_set.kind == GiftKind.collectible:
        # No pack to roll, no coins to credit — the gift row's existence is
        # the reward. The frontend never shows a manual "open" button for
        # these; it auto-claims them right after fetching the list.
        gift.claimed_at = datetime.now(timezone.utc)
        db.add(gift)
        await db.commit()
        await db.refresh(gift)
        return GiftClaimResult(
            gift=GiftOut.model_validate(gift), pack_result=None, coins_credited=0, new_balance=user.balance,
        )

    pack_result = None
    if gift_set.pack_id is not None:
        granted = await grant_bonus_pack_opening(
            db, user, gift_set.pack_id, idempotency_prefix=f"gift-{gift.id}", source=CardSource.gift,
        )
        if granted is not None:
            granted.collection_rewards = await collection_service.grant_collection_rewards_for_new_cards(
                db, user, [item.card.player.id for item in granted.cards]
            )
            gift.pack_opening_id = granted.opening_id
            pack_result = granted

    if gift_set.coins_amount:
        user = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, user, gift_set.coins_amount, TransactionType.gift_coins,
            f"Подарок «{gift_set.name}»", related_object_type="gift", related_object_id=gift.id,
        )

    gift.claimed_at = datetime.now(timezone.utc)
    db.add(gift)
    await db.commit()
    await db.refresh(user)
    await db.refresh(gift)

    if pack_result is not None:
        pack_result.new_balance = user.balance

    return GiftClaimResult(
        gift=GiftOut.model_validate(gift), pack_result=pack_result,
        coins_credited=gift_set.coins_amount, new_balance=user.balance,
    )
```

Add two new functions at the end of the file (after `admin_broadcast_gift`):

```python
async def buy_collectible_with_coins(
    db: AsyncSession, buyer: User, gift_set_id: int, recipient_id: int, message: Optional[str],
) -> GiftPurchaseResult:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    if not gift_set.is_active:
        raise ConflictError("This gift is not currently available")
    if gift_set.kind != GiftKind.collectible:
        raise ConflictError("This gift can only be bought with Stars")
    if gift_set.coins_price <= 0:
        raise ConflictError("This gift cannot be bought with coins")

    recipient = await db.get(User, recipient_id)
    if recipient is None:
        raise NotFoundError("Recipient not found")

    buyer = await lock_user_for_update(db, buyer.id)
    await debit_coins(
        db, buyer, gift_set.coins_price, TransactionType.gift_purchase_coins,
        f"Подарок «{gift_set.name}»", related_object_type="gift_set", related_object_id=gift_set.id,
    )

    gift = Gift(gift_set_id=gift_set.id, sender_id=buyer.id, recipient_id=recipient.id, message=message, is_admin_gift=False)
    db.add(gift)
    await db.commit()
    await db.refresh(buyer)
    await db.refresh(gift)

    return GiftPurchaseResult(gift=GiftOut.model_validate(gift), new_balance=buyer.balance)


async def set_gift_pinned(db: AsyncSession, user: User, gift_id: int, pinned: bool) -> GiftOut:
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.gift_set.kind != GiftKind.collectible:
        raise ConflictError("Only collectible gifts can be pinned")
    if gift.claimed_at is None:
        raise ConflictError("This gift hasn't been claimed yet")

    if pinned and not gift.is_pinned:
        pinned_count = (
            await db.execute(
                select(func.count()).select_from(Gift).where(Gift.recipient_id == user.id, Gift.is_pinned.is_(True))
            )
        ).scalar_one()
        if pinned_count >= 3:
            raise ConflictError("You can only pin up to 3 gifts — unpin one first")
        gift.is_pinned = True
        gift.pinned_at = datetime.now(timezone.utc)
    elif not pinned:
        gift.is_pinned = False
        gift.pinned_at = None

    db.add(gift)
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)
```

- [ ] **Step 4: Implement — `stars_payment_service.py`**

In `backend/app/services/stars_payment_service.py`, change the enums import (line 15) to include `GiftKind`:

```python
from app.models.enums import CardSource, GiftKind, TransactionType, WheelSpinSource
```

In `create_gift_invoice`, replace:

```python
    if recipient.id == user.id:
        raise ConflictError("You can't send a gift to yourself")
```

with:

```python
    if recipient.id == user.id and gift_set.kind == GiftKind.bundle:
        raise ConflictError("You can't send a gift to yourself")
```

- [ ] **Step 5: Implement — `routers/gifts.py`**

Replace the full file `backend/app/routers/gifts.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.gift import (
    GiftBuyWithCoinsIn,
    GiftClaimResult,
    GiftOut,
    GiftPinIn,
    GiftPurchaseResult,
    GiftSendIn,
    GiftSetOut,
)
from app.schemas.stars import StarsInvoiceCreateOut, StarsInvoiceStatusOut
from app.services import gift_service, stars_payment_service

router = APIRouter(prefix="/gifts", tags=["gifts"])


@router.get("/sets", response_model=list[GiftSetOut])
async def list_gift_sets(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await gift_service.list_active_gift_sets(db)


@router.post("/invoice", response_model=StarsInvoiceCreateOut)
async def create_gift_invoice(
    payload: GiftSendIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.create_gift_invoice(
        db, user, payload.gift_set_id, payload.recipient_id, payload.message
    )


@router.get("/stars-invoices/{payload_token}", response_model=StarsInvoiceStatusOut)
async def gift_invoice_status(
    payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stars_payment_service.get_invoice_status(db, user, payload_token)


@router.get("/mine", response_model=list[GiftOut])
async def list_my_gifts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await gift_service.list_my_gifts(db, user)


@router.post("/{gift_id}/claim", response_model=GiftClaimResult)
async def claim_gift(gift_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await gift_service.claim_gift(db, user, gift_id)


@router.post("/collectibles/{gift_set_id}/buy-with-coins", response_model=GiftPurchaseResult)
async def buy_collectible_with_coins(
    gift_set_id: int, payload: GiftBuyWithCoinsIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await gift_service.buy_collectible_with_coins(db, user, gift_set_id, payload.recipient_id, payload.message)


@router.patch("/{gift_id}/pin", response_model=GiftOut)
async def pin_gift(
    gift_id: int, payload: GiftPinIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await gift_service.set_gift_pinned(db, user, gift_id, payload.pinned)
```

- [ ] **Step 6: Run all gift tests to verify they pass**

```bash
cd backend
pytest tests/test_gifts.py -v
```
Expected: PASS — all existing tests plus the 7 new ones from Step 1.

- [ ] **Step 7: Run the full backend suite to check for regressions**

```bash
cd backend
pytest tests/ -v
```
Expected: PASS (the `TransactionType`/`CardSource`-style enum growth pattern is already proven safe elsewhere in this codebase — e.g. leagues, wheel-of-fortune — so no other service should be affected).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/gift_service.py backend/app/services/stars_payment_service.py backend/app/routers/gifts.py backend/tests/test_gifts.py
git commit -m "Add collectible gift coin purchase, pinning, and kind-aware claim/self-gift logic"
```

---

### Task 4: Image upload — allow `.gif` for gift-set images

**Files:**
- Modify: `backend/app/services/image_service.py`
- Test: `backend/tests/test_gifts.py`

**Interfaces:**
- Consumes: existing `save_gift_set_image` (unchanged signature).
- Produces: `.gif`/`image/gif` accepted by every `save_*_image` function (shared allowlist).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gifts.py`:

```python
async def test_admin_can_upload_gif_image_for_gift_set(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Анимированный кубок", "kind": "collectible", "coins_price": 100},
    )
    gift_set_id = create_resp.json()["id"]

    gif_bytes = b"GIF89a" + b"\x00" * 20  # minimal fake GIF payload — only the extension/content-type are validated
    upload_resp = await client.post(
        f"/api/v1/admin/gifts/sets/{gift_set_id}/image", headers=auth,
        files={"file": ("cup.gif", gif_bytes, "image/gif")},
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["image_path"].endswith(".gif")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend
pytest tests/test_gifts.py::test_admin_can_upload_gif_image_for_gift_set -v
```
Expected: FAIL with 400 "Extension .gif is not allowed".

- [ ] **Step 3: Implement**

In `backend/app/services/image_service.py`, change:

```python
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
```

to:

```python
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend
pytest tests/test_gifts.py::test_admin_can_upload_gif_image_for_gift_set -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_service.py backend/tests/test_gifts.py
git commit -m "Allow gif uploads for gift-set images"
```

---

### Task 5: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/gifts.ts`

**Interfaces:**
- Produces: `GiftSet.kind`, `GiftSet.coins_price`, `Gift.is_pinned`, `Gift.pinned_at`, `GiftPurchaseResult`, `buyCollectibleWithCoins(giftSetId, recipientId, message?) -> Promise<GiftPurchaseResult>`, `pinGift(giftId, pinned) -> Promise<Gift>`.

- [ ] **Step 1: Update `frontend/src/types/index.ts`**

Replace the existing `GiftSet`, `Gift`, `GiftClaimResult` block (currently lines 624–651):

```typescript
export interface GiftSet {
  id: number;
  name: string;
  description: string;
  image_path: string | null;
  kind: "bundle" | "collectible";
  pack_id: number | null;
  coins_amount: number;
  stars_price: number;
  coins_price: number;
  is_active: boolean;
  sort_order: number;
}

export interface Gift {
  id: number;
  gift_set: GiftSet;
  sender: UserPublic | null;
  message: string | null;
  is_admin_gift: boolean;
  is_pinned: boolean;
  claimed_at: string | null;
  created_at: string;
}

export interface GiftClaimResult {
  gift: Gift;
  pack_result: PackOpenResult | null;
  coins_credited: number;
  new_balance: number;
}

export interface GiftPurchaseResult {
  gift: Gift;
  new_balance: number;
}
```

- [ ] **Step 2: Update `frontend/src/api/gifts.ts`**

Replace the full file:

```typescript
import { api } from "@/lib/api";
import type { Gift, GiftClaimResult, GiftPurchaseResult, GiftSet, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchGiftSets(): Promise<GiftSet[]> {
  const { data } = await api.get<GiftSet[]>("/gifts/sets");
  return data;
}

export async function createGiftInvoice(
  giftSetId: number, recipientId: number, message?: string
): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/gifts/invoice", {
    gift_set_id: giftSetId, recipient_id: recipientId, message,
  });
  return data;
}

export async function fetchGiftInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/gifts/stars-invoices/${payloadToken}`);
  return data;
}

export async function fetchMyGifts(): Promise<Gift[]> {
  const { data } = await api.get<Gift[]>("/gifts/mine");
  return data;
}

export async function claimGift(giftId: number): Promise<GiftClaimResult> {
  const { data } = await api.post<GiftClaimResult>(`/gifts/${giftId}/claim`);
  return data;
}

export async function buyCollectibleWithCoins(
  giftSetId: number, recipientId: number, message?: string
): Promise<GiftPurchaseResult> {
  const { data } = await api.post<GiftPurchaseResult>(`/gifts/collectibles/${giftSetId}/buy-with-coins`, {
    recipient_id: recipientId, message,
  });
  return data;
}

export async function pinGift(giftId: number, pinned: boolean): Promise<Gift> {
  const { data } = await api.patch<Gift>(`/gifts/${giftId}/pin`, { pinned });
  return data;
}
```

- [ ] **Step 3: Verify**

```bash
cd frontend
npm run typecheck
```
Expected: PASS — these are additive interface fields and new exported functions; nothing in the frontend constructs `GiftSet`/`Gift` object literals (they only ever come from API responses), so no existing consumer breaks.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/gifts.ts
git commit -m "Add kind/coins_price/pinning fields and coin-purchase/pin API calls for gifts"
```

---

### Task 6: Admin panel — kind selector, coins price field, gif upload

**Files:**
- Modify: `frontend/src/admin/pages/AdminGiftsPage.tsx`

**Interfaces:**
- Consumes: `GiftSet.kind`, `GiftSet.coins_price` (Task 5).

- [ ] **Step 1: Update `GiftSetForm` and `giftSetToForm`**

```typescript
interface GiftSetForm {
  name: string;
  description: string;
  kind: "bundle" | "collectible";
  pack_id: number | null;
  coins_amount: number;
  stars_price: number;
  coins_price: number;
  is_active: boolean;
  sort_order: number;
}

function giftSetToForm(g?: GiftSet): GiftSetForm {
  return {
    name: g?.name ?? "",
    description: g?.description ?? "",
    kind: g?.kind ?? "bundle",
    pack_id: g?.pack_id ?? null,
    coins_amount: g?.coins_amount ?? 0,
    stars_price: g?.stars_price ?? 0,
    coins_price: g?.coins_price ?? 0,
    is_active: g?.is_active ?? true,
    sort_order: g?.sort_order ?? 0,
  };
}
```

- [ ] **Step 2: Show the kind in the list rows**

In the list item (inside `giftSets?.map(...)`), change the price/status line from:

```tsx
                <p className="text-[11px] text-slate-500">
                  {g.stars_price} ⭐ · {g.coins_amount} монет{g.pack_id ? " · с паком" : ""} ·{" "}
                  {g.is_active ? "Активен" : "Отключён"}
                </p>
```

to:

```tsx
                <p className="text-[11px] text-slate-500">
                  <span className="rounded bg-white/10 px-1.5 py-0.5 font-semibold">
                    {g.kind === "collectible" ? "Коллекционный" : "Набор"}
                  </span>{" "}
                  {g.kind === "collectible"
                    ? `${g.stars_price} ⭐ · ${g.coins_price} монет`
                    : `${g.stars_price} ⭐ · ${g.coins_amount} монет${g.pack_id ? " · с паком" : ""}`}{" "}
                  · {g.is_active ? "Активен" : "Отключён"}
                </p>
```

- [ ] **Step 3: Add the kind selector and conditional fields to the edit form**

Insert a kind selector right after the "Описание" `label` block (before "Пак в наборе"):

```tsx
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Тип подарка</span>
                <div className="flex gap-2 rounded-lg bg-bg-surface p-1">
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, kind: "bundle" })}
                    className={`flex-1 rounded-md py-1.5 text-xs font-semibold ${form.kind === "bundle" ? "bg-accent text-bg-base" : "text-slate-400"}`}
                  >
                    Набор
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, kind: "collectible" })}
                    className={`flex-1 rounded-md py-1.5 text-xs font-semibold ${form.kind === "collectible" ? "bg-accent text-bg-base" : "text-slate-400"}`}
                  >
                    Коллекционный
                  </button>
                </div>
              </label>
```

Wrap the existing "Пак в наборе" and "Монеты в наборе" `label` blocks in a `form.kind === "bundle" && (...)` guard, and add a "Цена в монетах" field guarded by `form.kind === "collectible"` right after the existing "Цена в ⭐" field:

```tsx
              {form.kind === "bundle" && (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Пак в наборе (необязательно)</span>
                    <select
                      value={form.pack_id ?? ""}
                      onChange={(e) => setForm({ ...form, pack_id: e.target.value ? Number(e.target.value) : null })}
                      className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                    >
                      <option value="">Без пака</option>
                      {packs?.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Монеты в наборе</span>
                    <NumberInput min={0} value={form.coins_amount} onChange={(v) => setForm({ ...form, coins_amount: v })} />
                  </label>
                </>
              )}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена в ⭐ (для покупки игроками)</span>
                <NumberInput min={0} value={form.stars_price} onChange={(v) => setForm({ ...form, stars_price: v })} />
              </label>
              {form.kind === "collectible" && (
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">Цена в монетах (для покупки игроками)</span>
                  <NumberInput min={0} value={form.coins_price} onChange={(v) => setForm({ ...form, coins_price: v })} />
                  <span className="text-[10px] text-slate-500">Нужна хотя бы одна цена — в ⭐ или в монетах.</span>
                </label>
              )}
```

- [ ] **Step 4: Allow gif uploads**

Change the file input's `accept` attribute:

```tsx
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="hidden"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadImageMutation.mutate(f); }}
                    />
```

- [ ] **Step 5: Verify**

```bash
cd frontend
npm run typecheck
npm run test -- --run
```
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/pages/AdminGiftsPage.tsx
git commit -m "Add kind selector and coin pricing to the admin gift-set form"
```

---

### Task 7: `GiftsPage.tsx` — collectible collection, shop with two sections, pin/unpin, auto-claim

**Files:**
- Modify: `frontend/src/pages/GiftsPage.tsx`

**Interfaces:**
- Consumes: `fetchMyGifts`, `claimGift`, `fetchGiftSets`, `createGiftInvoice`, `fetchGiftInvoiceStatus`, `buyCollectibleWithCoins`, `pinGift` (Task 5); `Gift`, `GiftSet`, `GiftClaimResult`, `UserPublic`, `TrophyDefinition` types.

- [ ] **Step 1: Replace the full file**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { adminBroadcastGift, adminSendGift, fetchAdminTrophies, grantTrophy } from "@/admin/api";
import {
  buyCollectibleWithCoins,
  claimGift,
  createGiftInvoice,
  fetchGiftInvoiceStatus,
  fetchGiftSets,
  fetchMyGifts,
  pinGift,
} from "@/api/gifts";
import { searchUsers } from "@/api/profile";
import PlayerCard from "@/components/cards/PlayerCard";
import EmptyState from "@/components/common/EmptyState";
import { UserBadge } from "@/components/common/UserBadge";
import { IconCoin, IconGift, IconInboxEmpty, IconSearch, IconTrophy } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { hapticNotify, openTelegramInvoice, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Gift, GiftClaimResult, GiftSet, TrophyDefinition, UserPublic } from "@/types";

export default function GiftsPage() {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"mine" | "shop">("mine");
  const [claimResult, setClaimResult] = useState<GiftClaimResult | null>(null);
  const [detailGift, setDetailGift] = useState<Gift | null>(null);

  const { data: myGifts } = useQuery({ queryKey: ["gifts", "mine"], queryFn: fetchMyGifts });

  const claimMutation = useMutation({
    mutationFn: claimGift,
    onSuccess: (data) => {
      hapticNotify("success");
      updateBalance(data.new_balance);
      setClaimResult(data);
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    },
  });

  // Collectible gifts have no "open" ceremony — a random pack roll needs an
  // explicit claim tap, but a cosmetic collectible's reward *is* the row
  // existing, so silently mark any unclaimed one claimed the moment it shows
  // up, instead of making the player hunt for a button that isn't there.
  useEffect(() => {
    const pendingCollectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible" && !g.claimed_at);
    if (pendingCollectibles.length === 0) return;
    Promise.allSettled(pendingCollectibles.map((g) => claimGift(g.id))).then(() => {
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    });
  }, [myGifts, queryClient]);

  if (!user) return null;

  const collectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible");
  const pendingBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && !g.claimed_at);
  const claimedBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && g.claimed_at);
  const isEmpty = collectibles.length === 0 && pendingBundles.length === 0 && claimedBundles.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconGift size={20} className="text-rarity-epic" />
        Подарки
      </h1>

      {user.is_admin && <AdminGiftControls />}

      <div className="flex gap-2 rounded-2xl bg-bg-surface p-1">
        <button
          onClick={() => setTab("mine")}
          className={`flex-1 rounded-xl py-2 text-sm font-semibold transition ${
            tab === "mine" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Мои подарки{pendingBundles.length > 0 ? ` (${pendingBundles.length})` : ""}
        </button>
        <button
          onClick={() => setTab("shop")}
          className={`flex-1 rounded-xl py-2 text-sm font-semibold transition ${
            tab === "shop" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Магазин подарков
        </button>
      </div>

      {tab === "mine" ? (
        isEmpty ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={() => setTab("shop")}
              className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95"
            >
              Магазин подарков
            </button>
            <EmptyState icon={IconInboxEmpty} title="Подарков пока нет" description="Купи подарок себе или другу в магазине." />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {collectibles.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {collectibles.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => setDetailGift(g)}
                    className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface p-2.5 active:scale-[0.98]"
                  >
                    <span className="relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl bg-rarity-epic/10">
                      {g.gift_set.image_path ? (
                        <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
                      ) : (
                        <IconGift size={26} className="text-rarity-epic" />
                      )}
                      {g.is_pinned && (
                        <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime text-[9px] font-bold text-bg-base">
                          ★
                        </span>
                      )}
                    </span>
                    <span className="w-full truncate text-center text-[11px] font-semibold text-ink-chalk">{g.gift_set.name}</span>
                  </button>
                ))}
              </div>
            )}

            {pendingBundles.length > 0 && (
              <div className="flex flex-col gap-2">
                {pendingBundles.map((g) => (
                  <div key={g.id} className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
                    <div className="flex items-center gap-3">
                      {g.gift_set.image_path ? (
                        <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-12 w-12 rounded-xl object-cover" />
                      ) : (
                        <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-rarity-epic/10">
                          <IconGift size={22} className="text-rarity-epic" />
                        </span>
                      )}
                      <div>
                        <p className="text-sm font-semibold text-ink-chalk">{g.gift_set.name}</p>
                        <p className="text-xs text-ink-mist">
                          {g.sender ? `От ${g.sender.username ?? g.sender.first_name ?? "игрока"}` : "От администрации"}
                        </p>
                        {g.message && <p className="mt-0.5 text-xs italic text-ink-mist-dim">«{g.message}»</p>}
                      </div>
                    </div>
                    <button
                      onClick={() => claimMutation.mutate(g.id)}
                      disabled={claimMutation.isPending}
                      className="shrink-0 rounded-xl bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
                    >
                      Открыть
                    </button>
                  </div>
                ))}
              </div>
            )}

            {claimedBundles.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold text-ink-mist-dim">История</p>
                <div className="flex flex-col gap-1.5">
                  {claimedBundles.map((g) => (
                    <div key={g.id} className="flex items-center justify-between rounded-xl bg-bg-surface/60 px-3 py-2 text-xs">
                      <span className="text-ink-mist">{g.gift_set.name}</span>
                      <span className="text-ink-mist-dim">{new Date(g.claimed_at!).toLocaleDateString("ru-RU")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      ) : (
        <ShopTab />
      )}

      {claimResult && <GiftClaimResultModal result={claimResult} onClose={() => setClaimResult(null)} />}
      {detailGift && <GiftDetailSheet gift={detailGift} onClose={() => setDetailGift(null)} />}
    </div>
  );
}

function GiftClaimResultModal({ result, onClose }: { result: GiftClaimResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <p className="flex items-center justify-center gap-1.5 text-center font-display text-base font-bold text-ink-chalk">
          <IconGift size={18} className="text-rarity-epic" />
          Подарок открыт!
        </p>

        {result.coins_credited > 0 && (
          <div className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-accent-green/10 py-2 font-mono text-sm font-bold text-accent-green">
            +{result.coins_credited} <IconCoin size={14} />
          </div>
        )}

        {result.pack_result && result.pack_result.cards.length > 0 && (
          <div className="mt-3 grid grid-cols-3 gap-2">
            {result.pack_result.cards.map((c) => (
              <PlayerCard key={c.card.id} player={c.card.player} size="sm" />
            ))}
          </div>
        )}

        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Отлично!
        </button>
      </div>
    </div>
  );
}

function GiftDetailSheet({ gift, onClose }: { gift: Gift; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const pinMutation = useMutation({
    mutationFn: (pinned: boolean) => pinGift(gift.id, pinned),
    onSuccess: () => {
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось изменить закрепление"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5 text-center" onClick={(e) => e.stopPropagation()}>
        <span className="mx-auto flex h-24 w-24 items-center justify-center overflow-hidden rounded-2xl bg-rarity-epic/10">
          {gift.gift_set.image_path ? (
            <img src={staticUrl(gift.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
          ) : (
            <IconGift size={40} className="text-rarity-epic" />
          )}
        </span>
        <p className="mt-3 font-display text-base font-bold text-ink-chalk">{gift.gift_set.name}</p>
        <p className="mt-1 text-xs text-ink-mist">
          {gift.sender ? `От ${gift.sender.username ?? gift.sender.first_name ?? "игрока"}` : "От администрации"}
        </p>
        {gift.message && <p className="mt-1 text-xs italic text-ink-mist-dim">«{gift.message}»</p>}

        {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

        <button
          onClick={() => pinMutation.mutate(!gift.is_pinned)}
          disabled={pinMutation.isPending}
          className="mt-4 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {gift.is_pinned ? "Открепить" : "Закрепить в профиле"}
        </button>
        <button onClick={onClose} className="mt-2 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Закрыть
        </button>
      </div>
    </div>
  );
}

function RecipientPicker({ target, onSelect }: { target: UserPublic | null; onSelect: (u: UserPublic | null) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2 && !target,
  });

  if (target) {
    return (
      <div className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2.5">
        <span className="flex items-center gap-1 text-sm text-ink-chalk">
          {target.username ?? target.first_name ?? `Игрок #${target.id}`}
          <UserBadge badge={target.active_badge} />
        </span>
        <button onClick={() => onSelect(null)} className="text-xs text-accent-lime">Сменить</button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Введи имя пользователя..."
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />
      {results && results.length > 0 && (
        <div className="flex flex-col gap-1">
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => onSelect(u)}
              className="flex items-center justify-between rounded-xl bg-black/20 px-3 py-2 text-left active:scale-[0.98]"
            >
              <span className="flex items-center gap-1 text-sm text-ink-chalk">
                {u.username ?? u.first_name ?? `Игрок #${u.id}`}
                <UserBadge badge={u.active_badge} />
              </span>
            </button>
          ))}
        </div>
      )}
      {query.length >= 2 && results?.length === 0 && (
        <EmptyState icon={IconSearch} title="Никого не найдено" />
      )}
    </div>
  );
}

function ShopTab() {
  const { data: giftSets } = useQuery({ queryKey: ["gift-sets"], queryFn: fetchGiftSets });
  const [selectedSet, setSelectedSet] = useState<GiftSet | null>(null);

  const bundleSets = (giftSets ?? []).filter((g) => g.kind === "bundle");
  const collectibleSets = (giftSets ?? []).filter((g) => g.kind === "collectible");

  if (selectedSet) {
    return <CollectiblePurchasePanel giftSet={selectedSet} onDone={() => setSelectedSet(null)} />;
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Наборы</p>
        {bundleSets.length > 0 ? (
          <BundleShop giftSets={bundleSets} />
        ) : (
          <EmptyState icon={IconGift} title="Наборов пока нет" description="Загляни позже — мы готовим подарки." />
        )}
      </div>
      <div>
        <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Коллекционные</p>
        {collectibleSets.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {collectibleSets.map((g) => (
              <button
                key={g.id}
                onClick={() => setSelectedSet(g)}
                className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-3 text-center active:scale-[0.98]"
              >
                {g.image_path ? (
                  <img src={staticUrl(g.image_path) ?? undefined} className="h-16 w-16 rounded-xl object-cover" />
                ) : (
                  <span className="flex h-16 w-16 items-center justify-center rounded-xl bg-rarity-epic/10">
                    <IconGift size={28} className="text-rarity-epic" />
                  </span>
                )}
                <p className="text-sm font-semibold text-ink-chalk">{g.name}</p>
                <p className="flex items-center gap-2 font-mono text-xs font-bold text-accent-lime">
                  {!!g.coins_price && (
                    <span className="flex items-center gap-1">
                      <IconCoin size={11} />
                      {g.coins_price}
                    </span>
                  )}
                  {!!g.stars_price && <span>{g.stars_price} ⭐</span>}
                </p>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState icon={IconGift} title="Коллекционных подарков пока нет" description="Загляни позже — мы готовим подарки." />
        )}
      </div>
    </div>
  );
}

function CollectiblePurchasePanel({ giftSet, onDone }: { giftSet: GiftSet; onDone: () => void }) {
  const user = useAuthStore((s) => s.user);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const [recipientMode, setRecipientMode] = useState<"self" | "friend">("self");
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [currency, setCurrency] = useState<"stars" | "coins">(giftSet.coins_price > 0 ? "coins" : "stars");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const recipientId = recipientMode === "self" ? user?.id : target?.id;

  const handleBuyWithCoins = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const result = await buyCollectibleWithCoins(giftSet.id, recipientId, message || undefined);
      updateBalance(result.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Не удалось купить подарок");
    } finally {
      setBusy(false);
    }
  };

  const handleBuyWithStars = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const invoice = await createGiftInvoice(giftSet.id, recipientId, message || undefined);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusy(false);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusy(false);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchGiftInvoiceStatus(invoice.payload_token);
        if (status.status === "completed") {
          hapticNotify("success");
          queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
          setSuccess(true);
          setBusy(false);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Подарок ещё не отправлен — попробуй проверить через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось отправить подарок");
      setBusy(false);
    }
  };

  const handleConfirm = () => (currency === "coins" ? handleBuyWithCoins() : handleBuyWithStars());

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-6 text-center">
        <IconGift size={32} className="text-rarity-epic" />
        <p className="font-display text-base font-bold text-ink-chalk">Подарок отправлен!</p>
        <button onClick={onDone} className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
          Готово
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-chalk">{giftSet.name}</p>
        <button onClick={onDone} className="text-xs text-accent-lime">Назад</button>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex gap-2 rounded-xl bg-black/20 p-1">
        <button
          onClick={() => { setRecipientMode("self"); setTarget(null); }}
          className={`flex-1 rounded-lg py-2 text-xs font-semibold ${recipientMode === "self" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
        >
          Себе
        </button>
        <button
          onClick={() => setRecipientMode("friend")}
          className={`flex-1 rounded-lg py-2 text-xs font-semibold ${recipientMode === "friend" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
        >
          Другу
        </button>
      </div>

      {recipientMode === "friend" && <RecipientPicker target={target} onSelect={setTarget} />}

      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        maxLength={500}
        placeholder="Поздравительная надпись (необязательно)"
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      {giftSet.stars_price > 0 && giftSet.coins_price > 0 && (
        <div className="flex gap-2 rounded-xl bg-black/20 p-1">
          <button
            onClick={() => setCurrency("coins")}
            className={`flex flex-1 items-center justify-center gap-1 rounded-lg py-2 text-xs font-semibold ${currency === "coins" ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            <IconCoin size={12} />
            {giftSet.coins_price}
          </button>
          <button
            onClick={() => setCurrency("stars")}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold ${currency === "stars" ? "bg-amber-400 text-bg-base" : "text-ink-mist"}`}
          >
            {giftSet.stars_price} ⭐
          </button>
        </div>
      )}

      <button
        onClick={handleConfirm}
        disabled={(recipientMode === "friend" && !target) || busy}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Отправка..." : `Отправить за ${currency === "coins" ? `${giftSet.coins_price} монет` : `${giftSet.stars_price} ⭐`}`}
      </button>
    </div>
  );
}

function BundleShop({ giftSets }: { giftSets: GiftSet[] }) {
  const [selectedSet, setSelectedSet] = useState<GiftSet | null>(null);
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSend = async () => {
    if (!selectedSet || !target) return;
    setError(null);
    setBusy(true);
    try {
      const invoice = await createGiftInvoice(selectedSet.id, target.id, message || undefined);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusy(false);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusy(false);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchGiftInvoiceStatus(invoice.payload_token);
        if (status.status === "completed") {
          hapticNotify("success");
          setSuccess(true);
          setBusy(false);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Подарок ещё не отправлен — попробуй проверить через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось отправить подарок");
      setBusy(false);
    }
  };

  if (success) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-6 text-center">
        <IconGift size={32} className="text-rarity-epic" />
        <p className="font-display text-base font-bold text-ink-chalk">Подарок отправлен!</p>
        <p className="text-sm text-ink-mist">{target?.username ?? target?.first_name} сможет открыть его в своём профиле.</p>
        <button
          onClick={() => { setSuccess(false); setSelectedSet(null); setTarget(null); setMessage(""); }}
          className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Отправить ещё один
        </button>
      </div>
    );
  }

  if (!selectedSet) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {giftSets.map((g) => (
          <button
            key={g.id}
            onClick={() => setSelectedSet(g)}
            className="flex flex-col items-center gap-2 rounded-2xl bg-bg-surface p-3 text-center active:scale-[0.98]"
          >
            {g.image_path ? (
              <img src={staticUrl(g.image_path) ?? undefined} className="h-16 w-16 rounded-xl object-cover" />
            ) : (
              <span className="flex h-16 w-16 items-center justify-center rounded-xl bg-rarity-epic/10">
                <IconGift size={28} className="text-rarity-epic" />
              </span>
            )}
            <p className="text-sm font-semibold text-ink-chalk">{g.name}</p>
            <p className="font-mono text-xs font-bold text-accent-lime">{g.stars_price} ⭐</p>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-chalk">{selectedSet.name}</p>
        <button onClick={() => setSelectedSet(null)} className="text-xs text-accent-lime">Сменить набор</button>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <RecipientPicker target={target} onSelect={setTarget} />

      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        maxLength={500}
        placeholder="Поздравительная надпись (необязательно)"
        className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
      />

      <button
        onClick={handleSend}
        disabled={!target || busy}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {busy ? "Отправка..." : `Отправить за ${selectedSet.stars_price} ⭐`}
      </button>
    </div>
  );
}

function AdminGiftControls() {
  const queryClient = useQueryClient();
  const { data: giftSets } = useQuery({ queryKey: ["gift-sets"], queryFn: fetchGiftSets });
  const { data: trophies } = useQuery({ queryKey: ["admin-trophies"], queryFn: fetchAdminTrophies });
  const [action, setAction] = useState<"send" | "broadcast" | "trophy" | null>(null);
  const [giftSetId, setGiftSetId] = useState<number | "">("");
  const [trophyId, setTrophyId] = useState<number | "">("");
  const [target, setTarget] = useState<UserPublic | null>(null);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setGiftSetId(""); setTrophyId(""); setTarget(null); setMessage(""); setError(null); };

  const sendMutation = useMutation({
    mutationFn: () => adminSendGift(Number(giftSetId), target!.id, message || undefined),
    onSuccess: () => { setNotice("Подарок отправлен игроку"); reset(); setAction(null); queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] }); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось отправить подарок"),
  });

  const broadcastMutation = useMutation({
    mutationFn: () => adminBroadcastGift(Number(giftSetId), message || undefined),
    onSuccess: (data) => { setNotice(`Подарок разослан ${data.recipients} игрокам`); reset(); setAction(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось разослать подарок"),
  });

  const trophyMutation = useMutation({
    mutationFn: () => grantTrophy(target!.id, Number(trophyId), message || undefined),
    onSuccess: () => { setNotice("Трофей вручён"); reset(); setAction(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось вручить трофей"),
  });

  return (
    <div className="rounded-2xl border border-rarity-epic/30 bg-rarity-epic/5 p-4">
      <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
        <IconTrophy size={15} className="text-rarity-epic" />
        Админ-инструменты
      </p>
      {notice && <p className="mt-2 rounded-xl bg-accent-green/10 px-3 py-2 text-xs text-accent-green">{notice}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={() => { setAction(action === "send" ? null : "send"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "send" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Отправить игроку
        </button>
        <button onClick={() => { setAction(action === "broadcast" ? null : "broadcast"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "broadcast" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Разослать всем
        </button>
        <button onClick={() => { setAction(action === "trophy" ? null : "trophy"); reset(); setNotice(null); }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${action === "trophy" ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          Подарить трофей
        </button>
      </div>

      {action && (
        <div className="mt-3 flex flex-col gap-2">
          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

          {action !== "trophy" && (
            <select
              value={giftSetId}
              onChange={(e) => setGiftSetId(e.target.value ? Number(e.target.value) : "")}
              className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk outline-none"
            >
              <option value="">Выбери набор...</option>
              {giftSets?.map((g) => (
                <option key={g.id} value={g.id}>{g.name}{g.kind === "collectible" ? " (коллекционный)" : ""}</option>
              ))}
            </select>
          )}

          {action === "trophy" && (
            <select
              value={trophyId}
              onChange={(e) => setTrophyId(e.target.value ? Number(e.target.value) : "")}
              className="rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk outline-none"
            >
              <option value="">Выбери трофей...</option>
              {trophies?.map((t: TrophyDefinition) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}

          {action !== "broadcast" && <RecipientPicker target={target} onSelect={setTarget} />}

          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={500}
            rows={4}
            placeholder="Подпись (необязательно) — переносы строк и HTML-теги (например <blockquote>) сохраняются как есть"
            className="resize-y rounded-xl bg-black/20 px-3 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
          />

          {action === "send" && (
            <button
              onClick={() => sendMutation.mutate()}
              disabled={!giftSetId || !target || sendMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Отправить бесплатно
            </button>
          )}
          {action === "broadcast" && (
            <button
              onClick={async () => {
                if (await showConfirm("Разослать этот набор бесплатно всем зарегистрированным игрокам?")) broadcastMutation.mutate();
              }}
              disabled={!giftSetId || broadcastMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Разослать всем
            </button>
          )}
          {action === "trophy" && (
            <button
              onClick={() => trophyMutation.mutate()}
              disabled={!trophyId || !target || trophyMutation.isPending}
              className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Вручить трофей
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify**

```bash
cd frontend
npm run typecheck
npm run test -- --run
```
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/GiftsPage.tsx
git commit -m "Rework GiftsPage into mine/shop tabs with collectible collection, pinning, and dual-currency purchase"
```

---

### Task 8: `ProfilePage.tsx` — move the "Подарки" block under "Трофеи", show pinned collectibles

**Files:**
- Modify: `frontend/src/pages/ProfilePage.tsx`

**Interfaces:**
- Consumes: `fetchMyGifts` (Task 5), `Gift.is_pinned`.

- [ ] **Step 1: Add the gifts query**

Add the import (alongside the existing `fetchMyBadges, fetchMyProfile, ...` import line 9):

```typescript
import { fetchMyGifts } from "@/api/gifts";
```

Add the query right after the existing `trophies` query (line 75):

```typescript
  const { data: trophies } = useQuery({ queryKey: ["profile", "trophies"], queryFn: fetchMyTrophies });
  const { data: myGifts } = useQuery({ queryKey: ["gifts", "mine"], queryFn: fetchMyGifts });
  const pinnedGifts = myGifts?.filter((g) => g.is_pinned) ?? [];
```

- [ ] **Step 2: Remove the old bottom "Подарки" button section**

Delete this block entirely (currently right after the "Купить монеты за ⭐" section):

```tsx
      <section className="rounded-2xl bg-bg-surface p-4">
        <button
          onClick={() => navigate("/gifts")}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-rarity-epic/80 py-3 text-sm font-bold text-white active:scale-95"
        >
          <IconGift size={16} />
          Подарки
        </button>
      </section>
```

- [ ] **Step 3: Insert the new block right after the Трофеи section**

Insert immediately after the Трофеи section's closing `)}` (right before the stats `<section className="rounded-2xl bg-bg-surface p-4">` that renders `<Stat label="Баланс" ...>`):

```tsx
      <button
        onClick={() => navigate("/gifts")}
        className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]"
      >
        <span className="flex items-center gap-1.5 font-display text-base font-bold text-ink-chalk">
          <IconGift size={16} className="text-rarity-epic" />
          Подарки
        </span>
        <span className="flex items-center gap-2">
          {pinnedGifts.length > 0 ? (
            <span className="flex -space-x-2">
              {pinnedGifts.slice(0, 3).map((g) => (
                <span
                  key={g.id}
                  className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border-2 border-bg-surface bg-rarity-epic/10"
                >
                  {g.gift_set.image_path ? (
                    <img src={staticUrl(g.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
                  ) : (
                    <IconGift size={14} className="text-rarity-epic" />
                  )}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-xs text-ink-mist-dim">Закрепи любимые подарки</span>
          )}
          <IconChevronRight size={16} className="text-ink-mist-dim" />
        </span>
      </button>
```

- [ ] **Step 4: Verify**

```bash
cd frontend
npm run typecheck
npm run test -- --run
```
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProfilePage.tsx
git commit -m "Move Подарки block under Трофеи in profile, show up to 3 pinned collectibles"
```

---

### Task 9: End-to-end manual verification

**Files:** none (verification only).

- [ ] **Step 1: Start the environment**

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
```
Expected: containers healthy, migration `0052` applies cleanly against real Postgres (this is the one check the SQLite-backed pytest suite cannot cover).

- [ ] **Step 2: Admin — create a collectible gift set**

In the admin panel (`/admin` → Подарки), create a new gift set, select "Коллекционный", set a coin price and a Stars price, upload a `.gif`. Confirm the list shows the "Коллекционный" tag and both prices.

- [ ] **Step 3: Player — empty state and shop**

As a non-admin player with zero gifts, open Profile → confirm the new block sits directly under "Трофеи" and shows "Закрепи любимые подарки". Tap it → confirm `/gifts` shows the "Подарков пока нет" empty state with the "Магазин подарков" button above it. Tap that button (or the "Магазин подарков" tab) → confirm both "Наборы" and "Коллекционные" sections render.

- [ ] **Step 4: Buy a collectible for yourself with coins**

Tap the collectible created in Step 2 → confirm "Себе" is selected by default → confirm the currency toggle shows both options → pick "монеты" → confirm → confirm balance drops by the coin price and the item now appears in "Мои подарки" without any manual "open" step.

- [ ] **Step 5: Pin/unpin**

Tap the newly-owned collectible in the grid → tap "Закрепить в профиле" → go back to Profile → confirm it now shows in the pinned row under "Подарки". Repeat with 2 more (real or admin-granted) collectibles to hit 3 pinned, then confirm a 4th pin attempt shows the "unpin one first" error.

- [ ] **Step 6: Buy a collectible for a friend with Stars**

Using a second test account's id, switch to "Другу", search/select them, pick the "⭐" currency, confirm the Telegram Stars invoice flow completes (or is exercised via the existing dev-mode/test payment path used elsewhere in this codebase), and confirm the recipient sees it appear in their own "Мои подарки" automatically.

- [ ] **Step 7: Confirm the old bundle flow is untouched**

Buy one of the existing bundle gift sets for a friend via "Наборы" — confirm it still requires the recipient to tap "Открыть" and still lands in "История" after claiming.

- [ ] **Step 8: Regression pass**

```bash
cd backend && pytest tests/ -v
cd frontend && npm run typecheck && npm run test -- --run && npm run build
```
Expected: all green.
