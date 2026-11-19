"""«Менеджер» — «Штаб президента»: the club's people.

- Staff: one of the owner's «Жители города» takes a club job (`manager_staff`,
  one per role and per resident). The resident's rarity sets the effect
  (`staff_effects`) and the wage — `staff_wage_pct` of the division grant a
  season, paid at the season start with the squad's wages (unpaid → he
  leaves). Places: `staff_slots` by division. Effects are folded into the
  club's «Клубная база» snapshot (`base_snapshot`), so they freeze into the
  season like the base, within `staff_caps` together with the base:
    coach     — % on every line in league matches;
    director  — the sporting director: replacements for the empty places and
                the leaving footballers within his budget (`director`);
    scout     — % off the catalog loan fees;
    academy   — rating points to the academy kids on empty places;
    physio    — % off the injury chance;
    transport — % on every line away, plus the club's fleet (`fleet`: a bus
                and a plane bought for club euros, upkeep each season);
    stadium   — % on every line at home;
    press     — more fans from press conferences (manager_press);
    marketing — % on the matchday income;
    finance   — percentage points off the loan rate (half on deposits).
  Each department has one «поручение» a season (`staff_orders`, `order`).
  The ten seats sit at the round table of the «Штаб» tab; `staff_slots`
  limits how many are taken by division.
- The VIP staff for Stars: «Аналитик» (the «Аналитика Pro» pass, code
  "analytics") and «Помощник» (code "assistant", manager_assistant), one
  bundle "staff_bundle" extends both; their names and skins.
- The president's status: cars and office rooms for coins or Stars.

Skins, cars and rooms are kept as `manager_cosmetics` rows (their codes),
the worn ones in `manager_clubs.office`. Numbers and catalogs:
GameConfig.manager_finance over manager_finance.DEFAULTS."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import TransactionType
from app.models.manager_club import ManagerClub, ManagerCosmetic, ManagerStaff
from app.models.town import TownResident, UserTownResident
from app.models.user import User
from app.services import manager_finance as finance, manager_perks as perks, wallet_service
from app.services.game_config_service import get_config

RARITIES = ("common", "rare", "epic", "legendary")
# `sign` + effect + `unit` is the effect's text ("" sign: no number).
ROLES: dict[str, dict] = {
    # The seats of the round table, clockwise from the president.
    "coach": {"name": "Главный тренер", "dept": "Тренерский штаб", "emoji": "🧢", "sign": "+", "unit": "% к силе всех линий в лиге"},
    "director": {"name": "Спортивный директор", "dept": "Спортивный департамент", "emoji": "🧭", "sign": "", "unit": "вар. замены на каждое место"},
    "scout": {"name": "Главный скаут", "dept": "Скаутинг", "emoji": "🔭", "sign": "−", "unit": "% к цене аренды из каталога"},
    "academy": {"name": "Директор академии", "dept": "Академия", "emoji": "🌱", "sign": "+", "unit": " к рейтингу воспитанников в составе"},
    "physio": {"name": "Главный врач", "dept": "Медицинский центр", "emoji": "🩺", "sign": "−", "unit": "% к шансу травмы"},
    "transport": {"name": "Начальник транспорта", "dept": "Транспортный департамент", "emoji": "🚌", "sign": "+", "unit": "% к силе в гостях"},
    "stadium": {"name": "Директор стадиона", "dept": "Стадион", "emoji": "🏟", "sign": "+", "unit": "% к силе дома"},
    "press": {"name": "Пресс-атташе", "dept": "Пресс-служба", "emoji": "🎙", "sign": "+", "unit": "% к итогам пресс-конференций"},
    "marketing": {"name": "Коммерческий директор", "dept": "Коммерция", "emoji": "📣", "sign": "+", "unit": "% к доходу с матчей"},
    "finance": {"name": "Финансовый директор", "dept": "Финансы", "emoji": "💼", "sign": "−", "unit": " п.п. к ставке кредита"},
}
FLEET_KINDS = ("bus", "plane")
VIP = {
    "analytics": {"role": "analyst", "name": "Аналитик", "emoji": "📊",
                  "about": "Думает за тебя: разбор соперника, совет на тур, оценка сделок, разбор матча, прогноз сезона, алерты по акциям"},
    "assistant": {"role": "assistant", "name": "Помощник", "emoji": "🗂",
                  "about": "Делает за тебя, пока ты офлайн: спонсоры, пустые места, продления, план на матч, события и пресс-конференции — по твоим правилам и в пределах лимита"},
}
VIP_ROLES = {v["role"]: code for code, v in VIP.items()}
BUNDLE = "staff_bundle"
ITEM_KINDS = ("skin", "car", "room")
NAME_MAX = 20
RELATED = "manager_club"


def _cfg(config) -> dict:
    return finance.cfg(config)


def effect_of(role: str, rarity: str, config) -> int:
    # A stored override written before a role existed falls back to the defaults.
    table = {**finance.DEFAULTS["staff_effects"], **(_cfg(config)["staff_effects"] or {})}
    return int(finance._num((table.get(role) or {}).get(rarity)))


def wage_of(rarity: str, division: int, config) -> int:
    from app.services import manager_service as ms

    pct = finance._num((_cfg(config)["staff_wage_pct"] or {}).get(rarity))
    return ms._nice(finance.grant_of(division, config) * pct / 100) if pct > 0 else 0


def slots_of(division: int, config) -> int:
    slots = list(_cfg(config)["staff_slots"] or [3])
    return int(slots[min(max(0, division - 1), len(slots) - 1)])


# --- the office JSON -------------------------------------------------------------------------

def office(club: Optional[ManagerClub]) -> dict:
    return dict((club.office if club else None) or {})


def save(club: ManagerClub, data: dict) -> None:
    club.office = data
    flag_modified(club, "office")


# --- staff rows and their effects ------------------------------------------------------------

async def staff_of(db: AsyncSession, club_id: int) -> list[ManagerStaff]:
    return list((await db.execute(select(ManagerStaff).where(ManagerStaff.club_id == club_id).order_by(ManagerStaff.id))).scalars().all())


async def _owned_residents(db: AsyncSession, owner_id: int) -> dict[int, TownResident]:
    rows = (await db.execute(select(UserTownResident).where(UserTownResident.user_id == owner_id))).scalars().all()
    return {r.resident_id: r.resident for r in rows if r.resident is not None and r.copies > 0}


async def effects(db: AsyncSession, owner_id: int, config) -> dict[str, int]:
    """{role: effect} of the owner's club staff whose resident he still owns."""
    club = (await db.execute(select(ManagerClub).where(ManagerClub.owner_id == owner_id))).scalar_one_or_none()
    if club is None:
        return {}
    rows = await staff_of(db, club.id)
    if not rows:
        return {}
    owned = await _owned_residents(db, owner_id)
    out = {s.role: effect_of(s.role, s.rarity, config) for s in rows if s.resident_id in owned}
    if "transport" in out:  # the fleet works with a head of transport
        for v in fleet_items(club, config).values():
            out["fleet_away"] = out.get("fleet_away", 0) + int(finance._num(v.get("away_pct")))
            out["fleet_injury"] = out.get("fleet_injury", 0) + int(finance._num(v.get("injury_pct")))
    return out


