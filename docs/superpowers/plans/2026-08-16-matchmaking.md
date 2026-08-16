# Opponent Matchmaking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a player press "Играть" in Тактико or Пенальти and be automatically paired with any other player currently searching for the same game, with a pre-match reveal of the opponent's nickname/rating/stats, then play out through the existing PvP match flow unchanged.

**Architecture:** A new per-game queue table (`TacticoQueueEntry`/`PenaltyQueueEntry`) plus a pairing function that runs *inside* the existing status-poll endpoint (no background worker, no websockets — this project has neither). Pairing uses `SELECT ... FOR UPDATE` / `FOR UPDATE SKIP LOCKED` so two concurrent polls can never double-pair or deadlock. Once paired, a `TacticoMatch`/`PenaltyMatch` row is created directly `in_progress` with a new `online` opponent type, and every existing match-lifecycle code path (round submission, forfeit, timeout sweep, `matchGuardStore`) takes over completely unchanged.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pytest (async, in-memory SQLite) on the backend; React 18, TypeScript, TanStack Query on the frontend.

## Global Constraints

- No rating/skill filtering — pair with whoever else is waiting for the same game, regardless of rating.
- Match starts automatically ~3 seconds after the reveal screen appears — no "Ready" confirmation from either side.
- Search times out after exactly 60 seconds with no opponent.
- A finished matchmade match updates `tactics_rating`/`penalty_rating` through the *exact same* win/draw/loss delta logic (+3/+1/-1, opposite mapping for the other side) already used for friend matches — no new rating logic.
- Matchmade matches grant **zero coins** — this must fall out naturally from *not* adding `online` to the existing bot-only coin-reward branch, not from a new conditional (anti-collusion: two accounts of the same person queuing together must not be able to farm coins).
- The hourly attempt counter (`tactico_hourly_attempts`/`penalty_hourly_attempts`, shared with bot matches) is consumed only at the moment of pairing, never at "join queue" time — an unsuccessful 60s search must not cost an attempt.
- Every player-facing string (button labels, search/timeout/error messages) must be plain, friendly Russian — never a raw backend exception string, HTTP status phrase, or English text. The exact verbatim strings are given in each task below; do not paraphrase them.
- Concurrency correctness (no double-pairing, no deadlock) is the primary safety property of this feature and is called out explicitly in the relevant tasks' testing steps.

### A note on testing real concurrency (read before Tasks 3/7)

The spec calls for tests using real concurrent requests (`asyncio.gather`) to prove the pairing algorithm is race-safe. This is **not achievable through this project's pytest suite**: `backend/tests/conftest.py` runs against `sqlite+aiosqlite://` with a `StaticPool` (a single shared physical connection for every test session), and SQLite has no row-level locking at all — `SELECT ... FOR UPDATE` and `FOR UPDATE SKIP LOCKED` are the entire safety mechanism this feature depends on, and neither has any real effect against SQLite. This exact limitation is already documented in this repo's `CLAUDE.md`: *"Row-level locking (`SELECT ... FOR UPDATE`) is not exercised by the SQLite test DB — verify locking-dependent changes manually against real Postgres."*

So: pytest tests in this plan verify the pairing **logic** is correct (sequential calls — join A, join B, poll A, confirm both paired to the same match, etc.), and Tasks 3 and 7 each end with an explicit **manual verification step against the real Postgres-backed dev stack** (two concurrent terminal sessions hitting the running backend) as the actual proof of race-safety — mirroring how this project already handles every other row-locking-dependent code path. Do not write an `asyncio.gather`-based "concurrency test" against the SQLite suite; it would not prove anything and would misrepresent test coverage.

---

## File Structure

