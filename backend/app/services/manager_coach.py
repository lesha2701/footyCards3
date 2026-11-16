"""«Главный тренер» with a character: the head coach of «Персонал» runs the
match day himself — the formation and style of every league match, the
«Установка на матч», the substitutions — and asks the president for the
player his team lacks. Without a coach the president (and «Алиса», the
assistant) does it.

The character is rolled at random when the coach is hired and kept in the
office JSON (`office["coach"] = {"resident_id", "trait"}`); a coach hired
before characters existed gets one from his resident id. The president may
take the tactics back (`office["coach_auto"] = False`): the coach then only
advises and keeps the substitutions.

Pure rules here, no DB except `coach_of`.
"""
import random
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_club import ManagerClub
from app.services.arena_tactics import BEATS, STYLE_LABELS, STYLES, formation_label

LINES = ("GK", "DEF", "MID", "FWD")
LINE_NAMES = {"GK": "вратарь", "DEF": "защитник", "MID": "полузащитник", "FWD": "нападающий"}

# formation: a code, or "fit" (the one the squad fills best);
# style: a code, or "read" (the one that beats the opponent's);
# plan: a «Установка на матч» code, "read" (bus vs a stronger side, press vs
# a weaker one), or None; sub_shift: minutes added to the sub windows;
# subs: substitutions over the base; wants: the line he asks for, or "weak"
# (the weakest line of the XI).
TRAITS: dict[str, dict] = {
    "spaniard": {"name": "Испанец", "title": "Тики-така", "emoji": "🇪🇸",
                 "about": "Мяч у нас — значит, у них его нет. Короткий пас, терпение, поздние замены.",
                 "quote": "Мы будем владеть мячом, пока они не устанут бегать.",
                 "formation": "4-3-3", "style": "possession", "plan": None, "sub_shift": 10, "subs": 0, "wants": "MID"},
    "portuguese": {"name": "Португалец", "title": "Особенный", "emoji": "🇵🇹",
                   "about": "Читает соперника и бьёт по его слабому месту. С сильными — «автобус», со слабыми — прессинг.",
                   "quote": "Я не проигрываю. Я изучаю, как выиграть в следующий раз.",
                   "formation": "4-2-3-1", "style": "read", "plan": "read", "sub_shift": 0, "subs": 0, "wants": "weak"},
    "frenchman": {"name": "Француз", "title": "Эстет", "emoji": "🇫🇷",
                  "about": "Красивый футбол через ромб и десятку. Верит в воспитанников и меняет рано.",
                  "quote": "Победить мало. Надо, чтобы трибуны встали.",
                  "formation": "4-3-1-2", "style": "attacking", "plan": None, "sub_shift": -5, "subs": 0, "wants": "MID"},
    "englishman": {"name": "Англичанин", "title": "Старая школа", "emoji": "🎩",
                   "about": "4-4-2, навесы и прессинг каждую игру. Замены — только когда ноги уже не бегут.",
                   "quote": "Футбол — игра мужчин. Бежим девяносто минут.",
                   "formation": "4-4-2", "style": "attacking", "plan": "press", "sub_shift": 10, "subs": 0, "wants": "FWD"},
    "strategist": {"name": "Стратег", "title": "Шахматист", "emoji": "♟️",
                   "about": "Подбирает схему под свой состав, а стиль — под соперника. Ни одного лишнего риска.",
                   "quote": "Матч выигрывается до стартового свистка.",
                   "formation": "fit", "style": "read", "plan": None, "sub_shift": 0, "subs": 0, "wants": "weak"},
    "motivator": {"name": "Мотиватор", "title": "Огонь в раздевалке", "emoji": "🔥",
                  "about": "Заводит команду на каждый матч: высокий прессинг и лишняя замена, чтобы не сбавлять.",
                  "quote": "Выйдите и оставьте на поле всё!",
                  "formation": "4-3-3H", "style": "attacking", "plan": "press", "sub_shift": 0, "subs": 1, "wants": "weak"},
    "iron": {"name": "Железный", "title": "Дисциплина", "emoji": "🛡️",
             "about": "Сначала не пропустить. Плотный блок 4-1-4-1, «автобус» против сильных.",
             "quote": "Ноль в своих воротах — уже половина победы.",
             "formation": "4-1-4-1", "style": "defensive", "plan": "read", "sub_shift": 0, "subs": 0, "wants": "DEF"},
    "gambler": {"name": "Авантюрист", "title": "Всё или ничего", "emoji": "🎲",
                "about": "Три нападающих, атака всегда и ранние замены. Матчи с ним не бывают скучными.",
                "quote": "Пропустим три — забьём четыре.",
                "formation": "3-4-3", "style": "attacking", "plan": None, "sub_shift": -10, "subs": 1, "wants": "FWD"},
    "mentor": {"name": "Наставник", "title": "Отец команды", "emoji": "🌱",
               "about": "Бережёт игроков: ротация, когда соперник слабее, контратака и спокойные замены.",
               "quote": "Сначала люди, потом очки. Очки придут.",
               "formation": "fit", "style": "counter", "plan": "rotate", "sub_shift": 0, "subs": 0, "wants": "weak"},
    "pragmatist": {"name": "Прагматик", "title": "Результат любой ценой", "emoji": "📐",
                   "about": "Схема — под состав, стиль — от обороны, контратака против тех, кто владеет мячом.",
                   "quote": "Красиво пусть играют другие. Нам нужны три очка.",
                   "formation": "fit", "style": "counter", "plan": "read", "sub_shift": 5, "subs": 0, "wants": "weak"},
}
CODES = tuple(TRAITS)


