"""«Воспитанник Академии»: the user's own child footballer, raised from
`start_age` years old to his peak in about a hundred real days.

- Age follows the calendar: every `days_per_year` local days since creation
  is a year. The age picks the stage (Двор → Детская школа → Юноши → U-19 →
  Дебют, `STAGES` / `stage_ages`); each stage but the last caps the rating
  (`stage_caps`), the last one is capped by the peak.
- The peak comes from the hidden potential ★1-5 (`peak_base` +
  `peak_per_star` × ★) plus peak bonuses: «Династия» (+`dynasty_peak_bonus`
  per earlier generation) and the owner's «Академия» (+1 per
  `academy_levels_per_peak` levels). A scout (Stars) reveals the ★, the
  U-19 stage reveals it on its own. The ★ grows by effort only: a training
  streak (`potential_streak_days`) and stage trials in «Ответка»
  (`trial_*`). The first child of a user is never below
  `first_min_potential`.
- Position: a universal player (provisional CM, drills of every line) until
  `position_stage`; there the coach offers positions by the drills done and
  the talents taken, lines rare among prospects give a deficit bonus (XP and
  «Менеджер» value). A later change costs `position_change_stars`.
- The rating is `start_rating` + XP // `xp_per_point`, capped as above —
  XP banked above a cap counts as soon as the age opens the next stage.
- XP: «Ответка» played by the prospect himself (match / goals / win, under
  the daily cap `daily_xp_cap`), the daily training (+ a streak bonus every
  `streak_days`), story forks every `story_every_days`. Bonuses on top: the
  «Академия» building's training wing, a mentor (an «Академия» path card the
  owner still holds) and the «Личный тренер» bought for Stars.
- In «Ответка» he plays against boys of his age: the rating the engines
  see is 75 ± how far he is ahead of / behind the age curve (`match_rating`).
- Extras: an NPC rival of the same age, the cohort of his start week, an
  album of memories, cosmetics for coins or Stars.

Every number lives in GameConfig.prospect over DEFAULTS. Coins and the
prospect row move under the user row lock; purchases are journaled in
prospect_ledger with a unique (user_id, idempotency_key).
"""
import hashlib
import random
import secrets
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.academy_prospect import AcademyProspect, ProspectLedger
from app.models.card import UserCard
from app.models.enums import Position, TransactionType
from app.models.user import User
from app.services import my_player_service
from app.services.game_config_service import get_config
from app.services.player_stats_service import compute_default_attack_defense
from app.services.wallet_service import debit_coins, lock_user_for_update

DEFAULTS: dict = {
    "enabled": True,
    "start_age": 6,
    "days_per_year": 8,
    # Age each stage begins at (STAGES order); the first must be start_age.
    "stage_ages": [6, 9, 12, 15, 18],
    # Rating cap of every stage but the last (the last is the peak).
    "stage_caps": [38, 52, 66, 78],
    "start_rating": 25,
    "peak_base": 80,
    "peak_per_star": 2,
    # Weights of potential ★1..★5 at creation.
    "potential_weights": [15, 30, 30, 18, 7],
    # The stage (index) that reveals the potential on its own.
    "reveal_stage": 3,
    "xp_per_point": 400,
    "daily_xp_cap": 320,
    "otvetka_match_xp": 40,
    "otvetka_goal_xp": 15,
    "otvetka_win_xp": 30,
    "training_xp": 60,
    "streak_days": 7,
    "streak_bonus_xp": 200,
    "story_every_days": 2,
    "mentor_xp_pct": 10,
    "coach_xp_pct": 25,
    "coach_days": 7,
    "coach_stars": 99,
    "extra_training_stars": 15,
    "extra_trainings_max": 3,
    "scout_stars": 25,
    # How many rating points ahead of the age curve make one «Ответка» edge step.
    "match_edge_per_point": 2,
    "cohort_size": 50,
    # «Менеджер»: from which stage (index) he plays for clubs, and his XP per
    # league match (under the same daily cap).
    "manager_min_stage": 1,
    "manager_match_xp": 30,
    "manager_goal_xp": 15,
    # Coins per season a club may pay him (his own cap, below «Мои игроки»').
    "manager_wage_max": 1500,
    # Other game modes he may play (Пенальти, Штрафной, 1 на 1): XP per game.
    "game_match_xp": 25,
    "game_goal_xp": 8,
    "game_win_xp": 15,
    # Talents: one pick at each of these stages (indexes).
    "spec_stages": [1, 2, 3],
    # Graduation at the last stage: coins to the owner; the next child of the
    # dynasty gets +potential (capped at ★5).
    "graduation_coins": 3000,
    # The very first child of a user (generation 1) is never below this ★.
    "first_min_potential": 3,
    # The ★ grows by effort: +1 for every `potential_streak_days` training days
    # in a row (at most `potential_streak_max` times) and +1 for a passed stage
    # trial — `trial_wins` wins in the first `trial_matches` «Ответка» matches
    # of each stage (index) in `trial_stages`.
    "potential_streak_days": 14,
    "potential_streak_max": 2,
    "trial_stages": [1, 2, 3],
    "trial_matches": 3,
    "trial_wins": 2,
    # Peak rating bonuses: «Династия» per earlier generation (≤ max) and +1 for
    # every `academy_levels_per_peak` levels of the owner's «Академия» (0 = off).
    "dynasty_peak_bonus": 1,
    "dynasty_peak_max": 3,
    "academy_levels_per_peak": 10,
    # Position: the stage (index) where the coach offers `position_options`
    # positions; a line whose share among prospects is below
    # `deficit_share_pct`% of its share in a formation (1/4/4/2 of 11) is in
    # deficit: +XP % and +«Менеджер» value %, frozen at the choice. A change
    # after the choice costs Stars.
    "position_stage": 2,
    "position_options": 3,
    "deficit_share_pct": 80,
    "deficit_xp_pct": 10,
    "deficit_value_pct": 15,
    "position_change_stars": 300,
    # «Турнир набора»: coins to places 1.. of the cohort by XP of an ISO week.
    "week_prizes": [3000, 2000, 1000],
    # Friends' duels in «Ответка»: hours to play, a day's limit, XP to the winner.
    "duel_hours": 48,
    "duels_per_day": 3,
    "duel_win_xp": 80,
    # Bot digest: local hour, only users seen within these days.
    "notify_hour": 18,
    "notify_active_days": 7,
    # Birthday box (Stars, on his birthday, once a year): XP and a cosmetic.
    "bday_stars": 30,
    "bday_xp": 150,
    # Gifts to a friend's prospect (Stars).
    "gift_training_stars": 15,
    "gift_coach_stars": 99,
    # Talent effects: code -> {goal_pct, win_pct, match_pct, train_pct, story_pct, atk, def}.
    "spec_effects": {
        "finisher": {"goal_pct": 50, "atk": 3},
        "playmaker": {"win_pct": 50, "atk": 1, "def": 1},
        "wall": {"match_pct": 30, "def": 3},
        "engine": {"train_pct": 20},
        "leader": {"story_pct": 25},
        "showman": {"goal_pct": 25, "win_pct": 25},
    },
    # Seasonal cosmetics are on sale only between these local dates (MM-DD).
    "seasons": {
        "winter": {"from": "12-01", "until": "01-15"},
        "halloween": {"from": "10-24", "until": "11-07"},
    },
    # Cosmetics: code -> price. 0 = not sold for that currency.
    "cosmetics": {
        "bg_yard": {"coins": 0, "stars": 0},
        "bg_gym": {"coins": 3000, "stars": 0},
        "bg_sunset": {"coins": 6000, "stars": 0},
        "bg_lights": {"coins": 0, "stars": 25},
        "bg_gold": {"coins": 0, "stars": 50},
        "acc_headband": {"coins": 2000, "stars": 0},
        "acc_band": {"coins": 4000, "stars": 0},
        "acc_boots": {"coins": 0, "stars": 20},
        "acc_trophy": {"coins": 0, "stars": 40},
        "bg_snow": {"coins": 0, "stars": 30},
        "acc_scarf": {"coins": 2500, "stars": 0},
        "bg_pumpkin": {"coins": 0, "stars": 25},
        "acc_pumpkin": {"coins": 2000, "stars": 0},
    },
}

GROWING, GRADUATE, RETIRED = "growing", "graduate", "retired"

STAGES = (
    {"code": "yard", "name": "Двор", "emoji": "⚽", "about": "Мяч, коробка во дворе и игры до темноты."},
    {"code": "school", "name": "Детская школа", "emoji": "🏫", "about": "Первый тренер, первая форма, первая позиция."},
    {"code": "youth", "name": "Юноши", "emoji": "🎽", "about": "Турниры сверстников и первые скауты на трибуне."},
    {"code": "u19", "name": "U-19", "emoji": "🔥", "about": "Молодёжка: взрослый футбол уже рядом."},
    {"code": "debut", "name": "Дебют", "emoji": "👑", "about": "Пик формы — время показать себя."},
)