def fold(snap: dict, staff: dict[str, int], config) -> dict:
    """The base snapshot with the staff on top, within the caps."""
    caps = _cfg(config)["staff_caps"] or {}
    cap = lambda key, value: int(min(finance._num(caps.get(key), 90), value))  # noqa: E731
    return {
        **snap,
        "matchday_pct": cap("matchday_pct", snap.get("matchday_pct", 0) + staff.get("marketing", 0)),
        "injury_pct": cap("injury_pct", snap.get("injury_pct", 0) + staff.get("physio", 0) + staff.get("fleet_injury", 0)),
        "coach_pct": cap("coach_pct", staff.get("coach", 0)),
        "scout_pct": cap("scout_pct", staff.get("scout", 0)),
        "press_pct": staff.get("press", 0),
        "away_pct": cap("away_pct", staff.get("transport", 0) + staff.get("fleet_away", 0)),
        "stadium_pct": cap("stadium_pct", staff.get("stadium", 0)),
        "academy_pts": cap("academy_pts", staff.get("academy", 0)),
        "finance_pts": cap("finance_pts", staff.get("finance", 0)),
        "transport": "transport" in staff,
    }


def coach_mods(mods: dict, base: dict, home: Optional[bool] = None) -> dict:
    """The head coach on every line; the stadium director at home, the
    transport department away."""
    base = base or {}
    pct = finance._num(base.get("coach_pct"))
    if home is True:
        pct += finance._num(base.get("stadium_pct"))
    elif home is False:
        pct += finance._num(base.get("away_pct"))
    if pct <= 0:
        return mods
    return {line: mods.get(line, 0) + pct for line in ("GK", "DEF", "MID", "FWD")}


