"""Fixed, server-side catalog of card skills (v1).

This module is the single source of truth for what each skill DOES, which
match-engine roll it touches, and the widest set of positions (by the real
`Position` enum codes, never by name) it can ever fit. Admins can narrow the
positions and close acquisition (card_skills table) and tune bonus values and
prices (GameConfig), but can never widen a skill past what is declared here
or switch on a skill the engine does not model (`engine_supported=False`).
"""
from dataclasses import dataclass, field

from app.models.enums import Position

MAX_SKILL_LEVEL = 3
LEVEL_ROMAN = {1: "I", 2: "II", 3: "III"}

_WINGERS = (Position.LW, Position.RW, Position.LM, Position.RM)


@dataclass(frozen=True)
class SkillDefinition:
    code: str
    name: str
    icon: str
    # Widest compatible set — card_skill_service intersects it with the admin subset.
    positions: tuple[Position, ...]
    # Short, exact description of the one roll this skill changes.
    effect: str
    # Where that roll actually exists today (shown to players as-is).
    applies_in: tuple[str, ...]
    # What the skill explicitly does NOT do (shown to players to avoid
    # implying a general strength boost).
    not_affected: str
    engine_supported: bool = True
    unavailable_reason: str | None = None
    remaining_work: tuple[str, ...] = field(default_factory=tuple)


SKILL_DEFINITIONS: dict[str, SkillDefinition] = {
    "sniper": SkillDefinition(
        code="sniper", name="Снайпер", icon="🎯",
        positions=(Position.ST, *_WINGERS, Position.CAM),
        effect="Снижает вероятность промаха, когда бьёт этот игрок",
        applies_in=(
            "Card Arena: твой удар («Бить») и удар после твоей передачи, если бьёт этот игрок",
            "Турниры игроков: удары, удары после передачи и выходы один на один этого игрока",
        ),
        not_affected="Не повышает шанс создать момент и не мешает блоку/сейву соперника",
    ),
    "dribbler": SkillDefinition(
        code="dribbler", name="Дриблёр", icon="🌀",
        positions=(*_WINGERS, Position.ST, Position.CAM),
        effect="Повышает вероятность успешного обыгрыша в единоборстве «атакующий против защитника»",
        applies_in=(
            "Турниры игроков: дуэль на прорыв (этап 1 атаки и контратаки), когда этот игрок — атакующий дуэлянт",
        ),
        not_affected="Не влияет на удар, передачу и Card Arena (там нет отдельного события обыгрыша)",
    ),
    "playmaker": SkillDefinition(
        code="playmaker", name="Диспетчер", icon="🧭",
        positions=(Position.CM, Position.CAM, Position.CDM),
        effect="Снижает вероятность неудачной передачи этого игрока, открывающей момент партнёру",
        applies_in=(
            "Card Arena: действие «Пас», если пасует этот игрок",
            "Турниры игроков: передача под удар партнёру, если пасует этот игрок",
        ),
        not_affected="Не усиливает последующий удар партнёра",
    ),
    "interceptor": SkillDefinition(
        code="interceptor", name="Перехватчик", icon="🛡️",
        positions=(Position.CB, Position.LB, Position.RB, Position.CDM),
        effect="Повышает вероятность прервать передачу соперника, когда этот игрок — выбранный защитник эпизода",
        applies_in=(
            "Турниры игроков: передача соперника под удар, когда этот игрок защищается в эпизоде",
        ),
        not_affected="Не влияет на подкаты, блоки и Card Arena (там защитник соперника не персонифицирован)",
    ),
    "aerial_master": SkillDefinition(
        code="aerial_master", name="Воздушный король", icon="🦅",
        positions=(Position.CB, Position.ST),
        effect="Повышает вероятность выиграть верховое единоборство на навесе",
        applies_in=(
            "Card Arena: действие «Блок» твоего ЦЗ при навесе на дальнюю штангу и в свалке после углового",
            "Турниры игроков: дуэль за навес при атаке с фланга с ударом в штрафной — ЦФ (или ЦЗ в атаке) "
            "против ЦЗ соперника",
        ),
        not_affected="Не даёт бонуса к самому удару головой после выигранной дуэли",
    ),
    "reflexes": SkillDefinition(
        code="reflexes", name="Реакция", icon="🧤",
        positions=(Position.GK,),
        effect="Повышает вероятность сейва вратаря",
        applies_in=(
            "Card Arena: сейвы твоего вратаря (и вратаря соперника, если у его карточки есть навык), включая пенальти",
            "Турниры игроков: бросок сейва команды этого вратаря, включая пенальти",
        ),
        not_affected=(
            "Типов ударов в движке нет — бонус добавляется к единому существующему броску сейва; "
            "в турнирах базовая сила сейва по-прежнему считается от рейтинга защитника эпизода"
        ),
    ),
}

SKILL_ORDER: tuple[str, ...] = tuple(SKILL_DEFINITIONS.keys())


def get_definition(code: str) -> SkillDefinition | None:
    return SKILL_DEFINITIONS.get(code)


def roman(level: int | None) -> str:
    return LEVEL_ROMAN.get(level or 0, "")
