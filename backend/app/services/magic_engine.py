"""«Мяч и Магия» — the pure, seeded rules engine: no database here.

A run is a short adventure: the player's hero walks a small map for a few
«days» (moves per day), picks up chests, mana wells, artifacts and
reinforcements, beats neutral camps and finally fights the rival hero (the
bot). Every fight is a turn-based battle of stacks on an 8×5 field: a stack
is one footballer's card turned into creatures of the hero's faction — the
card's rarity is the creature's tier, its number of copies the stack size.

Everything random goes through `rng(state)`, keyed by the run seed and a
counter kept in the state, so a replay of the same actions gives the same
run. `magic_service` owns the database, limits and rewards.
"""
import copy
import math
import random
from collections import deque
from typing import Optional


class EngineError(Exception):
    pass


# ---------------------------------------------------------------------------
# Catalog: factions, creatures, spells, artifacts
# ---------------------------------------------------------------------------

TIER_BY_RARITY = {"common": 1, "rare": 2, "epic": 3, "legendary": 4, "diamond": 5}
# Creatures per stack for one copy of the card; more copies grow it as √n.
BASE_COUNT = {1: 10, 2: 9, 3: 8, 4: 5, 5: 3}
TIER_STATS = {
    # hp, atk, def, dmg min, dmg max, speed
    1: (10, 4, 4, 1, 3, 4),
    2: (18, 7, 5, 3, 5, 4),
    3: (34, 10, 9, 6, 10, 5),
    4: (110, 17, 16, 18, 28, 6),
    5: (280, 27, 25, 40, 62, 7),
}

# code, name, tier, emoji, ranged, flying, ability, ability text, (hp, atk, def, speed) tweaks
UNITS: dict[str, dict] = {}


def _u(code, faction, tier, name, emoji, *, ranged=False, flying=False, ability=None, text="",
       hp=0, atk=0, defense=0, spd=0):
    base_hp, base_atk, base_def, dmin, dmax, base_spd = TIER_STATS[tier]
    UNITS[code] = {
        "code": code, "faction": faction, "tier": tier, "name": name, "emoji": emoji,
        "ranged": ranged, "flying": flying, "ability": ability, "ability_text": text,
        "hp": base_hp + hp, "atk": base_atk + atk, "def": base_def + defense,
        "dmin": dmin, "dmax": dmax, "spd": base_spd + spd,
    }


_u("dawn_banner", "dawn", 1, "Стенка", "🛡️", ability="shield", text="Стенка: −50% урона от стрел и магии", defense=1)
_u("dawn_spear", "dawn", 2, "Бомбардиры", "🗡️", ranged=True)
_u("dawn_priest", "dawn", 3, "Врачи сборной", "✨", ranged=True, ability="light",
   text="Свет: после хода лечит самый раненый отряд")
_u("dawn_guard", "dawn", 4, "Крылатые вратари", "🪽", flying=True, ability="guard",
   text="Два сейва: отвечают на два удара за раунд")
_u("dawn_phoenix", "dawn", 5, "Феникс камбэка", "🌅", flying=True, ability="rebirth",
   text="Возрождается один раз за бой с половиной сил")

_u("ash_bones", "ash", 1, "Костяные ультрас", "💀", ability="undead", text="Нежить: после боя треть павших встаёт")
_u("ash_imp", "ash", 2, "Бесы-пиротехники", "😈", ranged=True, atk=1, defense=-1)
_u("ash_witch", "ash", 3, "Ведьмы-тренеры", "🧙", ranged=True, ability="curse",
   text="Сглаз: цель бьёт на 30% слабее 2 раунда")
_u("ash_golem", "ash", 4, "Пепельный автобус", "🚌", ability="stone", text="Автобус у ворот: −25% любого урона",
   spd=-2, hp=20)
_u("ash_dragon", "ash", 5, "Дракон-бомбардир", "🐉", flying=True, ability="breath",
   text="Огненное дыхание: задевает отряд за целью")

# Position variants: a card's position picks one of two creatures of its tier.
_u("dawn_squire", "dawn", 1, "Дуплетисты", "⚔️", ability="double", text="Двойной удар: бьют дважды", atk=-1)
_u("dawn_sister", "dawn", 2, "Волшебная губка", "🕊️", ability="mend",
   text="Милосердие: после хода лечат соседних союзников", defense=1, atk=-1)
_u("dawn_knight", "dawn", 3, "Рыцари прессинга", "🐎", ability="charge", text="Натиск: враг не отвечает на удар", spd=1)
_u("ash_hound", "ash", 1, "Гончие прессинга", "🐺", ability="charge", text="Натиск: враг не отвечает на удар", spd=2, hp=-2)
_u("ash_leech", "ash", 2, "Вампиры затяжки", "🦇", ability="drain", text="Кровопийство: лечатся на половину урона", flying=True)
_u("ash_butcher", "ash", 3, "Костоломы", "🦴", ability="cleave", text="Грубый подкат: задевает всех врагов рядом",
   spd=-1, hp=6)

_u("wild_thug", "wild", 1, "Дикие хулиганы", "👊")
_u("wild_sling", "wild", 2, "Мальчики-подавальщики", "🏹", ranged=True)
_u("wild_troll", "wild", 3, "Тролль-талисман", "👹", hp=10, spd=-1)
_u("wild_ogre", "wild", 4, "Стадионный огр", "🦍", hp=10)
_u("wild_crow", "wild", 2, "Вороньё с трибун", "🐦‍⬛", flying=True, spd=2, hp=-4)
_u("wild_bouncer", "wild", 2, "Стюарды-вышибалы", "🧱", ability="stone", text="Камень: −25% любого урона", defense=3, spd=-1)
_u("wild_crossbow", "wild", 3, "Снайперы штрафных", "🎯", ranged=True, hp=-6)
_u("wild_harpy", "wild", 3, "Гарпии-кричалки", "🦅", flying=True, ability="charge", text="Натиск: враг не отвечает на удар")

# Pack-only creatures (docs/magic-army.md): more kinds per tier, the wild get a tier V.
_u("dawn_archer", "dawn", 2, "Мастерицы навесов", "🏹", ranged=True, atk=1, hp=-2)
_u("ash_ghost", "ash", 2, "Призраки офсайда", "👻", flying=True, ability="shield",
   text="Бестелесные: −50% урона от стрел и магии", hp=-3)
_u("dawn_griffin", "dawn", 4, "Крылатые фланговые", "🌞", flying=True, ability="charge",
   text="Натиск: враг не отвечает на удар", spd=1, hp=-10)
_u("ash_wraith", "ash", 4, "Завершители карьер", "💀", ability="drain",
   text="Конец карьеры: лечатся на половину урона",
   spd=1, hp=-6)
_u("wild_wyvern", "wild", 5, "Королева вувузел", "🦋", flying=True, ability="breath",
   text="Гул вувузел: задевает отряд за целью", hp=-30)
_u("wild_giant", "wild", 4, "Великан с трибуны", "🗻", ability="cleave", text="Кусок трибуны: задевает всех врагов рядом",
   spd=-2, hp=40)

# «Гильдия Потерявших всё»: a neutral faction of bosses. They guard the far lairs of
# «Приключение» and never come in packs; Безликий is the adventure's final boss, alone.
# Levels II–IV (V is Безликий alone): a lair's power is split evenly between its stacks, so a
# low one comes as a crowd and a high one as a few heavy fighters.
_u("lost_father", "lost", 4, "Отчаянный отец", "⚰️", ability="grief",
   text="Нечего терять: чем больше павших в отряде, тем сильнее удар (до ×2)", hp=20)
_u("lost_hook", "lost", 4, "Мститель с крюком", "⛓️", ability="hook",
   text="Крюк возмездия: притягивает врага цепью и бьёт, враг не отвечает", spd=1)
_u("lost_bankrupt", "lost", 3, "Банкрот", "💸", ability="debt",
   text="Долговая яма: цель бьёт на 30% слабее 2 раунда", defense=2)
_u("lost_bench", "lost", 2, "Вечный запасной", "🪑", flying=True, ability="sub",
   text="Выход на замену: первый удар двойной", hp=-2, spd=1)
_u("lost_widow", "lost", 3, "Вдова трибун", "🕯️", ranged=True, ability="mourn",
   text="Плач трибун: раз за бой поднимает павший отряд союзников", hp=-6)
_u("lost_victor", "lost", 5, "Безликий", "🎭", flying=True, ability="hypno",
   text="Гипноз: твой отряд на 2 раунда переходит на его сторону", spd=2)
LOST_UNITS = ["lost_father", "lost_hook", "lost_bankrupt", "lost_bench", "lost_widow"]
BOSS = "lost_victor"
# The boss: his health in % of the player's starting army power, and each hit in ‰ of it
# (±20%). One figure against a whole army — he answers with hypnosis and his curse.
BOSS_HP_PCT = {"easy": 80, "normal": 120, "hard": 170}
BOSS_HIT_PERMILLE = 14
BOSS_ATK = 18

FACTIONS = {
    "dawn": {"code": "dawn", "name": "Орден Рассвета", "emoji": "☀️",
             "tagline": "Щиты, свет и крылья — держат строй и лечат своих",
             "units": ["dawn_banner", "dawn_spear", "dawn_priest", "dawn_guard", "dawn_phoenix"],
             "spells": ["bless", "wall", "sunstrike"]},
    "ash": {"code": "ash", "name": "Легион Пепла", "emoji": "🔥",
            "tagline": "Нежить, проклятия и огонь — давят числом и жгут",
            "units": ["ash_bones", "ash_imp", "ash_witch", "ash_golem", "ash_dragon"],
            "spells": ["curse", "raise", "firerain"]},
}
WILD_UNITS = ["wild_thug", "wild_sling", "wild_troll", "wild_ogre"]
FACTIONS_AND_WILD = ("dawn", "ash", "wild")

# ---------------------------------------------------------------------------
# Captains and the guard: levels and traits
# ---------------------------------------------------------------------------

# The guard: one unit per rarity of its footballer. Every rarity has the same power budget —
# a common guard is many light fighters, a legendary one a few heavy ones.
GUARD = "magic_guard"  # the rare one (and the base of the budget)
_u("magic_guard_common", "guard", 2, "Гвардия", "🛡", ability="shield",
   text="Сомкнутые щиты: −50% урона от стрел и магии")
_u(GUARD, "guard", 3, "Гвардия", "🛡", ability="charge", text="Натиск: враг не отвечает на удар", hp=2)
_u("magic_guard_epic", "guard", 4, "Гвардия", "🛡", ability="guard", text="Отвечают на два удара за раунд")
_u("magic_guard_legend", "guard", 5, "Гвардия", "🛡", ability="cleave", text="Удар чемпиона: задевает всех врагов рядом")
GUARD_UNITS = {"common": "magic_guard_common", "rare": GUARD, "epic": "magic_guard_epic",
               "legendary": "magic_guard_legend", "diamond": "magic_guard_legend"}
GUARD_CODES = frozenset(GUARD_UNITS.values())

# XP needed for each level (index = level − 1). Slow on purpose: with 10 runs a day (5 free +
# 1 for coins + 4 for Stars) the guard is maxed in about two months, with 5 a day in four.
CAPTAIN_XP = (0, 2500, 8000, 20000, 45000)
GUARD_XP = (0, 800, 2200, 4300, 7500, 12000, 18000, 26000, 38000, 54000)
CAPTAIN_TRAIT_LEVELS = (3, 5)
GUARD_TRAIT_LEVELS = (3, 6, 9)
CAPTAIN_DUP_XP = 150  # a spare copy of the captain's own footballer (GameConfig can override)
# Refill of the guard: points per burnt copy; a fighter costs GUARD_POINTS_PER_FIGHTER points
# of the rare guard, scaled by how strong one fighter of this guard is.
GUARD_POINTS = {"same": 6, "higher": 4, "same_rarity": 3, "lower": 2}
GUARD_POINTS_PER_FIGHTER = 6
GUARD_SIZE = (15, 40)  # rare-guard fighters at level 1 → level 10
GROWTH_PCT = 5  # atk / def per level above the first
GUARD_HP_PCT = 4  # the guard's hp per level above the first
TRAITS = {
    "striker": ("⚽", "Бомбардир", "+15% к атаке отряда"),
    "wall": ("🧱", "Стена", "+15% к защите отряда"),
    "stamina": ("💪", "Выносливость", "+20% здоровья каждого бойца"),
    "pace": ("👟", "Скорость", "+1 к скорости отряда"),
}


def level_of(xp: int, table: tuple) -> int:
    return sum(1 for need in table if xp >= need)


def trait_slots(level: int, levels: tuple) -> int:
    return sum(1 for lv in levels if level >= lv)


def guard_unit(rarity: str) -> str:
    return GUARD_UNITS.get(rarity or "", GUARD)


def _guard_ratio(unit: str) -> float:
    """How many fighters of this guard weigh as much as one of the rare guard."""
    return unit_value(UNITS[GUARD]) / unit_value(UNITS[unit])


def guard_size(level: int, unit: str = GUARD) -> int:
    lo, hi = GUARD_SIZE
    base = lo + (hi - lo) * (max(1, min(10, level)) - 1) // 9
    return max(1, round(base * _guard_ratio(unit)))


def guard_fighter_points(unit: str = GUARD) -> int:
    """Refill points one fighter of this guard costs."""
    return max(1, round(GUARD_POINTS_PER_FIGHTER / _guard_ratio(unit)))


def run_xp(state: dict, pct: int = 100) -> int:
    """XP a captain / the guard earns from a run it marched in (none for a forfeit)."""
    if state.get("forfeit"):
        return 0
    # A quick run has ~10 fights (7 XP each), hardcore ~14 (9 each); the per-run part counts
    # once per run the mode costs (hardcore: 2) — a hardcore run gives about what 2 quick ones do.
    L = MODES.get(state.get("mode", "quick"), QUICK_LAYOUT)
    runs = L["runs"]
    xp = runs * 20 + L["battle_xp"] * state.get("battles_won", 0) + (runs * 40 if state.get("winner") == "me" else 0)
    return xp * max(0, pct) // 100


def _pct(v: int, pct: int) -> int:
    return max(1, round(v * pct / 100)) if pct > 0 else 0


