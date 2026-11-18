"""«Моя вилла»: the player's own plot in his town, laid out as he likes.

The plot is the meadow of the plot picture cut into isometric cells
(town_villa_plot.CELLS, centre first): a villa level opens the first
cells_<level> of them, so the plot grows outwards in a round shape that
follows the meadow. A layout that no longer fits (the admin shrank the
plot) is repaired on the next look: what is outside goes to storage, the
villa and the garage move to a free spot. On it stand the villa itself (5 levels), the garage (0–3
levels, garage_slots_<level> cars) and whatever the player bought: cars and
yard things for coins (`coins_<code>`) or for Telegram Stars (`stars_<code>`,
the premium ones; `supply_<code>` > 0 makes an item limited, every copy
numbered). Bought things land in storage; the player places them on free
cells, turns them (w and h swapped) or puts them back (PUT layout — the whole
result is checked: owned, inside the grid, no overlaps, the villa and the
garage always stand).

«Персонал»: residents the player holds work at the villa, one a post, each
post takes residents of its professions (POSTS, matched on the title).

«Престиж» = villa level × prestige_villa_level + garage level ×
prestige_garage_level + every kind of thing owned once × prestige_<code> +
working staff × prestige_staff + every combo × prestige_combo. A post
works only while its workplace stands on the plot (POST_WORKPLACE: the
garage for the mechanic, the pool for the lifeguard…; security and the
concierge always). A combo (COMBOS) is two things standing side by side
(their footprints touch, diagonals too) — each combo counts once. So the
layout itself moves the prestige: save_layout settles the rent first.
Every prestige_per_pct of it adds 1 % to the rent of
the town's houses, at most prestige_max_pct (town_service._income_parts) —
so the rent so far is settled before the prestige changes.

The chosen car (`car_item_id`) drives on the owner's town map. Guests see
the villa (town_social_service visits) and like it once a day
(town_visits.villa_liked); «Вилла недели» ranks villas by those likes (guests
older than town_social.week_min_account_days only) and pays
villa_week_reward_1..3 once a week — settled lazily by the first reader
under a town_weeks row keyed "V" + the ISO week.

In the game (PERKS): a building on the plot gives one perk — once, however
many buildings of that perk stand (two pitches are still one extra
training): ⚽ a pitch → +1 free «Мой игрок» training a day
(my_players.villa_training_day), 🩺 the tennis court / the stable → the
«Менеджер» club's injuries are treated perk_treat_pct cheaper, 🚁 the
helipad / the guest garage → its tours cost perk_tour_pct less (both go
into manager_service.base_snapshot, frozen with the season like the rest
of it), 🏆 the trophy pavilion → guests see the owner's trophies.
The villa pays its income once a local day: income_base + prestige ×
income_per_100 / 100, at most income_cap (user_town_villas.income_day).
Once a week the owner throws a party (party_cost coins, party_hours):
a guest liking the villa then gets party_guest_coins, for at most
party_guest_per_day parties a day (town_visits.party_coins).
«Вилла месяца» ranks villas by prestige + the month's likes ×
month_like_points and pays month_reward_1..3, settled like the week under
"VM" + the month; the prestige is the one last shown to the owner
(user_town_villas.prestige).
"""
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.enums import TransactionType
from app.models.town import (
    TownLedger, TownResident, TownVisit, TownWeek, TownWeekResult, UserTown, UserTownResident, UserTownVilla,
    UserTownVillaItem,
)
from app.models.user import User
from app.services import town_service
from app.services.town_villa_plot import CELL_COUNT, CELLS
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

STARS_PREFIX = "town:villa:"
MAX_VILLA_LEVEL = 5
MAX_GARAGE_LEVEL = 3
VILLA_SIZE = (4, 4)
GARAGE_SIZE = (2, 2)

# code -> (name, emoji, kind, w, h). kind: car | yard | premium.
ITEMS: dict[str, tuple[str, str, str, int, int]] = {
    "car_hatch": ("Городской хэтчбек", "🚗", "car", 1, 2),
    "car_jeep": ("Открытый джип", "🚙", "car", 1, 2),
    "car_van": ("Фургон сёрфера", "🚐", "car", 1, 2),
    "car_cabrio": ("Кабриолет 60-х", "🚘", "car", 1, 2),
    "car_sport": ("Суперкар", "🏎️", "car", 1, 2),
    "car_bus": ("Автобус команды", "🚌", "car", 1, 2),
    "car_classic": ("Золотой родстер", "🏁", "car", 1, 2),
    "pool": ("Бассейн", "🏊", "yard", 3, 2),
    "pitch_mini": ("Мини-поле", "⚽", "yard", 4, 4),
    "goal_practice": ("Ворота для тренировки", "🥅", "yard", 1, 1),
    "gazebo_bbq": ("Беседка с грилем", "🍖", "yard", 2, 2),
    "palm": ("Пальма", "🌴", "yard", 1, 1),
    "olive": ("Оливковое дерево", "🫒", "yard", 1, 1),
    "cypress": ("Кипарис", "🌲", "yard", 1, 1),
    "flowers": ("Клумба", "💐", "yard", 1, 1),
    "hedge": ("Живая изгородь", "🌿", "yard", 1, 1),
    "lamp": ("Фонарь", "🏮", "yard", 1, 1),
    "bench": ("Скамейка", "🪑", "yard", 1, 1),
    "path": ("Дорожка", "▫️", "yard", 1, 1),
    "path_gravel": ("Гравийная дорожка", "🪨", "yard", 1, 1),
    "path_terracotta": ("Терракотовая плитка", "🟧", "yard", 1, 1),
    "path_deck": ("Деревянный настил", "🪵", "yard", 1, 1),
    "path_stepping": ("Камни в траве", "🌿", "yard", 1, 1),
    "sun_umbrella": ("Зонт с шезлонгом", "⛱️", "yard", 1, 1),
    "pitch_five": ("Поле для пятёрок", "🏟️", "yard", 3, 6),
    "pergola_bbq": ("Летняя кухня", "🥩", "yard", 2, 2),
    "pizza_oven": ("Печь для пиццы", "🍕", "yard", 1, 1),
    "garage_guest": ("Гостевой гараж", "🏠", "yard", 2, 2),
    "fence_stone": ("Каменная ограда", "🧱", "yard", 1, 1),
    "fence_iron": ("Кованая ограда", "⚜️", "yard", 1, 1),
    "fence_hedge": ("Изгородь-ограда", "🌳", "yard", 1, 1),
    "fence_picket": ("Белый заборчик", "🤍", "yard", 1, 1),
    "chicken_coop": ("Курятник", "🐔", "yard", 2, 2),
    "staff_house": ("Домик персонала", "🏡", "yard", 3, 2),
    "dog_kennel": ("Будка с собакой", "🐕", "yard", 1, 1),
    "greenhouse": ("Оранжерея", "🪴", "yard", 2, 2),
    "vegetable_garden": ("Огород", "🥕", "yard", 2, 2),
    "stable": ("Конюшня", "🐴", "yard", 3, 2),
    "tennis_court": ("Теннисный корт", "🎾", "yard", 3, 5),
    "treehouse": ("Домик на дереве", "🌳", "yard", 2, 2),
    "flamingo_pond": ("Пруд с фламинго", "🦩", "premium", 2, 2),
    "beehive": ("Пасека", "🐝", "yard", 1, 1),
    "hammock": ("Гамак между пальмами", "🏖️", "yard", 2, 1),
    "basketball_hoop": ("Баскетбольное кольцо", "🏀", "yard", 1, 1),
    "fountain_ball": ("Фонтан с золотым мячом", "⛲", "premium", 2, 2),
    "statue_gold": ("Золотая статуя", "🏆", "premium", 1, 1),
    "trophy_pavilion": ("Павильон трофеев", "🏛️", "premium", 2, 2),
    "helipad": ("Вертолётная площадка", "🚁", "premium", 3, 3),
    "firepit": ("Лаунж с камином", "🔥", "premium", 2, 2),
    "patio_pool": ("Патио с бассейном", "🏝️", "premium", 4, 4),
    "lion_enclosure": ("Вольер со львом", "🦁", "premium", 3, 3),
}
# What the villa gives in the game: perk -> (name, emoji, buildings). A perk counts once, however
# many of its buildings stand on the plot (in storage they give nothing).
PERKS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "training": ("Своё поле", "⚽", ("pitch_mini", "pitch_five")),
    "recovery": ("Восстановление", "🩺", ("tennis_court", "stable")),
    "travel": ("Свой транспорт", "🚁", ("helipad", "garage_guest")),
    "trophies": ("Витрина трофеев", "🏆", ("trophy_pavilion",)),
}
# Fence sections join their neighbours of the same fence; rot = 1 makes a section a gate.
FENCES = ("fence_stone", "fence_iron", "fence_hedge", "fence_picket")
# Flat path tiles of every kind (the frontend joins tiles of the same kind).
PATHS = ("path", "path_gravel", "path_terracotta", "path_deck", "path_stepping")
# One copy at most: cars and premium things (yard things — as many as fit).
_SINGLE_KINDS = ("car", "premium")

