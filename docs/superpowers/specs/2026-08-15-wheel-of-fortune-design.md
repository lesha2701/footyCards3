# Wheel of Fortune (Колесо фортуны)

## Goal

A new daily engagement mechanic: a prize reel players spin for a chance at
coins, packs, rare/epic/legendary cards, or exclusive profile badges. Free
spins are limited per day; extra spins can be bought with coins or Telegram
Stars. Prize odds are entirely admin-configurable via weighted entries in
the admin panel, so the operator can rebalance the economy without a
deploy.

Presented as a "барабан" (reel), not a circular wheel — a single row of
prize icons where the center one is highlighted/enlarged, matching the
"large carousel" mockup approved during design (fewer icons visible at
once, center one scaled up and outlined, real app icon geometry — no
emoji).

## Placement

A `NoticeCard`-style entry on `HomePage.tsx` (same pattern as the existing
referral/daily-reward/free-pack notices), linking to a new dedicated route
`/wheel`. The reel animation needs real screen space, so it does not fit
as an inline home-page widget — the card is a teaser/entry point only.

## Economy & limits

**Free spins**: `GameConfig.wheel_free_spins_per_day: int` (default 2).
Tracked on `User` with the same calendar-day-reset pattern already used
for mini-game daily caps (e.g. `hangman_rewarded_attempts_today` /
`hangman_attempts_reset_at`, reset via `local_today()` comparison — see
`hangman_service.py` and `game_config_service.py`):

```python
# User model additions
wheel_free_spins_used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
wheel_spins_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Paid spins**: no daily cap — as many as the player can afford. Two
payment paths, both amounts admin-configurable on `GameConfig`:

```python
wheel_spin_cost_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
wheel_spin_cost_stars: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
```

- **Coins path**: synchronous — debit `wheel_spin_cost_coins`
  (`debit_coins`, new `TransactionType.wheel_spin_cost`) and resolve the
  spin in the same request, mirroring how coin-priced packs are bought.
- **Stars path**: asynchronous, reusing the existing Telegram Stars invoice
  flow used for packs/gifts/coin top-ups (`StarsInvoice` +
  `stars_payment_service.py` + the bot's `pre_checkout_query` /
  `successful_payment` relay). Add a new nullable marker column,
  `StarsInvoice.is_wheel_spin: Mapped[bool] = mapped_column(Boolean, default=False)`,
  alongside the existing `pack_id` / `gift_set_id` / `coins_amount`
  discriminators. The spin is rolled at **delivery** time
  (`deliver_payment`), not at invoice-creation time — same principle as a
  Stars pack only rolling its cards on delivery, so nothing is decided
  before payment actually clears.

## Prize pool

New table, admin-managed, weighted random selection (plain integer
weights, not normalized probabilities — simpler for an admin adding/
removing entries without needing to rebalance everything else to sum to
1):

```python
class WheelPrizeType(str, enum.Enum):
    coins = "coins"
    pack = "pack"
    card_rarity = "card_rarity"
    badge = "badge"

class WheelPrize(TimestampMixin, Base):
    __tablename__ = "wheel_prizes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prize_type: Mapped[WheelPrizeType] = mapped_column(Enum(WheelPrizeType, name="wheel_prize_type_enum"), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)  # relative, need not sum to any total
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # exactly one of the below is set, matching prize_type
    coins_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="CASCADE"), nullable=True)
    card_rarity: Mapped[Optional[Rarity]] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=True)
    badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), nullable=True)

    pack: Mapped[Optional["Pack"]] = relationship(lazy="joined")
    badge: Mapped[Optional["Badge"]] = relationship(lazy="joined")
