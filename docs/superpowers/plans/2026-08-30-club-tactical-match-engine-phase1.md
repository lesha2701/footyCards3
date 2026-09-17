# Club Tactical Match Engine — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace club tournament matches' `team_strength`-only resolution with a formation/mentality/playstyle-driven possession-phase pipeline (initiative → progression → duel chain → effective defensive pool → counter-attack chain → existing shot/save engine), per Phase 1 of the design spec.

**Architecture:** Three new club-only services (`club_formation_service`, `club_tactical_profile_service`, `club_tactical_matchup_service`) produce a list of individually-duelled `Chance` objects each round; `tournament_match_engine.py` is refactored to consume that list instead of its own random moment queue, handing each chance to its existing (unchanged) shot/tackle/save resolution functions with a quality-derived bias. `ClubLineup` gains `formation`/`mentality`/`playstyle` columns and a `PUT /clubs/me/tactics` endpoint. `tournament_simulation_service.simulate_next_round` is rewired to build tactical profiles and call the new engine entry point.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, pytest (async, in-memory SQLite), React 18 + TypeScript + TanStack Query for the minimal Phase 1 picker UI.

**Spec:** [docs/superpowers/specs/2026-08-30-club-tactical-match-engine-design.md](../specs/2026-08-30-club-tactical-match-engine-design.md)

## Global Constraints

- Never edit `lineup_service.py`'s `FormationSlot`, `FORMATION_SLOTS`, `SLOTS_BY_CODE`, `TACTIC_MULTIPLIERS`, `split_strength`, or anything in `match_service.py` — those drive the personal Card Arena engine and must stay untouched (spec §2). `CATEGORY_POSITIONS` and `calculate_base_strength` ARE imported and reused as-is (formation-agnostic).
- `match_situations.py`'s `ATTACK_SITUATIONS_*`/`DEFENSE_SITUATIONS_*` stay untouched — still used by `match_service.py`. `tournament_match_engine.py` stops importing them entirely (Task 10).
- No dual-engine flag. `generate_moment_queue` and the old `simulate_match` in `tournament_match_engine.py` are deleted outright once the new pipeline replaces their only caller (spec §2, §13).
- `SUBSTITUTION_PENALTY` in `tournament_simulation_service.py` is retired (spec §5) — a forced substitution's effect on the match is now emergent (a weaker sub lowers whichever zone(s) it feeds), not a flat 0.5× multiplier.
- Form (`form_multiplier`) stops affecting match simulation outcomes in the new engine — it is computed for `team_strength` UI display only (spec §5). Do not plumb it into initiative or any zone.
- Every zone/duel/mentality/playstyle numeric table in this plan is copied verbatim from spec §5/§6/§7/§8 where the spec gives an exact table; the small number of formulas the spec describes only in prose (not as an exact table) are pinned to one concrete formula each, called out explicitly in that task with a comment explaining the choice — Phase 3's balance script (out of scope here) is where these get tuned, not invented.
- All new backend modules live under `backend/app/services/`. Reuse `db_session`/`client`/`bot_token` pytest fixtures and this repo's existing `_seed_position_pool` / `_create_club` test patterns (see `tests/test_club_squad.py`, `tests/test_tournament_simulation_lineup.py`) — do not invent new fixture styles.
- Run `cd backend && pytest tests/ -v` after every task; run `cd frontend && npm run typecheck` after Task 14.

---

### Task 1: Formation registry

**Files:**
- Create: `backend/app/services/club_formation_service.py`
- Test: `backend/tests/test_club_formation_service.py`

**Interfaces:**
- Produces: `CLUB_FORMATIONS: dict[str, list[FormationSlot]]`, `DEFAULT_FORMATION: str`, `get_formation_slots(formation: str) -> list[FormationSlot]`, `get_slots_by_code(formation: str) -> dict[str, FormationSlot]`. Raises `app.core.exceptions.ConflictError` for an unknown formation name.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_club_formation_service.py
import pytest

from app.core.exceptions import ConflictError
from app.models.enums import Position
from app.services import club_formation_service as svc


def test_default_formation_is_4_3_3():
    assert svc.DEFAULT_FORMATION == "4-3-3"


def test_every_formation_has_eleven_slots_and_one_gk():
    for formation, slots in svc.CLUB_FORMATIONS.items():
        assert len(slots) == 11, formation
        gk_slots = [s for s in slots if s.category == "GK"]
        assert len(gk_slots) == 1, formation
        assert gk_slots[0].ideal_position == Position.GK


def test_get_formation_slots_returns_registered_list():
    slots = svc.get_formation_slots("4-4-2")
    assert [s.code for s in slots] == ["GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "MID4", "FWD1", "FWD2"]
    assert [s.ideal_position for s in slots if s.category == "MID"] == [Position.LM, Position.CM, Position.CM, Position.RM]


def test_get_formation_slots_rejects_unknown_formation():
    with pytest.raises(ConflictError):
        svc.get_formation_slots("4-2-4")


def test_get_slots_by_code_keys_match_codes():
    by_code = svc.get_slots_by_code("3-5-2")
    assert set(by_code.keys()) == {"GK", "DEF1", "DEF2", "DEF3", "MID1", "MID2", "MID3", "MID4", "MID5", "FWD1", "FWD2"}
    assert by_code["MID2"].ideal_position == Position.CDM


def test_5_3_2_has_five_defenders_and_two_wide_backs():
    slots = svc.get_formation_slots("5-3-2")
    def_positions = [s.ideal_position for s in slots if s.category == "DEF"]
    assert def_positions.count(Position.CB) == 3
    assert Position.LB in def_positions and Position.RB in def_positions
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_formation_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.club_formation_service'`

- [ ] **Step 3: Implement the formation registry**

```python
# backend/app/services/club_formation_service.py
from app.core.exceptions import ConflictError
from app.models.enums import Position
from app.services.lineup_service import FormationSlot

DEFAULT_FORMATION = "4-3-3"

# Verbatim from the design spec §4. FormationSlot is imported (not redefined)
# from lineup_service — same dataclass shape, but this dict is a completely
# separate registry from lineup_service.FORMATION_SLOTS: club matches must
# never be affected by a future change to the personal engine's single
# formation, and vice versa (see this plan's Global Constraints).
CLUB_FORMATIONS: dict[str, list[FormationSlot]] = {
    "4-3-3": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.CDM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CAM),
        FormationSlot("FWD1", "FWD", Position.LW), FormationSlot("FWD2", "FWD", Position.ST),
        FormationSlot("FWD3", "FWD", Position.RW),
    ],
    "4-4-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.LM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CM), FormationSlot("MID4", "MID", Position.RM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
    "3-5-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.CB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB),
        FormationSlot("MID1", "MID", Position.LM), FormationSlot("MID2", "MID", Position.CDM),
        FormationSlot("MID3", "MID", Position.CM), FormationSlot("MID4", "MID", Position.CAM),
        FormationSlot("MID5", "MID", Position.RM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
    "5-3-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.CB),
        FormationSlot("DEF5", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.CDM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CAM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
}


def get_formation_slots(formation: str) -> list[FormationSlot]:
    if formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Unknown formation: {formation}")
    return CLUB_FORMATIONS[formation]


def get_slots_by_code(formation: str) -> dict[str, FormationSlot]:
    return {s.code: s for s in get_formation_slots(formation)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_formation_service.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_formation_service.py tests/test_club_formation_service.py
git commit -m "feat(clubs): add club formation registry (4-3-3/4-4-2/3-5-2/5-3-2)"
```

---

### Task 2: Data model — ClubLineup tactics columns + GameConfig fields + migration

**Files:**
- Modify: `backend/app/models/club_lineup.py`
- Modify: `backend/app/models/game_config.py`
- Create: `backend/alembic/versions/0082_club_tactics.py`
- Test: `backend/tests/test_club_squad.py` (extend)

**Interfaces:**
- Produces: `ClubLineup.formation: str` (default `"4-3-3"`), `ClubLineup.mentality: str` (default `"BALANCED"`), `ClubLineup.playstyle: str` (default `"CENTRAL_PLAY"`); `GameConfig.club_tactical_phases_per_match_min/_max`, `.club_tactical_promoted_chance_target_min/_max`, `.club_tactical_fit_formation_weight/_playstyle_weight/_mentality_weight`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_club_squad.py
async def test_new_club_lineup_defaults_to_4_3_3_balanced_central(client, db_session, bot_token):
    from app.models.club_lineup import ClubLineup

    club, _headers = await _create_club(client, bot_token, 820310, "Клуб с тактикой по умолчанию")
    # `select` is already imported at the top of this file (`from sqlalchemy import select, text`).
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == club["id"]))).scalar_one()
    assert lineup.formation == "4-3-3"
    assert lineup.mentality == "BALANCED"
    assert lineup.playstyle == "CENTRAL_PLAY"
```

(Uses `_create_club`/`_seed_position_pool` already defined earlier in this file.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_club_squad.py::test_new_club_lineup_defaults_to_4_3_3_balanced_central -v`
Expected: FAIL with `AttributeError: 'ClubLineup' object has no attribute 'formation'`

- [ ] **Step 3: Add the model columns**

```python
# backend/app/models/club_lineup.py — add to ClubLineup, after `created_at`:
    formation: Mapped[str] = mapped_column(String(16), default="4-3-3", nullable=False, server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), default="BALANCED", nullable=False, server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), default="CENTRAL_PLAY", nullable=False, server_default="CENTRAL_PLAY")
```

