# Лига: личные турниры на 16 игроков — дизайн

Дата: 2026-09-25. Статус: черновик на ревью.

## Цель

Добавить в основную игру турниры между игроками (аналог клубных турниров), с отдельным составом из своих карт, тактикой, настраиваемыми наградами и рейтингом по местам.

## Отличия от клубных турниров

| | Клубы | Лига |
|---|---|---|
| Участников | 8 | 16 |
| Туров | 14 (2 круга по 7) | 30 (2 круга по 15) |
| Симуляция | 12:00, 20:00 | 10:00, 15:00, 21:00 |
| Состав | карты клуба | карты игрока (`user_cards`) |
| Итог | звёзды/кубки клуба | `users.league_rating` |

## Подход

Параллельная подсистема с собственными таблицами. Переиспользуем без изменений: `tournament_match_engine.simulate_match`, `club_tactical_matchup_service.build_side`, паттерн очереди из `tournament_queue_service`, `TournamentSimulationSlotLog` (новый `kind`), `TournamentMatchReplay` на фронте. Клубные таблицы и логика не меняются.

## Ограничения (Global Constraints)

- Экономика, вероятности и награды — только на бэкенде, значения из `GameConfig` (`game_config_service.get_config()`), не хардкодить.
- Монеты только через `wallet_service.lock_user_for_update` + `credit_coins` (populate_existing, `CoinTransaction`).
- Только async-доступ к БД. Гонки: `SELECT ... FOR UPDATE`.
- Идемпотентность симуляции через `slot_key` + блокировку турнира.
- Миграции последовательные: 0119 и далее, `down_revision` = текущая голова (0118).
- Слоты: 10:00, 15:00, 21:00 по `settings.timezone` (константа в боте, как `SIMULATION_SLOTS`).
- Правка таблиц, которых касается бот (users, notifications) — обновлять и SQL бота.

## Данные (миграции)

- `personal_squads` (+ `personal_squad_cards`): `user_id`, `template_index` 1..5 (unique с `user_id`), `name`, `formation`, `mentality`, `playstyle`, `is_active` (частичный unique индекс «один активный на игрока»), тренер (по образцу `Lineup.user_coach_card_id`), карты по слотам с unique `(squad_id, user_card_id)` и `(squad_id, slot_code)`. Шаблоны 2–5 создаются лениво, как `lineup_service._ensure_templates`.
- `league_tournaments`: `status`, `rounds_simulated` CHECK 0..30, `created_at`.
- `league_participants`: `tournament_id`, `user_id`, `is_withdrawn`; unique `(tournament_id, user_id)`.
- `league_standings`: `points`, `goals_for`, `goals_against`; unique `(tournament_id, user_id)`.
- `league_matches`: `tournament_id`, `round_number`, `user_a_id`, `user_b_id`, `score_a`, `score_b`, `event_log` JSON, `simulated_at`.
- `league_results`: `final_rank`, `coins_awarded`, `rating_delta`; unique `(tournament_id, user_id)`.
- `league_queue_state` (singleton id=1), `league_queues`, `league_queue_entries` — как клубная очередь, но `TOURNAMENT_SIZE = 16`. Singleton лениво создаётся, как в `_lock_queue_state` (тесты идут через `create_all`, не alembic).
- `users.league_rating` INT NOT NULL DEFAULT 0 (без нижней границы).
- `game_config`: `league_match_reward_win/draw/loss`, `league_place_rewards` (JSON, 16 значений монет), `league_rating_by_place` (JSON, 16 значений; по умолчанию 5,4,3,2,1,0,0,0,0,0,0,-1,-2,-3,-4,-5), `league_hourly_...` не нужны. Значения по умолчанию наград выбрать в плане.

## Логика

**Расписание.** Обобщение `generate_fixtures` на 16: круговой алгоритм, 15 туров по 8 пар, второй круг повторяет пары с теми же тура n+15 (без одинаковых соперников подряд по той же причине, что в клубах).

**Заявка.** Условия: полный состав из 11 карт в активном шаблоне, игрок не в активном турнире, не в текущей очереди. Блокировка singleton очереди; при 16 записях создаётся турнир, участники и standings, очередь закрывается, открывается новая. Ожидание без ботов.

**Симуляция тура** (`league_simulation_service.simulate_next_round(db, slot_key)`, вызов `POST /internal/league/simulate-round`): вставка `slot_key` (kind `league_round`) → `IntegrityError` = no-op; для каждого активного турнира блокировка и проверка `rounds_simulated`; для каждой пары — сбор состава из активного шаблона (`build_side` с картами игрока); если у игрока не хватает карт (проданы/обменены) — поражение 0–3 без запуска движка; иначе `simulate_match`. Травм и дисквалификаций нет (результаты движка по красным/травмам игнорируются). После матча: standings, награда за матч из конфига (win/draw/loss) обоим игрокам, уведомление без счёта (реплей открывается в приложении). На 30-м туре — `conclude_league` (ранжирование по очкам, разнице, H2H как в `rank_standings`), награды за место (монеты) и `league_rating += league_rating_by_place[rank-1]`, статус completed.

**Напоминания.** `POST /internal/league/lineup-reminders` за час до слота тем, у кого неполный состав.

**Бот.** `bot/services/league_scheduler.py` (или расширение `tournament_scheduler`) с `LEAGUE_SLOTS = [(10, 0), (15, 0), (21, 0)]` и теми же `_due_slots`, catch-up и `slot_key`.

## API (`routers/league.py`)

Состав: get/set шаблонов (5), выбор активного. Лига: статус очереди, заявка, текущий турнир, таблица, мои матчи, матч с event_log. Рейтинг лиги в профиле и лидербордах. Админ: чтение и правка полей `league_*` в конфиге (`AdminGamesPage`).

## Фронтенд

Страница лиги (очередь/заявка, таблица, мои матчи, реплей — переиспользование `TournamentMatchReplay`), редактор составов с 5 шаблонами (по образцу редактора Тактико/клуба), рейтинг в профиле и лидерборде, вкладка настроек лиги в админке.

## Тесты

pytest (SQLite): расписание 16, очередь и заявка, симуляция тура, идемпотентность по `slot_key` и по гонке, forfeit при нехватке карт, места/рейтинг/награды, миграции применимы. Блокировки проверить вручную на Postgres. Vitest для страницы и реплея.

## Порядок работ (три плана)

1. Бэкенд-ядро: модели, миграции, составы, очередь, симуляция, награды, рейтинг, эндпоинты, бот-слоты, тесты.
2. Фронт для игроков.
3. Админка и конфиг.

## Открытые допущения

- Рейтинг может быть отрицательным.
- Без ботов-добивки очереди, без тренировочного буста, без травм.
- Значения по умолчанию наград согласовать в плане.