COSMETICS: dict[str, dict] = {
    "bg_yard": {"kind": "background", "name": "Двор", "emoji": "🏘️"},
    "bg_gym": {"kind": "background", "name": "Спортзал школы", "emoji": "🏫"},
    "bg_sunset": {"kind": "background", "name": "Закат на поле", "emoji": "🌅"},
    "bg_lights": {"kind": "background", "name": "Огни стадиона", "emoji": "🏟️"},
    "bg_gold": {"kind": "background", "name": "Золотой час", "emoji": "✨"},
    "acc_headband": {"kind": "accessory", "name": "Повязка на лоб", "emoji": "🎗️"},
    "acc_band": {"kind": "accessory", "name": "Капитанская повязка", "emoji": "©️"},
    "acc_boots": {"kind": "accessory", "name": "Счастливые бутсы", "emoji": "👟"},
    "acc_trophy": {"kind": "accessory", "name": "Первый кубок", "emoji": "🏆"},
    "bg_snow": {"kind": "background", "name": "Зимний двор", "emoji": "❄️", "season": "winter"},
    "acc_scarf": {"kind": "accessory", "name": "Новогодний шарф", "emoji": "🧣", "season": "winter"},
    "bg_pumpkin": {"kind": "background", "name": "Ночь тыкв", "emoji": "🎃", "season": "halloween"},
    "acc_pumpkin": {"kind": "accessory", "name": "Тыквенная повязка", "emoji": "🎃", "season": "halloween"},
}

# Talents (effects in config spec_effects).
SPECS: dict[str, dict] = {
    "finisher": {"name": "Бомбардир", "emoji": "🎯", "about": "больше опыта за голы, атака сильнее"},
    "playmaker": {"name": "Плеймейкер", "emoji": "🧠", "about": "больше опыта за победы, атака и защита"},
    "wall": {"name": "Стена", "emoji": "🧱", "about": "больше опыта за каждый матч, защита сильнее"},
    "engine": {"name": "Мотор", "emoji": "⚡", "about": "больше опыта с тренировок"},
    "leader": {"name": "Лидер", "emoji": "©️", "about": "больше опыта из жизненных историй"},
    "showman": {"name": "Артист", "emoji": "🎩", "about": "больше опыта за голы и победы"},
}

# Daily drills by line: (code, title).
DRILLS: dict[str, tuple[tuple[str, str], ...]] = {
    "GK": (("reflex", "Реакция на линии"), ("cross", "Игра на выходах"), ("kick", "Ввод мяча")),
    "DEF": (("tackle", "Отбор"), ("header", "Игра головой"), ("position", "Выбор позиции")),
    "MID": (("pass", "Короткий пас"), ("vision", "Видение поля"), ("stamina", "Выносливость")),
    "FWD": (("finish", "Удары по воротам"), ("dribble", "Дриблинг"), ("speed", "Рывки")),
}
GRADES = ((1, 25, 80), (2, 50, 100), (3, 25, 130))  # (stars, weight, xp %)

# Story forks: stages they may come at (inclusive indexes), and options with
# {"label", "xp", "coins" (cost), "chance" (% of the "win" outcome),
#  "win_xp", "trial" (the win counts as a won match of the stage trial,
#  once a stage — luck helps the ★ but never replaces playing), "text" (album line)}.
STORIES: tuple[dict, ...] = (
    {"code": "rain", "stages": (0, 1), "title": "Ливень", "text": "За окном ливень, во дворе ни души.", "options": (
        {"label": "Всё равно пойти с мячом", "xp": 50, "text": "Играл под ливнем один — и не пожалел"},
        {"label": "Смотреть футбол дома", "xp": 25, "text": "Разбирал по телевизору, как играют профи"},
    )},
    {"code": "older_kids", "stages": (0, 1), "title": "Старшие ребята", "text": "Старшие зовут в свою команду, но там жёстко.", "options": (
        {"label": "Пойти к старшим", "xp": 20, "chance": 40, "win_xp": 90, "text": "Выдержал игру со старшими"},
        {"label": "Остаться со сверстниками", "xp": 40, "text": "Был лучшим среди своих"},
    )},
    {"code": "new_ball", "stages": (0, 1), "title": "Новый мяч", "text": "Можно купить настоящий кожаный мяч.", "options": (
        {"label": "Купить мяч", "xp": 70, "coins": 300, "text": "Первый настоящий мяч"},
        {"label": "Играть старым", "xp": 30, "text": "Старый мяч ещё послужит"},
    )},
    {"code": "tryout", "stages": (1, 1), "title": "Просмотр в школе", "text": "В футбольной школе просмотр. Волнуешься?", "options": (
        {"label": "Показать финты", "xp": 30, "chance": 50, "win_xp": 100, "text": "Финтами покорил тренера на просмотре"},
        {"label": "Играть просто и надёжно", "xp": 60, "text": "Взяли за надёжность"},
    )},
    {"code": "exam", "stages": (1, 2), "title": "Контрольная", "text": "Завтра контрольная, а сегодня тренировка.", "options": (
        {"label": "На тренировку", "xp": 60, "text": "Выбрал тренировку вместо учебников"},
        {"label": "Подготовиться к контрольной", "xp": 20, "chance": 30, "win_xp": 20, "trial": True,
         "text": "Отличник и футболист — тренер оценил характер"},
    )},
    {"code": "camp", "stages": (1, 2), "title": "Летний лагерь", "text": "Летний футбольный лагерь у моря.", "options": (
        {"label": "Поехать в лагерь", "xp": 120, "coins": 1500, "text": "Лето в футбольном лагере"},
        {"label": "Тренироваться во дворе", "xp": 40, "text": "Лето во дворе с мячом"},
    )},
    {"code": "captain", "stages": (2, 3), "title": "Капитанская повязка", "text": "Тренер предлагает повязку капитана.", "options": (
        {"label": "Взять ответственность", "xp": 40, "chance": 50, "win_xp": 110, "text": "Стал капитаном команды"},
        {"label": "Пусть будет другой", "xp": 50, "text": "Сосредоточился на своей игре"},
    )},
    {"code": "scout_watch", "stages": (2, 3), "title": "Скаут на трибуне", "text": "На матче скаут большого клуба.", "options": (
        {"label": "Рискнуть и взять игру на себя", "xp": 30, "chance": 35, "win_xp": 60, "trial": True,
         "text": "Скаут записал имя в блокнот"},
        {"label": "Играть на команду", "xp": 60, "text": "Сыграл на команду под взглядом скаута"},
    )},
    {"code": "injury", "stages": (2, 4), "title": "Лёгкая травма", "text": "Ноет голеностоп. Выйти на матч?", "options": (
        {"label": "Отдохнуть пару дней", "xp": 40, "text": "Вовремя остановился и восстановился"},
        {"label": "Сыграть через боль", "xp": 10, "chance": 50, "win_xp": 120, "text": "Сыграл через боль и решил матч"},
    )},
    {"code": "agent", "stages": (3, 4), "title": "Агент", "text": "Агент обещает контракт с брендом бутс.", "options": (
        {"label": "Подписать", "xp": 70, "text": "Первый спонсорский контракт"},
        {"label": "Сначала — футбол", "xp": 50, "chance": 30, "win_xp": 20, "trial": True,
         "text": "Отказался от денег ради футбола"},
    )},
    {"code": "abroad", "stages": (3, 4), "title": "Зарубежная академия", "text": "Зовут на сборы в зарубежную академию.", "options": (
        {"label": "Поехать", "xp": 150, "coins": 3000, "text": "Сборы в зарубежной академии"},
        {"label": "Остаться дома", "xp": 50, "text": "Остался верен родному клубу"},
    )},
    {"code": "night", "stages": (3, 4), "title": "Вечеринка", "text": "Друзья зовут на вечеринку перед игрой.", "options": (
        {"label": "Лечь спать пораньше", "xp": 70, "text": "Выспался перед важной игрой"},
        {"label": "Ненадолго заглянуть", "xp": 10, "chance": 50, "win_xp": 40, "text": "Заглянул к друзьям — и успел выспаться"},
    )},
    {"code": "big_club", "stages": (3, 4), "title": "Предложение гранда", "text": "Гранд зовёт в свою академию, но там долго ждать шанса.", "options": (
        {"label": "Уйти в гранд", "xp": 40, "chance": 40, "win_xp": 160, "text": "Пробился в академию гранда"},
        {"label": "Остаться, где играешь", "xp": 80, "text": "Выбрал игровую практику"},
    )},
    {"code": "national", "stages": (3, 4), "title": "Вызов в сборную", "text": "Вызов в юношескую сборную — но в клубе важный матч.", "options": (
        {"label": "Поехать в сборную", "xp": 90, "text": "Надел футболку юношеской сборной"},
        {"label": "Остаться в клубе", "xp": 50, "chance": 40, "win_xp": 40, "trial": True,
         "text": "Клуб запомнил преданность"},
    )},
    {"code": "interview", "stages": (3, 4), "title": "Первое интервью", "text": "Журналист просит интервью после хет-трика.", "options": (
        {"label": "Поблагодарить команду", "xp": 60, "text": "Скромное первое интервью"},
        {"label": "Пообещать Золотой мяч", "xp": 20, "chance": 50, "win_xp": 110, "text": "Громкое обещание — и гол в следующем матче"},
    )},
    {"code": "legend", "stages": (2, 4), "title": "Встреча с легендой", "text": "Легенда клуба смотрит тренировку.", "options": (
        {"label": "Попросить совет", "xp": 90, "text": "Совет легенды запомнится навсегда"},
        {"label": "Показать удар", "xp": 30, "chance": 50, "win_xp": 130, "text": "Легенда похлопала по плечу после удара"},
    )},
)