# post -> (name, emoji, title keywords)
POSTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "security": ("Охрана", "🛡️", ("полиц", "охран", "кинолог", "боксёр", "карате", "капоэйр", "спецназ", "солдат", "стронгмен")),
    "garden": ("Сад и газон", "🌱", ("газон", "смотритель поля", "флорист", "цвет", "садов", "агроном")),
    "garage": ("Гараж", "🔧", ("механик", "таксист", "водител", "трамвай", "инженер", "курьер")),
    "kitchen": ("Кухня и бар", "🍹", ("повар", "бармен", "бариста", "мороженщ", "пекар", "лавк", "кондитер")),
    "party": ("Вечеринки", "🎧", ("диджей", "певиц", "танцов", "барабан", "киномеханик")),
    "health": ("Здоровье", "🩺", ("фельдшер", "ветеринар", "массаж", "врач")),
    "pool": ("Бассейн и пляж", "🛟", ("спасател", "сёрф", "парус", "водолаз")),
    "concierge": ("Дворецкий", "🎩", ("консьерж", "отел", "экскурсовод", "стюардесс", "помощниц")),
}

# post -> things any one of which on the plot makes it work (empty = always works)
POST_WORKPLACE: dict[str, tuple[str, ...]] = {
    "security": (), "concierge": (),
    "garden": ("palm", "olive", "cypress", "flowers", "hedge", "greenhouse", "vegetable_garden", "beehive"),
    "garage": ("garage", "garage_guest"),
    "kitchen": ("gazebo_bbq", "pergola_bbq", "pizza_oven"),
    "party": ("firepit", "gazebo_bbq", "pergola_bbq"),
    "health": ("pool", "pitch_mini", "pitch_five", "patio_pool", "tennis_court", "stable", "lion_enclosure"),
    "pool": ("pool", "patio_pool"),
}

# (a, b, name, emoji): a and b standing side by side
COMBOS: tuple[tuple[str, str, str, str], ...] = (
    ("pool", "sun_umbrella", "Пляж у бассейна", "🏖️"),
    ("pool", "palm", "Тропики", "🌴"),
    ("gazebo_bbq", "lamp", "Вечер у гриля", "🍖"),
    ("bench", "flowers", "Тихий уголок", "🌸"),
    ("goal_practice", "pitch_mini", "Тренировочная база", "⚽"),
    ("garage", "path", "Подъезд к гаражу", "🛣️"),
    ("villa", "fountain_ball", "Парадный вход", "⛲"),
    ("firepit", "olive", "Средиземноморский вечер", "🔥"),
    ("statue_gold", "hedge", "Аллея славы", "🗿"),
    ("helipad", "lamp", "Ночная посадка", "🚁"),
    ("trophy_pavilion", "flowers", "Зал трофеев", "🏆"),
    ("villa", "pool", "Бассейн у дома", "🏊"),
    ("pizza_oven", "pergola_bbq", "Итальянский вечер", "🍕"),
    ("pitch_five", "goal_practice", "Своя пятёрка", "⚽"),
    ("patio_pool", "palm", "Курорт", "🏝️"),
    ("villa", "fence_iron", "Кованые ворота", "⚜️"),
    ("garage_guest", "path", "Гостевая парковка", "🅿️"),
    ("chicken_coop", "vegetable_garden", "Своя ферма", "🐔"),
    ("greenhouse", "beehive", "Сад и пасека", "🐝"),
    ("hammock", "palm", "Сиеста", "🌴"),
    ("villa", "dog_kennel", "Верный сторож", "🐕"),
    ("tennis_court", "bench", "Свой Уимблдон", "🎾"),
    ("flamingo_pond", "flowers", "Розовый сад", "🦩"),
    ("lion_enclosure", "statue_gold", "Царь зверей", "🦁"),
    ("stable", "fence_picket", "Конный двор", "🐴"),
    ("staff_house", "path", "Служебный вход", "🏡"),
    ("basketball_hoop", "pitch_mini", "Спортгородок", "🏀"),
)

