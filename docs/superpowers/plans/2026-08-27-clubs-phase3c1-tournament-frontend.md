# Clubs Phase 3c-1: Player-Facing Tournament Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give players a way to experience the tournament pipeline that has run backend-only since Phase 3a: apply to a tournament, watch standings/fixtures, replay a match with real commentary, see round-14 results, and check a club leaderboard.

**Architecture:** Four small, targeted backend additions to already-shipped Phase 3a/3b code (event descriptions in the match engine, `cups_count`/`stars_count` exposure, a new club-ranking service+endpoint, `TournamentClubResult` data on standings) — none require a new Alembic migration, since `Club.cups_count`/`.stars_count` and the `tournament_club_results` table already exist. Then new frontend pages/components consuming the already-shipped (now description-complete) read API: an apply entry point on `ClubHome`, a standings+fixtures+results page, a standalone replay viewer (NOT extracted from the live `MatchSimulation`/`ArenaPage.tsx` — a fresh, simpler component reusing only the reveal-over-a-timer mechanic), a club-preview popup, and a club leaderboard page mirroring `RankingPage.tsx`. Finally, restore the one-line `club_match` bot deep-link Phase 3b deliberately removed pending this route's existence.

**Tech Stack:** FastAPI + SQLAlchemy 2 async (backend), React 18 + TypeScript + TanStack Query + React Router (frontend), aiogram 3 (bot, one-line change only).

**Spec:** `docs/superpowers/specs/2026-08-27-clubs-phase3c1-tournament-frontend-design.md`

## Global Constraints

- No new Alembic migration in this plan — `Club.cups_count`/`.stars_count` (Phase 3a) and the `tournament_club_results` table (Phase 3a) already exist; this plan only exposes existing columns/rows through schemas and new read paths.
- Event descriptions never name individual players — only the acting club, exactly like the personal engine's own `_EVENT_DESCRIPTIONS` in `match_service.py` (team-level phrasing only, no `{shooter}`-style placeholder there either — confirmed by direct read).
- `frontend/src/pages/ArenaPage.tsx` and its private `MatchSimulation` component are never touched by this plan — the replay viewer is new, standalone code.
- `bot/services/notifier.py`'s `_MATCH_PATH_PREFIXES["club_match"]` is restored only in the last task, after the real `/clubs/tournament/:id` route exists (Phase 3b deliberately removed it for exactly this reason).
- Tournaments are round-robin, not an elimination bracket — the standings page is a ranked table + played-fixtures list, never a bracket/tree UI.
- The results-gate is a frontend-only `localStorage` flag keyed by tournament id — no backend "seen" concept is introduced.
- Every mutating economy/reward calculation (budget, stars, cups) already happened in Phase 3a/3b's `tournament_reward_service.py` — this plan only reads and displays already-computed values, never recomputes them client-side or server-side.

---

### Task 1: Backend — tournament match event descriptions + club-name threading

**Files:**
- Modify: `backend/app/services/tournament_match_engine.py`
- Modify: `backend/app/services/tournament_simulation_service.py:1-20,247-252,279-281` (imports, participant club-name lookup, `simulate_match` call site)
- Test: `backend/tests/test_tournament_match_engine.py`

**Interfaces:**
- Consumes: nothing new from other tasks (first task in the plan).
- Produces: `tournament_match_engine.simulate_match(strength_a, strength_b, lineup_a, lineup_b, config, club_a_name="Клуб A", club_b_name="Клуб B") -> MatchResult`, where every dict in `MatchResult.event_log` now also carries a `"description"` key (`str`, real club name, never a player name). Later tasks (frontend Task 8, `MatchEvent` type in Task 5) rely on `event_log` entries always having `description` from this point on.

- [ ] **Step 1: Write the failing test for description generation**

Add to `backend/tests/test_tournament_match_engine.py` (reuses this file's existing `_fake_lineup`/`_FakeMatchConfig` fixtures, already defined above where this test is appended):

```python
def test_simulate_match_events_carry_club_name_descriptions(monkeypatch):
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)  # every roll fails -> every shot scores, same trick as the existing determinism test
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig(), "Реал Мадрид", "Барселона")

    assert result.event_log  # sanity: there is something to check
    for event in result.event_log:
        assert isinstance(event["description"], str) and event["description"]
        assert "Player" not in event["description"]  # never names an individual player, only the club
        club_name = "Реал Мадрид" if event["team"] == "a" else "Барселона"
        assert club_name in event["description"]


def test_simulate_match_default_club_names_when_omitted():
    # Existing two call sites in this file (test_simulate_match_produces_deterministic_score_from_event_log,
    # and the one further below) call simulate_match with only 5 positional args — confirms that keeps working
    # via the new params' defaults, not a breaking signature change.
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())
    for event in result.event_log:
        assert event["description"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_tournament_match_engine.py::test_simulate_match_events_carry_club_name_descriptions -v`
Expected: FAIL with `KeyError: 'description'`

- [ ] **Step 3: Add `_EVENT_DESCRIPTIONS` + `_describe_event` and thread club names through `simulate_match`**

In `backend/app/services/tournament_match_engine.py`, add this module-level dict right after `_SHOT_CHANCE_WEIGHT = 26` (after line 19, before the blank line at line 20-21):

```python
# Distinct from match_service.py's personal-engine _EVENT_DESCRIPTIONS (phrased "your team" vs.
# "{them}") — a tournament replay is watched from a neutral standpoint by any club's members, so
# every description names the real club instead. Never names an individual player, matching the
# personal engine's own team-level-only phrasing. Exactly 7 event types — confirmed exhaustive:
# generate_moment_queue only ever appends "flavor" moments (never persisted to event_log, see the
# `continue` in simulate_match below) or one of these 7 resolved shot/tackle outcomes.
_EVENT_DESCRIPTIONS: dict[str, list[str]] = {
    "goal": [
        "⚽ Гол! {club} открывает счёт!",
        "⚽ ГОЛ! {club} забивает!",
        "⚽ {club} находит путь в ворота!",
    ],
    "shot": [
        "🎯 {club} бьёт — мимо ворот",
        "🎯 Удар {club} уходит выше перекладины",
    ],
    "save": [
        "🧤 Вратарь {club} спасает свою команду!",
        "🧤 Отличный сейв на счету {club}!",
    ],
    "blocked": [
        "🛡️ Защитник {club} блокирует удар!",
        "🛡️ {club} накрывает удар в последний момент!",
    ],
    "pass_failed": [
        "❌ Пас {club} не находит адресата — атака сорвана",
        "❌ {club} теряет мяч в решающей передаче",
    ],
    "tackle_won": [
        "🛡️ Защитник {club} чисто отбирает мяч в подкате!",
        "🛡️ {club} прерывает атаку точным подкатом",
    ],
    "foul_stopped": [
        "🟨 Фол защитника {club} останавливает атаку",
        "🟨 {club} фолит, чтобы сорвать атаку",
    ],
}


def _describe_event(event_type: str, team: str, club_a_name: str, club_b_name: str) -> str:
    club = club_a_name if team == "a" else club_b_name
    template = random.choice(_EVENT_DESCRIPTIONS[event_type])
    return template.format(club=club)
```

Change the `simulate_match` signature (line 229) from:

```python
def simulate_match(strength_a: int, strength_b: int, lineup_a: list[dict], lineup_b: list[dict], config) -> "MatchResult":
```

to:

```python
def simulate_match(
    strength_a: int, strength_b: int, lineup_a: list[dict], lineup_b: list[dict], config,
    club_a_name: str = "Клуб A", club_b_name: str = "Клуб B",
) -> "MatchResult":
```

(Defaults keep this file's two existing test call sites — `test_simulate_match_produces_deterministic_score_from_event_log` and the one further below it — working unchanged; the real production caller in `tournament_simulation_service.py`, changed in Step 5 below, always passes real names.)

Then, in the same function's body, add a `description` key right after each of the 3 `result.event_log.append(...)` calls:

```python
        if moment["situation_kind"] == "breakaway":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
            if scorer != "none":
```

```python
        event, scorer = _resolve_shot_action(attacking_side, moment, config)
        result.event_log.append(event)
        event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
        if scorer != "none":
```

```python
        if event["event_type"] in ("blocked", "save") and random.random() < 0.15:
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            defense_event["description"] = _describe_event(defense_event["event_type"], defense_event["team"], club_a_name, club_b_name)
            if defense_scorer != "none":
```

(Setting `event["description"]` after `append` rather than before is equivalent — `append` stores the same dict reference, so mutating it afterward still lands in `result.event_log` — and keeps the diff to one line per site instead of restructuring the dict literals themselves.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_tournament_match_engine.py -v`
Expected: all PASS, including both new tests and every pre-existing test in the file.

- [ ] **Step 5: Thread real club names through from `tournament_simulation_service.py`**

In `backend/app/services/tournament_simulation_service.py`, add `Club` to the existing model imports (line 9, currently `from app.models.club_card import ClubCard`) — add a new import line right above it:

```python
from app.models.club import Club
from app.models.club_card import ClubCard
```

In `simulate_next_round`, right after the `participants = (...)` block (after `club_ids = [p.club_id for p in participants]` and `withdrawn_ids = {...}`, i.e. after the current line `withdrawn_ids = {p.club_id for p in participants if p.is_withdrawn}`), add a club-name lookup:

```python
        club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_(club_ids)))).scalars().all()}
