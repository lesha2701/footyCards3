import random

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_coach_card import ClubCoachCard
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.coach import Coach
from app.models.enums import ClubCardSource, Position
from app.models.player import Player
from app.models.tournament import Tournament, TournamentClub
from app.models.user import User
from app.schemas.club_squad import (
    ClubCardOut,
    ClubCoachCardOut,
    ClubCoachSetRequest,
    ClubLineupOut,
    ClubLineupSetRequest,
    ClubLineupSlotOut,
    ClubTacticsSetRequest,
    EquippedCoachOut,
    NextOpponentOut,
)
from app.schemas.player import PlayerOut
from app.services.club_card_service import create_club_card
from app.services.club_formation_service import CLUB_FORMATIONS, DEFAULT_FORMATION, get_formation_slots, get_slots_by_code
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES
from app.services.club_tactical_profile_service import ZONES, _playstyle_alignment, compute_profile, compute_tactical_fit
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, calculate_base_strength
from app.services.tournament_fixture_service import generate_fixtures

# app.services.club_service imports seed_starting_squad from this module at
# module load time, so a module-level `from app.services.club_service import
# _require_manager, _require_membership` here would be a circular import;
# each function below imports them locally instead — same cross-service call
# the brief specifies, just deferred until both modules have finished
# initializing.

# Bench categories seeded alongside the 11 starters — one extra card per
# category, giving every fresh club a small reserve pool from day one (per
# the design spec's "so a club is never caught with nobody to substitute").
BENCH_CATEGORIES = ["GK", "DEF", "MID", "FWD"]

# Russian zone labels for the tactical-fit hint (spec §9) — deliberately not
# shared with any frontend label file: this string is entirely server-
# generated and never round-trips through a select/enum on the client.
_ZONE_LABELS_RU: dict[str, str] = {
    "central_attack": "атака через центр",
    "wing_attack": "атака флангами",
    "midfield_control": "контроль полузащиты",
    "central_defence": "центральная защита",
    "wing_defence": "фланговая защита",
    "goalkeeping": "игра вратаря",
}

_PLAYSTYLE_FIT_HINTS: dict[str, str] = {
    "WING_PLAY": "Хорошо подходит для игры по флангам",
    "CENTRAL_PLAY": "Хорошо подходит для игры через центр",
    "POSSESSION": "Хорошо подходит для контроля мяча",
    "HIGH_PRESS": "Хорошо подходит для высокого прессинга",
    "COUNTER_ATTACK": "Хорошо подходит для контратак",
}


def _tactical_fit_hint(profile, playstyle: str) -> str:
    """One-line hint for the squad screen (spec §9): praise when the chosen
    playstyle's target zone(s) are genuinely among this squad's strongest
    (reuses club_tactical_profile_service's own _playstyle_alignment, the
    same 0-1 score compute_tactical_fit already folds in — no new zone-
    ranking logic), otherwise name the squad's single weakest zone. 0.65 is
    "target zone(s) rank in roughly the top third of the 6" — _playstyle_alignment
    returns 1.0 for a #1-ranked zone, 0.8 for #2, 0.6 for #3 (out of 6 zones,
    ranks 0-5 map to scores 1.0, 0.8, 0.6, 0.4, 0.2, 0.0)."""
    if _playstyle_alignment(profile, playstyle) >= 0.65:
        return _PLAYSTYLE_FIT_HINTS[playstyle]
    zone_values = {zone: getattr(profile, zone) for zone in ZONES}
    weakest_zone = min(zone_values, key=zone_values.get)
    return f"Слабое место: {_ZONE_LABELS_RU[weakest_zone]}"


async def _pick_weakest_active_player_id(db: AsyncSession, positions: list[Position], excluded_player_ids: set[int]) -> int:
    query = (
        select(Player.id, Player.rating)
        .where(Player.is_active.is_(True), Player.position.in_(positions))
        .order_by(Player.rating.asc())
        .limit(20)
    )
    if excluded_player_ids:
        query = query.where(Player.id.notin_(excluded_player_ids))
    rows = (await db.execute(query)).all()
    if not rows:
        # Fall back to allowing repeats if the active player pool for this
        # position is smaller than the number of slots needing it (e.g. a
        # freshly-seeded dev database) — a duplicate weak player beats no
        # player at all for a brand-new club's starting squad.
        rows = (
            await db.execute(
                select(Player.id, Player.rating)
                .where(Player.is_active.is_(True), Player.position.in_(positions))
                .order_by(Player.rating.asc())
                .limit(20)
            )
        ).all()
    lowest_rating = rows[0][1]
    lowest_rated_ids = [player_id for player_id, rating in rows if rating == lowest_rating]
    return random.choice(lowest_rated_ids)


