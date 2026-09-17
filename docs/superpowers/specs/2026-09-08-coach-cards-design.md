# Coach Cards — Design

> **For agentic workers:** this spec is the authority for the implementation
> plan(s) that follow. Where the plan and this spec disagree, this spec wins.

## 1. Overview and goals

Today every collectible card is a `Player`: a position, a rating, a rarity,
nothing else. This spec adds a second, structurally different card
archetype — **Coach** — that has no position and does not represent a
squad slot. A coach is instead *equipped* (one at a time) and passively
grants 1-3 fixed boosts that strengthen a squad's attack, defense, or
passing, scaled by rarity.

Coaches exist in **two independent economies**, confirmed by the product
owner and mirroring how `Player` already has two independent ownership
paths (`UserCard` vs `ClubCard`):

- **Club coaches** — owned by a club (not any one member), acquired only
  through a new club-budget-funded pack, assignable by the captain/
  assistants, and active on every club tournament match.
- **Personal coaches** — owned by an individual player, acquired through a
  new personal pack, and active in Card Arena (`match_service.py`'s
  personal match engine). **Not** wired into Tactico — explicitly excluded
  for this iteration (product owner's instruction).

**Goal:** ship a genuinely new collectible category (its own rarity tiers,
its own packs, its own "which one is equipped" UI) whose gameplay effect is
real but bounded — a coach should meaningfully shift a close match, never
let a weak squad's coach substitute for a strong squad's cards, and (per
explicit instruction) should matter *more* in tournaments, where the
match engine already has a rich zone/mentality/playstyle system to hook
into, than in Card Arena, whose engine is flatter and only exposes a
handful of numeric levers.

**Explicitly out of scope for this iteration:**
- Tactico (`Tactico`/`TacticoMatch`) — no coach hook there at all.
- Diamond-rarity coaches — coaches stop at `legendary`; `diamond` stays a
  player-only rarity tier for now.
- Trading coach cards through the existing player-exchange system — real
  scope of its own (the exchange system's models/schemas are keyed to
  `UserCard`), deferred to a later iteration. Coaches are ownable and
  quick-sellable, but not tradeable, in this iteration.
- Any admin-tunable boost magnitude via `GameConfig` — boost magnitudes are
  plain module constants (see §7), matching how this codebase already
  treats "spec-shaped" balance numbers (rarity bonus, mentality shifts,
  zone weights) as code, not admin config.

## 2. Why Coach can't reuse the Player model

Confirmed by direct inspection (`backend/app/models/player.py`,
`backend/app/models/card.py`): `Player` carries a `position` column
(`Position` enum) that `ZONE_WEIGHTS`/`CATEGORY_POSITIONS`/formation-slot
fit logic all key off, and `UserCard` carries `diamond_rating_bonus` plus
`is_in_lineup`/`is_in_tactico_squad` lock flags tied to the diamond-upgrade
and squad-slot systems. A coach has no position and must never be
diamond-upgradeable or slot-lockable the way a player card is. Reusing
`Player`+`UserCard` with a sentinel position would (a) pollute every
position-fit code path with a "this isn't really a position" special case,
and (b) accidentally make coaches diamond-upgradeable unless every one of
those call sites was separately guarded. A parallel model pair, sharing
only the `Rarity` enum, is the clean boundary — exactly how `ClubCard`
already stays clean of `UserCard`'s diamond/lock concerns by being its own
table (confirmed: `ClubCard` has no `diamond_rating_bonus`/lock columns at
all; `lineup_service.calculate_base_strength` reads it via
`getattr(card, "diamond_rating_bonus", 0)` specifically to stay correct for
both — see `lineup_service.py:102-107`).

## 3. Data model

New enum, alongside `Rarity`/`Position` in `backend/app/models/enums.py`:

```python
class CoachBoostType(str, enum.Enum):
    ATTACK_CENTRAL = "attack_central"
    ATTACK_WING = "attack_wing"
    MIDFIELD_CONTROL = "midfield_control"
    DEFENCE_CENTRAL = "defence_central"
    DEFENCE_WING = "defence_wing"
    GOALKEEPING = "goalkeeping"
    PASSING_ACCURACY = "passing_accuracy"
    BALL_CONTROL = "ball_control"
    DEFENSIVE_DISCIPLINE = "defensive_discipline"
    COUNTER_MASTERY = "counter_mastery"
    SQUAD_STABILITY = "squad_stability"
```

New tables (new files, mirroring the existing `player.py` / `card.py` /
`club_card.py` split — one concern per file):

**`backend/app/models/coach.py`** — the coach *template* (admin-authored,
exactly like `Player`) plus its fixed boosts:

```python
class Coach(TimestampMixin, Base):
    __tablename__ = "coaches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False, index=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_sell_price: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_pack_droppable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_club_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    boosts: Mapped[list["CoachBoost"]] = relationship(back_populates="coach", cascade="all, delete-orphan")

    # CHECK constraint (rarity != 'diamond') added in the migration — Coach
    # rarity is capped at legendary per §1; enforced at the DB level, not
    # only in the admin form, so a future pack-roll bug can't create one.


class CoachBoost(Base):
    __tablename__ = "coach_boosts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id", ondelete="CASCADE"), nullable=False, index=True)
    boost_type: Mapped[CoachBoostType] = mapped_column(Enum(CoachBoostType, name="coach_boost_type_enum"), nullable=False)
    magnitude: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    coach: Mapped["Coach"] = relationship(back_populates="boosts")

    __table_args__ = (UniqueConstraint("coach_id", "boost_type", name="uq_coach_boost_type_once"),)
    # "Once per type" also enforces "no duplicate boost on one coach" per §1.
```

`quick_sell_price`/`next_serial_number`/`next_club_serial_number` exist on
`Coach` for the exact reasons they exist on `Player` — quick-selling and
atomic per-template serial assignment (`Player.next_serial_number`'s own
docstring: "assigned atomically... under a row lock on the Player" —
`services/card_creation.py` pattern to be reused for coaches, see §8).

**`backend/app/models/user_coach_card.py`** — personal ownership, a direct
`UserCard` mirror minus everything diamond/lock-specific:

```python
class UserCoachCard(Base):
    __tablename__ = "user_coach_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id", ondelete="RESTRICT"), nullable=False, index=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[CardSource] = mapped_column(Enum(CardSource, name="card_source_enum"), nullable=False)
    source_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_locked_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped["User"] = relationship()
    coach: Mapped["Coach"] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("coach_id", "serial_number", name="uq_user_coach_cards_coach_serial"),)
```

Reuses the existing `CardSource` enum (`pack`/`admin_grant`/... — confirm
exact members at implementation time) rather than inventing a parallel one.

**`backend/app/models/club_coach_card.py`** — club ownership, a direct
`ClubCard` mirror:

```python
class ClubCoachCard(Base):
    __tablename__ = "club_coach_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[ClubCoachCardSource] = mapped_column(Enum(ClubCoachCardSource, name="club_coach_card_source_enum"), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    coach: Mapped["Coach"] = relationship(lazy="joined")
```

`ClubCoachCardSource` is a new, minimal enum (`club_pack` only for now —
`ClubCardSource` also has `starter_seed`, not needed here since clubs don't
start with a free coach).

**Equip = a nullable FK on the existing "settings" row, not a new table.**
Both `ClubLineup` (one row per club, `club_id` unique) and `Lineup`
(multiple rows per user, at most one `is_active=True`, enforced by
`uq_lineup_one_active_per_user`) are already exactly "the row that holds
this squad's current settings" — formation/mentality/playstyle for clubs,
formation/tactic for personal. A coach is one more setting of that same
kind, so it belongs there, not in a new junction table:

```python
# ClubLineup (backend/app/models/club_lineup.py) gains:
club_coach_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True)

# Lineup (backend/app/models/lineup.py) gains:
user_coach_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True)
```

`ON DELETE SET NULL` (not `RESTRICT`/`CASCADE`) — unequipping is implicit
and safe if the underlying coach card is ever removed by an admin.

## 4. Rarity → boost-slot-count and magnitude framework

Confirmed with the product owner: rarity caps at `legendary` (no diamond
coaches), boost **count** scales with rarity, and higher rarity also means
a **stronger** magnitude for whichever boosts a coach has:

| Rarity    | Boost slots | Distinct boost types required |
|-----------|-------------|--------------------------------|
| common    | 1           | 1 (no duplicates — enforced by `uq_coach_boost_type_once`) |
| rare      | 1           | 1 |
| epic      | 2           | 2 |
| legendary | 3           | 3 |

A coach can never carry the same `CoachBoostType` twice (§3's unique
constraint) — this is deliberate: it keeps a legendary coach a genuine
*build* (three different levers) rather than one stat tripled.

**Magnitude tiers per rarity** (a coach's own rarity sets the magnitude of
*every* boost it carries — a legendary coach's three boosts are all at the
legendary tier, not independently rolled):

Every boost's `magnitude` is expressed in that boost's own native unit
(documented per boost in §5) using a common **tier index** — common=1,
rare=2, epic=3, legendary=4 — so `coach_boost_service.py` (§6) can compute
`base_unit * tier_index` uniformly, with `base_unit` fixed per boost type.
**These starting `base_unit` values are placeholders for a first pass, not
final numbers** — exactly like every other constant in
`club_tactical_matchup_service.py` this session, they must be validated
against `scripts/simulate_tactical_matrix.py`-style simulation before
shipping, not shipped on judgment alone. Starting points, chosen to sit
well inside the existing systems' own ranges (never let a legendary coach
alone flip a matchup the way an uncapped multiplier already proved unsafe
once this session — see the Phase 1 STATUS doc's "safety bug" writeup):

| Boost type              | Native unit                              | `base_unit` (× tier 1-4) |
|--------------------------|-------------------------------------------|--------------------------|
| Zone/category boosts (1-6 in §5) | flat rating points, capped at 99 | 2 → 4/6/8 rating points |
| `PASSING_ACCURACY`       | percentage points off pass-fail chance     | 1 → 2/3/4 points |
| `BALL_CONTROL`           | additive to `INITIATIVE_MULT`              | 0.03 → 0.06/0.09/0.12 |
| `DEFENSIVE_DISCIPLINE`   | additive to `MENTALITY_DEFENSE_SHIFT["ATTACKING"]`, **clamped so the result never exceeds `0.0`** (never lets ATTACKING defend as well as BALANCED — see §5) | 0.01 → 0.02/0.03/0.04 |
| `COUNTER_MASTERY`        | additive to `TRANSITION_BONUS["COUNTER_ATTACK"]` | 0.1 → 0.2/0.3/0.4 |
| `SQUAD_STABILITY`        | additive to `DEPTH_BONUS_CAP`              | 1 → 2/3/4 rating points |

## 5. The 11 boosts and their exact hook points

Grounded in the actual current code (all file:line references verified
against the working tree as of this spec's writing):

1. **Атака в центре** (`ATTACK_CENTRAL`) — Tournament: adds to
   `zone_values["central_attack"]` inside `compute_profile`
   (`club_tactical_profile_service.py:80-97`), before the `min(99.0, ...)`
   clamp. Arena: adds to the FWD category average
   (`match_service._category_avg(lineup, "FWD")`, `match_service.py:77-79`).
2. **Атака на флангах** (`ATTACK_WING`) — Tournament only:
   `zone_values["wing_attack"]`. Arena has no flank concept (confirmed:
   Arena's only categories are `FWD`/`DEF`/`GK`, `lineup_service.py:48-53`)
   — no-op there, and the frontend/admin coach UI must say so plainly
   rather than imply a hidden effect.
3. **Контроль полузащиты** (`MIDFIELD_CONTROL`) — Tournament:
   `zone_values["midfield_control"]`. Arena: no midfield category exists;
   apply the same rating-point value directly to the personal
   `lineup.team_strength` used in `_with_jitter(lineup.team_strength)`
   (`match_service.py:643`) as a small flat bonus — a deliberately modest,
   generic stand-in, documented as such (not a fabricated "midfield" number
   Arena has no way to represent).
4. **Защита в центре** (`DEFENCE_CENTRAL`) — Tournament:
   `zone_values["central_defence"]`. Arena: DEF category average.
5. **Защита на флангах** (`DEFENCE_WING`) — Tournament only:
   `zone_values["wing_defence"]`. Same "no flank concept" no-op as #2.
6. **Игра вратаря** (`GOALKEEPING`) — Tournament:
   `zone_values["goalkeeping"]`. Arena: GK category average.
7. **Точность передач** (`PASSING_ACCURACY`) — Tournament: raises the input
   to `_first_pass_quality_factor(profile.midfield_control)`
   (`club_tactical_matchup_service.py:265`) by the boost's rating-point
   value before that function runs (i.e. treat midfield_control as higher,
   for this factor only, without mutating the real zone value other duel
   math reads). Arena: subtracts the magnitude (percentage points) from
   both `config.match_pass_fail_chance_min` and `..._max` for the passer's
   own side only, right before the `_lerp_chance(...)` call at
   `match_service.py:363-365`, floored so the chance can never go negative.
8. **Контроль мяча** (`BALL_CONTROL`) — Tournament: adds directly to
   `INITIATIVE_MULT[mentality]` for the coached side's own mentality inside
   `initiative_probability` (`club_tactical_matchup_service.py:64-68`).
   Arena: **no hook** — Arena has no initiative/possession-share concept
   (confirmed in research; not fabricated). Documented as tournament-only.
9. **Дисциплина в обороне** (`DEFENSIVE_DISCIPLINE`) — Tournament only:
   inside `defender_ratio_shift_for` (`club_tactical_matchup_service.py:
   396-399`), when `defender.mentality == "ATTACKING"`, add the boost's
   magnitude to `MENTALITY_DEFENSE_SHIFT["ATTACKING"]` for that lookup,
   **clamped at `min(0.0, ...)`** — an ATTACKING-mentality team can never
   be pushed to defend as well as BALANCED (`0.0`) purely by a coach; the
   tradeoff mentality itself represents must stay real. No Arena hook (no
   mentality concept there).
10. **Мастерство контратак** (`COUNTER_MASTERY`) — Tournament only: when
    the coached side's `playstyle == "COUNTER_ATTACK"`, adds to
    `TRANSITION_BONUS["COUNTER_ATTACK"]` (`club_tactical_matchup_service.py:
    24-27`) for that side's own transition-chance calculation only — never
    mutates the shared module dict, applied as a local override at the
    specific call site (`club_tactical_matchup_service.py:265`, the same
    `TRANSITION_BONUS[y.playstyle]` read). No Arena hook (no playstyle
    concept there).
11. **Стабильность состава** (`SQUAD_STABILITY`) — Tournament only: adds to
    the effective `DEPTH_BONUS_CAP` used inside `compute_profile`'s per-zone
    loop (`club_tactical_profile_service.py:92`) for the coached team's
    zones. No Arena hook (Arena has one fixed formation, no depth-bonus
    concept — confirmed, `lineup_service.py`'s personal path never imports
    `DEPTH_BONUS_CAP`).

**Honesty about Arena coverage, matching the product owner's own framing**
("в кард арене, на что сможем повлиять, на то и повлияем"): boosts 8-11
(4 of 11) have *no* Arena effect at all, by design — Arena's engine
genuinely has no matching lever, and inventing one would be exactly the
kind of unsubstantiated claim this session has repeatedly avoided when
writing player-facing tactics copy (see `ClubSquadPage.tsx`'s tactics-guide
block, written from verified mechanics only). The Coach detail UI (§9) must
say plainly which boosts are tournament-only.

## 6. `coach_boost_service.py` — where the dispatch logic lives

A new service, not scattered `if boost_type == ...` blocks inside the match
engines themselves — keeps `club_tactical_profile_service.py`,
`club_tactical_matchup_service.py`, and `match_service.py` each taking a
small, explicit "here are this team's active coach boosts" input rather
than importing coach internals directly.

```python
@dataclass(frozen=True)
class ActiveCoachBoosts:
    by_type: dict[CoachBoostType, float]  # boost_type -> resolved magnitude, already tier-scaled

def resolve_active_boosts(coach: Coach | None) -> ActiveCoachBoosts:
    """coach=None (nothing equipped) returns an empty ActiveCoachBoosts —
    every call site below treats a missing entry in `by_type` as 0, so
    'no coach equipped' requires zero special-casing downstream."""

def apply_zone_boosts(zone_values: dict[str, float], boosts: ActiveCoachBoosts) -> dict[str, float]:
    """Central_attack/wing_attack/midfield_control/central_defence/
    wing_defence/goalkeeping — used by compute_profile."""

def depth_bonus_cap_for(boosts: ActiveCoachBoosts) -> float:
    """DEPTH_BONUS_CAP + SQUAD_STABILITY's resolved magnitude, or the plain
    constant if boosts.by_type is empty."""

def initiative_mult_for(mentality: str, boosts: ActiveCoachBoosts) -> float:
    """INITIATIVE_MULT[mentality] + BALL_CONTROL's resolved magnitude."""

def defensive_shift_for(mentality: str, boosts: ActiveCoachBoosts) -> float:
    """MENTALITY_DEFENSE_SHIFT[mentality], plus DEFENSIVE_DISCIPLINE's
    clamped offset when mentality == 'ATTACKING'."""

def transition_bonus_for(playstyle: str, boosts: ActiveCoachBoosts) -> float:
    """TRANSITION_BONUS[playstyle], plus COUNTER_MASTERY's magnitude when
    playstyle == 'COUNTER_ATTACK'."""

def first_pass_input_bonus(boosts: ActiveCoachBoosts) -> float:
    """PASSING_ACCURACY's resolved magnitude, added to midfield_control
    before _first_pass_quality_factor runs."""

def arena_category_bonus(category: str, boosts: ActiveCoachBoosts) -> int:
    """FWD/DEF/GK -> the matching zone boost's magnitude, or 0."""

def arena_pass_fail_chance_reduction(boosts: ActiveCoachBoosts) -> float:
    """PASSING_ACCURACY's magnitude, as percentage points to subtract."""

def arena_team_strength_bonus(boosts: ActiveCoachBoosts) -> int:
    """MIDFIELD_CONTROL's magnitude, Arena's stand-in per §5 item 3."""
```

Every one of the match-engine functions this touches
(`compute_profile`, `initiative_probability`, `defender_ratio_shift_for`,
the `TRANSITION_BONUS[...]` read inside the duel chain,
`_first_pass_quality_factor`'s call site, `calculate_base_strength`'s
callers, `_category_avg`, the pass-fail `_lerp_chance` call) gains an
**optional** `coach_boosts: ActiveCoachBoosts | None = None` parameter
defaulting to `None` → treated as empty, so no existing call site (tests
included) changes behavior without explicitly opting in. This is the same
non-breaking-default-arg approach already used for `_describe_event`'s
`playstyle`/`quality` params this session — a proven pattern in this exact
codebase for adding an optional cross-cutting input to shared functions.

## 7. Acquisition — two new, independent pack systems

Confirmed: club coaches "выпадают из паков" (drop from packs) as their own
separate pool, distinct from personal coaches. Both mirror the existing
personal/club pack pair exactly, reusing the *rarity-roll* machinery
verbatim (`pack_service.roll_rarities` takes a list of `(rarity,
probability)` rows plus a card count — it has no idea what a "player" is,
so it needs no changes at all) while adding one new coach-drawing function
per side:

```python
# pack_service.py gains, alongside pick_random_player:
async def pick_random_coach(db: AsyncSession, rarity: Rarity) -> Coach:
    """Verbatim mirror of pick_random_player (pack_service.py:84-108),
    querying Coach instead of Player, no CardCollection join (coaches don't
    belong to seasonal collections in this iteration)."""
```

**New models** (each a direct mirror of its Player-pack equivalent):

- `backend/app/models/coach_pack.py` — `CoachPack` (mirrors `Pack`:
  `slug`, `name`, `price`, `card_count`, `guaranteed_min_rarity`,
  `rarity_probabilities`; no `stars_price`/`bonus_coins`/`badge_id` —
  Stars purchases and badges are out of scope for a first iteration) +
  `CoachPackRarityProbability`.
- `backend/app/models/coach_pack_opening.py` — `CoachPackOpening` +
  `CoachPackOpeningCard`, mirroring `PackOpening`/`PackOpeningCard`
  (`pack.py:68-96`) with `user_coach_card_id` in place of `user_card_id`.
- `backend/app/models/club_coach_pack.py` — `ClubCoachPack` (mirrors
  `ClubPack`, `club_pack.py:11-27`, exactly — same fields).
- `backend/app/models/club_coach_pack_opening.py` — `ClubCoachPackOpening`
  + `ClubCoachPackOpeningCard`, mirroring `club_pack_opening.py` verbatim
  with `club_coach_card_id` in place of `club_card_id`.

**New services**, each a close mirror of its player-pack counterpart:

- `coach_pack_service.open_coach_pack(db, user, coach_pack_id,
  idempotency_key)` — mirrors `pack_service.open_pack`'s coin-debit +
  idempotency-key-unique-constraint pattern (`pack_service.py:277-...`),
  crediting via the existing `wallet_service` (CLAUDE.md's wallet
  pattern — `lock_user_for_update`, `debit_coins`).
- `club_coach_pack_service.open_club_coach_pack(db, user, club_coach_pack_id,
  idempotency_key)` — mirrors `club_pack_service.open_club_pack`
  (`club_pack_service.py:44-108`) exactly, including its
  `_require_manager`/`_lock_club`/`debit_club_budget` sequence and its
  captured-`club_id`-before-rollback pattern (see that function's own
  comment on why, `club_pack_service.py:63-69` — the same race applies
  here unchanged).

## 8. Equip flow

**Club:** `PUT /clubs/me/coach` (new endpoint, mirrors the existing
`PUT /clubs/me/tactics` → `club_squad_service.set_club_tactics`), body
`{club_coach_card_id: int | null}`. Server validates the card belongs to
the caller's club (`ClubCoachCard.club_id == membership.club_id`) and the
caller is captain/assistant (same `_require_manager`-style check
`club_pack_service.py:46` already uses), then sets
`ClubLineup.club_coach_card_id`.

**Personal:** `PUT /matches/me/coach` (new endpoint, next to wherever
`Lineup`'s `tactic`/formation setters already live in the match/lineup
router), body `{user_coach_card_id: int | null}`. Sets
`Lineup.user_coach_card_id` on the caller's active lineup.

Both endpoints reject a card id that isn't owned by the caller (403/404 per
this codebase's existing `AppError` conventions, not a raw 500).

**Reading the equipped coach into a match:** `club_squad_service`'s lineup
loader and `lineup_service`'s active-lineup loader both already
`joinedload` their card relationships — add `joinedload(ClubLineup.club_coach_card).joinedload(ClubCoachCard.coach).joinedload(Coach.boosts)`
(and the personal equivalent) so `resolve_active_boosts(coach)` never
triggers a lazy load inside `compute_profile`/`start_match`, the same
async-safety concern already documented for `ClubCard.player`
(`lazy="joined"`, confirmed working end-to-end by this session's Task 2
reviewer).

## 9. Frontend & admin surface (implementation-plan level detail, not fully specced here)

- **Club squad page** (`ClubSquadPage.tsx`) — a new "Тренер" row above or
  below the tactics pickers, showing the equipped coach's name, rarity
  badge, and its boosts (using the same tournament-only/Arena-effective
  labeling from §5); tapping it opens a picker over the club's owned
  `ClubCoachCard`s (empty state: "У клуба пока нет тренера — открой пак").
- **A personal equivalent** wherever the Card Arena / personal lineup is
  managed (needs its own short exploration pass at plan time — this spec
  doesn't assume a specific existing page/file for it).
- **New pack-opening screens** for both new pack kinds, reusing the
  existing staged pack-opening animation component (CLAUDE.md: "packs with
  staged opening animation" is already a generic, reusable piece — confirm
  at plan time it takes a card-content prop generic enough for a coach's
  name+image+boosts instead of a player's name+position+rating).
  card+
- **Admin**: a new `AdminCoachesPage.tsx` mirroring `AdminPlayersPage.tsx`
  for `Coach` CRUD (including its up-to-3 `CoachBoost` rows per the rarity
  table in §4, validated client-side against §4's slot-count rule) plus new
  admin pages for `CoachPack`/`ClubCoachPack` mirroring the existing pack
  admin pages.

## 10. Configuration strategy

Per §1 and the precedent confirmed in research (the rarity bonus
coefficient, mentality shifts, zone weights, and `TRANSITION_BONUS` are all
plain module constants, not `GameConfig` fields, despite being just as
"tunable" in spirit): every `base_unit` in §4's table and the rarity→slot
mapping in §4 live as module constants in `coach_boost_service.py`. No new
`GameConfig` columns.

Coach **pack prices** are the one genuinely admin-tunable number here —
`CoachPack.price`/`ClubCoachPack.price` are plain row values (exactly like
`Pack.price`/`ClubPack.price` already are), editable via the new admin
pages, not `GameConfig` fields either — consistent with how existing packs
are priced.

## 11. Migration

New tables only — nothing about existing `Player`/`UserCard`/`ClubCard`/
`Pack`/`ClubPack` rows changes. `ClubLineup.club_coach_card_id` and
`Lineup.user_coach_card_id` are nullable columns added to existing tables
(`ALTER TABLE ... ADD COLUMN ... NULL`), defaulting every existing lineup
to "no coach equipped" — exactly the same shape as the `diamond`
rarity-enum migration this session already did for a comparable "add a new
optional thing, nothing existing breaks" change (`0083_diamond_rarity.py`).
Sequential `NNNN_` numbering continues from whatever HEAD is at
implementation time (confirmed current HEAD: `0089_diamond_rating_cap.py`,
but this will have moved on by plan time — the plan must re-check, not
assume `0090`).

## 12. Tests

- Model/service level: `CoachBoost`'s per-coach uniqueness constraint;
  `resolve_active_boosts` returns empty for `coach=None`; each
  `coach_boost_service` function's boost-vs-no-boost delta, including the
  `DEFENSIVE_DISCIPLINE` clamp (`ATTACKING`'s effective shift must never
  exceed `0.0` even at legendary magnitude — a direct regression test
  against this session's own "extreme values inverted a matchup" lesson).
- Pack level: `pick_random_coach` mirrors `pick_random_player`'s own test
  coverage (rarity filter, `is_active`/`is_pack_droppable` filter,
  fallback-to-any-active-coach path); `open_coach_pack`/
  `open_club_coach_pack` idempotency-key tests mirroring the existing pack
  tests exactly.
- Integration/balance: extend `scripts/simulate_tactical_matrix.py` (or a
  sibling script) with a coach-boost dimension — at minimum, confirm no
  single legendary coach build lets a materially weaker squad beat a
  materially stronger one at a rate outside the bands this session already
  established for tactics alone (§4 of the Phase 1 STATUS doc's target 4).
  **This is not optional polish** — every other numeric lever in this
  match engine shipped only after simulation evidence, per this session's
  own established practice, and boost magnitudes are exactly the kind of
  number that looked safe in isolation and wasn't (the multiplier→shift
  redesign this session did for mentality was exactly this failure mode).

## 13. Suggested phasing

This spec describes the whole feature; a single implementation plan
attempting all of it (2 pack economies × 2 match-engine hook sets × admin
+ frontend UI for both) would be too large for one coherent plan/review
cycle. Suggested phase boundaries, each shipping a complete, testable
slice — mirroring how the club tactical match engine itself was phased:

- **Phase 1 — shared foundations.** `Coach`/`CoachBoost` models, migration,
  `coach_boost_service.py` (§6), admin CRUD for coaches (`AdminCoachesPage`,
  §9). No acquisition path yet — coaches exist and can be graded/balanced
  by an admin, nothing user-facing changes.
- **Phase 2 — club track, end to end.** `ClubCoachCard`, `ClubCoachPack` +
  its open/purchase flow (§7), `ClubLineup.club_coach_card_id` + the equip
  endpoint (§8), every tournament-engine hook in §5, the squad-page "Тренер"
  UI (§9). Ships the higher-priority half per §1's explicit instruction
  (tournaments first) as one working feature end to end.
- **Phase 3 — personal track, end to end.** `UserCoachCard`, `CoachPack` +
  its open/purchase flow, `Lineup.user_coach_card_id` + its equip endpoint,
  every Arena-effective hook in §5, the personal equip UI. Mirrors Phase
  2's shape for the second, independent economy.
- **Phase 4 — balance pass.** Extend the simulation tooling per §12,
  validate/adjust every `base_unit` in §4 against real match data before
  calling the magnitudes final — not a "nice to have," per this session's
  own established practice of never shipping a new numeric lever on
  judgment alone.

## 14. Open items for the implementation plan (not blocking this spec)

- Exact router/file for the personal "equip coach" endpoint and UI — needs
  a short exploration pass (this spec doesn't assume where Card
  Arena's own settings UI/router already lives beyond `match_service.py`).
- Whether `CardSource`'s existing enum members (`pack`, `admin_grant`, ...)
  are sufficient for `UserCoachCard.source` as-is, or need a coach-specific
  addition — confirm exact current members at implementation time.
- Whether the pack-opening animation component's props are generic enough
  to reuse for coaches without modification, or need a small prop-shape
  extension.
