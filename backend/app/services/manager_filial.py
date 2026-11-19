"""«Филиал академии» of a «Менеджер» club: a youth school in a region of the
world that sends ready footballers to the club.

- Opened once for coins in a region (`REGIONS`: the countries of a «выпуск»
  are drawn by the region's weights, the line by its bias); the president
  picks the country he puts it in — the look only. Four buildings for coins:
  «Поля» (+1 to the peak a level), «Интернат» (+1 contract a level; at the
  top a release every `filial_every_min` seasons instead of `filial_every`),
  «Скаут-офис» (one more candidate; then +1 to the lowest potential),
  «Спортзал» (the decline starts a season later a level).
- «Выпуск»: every `filial_every` seasons, while a contract is free, the
  president picks one of the candidates (or lets them go). The alumnus
  joins the club's squad (counts against `manager_squad_max`), takes a
  catalog-like wage at every season start, and holds the contract while he
  plays for this club — sold, released or retired, it frees.
- Career: 1 season = 1 year from `filial_start_age`; the peak is the club's
  division rating at the release + potential + «Поля», so a club in the
  bottom division can't raise a star; the rating climbs to the peak, holds
  until the decline age and falls by `filial_decline` a season; he retires
  at an age in `filial_retire_age`. Everything follows from the season keys
  (`rating_at` / `age_at`), retirement is marked lazily on reads.
- Money is never created from nothing: the market buys an alumnus back at
  `manager_sell_back_pct` of his value once a season per club; other
  presidents buy him at `filial_min_price_pct`..`filial_max_price_pct` of
  his value (no dumping between friends or to one's second account), the
  `filial_fee_pct` is burnt, and one pair of clubs trades again only after
  `filial_pair_cooldown_seasons`.

Numbers: GameConfig.manager_finance over manager_finance.DEFAULTS."""
import random
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import TransactionType
from app.models.manager_club import ManagerClub
from app.models.manager_filial import ManagerAlumniTrade, ManagerAlumnus, ManagerFilial
from app.models.user import User
from app.services import manager_finance as finance, manager_staff as staff, wallet_service
from app.services.game_config_service import get_config

RELATED = "manager_filial"
BUILDINGS: dict[str, dict] = {
    "fields": {"name": "Тренировочные поля", "emoji": "⚽", "about": "+1 к пику выпускника за уровень"},
    "internat": {"name": "Интернат", "emoji": "🏠", "about": "+1 контракт выпускника; на последнем уровне выпуск чаще"},
    "scout": {"name": "Скаут-офис", "emoji": "🔭", "about": "больше кандидатов на выбор, затем выше потенциал"},
    "gym": {"name": "Спортзал", "emoji": "💪", "about": "спад начинается на сезон позже за уровень"},
}
LINES = ("GK", "DEF", "MID", "FWD")
POSITIONS = {"GK": ("GK",), "DEF": ("CB", "CB", "LB", "RB"), "MID": ("CM", "CM", "CDM", "CAM", "LM", "RM"),
             "FWD": ("ST", "ST", "LW", "RW")}
LINE_OF = {p: line for line, ps in POSITIONS.items() for p in ps}

