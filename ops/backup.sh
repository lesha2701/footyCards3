#!/usr/bin/env bash
# Дамп базы в ~/backups (custom-формат, сжатый). Проверяет, что дамп
# читается, и удаляет дампы старше KEEP_DAYS дней.
#   ./ops/backup.sh            — вручную
#   cron: 30 4 * * * /root/footyCards3/ops/backup.sh >> /root/backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

# Имя базы и пользователь — из .env (только читаем).
DB_NAME=$(grep -E '^DB_NAME=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
DB_USER=$(grep -E '^DB_USER=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
DB_NAME="${DB_NAME:-footycards}"
DB_USER="${DB_USER:-postgres}"

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d_%H%M)
OUT="$BACKUP_DIR/${DB_NAME}_${STAMP}.dump"
TMP="$OUT.part"

echo "[$(date '+%F %T')] Бэкап $DB_NAME → $OUT (обычно 1–3 минуты, во время дампа ничего не печатается)..."
$COMPOSE exec -T postgres pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$TMP"

SIZE=$(stat -c %s "$TMP")
if [ "$SIZE" -lt 10000 ]; then
  echo "ОШИБКА: дамп подозрительно маленький ($SIZE байт), оставлен как $TMP"
  exit 1
fi
# Дамп должен читаться: pg_restore --list разбирает оглавление файла.
if ! $COMPOSE exec -T postgres pg_restore --list < "$TMP" > /dev/null; then
  echo "ОШИБКА: дамп не читается, оставлен как $TMP"
  exit 1
fi
mv "$TMP" "$OUT"

find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime +"$KEEP_DAYS" -delete
echo "[$(date '+%F %T')] ГОТОВО: $(du -h "$OUT" | cut -f1). Всего дампов: $(ls "$BACKUP_DIR"/${DB_NAME}_*.dump | wc -l), место: $(df -h "$BACKUP_DIR" | awk 'NR==2{print $4}') свободно"
