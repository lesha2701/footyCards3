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

# Имя базы и пользователь берём из окружения контейнера postgres.
DB_NAME=$($COMPOSE exec -T postgres printenv POSTGRES_DB | tr -d '\r')
DB_USER=$($COMPOSE exec -T postgres printenv POSTGRES_USER | tr -d '\r')

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

# Копия вне сервера: бот присылает дамп в личку владельцу (@victor2289) —
# только ему, НЕ всем из ADMIN_TELEGRAM_IDS. BACKUP_TG=0 — выключить.
# Боты отправляют файлы до 50 МБ, поэтому дамп режется на части по 45 МБ.
# Собрать обратно:  cat footycards_ДАТА.dump.* > footycards_ДАТА.dump
BACKUP_TG_CHAT="488556166"
if [ "${BACKUP_TG:-1}" != "0" ]; then
  TOKEN=$($COMPOSE exec -T bot printenv TELEGRAM_BOT_TOKEN | tr -d '\r')
  if [ -z "$TOKEN" ]; then
    echo "Копия в Telegram пропущена: у бота нет токена"
  elif ! command -v curl > /dev/null; then
    echo "Копия в Telegram пропущена: на сервере нет curl (apt install curl)"
  else
    PARTS_DIR=$(mktemp -d)
    split -b 45M -d -a 2 "$OUT" "$PARTS_DIR/$(basename "$OUT")."
    TOTAL=$(ls "$PARTS_DIR" | wc -l)
    N=0
    FAILED=0
    for PART in "$PARTS_DIR"/*; do
      N=$((N + 1))
      if ! curl -sf -o /dev/null --max-time 600 \
          -F chat_id="$BACKUP_TG_CHAT" -F disable_notification=true \
          -F caption="💾 Бэкап $STAMP, часть $N/$TOTAL" \
          -F document=@"$PART" "https://api.telegram.org/bot$TOKEN/sendDocument"; then
        FAILED=1
      fi
    done
    rm -rf "$PARTS_DIR"
    if [ "$FAILED" = 0 ]; then
      echo "Копия отправлена в Telegram (@victor2289): $TOTAL ч."
    else
      echo "ВНИМАНИЕ: не все части ушли в Telegram (локальный дамп цел)"
    fi
  fi
fi
