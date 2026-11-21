# Load test: a wave of newcomers

`newcomers.py` plays N brand-new players arriving over a few seconds, as an
ad does. Each one signs its Telegram initData, then calls `POST /auth/session`,
fires the home screen's ~25 GETs in parallel, opens «Пак дебютанта», and
refreshes the home screen twice more.

Run it only against an isolated stand, never prod: the fake accounts would
end up in the real stats. The stand is the prod image and command on a
throwaway network:

```bash
docker network create fc-load
docker run -d --name fc-load-pg --network fc-load --cpus 3 -e POSTGRES_PASSWORD=load -e POSTGRES_DB=footycards postgres:16 -c max_connections=400 -c shared_buffers=1GB
docker run -d --name fc-load-redis --network fc-load redis:7-alpine
docker build -t fc-load-backend backend
docker run -d --name fc-load-backend --network fc-load --cpus 6 \
  -e ENVIRONMENT=production -e DEV_MODE=false \
  -e DATABASE_URL=postgresql+asyncpg://postgres:load@fc-load-pg:5432/footycards \
  -e RATE_LIMIT_REDIS_URL=redis://fc-load-redis:6379/0 \
  -e TELEGRAM_BOT_TOKEN=123456:LOADTEST -e DB_POOL_SIZE=20 -e DB_MAX_OVERFLOW=30 \
  fc-load-backend gunicorn app.main:app -k uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000 --workers 6 --max-requests 4000 --max-requests-jitter 800 --timeout 120
docker exec fc-load-backend python -m app.seed
```

Run the generator inside the same network. Docker Desktop's port forwarding
on Windows drops connections under load, and httpx is too slow a client, so
the script uses aiohttp:

```bash
docker run -d --name fc-load-gen --network fc-load -v "$PWD/ops/loadtest:/lt" python:3.12-slim sh -c "pip install -q aiohttp && sleep infinity"
docker exec fc-load-gen python /lt/newcomers.py --base http://fc-load-backend:8000/api/v1 --token 123456:LOADTEST --users 200 --ramp 30
```

`--users 200 --ramp 30` means 200 players over 30 s. The report lists each
endpoint's p50/p95/max and its status codes. The three 404 «не в клубе»
responses per player are normal. When done, remove the containers:

```bash
docker rm -f fc-load-gen fc-load-backend fc-load-redis fc-load-pg
docker network rm fc-load
```

## Results, 2026-11-21

Stand: 6 CPUs for the backend and 3 for Postgres, about 40k background
players and 1M cards. «Путь новичка» is the time to the pack plus two home
refreshes, 2–8 s of which are pauses the script makes on purpose.

| wave (за 30 с) | до правок | после |
|---|---|---|
| 100 | p95 ответа 6–12 с, путь новичка 23 с | p95 0.5 с, путь 5.6 с |
| 200 | p95 до 22 с, путь 37 с, ошибки 500 | p95 1–3 с, путь 7.7 с, без ошибок |
| 300 | — | пул БД исчерпан, 500-е: это предел стенда (~170 запросов/с) |

## `GET /home` (the same day)

The first screen used to be ~39 parallel requests: layout, home and
popups, captured in a browser. Now it is one `GET /home` (backend
`routers/home.py`, frontend `lib/homeBundle.ts`), plus `/clubs/me` for a
player without a club (its 404). Compare the two with `--bundle`.

| per newcomer | ~39 requests | `/home` |
|---|---|---|
| backend CPU | 1.3–1.6 s | 0.41–0.50 s |
| Postgres CPU | 0.65 s | 0.15 s |
| 300 за 30 с | path 55 s | path 8 s, no errors |
| limit of the stand | ~200 за 30 с | ~400 за 30 с |