def _apply_growth(s: dict, level: int, traits: list) -> None:
    """A captain's (or the guard's) level and traits on its stack — in % of the stack's own
    numbers, so a level weighs the same on a goblin and on a dragon."""
    atk0, def0, hp0 = s["atk"], s["def"], s["hp"]
    s["atk"] += _pct(atk0, GROWTH_PCT * (level - 1))
    s["def"] += _pct(def0, GROWTH_PCT * (level - 1))
    for t in traits or []:
        if t == "striker":
            s["atk"] += _pct(atk0, 15)
        elif t == "wall":
            s["def"] += _pct(def0, 15)
        elif t == "stamina":
            s["hp"] += _pct(hp0, 20)
        elif t == "pace":
            s["spd"] += 1
    s["level"] = level
    s["traits"] = list(traits or [])
# Which creature a card of this tier becomes, by its position group (else the base one).
VARIANTS = {
    "dawn": {1: {"att": "dawn_squire"}, 2: {"def": "dawn_sister", "gk": "dawn_sister"}, 3: {"att": "dawn_knight"}},
    "ash": {1: {"att": "ash_hound"}, 2: {"def": "ash_leech", "gk": "ash_leech"}, 3: {"def": "ash_butcher", "gk": "ash_butcher"}},
}
VARIANT_NOTE = {"att": "нападающие", "def": "защитники и вратари", "gk": "защитники и вратари"}


def faction_unit(faction: str, tier: int, position: Optional[str] = None) -> str:
    """The creature a card of `tier` and `position` becomes in this faction."""
    group = POSITION_GROUP.get(position or "")
    alt = VARIANTS.get(faction, {}).get(tier, {}).get(group or "")
    return alt or FACTIONS[faction]["units"][tier - 1]


# ---------------------------------------------------------------------------
# Creature cards («Магический пак», docs/magic-army.md): a card is a band of fighters
# of one creature. Packs mix every race (Рассвет, Пепел, the wild): the hero's faction
# gives spells, the army is whatever the player collected.
# ---------------------------------------------------------------------------

CARD_FIGHTERS = {1: 10, 2: 8, 3: 5, 4: 3, 5: 1}
PACK_SIZE = 5
PACK_ODDS = ((1, 550), (2, 280), (3, 120), (4, 45), (5, 5))  # per mille, sums to 1000
STARTER_TIERS = (1, 1, 1, 1, 2, 2, 3)  # the first cards of each faction, once


def creature_pool(tier: int) -> list[str]:
    """Every creature of this tier, of any race (the guard is never in a pack)."""
    return sorted(c for c, u in UNITS.items() if u["tier"] == tier and u["faction"] in FACTIONS_AND_WILD)


def open_pack(r: random.Random, size: int = PACK_SIZE) -> list[str]:
    """The creature codes of a fresh pack (one per card)."""
    out = []
    for _ in range(size):
        roll, tier = r.randrange(1000), 1
        for t, w in PACK_ODDS:
            if roll < w:
                tier = t
                break
            roll -= w
        out.append(r.choice(creature_pool(tier)))
    return out


def starter_cards(r: random.Random, faction: str) -> list[str]:
    """A faction's base creatures: the starter set holds both factions' (variants come from packs)."""
    return [FACTIONS[faction]["units"][t - 1] for t in STARTER_TIERS]


# Camps with a character: each style asks for its own plan.
CAMP_STYLES = {
    "mixed": {"label": "Лагерь", "units": WILD_UNITS,
              "tiers": {1: [1, 1, 2], 2: [1, 2, 3], 3: [2, 3, 4]}},
    "archers": {"label": "Лагерь стрелков", "units": ["wild_thug", "wild_sling", "wild_crossbow", "wild_ogre"],
                "tiers": {1: [2, 2, 1], 2: [2, 3, 3], 3: [3, 3, 4]}},
    "flyers": {"label": "Гнездо летунов", "units": ["wild_thug", "wild_crow", "wild_harpy", "wild_ogre"],
               "tiers": {1: [2, 2, 1], 2: [2, 3, 2], 3: [3, 3, 4]}},
    "wall": {"label": "Стена громил", "units": ["wild_thug", "wild_bouncer", "wild_troll", "wild_ogre"],
             "tiers": {1: [2, 1], 2: [2, 3], 3: [3, 4, 4]}},
}
# «Приключение»: camps of the two races too, and the Lost in the far lairs (level 4).
CAMP_STYLES["dawn"] = {"label": "Застава Рассвета", "units": ["dawn_banner", "dawn_spear", "dawn_priest", "dawn_guard"],
                       "tiers": {1: [1, 1, 2], 2: [1, 2, 3], 3: [2, 3, 4]}}
CAMP_STYLES["ash"] = {"label": "Логово Пепла", "units": ["ash_bones", "ash_imp", "ash_witch", "ash_golem"],
                      "tiers": {1: [1, 1, 2], 2: [1, 2, 3], 3: [2, 3, 4]}}
CAMP_STYLES["lost"] = {"label": "Логово Потерявших всё", "units": LOST_UNITS, "tiers": {4: [3, 3, 4]}}
CAMP_STYLE_HINT = {
    "mixed": "", "archers": "Стрелки: подходи вплотную — в ближнем бою они бьют вполсилы",
    "flyers": "Летуны: быстрые, перелетают через всех — береги стрелков",
    "wall": "Громилы: медленные и крепкие — расстреливай издалека",
    "dawn": "Рассвет: лечат своих — бей сначала врачей",
    "ash": "Пепел: сглаз и нежить — заканчивай бой быстро",
    "lost": "Потерявшие всё: боссы с особыми умениями — приходи сильным",
}
BASE_LUCK, BASE_MORALE = 5, 5  # % chance of a double hit / an extra turn

# ---------------------------------------------------------------------------
# Run flavour: hero perks, quests, events of the day, the rival's character
# ---------------------------------------------------------------------------

# Score at which the hero grows within the run and picks 1 of 3 perks.
PERK_AT = (70, 170, 300, 450, 620, 820, 1050)
PERKS = {
    "steps": ("👣", "Скороход", "+1 шаг каждый день"),
    "atk": ("⚔️", "Ярость", "+10% урона армии"),
    "def": ("🛡️", "Стойкость", "−10% урона по армии"),
    "magic": ("🔮", "Чародей", "+1 сила магии и +3 маны"),
    "luck": ("🍀", "Фарт", "+8% к удаче: двойной удар чаще"),
    "scout": ("🔭", "Разведчик", "Герой видит на 1 клетку дальше"),
}
# code: text, target (quick, hardcore)
QUESTS = {
    "mines": ("Владей двумя золотыми шахтами", (2, 2, 2)),
    "camps": ("Разбей {n} {camps}", (3, 5, 12)),
    "chests": ("Открой {n} {chests}", (3, 6, 12)),
    "artifacts": ("Найди {n} {artifacts}", (2, 3, 5)),
    "strong": ("Разбей сильный лагерь до дня {n}", (4, 7, 10)),
}
QUEST_GOLD, QUEST_SCORE = 250, 25


def _quest_text(code: str, n: int) -> str:
    few = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return QUESTS[code][0].format(n=n, camps="лагеря" if few else "лагерей", chests="сундука" if few else "сундуков",
                                  artifacts="артефакта" if few else "артефактов")
# Something happens on some mornings.
EVENTS = {
    "caravan": ("🐫", "Караван у рынка", "Сегодня наём на рынке на 30% дешевле"),
    "storm": ("🌧️", "Буря", "Дороги размыло: сегодня на 2 шага меньше"),
    "tailwind": ("🌬️", "Попутный ветер", "Сегодня на 2 шага больше"),
    "deserters": ("🏳️", "Дезертиры", "Отряд из чужой армии просится к тебе — уже в строю"),
    "purse": ("👛", "Оброненный кошель", "Купцы потеряли кошель: +150 золота"),
    "lost": ("🧭", "Соперник заблудился", "Этой ночью соперник пройдёт меньше"),
}
EVENT_CHANCE = 45
BOT_STYLES = {
    "greedy": ("Жадина", "Гоняется за сундуками, шахтами и сокровищами"),
    "warrior": ("Воитель", "Громит лагеря и нападает сам, если ты слабее"),
    "sly": ("Хитрец", "Берёт что ближе и выгоднее"),
}

# code: name, mana cost, target (ally | enemy | all_enemies), description
SPELLS = {
    "bless": ("Благословение", 3, "ally", "Отряд бьёт на 30% сильнее 2 раунда"),
    "wall": ("Стена света", 4, "ally", "Отряд получает на 40% меньше урона 2 раунда"),
    "sunstrike": ("Солнечный удар", 5, "enemy", "Луч света: урон 25 + 15 за силу магии"),
    "curse": ("Проклятие", 3, "enemy", "Отряд бьёт на 30% слабее 2 раунда"),
    "raise": ("Поднять павших", 4, "ally", "Возвращает 30 + 20 за силу магии здоровья, павшие встают"),
    "firerain": ("Огненный дождь", 6, "all_enemies", "Каждый отряд врага: урон 12 + 8 за силу магии"),
}
# How many of the faction's spells a hero of this level knows.
SPELLS_BY_LEVEL = ((1, 2), (3, 3))

ARTIFACTS = {
    "boots": ("Бутсы-скороходы", "👟", "+2 хода в день"),
    "armband": ("Повязка капитана", "🎗️", "+10% урона армии"),
    "shinguards": ("Щитки стража", "🦺", "−10% урона по армии"),
    "whistle": ("Свисток чародея", "📯", "+1 сила магии"),
    "flag": ("Флаг трибун", "🚩", "+1 скорость армии"),
}

POSITION_GROUP = {
    "GK": "gk", "CB": "def", "LB": "def", "RB": "def", "LWB": "def", "RWB": "def",
    "CDM": "mid", "CM": "mid", "CAM": "mid", "LM": "mid", "RM": "mid",
    "LW": "att", "RW": "att", "ST": "att",
}
POSITION_TRAIT = {
    "att": "Нападающий: +12% урона", "def": "Защитник: −10% урона по отряду",
    "mid": "Полузащитник: +1 скорость", "gk": "Вратарь: отвечает на каждый удар",
}

DIFFICULTY = {
    # army power vs yours, bot moves per day, bot spell power, bot mana
    "easy": {"label": "Лёгкий", "power": 60, "moves": 6, "spell_power": 1, "mana": 6},
    "normal": {"label": "Средний", "power": 95, "moves": 7, "spell_power": 2, "mana": 8},
    "hard": {"label": "Сложный", "power": 135, "moves": 8, "spell_power": 3, "mana": 10},
}

# The playable land is a tall band of an n×n grid, so on a phone the map fills
# the whole screen: |x − y| ≤ half_w (screen width) and v0 ≤ x + y ≤ v1 (screen
# height; v0 + v1 = 2(n − 1) keeps it point-symmetric). Castles stand at the
# bottom (you) and the top (the rival).
#   quick    — the everyday run: one screen-and-a-bit, 7 days, a long step.
#   hardcore — about 3.2× the land, 13 camps a side, 14 days; costs 2 runs
#              and pays like 2 (the service scales it).
MODES = {
    "quick": {
        # A longer step (+4 moves a day) and 7 camps a side: ~10 fights in the same 7 days.
        "label": "Быстрая схватка", "n": 28, "half_w": 6, "v0": 6, "v1": 48, "me": (22, 22),
        "extra_days": 0, "extra_moves": 4, "runs": 1, "battle_xp": 7,
        "camps": ((3, (12, 15)), (3, (10, 14)), (2, (7, 12)), (2, (8, 13)), (1, (3, 7)), (1, (4, 9)), (1, (5, 11))),
        "pairs": (("chest", 4), ("well", 1), ("artifact", 2), ("tribune", 1), ("reinforce", 1), ("market", 1), ("mine", 1),
                  ("training", 1), ("medic", 1)),
        "terrain": 1,
    },
    "hardcore": {
        # 14 days on a 60-cell band, 13 camps a side: ~2× a quick run in time, battles and
        # score, so it costs 2 runs and pays like 2 (the progress pace stays the same).
        "label": "Хардкор", "n": 60, "half_w": 8, "v0": 6, "v1": 112, "me": (53, 53),
        "extra_days": 7, "extra_moves": 0, "runs": 2, "battle_xp": 9,
        "camps": ((3, (40, 46)), (3, (36, 44)), (3, (32, 40)), (3, (28, 36)), (2, (24, 32)), (2, (20, 28)),
                  (2, (16, 24)), (2, (13, 20)), (2, (10, 16)), (1, (3, 8)), (1, (5, 11)), (1, (7, 13)), (1, (9, 15))),
        "pairs": (("chest", 12), ("well", 3), ("artifact", 5), ("tribune", 3), ("reinforce", 3), ("market", 2), ("mine", 4),
                  ("training", 2), ("floodtower", 2), ("medic", 1), ("tunnel", 1)),
        "terrain": 4,
    },
    "adventure": {
        # No rival: 31 days on a huge band to loot and grow, then Безликий in his lair at the top.
        # Camps get stronger the farther from home (levels by distance; the far quarter are Lost lairs).
        "label": "Приключение", "n": 76, "half_w": 10, "v0": 6, "v1": 144, "me": (69, 69),
        "extra_days": 24, "extra_moves": 4, "runs": 4, "battle_xp": 9, "solo": True,
        "camps": tuple((1, (3 + 4 * i, 9 + 4 * i)) for i in range(15)),
        "pairs": (("chest", 20), ("well", 5), ("artifact", 8), ("tribune", 5), ("reinforce", 6), ("market", 4), ("mine", 5),
                  ("training", 3), ("floodtower", 3), ("medic", 2), ("tunnel", 2), ("shrine", 2)),
        "terrain": 5,
    },
}
# «Приключение»: a camp's level by how far it stands from home (share of the castles' distance).
SOLO_LEVELS = ((0.22, 1), (0.47, 2), (0.74, 3), (1.01, 4))
SOLO_REST_PCT = 20  # «Приключение»: % of each stack the night's rest brings back
QUICK = QUICK_LAYOUT = MODES["quick"]
# The quick layout under its old names (tests, older code).
MAP_W = MAP_H = QUICK["n"]
MAP_HALF_W, MAP_V0, MAP_V1 = QUICK["half_w"], QUICK["v0"], QUICK["v1"]
ME_CASTLE = QUICK["me"]
BOT_CASTLE = (MAP_W - 1 - ME_CASTLE[0], MAP_H - 1 - ME_CASTLE[1])
BIOMES = ("meadow", "desert", "snow", "ash")
VISION = 3  # how far the hero sees
FIELD_W, FIELD_H = 10, 10  # a square football pitch of square cells (fits a phone in portrait)
# What stands on the pitch besides the biome's hazard (frontend/public/magic/battle/obstacles/<kind>.png).
BATTLE_OBSTACLES = ["cones", "dummies", "ball_cart", "goalpost", "bench"]
# A Lost lair and Безликий fight on their own cracked pitch with its own junk.
LAIR_OBSTACLES = ["floodlight", "mirror", "grave"]
# Map buildings (docs: the adventure's buildings).
TRAINING_PCT = 10   # «Тренировочная база»: +% army damage for the rest of the run
FLOODTOWER_SIGHT = 12  # «Прожекторная вышка»: how far its beam lifts the fog
MEDIC_EVERY = 5     # «Лазарет команды»: days between two full heals
TUNNEL_SOLO_FROM = 0.27  # «Приключение»: a tunnel's near end at least this share of the way out
# Objects that stay on the map after a visit (walked onto again and again).
REUSABLE = ("market", "mine", "medic", "tunnel")
MAX_ROUNDS = 25
MAX_STACKS = 5