def roll(rng: Optional[random.Random] = None) -> str:
    return (rng or random).choice(CODES)


def trait_for(club: Optional[ManagerClub], resident_id: int) -> str:
    """The stored character of this coach, or one from his id (hired before characters)."""
    stored = ((club.office if club else None) or {}).get("coach") or {}
    if stored.get("resident_id") == resident_id and stored.get("trait") in TRAITS:
        return stored["trait"]
    return CODES[resident_id % len(CODES)]


def auto(club: Optional[ManagerClub]) -> bool:
    """Does the coach set the tactics (default), or the president himself?"""
    return ((club.office if club else None) or {}).get("coach_auto", True) is not False


async def coach_of(db: AsyncSession, club: ManagerClub) -> Optional[dict]:
    """The hired head coach: {"trait", "resident_id", "name", "auto", **TRAITS[trait]}."""
    from app.models.town import TownResident
    from app.services import manager_staff as staff

    row = next((s for s in await staff.staff_of(db, club.id) if s.role == "coach"), None)
    if row is None:
        return None
    resident = await db.get(TownResident, row.resident_id)
    trait = trait_for(club, row.resident_id)
    return {**TRAITS[trait], "trait": trait, "resident_id": row.resident_id,
            "person": resident.name if resident else TRAITS[trait]["name"], "auto": auto(club), "rarity": row.rarity}


# --- match day ---------------------------------------------------------------------------

def formation_for(trait: str, roster: list[dict], fallback: str, formations: tuple[str, ...], fit) -> str:
    """His formation; "fit" = the one whose XI has the highest average
    (`fit(formation)` → the XI's average rating)."""
    t = TRAITS.get(trait) or {}
    want = t.get("formation")
    if want in formations:
        return want
    if want == "fit":
        return max(formations, key=lambda f: (fit(f), f == fallback, f))
    return fallback


def style_for(trait: str, fallback: str, opponent_style: Optional[str]) -> str:
    want = (TRAITS.get(trait) or {}).get("style")
    if want == "read":
        if opponent_style in BEATS:
            return next(s for s in STYLES if BEATS[s] == opponent_style)
        return fallback
    return want if want in STYLES else fallback


def plan_for(trait: str, own_rating: int, opponent_rating: int, plans: set[str]) -> tuple[Optional[str], str]:
    """(plan code or None, why)."""
    want = (TRAITS.get(trait) or {}).get("plan")
    gap = own_rating - opponent_rating
    if want == "read":
        if gap <= -3 and "bus" in plans:
            return "bus", f"соперник сильнее на {-gap} — закрываемся"
        if gap >= 3 and "press" in plans:
            return "press", f"мы сильнее на {gap} — давим с первых минут"
        return None, "силы равны — играем от схемы"
    if want == "rotate":
        if gap >= 3 and "rotate" in plans:
            return "rotate", "соперник слабее — даём отдых лидерам"
        return None, "матч важный — играют лучшие"
    if want in plans:
        return want, "так играет его команда"
    return None, ""


def sub_rules(trait: Optional[str], minutes: list[int], subs_max: int) -> tuple[list[int], int]:
    """His substitution windows and their number."""
    t = TRAITS.get(trait or "") or {}
    shift = int(t.get("sub_shift", 0))
    return [max(46, min(89, m + shift)) for m in minutes], max(0, subs_max + int(t.get("subs", 0)))


def request(trait: str, xi: list[dict], category) -> Optional[dict]:
    """The line he asks to strengthen: kids in the XI first, then his own
    line, then the weakest one. {"line", "text"} or None."""
    t = TRAITS.get(trait) or {}
    by_line: dict[str, list[dict]] = {line: [] for line in LINES}
    for p in xi:
        by_line[category(p)].append(p)
    kids = [line for line in LINES if any(p["kind"] == "kid" for p in by_line[line])]
    if kids:
        line = kids[0]
        return {"line": line, "text": f"Нужен {LINE_NAMES[line]}: в старте играет воспитанник"}
    want = t.get("wants")
    avg = {line: sum(p["rating"] for p in ps) / len(ps) for line, ps in by_line.items() if ps}
    if not avg:
        return None
    if want not in avg:
        want = min(avg, key=lambda line: (avg[line], line))
    return {"line": want, "text": f"Нужен {LINE_NAMES[want]} сильнее — {style_text(t)}"}


def style_text(t: dict) -> str:
    style = t.get("style")
    if style in STYLE_LABELS:
        return f"под стиль «{STYLE_LABELS[style]}»"
    return "чтобы схема заработала"


def out(coach: Optional[dict]) -> Optional[dict]:
    if not coach:
        return None
    formation = coach.get("formation")
    return {
        "trait": coach["trait"], "name": coach["person"], "nation": coach["name"], "title": coach["title"],
        "emoji": coach["emoji"], "about": coach["about"], "quote": coach["quote"], "auto": coach["auto"],
        "formation": formation_label(formation) if formation not in ("fit", None) else "под состав",
        "style": STYLE_LABELS.get(coach.get("style"), "под соперника" if coach.get("style") == "read" else ""),
    }