```

Then change the `simulate_match` call site from:

```python
            engine_result = tournament_match_engine.simulate_match(strength_a, strength_b, lineup_a, lineup_b, config)
```

to:

```python
            engine_result = tournament_match_engine.simulate_match(
                strength_a, strength_b, lineup_a, lineup_b, config,
                club_names[club_a_id], club_names[club_b_id],
            )
```

- [ ] **Step 6: Run the full tournament test suite**

Run: `cd backend && pytest tests/test_tournament_match_engine.py tests/test_tournament_simulation_service.py tests/test_tournament_simulation_lineup.py tests/test_tournament_api.py -v`
Expected: all PASS. (`club_names[club_a_id]`/`club_names[club_b_id]` can only KeyError if a participant's `Club` row vanished mid-round — not reachable today since soft-disband, not hard-delete, is used for any club with tournament history, per Phase 3a's Task 15 fix.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tournament_match_engine.py backend/app/services/tournament_simulation_service.py backend/tests/test_tournament_match_engine.py
git commit -m "feat: add real-club-name event descriptions to tournament match engine"
```

---

### Task 2: Backend — expose `cups_count`/`stars_count` on club schemas

**Files:**
- Modify: `backend/app/schemas/club.py:32-56` (`ClubSummaryOut`, `ClubDetailOut`)
- Modify: `backend/app/services/club_service.py:86-96,149-155` (`_club_to_detail`, `list_clubs`)
- Test: `backend/tests/test_clubs.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `ClubSummaryOut` and `ClubDetailOut` both gain `cups_count: int` and `stars_count: int` fields, populated from the existing `Club.cups_count`/`Club.stars_count` columns. Frontend Task 5's `Club`/`ClubSummary` TS types mirror these two new fields exactly.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_clubs.py` (reuses this file's existing `_register`/`telegram_headers` helpers):

```python
async def test_club_detail_and_summary_expose_cups_and_stars_count(client, db_session, bot_token):
    await _register(client, db_session, 820020, bot_token)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820020, bot_token),
        json={"name": "Звёздный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["cups_count"] == 0
    assert create_resp.json()["stars_count"] == 0

    club_id = create_resp.json()["id"]
    club_row = await db_session.get(Club, club_id)
    club_row.cups_count = 3
    club_row.stars_count = 7
    db_session.add(club_row)
    await db_session.commit()

    detail_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820020, bot_token))
    assert detail_resp.json()["cups_count"] == 3
    assert detail_resp.json()["stars_count"] == 7

    list_resp = await client.get("/api/v1/clubs", headers=telegram_headers(820020, bot_token))
    listed = next(c for c in list_resp.json() if c["id"] == club_id)
    assert listed["cups_count"] == 3
    assert listed["stars_count"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_clubs.py::test_club_detail_and_summary_expose_cups_and_stars_count -v`
Expected: FAIL with a Pydantic/KeyError-style failure — `cups_count` missing from the response body.

- [ ] **Step 3: Add the two fields to both schemas**

In `backend/app/schemas/club.py`, change `ClubSummaryOut` (lines 32-38) from:

```python
class ClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    member_count: int
```

to:

```python
class ClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    member_count: int
    cups_count: int
    stars_count: int
```

And `ClubDetailOut` (lines 41-56) from:

```python
class ClubDetailOut(BaseModel):
    id: int
    name: str
    description: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    captain_id: int
    founded_at: datetime
    member_count: int
    budget: int
    members: list[ClubMemberOut]
```

to:

```python
class ClubDetailOut(BaseModel):
    id: int
    name: str
    description: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    captain_id: int
    founded_at: datetime
    member_count: int
    budget: int
    cups_count: int
    stars_count: int
    members: list[ClubMemberOut]
```

- [ ] **Step 4: Populate both fields from the `Club` row**

In `backend/app/services/club_service.py`, change `_club_to_detail`'s `ClubDetailOut(...)` construction (lines 90-96) from:

```python
    return ClubDetailOut(
        id=club.id, name=club.name, description=club.description, club_type=club.club_type,
        logo_shape=club.logo_shape, logo_color=club.logo_color, captain_id=club.captain_id,
        founded_at=club.founded_at, member_count=len(members), budget=club.budget, members=members,
        invite_code=club.invite_code if is_member else None,
        my_role=my_membership.role if my_membership else None,
    )
```

to:

```python
    return ClubDetailOut(
        id=club.id, name=club.name, description=club.description, club_type=club.club_type,
        logo_shape=club.logo_shape, logo_color=club.logo_color, captain_id=club.captain_id,
        founded_at=club.founded_at, member_count=len(members), budget=club.budget,
        cups_count=club.cups_count, stars_count=club.stars_count, members=members,
        invite_code=club.invite_code if is_member else None,
        my_role=my_membership.role if my_membership else None,
    )
```

And change `list_clubs`'s `ClubSummaryOut(...)` construction (lines 150-153) from:

```python
        ClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape,
            logo_color=c.logo_color, member_count=count,
        )
```

to:

```python
        ClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape,
            logo_color=c.logo_color, member_count=count,
            cups_count=c.cups_count, stars_count=c.stars_count,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_clubs.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/club.py backend/app/services/club_service.py backend/tests/test_clubs.py
git commit -m "feat: expose cups_count/stars_count on club API responses"
```

---

### Task 3: Backend — club leaderboard service + `GET /clubs/leaderboard`

**Files:**
- Create: `backend/app/schemas/club_ranking.py`
- Create: `backend/app/services/club_ranking_service.py`
- Modify: `backend/app/routers/clubs.py:1-45` (imports + new route, inserted before `/clubs/{club_id}`)
- Test: `backend/tests/test_club_ranking_service.py`

**Interfaces:**
- Consumes: `Club.cups_count`/`.stars_count` (already on the model since Phase 3a; exposed on schemas by Task 2, but this task reads the ORM column directly, not through Task 2's schema).
- Produces: `GET /clubs/leaderboard?metric=cups|stars` -> `ClubRankingOut { metric, top: ClubRankingEntry[], me: ClubRankingEntry | null }`, where `ClubRankingEntry = { rank, club_id, name, logo_shape, logo_color, value }`. Frontend Task 5's `ClubRankingMetric`/`ClubRankingEntry`/`ClubRankingResult` TS types and Task 9's leaderboard page consume this exact shape.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_club_ranking_service.py`:

```python
import pytest_asyncio

from app.models.club import Club
from app.models.enums import Position
from app.schemas.club_ranking import ClubRankingMetric
from app.services.club_ranking_service import get_club_ranking
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad on every creation — same seeding every other club test
    file needs (see test_clubs.py's identical fixture)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _make_club(client, db_session, bot_token, telegram_id, name, cups=0, stars=0):
    await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    user = await get_user_by_telegram_id(db_session, telegram_id)
    resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    club = await db_session.get(Club, resp.json()["id"])
    club.cups_count = cups
    club.stars_count = stars
    db_session.add(club)
    await db_session.commit()
    return club, user


async def test_get_club_ranking_orders_by_metric_and_finds_me(client, db_session, bot_token):
    club_a, user_a = await _make_club(client, db_session, bot_token, 860001, "Клуб А", cups=5)
    club_b, _ = await _make_club(client, db_session, bot_token, 860002, "Клуб Б", cups=2)
    club_c, _ = await _make_club(client, db_session, bot_token, 860003, "Клуб В", cups=9)

    result = await get_club_ranking(db_session, ClubRankingMetric.cups, current_user_id=user_a.id)

    assert [e.club_id for e in result.top] == [club_c.id, club_a.id, club_b.id]
    assert [e.value for e in result.top] == [9, 5, 2]
    assert result.me is not None
    assert result.me.club_id == club_a.id
    assert result.me.rank == 2


async def test_get_club_ranking_me_is_none_when_not_in_a_club(client, db_session, bot_token):
    await _make_club(client, db_session, bot_token, 860004, "Клуб Г", stars=1)
    await client.post("/api/v1/auth/session", headers=telegram_headers(860005, bot_token))
    outsider = await get_user_by_telegram_id(db_session, 860005)

    result = await get_club_ranking(db_session, ClubRankingMetric.stars, current_user_id=outsider.id)
    assert result.me is None


async def test_leaderboard_endpoint_returns_ranked_clubs(client, db_session, bot_token):
    await _make_club(client, db_session, bot_token, 860006, "Клуб Д", stars=4)
    resp = await client.get(
        "/api/v1/clubs/leaderboard", params={"metric": "stars"}, headers=telegram_headers(860006, bot_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "stars"
    assert body["top"][0]["value"] == 4
    assert body["top"][0]["name"] == "Клуб Д"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_club_ranking_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.club_ranking'`

- [ ] **Step 3: Create the schema**

Create `backend/app/schemas/club_ranking.py`:

```python
import enum
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape


class ClubRankingMetric(str, enum.Enum):
    cups = "cups"
    stars = "stars"


class ClubRankingEntry(BaseModel):
    rank: int
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    value: int


class ClubRankingOut(BaseModel):
    metric: ClubRankingMetric
    top: list[ClubRankingEntry]
    me: Optional[ClubRankingEntry] = None
```

- [ ] **Step 4: Create the service**

Create `backend/app/services/club_ranking_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import Club, ClubMember
from app.schemas.club_ranking import ClubRankingEntry, ClubRankingMetric, ClubRankingOut

# Mirrors ranking_service.get_ranking's exact shape (one unfiltered query, Python top-N slice,
# linear scan of the full row set for "my position") — confirmed by direct read of that file
# before writing this one. Entry serialization doesn't transfer (personal entries carry
# avatar/badge; club entries carry name/logo), so ClubRankingEntry is its own schema.
_DIRECT_COLUMNS = {
    ClubRankingMetric.cups: Club.cups_count,
    ClubRankingMetric.stars: Club.stars_count,
}


async def get_club_ranking(
    db: AsyncSession, metric: ClubRankingMetric, current_user_id: int, limit: int = 10
) -> ClubRankingOut:
    column = _DIRECT_COLUMNS[metric]
    stmt = select(Club, column).where(Club.is_disbanded.is_(False)).order_by(column.desc())
    rows = (await db.execute(stmt)).all()

    def to_entry(rank: int, club: Club, value) -> ClubRankingEntry:
        return ClubRankingEntry(
            rank=rank, club_id=club.id, name=club.name,
            logo_shape=club.logo_shape, logo_color=club.logo_color, value=int(value or 0),
        )

    top = [to_entry(i + 1, club, value) for i, (club, value) in enumerate(rows[:limit])]

    my_club_id = (
        await db.execute(select(ClubMember.club_id).where(ClubMember.user_id == current_user_id))
    ).scalar_one_or_none()

    me = None
    if my_club_id is not None:
        for i, (club, value) in enumerate(rows):
            if club.id == my_club_id:
                me = to_entry(i + 1, club, value)
                break

    return ClubRankingOut(metric=metric, top=top, me=me)
```

- [ ] **Step 5: Wire the router endpoint**

In `backend/app/routers/clubs.py`, add the new schema import to the existing `from app.schemas.club import ...` import block (line 17) — change:

```python
from app.schemas.club import ClubCreate, ClubDetailOut, ClubJoinRequestOut, ClubSummaryOut, JoinByInviteIn, TransferCaptainIn
```

to add a new import line right after it:

```python
from app.schemas.club import ClubCreate, ClubDetailOut, ClubJoinRequestOut, ClubSummaryOut, JoinByInviteIn, TransferCaptainIn
from app.schemas.club_ranking import ClubRankingMetric, ClubRankingOut
```

Change the services import (line 29) from:

```python
from app.services import club_pack_service, club_service, club_squad_service, tournament_queue_service
```

to:

```python
from app.services import club_pack_service, club_ranking_service, club_service, club_squad_service, tournament_queue_service
```

Insert a new route right after `list_club_packs` (after line 44, before the `/me` route at line 47) — inserted here, before `/{club_id}` (line 52), for the same single-path-segment-collision reason `/me` and `/packs` are already declared before it (a `GET /clubs/leaderboard` request would otherwise match `/clubs/{club_id}` first and fail int validation on `"leaderboard"`):

```python
@router.get("/leaderboard", response_model=ClubRankingOut)
async def get_club_leaderboard(
    metric: ClubRankingMetric, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_ranking_service.get_club_ranking(db, metric, current_user_id=user.id)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_club_ranking_service.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full club test suite to confirm no route-ordering regression**

Run: `cd backend && pytest tests/test_clubs.py tests/test_club_ranking_service.py -v`
Expected: all PASS — in particular, existing `/clubs/{club_id}` tests still resolve correctly with the new `/clubs/leaderboard` route inserted above them.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/club_ranking.py backend/app/services/club_ranking_service.py backend/app/routers/clubs.py backend/tests/test_club_ranking_service.py
git commit -m "feat: add club cups/stars leaderboard endpoint"
```

---

### Task 4: Backend — expose `TournamentClubResult` data on standings

**Files:**
- Modify: `backend/app/schemas/tournament.py:16-22` (`TournamentStandingOut`)
- Modify: `backend/app/routers/clubs.py` (`get_tournament_detail`)
- Test: `backend/tests/test_tournament_api.py`

**Interfaces:**
- Consumes: `TournamentClubResult(tournament_id, club_id, final_rank, budget_awarded, stars_delta, cup_awarded)` — existing model, populated once at round 14 by `tournament_reward_service.conclude_tournament` (unchanged by this task).
- Produces: `TournamentStandingOut` gains `budget_awarded: int | None`, `stars_delta: int | None`, `cup_awarded: bool | None` (all `None` until the tournament completes). Frontend Task 5's `TournamentStanding` TS type and Task 7's results section consume these three fields.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tournament_api.py` (reuses this file's existing `eight_club_tournament` fixture):

```python
async def test_tournament_detail_exposes_reward_fields_only_after_completion(
    client, db_session, bot_token, eight_club_tournament
):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    mid_resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert mid_resp.status_code == 200
    assert all(s["budget_awarded"] is None for s in mid_resp.json()["standings"])

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    done_resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert done_resp.status_code == 200
    standings = done_resp.json()["standings"]
    assert all(s["budget_awarded"] is not None for s in standings)
    assert all(s["stars_delta"] is not None for s in standings)
    winner = next(s for s in standings if s["final_rank"] == 1)
    assert winner["cup_awarded"] is True
    runner_up = next(s for s in standings if s["final_rank"] == 2)
    assert runner_up["cup_awarded"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_tournament_api.py::test_tournament_detail_exposes_reward_fields_only_after_completion -v`
Expected: FAIL with a `KeyError`/`None` mismatch — `budget_awarded` missing from the response body.

- [ ] **Step 3: Add the three fields to `TournamentStandingOut`**

In `backend/app/schemas/tournament.py`, change `TournamentStandingOut` (lines 16-22) from:

```python
class TournamentStandingOut(BaseModel):
    club_id: int
    club_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
```

to:

```python
class TournamentStandingOut(BaseModel):
    club_id: int
    club_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    budget_awarded: Optional[int] = None
    stars_delta: Optional[int] = None
    cup_awarded: Optional[bool] = None
```

- [ ] **Step 4: Populate the fields in `get_tournament_detail`**

In `backend/app/routers/clubs.py`, add the two new imports needed — `TournamentStatus` (not currently imported in this file) and `TournamentClubResult`. Change the model imports block (lines 11-16) from:

```python
from app.models.club import Club
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_queue import TournamentQueueEntry, TournamentQueueState
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
```

to:

```python
from app.models.club import Club
from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_queue import TournamentQueueEntry, TournamentQueueState
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
```

Change `get_tournament_detail` (currently lines 202-227) from:

```python
@router.get("/tournament/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament_id))).scalars().all()
    matches = (await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id))).scalars().all()
    ranked = rank_standings(standings, matches)

    club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_([s.club_id for s in standings])))).scalars().all()}

    return TournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=[
            TournamentStandingOut(
                club_id=s.club_id, club_name=club_names.get(s.club_id, ""), points=s.points,
                goals_for=s.goals_for, goals_against=s.goals_against, final_rank=index + 1,
            )
            for index, s in enumerate(ranked)
        ],
        matches=[
            TournamentMatchSummaryOut(id=m.id, round_number=m.round_number, club_a_id=m.club_a_id, club_b_id=m.club_b_id, score_a=m.score_a, score_b=m.score_b)
            for m in matches
        ],
    )