# country: (flag, weight in its region, first names, last names)
_SA = {
    "Бразилия": ("🇧🇷", 35, ["Габриэл", "Лукас", "Матеус", "Витор", "Рафаэл", "Жуан", "Кайо", "Тиаго", "Энзо", "Давид"],
                 ["Силва", "Сантус", "Оливейра", "Соуза", "Перейра", "Алвес", "Лима", "Карвальо", "Гомес", "Рибейру"]),
    "Аргентина": ("🇦🇷", 25, ["Матиас", "Франко", "Николас", "Лаутаро", "Хулиан", "Агустин", "Тьяго", "Факундо", "Валентин"],
                  ["Гонсалес", "Родригес", "Фернандес", "Лопес", "Мартинес", "Перес", "Гомес", "Санчес", "Ромеро"]),
    "Уругвай": ("🇺🇾", 12, ["Федерико", "Родриго", "Себастьян", "Брайан", "Матиас", "Агустин"],
                ["Суарес", "Перейра", "Кабрера", "Оливера", "Нуньес", "Гарсия"]),
    "Колумбия": ("🇨🇴", 12, ["Хуан", "Луис", "Кристиан", "Хамес", "Дуван", "Хесус"],
                 ["Каррильо", "Мина", "Ариас", "Кинтеро", "Борха", "Санчес"]),
    "Чили": ("🇨🇱", 8, ["Алексис", "Артуро", "Диего", "Бенхамин", "Игнасио"], ["Варгас", "Исла", "Арангис", "Сото", "Муньос"]),
    "Эквадор": ("🇪🇨", 8, ["Мойсес", "Энер", "Пьеро", "Кендри"], ["Кайседо", "Эступиньян", "Пласиос", "Инкапье"]),
}
_EU = {
    "Испания": ("🇪🇸", 12, ["Пабло", "Алехандро", "Серхио", "Альваро", "Даниэль", "Хави"],
                ["Гарсия", "Мартин", "Руис", "Наварро", "Морено", "Ортега"]),
    "Франция": ("🇫🇷", 12, ["Антуан", "Люка", "Тео", "Хьюго", "Матис", "Эмиль"],
                ["Мартен", "Бернар", "Дюбуа", "Лефевр", "Мерсье", "Жиру"]),
    "Германия": ("🇩🇪", 10, ["Лукас", "Йонас", "Леон", "Феликс", "Пауль", "Ник"],
                 ["Мюллер", "Шмидт", "Шнайдер", "Фишер", "Вебер", "Вагнер"]),
    "Италия": ("🇮🇹", 10, ["Лоренцо", "Франческо", "Маттео", "Алессандро", "Федерико", "Никколо"],
               ["Росси", "Руссо", "Феррари", "Бьянки", "Риччи", "Коломбо"]),
    "Англия": ("🏴", 10, ["Джек", "Гарри", "Оливер", "Чарли", "Джордж", "Мейсон"],
               ["Смит", "Джонс", "Тейлор", "Браун", "Уокер", "Райт"]),
    "Португалия": ("🇵🇹", 8, ["Жуан", "Диогу", "Гонсалу", "Руй", "Нуну", "Бернарду"],
                   ["Феррейра", "Кошта", "Мендеш", "Нунеш", "Сильва", "Пинту"]),
    "Нидерланды": ("🇳🇱", 7, ["Даан", "Йесс", "Тейс", "Люк", "Сем", "Ким"],
                   ["де Йонг", "Янсен", "Баккер", "Виссер", "ван Дейк", "Смит"]),
    "Россия": ("🇷🇺", 8, ["Артём", "Максим", "Иван", "Дмитрий", "Кирилл", "Матвей", "Егор"],
               ["Смирнов", "Иванов", "Кузнецов", "Соколов", "Попов", "Волков", "Морозов"]),
    "Украина": ("🇺🇦", 7, ["Андрей", "Богдан", "Тарас", "Олег", "Назар", "Виталий"],
                ["Шевченко", "Бондаренко", "Коваленко", "Ткаченко", "Мельник", "Кравченко"]),
    "Польша": ("🇵🇱", 5, ["Якуб", "Кацпер", "Шимон", "Мацей", "Бартош"], ["Новак", "Ковальски", "Вишневски", "Зелински", "Левандовски"]),
    "Сербия": ("🇷🇸", 4, ["Душан", "Лазар", "Никола", "Сергей", "Марко"], ["Йованович", "Петрович", "Николич", "Милинкович", "Влахович"]),
    "Хорватия": ("🇭🇷", 4, ["Лука", "Иван", "Марио", "Йосип", "Анте"], ["Модрич", "Перишич", "Ковачич", "Шимунович", "Бротович"]),
    "Чехия": ("🇨🇿", 3, ["Томаш", "Павел", "Адам", "Ян"], ["Новотны", "Свобода", "Дворжак", "Чех"]),
}
_AF = {
    "Нигерия": ("🇳🇬", 25, ["Виктор", "Самуэль", "Эммануэль", "Чиди", "Олу", "Тайво"],
                ["Осимхен", "Окафор", "Эзе", "Адеола", "Нвакали", "Ивоби"]),
    "Гана": ("🇬🇭", 18, ["Кваме", "Коджо", "Йав", "Кофи", "Абеди"], ["Мензах", "Аппиа", "Бойе", "Асамоа", "Партей"]),
    "Сенегал": ("🇸🇳", 18, ["Мамаду", "Исмаила", "Шейх", "Папе", "Ибраима"], ["Диалло", "Ндиайе", "Сарр", "Куяте", "Гуйе"]),
    "Кот-д'Ивуар": ("🇨🇮", 15, ["Яя", "Серж", "Франк", "Вильфрид", "Себастьен"], ["Туре", "Коне", "Бамба", "Кесси", "Зага"]),
    "Камерун": ("🇨🇲", 12, ["Андре", "Эрик", "Самуэль", "Венсан"], ["Мбеумо", "Онана", "Ангисса", "Тоуко"]),
    "Марокко": ("🇲🇦", 12, ["Ашраф", "Хаким", "Юссеф", "Софьян", "Нуссаир"], ["Амрабат", "Эль-Каби", "Буфаль", "Мазрауи", "Сайс"]),
}
_AS = {
    "Япония": ("🇯🇵", 30, ["Такуми", "Каору", "Дайти", "Рицу", "Ватару", "Сюн"],
               ["Минамино", "Мито", "Камада", "Доан", "Эндо", "Ито"]),
    "Корея": ("🇰🇷", 25, ["Мин-Джэ", "Хын-Мин", "Кан-Ин", "Хи-Чхан", "Сын-Хо"], ["Ким", "Сон", "Ли", "Хван", "Пак"]),
    "Иран": ("🇮🇷", 15, ["Мехди", "Сердар", "Алиреза", "Саман"], ["Тареми", "Азмун", "Джаханбахш", "Голизаде"]),
    "Саудовская Аравия": ("🇸🇦", 12, ["Салем", "Фирас", "Мохаммед", "Абдулла"], ["Аль-Давсари", "Аль-Бурайкан", "Аль-Шахрани"]),
    "Австралия": ("🇦🇺", 10, ["Джексон", "Мэтью", "Райли", "Митчелл"], ["Ирвин", "Леки", "Гудвин", "Сутар"]),
    "Узбекистан": ("🇺🇿", 8, ["Эльдор", "Аббосбек", "Жалолиддин", "Отабек"], ["Шомуродов", "Файзуллаев", "Машарипов", "Хусанов"]),
}
_NA = {
    "США": ("🇺🇸", 30, ["Кристиан", "Уэстон", "Тайлер", "Джош", "Брэндон"], ["Пулишич", "Маккенни", "Адамс", "Робинсон", "Тернер"]),
    "Мексика": ("🇲🇽", 30, ["Эдсон", "Ирвинг", "Сантьяго", "Уго", "Рауль"], ["Альварес", "Лосано", "Хименес", "Гальярдо", "Очоа"]),
    "Канада": ("🇨🇦", 15, ["Альфонсо", "Джонатан", "Тажон", "Исмаэль"], ["Дэвис", "Дэвид", "Бьюкенен", "Корне"]),
    "Коста-Рика": ("🇨🇷", 10, ["Кейлор", "Джоэл", "Брайан"], ["Навас", "Кэмпбелл", "Руис"]),
    "Ямайка": ("🇯🇲", 8, ["Леон", "Майкл", "Демарай"], ["Бэйли", "Антонио", "Грей"]),
    "Панама": ("🇵🇦", 7, ["Адальберто", "Анибал", "Хосе"], ["Карраскилья", "Годой", "Фахардо"]),
}
REGIONS: dict[str, dict] = {
    "south_america": {"name": "Южная Америка", "emoji": "🌎", "countries": _SA, "lines": {"GK": 8, "DEF": 24, "MID": 30, "FWD": 38}},
    "europe": {"name": "Европа", "emoji": "🌍", "countries": _EU, "lines": {"GK": 12, "DEF": 30, "MID": 32, "FWD": 26}},
    "africa": {"name": "Африка", "emoji": "🌍", "countries": _AF, "lines": {"GK": 8, "DEF": 36, "MID": 30, "FWD": 26}},
    "asia": {"name": "Азия", "emoji": "🌏", "countries": _AS, "lines": {"GK": 10, "DEF": 26, "MID": 40, "FWD": 24}},
    "north_america": {"name": "Северная и Центральная Америка", "emoji": "🌎", "countries": _NA,
                      "lines": {"GK": 12, "DEF": 32, "MID": 30, "FWD": 26}},
}