async def wages(db: AsyncSession, club_id: int) -> int:
    return sum(s.wage for s in await staff_of(db, club_id))


async def pay(db: AsyncSession, club: ManagerClub, key: str, config) -> list[str]:
    """The season start (club locked): the staff's wages; whoever can't be paid leaves."""
    notes = []
    owned = await _owned_residents(db, club.owner_id)
    for s in await staff_of(db, club.id):
        resident = owned.get(s.resident_id)
        if resident is None:
            await db.delete(s)
            continue
        if s.wage > club.budget:
            await db.delete(s)
            notes.append(f"{resident.name}: не хватило на зарплату — ушёл из штаба")
            continue
        if s.wage:
            await finance.book(db, club, "staff_wages", -s.wage, key, note=resident.name)
    # The fleet's upkeep; a vehicle the club can't keep is sold off.
    data = office(club)
    fleet = dict(data.get("fleet") or {})
    grant = finance.grant_of(club.division, config)
    for kind, it in fleet_items(club, config).items():
        cost = int(grant * finance._num(it.get("upkeep_pct")) / 100)
        if cost > club.budget:
            fleet[kind] = 0
            notes.append(f"{it['name']}: не хватило на содержание — продан")
            continue
        await finance.book(db, club, "fleet_upkeep", -cost, key, ref=f"fleet_upkeep:{key}:{kind}", note=it["name"])
    if fleet != (data.get("fleet") or {}):
        data["fleet"] = fleet
        save(club, data)
    return notes


# --- hire / fire -----------------------------------------------------------------------------

async def _club(db: AsyncSession, user: User, lock: bool = False) -> ManagerClub:
    from app.services import manager_service as ms

    club = await ms._owned_club(db, user.id, lock=lock)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return club


async def _settle_town(db: AsyncSession, user_id: int, config) -> None:
    """A resident on the staff leaves the town's «Рабочие места» (and a fired
    one comes back): the town's rent so far is settled at the old rate first."""
    from app.services import town_service
    from app.services.wallet_service import lock_user_for_update

    await lock_user_for_update(db, user_id)
    await town_service._settle_before_population_change(db, config, user_id)


async def hire(db: AsyncSession, user: User, resident_id: int, role: str) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    if role not in ROLES:
        raise NotFoundError("Такой должности нет")
    club = await _club(db, user, lock=True)
    await ms._ensure_window(db, club)
    resident = (await _owned_residents(db, user.id)).get(resident_id)
    if resident is None:
        raise NotFoundError("Такого жителя у тебя нет")
    rows = await staff_of(db, club.id)
    if any(s.role == role for s in rows):
        raise ConflictError(f"Должность «{ROLES[role]['name']}» уже занята — сначала освободи её")
    if any(s.resident_id == resident_id for s in rows):
        raise ConflictError(f"{resident.name} уже работает в штабе")
    if len(rows) >= slots_of(club.division, config):
        raise ConflictError(f"В штабе {ms.division_name(club.division).lower()} не больше {slots_of(club.division, config)} человек")
    wage = wage_of(resident.rarity, club.division, config)
    reserved = await ms.start_bill(db, club, config)
    if wage > club.budget - reserved:
        raise ConflictError(ms._short_of(wage, club.budget, reserved))
    await _settle_town(db, user.id, config)
    try:
        async with db.begin_nested():
            db.add(ManagerStaff(club_id=club.id, role=role, resident_id=resident_id, rarity=resident.rarity, wage=wage,
                                hired_at=datetime.now(timezone.utc)))
    except IntegrityError:
        raise ConflictError("Эта должность только что занята")
    if role == "coach":  # «Главный тренер»: his character is rolled at the hiring
        from app.services import manager_coach as coach

        data = office(club)
        data["coach"] = {"resident_id": resident_id, "trait": coach.roll()}
        save(club, data)
    await db.commit()
    return await view(db, user)