# Hero classes, picked before a run: what each changes against the level's base stats.
HERO_CLASSES = {
    "knight": {"code": "knight", "leadership": 3, "name": "Рыцарь", "emoji": "🛡️",
               "tagline": "Отряды +1 к атаке и защите, но маны на 2 меньше",
               "mana": -2, "spell_power": 0, "moves": 0, "atk": 1, "def": 1, "spd": 0},
    "mage": {"code": "mage", "leadership": -2, "name": "Маг", "emoji": "🔮",
             "tagline": "Маны +4 и заклинания на 1 сильнее",
             "mana": 4, "spell_power": 1, "moves": 0, "atk": 0, "def": 0, "spd": 0},
    "ranger": {"code": "ranger", "leadership": 0, "name": "Следопыт", "emoji": "🏹",
               "tagline": "+2 шага в день и +1 к скорости отрядов, маны на 1 меньше",
               "mana": -1, "spell_power": 0, "moves": 2, "atk": 0, "def": 0, "spd": 1},
}


# Which class each hero skin dresses (a skin shows only on its own class).
SKIN_CLASS = {"gold": "knight", "frost": "knight", "shadow": "mage", "ember": "mage", "grove": "ranger", "night": "ranger"}


def skin_for(skin: str, hero_class: str) -> str:
    return skin if SKIN_CLASS.get(skin, hero_class) == hero_class else "default"


# Leadership (docs/magic-army.md): what each stack of this tier costs, and the hero's budget.
STACK_COST = {1: 1, 2: 2, 3: 3, 4: 5, 5: 8}
# The highest creature tier a captain of this rarity may lead.
CAPTAIN_CAP = {"common": 2, "rare": 3, "epic": 4, "legendary": 5, "diamond": 5}


def leadership(level: int, hero_class: str = "knight") -> int:
    return 10 + level + HERO_CLASSES.get(hero_class, HERO_CLASSES["knight"])["leadership"]


def hero_base(level: int, hero_class: str = "knight") -> tuple[int, int]:
    """(max mana, spell power) a hero of this level and class starts a run with."""
    c = HERO_CLASSES[hero_class]
    return max(3, 6 + level + c["mana"]), 1 + level // 3 + c["spell_power"]
CAMP_POWER = {1: 30, 2: 50, 3: 75, 4: 105}  # % of the player's starting army power (4: a Lost lair)
SCORE = {"chest": 10, "well": 5, "artifact": 15, "tribune": 5, "reinforce": 10, "mine": 15,
         "training": 10, "floodtower": 5, "medic": 5, "tunnel": 0, "shrine": 10,
         "camp": {1: 20, 2: 35, 3: 55, 4: 80}, "final": 100, "boss": 250}
# What the rival hero gains (army %) when it takes an object first.
BOT_GAIN = {"chest": 1, "well": 1, "artifact": 3, "tribune": 2, "reinforce": 3, "mine": 2, "training": 3, "camp": {1: 2, 2: 4, 3: 6, 4: 8}}
# «Боевой дух»: the army's damage % for each camp beaten, kept until the run ends.
CAMP_MORALE = {1: 4, 2: 6, 3: 10, 4: 12}
# Mirrored pairs of each object on the old quick map (MODES has the current layouts).
OBJECT_PAIRS = (("chest", 4), ("well", 1), ("artifact", 2), ("tribune", 1), ("reinforce", 1), ("market", 1), ("mine", 1))
MINE_GOLD = 100  # gold a mine gives its owner every morning
MARKET_PRICE = {2: 400, 3: 700, 4: 1100}
# Hero XP = the run's score (~300 a run). Level 10 takes about a month at 10 runs a day.
HERO_LEVELS = (0, 1500, 4000, 8000, 14000, 22000, 33000, 48000, 68000, 95000)


def rng(state: dict) -> random.Random:
    state["rng_n"] = state.get("rng_n", 0) + 1
    return random.Random(f"magic:{state['seed']}:{state['rng_n']}")


def other(side: str) -> str:
    return "foe" if side == "me" else "me"


def hero_level(xp: int) -> int:
    level = 1
    for i, need in enumerate(HERO_LEVELS):
        if xp >= need:
            level = i + 1
    return level


def level_bounds(level: int) -> tuple[int, Optional[int]]:
    start = HERO_LEVELS[min(level, len(HERO_LEVELS)) - 1]
    nxt = HERO_LEVELS[level] if level < len(HERO_LEVELS) else None
    return start, nxt


def known_spells(faction: str, level: int) -> list[str]:
    n = 0
    for need, count in SPELLS_BY_LEVEL:
        if level >= need:
            n = count
    return FACTIONS[faction]["spells"][:n]


# ---------------------------------------------------------------------------
# Stacks
# ---------------------------------------------------------------------------

def stack_count(tier: int, copies: int, cap: int) -> int:
    return max(1, min(cap, round(BASE_COUNT[tier] * math.sqrt(max(1, copies)))))


def unit_value(u: dict) -> float:
    return u["hp"] + 3 * (u["dmin"] + u["dmax"]) / 2 + 1.5 * (u["atk"] + u["def"])


