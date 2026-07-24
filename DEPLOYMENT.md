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

### Перед первым запуском: настройка Docker-демона

На некоторых серверах (особенно у российских хостеров) встречаются два
известных препятствия — лучше поправить их сразу, не дожидаясь ошибок:

```bash
sudo nano /etc/docker/daemon.json
```

Содержимое (создаёт файл, если его не было):

```json
{
  "registry-mirrors": ["https://mirror.gcr.io"],
  "ip6tables": true
}
```

- `registry-mirrors` — Docker Hub ограничивает анонимные скачивания образов
  по IP (обычно 100 запросов/6ч); при нескольких пересборках подряд лимит
  легко исчерпать, и `docker compose up --build` упадёт с `429 Too Many
  Requests`. Публичное зеркало Google снимает эту проблему.
- `ip6tables` — нужен для следующего шага (IPv6 наружу из контейнеров).

Применить:

```bash
sudo systemctl restart docker
```

### Если у сервера сломан IPv4-маршрут до Telegram (частая ситуация у РФ-хостеров)

У некоторых провайдеров исторически заблокирован/сломан **IPv4**-маршрut до
`api.telegram.org`, при этом **IPv6** работает нормально. Проверить прямо
сейчас:

```bash
curl -4 -s -o /dev/null -w "IPv4: %{http_code}, %{time_total}s\n" --max-time 8 https://api.telegram.org
curl -6 -s -o /dev/null -w "IPv6: %{http_code}, %{time_total}s\n" --max-time 8 https://api.telegram.org
```

Если IPv4 таймаутит, а IPv6 отвечает быстро — бот и любые вызовы Telegram API
из backend (проверка подписки на канал для премиум-заданий) будут падать по
таймауту, если контейнерам не дать реальный выход в IPv6. Это уже заложено в
`docker-compose.prod.yml` этого репозитория (секция `networks.default` с
`enable_ipv6: true`) — просто убедитесь, что `ip6tables: true` стоит в
`daemon.json` (см. выше) до первого `up`.

Если оба запроса выше отвечают одинаково быстро — можете просто это игнорировать,
у вас такой проблемы нет.

### Запуск

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
- **`docker compose up --build` падает с `429 Too Many Requests` при
  скачивании базовых образов (`python:3.12-slim`, `node:20-alpine` и т.д.).**
  Docker Hub ограничивает анонимные pull'ы по IP. Настройте зеркало — см.
  «Перед первым запуском» в Шаге 8 (`registry-mirrors` в
  `/etc/docker/daemon.json`), затем `sudo systemctl restart docker` и
  повторите сборку.
- **Бот и/или backend не могут достучаться до Telegram (`TelegramNetworkError:
  Request timeout error`, или у backend не работает проверка подписки на
  канал для премиум-заданий), при этом с самого сервера `curl
  https://api.telegram.org` работает.** Скорее всего у хостера сломан именно
  IPv4-маршрут до Telegram, а IPv6 — рабочий (проверить: `curl -4`/`curl -6`
  на `https://api.telegram.org`, см. Шаг 8). Контейнерам по умолчанию IPv6
  недоступен даже если у хоста он есть. Решение уже в
  `docker-compose.prod.yml` этого репозитория (`networks.default.enable_ipv6:
  true` + `ip6tables: true` в `daemon.json`) — если ловите эту ошибку на
  чистом сервере, значит `daemon.json` ещё не поправлен или Docker не
  перезапущен после правки; либо сеть нужно пересоздать (`docker compose -f
  docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml
  up --build -d`, просто `up` без `down` не применит новые настройки сети к
  уже существующей сети).

---

## Если Telegram в целом ограничен в вашей стране: прокси для бота и backend

IPv6-фикс из Шага 8 помогает только когда ломался конкретно IPv4-маршрут. Если
Telegram у вас ограничен на уровне страны/провайдера более широко — бот и
проверка подписки на канал (backend) будут работать нестабильно даже с
рабочим IPv6. Решение — завернуть все запросы к `api.telegram.org` через
прокси на сервере за пределами страны.

