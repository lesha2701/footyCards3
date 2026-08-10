# Penalty Visuals + 6-Zone Shooting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing solo-vs-bot Penalty mini-game a real goal/goalkeeper visual (colored by whose side is defending) and replace its 3-direction picker with a 3×2 grid of 6 shooting zones — no new backend subsystem, no PvP yet.

**Architecture:** Backend: widen the existing `penalty_service.py`'s direction constant from 3 values to 6 and extract the shared miss/zone-compare logic into one pure helper (reused later by PvP). Frontend: extract a new `PenaltyGoalScene` component (SVG goal + recolorable gloves + real football artwork, CSS-transition-driven) that `PenaltyGamePage` drives from kick results; the component is deliberately built to be reused unchanged by the PvP match page in the next plan.

**Tech Stack:** FastAPI/SQLAlchemy (backend — one migration in this plan, adding the `users.penalty_rating` column Task 1 needs), React + TypeScript + Tailwind + inline SVG (frontend, no new npm dependencies).

## Global Constraints

- Preserve existing solo-vs-bot behavior exactly (regulation 10 kicks / 5 rounds, unlimited sudden death on a tie, no draw) — only the zone *set* and the visuals change, per the approved spec's "Не цели" section.
- `player_miss_chance(rating)` continues to use the **shooter's** card rating, never the defender's — per spec's zones section.
- No new coins, no new limits, no config changes in this plan — `penalty_reward_win/draw/loss`, `penalty_bot_miss_chance`, `penalty_daily_limit`, `hourly_game_limit` are untouched.
- Reference spec: `docs/superpowers/specs/2026-08-10-penalty-visuals-and-pvp-design.md` (sections "Визуал", "6 zones").
- This plan intentionally excludes the PvP subsystem (challenge/accept/pick/timers/rating/leaderboard) — that is a second, separate plan (`docs/superpowers/plans/2026-08-10-penalty-pvp.md`) that depends on this one shipping first, because PvP reuses the `PENALTY_ZONES` constant and the `PenaltyGoalScene` component built here.

---

## File Structure

- Modify: `backend/app/services/penalty_service.py` — rename `DIRECTIONS` → `PENALTY_ZONES` (6 values), extract `_resolve_shot()`.
- Modify: `backend/app/models/user.py` — add `penalty_rating: Mapped[int]` (default 0), mirroring `tactics_rating`. **[Resolved during Task 1 execution — done by the controller, not the implementer; see note below.]**
- Create: `backend/alembic/versions/0039_penalty_rating.py` — adds `users.penalty_rating` (Integer, not null, server_default 0). **[Same resolution.]**
- Modify: `backend/tests/test_penalty.py` — update the 2 hardcoded `"left"` literals to a valid new zone; add zone-coverage tests.
- Modify: `frontend/src/types/index.ts` — `PenaltyDirection` becomes a 6-value union.
- Create: `frontend/public/penalty/gk-gloves.png` — the goalkeeper-gloves silhouette asset (copied from `/Users/alex/Downloads/goalkeeper.png`), served as a static file and recolored client-side via an SVG alpha mask.
- Create: `frontend/src/components/penalty/PenaltyGoalScene.tsx` — the reusable goal/keeper/ball scene.
- Modify: `frontend/src/pages/PenaltyGamePage.tsx` — drive the new scene, replace the 3-button row with a 3×2 zone grid.

---

### Task 1: Backend — 6 zones + shared shot-resolution helper

