# Player Tournaments — Stars, Cups & Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-number player-tournament rating with clubs' proven two-metric model — cups (tournament wins) and stars (place-based delta, ±5) — add a summary bar to the tournament hub (tournaments played / stars / cups), and add an all-time stats page mirroring the club one.

**Architecture:** Pure rename-and-extend of the already-shipped player-tournament backend (`main`, commit `f089717`) to match the already-shipped club pattern (`Club.stars_count`/`cups_count`, `club_ranking_service.py`, `club_stats_service.py`, `ClubLeaderboardPage.tsx`, `ClubStatsPage.tsx`) field-for-field. No new subsystem — a migration renames 2 columns and adds 2, plus 2 new service files and 2 new frontend pages copied from their club counterparts.

**Tech Stack:** Python 3.12 (test venv: 3.14), FastAPI, async SQLAlchemy 2, Alembic, pytest; React 18 + TypeScript + Vite + TanStack Query.

**Spec:** This plan supersedes the rating-only design in `docs/superpowers/specs/2026-09-25-league-tournaments-design.md` for the leaderboard/stats surface — approved in chat on 2026-09-28 ("рейтинг турниров должен быть как по кубкам так и по звездам..."). Builds on `docs/superpowers/plans/2026-09-25-player-tournaments-backend.md` and `docs/superpowers/plans/2026-09-28-player-tournaments-frontend.md`, both already merged to `main`.

## Global Constraints