VILLA_DEFAULTS: dict[str, int] = {
    "villa_price_2": 15000, "villa_price_3": 40000, "villa_price_4": 90000, "villa_price_5": 180000,
    # meadow cells open at a villa level (the plot's centre first; at most all of them)
    "cells_1": 140, "cells_2": 220, "cells_3": 320, "cells_4": 460, "cells_5": 700,
    "garage_price_1": 8000, "garage_price_2": 25000, "garage_price_3": 60000,
    "garage_slots_1": 1, "garage_slots_2": 3, "garage_slots_3": 6,
    "prestige_villa_level": 20, "prestige_garage_level": 10, "prestige_staff": 15, "prestige_combo": 5,
    "prestige_per_pct": 60, "prestige_max_pct": 5,
    "max_items": 250,  # paths and fence sections are things too: a full plot needs room
    "villa_week_reward_1": 2000, "villa_week_reward_2": 1000, "villa_week_reward_3": 500,
    # the villa in the game: one perk per kind of building (PERKS)
    "perk_training": 1,  # extra free «Мой игрок» trainings a day with a pitch on the plot (0 = off)
    "perk_treat_pct": 30, "perk_tour_pct": 20,
    "income_base": 20, "income_per_100": 20, "income_cap": 200,
    "party_cost": 1000, "party_hours": 24, "party_guest_coins": 30, "party_guest_per_day": 3,
    "month_like_points": 10,
    "month_reward_1": 10000, "month_reward_2": 5000, "month_reward_3": 2500,
    # cars
    "coins_car_hatch": 3000, "prestige_car_hatch": 5,
    "coins_car_jeep": 6000, "prestige_car_jeep": 8,
    "coins_car_van": 9000, "prestige_car_van": 10,
    "coins_car_cabrio": 12000, "prestige_car_cabrio": 12,
    "stars_car_sport": 99, "prestige_car_sport": 25,
    "stars_car_bus": 149, "prestige_car_bus": 30,
    "stars_car_classic": 249, "prestige_car_classic": 40, "supply_car_classic": 300,
    # yard
    "coins_pool": 15000, "prestige_pool": 20,
    "coins_pitch_mini": 20000, "prestige_pitch_mini": 25,
    "coins_goal_practice": 2500, "prestige_goal_practice": 4,
    "coins_gazebo_bbq": 8000, "prestige_gazebo_bbq": 10,
    "coins_palm": 600, "prestige_palm": 1,
    "coins_olive": 800, "prestige_olive": 1,
    "coins_cypress": 600, "prestige_cypress": 1,
    "coins_flowers": 400, "prestige_flowers": 1,
    "coins_hedge": 300, "prestige_hedge": 1,
    "coins_lamp": 500, "prestige_lamp": 1,
    "coins_bench": 400, "prestige_bench": 1,
    "coins_path": 100, "prestige_path": 0,
    "coins_path_gravel": 80, "prestige_path_gravel": 0,
    "coins_path_terracotta": 150, "prestige_path_terracotta": 0,
    "coins_path_deck": 150, "prestige_path_deck": 0,
    "coins_path_stepping": 120, "prestige_path_stepping": 0,
    "coins_sun_umbrella": 700, "prestige_sun_umbrella": 1,
    "coins_pitch_five": 30000, "prestige_pitch_five": 30,
    "coins_pergola_bbq": 9000, "prestige_pergola_bbq": 11,
    "coins_pizza_oven": 3500, "prestige_pizza_oven": 4,
    "coins_garage_guest": 12000, "prestige_garage_guest": 8,
    "coins_fence_stone": 150, "prestige_fence_stone": 0,
    "coins_fence_iron": 250, "prestige_fence_iron": 0,
    "coins_fence_hedge": 120, "prestige_fence_hedge": 0,
    "coins_fence_picket": 100, "prestige_fence_picket": 0,
    "coins_chicken_coop": 4000, "prestige_chicken_coop": 5,
    "coins_staff_house": 10000, "prestige_staff_house": 10,
    "coins_dog_kennel": 1500, "prestige_dog_kennel": 2,
    "coins_greenhouse": 7000, "prestige_greenhouse": 8,
    "coins_vegetable_garden": 3000, "prestige_vegetable_garden": 4,
    "coins_stable": 18000, "prestige_stable": 18,
    "coins_tennis_court": 25000, "prestige_tennis_court": 25,
    "coins_treehouse": 6000, "prestige_treehouse": 7,
    "coins_beehive": 1200, "prestige_beehive": 2,
    "coins_hammock": 1500, "prestige_hammock": 2,
    "coins_basketball_hoop": 2000, "prestige_basketball_hoop": 3,
    # premium
    "stars_fountain_ball": 250, "prestige_fountain_ball": 25,
    "stars_statue_gold": 150, "prestige_statue_gold": 20,
    "stars_trophy_pavilion": 300, "prestige_trophy_pavilion": 30,
    "stars_helipad": 600, "prestige_helipad": 45,
    "stars_firepit": 200, "prestige_firepit": 15,
    "stars_patio_pool": 400, "prestige_patio_pool": 35,
    "stars_lion_enclosure": 500, "prestige_lion_enclosure": 40,
    "stars_flamingo_pond": 300, "prestige_flamingo_pond": 30,
    # copies of a Stars item sold at most, each numbered (0 = no limit, no numbers)
    "supply_car_sport": 0, "supply_car_bus": 0, "supply_fountain_ball": 0, "supply_statue_gold": 0,
    "supply_trophy_pavilion": 0, "supply_helipad": 0, "supply_firepit": 0,
    "supply_patio_pool": 0, "supply_lion_enclosure": 0, "supply_flamingo_pond": 0,
}


def villa_config(config) -> dict[str, int]:
    stored = getattr(config, "town_villa", None) or {}
    out = dict(VILLA_DEFAULTS)
    for key, value in stored.items():
        if key in VILLA_DEFAULTS and isinstance(value, int) and not isinstance(value, bool):
            out[key] = max(0, value)
    for level in range(1, MAX_VILLA_LEVEL + 1):  # the plot never shrinks and always holds the villa and the garage
        floor = out[f"cells_{level - 1}"] if level > 1 else 40
        out[f"cells_{level}"] = min(CELL_COUNT, max(floor, out[f"cells_{level}"]))
    out["prestige_per_pct"] = max(1, out["prestige_per_pct"])
    return out


def validate_villa(raw: dict) -> dict:
    out: dict = {}
    for key, value in (raw or {}).items():
        if key not in VILLA_DEFAULTS:
            raise ValueError(f"неизвестный параметр «{key}»")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key}: нужно целое число ≥ 0")
        out[key] = value
    return out


def item_price(v: dict, code: str) -> tuple[int, int]:
    """(coins, stars) — exactly one of them is > 0 for an item on sale."""
    return v.get(f"coins_{code}", 0), v.get(f"stars_{code}", 0)


def open_cells(v: dict, villa_level: int) -> tuple[tuple[int, int], ...]:
    """The cells open at a villa level, the plot's centre first."""
    level = max(1, min(MAX_VILLA_LEVEL, villa_level))
    return CELLS[:v[f"cells_{level}"]]


def garage_slots(v: dict, garage_level: int) -> int:
    return v[f"garage_slots_{garage_level}"] if garage_level > 0 else 0


def size_of(code: str) -> tuple[int, int]:
    if code == "villa":
        return VILLA_SIZE
    if code == "garage":
        return GARAGE_SIZE
    _, _, _, w, h = ITEMS[code]
    return w, h


def footprint(code: str, rot: int) -> tuple[int, int]:
    w, h = size_of(code)
    return (h, w) if rot else (w, h)


def check_layout(cells, items: list[tuple[int, str, Optional[int], Optional[int], int]]) -> Optional[str]:
    """None when (id, code, x, y, rot) items fit: on open cells only, no
    overlaps, the villa and the garage placed. Otherwise why not."""
    cells = cells if isinstance(cells, (set, frozenset)) else set(cells)
    taken: dict[tuple[int, int], int] = {}
    for item_id, code, x, y, rot in items:
        if x is None or y is None:
            if code in ("villa", "garage"):
                return "Виллу и гараж нельзя убрать на склад"
            continue
        w, h = footprint(code, rot)
        if any((x + dx, y + dy) not in cells for dx in range(w) for dy in range(h)):
            return "Предмет выходит за участок"
        for dx in range(w):
            for dy in range(h):
                if (x + dx, y + dy) in taken:
                    return "Клетки уже заняты"
                taken[(x + dx, y + dy)] = item_id
    return None


def staff_posts_for(title: Optional[str]) -> list[str]:
    lowered = (title or "").lower()
    return [post for post, (_, _, words) in POSTS.items() if any(w in lowered for w in words)]


def _cells(item) -> Optional[tuple[int, int, int, int]]:
    """(x0, y0, x1, y1) inclusive of a placed thing, None in storage."""
    if item.x is None or item.y is None:
        return None
    w, h = footprint(item.code, item.rot)
    return item.x, item.y, item.x + w - 1, item.y + h - 1


def _touch(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] - 1 <= b[2] and b[0] - 1 <= a[2] and a[1] - 1 <= b[3] and b[1] - 1 <= a[3]


def _kind_of(code: str) -> str:
    """Every kind of path tile counts as «path» in the combos."""
    return "path" if code in PATHS else code


def combos_of(items) -> list[dict]:
    """The combos standing on the plot, each once, with the ids that make it."""
    placed = [(i, c) for i in items if (c := _cells(i)) is not None]
    out = []
    for a, b, name, emoji in COMBOS:
        pair = next(((x.id, y.id) for x, cx in placed if _kind_of(x.code) == a
                     for y, cy in placed if _kind_of(y.code) == b and _touch(cx, cy)), None)
        if pair:
            out.append({"a": a, "b": b, "name": name, "emoji": emoji, "ids": list(pair)})
    return out


