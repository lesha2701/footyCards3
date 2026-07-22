# Football Cards — Telegram Mini App

Коллекционная карточная игра про футболистов внутри Telegram: паки с игроками,
коллекция, обмены, две мини-игры (Memory Sequence и Card Arena), ежедневные
награды, достижения и полноценная административная панель.

## Стек

- **Frontend**: React 18 + TypeScript + Vite, React Router, Zustand, TanStack Query,
  Tailwind CSS, Framer Motion, Axios, Telegram Mini Apps bridge (`window.Telegram.WebApp`).
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL,
  Pydantic v2, PyJWT (только для админ-сессий), aiogram 3 (бот).
- **Инфраструктура**: Docker, Docker Compose, Nginx (prod), pytest, Vitest.

## Структура репозитория

```text
footyCards3/
├── backend/            # FastAPI-приложение
│   ├── app/
│   │   ├── models/     # SQLAlchemy-модели (20+ таблиц)
│   │   ├── schemas/    # Pydantic-схемы
│   │   ├── routers/    # /api/v1/* + /api/v1/admin/*
│   │   ├── services/   # игровая логика (паки, обмены, матчи, кошелёк...)
│   │   ├── core/       # security, exceptions, pagination, rate-limit
│   │   ├── main.py     # точка входа FastAPI
│   │   └── seed.py     # seed-скрипт
│   ├── alembic/versions/0001_initial.py
│   ├── static/players/{common,rare,epic,legendary}/  # изображения игроков
│   ├── static/packs/                                  # изображения паков
│   ├── tests/          # pytest (35 тестов)
│   └── Dockerfile
├── frontend/           # React Mini App + админ-панель (/admin)
│   ├── src/pages/       # Главная, Паки, Играть, Коллекция, Обмены, Профиль
│   ├── src/admin/        # административная панель
│   ├── src/components/, src/api/, src/store/, src/lib/
│   ├── src/test/        # Vitest (16 тестов)
│   └── Dockerfile
├── bot/                # aiogram 3 бот (polling/webhook)
│   ├── handlers/, services/, db.py, bot.py
│   └── Dockerfile
├── nginx/              # production reverse-proxy + сборка frontend
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml       # development
├── docker-compose.prod.yml  # production
├── .env.example
└── CLAUDE.md
```

## Переменные окружения

Скопируйте `.env.example` в `.env` и заполните значения:

```bash
cp .env.example .env
```

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `TELEGRAM_BOT_USERNAME` | Username бота без `@` (для deep link) |
| `ADMIN_TELEGRAM_IDS` | Telegram ID администраторов через запятую |
| `MINI_APP_URL` | Публичный HTTPS-URL фронтенда (для кнопки бота) |
| `BOT_MODE` | `polling` (dev) или `webhook` (prod) |
| `BOT_WEBHOOK_URL` / `BOT_WEBHOOK_SECRET` / `BOT_WEBHOOK_PORT` | Настройки webhook-режима |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Подключение к PostgreSQL |
| `DATABASE_URL` | Полная строка подключения (`postgresql+asyncpg://...`) |
| `JWT_SECRET` | Секрет для подписи admin-JWT (только админка) |
| `DEV_MODE` | `true` — разрешает вход без реального Telegram (заголовок `X-Dev-Mode: true`) |
| `DEV_USER_TELEGRAM_ID` | Telegram ID тестового dev-пользователя |
| `CORS_ORIGINS` | Разрешённые origin для CORS через запятую |
| `TIMEZONE` | Часовой пояс для расчёта ежедневных наград (например `Europe/Moscow`) |
| `STARTING_BALANCE` | Стартовый бонус монет при регистрации |
| `VITE_API_URL`, `VITE_STATIC_URL` | Базовые URL для фронтенда |
| `NGINX_PORT`, `BACKEND_PORT`, `FRONTEND_PORT` | Порты сервисов |

**Секреты не должны попадать в Git.** `.env` и `.env.local` уже в `.gitignore`.

## Запуск через Docker (рекомендуется)

### Development

```bash
docker compose up --build
```

Поднимет: `postgres`, `backend` (uvicorn --reload, порт 8000), `bot` (polling),
`frontend` (Vite dev-server с HMR, порт 5173).

Применить миграции и заполнить тестовыми данными (в отдельном терминале, после
того как контейнеры поднялись — миграции применяются автоматически при старте
`backend` через `docker-entrypoint.sh`, но seed нужно запустить вручную один раз):