**Files:**
- Modify: `backend/app/services/penalty_service.py`
- Test: `backend/tests/test_penalty.py`
- (Already done by the controller, not part of this task's dispatch: `backend/app/models/user.py` gained `penalty_rating`, and migration `0039_penalty_rating.py` was added and applied — the plan originally omitted this column, and the implementer correctly escalated rather than guessing.)

**Interfaces:**
- Produces: `PENALTY_ZONES: tuple[str, ...]` (6 values: `"top_left"`, `"top_center"`, `"top_right"`, `"bottom_left"`, `"bottom_center"`, `"bottom_right"`) and `_resolve_shot(miss_chance: float, shot_zone: str, dive_zone: str) -> str` (returns `"goal"` | `"saved"` | `"miss"`) — both importable from `app.services.penalty_service`, both needed by the PvP plan.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_penalty.py`. Fix the two existing calls that hardcode the old 3-value `"left"` (lines 55 and 110 today) to use a valid new zone, and add two new tests covering the full 6-zone set and rejection of stale/invalid values.

Replace this line (inside `test_penalty_full_shootout_resolves_and_pays_reward`):
```python
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "left"})
```
with:
```python
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})
```

Replace this line (inside `test_penalty_daily_reward_cap_still_allows_play_with_zero_reward`):
```python
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "left"})
```
with:
```python
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "bottom_right"})
```

Then add these two new tests right after `test_penalty_invalid_direction_rejected`:

```python
async def test_penalty_accepts_all_six_zones(client, db_session, bot_token):
    user = await _register(client, db_session, 830006, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830006, bot_token)

    zones = ["top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right"]
    for i, zone in enumerate(zones):
        start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
        session_id = start.json()["session_id"]
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": zone})
        assert resp.status_code == 200, f"zone {zone} rejected"
        if i < len(zones) - 1:
            await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})


async def test_penalty_rejects_stale_three_direction_values(client, db_session, bot_token):
    user = await _register(client, db_session, 830007, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830007, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]
    resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "left"})
    assert resp.status_code == 409


async def test_penalty_bot_match_updates_penalty_rating(client, db_session, bot_token):
    """The spec requires penalty_rating to move for bot matches too (win
    +3 / loss -1, same deltas Tactico uses), not just PvP — this is the
    only place in the codebase that finishes a solo Penalty match, so the
    rating update has to live in resolve_kick's is_finished branch."""
    user = await _register(client, db_session, 830008, bot_token)
    card = await _grant_card(db_session, user.id, rating=99)  # near-zero miss chance, deterministic
    headers = telegram_headers(830008, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]

    result = None
    for _ in range(30):
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})
        body = resp.json()
        if body["is_finished"]:
            result = body["result"]
            break

    await db_session.refresh(user)
    assert user.penalty_rating == (3 if result == "win" else -1)
```

Note: `test_penalty_accepts_all_six_zones` starts a fresh session per zone (rather than trying to drive one session through all 6 without exhausting the hourly limit). `backend/tests/conftest.py` has no `GameConfig` override, so the model default (`hourly_game_limit=3`, `backend/app/models/game_config.py`) applies — 6 fresh `start` calls would 409 after the 3rd without raising it first. Add this right after computing `headers`, before the loop:

```python
    from app.services.game_config_service import get_config
    config = await get_config(db_session)
    config.hourly_game_limit = 10
    db_session.add(config)
    await db_session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec -T backend pytest tests/test_penalty.py -v`
Expected: `test_penalty_full_shootout_resolves_and_pays_reward` and the daily-cap test now fail with `409` (since `"top_left"`/`"bottom_right"` aren't valid yet), and the two new tests fail (`test_penalty_accepts_all_six_zones` gets a 409 on the first non-`"top_left"`-ish zone; `test_penalty_rejects_stale_three_direction_values` currently passes by accident since `"left"` IS still valid — that one will only become a meaningful regression test once Step 3 lands, which is fine, TDD-wise this one is a "confirm it still passes after the change" test more than a "currently red" one).

- [ ] **Step 3: Implement the 6 zones + shared helper**

In `backend/app/services/penalty_service.py`, replace:
```python
DIRECTIONS = ("left", "center", "right")
REGULATION_KICKS = 10  # 5 rounds x 2 kicks


def player_miss_chance(rating: int) -> float:
    r = max(58, min(99, rating))
    return 0.30 - (r - 58) / (99 - 58) * (0.30 - 0.05)
```
with:
```python
# 3x2 grid: which third of the goal (left/center/right) and which half
# (top/bottom) the shot/dive targets. Shared with PvP (see penalty_match_service.py).
PENALTY_ZONES = ("top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right")
REGULATION_KICKS = 10  # 5 rounds x 2 kicks


