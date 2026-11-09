#!/usr/bin/env bash
# Вернуть монеты болельщикам «Менеджера», которые купили мерч, когда клуб уже
# собрал сезонный максимум (manager_merch_cap_eur): монеты списались, а клуб
# получил €0 (manager_merch.eur = 0). Предмет и статус болельщика остаются.
#
#   ./ops/refund_merch.sh           — проверка: кому и сколько вернётся (ничего не меняет)
#   ./ops/refund_merch.sh --apply   — вернуть монеты (один раз)
#
# Всё одной транзакцией: баланс игрока + строка в истории монет + уведомление;
# у возвращённых покупок coins становится 0, так что второй запуск ничего не найдёт.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
DB_NAME=$($COMPOSE exec -T postgres printenv POSTGRES_DB | tr -d '\r')
DB_USER=$($COMPOSE exec -T postgres printenv POSTGRES_USER | tr -d '\r')
DONE_MARK="${BACKUP_DIR:-$HOME/backups}/.merch_refunded"

if [ "${1:-}" = "--apply" ] && [ -f "$DONE_MARK" ]; then
  echo "Монеты за мерч уже возвращали ($(cat "$DONE_MARK"))."; exit 1
fi
FINISH="ROLLBACK"
[ "${1:-}" = "--apply" ] && FINISH="COMMIT"

$COMPOSE exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q <<SQL
BEGIN;
CREATE TEMP TABLE refund AS
SELECT m.user_id, sum(m.coins)::int AS coins, count(*) AS items
FROM manager_merch m WHERE m.eur = 0 AND m.coins > 0 GROUP BY m.user_id;
-- Балансы этих игроков не должны поменяться посреди возврата.
SELECT id FROM users WHERE id IN (SELECT user_id FROM refund) FOR UPDATE \g /dev/null

\echo 'Покупок без пользы для клуба / игроков / монет к возврату:'
SELECT coalesce(sum(items), 0) AS items, count(*) AS players, coalesce(sum(coins), 0) AS coins FROM refund;
\echo 'По клубам:'
SELECT c.name AS club, count(*) AS items, sum(m.coins) AS coins
FROM manager_merch m JOIN manager_clubs c ON c.id = m.club_id
WHERE m.eur = 0 AND m.coins > 0 GROUP BY c.name ORDER BY coins DESC LIMIT 20;
\echo 'Кому больше всех (топ-20):'
SELECT coalesce(u.username, u.first_name, u.telegram_id::text) AS player, r.items, r.coins
FROM refund r JOIN users u ON u.id = r.user_id ORDER BY r.coins DESC LIMIT 20;

INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, related_object_type, created_at)
SELECT u.id, r.coins, u.balance, u.balance + r.coins, 'admin_adjustment',
       'Возврат за мерч, который не дал клубу денег (' || r.items || ' шт.)', 'manager_merch', now()
FROM refund r JOIN users u ON u.id = r.user_id;
INSERT INTO notifications (user_id, type, title, body, is_read, telegram_sent, created_at)
SELECT r.user_id, 'admin_message', 'Вернули ' || r.coins || ' монет за мерч',
       'Клуб уже собрал максимум с мерча в сезоне, и твоя покупка не принесла ему денег. Монеты вернули, мерч остаётся у тебя.',
       false, false, now()
FROM refund r;
UPDATE users u SET balance = u.balance + r.coins FROM refund r WHERE u.id = r.user_id;
UPDATE manager_merch SET coins = 0 WHERE eur = 0 AND coins > 0;
$FINISH;
SQL

if [ "$FINISH" = "COMMIT" ]; then
  date '+%F %T' > "$DONE_MARK"
  echo "✅ Монеты возвращены, игрокам ушли уведомления."
else
  echo; echo "Это была проверка — ничего не изменено. Если цифры верные: ./ops/refund_merch.sh --apply"
fi
