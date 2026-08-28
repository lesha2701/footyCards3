# Clubs Phase 3c-2: Admin Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin panel read-only visibility into clubs/tournaments (currently zero) and expose the 11 club/tournament `GameConfig` fields that are already admin-tunable per CLAUDE.md's "Economy config" rule but aren't surfaced in the admin UI at any layer.

**Architecture:** Two independent, additive pieces. (1) A fully greenfield `admin_clubs.py` router + `AdminClubsPage.tsx`, modeled directly on the existing `admin_users.py`/`AdminUsersPage.tsx` pattern (paginated searchable list, click-to-open modal with lazily-loaded tabs) — read-only, no mutations. (2) A three-layer schema-exposure fix (`GameConfigOut`/`GameConfigUpdate` Pydantic schemas → `GameConfig` TS interface → `AdminGamesPage.tsx`'s existing "Общие лимиты" section) for 11 fields that already exist on the `GameConfig` model but are invisible above the ORM layer.

**Tech Stack:** FastAPI + SQLAlchemy 2 async (backend), React 18 + TypeScript + TanStack Query (admin frontend, same app as the player-facing Mini App under `/admin/*`).

**Spec:** `docs/superpowers/specs/2026-08-28-clubs-phase3c2-admin-design.md`

## Global Constraints

- Read-only for clubs/tournaments in this phase — no moderation endpoints (force-disband, kick, budget adjustment). Every new route in `admin_clubs.py` is a `GET`.
- Admin clubs list includes disbanded clubs (`is_disbanded=True`), unlike the player-facing browse list which filters them out.
- The tournament tab shows the club's own stored `TournamentClubStanding` fields directly — no cross-club rank computation. `final_rank` comes straight from `TournamentClubResult`, already computed and stored by `tournament_reward_service.conclude_tournament` when a tournament completes.
- Exactly 11 `GameConfig` fields are in scope: `club_tournament_cooldown_hours`, `club_form_window_matches`, `club_form_bonus_per_result`, `club_tournament_budget_place_1` through `club_tournament_budget_place_8`. `maintenance_banner_until` and `last_update_broadcast_at` are explicitly out of scope (managed via dedicated `/admin/maintenance`/`/admin/broadcasts` endpoints, not the generic config editor).
- Every new admin route uses the exact two-part auth pattern every existing admin router uses: `dependencies=[Depends(get_current_admin)]` at the router level. No admin-attributed mutation exists in this phase, so no route needs an `admin: User` parameter or `log_action` call.

---

### Task 1: Backend — expose the 11 missing `GameConfig` fields

**Files:**
- Modify: `backend/app/schemas/admin.py:128-296` (`GameConfigOut`, `GameConfigUpdate`)
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: nothing new — `GameConfig` model already has all 11 fields (added in Phase 3a).
- Produces: `GET /admin/games/config` and `PUT /admin/games/config` now accept/return all 11 fields. Task 3 (frontend) consumes these exact field names.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_admin.py`:

```python
async def test_admin_can_update_club_tournament_game_config_fields(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.put(
        "/api/v1/admin/games/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "club_tournament_cooldown_hours": 4,
            "club_form_window_matches": 5,
            "club_form_bonus_per_result": 0.05,
            "club_tournament_budget_place_1": 1200,
            "club_tournament_budget_place_2": 900,
            "club_tournament_budget_place_3": 700,
            "club_tournament_budget_place_4": 500,
            "club_tournament_budget_place_5": 350,
            "club_tournament_budget_place_6": 250,
            "club_tournament_budget_place_7": 150,
            "club_tournament_budget_place_8": 80,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["club_tournament_cooldown_hours"] == 4
    assert body["club_form_window_matches"] == 5
    assert body["club_form_bonus_per_result"] == 0.05
    assert body["club_tournament_budget_place_1"] == 1200
    assert body["club_tournament_budget_place_8"] == 80

    get_resp = await client.get(
        "/api/v1/admin/games/config", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert get_resp.json()["club_tournament_budget_place_1"] == 1200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_admin.py::test_admin_can_update_club_tournament_game_config_fields -v`
Expected: FAIL — Pydantic silently drops the unrecognized fields from `GameConfigUpdate` (since it has no `extra="forbid"`), so `update_config`'s `payload.model_dump(exclude_unset=True)` never sets them, and the response won't contain them under `GameConfigOut` either — the `assert body["club_tournament_cooldown_hours"] == 4` assertion fails with a `KeyError` on `body["club_tournament_cooldown_hours"]` (the key is simply absent from the JSON response, since `GameConfigOut` doesn't declare it).

- [ ] **Step 3: Add the 11 fields to both schemas**

In `backend/app/schemas/admin.py`, change `GameConfigOut` (currently lines 128-211) — add these 11 fields right after `club_daily_reward_coins: int` (line 132):

```python
    club_creation_cost_coins: int
    club_daily_reward_coins: int
    club_tournament_cooldown_hours: int
    club_form_window_matches: int
    club_form_bonus_per_result: float
    club_tournament_budget_place_1: int
    club_tournament_budget_place_2: int
    club_tournament_budget_place_3: int
    club_tournament_budget_place_4: int
    club_tournament_budget_place_5: int
    club_tournament_budget_place_6: int
    club_tournament_budget_place_7: int
    club_tournament_budget_place_8: int
    memory_daily_reward_limit: int
```

Change `GameConfigUpdate` (currently lines 214-295) — add these 11 fields right after `club_daily_reward_coins: Optional[int] = Field(default=None, ge=0)` (line 216):

```python
    club_creation_cost_coins: Optional[int] = Field(default=None, ge=0)
    club_daily_reward_coins: Optional[int] = Field(default=None, ge=0)
    club_tournament_cooldown_hours: Optional[int] = Field(default=None, ge=0)
    club_form_window_matches: Optional[int] = Field(default=None, ge=1)
    club_form_bonus_per_result: Optional[float] = Field(default=None, ge=0)
    club_tournament_budget_place_1: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_2: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_3: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_4: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_5: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_6: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_7: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_8: Optional[int] = Field(default=None, ge=0)
    memory_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
```

(`ge=1` on `club_form_window_matches` matches the model's own semantics — a 0-match form window is meaningless; `ge=0` on the rest matches every other coin/hour field's existing validation style in this schema.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/test_admin.py -v`
Expected: all PASS, including the new test and every pre-existing test in the file (in particular `test_feature_flags_default_enabled_and_toggle_hides_them`, which also `PUT`s `/admin/games/config` — confirm it still passes unchanged, since `GameConfigUpdate`'s new fields are all `Optional` with no `exclude_unset` behavior change).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/admin.py backend/tests/test_admin.py
git commit -m "feat: expose club/tournament GameConfig fields on admin schema"
```

---

### Task 2: Backend — new `admin_clubs.py` read-only router

**Files:**
- Create: `backend/app/schemas/admin_clubs.py`
- Create: `backend/app/routers/admin_clubs.py`
- Modify: `backend/app/main.py:9-27,121-140` (router import + registration)
- Test: `backend/tests/test_admin_clubs.py`

**Interfaces:**
- Consumes: `Club`, `ClubMember`, `ClubBudgetTransaction`, `Tournament`, `TournamentClub`, `TournamentClubStanding`, `TournamentClubResult` models (all already exist, unchanged by this task). `get_current_admin` dependency (`app.core.dependencies`). `Page`/`PageParams` (`app.core.pagination`).
- Produces: `GET /admin/clubs`, `GET /admin/clubs/{id}`, `GET /admin/clubs/{id}/members`, `GET /admin/clubs/{id}/budget-transactions`, `GET /admin/clubs/{id}/tournaments`. Task 4 (frontend) consumes these exact paths and the exact field names on `AdminClubSummaryOut`/`AdminClubDetailOut`/`AdminClubMemberOut`/`AdminClubBudgetTransactionOut`/`AdminClubTournamentOut` defined below.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_clubs.py`:

```python
import pytest_asyncio

from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.enums import ClubBudgetTransactionType, Position
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


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _make_club(client, db_session, bot_token, telegram_id, name, club_type="open"):
    await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": club_type, "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return await db_session.get(Club, resp.json()["id"])


async def test_list_clubs_requires_admin(client):
    resp = await client.get("/api/v1/admin/clubs")
    assert resp.status_code == 401


async def test_list_clubs_filters_by_search_and_includes_disbanded(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await _make_club(client, db_session, bot_token, 870001, "Красные дьяволы")
    disbanded = await _make_club(client, db_session, bot_token, 870002, "Синие орлы")
    disbanded.is_disbanded = True
    db_session.add(disbanded)
    await db_session.commit()

    resp = await client.get("/api/v1/admin/clubs", params={"search": "дьявол"}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Красные дьяволы"

    resp2 = await client.get("/api/v1/admin/clubs", params={"search": "орл"}, headers=auth)
    assert resp2.json()["items"][0]["is_disbanded"] is True


async def test_get_club_detail_returns_full_fields_and_404s_for_missing(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870003, "Клуб детали")

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_count"] == 1
    assert body["invite_code"] == club.invite_code
    assert body["description"] == ""

    missing_resp = await client.get("/api/v1/admin/clubs/999999", headers=auth)
    assert missing_resp.status_code == 404


async def test_get_club_members_returns_roster(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870004, "Клуб состава")

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}/members", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["role"] == "captain"


async def test_get_club_budget_transactions_paginated(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870005, "Клуб бюджета")

    db_session.add(
        ClubBudgetTransaction(
            club_id=club.id, amount=200, balance_before=0, balance_after=200,
            type=ClubBudgetTransactionType.daily_claim, description="Ежедневная награда",
        )
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}/budget-transactions", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == 200
    assert body["items"][0]["type"] == "daily_claim"


async def test_get_club_tournaments_shows_null_rewards_before_completion_and_real_values_after(
    client, db_session, bot_token
):
    from app.services.tournament_simulation_service import simulate_next_round
    from app.services.tournament_queue_service import apply_to_tournament

    auth = await _admin_auth(client, bot_token)
    clubs_and_captains = []
    tournament_id = None
    for i in range(8):
        await client.post("/api/v1/auth/session", headers=telegram_headers(870100 + i, bot_token))
        create_resp = await client.post(
            "/api/v1/clubs", headers=telegram_headers(870100 + i, bot_token),
            json={"name": f"Клуб турнира {i}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
        )
        club = await db_session.get(Club, create_resp.json()["id"])
        second_telegram_id = 870100 + i + 900_000
        await client.post("/api/v1/auth/session", headers=telegram_headers(second_telegram_id, bot_token))
        await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(second_telegram_id, bot_token))
        captain = await get_user_by_telegram_id(db_session, 870100 + i)
        result = await apply_to_tournament(db_session, captain)
        clubs_and_captains.append(club)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id

    assert tournament_id is not None
    club0 = clubs_and_captains[0]

    mid_resp = await client.get(f"/api/v1/admin/clubs/{club0.id}/tournaments", headers=auth)
    assert mid_resp.status_code == 200
    mid_body = mid_resp.json()
    assert len(mid_body) == 1
    assert mid_body[0]["tournament_id"] == tournament_id
    assert mid_body[0]["status"] == "active"
    assert mid_body[0]["final_rank"] is None
    assert mid_body[0]["budget_awarded"] is None

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    done_resp = await client.get(f"/api/v1/admin/clubs/{club0.id}/tournaments", headers=auth)
    done_body = done_resp.json()
    assert done_body[0]["status"] == "completed"
    assert done_body[0]["budget_awarded"] is not None
    assert done_body[0]["final_rank"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_admin_clubs.py -v`
Expected: FAIL — `404 Not Found` on every request (no `/admin/clubs*` route exists yet), or a collection error if the file imports something not yet created.

- [ ] **Step 3: Create the schemas**

Create `backend/app/schemas/admin_clubs.py`:

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import ClubBudgetTransactionType, ClubLogoShape, ClubRole, ClubType, TournamentStatus


class AdminClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    captain_id: int
    member_count: int
    budget: int
    cups_count: int
    stars_count: int
    founded_at: datetime
    is_disbanded: bool


class AdminClubDetailOut(AdminClubSummaryOut):
    description: str
    invite_code: str
    last_tournament_applied_at: Optional[datetime] = None


class AdminClubMemberOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    role: ClubRole
    joined_at: datetime


class AdminClubBudgetTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    balance_before: int
    balance_after: int
    type: ClubBudgetTransactionType
    description: str
    created_at: datetime


class AdminClubTournamentOut(BaseModel):
    tournament_id: int
    status: TournamentStatus
    rounds_simulated: int
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    budget_awarded: Optional[int] = None
    stars_delta: Optional[int] = None
    cup_awarded: Optional[bool] = None
```

- [ ] **Step 4: Create the router**

Create `backend/app/routers/admin_clubs.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.club import Club, ClubMember
from app.models.club_budget import ClubBudgetTransaction
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
from app.schemas.admin_clubs import (
    AdminClubBudgetTransactionOut,
    AdminClubDetailOut,
    AdminClubMemberOut,
    AdminClubSummaryOut,
    AdminClubTournamentOut,
)

router = APIRouter(prefix="/admin/clubs", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[AdminClubSummaryOut])
async def list_clubs(search: Optional[str] = None, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    member_count_subq = (
        select(ClubMember.club_id, func.count(ClubMember.id).label("cnt"))
        .group_by(ClubMember.club_id)
        .subquery()
    )
    query = (
        select(Club, func.coalesce(member_count_subq.c.cnt, 0))
        .outerjoin(member_count_subq, member_count_subq.c.club_id == Club.id)
    )
    count_query = select(func.count(Club.id))
    if search:
        pattern = f"%{search}%"
        query = query.where(Club.name.ilike(pattern))
        count_query = count_query.where(Club.name.ilike(pattern))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Club.founded_at.desc()).offset(params.offset).limit(params.page_size)
    rows = (await db.execute(query)).all()
    items = [
        AdminClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape, logo_color=c.logo_color,
            captain_id=c.captain_id, member_count=count, budget=c.budget, cups_count=c.cups_count,
            stars_count=c.stars_count, founded_at=c.founded_at, is_disbanded=c.is_disbanded,
        )
        for c, count in rows
    ]
    return Page.build(items, total, params)


async def _get_club_or_404(db: AsyncSession, club_id: int) -> Club:
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Club not found")
    return club


async def _member_count(db: AsyncSession, club_id: int) -> int:
    return (await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))).scalar_one()


@router.get("/{club_id}", response_model=AdminClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db)):
    club = await _get_club_or_404(db, club_id)
    count = await _member_count(db, club_id)
    return AdminClubDetailOut(
        id=club.id, name=club.name, club_type=club.club_type, logo_shape=club.logo_shape, logo_color=club.logo_color,
        captain_id=club.captain_id, member_count=count, budget=club.budget, cups_count=club.cups_count,
        stars_count=club.stars_count, founded_at=club.founded_at, is_disbanded=club.is_disbanded,
        description=club.description, invite_code=club.invite_code,
        last_tournament_applied_at=club.last_tournament_applied_at,
    )


@router.get("/{club_id}/members", response_model=list[AdminClubMemberOut])
async def get_club_members(club_id: int, db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    rows = (
        await db.execute(
            select(ClubMember, User)
            .join(User, User.id == ClubMember.user_id)
            .where(ClubMember.club_id == club_id)
            .order_by(ClubMember.joined_at)
        )
    ).all()
    return [
        AdminClubMemberOut(user_id=u.id, username=u.username, first_name=u.first_name, role=m.role, joined_at=m.joined_at)
        for m, u in rows
    ]


@router.get("/{club_id}/budget-transactions", response_model=Page[AdminClubBudgetTransactionOut])
async def get_club_budget_transactions(club_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    total = (
        await db.execute(select(func.count(ClubBudgetTransaction.id)).where(ClubBudgetTransaction.club_id == club_id))
    ).scalar_one()
    result = await db.execute(
        select(ClubBudgetTransaction)
        .where(ClubBudgetTransaction.club_id == club_id)
        .order_by(ClubBudgetTransaction.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    items = [AdminClubBudgetTransactionOut.model_validate(t) for t in result.scalars().all()]
    return Page.build(items, total, params)


@router.get("/{club_id}/tournaments", response_model=list[AdminClubTournamentOut])
async def get_club_tournaments(club_id: int, db: AsyncSession = Depends(get_db)):
    await _get_club_or_404(db, club_id)
    rows = (
        await db.execute(
            select(TournamentClub, Tournament, TournamentClubStanding)
            .join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .join(
                TournamentClubStanding,
                (TournamentClubStanding.tournament_id == TournamentClub.tournament_id)
                & (TournamentClubStanding.club_id == TournamentClub.club_id),
            )
            .where(TournamentClub.club_id == club_id)
            .order_by(Tournament.id.desc())
        )
    ).all()

    tournament_ids = [t.id for _, t, _ in rows]
    results_by_tournament: dict[int, TournamentClubResult] = {}
    if tournament_ids:
        result_rows = (
            await db.execute(
                select(TournamentClubResult).where(
                    TournamentClubResult.club_id == club_id, TournamentClubResult.tournament_id.in_(tournament_ids)
                )
            )
        ).scalars().all()
        results_by_tournament = {r.tournament_id: r for r in result_rows}

    return [
        AdminClubTournamentOut(
            tournament_id=t.id, status=t.status, rounds_simulated=t.rounds_simulated,
            points=s.points, goals_for=s.goals_for, goals_against=s.goals_against,
            final_rank=results_by_tournament[t.id].final_rank if t.id in results_by_tournament else None,
            budget_awarded=results_by_tournament[t.id].budget_awarded if t.id in results_by_tournament else None,
            stars_delta=results_by_tournament[t.id].stars_delta if t.id in results_by_tournament else None,
            cup_awarded=results_by_tournament[t.id].cup_awarded if t.id in results_by_tournament else None,
        )
        for _, t, s in rows
    ]
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, add `admin_clubs` to the import block (currently lines 9-27) — insert it alphabetically between `admin_club_packs` and `admin_coin_packages`:

```python
from app.routers import (
    admin_badges,
    admin_card_collections,
    admin_card_upgrades,
    admin_club_packs,
    admin_clubs,
    admin_coin_packages,
    admin_dashboard,
    admin_games,
```

Add the registration line right after `app.include_router(admin_club_packs.router, prefix=API_PREFIX)` (currently line 129):

```python
app.include_router(admin_club_packs.router, prefix=API_PREFIX)
app.include_router(admin_clubs.router, prefix=API_PREFIX)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_admin_clubs.py -v`
Expected: all PASS.

Then run: `docker compose exec backend pytest tests/ -q` (full suite) to confirm no regression from the new router registration.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/admin_clubs.py backend/app/routers/admin_clubs.py backend/app/main.py backend/tests/test_admin_clubs.py
git commit -m "feat: add read-only admin clubs/tournaments router"
```

---

### Task 3: Frontend — extend `AdminGamesPage.tsx` with the 11 fields

**Files:**
- Modify: `frontend/src/admin/types.ts:92-174` (`GameConfig` interface)
- Modify: `frontend/src/admin/pages/AdminGamesPage.tsx:63-70` ("Общие лимиты" section)

**Interfaces:**
- Consumes: Task 1's `GameConfigOut`/`GameConfigUpdate` (already returns/accepts these 11 fields).
- Produces: nothing consumed by a later task in this plan.

- [ ] **Step 1: Add the 11 fields to the `GameConfig` TS interface**

In `frontend/src/admin/types.ts`, change the `GameConfig` interface (lines 92-174) — add these 11 fields right after `club_daily_reward_coins: number;` (line 94):

```typescript
export interface GameConfig {
  club_creation_cost_coins: number;
  club_daily_reward_coins: number;
  club_tournament_cooldown_hours: number;
  club_form_window_matches: number;
  club_form_bonus_per_result: number;
  club_tournament_budget_place_1: number;
  club_tournament_budget_place_2: number;
  club_tournament_budget_place_3: number;
  club_tournament_budget_place_4: number;
  club_tournament_budget_place_5: number;
  club_tournament_budget_place_6: number;
  club_tournament_budget_place_7: number;
  club_tournament_budget_place_8: number;
  memory_daily_reward_limit: number;
```

(Every following field stays exactly as it already is — this only inserts 11 new lines after `club_daily_reward_coins`.)

- [ ] **Step 2: Add the 11 fields to the "Общие лимиты" section**

In `frontend/src/admin/pages/AdminGamesPage.tsx`, change the "Общие лимиты" section (currently lines 63-70) from:

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Общие лимиты</p>
        <div className="grid grid-cols-2 gap-3">
          {field("hourly_game_limit", "Лимит игр в час (на каждую игру)")}
          {field("club_creation_cost_coins", "Стоимость создания клуба")}
          {field("club_daily_reward_coins", "Ежедневная награда клуба")}
        </div>
      </section>
```

to:

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Общие лимиты</p>
        <div className="grid grid-cols-2 gap-3">
          {field("hourly_game_limit", "Лимит игр в час (на каждую игру)")}
          {field("club_creation_cost_coins", "Стоимость создания клуба")}
          {field("club_daily_reward_coins", "Ежедневная награда клуба")}
          {field("club_tournament_cooldown_hours", "Кулдаун между заявками на турнир, часы")}
          {field("club_form_window_matches", "Окно формы клуба, матчей")}
          {field("club_form_bonus_per_result", "Бонус формы за результат (напр. 0.02)")}
          {field("club_tournament_budget_place_1", "Награда бюджетом за 1-е место")}
          {field("club_tournament_budget_place_2", "Награда бюджетом за 2-е место")}
          {field("club_tournament_budget_place_3", "Награда бюджетом за 3-е место")}
          {field("club_tournament_budget_place_4", "Награда бюджетом за 4-е место")}
          {field("club_tournament_budget_place_5", "Награда бюджетом за 5-е место")}
          {field("club_tournament_budget_place_6", "Награда бюджетом за 6-е место")}
          {field("club_tournament_budget_place_7", "Награда бюджетом за 7-е место")}
          {field("club_tournament_budget_place_8", "Награда бюджетом за 8-е место")}
        </div>
      </section>
```

(No changes needed to `api.ts` — `fetchGameConfig`/`updateGameConfig` already round-trip the whole `GameConfig` object, so the 11 new fields flow through automatically once they're on the type and rendered by the existing `field(key, label)` helper closure, unmodified.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS with zero errors.

- [ ] **Step 4: Manual verification**

With the local dev environment running (`docker compose up -d backend postgres` and the frontend dev server), open `/admin/games` as an admin, confirm all 11 new fields render with real current values in "Общие лимиты", change one, click "Сохранить настройки", reload the page, and confirm the change persisted.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/admin/types.ts frontend/src/admin/pages/AdminGamesPage.tsx
git commit -m "feat: expose club/tournament GameConfig fields in admin games page"
```

---

### Task 4: Frontend — `AdminClubsPage.tsx`

**Files:**
- Modify: `frontend/src/admin/types.ts` (append new types after the existing admin types)
- Modify: `frontend/src/admin/api.ts` (append new API functions)
- Create: `frontend/src/admin/pages/AdminClubsPage.tsx`
- Modify: `frontend/src/admin/AdminLayout.tsx:6-24` (nav entry)
- Modify: `frontend/src/App.tsx:11,150` (import + route)

**Interfaces:**
- Consumes: Task 2's 5 endpoints and their exact response shapes (`AdminClubSummaryOut`, `AdminClubDetailOut`, `AdminClubMemberOut`, `AdminClubBudgetTransactionOut`, `AdminClubTournamentOut`).
- Produces: route `/admin/clubs`. Nothing else in this plan consumes it.

- [ ] **Step 1: Add the TS types**

In `frontend/src/admin/types.ts`, append after the `AdminUser` interface's closing brace (find it in the file — it directly follows the `Dashboard` interface, per the file's current structure):

```typescript
export interface AdminClub {
  id: number;
  name: string;
  club_type: "open" | "closed";
  logo_shape: "shield" | "circle" | "hexagon" | "star" | "diamond" | "banner" | "crest" | "chevron";
  logo_color: string;
  captain_id: number;
  member_count: number;
  budget: number;
  cups_count: number;
  stars_count: number;
  founded_at: string;
  is_disbanded: boolean;
}

export interface AdminClubDetail extends AdminClub {
  description: string;
  invite_code: string;
  last_tournament_applied_at: string | null;
}

export interface AdminClubMember {
  user_id: number;
  username: string | null;
  first_name: string | null;
  role: "captain" | "assistant" | "member";
  joined_at: string;
}

export interface AdminClubBudgetTransaction {
  id: number;
  amount: number;
  balance_before: number;
  balance_after: number;
  type: "daily_claim" | "pack_purchase" | "tournament_reward";
  description: string;
  created_at: string;
}

export interface AdminClubTournament {
  tournament_id: number;
  status: "active" | "completed";
  rounds_simulated: number;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  budget_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}
```

- [ ] **Step 2: Add the API functions**

In `frontend/src/admin/api.ts`, add the new types to the existing `@/admin/types` import block (currently lines 19-33) — change:

```typescript
import type {
  AdminActionLog,
  AdminUser,
  AdminWheelPrize,
```

to:

```typescript
import type {
  AdminActionLog,
  AdminClub,
  AdminClubBudgetTransaction,
  AdminClubDetail,
  AdminClubMember,
  AdminClubTournament,
  AdminUser,
  AdminWheelPrize,
```

Then append these functions to the end of the file:

```typescript

// --- Clubs ---
export async function fetchAdminClubs(search: string, page: number): Promise<Page<AdminClub>> {
  const { data } = await api.get<Page<AdminClub>>("/admin/clubs", { params: { search: search || undefined, page } });
  return data;
}

export async function fetchAdminClub(id: number): Promise<AdminClubDetail> {
  const { data } = await api.get<AdminClubDetail>(`/admin/clubs/${id}`);
  return data;
}

export async function fetchAdminClubMembers(id: number): Promise<AdminClubMember[]> {
  const { data } = await api.get<AdminClubMember[]>(`/admin/clubs/${id}/members`);
  return data;
}

export async function fetchAdminClubBudgetTransactions(id: number, page = 1): Promise<Page<AdminClubBudgetTransaction>> {
  const { data } = await api.get<Page<AdminClubBudgetTransaction>>(`/admin/clubs/${id}/budget-transactions`, { params: { page } });
  return data;
}

export async function fetchAdminClubTournaments(id: number): Promise<AdminClubTournament[]> {
  const { data } = await api.get<AdminClubTournament[]>(`/admin/clubs/${id}/tournaments`);
  return data;
}
```

- [ ] **Step 3: Create `AdminClubsPage.tsx`**

Create `frontend/src/admin/pages/AdminClubsPage.tsx`, mirroring `AdminUsersPage.tsx`'s exact structure (search + paginated table + click-to-open modal with lazily-loaded tabs), extended to 4 tabs:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchAdminClub,
  fetchAdminClubBudgetTransactions,
  fetchAdminClubMembers,
  fetchAdminClubs,
  fetchAdminClubTournaments,
} from "@/admin/api";
import type { AdminClub } from "@/admin/types";

const ROLE_LABELS: Record<string, string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };

export default function AdminClubsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AdminClub | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["admin-clubs", search, page], queryFn: () => fetchAdminClubs(search, page) });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Клубы</h1>

      <input
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        placeholder="Поиск по названию..."
        className="max-w-sm rounded-xl bg-bg-surface px-4 py-2.5 text-sm outline-none"
      />

      <div className="overflow-x-auto rounded-2xl border border-white/5">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-bg-surface text-left text-xs text-slate-400">
            <tr>
              <th className="px-3 py-2">Название</th>
              <th className="px-3 py-2">Тип</th>
              <th className="px-3 py-2">Участники</th>
              <th className="px-3 py-2">Бюджет</th>
              <th className="px-3 py-2">🏆 / ⭐</th>
              <th className="px-3 py-2">Статус</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className="border-t border-white/5">
                <td className="px-3 py-2">{c.name}</td>
                <td className="px-3 py-2 text-slate-400">{c.club_type === "open" ? "Открытый" : "Закрытый"}</td>
                <td className="px-3 py-2">{c.member_count}/11</td>
                <td className="px-3 py-2 text-amber-300">🪙{c.budget}</td>
                <td className="px-3 py-2 text-slate-400">{c.cups_count} / {c.stars_count}</td>
                <td className="px-3 py-2">
                  {c.is_disbanded ? <span className="text-red-400">Расформирован</span> : <span className="text-emerald-400">Активен</span>}
                </td>
                <td className="px-3 py-2">
                  <button onClick={() => setSelected(c)} className="rounded-lg bg-accent px-3 py-1 text-xs font-bold text-bg-base">
                    Открыть
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <p className="p-4 text-sm text-slate-400">Загрузка...</p>}
      </div>

      {data && data.pages > 1 && (
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">←</button>
          <span className="text-sm text-slate-400">{page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg bg-white/5 px-3 py-1.5 text-sm disabled:opacity-30">→</button>
        </div>
      )}

      {selected && <ClubDetailModal clubId={selected.id} onClose={() => setSelected(null)} />}
    </div>
  );
}