# Lines and the positions the coach may offer in each (my_player lines).
LINE_POSITIONS: dict[str, tuple[str, ...]] = {
    "GK": ("GK",), "DEF": ("CB", "LB", "RB"), "MID": ("CDM", "CM", "CAM", "LM", "RM"), "FWD": ("ST", "LW", "RW"),
}
LINE_NAMES = {"GK": "Вратарь", "DEF": "Защита", "MID": "Полузащита", "FWD": "Атака"}
# A line's places in an 11 (the deficit is measured against these shares).
LINE_TARGET = {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2}
# Talents lean to lines (weight in drills).
SPEC_LINES: dict[str, dict[str, int]] = {
    "wall": {"DEF": 3}, "finisher": {"FWD": 3}, "playmaker": {"MID": 3}, "engine": {"MID": 2}, "showman": {"FWD": 2},
}
# Smoothing of the line shares: as if this many prospects already sat at the target shares.
_SHARE_PRIOR = 22
UNIVERSAL_POSITION = Position.CM

RIVAL_NAMES = ("Артём Лис", "Марк Орлов", "Тимур Гром", "Лео Сокол", "Даня Ветров", "Ян Буря", "Илья Шторм", "Макс Волков")


def cfg(config) -> dict:
    stored = getattr(config, "prospect", None) or {}
    out = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    out["cosmetics"] = {**DEFAULTS["cosmetics"], **{
        k: v for k, v in (stored.get("cosmetics") or {}).items() if k in COSMETICS and isinstance(v, dict)
    }}
    out["spec_effects"] = {**DEFAULTS["spec_effects"], **{
        k: v for k, v in (stored.get("spec_effects") or {}).items() if k in SPECS and isinstance(v, dict)
    }}
    out["seasons"] = {**DEFAULTS["seasons"], **{
        k: v for k, v in (stored.get("seasons") or {}).items() if k in DEFAULTS["seasons"] and isinstance(v, dict)
    }}
    return out


def validate(raw: dict) -> dict:
    """Admin input: known keys only, non-negative numbers, lists of
    non-negative numbers, cosmetics prices by known code."""
    out: dict = {}
    for key, value in (raw or {}).items():
        if key not in DEFAULTS:
            raise ValueError(f"неизвестный параметр «{key}»")
        default = DEFAULTS[key]
        if isinstance(default, bool):
            out[key] = bool(value)
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{key}: нужно неотрицательное число")
            out[key] = int(value)
        elif isinstance(default, list):
            if not isinstance(value, list) or not value or not all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in value
            ):
                raise ValueError(f"{key}: нужен список неотрицательных чисел")
            out[key] = [int(x) for x in value]
        elif key == "cosmetics":
            if not isinstance(value, dict) or any(k not in COSMETICS for k in value):
                raise ValueError("cosmetics: коды только из каталога")
            out[key] = {k: {"coins": max(0, int(v.get("coins", 0))), "stars": max(0, int(v.get("stars", 0)))}
                        for k, v in value.items() if isinstance(v, dict)}
        elif key == "spec_effects":
            if not isinstance(value, dict) or any(k not in SPECS for k in value):
                raise ValueError("spec_effects: коды талантов только из каталога")
            fields = ("goal_pct", "win_pct", "match_pct", "train_pct", "story_pct", "atk", "def")
            out[key] = {k: {f: max(0, int(v[f])) for f in fields if f in v} for k, v in value.items() if isinstance(v, dict)}
        elif key == "seasons":
            if not isinstance(value, dict) or any(k not in DEFAULTS["seasons"] for k in value):
                raise ValueError("seasons: только известные сезоны")
            for v in value.values():
                for edge in ("from", "until"):
                    try:
                        datetime.strptime(f"2024-{v[edge]}", "%Y-%m-%d")
                    except (KeyError, TypeError, ValueError):
                        raise ValueError("seasons: даты в формате ММ-ДД") from None
            out[key] = {k: {"from": v["from"], "until": v["until"]} for k, v in value.items()}
    merged = {**DEFAULTS, **out}
    if len(merged["stage_ages"]) != len(STAGES) or merged["stage_ages"] != sorted(merged["stage_ages"]):
        raise ValueError(f"stage_ages: {len(STAGES)} возрастов по возрастанию")
    if merged["stage_ages"][0] != merged["start_age"]:
        raise ValueError("stage_ages: первая ступень начинается со start_age")
    if len(merged["stage_caps"]) != len(STAGES) - 1:
        raise ValueError(f"stage_caps: {len(STAGES) - 1} потолка (у последней ступени — пик)")
    if len(merged["potential_weights"]) != 5 or not any(merged["potential_weights"]):
        raise ValueError("potential_weights: 5 весов, хотя бы один больше 0")
    return out


def _require_enabled(c: dict) -> None:
    if not c["enabled"]:
        raise ConflictError("«Воспитанник Академии» сейчас недоступен")


# --- pure progression --------------------------------------------------------

def age_days(p: AcademyProspect, today: date) -> int:
    return max(0, (today - local_today(ensure_aware(p.created_at))).days)


def age_of(days: int, c: dict) -> int:
    return int(c["start_age"]) + days // max(1, int(c["days_per_year"]))


def stage_index(age: int, c: dict) -> int:
    index = 0
    for i, start in enumerate(c["stage_ages"][: len(STAGES)]):
        if age >= int(start):
            index = i
    return index


def peak_of(potential: int, c: dict, bonus: int = 0) -> int:
    return min(99, int(c["peak_base"]) + int(c["peak_per_star"]) * max(1, min(5, potential)) + max(0, int(bonus)))


def dynasty_peak(generation: int, c: dict) -> int:
    return min(int(c["dynasty_peak_max"]), max(0, int(generation or 1) - 1) * int(c["dynasty_peak_bonus"]))


def academy_peak_for(level: int, c: dict) -> int:
    per = int(c["academy_levels_per_peak"])
    return max(0, int(level)) // per if per > 0 else 0


def peak_bonus(p: AcademyProspect, c: dict) -> int:
    """+peak rating: «Династия» and the owner's «Академия»."""
    return dynasty_peak(p.generation, c) + max(0, int(p.academy_peak or 0))


def stage_cap(stage: int, potential: int, c: dict, bonus: int = 0) -> int:
    peak = peak_of(potential, c, bonus)
    caps = list(c["stage_caps"])
    return min(peak, int(caps[stage])) if stage < len(caps) else peak


def raw_rating(xp: int, c: dict) -> int:
    return int(c["start_rating"]) + max(0, xp) // max(1, int(c["xp_per_point"]))


def rating_of(p: AcademyProspect, c: dict, today: date) -> int:
    stage = stage_index(age_of(age_days(p, today), c), c)
    return min(raw_rating(p.xp, c), stage_cap(stage, p.potential, c, peak_bonus(p, c)))


def days_to_peak(c: dict) -> int:
    return (int(c["stage_ages"][-1]) - int(c["start_age"])) * max(1, int(c["days_per_year"]))


def curve_rating(days: int, peak: int, c: dict) -> int:
    """Where a boy growing steadily to `peak` stands on day `days`: a straight
    line to the peak at the debut age, capped by the stage."""
    start = int(c["start_rating"])
    line = start + round((peak - start) * min(1.0, days / max(1, days_to_peak(c))))
    stage = stage_index(age_of(days, c), c)
    caps = list(c["stage_caps"])
    cap = min(peak, int(caps[stage])) if stage < len(caps) else peak
    return min(line, cap)


def match_rating(p: AcademyProspect, c: dict, today: date) -> int:
    """The rating «Ответка» sees: he plays boys of his age, so 75 is «on the
    curve of an average ★3 boy», every point ahead adds an edge step."""
    days = age_days(p, today)
    expected = curve_rating(days, peak_of(3, c), c)
    return max(40, min(99, 75 + int(c["match_edge_per_point"]) * (rating_of(p, c, today) - expected)))


def roll_potential(c: dict, rnd: random.Random) -> int:
    weights = [max(0, int(w)) for w in c["potential_weights"][:5]] or [1]
    return rnd.choices(range(1, len(weights) + 1), weights=weights)[0]


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def spec_pct(p: AcademyProspect, c: dict, field: str) -> int:
    effects = c["spec_effects"]
    return sum(int((effects.get(code) or {}).get(field, 0)) for code in (p.specs or []))


def with_spec(p: AcademyProspect, c: dict, field: str, xp: int) -> int:
    return int(xp) + int(xp) * spec_pct(p, c, field) // 100


def atk_def_of(p: AcademyProspect, c: dict, rating: int) -> tuple[int, int]:
    attack, defense = compute_default_attack_defense(rating, p.position)
    return (max(1, min(99, attack + spec_pct(p, c, "atk"))), max(1, min(99, defense + spec_pct(p, c, "def"))))


def _bump_week(p: AcademyProspect, gained: int, today: date) -> None:
    key = week_key(today)
    if p.week_key != key:
        p.last_week_key, p.last_week_xp = p.week_key, p.week_xp
        p.week_key, p.week_xp = key, 0
    p.week_xp += max(0, gained)


def _reset_xp_day(p: AcademyProspect, today: date) -> None:
    if p.xp_day != today:
        p.xp_day = today
        p.xp_today = 0


def grant_xp(p: AcademyProspect, base: int, c: dict, today: date, bonus_pct: int = 0, capped: bool = True) -> int:
    """Adds XP; matches (`capped`) count against the daily cap — the bonus
    goes on top of what the cap let through. Returns what was added."""
    base = max(0, int(base))
    if capped:
        _reset_xp_day(p, today)
        allowed = max(0, int(c["daily_xp_cap"]) - p.xp_today)
        base = min(base, allowed)
        p.xp_today += base
    gained = base + base * max(0, bonus_pct) // 100
    p.xp += gained
    _bump_week(p, gained, today)
    return gained


