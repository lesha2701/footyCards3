from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import verify_internal_secret
from app.database import get_db
from app.schemas.chat_pack import ChatPackOpenIn
from app.schemas.pack import PackOpenResult
from app.schemas.stars import (
    StarsInvoiceStatusOut,
    StarsPaymentDeliverIn,
    StarsPreCheckoutValidateIn,
    StarsPreCheckoutValidateOut,
)
from app.schemas.tournament import LineupReminderResult, SimulateRoundResult
from app.services import chat_pack_service, stars_payment_service, tournament_notification_service, tournament_simulation_service

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_secret)])


@router.post("/stars-payments/pre-checkout", response_model=StarsPreCheckoutValidateOut)
async def pre_checkout(payload: StarsPreCheckoutValidateIn, db: AsyncSession = Depends(get_db)):
    ok, error_message = await stars_payment_service.validate_pre_checkout(
        db, payload.payload_token, payload.total_amount
    )
    return StarsPreCheckoutValidateOut(ok=ok, error_message=error_message or None)


@router.post("/stars-payments/deliver", response_model=StarsInvoiceStatusOut)
async def deliver(payload: StarsPaymentDeliverIn, db: AsyncSession = Depends(get_db)):
    return await stars_payment_service.deliver_payment(
        db, payload.payload_token, payload.telegram_user_id, payload.telegram_payment_charge_id, payload.total_amount
    )


@router.post("/chat-pack/open", response_model=PackOpenResult)
async def open_chat_pack(payload: ChatPackOpenIn, db: AsyncSession = Depends(get_db)):
    """Called by the bot when a user sends "вкарта" in a group chat — see
    handlers/chat_pack.py. Errors (not registered / banned / cooldown) go
    through the normal AppError -> JSON error handler; the bot distinguishes
    them by HTTP status (404 / 409 / 429)."""
    return await chat_pack_service.claim_chat_pack_for_telegram_user(
        db, payload.telegram_user_id, payload.username, payload.first_name, payload.last_name
    )


@router.post("/clubs/simulate-round", response_model=SimulateRoundResult)
async def simulate_round(db: AsyncSession = Depends(get_db)):
    """Called by an external scheduler (cron/bot job) to advance every
    active tournament by one round. See tournament_simulation_service.
    simulate_next_round for the concurrency guarantees if this ever fires
    twice close together."""
    matches = await tournament_simulation_service.simulate_next_round(db)
    return SimulateRoundResult(matches_simulated=len(matches))


@router.post("/clubs/lineup-reminders", response_model=LineupReminderResult)
async def lineup_reminders(db: AsyncSession = Depends(get_db)):
    """Called by the bot's lineup-reminder loop, ~1h before each daily
    simulation slot. See tournament_notification_service.send_lineup_reminders."""
    count = await tournament_notification_service.send_lineup_reminders(db)
    return LineupReminderResult(clubs_notified=count)
