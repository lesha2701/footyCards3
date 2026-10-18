# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Telegram Mini App for collecting football cards.

Main features:
- packs with staged opening animation, including themed card collections with completion rewards;
- card collection (album + "my cards"), filtering and selling;
- «Академия» path cards: diamond youngsters that level up from rewarded
  matches along staged gates and carry a situational talent
  (`path_service.py` / `path_talent_effects.py` / `path_match_service.py`,
  see docs/path-cards.md);
- game currency, daily rewards and a free periodic pack;
- mini-games: Memory Sequence, Card Arena, Саботёр (Saboteur), Пенальти,
  Штрафной удар (Free Kick), Футбольные буквы (a football-themed word-guessing
  game), Тактико (Tactico — turn-based squad-vs-squad, bot or friend),
  Футбольное Стратего (hidden-information board game on cards, bot or
  friend — `stratego_engine.py` holds the pure rules, `stratego_service.py`
  the DB/limits/rewards; only `_hydrate_match` may serialize a match, and
  it strips unrevealed enemy pieces) and Футбольный магнат (a short
  4-seat economic board game — `magnate_engine.py` is the pure, seeded
  rules engine + bot, `magnate_service.py` the lobbies/rooms, turn timers,
  limits and rewards; see "Turn-based game state" below);
- clubs: squad/tournaments/league plus emblem constructor (`club_emblem_service`,
  paid layers for budget coins or Stars), «Казна за Stars» (`club_treasury_service`),
  spare-card sale/exchange (`club_market_service`), roles (vice-captain, treasurer),
  wall, shop / weekly quests / wars whose member rewards go through one claim
  mechanism (`club_reward_service`), league divisions with seasons and a trophy
  room. Quests, wars and league settlement have no scheduler of their own: they
  run lazily on reads and from bot sweeps (`/internal/clubs/...`), idempotent via
  unique rows;
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
  saboteur, penalty, free_kick, hangman, tactico, pairs, stratego, magnate) has two independent
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
  specifically to keep that sweep running promptly. «Футбольный магнат»
  is the exception with ~30 s turns: besides the lazy sweep on reads, the
  bot calls `POST /internal/magnate/sweep` every 10 s
  (`bot/services/magnate_scheduler.py`); each match is taken with
  `FOR UPDATE SKIP LOCKED` and its `next_deadline_at` re-checked under the
  lock, so both paths can run at once without double-processing, and
  client actions carry the match `version` (stale → 409).
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
- **Telegram Stars payments**: the Mini App creates a `StarsInvoice`
  (price frozen on it); the bot answers `pre_checkout_query` and, on
  `successful_payment`, first inserts a `stars_payment_receipts` row
  straight into Postgres (the player is already charged — the receipt must
  survive a backend outage), then calls `POST /internal/stars-payments/deliver`
  (`stars_receipt_service.deliver_with_receipt` → idempotent
  `stars_payment_service.deliver_payment`). Every attempt updates the
  receipt (status/attempts/last_error/backoff); the bot's
  `run_stars_payment_retry_loop` retries failed ones, and admins re-deliver
  or refund (`refundStarPayment`) from Магазин → Платежи Stars. A refunded
  receipt is never delivered and a delivered one never refunded (decided
  under the receipt's row lock). Availability is enforced at pre-checkout,
  not at delivery. The bot also serves `/paysupport` and `/terms`.
- **Card locks and squads**: `UserCard.is_user_locked` is the owner's own
  «замок» (`PATCH /collection/cards/lock`, bulk) — a locked copy is never
  sold or burned as material; it still plays and trades. `UserCard.can_burn()`
  is the material check (no squad flag, no trade/admin lock, no «замок»);
  player-tournament squads have no flag on the card, so material/Forge paths
  also check `collection_service.personal_squad_card_ids`. Improving a card
  (stars, diamond feeding, path, skill) is allowed while it plays; the Forge
  destroys the stake, so a squad copy needs `confirm_leave_squad`. Lists
  (`/collection/cards`, album, `/upgrade-cards`) return squad and locked
  copies as their own tiles (`in_personal_squad` flag); the UI shades them
  (`PlayerCard inSquad / userLocked`, `lib/cardLocks.ts`).
- **Card filter**: `users.card_filter_default` (`GET/PUT
  /collection/filter-default`) is the saved default for «Мои карты», the
  album and the Forge (`lib/cardFilter.ts` `useCardFilter`,
  `CardFilterBar`); `/collection/filter-options` lists the owner's countries
  and clubs.
- **Trade anti-farming / «Антифрод»**: `trade_guard_service` gates trades
  (GameConfig `trade_send_min_*`, `trade_daily_coins_receive_cap` — the cap is
  what stops a hub collecting millions in one evening — and `trade_coin_tax_pct`);
  `GameConfig.trades_enabled` switches trading off. Admin «Антифрод»
  (`admin_antifraud_service`, `/admin/antifraud/scan|ban`) finds hubs (coins
  from >= N distinct senders), the farm accounts that fed them and
  registration bursts, and bans in bulk (payers of Stars are flagged, never
  pre-selected; admins are never banned). Admin adjustments may take a balance
  below zero (migration 0164) — used to claw back already-spent farm coins.
- **Frontend routing**: one React app serves both the Mini App (`/`, `/packs`,
  `/play/*`, `/collection`, …) and the admin panel (`/admin/*`, gated by
  `AdminGuard` client-side and `get_current_admin` server-side). State:
  Zustand for client state (`authStore`, `uiStore`, and `matchGuardStore`
  which blocks in-app navigation during a live match and also fires a
  `pagehide` keepalive `fetch` so a real tab close/reload still records a
  forfeit), TanStack Query for server state.
- **Admin analytics**: `user_daily_activity` holds one row per user per
  local day (settings.timezone), written by `activity_service.record_daily_activity`
  from the same once-a-day spot in `core/dependencies.py` that advances the
  login streak (`users.last_seen_at` alone can't answer "came back on day 7").
  `admin_analytics_service.py` (`GET /admin/dashboard/analytics`) derives DAU/
  WAU/MAU, retention cohorts, the new-player funnel, mode popularity and Stars
  monetization from it plus the per-mode tables listed in `MODE_SOURCES` —
  add a new game mode there. History before migration 0150 is backfilled from
  timestamped activity, so it's a lower bound.
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
test DB. Concurrency/locking tests that need real Postgres use the `real_pg`
fixture (`tests/conftest.py`, logic in `tests/real_postgres.py`) — use it for
any new one, never a hand-rolled `create_async_engine`:

- They write to a **separate database whose name must end in `_test`**, never
  the app's own: `REAL_POSTGRES_URL` if set, otherwise the process's
  `DATABASE_URL` with `_test` appended (inside the backend container:
  `footycards_test` on the compose `postgres`). Any other database name fails
  the test. A missing test DB is created and `alembic upgrade head`-ed once
  per pytest session; it is disposable — drop it any time.
- Each test snapshots the max primary key of every table and on teardown
  (pass or fail) deletes every row created after it, children first —
  including rows the code under test created (tournaments, transactions,
  user_cards, …). Tests don't write their own cleanup.
- Unreachable server → the tests skip, so plain SQLite runs stay green.

```bash
# inside the dev stack (writes to footycards_test on the compose postgres):
docker compose exec backend pytest tests/ -v
# from the host against the compose postgres (port 5434):
REAL_POSTGRES_URL=postgresql+asyncpg://postgres:<password>@localhost:5434/footycards_test pytest tests/ -v
```

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