def _remember(p: AcademyProspect, today: date, code: str, text: str) -> None:
    memories = list(p.memories or [])
    if any(m.get("code") == code for m in memories):
        return
    memories.append({"day": today.isoformat(), "code": code, "text": text})
    p.memories = memories[-60:]
    flag_modified(p, "memories")


def _stats(p: AcademyProspect) -> dict:
    return dict(p.stats or {})


def _set_stats(p: AcademyProspect, stats: dict) -> None:
    p.stats = stats
    flag_modified(p, "stats")


def sync(p: AcademyProspect, c: dict, today: date) -> None:
    """Time-driven changes, applied lazily: a memory for every stage reached,
    the potential revealed at `reveal_stage`."""
    stage = stage_index(age_of(age_days(p, today), c), c)
    for i in range(1, stage + 1):
        _remember(p, today, f"stage:{STAGES[i]['code']}", f"{STAGES[i]['emoji']} Новая ступень: {STAGES[i]['name']}")
    if stage >= int(c["reveal_stage"]) and not p.potential_revealed:
        p.potential_revealed = True


# --- story forks -------------------------------------------------------------

def _pick(seed: str, n: int) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % max(1, n)


def current_story(p: AcademyProspect, c: dict, today: date) -> Optional[dict]:
    if age_days(p, today) < 1:
        return None
    if p.story_day is not None and (today - p.story_day).days < int(c["story_every_days"]):
        return None
    stage = stage_index(age_of(age_days(p, today), c), c)
    eligible = [s for s in STORIES if s["stages"][0] <= stage <= s["stages"][1]]
    seen = set(_stats(p).get("stories") or [])
    fresh = [s for s in eligible if s["code"] not in seen] or eligible
    if not fresh:
        return None
    return fresh[_pick(f"{p.id}:{today.isoformat()}", len(fresh))]


def story_out(story: Optional[dict], trial_open: bool = False) -> Optional[dict]:
    """`trial_open`: a win may still count in the stage trial right now."""
    if story is None:
        return None
    return {
        "code": story["code"], "title": story["title"], "text": story["text"],
        "options": [{
            "label": o["label"], "xp": o["xp"], "coins": o.get("coins", 0), "chance": o.get("chance"),
            "win_xp": o.get("win_xp"), "trial": bool(o.get("trial")) and trial_open,
        } for o in story["options"]],
    }


# --- rival / cohort ----------------------------------------------------------

def rival_of(p: AcademyProspect, c: dict, today: date) -> dict:
    rnd = random.Random(p.rival_seed)
    name = RIVAL_NAMES[rnd.randrange(len(RIVAL_NAMES))]
    peak = int(c["peak_base"]) + 1 + rnd.randrange(4) * 2
    days = age_days(p, today)
    jitter = random.Random(p.rival_seed * 1009 + days).randint(-1, 1) if days else 0
    rating = max(int(c["start_rating"]), curve_rating(days, peak, c) + jitter)
    mine = rating_of(p, c, today)
    return {"name": name, "rating": rating, "ahead": mine - rating}


def cohort_key(created_at: datetime) -> str:
    year, week, _ = local_today(ensure_aware(created_at)).isocalendar()
    return f"{year}-W{week:02d}"


def _week_bounds(created_at: datetime) -> tuple[datetime, datetime]:
    day = local_today(ensure_aware(created_at))
    monday = day - timedelta(days=day.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc) - timedelta(days=1)
    return start, start + timedelta(days=9)


async def cohort(db: AsyncSession, p: AcademyProspect, c: dict, today: date) -> dict:
    """Everyone who started in the same local ISO week, by rating."""
    key = cohort_key(p.created_at)
    start, end = _week_bounds(p.created_at)
    rows = (await db.execute(select(AcademyProspect).where(
        AcademyProspect.created_at >= start, AcademyProspect.created_at < end,
    ))).scalars().all()
    peers = [r for r in rows if cohort_key(r.created_at) == key]
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([r.user_id for r in peers])))).scalars()}
    ranked = sorted(
        ({"user_id": r.user_id, "name": r.name, "owner": getattr(owners.get(r.user_id), "first_name", None),
          "rating": rating_of(r, c, today), "xp": r.xp} for r in peers),
        key=lambda e: (-e["rating"], -e["xp"], e["user_id"]),
    )
    place = next((i + 1 for i, e in enumerate(ranked) if e["user_id"] == p.user_id), None)
    top = [{k: v for k, v in e.items() if k != "xp"} | {"place": i + 1, "me": e["user_id"] == p.user_id}
           for i, e in enumerate(ranked[: int(c["cohort_size"])])]
    return {"key": key, "size": len(ranked), "place": place, "top": top}


# --- bonuses -----------------------------------------------------------------

async def _mentor(db: AsyncSession, p: AcademyProspect) -> Optional[UserCard]:
    if not p.mentor_card_id:
        return None
    from app.services.path_service import is_path_card

    card = (await db.execute(
        select(UserCard).options(selectinload(UserCard.player)).where(UserCard.id == p.mentor_card_id)
    )).scalar_one_or_none()
    if card is None or card.owner_id != p.user_id or not is_path_card(card):
        return None
    return card