def player_miss_chance(rating: int) -> float:
    r = max(58, min(99, rating))
    return 0.30 - (r - 58) / (99 - 58) * (0.30 - 0.05)


def _resolve_shot(miss_chance: float, shot_zone: str, dive_zone: str) -> str:
    """A single blind shot vs. a single blind dive: 'goal', 'saved', or
    'miss'. The shooter's own miss chance is rolled first (independent of
    zones) — only if they don't miss do the zones get compared. Shared by
    the bot mode below and by PvP (which reuses this exact rule, just with
    a real dive instead of a random one)."""
    if random.random() < miss_chance:
        return "miss"
    return "saved" if shot_zone == dive_zone else "goal"
```

Then replace the direction-validation line in `resolve_kick`:
```python
    if direction not in DIRECTIONS:
        raise ConflictError("Invalid direction")
```
with:
```python
    if direction not in PENALTY_ZONES:
        raise ConflictError("Invalid direction")
```

Then replace the whole scoring block inside `resolve_kick`:
```python
    if kicker == "player":
        missed = random.random() < player_miss_chance(state["player_rating"])
        bot_dir = random.choice(DIRECTIONS)
        goal = (not missed) and (direction != bot_dir)
        if goal:
            state["player_score"] += 1
        outcome = "goal" if goal else ("miss" if missed else "saved")
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_missed = random.random() < float(config.penalty_bot_miss_chance)
        bot_shot_dir = random.choice(DIRECTIONS)
        saved = (not bot_missed) and (direction == bot_shot_dir)
        if not bot_missed and not saved:
            state["bot_score"] += 1
        outcome = "saved" if saved else ("miss" if bot_missed else "goal")
        round_entry = {
            "kicker": "bot", "player_direction": direction, "bot_direction": bot_shot_dir, "outcome": outcome,
        }
```
with:
```python
    if kicker == "player":
        bot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(player_miss_chance(state["player_rating"]), direction, bot_dir)
        if outcome == "goal":
            state["player_score"] += 1
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_shot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(float(config.penalty_bot_miss_chance), bot_shot_dir, direction)
        if outcome == "goal":
            state["bot_score"] += 1
        round_entry = {
            "kicker": "bot", "player_direction": direction, "bot_direction": bot_shot_dir, "outcome": outcome,
        }
```

This is behavior-preserving: for the player's own kick, `_resolve_shot(miss_chance, direction, bot_dir)` returns `"saved"` exactly when `direction == bot_dir` (bot "guessed" the same zone), matching the old `direction != bot_dir` goal condition. For the bot's kick, `_resolve_shot(bot_miss_chance, bot_shot_dir, direction)` returns `"saved"` exactly when `bot_shot_dir == direction` (player guessed correctly), matching the old `direction == bot_shot_dir` save condition.

Finally, `penalty_rating` needs to move for bot matches too (per the spec's "Рейтинг и лидерборд" section: "И бот-режим, и PvP обновляют её") — this is the only place a solo Penalty match finishes, so it's the only place that needs the change. Replace:
```python
    if is_finished:
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        state["result"] = result
        session.server_state = state
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = {
            "win": config.penalty_reward_win, "loss": config.penalty_reward_loss,
        }[result]
        await task_service.evaluate_penalty_win_max_rating(db, user, state["player_rating"], result == "win")
```
with:
```python
    if is_finished:
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        state["result"] = result
        session.server_state = state
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = {
            "win": config.penalty_reward_win, "loss": config.penalty_reward_loss,
        }[result]
        # Same +3/-1 deltas Tactico uses for its rating; a solo shootout has
        # no draw outcome, so there's no +1 case to handle here.
        locked_user = await lock_user_for_update(db, user.id)
        locked_user.penalty_rating = max(0, locked_user.penalty_rating + (3 if result == "win" else -1))
        db.add(locked_user)
        await task_service.evaluate_penalty_win_max_rating(db, user, state["player_rating"], result == "win")