def _cfg(config) -> dict:
    return finance.cfg(config)


def _monday(key: str) -> date:
    year, week = key.split("-W")
    return date.fromisocalendar(int(year), int(week), 1)


def seasons_between(a: str, b: str) -> int:
    """Seasons (weeks) from key `a` to key `b`."""
    return (_monday(b) - _monday(a)).days // 7


def age_at(al: ManagerAlumnus, key: str) -> int:
    return al.start_age + max(0, seasons_between(al.joined_key, key))


def rating_at(al: ManagerAlumnus, key: str, config) -> int:
    """The career curve: grow_gap under the peak at the start, linear to the
    peak at `peak_age`, the peak until `decline_age`, then −decline a season."""
    age = age_at(al, key)
    start = al.peak - int(_cfg(config)["filial_grow_gap"])
    if age < al.peak_age:
        span = max(1, al.peak_age - al.start_age)
        return round(start + (al.peak - start) * (age - al.start_age) / span)
    if age <= al.decline_age:
        return al.peak
    return max(40, round(al.peak - float(_cfg(config)["filial_decline"]) * (age - al.decline_age)))


def _level(f: Optional[ManagerFilial], code: str) -> int:
    return int(((f.levels if f else None) or {}).get(code, 0))


def _prices(config, code: str) -> list[int]:
    return [int(x) for x in _cfg(config)[f"filial_{code}_coins"] or []]