```python
# backend/app/models/game_config.py — add to GameConfig, after club_missing_item_reward_cap:
    club_tactical_phases_per_match_min: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    club_tactical_phases_per_match_max: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    club_tactical_promoted_chance_target_min: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    club_tactical_promoted_chance_target_max: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    club_tactical_fit_formation_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.40, nullable=False)
    club_tactical_fit_playstyle_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.40, nullable=False)
    club_tactical_fit_mentality_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.20, nullable=False)
```

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0082_club_tactics.py
"""Add club formation/mentality/playstyle + tactical engine config fields

Revision ID: 0082
Revises: 0081
Create Date: 2026-08-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: Union[str, None] = "0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("formation", sa.String(length=16), nullable=False, server_default="4-3-3"))
    op.add_column("club_lineups", sa.Column("mentality", sa.String(length=16), nullable=False, server_default="BALANCED"))
    op.add_column("club_lineups", sa.Column("playstyle", sa.String(length=16), nullable=False, server_default="CENTRAL_PLAY"))

    op.add_column("game_config", sa.Column("club_tactical_phases_per_match_min", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("club_tactical_phases_per_match_max", sa.Integer(), nullable=False, server_default="70"))
    op.add_column("game_config", sa.Column("club_tactical_promoted_chance_target_min", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("club_tactical_promoted_chance_target_max", sa.Integer(), nullable=False, server_default="25"))
    op.add_column("game_config", sa.Column("club_tactical_fit_formation_weight", sa.Numeric(4, 2), nullable=False, server_default="0.40"))
    op.add_column("game_config", sa.Column("club_tactical_fit_playstyle_weight", sa.Numeric(4, 2), nullable=False, server_default="0.40"))
    op.add_column("game_config", sa.Column("club_tactical_fit_mentality_weight", sa.Numeric(4, 2), nullable=False, server_default="0.20"))


def downgrade() -> None:
    op.drop_column("game_config", "club_tactical_fit_mentality_weight")
    op.drop_column("game_config", "club_tactical_fit_playstyle_weight")
    op.drop_column("game_config", "club_tactical_fit_formation_weight")
    op.drop_column("game_config", "club_tactical_promoted_chance_target_max")
    op.drop_column("game_config", "club_tactical_promoted_chance_target_min")
    op.drop_column("game_config", "club_tactical_phases_per_match_max")
    op.drop_column("game_config", "club_tactical_phases_per_match_min")

    op.drop_column("club_lineups", "playstyle")
    op.drop_column("club_lineups", "mentality")
    op.drop_column("club_lineups", "formation")
```

Note: `game_config.py`'s `Numeric` import already exists (used by `club_form_bonus_per_result`); no new import needed there. `String`/`Mapped`/`mapped_column` already imported in `club_lineup.py`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_club_squad.py::test_new_club_lineup_defaults_to_4_3_3_balanced_central -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/models/club_lineup.py app/models/game_config.py alembic/versions/0082_club_tactics.py tests/test_club_squad.py
git commit -m "feat(clubs): add formation/mentality/playstyle columns and tactical config fields"
```

---

### Task 3: TeamTacticalProfile — zone weight table and profile computation

**Files:**
- Create: `backend/app/services/club_tactical_profile_service.py`
- Test: `backend/tests/test_club_tactical_profile_service.py`

**Interfaces:**
- Consumes: `lineup_service.FormationSlot`, `lineup_service.calculate_base_strength`.
- Produces: `ZONES: tuple[str, ...]`, `ZONE_WEIGHTS: dict[Position, dict[str, float]]`, `zone_weight(position, zone) -> float`, `position_fit(position, zone) -> float`, `@dataclass TeamTacticalProfile(central_attack, wing_attack, midfield_control, central_defence, wing_defence, goalkeeping, team_strength)`, `compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]]) -> TeamTacticalProfile` where each card-like object exposes `.player.position: Position` and `.player.rating: int`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_club_tactical_profile_service.py
from dataclasses import dataclass

from app.models.enums import Position
from app.services import club_tactical_profile_service as svc
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots


@dataclass
class _FakePlayer:
    position: Position
    rating: int


@dataclass
class _FakeCard:
    id: int
    player: _FakePlayer


def _cards_with_slots(ratings_by_code: dict[str, int], formation: str = "4-3-3"):
    slots = get_formation_slots(formation)
    out = []
    for i, slot in enumerate(slots):
        rating = ratings_by_code.get(slot.code, 70)
        out.append((_FakeCard(id=i, player=_FakePlayer(position=slot.ideal_position, rating=rating)), slot))
    return out


def test_zone_weights_cover_every_position_used_in_any_formation():
    for formation, slots in CLUB_FORMATIONS.items():
        for slot in slots:
            assert slot.ideal_position in svc.ZONE_WEIGHTS, (formation, slot.ideal_position)


def test_st_is_the_strongest_contributor_to_central_attack():
    assert svc.zone_weight(Position.ST, "central_attack") == 1.00
    assert svc.zone_weight(Position.LW, "central_attack") == 0.65
    assert svc.zone_weight(Position.CB, "central_attack") == 0.0


def test_position_fit_discretizes_into_1_0_0_9_0_85():
    assert svc.position_fit(Position.ST, "central_attack") == 1.0       # weight 1.00
    assert svc.position_fit(Position.LW, "central_attack") == 0.9       # weight 0.65
    assert svc.position_fit(Position.CAM, "wing_attack") == 0.85        # weight 0.10
    assert svc.position_fit(Position.CB, "central_attack") == 0.0       # not eligible at all


def test_compute_profile_is_a_weighted_average_not_a_sum():
    # Two STs at rating 90 vs one ST at rating 90 must produce the SAME
    # central_attack value (weighted AVERAGE, not sum) — spec §5.
    one_st = _cards_with_slots({"FWD2": 90})
    profile_one = svc.compute_profile(one_st)

    two_st_formation = _cards_with_slots({"FWD1": 90, "FWD2": 90}, formation="4-4-2")
    profile_two = svc.compute_profile(two_st_formation)

    assert profile_one.central_attack == profile_two.central_attack == 90.0


def test_compute_profile_goalkeeping_only_reflects_the_gk():
    cards = _cards_with_slots({"GK": 88})
    profile = svc.compute_profile(cards)
    assert profile.goalkeeping == 88.0


def test_compute_profile_team_strength_matches_calculate_base_strength():
    from app.services.lineup_service import calculate_base_strength

    cards = _cards_with_slots({})
    profile = svc.compute_profile(cards)
    assert profile.team_strength == calculate_base_strength(cards)


def test_5_3_2_produces_lower_wing_attack_than_4_3_3_for_identical_lb_rb_ratings():
    # 5-3-2 has no LM/RM feeding wing_attack (0.85 weight) the way 4-3-3's
    # LW/RW (1.00 weight) do — same LB/RB rating in both, but 4-3-3's front
    # three genuinely contribute to wing_attack while 5-3-2's extra CB does not.
    shared = {"DEF1": 75, "DEF4": 75}
    four_three_three = svc.compute_profile(_cards_with_slots({**shared, "FWD1": 90, "FWD3": 90}, "4-3-3"))
    five_three_two = svc.compute_profile(_cards_with_slots({**shared, "DEF5": 75}, "5-3-2"))
    assert four_three_three.wing_attack > five_three_two.wing_attack
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_profile_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the zone weight table and profile computation**

```python
# backend/app/services/club_tactical_profile_service.py
from dataclasses import dataclass
from typing import Any

from app.models.enums import Position
from app.services.lineup_service import FormationSlot, calculate_base_strength

ZONES = ("central_attack", "wing_attack", "midfield_control", "central_defence", "wing_defence", "goalkeeping")

# Verbatim from design spec §5. Every position that appears as an
# `ideal_position` in any CLUB_FORMATIONS slot (Task 1) has an entry here;
# test_zone_weights_cover_every_position_used_in_any_formation enforces this.
ZONE_WEIGHTS: dict[Position, dict[str, float]] = {
    Position.GK: {"central_defence": 0.15, "wing_defence": 0.15, "goalkeeping": 1.00},
    Position.CB: {"midfield_control": 0.10, "central_defence": 1.00, "wing_defence": 0.25},
    Position.LB: {"wing_attack": 0.55, "midfield_control": 0.10, "central_defence": 0.20, "wing_defence": 1.00},
    Position.RB: {"wing_attack": 0.55, "midfield_control": 0.10, "central_defence": 0.20, "wing_defence": 1.00},
    Position.CDM: {"central_attack": 0.05, "midfield_control": 0.85, "central_defence": 0.45, "wing_defence": 0.15},
    Position.CM: {"central_attack": 0.20, "wing_attack": 0.05, "midfield_control": 1.00, "central_defence": 0.10},
    Position.CAM: {"central_attack": 0.60, "wing_attack": 0.10, "midfield_control": 0.55},
    Position.LM: {"central_attack": 0.10, "wing_attack": 0.85, "midfield_control": 0.35, "wing_defence": 0.20},
    Position.RM: {"central_attack": 0.10, "wing_attack": 0.85, "midfield_control": 0.35, "wing_defence": 0.20},
    Position.LW: {"central_attack": 0.65, "wing_attack": 1.00, "wing_defence": 0.05},
    Position.RW: {"central_attack": 0.65, "wing_attack": 1.00, "wing_defence": 0.05},
    Position.ST: {"central_attack": 1.00, "wing_attack": 0.10},
}


def zone_weight(position: Position, zone: str) -> float:
    return ZONE_WEIGHTS.get(position, {}).get(zone, 0.0)


# Discretizes the continuous ZONE_WEIGHTS table into the same 1.0/0.9/0.85-
# shaped fit concept calculate_base_strength already uses per formation slot
# (spec §6.3) — reapplied per zone instead. Thresholds: the zone's own
# primary position(s) (weight == 1.00) get full credit; a strong natural
# contributor (weight >= 0.5) gets 0.9; anything present but weakly relevant
# (0 < weight < 0.5) gets 0.85; zero weight means not eligible for this zone.
def position_fit(position: Position, zone: str) -> float:
    weight = zone_weight(position, zone)
    if weight >= 1.00:
        return 1.0
    if weight >= 0.5:
        return 0.9
    if weight > 0.0:
        return 0.85
    return 0.0


@dataclass
class TeamTacticalProfile:
    central_attack: float
    wing_attack: float
    midfield_control: float
    central_defence: float
    wing_defence: float
    goalkeeping: float
    team_strength: int


def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]]) -> TeamTacticalProfile:
    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        zone_values[zone] = round(weighted_sum / weight_total, 1) if weight_total > 0 else 0.0

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_profile_service.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_profile_service.py tests/test_club_tactical_profile_service.py
git commit -m "feat(clubs): compute TeamTacticalProfile zones from position weight table"
```

---

### Task 4: Tactical Fit calculation

**Files:**
- Modify: `backend/app/services/club_tactical_profile_service.py`
- Test: `backend/tests/test_club_tactical_profile_service.py` (extend)

**Interfaces:**
- Consumes: `TeamTacticalProfile`, `ZONES`, `zone_weight`, a `config` object exposing `club_tactical_fit_formation_weight/_playstyle_weight/_mentality_weight` (Task 2).
- Produces: `PLAYSTYLE_ZONES: dict[str, tuple[str, ...]]`, `compute_tactical_fit(cards_with_slots, profile: TeamTacticalProfile, mentality: str, playstyle: str, config) -> int` (0–100).

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_tactical_profile_service.py
class _FakeTacticalFitConfig:
    club_tactical_fit_formation_weight = 0.40
    club_tactical_fit_playstyle_weight = 0.40
    club_tactical_fit_mentality_weight = 0.20


def test_tactical_fit_is_a_percentage():
    cards = _cards_with_slots({})
    profile = svc.compute_profile(cards)
    fit = svc.compute_tactical_fit(cards, profile, "BALANCED", "CENTRAL_PLAY", _FakeTacticalFitConfig())
    assert 0 <= fit <= 100


def test_wing_play_scores_higher_fit_for_a_squad_with_strong_flanks_than_weak_flanks():
    strong_flanks = _cards_with_slots({"FWD1": 92, "FWD3": 92, "DEF1": 85, "DEF4": 85, "FWD2": 65})
    weak_flanks = _cards_with_slots({"FWD1": 65, "FWD3": 65, "DEF1": 65, "DEF4": 65, "FWD2": 92})
    config = _FakeTacticalFitConfig()

    strong_profile = svc.compute_profile(strong_flanks)
    weak_profile = svc.compute_profile(weak_flanks)

    strong_fit = svc.compute_tactical_fit(strong_flanks, strong_profile, "BALANCED", "WING_PLAY", config)
    weak_fit = svc.compute_tactical_fit(weak_flanks, weak_profile, "BALANCED", "WING_PLAY", config)
    assert strong_fit > weak_fit


def test_park_the_bus_scores_higher_fit_for_a_defence_heavy_squad_than_an_attack_heavy_one():
    defence_heavy = _cards_with_slots({"DEF1": 90, "DEF2": 90, "DEF3": 90, "DEF4": 90, "FWD2": 60})
    attack_heavy = _cards_with_slots({"DEF1": 60, "DEF2": 60, "DEF3": 60, "DEF4": 60, "FWD2": 90})
    config = _FakeTacticalFitConfig()

    defence_fit = svc.compute_tactical_fit(
        defence_heavy, svc.compute_profile(defence_heavy), "PARK_THE_BUS", "CENTRAL_PLAY", config
    )
    attack_fit = svc.compute_tactical_fit(
        attack_heavy, svc.compute_profile(attack_heavy), "PARK_THE_BUS", "CENTRAL_PLAY", config
    )
    assert defence_fit > attack_fit
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_profile_service.py -k tactical_fit -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'compute_tactical_fit'`

- [ ] **Step 3: Implement Tactical Fit**

```python
# Append to backend/app/services/club_tactical_profile_service.py
from app.models.enums import Position as _Position  # noqa: F401 (re-export not needed; see CATEGORY_POSITIONS import below)
from app.services.lineup_service import CATEGORY_POSITIONS

# Which zone(s) each playstyle actually leans on — used by playstyle_alignment
# below to check whether a squad's chosen playstyle plays to its OWN strongest
# zones, independent of how strong the squad is in absolute terms (spec §9).
PLAYSTYLE_ZONES: dict[str, tuple[str, ...]] = {
    "WING_PLAY": ("wing_attack", "wing_defence"),
    "CENTRAL_PLAY": ("central_attack", "midfield_control"),
    "POSSESSION": ("midfield_control",),
    "HIGH_PRESS": ("midfield_control", "wing_defence"),
    "COUNTER_ATTACK": ("central_attack", "wing_attack"),
}


def _formation_fit_score(cards_with_slots: list[tuple[Any, FormationSlot]]) -> float:
    """Average of the same 1.0/0.9/0.75 per-slot fit calculate_base_strength
    uses, normalized from its [0.75, 1.0] range into [0, 1] — a squad using
    every slot's ideal position scores 1.0, a squad using only category-legal
    but off-position players throughout scores 0.0."""
    if not cards_with_slots:
        return 0.0
    fits = []
    for card, slot in cards_with_slots:
        if card.player.position == slot.ideal_position:
            fits.append(1.0)
        elif card.player.position in CATEGORY_POSITIONS[slot.category]:
            fits.append(0.9)
        else:
            fits.append(0.75)
    avg_fit = sum(fits) / len(fits)
    return max(0.0, min(1.0, (avg_fit - 0.75) / (1.0 - 0.75)))


def _playstyle_alignment(profile: TeamTacticalProfile, playstyle: str) -> float:
    """Ranks this squad's 6 zones best-to-worst and scores how highly the
    playstyle's target zone(s) rank — 1.0 if they're this squad's very best
    zone(s), 0.0 if they're the worst, regardless of the squad's absolute
    strength (spec §9: "is the zone(s) this playstyle uses actually this
    squad's STRONGEST zone(s)?")."""
    zone_values = {zone: getattr(profile, zone) for zone in ZONES}
    ranked = sorted(zone_values, key=zone_values.get, reverse=True)
    target_zones = PLAYSTYLE_ZONES[playstyle]
    scores = [1 - (ranked.index(zone) / (len(ranked) - 1)) for zone in target_zones]
    return sum(scores) / len(scores)


# target[mentality]: where PARK_THE_BUS/DEFENSIVE want (defence − attack) to
# lean positive, ATTACKING wants it to lean negative, BALANCED wants it near
# zero. A 20-rating gap between defence and attack zones is treated as
# already a full lean (clamped to +/-1) — ratings run ~58-99, so 20 points is
# a large, clearly-intentional squad shape rather than incidental variance.
_MENTALITY_FIT_TARGET = {"PARK_THE_BUS": 1.0, "DEFENSIVE": 0.5, "BALANCED": 0.0, "ATTACKING": -1.0}


def _mentality_fit(profile: TeamTacticalProfile, mentality: str) -> float:
    defence_avg = (profile.central_defence + profile.wing_defence) / 2
    attack_avg = (profile.central_attack + profile.wing_attack) / 2
    gap = max(-1.0, min(1.0, (defence_avg - attack_avg) / 20))
    target = _MENTALITY_FIT_TARGET[mentality]
    return max(0.0, 1 - abs(gap - target) / 2)


def compute_tactical_fit(
    cards_with_slots: list[tuple[Any, FormationSlot]], profile: TeamTacticalProfile, mentality: str, playstyle: str, config
) -> int:
    formation_component = _formation_fit_score(cards_with_slots) * float(config.club_tactical_fit_formation_weight)
    playstyle_component = _playstyle_alignment(profile, playstyle) * float(config.club_tactical_fit_playstyle_weight)
    mentality_component = _mentality_fit(profile, mentality) * float(config.club_tactical_fit_mentality_weight)
    return round(100 * (formation_component + playstyle_component + mentality_component))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_profile_service.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_profile_service.py tests/test_club_tactical_profile_service.py
git commit -m "feat(clubs): add Tactical Fit calculation (formation/playstyle/mentality)"
```

---

### Task 5: Mentality/playstyle registries and initiative

**Files:**
- Create: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py`

**Interfaces:**
- Consumes: `club_tactical_profile_service.TeamTacticalProfile`.
- Produces: `MENTALITIES: tuple[str, ...]`, `PLAYSTYLES: tuple[str, ...]`, `INITIATIVE_MULT: dict[str, float]`, `SAMPLE_FRACTION: dict[str, float]`, `HIGH_PRESS_POOL_MULT: float`, `TRANSITION_BONUS: dict[str, float]`, `initiative_probability(profile_a, mentality_a, profile_b, mentality_b) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_club_tactical_matchup_service.py
from app.services import club_tactical_matchup_service as svc
from app.services.club_tactical_profile_service import TeamTacticalProfile


def _profile(**overrides) -> TeamTacticalProfile:
    base = dict(central_attack=70, wing_attack=70, midfield_control=70, central_defence=70, wing_defence=70, goalkeeping=70, team_strength=700)
    base.update(overrides)
    return TeamTacticalProfile(**base)


def test_mentalities_and_playstyles_registries_match_spec():
    assert svc.MENTALITIES == ("PARK_THE_BUS", "DEFENSIVE", "BALANCED", "ATTACKING")
    assert svc.PLAYSTYLES == ("WING_PLAY", "CENTRAL_PLAY", "POSSESSION", "HIGH_PRESS", "COUNTER_ATTACK")


def test_initiative_mult_table():
    assert svc.INITIATIVE_MULT == {"PARK_THE_BUS": 0.55, "DEFENSIVE": 0.80, "BALANCED": 1.00, "ATTACKING": 1.25}


def test_equal_profiles_and_mentalities_split_initiative_evenly():
    p = _profile()
    assert svc.initiative_probability(p, "BALANCED", p, "BALANCED") == 0.5


def test_attacking_mentality_wins_more_initiative_than_park_the_bus_at_equal_midfield():
    p = _profile()
    prob = svc.initiative_probability(p, "ATTACKING", p, "PARK_THE_BUS")
    assert prob > 0.5


def test_stronger_midfield_wins_more_initiative_at_equal_mentality():
    strong = _profile(midfield_control=90)
    weak = _profile(midfield_control=50)
    prob = svc.initiative_probability(strong, "BALANCED", weak, "BALANCED")
    assert prob > 0.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the registries and initiative**

```python
# backend/app/services/club_tactical_matchup_service.py
import random
from dataclasses import dataclass, field
from typing import Any

from app.services.club_tactical_profile_service import TeamTacticalProfile

MENTALITIES = ("PARK_THE_BUS", "DEFENSIVE", "BALANCED", "ATTACKING")
PLAYSTYLES = ("WING_PLAY", "CENTRAL_PLAY", "POSSESSION", "HIGH_PRESS", "COUNTER_ATTACK")

# Verbatim from design spec §7.
INITIATIVE_MULT: dict[str, float] = {"PARK_THE_BUS": 0.55, "DEFENSIVE": 0.80, "BALANCED": 1.00, "ATTACKING": 1.25}
SAMPLE_FRACTION: dict[str, float] = {"PARK_THE_BUS": 1.00, "DEFENSIVE": 0.90, "BALANCED": 0.75, "ATTACKING": 0.55}
HIGH_PRESS_POOL_MULT = 0.85

# Verbatim from design spec §8's "Transition bonus (§6.5)" column.
TRANSITION_BONUS: dict[str, float] = {
    "WING_PLAY": 1.0, "CENTRAL_PLAY": 1.0, "POSSESSION": 0.7, "HIGH_PRESS": 1.3, "COUNTER_ATTACK": 1.5,
}


def initiative_probability(profile_a: TeamTacticalProfile, mentality_a: str, profile_b: TeamTacticalProfile, mentality_b: str) -> float:
    score_a = profile_a.midfield_control * INITIATIVE_MULT[mentality_a]
    score_b = profile_b.midfield_control * INITIATIVE_MULT[mentality_b]
    total = score_a + score_b
    return score_a / total if total else 0.5
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_matchup_service.py tests/test_club_tactical_matchup_service.py
git commit -m "feat(clubs): add mentality/playstyle registries and initiative calculation"
```

---

### Task 6: Weighted-pick duelist selection, position-fit-weighted zone_ratio, and duel bands

**Files:**
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py` (extend)

**Interfaces:**
- Consumes: `club_tactical_profile_service.ZONE_WEIGHTS/zone_weight/position_fit`.
- Produces: `weighted_pick(cards: list[Any], zone: str, exclude_ids: frozenset[int] = frozenset()) -> Any`, `zone_ratio(attacker, attacker_zone, defender, defender_zone) -> float`, `STAGE1_BANDS`, `STAGE2_BANDS`, `resolve_stage1(ratio: float) -> str`, `resolve_quality(combined_advantage: float) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_tactical_matchup_service.py
import random as _random
from dataclasses import dataclass

from app.models.enums import Position


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"  # _card_to_actor (Task 9) reads this


@dataclass
class _FakeCard:
    id: int
    player: _FakePlayer
    player_id: int = 0  # _card_to_actor (Task 9) reads this


def test_weighted_pick_only_returns_eligible_positions_for_the_zone():
    cards = [
        _FakeCard(1, _FakePlayer(Position.ST, 90)),
        _FakeCard(2, _FakePlayer(Position.CB, 90)),
    ]
    for _ in range(20):
        picked = svc.weighted_pick(cards, "central_attack")
        assert picked.id == 1  # only the ST has any central_attack weight


def test_weighted_pick_respects_exclude_ids():
    cards = [
        _FakeCard(1, _FakePlayer(Position.ST, 90)),
        _FakeCard(2, _FakePlayer(Position.LW, 90)),
    ]
    for _ in range(20):
        picked = svc.weighted_pick(cards, "central_attack", exclude_ids=frozenset({1}))
        assert picked.id == 2


def test_zone_ratio_favors_the_higher_effective_rating():
    # zone_ratio is a plain rating-share formula (eff_a/(eff_a+eff_b)), not
    # squared or sigmoid-shaped, so even the widest possible rating gap at
    # position_fit==1.0 on both sides (99 vs 58) only reaches ~0.63 — well
    # short of 0.75. STAGE1_BANDS'/STAGE2_BANDS' ">0.75" tier is reachable
    # only through the counter-attack chain's extra multipliers (Task 8's
    # transition_bonus/first_pass_quality_factor), not a plain Stage-1/
    # Stage-2 duel — a real, intentional structural property of the design,
    # not a bug. This test checks the achievable direction/magnitude for a
    # 94-vs-65 matchup: 94/(94+65)=0.591.
    strong = _FakeCard(1, _FakePlayer(Position.ST, 94))
    weak = _FakeCard(2, _FakePlayer(Position.CB, 65))
    ratio = svc.zone_ratio(strong, "central_attack", weak, "central_defence")
    assert ratio > 0.55


def test_zone_ratio_is_half_for_identical_effective_ratings():
    a = _FakeCard(1, _FakePlayer(Position.ST, 80))
    b = _FakeCard(2, _FakePlayer(Position.ST, 80))
    assert svc.zone_ratio(a, "central_attack", b, "central_attack") == 0.5


def test_resolve_stage1_weights_advance_more_at_high_ratio(monkeypatch):
    captured = {}
    def fake_choices(population, weights=None, k=1):
        captured["weights"] = weights
        return [population[-1]]
    monkeypatch.setattr(svc.random, "choices", fake_choices)
    svc.resolve_stage1(0.90)
    assert captured["weights"] == [0.10, 0.25, 0.65]
    svc.resolve_stage1(0.30)
    assert captured["weights"] == [0.45, 0.35, 0.20]


def test_resolve_quality_weights_very_high_more_at_strong_advantage(monkeypatch):
    captured = {}
    def fake_choices(population, weights=None, k=1):
        captured["weights"] = weights
        return [population[0]]
    monkeypatch.setattr(svc.random, "choices", fake_choices)
    svc.resolve_quality(0.80)
    assert captured["weights"] == [0.05, 0.20, 0.50, 0.25]
    svc.resolve_quality(0.20)
    assert captured["weights"] == [0.55, 0.35, 0.09, 0.01]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'weighted_pick'`

- [ ] **Step 3: Implement duelist selection and duel bands**

```python
# Append imports at the top of backend/app/services/club_tactical_matchup_service.py
from app.services.club_tactical_profile_service import position_fit, zone_weight

# --- Player selection (spec §6.6) ------------------------------------------


def weighted_pick(cards: list[Any], zone: str, exclude_ids: frozenset = frozenset()) -> Any:
    """Among the given cards, picks one at random with probability
    proportional to its position's zone_weight for `zone` — the same
    "weighted-pick, not uniform-random" idea tournament_match_engine._pick_actor
    already uses for shot moments today, zone-scoped instead of category-scoped
    (spec §6.6). Falls back to a uniform pick among all non-excluded cards if
    none has any weight for this zone (mirrors _pick_actor's own fallback
    shape) — should only happen for a near-empty candidate list in tests."""
    candidates = []
    weights = []
    for card in cards:
        if card.id in exclude_ids:
            continue
        weight = zone_weight(card.player.position, zone)
        if weight > 0:
            candidates.append(card)
            weights.append(weight)
    if not candidates:
        candidates = [c for c in cards if c.id not in exclude_ids]
        weights = [1.0] * len(candidates)
    return random.choices(candidates, weights=weights, k=1)[0]


def zone_ratio(attacker: Any, attacker_zone: str, defender: Any, defender_zone: str) -> float:
    eff_attacker = attacker.player.rating * position_fit(attacker.player.position, attacker_zone)
    eff_defender = defender.player.rating * position_fit(defender.player.position, defender_zone)
    total = eff_attacker + eff_defender
    return eff_attacker / total if total else 0.5


# --- Duel bands (spec §6.3) -------------------------------------------------
# Each row is (lower_bound_exclusive, outcome_weights); rows are checked in
# order and the first `ratio > lower_bound` wins, so the final row's -1.0
# sentinel always matches (covers the "< 0.40" bucket without a special case).
STAGE1_BANDS: list[tuple[float, tuple[float, float, float]]] = [
    (0.75, (0.10, 0.25, 0.65)),   # breakdown, stall, advance
    (0.60, (0.18, 0.35, 0.47)),
    (0.40, (0.30, 0.45, 0.25)),
    (-1.0, (0.45, 0.35, 0.20)),
]
STAGE2_BANDS: list[tuple[float, tuple[float, float, float, float]]] = [
    (0.75, (0.05, 0.20, 0.50, 0.25)),   # LOW, NORMAL, HIGH, VERY_HIGH
    (0.60, (0.15, 0.35, 0.38, 0.12)),
    (0.40, (0.25, 0.50, 0.22, 0.03)),
    (-1.0, (0.55, 0.35, 0.09, 0.01)),
]


def _band(value: float, bands: list[tuple[float, tuple]]) -> tuple:
    for lower_bound, outcome in bands:
        if value > lower_bound:
            return outcome
    return bands[-1][1]


def resolve_stage1(ratio: float) -> str:
    breakdown, stall, advance = _band(ratio, STAGE1_BANDS)
    return random.choices(["breakdown", "stall", "advance"], weights=[breakdown, stall, advance], k=1)[0]


def resolve_quality(combined_advantage: float) -> str:
    low, normal, high, very_high = _band(combined_advantage, STAGE2_BANDS)
    return random.choices(["LOW", "NORMAL", "HIGH", "VERY_HIGH"], weights=[low, normal, high, very_high], k=1)[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_matchup_service.py tests/test_club_tactical_matchup_service.py
git commit -m "feat(clubs): add weighted duelist selection and Stage1/Stage2 duel bands"
```

---

### Task 7: Effective defensive pool

**Files:**
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py` (extend)

**Interfaces:**
- Produces: `defensive_pool(cards: list[Any], mentality: str, playstyle: str) -> list[Any]`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_tactical_matchup_service.py
def _back_line(n: int, start_id: int = 1) -> list[_FakeCard]:
    return [_FakeCard(start_id + i, _FakePlayer(Position.CB, 70)) for i in range(n)]


def test_park_the_bus_keeps_the_full_back_line_eligible():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "PARK_THE_BUS", "CENTRAL_PLAY")
    assert len(pool) == 4


def test_attacking_shrinks_the_pool_below_the_full_back_line():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    assert len(pool) < 4
    assert len(pool) >= 1


def test_high_press_shrinks_the_pool_further_than_the_same_mentality_without_it():
    cards = _back_line(10)
    without_press = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    with_press = svc.defensive_pool(cards, "ATTACKING", "HIGH_PRESS")
    assert len(with_press) <= len(without_press)


def test_defensive_pool_never_drops_below_one():
    cards = _back_line(1)
    pool = svc.defensive_pool(cards, "ATTACKING", "HIGH_PRESS")
    assert len(pool) == 1


def test_defensive_pool_is_drawn_from_real_unmodified_ratings():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    for card in pool:
        assert card.player.rating == 70  # never adjusted, per spec §6.4
        assert card in cards
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -k defensive_pool -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'defensive_pool'`

- [ ] **Step 3: Implement the effective defensive pool**

```python
# Append to backend/app/services/club_tactical_matchup_service.py

def defensive_pool(cards: list[Any], mentality: str, playstyle: str) -> list[Any]:
    """Spec §6.4: a transition moment's defensive duelist is drawn from a
    mentality-sized random SUBSET of the team's real defensive-zone
    contributors, re-rolled fresh every call — never from a rating-adjusted
    version of the back line. "Defensive-zone contributors" = anyone with
    nonzero central_defence or wing_defence weight (CB/LB/RB/CDM, plus GK's
    small 0.15 sliver — rarely picked in practice since weighted_pick still
    weights by that same small value)."""
    contributors = [c for c in cards if zone_weight(c.player.position, "central_defence") > 0 or zone_weight(c.player.position, "wing_defence") > 0]
    if not contributors:
        return []

    fraction = SAMPLE_FRACTION[mentality]
    if playstyle == "HIGH_PRESS":
        fraction *= HIGH_PRESS_POOL_MULT

    pool_size = max(1, round(fraction * len(contributors)))
    pool_size = min(pool_size, len(contributors))
    return random.sample(contributors, pool_size)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_matchup_service.py tests/test_club_tactical_matchup_service.py
git commit -m "feat(clubs): add mentality-sized effective defensive pool sampling"
```

---

### Task 8: Counter-attack chain

**Files:**
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py` (extend)

**Interfaces:**
- Consumes: `TRANSITION_BONUS`, `defensive_pool`, `weighted_pick`, `zone_ratio`/`position_fit`, `resolve_stage1`, `resolve_quality`.
- Produces: `@dataclass ClubTacticalSide(cards: list[Any], profile: TeamTacticalProfile, mentality: str, playstyle: str)`, `_first_pass_quality_factor(midfield_control: float) -> float`, `resolve_counter(attacking_side_label: str, y: ClubTacticalSide, x: ClubTacticalSide) -> tuple[str, float] | None` returning `(quality_or_"CLEAN_BREAKAWAY", combined_advantage)` or `None` on a stall/re-breakdown.

**Note on the worked example (spec §6.5):** this task's tests directly reproduce the spec's own "weak CB vs elite ST under PARK_THE_BUS" check — a bus squad's defenders must keep losing to elite attackers even though the pool stays full, because `defensive_pool` (Task 7) only changes *which* real defender is eligible, never their rating.

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_tactical_matchup_service.py
from app.services.club_tactical_profile_service import TeamTacticalProfile as _TTP


def _side(cards, mentality="BALANCED", playstyle="CENTRAL_PLAY", midfield_control=70) -> "svc.ClubTacticalSide":
    profile = _TTP(central_attack=70, wing_attack=70, midfield_control=midfield_control, central_defence=70, wing_defence=70, goalkeeping=70, team_strength=700)
    return svc.ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle)


def test_first_pass_quality_factor_increases_with_midfield_control():
    assert svc._first_pass_quality_factor(90) > svc._first_pass_quality_factor(60)


def test_resolve_counter_strongly_favors_elite_attacker_against_weak_bus_defence():
    elite_forwards = [
        _FakeCard(1, _FakePlayer(Position.ST, 95)), _FakeCard(2, _FakePlayer(Position.LW, 93)), _FakeCard(3, _FakePlayer(Position.RW, 94)),
        _FakeCard(4, _FakePlayer(Position.CM, 80)),
    ]
    weak_defenders = [_FakeCard(10 + i, _FakePlayer(Position.CB, 65)) for i in range(4)]

    y = _side(elite_forwards, mentality="ATTACKING", playstyle="COUNTER_ATTACK")  # Y just won the ball, now counters
    x = _side(weak_defenders, mentality="PARK_THE_BUS", playstyle="BALANCED")     # X is the bus side conceding the counter

    # A ~95-rated forward (boosted by COUNTER_ATTACK's 1.5x transition bonus)
    # against a genuinely 65-rated defender lands the duel's zone_ratio around
    # 0.6-0.65 — comfortably in STAGE1_BANDS' "0.60-0.75" bucket, not the top
    # ">0.75" one, since the defender's rating is never reduced (spec §6.5's
    # whole point: PARK_THE_BUS keeps the full pool eligible, but every
    # member of it stays genuinely weak). Assert on the duel's own ratio and,
    # among transitions that actually advance, the quality skew — not a flat
    # "most of all trials are high quality", since many phases legitimately
    # stall or get won back before any shot chance exists at all.
    trials = 300
    ratios = []
    advanced = 0
    high_or_very_high = 0
    for _ in range(trials):
        outcome = svc.resolve_counter("a", y, x)
        if outcome is not None:
            advanced += 1
            quality, ratio = outcome
            ratios.append(ratio)
            if quality in ("HIGH", "VERY_HIGH", "CLEAN_BREAKAWAY"):
                high_or_very_high += 1

    assert advanced > 0
    assert sum(ratios) / len(ratios) > 0.55  # the duel itself consistently favors Y's elite forwards
    assert high_or_very_high / advanced > 0.40  # among successful transitions, quality skews toward HIGH/VERY_HIGH


def test_resolve_counter_returns_none_on_a_stalled_or_re_broken_transition(monkeypatch):
    monkeypatch.setattr(svc, "resolve_stage1", lambda ratio: "stall")
    y = _side([_FakeCard(1, _FakePlayer(Position.ST, 80))])
    x = _side([_FakeCard(2, _FakePlayer(Position.CB, 80))])
    assert svc.resolve_counter("a", y, x) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -k "counter or first_pass" -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'ClubTacticalSide'`

- [ ] **Step 3: Implement the counter-attack chain**

```python
# Append to backend/app/services/club_tactical_matchup_service.py
# (dataclass already imported at the top of this module — Task 5's Step 3)

@dataclass
class ClubTacticalSide:
    cards: list[Any]
    profile: TeamTacticalProfile
    mentality: str
    playstyle: str


def _first_pass_quality_factor(midfield_control: float) -> float:
    """A weak outlet pass caps how dangerous a counter can be, even with elite
    forwards waiting (spec §6.5). Scaled around 70 (a "solid" personal-engine
    midfielder rating) so an average midfield neither boosts nor caps the
    counter (factor 1.0), while a genuinely weak one (~58, the engine's rating
    floor) meaningfully blunts it and a genuinely elite one (~99) sharpens it."""
    return max(0.7, min(1.15, 0.7 + (midfield_control - 58) / (99 - 58) * 0.45))


def resolve_counter(attacking_side_label: str, y: ClubTacticalSide, x: ClubTacticalSide) -> tuple[str, float] | None:
    """Spec §6.5: Y (the team that just won the Stage-1 duel) gets an
    immediate transition check against X's shrunk defensive pool (Task 7),
    resolved via the SAME picked-duelist mechanism as Stage 1/Stage 2 (Task
    6) — not a team-aggregate. Returns (quality_tier, combined_advantage) on
    a successful transition, or None if it stalls or the ball is win back
    immediately (no further recursive counter chain in Phase 1 — bounded
    scope, matches the "roughly 40-70 phases" budget instead of unbounded
    recursion)."""
    zone = random.choices(["central_attack", "wing_attack"], weights=[0.6, 0.4], k=1)[0]
    defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"

    y_duelist = weighted_pick(y.cards, zone)
    pool = defensive_pool(x.cards, x.mentality, x.playstyle)
    x_duelist = weighted_pick(pool, defence_zone)

    eff_y = y_duelist.player.rating * position_fit(y_duelist.player.position, zone) * TRANSITION_BONUS[y.playstyle] * _first_pass_quality_factor(y.profile.midfield_control)
    eff_x = x_duelist.player.rating * position_fit(x_duelist.player.position, defence_zone)
    total = eff_y + eff_x
    ratio = eff_y / total if total else 0.5

    outcome = resolve_stage1(ratio)
    if outcome != "advance":
        return None

    quality = resolve_quality(ratio)
    if quality == "VERY_HIGH" and len(pool) == 1:
        # Thinnest possible cover beaten decisively — the keeper-race
        # breakaway case _resolve_breakaway (Task 9) already handles.
        return "CLEAN_BREAKAWAY", ratio
    return quality, ratio
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (19 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_matchup_service.py tests/test_club_tactical_matchup_service.py
git commit -m "feat(clubs): add counter-attack chain reusing the picked-duelist mechanism"
```

---

### Task 9: Possession-phase orchestrator

**Files:**
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Test: `backend/tests/test_club_tactical_matchup_service.py` (extend)

**Interfaces:**
- Consumes: everything from Tasks 5–8, `club_tactical_profile_service.compute_profile`.
- Produces: `PLAYSTYLE_ZONE_WEIGHTS: dict[str, dict[str, float]]`, `pick_progression_zone(playstyle: str) -> str | None`, `possession_buildup_survives(midfield_control: float) -> bool`, `@dataclass Chance(attacking_side, minute, quality, shot_type, is_box, shooter, pass_target, defender)`, `build_side(cards_with_slots, mentality: str, playstyle: str) -> ClubTacticalSide`, `simulate_phase(minute, side_a, side_b, config) -> Chance | None`, `simulate_match_phases(side_a, side_b, config) -> list[Chance]`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_tactical_matchup_service.py
class _FakePhaseConfig:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def _full_squad(rating: int = 75) -> list[tuple[_FakeCard, object]]:
    """Pairs each fake card with a REAL FormationSlot from the 4-3-3 registry
    (Task 1) — compute_profile's team_strength field calls the existing
    calculate_base_strength(cards_with_slots), which reads slot.ideal_position
    and slot.category directly, so a None slot would crash there even though
    the zone math itself never touches slot."""
    from app.services.club_formation_service import get_formation_slots

    slots = get_formation_slots("4-3-3")
    return [(_FakeCard(i, _FakePlayer(slot.ideal_position, rating)), slot) for i, slot in enumerate(slots)]


def test_pick_progression_zone_returns_a_valid_zone_or_none():
    for playstyle in svc.PLAYSTYLES:
        for _ in range(30):
            zone = svc.pick_progression_zone(playstyle)
            assert zone in ("central_attack", "wing_attack", None)


def test_build_side_computes_a_real_profile():
    side = svc.build_side(_full_squad(), "BALANCED", "CENTRAL_PLAY")
    assert side.mentality == "BALANCED"
    assert side.profile.central_attack > 0


def test_simulate_match_phases_returns_a_bounded_list_of_chances():
    side_a = svc.build_side(_full_squad(), "BALANCED", "CENTRAL_PLAY")
    side_b = svc.build_side(_full_squad(rating=70), "BALANCED", "CENTRAL_PLAY")
    chances = svc.simulate_match_phases(side_a, side_b, _FakePhaseConfig())
    assert len(chances) <= _FakePhaseConfig.club_tactical_promoted_chance_target_max
    for chance in chances:
        assert chance.attacking_side in ("a", "b")
        assert chance.quality in ("LOW", "NORMAL", "HIGH", "VERY_HIGH")
        assert chance.shot_type in ("in_box", "long_range", "empty_net")


def test_much_stronger_side_produces_more_chances_than_a_much_weaker_one():
    # Deliberately no monkeypatching here: random.sample is used for TWO
    # different things in this module (minute selection in
    # simulate_match_phases AND pool sampling in defensive_pool), so a naive
    # blanket patch would corrupt defensive_pool's output. The rating/
    # mentality gap (95 ATTACKING vs 60 PARK_THE_BUS) skews both
    # initiative_probability and every duel ratio heavily enough that a
    # single real run, summed over several trials, is a reliable signal.
    # Playstyle is held constant (CENTRAL_PLAY) on both sides so mentality
    # and rating are the only varying factors — "DEFENSIVE" is a MENTALITY
    # value (already used on the mentality argument for consistency with
    # the "much weaker" framing), not a member of PLAYSTYLES, so it cannot
    # be passed as the playstyle argument here.
    side_a = svc.build_side(_full_squad(rating=95), "ATTACKING", "CENTRAL_PLAY")
    side_b = svc.build_side(_full_squad(rating=60), "PARK_THE_BUS", "CENTRAL_PLAY")

    a_total = b_total = 0
    for _ in range(10):
        chances = svc.simulate_match_phases(side_a, side_b, _FakePhaseConfig())
        a_total += sum(1 for c in chances if c.attacking_side == "a")
        b_total += sum(1 for c in chances if c.attacking_side == "b")
    assert a_total > b_total
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -k "phase or build_side or progression_zone" -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'pick_progression_zone'`

- [ ] **Step 3: Implement the orchestrator**

```python
# Append to backend/app/services/club_tactical_matchup_service.py
# (dataclass and field already imported at the top of this module — Task 5's Step 3)
from app.services.club_tactical_profile_service import compute_profile

# Verbatim shape from design spec §8's "Progression zone target (§6.2)"
# column, turned into concrete weights: "none" is the low-event/recycle
# outcome where this phase ends without reaching Stage 1 at all — folds
# spec's "rest low-event"/"~60% attempt progression at all" wording into one
# number per playstyle. HIGH_PRESS behaves like BALANCED in possession per
# spec §8 ("~BALANCED zone mix when in possession").
PLAYSTYLE_ZONE_WEIGHTS: dict[str, dict[str, float]] = {
    "WING_PLAY": {"wing_attack": 0.65, "central_attack": 0.25, "none": 0.10},
    "CENTRAL_PLAY": {"central_attack": 0.65, "wing_attack": 0.25, "none": 0.10},
    "POSSESSION": {"central_attack": 0.40, "wing_attack": 0.40, "none": 0.20},
    "HIGH_PRESS": {"central_attack": 0.45, "wing_attack": 0.45, "none": 0.10},
    "COUNTER_ATTACK": {"central_attack": 0.30, "wing_attack": 0.30, "none": 0.40},
}


def pick_progression_zone(playstyle: str) -> str | None:
    weights = PLAYSTYLE_ZONE_WEIGHTS[playstyle]
    zones = list(weights.keys())
    picked = random.choices(zones, weights=list(weights.values()), k=1)[0]
    return None if picked == "none" else picked


def possession_buildup_survives(midfield_control: float) -> bool:
    """POSSESSION's buildup gate (spec §8): "weak midfield → higher breakdown
    chance before even reaching §6.3". Scaled so a midfield_control of 70
    (this engine's typical "solid" rating) survives 60% of the time, rising
    to a 95%-capped ceiling for elite midfields and a 30%-floored chance for
    weak ones — never zero, since even a weak midfield occasionally strings
    passes together."""
    chance = min(0.95, max(0.30, (midfield_control - 40) / 50))
    return random.random() < chance


def _pick_shot_type(config) -> str:
    weights = [config.match_shot_type_in_box_weight, config.match_shot_type_long_range_weight]
    return random.choices(["in_box", "long_range"], weights=weights, k=1)[0]


def _card_to_actor(card: Any) -> dict:
    return {
        "club_card_id": card.id, "player_id": card.player_id, "name": card.player.display_name,
        "rating": card.player.rating, "position": card.player.position.value,
    }


@dataclass
class Chance:
    attacking_side: str
    minute: int
    quality: str
    shot_type: str
    is_box: bool
    shooter: dict = field(default_factory=dict)
    pass_target: dict = field(default_factory=dict)
    defender: dict = field(default_factory=dict)


def build_side(cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots)
    cards = [card for card, _slot in cards_with_slots]
    return ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle)


