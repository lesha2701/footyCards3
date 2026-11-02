"""Team morale of «Карьера тренера» and how the coach handles it.

Every team of a season (bots too) has a morale 0..100, kept in
season.state["morale"] for seasons started with it on
(GameConfig.career_morale_enabled). Its level (-2..+2, LEVELS) moves the
match rating of all the team's players by that many points — a team on a
roll plays above itself, a beaten one below.

The coach's levers:
  * «Речь перед матчем» (SPEECHES), chosen per round: what it does depends
    on the team's mood and on who is the favourite, so there is no speech
    that is always right.
  * «Разговор в перерыве» (TALKS), in the live match centre's half-time
    orders: depends on the score and the mood, for the second half.
  * «Сплочение» (training team_building): morale up before the match.

After a league match morale moves by the result (an upset counts more, a
rout too), the speech's after-effect, the flank duels and a pull back to
the start value. Pure functions here; career_service stores the numbers
and wires the bonuses into CareerSideRunner (morale_bonus, talk).
Numbers: GameConfig.career_tactics_tuning["morale"] over DEFAULT_TUNING.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# (lowest morale of the level, level, label)
LEVELS: tuple[tuple[int, int, str], ...] = (
    (90, 2, "Эйфория"), (70, 1, "На подъёме"), (40, 0, "Ровная"), (20, -1, "Не в духе"), (0, -2, "Подавлена"),
)

SPEECHES: dict[str, tuple[str, str]] = {
    "inspire": ("Вдохновить", "+1 к рейтингу, если команда не на подъёме; заряженных не разогреть сильнее."),
    "calm": ("Снять давление", "Плохое настроение не мешает в этом матче; после поражения мораль падает вдвое меньше."),
    "demand": ("Потребовать", "Фаворитом: +1 и больше морали за победу. Андердогом давит: −1. Ставки выше в обе стороны."),
}
TALKS: dict[str, tuple[str, str]] = {
    "praise": ("Похвалить", "Ведём: +1 во втором тайме. Проигрываем — расслабит (−1). В эйфории не работает."),
    "rouse": ("Встряхнуть", "Проигрываем: +1. Ведём — разозлит (−1). Подавленную команду ломает (−1)."),
    "calm": ("Успокоить", "Ничья: +1 во втором тайме, иначе без эффекта."),
}

DEFAULT_TUNING: dict[str, Any] = {
    "start": 60,
    "rating_per_level": 1,
    # The whole morale + speech + talk shift of a player's rating.
    "cap": 3,
    "win": 8, "draw": 0, "loss": -8,
    # Beating a stronger team / losing to a weaker one (average XI rating
    # by at least `favourite_gap`), and a margin of `rout_margin` goals.
    "upset": 4, "rout": 3, "rout_margin": 3, "favourite_gap": 2,
    "demand_win": 4, "demand_loss": -4,
    # Flank duels: my players won (lost) the decided duels by this margin.
    "duels_margin": 4, "duels": 2,
    # Pull back toward `start` each round (share of the gap).
    "regress": 0.1,
    "team_building": 6,
}


def tuning_of(career_tuning: Optional[dict]) -> dict:
    custom = (career_tuning or {}).get("morale") or {}
    return {**DEFAULT_TUNING, **custom}


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def level_of(value: float) -> tuple[int, str]:
    for low, level, label in LEVELS:
        if value >= low:
            return level, label
    return LEVELS[-1][1], LEVELS[-1][2]


def favourite_of(own_rating: float, opp_rating: float, tuning: dict) -> int:
    """+1 favourite, -1 underdog, 0 even (average XI ratings)."""
    gap = own_rating - opp_rating
    return 1 if gap >= tuning["favourite_gap"] else -1 if gap <= -tuning["favourite_gap"] else 0


def match_bonus(value: float, speech: Optional[str], favourite: int, tuning: dict,
                skills: Optional[dict] = None) -> tuple[int, int, list[str]]:
    """(mood shift, speech shift, reasons) of every player's rating for the
    match; the mood part goes through each player's trait (player_mood).
    «Оратор» (ORATOR_PERKS): a speech never backfires, a good one is stronger."""
    orator = (skills or {}).get("orator", 0)
    level, label = level_of(value)
    mood = level * tuning["rating_per_level"]
    reasons = [f"мораль «{label}»: {mood:+d}"] if mood else []
    extra = 0
    if speech == "inspire" and level <= 0:
        extra = 1
        reasons.append("речь «Вдохновить»: +1")
    elif speech == "calm" and mood < 0:
        extra = -mood
        reasons.append(f"речь «Снять давление»: {extra:+d}")
    elif speech == "demand" and favourite:
        extra = favourite
        if extra < 0 and orator_perk(orator, "speech_safe"):
            extra = 0
            reasons.append("речь «Потребовать»: андердогу не давит (Оратор)")
        else:
            reasons.append(f"речь «Потребовать»: {extra:+d}" + (" (давит на андердога)" if favourite < 0 else ""))
    plus = orator_perk(orator, "speech_plus")
    if extra > 0 and plus:
        extra += plus
        reasons.append(f"Оратор: речь сильнее {plus:+d}")
    return mood, extra, reasons


def talk_bonus(talk: Optional[str], value: float, own: int, opp: int, orator: int = 0) -> int:
    """Second-half rating shift of the half-time talk. «Оратор»
    (ORATOR_PERKS, `orator` — his level): it never backfires, a good one
    gives more."""
    bonus = _talk(talk, value, own, opp)
    if bonus < 0 and orator_perk(orator, "talk_safe"):
        return 0
    if bonus > 0:
        return bonus + orator_perk(orator, "talk_plus")
    return bonus


def _talk(talk: Optional[str], value: float, own: int, opp: int) -> int:
    level, _ = level_of(value)
    diff = own - opp
    if talk == "praise":
        if level >= 2:
            return 0
        return 1 if diff > 0 else -1 if diff < 0 else 0
    if talk == "rouse":
        if level <= -1:
            return -1
        return 1 if diff < 0 else -1 if diff > 0 else 0
    if talk == "calm":
        return 1 if diff == 0 else 0
    return 0


def after_match(value: float, own: int, opp: int, favourite: int, speech: Optional[str],
                duels: Optional[tuple[int, int]], tuning: dict, skills: Optional[dict] = None,
                extra: tuple[int, list[str]] = (0, []), coach: Optional[dict] = None) -> tuple[int, list[str]]:
    """Morale after a league match: (new value, reasons). `skills` — the
    coach's specialization levels («Мотиватор», «Психолог»; numbers from
    `coach`, COACH_TUNING by default), `extra` — the players' traits."""
    t = tuning
    skills = skills or {}
    coach = coach or COACH_TUNING
    delta, reasons = 0.0, []
    if own > opp:
        delta += t["win"]
        reasons.append(f"победа {t['win']:+d}")
        if favourite < 0:
            delta += t["upset"]
            reasons.append(f"обыграли фаворита {t['upset']:+d}")
        if own - opp >= t["rout_margin"]:
            delta += t["rout"]
            reasons.append(f"разгром {t['rout']:+d}")
        if speech == "demand":
            delta += t["demand_win"]
            reasons.append(f"требование выполнено {t['demand_win']:+d}")
        if skills.get("motivator"):
            boost = delta * coach["motivator_pct"] * skills["motivator"] / 100
            delta += boost
            reasons.append(f"Мотиватор {round(boost):+d}")
    elif own < opp:
        loss = t["loss"]
        if favourite > 0:
            loss -= t["upset"]
        if opp - own >= t["rout_margin"]:
            loss -= t["rout"]
        if speech == "calm":
            loss /= 2
        if skills.get("psychologist"):
            loss *= max(0.0, 1 - coach["psychologist_pct"] * skills["psychologist"] / 100)
        delta += loss
        reasons.append(f"поражение {round(loss):+d}" + (" (без давления — вдвое мягче)" if speech == "calm" else "")
                       + (" (Психолог)" if skills.get("psychologist") else ""))
        if speech == "demand":
            delta += t["demand_loss"]
            reasons.append(f"требование не выполнено {t['demand_loss']:+d}")
    elif t["draw"]:
        delta += t["draw"]
        reasons.append(f"ничья {t['draw']:+d}")
    if duels is not None:
        won, lost = duels
        if won - lost >= t["duels_margin"]:
            delta += t["duels"]
            reasons.append(f"выиграли дуэли {t['duels']:+d}")
        elif lost - won >= t["duels_margin"]:
            delta -= t["duels"]
            reasons.append(f"проиграли дуэли {-t['duels']:+d}")
    delta += extra[0]
    reasons += extra[1]
    moved = value + delta
    moved += (t["start"] - moved) * t["regress"]
    return clamp(moved), reasons


