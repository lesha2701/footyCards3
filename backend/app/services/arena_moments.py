"""Card Arena "live" layer — pure helpers, no DB: the frozen squads a match
keeps in server_state, the choice cards of a moment, the auto-pick for a
skipped or timed-out moment, match goals, score-aware commentary and the man
of the match. match_service owns the rolls; matches started before this layer
(no state["live"]) and FUT Draft never reach any of it.
"""
import random
from types import SimpleNamespace
from typing import Optional

from app.models.enums import Position

DEFAULT_TUNING = {
    # Pass: how much the through ball opens the keeper up. The situation's
    # bias moves it, so "партнёр свободен" really is the better ball.
    "pass_keeper_drop": 7,
    "pass_bias_weight": 1.4,
    # Dribble: a duel with their back line. Beat him — almost an open goal.
    "dribble_fail_base": 0.44,
    "dribble_fail_per_point": 0.014,
    "dribble_keeper_drop": 20,
    "dribble_penalty_pct": 16,
    # Tackle: can be beaten, a foul outside the box is a dangerous free kick.
    "tackle_beaten_base": 0.27,
    "tackle_beaten_per_point": 0.012,
    "tackle_aerial_extra": 0.22,
    "free_kick_goal_pct": 16,
    # Block: reliable from range, hopeless once he's clean through.
    "block_fail_extra": 0.14,
    "block_one_on_one_extra": 0.3,
    "block_long_range_extra": -0.08,
    # Keeper off his line: claims it or leaves the goal open.
    "rush_base": 0.56,
    "rush_per_point": 0.016,
    "rush_one_on_one": 0.2,
    "rush_aerial": 0.04,
    "rush_long_range": -0.26,
    "rush_fail_goal": 0.62,
    "penalty_auto_goal": 0.76,
}


def tuning(config) -> dict:
    return {**DEFAULT_TUNING, **(getattr(config, "arena_decision_tuning", None) or {})}


def card_actor(card) -> dict:
    player = card.player
    rarity = getattr(player, "rarity", None)
    return {
        "user_card_id": card.id,
        "player_id": player.id,
        "name": player.display_name,
        "rating": player.rating,
        "position": getattr(player.position, "value", player.position),
        "image_path": getattr(player, "image_path", None),
        "rarity": getattr(rarity, "value", rarity),
    }


def snapshot_lineup(lineup) -> Optional[list[dict]]:
    """Who plays, frozen at kickoff: the second half and an all-in are drawn
    after the player could have changed the squad."""
    if lineup is None:
        return None
    return [{"category": s.category, **card_actor(s.card)} for s in lineup.slots if s.card]


def restore_lineup(snapshot: Optional[list[dict]]):
    """A lineup stand-in `_pick_actor` can read."""
    if not snapshot:
        return None
    slots = []
    for row in snapshot:
        player = SimpleNamespace(
            id=row["player_id"], display_name=row["name"], rating=row["rating"],
            position=Position(row["position"]), image_path=row.get("image_path"), rarity=row.get("rarity"),
        )
        slots.append(SimpleNamespace(category=row["category"], card=SimpleNamespace(id=row["user_card_id"], player=player)))
    return SimpleNamespace(slots=slots, chemistry=None)


def line_actor(squad: Optional[list[dict]], category: str, rating: int, label: str) -> dict:
    """Their man in a duel: a real card of their squad, or the bot's line."""
    pool = [row for row in (squad or []) if row["category"] == category]
    if pool:
        row = random.choice(pool)
        return {"name": row["name"], "rating": row["rating"], "position": row["position"],
                "image_path": row.get("image_path"), "rarity": row.get("rarity")}
    return {"name": label, "rating": rating, "position": category, "image_path": None, "rarity": None}


def keeper_of(squad: Optional[list[dict]]) -> Optional[dict]:
    return next((row for row in (squad or []) if row["category"] == "GK"), None)