def coach_active(p: AcademyProspect, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return p.coach_until is not None and ensure_aware(p.coach_until) > now


async def bonus_parts(db: AsyncSession, p: AcademyProspect, config, c: dict) -> dict:
    from app.services import academy_service

    effects = await academy_service.user_effects(db, p.user_id, config) if config.academy_enabled else {}
    return {
        "academy": int(effects.get("training", 0)),
        "mentor": int(c["mentor_xp_pct"]) if await _mentor(db, p) is not None else 0,
        "coach": int(c["coach_xp_pct"]) if coach_active(p) else 0,
        "deficit": int((_stats(p).get("deficit") or {}).get("xp_pct", 0)),
    }


async def bonus_pct(db: AsyncSession, p: AcademyProspect, config, c: dict) -> int:
    return sum((await bonus_parts(db, p, config, c)).values())


# --- potential growth, peak bonuses, position --------------------------------

# Service fields in stats (not shown as his numbers).
_INTERNAL_STATS = ("stories", "drills", "trials", "streak_potential", "deficit")


async def academy_level(db: AsyncSession, user_id: int) -> int:
    """The owner's «Академия» level: the sum of its wing levels."""
    from app.models.card_path import UserAcademy
    from app.services import academy_service

    return sum(academy_service.effective_levels(await db.get(UserAcademy, user_id)).values())


async def refresh_academy_peak(db: AsyncSession, p: AcademyProspect, config, c: dict) -> None:
    """+1 peak rating per `academy_levels_per_peak` «Академия» levels; never lowered."""
    if not getattr(config, "academy_enabled", True):
        return
    got = academy_peak_for(await academy_level(db, p.user_id), c)
    if got > int(p.academy_peak or 0):
        p.academy_peak = got


def _raise_potential(p: AcademyProspect, today: date, code: str, text: str) -> bool:
    if p.potential >= 5:
        return False
    p.potential += 1
    _remember(p, today, code, text)
    return True


def _streak_potential(p: AcademyProspect, c: dict, stats: dict, today: date) -> bool:
    """+1★ on every `potential_streak_days`-th training day in a row."""
    every = int(c["potential_streak_days"])
    got = int(stats.get("streak_potential", 0))
    if every <= 0 or p.training_streak % every or got >= int(c["potential_streak_max"]):
        return False
    if not _raise_potential(p, today, f"pot_streak:{got + 1}",
                            f"📈 {p.training_streak} дней тренировок без пропусков — потенциал вырос"):
        return False
    stats["streak_potential"] = got + 1
    return True


def _trial_rules(c: dict) -> tuple[int, int]:
    total = max(1, int(c["trial_matches"]))
    return total, max(1, min(int(c["trial_wins"]), total))


def _trial_state(stats: dict, stage: int) -> dict:
    return dict((stats.get("trials") or {}).get(str(stage)) or {"played": 0, "wins": 0})


def _trial_match(p: AcademyProspect, c: dict, stats: dict, won: bool, today: date) -> bool:
    """A stage trial: the first `trial_matches` «Ответка» matches of the
    stage; `trial_wins` wins pass it (+1★), too many losses fail it."""
    stage = stage_of(p, c, today)
    if stage not in {int(x) for x in c["trial_stages"]}:
        return False
    t = _trial_state(stats, stage)
    if "passed" in t:
        return False
    total, need = _trial_rules(c)
    t["played"] += 1
    t["wins"] += int(bool(won))
    up = False
    if t["wins"] >= need:
        t["passed"] = True
        up = _raise_potential(p, today, f"trial:{STAGES[stage]['code']}",
                              f"🏅 Испытание ступени «{STAGES[stage]['name']}» пройдено — потенциал вырос")
    elif t["played"] - t["wins"] > total - need:
        t["passed"] = False
    stats["trials"] = {**(stats.get("trials") or {}), str(stage): t}
    return up


def trial_credit_open(p: AcademyProspect, c: dict, stats: dict, today: date) -> bool:
    """A story win may count in this stage's trial: a trial stage, the trial
    not decided yet and no story credit used on it."""
    stage = stage_of(p, c, today)
    if stage not in {int(x) for x in c["trial_stages"]}:
        return False
    t = _trial_state(stats, stage)
    return "passed" not in t and not t.get("story")


def growth_out(p: AcademyProspect, c: dict, today: date, academy_lvl: int) -> dict:
    """How the ★ grows (streak, trials) and where the peak bonuses come from."""
    stats = _stats(p)
    stage = stage_of(p, c, today)
    total, need = _trial_rules(c)
    trials = []
    for st in sorted({int(x) for x in c["trial_stages"]}):
        if st >= len(STAGES):
            continue
        t = _trial_state(stats, st)
        status = ("passed" if t.get("passed") is True else "failed" if t.get("passed") is False
                  else "active" if st == stage else "missed" if st < stage else "upcoming")
        trials.append({"stage": st, "name": STAGES[st]["name"], "played": t["played"], "wins": t["wins"], "status": status,
                       "story": bool(t.get("story"))})
    per = int(c["academy_levels_per_peak"])
    return {
        "potential_max": p.potential >= 5,
        "streak": {"every": int(c["potential_streak_days"]), "ups": int(stats.get("streak_potential", 0)),
                   "max": int(c["potential_streak_max"]),
                   "current": p.training_streak if p.training_day in (today, today - timedelta(days=1)) else 0},
        "trial": {"matches": total, "wins_needed": need, "stages": trials},
        "peak": {"dynasty": dynasty_peak(p.generation, c), "dynasty_per": int(c["dynasty_peak_bonus"]),
                 "academy": int(p.academy_peak or 0), "academy_level": academy_lvl, "per_levels": per,
                 "next_level": (academy_lvl // per + 1) * per if per > 0 else None},
    }


def line_scores(p: AcademyProspect) -> dict[str, int]:
    """How much he leans to each line: drills done there plus talents."""
    drills = _stats(p).get("drills") or {}
    scores = {line: int(drills.get(line, 0)) for line in LINE_POSITIONS}
    for code in p.specs or []:
        for line, weight in SPEC_LINES.get(code, {}).items():
            scores[line] += weight
    return scores


async def deficit_lines(db: AsyncSession, c: dict, exclude_id: Optional[int] = None) -> set[str]:
    """Lines whose share among prospects with a position (growing or
    graduates) is below `deficit_share_pct`% of the formation share."""
    query = select(AcademyProspect.position).where(
        AcademyProspect.position_set.is_(True), AcademyProspect.status.in_([GROWING, GRADUATE]))
    if exclude_id is not None:
        query = query.where(AcademyProspect.id != exclude_id)
    counts = {line: 0 for line in LINE_POSITIONS}
    for pos in (await db.execute(query)).scalars():
        counts[my_player_service.category_of(Position(pos))] += 1
    total = sum(counts.values())
    out = set()
    for line, places in LINE_TARGET.items():
        target = places / 11
        share = (counts[line] + _SHARE_PRIOR * target) / (total + _SHARE_PRIOR)
        if share * 100 < target * int(c["deficit_share_pct"]):
            out.add(line)
    return out


def position_offers(p: AcademyProspect, c: dict, deficits: set[str]) -> list[dict]:
    """The coach's offer: two positions of his strongest line, then one of
    each next line (ties go to deficit lines), `position_options` in all."""
    scores = line_scores(p)
    order = list(LINE_POSITIONS)
    lines = sorted(order, key=lambda line: (-scores[line], line not in deficits, order.index(line)))
    picks: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        pool = list(LINE_POSITIONS[line])
        random.Random(f"{p.rival_seed}:{line}").shuffle(pool)
        picks += [(pos, line) for pos in pool[: 2 if i == 0 else 1]]
    talents = {line: [SPECS[code]["name"] for code in (p.specs or []) if line in SPEC_LINES.get(code, {})] for line in order}
    drills = _stats(p).get("drills") or {}
    return [{
        "position": pos, "line": line, "line_name": LINE_NAMES[line], "drills": int(drills.get(line, 0)),
        "talents": talents[line], "deficit": line in deficits,
        "xp_pct": int(c["deficit_xp_pct"]) if line in deficits else 0,
        "value_pct": int(c["deficit_value_pct"]) if line in deficits else 0,
    } for pos, line in picks[: max(1, int(c["position_options"]))]]


async def position_pick_out(db: AsyncSession, p: AcademyProspect, c: dict, today: date) -> Optional[dict]:
    if p.position_set or stage_of(p, c, today) < int(c["position_stage"]):
        return None
    return {"options": position_offers(p, c, await deficit_lines(db, c))}


def value_pct(p: AcademyProspect) -> int:
    """«Менеджер» value bonus of a deficit position (frozen at the choice)."""
    return int((_stats(p).get("deficit") or {}).get("value_pct", 0))


async def _set_position(db: AsyncSession, p: AcademyProspect, c: dict, position: Position, today: date,
                        changed: bool = False) -> None:
    """Sets the position and freezes the deficit bonus of its line now."""
    line = my_player_service.category_of(position)
    deficit = line in await deficit_lines(db, c, exclude_id=p.id)
    p.position = position
    p.position_set = True
    stats = _stats(p)
    if deficit:
        stats["deficit"] = {"line": line, "xp_pct": int(c["deficit_xp_pct"]), "value_pct": int(c["deficit_value_pct"])}
    else:
        stats.pop("deficit", None)
    _set_stats(p, stats)
    if changed:
        _remember(p, today, f"position:{today.isoformat()}:{position.value}", f"🔁 Переход на позицию {position.value}")
    else:
        _remember(p, today, "position", f"🧭 Тренер поставил на позицию {position.value}")


async def choose_position(db: AsyncSession, user: User, position: str) -> dict:
    """One of the coach's offers, once he reaches `position_stage`."""
    c = cfg(await get_config(db))
    _require_enabled(c)
    p = await _locked(db, user.id)
    today = local_today()
    if p.position_set:
        raise ConflictError(f"Позиция уже выбрана — сменить можно за {int(c['position_change_stars'])} ⭐")
    stage = int(c["position_stage"])
    if stage_of(p, c, today) < stage:
        raise ConflictError(f"Позицию тренер предложит на ступени «{STAGES[min(stage, len(STAGES) - 1)]['name']}»")
    options = position_offers(p, c, await deficit_lines(db, c))
    if position not in {o["position"] for o in options}:
        raise ConflictError("Тренер предлагает другие позиции — обнови экран")
    await _set_position(db, p, c, my_player_service._position(position), today)
    db.add(p)
    await db.commit()
    return await get_view(db, await db.get(User, user.id))


# --- reads -------------------------------------------------------------------

async def get_prospect(db: AsyncSession, user_id: int, status: str = GROWING) -> Optional[AcademyProspect]:
    """The growing child (default) or the active graduate of a user."""
    return (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == status)
    )).scalar_one_or_none()


async def _locked(db: AsyncSession, user_id: int, status: str = GROWING) -> AcademyProspect:
    p = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == status)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if p is None:
        raise NotFoundError("Воспитанника ещё нет" if status == GROWING else "Выпускника ещё нет")
    return p


def season_active(c: dict, season: Optional[str], today: date) -> bool:
    """A seasonal item is on sale between its season's MM-DD dates (the
    window may wrap the new year)."""
    if not season:
        return True
    window = c["seasons"].get(season)
    if not window:
        return False
    md = today.strftime("%m-%d")
    start, end = window["from"], window["until"]
    return start <= md <= end if start <= end else (md >= start or md <= end)


def prospect_out(p: AcademyProspect, c: dict, today: date) -> dict:
    days = age_days(p, today)
    age = age_of(days, c)
    stage = stage_index(age, c)
    rating = rating_of(p, c, today)
    bonus = peak_bonus(p, c)
    cap = stage_cap(stage, p.potential, c, bonus)
    per = max(1, int(c["xp_per_point"]))
    raw = raw_rating(p.xp, c)
    next_age_day = None
    if stage + 1 < len(STAGES):
        next_age_day = (int(c["stage_ages"][stage + 1]) - int(c["start_age"])) * max(1, int(c["days_per_year"]))
    cos = dict(p.cosmetics or {})
    return {
        "name": p.name, "number": p.number, "position": p.position.value, "foot": p.foot,
        "appearance": p.appearance or {}, "age": age, "age_days": days,
        "days_to_birthday": max(1, int(c["days_per_year"])) - days % max(1, int(c["days_per_year"])),
        "stage": stage, "stage_code": STAGES[stage]["code"],
        "rating": rating, "stage_cap": cap, "capped": raw >= cap and rating >= cap,
        "banked_points": max(0, raw - rating),
        "xp": p.xp, "xp_in_point": p.xp % per, "xp_per_point": per,
        "potential": p.potential if p.potential_revealed else None,
        "peak": peak_of(p.potential, c, bonus) if p.potential_revealed else None,
        "peak_bonus": {"dynasty": dynasty_peak(p.generation, c), "academy": max(0, int(p.academy_peak or 0))},
        "universal": not p.position_set, "line": my_player_service.category_of(p.position),
        "deficit": _stats(p).get("deficit"),
        "days_to_next_stage": None if next_age_day is None else max(0, next_age_day - days),
        "background": cos.get("background") or "bg_yard", "accessory": cos.get("accessory"),
        "owned_cosmetics": sorted(set(cos.get("owned") or []) | {"bg_yard"}),
        "stats": {k: v for k, v in _stats(p).items() if k not in _INTERNAL_STATS},
        "memories": list(reversed(p.memories or []))[:30],
        "atk_def": list(atk_def_of(p, c, rating)),
        "generation": p.generation,
        "specs": [{"code": code, **SPECS[code]} for code in (p.specs or []) if code in SPECS],
    }


