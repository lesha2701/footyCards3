# «Ответка»

A football match in ten episodes. The player plays an episode, the opponent
answers it; a draw after the ten goes to a penalty shoot-out, sudden death.
For now the opponent is a bot, and the game says so.

Code: `backend/app/services/otvetka_service.py`, `routers/games.py`
(`/games/otvetka/start|{id}/episode|{id}/claim`), migration `0255_otvetka`;
frontend `pages/OtvetkaPage.tsx`, `components/oneOnOne/SetPieceRun.tsx`
(penalty / free kick) and `AttackRun.tsx` (everything else).

## A match

`plan_kinds` draws ten kinds within `LIMITS`:

| Kind | Min | Max |
| --- | --- | --- |
| Пенальти | 1 | 2 |
| Штрафной | 1 | 2 |
| Выход 1 на 1 | 1 | 3 |
| 2 на 1 | 1 | 3 |
| 3 на 2 | 1 | 3 |
| Пас в разрез | 1 | 3 |
| Навес / прострел | 1 | 3 |

`plan_minutes` puts one episode in each nine-minute stretch, so the minutes
ascend. Every episode is signed on screen: «35′ · Выход 1 на 1», on the score
bug and, until the first touch, as a title with a hint.

## The server's word

The state lives in `GameSession.server_state` (`GameType.otvetka`). The bot's
answers are rolled at the start and stay there: the client gets an episode's
answer only with that episode's verdict.

The client sends only the input: a timeline (with passes) or a quantized
swipe. `_replay` runs it through the Python ports of the client's engines
(`one_on_one_engine`, `team_attack_engine`, `free_kick_3d_engine`), so the
outcome, the score and the coins are the server's alone. An input of the wrong
sort for the episode, or one that came sooner than it could have been played,
is a 409.

## Numbers

All on `GameConfig`, in the admin's «Ответка» section:
`otvetka_daily_limit`, `otvetka_goal_coins`, `otvetka_win_coins`,
`otvetka_loss_coins`, `otvetka_bot_goal_pct`, `otvetka_bot_penalty_pct`
(the last one for penalties, the shoot-out's too). Past the daily cap the
player keeps playing for nothing; the shared hourly cap applies as to any
mini-game (`game_limits_service`).

## Later

A live opponent needs a two-sided table instead of `GameSession`: the same
seeds for both, an episode's answer revealed once both have reached it.
Cards: progress for «Мой игрок» and «Академия» heroes, talents.
