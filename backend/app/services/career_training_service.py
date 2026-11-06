"""«Карьера тренера»: the training plan before a round. Two sessions, the main
one and an extra one at second_pct of its strength, and an intensity: harder
work does more, tires more and hurts more often. Besides the plan, one player
at a time can be on an individual programme: he has to play program_rounds
matches for it, tires a little more meanwhile and ends up with a career rating
bonus until the season's end. Pure rules; the numbers are
career_tactics_tuning["training"], career_service applies what plan_effects
returns and shows the coach what the plan gave after the match.
"""
from typing import Optional

INTENSITY_LABELS = {"light": "Лёгкая", "normal": "Обычная", "hard": "Жёсткая"}
DEFAULT_INTENSITY = "normal"
UNIT_SESSIONS = {"attack": "FWD", "defence": "DEF"}
LATE_MINUTE = 70
SET_PIECE_GOALS = ("corner", "free_kick")


def _load(code: str) -> bool:
    return code not in ("recovery", "team_building")


def plan_effects(main: Optional[str], extra: Optional[str], intensity: Optional[str], tr: dict, fx: Optional[dict] = None,
                 team_building: int = 0) -> dict:
    """What the plan does to the next match; fx = «Клубная база» effects."""
    level = tr["intensity"].get(intensity or DEFAULT_INTENSITY) or tr["intensity"][DEFAULT_INTENSITY]
    out = {"fatigue": 0, "familiarity_tenths": 0, "opponent_boost": 1.0, "set_piece_boost": 1.0, "morale": 0,
           "fitness_mult": 1.0, "units": {}, "injury_mult": 1.0}
    sessions = [(code, pct) for code, pct in ((main, 100), (extra, int(tr["second_pct"]))) if code]
    if not sessions:
        return out
    out["injury_mult"] = int(level["injury_pct"]) / 100
    for code, pct in sessions:
        strength = pct * int(level["effect_pct"]) / 10000
        if _load(code):
            out["fatigue"] += round(tr["load_fatigue"] * int(level["load_pct"]) / 100)
        if code == "recovery":
            out["fatigue"] += round(tr["recovery_fatigue"] * strength) - int((fx or {}).get("recovery", 0))
        elif code == "tactical":
            out["familiarity_tenths"] += round(tr["tactical_familiarity_tenths"] * strength)
        elif code == "opponent":
            out["opponent_boost"] = round(1 + (tr["opponent_boost"] - 1) * strength, 3)
        elif code == "set_pieces":
            out["set_piece_boost"] = round(1 + (tr["set_piece_boost"] - 1) * strength, 3)
        elif code == "team_building":
            out["morale"] = round(team_building * strength)
        elif code == "fitness":
            out["fitness_mult"] = round(1 - (1 - tr["fitness_fatigue_mult"]) * strength, 3)
        elif code in UNIT_SESSIONS:
            out["units"][UNIT_SESSIONS[code]] = max(1, round(tr["unit_rating"] * strength))
    return out


def _pct(boost: float) -> int:
    return round((boost - 1) * 100)


def preview(fx: dict) -> list[str]:
    """The plan's effects in plain words, before the match."""
    lines = []
    if fx["familiarity_tenths"]:
        lines.append(f"Сыгранность в матче +{fx['familiarity_tenths'] / 10:g}%")
    if fx["opponent_boost"] > 1:
        lines.append(f"Сильные стороны против соперника +{_pct(fx['opponent_boost'])}%")
    if fx["set_piece_boost"] > 1:
        lines.append(f"Угловые и штрафные опаснее на {_pct(fx['set_piece_boost'])}%")
    if fx["morale"]:
        lines.append(f"Мораль +{fx['morale']}")
    if fx["fitness_mult"] < 1:
        lines.append(f"В матче устают на {round((1 - fx['fitness_mult']) * 100)}% меньше")
    if fx["units"].get("FWD"):
        lines.append(f"Нападающие +{fx['units']['FWD']} к рейтингу")
    if fx["units"].get("DEF"):
        lines.append(f"Защитники +{fx['units']['DEF']} к рейтингу")
    if fx["fatigue"]:
        lines.append(f"Усталость заявки {fx['fatigue']:+d}")
    if fx["injury_mult"] != 1:
        lines.append(f"Риск травм {round((fx['injury_mult'] - 1) * 100):+d}%")
    return lines


def plan_out(main: Optional[str], extra: Optional[str], intensity: Optional[str], tr: dict, fx: Optional[dict],
             team_building: int) -> dict:
    return {"extra": extra, "intensity": intensity or DEFAULT_INTENSITY, "second_pct": int(tr["second_pct"]),
            "intensities": [{"code": code, "label": label} for code, label in INTENSITY_LABELS.items()],
            "lines": preview(plan_effects(main, extra, intensity, tr, fx, team_building))}


