-- «Менеджер», только чтение, только итоги без игроков (все режимы — scripts/mode_stats.py).
-- Запуск: docker compose -f docker-compose.prod.yml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/scripts/manager_stats.sql
SET default_transaction_read_only = on;
\pset footer off

\echo '=== 1. Клубы: всего и за последние 7/14 дней активности владельца ==='
SELECT count(*) AS clubs,
       count(*) FILTER (WHERE u.last_seen_at > now() - interval '7 days') AS owner_seen_7d,
       count(*) FILTER (WHERE u.last_seen_at > now() - interval '14 days') AS owner_seen_14d,
       count(*) FILTER (WHERE c.seasons_played = 0) AS never_played_season,
       (SELECT count(*) FROM user_daily_activity a WHERE a.day > current_date - 7) / 7 AS game_avg_dau_7d
FROM manager_clubs c JOIN users u ON u.id = c.owner_id WHERE NOT u.is_banned;

\echo '=== 2. Возврат: сколько клубов созданы и дошли до N сезонов ==='
SELECT to_char(date_trunc('week', c.created_at), 'YYYY-MM-DD') AS founded_week, count(*) AS clubs,
       count(*) FILTER (WHERE c.seasons_played >= 1) AS s1,
       count(*) FILTER (WHERE c.seasons_played >= 2) AS s2,
       count(*) FILTER (WHERE c.seasons_played >= 4) AS s4,
       count(*) FILTER (WHERE c.seasons_played >= 8) AS s8
FROM manager_clubs c GROUP BY 1 ORDER BY 1;

\echo '=== 3. Активные клубы по сезонам: кто вообще что-то делал сам ==='
WITH acts AS (
  SELECT season_key, club_id FROM manager_moves
  UNION SELECT season_key, club_id FROM manager_deals
  UNION SELECT season_key, club_id FROM manager_events WHERE status = 'chosen'
)
SELECT s.key AS season, s.depth,
       (SELECT count(DISTINCT l.club_id) FROM manager_ledger l WHERE l.season_key = s.key) AS clubs_with_money,
       (SELECT count(DISTINCT a.club_id) FROM acts a WHERE a.season_key = s.key) AS clubs_acted,
       (SELECT count(*) FROM manager_leagues l WHERE l.season_key = s.key) AS leagues
FROM manager_seasons s ORDER BY s.key DESC LIMIT 10;

\echo '=== 4. События клуба: выбирают или пропускают ==='
SELECT code, count(*) AS offered,
       count(*) FILTER (WHERE status = 'chosen') AS chosen,
       count(*) FILTER (WHERE status = 'expired') AS expired,
       round(100.0 * count(*) FILTER (WHERE status = 'chosen') / count(*)) AS chosen_pct,
       round(avg(extract(epoch FROM decided_at - created_at) / 3600) FILTER (WHERE status = 'chosen'), 1) AS hours_to_decide
FROM manager_events GROUP BY code ORDER BY offered DESC;

\echo '=== 5. Варианты в событиях ==='
SELECT code, choice, count(*) FROM manager_events WHERE choice IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 3 DESC;

\echo '=== 6. Сделки: какие финансовые функции используют ==='
SELECT kind, count(*) AS deals, count(DISTINCT club_id) AS clubs, coalesce(option, '-') AS option
FROM manager_deals GROUP BY kind, option ORDER BY kind, deals DESC;

\echo '=== 7. Деньги: приход и расход по видам за 4 последних сезона ==='
SELECT kind, count(DISTINCT club_id) AS clubs, sum(amount) AS total, round(avg(amount)) AS avg_entry
FROM manager_ledger
WHERE season_key IN (SELECT key FROM manager_seasons ORDER BY key DESC LIMIT 4)
GROUP BY kind ORDER BY total DESC;

\echo '=== 8. Экономика: бюджеты по дивизионам ==='
SELECT division, count(*) AS clubs, min(budget) AS min, percentile_disc(0.5) WITHIN GROUP (ORDER BY budget) AS median,
       max(budget) AS max, sum(titles) AS titles
FROM manager_clubs GROUP BY division ORDER BY division;

\echo '=== 9. Кредиты, биржа, облигации ==='
SELECT (SELECT count(*) FROM manager_loans) AS loans,
       (SELECT count(DISTINCT club_id) FROM manager_loans) AS loan_clubs,
       (SELECT count(*) FROM manager_stocks WHERE floated > 0) AS ipo_clubs,
       (SELECT count(*) FROM manager_trades WHERE side <> 'ipo') AS trades,
       (SELECT count(DISTINCT holder_club_id) FROM manager_trades) AS traders,
       (SELECT count(*) FROM manager_shares WHERE shares > 0) AS holdings,
       (SELECT count(*) FROM manager_shares s WHERE s.shares > 0 AND s.holder_club_id <> s.club_id) AS foreign_holdings,
       (SELECT count(*) FROM manager_bonds) AS bonds;

\echo '=== 10. Концентрация акционеров: сколько владельцев у клуба с IPO ==='
SELECT holders, count(*) AS clubs FROM (
  SELECT club_id, count(*) AS holders FROM manager_shares WHERE shares > 0 AND holder_club_id <> club_id GROUP BY club_id
) t GROUP BY holders ORDER BY holders;

\echo '=== 11. Что ещё трогают: тактика, трансферы, кубок, товарищеские, Stars ==='
SELECT (SELECT count(*) FROM manager_clubs WHERE style <> 'possession' OR formation <> '4-3-3') AS tactics_changed,
       (SELECT count(*) FROM manager_clubs WHERE match_plan IS NOT NULL) AS used_match_plan,
       (SELECT count(*) FROM manager_clubs WHERE ticket_pct <> 100) AS ticket_changed,
       (SELECT count(DISTINCT club_id) FROM manager_moves) AS clubs_with_moves,
       (SELECT count(*) FROM manager_friendlies) AS friendlies,
       (SELECT count(*) FROM manager_cups) AS cups,
       (SELECT count(*) FROM manager_clubs WHERE pro_until > now()) AS pro_now,
       (SELECT count(*) FROM manager_clubs WHERE perks::text LIKE '%analytics%') AS analytics_ever,
       (SELECT count(DISTINCT club_id) FROM manager_cosmetics) AS clubs_with_cosmetics;

\echo '=== 12. Трансферы по видам ==='
SELECT kind, direction, count(*) AS moves, count(DISTINCT club_id) AS clubs, round(avg(fee)) AS avg_fee
FROM manager_moves GROUP BY 1, 2 ORDER BY moves DESC;