def working_posts(items, posts) -> list[str]:
    """Staffed posts whose workplace stands on the plot."""
    placed = {i.code for i in items if i.x is not None and i.y is not None}
    return [p for p in posts if p in POST_WORKPLACE and (not POST_WORKPLACE[p] or placed & set(POST_WORKPLACE[p]))]


def prestige_of(v: dict, villa: Optional[UserTownVilla], items, posts) -> int:
    if villa is None:
        return 0
    codes = {i.code for i in items}
    return (villa.villa_level * v["prestige_villa_level"] + villa.garage_level * v["prestige_garage_level"]
            + sum(v.get(f"prestige_{c}", 0) for c in codes if c in ITEMS)
            + len(working_posts(items, posts)) * v["prestige_staff"]
            + len(combos_of(items)) * v["prestige_combo"])


def prestige_pct(v: dict, prestige: int) -> int:
    return min(v["prestige_max_pct"], prestige // v["prestige_per_pct"])


# --- reading -------------------------------------------------------------------------------------

async def _villa(db: AsyncSession, user_id: int, lock: bool = False) -> Optional[UserTownVilla]:
    query = select(UserTownVilla).where(UserTownVilla.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def _items(db: AsyncSession, user_id: int) -> list[UserTownVillaItem]:
    return list((await db.execute(
        select(UserTownVillaItem).where(UserTownVillaItem.user_id == user_id).order_by(UserTownVillaItem.id)
    )).scalars())


async def _staff_rows(db: AsyncSession, user_id: int, villa: Optional[UserTownVilla]) -> dict[str, TownResident]:
    """Posts whose resident the player still holds (an active one)."""
    staff = dict(villa.staff or {}) if villa is not None else {}
    ids = [int(i) for i in staff.values() if isinstance(i, int)]
    if not ids:
        return {}
    held = {r.resident_id: r.resident for r in (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user_id, UserTownResident.resident_id.in_(ids),
                                       UserTownResident.copies > 0)
    )).scalars() if r.resident.is_active}
    return {post: held[rid] for post, rid in staff.items() if post in POSTS and rid in held}


async def prestige_for(db: AsyncSession, config, user_id: int) -> tuple[int, int]:
    """(prestige, rent %) of a player's villa — for town_service._income_parts."""
    villa = await _villa(db, user_id)
    if villa is None:
        return 0, 0
    v = villa_config(config)
    items = [i for i in await _items(db, user_id) if i.code in ITEMS or i.code in ("villa", "garage")]
    staff = await _staff_rows(db, user_id, villa) if config.town_residents_enabled else {}
    prestige = prestige_of(v, villa, items, list(staff))
    return prestige, prestige_pct(v, prestige)


# --- the villa in the game ----------------------------------------------------------------------

def perks_of(items) -> list[str]:
    """The perks of the things standing on the plot — each once, whatever stands twice."""
    placed = {i.code for i in items if i.x is not None}
    return [p for p, (_, _, codes) in PERKS.items() if placed & set(codes)]


def perk_text(v: dict, perk: str) -> str:
    return {
        "training": f"+{v['perk_training']} бесплатная тренировка «Моего игрока» в день",
        "recovery": f"лечение травм в «Менеджере» дешевле на {v['perk_treat_pct']}%",
        "travel": f"турне клуба в «Менеджере» дешевле на {v['perk_tour_pct']}%",
        "trophies": "гости виллы видят твои трофеи",
    }[perk]


async def perks_for(db: AsyncSession, config, user_id: int) -> list[str]:
    """The owner's villa perks now (none while the town is off or there is no villa)."""
    if not config.town_enabled or await _villa(db, user_id) is None:
        return []
    return perks_of(await _items(db, user_id))


async def training_perk(db: AsyncSession, config, user_id: int) -> int:
    """Extra free «Мой игрок» trainings a day the villa's pitch gives (0 or 1)."""
    v = villa_config(config)
    return min(1, v["perk_training"]) if "training" in await perks_for(db, config, user_id) else 0


async def manager_perks(db: AsyncSession, config, owner_id: int) -> dict[str, int]:
    """What the owner's villa gives his «Менеджер» club (manager_service.base_snapshot)."""
    v = villa_config(config)
    perks = await perks_for(db, config, owner_id)
    return {"villa_treat_pct": min(90, v["perk_treat_pct"]) if "recovery" in perks else 0,
            "villa_tour_pct": min(90, v["perk_tour_pct"]) if "travel" in perks else 0}