Поддержка прокси уже встроена в код (`TELEGRAM_PROXY_URL` в `.env`,
используется и ботом, и backend'ом). Не хватает только самого прокси-сервера.

### 1. Арендовать небольшой сервер за рубежом

Любой дешёвый VPS ($3-5/мес) вне зоны ограничений — Hetzner, DigitalOcean,
Vultr, Contabo и т.п. Отдельная сущность от основного сервера с
`footycards.ru` — этот VPS нужен только как точка выхода для трафика к
Telegram, ресурсы ему нужны минимальные (1 vCPU / 512MB-1GB RAM хватает с
запасом).

### 2. Поднять на нём SOCKS5-прокси (microsocks — маленький, простой, без лишнего)

```bash
ssh root@<IP-зарубежного-сервера>
apt update && apt install -y git build-essential
git clone https://github.com/rofl0r/microsocks.git
cd microsocks
make
sudo make install
```

Создать systemd-сервис, чтобы прокси работал постоянно и поднимался после
перезагрузки:

```bash
sudo nano /etc/systemd/system/microsocks.service
```

Содержимое (замените `ваш_логин`/`ваш_пароль` на свои — прокси смотрит в
интернет, обязательно с аутентификацией):

```ini
[Unit]
Description=microsocks SOCKS5 proxy
After=network.target

[Service]
ExecStart=/usr/local/bin/microsocks -1 -u ваш_логин -P ваш_пароль -p 1080
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now microsocks
sudo systemctl status microsocks
```

Откройте порт 1080 в файрволе этого (зарубежного) сервера:

```bash
ufw allow 1080/tcp
```

### 3. Подключить прокси на основном сервере (footycards.ru)

В `.env` основного сервера:

```
TELEGRAM_PROXY_URL=socks5://ваш_логин:ваш_пароль@<IP-зарубежного-сервера>:1080
```

Пересоздать контейнеры:

```bash
cd ~/footyCards3
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

### 4. Проверить

```bash
docker compose -f docker-compose.prod.yml exec bot python -c "
from config import get_bot_settings
print('proxy set to:', get_bot_settings().telegram_proxy_url)
"
docker compose -f docker-compose.prod.yml logs --tail 30 bot
```

Должно быть `"Starting bot in webhook mode on port 8081"` без таймаутов.
Напишите боту `/start` в Telegram — теперь запросы идут через зарубежный
сервер и не должны зависеть от ограничений в вашей стране.

**Важно:** прокси-сервер становится единой точкой отказа для связи с
Telegram — если он упадёт, бот перестанет отвечать. Для небольшого проекта
это приемлемый компромисс; при росте нагрузки стоит рассмотреть резервный
прокси или готовый прокси-сервис с SLA.

---

## Полный переезд на другой сервер (с сохранением данных)

Радикальное решение той же проблемы — вместо прокси перенести весь проект
на сервер за пределами страны. План ниже переносит **всё как есть**:
пользователей, балансы, купленные карточки, историю транзакций, импортированных
игроков. Домен `footycards.ru` не меняется — меняется только IP, на который
он указывает, поэтому в BotFather ничего перенастраивать не придётся.

Порядок важен: сначала полностью готовим новый сервер и проверяем его
локально (пока DNS ещё указывает на старый), и только в конце — одним
быстрым переключением DNS — переводим трафик. Так старый сервер продолжает
отвечать пользователям всё время, пока новый готовится.

### Этап 1. Арендовать новый сервер и подготовить его — как обычный деплой, но не трогая DNS

Пройдите Шаги 1, 3, 4, 5 из начала этого файла **на новом сервере**:
арендовать VPS за пределами страны, первичная настройка (файрвол, Docker),
скачать код (`git clone`), настроить `.env` (те же значения, что были на
старом сервере — тот же `TELEGRAM_BOT_TOKEN`, тот же `JWT_SECRET` можно
оставить или сменить, `DB_PASSWORD` можно сгенерировать новый).

**Пока не делайте:**
- Шаг 2 (DNS) — домен пока должен указывать на старый сервер.
- Шаг 6 (Caddy) — сертификат Let's Encrypt не выпустится, пока DNS не
  указывает на этот сервер. Вернёмся к этому в Этапе 6.

Раз новый сервер (предположительно) не в РФ — можно сразу убрать
`TELEGRAM_PROXY_URL` из `.env`, если использовали прокси, и не переживать за
IPv4/IPv6 до Telegram — но сначала проверьте:

```bash
curl -4 -s -o /dev/null -w "IPv4: %{http_code}, %{time_total}s\n" --max-time 8 https://api.telegram.org
```

### Этап 2. Снять дамп базы данных со старого сервера

На **старом** сервере:

```bash
cd ~/footyCards3
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U postgres -Fc footycards > ~/footycards_backup.dump
```

(`-Fc` — сжатый «custom»-формат, восстанавливается через `pg_restore` и
надёжнее обычного SQL-дампа).

### Этап 3. Передать дамп на новый сервер

Проще всего через свой Mac как промежуточное звено:

```bash
scp root@<IP-старого-сервера>:~/footycards_backup.dump ~/Downloads/footycards_backup.dump
scp ~/Downloads/footycards_backup.dump root@<IP-нового-сервера>:~/footycards_backup.dump
```

### Этап 4. Восстановить базу на новом сервере

Важно поднять **сначала только postgres**, не давая `backend` создать пустые
таблицы через Alembic раньше, чем мы восстановим дамп:

```bash
cd ~/footyCards3
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml exec postgres pg_isready -U postgres

cat ~/footycards_backup.dump | docker compose -f docker-compose.prod.yml exec -T postgres pg_restore -U postgres -d footycards --no-owner

# Теперь поднимаем всё остальное — Alembic увидит, что база уже на
# актуальной ревизии, и ничего не станет пересоздавать
docker compose -f docker-compose.prod.yml up --build -d
```

Проверить, что данные реально восстановились:

```bash
docker compose -f docker-compose.prod.yml exec backend python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.player import Player
from sqlalchemy import func, select

async def main():
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(func.count(User.id)))).scalar_one()
        players = (await db.execute(select(func.count(Player.id)))).scalar_one()
        print('users:', users, '| players:', players)

