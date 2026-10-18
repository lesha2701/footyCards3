"""«Мой игрок»: the user's own footballer.

- Built once in a constructor (name, number, position, appearance); name,
  number and appearance can be changed any time, the position only within
  its line (e.g. ST -> LW). Changing the line itself is a paid «смена
  амплуа» (coins or Stars, `change_role`).
- Two attributes, the same the whole game uses for cards: attack and
  defense (Player.attack_rating / defense_rating). The overall rating is
  their average, as for every other card (player_stats_service).
- XP accrues on the user row (User.my_player_xp) from every rewarded game
  action — see `grant_reward_xp`, called by wallet_service.credit_coins under
  the user's row lock — with a daily cap. Levels turn XP into attribute
  points the player spends on attack/defense. «Имущество» items may add an
  XP bonus (lifestyle_service.effects_of); `add_xp` takes it as bonus_pct.
- The rating is capped by config.my_player_rating_cap; the frame tier
  (bronze -> legend) follows the rating.
- Game modes field it through `engine_card`, a duck-typed stand-in for a
  UserCard (same shape the tournament engine reads): «Карьера тренера»,
  «Футбольное Стратего» and «Карьера игрока». Low freshness (drained by
  «Карьера игрока» matches, restored by time and trainings) lowers its
  rating there.
- A card skill (any catalog skill that fits the position and acts in the
  tournament engine), bought and leveled exactly like a card skill (tokens +
  coins at GameConfig.card_skill_* prices).
- A daily training mini-game whose drill changes with the weekday and the
  line (XP on top of the daily cap); every my_player_streak_days days in a
  row pay skill tokens. Extra trainings (up to config max a day) for coins
  or Telegram Stars.
- Cosmetics (accessory, card background, card effect) for coins and/or
  Stars; «Имущество» items for coins (lifestyle_service) or Stars.
- Friend duels: the player's footballer against a friend's, played
  instantly (`play_duel`), a daily limit, coins + XP for the challenger.
- Stars go through stars_payment_service (`create_stars_invoice` /
  `validate_stars_purchase` / `deliver_stars_purchase`).

Every number lives in GameConfig.my_player_*.
"""
import random
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card_skill import CardSkill
from app.models.enums import NotificationType, Position, Rarity, TransactionType
from app.models.my_player import MyPlayer, MyPlayerDuel
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
# GameConfig.my_player_cosmetic_prices (coins) and
# my_player_cosmetic_stars_prices (Stars). The frontend draws the same codes
# (components/myPlayer/PlayerAvatar.tsx, CardEffect.tsx).
COSMETICS = {
    "headband": ("accessory", "Повязка на голову"),
    "earring": ("accessory", "Серьга"),
    "chain": ("accessory", "Цепочка"),
    "goggles": ("accessory", "Спортивные очки"),
    "captain": ("accessory", "Капитанская повязка"),
    "headphones": ("accessory", "Наушники"),
    "crown": ("accessory", "Корона"),
    "bg_sunset": ("background", "Фон «Закат»"),
    "bg_neon": ("background", "Фон «Неон»"),
    "bg_gold": ("background", "Фон «Золотой стадион»"),
    "bg_night": ("background", "Фон «Ночной матч»"),
    "bg_galaxy": ("background", "Фон «Галактика»"),
    "bg_champions": ("background", "Фон «Лига чемпионов»"),
    "fx_sparkle": ("effect", "Эффект «Искры»"),
    "fx_fire": ("effect", "Эффект «Пламя»"),
    "fx_lightning": ("effect", "Эффект «Молния»"),
    "aviators": ("accessory", "Очки-авиаторы звезды"),
    "diamond_chain": ("accessory", "Бриллиантовая цепь"),
    "hair_neymar": ("hair", "Прическа Неймара"),
    "hair_cr7": ("hair", "Укладка Роналду"),
    "hair_pogba": ("hair", "Цветной фейд Погба"),
    "bg_goal": ("background", "Фон «Ворота»"),
    "bg_national": ("background", "Фон «Флаг сборной»"),
    # Granted with «Карьера Pro», never sold.
    "bg_pro": ("background", "Фон «Pro»"),
    # Shown in key moments and the headlines after a goal.
    "cel_siu": ("celebration", "Празднование «Сиу!»"),
    "cel_plane": ("celebration", "Празднование «Самолётик»"),
    "cel_heart": ("celebration", "Празднование «Сердечко»"),
    "cel_dance": ("celebration", "Празднование «Танец у флажка»"),
}
COSMETIC_KINDS = ("accessory", "background", "effect", "hair", "celebration")
# Premium hairstyles: wearing one sets appearance["hair"] to this index
# (PlayerAvatar draws 14+ as these styles); the free choices stay 0..13.
PREMIUM_HAIR = {"hair_neymar": 14, "hair_cr7": 15, "hair_pogba": 16}
# «Статус» from owned style items — added to the «Имущество» status
# (lifestyle_service.cosmetic_prestige).
COSMETIC_STATUS = {
    "hair_neymar": 30, "hair_cr7": 25, "hair_pogba": 20, "aviators": 15, "diamond_chain": 20,
    "crown": 25, "bg_galaxy": 10, "bg_champions": 15, "fx_sparkle": 8, "fx_fire": 10, "fx_lightning": 15,
}

TRAINING_MAX_HITS = 3
# A run must take at least this long (three timed attempts) and be finished
# within the TTL — the client reports hits, so the reward is kept small
# and once a day.
TRAINING_MIN_SECONDS = 4
TRAINING_TTL = timedelta(minutes=5)