async def seed_starting_squad(db: AsyncSession, club_id: int) -> None:
    """Mints the club's first 15 ClubCards (11 starters, placed directly
    into a fresh ClubLineup, plus 4 bench cards — one per category) using
    the lowest-rated active Player available per slot, random among ties.
    Deliberately weak by design — the club has to earn its way up via
    packs. Called once, synchronously, from club_service.create_club."""
    lineup = ClubLineup(club_id=club_id)
    db.add(lineup)
    await db.flush()

    used_player_ids: set[int] = set()

    for slot in get_formation_slots(DEFAULT_FORMATION):
        positions = list(CATEGORY_POSITIONS[slot.category])
        # Position enum members compare by value against Player.position's
        # own enum column — no str() conversion needed, matches how
        # lineup_service itself queries by these same enum members.
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        club_card = await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=club_card.id, slot_code=slot.code))

    for category in BENCH_CATEGORIES:
        positions = list(CATEGORY_POSITIONS[category])
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        # No ClubLineupCard row for bench cards — per this plan's "bench =
        # any club card not currently in the lineup" simplification, these
        # are just extra ClubCard rows the squad editor's picker surfaces.

    await db.flush()


async def _get_or_none_lineup(db: AsyncSession, club_id: int) -> ClubLineup | None:
    # populate_existing=True is required here for the same reason as
    # wallet_service.lock_user_for_update: the session's identity map may
    # already hold this same ClubLineup object from earlier in the request
    # (e.g. set_club_lineup's locked query before its delete-then-recreate),
    # and this app's session factory uses expire_on_commit=False (see
    # database.py), so a plain re-SELECT after commit would silently return
    # that stale cached object — including its now-outdated `.cards`
    # collection — instead of what this query actually just fetched.
    result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(
            joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card),
            joinedload(ClubLineup.club_coach_card).joinedload(ClubCoachCard.coach).joinedload(Coach.boosts),
        )
        .execution_options(populate_existing=True)
    )
    return result.unique().scalar_one_or_none()


def _club_card_to_out(card: ClubCard, in_lineup_ids: set[int]) -> ClubCardOut:
    return ClubCardOut(
        id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
        acquired_at=card.acquired_at, is_in_lineup=card.id in in_lineup_ids,
    )


async def list_club_cards(db: AsyncSession, user: User) -> list[ClubCardOut]:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    cards = (await db.execute(select(ClubCard).where(ClubCard.club_id == membership.club_id).order_by(ClubCard.acquired_at))).scalars().all()
    lineup = await _get_or_none_lineup(db, membership.club_id)
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()
    return [_club_card_to_out(c, in_lineup_ids) for c in cards]


async def list_club_coach_cards(db: AsyncSession, user: User) -> list[ClubCoachCardOut]:
    """GET /clubs/me/coach-cards — mirrors list_club_cards above, one per
    club-owned ClubCoachCard (a club may own several)."""
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    cards = (
        await db.execute(
            select(ClubCoachCard)
            .where(ClubCoachCard.club_id == membership.club_id)
            .order_by(ClubCoachCard.acquired_at)
            # ClubCoachCard.coach is lazy="joined" on the model, but that does
            # not cascade to Coach.boosts (a separate lazy="select" relationship)
            # — without this, serializing coach.boosts below hits MissingGreenlet.
            .options(joinedload(ClubCoachCard.coach).joinedload(Coach.boosts))
        )
    ).scalars().unique().all()
    # ClubCoachCardOut has no from_attributes config (see club_coach_pack_service.
    # _to_club_coach_card_out, the existing precedent) — construct explicitly
    # rather than model_validate(orm_object), which would reject a raw ORM instance.
    return [ClubCoachCardOut(id=c.id, serial_number=c.serial_number, coach=c.coach, acquired_at=c.acquired_at) for c in cards]