```

to:

```python
@router.get("/tournament/{tournament_id}", response_model=TournamentDetailOut)
async def get_tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Турнир не найден")

    standings = (await db.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament_id))).scalars().all()
    matches = (await db.execute(select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id))).scalars().all()
    ranked = rank_standings(standings, matches)

    club_names = {c.id: c.name for c in (await db.execute(select(Club).where(Club.id.in_([s.club_id for s in standings])))).scalars().all()}

    results_by_club: dict[int, TournamentClubResult] = {}
    if tournament.status == TournamentStatus.completed:
        results = (
            await db.execute(select(TournamentClubResult).where(TournamentClubResult.tournament_id == tournament_id))
        ).scalars().all()
        results_by_club = {r.club_id: r for r in results}

    return TournamentDetailOut(
        id=tournament.id, status=tournament.status.value, rounds_simulated=tournament.rounds_simulated,
        standings=[
            TournamentStandingOut(
                club_id=s.club_id, club_name=club_names.get(s.club_id, ""), points=s.points,
                goals_for=s.goals_for, goals_against=s.goals_against, final_rank=index + 1,
                budget_awarded=results_by_club[s.club_id].budget_awarded if s.club_id in results_by_club else None,
                stars_delta=results_by_club[s.club_id].stars_delta if s.club_id in results_by_club else None,
                cup_awarded=results_by_club[s.club_id].cup_awarded if s.club_id in results_by_club else None,
            )
            for index, s in enumerate(ranked)
        ],
        matches=[
            TournamentMatchSummaryOut(id=m.id, round_number=m.round_number, club_a_id=m.club_a_id, club_b_id=m.club_b_id, score_a=m.score_a, score_b=m.score_b)
            for m in matches
        ],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_tournament_api.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/tournament.py backend/app/routers/clubs.py backend/tests/test_tournament_api.py
git commit -m "feat: expose tournament reward results on standings after completion"
```

---

### Task 5: Frontend — types + API client foundation

**Files:**
- Modify: `frontend/src/types/index.ts` (append near the existing `Club`-related types around line 944-1043)
- Modify: `frontend/src/api/clubs.ts` (append new functions)
- Modify: `frontend/src/api/leaderboard.ts` (append `fetchClubLeaderboard`)

**Interfaces:**
- Consumes: Task 1's `event_log[].description` (always present now), Task 2's `cups_count`/`stars_count`, Task 3's `ClubRankingOut` shape, Task 4's three new `TournamentStandingOut` fields.
- Produces: every TS type and API function Tasks 6-9 import. No runtime logic in this task — purely additive types + thin API wrappers, so no automated test (matches this codebase's convention of not unit-testing pure Axios passthrough wrappers — see every existing function in `api/clubs.ts`).

- [ ] **Step 1: Add `cups_count`/`stars_count` to `ClubSummary` and `Club`**

In `frontend/src/types/index.ts`, change `ClubSummary` (lines 958-965) from:

```typescript
export interface ClubSummary {
  id: number;
  name: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  member_count: number;
}
```

to:

```typescript
export interface ClubSummary {
  id: number;
  name: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  member_count: number;
  cups_count: number;
  stars_count: number;
}
```

And change `Club` (lines 967-981) from:

```typescript
export interface Club {
  id: number;
  name: string;
  description: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  captain_id: number;
  founded_at: string;
  member_count: number;
  members: ClubMember[];
  invite_code: string | null;
  my_role: ClubRole | null;
  budget: number;
}
```

to:

```typescript
export interface Club {
  id: number;
  name: string;
  description: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  captain_id: number;
  founded_at: string;
  member_count: number;
  members: ClubMember[];
  invite_code: string | null;
  my_role: ClubRole | null;
  budget: number;
  cups_count: number;
  stars_count: number;
}
```

- [ ] **Step 2: Add tournament + club-ranking types**

Append to the end of `frontend/src/types/index.ts` (after `ClubPackOpenResult`, currently ending at line 1043):

```typescript

export type ClubRankingMetric = "cups" | "stars";

export interface ClubRankingEntry {
  rank: number;
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  value: number;
}

export interface ClubRankingResult {
  metric: ClubRankingMetric;
  top: ClubRankingEntry[];
  me: ClubRankingEntry | null;
}

export type TournamentCurrentStatus = "not_queued" | "queued" | "active" | "completed";

export interface TournamentApplyResult {
  queued: boolean;
  tournament_id: number | null;
  queue_position: number | null;
}

export interface TournamentCurrent {
  status: TournamentCurrentStatus;
  queue_position: number | null;
  tournament_id: number | null;
}

export interface TournamentStanding {
  club_id: number;
  club_name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  budget_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}

export interface TournamentMatchSummary {
  id: number;
  round_number: number;
  club_a_id: number;
  club_b_id: number;
  score_a: number;
  score_b: number;
}

export interface TournamentDetail {
  id: number;
  status: string;
  rounds_simulated: number;
  standings: TournamentStanding[];
  matches: TournamentMatchSummary[];
}

export interface TournamentMatchDetail {
  id: number;
  round_number: number;
  club_a_id: number;
  club_b_id: number;
  score_a: number;
  score_b: number;
  event_log: MatchEvent[];
}
```

(`event_log: MatchEvent[]` reuses the existing `MatchEvent` type from this same file — `{ minute, event_type, team, description, payload }` — since Task 1 guarantees every tournament event now carries `description` too, the shape is identical to the personal engine's events.)

- [ ] **Step 3: Add API client functions**

Append to `frontend/src/api/clubs.ts`, and change its type import line (currently `import type { Club, ClubJoinRequest, ClubSummary } from "@/types";`) to:

```typescript
import type {
  Club,
  ClubJoinRequest,
  ClubSummary,
  TournamentApplyResult,
  TournamentCurrent,
  TournamentDetail,
  TournamentMatchDetail,
} from "@/types";
```

Then append these functions to the end of the file:

```typescript

export async function applyToTournament(): Promise<TournamentApplyResult> {
  const { data } = await api.post<TournamentApplyResult>("/clubs/tournament/apply");
  return data;
}

export async function fetchTournamentCurrent(): Promise<TournamentCurrent> {
  const { data } = await api.get<TournamentCurrent>("/clubs/tournament/current");
  return data;
}

export async function fetchTournamentDetail(id: number): Promise<TournamentDetail> {
  const { data } = await api.get<TournamentDetail>(`/clubs/tournament/${id}`);
  return data;
}

export async function fetchTournamentMatch(tournamentId: number, matchId: number): Promise<TournamentMatchDetail> {
  const { data } = await api.get<TournamentMatchDetail>(`/clubs/tournament/${tournamentId}/matches/${matchId}`);
  return data;
}
```

- [ ] **Step 4: Add the club-leaderboard API function**

In `frontend/src/api/leaderboard.ts`, change the type import line from:

```typescript
import type { ArenaLeaderboardEntry, MemoryLeaderboardEntry, RankingMetric, RankingResult } from "@/types";
```

to:

```typescript
import type { ArenaLeaderboardEntry, ClubRankingMetric, ClubRankingResult, MemoryLeaderboardEntry, RankingMetric, RankingResult } from "@/types";
```

Then append:

```typescript

export async function fetchClubLeaderboard(metric: ClubRankingMetric): Promise<ClubRankingResult> {
  const { data } = await api.get<ClubRankingResult>("/clubs/leaderboard", { params: { metric } });
  return data;
}
```

- [ ] **Step 5: Run typecheck to verify no errors**

Run: `cd frontend && npm run typecheck`
Expected: PASS (this task only adds types/functions; nothing consumes them yet, so no "unused" errors either — TS doesn't flag unused exports).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/clubs.ts frontend/src/api/leaderboard.ts
git commit -m "feat: add frontend types and API client for tournament frontend"
```

---

### Task 6: Frontend — club-preview popup + browse-list click wiring

**Files:**
- Create: `frontend/src/components/clubs/ClubPreviewPopup.tsx`
- Modify: `frontend/src/pages/ClubsPage.tsx` (`ClubBrowseList` gains a click handler)

**Interfaces:**
- Consumes: `fetchClub(id): Promise<Club>` (existing, already used by `ClubsPage.tsx`'s other flows), Task 5's `Club.cups_count`/`.stars_count`.
- Produces: `ClubPreviewPopup({ clubId, onClose }: { clubId: number | null; onClose: () => void })` — Task 7's standings page reuses this exact component for standings-row clicks.

- [ ] **Step 1: Create the popup component**

Create `frontend/src/components/clubs/ClubPreviewPopup.tsx`, following this codebase's existing bottom-sheet modal pattern (`HelpModal.tsx`'s `createPortal` + `framer-motion` shape):

```tsx
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { createPortal } from "react-dom";

import { fetchClub } from "@/api/clubs";
import { ClubLogo } from "@/components/clubs/ClubLogo";

export function ClubPreviewPopup({ clubId, onClose }: { clubId: number | null; onClose: () => void }) {
  const { data: club, isLoading } = useQuery({
    queryKey: ["clubs", "preview", clubId],
    queryFn: () => fetchClub(clubId!),
    enabled: clubId !== null,
  });

  return createPortal(
    <AnimatePresence>
      {clubId !== null && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="safe-bottom w-full max-w-sm rounded-t-3xl border border-white/10 bg-bg-surface p-6 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
          >
            {isLoading && <p className="text-sm text-ink-mist">Загрузка...</p>}
            {club && (
              <div className="flex flex-col items-center gap-3 text-center">
                <ClubLogo shape={club.logo_shape} color={club.logo_color} size={64} />
                <p className="font-display text-lg font-bold text-ink-chalk">{club.name}</p>
                <p className="text-xs text-ink-mist-dim">
                  С {new Date(club.founded_at).toLocaleDateString("ru-RU")} · {club.member_count}/11 участников
                </p>
                <div className="flex gap-4 font-mono text-sm font-bold">
                  <span className="text-accent-lime">🏆 {club.cups_count}</span>
                  <span className="text-accent-cyan">⭐ {club.stars_count}</span>
                </div>
                {club.description && <p className="text-sm text-ink-mist">{club.description}</p>}
              </div>
            )}
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
            >
              Закрыть
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
```

- [ ] **Step 2: Wire a click handler onto browse-list rows**

In `frontend/src/pages/ClubsPage.tsx`, add the popup import and open-on-click state to `ClubBrowseList`. Change the top imports (add one line after the `ClubLogo` import):

```typescript
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
```

In `ClubBrowseList`, add popup state right after the existing `const [requestSentId, setRequestSentId] = useState<number | null>(null);` line:

```typescript
  const [previewClubId, setPreviewClubId] = useState<number | null>(null);
```

Change the club row's `<div key={c.id} ...>` (currently just `className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3"`) to add a click handler on the name/logo area, without breaking the existing join/request button clicks (which must not also trigger the preview — `stopPropagation` on the button clicks already works implicitly since React's synthetic event bubbling requires an explicit stop only if the parent also has a handler; adding `stopPropagation` to the join/request buttons keeps this exact behavior unambiguous):

