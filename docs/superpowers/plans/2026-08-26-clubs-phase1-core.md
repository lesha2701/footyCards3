# Clubs — Phase 1: Core (data model, membership, roles, invites) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational layer of the Clubs (clan) feature: club creation, browsing/search, membership, the captain/assistant/member role hierarchy, closed-club join requests, and permanent invite links. This is Phase 1 of a multi-phase build — it deliberately excludes club budget/economy, squads, and tournaments, which are separate follow-up plans that build on top of what's implemented here.

**Architecture:** Standard FastAPI service/router/schema layering matching this codebase's existing feature modules (closest precedents: `league_service.py`/`routers/leagues.py`/`routers/admin_leagues.py` for CRUD+role shape, `tactico_service.py` for row-locking a shared resource under concurrent access, `task_service.py`'s referral-adjacent notification calls). A club is capped at 11 members with three roles (captain, ≤2 assistants, members). Invite links reuse the exact same 3-hop deep-link mechanism already used for referrals (bot `/start` payload → `?joinClub=` query param on the Mini App URL → an authenticated API call once the app is open), except — unlike referrals, which are registration-time-only — invite links must work for already-registered users opening the link at any time, so consumption is a normal authenticated endpoint call, not something baked into `/auth/session`.

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, PostgreSQL, Pydantic v2 (backend); React 18, TypeScript, Vite, Zustand, TanStack Query, Tailwind, React Router (frontend); aiogram 3 (bot, one new `/start` payload branch only in this phase).

**Spec:** [docs/superpowers/specs/2026-08-26-clubs-design.md](../specs/2026-08-26-clubs-design.md) — this plan implements the "Data model" (Club/ClubMember/ClubJoinRequest slice only), "Roles & permissions", and "Club lifecycle" sections. `budget`/`cups_count`/`stars_count`/`last_tournament_applied_at` and every `ClubCard`/squad/tournament table are deliberately deferred to Phase 2 (economy & squad) and Phase 3 (tournaments) — adding them now would be unused schema this plan's own tests and endpoints never touch.

## Global Constraints

- Max club size: **11 members** (enforced in service code via a row-locked count-then-insert, not a DB constraint — mirrors how Tactico enforces its 11-card squad size).
- Max **2 assistants** per club, enforced the same way.
- A user can be in **at most one club** — enforced at the DB level via a `UNIQUE` constraint on `ClubMember.user_id`.
- Every balance-mutating or capacity-checked operation must row-lock the `Club` row first (`SELECT ... FOR UPDATE`) before counting members or inserting — race-sensitive, per CLAUDE.md's "use row locking for race-sensitive operations."
- Club creation costs `GameConfig.club_creation_cost_coins` (new field, default `500`), debited via the existing `wallet_service.debit_coins` (which already raises `InsufficientBalanceError` on an insufficient balance — do not re-implement that check).
- All player-facing error messages in Russian, matching this feature area's dominant existing convention (e.g. `task_service.py`'s `"Похоже, ты ещё не подписан на канал"`).
- Alembic revision `0056`, `down_revision = "0055"`.
- Never hardcode the creation cost or any other economy number — always read it from `game_config_service.get_config(db)`.

---

### Task 1: Enums, GameConfig field, migration groundwork

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/game_config.py`
- Test: `backend/tests/test_clubs.py` (created here, extended by later tasks)

**Interfaces:**
- Produces: `ClubRole` (`captain`/`assistant`/`member`), `ClubType` (`open`/`closed`), `ClubJoinRequestStatus` (`pending`/`accepted`/`rejected`), `ClubLogoShape` (8 values), and six new `NotificationType` members — all consumed by every later task in this plan.

- [ ] **Step 1: Add the new enums**

In `backend/app/models/enums.py`, add these new classes (anywhere alongside the other small enums, e.g. right after `GiftKind`):

```python
class ClubRole(str, enum.Enum):
    captain = "captain"
    assistant = "assistant"
    member = "member"


class ClubType(str, enum.Enum):
    open = "open"
    closed = "closed"


class ClubJoinRequestStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class ClubLogoShape(str, enum.Enum):
    shield = "shield"
    circle = "circle"
    hexagon = "hexagon"
    star = "star"
    diamond = "diamond"
    banner = "banner"
    crest = "crest"
    chevron = "chevron"
```

- [ ] **Step 2: Add the new `NotificationType` members**

In the same file, find `class NotificationType(str, enum.Enum):` and add these six lines right after the existing `league_promoted = "league_promoted"`:

```python
    club_join_request_received = "club_join_request_received"
    club_join_request_accepted = "club_join_request_accepted"
    club_join_request_rejected = "club_join_request_rejected"
    club_role_changed = "club_role_changed"
    club_kicked = "club_kicked"
    club_captain_transferred = "club_captain_transferred"
```

- [ ] **Step 3: Add the `club_creation_cost_coins` field to `GameConfig`**

In `backend/app/models/game_config.py`, add this line inside the `GameConfig` class (anywhere among the other `Integer` fields is fine, e.g. right after `id`):

```python
    club_creation_cost_coins: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
```

- [ ] **Step 4: Sanity-check the backend still imports**

Run: `docker compose exec -T backend python -c "from app.main import app; print('ok')"`
Expected: `ok`, no traceback.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/game_config.py
git commit -m "Add Club-related enums and GameConfig.club_creation_cost_coins"
```

---

### Task 2: `Club`/`ClubMember`/`ClubJoinRequest` models + migration

**Files:**
- Create: `backend/app/models/club.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0056_clubs_core.py`

**Interfaces:**
- Consumes: `ClubRole`, `ClubType`, `ClubJoinRequestStatus`, `ClubLogoShape` from Task 1.
- Produces: `Club(id, name, description, club_type, logo_shape, logo_color, captain_id, invite_code, founded_at)`, `ClubMember(id, club_id, user_id, role, joined_at)`, `ClubJoinRequest(id, club_id, user_id, status, created_at)` — every later backend task imports these three classes from `app.models.club`.

- [ ] **Step 1: Write the models**

Create `backend/app/models/club.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ClubJoinRequestStatus, ClubLogoShape, ClubRole, ClubType
from app.models.mixins import utcnow


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    club_type: Mapped[ClubType] = mapped_column(Enum(ClubType, name="club_type_enum"), nullable=False)
    logo_shape: Mapped[ClubLogoShape] = mapped_column(
        Enum(ClubLogoShape, name="club_logo_shape_enum"), nullable=False
    )
    # Hex color string, e.g. "#3B82F6" — validated by ClubCreate/ClubUpdate schemas, not here.
    logo_color: Mapped[str] = mapped_column(String(16), nullable=False)
    captain_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Permanent, unique deep-link token — see club_service.join_by_invite.
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    founded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubMember(Base):
    __tablename__ = "club_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    # unique=True is what enforces "a user is in at most one club" at the DB level.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    role: Mapped[ClubRole] = mapped_column(Enum(ClubRole, name="club_role_enum"), default=ClubRole.member, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubJoinRequest(Base):
    __tablename__ = "club_join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ClubJoinRequestStatus] = mapped_column(
        Enum(ClubJoinRequestStatus, name="club_join_request_status_enum"),
        default=ClubJoinRequestStatus.pending, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        # Only one *pending* request per (club, user) — re-requesting after a
        # rejection is allowed, this just stops a duplicate pending row.
        Index(
            "uq_club_join_request_pending", "club_id", "user_id", unique=True,
            postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
    )
```

- [ ] **Step 2: Register the new models**

