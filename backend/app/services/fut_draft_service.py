import random
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.card_collection import CardCollection
from app.models.enums import GameSessionStatus, GameType, MatchDifficulty, Rarity, TransactionType
from app.models.game import GameSession
from app.models.player import Player
from app.models.user import User
from app.schemas.fut_draft import (
    FutDraftCandidateOut,
    FutDraftClaimOut,
    FutDraftConfigOut,
    FutDraftLeaderboardEntry,
    FutDraftMatchEventOut,
    FutDraftMatchResultOut,
    FutDraftSlotOut,
    FutDraftStartOut,
    FutDraftStateOut,
)
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.game_config_service import get_config
from app.services.lineup_service import FormationSlot, calculate_base_strength
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

CANDIDATES_PER_SLOT = 3
FORMATION_OPTIONS_COUNT = 3
MAX_MATCHES = 4
MIN_STRONG_OR_BETTER_SLOTS = 3
MAX_CONSECUTIVE_WEAK = 2
STRONG_OR_BETTER_TIERS = {"strong", "top", "jackpot"}

# Spec: legendary only ever appears via the jackpot tier — this is what keeps
# it feeling rare across an 11-slot draft instead of a frequent sight. Each
# tier deals CANDIDATES_PER_SLOT distinct players at these rarities.
TIER_COMPOSITIONS: dict[str, list[Rarity]] = {
    "weak": [Rarity.common, Rarity.common, Rarity.common],
    "normal": [Rarity.common, Rarity.common, Rarity.rare],
    "strong": [Rarity.common, Rarity.rare, Rarity.epic],
    "top": [Rarity.rare, Rarity.epic, Rarity.epic],
    "jackpot": [Rarity.epic, Rarity.legendary, Rarity.legendary],
}

_DIFFICULTY_SEQUENCE = [MatchDifficulty.easy, MatchDifficulty.medium, MatchDifficulty.hard, MatchDifficulty.hard]


async def get_public_config(db: AsyncSession) -> FutDraftConfigOut:
    config = await get_config(db)
    return FutDraftConfigOut(entry_cost=config.fut_draft_entry_cost)


def _formation_options() -> list[str]:
    codes = list(CLUB_FORMATIONS.keys())
    return random.sample(codes, k=min(FORMATION_OPTIONS_COUNT, len(codes)))


def _tier_weights(config) -> list[tuple[str, int]]:
    return [
        ("weak", config.fut_draft_weak_chance),
        ("normal", config.fut_draft_normal_chance),
        ("strong", config.fut_draft_strong_chance),
        ("top", config.fut_draft_top_chance),
        ("jackpot", config.fut_draft_jackpot_chance),
    ]


def _roll_tier(weights: list[tuple[str, int]], forbid_weak: bool) -> str:
    pool = [(t, w) for t, w in weights if w > 0 and not (forbid_weak and t == "weak")]
    if not pool:
        pool = [(t, w) for t, w in weights if w > 0]
    tiers, ws = zip(*pool)
    return random.choices(tiers, weights=ws, k=1)[0]


def _roll_tier_for_open_slot(config, state: dict, remaining_count: int) -> str:
    """Tiers are rolled lazily, one per slot, at the moment the player opens
    it — not precomputed — because the player picks which slot to open in
    whatever order they like (this is the whole "как в фифе" point). The two
    whole-draft guarantees (>=1 jackpot slot, >=MIN_STRONG_OR_BETTER_SLOTS
    strong-or-better slots) are enforced as pity timers keyed off how many
    slots are left to open, not off a fixed position in a sequence — this
    keeps them correct regardless of open order. The "no 3 weak in a row"
    guard applies to the player's actual reveal order (weak_streak), which
    is the only order that matters for how a run actually *feels*."""
    if remaining_count == 1 and not state["jackpot_seen"]:
        return "jackpot"

    needed_strong = max(0, MIN_STRONG_OR_BETTER_SLOTS - state["strong_or_better_count"])
    weights = _tier_weights(config)
    if needed_strong >= remaining_count:
        weights = [(t, w) for t, w in weights if t in STRONG_OR_BETTER_TIERS]

    return _roll_tier(weights, forbid_weak=state["weak_streak"] >= MAX_CONSECUTIVE_WEAK)


def _active_filter():
    return (
        Player.is_active.is_(True),
        Player.is_pack_droppable.is_(True),
        (CardCollection.is_active.is_(True)) | (Player.collection_id.is_(None)),
    )


async def _query_players(db: AsyncSession, *extra_filters, exclude_ids: set[int]) -> list[Player]:
    query = (
        select(Player)
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(*_active_filter(), *extra_filters)
    )
    if exclude_ids:
        query = query.where(Player.id.notin_(exclude_ids))
    result = await db.execute(query)
    return list(result.scalars().all())


