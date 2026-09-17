# Club Tournament Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five independent improvements to the club-tactical tournament system: (1) per-match
club-budget rewards, (2) fix a real bug where the join-request "Принять" button silently does
nothing, (3) raise the assistant cap from 2 to 4 and hide the assign button once full, (4) a new
"Тренировка состава" mechanic — 3 uses per tournament, each boosting the squad ~10% for exactly
the next tour, (5) make red cards/injuries visible (who, why, for how long — in both the
notification and the squad UI) and slightly more frequent.

**Architecture:** All five build on the existing club-tactical match engine
(`docs/superpowers/plans/2026-08-30-club-tactical-match-engine-phase1.md`,
`docs/superpowers/plans/2026-09-07-club-tactical-match-engine-phase2.md`) without touching its
core simulation math. Match rewards hook into `tournament_simulation_service.simulate_next_round`
right where results are already applied. The training boost is a per-tournament-per-club counter
on the already-one-row-per-tournament-per-club `TournamentClubStanding`, applied as an optional
multiplier threaded through `club_tactical_profile_service.compute_profile` (the existing choke
point the coach-boost system already uses the same way) — so it affects real match resolution,
not just a cosmetic number. Red card/injury visibility surfaces data that already exists
server-side (`ClubCardAvailability.rounds_remaining`) through the API and UI layers that
currently never read it, plus one new column (`reason`) to tell the two apart.

**Tech Stack:** FastAPI + async SQLAlchemy 2 (backend), React 18 + TypeScript + TanStack Query
(frontend), Alembic migrations, pytest (async, in-memory SQLite; Postgres for
migration/locking/enum verification per this repo's CLAUDE.md).

**Spec:** No separate spec document — scoped directly in chat with the user, covering five
distinct, user-reported items against the already-built club-tactical engine.

## Global Constraints

- **Every new Postgres enum value needs an explicit `ALTER TYPE ... ADD VALUE IF NOT EXISTS`
  in its migration** (`ClubBudgetTransactionType.tournament_match_reward` — Task 1). This plan's
  immediately-prior sibling plan (club-penalty, 2026-09-09) shipped without this and every
  affected endpoint 500'd on real Postgres until a follow-up migration fixed it — do not repeat
  that mistake. A brand-new enum TYPE (not adding a value to an existing one — e.g.
  `club_card_availability_reason_enum`, Task 8) is different: create it explicitly via
  `sa.Enum(...).create(op.get_bind(), checkfirst=True)` before the `op.add_column` call that
  uses it with `create_type=False`, matching this repo's own established `rarity_enum` reuse
  pattern — do not rely on implicit auto-create behavior for `add_column`.
- **Every `nullable=False` column addition needs `server_default=`** in the migration's
  `op.add_column(...)` call, not just a Python-side `default=` on the model.
- **Any mutation of `Club.budget` must go through a locked club row** (`club_service._lock_club`,
  a module-private function this codebase already imports across service boundaries —
  `club_missing_item_service.py`/`club_penalty_service.py` both do this — same pattern applies
  here) followed by `club_budget_service.credit_club_budget`. Never mutate `club.budget` or call
  `credit_club_budget` on an unlocked `Club` row fetched via a plain `db.get`/`select`.
- **`compute_profile`'s new `training_multiplier` parameter must default to `1.0`** so its three
  existing call sites (`club_tactical_matchup_service.build_side`, and the two
  `club_squad_service.py` call sites — one for the viewer's own squad, one for
  `get_next_opponent`'s preview of the OPPONENT's squad) are unaffected unless a caller opts in.
  The opponent-preview call site must never receive the viewer's own training multiplier — it is
  not that call's own club.
- **The training boost applies to exactly one round: the tournament's next round to be
  simulated at activation time.** It must be consumed (cleared back to `None`) the moment that
  round is actually simulated — whether or not the club's own match that round was a bye/
  withdrawal-loss (it isn't: withdrawn-club auto-loss matches skip engine resolution entirely, so
  a boost active for that round would otherwise sit unconsumed and silently carry into the next
  real round — clear it for every club whose "next round" advances, not only clubs with a real
  match that round, though in practice every non-withdrawn club always has a real match).
- **A new tournament for a club always gets a brand-new `TournamentClubStanding` row**
  (enforced by `uq_tournament_club_standings_once`) — so `training_uses_remaining` resetting to
  its configured per-tournament amount at the start of every tournament requires no separate
  "reset" code path; it falls out of the row being freshly created in
  `tournament_queue_service.apply_to_tournament`.
- **Red card vs. injury `reason` tracking must reflect the more informative outcome when both
  happen to the same card in the same match.** The match engine's existing rule (an injury can
  only ever roll as a bonus ON TOP of a red card, never independently) already computes the
  final `rounds_remaining` via `max(existing, new)`; process `red_cards` fully before `injuries`
  in `_apply_engine_result` so a card that got both ends up with `reason="injury"` (the more
  severe, more informative label) — not because it's more common, but because it's what actually
  governs how long the player is out.
