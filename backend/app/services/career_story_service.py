"""«Карьера тренера»: the club around the matches. The news feed, the stands
(mood, attendance, what they add to the stadium's income), the moments after a
round that ask the coach for a word (a press question, a hero, a player tired
of the bench), rivalries, the board's hot seat and the club's legends.

Pure rules over the season state and CareerProfile JSON; career_service calls
in once a round is played and stores what comes back. Numbers come from
tuning_of (GameConfig.career_tactics_tuning["story"] overrides any key).
"""
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from app.services import career_commentary_service as commentary

NEWS_KEEP = 40
LEGENDS_SHOWN = 5

DEFAULT_TUNING: dict = {
    "fans_start": 50, "fans_win": 6, "fans_draw": 0, "fans_loss": -6, "fans_rout": 3, "fans_rout_margin": 3,
    "derby_mult": 2, "revenge_fans": 4,
    "capacity_base": 4000, "capacity_per_coin": 25,
    "income_min_pct": 85, "income_max_pct": 120,
    "bench_rounds": 3, "bench_rounds_grumbler": 2,
    "promise_kept_morale": 3, "promise_broken_morale": -5,
    "streak": 3, "big_loss": 3, "big_win": 3,
    "hot_seat_fails": 2, "hot_seat_rep": -20,
}

# code -> question and answers: (answer code, text, morale, fans).
MOMENTS: dict[str, dict] = {
    "press_big_win": {"kind": "press", "text": "Журналист: «{score} против «{opp}»! Команда готова бороться за самое высокое?»", "answers": [
        ("bold", "Да, мы идём за первым местом", 4, 3), ("calm", "Это один матч. Работаем дальше", 2, 0),
        ("credit", "Вся заслуга у игроков", 3, 1)]},
    "press_big_loss": {"kind": "press", "text": "Журналист: «{score} против «{opp}». Кто отвечает за такой результат?»", "answers": [
        ("own", "Я. Это моя ответственность", 3, 2), ("players", "Игроки сегодня не вышли на матч", -3, 1),
        ("next", "Разберём и забудем", 1, -1)]},
    "press_win_streak": {"kind": "press", "text": "Журналист: «{streak} победы подряд. В чём секрет?»", "answers": [
        ("team", "Раздевалка едина", 3, 1), ("plan", "Просто следуем плану", 1, 0), ("title", "Нас уже не остановить", 2, 4)]},
    "press_loss_streak": {"kind": "press", "text": "Журналист: «{streak} поражения подряд. Болельщики недовольны. Что скажете им?»", "answers": [
        ("sorry", "Извиняемся, исправимся", 1, 4), ("trust", "Я верю в этих ребят", 4, 0), ("change", "Скоро будут перемены в составе", -2, 2)]},
    "press_derby": {"kind": "press", "text": "Журналист: «Принципиальный матч с «{opp}» — {score}. Что он значит для клуба?»", "answers": [
        ("city", "Это матч для наших болельщиков", 2, 5), ("cold", "Обычный матч чемпионата", 1, -2), ("fire", "Такие игры делают команду", 4, 1)]},
    "player_hero": {"kind": "player", "text": "{name} — герой матча с «{opp}». Скажешь что-нибудь в раздевалке?", "answers": [
        ("praise", "Похвалить при всех", 3, 0), ("ground", "Спокойно: впереди ещё матчи", 1, 0)]},
    "player_bench": {"kind": "player", "text": "{name} подошёл после тренировки: «Тренер, я уже {rounds} матча без игры. Дайте мне шанс».", "answers": [
        ("promise", "В следующем матче сыграешь", 0, 0), ("wait", "Твоё время придёт, работай", -2, 0)]},
}

FAN_LABELS = ((80, "Трибуны поют"), (60, "Болельщики довольны"), (40, "Спокойно"), (20, "Недовольный гул"), (0, "Стадион свистит"))


def tuning_of(career_tuning: Optional[dict]) -> dict:
    return {**DEFAULT_TUNING, **((career_tuning or {}).get("story") or {})}


def _league(profile: Any) -> dict:
    return dict(profile.league or {})


def _save_league(profile: Any, league: dict) -> None:
    profile.league = league
    flag_modified(profile, "league")


# --- news ---------------------------------------------------------------------------------

def add_news(state: dict, team: int, round_index: int, icon: str, text: str, tone: str = "plain") -> None:
    feed = state.setdefault("news", {}).setdefault(str(team), [])
    feed.append({"round": round_index, "icon": icon, "text": text, "tone": tone})
    del feed[:-NEWS_KEEP]