def _resolve_progression_and_duel(attacker: ClubTacticalSide, defender: ClubTacticalSide, attacking_side: str, minute: int, config) -> Chance | None:
    zone = pick_progression_zone(attacker.playstyle)
    if zone is None:
        return None
    if attacker.playstyle == "POSSESSION" and not possession_buildup_survives(attacker.profile.midfield_control):
        return None

    defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"
    attacker_duelist = weighted_pick(attacker.cards, zone)
    defender_duelist = weighted_pick(defender.cards, defence_zone)
    ratio_1 = zone_ratio(attacker_duelist, zone, defender_duelist, defence_zone)
    outcome_1 = resolve_stage1(ratio_1)

    if outcome_1 == "stall":
        return None
    if outcome_1 == "breakdown":
        defending_side_label = "b" if attacking_side == "a" else "a"
        result = resolve_counter(defending_side_label, defender, attacker)
        if result is None:
            return None
        quality, ratio = result
        if quality == "CLEAN_BREAKAWAY":
            return Chance(attacking_side=defending_side_label, minute=minute, quality="VERY_HIGH", shot_type="empty_net", is_box=False)
        counter_shot_type = _pick_shot_type(config)
        counter_shooter = weighted_pick(defender.cards, "central_attack")
        return Chance(
            attacking_side=defending_side_label, minute=minute, quality=quality, shot_type=counter_shot_type,
            is_box=(counter_shot_type == "in_box"),
            shooter=_card_to_actor(counter_shooter),
            pass_target=_card_to_actor(weighted_pick(defender.cards, "central_attack", exclude_ids=frozenset({counter_shooter.id}))),
            defender=_card_to_actor(weighted_pick(attacker.cards, "central_defence")),
        )

    # advance -> Stage 2 (spec §6.3)
    attacker_second = weighted_pick(attacker.cards, zone, exclude_ids=frozenset({attacker_duelist.id}))
    defender_second = weighted_pick(defender.cards, defence_zone, exclude_ids=frozenset({defender_duelist.id}))
    ratio_2 = zone_ratio(attacker_second, zone, defender_second, defence_zone)
    combined_advantage = (ratio_1 + ratio_2) / 2
    quality = resolve_quality(combined_advantage)
    shot_type = _pick_shot_type(config)
    return Chance(
        attacking_side=attacking_side, minute=minute, quality=quality, shot_type=shot_type, is_box=(shot_type == "in_box"),
        shooter=_card_to_actor(attacker_duelist), pass_target=_card_to_actor(attacker_second), defender=_card_to_actor(defender_second),
    )


