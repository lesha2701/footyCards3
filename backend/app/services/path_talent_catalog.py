"""Server catalog of «Начало пути» talents: what each talent DOES and where
the match engines model it. Admin-tunable state (on/off, strength per level,
order) lives in the `path_talents` table; the numbers below are only the
defaults a fresh row is seeded with and the fallback for a missing key.

A talent is a SITUATIONAL bonus to the card's match rating (never the
rating shown on the card): it is frozen into the match state at kickoff and
— for the conditions that depend on the match itself (minute, score, a
one-on-one) — applied to the card only in the moments where the condition
holds. All talents of one card together never add more than
GameConfig.path_talent_cap in one match, and the match rating stays <= 99.

Modes: "arena" (Card Arena), "ptour" (player tournaments), "career"
(«Карьера тренера»), "tactico", "stratego". A mode missing from `modes` means
the talent does NOTHING there (the UI says «не действует») — no stand-in
effects.
"""
from dataclasses import dataclass, field

from app.models.enums import Position

# Kinds of application, used by path_talent_effects.
STATIC = "static"      # decided once at kickoff, the whole match
DYNAMIC = "dynamic"    # applied only in the moments where the condition holds


@dataclass(frozen=True)
class TalentDefinition:
    code: str
    name: str
    emoji: str
    kind: str
    # Short rule, one line per level ({…} = level_values keys).
    summary: str
    level_text: tuple[str, str]
    # param -> (level I default, level II default)
    params: dict[str, tuple[int, int]]
    # mode -> how it works there (shown in the UI); missing = «не действует».
    modes: dict[str, str] = field(default_factory=dict)
    # Positions the admin may give it to (None = everyone).
    positions: frozenset | None = None


DEFENDERS = frozenset({Position.GK, Position.CB, Position.LB, Position.RB, Position.LWB, Position.RWB})

TALENTS: dict[str, TalentDefinition] = {t.code: t for t in (
    TalentDefinition(
        code="big_matches", name="Большие матчи", emoji="🔥", kind=STATIC,
        summary="Раскрывается против сильных: соперник сильнее хотя бы на {threshold_pct}%.",
        level_text=("+{bonus} к рейтингу в матче против более сильного соперника",
                    "+{bonus} к рейтингу в матче против более сильного соперника"),
        params={"bonus": (3, 5), "threshold_pct": (5, 5)},
        modes={
            "arena": "Сила соперника на старте матча больше силы твоего состава",
            "ptour": "Средний рейтинг состава соперника больше твоего",
        },
    ),
    TalentDefinition(
        code="second_wind", name="Второе дыхание", emoji="💨", kind=DYNAMIC,
        summary="Сильнее во второй половине второго тайма.",
        level_text=("+{bonus} к рейтингу с {from_minute}-й минуты; в карьере усталость за матч −{fatigue_cut_pct}%",
                    "+{bonus} к рейтингу с {from_minute}-й минуты; в карьере усталость за матч −{fatigue_cut_pct}%"),
        params={"bonus": (3, 5), "from_minute": (60, 60), "fatigue_cut_pct": (25, 40)},
        modes={
            "arena": "Моменты с его участием с указанной минуты",
            "ptour": "Моменты с его участием с указанной минуты",
            "career": "Набирает меньше усталости за матч (рейтинг в карьере не меняет)",
        },
    ),
    TalentDefinition(
        code="universal", name="Универсал", emoji="🔄", kind=STATIC,
        summary="Играет на соседней позиции как на своей.",
        level_text=("Соседняя позиция — без штрафа за позицию",
                    "Соседняя позиция — без штрафа, химия не обнуляется и +{bonus} к рейтингу"),
        params={"bonus": (0, 2)},
        modes={
            "arena": "Слот соседней позиции в составе Арены",
            "ptour": "Слот соседней позиции в составе турнира",
        },
    ),
    TalentDefinition(
        code="own_guy", name="Свой парень", emoji="🤝", kind=STATIC,
        summary="С ним сыгрываются все: связи химии с соседями не ниже заданной.",
        level_text=("Связи химии с ним — минимум средние",
                    "Связи химии с ним — минимум сильные, +{extra_points} очко его химии"),
        params={"link_floor": (1, 2), "extra_points": (0, 1)},
        modes={
            "arena": "Только при включённой химии",
            "ptour": "Только если турнир играется с химией",
        },
    ),
    TalentDefinition(
        code="academy", name="Воспитанник", emoji="🧑‍🎓", kind=STATIC,
        summary="Играет за своих: тренер из его страны и/или стадион его клуба.",
        level_text=("+{coach_bonus} с тренером-земляком, +{stadium_bonus} на стадионе своего клуба",
                    "+{coach_bonus} с тренером-земляком, +{stadium_bonus} на стадионе своего клуба"),
        params={"coach_bonus": (2, 4), "stadium_bonus": (2, 4)},
        modes={
            "arena": "Тренер и стадион из состава Арены",
            "ptour": "Тренер — всегда, стадион — только в домашнем матче",
        },
    ),
    TalentDefinition(
        code="hunger", name="Голод", emoji="📈", kind=STATIC,
        summary="Чем больше матчей подряд в составе, тем сильнее.",
        level_text=("+{per_match} за каждый матч подряд в составе, максимум +{max}; пропуск — сброс",
                    "+{per_match} за каждый матч подряд в составе, максимум +{max}; пропуск — серия вдвое"),
        params={"per_match": (1, 1), "max": (3, 6), "keep_on_miss_pct": (0, 50)},
        modes={"arena": "Серия считается по матчам Card Arena"},
    ),
    TalentDefinition(
        code="fighter", name="Боец", emoji="💪", kind=DYNAMIC,
        summary="Не сдаётся: сильнее, когда команда проигрывает.",
        level_text=("+{bonus} к рейтингу, пока команда уступает в счёте",
                    "+{bonus} к рейтингу, пока команда уступает в счёте"),
        params={"bonus": (3, 5)},
        modes={
            "arena": "Моменты с его участием при отставании в счёте",
            "ptour": "Моменты с его участием при отставании в счёте",
        },
    ),
    TalentDefinition(
        code="composure", name="Хладнокровие", emoji="🧊", kind=DYNAMIC,
        summary="Не дрожит в решающий момент: выходы один на один и пенальти.",
        level_text=("+{bonus} к рейтингу в выходах один на один и пенальти",
                    "+{bonus} к рейтингу в выходах один на один и пенальти"),
        params={"bonus": (4, 7)},
        modes={
            "arena": "Удар в эпизоде «один на один»; вратарь — сейв один на один и пенальти",
            "ptour": "Удар в моменте наивысшего качества; вратарь — сейв в нём и на пенальти",
        },
    ),
    TalentDefinition(
        code="hold_lead", name="Держать счёт", emoji="🧱", kind=DYNAMIC,
        summary="Защитник/вратарь, который не отдаёт победу в концовке.",
        level_text=("+{bonus} к рейтингу при ведении в счёте с {from_minute}-й минуты",
                    "+{bonus} к рейтингу при ведении в счёте с {from_minute}-й минуты"),
        params={"bonus": (3, 5), "from_minute": (75, 75)},
        modes={
            "arena": "Его отбор/блок и сейвы вратаря при ведении в концовке",
            "ptour": "Его оборона и сейвы вратаря при ведении в концовке",
        },
        positions=DEFENDERS,
    ),
    TalentDefinition(
        code="captain", name="Капитан", emoji="🎖️", kind=STATIC,
        summary="Ведёт за собой: соседи по схеме играют сильнее.",
        level_text=("+{aura} к рейтингу каждому соседу по схеме, всего не больше +{aura_cap} на команду",
                    "+{aura} к рейтингу каждому соседу по схеме, всего не больше +{aura_cap} на команду"),
        params={"aura": (1, 2), "aura_cap": (4, 6)},
        modes={
            "arena": "Соседи по связям схемы 4-3-3",
            "ptour": "Соседи по связям схемы турнирного состава",
        },
    ),
)}

