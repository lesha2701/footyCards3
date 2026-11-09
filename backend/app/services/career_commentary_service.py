"""Карьера тренера: the match told as a story. Pure functions over a stored
event log, applied when a match is read: a goal learns what it meant (a brace,
a comeback, a late winner), the last minutes of a close game feel tense, and
the whole match fits in two phrases. Each event looks only at what came before
it, so a replay followed in real time gives nothing away."""
from typing import Optional

LATE_MINUTE = 85
TENSE_MINUTE = 80
ROUT_MARGIN = 3


def _other(team: str) -> str:
    return "b" if team == "a" else "a"


def _shooter(event: dict) -> Optional[str]:
    return (event.get("payload") or {}).get("shooter")


def _mood(event: dict, goals: dict, tally: dict, trail: dict, run: int, minute: int) -> Optional[str]:
    """What this goal meant; goals/tally/trail already count it."""
    team = event["team"]
    own, opp = goals[team], goals[_other(team)]
    name = _shooter(event)
    if name and tally.get((team, name), 0) == 3:
        return "Хет-трик!"
    if minute >= LATE_MINUTE and own == opp:
        return "Спасён матч в самой концовке!"
    if minute >= LATE_MINUTE and own == opp + 1:
        return "Решающий гол на последних минутах!"
    if own == opp + 1 and trail[team] > 0:
        return f"Камбэк! Отыгрались и вышли вперёд, уступая {trail[team]} мяч."
    if own == opp and trail[team] > 1:
        return "Игра началась заново — счёт снова равный!"
    if run >= 3:
        return f"{run} гола подряд — соперник поплыл."
    if name and tally.get((team, name), 0) == 2:
        return "Дубль!"
    return None


def enrich(events: Optional[list]) -> list:
    """The events with the mood added to their text; the stored log and the
    replay's own timing stay as they are."""
    goals, tally, trail = {"a": 0, "b": 0}, {}, {"a": 0, "b": 0}
    last, run = None, 0
    out = []
    for event in events or []:
        team, minute = event.get("team"), event.get("minute") or 0
        text = None
        if event.get("event_type") == "goal" and team in goals:
            goals[team] += 1
            tally[(team, _shooter(event))] = tally.get((team, _shooter(event)), 0) + 1
            run = run + 1 if last == team else 1
            last = team
            text = _mood(event, goals, tally, trail, run, minute)
            trail[_other(team)] = max(trail[_other(team)], goals[team] - goals[_other(team)])
        elif event.get("event_type") in ("save", "shot") and minute >= TENSE_MINUTE and abs(goals["a"] - goals["b"]) <= 1:
            text = "Нервы на пределе!" if minute % 2 else "Трибуны замерли."
        if text and event.get("description"):
            event = {**event, "description": f"{event['description']} {text}"}
        out.append(event)
    return out


def story(events: Optional[list], home: str, away: str, hs: int, as_: int) -> list[str]:
    """Two phrases: how the match went and who made it."""
    names = {"a": f"«{home}»", "b": f"«{away}»"}
    goals_log = [e for e in events or [] if e.get("event_type") == "goal" and e.get("team") in names]
    score = f"{hs}:{as_}"
    if not goals_log:
        return [f"Нулевая ничья {names['a']} и {names['b']}: моментов было мало или вратари были лучше."] if hs == as_ == 0 else []

    goals = {"a": 0, "b": 0}
    worst = {"a": 0, "b": 0}
    decider = None
    for event in goals_log:
        team = event["team"]
        goals[team] += 1
        worst[_other(team)] = max(worst[_other(team)], goals[team] - goals[_other(team)])
        if goals["a"] != goals["b"]:
            lead = "a" if goals["a"] > goals["b"] else "b"
            if lead == team and goals[lead] == goals[_other(lead)] + 1:
                decider = event
    winner = "a" if hs > as_ else "b" if as_ > hs else None

    if winner is None:
        last = goals_log[-1]
        first = (f"{names[last['team']]} спасает ничью {score} на {last['minute']}-й минуте."
                 if (last.get("minute") or 0) >= LATE_MINUTE else f"Боевая ничья {score}: никто не уступил.")
    else:
        loser = _other(winner)
        score = f"{max(hs, as_)}:{min(hs, as_)}"  # the winner's side first
        if worst[winner] > 0:
            first = f"{names[winner]} отыгрывается и вырывает победу у {names[loser]} — {score}."
        elif abs(hs - as_) >= ROUT_MARGIN:
            first = f"Разгром: {names[winner]} сильнее {names[loser]} — {score}."
        elif decider is not None and (decider.get("minute") or 0) >= LATE_MINUTE:
            first = f"{names[winner]} вырывает победу у {names[loser]} в самой концовке — {score}."
        else:
            first = f"{names[winner]} обыгрывает {names[loser]} — {score}."

    tally: dict = {}
    for event in goals_log:
        tally[_shooter(event)] = tally.get(_shooter(event), 0) + 1
    tally.pop(None, None)
    if not tally:
        return [first]
    hero, count = max(tally.items(), key=lambda kv: kv[1])
    if count >= 3:
        second = f"Главный герой — {hero}: хет-трик."
    elif count == 2:
        second = f"Главный герой — {hero}: дубль."
    elif decider is not None and winner is not None and _shooter(decider):
        second = f"Победный мяч на счету {_shooter(decider)} ({decider.get('minute')}′)."
    else:
        opener = goals_log[0]
        second = f"Счёт открыл {_shooter(opener) or 'неизвестный герой'} на {opener.get('minute')}-й минуте."
    return [first, second]


def add_scorers(state: dict, round_index: int, events: Optional[list], home: int, away: int) -> None:
    """Goals of a round by team and player, kept per round so a round on air
    can be left out of the list."""
    book = state.setdefault("scorers", {}).setdefault(str(round_index), {})
    for event in events or []:
        name = _shooter(event)
        if event.get("event_type") == "goal" and name and event.get("team") in ("a", "b"):
            key = f"{home if event['team'] == 'a' else away}|{name}"
            book[key] = book.get(key, 0) + 1


def top_scorers(state: dict, upto: Optional[int] = None, limit: int = 10) -> list[dict]:
    """The league's scorers over the rounds before `upto` (all by default)."""
    teams = state.get("teams") or []
    total: dict = {}
    for round_key, book in (state.get("scorers") or {}).items():
        if upto is None or int(round_key) < upto:
            for key, goals in book.items():
                total[key] = total.get(key, 0) + goals
    rows = []
    for key, goals in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]:
        team, name = key.split("|", 1)
        rows.append({"name": name, "team_index": int(team), "team": teams[int(team)]["name"], "goals": goals})
    return rows
