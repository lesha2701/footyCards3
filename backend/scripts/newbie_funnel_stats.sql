-- Воронка новичков рекламы: где отваливаются. Только чтение.
-- Когорта: пришедшие по рекламным меткам 8 ноября (поменяй дату под кампанию).
SET default_transaction_read_only = on;
\pset footer off

WITH c AS (
  SELECT u.id, CASE WHEN u.acquisition_source LIKE 'penalty%' THEN 'пенальти' ELSE 'прямая' END AS link
  FROM users u
  WHERE u.acquisition_source IS NOT NULL AND NOT u.is_banned AND u.created_at::date = DATE '2026-11-08'
), s AS (
  SELECT c.link, np.claimed::jsonb AS cl,
    EXISTS (SELECT 1 FROM game_sessions g WHERE g.user_id = c.id) AS minigame,
    EXISTS (SELECT 1 FROM matches m WHERE m.user_id = c.id) AS arena,
    (SELECT count(*) FROM pack_openings o WHERE o.user_id = c.id) AS packs,
    (SELECT count(DISTINCT a.day) FROM user_daily_activity a WHERE a.user_id = c.id) AS days
  FROM c LEFT JOIN newbie_progress np ON np.user_id = c.id
), t AS (
  SELECT link, count(*) AS total,
    count(*) FILTER (WHERE cl IS NOT NULL) AS path_started,
    count(*) FILTER (WHERE cl ? 'first_pack') AS first_pack,
    count(*) FILTER (WHERE cl ? 'squad_pack') AS squad_pack,
    count(*) FILTER (WHERE minigame) AS minigame,
    count(*) FILTER (WHERE arena) AS arena_match,
    count(*) FILTER (WHERE cl ? 'arena') AS arena_reward,
    count(*) FILTER (WHERE packs >= 3) AS packs_3plus,
    count(*) FILTER (WHERE days >= 2) AS came_back
  FROM s GROUP BY link
)
SELECT t.link, x.step, x.n, round(100.0 * x.n / t.total, 1) AS pct
FROM t, LATERAL (VALUES
  ('1 открыл приложение', t.total),
  ('2 начал путь дебютанта', t.path_started),
  ('3 открыл Пак дебютанта', t.first_pack),
  ('4 открыл «Твоя команда»', t.squad_pack),
  ('5 сыграл любую мини-игру', t.minigame),
  ('6 сыграл матч Арены', t.arena_match),
  ('7 забрал награду за Арену', t.arena_reward),
  ('8 открыл 3+ паков', t.packs_3plus),
  ('9 вернулся в другой день', t.came_back)
) AS x(step, n)
ORDER BY t.link DESC, x.step;

\echo '=== Все шаги пути дебютанта (сколько отметили) ==='
SELECT k AS step, count(*) AS players
FROM newbie_progress np JOIN users u ON u.id = np.user_id, jsonb_object_keys(np.claimed::jsonb) AS k
WHERE u.acquisition_source IS NOT NULL AND u.created_at::date = DATE '2026-11-08'
GROUP BY k ORDER BY players DESC;