```
`lock_user_for_update` is already imported at the top of this file (`from app.services.wallet_service import credit_coins, lock_user_for_update`) — no new import needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec -T backend pytest tests/test_penalty.py -v`
Expected: all tests PASS, including the 2 new ones.

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `docker compose exec -T backend pytest tests/ -q`
Expected: same pass count as before this change (the pre-existing unrelated `test_task_reward_pack_grants_all_cards` failure is fine — confirm it's the *only* failure).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/penalty_service.py backend/tests/test_penalty.py
git commit -m "$(cat <<'EOF'
Widen Penalty to 6 shooting zones (3x2 grid, was 3 directions)

Extracts the miss-chance/zone-compare logic into _resolve_shot(), shared
by both sides of the bot match and reused as-is by the upcoming PvP mode.
Behavior-preserving for existing 3-zone-equivalent play; PENALTY_ZONES
now has 6 values instead of 3.
EOF
)"
```

---

### Task 2: Frontend — widen the `PenaltyDirection` type

**Files:**
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: `PenaltyDirection` as a 6-value union, consumed by Task 4/5.

- [ ] **Step 1: Update the type**

In `frontend/src/types/index.ts`, replace:
```ts
export type PenaltyDirection = "left" | "center" | "right";
```
with:
```ts
export type PenaltyDirection =
  | "top_left" | "top_center" | "top_right"
  | "bottom_left" | "bottom_center" | "bottom_right";
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: **fails** right now — `PenaltyGamePage.tsx` still references the old 3 values. That's expected; Task 4 fixes it. Confirm the errors are only in `PenaltyGamePage.tsx` (nowhere else references `PenaltyDirection`'s literal values).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "Widen PenaltyDirection type to the 6-zone grid"
```

---

### Task 3: Frontend — add the recolorable gloves asset

**Files:**
- Create: `frontend/public/penalty/gk-gloves.png`

**Interfaces:**
- Produces: a static asset served at `/penalty/gk-gloves.png` (same convention as `frontend/public/brand/victor-fc-crest.jpg`, referenced directly by path — no `staticUrl()` helper needed since this isn't backend-uploaded content).

- [ ] **Step 1: Copy the asset into the repo**

```bash
mkdir -p frontend/public/penalty
cp /Users/alex/Downloads/goalkeeper.png frontend/public/penalty/gk-gloves.png
```

- [ ] **Step 2: Verify it's a black silhouette on a transparent background**

```bash
file frontend/public/penalty/gk-gloves.png
```
Expected: `PNG image data, ... RGBA` (has an alpha channel — required for the alpha-mask recoloring technique in Task 4). If it reports no alpha channel, stop and flag it — the mask approach in `PenaltyGoalScene` won't recolor correctly without one.

- [ ] **Step 3: Commit**

```bash
git add frontend/public/penalty/gk-gloves.png
git commit -m "Add goalkeeper gloves asset for the Penalty goal scene"
```

---

### Task 4: Frontend — `PenaltyGoalScene` component

**Files:**
- Create: `frontend/src/components/penalty/PenaltyGoalScene.tsx`

**Interfaces:**
- Consumes: `PenaltyDirection` (from `@/types`, produced by Task 2), the `/penalty/gk-gloves.png` asset (Task 3).
- Produces:
  ```ts
  export interface PenaltyGoalKick {
    shotZone: PenaltyDirection;
    diveZone: PenaltyDirection;
    outcome: "goal" | "saved" | "miss";
  }
  export interface PenaltyGoalSceneProps {
    keeperSide: "own" | "opponent";
    kick: PenaltyGoalKick | null;
    outcomeLabel: string | null;
    outcomeGood: boolean;
  }
  export default function PenaltyGoalScene(props: PenaltyGoalSceneProps): JSX.Element
  ```
  Consumed by Task 5 (`PenaltyGamePage.tsx`) and by the PvP match page in the next plan.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/penalty/PenaltyGoalScene.tsx`:

```tsx
import { useEffect, useRef } from "react";

import type { PenaltyDirection } from "@/types";

export interface PenaltyGoalKick {
  shotZone: PenaltyDirection;
  diveZone: PenaltyDirection;
  outcome: "goal" | "saved" | "miss";
}

export interface PenaltyGoalSceneProps {
  /** "own" = your goal is under attack, your (red) keeper dives.
   *  "opponent" = you're attacking, their (blue) keeper dives. */
  keeperSide: "own" | "opponent";
  /** The kick currently animating in, or null to show the idle/reset scene. */
  kick: PenaltyGoalKick | null;
  /** Text shown in the small badge above the crossbar, e.g. "Гол!". */
  outcomeLabel: string | null;
  /** Colors the badge green (true) or red (false) — "good" is relative to
   * the viewer: scoring while attacking is good, saving while defending is good. */
  outcomeGood: boolean;
}

const KEEPER_BASE = { x: 150, y: 118 };
const BALL_REST = { x: 150, y: 234 };

const ZONE_KEEPER_OFFSET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: -78, y: -58 },
  top_center: { x: 0, y: -68 },
  top_right: { x: 78, y: -58 },
  bottom_left: { x: -78, y: 34 },
  bottom_center: { x: 0, y: 40 },
  bottom_right: { x: 78, y: 34 },
};

const ZONE_BALL_TARGET: Record<PenaltyDirection, { x: number; y: number }> = {
  top_left: { x: 80, y: 55 },
  top_center: { x: 150, y: 45 },
  top_right: { x: 220, y: 55 },
  bottom_left: { x: 80, y: 168 },
  bottom_center: { x: 150, y: 176 },
  bottom_right: { x: 220, y: 168 },
};

const KEEPER_COLOR = { own: "#e6483b", opponent: "#3b82f6" };

export default function PenaltyGoalScene({ keeperSide, kick, outcomeLabel, outcomeGood }: PenaltyGoalSceneProps) {
  const maskRef = useRef<SVGMaskElement>(null);
  useEffect(() => {
    // mask-type isn't a recognized React/JSX style key, so it's set
    // imperatively — "alpha" (not the SVG default "luminance") is required
    // because the source PNG is a solid black shape on a transparent
    // background: luminance masking would treat pure-black as invisible.
    maskRef.current?.setAttribute("mask-type", "alpha");
  }, []);

  const keeperOffset = kick ? ZONE_KEEPER_OFFSET[kick.diveZone] : { x: 0, y: 0 };
  const ballTarget = kick ? ZONE_BALL_TARGET[kick.shotZone] : BALL_REST;

  return (
    <div className="relative overflow-hidden rounded-[20px] border border-white/5 bg-[#0d1a10] px-4 pb-3.5 pt-5">
      <div className="pointer-events-none absolute -inset-x-[20%] -top-[40%] h-[140px] bg-gradient-to-r from-accent-cyan via-accent-green to-accent-lime opacity-[0.16] blur-[30px]" />

      <div className="relative mx-auto my-1.5 max-w-[300px]">
        <svg className="block w-full overflow-visible" viewBox="0 0 300 258">
          <path d="M 30 200 L 30 30 L 270 30 L 270 200" fill="none" stroke="#eef2ee" strokeWidth={4} strokeLinecap="round" />
          <g stroke="rgba(238,242,238,0.28)" strokeWidth={1}>
            {Array.from({ length: 13 }, (_, i) => 30 + i * 20).map((x) => (
              <line key={`v${x}`} x1={x} y1={30} x2={x} y2={200} />
            ))}
            {Array.from({ length: 9 }, (_, i) => 30 + i * 21).map((y) => (
              <line key={`h${y}`} x1={30} y1={y} x2={270} y2={y} />
            ))}
          </g>

          <defs>
            <mask ref={maskRef} id="penaltyGloveMask" maskUnits="userSpaceOnUse" x={-40} y={-40} width={80} height={80}>
              <image href="/penalty/gk-gloves.png" x={-40} y={-40} width={80} height={80} />
            </mask>
          </defs>
          <g
            style={{
              transformOrigin: `${KEEPER_BASE.x}px ${KEEPER_BASE.y}px`,
              transform: `translate(${KEEPER_BASE.x + keeperOffset.x}px, ${KEEPER_BASE.y + keeperOffset.y}px) scale(${kick ? 1.05 : 1})`,
              transition: "transform 420ms cubic-bezier(0.2,0.9,0.3,1.3)",
            }}
          >
            <ellipse cx={0} cy={36} rx={36} ry={6} fill="rgba(0,0,0,0.35)" />
            <rect
              x={-40} y={-40} width={80} height={80}
              mask="url(#penaltyGloveMask)"
              fill={KEEPER_COLOR[keeperSide]}
              style={{ transition: "fill 200ms linear" }}
            />
          </g>

          <ellipse cx={BALL_REST.x} cy={BALL_REST.y} rx={10} ry={3.5} fill="rgba(238,242,238,0.55)" />
          <g
            style={{
              transformOrigin: `${BALL_REST.x}px ${BALL_REST.y}px`,
              transform: `translate(${ballTarget.x - BALL_REST.x}px, ${ballTarget.y - BALL_REST.y}px) scale(${kick ? 0.75 : 1})`,
              transition: "transform 550ms cubic-bezier(0.16,0.85,0.35,1)",
            }}
          >
            <g transform={`translate(${BALL_REST.x},${BALL_REST.y}) scale(1.06) translate(-10.377,-10.047) translate(-1.623,-1.913)`}>
              <circle fill="#f3f6f2" cx={12} cy={12} r={9} />
              <path fill="#2ca9bc" d="M14.33,3.31,12,5,9.67,3.31a8.91,8.91,0,0,1,4.66,0ZM4.46,7.1A9,9,0,0,0,3,11.53L5.34,9.84ZM8,17.89l-.07-.23H5A8.92,8.92,0,0,0,8.78,20.4ZM12,8,8.5,10.67,9.84,15h4.32l1.34-4.33Zm4.11,9.66-.07.23-.82,2.51A8.92,8.92,0,0,0,19,17.66ZM19.54,7.11l-.88,2.73L21,11.53a8.93,8.93,0,0,0-1.46-4.42Z" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.67,3.31,12,5l2.33-1.69" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.02,11.53,5.34,9.84,4.46,7.1" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18,18l-1.92-.04-.73,2.38" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6,18l1.92-.04.73,2.38" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.55,7.1l-.89,2.74,2.32,1.69" />
              <path fill="none" stroke="#0d1a10" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12,8V5M8.41,10.65,5.34,9.84M9.84,15,7.89,18m6.27-3,1.95,3m-.61-7.33,3.16-.83M12,8,8.5,10.67,9.84,15h4.32l1.34-4.33Zm0-5a9,9,0,1,0,9,9A9,9,0,0,0,12,3Z" />
            </g>
          </g>
        </svg>

        {outcomeLabel && (
          <span
            className={`absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full px-2.5 py-1 font-mono text-xs font-extrabold uppercase tracking-wider ${
              outcomeGood ? "bg-accent-green/20 text-accent-green" : "bg-[#e6483b]/20 text-[#e6483b]"
            }`}
          >
            {outcomeLabel}
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: no NEW errors from this file (the pre-existing `PenaltyGamePage.tsx` errors from Task 2 are still there — that's fine, Task 5 fixes them).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/penalty/PenaltyGoalScene.tsx
git commit -m "Add PenaltyGoalScene: goal/keeper/ball visual, reusable by PvP"
```

