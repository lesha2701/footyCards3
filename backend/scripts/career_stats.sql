-- «Карьера тренера», только чтение, только итоги без игроков (все режимы — scripts/mode_stats.py).
-- Запуск: docker compose -f docker-compose.prod.yml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/scripts/career_stats.sql
-- Матчи и настройки берутся за последние 60 дней: state большой, старые сезоны не нужны.
SET default_transaction_read_only = on;
\pset footer off

-- Матчи людей из JSON один раз: ниже их читают почти все разделы.
\set recent 'created_at > now() - interval \'60 days\''
\set human_matches '(SELECT p.id AS part, p.user_id, COALESCE(p.division, s.division) AS division, s.status AS season_status, r.n - 1 AS round, (m->>''hs'')::int AS hs, (m->>''as'')::int AS gs, (m->>''home'')::int = p.team_index AS is_home, m->''tactics''->(p.team_index::text) AS played FROM career_participants p JOIN career_seasons s ON s.id = p.season_id AND s.created_at > now() - interval ''60 days'', json_array_elements(s.state->''results'') WITH ORDINALITY r(rnd, n), json_array_elements(r.rnd) m WHERE p.status IN (''accepted'', ''left'') AND p.team_index IN ((m->>''home'')::int, (m->>''away'')::int))'
\set outcomes '(SELECT *, CASE WHEN is_home THEN hs ELSE gs END AS own, CASE WHEN is_home THEN gs ELSE hs END AS opp FROM :human_matches x)'

\echo '=== 1. Размер режима ==='
SELECT count(*) AS coaches,
       count(*) FILTER (WHERE c.last_active_at > now() - interval '1 day') AS opened_1d,
       count(*) FILTER (WHERE c.last_active_at > now() - interval '7 days') AS opened_7d,
       count(*) FILTER (WHERE c.last_active_at > now() - interval '30 days') AS opened_30d,
       count(*) FILTER (WHERE c.seasons_played = 0) AS no_finished_season,
       round(avg(c.seasons_played), 1) AS avg_seasons
FROM career_profiles c JOIN users u ON u.id = c.user_id WHERE NOT u.is_banned;

\echo '=== 2. Сезоны по статусу, участники по статусу ==='
SELECT status, count(*) AS seasons,
       round(avg(rounds_played), 1) AS avg_rounds,
       round(avg(extract(epoch FROM finished_at - starts_at) / 3600) FILTER (WHERE finished_at IS NOT NULL), 1) AS hours_long
FROM career_seasons GROUP BY status ORDER BY seasons DESC;
SELECT status, count(*) AS participants, count(DISTINCT user_id) AS coaches FROM career_participants GROUP BY status ORDER BY 2 DESC;

\echo '=== 3. Возврат: неделя первого сезона -> дошли до N-го сезона ==='
WITH firsts AS (
  SELECT user_id, min(created_at) AS first_at, count(*) AS seasons
  FROM career_participants WHERE status IN ('accepted', 'left') GROUP BY user_id
)
SELECT to_char(date_trunc('week', first_at), 'YYYY-MM-DD') AS first_week, count(*) AS coaches,
       count(*) FILTER (WHERE seasons >= 2) AS s2, count(*) FILTER (WHERE seasons >= 3) AS s3,
       count(*) FILTER (WHERE seasons >= 5) AS s5, count(*) FILTER (WHERE seasons >= 10) AS s10,
       round(100.0 * count(*) FILTER (WHERE seasons >= 2) / count(*)) AS s2_pct
FROM firsts GROUP BY 1 ORDER BY 1 DESC LIMIT 12;

\echo '=== 4. Идёт ли сезон сам: идущие сезоны и давно ли тренер заходил ==='
SELECT count(*) AS active_parts,
       count(*) FILTER (WHERE c.last_active_at > now() - interval '1 day') AS seen_1d,
       count(*) FILTER (WHERE c.last_active_at BETWEEN now() - interval '3 days' AND now() - interval '1 day') AS seen_1_3d,
       count(*) FILTER (WHERE c.last_active_at < now() - interval '3 days') AS gone_3d_plus
FROM career_participants p JOIN career_seasons s ON s.id = p.season_id JOIN career_profiles c ON c.user_id = p.user_id
WHERE s.status = 'active' AND p.status = 'accepted';

