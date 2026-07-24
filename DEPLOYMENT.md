# Деплой FootyCards на сервер (footycards.ru)

Пошаговый гайд, как выложить проект на реальный сервер, чтобы бот и мини-апп
работали не только локально. Ориентирован конкретно на файлы этого репозитория
(`docker-compose.prod.yml`, `nginx/`, `bot/`), а не на общие советы.

## Что мы получим в итоге

```
Интернет → footycards.ru (DNS) → сервер
                                    │
                             Caddy (443/80, HTTPS)   ← ставим на сервер отдельно от Docker
                                    │  proxy → 127.0.0.1:8080
                                    ▼
                     docker-compose.prod.yml:
                     ├── nginx    (порт 8080→80 внутри, раздаёт фронтенд + проксирует /api, /static, /bot/webhook)
                     ├── backend  (FastAPI, uvicorn, 2 воркера)
                     ├── bot      (aiogram, режим webhook)
                     └── postgres (данные в volume postgres_data)
```

HTTPS обязателен: Telegram Mini App и `bot.webhook` не работают без него. Сам
репозиторий поднимает только HTTP на 80 (см. `nginx/nginx.conf`), поэтому TLS
терминируем снаружи через **Caddy** — он сам получает и продлевает сертификат
Let's Encrypt, конфиг — 3 строчки.

---

## Шаг 1. Арендовать сервер (VPS)

Хватит минимальной конфигурации: **2 vCPU / 2–4 GB RAM / 40 GB SSD**, Ubuntu
22.04 или 24.04 LTS. Postgres + backend + bot + nginx в Docker на таком сервере
работают комфортно для старта проекта.

Варианты (любой на выбор, гайд не зависит от провайдера):
- Российские: Timeweb Cloud, Selectel, VK Cloud — удобны по оплате российской
  картой, если домен и аудитория в РФ.
- Зарубежные: Hetzner, DigitalOcean, Vultr — дешевле, но оплата обычно нужна
  картой с поддержкой международных платежей.

При создании сервера укажите свой SSH-публичный ключ (или используйте пароль,
если провайдер выдаёт его по умолчанию) — понадобится для шага 3.

Запишите **публичный IPv4-адрес** сервера — он понадобится в следующем шаге.

---

## Шаг 2. Прописать DNS для footycards.ru (в личном кабинете reg.ru)

Проверьте на странице «DNS-серверы и управление зоной» вашего домена, какие
DNS-серверы указаны, и выберите подходящий вариант ниже.

### Вариант А — стоят `ns1.reg.ru` / `ns2.reg.ru`

