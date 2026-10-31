"""«Контратака» catalogs: «Тактические комплекты» (gear) and the weekly bosses.

Gear: four slots, each piece boosts one stat by a small % set by its
rarity; two / four pieces of one set on a card add a set bonus. Effects
are deliberately small (a full legendary set is about +15–30% on one
stat) — gear helps, cards decide.
"""
import random
from datetime import date
from typing import Iterable

SLOTS = {
    "boots": ("Бутсы", "spd"),
    "shinguards": ("Щитки", "def"),
    "armband": ("Повязка", "atk"),
    "gloves": ("Перчатки", "max_hp"),
}
RARITY_PCT = {"common": 2, "rare": 3, "epic": 5, "legendary": 7}
RARITY_LABELS = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "legendary": "Легендарная"}
# Drop weights for a random piece (chests, battle drops).
RARITY_WEIGHTS = (("common", 50), ("rare", 32), ("epic", 14), ("legendary", 4))

# set -> (name, 2-piece bonus {stat: pct}, 4-piece bonus {stat: pct} or a
# special engine flag, description)
SETS: dict[str, tuple[str, dict, dict, str]] = {
    "speed": ("Скоростной", {"spd": 5}, {"spd": 12}, "2: +5% скорости · 4: +12% скорости"),
    "sniper": ("Снайперский", {"crit": 5}, {"crit_dmg": 20}, "2: +5% шанса крита · 4: +20% урона крита"),
    "medic": ("Медицинский", {"max_hp": 8}, {"medic": 1}, "2: +8% HP · 4: лечит себя на 5% в начале хода"),
    "captain": ("Капитанский", {"def": 5}, {"captain": 1}, "2: +5% защиты · 4: +4% атаки всему отряду"),
}


def gear_bonus(pieces: Iterable[dict]) -> dict:
    """{"pct": {stat: %}, "sets4": [flags]} for the pieces worn by one card
    (each piece: {"slot", "set_code", "rarity"})."""
    pct: dict[str, int] = {}
    counts: dict[str, int] = {}
    for p in pieces:
        stat = SLOTS[p["slot"]][1]
        pct[stat] = pct.get(stat, 0) + RARITY_PCT.get(p["rarity"], 0)
        counts[p["set_code"]] = counts.get(p["set_code"], 0) + 1
    flags = []
    for code, n in counts.items():
        _, two, four, _ = SETS[code]
        for stat, value in two.items():
            if n >= 2:
                pct[stat] = pct.get(stat, 0) + value
        if n >= 4:
            for stat, value in four.items():
                if stat in ("medic", "captain"):
                    flags.append(stat)
                else:
                    pct[stat] = pct.get(stat, 0) + value
    return {"pct": pct, "sets4": flags}


def roll_piece(r: random.Random) -> dict:
    roll = r.randint(1, sum(w for _, w in RARITY_WEIGHTS))
    rarity = RARITY_WEIGHTS[-1][0]
    for name, weight in RARITY_WEIGHTS:
        roll -= weight
        if roll <= 0:
            rarity = name
            break
    return {"slot": r.choice(list(SLOTS)), "set_code": r.choice(list(SETS)), "rarity": rarity}


# ---------------------------------------------------------------------------
# Weekly bosses (rotate by ISO week)
# ---------------------------------------------------------------------------

# code, name, tagline, atk, def, spd, abilities
BOSSES = (
    ("tyrant", "Тренер-тиран", "Разносит весь отряд и раздаёт красные — держи щиты и лечение",
     260, 220, 105, ("boss_slam", "boss_card")),
    ("wall", "Вратарь-стена", "Огромная защита — «Прессинг» и «жёлтая» её пробивают",
     200, 520, 90, ("boss_card", "boss_slam")),
    ("referee", "Продажный судья", "Карточки и травмы — нужна быстрая «Медбригада»",
     220, 260, 120, ("boss_card", "boss_chant")),
    ("ultras", "Фанатский сектор", "Кричалки травмируют всех — бей быстро, пока стоишь",
     240, 240, 110, ("boss_chant", "boss_slam")),
)


# «🎃 Ночь тыкв» (halloween_service.kontra_boss): replaces the weekly boss
# while the event runs. Same shape as boss_for().
HALLOWEEN_BOSS = {
    "code": "headless", "name": "Безголовый вратарь",
    "tagline": "Ловит мячи без головы и пугает защитников — выстой до свистка, тыквы ×2",
    "atk": 250, "def": 300, "spd": 115, "abilities": ("boss_chant", "boss_slam"),
}


def boss_for(day: date) -> dict:
    week = day.isocalendar()
    code, name, tagline, atk, defense, spd, abilities = BOSSES[(week[0] * 53 + week[1]) % len(BOSSES)]
    return {"code": code, "name": name, "tagline": tagline, "atk": atk, "def": defense, "spd": spd,
            "abilities": list(abilities)}


def week_start(day: date) -> date:
    return date.fromordinal(day.toordinal() - day.weekday())