- **The two hardcoded literals this plan converts to config (`0.15` tackle-attempt gate, `0.3`
  injury-given-red chance) live only in the CLUB tactical engine** (`tournament_match_engine.py`).
  Do NOT touch `match_tackle_foul_chance_min/max`/`match_tackle_red_chance_min/max` — those are
  deliberately SHARED with the personal Card Arena engine (`match_service.py`), by explicit
  design (see `tournament_match_engine.py`'s own module comment), and changing them would alter
  personal Card Arena's balance, which nobody asked for.
- This repo's CLAUDE.md mandatory rules apply throughout: economy/authorization/probability
  calculations stay backend-only, never trust frontend-supplied values for rewards, atomic +
  row-locked mutations for anything touching coins/cards/packs/club budget, async DB access only.

---

### Task 1: Backend — per-match club budget rewards

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/game_config.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/tournament_simulation_service.py`
- Create: `backend/alembic/versions/0102_club_match_rewards.py`
- Test: `backend/tests/test_tournament_simulation_service.py`

**Interfaces:**
- Produces: `ClubBudgetTransactionType.tournament_match_reward`,
  `GameConfig.club_match_reward_win/draw/loss`. No other task consumes these directly, but
  Task 2 (admin UI) references the same field names.

- [ ] **Step 1: Add the enum member**

In `backend/app/models/enums.py`, `ClubBudgetTransactionType` currently ends:

```python
    club_penalty_reward = "club_penalty_reward"
    # Zero writers left anywhere in the codebase — ...
    coach_pack_purchase = "coach_pack_purchase"
```

Add the new member right after `club_penalty_reward`, before the `coach_pack_purchase` comment
block:

```python
    club_penalty_reward = "club_penalty_reward"
    tournament_match_reward = "tournament_match_reward"
    # Zero writers left anywhere in the codebase — ...
    coach_pack_purchase = "coach_pack_purchase"
```

- [ ] **Step 2: Add the three GameConfig fields**

In `backend/app/models/game_config.py`, find `club_tournament_budget_place_8` (the last of the
8 placement-reward fields) and add right after it:

```python
    club_tournament_budget_place_8: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    club_match_reward_win: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    club_match_reward_draw: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    club_match_reward_loss: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
```

- [ ] **Step 3: Add the admin schema fields**

In `backend/app/schemas/admin.py`, `GameConfigOut` has `club_tournament_budget_place_8: int`
right before `club_game_hourly_limit: int`. Add right after `club_tournament_budget_place_8`:

```python
    club_match_reward_win: int
    club_match_reward_draw: int
    club_match_reward_loss: int
```

Do the identical addition in `GameConfigUpdate` (right after its own
`club_tournament_budget_place_8: Optional[int] = Field(default=None, ge=0)`):

```python
    club_match_reward_win: Optional[int] = Field(default=None, ge=0)
    club_match_reward_draw: Optional[int] = Field(default=None, ge=0)
    club_match_reward_loss: Optional[int] = Field(default=None, ge=0)
```

- [ ] **Step 4: Write the migration**

Run `cd backend && alembic revision -m "club match rewards"` to get a fresh skeleton, then
replace its contents (confirm the real current head first via `alembic heads` — expected `0101`
at plan-authoring time, so this should land as `0102`; adjust if something else has landed):

```python
"""Per-match club budget rewards — ClubBudgetTransactionType.tournament_match_reward,
GameConfig.club_match_reward_win/draw/loss

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: Union[str, None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'tournament_match_reward'")

    op.add_column("game_config", sa.Column("club_match_reward_win", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("game_config", sa.Column("club_match_reward_draw", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("club_match_reward_loss", sa.Integer(), nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("game_config", "club_match_reward_loss")
    op.drop_column("game_config", "club_match_reward_draw")
    op.drop_column("game_config", "club_match_reward_win")
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
```

- [ ] **Step 5: Wire the reward into `simulate_next_round`**

In `backend/app/services/tournament_simulation_service.py`:

Add to the imports:

```python
from app.models.enums import ClubBudgetTransactionType, NotificationType, TournamentStatus
from app.services.club_budget_service import credit_club_budget
```

Change the per-tournament setup (currently builds only a name lookup) to keep the real `Club`
rows too:

```python
        clubs_by_id = {c.id: c for c in (await db.execute(select(Club).where(Club.id.in_(club_ids)))).scalars().all()}
        club_names = {cid: c.name for cid, c in clubs_by_id.items()}
```

In the real-match branch (after the existing `apply_match_result(standings_by_club[club_a_id],
standings_by_club[club_b_id], engine_result.score_a, engine_result.score_b)` call, and BEFORE
the `_decay_availability`/`_apply_engine_result` calls — order doesn't matter relative to those,
but keep it grouped with the standings update it logically belongs with), add:

```python
            from app.services.club_service import _lock_club

            club_a = await _lock_club(db, club_a_id)
            club_b = await _lock_club(db, club_b_id)
            if engine_result.score_a > engine_result.score_b:
                reward_a, reward_b = config.club_match_reward_win, config.club_match_reward_loss
            elif engine_result.score_a < engine_result.score_b:
                reward_a, reward_b = config.club_match_reward_loss, config.club_match_reward_win
            else:
                reward_a = reward_b = config.club_match_reward_draw
            await credit_club_budget(
                db, club_a, reward_a, ClubBudgetTransactionType.tournament_match_reward,
                f"Матч {round_number}-го тура турнира", related_object_type="tournament_match", related_object_id=tournament.id,
            )
            await credit_club_budget(
                db, club_b, reward_b, ClubBudgetTransactionType.tournament_match_reward,
                f"Матч {round_number}-го тура турнира", related_object_type="tournament_match", related_object_id=tournament.id,
            )
```

(The `from app.services.club_service import _lock_club` import is local/inline, matching this
exact file's own established convention for cross-service imports of module-private helpers —
see `club_service.py`'s `_disband_or_soft_disband` docstring for the precedent this mirrors.)

Do NOT add any reward in the withdrawn-club auto-loss branch above this one (the `if club_a_id
in withdrawn_ids or club_b_id in withdrawn_ids:` block) — that is not a real match.

- [ ] **Step 6: Write tests**

Add to `backend/tests/test_tournament_simulation_service.py`:

```python
async def test_simulate_next_round_credits_both_clubs_by_result(db_session, eight_club_tournament):
    from app.services.game_config_service import get_config

    tournament, _clubs_and_captains = eight_club_tournament
    config = await get_config(db_session)

    clubs_before = {}
    for club, _captain in _clubs_and_captains:
        await db_session.refresh(club)
        clubs_before[club.id] = club.budget

    matches = await simulate_next_round(db_session)
    await db_session.commit()

    round_1_matches = [m for m in matches if m.tournament_id == tournament.id]
    assert len(round_1_matches) == 4
    for m in round_1_matches:
        for club, _captain in _clubs_and_captains:
            if club.id not in (m.club_a_id, m.club_b_id):
                continue
            await db_session.refresh(club)
            my_score, opp_score = (m.score_a, m.score_b) if club.id == m.club_a_id else (m.score_b, m.score_a)
            expected_reward = (
                config.club_match_reward_win if my_score > opp_score
                else config.club_match_reward_loss if my_score < opp_score
                else config.club_match_reward_draw
            )
            assert club.budget == clubs_before[club.id] + expected_reward


async def test_simulate_next_round_does_not_reward_withdrawn_clubs(db_session, eight_club_tournament):
    from sqlalchemy import select as sa_select

    from app.models.club import Club as ClubModel
    from app.models.tournament import TournamentClub

    tournament, _clubs_and_captains = eight_club_tournament
    participants = (
        await db_session.execute(sa_select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))
    ).scalars().all()
    withdrawn = participants[0]
    withdrawn.is_withdrawn = True
    db_session.add(withdrawn)
    await db_session.commit()

    withdrawn_club = await db_session.get(ClubModel, withdrawn.club_id)
    budget_before = withdrawn_club.budget

    await simulate_next_round(db_session)
    await db_session.refresh(withdrawn_club)
    assert withdrawn_club.budget == budget_before
```

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/test_tournament_simulation_service.py -v` — both new tests plus all pre-existing ones in this file must pass.

- [ ] **Step 7: Verify against real Postgres**

Run: `docker compose exec backend alembic upgrade head`, confirm via `docker compose exec
postgres psql -U postgres -d footycards -c "SELECT enumlabel FROM pg_enum WHERE enumtypid =
'club_budget_transaction_type_enum'::regtype;"` that `tournament_match_reward` is present.
Confirm `\d game_config` shows the three new columns. Then `alembic downgrade -1` /
`alembic upgrade head` to confirm a clean round-trip.

- [ ] **Step 8: Full suite + commit**

Run the full backend suite (`docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest
football-cards-backend:latest tests/ -q`) — expect only the one pre-existing, unrelated failure
(`test_tasks.py::test_task_reward_pack_grants_all_cards`).

```bash
git add backend/app/models/enums.py backend/app/models/game_config.py backend/app/schemas/admin.py backend/app/services/tournament_simulation_service.py backend/alembic/versions/0102_club_match_rewards.py backend/tests/test_tournament_simulation_service.py
git commit -m "feat(club-tournament): credit both clubs' budgets per tournament match by result"
```

---

### Task 2: Frontend — admin UI for match rewards

**Files:**
- Modify: `frontend/src/admin/types.ts`
- Modify: `frontend/src/admin/pages/AdminGamesPage.tsx`

**Interfaces:**
- Consumes: `club_match_reward_win/draw/loss` (Task 1's `GameConfigOut`/`GameConfigUpdate`).

- [ ] **Step 1: Add the fields to `GameConfig`**

In `frontend/src/admin/types.ts`, find `club_tournament_budget_place_8: number;` and add right
after it:

```typescript
  club_match_reward_win: number;
  club_match_reward_draw: number;
  club_match_reward_loss: number;
```

- [ ] **Step 2: Add a new admin section**

In `frontend/src/admin/pages/AdminGamesPage.tsx`, add a new section right after the "Общие
лимиты" section (the one containing `club_tournament_budget_place_1..8`):

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Награда за матч турнира</p>
        <p className="mb-3 text-xs text-slate-500">Начисляется в бюджет клуба за каждый сыгранный матч тура — отдельно от награды за итоговое место.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_match_reward_win", "Награда за победу")}
          {field("club_match_reward_draw", "Награда за ничью")}
          {field("club_match_reward_loss", "Награда за поражение")}
        </div>
      </section>
```

- [ ] **Step 3: Typecheck + commit**

Run: `cd frontend && npm run typecheck` — expect PASS.

```bash
git add frontend/src/admin/types.ts frontend/src/admin/pages/AdminGamesPage.tsx
git commit -m "feat(club-tournament): add admin UI for per-match club reward config"
```

---

### Task 3: Frontend — fix the silent "Принять"/"Отклонить" bug

**Files:**
- Modify: `frontend/src/pages/ClubsPage.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Read the current mutations**

Confirmed root cause (verified this session): the backend's `respond_to_join_request` already
correctly rejects with a 409 (`"Игрок уже состоит в другом клубе"`) when the applicant joined a
different club first — it is not a backend bug. `acceptMutation`/`rejectMutation` in
`ClubsPage.tsx` are the only two mutations on this page with no `onError` handler, so that 409
(and any other failure) is silently swallowed: no banner, no console feedback, and since
`onSuccess`/`invalidate()` never runs, the stale request stays visibly sitting there looking
like the button did nothing. Every sibling mutation on this same page
(`leaveMutation`/`kickMutation`/`appointMutation`/`removeAssistantMutation`/`clubTypeMutation`)
already wires `onError: onActionError`, which sets the `actionError` state string rendered by the
existing banner right below the join-requests block.

- [ ] **Step 2: Fix it**

The current code:

```tsx
  const acceptMutation = useMutation({ mutationFn: (id: number) => acceptJoinRequest(id), onSuccess: invalidate });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectJoinRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "join-requests"] }),
  });
```

Replace with:

```tsx
  const acceptMutation = useMutation({ mutationFn: (id: number) => acceptJoinRequest(id), onSuccess: invalidate, onError: onActionError });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectJoinRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "join-requests"] }),
    onError: onActionError,
  });
```

Then find the two buttons that call these mutations:

```tsx
                <button onClick={() => acceptMutation.mutate(r.id)} className="rounded-lg bg-accent-green px-2 py-1 text-[11px] font-bold text-bg-base">
                  Принять
                </button>
                <button onClick={() => rejectMutation.mutate(r.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                  Отклонить
                </button>
```

Add `disabled` so a double-tap while the request is in flight can't fire it twice (matching
every other action button on this page, e.g. `kickMutation`'s own button already does this):

```tsx
                <button
                  onClick={() => acceptMutation.mutate(r.id)}
                  disabled={acceptMutation.isPending}
                  className="rounded-lg bg-accent-green px-2 py-1 text-[11px] font-bold text-bg-base disabled:opacity-50"
                >
                  Принять
                </button>
                <button
                  onClick={() => rejectMutation.mutate(r.id)}
                  disabled={rejectMutation.isPending}
                  className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400 disabled:opacity-50"
                >
                  Отклонить
                </button>
```

- [ ] **Step 3: Verify live**

Rebuild (`docker compose up -d --build frontend backend`). Reproduce the exact reported scenario:
as one dev-mode identity, apply to join club A; before club A's captain accepts, join (or get
accepted into) club B instead; then, as club A's captain, tap "Принять" on the now-stale
request. Confirm a red error banner now appears with a real message instead of nothing
happening, and that a normal accept (an applicant who hasn't joined anywhere else) still works
and removes the request from the list.

- [ ] **Step 4: Typecheck + commit**

Run: `cd frontend && npm run typecheck` — expect PASS.

```bash
git add frontend/src/pages/ClubsPage.tsx
git commit -m "fix(club-tournament): surface join-request accept/reject errors instead of swallowing them"
```

---

### Task 4: Assistant cap — raise to 4, hide the button once full

**Files:**
- Modify: `backend/app/services/club_service.py`
- Modify: `frontend/src/pages/ClubsPage.tsx`
- Test: `backend/tests/test_clubs.py`

**Interfaces:** none new — `MAX_ASSISTANTS` stays a plain constant, no `GameConfig` field (matches
`MAX_MEMBERS`'s own existing precedent right next to it).

- [ ] **Step 1: Raise the backend cap**

In `backend/app/services/club_service.py`:

```python
MAX_MEMBERS = 11
MAX_ASSISTANTS = 2
```

Change to:

```python
MAX_MEMBERS = 11
MAX_ASSISTANTS = 4
```

- [ ] **Step 2: Hide the button client-side once full**

In `frontend/src/pages/ClubsPage.tsx`, find the member-list render block. The button currently
shows unconditionally for every regular member when the viewer is captain:

```tsx
              {isCaptain && m.role === "member" && m.user_id !== userId && (
                <button
                  onClick={() => setConfirmMemberAction({ type: "appoint", userId: m.user_id, name: m.username ?? m.first_name ?? `#${m.user_id}` })}
                  className="rounded-lg bg-accent-lime/10 px-2 py-1 text-[11px] text-accent-lime"
                >
                  Назначить ассистентом
                </button>
              )}
```

Add a `MAX_ASSISTANTS` constant near the top of the file (mirrors the backend's own constant —
this file has no shared constants module to import it from, matching how this page already
hardcodes its own copies of small display-only constants elsewhere):

```typescript
const MAX_ASSISTANTS = 4;
```

Compute the current count once, right before the `club.members.map(...)` block (or wherever a
`const` can sit just above it — read the file to place it sensibly relative to the existing
`isCaptain`/`isManager` derivations):

```typescript
  const assistantCount = club.members.filter((m) => m.role === "assistant").length;
```

Then gate the button:

```tsx
              {isCaptain && m.role === "member" && m.user_id !== userId && assistantCount < MAX_ASSISTANTS && (
                <button
                  onClick={() => setConfirmMemberAction({ type: "appoint", userId: m.user_id, name: m.username ?? m.first_name ?? `#${m.user_id}` })}
                  className="rounded-lg bg-accent-lime/10 px-2 py-1 text-[11px] text-accent-lime"
                >
                  Назначить ассистентом
                </button>
              )}
```

- [ ] **Step 3: Write a backend test**

Add to `backend/tests/test_clubs.py` (read the file first for its own club-creation/join-request
helper conventions and mirror them exactly rather than guessing):

```python
async def test_up_to_four_assistants_can_be_appointed(client, db_session, bot_token):
    # Mirrors this file's own club-creation helper — captain + 4 members, all appointed
    # assistant, the 5th appointment attempt must be rejected.
    captain_headers = telegram_headers(870301, bot_token)
    await client.post("/api/v1/auth/session", headers=captain_headers)
    create_resp = await client.post(
        "/api/v1/clubs", headers=captain_headers,
        json={"name": "Ассистенты клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#00FF00"},
    )
    assert create_resp.status_code == 200
    club_id = create_resp.json()["id"]

    member_ids = []
    for i in range(5):
        headers = telegram_headers(870302 + i, bot_token)
        resp = await client.post("/api/v1/auth/session", headers=headers)
        member_ids.append(resp.json()["user"]["id"])
        join_resp = await client.post(f"/api/v1/clubs/{club_id}/join", headers=headers)
        assert join_resp.status_code == 200

    for user_id in member_ids[:4]:
        resp = await client.post(f"/api/v1/clubs/me/assistants/{user_id}/appoint", headers=captain_headers)
        assert resp.status_code == 200

    resp = await client.post(f"/api/v1/clubs/me/assistants/{member_ids[4]}/appoint", headers=captain_headers)
    assert resp.status_code == 409
```

- [ ] **Step 4: Full suite + typecheck + commit**

Run the full backend suite and `cd frontend && npm run typecheck` — expect the one pre-existing
backend failure and a clean frontend typecheck.

```bash
git add backend/app/services/club_service.py frontend/src/pages/ClubsPage.tsx backend/tests/test_clubs.py
git commit -m "feat(club-tournament): raise assistant cap to 4, hide the assign button once full"
```

---

### Task 5: Backend — training mechanic model + migration

**Files:**
- Modify: `backend/app/models/tournament_standing.py`
- Modify: `backend/app/models/game_config.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/tournament_queue_service.py`
- Create: `backend/alembic/versions/0103_club_training.py`

**Interfaces:**
- Produces: `TournamentClubStanding.training_uses_remaining` / `training_boost_round`,
  `GameConfig.club_training_boost_pct` / `club_training_uses_per_tournament`. Task 6 consumes
  all four by exact name.

- [ ] **Step 1: Add the two columns to `TournamentClubStanding`**

In `backend/app/models/tournament_standing.py`:

```python
class TournamentClubStanding(Base):
    __tablename__ = "tournament_club_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # "Тренировка состава" — a one-tour-only ~10% squad boost, up to
    # club_training_uses_per_tournament activations per tournament (set explicitly from
    # GameConfig at row-creation time in tournament_queue_service.apply_to_tournament, not from
    # this column's own Python default — see that function). Resets automatically every
    # tournament: this whole row is freshly created per (tournament, club), enforced by
    # uq_tournament_club_standings_once, so there is no separate "reset" code path.
    training_uses_remaining: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # The tournament round number this club's next-activated boost applies to, or NULL if no
    # boost is currently pending. Set to rounds_simulated+1 on activation; cleared back to NULL
    # the moment that round is actually simulated (tournament_simulation_service), whether or
    # not consumed — the boost never rolls over.
    training_boost_round: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_standings_once"),)
```

- [ ] **Step 2: Add the two GameConfig fields**

In `backend/app/models/game_config.py`, add right after the `club_match_reward_*` fields from
Task 1:

```python
    club_training_boost_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=0.10, nullable=False)
    club_training_uses_per_tournament: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
```

- [ ] **Step 3: Add the admin schema fields**

In `backend/app/schemas/admin.py`, add to `GameConfigOut` right after the `club_match_reward_*`
fields from Task 1:

```python
    club_training_boost_pct: float
    club_training_uses_per_tournament: int
```

And to `GameConfigUpdate`:

```python
    club_training_boost_pct: Optional[float] = Field(default=None, ge=0, le=1)
    club_training_uses_per_tournament: Optional[int] = Field(default=None, ge=0)
```

- [ ] **Step 4: Set `training_uses_remaining` from config at standing creation**

In `backend/app/services/tournament_queue_service.py`, `apply_to_tournament` already calls
`config = await get_config(db)` earlier in the function (for `club_tournament_cooldown_hours`).
The per-club loop currently reads:

```python
    for club_id in club_ids:
        db.add(TournamentClub(tournament_id=tournament.id, club_id=club_id))
        db.add(TournamentClubStanding(tournament_id=tournament.id, club_id=club_id))
        club_row = await db.get(Club, club_id)
        club_row.last_tournament_applied_at = datetime.now(timezone.utc)
        db.add(club_row)
```

Change the standing-creation line to pass the configured count explicitly:

```python
    for club_id in club_ids:
        db.add(TournamentClub(tournament_id=tournament.id, club_id=club_id))
        db.add(TournamentClubStanding(
            tournament_id=tournament.id, club_id=club_id,
            training_uses_remaining=config.club_training_uses_per_tournament,
        ))
        club_row = await db.get(Club, club_id)
        club_row.last_tournament_applied_at = datetime.now(timezone.utc)
        db.add(club_row)
```

- [ ] **Step 5: Write the migration**

Run `cd backend && alembic revision -m "club training"`, confirm real head (expected `0102` from
Task 1), replace contents:

```python
"""Club training mechanic — TournamentClubStanding.training_uses_remaining/training_boost_round,
GameConfig.club_training_boost_pct/club_training_uses_per_tournament

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: Union[str, None] = "0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tournament_club_standings", sa.Column("training_uses_remaining", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("tournament_club_standings", sa.Column("training_boost_round", sa.Integer(), nullable=True))

    op.add_column("game_config", sa.Column("club_training_boost_pct", sa.Numeric(4, 2), nullable=False, server_default="0.10"))
    op.add_column("game_config", sa.Column("club_training_uses_per_tournament", sa.Integer(), nullable=False, server_default="3"))


def downgrade() -> None:
    op.drop_column("game_config", "club_training_uses_per_tournament")
    op.drop_column("game_config", "club_training_boost_pct")
    op.drop_column("tournament_club_standings", "training_boost_round")
    op.drop_column("tournament_club_standings", "training_uses_remaining")
```

- [ ] **Step 6: Verify against real Postgres + full suite**

`docker compose exec backend alembic upgrade head`, confirm `\d tournament_club_standings` and
`\d game_config` show the new columns, round-trip downgrade/upgrade once. Run the full backend
suite — expect only the one pre-existing, unrelated failure.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/tournament_standing.py backend/app/models/game_config.py backend/app/schemas/admin.py backend/app/services/tournament_queue_service.py backend/alembic/versions/0103_club_training.py
git commit -m "feat(club-tournament): add training mechanic model fields, sourced from admin-tunable config"
```

---

### Task 6: Backend — training mechanic service, schema, router

**Files:**
- Modify: `backend/app/services/club_tactical_profile_service.py`
- Modify: `backend/app/services/club_tactical_matchup_service.py`
- Modify: `backend/app/services/club_squad_service.py`
- Modify: `backend/app/services/tournament_simulation_service.py`
- Modify: `backend/app/schemas/club_squad.py`
- Modify: `backend/app/routers/clubs.py`
- Test: `backend/tests/test_club_squad_service.py` (or wherever `club_squad_service` already has
  tests — read the test directory first to find the real file name; create
  `backend/tests/test_club_training.py` if no obviously-matching existing file exists)

**Interfaces:**
- Consumes: `TournamentClubStanding.training_uses_remaining`/`training_boost_round`,
  `GameConfig.club_training_boost_pct` (Task 5).
- Produces: `activate_training(db, user) -> ClubLineupOut`,
  `compute_profile(..., training_multiplier: float = 1.0)`,
  `build_side(..., training_multiplier: float = 1.0)`,
  `ClubLineupOut.training_uses_remaining/training_boost_active/in_active_tournament`. Task 7's
  frontend consumes the three new `ClubLineupOut` fields and the new router endpoint.

- [ ] **Step 1: Thread the multiplier through `compute_profile`**

In `backend/app/services/club_tactical_profile_service.py`, the current function:

```python
def compute_profile(cards_with_slots: list[tuple[Any, FormationSlot]], coach: "Coach | None" = None) -> TeamTacticalProfile:
    boosts = resolve_active_boosts(coach)
    depth_cap = depth_bonus_cap_for(DEPTH_BONUS_CAP, boosts)

    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        if weight_total > 0:
            base_avg = weighted_sum / weight_total
            depth_bonus = max(0.0, min(depth_cap, DEPTH_BONUS_SCALE * (weight_total - 1.0)))
            zone_values[zone] = round(min(99.0, base_avg + depth_bonus), 1)
        else:
            zone_values[zone] = 0.0

    zone_values = apply_zone_boosts(zone_values, boosts)
    zone_values = {zone: round(min(99.0, value), 1) for zone, value in zone_values.items()}

    return TeamTacticalProfile(team_strength=calculate_base_strength(cards_with_slots), **zone_values)
```

Change to:

```python
def compute_profile(
    cards_with_slots: list[tuple[Any, FormationSlot]], coach: "Coach | None" = None, training_multiplier: float = 1.0,
) -> TeamTacticalProfile:
    boosts = resolve_active_boosts(coach)
    depth_cap = depth_bonus_cap_for(DEPTH_BONUS_CAP, boosts)

    zone_values: dict[str, float] = {}
    for zone in ZONES:
        weighted_sum = 0.0
        weight_total = 0.0
        for card, _slot in cards_with_slots:
            weight = zone_weight(card.player.position, zone)
            if weight > 0:
                weighted_sum += card.player.rating * weight
                weight_total += weight
        if weight_total > 0:
            base_avg = weighted_sum / weight_total
            depth_bonus = max(0.0, min(depth_cap, DEPTH_BONUS_SCALE * (weight_total - 1.0)))
            zone_values[zone] = round(min(99.0, base_avg + depth_bonus), 1)
        else:
            zone_values[zone] = 0.0

    zone_values = apply_zone_boosts(zone_values, boosts)
    zone_values = {zone: round(min(99.0, value * training_multiplier), 1) for zone, value in zone_values.items()}

    return TeamTacticalProfile(
        team_strength=round(calculate_base_strength(cards_with_slots) * training_multiplier), **zone_values
    )
```

- [ ] **Step 2: Thread it through `build_side`**

In `backend/app/services/club_tactical_matchup_service.py`:

```python
def build_side(cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str, coach: "Coach | None" = None) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots, coach=coach)
```

Change to:

```python
def build_side(
    cards_with_slots: list[tuple[Any, Any]], mentality: str, playstyle: str,
    coach: "Coach | None" = None, training_multiplier: float = 1.0,
) -> ClubTacticalSide:
    profile = compute_profile(cards_with_slots, coach=coach, training_multiplier=training_multiplier)
```

- [ ] **Step 3: Write the training-state helper and `activate_training` in `club_squad_service.py`**

Read the current full file first (already partially read this session — re-read for exact,
current line numbers/imports before editing). Add near the top-level helpers (alongside
`_get_or_none_lineup`, `_club_card_to_out`, etc.):

```python
async def _training_state(db: AsyncSession, club_id: int, config) -> tuple[float, int, bool, bool]:
    """Returns (multiplier_to_apply_now, uses_remaining, boost_active_for_next_round,
    in_active_tournament). multiplier is 1.0 unless the club has an activated boost that
    targets its own upcoming round; uses_remaining/in_active_tournament are 0/False when the
    club isn't currently in an active tournament at all."""
    from app.models.enums import TournamentStatus
    from app.models.tournament import Tournament
    from app.models.tournament_standing import TournamentClubStanding

    row = (
        await db.execute(
            select(TournamentClubStanding, Tournament.rounds_simulated)
            .join(Tournament, Tournament.id == TournamentClubStanding.tournament_id)
            .where(TournamentClubStanding.club_id == club_id, Tournament.status == TournamentStatus.active)
        )
    ).first()
    if row is None:
        return 1.0, 0, False, False
    standing, rounds_simulated = row
    next_round = rounds_simulated + 1
    active = standing.training_boost_round == next_round
    multiplier = 1.0 + float(config.club_training_boost_pct) if active else 1.0
    return multiplier, standing.training_uses_remaining, active, True


async def activate_training(db: AsyncSession, user: User) -> ClubLineupOut:
    from app.models.enums import TournamentStatus
    from app.models.tournament import Tournament
    from app.models.tournament_standing import TournamentClubStanding
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    row = (
        await db.execute(
            select(TournamentClubStanding, Tournament)
            .join(Tournament, Tournament.id == TournamentClubStanding.tournament_id)
            .where(TournamentClubStanding.club_id == club_id, Tournament.status == TournamentStatus.active)
            .with_for_update(of=TournamentClubStanding)
        )
    ).first()
    if row is None:
        raise ConflictError("Клуб сейчас не участвует в турнире")
    standing, tournament = row
    next_round = tournament.rounds_simulated + 1

    if standing.training_boost_round == next_round:
        raise ConflictError("Тренировка уже активирована на следующий тур")
    if standing.training_uses_remaining <= 0:
        raise ConflictError("Тренировки на этот турнир закончились")

    standing.training_uses_remaining -= 1
    standing.training_boost_round = next_round
    db.add(standing)
    await db.commit()

    return await _lineup_to_out(db, club_id)
```

`with_for_update(of=TournamentClubStanding)` scopes the row lock to just that table — the same
established fix this codebase already applies everywhere a locked SELECT joins to another table
(`wallet_service.lock_user_for_update`, `club_squad_service`'s own existing locks elsewhere in
this file) — `Tournament` isn't locked here and doesn't need to be; only the standing row's
`training_uses_remaining`/`training_boost_round` are being mutated.

Confirm `ConflictError` is already imported in this file (it should be — used elsewhere in
`set_club_lineup`); confirm `select` is imported from `sqlalchemy` at the top.

- [ ] **Step 4: Wire `_lineup_to_out` to surface training state and apply the multiplier**

The current `_lineup_to_out`:

```python
    is_complete = len(cards_with_slots) == len(get_formation_slots(formation))
    team_strength = calculate_base_strength(cards_with_slots) if is_complete else None

    config = await get_config(db)
    profile = compute_profile(cards_with_slots) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0
    tactical_fit_hint = _tactical_fit_hint(profile, playstyle) if profile else "Заполни состав, чтобы увидеть подсказку"

    coach_out = None
    if lineup and lineup.club_coach_card:
        coach_out = EquippedCoachOut.model_validate(lineup.club_coach_card.coach)

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, tactical_fit_hint=tactical_fit_hint, slots=slots,
        coach=coach_out,
    )
```

Change to:

```python
    is_complete = len(cards_with_slots) == len(get_formation_slots(formation))

    config = await get_config(db)
    multiplier, training_uses_remaining, training_boost_active, in_active_tournament = await _training_state(db, club_id, config)

    team_strength = round(calculate_base_strength(cards_with_slots) * multiplier) if is_complete else None
    profile = compute_profile(cards_with_slots, training_multiplier=multiplier) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0
    tactical_fit_hint = _tactical_fit_hint(profile, playstyle) if profile else "Заполни состав, чтобы увидеть подсказку"

    coach_out = None
    if lineup and lineup.club_coach_card:
        coach_out = EquippedCoachOut.model_validate(lineup.club_coach_card.coach)

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, tactical_fit_hint=tactical_fit_hint, slots=slots,
        coach=coach_out, training_uses_remaining=training_uses_remaining,
        training_boost_active=training_boost_active, in_active_tournament=in_active_tournament,
    )
```

`_lineup_to_out(db, club_id)` already takes `club_id` as a parameter (confirm this from the
current signature — it does, per this session's own earlier reading of this file), so
`_training_state(db, club_id, config)` has everything it needs; no signature change to
`_lineup_to_out` itself is required.

**Do not touch** the other `compute_profile(opponent_cards_with_slots)` call site in this same
file (the opponent-preview path, inside `get_next_opponent` or similarly named) — it must keep
calling `compute_profile` with no `training_multiplier` argument at all (defaults to `1.0`), since
that call computes the OPPONENT's numbers, never the viewer's own club's training state.

- [ ] **Step 5: Add the schema fields**

In `backend/app/schemas/club_squad.py`, `ClubLineupOut` currently ends:

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
    coach: EquippedCoachOut | None = None
```

Add three fields:

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
    coach: EquippedCoachOut | None = None
    training_uses_remaining: int = 0
    training_boost_active: bool = False
    in_active_tournament: bool = False
```

- [ ] **Step 6: Apply and consume the boost in `simulate_next_round`**

In `backend/app/services/tournament_simulation_service.py`, the real-match branch currently
builds sides with no multiplier:

```python
            lineup_a, _had_sub_a, cards_with_slots_a, club_lineup_a = await resolve_match_lineup(db, club_a_id)
            lineup_b, _had_sub_b, cards_with_slots_b, club_lineup_b = await resolve_match_lineup(db, club_b_id)
            coach_a = club_lineup_a.club_coach_card.coach if club_lineup_a.club_coach_card else None
            coach_b = club_lineup_b.club_coach_card.coach if club_lineup_b.club_coach_card else None
            side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle, coach=coach_a)
            side_b = build_side(cards_with_slots_b, club_lineup_b.mentality, club_lineup_b.playstyle, coach=coach_b)
```

Change to:

```python
            lineup_a, _had_sub_a, cards_with_slots_a, club_lineup_a = await resolve_match_lineup(db, club_a_id)
            lineup_b, _had_sub_b, cards_with_slots_b, club_lineup_b = await resolve_match_lineup(db, club_b_id)
            coach_a = club_lineup_a.club_coach_card.coach if club_lineup_a.club_coach_card else None
            coach_b = club_lineup_b.club_coach_card.coach if club_lineup_b.club_coach_card else None

            config_boost_pct = float(config.club_training_boost_pct)
            standing_a, standing_b = standings_by_club[club_a_id], standings_by_club[club_b_id]
            multiplier_a = 1.0 + config_boost_pct if standing_a.training_boost_round == round_number else 1.0
            multiplier_b = 1.0 + config_boost_pct if standing_b.training_boost_round == round_number else 1.0

            side_a = build_side(cards_with_slots_a, club_lineup_a.mentality, club_lineup_a.playstyle, coach=coach_a, training_multiplier=multiplier_a)
            side_b = build_side(cards_with_slots_b, club_lineup_b.mentality, club_lineup_b.playstyle, coach=coach_b, training_multiplier=multiplier_b)
```

Right after `tournament.rounds_simulated = round_number` (near the end of the per-tournament
loop, before the `if round_number == 14:` block), clear the boost for every non-withdrawn
participant whose upcoming round just became this one — matching the Global Constraint that a
boost activated for a round is consumed the moment that round is simulated, regardless of
whether that specific club had a real match (in practice every non-withdrawn club does):

```python
        for standing in standings_by_club.values():
            if standing.training_boost_round == round_number:
                standing.training_boost_round = None
                db.add(standing)

        tournament.rounds_simulated = round_number
        db.add(tournament)
```

(Place the clearing loop immediately before the existing `tournament.rounds_simulated =
round_number` line, not after — order doesn't functionally matter here since both are in the
same uncommitted transaction, but keep the diff minimal and grouped with the round-closing
logic it belongs with.)

- [ ] **Step 7: Add the router endpoint**

In `backend/app/routers/clubs.py`, add right after the existing `set_club_coach` route:

```python
@router.post("/me/training", response_model=ClubLineupOut)
async def activate_club_training(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.activate_training(db, user)
```

No new schema import needed — `ClubLineupOut` is already imported in this file.

- [ ] **Step 8: Write tests**

Find the real test file for `club_squad_service`/club lineup endpoints (search
`backend/tests/` for `set_club_lineup`/`get_club_lineup` call sites to find it — do not assume a
filename). Add tests there, or create `backend/tests/test_club_training.py` if nothing existing
fits, mirroring `test_tournament_simulation_service.py`'s `eight_club_tournament` fixture
pattern (import it or recreate an equivalent local fixture per this codebase's own
per-file-fixture convention):

```python
async def test_activate_training_requires_manager(db_session, eight_club_tournament):
    import pytest
    from sqlalchemy import select

    from app.core.exceptions import ForbiddenError
    from app.models.club import ClubMember
    from app.models.user import User
    from app.services.club_squad_service import activate_training

    tournament, clubs_and_captains = eight_club_tournament
    club, captain = clubs_and_captains[0]

    # eight_club_tournament's own fixture (test_tournament_simulation_service.py) always adds a
    # second, plain member to every club — no new member needs creating here.
    other_membership = (
        await db_session.execute(
            select(ClubMember).where(ClubMember.club_id == club.id, ClubMember.user_id != captain.id)
        )
    ).scalar_one()
    assert other_membership.role.value == "member"
    plain_member = await db_session.get(User, other_membership.user_id)

    with pytest.raises(ForbiddenError):
        await activate_training(db_session, plain_member)


async def test_activate_training_boosts_exactly_the_next_round_and_is_consumed(db_session, eight_club_tournament):
    from app.models.tournament_standing import TournamentClubStanding
    from app.services.club_squad_service import activate_training, get_club_lineup
    from app.services.tournament_simulation_service import simulate_next_round
    from sqlalchemy import select

    tournament, clubs_and_captains = eight_club_tournament
    club, captain = clubs_and_captains[0]

    lineup_before = await get_club_lineup(db_session, captain)
    assert lineup_before.training_uses_remaining == 3
    assert lineup_before.training_boost_active is False

    boosted = await activate_training(db_session, captain)
    assert boosted.training_uses_remaining == 2
    assert boosted.training_boost_active is True
    assert boosted.team_strength > lineup_before.team_strength

    # Re-activating for the same still-upcoming round must be rejected.
    from app.core.exceptions import ConflictError
    import pytest
    with pytest.raises(ConflictError):
        await activate_training(db_session, captain)

    await simulate_next_round(db_session)
    await db_session.commit()

    standing = (
        await db_session.execute(
            select(TournamentClubStanding).where(
                TournamentClubStanding.tournament_id == tournament.id, TournamentClubStanding.club_id == club.id,
            )
        )
    ).scalar_one()
    assert standing.training_boost_round is None  # consumed, even though only 1 round was simulated

    lineup_after = await get_club_lineup(db_session, captain)
    assert lineup_after.training_boost_active is False
```

Run the new/updated test file(s), then the full backend suite — expect only the one
pre-existing, unrelated failure.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/club_tactical_profile_service.py backend/app/services/club_tactical_matchup_service.py backend/app/services/club_squad_service.py backend/app/services/tournament_simulation_service.py backend/app/schemas/club_squad.py backend/app/routers/clubs.py backend/tests/
git commit -m "feat(club-tournament): add training mechanic — 3 uses/tournament, +10% for exactly the next round"
```

---

### Task 7: Frontend — training mechanic UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/clubSquad.ts`
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Consumes: `POST /clubs/me/training` (Task 6), `ClubLineupOut.training_uses_remaining/
  training_boost_active/in_active_tournament`.

- [ ] **Step 1: Add the type fields**

In `frontend/src/types/index.ts`, `ClubLineup` currently ends:

```typescript
export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  tactical_fit_hint: string;
  coach: EquippedCoach | null;
  slots: ClubLineupSlot[];
}
```

Add three fields:

```typescript
export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  tactical_fit_hint: string;
  coach: EquippedCoach | null;
  slots: ClubLineupSlot[];
  training_uses_remaining: number;
  training_boost_active: boolean;
  in_active_tournament: boolean;
}
```

- [ ] **Step 2: Add the API function**

In `frontend/src/api/clubSquad.ts`, add:

```typescript
export async function activateClubTraining(): Promise<ClubLineup> {
  const { data } = await api.post<ClubLineup>("/clubs/me/training");
  return data;
}
```

(`ClubLineup` is already imported in this file from `@/types` for the other lineup functions —
no new import needed.)

- [ ] **Step 3: Add the button + state to `ClubSquadPage.tsx`**

Read the current full file first (already partially read this session). Add the mutation near
the existing `setLineupMutation`/`setTacticsMutation`-style mutations:

```typescript
  const trainingMutation = useMutation({
    mutationFn: activateClubTraining,
    onSuccess: (data) => queryClient.setQueryData(["clubs", "me", "lineup"], data),
    onError: (err) => setLineupError(formatGameError(err, "Не удалось активировать тренировку")),
  });
```

(Match the exact query key this page already uses for the lineup query — read the existing
`useQuery({ queryKey: [...], queryFn: fetchClubLineup })` call in this file and use that SAME
key array in `setQueryData` above; `["clubs", "me", "lineup"]` above is illustrative, not
guaranteed to match — verify and correct if the real key differs. Also confirm `formatGameError`
and a `setLineupError`-style error-state setter already exist in this file, matching its
existing error-handling convention for other mutations here — reuse them rather than inventing a
new one.)

Add `activateClubTraining` to this file's import from `@/api/clubSquad`.

Render the button somewhere sensible near the squad header/team-strength display (only when
`lineup?.in_active_tournament` is true — otherwise the training concept doesn't apply at all
right now and showing it would be confusing):

```tsx
{lineup?.in_active_tournament && (
  <button
    onClick={() => trainingMutation.mutate()}
    disabled={trainingMutation.isPending || lineup.training_boost_active || lineup.training_uses_remaining <= 0}
    className={`flex items-center justify-center gap-1.5 rounded-2xl px-3 py-2 text-xs font-bold active:scale-95 disabled:opacity-50 ${
      lineup.training_boost_active ? "bg-accent-green/20 text-accent-green" : "bg-accent-lime/10 text-accent-lime"
    }`}
  >
    {lineup.training_boost_active
      ? "Тренировка активна на след. тур ✓"
      : lineup.training_uses_remaining > 0
        ? `Тренировка состава (${lineup.training_uses_remaining} ост.)`
        : "Тренировки закончились"}
  </button>
)}
```

Place this in the JSX wherever the squad header (team strength / tactical fit area) already
lives in this file — read the surrounding structure and put it in a spot that doesn't disrupt
the existing layout, e.g. right below the team-strength display. Use whatever this page's own
existing button/card styling convention is for anything not explicitly specified above (rounded
corners, spacing) rather than inventing new classes wholesale — match the file's own look.

- [ ] **Step 4: Verify live**

Rebuild. As a club captain whose club is in an active tournament, open the squad page, confirm
the training button shows with "3 ост.", tap it, confirm team strength visibly increases (~10%)
and the button switches to the "active" state, confirm a second tap is rejected (button already
disabled, but also verify the backend 409 path doesn't crash anything if forced). Trigger a round
simulation (via whatever admin/dev mechanism this repo already uses for testing tournament
rounds — check `docs/superpowers/plans/2026-08-30-club-tactical-match-engine-phase1.md` /
`2026-09-07-club-tactical-match-engine-phase2.md` or the bot's internal endpoint for how this was
tested during those plans) and confirm the boost clears and strength returns to its unboosted
value afterward.

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npm run typecheck` — expect PASS.

```bash
git add frontend/src/types/index.ts frontend/src/api/clubSquad.ts frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(club-tournament): add Тренировка состава button to the club squad page"
```

---

### Task 8: Backend — red card/injury `reason` tracking + probability config

**Files:**
- Modify: `backend/app/models/enums.py`
- Modify: `backend/app/models/club_card_availability.py`
- Modify: `backend/app/models/game_config.py`
- Modify: `backend/app/schemas/admin.py`
- Modify: `backend/app/services/tournament_match_engine.py`
- Modify: `backend/app/services/tournament_simulation_service.py`
- Create: `backend/alembic/versions/0104_club_card_availability_reason.py`

**Interfaces:**
- Produces: `ClubCardAvailabilityReason` enum, `ClubCardAvailability.reason`,
  `GameConfig.club_tactical_tackle_attempt_chance`/`club_tactical_injury_chance`. Task 9
  consumes `ClubCardAvailability.reason` by exact name.

- [ ] **Step 1: Add the reason enum**

In `backend/app/models/enums.py`, add near `ClubRole`/`TournamentStatus` (any sensible nearby
spot — this file groups related enums loosely, not strictly alphabetically):

```python
class ClubCardAvailabilityReason(str, enum.Enum):
    red_card = "red_card"
    injury = "injury"
```

- [ ] **Step 2: Add the column to the model**

In `backend/app/models/club_card_availability.py`:

```python
from sqlalchemy import Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ClubCardAvailabilityReason


class ClubCardAvailability(Base):
    """A row only exists while a ClubCard is actually suspended
    (rounds_remaining > 0). Absence of a row = available. Delete the row
    once rounds_remaining reaches 0 rather than keeping it at 0."""

    __tablename__ = "club_card_availabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), unique=True, nullable=False)
    rounds_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[ClubCardAvailabilityReason] = mapped_column(
        Enum(ClubCardAvailabilityReason, name="club_card_availability_reason_enum"), nullable=False,
    )
```

- [ ] **Step 3: Add the two GameConfig probability fields**

In `backend/app/models/game_config.py`, add right after `club_tactical_fit_mentality_weight`
(the existing club-tactical config cluster):

```python
    club_tactical_tackle_attempt_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.20, nullable=False)
    club_tactical_injury_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.35, nullable=False)
```

(Was `0.15` and `0.3` as hardcoded literals before this task — this is the "slightly increase
the chance" the user asked for, applied only to the club tournament engine, per this plan's
Global Constraints — the SHARED `match_tackle_foul_chance_min/max`/`match_tackle_red_chance_min/
max` fields stay completely untouched.)

- [ ] **Step 4: Add the admin schema fields**

In `backend/app/schemas/admin.py`, add to `GameConfigOut` near `club_tactical_fit_mentality_weight`:

```python
    club_tactical_tackle_attempt_chance: float
    club_tactical_injury_chance: float
```

And to `GameConfigUpdate`:

```python
    club_tactical_tackle_attempt_chance: Optional[float] = Field(default=None, ge=0, le=1)
    club_tactical_injury_chance: Optional[float] = Field(default=None, ge=0, le=1)
```

- [ ] **Step 5: Use the config values in the match engine**

In `backend/app/services/tournament_match_engine.py`, `simulate_match`'s current tail:

```python
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
```

Change the two literals to read from `config`:

```python
        if event["event_type"] in ("blocked", "save") and random.random() < float(config.club_tactical_tackle_attempt_chance):
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            defense_event["description"] = _describe_event(defense_event["event_type"], defense_event["team"], club_a_name, club_b_name)
            if defense_scorer != "none":
                setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
            if card is not None:
                club_card_id, card_kind = card
                if card_kind == "red":
                    result.red_cards.append((club_card_id, 1))
                    if random.random() < float(config.club_tactical_injury_chance):
                        result.injuries.append((club_card_id, random.randint(1, 3)))
```

- [ ] **Step 6: Record `reason` in `_apply_engine_result`**

In `backend/app/services/tournament_simulation_service.py`, the current function:

```python
async def _apply_engine_result(db: AsyncSession, engine_result: "tournament_match_engine.MatchResult") -> None:
    """..."""
    for club_card_id, rounds in [*engine_result.red_cards, *engine_result.injuries]:
        existing = (
            await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))
        ).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            db.add(existing)
