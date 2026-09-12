import random
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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
    FutDraftPendingMomentOut,
    FutDraftRoundOut,
    FutDraftSlotOut,
    FutDraftStartOut,
    FutDraftStateOut,
)
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot, calculate_base_strength, split_strength
from app.services.match_service import (
    BOT_NAMES,
    _advance,
    _category_avg,
    _generate_moment_queue,
    _is_interactive,
    _resolve_action,
    _synthesize_bot_ratings,
    _with_jitter,
)
from app.services.penalty_service import PENALTY_ZONES, _resolve_shot, player_miss_chance
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

# Rounds 1-2 are an easy warm-up, rounds 3-4 step up to a standard bot —
# deliberately no "hard" tier: a full run should be winnable often enough to
# actually see the later rounds, not a fast, frequent wipe-out.
_ROUND_DIFFICULTY = [MatchDifficulty.easy, MatchDifficulty.easy, MatchDifficulty.medium, MatchDifficulty.medium]

TACTICO_PHASES = 4
TACTIC_CHOICES = ["Играть через центр", "Играть флангами", "Прессинг с первых минут"]

PENALTY_REGULATION_KICKS = 5


async def get_public_config(db: AsyncSession) -> FutDraftConfigOut:
    config = await get_config(db)
    return FutDraftConfigOut(
        entry_cost=config.fut_draft_entry_cost,
        reward_by_wins=[
            config.fut_draft_reward_win_0, config.fut_draft_reward_win_1, config.fut_draft_reward_win_2,
            config.fut_draft_reward_win_3, config.fut_draft_reward_win_4,
        ],
    )


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


async def _eligible_pool(db: AsyncSession, rarity: Rarity, category: str, exclude_ids: set[int]) -> list[Player]:
    """(rarity, any position in this slot's category) -> (rarity, any
    position) -> (any rarity, this category) -> any active droppable player.
    Drawing from the whole CATEGORY (not just the slot's single ideal
    position) is deliberate: it's what makes a slot sometimes offer an
    off-position card from the same line (e.g. an ST for an RW slot) — the
    same fit penalty calculate_base_strength already applies to an
    off-position pick, so a higher-rated off-position card is a genuine
    trade-off against a lower-rated on-position one, not a strictly better
    or worse choice."""
    positions = CATEGORY_POSITIONS[category]
    pool = await _query_players(db, Player.rarity == rarity, Player.position.in_(positions), exclude_ids=exclude_ids)
    if pool:
        return pool
    pool = await _query_players(db, Player.rarity == rarity, exclude_ids=exclude_ids)
    if pool:
        return pool
    pool = await _query_players(db, Player.position.in_(positions), exclude_ids=exclude_ids)
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
        pool = await _eligible_pool(db, rarity, slot.category, excluded)
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
            "active_round": None,
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


def _fut_draft_chemistry_bonus(config, club_counts: dict, country_counts: dict) -> int:
    """Sums the bonus across EVERY club/country group with 2+ picks, not
    just the single largest one — a squad with 3 PSG and 2 Bayern picks
    should be rewarded (and shown, see _chemistry_hints) for both groups,
    not just whichever happens to be biggest."""
    bonus = sum((count - 1) * config.fut_draft_club_bonus_per_extra for count in club_counts.values() if count >= 2)
    bonus += sum((count - 1) * config.fut_draft_country_bonus_per_extra for count in country_counts.values() if count >= 2)
    return bonus


async def _compute_team_strength(db: AsyncSession, picks: dict, slots: list[FormationSlot], config, club_counts: dict, country_counts: dict) -> int:
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
    base = calculate_base_strength(cards_with_slots)
    return base + _fut_draft_chemistry_bonus(config, club_counts, country_counts)