---

### Task 5: Frontend — wire `PenaltyGamePage` to the new scene and 6-zone grid

**Files:**
- Modify: `frontend/src/pages/PenaltyGamePage.tsx`

**Interfaces:**
- Consumes: `PenaltyGoalScene`/`PenaltyGoalKick` (Task 4), `PenaltyDirection` (Task 2). Existing `startPenalty`/`kickPenalty`/`claimPenaltyReward` from `@/api/games` and `PenaltyKickResult`/`PenaltyStartResult`/`PenaltyClaimResult` from `@/types` are unchanged.

- [ ] **Step 1: Replace the file**

Replace the full contents of `frontend/src/pages/PenaltyGamePage.tsx` with:

```tsx
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimPenaltyReward, kickPenalty, startPenalty } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { IconCoin, IconFlagCheckered, IconTrophy } from "@/components/icons";
import PenaltyGoalScene, { type PenaltyGoalKick } from "@/components/penalty/PenaltyGoalScene";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PenaltyDirection, PenaltyKickResult } from "@/types";

type Phase = "pick_card" | "playing" | "finished";

const ZONES: { value: PenaltyDirection; label: string; arrow: string }[] = [
  { value: "top_left", label: "Верх-лево", arrow: "↖" },
  { value: "top_center", label: "Верх-центр", arrow: "↑" },
  { value: "top_right", label: "Верх-право", arrow: "↗" },
  { value: "bottom_left", label: "Низ-лево", arrow: "↙" },
  { value: "bottom_center", label: "Низ-центр", arrow: "↓" },
  { value: "bottom_right", label: "Низ-право", arrow: "↘" },
];

function goalKickFrom(result: PenaltyKickResult): PenaltyGoalKick | null {
  if (!result.player_direction) return null;
  return result.kicker === "player"
    ? { shotZone: result.player_direction, diveZone: result.bot_direction, outcome: result.outcome }
    : { shotZone: result.bot_direction, diveZone: result.player_direction, outcome: result.outcome };
}

function outcomeLabelFor(result: PenaltyKickResult): { label: string; good: boolean } {
  if (result.kicker === "player") {
    if (result.outcome === "goal") return { label: "Гол!", good: true };
    if (result.outcome === "saved") return { label: "Отбито", good: false };
    return { label: "Мимо", good: false };
  }
  if (result.outcome === "saved") return { label: "Отбил!", good: true };
  if (result.outcome === "goal") return { label: "Пропустил", good: false };
  return { label: "Соперник промазал", good: true };
}

export default function PenaltyGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("pick_card");
  const [lastKick, setLastKick] = useState<PenaltyKickResult | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });

  const startMutation = useMutation({
    mutationFn: startPenalty,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setLastKick(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const claimMutation = useMutation({
    mutationFn: () => claimPenaltyReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  const kickMutation = useMutation({
    mutationFn: (direction: PenaltyDirection) => kickPenalty(sessionId!, direction),
    onSuccess: (result) => {
      haptic(result.outcome === "goal" || result.outcome === "saved" ? "medium" : "light");
      setLastKick(result);
      if (result.is_finished) {
        hapticNotify(result.result === "win" ? "success" : "error");
        setPhase("finished");
        claimMutation.mutate();
      }
    },
  });

  if (phase === "pick_card") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти</h1>
        <p className="text-sm text-ink-mist">
          Выбери игрока для серии пенальти. Чем выше его рейтинг, тем меньше шанс промазать по воротам.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open
          title="Выбери игрока"
          cards={collection?.items ?? []}
          onSelect={(card) => startMutation.mutate(card.id)}
          onClose={() => navigate("/play")}
        />
      </div>
    );
  }

  if (phase === "finished") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        {lastKick?.result === "win" ? (
          <IconTrophy size={40} className="text-accent-lime" />
        ) : (
          <IconFlagCheckered size={40} className="text-ink-mist" />
        )}
        <p className="font-display text-2xl font-bold text-ink-chalk">
          {lastKick?.result === "win" ? "Победа!" : "Поражение"}
        </p>
        <p className="text-sm text-ink-mist">
          Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score} : {lastKick?.bot_score}</span>
        </p>

        {claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claimResult ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        ) : claimMutation.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claimMutation.error, "Не удалось начислить награду")}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button onClick={() => setPhase("pick_card")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const isPlayerKicking = !lastKick || lastKick.next_kicker === "player";
  const roleLabel = kickMutation.isPending
    ? "..."
    : isPlayerKicking
      ? "Твой удар — выбери зону"
      : "Бот бьёт — угадай, куда прыгнуть";

  const outcome = lastKick ? outcomeLabelFor(lastKick) : null;

  return (
    <div className="flex flex-col items-center gap-5 py-6">
      <p className="text-sm text-ink-mist">
        Счёт: <span className="font-mono font-bold text-accent-cyan">{lastKick?.player_score ?? 0} : {lastKick?.bot_score ?? 0}</span>
      </p>

      <PenaltyGoalScene
        keeperSide={lastKick?.kicker === "bot" ? "own" : "opponent"}
        kick={lastKick ? goalKickFrom(lastKick) : null}
        outcomeLabel={outcome?.label ?? null}
        outcomeGood={outcome?.good ?? false}
      />

      <p className="text-sm font-semibold text-ink-mist">{roleLabel}</p>

      <div className="grid grid-cols-3 gap-2.5">
        {ZONES.map((z) => (
          <button
            key={z.value}
            onClick={() => kickMutation.mutate(z.value)}
            disabled={kickMutation.isPending}
            className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-3 py-3.5 text-[11px] font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
          >
            <span className="text-base leading-none">{z.arrow}</span>
            {z.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

Notes on what changed vs. the old file, for the reviewer:
- `keeperSide` is `"own"` when the bot is kicking (your keeper defends) and `"opponent"` when you're kicking (their keeper defends) — matches the spec's color rule.
- `goalKickFrom`/`outcomeLabelFor` are small pure helpers translating the existing `PenaltyKickResult` API shape into the scene's props — no backend contract change needed beyond Task 1's widened zone values.
- The old inline `OUTCOME`/`DIRECTIONS` constants and the `AnimatePresence`/`motion` outcome card are gone — replaced by `PenaltyGoalScene`, which owns its own CSS-transition animation.

- [ ] **Step 2: Typecheck**

Run: `docker compose exec -T frontend sh -c "npm run typecheck"`
Expected: clean, no errors anywhere.

- [ ] **Step 3: Rebuild and manually verify in the browser**

The dev stack uses `docker-compose.override.yml`, which runs `build && preview` (no hot reload) — rebuild after this change:
```bash
docker compose up -d --build frontend
```
Wait for it to come up, then open `http://localhost:5173/play/penalty` (dev-mode auth via `X-Dev-Mode` header, no real Telegram needed — see `CLAUDE.md`). Pick a card, play a few kicks covering both roles (your kick and the bot's kick), and confirm:
- The keeper is blue while you're kicking, red while the bot is kicking.
- Low-zone shots visibly land near the bottom of the goal, not the middle.
- The outcome badge sits above the crossbar, never overlapping the gloves.
- Colors are correct: your goal (red keeper) — saving is green, conceding is red; their goal (blue keeper) — scoring is green, being saved is red.