async def fire(db: AsyncSession, user: User, staff_id: int) -> dict:
    club = await _club(db, user, lock=True)
    row = await db.get(ManagerStaff, staff_id)
    if row is None or row.club_id != club.id:
        raise NotFoundError("Такого сотрудника нет")
    await _settle_town(db, user.id, await get_config(db))
    if row.role == "coach":
        data = office(club)
        data.pop("coach", None)
        save(club, data)
    await db.delete(row)
    await db.commit()
    return await view(db, user)


# --- VIP names, items (skins, cars, rooms) ---------------------------------------------------

def items(config) -> list[dict]:
    out = []
    for raw in _cfg(config)["staff_items"] or []:
        if not isinstance(raw, dict) or raw.get("kind") not in ITEM_KINDS or not raw.get("code"):
            continue
        out.append({"code": str(raw["code"])[:32], "kind": raw["kind"], "role": raw.get("role"), "name": str(raw.get("name") or raw["code"])[:40],
                    "about": str(raw.get("about") or "")[:80], "art": raw.get("art") or {},
                    "coins": max(0, int(finance._num(raw.get("coins")))), "stars": max(0, int(finance._num(raw.get("stars"))))})
    return out


def item(config, code: str) -> Optional[dict]:
    return next((i for i in items(config) if i["code"] == code), None)


def is_item(code: str, config) -> bool:
    return item(config, code) is not None


async def _owned_codes(db: AsyncSession, club_id: int) -> set[str]:
    return set((await db.execute(select(ManagerCosmetic.code).where(ManagerCosmetic.club_id == club_id))).scalars().all())


def _free(i: dict) -> bool:
    return i["coins"] == 0 and i["stars"] == 0


async def buy_item(db: AsyncSession, user: User, code: str) -> dict:
    """A skin, a car or a room for coins (the Stars ones go through manager_shop)."""
    config = await get_config(db)
    i = item(config, code)
    if i is None:
        raise NotFoundError("Такого предмета нет")
    if i["coins"] <= 0:
        raise ConflictError("Этот предмет продаётся только за звёзды" if i["stars"] else "Он и так бесплатный")
    club = await _club(db, user, lock=True)
    if code in await _owned_codes(db, club.id):
        raise ConflictError("Уже куплено")
    locked = await wallet_service.lock_user_for_update(db, user.id)
    await wallet_service.debit_coins(db, locked, i["coins"], TransactionType.manager_cosmetic, f"Штаб президента: {i['name']}",
                                     related_object_type=RELATED, related_object_id=club.id)
    db.add(ManagerCosmetic(club_id=club.id, code=code))
    _wear(club, i)
    await db.commit()
    return await view(db, user)


def stars_order(club: ManagerClub, code: str, config) -> tuple[str, str, str, int]:
    """manager_shop's Stars flow for the VIP bundle and the items."""
    from app.services import manager_service as ms

    if code == BUNDLE:
        stars = int(finance._num(_cfg(config)["staff_bundle_stars"]))
        if stars <= 0:
            raise ConflictError("Сейчас не продаётся")
        days = int(finance._num(_cfg(config)["assistant_days"], 30))
        return f"manager:{code}", "Штаб: аналитик + помощник", f"«{club.name}»: аналитик и помощник на {days} дн.", stars
    i = item(config, code)
    if i is None or i["stars"] <= 0:
        raise ConflictError("Этот предмет за звёзды не продаётся")
    return f"manager:{code}", i["name"], f"Штаб президента «{club.name}»: {i['name']}", i["stars"]


def stars_price(code: str, config) -> int:
    if code == BUNDLE:
        return int(finance._num(_cfg(config)["staff_bundle_stars"]))
    i = item(config, code)
    return i["stars"] if i else 0