def news_out(state: dict, team: int, upto: Optional[int] = None) -> list[dict]:
    """Newest first; `upto` leaves out a round still on air."""
    feed = (state.get("news") or {}).get(str(team)) or []
    return [n for n in reversed(feed) if upto is None or n["round"] < upto]


# --- the stands ---------------------------------------------------------------------------

def fans_mood(state: dict, team: int, profile: Any, tuning: dict) -> int:
    stored = (state.get("fans") or {}).get(str(team))
    if stored is not None:
        return int(stored)
    return int(_league(profile).get("fans", tuning["fans_start"])) if profile is not None else int(tuning["fans_start"])


def _set_fans(state: dict, team: int, profile: Any, value: float) -> int:
    value = max(0, min(100, round(value)))
    state.setdefault("fans", {})[str(team)] = value
    if profile is not None:
        league = _league(profile)
        league["fans"] = value
        _save_league(profile, league)
    return value


def capacity(fx: Optional[dict], tuning: dict) -> int:
    """The stadium's seats, from what «Клубная база» earns on a match day."""
    return int(tuning["capacity_base"]) + int((fx or {}).get("matchday", 0)) * int(tuning["capacity_per_coin"])


def attendance(mood: int, fx: Optional[dict], tuning: dict) -> int:
    return capacity(fx, tuning) * (55 + mood * 45 // 100) // 100


def income_pct(mood: int, tuning: dict) -> int:
    """100 at the neutral 50, down to income_min_pct and up to income_max_pct."""
    low, high = int(tuning["income_min_pct"]), int(tuning["income_max_pct"])
    return low + (100 - low) * mood // 50 if mood <= 50 else 100 + (high - 100) * (mood - 50) // 50


def fans_out(state: dict, team: int, profile: Any, fx: Optional[dict], tuning: dict) -> dict:
    mood = fans_mood(state, team, profile, tuning)
    return {"mood": mood, "label": next(text for low, text in FAN_LABELS if mood >= low),
            "attendance": attendance(mood, fx, tuning), "capacity": capacity(fx, tuning), "income_pct": income_pct(mood, tuning)}


# --- rivals -------------------------------------------------------------------------------

def rivalry(profile: Any, club_id: Optional[int], name: str) -> Optional[dict]:
    """What this club means to the coach: the one that hurt him last season,
    or the club he has met most (at least three times)."""
    if profile is None or club_id is None:
        return None
    league = _league(profile)
    nemesis = league.get("nemesis") or {}
    if nemesis.get("club_id") == club_id:
        return {"kind": "nemesis", "text": f"Обидчик прошлого сезона: {nemesis['score']}"}
    history = league.get("history") or {}
    met = {key: sum(row.get(k, 0) for k in "wdl") for key, row in history.items()}
    if met and max(met.values()) >= 3 and max(met, key=lambda k: (met[k], k)) == str(club_id):
        return {"kind": "derby", "text": f"Принципиальное противостояние с «{name}»"}
    return None


def set_nemesis(profile: Any, state: dict, team: int) -> None:
    """At the season's end: the bot club behind the coach's heaviest defeat."""
    worst = None
    for round_results in state.get("results") or []:
        for m in round_results:
            if team not in (m["home"], m["away"]):
                continue
            own, opp, other = (m["hs"], m["as"], m["away"]) if m["home"] == team else (m["as"], m["hs"], m["home"])
            club = (state["teams"][other]).get("club_id")
            if own < opp and club is not None and (worst is None or opp - own >= worst[0]):
                worst = (opp - own, club, f"{own}:{opp}")
    league = _league(profile)
    league["nemesis"] = {"club_id": worst[1], "score": worst[2]} if worst else None
    _save_league(profile, league)


# --- moments ------------------------------------------------------------------------------

def _streak(state: dict, team: int) -> tuple[str, int]:
    run: list[str] = []
    for round_results in state.get("results") or []:
        for m in round_results:
            if team in (m["home"], m["away"]):
                own, opp = (m["hs"], m["as"]) if m["home"] == team else (m["as"], m["hs"])
                run.append("W" if own > opp else "D" if own == opp else "L")
    if not run:
        return "", 0
    n = 0
    for result in reversed(run):
        if result != run[-1]:
            break
        n += 1
    return run[-1], n


def _hero(events: Optional[list], side: str) -> Optional[str]:
    goals: dict = {}
    for event in events or []:
        name = (event.get("payload") or {}).get("shooter")
        if event.get("event_type") == "goal" and event.get("team") == side and name:
            goals[name] = goals.get(name, 0) + 1
    best = max(goals.items(), key=lambda kv: kv[1], default=None)
    return best[0] if best and best[1] >= 2 else None


def _pick_moment(state: dict, team: int, match: dict, own: int, opp: int, opp_name: str, side: str, rival: Optional[dict],
                 benched: Optional[tuple], tuning: dict) -> Optional[tuple[str, dict]]:
    score = f"{own}:{opp}"
    result, streak = _streak(state, team)
    common = {"score": score, "opp": opp_name, "streak": streak}
    if rival and rival["kind"] == "derby":
        return "press_derby", common
    if own - opp >= int(tuning["big_win"]):
        return "press_big_win", common
    if opp - own >= int(tuning["big_loss"]):
        return "press_big_loss", common
    if streak >= int(tuning["streak"]) and result in ("W", "L"):
        return ("press_win_streak" if result == "W" else "press_loss_streak"), common
    hero = _hero(match.get("events"), side)
    if hero:
        return "player_hero", {**common, "name": hero}
    if benched:
        return "player_bench", {**common, "name": benched[1], "rounds": benched[2], "card_id": benched[0]}
    return None


def _render(code: str, data: dict) -> str:
    return MOMENTS[code]["text"].format(**{"name": "", "rounds": 0, **data})


def moment_out(state: dict, team: int, rounds_played: int) -> Optional[dict]:
    """The question waiting for the coach after the last round played."""
    current = (state.get("moments") or {}).get(str(team))
    if not current or current.get("answer") or current["round"] != rounds_played - 1:
        return None
    spec = MOMENTS[current["code"]]
    return {"kind": spec["kind"], "text": _render(current["code"], current["data"]),
            "answers": [{"code": code, "text": text, "morale": morale, "fans": fans}
                        for code, text, morale, fans in spec["answers"]]}


def answer_moment(state: dict, team: int, rounds_played: int, answer: str, profile: Any, tuning: dict) -> int:
    """Stores the coach's word; returns the change to the team's morale."""
    current = (state.get("moments") or {}).get(str(team))
    if not current or current.get("answer") or current["round"] != rounds_played - 1:
        raise ValueError("Вопрос уже не актуален")
    spec = MOMENTS[current["code"]]
    chosen = next((a for a in spec["answers"] if a[0] == answer), None)
    if chosen is None:
        raise ValueError("Такого ответа нет")
    _code, text, morale_delta, fans_delta = chosen
    current["answer"] = answer
    if fans_delta:
        _set_fans(state, team, profile, fans_mood(state, team, profile, tuning) + fans_delta)
    if answer == "promise":
        state.setdefault("promises", {})[str(team)] = {
            "card_id": current["data"]["card_id"], "name": current["data"]["name"], "round": rounds_played,
        }
    add_news(state, team, current["round"], "🎙" if spec["kind"] == "press" else "💬", f"Тренер: «{text}»")
    return morale_delta


# --- after a round ------------------------------------------------------------------------

def _bench_update(state: dict, team: int, squad_ids: list, played_ids: set, fit_ids: set, names: dict,
                  traits: dict, tuning: dict) -> Optional[tuple]:
    """Rounds without a minute per squad player; the first who ran out of patience."""
    book = dict((state.get("bench_rounds") or {}).get(str(team)) or {})
    wants = None
    for cid in squad_ids:
        key = str(cid)
        if cid in played_ids or cid not in fit_ids:
            book.pop(key, None)
            continue
        book[key] = book.get(key, 0) + 1
        limit = int(tuning["bench_rounds_grumbler"] if traits.get(cid) == "grumbler" else tuning["bench_rounds"])
        if wants is None and book[key] >= limit:
            wants = (cid, names.get(cid, "Игрок"), book[key])
            book[key] = 0  # he asks once, then waits again
    state.setdefault("bench_rounds", {})[str(team)] = book
    return wants


def _others_news(state: dict, team: int, results: list, round_index: int, before_leader: Optional[int], top_before: Optional[str],
                 standings: list) -> None:
    teams = state["teams"]
    leader = standings[0]["team_index"] if standings else None
    if leader is not None and leader != before_leader and round_index > 0:
        if leader == team:
            add_news(state, team, round_index, "👑", "Мы возглавили таблицу!", "good")
        else:
            add_news(state, team, round_index, "📊", f"Новый лидер лиги — «{teams[leader]['name']}»")
    others = [m for m in results if team not in (m["home"], m["away"])]
    rout = max(others, key=lambda m: abs(m["hs"] - m["as"]), default=None)
    if rout and abs(rout["hs"] - rout["as"]) >= 4:
        add_news(state, team, round_index, "💥", f"«{teams[rout['home']]['name']}» — «{teams[rout['away']]['name']}» {rout['hs']}:{rout['as']}: главный разгром тура")
    scorers = commentary.top_scorers(state, limit=1)
    if scorers and scorers[0]["name"] != top_before and scorers[0]["goals"] >= 3:
        add_news(state, team, round_index, "🥇", f"{scorers[0]['name']} («{scorers[0]['team']}») вышел в лидеры гонки бомбардиров: {scorers[0]['goals']}")


def after_round(state: dict, *, team: int, round_index: int, match: dict, own: int, opp: int, is_home: bool, opponent: dict,
                results: list, report: dict, played_ids: set, fit_ids: set, squad_ids: list, names: dict, traits: dict,
                profile: Any, fx: Optional[dict], tuning: dict, standings: list, before_leader: Optional[int],
                top_before: Optional[str], moments_on: bool) -> int:
    """What a played round left behind for a human team: the stands, the news,
    a promise kept or broken, the next moment. Returns the morale change."""
    side = "a" if is_home else "b"
    rival = rivalry(profile, opponent.get("club_id"), opponent["name"])
    add_news(state, team, round_index, "⚽", commentary.story(match.get("events"), match_name(state, match, "home"), match_name(state, match, "away"),
                                                              match["hs"], match["as"])[0] if match.get("events") else f"{own}:{opp} против «{opponent['name']}»",
             "good" if own > opp else "bad" if own < opp else "plain")

    # The stands react to the result (a derby twice as much).
    delta = int(tuning["fans_win"] if own > opp else tuning["fans_draw"] if own == opp else tuning["fans_loss"])
    if abs(own - opp) >= int(tuning["fans_rout_margin"]):
        delta += int(tuning["fans_rout"]) * (1 if own > opp else -1)
    if rival and rival["kind"] == "derby":
        delta *= int(tuning["derby_mult"])
    if rival and rival["kind"] == "nemesis" and own > opp:
        delta += int(tuning["revenge_fans"])
        add_news(state, team, round_index, "🔥", f"Реванш! Обидчик прошлого сезона «{opponent['name']}» повержен", "good")
    mood = _set_fans(state, team, profile, fans_mood(state, team, profile, tuning) + delta)
    if is_home:
        report["attendance"] = attendance(mood, fx, tuning)
        add_news(state, team, round_index, "🏟", f"На трибунах {report['attendance']:,} зрителей".replace(",", " "))

    # What happened to my players.
    for name in report.get("injured") or []:
        add_news(state, team, round_index, "✚", f"{name} получил травму", "bad")
    for name in report.get("red") or []:
        add_news(state, team, round_index, "🟥", f"{name} удалён и пропустит матч", "bad")
    for text in report.get("auto_subs") or []:
        add_news(state, team, round_index, "⇄", f"Автозамена в старте: {text}")
    for text in report.get("training") or []:
        add_news(state, team, round_index, "🏋", text)
    place, before = report.get("place"), None
    previous = ((state.get("reports") or {}).get(str(round_index - 1)) or {}).get(str(team)) or {}
    before = previous.get("place")
    if place is not None and before is not None and abs(before - place) >= 2:
        add_news(state, team, round_index, "📈" if place < before else "📉", f"С {before}-го места на {place}-е", "good" if place < before else "bad")
    _others_news(state, team, results, round_index, before_leader, top_before, standings)

    # A promise to a benched player.
    morale_delta = 0
    promise = (state.get("promises") or {}).get(str(team))
    if promise and promise["round"] == round_index:
        kept = promise["card_id"] in played_ids
        morale_delta += int(tuning["promise_kept_morale"] if kept else tuning["promise_broken_morale"])
        add_news(state, team, round_index, "💬", f"{promise['name']}: " + ("тренер сдержал слово" if kept else "тренер обещал, но не выпустил"),
                 "good" if kept else "bad")
        state["promises"].pop(str(team), None)

    benched = _bench_update(state, team, squad_ids, played_ids, fit_ids, names, traits, tuning)
    if moments_on:
        picked = _pick_moment(state, team, match, own, opp, opponent["name"], side, rival, benched, tuning)
        if picked:
            state.setdefault("moments", {})[str(team)] = {"round": round_index, "code": picked[0], "data": picked[1], "answer": None}
    return morale_delta


def match_name(state: dict, match: dict, key: str) -> str:
    return state["teams"][match[key]]["name"]


# --- the board ----------------------------------------------------------------------------

def hot_seat_out(profile: Any) -> Optional[dict]:
    seat = _league(profile).get("hot_seat")
    return {"level": seat["level"], "text": "Руководство недовольно. Задание на сезон — остаться в лиге и не вылететь: иначе новый штраф к репутации."} if seat else None


def board_verdict(profile: Any, objective_met: bool, relegated: bool, tuning: dict) -> tuple[int, str]:
    """The season's end in the president's office: a coach is never sacked.
    A second failure in a row or a failed relegation puts him on the hot seat:
    a reputation penalty and a set task for next season. Doing it clears the
    seat; failing it costs more. Returns (reputation change, line for the note)."""
    league = _league(profile)
    seat = league.get("hot_seat")
    fails = 0 if objective_met else int(league.get("failed_seasons", 0)) + 1
    league["failed_seasons"] = fails
    rep, text = 0, ""
    if seat and objective_met:
        league["hot_seat"] = None
        text = "\nРуководство снова доверяет тренеру: горячее кресло позади"
    elif seat:
        league["hot_seat"] = {"level": seat["level"] + 1}
        rep = int(tuning["hot_seat_rep"]) * (seat["level"] + 1)
        text = f"\nГорячее кресло: задание провалено, штраф {rep} к репутации. Новое задание — на следующий сезон"
    elif not objective_met and (relegated or fails >= int(tuning["hot_seat_fails"])):
        league["hot_seat"] = {"level": 1}
        rep = int(tuning["hot_seat_rep"])
        text = f"\nГорячее кресло: штраф {rep} к репутации и задание руководства на следующий сезон"
    _save_league(profile, league)
    return rep, text


# --- legends ------------------------------------------------------------------------------

def record_legends(profile: Any, season_id: int, played: dict, events: Optional[list], side: str, own: int, opp: int,
                   opponent: str) -> None:
    """Appearances and goals of the coach's players (`played`: card id -> name)
    and the club's records, across seasons."""
    league = _league(profile)
    legends = dict(league.get("legends") or {})
    players = dict(legends.get("players") or {})
    records = dict(legends.get("records") or {})
    for cid, name in played.items():
        row = dict(players.get(str(cid)) or {"name": name, "apps": 0, "goals": 0, "assists": 0, "seasons": 0, "last": None})
        row["apps"] += 1
        if row["last"] != season_id:
            row["seasons"], row["last"] = row["seasons"] + 1, season_id
        players[str(cid)] = row
    for event in events or []:
        payload = event.get("payload") or {}
        if event.get("event_type") == "goal" and event.get("team") == side:
            for key, stat in (("shooter_id", "goals"), ("assist_id", "assists")):
                row = players.get(str(payload.get(key)))
                if row:
                    players[str(payload[key])] = {**row, stat: row[stat] + 1}
    if own - opp > int((records.get("biggest_win") or {}).get("margin", 0)):
        records["biggest_win"] = {"margin": own - opp, "score": f"{own}:{opp}", "opponent": opponent}
    records["streak"] = int(records.get("streak", 0)) + 1 if own > opp else 0
    records["best_streak"] = max(int(records.get("best_streak", 0)), records["streak"])
    legends.update(players=players, records=records)
    league["legends"] = legends
    _save_league(profile, league)


def legends_out(profile: Any) -> Optional[dict]:
    legends = _league(profile).get("legends")
    if not legends:
        return None
    rows = sorted((legends.get("players") or {}).values(), key=lambda r: (-r["goals"], -r["apps"], r["name"]))
    return {
        "players": [{k: r[k] for k in ("name", "apps", "goals", "assists", "seasons")} for r in rows[:LEGENDS_SHOWN]],
        "apps_leader": max(rows, key=lambda r: r["apps"])["name"] if rows else None,
        "biggest_win": (legends.get("records") or {}).get("biggest_win"),
        "best_streak": int((legends.get("records") or {}).get("best_streak", 0)),
    }


def keep_rosters(profile: Any, teams: list[dict]) -> None:
    """What the clubs of the coach's next league keep: their players (with
    their edge over the club's level, so a star stays one) and their place
    among the rivals."""
    league = _league(profile)
    league["rosters"] = {
        str(t["club_id"]): {"players": {p["slot"]: [p["player_id"], p.get("edge", 0)] for p in t["players"]},
                            "spread": t.get("spread", 0)}
        for t in teams if t.get("club_id") in (league.get("next_clubs") or []) and t.get("players")
    }
    _save_league(profile, league)