async def _eligible_pool(db: AsyncSession, rarity: Rarity, position, exclude_ids: set[int]) -> list[Player]:
    """(rarity, position) -> (rarity, any position) -> (any rarity, position)
    -> any active droppable player. Real prod rarity/position counts are
    healthy enough that only the strictest, most specific level should ever
    miss — the cascade exists as a safety net, not the common path."""
    pool = await _query_players(db, Player.rarity == rarity, Player.position == position, exclude_ids=exclude_ids)
    if pool:
        return pool
    pool = await _query_players(db, Player.rarity == rarity, exclude_ids=exclude_ids)
    if pool:
        return pool
    pool = await _query_players(db, Player.position == position, exclude_ids=exclude_ids)
    if pool:
        return pool
    pool = await _query_players(db, exclude_ids=exclude_ids)
    if not pool:
        raise ConflictError("Not enough active players configured for this game")
    return pool


def _weighted_choice(pool: list[Player], club_counts: dict, country_counts: dict) -> Player:
    weights = []
    for p in pool:
        w = 1.0
        if club_counts.get(p.club, 0) >= 2:
            w *= 2.5
        if country_counts.get(p.country, 0) >= 2:
            w *= 1.5
        weights.append(w)
    return random.choices(pool, weights=weights, k=1)[0]


async def _deal_slot_candidates(
    db: AsyncSession, slot: FormationSlot, tier: str, club_counts: dict, country_counts: dict, already_picked_ids: set[int],
) -> list[Player]:
    excluded = set(already_picked_ids)
    dealt: list[Player] = []
    for rarity in TIER_COMPOSITIONS[tier]:
        pool = await _eligible_pool(db, rarity, slot.ideal_position, excluded)
        player = _weighted_choice(pool, club_counts, country_counts)
        dealt.append(player)
        excluded.add(player.id)
    random.shuffle(dealt)
    return dealt


async def start_draft(db: AsyncSession, user: User) -> FutDraftStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await debit_coins(
        db, locked_user, config.fut_draft_entry_cost, TransactionType.fut_draft_entry, "Вход в FUT Draft",
    )

    formation_options = _formation_options()
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.fut_draft, status=GameSessionStatus.in_progress,
        server_state={
            "phase": "choose_formation",
            "formation_options": formation_options,
            "formation": None,
            "picks": {},  # slot_code -> player_id
            "tiers": {},  # slot_code -> tier, assigned lazily as slots are opened
            "pending_slot": None,
            "pending_candidates": [],
            "club_counts": {},
            "country_counts": {},
            "weak_streak": 0,
            "jackpot_seen": False,
            "strong_or_better_count": 0,
            "team_strength": 0,
            "match_round": 0,
            "match_results": [],
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return FutDraftStartOut(
        session_id=session.id, formation_options=formation_options,
        entry_cost=config.fut_draft_entry_cost, new_balance=locked_user.balance,
    )


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.fut_draft:
        raise NotFoundError("Draft session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def _compute_team_strength(db: AsyncSession, picks: dict, slots: list[FormationSlot]) -> int:
    if not picks:
        return 0
    slots_by_code = {s.code: s for s in slots}
    player_ids = list(picks.values())
    result = await db.execute(select(Player).where(Player.id.in_(player_ids)))
    players_by_id = {p.id: p for p in result.scalars().all()}
    cards_with_slots = [
        (SimpleNamespace(player=players_by_id[player_id]), slots_by_code[slot_code])
        for slot_code, player_id in picks.items()
    ]
    return calculate_base_strength(cards_with_slots)


async def _state_out(
    db: AsyncSession, session: GameSession, slots: list[FormationSlot], candidates: list[Player] | None,
    last_pick_strength_delta: int | None = None,
) -> FutDraftStateOut:
    state = session.server_state
    picks: dict = state["picks"]
    player_ids = list(picks.values())
    players_by_id: dict[int, Player] = {}
    if player_ids:
        result = await db.execute(select(Player).where(Player.id.in_(player_ids)))
        players_by_id = {p.id: p for p in result.scalars().all()}

    slots_out = [
        FutDraftSlotOut(
            slot_code=s.code, category=s.category, ideal_position=s.ideal_position.value,
            player=FutDraftCandidateOut.model_validate(players_by_id[picks[s.code]]) if s.code in picks else None,
        )
        for s in slots
    ]

    return FutDraftStateOut(
        session_id=session.id, formation=state["formation"], phase=state["phase"], slots=slots_out,
        pending_slot=state["pending_slot"],
        candidates=[FutDraftCandidateOut.model_validate(c) for c in candidates] if candidates is not None else None,
        team_strength=state["team_strength"], last_pick_strength_delta=last_pick_strength_delta,
    )


async def choose_formation(db: AsyncSession, user: User, session_id: int, formation: str) -> FutDraftStateOut:
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    if state["phase"] != "choose_formation":
        raise ConflictError("A formation has already been chosen for this draft")
    if formation not in state["formation_options"]:
        raise ConflictError("This formation was not offered")

    slots = get_formation_slots(formation)
    state.update({"phase": "drafting", "formation": formation})
    session.server_state = state
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, None)


async def open_slot(db: AsyncSession, user: User, session_id: int, slot_code: str) -> FutDraftStateOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    if state["phase"] != "drafting":
        raise ConflictError("This draft is not currently drafting a squad")
    if state["pending_slot"] is not None:
        raise ConflictError("Pick the card offered for the currently open slot first")

    slots = get_formation_slots(state["formation"])
    slots_by_code = {s.code: s for s in slots}
    slot = slots_by_code.get(slot_code)
    if slot is None:
        raise ConflictError("Unknown slot")
    if slot_code in state["picks"]:
        raise ConflictError("This slot is already filled")

    remaining = [s.code for s in slots if s.code not in state["picks"]]
    tier = _roll_tier_for_open_slot(config, state, len(remaining))
    already_picked_ids = set(state["picks"].values())
    candidates = await _deal_slot_candidates(
        db, slot, tier, state["club_counts"], state["country_counts"], already_picked_ids,
    )

    tiers = dict(state["tiers"])
    tiers[slot_code] = tier
    state["tiers"] = tiers
    state["pending_slot"] = slot_code
    state["pending_candidates"] = [p.id for p in candidates]
    session.server_state = state
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, candidates)