def _chemistry_hints(config, state: dict, players_by_id: dict[int, Player], slots_by_code: dict[str, FormationSlot]) -> list[str]:
    """Mirrors _fut_draft_chemistry_bonus exactly so the numbers shown here
    are the real contribution, not an approximation — the whole point is
    proving to the player that a "smart" pick actually helped."""
    hints: list[str] = []
    picks: dict = state["picks"]
    club_counts: dict = state["club_counts"]
    country_counts: dict = state["country_counts"]

    # Every qualifying group, not just the single biggest one — sorted by
    # count desc so the strongest synergy leads, ties broken by name for a
    # stable order across renders.
    for club, count in sorted(club_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= 2:
            hints.append(f"Одноклубники «{club}» ×{count}: +{(count - 1) * config.fut_draft_club_bonus_per_extra} к силе")
    for country, count in sorted(country_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count >= 2:
            hints.append(f"Один регион «{country}» ×{count}: +{(count - 1) * config.fut_draft_country_bonus_per_extra} к силе")
    if picks:
        exact_fit = sum(
            1 for slot_code, player_id in picks.items()
            if slot_code in slots_by_code and players_by_id[player_id].position == slots_by_code[slot_code].ideal_position
        )
        hints.append(f"На своей позиции: {exact_fit} из {len(picks)}")
    return hints


async def _state_out(
    db: AsyncSession, session: GameSession, slots: list[FormationSlot], candidates: list[Player] | None,
    config, last_pick_strength_delta: int | None = None,
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
    slots_by_code = {s.code: s for s in slots}

    return FutDraftStateOut(
        session_id=session.id, formation=state["formation"], phase=state["phase"], slots=slots_out,
        pending_slot=state["pending_slot"],
        candidates=[FutDraftCandidateOut.model_validate(c) for c in candidates] if candidates is not None else None,
        team_strength=state["team_strength"], last_pick_strength_delta=last_pick_strength_delta,
        chemistry_hints=_chemistry_hints(config, state, players_by_id, slots_by_code),
    )


async def choose_formation(db: AsyncSession, user: User, session_id: int, formation: str) -> FutDraftStateOut:
    config = await get_config(db)
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
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, None, config)


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
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, candidates, config)


async def submit_pick(db: AsyncSession, user: User, session_id: int, player_id: int) -> FutDraftStateOut:
    config = await get_config(db)
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
    new_strength = await _compute_team_strength(db, picks, slots, config, club_counts, country_counts)
    state["team_strength"] = new_strength

    if len(picks) == len(slots):
        state["phase"] = "ready"

    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()

    return await _state_out(db, session, slots, None, config, last_pick_strength_delta=new_strength - old_strength)


def _fut_draft_lineup_adapter(picks: dict, slots: list[FormationSlot], players_by_id: dict[int, Player]) -> SimpleNamespace:
    """Presents the temporary draft squad in the same shape
    app.services.match_service's moment-generation/resolution functions
    expect from a real LineupOut (`.slots[i].category`, `.slots[i].card.id`,
    `.slots[i].card.player.{rating,position,display_name,id}`) — duck-typed,
    same trick _compute_team_strength already uses to feed calculate_base_strength
    a temporary squad. Lets Card Arena rounds reuse the exact real engine
    instead of a separate one, per the spec that FUT Draft's Card Arena plays
    exactly like the real thing."""
    slots_by_code = {s.code: s for s in slots}
    adapter_slots = [
        SimpleNamespace(category=slots_by_code[slot_code].category, card=SimpleNamespace(id=player_id, player=players_by_id[player_id]))
        for slot_code, player_id in picks.items()
    ]
    return SimpleNamespace(slots=adapter_slots)


def _result_from_scores(user_score: int, opponent_score: int) -> str:
    if user_score > opponent_score:
        return "win"
    if user_score < opponent_score:
        return "loss"
    return "draw"


def _card_arena_pending_moment(active: dict) -> Optional[FutDraftPendingMomentOut]:
    """Mirrors app.models.match.Match.pending_moment exactly, read from
    FUT Draft's own active_round dict instead of a persisted Match row."""
    moments = active["moments"]
    i = active["next_index"]
    if i >= len(moments):
        return None
    moment = moments[i]
    if moment["kind"] != "shot" or not _is_interactive(moment):
        return None
    situation_kind = moment.get("situation_kind", "")
    kind = "breakaway" if situation_kind.startswith("breakaway") else situation_kind
    return FutDraftPendingMomentOut(
        seq=i, team=moment["team"], kind=kind, shot_type=moment["shot_type"],
        description=moment.get("description", ""), actions=moment.get("actions", []), actors=moment.get("actors", {}),
    )


def _card_arena_round_out(session: GameSession, active: dict, wins: int) -> FutDraftRoundOut:
    return FutDraftRoundOut(
        session_id=session.id, game_type="card_arena", round_in_progress=True,
        events=[FutDraftMatchEventOut(**e) for e in active["events"]],
        pending_moment=_card_arena_pending_moment(active),
        opponent_name=active["opponent_name"],
        user_score=active["user_score"], bot_score=active["opponent_score"],
        wins=wins, status=session.status.value,
    )


async def _start_card_arena_round(db: AsyncSession, session: GameSession, state: dict, config, team_strength: int, bot_strength: int) -> FutDraftRoundOut:
    result = await db.execute(select(Player).where(Player.id.in_(list(state["picks"].values()))))
    players_by_id = {p.id: p for p in result.scalars().all()}
    slots = get_formation_slots(state["formation"])
    lineup = _fut_draft_lineup_adapter(state["picks"], slots, players_by_id)

    user_strength = _with_jitter(team_strength)
    opponent_strength = _with_jitter(bot_strength)
    # FUT Draft squads have no tactic selector — "balanced" keeps the
    # attack/defense split neutral, same default a real lineup starts on.
    user_attack, _user_defense = split_strength(user_strength, "balanced")
    opponent_attack, _opponent_defense = split_strength(opponent_strength, "balanced")

    user_fwd, user_def, user_gk = _category_avg(lineup, "FWD"), _category_avg(lineup, "DEF"), _category_avg(lineup, "GK")
    opponent_fwd, opponent_def, opponent_gk = _synthesize_bot_ratings(user_fwd, user_def, user_gk, opponent_strength, user_strength)
    opponent_name = random.choice(BOT_NAMES)

    active = {
        "game_type": "card_arena",
        "moments": _generate_moment_queue(user_attack, opponent_attack, config, lineup, opponent_name),
        "next_index": 0,
        "user_score": 0,
        "opponent_score": 0,
        "ratings": {
            "user_fwd": user_fwd, "user_def": user_def, "user_gk": user_gk,
            "opponent_fwd": opponent_fwd, "opponent_def": opponent_def, "opponent_gk": opponent_gk,
        },
        "cards": {},
        "red_card_applied": False,
        "opponent_name": opponent_name,
        "events": [],
    }
    active["events"] = _advance(active, config, opponent_name)

    if active["next_index"] >= len(active["moments"]):
        # Rare edge case: the randomly-generated queue drew zero shot
        # chances at all — finalize immediately rather than leaving the
        # round stuck in_progress forever with nothing left to advance it.
        result_str = _result_from_scores(active["user_score"], active["opponent_score"])
        round_out = _finalize_round(session, state, config, "card_arena", result_str, active["user_score"], active["opponent_score"])
        round_out.events = [FutDraftMatchEventOut(**e) for e in active["events"]]
        round_out.opponent_name = opponent_name
        db.add(session)
        await db.commit()
        return round_out

    state["active_round"] = active
    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()
    wins = sum(1 for r in state["match_results"] if r == "win")
    return _card_arena_round_out(session, active, wins)


def _reward_for_wins(wins: int, config) -> int:
    return {
        0: config.fut_draft_reward_win_0, 1: config.fut_draft_reward_win_1, 2: config.fut_draft_reward_win_2,
        3: config.fut_draft_reward_win_3, 4: config.fut_draft_reward_win_4,
    }[wins]


def _finalize_round(session: GameSession, state: dict, config, game_type: str, result: str, user_score: int, bot_score: int) -> FutDraftRoundOut:
    """Entry point every flavor's finishing path calls once a round's
    win/draw/loss is known. A draw doesn't end the round outright — it
    hands off to a coin flip (call heads or tails; guess right and it
    counts as a win, guess wrong and it's a loss — see submit_coin_flip)
    instead of ending the series on what was really a toss-up. Any other
    result finalizes for real through _finalize_round_definitive."""
    if result == "draw":
        return _start_coin_flip(session, state, game_type, user_score, bot_score)
    return _finalize_round_definitive(session, state, config, game_type, result, user_score, bot_score)


def _start_coin_flip(session: GameSession, state: dict, source_game_type: str, user_score: int, bot_score: int) -> FutDraftRoundOut:
    active = {
        "game_type": "coin_flip", "source_game_type": source_game_type,
        "user_score": user_score, "bot_score": bot_score,
    }
    state["active_round"] = active
    session.server_state = state
    flag_modified(session, "server_state")

    wins = sum(1 for r in state["match_results"] if r == "win")
    return FutDraftRoundOut(
        session_id=session.id, game_type="coin_flip", round_in_progress=True,
        coin_flip_choices=["heads", "tails"],
        user_score=user_score, bot_score=bot_score,
        wins=wins, status=session.status.value,
    )


def _finalize_round_definitive(session: GameSession, state: dict, config, game_type: str, result: str, user_score: int, bot_score: int) -> FutDraftRoundOut:
    """Shared tail for every flavor (including a coin flip's own outcome)
    once a round's real win/loss is known: records it, advances (or ends)
    the 4-match series, and computes the reward the same way regardless of
    which game — or coin flip — decided this round."""
    match_results = list(state["match_results"]) + [result]
    state["match_results"] = match_results
    state["match_round"] = state["match_round"] + 1
    state["active_round"] = None

    wins = sum(1 for r in match_results if r == "win")
    is_finished = result != "win" or state["match_round"] >= MAX_MATCHES

    if is_finished:
        session.status = GameSessionStatus.won if wins == MAX_MATCHES else GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = _reward_for_wins(wins, config)

    session.server_state = state
    flag_modified(session, "server_state")

    return FutDraftRoundOut(
        session_id=session.id, game_type=game_type, round_in_progress=False,
        events=[], user_score=user_score, bot_score=bot_score,
        round_number=state["match_round"], result=result, wins=wins,
        is_finished=is_finished, status=session.status.value,
    )


def _round_bot_boost(config, match_round: int) -> float:
    """Bots get progressively tougher across the MAX_MATCHES-match series —
    linearly ramped from no boost in match 1 up to
    `fut_draft_round_bot_boost_pct` in the final match — on top of the
    round's own easy/medium difficulty multiplier. Without this, a very
    strong squad faces the same relative difficulty in every round and wins
    the whole series far too often."""
    if MAX_MATCHES <= 1:
        return 1.0
    return 1 + (float(config.fut_draft_round_bot_boost_pct) / 100) * (match_round / (MAX_MATCHES - 1))


async def submit_coin_flip(db: AsyncSession, user: User, session_id: int, choice: str) -> FutDraftRoundOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    active = state.get("active_round")
    if not active or active["game_type"] != "coin_flip":
        raise ConflictError("No coin flip is currently pending")
    if choice not in ("heads", "tails"):
        raise ConflictError("Unknown coin flip choice")

    landed = random.choice(["heads", "tails"])
    result = "win" if choice == landed else "loss"
    round_out = _finalize_round_definitive(
        session, state, config, active["source_game_type"], result, active["user_score"], active["bot_score"],
    )
    round_out.coin_flip_result = landed
    db.add(session)
    await db.commit()
    return round_out


async def start_match(db: AsyncSession, user: User, session_id: int) -> FutDraftRoundOut:
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

    difficulty = _ROUND_DIFFICULTY[match_round]
    multiplier = float({
        MatchDifficulty.easy: config.difficulty_easy_multiplier,
        MatchDifficulty.medium: config.difficulty_medium_multiplier,
        MatchDifficulty.hard: config.difficulty_hard_multiplier,
    }[difficulty])
    team_strength = state["team_strength"]
    bot_strength = max(1, round(team_strength * multiplier * _round_bot_boost(config, match_round)))

    # Every round is Card Arena for now, played out with the exact same
    # engine as the real Card Arena (app.services.match_service) — see
    # _start_card_arena_round. Тактико/Пенальти keep their own turn-based
    # implementations below, unreachable from this selection for now but
    # left in place in case round-type variety comes back later.
    game_type = "card_arena"

    if game_type == "card_arena":
        return await _start_card_arena_round(db, session, state, config, team_strength, bot_strength)

    if game_type == "tactico":
        state["active_round"] = {
            "game_type": "tactico", "bot_strength": bot_strength, "phase": 0,
            "user_score": 0, "bot_score": 0,
        }
        session.server_state = state
        flag_modified(session, "server_state")
        db.add(session)
        await db.commit()
        wins = sum(1 for r in state["match_results"] if r == "win")
        return FutDraftRoundOut(
            session_id=session.id, game_type="tactico", round_in_progress=True,
            phase=1, total_phases=TACTICO_PHASES, tactic_choices=TACTIC_CHOICES,
            user_score=0, bot_score=0, wins=wins, status=session.status.value,
        )

    # penalty
    player_id = random.choice(list(state["picks"].values())) if state["picks"] else None
    player = await db.get(Player, player_id) if player_id else None
    miss_chance = player_miss_chance(player.rating) if player else 0.15
    state["active_round"] = {
        "game_type": "penalty", "miss_chance": miss_chance, "bot_miss_chance": float(config.penalty_bot_miss_chance),
        "kick_number": 0, "user_score": 0, "bot_score": 0,
    }
    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()
    wins = sum(1 for r in state["match_results"] if r == "win")
    return FutDraftRoundOut(
        session_id=session.id, game_type="penalty", round_in_progress=True,
        kick_number=1, picked_player=FutDraftCandidateOut.model_validate(player) if player else None,
        zone_choices=list(PENALTY_ZONES), user_score=0, bot_score=0, wins=wins, status=session.status.value,
    )


async def submit_tactico_phase(db: AsyncSession, user: User, session_id: int, choice: str) -> FutDraftRoundOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    active = state.get("active_round")
    if not active or active["game_type"] != "tactico":
        raise ConflictError("No Тактико round is currently in progress")
    if choice not in TACTIC_CHOICES:
        raise ConflictError("Unknown tactical choice")

    team_strength = state["team_strength"]
    bot_strength = active["bot_strength"]
    win_prob = team_strength / (team_strength + bot_strength)

    if random.random() < win_prob:
        active["user_score"] += 1
        last_phase_result = f"«{choice}» сработало — гол!"
    elif random.random() < (bot_strength / (team_strength + bot_strength)) * 0.6:
        active["bot_score"] += 1
        last_phase_result = "Соперник наказал за потерю — гол соперника"
    else:
        last_phase_result = f"«{choice}» не принесло гола, но оборона выстояла"

    active["phase"] += 1
    round_in_progress = active["phase"] < TACTICO_PHASES

    if not round_in_progress:
        result = "win" if active["user_score"] > active["bot_score"] else "loss" if active["user_score"] < active["bot_score"] else "draw"
        round_out = _finalize_round(session, state, config, "tactico", result, active["user_score"], active["bot_score"])
        round_out.last_phase_result = last_phase_result
        db.add(session)
        await db.commit()
        return round_out

    state["active_round"] = active
    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()
    wins = sum(1 for r in state["match_results"] if r == "win")
    return FutDraftRoundOut(
        session_id=session.id, game_type="tactico", round_in_progress=True,
        phase=active["phase"] + 1, total_phases=TACTICO_PHASES, tactic_choices=TACTIC_CHOICES,
        last_phase_result=last_phase_result, user_score=active["user_score"], bot_score=active["bot_score"],
        wins=wins, status=session.status.value,
    )


async def submit_penalty_kick(db: AsyncSession, user: User, session_id: int, direction: str) -> FutDraftRoundOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    active = state.get("active_round")
    if not active or active["game_type"] != "penalty":
        raise ConflictError("No Пенальти round is currently in progress")
    if direction not in PENALTY_ZONES:
        raise ConflictError("Invalid direction")

    bot_dive = random.choice(PENALTY_ZONES)
    user_outcome = _resolve_shot(active["miss_chance"], direction, bot_dive)
    scored_user = user_outcome == "goal"
    if scored_user:
        active["user_score"] += 1
        last_kick_result = "Гол! Точный удар"
    else:
        last_kick_result = "Не забил" if user_outcome == "miss" else "Вратарь соперника парирует удар"

    bot_shot_zone = random.choice(PENALTY_ZONES)
    user_dive = random.choice(PENALTY_ZONES)
    bot_outcome = _resolve_shot(active["bot_miss_chance"], bot_shot_zone, user_dive)
    scored_bot = bot_outcome == "goal"
    if scored_bot:
        active["bot_score"] += 1

    active["kick_number"] += 1
    regulation_done = active["kick_number"] >= PENALTY_REGULATION_KICKS
    tied = active["user_score"] == active["bot_score"]
    round_in_progress = not regulation_done or tied

    if not round_in_progress:
        result = "win" if active["user_score"] > active["bot_score"] else "loss"
        round_out = _finalize_round(session, state, config, "penalty", result, active["user_score"], active["bot_score"])
        round_out.last_kick_result = last_kick_result
        db.add(session)
        await db.commit()
        return round_out

    state["active_round"] = active
    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()
    wins = sum(1 for r in state["match_results"] if r == "win")
    return FutDraftRoundOut(
        session_id=session.id, game_type="penalty", round_in_progress=True,
        kick_number=active["kick_number"] + 1, zone_choices=list(PENALTY_ZONES),
        last_kick_result=last_kick_result, user_score=active["user_score"], bot_score=active["bot_score"],
        wins=wins, status=session.status.value,
    )


async def submit_card_arena_action(db: AsyncSession, user: User, session_id: int, action: str) -> FutDraftRoundOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This draft has already finished")
    state = dict(session.server_state)
    active = state.get("active_round")
    if not active or active["game_type"] != "card_arena":
        raise ConflictError("No Card Arena round is currently in progress")

    moments = active["moments"]
    i = active["next_index"]
    if i >= len(moments) or moments[i]["kind"] != "shot" or not _is_interactive(moments[i]):
        raise ConflictError("No pending action for this round")
    pending = moments[i]
    if action not in pending["actions"]:
        raise ConflictError(f"Action '{action}' is not available for this moment")

    event, scored_by = _resolve_action(pending, action, active, config, active["opponent_name"])
    if scored_by:
        active[f"{scored_by}_score"] += 1
    active["next_index"] = i + 1

    new_events = [event] + _advance(active, config, active["opponent_name"])
    active["events"] = active["events"] + new_events

    if active["next_index"] >= len(moments):
        result = _result_from_scores(active["user_score"], active["opponent_score"])
        round_out = _finalize_round(session, state, config, "card_arena", result, active["user_score"], active["opponent_score"])
        round_out.events = [FutDraftMatchEventOut(**e) for e in active["events"]]
        round_out.opponent_name = active["opponent_name"]
        db.add(session)
        await db.commit()
        return round_out

    state["active_round"] = active
    session.server_state = state
    flag_modified(session, "server_state")
    db.add(session)
    await db.commit()
    wins = sum(1 for r in state["match_results"] if r == "win")
    return _card_arena_round_out(session, active, wins)


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