```tsx
          <div key={c.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <button
              onClick={() => setPreviewClubId(c.id)}
              className="flex flex-1 items-center gap-3 text-left"
            >
              <ClubLogo shape={c.logo_shape} color={c.logo_color} size={40} />
              <div className="flex-1">
                <p className="font-display text-sm font-bold text-ink-chalk">{c.name}</p>
                <p className="text-xs text-ink-mist-dim">{c.member_count}/11 участников</p>
              </div>
            </button>
            {c.club_type === "open" ? (
              <button
                onClick={() => joinMutation.mutate(c.id)}
                className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
              >
                Вступить
              </button>
            ) : requestSentId === c.id ? (
              <span className="rounded-xl bg-accent-green/10 px-3 py-2 text-xs font-semibold text-accent-green">
                Заявка отправлена
              </span>
            ) : (
              <button
                onClick={() => requestMutation.mutate(c.id)}
                disabled={requestMutation.isPending}
                className="rounded-xl bg-white/5 px-3 py-2 text-xs font-semibold text-ink-mist active:scale-95"
              >
                Подать заявку
              </button>
            )}
          </div>
```

(The join/request buttons are siblings of the new preview button, not nested inside it, so no click-through/bubbling concern exists — clicking "Вступить" never also opens the preview.)

Add the popup render at the end of `ClubBrowseList`'s returned JSX, right before the closing `</div>` of the outer `<div className="flex flex-col gap-4">`:

```tsx
      <ClubPreviewPopup clubId={previewClubId} onClose={() => setPreviewClubId(null)} />
    </div>
  );
}
```

- [ ] **Step 3: Typecheck and manual verification**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

Start the dev server (`docker compose up -d frontend` or the existing local run), open `/clubs` as a user not in a club, click a club row (not the join/request button), confirm the popup opens showing logo/name/founded date/member count/cups/stars, and closing it (backdrop click or "Закрыть") works.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/clubs/ClubPreviewPopup.tsx frontend/src/pages/ClubsPage.tsx
git commit -m "feat: add club preview popup to the browse list"
```

---

### Task 7: Frontend — apply entry point + tournament standings/fixtures/results page

**Files:**
- Create: `frontend/src/pages/TournamentPage.tsx`
- Modify: `frontend/src/pages/ClubsPage.tsx` (`ClubHome` gains the apply entry point)
- Modify: `frontend/src/App.tsx` (new route + import)

**Interfaces:**
- Consumes: Task 5's `fetchTournamentCurrent`/`fetchTournamentDetail`/`applyToTournament`/`TournamentCurrent`/`TournamentDetail` types, Task 6's `ClubPreviewPopup`.
- Produces: route `/clubs/tournament/:id`. Task 8's replay viewer is linked from this page's fixture rows (`/clubs/tournament/:id/matches/:matchId`), so this task creates that `<Link>`/`navigate` call even though the destination route doesn't exist until Task 8 — matches this plan's own dependency order (Task 8 comes right after).

- [ ] **Step 1: Add the apply entry point to `ClubHome`**

In `frontend/src/pages/ClubsPage.tsx`, add the tournament-current query and apply mutation to `ClubHome`, plus the API import. Change the top import block's `@/api/clubs` import from:

```typescript
import {
  acceptJoinRequest,
  claimDailyReward,
  createJoinRequest,
  fetchClubs,
  fetchMyClub,
  fetchMyJoinRequests,
  joinClub,
  kickMember,
  leaveClub,
  rejectJoinRequest,
} from "@/api/clubs";
```

to:

```typescript
import {
  acceptJoinRequest,
  applyToTournament,
  claimDailyReward,
  createJoinRequest,
  fetchClubs,
  fetchMyClub,
  fetchMyJoinRequests,
  fetchTournamentCurrent,
  joinClub,
  kickMember,
  leaveClub,
  rejectJoinRequest,
} from "@/api/clubs";
```

In `ClubHome`, add right after the existing `const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });` line:

```typescript
  const { data: tournamentCurrent } = useQuery({ queryKey: ["clubs", "tournament", "current"], queryFn: fetchTournamentCurrent });
  const [applyError, setApplyError] = useState<string | null>(null);
  const applyMutation = useMutation({
    mutationFn: applyToTournament,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "tournament", "current"] }); setApplyError(null); },
    onError: (err) => setApplyError(err instanceof ApiRequestError ? err.message : "Не удалось подать заявку"),
  });