- [ ] **Step 4: Run the frontend unit suite**

Run: `docker compose exec -T frontend sh -c "npm run test -- --run"`
Expected: all existing tests still pass (none of them touch `PenaltyGamePage`, so this is a regression guard, not new coverage).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PenaltyGamePage.tsx
git commit -m "$(cat <<'EOF'
Penalty: real goal/keeper visual + 6-zone shooting grid

Replaces the 3-button direction row and the plain outcome icon/text with
PenaltyGoalScene — an animated goal, a recolorable keeper (red when
defending your own goal, blue when attacking), and the real football
artwork. Verified live: colors, low-zone shot height, and badge
positioning all match the approved design mockup.
EOF
)"
```

---

## Self-Review Notes

- **Spec coverage:** "Визуал" (Task 4/5) ✅. "6 zones" (Task 1/2/5) ✅. Solo-mode `player_miss_chance` on the shooter only — preserved via `_resolve_shot`'s explicit parameter order ✅. `penalty_rating` for the bot-mode win/loss case (Task 1, Step 3's final diff + `test_penalty_bot_match_updates_penalty_rating`) ✅ — this was initially missed and only caught during the PvP plan's self-review; folded back in here since `resolve_kick` is where it belongs. PvP, leaderboard wiring are explicitly out of scope for this plan (see the second plan).
- **Placeholder scan:** none — every step has real, complete code.
- **Type consistency:** `PenaltyGoalKick.shotZone/diveZone` (Task 4) match `PenaltyDirection` (Task 2) exactly; `goalKickFrom`/`outcomeLabelFor` (Task 5) consume the existing `PenaltyKickResult` fields (`kicker`, `outcome`, `player_direction`, `bot_direction`) without renaming anything backend-facing.
