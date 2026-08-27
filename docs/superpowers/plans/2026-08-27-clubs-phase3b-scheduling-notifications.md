# Clubs Phase 3b: Scheduling & Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the already-shipped Phase 3a tournament pipeline a real clock — two bot-side daily loops that fire round simulation and lineup reminders — plus notification wiring so players hear about match results and tournament conclusions.

**Architecture:** Two new bot-side `while True: sleep()` loops (`bot/services/tournament_scheduler.py`) call two backend internal endpoints over HTTP (the existing `simulate-round`, plus a new `lineup-reminders`). All notification content decisions stay backend-side: a new `tournament_notification_service.py` module provides one shared `notify_club_members` helper, reused by the new lineup-reminder endpoint and by two small hooks added to Phase 3a's already-shipped `simulate_next_round`/`conclude_tournament`. The bot's only job, as with every other feature in this codebase, is deliver-and-mark-sent via the existing dispatcher — never compute-what-to-say.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, PostgreSQL, aiogram 3, aiohttp, pytest.

**Spec:** [docs/superpowers/specs/2026-08-27-clubs-phase3b-scheduling-notifications-design.md](../specs/2026-08-27-clubs-phase3b-scheduling-notifications-design.md)

## Global Constraints

- All notification *content* decisions live in the backend; the bot only delivers (existing `run_notification_dispatcher`) — never add message-composition logic to the bot process.
- The two bot loops must have catch-up behavior: a slot whose fire-time has passed today and hasn't fired today yet fires on the next 15-minute check, not just at the exact minute — because `simulate_next_round`'s "no round ever skipped" guarantee depends on every slot actually firing.
- `SIMULATION_SLOTS = [(12, 0), (20, 0)]` (hour, minute, server-local via `ZoneInfo(settings.timezone)`) is a plain module constant, not `GameConfig` — this is ops/scheduling cadence, not a game-economy number.
- `club_match` notifications carry `related_object_id=tournament.id` (not a specific match id) and deep-link to `/clubs/tournament/{tournament_id}` — the existing `related_object_id` column is a single nullable int with no room for a composite (tournament, match) id, and extending the shared `_MATCH_PATH_PREFIXES` mechanism for one case isn't worth it.
- A fixture where either club is `is_withdrawn` produces no `club_match` notification and is skipped by the lineup-reminder check for both sides — no real match is simulated for either club that round.
- Alembic revisions continue sequentially from the current head `0070` — this plan uses `0071`.
- Player-facing error/notification text in Russian, matching every prior Clubs task's convention.
- `git add` discipline: this working tree may carry files from other, unrelated in-progress sessions of work — every task below names its exact file list; stage only those files, never `-A`/`.`.

---

### Task 1: `NotificationType` enum members

**Files:**
- Modify: `backend/app/models/enums.py`
- Create: `backend/alembic/versions/0071_club_tournament_notification_types.py`

**Interfaces:**
- Produces: `NotificationType.club_match`, `.club_lineup_reminder`, `.club_tournament_results_ready` — consumed by Tasks 2, 3, 4.

- [ ] **Step 1: Add the enum members**

In `backend/app/models/enums.py`, inside `class NotificationType(str, enum.Enum)`, after the existing `club_captain_transferred` line:

```python
    club_match = "club_match"
    club_lineup_reminder = "club_lineup_reminder"
    club_tournament_results_ready = "club_tournament_results_ready"
```

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/0071_club_tournament_notification_types.py`:

```python
"""Add club_match, club_lineup_reminder, club_tournament_results_ready to notification_type_enum

Revision ID: 0071
Revises: 0070
Create Date: 2026-08-27
"""
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_match'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_lineup_reminder'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_tournament_results_ready'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
    pass