def deliver_stars(db: AsyncSession, club: ManagerClub, code: str, config, owned: set[str]) -> dict:
    """Paid already — never refuses."""
    if code == BUNDLE:
        days = int(finance._num(_cfg(config)["assistant_days"], 30))
        perks.extend(club, "analytics", days)
        perks.extend(club, "assistant", days)
        return {"kind": "manager_staff", "name": "Штаб: аналитик + помощник"}
    i = item(config, code) or {"code": code, "name": code, "kind": "skin", "role": None}
    if code not in owned:
        db.add(ManagerCosmetic(club_id=club.id, code=code))
    _wear(club, i)
    return {"kind": "manager_staff_item", "name": i["name"]}


def _wear(club: ManagerClub, i: dict) -> None:
    data = office(club)
    if i["kind"] == "skin" and i.get("role") in VIP_ROLES:
        data["skins"] = {**(data.get("skins") or {}), i["role"]: i["code"]}
    elif i["kind"] in ("car", "room"):
        data[i["kind"]] = i["code"]
    save(club, data)


async def wear(db: AsyncSession, user: User, code: str) -> dict:
    config = await get_config(db)
    i = item(config, code)
    if i is None:
        raise NotFoundError("Такого предмета нет")
    club = await _club(db, user, lock=True)
    if not _free(i) and code not in await _owned_codes(db, club.id):
        raise ConflictError("Сначала купи")
    _wear(club, i)
    await db.commit()
    return await view(db, user)


async def rename(db: AsyncSession, user: User, role: str, name: str) -> dict:
    if role not in VIP_ROLES:
        raise NotFoundError("Такой должности нет")
    clean = " ".join(str(name or "").split())[:NAME_MAX]
    if len(clean) < 2:
        raise ConflictError("Имя — от 2 букв")
    club = await _club(db, user, lock=True)
    data = office(club)
    data["names"] = {**(data.get("names") or {}), role: clean}
    save(club, data)
    await db.commit()
    return await view(db, user)


DEFAULT_NAMES = {"assistant": "Алиса", "analyst": "Марк"}


def vip_name(club: Optional[ManagerClub], role: str) -> str:
    return (office(club).get("names") or {}).get(role) or DEFAULT_NAMES.get(role, "")


def worn(club: Optional[ManagerClub], config) -> dict:
    """{"assistant": item, "analyst": item, "car": item, "room": item} — the
    default (free) item of each when nothing is worn."""
    data = office(club)
    all_items = items(config)
    out = {}
    for role in VIP_ROLES:
        code = (data.get("skins") or {}).get(role)
        out[role] = next((i for i in all_items if i["code"] == code), None) or next(
            (i for i in all_items if i["kind"] == "skin" and i["role"] == role and _free(i)), None)
    for kind in ("car", "room"):
        code = data.get(kind)
        out[kind] = next((i for i in all_items if i["code"] == code), None) or next(
            (i for i in all_items if i["kind"] == kind and _free(i)), None)
    return out


# --- view ------------------------------------------------------------------------------------

def effect_text(role: str, value: int) -> str:
    r = ROLES[role]
    if role == "director":
        return f"{value} {r['unit']}"
    return f"{r['sign']}{value}{r['unit']}" if r["sign"] else r["unit"]


def coach_card(club: ManagerClub, resident: TownResident) -> dict:
    from app.services import manager_coach as coach

    trait = coach.trait_for(club, resident.id)
    return coach.out({**coach.TRAITS[trait], "trait": trait, "person": resident.name, "auto": coach.auto(club)})


