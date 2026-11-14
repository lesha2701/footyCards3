"""«Менеджер» — «Штаб президента»: the club's people.

- Staff: one of the owner's «Жители города» takes a club job (`manager_staff`,
  one per role and per resident). The resident's rarity sets the effect
  (`staff_effects`) and the wage — `staff_wage_pct` of the division grant a
  season, paid at the season start with the squad's wages (unpaid → he
  leaves). Places: `staff_slots` by division. Effects are folded into the
  club's «Клубная база» snapshot (`base_snapshot`), so they freeze into the
  season like the base, within `staff_caps` together with the base:
    coach     — % on every line in league matches;
    physio    — % off the injury chance;
    agent     — % off the footballers' wages;
    marketing — % on the matchday income;
    scout     — % off the catalog loan fees;
    press     — more fans from press conferences (manager_press);
    driver    — the president's car with a driver (status only).
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
    "coach": {"name": "Главный тренер", "emoji": "🧢", "sign": "+", "unit": "% к силе всех линий в лиге"},
    "physio": {"name": "Физиотерапевт", "emoji": "🩺", "sign": "−", "unit": "% к шансу травмы"},
    "agent": {"name": "Агент", "emoji": "🤝", "sign": "−", "unit": "% к зарплатам футболистов"},
    "marketing": {"name": "Директор по маркетингу", "emoji": "📣", "sign": "+", "unit": "% к доходу с матчей"},
    "scout": {"name": "Скаут", "emoji": "🔭", "sign": "−", "unit": "% к цене аренды из каталога"},
    "press": {"name": "Пресс-атташе", "emoji": "🎙", "sign": "+", "unit": "% к итогам пресс-конференций"},
    "driver": {"name": "Шофёр", "emoji": "🚘", "sign": "", "unit": "Возит президента на матчи — статус"},
}
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
    return int(finance._num(((_cfg(config)["staff_effects"] or {}).get(role) or {}).get(rarity)))


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
    return {s.role: effect_of(s.role, s.rarity, config) for s in rows if s.resident_id in owned}


def fold(snap: dict, staff: dict[str, int], config) -> dict:
    """The base snapshot with the staff on top, within the caps."""
    caps = _cfg(config)["staff_caps"] or {}
    cap = lambda key, value: int(min(finance._num(caps.get(key), 90), value))  # noqa: E731
    return {
        **snap,
        "matchday_pct": cap("matchday_pct", snap.get("matchday_pct", 0) + staff.get("marketing", 0)),
        "discount_pct": cap("discount_pct", snap.get("discount_pct", 0) + staff.get("agent", 0)),
        "injury_pct": cap("injury_pct", snap.get("injury_pct", 0) + staff.get("physio", 0)),
        "coach_pct": cap("coach_pct", staff.get("coach", 0)),
        "scout_pct": cap("scout_pct", staff.get("scout", 0)),
        "press_pct": staff.get("press", 0),
        "driver": "driver" in staff,
    }


def coach_mods(mods: dict, base: dict) -> dict:
    pct = finance._num((base or {}).get("coach_pct"))
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
    return notes


# --- hire / fire -----------------------------------------------------------------------------

async def _club(db: AsyncSession, user: User, lock: bool = False) -> ManagerClub:
    from app.services import manager_service as ms

    club = await ms._owned_club(db, user.id, lock=lock)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return club


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
    try:
        async with db.begin_nested():
            db.add(ManagerStaff(club_id=club.id, role=role, resident_id=resident_id, rarity=resident.rarity, wage=wage,
                                hired_at=datetime.now(timezone.utc)))
    except IntegrityError:
        raise ConflictError("Эта должность только что занята")
    await db.commit()
    return await view(db, user)


async def fire(db: AsyncSession, user: User, staff_id: int) -> dict:
    club = await _club(db, user, lock=True)
    row = await db.get(ManagerStaff, staff_id)
    if row is None or row.club_id != club.id:
        raise NotFoundError("Такого сотрудника нет")
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
    return f"{r['sign']}{value}{r['unit']}" if r["sign"] else r["unit"]


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
        staff.append({"id": s.id, "role": s.role, "role_name": ROLES[s.role]["name"], "emoji": ROLES[s.role]["emoji"],
                      "resident_id": r.id, "name": r.name, "icon": r.icon, "image": r.image_path, "rarity": s.rarity,
                      "effect": value, "effect_text": effect_text(s.role, value), "wage": s.wage})
    candidates = [
        {"resident_id": r.id, "name": r.name, "title": r.title, "icon": r.icon, "image": r.image_path, "rarity": r.rarity,
         "wage": wage_of(r.rarity, club.division, config)}
        for r in sorted(owned.values(), key=lambda r: (-RARITIES.index(r.rarity) if r.rarity in RARITIES else 0, r.name))
        if r.id not in hired_ids
    ]
    return {
        "vip": vip, "bundle_stars": int(finance._num(f["staff_bundle_stars"])),
        "staff": staff, "slots": slots_of(club.division, config), "candidates": candidates,
        "roles": [{"code": code, "name": r["name"], "emoji": r["emoji"],
                   "effects": {rar: effect_text(code, effect_of(code, rar, config)) for rar in RARITIES}} for code, r in ROLES.items()],
        "wages": sum(s["wage"] for s in staff), "window": not await ms.is_playing(db, club) and await ms.window_open(db, now),
        "items": [{**i, "owned": _free(i) or i["code"] in have} for i in items(config)],
        "worn": wear_now,
    }
