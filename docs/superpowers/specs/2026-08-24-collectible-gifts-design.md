# Collectible Gifts ("Подарки" v2) — Design Spec

## Goal

Add a second, "Telegram-style" gift type — a purely cosmetic image/gif collectible, bought with Stars or coins, for yourself or a friend — alongside the existing gift-set (pack + coins bundle, Stars-only) system, without building a parallel data model or purchase pipeline. The existing gift system already covers 80% of the mechanics this needs (Stars invoice + polling, admin send-to-user/broadcast, buy-for-a-friend, recipient search) — this spec extends `GiftSet`/`Gift` with a `kind` discriminator instead of introducing new tables.

Also relocates and reshapes the Profile page's "Подарки" entry point: it moves up to sit directly under "Трофеи" and becomes a live block showing up to 3 pinned collectibles, instead of a bare button near the bottom of the page.

## Data model

### `GiftSet` — extend with a kind discriminator

```python
class GiftKind(str, enum.Enum):   # app/models/enums.py
    bundle = "bundle"             # today's pack + coins Stars bundle
    collectible = "collectible"   # new: cosmetic image/gif, Stars and/or coins
```

```python
# app/models/gift.py — GiftSet, new columns
kind: Mapped[GiftKind] = mapped_column(Enum(GiftKind), default=GiftKind.bundle, nullable=False)
coins_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # collectible-only
```