def income_of(v: dict, prestige: int) -> int:
    return min(v["income_cap"], v["income_base"] + prestige * v["income_per_100"] // 100)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def party_on(villa: Optional[UserTownVilla], now: Optional[datetime] = None) -> bool:
    if villa is None or villa.party_until is None:
        return False
    until = villa.party_until if villa.party_until.tzinfo else villa.party_until.replace(tzinfo=timezone.utc)
    return until > (now or _now())


async def _sold(db: AsyncSession, code: str) -> int:
    return int((await db.execute(
        select(func.count(UserTownVillaItem.id)).where(UserTownVillaItem.code == code)
    )).scalar_one())


def _item_out(item: UserTownVillaItem, villa: UserTownVilla) -> dict:
    name, emoji, kind = ("Вилла", "🏡", "villa") if item.code == "villa" else \
        ("Гараж", "🅿️", "garage") if item.code == "garage" else ITEMS[item.code][:3]
    w, h = size_of(item.code)
    level = villa.villa_level if item.code == "villa" else villa.garage_level if item.code == "garage" else None
    return {"id": item.id, "code": item.code, "name": name, "emoji": emoji, "kind": kind, "w": w, "h": h,
            "x": item.x, "y": item.y, "rot": item.rot, "serial": item.serial, "level": level}


def _plot(v: dict, villa: UserTownVilla, items: list[UserTownVillaItem], staff: dict[str, TownResident]) -> dict:
    """What anyone may see of a villa: the grid and what stands on it."""
    known = [i for i in items if i.code in ITEMS or i.code in ("villa", "garage")]
    prestige = prestige_of(v, villa, known, list(staff))
    working = set(working_posts(known, list(staff)))
    car = next((i for i in known if i.id == villa.car_item_id and i.code in ITEMS), None)
    return {
        "villa_level": villa.villa_level, "garage_level": villa.garage_level,
        "cells_open": len(open_cells(v, villa.villa_level)), "cells_total": CELL_COUNT,
        "combos": combos_of(known),
        "items": [_item_out(i, villa) for i in known],
        "car": {"id": car.id, "code": car.code, "name": ITEMS[car.code][0], "emoji": ITEMS[car.code][1]} if car else None,
        "staff": [{"post": p, "name": POSTS[p][0], "emoji": POSTS[p][1], "working": p in working, "resident": {
            "id": r.id, "name": r.name, "title": r.title, "icon": r.icon, "image_path": r.image_path, "rarity": r.rarity,
        }} for p, r in staff.items()],
        "prestige": prestige, "prestige_pct": prestige_pct(v, prestige),
        "perks": [{"code": p, "name": PERKS[p][0], "emoji": PERKS[p][1], "text": perk_text(v, p)} for p in perks_of(known)],
        "party_until": villa.party_until.isoformat() if party_on(villa) else None,
    }


def _first_free(cells: tuple[tuple[int, int], ...], items: list[UserTownVillaItem], code: str) -> Optional[tuple[int, int]]:
    """The free spot nearest the plot's centre (cells come centre first)."""
    layout = [(i.id, i.code, i.x, i.y, i.rot) for i in items]
    room = set(cells)
    for x, y in cells:
        if check_layout(room, layout + [(0, code, x, y, 0)]) is None:
            return x, y
    return None


def _repair(cells: tuple[tuple[int, int], ...], items: list[UserTownVillaItem]) -> bool:
    """Makes a layout that no longer fits fit again (the grid changed): the
    villa and the garage first, then the rest in order; what can't stand
    goes to storage, a villa or garage that can't to the first free spot.
    True when something moved."""
    layout = lambda: [(i.id, i.code, i.x, i.y, i.rot) for i in items]  # noqa: E731
    if check_layout(cells, layout()) is None:
        return False
    order = sorted(items, key=lambda i: (i.code not in ("villa", "garage"), i.id))
    kept: list[UserTownVillaItem] = []
    for item in order:
        if item.x is not None and check_layout(cells, [(k.id, k.code, k.x, k.y, k.rot) for k in kept]
                                               + [(item.id, item.code, item.x, item.y, item.rot)]) is None:
            kept.append(item)
            continue
        if item.code in ("villa", "garage"):
            spot = _first_free(cells, kept, item.code)
            item.x, item.y, item.rot = (spot[0], spot[1], 0) if spot else (0, 0, 0)
            kept.append(item)
        else:
            item.x = item.y = None
    return True


async def _ensure_villa(db: AsyncSession, config, user_id: int) -> UserTownVilla:
    """The villa row under a lock, created (with the villa on the plot) on
    the first look of an opened town."""
    villa = await _villa(db, user_id, lock=True)
    if villa is not None:
        return villa
    try:
        async with db.begin_nested():
            villa = UserTownVilla(user_id=user_id, villa_level=1, garage_level=0, staff={})
            db.add(villa)
            await db.flush()
            spot = _first_free(open_cells(villa_config(config), 1), [], "villa") or CELLS[0]
            db.add(UserTownVillaItem(user_id=user_id, code="villa", x=spot[0], y=spot[1], rot=0))
            await db.flush()
    except IntegrityError:  # a parallel request made it first
        pass
    return await _villa(db, user_id, lock=True)


async def _open(db: AsyncSession, config, user_id: int) -> UserTownVilla:
    town_service._require_enabled(config)
    if not town_service.is_unlocked(config, await db.get(UserTown, user_id)):
        raise ConflictError("Сначала открой город")
    villa = await _ensure_villa(db, config, user_id)
    items = await _items(db, user_id)
    if _repair(open_cells(villa_config(config), villa.villa_level), items):
        db.add_all(items)
        await db.flush()
    return villa


async def get_villa(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    villa = await _open(db, config, user.id)
    await db.commit()
    return await _state(db, config, user, villa)


async def _state(db: AsyncSession, config, user: User, villa: UserTownVilla) -> dict:
    v = villa_config(config)
    items = await _items(db, user.id)
    staff = await _staff_rows(db, user.id, villa) if config.town_residents_enabled else {}
    owned_codes: dict[str, int] = {}
    for i in items:
        owned_codes[i.code] = owned_codes.get(i.code, 0) + 1
    cars = sum(1 for i in items if i.code in ITEMS and ITEMS[i.code][2] == "car")
    slots = garage_slots(v, villa.garage_level)
    shop = []
    for code, (name, emoji, kind, w, h) in ITEMS.items():
        coins, stars = item_price(v, code)
        supply = v.get(f"supply_{code}", 0)
        sold = await _sold(db, code) if supply else 0
        single = kind in _SINGLE_KINDS
        reason = ""
        if not coins and not stars:
            reason = "Не продаётся"
        elif single and owned_codes.get(code):
            reason = "Уже твоё"
        elif kind == "car" and cars >= slots:
            reason = "Нужно место в гараже" if slots else "Сначала построй гараж"
        elif supply and sold >= supply:
            reason = "Все копии разобраны"
        elif len(items) >= v["max_items"]:
            reason = "Склад полон"
        shop.append({
            "code": code, "name": name, "emoji": emoji, "kind": kind, "w": w, "h": h,
            "coins": coins, "stars": stars, "prestige": v.get(f"prestige_{code}", 0),
            "owned": owned_codes.get(code, 0), "supply": supply, "sold": sold,
            "can_buy": not reason, "reason": reason,
        })
    # Residents the player holds that some post takes.
    held = (await db.execute(
        select(UserTownResident).where(UserTownResident.user_id == user.id, UserTownResident.copies > 0)
    )).scalars().all() if config.town_residents_enabled else []
    candidates = [{"id": r.resident.id, "name": r.resident.name, "title": r.resident.title, "icon": r.resident.icon,
                   "image_path": r.resident.image_path, "rarity": r.resident.rarity,
                   "posts": staff_posts_for(r.resident.title)}
                  for r in held if r.resident.is_active and staff_posts_for(r.resident.title)]
    nl, ng = villa.villa_level + 1, villa.garage_level + 1
    plot = _plot(v, villa, items, staff)
    if villa.prestige != plot["prestige"]:  # «Вилла месяца» ranks by the prestige last shown
        villa.prestige = plot["prestige"]
        db.add(villa)
        await db.commit()
    today = local_today()
    return {
        **plot,
        "all_perks": [{"code": p, "name": n, "emoji": e, "text": perk_text(v, p),
                       "buildings": [ITEMS[c][0] for c in codes]} for p, (n, e, codes) in PERKS.items()],
        "income": {"coins": income_of(v, plot["prestige"]), "ready": villa.income_day != today,
                   "base": v["income_base"], "per_100": v["income_per_100"], "cap": v["income_cap"]},
        "party": {"cost": v["party_cost"], "hours": v["party_hours"], "guest_coins": v["party_guest_coins"],
                  "can_throw": v["party_hours"] > 0 and villa.party_week != villa_week_key(today) and not party_on(villa)},
        "user_id": user.id,
        "next_villa": {"level": nl, "price": v[f"villa_price_{nl}"], "cells": len(open_cells(v, nl))} if nl <= MAX_VILLA_LEVEL else None,
        "next_garage": {"level": ng, "price": v[f"garage_price_{ng}"], "slots": garage_slots(v, ng)}
        if ng <= MAX_GARAGE_LEVEL else None,
        "garage_slots": slots, "cars": cars,
        "shop": shop,
        "posts": [{"post": p, "name": n, "emoji": e, "workplace": [ITEMS[c][0] if c in ITEMS else "Гараж" for c in POST_WORKPLACE[p]]}
                  for p, (n, e, _) in POSTS.items()],
        "all_combos": [{"a": a, "b": b, "name": n, "emoji": e,
                        "a_name": ITEMS[a][0] if a in ITEMS else {"villa": "Вилла", "garage": "Гараж"}[a],
                        "b_name": ITEMS[b][0] if b in ITEMS else {"villa": "Вилла", "garage": "Гараж"}[b]}
                       for a, b, n, e in COMBOS],
        "prestige_combo": v["prestige_combo"], "prestige_staff": v["prestige_staff"],
        "candidates": candidates,
        "prestige_per_pct": v["prestige_per_pct"], "prestige_max_pct": v["prestige_max_pct"],
        "max_items": v["max_items"],
        "likes_total": await _villa_likes(db, user.id),
    }


# --- actions -------------------------------------------------------------------------------------

async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> bool:
    if not key:
        return False
    return (await db.execute(select(TownLedger.id).where(
        TownLedger.user_id == user_id, TownLedger.idempotency_key == key,
    ))).first() is not None


async def upgrade(db: AsyncSession, user: User, target: str, idempotency_key: Optional[str]) -> dict:
    """The villa's or the garage's next level for coins."""
    config = await get_config(db)
    if target not in ("villa", "garage"):
        raise NotFoundError("Такой постройки нет")
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}
    v = villa_config(config)
    level = (villa.villa_level if target == "villa" else villa.garage_level) + 1
    if level > (MAX_VILLA_LEVEL if target == "villa" else MAX_GARAGE_LEVEL):
        raise ConflictError("Это уже последний уровень")
    price = v[f"{target}_price_{level}"]
    items = await _items(db, user.id)
    spot = None
    if target == "garage" and level == 1:
        spot = _first_free(open_cells(v, villa.villa_level), items, "garage")
        if spot is None:
            raise ConflictError("Освободи на участке место 2×2 под гараж")
    await town_service._settle_before_population_change(db, config, user.id)
    if price:
        await debit_coins(db, locked_user, price, TransactionType.town_villa,
                          f"Вилла: {'вилла' if target == 'villa' else 'гараж'}, уровень {level}",
                          related_object_type="town_villa", related_object_id=level)
    if target == "villa":
        villa.villa_level = level
    else:
        villa.garage_level = level
        if spot is not None:
            db.add(UserTownVillaItem(user_id=user.id, code="garage", x=spot[0], y=spot[1], rot=0))
    db.add_all([villa, TownLedger(user_id=user.id, kind="villa", building_code=f"{target}:{level}", coins_spent=price,
                                  result={"target": target, "level": level}, idempotency_key=idempotency_key)])
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}