- `backend/app/models/tactico.py` — add `TacticoQueueEntry` (new tables live in the same file as their game's other models, matching this repo's existing convention: `TacticoSquad`/`TacticoSquadCard`/`TacticoMatch` already share this file).
- `backend/app/models/penalty.py` — add `PenaltyQueueEntry`, add `opponent_type` to `PenaltyMatch`.
- `backend/app/models/enums.py` — add `online` to `TacticoOpponentType`; add new `PenaltyOpponentType` enum.
- `backend/alembic/versions/0043_tactico_matchmaking.py`, `0044_penalty_matchmaking.py` — new migrations, one per game (matches this repo's existing one-revision-per-logical-change granularity).
- `backend/app/services/tactico_service.py` — add `start_search`/`get_search_status`/`cancel_search`/`_hourly_slot_available`; **fix three existing conditionals that only check `== TacticoOpponentType.friend` and would silently misbehave for the new `online` type** (identified in Task 3).
- `backend/app/services/penalty_match_service.py` — add the Penalty equivalents. No existing conditional logic needs fixing here — `PenaltyMatch` has never had a `bot` code path to accidentally exclude `online` from (confirmed by reading the file in full: every branch already assumes two human players unconditionally).
- `backend/app/schemas/tactico.py` — add `TacticoSearchStatusOut`.
- `backend/app/schemas/penalty_match.py` — add `PenaltySearchStatusOut`, add `opponent_type` to `PenaltyMatchOut`.
- `backend/app/schemas/profile.py` — add `tactics_rating`/`penalty_rating` to `ProfilePublicOut`.
- `backend/app/routers/tactico.py`, `backend/app/routers/penalty_matches.py` — add the three matchmaking endpoints each.
- `frontend/src/types/index.ts` — add `TacticoSearchStatus`/`PenaltySearchStatus` types, extend `TacticoOpponentType`, add `PenaltyOpponentType`, extend `PenaltyMatch`/`ProfilePublic`.
- `frontend/src/api/tactico.ts`, `frontend/src/api/penalty.ts` — add the three client functions each.
- `frontend/src/pages/TacticoSearchPage.tsx`, `frontend/src/pages/PenaltySearchPage.tsx` — new full-flow pages (searching → reveal → auto-navigate), each self-contained (mirrors how `PackOpenPage.tsx` owns multiple internal phases rather than splitting into several route-level pages).
- `frontend/src/pages/TacticoMatchesPage.tsx`, `frontend/src/pages/PenaltyMatchesPage.tsx` — add the primary "Играть" entry button; re-lay-out the existing secondary buttons underneath it.
- `frontend/src/pages/TacticoMatchPage.tsx` — fix the two opponent-type label ternaries that would otherwise mislabel an `online` match as "Против друга".
- `frontend/src/App.tsx` — add `/play/tactico/search` and `/play/penalty/matches/search` routes.

Decomposition: **not** introducing a shared matchmaking helper/table across the two games — the spec explicitly keeps `TacticoQueueEntry`/`PenaltyQueueEntry` as separate tables, matching this codebase's existing convention that Tactico and Penalty never share tables or service code despite very similar shapes (confirmed: `_has_active_match`, `_hydrate_match`, `forfeit_match` are all already independently duplicated per game today). Tasks below follow the same split: full Tactico stack first, then full Penalty stack, with the tiny shared prerequisite (public-profile rating fields) done once upfront since both reveal screens need it.

---

### Task 1: Public profile — expose `tactics_rating`/`penalty_rating`

**Files:**
- Modify: `backend/app/schemas/profile.py`
- Modify: `backend/app/services/profile_service.py`
- Modify: `frontend/src/types/index.ts`
- Test: `backend/tests/test_users.py` (new file — no test currently covers the public-profile endpoint at all)

**Interfaces:**
- Produces: `ProfilePublicOut.tactics_rating: int`, `ProfilePublicOut.penalty_rating: int` — consumed by both games' reveal screens in Tasks 5 and 9.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_users.py`:

```python
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_public_profile_exposes_tactics_and_penalty_rating(client, db_session, bot_token):
    viewer = await _register(client, db_session, 870001, bot_token)
    target = await _register(client, db_session, 870002, bot_token)
    target.tactics_rating = 42
    target.penalty_rating = 17
    db_session.add(target)
    await db_session.commit()

    resp = await client.get(f"/api/v1/users/{target.id}", headers=telegram_headers(870001, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["tactics_rating"] == 42
    assert body["penalty_rating"] == 17
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_users.py -v`
Expected: FAIL — `KeyError` or `assert None == 42` (field missing from the response).

- [ ] **Step 3: Add the fields to `ProfilePublicOut`**

In `backend/app/schemas/profile.py`, add to the `ProfilePublicOut` class body (any position among the existing `int` fields, e.g. right after `arena_rank: int`):

```python
    tactics_rating: int
    penalty_rating: int
```

- [ ] **Step 4: Populate them in `_build_public`**

In `backend/app/services/profile_service.py`, add two lines to the `ProfilePublicOut(...)` constructor call inside `_build_public` (alongside the existing `arena_rating=user.arena_rating,`):

```python
        tactics_rating=user.tactics_rating,
        penalty_rating=user.penalty_rating,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest tests/test_users.py -v`
Expected: PASS

- [ ] **Step 6: Add the fields to the frontend type**

In `frontend/src/types/index.ts`, add to the `ProfilePublic` interface (alongside the existing `arena_rank: number;`):

```typescript
  tactics_rating: number;
  penalty_rating: number;
```

- [ ] **Step 7: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/profile.py backend/app/services/profile_service.py backend/tests/test_users.py frontend/src/types/index.ts
git commit -m "Expose tactics_rating/penalty_rating on the public profile"
```

---

### Task 2: Tactico matchmaking — data model and migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/tactico.py`
- Create: `backend/alembic/versions/0043_tactico_matchmaking.py`
- Test: `backend/tests/test_tactico.py` (append)

**Interfaces:**
- Produces: `TacticoOpponentType.online`; `TacticoQueueEntry` model (`id, user_id, created_at, matched_match_id`), consumed by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_tactico.py`:

```python
from app.models.tactico import TacticoQueueEntry


async def test_tactico_opponent_type_has_online_member():
    assert TacticoOpponentType.online == "online"


async def test_tactico_queue_entry_roundtrip(client, db_session, bot_token):
    headers = await _register(client, bot_token, 951001)
    user = await get_user_by_telegram_id(db_session, 951001)

    entry = TacticoQueueEntry(user_id=user.id)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    assert entry.id is not None
    assert entry.matched_match_id is None
    assert entry.created_at is not None


async def test_tactico_queue_entry_user_id_is_unique(client, db_session, bot_token):
    headers = await _register(client, bot_token, 951002)
    user = await get_user_by_telegram_id(db_session, 951002)

    db_session.add(TacticoQueueEntry(user_id=user.id))
    await db_session.commit()

    db_session.add(TacticoQueueEntry(user_id=user.id))
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()
```

Add `TacticoOpponentType` to the existing `from app.models.enums import (...)` import block at the top of the file if it isn't already imported there (it is not — this file currently imports `CardSource, NotificationType, Position, Rarity` from `app.models.enums`, not `TacticoOpponentType`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_tactico.py -k "queue_entry or online_member" -v`
Expected: FAIL — `ImportError` (`TacticoQueueEntry` doesn't exist yet) / `AttributeError` (`online` not a member yet).

- [ ] **Step 3: Add `online` to `TacticoOpponentType`**

In `backend/app/models/enums.py`, change:

```python
class TacticoOpponentType(str, enum.Enum):
    bot = "bot"
    friend = "friend"
```

to:

```python
class TacticoOpponentType(str, enum.Enum):
    bot = "bot"
    friend = "friend"
    online = "online"
```

- [ ] **Step 4: Add `TacticoQueueEntry` to `backend/app/models/tactico.py`**

Add at the end of the file (after the existing `TacticoMatch` class):

```python
class TacticoQueueEntry(Base):
    """One player currently searching for an opponent via matchmaking.
    `matched_match_id` is set by whichever poll (theirs or the paired
    player's) performs the pairing — see wheel_service.py-style "the reader
    does the lazy work" pattern, applied here to matchmaking instead of
    round timeouts (see tactico_service.get_search_status)."""

    __tablename__ = "tactico_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tactico_matches.id", ondelete="SET NULL"), nullable=True
    )
```

(`DateTime`, `ForeignKey`, `Integer`, `Optional`, `utcnow`, `Mapped`, `mapped_column`, `Base` are all already imported at the top of this file — no new imports needed.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_tactico.py -k "queue_entry or online_member" -v`
Expected: 3 passed.

- [ ] **Step 6: Write the migration**

First confirm the actual current Alembic head (should be `0042`, but verify — do not assume):

Run: `docker compose exec backend alembic heads`

Create `backend/alembic/versions/0043_tactico_matchmaking.py` (adjust `down_revision` if Step 6's check showed a different actual head):

```python
"""Tactico matchmaking: queue table + online opponent type

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tactico_opponent_type_enum ADD VALUE IF NOT EXISTS 'online'")

    op.create_table(
        "tactico_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("tactico_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_unique_constraint("uq_tactico_queue_entries_user_id", "tactico_queue_entries", ["user_id"])
    op.create_index("ix_tactico_queue_entries_user_id", "tactico_queue_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tactico_queue_entries_user_id", table_name="tactico_queue_entries")
    op.drop_table("tactico_queue_entries")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'online' on the enum
    # on downgrade is harmless (mirrors every prior migration's same note).
```

- [ ] **Step 7: Full backend import sanity check**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/tactico.py backend/alembic/versions/0043_tactico_matchmaking.py backend/tests/test_tactico.py
git commit -m "Add Tactico matchmaking data model: TacticoQueueEntry, online opponent type"
```

---

### Task 3: Tactico matchmaking — service layer (search, pairing, cancel)

**Files:**
- Modify: `backend/app/services/tactico_service.py`
- Test: `backend/tests/test_tactico.py` (append)

**Interfaces:**
- Consumes: `TacticoQueueEntry` (Task 2), `get_squad`, `_has_active_match`, `_pick_phase`, `_consume_hourly_slot`, `_ensure_hourly_reset` (all pre-existing in this file).
- Produces: `tactico_service.start_search(db, user) -> TacticoQueueEntry`, `tactico_service.get_search_status(db, user) -> tuple[str, Optional[int]]` (status is one of `"not_searching"`, `"searching"`, `"matched"`, `"timeout"`), `tactico_service.cancel_search(db, user) -> None`, `tactico_service.MATCHMAKING_TIMEOUT_SECONDS: int = 60` — consumed by Task 4's router.

**Critical existing-code fixes bundled into this task** (found by tracing every `opponent_type ==`/`!=` check in this file against what an `online` match needs — without these three fixes, an online match would silently never update the opponent's rating, and would silently stop advancing after the first round with no idle-player timeout):

1. `_finish_match`'s `is_friend` check currently reads `match.opponent_type == TacticoOpponentType.friend and match.opponent_user_id is not None` — this gates whether the *opponent's* rating gets updated and whether both players get a "match finished" notification. An `online` match has a real opponent exactly like a `friend` match does; this must become `match.opponent_type != TacticoOpponentType.bot and match.opponent_user_id is not None`.
2. `_hydrate_match`'s `round_deadline` surfacing currently only fires `if match.opponent_type == TacticoOpponentType.friend and ...` — must become `if match.opponent_type != TacticoOpponentType.bot and ...`, or the frontend never learns an `online` match's round has a deadline.
3. `submit_round`'s post-resolve block that re-arms `current_deadline` and sends the "your turn" notification currently only fires `if resolved and match.opponent_type == TacticoOpponentType.friend:` — must become `if resolved and match.opponent_type != TacticoOpponentType.bot:`, or an `online` match's round timeout sweep loses track after the very first round (no deadline ever gets set again, so an idle opponent can never be auto-resolved).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tactico.py`:

```python
async def test_start_search_requires_complete_squad(client, bot_token):
    headers = await _register(client, bot_token, 952001)
    resp = await client.post("/api/v1/tactico/matchmaking/search", headers=headers)
    assert resp.status_code == 409
    assert "состав" in resp.json()["error"]["message"]


async def test_start_search_rejects_second_entry(client, db_session, bot_token):
    headers = await _register(client, bot_token, 952002)
    user = await get_user_by_telegram_id(db_session, 952002)
    await _build_squad_cards(db_session, user.id)

    first = await client.post("/api/v1/tactico/matchmaking/search", headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/v1/tactico/matchmaking/search", headers=headers)
    assert second.status_code == 409
    assert "уже ищешь" in second.json()["error"]["message"]


async def test_start_search_rejects_when_active_match_exists(client, db_session, bot_token):
    headers = await _register(client, bot_token, 952003)
    user = await get_user_by_telegram_id(db_session, 952003)
    await _build_squad_cards(db_session, user.id)
    bot_match = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "easy"})
    assert bot_match.status_code == 200

    resp = await client.post("/api/v1/tactico/matchmaking/search", headers=headers)
    assert resp.status_code == 409
    assert "в процессе" in resp.json()["error"]["message"]


async def test_status_before_searching_is_not_searching(client, bot_token):
    headers = await _register(client, bot_token, 952004)
    resp = await client.get("/api/v1/tactico/matchmaking/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_searching"


async def test_two_waiting_players_get_paired_on_poll(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 952005)
    user_a = await get_user_by_telegram_id(db_session, 952005)
    await _build_squad_cards(db_session, user_a.id)
    headers_b = await _register(client, bot_token, 952006)
    user_b = await get_user_by_telegram_id(db_session, 952006)
    await _build_squad_cards(db_session, user_b.id)

    assert (await client.post("/api/v1/tactico/matchmaking/search", headers=headers_a)).status_code == 200
    assert (await client.post("/api/v1/tactico/matchmaking/search", headers=headers_b)).status_code == 200

    status_a = await client.get("/api/v1/tactico/matchmaking/status", headers=headers_a)
    assert status_a.status_code == 200
    body_a = status_a.json()
    assert body_a["status"] == "matched"
    match_id = body_a["match_id"]
    assert match_id is not None

    status_b = await client.get("/api/v1/tactico/matchmaking/status", headers=headers_b)
    assert status_b.json() == {"status": "matched", "match_id": match_id, "created_at": None}

    match_resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    match_body = match_resp.json()
    assert match_body["opponent_type"] == "online"
    assert match_body["status"] == "in_progress"
    assert match_body["round_deadline"] is not None  # fix #2 above, verified end-to-end


async def test_matchmaking_grants_zero_coins_and_updates_both_ratings(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 952007)
    user_a = await get_user_by_telegram_id(db_session, 952007)
    card_ids_a = await _build_squad_cards(db_session, user_a.id, rating=90)
    headers_b = await _register(client, bot_token, 952008)
    user_b = await get_user_by_telegram_id(db_session, 952008)
    card_ids_b = await _build_squad_cards(db_session, user_b.id, rating=10)

    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_a)
    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_b)
    status_a = await client.get("/api/v1/tactico/matchmaking/status", headers=headers_a)
    match_id = status_a.json()["match_id"]

    for card_a, card_b in zip(card_ids_a, card_ids_b):
        resp_a = await client.post(
            f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_a, json={"user_card_id": card_a}
        )
        if resp_a.json()["status"] != "in_progress":
            break
        await client.post(
            f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_b, json={"user_card_id": card_b}
        )

    final = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    body = final.json()
    assert body["status"] == "finished"
    assert body["reward_coins"] == 0  # no coins for matchmaking, per the spec

    await db_session.refresh(user_a)
    await db_session.refresh(user_b)
    assert user_a.tactics_rating != 0 or user_b.tactics_rating != 0  # someone's rating moved
    assert user_a.tactics_rating + user_b.tactics_rating in (2, -2, 3 - 1, 1 + 1)  # win/loss (+3/-1) or draw (+1/+1)


async def test_search_timeout_after_60_seconds(client, db_session, bot_token, monkeypatch):
    from datetime import datetime, timedelta, timezone

    headers = await _register(client, bot_token, 952009)
    user = await get_user_by_telegram_id(db_session, 952009)
    await _build_squad_cards(db_session, user.id)
    await client.post("/api/v1/tactico/matchmaking/search", headers=headers)

    entry = (
        await db_session.execute(select(TacticoQueueEntry).where(TacticoQueueEntry.user_id == user.id))
    ).scalar_one()
    entry.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db_session.add(entry)
    await db_session.commit()

    resp = await client.get("/api/v1/tactico/matchmaking/status", headers=headers)
    assert resp.json()["status"] == "timeout"

    remaining = (
        await db_session.execute(select(TacticoQueueEntry).where(TacticoQueueEntry.user_id == user.id))
    ).scalar_one_or_none()
    assert remaining is None


async def test_cancel_search_removes_entry(client, db_session, bot_token):
    headers = await _register(client, bot_token, 952010)
    user = await get_user_by_telegram_id(db_session, 952010)
    await _build_squad_cards(db_session, user.id)
    await client.post("/api/v1/tactico/matchmaking/search", headers=headers)

    resp = await client.post("/api/v1/tactico/matchmaking/cancel", headers=headers)
    assert resp.status_code == 204

    status = await client.get("/api/v1/tactico/matchmaking/status", headers=headers)
    assert status.json()["status"] == "not_searching"


async def test_cancel_search_rejected_once_matched(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 952011)
    user_a = await get_user_by_telegram_id(db_session, 952011)
    await _build_squad_cards(db_session, user_a.id)
    headers_b = await _register(client, bot_token, 952012)
    user_b = await get_user_by_telegram_id(db_session, 952012)
    await _build_squad_cards(db_session, user_b.id)

    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_a)
    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_b)
    await client.get("/api/v1/tactico/matchmaking/status", headers=headers_a)  # triggers pairing

    resp = await client.post("/api/v1/tactico/matchmaking/cancel", headers=headers_a)
    assert resp.status_code == 409
    assert "уже найден" in resp.json()["error"]["message"]


async def test_pairing_skips_candidate_with_stale_hourly_limit(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 952013)
    user_a = await get_user_by_telegram_id(db_session, 952013)
    await _build_squad_cards(db_session, user_a.id)
    headers_b = await _register(client, bot_token, 952014)
    user_b = await get_user_by_telegram_id(db_session, 952014)
    await _build_squad_cards(db_session, user_b.id)
    await _set_config(db_session, hourly_game_limit=1)
    user_b.tactico_hourly_attempts = 1
    db_session.add(user_b)
    await db_session.commit()

    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_a)
    await client.post("/api/v1/tactico/matchmaking/search", headers=headers_b)
    status_a = await client.get("/api/v1/tactico/matchmaking/status", headers=headers_a)
    # B is over its hourly limit — pairing must skip B rather than crash or pair anyway
    assert status_a.json()["status"] == "searching"
```

Add `from sqlalchemy import select` at the top of `backend/tests/test_tactico.py` if not already imported (it is — confirmed at the top of the existing file).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_tactico.py -k "search or matchmaking or pairing" -v`
Expected: FAIL — 404 (routes don't exist yet) / `AttributeError` (service functions don't exist yet).

- [ ] **Step 3: Add the three existing-conditional fixes**

In `backend/app/services/tactico_service.py`, apply these three targeted edits (do not change anything else in the surrounding lines):

In `_finish_match`, change:

```python
    is_friend = match.opponent_type == TacticoOpponentType.friend and match.opponent_user_id is not None
```

to:

```python
    # Both `friend` and `online` matches have a real second player whose
    # rating/notification need updating — only `bot` doesn't.
    is_friend = match.opponent_type != TacticoOpponentType.bot and match.opponent_user_id is not None
```

In `_hydrate_match`, change:

```python
        if match.opponent_type == TacticoOpponentType.friend and one_side_committed and state.get("current_deadline"):
```

to:

```python
        if match.opponent_type != TacticoOpponentType.bot and one_side_committed and state.get("current_deadline"):
```

In `submit_round`, change:

```python
        if resolved and match.opponent_type == TacticoOpponentType.friend:
```

to:

```python
        if resolved and match.opponent_type != TacticoOpponentType.bot:
```

- [ ] **Step 4: Add the matchmaking functions**

Add near the bottom of `backend/app/services/tactico_service.py`, after `get_match`:

```python
# ---------------------------------------------------------------------------
# Matchmaking
# ---------------------------------------------------------------------------

MATCHMAKING_TIMEOUT_SECONDS = 60


async def _hourly_slot_available(db: AsyncSession, user_id: int, config: GameConfig) -> bool:
    """Non-raising check mirroring the first half of `_consume_hourly_slot` —
    used to decide whether a queue entry is still eligible for pairing
    without crashing the *other* player's poll if it turns out someone's
    limit was hit while they sat in the queue."""
    locked_user = await lock_user_for_update(db, user_id)
    await _ensure_hourly_reset(locked_user)
    db.add(locked_user)
    return locked_user.tactico_hourly_attempts < config.hourly_game_limit


async def start_search(db: AsyncSession, user: User) -> TacticoQueueEntry:
    if await _has_active_match(db, user.id):
        raise ConflictError("У тебя уже есть матч в процессе — заверши его, прежде чем искать нового соперника")
    existing = await db.execute(select(TacticoQueueEntry).where(TacticoQueueEntry.user_id == user.id))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Ты уже ищешь соперника")
    squad = await get_squad(db, user)
    if not squad.is_complete:
        raise ConflictError(f"Собери полный состав из {SQUAD_SIZE} карточек, прежде чем искать соперника")

    entry = TacticoQueueEntry(user_id=user.id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_search_status(db: AsyncSession, user: User) -> tuple[str, Optional[int]]:
    """Also *is* the pairing attempt — every poller tries to pair itself
    with the oldest other waiting entry. See the design spec's pairing
    algorithm; there is no separate sweep."""
    result = await db.execute(
        select(TacticoQueueEntry).where(TacticoQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    my_entry = result.scalar_one_or_none()
    if my_entry is None:
        return "not_searching", None

    if my_entry.matched_match_id is not None:
        await db.commit()
        return "matched", my_entry.matched_match_id

    if datetime.now(timezone.utc) - ensure_aware(my_entry.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS):
        await db.delete(my_entry)
        await db.commit()
        return "timeout", None

    candidate_result = await db.execute(
        select(TacticoQueueEntry)
        .where(TacticoQueueEntry.user_id != user.id, TacticoQueueEntry.matched_match_id.is_(None))
        .order_by(TacticoQueueEntry.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    candidate = candidate_result.scalar_one_or_none()
    if candidate is None:
        await db.commit()
        return "searching", None

    candidate_user = await db.get(User, candidate.user_id)
    config = await get_config(db)

    # Re-validate everything right before creating the match — state may
    # have drifted while both entries sat in the queue. Each side is
    # checked independently; either, both, or neither may have gone stale.
    squad_a = await get_squad(db, user)
    squad_b = await get_squad(db, candidate_user)
    stale: list[TacticoQueueEntry] = []
    if await _has_active_match(db, user.id) or not squad_a.is_complete or not await _hourly_slot_available(db, user.id, config):
        stale.append(my_entry)
    if (
        await _has_active_match(db, candidate.user_id)
        or not squad_b.is_complete
        or not await _hourly_slot_available(db, candidate.user_id, config)
    ):
        stale.append(candidate)
    if stale:
        for entry in stale:
            await db.delete(entry)
        await db.commit()
        return ("not_searching" if my_entry in stale else "searching"), None

    locked_user = await _consume_hourly_slot(db, user.id, config)
    locked_candidate = await _consume_hourly_slot(db, candidate.user_id, config)

    state = {
        "rounds": [],
        "current_index": 0,
        "current_phase": _pick_phase(),
        "current_deadline": (
            datetime.now(timezone.utc) + timedelta(hours=config.tactico_round_timeout_hours)
        ).isoformat(),
        "user_pool": [c.id for c in squad_a.cards],
        "opponent_pool": [c.id for c in squad_b.cards],
        "user_pending_card_id": None,
        "user_pending_snapshot": None,
        "opponent_pending_card_id": None,
        "opponent_pending_snapshot": None,
    }
    match = TacticoMatch(
        user_id=locked_user.id,
        opponent_user_id=locked_candidate.id,
        opponent_name=locked_candidate.full_display_name(),
        opponent_type=TacticoOpponentType.online,
        difficulty=None,
        status=TacticoMatchStatus.in_progress,
        server_state=state,
    )
    db.add(match)
    await db.flush()

    my_entry.matched_match_id = match.id
    candidate.matched_match_id = match.id
    db.add(my_entry)
    db.add(candidate)
    await db.commit()
    return "matched", match.id


async def cancel_search(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(TacticoQueueEntry).where(TacticoQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Ты не ищешь соперника")
    if entry.matched_match_id is not None:
        raise ConflictError("Соперник уже найден — матч начинается")
    await db.delete(entry)
    await db.commit()
```

Add `from app.models.tactico import TacticoQueueEntry` to the existing `from app.models.tactico import TacticoMatch, TacticoSquad, TacticoSquadCard` import line at the top of the file (combine into one import).

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_tactico.py -v`
Expected: all passed.

- [ ] **Step 6: Full backend regression check**

Run: `docker compose exec backend pytest tests/ -q`
Expected: no new failures versus the pre-existing baseline (check `git stash` + rerun if any failure looks suspicious, to confirm it's not caused by this change).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/tactico_service.py backend/tests/test_tactico.py
git commit -m "Add Tactico matchmaking service: search, race-safe pairing, cancel"
```

- [ ] **Step 8: Manual concurrency verification against real Postgres (required — see Global Constraints note)**

Dev-mode auth (`X-Dev-Mode: true`) always resolves to the *same single* fixed dev user (`settings.dev_user_telegram_id`) — confirmed by reading `backend/app/core/dependencies.py`'s `get_current_user`, which has no way to select a different dev-mode identity per request. Getting two independently-authenticated users against the real running dev stack requires two real, HMAC-signed `X-Telegram-Init-Data` headers (the same mechanism `tests/utils.py::make_init_data` already implements for pytest) built with the actual configured bot token, which only the running backend process itself has access to (never read/print `.env` directly — see CLAUDE.md). So this verification runs as a small script executed *inside* the backend container, which already has that token loaded via its own settings.

With the normal `docker compose up` dev stack running (real Postgres) and this migration applied (`docker compose exec backend alembic upgrade head`):

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'EOF'
SELECT id FROM players WHERE is_active = true LIMIT 22;
EOF
```

Copy the 22 printed ids into the seeding step below (replace `PLAYER_ID_1..PLAYER_ID_22` — 11 for user A, 11 for user B; any 22 distinct active player ids work, they don't need to be contiguous).

```bash
cat > /tmp/mm_verify.py <<'PYEOF'
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx

from app.config import get_settings

settings = get_settings()
BOT_TOKEN = settings.telegram_bot_token
BASE = "http://localhost:8000/api/v1"


def make_init_data(telegram_id: int, first_name: str) -> str:
    user = {"id": telegram_id, "first_name": first_name}
    data = {"auth_date": str(int(time.time())), "query_id": "verify", "user": json.dumps(user, separators=(",", ":"))}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


async def main():
    headers_a = {"X-Telegram-Init-Data": make_init_data(910001001, "VerifyA")}
    headers_b = {"X-Telegram-Init-Data": make_init_data(910001002, "VerifyB")}
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as client:
        session_a = (await client.post("/auth/session", headers=headers_a)).json()
        session_b = (await client.post("/auth/session", headers=headers_b)).json()
        print("user ids:", session_a["id"], session_b["id"])
        print("Now run the SQL below (with these two user ids) to seed each a full squad, then press Enter.")
        input()

        search_a, search_b = await asyncio.gather(
            client.post("/tactico/matchmaking/search", headers=headers_a),
            client.post("/tactico/matchmaking/search", headers=headers_b),
        )
        print("search A:", search_a.status_code, search_a.text[:300])
        print("search B:", search_b.status_code, search_b.text[:300])

        status_a, status_b = await asyncio.gather(
            client.get("/tactico/matchmaking/status", headers=headers_a),
            client.get("/tactico/matchmaking/status", headers=headers_b),
        )
        print("status A:", status_a.json())
        print("status B:", status_b.json())
        assert status_a.json()["status"] == "matched", "user A was not paired"
        assert status_a.json()["match_id"] == status_b.json()["match_id"], "paired to two different matches!"
        print("OK: both paired to the same match", status_a.json()["match_id"])


asyncio.run(main())
PYEOF
docker compose cp /tmp/mm_verify.py backend:/app/mm_verify.py
docker compose exec backend python mm_verify.py
```

When the script pauses at `input()`, in a second terminal seed both users' squads (replace `<user_a_id>`/`<user_b_id>` with the two ids the script just printed, and the 22 player ids from the query above — 11 per user):

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<EOF
INSERT INTO tactico_squads (user_id, created_at, updated_at)
  VALUES (<user_a_id>, now(), now()), (<user_b_id>, now(), now())
  RETURNING id, user_id;
EOF
```

Note the two returned squad ids, then (replacing `<squad_a_id>`/`<squad_b_id>` and the 22 player ids):

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<EOF
INSERT INTO user_cards (owner_id, player_id, source, serial_number, is_in_tactico_squad, acquired_at)
SELECT <user_a_id>, p.id, 'seed', row_number() OVER (), true, now()
FROM (VALUES (PLAYER_ID_1),(PLAYER_ID_2),(PLAYER_ID_3),(PLAYER_ID_4),(PLAYER_ID_5),(PLAYER_ID_6),(PLAYER_ID_7),(PLAYER_ID_8),(PLAYER_ID_9),(PLAYER_ID_10),(PLAYER_ID_11)) AS p(id)
RETURNING id;
EOF
```

(`user_cards` has no `updated_at` column, only `acquired_at` — confirmed against `backend/app/models/card.py`; unlike `tactico_squads`, this table doesn't use `TimestampMixin`.)

then the same `INSERT` again for `<user_b_id>` with the other 11 player ids, then link both sets of 11 `user_cards.id` values into `tactico_squad_cards (squad_id, user_card_id)` for `<squad_a_id>`/`<squad_b_id>` respectively. Once both squads show 11 cards, return to the paused script and press Enter.

Confirm the script prints `OK: both paired to the same match <id>`. Then independently verify via psql:

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'EOF'
SELECT id, user_id, opponent_user_id, opponent_type, status FROM tactico_matches ORDER BY id DESC LIMIT 3;
SELECT id, user_id, matched_match_id FROM tactico_queue_entries ORDER BY id DESC LIMIT 3;
EOF
```

Confirm exactly one new `tactico_matches` row with `opponent_type = 'online'`, and both queue entries (if not yet cleaned up) pointing at the same `matched_match_id`. Repeat the whole script run 5-10 times (fresh synthetic telegram ids each time, e.g. increment `910001001`/`910001002`) to build confidence — a race window this narrow may not reproduce every single run. Clean up the synthetic test users afterward if this was run against a shared dev database, not a throwaway local one.

---

### Task 4: Tactico matchmaking — router, schema, frontend API client

**Files:**
- Modify: `backend/app/schemas/tactico.py`
- Modify: `backend/app/routers/tactico.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/tactico.ts`
- Test: `backend/tests/test_tactico.py` (append)

**Interfaces:**
- Consumes: `tactico_service.start_search`/`get_search_status`/`cancel_search`/`MATCHMAKING_TIMEOUT_SECONDS` (Task 3).
- Produces: `POST /api/v1/tactico/matchmaking/search`, `GET /api/v1/tactico/matchmaking/status`, `POST /api/v1/tactico/matchmaking/cancel` — consumed by Task 5's frontend page. TS `TacticoSearchStatus` type, `startTacticoSearch()`/`fetchTacticoSearchStatus()`/`cancelTacticoSearch()` client functions.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_tactico.py` (this exercises the endpoints already indirectly covered by Task 3's tests through the same routes — this step specifically pins down the response shape/status codes at the HTTP layer):

```python
async def test_search_endpoint_response_shape(client, db_session, bot_token):
    headers = await _register(client, bot_token, 952015)
    user = await get_user_by_telegram_id(db_session, 952015)
    await _build_squad_cards(db_session, user.id)

    resp = await client.post("/api/v1/tactico/matchmaking/search", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "searching"
    assert body["match_id"] is None
    assert body["created_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_tactico.py -k search_endpoint_response_shape -v`
Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Add `TacticoSearchStatusOut` to `backend/app/schemas/tactico.py`**

Add at the end of the file:

```python
class TacticoSearchStatusOut(BaseModel):
    status: Literal["not_searching", "searching", "matched", "timeout"]
    match_id: Optional[int] = None
    created_at: Optional[datetime] = None
```

- [ ] **Step 4: Add the three endpoints to `backend/app/routers/tactico.py`**

Add `TacticoSearchStatusOut` to the existing `from app.schemas.tactico import (...)` block, then add at the end of the file:

```python
@router.post("/matchmaking/search", response_model=TacticoSearchStatusOut)
async def start_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"tactico_search:{user.id}", max_calls=10, window_seconds=60)
    entry = await tactico_service.start_search(db, user)
    return TacticoSearchStatusOut(status="searching", match_id=None, created_at=entry.created_at)


@router.get("/matchmaking/status", response_model=TacticoSearchStatusOut)
async def get_search_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    status, match_id = await tactico_service.get_search_status(db, user)
    return TacticoSearchStatusOut(status=status, match_id=match_id, created_at=None)


@router.post("/matchmaking/cancel", status_code=204)
async def cancel_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await tactico_service.cancel_search(db, user)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_tactico.py -v`
Expected: all passed.

- [ ] **Step 6: Add the frontend TS type**

In `frontend/src/types/index.ts`, change:

```typescript
export type TacticoOpponentType = "bot" | "friend";
```

to:

```typescript
export type TacticoOpponentType = "bot" | "friend" | "online";
```

Add near the `TacticoMatch` interface:

```typescript
export interface TacticoSearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
  created_at: string | null;
}
```

- [ ] **Step 7: Add the frontend API client functions**

Add to `frontend/src/api/tactico.ts`:

```typescript
export async function startTacticoSearch(): Promise<TacticoSearchStatus> {
  const { data } = await api.post<TacticoSearchStatus>("/tactico/matchmaking/search");
  return data;
}

export async function fetchTacticoSearchStatus(): Promise<TacticoSearchStatus> {
  const { data } = await api.get<TacticoSearchStatus>("/tactico/matchmaking/status");
  return data;
}

export async function cancelTacticoSearch(): Promise<void> {
  await api.post("/tactico/matchmaking/cancel");
}
```

Add `TacticoSearchStatus` to the existing `import type { TacticoMatch, TacticoSquad, TacticoStats } from "@/types";` line.

- [ ] **Step 8: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/tactico.py backend/app/routers/tactico.py backend/tests/test_tactico.py frontend/src/types/index.ts frontend/src/api/tactico.ts
git commit -m "Add Tactico matchmaking endpoints and frontend API client"
```

---

### Task 5: Tactico matchmaking — frontend UI

**Files:**
- Create: `frontend/src/pages/TacticoSearchPage.tsx`
- Modify: `frontend/src/pages/TacticoMatchesPage.tsx`
- Modify: `frontend/src/pages/TacticoMatchPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `startTacticoSearch`/`fetchTacticoSearchStatus`/`cancelTacticoSearch` (Task 4), `fetchPublicProfile` (`@/api/profile`, pre-existing), `ProfilePublic.tactics_rating` (Task 1).
- Produces: `/play/tactico/search` route, reachable end-to-end from the "Играть" button through to a live match.

- [ ] **Step 1: Create `frontend/src/pages/TacticoSearchPage.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cancelTacticoSearch, fetchTacticoSearchStatus, startTacticoSearch } from "@/api/tactico";
import { fetchPublicProfile } from "@/api/profile";
import { UserBadge } from "@/components/common/UserBadge";
import { IconTarget, IconUsers } from "@/components/icons";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { ProfilePublic } from "@/types";

const REVEAL_PAUSE_MS = 3000;

export default function TacticoSearchPage() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"starting" | "searching" | "timeout" | "reveal" | "error">("starting");
  const [error, setError] = useState<string | null>(null);
  const [opponent, setOpponent] = useState<ProfilePublic | null>(null);
  const hasStartedRef = useRef(false);

  useEffect(() => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    startTacticoSearch()
      .then(() => setPhase("searching"))
      .catch((err) => {
        setPhase("error");
        setError(formatGameError(err, "Не удалось начать поиск соперника"));
      });
  }, []);

  const { data: status } = useQuery({
    queryKey: ["tactico-search-status"],
    queryFn: fetchTacticoSearchStatus,
    enabled: phase === "searching",
    refetchInterval: () => (phase === "searching" ? 2000 : false),
  });

  useEffect(() => {
    if (!status) return;
    if (status.status === "timeout") {
      setPhase("timeout");
    } else if (status.status === "matched" && status.match_id) {
      const matchId = status.match_id;
      fetchTacticoMatchOpponentAndReveal(matchId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.match_id]);

  const fetchTacticoMatchOpponentAndReveal = async (matchId: number) => {
    try {
      const { fetchTacticoMatch } = await import("@/api/tactico");
      const match = await fetchTacticoMatch(matchId);
      if (match.opponent_user_id) {
        const profile = await fetchPublicProfile(match.opponent_user_id);
        setOpponent(profile);
      }
      setPhase("reveal");
      setTimeout(() => navigate(`/play/tactico/matches/${matchId}`), REVEAL_PAUSE_MS);
    } catch {
      // The match exists even if the reveal fetch failed for some reason —
      // don't strand the player on a dead search screen over a cosmetic step.
      navigate(`/play/tactico/matches/${matchId}`);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelTacticoSearch();
    } catch {
      // Ignore — if this fails because pairing already happened, the
      // player is about to be redirected into the match anyway.
    }
    navigate("/play/tactico");
  };

  if (phase === "error") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={() => navigate("/play/tactico")}
          className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
        >
          Назад
        </button>
      </div>
    );
  }

  if (phase === "timeout") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <IconUsers size={40} className="text-ink-mist-dim" />
        <p className="font-display text-lg font-bold text-ink-chalk">Соперник не найден</p>
        <p className="text-sm text-ink-mist">Попробуй ещё раз</p>
        <div className="flex w-full gap-2">
          <button
            onClick={() => navigate("/play/tactico")}
            className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95"
          >
            Назад
          </button>
          <button
            onClick={() => { hasStartedRef.current = false; setPhase("starting"); }}
            className="flex-1 rounded-2xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95"
          >
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  if (phase === "reveal") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-accent-lime">Соперник найден!</p>
        {opponent ? (
          <>
            <img
              src={opponent.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt="avatar"
              className="h-20 w-20 rounded-full ring-2 ring-accent-lime object-cover"
            />
            <p className="flex items-center gap-1.5 font-display text-xl font-bold text-ink-chalk">
              {opponent.username ?? opponent.first_name ?? "Игрок"}
              <UserBadge badge={opponent.active_badge} />
            </p>
            <p className="text-sm text-ink-mist">Рейтинг Тактико: {opponent.tactics_rating}</p>
          </>
        ) : (
          <p className="text-sm text-ink-mist">Загрузка...</p>
        )}
        <p className="animate-pulse text-xs text-ink-mist-dim">Матч начинается...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <IconTarget size={40} className="animate-pulse text-accent-lime" />
      <p className="font-display text-lg font-bold text-ink-chalk">Ищем соперника...</p>
      <button
        onClick={handleCancel}
        className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
      >
        Отменить
      </button>
    </div>
  );
}
```

(The dynamic `import("@/api/tactico")` inside `fetchTacticoMatchOpponentAndReveal` is only there to avoid a same-file circular naming clash in this snippet — replace it with a plain top-level `import { fetchTacticoMatch, ... } from "@/api/tactico";` alongside the other Task 4 imports at the top of the file; there's no real circularity, this file already imports several other functions from that same module. Use the plain top-level import form.)

- [ ] **Step 2: Register the route in `frontend/src/App.tsx`**

Add the import `import TacticoSearchPage from "@/pages/TacticoSearchPage";`, and add inside the existing `<Route element={<AppLayout />}>` block, alongside `/play/tactico/squad`:

```tsx
        <Route path="/play/tactico/search" element={<TacticoSearchPage />} />
```

- [ ] **Step 3: Add the primary "Играть" button to `TacticoMatchesPage.tsx`**

Replace the existing side-by-side button block:

```tsx
        <div className="flex gap-2">
          <button
            onClick={() => setBotSheetOpen(true)}
            className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-sm font-bold text-bg-base ring-2 ring-accent-green/40 active:scale-95"
          >
            <IconPlay size={17} />
            Играть с ботом
          </button>
          <button
            onClick={() => setChallengeSheetOpen(true)}
            className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-floodlight py-4 text-sm font-bold text-bg-base ring-2 ring-accent-cyan/40 active:scale-95"
          >
            <IconUsers size={17} />
            Вызвать друга
          </button>
        </div>
```

with a primary button on top and the same two as smaller secondary options below it:

```tsx
        <button
          onClick={() => navigate("/play/tactico/search")}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-5 text-base font-bold text-bg-base ring-2 ring-accent/40 active:scale-95"
        >
          <IconPlay size={20} />
          Играть
        </button>
        <div className="flex gap-2">
          <button
            onClick={() => setBotSheetOpen(true)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconPlay size={14} />
            С ботом
          </button>
          <button
            onClick={() => setChallengeSheetOpen(true)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconUsers size={14} />
            Вызвать друга
          </button>
        </div>
```

(This block replaces the `else` branch of the existing `{activeMatch ? (...) : (...)}` conditional — the `activeMatch` "Продолжить матч" branch above it is unchanged.)

- [ ] **Step 4: Fix the opponent-type label in `TacticoMatchesPage.tsx`'s `MatchRow`**

Change:

```tsx
          {match.opponent_type === "bot" ? "Против бота" : "Против друга"} · {STATUS_LABELS[match.status]}
```

to:

```tsx
          {OPPONENT_TYPE_LABELS[match.opponent_type]} · {STATUS_LABELS[match.status]}
```

Add near the existing `STATUS_LABELS` constant:

```typescript
const OPPONENT_TYPE_LABELS: Record<string, string> = {
  bot: "Против бота",
  friend: "Против друга",
  online: "Против соперника",
};
```

- [ ] **Step 5: Fix the opponent-type label in `TacticoMatchPage.tsx`**

Change:

```tsx
            {match.opponent_type === "bot" ? "Против бота" : "Против друга"} · {match.opponent_name}
```

to:

```tsx
            {OPPONENT_TYPE_LABELS[match.opponent_type]} · {match.opponent_name}
```

Add the same `OPPONENT_TYPE_LABELS` constant used in Step 4 near the top of this file (both files need their own copy — this codebase doesn't currently share small per-page label maps like `STATUS_LABELS` across files, matching the existing convention of each page owning its own copy).

- [ ] **Step 6: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Manual end-to-end verification**

With `docker compose up` running: open two browser sessions (e.g. one normal + one incognito window, both in dev mode as different users with complete Tactico squads already saved). In both, go to `/play/tactico` and tap the new "Играть" button. Confirm: both land on the searching screen; within ~2-4 seconds both transition to the reveal screen showing the *other* player's real nickname/avatar/rating; both auto-advance into the same live match after ~3s; the match plays normally; cancelling before a match is found returns cleanly to `/play/tactico`; letting one session search alone for over 60 seconds shows the timeout screen with a working "Попробовать снова".

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/TacticoSearchPage.tsx frontend/src/pages/TacticoMatchesPage.tsx frontend/src/pages/TacticoMatchPage.tsx frontend/src/App.tsx
git commit -m "Add Tactico matchmaking UI: search/reveal flow, primary Играть button"
```

---

### Task 6: Penalty matchmaking — data model and migration

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/penalty.py`
- Create: `backend/alembic/versions/0044_penalty_matchmaking.py`
- Test: `backend/tests/test_penalty_pvp.py` (append)

**Interfaces:**
- Produces: `PenaltyOpponentType` enum (`friend`, `online`); `PenaltyMatch.opponent_type` column (`server_default='friend'`); `PenaltyQueueEntry` model (`id, user_id, user_card_id, created_at, matched_match_id`) — consumed by Task 7.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_penalty_pvp.py`:

```python
from app.models.enums import PenaltyOpponentType
from app.models.penalty import PenaltyQueueEntry


async def test_penalty_opponent_type_has_friend_and_online():
    assert PenaltyOpponentType.friend == "friend"
    assert PenaltyOpponentType.online == "online"


async def test_existing_penalty_match_defaults_opponent_type_to_friend(client, db_session, bot_token):
    sender = await _register(client, db_session, 861001, bot_token)
    receiver = await _register(client, db_session, 861002, bot_token)
    sender_card = await _grant_card(db_session, sender.id)

    resp = await client.post(
        "/api/v1/games/penalty/challenges", headers=telegram_headers(861001, bot_token),
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    assert resp.status_code == 200
    assert resp.json()["opponent_type"] == "friend"


async def test_penalty_queue_entry_roundtrip(client, db_session, bot_token):
    user = await _register(client, db_session, 861003, bot_token)
    card = await _grant_card(db_session, user.id)

    entry = PenaltyQueueEntry(user_id=user.id, user_card_id=card.id)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)

    assert entry.id is not None
    assert entry.matched_match_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -k "opponent_type or queue_entry" -v`
Expected: FAIL — `ImportError`/`KeyError` (`opponent_type` not on the response, `PenaltyOpponentType`/`PenaltyQueueEntry` don't exist).

- [ ] **Step 3: Add `PenaltyOpponentType` to `backend/app/models/enums.py`**

Add near the existing `TacticoOpponentType`:

```python
class PenaltyOpponentType(str, enum.Enum):
    friend = "friend"
    online = "online"
```

- [ ] **Step 4: Add `opponent_type` and `PenaltyQueueEntry` to `backend/app/models/penalty.py`**

Change the import line:

```python
from app.models.enums import MatchResult, PenaltyMatchStatus
```

to:

```python
from app.models.enums import MatchResult, PenaltyMatchStatus, PenaltyOpponentType
```

Add a new column to `PenaltyMatch` (anywhere among the other plain columns, e.g. right after `opponent_name`):

```python
    opponent_type: Mapped[PenaltyOpponentType] = mapped_column(
        Enum(PenaltyOpponentType, name="penalty_opponent_type_enum"),
        default=PenaltyOpponentType.friend, nullable=False,
    )
```

Add a new class at the end of the file:

```python
class PenaltyQueueEntry(Base):
    """One player currently searching for a Penalty opponent via
    matchmaking. Mirrors TacticoQueueEntry — see that model's docstring for
    how `matched_match_id` gets set (tactico_service.get_search_status's
    pairing algorithm, reused identically in penalty_match_service)."""

    __tablename__ = "penalty_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("penalty_matches.id", ondelete="SET NULL"), nullable=True
    )
```

This file currently imports `from app.models.mixins import utcnow` already (used by `PenaltyMatch.created_at`) — no new import needed for `utcnow`. `DateTime`, `Enum`, `ForeignKey`, `Integer`, `Optional`, `Mapped`, `mapped_column` are all already imported at the top of this file too.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -k "opponent_type or queue_entry" -v`
Expected: 3 passed.

- [ ] **Step 6: Add `opponent_type` to `PenaltyMatchOut` and `_hydrate_match`**

In `backend/app/schemas/penalty_match.py`, add to `PenaltyMatchOut` (alongside the existing `opponent_name: str`):

```python
    opponent_type: PenaltyOpponentType
```

Change the import line:

```python
from app.models.enums import MatchResult, PenaltyMatchStatus
```

to:

```python
from app.models.enums import MatchResult, PenaltyMatchStatus, PenaltyOpponentType
```

In `backend/app/services/penalty_match_service.py`'s `_hydrate_match`, add `opponent_type=match.opponent_type,` to the `PenaltyMatchOut(...)` constructor call (alongside the existing `opponent_name=opponent_name,`).

- [ ] **Step 7: Run tests to verify they still pass**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -v`
Expected: all passed (the earlier `test_existing_penalty_match_defaults_opponent_type_to_friend` test from Step 1 now actually exercises the field end-to-end).

- [ ] **Step 8: Write the migration**

Confirm the actual head first: `docker compose exec backend alembic heads` (should now be `0043` from Task 2).

Create `backend/alembic/versions/0044_penalty_matchmaking.py`:

```python
"""Penalty matchmaking: queue table + opponent type

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

penalty_opponent_type_enum = postgresql.ENUM(
    "friend", "online", name="penalty_opponent_type_enum", create_type=False
)


def upgrade() -> None:
    penalty_opponent_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "penalty_matches",
        sa.Column("opponent_type", penalty_opponent_type_enum, nullable=False, server_default="friend"),
    )

    op.create_table(
        "penalty_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("penalty_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_unique_constraint("uq_penalty_queue_entries_user_id", "penalty_queue_entries", ["user_id"])
    op.create_index("ix_penalty_queue_entries_user_id", "penalty_queue_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_penalty_queue_entries_user_id", table_name="penalty_queue_entries")
    op.drop_table("penalty_queue_entries")
    op.drop_column("penalty_matches", "opponent_type")
    penalty_opponent_type_enum.drop(op.get_bind(), checkfirst=True)
```

(This is a genuinely new enum type — not adding a value to an existing one — so it uses the `postgresql.ENUM(..., create_type=False)` + explicit `.create()`/`.drop()` pattern already established in this codebase's earlier migrations for the same situation, e.g. `0002_tasks_and_minigames.py`, rather than the `ALTER TYPE ... ADD VALUE` pattern Task 2 used for extending the *existing* `TacticoOpponentType`.)

- [ ] **Step 9: Full backend import sanity check**

Run: `docker compose exec backend python -c "from app.main import app"`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/penalty.py backend/app/schemas/penalty_match.py backend/app/services/penalty_match_service.py backend/alembic/versions/0044_penalty_matchmaking.py backend/tests/test_penalty_pvp.py
git commit -m "Add Penalty matchmaking data model: PenaltyQueueEntry, opponent_type"
```

---

### Task 7: Penalty matchmaking — service layer (search, pairing, cancel)

**Files:**
- Modify: `backend/app/services/penalty_match_service.py`
- Test: `backend/tests/test_penalty_pvp.py` (append)

**Interfaces:**
- Consumes: `PenaltyQueueEntry` (Task 6), `_has_active_match`, `_load_owned_card`, `_consume_hourly_slot`, `_ensure_hourly_reset` (all pre-existing in this file), `KICK_TIMEOUT_SECONDS`, `MATCH_TIMEOUT_SECONDS` (pre-existing module constants).
- Produces: `penalty_match_service.start_search(db, user, user_card_id) -> PenaltyQueueEntry`, `penalty_match_service.get_search_status(db, user) -> tuple[str, Optional[int]]`, `penalty_match_service.cancel_search(db, user) -> None`, `penalty_match_service.MATCHMAKING_TIMEOUT_SECONDS: int = 60` — consumed by Task 8's router.

**No existing-conditional fixes needed here** (unlike Task 3's Tactico fixes) — every branch of `PenaltyMatch`'s existing lifecycle code (`_finish_match`, `_hydrate_match`, `_resolve_current_kick`, `_auto_resolve_overdue`) already assumes two real human players unconditionally, with no `bot`-vs-other branching anywhere in this file to accidentally exclude `online` from — confirmed by reading the full file: `_finish_match` always locks and updates both `locked_user`/`locked_opponent`, `_hydrate_match` always computes `kick_deadline`/`match_deadline` the same way regardless of type. Adding `opponent_type` here is purely informational.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_penalty_pvp.py`:

```python
async def test_penalty_start_search_requires_owned_card(client, db_session, bot_token):
    sender = await _register(client, db_session, 862001, bot_token)
    other_owner = await _register(client, db_session, 862002, bot_token)
    someone_elses_card = await _grant_card(db_session, other_owner.id)

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=telegram_headers(862001, bot_token),
        json={"user_card_id": someone_elses_card.id},
    )
    assert resp.status_code == 403


async def test_penalty_start_search_rejects_second_entry(client, db_session, bot_token):
    user = await _register(client, db_session, 862003, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862003, bot_token)

    first = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert second.status_code == 409
    assert "уже ищешь" in second.json()["error"]["message"]


async def test_penalty_two_waiting_players_get_paired(client, db_session, bot_token):
    user_a = await _register(client, db_session, 862004, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    user_b = await _register(client, db_session, 862005, bot_token)
    card_b = await _grant_card(db_session, user_b.id)
    headers_a = telegram_headers(862004, bot_token)
    headers_b = telegram_headers(862005, bot_token)

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})

    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "matched"
    match_id = status_a.json()["match_id"]

    status_b = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_b)
    assert status_b.json()["match_id"] == match_id

    match_resp = await client.get(f"/api/v1/games/penalty/matches/{match_id}", headers=headers_a)
    body = match_resp.json()
    assert body["opponent_type"] == "online"
    assert body["status"] == "in_progress"
    assert body["kick_deadline"] is not None
    assert body["match_deadline"] is not None


async def test_penalty_search_timeout(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 862006, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862006, bot_token)
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id})

    entry = (
        await db_session.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id))
    ).scalar_one()
    entry.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    db_session.add(entry)
    await db_session.commit()

    resp = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers)
    assert resp.json()["status"] == "timeout"