def _public(actor: Optional[dict]) -> Optional[dict]:
    if not actor:
        return None
    return {k: actor.get(k) for k in ("name", "rating", "position", "image_path", "rarity")}


def attack_options(moment: dict, in_box: bool, one_on_one: bool, keeper: dict, defender: dict) -> list[dict]:
    shooter, target = moment["actors"]["shooter"], moment["actors"]["pass_target"]
    dribble_note = "Обыграл — вратарь почти один, потерял — атака сорвана"
    return [
        {"action": "shoot", "me": _public(shooter), "vs": _public(keeper), "risk": "mid",
         "note": "Выходит один на один" if one_on_one else "Бьёшь сразу, пока есть удар"},
        {"action": "pass", "me": _public(target), "vs": _public(keeper), "risk": "low",
         "note": "Партнёр в выгодной позиции, если пас дойдёт"},
        {"action": "dribble", "me": _public(shooter), "vs": _public(defender), "risk": "high",
         "note": dribble_note + (", в штрафной могут сфолить" if in_box else "")},
    ]


def defense_options(moment: dict, tags: tuple, in_box: bool, attacker: dict, keeper: Optional[dict], gk_rating: int) -> list[dict]:
    defender = moment["actors"]["defender"]
    my_keeper = _public(keeper) or {"name": "Вратарь", "rating": gk_rating, "position": "GK", "image_path": None, "rarity": None}
    through = "one_on_one" in tags or "breakaway" in tags
    if through:
        block, rush = "Он уже за спиной: перекрыть почти невозможно", "Сокращает угол — лучший шанс забрать мяч"
    elif "aerial" in tags:
        block, rush = "Верховая дуэль, здесь защитник силён", "Выход на навес: заберёт или пустые ворота"
    elif in_box:
        block, rush = "Надёжно, но можно не успеть", "Заберёт или оставит ворота пустыми"
    else:
        block, rush = "С дистанции перекрыть проще всего", "Далеко от ворот: большой риск"
    tackle = "Фол в штрафной — пенальти" if in_box else "Фол здесь — опасный штрафной"
    if "aerial" in tags:
        tackle = "Подкатом навес не снять, плюс риск пенальти"
    return [
        {"action": "tackle", "me": _public(defender), "vs": _public(attacker), "risk": "high" if in_box else "mid", "note": tackle},
        {"action": "block", "me": _public(defender), "vs": _public(attacker), "risk": "high" if through else "low", "note": block},
        {"action": "keeper", "me": my_keeper, "vs": _public(attacker), "risk": "mid" if through else "high", "note": rush},
    ]


def _best_action(moment: dict, state: dict) -> str:
    kind = moment.get("situation_kind")
    if kind == "attack":
        actors = moment["actors"]
        bias = float(moment.get("bias", 0))
        return "shoot" if actors["shooter"]["rating"] + bias >= actors["pass_target"]["rating"] - bias else "pass"
    if kind == "defense":
        tags = moment.get("tags") or []
        if "one_on_one" in tags or "breakaway" in tags:
            attacker = (moment.get("attacker") or {}).get("rating", 75)
            return "keeper" if state["ratings"]["user_gk"] >= attacker - 3 else "tackle"
        return "block"
    return (moment.get("actions") or ["strike"])[0]


def auto_action(moment: dict, state: dict, config) -> str:
    """A skipped or timed-out moment: a sensible but not a perfect pick, so a
    player who actually reads the moment still plays it better."""
    kind = moment.get("kind")
    if kind == "halftime":
        return "keep_style"
    if kind == "late_call":
        return "hold"
    if kind == "penalty":
        return "auto_penalty"
    actions = moment.get("actions") or []
    if len(actions) < 2:
        return actions[0] if actions else "strike"
    if random.randrange(100) < int(getattr(config, "arena_auto_best_pct", 60)):
        return _best_action(moment, state)
    return random.choice(actions)


MATCH_GOALS = {
    "clean_sheet": "Победи всухую",
    "win_by_two": "Победи с разницей в 2 мяча",
    "score_three": "Забей 3 гола",
    "no_cards": "Победи без карточек",
}