1. Зайдите в [личный кабинет reg.ru](https://www.reg.ru/), откройте раздел
   **Домены**, кликните на `footycards.ru`.
2. Найдите блок **«DNS-серверы и управление зоной»** и нажмите **«Изменить»**.
3. Нажмите **«Добавить запись»**, в открывшейся справа панели выберите тип
   **A**.
4. Заполните:
   - **Subdomain** — `@` (это значит «сам домен», без поддомена);
   - **IP-адрес** — публичный IPv4 вашего сервера (из Шага 1).
   - Нажмите **«Готово»**.
5. Повторите то же самое ещё раз, но с **Subdomain = `www`**, если хотите,
   чтобы сайт открывался и по адресу `www.footycards.ru` (не обязательно).

### Вариант Б — стоят `ns1.hosting.reg.ru` / `ns2.hosting.reg.ru`

Значит, к домену подключён бесплатный хостинг reg.ru, и ресурсные записи
редактируются не на странице домена, а в панели хостинга:

1. На странице «DNS-серверы и управление зоной» под блоком «Ресурсные записи»
   нажмите ссылку **«Управление DNS записями (A, MX, TXT, CNAME) на хостинге»**
   — откроется панель управления хостингом (ispmanager).
2. Раздел **«Управление DNS»** → кликните на `footycards.ru` → **«DNS
   записи»**.
3. **«Создать запись»** → тип **А**.
4. В поле **«Имя»** введите домен **с точкой в конце**: `footycards.ru.`
   (без точки запись создастся некорректно).
5. В поле IP-адрес — впишите IP вашего сервера → **«Ок»**.
6. При желании повторите с именем `www.footycards.ru.`.

DNS обновляется от 15 минут до часа (иногда дольше). Проверить, что применилось:

```bash
ping footycards.ru
# или
nslookup footycards.ru
```

Должен вернуться IP вашего сервера. Дальше можно продолжать, не дожидаясь
полного распространения DNS по всему миру — для большинства провайдеров
достаточно нескольких минут.

---

## Шаг 3. Первичная настройка сервера

Подключитесь по SSH (замените на свои данные от провайдера):

```bash
ssh root@<IP-адрес-сервера>
```

Обновить систему и поставить базовые утилиты:

```bash
apt update && apt upgrade -y
apt install -y curl git ufw
```

Настроить файрвол — открываем только SSH, HTTP и HTTPS (порт для бота/бэкенда
наружу открывать не нужно, они видны только внутри Docker-сети и через Caddy):

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

Поставить Docker Engine + Compose plugin (официальный скрипт):

```bash
curl -fsSL https://get.docker.com | sh
```

Проверить:

```bash
docker --version
docker compose version
```

(Опционально, но рекомендуется) создать отдельного пользователя вместо работы
под root:

```bash
adduser deploy
usermod -aG docker,sudo deploy
su - deploy
```

Дальше все команды выполняются от этого пользователя (или от root — на суть
гайда не влияет).

---

## Шаг 4. Скачать код на сервер

```bash
git clone https://github.com/lesha2701/footyCards3.git
cd footyCards3
```

Если репозиторий приватный — понадобится personal access token GitHub вместо
пароля при клонировании, либо настроенный deploy-key.

---

## Шаг 5. Настроить `.env` для продакшена

```bash
cp .env.example .env
nano .env   # или vim/любой редактор
```

Заполните файл реальными значениями:

| Переменная | Что поставить |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен вашего бота от [@BotFather](https://t.me/BotFather) (см. Шаг 7, если бота ещё нет) |
| `TELEGRAM_BOT_USERNAME` | Username бота без `@` |
| `ADMIN_TELEGRAM_IDS` | Ваш Telegram ID через запятую (узнать — см. врезку ниже) |
| `MINI_APP_URL` | `https://footycards.ru` |
| `BOT_MODE` | `webhook` (обязательно, `polling` для прода не годится) |
| `BOT_WEBHOOK_URL` | `https://footycards.ru/bot/webhook` |
| `BOT_WEBHOOK_SECRET` | Случайная строка — сгенерировать: `openssl rand -hex 32` |
| `BOT_WEBHOOK_PORT` | оставьте `8081` (по умолчанию) |
| `DB_NAME` / `DB_USER` | можно оставить `footycards` / `postgres` |
| `DB_PASSWORD` | **обязательно смените** на случайный пароль: `openssl rand -hex 24` |
| `DATABASE_URL` | оставить как в примере — подставит переменные автоматически |
| `JWT_SECRET` | **обязательно смените**: `openssl rand -hex 32` |
| `DEV_MODE` | значение здесь неважно — `docker-compose.prod.yml` принудительно задаёт `DEV_MODE=false` для backend-контейнера, что и требуется для продакшена |
| `ENVIRONMENT` | `production` |
| `CORS_ORIGINS` | `https://footycards.ru` |
| `TIMEZONE` | `Europe/Moscow` (или ваш часовой пояс — влияет на расчёт ежедневных наград) |
| `STARTING_BALANCE` | оставить как есть или поменять под свою экономику |
| `VITE_API_URL` / `VITE_STATIC_URL` | не используются в проде напрямую — их задаёт `nginx/Dockerfile` (`/api/v1`, `/static`), можно не трогать |
| `NGINX_PORT` | `8080` — см. пояснение ниже |

**Про `NGINX_PORT=8080`:** контейнер `nginx` в проде слушает 80-й порт внутри
себя, а наружу на хост публикуется `${NGINX_PORT}`. Если оставить `80`, он
займёт 80-й порт хоста — но этот порт нужен снаружи для Caddy (TLS-терминатора
из Шага 6). Поэтому выставляем `NGINX_PORT=8080`: Docker-nginx слушает
`127.0.0.1:8080` изнутри сервера, а на 80/443 снаружи отвечает уже Caddy и
проксирует туда трафик. Файрвол (Шаг 3) и так не пропускает внешние запросы на
8080 — задача решена без правки файлов репозитория.

**Как узнать свой Telegram ID:** напишите любое сообщение боту
[@userinfobot](https://t.me/userinfobot) — он ответит числовым ID.

---

## Шаг 6. HTTPS через Caddy

Ставим Caddy на сам сервер (не в Docker) — он не занимает 80/443 внутри
Compose, поэтому конфликта портов с `docker-compose.prod.yml` не будет.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Прописываем конфиг:

```bash
sudo nano /etc/caddy/Caddyfile
```

Содержимое (полностью заменяет то, что там было):

```
footycards.ru, www.footycards.ru {
    reverse_proxy 127.0.0.1:8080
}
```

Перезапустить:

```bash
sudo systemctl restart caddy
sudo systemctl enable caddy
```

Caddy сам получит сертификат Let's Encrypt при первом запросе (важно: DNS из
Шага 2 уже должен указывать на сервер, иначе выпуск сертификата не пройдёт) и
будет сам продлевать его — никакого cron с certbot настраивать не нужно.

Проверить, что Caddy запустился без ошибок:

```bash
sudo systemctl status caddy
sudo journalctl -u caddy -f    # логи, Ctrl+C для выхода
```

---

## Шаг 7. (Если бота ещё нет) Создать бота в BotFather

1. Откройте [@BotFather](https://t.me/BotFather) → `/newbot`, следуйте
   инструкциям, получите токен → впишите в `.env` как `TELEGRAM_BOT_TOKEN`.
2. `/setmenubutton` → выберите бота → отправьте текст кнопки (например,
   «⚽ Играть») и URL `https://footycards.ru`.
3. `/setjoingroups` и `/setprivacy` — не обязательны для работы Mini App,
   настраиваются по желанию.

Если бот уже был создан для локальной разработки — просто используйте тот же
токен, здесь ничего создавать заново не нужно, но `/setmenubutton` всё равно
нужно перенастроить на `https://footycards.ru` (был указан туннель для
локальной разработки).

---

## Шаг 8. Запустить стек

```bash
cd ~/footyCards3
docker compose -f docker-compose.prod.yml up --build -d
```

Первая сборка образов (особенно фронтенда) может занять несколько минут.
Проверить статус:

```bash
docker compose -f docker-compose.prod.yml ps
```

Все сервисы должны быть `Up` (postgres и backend — `healthy`). Если
что-то не стартовало — смотрите логи:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f bot
```

Миграции Alembic применяются **автоматически** при старте контейнера
`backend` (см. `backend/docker-entrypoint.sh`) — вручную запускать
`alembic upgrade head` не обязательно, но можно как проверку:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic current
```

Должно показать последнюю ревизию (`0004 (head)`).

### Тестовые данные (опционально)

`python -m app.seed` создаёт 44 демо-футболиста, 3 демо-пака и тестовых
пользователей — удобно, чтобы сразу увидеть, что всё работает:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.seed
```

Для реального продакшена футболистов правильнее заводить через админ-панель
(вручную или CSV-импортом) — `seed` предназначен для демонстрации/разработки.

---

## Шаг 9. Проверить, что всё работает

1. Откройте бота в Telegram, нажмите `/start` — должен ответить и показать
   кнопку меню.
2. Нажмите кнопку меню (или `/start` → кнопка «Открыть FootyCards») — должен
   открыться Mini App на `https://footycards.ru` внутри Telegram.
3. Пройдите авторизацию (происходит автоматически, по вашему Telegram-аккаунту),
   откройте список паков, попробуйте открыть один.
4. Проверьте админ-панель: напишите боту `/admin` (сработает только если ваш
   Telegram ID указан в `ADMIN_TELEGRAM_IDS`) — бот пришлёт кнопку, которая
   откроет Mini App сразу на `/admin`.

**Важно:** админ-панель, как и весь Mini App, работает только через реальные
Telegram-данные (`window.Telegram.WebApp.initData`) — открыть
`https://footycards.ru/admin` напрямую в обычном браузере не получится (в
проде `DEV_MODE=false`, обхода нет). Для удобной работы с админкой (загрузка
CSV с футболистами и т.п.) лучше использовать **Telegram Desktop** — там
Mini App открывается в увеличенном окне, а не на маленьком экране телефона.

---

## Дальнейшая эксплуатация

### Обновление кода (передеплой после изменений)

```bash
cd ~/footyCards3
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

Миграции (если добавлялись новые) применятся автоматически при перезапуске
`backend`.

### Бэкапы базы данных

Данные Postgres лежат в Docker volume `postgres_data`. Простой бэкап дампом:

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U postgres footycards > backup_$(date +%Y%m%d).sql
```

Стоит добавить это в cron (например, раз в сутки) и копировать файл за
пределы сервера (например, в облачное хранилище).

### Логи

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f nginx
```

### Обновление сертификата

Ничего делать не нужно — Caddy продлевает сертификат Let's Encrypt
автоматически в фоне.

---

## Частые проблемы

- **Caddy не может получить сертификат.** Почти всегда — DNS ещё не
  распространился (проверьте `nslookup footycards.ru` с самого сервера) или
  порт 80 занят чем-то другим (проверьте `sudo ss -tlnp | grep :80` — там
  должен быть только `caddy`).
- **Бот не отвечает после деплоя.** Проверьте `docker compose -f
  docker-compose.prod.yml logs bot` — частая причина: неверный
  `BOT_WEBHOOK_URL`/`BOT_WEBHOOK_SECRET` в `.env`, либо Caddy ещё не поднял
  сертификат (Telegram не примет вебхук на URL без валидного HTTPS).
- **Mini App открывается, но авторизация падает с ошибкой.** Проверьте, что
  `MINI_APP_URL`, `CORS_ORIGINS` совпадают с реальным доменом
  (`https://footycards.ru`, без опечаток и без `www`, если в BotFather указан
  домен без `www`).
- **502 Bad Gateway от Caddy.** Значит docker-контейнеры ещё не поднялись
  или упали — смотрите `docker compose -f docker-compose.prod.yml ps` и логи.
