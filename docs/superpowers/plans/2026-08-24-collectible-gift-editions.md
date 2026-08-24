# Collectible Gift Editions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add serial numbers (with an optional capped supply) to collectible gifts, let admins tag one with an existing `CardCollection`, let admins configure a purchase prize (coins/pack) for either gift kind, and give that prize a reveal moment — which means removing the silent background auto-claim shipped for collectibles and restoring the manual "Открыть" step for gifts received from someone else, while self-purchases get an immediate reveal.

**Architecture:** Two new `GiftSet` columns (`max_supply`, `next_serial_number`) plus one new `Gift` column (`serial_number`), minted by a single row-locked helper reused by all four gift-creation paths (coin purchase, Stars purchase, admin send, admin broadcast). `claim_gift`'s collectible-specific early-return is deleted so both kinds share one reward-granting code path — a collectible with no configured prize behaves exactly as before (claims, grants nothing); one with `coins_amount`/`pack_id` configured now grants it, identically to a bundle.

**Tech Stack:** FastAPI + async SQLAlchemy 2 + Alembic (backend), React 18 + TypeScript + TanStack Query + Tailwind (frontend), pytest (async, in-memory SQLite) for backend tests.

**Spec:** [docs/superpowers/specs/2026-08-24-collectible-gift-editions-design.md](../specs/2026-08-24-collectible-gift-editions-design.md)

## Global Constraints

