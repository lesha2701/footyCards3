"""«Поиск обменов»: «Ищу» / «Отдаю» lists and partner matching.

A player lists up to `trade_finder_max_wants` players they are looking for
and up to `trade_finder_max_gives` they are ready to give. Matching reads
live ownership, so a wish never reserves or locks a card:

- «у него есть» — players from my «Ищу» the partner owns a tradeable copy of
  (not hidden from trades by its owner);
- «ему нужно» — players from the partner's «Ищу» I can give: listed in my
  «Отдаю», or a spare copy (I own two or more tradeable copies).

Partners are players who were active in the last `trade_finder_active_days`
days, accept trades, aren't banned and pass the trade give rules (a new
account can't give anything, so suggesting it would only lead to an error).
Mutual matches come first. The offer itself still goes through
trade_service.create_offer with every usual check.

When a card lands with a new owner (create_user_card, an accepted trade),
everyone who has that player in «Ищу» gets a «нашлась карточка»
notification — at most once per wish per `trade_finder_notify_hours`, and
only if the new owner could actually trade it.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.enums import NotificationType, Rarity
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.trade import TradeWish
from app.models.user import User
from app.schemas.player import PlayerOut
from app.schemas.user import UserPublicOut
from app.services import trade_guard_service
from app.services.notification_service import notify

WANT = "want"
GIVE = "give"
KINDS = (WANT, GIVE)
MAX_MATCHES = 30
# Partners checked against the give rules (one query each) before ranking cuts.
MAX_CANDIDATES = 90


def _tradeable_card_filter():
    """SQL twin of trade_service.create_offer's per-card checks."""
    return and_(
        UserCard.is_locked_by_admin.is_(False),
        UserCard.is_locked_in_trade.is_(False),
        UserCard.is_in_lineup.is_(False),
        UserCard.is_in_tactico_squad.is_(False),
        Player.is_active.is_(True),
        or_(Player.rarity != Rarity.diamond, Player.path_talent_code.is_not(None)),
        # A valuable copy from a free source never leaves its account
        # (card_value_service) — limited cards are left to the offer check.
        or_(
            UserCard.from_free_source.is_(False),
            and_(Player.rarity.not_in([Rarity.legendary, Rarity.diamond]), Player.path_talent_code.is_(None)),
        ),
    )


def _copy_order():
    # The plainest copy first: no own «замок», no skill, fewest stars.
    return (UserCard.is_user_locked, UserCard.skill_code.is_not(None), UserCard.stars, UserCard.id)


async def _wishes(db: AsyncSession, user_id: int) -> dict[str, list[int]]:
    rows = (await db.execute(
        select(TradeWish.kind, TradeWish.player_id).where(TradeWish.user_id == user_id).order_by(TradeWish.id)
    )).all()
    out: dict[str, list[int]] = {WANT: [], GIVE: []}
    for kind, player_id in rows:
        out.setdefault(kind, []).append(player_id)
    return out


async def _players(db: AsyncSession, ids: list[int]) -> dict[int, Player]:
    if not ids:
        return {}
    return {p.id: p for p in (await db.execute(select(Player).where(Player.id.in_(ids)))).scalars().all()}


async def list_wishes(db: AsyncSession, user: User, config: GameConfig) -> dict:
    wishes = await _wishes(db, user.id)
    players = await _players(db, wishes[WANT] + wishes[GIVE])
    return {
        "wants": [PlayerOut.model_validate(players[i]) for i in wishes[WANT] if i in players],
        "gives": [PlayerOut.model_validate(players[i]) for i in wishes[GIVE] if i in players],
        "max_wants": config.trade_finder_max_wants,
        "max_gives": config.trade_finder_max_gives,
    }


