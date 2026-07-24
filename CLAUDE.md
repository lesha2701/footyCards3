# FootyCards3

## Project

Telegram Mini App for collecting football cards.

Main features:
- packs with staged opening animation;
- card collection, filtering and selling;
- game currency and daily rewards;
- Memory Sequence and Card Arena;
- player-to-player card exchanges;
- achievements, leaderboards and profile;
- Telegram bot and administrative panel.

## Stack

- Frontend: React 18, TypeScript, Vite, Zustand, TanStack Query,
  Tailwind CSS, Framer Motion.
- Backend: Python 3.12, FastAPI, async SQLAlchemy 2, Alembic,
  PostgreSQL, Pydantic v2.
- Bot: aiogram 3.
- Infrastructure: Docker Compose and Nginx.
- Tests: pytest and Vitest.

## Repository structure

- `backend/` — FastAPI API, models, schemas, services and tests.
- `frontend/` — Telegram Mini App and admin panel.
- `bot/` — aiogram Telegram bot.
- `nginx/` — production reverse proxy.
- `docker-compose.yml` — development environment.
- `docker-compose.prod.yml` — production environment.

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

Backend checks

cd backend
pytest tests/ -v
python -c "from app.main import app"

Frontend checks

cd frontend
npm run test
npm run typecheck
npm run build

Definition of done

A task is complete only when:

requested behavior is implemented;
existing architecture is respected;
relevant tests pass;
TypeScript typecheck passes for frontend changes;
no secrets or generated artifacts were added;
final response lists modified files and verification results.