- `pack_id` / `coins_amount` keep their existing meaning ("reward granted on claim") and are only ever set for `kind=bundle`.
- `stars_price` is reused for both kinds (bundle: the existing Stars-only price; collectible: one of up to two purchase currencies).
- `coins_price` is new, nullable, collectible-only. A collectible must have at least one of `stars_price > 0` / `coins_price > 0`. Not DB-enforced (same convention as `Pack`'s coins/stars pricing) — validated in the admin schema/service.
- `image_path` is reused as-is; the upload endpoint starts accepting `.gif` (see "Image upload" below) so collectibles can be animated.
- Existing rows get `kind=bundle` via the migration's server default — no backfill needed, no behavior change for today's gift sets.

### `Gift` — extend with pinning

```python
# app/models/gift.py — Gift, new columns
is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- `pinned_at` orders the pinned set (most-recently-pinned first) and doubles as the "when was this pinned" audit trail; both columns are only ever set for `kind=collectible` gifts the recipient owns.
- No new uniqueness constraint — a player can own duplicate copies of the same collectible design (confirmed).

### Migration

One new Alembic revision, `NNNN_gift_kind_and_pinning.py`: adds `gift_sets.kind` (enum, default `bundle`, not null), `gift_sets.coins_price` (nullable int), `gifts.is_pinned` (bool, default false), `gifts.pinned_at` (nullable timestamp).

### New `TransactionType`

`gift_purchase_coins` — the ledger entry when a player debits coins to buy a collectible for themself or a friend (mirrors `pack_purchase`).

## Claim semantics — reuse the existing pending → claim pipeline

No new claim pipeline. `Gift` rows for both kinds are created the same way they are today (unclaimed, `claimed_at=None`) by every existing creation path (Stars delivery, admin send, admin broadcast, and the new coin-purchase path below) — this is what lets admin send/broadcast work on collectibles with **zero code changes**.

`gift_service.claim_gift` branches on `gift.gift_set.kind`:
- `bundle` (unchanged): rolls the pack / credits `coins_amount`, sets `claimed_at`.
- `collectible` (new branch): sets `claimed_at = now()` only — nothing to grant, the row's existence *is* the reward.

The frontend never shows a "claim" affordance for collectibles. Instead, right after `GET /gifts/mine` resolves, it fires `POST /gifts/{id}/claim` in the background for every unclaimed collectible-kind gift in the response (fire-and-forget, `Promise.allSettled`, silent — a failed claim there just means the item still shows as unclaimed next fetch, no user-facing error needed). This means a gifted collectible appears already "in the collection" the moment the recipient opens the app, matching Telegram's own gift UX, while `claimed_at` still exists as the correct signal for "has this row been fully processed" everywhere else in the codebase that touches `Gift`.

Grouping for display (client-side, from the one `GET /gifts/mine` response — no new list endpoint):
- `kind === "bundle" && !claimed_at` → pending list, "Открыть" tap-to-claim (unchanged today).
- `kind === "bundle" && claimed_at` → collapsed "История" (unchanged today).
- `kind === "collectible"` → main "Мои подарки" grid, regardless of `claimed_at` (which will always end up set almost immediately via the auto-claim above).

## Backend changes

### `stars_payment_service.create_gift_invoice`

The existing guard:
```python
if recipient.id == user.id:
    raise ConflictError("You can't send a gift to yourself")
```
becomes conditional on kind:
```python
if recipient.id == user.id and gift_set.kind == GiftKind.bundle:
    raise ConflictError("You can't send a gift to yourself")
```
Collectibles may be self-purchased; bundles keep today's restriction unchanged.

### New: `gift_service.buy_collectible_with_coins`

```python
async def buy_collectible_with_coins(
    db: AsyncSession, buyer: User, gift_set_id: int, recipient_id: int, message: Optional[str],
) -> GiftOut:
```
- Loads the `GiftSet`, 404s if missing, `ConflictError`s if `not is_active`, `kind != collectible`, or `coins_price` is `None`/`<= 0`.
- Loads the recipient (404 if missing) — self-purchase is allowed here (`recipient_id == buyer.id` is fine).
- `wallet_service.lock_user_for_update(db, buyer.id)` then `debit_coins(db, buyer, gift_set.coins_price, TransactionType.gift_purchase_coins, f"Подарок «{gift_set.name}»", related_object_type="gift_set", related_object_id=gift_set.id)` — raises `InsufficientBalanceError` automatically if short, same pattern as every other coin spend in the codebase.
- Creates the `Gift` row (`sender_id=buyer.id`, `recipient_id=recipient_id`, `is_admin_gift=False`, `message=message`), commits, returns a new `GiftPurchaseResult` schema.

```python
class GiftPurchaseResult(BaseModel):
    gift: GiftOut
    new_balance: int
```

New router: `POST /gifts/collectibles/{gift_set_id}/buy-with-coins`, body `{recipient_id: int, message?: str}` → `GiftPurchaseResult`, so the frontend can update the balance store without a refetch (mirrors `PackOpenResult.new_balance`).

### New: `PATCH /gifts/{gift_id}/pin`

Body `{pinned: bool}`. Loads the `Gift`, 404s unless `recipient_id == current_user.id`, `ConflictError`s if `gift_set.kind != collectible` or `claimed_at is None` (must be owned first — in practice always true by the time the frontend lets you tap pin, since the auto-claim above runs first). Pinning: if already 3 gifts pinned for this user, `ConflictError` ("Сначала открепи один из подарков") — no auto-eviction, matches the "manual pin/unpin" answer. Unpinning always succeeds. Sets/clears `is_pinned` + `pinned_at`.

### Admin (`admin_gifts.py`, `schemas/gift.py`) — no new endpoints, extended payloads

- `GiftSetCreate`/`GiftSetUpdate`/`GiftSetOut` gain `kind: GiftKind` and `coins_price: Optional[int]`.
- `create_gift_set`/`update_gift_set` — no service-level change needed beyond the schema growing (same `GiftSet(**payload.model_dump())` / `setattr` loop already handles new fields generically).
- `admin_send_gift_to_user` / `admin_broadcast_gift` — **unchanged**, already take a bare `gift_set_id` and don't care about kind.

### Image upload

`image_service.py`'s shared `ALLOWED_EXTENSIONS`/`ALLOWED_CONTENT_TYPES` (used by every `save_*_image` function, including `save_gift_set_image`) gain `"gif"` / `"image/gif"`. This is a one-line change to a shared allowlist rather than a gift-specific code path — harmless for the other upload endpoints, and avoids forking `save_gift_set_image` into its own validation logic.

## API surface summary

| Endpoint | Change |
|---|---|
| `GET /gifts/sets` | unchanged shape, `GiftSetOut` now includes `kind`/`coins_price` |
| `GET /gifts/mine` | unchanged — frontend groups client-side by `kind` |
| `POST /gifts/invoice` | unchanged request/response; self-gift guard now kind-conditional |
| `POST /gifts/{id}/claim` | unchanged signature; branches on kind internally |
| `POST /gifts/collectibles/{gift_set_id}/buy-with-coins` | **new** |
| `PATCH /gifts/{id}/pin` | **new** |
| `/admin/gifts/sets*` | unchanged shape, payloads gain `kind`/`coins_price` |
| `/admin/gifts/send`, `/admin/gifts/broadcast` | unchanged |

## Frontend

### Profile page (`ProfilePage.tsx`)

The current bottom-of-page "Подарки" section (a lone button navigating to `/gifts`) is removed from its current position and replaced by a new block inserted immediately after the "Трофеи" `section` (both live under the "achievements" umbrella visually). The block:
- Header "🎁 Подарки" (reuse `IconGift`), tappable, navigates to `/gifts`.
- Row of up to 3 pinned collectibles (thumbnail + name), sourced from a lightweight new query (`GET /gifts/mine`, filtered client-side to `is_pinned` — no new endpoint needed since the full list is already small per user).
- If the player has zero pinned collectibles (whether because they own none, or own some but haven't pinned any), the block shows a muted placeholder ("Закрепи любимые подарки" / a plain gift icon) rather than being hidden — it should always be visible under Трофеи as a discoverable entry point, unlike the trophies section which today only renders `{!!trophies?.length && ...}`.

### `/gifts` page (`GiftsPage.tsx`) — reshaped into two tabs

Replaces the current `tab: "mine" | "send"` with `tab: "mine" | "shop"`:

- **Мои подарки** (`mine`, default):
  - Empty state exactly as requested: if the player owns zero collectibles *and* has zero bundle gifts (pending or claimed), show `EmptyState` "Подарков пока нет" with a "Магазин подарков" button above it (switches to the `shop` tab) — this replaces today's `EmptyState` copy ("Пока нет подарков") for the fully-empty case.
  - Otherwise: collectible grid at the top (tap a card → detail sheet with pin/unpin toggle, sender, message, received date), then the existing pending-bundle list ("Открыть" button, unchanged), then the existing collapsed "История" for claimed bundles (unchanged).
  - On mount / whenever `fetchMyGifts` resolves, fire the background auto-claim pass described above for unclaimed collectibles.
- **Магазин подарков** (`shop`): two sections, stacked (not nested tabs, to keep one tap-depth):
  - "Наборы" — today's `SendGiftTab` body, unchanged (grid of `GiftSet` cards filtered to `kind=bundle`, `RecipientPicker`, message, Stars-only checkout).
  - "Коллекционные" — new grid of `kind=collectible` gift sets. Selecting one opens a picker reusing `RecipientPicker` (defaulting to "себе" as a distinct first option, not just an empty search — self-purchase is the common case here), the optional message field, and — when a set has both `stars_price` and `coins_price` — a two-button currency toggle before the confirm button, whose label always shows the chosen amount (`Отправить за N ⭐` / `Отправить за N 🪙`). Stars path reuses the existing invoice-create → `openTelegramInvoice` → poll flow (already kind-agnostic per the backend change above); coins path calls the new `buy-with-coins` endpoint directly (no invoice/poll needed) and updates the balance store from the response.

### Admin (`AdminGiftsPage.tsx`)

- Form gains a `kind` selector (segmented control: "Набор" / "Коллекционный") at the top, defaulting to "Набор" for parity with today.
- When `kind=collectible`: hide "Пак в наборе" and "Монеты в наборе" (not applicable), show a new "Цена в монетах" `NumberInput` alongside the existing "Цена в ⭐" one; helper copy clarifies at least one of the two prices is required.
- When `kind=bundle`: unchanged form (today's fields), `coins_price` stays hidden/unset.
- File input's `accept` attribute grows to include `image/gif`.
- List rows show the kind (small tag/badge) so admins can tell bundles and collectibles apart at a glance.

## Testing

Extend `backend/tests/test_gifts.py`:
- Buying a collectible with coins: success (balance debited, `Gift` row created, `claimed_at=None`), insufficient balance (`InsufficientBalanceError`), wrong kind (`ConflictError` when target is a bundle), self-purchase allowed.
- `create_gift_invoice` self-gift guard: still blocked for `kind=bundle`, allowed for `kind=collectible`.
- `claim_gift` on a collectible: sets `claimed_at`, grants no pack/coins, balance unchanged.
- Pin/unpin: pinning a 4th when 3 already pinned raises `ConflictError`; pinning someone else's gift or a bundle/unclaimed gift raises `ConflictError`/`NotFoundError`; unpin always succeeds.
- Admin broadcast/send with a `kind=collectible` gift_set_id: existing tests already cover the generic path — add one case confirming it works unchanged for collectibles.

Frontend: manual verification in the running `docker compose` stack (profile block, empty state, shop → both sections → both currencies, pin/unpin from the detail sheet, admin CRUD with an uploaded gif) — no existing Vitest coverage for `GiftsPage`/`ProfilePage` to extend within this task's scope.
