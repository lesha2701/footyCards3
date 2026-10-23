-- Какие мини-игры чаще всего играли за последние 7 дней (только чтение).
-- Запуск:  psql -U postgres -d footycards -f weekly_minigame_stats.sql
--          (период: -v days=30 для 30 дней; по умолчанию 7)
-- «Игр» — начатые партии (сессии/матчи) за период; «игроков» — уникальные
-- живые игроки (в PvP считаются обе стороны, боты не считаются);
-- «завершено» — доигранные партии (брошенные/просроченные не считаются).
\if :{?days}
\else
  \set days 7
\endif

WITH period AS (
  SELECT now() - make_interval(days => :days) AS since
),
plays AS (
  -- Мини-игры на game_sessions (memory, saboteur, free kick, hangman, pairs, …)
  SELECT CASE gs.game_type::text
           WHEN 'memory_sequence'     THEN 'Memory Sequence'
           WHEN 'card_arena'          THEN 'Card Arena (сессии)'
           WHEN 'saboteur'            THEN 'Саботёр'
           WHEN 'penalty'             THEN 'Пенальти (сессии)'
           WHEN 'free_kick'           THEN 'Штрафной удар'
           WHEN 'football_hangman'    THEN 'Футбольные буквы'
           WHEN 'card_pairs'          THEN 'Пары карточек'
           WHEN 'position_match'      THEN 'Угадай позицию'
           WHEN 'fut_draft'           THEN 'FUT Draft'
           WHEN 'club_sequence'       THEN 'Клуб: последовательность'
           WHEN 'club_missing_item'   THEN 'Клуб: чего не хватает'
           WHEN 'club_penalty'        THEN 'Клуб: пенальти'
           WHEN 'club_position_match' THEN 'Клуб: угадай позицию'
           ELSE gs.game_type::text
         END AS game,
         gs.id::text AS play_id, gs.user_id,
         gs.status::text IN ('won', 'lost', 'rewarded') AS finished  -- expired = брошена
  FROM game_sessions gs, period WHERE gs.created_at >= period.since

  UNION ALL  -- Card Arena
  SELECT 'Card Arena', m.id::text, u.uid, m.status::text <> 'in_progress'
  FROM matches m CROSS JOIN period
  CROSS JOIN LATERAL (VALUES (m.user_id), (m.opponent_user_id)) u(uid)
  WHERE m.created_at >= period.since AND u.uid IS NOT NULL

  UNION ALL  -- Пенальти
  SELECT 'Пенальти', p.id::text, u.uid, p.resolved_at IS NOT NULL
  FROM penalty_matches p CROSS JOIN period
  CROSS JOIN LATERAL (VALUES (p.user_id), (p.opponent_user_id)) u(uid)
  WHERE p.created_at >= period.since AND u.uid IS NOT NULL

  UNION ALL  -- Тактико
  SELECT 'Тактико', t.id::text, u.uid, t.resolved_at IS NOT NULL
  FROM tactico_matches t CROSS JOIN period
  CROSS JOIN LATERAL (VALUES (t.user_id), (t.opponent_user_id)) u(uid)
  WHERE t.created_at >= period.since AND u.uid IS NOT NULL

  UNION ALL  -- Футбольное Стратего
  SELECT 'Стратего', s.id::text, u.uid, s.resolved_at IS NOT NULL
  FROM stratego_matches s CROSS JOIN period
  CROSS JOIN LATERAL (VALUES (s.user_id), (s.opponent_user_id)) u(uid)
  WHERE s.created_at >= period.since AND u.uid IS NOT NULL

  UNION ALL  -- Футбольный магнат (живые места, без ботов)
  SELECT 'Магнат', mm.id::text, ms.user_id, mm.finished_at IS NOT NULL
  FROM magnate_matches mm JOIN magnate_seats ms ON ms.match_id = mm.id CROSS JOIN period
  WHERE mm.created_at >= period.since AND ms.user_id IS NOT NULL AND NOT ms.is_bot

  UNION ALL  -- Блэкджек 21
  SELECT 'Блэкджек 21', b.id::text, b.user_id, b.finished_at IS NOT NULL
  FROM blackjack_matches b, period WHERE b.created_at >= period.since

  UNION ALL  -- Дуэли «Мой игрок»
  SELECT 'Дуэль «Мой игрок»', d.id::text, u.uid, true
  FROM my_player_duels d CROSS JOIN period
  CROSS JOIN LATERAL (VALUES (d.user_id), (d.opponent_user_id)) u(uid)
  WHERE d.created_at >= period.since AND u.uid IS NOT NULL
)
SELECT game                                   AS "Мини-игра",
       count(DISTINCT play_id)                AS "Игр",
       count(DISTINCT play_id) FILTER (WHERE finished) AS "Завершено",
       count(DISTINCT user_id)                AS "Игроков",
       round(count(DISTINCT play_id)::numeric / NULLIF(count(DISTINCT user_id), 0), 1) AS "Игр на игрока"
FROM plays
GROUP BY game
ORDER BY "Игр" DESC, "Игроков" DESC;