In `backend/app/models/__init__.py`, add the import and `__all__` entries alongside the existing ones (follow the file's exact existing pattern — e.g. next to the `DailyReward` import):

```python
from app.models.club import Club, ClubJoinRequest, ClubMember
```

and add `"Club"`, `"ClubJoinRequest"`, `"ClubMember"` to the `__all__` list.

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0056_clubs_core.py`:

```python
"""Clubs core: Club, ClubMember, ClubJoinRequest + club_creation_cost_coins

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("club_creation_cost_coins", sa.Integer(), nullable=False, server_default="500"))

    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("club_type", sa.Enum("open", "closed", name="club_type_enum"), nullable=False),
        sa.Column(
            "logo_shape",
            sa.Enum("shield", "circle", "hexagon", "star", "diamond", "banner", "crest", "chevron", name="club_logo_shape_enum"),
            nullable=False,
        ),
        sa.Column("logo_color", sa.String(length=16), nullable=False),
        sa.Column("captain_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invite_code", sa.String(length=16), nullable=False, unique=True),
        sa.Column("founded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clubs_invite_code", "clubs", ["invite_code"])

    op.create_table(
        "club_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("role", sa.Enum("captain", "assistant", "member", name="club_role_enum"), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_members_club_id", "club_members", ["club_id"])

    op.create_table(
        "club_join_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status", sa.Enum("pending", "accepted", "rejected", name="club_join_request_status_enum"),
            nullable=False, server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_join_requests_club_id", "club_join_requests", ["club_id"])
    op.create_index("ix_club_join_requests_user_id", "club_join_requests", ["user_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_club_join_request_pending ON club_join_requests (club_id, user_id) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.drop_index("uq_club_join_request_pending", table_name="club_join_requests")
    op.drop_table("club_join_requests")
    op.drop_table("club_members")
    op.drop_index("ix_clubs_invite_code", table_name="clubs")
    op.drop_table("clubs")
    op.drop_column("game_config", "club_creation_cost_coins")
    # Matches the drop idiom already established in 0012_card_arena_interactive.py
    # for a handwritten (non-autogenerated) enum-backed migration.
    bind = op.get_bind()
    sa.Enum(name="club_join_request_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="club_role_enum").drop(bind, checkfirst=True)
    sa.Enum(name="club_logo_shape_enum").drop(bind, checkfirst=True)
    sa.Enum(name="club_type_enum").drop(bind, checkfirst=True)
```

- [ ] **Step 4: Apply the migration against the real dev Postgres and verify**

```bash
docker compose exec -T backend alembic upgrade head
```
Expected: `Running upgrade 0055 -> 0056, Clubs core...` with no errors. Then:
```bash
docker compose exec -T postgres psql -U postgres -d footycards -c "\d clubs" -c "\d club_members" -c "\d club_join_requests"
```
Confirm all columns/constraints/indexes exist as written above.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/club.py backend/app/models/__init__.py backend/alembic/versions/0056_clubs_core.py
git commit -m "Add Club/ClubMember/ClubJoinRequest models and migration"
```

---

### Task 3: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/club.py`

**Interfaces:**
- Consumes: `Club`, `ClubMember`, `ClubJoinRequest` (Task 2); `ClubRole`, `ClubType`, `ClubLogoShape` (Task 1).
- Produces: `ClubCreate`, `ClubUpdate`, `ClubSummaryOut`, `ClubMemberOut`, `ClubDetailOut`, `ClubJoinRequestOut`, `JoinByInviteIn`, `TransferCaptainIn` — consumed by Task 4/5's router.

- [ ] **Step 1: Write the schemas**

Create `backend/app/schemas/club.py`:

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClubJoinRequestStatus, ClubLogoShape, ClubRole, ClubType


class ClubCreate(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=512)
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str = Field(min_length=4, max_length=16)


class ClubUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=512)
    logo_shape: Optional[ClubLogoShape] = None
    logo_color: Optional[str] = Field(default=None, min_length=4, max_length=16)


class ClubMemberOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    role: ClubRole
    joined_at: datetime


class ClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    member_count: int


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
    members: list[ClubMemberOut]
    # Only populated when the requester is a member — never leak an
    # invite code to an outsider browsing the club list.
    invite_code: Optional[str] = None
    my_role: Optional[ClubRole] = None


class ClubJoinRequestOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    status: ClubJoinRequestStatus


class JoinByInviteIn(BaseModel):
    invite_code: str


class TransferCaptainIn(BaseModel):
    user_id: int
```

Note: `ConfigDict(from_attributes=True)` is deliberately **not** used on `ClubMemberOut`/`ClubJoinRequestOut`/`ClubDetailOut` — their `username`/`first_name`/`avatar_url` fields live on the joined `User` row, not the `ClubMember`/`ClubJoinRequest` ORM object itself, so Task 4/5's service functions construct these as plain dicts/kwargs from an explicit join query rather than `model_validate(orm_obj)`. `ConfigDict(from_attributes=True)` isn't needed as a result — don't add it back in a later task without also flattening the query.

- [ ] **Step 2: Sanity-check imports**

Run: `docker compose exec -T backend python -c "from app.schemas.club import ClubCreate, ClubDetailOut; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/club.py
git commit -m "Add Club Pydantic schemas"
```

---

### Task 4: Club creation, browsing, and detail (service + router + tests)

**Files:**
- Create: `backend/app/services/club_service.py`
- Create: `backend/app/routers/clubs.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_clubs.py`

**Interfaces:**
- Consumes: `Club`/`ClubMember`/`ClubJoinRequest` (Task 2), schemas (Task 3), `wallet_service.debit_coins`/`lock_user_for_update`, `game_config_service.get_config`.
- Produces: `create_club`, `list_clubs`, `get_my_club_detail`, `get_club_detail`, `_lock_club` (a shared row-lock helper Task 5 also imports), `_club_to_summary`/`_club_to_detail` (internal DTO builders) — routes `POST /clubs`, `GET /clubs`, `GET /clubs/me`, `GET /clubs/{club_id}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_clubs.py`:

```python
import secrets

from sqlalchemy import select

from app.models.club import Club, ClubMember
from app.models.enums import ClubRole, ClubType, ClubLogoShape
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_create_club_debits_cost_and_makes_creator_captain(client, db_session, bot_token):
    user = await _register(client, db_session, 820001, bot_token)
    headers = telegram_headers(820001, bot_token)

    resp = await client.post(
        "/api/v1/clubs",
        headers=headers,
        json={"name": "Ночные волки", "description": "test", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["captain_id"] == user.id
    assert body["my_role"] == "captain"
    assert body["member_count"] == 1
    assert body["invite_code"]

    await db_session.refresh(user)
    assert user.balance == 500 - 500  # starting_balance (500 in test settings) - default club_creation_cost_coins (500)


async def test_create_club_rejects_user_already_in_a_club(client, db_session, bot_token):
    await _register(client, db_session, 820002, bot_token)
    headers = telegram_headers(820002, bot_token)
    payload = {"name": "Клуб раз", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"}
    first = await client.post("/api/v1/clubs", headers=headers, json=payload)
    assert first.status_code == 200

    payload2 = {"name": "Клуб два", "club_type": "open", "logo_shape": "circle", "logo_color": "#00FF00"}
    second = await client.post("/api/v1/clubs", headers=headers, json=payload2)
    assert second.status_code == 409


async def test_create_club_fails_on_insufficient_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 820003, bot_token)
    user.balance = 10
    db_session.add(user)
    await db_session.commit()
    headers = telegram_headers(820003, bot_token)

    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": "Бедный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 400  # InsufficientBalanceError maps to 400 (core/exceptions.py)


async def test_list_clubs_filters_by_search(client, db_session, bot_token):
    await _register(client, db_session, 820004, bot_token)
    await client.post(
        "/api/v1/clubs", headers=telegram_headers(820004, bot_token),
        json={"name": "Красные дьяволы", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    await _register(client, db_session, 820005, bot_token)
    await client.post(
        "/api/v1/clubs", headers=telegram_headers(820005, bot_token),
        json={"name": "Синие орлы", "club_type": "closed", "logo_shape": "circle", "logo_color": "#0000FF"},
    )

    resp = await client.get("/api/v1/clubs", params={"search": "дьявол"}, headers=telegram_headers(820004, bot_token))
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert names == ["Красные дьяволы"]


async def test_get_my_club_404_when_not_in_a_club(client, db_session, bot_token):
    await _register(client, db_session, 820006, bot_token)
    resp = await client.get("/api/v1/clubs/me", headers=telegram_headers(820006, bot_token))
    assert resp.status_code == 404


async def test_get_club_detail_hides_invite_code_from_non_members(client, db_session, bot_token):
    await _register(client, db_session, 820007, bot_token)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820007, bot_token),
        json={"name": "Скрытый клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    club_id = create_resp.json()["id"]

    await _register(client, db_session, 820008, bot_token)
    outsider_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820008, bot_token))
    assert outsider_resp.status_code == 200
    assert outsider_resp.json()["invite_code"] is None
    assert outsider_resp.json()["my_role"] is None

    member_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820007, bot_token))
    assert member_resp.json()["invite_code"]
    assert member_resp.json()["my_role"] == "captain"
```

- [ ] **Step 2: Run to verify failure**

Run: `docker compose exec -T backend pytest tests/test_clubs.py -v`
Expected: collection error or all `FAIL` (route `/api/v1/clubs` doesn't exist yet).

- [ ] **Step 3: Implement `club_service.py`**

Create `backend/app/services/club_service.py`:

```python
import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.club import Club, ClubJoinRequest, ClubMember
from app.models.enums import ClubRole, ClubType, TransactionType
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubMemberOut, ClubSummaryOut, ClubUpdate
from app.services.game_config_service import get_config
from app.services.wallet_service import debit_coins, lock_user_for_update

MAX_MEMBERS = 11
MAX_ASSISTANTS = 2


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(6)[:8]


async def _lock_club(db: AsyncSession, club_id: int) -> Club:
    result = await db.execute(select(Club).where(Club.id == club_id).with_for_update())
    club = result.scalar_one_or_none()
    if club is None:
        raise NotFoundError("Клуб не найден")
    return club


async def _member_count(db: AsyncSession, club_id: int) -> int:
    result = await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))
    return result.scalar_one()


async def _get_membership(db: AsyncSession, user_id: int) -> Optional[ClubMember]:
    result = await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))
    return result.scalar_one_or_none()


async def _require_membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = await _get_membership(db, user_id)
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


def _require_manager(membership: ClubMember) -> None:
    if membership.role not in (ClubRole.captain, ClubRole.assistant):
        raise ForbiddenError("Только капитан или ассистент может это делать")


async def _members_with_users(db: AsyncSession, club_id: int) -> list[ClubMemberOut]:
    rows = (
        await db.execute(
            select(ClubMember, User)
            .join(User, User.id == ClubMember.user_id)
            .where(ClubMember.club_id == club_id)
            .order_by(ClubMember.joined_at)
        )
    ).all()
    return [
        ClubMemberOut(
            user_id=u.id, username=u.username, first_name=u.first_name, avatar_url=u.avatar_url,
            role=m.role, joined_at=m.joined_at,
        )
        for m, u in rows
    ]


async def _club_to_detail(db: AsyncSession, club: Club, requester_user_id: Optional[int]) -> ClubDetailOut:
    members = await _members_with_users(db, club.id)
    my_membership = next((m for m in members if m.user_id == requester_user_id), None)
    is_member = my_membership is not None
    return ClubDetailOut(
        id=club.id, name=club.name, description=club.description, club_type=club.club_type,
        logo_shape=club.logo_shape, logo_color=club.logo_color, captain_id=club.captain_id,
        founded_at=club.founded_at, member_count=len(members), members=members,
        invite_code=club.invite_code if is_member else None,
        my_role=my_membership.role if my_membership else None,
    )


async def create_club(db: AsyncSession, user: User, payload: ClubCreate) -> ClubDetailOut:
    existing = await _get_membership(db, user.id)
    if existing is not None:
        raise ConflictError("Ты уже состоишь в клубе")

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await debit_coins(
        db, locked_user, config.club_creation_cost_coins, TransactionType.admin_adjustment,
        f"Создание клуба «{payload.name}»",
    )

    club = Club(
        name=payload.name, description=payload.description, club_type=payload.club_type,
        logo_shape=payload.logo_shape, logo_color=payload.logo_color, captain_id=locked_user.id,
        invite_code=_generate_invite_code(),
    )
    db.add(club)
    await db.flush()

    db.add(ClubMember(club_id=club.id, user_id=locked_user.id, role=ClubRole.captain))
    await db.flush()

    await db.commit()
    await db.refresh(club)
    return await _club_to_detail(db, club, requester_user_id=locked_user.id)


async def list_clubs(db: AsyncSession, search: Optional[str]) -> list[ClubSummaryOut]:
    member_count_subq = (
        select(ClubMember.club_id, func.count(ClubMember.id).label("cnt"))
        .group_by(ClubMember.club_id)
        .subquery()
    )
    query = (
        select(Club, func.coalesce(member_count_subq.c.cnt, 0))
        .outerjoin(member_count_subq, member_count_subq.c.club_id == Club.id)
        .order_by(func.coalesce(member_count_subq.c.cnt, 0).desc(), Club.founded_at.desc())
        .limit(100)
    )
    if search:
        query = query.where(Club.name.ilike(f"%{search}%"))
    rows = (await db.execute(query)).all()
    return [
        ClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape,
            logo_color=c.logo_color, member_count=count,
        )
        for c, count in rows
    ]


async def get_my_club_detail(db: AsyncSession, user: User) -> ClubDetailOut:
    membership = await _require_membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    return await _club_to_detail(db, club, requester_user_id=user.id)


async def get_club_detail(db: AsyncSession, club_id: int, requester_user_id: int) -> ClubDetailOut:
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    return await _club_to_detail(db, club, requester_user_id=requester_user_id)
```

Note: `TransactionType.admin_adjustment` is reused for the creation-cost debit description rather than adding a new enum value — this codebase already reuses that type for miscellaneous non-gameplay coin movements (see `bot/db.py`'s `give_coins`), and a club creation fee doesn't need its own ledger category for Phase 1. If a later phase wants a dedicated type for club-related personal-wallet debits, add one then.

- [ ] **Step 4: Wire the router**

Create `backend/app/routers/clubs.py`:

```python
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubSummaryOut
from app.services import club_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubSummaryOut])
async def list_clubs(
    search: Optional[str] = Query(default=None), db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    return await club_service.list_clubs(db, search)


@router.get("/me", response_model=ClubDetailOut)
async def get_my_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_my_club_detail(db, user)


@router.get("/{club_id}", response_model=ClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_club_detail(db, club_id, requester_user_id=user.id)


@router.post("", response_model=ClubDetailOut)
async def create_club(
    payload: ClubCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_service.create_club(db, user, payload)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`: add `clubs` to the `from app.routers import (...)` block (alphabetically, between `card_collections` and `collection`), and add `app.include_router(clubs.router, prefix=API_PREFIX)` next to the other feature routers (e.g. right after `app.include_router(leagues.router, prefix=API_PREFIX)`).

- [ ] **Step 6: Run tests, iterate until green**

Run: `docker compose exec -T backend pytest tests/test_clubs.py -v`
Expected: all 6 tests pass.

- [ ] **Step 7: Run the full backend suite**

Run: `docker compose exec -T backend pytest tests/ -q`
Expected: same pass count as before this task plus 6, only the pre-existing unrelated `test_task_reward_pack_grants_all_cards` failure (if still present).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/club_service.py backend/app/routers/clubs.py backend/app/main.py backend/tests/test_clubs.py
git commit -m "Add club creation, browsing, and detail endpoints"
```

---

### Task 5: Membership actions — join, requests, leave, roles, invite (service + router + tests)

**Files:**
- Modify: `backend/app/services/club_service.py`
- Modify: `backend/app/routers/clubs.py`
- Modify: `backend/tests/test_clubs.py`

**Interfaces:**
- Consumes: everything from Task 4 (`_lock_club`, `_member_count`, `_get_membership`, `_require_membership`, `_require_manager`, `_club_to_detail`), `notification_service.notify`.
- Produces: `join_open_club`, `create_join_request`, `list_join_requests`, `respond_to_join_request`, `leave_club`, `kick_member`, `appoint_assistant`, `remove_assistant`, `transfer_captain`, `disband_club`, `join_by_invite` — routes for all of these.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_clubs.py`:

```python
async def _create_club(client, bot_token, telegram_id, name, club_type="open"):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": club_type, "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def test_join_open_club_adds_member(client, db_session, bot_token):
    club, _ = await _create_club(client, bot_token, 820101, "Открытый клуб")
    await _register_only(client, bot_token, 820102)
    headers2 = telegram_headers(820102, bot_token)

    resp = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=headers2)
    assert resp.status_code == 200
    assert resp.json()["member_count"] == 2


async def test_join_closed_club_creates_request_then_accept_adds_member(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820103, "Закрытый клуб", club_type="closed")
    await _register_only(client, bot_token, 820104)
    headers2 = telegram_headers(820104, bot_token)

    direct_join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=headers2)
    assert direct_join.status_code == 409

    req_resp = await client.post(f"/api/v1/clubs/{club['id']}/join-requests", headers=headers2)
    assert req_resp.status_code == 200
    request_id = req_resp.json()["id"]

    list_resp = await client.get("/api/v1/clubs/me/join-requests", headers=captain_headers)
    assert len(list_resp.json()) == 1

    accept_resp = await client.post(f"/api/v1/clubs/me/join-requests/{request_id}/accept", headers=captain_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["member_count"] == 2


async def test_leave_club_promotes_longest_tenured_assistant(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820105, "Клуб с ассистентом")
    await _register_only(client, bot_token, 820106)
    member_headers = telegram_headers(820106, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    appoint = await client.post(f"/api/v1/clubs/me/assistants/{member_user_id}/appoint", headers=captain_headers)
    assert appoint.status_code == 200

    leave_resp = await client.post("/api/v1/clubs/me/leave", headers=captain_headers)
    assert leave_resp.status_code == 200

    new_club_state = await client.get("/api/v1/clubs/me", headers=member_headers)
    assert new_club_state.json()["captain_id"] == member_user_id


async def test_leave_club_disbands_when_no_assistants(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820107, "Клуб без ассистентов")
    leave_resp = await client.post("/api/v1/clubs/me/leave", headers=captain_headers)
    assert leave_resp.status_code == 200

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.status_code == 404


async def test_kick_member_removes_them(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820108, "Клуб-кикер")
    await _register_only(client, bot_token, 820109)
    member_headers = telegram_headers(820109, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    kick_resp = await client.post(f"/api/v1/clubs/me/members/{member_user_id}/kick", headers=captain_headers)
    assert kick_resp.status_code == 200
    assert kick_resp.json()["member_count"] == 1

    solo_check = await client.get("/api/v1/clubs/me", headers=member_headers)
    assert solo_check.status_code == 404


async def test_join_by_invite_code(client, db_session, bot_token):
    club, _ = await _create_club(client, bot_token, 820110, "Клуб по инвайту", club_type="closed")
    await _register_only(client, bot_token, 820111)
    headers2 = telegram_headers(820111, bot_token)

    resp = await client.post("/api/v1/clubs/join-by-invite", headers=headers2, json={"invite_code": club["invite_code"]})
    assert resp.status_code == 200
    assert resp.json()["member_count"] == 2


async def test_transfer_captain(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820112, "Клуб-передача")
    await _register_only(client, bot_token, 820113)
    member_headers = telegram_headers(820113, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    resp = await client.post("/api/v1/clubs/me/transfer-captain", headers=captain_headers, json={"user_id": member_user_id})
    assert resp.status_code == 200
    assert resp.json()["captain_id"] == member_user_id


async def test_disband_club(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820114, "Клуб на роспуск")
    resp = await client.post("/api/v1/clubs/me/disband", headers=captain_headers)
    assert resp.status_code == 204

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `docker compose exec -T backend pytest tests/test_clubs.py -v -k "join or leave or kick or transfer or disband"`
Expected: `FAIL` / `404` for the new routes (not implemented yet).

- [ ] **Step 3: Implement the new service functions**

Append to `backend/app/services/club_service.py`. First update its existing import lines: add `ClubJoinRequestStatus, NotificationType` to the `from app.models.enums import ...` line, add `ClubJoinRequestOut` to the `from app.schemas.club import ...` line, and add two new import lines — `from app.services.notification_service import notify` and `from typing import Optional` (only if not already present from Task 4's own imports; Task 4's file already imports `Optional` from `typing`, so just confirm it's there rather than duplicating it). `ClubJoinRequest` itself is already imported via Task 4's `from app.models.club import Club, ClubJoinRequest, ClubMember` line.

```python
async def join_open_club(db: AsyncSession, user: User, club_id: int) -> ClubDetailOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    club = await _lock_club(db, club_id)
    if club.club_type != ClubType.open:
        raise ConflictError("Это закрытый клуб — нужна заявка")
    if await _member_count(db, club_id) >= MAX_MEMBERS:
        raise ConflictError("В клубе нет свободных мест")

    db.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.member))
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=user.id)


async def create_join_request(db: AsyncSession, user: User, club_id: int) -> ClubJoinRequestOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    if club.club_type != ClubType.closed:
        raise ConflictError("Это открытый клуб — просто вступи")

    existing = await db.execute(
        select(ClubJoinRequest).where(
            ClubJoinRequest.club_id == club_id, ClubJoinRequest.user_id == user.id,
            ClubJoinRequest.status == ClubJoinRequestStatus.pending,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Заявка уже отправлена")

    request = ClubJoinRequest(club_id=club_id, user_id=user.id)
    db.add(request)
    await db.flush()

    managers = await db.execute(
        select(ClubMember.user_id).where(ClubMember.club_id == club_id, ClubMember.role.in_([ClubRole.captain, ClubRole.assistant]))
    )
    for manager_id in managers.scalars().all():
        await notify(
            db, manager_id, NotificationType.club_join_request_received,
            "Новая заявка в клуб", f"Игрок хочет вступить в «{club.name}»",
            related_object_type="club_join_request", related_object_id=request.id,
        )
    await db.commit()
    await db.refresh(request)
    return ClubJoinRequestOut(
        id=request.id, user_id=user.id, username=user.username, first_name=user.first_name,
        avatar_url=user.avatar_url, created_at=request.created_at, status=request.status,
    )


async def list_join_requests(db: AsyncSession, user: User) -> list[ClubJoinRequestOut]:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    rows = (
        await db.execute(
            select(ClubJoinRequest, User)
            .join(User, User.id == ClubJoinRequest.user_id)
            .where(ClubJoinRequest.club_id == membership.club_id, ClubJoinRequest.status == ClubJoinRequestStatus.pending)
            .order_by(ClubJoinRequest.created_at)
        )
    ).all()
    return [
        ClubJoinRequestOut(
            id=r.id, user_id=u.id, username=u.username, first_name=u.first_name,
            avatar_url=u.avatar_url, created_at=r.created_at, status=r.status,
        )
        for r, u in rows
    ]


async def respond_to_join_request(db: AsyncSession, actor: User, request_id: int, accept: bool) -> None:
    membership = await _require_membership(db, actor.id)
    _require_manager(membership)

    request = await db.get(ClubJoinRequest, request_id)
    if request is None or request.club_id != membership.club_id:
        raise NotFoundError("Заявка не найдена")
    if request.status != ClubJoinRequestStatus.pending:
        raise ConflictError("Заявка уже обработана")

    club = await _lock_club(db, membership.club_id)
    if accept:
        if await _get_membership(db, request.user_id) is not None:
            raise ConflictError("Игрок уже состоит в другом клубе")
        if await _member_count(db, club.id) >= MAX_MEMBERS:
            raise ConflictError("В клубе нет свободных мест")
        request.status = ClubJoinRequestStatus.accepted
        db.add(ClubMember(club_id=club.id, user_id=request.user_id, role=ClubRole.member))
        await notify(
            db, request.user_id, NotificationType.club_join_request_accepted,
            "Заявка одобрена", f"Ты теперь в клубе «{club.name}»",
        )
    else:
        request.status = ClubJoinRequestStatus.rejected
        await notify(
            db, request.user_id, NotificationType.club_join_request_rejected,
            "Заявка отклонена", f"Заявка в клуб «{club.name}» отклонена",
        )
    db.add(request)
    await db.commit()


async def _promote_longest_tenured_assistant(db: AsyncSession, club: Club) -> Optional[ClubMember]:
    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant)
        .order_by(ClubMember.joined_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def leave_club(db: AsyncSession, user: User) -> None:
    membership = await _require_membership(db, user.id)
    club = await _lock_club(db, membership.club_id)

    if membership.role == ClubRole.captain:
        successor = await _promote_longest_tenured_assistant(db, club)
        if successor is None:
            # No assistants to take over — the club disbands entirely,
            # per the approved design (even if regular members remain).
            await db.delete(club)
            await db.commit()
            return
        successor.role = ClubRole.captain
        club.captain_id = successor.user_id
        db.add(successor)
        db.add(club)
        await notify(
            db, successor.user_id, NotificationType.club_captain_transferred,
            "Ты теперь капитан", f"Капитан клуба «{club.name}» покинул клуб — теперь капитан ты",
        )

    await db.delete(membership)
    await db.commit()


async def kick_member(db: AsyncSession, actor: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, actor.id)
    _require_manager(membership)
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id:
        raise NotFoundError("Игрок не в этом клубе")
    if target.role != ClubRole.member:
        raise ForbiddenError("Нельзя исключить капитана или ассистента")

    await db.delete(target)
    await db.flush()
    await notify(db, target_user_id, NotificationType.club_kicked, "Исключение из клуба", f"Тебя исключили из «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=actor.id)


async def appoint_assistant(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может назначать ассистентов")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id or target.role != ClubRole.member:
        raise ConflictError("Можно назначить ассистентом только обычного участника клуба")

    assistant_count = (
        await db.execute(
            select(func.count(ClubMember.id)).where(ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant)
        )
    ).scalar_one()
    if assistant_count >= MAX_ASSISTANTS:
        raise ConflictError("Уже назначено максимальное число ассистентов")

    target.role = ClubRole.assistant
    db.add(target)
    await notify(db, target_user_id, NotificationType.club_role_changed, "Новая роль", f"Ты назначен ассистентом в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def remove_assistant(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может снимать ассистентов")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id or target.role != ClubRole.assistant:
        raise ConflictError("Этот игрок не ассистент в твоём клубе")

    target.role = ClubRole.member
    db.add(target)
    await notify(db, target_user_id, NotificationType.club_role_changed, "Новая роль", f"Ты больше не ассистент в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def transfer_captain(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может передать капитанство")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id:
        raise NotFoundError("Игрок не в этом клубе")

    assistant_count = (
        await db.execute(
            select(func.count(ClubMember.id)).where(
                ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant, ClubMember.user_id != target_user_id,
            )
        )
    ).scalar_one()
    membership.role = ClubRole.assistant if assistant_count < MAX_ASSISTANTS else ClubRole.member
    target.role = ClubRole.captain
    club.captain_id = target_user_id
    db.add_all([membership, target, club])
    await notify(db, target_user_id, NotificationType.club_captain_transferred, "Ты теперь капитан", f"Тебе передали капитанство в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def disband_club(db: AsyncSession, captain: User) -> None:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может распустить клуб")
    club = await _lock_club(db, membership.club_id)

    other_member_ids = (
        await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club.id, ClubMember.user_id != captain.id))
    ).scalars().all()
    for member_id in other_member_ids:
        await notify(db, member_id, NotificationType.club_kicked, "Клуб распущен", f"Клуб «{club.name}» распущен капитаном")

    await db.delete(club)
    await db.commit()


async def join_by_invite(db: AsyncSession, user: User, invite_code: str) -> ClubDetailOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    result = await db.execute(select(Club).where(Club.invite_code == invite_code).with_for_update())
    club = result.scalar_one_or_none()
    if club is None:
        raise NotFoundError("Приглашение недействительно")
    if await _member_count(db, club.id) >= MAX_MEMBERS:
        raise ConflictError("В клубе нет свободных мест")

    db.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.member))
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=user.id)
```

- [ ] **Step 4: Wire the router**

Append to `backend/app/routers/clubs.py` (add imports: `from app.schemas.club import ClubJoinRequestOut, JoinByInviteIn, TransferCaptainIn` and `from fastapi import status`):

```python
@router.post("/{club_id}/join", response_model=ClubDetailOut)
async def join_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_open_club(db, user, club_id)


@router.post("/{club_id}/join-requests", response_model=ClubJoinRequestOut)
async def create_join_request(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.create_join_request(db, user, club_id)


@router.get("/me/join-requests", response_model=list[ClubJoinRequestOut])
async def list_join_requests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.list_join_requests(db, user)


@router.post("/me/join-requests/{request_id}/accept", response_model=ClubDetailOut)
async def accept_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=True)
    return await club_service.get_my_club_detail(db, user)


@router.post("/me/join-requests/{request_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=False)


@router.post("/join-by-invite", response_model=ClubDetailOut)
async def join_by_invite(payload: JoinByInviteIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_by_invite(db, user, payload.invite_code)


@router.post("/me/leave", status_code=status.HTTP_200_OK)
async def leave_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.leave_club(db, user)
    return {"ok": True}


@router.post("/me/members/{user_id}/kick", response_model=ClubDetailOut)
async def kick_member(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.kick_member(db, user, user_id)


@router.post("/me/assistants/{user_id}/appoint", response_model=ClubDetailOut)
async def appoint_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.appoint_assistant(db, user, user_id)


@router.post("/me/assistants/{user_id}/remove", response_model=ClubDetailOut)
async def remove_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.remove_assistant(db, user, user_id)


@router.post("/me/transfer-captain", response_model=ClubDetailOut)
async def transfer_captain(payload: TransferCaptainIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.transfer_captain(db, user, payload.user_id)


@router.post("/me/disband", status_code=status.HTTP_204_NO_CONTENT)
async def disband_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.disband_club(db, user)
```

**Important — route ordering:** FastAPI matches routes in declaration order. `GET /{club_id}` (Task 4) is a catch-all path parameter that would incorrectly swallow `GET /me` if declared first. Confirm `router.get("/me", ...)` from Task 4 is declared **before** `router.get("/{club_id}", ...)` in the final file (it already is, since Task 4 wrote `/me` first) — this new task only adds `POST`/other-path routes, so this ordering concern doesn't apply to them, but double-check `/me/join-requests` (a `GET`) isn't shadowed by anything either (it isn't, since the only other `GET` is `/{club_id}` which is declared before it in file order from Task 4 — actually verify `/me/join-requests` comes anywhere, order among `GET`s doesn't matter for it since `/{club_id}` only has one path segment and won't match `/me/join-requests`'s two segments... but FastAPI still tries routes in order for equal-specificity matches, so as a rule of thumb keep literal-prefix routes appearing before single-param catch-alls in the same file regardless).

- [ ] **Step 5: Run tests, iterate until green**

Run: `docker compose exec -T backend pytest tests/test_clubs.py -v`
Expected: all tests (Task 4's 6 + this task's 8) pass.

- [ ] **Step 6: Run the full backend suite**

Run: `docker compose exec -T backend pytest tests/ -q`

- [ ] **Step 7: Manually verify the row-locking under real Postgres**

This task's `_lock_club`/`join_open_club`/`respond_to_join_request` are exactly the kind of locking-dependent code CLAUDE.md flags as untested by SQLite. Verify manually:
```bash
docker compose exec -T backend python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.services import club_service

async def main():
    async with AsyncSessionLocal() as db:
        # Confirm _lock_club actually emits FOR UPDATE against real Postgres
        from sqlalchemy import select
        from app.models.club import Club
        stmt = select(Club).where(Club.id == 1).with_for_update()
        print(str(stmt.compile(dialect=db.bind.dialect, compile_kwargs={'literal_binds': True})))

asyncio.run(main())
"
```
Confirm the printed SQL contains `FOR UPDATE`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/club_service.py backend/app/routers/clubs.py backend/tests/test_clubs.py
git commit -m "Add club membership actions: join, requests, leave, roles, invite"
```

---

### Task 6: Bot deep-link handling for club invites

**Files:**
- Modify: `bot/handlers/user.py`

**Interfaces:**
- Consumes: `open_app_keyboard` (existing, `bot/keyboards.py`).
- Produces: `/start club_<code>` now opens the Mini App with `?joinClub=<code>` appended — consumed by Task 12's frontend query-param handler.

- [ ] **Step 1: Add the new payload branch**

In `bot/handlers/user.py`'s `cmd_start`, add an `elif` branch alongside the existing `ref_`/`chatpack` handling:

```python
    elif payload and payload.startswith("club_"):
        invite_code = payload[len("club_"):]
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            "⚽ Тебя пригласили в клуб в <b>VICTOR FC</b>!\n\n"
            "Нажми кнопку ниже, чтобы открыть приложение и вступить 👇"
        )
        keyboard = open_app_keyboard(query=f"?joinClub={invite_code}")
```

Place this `elif` after the existing `if payload and payload.startswith("ref_"):` block and before `elif payload == "chatpack":` (order doesn't functionally matter since the prefixes are disjoint, but keep the existing block's flow intact — don't restructure the `ref_`/`chatpack` branches).

- [ ] **Step 2: Manual smoke test**

Run: `docker compose exec -T bot python -c "import handlers.user; print('ok')"`
Expected: `ok`, no syntax/import errors.

- [ ] **Step 3: Commit**

```bash
git add bot/handlers/user.py
git commit -m "Handle club invite deep links in the bot's /start command"
```

---

### Task 7: Frontend types and API client

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/api/clubs.ts`

**Interfaces:**
- Produces: `Club`, `ClubMember`, `ClubJoinRequest`, `ClubType`, `ClubRole`, `ClubLogoShape` types; `fetchClubs`, `fetchMyClub`, `fetchClub`, `createClub`, `updateClub`, `joinClub`, `createJoinRequest`, `fetchMyJoinRequests`, `acceptJoinRequest`, `rejectJoinRequest`, `joinByInvite`, `leaveClub`, `kickMember`, `appointAssistant`, `removeAssistant`, `transferCaptain`, `disbandClub` API functions — consumed by every frontend task after this one.

- [ ] **Step 1: Add the types**

In `frontend/src/types.ts`, add (matching this file's existing style — plain exported `interface`/`type`, no class):

```typescript
export type ClubType = "open" | "closed";
export type ClubRole = "captain" | "assistant" | "member";
export type ClubLogoShape = "shield" | "circle" | "hexagon" | "star" | "diamond" | "banner" | "crest" | "chevron";

export interface ClubMember {
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  role: ClubRole;
  joined_at: string;
}

export interface ClubSummary {
  id: number;
  name: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  member_count: number;
}

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
}

export interface ClubJoinRequest {
  id: number;
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  created_at: string;
  status: "pending" | "accepted" | "rejected";
}
```

- [ ] **Step 2: Write the API client**

Create `frontend/src/api/clubs.ts`:

```typescript
import { api } from "@/lib/api";
import type { Club, ClubJoinRequest, ClubSummary } from "@/types";

export async function fetchClubs(search?: string): Promise<ClubSummary[]> {
  const { data } = await api.get<ClubSummary[]>("/clubs", { params: { search: search || undefined } });
  return data;
}

export async function fetchMyClub(): Promise<Club> {
  const { data } = await api.get<Club>("/clubs/me");
  return data;
}

export async function fetchClub(id: number): Promise<Club> {
  const { data } = await api.get<Club>(`/clubs/${id}`);
  return data;
}

export async function createClub(payload: {
  name: string;
  description: string;
  club_type: string;
  logo_shape: string;
  logo_color: string;
}): Promise<Club> {
  const { data } = await api.post<Club>("/clubs", payload);
  return data;
}

export async function joinClub(id: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/${id}/join`);
  return data;
}

export async function createJoinRequest(id: number): Promise<ClubJoinRequest> {
  const { data } = await api.post<ClubJoinRequest>(`/clubs/${id}/join-requests`);
  return data;
}

export async function fetchMyJoinRequests(): Promise<ClubJoinRequest[]> {
  const { data } = await api.get<ClubJoinRequest[]>("/clubs/me/join-requests");
  return data;
}

export async function acceptJoinRequest(requestId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/join-requests/${requestId}/accept`);
  return data;
}

export async function rejectJoinRequest(requestId: number): Promise<void> {
  await api.post(`/clubs/me/join-requests/${requestId}/reject`);
}

export async function joinByInvite(inviteCode: string): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/join-by-invite", { invite_code: inviteCode });
  return data;
}

export async function leaveClub(): Promise<void> {
  await api.post("/clubs/me/leave");
}

export async function kickMember(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/members/${userId}/kick`);
  return data;
}

export async function appointAssistant(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/assistants/${userId}/appoint`);
  return data;
}

export async function removeAssistant(userId: number): Promise<Club> {
  const { data } = await api.post<Club>(`/clubs/me/assistants/${userId}/remove`);
  return data;
}

export async function transferCaptain(userId: number): Promise<Club> {
  const { data } = await api.post<Club>("/clubs/me/transfer-captain", { user_id: userId });
  return data;
}

export async function disbandClub(): Promise<void> {
  await api.post("/clubs/me/disband");
}
```

- [ ] **Step 3: Typecheck**

Run: `docker compose exec -T frontend npm run typecheck`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/clubs.ts
git commit -m "Add Club frontend types and API client"
```

---

### Task 8: `ClubLogo` component (SVG shapes + color)

**Files:**
- Create: `frontend/src/components/clubs/ClubLogo.tsx`

**Interfaces:**
- Produces: `<ClubLogo shape={ClubLogoShape} color={string} size={number} />` — consumed by every later frontend task that renders a club.

- [ ] **Step 1: Write the component**

Create `frontend/src/components/clubs/ClubLogo.tsx`:

```typescript
import type { ClubLogoShape } from "@/types";

const SHAPE_PATHS: Record<ClubLogoShape, string> = {
  shield: "M50 5 L90 20 V50 C90 75 70 90 50 95 C30 90 10 75 10 50 V20 Z",
  circle: "M50 5 A45 45 0 1 1 49.99 5 Z",
  hexagon: "M50 5 L90 27.5 V72.5 L50 95 L10 72.5 V27.5 Z",
  star: "M50 5 L61 38 H96 L67 59 L78 92 L50 71 L22 92 L33 59 L4 38 H39 Z",
  diamond: "M50 5 L90 50 L50 95 L10 50 Z",
  banner: "M15 5 H85 V80 L50 65 L15 80 Z",
  crest: "M50 5 C70 5 88 15 88 35 C88 60 70 85 50 95 C30 85 12 60 12 35 C12 15 30 5 50 5 Z",
  chevron: "M10 30 L50 5 L90 30 L90 60 L50 35 L10 60 Z M10 65 L50 40 L90 65 L90 95 L50 70 L10 95 Z",
};

export function ClubLogo({ shape, color, size = 40 }: { shape: ClubLogoShape; color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <path d={SHAPE_PATHS[shape]} fill={color} />
    </svg>
  );
}

export const CLUB_LOGO_SHAPES: ClubLogoShape[] = [
  "shield", "circle", "hexagon", "star", "diamond", "banner", "crest", "chevron",
];

export const CLUB_LOGO_COLORS: string[] = [
  "#EF4444", "#F97316", "#EAB308", "#22C55E", "#06B6D4", "#3B82F6", "#8B5CF6", "#EC4899",
];
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend npm run typecheck`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/clubs/ClubLogo.tsx
git commit -m "Add ClubLogo SVG shape+color component"
```

---

### Task 9: `ClubsPage` — browse list / auto-render own club

**Files:**
- Create: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `fetchMyClub`, `fetchClubs`, `joinClub`, `createJoinRequest` (Task 7), `ClubLogo` (Task 8).
- Produces: renders at `/clubs` (wired in Task 12). If the user has a club (`fetchMyClub` succeeds), renders inline club-home content (members list, role, leave button) — **this task's club-home view is intentionally minimal** (full squad/budget/tournament UI is later phases); if not (404), renders the browse list + search + "Создать клуб" button.

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/ClubsPage.tsx`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ClubLogo } from "@/components/clubs/ClubLogo";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconPlus, IconUsers } from "@/components/icons";
import { createJoinRequest, fetchClubs, fetchMyClub, joinClub, kickMember, leaveClub } from "@/api/clubs";
import { ApiRequestError } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Club } from "@/types";

export default function ClubsPage() {
  const { data: myClub, isLoading: loadingMine, error: myClubError } = useQuery({
    queryKey: ["clubs", "me"],
    queryFn: fetchMyClub,
    retry: false,
  });

  const inClub = !loadingMine && !myClubError;

  if (loadingMine) return <ListSkeleton />;
  if (inClub && myClub) return <ClubHome club={myClub} />;
  return <ClubBrowseList />;
}

function ClubBrowseList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { data: clubs, isLoading } = useQuery({ queryKey: ["clubs", "list", search], queryFn: () => fetchClubs(search) });

  const joinMutation = useMutation({
    mutationFn: (id: number) => joinClub(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs"] }),
    onError: (err) => setJoinError(err instanceof ApiRequestError ? err.message : "Не удалось вступить"),
  });
  const requestMutation = useMutation({
    mutationFn: (id: number) => createJoinRequest(id),
    onError: (err) => setJoinError(err instanceof ApiRequestError ? err.message : "Не удалось отправить заявку"),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубы</h1>
        <button
          onClick={() => navigate("/clubs/create")}
          className="flex items-center gap-1 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
        >
          <IconPlus size={13} />
          Создать
        </button>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск клуба..."
        className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
      />

      {joinError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{joinError}</p>}
      {isLoading && <ListSkeleton />}
      {!isLoading && !clubs?.length && <EmptyState icon={IconUsers} title="Клубов пока нет" description="Стань первым, кто создаст клуб" />}

      <div className="flex flex-col gap-2">
        {clubs?.map((c) => (
          <div key={c.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <ClubLogo shape={c.logo_shape} color={c.logo_color} size={40} />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{c.name}</p>
              <p className="text-xs text-ink-mist-dim">{c.member_count}/11 участников</p>
            </div>
            {c.club_type === "open" ? (
              <button
                onClick={() => joinMutation.mutate(c.id)}
                className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
              >
                Вступить
              </button>
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
        ))}
      </div>
    </div>
  );
}

const ROLE_LABELS: Record<string, string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };

function ClubHome({ club }: { club: Club }) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const isManager = club.my_role === "captain" || club.my_role === "assistant";

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["clubs"] });
  const leaveMutation = useMutation({ mutationFn: leaveClub, onSuccess: invalidate });
  const kickMutation = useMutation({ mutationFn: (id: number) => kickMember(id), onSuccess: invalidate });

  const handleLeave = async () => {
    const confirmMsg = club.my_role === "captain" ? "Покинуть клуб? Капитанство перейдёт ассистенту (или клуб распустится, если ассистентов нет)." : "Покинуть клуб?";
    if (await showConfirm(confirmMsg)) leaveMutation.mutate();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <ClubLogo shape={club.logo_shape} color={club.logo_color} size={56} />
        <div>
          <h1 className="font-display text-xl font-bold text-ink-chalk">{club.name}</h1>
          <p className="text-xs text-ink-mist-dim">{club.member_count}/11 участников · {ROLE_LABELS[club.my_role ?? "member"]}</p>
        </div>
      </div>

      {club.description && <p className="rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">{club.description}</p>}

      {club.invite_code && (
        <div className="rounded-2xl bg-bg-surface p-3 text-xs text-ink-mist">
          Ссылка-приглашение: <span className="font-mono text-ink-chalk">club_{club.invite_code}</span>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Участники</p>
        {club.members.map((m) => (
          <div key={m.user_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
            <span className="text-sm text-ink-chalk">{m.username ?? m.first_name ?? `#${m.user_id}`} · {ROLE_LABELS[m.role]}</span>
            {isManager && m.role === "member" && m.user_id !== userId && (
              <button
                onClick={() => kickMutation.mutate(m.user_id)}
                className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400"
              >
                Исключить
              </button>
            )}
          </div>
        ))}
      </div>

      <button onClick={handleLeave} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
        Покинуть клуб
      </button>
    </div>
  );
}
```

`IconUsers` is a confirmed existing export in `frontend/src/components/icons/index.tsx:318` — import it from `@/components/icons` alongside `IconPlus`.

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend npm run typecheck`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClubsPage.tsx
git commit -m "Add ClubsPage: browse list and minimal club home"
```

---

### Task 10: `ClubCreatePage`

**Files:**
- Create: `frontend/src/pages/ClubCreatePage.tsx`

**Interfaces:**
- Consumes: `createClub` (Task 7), `ClubLogo`/`CLUB_LOGO_SHAPES`/`CLUB_LOGO_COLORS` (Task 8).

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/ClubCreatePage.tsx`:

```typescript
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CLUB_LOGO_COLORS, CLUB_LOGO_SHAPES, ClubLogo } from "@/components/clubs/ClubLogo";
import { IconChevronLeft } from "@/components/icons";
import { createClub } from "@/api/clubs";
import { ApiRequestError } from "@/lib/api";
import type { ClubLogoShape, ClubType } from "@/types";

export default function ClubCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [clubType, setClubType] = useState<ClubType>("open");
  const [shape, setShape] = useState<ClubLogoShape>("shield");
  const [color, setColor] = useState(CLUB_LOGO_COLORS[0]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => createClub({ name, description, club_type: clubType, logo_shape: shape, logo_color: color }),
    onSuccess: () => navigate("/clubs"),
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать клуб"),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Новый клуб</h1>
      </div>

      <div className="flex justify-center">
        <ClubLogo shape={shape} color={color} size={80} />
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        {CLUB_LOGO_SHAPES.map((s) => (
          <button
            key={s}
            onClick={() => setShape(s)}
            className={`rounded-xl p-2 ${shape === s ? "bg-floodlight/30" : "bg-bg-surface"}`}
          >
            <ClubLogo shape={s} color={color} size={28} />
          </button>
        ))}
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        {CLUB_LOGO_COLORS.map((c) => (
          <button
            key={c}
            onClick={() => setColor(c)}
            style={{ backgroundColor: c }}
            className={`h-8 w-8 rounded-full ${color === c ? "ring-2 ring-white" : ""}`}
          />
        ))}
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-mist-dim">Название</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-mist-dim">Описание (необязательно)</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={512}
          rows={3}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
        />
      </label>

      <div className="flex gap-2">
        <button
          onClick={() => setClubType("open")}
          className={`flex-1 rounded-xl py-2 text-xs font-semibold ${clubType === "open" ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
        >
          Открытый
        </button>
        <button
          onClick={() => setClubType("closed")}
          className={`flex-1 rounded-xl py-2 text-xs font-semibold ${clubType === "closed" ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
        >
          Закрытый (по заявке)
        </button>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <button
        onClick={() => mutation.mutate()}
        disabled={name.trim().length < 3 || mutation.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {mutation.isPending ? "Создание..." : "Создать клуб"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend npm run typecheck`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClubCreatePage.tsx
git commit -m "Add ClubCreatePage"
```

---

### Task 11: Join-requests inbox (closed-club captain/assistant view)

**Files:**
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:**
- Consumes: `fetchMyJoinRequests`, `acceptJoinRequest`, `rejectJoinRequest` (Task 7).

- [ ] **Step 1: Add the inbox to `ClubHome`**

In `frontend/src/pages/ClubsPage.tsx`, extend `ClubHome` to show a pending-requests section when `isManager && club.club_type === "closed"`. Add the import `import { acceptJoinRequest, fetchMyJoinRequests, rejectJoinRequest } from "@/api/clubs";` (merge into the existing `@/api/clubs` import line), then inside `ClubHome`, add:

```typescript
  const { data: joinRequests } = useQuery({
    queryKey: ["clubs", "join-requests"],
    queryFn: fetchMyJoinRequests,
    enabled: isManager && club.club_type === "closed",
  });
  const acceptMutation = useMutation({ mutationFn: (id: number) => acceptJoinRequest(id), onSuccess: invalidate });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectJoinRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "join-requests"] }),
  });
```

and, right before the "Участники" section, render:

```typescript
      {isManager && club.club_type === "closed" && joinRequests && joinRequests.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Заявки на вступление</p>
          {joinRequests.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
              <span className="text-sm text-ink-chalk">{r.username ?? r.first_name ?? `#${r.user_id}`}</span>
              <div className="flex gap-2">
                <button onClick={() => acceptMutation.mutate(r.id)} className="rounded-lg bg-accent-green px-2 py-1 text-[11px] font-bold text-bg-base">
                  Принять
                </button>
                <button onClick={() => rejectMutation.mutate(r.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend npm run typecheck`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClubsPage.tsx
git commit -m "Add join-request inbox to club home"
```

---

### Task 12: Routing, `?joinClub=` consumption, and the Home banner

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/HomePage.tsx`

**Interfaces:**
- Consumes: `ClubsPage` (Task 9), `ClubCreatePage` (Task 10), `joinByInvite` (Task 7), `ClubLogo` (Task 8).
- Produces: `/clubs`, `/clubs/create` routes; opening the app with `?joinClub=<code>` in the URL joins that club then redirects to `/clubs`; a new banner block on Home linking to `/clubs`.

- [ ] **Step 1: Add the routes**

In `frontend/src/App.tsx`: add `import ClubsPage from "@/pages/ClubsPage";` and `import ClubCreatePage from "@/pages/ClubCreatePage";` (alphabetically among the other page imports), then inside the `<Route element={<AppLayout />}>` block, add:

```typescript
        <Route path="/clubs" element={<ClubsPage />} />
        <Route path="/clubs/create" element={<ClubCreatePage />} />
```

(placed near `/trades`, matching this file's existing grouping-by-feature order).

- [ ] **Step 2: Consume `?joinClub=` after auth succeeds**

Add the import `import { joinByInvite } from "@/api/clubs";` to `App.tsx`'s existing import block, and add `useNavigate` to its existing `import { Navigate, Route, Routes, useLocation } from "react-router-dom";` line (`useNavigate` isn't imported yet — only `useLocation` is, used by the separate `PenaltySearchRoute` component). `App()` itself doesn't currently call `useNavigate()` — add `const navigate = useNavigate();` inside `App()`, alongside its other hooks near the top. This is safe: `App` renders inside `<BrowserRouter>` (see `main.tsx`), so the hook has a valid router context. This codebase's `BrowserRouter` (confirmed in `main.tsx` — **not** `HashRouter`) means navigation must go through `useNavigate()`, not by writing to `window.location.hash`, which wouldn't actually change the route.

Then, **after** the existing `useEffect` that calls `createSession(...)` — not inside it, since — unlike `ref`, which is registration-time-only — `joinClub` must work for an already-registered user reopening the same link — add a **new**, separate `useEffect` (don't cram it into the session-creation effect, which has an unrelated cleanup/cancellation contract):

```typescript
  useEffect(() => {
    if (!isReady || !user) return;
    const joinClubCode = new URLSearchParams(window.location.search).get("joinClub");
    if (!joinClubCode) return;
    joinByInvite(joinClubCode)
      .catch(() => undefined)
      .finally(() => {
        const url = new URL(window.location.href);
        url.searchParams.delete("joinClub");
        window.history.replaceState({}, "", url.toString());
        navigate("/clubs", { replace: true });
      });
  }, [isReady, user, navigate]);
```

Note: swallowing the error (`.catch(() => undefined)`) is deliberate for this first phase — e.g. the user is already in a different club, or the invite is stale. A toast/error surface can be added later; the important behavior for Phase 1 is that a valid invite silently joins and always lands on `/clubs`, where the normal club-home view (or a fresh browse list, if the join failed) takes over.

- [ ] **Step 3: Add the Home banner**

In `frontend/src/pages/HomePage.tsx`, add `import { useNavigate } from "react-router-dom";` if not already imported (check first — `HomePage.tsx` likely already has it, given the League banner calls `navigate("/league")`), and immediately after the closing `)}` of the existing League banner block (the one with `onClick={() => navigate("/league")}`, ending around where `leagueStatus.next_league` rendering finishes), add:

```typescript
      <button
        onClick={() => navigate("/clubs")}
        className="flex w-full items-center gap-3 rounded-2xl bg-bg-surface p-3 text-left active:scale-[0.99]"
      >
        <IconUsers size={22} className="text-floodlight" />
        <div>
          <p className="font-display text-sm font-bold text-ink-chalk">Клубы</p>
          <p className="text-xs text-ink-mist-dim">Собери команду и соревнуйся в турнирах</p>
        </div>
      </button>
```

Import `IconUsers` from `@/components/icons` — the same export used in Task 9.

- [ ] **Step 4: Browser verification**

Start/attach the frontend preview (rebuild via `docker compose up -d --build frontend` first if the static-preview override from `docker-compose.override.yml` is active — check `CLAUDE.md`/earlier session notes). Then:
1. Navigate to `http://localhost:5173`, confirm the new "Клубы" banner renders on Home right after the League banner.
2. Click it — since this user isn't in a club yet, confirm the browse list renders (empty state or existing test clubs).
3. Click "Создать", fill the form, pick a shape/color, submit — confirm redirect to `/clubs` now shows the club-home view with the creator as captain.
4. Open a second dev-mode session (or use the admin/dev-mode header trick already established in this codebase) as a different user, confirm they see the new club in the browse list and can join it.
5. Confirm the invite-link JSON field (`club_<code>`) is visible in the club-home view for a member.

- [ ] **Step 5: Full verification pass**

```bash
docker compose exec -T backend pytest tests/ -q
docker compose exec -T frontend npm run typecheck
```
Both must be clean (only the pre-existing unrelated `test_task_reward_pack_grants_all_cards` failure allowed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/HomePage.tsx
git commit -m "Wire Clubs routes, invite-link consumption, and Home banner"
```
