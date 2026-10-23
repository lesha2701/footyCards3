"""«Легенда ринга» — the boxer of the day.

One legend per local day (rotating through LEGENDS by date): a strong bot
with one recognisable habit (mordoboi_engine.STYLE_WEIGHTS / "copy" /
"counter"). The habit is told to the player up front — reading it and
punishing it is the whole game. A win pays GameConfig.mordoboi_legend_reward
once per day; legend bouts never touch rating, limits or regular rewards.
"""
from datetime import date

# code, name, nickname, style, position, tagline, look (gloves, shorts, entrance)
LEGENDS = (
    ("garcia", "Мигель Гарсия", "Хукмейстер", "hooker", "ST",
     "Бьёт хуком почти всегда — уклон его наказывает", ("fire", "red", "fireworks")),
    ("bergman", "Ларс Бергман", "Стена", "wall", "CB",
     "Уходит в глухой блок — апперкот пробивает его защиту", ("steel", "black", "smoke")),
    ("moth", "Луи Папийон", "Мотылёк", "moth", "RW",
     "Порхает и уклоняется — ловит его только апперкот", ("ice", "white", "spotlight")),
    ("gatling", "Марко Ризи", "Пулемёт", "machinegun", "LW",
     "Сыплет джебами без остановки — хук проходит сквозь них", ("neon", "blue", "lightning")),
    ("hammer", "Иван Кувалдин", "Кувалда", "hammer", "CDM",
     "Ждёт момента для апперкота — быстрый джеб его опережает", ("gold", "red", "fireworks")),
    ("mirror", "Тео Зеркальный", "Зеркало", "copy", "CAM",
     "Повторяет твой прошлый удар — подумай, чем его встретить", ("ice", "white", "smoke")),
    ("fox", "Франко Лисицын", "Хитрец", "counter", "CM",
     "Отвечает контрой на твой прошлый удар — не повторяйся", ("toxic", "green", "lightning")),
)


def legend_for(day: date) -> dict:
    code, name, nickname, style, position, tagline, look = LEGENDS[day.toordinal() % len(LEGENDS)]
    gloves, shorts, entrance = look
    return {
        "code": code, "name": name, "nickname": nickname, "style": style, "position": position,
        "tagline": tagline, "look": {"gloves": gloves, "shorts": shorts, "entrance": entrance, "nickname": nickname},
    }