async def _available(db: AsyncSession, config, user_id: int, code: str, villa: Optional[UserTownVilla]) -> tuple[bool, str]:
    if code not in ITEMS:
        return False, "Такого предмета нет"
    if villa is None:
        return False, "Сначала открой виллу"
    v = villa_config(config)
    name, _, kind, _, _ = ITEMS[code]
    items = await _items(db, user_id)
    if len(items) >= v["max_items"]:
        return False, f"Склад полон — у виллы не больше {v['max_items']} предметов"
    if kind in _SINGLE_KINDS and any(i.code == code for i in items):
        return False, f"«{name}» уже у тебя"
    if kind == "car":
        slots = garage_slots(v, villa.garage_level)
        if sum(1 for i in items if i.code in ITEMS and ITEMS[i.code][2] == "car") >= slots:
            return False, "Нужно место в гараже — улучши гараж" if slots else "Сначала построй гараж"
    supply = v.get(f"supply_{code}", 0)
    if supply and await _sold(db, code) >= supply:
        return False, "Все копии уже разобраны"
    return True, ""


async def _grant(db: AsyncSession, user_id: int, code: str, supply: int) -> UserTownVillaItem:
    """A new thing in storage; a limited one numbered (the unique index
    decides between two buyers of the same serial)."""
    if not supply:
        item = UserTownVillaItem(user_id=user_id, code=code)
        db.add(item)
        await db.flush()
        return item
    for _ in range(5):
        top = (await db.execute(
            select(func.max(UserTownVillaItem.serial)).where(UserTownVillaItem.code == code)
        )).scalar_one()
        try:
            async with db.begin_nested():
                item = UserTownVillaItem(user_id=user_id, code=code, serial=int(top or 0) + 1)
                db.add(item)
                await db.flush()
            return item
        except IntegrityError:
            continue
    item = UserTownVillaItem(user_id=user_id, code=code)  # never refuse a paid one
    db.add(item)
    await db.flush()
    return item


async def buy_item(db: AsyncSession, user: User, code: str, idempotency_key: Optional[str]) -> dict:
    """A thing for coins, into storage."""
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    if await _replay(db, user.id, idempotency_key):
        return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}
    v = villa_config(config)
    if code not in ITEMS:
        raise NotFoundError("Такого предмета нет")
    coins, stars = item_price(v, code)
    if not coins:
        raise ConflictError("Этот предмет продаётся только за ⭐" if stars else "Этот предмет не продаётся")
    ok, reason = await _available(db, config, user.id, code, villa)
    if not ok:
        raise ConflictError(reason)
    await town_service._settle_before_population_change(db, config, user.id)
    await debit_coins(db, locked_user, coins, TransactionType.town_villa, f"Вилла: {ITEMS[code][0]}",
                      related_object_type="town_villa_item")
    item = await _grant(db, user.id, code, v.get(f"supply_{code}", 0))
    db.add(TownLedger(user_id=user.id, kind="villa", building_code=code, coins_spent=coins,
                      result={"item_id": item.id}, idempotency_key=idempotency_key))
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}


async def save_layout(db: AsyncSession, user: User, moves: list[dict]) -> dict:
    """Moves things: [{id, x, y, rot}] (x/y None = to storage). Things not
    named stay where they are; the result as a whole must fit."""
    config = await get_config(db)
    await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    v = villa_config(config)
    await town_service._settle_before_population_change(db, config, user.id)  # combos and workplaces move the prestige
    items = {i.id: i for i in await _items(db, user.id)}
    for move in moves:
        item = items.get(move.get("id"))
        if item is None:
            raise NotFoundError("Этого предмета у тебя нет")
        x, y = move.get("x"), move.get("y")
        if (x is None) != (y is None):
            raise ConflictError("Нужны обе координаты")
        item.x, item.y = x, y
        item.rot = 1 if move.get("rot") else 0
    error = check_layout(open_cells(v, villa.villa_level), [(i.id, i.code, i.x, i.y, i.rot) for i in items.values()])
    if error:
        await db.rollback()
        raise ConflictError(error)
    db.add_all(items.values())
    await db.commit()
    return await _state(db, config, user, villa)


async def choose_car(db: AsyncSession, user: User, item_id: Optional[int]) -> dict:
    config = await get_config(db)
    villa = await _open(db, config, user.id)
    if item_id is not None:
        item = await db.get(UserTownVillaItem, item_id)
        if item is None or item.user_id != user.id or item.code not in ITEMS or ITEMS[item.code][2] != "car":
            raise NotFoundError("Этой машины у тебя нет")
    villa.car_item_id = item_id
    db.add(villa)
    await db.commit()
    return await _state(db, config, user, villa)


async def set_staff(db: AsyncSession, user: User, post: str, resident_id: Optional[int]) -> dict:
    """Puts a held resident of a fitting profession on a post (off any other)
    or frees the post. The rent so far is settled at the old prestige."""
    config = await get_config(db)
    if post not in POSTS:
        raise NotFoundError("Такой должности нет")
    if not config.town_residents_enabled:
        raise ConflictError("Жители сейчас отключены")
    await lock_user_for_update(db, user.id)
    villa = await _open(db, config, user.id)
    staff = {p: r for p, r in dict(villa.staff or {}).items() if p in POSTS and p != post and r != resident_id}
    if resident_id is not None:
        row = (await db.execute(select(UserTownResident).where(
            UserTownResident.user_id == user.id, UserTownResident.resident_id == resident_id, UserTownResident.copies > 0,
        ))).scalar_one_or_none()
        if row is None or not row.resident.is_active:
            raise NotFoundError("Этого жителя у тебя нет")
        if post not in staff_posts_for(row.resident.title):
            raise ConflictError(f"{row.resident.name} не подходит на пост «{POSTS[post][0]}»")
        staff[post] = resident_id
    await town_service._settle_before_population_change(db, config, user.id)
    villa.staff = staff
    db.add(villa)
    await db.commit()
    return await _state(db, config, user, villa)


# --- Stars ---------------------------------------------------------------------------------------