def _plural_goals(n: int) -> str:
    d, h = n % 10, n % 100
    return "гол" if d == 1 and h != 11 else "гола" if 2 <= d <= 4 and not 12 <= h <= 14 else "голов"


def match_results(main: Optional[str], extra: Optional[str], fx: dict, events: Optional[list], side: str, own: int,
                  opp: int) -> list[str]:
    """What the sessions gave in the match that followed, for the report."""
    goals = [e for e in events or [] if e.get("event_type") == "goal" and e.get("team") in ("a", "b")]
    mine = [e for e in goals if e["team"] == side]
    theirs = [e for e in goals if e["team"] != side]
    lines = []
    for code in (main, extra):
        if code == "set_pieces":
            n = sum((e.get("payload") or {}).get("set_piece") in SET_PIECE_GOALS for e in mine)
            lines.append(f"Стандарты: {n} {_plural_goals(n)} с угловых и штрафных" if n else "Стандарты: в этот раз без голов")
        elif code == "fitness":
            late = (sum((e.get("minute") or 0) > LATE_MINUTE for e in mine), sum((e.get("minute") or 0) > LATE_MINUTE for e in theirs))
            lines.append(f"Физподготовка: концовка {late[0]}:{late[1]} после {LATE_MINUTE}-й минуты")
        elif code == "attack":
            lines.append(f"Атака: {own} {_plural_goals(own)} за матч")
        elif code == "defence":
            lines.append("Оборона: сухой матч" if opp == 0 else f"Оборона: пропущено {opp}")
        elif code == "recovery":
            lines.append(f"Восстановление: усталость заявки {fx['fatigue']:+d} к матчу")
        elif code == "tactical":
            lines.append(f"Тактика: сыгранность +{fx['familiarity_tenths'] / 10:g}% в матче")
        elif code == "opponent":
            lines.append("Разбор соперника: " + ("план сработал" if own > opp else "соперника не переиграли" if own < opp else "ничья в борьбе схем"))
        elif code == "team_building":
            lines.append(f"Сплочение: мораль +{fx['morale']}")
    return lines


# --- individual programme -----------------------------------------------------------------
# CareerParticipant.training_program: {"active": {"card_id", "name", "played"},
# "done": {card id: {"name", "bonus"}}}.

def program_start(program: Optional[dict], card_id: int, name: str, tr: dict) -> dict:
    program = dict(program or {})
    done = program.get("done") or {}
    if program.get("active"):
        raise ValueError("Один игрок за раз: сначала закончи или отмени программу")
    if str(card_id) in done:
        raise ValueError("Этот игрок уже прошёл программу в этом сезоне")
    if len(done) >= int(tr["program_limit"]):
        raise ValueError("Лимит программ на сезон исчерпан")
    program["active"] = {"card_id": card_id, "name": name, "played": 0}
    return program


def program_cancel(program: Optional[dict]) -> dict:
    return {**(program or {}), "active": None}


def program_card(program: Optional[dict]) -> Optional[int]:
    return ((program or {}).get("active") or {}).get("card_id")


def program_bonus(program: Optional[dict], card_id: int) -> int:
    return int((((program or {}).get("done") or {}).get(str(card_id)) or {}).get("bonus", 0))


def program_after_match(program: Optional[dict], played_ids: set, tr: dict) -> tuple[Optional[dict], Optional[str]]:
    """A match counts only if he was on the pitch. Returns the programme and
    the line for the report (None when he didn't play or nobody is on it)."""
    active = (program or {}).get("active")
    if not active or active["card_id"] not in played_ids:
        return program, None
    total = int(tr["program_rounds"])
    played = active["played"] + 1
    if played < total:
        return {**program, "active": {**active, "played": played}}, f"Программа: {active['name']} {played} из {total}"
    bonus = int(tr["program_bonus"])
    done = {**(program.get("done") or {}), str(active["card_id"]): {"name": active["name"], "bonus": bonus}}
    return {"active": None, "done": done}, f"Программа завершена: {active['name']} +{bonus} к рейтингу до конца сезона"


def program_out(program: Optional[dict], tr: dict) -> dict:
    done = (program or {}).get("done") or {}
    return {"active": (program or {}).get("active"), "rounds": int(tr["program_rounds"]), "bonus": int(tr["program_bonus"]),
            "fatigue": int(tr["program_fatigue"]), "limit": int(tr["program_limit"]),
            "done": [{"card_id": int(cid), **row} for cid, row in done.items()]}