def simulate_phase(minute: int, side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> Chance | None:
    p_a_initiative = initiative_probability(side_a.profile, side_a.mentality, side_b.profile, side_b.mentality)
    if random.random() < p_a_initiative:
        return _resolve_progression_and_duel(side_a, side_b, "a", minute, config)
    return _resolve_progression_and_duel(side_b, side_a, "b", minute, config)


def simulate_match_phases(side_a: ClubTacticalSide, side_b: ClubTacticalSide, config) -> list[Chance]:
    num_phases = random.randint(config.club_tactical_phases_per_match_min, config.club_tactical_phases_per_match_max)
    minutes = sorted(random.sample(range(1, 90), min(num_phases, 89)))

    chances: list[Chance] = []
    for minute in minutes:
        chance = simulate_phase(minute, side_a, side_b, config)
        if chance is not None:
            chances.append(chance)

    # Sanity-clip to the configured target ceiling (spec §12) — keeps match
    # length in the range players already see today; no minimum enforcement
    # in Phase 1 (would need re-rolling extra phases, deferred to Phase 3
    # tuning if the realized count ever runs low in practice).
    max_target = config.club_tactical_promoted_chance_target_max
    if len(chances) > max_target:
        chances = chances[:max_target]
    return chances
```

Note: the counter-chain's actors above deliberately draw fresh weighted picks for shooter/pass_target/defender rather than reusing `resolve_counter`'s internal duelists — `resolve_counter` (Task 8) intentionally returns only `(quality, ratio)`, keeping its role scoped to "does the counter succeed and how well" (matching its own task's tested interface) while `_resolve_progression_and_duel` here owns turning any successful outcome into concrete actors for the shot engine, consistent with this task owning "everything between who has the ball and who's taking the shot" (spec §2).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_tactical_matchup_service.py -v`
Expected: PASS (24 tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/club_tactical_matchup_service.py tests/test_club_tactical_matchup_service.py
git commit -m "feat(clubs): add possession-phase orchestrator producing a Chance list"
```

---

### Task 10: Refactor tournament_match_engine.py to consume the new Chance pipeline

**Files:**
- Modify: `backend/app/services/tournament_match_engine.py`
- Modify: `backend/tests/test_tournament_match_engine.py`

**Interfaces:**
- Consumes: `club_tactical_matchup_service.ClubTacticalSide`, `.simulate_match_phases`, `.Chance`.
- Produces: `QUALITY_BIAS: dict[str, float]`, `_resolve_shot_action(attacking_side, moment, config, quality_bias: float = 0) -> tuple[dict, str]` (signature change), `_resolve_defense_tackle(defending_side, moment, config) -> tuple[dict, str, tuple[int, str] | None]` (reads `moment["is_box"]` instead of `DEFENSE_SITUATIONS_BY_ID`), `simulate_match(side_a, side_b, lineup_a: list[dict], lineup_b: list[dict], config, club_a_name="Клуб A", club_b_name="Клуб B") -> MatchResult` (new signature). Deletes `generate_moment_queue`, `_build_shot_moment`, `_pick_actor`, `SHOT_TYPES`, `_FLAVOR_WEIGHTS`, `_SHOT_CHANCE_WEIGHT`, and the `match_situations` import.

**Design note (deviation from spec §6.7's literal wording, documented per this plan's Global Constraints):** the spec describes all four resolution functions gaining a `quality_bias` parameter. Only `_resolve_shot_action` actually reads a bias-like value today (`situation.bias`); `_resolve_defense_tackle`/`_resolve_breakaway`/`_resolve_shot_continuation` never did and have nothing to apply a bias to. Giving them an unused parameter would be dead code (violates this repo's YAGNI rule in `CLAUDE.md`). This task gives `quality_bias` only to `_resolve_shot_action`, and gives `_resolve_defense_tackle` the one substitute it actually needs — `moment["is_box"]` in place of the deleted `DEFENSE_SITUATIONS_BY_ID` lookup — which fulfills the same functional requirement (§6.7: "a chance's quality nudges the shot-resolution math the same way `situation.bias` did") without adding unused parameters elsewhere.

- [ ] **Step 1: Update the resolution function tests**

First, extend the existing `_FakeMatchConfig` class in `backend/tests/test_tournament_match_engine.py` with the tactical-pipeline config fields `simulate_match_phases` (Task 9) now reads — without these, every test in this file calling the new `engine.simulate_match(...)` crashes with `AttributeError: 'match_shot_type_in_box_weight'`-... no, `AttributeError: club_tactical_phases_per_match_min`, since the class currently only carries the shot-type/miss-chance fields from before this feature:

```python
# backend/tests/test_tournament_match_engine.py — add to the existing _FakeMatchConfig class body:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
```

Then replace the two situation-dependent tests in `backend/tests/test_tournament_match_engine.py` (`test_resolve_shot_action_follows_default_shoot_pass_policy_by_bias` and the `_hand_built_moment` helper it uses) — the new `_resolve_shot_action` no longer reads `moment["situation_id"]` at all:

```python
# Replace _hand_built_moment and test_resolve_shot_action_follows_default_shoot_pass_policy_by_bias
# in backend/tests/test_tournament_match_engine.py with:
def _hand_built_moment(shot_type: str = "in_box") -> dict:
    return {
        "minute": 10,
        "shot_type": shot_type,
        "is_box": shot_type == "in_box",
        "actors": {
            "shooter": {"club_card_id": 1, "player_id": 1, "name": "Shooter", "rating": 75, "position": "ST"},
            "pass_target": {"club_card_id": 2, "player_id": 2, "name": "PassTarget", "rating": 75, "position": "CAM"},
            "defender": {"club_card_id": 3, "player_id": 3, "name": "Defender", "rating": 75, "position": "CB"},
        },
    }


def test_resolve_shot_action_shoots_on_non_negative_quality_bias_and_passes_otherwise():
    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig(), quality_bias=5)
    assert event["payload"]["action"] == "shoot"

    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig(), quality_bias=-6)
    assert event["payload"]["action"] == "pass"


