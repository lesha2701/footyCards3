# Пенальти: визуал, 6 зон удара, PvP с друзьями

Date: 2026-08-10
Status: approved for planning

## Контекст

Сейчас режим «Пенальти» (`backend/app/services/penalty_service.py`,
`frontend/src/pages/PenaltyGamePage.tsx`) — это одиночная серия ударов
против бота: 3 направления (left/center/right), 10 ударов регламента
(5 раундов), при ничьей после регламента — доп. удары без ограничения
до победителя. Игрок уже и бьёт (когда его очередь), и защищается
(угадывает направление удара бота) — механика симметрична внутри одной
сессии, только у бота нет стратегии (случайный выбор с обеих сторон).

Нет визуала поля/вратаря (только текст+иконка исхода), нет PvP-режима.

## Цели

1. Визуал: анимированные ворота и вратарь (свой — красный, соперника —
   синий), работает и в игре с ботом, и в PvP.
2. 6 зон удара вместо 3 (сетка 3×2: лево/центр/право × верх/низ), и в
   боте, и в PvP.
3. PvP: вызов друга (как в Тактико), обмен ударами с таймерами (10 сек
   на выбор одного удара, 3 минуты на весь матч), слепой одновременный
   выбор (бьющий — зону удара, защищающийся — зону прыжка), ничья
   возможна при истечении общего таймера.
4. Рейтинг `penalty_rating`, меняется и от игр с ботом, и от PvP —
   попадает в лидерборд как `arena_rating`/`tactics_rating`.

## Не цели (явно вне объёма этой итерации)

- Монеты за PvP-победу/ничью — намеренно НЕ даём (см. «Анти-абьюз»).
- Сезонные сбросы рейтинга, история, аналитика — не требуется.
- Матчмейкинг «прямо сейчас» — только асинхронный вызов, как в Тактико.
- Изменение регламента одиночной игры (10 ударов, доп. удары до
  победителя без ничьей) — остаётся как есть.

## Анти-абьюз: почему без монет за PvP

Тактико уже решило эту проблему: дружеские матчи не дают монет, только
рейтинг (`test_friend_match_gives_rating_only_no_coins`), потому что
монеты за победу над «своим» вторым аккаунтом — тривиальный фарм.
PvP-Пенальти повторяет то же решение: PvP даёт только результат
(W/D/L) и изменение `penalty_rating`. Игра с ботом монеты по-прежнему
даёт (как сейчас, `penalty_reward_win`/`penalty_reward_loss` из
`GameConfig`) — там фармить не через кого.

## Архитектура

### Новая модель `PenaltyMatch` (backend/app/models/penalty.py)

Не переиспользуем `GameSession` (она рассчитана на одного игрока —
`user_id` без второй стороны). Заводим отдельную модель, по образцу
`TacticoMatch` (`backend/app/models/tactico.py`):

```python
class PenaltyMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"

class PenaltyMatchResult(str, enum.Enum):
    win = "win"
    draw = "draw"
    loss = "loss"

class PenaltyMatch(Base):
    __tablename__ = "penalty_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]                       # challenger
    opponent_user_id: Mapped[int]
    user_card_id: Mapped[Optional[int]]        # set at challenge creation
    opponent_card_id: Mapped[Optional[int]]    # set at accept
    status: Mapped[PenaltyMatchStatus]
    result: Mapped[Optional[PenaltyMatchResult]]   # from challenger's POV
    rating_delta: Mapped[Optional[int]]            # challenger's delta
    server_state: Mapped[dict]   # JSON, shape below
    expires_at: Mapped[datetime]   # challenge (pending_accept) expiry
    resolved_at: Mapped[Optional[datetime]]
    created_at, updated_at (TimestampMixin)
```