\echo '=== 5. Сложность по дивизионам (матчи людей, 60 дней; dead = техническое поражение) ==='
SELECT division, count(*) AS matches,
       round(100.0 * count(*) FILTER (WHERE own > opp) / count(*)) AS win_pct,
       round(100.0 * count(*) FILTER (WHERE own = opp) / count(*)) AS draw_pct,
       round(100.0 * count(*) FILTER (WHERE own < opp) / count(*)) AS loss_pct,
       round(avg(own), 2) AS gf, round(avg(opp), 2) AS ga,
       count(*) FILTER (WHERE played IS NULL) AS dead
FROM :outcomes o GROUP BY division ORDER BY division;

\echo '=== 6. Форма по ходу сезона: победы по турам ==='
SELECT round + 1 AS tour, count(*) AS matches, round(100.0 * count(*) FILTER (WHERE own > opp) / count(*)) AS win_pct
FROM :outcomes o GROUP BY round ORDER BY round;

\echo '=== 7. Итоги сезонов по дивизионам (60 дней): места, подъём, вылет ==='
SELECT p.division, count(*) AS finished,
       round(avg(p.final_place), 1) AS avg_place,
       count(*) FILTER (WHERE p.final_place = 1) AS champions,
       count(*) FILTER (WHERE p.next_division < p.division) AS promoted,
       count(*) FILTER (WHERE p.next_division = p.division) AS stayed,
       count(*) FILTER (WHERE p.next_division > p.division) AS relegated,
       round(avg(p.coins_earned)) AS avg_coins
FROM career_participants p JOIN career_seasons s ON s.id = p.season_id
WHERE s.status = 'finished' AND s.created_at > now() - interval '60 days' AND p.final_place IS NOT NULL
GROUP BY p.division ORDER BY p.division;

\echo '=== 8. Где стоят тренеры: дивизион и репутация ==='
SELECT division, count(*) AS coaches,
       count(*) FILTER (WHERE last_active_at > now() - interval '7 days') AS opened_7d,
       round(avg(reputation)) AS avg_rep, max(reputation) AS max_rep,
       round(avg(seasons_played), 1) AS avg_seasons, sum(titles) AS titles
FROM career_profiles GROUP BY division ORDER BY division;

\echo '=== 9. Что настраивают: доля участников сезонов за 60 дней ==='
SELECT count(*) AS parts,
       round(100.0 * count(*) FILTER (WHERE p.tactic IS NOT NULL) / count(*)) AS tactic_pct,
       round(100.0 * count(*) FILTER (WHERE p.playstyle = 'CUSTOM') / count(*)) AS custom_pct,
       round(100.0 * count(*) FILTER (WHERE p.match_plan IS NOT NULL) / count(*)) AS plan_pct,
       round(100.0 * count(*) FILTER (WHERE p.set_pieces IS NOT NULL) / count(*)) AS set_pieces_pct,
       round(100.0 * count(*) FILTER (WHERE p.roles IS NOT NULL) / count(*)) AS roles_pct,
       round(100.0 * count(*) FILTER (WHERE p.marking IS NOT NULL) / count(*)) AS marking_pct,
       round(100.0 * count(*) FILTER (WHERE p.lineup IS NOT NULL) / count(*)) AS lineup_pct,
       round(100.0 * count(*) FILTER (WHERE p.training IS NOT NULL) / count(*)) AS training_pct,
       round(100.0 * count(*) FILTER (WHERE p.ambition IS NOT NULL) / count(*)) AS ambition_pct,
       round(100.0 * count(*) FILTER (WHERE p.camp IS NOT NULL) / count(*)) AS camp_pct
FROM career_participants p WHERE p.status IN ('accepted', 'left') AND p.created_at > now() - interval '60 days';

\echo '=== 10. Схемы и настрой: сколько и как играют (связь с победой не причина: сильные выбирают иначе) ==='
SELECT played->>'formation' AS formation, count(*) AS matches, count(DISTINCT user_id) AS coaches,
       round(100.0 * count(*) FILTER (WHERE own > opp) / count(*)) AS win_pct
FROM :outcomes o WHERE played IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
SELECT played->>'preset' AS preset, played->>'mentality' AS mentality, count(*) AS matches, count(DISTINCT user_id) AS coaches,
       round(100.0 * count(*) FILTER (WHERE own > opp) / count(*)) AS win_pct
FROM :outcomes o WHERE played IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 12;