```bash
docker compose exec backend python -m app.seed
```

Frontend: http://localhost:5173
Backend Swagger: http://localhost:8000/api/docs
Админ-панель: http://localhost:5173/admin (нужен Telegram ID из `ADMIN_TELEGRAM_IDS`)

### Production

```bash
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python -m app.seed   # опционально
```

Поднимет: `postgres`, `backend` (без reload, несколько воркеров), `bot`, `nginx`
(собирает production-бандл фронтенда и отдаёт его + проксирует `/api`, `/static`,
`/bot/webhook` на соответствующие сервисы). Приложение доступно на `http://<host>:${NGINX_PORT}`.

Изображения футболистов и паков подключены как volume (`./backend/static`), поэтому
переживают пересборку контейнеров.

## Запуск без Docker

Требуется локальный PostgreSQL, Python 3.12 и Node.js 20+.

### Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Применить миграции
alembic upgrade head

# Заполнить тестовыми данными
python -m app.seed

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

Backend читает конфигурацию из переменных окружения / `backend/.env` (см. `.env.example`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Откроется на http://localhost:5173, использует `VITE_API_URL`/`VITE_STATIC_URL`
из `.env` (по умолчанию — `http://localhost:8000`).

### Telegram-бот

```bash
cd bot
python -m venv .venv
.venv\Scripts\activate   # или source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

По умолчанию работает в режиме polling (`BOT_MODE=polling`).

## Тесты

### Backend (pytest, 35 тестов)

```bash
cd backend
pytest tests/ -v
```

Использует изолированную in-memory SQLite (не требует поднятого PostgreSQL).
Покрывает: проверку Telegram `initData` (валидная/подделанная подпись/чужой токен),
регистрацию и защиту от повторного стартового бонуса, dev-mode вход, открытие
пака (успех/атомарность/недостаточный баланс/гарантированная редкость/
idempotency-key), продажу карточек (включая предупреждение о последнем
экземпляре и блокировку карточек в составе), обмены (блокировка карточек,
принятие/отмена/повторное принятие, запрет обмена с самим собой), ежедневную
награду (получение/повторное получение в тот же день), Memory Sequence
(старт/верный и неверный ответ/начисление и повторное начисление награды),
составы и матчи (запрет использования чужой карточки, обязательность полного
состава, начисление энергии/наград), защиту административных маршрутов
(отсутствие токена, чужой не-админский токен, валидный админ-токен).

### Frontend (Vitest, 16 тестов)

```bash
cd frontend
npm run test
```

Покрывает утилиты (`rarity`, `formation`), Zustand-стор авторизации и рендер
ключевых компонентов (`EmptyState`, `PlayerCard`).

### Проверка сборки

```bash
cd frontend && npm run typecheck && npm run build
cd backend && python -c "from app.main import app"
```

## Настройка BotFather

1. Создайте бота через [@BotFather](https://t.me/BotFather) → `/newbot`, получите токен → в `TELEGRAM_BOT_TOKEN`.
2. `/setmenubutton` → выберите бота → отправьте текст кнопки (например «⚽ Играть») и URL Mini App
   (см. ниже — публичный HTTPS-адрес фронтенда).
3. `/setjoingroups`, `/setprivacy` — по желанию, не обязательны для работы Mini App.
4. Для локальной разработки Telegram требует HTTPS для WebApp URL — используйте
   туннель (например `ngrok http 5173` или `cloudflared tunnel --url http://localhost:5173`)
   и укажите полученный HTTPS-адрес в `/setmenubutton` и в `MINI_APP_URL`.

## Настройка URL Mini App

- `MINI_APP_URL` в `.env` — адрес, который бот использует в inline-кнопке
  «Открыть Football Cards» (`bot/keyboards.py`).
- Для production это URL вашего nginx (например `https://cards.example.com`).
- Для локальной разработки — туннель к `http://localhost:5173` (см. выше).

## Webhook или polling

- **Polling** (по умолчанию, проще для разработки): `BOT_MODE=polling`. Бот сам
  опрашивает Telegram, не требует публичного адреса.
- **Webhook** (рекомендуется для production): `BOT_MODE=webhook`,
  `BOT_WEBHOOK_URL=https://<ваш-домен>/bot/webhook`, `BOT_WEBHOOK_SECRET=<случайная строка>`.
  В `docker-compose.prod.yml` nginx уже проксирует `/bot/webhook` на сервис `bot`
  (порт `BOT_WEBHOOK_PORT`, по умолчанию 8081).

## Production-развёртывание (кратко)

1. Настройте DNS/сервер, установите Docker + Docker Compose.
2. Склонируйте репозиторий, создайте `.env` из `.env.example` с реальными
   секретами (`JWT_SECRET`, `TELEGRAM_BOT_TOKEN`, `DB_PASSWORD` и т.д.), `DEV_MODE=false`.
3. Настройте HTTPS перед nginx (например через внешний reverse-proxy/Let's
   Encrypt-терминатор — конфигурация в этом репозитории поднимает только HTTP на 80 порту).
4. `docker compose -f docker-compose.prod.yml up --build -d`.
5. `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head`.
6. Заполните продовые данные о футболистах через админ-панель (`/admin/players`,
   создание вручную или импорт CSV) — тестовый `app.seed` предназначен для demo/dev.
7. В BotFather укажите production `MINI_APP_URL`, переключите бота на webhook.

## Реализованные функции

- Безопасная Telegram-авторизация (проверка HMAC-подписи `initData` на сервере,
  автосоздание пользователя, стартовый бонус выдаётся один раз, dev-режим).
- Игровая валюта: стартовый бонус, ежедневная награда, мини-игры, матчи,
  достижения, продажа карточек, админ-корректировка — вся логика на backend,
  атомарные транзакции, журнал `coin_transactions`.
- Футбольные карточки: 44 тестовых футболиста всех 4 редкостей, 12 позиций,
  уникальные экземпляры с серийным номером, блокировки (в составе/в обмене/
  админом), локальные сгенерированные изображения (без внешних загрузок).
- 3 пака (Basic/Premium/Elite) с настраиваемыми вероятностями редкости,
  гарантированной минимальной редкостью, лимитами покупок и периодом продажи;
  открытие — атомарная транзакция с idempotency-key и защитой от гонки
  повторных запросов (проверено тестами и вручную).
- Поэтапная анимация открытия пака на Framer Motion (позиция → редкость →
  страна → клуб → силуэт → полное раскрытие), эффект свечения по редкости,
  ускорение по тапу, кнопка «Пропустить всё», итоговый экран с отметками
  «Новая»/дубликаты.
- Коллекция: фильтры (редкость/страна/клуб/позиция/рейтинг), поиск, сортировка,
  сетка, детальная карточка, быстрая и массовая продажа с подтверждением и
  предупреждением о последнем экземпляре.
- Memory Sequence: серверная сессия и раунды, длина растёт с каждым уровнем,
  дневной лимит наградных попыток, рекорд, таблица лидеров.
- Card Arena: состав 4-3-3, расчёт силы команды на backend (рейтинг + позиция +
  редкость + химия клуба/страны + случайность), матчи против бота или реального
  состава другого игрока, хронология событий, дневная энергия, статистика,
  рейтинг Arena, таблица лидеров, история матчей.
- Обмены: поиск игрока, предложение карточек/монет, блокировка карточек на
  время сделки, повторная проверка при принятии, авто-истечение через 24 часа,
  уведомления через Telegram-бота.
- Ежедневная награда на 7 дней (монеты/бесплатный пак/случайная карточка),
  проверка даты на backend с настраиваемым часовым поясом.
- Профиль (приватный/публичный), рейтинг, история транзакций (только у
  владельца/админа), достижения с автоматическим начислением.
- Административная панель: дашборд с графиками, пользователи (баланс, бан,
  выдача карточек, сброс лимитов, блокировка игровых наград), футболисты
  (CRUD, загрузка/удаление изображений, CSV импорт/экспорт, запрет удаления
  при наличии выданных карточек), паки (CRUD, предпросмотр вероятностей),
  обмены (принудительная отмена), игры (настройка наград/лимитов/сложности,
  подозрительные результаты), журнал административных действий.
- Telegram-бот: `/start`, `/profile`, `/help`, deep link приглашения,
  автодоставка уведомлений об обменах, напоминание о ежедневной награде,
  админ-команды (`/admin`, `/give_coins`, `/give_card`, `/ban`, `/unban`,
  `/stats`, `/announce_pack`) с проверкой Telegram ID.
- Безопасность: HMAC-проверка initData, серверная проверка всех игровых
  операций, защита от отрицательного баланса, блокировки строк `SELECT...FOR
  UPDATE`, idempotency-key для открытия пака, rate limiting критичных
  операций, валидация загружаемых файлов (тип/размер/безопасное имя), единый
  формат ошибок без внутренних stack trace, CORS по белому списку.

## Команды запуска (шпаргалка)

```bash
# Docker dev
docker compose up --build
docker compose exec backend python -m app.seed

# Docker prod
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Без Docker
cd backend && alembic upgrade head && python -m app.seed && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
cd bot && python bot.py

# Тесты
cd backend && pytest tests/ -v
cd frontend && npm run test
```

## Что фактически проверено в этой сессии

- `pytest tests/ -v` — **35/35 тестов пройдено** (backend, изолированная SQLite).
- `npm run test` (Vitest) — **16/16 тестов пройдено** (frontend).
- `npm run typecheck` и `npm run build` — фронтенд собирается без ошибок TypeScript.
- Alembic-миграция `0001_initial` применена к реальному локальному PostgreSQL
  (создаёт все таблицы, индексы, enum'ы, ограничения уникальности).
- `python -m app.seed` дважды выполнен на реальном PostgreSQL: идемпотентен,
  создаёт 44 футболиста (20/12/8/4 по редкости), 3 пака, достижения, dev-админа,
  5 тестовых пользователей, пример коллекции/состава/обмена, генерирует локальные
  placeholder-изображения (без внешних загрузок).
- Ручное сквозное тестирование через реальный запущенный backend (uvicorn) и
  frontend (Vite dev-server) в браузере: вход через dev-режим, главная,
  список паков, **полный цикл открытия пака с анимацией** (packshot → поэтапный
  reveal → summary), появление новых карточек в коллекции, получение ежедневной
  награды (баланс корректно изменился, повторное получение заблокировано),
  профиль с реальной статистикой и автоматически засчитанным достижением,
  админ-панель (дашборд с реальными агрегатами, список футболистов с пагинацией).
  В процессе этого тестирования найдены и исправлены два реальных бага:
  гонка при открытии пака с одинаковым idempotency-key (backend теперь
  корректно возвращает результат первого запроса вместо ошибки) и потеря
  подписки React Query `useMutation` при повторном вызове эффекта в
  React StrictMode (переписано на локальный `useState`/`useEffect`).
- Docker-compose файлы и Dockerfile'ы проверены статически (валидный YAML,
  корректные volume/healthcheck/depends_on), но **сборка образов и запуск через
  Docker не выполнялись** — в этом окружении не было доступа к Docker Engine.
  Backend и frontend полностью проверены в реальной работе напрямую (без
  контейнеров), что покрывает всю прикладную логику; Docker-слой воспроизводит
  ту же конфигурацию (тот же `requirements.txt`/`package.json`, тот же код).
- Telegram-бот: подключение к реальному Telegram Bot API проверено
  (`bot.get_me()` вернул `@footyCards5463bot`), сам процесс бота кратко
  запускался в режиме polling без ошибок при старте; полный цикл отправки
  сообщений реальному пользователю не тестировался (нет тестового Telegram-чата
  в этом окружении).

## Известные ограничения

- Массовая рассылка `/announce_pack` и напоминание о ежедневной награде из бота
  используют `bot.send_message` в цикле по всем пользователям — для очень
  большой базы пользователей это стоит заменить на очередь с ограничением
  скорости (Telegram лимитирует ~30 сообщений/сек).
- Rate limiting реализован in-memory (на процесс) — для горизontального
  масштабирования backend на несколько инстансов нужен внешний стор (Redis).
- Достижения начисляются по ограниченному набору метрик (`packs_opened`,
  `unique_players`, `trades_completed`) в соответствующих сервисах; добавление
  новой метрики требует явного вызова `evaluate_and_award` в нужном месте.
- Изображения футболистов — процедурно сгенерированные заглушки (цветной
  градиент по редкости + инициалы), а не реальные фотографии, как и требовалось
  в задании («не скачивай фотографии из интернета»); имена футболистов —
  вымышленные, чтобы не использовать чужие права на изображение/имя.
- CSV-импорт футболистов сопоставляет строки по `display_name` (upsert) — при
  массовом импорте с опечатками в имени возможны дубликаты.
- `npm audit` показывает несколько уязвимостей в dev-зависимостях (обычная
  ситуация для актуального Vite/Vitest-тулчейна на момент сборки) — не
  проверялось `npm audit fix --force`, так как это может подтянуть breaking-changes.