```

Change to process the two lists separately (so a card that gets both ends up with
`reason="injury"` — the injuries loop runs second and always overwrites `reason`, per this
plan's Global Constraint on which label wins when both occur):

```python
async def _apply_engine_result(db: AsyncSession, engine_result: "tournament_match_engine.MatchResult") -> None:
    """Persists the new suspensions this match itself produced (injuries:
    1-3 future rounds; red cards: next round only). Must run AFTER
    _decay_availability for both clubs in the same round — a suspension
    minted by this match must still hold for the *next* round, not be
    decremented to 0 in the very round it was earned. A club_card_id that
    picked up both a red card and its associated injury roll in the same
    match keeps the longer of the two (max) rounds_remaining, and ends up
    labeled reason=injury — the more informative outcome, since the two
    loops below process red_cards first, injuries second, and injuries can
    only ever fire as a bonus on top of an existing red card, never alone."""
    from app.models.enums import ClubCardAvailabilityReason

    for club_card_id, rounds in engine_result.red_cards:
        existing = (
            await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))
        ).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds, reason=ClubCardAvailabilityReason.red_card))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            existing.reason = ClubCardAvailabilityReason.red_card
            db.add(existing)

    for club_card_id, rounds in engine_result.injuries:
        existing = (
            await db.execute(select(ClubCardAvailability).where(ClubCardAvailability.club_card_id == club_card_id))
        ).scalar_one_or_none()
        if existing is None:
            db.add(ClubCardAvailability(club_card_id=club_card_id, rounds_remaining=rounds, reason=ClubCardAvailabilityReason.injury))
        else:
            existing.rounds_remaining = max(existing.rounds_remaining, rounds)
            existing.reason = ClubCardAvailabilityReason.injury
            db.add(existing)