\echo '=== 11. Тренировки: занятия и нагрузка (идущие и новые сезоны) ==='
SELECT COALESCE(training, '— нет') AS main, count(*) AS parts FROM career_participants WHERE :recent GROUP BY 1 ORDER BY 2 DESC;
SELECT COALESCE(training_extra, '— нет') AS extra, count(*) AS parts FROM career_participants WHERE :recent GROUP BY 1 ORDER BY 2 DESC;
SELECT training_intensity, count(*) AS parts FROM career_participants WHERE :recent GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) FILTER (WHERE training_program IS NOT NULL) AS with_programme,
       count(*) FILTER (WHERE training_program->'active' IS NOT NULL AND json_typeof(training_program->'active') = 'object') AS on_it_now,
       count(*) AS parts
FROM career_participants WHERE :recent;

\echo '=== 12. Пресс-конференции: последний вопрос сезона, ответили ли ==='
SELECT mo.value->>'code' AS code, count(*) AS asked, count(mo.value->>'answer') AS answered,
       round(100.0 * count(mo.value->>'answer') / count(*)) AS answered_pct
FROM career_seasons s, json_each(s.state->'moments') mo WHERE s.created_at > now() - interval '60 days'
GROUP BY 1 ORDER BY 2 DESC;
SELECT mo.value->>'code' AS code, mo.value->>'answer' AS answer, count(*) AS n
FROM career_seasons s, json_each(s.state->'moments') mo
WHERE s.created_at > now() - interval '60 days' AND mo.value->>'answer' IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 3 DESC;

\echo '=== 13. Мораль и трибуны: идущие и законченные сезоны (пусто = сезон без морали) ==='
SELECT s.division, count(*) AS teams,
       round(avg((mo.value)::text::numeric)) AS avg_morale,
       round(avg((f.value)::text::numeric)) AS avg_fans
FROM career_participants p JOIN career_seasons s ON s.id = p.season_id
LEFT JOIN LATERAL json_each(s.state->'morale'->'teams') mo ON mo.key = p.team_index::text
LEFT JOIN LATERAL json_each(s.state->'fans') f ON f.key = p.team_index::text
WHERE s.status IN ('active', 'finished') AND s.created_at > now() - interval '60 days' GROUP BY 1 ORDER BY 1;

\echo '=== 14. Сезоны с другом, кубок, сборы ==='
SELECT count(*) AS seasons,
       count(*) FILTER (WHERE humans >= 2) AS with_friend,
       count(*) FILTER (WHERE has_cup) AS with_cup,
       count(*) FILTER (WHERE has_friendly) AS with_friendly
FROM (SELECT s.id, count(*) FILTER (WHERE p.status IN ('accepted', 'left')) AS humans,
             s.state->'cup' IS NOT NULL AS has_cup,
             s.state->'friendlies' IS NOT NULL OR s.state->'friendly' IS NOT NULL AS has_friendly
      FROM career_seasons s JOIN career_participants p ON p.season_id = s.id
      WHERE s.created_at > now() - interval '60 days' GROUP BY s.id) x;
SELECT COALESCE(camp, '— нет') AS camp, count(*) AS parts FROM career_participants WHERE :recent GROUP BY 1 ORDER BY 2 DESC;
SELECT COALESCE(ambition, '— нет') AS ambition, count(*) AS parts, round(avg(final_place), 1) AS avg_place
FROM career_participants WHERE :recent GROUP BY 1 ORDER BY 2 DESC;

\echo '=== 15. Профиль: опыт, навыки, достижения ==='
SELECT count(*) AS coaches,
       count(*) FILTER (WHERE (coach_skills->>'xp')::int > 0) AS with_xp,
       count(*) FILTER (WHERE (coach_skills->'skills')::text NOT IN ('{}', 'null')) AS spent_skills,
       count(*) FILTER (WHERE (achievements->'unlocked')::text NOT IN ('{}', '[]', 'null')) AS with_achievements
FROM career_profiles;

\echo '=== 16. Монеты: сколько даёт режим за сезон, по неделям ==='
SELECT to_char(date_trunc('week', s.finished_at), 'YYYY-MM-DD') AS week, count(*) AS parts, sum(p.coins_earned) AS coins, round(avg(p.coins_earned)) AS avg_coins
FROM career_participants p JOIN career_seasons s ON s.id = p.season_id
WHERE s.status = 'finished' AND s.finished_at > now() - interval '60 days' GROUP BY 1 ORDER BY 1 DESC;