def drills_for(p: AcademyProspect, today: date) -> list[dict]:
    """His line's drills; a universal player gets one drill of every line
    (rotating by day) — what he trains decides the positions offered later."""
    if p.position_set:
        line = my_player_service.category_of(p.position)
        return [{"code": code, "title": title, "line": line} for code, title in DRILLS[line]]
    n = today.toordinal()
    out = []
    for i, (line, drills) in enumerate(DRILLS.items()):
        code, title = drills[(n + i) % len(drills)]
        out.append({"code": code, "title": title, "line": line})
    return out


def _training_out(p: AcademyProspect, c: dict, today: date) -> dict:
    streak = p.training_streak if p.training_day in (today, today - timedelta(days=1)) else 0
    return {
        "free_available": p.training_day != today,
        "extra_credits": p.extra_credits,
        "extra_bought_today": p.extra_bought if p.extra_day == today else 0,
        "extra_max": int(c["extra_trainings_max"]),
        "extra_stars": int(c["extra_training_stars"]),
        "xp": with_spec(p, c, "train_pct", int(c["training_xp"])), "streak": streak, "streak_days": int(c["streak_days"]),
        "streak_bonus_xp": int(c["streak_bonus_xp"]),
        "drills": drills_for(p, today), "universal": not p.position_set,
    }


def _shop_out(p: AcademyProspect, c: dict, today: Optional[date] = None) -> list[dict]:
    """The catalog; a seasonal item shows only in its season (or once owned)."""
    today = today or local_today()
    owned = set((p.cosmetics or {}).get("owned") or []) | {"bg_yard"}
    return [{
        "code": code, "kind": meta["kind"], "name": meta["name"], "emoji": meta["emoji"],
        "coins": int(c["cosmetics"].get(code, {}).get("coins", 0)),
        "stars": int(c["cosmetics"].get(code, {}).get("stars", 0)), "owned": code in owned,
        "season": meta.get("season"),
    } for code, meta in COSMETICS.items() if code in owned or season_active(c, meta.get("season"), today)]


async def _mentor_options(db: AsyncSession, user_id: int) -> list[dict]:
    from app.services.path_service import is_path_card

    from app.models.player import Player

    cards = (await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(selectinload(UserCard.player))
        .where(UserCard.owner_id == user_id, Player.path_talent_code.is_not(None))
    )).scalars().all()
    out = [{"card_id": card.id, "name": card.player.display_name, "position": card.player.position.value,
            "rating": card.player.rating} for card in cards if is_path_card(card)]
    return sorted(out, key=lambda o: (-o["rating"], o["name"]))[:40]


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    c = cfg(config)
    today = local_today()
    await db.refresh(user)
    base = {
        "enabled": bool(c["enabled"]), "balance": user.balance,
        "stages": [{**s, "from_age": int(c["stage_ages"][i]),
                    "cap": int(c["stage_caps"][i]) if i < len(c["stage_caps"]) else None} for i, s in enumerate(STAGES)],
        "positions": [pos.value for pos in Position],
        "appearance_options": my_player_service.APPEARANCE_OPTIONS,
        "days_per_year": int(c["days_per_year"]), "start_age": int(c["start_age"]),
        "peak_range": [peak_of(1, c), peak_of(5, c)],
    }
    from app.services import prospect_life

    life = await prospect_life.view_extras(db, user, c, today)
    p = await get_prospect(db, user.id)
    if p is None:
        return {**base, **life, "prospect": None}
    sync(p, c, today)
    await refresh_academy_peak(db, p, config, c)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    parts = await bonus_parts(db, p, config, c)
    mentor = await _mentor(db, p)
    _reset_xp_day(p, today)
    return {
        **base,
        "prospect": prospect_out(p, c, today),
        "xp_today": p.xp_today, "daily_xp_cap": int(c["daily_xp_cap"]),
        "otvetka_xp": {"match": int(c["otvetka_match_xp"]), "goal": int(c["otvetka_goal_xp"]), "win": int(c["otvetka_win_xp"])},
        "match_rating": match_rating(p, c, today),
        "bonus": parts, "bonus_pct": sum(parts.values()),
        "coach": {"active": coach_active(p), "until": p.coach_until.isoformat() if coach_active(p) else None,
                  "stars": int(c["coach_stars"]), "days": int(c["coach_days"]), "pct": int(c["coach_xp_pct"])},
        "scout": {"stars": int(c["scout_stars"]), "revealed": p.potential_revealed},
        "mentor": None if mentor is None else {"card_id": mentor.id, "name": mentor.player.display_name,
                                               "rating": mentor.player.rating, "pct": int(c["mentor_xp_pct"])},
        "mentor_options": await _mentor_options(db, user.id),
        "training": _training_out(p, c, today),
        "story": story_out(current_story(p, c, today), trial_credit_open(p, c, _stats(p), today)),
        "growth": growth_out(p, c, today, await academy_level(db, user.id) if config.academy_enabled else 0),
        "position_pick": await position_pick_out(db, p, c, today),
        "position_change": None if not p.position_set else {
            "stars": int(c["position_change_stars"]),
            "options": [pos for line in LINE_POSITIONS.values() for pos in line if pos != p.position.value],
        },
        "rival": rival_of(p, c, today),
        "cohort": await cohort(db, p, c, today),
        "shop": _shop_out(p, c, today),
        **life,
        **await prospect_life.prospect_extras(db, user, p, c, today),
    }


# --- writes ------------------------------------------------------------------

def _clean_number(number: int) -> int:
    return my_player_service.clean_number(number)


def _clean_foot(foot: str) -> str:
    if foot not in ("right", "left"):
        raise ConflictError("Рабочая нога: right или left")
    return foot


async def create(db: AsyncSession, user: User, name: str, number: int, position: Optional[str], foot: str,
                 appearance: dict) -> dict:
    """`position` is ignored: he is universal until the coach's offer."""
    config = await get_config(db)
    c = cfg(config)
    _require_enabled(c)
    await lock_user_for_update(db, user.id)
    if await get_prospect(db, user.id) is not None:
        raise ConflictError("Воспитанник у тебя уже есть")
    rnd = random.SystemRandom()
    today = local_today()
    # «Династия»: every earlier child of this user (graduated or retired).
    generation = 1 + len((await db.execute(
        select(AcademyProspect.id).where(AcademyProspect.user_id == user.id)
    )).scalars().all())
    potential = roll_potential(c, rnd)
    if generation == 1:
        # Nobody starts the game with a hopeless first child.
        potential = max(potential, min(5, int(c["first_min_potential"])))
    p = AcademyProspect(
        user_id=user.id, generation=generation, name=my_player_service.clean_name(name), number=_clean_number(number),
        position=UNIVERSAL_POSITION, position_set=False, foot=_clean_foot(foot),
        appearance=my_player_service.clean_appearance(appearance), potential=potential,
        rival_seed=rnd.randrange(1, 2**31 - 1), cosmetics={"owned": ["bg_yard"], "background": "bg_yard"},
        memories=[{"day": today.isoformat(), "code": "born", "text": f"⚽ Первый мяч в {int(c['start_age'])} лет"
                   + (f" · {generation}-е поколение династии" if generation > 1 else "")}],
        stats={"matches": 0, "goals": 0, "wins": 0, "trainings": 0, "stories": []},
    )
    await refresh_academy_peak(db, p, config, c)
    db.add(p)
    await db.commit()
    return await get_view(db, user)


async def update(db: AsyncSession, user: User, name: Optional[str], number: Optional[int], position: Optional[str],
                 foot: Optional[str], appearance: Optional[dict]) -> dict:
    """Name, number, foot and appearance any time. The position is the
    coach's offer (`choose_position`) or a Stars change, never free here."""
    c = cfg(await get_config(db))
    _require_enabled(c)
    p = await _locked(db, user.id)
    if name is not None:
        p.name = my_player_service.clean_name(name)
    if number is not None:
        p.number = _clean_number(number)
    if foot is not None:
        p.foot = _clean_foot(foot)
    if appearance is not None:
        p.appearance = my_player_service.clean_appearance(appearance)
    if position is not None and p.position_set and my_player_service._position(position) != p.position:
        raise ConflictError(f"Сменить позицию можно за {int(c['position_change_stars'])} ⭐")
    db.add(p)
    await db.commit()
    return await get_view(db, await db.get(User, user.id))


async def train(db: AsyncSession, user: User, drill: str) -> dict:
    config = await get_config(db)
    c = cfg(config)
    _require_enabled(c)
    await lock_user_for_update(db, user.id)
    p = await _locked(db, user.id)
    today = local_today()
    offered = {d["code"]: d for d in drills_for(p, today)}
    if drill not in offered:
        raise ConflictError("Неизвестное упражнение")
    free = p.training_day != today
    if not free:
        if p.extra_credits <= 0:
            raise ConflictError("Сегодня тренировка уже была")
        p.extra_credits -= 1
    rnd = random.SystemRandom()
    stars, _, pct = rnd.choices(GRADES, weights=[g[1] for g in GRADES])[0]
    base = with_spec(p, c, "train_pct", int(c["training_xp"])) * pct // 100
    streak_bonus = 0
    stats = _stats(p)
    potential_up = False
    if free:
        p.training_streak = p.training_streak + 1 if p.training_day == today - timedelta(days=1) else 1
        p.training_day = today
        if p.training_streak % max(1, int(c["streak_days"])) == 0:
            streak_bonus = int(c["streak_bonus_xp"])
            _remember(p, today, f"streak:{p.training_streak}", f"🔥 {p.training_streak} дней тренировок подряд")
        potential_up = _streak_potential(p, c, stats, today)
    bonus = await bonus_pct(db, p, config, c)
    gained = grant_xp(p, base + streak_bonus, c, today, bonus, capped=False)
    stats["trainings"] = int(stats.get("trainings", 0)) + 1
    line = offered[drill]["line"]
    stats["drills"] = {**(stats.get("drills") or {}), line: int((stats.get("drills") or {}).get(line, 0)) + 1}
    _set_stats(p, stats)
    db.add(p)
    await db.commit()
    return {"drill": offered[drill]["title"], "grade": stars, "xp": gained, "streak_bonus": streak_bonus,
            "potential_up": potential_up, "view": await get_view(db, await db.get(User, user.id))}


