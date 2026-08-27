from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import ClubMember
from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import NotificationType, TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.services.notification_service import notify
from app.services.tournament_fixture_service import generate_fixtures


async def notify_club_members(
    db: AsyncSession, club_id: int, type_: NotificationType, title: str, body: str,
    related_object_type: str | None = None, related_object_id: int | None = None,
) -> None:
    """Notifies every member of a club — used for events that affect the
    whole club (a match played, a tournament concluded, a lineup gap),
    unlike Clubs' other notify() call sites which target one specific
    user (a role change, a kick)."""
    member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club_id))).scalars().all()
    for user_id in member_ids:
        await notify(db, user_id, type_, title, body, related_object_type, related_object_id)


async def _club_has_suspended_starter(db: AsyncSession, club_id: int) -> bool:
    """Read-only check — does NOT call resolve_match_lineup (Task 12),
    which also performs substitution and returns engine-shaped actor
    dicts neither needed nor wanted for a preview check."""
    from app.services.club_squad_service import _get_or_none_lineup

    lineup = await _get_or_none_lineup(db, club_id)
    if lineup is None:
        return False
    lineup_card_ids = {lc.club_card_id for lc in lineup.cards}
    if not lineup_card_ids:
        return False
    result = await db.execute(
        select(ClubCardAvailability.id)
        .where(ClubCardAvailability.club_card_id.in_(lineup_card_ids), ClubCardAvailability.rounds_remaining > 0)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def send_lineup_reminders(db: AsyncSession, slot_key: str | None = None) -> int:
    """For every active tournament's upcoming round, notifies every member
    of any club (on either side of a real, non-withdrawn fixture) whose
    active lineup has a still-suspended starter. Mutates nothing but the
    Notification rows it inserts (and, when slot_key is given, the dedup
    log row below). Returns the number of (club, notified) events, for the
    internal endpoint's response.

    Time-based idempotency (surviving a bot restart that resets in-memory
    scheduling state) is handled by the caller-supplied slot_key try-insert
    against TournamentSimulationSlotLog below — a duplicate slot_key raises
    IntegrityError and this function returns 0 without notifying anyone."""
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind="lineup_reminders", slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return 0

    tournaments = (
        await db.execute(
            select(Tournament).where(Tournament.status == TournamentStatus.active, Tournament.rounds_simulated < 14)
        )
    ).scalars().all()

    notified_count = 0
    for tournament in tournaments:
        round_number = tournament.rounds_simulated + 1
        participants = (
            await db.execute(
                select(TournamentClub).where(TournamentClub.tournament_id == tournament.id).order_by(TournamentClub.id)
            )
        ).scalars().all()
        club_ids = [p.club_id for p in participants]
        withdrawn_ids = {p.club_id for p in participants if p.is_withdrawn}

        fixtures = [f for f in generate_fixtures(club_ids) if f[0] == round_number]
        for _, club_a_id, club_b_id in fixtures:
            if club_a_id in withdrawn_ids or club_b_id in withdrawn_ids:
                continue
            for club_id in (club_a_id, club_b_id):
                if await _club_has_suspended_starter(db, club_id):
                    await notify_club_members(
                        db, club_id, NotificationType.club_lineup_reminder,
                        "Кто-то из состава не сыграет",
                        "В стартовом составе клуба есть игрок под дисквалификацией — проверь состав перед следующим туром турнира.",
                    )
                    notified_count += 1

    await db.commit()
    return notified_count