async def view(db: AsyncSession, user: User) -> dict:
    from app.services import manager_assistant as assistant, manager_service as ms

    config = await get_config(db)
    club = await _club(db, user)
    f = _cfg(config)
    owned = await _owned_residents(db, user.id)
    rows = await staff_of(db, club.id)
    hired_ids = {s.resident_id for s in rows}
    now = datetime.now(timezone.utc)
    have = await _owned_codes(db, club.id)
    wear_now = worn(club, config)
    vip = []
    for code, v in VIP.items():
        stars, days = perks._price(code, config)
        end = perks.until(club, code)
        vip.append({
            "code": code, "role": v["role"], "title": v["name"], "emoji": v["emoji"], "about": v["about"],
            "name": vip_name(club, v["role"]), "stars": stars, "days": days, "active": perks.active(club, code, now),
            "until": end.isoformat() if end else None, "skin": wear_now.get(v["role"]),
            "trial": v["role"] == "assistant" and assistant.trial_available(club, config),
        })
    staff = []
    for s in rows:
        r = owned.get(s.resident_id)
        if r is None:
            continue
        value = effect_of(s.role, s.rarity, config)
        if s.role not in ROLES:
            continue
        staff.append({"id": s.id, "role": s.role, "role_name": ROLES[s.role]["name"], "dept": ROLES[s.role]["dept"], "emoji": ROLES[s.role]["emoji"],
                      "resident_id": r.id, "name": r.name, "icon": r.icon, "image": r.image_path, "rarity": s.rarity,
                      "effect": value, "effect_text": effect_text(s.role, value), "wage": s.wage,
                      **({"coach": coach_card(club, r)} if s.role == "coach" else {})})
    candidates = [
        {"resident_id": r.id, "name": r.name, "title": r.title, "icon": r.icon, "image": r.image_path, "rarity": r.rarity,
         "wage": wage_of(r.rarity, club.division, config)}
        for r in sorted(owned.values(), key=lambda r: (-RARITIES.index(r.rarity) if r.rarity in RARITIES else 0, r.name))
        if r.id not in hired_ids
    ]
    return {
        "vip": vip, "bundle_stars": int(finance._num(f["staff_bundle_stars"])),
        "staff": staff, "slots": slots_of(club.division, config), "candidates": candidates,
        "roles": [{"code": code, "name": r["name"], "dept": r["dept"], "emoji": r["emoji"],
                   "effects": {rar: effect_text(code, effect_of(code, rar, config)) for rar in RARITIES}} for code, r in ROLES.items()],
        "wages": sum(s["wage"] for s in staff), "window": not await ms.is_playing(db, club) and await ms.window_open(db, now),
        "items": [{**i, "owned": _free(i) or i["code"] in have} for i in items(config)],
        "worn": wear_now,
        "orders": await _orders_view(db, club, config),
        "fleet": _fleet_view(club, config),
    }



# --- «Транспортный департамент»: the club's fleet ------------------------------------------

def fleet_cfg(config) -> dict[str, list[dict]]:
    raw = _cfg(config).get("fleet") or finance.DEFAULTS["fleet"]
    return {kind: [i for i in (raw.get(kind) or []) if isinstance(i, dict) and i.get("code")] for kind in FLEET_KINDS}


def fleet_levels(club: ManagerClub) -> dict[str, int]:
    data = office(club).get("fleet") or {}
    return {kind: max(0, int(finance._num(data.get(kind)))) for kind in FLEET_KINDS}


def fleet_items(club: ManagerClub, config) -> dict[str, dict]:
    """The vehicle of each kind the club has now."""
    levels, table = fleet_levels(club), fleet_cfg(config)
    return {kind: table[kind][min(level, len(table[kind])) - 1] for kind, level in levels.items() if level > 0 and table[kind]}


async def buy_fleet(db: AsyncSession, user: User, kind: str) -> dict:
    """The next vehicle of `kind` for club euros (window only, needs a head of transport)."""
    from app.services import manager_budget, manager_service as ms

    config = await get_config(db)
    if kind not in FLEET_KINDS:
        raise NotFoundError("Такого транспорта нет")
    club = await _club(db, user, lock=True)
    await ms._ensure_window(db, club)
    if not any(s.role == "transport" for s in await staff_of(db, club.id)):
        raise ConflictError("Сначала назначь начальника транспортного департамента")
    levels, table = fleet_levels(club), fleet_cfg(config)
    if levels[kind] >= len(table[kind]):
        raise ConflictError("Это уже лучший транспорт")
    nxt = table[kind][levels[kind]]
    price = int(finance.grant_of(club.division, config) * finance._num(nxt.get("price_pct")) / 100)
    reserved = await ms.start_bill(db, club, config)
    if price > club.budget - reserved:
        raise ConflictError(ms._short_of(price, club.budget, reserved))
    key = await finance.club_key(db, club)
    await finance.book(db, club, "fleet", -price, key, note=nxt.get("name"))
    data = office(club)
    data["fleet"] = {**(data.get("fleet") or {}), kind: levels[kind] + 1}
    save(club, data)
    manager_budget.act(club, key)
    await db.commit()
    return await view(db, user)