- `max_supply` is nullable (`null` = unlimited); `0` is never a valid value for it — the admin form uses `0` in its own local form state purely as a UI sentinel for "unlimited" and must convert `0 → null` before sending to the API (mirrors nowhere else in this codebase, called out explicitly per task below).
- Every gift-creation path must reserve serial numbers through the one shared `gift_service.reserve_gift_serial_numbers` helper — never increment `next_serial_number` inline anywhere else.
- Lock order when both a `User` and a `GiftSet` are locked in the same transaction: `User` first, then `GiftSet` (matches `buy_collectible_with_coins`'s existing order) — never the reverse, to avoid deadlocks.
- `collection_id` is descriptive only — it must never be read by `UserCollectionReward`/collection-completion logic.
- Preserve idempotency and existing test behavior — every existing test in `backend/tests/test_gifts.py` must keep passing unmodified.
- Frontend: `npm run typecheck` and `npm run test -- --run` must pass after every frontend task.
- Backend: `pytest tests/test_gifts.py -v` must pass after every backend task; `python -c "from app.main import app"` sanity check after any model/schema change.

---

### Task 1: Data model, migration, schemas

**Files:**
- Modify: `backend/app/models/gift.py`
- Create: `backend/alembic/versions/0053_gift_editions.py`
- Modify: `backend/app/schemas/gift.py`

**Interfaces:**
- Produces: `GiftSet.max_supply: Optional[int]`, `GiftSet.next_serial_number: int`, `GiftSet.collection_id: Optional[int]`, `Gift.serial_number: Optional[int]`; `GiftSetOut`/`GiftSetCreate`/`GiftSetUpdate` gain `max_supply`, `collection_id` (`GiftSetOut` additionally exposes `next_serial_number`); `GiftOut` gains `serial_number`.

- [ ] **Step 1: Extend `GiftSet` and `Gift` in `app/models/gift.py`**

In `class GiftSet`, add three new columns right after `coins_price`:

```python
    coins_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_serial_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    collection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

(only the three new lines between `coins_price` and `is_active` are additions — both of those already exist, shown for exact placement).

In `class Gift`, add one new column right after `pinned_at`:

```python
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    serial_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

(`pinned_at` and `claimed_at` already exist — only the `serial_number` line is new).

No new import is needed — `ForeignKey`, `Integer`, `Optional` are already imported in this file.

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/0053_gift_editions.py`:

```python
"""Collectible gift editions: serial numbers, max supply, collection tag

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gift_sets", sa.Column("max_supply", sa.Integer(), nullable=True))
    op.add_column("gift_sets", sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "gift_sets",
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("gifts", sa.Column("serial_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("gifts", "serial_number")
    op.drop_column("gift_sets", "collection_id")
    op.drop_column("gift_sets", "next_serial_number")
    op.drop_column("gift_sets", "max_supply")
```

- [ ] **Step 3: Extend `backend/app/schemas/gift.py`**

In `GiftSetOut`, add three fields right after `coins_price`:

```python
    coins_price: int
    max_supply: Optional[int] = None
    next_serial_number: int
    collection_id: Optional[int] = None
    is_active: bool
```

(only the three new lines between `coins_price` and `is_active` are additions).

In `GiftSetCreate`, add two fields right after `coins_price`:

```python
    coins_price: int = Field(default=0, ge=0)
    max_supply: Optional[int] = Field(default=None, ge=1)
    collection_id: Optional[int] = None
    is_active: bool = True
```

In `GiftSetUpdate`, add two fields right after `coins_price`:

```python
    coins_price: Optional[int] = Field(default=None, ge=0)
    max_supply: Optional[int] = Field(default=None, ge=1)
    collection_id: Optional[int] = None
    is_active: Optional[bool] = None
```

In `GiftOut`, add one field right after `is_pinned`:

```python
    is_pinned: bool
    serial_number: Optional[int] = None
    claimed_at: Optional[datetime] = None
```

- [ ] **Step 4: Verify**

```bash
cd backend
python -c "from app.main import app"
pytest tests/test_gifts.py -v
```
Expected: import succeeds, all 17 existing gift tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/gift.py backend/alembic/versions/0053_gift_editions.py backend/app/schemas/gift.py
git commit -m "Add serial number, max supply, and collection tag columns to gift models"
```

---

### Task 2: Backend logic — serial minting, unified claim reward, admin validation

**Files:**
- Modify: `backend/app/services/gift_service.py`
- Modify: `backend/app/services/stars_payment_service.py`
- Modify: `backend/app/routers/admin_gifts.py`
- Test: `backend/tests/test_gifts.py`

**Interfaces:**
- Consumes: `GiftSet.max_supply`/`next_serial_number`/`collection_id`, `Gift.serial_number` (Task 1).
- Produces: `gift_service.reserve_gift_serial_numbers(db, gift_set, count=1) -> Optional[int]`, simplified `claim_gift` (no kind branch), serial-aware `buy_collectible_with_coins`/`admin_send_gift_to_user`/`admin_broadcast_gift`, serial-aware `stars_payment_service.deliver_payment`'s gift branch, `admin_gifts._validate_max_supply`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_gifts.py`:

```python
async def test_collectible_purchases_get_sequential_serial_numbers(client, db_session, bot_token):
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0)
    buyer = await _register(client, db_session, 860020, bot_token)
    headers = telegram_headers(860020, bot_token)

    first = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers, json={"recipient_id": buyer.id},
    )
    second = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers, json={"recipient_id": buyer.id},
    )
    assert first.json()["gift"]["serial_number"] == 1
    assert second.json()["gift"]["serial_number"] == 2


async def test_buying_past_max_supply_is_rejected_and_not_charged(client, db_session, bot_token):
    gift_set = await create_gift_set(
        db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0, max_supply=1,
    )
    buyer = await _register(client, db_session, 860021, bot_token)
    headers = telegram_headers(860021, bot_token)

    first = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers, json={"recipient_id": buyer.id},
    )
    assert first.status_code == 200
    balance_after_first = first.json()["new_balance"]

    second = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers, json={"recipient_id": buyer.id},
    )
    assert second.status_code == 409

    await db_session.refresh(buyer)
    assert buyer.balance == balance_after_first


async def test_claiming_collectible_with_configured_prize_grants_it(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.epic)
    pack = await create_pack(db_session, "gift-prize-pack", price=0, card_count=1, probabilities={Rarity.epic: 1.0})
    gift_set = await create_gift_set(
        db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0,
        coins_amount=25, pack_id=pack.id,
    )
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860022, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860022)

    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]
    assert send_resp.json()["serial_number"] == 1

    claim_resp = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["coins_credited"] == 25
    assert len(body["pack_result"]["cards"]) == 1
    assert body["new_balance"] == 500 + 25


async def test_broadcast_rejected_when_supply_cant_cover_all_recipients(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await _register(client, db_session, 860023, bot_token)
    await _register(client, db_session, 860024, bot_token)

    gift_set = await create_gift_set(
        db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0, max_supply=1,
    )

    resp = await client.post(
        "/api/v1/admin/gifts/broadcast", headers=auth,
        json={"gift_set_id": gift_set.id},
    )
    assert resp.status_code == 409

    mine = await client.get("/api/v1/gifts/mine", headers=telegram_headers(860023, bot_token))
    assert mine.json() == []


async def test_admin_cannot_shrink_max_supply_below_issued_count(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0)
    recipient_headers = telegram_headers(860025, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860025)

    for _ in range(2):
        await client.post(
            "/api/v1/admin/gifts/send", headers=auth,
            json={"gift_set_id": gift_set.id, "user_id": recipient.id},
        )

    resp = await client.put(
        f"/api/v1/admin/gifts/sets/{gift_set.id}", headers=auth, json={"max_supply": 1},
    )
    assert resp.status_code == 409
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd backend
pytest tests/test_gifts.py -k "serial_numbers or max_supply or configured_prize or broadcast_rejected or shrink_max_supply" -v
```
Expected: FAIL — `serial_number` isn't set anywhere yet, `max_supply` isn't enforced, claiming a collectible with a configured prize currently grants nothing (the old early-return is still in place), and `update_gift_set` has no shrink guard.

- [ ] **Step 3: Implement — `gift_service.py`**

Add this function to `backend/app/services/gift_service.py`, right after `list_my_gifts` and before `claim_gift`:

```python
async def reserve_gift_serial_numbers(db: AsyncSession, gift_set: GiftSet, count: int = 1) -> Optional[int]:
    """Atomically reserves `count` consecutive serial numbers on a
    collectible gift_set and returns the first one — None for a bundle,
    which is never numbered. Row-locks gift_set so concurrent mints (two
    purchases, or a purchase racing an admin broadcast) can't hand out the
    same number. Enforces max_supply; raises rather than partially
    fulfilling an over-capacity request."""
    if gift_set.kind != GiftKind.collectible:
        return None
    result = await db.execute(
        select(GiftSet).where(GiftSet.id == gift_set.id).with_for_update().execution_options(populate_existing=True)
    )
    locked = result.scalar_one()
    start = locked.next_serial_number
    end = start + count - 1
    if locked.max_supply is not None and end > locked.max_supply:
        remaining = max(0, locked.max_supply - start + 1)
        raise ConflictError(f"Недостаточно тиража: осталось {remaining}, а нужно {count}")
    locked.next_serial_number = end + 1
    db.add(locked)
    return start
```

Replace `claim_gift` in full — this deletes the collectible early-return block so both kinds share the same reward logic:

```python
async def claim_gift(db: AsyncSession, user: User, gift_id: int) -> GiftClaimResult:
    """Opens a pending gift — reward is only granted once the recipient
    explicitly claims it (never on receipt), mirroring opening a pack. Row
    locks the gift before checking claimed_at so two concurrent claim taps
    (e.g. a double-tap) can't both pass the check and deliver twice.

    Both gift kinds share this exact reward logic: a collectible with no
    configured coins_amount/pack_id just claims with nothing granted (the
    common case — the row's existence is its own reward); one with a prize
    configured grants it exactly like a bundle does."""
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.claimed_at is not None:
        raise ConflictError("This gift was already claimed")

    gift_set = gift.gift_set

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

In `admin_send_gift_to_user`, mint the serial number before constructing the `Gift`:

```python
async def admin_send_gift_to_user(db: AsyncSession, gift_set_id: int, user_id: int, message: Optional[str]) -> GiftOut:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    recipient = await db.get(User, user_id)
    if recipient is None:
        raise NotFoundError("User not found")

    serial_number = await reserve_gift_serial_numbers(db, gift_set)

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=None, recipient_id=recipient.id, message=message,
        is_admin_gift=True, serial_number=serial_number,
    )
    db.add(gift)
    db.add(
        Notification(
            user_id=recipient.id, type=NotificationType.admin_message,
            title="🎁 Подарок!", body=message or "Тебе подарок в приложении — открой и забери!",
        )
    )
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)
```

In `admin_broadcast_gift`, reserve a block and assign per-row:

```python
async def admin_broadcast_gift(db: AsyncSession, gift_set_id: int, message: Optional[str]) -> int:
    """Grants gift_set_id free to every registered user (a holiday-style
    giveaway) via a single bulk INSERT rather than one ORM object per user.

    Also queues a real Telegram notification per recipient (same
    Notification table + notifier.py delivery path as
    broadcast_service.send_update_broadcast), so the bulk grant doesn't sit
    silently in-app — recipients are paced at notifier.py's rate limit
    rather than pinged all at once."""
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")

    user_ids = (await db.execute(select(User.id))).scalars().all()
    if not user_ids:
        return 0

    start_serial = await reserve_gift_serial_numbers(db, gift_set, count=len(user_ids))

    now = datetime.now(timezone.utc)
    await db.execute(
        insert(Gift),
        [
            {
                "gift_set_id": gift_set.id, "sender_id": None, "recipient_id": uid,
                "message": message, "is_admin_gift": True, "claimed_at": None,
                "serial_number": (start_serial + i) if start_serial is not None else None,
                "created_at": now, "updated_at": now,
            }
            for i, uid in enumerate(user_ids)
        ],
    )
    await db.execute(
        insert(Notification),
        [
            {
                "user_id": uid, "type": NotificationType.admin_message,
                "title": "🎁 Подарок!", "body": message or "Тебе подарок в приложении — открой и забери!",
                "is_read": False, "telegram_sent": False, "created_at": now,
            }
            for uid in user_ids
        ],
    )
    await db.commit()
    return len(user_ids)
```

In `buy_collectible_with_coins`, mint before debiting:

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
    serial_number = await reserve_gift_serial_numbers(db, gift_set)
    await debit_coins(
        db, buyer, gift_set.coins_price, TransactionType.gift_purchase_coins,
        f"Подарок «{gift_set.name}»", related_object_type="gift_set", related_object_id=gift_set.id,
    )

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=buyer.id, recipient_id=recipient.id, message=message,
        is_admin_gift=False, serial_number=serial_number,
    )
    db.add(gift)
    await db.commit()
    await db.refresh(buyer)
    await db.refresh(gift)

    return GiftPurchaseResult(gift=GiftOut.model_validate(gift), new_balance=buyer.balance)
```

- [ ] **Step 4: Implement — `stars_payment_service.py`**

Add `from app.services import gift_service` to the imports (alongside the existing `from app.services import collection_service` line).

In `create_gift_invoice`, add a non-authoritative sold-out check right after the existing `if gift_set.stars_price <= 0: raise ConflictError(...)` line:

```python
    if gift_set.kind == GiftKind.collectible and gift_set.max_supply is not None and gift_set.next_serial_number > gift_set.max_supply:
        raise ConflictError("Тираж этого подарка распродан")
```

In `deliver_payment`'s `elif invoice.gift_set_id is not None:` branch, mint before constructing `Gift`:

```python
    elif invoice.gift_set_id is not None:
        gift_set = await db.get(GiftSet, invoice.gift_set_id)
        if gift_set is None or not gift_set.is_active or gift_set.stars_price != total_amount:
            raise ConflictError("This gift set is no longer available")

        serial_number = await gift_service.reserve_gift_serial_numbers(db, gift_set)

        gift = Gift(
            gift_set_id=gift_set.id, sender_id=invoice.user_id, recipient_id=invoice.gift_recipient_id,
            message=invoice.gift_message, is_admin_gift=False, serial_number=serial_number,
        )
        db.add(gift)
        await db.flush()
        invoice.gift_id = gift.id
```

- [ ] **Step 5: Implement — `admin_gifts.py`**

Add a second validator right after `_validate_collectible_pricing`:

```python
def _validate_max_supply(gift_set: GiftSet) -> None:
    if gift_set.max_supply is not None and gift_set.max_supply < gift_set.next_serial_number - 1:
        raise ConflictError("Нельзя уменьшить тираж ниже уже выпущенного количества")
```

Call it alongside `_validate_collectible_pricing` in both `create_gift_set` and `update_gift_set` — in `create_gift_set`, right after the existing `_validate_collectible_pricing(gift_set)` line:

```python
    gift_set = GiftSet(**payload.model_dump())
    _validate_collectible_pricing(gift_set)
    _validate_max_supply(gift_set)
    db.add(gift_set)
```

In `update_gift_set`, right after the existing `_validate_collectible_pricing(gift_set)` line:

```python
    for key, value in updates.items():
        setattr(gift_set, key, value)
    _validate_collectible_pricing(gift_set)
    _validate_max_supply(gift_set)
    db.add(gift_set)
```

- [ ] **Step 6: Run all gift tests to verify they pass**

```bash
cd backend
pytest tests/test_gifts.py -v
```
Expected: PASS — all 17 existing tests plus the 5 new ones from Step 1.

- [ ] **Step 7: Run the full backend suite to check for regressions**

```bash
cd backend
pytest tests/ -v
```
Expected: PASS except the one pre-existing unrelated `test_tasks.py::test_task_reward_pack_grants_all_cards` failure (already confirmed present on `main` before this feature, unrelated to gifts).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/gift_service.py backend/app/services/stars_payment_service.py backend/app/routers/admin_gifts.py backend/tests/test_gifts.py
git commit -m "Add serial number minting, unify collectible/bundle claim rewards, validate max supply"
```

---

### Task 3: Frontend types + admin panel

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/admin/pages/AdminGiftsPage.tsx`

**Interfaces:**
- Consumes: `GiftSet.max_supply`/`next_serial_number`/`collection_id`, `Gift.serial_number` (Task 1-2); `fetchAdminCardCollections()` (existing, `frontend/src/admin/api.ts`), `CardCollection` (existing, `frontend/src/admin/types.ts`).
- Produces: updated `GiftSet`/`Gift` TS interfaces; the admin gift-set form gains max supply, collection tag, and shows the prize fields for both kinds.

- [ ] **Step 1: Update `frontend/src/types/index.ts`**

In the `GiftSet` interface, add three fields right after `coins_price`:

```typescript
  coins_price: number;
  max_supply: number | null;
  next_serial_number: number;
  collection_id: number | null;
  is_active: boolean;
```

(only the three new lines between `coins_price` and `is_active` are additions — both already exist).

In the `Gift` interface, add one field right after `is_pinned`:

```typescript
  is_pinned: boolean;
  serial_number: number | null;
  claimed_at: string | null;
```

- [ ] **Step 2: Update `frontend/src/admin/pages/AdminGiftsPage.tsx`**

Add `fetchAdminCardCollections` to the existing `@/admin/api` import block, and `CardCollection` to the existing `@/types` import:

```typescript
import {
  createGiftSet,
  deleteGiftSet,
  deleteGiftSetImage,
  fetchAdminCardCollections,
  fetchAdminGiftSets,
  fetchAdminPacks,
  updateGiftSet,
  uploadGiftSetImage,
} from "@/admin/api";
```
```typescript
import type { CardCollection, GiftSet } from "@/types";
```

Update `GiftSetForm` and `giftSetToForm`:

```typescript
interface GiftSetForm {
  name: string;
  description: string;
  kind: "bundle" | "collectible";
  pack_id: number | null;
  coins_amount: number;
  stars_price: number;
  coins_price: number;
  max_supply: number;
  collection_id: number | null;
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
    max_supply: g?.max_supply ?? 0,
    collection_id: g?.collection_id ?? null,
    is_active: g?.is_active ?? true,
    sort_order: g?.sort_order ?? 0,
  };
}
```

`max_supply: 0` in the form is a local UI sentinel for "unlimited" (matches this form's own `stars_price`/`coins_price` convention of `0` meaning "not set") — it is converted to `null` at submit time, never sent as `0`.

Fetch collections and convert `max_supply` at submit time — in `AdminGiftsPage`, add the query right after the existing `packs` query:

```typescript
  const { data: packs } = useQuery({ queryKey: ["admin-packs-for-gifts"], queryFn: fetchAdminPacks });
  const { data: collections } = useQuery({ queryKey: ["admin-card-collections-for-gifts"], queryFn: fetchAdminCardCollections });
```

Change `saveMutation` to convert the sentinel:

```typescript
  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = { ...form, max_supply: form.max_supply > 0 ? form.max_supply : null };
      return editing === "new" ? createGiftSet(payload) : updateGiftSet((editing as GiftSet).id, payload);
    },
    onSuccess: () => { invalidate(); setEditing(null); setError(null); },
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось сохранить набор"),
  });
```

In the list row, add a "Тираж" line for collectibles — change the price/status paragraph from:

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
                  {g.kind === "collectible" && (
                    <> · Тираж: {g.next_serial_number - 1}/{g.max_supply ?? "∞"}</>
                  )}
                </p>
```

Move the pack/coins-amount fields out of the `form.kind === "bundle"` guard so they show for both kinds (with kind-appropriate copy), and add the collection/max-supply fields for collectibles — replace:

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

with:

```tsx
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">
                  {form.kind === "bundle" ? "Пак в наборе (необязательно)" : "Пак-приз при получении (необязательно)"}
                </span>
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
                <span className="text-xs text-slate-400">
                  {form.kind === "bundle" ? "Монеты в наборе" : "Монеты-приз при получении"}
                </span>
                <NumberInput min={0} value={form.coins_amount} onChange={(v) => setForm({ ...form, coins_amount: v })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Цена в ⭐ (для покупки игроками)</span>
                <NumberInput min={0} value={form.stars_price} onChange={(v) => setForm({ ...form, stars_price: v })} />
              </label>
              {form.kind === "collectible" && (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Цена в монетах (для покупки игроками)</span>
                    <NumberInput min={0} value={form.coins_price} onChange={(v) => setForm({ ...form, coins_price: v })} />
                    <span className="text-[10px] text-slate-500">Нужна хотя бы одна цена — в ⭐ или в монетах.</span>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Тираж (0 = без ограничения)</span>
                    <NumberInput min={0} value={form.max_supply} onChange={(v) => setForm({ ...form, max_supply: v })} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">Коллекция (необязательно)</span>
                    <select
                      value={form.collection_id ?? ""}
                      onChange={(e) => setForm({ ...form, collection_id: e.target.value ? Number(e.target.value) : null })}
                      className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                    >
                      <option value="">Без коллекции</option>
                      {collections?.map((c: CardCollection) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </label>
                </>
              )}
```

- [ ] **Step 3: Verify**

```bash
cd frontend
npm run typecheck
npm run test -- --run
```
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/admin/pages/AdminGiftsPage.tsx
git commit -m "Add serial number, max supply, and collection tag to the admin gift-set form"
```

---

### Task 4: `GiftsPage.tsx` — remove auto-claim, unify pending list, reveal prizes

**Files:**
- Modify: `frontend/src/pages/GiftsPage.tsx`

**Interfaces:**
- Consumes: `Gift.serial_number`, `GiftSet.max_supply` (Tasks 1-3); existing `claimGift`, `buyCollectibleWithCoins`, `createGiftInvoice`, `fetchGiftInvoiceStatus` (unchanged signatures).

- [ ] **Step 1: Replace the full file**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

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

  if (!user) return null;

  // Both gift kinds now share the same pending -> claim -> reveal lifecycle:
  // a collectible with no configured prize just claims with nothing granted,
  // one with coins/pack configured grants it exactly like a bundle does.
  const collectibles = (myGifts ?? []).filter((g) => g.gift_set.kind === "collectible" && !!g.claimed_at);
  const pendingGifts = (myGifts ?? []).filter((g) => !g.claimed_at);
  const claimedBundles = (myGifts ?? []).filter((g) => g.gift_set.kind === "bundle" && g.claimed_at);
  const isEmpty = collectibles.length === 0 && pendingGifts.length === 0 && claimedBundles.length === 0;

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
          Мои подарки{pendingGifts.length > 0 ? ` (${pendingGifts.length})` : ""}
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
                    {g.serial_number != null && (
                      <span className="font-mono text-[10px] text-ink-mist-dim">№{g.serial_number}</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {pendingGifts.length > 0 && (
              <div className="flex flex-col gap-2">
                {pendingGifts.map((g) => (
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
  const isCollectible = result.gift.gift_set.kind === "collectible";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        {isCollectible ? (
          <div className="flex flex-col items-center gap-1">
            <span className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-2xl bg-rarity-epic/10">
              {result.gift.gift_set.image_path ? (
                <img src={staticUrl(result.gift.gift_set.image_path) ?? undefined} className="h-full w-full object-cover" />
              ) : (
                <IconGift size={32} className="text-rarity-epic" />
              )}
            </span>
            <p className="mt-2 font-display text-base font-bold text-ink-chalk">{result.gift.gift_set.name}</p>
            {result.gift.serial_number != null && (
              <p className="font-mono text-xs text-ink-mist">
                №{result.gift.serial_number}
                {result.gift.gift_set.max_supply ? ` из ${result.gift.gift_set.max_supply}` : ""}
              </p>
            )}
          </div>
        ) : (
          <p className="flex items-center justify-center gap-1.5 text-center font-display text-base font-bold text-ink-chalk">
            <IconGift size={18} className="text-rarity-epic" />
            Подарок открыт!
          </p>
        )}

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
        {gift.serial_number != null && (
          <p className="mt-1 font-mono text-xs text-accent-lime">
            №{gift.serial_number}
            {gift.gift_set.max_supply ? ` из ${gift.gift_set.max_supply}` : ""}
          </p>
        )}
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
                {g.max_supply != null && (
                  <p className="font-mono text-[10px] text-ink-mist-dim">
                    Осталось {Math.max(0, g.max_supply - (g.next_serial_number - 1))} из {g.max_supply}
                  </p>
                )}
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
  const [revealResult, setRevealResult] = useState<GiftClaimResult | null>(null);

  const recipientId = recipientMode === "self" ? user?.id : target?.id;

  // Self-purchases feel instant: claim (and thus grant any configured
  // prize) immediately after the purchase call succeeds, then show the same
  // reveal modal a "received" gift shows after tapping "Открыть" — no
  // separate trip to the pending list. Friend purchases keep the plain
  // "sent" confirmation; the prize belongs to the recipient, who gets their
  // own reveal when they claim it later.
  const revealIfSelf = async (giftId: number) => {
    const claimResult = await claimGift(giftId);
    updateBalance(claimResult.new_balance);
    hapticNotify("success");
    queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
    setRevealResult(claimResult);
  };

  const handleBuyWithCoins = async () => {
    if (!recipientId) return;
    setError(null);
    setBusy(true);
    try {
      const result = await buyCollectibleWithCoins(giftSet.id, recipientId, message || undefined);
      updateBalance(result.new_balance);
      queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
      if (recipientMode === "self") {
        await revealIfSelf(result.gift.id);
      } else {
        hapticNotify("success");
        setSuccess(true);
      }
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
          queryClient.invalidateQueries({ queryKey: ["gifts", "mine"] });
          if (recipientMode === "self" && status.gift_result) {
            await revealIfSelf(status.gift_result.id);
          } else {
            hapticNotify("success");
            setSuccess(true);
          }
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

  if (revealResult) {
    return <GiftClaimResultModal result={revealResult} onClose={onDone} />;
  }

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
git commit -m "Remove silent auto-claim, unify pending gifts, reveal prizes and serial numbers"
```

---

### Task 5: End-to-end manual verification

**Files:** none (verification only).

- [ ] **Step 1: Start the environment**

```bash
docker compose up -d --build backend frontend
docker compose exec backend alembic upgrade head
```
Expected: containers healthy, migration `0053` applies cleanly against real Postgres.

- [ ] **Step 2: Admin — configure a numbered, prize-bearing collectible**

Create a new collectible gift set (or edit the existing one from the prior feature) with: a `Тираж` of e.g. `3`, a `Коллекция` selected from the dropdown, a coins-prize (`Монеты-приз`) amount, and confirm the list row shows "Тираж: 0/3". Confirm setting `max_supply` below the already-issued count (after issuing a couple below) is rejected.

- [ ] **Step 3: Self-purchase reveal**

As a player, buy the collectible for yourself with coins. Confirm: balance drops by the coin price, a reveal screen appears immediately (no extra tap) showing the collectible art, "№1 из 3", and the configured coins prize credited — confirm balance reflects BOTH the debit and the prize credit. Confirm the item now appears in "Мои подарки" already claimed (no separate "Открыть" needed).

- [ ] **Step 4: Received-gift claim reveal**

Have an admin send the same collectible to a second test account (or buy one for a friend). Confirm it appears in that account's "Мои подарки" as a pending item (NOT silently auto-claimed) with "Открыть" — tap it, confirm the reveal modal shows the art, serial number, and prize, and the item moves into the always-visible grid afterward.

- [ ] **Step 5: Sold out**

Exhaust the remaining supply (2 more purchases/sends against the tirage of 3), then confirm a further purchase attempt is rejected with a clear "тираж распродан"-style error and the buyer isn't charged.

- [ ] **Step 6: Confirm bundle gifts are untouched**

Buy or receive one of the existing bundle gift sets — confirm the flow (pending → "Открыть" → History) is unchanged from before this feature.

- [ ] **Step 7: Regression pass**

```bash
cd backend && pytest tests/ -v
cd frontend && npm run typecheck && npm run test -- --run && npm run build
```
Expected: all green except the one pre-existing unrelated `test_tasks.py` failure.
