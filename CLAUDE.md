# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Telegram Mini App for collecting football cards.

Main features:
- packs with staged opening animation, including themed card collections with completion rewards;
- card collection (album + "my cards"), filtering and selling;
- game currency, daily rewards and a free periodic pack;
- seven mini-games: Memory Sequence, Card Arena, Саботёр (Saboteur), Пенальти,
  Штрафной удар (Free Kick), Футбольные буквы (a football-themed word-guessing
  game), and Тактико (Tactico — turn-based squad-vs-squad, bot or friend);
- player-to-player card exchanges;
- tasks/achievements, referrals, leaderboards and profile;
- Telegram bot (notifications/reminders) and a React-based administrative panel.

## Stack

- Frontend: React 18, TypeScript, Vite, Zustand, TanStack Query,
  Tailwind CSS, Framer Motion, Axios.
- Backend: Python 3.12, FastAPI, async SQLAlchemy 2, Alembic,
  PostgreSQL, Pydantic v2, PyJWT (admin sessions only).
- Bot: aiogram 3, talks to Postgres directly (not through the backend API).
- Infrastructure: Docker Compose and Nginx.
- Tests: pytest (async, in-memory SQLite) and Vitest.

## Repository structure

- `backend/` — FastAPI API, models, schemas, services and tests.
- `frontend/` — Telegram Mini App and admin panel (same React app, `/admin/*` routes).
- `bot/` — aiogram Telegram bot; reads/writes Postgres directly via its own asyncpg pool.
- `nginx/` — production reverse proxy.
- `docker-compose.yml` — development environment.
- `docker-compose.override.yml` — optional local override (e.g. exposing the
  Mini App through an SSH tunnel); if present it may replace the frontend's
  dev command with a static `build && preview`, which does **not** hot-reload —
  rebuild (`docker compose up -d --build frontend`) after frontend edits when
  this override is active.
- `docker-compose.prod.yml` — production environment.

## Architecture