def test_resolve_shot_action_defaults_quality_bias_to_zero_which_shoots():
    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig())
    assert event["payload"]["action"] == "shoot"
```

Also add new tests for the refactored `simulate_match` entry point and `_resolve_defense_tackle`'s `is_box` handling:

```python
# Append to backend/tests/test_tournament_match_engine.py
from app.services.club_tactical_matchup_service import ClubTacticalSide, build_side
from app.services.club_tactical_profile_service import TeamTacticalProfile


def _fake_side(rating: int = 75, mentality: str = "BALANCED", playstyle: str = "CENTRAL_PLAY") -> ClubTacticalSide:
    from dataclasses import dataclass as _dc

    @_dc
    class _P:
        position: object
        rating: int
        display_name: str = "Test Player"  # _card_to_actor reads this

    @_dc
    class _C:
        id: int
        player: _P
        player_id: int = 0  # _card_to_actor reads this

    from app.models.enums import Position
    from app.services.club_formation_service import get_formation_slots

    # Paired with REAL FormationSlot objects (not None) — compute_profile's
    # team_strength field calls calculate_base_strength(cards_with_slots),
    # which reads slot.ideal_position/slot.category directly.
    slots = get_formation_slots("4-3-3")
    cards_with_slots = [(_C(id=100 + i, player_id=100 + i, player=_P(position=slot.ideal_position, rating=rating)), slot) for i, slot in enumerate(slots)]
    return build_side(cards_with_slots, mentality, playstyle)


def test_resolve_defense_tackle_reads_is_box_from_the_moment():
    # _resolve_defense_tackle's body reads moment["shot_type"] unconditionally
    # (for its event payloads) alongside moment["is_box"] — both keys required.
    moment = {"minute": 10, "shot_type": "in_box", "is_box": True, "actors": {"defender": {"club_card_id": 3, "player_id": 3, "name": "D", "rating": 60, "position": "CB"}}}
    event, _scorer, _card = engine._resolve_defense_tackle("a", moment, _FakeMatchConfig())
    assert event["event_type"] in ("tackle_won", "goal", "save", "foul_stopped")


