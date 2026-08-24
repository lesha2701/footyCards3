# Collectible Gift Editions — Design Spec

## Goal

Four additions to the collectible-gift system shipped earlier: per-design serial numbers (with an optional capped supply), tagging a collectible with an existing `CardCollection`, a configurable purchase prize (coins/pack), and a reveal moment for that prize. Point 4 of the original request ("pinned gifts always visible in profile") is already satisfied by the existing `ProfilePage.tsx` block — verified, no change needed there.

The prize requirement forces a UX reversal: collectibles can no longer auto-claim silently in the background (what was shipped last time), because a real prize now needs a moment where the player sees what they got. This spec restores the manual "Открыть" claim step for collectibles received from someone else, while self-purchases get an immediate reveal driven by the purchase flow itself.

## Data model

```python
# app/models/gift.py — GiftSet, new columns (after coins_price)
max_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)       # null = unlimited
next_serial_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
collection_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True
)
```

```python
# app/models/gift.py — Gift, new column (after pinned_at)
serial_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # null for bundle-kind gifts
```

- `max_supply`/`next_serial_number`/`collection_id` are meaningful only for `kind=collectible`; bundles never get numbered (`Gift.serial_number` stays `null`) and `collection_id` is simply unused for bundles (not validated either way — harmless if set).
- `collection_id` is purely descriptive — it does **not** feed into `UserCollectionReward`'s completion-tracking logic. No relationship attribute is added to avoid an import between `models/gift.py` and `models/card_collection.py`; the schema layer exposes the bare id.
- `coins_amount`/`pack_id` (existing columns) are reused as the configurable purchase prize for **both** kinds — previously bundle-only, now applies to collectibles too. No new columns needed for this part.

## Migration

One new Alembic revision (`0053_gift_editions.py`): adds the four columns above with matching server defaults (`next_serial_number` defaults to `1`).

## Serial number minting — one shared, row-locked helper

```python
# app/services/gift_service.py
async def reserve_gift_serial_numbers(db: AsyncSession, gift_set: GiftSet, count: int = 1) -> Optional[int]:
    """Atomically reserves `count` consecutive serial numbers on a collectible
    gift_set and returns the first one — None for a bundle (never numbered).
    Row-locks gift_set so concurrent mints (two purchases, or a purchase
    racing a broadcast) can't hand out the same number. Enforces max_supply;
    raises rather than partially fulfilling an over-capacity request."""
```

Called by every Gift-creation path, in this lock order (buyer/User row first where one is involved, then GiftSet — the only order used anywhere in this codebase for these two tables, so no deadlock risk):

- `buy_collectible_with_coins`: mint **before** `debit_coins`, so a sold-out edition never charges the buyer.
- `stars_payment_service.deliver_payment`'s gift branch: mint before constructing the `Gift` row. `create_gift_invoice` also gets a non-authoritative early check (reject obviously-sold-out purchases before generating a real Telegram invoice) — the row-locked mint at delivery remains the actual enforcement.
- `admin_send_gift_to_user`: mint (count=1) before constructing the `Gift` row.
- `admin_broadcast_gift`: mint a block (`count=len(user_ids)`) once, then assign `start + i` to each row in the existing bulk-insert list comprehension. If supply can't cover every recipient, the whole broadcast is rejected up front (`ConflictError`) rather than partially fulfilled.

## Claim semantics — unify instead of special-casing

The previous `claim_gift` had an early-return branch for `kind=collectible` that granted nothing. That branch is deleted. Every gift, either kind, now falls through the same logic: roll `gift_set.pack_id` if set, credit `gift_set.coins_amount` if set, stamp `claimed_at`. For a collectible with no configured prize (the common case, `coins_amount=0`, `pack_id=None`), this is behaviorally identical to before — grants nothing, just claims. For one with a prize configured, it now grants it, identically to how bundles already work. `GiftOut.serial_number` rides along in the response automatically since it's just a column on the row.

This means **the frontend's silent background auto-claim effect is removed**. Collectible gifts now behave exactly like bundles in the pending/claim lifecycle:
- Unclaimed (received from someone else — friend purchase, admin send/broadcast) → sits in a pending list, "Открыть" tap → `claim_gift` → reveal modal (now showing the collectible's art + serial number alongside any coins/pack won) → moves into the always-visible "Мои подарки" grid.
- **Self-purchase** (buy for yourself, either currency) is the one path that still feels instant: right after the purchase call succeeds, the frontend immediately calls `claimGift` on the resulting gift id and shows the same reveal modal — no separate trip to a pending list. This is two API calls instead of baking self-vs-friend branching into the purchase service functions, deliberately: `claim_gift` stays the single source of truth for "what does opening this gift grant," reused by every path instead of duplicated.
- Friend-purchase still shows today's plain "Подарок отправлен!" confirmation to the *buyer* — the prize belongs to the recipient, who gets their own reveal when they claim it.

## Admin panel

- `GiftSetForm` gains `max_supply: number | null` (empty input = unlimited) and `collection_id: number | null` (dropdown, reusing the existing `fetchAdminCardCollections()`), both shown only when `kind === "collectible"`.
- The `pack_id`/`coins_amount` fields move out of the `kind === "bundle"` guard — shown for both kinds now, with kind-appropriate helper copy ("приз" framing for collectibles vs. today's "в наборе" framing for bundles).
- `_validate_max_supply` (new, mirrors the existing `_validate_collectible_pricing`): rejects lowering `max_supply` below `next_serial_number - 1` (can't cap below what's already issued).
- List rows show "Тираж: X/Y" (X = `next_serial_number - 1`, Y = `max_supply` or "∞") for collectibles.

## Frontend display

- Collection grid cards and the detail sheet show "№23" (or "№23 из 5000" when `max_supply` is set).
- `GiftClaimResultModal` extended: when `result.gift.gift_set.kind === "collectible"`, shows the collectible's image and serial number above the existing coins/cards-won display (which needs no change — it already renders `coins_credited`/`pack_result` generically).

## Testing

Extend `backend/tests/test_gifts.py`:
- Two concurrent-ish purchases of the same limited collectible get distinct, sequential serial numbers (sequential calls are enough to prove the counter advances correctly; true concurrency isn't exercised by the SQLite test DB, consistent with this codebase's existing row-locking test conventions).
- Purchasing past `max_supply` is rejected (`ConflictError`) and does not charge the buyer.
- A collectible with `coins_amount`/`pack_id` configured now grants them on claim (self-purchase path and received-from-admin path both covered).
- `admin_broadcast_gift` on a collectible with insufficient remaining supply for all registered users is rejected outright, and issues no partial gifts.
- `_validate_max_supply` rejects shrinking below the issued count.
- `GiftOut.serial_number` round-trips correctly through `list_my_gifts`.