async def _lineup_to_out(db: AsyncSession, club_id: int) -> ClubLineupOut:
    lineup = await _get_or_none_lineup(db, club_id)
    formation = lineup.formation if lineup else DEFAULT_FORMATION
    mentality = lineup.mentality if lineup else "BALANCED"
    playstyle = lineup.playstyle if lineup else "CENTRAL_PLAY"
    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards} if lineup else {}
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()

    slots = []
    cards_with_slots = []
    for slot in get_formation_slots(formation):
        card = by_slot.get(slot.code)
        slots.append(
            ClubLineupSlotOut(
                slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
                card=_club_card_to_out(card, in_lineup_ids) if card else None,
            )
        )
        if card:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(get_formation_slots(formation))
    team_strength = calculate_base_strength(cards_with_slots) if is_complete else None

    config = await get_config(db)
    profile = compute_profile(cards_with_slots) if cards_with_slots else None
    tactical_fit = compute_tactical_fit(cards_with_slots, profile, mentality, playstyle, config) if profile else 0
    tactical_fit_hint = _tactical_fit_hint(profile, playstyle) if profile else "Заполни состав, чтобы увидеть подсказку"

    coach_out = None
    if lineup and lineup.club_coach_card:
        coach_out = EquippedCoachOut.model_validate(lineup.club_coach_card.coach)

    return ClubLineupOut(
        is_complete=is_complete, team_strength=team_strength, formation=formation, mentality=mentality,
        playstyle=playstyle, tactical_fit=tactical_fit, tactical_fit_hint=tactical_fit_hint, slots=slots,
        coach=coach_out,
    )


async def get_club_lineup(db: AsyncSession, user: User) -> ClubLineupOut:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    return await _lineup_to_out(db, membership.club_id)


async def set_club_lineup(db: AsyncSession, user: User, payload: ClubLineupSetRequest) -> ClubLineupOut:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    current_lineup = await _get_or_none_lineup(db, club_id)
    formation = current_lineup.formation if current_lineup else DEFAULT_FORMATION
    slots_by_code = get_slots_by_code(formation)

    slot_codes = [s.slot_code for s in payload.slots]
    if len(slot_codes) != len(set(slot_codes)):
        raise ConflictError("Один слот не может использоваться дважды")
    if any(code not in slots_by_code for code in slot_codes):
        raise ConflictError("Неизвестный слот состава")

    card_ids = [s.club_card_id for s in payload.slots]
    if len(card_ids) != len(set(card_ids)):
        raise ConflictError("Одна карточка не может занимать два слота")

    club_cards = (await db.execute(select(ClubCard).where(ClubCard.id.in_(card_ids), ClubCard.club_id == club_id))).scalars().all()
    if len(club_cards) != len(card_ids):
        raise ConflictError("Карточка не принадлежит этому клубу")
    cards_by_id = {c.id: c for c in club_cards}

    # No duplicate-player check across slots, mirroring lineup_service.set_lineup's
    # same rule for personal squads: one player instance per slot.
    player_ids = [cards_by_id[cid].player_id for cid in card_ids]
    if len(player_ids) != len(set(player_ids)):
        raise ConflictError("Один футболист не может занимать две позиции")

    for slot_in in payload.slots:
        slot = slots_by_code[slot_in.slot_code]
        card = cards_by_id[slot_in.club_card_id]
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(f"Игрок на позиции {card.player.position.value} не подходит для слота {slot.code}")

    # Lock the ClubLineup row before the delete-then-recreate below, mirroring
    # lineup_service.set_lineup's own with_for_update() — a club's captain and
    # up to 2 assistants can all submit lineup changes concurrently, so this
    # serializes overlapping submissions instead of racing on the child rows.
    #
    # with_for_update(of=ClubLineup) scopes the row lock to just the
    # `club_lineups` table: joinedload(ClubLineup.cards) is a LEFT OUTER JOIN
    # to club_lineup_cards (and ClubLineupCard.club_card is itself
    # lazy="joined", cascading further outer joins into club_cards/players/
    # card_collections), and a plain FOR UPDATE tries to lock every joined
    # table including the nullable side of those outer joins, which Postgres
    # rejects outright (FeatureNotSupportedError: FOR UPDATE cannot be
    # applied to the nullable side of an outer join). Restricting the lock to
    # club_lineups keeps the eager-loaded cards while avoiding that
    # restriction — same fix as wallet_service.lock_user_for_update.
    lineup_result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(joinedload(ClubLineup.cards))
        .with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    for lc in list(lineup.cards):
        await db.delete(lc)
    await db.flush()
    for slot_in in payload.slots:
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=slot_in.club_card_id, slot_code=slot_in.slot_code))
    try:
        await db.commit()
    except IntegrityError:
        # Observed in production as an unhandled 500 on PUT /clubs/me/lineup: the
        # with_for_update(of=ClubLineup) lock above only serializes overlapping saves once
        # each one's SELECT resolves it, but under real load (slow responses inviting a
        # repeated/double tap, or a genuinely slow backend) enough overlapping submissions can
        # still interleave around the delete-then-recreate below and collide on
        # uq_club_lineup_card_once — reproduced directly with 6 concurrent identical saves
        # against real Postgres (2 succeeded, 4 hit this exact IntegrityError). Surface a clean,
        # retriable error instead of a raw 500 — the caller's own payload is still valid against
        # the now-current state.
        await db.rollback()
        raise ConflictError("Не удалось сохранить состав — попробуй ещё раз")
    return await _lineup_to_out(db, club_id)