async def create_invoice(db: AsyncSession, user: User, code: str) -> dict:
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    villa = await _open(db, config, user.id)
    if code not in ITEMS:
        raise NotFoundError("Такого предмета нет")
    _, stars = item_price(villa_config(config), code)
    if stars <= 0:
        raise ConflictError("Этот предмет не продаётся за ⭐")
    ok, reason = await _available(db, config, user.id, code, villa)
    if not ok:
        raise ConflictError(reason)
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=STARS_PREFIX + code))
    await db.flush()
    name, emoji, _, _, _ = ITEMS[code]
    link = await _request_telegram_invoice_link(token, f"{emoji} {name}", "Для твоей виллы в городе", stars)
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def validate_invoice(db: AsyncSession, invoice) -> tuple[bool, str]:
    config = await get_config(db)
    code = invoice.academy_speedup[len(STARS_PREFIX):]
    if code not in ITEMS:
        return False, "Unknown order"
    if item_price(villa_config(config), code)[1] != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return await _available(db, config, invoice.user_id, code, await _villa(db, invoice.user_id))


async def deliver_invoice(db: AsyncSession, user: User, invoice) -> dict:
    """Under the invoice row lock; never refuses a taken payment (a second
    copy of a single item only goes to the ledger). The caller commits."""
    config = await get_config(db)
    code = invoice.academy_speedup[len(STARS_PREFIX):]
    item_id = None
    repeat = True
    if code in ITEMS:
        held = (await db.execute(select(UserTownVillaItem.id).where(
            UserTownVillaItem.user_id == user.id, UserTownVillaItem.code == code,
        ))).first()
        repeat = held is not None and ITEMS[code][2] in _SINGLE_KINDS
        if not repeat:
            await _ensure_villa(db, config, user.id)
            await town_service._settle_before_population_change(db, config, user.id)
            item = await _grant(db, user.id, code, villa_config(config).get(f"supply_{code}", 0))
            item_id = item.id
    db.add(TownLedger(user_id=user.id, kind="villa", building_code=code, result={"item_id": item_id, "repeat": repeat},
                      idempotency_key=f"stars-{invoice.payload_token}"))
    await db.flush()
    return {"kind": "town_villa", "code": code, "item_id": item_id}


# --- guests and «Вилла недели» -------------------------------------------------------------------

async def _villa_likes(db: AsyncSession, owner_id: int, since: Optional[date] = None) -> int:
    query = select(func.count()).select_from(TownVisit).where(TownVisit.owner_id == owner_id, TownVisit.villa_liked.is_(True))
    if since is not None:
        query = query.where(TownVisit.day >= since)
    return int((await db.execute(query)).scalar_one())


async def guest_view(db: AsyncSession, config, owner_id: int, visit: TownVisit) -> dict:
    """Someone's villa for a guest (read-only)."""
    villa = await _villa(db, owner_id)
    if villa is None:
        raise NotFoundError("Хозяин ещё не обустроил виллу")
    v = villa_config(config)
    staff = await _staff_rows(db, owner_id, villa) if config.town_residents_enabled else {}
    from app.services.town_social_service import week_days

    monday, _ = week_days(local_today())
    plot = _plot(v, villa, await _items(db, owner_id), staff)
    trophies = []
    if any(p["code"] == "trophies" for p in plot["perks"]):
        from app.services.my_player_service import trophies_of

        trophies = [{k: t[k] for k in ("id", "name", "icon", "image_path")} for t in (await trophies_of(db, owner_id))[:12]]
    return {
        **plot, "trophies": trophies,
        "party_guest_coins": v["party_guest_coins"] if plot["party_until"] else 0,
        "user_id": owner_id, "liked": visit.villa_liked,
        "likes_total": await _villa_likes(db, owner_id), "likes_week": await _villa_likes(db, owner_id, monday),
    }


async def summary(db: AsyncSession, config, owner_id: int) -> Optional[dict]:
    """A line about someone's villa for the town visit (None — no villa)."""
    villa = await _villa(db, owner_id)
    if villa is None:
        return None
    prestige, _ = await prestige_for(db, config, owner_id)
    car = await db.get(UserTownVillaItem, villa.car_item_id) if villa.car_item_id else None
    return {"villa_level": villa.villa_level, "prestige": prestige, "party": party_on(villa),
            "car": car.code if car is not None and car.user_id == owner_id and car.code in ITEMS else None}


def villa_week_key(day: date) -> str:
    from app.services.town_social_service import week_key

    return "V" + week_key(day)


def _week_reward(v: dict, place: int) -> int:
    return v.get(f"villa_week_reward_{place}", 0)


async def _week_scores(db: AsyncSession, config, day: date) -> list[dict]:
    from datetime import datetime, timezone

    from app.services.town_social_service import _owner_name, social_config, week_days

    s = social_config(config)
    monday, sunday = week_days(day)
    old_enough = datetime.now(timezone.utc) - timedelta(days=s["week_min_account_days"])
    rows = (await db.execute(
        select(TownVisit.owner_id, func.count()).join(User, User.id == TownVisit.visitor_id)
        .where(TownVisit.day >= monday, TownVisit.day <= sunday, TownVisit.villa_liked.is_(True),
               User.created_at <= old_enough, User.is_banned.is_(False))
        .group_by(TownVisit.owner_id)
    )).all()
    if not rows:
        return []
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([r[0] for r in rows])))).scalars()}
    villas = {x.user_id: x for x in (await db.execute(
        select(UserTownVilla).where(UserTownVilla.user_id.in_([r[0] for r in rows]))
    )).scalars()}
    out = [{"user_id": oid, "owner": _owner_name(owners.get(oid)), "likes": int(n),
            "villa_level": villas[oid].villa_level}
           for oid, n in rows if oid in owners and not owners[oid].is_banned and oid in villas]
    out.sort(key=lambda r: (-r["likes"], -r["villa_level"], r["user_id"]))
    for place, row in enumerate(out, start=1):
        row["place"] = place
    return out


async def settle_villa_week(db: AsyncSession, config, day: date) -> bool:
    key = villa_week_key(day)
    if await db.get(TownWeek, key) is not None:
        return False
    v = villa_config(config)
    ranking = await _week_scores(db, config, day)
    try:
        db.add(TownWeek(week=key))
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    for row in ranking[:3]:
        coins = _week_reward(v, row["place"])
        user = await lock_user_for_update(db, row["user_id"])
        paid = 0 if user.game_rewards_blocked else coins
        if paid:
            await credit_coins(db, user, paid, TransactionType.town_week, f"«Вилла недели»: {row['place']} место",
                               related_object_type="town_villa_week", related_object_id=row["place"])
        db.add(TownWeekResult(week=key, place=row["place"], user_id=row["user_id"], score=row["likes"], coins=paid))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def villa_week(db: AsyncSession, user: User) -> dict:
    from app.services.town_social_service import _owner_name, week_days

    config = await get_config(db)
    town_service._require_enabled(config)
    v = villa_config(config)
    today = local_today()
    last_day = today - timedelta(days=7)
    await settle_villa_week(db, config, last_day)
    ranking = await _week_scores(db, config, today)
    last_key = villa_week_key(last_day)
    winners = (await db.execute(
        select(TownWeekResult).where(TownWeekResult.week == last_key).order_by(TownWeekResult.place).limit(3)
    )).scalars().all()
    names = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_([w.user_id for w in winners] or [0]))
    )).scalars()}
    _, sunday = week_days(today)
    return {
        "ends_on": sunday.isoformat(),
        "rewards": [{"place": p, "coins": _week_reward(v, p)} for p in (1, 2, 3)],
        "top": [{**r, "reward": _week_reward(v, r["place"]) if r["place"] <= 3 else 0} for r in ranking[:20]],
        "me": next((r for r in ranking if r["user_id"] == user.id), None),
        "last_week": [{"place": w.place, "user_id": w.user_id, "owner": _owner_name(names.get(w.user_id)),
                       "likes": w.score, "coins": w.coins} for w in winners],
        "month": await _month_view(db, config, user, today),
    }