```

- [ ] **Step 3: Apply and verify against real Postgres**

```bash
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres psql -U postgres -d footycards -c "SELECT unnest(enum_range(NULL::notification_type_enum))" | grep club_
```

Confirm all three new values appear alongside the existing `club_*` values.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/enums.py backend/alembic/versions/0071_club_tournament_notification_types.py
git commit -m "Add club_match/club_lineup_reminder/club_tournament_results_ready notification types"
```

---

### Task 2: Lineup-reminder service + internal endpoint

**Files:**
- Create: `backend/app/services/tournament_notification_service.py`
- Modify: `backend/app/schemas/tournament.py`
- Modify: `backend/app/routers/internal.py`
- Test: `backend/tests/test_tournament_notification_service.py`

**Interfaces:**
- Consumes: `NotificationType` (Task 1), `notify` (existing, `notification_service.py`), `generate_fixtures` (Phase 3a), `Tournament`/`TournamentClub` (Phase 3a), `ClubCardAvailability` (Phase 3a), `ClubMember` (Phase 1, `club.py`), `_get_or_none_lineup` (Phase 2, `club_squad_service.py`, function-local import per this codebase's established circular-import-avoidance convention).
- Produces: `notify_club_members(db, club_id, type_, title, body, related_object_type=None, related_object_id=None) -> None` and `send_lineup_reminders(db) -> int` in `tournament_notification_service.py` — `notify_club_members` consumed by Tasks 3 and 4; route `POST /internal/clubs/lineup-reminders` consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tournament_notification_service.py`:

```python
from sqlalchemy import select

from app.models.club import ClubMember
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import Position
from app.models.notification import Notification
from app.services.tournament_notification_service import notify_club_members, send_lineup_reminders
from app.services.tournament_queue_service import apply_to_tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _seed_position_pool(db_session):
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200

    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id + 500000, bot_token))
    assert resp2.status_code == 200
    join_resp = await client.post(
        f"/api/v1/clubs/{create_resp.json()['id']}/join", headers=telegram_headers(telegram_id + 500000, bot_token)
    )
    assert join_resp.status_code == 200

    return create_resp.json()["id"], captain


async def test_notify_club_members_notifies_every_member(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club_id, captain = await _create_club_with_full_squad(client, db_session, bot_token, 850001, "Клуб уведомлений")

    from app.models.enums import NotificationType

    await notify_club_members(db_session, club_id, NotificationType.club_match, "Заголовок", "Текст")
    await db_session.commit()

    member_count = (
        await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))
    ).scalars().all()
    notifications = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_match))).scalars().all()
    assert len(notifications) == len(member_count) == 2


async def test_send_lineup_reminders_notifies_club_with_suspended_starter(client, db_session, bot_token):
    from app.models.club import Club

    await _seed_position_pool(db_session)
    club_ids_and_captains = []
    for i in range(8):
        await _create_club_with_full_squad(client, db_session, bot_token, 850100 + i * 2, f"Резерв {i}")
        club = (await db_session.execute(select(Club).where(Club.name == f"Резерв {i}"))).scalar_one()
        captain = await get_user_by_telegram_id(db_session, 850100 + i * 2)
        club_ids_and_captains.append((club, captain))

    tournament_id = None
    for club, captain in club_ids_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    from app.models.club_lineup import ClubLineup, ClubLineupCard

    first_club = club_ids_and_captains[0][0]
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == first_club.id))).scalar_one()
    lineup_card = (await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().first()
    db_session.add(ClubCardAvailability(club_card_id=lineup_card.club_card_id, rounds_remaining=1))
    await db_session.commit()

    notified = await send_lineup_reminders(db_session)
    assert notified == 1

    from app.models.enums import NotificationType

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_lineup_reminder))
    ).scalars().all()
    assert len(notifications) == 2  # 2 members of the affected club


async def test_send_lineup_reminders_skips_clubs_with_no_suspension(client, db_session, bot_token):
    from app.models.club import Club

    await _seed_position_pool(db_session)
    tournament_id = None
    for i in range(8):
        await _create_club_with_full_squad(client, db_session, bot_token, 850200 + i * 2, f"Чистые {i}")
        captain = await get_user_by_telegram_id(db_session, 850200 + i * 2)
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    notified = await send_lineup_reminders(db_session)
    assert notified == 0