```

Add the tournament UI block right after the existing "🎁 Клубные паки" manager button (after its closing `)}` — i.e. right after the block that ends with `🎁 Клубные паки\n        </button>\n      )}`):

```tsx
      {tournamentCurrent?.status === "not_queued" && isManager && (
        <button
          onClick={() => applyMutation.mutate()}
          disabled={applyMutation.isPending}
          className="rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99] disabled:opacity-40"
        >
          🏆 Подать заявку на турнир
        </button>
      )}
      {applyError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{applyError}</p>}
      {tournamentCurrent?.status === "queued" && (
        <div className="rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">
          🏆 В очереди на турнир — место {tournamentCurrent.queue_position}
        </div>
      )}
      {(tournamentCurrent?.status === "active" || tournamentCurrent?.status === "completed") && tournamentCurrent.tournament_id && (
        <button
          onClick={() => navigate(`/clubs/tournament/${tournamentCurrent.tournament_id}`)}
          className="rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          🏆 Турнир клуба
        </button>
      )}
```

- [ ] **Step 2: Create `TournamentPage.tsx`**

Create `frontend/src/pages/TournamentPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchTournamentDetail, fetchMyClub } from "@/api/clubs";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
import { ListSkeleton } from "@/components/common/Skeleton";

function resultsGateKey(tournamentId: number) {
  return `tournament_results_seen_${tournamentId}`;
}