MODE_LABELS = {
    "arena": "Card Arena", "ptour": "Турнир игроков", "career": "Карьера тренера",
    "tactico": "Тактико", "stratego": "Стратего",
}

# «Универсал»: positions that count as a neighbour of each position. Wing-
# backs and full-backs are already each other's ideal position
# (lineup_service.POSITION_EQUIVALENTS).
ADJACENT_POSITIONS: dict[Position, frozenset] = {
    Position.GK: frozenset(),
    Position.CB: frozenset({Position.CDM, Position.LB, Position.RB}),
    Position.LB: frozenset({Position.CB, Position.LM, Position.LWB}),
    Position.RB: frozenset({Position.CB, Position.RM, Position.RWB}),
    Position.LWB: frozenset({Position.LB, Position.LM}),
    Position.RWB: frozenset({Position.RB, Position.RM}),
    Position.CDM: frozenset({Position.CB, Position.CM}),
    Position.CM: frozenset({Position.CDM, Position.CAM, Position.LM, Position.RM}),
    Position.CAM: frozenset({Position.CM, Position.ST, Position.LW, Position.RW}),
    Position.LM: frozenset({Position.LW, Position.LB, Position.CM, Position.LWB}),
    Position.RM: frozenset({Position.RW, Position.RB, Position.CM, Position.RWB}),
    Position.LW: frozenset({Position.LM, Position.ST, Position.CAM}),
    Position.RW: frozenset({Position.RM, Position.ST, Position.CAM}),
    Position.ST: frozenset({Position.CAM, Position.LW, Position.RW}),
}


def roman(level: int) -> str:
    return {1: "I", 2: "II"}.get(level, str(level))


def is_adjacent(position, slot_position) -> bool:
    return slot_position in ADJACENT_POSITIONS.get(position, frozenset())


def default_level_values() -> dict:
    return {
        code: {str(lvl): {k: v[lvl - 1] for k, v in t.params.items()} for lvl in (1, 2)}
        for code, t in TALENTS.items()
    }


def values_for(code: str, level: int, stored: dict | None) -> dict:
    """Catalog defaults overlaid with the admin's stored numbers."""
    definition = TALENTS[code]
    out = {k: v[level - 1] for k, v in definition.params.items()}
    for k, v in ((stored or {}).get(str(level)) or {}).items():
        if k in out:
            out[k] = int(v)
    return out


def describe_level(code: str, level: int, values: dict) -> str:
    return TALENTS[code].level_text[level - 1].format(**values)