def contracts_of(f: ManagerFilial, config) -> int:
    return int(_cfg(config)["filial_contracts"]) + _level(f, "internat")


def every_of(f: ManagerFilial, config) -> int:
    top = _level(f, "internat") >= len(_prices(config, "internat"))
    c = _cfg(config)
    return int(c["filial_every_min"] if top else c["filial_every"])


def _weighted(rng: random.Random, items: dict) -> str:
    total = sum(w for w in items.values())
    roll = rng.uniform(0, total)
    for k, w in items.items():
        roll -= w
        if roll <= 0:
            return k
    return next(iter(items))


def candidates(f: ManagerFilial, base_rating: int, key: str, config) -> list[dict]:
    """The release of season `key` (seeded: the same filial and season give
    the same footballers)."""
    c = _cfg(config)
    rng = random.Random(f"filial:{f.id}:{key}")
    region = REGIONS.get(f.region) or REGIONS["europe"]
    scout = _level(f, "scout")
    count = int(c["filial_candidates"]) + (1 if scout >= 1 else 0)
    top = int(c["filial_potential_max"])
    peak_lo, peak_hi = (list(c["filial_peak_age"]) + [27, 27])[:2]
    retire_lo, retire_hi = (list(c["filial_retire_age"]) + [35, 35])[:2]
    out = []
    for _ in range(count):
        country = _weighted(rng, {k: v[1] for k, v in region["countries"].items()})
        flag, _w, firsts, lasts = region["countries"][country]
        line = _weighted(rng, region["lines"])
        potential = min(top, min(rng.randint(0, top), rng.randint(0, top)) + (1 if scout >= 2 else 0))
        peak = base_rating + potential + _level(f, "fields")
        decline = int(c["filial_decline_age"]) + _level(f, "gym")
        out.append({
            "name": f"{rng.choice(firsts)} {rng.choice(lasts)}", "country": country, "flag": flag,
            "position": rng.choice(POSITIONS[line]), "potential": potential, "peak": peak,
            "peak_age": rng.randint(int(peak_lo), int(peak_hi)), "decline_age": decline,
            "retire_age": max(decline + 1, rng.randint(int(retire_lo), int(retire_hi))),
            "rating": peak - int(c["filial_grow_gap"]),
        })
    return out


def stars(potential: int, config) -> int:
    """The potential the president sees: ★1..5."""
    top = max(1, int(_cfg(config)["filial_potential_max"]))
    return 1 + round(4 * potential / top)


# --- reads ---------------------------------------------------------------------------------------