def test_simulate_match_with_tactical_sides_produces_a_valid_result():
    side_a, side_b = _fake_side(), _fake_side(rating=70)
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 70, "position": "ST", "category": "FWD"} for i in range(11)]

    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig())
    assert result.score_a >= 0 and result.score_b >= 0
    for event in result.event_log:
        assert event["description"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_tournament_match_engine.py -v`
Expected: FAIL — old tests referencing `ATTACK_SITUATIONS_BY_ID`/`generate_moment_queue`/old `simulate_match` signature error out; new tests fail with `TypeError`/`AttributeError`.

- [ ] **Step 3: Refactor the engine**

Remove these from `backend/app/services/tournament_match_engine.py`: the `from app.services.match_situations import (...)` block, `SHOT_TYPES`, `_FLAVOR_WEIGHTS`, `_SHOT_CHANCE_WEIGHT`, `_pick_actor`, `_build_shot_moment`, `generate_moment_queue`, and the old `simulate_match`.

Add near the top (after `_EVENT_DESCRIPTIONS`/`_describe_event`, before the resolution section):

```python
from app.services import club_tactical_matchup_service

# Maps a Chance's quality tier (club_tactical_matchup_service.Chance.quality)
# onto the same units situation.bias used to nudge effective rating in the
# old engine (spec §6.7).
QUALITY_BIAS: dict[str, float] = {"LOW": -6, "NORMAL": 0, "HIGH": 5, "VERY_HIGH": 10}
```

Replace `_resolve_shot_action` with:

```python
def _resolve_shot_action(attacking_side: str, moment: dict, config, quality_bias: float = 0) -> tuple[dict, str]:
    """Shoots when quality_bias is non-negative (a clear chance), passes
    otherwise — same shoot/pass split the old situation.bias-driven policy
    used, now driven by the tactical pipeline's resolved chance quality
    instead of a scripted ATTACK_SITUATIONS template (spec §6.7)."""
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    defender = moment["actors"]["defender"]
    shot_type = moment["shot_type"]

    action = "shoot" if quality_bias >= 0 else "pass"
    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + quality_bias)
        missed = random.random() < _lerp_chance(eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max))
        scorer = shooter
    else:
        eff_passer_rating = _clamp_rating(shooter["rating"] - quality_bias)
        pass_failed = random.random() < _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max))
        if pass_failed:
            event = {
                "minute": moment["minute"], "event_type": "pass_failed", "team": attacking_side,
                "payload": {"shot_type": shot_type, "action": "pass", "passer": shooter["name"]},
            }
            return event, "none"
        missed = random.random() < _lerp_chance(pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max))
        scorer = pass_target

    outcome, extra = _resolve_shot_continuation(missed, shot_type, config, blocker_rating=defender["rating"], keeper_rating=defender["rating"])
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": {"shot_type": shot_type, "action": action, "shooter": scorer["name"], **extra},
    }
    return event, (attacking_side if outcome == "goal" else "none")
```

In `_resolve_defense_tackle`, replace the `defense_situation = DEFENSE_SITUATIONS_BY_ID[moment["defense_situation_id"]]` line and the `if "box" in defense_situation.tags:` check with:

```python
    is_box = moment["is_box"]
    ...
    if is_box:
```

(the rest of the function body is unchanged — only the source of the box/non-box branch changes).

Replace the old `simulate_match` with:

```python
def simulate_match(
    side_a: "club_tactical_matchup_service.ClubTacticalSide", side_b: "club_tactical_matchup_service.ClubTacticalSide",
    lineup_a: list[dict], lineup_b: list[dict], config,
    club_a_name: str = "Клуб A", club_b_name: str = "Клуб B",
) -> "MatchResult":
    """Replaces the old strength-driven random moment queue: chances now come
    from club_tactical_matchup_service's possession-phase pipeline (spec §6),
    already carrying a resolved quality tier and real picked duelists.
    lineup_a/lineup_b (the plain category-tagged actor dicts
    tournament_simulation_service.resolve_match_lineup already produces) are
    still needed for _resolve_breakaway's unchanged fwd_candidates lookup on
    a clean-breakaway chance."""
    chances = club_tactical_matchup_service.simulate_match_phases(side_a, side_b, config)

    result = MatchResult(score_a=0, score_b=0)
    for chance in chances:
        attacking_side = chance.attacking_side
        defending_side = "b" if attacking_side == "a" else "a"

        if chance.shot_type == "empty_net":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            moment = {"minute": chance.minute}
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
            if scorer != "none":
                setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
            continue

        moment = {
            "minute": chance.minute, "shot_type": chance.shot_type, "is_box": chance.is_box,
            "actors": {"shooter": chance.shooter, "pass_target": chance.pass_target, "defender": chance.defender},
        }
        quality_bias = QUALITY_BIAS[chance.quality]
        event, scorer = _resolve_shot_action(attacking_side, moment, config, quality_bias)
        result.event_log.append(event)
        event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
        if scorer != "none":
            setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)

        if event["event_type"] in ("blocked", "save") and random.random() < 0.15:
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            defense_event["description"] = _describe_event(defense_event["event_type"], defense_event["team"], club_a_name, club_b_name)
            if defense_scorer != "none":
                setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
            if card is not None:
                club_card_id, card_kind = card
                if card_kind == "red":
                    result.red_cards.append((club_card_id, 1))
                    if random.random() < 0.3:
                        result.injuries.append((club_card_id, random.randint(1, 3)))

    return result
```

Also delete the now-obsolete tests referencing deleted symbols in `backend/tests/test_tournament_match_engine.py`: `test_moment_queue_has_between_18_and_26_moments`, `test_shot_moments_pick_real_actors_from_both_sides`, `test_stronger_side_attacks_more_often`, `test_empty_net_shot_moment_has_no_actors_and_no_defense_situation_id`, and the old `test_simulate_match_produces_deterministic_score_from_event_log`/`test_simulate_match_records_red_card_and_injury_availability`/`test_simulate_match_events_carry_club_name_descriptions`/`test_simulate_match_default_club_names_when_omitted` (their `simulate_match(70, 70, lineup_a, lineup_b, config)` calls no longer match the new signature) — replace the four `simulate_match`-calling tests with tactical-side-based equivalents:

```python
# Replace the four simulate_match(...) tests in backend/tests/test_tournament_match_engine.py with:
def test_simulate_match_produces_a_deterministic_score_from_event_log(monkeypatch):
    # 0.99, not 0.0 — every _lerp_chance/_lerp_chance_positive threshold this
    # engine uses tops out around ~0.75 (match_keeper_save_chance_max), so
    # forcing random.random() to 0.99 makes every "random.random() < threshold"
    # check False, which is what drives every resolved chance to a goal
    # (missed=False, blocked=False, saved=False -> outcome="goal") — same
    # trick the pre-refactor version of this test used. random.random() is
    # shared process-wide (both this module's and club_tactical_matchup_service's
    # `import random` bind the same module object), so this also forces every
    # initiative check to go the same way — harmless here since the test only
    # asserts on goal-count consistency, not on which side attacks.
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)
    side_a, side_b = _fake_side(), _fake_side()
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig())
    goals_in_log = sum(1 for e in result.event_log if e["event_type"] == "goal")
    assert goals_in_log == result.score_a + result.score_b