asyncio.run(main())
"
```

Числа должны совпадать с тем, что было на старом сервере.

### Этап 5. Отключить старый сервер от трафика

На **старом** сервере — остановить контейнеры, чтобы во время переключения
DNS не было двух серверов, одновременно принимающих запросы:

```bash
cd ~/footyCards3
docker compose -f docker-compose.prod.yml down
```

С этого момента `footycards.ru` временно недоступен — это ожидаемо, пока не
переключим DNS и не поднимем Caddy на новом сервере (обычно несколько минут).

### Этап 6. Переключить DNS

В личном кабинете reg.ru (в панели хостинга — там же, где добавляли
A-запись изначально) поменяйте значение A-записи `footycards.ru.` с IP
старого сервера на IP нового. Подождите 10-15 минут.

Проверить, что обновилось:

```bash
curl -s "https://dns.google/resolve?name=footycards.ru&type=A"
```

### Этап 7. HTTPS на новом сервере

Теперь, когда DNS указывает на новый сервер, можно пройти Шаг 6 основного
гайда (установка Caddy) — сертификат Let's Encrypt выпустится успешно, так
как ACME-проверка увидит правильный IP.

### Этап 8. Финальная проверка

- `curl https://footycards.ru/api/health` — должен ответить `{"status":"ok",...}`.
- Открыть бота в Telegram, `/start` — должен ответить.
- Открыть мини-апп — старые пользователи должны увидеть свой прежний
  баланс и карточки (те, кто уже играл на старом сервере).
- `/admin` → раздел «Коллекции карт» → убедиться, что World Cup 2026 и 125
  игроков на месте.

### Этап 9. Освободить старый сервер

Когда убедились, что новый сервер стабильно работает несколько дней —
можно отменить/удалить старый VPS у провайдера (в его личном кабинете, вне
Docker — зависит от провайдера).