# --- season state ------------------------------------------------------------------------

def is_on(state: dict) -> bool:
    return bool((state or {}).get("morale"))


def initial(team_count: int, tuning: dict) -> dict:
    return {"teams": {str(i): tuning["start"] for i in range(team_count)}, "log": {}, "speeches": {}}


def value_of(state: dict, team_index: int, tuning: dict) -> int:
    return int(((state.get("morale") or {}).get("teams") or {}).get(str(team_index), tuning["start"]))


def speech_for(state: dict, team_index: int, round_index: int) -> Optional[str]:
    entry = ((state.get("morale") or {}).get("speeches") or {}).get(str(team_index)) or {}
    return entry.get("speech") if entry.get("round") == round_index else None


def view(state: dict, team_index: int, round_index: int, tuning: dict) -> Optional[dict]:
    """The morale card: value, level, its rating effect, the last changes,
    the speech chosen for the next round and the options."""
    if not is_on(state):
        return None
    value = value_of(state, team_index, tuning)
    level, label = level_of(value)
    return {
        "value": value, "level": level, "label": label, "rating": level * tuning["rating_per_level"],
        "log": ((state["morale"].get("log") or {}).get(str(team_index)) or [])[-5:],
        "speech": speech_for(state, team_index, round_index),
        "speeches": [{"code": c, "label": lbl, "hint": hint} for c, (lbl, hint) in SPEECHES.items()],
        "talks": [{"code": c, "label": lbl, "hint": hint} for c, (lbl, hint) in TALKS.items()],
        "team_building": tuning["team_building"],
    }


