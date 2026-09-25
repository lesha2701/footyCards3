from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationType, TournamentStatus
from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.services import personal_squad_service
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOTAL_ROUNDS

REMINDER_KIND = "player_tournament_reminders"


async def send_lineup_reminders(db: AsyncSession, slot_key: str | None = None) -> int:
    """Notifies every participant of an active tournament whose active squad
    can no longer field a full XI. Returns the number of users notified.
    Deduped by slot_key (see tournament_notification_service for the pattern)."""
    if slot_key is not None:
        try:
            db.add(TournamentSimulationSlotLog(kind=REMINDER_KIND, slot_key=slot_key))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return 0

    user_ids = (
        await db.execute(
            select(PlayerTournamentParticipant.user_id)
            .join(PlayerTournament, PlayerTournament.id == PlayerTournamentParticipant.tournament_id)
            .where(PlayerTournament.status == TournamentStatus.active, PlayerTournament.rounds_simulated < TOTAL_ROUNDS)
        )
    ).scalars().all()

    notified = 0
    for user_id in user_ids:
        if await personal_squad_service.is_squad_complete(db, user_id):
            continue
        await notify(
            db, user_id, NotificationType.player_tournament_reminder, "Заполни состав",
            "В твоём составе турнира не хватает игроков — следующий тур скоро!",
        )
        notified += 1
    await db.commit()
    return notified
