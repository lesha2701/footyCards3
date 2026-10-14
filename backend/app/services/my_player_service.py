"""«Мой игрок»: the user's own footballer.

- Built once in a constructor (name, number, position, appearance); name,
  number and appearance can be changed any time, the position only within
  its line (e.g. ST -> LW).
- Two attributes, the same the whole game uses for cards: attack and
  defense (Player.attack_rating / defense_rating). The overall rating is
  their average, as for every other card (player_stats_service).
- XP accrues on the user row (User.my_player_xp) from every rewarded game
  action — see `grant_reward_xp`, called by wallet_service.credit_coins under
  the user's row lock — with a daily cap. Levels turn XP into attribute
  points the player spends on attack/defense.
- The rating is capped by config.my_player_rating_cap; the frame tier
  (bronze -> legend) follows the rating.
- Game modes field it through `engine_card`, a duck-typed stand-in for a
  UserCard (same shape the tournament engine reads). Only «Карьера тренера»
  uses it for now (career_service).
- Stage 2: a card skill (any catalog skill that fits the position and acts
  in the tournament engine), bought and leveled exactly like a card skill; a daily
  training mini-game (XP on top of the daily cap); cosmetics for coins
  (accessory + card background); a rating leaderboard (all / friends).
- Extra trainings (up to config max a day) for coins or Telegram Stars, and
  «Имущество» items for Stars (lifestyle_service handles coin purchases) —
  Stars go through stars_payment_service (`create_stars_invoice` /
  `validate_stars_purchase` / `deliver_stars_purchase`).
- The skill is assigned / upgraded / replaced with skill tokens + coins at
  exactly the card-skill prices (GameConfig.card_skill_*), same rules.

Every number lives in GameConfig.my_player_*.
"""
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card_skill import CardSkill
from app.models.enums import Position, Rarity, TransactionType
from app.models.my_player import MyPlayer
from app.models.user import User
from app.services.card_skill_catalog import LEVEL_ROMAN, MAX_SKILL_LEVEL, SKILL_DEFINITIONS, SKILL_ORDER
from app.services.card_skill_effects import effect_for_card
from app.services.card_skill_service import allowed_positions
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS
from app.services.player_stats_service import compute_default_attack_defense

ATTRS = ("atk", "def")
ATTR_LABELS = {"atk": "Атака", "def": "Защита"}
ATTR_MAX = 99
# Starting overall rating; the attack/defense split follows the position,
# exactly like a pack card's default split (compute_default_attack_defense).
START_RATING = 52

# Number of choices per appearance option (indexes 0..n-1); the frontend
# constructor (components/myPlayer/PlayerAvatar.tsx) draws the same sets.
APPEARANCE_OPTIONS = {"skin": 6, "hair": 14, "hair_color": 7, "beard": 5, "eye_color": 6, "kit": 10, "kit_pattern": 4}

TIERS = ("bronze", "silver", "gold", "legend")
TIER_LABELS = {"bronze": "Бронза", "silver": "Серебро", "gold": "Золото", "legend": "Легенда"}
# Engine/UI rarity equivalent of each frame (the engine reads card rarity).
TIER_RARITY = {"bronze": Rarity.common, "silver": Rarity.rare, "gold": Rarity.epic, "legend": Rarity.legendary}

# The attribute that matters most at a position (UI hint only).
_DEFENSIVE_POSITIONS = {Position.GK, Position.LB, Position.CB, Position.RB, Position.LWB, Position.RWB, Position.CDM}

# Rewarded game actions that grant XP (coins credited with these types).
XP_TX_TYPES = frozenset({
    TransactionType.daily_reward, TransactionType.game_reward, TransactionType.match_reward,
    TransactionType.tactico_reward, TransactionType.career_reward, TransactionType.task_reward,
    TransactionType.bingo_reward, TransactionType.player_tournament_match_reward,
    TransactionType.club_tournament_match_reward, TransactionType.stratego_reward,
})

# Cosmetics catalog (what exists and where it is drawn); prices live in
# GameConfig.my_player_cosmetic_prices. The frontend draws the same codes
# (components/myPlayer/PlayerAvatar.tsx).
COSMETICS = {
    "headband": ("accessory", "Повязка на голову"),
    "earring": ("accessory", "Серьга"),
    "chain": ("accessory", "Цепочка"),
    "goggles": ("accessory", "Спортивные очки"),
    "bg_sunset": ("background", "Фон «Закат»"),
    "bg_neon": ("background", "Фон «Неон»"),
    "bg_gold": ("background", "Фон «Золотой стадион»"),
}
COSMETIC_KINDS = ("accessory", "background")