def pick_goal() -> str:
    return random.choice(tuple(MATCH_GOALS))


def goal_done(code: Optional[str], user_score: int, opponent_score: int, state: dict) -> bool:
    if code == "clean_sheet":
        return user_score > opponent_score and opponent_score == 0
    if code == "win_by_two":
        return user_score - opponent_score >= 2
    if code == "score_three":
        return user_score >= 3
    if code == "no_cards":
        return user_score > opponent_score and not state.get("cards")
    return False


def finish_goal(event: dict, scored_by: str, state: dict, moment: dict) -> None:
    """Names the scorer and says what the goal did to the match."""
    payload = event.get("payload") or {}
    event["payload"] = payload
    if scored_by == "user":
        name = payload.get("shooter") or (moment.get("taker") or {}).get("name")
        squad = (state.get("squads") or {}).get("user") or []
        scorer = next((row for row in squad if row["name"] == name), None)
        if scorer is None:
            # An open-goal chance has no actors: one of the forwards tapped it in.
            forwards = [row for row in squad if row["category"] == "FWD"] or squad
            scorer = random.choice(forwards) if forwards else None
            name = scorer["name"] if scorer else None
            if scorer:
                payload.update(shooter=name, shooter_id=scorer["user_card_id"])
    else:
        scorer = moment.get("attacker") or moment.get("taker")
        name = (scorer or {}).get("name")
    if name:
        event["description"] = f"{event['description']} ({name})"
    if scorer:
        payload["scorer"] = _public(scorer)
    mine, theirs = state["user_score"], state["opponent_score"]
    payload["score"] = [mine, theirs]
    line = None
    if event["minute"] >= 80:
        if scored_by == "user":
            line = "Спасает ничью на последних минутах!" if mine == theirs else (
                "Вырывает победу в концовке!" if mine == theirs + 1 else None)
        else:
            line = "Обидно: ничья ускользает" if theirs == mine + 1 else ("Соперник отыгрался в концовке" if mine == theirs else None)
    if line:
        event["description"] = f"{event['description']} {line}"
    payload["context"] = line


def man_of_the_match(state: dict, events: list) -> Optional[dict]:
    """Goals, assists and the defensive work of the played events."""
    squad = (state.get("squads") or {}).get("user") or []
    if not squad:
        return None
    by_id = {row["user_card_id"]: row for row in squad}
    by_name = {row["name"]: row for row in squad}
    keeper = keeper_of(squad)
    points: dict[int, int] = {}
    goals: dict[int, int] = {}
    assists: dict[int, int] = {}

    def add(row: Optional[dict], value: int) -> None:
        if row:
            points[row["user_card_id"]] = points.get(row["user_card_id"], 0) + value

    for e in events:
        payload = e.payload or {}
        if e.team == "user" and e.event_type == "goal":
            scorer = by_id.get(payload.get("shooter_id")) or by_name.get(payload.get("shooter"))
            add(scorer, 3)
            if scorer:
                goals[scorer["user_card_id"]] = goals.get(scorer["user_card_id"], 0) + 1
            helper = by_id.get(payload.get("assist_id"))
            add(helper, 2)
            if helper:
                assists[helper["user_card_id"]] = assists.get(helper["user_card_id"], 0) + 1
        elif e.team == "opponent" and e.event_type in ("tackle_won", "blocked"):
            add(by_name.get(payload.get("defender")), 1)
        elif e.team == "opponent" and e.event_type == "save":
            add(keeper, 1)
    if not points:
        return {"goals": goals, "assists": assists, "player": None}
    top = max(points, key=lambda card_id: (points[card_id], by_id[card_id]["rating"]))
    row = by_id[top]
    return {
        "goals": goals, "assists": assists,
        "player": {**(_public(row) or {}), "user_card_id": top, "goals": goals.get(top, 0), "assists": assists.get(top, 0)},
    }