function ClubDetailModal({ clubId, onClose }: { clubId: number; onClose: () => void }) {
  const [tab, setTab] = useState<"overview" | "members" | "budget" | "tournaments">("overview");

  const { data: club } = useQuery({ queryKey: ["admin-club", clubId], queryFn: () => fetchAdminClub(clubId) });
  const { data: members } = useQuery({
    queryKey: ["admin-club-members", clubId],
    queryFn: () => fetchAdminClubMembers(clubId),
    enabled: tab === "members",
  });
  const { data: budgetTransactions } = useQuery({
    queryKey: ["admin-club-budget", clubId],
    queryFn: () => fetchAdminClubBudgetTransactions(clubId),
    enabled: tab === "budget",
  });
  const { data: tournaments } = useQuery({
    queryKey: ["admin-club-tournaments", clubId],
    queryFn: () => fetchAdminClubTournaments(clubId),
    enabled: tab === "tournaments",
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <p className="font-display text-lg font-bold">{club?.name ?? "..."} (#{clubId})</p>
          <button onClick={onClose} className="rounded-full bg-white/5 px-3 py-1.5 text-sm">Закрыть</button>
        </div>

        <div className="mb-4 flex gap-2">
          {(["overview", "members", "budget", "tournaments"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${tab === t ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
            >
              {t === "overview" ? "Обзор" : t === "members" ? "Участники" : t === "budget" ? "Бюджет" : "Турниры"}
            </button>
          ))}
        </div>

        {tab === "overview" && club && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Info label="Тип" value={club.club_type === "open" ? "Открытый" : "Закрытый"} />
            <Info label="Капитан (ID)" value={club.captain_id} />
            <Info label="Основан" value={new Date(club.founded_at).toLocaleDateString("ru-RU")} />
            <Info label="Бюджет" value={`🪙${club.budget}`} />
            <Info label="Кубки / Звёзды" value={`🏆${club.cups_count} / ⭐${club.stars_count}`} />
            <Info label="Код приглашения" value={club.invite_code} />
            <Info label="Статус" value={club.is_disbanded ? "Расформирован" : "Активен"} />
            <Info
              label="Последняя заявка на турнир"
              value={club.last_tournament_applied_at ? new Date(club.last_tournament_applied_at).toLocaleDateString("ru-RU") : "—"}
            />
            {club.description && <div className="col-span-2"><Info label="Описание" value={club.description} /></div>}
          </div>
        )}

        {tab === "members" && (
          <div className="flex flex-col gap-2">
            {members?.map((m) => (
              <div key={m.user_id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <span>{m.username ?? m.first_name ?? `#${m.user_id}`}</span>
                <span className="text-slate-400">{ROLE_LABELS[m.role]}</span>
              </div>
            ))}
            {!members?.length && <p className="text-sm text-slate-500">Нет участников</p>}
          </div>
        )}

        {tab === "budget" && (
          <div className="flex flex-col gap-2">
            {budgetTransactions?.items.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <span>{t.description || t.type}</span>
                <span className={t.amount >= 0 ? "text-emerald-400" : "text-red-400"}>{t.amount}</span>
              </div>
            ))}
            {!budgetTransactions?.items.length && <p className="text-sm text-slate-500">Нет транзакций</p>}
          </div>
        )}

        {tab === "tournaments" && (
          <div className="flex flex-col gap-2">
            {tournaments?.map((t) => (
              <div key={t.tournament_id} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
                <div>
                  <p>Турнир #{t.tournament_id} — {t.status === "completed" ? "завершён" : `тур ${t.rounds_simulated}/14`}</p>
                  <p className="text-slate-400">{t.points} очк. · {t.goals_for}:{t.goals_against}</p>
                </div>
                {t.status === "completed" && (
                  <div className="text-right">
                    <p>#{t.final_rank}{t.cup_awarded ? " 🏆" : ""}</p>
                    <p className="text-slate-400">⭐{t.stars_delta} · 🪙+{t.budget_awarded}</p>
                  </div>
                )}
              </div>
            ))}
            {!tournaments?.length && <p className="text-sm text-slate-500">Клуб не участвовал в турнирах</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface px-3 py-2">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-semibold text-slate-100">{value}</p>
    </div>
  );
}
```

- [ ] **Step 4: Wire the nav entry**

In `frontend/src/admin/AdminLayout.tsx`, add a new entry to `SECTIONS` (currently lines 6-24) right after `{ to: "/admin/club-packs", label: "Клубные паки", icon: "🏟️" }`:

```typescript
  { to: "/admin/club-packs", label: "Клубные паки", icon: "🏟️" },
  { to: "/admin/clubs", label: "Клубы", icon: "👥" },
```

(`👥` is already used by `/admin/users` — that's fine, `SECTIONS` has no uniqueness requirement on icons, and no other unused people-related emoji fits better; this matches the plan's earlier note that only `🏟️` needed to be avoided since it's the icon immediately adjacent in the nav.)

- [ ] **Step 5: Wire the route**

In `frontend/src/App.tsx`, add the import next to the existing `AdminClubPacksPage` import (currently line 11):

```typescript
import AdminClubPacksPage from "@/admin/pages/AdminClubPacksPage";
import AdminClubsPage from "@/admin/pages/AdminClubsPage";
```

Add the route right after `<Route path="club-packs" element={<AdminClubPacksPage />} />` (currently in the `/admin` route block):

```tsx
        <Route path="club-packs" element={<AdminClubPacksPage />} />
        <Route path="clubs" element={<AdminClubsPage />} />
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS with zero errors.

- [ ] **Step 7: Manual verification**

With the local dev environment running, open `/admin/clubs` as an admin. Confirm the list loads, search filters by name, pagination works if more than 20 clubs exist (page_size default). Open a club and confirm all 4 tabs render — in particular, open a club that has completed a tournament (or complete one via 14 rounds of `simulate_next_round` against a local test club) and confirm the "Турниры" tab shows the final rank/cup/stars/budget once completed. Confirm a disbanded club shows "Расформирован" in the list.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/admin/types.ts frontend/src/admin/api.ts frontend/src/admin/pages/AdminClubsPage.tsx frontend/src/admin/AdminLayout.tsx frontend/src/App.tsx
git commit -m "feat: add read-only admin clubs page"
```

---

## Final verification (after all 4 tasks)

```bash
docker compose exec backend pytest tests/ -q
cd frontend && npm run typecheck && npm run test
```

(`npm run lint` remains broken repo-wide — missing `eslint.config.js`, a pre-existing gap unrelated to this plan, already noted during Phase 3c-1.)

Manual end-to-end walkthrough: log in as admin, open `/admin/games`, confirm all 11 new fields are visible and editable and persist on save; open `/admin/clubs`, search, open a club with a completed tournament, confirm every tab renders real data including the tournament results.