async def add_wish(db: AsyncSession, user: User, kind: str, player_id: int, config: GameConfig) -> dict:
    if kind not in KINDS:
        raise NotFoundError("Unknown list")
    player = await db.get(Player, player_id)
    if player is None or not player.is_active:
        raise NotFoundError("Игрок не найден")
    if player.rarity == Rarity.diamond and player.path_talent_code is None:
        raise ConflictError("Алмазные карточки не участвуют в обменах")

    wishes = await _wishes(db, user.id)
    if player_id in wishes[kind]:
        return await list_wishes(db, user, config)
    other = GIVE if kind == WANT else WANT
    if player_id in wishes[other]:
        raise ConflictError("Эта карточка уже в другом списке — сначала убери её оттуда")
    limit = config.trade_finder_max_wants if kind == WANT else config.trade_finder_max_gives
    if len(wishes[kind]) >= limit:
        label = "«Ищу»" if kind == WANT else "«Отдаю»"
        raise ConflictError(f"В списке {label} может быть не больше {limit} карточек")
    if kind == GIVE:
        owned = (await db.execute(
            select(func.count(UserCard.id)).join(Player, Player.id == UserCard.player_id)
            .where(UserCard.owner_id == user.id, UserCard.player_id == player_id)
        )).scalar_one()
        if not owned:
            raise ConflictError("В «Отдаю» можно добавить только карточку, которая у тебя есть")

    db.add(TradeWish(user_id=user.id, player_id=player_id, kind=kind))
    await db.commit()
    return await list_wishes(db, user, config)


async def remove_wish(db: AsyncSession, user: User, kind: str, player_id: int, config: GameConfig) -> dict:
    await db.execute(delete(TradeWish).where(
        TradeWish.user_id == user.id, TradeWish.kind == kind, TradeWish.player_id == player_id,
    ))
    await db.commit()
    return await list_wishes(db, user, config)


async def _my_giveable(db: AsyncSession, user_id: int, gives: list[int]) -> dict[int, int]:
    """player_id -> my card id I'd offer: «Отдаю» players and spare copies."""
    rows = (await db.execute(
        select(UserCard.player_id, UserCard.id)
        .join(Player, Player.id == UserCard.player_id)
        .where(UserCard.owner_id == user_id, _tradeable_card_filter())
        .order_by(UserCard.player_id, *_copy_order())
    )).all()
    copies: dict[int, list[int]] = defaultdict(list)
    for player_id, card_id in rows:
        copies[player_id].append(card_id)
    give_set = set(gives)
    return {pid: ids[0] for pid, ids in copies.items() if pid in give_set or len(ids) >= 2}