async def answer_story(db: AsyncSession, user: User, code: str, option: int) -> dict:
    config = await get_config(db)
    c = cfg(config)
    _require_enabled(c)
    locked = await lock_user_for_update(db, user.id)
    p = await _locked(db, user.id)
    today = local_today()
    story = current_story(p, c, today)
    if story is None or story["code"] != code:
        raise ConflictError("Эта история уже позади")
    if not 0 <= option < len(story["options"]):
        raise ConflictError("Нет такого варианта")
    choice = story["options"][option]
    cost = int(choice.get("coins", 0))
    if cost > 0:
        await debit_coins(db, locked, cost, TransactionType.prospect_purchase, f"Воспитанник: «{story['title']}»")
    won = None
    xp = int(choice["xp"])
    stats = _stats(p)
    potential_up = trial_credit = False
    if choice.get("chance") is not None:
        won = random.SystemRandom().randrange(100) < int(choice["chance"])
        if won:
            xp = int(choice.get("win_xp") or xp)
            if choice.get("trial") and trial_credit_open(p, c, stats, today):
                # Counts as a won match of the stage trial (once a stage).
                potential_up = _trial_match(p, c, stats, True, today)
                stage = str(stage_of(p, c, today))
                stats["trials"][stage] = {**stats["trials"][stage], "story": True}
                trial_credit = True
    gained = grant_xp(p, with_spec(p, c, "story_pct", xp), c, today, await bonus_pct(db, p, config, c), capped=False)
    p.story_day = today
    stats["stories"] = [*(stats.get("stories") or []), story["code"]][-len(STORIES):]
    _set_stats(p, stats)
    if won is not False:
        _remember(p, today, f"story:{story['code']}", choice["text"])
    db.add_all([p, locked])
    await db.commit()
    return {"won": won, "xp": gained, "potential_up": potential_up, "trial_credit": trial_credit, "coins_spent": cost,
            "view": await get_view(db, await db.get(User, user.id))}


async def set_mentor(db: AsyncSession, user: User, card_id: Optional[int]) -> dict:
    from app.services.path_service import is_path_card

    c = cfg(await get_config(db))
    _require_enabled(c)
    p = await _locked(db, user.id)
    if card_id is None:
        p.mentor_card_id = None
    else:
        card = (await db.execute(
            select(UserCard).options(selectinload(UserCard.player)).where(UserCard.id == card_id)
        )).scalar_one_or_none()
        if card is None or card.owner_id != user.id:
            raise NotFoundError("Карта не найдена")
        if not is_path_card(card):
            raise ConflictError("Наставником может быть только карта «Академии»")
        p.mentor_card_id = card.id
    db.add(p)
    await db.commit()
    return await get_view(db, await db.get(User, user.id))


def _give_cosmetic(p: AcademyProspect, code: str) -> None:
    cos = dict(p.cosmetics or {})
    owned = set(cos.get("owned") or []) | {"bg_yard", code}
    cos["owned"] = sorted(owned)
    p.cosmetics = cos
    flag_modified(p, "cosmetics")


async def buy_cosmetic(db: AsyncSession, user: User, code: str) -> dict:
    c = cfg(await get_config(db))
    _require_enabled(c)
    if code not in COSMETICS:
        raise NotFoundError("Нет такого предмета")
    coins = int(c["cosmetics"].get(code, {}).get("coins", 0))
    if coins <= 0:
        raise ConflictError("Этот предмет продаётся только за ⭐")
    if not season_active(c, COSMETICS[code].get("season"), local_today()):
        raise ConflictError("Сезонный предмет — сейчас не продаётся")
    locked = await lock_user_for_update(db, user.id)
    p = await _locked(db, user.id)
    if code in set((p.cosmetics or {}).get("owned") or []):
        raise ConflictError("Уже есть")
    await debit_coins(db, locked, coins, TransactionType.prospect_purchase, f"Воспитанник: {COSMETICS[code]['name']}")
    _give_cosmetic(p, code)
    db.add_all([p, locked, ProspectLedger(user_id=user.id, kind="cosmetic", code=code, coins=coins,
                                          idempotency_key=f"cos:{code}")])
    await db.commit()
    return await get_view(db, await db.get(User, user.id))


async def equip_cosmetic(db: AsyncSession, user: User, kind: str, code: Optional[str]) -> dict:
    c = cfg(await get_config(db))
    _require_enabled(c)
    if kind not in ("background", "accessory"):
        raise ConflictError("Неизвестный слот")
    p = await _locked(db, user.id)
    cos = dict(p.cosmetics or {})
    if code is not None:
        if code not in COSMETICS or COSMETICS[code]["kind"] != kind:
            raise ConflictError("Этот предмет сюда не надевается")
        if code not in set(cos.get("owned") or []) | {"bg_yard"}:
            raise ConflictError("Сначала купи предмет")
    cos[kind] = code
    p.cosmetics = cos
    flag_modified(p, "cosmetics")
    db.add(p)
    await db.commit()
    return await get_view(db, await db.get(User, user.id))


# --- Telegram Stars ----------------------------------------------------------

PREFIX = "prospect:"
_TITLES = {"training": "Доп. тренировка воспитанника", "coach": "Личный тренер", "scout": "Скаут: потенциал",
           "bday": "Подарок на день рождения"}
_ALL_POSITIONS = {pos for line in LINE_POSITIONS.values() for pos in line}


def _gift_of(purchase: str) -> Optional[tuple[str, int]]:
    """gift:<training|coach>:<user id> -> (kind, recipient)."""
    parts = purchase.split(":")
    if len(parts) == 3 and parts[0] == "gift" and parts[1] in ("training", "coach") and parts[2].isdigit():
        return parts[1], int(parts[2])
    return None


def is_birthday(p: AcademyProspect, c: dict, today: date) -> bool:
    days = age_days(p, today)
    return days > 0 and days % max(1, int(c["days_per_year"])) == 0


def _stars_price(c: dict, purchase: str) -> int:
    if purchase == "training":
        return int(c["extra_training_stars"])
    if purchase == "coach":
        return int(c["coach_stars"])
    if purchase == "scout":
        return int(c["scout_stars"])
    if purchase == "bday":
        return int(c["bday_stars"])
    gift = _gift_of(purchase)
    if gift is not None:
        return int(c["gift_training_stars"] if gift[0] == "training" else c["gift_coach_stars"])
    if purchase.startswith("cos:") and purchase[4:] in COSMETICS:
        return int(c["cosmetics"].get(purchase[4:], {}).get("stars", 0))
    if purchase.startswith("pos:") and purchase[4:] in _ALL_POSITIONS:
        return int(c["position_change_stars"])
    raise ConflictError("Неизвестная покупка")


async def _check_buyable_async(db: AsyncSession, user_id: int, c: dict, purchase: str, today: date) -> None:
    """The checks that need the database: a gift goes to a friend's
    prospect; the birthday box once a year."""
    from app.services.friend_service import friend_ids

    gift = _gift_of(purchase)
    if gift is not None:
        if gift[1] == user_id or gift[1] not in set(await friend_ids(db, user_id)):
            raise ConflictError("Подарить можно только другу")
        if await get_prospect(db, gift[1]) is None:
            raise ConflictError("У друга нет воспитанника")
        return
    p = await get_prospect(db, user_id)
    _check_buyable(p, c, purchase, today)
    if purchase == "bday":
        age = age_of(age_days(p, today), c)
        if (await db.execute(select(ProspectLedger.id).where(
            ProspectLedger.user_id == user_id, ProspectLedger.idempotency_key == f"bday:{p.id}:{age}",
        ))).scalar_one_or_none() is not None:
            raise ConflictError("Подарок на этот день рождения уже открыт")


def _check_buyable(p: Optional[AcademyProspect], c: dict, purchase: str, today: date) -> None:
    if p is None:
        raise ConflictError("Сначала создай воспитанника")
    if purchase == "bday":
        if not is_birthday(p, c, today):
            raise ConflictError("Подарок открывается в день рождения")
    elif purchase == "training":
        bought = p.extra_bought if p.extra_day == today else 0
        if bought >= int(c["extra_trainings_max"]):
            raise ConflictError("На сегодня доп. тренировок хватит")
    elif purchase == "scout":
        if p.potential_revealed:
            raise ConflictError("Потенциал уже известен")
    elif purchase.startswith("pos:"):
        if not p.position_set:
            raise ConflictError("Позицию предложит тренер на «Юношах»")
        if purchase[4:] == p.position.value:
            raise ConflictError("Он уже играет на этой позиции")
    elif purchase.startswith("cos:"):
        if purchase[4:] in set((p.cosmetics or {}).get("owned") or []):
            raise ConflictError("Уже есть")
        if not season_active(c, COSMETICS[purchase[4:]].get("season"), today):
            raise ConflictError("Сезонный предмет — сейчас не продаётся")