# Training drills: (name, how to play). The drill of the day follows the
# weekday (Mon..Sun) and the player's line; the frontend draws each one
# (components/myPlayer/TrainingGame.tsx). Same scoring for every drill.
DRILLS = {
    "shot": ("Точный удар", "Останови мяч в зелёной зоне — удар в девятку"),
    "pass": ("Пас в касание", "Отдай пас, когда мяч у открывшегося партнёра"),
    "tackle": ("Отбор мяча", "Подкат точно в момент, когда соперник рядом"),
    "save": ("Реакция вратаря", "Прыгни, когда мяч в створе"),
}
DRILL_WEEK = {
    "GK": ("save", "pass", "save", "tackle", "save", "pass", "save"),
    "DEF": ("tackle", "pass", "tackle", "shot", "tackle", "pass", "tackle"),
    "MID": ("pass", "shot", "tackle", "pass", "shot", "pass", "tackle"),
    "FWD": ("shot", "pass", "shot", "tackle", "shot", "pass", "shot"),
}

# Friend duel: attacks per side; chance an attack scores = base + (attack -
# defense) x slope, clamped.
DUEL_ATTACKS = 5
DUEL_BASE_CHANCE = 0.32
DUEL_SLOPE = 0.012
DUEL_CHANCE_RANGE = (0.08, 0.75)

TROPHY_CODES = (
    "player_career_champion", "player_career_top_scorer", "player_career_mvp",
    "player_career_cl_winner", "player_career_national_winner", "player_career_golden_ball",
)

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


def add_xp(
    user: User, amount: int, config, today: Optional[date] = None, capped: bool = True, bonus_pct: int = 0,
) -> int:
    """Adds up to `amount` XP (+bonus_pct% from «Имущество») to a row-locked
    user within the daily cap (`capped=False`: the training bonus, which
    sits on top of it). Returns the XP actually granted. The caller commits."""
    if amount <= 0 or not config.my_player_enabled:
        return 0
    if bonus_pct > 0:
        amount += amount * bonus_pct // 100
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


async def xp_bonus_pct(db: AsyncSession, user_id: int) -> int:
    """XP bonus from the player's «Имущество» and worn «Артефакты»."""
    from app.services import artifact_service
    from app.services.lifestyle_service import effects_of

    return (await effects_of(db, user_id)).get("xp_bonus_pct", 0) + (
        await artifact_service.effects_of(db, user_id)
    ).get("xp_bonus_pct", 0)