export default function TournamentPage() {
  const { id } = useParams<{ id: string }>();
  const tournamentId = Number(id);
  const navigate = useNavigate();
  const [previewClubId, setPreviewClubId] = useState<number | null>(null);
  const [resultsRevealed, setResultsRevealed] = useState(() => localStorage.getItem(resultsGateKey(tournamentId)) === "1");

  const { data: tournament, isLoading } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId],
    queryFn: () => fetchTournamentDetail(tournamentId),
  });
  const { data: myClub } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });

  if (isLoading) return <ListSkeleton />;
  if (!tournament) return null;

  const revealResults = () => {
    localStorage.setItem(resultsGateKey(tournamentId), "1");
    setResultsRevealed(true);
  };

  const matchesByRound = new Map<number, typeof tournament.matches>();
  for (const m of tournament.matches) {
    matchesByRound.set(m.round_number, [...(matchesByRound.get(m.round_number) ?? []), m]);
  }
  const rounds = [...matchesByRound.keys()].sort((a, b) => b - a);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Турнир #{tournament.id}</h1>
        <p className="text-xs text-ink-mist-dim">
          {tournament.status === "completed" ? "Завершён" : `Тур ${tournament.rounds_simulated}/14`}
        </p>
      </div>

      {tournament.status === "completed" && !resultsRevealed && (
        <button
          onClick={revealResults}
          className="rounded-2xl bg-floodlight p-3 text-sm font-bold text-bg-base active:scale-95"
        >
          🏆 Турнир завершён — смотреть итоги
        </button>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Турнирная таблица</p>
        {tournament.standings.map((s) => (
          <button
            key={s.club_id}
            onClick={() => setPreviewClubId(s.club_id)}
            className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm ${
              s.club_id === myClub?.id ? "bg-accent-lime/12" : "bg-bg-surface"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{s.final_rank}</span>
              <span className={s.club_id === myClub?.id ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{s.club_name}</span>
            </div>
            <div className="flex items-center gap-3 font-mono text-xs text-ink-mist">
              <span>{s.goals_for}:{s.goals_against}</span>
              <span className="font-bold text-ink-chalk">{s.points} очк.</span>
            </div>
          </button>
        ))}
      </div>

      {tournament.status === "completed" && resultsRevealed && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Итоги турнира</p>
          {tournament.standings.map((s) => (
            <div key={s.club_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3 text-sm">
              <span className="text-ink-chalk">#{s.final_rank} {s.club_name}</span>
              <div className="flex items-center gap-2 font-mono text-xs">
                {s.cup_awarded && <span>🏆</span>}
                <span className={s.stars_delta && s.stars_delta > 0 ? "text-accent-lime" : "text-ink-mist"}>
                  ⭐ {s.stars_delta && s.stars_delta > 0 ? `+${s.stars_delta}` : s.stars_delta}
                </span>
                <span className="text-accent-cyan">🪙 +{s.budget_awarded}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Матчи</p>
        {rounds.map((round) => (
          <div key={round} className="flex flex-col gap-1.5">
            <p className="text-xs text-ink-mist-dim">Тур {round}</p>
            {matchesByRound.get(round)!.map((m) => {
              const clubA = tournament.standings.find((s) => s.club_id === m.club_a_id);
              const clubB = tournament.standings.find((s) => s.club_id === m.club_b_id);
              return (
                <button
                  key={m.id}
                  onClick={() => navigate(`/clubs/tournament/${tournament.id}/matches/${m.id}`)}
                  className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-left text-xs text-ink-chalk active:scale-[0.99]"
                >
                  <span>{clubA?.club_name ?? m.club_a_id}</span>
                  <span className="font-mono font-bold">{m.score_a} : {m.score_b}</span>
                  <span>{clubB?.club_name ?? m.club_b_id}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>

      <ClubPreviewPopup clubId={previewClubId} onClose={() => setPreviewClubId(null)} />
    </div>
  );
}
```

- [ ] **Step 3: Wire the route**

In `frontend/src/App.tsx`, add the import near the existing `import ClubsPage from "@/pages/ClubsPage";` line:

```typescript
import ClubsPage from "@/pages/ClubsPage";
import TournamentPage from "@/pages/TournamentPage";
```

Add the route right after `<Route path="/clubs/packs" element={<ClubPacksPage />} />` (line 192):

```tsx
        <Route path="/clubs/packs" element={<ClubPacksPage />} />
        <Route path="/clubs/tournament/:id" element={<TournamentPage />} />
```

- [ ] **Step 4: Typecheck and manual verification**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

Manually: with a running dev environment and 8 tournament-eligible clubs (or fewer, applying via captain accounts), apply one club to the tournament, confirm the "🏆 В очереди..." state shows, then once the 8th club applies confirm the "🏆 Турнир клуба" button appears and navigates to `/clubs/tournament/:id`, showing the standings table (all clubs at 0 points before any round is simulated) and an empty "Матчи" section (no rounds simulated yet — the section will just show nothing under "Матчи" until a round exists, which is expected since `rounds` is empty).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/TournamentPage.tsx frontend/src/pages/ClubsPage.tsx frontend/src/App.tsx
git commit -m "feat: add tournament apply entry point and standings/fixtures/results page"
```

---

### Task 8: Frontend — `TournamentMatchReplay` component + match route

**Files:**
- Create: `frontend/src/components/clubs/TournamentMatchReplay.tsx`
- Create: `frontend/src/pages/TournamentMatchPage.tsx`
- Modify: `frontend/src/App.tsx` (new route + import)
- Test: `frontend/src/test/TournamentMatchReplay.test.tsx`

**Interfaces:**
- Consumes: Task 5's `fetchTournamentMatch`/`TournamentMatchDetail`/`MatchEvent` (already description-complete from Task 1), Task 7's `TournamentPage` fixture-row `navigate()` call (already pointing at this route).
- Produces: route `/clubs/tournament/:id/matches/:matchId`. Nothing else in this plan consumes `TournamentMatchReplay` directly — it is used only from this page.

- [ ] **Step 1: Create the replay component**

Create `frontend/src/components/clubs/TournamentMatchReplay.tsx`. This reuses the `revealedCount`/`setTimeout` reveal mechanic `MatchSimulation` (`ArenaPage.tsx`) already proved out, as fresh standalone code — no `ActionPrompt`, no breakaway acknowledgment pause (nothing is pending here, every event is already resolved server-side), no win/loss/reward banner (tournament rewards are conclusion-level, shown on `TournamentPage`'s results section, not per-match):

```tsx
import { useEffect, useRef, useState } from "react";

import type { MatchEvent } from "@/types";

const EVENT_STEP_MS = 950;

export function TournamentMatchReplay({
  events,
  clubAName,
  clubBName,
  scoreA,
  scoreB,
}: {
  events: MatchEvent[];
  clubAName: string;
  clubBName: string;
  scoreA: number;
  scoreB: number;
}) {
  const [revealedCount, setRevealedCount] = useState(0);
  const [autoSkip, setAutoSkip] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const total = events.length;
  const caughtUp = revealedCount >= total;

  useEffect(() => {
    if (caughtUp) return;
    if (autoSkip) {
      setRevealedCount(total);
      return;
    }
    timerRef.current = setTimeout(() => setRevealedCount((c) => c + 1), EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [revealedCount, caughtUp, autoSkip, total]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [revealedCount]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setAutoSkip(true);
  };

  const revealed = events.slice(0, revealedCount);
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;
  const liveScoreA = revealed.filter((e) => e.event_type === "goal" && e.team === "a").length;
  const liveScoreB = revealed.filter((e) => e.event_type === "goal" && e.team === "b").length;

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {caughtUp ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : `${currentMinute}' · идёт матч...`}
        </span>
        {!caughtUp && !autoSkip && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      <p className="mt-1 text-center font-mono text-lg font-bold text-ink-chalk">{liveScoreA} : {liveScoreB}</p>
      <p className="text-center text-sm text-ink-mist">{clubAName} vs {clubBName}</p>

      {caughtUp && (
        <p className="mt-1 text-center font-display text-sm font-bold text-ink-chalk">
          Итоговый счёт: {scoreA} : {scoreB}
        </p>
      )}

      <div ref={logRef} className="mt-3 max-h-64 space-y-1 overflow-y-auto text-xs">
        {revealed.map((e, i) => (
          <p key={i} className={e.team === "a" ? "text-accent-green" : "text-ink-mist"}>
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.description}
          </p>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Create the page that fetches the match and club names**

Create `frontend/src/pages/TournamentMatchPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchTournamentDetail, fetchTournamentMatch } from "@/api/clubs";
import { ListSkeleton } from "@/components/common/Skeleton";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";

export default function TournamentMatchPage() {
  const { id, matchId } = useParams<{ id: string; matchId: string }>();
  const tournamentId = Number(id);
  const matchIdNum = Number(matchId);

  const { data: tournament } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId],
    queryFn: () => fetchTournamentDetail(tournamentId),
  });
  const { data: match, isLoading } = useQuery({
    queryKey: ["clubs", "tournament", tournamentId, "matches", matchIdNum],
    queryFn: () => fetchTournamentMatch(tournamentId, matchIdNum),
  });

  if (isLoading || !match) return <ListSkeleton />;

  const clubAName = tournament?.standings.find((s) => s.club_id === match.club_a_id)?.club_name ?? "Клуб A";
  const clubBName = tournament?.standings.find((s) => s.club_id === match.club_b_id)?.club_name ?? "Клуб B";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Тур {match.round_number}</h1>
      <TournamentMatchReplay
        events={match.event_log}
        clubAName={clubAName}
        clubBName={clubBName}
        scoreA={match.score_a}
        scoreB={match.score_b}
      />
    </div>
  );
}
```

- [ ] **Step 3: Write a Vitest test for the reveal mechanic**

Create `frontend/src/test/TournamentMatchReplay.test.tsx`, following `PlayerCard.test.tsx`'s render/query conventions — `TournamentMatchReplay` is a pure presentational component (props only, no API calls), matching that same testable shape:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import type { MatchEvent } from "@/types";

const events: MatchEvent[] = [
  { minute: 5, event_type: "shot", team: "a", description: "🎯 Реал бьёт — мимо ворот" },
  { minute: 20, event_type: "goal", team: "a", description: "⚽ Гол! Реал открывает счёт!" },
  { minute: 40, event_type: "save", team: "b", description: "🧤 Вратарь Барселоны спасает!" },
  { minute: 70, event_type: "goal", team: "b", description: "⚽ ГОЛ! Барселона забивает!" },
];

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("TournamentMatchReplay", () => {
  it("reveals events one at a time in order, climbing the live score", async () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);

    expect(screen.getByText("0 : 0")).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(950);
    expect(screen.getByText(/Реал бьёт/)).toBeInTheDocument();
    expect(screen.getByText("0 : 0")).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(950);
    expect(screen.getByText(/Реал открывает счёт/)).toBeInTheDocument();
    expect(screen.getByText("1 : 0")).toBeInTheDocument();
  });

  it("reaches a stable end state matching the final score after all events reveal", async () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);
    await vi.advanceTimersByTimeAsync(950 * events.length);
    await waitFor(() => expect(screen.getByText("Матч завершён")).toBeInTheDocument());
    expect(screen.getByText("2 : 2")).toBeInTheDocument();
    expect(screen.getByText("Итоговый счёт: 2 : 2")).toBeInTheDocument();
    // Advancing further must not throw or reveal past the end (caughtUp gates the effect's setTimeout).
    await vi.advanceTimersByTimeAsync(950 * 5);
    expect(screen.getByText("2 : 2")).toBeInTheDocument();
  });

  it("skip button jumps straight to the final state without waiting out every timer", () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);
    screen.getByText("Пропустить").click();
    expect(screen.getByText("Пропускаем матч...")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- TournamentMatchReplay`
Expected: all PASS.

- [ ] **Step 5: Wire the route**

In `frontend/src/App.tsx`, add the import next to `TournamentPage`'s:

```typescript
import TournamentMatchPage from "@/pages/TournamentMatchPage";
import TournamentPage from "@/pages/TournamentPage";
```

Add the route right after `<Route path="/clubs/tournament/:id" element={<TournamentPage />} />`:

```tsx
        <Route path="/clubs/tournament/:id" element={<TournamentPage />} />
        <Route path="/clubs/tournament/:id/matches/:matchId" element={<TournamentMatchPage />} />
```

- [ ] **Step 6: Typecheck and manual verification**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

Manually: from `TournamentPage` (Task 7), simulate a round via the backend (e.g. `docker compose exec backend python -c "..."` calling `simulate_next_round`, or wait for the bot's scheduled slot), then click a played fixture row and confirm the replay reveals events one at a time with real club names in the commentary, the live score climbs correctly, "Пропустить" jumps straight to the end, and the final score matches `match.score_a`/`score_b`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/clubs/TournamentMatchReplay.tsx frontend/src/pages/TournamentMatchPage.tsx frontend/src/test/TournamentMatchReplay.test.tsx frontend/src/App.tsx
git commit -m "feat: add standalone tournament match replay viewer"
```

---

### Task 9: Frontend — club leaderboard page

**Files:**
- Create: `frontend/src/pages/ClubLeaderboardPage.tsx`
- Modify: `frontend/src/App.tsx` (new route + import)

**Interfaces:**
- Consumes: Task 5's `fetchClubLeaderboard`/`ClubRankingResult`/`ClubRankingMetric` types.
- Produces: route `/clubs/leaderboard`. Nothing else in this plan consumes this page.

- [ ] **Step 1: Create the leaderboard page**

Create `frontend/src/pages/ClubLeaderboardPage.tsx`, mirroring `RankingPage.tsx`'s tabs + top-N + "my position" pattern exactly:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchClubLeaderboard } from "@/api/leaderboard";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import EmptyState from "@/components/common/EmptyState";
import { IconStar, IconTrophy, type IconProps } from "@/components/icons";
import type { ClubRankingEntry, ClubRankingMetric } from "@/types";

const METRICS: { value: ClubRankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "cups", label: "Кубки", Icon: IconTrophy },
  { value: "stars", label: "Звёзды", Icon: IconStar },
];

export default function ClubLeaderboardPage() {
  const [metric, setMetric] = useState<ClubRankingMetric>("cups");
  const { data, isLoading } = useQuery({ queryKey: ["clubs", "leaderboard", metric], queryFn: () => fetchClubLeaderboard(metric) });

  const meInTop = !!data?.me && data.top.some((e) => e.club_id === data.me!.club_id);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTrophy size={20} className="text-accent-lime" />
        Рейтинг клубов
      </h1>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {METRICS.map((m) => (
          <button
            key={m.value}
            onClick={() => setMetric(m.value)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
              metric === m.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <m.Icon size={13} />
            {m.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-ink-mist">Загрузка...</p>}

      {!isLoading && !data?.top.length ? (
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Стань первым клубом в рейтинге!" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <ClubRankingRow key={entry.club_id} entry={entry} highlight={entry.club_id === data?.me?.club_id} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
          <ClubRankingRow entry={data.me} highlight />
        </>
      )}
    </div>
  );
}

function ClubRankingRow({ entry, highlight = false }: { entry: ClubRankingEntry; highlight?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
        highlight ? "bg-accent-lime/12" : "bg-bg-surface"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <ClubLogo shape={entry.logo_shape} color={entry.logo_color} size={24} />
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.name}</span>
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
```

Note: this uses `IconStar`, which does not exist in `frontend/src/components/icons/index.tsx` today (the grep of that file's exports found no `IconStar`). Add it before using it. Every icon in this file wraps its shapes in the shared `IconBase` (`frontend/src/components/icons/Icon.tsx`, already imported at the top of `index.tsx` as `import { IconBase, type IconProps } from "./Icon";`) — `IconBase` supplies the `<svg>` element itself (24x24 viewBox, `fill="none"`, `stroke="currentColor"`, `strokeWidth={1.8}`, rounded caps/joins) so individual icon functions only render the inner shape, exactly like `IconBall`'s `<polygon>` + `<line>` rays (confirmed by direct read of both `Icon.tsx` and `IconBall`/`IconTrophy`'s real bodies — a raw hand-built `<svg>` would double-wrap and drop every one of those shared stroke/size defaults). Append, matching that exact pattern:

```tsx
export function IconStar(props: IconProps) {
  return (
    <IconBase {...props}>
      <polygon points="12,3 14.5,9.5 21,10 16,14.3 17.5,21 12,17.3 6.5,21 8,14.3 3,10 9.5,9.5" />
    </IconBase>
  );
}
```

(Insert it near `IconTrophy`/`IconGoal`, matching this file's existing loose grouping — exact position doesn't matter, this file has no enforced ordering convention based on the grep output already gathered.)

- [ ] **Step 2: Wire the route**

In `frontend/src/App.tsx`, add the import next to `RankingPage`'s existing import:

```typescript
import ClubLeaderboardPage from "@/pages/ClubLeaderboardPage";
```

Add the route right after `<Route path="/ranking" element={<RankingPage />} />` (line 196):

```tsx
        <Route path="/ranking" element={<RankingPage />} />
        <Route path="/clubs/leaderboard" element={<ClubLeaderboardPage />} />
```

- [ ] **Step 3: Typecheck and manual verification**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

Manually: navigate to `/clubs/leaderboard`, confirm both "Кубки"/"Звёзды" tabs load and render club rows with logos, and that a club with 0 in both metrics still appears in the list (not filtered out — `club_ranking_service.get_club_ranking` has no minimum-value filter, matching `ranking_service.get_ranking`'s own unfiltered behavior).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ClubLeaderboardPage.tsx frontend/src/components/icons/index.tsx frontend/src/App.tsx
git commit -m "feat: add club leaderboard page"
```

---

### Task 10: Bot — restore the `club_match` deep-link

**Files:**
- Modify: `bot/services/notifier.py:31-34`

**Interfaces:**
- Consumes: Task 7's `/clubs/tournament/:id` route (must exist before this restoration is meaningful — it does, as of Task 7, which runs before this final task).
- Produces: nothing consumed by a later task — this is the plan's last task.

- [ ] **Step 1: Restore the one line**

In `bot/services/notifier.py`, change `_MATCH_PATH_PREFIXES` (lines 31-34) from:

```python
_MATCH_PATH_PREFIXES = {
    "penalty_match": "/play/penalty/matches",
    "tactico_match": "/play/tactico/matches",
}
```

to:

```python
_MATCH_PATH_PREFIXES = {
    "penalty_match": "/play/penalty/matches",
    "tactico_match": "/play/tactico/matches",
    "club_match": "/clubs/tournament",
}
```

- [ ] **Step 2: Verify manually (no bot-side pytest harness exists in this codebase, per Phase 3b's own established, sanctioned contingency)**

Run: `docker compose exec backend python -c "from app.models.enums import NotificationType; print(NotificationType.club_match)"` to confirm the enum member name matches (`club_match`), then trigger a round simulation (via the bot's scheduler or a manual `simulate_next_round` call) and confirm a `club_match` notification's deep-link button now opens `/clubs/tournament/{tournament_id}` in the Mini App instead of falling back to the generic "open the app" keyboard.

- [ ] **Step 3: Commit**

```bash
git add bot/services/notifier.py
git commit -m "feat: restore club_match deep-link now that the tournament route exists"
```

---

## Final verification (after all 10 tasks)

Run the full backend and frontend check suites:

```bash
cd backend && pytest tests/ -v
cd frontend && npm run typecheck && npm run lint && npm run build
```

Manual end-to-end walkthrough: apply 8 real clubs to a tournament (dev-mode multi-session or 8 separate captain accounts), simulate at least one round, watch its replay end-to-end, confirm the deep-link notification (Phase 3b) now lands on the real standings page instead of the home-page fallback Phase 3b deliberately left in place, and check the leaderboard page shows the applying clubs.