async def submit_pick(db: AsyncSession, user: User, session_id: int, player_id: int) -> FutDraftStateOut:
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    if state["phase"] != "drafting" or state["pending_slot"] is None:
        raise ConflictError("No slot is currently open to pick for")
    if player_id not in state["pending_candidates"]:
        raise ConflictError("This card was not offered for this slot")

    slots = get_formation_slots(state["formation"])
    slot_code = state["pending_slot"]

    player = await db.get(Player, player_id)
    picks = dict(state["picks"])
    picks[slot_code] = player_id
    state["picks"] = picks

    club_counts = dict(state["club_counts"])
    club_counts[player.club] = club_counts.get(player.club, 0) + 1
    country_counts = dict(state["country_counts"])
    country_counts[player.country] = country_counts.get(player.country, 0) + 1
    state["club_counts"] = club_counts
    state["country_counts"] = country_counts

    tier = state["tiers"][slot_code]
    state["weak_streak"] = state["weak_streak"] + 1 if tier == "weak" else 0
    if tier == "jackpot":
        state["jackpot_seen"] = True
    if tier in STRONG_OR_BETTER_TIERS:
        state["strong_or_better_count"] = state["strong_or_better_count"] + 1

    state["pending_slot"] = None
    state["pending_candidates"] = []

    old_strength = state["team_strength"]
    new_strength = await _compute_team_strength(db, picks, slots)
    state["team_strength"] = new_strength

    if len(picks) == len(slots):
        state["phase"] = "ready"

    session.server_state = state
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, None, last_pick_strength_delta=new_strength - old_strength)


def _resolve_match(user_strength: int, bot_strength: int) -> tuple[str, int, int]:
    """A single dice roll (win probability from relative strength, plus a
    flat draw chance) instead of the interactive moment-by-moment Card Arena
    engine — deliberately simpler for a fast, repeatable arcade-style series.
    The scoreline is generated after the fact purely for display."""
    win_prob = user_strength / (user_strength + bot_strength)
    draw_chance = 0.12
    roll = random.random()
    if roll < draw_chance:
        result = "draw"
    elif roll < draw_chance + (1 - draw_chance) * win_prob:
        result = "win"
    else:
        result = "loss"

    if result == "win":
        user_score = random.randint(1, 3)
        bot_score = random.randint(0, user_score - 1)
    elif result == "loss":
        bot_score = random.randint(1, 3)
        user_score = random.randint(0, bot_score - 1)
    else:
        user_score = bot_score = random.randint(0, 2)
    return result, user_score, bot_score