TRAINING_MAX_HITS = 3
# A run must take at least this long (three timed shots) and be finished
# within the TTL — the client reports hits, so the reward is kept small
# and once a day.
TRAINING_MIN_SECONDS = 4
TRAINING_TTL = timedelta(minutes=5)

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё .'\-]{1,19}$")
_BANNED_ROOTS = (
    "хуй", "хуе", "хуё", "хуя", "пизд", "ебат", "ебан", "еблан", "ёба", "уеб", "уёб", "выеб", "бляд", "блят",
    "мудак", "мудил", "пидор", "пидар", "гандон", "залуп", "шлюх", "дроч", "манда",
    "fuck", "shit", "bitch", "cunt", "dick", "nigg", "fag", "whore", "porn",
)


def category_of(position: Position) -> str:
    return next(cat for cat, positions in CATEGORY_POSITIONS.items() if position in positions)


def start_attributes(position: Position) -> dict[str, int]:
    attack, defense = compute_default_attack_defense(START_RATING, position)
    return {"atk": attack, "def": defense}


def key_attr(position: Position) -> str:
    return "def" if position in _DEFENSIVE_POSITIONS else "atk"


def attributes_of(mp: MyPlayer) -> dict[str, int]:
    attrs = mp.attributes or {}
    if not all(a in attrs for a in ATTRS):  # legacy 5-attribute rows
        return start_attributes(mp.position)
    return {a: int(attrs[a]) for a in ATTRS}


def migrate_legacy(mp: MyPlayer) -> bool:
    """Rows created with the old 5-attribute model: reset to the position's
    starting split and refund every spent point. Returns True if changed."""
    if all(a in (mp.attributes or {}) for a in ATTRS):
        return False
    mp.attributes = start_attributes(mp.position)
    mp.points_spent = 0
    return True


def raw_rating(attributes: dict) -> int:
    return round(sum(int(attributes[a]) for a in ATTRS) / len(ATTRS))


def rating_of(mp: MyPlayer, config) -> int:
    return max(1, min(config.my_player_rating_cap, raw_rating(attributes_of(mp))))


def tier_of(rating: int, config) -> str:
    thresholds = list(config.my_player_tier_thresholds or [65, 75, 85])
    tier = 0
    for i, threshold in enumerate(thresholds[:3]):
        if rating >= threshold:
            tier = i + 1
    return TIERS[tier]


# --- XP & levels ---------------------------------------------------------------

def xp_for_next(level: int, config) -> int:
    """XP to go from `level` to `level + 1`."""
    return max(1, config.my_player_xp_level_base + config.my_player_xp_level_step * (level - 1))


def level_info(xp: int, config) -> tuple[int, int, int]:
    """(level, xp into the current level, xp needed for the next)."""
    level, left = 1, max(0, xp)
    while left >= (need := xp_for_next(level, config)) and level < 500:
        left -= need
        level += 1
    return level, left, xp_for_next(level, config)


def add_xp(user: User, amount: int, config, today: Optional[date] = None, capped: bool = True) -> int:
    """Adds up to `amount` XP to a row-locked user within the daily cap
    (`capped=False`: the daily training bonus, which sits on top of it).
    Returns the XP actually granted. The caller commits."""
    if amount <= 0 or not config.my_player_enabled:
        return 0
    if not capped:
        user.my_player_xp = (user.my_player_xp or 0) + amount
        return amount
    today = today or local_today()
    if user.my_player_xp_day != today:
        user.my_player_xp_day = today
        user.my_player_xp_today = 0
    granted = max(0, min(amount, config.my_player_xp_daily_cap - (user.my_player_xp_today or 0)))
    if granted:
        user.my_player_xp = (user.my_player_xp or 0) + granted
        user.my_player_xp_today = (user.my_player_xp_today or 0) + granted
    return granted