async def filial_of(db: AsyncSession, club_id: int, lock: bool = False) -> Optional[ManagerFilial]:
    stmt = select(ManagerFilial).where(ManagerFilial.club_id == club_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def club_alumni(db: AsyncSession, club_id: int, key: str) -> list[ManagerAlumnus]:
    """The alumni playing for the club now (the retired ones are marked)."""
    rows = list((await db.execute(
        select(ManagerAlumnus).where(ManagerAlumnus.club_id == club_id, ManagerAlumnus.status == "club").order_by(ManagerAlumnus.id)
    )).scalars().all())
    out = []
    for al in rows:
        if age_at(al, key) > al.retire_age:
            al.status, al.price, al.ended_at = "retired", None, datetime.now(timezone.utc)
            continue
        out.append(al)
    return out


async def used_contracts(db: AsyncSession, f: ManagerFilial, key: str) -> int:
    return sum(1 for al in await club_alumni(db, f.club_id, key) if al.filial_id == f.id)


def wage_of(al: ManagerAlumnus, key: str, club: ManagerClub, snap: dict, config) -> int:
    """A season's wage, like a catalog footballer's of his rating."""
    from app.services import manager_service as ms

    value = ms.value_of(rating_at(al, key, config), config)
    wage = value * config.manager_wage_pct // 100
    return wage * ms._pct(config.manager_division_wage_pct, club.division) // 100 * (100 - snap.get("discount_pct", 0)) // 100


def entry(al: ManagerAlumnus, key: str, config) -> dict:
    """The squad entry of an alumnus (manager_service.build_pool)."""
    return {"key": f"alum:{al.id}", "kind": "alum", "ref": al.id, "name": al.name, "position": al.position,
            "rating": rating_at(al, key, config), "age": age_at(al, key), "country": al.country,
            "flag": _flag(al.country)}


def _flag(country: str) -> str:
    for region in REGIONS.values():
        if country in region["countries"]:
            return region["countries"][country][0]
    return "🌍"


def _al_out(al: ManagerAlumnus, key: str, config, mine: bool = True) -> dict:
    from app.services import manager_service as ms

    rating = rating_at(al, key, config)
    value = ms.value_of(rating, config)
    c = _cfg(config)
    age = age_at(al, key)
    return {
        "id": al.id, "name": al.name, "country": al.country, "flag": _flag(al.country), "position": al.position,
        "age": age, "rating": rating, "value": value, "stars": stars(al.potential, config), "status": al.status,
        "peak_age": al.peak_age, "retire_in": max(0, al.retire_age - age),
        "phase": "рост" if age < al.peak_age else "пик" if age <= al.decline_age else "спад",
        "price": al.price, "goals": al.goals,
        "sell_back": ms._nice(value * config.manager_sell_back_pct / 100) if mine else None,
        "price_min": ms._nice(value * int(c["filial_min_price_pct"]) / 100),
        "price_max": ms._nice(value * int(c["filial_max_price_pct"]) / 100),
    }


async def _refresh(db: AsyncSession, f: ManagerFilial, club: ManagerClub, key: str, config) -> None:
    """A due «выпуск»: candidates while a contract is free."""
    from app.services import manager_service as ms

    if f.pending:
        return
    if await used_contracts(db, f, key) >= contracts_of(f, config):
        return
    if f.last_release_key and seasons_between(f.last_release_key, key) < every_of(f, config):
        return
    f.pending = {"key": key, "candidates": candidates(f, ms._division_rating(club.division, config), key, config)}
    f.last_release_key = key


async def view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    c = _cfg(config)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    key = ms.season_key(now)
    f = await filial_of(db, club.id)
    if f is not None:
        await _refresh(db, f, club, key, config)
    alumni = await club_alumni(db, club.id, key)
    await db.commit()
    history = []
    if f is not None:
        history = list((await db.execute(
            select(ManagerAlumnus).where(ManagerAlumnus.filial_id == f.id, ManagerAlumnus.status != "club")
            .order_by(ManagerAlumnus.id.desc()).limit(20)
        )).scalars().all())
    next_in = None
    if f is not None and not f.pending and f.last_release_key:
        next_in = max(0, every_of(f, config) - seasons_between(f.last_release_key, key))
    buildings = []
    for code, b in BUILDINGS.items():
        prices = _prices(config, code)
        lvl = _level(f, code)
        buildings.append({"code": code, **b, "level": lvl, "max": len(prices),
                          "price": prices[lvl] if lvl < len(prices) else None})
    used = await used_contracts(db, f, key) if f else 0
    return {
        "enabled": bool(c["filial_enabled"]), "open_coins": int(c["filial_open_coins"]), "balance": user.balance,
        "regions": [{"code": k, "name": r["name"], "emoji": r["emoji"],
                     "countries": [{"name": n, "flag": v[0]} for n, v in r["countries"].items()]} for k, r in REGIONS.items()],
        "filial": None if f is None else {
            "region": f.region, "region_name": REGIONS.get(f.region, {}).get("name", f.region), "country": f.country,
            "flag": _flag(f.country), "contracts": contracts_of(f, config), "used": used, "every": every_of(f, config),
            "next_in": next_in, "sold_this_season": f.sold_key == key,
            "pending": [{**cand, "stars": stars(cand["potential"], config), "peak": None, "potential": None}
                        for cand in (f.pending or {}).get("candidates", [])],
        },
        "buildings": buildings,
        "alumni": [_al_out(al, key, config) for al in alumni],
        "history": [{"name": al.name, "flag": _flag(al.country), "position": al.position, "status": al.status,
                     "age": age_at(al, key)} for al in history],
        "window_open": await finance.window_open(db, club, now),
        "squad_max": config.manager_squad_max,
    }


# --- actions -------------------------------------------------------------------------------------

async def _club(db: AsyncSession, user: User) -> ManagerClub:
    from app.services import manager_service as ms

    config = await get_config(db)
    if not _cfg(config)["filial_enabled"]:
        raise ConflictError("Филиалы академий пока закрыты")
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return club


async def _pay(db: AsyncSession, user: User, coins: int, note: str, club: ManagerClub) -> None:
    if coins <= 0:
        return
    locked = await wallet_service.lock_user_for_update(db, user.id)
    await wallet_service.debit_coins(db, locked, coins, TransactionType.manager_filial, note,
                                     related_object_type=RELATED, related_object_id=club.id)


async def open_filial(db: AsyncSession, user: User, region: str, country: str) -> dict:
    club = await _club(db, user)
    config = await get_config(db)
    r = REGIONS.get(region)
    if r is None:
        raise ConflictError("Такого региона нет")
    if country not in r["countries"]:
        raise ConflictError("Эта страна не из выбранного региона")
    if await filial_of(db, club.id) is not None:
        raise ConflictError("Филиал уже построен")
    await _pay(db, user, int(_cfg(config)["filial_open_coins"]), f"Филиал академии: {country}", club)
    try:
        async with db.begin_nested():
            db.add(ManagerFilial(club_id=club.id, region=region, country=country, levels={}))
    except IntegrityError:
        raise ConflictError("Филиал уже построен")
    await db.commit()
    return await view(db, user)


async def build(db: AsyncSession, user: User, code: str) -> dict:
    club = await _club(db, user)
    config = await get_config(db)
    if code not in BUILDINGS:
        raise NotFoundError("Такого здания нет")
    f = await filial_of(db, club.id, lock=True)
    if f is None:
        raise ConflictError("Сначала построй филиал")
    prices = _prices(config, code)
    lvl = _level(f, code)
    if lvl >= len(prices):
        raise ConflictError("Уже максимальный уровень")
    await _pay(db, user, prices[lvl], f"Филиал: {BUILDINGS[code]['name']} ур. {lvl + 1}", club)
    f.levels = {**(f.levels or {}), code: lvl + 1}
    await db.commit()
    return await view(db, user)


async def pick(db: AsyncSession, user: User, index: Optional[int]) -> dict:
    """Takes candidate `index` of the release into the squad, or (None) lets them all go."""
    from app.services import manager_service as ms

    club = await _club(db, user)
    config = await get_config(db)
    f = await filial_of(db, club.id, lock=True)
    if f is None or not f.pending:
        raise ConflictError("Выпуска сейчас нет")
    cands = f.pending.get("candidates") or []
    if index is not None:
        if not 0 <= index < len(cands):
            raise NotFoundError("Такого кандидата нет")
        if await ms._squad_size(db, club) >= config.manager_squad_max:
            raise ConflictError(f"В заявке не больше {config.manager_squad_max} игроков — освободи место")
        cand = cands[index]
        db.add(ManagerAlumnus(
            filial_id=f.id, club_id=club.id, name=cand["name"], country=cand["country"], position=cand["position"],
            potential=int(cand["potential"]), peak=int(cand["peak"]), peak_age=int(cand["peak_age"]),
            decline_age=int(cand["decline_age"]), retire_age=int(cand["retire_age"]),
            start_age=int(_cfg(config)["filial_start_age"]), joined_key=f.pending.get("key") or ms.season_key(datetime.now(timezone.utc)),
        ))
        now = datetime.now(timezone.utc)
        await ms._move(db, club, "in", "filial", {"who": cand["name"], "position": cand["position"], "rating": cand["rating"]}, now)
    f.pending = None
    await db.commit()
    return await view(db, user)


async def _mine(db: AsyncSession, club: ManagerClub, alumnus_id: int, key: str) -> ManagerAlumnus:
    al = await db.get(ManagerAlumnus, alumnus_id, with_for_update=True)
    if al is None or al.club_id != club.id or al.status != "club" or age_at(al, key) > al.retire_age:
        raise NotFoundError("Такого выпускника в клубе нет")
    return al


async def sell_market(db: AsyncSession, user: User, alumnus_id: int) -> dict:
    """The market buys him back at manager_sell_back_pct, once a season per club."""
    from app.services import manager_service as ms

    club = await _club(db, user)
    config = await get_config(db)
    now = datetime.now(timezone.utc)
    key = ms.season_key(now)
    await ms._ensure_window(db, club)
    office = staff.office(club)
    if office.get("alum_sold") == key:
        raise ConflictError("Рынок выкупает одного выпускника за сезон — продай другому президенту")
    al = await _mine(db, club, alumnus_id, key)
    rating = rating_at(al, key, config)
    refund = ms._nice(ms.value_of(rating, config) * config.manager_sell_back_pct / 100)
    await finance.book(db, club, "npc_sale", refund, await finance.upcoming_key(db, now), note=al.name)
    al.status, al.club_id, al.price, al.ended_at = "sold", None, None, now
    staff.save(club, {**office, "alum_sold": key})
    f = await filial_of(db, club.id)
    if f is not None:
        f.sold_key = key
    await ms._move(db, club, "out", "market", {"who": al.name, "position": al.position, "rating": rating}, now, fee=refund)
    await db.commit()
    return await view(db, user)


async def release(db: AsyncSession, user: User, alumnus_id: int) -> dict:
    from app.services import manager_service as ms

    club = await _club(db, user)
    now = datetime.now(timezone.utc)
    key = ms.season_key(now)
    await ms._ensure_window(db, club)
    al = await _mine(db, club, alumnus_id, key)
    al.status, al.club_id, al.price, al.ended_at = "released", None, None, now
    await ms._move(db, club, "out", "released", {"who": al.name, "position": al.position}, now)
    await db.commit()
    return await view(db, user)


def _bounds(al: ManagerAlumnus, key: str, config) -> tuple[int, int]:
    from app.services import manager_service as ms

    value = ms.value_of(rating_at(al, key, config), config)
    c = _cfg(config)
    return ms._nice(value * int(c["filial_min_price_pct"]) / 100), ms._nice(value * int(c["filial_max_price_pct"]) / 100)


async def list_for_sale(db: AsyncSession, user: User, alumnus_id: int, price: Optional[int]) -> dict:
    """Puts him on the presidents' market at `price` (None takes him off)."""
    from app.services import manager_service as ms

    club = await _club(db, user)
    config = await get_config(db)
    key = ms.season_key(datetime.now(timezone.utc))
    al = await _mine(db, club, alumnus_id, key)
    if price is None:
        al.price = None
    else:
        lo, hi = _bounds(al, key, config)
        if not lo <= int(price) <= hi:
            raise ConflictError(f"Цена — от {ms.money(lo)} до {ms.money(hi)}: дешевле нельзя, чтобы не было договорных сделок")
        al.price = int(price)
    await db.commit()
    return await view(db, user)


async def market(db: AsyncSession, user: User) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    key = ms.season_key(datetime.now(timezone.utc))
    rows = list((await db.execute(
        select(ManagerAlumnus, ManagerClub.name).join(ManagerClub, ManagerClub.id == ManagerAlumnus.club_id)
        .where(ManagerAlumnus.status == "club", ManagerAlumnus.price.is_not(None),
               ManagerAlumnus.club_id != (club.id if club else 0))
        .order_by(ManagerAlumnus.id.desc()).limit(60)
    )).all())
    out = []
    for al, club_name in rows:
        if age_at(al, key) > al.retire_age:
            continue
        lo, hi = _bounds(al, key, config)
        out.append({**_al_out(al, key, config, mine=False), "club": club_name, "valid": lo <= (al.price or 0) <= hi})
    return {"lots": out}


async def buy(db: AsyncSession, user: User, alumnus_id: int) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    if not _cfg(config)["filial_enabled"]:
        raise ConflictError("Филиалы академий пока закрыты")
    me = await ms._owned_club(db, user.id)
    if me is None:
        raise NotFoundError("Сначала основай клуб")
    al = await db.get(ManagerAlumnus, alumnus_id)
    if al is None or al.status != "club" or al.price is None or al.club_id is None:
        raise NotFoundError("Этот выпускник уже не продаётся")
    if al.club_id == me.id:
        raise ConflictError("Это твой выпускник")
    clubs = await ms._lock_clubs(db, [me.id, al.club_id])
    buyer, seller = clubs.get(me.id), clubs.get(al.club_id)
    if buyer is None or seller is None or buyer.owner_id == seller.owner_id:
        raise ConflictError("Сделка невозможна")
    al = await db.get(ManagerAlumnus, alumnus_id, with_for_update=True, populate_existing=True)
    now = datetime.now(timezone.utc)
    key = ms.season_key(now)
    if al is None or al.status != "club" or al.price is None or al.club_id != seller.id or age_at(al, key) > al.retire_age:
        raise NotFoundError("Этот выпускник уже не продаётся")
    await ms._ensure_window(db, buyer)
    await ms._ensure_window(db, seller, "Клуб-продавец")
    await finance.ensure_can_transfer(db, buyer)
    lo, hi = _bounds(al, key, config)
    price = int(al.price)
    if not lo <= price <= hi:
        raise ConflictError("Цена устарела — продавец должен обновить её")
    cooldown = int(_cfg(config)["filial_pair_cooldown_seasons"])
    last = (await db.execute(
        select(ManagerAlumniTrade.season_key).where(or_(
            (ManagerAlumniTrade.seller_club_id == seller.id) & (ManagerAlumniTrade.buyer_club_id == buyer.id),
            (ManagerAlumniTrade.seller_club_id == buyer.id) & (ManagerAlumniTrade.buyer_club_id == seller.id),
        )).order_by(ManagerAlumniTrade.id.desc()).limit(1)
    )).scalar_one_or_none()
    if last and seasons_between(last, key) < cooldown:
        raise ConflictError(f"Эти клубы уже менялись выпускниками — следующая сделка между ними через {cooldown - seasons_between(last, key)} сез.")
    if await ms._squad_size(db, buyer) >= config.manager_squad_max:
        raise ConflictError(f"В заявке не больше {config.manager_squad_max} игроков")
    snap = await ms.base_snapshot(db, buyer.owner_id, config)
    reserved = await ms.start_bill(db, buyer, config, snap)
    wage = wage_of(al, key, buyer, snap, config)
    if price + wage > buyer.budget - reserved:
        raise ConflictError(ms._short_of(price + wage, buyer.budget, reserved))
    fee = price * int(_cfg(config)["filial_fee_pct"]) // 100
    up = await finance.upcoming_key(db, now)
    await finance.book(db, buyer, "transfer_out", -price, up, note=al.name)
    await finance.book(db, seller, "transfer_in", price - fee, up, note=al.name)
    rating = rating_at(al, key, config)
    who = {"who": al.name, "position": al.position, "rating": rating}
    await ms._move(db, buyer, "in", "buy", who, now, fee=price, other=seller.name)
    await ms._move(db, seller, "out", "sell", who, now, fee=price - fee, other=buyer.name)
    db.add(ManagerAlumniTrade(alumnus_id=al.id, seller_club_id=seller.id, buyer_club_id=buyer.id, price=price, season_key=key))
    al.club_id, al.price = buyer.id, None
    await db.commit()
    return await market(db, user)


# --- season start (manager_service._prepare_club) -----------------------------------------------

async def pay_wages(db: AsyncSession, club: ManagerClub, key: str, snap: dict, config, now: datetime) -> list[str]:
    """The alumni's wages; one the club can't pay goes to the market for its buy-back."""
    from app.services import manager_service as ms

    notes = []
    for al in await club_alumni(db, club.id, key):
        pay = wage_of(al, key, club, snap, config)
        if pay > club.budget:
            refund = ms._nice(ms.value_of(rating_at(al, key, config), config) * config.manager_sell_back_pct / 100)
            await finance.book(db, club, "npc_sale", refund, key, note=al.name)
            al.status, al.club_id, al.price, al.ended_at = "sold", None, None, now
            notes.append(f"{al.name}: не хватило на зарплату — ушёл, выкуп {ms.money(refund)} в бюджет")
            continue
        await finance.book(db, club, "wages", -pay, key)
    return notes


async def wage_total(db: AsyncSession, club: ManagerClub, key: str, snap: dict, config) -> int:
    return sum(wage_of(al, key, club, snap, config) for al in await club_alumni(db, club.id, key))


async def count(db: AsyncSession, club_id: int, key: str) -> int:
    return len(await club_alumni(db, club_id, key))