def test_simulate_match_events_carry_real_club_name_descriptions():
    side_a, side_b = _fake_side(), _fake_side()
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig(), "Реал Мадрид", "Барселона")
    for event in result.event_log:
        assert isinstance(event["description"], str) and event["description"]
        club_name = "Реал Мадрид" if event["team"] == "a" else "Барселона"
        assert club_name in event["description"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_tournament_match_engine.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite to check nothing else broke**

Run: `cd backend && pytest tests/ -v`
Expected: only `test_tournament_simulation_service.py`/`test_tournament_simulation_lineup.py` (Task 12) should still be failing at this point, from `resolve_match_lineup`/`match_strength`/`simulate_next_round` still calling the deleted old `simulate_match` shape — everything else passes.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/tournament_match_engine.py tests/test_tournament_match_engine.py
git commit -m "refactor(clubs): consume the tactical Chance pipeline in tournament_match_engine"
```

---

### Task 11: Club-owned formation on lineup display/edit + PUT /clubs/me/tactics

**Files:**
- Modify: `backend/app/services/club_squad_service.py`
- Modify: `backend/app/schemas/club_squad.py`
- Modify: `backend/app/routers/clubs.py`
- Modify: `backend/tests/test_club_squad.py`

**Interfaces:**
- Consumes: `club_formation_service.get_formation_slots/get_slots_by_code/CLUB_FORMATIONS`, `club_tactical_profile_service.compute_profile/compute_tactical_fit`, `club_tactical_matchup_service.MENTALITIES/PLAYSTYLES`.
- Produces: `ClubLineupOut` gains `formation: str`, `mentality: str`, `playstyle: str`, `tactical_fit: int`; new `ClubTacticsSetRequest(formation: str, mentality: str, playstyle: str)`; new service function `set_club_tactics(db, user, payload: ClubTacticsSetRequest) -> ClubLineupOut`; new route `PUT /clubs/me/tactics`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to backend/tests/test_club_squad.py
async def test_get_club_lineup_reports_formation_mentality_playstyle_and_fit(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820320, "Клуб с тактикой в ответе")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert body["formation"] == "4-3-3"
    assert body["mentality"] == "BALANCED"
    assert body["playstyle"] == "CENTRAL_PLAY"
    assert 0 <= body["tactical_fit"] <= 100


async def test_set_club_tactics_updates_formation_mentality_playstyle(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820321, "Клуб меняет тактику")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-4-2", "mentality": "ATTACKING", "playstyle": "WING_PLAY"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["formation"] == "4-4-2"
    assert body["mentality"] == "ATTACKING"
    assert body["playstyle"] == "WING_PLAY"
    assert len(body["slots"]) == 10  # 4-4-2 has 10 outfield-plus-GK... wait: GK+4+4+2 = 11
```

Correct the slot-count assertion (4-4-2 has 11 slots total, same as every formation):

```python
    assert len(body["slots"]) == 11
```

```python
async def test_set_club_tactics_rejects_unknown_formation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820322, "Клуб с плохой тактикой")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-2-4", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 409


async def test_set_club_tactics_rejects_unknown_mentality(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820323, "Клуб с плохим настроем")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-3-3", "mentality": "BERSERK", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 409


async def test_set_club_tactics_non_manager_forbidden(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820324, "Клуб с рядовым участником")
    await _register_only(client, bot_token, 820325)
    member_headers = telegram_headers(820325, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=member_headers,
        json={"formation": "4-4-2", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 403


async def test_changing_formation_clears_slots_not_present_in_the_new_formation_and_keeps_shared_ones(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820326, "Клуб меняет формацию")
    before = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()
    gk_card_id_before = next(s["card"]["id"] for s in before["slots"] if s["slot_code"] == "GK")

    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-4-2", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    body = resp.json()
    # 4-3-3's slot codes are GK,DEF1-4,MID1-3,FWD1-3; 4-4-2's are
    # GK,DEF1-4,MID1-4,FWD1-2 — only FWD3 exists in 4-3-3 but not 4-4-2 (its
    # card gets freed to the bench), and only MID4 exists in 4-4-2 but not
    # 4-3-3 (newly empty, nothing to free). Every other code is shared and
    # keeps its card. So exactly one slot goes from filled to missing.
    assert body["is_complete"] is False

    gk_slot = next(s for s in body["slots"] if s["slot_code"] == "GK")
    assert gk_slot["card"]["id"] == gk_card_id_before  # shared-code slot kept its card
    mid4_slot = next(s for s in body["slots"] if s["slot_code"] == "MID4")
    assert mid4_slot["card"] is None  # 4-3-3 never had a MID4 code to carry over

    cards_resp = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    freed_cards = [c for c in cards_resp if not c["is_in_lineup"]]
    # seed_starting_squad mints 4 bench cards on top of the 11 starters
    # (Task 1's fixture, unchanged by this feature); the formation switch
    # frees exactly one more (the card that was in FWD3) on top of those.
    assert len(freed_cards) == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_squad.py -k "tactics or formation_mentality" -v`
Expected: FAIL with 404s (no `/clubs/me/tactics` route yet) and `KeyError: 'formation'` on the lineup response.

- [ ] **Step 3: Update the schemas**

```python
# backend/app/schemas/club_squad.py — replace ClubLineupOut and add ClubTacticsSetRequest:
class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    slots: list[ClubLineupSlotOut]


class ClubTacticsSetRequest(BaseModel):
    formation: str
    mentality: str
    playstyle: str
```

- [ ] **Step 4: Make club_squad_service formation-aware and add set_club_tactics**

```python
# backend/app/services/club_squad_service.py — replace the lineup_service import and
# every FORMATION_SLOTS/SLOTS_BY_CODE usage:
from app.core.exceptions import ConflictError
from app.models.club_card import ClubCard
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubCardSource, Position
from app.models.player import Player
from app.models.user import User
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest, ClubLineupSlotOut, ClubTacticsSetRequest
from app.schemas.player import PlayerOut
from app.services.club_card_service import create_club_card
from app.services.club_formation_service import CLUB_FORMATIONS, DEFAULT_FORMATION, get_formation_slots, get_slots_by_code
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES
from app.services.club_tactical_profile_service import compute_profile, compute_tactical_fit
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, calculate_base_strength
```

Update `seed_starting_squad` to iterate the default formation's slots explicitly (same slot list as before, now sourced from the club-owned registry instead of the shared personal one):

```python
    for slot in get_formation_slots(DEFAULT_FORMATION):
```

(replaces `for slot in FORMATION_SLOTS:` — no other change in that function's body).

Update `_lineup_to_out` to read the club's own formation and compute Tactical Fit:

```python
async def _lineup_to_out(db: AsyncSession, club_id: int) -> ClubLineupOut:
    lineup = await _get_or_none_lineup(db, club_id)
    formation = lineup.formation if lineup else DEFAULT_FORMATION
    mentality = lineup.mentality if lineup else "BALANCED"
    playstyle = lineup.playstyle if lineup else "CENTRAL_PLAY"
    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards} if lineup else {}
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()

    slots = []
    cards_with_slots = []
    for slot in get_formation_slots(formation):
        card = by_slot.get(slot.code)
        slots.append(
            ClubLineupSlotOut(
                slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
                card=_club_card_to_out(card, in_lineup_ids) if card else None,
            )
        )
        if card:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(get_formation_slots(formation))
    team_strength = calculate_base_strength(cards_with_slots) if is_complete else None

    config = await get_config(db)
    profile = compute_profile(cards_with_slots) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, slots=slots,
    )
```

Update `set_club_lineup` to validate against the club's *current* formation instead of the shared module-level constants:

```python
async def set_club_lineup(db: AsyncSession, user: User, payload: ClubLineupSetRequest) -> ClubLineupOut:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    current_lineup = await _get_or_none_lineup(db, club_id)
    formation = current_lineup.formation if current_lineup else DEFAULT_FORMATION
    slots_by_code = get_slots_by_code(formation)

    slot_codes = [s.slot_code for s in payload.slots]
    if len(slot_codes) != len(set(slot_codes)):
        raise ConflictError("Один слот не может использоваться дважды")
    if any(code not in slots_by_code for code in slot_codes):
        raise ConflictError("Неизвестный слот состава")
    ...
```

(the rest of `set_club_lineup`'s body is unchanged except every reference to the old module-level `SLOTS_BY_CODE` becomes `slots_by_code`, computed above).

Add `set_club_tactics` at the end of the file:

```python
async def set_club_tactics(db: AsyncSession, user: User, payload: ClubTacticsSetRequest) -> ClubLineupOut:
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

    lineup_result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards)).with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    new_slot_codes = set(get_slots_by_code(payload.formation).keys())
    for lc in list(lineup.cards):
        if lc.slot_code not in new_slot_codes:
            await db.delete(lc)

    lineup.formation = payload.formation
    lineup.mentality = payload.mentality
    lineup.playstyle = payload.playstyle
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id)
```

- [ ] **Step 5: Add the route**

```python
# backend/app/routers/clubs.py — add ClubTacticsSetRequest to the club_squad import,
# and add a new route right after set_club_lineup:
@router.put("/me/tactics", response_model=ClubLineupOut)
async def set_club_tactics(payload: ClubTacticsSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.set_club_tactics(db, user, payload)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_club_squad.py -v`
Expected: PASS

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && pytest tests/ -v`
Expected: only Task 12's `tournament_simulation_service`/`tournament_simulation_lineup` tests still failing (they still call the deleted-shape `simulate_match`/`FORMATION_SLOTS`-only `resolve_match_lineup`).

- [ ] **Step 8: Commit**

```bash
cd backend && git add app/services/club_squad_service.py app/schemas/club_squad.py app/routers/clubs.py tests/test_club_squad.py
git commit -m "feat(clubs): add PUT /clubs/me/tactics and make lineup display formation-aware"
```

---

### Task 12: Wire tournament_simulation_service into the new engine

**Files:**
- Modify: `backend/app/services/tournament_simulation_service.py`
- Modify: `backend/tests/test_tournament_simulation_lineup.py`
- Modify: `backend/tests/test_tournament_simulation_service.py` (only if it directly exercises `match_strength`/`simulate_match` — verify during Step 1 and adjust call sites the same way as below)

**Interfaces:**
- Consumes: `club_formation_service.get_formation_slots`, `club_tactical_matchup_service.build_side/simulate_match_phases`, `tournament_match_engine.simulate_match` (new signature, Task 10).
- Produces: `resolve_match_lineup(db, club_id) -> tuple[list[dict], bool, list[tuple[ClubCard, FormationSlot]], ClubLineup]` (return arity changes from 3 to 4 — adds the `ClubLineup` row itself so its `.mentality`/`.playstyle` are available without a second fetch). `match_strength` no longer applies `SUBSTITUTION_PENALTY`. `SUBSTITUTION_PENALTY` constant is deleted.

- [ ] **Step 1: Update the existing tests for the new return arity and call site**

```python
# backend/tests/test_tournament_simulation_lineup.py — update the three call sites:
async def test_resolve_match_lineup_returns_engine_shape(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, had_sub, cards_with_slots, club_lineup = await resolve_match_lineup(db_session, club.id)
    assert len(lineup) == 11
    assert had_sub is False
    assert len(cards_with_slots) == 11
    assert club_lineup.formation == "4-3-3"
    for card, slot in cards_with_slots:
        assert card.id in {c["club_card_id"] for c in lineup}
        assert slot.code in {"GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "FWD1", "FWD2", "FWD3"}
    for c in lineup:
        assert set(c.keys()) >= {"club_card_id", "player_id", "name", "rating", "position", "category"}


async def test_resolve_match_lineup_substitutes_suspended_card(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, _, _, _ = await resolve_match_lineup(db_session, club.id)
    suspended_card_id = lineup[0]["club_card_id"]
    db_session.add(ClubCardAvailability(club_card_id=suspended_card_id, rounds_remaining=2))
    await db_session.commit()

    new_lineup, had_sub, cards_with_slots, _club_lineup = await resolve_match_lineup(db_session, club.id)
    assert had_sub is True
    assert suspended_card_id not in {c["club_card_id"] for c in new_lineup}
    assert len(new_lineup) == 11
    assert len(cards_with_slots) == 11
    assert suspended_card_id not in {c.id for c, _ in cards_with_slots}
```

Add one new test confirming the substitution penalty is gone:

```python
async def test_match_strength_no_longer_applies_a_flat_substitution_penalty(db_session, seeded_club_with_full_squad):
    from app.services.game_config_service import get_config
    from app.services.tournament_simulation_service import match_strength
    from app.services.lineup_service import calculate_base_strength

    club, _captain = seeded_club_with_full_squad
    lineup, _, cards_with_slots, _club_lineup = await resolve_match_lineup(db_session, club.id)
    suspended_card_id = lineup[0]["club_card_id"]
    db_session.add(ClubCardAvailability(club_card_id=suspended_card_id, rounds_remaining=2))
    await db_session.commit()

    config = await get_config(db_session)
    strength, _lineup = await match_strength(db_session, club.id, config)
    _, _, post_sub_cards_with_slots, _ = await resolve_match_lineup(db_session, club.id)
    # Strength reflects the post-substitution squad directly — no extra 0.5x on top.
    assert strength == round(calculate_base_strength(post_sub_cards_with_slots) * 1.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_tournament_simulation_lineup.py -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 4, got 3)`.

- [ ] **Step 3: Rewire tournament_simulation_service.py**

```python
# backend/app/services/tournament_simulation_service.py — update imports:
from app.services import tournament_match_engine, tournament_notification_service
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot, calculate_base_strength
from app.services.tournament_fixture_service import generate_fixtures
from app.services.tournament_reward_service import conclude_tournament
from app.services.tournament_standing_service import apply_match_result
```

(drops `FORMATION_SLOTS`, no longer used; removes the `SUBSTITUTION_PENALTY = 0.5` module constant entirely.)

Update `resolve_match_lineup` to iterate the club's own formation and return the `ClubLineup` row:

```python
async def resolve_match_lineup(
    db: AsyncSession, club_id: int
) -> tuple[list[dict], bool, list[tuple[ClubCard, FormationSlot]], "ClubLineup | None"]:
    """Returns (engine-ready lineup list, had_substitution, cards_with_slots,
    club_lineup). Iterates the club's OWN formation (club_formation_service,
    via club_lineup.formation) instead of the shared personal-engine
    FORMATION_SLOTS — a club playing 4-4-2 must substitute into 4-4-2's slot
    set, not 4-3-3's. club_lineup is returned alongside so callers can read
    its mentality/playstyle without a second fetch."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return [], False, [], None

    formation_slots = get_formation_slots(lineup.formation)
    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards}
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}

    suspended_ids: set[int] = set()
    if lineup_card_ids:
        rows = (
            await db.execute(
                select(ClubCardAvailability.club_card_id)
                .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
            )
        ).scalars().all()
        suspended_ids = set(rows)

    bench_cards = (
        await db.execute(
            select(ClubCard).where(ClubCard.club_id == club_id, ClubCard.id.notin_(lineup_card_ids or [0]))
            .options(joinedload(ClubCard.player))
        )
    ).unique().scalars().all()

    used_bench_ids: set[int] = set()
    had_substitution = False
    result: list[dict] = []
    cards_with_slots: list[tuple[ClubCard, FormationSlot]] = []

    for slot in formation_slots:
        card = by_slot.get(slot.code)
        if card is None or card.id in suspended_ids:
            had_substitution = True
            candidates = [b for b in bench_cards if b.id not in used_bench_ids and b.player.position in CATEGORY_POSITIONS[slot.category]]
            if not candidates:
                candidates = [b for b in bench_cards if b.id not in used_bench_ids]
            if candidates:
                sub = random.choice(candidates)
                used_bench_ids.add(sub.id)
                result.append(_card_to_actor(sub, slot.category))
                cards_with_slots.append((sub, slot))
        else:
            result.append(_card_to_actor(card, slot.category))
            cards_with_slots.append((card, slot))

    return result, had_substitution, cards_with_slots, lineup
```

Update `match_strength` to drop the substitution penalty (form still applies, for UI purposes — the caller displaying `team_strength` still wants a form-adjusted number, even though the tactical engine itself no longer reads this return value for its own resolution):

```python
async def match_strength(db: AsyncSession, club_id: int, config) -> tuple[int, list[dict]]:
    """UI-facing team_strength only — no longer plumbed into match
    resolution (spec §5, §6.1): the tactical engine's initiative comes from
    TeamTacticalProfile.midfield_control × mentality instead. Substitution's
    effect is now emergent through the zones a weaker sub feeds, so no flat
    penalty is applied here any more."""
    lineup, _had_substitution, cards_with_slots, _club_lineup = await resolve_match_lineup(db, club_id)
    base = calculate_base_strength(cards_with_slots)
    multiplier = await form_multiplier(db, club_id, config)
    return max(1, round(base * multiplier)), lineup
```

Update `simulate_next_round`'s per-fixture simulation block to build tactical sides and call the new engine:

```python
            lineup_a, _had_sub_a, cards_with_slots_a, club_lineup_a = await resolve_match_lineup(db, club_a_id)
            lineup_b, _had_sub_b, cards_with_slots_b, club_lineup_b = await resolve_match_lineup(db, club_b_id)
            side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle)
            side_b = build_side(cards_with_slots_b, club_lineup_b.mentality, club_lineup_b.playstyle)
            engine_result = tournament_match_engine.simulate_match(
                side_a, side_b, lineup_a, lineup_b, config,
                club_names[club_a_id], club_names[club_b_id],
            )
```

(replaces the old `strength_a, lineup_a = await match_strength(...)` / `strength_b, lineup_b = await match_strength(...)` / `tournament_match_engine.simulate_match(strength_a, strength_b, lineup_a, lineup_b, config, ...)` block — `match_strength` is no longer called from this function at all, only `resolve_match_lineup` directly, since strength is UI-only now).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_tournament_simulation_lineup.py tests/test_tournament_simulation_service.py -v`
Expected: PASS. If `test_tournament_simulation_service.py` has any test asserting on the OLD strength-driven attack-probability skew (e.g. "stronger club scores more"), keep the assertion's *intent* (stronger club still favored) but drive the fixture's strength gap through rating differences on real seeded squads rather than a hand-constructed `strength_a`/`strength_b` pair, since those numbers are no longer accepted by `simulate_match`.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && pytest tests/ -v`
Expected: full PASS — every previously-passing club/tournament test (fixtures, standings, rewards, queue, notifications) is untouched by this task and should still be green.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/tournament_simulation_service.py tests/test_tournament_simulation_lineup.py tests/test_tournament_simulation_service.py
git commit -m "feat(clubs): drive tournament match simulation from TeamTacticalProfile, retire SUBSTITUTION_PENALTY"
```

---

### Task 13: Statistical balance assertions (spec §14, items 1–9, Phase 1 subset)

**Files:**
- Create: `backend/tests/test_club_tactical_balance.py`

This is not the Phase 3 tuning script (`backend/scripts/simulate_tactical_balance.py`, out of scope for this plan) — it is a small, fast, pytest-native set of statistical assertions over the pure `club_tactical_matchup_service` functions (no DB, no HTTP), matching spec §14's items 1, 2, 3, 4, 7, 8 (items 5/6 need COUNTER_ATTACK/HIGH_PRESS-vs-opponent framing already covered indirectly by item 4's mechanism reuse; item 9 — "existing mechanics keep passing" — is what Task 12's Step 5 full-suite run already verifies, not a new test here).

**Interfaces:**
- Consumes: `club_tactical_matchup_service.build_side/simulate_match_phases`, `club_tactical_profile_service`.

- [ ] **Step 1: Write the balance tests**

```python
# backend/tests/test_club_tactical_balance.py
from dataclasses import dataclass

from app.models.enums import Position
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side, simulate_match_phases


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"  # _card_to_actor reads this


@dataclass
class _FakeCard:
    id: int
    player_id: int
    player: _FakePlayer


class _Config:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def _squad(ratings: dict[Position, int], default: int = 75, formation: str = "4-3-3") -> list[tuple[_FakeCard, object]]:
    """Pairs each fake card with a REAL FormationSlot (not None) —
    compute_profile's team_strength field needs slot.ideal_position/
    slot.category, same reasoning as Task 9/10's equivalent fixtures."""
    slots = get_formation_slots(formation)
    cards = []
    for i, slot in enumerate(slots):
        rating = ratings.get(slot.ideal_position, default)
        cards.append((_FakeCard(id=i, player_id=i, player=_FakePlayer(slot.ideal_position, rating)), slot))
    return cards


def _chances_for(mentality_a, playstyle_a, ratings_a, mentality_b, playstyle_b, ratings_b, trials=40):
    a_total = b_total = 0
    quality_score = {"LOW": 1, "NORMAL": 2, "HIGH": 3, "VERY_HIGH": 4}
    a_quality_sum = b_quality_sum = 0
    for _ in range(trials):
        side_a = build_side(_squad(ratings_a), mentality_a, playstyle_a)
        side_b = build_side(_squad(ratings_b), mentality_b, playstyle_b)
        chances = simulate_match_phases(side_a, side_b, _Config())
        for c in chances:
            if c.attacking_side == "a":
                a_total += 1
                a_quality_sum += quality_score[c.quality]
            else:
                b_total += 1
                b_quality_sum += quality_score[c.quality]
    return a_total, a_quality_sum / a_total if a_total else 0, b_total, b_quality_sum / b_total if b_total else 0


# --- spec §14 item 1: two strong STs are better used under 4-4-2 than 4-3-3 ---
def test_two_strong_strikers_produce_higher_central_attack_in_4_4_2_than_4_3_3():
    from app.services.club_tactical_profile_service import compute_profile

    # 4-3-3 can only field one true ST (FWD2) — the second strong finisher
    # has to sit at LW instead, where its central_attack weight is only 0.65
    # (spec §5's table) instead of ST's full 1.00.
    squad_4_3_3 = _squad({Position.LW: 92, Position.ST: 92, Position.RW: 70}, formation="4-3-3")
    # 4-4-2 has two true ST slots, so both strong finishers get full weight.
    squad_4_4_2 = _squad({Position.ST: 92}, formation="4-4-2")

    assert compute_profile(squad_4_4_2).central_attack > compute_profile(squad_4_3_3).central_attack


# --- spec §14 item 4 (worked example): PARK_THE_BUS does not out-defend BALANCED for weak defenders ---
def test_park_the_bus_does_not_rescue_weak_defenders_against_elite_attackers():
    # Playstyle is held at CENTRAL_PLAY on the defending side in both calls —
    # "BALANCED" is a MENTALITY value, not a member of PLAYSTYLES, so it
    # cannot be passed as the playstyle argument (would KeyError inside
    # pick_progression_zone's PLAYSTYLE_ZONE_WEIGHTS[playstyle] lookup).
    # Mentality is the only varying factor between the two _chances_for calls.
    weak_def_ratings = {Position.CB: 64, Position.LB: 65, Position.RB: 66}
    elite_atk_ratings = {Position.ST: 95, Position.LW: 93, Position.RW: 94}

    bus_a, _bus_q, _bus_bt, bus_conceded_quality = _chances_for(
        "PARK_THE_BUS", "CENTRAL_PLAY", weak_def_ratings, "ATTACKING", "CENTRAL_PLAY", elite_atk_ratings,
    )
    balanced_a, _bal_q, _bal_bt, balanced_conceded_quality = _chances_for(
        "BALANCED", "CENTRAL_PLAY", weak_def_ratings, "ATTACKING", "CENTRAL_PLAY", elite_atk_ratings,
    )
    # PARK_THE_BUS must not produce a LOWER average conceded chance quality
    # than BALANCED by more than a token amount — the bus narrows exposure
    # (fewer total chances via low initiative) but the individual chances
    # that do get through remain just as dangerous, since defenders are
    # never rating-boosted (spec §6.5's worked check).
    assert balanced_conceded_quality - bus_conceded_quality < 0.5


# --- spec §14 item 7: a 70-rated squad does not beat a 95-rated squad even with a good tactical matchup ---
def test_much_weaker_squad_does_not_out_chance_a_much_stronger_one_even_with_a_good_matchup():
    # "DEFENSIVE" is a MENTALITY value, not a member of PLAYSTYLES — the
    # stronger side's playstyle here is CENTRAL_PLAY (a neutral choice,
    # isolating mentality+rating as the two variables under test).
    weak = {pos: 70 for pos in Position}
    strong = {pos: 95 for pos in Position}
    weak_total, _wq, strong_total, _sq = _chances_for(
        "ATTACKING", "COUNTER_ATTACK", weak, "PARK_THE_BUS", "CENTRAL_PLAY", strong,
    )
    assert strong_total >= weak_total


# --- spec §14 item 8: two identical squads simulate close to an even split ---
def test_identical_squads_on_identical_settings_split_close_to_even():
    ratings = {pos: 78 for pos in Position}
    a_total, _aq, b_total, _bq = _chances_for("BALANCED", "CENTRAL_PLAY", ratings, "BALANCED", "CENTRAL_PLAY", ratings, trials=60)
    total = a_total + b_total
    assert total > 0
    assert 0.35 < a_total / total < 0.65
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_club_tactical_balance.py -v`
Expected: FAIL (module doesn't exist yet) — after Steps 1's file is created they should run against the already-implemented Tasks 1–9 and mostly pass immediately; if `test_much_weaker_squad_does_not_out_chance_a_much_stronger_one_even_with_a_good_matchup` or the bus test is flaky/borderline, that is real signal about Task 6–9's default coefficients, not a test bug — do not loosen the assertion to force a pass; instead re-check the Stage 1/Stage 2 band values against spec §6.3 for a transcription error first.

- [ ] **Step 3: Run and confirm passing**

Run: `cd backend && pytest tests/test_club_tactical_balance.py -v`
Expected: PASS (5 tests). These are intentionally coarse statistical checks (spec §14's exhaustive 1000+-match tuning pass is Phase 3's `simulate_tactical_balance.py` script, not this file) — they exist to catch a genuinely broken direction (e.g. bus rescuing weak defenders, or a 70 beating a 95 outright), not to validate exact magnitudes.

- [ ] **Step 4: Commit**

```bash
cd backend && git add tests/test_club_tactical_balance.py
git commit -m "test(clubs): add coarse statistical balance checks for the tactical pipeline"
```

---

### Task 14: Minimal frontend picker (formation/mentality/playstyle) and types

Per spec §15's Phase 1 boundary: "no new UI beyond the minimum formation/mentality/playstyle picker needed to actually exercise the feature (bare-bones acceptable — polish is Phase 2)." This task adds exactly that — plain `<select>`s and a save button — not the segmented-control/Tactical-Fit-hint-line polish described in spec §11 (Phase 2).

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/clubSquad.ts`
- Create: `frontend/src/lib/clubTactics.ts`
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Produces: `ClubLineup` type gains `formation/mentality/playstyle/tactical_fit`; `setClubTactics(payload: {formation, mentality, playstyle}) -> Promise<ClubLineup>`; `FORMATIONS`, `MENTALITIES`, `PLAYSTYLES` label arrays in `lib/clubTactics.ts`.

- [ ] **Step 1: Update the ClubLineup type**

```typescript
// frontend/src/types/index.ts — replace the ClubLineup interface:
export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  slots: ClubLineupSlot[];
}
```

- [ ] **Step 2: Add the setClubTactics API call**

```typescript
// frontend/src/api/clubSquad.ts — add:
export async function setClubTactics(payload: { formation: string; mentality: string; playstyle: string }): Promise<ClubLineup> {
  const { data } = await api.put<ClubLineup>("/clubs/me/tactics", payload);
  return data;
}
```

- [ ] **Step 3: Add the club-only tactics registry (deliberately separate from `lib/formation.ts`, which drives the personal Card Arena lineup)**

```typescript
// frontend/src/lib/clubTactics.ts
export const FORMATIONS: { value: string; label: string }[] = [
  { value: "4-3-3", label: "4-3-3" },
  { value: "4-4-2", label: "4-4-2" },
  { value: "3-5-2", label: "3-5-2" },
  { value: "5-3-2", label: "5-3-2" },
];

export const MENTALITIES: { value: string; label: string }[] = [
  { value: "PARK_THE_BUS", label: "Автобус у ворот" },
  { value: "DEFENSIVE", label: "Оборонительный" },
  { value: "BALANCED", label: "Сбалансированный" },
  { value: "ATTACKING", label: "Атакующий" },
];

export const PLAYSTYLES: { value: string; label: string }[] = [
  { value: "WING_PLAY", label: "Игра флангами" },
  { value: "CENTRAL_PLAY", label: "Игра через центр" },
  { value: "POSSESSION", label: "Контроль мяча" },
  { value: "HIGH_PRESS", label: "Высокий прессинг" },
  { value: "COUNTER_ATTACK", label: "Контратаки" },
];
```

- [ ] **Step 4: Add the picker to ClubSquadPage.tsx**

```typescript
// frontend/src/pages/ClubSquadPage.tsx — add to the imports:
import { setClubTactics } from "@/api/clubSquad";
import { FORMATIONS, MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";
```

Add a mutation, right after `setLineupMutation`:

```typescript
  const setTacticsMutation = useMutation({
    mutationFn: setClubTactics,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "lineup"] }); queryClient.invalidateQueries({ queryKey: ["clubs", "cards"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить тактику")),
  });

  const updateTactics = (patch: Partial<{ formation: string; mentality: string; playstyle: string }>) => {
    if (!lineup) return;
    setTacticsMutation.mutate({ formation: lineup.formation, mentality: lineup.mentality, playstyle: lineup.playstyle, ...patch });
  };
```

Replace the hardcoded `"Состав 4-3-3"` header with the live formation, and add the three selects right below it:

```tsx
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав {lineup?.formation}</p>
          {lineup?.is_complete && <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>}
        </div>

        {canEdit && lineup && (
          <div className="mb-3 flex flex-col gap-2">
            <select
              value={lineup.formation}
              onChange={(e) => updateTactics({ formation: e.target.value })}
              disabled={setTacticsMutation.isPending}
              className="rounded-lg bg-white/5 px-2 py-1.5 text-xs text-ink-chalk"
            >
              {FORMATIONS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
            <select
              value={lineup.mentality}
              onChange={(e) => updateTactics({ mentality: e.target.value })}
              disabled={setTacticsMutation.isPending}
              className="rounded-lg bg-white/5 px-2 py-1.5 text-xs text-ink-chalk"
            >
              {MENTALITIES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <select
              value={lineup.playstyle}
              onChange={(e) => updateTactics({ playstyle: e.target.value })}
              disabled={setTacticsMutation.isPending}
              className="rounded-lg bg-white/5 px-2 py-1.5 text-xs text-ink-chalk"
            >
              {PLAYSTYLES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
        )}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS, no errors.

- [ ] **Step 6: Manual smoke test**

Start the dev environment (`docker compose up -d --build frontend backend` or the project's usual dev command) and, in the browser preview, open `/clubs/squad` as a club captain: confirm the three selects render with the club's current formation/mentality/playstyle, changing one triggers a `PUT /clubs/me/tactics` call (visible in the network tab) and the header/slots update to match the new formation (e.g. switching to 4-4-2 shows 11 slots with no `FWD3`/`MID3` codes and the previously-filled ones now empty).

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/types/index.ts src/api/clubSquad.ts src/lib/clubTactics.ts src/pages/ClubSquadPage.tsx
git commit -m "feat(clubs): add minimal formation/mentality/playstyle picker to the squad page"
```

---

## Post-plan checklist (do not skip)

- [ ] `cd backend && pytest tests/ -v` — full suite green.
- [ ] `cd backend && python -c "from app.main import app"` — startup sanity check.
- [ ] `cd backend && alembic upgrade head` against a real Postgres (via `docker compose exec backend alembic upgrade head`) — confirms migration 0082 applies cleanly; the `server_default`-only column adds should be instant even against production's ~40+ existing `club_lineups` rows.
- [ ] `cd frontend && npm run typecheck && npm run lint && npm run build` — all green.
- [ ] Manually verify one full simulated round (`docker compose exec backend python -c "..."` calling `tournament_simulation_service.simulate_next_round` against dev Postgres, or trigger it via the existing admin/queue flow) produces a plausible event log and a real, non-crashing score — row-level locking and the real Postgres substitution/availability path are not exercised by the SQLite test suite (per this repo's own noted limitation in `CLAUDE.md`).
- [ ] Confirm `git log --stat` for this feature touches no file under `match_service.py`'s personal-engine path and no file in `lineup_service.py` beyond imports.