async def _generate_events(db: AsyncSession, picks: dict, user_score: int, bot_score: int) -> list[FutDraftMatchEventOut]:
    """Not a real chance-by-chance simulation (see _resolve_match) — the
    final score is already decided; this only reconstructs a plausible-
    looking timeline of goals (attributed to real squad picks for the user's
    side, for flavor) plus a couple of near-misses, so the match plays out
    on screen the way Card Arena's does instead of just flashing a result."""
    scorer_pool: list[str] = []
    if user_score > 0 and picks:
        result = await db.execute(select(Player).where(Player.id.in_(list(picks.values()))))
        scorer_pool = [p.display_name for p in result.scalars().all()]

    extra_misses = random.randint(1, 3)
    total_events = user_score + bot_score + extra_misses
    minutes = sorted(random.sample(range(1, 91), k=min(90, total_events)))
    kinds = (["user_goal"] * user_score) + (["bot_goal"] * bot_score) + (["miss"] * extra_misses)
    random.shuffle(kinds)

    events: list[FutDraftMatchEventOut] = []
    for minute, kind in zip(minutes, kinds):
        if kind == "user_goal":
            scorer = random.choice(scorer_pool) if scorer_pool else "Твоя команда"
            events.append(FutDraftMatchEventOut(minute=minute, team="user", type="goal", text=f"Гол! {scorer}"))
        elif kind == "bot_goal":
            events.append(FutDraftMatchEventOut(minute=minute, team="bot", type="goal", text="Гол соперника"))
        else:
            team = random.choice(["user", "bot"])
            events.append(FutDraftMatchEventOut(minute=minute, team=team, type="miss", text="Момент не реализован"))
    return events


def _reward_for_wins(wins: int, config) -> int:
    return {
        0: config.fut_draft_reward_win_0, 1: config.fut_draft_reward_win_1, 2: config.fut_draft_reward_win_2,
        3: config.fut_draft_reward_win_3, 4: config.fut_draft_reward_win_4,
    }[wins]


async def start_match(db: AsyncSession, user: User, session_id: int) -> FutDraftMatchResultOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    if state["phase"] != "ready":
        raise ConflictError("The squad is not ready to play yet")
    match_round = state["match_round"]
    if match_round >= MAX_MATCHES:
        raise ConflictError("All matches have already been played")

    difficulty = _DIFFICULTY_SEQUENCE[match_round]
    multiplier = {
        MatchDifficulty.easy: config.difficulty_easy_multiplier,
        MatchDifficulty.medium: config.difficulty_medium_multiplier,
        MatchDifficulty.hard: config.difficulty_hard_multiplier,
    }[difficulty]

    team_strength = state["team_strength"]
    user_strength = max(1, round(team_strength * (1 + random.uniform(-0.05, 0.05))))
    bot_strength = max(1, round(team_strength * float(multiplier) * (1 + random.uniform(-0.05, 0.05))))
    result, user_score, bot_score = _resolve_match(user_strength, bot_strength)
    events = await _generate_events(db, state["picks"], user_score, bot_score)

    match_results = list(state["match_results"]) + [result]
    state["match_results"] = match_results
    state["match_round"] = match_round + 1

    wins = sum(1 for r in match_results if r == "win")
    is_finished = result != "win" or state["match_round"] >= MAX_MATCHES

    if is_finished:
        session.status = GameSessionStatus.won if wins == MAX_MATCHES else GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = _reward_for_wins(wins, config)

    session.server_state = state
    db.add(session)
    await db.commit()

    return FutDraftMatchResultOut(
        session_id=session.id, round_number=state["match_round"], user_score=user_score, bot_score=bot_score,
        result=result, events=events, wins=wins, is_finished=is_finished, status=session.status.value,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> FutDraftClaimOut:
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("This draft is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")

    reward = 0 if locked_user.game_rewards_blocked else session.reward_coins
    session.is_rewarded = True

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за FUT Draft", related_object_type="game_session", related_object_id=session.id,
        )

    team_strength = session.server_state.get("team_strength") or 0
    is_new_best = team_strength > locked_user.fut_draft_best_squad_strength
    if is_new_best:
        locked_user.fut_draft_best_squad_strength = team_strength

    db.add(locked_user)
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    wins = sum(1 for r in session.server_state.get("match_results", []) if r == "win")

    return FutDraftClaimOut(
        reward_coins=reward, new_balance=locked_user.balance, wins=wins, team_strength=team_strength,
        is_new_best=is_new_best, best_squad_strength=locked_user.fut_draft_best_squad_strength,
    )


async def leaderboard(db: AsyncSession, limit: int = 20) -> list[FutDraftLeaderboardEntry]:
    result = await db.execute(
        select(User)
        .where(User.fut_draft_best_squad_strength > 0, User.is_admin.is_(False))
        .order_by(User.fut_draft_best_squad_strength.desc())
        .limit(limit)
    )
    return [
        FutDraftLeaderboardEntry(
            user_id=u.id, display_name=u.full_display_name(), avatar_url=u.avatar_url,
            best_squad_strength=u.fut_draft_best_squad_strength,
        )
        for u in result.scalars().all()
    ]
