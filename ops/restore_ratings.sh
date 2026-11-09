#!/usr/bin/env bash
# Вернуть очки Лиги, стёртые первым понедельничным обнулением «Топа недели»
# (тогда ещё не было копилки users.league_points — миграция 0268, запускать
# ПОСЛЕ деплоя). Рейтинги игр обнуляются каждую неделю по правилам — их не
# трогаем; очки Лиги из бэкапа (Арена + Тактико + Пенальти) кладём в копилку.
#
#   ./ops/restore_ratings.sh                      — показать бэкапы и время обнуления
#   ./ops/restore_ratings.sh ~/backups/X.dump     — проверка: что получится (ничего не меняет)
#   ./ops/restore_ratings.sh ~/backups/X.dump --apply   — вернуть очки (один раз)
#
# Берите ПОСЛЕДНИЙ бэкап, сделанный ДО обнуления. Каждому игроку:
#   копилка Лиги += очки Лиги из бэкапа
#                 + очки из матчей между бэкапом и обнулением.
# Набранное после обнуления остаётся в рейтингах этой недели.
# Бэкап разворачивается в отдельную базу <имя>_ratings_backup, рабочая база
# меняется одной транзакцией. Уже полученные награды лиги не выдаются второй раз.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
DB_NAME=$($COMPOSE exec -T postgres printenv POSTGRES_DB | tr -d '\r')
DB_USER=$($COMPOSE exec -T postgres printenv POSTGRES_USER | tr -d '\r')
OLD_DB="${DB_NAME}_ratings_backup"
DONE_MARK="${BACKUP_DIR:-$HOME/backups}/.ratings_restored"
q() { $COMPOSE exec -T postgres psql -U "$DB_USER" -v ON_ERROR_STOP=1 -q "$@"; }

echo "Обнуления рейтингов (раздача «Топа недели»):"
q -d "$DB_NAME" -c "SELECT week_start, settled_at FROM weekly_top_runs ORDER BY week_start DESC LIMIT 3"

DUMP="${1:-}"
if [ -z "$DUMP" ]; then
  echo "Бэкапы:"; ls -l "${BACKUP_DIR:-$HOME/backups}"/*.dump 2>/dev/null | tail -10
  echo; echo "Выберите последний бэкап ДО времени обнуления и запустите: ./ops/restore_ratings.sh <бэкап>"
  exit 0
fi
[ -f "$DUMP" ] || { echo "Нет файла $DUMP"; exit 1; }
if [ "${2:-}" = "--apply" ] && [ -f "$DONE_MARK" ]; then
  echo "Рейтинги уже возвращали ($(cat "$DONE_MARK")). Второй раз нельзя — очки удвоятся."; exit 1
fi

if q -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$OLD_DB'" | grep -q 1; then
  echo "База $OLD_DB уже развёрнута — беру её (чтобы развернуть заново, удалите её вручную)."
else
  echo "Разворачиваю бэкап в базу $OLD_DB (несколько минут)…"
  q -d postgres -c "CREATE DATABASE \"$OLD_DB\""
  $COMPOSE exec -T postgres pg_restore -U "$DB_USER" -d "$OLD_DB" --no-owner --no-privileges < "$DUMP"
fi

echo "Переношу рейтинги из бэкапа…"
q -d "$DB_NAME" <<'SQL'
DROP TABLE IF EXISTS ratings_backup;
CREATE TABLE ratings_backup (user_id int PRIMARY KEY, arena int, tactics int, penalty int);
DROP TABLE IF EXISTS ratings_backup_ids;
CREATE TABLE ratings_backup_ids (matches int, tactico int, penalty int);
SQL
q -d "$OLD_DB" -c "\copy (SELECT id, arena_rating, tactics_rating, penalty_rating FROM users) TO STDOUT" \
  | q -d "$DB_NAME" -c "\copy ratings_backup FROM STDIN"
q -d "$OLD_DB" -c "\copy (SELECT (SELECT coalesce(max(id),0) FROM matches), (SELECT coalesce(max(id),0) FROM tactico_matches), (SELECT coalesce(max(id),0) FROM penalty_matches)) TO STDOUT" \
  | q -d "$DB_NAME" -c "\copy ratings_backup_ids FROM STDIN"

FINISH="ROLLBACK"
[ "${2:-}" = "--apply" ] && FINISH="COMMIT"

q -d "$DB_NAME" <<SQL
BEGIN;
-- Время обнуления: последняя раздача «Топа недели».
CREATE TEMP TABLE reset_at AS SELECT max(settled_at) AS t FROM weekly_top_runs;
-- Матчи, сыгранные после бэкапа, но до обнуления (их очки обнуление стёрло).
CREATE TEMP TABLE gap AS
SELECT user_id, sum(arena) arena, sum(tactics) tactics, sum(penalty) penalty
FROM (
  SELECT user_id, rating_delta arena, 0 tactics, 0 penalty
    FROM matches WHERE id > (SELECT matches FROM ratings_backup_ids) AND created_at <= (SELECT t FROM reset_at)
  UNION ALL SELECT user_id, 0, rating_delta, 0
    FROM tactico_matches WHERE id > (SELECT tactico FROM ratings_backup_ids) AND created_at <= (SELECT t FROM reset_at)
  UNION ALL SELECT user_id, 0, 0, rating_delta
    FROM penalty_matches WHERE id > (SELECT penalty FROM ratings_backup_ids) AND created_at <= (SELECT t FROM reset_at)
) d GROUP BY user_id;

CREATE TEMP TABLE before_fix AS
SELECT id, league_points + arena_rating + tactics_rating + penalty_rating AS league FROM users;

UPDATE users u SET league_points = u.league_points + greatest(0,
  b.arena + b.tactics + b.penalty + coalesce(g.arena, 0) + coalesce(g.tactics, 0) + coalesce(g.penalty, 0))
FROM ratings_backup b LEFT JOIN gap g ON g.user_id = b.user_id
WHERE u.id = b.user_id;

\echo 'Игроков с возвращёнными очками Лиги:'
SELECT count(*) FROM users u JOIN before_fix f ON f.id = u.id
WHERE u.league_points + u.arena_rating + u.tactics_rating + u.penalty_rating <> f.league;
\echo 'Топ-20 Лиги после возврата (сейчас → станет):'
SELECT coalesce(u.username, u.first_name, u.telegram_id::text) AS player, f.league AS now_before_fix,
       u.league_points + u.arena_rating + u.tactics_rating + u.penalty_rating AS restored
FROM users u JOIN before_fix f ON f.id = u.id
ORDER BY restored DESC LIMIT 20;
$FINISH;
SQL

if [ "$FINISH" = "COMMIT" ]; then
  date '+%F %T' > "$DONE_MARK"
  echo "✅ Очки возвращены. Базу $OLD_DB можно удалить, когда убедитесь, что всё в порядке."
else
  echo; echo "Это была проверка — ничего не изменено. Если цифры верные: ./ops/restore_ratings.sh $DUMP --apply"
fi
