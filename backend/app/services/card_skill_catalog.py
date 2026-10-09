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
    # Plain-language tail for "+N% ..." in the Mini App, and which match
    # engines the skill acts in ("arena" = Card Arena, "tournament" = player
    # tournaments) — shown so a player can see e.g. that Dribbler does
    # nothing in a Card Arena lineup.
    bonus_phrase: str = ""
    engines: tuple[str, ...] = ("arena", "tournament")
    engine_supported: bool = True
    unavailable_reason: str | None = None
    remaining_work: tuple[str, ...] = field(default_factory=tuple)


SKILL_DEFINITIONS: dict[str, SkillDefinition] = {
    "sniper": SkillDefinition(
        code="sniper", name="Снайпер", icon="🎯",
        bonus_phrase="к точности удара",
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
        bonus_phrase="к шансу обыграть защитника", engines=("tournament",),
        positions=(*_WINGERS, Position.ST, Position.CAM),
        effect="Повышает вероятность успешного обыгрыша в единоборстве «атакующий против защитника»",
        applies_in=(
            "Турниры игроков: дуэль на прорыв (этап 1 атаки и контратаки), когда этот игрок — атакующий дуэлянт",
        ),
        not_affected="Не влияет на удар, передачу и Card Arena (там нет отдельного события обыгрыша)",
    ),
    "playmaker": SkillDefinition(
        code="playmaker", name="Диспетчер", icon="🧭",
        bonus_phrase="к точности передачи под удар",
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
        bonus_phrase="к шансу перехватить передачу", engines=("tournament",),
        positions=(Position.CB, Position.LB, Position.RB, Position.CDM),
        effect="Повышает вероятность прервать передачу соперника, когда этот игрок — выбранный защитник эпизода",
        applies_in=(
            "Турниры игроков: передача соперника под удар, когда этот игрок защищается в эпизоде",
        ),
        not_affected="Не влияет на подкаты, блоки и Card Arena (там защитник соперника не персонифицирован)",
    ),
    "aerial_master": SkillDefinition(
        code="aerial_master", name="Воздушный король", icon="🦅",
        bonus_phrase="к шансу выиграть борьбу в воздухе",
        positions=(Position.CB, Position.ST),
        effect="Повышает вероятность выиграть верховое единоборство на навесе",
        applies_in=(
            "Card Arena: действие «Блок» твоего ЦЗ при навесе на дальнюю штангу и в свалке после углового",
            "Турниры игроков: дуэль за навес при атаке с фланга с ударом в штрафной — ЦФ (или ЦЗ в атаке) "
            "против ЦЗ соперника",
        ),
        not_affected="Не даёт бонуса к самому удару головой после выигранной дуэли",
    ),
    "crosser": SkillDefinition(
        code="crosser", name="Мастер навесов", icon="📐",
        bonus_phrase="к шансу опасного навеса",
        positions=(Position.LW, Position.RW, Position.LM, Position.RM, Position.LB, Position.RB),
        effect="Повышает долю опасных моментов (высокого качества) в атаках через фланг",
        applies_in=(
            "Card Arena: действие «Пас» этого игрока в эпизоде на фланге (навес / прострел)",
            "Турниры игроков: качество момента в атаке через фланг, когда этот игрок — один из атакующих дуэлянтов",
        ),
        not_affected="Не влияет на сам удар и на атаки через центр",
    ),
    "last_line": SkillDefinition(
        code="last_line", name="Последний рубеж", icon="🧱",
        bonus_phrase="к шансу остановить прорыв",
        positions=(Position.CB,),
        effect="Повышает шанс остановить опасный прорыв, когда этот игрок — последний защитник",
        applies_in=(
            "Card Arena: «Отбор» и «Блок» в эпизодах прорыва (контратака, выход к воротам, прорыв в штрафную)",
            "Турниры игроков: дуэль на контратаке соперника, когда этот игрок прикрывает",
        ),
        not_affected="Не влияет на обычные позиционные атаки и на сейв",
    ),
    "one_on_one": SkillDefinition(
        code="one_on_one", name="Один на один", icon="🥅",
        bonus_phrase="к шансу сейва один на один",
        positions=(Position.GK,),
        effect="Повышает вероятность сейва, когда соперник выходит один на один",
        applies_in=(
            "Card Arena: сейв в эпизодах «один на один» и «вратарь вышел из ворот» (свой вратарь и вратарь соперника)",
            "Турниры игроков: сейв в моментах наивысшего качества (выход один на один)",
        ),
        not_affected="Не влияет на сейвы в остальных эпизодах — для них есть «Реакция»",
    ),
    "reflexes": SkillDefinition(
        code="reflexes", name="Реакция", icon="🧤",
        bonus_phrase="к шансу сейва",
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

# Display / seed order: the v1 six first, then skills added later — matches the
# sort_order values the migrations seeded on existing databases.
SKILL_ORDER: tuple[str, ...] = (
    "sniper", "dribbler", "playmaker", "interceptor", "aerial_master", "reflexes",
    "crosser", "last_line", "one_on_one",
)
assert set(SKILL_ORDER) == set(SKILL_DEFINITIONS)


def get_definition(code: str) -> SkillDefinition | None:
    return SKILL_DEFINITIONS.get(code)


def roman(level: int | None) -> str:
    return LEVEL_ROMAN.get(level or 0, "")