```

- [ ] **Step 7: Write the migration**

Run `cd backend && alembic revision -m "club card availability reason"`, confirm real head
(expected `0103` from Task 5), replace contents:

```python
"""ClubCardAvailability.reason (red_card/injury) + club-tactical tackle/injury chance config,
replacing two previously-hardcoded probability literals

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0104"
down_revision: Union[str, None] = "0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    reason_enum = sa.Enum("red_card", "injury", name="club_card_availability_reason_enum")
    reason_enum.create(bind, checkfirst=True)
    op.add_column(
        "club_card_availabilities",
        sa.Column(
            "reason",
            sa.Enum("red_card", "injury", name="club_card_availability_reason_enum", create_type=False),
            nullable=False, server_default="red_card",
        ),
    )

    op.add_column("game_config", sa.Column("club_tactical_tackle_attempt_chance", sa.Numeric(4, 2), nullable=False, server_default="0.20"))
    op.add_column("game_config", sa.Column("club_tactical_injury_chance", sa.Numeric(4, 2), nullable=False, server_default="0.35"))


def downgrade() -> None:
    op.drop_column("game_config", "club_tactical_injury_chance")
    op.drop_column("game_config", "club_tactical_tackle_attempt_chance")
    op.drop_column("club_card_availabilities", "reason")
    sa.Enum(name="club_card_availability_reason_enum").drop(op.get_bind(), checkfirst=True)
```

The explicit `reason_enum.create(bind, checkfirst=True)` before `op.add_column` (rather than
relying on `add_column` to auto-create a brand-new enum type) is deliberate — this repo has no
established precedent either way for a new enum type added via `add_column` (only via
`create_table`, which is documented to auto-create), so this plan takes the explicit, unambiguous
path rather than assuming implicit behavior.

- [ ] **Step 8: Verify against real Postgres + full suite**

`docker compose exec backend alembic upgrade head`, confirm `\d club_card_availabilities` shows
`reason` as `club_card_availability_reason_enum NOT NULL`, confirm `\d game_config` shows the two
new columns. Round-trip downgrade/upgrade once — this one is worth verifying carefully given the
custom enum-type create/drop dance; confirm the type is genuinely gone after downgrade (`SELECT
* FROM pg_type WHERE typname = 'club_card_availability_reason_enum'` returns 0 rows) and
correctly recreated after the next upgrade.

Run the full backend suite — expect only the one pre-existing, unrelated failure. Any existing
test that constructs a `ClubCardAvailability` row directly (grep `backend/tests/` for
`ClubCardAvailability(` to find them) will now fail if it doesn't pass `reason=` — fix each one
by adding `reason=ClubCardAvailabilityReason.red_card` (or `.injury` if the test's own narrative
is about an injury specifically — read each call site's surrounding test to judge which fits,
don't default all of them to red_card blindly).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/enums.py backend/app/models/club_card_availability.py backend/app/models/game_config.py backend/app/schemas/admin.py backend/app/services/tournament_match_engine.py backend/app/services/tournament_simulation_service.py backend/alembic/versions/0104_club_card_availability_reason.py backend/tests/
git commit -m "feat(club-tournament): track red-card-vs-injury reason, raise club tactical suspension odds slightly"
```

---

### Task 9: Backend — surface availability in the squad API + rewrite the notification

**Files:**
- Modify: `backend/app/schemas/club_squad.py`
- Modify: `backend/app/services/club_squad_service.py`
- Modify: `backend/app/services/tournament_notification_service.py`
- Test: `backend/tests/test_tournament_simulation_service.py` or a dedicated notification test
  file (search `backend/tests/` for existing `tournament_notification_service`/
  `send_lineup_reminders` test coverage first — extend it if found, create
  `backend/tests/test_tournament_notification_service.py` if not)

**Interfaces:**
- Consumes: `ClubCardAvailability.reason` (Task 8).
- Produces: `ClubCardOut.availability`. Task 11's frontend consumes this field by exact name.

- [ ] **Step 1: Add the schema field**

In `backend/app/schemas/club_squad.py`, add above `ClubCardOut`:

```python
class ClubCardAvailabilityOut(BaseModel):
    reason: str
    rounds_remaining: int
```

Add the field to `ClubCardOut`:

```python
class ClubCardOut(BaseModel):
    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    is_in_lineup: bool
    availability: ClubCardAvailabilityOut | None = None
```

- [ ] **Step 2: Thread availability data through `_club_card_to_out`**

In `backend/app/services/club_squad_service.py`, add a helper near the other private helpers:

```python
async def _availability_by_card_id(db: AsyncSession, club_id: int) -> dict[int, "ClubCardAvailability"]:
    from app.models.club_card_availability import ClubCardAvailability

    rows = (
        await db.execute(
            select(ClubCardAvailability)
            .join(ClubCard, ClubCard.id == ClubCardAvailability.club_card_id)
            .where(ClubCard.club_id == club_id, ClubCardAvailability.rounds_remaining > 0)
        )
    ).scalars().all()
    return {row.club_card_id: row for row in rows}
```

Change `_club_card_to_out`'s current signature and body:

```python
def _club_card_to_out(card: ClubCard, in_lineup_ids: set[int]) -> ClubCardOut:
    return ClubCardOut(
        id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
        acquired_at=card.acquired_at, is_in_lineup=card.id in in_lineup_ids,
    )
```

to:

```python
def _club_card_to_out(
    card: ClubCard, in_lineup_ids: set[int], availability_by_card_id: dict[int, "ClubCardAvailability"] | None = None,
) -> ClubCardOut:
    availability = (availability_by_card_id or {}).get(card.id)
    return ClubCardOut(
        id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
        acquired_at=card.acquired_at, is_in_lineup=card.id in in_lineup_ids,
        availability=ClubCardAvailabilityOut(reason=availability.reason.value, rounds_remaining=availability.rounds_remaining) if availability else None,
    )
```

(`availability_by_card_id` defaults to `None`/treated as empty so any OTHER existing caller of
`_club_card_to_out` this task's own search doesn't find — grep to be sure there are only the two
described below — keeps working unchanged.)

Update `list_club_cards`:

```python
async def list_club_cards(db: AsyncSession, user: User) -> list[ClubCardOut]:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    cards = (await db.execute(select(ClubCard).where(ClubCard.club_id == membership.club_id).order_by(ClubCard.acquired_at))).scalars().all()
    lineup = await _get_or_none_lineup(db, membership.club_id)
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()
    availability_by_card_id = await _availability_by_card_id(db, membership.club_id)
    return [_club_card_to_out(c, in_lineup_ids, availability_by_card_id) for c in cards]
```

Update `_lineup_to_out`'s slot-building loop — the current:

```python
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
```

to:

```python
    availability_by_card_id = await _availability_by_card_id(db, club_id)
    slots = []
    cards_with_slots = []
    for slot in get_formation_slots(formation):
        card = by_slot.get(slot.code)
        slots.append(
            ClubLineupSlotOut(
                slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
                card=_club_card_to_out(card, in_lineup_ids, availability_by_card_id) if card else None,
            )
        )
        if card:
            cards_with_slots.append((card, slot))
```

Import `ClubCardAvailabilityOut` in this file's existing import from `app.schemas.club_squad`.

- [ ] **Step 3: Rewrite the notification to name names**

In `backend/app/services/tournament_notification_service.py`, replace `_club_has_suspended_starter`:

```python
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
```

with:

```python
async def _suspended_starters(db: AsyncSession, club_id: int) -> list[tuple[str, "ClubCardAvailabilityReason", int]]:
    """Read-only check — does NOT call resolve_match_lineup (Task 12),
    which also performs substitution and returns engine-shaped actor
    dicts neither needed nor wanted for a preview check. Returns
    (player_display_name, reason, rounds_remaining) for every starter
    currently suspended, so the reminder can name names instead of a
    generic "someone" — previously this only returned a boolean."""
    from app.models.player import Player
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return []
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}
    if not lineup_card_ids:
        return []
    rows = (
        await db.execute(
            select(ClubCardAvailability.reason, ClubCardAvailability.rounds_remaining, Player.display_name)
            .join(ClubCard, ClubCard.id == ClubCardAvailability.club_card_id)
            .join(Player, Player.id == ClubCard.player_id)
            .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
        )
    ).all()
    return [(name, reason, rounds) for reason, rounds, name in rows]
```

Update `send_lineup_reminders`'s inner loop — the current:

```python
            for club_id in (club_a_id, club_b_id):
                if await _club_has_suspended_starter(db, club_id):
                    await notify_club_members(
                        db, club_id, NotificationType.club_lineup_reminder,
                        "Кто-то из состава не сыграет",
                        "В стартовом составе клуба есть игрок под дисквалификацией — проверь состав перед следующим туром турнира.",
                    )
                    notified_count += 1
```

to:

```python
            for club_id in (club_a_id, club_b_id):
                suspended = await _suspended_starters(db, club_id)
                if suspended:
                    from app.models.enums import ClubCardAvailabilityReason

                    parts = []
                    for name, reason, rounds in suspended:
                        reason_label = "красная карточка" if reason == ClubCardAvailabilityReason.red_card else "травма"
                        tour_word = "тур" if rounds == 1 else "тура"
                        parts.append(f"{name} — {reason_label} ({rounds} {tour_word})")
                    await notify_club_members(
                        db, club_id, NotificationType.club_lineup_reminder,
                        "Кто-то из состава не сыграет",
                        f"Перед следующим туром замени в составе: {'; '.join(parts)}.",
                    )
                    notified_count += 1
```

Add `from app.models.enums import ClubCardAvailabilityReason` to this file's top-level imports
instead of the inline import shown above, if you prefer — either works, match this file's own
existing style for where it places its imports (it already has several function-local imports
for cross-module references, e.g. inside `_club_has_suspended_starter`/now `_suspended_starters`
itself, so an inline import here is consistent, but a top-level one is equally fine — your call).

- [ ] **Step 4: Write/extend tests**

Add (to whichever file you found/created in this task's own file list):

```python
async def test_lineup_reminder_names_the_player_and_reason(db_session, eight_club_tournament):
    from sqlalchemy import select

    from app.models.club_card import ClubCard
    from app.models.club_card_availability import ClubCardAvailability
    from app.models.club_lineup import ClubLineupCard
    from app.models.enums import ClubCardAvailabilityReason, NotificationType
    from app.models.notification import Notification
    from app.services.tournament_notification_service import send_lineup_reminders

    tournament, clubs_and_captains = eight_club_tournament
    club, _captain = clubs_and_captains[0]

    lineup_card = (
        await db_session.execute(select(ClubLineupCard).join(ClubCard, ClubCard.id == ClubLineupCard.club_card_id).where(ClubCard.club_id == club.id).limit(1))
    ).scalar_one()
    starter = await db_session.get(ClubCard, lineup_card.club_card_id)
    db_session.add(ClubCardAvailability(club_card_id=starter.id, rounds_remaining=2, reason=ClubCardAvailabilityReason.injury))
    await db_session.commit()

    count = await send_lineup_reminders(db_session)
    assert count > 0

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_lineup_reminder))
    ).scalars().all()
    assert notifications
    bodies = [n.body for n in notifications]
    assert any("травма" in b and "2 тура" in b for b in bodies)
```

Run this file plus the full backend suite — expect only the one pre-existing, unrelated failure.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/club_squad.py backend/app/services/club_squad_service.py backend/app/services/tournament_notification_service.py backend/tests/
git commit -m "feat(club-tournament): name the player, reason, and duration in lineup-gap notifications and the squad API"
```

---

### Task 10: Frontend — admin UI for club-tactical suspension probabilities

**Files:**
- Modify: `frontend/src/admin/types.ts`
- Modify: `frontend/src/admin/pages/AdminGamesPage.tsx`

**Interfaces:**
- Consumes: `club_tactical_tackle_attempt_chance`/`club_tactical_injury_chance` (Task 8's
  `GameConfigOut`/`GameConfigUpdate`).

- [ ] **Step 1: Add the fields to `GameConfig`**

In `frontend/src/admin/types.ts`, add near wherever `club_tournament_budget_place_8` (or the
Task 2/5 fields you already added right after it) end:

```typescript
  club_tactical_tackle_attempt_chance: number;
  club_tactical_injury_chance: number;
```

- [ ] **Step 2: Add the fields to the admin page**

In `frontend/src/admin/pages/AdminGamesPage.tsx`, add a new section (or extend the "Награда за
матч турнира" section from Task 2 if you'd rather keep club-tournament-tactical config together
— either is fine, pick whichever reads more naturally once you see the current file state):

```tsx
      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Красные карточки и травмы (клубный турнир)</p>
        <p className="mb-3 text-xs text-slate-500">Влияет только на клубные турнирные матчи — на Card Arena не распространяется.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_tactical_tackle_attempt_chance", "Шанс попытки подката (0-1)")}
          {field("club_tactical_injury_chance", "Шанс травмы при красной (0-1)")}
        </div>
      </section>
```

- [ ] **Step 3: Typecheck + commit**

Run: `cd frontend && npm run typecheck` — expect PASS.

```bash
git add frontend/src/admin/types.ts frontend/src/admin/pages/AdminGamesPage.tsx
git commit -m "feat(club-tournament): add admin UI for club-tactical tackle/injury probability config"
```

---

### Task 11: Frontend — squad-page visual badges for red cards/injuries

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/ClubSquadPage.tsx`

**Interfaces:**
- Consumes: `ClubCardOut.availability` (Task 9) via `ClubCard.availability`.

- [ ] **Step 1: Add the type field**

In `frontend/src/types/index.ts`, add above `ClubCard`:

```typescript
export interface ClubCardAvailability {
  reason: "red_card" | "injury";
  rounds_remaining: number;
}
```

Add the field to `ClubCard`:

```typescript
export interface ClubCard {
  id: number;
  serial_number: number;
  player: Player;
  acquired_at: string;
  is_in_lineup: boolean;
  availability: ClubCardAvailability | null;
}
```

- [ ] **Step 2: Render the badges**

In `frontend/src/pages/ClubSquadPage.tsx`, the current per-slot card rendering:

```tsx
                    {slot.card ? (
                      <>
                        <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                          <img
                            src={staticUrl(slot.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">{slot.card.player.position}</span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.card.player.rating}</span>
                      </>
                    ) : (
```

Change to:

```tsx
                    {slot.card ? (
                      <>
                        <div className={`relative aspect-square w-full overflow-hidden rounded-lg bg-black/40 ${
                          slot.card.availability ? "ring-2 ring-red-500" : ""
                        }`}>
                          <img
                            src={staticUrl(slot.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                          {slot.card.availability && (
                            <span className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-sm bg-red-600 text-[10px] font-black leading-none text-white">
                              {slot.card.availability.reason === "red_card" ? "▮" : "+"}
                            </span>
                          )}
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">{slot.card.player.position}</span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.card.player.rating}</span>
                        {slot.card.availability && (
                          <span className="text-center font-mono text-[8px] font-bold leading-tight text-red-400">
                            {slot.card.availability.reason === "red_card" ? "Диск." : "Травма"} · {slot.card.availability.rounds_remaining}т
                          </span>
                        )}
                      </>
                    ) : (
```

The red rectangle (`▮`, a filled-block glyph) for a red card and `+` (a plain cross/plus glyph)
for an injury are plain text characters styled inside a small red badge — no new icon component
needed; this matches how several other pages in this codebase already render small glyph badges
as styled text rather than importing a dedicated icon for every single case.

- [ ] **Step 3: Verify live**

Rebuild. Directly insert a `ClubCardAvailability` row for a real starter's `club_card_id` via
`docker compose exec postgres psql` (one row with `reason='red_card', rounds_remaining=1`, one
with `reason='injury', rounds_remaining=2`, on two different clubs' squads if convenient) and
confirm the squad page shows: a red ring around the card image, the correct badge glyph in the
corner, and the "Диск. · 1т" / "Травма · 2т" label beneath the rating. Clean up the inserted
rows afterward (`DELETE FROM club_card_availabilities WHERE id IN (...)`).

- [ ] **Step 4: Typecheck + commit**

Run: `cd frontend && npm run typecheck` — expect PASS.

```bash
git add frontend/src/types/index.ts frontend/src/pages/ClubSquadPage.tsx
git commit -m "feat(club-tournament): show red card/injury badges and recovery countdown on the squad page"
```

---

### Task 12: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint pytest football-cards-backend:latest tests/ -q`

Expected: all pass except the one pre-existing, already-flagged, unrelated failure
(`test_tasks.py::test_task_reward_pack_grants_all_cards`).

- [ ] **Step 2: Run the full frontend typecheck and lint**

Run: `cd frontend && npm run typecheck` — expect PASS.
Run: `cd frontend && npm run lint` — expect only the known, pre-existing
`eslint.config.js`-missing failure.

- [ ] **Step 3: Verify the migration chain**

Run: `docker run --rm -v "$(pwd)/backend:/app" --entrypoint alembic football-cards-backend:latest history`
— confirm `0102`, `0103`, `0104` all appear in order after `0101`, `0104` is head, no branching.
Confirm `docker compose exec backend alembic current` reports the same on the live dev Postgres.

- [ ] **Step 4: Live-verify all five features end to end**

Rebuild (`docker compose up -d --build frontend backend`). Using a real (or dev-mode-simulated)
8-club tournament already in progress:

1. **Match rewards**: note both clubs' budgets before a round, trigger a round simulation,
   confirm each club's budget increased by exactly the configured win/draw/loss amount, and that
   `GET /clubs/{id}` (or wherever budget is shown) reflects it.
2. **Accept/reject bug**: reproduce the exact reported scenario (applicant joins a different club
   before being accepted) and confirm the captain now sees a real error message instead of
   nothing happening.
3. **Assistant cap**: appoint 4 assistants in one club, confirm the "Назначить ассистентом"
   button disappears for the remaining regular members, confirm a 5th appointment attempt (if
   forced via direct API call) still 409s server-side too.
4. **Training**: activate it, confirm the squad's team strength and tactical numbers visibly rise
   (~10%), confirm the button shows "активна", simulate a round, confirm it reverts and the
   use-counter decremented by exactly 1 (not 2, not 0).
5. **Red card/injury**: play enough rounds (or seed rows directly, as in Task 11's own live-check)
   to see the squad page badges and a real lineup-reminder notification naming an actual player,
   reason, and duration.

Check the browser console for errors throughout every step above.

- [ ] **Step 5: Report**

No commit for this task (verification only) — summarize the full pass/fail state of Steps 1-4.

---
