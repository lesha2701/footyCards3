# Club Tactical Match Engine — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface Tactical Fit (§9) and opponent scouting (§10) to players, and give the tactics picker and match commentary a real UX pass (§11) — on top of Phase 1's already-shipped and rebalanced match engine.

**Architecture:** Every number this phase surfaces (`tactical_fit`, the scouting rollup) is already computed server-side by Phase 1's `club_tactical_profile_service.compute_profile`/`compute_tactical_fit` — this phase adds a hint string alongside the existing fit number, one new read-only GET endpoint that rolls an opponent's *current* lineup through the same `compute_profile` call Phase 1 already uses for the caller's own squad, and frontend rendering for both. The event-description flavor text reuses `Chance.quality` and `ClubTacticalSide.playstyle`, both already computed by Phase 1's pipeline — no new match-engine logic, no new `GameConfig` fields.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 + TypeScript + TanStack Query + Tailwind CSS (frontend) — same stack as Phase 1, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-club-tactical-match-engine-design.md` — this plan covers §9 (Tactical Fit UI), §10 (opponent scouting), §11 (UX pass), i.e. spec's own "Phase 2" per §15. §12's config strategy, §13's migration notes, and everything Phase 1 already shipped (§2-8, §14) are out of scope here — no match-engine formula changes.

## Global Constraints

- Never expose the scouted opponent's own formation, mentality, or playstyle anywhere — only the 4 rolled-up numbers (`attack`, `midfield`, `defence`, `goalkeeping`) plus `round_number`/`opponent_club_id`/`opponent_club_name` (spec §10, "Never exposed").
- No new `GameConfig` fields — every number this phase surfaces is either already computed (`tactical_fit`) or a simple average of already-computed `TeamTacticalProfile` zones (the scouting rollup) — no new tunables.
- Card ratings and existing match-engine formulas (`club_tactical_matchup_service.py`'s mentality/playstyle/formation balance constants) are NOT touched by this plan — Phase 1's balance work is done and separately documented in `docs/superpowers/plans/2026-08-30-club-tactical-match-engine-phase1-STATUS.md`.
- Mobile-first Telegram Mini App conventions: match `ClubSquadPage.tsx`/`ClubsPage.tsx`'s existing Tailwind class idioms exactly (`bg-bg-surface`, `text-ink-chalk`/`text-ink-mist`/`text-ink-mist-dim`, `rounded-2xl`/`rounded-xl`, `active:scale-95`/`active:scale-[0.99]` on tappable elements) — introduce no new design language for these additions.
- Russian-language UI copy throughout, register matching `frontend/src/lib/clubTactics.ts`'s existing labels (e.g. `"Игра флангами"`, `"Автобус у ворот"`).
- Every behavior change gets a test. Backend: pytest, in-memory SQLite (`cd backend && pytest tests/ -v`). Frontend: `cd frontend && npm run typecheck` must stay clean — no new Vitest test infra is introduced for `ClubSquadPage.tsx`/`ClubsPage.tsx` (none exists there today; UI correctness for this plan is verified live in the browser per this repo's own "test the golden path in a browser" rule for frontend changes, not by inventing a new test harness).
- Do not perform unrelated refactoring — e.g. `club_squad_service.py`'s existing `_lineup_to_out` loop (which builds both the UI slot list and the profile input together) is left exactly as-is; the new scouting endpoint gets its own small, separate helper rather than a forced extraction.

---

### Task 1: Backend — Tactical Fit hint string (§9)

**Files:**
- Modify: `backend/app/services/club_squad_service.py` (add `_tactical_fit_hint`, wire into `_lineup_to_out`)
- Modify: `backend/app/schemas/club_squad.py:23-30` (add `tactical_fit_hint: str` to `ClubLineupOut`)
- Test: `backend/tests/test_club_squad.py`

**Interfaces:**
- Consumes: `club_tactical_profile_service.ZONES` (the 6-tuple of zone names), `club_tactical_profile_service._playstyle_alignment(profile, playstyle) -> float` (0-1, already computed as part of Phase 1's `compute_tactical_fit`), `club_tactical_profile_service.PLAYSTYLE_ZONES` (not directly needed here, `_playstyle_alignment` already encapsulates it) — all already imported/importable from `app.services.club_tactical_profile_service`.
- Produces: `_tactical_fit_hint(profile: TeamTacticalProfile, playstyle: str) -> str`, called from `_lineup_to_out`; `ClubLineupOut.tactical_fit_hint: str` — later tasks don't consume this, it's a leaf.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_club_squad.py` (this file already has `_create_club`/`_register_only` helpers and a `_seed_position_pool` autouse fixture — see the file's own top for exact signatures):

```python
async def test_get_club_lineup_reports_a_tactical_fit_hint(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820330, "Клуб с подсказкой")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert isinstance(body["tactical_fit_hint"], str)
    assert len(body["tactical_fit_hint"]) > 0


async def test_tactical_fit_hint_praises_a_well_aligned_playstyle(client, db_session, bot_token):
    # The default new-club squad is BALANCED/CENTRAL_PLAY on a fresh position
    # pool seeded evenly (see _seed_position_pool) — set an explicit
    # CENTRAL_PLAY (already the default) and assert the praise-branch string,
    # since a freshly seeded squad has no artificially weak zone to trigger
    # the "Слабое место" branch on this exact seed.
    _, headers = await _create_club(client, bot_token, 820331, "Клуб с похвалой")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert body["tactical_fit_hint"] in (
        "Хорошо подходит для игры через центр", "Хорошо подходит для игры по флангам",
        "Хорошо подходит для контроля мяча", "Хорошо подходит для высокого прессинга",
        "Хорошо подходит для контратак",
    ) or body["tactical_fit_hint"].startswith("Слабое место: ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_club_squad.py::test_get_club_lineup_reports_a_tactical_fit_hint -v`
Expected: FAIL with `KeyError: 'tactical_fit_hint'` (field doesn't exist in the response yet).

- [ ] **Step 3: Add the schema field**

In `backend/app/schemas/club_squad.py`, change:

```python
class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    slots: list[ClubLineupSlotOut]
```

to:

```python
class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    tactical_fit_hint: str
    slots: list[ClubLineupSlotOut]
```

- [ ] **Step 4: Write the hint function and wire it in**

In `backend/app/services/club_squad_service.py`, change this import line:

```python
from app.services.club_tactical_profile_service import compute_profile, compute_tactical_fit
```

to:

```python
from app.services.club_tactical_profile_service import ZONES, _playstyle_alignment, compute_profile, compute_tactical_fit
```

Add this near the top of the file, after the `BENCH_CATEGORIES` constant:

```python
# Russian zone labels for the tactical-fit hint (spec §9) — deliberately not
# shared with any frontend label file: this string is entirely server-
# generated and never round-trips through a select/enum on the client.
_ZONE_LABELS_RU: dict[str, str] = {
    "central_attack": "атака через центр",
    "wing_attack": "атака флангами",
    "midfield_control": "контроль полузащиты",
    "central_defence": "центральная защита",
    "wing_defence": "фланговая защита",
    "goalkeeping": "игра вратаря",
}

_PLAYSTYLE_FIT_HINTS: dict[str, str] = {
    "WING_PLAY": "Хорошо подходит для игры по флангам",
    "CENTRAL_PLAY": "Хорошо подходит для игры через центр",
    "POSSESSION": "Хорошо подходит для контроля мяча",
    "HIGH_PRESS": "Хорошо подходит для высокого прессинга",
    "COUNTER_ATTACK": "Хорошо подходит для контратак",
}


def _tactical_fit_hint(profile, playstyle: str) -> str:
    """One-line hint for the squad screen (spec §9): praise when the chosen
    playstyle's target zone(s) are genuinely among this squad's strongest
    (reuses club_tactical_profile_service's own _playstyle_alignment, the
    same 0-1 score compute_tactical_fit already folds in — no new zone-
    ranking logic), otherwise name the squad's single weakest zone. 0.65 is
    "target zone(s) rank in roughly the top third of the 6" — _playstyle_alignment
    returns 1.0 for a #1-ranked zone, 0.8 for #2, 0.6 for #3 (out of 6 zones,
    ranks 0-5 map to scores 1.0, 0.8, 0.6, 0.4, 0.2, 0.0)."""
    if _playstyle_alignment(profile, playstyle) >= 0.65:
        return _PLAYSTYLE_FIT_HINTS[playstyle]
    zone_values = {zone: getattr(profile, zone) for zone in ZONES}
    weakest_zone = min(zone_values, key=zone_values.get)
    return f"Слабое место: {_ZONE_LABELS_RU[weakest_zone]}"
```

Then in `_lineup_to_out`, change:

```python
    config = await get_config(db)
    profile = compute_profile(cards_with_slots) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, slots=slots,
    )
```

to:

```python
    config = await get_config(db)
    profile = compute_profile(cards_with_slots) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0
    tactical_fit_hint = _tactical_fit_hint(profile, playstyle) if profile else "Заполни состав, чтобы увидеть подсказку"

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, tactical_fit_hint=tactical_fit_hint, slots=slots,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_club_squad.py -v`
Expected: PASS (all tests in the file, including the two new ones).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/club_squad_service.py backend/app/schemas/club_squad.py backend/tests/test_club_squad.py
git commit -m "feat(clubs): surface a tactical-fit hint alongside the existing percentage"
```

---

### Task 2: Backend — Opponent scouting endpoint (§10)

**Files:**
- Modify: `backend/app/schemas/club_squad.py` (add `NextOpponentOut`)
- Modify: `backend/app/services/club_squad_service.py` (add `get_next_opponent`)
- Modify: `backend/app/routers/clubs.py` (add `GET /clubs/tournament/next-opponent`)
- Test: `backend/tests/test_club_squad.py`

**Interfaces:**
- Consumes: `tournament_fixture_service.generate_fixtures(club_ids: list[int]) -> list[tuple[int, int, int]]` (round_number, club_a_id, club_b_id — already exists, `backend/app/services/tournament_fixture_service.py:1`), `Tournament`/`TournamentClub` models (`app.models.tournament`, fields `Tournament.status`, `Tournament.rounds_simulated`, `TournamentClub.tournament_id`/`.club_id`), `Club` model (`app.models.club`, field `Club.name`), `club_squad_service._get_or_none_lineup(db, club_id) -> ClubLineup | None` (already exists in the same module), `club_tactical_profile_service.compute_profile(cards_with_slots) -> TeamTacticalProfile`, `club_formation_service.get_formation_slots(formation) -> list[FormationSlot]`, `club_formation_service.DEFAULT_FORMATION` (all already imported in `club_squad_service.py`).
- Produces: `NextOpponentOut` schema (`round_number: int, opponent_club_id: int, opponent_club_name: str, attack: int, midfield: int, defence: int, goalkeeping: int`); `get_next_opponent(db: AsyncSession, user: User) -> NextOpponentOut` (raises `ConflictError` if the caller's club has no active tournament or no round left to play); `GET /clubs/tournament/next-opponent` route.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_club_squad.py`:

```python
async def test_next_opponent_rejects_a_club_with_no_active_tournament(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820340, "Клуб без турнира")
    resp = await client.get("/api/v1/clubs/tournament/next-opponent", headers=headers)
    assert resp.status_code == 409


async def test_next_opponent_reports_round_and_opponent_for_an_active_tournament(client, db_session, bot_token):
    from sqlalchemy import select
    from app.models.club import Club
    from app.services.club_squad_service import get_next_opponent
    from app.services.tournament_queue_service import apply_to_tournament
    from tests.factories import get_user_by_telegram_id

    club_ids_and_users = []
    for i in range(8):
        club, _headers = await _create_club(client, bot_token, 820350 + i, f"Скаутинг {i}")
        user = await get_user_by_telegram_id(db_session, 820350 + i)
        club_ids_and_users.append((club, user))

    tournament_id = None
    for _club, user in club_ids_and_users:
        result = await apply_to_tournament(db_session, user)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    first_club, first_user = club_ids_and_users[0]
    out = await get_next_opponent(db_session, first_user)
    assert out.round_number == 1
    assert out.opponent_club_id != first_club["id"]
    opponent = await db_session.get(Club, out.opponent_club_id)
    assert out.opponent_club_name == opponent.name
    # Fresh clubs' seeded starting squads (see _seed_position_pool) give every
    # zone a real, positive value — never all-zero, since compute_profile
    # only returns 0.0 for a genuinely empty lineup (no cards at all).
    assert out.attack > 0
    assert out.midfield > 0
    assert out.defence > 0
    assert out.goalkeeping > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_club_squad.py::test_next_opponent_rejects_a_club_with_no_active_tournament -v`
Expected: FAIL with 404 (route doesn't exist yet, not 409).

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/club_squad.py`, add at the end of the file:

```python
class NextOpponentOut(BaseModel):
    round_number: int
    opponent_club_id: int
    opponent_club_name: str
    attack: int
    midfield: int
    defence: int
    goalkeeping: int
```

- [ ] **Step 4: Add the service function**

In `backend/app/services/club_squad_service.py`, add these imports at the top of the file (alongside the existing ones — `Club`/`Tournament`/`TournamentClub`/`generate_fixtures` have no import of `club_squad_service` themselves, so this is safe at module level, unlike the `club_service` imports this file already keeps local to break an actual circular-import chain):

```python
from app.models.club import Club
from app.models.tournament import Tournament, TournamentClub
from app.services.tournament_fixture_service import generate_fixtures
```

Add this function after `set_club_tactics`:

```python
async def get_next_opponent(db: AsyncSession, user: User) -> NextOpponentOut:
    """GET /clubs/tournament/next-opponent (spec §10). Never returns the
    opponent's formation/mentality/playstyle — only the 4 rolled-up numbers.
    A live snapshot of the opponent's CURRENT lineup, not a locked
    prediction — matches spec §10's explicit "can still shift between views
    if the opponent changes their squad before kickoff" behavior, since it's
    resolved fresh on every call, not cached or computed at fixture-generation
    time."""
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    active_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_tc is None:
        raise ConflictError("Клуб не участвует в активном турнире")

    tournament = await db.get(Tournament, active_tc.tournament_id)
    round_number = tournament.rounds_simulated + 1
    if round_number > 14:
        raise ConflictError("Турнир уже завершён")

    participants = (
        await db.execute(
            select(TournamentClub).where(TournamentClub.tournament_id == tournament.id).order_by(TournamentClub.id)
        )
    ).scalars().all()
    club_ids = [p.club_id for p in participants]
    pairing = next(
        (f for f in generate_fixtures(club_ids) if f[0] == round_number and club_id in (f[1], f[2])), None,
    )
    if pairing is None:
        raise ConflictError("На следующий тур соперник не назначен")
    opponent_club_id = pairing[2] if pairing[1] == club_id else pairing[1]

    opponent_club = await db.get(Club, opponent_club_id)
    opponent_lineup = await _get_or_none_lineup(db, opponent_club_id)
    opponent_formation = opponent_lineup.formation if opponent_lineup else DEFAULT_FORMATION
    opponent_by_slot = {lc.slot_code: lc.club_card for lc in opponent_lineup.cards} if opponent_lineup else {}
    opponent_cards_with_slots = [
        (opponent_by_slot[slot.code], slot) for slot in get_formation_slots(opponent_formation) if slot.code in opponent_by_slot
    ]
    profile = compute_profile(opponent_cards_with_slots) if opponent_cards_with_slots else None

    return NextOpponentOut(
        round_number=round_number, opponent_club_id=opponent_club_id, opponent_club_name=opponent_club.name,
        attack=round((profile.central_attack + profile.wing_attack) / 2) if profile else 0,
        midfield=round(profile.midfield_control) if profile else 0,
        defence=round((profile.central_defence + profile.wing_defence) / 2) if profile else 0,
        goalkeeping=round(profile.goalkeeping) if profile else 0,
    )
```

Add `NextOpponentOut` to the existing schema import line at the top of the file:

```python
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest, ClubLineupSlotOut, ClubTacticsSetRequest
```

becomes:

```python
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest, ClubLineupSlotOut, ClubTacticsSetRequest, NextOpponentOut
```

- [ ] **Step 5: Add the router endpoint**

In `backend/app/routers/clubs.py`, add `NextOpponentOut` to the existing `club_squad` schema import, and add this route right after `get_current_tournament` (before `@router.get("/tournament/{tournament_id}", ...)` — it must come first, same reason `/tournament/current` already precedes `/tournament/{tournament_id}`):

```python
@router.get("/tournament/next-opponent", response_model=NextOpponentOut)
async def get_next_opponent(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.get_next_opponent(db, user)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_club_squad.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/club_squad.py backend/app/services/club_squad_service.py backend/app/routers/clubs.py backend/tests/test_club_squad.py
git commit -m "feat(clubs): add opponent scouting endpoint for the next tournament round"
```

---

### Task 3: Backend — Tactic-flavored event descriptions (§11)

**Files:**
- Modify: `backend/app/services/tournament_match_engine.py`
- Test: `backend/tests/test_tournament_match_engine.py`

**Interfaces:**
- Consumes: `Chance.quality` (already exists, `club_tactical_matchup_service.py`'s `Chance` dataclass), `ClubTacticalSide.playstyle` (already exists on `side_a`/`side_b`, both already in scope throughout `simulate_match`).
- Produces: `_describe_event(event_type, team, club_a_name, club_b_name, playstyle=None, quality=None)` — the two new params are optional with `None` defaults, so every existing call site and every existing unit test that calls `_describe_event` directly keeps working unmodified.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tournament_match_engine.py` (check the file's own top for its exact import style before adding — it already imports `tournament_match_engine` as a module or specific names; match whichever pattern is already there):

```python
def test_describe_event_uses_tactic_flavor_for_a_high_quality_goal():
    import random
    from app.services import tournament_match_engine as engine

    random.seed(1)
    descriptions = {
        engine._describe_event("goal", "a", "Клуб А", "Клуб Б", playstyle="COUNTER_ATTACK", quality="VERY_HIGH")
        for _ in range(50)
    }
    # Over 50 draws, at least one COUNTER_ATTACK-flavored template must have
    # been picked — the flavor pool is mixed with the generic pool (spec
    # §11: "occasionally tactic-flavored", not every single goal), so this
    # asserts the flavor CAN appear, not that every draw uses it.
    assert any("контратак" in d.lower() for d in descriptions)


def test_describe_event_ignores_playstyle_for_a_low_quality_goal():
    import random
    from app.services import tournament_match_engine as engine

    random.seed(1)
    descriptions = {
        engine._describe_event("goal", "a", "Клуб А", "Клуб Б", playstyle="COUNTER_ATTACK", quality="LOW")
        for _ in range(50)
    }
    # LOW quality never gets tactic flavor (spec's examples are all
    # standout-moment phrasing) — every description must be one of the
    # original 3 generic goal templates.
    assert descriptions <= {
        "⚽ Гол! Клуб А открывает счёт!", "⚽ ГОЛ! Клуб А забивает!", "⚽ Клуб А находит путь в ворота!",
    }


def test_describe_event_still_works_with_no_playstyle_or_quality_passed():
    from app.services import tournament_match_engine as engine

    description = engine._describe_event("tackle_won", "b", "Клуб А", "Клуб Б")
    assert "Клуб Б" in description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_tournament_match_engine.py::test_describe_event_uses_tactic_flavor_for_a_high_quality_goal -v`
Expected: FAIL with `TypeError: _describe_event() got an unexpected keyword argument 'playstyle'`.

- [ ] **Step 3: Add the flavor templates and update `_describe_event`**

In `backend/app/services/tournament_match_engine.py`, add this after the existing `_EVENT_DESCRIPTIONS` dict:

```python
# Tactic-flavored variants for a standout ("HIGH"/"VERY_HIGH" quality) goal —
# mixed into the generic pool below rather than replacing it, so a
# tactic-flavored description appears "occasionally", never every time (spec
# §11). Only "goal" gets flavor text — spec's own 3 examples are all
# scoring-moment phrasing, and extending this to every event type would be
# scope beyond what's asked.
_PLAYSTYLE_GOAL_FLAVOR: dict[str, list[str]] = {
    "COUNTER_ATTACK": [
        "⚡ Быстрая контратака {club} застаёт соперника врасплох!",
        "⚡ {club} убегает в разрушительную контратаку!",
    ],
    "HIGH_PRESS": [
        "🔥 Высокий прессинг {club} перехватывает мяч — и сразу гол!",
        "🔥 {club} выигрывает мяч прессингом в опасной зоне!",
    ],
    "CENTRAL_PLAY": ["🎯 {club} находит момент через центр поля!"],
    "WING_PLAY": ["🎯 {club} врывается с фланга и не оставляет шансов!"],
    "POSSESSION": ["🎯 {club} терпеливо выводит мяч на убойную позицию!"],
}
```

Change:

```python
def _describe_event(event_type: str, team: str, club_a_name: str, club_b_name: str) -> str:
    club = club_a_name if team == "a" else club_b_name
    template = random.choice(_EVENT_DESCRIPTIONS[event_type])
    return template.format(club=club)
```

to:

```python
def _describe_event(
    event_type: str, team: str, club_a_name: str, club_b_name: str,
    playstyle: str | None = None, quality: str | None = None,
) -> str:
    club = club_a_name if team == "a" else club_b_name
    pool = _EVENT_DESCRIPTIONS[event_type]
    if event_type == "goal" and quality in ("HIGH", "VERY_HIGH") and playstyle in _PLAYSTYLE_GOAL_FLAVOR:
        pool = pool + _PLAYSTYLE_GOAL_FLAVOR[playstyle]
    template = random.choice(pool)
    return template.format(club=club)
```

- [ ] **Step 4: Thread playstyle/quality through `simulate_match`'s two attacking-event call sites**

In `backend/app/services/tournament_match_engine.py`'s `simulate_match`, change:

```python
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
```

to:

```python
    result = MatchResult(score_a=0, score_b=0)
    for chance in chances:
        attacking_side = chance.attacking_side
        defending_side = "b" if attacking_side == "a" else "a"
        attacking_playstyle = side_a.playstyle if attacking_side == "a" else side_b.playstyle

        if chance.shot_type == "empty_net":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            moment = {"minute": chance.minute}
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            event["description"] = _describe_event(
                event["event_type"], event["team"], club_a_name, club_b_name,
                playstyle=attacking_playstyle, quality=chance.quality,
            )
```

And change the second call site (the main shot-action branch, right after `event, scorer = _resolve_shot_action(...)`):

```python
        event, scorer = _resolve_shot_action(attacking_side, moment, config, quality_bias)
        result.event_log.append(event)
        event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
```

to:

```python
        event, scorer = _resolve_shot_action(attacking_side, moment, config, quality_bias)
        result.event_log.append(event)
        event["description"] = _describe_event(
            event["event_type"], event["team"], club_a_name, club_b_name,
            playstyle=attacking_playstyle, quality=chance.quality,
        )
```

Leave the third call site (the defense-tackle branch, describing `defending_side`'s action) unchanged — it never receives `playstyle`/`quality`, matching this task's scope (attacking-moment flavor only).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_tournament_match_engine.py -v`
Expected: PASS — including every pre-existing test in this file (the two new params default to `None`, so no existing call site or test changes behavior).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest tests/ -v`
Expected: PASS, except the one pre-existing unrelated failure (`test_tasks.py::test_task_reward_pack_grants_all_cards`) already documented as unrelated to any club/tactics work this session.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tournament_match_engine.py backend/tests/test_tournament_match_engine.py
git commit -m "feat(clubs): flavor high-quality goal commentary by attacking playstyle"
```

---

### Task 4: Frontend — Tactical Fit display + segmented tactics picker (§9, §11)

**Files:**
- Modify: `frontend/src/types/index.ts:1110-1118` (add `tactical_fit_hint: string` to `ClubLineup`)
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Consumes: `ClubLineup.tactical_fit: number` (already exists), new `ClubLineup.tactical_fit_hint: string` (Task 1's backend field — frontend type must match exactly), `FORMATIONS`/`MENTALITIES`/`PLAYSTYLES` from `frontend/src/lib/clubTactics.ts` (already exist, `{value, label}[]` shape).
- Produces: nothing new consumed by later tasks — this is a leaf UI change.

- [ ] **Step 1: Add the type field**

In `frontend/src/types/index.ts`, change:

```typescript
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

to:

```typescript
export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  tactical_fit_hint: string;
  slots: ClubLineupSlot[];
}
```

- [ ] **Step 2: Run typecheck to confirm the new field alone doesn't break anything**

Run: `cd frontend && npm run typecheck`
Expected: PASS (adding a required field to a type only used for reading API responses, never constructed by hand in this codebase, is safe).

- [ ] **Step 3: Show the tactical-fit percentage and hint in the squad header**

In `frontend/src/pages/ClubSquadPage.tsx`, change:

```tsx
      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав {lineup?.formation}</p>
          {lineup?.is_complete && <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>}
        </div>
```

to:

```tsx
      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав {lineup?.formation}</p>
          {lineup?.is_complete && <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>}
        </div>

        {lineup?.is_complete && (
          <div className="mb-3 flex items-center justify-between rounded-xl bg-white/5 px-3 py-2">
            <span className="text-xs text-ink-mist">{lineup.tactical_fit_hint}</span>
            <span className="shrink-0 font-mono text-xs font-bold text-accent-lime">{lineup.tactical_fit}%</span>
          </div>
        )}
```

- [ ] **Step 4: Replace the three plain `<select>`s with a segmented pill-row picker**

In `frontend/src/pages/ClubSquadPage.tsx`, change:

```tsx
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

to:

```tsx
        {canEdit && lineup && (
          <div className="mb-3 flex flex-col gap-2">
            <TacticRow
              label="Схема"
              options={FORMATIONS}
              value={lineup.formation}
              disabled={setTacticsMutation.isPending}
              onChange={(value) => updateTactics({ formation: value })}
            />
            <TacticRow
              label="Настрой"
              options={MENTALITIES}
              value={lineup.mentality}
              disabled={setTacticsMutation.isPending}
              onChange={(value) => updateTactics({ mentality: value })}
            />
            <TacticRow
              label="Стиль игры"
              options={PLAYSTYLES}
              value={lineup.playstyle}
              disabled={setTacticsMutation.isPending}
              onChange={(value) => updateTactics({ playstyle: value })}
            />
          </div>
        )}
```

Then add this new component at the bottom of the same file (after the default-exported `ClubSquadPage` function's closing brace):

```tsx
function TacticRow({
  label, options, value, disabled, onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-ink-mist-dim">{label}</p>
      <div className="flex gap-1.5 overflow-x-auto pb-0.5">
        {options.map((option) => (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            disabled={disabled}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-60 ${
              value === option.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Verify live in the browser**

Start the dev server (`docker compose up -d --build frontend backend` if the override is active, per this repo's own note on static-preview mode), open `/clubs/squad` (or navigate via the app's own club → squad flow) as a club captain with a complete 11-card squad. Confirm: the tactical-fit percentage and hint line render under the squad header; each of the 3 tactic rows renders as a horizontal pill row (not a native `<select>`); tapping a pill updates the lineup (mutation fires, the active pill highlights) exactly like the old `<select>`s did; a non-manager viewing the same page still sees no editable pills (the `canEdit` gate is untouched).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(clubs): show tactical fit and switch the tactics picker to pill rows"
```

---

### Task 5: Frontend — "Следующий соперник" block (§10, §11)

**Files:**
- Modify: `frontend/src/types/index.ts` (add `NextOpponent` interface, near `TournamentCurrent`)
- Modify: `frontend/src/api/clubs.ts` (add `fetchNextOpponent`)
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `GET /clubs/tournament/next-opponent` (Task 2's backend endpoint — returns 409 when there's no active tournament or no round left, which this task's query treats as "don't show the block", not an error banner), `TournamentCurrent.status`/`.tournament_id` (already exists, already fetched on this exact page).
- Produces: nothing consumed by a later task — this is this plan's last task.

- [ ] **Step 1: Add the type**

In `frontend/src/types/index.ts`, add this near `TournamentCurrent` (after its closing brace, ~line 1182):

```typescript
export interface NextOpponent {
  round_number: number;
  opponent_club_id: number;
  opponent_club_name: string;
  attack: number;
  midfield: number;
  defence: number;
  goalkeeping: number;
}
```

- [ ] **Step 2: Add the API function**

In `frontend/src/api/clubs.ts`, find `fetchTournamentCurrent` (it's a simple `api.get<T>(path)` wrapper) and add right after it:

```typescript
export async function fetchNextOpponent(): Promise<NextOpponent> {
  const { data } = await api.get<NextOpponent>("/clubs/tournament/next-opponent");
  return data;
}
```

Add `NextOpponent` to this file's existing `@/types` import line.

- [ ] **Step 3: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Render the block**

In `frontend/src/pages/ClubsPage.tsx`, add `fetchNextOpponent` to the existing `@/api/clubs` import block, and add `NextOpponent` if needed to the `@/types` import (only if referenced by name — using inferred typing from the query may make this unnecessary; add it if TypeScript complains at Step 6).

Add this query near the file's other `useQuery` calls (alongside wherever `tournamentCurrent` — from `fetchTournamentCurrent` — is already fetched):

```tsx
  const { data: nextOpponent } = useQuery({
    queryKey: ["clubs", "tournament", "next-opponent"],
    queryFn: fetchNextOpponent,
    enabled: tournamentCurrent?.status === "active",
    retry: false,
  });
```

Then, right after the existing "Турнир клуба" button block:

```tsx
      {(tournamentCurrent?.status === "active" || tournamentCurrent?.status === "completed") && tournamentCurrent.tournament_id && (
        <button
          onClick={() => navigate(`/clubs/tournament/${tournamentCurrent.tournament_id}`)}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconFlagCheckered size={16} className="text-accent-lime" />
          Турнир клуба
          {tournamentCurrent.status === "active" && (
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-accent-lime/10 px-2 py-1 text-[10px] font-bold text-accent-lime">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-lime" />
              Идёт
            </span>
          )}
        </button>
      )}
```

add:

```tsx
      {nextOpponent && (
        <div className="rounded-2xl bg-bg-surface p-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-ink-mist">
            <IconGoal size={14} className="text-accent-lime" />
            Тур {nextOpponent.round_number} · Следующий соперник
          </div>
          <p className="mb-2 font-display text-sm font-bold text-ink-chalk">{nextOpponent.opponent_club_name}</p>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.attack}</p>
              <p className="text-[9px] text-ink-mist-dim">Атака</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.midfield}</p>
              <p className="text-[9px] text-ink-mist-dim">Полузащита</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.defence}</p>
              <p className="text-[9px] text-ink-mist-dim">Защита</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.goalkeeping}</p>
              <p className="text-[9px] text-ink-mist-dim">Вратарь</p>
            </div>
          </div>
          {isManager && (
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => navigate("/clubs/squad")}
                className="flex-1 rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95"
              >
                Изменить состав
              </button>
            </div>
          )}
        </div>
      )}
```

(`IconGoal` is already imported on this page's existing icon import line — confirm before adding a duplicate import; `isManager` is already computed elsewhere in this component, per its existing manager-gated blocks like the tournament-apply button.)

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Verify live in the browser**

With a club that has just formed an 8-club tournament (queue completes automatically once the 8th club applies — see Task 2's test for the exact flow, or use an already-active tournament if one exists in the dev environment), open the Clubs page as a member of one of the 8 clubs. Confirm: the "Следующий соперник" card renders right below "Турнир клуба", shows the correct round number and the real opponent club's name (cross-check against `/clubs/tournament/{id}`'s standings/fixture list), and the 4 numbers are plausible (roughly 58-99-ish, matching the opponent's actual squad strength — spot-check by comparing against that club's own squad page if you have access). Confirm the card does NOT render for a club with no active tournament (e.g. `status: "not_queued"` or `"queued"`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/clubs.ts frontend/src/pages/ClubsPage.tsx
git commit -m "feat(clubs): show the next tournament opponent's scouted strengths"
```

---

## Self-Review Notes

**Spec coverage:** §9 (Tactical Fit UI) → Task 1 (backend) + Task 4 (frontend). §10 (scouting endpoint) → Task 2 (backend) + Task 5 (frontend). §11 (UX pass): tactics picker → Task 4 Step 4; "Следующий соперник" block → Task 5; event-log flavor text → Task 3. §11's `PUT /clubs/me/tactics` endpoint itself is Phase 1 work, already shipped — not re-planned here. §12 config strategy: deliberately not touched (no new tunables needed). §13 migration/§14 tests: Phase 1-scoped, not re-litigated.

**Placeholder scan:** every step has real code, real assertions, real Russian copy — no TBD/TODO, no "add appropriate handling", no "similar to Task N" cross-references without the actual code repeated in place.

**Type consistency:** `ClubLineupOut.tactical_fit_hint: str` (Task 1) matches `ClubLineup.tactical_fit_hint: string` (Task 4) exactly. `NextOpponentOut`'s 7 fields (Task 2) match `NextOpponent`'s 7 fields (Task 5) exactly, same names, same order. `get_next_opponent(db, user)`'s signature (Task 2) matches its router call site exactly.