# --- character traits (stage 3): how a footballer lives with the team's mood -------------
# Only about morale, so they never overlap the card skills or the «Академия»
# talents («Боец», «Капитан», «Большие матчи», …). players.character_trait:
# NULL = derived (trait_of), "none" = set to no trait in the admin.

TRAITS: dict[str, tuple[str, str, str]] = {
    "spark": ("Заводила", "🎉", "Сыграл и победили — мораль команды растёт сильнее."),
    "stoic": ("Стоик", "🗿", "Плохое настроение команды не снижает его рейтинг."),
    "emotional": ("Эмоциональный", "🎭", "Настроение команды влияет на него вдвое сильнее — в обе стороны."),
    "peacemaker": ("Миротворец", "🕊️", "Сыграл и проиграли — мораль падает слабее."),
    "grumbler": ("Ворчун", "😤", "Остался без игры — мораль команды после матча ниже."),
}
_TRAIT_POOL = ("spark", "stoic", "emotional", "peacemaker", "grumbler")
TRAIT_TUNING: dict[str, Any] = {"spark": 2, "peacemaker": 2, "grumbler": 2, "share_pct": 30}


def trait_of(player: Any, share_pct: int = TRAIT_TUNING["share_pct"]) -> Optional[str]:
    """The player's character trait: set in the admin, else a stable derived
    one for about share_pct% of the footballers (by person, so every
    version of him agrees)."""
    import zlib

    from app.services.player_identity import person_key

    trait = getattr(player, "character_trait", None)
    if trait in TRAITS:
        return trait
    if trait == "none":
        return None
    roll = zlib.crc32(("trait:" + person_key(player)).encode())
    if roll % 100 >= share_pct:
        return None
    return _TRAIT_POOL[(roll // 100) % len(_TRAIT_POOL)]


def player_mood(mood: int, trait: Optional[str]) -> int:
    """The mood part of one player's rating shift, after his trait."""
    if trait == "stoic" and mood < 0:
        return 0
    if trait == "emotional":
        return mood * 2
    return mood


def trait_delta(own: int, opp: int, played: set[str], benched: set[str], tuning: dict) -> tuple[int, list[str]]:
    """Morale after the match from the traits of those who played (spark,
    peacemaker) and those left out (grumbler); each trait counts once."""
    t = {**TRAIT_TUNING, **(tuning.get("traits") or {})}
    delta, reasons = 0, []
    if own > opp and "spark" in played:
        delta += t["spark"]
        reasons.append(f"заводила в составе {t['spark']:+d}")
    if own < opp and "peacemaker" in played:
        delta += t["peacemaker"]
        reasons.append(f"миротворец в составе {t['peacemaker']:+d}")
    if "grumbler" in benched:
        delta -= t["grumbler"]
        reasons.append(f"ворчун без игры {-t['grumbler']:+d}")
    return delta, reasons


# --- coach specialization (stage 3): one, levelled slowly with experience ------------------
# A coach can't be everything at once: he picks ONE specialization and only
# it works and earns experience. CareerProfile.coach_skills =
# {"spec": code, "xp": {code: n}, "changed_at": iso}; every spec keeps its
# own experience, so switching back (once per `switch_days`) resumes it.
# Experience: every league match of a season with morale (win / draw / loss)
# and the final place. `levels` — cumulative experience of levels 1..10
# (level 1 right on choosing): ~3 months of active play to the top.

COACH_SPECS: dict[str, tuple[str, str, str]] = {
    "motivator": ("Мотиватор", "🔥", "Победы заряжают команду сильнее."),
    "psychologist": ("Психолог", "🧠", "Поражения бьют по морали слабее."),
    "orator": ("Оратор", "🎤", "Речи и разговоры в перерыве: не вредят и работают сильнее, сильнее «Сплочение»."),
    "analyst": ("Аналитик", "📋", "Твои игроки меньше боятся неудобных соперников в дуэлях."),
}
# «Оратор» levels 1..10: (perk, text).
ORATOR_PERKS: tuple[tuple[str, str], ...] = (
    ("talk_safe", "разговор в перерыве не вредит"),
    ("speech_safe", "речь перед матчем не вредит"),
    ("talk_plus", "удачный разговор в перерыве +1"),
    ("team_building", "«Сплочение» +2 морали"),
    ("speech_plus", "удачная речь перед матчем +1"),
    ("team_building", "«Сплочение» +4 морали"),
    ("team_building", "«Сплочение» +6 морали"),
    ("talk_plus", "удачный разговор в перерыве +2"),
    ("team_building", "«Сплочение» +8 морали"),
    ("speech_plus", "удачная речь перед матчем +2"),
)
COACH_TUNING: dict[str, Any] = {
    "levels": [0, 15, 35, 60, 95, 140, 195, 265, 350, 450],
    "xp_win": 3, "xp_draw": 2, "xp_loss": 1,
    # Final place of a season: 1st, 2nd-3rd, the rest.
    "xp_season": [15, 10, 5],
    "switch_days": 30,
    # Per level: «Мотиватор» % more morale from a win, «Психолог» % softer
    # losses, «Аналитик» % less fear in duels.
    "motivator_pct": 10, "psychologist_pct": 6, "analyst_pct": 10,
}


def coach_tuning_of(career_tuning: Optional[dict]) -> dict:
    return {**COACH_TUNING, **((career_tuning or {}).get("coach") or {})}


def _coach_data(profile: Any) -> dict:
    data = (getattr(profile, "coach_skills", None) or {}) if profile is not None else {}
    xp = data.get("xp")
    return {"spec": data.get("spec") if data.get("spec") in COACH_SPECS else None,
            "xp": {c: int(v) for c, v in xp.items() if c in COACH_SPECS} if isinstance(xp, dict) else {},
            "changed_at": data.get("changed_at")}


def level_for(xp: int, tuning: dict) -> int:
    return sum(1 for need in tuning["levels"] if xp >= need)


def skills_of(profile: Any, tuning: Optional[dict] = None) -> dict[str, int]:
    """{spec: level} of the chosen specialization only (others are 0)."""
    tuning = tuning or COACH_TUNING
    data = _coach_data(profile)
    out = {code: 0 for code in COACH_SPECS}
    if data["spec"]:
        out[data["spec"]] = level_for(data["xp"].get(data["spec"], 0), tuning)
    return out


def orator_perk(level: int, perk: str) -> int:
    """How strong an «Оратор» perk is at this level (0 = not yet)."""
    return sum(1 for code, _ in ORATOR_PERKS[:level] if code == perk)


def level_texts(code: str, tuning: dict) -> list[str]:
    n = len(tuning["levels"])
    if code == "orator":
        return [text for _, text in ORATOR_PERKS[:n]]
    if code == "motivator":
        return [f"мораль за победу +{tuning['motivator_pct'] * i}%" for i in range(1, n + 1)]
    if code == "psychologist":
        return [f"поражение бьёт по морали на {tuning['psychologist_pct'] * i}% слабее" for i in range(1, n + 1)]
    return [f"страх в дуэлях слабее на {min(100, tuning['analyst_pct'] * i)}%" for i in range(1, n + 1)]


def _switch_at(data: dict, tuning: dict) -> Optional[datetime]:
    if not data["changed_at"]:
        return None
    return datetime.fromisoformat(data["changed_at"]) + timedelta(days=int(tuning["switch_days"]))


def coach_view(profile: Any, tuning: dict, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    data = _coach_data(profile)
    levels = tuning["levels"]
    switch_at = _switch_at(data, tuning)
    specs = []
    for code, (label, icon, about) in COACH_SPECS.items():
        xp = data["xp"].get(code, 0)
        level = level_for(xp, tuning) if (code == data["spec"] or xp) else 0
        specs.append({
            "code": code, "label": label, "icon": icon, "about": about, "xp": xp, "level": level,
            "level_xp": levels[level - 1] if level else 0,
            "next_xp": levels[level] if level < len(levels) else None,
            "levels": level_texts(code, tuning),
        })
    return {
        "spec": data["spec"], "specs": specs, "max_level": len(levels),
        "switch_at": switch_at.isoformat() if switch_at and switch_at > now else None,
        "switch_days": int(tuning["switch_days"]),
        "xp_win": tuning["xp_win"], "xp_draw": tuning["xp_draw"], "xp_loss": tuning["xp_loss"],
        "xp_season": list(tuning["xp_season"]),
    }


def _gain(profile: Any, gain: int) -> int:
    data = _coach_data(profile)
    if not data["spec"] or gain <= 0:
        return 0
    raw = dict(getattr(profile, "coach_skills", None) or {})
    raw["xp"] = {**data["xp"], data["spec"]: data["xp"].get(data["spec"], 0) + gain}
    profile.coach_skills = raw
    return gain


def add_xp(profile: Any, own: int, opp: int, tuning: dict) -> int:
    """Experience of a league match into the chosen specialization."""
    return _gain(profile, tuning["xp_win"] if own > opp else tuning["xp_draw"] if own == opp else tuning["xp_loss"])


def add_season_xp(profile: Any, place: int, tuning: dict) -> int:
    first, podium, rest = (list(tuning["xp_season"]) + [0, 0, 0])[:3]
    return _gain(profile, first if place == 1 else podium if place <= 3 else rest)


def choose(profile: Any, code: str, tuning: dict, now: Optional[datetime] = None) -> None:
    """Picks (or switches) the specialization; raises ValueError."""
    now = now or datetime.now(timezone.utc)
    if code not in COACH_SPECS:
        raise ValueError("Неизвестная специализация")
    data = _coach_data(profile)
    if data["spec"] == code:
        raise ValueError("Эта специализация уже выбрана")
    switch_at = _switch_at(data, tuning)
    if data["spec"] and switch_at and switch_at > now:
        raise ValueError(f"Сменить специализацию можно с {switch_at.astimezone(timezone.utc):%d.%m}")
    raw = dict(getattr(profile, "coach_skills", None) or {})
    raw.pop("skills", None)
    raw.update({"spec": code, "xp": data["xp"], "changed_at": now.isoformat()})
    profile.coach_skills = raw