async def set_club_tactics(db: AsyncSession, user: User, payload: ClubTacticsSetRequest) -> ClubLineupOut:
    """PUT /clubs/me/tactics — mirrors set_club_lineup's captain/assistant-
    only gating. Changing formation reconciles existing slots (spec §3):
    ClubLineupCard rows whose slot_code doesn't exist in the new formation
    are cleared (freeing their card to the bench); slots that share a code
    across both formations (GK, DEF1, ...) keep their card."""
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    if payload.formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Неизвестная схема: {payload.formation}")
    if payload.mentality not in MENTALITIES:
        raise ConflictError(f"Неизвестный настрой: {payload.mentality}")
    if payload.playstyle not in PLAYSTYLES:
        raise ConflictError(f"Неизвестный стиль игры: {payload.playstyle}")

    lineup_result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards)).with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    new_slot_codes = set(get_slots_by_code(payload.formation).keys())
    for lc in list(lineup.cards):
        if lc.slot_code not in new_slot_codes:
            await db.delete(lc)

    lineup.formation = payload.formation
    lineup.mentality = payload.mentality
    lineup.playstyle = payload.playstyle
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id)


async def set_club_coach(db: AsyncSession, user: User, payload: ClubCoachSetRequest) -> ClubLineupOut:
    """PUT /clubs/me/coach — mirrors set_club_tactics's captain/assistant-
    only gating and row-locking. A None club_coach_card_id clears the
    equipped coach."""
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    if payload.club_coach_card_id is not None:
        card = await db.get(ClubCoachCard, payload.club_coach_card_id)
        if card is None or card.club_id != club_id:
            raise ConflictError("Тренер не принадлежит этому клубу")

    lineup_result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards)).with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    lineup.club_coach_card_id = payload.club_coach_card_id
    db.add(lineup)
    await db.commit()
    return await _lineup_to_out(db, club_id)


async def get_next_opponent(db: AsyncSession, user: User) -> NextOpponentOut:
    """GET /clubs/tournament/next-opponent (spec §10). Never returns the
    opponent's formation/mentality/playstyle — only the 4 rolled-up numbers.
    A live snapshot of the opponent's CURRENT lineup, not a locked
    prediction — matches spec §10's explicit "can still shift between views
    if the opponent changes their squad before kickoff" behavior, since it's
    resolved fresh on every call, not cached or computed at fixture-generation
    time."""
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    active_tc = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    if active_tc is None:
        raise ConflictError("Клуб не участвует в активном турнире")

    tournament = await db.get(Tournament, active_tc.tournament_id)
    round_number = tournament.rounds_simulated + 1
    if round_number > 14:
        raise ConflictError("Турнир уже завершён")

    participants = (
        await db.execute(
            select(TournamentClub).where(TournamentClub.tournament_id == tournament.id).order_by(TournamentClub.id)
        )
    ).scalars().all()
    club_ids = [p.club_id for p in participants]
    pairing = next(
        (f for f in generate_fixtures(club_ids) if f[0] == round_number and club_id in (f[1], f[2])), None,
    )
    if pairing is None:
        raise ConflictError("На следующий тур соперник не назначен")
    opponent_club_id = pairing[2] if pairing[1] == club_id else pairing[1]

    opponent_club = await db.get(Club, opponent_club_id)
    opponent_lineup = await _get_or_none_lineup(db, opponent_club_id)
    opponent_formation = opponent_lineup.formation if opponent_lineup else DEFAULT_FORMATION
    opponent_by_slot = {lc.slot_code: lc.club_card for lc in opponent_lineup.cards} if opponent_lineup else {}
    opponent_cards_with_slots = [
        (opponent_by_slot[slot.code], slot) for slot in get_formation_slots(opponent_formation) if slot.code in opponent_by_slot
    ]
    profile = compute_profile(opponent_cards_with_slots) if opponent_cards_with_slots else None

    return NextOpponentOut(
        round_number=round_number, opponent_club_id=opponent_club_id, opponent_club_name=opponent_club.name,
        attack=round((profile.central_attack + profile.wing_attack) / 2) if profile else 0,
        midfield=round(profile.midfield_control) if profile else 0,
        defence=round((profile.central_defence + profile.wing_defence) / 2) if profile else 0,
        goalkeeping=round(profile.goalkeeping) if profile else 0,
    )