- **Auth**: a single `POST /auth/session` validates Telegram `initData` (HMAC,
  see `core/security.py`) or, outside Telegram, an `X-Dev-Mode: true` header
  (only honored when `DEV_MODE=true`; the app refuses to start with
  `DEV_MODE=true` under `ENVIRONMENT=production`). The same call returns the
  user profile *and* an admin JWT if `user.is_admin` — the frontend stores
  both; regular API calls send `X-Telegram-Init-Data`/`X-Dev-Mode`, admin API
  calls (`/admin/*`) send `Authorization: Bearer <admin JWT>` instead (see
  `frontend/src/lib/api.ts`'s axios interceptor).
- **Economy config**: almost every tunable number (rewards, hourly limits,
  pack probabilities, Tactico bonuses/rewards, referral rewards, etc.) lives
  on the single `GameConfig` row (id=1), editable from the admin panel
  (`AdminGamesPage.tsx` and friends). Never hardcode economy numbers in
  services or in frontend copy — read them from `game_config_service.get_config()`
  (backend) or from the profile/API response (frontend), so admin changes
  take effect without a deploy.
- **Wallet pattern**: `wallet_service.lock_user_for_update()` does a
  `SELECT ... FOR UPDATE` with `populate_existing=True` (required — the user
  row is typically already in the session's identity map from
  `get_current_user`, so without it you'd silently read stale pre-lock data).
  `credit_coins`/`debit_coins` mutate the locked user in memory and create a
  `CoinTransaction` row; the caller still has to `db.add`/`db.commit`. Any
  coins/cards/packs/exchange mutation should go through this pattern.
- **Mini-game hourly/daily limits**: each mini-game (memory, arena/match,
  saboteur, penalty, free_kick, hangman, tactico) has two independent
  counters on `User`: `<game>_hourly_attempts` / `<game>_hour_started_at`
  (a shared cap, `config.hourly_game_limit`, resets on a rolling 1h window —
  see `game_limits_service.py`) and `<game>_rewarded_attempts_today` /
  `<game>_attempts_reset_at` (a per-game daily cap on *rewarded* attempts —
  players can keep playing unrewarded after hitting it, they just get
  `reward_coins=0`). Adding a new mini-game means adding both pairs of
  columns (see `hangman_service.py` for the smallest example) plus an
  Alembic migration.
- **Turn-based game state**: `GameSession`/`TacticoMatch` persist a JSON
  `server_state` blob (guessed letters, per-round picks, deadlines, etc.)
  instead of dedicated tables per step, so a multi-step flow can resume
  across requests. Tactico friend matches are asynchronous: there is no
  background scheduler — stale rounds are resolved lazily by a "sweep"
  function (`_auto_play_overdue_rounds`) that runs opportunistically whenever
  either player's client calls `GET /tactico/matches` or `GET .../{id}`, and
  the frontend polls (`refetchInterval`) while waiting on the other side
  specifically to keep that sweep running promptly.
- **Idempotency**: deduplication is enforced via DB unique constraints
  (`pack_openings.(user_id, idempotency_key)`, `daily_rewards.(user_id,
  reward_date)`), not an in-memory cache — this is what makes it safe under
  concurrent/retried requests. The `Idempotency-Key` header is plumbed
  through but the actual guarantee comes from the constraint.
- **Errors**: raise `AppError` subclasses from `core/exceptions.py`
  (`NotFoundError`, `ForbiddenError`, `ConflictError`,
  `InsufficientBalanceError`, `RateLimitedError`, `UnauthorizedError`); a
  global handler serializes them to `{"error": {"code", "message",
  "details"}}`. The frontend's axios interceptor (`lib/api.ts`) unwraps this
  into `ApiRequestError`; use `formatGameError`/`err.message` rather than
  re-deriving messages.
- **Rate limiting**: `core/rate_limit.py` is an in-memory sliding window,
  per-process only — fine for a single backend instance, would need a
  Redis-backed limiter before running multiple backend replicas.
- **Referrals**: the referrer relationship is recorded at registration, but
  the referrer's reward/count is only granted on the referred user's first
  *genuine paid* pack purchase (`pack_service.open_pack`) — crediting it at
  registration would let anyone farm rewards with disposable, never-used
  accounts.
- **Bot**: aiogram service that does not call the backend HTTP API — it reads
  and writes Postgres directly through its own `asyncpg` pool (`bot/db.py`).
  When changing a table the bot touches (users, notifications, daily
  rewards, free pack), update both the SQLAlchemy model/migration and the
  bot's raw SQL.
- **Frontend routing**: one React app serves both the Mini App (`/`, `/packs`,
  `/play/*`, `/collection`, …) and the admin panel (`/admin/*`, gated by
  `AdminGuard` client-side and `get_current_admin` server-side). State:
  Zustand for client state (`authStore`, `uiStore`, and `matchGuardStore`
  which blocks in-app navigation during a live match and also fires a
  `pagehide` keepalive `fetch` so a real tab close/reload still records a
  forfeit), TanStack Query for server state.
- **Alembic revisions** are named sequentially (`0001_...` → current head),
  not autogenerate-hash IDs — follow that convention (`NNNN_short_description.py`)
  and bump `down_revision` to the current head.

## Mandatory rules

- Inspect existing implementation before adding new abstractions.
- Do not invent models, endpoints or fields without checking the code.
- Keep game economy, authorization and probability calculations on backend.
- Never trust values received from frontend for balances, rewards or cards.
- Preserve Telegram initData HMAC validation.
- Use async database access only.
- Any operation involving coins, cards, packs or exchanges must be atomic.
- Use row locking for race-sensitive operations.
- Preserve idempotency for pack opening and other retryable operations.
- Never read, print or edit `.env`; use `.env.example`.
- Do not run destructive Git, Docker or database commands.
- Do not commit or push unless explicitly requested.
- Do not perform unrelated refactoring.
- Update or add tests whenever behavior changes.
- Keep Telegram UI mobile-first and compatible with Telegram theme variables.
- Reuse existing components, schemas, services and error formats.

## Workflow

For tasks affecting several modules:

1. Inspect relevant code.
2. Give a short implementation plan.
3. Implement the smallest coherent change.
4. Run relevant tests and type checks.
5. Review the resulting diff.
6. Summarize changed files and any remaining risks.

Do not stop after writing code if checks are available.

## Commands

### Run development environment

```bash
docker compose up --build
docker compose exec backend python -m app.seed
```

Frontend: http://localhost:5173 · Backend Swagger: http://localhost:8000/api/docs ·
Admin panel: http://localhost:5173/admin (needs a Telegram ID from `ADMIN_TELEGRAM_IDS`,
or the dev-mode user when `DEV_MODE=true`).

### Backend checks

```bash
cd backend
pytest tests/ -v                        # full suite (in-memory SQLite, no Postgres needed)
pytest tests/test_tactico.py -v         # single file
pytest tests/test_tactico.py::test_name -v   # single test
python -c "from app.main import app"    # import/startup sanity check
```

Row-level locking (`SELECT ... FOR UPDATE`) is not exercised by the SQLite
test DB — verify locking-dependent changes manually against real Postgres
(e.g. via the running `docker compose` backend/postgres containers).

### Database migrations

```bash
cd backend
alembic revision -m "short description"   # then hand-write op.* calls, see existing versions/
alembic upgrade head
# inside docker compose:
docker compose exec backend alembic upgrade head
```

### Frontend checks

```bash
cd frontend
npm run test        # Vitest
npm run typecheck   # tsc -b --noEmit
npm run lint        # eslint .
npm run build
```

## Definition of done

A task is complete only when:

- requested behavior is implemented;
- existing architecture is respected;
- relevant tests pass;
- TypeScript typecheck passes for frontend changes;
- no secrets or generated artifacts were added;
- final response lists modified files and verification results.