```

(Reuses the exact `_create_club_with_full_squad`/per-file-local-fixture convention Phase 3a's own test files established — every fresh club auto-seeds a full 11/11 lineup via `seed_starting_squad`, so no manual lineup-filling step is needed.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec -T backend pytest tests/test_tournament_notification_service.py -v
```

Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Create `backend/app/services/tournament_notification_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import ClubMember
from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import NotificationType, TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.services.notification_service import notify
from app.services.tournament_fixture_service import generate_fixtures


async def notify_club_members(
    db: AsyncSession, club_id: int, type_: NotificationType, title: str, body: str,
    related_object_type: str | None = None, related_object_id: int | None = None,
) -> None:
    """Notifies every member of a club — used for events that affect the
    whole club (a match played, a tournament concluded, a lineup gap),
    unlike Clubs' other notify() call sites which target one specific
    user (a role change, a kick)."""
    member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club_id))).scalars().all()
    for user_id in member_ids:
        await notify(db, user_id, type_, title, body, related_object_type, related_object_id)


async def _club_has_suspended_starter(db: AsyncSession, club_id: int) -> bool:
    """Read-only check — does NOT call resolve_match_lineup (Task 12),
    which also performs substitution and returns engine-shaped actor
    dicts neither needed nor wanted for a preview check."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return False
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}
    if not lineup_card_ids:
        return False
    result = await db.execute(
        select(ClubCardAvailability.id)
        .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def send_lineup_reminders(db: AsyncSession) -> int:
    """For every active tournament's upcoming round, notifies every member
    of any club (on either side of a real, non-withdrawn fixture) whose
    active lineup has a still-suspended starter. Read-only — mutates
    nothing but the Notification rows it inserts. Returns the number of
    (club, notified) events, for the internal endpoint's response."""
    tournaments = (
        await db.execute(
            select(Tournament).where(Tournament.status == TournamentStatus.active, Tournament.rounds_simulated < 14)
        )
    ).scalars().all()

    notified_count = 0
    for tournament in tournaments:
        round_number = tournament.rounds_simulated + 1
        participants = (
            await db.execute(
                select(TournamentClub).where(TournamentClub.tournament_id == tournament.id).order_by(TournamentClub.id)
            )
        ).scalars().all()
        club_ids = [p.club_id for p in participants]
        withdrawn_ids = {p.club_id for p in participants if p.is_withdrawn}

        fixtures = [f for f in generate_fixtures(club_ids) if f[0] == round_number]
        for _, club_a_id, club_b_id in fixtures:
            if club_a_id in withdrawn_ids or club_b_id in withdrawn_ids:
                continue
            for club_id in (club_a_id, club_b_id):
                if await _club_has_suspended_starter(db, club_id):
                    await notify_club_members(
                        db, club_id, NotificationType.club_lineup_reminder,
                        "Кто-то из состава не сыграет",
                        "В стартовом составе клуба есть игрок под дисквалификацией — проверь состав перед следующим туром турнира.",
                    )
                    notified_count += 1

    await db.commit()
    return notified_count
```

- [ ] **Step 4: Add the schema and internal endpoint**

Append to `backend/app/schemas/tournament.py`:

```python
class LineupReminderResult(BaseModel):
    clubs_notified: int
```

In `backend/app/routers/internal.py`, add to the existing `from app.services import ...` import line: `tournament_notification_service`. Add to the existing `from app.schemas.tournament import SimulateRoundResult` line: `, LineupReminderResult`. Then append:

```python
@router.post("/clubs/lineup-reminders", response_model=LineupReminderResult)
async def lineup_reminders(db: AsyncSession = Depends(get_db)):
    """Called by the bot's lineup-reminder loop, ~1h before each daily
    simulation slot. See tournament_notification_service.send_lineup_reminders."""
    count = await tournament_notification_service.send_lineup_reminders(db)
    return LineupReminderResult(clubs_notified=count)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec -T backend pytest tests/test_tournament_notification_service.py -v
```

Expected: PASS, all 3 tests.

- [ ] **Step 6: Verify the internal endpoint against real Postgres**

```bash
curl -s -X POST http://localhost:8000/api/v1/internal/clubs/lineup-reminders -H "X-Internal-Secret: dev_only_internal_secret"
```

(Use the real value of `INTERNAL_API_SECRET` from your `.env` if it differs from the default — never print or read the actual `.env` file per this codebase's rules; just confirm you get a `200 {"clubs_notified": N}` response, not a 401.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tournament_notification_service.py backend/app/schemas/tournament.py backend/app/routers/internal.py backend/tests/test_tournament_notification_service.py
git commit -m "Add lineup-reminder service and internal endpoint"
```

---

### Task 3: `club_match` notifications in `simulate_next_round`

**Files:**
- Modify: `backend/app/services/tournament_simulation_service.py`
- Test: `backend/tests/test_tournament_simulation_service.py`

**Interfaces:**
- Consumes: `notify_club_members` (Task 2), `NotificationType.club_match` (Task 1).
- Produces: no new interface — this is a behavioral addition to an existing function.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tournament_simulation_service.py` (this file already has an `eight_club_tournament` local fixture per Phase 3a's plan — reuse it):

```python
async def test_simulate_next_round_notifies_both_clubs_on_a_real_match(db_session, eight_club_tournament):
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    matches = await simulate_next_round(db_session)
    await db_session.commit()

    real_matches = [m for m in matches if m.tournament_id == tournament.id and m.event_log]
    assert real_matches  # at least one real (non-withdrawn) match this round

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_match))
    ).scalars().all()
    # 2 members per club (per Task 2's fixture convention) * 2 clubs per real match
    assert len(notifications) == len(real_matches) * 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_service.py -k notifies_both_clubs -v
```

Expected: FAIL (0 notifications, not `len(real_matches) * 4`).

- [ ] **Step 3: Implement**

In `backend/app/services/tournament_simulation_service.py`, add to the imports:

```python
from app.models.enums import NotificationType, TournamentStatus
from app.services import tournament_notification_service
```

(Note `NotificationType` — check the existing `from app.models.enums import TournamentStatus` line and extend it to `from app.models.enums import NotificationType, TournamentStatus` rather than adding a second import line for the same module.)

Inside `simulate_next_round`'s real-match branch, right after `round_matches.append(match)` (the line immediately following `await _apply_engine_result(db, engine_result)`):

```python
            round_matches.append(match)

            await tournament_notification_service.notify_club_members(
                db, club_a_id, NotificationType.club_match, "Матч сыгран",
                f"Твой клуб сыграл матч {round_number}-го тура турнира — счёт {engine_result.score_a}:{engine_result.score_b}",
                related_object_type="club_match", related_object_id=tournament.id,
            )
            await tournament_notification_service.notify_club_members(
                db, club_b_id, NotificationType.club_match, "Матч сыгран",
                f"Твой клуб сыграл матч {round_number}-го тура турнира — счёт {engine_result.score_b}:{engine_result.score_a}",
                related_object_type="club_match", related_object_id=tournament.id,
            )
```

Do **not** add this to the withdrawn-club auto-loss branch — per the Global Constraints, no `club_match` notification fires for either side of a withdrawn fixture.

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose exec -T backend pytest tests/test_tournament_simulation_service.py -v
```

Expected: PASS, including the new test and every pre-existing test in this file (no regression to round-1/round-14 idempotency, standings, or withdrawal behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_simulation_service.py backend/tests/test_tournament_simulation_service.py
git commit -m "Notify both clubs' members when simulate_next_round persists a real match"
```

---

### Task 4: `club_tournament_results_ready` notifications in `conclude_tournament`

**Files:**
- Modify: `backend/app/services/tournament_reward_service.py`
- Test: `backend/tests/test_tournament_reward_service.py`

**Interfaces:**
- Consumes: `notify_club_members` (Task 2), `NotificationType.club_tournament_results_ready` (Task 1).
- Produces: no new interface — behavioral addition to an existing function.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tournament_reward_service.py` (reuse the file's existing `_make_club` helper and 8-club standings setup from `test_conclude_awards_cups_stars_budget_by_rank`):

```python
async def test_conclude_tournament_notifies_every_club(db_session):
    from sqlalchemy import select

    from app.models.club import ClubMember
    from app.models.enums import NotificationType
    from app.models.notification import Notification
    from app.models.tournament import Tournament
    from app.models.tournament_standing import TournamentClubStanding
    from app.models.user import User
    from app.services.tournament_reward_service import conclude_tournament

    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()

    clubs = [await _make_club(db_session, f"ClubNotif{i}") for i in range(8)]
    standings = []
    for i, club in enumerate(clubs):
        user = User(telegram_id=900000 + i, first_name="T")
        db_session.add(user)
        await db_session.flush()
        db_session.add(ClubMember(club_id=club.id, user_id=user.id, role="captain"))
        s = TournamentClubStanding(tournament_id=tournament.id, club_id=club.id, points=(8 - i) * 3)
        db_session.add(s)
        standings.append(s)
    await db_session.flush()

    await conclude_tournament(db_session, tournament, standings, matches=[])
    await db_session.commit()

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_tournament_results_ready))
    ).scalars().all()
    assert len(notifications) == 8  # one captain per club, per this test's minimal setup
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec -T backend pytest tests/test_tournament_reward_service.py -k notifies_every_club -v
```

Expected: FAIL.

- [ ] **Step 3: Implement**

In `backend/app/services/tournament_reward_service.py`, add to the imports:

```python
from app.models.enums import ClubBudgetTransactionType, NotificationType, TournamentStatus
from app.services import tournament_notification_service
```

(Extend the existing `from app.models.enums import ClubBudgetTransactionType, TournamentStatus` line to also import `NotificationType`, rather than a second import line.)

Inside `conclude_tournament`'s per-club loop, right after `results.append(result)`:

```python
        results.append(result)

        await tournament_notification_service.notify_club_members(
            db, club.id, NotificationType.club_tournament_results_ready,
            "Турнир завершён", f"Твой клуб занял {rank}-е место в турнире — загляни за результатами!",
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker compose exec -T backend pytest tests/test_tournament_reward_service.py -v
```

Expected: PASS, including the new test and every pre-existing test in this file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tournament_reward_service.py backend/tests/test_tournament_reward_service.py
git commit -m "Notify every club's members when conclude_tournament writes their result"
```

---

### Task 5: Bot-side scheduler loops + registration + deep-link

**Files:**
- Create: `bot/services/tournament_scheduler.py`
- Modify: `bot/bot.py`
- Modify: `bot/services/notifier.py`
- Test: `bot/tests/test_tournament_scheduler.py` (check whether a `bot/tests/` directory with a working pytest setup already exists — see Step 1 below; if this codebase has no bot-side test suite at all, this task's test step becomes a standalone script run once to confirm behavior, documented in the commit message, since inventing a whole new bot-side test harness is out of scope for this plan)

**Interfaces:**
- Consumes: `POST /internal/clubs/simulate-round` (Phase 3a, unchanged), `POST /internal/clubs/lineup-reminders` (Task 2).
- Produces: `run_simulation_loop()`, `run_lineup_reminder_loop()` in `tournament_scheduler.py`, registered in `bot.py`.

- [ ] **Step 1: Check for an existing bot-side test setup**

```bash
ls bot/tests/ 2>/dev/null || echo "no bot/tests directory"
cat bot/pytest.ini bot/pyproject.toml bot/setup.cfg 2>/dev/null | grep -i pytest
```

If a working bot-side pytest configuration exists, write the test in Step 2 as a real pytest file. If not, write the same test logic as a standalone script (`bot/scripts/test_due_slots_manually.py` or run it inline via `docker compose exec -T bot python -c "..."`) and note in your report that this plan doesn't introduce new bot-side test infrastructure — only exercises the pure function directly.

- [ ] **Step 2: Write the failing test for the pure decision function**

The core logic worth testing in isolation is `_due_slots` — a pure function taking "now" and "last fired per slot" and returning which slots are due, deliberately NOT wrapped in `asyncio.sleep`-driven timing so it's fast and deterministic to test:

```python
from datetime import date, datetime

from services.tournament_scheduler import SIMULATION_SLOTS, _due_slots


def test_due_slots_fires_when_past_fire_time_and_not_yet_fired_today():
    now = datetime(2026, 8, 27, 12, 5)  # 5 min after the 12:00 slot
    due = _due_slots(now, last_fired={})
    assert (12, 0) in due
    assert (20, 0) not in due  # not due yet today


def test_due_slots_does_not_refire_the_same_slot_twice_in_one_day():
    now = datetime(2026, 8, 27, 12, 5)
    due = _due_slots(now, last_fired={(12, 0): date(2026, 8, 27)})
    assert (12, 0) not in due


def test_due_slots_refires_a_slot_on_a_new_day():
    now = datetime(2026, 8, 28, 12, 5)
    due = _due_slots(now, last_fired={(12, 0): date(2026, 8, 27)})
    assert (12, 0) in due


def test_due_slots_applies_lead_minutes_for_the_reminder_loop():
    now = datetime(2026, 8, 27, 11, 5)  # 5 min after 11:00 (60 min before the 12:00 slot)
    due = _due_slots(now, last_fired={}, lead_minutes=60)
    assert (12, 0) in due
    now_too_early = datetime(2026, 8, 27, 10, 55)
    assert _due_slots(now_too_early, last_fired={}, lead_minutes=60) == []


def test_due_slots_catches_up_after_a_missed_check():
    # Bot was down from before 12:00 until 14:00 — the 12:00 slot is still
    # due, since it hasn't fired today, even though we're 2h past it.
    now = datetime(2026, 8, 27, 14, 0)
    due = _due_slots(now, last_fired={})
    assert (12, 0) in due
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker compose exec -T bot python -m pytest tests/test_tournament_scheduler.py -v
# or, if no bot-side pytest setup exists per Step 1:
docker compose exec -T bot python -c "from services.tournament_scheduler import _due_slots"
```

Expected: FAIL, module not found.

- [ ] **Step 4: Implement**

Create `bot/services/tournament_scheduler.py`:

```python
import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from config import get_bot_settings

logger = logging.getLogger(__name__)
settings = get_bot_settings()

SIMULATION_SLOTS: list[tuple[int, int]] = [(12, 0), (20, 0)]
REMINDER_LEAD_MINUTES = 60
LOOP_CHECK_INTERVAL_SECONDS = 900  # 15 min — frequent enough to catch a slot within a reasonable window, cheap enough to run forever

_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _due_slots(
    now: datetime, last_fired: dict[tuple[int, int], date], lead_minutes: int = 0
) -> list[tuple[int, int]]:
    """Pure decision function — deliberately has no I/O so it's fast and
    deterministic to test in isolation. A slot is due once `now` has passed
    its fire time (the slot itself, or `lead_minutes` earlier for the
    reminder loop) and it hasn't already fired today. Catch-up is implicit:
    a slot whose fire time passed hours ago and never fired today is still
    "due" — this is what keeps a bot restart or transient outage from
    silently skipping a whole day's slot."""
    due = []
    for slot in SIMULATION_SLOTS:
        fire_at = now.replace(hour=slot[0], minute=slot[1], second=0, microsecond=0)
        if lead_minutes:
            fire_at -= timedelta(minutes=lead_minutes)
        if now >= fire_at and last_fired.get(slot) != now.date():
            due.append(slot)
    return due


async def _post_internal(path: str) -> dict:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(f"{settings.internal_backend_url}/internal{path}", headers=_HEADERS) as resp:
            resp.raise_for_status()
            return await resp.json()


async def run_simulation_loop() -> None:
    """Fires POST /internal/clubs/simulate-round at each of SIMULATION_SLOTS,
    once per slot per day, with catch-up (see _due_slots). simulate_next_round
    is idempotent (per-Tournament row lock), so a duplicate/late fire is safe
    — the risk this loop protects against is a MISSED fire, not a double one."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired):
                data = await _post_internal("/clubs/simulate-round")
                logger.info("Tournament round simulation fired for slot %s: %s matches", slot, data.get("matches_simulated"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Tournament simulation loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_lineup_reminder_loop() -> None:
    """Fires POST /internal/clubs/lineup-reminders REMINDER_LEAD_MINUTES
    before each simulation slot, once per slot per day, with the same
    catch-up behavior as run_simulation_loop."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=REMINDER_LEAD_MINUTES):
                data = await _post_internal("/clubs/lineup-reminders")
                logger.info("Lineup reminders fired for slot %s: %s clubs notified", slot, data.get("clubs_notified"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Lineup reminder loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec -T bot python -m pytest tests/test_tournament_scheduler.py -v
```

Expected: PASS, all 5 tests.

- [ ] **Step 6: Register both loops in `bot.py`**

In `bot/bot.py`, add to the imports:

```python
from services.tournament_scheduler import run_lineup_reminder_loop, run_simulation_loop
```

In `run_polling()`, add two entries to the `background_tasks` list (alongside the existing three):

```python
    background_tasks = [
        asyncio.create_task(run_notification_dispatcher(bot)),
        # Daily reward reminder disabled — see run_webhook() below.
        asyncio.create_task(run_free_pack_notifier(bot)),
        asyncio.create_task(run_premium_subscription_check(bot)),
        asyncio.create_task(run_simulation_loop()),
        asyncio.create_task(run_lineup_reminder_loop()),
    ]
```

In `run_webhook()`, add the same two `asyncio.create_task(...)` calls alongside the existing three (this function doesn't collect them into a list — check its current exact structure and match the existing style: bare `asyncio.create_task(...)` statements, not assigned to a variable).

- [ ] **Step 7: Add the `club_match` deep-link entry**

In `bot/services/notifier.py`, add one entry to `_MATCH_PATH_PREFIXES`:

```python
_MATCH_PATH_PREFIXES = {
    "penalty_match": "/play/penalty/matches",
    "tactico_match": "/play/tactico/matches",
    "club_match": "/clubs/tournament",
}
```

Do not add entries for `club_lineup_reminder`/`club_tournament_results_ready` — per the design, these deliberately fall back to the generic "open the app" keyboard `_keyboard_for` already produces when a type has no prefix entry (no code change needed there).

- [ ] **Step 8: Restart the bot and verify it starts cleanly**

```bash
docker compose restart bot
docker compose logs bot --tail 30
```

Confirm no import errors or crash-loop; confirm the log shows the bot reach "Start polling"/"Run polling for bot" as it always does, with no new exceptions.

- [ ] **Step 9: Commit**

```bash
git add bot/services/tournament_scheduler.py bot/bot.py bot/services/notifier.py bot/tests/test_tournament_scheduler.py
git commit -m "Add bot-side tournament scheduler loops and club_match deep-link"
```

(If Step 1 found no bot-side pytest setup and you used a standalone script instead, adjust the git add list to whatever you actually created, and say so explicitly in the commit message.)
