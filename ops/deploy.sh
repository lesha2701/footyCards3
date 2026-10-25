#!/usr/bin/env bash
# Деплой одной командой: бэкап → git pull → сборка → миграции → проверка.
#   ./ops/deploy.sh             — с бэкапом
#   ./ops/deploy.sh --no-backup — без бэкапа (если нет новых миграций)
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
step() { echo; echo "=== $* ==="; }
fail() { echo; echo "❌ ДЕПЛОЙ НЕ УДАЛСЯ: $*"; exit 1; }

step "1/5 Забираю код"
BEFORE=$(git rev-parse HEAD)
git pull --ff-only || fail "git pull (есть локальные изменения на сервере?)"
AFTER=$(git rev-parse HEAD)
NEW_MIGRATIONS=$(git diff --name-only "$BEFORE" "$AFTER" -- backend/alembic/versions | wc -l)
echo "Было $(git rev-parse --short "$BEFORE"), стало $(git rev-parse --short "$AFTER"). Новых миграций: $NEW_MIGRATIONS"

step "2/5 Бэкап"
if [ "${1:-}" = "--no-backup" ]; then
  echo "Пропущен (--no-backup)"
else
  ./ops/backup.sh || fail "бэкап"
fi

step "3/5 Сборка и перезапуск (несколько минут)"
$COMPOSE up --build -d || fail "docker compose up"

step "4/5 Жду, пока бэкенд поднимется"
for i in $(seq 1 60); do
  if $COMPOSE exec -T backend curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "Бэкенд отвечает"; break
  fi
  [ "$i" = 60 ] && { $COMPOSE logs --tail=40 backend; fail "бэкенд не поднялся за 3 минуты (логи выше)"; }
  sleep 3
done

step "5/5 Проверяю миграции"
CURRENT=$($COMPOSE exec -T backend alembic current 2>/dev/null | grep -oE '^[0-9a-z_]+' | head -1)
HEAD=$($COMPOSE exec -T backend alembic heads 2>/dev/null | grep -oE '^[0-9a-z_]+' | head -1)
echo "База: $CURRENT, код: $HEAD"
[ -n "$CURRENT" ] && [ "$CURRENT" = "$HEAD" ] || fail "база не на последней миграции"

$COMPOSE ps --format '{{.Service}}: {{.State}}'
echo
echo "✅ ДЕПЛОЙ ГОТОВ ($(git log -1 --format='%h %s' | cut -c1-70))"
