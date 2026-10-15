"""«Академия» in the match engines: kickoff talent decisions for Card Arena
and player tournaments, and the experience award after a match. The pure
rules are in path_talent_effects / path_service; this module only gathers
the inputs (cards, chemistry, coach, stadium, streaks) and the outputs."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card import UserCard
from app.models.card_path import CardPath
from app.models.lineup import LineupCard
from app.services import chemistry_service, path_service
from app.services.path_talent_effects import (
    TalentPlan, dynamic_bonus, dynamic_note, override_positions, plan_static, talent_snapshot, with_bonus,
)
from app.services.player_stats_service import card_rating_bonus, effective_card_stats


def _player_is_path(player) -> bool:
    return getattr(player, "path_talent_code", None) is not None


# --- Card Arena ----------------------------------------------------------------------

@dataclass
class ArenaKickoff:
    path_cards: list[int]
    plan: Optional[TalentPlan] = None
    strength_delta: int = 0
    ratings: Optional[dict] = None  # {"FWD": n, "DEF": n, "GK": n} with talents
    gk_card: Optional[int] = None

    def state(self) -> dict:
        talents = None
        if self.plan is not None and self.plan.active:
            talents = {**self.plan.snapshot(), "gk_card": self.gk_card}
        return {"path": {"cards": self.path_cards, "goals": {}, "assists": {}}, "talents": talents}


async def arena_kickoff(db: AsyncSession, lineup, *, user_strength: int, opponent_strength: int, config) -> Optional[ArenaKickoff]:
    """None when the lineup has no «Академия» card (nothing changes)."""
    from app.services.lineup_service import ARENA_FORMATION, SLOTS_BY_CODE, calculate_base_strength

    path_ids = [s.card.id for s in lineup.slots if s.card is not None and _player_is_path(s.card.player)]
    if not path_ids:
        return None
    kickoff = ArenaKickoff(path_cards=path_ids)
    if not config.path_enabled:
        return kickoff
    rows = (await db.execute(
        select(LineupCard, UserCard).join(UserCard, UserCard.id == LineupCard.user_card_id)
        .options(joinedload(UserCard.player)).where(LineupCard.lineup_id == lineup.id)
    )).unique().all()
    pairs = [(card, SLOTS_BY_CODE[lc.slot_code]) for lc, card in rows if lc.slot_code in SLOTS_BY_CODE]
    catalog = await path_service.load_catalog(db)
    talents = {c.id: snap for c, _ in pairs if (snap := talent_snapshot(c, catalog, config, "arena"))}
    if not talents:
        return kickoff
    hunger = {}
    hunger_ids = [cid for cid, snap in talents.items() if snap["code"] == "hunger"]
    if hunger_ids:
        hunger = {p.user_card_id: p.hunger_streak for p in (await db.execute(
            select(CardPath).where(CardPath.user_card_id.in_(hunger_ids))
        )).scalars().all()}
    rules = chemistry_service.active_rules(config)
    coach_country = getattr(lineup.coach, "country", None) if lineup.coach else None
    stadium_club = getattr(lineup.stadium, "club", None) if lineup.stadium else None
    plan = plan_static(
        pairs, talents, config, formation=ARENA_FORMATION,
        opponent_ratio=(opponent_strength / user_strength) if user_strength else None,
        coach_country=coach_country, stadium_club=stadium_club, hunger=hunger, chemistry_on=rules is not None,
    )
    stadium_multiplier = 1.0 + float(lineup.stadium.boost_pct) if lineup.stadium else 1.0

    def chemistry(hooks: dict | None):
        if rules is None:
            return None
        return chemistry_service.compute_chemistry(
            pairs, ARENA_FORMATION, rules, slot_count=len(SLOTS_BY_CODE),
            coach_country=chemistry_service.coach_country_of(lineup.coach),
            stadium_club=chemistry_service.stadium_club_of(lineup.stadium), **(hooks or {}),
        )

    before, after = chemistry(None), chemistry(plan.chemistry_hooks())
    old = calculate_base_strength(pairs, tactic=lineup.tactic, stadium_multiplier=stadium_multiplier, chemistry=before)
    new = calculate_base_strength(
        override_positions(pairs, plan), tactic=lineup.tactic, stadium_multiplier=stadium_multiplier, chemistry=after,
    )
    kickoff.plan = plan
    kickoff.gk_card = next((card.id for card, slot in pairs if slot.category == "GK"), None)
    kickoff.strength_delta = (new - old) + sum(plan.static.values())
    ratings: dict[str, list[int]] = {}
    for card, slot in pairs:
        rating, _, _ = effective_card_stats(card.player, card_rating_bonus(card))
        if after is not None:
            rating = chemistry_service.boosted_rating(rating, after.rating_bonus(slot.code))
        ratings.setdefault(slot.category, []).append(with_bonus(rating, plan.static.get(card.id, 0)))
    kickoff.ratings = {cat: round(sum(v) / len(v)) for cat, v in ratings.items() if v}
    return kickoff


def arena_actor_rating(state: dict, actor: dict, minute: int, role: str, notes: list, *,
                       one_on_one: bool = False, penalty: bool = False) -> int:
    """An actor's rating for one Card Arena roll: its card rating + static
    talents (kickoff) + a dynamic talent if its condition holds now. The
    note goes to the event log only when a talent of THIS card changed the
    roll."""
    talents = state.get("talents") or {}
    cid = str(actor.get("user_card_id"))
    static = int((talents.get("static") or {}).get(cid, 0))
    snap = (talents.get("cards") or {}).get(cid)
    dyn = dynamic_bonus(
        snap, minute=minute, own=state.get("user_score", 0), opp=state.get("opponent_score", 0),
        role=role, one_on_one=one_on_one, penalty=penalty,
    )
    own_static = static if snap is not None else 0
    if snap is not None and (dyn or own_static):
        notes.append(dynamic_note(snap, dyn + own_static))
    return with_bonus(actor["rating"], static + dyn)


def arena_keeper_bonus(state: dict, minute: int, notes: list, *, one_on_one: bool = False, penalty: bool = False) -> int:
    """Dynamic talent of the user's goalkeeper for a save roll (its static
    part is already inside the frozen user_gk rating)."""
    talents = state.get("talents") or {}
    gk = talents.get("gk_card")
    snap = (talents.get("cards") or {}).get(str(gk)) if gk is not None else None
    dyn = dynamic_bonus(
        snap, minute=minute, own=state.get("user_score", 0), opp=state.get("opponent_score", 0),
        role="keeper", one_on_one=one_on_one, penalty=penalty,
    )
    if dyn:
        notes.append(dynamic_note(snap, dyn))
    return dyn


def arena_track_goal(state: dict, scorer_id, assist_id=None) -> None:
    path = state.get("path")
    if not path:
        return
    cards = {str(c) for c in path.get("cards", [])}
    if scorer_id is not None and str(scorer_id) in cards:
        path["goals"][str(scorer_id)] = path["goals"].get(str(scorer_id), 0) + 1
    if assist_id is not None and str(assist_id) in cards:
        path["assists"][str(assist_id)] = path["assists"].get(str(assist_id), 0) + 1


async def arena_after_match(db: AsyncSession, user_id: int, match, state: dict, result: str, rewarded: bool, config) -> None:
    """Experience for the path cards that played (rewarded matches only) and
    «Голод» streaks. Same transaction as the match finalisation."""
    path = state.get("path")
    if path is None:
        # No path card played: streaks of the user's path cards still break.
        if config.path_enabled:
            await path_service.update_hunger_streaks(db, user_id, set())
        return
    cards = [int(c) for c in path.get("cards", [])]
    if rewarded and config.path_enabled:
        awarded = await path_service.award_match(
            db, user_id=user_id, source_type="arena", source_id=str(match.id), config=config,
            entries=[
                path_service.MatchEntry(
                    user_card_id=cid, result=result, goals=int(path["goals"].get(str(cid), 0)),
                    assists=int(path["assists"].get(str(cid), 0)),
                )
                for cid in cards
            ],
        )
        path["awarded"] = [
            {"user_card_id": a.user_card_id, "status": a.status, "xp": a.xp, "levels": a.levels, "stages": a.stages}
            for a in awarded
        ]
    if config.path_enabled:
        await path_service.update_hunger_streaks(db, user_id, set(cards))


# --- player tournaments ------------------------------------------------------------------

def ptour_plan(
    pairs: list, catalog, config, *, formation: str, opponent_avg: Optional[float], own_avg: Optional[float],
    coach_country: Optional[str], stadium_club: Optional[str], chemistry_on: bool,
) -> Optional[TalentPlan]:
    talents = {c.id: snap for c, _ in pairs if (snap := talent_snapshot(c, catalog, config, "ptour"))}
    if not talents:
        return None
    return plan_static(
        pairs, talents, config, formation=formation,
        opponent_ratio=(opponent_avg / own_avg) if opponent_avg and own_avg else None,
        coach_country=coach_country, stadium_club=stadium_club, chemistry_on=chemistry_on,
    )


def side_result(own: int, opp: int) -> str:
    return "win" if own > opp else "loss" if own < opp else "draw"


def goals_and_assists(event_log: list, side: str) -> tuple[dict, dict]:
    goals: dict[int, int] = {}
    assists: dict[int, int] = {}
    for event in event_log or []:
        if event.get("event_type") != "goal" or event.get("team") != side:
            continue
        payload = event.get("payload") or {}
        if payload.get("shooter_id") is not None:
            goals[payload["shooter_id"]] = goals.get(payload["shooter_id"], 0) + 1
        if payload.get("assist_id") is not None:
            assists[payload["assist_id"]] = assists.get(payload["assist_id"], 0) + 1
    return goals, assists


async def award_side(
    db: AsyncSession, *, user_id: int, source_type: str, source_id: str, card_ids, own: int, opp: int,
    event_log: list, side: str, config,
) -> list:
    path_ids = await path_service.path_card_ids(db, card_ids)
    if not path_ids:
        return []
    goals, assists = goals_and_assists(event_log, side)
    return await path_service.award_match(
        db, user_id=user_id, source_type=source_type, source_id=source_id, config=config,
        entries=[
            path_service.MatchEntry(user_card_id=cid, result=side_result(own, opp),
                                    goals=goals.get(cid, 0), assists=assists.get(cid, 0))
            for cid in sorted(path_ids)
        ],
    )


# --- «Карьера тренера» ---------------------------------------------------------------------

async def career_fatigue_gains(db: AsyncSession, gains: Optional[dict], cards_by_id: dict, config) -> Optional[dict]:
    """«Второе дыхание» in the career: the card builds up less fatigue in a
    match (the only talent the career models — its ratings are untouched)."""
    if not gains or not config.path_enabled:
        return gains
    candidates = [
        c for cid, c in cards_by_id.items()
        if cid in gains and path_service.talent_code_of(c) == "second_wind"
    ]
    if not candidates:
        return gains
    catalog = await path_service.load_catalog(db)
    out = dict(gains)
    for card in candidates:
        snap = talent_snapshot(card, catalog, config, "career")
        if snap is not None:
            out[card.id] = out[card.id] * (100 - int(snap["values"]["fatigue_cut_pct"])) // 100
    return out


async def career_apply_talents(db: AsyncSession, runners, cards_by_id: dict, config) -> None:
    """«Академия» talents for a «Карьера тренера» match, decided at kickoff
    once both sides exist (opponent strength for «Большие матчи»). Static
    ones go into each starter's match rating (after familiarity, fatigue and
    form); dynamic ones ride on the engine card's `talent` snapshot and are
    applied per chance by tournament_match_engine exactly as in player
    tournaments; «Универсал» / «Свой парень» shape the runner's chemistry.
    Bench players carry their dynamic talents only. No RNG is drawn."""
    if not config.path_enabled:
        return
    runners = [r for r in runners if r is not None]
    if len(runners) != 2 or not any(
        path_service.is_path_card(cards_by_id.get(p.card.id)) for r in runners for p in r.on_pitch + r.bench
        if cards_by_id.get(p.card.id) is not None
    ):
        return
    catalog = await path_service.load_catalog(db)

    def avg(runner) -> float:
        return sum(p.base_rating for p in runner.on_pitch) / len(runner.on_pitch) if runner.on_pitch else 0.0

    for runner, other in ((runners[0], runners[1]), (runners[1], runners[0])):
        talents = {}
        for p in runner.on_pitch + runner.bench:
            card = cards_by_id.get(p.card.id)
            if card is None or card.owner_id is None:
                continue
            snap = talent_snapshot(card, catalog, config, "career")
            if snap is not None:
                talents[p.card.id] = snap
        if not talents:
            continue
        own_avg, opp_avg = avg(runner), avg(other)
        pairs = [(_CareerCard(p.card, cards_by_id.get(p.card.id)), p.slot) for p in runner.on_pitch]
        plan = plan_static(
            pairs, {cid: s for cid, s in talents.items() if any(p.card.id == cid for p in runner.on_pitch)}, config,
            formation=runner.formation, opponent_ratio=(opp_avg / own_avg) if own_avg else None,
            coach_country=chemistry_service.coach_country_of(runner.coach), stadium_club=None,
            chemistry_on=runner.chem_rules is not None,
        )
        cap = max(0, int(config.path_talent_cap))
        for p in runner.on_pitch:
            p.talent_static = plan.static.get(p.card.id, 0)
            position = plan.position_override.get(p.card.id)
            if position is not None:
                p.card.player.position = position  # this match's engine copy only
        for p in runner.on_pitch + runner.bench:
            snap = plan.talents.get(p.card.id)
            if snap is None and p.card.id in talents:
                snap = {**talents[p.card.id], "static": 0, "room": cap if talents[p.card.id]["kind"] == "dynamic" else 0}
            if snap is not None:
                p.card.talent = snap
        runner.talent_hooks = plan.chemistry_hooks()
        runner.refresh_chemistry()
        runner._cache_key = None


class _CareerCard:
    """(engine card, user card) for plan_static: identity / position / club /
    country come from the engine copy, the talent from the user card."""

    def __init__(self, engine_card, user_card):
        self.id = engine_card.id
        self.player = engine_card.player
        self.player_id = getattr(engine_card, "player_id", None)
        self._user_card = user_card
