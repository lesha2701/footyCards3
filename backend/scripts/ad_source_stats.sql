-- Реклама: откуда пришли игроки и что с ними стало. Только чтение, только итоги.
-- Запуск: docker compose -f docker-compose.prod.yml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/scripts/ad_source_stats.sql
-- Часть 1 считает метки ссылок (users.acquisition_source, ?startapp=penalty_vans).
-- Части 2 и 3 работают и для старой рекламы без меток.
SET default_transaction_read_only = on;
\pset footer off

\echo '=== 1. По меткам: регистрации, возврат, Stars ==='
WITH cohort AS (
  SELECT u.id, u.telegram_id, u.acquisition_source AS source, u.created_at::date AS day
  FROM users u WHERE u.acquisition_source IS NOT NULL AND NOT u.is_banned
), paid AS (
  SELECT r.telegram_user_id, sum(r.total_amount) AS stars
  FROM stars_payment_receipts r WHERE r.status = 'delivered' GROUP BY 1
)
SELECT c.source, count(*) AS new_users,
       count(DISTINCT c.id) FILTER (WHERE g.user_id IS NOT NULL) AS played_penalty,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = c.id AND a.day = c.day + 1)) AS d1,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = c.id AND a.day = c.day + 7)) AS d7,
       count(p.stars) AS payers, coalesce(sum(p.stars), 0) AS stars
FROM cohort c
LEFT JOIN LATERAL (SELECT user_id FROM game_sessions s WHERE s.user_id = c.id AND s.game_type::text = 'penalty' LIMIT 1) g ON true
LEFT JOIN paid p ON p.telegram_user_id = c.telegram_id
GROUP BY 1 ORDER BY new_users DESC;

\echo '=== 2. Регистрации по дням: день рекламы против обычного фона ==='
WITH days AS (
  SELECT u.created_at::date AS day, count(*) AS new_users FROM users u
  WHERE NOT u.is_banned AND u.created_at > now() - interval '60 days' GROUP BY 1
)
SELECT d.day, d.new_users, (SELECT count(*) FROM users u WHERE u.created_at::date = d.day AND u.referred_by_id IS NOT NULL) AS by_invite,
       round(avg(d.new_users) OVER (ORDER BY d.day ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)) AS prev_7d_avg
FROM days d ORDER BY d.day;

\echo '=== 3. Рекламная когорта: день 14 октября, возврат и Stars (поменяй дату под кампанию) ==='
WITH cohort AS (
  SELECT u.id, u.telegram_id, u.created_at::date AS day FROM users u
  WHERE u.created_at::date = DATE '2026-10-14' AND NOT u.is_banned
)
SELECT count(*) AS new_users,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = c.id AND a.day = c.day + 1)) AS d1,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = c.id AND a.day = c.day + 7)) AS d7,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = c.id AND a.day = c.day + 14)) AS d14,
       (SELECT count(DISTINCT r.telegram_user_id) FROM stars_payment_receipts r JOIN cohort x ON x.telegram_id = r.telegram_user_id WHERE r.status = 'delivered') AS payers,
       (SELECT coalesce(sum(r.total_amount), 0) FROM stars_payment_receipts r JOIN cohort x ON x.telegram_id = r.telegram_user_id WHERE r.status = 'delivered') AS stars
FROM cohort c;

\echo '=== 4. Подарок за возвращение: выдано и вернулись на следующий день ==='
SELECT to_char(date_trunc('week', g.gift_date), 'YYYY-MM-DD') AS week, count(*) AS gifts,
       round(avg(g.days_away)) AS avg_days_away,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = g.user_id AND a.day = g.gift_date + 1)) AS next_day,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_daily_activity a WHERE a.user_id = g.user_id AND a.day BETWEEN g.gift_date + 1 AND g.gift_date + 7)) AS within_7d
FROM comeback_gifts g GROUP BY 1 ORDER BY 1;