def make_stack(sid: str, unit_code: str, count: int, *, card: Optional[dict] = None, position: Optional[str] = None,
               rating: int = 75, copies: int = 1) -> dict:
    u = UNITS[unit_code]
    bonus = max(-3, min(5, (rating - 75) // 4)) if card else 0
    group = POSITION_GROUP.get(position or "", None)
    return {
        "id": sid, "unit": unit_code, "name": (card or {}).get("name") or u["name"], "card": card,
        "position": position, "group": group, "rating": rating, "copies": copies,
        "tier": u["tier"], "hp": u["hp"], "atk": u["atk"] + bonus, "def": u["def"] + bonus,
        "dmin": u["dmin"], "dmax": u["dmax"], "spd": u["spd"] + (1 if group == "mid" else 0),
        "ranged": u["ranged"], "flying": u["flying"], "ability": u["ability"],
        "count": count, "max_count": count,
    }


def stack_power(s: dict) -> float:
    return s["count"] * unit_value(s)


def army_power(stacks: list[dict]) -> int:
    return int(sum(stack_power(s) for s in stacks if s["count"] > 0))


def scaled_army(faction_units: list[str], tiers: list[int], target_power: float, prefix: str) -> list[dict]:
    """An army of `faction_units` creatures in the given tiers whose power is
    about `target_power`, split evenly between the stacks."""
    tiers = tiers or [1, 2, 3]
    share = target_power / len(tiers)
    out = []
    for i, tier in enumerate(tiers, 1):
        code = faction_units[min(tier, len(faction_units)) - 1]
        u = UNITS[code]
        count = max(1, round(share / unit_value(u)))
        out.append(make_stack(f"{prefix}{i}", code, count))
    return out


# ---------------------------------------------------------------------------
# Map
#
# A tall band of a 28×28 grid (see MAP_HALF_W) in one of four biomes. Terrain (forests, rocks, mountains,
# lakes) and every object are generated from the run seed, point-symmetric
# around the centre so both castles get an equal share; each run is a new
# layout, so a map can't be learnt by heart. Fog of war: the player only
# sees what the hero has been near (`seen`), the service strips the rest.
# ---------------------------------------------------------------------------

def _in_band(L: dict, x: int, y: int) -> bool:
    """Inside the playable band of a new map of layout `L` (a MODES entry)."""
    n = L["n"]
    return 0 <= x < n and 0 <= y < n and abs(x - y) <= L["half_w"] and L["v0"] <= x + y <= L["v1"]


BANDS = {k: [(x, y) for y in range(L["n"]) for x in range(L["n"]) if _in_band(L, x, y)] for k, L in MODES.items()}
BAND = BANDS["quick"]

def inside(state: dict, x: int, y: int) -> bool:
    """Inside this run's map (runs started before the band are full squares)."""
    m = state["map"]
    if not (0 <= x < m["w"] and 0 <= y < m["h"]):
        return False
    s = m.get("shape")
    return s is None or (abs(x - y) <= s[0] and s[1] <= x + y <= s[2])


def _neighbours(state: dict, x: int, y: int):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if inside(state, nx, ny):
            yield nx, ny


def _mirror(x: int, y: int, n: int = MAP_W) -> tuple:
    return n - 1 - x, n - 1 - y


def _object_at(state: dict, x: int, y: int) -> Optional[dict]:
    for o in state["map"]["objects"]:
        if o["x"] == x and o["y"] == y and (not o.get("taken_by") or o["kind"] in REUSABLE):
            return o
    return None


def _blocked(state: dict) -> set:
    return {(b[0], b[1]) for b in state["map"]["blocks"]}


def _stoppers(state: dict, who: str) -> set:
    """Cells a path may end on but not pass through: untaken objects (a
    market or a mine stays an object) and the other hero."""
    out = {(o["x"], o["y"]) for o in state["map"]["objects"]
           if o["kind"] != "castle" and (not o.get("taken_by") or o["kind"] in REUSABLE)}
    rival = state["bot"] if who == "me" else state["hero"]
    out.add((rival["x"], rival["y"]))
    return out


def _bfs(state: dict, start: tuple, who: str = "me", limit: Optional[int] = None) -> dict:
    """{cell: previous cell} for every cell reachable from `start` (within
    `limit` steps when given), plus `_dist` in a side dict."""
    blocks = _blocked(state)
    stoppers = _stoppers(state, who)
    prev = {start: None}
    dist = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur != start and cur in stoppers:
            continue  # you stop on an object, you don't walk through it
        if limit is not None and dist[cur] >= limit:
            continue
        for nb in _neighbours(state, *cur):
            if nb in prev or nb in blocks:
                continue
            prev[nb] = cur
            dist[nb] = dist[cur] + 1
            q.append(nb)
    return {"prev": prev, "dist": dist}


def _path_from(tree: dict, goal: tuple) -> Optional[list]:
    if goal not in tree["prev"]:
        return None
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = tree["prev"][cur]
    return path[::-1]


def map_path(state: dict, start: tuple, goal: tuple, who: str = "me") -> Optional[list]:
    """Shortest 4-way path start→goal (both ends included)."""
    return _path_from(_bfs(state, tuple(start), who), tuple(goal))


def reachable(state: dict) -> list[list[int]]:
    """Seen cells the player's hero can reach today (for the map highlight)."""
    hero = state["hero"]
    tree = _bfs(state, (hero["x"], hero["y"]), "me", limit=hero["moves"])
    return [[x, y] for (x, y), d in tree["dist"].items() if d > 0 and is_seen(state, x, y)]


def is_seen(state: dict, x: int, y: int) -> bool:
    return bool(state["seen"][y] >> x & 1)


def reveal(state: dict, x: int, y: int, radius: int = VISION) -> None:
    m = state["map"]
    for yy in range(max(0, y - radius), min(m["h"], y + radius + 1)):
        for xx in range(max(0, x - radius), min(m["w"], x + radius + 1)):
            if abs(xx - x) + abs(yy - y) <= radius + 1:
                state["seen"][yy] |= 1 << xx


def _blob(L: dict, r: random.Random, x: int, y: int, size: int) -> set:
    """A random-walk clump of cells around (x, y)."""
    cells = {(x, y)}
    cx, cy = x, y
    for _ in range(size * 3):
        if len(cells) >= size:
            break
        dx, dy = r.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        if not _in_band(L, cx + dx, cy + dy):
            continue
        cx, cy = cx + dx, cy + dy
        cells.add((cx, cy))
        if r.random() < 0.25:
            cx, cy = r.choice(sorted(cells))
    return cells


RIVER_OUT = 3  # the river runs on this many cells past the band's edge (drawn only)


def _river(L: dict, r: random.Random) -> set:
    """A winding river across the middle of the band, from one long edge to the other.

    Half of it is a walk from the edge to the centre (every step moves one cell across the
    band, meandering along it); the other half is its mirror, so the map stays fair. It
    starts a few cells outside the band so its mouths run off the map's edge."""
    n = L["n"]
    t = (n - 1) // 2
    target = 2 * t  # x + y at the centre cell (t, t)
    d = L["half_w"] + RIVER_OUT
    s = target + r.choice([-2, 0, 2]) + (d % 2)
    x, y = (s + d) // 2, (s - d) // 2
    cells = {(x, y)}
    last, run = None, 0
    while d > 0:
        # A step either lowers x or raises y: one cell closer to the centre line x == y.
        # At most two steps the same way in a row, so it bends instead of running straight.
        options = []
        for step, (nx, ny) in enumerate(((x - 1, y), (x, y + 1))):
            ns = nx + ny
            if abs(ns - target) <= d - 1 and abs(ns - target) <= 3 and not (step == last and run >= 2):
                options.append((step, nx, ny))
        if not options:  # only the same way is left to land on the centre
            options = [(s_, nx, ny) for s_, (nx, ny) in enumerate(((x - 1, y), (x, y + 1)))
                       if abs(nx + ny - target) <= d - 1]
        step, x, y = r.choice(options)
        run = run + 1 if step == last else 1
        last = step
        d -= 1
        cells.add((x, y))
        if r.random() < 0.3:
            cells.add(r.choice(((x + 1, y), (x, y - 1))))  # wider here
    if (n - 1) % 2:
        # An even grid has no centre cell: two cells join the half to its mirror.
        cells |= {(t + 1, t), (t, t + 1)}
    return cells | {_mirror(cx, cy, n) for cx, cy in cells}


def _terrain(L: dict, r: random.Random, me_castle: tuple, bot_castle: tuple) -> tuple[dict, list]:
    """{cell: (kind, variant)} of blocked terrain and the road between the castles."""
    n = L["n"]
    mirror = lambda x, y: _mirror(x, y, n)  # noqa: E731
    keep_clear = set()
    for cx, cy in (me_castle, bot_castle):
        for y in range(cy - 2, cy + 3):
            for x in range(cx - 2, cx + 3):
                if abs(x - cx) + abs(y - cy) <= 2:
                    keep_clear.add((x, y))
    blocks: dict = {}
    # Half the map is generated, the other half mirrors it.
    plan = []
    for _ in range(L["terrain"]):
        plan += [("mountain", r.randint(5, 8)), ("mountain", r.randint(3, 6)), ("water", r.randint(4, 7))]
        plan += [("tree", r.randint(3, 7)) for _ in range(6)] + [("rock", r.randint(1, 3)) for _ in range(4)]
    band = BANDS[next(k for k, v in MODES.items() if v is L)]
    river = _river(L, r)
    for cell in river:
        if _in_band(L, *cell) and cell not in keep_clear:
            blocks[cell] = ("water", r.randrange(3))
    for kind, size in plan:
        x, y = r.choice(band)
        for c in _blob(L, r, x, y, size):
            for cell in (c, mirror(*c)):
                if cell not in keep_clear and cell not in blocks:
                    blocks[cell] = (kind, r.randrange(3))
    # A road from castle to castle (drawn; it also keeps a corridor open).
    road = []
    x, y = me_castle
    while (x, y) != bot_castle:
        road.append((x, y))
        steps = [c for c in ((x - 1, y) if x > bot_castle[0] else None, (x, y - 1) if y > bot_castle[1] else None)
                 if c and _in_band(L, *c)]
        x, y = r.choice(steps)
    road.append(bot_castle)
    for c in road:
        blocks.pop(c, None)
        blocks.pop(mirror(*c), None)
    # Two ordered tracks (castle to castle and its mirror) for drawing a winding path.
    tracks = [[list(c) for c in road], [list(mirror(*c)) for c in road]]
    road = sorted(set(road) | {mirror(*c) for c in road})
    # Where the road crosses the river: bridges (the cells stay passable road).
    bridges = sorted(c for c in road if c in river)
    return blocks, road, tracks, river, bridges


def _straight_crossings(track: list, bridges: set) -> bool:
    """Every bridge cell on the road's path has its neighbours on opposite sides (no turn)."""
    path = [tuple(c) for c in track]
    for i, c in enumerate(path):
        if c not in bridges:
            continue
        if i == 0 or i == len(path) - 1:
            return False
        (ax, ay), (bx, by) = path[i - 1], path[i + 1]
        if abs(ax - bx) + abs(ay - by) != 2 or (ax != bx and ay != by):
            return False
    return True


def _generate_map(state: dict) -> None:
    r = rng(state)
    mode = state.get("mode", "quick")
    L = MODES[mode]
    size = L["n"]
    _mirror = lambda x, y: (size - 1 - x, size - 1 - y)  # noqa: E731,N806 — this layout's mirror
    me_castle = L["me"]
    bot_castle = _mirror(*me_castle)
    biome = r.choice(BIOMES)
    shape = [L["half_w"], L["v0"], L["v1"]]
    state["map"] = {"w": size, "h": size, "shape": shape, "blocks": [], "objects": []}
    for attempt in range(200):
        blocks, road, tracks, river, bridges = _terrain(L, r, me_castle, bot_castle)
        # A short, straight crossing (one painted bridge, not a jog over the water) — the last
        # tries take any short one so a big map always comes out.
        if len(bridges) > 6 or (attempt < 90 and not _straight_crossings(tracks[0], set(bridges))):
            continue
        # Pockets the castles can't reach become terrain too.
        free = {c for c in BANDS[mode] if c not in blocks}
        seen_cells = {me_castle}
        q = deque([me_castle])
        while q:
            cur = q.popleft()
            for nb in _neighbours(state, *cur):
                if nb in free and nb not in seen_cells:
                    seen_cells.add(nb)
                    q.append(nb)
        for c in free - seen_cells:
            blocks[c] = ("tree", r.randrange(3))
        free = seen_cells
        if bot_castle not in free:
            continue
        road_set = set(road)

        def open_cell(c):
            # Not a corridor: an object there would cut the map in two.
            return c in free and c not in road_set and sum(1 for nb in _neighbours(state, *c) if nb in free) >= 3

        dist_me = {c: abs(c[0] - me_castle[0]) + abs(c[1] - me_castle[1]) for c in free}
        # Candidate cells on the player's half (the mirror gives the rival's).
        half = [c for c in free if open_cell(c) and open_cell(_mirror(*c)) and dist_me[c] < dist_me[_mirror(*c)]
                and dist_me[c] > 2]
        r.shuffle(half)
        used: set = set()

        def take(pred) -> Optional[tuple]:
            # Rather not even on a diagonal of another object (two of them across a narrow pass
            # would shut it), but a crowded map takes any cell not right next to one.
            for gap in (lambda dx, dy: max(dx, dy), lambda dx, dy: dx + dy):
                for c in half:
                    if c in used or _mirror(*c) in used or not pred(c):
                        continue
                    if any(gap(abs(c[0] - u[0]), abs(c[1] - u[1])) < 2 for u in used):
                        continue
                    used.add(c)
                    used.add(_mirror(*c))
                    return c
            return None

        objects = [
            {"id": "c_me", "kind": "castle", "owner": "me", "x": me_castle[0], "y": me_castle[1]},
            {"id": "c_bot", "kind": "castle", "owner": "bot", "x": bot_castle[0], "y": bot_castle[1]},
        ]
        ok = True
        n = 0
        solo = L.get("solo", False)
        span = dist_me[bot_castle]
        for level, (lo, hi) in L["camps"]:
            c = take(lambda c, lo=lo, hi=hi: lo <= dist_me[c] <= hi)
            if c is None:
                ok = False
                break
            style = r.choice(["mixed", "mixed", "archers", "flyers", "wall"] + (["dawn", "ash"] if solo else []))
            for cell in (c, _mirror(*c)):
                lv = level
                if solo:
                    lv = next((v for share, v in SOLO_LEVELS if dist_me[cell] < share * span), 4)
                n += 1
                if lv == 4:
                    lost = r.sample(LOST_UNITS, 3)
                    objects.append({"id": f"camp{n}", "kind": "camp", "level": 4, "x": cell[0], "y": cell[1],
                                    "unit": lost[0], "tiers": [UNITS[c]["tier"] for c in lost], "style": "lost",
                                    "lost": lost})
                    continue
                st = CAMP_STYLES[style]
                tiers = st["tiers"][lv]
                objects.append({"id": f"camp{n}", "kind": "camp", "level": lv, "x": cell[0], "y": cell[1],
                                "unit": st["units"][max(tiers) - 1], "tiers": tiers, "style": style})
        if not ok:
            continue
        artifacts = list(ARTIFACTS)
        r.shuffle(artifacts)
        art_i = 0
        for kind, pairs in L["pairs"]:
            for k in range(pairs):
                # A tunnel links the two halves: one end near each castle, not two holes side by side.
                # «Приключение»: its far end stays short of the Lost lairs and Безликий's tower.
                c = take((lambda c: 2 * dist_me[c] < dist_me[_mirror(*c)] and (not solo or dist_me[c] > TUNNEL_SOLO_FROM * span))
                         if kind == "tunnel" else (lambda c: True))
                if c is None:
                    ok = False
                    break
                for j, cell in enumerate((c, _mirror(*c))):
                    obj = {"id": f"{kind}{2 * k + j + 1}", "kind": kind, "x": cell[0], "y": cell[1]}
                    if kind == "artifact":
                        obj["artifact"] = artifacts[art_i % len(artifacts)]
                        art_i += 1
                    if kind == "reinforce":
                        obj["tier"] = r.choice([2, 3])
                    if kind == "chest":
                        obj["gold"] = r.randint(4, 8) * 50
                    if kind == "tunnel":
                        obj["to"] = f"tunnel{2 * k + 2 - j}"
                    objects.append(obj)
            if not ok:
                break
        if not ok:
            continue
        # Ground decor on a few free cells (drawn only).
        decor_cells = sorted(free - used - road_set - {me_castle, bot_castle})
        r.shuffle(decor_cells)
        decor = [[x, y, r.randrange(4)] for x, y in decor_cells[: len(decor_cells) // 5]]
        state["map"] = {
            "w": size, "h": size, "shape": shape, "biome": biome,
            "blocks": [[x, y, kind, var] for (x, y), (kind, var) in sorted(blocks.items())],
            "road": [list(c) for c in road], "tracks": tracks, "decor": decor, "objects": objects,
            # The river's cells (also past the band's edge, drawn only) and its bridges.
            "river": [list(c) for c in sorted(river)], "bridges": [list(c) for c in bridges],
        }
        # Every object must be reachable from both castles (objects block passing).
        me_tree = _bfs(state, me_castle, "me")
        state_bot = state["bot"]
        bot_tree = _bfs(state, (state_bot["x"], state_bot["y"]), "bot")
        if all((o["x"], o["y"]) in me_tree["prev"] and (o["x"], o["y"]) in bot_tree["prev"] for o in objects):
            return
    raise EngineError("map generation failed")


def _market_offers(state: dict) -> list[dict]:
    units = FACTIONS[state["faction"]]["units"]
    avg = state["start_power"] / max(1, len(state["army"]))
    r = rng(state)
    offers = []
    for tier in sorted(r.sample([2, 3, 4], 2)):
        code = units[tier - 1]
        count = max(1, round(avg * 0.55 / unit_value(UNITS[code])))
        offers.append({"unit": code, "count": count, "price": MARKET_PRICE[tier], "bought": False})
    return offers


def new_run(seed: str, *, faction: str, difficulty: str, army: list[dict], hero_level_: int,
            days: int, moves_per_day: int, stack_cap: int, mode: str = "quick", hero_class: str = "knight",
            mana_bonus: int = 0, guard: Optional[dict] = None, scaling_pct: int = 100) -> dict:
    """`army`: [{"unit": code, "count", "card", "position", "rating", "copies"}] (the service built it)."""
    if faction not in FACTIONS:
        raise EngineError("Неизвестная раса")
    if hero_class not in HERO_CLASSES:
        raise EngineError("Неизвестный класс героя")
    cls = HERO_CLASSES[hero_class]
    moves_per_day += cls["moves"]
    max_mana, spell_power = hero_base(hero_level_, hero_class)
    max_mana += max(0, mana_bonus)
    if difficulty not in DIFFICULTY:
        raise EngineError("Неизвестная сложность")
    if not army:
        raise EngineError("Нужна хотя бы одна карточка")
    if mode not in MODES:
        raise EngineError("Неизвестный режим")
    L = MODES[mode]
    days += L["extra_days"]
    moves_per_day += L["extra_moves"]
    me = L["me"]
    bot_at = _mirror(*me, L["n"])
    diff = DIFFICULTY[difficulty]
    rival = "ash" if faction == "dawn" else "dawn"
    stacks = [
        make_stack(f"m{i}", a["unit"], min(stack_cap, a["count"]), card=a.get("card"), position=a.get("position"),
                   rating=a.get("rating", 75), copies=a.get("copies", 1))
        for i, a in enumerate(army[:MAX_STACKS], 1)
    ]
    base_power = army_power(stacks)  # the army before any progress (levels, traits, the guard)
    for a, s in zip(army[:MAX_STACKS], stacks):
        if a.get("captain_level"):
            _apply_growth(s, a["captain_level"], a.get("traits") or [])
    if guard and guard.get("count", 0) > 0:
        unit = guard.get("unit") or GUARD
        # The rating gives no bonus here: every rarity has the same budget.
        g = make_stack("g1", unit, guard["count"], card=guard.get("card"), position=guard.get("position"), rating=75)
        g["name"] = f"Гвардия · {(guard.get('card') or {}).get('name') or ''}".strip(" ·")
        g["guard"] = True
        g["max_count"] = g["count"]
        g["hp"] += _pct(g["hp"], GUARD_HP_PCT * (guard.get("level", 1) - 1)) if guard.get("level", 1) > 1 else 0
        _apply_growth(g, guard.get("level", 1), guard.get("traits") or [])
        stacks.append(g)
    progress = max(0, army_power(stacks) - base_power)
    for s in stacks:
        s["atk"] += cls["atk"]
        s["def"] += cls["def"]
        s["spd"] += cls["spd"]
        s["own"] = s["own0"] = s["count"]  # fighters from the collection (hired ones are not theirs to lose)
    state = {
        "seed": seed, "rng_n": 0, "mode": mode, "phase": "map", "faction": faction, "rival": rival, "difficulty": difficulty,
        "day": 1, "days": days, "moves_per_day": moves_per_day, "score": 0, "events": [],
        "hero": {"x": me[0], "y": me[1], "moves": moves_per_day, "level": hero_level_, "class": hero_class,
                 "mana": max_mana, "max_mana": max_mana, "spell_power": spell_power,
                 "artifacts": [], "spells": known_spells(faction, hero_level_), "gold": 0},
        "bot": {"x": bot_at[0], "y": bot_at[1], "moves": diff["moves"], "gain_pct": 0, "taken": [],
                "solo": bool(L.get("solo"))},
        # The rivals grow with the army only by `scaling_pct` of its progress: a levelled army feels stronger.
        "army": stacks, "start_power": max(1, army_power(stacks) - progress * (100 - max(0, min(100, scaling_pct))) // 100),
        "battle": None, "winner": None, "log": [],
        "finished": False, "battles_won": 0, "seen": [0] * L["n"], "notice": None, "pending": None,
        "fallen": {},
    }
    _generate_map(state)
    for o in state["map"]["objects"]:
        if o["kind"] == "market":
            o["offers"] = _market_offers(state)
    r = rng(state)
    big = {"hardcore": 1, "adventure": 2}.get(mode, 0)
    state["bot"]["style"] = r.choice(sorted(BOT_STYLES))
    state["stats"] = {"chests": 0, "camps": 0, "strong_day": None}
    state["perks"] = []
    state["quests"] = [
        {"code": code, "text": _quest_text(code, QUESTS[code][1][big]), "target": QUESTS[code][1][big],
         "progress": 0, "done": False, "failed": False}
        for code in r.sample(sorted(QUESTS), 2)
    ]
    reveal(state, *me, VISION + 1)
    _log(state, "start", text=f"День 1. Герой выходит из замка — {FACTIONS[faction]['name']}")
    if L.get("solo"):
        state["bot"]["style"] = None
        state["rival_name"] = "Безликий"
    return state


def _log(state: dict, kind: str, **data) -> None:
    state["log"] = (state.get("log") or [])[-30:]
    state["log"].append({"kind": kind, "day": state["day"], **data})


def _notice(state: dict, kind: str, title: str, text: str, **data) -> None:
    """The popup the client shows for what just happened (one per action)."""
    state["notice"] = {"kind": kind, "title": title, "text": text, **data}


def _apply_object(state: dict, obj: dict, side: str) -> None:
    kind = obj["kind"]
    obj["taken_by"] = side
    if side == "bot":
        gain = BOT_GAIN[kind][obj["level"]] if kind == "camp" else BOT_GAIN[kind]
        state["bot"]["gain_pct"] += gain
        state["bot"]["taken"].append(obj["id"])
        _log(state, "bot_take", object=obj["id"], text=f"Соперник забрал: {object_label(obj)} (+{gain}% к его армии)")
        return
    hero = state["hero"]
    pts = SCORE[kind][obj["level"]] if kind == "camp" else SCORE[kind]
    state["score"] += pts
    title = object_label(obj)
    text = ""
    extra: dict = {}
    if kind == "well":
        hero["max_mana"] += 1
        hero["mana"] = hero["max_mana"]
        text = f"Мана восполнена, запас +1 (теперь {hero['max_mana']})"
    elif kind == "artifact":
        art = obj["artifact"]
        hero["artifacts"].append(art)
        if art == "boots":
            hero["moves"] += 2
        if art == "whistle":
            hero["spell_power"] += 1
        text = ARTIFACTS[art][2]
        extra["artifact"] = art
    elif kind == "tribune":
        healed = 0
        for s in state["army"]:
            if s["count"] < s["max_count"]:
                add = max(1, (s["max_count"] + 3) // 4)
                before = s["count"]
                s["count"] = min(s["max_count"], s["count"] + add)
                healed += s["count"] - before
                _own_back(state, s, s["count"] - before)
        text = f"Болельщики пополнили армию: +{healed} бойцов" if healed else "Армия и так в полном составе — болельщики поют гимн"
    elif kind == "camp":
        hero["morale"] = hero.get("morale", 0) + CAMP_MORALE[obj["level"]]
        title = f"{title} разбит"
        text = f"Боевой дух армии +{CAMP_MORALE[obj['level']]}% урона до конца похода"
    elif kind == "mine":
        text = f"Шахта твоя: +{MINE_GOLD} золота каждое утро"
    elif kind == "reinforce":
        units = FACTIONS[state["faction"]]["units"]
        code = units[obj["tier"] - 1]
        avg = state["start_power"] / max(1, len(state["army"]))
        count = max(1, round(avg * 0.6 / unit_value(UNITS[code])))
        if _add_stack(state, code, count):
            text = f"К армии присоединились {UNITS[code]['name']} ×{count}"
            extra["unit"] = code
        else:
            text = "В армии нет места — новобранцы ушли домой"
    elif kind == "training":
        hero["perk_atk"] = hero.get("perk_atk", 0) + TRAINING_PCT
        text = f"Сборы прошли: армия бьёт на {TRAINING_PCT}% сильнее до конца похода"
    elif kind == "floodtower":
        reveal(state, obj["x"], obj["y"], FLOODTOWER_SIGHT)
        text = "Луч прожектора разогнал туман вокруг"
    elif kind == "shrine":
        hero["ward"] = hero.get("ward", 0) + 1
        text = "Оберег от гипноза: первый гипноз Безликого не сработает"
        lair = _nearest_lair(state, obj)
        if lair:
            reveal(state, lair["x"], lair["y"], 1)
            text += ". В ближайшем логове: " + ", ".join(UNITS[c]["name"] for c in lair["lost"])
            extra["lair"] = lair["id"]
    _log(state, "take", object=obj["id"], points=pts, text=f"{title}: {text}")
    _notice(state, kind, title, text, points=pts, **extra)


def _nearest_lair(state: dict, obj: dict) -> Optional[dict]:
    lairs = [o for o in state["map"]["objects"] if o.get("style") == "lost" and not o.get("taken_by")]
    return min(lairs, key=lambda o: abs(o["x"] - obj["x"]) + abs(o["y"] - obj["y"]), default=None)


def _use_medic(state: dict, obj: dict) -> None:
    """«Лазарет команды»: the whole army back to full, then it needs MEDIC_EVERY days."""
    title = object_label(obj)
    ready = obj.get("ready_day", 1)
    if state["day"] < ready:
        _notice(state, "medic", title, f"Врачи отдыхают — лазарет снова примет на {ready}-й день")
        return
    healed = 0
    for s in state["army"]:
        if s["count"] < s["max_count"]:
            add = s["max_count"] - s["count"]
            s["count"] = s["max_count"]
            _own_back(state, s, add)
            healed += add
    obj["ready_day"] = state["day"] + MEDIC_EVERY
    pts = 0 if obj.get("taken_by") else SCORE["medic"]
    obj["taken_by"] = "me"
    state["score"] += pts
    text = (f"Армия в полном составе: +{healed} бойцов" if healed else "Все здоровы — врачи просто проверили пульс") + \
        f". Следующий приём на {obj['ready_day']}-й день"
    _log(state, "take", object=obj["id"], points=pts, text=f"{title}: {text}")
    _notice(state, "medic", title, text, points=pts)


def _use_tunnel(state: dict, obj: dict) -> None:
    """«Тоннель раздевалок»: step in here, come out at its other end."""
    hero = state["hero"]
    other = next((o for o in state["map"]["objects"] if o["id"] == obj.get("to")), None)
    if other is None:
        return
    obj["taken_by"] = other["taken_by"] = "me"
    hero["x"], hero["y"] = other["x"], other["y"]
    hero["goal"] = None
    reveal(state, other["x"], other["y"], VISION + 1 + hero.get("perk_vision", 0))
    text = "Герой прошёл под трибунами и вышел у другого конца тоннеля"
    _log(state, "tunnel", object=obj["id"], text=text)
    _notice(state, "tunnel", object_label(obj), text, to=[other["x"], other["y"]])


def _add_stack(state: dict, code: str, count: int) -> bool:
    for s in state["army"]:
        if s["unit"] == code and not s["card"]:
            s["count"] += count
            s["max_count"] += count
            return True
    if len([s for s in state["army"] if not s.get("guard")]) >= MAX_STACKS + 1:
        # No free slot: hired fighters join the smallest stack of the same
        # creature (a card's stack too) — that's how a stack is topped up.
        same = [s for s in state["army"] if s["unit"] == code]
        if not same:
            return False
        s = min(same, key=lambda s: s["count"])
        s["count"] += count
        s["max_count"] += count
        return True
    state["next_stack"] = state.get("next_stack", len(state["army"])) + 1
    hired = make_stack(f"r{state['next_stack']}", code, count)
    cls = HERO_CLASSES[state["hero"].get("class", "knight")]
    for k in ("atk", "def", "spd"):
        hired[k] += cls[k]
    state["army"].append(hired)
    return True


def object_label(obj: dict) -> str:
    kind = obj["kind"]
    if kind == "artifact":
        return f"Артефакт «{ARTIFACTS[obj['artifact']][0]}»"
    if kind == "camp":
        return f"{CAMP_STYLES[obj.get('style', 'mixed')]['label']} «{UNITS[obj['unit']]['name']}»"
    return {"chest": "Сундук с золотом", "well": "Источник маны", "tribune": "Трибуна", "reinforce": "Лагерь новобранцев",
            "castle": "Замок", "market": "Трансферный рынок", "mine": "Золотая шахта",
            "training": "Тренировочная база", "floodtower": "Прожекторная вышка", "medic": "Лазарет команды",
            "tunnel": "Тоннель раздевалок", "shrine": "Святилище Гильдии"}.get(kind, kind)


def market_price(state: dict, offer: dict) -> int:
    ev = state.get("event") or {}
    if ev.get("code") == "caravan" and ev.get("day") == state["day"]:
        return offer["price"] * 7 // 10
    return offer["price"]


def _morning_event(state: dict) -> Optional[str]:
    """Maybe something happens this morning (applied at once)."""
    r = rng(state)
    if r.randint(1, 100) > EVENT_CHANCE:
        state["event"] = None
        return None
    code = r.choice(sorted(c for c in EVENTS if not (c == "lost" and state["bot"].get("solo"))))
    hero = state["hero"]
    if code == "storm":
        hero["moves"] = max(2, hero["moves"] - 2)
    elif code == "tailwind":
        hero["moves"] += 2
    elif code == "purse":
        hero["gold"] = hero.get("gold", 0) + 150
    elif code == "lost":
        state["bot"]["lost"] = True
    elif code == "deserters":
        tier = r.choice([2, 3])
        unit = FACTIONS[state["faction"]]["units"][tier - 1]
        avg = state["start_power"] / max(1, len(state["army"]))
        if not _add_stack(state, unit, max(1, round(avg * 0.4 / unit_value(UNITS[unit])))):
            hero["gold"] = hero.get("gold", 0) + 100  # no room: they pay to go home
    state["event"] = {"code": code, "day": state["day"]}
    _log(state, "event", text=f"{EVENTS[code][0]} {EVENTS[code][1]}: {EVENTS[code][2]}")
    return code


def _bot_hunts(state: dict, moves: int) -> bool:
    """A warrior rival attacks the hero when it's clearly stronger and close."""
    if state["day"] < 3:
        return False
    bot, hero = state["bot"], state["hero"]
    bot_power = state["start_power"] * (DIFFICULTY[state["difficulty"]]["power"] + bot["gain_pct"]) / 100
    if bot_power < army_power(state["army"]) * 1.15:
        return False
    path = map_path(state, (bot["x"], bot["y"]), (hero["x"], hero["y"]), "bot")
    if not path or len(path) - 1 > moves:
        return False
    bot["trail"] = [list(c) for c in path[:-1]]
    bot["x"], bot["y"] = path[-2]
    _log(state, "bot_attack", text="Соперник напал на героя!")
    _start_final(state)
    return True


def _quest_progress(state: dict, q: dict) -> int:
    stats = state.get("stats") or {}
    if q["code"] == "mines":
        return sum(1 for o in state["map"]["objects"] if o["kind"] == "mine" and o.get("taken_by") == "me")
    if q["code"] == "camps":
        return stats.get("camps", 0)
    if q["code"] == "chests":
        return stats.get("chests", 0)
    if q["code"] == "artifacts":
        return len(state["hero"]["artifacts"])
    if q["code"] == "strong":
        day = stats.get("strong_day")
        return 1 if day and day <= q["target"] else 0
    return 0


def _progress(state: dict) -> None:
    """Quests and the hero's in-run growth, checked after every step of the run."""
    if state["phase"] != "map":
        return
    for q in state.get("quests") or []:
        if q["done"] or q["failed"]:
            continue
        q["progress"] = _quest_progress(state, q)
        goal = 1 if q["code"] == "strong" else q["target"]
        if q["progress"] >= goal:
            q["done"] = True
            state["hero"]["gold"] = state["hero"].get("gold", 0) + QUEST_GOLD
            state["score"] += QUEST_SCORE
            _log(state, "quest", text=f"Задание выполнено: {q['text']} (+{QUEST_GOLD} золота)")
            if not state.get("notice") or state["notice"].get("kind") != "day":
                _notice(state, "quest", "Задание выполнено!", q["text"], gold=QUEST_GOLD, points=QUEST_SCORE)
        elif q["code"] == "strong" and state["day"] > q["target"]:
            q["failed"] = True
    perks = state.setdefault("perks", [])
    if len(perks) < len(PERK_AT) and state["score"] >= PERK_AT[len(perks)]:
        r = rng(state)
        options = r.sample([p for p in sorted(PERKS) if not (p == "scout" and "scout" in perks)], 3)
        state["phase"] = "choice"
        state["pending"] = {"kind": "perk", "options": [
            {"code": p, "emoji": PERKS[p][0], "title": PERKS[p][1], "text": PERKS[p][2]} for p in options]}


def _take_perk(state: dict, code: str) -> None:
    hero = state["hero"]
    if code == "steps":
        state["moves_per_day"] += 1
        hero["moves"] += 1
    elif code == "atk":
        hero["perk_atk"] = hero.get("perk_atk", 0) + 10
    elif code == "def":
        hero["perk_def"] = min(40, hero.get("perk_def", 0) + 10)
    elif code == "magic":
        hero["spell_power"] += 1
        hero["max_mana"] += 3
        hero["mana"] += 3
    elif code == "luck":
        hero["perk_luck"] = hero.get("perk_luck", 0) + 8
    elif code == "scout":
        hero["perk_vision"] = hero.get("perk_vision", 0) + 1
        reveal(state, hero["x"], hero["y"], VISION + hero["perk_vision"])
    state["perks"].append(code)
    state["phase"] = "map"
    state["pending"] = None
    icon, name, text = PERKS[code]
    _log(state, "perk", text=f"Герой вырос: {name} — {text}")
    _notice(state, "perk", f"{icon} {name}", text)
    _progress(state)  # maybe the next perk is already due


def move_hero(state: dict, x: int, y: int) -> None:
    _move_hero(state, x, y)
    _progress(state)


def _move_hero(state: dict, x: int, y: int) -> None:
    if state["phase"] != "map":
        raise EngineError("Сначала закончи с тем, что открыто" if state["phase"] == "choice" else "Сейчас идёт бой")
    hero = state["hero"]
    if not inside(state, x, y):
        raise EngineError("За краем карты")
    if not is_seen(state, x, y):
        raise EngineError("Туда ещё не видно дороги")
    if (x, y) in _blocked(state):
        raise EngineError("Туда не пройти")
    path = map_path(state, (hero["x"], hero["y"]), (x, y))
    if not path or len(path) < 2:
        raise EngineError("Туда не пройти")
    steps = len(path) - 1
    if hero["moves"] <= 0:
        raise EngineError("Шаги на сегодня закончились — заверши день")
    if steps > hero["moves"]:
        # Too far for today: walk as far as the moves go, the rest of the way
        # waits for tomorrow (`goal`). The cells on the way are free ground.
        part = path[: hero["moves"] + 1]
        hero["moves"] = 0
        for cx, cy in part:
            reveal(state, cx, cy, VISION + hero.get("perk_vision", 0))
        hero["x"], hero["y"] = part[-1]
        hero["goal"] = [x, y]
        return
    hero["moves"] -= steps
    hero["goal"] = None
    for cx, cy in path:
        reveal(state, cx, cy, VISION + hero.get("perk_vision", 0))
    bot = state["bot"]
    if (x, y) == (bot["x"], bot["y"]):
        # Stand next to the rival and challenge it: the final battle.
        hero["x"], hero["y"] = path[-2]
        _start_final(state)
        return
    hero["x"], hero["y"] = x, y
    obj = _object_at(state, x, y)
    if obj is None:
        return
    kind = obj["kind"]
    if kind == "castle":
        if obj["owner"] == "bot":
            _start_final(state)
        return
    if kind == "camp":
        _start_camp(state, obj)
        return
    if kind == "market":
        _notice(state, "market", object_label(obj), "Наймите подкрепление за золото похода", object=obj["id"])
        return
    if kind == "medic":
        _use_medic(state, obj)
        return
    if kind == "tunnel":
        _use_tunnel(state, obj)
        return
    if kind == "mine":
        if obj.get("taken_by") == "me":
            return
        obj["taken_by"] = None  # a mine the rival held is retaken
        _apply_object(state, obj, "me")
        return
    if kind == "chest":
        obj["taken_by"] = "me"
        state["phase"] = "choice"
        state["pending"] = {"object": obj["id"], "options": [
            {"code": "gold", "gold": obj["gold"]},
            {"code": "xp", "xp": obj["gold"] // 10},
        ]}
        return
    _apply_object(state, obj, "me")


def choose(state: dict, code: str) -> None:
    """The chest's choice: gold for the market (and coins at the end) or the hero's experience."""
    if state["phase"] != "choice" or not state.get("pending"):
        raise EngineError("Выбирать нечего")
    opt = next((o for o in state["pending"]["options"] if o["code"] == code), None)
    if opt is None:
        raise EngineError("Нет такого варианта")
    if state["pending"].get("kind") == "perk":
        _take_perk(state, code)
        return
    obj = next(o for o in state["map"]["objects"] if o["id"] == state["pending"]["object"])
    hero = state["hero"]
    state["score"] += SCORE["chest"]
    state.setdefault("stats", {}).setdefault("chests", 0)
    state["stats"]["chests"] += 1
    if code == "gold":
        hero["gold"] += opt["gold"]
        text = f"+{opt['gold']} золота (всего {hero['gold']})"
    else:
        state["score"] += opt["xp"]
        text = f"+{opt['xp'] + SCORE['chest']} опыта героя"
    state["phase"] = "map"
    state["pending"] = None
    _log(state, "take", object=obj["id"], text=f"{object_label(obj)}: {text}")
    _notice(state, "chest", object_label(obj), text, gold=opt.get("gold") if code == "gold" else 0)
    _progress(state)


def buy(state: dict, object_id: str, index: int) -> None:
    """Hire one market offer for the run's gold; the hero must stand there."""
    if state["phase"] != "map":
        raise EngineError("Сейчас не до покупок")
    hero = state["hero"]
    obj = next((o for o in state["map"]["objects"] if o["id"] == object_id and o["kind"] == "market"), None)
    if obj is None or (obj["x"], obj["y"]) != (hero["x"], hero["y"]):
        raise EngineError("Встань на рынок, чтобы нанимать")
    if not (0 <= index < len(obj["offers"])):
        raise EngineError("Нет такого предложения")
    offer = obj["offers"][index]
    if offer["bought"]:
        raise EngineError("Этот отряд уже нанят")
    price = market_price(state, offer)
    if hero["gold"] < price:
        raise EngineError(f"Нужно {price} золота, у тебя {hero['gold']}")
    if not _add_stack(state, offer["unit"], offer["count"]):
        raise EngineError("В армии нет места: 6 отрядов, и такого существа среди них нет")
    hero["gold"] -= price
    offer["bought"] = True
    name = UNITS[offer["unit"]]["name"]
    _log(state, "buy", object=obj["id"], text=f"Нанят отряд: {name} ×{offer['count']}")
    _notice(state, "hired", "Отряд нанят", f"{name} ×{offer['count']} в армии", unit=offer["unit"])


def end_day(state: dict) -> None:
    if state["phase"] != "map":
        raise EngineError("Сначала закончи с тем, что открыто" if state["phase"] == "choice" else "Сейчас идёт бой")
    log_from = len(state["log"])
    _bot_day(state)
    if state["phase"] != "map":
        return
    if state["day"] >= state["days"]:
        _log(state, "final_call", text="Последний день прошёл — Безликий выходит из логова" if state["bot"].get("solo")
             else "Последний день прошёл — соперник вызывает на финальную битву")
        _start_final(state)
        return
    state["day"] += 1
    hero = state["hero"]
    hero["moves"] = state["moves_per_day"] + (2 if "boots" in hero["artifacts"] else 0)
    hero["mana"] = min(hero["max_mana"], hero["mana"] + 2)
    mines = sum(1 for o in state["map"]["objects"] if o["kind"] == "mine" and o.get("taken_by") == "me")
    event = _morning_event(state)
    lines = [e["text"] for e in state["log"][log_from:]]
    if event:
        icon, name, text = EVENTS[event]
        lines.insert(0, f"{icon} {name}: {text}")
    if mines:
        hero["gold"] += mines * MINE_GOLD
        lines.append(f"Шахты принесли +{mines * MINE_GOLD} золота")
    if state["bot"].get("solo"):
        # «Приключение»: a long road — every night the army heals a share of its fallen.
        back = 0
        for s in state["army"]:
            if s["count"] < s["max_count"]:
                add = min(s["max_count"] - s["count"], max(1, s["max_count"] * SOLO_REST_PCT // 100))
                s["count"] += add
                _own_back(state, s, add)
                back += add
        if back:
            lines.append(f"Привал: армия восполнила {back} бойцов")
    _log(state, "day", text=f"День {state['day']}")
    left = state["days"] - state["day"]
    title = f"День {state['day']} из {state['days']}"
    _notice(state, "day", title, "Последний день — потом финальная битва!" if left == 0 else
            f"До финальной битвы {left} {'день' if left == 1 else 'дня' if left < 5 else 'дней'}", lines=lines[:6],
            event=event)
    _progress(state)


def _bot_day(state: dict) -> None:
    """The rival walks to the most valuable object for the distance (camps
    up to its difficulty's strength) and takes it."""
    bot = state["bot"]
    if bot.get("solo"):
        return  # «Приключение»: no rival on the map
    moves = DIFFICULTY[state["difficulty"]]["moves"]
    if bot.pop("lost", False):
        moves = max(1, moves - 3)
    style = bot.get("style", "sly")
    bot["trail"] = [[bot["x"], bot["y"]]]  # where it walked tonight (drawn as footprints)
    max_camp = {"easy": 1, "normal": 2, "hard": 3}[state["difficulty"]] + (1 if style == "warrior" else 0)
    if style == "warrior" and _bot_hunts(state, moves):
        return
    while moves > 0:
        start = (bot["x"], bot["y"])
        tree = _bfs(state, start, "bot")
        best = None
        for o in state["map"]["objects"]:
            if o["kind"] in ("castle", "market", "floodtower", "medic", "tunnel", "shrine") or \
                    (o["kind"] == "camp" and o["level"] > max_camp):
                continue
            if o.get("taken_by") and not (o["kind"] == "mine" and o["taken_by"] == "me"):
                continue
            cell = (o["x"], o["y"])
            if cell not in tree["dist"] or cell == start:
                continue
            value = BOT_GAIN[o["kind"]][o["level"]] if o["kind"] == "camp" else BOT_GAIN[o["kind"]]
            if style == "greedy" and o["kind"] in ("chest", "mine", "well", "artifact"):
                value *= 2
            if style == "warrior" and o["kind"] == "camp":
                value *= 1.8
            score = value / (tree["dist"][cell] + 3)
            if best is None or score > best[0]:
                best = (score, o, cell)
        if best is None:
            return
        _, obj, cell = best
        path = _path_from(tree, cell)
        steps = len(path) - 1
        if steps > moves:
            bot["trail"] += [list(c) for c in path[1:moves + 1]]
            bot["x"], bot["y"] = path[moves]
            return
        moves -= steps
        bot["trail"] += [list(c) for c in path[1:]]
        bot["x"], bot["y"] = cell
        obj["taken_by"] = None
        _apply_object(state, obj, "bot")


# ---------------------------------------------------------------------------
# Battles
# ---------------------------------------------------------------------------

def camp_foes(state: dict, obj: dict, prefix: str = "e") -> list[dict]:
    target = state["start_power"] * CAMP_POWER[obj["level"]] / 100
    if obj.get("style") == "lost":
        codes = obj["lost"]
        return [make_stack(f"{prefix}{i}", c, max(1, round(target / len(codes) / unit_value(UNITS[c]))))
                for i, c in enumerate(codes, 1)]
    style = CAMP_STYLES[obj.get("style", "mixed")]
    return scaled_army(style["units"], obj["tiers"], target, prefix)


def boss_stack(state: dict, prefix: str = "e") -> dict:
    """Безликий: one figure with an army's health (`BOSS_HP_PCT`) and heavy hits."""
    p = state["start_power"]
    s = make_stack(f"{prefix}1", BOSS, 1)
    hit = p * BOSS_HIT_PERMILLE / 1000
    s["atk"] = s["def"] = BOSS_ATK
    s["dmin"], s["dmax"] = max(1, round(hit * 0.8)), max(2, round(hit * 1.2))
    s["hp"] = max(1, round(p * BOSS_HP_PCT[state["difficulty"]] / 100))
    s["boss"] = True
    return s


def _start_camp(state: dict, obj: dict) -> None:
    foes = camp_foes(state, obj)
    _start_battle(state, "camp", foes, obj_id=obj["id"], foe_name=object_label(obj), foe_hero=None)


def _start_final(state: dict) -> None:
    if not state.get("final_snapshot"):
        # What a second chance restores: the army and mana as they came to the final.
        state["final_snapshot"] = {"army": copy.deepcopy(state["army"]), "mana": state["hero"]["mana"],
                                   "fallen": dict(state.get("fallen") or {})}
    diff = DIFFICULTY[state["difficulty"]]
    if state["bot"].get("solo"):
        # «Приключение»: Безликий alone, with his own curse.
        foe_hero = {"faction": "lost", "mana": diff["mana"], "spell_power": diff["spell_power"],
                    "spells": ["curse"], "cast_round": 0}
        _start_battle(state, "final", [boss_stack(state)], obj_id=None, foe_name="Безликий", foe_hero=foe_hero)
        return
    pct = diff["power"] + state["bot"]["gain_pct"]
    target = state["start_power"] * pct / 100
    tiers = sorted({s["tier"] for s in state["army"] if s["card"]} or {1, 2, 3})
    while len(tiers) < 3:
        tiers.append(min(5, tiers[-1] + 1) if tiers[-1] < 5 else tiers[0])
    foes = scaled_army(FACTIONS[state["rival"]]["units"], tiers[:MAX_STACKS], target, "e")
    foe_hero = {"faction": state["rival"], "mana": diff["mana"], "spell_power": diff["spell_power"],
                "spells": FACTIONS[state["rival"]]["spells"], "cast_round": 0}
    name = f"Герой {FACTIONS[state['rival']]['name']}"
    _start_battle(state, "final", foes, obj_id=None, foe_name=name, foe_hero=foe_hero)


def _start_battle(state: dict, kind: str, foes: list[dict], *, obj_id: Optional[str], foe_name: str,
                  foe_hero: Optional[dict]) -> None:
    # Five stacks a row apart on the edge column; the guard / a hired stack stand behind, in between.
    rows = [4, 2, 6, 0, 8, 5, 3, 7, 1, 9]
    units = []
    for i, s in enumerate([s for s in state["army"] if s["count"] > 0]):
        u = dict(s, side="me", x=0 if i < 5 else 1, y=rows[i % len(rows)], start_count=s["count"], effects=[],
                 retaliated=0, reborn=False, defending=False)
        units.append(u)
    for i, s in enumerate(foes):
        units.append(dict(s, side="foe", x=FIELD_W - 1 if i < 5 else FIELD_W - 2, y=rows[i % len(rows)],
                          start_count=s["count"], effects=[], retaliated=0, reborn=False, defending=False))
    # A few obstacles in the middle of the pitch: cover and choke points. Football junk anywhere,
    # plus the biome's own hazard (a swamp, an ice patch, quicksand, a lava pool).
    r = rng(state)
    rocks: list = []
    obj = next((o for o in state.get("map", {}).get("objects", []) if o["id"] == obj_id), None) if obj_id else None
    lair = (obj or {}).get("style") == "lost" or (kind == "final" and state["bot"].get("solo"))
    biome = state.get("map", {}).get("biome", "meadow")
    hazards = LAIR_OBSTACLES if lair else [biome]
    for _ in range(r.randint(4, 7)):
        for _try in range(10):
            c = [r.randint(2, FIELD_W - 3), r.randrange(FIELD_H)]
            if c not in [o[:2] for o in rocks]:
                rocks.append(c + [r.choice(BATTLE_OBSTACLES + hazards * 3)])
                break
    state["phase"] = "battle"
    state["battle"] = {
        "kind": kind, "object": obj_id, "foe_name": foe_name, "units": units, "round": 1, "queue": [],
        "turn_of": None, "auto": False, "my_cast_round": 0, "foe_hero": foe_hero, "events": [], "n": 0,
        "winner": None, "rocks": rocks, "pitch": "lair" if lair else None,
    }
    _ev(state, "start", text=f"Бой: {foe_name}",
        units={u["id"]: [u["x"], u["y"], u["count"]] for u in units})
    _new_round(state)
    run_until_input(state)


def _ev(state: dict, kind: str, **data) -> None:
    b = state["battle"]
    b["n"] += 1
    b["events"].append({"n": b["n"], "kind": kind, **data})


def bunit(state: dict, uid: str) -> dict:
    for u in state["battle"]["units"]:
        if u["id"] == uid:
            return u
    raise EngineError("Нет такого отряда")


def _alive(state: dict, side: Optional[str] = None) -> list[dict]:
    return [u for u in state["battle"]["units"] if u["count"] > 0 and (side is None or u["side"] == side)]


def _home(u: dict) -> str:
    """The side a stack belongs to (a hypnotised one fights for the other side for a while)."""
    return u.get("orig_side", u["side"])


def _hypno_end(state: dict, u: dict) -> None:
    u["side"] = u.pop("orig_side")
    u["effects"] = [e for e in u["effects"] if e["code"] != "hypno"]
    _ev(state, "hypno_end", target=u["id"])


def _speed(state: dict, u: dict) -> int:
    flag = 1 if u["side"] == "me" and "flag" in state["hero"]["artifacts"] else 0
    return u["spd"] + flag


def _new_round(state: dict) -> None:
    b = state["battle"]
    for u in b["units"]:
        u["retaliated"] = 0
        u["defending"] = False
        u["effects"] = [dict(e, turns=e["turns"] - 1) for e in u["effects"] if e["turns"] > 1] if b["round"] > 1 else u["effects"]
        if "orig_side" in u and not _has_effect(u, "hypno"):
            _hypno_end(state, u)
    order = sorted(_alive(state), key=lambda u: (-_speed(state, u), u["side"] != "me", u["id"]))
    b["queue"] = [u["id"] for u in order]
    if b["foe_hero"] and b["foe_hero"]["cast_round"] < b["round"]:
        _ai_cast(state, "foe")
    if b["auto"] and b["my_cast_round"] < b["round"]:
        _ai_cast(state, "me")


def _dist(a: dict, x: int, y: int) -> int:
    return max(abs(a["x"] - x), abs(a["y"] - y))


def _occupied(state: dict, except_id: Optional[str] = None) -> set:
    rocks = {tuple(c[:2]) for c in state["battle"].get("rocks", [])}
    return {(u["x"], u["y"]) for u in _alive(state) if u["id"] != except_id} | rocks


def move_cells(state: dict, u: dict) -> dict:
    """{(x, y): steps} cells the stack can move to this turn (8-way steps;
    walkers go around stacks, fliers jump)."""
    occ = _occupied(state, u["id"])
    spd = _speed(state, u)
    if u["flying"]:
        return {(x, y): _dist(u, x, y) for x in range(FIELD_W) for y in range(FIELD_H)
                if (x, y) not in occ and 0 < _dist(u, x, y) <= spd}
    out = {}
    q = deque([((u["x"], u["y"]), 0)])
    seen = {(u["x"], u["y"])}
    while q:
        (cx, cy), d = q.popleft()
        if d == spd:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = cx + dx, cy + dy
                if (dx or dy) and 0 <= nx < FIELD_W and 0 <= ny < FIELD_H and (nx, ny) not in seen and (nx, ny) not in occ:
                    seen.add((nx, ny))
                    out[(nx, ny)] = d + 1
                    q.append(((nx, ny), d + 1))
    return out


def _adjacent_enemy(state: dict, u: dict) -> bool:
    return any(_dist(u, e["x"], e["y"]) == 1 for e in _alive(state, other(u["side"])))


def can_shoot(state: dict, u: dict) -> bool:
    return u["ranged"] and not _adjacent_enemy(state, u)


def attack_cells(state: dict, u: dict, target: dict) -> list[tuple]:
    """Cells from which `u` can hit `target` in melee this turn (current cell first)."""
    out = []
    if _dist(u, target["x"], target["y"]) == 1:
        out.append((u["x"], u["y"]))
    for (x, y), steps in sorted(move_cells(state, u).items(), key=lambda kv: kv[1]):
        if max(abs(x - target["x"]), abs(y - target["y"])) == 1:
            out.append((x, y))
    return out


def _has_effect(u: dict, code: str) -> bool:
    return any(e["code"] == code for e in u["effects"])


def _add_effect(u: dict, code: str, turns: int) -> None:
    u["effects"] = [e for e in u["effects"] if e["code"] != code] + [{"code": code, "turns": turns}]


def _damage(state: dict, att: dict, dfn: dict, *, ranged: bool, half: bool, r: random.Random) -> int:
    base = sum(r.randint(att["dmin"], att["dmax"]) for _ in range(min(att["count"], 10)))
    base = base * att["count"] / min(att["count"], 10)
    diff = att["atk"] - dfn["def"]
    mult = max(0.4, min(2.5, 1 + 0.05 * diff))
    dmg = base * mult
    if half:
        dmg *= 0.5
    if ranged and _dist(att, dfn["x"], dfn["y"]) > 4:
        dmg *= 0.75  # a long shot loses force
    if att["side"] == "me" and state["hero"].get("perk_atk"):
        dmg *= 1 + state["hero"]["perk_atk"] / 100
    if att["group"] == "att":
        dmg *= 1.12
    if att["side"] == "me" and "armband" in state["hero"]["artifacts"]:
        dmg *= 1.10
    if att["side"] == "me" and state["hero"].get("morale"):
        dmg *= 1 + state["hero"]["morale"] / 100
    if _has_effect(att, "bless"):
        dmg *= 1.30
    if _has_effect(att, "curse"):
        dmg *= 0.70
    if att["ability"] == "grief" and att.get("start_count"):
        dmg *= 1 + max(0.0, 1 - att["count"] / att["start_count"])
    dmg = _taken(state, dfn, dmg, magic=False, ranged=ranged)
    return max(1, round(dmg))


def _taken(state: dict, dfn: dict, dmg: float, *, magic: bool, ranged: bool) -> float:
    if dfn["group"] == "def":
        dmg *= 0.90
    if dfn["side"] == "me" and "shinguards" in state["hero"]["artifacts"]:
        dmg *= 0.90
    if dfn["side"] == "me" and state["hero"].get("perk_def"):
        dmg *= 1 - state["hero"]["perk_def"] / 100
    if _has_effect(dfn, "wall"):
        dmg *= 0.60
    if dfn.get("defending"):
        dmg *= 0.75
    if dfn["ability"] == "stone":
        dmg *= 0.75
    if dfn["ability"] == "shield" and (ranged or magic):
        dmg *= 0.50
    return dmg


def _apply_damage(state: dict, dfn: dict, dmg: int, source: str, kind: str) -> None:
    total = (dfn["count"] - 1) * dfn["hp"] + dfn.get("top_hp", dfn["hp"])
    total = max(0, total - dmg)
    before = dfn["count"]
    dfn["count"] = math.ceil(total / dfn["hp"]) if total > 0 else 0
    dfn["top_hp"] = total - (dfn["count"] - 1) * dfn["hp"] if dfn["count"] else 0
    killed = before - dfn["count"]
    _ev(state, kind, src=source, target=dfn["id"], damage=dmg, killed=killed, count=dfn["count"])
    if dfn["count"] == 0:
        if dfn["ability"] == "rebirth" and not dfn["reborn"]:
            dfn["reborn"] = True
            dfn["count"] = max(1, dfn["start_count"] // 2)
            dfn["top_hp"] = dfn["hp"]
            _ev(state, "rebirth", target=dfn["id"], count=dfn["count"])
        else:
            _ev(state, "down", target=dfn["id"])


def _heal(state: dict, u: dict, amount: int, source: str) -> None:
    cap = u["start_count"]
    total = (u["count"] - 1) * u["hp"] + u.get("top_hp", u["hp"]) if u["count"] else 0
    total = min(cap * u["hp"], total + amount)
    before = u["count"]
    u["count"] = math.ceil(total / u["hp"]) if total > 0 else 0
    u["top_hp"] = total - (u["count"] - 1) * u["hp"] if u["count"] else 0
    _ev(state, "heal", src=source, target=u["id"], amount=amount, raised=u["count"] - before, count=u["count"])


def chemistry(state: dict, side: str) -> int:
    """Club chemistry of a side: +4% luck and morale for every card that shares
    its club with another card of the army (capped at +20%)."""
    if side != "me":
        return 0
    clubs: dict = {}
    for s in state["army"]:
        club = (s.get("card") or {}).get("club")
        if club:
            clubs[club] = clubs.get(club, 0) + 1
    return min(20, 4 * sum(n for n in clubs.values() if n > 1))


def _luck(state: dict, u: dict) -> int:
    return BASE_LUCK + chemistry(state, u["side"]) + (state["hero"].get("perk_luck", 0) if u["side"] == "me" else 0)


def _strike(state: dict, att: dict, dfn: dict, *, ranged: bool) -> None:
    r = rng(state)
    half = not ranged and att["ranged"]  # a shooter in melee hits at half strength
    dmg = _damage(state, att, dfn, ranged=ranged, half=half, r=r)
    if r.randint(1, 100) <= _luck(state, att):
        dmg *= 2
        _ev(state, "lucky", src=att["id"], target=dfn["id"])
    elif att["ability"] == "sub" and not att.get("subbed"):
        att["subbed"] = True
        dmg *= 2
        _ev(state, "lucky", src=att["id"], target=dfn["id"])
    _apply_damage(state, dfn, dmg, att["id"], "shoot" if ranged else "hit")
    if att["ability"] == "drain" and dmg > 0:
        _heal(state, att, dmg // 2, att["id"])
    if att["ability"] == "cleave" and not ranged:
        for e in _alive(state, other(att["side"])):
            if e["id"] != dfn["id"] and _dist(att, e["x"], e["y"]) == 1:
                _apply_damage(state, e, max(1, dmg // 2), att["id"], "hit")
    if att["ability"] == "double" and not ranged and dfn["count"] > 0 and att["count"] > 0:
        again = _damage(state, att, dfn, ranged=False, half=False, r=rng(state))
        _apply_damage(state, dfn, again, att["id"], "hit")
    if att["ability"] in ("curse", "debt") and dfn["count"] > 0:
        _add_effect(dfn, "curse", 2)
        _ev(state, "effect", target=dfn["id"], effect="curse")
    if att["ability"] == "breath" and not ranged:
        bx = dfn["x"] + (1 if dfn["x"] > att["x"] else -1 if dfn["x"] < att["x"] else 0)
        by = dfn["y"] + (1 if dfn["y"] > att["y"] else -1 if dfn["y"] < att["y"] else 0)
        behind = next((u for u in _alive(state) if u["x"] == bx and u["y"] == by and u["id"] != att["id"]), None)
        if behind is not None and behind["side"] != att["side"]:
            _apply_damage(state, behind, max(1, dmg // 2), att["id"], "hit")
    if not ranged and dfn["count"] > 0 and att["count"] > 0 and att["ability"] not in ("charge", "hook"):
        limit = 99 if dfn["group"] == "gk" else 2 if dfn["ability"] == "guard" else 1
        if dfn["retaliated"] < limit:
            dfn["retaliated"] += 1
            r2 = rng(state)
            back = _damage(state, dfn, att, ranged=False, half=dfn["ranged"], r=r2)
            _apply_damage(state, att, back, dfn["id"], "retaliate")


def _after_turn(state: dict, u: dict) -> None:
    if u["ability"] == "mourn" and u["count"] > 0 and not u.get("mourned"):
        dead = [a for a in state["battle"]["units"] if a["count"] == 0 and _home(a) == _home(u) and a["id"] != u["id"]]
        if dead:
            a = max(dead, key=lambda a: a["start_count"] * unit_value(a))
            u["mourned"] = True
            a["count"] = max(1, a["start_count"] * 3 // 10)
            a["top_hp"] = a["hp"]
            _ev(state, "rebirth", target=a["id"], count=a["count"])
    if u["ability"] == "mend" and u["count"] > 0:
        for a in _alive(state, u["side"]):
            if a["id"] != u["id"] and _dist(u, a["x"], a["y"]) == 1 and (
                    a["count"] < a["start_count"] or a.get("top_hp", a["hp"]) < a["hp"]):
                _heal(state, a, u["count"] * 3, u["id"])
    if u["ability"] == "light" and u["count"] > 0:
        hurt = [a for a in _alive(state, u["side"]) if a["count"] < a["start_count"] or a.get("top_hp", a["hp"]) < a["hp"]]
        if hurt:
            t = max(hurt, key=lambda a: (a["start_count"] - a["count"]) * a["hp"])
            _heal(state, t, u["count"] * 4, u["id"])


def stack_act(state: dict, uid: str, action: str, target_id: Optional[str] = None,
              x: Optional[int] = None, y: Optional[int] = None) -> None:
    """One stack's turn: move | attack (move next to target and hit) | shoot | defend."""
    b = state["battle"]
    if b is None or state["phase"] != "battle":
        raise EngineError("Боя нет")
    if b["turn_of"] != uid:
        raise EngineError("Сейчас ходит другой отряд")
    u = bunit(state, uid)
    if action == "wait":
        # Step to the end of this round's queue (once a round).
        if u.get("waited") == b["round"]:
            raise EngineError("Этот отряд уже ждал в этом раунде")
        u["waited"] = b["round"]
        b["queue"] = [q for q in b["queue"] if q != uid] + [uid]
        b["turn_of"] = None
        _ev(state, "wait", src=uid)
        return
    if action == "defend":
        u["defending"] = True
        _ev(state, "defend", src=uid)
    elif action == "move":
        if x is None or y is None or (x, y) not in move_cells(state, u):
            raise EngineError("Туда не дойти")
        u["x"], u["y"] = x, y
        _ev(state, "move", src=uid, x=x, y=y)
    elif action in ("attack", "shoot"):
        if not target_id:
            raise EngineError("Выбери цель")
        t = bunit(state, target_id)
        if t["side"] == u["side"] or t["count"] <= 0:
            raise EngineError("Это не враг")
        if action == "shoot" or (u["ranged"] and can_shoot(state, u) and x is None):
            if not can_shoot(state, u):
                raise EngineError("Рядом враг — стрелять нельзя")
            _ev(state, "aim", src=uid, target=target_id)
            _strike(state, u, t, ranged=True)
        else:
            cells = attack_cells(state, u, t)
            if not cells:
                raise EngineError("До цели не дойти")
            cell = (x, y) if x is not None and y is not None else cells[0]
            if cell not in cells:
                raise EngineError("Оттуда не ударить")
            if cell != (u["x"], u["y"]):
                u["x"], u["y"] = cell
                _ev(state, "move", src=uid, x=cell[0], y=cell[1])
            _strike(state, u, t, ranged=False)
    else:
        raise EngineError("Неизвестное действие")
    _after_turn(state, u)
    b["queue"] = [q for q in b["queue"] if q != uid]
    b["turn_of"] = None
    _check_end(state)
    # High morale: sometimes a stack acts again at once (once a round).
    if (not b["winner"] and u["count"] > 0 and action != "defend" and u.get("morale_round") != b["round"]
            and rng(state).randint(1, 100) <= BASE_MORALE + chemistry(state, u["side"])):
        u["morale_round"] = b["round"]
        b["queue"].insert(0, uid)
        _ev(state, "morale", src=uid)


def cast(state: dict, side: str, spell: str, target_id: Optional[str]) -> None:
    b = state["battle"]
    if b is None or state["phase"] != "battle":
        raise EngineError("Боя нет")
    if side == "me":
        hero = state["hero"]
        if b["my_cast_round"] >= b["round"]:
            raise EngineError("Герой уже колдовал в этом раунде")
        if spell not in hero["spells"]:
            raise EngineError("Герой не знает этого заклинания")
        power = hero["spell_power"]
    else:
        hero = b["foe_hero"]
        power = hero["spell_power"]
    name, cost, target_kind, _ = SPELLS[spell]
    if hero["mana"] < cost:
        raise EngineError("Не хватает маны")
    targets = []
    if target_kind == "all_enemies":
        targets = _alive(state, other(side))
    else:
        if not target_id:
            raise EngineError("Выбери цель заклинания")
        t = bunit(state, target_id)
        if t["count"] <= 0 and spell != "raise":
            raise EngineError("Цель уже пала")
        if (target_kind == "ally") != (t["side"] == side):
            raise EngineError("Не та цель")
        targets = [t]
    hero["mana"] -= cost
    if side == "me":
        b["my_cast_round"] = b["round"]
    else:
        hero["cast_round"] = b["round"]
    _ev(state, "cast", side=side, spell=spell, name=name, targets=[t["id"] for t in targets])
    for t in targets:
        if spell in ("bless", "wall", "curse"):
            _add_effect(t, spell, 3)  # this round + 2 more
            _ev(state, "effect", target=t["id"], effect=spell)
        elif spell == "raise":
            _heal(state, t, 30 + 20 * power, "hero")
        elif spell == "sunstrike":
            _apply_damage(state, t, max(1, round(_taken(state, t, 25 + 15 * power, magic=True, ranged=False))), "hero", "spell")
        elif spell == "firerain":
            _apply_damage(state, t, max(1, round(_taken(state, t, 12 + 8 * power, magic=True, ranged=False))), "hero", "spell")
    _check_end(state)


def _ai_cast(state: dict, side: str) -> None:
    b = state["battle"]
    hero = state["hero"] if side == "me" else b["foe_hero"]
    spells = hero["spells"]
    allies, enemies = _alive(state, side), _alive(state, other(side))
    if not allies or not enemies:
        return
    for spell in sorted(spells, key=lambda s: -SPELLS[s][1]):
        name, cost, kind, _ = SPELLS[spell]
        if hero["mana"] < cost:
            continue
        target = None
        if spell == "raise":
            hurt = [a for a in allies if a["count"] < a["start_count"] * 0.7]
            if not hurt:
                continue
            target = max(hurt, key=lambda a: (a["start_count"] - a["count"]) * a["hp"])["id"]
        elif spell == "firerain":
            if len(enemies) < 2:
                continue
        elif kind == "ally":
            target = max(allies, key=stack_power)["id"]
        else:
            target = max(enemies, key=stack_power)["id"]
        try:
            cast(state, side, spell, target)
        except EngineError:
            continue
        return


def _ai_turn(state: dict, u: dict) -> None:
    """Shoot the most valuable target, else hit what it can reach, else walk on."""
    enemies = _alive(state, other(u["side"]))
    b = state["battle"]
    if not enemies:
        # Only hypnotised stacks are left on the other side: the spell breaks, the turn passes.
        for e in b["units"]:
            if "orig_side" in e:
                _hypno_end(state, e)
        b["queue"] = [q for q in b["queue"] if q != u["id"]]
        b["turn_of"] = None
        return
    if u["ability"] == "hypno" and b["round"] % 4 == 1 and not any("orig_side" in e for e in b["units"]):
        # Безликий: the strongest of the enemy's stacks fights for him this round and the next two (every 4th round).
        free = [e for e in enemies if "orig_side" not in e]
        if len(free) >= 2 and state["hero"].get("ward") and free[0]["side"] == "me":
            # «Святилище Гильдии»: the ward takes the first hypnosis and breaks.
            state["hero"]["ward"] -= 1
            _ev(state, "ward", src=u["id"], target=max(free, key=stack_power)["id"])
            b["queue"] = [q for q in b["queue"] if q != u["id"]]
            b["turn_of"] = None
            return
        if len(free) >= 2:
            t = max(free, key=stack_power)
            t["orig_side"] = t["side"]
            t["side"] = u["side"]
            _add_effect(t, "hypno", 3)
            _ev(state, "hypno", src=u["id"], target=t["id"])
            b["queue"] = [q for q in b["queue"] if q != u["id"]]
            b["turn_of"] = None
            _check_end(state)
            return
    if u["ability"] == "hook" and not _adjacent_enemy(state, u):
        # The chain: pull the nearest enemy within 4 cells next to itself, then hit it.
        busy = _occupied(state)
        rocks = {tuple(o[:2]) for o in b.get("rocks") or []}
        free_cells = [(u["x"] + dx, u["y"] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        free_cells = [c for c in free_cells if 0 <= c[0] < FIELD_W and 0 <= c[1] < FIELD_H and c not in busy and c not in rocks]
        near = [e for e in enemies if _dist(u, e["x"], e["y"]) <= 4]
        if near and free_cells:
            t = min(near, key=lambda e: _dist(u, e["x"], e["y"]))
            cell = min(free_cells, key=lambda c: max(abs(c[0] - t["x"]), abs(c[1] - t["y"])))
            t["x"], t["y"] = cell
            _ev(state, "move", src=t["id"], x=cell[0], y=cell[1])
            _ev(state, "hook", src=u["id"], target=t["id"])
            stack_act(state, u["id"], "attack", t["id"], u["x"], u["y"])
            return
    value = lambda e: stack_power(e) / max(1, e["count"]) * min(e["count"], 1 + u["count"])  # noqa: E731
    if can_shoot(state, u):
        t = max(enemies, key=value)
        stack_act(state, u["id"], "shoot", t["id"])
        return
    reach = [(e, attack_cells(state, u, e)) for e in enemies]
    reach = [(e, c) for e, c in reach if c]
    if reach:
        e, cells = max(reach, key=lambda ec: value(ec[0]))
        stack_act(state, u["id"], "attack", e["id"], *cells[0])
        return
    cells = move_cells(state, u)
    if not cells:
        stack_act(state, u["id"], "defend")
        return
    nearest = min(enemies, key=lambda e: _dist(u, e["x"], e["y"]))
    best = min(cells, key=lambda c: (max(abs(c[0] - nearest["x"]), abs(c[1] - nearest["y"])), cells[c]))
    stack_act(state, u["id"], "move", None, *best)


def _check_end(state: dict) -> None:
    b = state["battle"]
    if b["winner"]:
        return
    home = lambda side: [u for u in _alive(state) if _home(u) == side]  # noqa: E731
    if not home("foe"):
        b["winner"] = "me"
    elif not home("me"):
        b["winner"] = "foe"
    if b["winner"]:
        for u in b["units"]:
            if "orig_side" in u:
                _hypno_end(state, u)
    elif b["round"] > MAX_ROUNDS:
        b["winner"] = "foe"


def run_until_input(state: dict) -> None:
    """Plays every turn that doesn't need the player; stops at the player's
    stack (manual) or when the battle is over (then resolves it)."""
    b = state["battle"]
    guard = 0
    while b and not b["winner"]:
        guard += 1
        if guard > 2000:
            b["winner"] = "foe"
            break
        b["queue"] = [q for q in b["queue"] if bunit(state, q)["count"] > 0]
        if not b["queue"]:
            b["round"] += 1
            if b["round"] > MAX_ROUNDS:
                _check_end(state)
                break
            _ev(state, "round", round=b["round"])
            _new_round(state)
            continue
        u = bunit(state, b["queue"][0])
        b["turn_of"] = u["id"]
        if u["side"] == "me" and not b["auto"]:
            return
        _ai_turn(state, u)
    if b and b["winner"]:
        _resolve_battle(state)


def set_auto(state: dict) -> None:
    b = state["battle"]
    if b is None:
        raise EngineError("Боя нет")
    b["auto"] = True
    if b["my_cast_round"] < b["round"]:
        _ai_cast(state, "me")
    run_until_input(state)


# ---------------------------------------------------------------------------
# Losses: what a run takes from the collection
# ---------------------------------------------------------------------------

# Essence for one fallen fighter of each tier (a card of tier I = 10 fighters = 10 essence).
ESSENCE = {1: 1, 2: 2, 3: 5, 4: 15, 5: 100}
# Of the fallen, this % dies for good (the rest come back wounded); hardcore: everyone.
DEAD_PCT = {"quick": 50, "hardcore": 100, "adventure": 50}


def _own_lost(state: dict, s: dict, lost: int) -> None:
    """`lost` fighters of stack `s` fell: hired ones first, then the collection's own."""
    if "own" not in s or lost <= 0:
        return
    hired = max(0, s["count"] - s["own"])
    own = min(s["own"], max(0, lost - hired))
    if own:
        s["own"] -= own
        fallen = state.setdefault("fallen", {})
        fallen[s["unit"]] = fallen.get(s["unit"], 0) + own


def _own_back(state: dict, s: dict, back: int) -> None:
    """A refill: the collection's own fallen fighters of `s` return first."""
    if "own" not in s or back <= 0:
        return
    fallen = state.setdefault("fallen", {})
    n = min(back, s["own0"] - s["own"], fallen.get(s["unit"], 0))
    if n > 0:
        s["own"] += n
        fallen[s["unit"]] -= n


def casualties(state: dict) -> dict:
    """The fallen of the run split into the dead (gone, essence) and the wounded (back later)."""
    pct = DEAD_PCT.get(state.get("mode", "quick"), 50)
    dead, wounded, essence = {}, {}, 0
    for unit, n in sorted((state.get("fallen") or {}).items()):
        if n <= 0 or unit not in UNITS or unit in GUARD_CODES:
            continue
        d = n if pct >= 100 else n - n * (100 - pct) // 100
        if d:
            dead[unit] = d
            essence += d * ESSENCE[UNITS[unit]["tier"]]
        if n - d:
            wounded[unit] = n - d
    if state.get("mode") == "hardcore":
        essence *= 2
    g = sum(v for k, v in (state.get("fallen") or {}).items() if k in GUARD_CODES)
    guard_lost = g if pct >= 100 else g - g * (100 - pct) // 100
    return {"dead": dead, "wounded": wounded, "essence": essence, "guard_lost": max(0, guard_lost)}


def _resolve_battle(state: dict) -> None:
    b = state["battle"]
    won = b["winner"] == "me"
    b["turn_of"] = None
    survivors = {u["id"]: u for u in b["units"] if _home(u) == "me"}
    losses = 0
    for s in state["army"]:
        u = survivors.get(s["id"])
        if u is None:
            continue
        lost = max(0, u["start_count"] - u["count"])
        count = u["count"]
        if s["ability"] == "undead" and lost and count > 0:
            back = lost // 3
            count += back
        losses += max(0, s["count"] - count)
        new = min(s["max_count"], count)
        if new < s["count"]:
            _own_lost(state, s, s["count"] - new)
        elif new > s["count"]:
            _own_back(state, s, new - s["count"])
        s["count"] = new
    state["army"] = [s for s in state["army"] if s["count"] > 0]
    b["result"] = {"won": won, "losses": losses}
    _ev(state, "end", winner=b["winner"])
    if b["kind"] == "final":
        if not won and not state.get("retry_used") and not state.get("forfeit"):
            # Lost the final: the service may sell one second chance (retry_final) — or accept_defeat.
            state["phase"] = "final_lost"
            _log(state, "final", won=False, text="Поражение в финальной битве")
            return
        state["phase"] = "finished"
        state["finished"] = True
        state["winner"] = "me" if won else "bot"
        if won:
            state["score"] += SCORE["boss" if state["bot"].get("solo") else "final"]
            state["battles_won"] += 1
        _log(state, "final", won=won, text=("Безликий повержен!" if state["bot"].get("solo") else "Победа в финальной битве!")
             if won else "Поражение в финальной битве")
        return
    if won:
        state["battles_won"] += 1
        obj = next(o for o in state["map"]["objects"] if o["id"] == b["object"])
        stats = state.setdefault("stats", {"chests": 0, "camps": 0, "strong_day": None})
        stats["camps"] = stats.get("camps", 0) + 1
        if obj.get("level") == 3 and not stats.get("strong_day"):
            stats["strong_day"] = state["day"]
        _apply_object(state, obj, "me")
        state["phase"] = "battle_over"
        return
    # The camp beat the whole army — the run is lost.
    state["phase"] = "finished"
    state["finished"] = True
    state["winner"] = "bot"
    _log(state, "camp_lost", text="Армия пала в бою с лагерем")


def leave_battle(state: dict) -> None:
    """Back to the map after a won camp battle (the result screen is shown first)."""
    if state["phase"] != "battle_over":
        raise EngineError("Бой ещё идёт")
    state["phase"] = "map"
    state["battle"] = None
    if not state["army"]:
        state["phase"] = "finished"
        state["finished"] = True
        state["winner"] = "bot"
        return
    _progress(state)


def retry_final(state: dict) -> None:
    """The second chance: the final again, with the army and mana it came with."""
    if state["phase"] != "final_lost":
        raise EngineError("Переиграть можно только проигранный финал")
    snap = state["final_snapshot"]
    state["army"] = copy.deepcopy(snap["army"])
    state["hero"]["mana"] = snap["mana"]
    state["fallen"] = dict(snap.get("fallen") or {})
    state["retry_used"] = True
    state["battle"] = None
    state["phase"] = "map"
    _log(state, "retry", text="Второй шанс: финальная битва заново")
    _start_final(state)


def accept_defeat(state: dict) -> None:
    if state["phase"] != "final_lost":
        raise EngineError("Поход ещё не проигран")
    state["phase"] = "finished"
    state["finished"] = True
    state["winner"] = "bot"


def forfeit(state: dict) -> None:
    b = state.get("battle")
    if b and state["phase"] == "battle":
        on_field = {u["id"] for u in b["units"] if _home(u) == "me"}
        for s in state["army"]:
            if s["id"] in on_field and s["count"] > 0:
                _own_lost(state, s, s["count"])
                s["count"] = 0
        state["army"] = [s for s in state["army"] if s["count"] > 0]
    state["phase"] = "finished"
    state["finished"] = True
    state["winner"] = "bot"
    state["forfeit"] = True
    if state.get("battle"):
        state["battle"]["winner"] = state["battle"].get("winner") or "foe"