async def grant_reward_xp(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> int:
    """Hook for wallet_service.credit_coins: a rewarded game action gives XP.
    Reads the already-loaded config row (identity map), never creates it."""
    if amount <= 0 or tx_type not in XP_TX_TYPES:
        return 0
    from app.models.game_config import GameConfig

    config = await db.get(GameConfig, 1)
    if config is None:
        return 0
    return add_xp(user, config.my_player_xp_per_reward, config)


def points_available(mp: Optional[MyPlayer], xp: int, config) -> int:
    level, _, _ = level_info(xp, config)
    return max(0, (level - 1) * config.my_player_points_per_level - (mp.points_spent if mp else 0))


# --- validation ------------------------------------------------------------------

def clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not NAME_RE.match(name):
        raise ConflictError("Имя: 2–20 букв, можно пробел, точку, дефис и апостроф")
    lowered = name.lower().replace("ё", "е")
    if any(root.replace("ё", "е") in lowered for root in _BANNED_ROOTS):
        raise ConflictError("Такое имя использовать нельзя")
    return name


def clean_number(number: int) -> int:
    if not 1 <= int(number) <= 99:
        raise ConflictError("Номер — от 1 до 99")
    return int(number)


def clean_appearance(appearance: dict) -> dict:
    clean = {}
    for key, count in APPEARANCE_OPTIONS.items():
        value = (appearance or {}).get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < count:
            raise ConflictError("Неизвестный вариант внешности")
        clean[key] = value
    return clean


# --- reads ---------------------------------------------------------------------

async def get_my_player(db: AsyncSession, user_id: int) -> Optional[MyPlayer]:
    return (await db.execute(select(MyPlayer).where(MyPlayer.user_id == user_id))).scalar_one_or_none()


def card_id_for(user_id: int) -> int:
    """Stand-in card id used by game modes (career lineups/conditions). Negative
    so it never clashes with a UserCard id or a career bot's (-1..-816)."""
    return -(1_000_000 + user_id)


def cosmetics_of(mp: MyPlayer) -> dict:
    raw = mp.cosmetics or {}
    owned = [c for c in raw.get("owned", []) if c in COSMETICS]
    out: dict = {"owned": owned}
    for kind in COSMETIC_KINDS:
        code = raw.get(kind)
        out[kind] = code if code in owned and COSMETICS[code][0] == kind else None
    return out


# --- skill ---------------------------------------------------------------------


async def skill_options(db: AsyncSession, position: Position) -> list[dict]:
    """Catalog skills that act in the tournament engine (career), are open
    and fit the position — same rules as for cards."""
    rows = {r.code: r for r in (await db.execute(select(CardSkill))).scalars().all()}
    options = []
    for code in SKILL_ORDER:
        definition = SKILL_DEFINITIONS[code]
        row = rows.get(code)
        if not definition.engine_supported or "tournament" not in definition.engines:
            continue
        if row is not None and not row.is_enabled:
            continue
        if position not in allowed_positions(definition, row):
            continue
        options.append({
            "code": code, "name": definition.name, "icon": definition.icon,
            "effect": definition.effect, "bonus_phrase": definition.bonus_phrase,
        })
    return options


def player_out(mp: MyPlayer, config) -> dict:
    rating = rating_of(mp, config)
    attributes = attributes_of(mp)
    tier = tier_of(rating, config)
    return {
        "name": mp.name, "number": mp.number, "position": mp.position.value, "category": category_of(mp.position),
        "appearance": {**{k: 0 for k in APPEARANCE_OPTIONS}, **(mp.appearance or {})},
        "attributes": attributes,
        "rating": rating, "attack_rating": attributes["atk"], "defense_rating": attributes["def"],
        "key_attr": key_attr(mp.position),
        "accessory": cosmetics_of(mp)["accessory"],
        "background": cosmetics_of(mp)["background"],
        "tier": tier, "tier_label": TIER_LABELS[tier],
    }


async def engine_card(db: AsyncSession, user_id: int, config=None) -> Optional[SimpleNamespace]:
    """The player's own footballer shaped like a UserCard (id, player_id,
    player.{display_name, position, rating, rarity, ...}, no skill, never
    locked) — for auto_squad_service.pick_cards and the tournament engine."""
    config = config or await get_config(db)
    if not config.my_player_enabled:
        return None
    mp = await get_my_player(db, user_id)
    if mp is None:
        return None
    out = player_out(mp, config)
    card_id = card_id_for(user_id)
    skill_level = mp.skill_level or 1
    has_skill = bool(mp.skill_code and effect_for_card(mp.skill_code, skill_level, mp.position, config))
    return SimpleNamespace(
        id=card_id, player_id=card_id, diamond_rating_bonus=0,
        skill_code=mp.skill_code if has_skill else None, skill_level=skill_level if has_skill else None,
        is_locked_by_admin=False, is_locked_in_trade=False, is_my_player=True,
        player=SimpleNamespace(
            display_name=mp.name, position=mp.position, rating=out["rating"], rarity=TIER_RARITY[out["tier"]],
            club="Мой игрок", country="", attack_rating=out["attack_rating"], defense_rating=out["defense_rating"],
        ),
    )


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    mp = await get_my_player(db, user.id)
    if mp is not None and migrate_legacy(mp):
        await db.commit()
    xp = user.my_player_xp or 0
    level, into, need = level_info(xp, config)
    today_xp = user.my_player_xp_today if user.my_player_xp_day == local_today() else 0
    rating = rating_of(mp, config) if mp else None
    return {
        "enabled": config.my_player_enabled,
        "balance": user.balance,
        "player": player_out(mp, config) if mp else None,
        "xp": xp, "level": level, "xp_into_level": into, "xp_for_next": need,
        "xp_today": today_xp or 0, "xp_daily_cap": config.my_player_xp_daily_cap,
        "xp_per_reward": config.my_player_xp_per_reward,
        "xp_career_match": config.my_player_xp_career_match,
        "xp_stratego_match": config.stratego_my_player_xp,
        "points_available": points_available(mp, xp, config),
        "points_per_level": config.my_player_points_per_level,
        "rating_cap": config.my_player_rating_cap,
        "at_rating_cap": bool(mp and raw_rating(attributes_of(mp)) >= config.my_player_rating_cap),
        "tier_thresholds": list(config.my_player_tier_thresholds or [65, 75, 85]),
        "appearance_options": APPEARANCE_OPTIONS,
        "attr_labels": ATTR_LABELS,
        "next_tier_at": next((t for t in (config.my_player_tier_thresholds or []) if rating is not None and t > rating), None),
        "skill": await _skill_view(db, mp, level, config) if mp else None,
        "training": _training_view(mp, config),
        "cosmetics": _cosmetics_view(mp, config),
    }


async def _skill_view(db: AsyncSession, mp: MyPlayer, level: int, config) -> dict:
    """Skill state + the next actions, priced like card skills
    (card_skill_service.costs: assign / upgrade_to_2 / upgrade_to_3 / replace)."""
    from app.services.card_skill_service import costs, get_token_balances

    definition = SKILL_DEFINITIONS.get(mp.skill_code or "")
    current = (mp.skill_level or 1) if definition else 0
    prices = costs(config)
    upgrade = None
    if definition and current < MAX_SKILL_LEVEL:
        cost = prices.upgrade_to_2 if current + 1 == 2 else prices.upgrade_to_3
        upgrade = {"to_level": current + 1, "token_cost": cost.token_cost, "coin_cost": cost.coin_cost}
    tokens = await get_token_balances(db, mp.user_id)
    return {
        "enabled": config.card_skills_enabled,
        "code": mp.skill_code if definition else None,
        "name": definition.name if definition else None,
        "icon": definition.icon if definition else None,
        "level": current,
        "level_label": LEVEL_ROMAN.get(current),
        "upgrade": upgrade,
        "assign_token_cost": prices.assign.token_cost, "assign_coin_cost": prices.assign.coin_cost,
        "replace_token_cost": prices.replace.token_cost, "replace_coin_cost": prices.replace.coin_cost,
        "tokens": {code: tokens.get(code, 0) for code in SKILL_ORDER},
        "options": await skill_options(db, mp.position),
    }


def _extra_bought_today(mp: MyPlayer, today: date) -> int:
    return mp.extra_trainings_bought if mp.extra_training_day == today else 0


def _training_view(mp: Optional[MyPlayer], config) -> dict:
    today = local_today()
    free_done = bool(mp and mp.training_day == today)
    credits = mp.extra_training_credits if mp else 0
    bought = _extra_bought_today(mp, today) if mp else 0
    return {
        "done_today": free_done,
        "can_train": bool(mp) and (not free_done or credits > 0),
        "extra_credits": credits,
        "extra_bought_today": bought,
        "extra_max": config.my_player_extra_trainings_max,
        "extra_left_today": max(0, config.my_player_extra_trainings_max - bought),
        "extra_coins_price": config.my_player_extra_training_coins,
        "extra_stars_price": config.my_player_extra_training_stars,
        "xp_base": config.my_player_training_xp_base,
        "xp_per_hit": config.my_player_training_xp_per_hit,
        "max_hits": TRAINING_MAX_HITS,
    }


def _cosmetics_view(mp: Optional[MyPlayer], config) -> dict:
    state = cosmetics_of(mp) if mp else {"owned": [], "accessory": None, "background": None}
    prices = config.my_player_cosmetic_prices or {}
    return {
        **state,
        "catalog": [
            {"code": code, "kind": kind, "name": name, "price": int(prices.get(code) or 0), "owned": code in state["owned"]}
            for code, (kind, name) in COSMETICS.items()
            if code in state["owned"] or int(prices.get(code) or 0) > 0
        ],
    }


async def public_view(db: AsyncSession, user_id: int) -> dict:
    config = await get_config(db)
    mp = await get_my_player(db, user_id) if config.my_player_enabled else None
    if mp is None:
        return {"player": None, "level": None}
    owner = await db.get(User, user_id)
    level, _, _ = level_info(owner.my_player_xp if owner else 0, config)
    return {"player": player_out(mp, config), "level": level}


# --- writes --------------------------------------------------------------------

def _require_enabled(config) -> None:
    if not config.my_player_enabled:
        raise ConflictError("«Мой игрок» сейчас недоступен")


async def create(db: AsyncSession, user: User, name: str, number: int, position: str, appearance: dict) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    try:
        pos = Position(position)
    except ValueError:
        raise ConflictError("Неизвестная позиция")
    if await get_my_player(db, user.id):
        raise ConflictError("Игрок уже создан")
    db.add(MyPlayer(
        user_id=user.id, name=clean_name(name), number=clean_number(number), position=pos,
        appearance=clean_appearance(appearance), attributes=start_attributes(pos), points_spent=0,
    ))
    await db.commit()
    return await get_view(db, user)


async def update(
    db: AsyncSession, user: User, name: Optional[str], number: Optional[int],
    position: Optional[str], appearance: Optional[dict],
) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    mp = await get_my_player(db, user.id)
    if mp is None:
        raise NotFoundError("Игрок ещё не создан")
    if name is not None:
        mp.name = clean_name(name)
    if number is not None:
        mp.number = clean_number(number)
    if appearance is not None:
        mp.appearance = clean_appearance(appearance)
    if position is not None:
        try:
            pos = Position(position)
        except ValueError:
            raise ConflictError("Неизвестная позиция")
        if category_of(pos) != category_of(mp.position):
            raise ConflictError("Позицию можно менять только в пределах своей линии")
        mp.position = pos
    await db.commit()
    return await get_view(db, user)


async def train(db: AsyncSession, user: User, attr: str, points: int) -> dict:
    """Spends `points` attribute points on `attr`. Locks the user row so two
    concurrent requests can't spend the same points twice."""
    config = await get_config(db)
    _require_enabled(config)
    if attr not in ATTRS:
        raise ConflictError("Неизвестная характеристика")
    if points < 1:
        raise ConflictError("Нужно хотя бы одно очко")
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = (await db.execute(select(MyPlayer).where(MyPlayer.user_id == user.id).with_for_update())).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Игрок ещё не создан")
    migrate_legacy(mp)
    if points > points_available(mp, locked.my_player_xp or 0, config):
        raise ConflictError("Не хватает очков — играй и получай опыт")
    attributes = attributes_of(mp)
    if attributes[attr] + points > ATTR_MAX:
        raise ConflictError(f"{ATTR_LABELS[attr]} не может быть выше {ATTR_MAX}")
    if raw_rating(attributes) >= config.my_player_rating_cap:
        raise ConflictError(f"Достигнут потолок рейтинга {config.my_player_rating_cap}")
    attributes[attr] += points
    mp.attributes = attributes
    mp.points_spent += points
    await db.commit()
    return await get_view(db, locked)


async def _locked_player(db: AsyncSession, user_id: int) -> MyPlayer:
    mp = (await db.execute(select(MyPlayer).where(MyPlayer.user_id == user_id).with_for_update())).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Игрок ещё не создан")
    return mp


# --- skill / training / cosmetics / leaderboard (stage 2) -------------------------

async def _spend_skill_price(
    db: AsyncSession, locked: User, mp: MyPlayer, code: str, token_cost: int, coin_cost: int, what: str,
) -> None:
    """Takes `token_cost` tokens of `code` and `coin_cost` coins, exactly as a
    card-skill operation would. Caller holds the user row lock and commits."""
    from app.services import wallet_service
    from app.services.card_skill_service import _lock_token_row

    name = SKILL_DEFINITIONS[code].name
    if token_cost > 0:
        row = await _lock_token_row(db, locked.id, code, create=False)
        owned = row.quantity if row else 0
        if owned < token_cost:
            raise ConflictError(f"Нужно жетонов «{name}»: {token_cost}, у тебя: {owned}")
        row.quantity -= token_cost
    if coin_cost > 0:
        await wallet_service.debit_coins(
            db, locked, coin_cost, TransactionType.card_skill_purchase, f"Мой игрок: {what} «{name}»",
            related_object_type="my_player", related_object_id=mp.id,
        )


async def set_skill(db: AsyncSession, user: User, code: str) -> dict:
    """Assigns a skill at level I (card «assign» price) or replaces the
    current one (card «replace» price, the new skill starts at level I) —
    the same operations, rules and prices as for a card."""
    config = await get_config(db)
    _require_enabled(config)
    from app.services import wallet_service
    from app.services.card_skill_service import acquisition_block_reason, costs

    if code not in SKILL_DEFINITIONS:
        raise ConflictError("Неизвестный навык")
    row = (await db.execute(select(CardSkill).where(CardSkill.code == code))).scalar_one_or_none()
    reason = acquisition_block_reason(SKILL_DEFINITIONS[code], row, config)
    if reason:
        raise ConflictError(reason)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    if code not in {o["code"] for o in await skill_options(db, mp.position)}:
        raise ConflictError("Этот навык не подходит для позиции игрока")
    if mp.skill_code == code:
        raise ConflictError("Этот навык уже выбран")
    prices = costs(config)
    cost = prices.replace if mp.skill_code else prices.assign
    await _spend_skill_price(
        db, locked, mp, code, cost.token_cost, cost.coin_cost, "замена навыка на" if mp.skill_code else "навык",
    )
    mp.skill_code = code
    mp.skill_level = 1
    await db.commit()
    return await get_view(db, locked)


async def upgrade_skill(db: AsyncSession, user: User) -> dict:
    """Raises the skill one level at the card-skill upgrade price."""
    config = await get_config(db)
    _require_enabled(config)
    from app.services import wallet_service
    from app.services.card_skill_service import acquisition_block_reason, costs

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    if not mp.skill_code or mp.skill_code not in SKILL_DEFINITIONS:
        raise ConflictError("Сначала выбери навык")
    row = (await db.execute(select(CardSkill).where(CardSkill.code == mp.skill_code))).scalar_one_or_none()
    reason = acquisition_block_reason(SKILL_DEFINITIONS[mp.skill_code], row, config)
    if reason:
        raise ConflictError(reason)
    current = mp.skill_level or 1
    if current >= MAX_SKILL_LEVEL:
        raise ConflictError("Навык уже максимального уровня")
    target = current + 1
    prices = costs(config)
    cost = prices.upgrade_to_2 if target == 2 else prices.upgrade_to_3
    await _spend_skill_price(
        db, locked, mp, mp.skill_code, cost.token_cost, cost.coin_cost, f"навык → {LEVEL_ROMAN[target]}",
    )
    mp.skill_level = target
    await db.commit()
    return await get_view(db, locked)


async def training_start(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    now = now or datetime.now(timezone.utc)
    mp = await _locked_player(db, user.id)
    if mp.training_day == local_today(now) and mp.extra_training_credits <= 0:
        raise ConflictError("Тренировка на сегодня уже пройдена — купи дополнительную или приходи завтра")
    mp.training_started_at = now
    await db.commit()
    return {"max_hits": TRAINING_MAX_HITS, "min_seconds": TRAINING_MIN_SECONDS}


async def training_finish(db: AsyncSession, user: User, hits: int, now: Optional[datetime] = None) -> dict:
    """Credits the training XP (base + per hit): the free run once per local
    day, then one bought extra-training credit per run. The run must have
    been started on the server, take a plausible time and not be stale."""
    config = await get_config(db)
    _require_enabled(config)
    from app.services import wallet_service

    now = now or datetime.now(timezone.utc)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    free_available = mp.training_day != local_today(now)
    if not free_available and mp.extra_training_credits <= 0:
        raise ConflictError("Тренировка на сегодня уже пройдена — купи дополнительную или приходи завтра")
    started = ensure_aware(mp.training_started_at) if mp.training_started_at else None
    if started is None or now - started > TRAINING_TTL:
        raise ConflictError("Тренировка не начата или устарела — начни заново")
    if (now - started).total_seconds() < TRAINING_MIN_SECONDS:
        raise ConflictError("Слишком быстро — пройди тренировку целиком")
    hits = max(0, min(TRAINING_MAX_HITS, int(hits)))
    xp = add_xp(
        locked, config.my_player_training_xp_base + config.my_player_training_xp_per_hit * hits, config, capped=False,
    )
    if free_available:
        mp.training_day = local_today(now)
    else:
        mp.extra_training_credits -= 1
    mp.training_started_at = None
    await db.commit()
    view = await get_view(db, locked)
    view["training_xp"] = xp
    return view


async def buy_cosmetic(db: AsyncSession, user: User, code: str) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    price = int((config.my_player_cosmetic_prices or {}).get(code) or 0)
    if code not in COSMETICS or price <= 0:
        raise ConflictError("Этого предмета нет в продаже")
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    state = cosmetics_of(mp)
    if code in state["owned"]:
        raise ConflictError("Уже куплено")
    await wallet_service.debit_coins(
        db, locked, price, TransactionType.my_player_cosmetic, f"Мой игрок: {COSMETICS[code][1]}",
        related_object_type="my_player", related_object_id=mp.id,
    )
    kind = COSMETICS[code][0]
    mp.cosmetics = {**state, "owned": [*state["owned"], code], kind: code}
    await db.commit()
    return await get_view(db, locked)


async def equip_cosmetic(db: AsyncSession, user: User, kind: str, code: Optional[str]) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    if kind not in COSMETIC_KINDS:
        raise ConflictError("Неизвестный слот")
    mp = await _locked_player(db, user.id)
    state = cosmetics_of(mp)
    if code is not None and (code not in state["owned"] or COSMETICS[code][0] != kind):
        raise ConflictError("Сначала купи этот предмет")
    mp.cosmetics = {**state, kind: code}
    await db.commit()
    return await get_view(db, user)


async def leaderboard(db: AsyncSession, user: User, scope: str = "all", limit: int = 50) -> dict:
    """Top players by rating. Rating = start + points spent / 2 (capped), so
    ordering by points_spent (then XP) needs no per-row JSON maths in SQL."""
    config = await get_config(db)
    scope_ids: Optional[list[int]] = None
    if scope == "friends":
        from app.services.friend_service import friend_ids

        scope_ids = [user.id, *await friend_ids(db, user.id)]
    query = select(MyPlayer, User).join(User, User.id == MyPlayer.user_id)
    if scope_ids is not None:
        query = query.where(MyPlayer.user_id.in_(scope_ids))
    rows = (await db.execute(
        query.order_by(MyPlayer.points_spent.desc(), User.my_player_xp.desc(), MyPlayer.id).limit(limit)
    )).all()

    def entry(rank: int, mp: MyPlayer, owner: User) -> dict:
        return {
            "rank": rank, "user_id": owner.id, "is_me": owner.id == user.id,
            "user_name": owner.first_name or owner.username or "Игрок",
            "level": level_info(owner.my_player_xp or 0, config)[0],
            "player": player_out(mp, config),
        }

    entries = [entry(i + 1, mp, owner) for i, (mp, owner) in enumerate(rows)]
    me = None
    if not any(e["is_me"] for e in entries):
        mine = await get_my_player(db, user.id)
        if mine is not None:
            ahead = select(func.count(MyPlayer.id)).join(User, User.id == MyPlayer.user_id).where(or_(
                MyPlayer.points_spent > mine.points_spent,
                and_(MyPlayer.points_spent == mine.points_spent, User.my_player_xp > (user.my_player_xp or 0)),
            ))
            if scope_ids is not None:
                ahead = ahead.where(MyPlayer.user_id.in_(scope_ids))
            me = entry((await db.execute(ahead)).scalar_one() + 1, mine, user)
    return {"scope": scope, "entries": entries, "me": me}


# --- extra trainings & Stars purchases ---------------------------------------------

def _count_extra_purchase(mp: MyPlayer, config, today: date, strict: bool = True) -> None:
    """Books one extra-training purchase for today (daily max) and adds a
    credit. strict=False (a Stars payment already taken) never refuses."""
    bought = _extra_bought_today(mp, today)
    if strict and bought >= config.my_player_extra_trainings_max:
        raise ConflictError("Лимит дополнительных тренировок на сегодня исчерпан")
    mp.extra_training_day = today
    mp.extra_trainings_bought = bought + 1
    mp.extra_training_credits += 1


async def buy_extra_training(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    price = config.my_player_extra_training_coins
    if price <= 0:
        raise ConflictError("За монеты дополнительные тренировки не продаются")
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    _count_extra_purchase(mp, config, local_today())
    await wallet_service.debit_coins(
        db, locked, price, TransactionType.my_player_extra_training, "Мой игрок: дополнительная тренировка",
        related_object_type="my_player", related_object_id=mp.id,
    )
    await db.commit()
    return await get_view(db, locked)


async def create_stars_invoice(db: AsyncSession, user: User, purchase: str, item_id: Optional[int] = None) -> dict:
    """Telegram Stars invoice for one extra training ("training") or an
    «Имущество» item ("item"). The price is frozen on the invoice."""
    import secrets

    from app.models.lifestyle import LifestyleItem
    from app.models.pack import StarsInvoice
    from app.services import lifestyle_service
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    _require_enabled(config)
    if purchase == "training":
        mp = await get_my_player(db, user.id)
        if mp is None:
            raise NotFoundError("Игрок ещё не создан")
        stars = config.my_player_extra_training_stars
        if stars <= 0:
            raise ConflictError("За звёзды дополнительные тренировки не продаются")
        if _extra_bought_today(mp, local_today()) >= config.my_player_extra_trainings_max:
            raise ConflictError("Лимит дополнительных тренировок на сегодня исчерпан")
        key, title, description = "training", "Дополнительная тренировка", "Ещё одна тренировка «Точный удар» для твоего игрока"
    elif purchase == "item" and item_id is not None:
        item = await db.get(LifestyleItem, item_id)
        if item is None:
            raise NotFoundError("Предмет не найден")
        if item.stars_price <= 0:
            raise ConflictError("Этот предмет продаётся только за монеты")
        await lifestyle_service.check_buyable(db, user.id, item)
        stars = item.stars_price
        key, title, description = f"item:{item.id}", item.name, item.description or f"Имущество: {item.name}"
    else:
        raise ConflictError("Неизвестная покупка")

    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, my_player_purchase=key))
    await db.flush()
    link = await _request_telegram_invoice_link(token, title, description, stars)
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def validate_stars_purchase(db: AsyncSession, invoice) -> tuple[bool, str]:
    """pre_checkout_query check: still buyable at the frozen price."""
    from app.models.lifestyle import LifestyleItem
    from app.services import lifestyle_service

    config = await get_config(db)
    if not config.my_player_enabled:
        return False, "«Мой игрок» сейчас недоступен"
    if invoice.my_player_purchase == "training":
        mp = await get_my_player(db, invoice.user_id)
        if mp is None or _extra_bought_today(mp, local_today()) >= config.my_player_extra_trainings_max:
            return False, "Лимит дополнительных тренировок на сегодня исчерпан"
        return True, ""
    if invoice.my_player_purchase.startswith("item:"):
        item = await db.get(LifestyleItem, int(invoice.my_player_purchase.split(":", 1)[1]))
        if item is None or item.stars_price != invoice.stars_amount:
            return False, "Этот предмет больше не продаётся"
        try:
            await lifestyle_service.check_buyable(db, invoice.user_id, item)
        except ConflictError as exc:
            return False, exc.message
        return True, ""
    return False, "Unknown order"


async def deliver_stars_purchase(db: AsyncSession, user: User, invoice) -> dict:
    """Called by stars_payment_service.deliver_payment under the invoice row
    lock (idempotent there). The payment is already taken, so this never
    refuses on soft limits — pre-checkout already enforced them. The caller
    commits."""
    from app.models.lifestyle import LifestyleItem, UserLifestyleItem
    from app.services import lifestyle_service

    config = await get_config(db)
    if invoice.my_player_purchase == "training":
        mp = await _locked_player(db, user.id)
        _count_extra_purchase(mp, config, local_today(), strict=False)
        return {"kind": "training", "name": "Дополнительная тренировка"}
    item_id = int(invoice.my_player_purchase.split(":", 1)[1])
    item = (await db.execute(
        select(LifestyleItem).where(LifestyleItem.id == item_id).with_for_update()
    )).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Предмет не найден")
    already = (await db.execute(select(UserLifestyleItem.id).where(
        UserLifestyleItem.user_id == user.id, UserLifestyleItem.item_id == item.id,
    ))).first()
    if not already:
        await lifestyle_service.grant(db, user.id, item, "stars")
    return {"kind": "item", "name": item.name}