async def grant_reward_xp(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> int:
    """Hook for wallet_service.credit_coins: a rewarded game action gives XP.
    Reads the already-loaded config row (identity map), never creates it."""
    if amount <= 0 or tx_type not in XP_TX_TYPES:
        return 0
    from app.models.game_config import GameConfig

    config = await db.get(GameConfig, 1)
    if config is None or not config.my_player_enabled:
        return 0
    return add_xp(user, config.my_player_xp_per_reward, config, bonus_pct=await xp_bonus_pct(db, user.id))


def points_available(mp: Optional[MyPlayer], xp: int, config) -> int:
    level, _, _ = level_info(xp, config)
    return max(0, (level - 1) * config.my_player_points_per_level - (mp.points_spent if mp else 0))


# --- freshness -------------------------------------------------------------------

def freshness_now(mp: MyPlayer, config, now: Optional[datetime] = None, regen_bonus: int = 0) -> int:
    """Current freshness: the stored value plus regeneration since it was set."""
    base = 100 if mp.freshness is None else mp.freshness
    if mp.freshness_at is None or base >= 100:
        return min(100, base)
    now = now or datetime.now(timezone.utc)
    hours = max(0.0, (now - ensure_aware(mp.freshness_at)).total_seconds() / 3600)
    return int(min(100, base + hours * max(0, config.my_player_freshness_regen_per_hour + regen_bonus)))


def set_freshness(mp: MyPlayer, value: int, now: Optional[datetime] = None) -> None:
    mp.freshness = max(0, min(100, int(value)))
    mp.freshness_at = now or datetime.now(timezone.utc)


def fatigue_penalty(freshness: int, config) -> int:
    """Rating points lost in matches: 0 when fresh, max_penalty at 0."""
    return round(max(0, config.my_player_fatigue_max_penalty) * (100 - max(0, min(100, freshness))) / 100)


async def regen_bonus(db: AsyncSession, user_id: int) -> int:
    from app.services import artifact_service
    from app.services.lifestyle_service import effects_of

    return (await effects_of(db, user_id)).get("freshness_regen", 0) + (
        await artifact_service.effects_of(db, user_id)
    ).get("freshness_regen", 0)


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


def _position(value: str) -> Position:
    try:
        return Position(value)
    except ValueError:
        raise ConflictError("Неизвестная позиция")


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
    # The free hairstyle to go back to when a premium one is taken off.
    out["base_hair"] = int(raw.get("base_hair") or 0)
    return out


def _apply_hair(mp: MyPlayer, code: Optional[str], state: dict) -> None:
    """Puts a premium hairstyle on (or back to the free one)."""
    appearance = dict(mp.appearance or {})
    current = int(appearance.get("hair") or 0)
    if current < APPEARANCE_OPTIONS["hair"]:
        state["base_hair"] = current
    appearance["hair"] = PREMIUM_HAIR[code] if code else state.get("base_hair", 0)
    mp.appearance = appearance


def cosmetic_status(mp: Optional[MyPlayer]) -> int:
    if mp is None:
        return 0
    return sum(COSMETIC_STATUS.get(c, 0) for c in cosmetics_of(mp)["owned"])


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
    cosmetics = cosmetics_of(mp)
    return {
        "name": mp.name, "number": mp.number, "position": mp.position.value, "category": category_of(mp.position),
        "appearance": {**{k: 0 for k in APPEARANCE_OPTIONS}, **(mp.appearance or {})},
        "attributes": attributes,
        "rating": rating, "attack_rating": attributes["atk"], "defense_rating": attributes["def"],
        "key_attr": key_attr(mp.position),
        "accessory": cosmetics["accessory"],
        "background": cosmetics["background"],
        "effect": cosmetics["effect"],
        "celebration": cosmetics["celebration"],
        "tier": tier, "tier_label": TIER_LABELS[tier],
        "country": mp.country,
        "pro": bool(mp.pro_until and ensure_aware(mp.pro_until) > datetime.now(timezone.utc)),
    }


async def match_stats(db: AsyncSession, mp: MyPlayer, config, now: Optional[datetime] = None) -> dict:
    """Rating / attack / defense as fielded in matches: minus the fatigue
    penalty, plus the attack/defense of worn «Артефакты»."""
    from app.services import artifact_service

    out = player_out(mp, config)
    penalty = fatigue_penalty(freshness_now(mp, config, now, await regen_bonus(db, mp.user_id)), config)
    artifacts = await artifact_service.effects_of(db, mp.user_id, "my_player", config)
    atk_bonus, def_bonus = artifacts.get("attack", 0), artifacts.get("defense", 0)
    rating_bonus = round((atk_bonus + def_bonus) / 2) + artifacts.get("match_rating", 0)
    return {
        "rating": max(1, min(99, out["rating"] - penalty + rating_bonus)),
        "attack": max(1, min(99, out["attack_rating"] - penalty + atk_bonus)),
        "defense": max(1, min(99, out["defense_rating"] - penalty + def_bonus)),
        "penalty": penalty, "tier": out["tier"],
    }


async def engine_card(db: AsyncSession, user_id: int, config=None) -> Optional[SimpleNamespace]:
    """The player's own footballer shaped like a UserCard (id, player_id,
    player.{display_name, position, rating, rarity, ...}, never locked) —
    for auto_squad_service.pick_cards and the tournament engine. Fatigue
    lowers its numbers."""
    config = config or await get_config(db)
    if not config.my_player_enabled:
        return None
    mp = await get_my_player(db, user_id)
    if mp is None:
        return None
    from app.services import artifact_service

    stats = await match_stats(db, mp, config)
    artifacts = await artifact_service.effects_of(db, user_id, "my_player", config)
    card_id = card_id_for(user_id)
    # A «skill_level» artifact plays the skill higher (3 = the top level).
    skill_level = min(3, (mp.skill_level or 1) + artifacts.get("skill_level", 0)) if mp.skill_code else 1
    # Match-engine boosts from artifacts (tournament_match_engine /
    # club_tactical_matchup_service read them off the engine card).
    boosts = {k: artifacts[k] for k in ("shot_pp", "dribble_pp") if artifacts.get(k)}
    has_skill = bool(mp.skill_code and effect_for_card(mp.skill_code, skill_level, mp.position, config))
    return SimpleNamespace(
        id=card_id, player_id=card_id, diamond_rating_bonus=0,
        skill_code=mp.skill_code if has_skill else None, skill_level=skill_level if has_skill else None,
        is_locked_by_admin=False, is_locked_in_trade=False, is_my_player=True, boosts=boosts or None,
        player=SimpleNamespace(
            display_name=mp.name, position=mp.position, rating=stats["rating"], rarity=TIER_RARITY[stats["tier"]],
            club="Мой игрок", country="", attack_rating=stats["attack"], defense_rating=stats["defense"],
        ),
    )


async def trophies_of(db: AsyncSession, user_id: int) -> list[dict]:
    """«Карьера игрока» trophies, newest first (the showcase)."""
    from app.models.trophy import TrophyDefinition, UserTrophy

    rows = (await db.execute(
        select(UserTrophy).join(TrophyDefinition, TrophyDefinition.id == UserTrophy.trophy_definition_id)
        .where(UserTrophy.user_id == user_id, TrophyDefinition.code.in_(TROPHY_CODES))
        .order_by(UserTrophy.granted_at.desc(), UserTrophy.id.desc())
    )).unique().scalars().all()
    return [
        {
            "id": r.id, "code": r.trophy.code, "name": r.trophy.name, "icon": r.trophy.icon,
            "image_path": r.trophy.image_path, "message": r.message, "granted_at": ensure_aware(r.granted_at).isoformat(),
        }
        for r in rows
    ]


async def _career_offers_waiting(db: AsyncSession, user_id: int) -> bool:
    """The last «Карьера игрока» season is over and clubs made offers."""
    from app.models.player_career import PlayerCareerSeason

    last = (await db.execute(
        select(PlayerCareerSeason).where(PlayerCareerSeason.user_id == user_id)
        .order_by(PlayerCareerSeason.id.desc()).limit(1)
    )).scalar_one_or_none()
    return bool(last and last.status == "finished" and (last.state or {}).get("offers"))


async def get_view(db: AsyncSession, user: User) -> dict:
    from app.services.lifestyle_service import effects_of, income_ready

    config = await get_config(db)
    mp = await get_my_player(db, user.id)
    xp = user.my_player_xp or 0
    level, into, need = level_info(xp, config)
    if mp is not None:
        changed = migrate_legacy(mp)
        if not mp.level_seen:
            mp.level_seen = level  # start tracking without a retroactive level-up screen
            changed = True
        today = local_today()
        if mp.pro_until and ensure_aware(mp.pro_until) > datetime.now(timezone.utc) and mp.pro_bonus_day != today:
            # «Карьера Pro»: one more training every day.
            mp.extra_training_credits += 1
            mp.pro_bonus_day = today
            changed = True
        if changed:
            await db.commit()
    today_xp = user.my_player_xp_today if user.my_player_xp_day == local_today() else 0
    rating = rating_of(mp, config) if mp else None
    effects = await effects_of(db, user.id) if mp else {}
    points = points_available(mp, xp, config)
    training = _training_view(mp, config)
    level_seen = mp.level_seen if mp else level
    view = {
        "enabled": config.my_player_enabled,
        "balance": user.balance,
        "player": player_out(mp, config) if mp else None,
        "xp": xp, "level": level, "xp_into_level": into, "xp_for_next": need,
        "xp_today": today_xp or 0, "xp_daily_cap": config.my_player_xp_daily_cap,
        "xp_per_reward": config.my_player_xp_per_reward,
        "xp_career_match": config.my_player_xp_career_match,
        "xp_stratego_match": config.stratego_my_player_xp,
        "xp_player_career_match": config.player_career_match_xp,
        "xp_bonus_pct": effects.get("xp_bonus_pct", 0),
        "points_available": points,
        "points_per_level": config.my_player_points_per_level,
        "level_seen": level_seen,
        "level_up": {
            "from_level": level_seen, "to_level": level,
            "points": (level - level_seen) * config.my_player_points_per_level,
        } if mp and level > level_seen else None,
        "rating_cap": config.my_player_rating_cap,
        "at_rating_cap": bool(mp and raw_rating(attributes_of(mp)) >= config.my_player_rating_cap),
        "tier_thresholds": list(config.my_player_tier_thresholds or [65, 75, 85]),
        "appearance_options": APPEARANCE_OPTIONS,
        "attr_labels": ATTR_LABELS,
        "next_tier_at": next((t for t in (config.my_player_tier_thresholds or []) if rating is not None and t > rating), None),
        "skill": await _skill_view(db, mp, level, config) if mp else None,
        "training": training,
        "cosmetics": _cosmetics_view(mp, config),
        "freshness": _freshness_view(mp, config, effects.get("freshness_regen", 0)) if mp else None,
        "role_change": {
            "coins_price": config.my_player_role_change_coins, "stars_price": config.my_player_role_change_stars,
        },
        "trophies": await trophies_of(db, user.id) if mp else [],
        "countries": await _countries(db),
    }
    view["attention"] = {
        "create": mp is None,
        "level_up": view["level_up"] is not None,
        "points": bool(mp) and points > 0 and not view["at_rating_cap"],
        "training": bool(mp) and not training["done_today"],
        "income": bool(mp) and await income_ready(db, user.id) > 0,
        "career_offers": bool(mp) and await _career_offers_waiting(db, user.id),
    }
    return view


async def _countries(db: AsyncSession) -> list[str]:
    from app.services.player_career_cups import countries

    return await countries(db)


async def _clean_country(db: AsyncSession, country: Optional[str]) -> Optional[str]:
    if country is None or not country.strip():
        return None
    if country not in await _countries(db):
        raise ConflictError("Неизвестная страна")
    return country


def _freshness_view(mp: MyPlayer, config, bonus: int) -> dict:
    value = freshness_now(mp, config, regen_bonus=bonus)
    return {
        "value": value, "penalty": fatigue_penalty(value, config),
        "max_penalty": config.my_player_fatigue_max_penalty,
        "regen_per_hour": config.my_player_freshness_regen_per_hour + bonus, "regen_bonus": bonus,
        "per_match": config.my_player_freshness_per_match, "training": config.my_player_freshness_training,
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


def drill_for(position: Position, day: date) -> str:
    return DRILL_WEEK[category_of(position)][day.weekday()]


def current_streak(mp: MyPlayer, today: date) -> int:
    """Free trainings in a row, 0 once a day was missed."""
    if mp.training_day is None or mp.training_day < today - timedelta(days=1):
        return 0
    return mp.training_streak or 0


def _training_view(mp: Optional[MyPlayer], config) -> dict:
    today = local_today()
    free_done = bool(mp and mp.training_day == today)
    credits = mp.extra_training_credits if mp else 0
    bought = _extra_bought_today(mp, today) if mp else 0
    drill = drill_for(mp.position, today) if mp else "shot"
    streak = current_streak(mp, today) if mp else 0
    every = max(1, config.my_player_streak_days)
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
        "drill": {"code": drill, "name": DRILLS[drill][0], "hint": DRILLS[drill][1]},
        "streak": streak,
        "streak_days": every,
        "streak_tokens": config.my_player_streak_tokens,
        # Free trainings left until the next streak reward (counting today's if not done yet).
        "streak_left": every - streak % every,
        "freshness_bonus": config.my_player_freshness_training,
    }


def _cosmetics_view(mp: Optional[MyPlayer], config) -> dict:
    state = cosmetics_of(mp) if mp else {
        "owned": [], "accessory": None, "background": None, "effect": None, "hair": None, "base_hair": 0,
        "celebration": None,
    }
    coins = config.my_player_cosmetic_prices or {}
    stars = config.my_player_cosmetic_stars_prices or {}
    return {
        **state,
        "catalog": [
            {
                "code": code, "kind": kind, "name": name, "price": int(coins.get(code) or 0),
                "stars_price": int(stars.get(code) or 0), "owned": code in state["owned"],
                "status": COSMETIC_STATUS.get(code, 0), "hair_index": PREMIUM_HAIR.get(code),
            }
            for code, (kind, name) in COSMETICS.items()
            if code in state["owned"] or int(coins.get(code) or 0) > 0 or int(stars.get(code) or 0) > 0
        ],
    }


async def public_view(db: AsyncSession, user_id: int) -> dict:
    config = await get_config(db)
    mp = await get_my_player(db, user_id) if config.my_player_enabled else None
    if mp is None:
        return {"player": None, "level": None, "trophies": []}
    owner = await db.get(User, user_id)
    level, _, _ = level_info(owner.my_player_xp if owner else 0, config)
    return {"player": player_out(mp, config), "level": level, "trophies": await trophies_of(db, user_id)}


# --- writes --------------------------------------------------------------------

def _require_enabled(config) -> None:
    if not config.my_player_enabled:
        raise ConflictError("«Мой игрок» сейчас недоступен")


async def create(
    db: AsyncSession, user: User, name: str, number: int, position: str, appearance: dict, country: Optional[str] = None,
) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    pos = _position(position)
    if await get_my_player(db, user.id):
        raise ConflictError("Игрок уже создан")
    db.add(MyPlayer(
        user_id=user.id, name=clean_name(name), number=clean_number(number), position=pos,
        appearance=clean_appearance(appearance), attributes=start_attributes(pos), points_spent=0,
        level_seen=level_info(user.my_player_xp or 0, config)[0], country=await _clean_country(db, country),
    ))
    await db.commit()
    return await get_view(db, user)


async def update(
    db: AsyncSession, user: User, name: Optional[str], number: Optional[int],
    position: Optional[str], appearance: Optional[dict], country: Optional[str] = None, country_set: bool = False,
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
        state = cosmetics_of(mp)
        premium = PREMIUM_HAIR.get(state["hair"]) if state["hair"] else None
        incoming = dict(appearance)
        keep_premium = premium is not None and incoming.get("hair") == premium
        if keep_premium:
            incoming["hair"] = state["base_hair"]  # validate the rest, keep the premium style on
        mp.appearance = clean_appearance(incoming)
        if keep_premium:
            mp.appearance = {**mp.appearance, "hair": premium}
        else:
            # A free hairstyle picked in the constructor takes the premium one off.
            mp.cosmetics = {**state, "hair": None, "base_hair": mp.appearance["hair"]}
    if country_set:
        from app.services.player_career_cups import active_cup

        if country != mp.country and await active_cup(db, user.id, "national"):
            raise ConflictError("Сборную нельзя сменить во время турнира")
        mp.country = await _clean_country(db, country)
    if position is not None:
        pos = _position(position)
        if category_of(pos) != category_of(mp.position):
            raise ConflictError("Сменить линию можно только через «Смену амплуа»")
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


async def ack_level_up(db: AsyncSession, user: User) -> dict:
    """The level-up screen was shown: remember the level it was shown for."""
    config = await get_config(db)
    mp = await _locked_player(db, user.id)
    mp.level_seen = max(mp.level_seen or 0, level_info(user.my_player_xp or 0, config)[0])
    await db.commit()
    return await get_view(db, user)


async def _locked_player(db: AsyncSession, user_id: int) -> MyPlayer:
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == user_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Игрок ещё не создан")
    return mp


# --- skill / training / cosmetics / leaderboard ---------------------------------------

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
    drill = drill_for(mp.position, local_today(now))
    return {"max_hits": TRAINING_MAX_HITS, "min_seconds": TRAINING_MIN_SECONDS, "drill": drill}


async def _streak_skill(db: AsyncSession, mp: MyPlayer, day: date) -> Optional[str]:
    """Skill whose tokens a streak pays: the player's own skill, else one
    that fits the position (stable for the day)."""
    if mp.skill_code in SKILL_DEFINITIONS and SKILL_DEFINITIONS[mp.skill_code].engine_supported:
        return mp.skill_code
    options = await skill_options(db, mp.position)
    if not options:
        return None
    return random.Random(f"{mp.user_id}:{day.isoformat()}").choice(options)["code"]


async def training_finish(db: AsyncSession, user: User, hits: int, now: Optional[datetime] = None) -> dict:
    """Credits the training XP (base + per hit): the free run once per local
    day, then one bought extra-training credit per run. The run must have
    been started on the server, take a plausible time and not be stale.
    Every run restores freshness; free runs on consecutive days build the
    streak, and every streak_days in a row pay skill tokens."""
    config = await get_config(db)
    _require_enabled(config)
    from app.services import wallet_service
    from app.services.card_skill_service import _lock_token_row

    now = now or datetime.now(timezone.utc)
    today = local_today(now)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    free_available = mp.training_day != today
    if not free_available and mp.extra_training_credits <= 0:
        raise ConflictError("Тренировка на сегодня уже пройдена — купи дополнительную или приходи завтра")
    started = ensure_aware(mp.training_started_at) if mp.training_started_at else None
    if started is None or now - started > TRAINING_TTL:
        raise ConflictError("Тренировка не начата или устарела — начни заново")
    if (now - started).total_seconds() < TRAINING_MIN_SECONDS:
        raise ConflictError("Слишком быстро — пройди тренировку целиком")
    hits = max(0, min(TRAINING_MAX_HITS, int(hits)))
    xp = add_xp(
        locked, config.my_player_training_xp_base + config.my_player_training_xp_per_hit * hits, config,
        capped=False, bonus_pct=await xp_bonus_pct(db, user.id),
    )
    bonus = await regen_bonus(db, user.id)
    set_freshness(mp, freshness_now(mp, config, now, bonus) + config.my_player_freshness_training, now)
    streak_reward = None
    if free_available:
        mp.training_streak = (mp.training_streak or 0) + 1 if mp.training_day == today - timedelta(days=1) else 1
        mp.training_day = today
        every = max(1, config.my_player_streak_days)
        if config.my_player_streak_tokens > 0 and mp.training_streak % every == 0:
            code = await _streak_skill(db, mp, today)
            if code:
                row = await _lock_token_row(db, locked.id, code, create=True)
                row.quantity += config.my_player_streak_tokens
                definition = SKILL_DEFINITIONS[code]
                streak_reward = {
                    "tokens": config.my_player_streak_tokens, "skill_code": code,
                    "skill_name": definition.name, "skill_icon": definition.icon, "streak": mp.training_streak,
                }
    else:
        mp.extra_training_credits -= 1
    mp.training_started_at = None
    await db.commit()
    view = await get_view(db, locked)
    view["training_xp"] = xp
    view["streak_reward"] = streak_reward
    return view


def _cosmetic_prices(code: str, config) -> tuple[int, int]:
    return (
        int((config.my_player_cosmetic_prices or {}).get(code) or 0),
        int((config.my_player_cosmetic_stars_prices or {}).get(code) or 0),
    )


def _give_cosmetic(mp: MyPlayer, code: str) -> None:
    """Adds `code` to the owned set and puts it on."""
    state = cosmetics_of(mp)
    owned = state["owned"] if code in state["owned"] else [*state["owned"], code]
    if COSMETICS[code][0] == "hair":
        _apply_hair(mp, code, state)
    mp.cosmetics = {**state, "owned": owned, COSMETICS[code][0]: code}


async def buy_cosmetic(db: AsyncSession, user: User, code: str) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    price, stars = _cosmetic_prices(code, config)
    if code not in COSMETICS or (price <= 0 and stars <= 0):
        raise ConflictError("Этого предмета нет в продаже")
    if price <= 0:
        raise ConflictError("Этот предмет продаётся только за звёзды")
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    if code in cosmetics_of(mp)["owned"]:
        raise ConflictError("Уже куплено")
    await wallet_service.debit_coins(
        db, locked, price, TransactionType.my_player_cosmetic, f"Мой игрок: {COSMETICS[code][1]}",
        related_object_type="my_player", related_object_id=mp.id,
    )
    _give_cosmetic(mp, code)
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
    if kind == "hair":
        _apply_hair(mp, code, state)
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


# --- line change («смена амплуа») ----------------------------------------------------

def _check_role(mp: MyPlayer, position: str) -> Position:
    pos = _position(position)
    if category_of(pos) == category_of(mp.position):
        raise ConflictError("Это та же линия — позицию внутри линии можно менять бесплатно")
    return pos


def _apply_role(mp: MyPlayer, pos: Position) -> None:
    """Moves the player to another line. When the main attribute changes
    (e.g. forward -> defender) attack and defense swap, so the player keeps
    his strength where it matters now."""
    if key_attr(pos) != key_attr(mp.position):
        attrs = attributes_of(mp)
        mp.attributes = {"atk": attrs["def"], "def": attrs["atk"]}
    mp.position = pos


async def change_role(db: AsyncSession, user: User, position: str) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    price = config.my_player_role_change_coins
    if price <= 0:
        raise ConflictError("За монеты смена амплуа не продаётся")
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    pos = _check_role(mp, position)
    await wallet_service.debit_coins(
        db, locked, price, TransactionType.my_player_role_change, f"Мой игрок: смена амплуа на {pos.value}",
        related_object_type="my_player", related_object_id=mp.id,
    )
    _apply_role(mp, pos)
    await db.commit()
    return await get_view(db, locked)


# --- friend duels -----------------------------------------------------------------

def _duel_chance(attack: int, defense: int) -> float:
    low, high = DUEL_CHANCE_RANGE
    return max(low, min(high, DUEL_BASE_CHANCE + (attack - defense) * DUEL_SLOPE))


def simulate_duel(me: dict, opp: dict, rng: random.Random) -> tuple[int, int, list[dict]]:
    """DUEL_ATTACKS attacks each, alternating; returns (my goals, opp goals, events)."""
    events: list[dict] = []
    goals = {"me": 0, "opp": 0}
    for n in range(1, DUEL_ATTACKS + 1):
        for side, attacker, defender in (("me", me, opp), ("opp", opp, me)):
            scored = rng.random() < _duel_chance(attacker["attack"], defender["defense"])
            outcome = "goal" if scored else rng.choice(("save", "miss"))
            goals[side] += scored
            events.append({"n": n, "side": side, "outcome": outcome})
    return goals["me"], goals["opp"], events


def _duel_out(duel: MyPlayerDuel, viewer_id: int, names: dict[int, str]) -> dict:
    mine = duel.user_id == viewer_id
    snap = duel.snapshot or {}
    flip = {"win": "loss", "loss": "win", "draw": "draw"}
    return {
        "id": duel.id, "created_at": ensure_aware(duel.created_at).isoformat(),
        "as_challenger": mine,
        "opponent_user_id": duel.opponent_user_id if mine else duel.user_id,
        "opponent_name": names.get(duel.opponent_user_id if mine else duel.user_id, "Игрок"),
        "my_goals": duel.my_goals if mine else duel.opp_goals,
        "opp_goals": duel.opp_goals if mine else duel.my_goals,
        "result": duel.result if mine else flip[duel.result],
        "reward_coins": duel.reward_coins if mine else 0,
        "events": [
            {**e, "side": e["side"] if mine else ("opp" if e["side"] == "me" else "me")} for e in (duel.events or [])
        ],
        "me": snap.get("me") if mine else snap.get("opp"),
        "opp": snap.get("opp") if mine else snap.get("me"),
    }


def _duels_left(mp: MyPlayer, config, today: date) -> int:
    used = mp.duels_today if mp.duels_day == today else 0
    return max(0, config.my_player_duels_per_day - used)


async def duels_view(db: AsyncSession, user: User) -> dict:
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    mp = await get_my_player(db, user.id)
    ids = await friend_ids(db, user.id)
    rows = (await db.execute(
        select(MyPlayer, User).join(User, User.id == MyPlayer.user_id).where(MyPlayer.user_id.in_(ids))
    )).all() if ids else []
    friends = sorted(
        (
            {
                "user_id": owner.id, "user_name": owner.first_name or owner.username or "Игрок",
                "level": level_info(owner.my_player_xp or 0, config)[0], "player": player_out(fmp, config),
            }
            for fmp, owner in rows
        ),
        key=lambda f: (-f["player"]["rating"], f["user_name"]),
    )
    duels = (await db.execute(
        select(MyPlayerDuel).where(or_(MyPlayerDuel.user_id == user.id, MyPlayerDuel.opponent_user_id == user.id))
        .order_by(MyPlayerDuel.id.desc()).limit(10)
    )).scalars().all()
    other_ids = {d.opponent_user_id for d in duels} | {d.user_id for d in duels}
    names = {
        u.id: u.first_name or u.username or "Игрок"
        for u in ((await db.execute(select(User).where(User.id.in_(other_ids)))).scalars().all() if other_ids else [])
    }
    return {
        "enabled": config.my_player_enabled and config.my_player_duels_per_day > 0,
        "left_today": _duels_left(mp, config, local_today()) if mp else 0,
        "per_day": config.my_player_duels_per_day,
        "reward_win": config.my_player_duel_reward_win, "reward_draw": config.my_player_duel_reward_draw,
        "xp": config.my_player_duel_xp,
        "attacks": DUEL_ATTACKS,
        "friends": friends,
        "recent": [_duel_out(d, user.id, names) for d in duels],
    }


async def play_duel(
    db: AsyncSession, user: User, opponent_user_id: int, now: Optional[datetime] = None, rng: Optional[random.Random] = None,
) -> dict:
    """The player's footballer against a friend's: played on the server
    right away (fatigue counts), daily limit, coins + XP for the challenger."""
    config = await get_config(db)
    _require_enabled(config)
    if config.my_player_duels_per_day <= 0:
        raise ConflictError("Дуэли сейчас выключены")
    from app.services import wallet_service
    from app.services.friend_service import friend_ids
    from app.services.notification_service import notify

    now = now or datetime.now(timezone.utc)
    today = local_today(now)
    if opponent_user_id == user.id or opponent_user_id not in await friend_ids(db, user.id):
        raise ConflictError("Вызвать на дуэль можно только друга")
    opp_mp = await get_my_player(db, opponent_user_id)
    if opp_mp is None:
        raise ConflictError("У друга ещё нет своего игрока")
    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = await _locked_player(db, user.id)
    if _duels_left(mp, config, today) <= 0:
        raise ConflictError("Дуэли на сегодня закончились — приходи завтра")

    me_stats, opp_stats = await match_stats(db, mp, config, now), await match_stats(db, opp_mp, config, now)
    my_goals, opp_goals, events = simulate_duel(me_stats, opp_stats, rng or random.Random())
    result = "win" if my_goals > opp_goals else "draw" if my_goals == opp_goals else "loss"
    reward = {"win": config.my_player_duel_reward_win, "draw": config.my_player_duel_reward_draw}.get(result, 0)
    if mp.duels_day != today:
        mp.duels_day, mp.duels_today = today, 0
    mp.duels_today += 1
    me_out, opp_out = player_out(mp, config), player_out(opp_mp, config)
    duel = MyPlayerDuel(
        user_id=user.id, opponent_user_id=opponent_user_id, my_goals=my_goals, opp_goals=opp_goals, result=result,
        reward_coins=reward, events=events,
        snapshot={"me": {**me_out, "match_rating": me_stats["rating"]}, "opp": {**opp_out, "match_rating": opp_stats["rating"]}},
    )
    db.add(duel)
    await db.flush()
    if reward:
        await wallet_service.credit_coins(
            db, locked, reward, TransactionType.my_player_duel_reward, f"Дуэль игроков: {my_goals}:{opp_goals}",
            related_object_type="my_player_duel", related_object_id=duel.id,
        )
    add_xp(locked, config.my_player_duel_xp, config, today, bonus_pct=await xp_bonus_pct(db, user.id))
    challenger = locked.first_name or locked.username or "Друг"
    verdict = {"win": "победил", "draw": "сыграл вничью с", "loss": "проиграл"}[result]
    await notify(
        db, opponent_user_id, NotificationType.my_player_duel, f"Дуэль: {mp.name} против {opp_mp.name}",
        f"{challenger} вызвал твоего игрока: {mp.name} {verdict} {opp_mp.name} ({my_goals}:{opp_goals}). Ответь реваншем!",
        related_object_type="my_player_duel", related_object_id=duel.id,
    )
    await db.commit()
    names = {opponent_user_id: (await db.get(User, opponent_user_id)).first_name or "Игрок"}
    out = _duel_out(duel, user.id, names)
    return {"duel": out, "duels": await duels_view(db, locked), "balance": locked.balance}


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


async def create_stars_invoice(
    db: AsyncSession, user: User, purchase: str, item_id: Optional[int] = None,
    code: Optional[str] = None, position: Optional[str] = None,
) -> dict:
    """Telegram Stars invoice for one extra training ("training"), an
    «Имущество» item ("item"), a cosmetic ("cosmetic"), a line change
    ("role") or a «Карьера игрока» extra ("career": code = pro | agent |
    refresh | heal | save_offer | fast, position carries the club key for
    save_offer). The price is frozen on the invoice."""
    import secrets

    from app.models.lifestyle import LifestyleItem
    from app.models.pack import StarsInvoice
    from app.services import lifestyle_service
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    _require_enabled(config)
    mp = await get_my_player(db, user.id)
    if purchase in ("training", "cosmetic", "role") and mp is None:
        raise NotFoundError("Игрок ещё не создан")
    if purchase == "career":
        from app.services import player_career_shop

        key, title, description, stars = await player_career_shop.stars_order(db, user.id, code or "", position, config)
    elif purchase == "training":
        stars = config.my_player_extra_training_stars
        if stars <= 0:
            raise ConflictError("За звёзды дополнительные тренировки не продаются")
        if _extra_bought_today(mp, local_today()) >= config.my_player_extra_trainings_max:
            raise ConflictError("Лимит дополнительных тренировок на сегодня исчерпан")
        key, title, description = "training", "Дополнительная тренировка", "Ещё одна тренировка для твоего игрока"
    elif purchase == "item" and item_id is not None:
        item = await db.get(LifestyleItem, item_id)
        if item is None:
            raise NotFoundError("Предмет не найден")
        if item.stars_price <= 0:
            raise ConflictError("Этот предмет продаётся только за монеты")
        await lifestyle_service.check_buyable(db, user.id, item)
        stars = item.stars_price
        key, title, description = f"item:{item.id}", item.name, item.description or f"Имущество: {item.name}"
    elif purchase == "cosmetic" and code in COSMETICS:
        stars = _cosmetic_prices(code, config)[1]
        if stars <= 0:
            raise ConflictError("Этот предмет продаётся только за монеты")
        if code in cosmetics_of(mp)["owned"]:
            raise ConflictError("Уже куплено")
        key, title, description = f"cosmetic:{code}", COSMETICS[code][1], f"Стиль для твоего игрока: {COSMETICS[code][1]}"
    elif purchase == "role" and position:
        stars = config.my_player_role_change_stars
        if stars <= 0:
            raise ConflictError("За звёзды смена амплуа не продаётся")
        pos = _check_role(mp, position)
        key, title, description = f"role:{pos.value}", "Смена амплуа", f"Твой игрок переходит на позицию {pos.value}"
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
    purchase = invoice.my_player_purchase
    mp = await get_my_player(db, invoice.user_id)
    if purchase == "training":
        if mp is None or _extra_bought_today(mp, local_today()) >= config.my_player_extra_trainings_max:
            return False, "Лимит дополнительных тренировок на сегодня исчерпан"
        return True, ""
    if purchase.startswith("item:"):
        item = await db.get(LifestyleItem, int(purchase.split(":", 1)[1]))
        if item is None or item.stars_price != invoice.stars_amount:
            return False, "Этот предмет больше не продаётся"
        try:
            await lifestyle_service.check_buyable(db, invoice.user_id, item)
        except ConflictError as exc:
            return False, exc.message
        return True, ""
    if purchase.startswith("cosmetic:"):
        code = purchase.split(":", 1)[1]
        if mp is None or code not in COSMETICS or _cosmetic_prices(code, config)[1] != invoice.stars_amount:
            return False, "Этот предмет больше не продаётся"
        if code in cosmetics_of(mp)["owned"]:
            return False, "Уже куплено"
        return True, ""
    if purchase.startswith("career:"):
        from app.services import player_career_shop

        return await player_career_shop.validate_stars(db, invoice, config)
    if purchase.startswith("role:"):
        if mp is None or config.my_player_role_change_stars != invoice.stars_amount:
            return False, "Цена смены амплуа изменилась — открой покупку заново"
        try:
            _check_role(mp, purchase.split(":", 1)[1])
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
    purchase = invoice.my_player_purchase
    if purchase == "training":
        mp = await _locked_player(db, user.id)
        _count_extra_purchase(mp, config, local_today(), strict=False)
        return {"kind": "training", "name": "Дополнительная тренировка"}
    if purchase.startswith("cosmetic:"):
        code = purchase.split(":", 1)[1]
        mp = await _locked_player(db, user.id)
        if code in COSMETICS:
            _give_cosmetic(mp, code)
        return {"kind": "cosmetic", "name": COSMETICS.get(code, ("", code))[1]}
    if purchase.startswith("career:"):
        from app.services import player_career_shop

        return await player_career_shop.deliver_stars(db, user, invoice, config)
    if purchase.startswith("role:"):
        mp = await _locked_player(db, user.id)
        pos = Position(purchase.split(":", 1)[1])
        if category_of(pos) != category_of(mp.position):
            _apply_role(mp, pos)
        return {"kind": "role", "name": f"Смена амплуа: {pos.value}"}
    item_id = int(purchase.split(":", 1)[1])
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
