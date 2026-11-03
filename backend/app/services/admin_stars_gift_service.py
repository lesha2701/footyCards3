"""An admin takes any Telegram Stars product without paying — for himself or
as a gift to another player. The admin creates the invoice the normal way in
the Mini App; instead of opening Telegram's payment sheet the client calls
`free_deliver`, which runs the same pre-checkout check and the same
`deliver_payment` as a real payment, with a charge id of "admin:<token>".

The invoice's stars_amount is zeroed after delivery, so Stars revenue, the
«Проверенный аккаунт» spend, supporter rankings and antifraud never count a
free grant. No receipt row is written: there is nothing to refund.

A gift reassigns the invoice to the recipient before delivery. Only products
that aren't tied to the admin's own objects can go to someone else (not his
card's «Академия» attempt, his muse, his club's emblem or treasury, a gift
set already addressed to someone, a subscription)."""
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.pack import StarsInvoice
from app.models.user import User
from app.services import stars_payment_service
from app.services.admin_log_service import log_action

# shop_product kinds bound to the buyer's own things.
_BOUND_PRODUCTS = {"club_emblem", "club_donation", "club_stars", "muse_accessory", "club_pass", "club_pass_renewal"}


def gift_block_reason(invoice: StarsInvoice) -> Optional[str]:
    """Why this product can't be handed to another player (None = it can)."""
    if invoice.path_user_card_id is not None or invoice.academy_speedup:
        return "Это улучшение твоей карточки — подарить его нельзя"
    if invoice.gift_set_id is not None:
        return "У подарка уже есть получатель"
    if invoice.shop_product and invoice.shop_product.partition(":")[0] in _BOUND_PRODUCTS:
        return "Этот товар привязан к твоему клубу или музе — подарить его нельзя"
    return None


async def find_player(db: AsyncSession, query: str) -> User:
    """A player by internal id, Telegram id or @username."""
    q = query.strip().lstrip("@")
    if not q:
        raise NotFoundError("Укажи игрока: id, Telegram id или @username")
    cond = [func.lower(User.username) == q.lower()]
    if q.isdigit():
        cond += [User.id == int(q), User.telegram_id == int(q)]
    user = (await db.execute(select(User).where(or_(*cond)).order_by(User.id).limit(1))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Игрок не найден")
    return user


async def free_deliver(
    db: AsyncSession, admin: User, payload_token: str, recipient: Optional[str] = None, ip_address: Optional[str] = None,
) -> dict:
    invoice = (await db.execute(
        select(StarsInvoice).where(StarsInvoice.payload_token == payload_token).with_for_update()
    )).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Заказ не найден")
    if invoice.user_id != admin.id:
        raise ForbiddenError("Это не твой заказ")
    if invoice.completed_at is not None:
        raise ConflictError("Заказ уже выполнен")
    target = admin
    if recipient:
        target = await find_player(db, recipient)
        if target.id != admin.id:
            reason = gift_block_reason(invoice)
            if reason:
                raise ConflictError(reason)
            invoice.user_id = target.id
            await db.flush()
    stars = invoice.stars_amount
    ok, message = await stars_payment_service.validate_pre_checkout(db, payload_token, stars)
    if not ok:
        raise ConflictError(message)
    await stars_payment_service.deliver_payment(db, payload_token, target.telegram_id, f"admin:{payload_token}", stars)
    invoice = (await db.execute(select(StarsInvoice).where(StarsInvoice.payload_token == payload_token))).scalar_one()
    invoice.stars_amount = 0
    await log_action(
        db, admin.id, "stars_free_gift" if target.id != admin.id else "stars_free_take", "stars_invoice", invoice.id,
        new_value={"stars": stars, "recipient_id": target.id}, ip_address=ip_address,
    )
    await db.commit()
    return {"recipient_id": target.id, "recipient_name": target.first_name or target.username or str(target.id), "stars": stars}