async def test_penalty_pairing_skips_entry_whose_card_was_traded_away(client, db_session, bot_token):
    user_a = await _register(client, db_session, 862007, bot_token)
    card_a = await _grant_card(db_session, user_a.id)
    user_b = await _register(client, db_session, 862008, bot_token)
    card_b = await _grant_card(db_session, user_b.id)
    headers_a = telegram_headers(862007, bot_token)
    headers_b = telegram_headers(862008, bot_token)

    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a.id})
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b.id})

    # Simulate card_b changing hands (e.g. via a trade) while both wait in the queue.
    card_b.owner_id = user_a.id
    db_session.add(card_b)
    await db_session.commit()

    status_a = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers_a)
    assert status_a.json()["status"] == "searching"  # B's stale entry dropped, not a broken match


async def test_penalty_cancel_search(client, db_session, bot_token):
    user = await _register(client, db_session, 862009, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862009, bot_token)
    await client.post("/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id})

    resp = await client.post("/api/v1/games/penalty/matchmaking/cancel", headers=headers)
    assert resp.status_code == 204
    status = await client.get("/api/v1/games/penalty/matchmaking/status", headers=headers)
    assert status.json()["status"] == "not_searching"
```

Add `from sqlalchemy import select` at the top of `backend/tests/test_penalty_pvp.py` if not already imported (check the existing top-of-file imports first — it likely is not, since the file currently has no `select(...)` usage visible in what's been read).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -k "search or matchmaking or pairing" -v`
Expected: FAIL — 404 (routes don't exist yet).

- [ ] **Step 3: Add the matchmaking functions**

Add near the bottom of `backend/app/services/penalty_match_service.py`, after `get_match`:

```python
# ---------------------------------------------------------------------------
# Matchmaking
# ---------------------------------------------------------------------------

MATCHMAKING_TIMEOUT_SECONDS = 60


async def _hourly_slot_available(db: AsyncSession, user_id: int, config) -> bool:
    from app.services.penalty_service import _ensure_hourly_reset

    locked_user = await lock_user_for_update(db, user_id)
    await _ensure_hourly_reset(db, locked_user)
    return locked_user.penalty_hourly_attempts < config.hourly_game_limit


async def start_search(db: AsyncSession, user: User, user_card_id: int) -> PenaltyQueueEntry:
    if await _has_active_match(db, user.id):
        raise ConflictError("У тебя уже есть матч в процессе — заверши его, прежде чем искать нового соперника")
    existing = await db.execute(select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Ты уже ищешь соперника")
    await _load_owned_card(db, user, user_card_id)

    entry = PenaltyQueueEntry(user_id=user.id, user_card_id=user_card_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_search_status(db: AsyncSession, user: User) -> tuple[str, Optional[int]]:
    result = await db.execute(
        select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    my_entry = result.scalar_one_or_none()
    if my_entry is None:
        return "not_searching", None

    if my_entry.matched_match_id is not None:
        await db.commit()
        return "matched", my_entry.matched_match_id

    if datetime.now(timezone.utc) - ensure_aware(my_entry.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS):
        await db.delete(my_entry)
        await db.commit()
        return "timeout", None

    candidate_result = await db.execute(
        select(PenaltyQueueEntry)
        .where(PenaltyQueueEntry.user_id != user.id, PenaltyQueueEntry.matched_match_id.is_(None))
        .order_by(PenaltyQueueEntry.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    candidate = candidate_result.scalar_one_or_none()
    if candidate is None:
        await db.commit()
        return "searching", None

    candidate_user = await db.get(User, candidate.user_id)
    config = await get_config(db)

    async def _card_still_owned(card_id: int, owner_id: int) -> bool:
        card_result = await db.execute(select(UserCard).where(UserCard.id == card_id))
        card = card_result.scalar_one_or_none()
        return card is not None and card.owner_id == owner_id

    stale: list[PenaltyQueueEntry] = []
    if (
        await _has_active_match(db, user.id)
        or not await _card_still_owned(my_entry.user_card_id, user.id)
        or not await _hourly_slot_available(db, user.id, config)
    ):
        stale.append(my_entry)
    if (
        await _has_active_match(db, candidate.user_id)
        or not await _card_still_owned(candidate.user_card_id, candidate.user_id)
        or not await _hourly_slot_available(db, candidate.user_id, config)
    ):
        stale.append(candidate)
    if stale:
        for entry in stale:
            await db.delete(entry)
        await db.commit()
        return ("not_searching" if my_entry in stale else "searching"), None

    locked_user = await _consume_hourly_slot(db, user.id, config)
    locked_candidate = await _consume_hourly_slot(db, candidate.user_id, config)

    now = datetime.now(timezone.utc)
    match = PenaltyMatch(
        user_id=locked_user.id,
        opponent_user_id=locked_candidate.id,
        opponent_name=locked_candidate.full_display_name(),
        user_card_id=my_entry.user_card_id,
        opponent_card_id=candidate.user_card_id,
        opponent_type=PenaltyOpponentType.online,
        status=PenaltyMatchStatus.in_progress,
        server_state={
            "kicks_taken": 0, "kicker": "user", "rounds": [],
            "user_score": 0, "opponent_score": 0,
            "user_pending_zone": None, "opponent_pending_zone": None,
            "kick_deadline": (now + timedelta(seconds=KICK_TIMEOUT_SECONDS)).isoformat(),
            "match_deadline": (now + timedelta(seconds=MATCH_TIMEOUT_SECONDS)).isoformat(),
        },
    )
    db.add(match)
    await db.flush()

    my_entry.matched_match_id = match.id
    candidate.matched_match_id = match.id
    db.add(my_entry)
    db.add(candidate)
    await db.commit()
    return "matched", match.id


async def cancel_search(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Ты не ищешь соперника")
    if entry.matched_match_id is not None:
        raise ConflictError("Соперник уже найден — матч начинается")
    await db.delete(entry)
    await db.commit()
```

Add `from app.models.penalty import PenaltyMatch, PenaltyQueueEntry` (combine with the existing `from app.models.penalty import PenaltyMatch` import line) and `from app.models.enums import MatchResult, NotificationType, PenaltyMatchStatus, PenaltyOpponentType` (combine with the existing enums import line) at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -v`
Expected: all passed.

- [ ] **Step 5: Full backend regression check**

Run: `docker compose exec backend pytest tests/ -q`
Expected: no new failures versus the pre-existing baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/penalty_match_service.py backend/tests/test_penalty_pvp.py
git commit -m "Add Penalty matchmaking service: search, race-safe pairing, cancel"
```

- [ ] **Step 7: Manual concurrency verification against real Postgres**

Same rationale and same synthetic-user approach as Task 3 Step 8 (see that step for why `X-Dev-Mode` can't be used here — it always resolves to one single fixed dev user, and see the Global Constraints note on why this can't be a pytest test). Penalty needs far less seed data than Tactico (one owned card per user, not an 11-card squad), so this script is simpler end-to-end:

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'EOF'
SELECT id FROM players WHERE is_active = true LIMIT 2;
EOF
```

Copy the 2 printed player ids into the seeding step below.

```bash
cat > /tmp/mm_verify_penalty.py <<'PYEOF'
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx

from app.config import get_settings

settings = get_settings()
BOT_TOKEN = settings.telegram_bot_token
BASE = "http://localhost:8000/api/v1"


def make_init_data(telegram_id: int, first_name: str) -> str:
    user = {"id": telegram_id, "first_name": first_name}
    data = {"auth_date": str(int(time.time())), "query_id": "verify", "user": json.dumps(user, separators=(",", ":"))}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


async def main():
    headers_a = {"X-Telegram-Init-Data": make_init_data(910002001, "VerifyA")}
    headers_b = {"X-Telegram-Init-Data": make_init_data(910002002, "VerifyB")}
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as client:
        session_a = (await client.post("/auth/session", headers=headers_a)).json()
        session_b = (await client.post("/auth/session", headers=headers_b)).json()
        print("user ids:", session_a["id"], session_b["id"])
        print("Now run the SQL below (with these two user ids) to grant each a card, then press Enter.")
        input()

        card_a = int(input("card id for user A: "))
        card_b = int(input("card id for user B: "))

        search_a, search_b = await asyncio.gather(
            client.post("/games/penalty/matchmaking/search", headers=headers_a, json={"user_card_id": card_a}),
            client.post("/games/penalty/matchmaking/search", headers=headers_b, json={"user_card_id": card_b}),
        )
        print("search A:", search_a.status_code, search_a.text[:300])
        print("search B:", search_b.status_code, search_b.text[:300])

        status_a, status_b = await asyncio.gather(
            client.get("/games/penalty/matchmaking/status", headers=headers_a),
            client.get("/games/penalty/matchmaking/status", headers=headers_b),
        )
        print("status A:", status_a.json())
        print("status B:", status_b.json())
        assert status_a.json()["status"] == "matched", "user A was not paired"
        assert status_a.json()["match_id"] == status_b.json()["match_id"], "paired to two different matches!"
        print("OK: both paired to the same match", status_a.json()["match_id"])


asyncio.run(main())
PYEOF
docker compose cp /tmp/mm_verify_penalty.py backend:/app/mm_verify_penalty.py
docker compose exec backend python mm_verify_penalty.py
```

When the script pauses at the first `input()`, in a second terminal grant both users a card (replace `<user_a_id>`/`<user_b_id>` with the printed ids and the 2 player ids from the query above):

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<EOF
INSERT INTO user_cards (owner_id, player_id, source, serial_number, acquired_at)
  VALUES (<user_a_id>, <player_id_1>, 'seed', 1, now())
  RETURNING id;
EOF
```

then the same for `<user_b_id>`/`<player_id_2>`. Return to the script, press Enter, then type each returned card id when prompted.

Confirm the script prints `OK: both paired to the same match <id>`. Then independently verify via psql:

```bash
docker compose exec -T postgres sh -c 'psql -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'EOF'
SELECT id, user_id, opponent_user_id, opponent_type, status FROM penalty_matches ORDER BY id DESC LIMIT 3;
SELECT id, user_id, matched_match_id FROM penalty_queue_entries ORDER BY id DESC LIMIT 3;
EOF
```

Confirm exactly one new `penalty_matches` row with `opponent_type = 'online'`, and both queue entries pointing at the same `matched_match_id`. Repeat 5-10 times with fresh synthetic telegram ids — a race window this narrow may not reproduce every single run. Clean up the synthetic test users afterward if this was run against a shared dev database.

---

### Task 8: Penalty matchmaking — router, schema, frontend API client

**Files:**
- Modify: `backend/app/schemas/penalty_match.py`
- Modify: `backend/app/routers/penalty_matches.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/penalty.ts`
- Test: `backend/tests/test_penalty_pvp.py` (append)

**Interfaces:**
- Consumes: `penalty_match_service.start_search`/`get_search_status`/`cancel_search` (Task 7).
- Produces: `POST /api/v1/games/penalty/matchmaking/search`, `GET /api/v1/games/penalty/matchmaking/status`, `POST /api/v1/games/penalty/matchmaking/cancel` — consumed by Task 9's frontend page. TS `PenaltySearchStatus` type, `startPenaltySearch()`/`fetchPenaltySearchStatus()`/`cancelPenaltySearch()` client functions.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_penalty_pvp.py`:

```python
async def test_penalty_search_endpoint_response_shape(client, db_session, bot_token):
    user = await _register(client, db_session, 862010, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(862010, bot_token)

    resp = await client.post(
        "/api/v1/games/penalty/matchmaking/search", headers=headers, json={"user_card_id": card.id}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "searching"
    assert body["match_id"] is None
    assert body["created_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -k search_endpoint_response_shape -v`
Expected: FAIL — 404.

- [ ] **Step 3: Add schemas to `backend/app/schemas/penalty_match.py`**

Add at the end of the file:

```python
class PenaltySearchRequest(BaseModel):
    user_card_id: int


class PenaltySearchStatusOut(BaseModel):
    status: Literal["not_searching", "searching", "matched", "timeout"]
    match_id: Optional[int] = None
    created_at: Optional[datetime] = None
```

- [ ] **Step 4: Add the three endpoints to `backend/app/routers/penalty_matches.py`**

Add `PenaltySearchRequest, PenaltySearchStatusOut` to the existing `from app.schemas.penalty_match import (...)` block, then add at the end of the file:

```python
@router.post("/matchmaking/search", response_model=PenaltySearchStatusOut)
async def start_search(
    payload: PenaltySearchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"penalty_search:{user.id}", max_calls=10, window_seconds=60)
    entry = await penalty_match_service.start_search(db, user, payload.user_card_id)
    return PenaltySearchStatusOut(status="searching", match_id=None, created_at=entry.created_at)


@router.get("/matchmaking/status", response_model=PenaltySearchStatusOut)
async def get_search_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    status, match_id = await penalty_match_service.get_search_status(db, user)
    return PenaltySearchStatusOut(status=status, match_id=match_id, created_at=None)


@router.post("/matchmaking/cancel", status_code=204)
async def cancel_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await penalty_match_service.cancel_search(db, user)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_penalty_pvp.py -v`
Expected: all passed.

- [ ] **Step 6: Add the frontend TS type**

In `frontend/src/types/index.ts`, add near the `PenaltyMatch` interface:

```typescript
export type PenaltyOpponentType = "friend" | "online";

export interface PenaltySearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
  created_at: string | null;
}
```

Add `opponent_type: PenaltyOpponentType;` to the existing `PenaltyMatch` interface (alongside the existing `opponent_name: string;`).

- [ ] **Step 7: Add the frontend API client functions**

Add to `frontend/src/api/penalty.ts`:

```typescript
export async function startPenaltySearch(userCardId: number): Promise<PenaltySearchStatus> {
  const { data } = await api.post<PenaltySearchStatus>("/games/penalty/matchmaking/search", {
    user_card_id: userCardId,
  });
  return data;
}

export async function fetchPenaltySearchStatus(): Promise<PenaltySearchStatus> {
  const { data } = await api.get<PenaltySearchStatus>("/games/penalty/matchmaking/status");
  return data;
}

export async function cancelPenaltySearch(): Promise<void> {
  await api.post("/games/penalty/matchmaking/cancel");
}
```

Add `PenaltySearchStatus` to the existing `import type { PenaltyDirection, PenaltyMatch } from "@/types";` line.

- [ ] **Step 8: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/penalty_match.py backend/app/routers/penalty_matches.py backend/tests/test_penalty_pvp.py frontend/src/types/index.ts frontend/src/api/penalty.ts
git commit -m "Add Penalty matchmaking endpoints and frontend API client"
```

---

### Task 9: Penalty matchmaking — frontend UI

**Files:**
- Create: `frontend/src/pages/PenaltySearchPage.tsx`
- Modify: `frontend/src/pages/PenaltyMatchesPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `startPenaltySearch`/`fetchPenaltySearchStatus`/`cancelPenaltySearch` (Task 8), `fetchPublicProfile` (pre-existing), `ProfilePublic.penalty_rating` (Task 1), `fetchCollection`/`CardPickerModal` (both pre-existing, already used by this same page's friend-challenge flow).
- Produces: `/play/penalty/matches/search` route, reachable end-to-end from the "Играть" button through to a live match.

- [ ] **Step 1: Create `frontend/src/pages/PenaltySearchPage.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cancelPenaltySearch, fetchPenaltyMatch, fetchPenaltySearchStatus, startPenaltySearch } from "@/api/penalty";
import { fetchPublicProfile } from "@/api/profile";
import { UserBadge } from "@/components/common/UserBadge";
import { IconTarget, IconUsers } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { ProfilePublic } from "@/types";

const REVEAL_PAUSE_MS = 3000;

export default function PenaltySearchPage({ userCardId }: { userCardId: number }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"starting" | "searching" | "timeout" | "reveal" | "error">("starting");
  const [error, setError] = useState<string | null>(null);
  const [opponent, setOpponent] = useState<ProfilePublic | null>(null);
  const hasStartedRef = useRef(false);

  useEffect(() => {
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;
    startPenaltySearch(userCardId)
      .then(() => setPhase("searching"))
      .catch((err) => {
        setPhase("error");
        setError(formatGameError(err, "Не удалось начать поиск соперника"));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: status } = useQuery({
    queryKey: ["penalty-search-status"],
    queryFn: fetchPenaltySearchStatus,
    enabled: phase === "searching",
    refetchInterval: () => (phase === "searching" ? 2000 : false),
  });

  useEffect(() => {
    if (!status) return;
    if (status.status === "timeout") {
      setPhase("timeout");
    } else if (status.status === "matched" && status.match_id) {
      revealThenEnter(status.match_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.match_id]);

  const revealThenEnter = async (matchId: number) => {
    try {
      const match = await fetchPenaltyMatch(matchId);
      if (match.opponent_user_id) {
        setOpponent(await fetchPublicProfile(match.opponent_user_id));
      }
      setPhase("reveal");
      setTimeout(() => navigate(`/play/penalty/matches/${matchId}`), REVEAL_PAUSE_MS);
    } catch {
      navigate(`/play/penalty/matches/${matchId}`);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelPenaltySearch();
    } catch {
      // Ignore — if this failed because pairing already happened, the
      // player is about to be redirected into the match anyway.
    }
    navigate("/play/penalty/matches");
  };

  if (phase === "error") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={() => navigate("/play/penalty/matches")}
          className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
        >
          Назад
        </button>
      </div>
    );
  }

  if (phase === "timeout") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <IconUsers size={40} className="text-ink-mist-dim" />
        <p className="font-display text-lg font-bold text-ink-chalk">Соперник не найден</p>
        <p className="text-sm text-ink-mist">Попробуй ещё раз</p>
        <div className="flex w-full gap-2">
          <button
            onClick={() => navigate("/play/penalty/matches")}
            className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95"
          >
            Назад
          </button>
          <button
            onClick={() => { hasStartedRef.current = false; setPhase("starting"); }}
            className="flex-1 rounded-2xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95"
          >
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  if (phase === "reveal") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-accent-lime">Соперник найден!</p>
        {opponent ? (
          <>
            <img
              src={opponent.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt="avatar"
              className="h-20 w-20 rounded-full ring-2 ring-accent-lime object-cover"
            />
            <p className="flex items-center gap-1.5 font-display text-xl font-bold text-ink-chalk">
              {opponent.username ?? opponent.first_name ?? "Игрок"}
              <UserBadge badge={opponent.active_badge} />
            </p>
            <p className="text-sm text-ink-mist">Рейтинг Пенальти: {opponent.penalty_rating}</p>
          </>
        ) : (
          <p className="text-sm text-ink-mist">Загрузка...</p>
        )}
        <p className="animate-pulse text-xs text-ink-mist-dim">Матч начинается...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <IconTarget size={40} className="animate-pulse text-accent-lime" />
      <p className="font-display text-lg font-bold text-ink-chalk">Ищем соперника...</p>
      <button
        onClick={handleCancel}
        className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
      >
        Отменить
      </button>
    </div>
  );
}
```

Note the `userCardId` prop: unlike Tactico (whose squad is already saved server-side, nothing to pick), Penalty's search needs a card chosen *before* this page's own `POST .../search` call fires on mount — that choice happens on `PenaltyMatchesPage` via the existing `CardPickerModal`, one step before navigating here (see Step 3).

- [ ] **Step 2: Register the route in `frontend/src/App.tsx`**

Add the import `import PenaltySearchPage from "@/pages/PenaltySearchPage";`. This route needs the picked card id, passed via router state rather than a URL param (matching how `PackOpenPage` already receives an optional prefetched result via `location.state`) — add inside the existing `<Route element={<AppLayout />}>` block, alongside `/play/penalty/matches/:matchId`:

```tsx
        <Route path="/play/penalty/matches/search" element={<PenaltySearchRoute />} />
```

Add this small wrapper component in the same file (near the other route-level components, or inline right above the `<Routes>` block), since `PenaltySearchPage` needs its `userCardId` prop pulled out of navigation state:

```tsx
function PenaltySearchRoute() {
  const location = useLocation();
  const userCardId = (location.state as { userCardId?: number } | null)?.userCardId;
  if (!userCardId) return <Navigate to="/play/penalty/matches" replace />;
  return <PenaltySearchPage userCardId={userCardId} />;
}
```

Add `Navigate` and `useLocation` to the existing `react-router-dom` import line in `App.tsx` if not already imported (check first — `useLocation` is likely already imported for other routes; `Navigate` may not be).

- [ ] **Step 3: Add the primary "Играть" button to `PenaltyMatchesPage.tsx`**

Add a new state flag and a second `CardPickerModal` usage for the matchmaking flow (separate from the existing `pickingOpponent` one, since matchmaking never has a specific opponent to name in the modal title):

```tsx
  const [pickingForSearch, setPickingForSearch] = useState(false);
```

Replace the existing single-button `else` branch:

```tsx
      ) : (
        <button
          onClick={() => setChallengeSheetOpen(true)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight py-4 text-sm font-bold text-bg-base ring-2 ring-accent-cyan/40 active:scale-95"
        >
          <IconUsers size={17} />
          Вызвать друга
        </button>
      )}
```

with:

```tsx
      ) : (
        <>
          <button
            onClick={() => setPickingForSearch(true)}
            className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-5 text-base font-bold text-bg-base ring-2 ring-accent/40 active:scale-95"
          >
            <IconPlay size={20} />
            Играть
          </button>
          <button
            onClick={() => setChallengeSheetOpen(true)}
            className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconUsers size={14} />
            Вызвать друга
          </button>
        </>
      )}
```

Add `IconPlay` to the existing `import { IconFlagCheckered, IconUsers } from "@/components/icons";` line.

Add the new card-picker modal instance right after the existing `{pickingOpponent && (...)}` block:

```tsx
      {pickingForSearch && (
        <CardPickerModal
          open
          title="Выбери карточку для матча"
          cards={collection?.items ?? []}
          onSelect={(card) => navigate("/play/penalty/matches/search", { state: { userCardId: card.id } })}
          onClose={() => setPickingForSearch(false)}
        />
      )}
```

This reuses the same `collection` query already declared in this file for `pickingOpponent` — change its `enabled` condition from `enabled: pickingOpponent !== null` to `enabled: pickingOpponent !== null || pickingForSearch`, since it now needs to fetch for either picker.

- [ ] **Step 4: Add an opponent-type label to `PenaltyMatchesPage.tsx`'s `MatchRow`**

Change:

```tsx
        <p className="mt-0.5 text-[11px] text-ink-mist">{STATUS_LABELS[match.status]}</p>
```

to:

```tsx
        <p className="mt-0.5 text-[11px] text-ink-mist">
          {match.opponent_type === "online" ? "Против соперника" : "Против друга"} · {STATUS_LABELS[match.status]}
        </p>
```

- [ ] **Step 5: Typecheck**

Run: `docker compose exec frontend npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Manual end-to-end verification**

With `docker compose up` running: open two browser sessions (e.g. one normal + one incognito window, both in dev mode as different users, each owning at least one card). In both, go to `/play/penalty/matches`, tap the new "Играть" button, pick a card in the modal that opens. Confirm: both land on the searching screen; within ~2-4 seconds both transition to the reveal screen showing the *other* player's real nickname/avatar/`penalty_rating`; both auto-advance into the same live match after ~3s; the match plays normally (kicks resolve, score updates); cancelling before a match is found returns cleanly to `/play/penalty/matches`; letting one session search alone for over 60 seconds shows the timeout screen with a working "Попробовать снова".

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/PenaltySearchPage.tsx frontend/src/pages/PenaltyMatchesPage.tsx frontend/src/App.tsx
git commit -m "Add Penalty matchmaking UI: search/reveal flow, primary Играть button"
```