async def find_matches(db: AsyncSession, user: User, config: GameConfig) -> list[dict]:
    wishes = await _wishes(db, user.id)
    my_wants = wishes[WANT]
    my_giveable = await _my_giveable(db, user.id, wishes[GIVE])
    if not my_wants and not my_giveable:
        return []

    active_since = datetime.now(timezone.utc) - timedelta(days=config.trade_finder_active_days)
    partner_ok = and_(
        User.id != user.id,
        User.is_banned.is_(False),
        User.is_trade_banned.is_(False),
        User.accept_trades.is_(True),
        User.last_seen_at.is_not(None),
        User.last_seen_at >= active_since,
    )

    # partner -> {player_id: their card id} for players I want.
    they_have: dict[int, dict[int, int]] = defaultdict(dict)
    if my_wants:
        rows = (await db.execute(
            select(UserCard.owner_id, UserCard.player_id, UserCard.id)
            .join(Player, Player.id == UserCard.player_id)
            .join(User, User.id == UserCard.owner_id)
            .where(UserCard.player_id.in_(my_wants), UserCard.hidden_from_trade.is_(False),
                   _tradeable_card_filter(), partner_ok)
            .order_by(UserCard.owner_id, UserCard.player_id, *_copy_order())
        )).all()
        for owner_id, player_id, card_id in rows:
            they_have[owner_id].setdefault(player_id, card_id)

    # partner -> players they want that I can give.
    they_want: dict[int, list[int]] = defaultdict(list)
    if my_giveable:
        rows = (await db.execute(
            select(TradeWish.user_id, TradeWish.player_id)
            .join(User, User.id == TradeWish.user_id)
            .where(TradeWish.kind == WANT, TradeWish.player_id.in_(list(my_giveable)), partner_ok)
            .order_by(TradeWish.id)
        )).all()
        for partner_id, player_id in rows:
            they_want[partner_id].append(player_id)

    # Partners' own «Отдаю» lists rank their copies higher.
    partner_ids = set(they_have) | set(they_want)
    if not partner_ids:
        return []
    marked = defaultdict(set)
    if my_wants:
        for partner_id, player_id in (await db.execute(
            select(TradeWish.user_id, TradeWish.player_id).where(
                TradeWish.kind == GIVE, TradeWish.user_id.in_(partner_ids), TradeWish.player_id.in_(my_wants),
            )
        )).all():
            marked[partner_id].add(player_id)

    def score(pid: int) -> tuple:
        has, wants = they_have.get(pid, {}), they_want.get(pid, [])
        return (bool(has) and bool(wants), len(has) + len(wants), len(marked[pid] & set(has)))

    ranked = sorted(partner_ids, key=score, reverse=True)[:MAX_CANDIDATES]
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ranked)))).scalars().all()}
    players = await _players(db, list({p for pid in ranked for p in list(they_have.get(pid, {})) + they_want.get(pid, [])}))

    matches = []
    for pid in ranked:
        partner = users.get(pid)
        if partner is None:
            continue
        # A partner who'd have to give something must be allowed to give.
        if they_have.get(pid) and await trade_guard_service.give_block_reason(db, partner, config) is not None:
            continue
        has, wants = they_have.get(pid, {}), they_want.get(pid, [])
        matches.append({
            "user": UserPublicOut.model_validate(partner),
            "mutual": bool(has) and bool(wants),
            "they_have": [
                {"card_id": card_id, "player": PlayerOut.model_validate(players[player_id]),
                 "marked_to_give": player_id in marked[pid]}
                for player_id, card_id in has.items() if player_id in players
            ],
            "they_want": [
                {"card_id": my_giveable[player_id], "player": PlayerOut.model_validate(players[player_id]),
                 "marked_to_give": player_id in set(wishes[GIVE])}
                for player_id in dict.fromkeys(wants) if player_id in players
            ],
        })
        if len(matches) >= MAX_MATCHES:
            break
    return matches


async def notify_wanted_card(db: AsyncSession, owner_id: int, player_id: int) -> int:
    """Tell players looking for `player_id` that `owner_id` now has a copy.
    Adds Notification rows only; the caller commits. Returns how many."""
    config = await db.get(GameConfig, 1)  # identity map; never creates the row
    if config is None or config.trade_finder_notify_hours <= 0:
        return 0
    now = datetime.now(timezone.utc)
    cooldown_start = now - timedelta(hours=config.trade_finder_notify_hours)
    wishes = (await db.execute(
        select(TradeWish).where(
            TradeWish.player_id == player_id, TradeWish.kind == WANT, TradeWish.user_id != owner_id,
            or_(TradeWish.notified_at.is_(None), TradeWish.notified_at < cooldown_start),
        ).order_by(TradeWish.id).limit(50)
    )).scalars().all()
    if not wishes:
        return 0
    player = await db.get(Player, player_id)
    owner = await db.get(User, owner_id)
    if player is None or owner is None or (player.rarity == Rarity.diamond and player.path_talent_code is None):
        return 0
    if owner.is_banned or owner.is_trade_banned or not owner.accept_trades:
        return 0
    if await trade_guard_service.give_block_reason(db, owner, config) is not None:
        return 0
    for wish in wishes:
        await notify(
            db, wish.user_id, NotificationType.trade_wish_available,
            "Нашлась карточка из «Ищу»",
            f"У игрока {owner.full_display_name()} появилась карточка {player.display_name}. "
            "Предложи обмен в «Поиске обменов»!",
            "user", owner_id,
        )
        wish.notified_at = now
    return len(wishes)