def _fleet_view(club: ManagerClub, config) -> dict:
    levels, table = fleet_levels(club), fleet_cfg(config)
    grant = finance.grant_of(club.division, config)
    kinds = []
    for kind in FLEET_KINDS:
        items_ = [{"code": i["code"], "name": i.get("name", i["code"]), "emoji": i.get("emoji", ""),
                   "price": int(grant * finance._num(i.get("price_pct")) / 100), "upkeep": int(grant * finance._num(i.get("upkeep_pct")) / 100),
                   "away_pct": finance._num(i.get("away_pct")), "injury_pct": finance._num(i.get("injury_pct"))} for i in table[kind]]
        kinds.append({"kind": kind, "title": "Автобус" if kind == "bus" else "Самолёт", "level": min(levels[kind], len(items_)), "items": items_})
    return {"kinds": kinds}


# --- «Поручения» -----------------------------------------------------------------------------

def orders_cfg(config) -> dict[str, dict]:
    return {k: v for k, v in (_cfg(config).get("staff_orders") or finance.DEFAULTS["staff_orders"]).items() if k in ROLES and isinstance(v, dict)}


async def _orders_done(db: AsyncSession, club_id: int, key: str) -> set[str]:
    from app.models.manager_club import ManagerLedger

    refs = (await db.execute(select(ManagerLedger.ref).where(
        ManagerLedger.club_id == club_id, ManagerLedger.ref.like(f"order:%:{key}")))).scalars().all()
    return {r.split(":")[1] for r in refs if r}


async def order(db: AsyncSession, user: User, role: str, now: Optional[datetime] = None) -> dict:
    """A department's «поручение» of the season: paid once (ledger ref), its
    fans now, its form for the next rounds of the running league, or an
    injured footballer back."""
    from app.models.manager_club import ManagerLeague
    from app.services import manager_budget, manager_service as ms

    config = await get_config(db)
    o = orders_cfg(config).get(role)
    if o is None:
        raise NotFoundError("У этого департамента нет поручений")
    club = await _club(db, user, lock=True)
    if not any(s.role == role for s in await staff_of(db, club.id)):
        raise ConflictError(f"Сначала назначь: {ROLES[role]['name']}")
    league = None
    if club.league_id:
        league = (await db.execute(select(ManagerLeague).where(ManagerLeague.id == club.league_id).with_for_update())).scalar_one_or_none()
    running = league is not None and league.status == "active" and league.rounds_played < len((league.state or {}).get("fixtures") or [])
    form, rounds = finance._num(o.get("form_pct")), int(finance._num(o.get("form_rounds")))
    if (form and rounds > 0 or o.get("heal")) and not running:
        raise ConflictError("Это поручение — во время сезона, между турами")
    hurt_key = None
    if o.get("heal"):
        hurt = ((league.state or {}).get("injuries") or {}).get(str(club.id)) or {}
        out = [(int(v.get("back", 0)), k) for k, v in hurt.items() if int(v.get("back", 0)) > league.rounds_played]
        if not out:
            raise ConflictError("Травмированных нет — врачу некого лечить")
        hurt_key = max(out)[1]
    key = await finance.club_key(db, club, now)
    cost = int(finance.grant_of(club.division, config) * finance._num(o.get("cost_pct")) / 100)
    if cost > club.budget:
        raise ConflictError(f"Не хватает бюджета: нужно {ms.money(cost)}")
    if not await finance.book(db, club, "staff_order", -cost, key, ref=f"order:{role}:{key}", note=o.get("title")):
        raise ConflictError("Это поручение уже было в этом сезоне")
    fans = int(finance._num(o.get("fans")))
    if fans:
        club.fans_bonus = max(0, int(club.fans_bonus or 0) + fans)
    if form and rounds > 0:
        start = league.rounds_played
        club.buffs = [b for b in (club.buffs or []) if b.get("league_id") == league.id] + [
            {"pct": form, "league_id": league.id, "from": start, "to": start + rounds, "order": role}]
        flag_modified(club, "buffs")
    if hurt_key:
        state = dict(league.state or {})
        state["injuries"][str(club.id)][hurt_key]["back"] = league.rounds_played
        league.state = state
        flag_modified(league, "state")
    manager_budget.act(club, key)
    await db.commit()
    return await view(db, user)