async def create_stars_invoice(db: AsyncSession, user: User, purchase: str) -> dict:
    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    c = cfg(await get_config(db))
    _require_enabled(c)
    stars = _stars_price(c, purchase)
    if stars <= 0:
        raise ConflictError("Это не продаётся за ⭐")
    await _check_buyable_async(db, user.id, c, purchase, local_today())
    gift = _gift_of(purchase)
    p = await get_prospect(db, gift[1] if gift else user.id)
    if gift:
        title = "Подарок другу: " + ("тренировка воспитанника" if gift[0] == "training" else "личный тренер")
    else:
        title = _TITLES.get(purchase) or (f"Смена позиции: {purchase[4:]}" if purchase.startswith("pos:")
                                          else f"Воспитанник: {COSMETICS[purchase[4:]]['name']}")
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, academy_speedup=PREFIX + purchase))
    await db.flush()
    link = await _request_telegram_invoice_link(token, title, f"{p.name}: {title.lower()}", stars)
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}


async def validate_stars_invoice(db: AsyncSession, invoice) -> tuple[bool, str]:
    c = cfg(await get_config(db))
    if not c["enabled"]:
        return False, "«Воспитанник Академии» сейчас недоступен"
    purchase = (invoice.academy_speedup or "")[len(PREFIX):]
    try:
        if _stars_price(c, purchase) != invoice.stars_amount:
            return False, "Цена изменилась — открой покупку заново"
        await _check_buyable_async(db, invoice.user_id, c, purchase, local_today())
    except ConflictError as exc:
        return False, exc.message
    return True, ""


async def deliver_stars_invoice(db: AsyncSession, user: User, invoice) -> dict:
    """Called by stars_payment_service.deliver_payment under the invoice row
    lock (idempotent there). The payment is taken, so soft limits are not
    re-checked; the caller commits."""
    purchase = (invoice.academy_speedup or "")[len(PREFIX):]
    c = cfg(await get_config(db))
    gift = _gift_of(purchase)
    if gift is not None:
        from app.services import prospect_life

        await prospect_life.deliver_gift(db, user, gift[0], gift[1], c)
        db.add(ProspectLedger(user_id=user.id, kind="stars", code=purchase[:32], stars=invoice.stars_amount,
                              idempotency_key=f"stars-{invoice.payload_token}"))
        await db.flush()
        return {"kind": "prospect", "purchase": purchase}
    p = await _locked(db, user.id)
    today = local_today()
    now = datetime.now(timezone.utc)
    if purchase == "bday":
        from app.services import prospect_life

        await prospect_life.open_bday_box(db, p, c, today)
    elif purchase == "training":
        if p.extra_day != today:
            p.extra_day = today
            p.extra_bought = 0
        p.extra_bought += 1
        p.extra_credits += 1
    elif purchase == "coach":
        start = ensure_aware(p.coach_until) if coach_active(p, now) else now
        p.coach_until = start + timedelta(days=int(c["coach_days"]))
    elif purchase == "scout":
        p.potential_revealed = True
        _remember(p, today, "scout", "🔭 Скаут оценил потенциал")
    elif purchase.startswith("pos:"):
        await _set_position(db, p, c, my_player_service._position(purchase[4:]), today, changed=True)
    elif purchase.startswith("cos:"):
        _give_cosmetic(p, purchase[4:])
    db.add_all([p, ProspectLedger(user_id=user.id, kind="stars", code=purchase[:32], stars=invoice.stars_amount,
                                  idempotency_key=f"stars-{invoice.payload_token}")])
    await db.flush()
    return {"kind": "prospect", "purchase": purchase}


# --- «Менеджер» ---------------------------------------------------------------

def card_id_for(user_id: int) -> int:
    """Stand-in card id in game engines: negative, apart from «Мой игрок»'s
    -(1_000_000 + id) and the bots'."""
    return -(2_000_000 + user_id)


def stage_of(p: AcademyProspect, c: dict, today: date) -> int:
    return stage_index(age_of(age_days(p, today), c), c)


def can_play_clubs(p: Optional[AcademyProspect], c: dict, today: Optional[date] = None) -> bool:
    if p is None or not c["enabled"]:
        return False
    if p.status == GRADUATE:
        return True
    return p.status == GROWING and stage_of(p, c, today or local_today()) >= int(c["manager_min_stage"])


def club_rating(p: AcademyProspect, c: dict, today: date) -> int:
    """A graduate's rating is frozen at graduation."""
    return p.final_rating if p.final_rating is not None else rating_of(p, c, today)


async def prospects_of(db: AsyncSession, user_ids, status: str = GROWING) -> dict[int, AcademyProspect]:
    ids = set(user_ids)
    if not ids:
        return {}
    return {p.user_id: p for p in (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id.in_(ids), AcademyProspect.status == status)
    )).scalars()}


def _rarity_for(rating: int):
    from app.models.enums import Rarity

    return Rarity.legendary if rating >= 90 else Rarity.epic if rating >= 85 else Rarity.rare if rating >= 80 else Rarity.common


async def engine_card(db: AsyncSession, user_id: int, config=None, status: str = GROWING) -> Optional[SimpleNamespace]:
    """The prospect (or the graduate) shaped like a UserCard for the
    tournament engine (the same duck type as my_player_service.engine_card):
    his rating, talents on attack / defense, the rarity by rating. None while
    he is too young for clubs."""
    config = config or await get_config(db)
    c = cfg(config)
    p = await get_prospect(db, user_id, status)
    today = local_today()
    if not can_play_clubs(p, c, today):
        return None
    rating = club_rating(p, c, today)
    attack, defense = atk_def_of(p, c, rating)
    rarity = _rarity_for(rating)
    card_id = card_id_for(user_id) - (1_000_000 if status == GRADUATE else 0)
    return SimpleNamespace(
        id=card_id, player_id=card_id, diamond_rating_bonus=0, skill_code=None, skill_level=None,
        is_locked_by_admin=False, is_locked_in_trade=False, is_my_player=True, is_prospect=True, boosts=None,
        player=SimpleNamespace(
            display_name=p.name, position=p.position, rating=rating, rarity=rarity,
            club="Выпускник" if status == GRADUATE else "Воспитанник", country="", attack_rating=attack, defense_rating=defense,
        ),
    )


async def award_manager(db: AsyncSession, user_id: int, goals: int, status: str = GROWING) -> int:
    """XP for a «Менеджер» league match he played (the caller commits). A
    graduate only counts the match — his rating is frozen."""
    config = await get_config(db)
    c = cfg(config)
    p = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == status)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if p is None or not c["enabled"]:
        return 0
    today = local_today()
    gained = 0
    if status == GROWING:
        base = with_spec(p, c, "match_pct", int(c["manager_match_xp"])) + with_spec(p, c, "goal_pct", int(c["manager_goal_xp"])) * max(0, goals)
        gained = grant_xp(p, base, c, today, await bonus_pct(db, p, config, c), capped=True)
    stats = _stats(p)
    stats["club_matches"] = int(stats.get("club_matches", 0)) + 1
    stats["club_goals"] = int(stats.get("club_goals", 0)) + max(0, goals)
    _set_stats(p, stats)
    _remember(p, today, "club_debut", "🏟️ Первый матч за клуб в «Менеджере»")
    if goals:
        _remember(p, today, "club_goal", "⚽ Первый гол за клуб в «Менеджере»")
    db.add(p)
    return gained


# --- «Ответка» ---------------------------------------------------------------

async def otvetka_entry(db: AsyncSession, user_id: int) -> SimpleNamespace:
    """The prospect as «Ответка» sees him: the age-relative rating."""
    c = cfg(await get_config(db))
    _require_enabled(c)
    p = await get_prospect(db, user_id)
    if p is None:
        raise NotFoundError("Воспитанника ещё нет")
    today = local_today()
    return SimpleNamespace(rating=match_rating(p, c, today), name=p.name, real_rating=rating_of(p, c, today))


async def award_otvetka(db: AsyncSession, user_id: int, goals: int, won: bool) -> int:
    """XP for a finished «Ответка» he played. The caller holds the session
    row lock and marks it rewarded, so this runs once; the caller commits."""
    config = await get_config(db)
    c = cfg(config)
    p = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == GROWING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if p is None or not c["enabled"]:
        return 0
    today = local_today()
    base = (with_spec(p, c, "match_pct", int(c["otvetka_match_xp"])) + with_spec(p, c, "goal_pct", int(c["otvetka_goal_xp"])) * max(0, goals)
            + (with_spec(p, c, "win_pct", int(c["otvetka_win_xp"])) if won else 0))
    gained = grant_xp(p, base, c, today, await bonus_pct(db, p, config, c), capped=True)
    stats = _stats(p)
    stats["matches"] = int(stats.get("matches", 0)) + 1
    stats["goals"] = int(stats.get("goals", 0)) + max(0, goals)
    stats["wins"] = int(stats.get("wins", 0)) + int(won)
    _trial_match(p, c, stats, won, today)
    _set_stats(p, stats)
    if goals > 0:
        _remember(p, today, "first_goal", "🥅 Первый гол в «Ответке»")
    if won:
        _remember(p, today, "first_win", "🏅 Первая победа")
    if stats["goals"] >= 50:
        _remember(p, today, "goals50", "⚽ 50 голов")
    db.add(p)
    return gained