- Mirror the club implementation exactly wherever one exists — `club_ranking_service.py` → `player_tournament_ranking_service.py`, `club_stats_service.py` → `player_tournament_stats_service.py`, `ClubLeaderboardPage.tsx` → rewritten `PlayerTournamentRatingPage.tsx`, `ClubStatsPage.tsx` → new `PlayerTournamentStatsPage.tsx`. Do not invent a different shape.
- New Alembic revision `0120`, `down_revision = "0119"` (current head on this branch).
- Renames (not new parallel fields): `User.tournament_rating` → `User.tournament_stars_count`; `GameConfig.ptour_rating_by_place` → `GameConfig.ptour_stars_by_place`; `PlayerTournamentResult.rating_delta` → `PlayerTournamentResult.stars_delta`. Add: `User.tournament_cups_count` (int, default 0), `PlayerTournamentResult.cup_awarded` (bool, default false, true iff `final_rank == 1`).
- The migration must backfill `cup_awarded` and `tournament_cups_count` from existing `player_tournament_results` rows (this branch's dev database already has one completed tournament) — never leave historical cup counts at 0 after the rename.
- The old `GET /player-tournaments/rating` endpoint, `TournamentRatingRowOut` schema, and `get_rating_leaderboard` service function are removed entirely, replaced by `GET /player-tournaments/leaderboard?metric=cups|stars` — no dead parallel code path.
- FastAPI route registration order matters (Starlette matches in declaration order, unlike React Router): `/leaderboard` and `/stats` must be declared in `player_tournaments.py` before the existing `/{tournament_id}` catch-all, same place `/rating` used to sit.
- Reuse `formatGameError`, `EmptyState`, `ListSkeleton`, design tokens — same rules as the two prior plans on this feature.
- `npm run lint` remains broken repo-wide (pre-existing, unrelated) — verify frontend with `npm run typecheck` and `npm run build` only.
- Backend tests run via `/private/tmp/claude-501/pt-venv/bin/python -m pytest` (the venv from the earlier plans in this session); if that venv no longer exists in this environment, an implementer must recreate it the same way (see Task 1's Environment note) before running tests.
- Do not touch club code, club tables, or unrelated player-tournament files (personal squads, simulation round logic beyond the two renamed fields, bot scheduler).

## File Structure

**Create**
- `backend/alembic/versions/0120_player_tournament_stars_and_cups.py`
- `backend/app/schemas/player_tournament_ranking.py`
- `backend/app/schemas/player_tournament_stats.py`
- `backend/app/services/player_tournament_ranking_service.py`
- `backend/app/services/player_tournament_stats_service.py`
- `backend/tests/test_player_tournament_ranking_service.py`
- `backend/tests/test_player_tournament_stats_service.py`
- `frontend/src/pages/PlayerTournamentStatsPage.tsx`

**Modify**
- `backend/app/models/user.py`, `backend/app/models/game_config.py`, `backend/app/models/player_tournament.py`
- `backend/app/schemas/player_tournament.py`
- `backend/app/services/player_tournament_simulation_service.py`, `backend/app/services/player_tournament_queue_service.py`, `backend/app/services/player_tournament_query_service.py`
- `backend/app/routers/player_tournaments.py`
- `backend/tests/test_player_tournament_models.py`, `backend/tests/test_player_tournament_simulation.py`, `backend/tests/test_player_tournament_api.py`
- `frontend/src/types/index.ts`, `frontend/src/api/personalTournament.ts`
- `frontend/src/pages/PlayerTournamentPage.tsx`, `frontend/src/pages/PlayerTournamentRatingPage.tsx`, `frontend/src/pages/PlayerTournamentDetailPage.tsx`
- `frontend/src/App.tsx`

---

### Task 1: Migration, model/schema renames, simulation & queue service updates

**Files:**
- Create: `backend/alembic/versions/0120_player_tournament_stars_and_cups.py`
- Modify: `backend/app/models/user.py`, `backend/app/models/game_config.py`, `backend/app/models/player_tournament.py`, `backend/app/schemas/player_tournament.py`, `backend/app/services/player_tournament_simulation_service.py`, `backend/app/services/player_tournament_queue_service.py`
- Test: `backend/tests/test_player_tournament_models.py`, `backend/tests/test_player_tournament_simulation.py`

**Interfaces:**
- Produces: `User.tournament_stars_count: int`, `User.tournament_cups_count: int`, `GameConfig.ptour_stars_by_place: list[int]`, `PlayerTournamentResult.stars_delta: int`, `PlayerTournamentResult.cup_awarded: bool`, `PlayerTournamentCurrentOut.tournaments_played/stars_count/cups_count: int`, `PlayerTournamentStandingOut.stars_delta: int | None`, `PlayerTournamentStandingOut.cup_awarded: bool | None`. Consumed by Task 2 (ranking/stats services read `User.tournament_stars_count`/`tournament_cups_count`) and Task 3 (frontend).

- [ ] **Step 1: Update the models**

`backend/app/models/user.py`: rename the field
```python
    tournament_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```
to
```python
    tournament_stars_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tournament_cups_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```
(same location, next to `hangman_hour_started_at` — see the block this sits in today).

`backend/app/models/game_config.py`: rename
```python
    ptour_rating_by_place: Mapped[list] = mapped_column(
        JSON, default=lambda: [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5], nullable=False,
    )
```
to
```python
    ptour_stars_by_place: Mapped[list] = mapped_column(
        JSON, default=lambda: [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5], nullable=False,
    )
```
(same default values, only the name changes).

`backend/app/models/player_tournament.py`: add `Boolean` to the sqlalchemy import (`from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, UniqueConstraint`), then in `PlayerTournamentResult` rename
```python
    rating_delta: Mapped[int] = mapped_column(Integer, nullable=False)
```
to
```python
    stars_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    cup_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 2: Update the schemas**

`backend/app/schemas/player_tournament.py`:
- In `PlayerTournamentCurrentOut`, add three fields:
```python
class PlayerTournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    queue_size: int = 16
    tournament_id: Optional[int] = None
    can_apply: bool = False
    tournaments_played: int = 0
    stars_count: int = 0
    cups_count: int = 0
```
- In `PlayerTournamentStandingOut`, rename `rating_delta` and add `cup_awarded`:
```python
class PlayerTournamentStandingOut(BaseModel):
    user_id: int
    display_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    coins_awarded: Optional[int] = None
    stars_delta: Optional[int] = None
    cup_awarded: Optional[bool] = None
```
- Delete the `TournamentRatingRowOut` class entirely (Task 2 replaces it with `player_tournament_ranking.py`'s own schemas).

- [ ] **Step 3: Update `conclude_tournament`**

In `backend/app/services/player_tournament_simulation_service.py`, inside `conclude_tournament`, replace:
```python
        rating_delta = _at(config.ptour_rating_by_place, index)

        await _credit(
            db, standing.user_id, coins, TransactionType.player_tournament_place_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}", tournament.id,
        )
        user = await wallet_service.lock_user_for_update(db, standing.user_id)
        user.tournament_rating += rating_delta
        db.add(user)

        result = PlayerTournamentResult(
            tournament_id=tournament.id, user_id=standing.user_id, final_rank=rank,
            coins_awarded=coins, rating_delta=rating_delta,
        )
```
with:
```python
        stars_delta = _at(config.ptour_stars_by_place, index)
        cup_awarded = rank == 1

        await _credit(
            db, standing.user_id, coins, TransactionType.player_tournament_place_reward,
            f"Награда за {rank}-е место в турнире #{tournament.id}", tournament.id,
        )
        user = await wallet_service.lock_user_for_update(db, standing.user_id)
        user.tournament_stars_count += stars_delta
        if cup_awarded:
            user.tournament_cups_count += 1
        db.add(user)

        result = PlayerTournamentResult(
            tournament_id=tournament.id, user_id=standing.user_id, final_rank=rank,
            coins_awarded=coins, stars_delta=stars_delta, cup_awarded=cup_awarded,
        )
```
Leave everything else in that function (notify call, `tournament.status = TournamentStatus.completed`, etc.) untouched.

- [ ] **Step 4: Add the summary fields to `get_current`**

In `backend/app/services/player_tournament_queue_service.py`:
- Add `func` to the sqlalchemy import: `from sqlalchemy import func, select`.
- Add `PlayerTournamentResult` to the `app.models.player_tournament` import block.
- Rewrite `get_current` to compute the summary once and pass it into all three return branches:
```python
async def get_current(db: AsyncSession, user: User) -> PlayerTournamentCurrentOut:
    tournaments_played = (
        await db.execute(
            select(func.count(PlayerTournamentResult.id)).where(PlayerTournamentResult.user_id == user.id)
        )
    ).scalar_one()
    summary = dict(
        tournaments_played=tournaments_played, stars_count=user.tournament_stars_count,
        cups_count=user.tournament_cups_count,
    )

    active_id = await _active_tournament_id(db, user.id)
    if active_id is not None:
        return PlayerTournamentCurrentOut(status="active", tournament_id=active_id, queue_size=TOURNAMENT_SIZE, **summary)

    # Plain read (no lock): the singleton is only lazily created by apply_to_tournament.
    state = await db.get(PlayerTournamentQueueState, 1)
    position = await _queue_position(db, user.id, state.current_queue_id) if state is not None else None
    if position is not None:
        return PlayerTournamentCurrentOut(status="queued", queue_position=position, queue_size=TOURNAMENT_SIZE, **summary)

    last_completed = (
        await db.execute(
            select(PlayerTournament.id)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user.id, PlayerTournament.status == TournamentStatus.completed)
            .order_by(PlayerTournament.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    can_apply = await personal_squad_service.is_squad_complete(db, user.id)
    return PlayerTournamentCurrentOut(
        status="completed" if last_completed is not None else "not_queued",
        tournament_id=last_completed, queue_size=TOURNAMENT_SIZE, can_apply=can_apply, **summary,
    )
```

- [ ] **Step 5: Write the migration**

Create `backend/alembic/versions/0120_player_tournament_stars_and_cups.py`:
```python
"""Player tournaments: rename the single rating to stars (matching Club.stars_count),
add cups (matching Club.cups_count), and backfill both from history already on this branch.

Revision ID: 0120
Revises: 0119
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0120"
down_revision: Union[str, None] = "0119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "tournament_rating", new_column_name="tournament_stars_count")
    op.add_column("users", sa.Column("tournament_cups_count", sa.Integer(), nullable=False, server_default="0"))

    op.alter_column("game_config", "ptour_rating_by_place", new_column_name="ptour_stars_by_place")

    op.alter_column("player_tournament_results", "rating_delta", new_column_name="stars_delta")
    op.add_column("player_tournament_results", sa.Column("cup_awarded", sa.Boolean(), nullable=False, server_default="false"))

    # Backfill: any tournament concluded before this migration only set rating_delta/final_rank,
    # never cup_awarded (the column didn't exist) and never touched tournament_cups_count. Both
    # need to reflect history, not just future conclusions.
    op.execute("UPDATE player_tournament_results SET cup_awarded = true WHERE final_rank = 1")
    op.execute(
        """
        UPDATE users SET tournament_cups_count = tournament_cups_count + sub.cnt
        FROM (
            SELECT user_id, COUNT(*) AS cnt FROM player_tournament_results WHERE final_rank = 1 GROUP BY user_id
        ) AS sub
        WHERE users.id = sub.user_id
        """
    )


def downgrade() -> None:
    op.drop_column("player_tournament_results", "cup_awarded")
    op.alter_column("player_tournament_results", "stars_delta", new_column_name="rating_delta")

    op.alter_column("game_config", "ptour_stars_by_place", new_column_name="ptour_rating_by_place")

    op.drop_column("users", "tournament_cups_count")
    op.alter_column("users", "tournament_stars_count", new_column_name="tournament_rating")
```

- [ ] **Step 6: Update the existing tests that reference the renamed fields**

`backend/tests/test_player_tournament_models.py`: replace
```python
    assert config.ptour_rating_by_place == [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]
    assert sum(config.ptour_rating_by_place) == 0
```
with
```python
    assert config.ptour_stars_by_place == [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]
    assert sum(config.ptour_stars_by_place) == 0
```
and replace `assert user.tournament_rating == 0` with `assert user.tournament_stars_count == 0`.

`backend/tests/test_player_tournament_simulation.py` (`test_full_season_concludes_with_places_rewards_and_rating`): replace
```python
    for r in results:
        assert r.rating_delta == config.ptour_rating_by_place[r.final_rank - 1]
        assert r.coins_awarded == config.ptour_place_rewards[r.final_rank - 1]
        user = await db_session.get(User, r.user_id)
        await db_session.refresh(user)
        assert user.tournament_rating == r.rating_delta
    assert sum(r.rating_delta for r in results) == 0
```
with
```python
    for r in results:
        assert r.stars_delta == config.ptour_stars_by_place[r.final_rank - 1]
        assert r.coins_awarded == config.ptour_place_rewards[r.final_rank - 1]
        assert r.cup_awarded == (r.final_rank == 1)
        user = await db_session.get(User, r.user_id)
        await db_session.refresh(user)
        assert user.tournament_stars_count == r.stars_delta
        assert user.tournament_cups_count == (1 if r.final_rank == 1 else 0)
    assert sum(r.stars_delta for r in results) == 0
    assert sum(1 for r in results if r.cup_awarded) == 1
```

- [ ] **Step 7: Run tests to verify**

Run (from `backend/`, using the venv used earlier in this session; if it no longer exists, recreate it: `python3 -m venv /private/tmp/claude-501/pt-venv && /private/tmp/claude-501/pt-venv/bin/pip install -q -r <(sed 's/==/>=/' requirements.txt) greenlet`):
```
/private/tmp/claude-501/pt-venv/bin/python -m pytest tests/test_player_tournament_models.py tests/test_player_tournament_simulation.py tests/test_player_tournament_queue_service.py -q
```
Expected: all pass. `test_player_tournament_api.py` is NOT run yet — it still references the old fields/endpoint and is fixed in Task 2 (which also builds what replaces `/rating`). `python -c "from app.main import app"` must also succeed (confirms no leftover reference to `TournamentRatingRowOut`/`rating_delta`/`tournament_rating`/`ptour_rating_by_place` anywhere still imported) — grep the whole `backend/app` tree for those four names after your edits and fix any stray reference before finishing this task.

---

### Task 2: Ranking and stats services, router, and the fixed API test

**Files:**
- Create: `backend/app/schemas/player_tournament_ranking.py`, `backend/app/schemas/player_tournament_stats.py`, `backend/app/services/player_tournament_ranking_service.py`, `backend/app/services/player_tournament_stats_service.py`
- Modify: `backend/app/services/player_tournament_query_service.py`, `backend/app/routers/player_tournaments.py`, `backend/tests/test_player_tournament_api.py`
- Test: `backend/tests/test_player_tournament_ranking_service.py`, `backend/tests/test_player_tournament_stats_service.py`

**Interfaces:**
- Consumes: `User.tournament_stars_count`/`tournament_cups_count`, `PlayerTournamentParticipant`, `PlayerTournamentMatch` (all from Task 1/already-shipped models).
- Produces: `get_player_tournament_ranking(db, metric, current_user_id, limit=10) -> PlayerTournamentRankingOut`; `get_player_tournament_stats(db, user) -> PlayerTournamentStatsOut`; endpoints `GET /player-tournaments/leaderboard?metric=cups|stars` and `GET /player-tournaments/stats` — both consumed by Task 3's frontend.

- [ ] **Step 1: Write the ranking schema**

Create `backend/app/schemas/player_tournament_ranking.py` (mirrors `backend/app/schemas/club_ranking.py` exactly, minus the club-only logo fields):
```python
import enum
from typing import Optional

from pydantic import BaseModel


class PlayerTournamentRankingMetric(str, enum.Enum):
    cups = "cups"
    stars = "stars"


class PlayerTournamentRankingEntry(BaseModel):
    rank: int
    user_id: int
    display_name: str
    value: int


class PlayerTournamentRankingOut(BaseModel):
    metric: PlayerTournamentRankingMetric
    top: list[PlayerTournamentRankingEntry]
    me: Optional[PlayerTournamentRankingEntry] = None
```

- [ ] **Step 2: Write the stats schema**

Create `backend/app/schemas/player_tournament_stats.py` (mirrors `backend/app/schemas/club_stats.py` exactly):
```python
from pydantic import BaseModel


class PlayerTournamentStatsOut(BaseModel):
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    win_rate_pct: float
    draw_rate_pct: float
    loss_rate_pct: float
    goals_scored_per_match: float
    goals_conceded_per_match: float
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_player_tournament_ranking_service.py`:
```python
from app.models.user import User
from app.schemas.player_tournament_ranking import PlayerTournamentRankingMetric
from app.services.player_tournament_ranking_service import get_player_tournament_ranking
from tests.player_tournament_helpers import make_ready_user, make_user
from app.services.player_tournament_queue_service import apply_to_tournament


async def test_ranking_orders_by_metric_and_excludes_non_participants(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890001)
    b = await make_ready_user(client, db_session, bot_token, 890002)
    await make_user(client, db_session, bot_token, 890003)  # never applied — must be excluded
    await apply_to_tournament(db_session, a)
    await apply_to_tournament(db_session, b)

    a.tournament_stars_count, a.tournament_cups_count = 3, 1
    b.tournament_stars_count, b.tournament_cups_count = 8, 0
    db_session.add_all([a, b])
    await db_session.commit()

    stars = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert [e.value for e in stars.top][:2] == [8, 3]
    assert [e.user_id for e in stars.top][:2] == [b.id, a.id]
    assert len(stars.top) == 2  # the never-applied user is excluded

    cups = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.cups, current_user_id=a.id)
    assert [e.value for e in cups.top][:2] == [1, 0]
    assert [e.user_id for e in cups.top][:2] == [a.id, b.id]


async def test_ranking_me_reflects_current_users_rank(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890010)
    b = await make_ready_user(client, db_session, bot_token, 890011)
    await apply_to_tournament(db_session, a)
    await apply_to_tournament(db_session, b)
    a.tournament_stars_count, b.tournament_stars_count = 1, 5
    db_session.add_all([a, b])
    await db_session.commit()

    result = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert result.me is not None
    assert result.me.user_id == a.id
    assert result.me.rank == 2


async def test_ranking_excludes_banned_and_admin(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890020)
    await apply_to_tournament(db_session, a)
    a.tournament_stars_count = 5
    a.is_admin = True
    db_session.add(a)
    await db_session.commit()

    result = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert result.top == []
    assert result.me is None
```

Create `backend/tests/test_player_tournament_stats_service.py`:
```python
from datetime import datetime, timezone

from app.models.player_tournament import PlayerTournament, PlayerTournamentMatch
from app.services.player_tournament_stats_service import get_player_tournament_stats
from tests.player_tournament_helpers import make_ready_user


async def _add_match(db_session, tournament_id, round_number, a_id, b_id, score_a, score_b):
    from app.models.player_tournament import PlayerTournamentMatch as M
    db_session.add(M(
        tournament_id=tournament_id, round_number=round_number, user_a_id=a_id, user_b_id=b_id,
        score_a=score_a, score_b=score_b, event_log=[], simulated_at=datetime.now(timezone.utc),
    ))


async def test_stats_aggregate_across_all_tournaments(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890100)
    b = await make_ready_user(client, db_session, bot_token, 890101)
    t1 = PlayerTournament()
    t2 = PlayerTournament()
    db_session.add_all([t1, t2])
    await db_session.flush()
    await _add_match(db_session, t1.id, 1, a.id, b.id, 3, 1)  # win
    await _add_match(db_session, t1.id, 2, b.id, a.id, 2, 2)  # draw
    await _add_match(db_session, t2.id, 1, a.id, b.id, 0, 4)  # loss
    await db_session.commit()

    stats = await get_player_tournament_stats(db_session, a)
    assert stats.matches_played == 3
    assert (stats.wins, stats.draws, stats.losses) == (1, 1, 1)
    assert stats.goals_scored == 3 + 2 + 0
    assert stats.goals_conceded == 1 + 2 + 4
    assert stats.win_rate_pct == round(100 / 3, 1)


async def test_stats_zero_matches(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890110)
    stats = await get_player_tournament_stats(db_session, a)
    assert stats.matches_played == 0
    assert stats.win_rate_pct == 0.0
```

- [ ] **Step 4: Run to verify they fail**

Run: `cd backend && /private/tmp/claude-501/pt-venv/bin/python -m pytest tests/test_player_tournament_ranking_service.py tests/test_player_tournament_stats_service.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 5: Implement the ranking service**

Create `backend/app/services/player_tournament_ranking_service.py` (mirrors `backend/app/services/club_ranking_service.py`):
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player_tournament import PlayerTournamentParticipant
from app.models.user import User
from app.schemas.player_tournament_ranking import (
    PlayerTournamentRankingEntry, PlayerTournamentRankingMetric, PlayerTournamentRankingOut,
)

# Mirrors club_ranking_service._DIRECT_COLUMNS exactly, one column per metric.
_DIRECT_COLUMNS = {
    PlayerTournamentRankingMetric.cups: User.tournament_cups_count,
    PlayerTournamentRankingMetric.stars: User.tournament_stars_count,
}


async def get_player_tournament_ranking(
    db: AsyncSession, metric: PlayerTournamentRankingMetric, current_user_id: int, limit: int = 10
) -> PlayerTournamentRankingOut:
    column = _DIRECT_COLUMNS[metric]
    played_user_ids = select(PlayerTournamentParticipant.user_id).distinct().subquery()
    stmt = (
        select(User, column)
        .where(User.id.in_(select(played_user_ids.c.user_id)), User.is_banned.is_(False), User.is_admin.is_(False))
        .order_by(column.desc(), User.id)
    )
    rows = (await db.execute(stmt)).all()

    def to_entry(rank: int, user: User, value) -> PlayerTournamentRankingEntry:
        return PlayerTournamentRankingEntry(
            rank=rank, user_id=user.id, display_name=user.full_display_name(), value=int(value or 0),
        )

    top = [to_entry(i + 1, user, value) for i, (user, value) in enumerate(rows[:limit])]

    me = None
    for i, (user, value) in enumerate(rows):
        if user.id == current_user_id:
            me = to_entry(i + 1, user, value)
            break

    return PlayerTournamentRankingOut(metric=metric, top=top, me=me)
```

- [ ] **Step 6: Implement the stats service**

Create `backend/app/services/player_tournament_stats_service.py` (mirrors `backend/app/services/club_stats_service.py`):
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player_tournament import PlayerTournamentMatch
from app.models.user import User
from app.schemas.player_tournament_stats import PlayerTournamentStatsOut


async def get_player_tournament_stats(db: AsyncSession, user: User) -> PlayerTournamentStatsOut:
    """All-time record across every personal tournament the player has ever played — not
    scoped to the current tournament. Mirrors club_stats_service.get_club_stats exactly,
    swapping club_id for user_id and the club match columns for the player ones."""
    matches = (
        await db.execute(
            select(
                PlayerTournamentMatch.user_a_id, PlayerTournamentMatch.user_b_id,
                PlayerTournamentMatch.score_a, PlayerTournamentMatch.score_b,
            )
            .where((PlayerTournamentMatch.user_a_id == user.id) | (PlayerTournamentMatch.user_b_id == user.id))
        )
    ).all()

    wins = draws = losses = goals_scored = goals_conceded = 0
    for user_a_id, _user_b_id, score_a, score_b in matches:
        own_score, opp_score = (score_a, score_b) if user_a_id == user.id else (score_b, score_a)
        goals_scored += own_score
        goals_conceded += opp_score
        if own_score > opp_score:
            wins += 1
        elif own_score < opp_score:
            losses += 1
        else:
            draws += 1

    matches_played = len(matches)
    if matches_played == 0:
        return PlayerTournamentStatsOut(
            matches_played=0, wins=0, draws=0, losses=0, goals_scored=0, goals_conceded=0,
            win_rate_pct=0.0, draw_rate_pct=0.0, loss_rate_pct=0.0,
            goals_scored_per_match=0.0, goals_conceded_per_match=0.0,
        )
    return PlayerTournamentStatsOut(
        matches_played=matches_played, wins=wins, draws=draws, losses=losses,
        goals_scored=goals_scored, goals_conceded=goals_conceded,
        win_rate_pct=round(100 * wins / matches_played, 1),
        draw_rate_pct=round(100 * draws / matches_played, 1),
        loss_rate_pct=round(100 * losses / matches_played, 1),
        goals_scored_per_match=round(goals_scored / matches_played, 2),
        goals_conceded_per_match=round(goals_conceded / matches_played, 2),
    )
```

- [ ] **Step 7: Remove the old rating leaderboard from the query service**

In `backend/app/services/player_tournament_query_service.py`: delete the `get_rating_leaderboard` function entirely, and remove `TournamentRatingRowOut` from the `app.schemas.player_tournament` import line (it no longer exists after Task 1 Step 2). Leave `get_tournament_detail`, `get_match_detail`, `next_round_seconds_remaining` untouched — but check `get_tournament_detail`'s construction of `PlayerTournamentStandingOut(...)`: it currently passes `rating_delta=result.rating_delta if result else None`; update that one keyword to `stars_delta=result.stars_delta if result else None` and add `cup_awarded=result.cup_awarded if result else None` right after it.

- [ ] **Step 8: Wire the two new endpoints into the router**

In `backend/app/routers/player_tournaments.py`:
- Add imports:
```python
from app.schemas.player_tournament_ranking import PlayerTournamentRankingMetric, PlayerTournamentRankingOut
from app.schemas.player_tournament_stats import PlayerTournamentStatsOut
```
and add `player_tournament_ranking_service, player_tournament_stats_service` to the existing `from app.services import (...)` block.
- Remove the existing `/rating` endpoint (the one using `TournamentRatingRowOut`/`get_rating_leaderboard`) entirely.
- In its place (same position, still before the `/{tournament_id}` route), add:
```python
@router.get("/leaderboard", response_model=PlayerTournamentRankingOut)
async def get_player_tournament_leaderboard(
    metric: PlayerTournamentRankingMetric, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await player_tournament_ranking_service.get_player_tournament_ranking(db, metric, current_user_id=user.id)


@router.get("/stats", response_model=PlayerTournamentStatsOut)
async def get_player_tournament_stats_endpoint(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_tournament_stats_service.get_player_tournament_stats(db, user)
```
Both must appear before `@router.get("/{tournament_id}", ...)` in the file, exactly where `/rating` used to sit — otherwise `/leaderboard` and `/stats` get swallowed by the `{tournament_id}: int` path converter's 422 before ever reaching a working route (Starlette tries routes in declaration order).

- [ ] **Step 9: Fix the existing API test**

In `backend/tests/test_player_tournament_api.py`, replace `test_rating_leaderboard_sorted` with:
```python
async def test_leaderboard_sorted_by_metric(client, db_session, bot_token):
    from app.services.player_tournament_queue_service import apply_to_tournament

    a = await make_ready_user(client, db_session, bot_token, 880400)
    b = await make_ready_user(client, db_session, bot_token, 880401)
    await apply_to_tournament(db_session, a)
    await apply_to_tournament(db_session, b)
    a.tournament_stars_count, b.tournament_stars_count = 3, 8
    db_session.add_all([a, b])
    await db_session.commit()
    resp = await client.get(f"{BASE}/leaderboard", params={"metric": "stars"}, headers=telegram_headers(880400, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert [e["value"] for e in body["top"]][:2] == [8, 3]
    assert body["me"]["user_id"] == a.id
```
Check the top of the file for how `apply_to_tournament` and `make_ready_user` are already imported elsewhere in this file (there is likely a module-level import already covering `make_ready_user`; only add the `apply_to_tournament` import if it is not already present at module scope) and adjust the import placement accordingly rather than duplicating an existing import.

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd backend && /private/tmp/claude-501/pt-venv/bin/python -m pytest tests/test_player_tournament_ranking_service.py tests/test_player_tournament_stats_service.py tests/test_player_tournament_api.py -q`
Expected: all pass. Then run the full player-tournament test surface plus an import check:
```
/private/tmp/claude-501/pt-venv/bin/python -m pytest tests/ -k player_tournament -q
/private/tmp/claude-501/pt-venv/bin/python -c "from app.main import app"
```
Both must be clean, and a final `grep -rn "rating_delta\|tournament_rating\b\|ptour_rating_by_place\|TournamentRatingRowOut\|get_rating_leaderboard" backend/app backend/tests` must return nothing.

---

### Task 3: Frontend — hub summary bar, cups/stars leaderboard, stats page

**Files:**
- Create: `frontend/src/pages/PlayerTournamentStatsPage.tsx`
- Modify: `frontend/src/types/index.ts`, `frontend/src/api/personalTournament.ts`, `frontend/src/pages/PlayerTournamentPage.tsx`, `frontend/src/pages/PlayerTournamentRatingPage.tsx`, `frontend/src/pages/PlayerTournamentDetailPage.tsx`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET /player-tournaments/leaderboard?metric=`, `GET /player-tournaments/stats`, and the 3 new fields on `GET /player-tournaments/current` and `stars_delta`/`cup_awarded` on tournament-detail standings (all from Task 1/2).

- [ ] **Step 1: Update types**

In `frontend/src/types/index.ts`:
- In `PlayerTournamentStanding`, rename `rating_delta` and add `cup_awarded`:
```typescript
export interface PlayerTournamentStanding {
  user_id: number;
  display_name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  coins_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}
```
- In `PlayerTournamentCurrent`, add the 3 summary fields:
```typescript
export interface PlayerTournamentCurrent {
  status: PlayerTournamentStatus;
  queue_position: number | null;
  queue_size: number;
  tournament_id: number | null;
  can_apply: boolean;
  tournaments_played: number;
  stars_count: number;
  cups_count: number;
}
```
- Replace the `TournamentRatingRow` interface with (same location):
```typescript
export type PlayerTournamentRankingMetric = "cups" | "stars";

export interface PlayerTournamentRankingEntry {
  rank: number;
  user_id: number;
  display_name: string;
  value: number;
}

export interface PlayerTournamentRankingResult {
  metric: PlayerTournamentRankingMetric;
  top: PlayerTournamentRankingEntry[];
  me: PlayerTournamentRankingEntry | null;
}

export interface PlayerTournamentStats {
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_scored: number;
  goals_conceded: number;
  win_rate_pct: number;
  draw_rate_pct: number;
  loss_rate_pct: number;
  goals_scored_per_match: number;
  goals_conceded_per_match: number;
}
```

- [ ] **Step 2: Update the API client**

In `frontend/src/api/personalTournament.ts`:
- Update the `import type { ... } from "@/types"` block: remove `TournamentRatingRow`, add `PlayerTournamentRankingMetric`, `PlayerTournamentRankingResult`, `PlayerTournamentStats`.
- Replace `fetchPlayerTournamentRating` with:
```typescript
export async function fetchPlayerTournamentLeaderboard(metric: PlayerTournamentRankingMetric): Promise<PlayerTournamentRankingResult> {
  const { data } = await api.get<PlayerTournamentRankingResult>("/player-tournaments/leaderboard", { params: { metric } });
  return data;
}

export async function fetchPlayerTournamentStats(): Promise<PlayerTournamentStats> {
  const { data } = await api.get<PlayerTournamentStats>("/player-tournaments/stats");
  return data;
}
```

- [ ] **Step 3: Add the summary bar to the hub page**

In `frontend/src/pages/PlayerTournamentPage.tsx`: add `IconStar` to the existing icon import (`import { IconChevronRight, IconClock, IconFlagCheckered, IconStar, IconTrophy, IconUsers } from "@/components/icons";`). Insert this block right after the `<h1>...</h1>` and its following `<p>` (the two elements already there), before the "Состав для турнира" button:
```tsx
      {current && (
        <div className="flex items-center gap-4 rounded-2xl bg-bg-surface px-4 py-3 text-xs text-ink-mist">
          <span className="flex items-center gap-1.5">
            <IconFlagCheckered size={13} />
            {current.tournaments_played} турниров
          </span>
          <span className="flex items-center gap-1.5 font-mono font-bold text-accent-lime">
            <IconTrophy size={13} />
            {current.cups_count}
          </span>
          <span className="flex items-center gap-1.5 font-mono font-bold text-accent-cyan">
            <IconStar size={13} />
            {current.stars_count}
          </span>
        </div>
      )}
```
Then add a third nav button (after "Рейтинг турнира", before the "Мой турнир" conditional block):
```tsx
      <button
        onClick={() => navigate("/player-tournament/stats")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconFlagCheckered size={16} className="text-accent-lime" />
        Статистика за всё время
        <IconChevronRight size={16} className="ml-auto text-ink-mist-dim" />
      </button>
```

- [ ] **Step 4: Rewrite the rating page as a cups/stars leaderboard**

Replace `frontend/src/pages/PlayerTournamentRatingPage.tsx` entirely (mirrors `frontend/src/pages/ClubLeaderboardPage.tsx`'s structure):
```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchPlayerTournamentLeaderboard } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { IconChevronLeft, IconStar, IconTrophy, type IconProps } from "@/components/icons";
import type { PlayerTournamentRankingEntry, PlayerTournamentRankingMetric } from "@/types";

const METRICS: { value: PlayerTournamentRankingMetric; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "cups", label: "Кубки", Icon: IconTrophy },
  { value: "stars", label: "Звёзды", Icon: IconStar },
];

export default function PlayerTournamentRatingPage() {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<PlayerTournamentRankingMetric>("cups");
  const { data, isLoading } = useQuery({
    queryKey: ["player-tournament", "leaderboard", metric],
    queryFn: () => fetchPlayerTournamentLeaderboard(metric),
  });

  const meInTop = !!data?.me && data.top.some((e) => e.user_id === data.me!.user_id);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-accent-lime" />
          Рейтинг турнира
        </h1>
      </div>

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
        <EmptyState icon={IconTrophy} title="Пока никто не набрал очков" description="Сыграй турнир, чтобы попасть в рейтинг" />
      ) : (
        <div className="flex flex-col gap-2">
          {data?.top.map((entry) => (
            <RankingRow key={entry.user_id} entry={entry} highlight={entry.user_id === data?.me?.user_id} />
          ))}
        </div>
      )}

      {data?.me && !meInTop && (
        <>
          <p className="mt-1 text-center text-xs text-ink-mist-dim">⋯</p>
          <RankingRow entry={data.me} highlight />
        </>
      )}
    </div>
  );
}

function RankingRow({ entry, highlight = false }: { entry: PlayerTournamentRankingEntry; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${highlight ? "bg-accent-lime/10" : "bg-bg-surface"}`}>
      <div className="flex items-center gap-2">
        <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{entry.rank}</span>
        <span className={highlight ? "font-semibold text-accent-lime" : "text-ink-chalk"}>{entry.display_name}</span>
      </div>
      <span className="font-mono font-bold text-accent-cyan">{entry.value}</span>
    </div>
  );
}
```

- [ ] **Step 5: Write the stats page**

Create `frontend/src/pages/PlayerTournamentStatsPage.tsx` (mirrors `frontend/src/pages/ClubStatsPage.tsx` exactly, swapping the data source):
```tsx
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchPlayerTournamentStats } from "@/api/personalTournament";
import { IconChevronLeft, IconTarget } from "@/components/icons";

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <p className="text-[11px] text-ink-mist-dim">{label}</p>
      <p className="font-mono text-lg font-bold text-ink-chalk">{value}</p>
    </div>
  );
}

export default function PlayerTournamentStatsPage() {
  const navigate = useNavigate();
  const { data: stats, isLoading } = useQuery({ queryKey: ["player-tournament", "stats"], queryFn: fetchPlayerTournamentStats });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTarget size={20} className="text-accent-lime" />
          Статистика личных турниров
        </h1>
      </div>

      {isLoading && <p className="text-sm text-ink-mist-dim">Загрузка...</p>}

      {stats && (
        <>
          <p className="text-xs text-ink-mist">Статистика за всё время выступлений в личных турнирах.</p>
          <div className="grid grid-cols-2 gap-3">
            <StatTile label="Матчей сыграно" value={stats.matches_played} />
            <StatTile label="Побед" value={stats.wins} />
            <StatTile label="Ничьих" value={stats.draws} />
            <StatTile label="Поражений" value={stats.losses} />
            <StatTile label="Голов забито" value={stats.goals_scored} />
            <StatTile label="Голов пропущено" value={stats.goals_conceded} />
            <StatTile label="% побед" value={`${stats.win_rate_pct}%`} />
            <StatTile label="% ничьих" value={`${stats.draw_rate_pct}%`} />
            <StatTile label="% поражений" value={`${stats.loss_rate_pct}%`} />
            <StatTile label="Голов за матч" value={stats.goals_scored_per_match} />
            <StatTile label="Пропущено за матч" value={stats.goals_conceded_per_match} />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Update the tournament detail page's results section**

In `frontend/src/pages/PlayerTournamentDetailPage.tsx`:
- Add `IconStar` to the existing icon import (`import { IconChevronLeft, IconCoin, IconStar, IconTrophy } from "@/components/icons";`).
- In the "Итоги турнира" block, replace:
```tsx
              <div className="flex items-center gap-3 font-mono text-xs">
                {s.rating_delta !== null && (
                  <span className={`flex items-center gap-1 ${
                    s.rating_delta > 0 ? "text-accent-lime" : s.rating_delta < 0 ? "text-red-400" : "text-ink-mist"
                  }`}>
                    <IconTrophy size={12} />
                    {s.rating_delta > 0 ? `+${s.rating_delta}` : s.rating_delta}
                  </span>
                )}
                {s.coins_awarded !== null && s.coins_awarded > 0 && (
                  <span className="flex items-center gap-1 text-accent-cyan">
                    <IconCoin size={12} />
                    +{s.coins_awarded}
                  </span>
                )}
              </div>
```
with:
```tsx
              <div className="flex items-center gap-3 font-mono text-xs">
                {s.cup_awarded && <IconTrophy size={14} className="text-accent-lime" />}
                {s.stars_delta !== null && (
                  <span className={`flex items-center gap-1 ${
                    s.stars_delta > 0 ? "text-accent-lime" : s.stars_delta < 0 ? "text-red-400" : "text-ink-mist"
                  }`}>
                    <IconStar size={12} />
                    {s.stars_delta > 0 ? `+${s.stars_delta}` : s.stars_delta}
                  </span>
                )}
                {s.coins_awarded !== null && s.coins_awarded > 0 && (
                  <span className="flex items-center gap-1 text-accent-cyan">
                    <IconCoin size={12} />
                    +{s.coins_awarded}
                  </span>
                )}
              </div>
```

- [ ] **Step 7: Register the new route**

In `frontend/src/App.tsx`:
1. Add `import PlayerTournamentStatsPage from "@/pages/PlayerTournamentStatsPage";` next to the other `PlayerTournament*` page imports.
2. Add `<Route path="/player-tournament/stats" element={<PlayerTournamentStatsPage />} />` next to the other `/player-tournament/...` routes, before `/player-tournament/:id` (same reasoning as the existing `/squad` and `/rating` routes — keep fixed-segment routes grouped ahead of the dynamic one for readability; ordering doesn't affect React Router v6 matching).

- [ ] **Step 8: Verify**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: no errors, build succeeds. `npm run lint` remains skipped (confirmed broken repo-wide, pre-existing).

---

## Self-review

**Spec coverage:** cups AND stars ranking — Task 2 (service) + Task 3 Step 4 (page). Hub summary (tournaments played / stars / cups) — Task 1 Step 4 (backend) + Task 3 Step 3 (frontend). All-time stats page "по аналогии с клубами" — Task 2 (service) + Task 3 Step 5 (page, byte-for-byte structural mirror of `ClubStatsPage.tsx`).

**Placeholder scan:** none — every step has complete code, including the full migration with backfill SQL and every modified function shown in its final form.

**Type consistency:** `stars_delta`/`cup_awarded` used identically across the model (Task 1), schema (Task 1 & 2), and frontend type + both consuming pages (Task 3). `PlayerTournamentRankingMetric`/`Entry`/`Result` names match between backend schema (Task 2) and frontend type (Task 3). `tournaments_played`/`stars_count`/`cups_count` match between `PlayerTournamentCurrentOut` (Task 1) and `PlayerTournamentCurrent` (Task 3) and their single consumer, the hub page.