async def _orders_view(db: AsyncSession, club: ManagerClub, config) -> dict[str, dict]:
    key = await finance.club_key(db, club)
    done = await _orders_done(db, club.id, key)
    grant = finance.grant_of(club.division, config)
    return {role: {"emoji": o.get("emoji", ""), "title": o.get("title", ""), "about": o.get("about", ""),
                   "cost": int(grant * finance._num(o.get("cost_pct")) / 100), "fans": int(finance._num(o.get("fans"))),
                   "form_pct": finance._num(o.get("form_pct")), "form_rounds": int(finance._num(o.get("form_rounds"))),
                   "season": bool(o.get("heal")) or bool(finance._num(o.get("form_pct"))), "done": role in done}
            for role, o in orders_cfg(config).items()}


# --- the sporting director -------------------------------------------------------------------

DIRECTOR_NEEDS = 4


async def director(db: AsyncSession, user: User, budget: Optional[int] = None) -> dict:
    """The sporting director's picks: for each empty place of the XI and each
    footballer whose contract runs out, `effect` catalog footballers the club
    can loan or buy within the president's budget for him (`office["director_budget"]`)."""
    from app.services import manager_service as ms
    from app.services.club_formation_service import get_formation_slots
    from app.services.lineup_service import on_ideal_position

    config = await get_config(db)
    club = await _club(db, user, lock=budget is not None)
    row = next((s for s in await staff_of(db, club.id) if s.role == "director"), None)
    owned = await _owned_residents(db, user.id)
    if row is None or row.resident_id not in owned:
        raise ConflictError("Назначь спортивного директора в штабе")
    grant = finance.grant_of(club.division, config)
    data = office(club)
    if budget is not None:
        data["director_budget"] = max(0, min(grant * 2, int(budget)))
        save(club, data)
        await db.commit()
    limit = int(data.get("director_budget") or grant // 4)
    count = max(1, effect_of("director", row.rarity, config))
    squad = await ms.squad_view(db, club, config)
    slots = {sl.code: sl for sl in get_formation_slots(ms.tactics.clean_formation(club.formation))}
    needs = []
    for kid in [p for p in squad["xi"] if p["kind"] == "kid"]:
        slot = slots.get(kid["slot"])
        if slot is not None:
            needs.append({"why": "empty", "title": f"Пустое место: {slot.ideal_position.value}", "line": slot.category,
                          "position": slot.ideal_position})
    for n in await ms._npcs(db, club.id):
        if n.seasons_left <= 0 and not n.auto:
            p = await db.get(ms.Player, n.player_id)
            if p is not None:
                needs.append({"why": "leaving", "title": f"Уходит {p.display_name} ({p.position.value}, {p.rating})",
                              "line": ms._category(p.position), "position": p.position})
    out = []
    seen: set[int] = set()
    for need in needs[:DIRECTOR_NEEDS]:
        page = await ms.npc_catalog(db, user, need["line"], None, 0, None, "rating", True)
        options = []
        for p in page["players"]:
            if p["taken_by"] or p["player_id"] in seen:
                continue
            loan, buy = p["loan_fee"] + p["wage_now"] <= limit, p["value"] + p["wage_now"] <= limit
            if loan or buy:
                options.append({**{k: p[k] for k in ("player_id", "name", "position", "rating", "club", "loan_fee", "value", "wage_now")},
                                "can_loan": loan, "can_buy": buy,
                                "fits": on_ideal_position(ms.Position(p["position"]), need["position"])})
        options.sort(key=lambda o: (not o["fits"], -o["rating"]))
        picks = options[:count]
        seen.update(o["player_id"] for o in picks)
        out.append({"why": need["why"], "title": need["title"], "options": picks})
    resident = owned[row.resident_id]
    return {"name": resident.name, "icon": resident.icon, "image": resident.image_path, "rarity": row.rarity, "count": count,
            "budget": limit, "grant": grant, "window": await ms.window_open(db, datetime.now(timezone.utc)) and not await ms.is_playing(db, club),
            "needs": out}
