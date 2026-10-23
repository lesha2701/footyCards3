"""/paysupport and /terms — required of bots that sell digital goods for
Telegram Stars. /paysupport shows the player's recent payments with their
delivery status and forwards their description of the problem to the
admins (ADMIN_TELEGRAM_IDS)."""
import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import db
from config import get_bot_settings
from services.stars_delivery import alert_admins

router = Router(name="support")
router.message.filter(F.chat.type == "private")
settings = get_bot_settings()
logger = logging.getLogger("footycards.bot.support")

# Same documents as frontend/src/lib/legalLinks.ts.
PACK_PURCHASE_TERMS_URL = "https://telegra.ph/Usloviya-pokupki-cifrovyh-pakov--VICTOR-FC-08-12"
PRIVACY_POLICY_URL = "https://telegra.ph/Politika-obrabotki-personalnyh-dannyh--VICTOR-FC-08-12"
USER_AGREEMENT_URL = "https://telegra.ph/Polzovatelskoe-soglashenie--VICTOR-FC-10-18"

TERMS_TEXT = (
    "📄 <b>Документы VICTOR FC</b>\n\n"
    f"• <a href=\"{USER_AGREEMENT_URL}\">Пользовательское соглашение</a>\n"
    f"• <a href=\"{PACK_PURCHASE_TERMS_URL}\">Условия покупки цифровых товаров</a>\n"
    f"• <a href=\"{PRIVACY_POLICY_URL}\">Политика обработки персональных данных</a>\n\n"
    "Покупки за Telegram Stars — цифровые товары внутри игры. Если покупка не начислилась, "
    "мы начислим её или вернём звёзды: напиши /paysupport."
)

STATUS_LABELS = {
    "pending": "⏳ начисляется",
    "failed": "⏳ повторяем начисление",
    "delivered": "✅ начислено",
    "refunded": "↩️ звёзды возвращены",
}


class PaySupport(StatesGroup):
    waiting_for_problem = State()


def receipts_summary(rows) -> str:
    if not rows:
        return "У тебя пока нет оплат звёздами."
    lines = ["Твои последние оплаты:"]
    for row in rows:
        when = row["created_at"].strftime("%d.%m %H:%M")
        lines.append(f"• {when} — {row['total_amount']} ⭐ — {STATUS_LABELS.get(row['status'], row['status'])}")
    return "\n".join(lines)


@router.message(Command("terms"))
async def cmd_terms(message: Message) -> None:
    await message.answer(TERMS_TEXT, disable_web_page_preview=True)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, state: FSMContext) -> None:
    rows = await db.recent_stars_receipts(message.from_user.id)
    await state.set_state(PaySupport.waiting_for_problem)
    await message.answer(
        "🛟 <b>Поддержка по оплатам</b>\n\n"
        f"{receipts_summary(rows)}\n\n"
        "Если покупка не появилась в течение нескольких минут, мы начислим её вручную или вернём звёзды.\n\n"
        "Опиши проблему одним сообщением (что покупал и когда) — я передам его администрации. "
        "Передумал — отправь /cancel."
    )


@router.message(Command("cancel"), StateFilter(PaySupport.waiting_for_problem))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Хорошо, обращение отменено.")


@router.message(StateFilter(PaySupport.waiting_for_problem), F.text, ~F.text.startswith("/"))
async def receive_problem(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    rows = await db.recent_stars_receipts(user.id)
    who = html.escape(user.full_name or "") + (f" (@{user.username})" if user.username else "")
    if not settings.admin_ids:
        logger.error("paysupport request from %s but ADMIN_TELEGRAM_IDS is empty: %s", user.id, message.text)
    await alert_admins(
        message.bot,
        f"🛟 <b>/paysupport</b> от {who}, id <code>{user.id}</code>\n\n"
        f"{html.escape(message.text[:1500])}\n\n{receipts_summary(rows)}\n\n"
        "Платежи: админка → Магазин → Платежи Stars.",
    )
    await message.answer(
        "✅ Сообщение передано администрации. Мы свяжемся с тобой и всё решим."
    )
