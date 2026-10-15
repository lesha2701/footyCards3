"""«Академия» — experience, levels and stages of path cards, daily limits,
bought attempts. Talents' match effects: services/path_talent_effects.py.

Rules (numbers from GameConfig / path_* tables, docs/path-cards.md):
  * A path card is a Player with path_talent_code set (diamond rarity).
  * Experience comes only from matches that earn it: a REWARDED Card Arena
    match (not a forfeit, rewards not blocked) uses one of the card's daily
    Arena attempts (free first, then bought ones); a player-tournament match
    and a «Карьера тренера» league round each count up to their own daily
    cap per card and never use Arena attempts. Per match: participation +
    win/draw + goals + assists.
  * Level n costs path_xp_base + path_xp_step * (n - 1 + offset) experience,
    offset = how far the design's own rating already is above
    path_start_rating. Each level adds path_rating_per_level to the card's
    rating — fixed on the row when gained (UserCard.path_rating_bonus).
  * Stages (path_stages) are rating bands. Leaving a stage needs its gate
    tasks (path_stage_tasks, counted since the card entered the stage);
    until they are done experience keeps accumulating but the level stops
    at the band's top. The last stage's top is the path's ceiling.
  * Idempotency: one path_xp_events row per (card, source match) — the
    unique constraint makes a retried / concurrent award a no-op.
  * Everything travels with the card on a trade (rows keyed by user_cards.id).
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import local_today
from app.models.card import UserCard
from app.models.card_path import CardPath, PathAttemptPurchase, PathStage, PathStageTask, PathTalent, PathXpEvent
from app.models.enums import Rarity, TransactionType
from app.models.player import Player
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.path_talent_catalog import MODE_LABELS, TALENTS, describe_level, roman, values_for
from app.services.wallet_service import debit_coins, lock_user_for_update

SOURCES = ("arena", "ptour", "career")

METRICS: dict[str, str] = {
    "matches": "Сыграть матчей",
    "wins": "Выиграть матчей",
    "goals": "Забить голов",
    "assists": "Отдать голевых передач",
    "goal_contributions": "Голы + голевые передачи",
    "arena_matches": "Матчей Card Arena",
    "ptour_matches": "Матчей турнира игроков",
    "career_matches": "Туров карьеры тренера",
    "official_matches": "Матчей турнира игроков или карьеры",
}

STAGE_DEFAULTS = [(0, "Новичок", 65, 0), (1, "Перспективный", 74, 0), (2, "Основной", 84, 1), (3, "Звезда", 89, 1), (4, "Легенда", 96, 2)]
_ATTACKING = ["ST", "LW", "RW", "CAM", "LM", "RM", "CM"]
TASK_DEFAULTS = [
    (0, "matches", 30, None), (0, "wins", 12, None),
    (1, "matches", 80, None), (1, "wins", 30, None), (1, "official_matches", 10, None),
    (2, "matches", 150, None), (2, "wins", 55, None), (2, "goal_contributions", 15, _ATTACKING),
    (2, "official_matches", 25, None),
    (3, "matches", 110, None), (3, "wins", 45, None), (3, "official_matches", 20, None),
]


# --- catalog -------------------------------------------------------------------

@dataclass
class Catalog:
    stages: list[PathStage]
    tasks: dict[int, list[PathStageTask]]
    talents: dict[str, PathTalent]

    def stage(self, index: int) -> PathStage:
        return self.stages[max(0, min(index, len(self.stages) - 1))]

    @property
    def last(self) -> PathStage:
        return self.stages[-1]

    def talent_level(self, stage_index: int) -> int:
        return max((s.talent_level for s in self.stages if s.stage_index <= stage_index), default=0)


async def ensure_catalog(db: AsyncSession) -> None:
    """Seeds missing talent / stage rows (and the default gate tasks when no
    task exists at all) — the migration does the same; this keeps fresh
    test databases and a manually cleared table working."""
    from app.services.path_talent_catalog import default_level_values

    have_talents = set((await db.execute(select(PathTalent.code))).scalars().all())
    defaults = default_level_values()
    changed = False
    for order, code in enumerate(TALENTS):
        if code not in have_talents:
            db.add(PathTalent(code=code, is_enabled=True, level_values=defaults[code], sort_order=order))
            changed = True
    have_stages = set((await db.execute(select(PathStage.stage_index))).scalars().all())
    if not have_stages:
        for index, name, max_rating, talent_level in STAGE_DEFAULTS:
            db.add(PathStage(stage_index=index, name=name, max_rating=max_rating, talent_level=talent_level))
        changed = True
    if changed:
        await db.flush()
    if not have_stages and (await db.execute(select(PathStageTask.id).limit(1))).first() is None:
        for order, (stage, metric, target, positions) in enumerate(TASK_DEFAULTS):
            db.add(PathStageTask(stage_index=stage, metric=metric, target=target, positions=positions, sort_order=order))
        await db.flush()


async def load_catalog(db: AsyncSession) -> Catalog:
    await ensure_catalog(db)
    stages = list((await db.execute(select(PathStage).order_by(PathStage.stage_index))).scalars().all())
    tasks: dict[int, list[PathStageTask]] = {}
    for task in (await db.execute(
        select(PathStageTask).where(PathStageTask.is_active.is_(True)).order_by(PathStageTask.sort_order, PathStageTask.id)
    )).scalars().all():
        tasks.setdefault(task.stage_index, []).append(task)
    talents = {t.code: t for t in (await db.execute(select(PathTalent))).scalars().all()}
    return Catalog(stages=stages, tasks=tasks, talents=talents)


# --- pure helpers ----------------------------------------------------------------

def is_path_player(player) -> bool:
    return getattr(player, "path_talent_code", None) is not None


def is_path_card(card) -> bool:
    player = getattr(card, "player", None)
    return player is not None and is_path_player(player)


def is_plain_diamond(card) -> bool:
    """A diamond that takes a diamond slot in squads (path cards have their own limit)."""
    return card.player.rarity == Rarity.diamond and not is_path_card(card)


def level_offset(player_rating: int, config) -> int:
    per = max(1, int(config.path_rating_per_level))
    return max(0, (player_rating - int(config.path_start_rating)) // per)


def level_cost(level: int, offset: int, config) -> int:
    """Experience to go from level-1 to `level` (1-based)."""
    return max(1, int(config.path_xp_base) + int(config.path_xp_step) * (level - 1 + offset))


def xp_for_levels(levels: int, offset: int, config) -> int:
    return sum(level_cost(n, offset, config) for n in range(1, levels + 1))


def levels_from_xp(xp: int, offset: int, config, max_level: int) -> int:
    level, spent = 0, 0
    while level < max_level:
        cost = level_cost(level + 1, offset, config)
        if spent + cost > xp:
            break
        spent += cost
        level += 1
    return level


def max_level_for_rating(top_rating: int, player_rating: int, config) -> int:
    per = max(1, int(config.path_rating_per_level))
    return max(0, (top_rating - player_rating) // per)


def initial_stage(catalog: Catalog, rating: int) -> int:
    for stage in catalog.stages:
        if rating <= stage.max_rating:
            return stage.stage_index
    return catalog.last.stage_index


def metric_deltas(source_type: str, result: str, goals: int, assists: int) -> dict[str, int]:
    deltas = {
        "matches": 1, "wins": 1 if result == "win" else 0, "goals": goals, "assists": assists,
        "goal_contributions": goals + assists, f"{source_type}_matches": 1,
        "official_matches": 1 if source_type in ("ptour", "career") else 0,
    }
    return {k: v for k, v in deltas.items() if v}


def match_xp(config, result: str, goals: int, assists: int) -> int:
    xp = int(config.path_xp_match)
    if result == "win":
        xp += int(config.path_xp_win)
    elif result == "draw":
        xp += int(config.path_xp_draw)
    return xp + goals * int(config.path_xp_goal) + assists * int(config.path_xp_assist)


def task_applies(task: PathStageTask, position) -> bool:
    if not task.positions:
        return True
    value = position.value if hasattr(position, "value") else str(position)
    return value in task.positions


def tasks_status(catalog: Catalog, stage_index: int, counters: dict, position) -> list[dict]:
    out = []
    for task in catalog.tasks.get(stage_index, []):
        applies = task_applies(task, position)
        progress = int((counters or {}).get(task.metric, 0))
        out.append({
            "id": task.id, "metric": task.metric, "label": METRICS.get(task.metric, task.metric),
            "target": task.target, "progress": min(progress, task.target), "applies": applies,
            "done": (not applies) or progress >= task.target,
        })
    return out


def stage_tasks_done(catalog: Catalog, stage_index: int, counters: dict, position) -> bool:
    return all(t["done"] for t in tasks_status(catalog, stage_index, counters, position))


def advance(card: UserCard, path: CardPath, catalog: Catalog, config) -> dict:
    """Applies everything the card's experience and stage tasks allow:
    gains levels up to the current stage's top, moves to the next stage when
    the band is full AND its tasks are done (counters restart), repeats.
    Never lowers anything. Returns {"levels": [ratings reached], "stages": [indexes]}."""
    player = card.player
    per = max(1, int(config.path_rating_per_level))
    offset = level_offset(player.rating, config)
    ceiling_level = max_level_for_rating(catalog.last.max_rating, player.rating, config)
    by_xp = levels_from_xp(path.xp, offset, config, ceiling_level)
    gained: dict = {"levels": [], "stages": []}
    for _ in range(len(catalog.stages) + 1):
        stage = catalog.stage(card.path_stage)
        band_top = min(ceiling_level, max_level_for_rating(stage.max_rating, player.rating, config))
        target = min(by_xp, band_top)
        while card.path_level < target:
            card.path_level += 1
            card.path_rating_bonus += per
            gained["levels"].append(player.rating + card.path_rating_bonus)
        is_last = stage.stage_index >= catalog.last.stage_index
        if is_last or card.path_level < band_top:
            break
        if not stage_tasks_done(catalog, stage.stage_index, path.stage_counters, player.position):
            break
        card.path_stage = stage.stage_index + 1
        path.stage_counters = {}
        gained["stages"].append(card.path_stage)
    return gained


def _reset_day(path: CardPath, today: date) -> None:
    if path.day != today:
        path.day = today
        path.arena_used = path.career_used = path.ptour_used = 0
        path.coin_buys = path.stars_buys = 0


def _price_list(values) -> list[int]:
    return [int(v) for v in (values or [])]


# --- DB access ---------------------------------------------------------------------

async def _lock_card(db: AsyncSession, card_id: int) -> Optional[UserCard]:
    result = await db.execute(
        select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
        .with_for_update(of=UserCard).execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()


async def get_or_create_path(db: AsyncSession, card: UserCard, catalog: Catalog, lock: bool = True) -> CardPath:
    query = select(CardPath).where(CardPath.user_card_id == card.id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    path = (await db.execute(query)).scalar_one_or_none()
    if path is not None:
        return path
    try:
        async with db.begin_nested():
            path = CardPath(user_card_id=card.id, xp=0, stage_counters={}, totals={})
            db.add(path)
            if card.path_level == 0 and card.path_stage == 0:
                card.path_stage = initial_stage(catalog, card.player.rating)
            await db.flush()
    except IntegrityError:
        path = (await db.execute(query)).scalar_one()
    return path


@dataclass
class MatchEntry:
    user_card_id: int
    result: str  # win | draw | loss
    goals: int = 0
    assists: int = 0


@dataclass
class AwardResult:
    user_card_id: int
    status: str  # awarded | duplicate | no_attempts | limit | not_path
    xp: int = 0
    levels: list = field(default_factory=list)
    stages: list = field(default_factory=list)


async def award_match(
    db: AsyncSession, *, user_id: int, source_type: str, source_id: str, entries: list[MatchEntry], config=None,
) -> list[AwardResult]:
    """Grants path experience for one finished match to every path card of
    `user_id` in `entries`. The caller decides the match counts at all
    (rewarded, not a forfeit) and commits. Each card row is locked; a card
    that changed owner since kickoff is skipped."""
    config = config or await get_config(db)
    if not config.path_enabled or not entries:
        return []
    catalog = await load_catalog(db)
    today = local_today()
    results: list[AwardResult] = []
    for entry in sorted(entries, key=lambda e: e.user_card_id):  # stable lock order
        card = await _lock_card(db, entry.user_card_id)
        if card is None or card.owner_id != user_id or not is_path_card(card):
            results.append(AwardResult(entry.user_card_id, "not_path"))
            continue
        path = await get_or_create_path(db, card, catalog)
        _reset_day(path, today)
        if source_type == "arena":
            free_left = int(config.path_daily_free_arena) - path.arena_used
            if free_left <= 0 and path.bought_attempts <= 0:
                results.append(AwardResult(card.id, "no_attempts"))
                continue
            attempt = "free" if free_left > 0 else "bought"
        else:
            cap = int(config.path_daily_career if source_type == "career" else config.path_daily_ptour)
            if getattr(path, f"{source_type}_used") >= cap:
                results.append(AwardResult(card.id, "limit"))
                continue
            attempt = source_type
        xp = match_xp(config, entry.result, entry.goals, entry.assists)
        event = PathXpEvent(
            user_card_id=card.id, user_id=user_id, source_type=source_type, source_id=str(source_id), xp=xp,
            details={"result": entry.result, "goals": entry.goals, "assists": entry.assists, "attempt": attempt},
        )
        try:
            async with db.begin_nested():
                db.add(event)
                await db.flush()
        except IntegrityError:
            results.append(AwardResult(card.id, "duplicate"))
            continue
        if attempt == "free":
            path.arena_used += 1
        elif attempt == "bought":
            path.bought_attempts -= 1
        else:
            setattr(path, f"{source_type}_used", getattr(path, f"{source_type}_used") + 1)
        path.xp += xp
        deltas = metric_deltas(source_type, entry.result, entry.goals, entry.assists)
        path.stage_counters = {**(path.stage_counters or {}), **{
            k: int((path.stage_counters or {}).get(k, 0)) + v for k, v in deltas.items()
        }}
        path.totals = {**(path.totals or {}), **{k: int((path.totals or {}).get(k, 0)) + v for k, v in deltas.items()}}
        gained = advance(card, path, catalog, config)
        event.details = {**event.details, **gained}
        db.add_all([card, path, event])
        results.append(AwardResult(card.id, "awarded", xp, gained["levels"], gained["stages"]))
    await db.flush()
    return results


async def path_card_ids(db: AsyncSession, card_ids) -> set[int]:
    ids = [int(c) for c in card_ids if c is not None]
    if not ids:
        return set()
    rows = await db.execute(
        select(UserCard.id).join(Player, Player.id == UserCard.player_id)
        .where(UserCard.id.in_(ids), Player.path_talent_code.is_not(None))
    )
    return set(rows.scalars().all())


async def update_hunger_streaks(db: AsyncSession, user_id: int, in_lineup: set[int], catalog: Catalog | None = None) -> None:
    """After a finished Card Arena match: +1 for every path card of the user
    that played, and for the ones that did not — reset, or keep a share of
    the streak when their «Голод» level says so."""
    cards = (await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(joinedload(UserCard.player))
        .where(UserCard.owner_id == user_id, Player.path_talent_code.is_not(None))
    )).unique().scalars().all()
    if not cards:
        return
    catalog = catalog or await load_catalog(db)
    for card in cards:
        path = await get_or_create_path(db, card, catalog)
        if card.id in in_lineup:
            path.hunger_streak += 1
            continue
        keep = 0
        level = catalog.talent_level(card.path_stage)
        if card.player.path_talent_code == "hunger" and level:
            row = catalog.talents.get("hunger")
            keep = values_for("hunger", level, row.level_values if row else None).get("keep_on_miss_pct", 0)
        path.hunger_streak = path.hunger_streak * int(keep) // 100
        db.add(path)


# --- player-facing ---------------------------------------------------------------

async def _owned_path_card(db: AsyncSession, user: User, card_id: int, lock: bool = False) -> UserCard:
    if lock:
        card = await _lock_card(db, card_id)
    else:
        card = (await db.execute(
            select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
        )).unique().scalar_one_or_none()
    if card is None:
        raise NotFoundError("Карточка не найдена")
    if card.owner_id != user.id:
        raise ForbiddenError("Это не твоя карточка")
    if not is_path_card(card):
        raise ConflictError("Это не карточка «Академии»")
    return card


def talent_out(code: Optional[str], level: int, catalog: Catalog, config) -> Optional[dict]:
    if not code or code not in TALENTS:
        return None
    definition = TALENTS[code]
    row = catalog.talents.get(code)
    enabled = bool(row.is_enabled if row else True) and bool(config.path_enabled)
    unlock = {}
    for stage in catalog.stages:
        if stage.talent_level and stage.talent_level not in unlock:
            unlock[stage.talent_level] = stage.name
    levels = []
    for lvl in (1, 2):
        values = values_for(code, lvl, row.level_values if row else None)
        levels.append({
            "level": lvl, "label": roman(lvl), "text": describe_level(code, lvl, values),
            "unlocked": level >= lvl, "unlock_stage": unlock.get(lvl),
        })
    summary_values = values_for(code, max(1, level), row.level_values if row else None)
    return {
        "code": code, "name": definition.name, "emoji": definition.emoji,
        "summary": definition.summary.format(**summary_values), "kind": definition.kind,
        "level": level, "level_label": roman(level) if level else None, "enabled": enabled,
        "levels": levels,
        "modes": [
            {"mode": mode, "label": label, "text": definition.modes.get(mode)} for mode, label in MODE_LABELS.items()
        ],
    }


def card_path_summary(card, catalog: Catalog, config) -> Optional[dict]:
    """Small block embedded in card payloads (frame / badge / progress bar)."""
    if not is_path_card(card):
        return None
    stage = catalog.stage(card.path_stage)
    return {
        "stage": card.path_stage, "stage_name": stage.name, "level": card.path_level,
        "talent_code": card.player.path_talent_code, "talent_level": catalog.talent_level(card.path_stage),
        "is_legend": card.path_stage >= catalog.last.stage_index,
    }


async def get_state(db: AsyncSession, user: User, card_id: int) -> dict:
    config = await get_config(db)
    catalog = await load_catalog(db)
    card = await _owned_path_card(db, user, card_id)
    path = (await db.execute(select(CardPath).where(CardPath.user_card_id == card.id))).scalar_one_or_none()
    return build_state(card, path, catalog, config, await _recent_events(db, card.id))


async def _recent_events(db: AsyncSession, card_id: int) -> list[PathXpEvent]:
    return list((await db.execute(
        select(PathXpEvent).where(PathXpEvent.user_card_id == card_id).order_by(PathXpEvent.id.desc()).limit(10)
    )).scalars().all())


def build_state(card: UserCard, path: Optional[CardPath], catalog: Catalog, config, events=()) -> dict:
    player = card.player
    today = local_today()
    xp = path.xp if path else 0
    counters = (path.stage_counters if path else {}) or {}
    stage_index = card.path_stage if path or card.path_level else initial_stage(catalog, player.rating)
    offset = level_offset(player.rating, config)
    ceiling_level = max_level_for_rating(catalog.last.max_rating, player.rating, config)
    spent = xp_for_levels(card.path_level, offset, config)
    next_cost = level_cost(card.path_level + 1, offset, config) if card.path_level < ceiling_level else None
    band_top = min(ceiling_level, max_level_for_rating(catalog.stage(stage_index).max_rating, player.rating, config))
    same_day = path is not None and path.day == today
    coin_prices, stars_prices = _price_list(config.path_coin_attempt_prices), _price_list(config.path_stars_attempt_prices)
    coin_buys = path.coin_buys if same_day else 0
    stars_buys = path.stars_buys if same_day else 0
    level = catalog.talent_level(stage_index)
    stages_out = []
    min_rating = player.rating
    for stage in catalog.stages:
        stages_out.append({
            "index": stage.stage_index, "name": stage.name,
            "min_rating": min_rating, "max_rating": stage.max_rating,
            "talent_level": stage.talent_level,
            "reached": stage.stage_index < stage_index, "current": stage.stage_index == stage_index,
            "tasks": tasks_status(
                catalog, stage.stage_index,
                counters if stage.stage_index == stage_index else ({} if stage.stage_index > stage_index else None),
                player.position,
            ) if stage.stage_index >= stage_index else [
                {**t, "progress": t["target"], "done": True}
                for t in tasks_status(catalog, stage.stage_index, {}, player.position)
            ],
        })
        min_rating = stage.max_rating + 1
    return {
        "card_id": card.id, "title": config.path_title, "enabled": bool(config.path_enabled),
        "player_name": player.display_name, "position": player.position.value,
        "base_rating": player.rating, "rating": min(99, player.rating + card.path_rating_bonus),
        "ceiling": catalog.last.max_rating, "level": card.path_level, "max_level": ceiling_level,
        "xp": xp, "xp_into_level": max(0, xp - spent), "xp_for_next": next_cost,
        "blocked_by_tasks": card.path_level >= band_top and stage_index < catalog.last.stage_index
        and xp - spent >= (next_cost or 0),
        "stage": stage_index, "stage_name": catalog.stage(stage_index).name,
        "is_legend": stage_index >= catalog.last.stage_index,
        "stages": stages_out,
        "talent": talent_out(player.path_talent_code, level, catalog, config),
        "daily": {
            "arena_free_total": int(config.path_daily_free_arena),
            "arena_free_left": max(0, int(config.path_daily_free_arena) - (path.arena_used if same_day else 0)),
            "bought_attempts": path.bought_attempts if path else 0,
            "career_total": int(config.path_daily_career),
            "career_left": max(0, int(config.path_daily_career) - (path.career_used if same_day else 0)),
            "ptour_total": int(config.path_daily_ptour),
            "ptour_left": max(0, int(config.path_daily_ptour) - (path.ptour_used if same_day else 0)),
            "coin_buys_left": max(0, len(coin_prices) - coin_buys),
            "next_coin_price": coin_prices[coin_buys] if coin_buys < len(coin_prices) else None,
            "stars_buys_left": max(0, len(stars_prices) - stars_buys),
            "next_stars_price": stars_prices[stars_buys] if stars_buys < len(stars_prices) else None,
        },
        "xp_rules": {
            "match": int(config.path_xp_match), "win": int(config.path_xp_win), "draw": int(config.path_xp_draw),
            "goal": int(config.path_xp_goal), "assist": int(config.path_xp_assist),
        },
        "totals": (path.totals if path else {}) or {},
        "hunger_streak": path.hunger_streak if path else 0,
        "recent": [
            {"source_type": e.source_type, "xp": e.xp, "result": (e.details or {}).get("result"),
             "goals": (e.details or {}).get("goals", 0), "assists": (e.details or {}).get("assists", 0),
             "levels": (e.details or {}).get("levels", []), "stages": (e.details or {}).get("stages", []),
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ],
    }


async def buy_attempt_with_coins(db: AsyncSession, user: User, card_id: int, idempotency_key: Optional[str]) -> dict:
    config = await get_config(db)
    if not config.path_enabled:
        raise ConflictError("Механика «Академия» сейчас выключена")
    locked_user = await lock_user_for_update(db, user.id)
    if idempotency_key:
        replay = (await db.execute(select(PathAttemptPurchase).where(
            PathAttemptPurchase.user_id == user.id, PathAttemptPurchase.idempotency_key == idempotency_key,
        ))).scalar_one_or_none()
        if replay is not None:
            state = await get_state(db, user, replay.user_card_id or card_id)
            return {**state, "new_balance": locked_user.balance}
    catalog = await load_catalog(db)
    card = await _owned_path_card(db, locked_user, card_id, lock=True)
    path = await get_or_create_path(db, card, catalog)
    today = local_today()
    _reset_day(path, today)
    prices = _price_list(config.path_coin_attempt_prices)
    if path.coin_buys >= len(prices):
        raise ConflictError("Сегодня для этой карточки больше нельзя купить попытки за монеты",
                            details={"limit": len(prices)})
    price = prices[path.coin_buys]
    await debit_coins(
        db, locked_user, price, TransactionType.path_attempt_purchase,
        f"Попытка «{config.path_title}» для {card.player.display_name}",
        related_object_type="user_card", related_object_id=card.id,
    )
    path.coin_buys += 1
    path.bought_attempts += 1
    db.add_all([path, PathAttemptPurchase(
        user_id=user.id, user_card_id=card.id, currency="coins", price=price, purchase_day=today,
        idempotency_key=idempotency_key,
    )])
    await db.commit()
    return {**await get_state(db, user, card.id), "new_balance": locked_user.balance}


async def check_stars_purchase(db: AsyncSession, user: User, card_id: int) -> tuple[UserCard, int]:
    """Validates a Stars attempt purchase before an invoice is created;
    returns (card, price). The limit is checked again at delivery."""
    config = await get_config(db)
    if not config.path_enabled:
        raise ConflictError("Механика «Академия» сейчас выключена")
    card = await _owned_path_card(db, user, card_id)
    path = (await db.execute(select(CardPath).where(CardPath.user_card_id == card.id))).scalar_one_or_none()
    bought = path.stars_buys if path is not None and path.day == local_today() else 0
    prices = _price_list(config.path_stars_attempt_prices)
    if bought >= len(prices):
        raise ConflictError("Сегодня для этой карточки больше нельзя купить попытки за Stars",
                            details={"limit": len(prices)})
    return card, prices[bought]


async def deliver_stars_attempt(db: AsyncSession, user: User, invoice) -> dict:
    """Called by stars_payment_service.deliver_payment under the invoice row
    lock (which, with completed_at, makes delivery once-only). The attempt
    goes to the card the invoice was created for, even if the daily limit
    filled up meanwhile — the player has already paid."""
    catalog = await load_catalog(db)
    card = await _lock_card(db, invoice.path_user_card_id) if invoice.path_user_card_id else None
    if card is None:
        raise ConflictError("Карточка для попытки больше не существует")
    path = await get_or_create_path(db, card, catalog)
    today = local_today()
    _reset_day(path, today)
    path.stars_buys += 1
    path.bought_attempts += 1
    db.add_all([path, PathAttemptPurchase(
        user_id=user.id, user_card_id=card.id, currency="stars", price=invoice.stars_amount, purchase_day=today,
        idempotency_key=f"stars-{invoice.payload_token}",
    )])
    await db.flush()
    return {"kind": "path_attempt", "user_card_id": card.id, "bought_attempts": path.bought_attempts}


async def create_stars_invoice(db: AsyncSession, user: User, card_id: int) -> dict:
    """Telegram Stars invoice for one extra Card Arena attempt of this card.
    The price (by today's Stars purchases of the card) is frozen on it."""
    import secrets

    from app.models.pack import StarsInvoice
    from app.services.stars_payment_service import _request_telegram_invoice_link

    config = await get_config(db)
    card, stars = await check_stars_purchase(db, user, card_id)
    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, path_user_card_id=card.id))
    await db.flush()
    link = await _request_telegram_invoice_link(
        token, f"Попытка «{config.path_title}»", f"Ещё одна попытка опыта для {card.player.display_name}", stars,
    )
    await db.commit()
    return {"invoice_link": link, "payload_token": token, "stars_amount": stars}