`server_state` shape (mirrors Tactico's per-round state machine):

```python
{
    "match_deadline": None,           # ISO ts, set to now()+3min at accept
    "kick_deadline": None,             # ISO ts, set to now()+10s per kick
    "kicks_taken": 0,
    "kicker": "user",                  # "user" | "opponent", alternates
    "user_score": 0, "opponent_score": 0,
    "user_pending_zone": None,         # this kick's blind pick, "user" side
    "opponent_pending_zone": None,
    "rounds": [ {kicker, shot_zone, dive_zone, outcome}, ... ],
}
```

Reuses `PENALTY_DIRECTIONS` (6 zones, see below) for `shot_zone`/`dive_zone`.

### 6 zones (заменяет `DIRECTIONS = ("left","center","right")`)

```python
PENALTY_ZONES = ("top_left", "top_center", "top_right",
                  "bottom_left", "bottom_center", "bottom_right")
```

Используется и в одиночной игре (`penalty_service.resolve_kick`), и в
PvP. Логика гола не меняется структурно — просто сравнение по 6
значениям вместо 3:

- Промах: как сейчас, `player_miss_chance(rating)` от рейтинга
  карточки **бьющего** (не защищающегося).
- Если не промах: `shot_zone == dive_zone` → отбито, иначе → гол.
- В боте: вратарь бота (когда бьёт игрок) — случайная зона, как
  сейчас (`random.choice`). Игрок, защищаясь от удара бота, уже сейчас
  выбирает зону явно (существующий эндпоинт `resolve_kick(direction)`)
  — просто расширяем набор значений.
- В PvP: обе стороны выбирают вслепую и одновременно (см. ниже) —
  никакой случайности кроме промаха бьющего.

### PvP flow

Мирроринг `tactico_service.py` (`create_challenge` / `accept_challenge`
/ `submit_round` / `_auto_play_overdue_rounds`), адаптированный под
одну карточку вместо состава из 11 и намного более короткие таймеры.

1. **Вызов**: `POST /games/penalty/challenges` `{opponent_user_id,
   user_card_id}` → создаёт `PenaltyMatch(status=pending_accept)`,
   уведомление получателю (`NotificationType.penalty_challenge_received`).
   `expires_at` — новое поле конфига `penalty_challenge_expiry_hours`
   (по аналогии с `tactico_challenge_expiry_hours`), дефолт 24ч.
2. **Принятие**: `POST /games/penalty/challenges/{id}/accept`
   `{user_card_id}` (это карточка принимающего) → статус
   `in_progress`, `server_state.match_deadline = now()+3min`,
   `kick_deadline = now()+10s`, `kicker = "user"` (вызвавший бьёт
   первым — фиксированно, не рандомно).

   **Живой перенос вызвавшего в матч**: после отправки вызова
   вызвавший сразу попадает на `/play/penalty/matches/{id}` (тот же
   паттерн `navigate()` в `onSuccess`, что у `challengeMutation` в
   `TacticoMatchesPage.tsx`) и видит «Вызов отправлен, ждём ответа».
   Это конкретное регрессионное требование: у Тактико сейчас баг —
   `TacticoMatchPage.tsx`'s `refetchInterval` отключает поллинг, пока
   `status !== "in_progress"`, поэтому вызвавший, оставшись на этом же
   экране, никогда не узнаёт, что друг принял вызов, пока сам не
   перезайдёт. Уже пофикшено в Тактико 2026-08-10 (поллинг раз в 5с,
   пока `status === "pending_accept" && viewer_side === "user"`) —
   для Пенальти реализовать аналогичный поллинг сразу, по тому же
   правилу (только для ждущей стороны, не для получателя вызова).
3. **Ход**: `POST /games/penalty/matches/{id}/pick` `{zone}` — любая
   сторона отправляет свой слепой выбор для текущего удара (кто сейчас
   `kicker` — зона удара; кто `не kicker` — зона прыжка). Пишется в
   `user_pending_zone`/`opponent_pending_zone`. Когда обе стороны
   отправили — раунд резолвится немедленно (тот же расчёт гол/отбито,
   что и в боте), `kicks_taken += 1`, `kicker` меняется на
   противоположного, `kick_deadline` сбрасывается на `+10s`.
   Обязательно через блокировку строки матча (`with_for_update`, как
   `_lock_match` у Тактико) — иначе два одновременных `pick` от разных
   сторон могут прочитать один и тот же `server_state` до записи друг
   друга и потерять один из выборов.
4. **Таймаут удара** (10 сек): ленивая проверка при любом GET на матч
   (как `_auto_play_overdue_rounds` в Тактико) — если `kick_deadline`
   прошёл и одна из сторон не выбрала зону, ей выбирается случайная
   зона автоматически, раунд резолвится.
5. **Таймаут матча** (3 мин): та же ленивая проверка — если
   `match_deadline` прошёл, а матч ещё `in_progress`, завершить сразу
   с текущим счётом: `user_score > opponent_score` → win/loss,
   `==` → draw. Работает независимо от того, сколько ударов сделано
   (даже если регламент 10 ударов не пройден) — 3-минутный таймер
   главнее регламента.
6. **Обычное завершение**: если оба счёта равны после 10 ударов (5
   раундов) — доп. удары продолжаются (как в боте) до тех пор, пока не
   решит один из двух факторов: перевес в счёте ИЛИ истечение
   3-минутного таймера (тогда — ничья, если счёт всё ещё равен).
7. **Награда**: без монет. По завершении — обновляем
   `penalty_rating` обеим сторонам (симметрично, как Тактико's
   `_OPPONENT_RATING_DELTA = {3: -1, -1: 3, 1: 1}`: win +3 / draw +1 /
   loss −1 для победителя, зеркально для соперника), плюс запись в
   истории матчей (`GET /games/penalty/matches`, аналог
   `GET /tactico/matches`).
8. **Отклонить/отменить**: `POST .../decline`, `POST .../cancel` —
   как в Тактико, только для `pending_accept`.
9. **Существующий часовой/дневной лимит** (`penalty_hourly_attempts`,
   `penalty_rewarded_attempts_today`) применяется только к игре с
   ботом (монеты только там) — PvP не расходует и не ограничивается
   этими счётчиками (как Тактико: часовой лимит у Тактико свой,
   отдельный от других игр — здесь используем **общий**
   `hourly_game_limit`, т.к. Пенальти уже на нём, применяем и к PvP
   через `_consume_hourly_slot`-подобный вызов при создании вызова,
   зеркаля Тактико).

### Рейтинг и лидерборд

- Новая колонка `User.penalty_rating: Mapped[int] = mapped_column(default=0)`.
- И бот-режим, и PvP обновляют её по итогам матча (бот: только
  win(+3)/loss(−1), ничьей в боте не бывает — доп. удары идут до
  победителя без ограничения, это НЕ меняется).
- `RankingMetric.penalty_rating` — новое значение enum
  (`backend/app/schemas/ranking.py`), плюс запись в
  `_DIRECT_COLUMNS` (`backend/app/services/ranking_service.py`) —
  сам механизм рейтинга уже универсален, изменение минимально.

### Фронтенд

- `PenaltyGamePage.tsx`: SVG-сцена ворот + вратарь (Framer Motion),
  цвет по стороне (свой красный / соперника синий), сетка 3×2 вместо
  3 кнопок в ряд.
- Новая страница матчей `PenaltyMatchesPage.tsx` (по образцу
  `TacticoMatchesPage.tsx`) — список вызовов/активных/истории PvP,
  кнопка «Вызвать друга» (переиспользуем `searchUsers` +
  bottom sheet, как в Тактико).
- Новая страница самого PvP-матча `PenaltyMatchPage.tsx` (по образцу
  `TacticoMatchPage.tsx`) — polling с `refetchInterval`, быстрее (в
  районе 2-3 сек, раз таймер удара всего 10 сек, а не 15 сек как у
  Тактико), обратный отсчёт до `kick_deadline` и `match_deadline`.
  **Live-баланс**: не забыть вызвать `updateBalance` там, где это
  нужно — но т.к. PvP не даёт монет, актуально не будет (нечего
  обновлять); фикс из этой сессии (issue про Тактико) тут не
  воспроизводится по построению.

## Тестирование

Мирроринг существующих тестов `test_tactico.py` (challenge/accept/
decline/cancel, timeout sweep, rating deltas) и `test_penalty.py`
(direction validation → расширить на 6 зон, daily cap regression —
уже есть, не трогаем). Новые сценарии:
- Вызов → принятие → обмен ударами → корректный счёт/результат.
- Таймаут одного удара (10с) → авто-случайный выбор для не успевшего.
- Таймаут матча (3 мин) → принудительное завершение текущим счётом,
  включая ничью.
- PvP не даёт монет ни при каком исходе; бот-режим монеты даёт
  по-прежнему.
- `penalty_rating` меняется симметрично для обеих сторон в PvP и
  корректно для одиночной игры с ботом.
- Лидерборд `penalty_rating` возвращает корректный топ.
- Вызвавший, оставшись на экране `pending_accept`, видит переход в
  `in_progress` без ручного захода/обновления (тот же ручной прогон,
  каким проверялся фикс поллинга в Тактико — второй аккаунт принимает
  вызов напрямую через сервис-функцию, без второй HTTP-сессии).

## Открытые допущения (можно поправить на этом этапе)

- Первым в PvP всегда бьёт вызвавший (не случайно и не по договору).
- Регламент — те же 10 ударов (5 раундов), что и сейчас; 3-минутный
  таймер может прервать его в любой момент.
- Часовой лимит PvP-вызовов — общий `hourly_game_limit`, расходуется
  при создании вызова (не при каждом ударе).
- Тайминги 10 сек / 3 мин — захардкожены константами (как
  `FRIEND_TURN_TIMEOUT_SECONDS` у Тактико), не через `GameConfig` —
  это игровое правило, не экономический рычаг для тюнинга админом.