# --- income, the party and «Вилла месяца» ---------------------------------------------------------

async def collect_income(db: AsyncSession, user: User) -> dict:
    """The villa's income for today, once a local day."""
    config = await get_config(db)
    town_service._require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _villa(db, user.id, lock=True)
    if villa is None:
        raise NotFoundError("Сначала открой виллу")
    today = local_today()
    if villa.income_day == today:
        raise ConflictError("Доход виллы за сегодня уже забран — приходи завтра")
    prestige, _ = await prestige_for(db, config, user.id)
    coins = 0 if locked_user.game_rewards_blocked else income_of(villa_config(config), prestige)
    villa.income_day = today
    db.add(villa)
    if coins:
        await credit_coins(db, locked_user, coins, TransactionType.town_villa, "Доход виллы",
                           related_object_type="town_villa_income", related_object_id=None)
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance, "income_paid": coins}


async def throw_party(db: AsyncSession, user: User) -> dict:
    """The week's party: party_cost coins, party_hours long, once a «Вилла недели» week."""
    config = await get_config(db)
    town_service._require_enabled(config)
    v = villa_config(config)
    if v["party_hours"] <= 0:
        raise ConflictError("Вечеринки сейчас не проводятся")
    locked_user = await lock_user_for_update(db, user.id)
    villa = await _villa(db, user.id, lock=True)
    if villa is None:
        raise NotFoundError("Сначала открой виллу")
    week = villa_week_key(local_today())
    if villa.party_week == week or party_on(villa):
        raise ConflictError("Вечеринка на этой неделе уже была — следующая с понедельника")
    if v["party_cost"]:
        await debit_coins(db, locked_user, v["party_cost"], TransactionType.town_villa, "Вечеринка на вилле",
                          related_object_type="town_villa_party", related_object_id=None)
    villa.party_until = _now() + timedelta(hours=v["party_hours"])
    villa.party_week = week
    db.add(villa)
    await db.commit()
    return {**await _state(db, config, user, villa), "new_balance": locked_user.balance}


async def party_reward(db: AsyncSession, config, guest: User, owner_id: int, visit: TownVisit) -> int:
    """A guest's villa like during the owner's party: party_guest_coins, for at most
    party_guest_per_day parties a day, accounts older than week_min_account_days only.
    The guest is locked by the caller, who commits."""
    from app.services.town_social_service import social_config

    v = villa_config(config)
    if not party_on(await _villa(db, owner_id)) or v["party_guest_coins"] <= 0 or guest.game_rewards_blocked:
        return 0
    created = guest.created_at if guest.created_at.tzinfo else guest.created_at.replace(tzinfo=timezone.utc)
    if _now() - created < timedelta(days=social_config(config)["week_min_account_days"]):
        return 0
    paid_today = int((await db.execute(select(func.count()).select_from(TownVisit).where(
        TownVisit.visitor_id == guest.id, TownVisit.day == visit.day, TownVisit.party_coins > 0,
    ))).scalar_one())
    if paid_today >= v["party_guest_per_day"]:
        return 0
    coins = v["party_guest_coins"]
    await credit_coins(db, guest, coins, TransactionType.town_villa, "Вечеринка на вилле",
                       related_object_type="town_villa_party", related_object_id=owner_id)
    visit.party_coins = coins
    return coins


# The first month «Вилла месяца» pays for (the ones before it had no rating).
FIRST_MONTH = "VM2026-11"


def villa_month_key(day: date) -> str:
    return f"VM{day.year:04d}-{day.month:02d}"


def _month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


async def _month_scores(db: AsyncSession, config, day: date) -> list[dict]:
    """Villas by prestige + the month's likes × month_like_points."""
    from app.services.town_social_service import _owner_name, social_config

    v = villa_config(config)
    first, last = _month_bounds(day)
    old_enough = _now() - timedelta(days=social_config(config)["week_min_account_days"])
    likes = {oid: int(n) for oid, n in (await db.execute(
        select(TownVisit.owner_id, func.count()).join(User, User.id == TownVisit.visitor_id)
        .where(TownVisit.day >= first, TownVisit.day <= last, TownVisit.villa_liked.is_(True),
               User.created_at <= old_enough, User.is_banned.is_(False))
        .group_by(TownVisit.owner_id)
    )).all()}
    rows = (await db.execute(
        select(UserTownVilla, User).join(User, User.id == UserTownVilla.user_id)
        .where(User.is_banned.is_(False), (UserTownVilla.prestige > 0) | UserTownVilla.user_id.in_(list(likes) or [0]))
    )).all()
    out = [{"user_id": villa.user_id, "owner": _owner_name(owner), "prestige": villa.prestige,
            "likes": likes.get(villa.user_id, 0), "villa_level": villa.villa_level,
            "score": villa.prestige + likes.get(villa.user_id, 0) * v["month_like_points"]}
           for villa, owner in rows]
    out.sort(key=lambda r: (-r["score"], -r["villa_level"], r["user_id"]))
    for place, row in enumerate(out, start=1):
        row["place"] = place
    return out


async def settle_villa_month(db: AsyncSession, config, day: date) -> bool:
    """Pays month_reward_1..3 for the month of `day`, once (a town_weeks row "VM…")."""
    key = villa_month_key(day)
    if key < FIRST_MONTH or await db.get(TownWeek, key) is not None:
        return False
    v = villa_config(config)
    ranking = await _month_scores(db, config, day)
    try:
        db.add(TownWeek(week=key))
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    for row in ranking[:3]:
        coins = v.get(f"month_reward_{row['place']}", 0)
        user = await lock_user_for_update(db, row["user_id"])
        paid = 0 if user.game_rewards_blocked else coins
        if paid:
            await credit_coins(db, user, paid, TransactionType.town_week, f"«Вилла месяца»: {row['place']} место",
                               related_object_type="town_villa_month", related_object_id=row["place"])
        db.add(TownWeekResult(week=key, place=row["place"], user_id=row["user_id"], score=row["score"], coins=paid))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


def _month_reward(v: dict, place: int) -> int:
    return v.get(f"month_reward_{place}", 0) if place <= 3 else 0


async def _month_view(db: AsyncSession, config, user: User, today: date) -> dict:
    from app.services.town_social_service import _owner_name

    v = villa_config(config)
    last_day = today.replace(day=1) - timedelta(days=1)
    await settle_villa_month(db, config, last_day)
    ranking = await _month_scores(db, config, today)
    winners = (await db.execute(
        select(TownWeekResult).where(TownWeekResult.week == villa_month_key(last_day))
        .order_by(TownWeekResult.place).limit(3)
    )).scalars().all()
    names = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_([w.user_id for w in winners] or [0]))
    )).scalars()}
    return {
        "ends_on": _month_bounds(today)[1].isoformat(), "like_points": v["month_like_points"],
        "rewards": [{"place": p, "coins": _month_reward(v, p)} for p in (1, 2, 3)],
        "top": [{**r, "reward": _month_reward(v, r["place"])} for r in ranking[:20]],
        "me": next((r for r in ranking if r["user_id"] == user.id), None),
        "last_month": [{"place": w.place, "user_id": w.user_id, "owner": _owner_name(names.get(w.user_id)),
                        "score": w.score, "coins": w.coins} for w in winners],
    }