```

- **coins**: `coins_amount` credited (`TransactionType.wheel_spin_reward`).
- **pack**: opens `pack_id` for free (reuses `roll_and_create_cards`, like
  `free_pack_service._grant_free_pack`) — admin picks which existing packs
  are eligible (nothing enforces "no higher than elite" in code; that's a
  content decision made by which packs the admin adds as prizes). A pack
  prize can roll cards the player already owns — this is already normal,
  existing pack-opening behavior (duplicate-count/coin-value handling
  lives in `pack_service`/`collection_service` today); nothing
  wheel-specific is needed here.
- **card_rarity**: grants one random card of that rarity directly
  (`pick_random_player(db, rarity)` + `create_user_card(..., source=CardSource.wheel)`),
  no `Pack`/`PackOpening` wrapper needed. Rare / epic / legendary are three
  separate `WheelPrize` rows, each independently weighted — the "more
  cheap prizes, fewer expensive ones" balance is just admin-set weights
  (e.g. coins=50, common pack=20, rare card=10, epic card=3,
  legendary card=1), not a schema concept.
- **badge**: grants `badge_id` via `UserBadge` (same table Stars-pack
  badges use — `uq_user_badge` prevents a duplicate row). If the player
  already owns this badge, credit `GameConfig.wheel_duplicate_badge_coins`
  coins instead (new admin-configurable field, default 200 — same order of
  magnitude as `GameConfig.referral_referred_reward`) —
  mirrors how duplicate cards already degrade to a coin value elsewhere in
  this codebase rather than being silently wasted. Badges used here are
  ordinary `Badge` rows; nothing in the schema separates "wheel badges"
  from "pack badges" — that's purely which rows the admin chooses to
  reference from `WheelPrize`, exactly like packs above.

New enum members needed:

- `CardSource.wheel = "wheel"`
- `TransactionType.wheel_spin_cost = "wheel_spin_cost"` (coin-path debit)
- `TransactionType.wheel_spin_reward = "wheel_spin_reward"` (coin prize credit)

## Spin flow (backend)

New `wheel_service.py`:

- `get_status(db, user) -> WheelStatusOut`: free spins remaining today,
  next free-spin reset time, coin/Stars cost for a paid spin.
- `spin_free(db, user) -> WheelSpinResult`: checks
  `wheel_free_spins_used_today < GameConfig.wheel_free_spins_per_day`
  (reset first if `local_today(wheel_spins_reset_at) != today`), locks the
  user row (`lock_user_for_update`, matching the existing race-safe
  pattern), increments the counter, rolls a prize, grants it, commits.
- `spin_paid_coins(db, user) -> WheelSpinResult`: locks user, checks
  balance, debits `wheel_spin_cost_coins`, rolls, grants, commits.
- `create_spin_invoice(db, user) -> StarsInvoiceCreateOut`: mirrors
  `stars_payment_service.create_invoice`, `is_wheel_spin=True`.
- `_roll_prize(db) -> WheelPrize`: fetch active prizes, weighted-random
  pick (`random.choices(prizes, weights=[p.weight for p in prizes])`),
  same idea as `roll_rarities` already does for pack contents.
- `_grant_prize(db, user, prize) -> WheelSpinResult`: dispatches on
  `prize.prize_type` to the granting logic described above.

All three spin paths funnel into the same `_roll_prize` /
`_grant_prize`, so the odds and granting logic exist in exactly one place
regardless of how the spin was paid for.

## Frontend

- `HomePage.tsx`: new `NoticeCard` — "Колесо фортуны" / "Осталось N
  бесплатных прокруток сегодня" (or "Все прокрутки использованы, крутить
  за монеты/Stars" once free ones are spent) → navigates to `/wheel`.
- New `WheelPage.tsx`:
  - Fetches prize pool + status (`GET /wheel/status`, returns remaining
    free spins, costs, and the full active prize list so the reel can
    render all possible stops, not just the winning one).
  - Reel: a horizontally laid-out row of prize chips (icon + label per
    the app's existing icon set — `IconCoin`, `IconPack`, `IconCard`, and
    the specific `Badge.icon`/`image_path` for badge prizes), the center
    one enlarged and outlined, matching the approved mockup. Framer Motion
    drives the spin: animate a horizontal offset through several loops of
    the prize strip before easing to a stop on the won prize's position
    (same "roll fast then decelerate onto the result" idea already used
    for the existing pack-opening reveal, adapted to a strip instead of a
    card stack).
  - Two spin buttons: "Крутить бесплатно (N/2)" (disabled once exhausted)
    and "Крутить за {cost}" with a coin/Stars sub-choice when both are
    available.
  - Reuses the pack-open-style result reveal (or the existing
    `RewardClaimedModal` pattern from Tasks) to show what was won.

## Admin panel

New `AdminWheelPage.tsx`, modeled directly on the existing
`AdminTasksPage.tsx` (list + create/edit form) and `AdminGiftsPage.tsx`
(active/sort_order toggles) patterns:

- CRUD list of `WheelPrize` rows: type selector (coins / pack / card
  rarity / badge) that reveals the matching field (amount / pack picker /
  rarity picker / badge picker), weight, active toggle, sort order.
- A small settings panel (extending wherever `GameConfig` is already
  edited, e.g. alongside `AdminGamesPage.tsx`'s existing per-game
  settings) for `wheel_free_spins_per_day`, `wheel_spin_cost_coins`,
  `wheel_spin_cost_stars`.

## Testing

- Backend: `pytest` coverage for `wheel_service.py` — free-spin daily
  reset/exhaustion, paid-coin spin balance checks, weighted roll
  distribution (statistical, over many rolls, matching the style of
  existing `roll_rarities` tests), each prize type's granting logic,
  Stars invoice creation + delivery (mirroring existing
  `test_stars_payments.py`-style coverage), and concurrent-spin race
  safety (row lock).
- Frontend: `npm run typecheck` or a smoke test of the reel reaching a
  stopped state; manual verification of the spin animation and both
  payment paths against the real dev bot (Stars payments cannot be
  meaningfully unit-tested against Telegram itself).

## Out of scope

- No changes to the existing pack/gift/badge purchase flows beyond adding
  the new `WheelPrize`/`StarsInvoice.is_wheel_spin` references.
- No leaderboard, streak bonus, or "pity timer" (guaranteed rare prize
  after N spins) mechanics — plain weighted-random every time, exactly as
  requested.
- No non-Telegram-Stars real-money payment path.
